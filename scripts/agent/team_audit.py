#!/usr/bin/env python3
"""团队体检机检脚本（team-steward 维护）。

把「团队编制/任务状态/交付物」里可机检的部分固化下来，避免靠 Lead
"碰巧注意到"才维护。只读仓库，不写任何文件；输出逐条 finding + 退出码。

覆盖 16 类检查（下表列初版 9 类 + 后续新增；最终以 run_checks 注册为准）
-------------
1. snapshot_health : 任务板快照是否存在/可解析/关键字段齐全（并提示快照可能过期）
2. roster          : `docs/guides/agent-team-org.md` §2 Owner 表 vs 快照成员/已退役集合
3. stall           : 快照里 `in_progress` 的任务，其 owner 已 `inactive` ⇒ 卡死；
                     **新增**：pending 任务无 owner ⇒ 无人认领（旧实现看不见，因为只扫 in_progress）
4. write_scope     : 未完成任务之间 writeScopes 重叠（含目录前缀重叠）⇒ 串行化风险；
                     **新增**：任务缺 owner/writeScopes ⇒ 检查输入不足（防「无输入=无冲突」假绿）
5. artifact_refs   : `artifacts/agent/verify/*.md` 中反引号引用的仓库路径是否真的存在
                     （"声称 ≠ 存在"）；任务声明的 `artifacts/.../*.md` 交付物是否存在
6. role_evidence   : `team/agents.json` 里 `status=active` 的角色，是否在
                     14 天内有可复跑证据（dispatch-log 派发 / 任务板 owner / 产物 mtime）。
                     补上 §4 漏检：声明 active 但从未运转的「幽灵角色」。
7. silent_failure  : **静默失败**（Lead 错误清单 A1–A5 的机检投影）。判据：
                     任何「完成/派发」声明都必须绑定到**可验证的产物**。
                     S1 done 无 report / S2 report 不存在 / S3 report mtime 晚于 done.ts
                     （=先写结论后干活）/ S4 spawn 超时未闭环 / S5 日志行序 ts 乱序。
8. contract_drift  : **契约 vs 现实**（D1/D2/D3 的机检投影）。逐条验证契约声明的机制
                     在现实中存在：event_stream.path 存在性、required_fields/phases 与
                     dispatch_log.py 常量一致、trigger_channel 证据路径存在、status 取值合法、
                     active 角色 id 与 roster 成员/别名对账（防「id 漂移导致活性检查假报」）。
9. commit_hygiene  : **Lead 自修链与不变量缺口**（Q3）。扫近 N 天 git 历史：
                     H1 提交说明自认"修复某提交引入的缺陷/回退/提交说明与代码不符"；
                     H2 同一文件同日改 ≥3 次（未收敛热点，仅 src/**）；
                     H3 `feat(` 改 src/** 但同 commit 未附带任何测试/探针（不变量缺位）。

10. dispatch_release / lessons / task_reports : 发版三查 / 教训库时效 / 任务报告存在性
                     （既有检查，详见各自函数注释）
11. plan_consulted   : **版本级规划是否先于实施**（AGENTS.md §0.5 L8）。task-100 新增。
                     对近 14 天提交里的版本号 V，比较「实施提交最早时间」与「docs/todo.md 计划最早落盘时间」；
                     实施早于计划 ⇒ WARN（首月宽限，之后 FAIL）。
12. role_registration: **角色注册三方全等**（org.md §2.3 执行纪律 1）。task-100 新增。
                     agents.json（active/standby，别名展开）== org.md §2+§2.2 == 快照 members；
                     且快照 exportedAt 必须晚于 agents.json/org.md 的 mtime。
13. dead_path_edit   : **改了无引用文件**（agent-team-lessons.md L0.3）。task-100 新增。
                     近 7 天改动的 src/scripts 文件，若全仓找不到一处 basename 引用且无 `@entry` 标记 ⇒ WARN。
14. mode_policy      : **spawn 是否显式做了模式决策**（AGENTS.md §0.5 L9）。task-100 新增。
                     扫 dispatch-log 的 phase=spawn：无 mode 字段或 modeExplicit=false ⇒ WARN
                     「静默默认 standard」；若整份日志都不记 mode ⇒ 显式报「无法判定 + checked_count」，不静默判绿。

用法
----
    python scripts/agent/team_audit.py            # 人类可读，FAIL⇒退出码 1
    python scripts/agent/team_audit.py --json     # 机器可读
    python scripts/agent/team_audit.py --strict   # WARN 也计入退出码
    python scripts/agent/team_audit.py --selftest # 自测：必须能红（三项）

证据口径
--------
每条 finding 都带 `evidence`（文件:行号 / 任务 id / 快照字段），不做无证据推测。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# 默认路径（相对仓库根）
# ---------------------------------------------------------------------------
DEFAULT_SNAPSHOT = "team/team-board-snapshot.json"
DEFAULT_ORG = "docs/guides/agent-team-org.md"
DEFAULT_VERIFY_DIR = "artifacts/agent/verify"
DEFAULT_AGENTS = "team/agents.json"
DEFAULT_DISPATCH_LOG = "team/dispatch-log.jsonl"
DEFAULT_DISPATCH_SCRIPT = "scripts/agent/dispatch_log.py"
DEFAULT_AGENTS_MD = "AGENTS.md"
ROLE_EVIDENCE_DAYS = 14
# silent_failure：done 记录与其 report 产物 mtime 的允许偏差（文件系统秒级 + 写入延迟）
DONE_REPORT_SKEW_SECONDS = 120
# silent_failure：spawn 超过该小时数仍无 done/retire 配对 ⇒ 派发未闭环
DISPATCH_ORPHAN_GRACE_HOURS = 6
# silent_failure：spawn→done 短于该秒数 ⇒ 闭环时间不可信（补记/伪造信号）
DISPATCH_MIN_TURNAROUND_SECONDS = 60
# commit_hygiene：默认扫描窗口（天）与热点阈值
COMMIT_WINDOW_DAYS = 3
HOTSPOT_MIN_COMMITS = 3
# task-100 新增检查的窗口/阈值（独立常量：不改既有检查的窗口语义）
PLAN_WINDOW_DAYS = 14            # plan_consulted：版本级实施/计划时序比对窗口
DEAD_PATH_WINDOW_DAYS = 7        # dead_path_edit：改动文件回溯窗口
MODE_POLICY_WINDOW_DAYS = 14     # mode_policy：spawn 记录回溯窗口
MAX_DEAD_PATH_FILES = 300        # dead_path_edit：单次最多检查的文件数（一次批量 git grep，成本可控）
DEFAULT_VERSION_FILE = "src/memoria/__version__.py"
TODO_DOC = "docs/todo.md"
# dead_path_edit：入口白名单标记（写在文件头 5 行内，实测生成，不允许只存在于文档约定）
ENTRY_MARKER_RE = re.compile(r"@entry\b")
_VERSION_RE = re.compile(r"\b\d+\.\d+\.\d+\b")
DEAD_PATH_EXTS = (".py", ".js", ".mjs", ".ts")
# mode_policy：DSH 四档（源码 tool-agent-team/src/index.ts）
VALID_MODES = ("mechanical", "standard", "deep", "creator")
# mode_policy 加分判据：任务描述明显只读/扫描类，却用了 standard/deep ⇒ 可能该用 mechanical
_MECHANICAL_DESC_RE = re.compile(r"扫描|统计|盘点|清点|只读|取数|生成报告|写报告|格式检查|列一下|数一数")
# agents.json 合法的角色状态（standby 是本轮新增：领域已登记但当前无活，不计活性）
VALID_ROLE_STATUS = ("active", "standby", "retired-in-dsh")
# trigger_channel 的合法类型前缀（真实通道；不许假装有 cron）
VALID_TRIGGER_TYPES = (
    "user-dialog", "explicit-dispatch", "keywords", "task-board",
    "user-dialog+task-board", "explicit-dispatch+keywords",
)

# 可被报告引用、且应当真实存在的仓库路径前缀
PATH_PREFIXES = (
    "scripts/",
    "src/",
    "docs/",
    "tests/",
    "config/",
    "packaging/",
    "artifacts/",
    "benchmarks/",
    "resources/",
    "Package/",
    # ★ 2026-10-23 新增：团队资产已迁入 team/（入库）。缺此前缀会让
    #   「契约声明的证据路径是否存在」这一类检查对 team/** 全部失明。
    "team/",
)

# 路径 token：从已知前缀开始，到空白/反引号/常见中文标点/引号/括号为止
PATH_TOKEN_RE = re.compile(
    r"(?<![\w./-])(" + "|".join(re.escape(p) for p in PATH_PREFIXES) + r")"
    r"[^\s`'\"，。；：、（）()\[\]<>|{}*?…“”‘’]+"
)

# 行尾需要剥掉的标点
_TRAILING_STRIP = ".,;:!?。，；：、」』”’)）]"
# `path:123` / `path:123-130` / `path:18,67` / `path:82/97/106` 行号后缀
_LINE_SUFFIX_RE = re.compile(r":\d+(?:[-/,:]\d+)*$")
# `path:limit.currentMembers` / `path:members` 这类字段锚点后缀（JSON/结构路径）
_FIELD_SUFFIX_RE = re.compile(r":[A-Za-z_][A-Za-z0-9_.\[\]]*(?::[A-Za-z_][A-Za-z0-9_.\[\]]*)*$")
# 「交付声明」标记：只有这类行上的缺失路径才算「声称 ≠ 存在」的 FAIL；
# 其余缺失引用（历史路径、一次性探针、被审计报告点名的缺文档）降为 WARN。
_CLAIM_RE = re.compile(r"已落盘|已交付|已产出|已生成|已写入|已保存|已提交|落盘|交付物")
# 「历史/计划/临时/被审计点名缺失」上下文：这类行上的缺失引用是叙述对象本身，不算交付缺陷
_CONTEXTUAL_RE = re.compile(
    r"原写|订正|旧路径|旧实现|已删|已清理|残留|临时|建议|计划|待建|待补|缺失|不存在|"
    r"未落盘|没有|不入库|PermissionError|沙箱|拒绝|拟|将新增|应补|历史|点名"
)

SKIP_TOKEN_MARKERS = ("*", "?", "{", "}", "<", ">", "…", "...", "$", "\\", "|")

# ---------------------------------------------------------------------------
# finding 模型
# ---------------------------------------------------------------------------
FAIL = "FAIL"
WARN = "WARN"
INFO = "INFO"
_SEV_ORDER = {FAIL: 0, WARN: 1, INFO: 2}


def _force_utf8_stdio() -> None:
    """Windows 控制台默认 cp1252，中文会 UnicodeEncodeError；统一转 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


@dataclass
class Finding:
    check: str
    severity: str
    message: str
    evidence: str

    def as_dict(self) -> dict:
        return {
            "check": self.check,
            "severity": self.severity,
            "message": self.message,
            "evidence": self.evidence,
        }


@dataclass
class AuditContext:
    repo: Path
    snapshot_path: Path
    org_path: Path
    verify_dir: Path
    agents_path: Path = Path(DEFAULT_AGENTS)
    dispatch_path: Path = Path(DEFAULT_DISPATCH_LOG)
    dispatch_script: Path = Path(DEFAULT_DISPATCH_SCRIPT)
    agents_md_path: Path = Path(DEFAULT_AGENTS_MD)
    commit_window_days: int = COMMIT_WINDOW_DAYS
    findings: list = field(default_factory=list)

    def add(self, check: str, severity: str, message: str, evidence: str) -> None:
        self.findings.append(Finding(check, severity, message, evidence))

    def rel(self, p: Path) -> str:
        try:
            return p.resolve().relative_to(self.repo.resolve()).as_posix()
        except ValueError:
            return p.as_posix()


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _parse_iso(ts: str):
    """解析快照 exportedAt（支持 +08:00 与 Z）。失败返回 None。"""
    if not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _git_head_commit_time(repo: Path):
    """返回 HEAD 提交时间（aware datetime）；非 git 仓库/无 git 返回 None。"""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "log", "-1", "--format=%ct"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        return datetime.fromtimestamp(int(out.stdout.strip()), tz=timezone.utc)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


# ---------------------------------------------------------------------------
# 1. 快照健康
# ---------------------------------------------------------------------------
def check_snapshot(ctx: AuditContext) -> dict | None:
    check = "snapshot_health"
    path = ctx.snapshot_path
    if not path.is_file():
        ctx.add(check, FAIL, f"缺任务板快照：{ctx.rel(path)} 不存在，无法机检编制/任务状态",
                f"missing file: {ctx.rel(path)}")
        return None
    try:
        data = json.loads(_read_text(path))
    except (OSError, json.JSONDecodeError) as exc:
        ctx.add(check, FAIL, f"快照无法解析：{exc}", f"{ctx.rel(path)}")
        return None

    if not isinstance(data, dict):
        ctx.add(check, FAIL, "快照顶层不是 JSON 对象", f"{ctx.rel(path)}")
        return None

    required = ("members", "tasks", "retired", "inactiveOwners", "limit")
    missing = [k for k in required if k not in data]
    if missing:
        ctx.add(check, FAIL, f"快照缺关键字段：{', '.join(missing)}", f"{ctx.rel(path)}")
        return data

    ctx.add(check, INFO,
            f"快照 exportedAt={data.get('exportedAt')}，成员 {len(data.get('members') or [])} 名，"
            f"任务 {len(data.get('tasks') or [])} 条，已退役 {len(data.get('retired') or [])} 个",
            f"{ctx.rel(path)}")

    limit = data.get("limit") or {}
    members = data.get("members") or []
    claimed_current = limit.get("currentMembers")
    if isinstance(claimed_current, int) and claimed_current != len(members):
        ctx.add(check, FAIL,
                f"快照自相矛盾：limit.currentMembers={claimed_current} 但 members 实有 {len(members)} 条",
                f"{ctx.rel(path)}:limit.currentMembers")
    max_members = limit.get("maxMembers")
    if isinstance(max_members, int) and len(members) > max_members:
        ctx.add(check, FAIL,
                f"成员数 {len(members)} 超过上限 maxMembers={max_members}",
                f"{ctx.rel(path)}:limit.maxMembers")

    # 快照过期提示：导出后又出现了新提交 / 新产物
    exported = _parse_iso(data.get("exportedAt"))
    if exported is None:
        ctx.add(check, WARN, f"快照 exportedAt 无法解析：{data.get('exportedAt')!r}",
                f"{ctx.rel(path)}:exportedAt")
    else:
        head_t = _git_head_commit_time(ctx.repo)
        if head_t is not None and head_t > exported.astimezone(timezone.utc):
            ctx.add(check, WARN,
                    "快照可能过期：导出后 HEAD 又有新提交（快照内容可能已落后于任务板实况）",
                    f"{ctx.rel(path)}:exportedAt={data.get('exportedAt')} < HEAD@{head_t.isoformat()}")
        newest = _newest_mtime([ctx.verify_dir])
        if newest is not None and newest > exported.astimezone(timezone.utc):
            ctx.add(check, WARN,
                    "快照可能过期：导出后 artifacts/agent/verify 有新产物落盘",
                    f"{ctx.rel(path)}:exportedAt={data.get('exportedAt')} < "
                    f"{ctx.rel(ctx.verify_dir)}@{newest.isoformat()}")
    return data


def _newest_mtime(paths: list[Path]):
    newest = None
    for base in paths:
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            try:
                mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
            except OSError:
                continue
            if newest is None or mtime > newest:
                newest = mtime
    return newest


# ---------------------------------------------------------------------------
# 2. 名册一致性（org.md §2 vs 快照）
# ---------------------------------------------------------------------------
_ORG_ROW_RE = re.compile(r"^\|\s*`([a-z0-9][a-z0-9-]*)`\s*\|")
_ORG_SECTION_RE = re.compile(r"^##\s+2\.(.*)$")
_NEXT_SECTION_RE = re.compile(r"^##\s+")
# ★ 2026-10-23 Lead 裁决：§2.2 的「非领域常驻成员」也是合法 roster 成员。
#   旧实现只解析 §2，导致快照里出现 todo-owner/team-curator 时被误判「名册漏登记」。
_RESIDENT_SECTION_RE = re.compile(r"^###\s+2\.2")
_RESIDENT_END_RE = re.compile(r"^##\s+|^###\s+")
# §2.2 的行首列形如 `\`todo-owner\`（TODO 文档 Owner）` —— 反引号后还有括号说明，
# 故不能用严格的 _ORG_ROW_RE（它要求反引号后直接是 `|`）。
_RESIDENT_ROW_RE = re.compile(r"^\|\s*`([a-z0-9][a-z0-9-]*)`")


def parse_org_owners(org_text: str) -> dict:
    """解析 §2 的 Owner 表第一列（反引号包裹的 agent 名）。"""
    lines = org_text.splitlines()
    owners = []
    start = None
    for i, line in enumerate(lines):
        if _ORG_SECTION_RE.match(line):
            start = i
            break
    if start is None:
        return {"owners": owners, "section_lines": None, "heading": None}
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if _NEXT_SECTION_RE.match(lines[j]):
            end = j
            break
    for k in range(start + 1, end):
        m = _ORG_ROW_RE.match(lines[k])
        if m:
            owners.append({"target": m.group(1), "line": k + 1})

    # ★ §2.2 非领域常驻成员（合法 roster 成员，但不算「领域 Owner」）
    resident = []
    r_start = None
    for i, line in enumerate(lines):
        if _RESIDENT_SECTION_RE.match(line):
            r_start = i
            break
    if r_start is not None:
        r_end = len(lines)
        for j in range(r_start + 1, len(lines)):
            if _RESIDENT_END_RE.match(lines[j]):
                r_end = j
                break
        for k in range(r_start + 1, r_end):
            m = _RESIDENT_ROW_RE.match(lines[k])
            if m:
                resident.append({"target": m.group(1), "line": k + 1})

    return {
        "owners": owners,
        "resident": resident,
        "section_lines": (start + 1, end),
        "heading": lines[start],
    }


def parse_org_counts(org_text: str, section_line: int | None) -> dict:
    """抽取文档自述的成员数量（§1 'N 个 teammate' 与 §2 标题 '当前 N 个'）。"""
    lines = org_text.splitlines()
    counts = {}
    m = re.search(r"\|\s*L1 常驻领域 Owner\s*\|\s*(\d+)\s*个 teammate", org_text)
    if m:
        counts["section1_teammates"] = int(m.group(1))
    if section_line is not None and section_line - 1 < len(lines):
        m2 = re.search(r"当前\s*(\d+)\s*个", lines[section_line - 1])
        if m2:
            counts["section2_current"] = int(m2.group(1))
    m3 = re.search(r"当前\s*(\d+)\s*名\s*teammate", org_text)
    if m3:
        counts["note_teammates"] = int(m3.group(1))
    return counts


def check_roster(ctx: AuditContext, data: dict | None) -> None:
    check = "roster"
    org_text = None
    if not ctx.org_path.is_file():
        ctx.add(check, FAIL, f"缺团队章程：{ctx.rel(ctx.org_path)} 不存在", f"missing {ctx.rel(ctx.org_path)}")
        return
    org_text = _read_text(ctx.org_path)
    parsed = parse_org_owners(org_text)
    org_owners = parsed["owners"]
    org_set = {o["target"] for o in org_owners}
    if not org_owners:
        ctx.add(check, FAIL, "无法从 §2 解析出任何 Owner 行（表格格式可能变了）",
                f"{ctx.rel(ctx.org_path)}:§2")
    if data is None:
        ctx.add(check, WARN, "快照不可用，名册比对跳过（仅能核对文档内部数字）", "snapshot unavailable")
        data = {}

    members = data.get("members") or []
    retired = {r.get("target") for r in (data.get("retired") or []) if isinstance(r, dict)}
    # ★ §2.2 非领域常驻成员：合法 roster 成员（不算领域 Owner，但必须允许出现在快照里）
    residents = {r["target"] for r in (parsed.get("resident") or [])}
    teammate_targets = {
        m.get("target") for m in members
        if isinstance(m, dict) and m.get("role") != "lead" and m.get("target")
    }

    for o in org_owners:
        if o["target"] not in teammate_targets and not data.get("members"):
            continue
        if o["target"] not in teammate_targets:
            ctx.add(check, FAIL,
                    f"org.md §2 列出的 Owner `{o['target']}` 不在快照成员中（疑似已退役但表未更新）",
                    f"{ctx.rel(ctx.org_path)}:{o['line']} vs {ctx.rel(ctx.snapshot_path)}:members")
    # §2.2 常驻成员：出现在快照里是**合法的**，不报 FAIL
    org_legal = org_set | residents

    # ★ 2026-10-24：按任务 spawn 的一次性执行者（ephemeral_agents）也是合法成员。
    #   它们不入常驻名册（org.md 无法预知每次会 spawn 谁），但必须显式登记在
    #   team/agents.json → ephemeral_agents（含 purpose/task/dispose_when），
    #   否则仍然 FAIL —— 保留「名册漂移检测」强度，只豁免已声明的那批。
    ephemeral = set()
    try:
        reg = json.loads((ctx.repo / "team" / "agents.json").read_text(encoding="utf-8"))
        for item in (reg.get("ephemeral_agents") or []):
            tid = item.get("id") if isinstance(item, dict) else None
            if tid:
                ephemeral.add(tid)
    except (OSError, ValueError, AttributeError):
        pass

    for target in sorted(teammate_targets - org_legal - ephemeral):
        ctx.add(check, FAIL,
                f"快照成员 `{target}` 未出现在 org.md §2 Owner 表中（名册漏登记）",
                f"{ctx.rel(ctx.snapshot_path)}:members vs {ctx.rel(ctx.org_path)}:§2")
    for target in sorted(teammate_targets & ephemeral):
        ctx.add(check, INFO,
                f"按任务 spawn 的执行者 `{target}`（已声明于 agents.json:ephemeral_agents，不计入常驻名册）",
                f"{ctx.rel(ctx.snapshot_path)}:members")
    for target in sorted(retired & org_set):
        ctx.add(check, FAIL,
                f"已退役的 `{target}` 仍出现在 org.md §2 当前 Owner 表中（应为历史记录/删除）",
                f"{ctx.rel(ctx.snapshot_path)}:retired vs {ctx.rel(ctx.org_path)}:§2")
    for target in sorted(retired & teammate_targets):
        # 2026-10-24：名字复用（同一角色换人）是合法的 —— 退役条目只有 target/description，
        # 无法区分"退役未生效"与"角色换代"。故降为 WARN 并要求 org.md 标注代次，
        # 由人/管理员复核；不静默通过，也不误判为 FAIL。
        ctx.add(check, WARN,
                f"`{target}` 同时出现在 retired 与 members —— 名字复用/角色换代？"
                f"（若为换代请在 org.md 标注代次；若为退役未生效请检查花名册）",
                f"{ctx.rel(ctx.snapshot_path)}:retired vs :members")

    # 文档内部数字自洽
    counts = parse_org_counts(org_text, parsed["section_lines"][0] if parsed["section_lines"] else None)
    actual = len(org_owners)
    if "section1_teammates" in counts and counts["section1_teammates"] != actual:
        ctx.add(check, FAIL,
                f"org.md §1 自称 {counts['section1_teammates']} 个 teammate，但 §2 表实有 {actual} 行",
                f"{ctx.rel(ctx.org_path)}:§1 vs §2")
    if "section2_current" in counts and counts["section2_current"] != actual:
        ctx.add(check, FAIL,
                f"org.md §2 标题自称「当前 {counts['section2_current']} 个」，但表实有 {actual} 行",
                f"{ctx.rel(ctx.org_path)}:§2 heading")
    if "note_teammates" in counts and counts["note_teammates"] != actual:
        ctx.add(check, FAIL,
                f"org.md §2 注记自称「当前 {counts['note_teammates']} 名 teammate」，但表实有 {actual} 行",
                f"{ctx.rel(ctx.org_path)}:§2 note")
    if org_owners and data.get("members"):
        # 快照口径：teammates = members - lead
        expected_total = actual + len(residents) + len(teammate_targets & ephemeral)
        if len(teammate_targets) != expected_total:
            ctx.add(check, FAIL,
                    f"快照 teammate 数 {len(teammate_targets)} ≠ org.md §2 领域 Owner {actual} + §2.2 常驻 {len(residents)} = {expected_total}",
                    f"{ctx.rel(ctx.snapshot_path)}:members vs {ctx.rel(ctx.org_path)}:§2+§2.2")
    if org_owners:
        ctx.add(check, INFO, f"org.md §2 解析到 {actual} 个领域 Owner：{', '.join(o['target'] for o in org_owners)}",
                f"{ctx.rel(ctx.org_path)}:§2")
        if residents:
            ctx.add(check, INFO, f"org.md §2.2 解析到 {len(residents)} 个非领域常驻：{', '.join(sorted(residents))}",
                    f"{ctx.rel(ctx.org_path)}:§2.2")


# ---------------------------------------------------------------------------
# 3. 卡死检测
# ---------------------------------------------------------------------------
def check_stalls(ctx: AuditContext, data: dict | None) -> None:
    check = "stall"
    if not data:
        ctx.add(check, WARN, "快照不可用，卡死检测跳过", "snapshot unavailable")
        return
    inactive = set(data.get("inactiveOwners") or [])
    members = {m.get("target") for m in (data.get("members") or []) if isinstance(m, dict)}
    tasks = [t for t in (data.get("tasks") or []) if isinstance(t, dict)]
    in_progress = [t for t in tasks if t.get("status") == "in_progress"]

    # ★ 2026-10-23 新增（Curator 第三轮）：未完成任务「无人认领」也必须报。
    #   旧实现只扫 in_progress 且在此处提前 return ⇒ 12 条 pending 任务 0 条有 owner 时
    #   全线静默，这正是「该做的事没做且不报错」的结构（Lead 清单 Q1）。
    unclaimed = [t for t in tasks if t.get("status") != "completed" and not t.get("owner")]
    if unclaimed:
        ids = [str(t.get("id", "?")) for t in unclaimed]
        ctx.add(check, WARN,
                f"未完成任务有 {len(unclaimed)}/{len(tasks)} 条没有 owner 字段"
                f"（无人认领 ⇒ 没人会被 stall 检查覆盖）：{', '.join(ids[:8])}"
                + ("…" if len(ids) > 8 else ""),
                f"{ctx.rel(ctx.snapshot_path)}:tasks[].owner 缺失")
    claimed = [t for t in tasks if t.get("status") != "completed" and t.get("owner")]
    if claimed:
        ctx.add(check, INFO, f"未完成任务 {len(claimed)} 条已认领（有 owner 字段）",
                f"{ctx.rel(ctx.snapshot_path)}:tasks")

    if not in_progress:
        ctx.add(check, INFO, "快照中没有 in_progress 任务", f"{ctx.rel(ctx.snapshot_path)}:tasks")
        return
    for t in in_progress:
        tid = t.get("id", "?")
        owner = t.get("owner")
        if owner in inactive:
            ctx.add(check, FAIL,
                    f"任务 {tid} 处于 in_progress，但 owner `{owner}` 已 inactive ⇒ 卡死信号"
                    f"（需 Lead 催办/改派，或确认快照过期）",
                    f"{ctx.rel(ctx.snapshot_path)}:tasks[{tid}].status=in_progress, "
                    f"inactiveOwners contains {owner}")
        if owner not in members:
            ctx.add(check, FAIL,
                    f"任务 {tid} 的 owner `{owner}` 不在快照成员中（幽灵 owner）",
                    f"{ctx.rel(ctx.snapshot_path)}:tasks[{tid}].owner")


# ---------------------------------------------------------------------------
# 4. 写域重叠（advisory）
# ---------------------------------------------------------------------------
def _norm_scope(s: str) -> str:
    s = s.strip().replace("\\", "/")
    while s.startswith("./"):
        s = s[2:]
    return s.rstrip("/")


def scopes_overlap(a: str, b: str) -> str | None:
    """返回重叠说明；无重叠返回 None。目录前缀按路径段边界判定。"""
    a, b = _norm_scope(a), _norm_scope(b)
    if a == b:
        return a
    if a.startswith(b + "/"):
        return a
    if b.startswith(a + "/"):
        return b
    return None


def check_write_scopes(ctx: AuditContext, data: dict | None) -> None:
    check = "write_scope"
    if not data:
        ctx.add(check, WARN, "快照不可用，写域重叠检测跳过", "snapshot unavailable")
        return
    tasks = [t for t in (data.get("tasks") or []) if isinstance(t, dict)]
    active = [t for t in tasks if t.get("status") != "completed"]
    # ★ 2026-10-23 新增：先验「检查有没有输入」。
    #   旧实现在 writeScopes 全缺失时输出「两两写域无重叠」= **假绿**：
    #   没有写域可比 ≠ 没有冲突。命令与判据必须分开。
    with_scopes = [t for t in active if t.get("writeScopes")]
    if active and not with_scopes:
        ctx.add(check, WARN,
                f"写域检查**输入不足**：{len(active)} 条未完成任务全部没有 writeScopes 字段"
                f"⇒ 本次「无重叠」结论无效（假绿风险），不能作为收口依据",
                f"{ctx.rel(ctx.snapshot_path)}:tasks[].writeScopes 全缺失")
    elif with_scopes and len(with_scopes) < len(active):
        ctx.add(check, WARN,
                f"写域检查**输入不全**：{len(active)} 条未完成任务中仅 {len(with_scopes)} 条有 writeScopes"
                f"⇒ 覆盖不完整（缺的 {len(active) - len(with_scopes)} 条无法参与冲突判定）",
                f"{ctx.rel(ctx.snapshot_path)}:tasks[].writeScopes 部分缺失")
    conflicts = 0
    for i in range(len(active)):
        for j in range(i + 1, len(active)):
            t1, t2 = active[i], active[j]
            if t1.get("owner") == t2.get("owner"):
                continue  # 同一 owner 内串行是它的自由
            for s1 in t1.get("writeScopes") or []:
                for s2 in t2.get("writeScopes") or []:
                    overlap = scopes_overlap(str(s1), str(s2))
                    if overlap:
                        conflicts += 1
                        ctx.add(check, WARN,
                                f"未完成任务 {t1.get('id')} 与 {t2.get('id')} 写域重叠：{overlap}"
                                f"（串行化风险，advisory）",
                                f"{ctx.rel(ctx.snapshot_path)}:tasks[{t1.get('id')}].writeScopes "
                                f"∩ tasks[{t2.get('id')}].writeScopes = {overlap}")
    if conflicts == 0:
        # 只有在「输入完整」时，「无重叠」才是可采信的结论
        if active and len(with_scopes) == len(active):
            ctx.add(check, INFO,
                    f"未完成任务 {len(active)} 条（写域字段齐全），两两写域无重叠",
                    f"{ctx.rel(ctx.snapshot_path)}:tasks")
        elif not active:
            ctx.add(check, INFO, "无未完成任务，写域检查无输入（非结论）",
                    f"{ctx.rel(ctx.snapshot_path)}:tasks")


# ---------------------------------------------------------------------------
# 5. 产物落盘核验（声称 ≠ 存在）
# ---------------------------------------------------------------------------
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")


def iter_inline_code_refs(md_text: str):
    """产出 (行号, 反引号内容, 整行文本)；跳过 fenced code block。"""
    in_fence = False
    for lineno, line in enumerate(md_text.splitlines(), start=1):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for m in _INLINE_CODE_RE.finditer(line):
            yield lineno, m.group(1), line


def extract_path_tokens(code_span: str):
    for m in PATH_TOKEN_RE.finditer(code_span):
        # brace glob（`x.{json,md}` / `run{1..5}`）：不是单个真实路径，跳过
        if code_span[m.end():m.end() + 1] == "{":
            continue
        token = m.group(0).strip()
        # 反复剥 行号后缀 + 尾标点，直到稳定
        for _ in range(3):
            before = token
            token = token.rstrip(_TRAILING_STRIP)
            token = _LINE_SUFFIX_RE.sub("", token)
            token = _FIELD_SUFFIX_RE.sub("", token)
            if token == before:
                break
        if not token or any(marker in token for marker in SKIP_TOKEN_MARKERS):
            continue
        # 反引号被截断成半截路径（如 `09-）时不是完整引用
        if token.endswith(("-", "_", "\\")):
            continue
        yield token


def check_task_reports(ctx: AuditContext, data: dict | None) -> None:
    """任务声明的 `artifacts/.../*.md` 交付物必须真实存在。"""
    check = "artifact_refs"
    if not data:
        return
    for t in data.get("tasks") or []:
        if not isinstance(t, dict):
            continue
        for scope in t.get("writeScopes") or []:
            scope = str(scope).replace("\\", "/").strip()
            if not scope.endswith(".md") or not scope.startswith("artifacts/"):
                continue
            if any(marker in scope for marker in SKIP_TOKEN_MARKERS):
                continue
            if not (ctx.repo / scope).is_file():
                ctx.add(check, FAIL,
                        f"任务 {t.get('id')} 声明的交付物不存在：{scope}（已完成任务=交付物缺失）",
                        f"{ctx.rel(ctx.snapshot_path)}:tasks[{t.get('id')}].writeScopes")


def check_artifact_refs(ctx: AuditContext) -> None:
    check = "artifact_refs"
    if not ctx.verify_dir.is_dir():
        ctx.add(check, FAIL, f"缺验证报告目录：{ctx.rel(ctx.verify_dir)}", f"missing dir {ctx.rel(ctx.verify_dir)}")
        return
    reports = sorted(ctx.verify_dir.glob("*.md"))
    if not reports:
        ctx.add(check, FAIL, "验证报告目录为空，无可核验产物", f"{ctx.rel(ctx.verify_dir)}")
        return

    # token -> {"claim": [site...], "other": [site...], "contextual": [site...]}
    missing: dict[str, dict[str, list[str]]] = {}
    checked = 0
    broken_reports = []
    for rp in reports:
        rel_report = ctx.rel(rp)
        try:
            text = _read_text(rp)
        except OSError as exc:
            broken_reports.append((rel_report, str(exc)))
            continue
        if not text.strip():
            broken_reports.append((rel_report, "empty file"))
            continue
        for lineno, span, line in iter_inline_code_refs(text):
            is_claim_line = bool(_CLAIM_RE.search(line))
            is_contextual = bool(_CONTEXTUAL_RE.search(line))
            for token in extract_path_tokens(span):
                checked += 1
                if (ctx.repo / token).exists():
                    continue
                bucket = missing.setdefault(token, {"claim": [], "other": [], "contextual": []})
                if is_claim_line:
                    key = "claim"
                elif is_contextual:
                    key = "contextual"
                else:
                    key = "other"
                bucket[key].append(f"{rel_report}:{lineno}")

    for rel_report, reason in broken_reports:
        ctx.add(check, FAIL, f"报告不可读/为空：{reason}", rel_report)

    claim_missing = {t: v["claim"] for t, v in missing.items() if v["claim"]}
    other_missing = {t: v["other"] for t, v in missing.items() if not v["claim"] and v["other"]}
    contextual_missing = {t: v["contextual"] for t, v in missing.items()
                          if not v["claim"] and not v["other"]}
    for token in sorted(claim_missing):
        sites = claim_missing[token]
        more = "" if len(sites) <= 3 else f" 等 {len(sites)} 处"
        ctx.add(check, FAIL,
                f"交付声明引用了不存在的仓库路径：{token}（声称 ≠ 存在）",
                "; ".join(sites[:3]) + more)
    for token in sorted(other_missing):
        sites = other_missing[token]
        ctx.add(check, WARN,
                f"报告提及的仓库路径不存在：{token}（可能是一次性/已清理产物或历史路径，需人工判读）",
                "; ".join(sites[:2]) + (f" 等 {len(sites)} 处" if len(sites) > 2 else ""))
    if contextual_missing:
        examples = sorted(contextual_missing)[:6]
        ctx.add(check, INFO,
                f"另有 {len(contextual_missing)} 个缺失引用出现在「历史/计划/临时/被审计点名缺失」语境中："
                + ", ".join(examples) + ("…" if len(contextual_missing) > 6 else ""),
                ctx.rel(ctx.verify_dir) + "/*.md")
    ctx.add(check, INFO,
            f"扫描 {len(reports)} 份报告、{checked} 条路径引用；交付声明缺失 {len(claim_missing)} 个、"
            f"非声明缺失 {len(other_missing)} 个、语境豁免 {len(contextual_missing)} 个",
            f"{ctx.rel(ctx.verify_dir)}/*.md")


# ---------------------------------------------------------------------------
# 6. 角色活性证据（agents.json active 角色 vs 14 天可复跑证据）
# ---------------------------------------------------------------------------
def _newest_under(path: Path):
    """返回文件或目录树内最新的 mtime（UTC aware）；不存在返回 None。"""
    if not path.exists():
        return None
    if path.is_file():
        try:
            return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            return None
    newest = None
    for p in path.rglob("*"):
        if not p.is_file():
            continue
        try:
            mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue
        if newest is None or mtime > newest:
            newest = mtime
    return newest


def _evidence_path_newest(repo: Path, raw: str):
    """把 agents.json 的 evidence_path 规整到可探测的静态前缀并取最新 mtime。

    支持真实文件/目录、glob（`verify/**`）与占位符（`audit-<date>/`）。
    - glob/`?` 的静态基目录**必须真实存在**，否则返回 None（不回退父目录，
      否则任意 `void/**` 都会回退到 `artifacts/agent/` 产生「假证据」）；
    - `<...>`/`{...}` 是文件名内占位符，允许回退到父目录。
    非路径（如 `git log -- ...`）返回 None。
    """
    text = str(raw).strip()
    if not text.startswith(PATH_PREFIXES):
        return None
    marker = None
    cut_at = -1
    for candidate in ("<", "{", "[", "*", "?"):
        idx = text.find(candidate)
        if idx >= 0 and (cut_at < 0 or idx < cut_at):
            cut_at, marker = idx, candidate
    if cut_at >= 0:
        text = text[:cut_at]
    allow_parent_fallback = marker in ("<", "{", "[")
    text = text.rstrip("/")
    while text:
        newest = _newest_under(repo / text)
        if newest is not None:
            return newest
        if not allow_parent_fallback or "/" not in text:
            return None
        text = text.rsplit("/", 1)[0]
    return None


def _parse_dispatch_stamps(path: Path) -> list[tuple]:
    """读取 dispatch-log，返回 [(ts, actor, target)]（坏行忽略，由 dispatch_log.py 负责报错）。"""
    rows = []
    if not path.is_file():
        return rows
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        ts = _parse_iso(str(obj.get("ts", "")))
        if ts is None:
            continue
        rows.append((ts.astimezone(timezone.utc), str(obj.get("actor") or ""), str(obj.get("target") or "")))
    return rows


def check_role_evidence(ctx: AuditContext, data: dict | None) -> None:
    """active 角色必须有 14 天证据；否则 WARN（幽灵角色，需 Lead 判 retired 或补派发）。

    证据来源三选一（任一即可）：dispatch-log 出现该 actor/target、任务板 owner、
    evidence_path 指向的产物在窗口内有过写入。这是 §2.2 三条硬判据的机检投影。
    """
    check = "role_evidence"
    path = ctx.agents_path
    if not path.is_file():
        ctx.add(check, INFO, f"未找到 {ctx.rel(path)}，角色活性检查跳过", f"missing file: {ctx.rel(path)}")
        return
    try:
        payload = json.loads(_read_text(path))
    except (OSError, json.JSONDecodeError) as exc:
        ctx.add(check, FAIL, f"角色能力目录无法解析：{exc}", f"{ctx.rel(path)}")
        return
    agents = [a for a in (payload.get("agents") or []) if isinstance(a, dict)]
    active = [a for a in agents if a.get("status") == "active"]
    if not active:
        ctx.add(check, INFO, f"{ctx.rel(path)} 无 active 角色", f"{ctx.rel(path)}:agents")
        return

    cutoff = datetime.now(timezone.utc) - timedelta(days=ROLE_EVIDENCE_DAYS)
    dispatch = _parse_dispatch_stamps(ctx.dispatch_path)
    owners = set()
    for t in (data or {}).get("tasks") or []:
        if isinstance(t, dict) and t.get("owner"):
            owners.add(str(t["owner"]))

    evidenced, ghosts = [], []
    for agent in active:
        aid = str(agent.get("id") or "?")
        # ★ 2026-10-23：id 与 roster 成员名/本轮 spawn 名可能不同（curator / team-curator /
        #   curator-r3）。只看精确 id 会让真实有派发的角色被误判「幽灵」。
        #   口径：agents.json 显式声明的 roster_alias 才参与匹配（声明即契约）。
        ids = {aid} | {str(a) for a in (agent.get("roster_alias") or [])}
        sources = []
        if any((actor in ids or target in ids) and ts >= cutoff for ts, actor, target in dispatch):
            sources.append("dispatch-log")
        if ids & owners:
            sources.append("team-board owner")
        newest = None
        for raw in agent.get("evidence_path") or []:
            # 只认「角色专属产物」：路径里必须出现角色 id 或其已声明别名，避免所有人共用
            # artifacts/agent/verify/** 这类公共目录而互相「借证据」。
            low = str(raw).lower()
            if not any(i.lower() in low for i in ids):
                continue
            stamp = _evidence_path_newest(ctx.repo, raw)
            if stamp is not None and (newest is None or stamp > newest):
                newest = stamp
        if newest is not None and newest >= cutoff:
            sources.append(f"产物 {newest.date().isoformat()}")
        if sources:
            evidenced.append(f"{aid}({', '.join(sources)})")
        else:
            ghosts.append(aid)
            ctx.add(check, WARN,
                    f"active 角色 `{aid}` 在 {ROLE_EVIDENCE_DAYS} 天内无派发/任务/产物证据"
                    f"（幽灵角色：须 Lead 判 retired-in-dsh 或补 dispatch-log）",
                    f"{ctx.rel(path)}:agents[{aid}].status=active; 无 dispatch-log 记录、"
                    f"无任务板 owner、evidence_path 产物早于 cutoff")
    if ghosts:
        ctx.add(check, WARN,
                f"agents.json 有 {len(ghosts)} 个 active 角色缺 {ROLE_EVIDENCE_DAYS} 天证据："
                + ", ".join(ghosts),
                f"{ctx.rel(path)}:agents")
    else:
        ctx.add(check, INFO,
                f"agents.json active 角色 {len(active)} 个，均有 {ROLE_EVIDENCE_DAYS} 天证据："
                + "; ".join(evidenced),
                f"{ctx.rel(path)}:agents + {ctx.rel(ctx.dispatch_path)}")


# ---------------------------------------------------------------------------
# 7. 静默失败（Lead 错误清单 A1–A5 的机检投影）
# ---------------------------------------------------------------------------
def _read_dispatch_rows(path: Path) -> list[dict]:
    """按文件行序读取 dispatch-log（保留行号；坏行跳过，由 dispatch_log.py 负责报错）。"""
    rows: list[dict] = []
    if not path.is_file():
        return rows
    for lineno, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        obj["_line"] = lineno
        rows.append(obj)
    return rows


def _mtime_utc(path: Path):
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None


def _born_utc(path: Path):
    """文件**创建**时间（判断「done 时产物是否已存在」的正确依据）。

    Windows 的 `st_ctime` 即创建时间；POSIX 上 `st_ctime` 是 inode 变更时间（≥创建），
    因此取 mtime 与 st_ctime 的较小值作为创建时间的保守下界：宁可漏报，不可误报。
    """
    try:
        st = path.stat()
    except OSError:
        return None
    birth = getattr(st, "st_birthtime", None)
    try:
        if birth:
            return datetime.fromtimestamp(birth, tz=timezone.utc)
        return datetime.fromtimestamp(min(st.st_mtime, st.st_ctime), tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _dispatch_worker(row: dict) -> str:
    """一条派发记录里「被派去做事的那个 agent」是谁。

    语义不对称（实测踩到）：`spawn` 的 `target` 是**被派者**，而 teammate 回报 done 时
    `actor`=teammate、`target`=lead。若只按 `target` 配对，所有 teammate 的 done 都会被
    错当成 Lead 的收口 ⇒ S4/S6 恒不触发（假绿）。
    口径：actor 不是 lead/空 ⇒ worker=actor；否则 worker=target。
    """
    actor = str(row.get("actor") or "")
    target = str(row.get("target") or "")
    if actor and actor.lower() not in ("lead", ""):
        return actor
    return target


def check_silent_failure(ctx: AuditContext) -> None:
    """「该做的没做，且不报错」的机检投影。

    抽象（Lead §F Q1）：A1–A5 的共同结构不是「代码有 bug」，而是
    **某个动作被声明为已完成，但它的可验证后果不存在，且没有任何检查去核对这个绑定**。
    因此可机检的判据只有一条：

        每条「完成 / 派发」声明，都必须绑定到一个**当时已存在**的产物。

    落到 dispatch-log 上是 5 条规则（S1–S5）。它们全部只读磁盘，不需要跑产品。
    """
    check = "silent_failure"
    path = ctx.dispatch_path
    if not path.is_file():
        ctx.add(check, INFO,
                f"无 {ctx.rel(path)}，静默失败检查跳过（缺失本身由 dispatch_log.py check 报）",
                f"missing file: {ctx.rel(path)}")
        return
    rows = _read_dispatch_rows(path)
    if not rows:
        ctx.add(check, WARN, "dispatch-log 为空 ⇒ 无法验证任何派发/完成绑定（活性不可机检）",
                f"{ctx.rel(path)}:0 行")
        return

    now = datetime.now(timezone.utc)
    problems = 0
    exempt = 0  # S1-exempt：显式 no_report_reason 豁免计数（可见但不阻断）

    # ---- 更正协议：append-only 日志的「更正靠新增记录」（AGENTS.md §3 铁律 ④） ----
    # backfill 记录若带 corrects{line,field,new}，则第 line 行的该字段以 new 为准。
    corrections: dict[int, dict] = {}
    for row in rows:
        fix = row.get("corrects")
        if isinstance(fix, dict) and isinstance(fix.get("line"), int):
            corrections[fix["line"]] = fix
    corrected_ok = 0

    # ---- S1/S2/S3：done 记录必须绑定到当时已存在的产物 ----
    for row in rows:
        if row.get("phase") != "done":
            continue
        ts = _parse_iso(str(row.get("ts", "")))
        ts_utc = ts.astimezone(timezone.utc) if ts else None
        report = row.get("report")
        where = f"{ctx.rel(path)}:{row['_line']}"
        fix = corrections.get(row["_line"])
        if fix and str(fix.get("field") or "report") == "report":
            new_report = str(fix.get("new") or "")
            if new_report and (ctx.repo / new_report.replace("\\", "/")).exists():
                corrected_ok += 1
                continue  # 已按声明更正，且更正后的产物真实存在
            problems += 1
            ctx.add(check, FAIL,
                    f"第 {row['_line']} 行声明更正为 {new_report!r}，但该产物仍不存在"
                    f"（更正本身不可验证 = 二次静默失败）",
                    f"{where} corrects={fix}")
            continue
        if not report:
            # S1-exempt：dispatch_log.py 允许 --no-report-reason 显式豁免。
            # 两个工具必须口径一致，否则同一份数据 A 工具放行、B 工具判 FAIL（实测踩到）。
            # 保留可见性：豁免记 WARN 而非静默放过；同一 actor 反复豁免仍会被 WARN 计数看见。
            exempt_reason = str(row.get("no_report_reason") or "").strip()
            if exempt_reason:
                exempt += 1
                ctx.add(check, WARN,
                        f"done 未绑定产物，但已显式声明豁免（S1-exempt）："
                        f"{exempt_reason[:100]}",
                        f"{where} actor={row.get('actor')} task={row.get('task')}")
                continue
            problems += 1
            ctx.add(check, FAIL,
                    f"done 记录未绑定任何产物（S1：完成无 report ⇒ 无法验证「做完了」）"
                    f"（无产物时应写 no_report_reason 显式豁免，而不是留空）",
                    f"{where} actor={row.get('actor')} task={row.get('task')}")
            continue
        target = ctx.repo / str(report).replace("\\", "/")
        if not target.exists():
            problems += 1
            ctx.add(check, FAIL,
                    f"done 记录引用的产物不存在（S2：声称 ≠ 存在）：{report}"
                    f"（如系路径迁移/改名，按更正协议追加一条带 corrects 的 backfill 记录）",
                    f"{where} report={report}")
            continue
        born = _born_utc(target)
        if ts_utc and born and born > ts_utc + timedelta(seconds=DONE_REPORT_SKEW_SECONDS):
            problems += 1
            ctx.add(check, WARN,
                    f"done 记录时间早于其产物**创建**时间（S3：先写结论后干活）："
                    f"{report} 创建于 {born.astimezone().isoformat(timespec='seconds')} "
                    f"晚于 done.ts {ts_utc.astimezone().isoformat(timespec='seconds')}",
                    f"{where} report={report}")

    # ---- S4：spawn 必须有后续 done/retire 配对（按 worker） ----
    closed: dict[str, list[datetime]] = {}
    for row in rows:
        if row.get("phase") in ("done", "retire"):
            worker = _dispatch_worker(row)
            ts = _parse_iso(str(row.get("ts", "")))
            if worker and ts:
                closed.setdefault(worker, []).append(ts.astimezone(timezone.utc))
    for row in rows:
        if row.get("phase") != "spawn":
            continue
        target = _dispatch_worker(row)
        ts = _parse_iso(str(row.get("ts", "")))
        if not target or not ts:
            continue
        ts_utc = ts.astimezone(timezone.utc)
        if now - ts_utc < timedelta(hours=DISPATCH_ORPHAN_GRACE_HOURS):
            continue  # 可能仍在飞；给宽限期，避免误报进行中的派发
        if any(t >= ts_utc for t in closed.get(target, [])):
            continue
        problems += 1
        ctx.add(check, WARN,
                f"派发未闭环（S4）：spawn `{target}` 已超过 "
                f"{DISPATCH_ORPHAN_GRACE_HOURS}h 无对应 done/retire（静默失踪风险）",
                f"{ctx.rel(path)}:{row['_line']} task={row.get('task')}")

    # ---- S5：append-only 日志的行序必须与 ts 同向（否则因果不可读） ----
    stamps = []
    for row in rows:
        ts = _parse_iso(str(row.get("ts", "")))
        if ts:
            stamps.append((ts.astimezone(timezone.utc), row["_line"]))
    inversions = [
        (prev, cur) for prev, cur in zip(stamps, stamps[1:]) if cur[0] < prev[0]
    ]
    if inversions:
        problems += 1
        prev, cur = inversions[0]
        ctx.add(check, WARN,
                f"dispatch-log 行序与时间不同向（S5：{len(inversions)} 处倒序，追加顺序≠事件顺序）",
                f"{ctx.rel(path)}: 第 {cur[1]} 行 @{cur[0].isoformat()} 早于第 {prev[1]} 行 @{prev[0].isoformat()}")

    # ---- S6：spawn→done 间隔短到不可能完成实际工作 ⇒ 要么是补记、要么是伪造 ----
    #   真实事故（2026-10-23 第 11/12 行）：team-curator 的 spawn 与 done 相差 **1 秒**，
    #   而其产物实际落盘晚 13 分钟 ⇒ 「闭环时间」不是真实时间，不能用它判断是否按时完成。
    spawn_ts: dict[str, list[datetime]] = {}
    for row in rows:
        if row.get("phase") != "spawn":
            continue
        worker = _dispatch_worker(row)
        ts = _parse_iso(str(row.get("ts", "")))
        if worker and ts:
            spawn_ts.setdefault(worker, []).append(ts.astimezone(timezone.utc))
    for row in rows:
        if row.get("phase") not in ("done", "retire"):
            continue
        worker = _dispatch_worker(row)
        ts = _parse_iso(str(row.get("ts", "")))
        if not worker or not ts:
            continue
        done_utc = ts.astimezone(timezone.utc)
        # 取「本条 done 之前最近的一次 spawn」作为配对起点（同一 worker 可能被派多次）
        starts = [s for s in spawn_ts.get(worker, []) if s <= done_utc]
        if not starts:
            continue
        delta = done_utc - max(starts)
        if timedelta(seconds=0) <= delta < timedelta(seconds=DISPATCH_MIN_TURNAROUND_SECONDS):
            problems += 1
            ctx.add(check, WARN,
                    f"派发闭环时间不可信（S6）：`{worker}` 从 spawn 到 {row['phase']} 仅 "
                    f"{delta.total_seconds():.0f}s（< {DISPATCH_MIN_TURNAROUND_SECONDS}s）"
                    f"⇒ 该 done 的 ts 是补记/估计值，不能用于「是否按时完成」的判断",
                    f"{ctx.rel(path)}:{row['_line']}")

    if problems == 0:
        ctx.add(check, INFO,
                f"dispatch-log {len(rows)} 条：done 记录均绑定到当时已存在的产物"
                f"（其中 {corrected_ok} 条按更正协议指向新路径）、spawn 均已闭环、行序单调",
                f"{ctx.rel(path)}")


# ---------------------------------------------------------------------------
# 8. 契约漂移（声明 vs 现实）
# ---------------------------------------------------------------------------
_CONST_LIST_RE = r"%s\s*=\s*[\(\[]([^\)\]]*)[\)\]]"


def _parse_py_const_list(text: str, name: str) -> list[str] | None:
    """从 python 源码里抽 `NAME = ("a", "b")` 形式的常量元组/列表。"""
    m = re.search(_CONST_LIST_RE % re.escape(name), text)
    if not m:
        return None
    return [v.strip().strip("\"'") for v in m.group(1).split(",") if v.strip()]


def check_contract_drift(ctx: AuditContext, data: dict | None) -> None:
    """逐条验证契约声明的机制在现实中存在（D1/D2/D3 的机检投影）。

    设计口径：**不检查「文档写得好不好」，只检查「契约说存在的通道，现实里能不能指到」**。
    """
    check = "contract_drift"
    path = ctx.agents_path
    if not path.is_file():
        ctx.add(check, INFO, f"未找到 {ctx.rel(path)}，契约漂移检查跳过", f"missing file: {ctx.rel(path)}")
        return
    try:
        payload = json.loads(_read_text(path))
    except (OSError, json.JSONDecodeError) as exc:
        ctx.add(check, FAIL, f"角色能力目录无法解析，无法核对契约：{exc}", f"{ctx.rel(path)}")
        return

    problems = 0

    # ---- D1：event_stream 声明了 enabled，路径就必须真实存在 ----
    stream = payload.get("event_stream") or {}
    if isinstance(stream, dict) and stream.get("status") == "enabled":
        stream_path = stream.get("path")
        if not stream_path:
            problems += 1
            ctx.add(check, FAIL, "event_stream.status=enabled 但未声明 path（契约不可验证）",
                    f"{ctx.rel(path)}:event_stream.path")
        elif not (ctx.repo / str(stream_path)).exists():
            problems += 1
            ctx.add(check, FAIL,
                    f"event_stream 声明 enabled+path={stream_path}，但该文件不存在（D1/D2：契约无现实）",
                    f"{ctx.rel(path)}:event_stream.path")

    # ---- D2：契约里的字段/阶段枚举必须与写入器常量一致（双源一致性） ----
    script = ctx.dispatch_script
    if script.is_file():
        src = _read_text(script)
        actual_phases = _parse_py_const_list(src, "PHASES")
        actual_required = _parse_py_const_list(src, "REQUIRED_FIELDS")
        for label, claimed, actual in (
            ("phases", stream.get("phases"), actual_phases),
            ("required_fields", stream.get("required_fields"), actual_required),
        ):
            if not isinstance(claimed, list) or actual is None:
                continue
            if [str(x) for x in claimed] != actual:
                problems += 1
                ctx.add(check, FAIL,
                        f"契约 event_stream.{label} 与写入器常量不一致（双源漂移）："
                        f"agents.json={claimed} vs dispatch_log.py={actual}",
                        f"{ctx.rel(path)}:event_stream.{label} vs {ctx.rel(script)}:{label.upper()}")

    # ---- D3：角色 status 合法 + trigger_channel 证据路径可指到 ----
    snapshot_members = {
        str(m.get("target")) for m in ((data or {}).get("members") or []) if isinstance(m, dict)
    }
    agents = [a for a in (payload.get("agents") or []) if isinstance(a, dict)]
    for agent in agents:
        aid = str(agent.get("id") or "?")
        status = agent.get("status")
        if status not in VALID_ROLE_STATUS:
            problems += 1
            ctx.add(check, FAIL,
                    f"角色 `{aid}` 的 status={status!r} 不在合法集合 {list(VALID_ROLE_STATUS)} 内"
                    f"（活性判定会静默失效）",
                    f"{ctx.rel(path)}:agents[{aid}].status")
        channel = agent.get("trigger_channel") or {}
        ctype = str(channel.get("type") or "")
        if ctype and ctype not in VALID_TRIGGER_TYPES:
            problems += 1
            ctx.add(check, WARN,
                    f"角色 `{aid}` 的 trigger_channel.type={ctype!r} 不在已知真实通道集合内"
                    f"（疑似声明了不存在的触发机制）",
                    f"{ctx.rel(path)}:agents[{aid}].trigger_channel.type")
        for token in extract_path_tokens(str(channel.get("evidence") or "")):
            if not (ctx.repo / token).exists():
                problems += 1
                ctx.add(check, WARN,
                        f"角色 `{aid}` 的触发通道证据路径不存在（契约无现实）：{token}",
                        f"{ctx.rel(path)}:agents[{aid}].trigger_channel.evidence")

    # ---- D4：active 角色 id 必须与 roster 成员或**已声明**别名对账 ----
    # 口径：声明即契约。别名必须显式写在 agents.json 的 roster_alias 里，且必须能在
    # roster 快照中命中；未声明的 id 分叉才是漂移（会导致 role_evidence 假报幽灵）。
    if snapshot_members:
        for agent in agents:
            if agent.get("status") != "active":
                continue
            aid = str(agent.get("id") or "?")
            aliases = [str(a) for a in (agent.get("roster_alias") or [])]
            if aid in snapshot_members:
                continue
            hit = [a for a in aliases if a in snapshot_members]
            if hit:
                continue  # 已声明的别名 → 契约与现实一致，不报
            problems += 1
            if aliases:
                ctx.add(check, FAIL,
                        f"active 角色 `{aid}` 声明的 roster_alias {aliases} 在 roster 快照里全部命中不到"
                        f"（别名本身是虚构的）",
                        f"{ctx.rel(path)}:agents[{aid}].roster_alias vs roster")
            else:
                ctx.add(check, FAIL,
                        f"active 角色 `{aid}` 既不在 roster 成员中、也未声明 roster_alias"
                        f"（声明的角色在现实名册里指不到人；依赖精确 id 的活性检查会假报「幽灵角色」）",
                        f"{ctx.rel(path)}:agents[{aid}].id vs roster")

    # ---- D5：AGENTS.md 若声明旧事件流「未落盘」，该文件就不该出现 ----
    legacy = ctx.repo / "artifacts/agent/events.jsonl"
    if legacy.exists():
        problems += 1
        ctx.add(check, WARN,
                "契约称旧事件流 events.jsonl「契约预留、未落盘」，但该文件已存在 ⇒ 契约与现实漂移，"
                "须裁决是启用还是删除",
                f"{ctx.rel(legacy)} vs {ctx.rel(ctx.agents_md_path)}")

    # ---- D6：dsn_roster_actions（Lead 待执行的花名册动作队列）不得残留 ----
    #   动作执行后必须从队列删除，否则「已退休的人」会以「待办理」形态永久挂在契约里
    #   （= 另一种静默：没人知道这动作做没做）。
    actions = payload.get("dsn_roster_actions") or {}
    if isinstance(actions, dict) and snapshot_members:
        for item in actions.get("retire_recommended") or []:
            tgt = str((item or {}).get("target") or "") if isinstance(item, dict) else ""
            if not tgt:
                problems += 1
                ctx.add(check, FAIL, "dsn_roster_actions.retire_recommended 有条目缺 target",
                        f"{ctx.rel(path)}:dsn_roster_actions.retire_recommended")
                continue
            if tgt not in snapshot_members:
                problems += 1
                ctx.add(check, WARN,
                        f"待执行退役动作 `{tgt}` 已不在 roster 快照中 ⇒ 该动作已执行（或名字不存在），"
                        f"应从 dsn_roster_actions 删除（残留会让人以为还没办）",
                        f"{ctx.rel(path)}:dsn_roster_actions.retire_recommended[{tgt}]")
        for tgt in actions.get("keep_standby") or []:
            tgt = str(tgt)
            if tgt not in snapshot_members:
                problems += 1
                ctx.add(check, WARN,
                        f"dsn_roster_actions.keep_standby 里的 `{tgt}` 不在 roster 快照中"
                        f"（保留名单与现实名册不一致）",
                        f"{ctx.rel(path)}:dsn_roster_actions.keep_standby")

    if problems == 0:
        ctx.add(check, INFO,
                f"契约 {len(agents)} 个角色的声明机制均能在磁盘指到现实（event_stream/通道/名册对账一致）",
                f"{ctx.rel(path)} + {ctx.rel(ctx.dispatch_script)}")


# ---------------------------------------------------------------------------
# 9. 提交卫生：自修链 / 热点 / 不变量缺位（Q3）
# ---------------------------------------------------------------------------
_SELF_FIX_RE = re.compile(
    r"修复.{0,16}引入|我引入|被我.{0,8}(破坏|覆盖|回退)|回退了|覆盖静默回退|"
    r"提交说明.{0,10}不符|与.{0,6}代码不符|重大更正|事故："
)
_TEST_HINT = ("tests/", "scripts/benchmark/", "scripts/", "test_", "_test.", "probe", "selftest")


def _git(repo: Path, *args: str) -> str:
    """执行 git 命令并返回 stdout；失败返回空串（非 git 仓库不报错）。"""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout if out.returncode == 0 else ""


def check_dispatch_release(ctx: AuditContext, data: dict | None) -> None:
    """第 11 类：派发与发布不变量（2026-10-24 新增）。

    对应 `AGENTS.md §0.5` 的 L1/L5 与 `docs/guides/lead-dispatch-rules.md` §4。
    设计口径：**只检查"能机器验证"的部分**，不检查"Lead 有没有读规范"。

    H1 `version_triad`    —— 版本三查：__version__.py == version.md §1 == Package/VERSION
    H2 `tag_version`      —— 最新 tag 与版本文件一致；已 bump 未打 tag ⇒ WARN（发版未完成）
    H3 `ephemeral_cleanup`—— agents.json 的 ephemeral 名单不得残留已退役成员

    三条都来自 2026-10-24 的真实事故：
      H1：DOC03 版本漂移（version.md 写 0.4.6 而 __version__.py 仍 0.4.5）
      H2：本地 tag v0.4.6 指向非发布 commit 且从未推送 ⇒ 差点做出多余且不可逆的"删 tag 重建"
      H3：退役 p0-selection / boot-probe 后 ephemeral 名单残留 ⇒ 需人工清
    """
    import re as _re
    import subprocess

    check = "dispatch_release"

    # ── H1 版本三查 ────────────────────────────────────────────────
    ver_py = ctx.repo / "src" / "memoria" / "__version__.py"
    code_ver = ""
    if ver_py.exists():
        m = _re.search(r'__version__\s*=\s*["\']([0-9][^"\']*)["\']',
                       ver_py.read_text(encoding="utf-8", errors="replace"))
        code_ver = m.group(1) if m else ""

    doc_ver = ""
    doc_path = ctx.repo / "docs" / "conventions" / "version.md"
    if doc_path.exists():
        m = _re.search(r"\|\s*当前版本\s*\|\s*\**v?([0-9][0-9.]*)\**", 
                       doc_path.read_text(encoding="utf-8", errors="replace"))
        doc_ver = m.group(1) if m else ""

    pkg_file = ctx.repo / "Package" / "VERSION"
    pkg_ver = ""
    if pkg_file.exists():
        pkg_ver = pkg_file.read_text(encoding="utf-8", errors="replace").strip()

    if code_ver and doc_ver and code_ver != doc_ver:
        ctx.add(check, FAIL,
                f"H1 版本漂移：__version__.py={code_ver} 但 version.md §1={doc_ver}（DOC03 同族）",
                f"{ctx.rel(ver_py)} vs {ctx.rel(doc_path)}")
    if code_ver and pkg_ver and code_ver != pkg_ver:
        ctx.add(check, FAIL,
                f"H1 打包产物版本不符：Package\\VERSION={pkg_ver} 但 __version__.py={code_ver}"
                f"（需重新 build_release）",
                f"{ctx.rel(pkg_file)} vs {ctx.rel(ver_py)}")
    if ver_py.exists() and not code_ver:
        # 文件在但解析不出 ⇒ 真问题；文件本身不存在（如 fixture/临时仓库）⇒ 静默跳过
        ctx.add(check, WARN, "H1 无法解析 __version__.py 的版本号", ctx.rel(ver_py))

    # ── H2 最新 tag ↔ 版本文件 ─────────────────────────────────────
    def _git(*args: str) -> str:
        try:
            r = subprocess.run(["git", *args], cwd=str(ctx.repo), capture_output=True,
                               text=True, encoding="utf-8", timeout=20)
            return (r.stdout or "").strip() if r.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            return ""

    latest_tag = _git("tag", "--sort=-creatordate")
    latest_tag = latest_tag.split("\n")[0].strip() if latest_tag else ""
    latest_tag = latest_tag[1:] if latest_tag.startswith("v") else latest_tag

    if code_ver and latest_tag and code_ver != latest_tag:
        # 版本文件比 tag 新 ⇒ 已 bump 未发版（WARN，不是错误：可能在准备中）
        try:
            newer = tuple(int(x) for x in code_ver.split(".")) > tuple(int(x) for x in latest_tag.split("."))
        except ValueError:
            newer = False
        if newer:
            ctx.add(check, WARN,
                    f"H2 版本文件 {code_ver} 领先最新 tag v{latest_tag} —— 已 bump 但未发版（发版未完成）",
                    f"{ctx.rel(ver_py)} vs git tag")
        else:
            ctx.add(check, FAIL,
                    f"H2 版本文件 {code_ver} 落后于最新 tag v{latest_tag} —— tag 与代码不一致",
                    f"{ctx.rel(ver_py)} vs git tag")

    # tag 指向的 commit 必须是发布 commit（即 tag 不得指向与版本文件不符的历史）
    if code_ver and latest_tag:
        tag_commit = _git("rev-list", "-n", "1", f"v{latest_tag}")
        head = _git("rev-parse", "HEAD")
        if tag_commit and head and tag_commit != head:
            unpushed = _git("log", "--oneline", f"v{latest_tag}..HEAD")
            n = len([ln for ln in unpushed.split("\n") if ln.strip()]) if unpushed else 0
            if n > 0:
                ctx.add(check, INFO,
                        f"H2 tag v{latest_tag} 之后还有 {n} 个 commit（tag 指向 {tag_commit[:8]}）",
                        "git tag / HEAD")

    # ── H3 ephemeral 名单残留 ─────────────────────────────────────
    reg_path = ctx.repo / "team" / "agents.json"
    if reg_path.exists():
        try:
            import json as _json

            reg = _json.loads(reg_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            reg = {}
        eph = [e.get("id") for e in (reg.get("ephemeral_agents") or []) if isinstance(e, dict)]
        members = set()
        if data:
            for m in (data.get("members") or []):
                if isinstance(m, dict) and m.get("target"):
                    members.add(m["target"])
        if eph and members:
            stale = [e for e in eph if e not in members]
            if stale:
                ctx.add(check, FAIL,
                        "H3 ephemeral 名单残留（成员已退役/不在快照中）：" + ", ".join(stale)
                        + " —— 收口时必须从 ephemeral_agents 删除",
                        f"{ctx.rel(reg_path)}:ephemeral_agents vs snapshot:members")
            live = [e for e in eph if e in members]
            if live:
                ctx.add(check, INFO,
                        "H3 活跃 ephemeral：" + ", ".join(live) + "（任务完成即退役）",
                        f"{ctx.rel(reg_path)}:ephemeral_agents")


def check_lessons(ctx: AuditContext) -> None:
    """检查「教训库」是否存在且未过久未更新（组织学习能力的机检投影）。

    设计口径（2026-10-24 自省）：团队反复踩同一类坑（假绿/假红/修了等于没修），
    每次都由 Lead 重新发现 —— 说明**教训没有沉淀机制**。
    `docs/guides/agent-team-lessons.md` 是沉淀载体；本检查只保证：
    ① 文件存在 ② 未被清空 ③ 不是几个月没动（提醒 Curator 复盘）。

    阈值取 21 天：一轮迭代通常 1–2 周，超过三周未更新说明复盘停摆。
    """
    check = "lessons_stale"
    path = ctx.repo / "docs" / "guides" / "agent-team-lessons.md"
    if not path.exists():
        ctx.add(check, FAIL,
                "教训库不存在（docs/guides/agent-team-lessons.md）—— 组织缺学习载体",
                ctx.rel(path))
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        ctx.add(check, WARN, f"教训库读取失败：{e}", ctx.rel(path))
        return
    # 排除 BOM 与空白后计数
    body = text.lstrip("\ufeff").strip()
    if len(body) < 1500:
        ctx.add(check, WARN,
                f"教训库内容过短（{len(body)} 字符 < 1500）—— 可能被清空或未真正沉淀",
                ctx.rel(path))
        return
    # 条目数（以 "### L" 开头的判据条目计）
    entries = sum(1 for ln in body.splitlines() if ln.startswith("### L"))
    try:
        import subprocess

        out = subprocess.run(
            ["git", "log", "-1", "--format=%ct", "--", str(path.relative_to(ctx.repo))],
            cwd=str(ctx.repo), capture_output=True, text=True, encoding="utf-8", timeout=15,
        )
        ts = int((out.stdout or "0").strip() or 0)
    except (OSError, ValueError, subprocess.SubprocessError):
        ts = 0
    if ts <= 0:
        ctx.add(check, INFO,
                f"教训库未入 git 历史（{entries} 条判据）—— 首版时正常，提交后转为日期检查",
                ctx.rel(path))
        return
    import time as _time

    age_days = (_time.time() - ts) / 86400.0
    if age_days > 21:
        ctx.add(check, INFO,
                f"教训库已 {age_days:.0f} 天未更新（{entries} 条判据）—— 建议 Curator 复盘后追加",
                ctx.rel(path))
    else:
        ctx.add(check, INFO,
                f"教训库健康：{entries} 条判据，{age_days:.1f} 天前更新",
                ctx.rel(path))


def check_commit_hygiene(ctx: AuditContext) -> None:
    """扫 git 历史找「自修链 / 同一文件同日反复 / 新特性无测试」三类信号。

    这是 Q3 的机检入口：**把「Lead 自己修自己」从偶然发现变成每轮必列**。
    只读 git log，不改仓库；非 git 仓库/无 git 时静默跳过。
    """
    check = "commit_hygiene"
    days = max(1, int(ctx.commit_window_days))
    log_out = _git(ctx.repo, "log", f"--since={days} days ago",
                   "--name-only", "--format=@@%H|%ad|%s", "--date=format:%Y-%m-%d")
    if not log_out.strip():
        ctx.add(check, INFO,
                f"近 {days} 天无 git 历史可扫（非 git 仓库或无提交），提交卫生检查跳过",
                f"git -C {ctx.repo} log --since='{days} days ago'")
        return

    commits: list[dict] = []
    cur: dict | None = None
    for line in log_out.splitlines():
        if line.startswith("@@"):
            payload = line[2:].split("|", 2)
            cur = {"sha": payload[0], "day": payload[1] if len(payload) > 1 else "?",
                   "subject": payload[2] if len(payload) > 2 else "", "files": []}
            commits.append(cur)
        elif line.strip() and cur is not None:
            cur["files"].append(line.strip())

    problems = 0

    # ---- H1：提交说明自认「修复此前引入 / 回退了 / 说明与代码不符」 ----
    self_fix = [c for c in commits if _SELF_FIX_RE.search(c["subject"])]
    if self_fix:
        problems += 1
        examples = "; ".join(f"{c['sha'][:8]}({c['day']})" for c in self_fix[:5])
        ctx.add(check, WARN,
                f"近 {days} 天有 {len(self_fix)} 个提交自认是「自修/回退/说明与代码不符」"
                f"⇒ 前一版在提交时未被发现有问题（Q3 自修链）：{examples}"
                + ("…" if len(self_fix) > 5 else ""),
                f"git -C . log --since='{days} days ago' --format=%h%x09%s | 正则 {_SELF_FIX_RE.pattern[:40]}…")

    # ---- H2：同一文件同一天被改 ≥3 次（仅 src/**，未收敛热点） ----
    hotspot: dict[tuple[str, str], list[str]] = {}
    for c in commits:
        for f in c["files"]:
            if not f.startswith("src/"):
                continue
            hotspot.setdefault((c["day"], f), []).append(c["sha"])
    hot = {k: v for k, v in hotspot.items() if len(v) >= HOTSPOT_MIN_COMMITS}
    if hot:
        problems += 1
        top = sorted(hot.items(), key=lambda kv: len(kv[1]), reverse=True)[:5]
        detail = "; ".join(f"{k[1]} @{k[0]} ✕{len(v)}" for k, v in top)
        ctx.add(check, WARN,
                f"近 {days} 天有 {len(hot)} 个 «文件×日» 组合被改 ≥{HOTSPOT_MIN_COMMITS} 次"
                f"（未收敛信号，非缺陷本身）：{detail}",
                f"git -C . log --since='{days} days ago' --name-only --format=@@%ad --date=format:%Y-%m-%d")

    # ---- H3：feat 改 src/** 但同 commit 未附任何测试/探针（不变量缺位） ----
    bare_feat = []
    for c in commits:
        if not c["subject"].startswith("feat("):
            continue
        files = c["files"]
        if not any(f.startswith("src/") for f in files):
            continue
        if any(any(hint in f for hint in _TEST_HINT) for f in files):
            continue
        bare_feat.append(c)
    if bare_feat:
        problems += 1
        examples = "; ".join(f"{c['sha'][:8]}({c['day']})" for c in bare_feat[:5])
        ctx.add(check, WARN,
                f"近 {days} 天有 {len(bare_feat)} 个 `feat(` 提交改了 src/** 却未在同一提交内附"
                f"测试/探针（该特性的不变量缺位，门禁无法验它）：{examples}"
                + ("…" if len(bare_feat) > 5 else ""),
                f"git -C . log --since='{days} days ago' --name-only --format=@@%H|%ad|%s")

    if problems == 0:
        ctx.add(check, INFO,
                f"近 {days} 天 {len(commits)} 个提交：无自修链、无 src 热点、feat 均附不变量检查",
                f"git -C . log --since='{days} days ago'")


# ---------------------------------------------------------------------------
# 10. task-100 新增四类检查（rule_ref 均已在现行规范内：L8 / org §2.3 / lessons L0.3 / L9）
# ---------------------------------------------------------------------------
def _git_raw(repo: Path, *args: str) -> str:
    """执行 git 并返回 stdout；失败返回空串。`core.quotepath=false` 防中文路径转义。"""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "-c", "core.quotepath=false", *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout if out.returncode == 0 else ""


def _is_git_repo(repo: Path) -> bool:
    return bool(_git(repo, "rev-parse", "--git-dir").strip())


def _git_commits_with_paths(repo: Path, days: int) -> list[dict] | None:
    """窗口内提交 [{sha, ts, subject, paths}]；非 git 仓库返回 None（调用方必须显式跳过）。"""
    if not _is_git_repo(repo):
        return None
    raw = _git_raw(repo, "log", "--all", f"--since={days} days ago",
                   "--format=@@%H%x1f%aI%x1f%s", "--name-only")
    commits: list[dict] = []
    current: dict | None = None
    for line in raw.splitlines():
        if line.startswith("@@"):
            parts = line[2:].split("\x1f")
            if len(parts) < 3:
                current = None
                continue
            current = {"sha": parts[0], "ts": _parse_iso(parts[1]), "subject": parts[2], "paths": []}
            commits.append(current)
        elif line.strip() and current is not None:
            current["paths"].append(line.strip())
    return commits


def _fmt_dt(moment) -> str:
    if not isinstance(moment, datetime):
        return "?"
    return moment.astimezone().strftime("%m-%d %H:%M")


def check_plan_consulted(ctx: AuditContext) -> None:
    """版本级规划是否先于实施（AGENTS.md §0.5 L8）。

    判据（设计稿 §5.2-①）：对窗口内出现的版本号 V，
      t_impl = 最早「提交信息含 V 且改动含 src/ 或 scripts/ 且不含 docs/」的提交时间；
      t_plan = 最早「改动 docs/todo.md 且 diff 中出现 V」的提交时间；
      t_impl 存在且（t_plan 不存在 或 t_plan > t_impl）⇒ WARN（首月宽限，之后 FAIL）。
    """
    check = "plan_consulted"
    commits = _git_commits_with_paths(ctx.repo, PLAN_WINDOW_DAYS)
    if commits is None:
        ctx.add(check, INFO,
                "非 git 仓库（或 git 不可用），plan_consulted 跳过（本检查必须依赖 git 历史）",
                f"git -C {ctx.rel(ctx.repo)} rev-parse --git-dir")
        return
    if not commits:
        ctx.add(check, WARN,
                f"近 {PLAN_WINDOW_DAYS} 天无提交：plan_consulted 输入为 0（**不得视为通过**；"
                f"若这是窗口配置错误需修）",
                f"git log --since='{PLAN_WINDOW_DAYS} days ago'")
        return

    version_path = ctx.repo / DEFAULT_VERSION_FILE
    current = ""
    if version_path.is_file():
        match = _VERSION_RE.search(_read_text(version_path))
        current = match.group(0) if match else ""
    family = ".".join(current.split(".")[:2]) + "." if current else None

    all_versions = sorted({v for c in commits for v in _VERSION_RE.findall(c["subject"])})
    versions_in_family = [v for v in all_versions if family and v.startswith(family)]
    if all_versions and not versions_in_family:
        ctx.add(check, FAIL,
                f"窗口内提交出现版本号 {all_versions[:6]}，但按当前版本家族 {family} 过滤后为 0 —— "
                f"版本/家族解析失效（输入为 0 不得判绿）",
                f"{ctx.rel(version_path)} + git log 提交信息")
        return
    if not versions_in_family:
        ctx.add(check, INFO,
                f"近 {PLAN_WINDOW_DAYS} 天 {len(commits)} 个提交中未出现版本级工作（checked_count=0，不适用）",
                f"git log --since='{PLAN_WINDOW_DAYS} days ago'")
        return

    checked = 0
    problems = 0
    for version in versions_in_family:
        impl = [
            c for c in commits
            if version in c["subject"]
            and any(p.startswith(("src/", "scripts/")) for p in c["paths"])
            and not any(p.startswith("docs/") for p in c["paths"])
        ]
        impl = [c for c in impl if c["ts"] is not None]
        if not impl:
            continue
        checked += 1
        first_impl = min(impl, key=lambda c: c["ts"])
        plan_raw = _git_raw(ctx.repo, "log", "--all", f"-S{version}", "--format=%aI", "--", TODO_DOC)
        plan_times = [t for t in (_parse_iso(x) for x in plan_raw.splitlines() if x.strip()) if t]
        first_plan = min(plan_times) if plan_times else None
        if first_plan is None or first_plan > first_impl["ts"]:
            problems += 1
            plan_text = f"{_fmt_dt(first_plan)}（{TODO_DOC}）" if first_plan else f"未找到（{TODO_DOC} 无该版本落盘）"
            ctx.add(check, WARN,
                    f"版本 {version} 的实施提交 {first_impl['sha'][:8]}（{_fmt_dt(first_impl['ts'])}）"
                    f"早于台账计划落盘 {plan_text} —— 违反 AGENTS.md §0.5 L8"
                    f"（版本级规划须先由 todo-owner 产出并写进 {TODO_DOC}；首月 WARN，之后 FAIL；"
                    f"checked_count={checked}）",
                    f"git:{first_impl['sha']} vs {TODO_DOC} -S'{version}'")
    if problems == 0:
        ctx.add(check, INFO,
                f"近 {PLAN_WINDOW_DAYS} 天 {checked} 个版本"
                f"（{', '.join(versions_in_family)}）的实施提交均不早于台账计划（checked_count={checked}）",
                f"git log --since='{PLAN_WINDOW_DAYS} days ago' + {TODO_DOC} -S")


def check_role_registration(ctx: AuditContext, data: dict | None) -> None:
    """角色注册三方全等 + 快照晚于注册修改（org.md §2.3 执行纪律 1）。

    三方：A = agents.json 中 status∈{active,standby} 的 id（roster_alias 展开，lead 除外）；
          B = org.md §2 + §2.2 解析出的 owner id；C = 快照 members（lead 除外）。
    判据：A == B == C；且 snapshot.exportedAt 必须晚于 agents.json / org.md 的 mtime（否则 WARN）。
    """
    check = "role_registration"
    sources = 0
    if not ctx.agents_path.is_file():
        ctx.add(check, FAIL, f"输入不足：{ctx.rel(ctx.agents_path)} 不存在，三方一致性无法验证（输入为 0 不得判绿）",
                f"missing file: {ctx.rel(ctx.agents_path)}")
        return
    try:
        payload = json.loads(_read_text(ctx.agents_path))
    except (OSError, json.JSONDecodeError) as exc:
        ctx.add(check, FAIL, f"输入不足：{ctx.rel(ctx.agents_path)} 无法解析（{exc}）",
                f"{ctx.rel(ctx.agents_path)}")
        return
    sources += 1

    if not ctx.org_path.is_file():
        ctx.add(check, FAIL, f"输入不足：{ctx.rel(ctx.org_path)} 不存在，三方一致性无法验证",
                f"missing file: {ctx.rel(ctx.org_path)}")
        return
    org_text = _read_text(ctx.org_path)
    parsed_org = parse_org_owners(org_text)
    if not (parsed_org["owners"] or parsed_org["resident"]):
        ctx.add(check, FAIL,
                f"输入不足：{ctx.rel(ctx.org_path)} §2/§2.2 未解析出任何 Owner（名册解析失效，输入为 0 不得判绿）",
                f"{ctx.rel(ctx.org_path)}:§2")
        return
    sources += 1

    if data is None:
        ctx.add(check, FAIL, "输入不足：任务板快照不可用，三方一致性无法验证",
                f"{ctx.rel(ctx.snapshot_path)}")
        return
    sources += 1

    org_targets = {str(item["target"]) for item in parsed_org["owners"] + parsed_org["resident"]}
    members = [m for m in (data.get("members") or []) if isinstance(m, dict)]
    member_targets = {str(m.get("target")) for m in members if m.get("target")}
    lead_targets = {
        str(m.get("target")) for m in members
        if m.get("role") == "lead" or str(m.get("target")) == "lead"
    }
    snapshot_targets = member_targets - lead_targets

    agent_targets: set[str] = set()
    for agent in (payload.get("agents") or []):
        if not isinstance(agent, dict) or agent.get("status") not in ("active", "standby"):
            continue
        aid = str(agent.get("id") or "")
        # lead 是 DSH 会话身份（scope=dsn-session），不进 org §2 名册计数，故三方比对一律排除
        if not aid or aid == "lead" or agent.get("scope") == "dsn-session":
            continue
        aliases = [str(a) for a in (agent.get("roster_alias") or [])]
        if aid in member_targets:
            agent_targets.add(aid)
        elif aliases:
            hit = next((a for a in aliases if a in member_targets), None)
            agent_targets.add(hit or aid)
        else:
            agent_targets.add(aid)

    if not (agent_targets or org_targets or snapshot_targets):
        ctx.add(check, FAIL, "输入不足：三方解析结果均为空（注册表/名册/快照同时失效？），输入为 0 不得判绿",
                f"{ctx.rel(ctx.agents_path)} + {ctx.rel(ctx.org_path)} + {ctx.rel(ctx.snapshot_path)}:members")
        return

    checked = len(agent_targets) + len(org_targets) + len(snapshot_targets)
    problems = 0
    diffs = [
        ("agents.json 有 / org.md 无", agent_targets - org_targets,
         f"{ctx.rel(ctx.agents_path)}:agents[].id vs {ctx.rel(ctx.org_path)}:§2+§2.2"),
        ("org.md 有 / agents.json 无", org_targets - agent_targets,
         f"{ctx.rel(ctx.org_path)}:§2+§2.2 vs {ctx.rel(ctx.agents_path)}:agents[].id"),
        ("agents.json 有 / 快照无", agent_targets - snapshot_targets,
         f"{ctx.rel(ctx.agents_path)}:agents[].id vs {ctx.rel(ctx.snapshot_path)}:members"),
        ("快照有 / agents.json 无", snapshot_targets - agent_targets,
         f"{ctx.rel(ctx.snapshot_path)}:members vs {ctx.rel(ctx.agents_path)}:agents[].id"),
        ("org.md 有 / 快照无", org_targets - snapshot_targets,
         f"{ctx.rel(ctx.org_path)}:§2+§2.2 vs {ctx.rel(ctx.snapshot_path)}:members"),
        ("快照有 / org.md 无", snapshot_targets - org_targets,
         f"{ctx.rel(ctx.snapshot_path)}:members vs {ctx.rel(ctx.org_path)}:§2+§2.2"),
    ]
    for label, diff, evidence in diffs:
        if not diff:
            continue
        problems += 1
        ctx.add(check, FAIL,
                f"角色注册三方不一致（{label}）：{sorted(diff)} —— 违反 org.md §2.3 执行纪律 1"
                f"（注册新角色 = 改 3 处 [agents.json / org.md §2.2 / 快照] 并在同一轮重导出快照；"
                f"id 与 roster 名不一致须显式写 roster_alias；checked_count={checked}）",
                evidence)

    exported = _parse_iso(data.get("exportedAt"))
    if exported is None:
        problems += 1
        ctx.add(check, FAIL, f"快照 exportedAt={data.get('exportedAt')!r} 不可解析，无法验证「快照晚于注册修改」",
                f"{ctx.rel(ctx.snapshot_path)}:exportedAt")
    else:
        for label, path in (("agents.json", ctx.agents_path), ("org.md", ctx.org_path)):
            if not path.is_file():
                continue
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if exported.astimezone(timezone.utc) < mtime - timedelta(seconds=30):
                problems += 1
                ctx.add(check, WARN,
                        f"快照 exportedAt={data.get('exportedAt')} 早于 {label} mtime={mtime.isoformat()} "
                        f"⇒ 快照不可能反映注册修改，须重导出快照后再审计（checked_count={checked}）",
                        f"{ctx.rel(ctx.snapshot_path)}:exportedAt vs {ctx.rel(path)} mtime")

    if problems == 0:
        ctx.add(check, INFO,
                f"角色注册三方一致：agents.json {len(agent_targets)} / org.md {len(org_targets)} / "
                f"快照 {len(snapshot_targets)} 个 id，且快照晚于注册修改（checked_count={checked}）",
                f"{ctx.rel(ctx.agents_path)} + {ctx.rel(ctx.org_path)} + {ctx.rel(ctx.snapshot_path)}:members")
    _ = sources  # 保留计数语义：三方任一不可用已在上方提前 return


def check_dead_path_edit(ctx: AuditContext) -> None:
    """改了无引用文件（agent-team-lessons.md L0.3：测试必须走被测路径）。

    判据：近 N 天改动的 src/**、scripts/** 文件（排除 tests/），若全仓
    `git grep -l <basename>` 找不到任何引用（含文档引用）且文件头 5 行无 `@entry` 标记 ⇒ WARN。
    白名单来自仓内实测（`@entry` 标记），不维护文档里的手工名单（防白名单过期变假绿/假红）。
    """
    check = "dead_path_edit"
    commits = _git_commits_with_paths(ctx.repo, DEAD_PATH_WINDOW_DAYS)
    if commits is None:
        ctx.add(check, INFO, "非 git 仓库（或 git 不可用），dead_path_edit 跳过（本检查必须依赖 git 历史）",
                f"git -C {ctx.rel(ctx.repo)} rev-parse --git-dir")
        return
    if not commits:
        ctx.add(check, WARN,
                f"近 {DEAD_PATH_WINDOW_DAYS} 天无提交：dead_path_edit 输入为 0（**不得视为通过**）",
                f"git log --since='{DEAD_PATH_WINDOW_DAYS} days ago'")
        return

    changed: list[str] = []
    for commit in commits:
        for path in commit["paths"]:
            if not path.startswith(("src/", "scripts/")):
                continue
            if "/tests/" in path or path.startswith("tests/"):
                continue
            if not path.endswith(DEAD_PATH_EXTS):
                continue
            if path not in changed:
                changed.append(path)
    if not changed:
        ctx.add(check, FAIL,
                f"近 {DEAD_PATH_WINDOW_DAYS} 天有 {len(commits)} 个提交，但未解析出任何 src/scripts 代码改动 —— "
                f"解析失效（输入为 0 不得判绿）",
                "git log --since=... --name-only")
        return

    # 性能：一次 git grep 批量搜全部 basename（逐文件调用会把机检拖到 60s+）；
    # 匹配行里必然含命中的 basename，故用整行子串反查即可。
    checkable: list[str] = []
    entry_whitelisted: list[str] = []
    deleted = 0
    for path in changed:
        target = ctx.repo / path
        if not target.is_file():
            deleted += 1  # 已删除文件不判（删除本身属 risk 清单，不在这里重复报）
            continue
        try:
            head_text = "\n".join(_read_text(target).splitlines()[:5])
        except OSError:
            continue
        if ENTRY_MARKER_RE.search(head_text):
            entry_whitelisted.append(path)
            continue
        checkable.append(path)
    checkable = checkable[:MAX_DEAD_PATH_FILES]
    if not checkable:
        ctx.add(check, FAIL,
                f"近 {DEAD_PATH_WINDOW_DAYS} 天有 {len(commits)} 个提交、解析出 {len(changed)} 个候选文件，"
                f"但全部不可检查（已删除 {deleted} / 入口白名单 {len(entry_whitelisted)}）—— 输入为 0 不得判绿",
                "git log --since=... --name-only")
        return

    basenames = sorted({path.rsplit("/", 1)[-1] for path in checkable})
    owners: dict[str, set[str]] = {}
    for path in checkable:
        owners.setdefault(path.rsplit("/", 1)[-1], set()).add(path)
    grep_args = ["grep", "-n", "-I", "-F"]
    for name in basenames:
        grep_args += ["-e", name]
    grep_out = _git_raw(ctx.repo, *grep_args, "HEAD")
    referenced: set[str] = set()
    for line in grep_out.splitlines():
        # 格式：HEAD:<repo-relative-path>:<lineno>:<content>
        if not line.startswith("HEAD:"):
            continue
        parts = line[5:].split(":", 2)
        if len(parts) < 3:
            continue
        match_path, _lineno, content = parts
        for name in basenames:
            if name in content and match_path not in owners.get(name, set()):
                # 排除「文件自己提到自己」（usage 文案/自述）——那不是外部入口引用
                referenced.add(name)
    orphans = [path for path in checkable if path.rsplit("/", 1)[-1] not in referenced]
    checked = len(checkable)

    if orphans:
        examples = "; ".join(orphans[:12]) + ("…" if len(orphans) > 12 else "")
        ctx.add(check, WARN,
                f"近 {DEAD_PATH_WINDOW_DAYS} 天改了 {len(orphans)} 个「全仓无引用」文件"
                f"（checked_count={checked}，扫描 {len(basenames)} 个 basename，一次批量 git grep）："
                f"{examples} —— 先确认它们在**生产/测试路径**上再改"
                f"（lessons L0.3；对照：改了 p5perf_workload2.mjs 才发现它无入口）",
                "git grep -n -I -F -e <basename>... HEAD")
    else:
        ctx.add(check, INFO,
                f"近 {DEAD_PATH_WINDOW_DAYS} 天改动的 {checked} 个 src/scripts 文件均能在仓内找到至少一处引用"
                f"（或文件头带 @entry 入口标记 {len(entry_whitelisted)} 个；checked_count={checked}）",
                "git grep -n -I -F -e <basename>... HEAD")


def check_mode_policy(ctx: AuditContext) -> None:
    """spawn 是否显式做了模式决策（AGENTS.md §0.5 L9）。

    判据：扫 dispatch-log 的 phase=spawn 记录：
      - 无 `mode` 字段 / `modeExplicit=false` ⇒ WARN「静默默认 standard（等于没做决策）」；
      - mode 不在 DSH 四档 ⇒ WARN；
      - 整份日志都没有 mode 字段 ⇒ 显式报「无法判定 + checked_count」，**不静默判绿**（lessons L1.1）。
    dispatch-log 当前尚未记录 mode（已实测 12 条 spawn 全缺）——本检查先暴露这个缺口，
    等 Lead 在 dispatch_log.py 增加 --mode 后自动转为可判定。
    """
    check = "mode_policy"
    path = ctx.dispatch_path
    if not path.is_file():
        ctx.add(check, FAIL, f"输入不足：{ctx.rel(path)} 不存在，无法检查 spawn 模式决策",
                f"missing file: {ctx.rel(path)}")
        return
    rows = _read_dispatch_rows(path)
    spawns = [r for r in rows if isinstance(r, dict) and r.get("phase") == "spawn"]
    if not spawns:
        ctx.add(check, FAIL,
                f"输入不足：{ctx.rel(path)} 中没有任何 phase=spawn 记录（输入为 0 不得判绿）",
                f"{ctx.rel(path)}:phase=spawn")
        return

    since = datetime.now(timezone.utc) - timedelta(days=MODE_POLICY_WINDOW_DAYS)
    in_window = []
    for row in spawns:
        stamp = _parse_iso(str(row.get("ts") or ""))
        if stamp is None or stamp.astimezone(timezone.utc) >= since:
            in_window.append((row, stamp))
    if not in_window:
        ctx.add(check, WARN,
                f"近 {MODE_POLICY_WINDOW_DAYS} 天无 spawn 记录：mode_policy 输入为 0（**不得视为通过**）",
                f"{ctx.rel(path)}:phase=spawn")
        return

    checked = len(in_window)
    missing_mode = [(row, stamp) for row, stamp in in_window if not str(row.get("mode") or "").strip()]
    with_mode = [(row, stamp) for row, stamp in in_window if str(row.get("mode") or "").strip()]
    if not with_mode:
        ctx.add(check, WARN,
                f"{checked} 条 spawn 记录**全部缺 mode 字段**（dispatch-log 尚未记录模式）⇒ "
                f"无法判定是否做过模式决策，**不静默判绿**。修法：dispatch_log.py 增加 --mode 参数，"
                f"spawn 时记录 mode（L9：不传 mode = 静默默认 standard）"
                f"（checked_count={checked}，with_mode=0）",
                f"{ctx.rel(path)}:phase=spawn 无 mode 字段（字段实测：ts/actor/phase/target/task/desc/source）")
        return

    problems = 0
    missing_explicit = 0
    # 有 mode 的记录里，仍可能有另一部分记录完全没记 mode —— 必须一并暴露（否则又是一处假绿）
    if missing_mode:
        problems += 1
        targets = ", ".join(str(r.get("target")) for r, _ in missing_mode[:6])
        ctx.add(check, WARN,
                f"{len(missing_mode)}/{checked} 条 spawn 记录缺 mode 字段（{targets}）⇒ 无法判定是否做了"
                f"模式决策（静默默认 standard；checked_count={checked}）",
                f"{ctx.rel(path)}:phase=spawn 缺 mode")
    for row, _stamp in with_mode:
        mode = str(row.get("mode")).strip()
        explicit = row.get("modeExplicit")
        if explicit is False or (explicit is None and "modeExplicit" not in row):
            # 有 mode 但没有显式决策标记 ⇒ 仍可能是不传 mode 的静默默认（无法区分），必须报
            missing_explicit += 1
            ctx.add(check, WARN,
                    f"spawn `{row.get('target')}`（{_fmt_dt(_stamp)}，task={row.get('task') or '—'}）"
                    f"记录了 mode={mode} 但无 modeExplicit 标记 ⇒ 无法证明是**显式**决策"
                    f"（L9：不传 mode 会被静默默认为 standard）",
                    f"{ctx.rel(path)}:phase=spawn[{row.get('target')}].modeExplicit")
            problems += 1
        if mode not in VALID_MODES:
            ctx.add(check, WARN,
                    f"spawn `{row.get('target')}` 的 mode={mode!r} 不在 DSH 四档 {list(VALID_MODES)} 内",
                    f"{ctx.rel(path)}:phase=spawn[{row.get('target')}].mode")
            problems += 1
        desc = str(row.get("desc") or "")
        if mode in ("standard", "deep") and _MECHANICAL_DESC_RE.search(desc):
            ctx.add(check, WARN,
                    f"spawn `{row.get('target')}` 的任务描述偏只读/扫描类（「{desc[:40]}…」）却用了 mode={mode} "
                    f"⇒ 可能该用 mechanical（推理链 off；L9 路由表）",
                    f"{ctx.rel(path)}:phase=spawn[{row.get('target')}].desc vs mode")
            problems += 1

    if problems == 0:
        ctx.add(check, INFO,
                f"近 {MODE_POLICY_WINDOW_DAYS} 天 {checked} 条 spawn 记录中 {len(with_mode)} 条带 mode 且均显式"
                f"（{', '.join(sorted({str(r.get('mode')) for r, _ in with_mode}))}，checked_count={checked}）",
                f"{ctx.rel(path)}:phase=spawn")
    else:
        ctx.add(check, INFO,
                f"mode_policy 统计：checked_count={checked}，with_mode={len(with_mode)}，"
                f"缺显式标记={missing_explicit}",
                f"{ctx.rel(path)}:phase=spawn")


# ---------------------------------------------------------------------------
# 汇总/自测
# ---------------------------------------------------------------------------
def run_checks(ctx: AuditContext) -> list:
    data = check_snapshot(ctx)
    check_roster(ctx, data)
    check_stalls(ctx, data)
    check_write_scopes(ctx, data)
    check_task_reports(ctx, data)
    check_artifact_refs(ctx)
    check_role_evidence(ctx, data)
    check_silent_failure(ctx)
    check_contract_drift(ctx, data)
    check_commit_hygiene(ctx)
    check_lessons(ctx)
    check_dispatch_release(ctx, data)
    # task-100 新增四类（rule_ref：AGENTS.md §0.5 L8 / org.md §2.3 / lessons L0.3 / AGENTS.md §0.5 L9）
    check_plan_consulted(ctx)
    check_role_registration(ctx, data)
    check_dead_path_edit(ctx)
    check_mode_policy(ctx)
    ctx.findings.sort(key=lambda f: (_SEV_ORDER.get(f.severity, 9), f.check, f.message))
    return ctx.findings


def _emit(findings: list, as_json: bool) -> None:
    counts = {FAIL: 0, WARN: 0, INFO: 0}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    if as_json:
        print(json.dumps({
            "schema": "team-audit/v1",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "summary": {"findings": len(findings), **counts},
            "findings": [f.as_dict() for f in findings],
        }, ensure_ascii=False, indent=2))
        return
    for f in findings:
        print(f"[{f.severity}] {f.check}: {f.message}")
        print(f"        证据：{f.evidence}")
    print(f"\n汇总：FAIL={counts[FAIL]} WARN={counts[WARN]} INFO={counts[INFO]} "
          f"合计 {len(findings)} 条")
    if counts[FAIL] == 0:
        print("结论：机检全绿（FAIL=0）")
    else:
        print("结论：存在 FAIL，需 Lead 处置（见逐条 finding）")


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def selftest() -> int:
    """构造红/绿两套 fixture，证明脚本既会红也会绿。"""
    failures = []

    def expect(findings, check, severity, needle):
        for f in findings:
            if f.check == check and f.severity == severity and needle in f.message:
                return True
        failures.append(f"未报出预期 finding：{severity} {check} …{needle}")
        return False

    tmp = Path(tempfile.mkdtemp(prefix="team-audit-selftest-"))
    try:
        # ---------- 红 fixture ----------
        red = tmp / "red"
        _write(red / "docs/guides/agent-team-org.md", """# org

| 层 | 谁 | 生命周期 |
|---|---|---|
| **L1 常驻领域 Owner** | 3 个 teammate | 常驻 |

## 2. 常驻成员（当前 2 个）

| Agent | 领域 |
|---|---|
| `alpha` | 甲 |
| `ghost` | 乙 |

## 3. 其他
""")
        _write(red / "team/team-board-snapshot.json", json.dumps({
            "schema": "team-board-snapshot/v1",
            "exportedAt": "2026-10-20T21:00:00+08:00",
            "limit": {"maxMembers": 16, "currentMembers": 3},
            "members": [
                {"target": "lead", "role": "lead", "status": "running"},
                {"target": "alpha", "role": "teammate", "status": "inactive"},
                {"target": "beta", "role": "teammate", "status": "inactive"},
            ],
            "retired": [],
            "inactiveOwners": ["alpha", "beta"],
            "tasks": [
                {"id": "t-1", "status": "in_progress", "owner": "alpha",
                 "writeScopes": ["src/shared.js"]},
                {"id": "t-2", "status": "pending", "owner": "beta",
                 "writeScopes": ["src/shared.js", "docs/x.md"]},
                # 无 owner 且无 writeScopes ⇒ 必须报「无人认领」+「写域输入不全」
                {"id": "t-3", "status": "pending"},
            ],
        }, ensure_ascii=False, indent=2))
        _write(red / "artifacts/agent/verify/claim-report.md",
               "# 报告\n\n已落盘 `scripts/not-exist/missing.py`。\n")
        # 幽灵角色：声明 active，但 14 天内无 dispatch/任务/产物证据
        _write(red / "team/agents.json", json.dumps({
            "schema_version": 2,
            # 契约声明 enabled 但 path 不存在 ⇒ contract_drift 必须 FAIL
            "event_stream": {"status": "enabled", "path": "team/no-such-stream.jsonl",
                             "phases": ["spawn", "done"], "required_fields": ["ts"]},
            "agents": [
                {"id": "phantom", "status": "active", "evidence_path": ["artifacts/agent/void/**"]},
                {"id": "alpha", "status": "active", "evidence_path": ["artifacts/agent/verify/**"]},
                # 非法 status ⇒ 活性判定会静默失效
                {"id": "weird", "status": "alive"},
            ],
            # D6 反例：待执行动作指向 roster 里不存在的人 ⇒ 必须 WARN（动作已执行却未清队列）
            "dsn_roster_actions": {"retire_recommended": [{"target": "already-gone"}],
                                   "keep_standby": ["never-existed"]},
        }, ensure_ascii=False, indent=2))
        # 静默失败 5 条规则的红 fixture
        _write(red / "team/bound-report.md", "# 真实存在的产物\n")
        _write(red / "team/dispatch-log.jsonl", "\n".join([
            json.dumps({"ts": "2026-01-02T00:00:00+08:00", "actor": "lead", "phase": "done",
                        "target": "x", "task": "no-report"}, ensure_ascii=False),
            json.dumps({"ts": "2026-01-02T01:00:00+08:00", "actor": "lead", "phase": "done",
                        "target": "x", "report": "team/not-there.md"}, ensure_ascii=False),
            json.dumps({"ts": "2026-01-03T00:00:00+08:00", "actor": "lead", "phase": "done",
                        "target": "y", "report": "team/bound-report.md"}, ensure_ascii=False),
            json.dumps({"ts": "2026-01-01T00:00:00+08:00", "actor": "lead", "phase": "spawn",
                        "target": "orphan-x"}, ensure_ascii=False),
            # 更正协议的反例：声明更正到仍不存在的路径 ⇒ 必须仍然 FAIL（二次静默失败）
            json.dumps({"ts": "2026-01-04T00:00:00+08:00", "actor": "lead", "phase": "backfill",
                        "target": "x",
                        "corrects": {"line": 6, "field": "report",
                                     "new": "team/still-missing.md"}}, ensure_ascii=False),
            json.dumps({"ts": "2026-01-05T00:00:00+08:00", "actor": "lead", "phase": "done",
                        "target": "z", "report": "team/old-moved.md"}, ensure_ascii=False),
            # S6：spawn→done 只差 30 秒 ⇒ 闭环时间不可信
            json.dumps({"ts": "2026-01-06T00:00:00+08:00", "actor": "lead", "phase": "spawn",
                        "target": "pair-x"}, ensure_ascii=False),
            json.dumps({"ts": "2026-01-06T00:00:30+08:00", "actor": "lead", "phase": "done",
                        "target": "pair-x", "report": "team/bound-report.md"}, ensure_ascii=False),
        ]) + "\n")
        red_ctx = AuditContext(
            repo=red,
            snapshot_path=red / DEFAULT_SNAPSHOT,
            org_path=red / DEFAULT_ORG,
            verify_dir=red / DEFAULT_VERIFY_DIR,
            agents_path=red / DEFAULT_AGENTS,
            dispatch_path=red / DEFAULT_DISPATCH_LOG,
            dispatch_script=red / DEFAULT_DISPATCH_SCRIPT,
            agents_md_path=red / DEFAULT_AGENTS_MD,
        )
        red_findings = run_checks(red_ctx)
        expect(red_findings, "roster", FAIL, "ghost")  # org 有、快照无
        expect(red_findings, "roster", FAIL, "beta")   # 快照有、org 无
        expect(red_findings, "stall", FAIL, "t-1")
        expect(red_findings, "stall", WARN, "无人认领")
        expect(red_findings, "write_scope", WARN, "t-1")
        expect(red_findings, "write_scope", WARN, "输入")
        expect(red_findings, "artifact_refs", FAIL, "scripts/not-exist/missing.py")
        expect(red_findings, "role_evidence", WARN, "phantom")  # 有声明无证据
        expect(red_findings, "silent_failure", FAIL, "S1")
        expect(red_findings, "silent_failure", FAIL, "S2")
        expect(red_findings, "silent_failure", FAIL, "更正本身不可验证")
        expect(red_findings, "silent_failure", WARN, "S3")
        expect(red_findings, "silent_failure", WARN, "S4")
        expect(red_findings, "silent_failure", WARN, "S5")
        expect(red_findings, "silent_failure", WARN, "S6")
        expect(red_findings, "contract_drift", FAIL, "no-such-stream.jsonl")
        expect(red_findings, "contract_drift", FAIL, "phantom")
        expect(red_findings, "contract_drift", FAIL, "alive")
        expect(red_findings, "contract_drift", WARN, "already-gone")
        expect(red_findings, "contract_drift", WARN, "never-existed")
        if not any(f.check == "commit_hygiene" and f.severity == INFO for f in red_findings):
            failures.append("commit_hygiene 在非 git fixture 上应 INFO 跳过，实际未出现")
        if not any(f.severity == FAIL for f in red_findings):
            failures.append("红 fixture 未产生 FAIL，退出码不会为 1")

        # ---------- 绿 fixture ----------

        green = tmp / "green"
        # lessons_stale（2026-10-24）：绿 fixture 必须也包含教训库 ——
        # 否则这个新检查会把"本该全绿"的 fixture 变成红的（自证夹具不完整）。
        _write(green / "docs/guides/agent-team-lessons.md",
               "# lessons\n\n" + "\n".join(
                   f"### L{i} 判据{i}\n说明{i}：这是一条足够长的判据说明文本，"
                   f"用于让 fixture 超过「内容过短」阈值（1500 字符）。\n"
                   for i in range(1, 40)) + "\n")
        _write(green / "docs/guides/agent-team-org.md", """# org

| 层 | 谁 | 生命周期 |
|---|---|---|
| **L1 常驻领域 Owner** | 2 个 teammate | 常驻 |

## 2. 常驻成员（当前 2 个）

| Agent | 领域 |
|---|---|
| `alpha` | 甲 |
| `team-curator` | 团队维护 |

## 3. 其他
""")
        _write(green / "team/team-board-snapshot.json", json.dumps({
            "schema": "team-board-snapshot/v1",
            # 未来时间：避免「快照过期」WARN（fixture 文件 mtime 必然晚于导出时间）
            "exportedAt": "2099-01-01T00:00:00+08:00",
            "limit": {"maxMembers": 16, "currentMembers": 3},
            "members": [
                {"target": "lead", "role": "lead", "status": "running"},
                {"target": "alpha", "role": "teammate", "status": "inactive"},
                {"target": "team-curator", "role": "teammate", "status": "inactive"},
            ],
            "retired": [], "inactiveOwners": ["alpha", "team-curator"], "tasks": [],
        }, ensure_ascii=False, indent=2))
        _write(green / "team/agents.json", json.dumps({
            "schema_version": 2,
            "event_stream": {"status": "enabled", "path": "team/dispatch-log.jsonl",
                             "phases": ["spawn", "message", "done", "retire", "backfill"],
                             "required_fields": ["ts", "actor", "phase"]},
            "agents": [
                {"id": "lead", "status": "active",
                 "trigger_channel": {"type": "user-dialog", "evidence": "team/dispatch-log.jsonl"}},
                # 声明式别名：id 与 roster 名不同但已显式登记 ⇒ 合法（不是漂移）
                {"id": "curator", "status": "active", "roster_alias": ["team-curator"],
                 "trigger_channel": {"type": "explicit-dispatch+keywords",
                                     "evidence": "team/dispatch-log.jsonl"}},
                # standby：领域已登记但当前无活，不计活性证据（本轮新增状态语义）
                {"id": "alpha", "status": "standby"},
            ],
        }, ensure_ascii=False, indent=2))
        _write(green / "team/dispatch-log.jsonl", "\n".join([
            # task-100：mode_policy 绿路径要求 spawn 显式记录 mode（L9）；否则绿 fixture 会出 WARN
            json.dumps({"ts": "2099-01-01T00:00:00+08:00", "actor": "lead",
                        "phase": "spawn", "target": "curator",
                        "mode": "mechanical", "modeExplicit": True}, ensure_ascii=False),
            json.dumps({"ts": "2099-01-01T00:01:00+08:00", "actor": "curator",
                        "phase": "done", "target": "lead",
                        "report": "artifacts/agent/verify/ok-report.md"}, ensure_ascii=False),
        ]) + "\n")
        _write(green / "scripts/agent/dispatch_log.py",
               'PHASES = ("spawn", "message", "done", "retire", "backfill")\n'
               'REQUIRED_FIELDS = ("ts", "actor", "phase")\n')
        _write(green / "scripts/ok.py", "print('ok')\n")
        _write(green / "artifacts/agent/verify/ok-report.md",
               "# 报告\n\n已落盘 `scripts/ok.py`。\n")
        green_ctx = AuditContext(
            repo=green,
            snapshot_path=green / DEFAULT_SNAPSHOT,
            org_path=green / DEFAULT_ORG,
            verify_dir=green / DEFAULT_VERIFY_DIR,
            agents_path=green / DEFAULT_AGENTS,
            dispatch_path=green / DEFAULT_DISPATCH_LOG,
            dispatch_script=green / DEFAULT_DISPATCH_SCRIPT,
            agents_md_path=green / DEFAULT_AGENTS_MD,
        )
        green_findings = run_checks(green_ctx)
        green_fails = [f for f in green_findings if f.severity == FAIL]
        if green_fails:
            failures.append("绿 fixture 出现意外 FAIL：" + "; ".join(
                f"{f.check}:{f.message}" for f in green_fails[:5]))
        green_warns = [f for f in green_findings if f.severity == WARN]
        if green_warns:
            failures.append("绿 fixture 出现意外 WARN：" + "; ".join(
                f"{f.check}:{f.message}" for f in green_warns[:5]))

        # ---------- task-100：四个新检查的专属红/绿 fixture（缺一不可） ----------
        def _git_do(repo, *args, env_extra=None):
            env = dict(os.environ)
            if env_extra:
                env.update(env_extra)
            subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                           text=True, check=False, env=env)

        def _init_git(repo):
            repo.mkdir(parents=True, exist_ok=True)
            _git_do(repo, "init", "-q")
            _git_do(repo, "config", "user.email", "selftest@example.com")
            _git_do(repo, "config", "user.name", "selftest")
            _git_do(repo, "config", "commit.gpgsign", "false")

        def _commit(repo, message, when):
            _git_do(repo, "add", "-A")
            stamp = when.isoformat()
            _git_do(repo, "commit", "-q", "-m", message,
                    env_extra={"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp})

        def _ctx(repo):
            return AuditContext(
                repo=repo,
                snapshot_path=repo / DEFAULT_SNAPSHOT,
                org_path=repo / DEFAULT_ORG,
                verify_dir=repo / DEFAULT_VERIFY_DIR,
                agents_path=repo / DEFAULT_AGENTS,
                dispatch_path=repo / DEFAULT_DISPATCH_LOG,
                dispatch_script=repo / DEFAULT_DISPATCH_SCRIPT,
                agents_md_path=repo / DEFAULT_AGENTS_MD,
            )

        def _isolated(check_fn, ctx, *extra_args):
            ctx.findings = []
            check_fn(ctx, *extra_args)
            return ctx.findings

        now = datetime.now(timezone.utc)
        day = lambda n: now - timedelta(days=n)  # noqa: E731

        # 1) plan_consulted：红 = 先实施后台账；绿 = 先计划后实施
        plan_red = tmp / "plan-red"
        _init_git(plan_red)
        _write(plan_red / DEFAULT_VERSION_FILE, '__version__ = "0.9.9"\n')
        _write(plan_red / "src" / "impl.py", "x = 1\n")
        _commit(plan_red, "feat: 0.9.9 实现第一步", day(3))
        _write(plan_red / TODO_DOC, "- 0.9.9 计划落盘\n")
        _commit(plan_red, "docs(todo): 0.9.9 计划", day(2))
        plan_red_findings = _isolated(check_plan_consulted, _ctx(plan_red))
        expect(plan_red_findings, "plan_consulted", WARN, "0.9.9")

        plan_green = tmp / "plan-green"
        _init_git(plan_green)
        _write(plan_green / TODO_DOC, "- 0.9.9 计划落盘\n")
        _commit(plan_green, "docs(todo): 0.9.9 计划", day(3))
        _write(plan_green / DEFAULT_VERSION_FILE, '__version__ = "0.9.9"\n')
        _write(plan_green / "src" / "impl.py", "x = 1\n")
        _commit(plan_green, "feat: 0.9.9 实现", day(2))
        plan_green_findings = _isolated(check_plan_consulted, _ctx(plan_green))
        if any(f.check == "plan_consulted" and f.severity in (FAIL, WARN) for f in plan_green_findings):
            failures.append("plan_consulted 绿 fixture 误报：" + "; ".join(
                f"{f.check}:{f.message}" for f in plan_green_findings if f.severity in (FAIL, WARN)))

        # 2) role_registration：红 = 三方各缺一个成员；绿 = 三方全等
        roles_green = tmp / "roles-green"
        _write(roles_green / DEFAULT_SNAPSHOT, json.dumps({
            "schema": "team-board-snapshot/v1", "exportedAt": "2099-01-01T00:00:00+08:00",
            "limit": {}, "retired": [], "inactiveOwners": [], "tasks": [],
            "members": [{"target": "lead", "role": "lead"}, {"target": "alpha", "role": "teammate"}],
        }, ensure_ascii=False))
        _write(roles_green / DEFAULT_ORG,
               "# org\n\n## 2. 常驻成员（当前 1 个）\n\n| Agent | 领域 |\n|---|---|\n| `alpha` | 甲 |\n")
        _write(roles_green / DEFAULT_AGENTS, json.dumps({
            "agents": [{"id": "alpha", "status": "active"}],
        }, ensure_ascii=False))
        green_role_snapshot = json.loads(_read_text(roles_green / DEFAULT_SNAPSHOT))
        roles_green_ctx = _ctx(roles_green)
        roles_green_findings = _isolated(check_role_registration, roles_green_ctx, green_role_snapshot)
        if any(f.check == "role_registration" and f.severity in (FAIL, WARN) for f in roles_green_findings):
            failures.append("role_registration 绿 fixture 误报：" + "; ".join(
                f"{f.check}:{f.message}" for f in roles_green_findings if f.severity in (FAIL, WARN)))

        roles_red = tmp / "roles-red"
        red_role_snapshot = {
            "schema": "team-board-snapshot/v1", "exportedAt": "2026-01-01T00:00:00+08:00",
            "limit": {}, "retired": [], "inactiveOwners": [], "tasks": [],
            "members": [{"target": "lead", "role": "lead"},
                        {"target": "alpha", "role": "teammate"},
                        {"target": "beta", "role": "teammate"}],
        }
        _write(roles_red / DEFAULT_SNAPSHOT, json.dumps(red_role_snapshot, ensure_ascii=False))
        _write(roles_red / DEFAULT_ORG,
               "# org\n\n## 2. 常驻成员\n\n| Agent | 领域 |\n|---|---|\n| `alpha` | 甲 |\n")
        _write(roles_red / DEFAULT_AGENTS, json.dumps({
            "agents": [{"id": "alpha", "status": "active"}, {"id": "ghost", "status": "active"}],
        }, ensure_ascii=False))
        roles_red_findings = _isolated(check_role_registration, _ctx(roles_red), red_role_snapshot)
        expect(roles_red_findings, "role_registration", FAIL, "ghost")   # agents 有 / org 无
        expect(roles_red_findings, "role_registration", FAIL, "beta")    # 快照有 / agents 无
        if not any(f.check == "role_registration" and "checked_count" in f.message for f in roles_red_findings):
            failures.append("role_registration 的 FAIL 消息未带 checked_count")

        # 3) dead_path_edit：红 = 无引用新文件；绿 = 文件被文档引用
        dead_red = tmp / "dead-red"
        _init_git(dead_red)
        _write(dead_red / "scripts" / "dead_probe_zz.py", "print('dead')\n")
        _commit(dead_red, "feat: 新增探针", day(1))
        dead_red_findings = _isolated(check_dead_path_edit, _ctx(dead_red))
        expect(dead_red_findings, "dead_path_edit", WARN, "dead_probe_zz.py")

        dead_green = tmp / "dead-green"
        _init_git(dead_green)
        _write(dead_green / "scripts" / "used_probe_zz.py", "print('used')\n")
        _write(dead_green / "docs" / "ref.md", "跑 `used_probe_zz.py` 取数。\n")
        _commit(dead_green, "feat: 新增被引用探针", day(1))
        dead_green_findings = _isolated(check_dead_path_edit, _ctx(dead_green))
        if any(f.check == "dead_path_edit" and f.severity in (FAIL, WARN) for f in dead_green_findings):
            failures.append("dead_path_edit 绿 fixture 误报：" + "; ".join(
                f"{f.check}:{f.message}" for f in dead_green_findings if f.severity in (FAIL, WARN)))

        # 4) mode_policy：红 = 缺 mode / 缺显式标记 / 非法档位；绿 = 显式 mechanical
        mode_red = tmp / "mode-red"
        stamp = now.isoformat(timespec="seconds")
        _write(mode_red / DEFAULT_DISPATCH_LOG, "\n".join([
            json.dumps({"ts": stamp, "actor": "lead", "phase": "spawn", "target": "no-mode",
                        "desc": "扫一遍仓库统计"}, ensure_ascii=False),
            json.dumps({"ts": stamp, "actor": "lead", "phase": "spawn", "target": "no-explicit",
                        "mode": "standard"}, ensure_ascii=False),
            json.dumps({"ts": stamp, "actor": "lead", "phase": "spawn", "target": "bad-mode",
                        "mode": "turbo", "modeExplicit": True}, ensure_ascii=False),
        ]) + "\n")
        mode_red_findings = _isolated(check_mode_policy, _ctx(mode_red))
        expect(mode_red_findings, "mode_policy", WARN, "缺 mode 字段")
        expect(mode_red_findings, "mode_policy", WARN, "modeExplicit")
        expect(mode_red_findings, "mode_policy", WARN, "不在 DSH 四档")

        mode_green = tmp / "mode-green"
        _write(mode_green / DEFAULT_DISPATCH_LOG, "\n".join([
            json.dumps({"ts": stamp, "actor": "lead", "phase": "spawn", "target": "ok",
                        "mode": "mechanical", "modeExplicit": True,
                        "desc": "跑一条命令取数"}, ensure_ascii=False),
        ]) + "\n")
        mode_green_findings = _isolated(check_mode_policy, _ctx(mode_green))
        if any(f.check == "mode_policy" and f.severity in (FAIL, WARN) for f in mode_green_findings):
            failures.append("mode_policy 绿 fixture 误报：" + "; ".join(
                f"{f.check}:{f.message}" for f in mode_green_findings if f.severity in (FAIL, WARN)))

        # 5) 四个新检查必须已注册进 run_checks（否则上面单测绿、生产不跑 = 假绿）
        registered = {f.check for f in run_checks(_ctx(roles_green))}
        for name in ("plan_consulted", "role_registration", "dead_path_edit", "mode_policy"):
            if name not in registered:
                failures.append(f"run_checks 未注册新检查：{name}")

        if failures:
            print("SELFTEST FAIL")
            for msg in failures:
                print(" - " + msg)
            return 1
        print("SELFTEST PASS：红 fixture 报出 9 类检查（roster×2 / stall ×2 / write_scope ×2 / "
              "artifact_refs / role_evidence / silent_failure ×6 / contract_drift ×5），"
              "commit_hygiene 在非 git fixture 上 INFO 跳过，绿 fixture 全绿；"
              "task-100 四类新检查各自红 fixture 必红、绿 fixture 不误报、且都已注册进 run_checks。")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(description="Memoria 团队体检机检脚本（只读）")
    parser.add_argument("--repo", default=None, help="仓库根目录（默认脚本上两级）")
    parser.add_argument("--snapshot", default=DEFAULT_SNAPSHOT, help="任务板快照路径（相对仓库根）")
    parser.add_argument("--org", default=DEFAULT_ORG, help="团队章程路径（相对仓库根）")
    parser.add_argument("--verify-dir", default=DEFAULT_VERIFY_DIR, help="验证报告目录（相对仓库根）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--strict", action="store_true", help="WARN 也计入退出码")
    parser.add_argument("--selftest", action="store_true", help="自测：证明脚本会红也会绿")
    parser.add_argument("--git-days", type=int, default=COMMIT_WINDOW_DAYS,
                        help=f"commit_hygiene 扫描窗口天数（默认 {COMMIT_WINDOW_DAYS}）")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    repo = Path(args.repo).resolve() if args.repo else Path(__file__).resolve().parents[2]
    ctx = AuditContext(
        repo=repo,
        snapshot_path=(repo / args.snapshot).resolve(),
        org_path=(repo / args.org).resolve(),
        verify_dir=(repo / args.verify_dir).resolve(),
        agents_path=repo / DEFAULT_AGENTS,
        dispatch_path=repo / DEFAULT_DISPATCH_LOG,
        dispatch_script=repo / DEFAULT_DISPATCH_SCRIPT,
        agents_md_path=repo / DEFAULT_AGENTS_MD,
        commit_window_days=args.git_days,
    )
    findings = run_checks(ctx)
    _emit(findings, args.json)
    has_fail = any(f.severity == FAIL for f in findings)
    has_warn = any(f.severity == WARN for f in findings)
    return 1 if has_fail or (args.strict and has_warn) else 0


if __name__ == "__main__":
    sys.exit(main())
