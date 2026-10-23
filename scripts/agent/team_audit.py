#!/usr/bin/env python3
"""团队体检机检脚本（team-steward 维护）。

把「团队编制/任务状态/交付物」里可机检的部分固化下来，避免靠 Lead
"碰巧注意到"才维护。只读仓库，不写任何文件；输出逐条 finding + 退出码。

覆盖 6 类检查
-------------
1. snapshot_health : 任务板快照是否存在/可解析/关键字段齐全（并提示快照可能过期）
2. roster          : `docs/guides/agent-team-org.md` §2 Owner 表 vs 快照成员/已退役集合
3. stall           : 快照里 `in_progress` 的任务，其 owner 已 `inactive` ⇒ 卡死
4. write_scope     : 未完成任务之间 writeScopes 重叠（含目录前缀重叠）⇒ 串行化风险
5. artifact_refs   : `artifacts/agent/verify/*.md` 中反引号引用的仓库路径是否真的存在
                     （"声称 ≠ 存在"）；任务声明的 `artifacts/.../*.md` 交付物是否存在
6. role_evidence   : `team/agents.json` 里 `status=active` 的角色，是否在
                     14 天内有可复跑证据（dispatch-log 派发 / 任务板 owner / 产物 mtime）。
                     补上 §4 漏检：声明 active 但从未运转的「幽灵角色」。

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
ROLE_EVIDENCE_DAYS = 14

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
    for target in sorted(teammate_targets - org_legal):
        ctx.add(check, FAIL,
                f"快照成员 `{target}` 未出现在 org.md §2 Owner 表中（名册漏登记）",
                f"{ctx.rel(ctx.snapshot_path)}:members vs {ctx.rel(ctx.org_path)}:§2")
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
        expected_total = actual + len(residents)
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
        ctx.add(check, INFO,
                f"未完成任务 {len(active)} 条，两两写域无重叠",
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
        sources = []
        if any((actor == aid or target == aid) and ts >= cutoff for ts, actor, target in dispatch):
            sources.append("dispatch-log")
        if aid in owners:
            sources.append("team-board owner")
        newest = None
        for raw in agent.get("evidence_path") or []:
            # 只认「角色专属产物」：路径里必须出现角色 id，避免所有人共用
            # artifacts/agent/verify/** 这类公共目录而互相「借证据」。
            if aid.lower() not in str(raw).lower():
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
            ],
        }, ensure_ascii=False, indent=2))
        _write(red / "artifacts/agent/verify/claim-report.md",
               "# 报告\n\n已落盘 `scripts/not-exist/missing.py`。\n")
        # 幽灵角色：声明 active，但 14 天内无 dispatch/任务/产物证据
        _write(red / "team/agents.json", json.dumps({
            "schema_version": 2,
            "agents": [
                {"id": "phantom", "status": "active", "evidence_path": ["artifacts/agent/void/**"]},
                {"id": "alpha", "status": "active", "evidence_path": ["artifacts/agent/verify/**"]},
            ],
        }, ensure_ascii=False, indent=2))
        red_ctx = AuditContext(
            repo=red,
            snapshot_path=red / DEFAULT_SNAPSHOT,
            org_path=red / DEFAULT_ORG,
            verify_dir=red / DEFAULT_VERIFY_DIR,
            agents_path=red / DEFAULT_AGENTS,
            dispatch_path=red / DEFAULT_DISPATCH_LOG,
        )
        red_findings = run_checks(red_ctx)
        expect(red_findings, "roster", FAIL, "ghost")  # org 有、快照无
        expect(red_findings, "roster", FAIL, "beta")   # 快照有、org 无
        expect(red_findings, "stall", FAIL, "t-1")
        expect(red_findings, "write_scope", WARN, "t-1")
        expect(red_findings, "artifact_refs", FAIL, "scripts/not-exist/missing.py")
        expect(red_findings, "role_evidence", WARN, "phantom")  # 有声明无证据
        if not any(f.severity == FAIL for f in red_findings):
            failures.append("红 fixture 未产生 FAIL，退出码不会为 1")

        # ---------- 绿 fixture ----------
        green = tmp / "green"
        _write(green / "docs/guides/agent-team-org.md", """# org

| 层 | 谁 | 生命周期 |
|---|---|---|
| **L1 常驻领域 Owner** | 1 个 teammate | 常驻 |

## 2. 常驻成员（当前 1 个）

| Agent | 领域 |
|---|---|
| `alpha` | 甲 |

## 3. 其他
""")
        _write(green / "team/team-board-snapshot.json", json.dumps({
            "schema": "team-board-snapshot/v1",
            # 未来时间：避免「快照过期」WARN（fixture 文件 mtime 必然晚于导出时间）
            "exportedAt": "2099-01-01T00:00:00+08:00",
            "limit": {"maxMembers": 16, "currentMembers": 2},
            "members": [
                {"target": "lead", "role": "lead", "status": "running"},
                {"target": "alpha", "role": "teammate", "status": "active"},
            ],
            "retired": [], "inactiveOwners": [], "tasks": [],
        }, ensure_ascii=False, indent=2))
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
        print("SELFTEST PASS：红 fixture 报出 6 项（roster×2 / stall / write_scope / artifact_refs / "
              "role_evidence），绿 fixture 全绿。")
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
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    repo = Path(args.repo).resolve() if args.repo else Path(__file__).resolve().parents[2]
    ctx = AuditContext(
        repo=repo,
        snapshot_path=(repo / args.snapshot).resolve(),
        org_path=(repo / args.org).resolve(),
        verify_dir=(repo / args.verify_dir).resolve(),
    )
    findings = run_checks(ctx)
    _emit(findings, args.json)
    has_fail = any(f.severity == FAIL for f in findings)
    has_warn = any(f.severity == WARN for f in findings)
    return 1 if has_fail or (args.strict and has_warn) else 0


if __name__ == "__main__":
    sys.exit(main())
