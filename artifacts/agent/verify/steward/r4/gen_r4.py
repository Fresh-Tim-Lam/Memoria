#!/usr/bin/env python3
"""r4 审计收据生成（2026-10-26）：标准重读 + append-only 更正投影 + prompt_drift_check 纳入。

边界（Lead）：只动 team/steward/** 与 artifacts/agent/verify/steward/**；不 commit。
"""
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

repo = Path(".").resolve()
now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
AUDIT_DIR = repo / "team/steward/audit-2026-10-26-r4"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)


def _raw_sha(path: Path) -> str:
    """当前 steward_self_audit 口径：工作区原始字节 sha256（task-110 未修，仍非跨平台）。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return proc.stdout.strip() if proc.returncode == 0 else ""


cumulative = repo / "team/steward/findings.jsonl"
rows = [json.loads(line) for line in cumulative.read_text(encoding="utf-8").splitlines() if line.strip()]
ids = {row["finding_id"] for row in rows}

# ---- 本轮新增 finding（append-only）----
new = []
fid = "SF-20261026-031"
if fid not in ids:
    new.append({
        "finding_id": fid, "audit_ts": now, "severity": "WARN", "check": "steward_self_audit",
        "rule_ref": None,
        "claim": "prompt_drift_check.py 已进入 team_audit 门禁（task-152），但 steward_self_audit 的 "
                 "STEWARD_STANDARDS 仍是 4 项，不含该脚本 ⇒ 它单独变更时收据不会过期（覆盖缺口）；"
                 "本轮 r4 我手工把它写进收据（第 5 项），但机检不会校验它。",
        "evidence": ["scripts/agent/team_audit.py:STEWARD_STANDARDS",
                     "scripts/agent/prompt_drift_check.py",
                     "team/steward/audit-2026-10-26-r4/standards_read.json"],
        "task_id": None, "disposition": "proposal", "mechanized_as": None,
        "disposition_by": "steward", "disposition_at": now,
        "note": "建议把 STEWARD_STANDARDS 扩为 5 项（加入 prompt_drift_check.py），"
                "并同步 org.md §2.6 B3 的标准清单；属 team_audit.py 写域，需 Lead 批。",
        "proposal_gap": "org.md §2.6 B3 只列了 AGENTS/rules/lessons/team_audit.py 四个标准，未覆盖新门禁脚本",
    })
fid2 = "SF-20261026-032"
if fid2 not in ids:
    new.append({
        "finding_id": fid2, "audit_ts": now, "severity": "WARN", "check": "audit_determinism",
        "rule_ref": "docs/guides/agent-team-org.md#2.6 B3",
        "claim": "r4 重签确认：当前 steward_self_audit 比对的是**工作区原始字节** sha256"
                 "（`hashlib.sha256(path.read_bytes())`），不是 LF 归一化 —— 即 task-110/SF-025 的不可移植性问题**仍然存在**；"
                 "本轮工作树恰为 LF（raw==LF），所以未暴露差异。另：task-152 的 team_audit.py/prompt_drift_check.py "
                 "改动是**未提交工作区修改**，r4 收据绑定的是 worktree sha（team_audit.py=4c697128…，"
                 "prompt_drift_check.py=6cbc9f86…），git base=f2a415c5；若 Lead 提交前再改这两个文件，r4 立即过期（符合设计）。",
        "evidence": ["scripts/agent/team_audit.py:current = hashlib.sha256(path.read_bytes())",
                     "scripts/agent/prompt_drift_check.py",
                     "team/steward/audit-2026-10-26-r4/standards_read.json"],
        "task_id": "task-110", "disposition": "open", "mechanized_as": None,
        "disposition_by": None, "disposition_at": None,
        "note": "本行为 task-110 的证据：修复时须同时改**写入端与读取端**为 content_sha256（LF 归一化），"
                "并跑一次新收据（r5），不得改历史收据。",
        "proposal_gap": None,
    })
all_rows = rows + new

# ---- 审计快照：append-only 台账的「更正投影」（去重后保留 supersede 记录）----
by_id = {row["finding_id"]: row for row in all_rows}
corrections = {}
for row in all_rows:
    corrected = row.get("corrects_finding_id")
    if corrected:
        corrections[corrected] = row
for original, correction in corrections.items():
    by_id.pop(original, None)
    by_id[correction["finding_id"]] = correction
snapshot_rows = list(by_id.values())
snapshot_rows.sort(key=lambda row: row["finding_id"])
(AUDIT_DIR / "findings.jsonl").write_text(
    "\n".join(json.dumps(row, ensure_ascii=False) for row in snapshot_rows) + "\n",
    encoding="utf-8", newline="\n")
if new:
    with cumulative.open("a", encoding="utf-8", newline="\n") as fh:
        for row in new:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

# ---- prompt_drift_check 独立核验（作为标准的一部分）----
pd = subprocess.run([sys.executable, "scripts/agent/prompt_drift_check.py", "--repo", str(repo), "--json"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
pd_summary = {}
try:
    pd_summary = (json.loads(pd.stdout).get("summary") or {}) if pd.stdout else {}
except json.JSONDecodeError:
    pd_summary = {"parse_error": True}

# ---- standards_read（第 5 项 = prompt_drift_check.py；全部按原始字节口径）----
standards = []
for path_rel, sections in (
    ("AGENTS.md", "§0.5"),
    ("docs/guides/lead-dispatch-rules.md", "全部（含 §1.2b/§1.3b/§5.4/§6.5）"),
    ("docs/guides/agent-team-lessons.md", "全部（含 L9.6/L9.7）"),
    ("scripts/agent/team_audit.py", "检查清单 + --determinism + deliberation_quality + prompt_drift 接线"),
    ("scripts/agent/prompt_drift_check.py", "C1-C5 检查 + --json/--selftest/--recheck-deps/--resign 接口"),
):
    target = repo / path_rel
    standards.append({
        "path": path_rel,
        "sections": sections,
        "sha256": _raw_sha(target),
        "sha_mode": "raw-worktree-bytes（当前 steward_self_audit 口径；task-110 修后应改 LF 归一化）",
        "read_at": now,
    })

receipt = {
    "schema": "steward-standards-read/v1",
    "audit_ts": now,
    "round": "r4",
    "tool": "team_audit.py@" + _raw_sha(repo / "scripts/agent/team_audit.py")[:12],
    "git_base": _git("rev-parse", "--short", "HEAD"),
    "worktree_dirty_standards": ["scripts/agent/team_audit.py", "scripts/agent/prompt_drift_check.py"],
    "standards": standards,
    "prompt_drift_standalone": {
        "command": "python scripts/agent/prompt_drift_check.py --json",
        "exit": pd.returncode,
        "summary": pd_summary,
    },
    "determinism": {
        "checked": True,
        "command": "python scripts/agent/team_audit.py --determinism",
        "result": "PASS（除 generatedAt 外逐字节一致；r4 前跑 sha 43c475c1…，compared_findings=81）",
    },
    "not_read": [
        "docs/guides/agent-team-org.md#§13（本轮只读 §2.3/§2.6，未逐条复核 §13 台账）",
        "src/**（产品代码质量/性能不在 steward 审计范围）",
        "session 正文（按设计不读，只作证据引用）",
    ],
}
(AUDIT_DIR / "standards_read.json").write_text(
    json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print(f"r4 findings snapshot: {len(snapshot_rows)}（台账 {len(all_rows)} 行，新 {len(new)}）")
for item in standards:
    print(item["path"], item["sha256"][:16], "raw")
print("prompt_drift standalone:", pd.returncode, pd_summary)
