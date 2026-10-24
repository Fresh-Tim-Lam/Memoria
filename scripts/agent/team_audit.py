#!/usr/bin/env python3
"""团队体检机检脚本（team-steward 维护）。

把「团队编制/任务状态/交付物」里可机检的部分固化下来，避免靠 Lead
"碰巧注意到"才维护。只读仓库，不写任何文件；输出逐条 finding + 退出码。

覆盖 9 类检查
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
        ctx.add(check, FAIL,
                f"已退役的 `{target}` 仍占快照成员名额（退役未生效）",
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
            json.dumps({"ts": "2099-01-01T00:00:00+08:00", "actor": "lead",
                        "phase": "spawn", "target": "curator"}, ensure_ascii=False),
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

        if failures:
            print("SELFTEST FAIL")
            for msg in failures:
                print(" - " + msg)
            return 1
        print("SELFTEST PASS：红 fixture 报出 9 类检查（roster×2 / stall ×2 / write_scope ×2 / "
              "artifact_refs / role_evidence / silent_failure ×6 / contract_drift ×5），"
              "commit_hygiene 在非 git fixture 上 INFO 跳过，绿 fixture 全绿。")
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
