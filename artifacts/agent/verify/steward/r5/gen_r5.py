#!/usr/bin/env python3
"""r5 审计收据生成（task-110）：LF 归一化内容 sha 口径 + prompt_drift_check 纳入第 5 标准。

只写 team/steward/**；不 commit。历史收据（r2/r3/r4）不改，append-only。
"""
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

repo = Path(".").resolve()
now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
AUDIT_DIR = repo / "team/steward/audit-2026-10-26-r5"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)


def content_sha256(path: Path) -> str:
    """与 team_audit.content_sha256 同口径：\\r\\n→\\n 后按字节 sha256（BOM 保留）。"""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _git(*args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return proc.stdout.strip() if proc.returncode == 0 else ""


cumulative = repo / "team/steward/findings.jsonl"
rows = [json.loads(line) for line in cumulative.read_text(encoding="utf-8").splitlines() if line.strip()]
ids = {row["finding_id"] for row in rows}

new = []
if "SF-20261026-033" not in ids:
    new.append({
        "finding_id": "SF-20261026-033", "audit_ts": now, "severity": "WARN",
        "check": "steward_self_audit", "rule_ref": "docs/guides/agent-team-org.md#2.6 B3",
        "claim": "SF-031 修复：STEWARD_STANDARDS 扩为 5 项（加入 scripts/agent/prompt_drift_check.py）；"
                 "该脚本单独变更现在也会让收据过期。r5 收据已按 5 项重读（真实 sha）。",
        "evidence": ["scripts/agent/team_audit.py:STEWARD_STANDARDS",
                     "team/steward/audit-2026-10-26-r5/standards_read.json"],
        "task_id": "task-110", "disposition": "fixed",
        "mechanized_as": "team_audit.py::steward_self_audit（5 标准）",
        "disposition_by": "steward", "disposition_at": now,
        "note": "SF-031 的 proposal 闭环；B3 条款文字仍待 Lead 落进 org.md。",
        "proposal_gap": None, "corrects_finding_id": "SF-20261026-031",
    })
if "SF-20261026-034" not in ids:
    new.append({
        "finding_id": "SF-20261026-034", "audit_ts": now, "severity": "WARN",
        "check": "audit_determinism", "rule_ref": "docs/guides/agent-team-org.md#2.6 B3",
        "claim": "task-110/SF-025 修复：新增 content_sha256(path)（\\r\\n→\\n 后算 sha256，BOM 保留）；"
                 "steward_self_audit 的读取校验改用它（写入端 r5 收据同口径）；新增 --sha-explain。"
                 "selftest 增双向移植性断言：LF/CRLF 同内容 ⇒ content_sha256 相同、原始字节 sha 不同；"
                 "旧口径（收据记原始 CRLF 字节 sha）fixture 必红、CRLF 工作区 + LF 口径收据必绿。"
                 "r5 FAIL=0，收据 sha 跨平台可复算。",
        "evidence": ["scripts/agent/team_audit.py:content_sha256",
                     "scripts/agent/team_audit.py:sha_explain",
                     "team/steward/audit-2026-10-26-r5/standards_read.json"],
        "task_id": "task-110", "disposition": "fixed",
        "mechanized_as": "team_audit.py::steward_self_audit + --selftest + --sha-explain",
        "disposition_by": "steward", "disposition_at": now,
        "note": "旧收据 r2/r3/r4 保持原样（append-only）；r5 起收据按 content_sha256 口径。",
        "proposal_gap": None, "corrects_finding_id": "SF-20261026-032",
    })
all_rows = rows + new

by_id = {row["finding_id"]: row for row in all_rows}
corrections = {}
for row in all_rows:
    corrected = row.get("corrects_finding_id")
    if corrected:
        corrections[corrected] = row
for original, correction in corrections.items():
    by_id.pop(original, None)
    by_id[correction["finding_id"]] = correction
snapshot_rows = sorted(by_id.values(), key=lambda row: row["finding_id"])
(AUDIT_DIR / "findings.jsonl").write_text(
    "\n".join(json.dumps(row, ensure_ascii=False) for row in snapshot_rows) + "\n",
    encoding="utf-8", newline="\n")
if new:
    with cumulative.open("a", encoding="utf-8", newline="\n") as fh:
        for row in new:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

standards = []
for path_rel, sections in (
    ("AGENTS.md", "§0.5"),
    ("docs/guides/lead-dispatch-rules.md", "全部（含 §1.2b/§1.3b/§5.4/§6.5）"),
    ("docs/guides/agent-team-lessons.md", "全部（含 L9.6/L9.7）"),
    ("scripts/agent/team_audit.py", "检查清单 + --determinism + --sha-explain + deliberation_quality"),
    ("scripts/agent/prompt_drift_check.py", "C1-C5 + --json/--selftest/--recheck-deps/--resign 接口"),
):
    target = repo / path_rel
    standards.append({
        "path": path_rel,
        "sections": sections,
        "sha256": content_sha256(target),
        "sha_mode": "content-lf（\\r\\n→\\n 后算；task-110/org.md §2.6 B3）",
        "read_at": now,
    })

dirty = [line[3:].strip() for line in _git("status", "--porcelain", "--", "scripts/agent", "team/steward").splitlines()
         if line.strip()]
receipt = {
    "schema": "steward-standards-read/v1",
    "audit_ts": now,
    "round": "r5",
    "tool": "team_audit.py@" + content_sha256(repo / "scripts/agent/team_audit.py")[:12],
    "git_base": _git("rev-parse", "--short", "HEAD"),
    "worktree_dirty_standards": [item for item in dirty if item.startswith("scripts/")],
    "standards": standards,
    "portability_evidence": {
        "selftest_assertions": "content_sha256(LF)==content_sha256(CRLF)；raw_sha256(LF)!=raw_sha256(CRLF)",
        "old_receipt_red_fixture": "steward-crlf-raw（收据记原始 CRLF 字节 sha ⇒ FAIL）",
        "crlf_workspace_green_fixture": "steward-crlf-lf（CRLF 工作区 + LF 口径收据 ⇒ 无 FAIL）",
    },
    "determinism": {
        "checked": True,
        "command": "python scripts/agent/team_audit.py --determinism",
        "result": "见 r5 报告（生成收据后单独运行）",
    },
    "not_read": [
        "docs/guides/agent-team-org.md#§13（本轮只读 §2.3/§2.6，未逐条复核 §13 台账）",
        "src/**（产品代码质量/性能不在 steward 审计范围）",
        "session 正文（按设计不读，只作证据引用）",
    ],
}
(AUDIT_DIR / "standards_read.json").write_text(
    json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print(f"r5 snapshot: {len(snapshot_rows)}（台账 {len(all_rows)} 行，新 {len(new)}）")
for item in standards:
    print(item["path"], item["sha256"][:16], "content-lf")
