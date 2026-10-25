#!/usr/bin/env python3
"""task-116：生成第三轮 steward 审计收据（r3）——重读标准（team_audit.py 已改）+ 追加 SF-029。

append-only：不改 r2 目录；只新增 r3 目录并追加 team/steward/findings.jsonl。
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

repo = Path(".").resolve()
now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
AUDIT_DIR = repo / "team/steward/audit-2026-10-25-r3"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
cumulative = repo / "team/steward/findings.jsonl"
existing = [json.loads(line) for line in cumulative.read_text(encoding="utf-8").splitlines() if line.strip()]
ids = {row["finding_id"] for row in existing}

new = []
fid = "SF-20261025-029"
if fid not in ids:
    new.append({
        "finding_id": fid, "audit_ts": now, "severity": "WARN", "check": "audit_determinism",
        "rule_ref": "docs/guides/lead-dispatch-rules.md#5.4",
        "claim": "§5.4 的确定性自检曾因 snapshot_health 把实时 mtime 写进 finding 文本而假红："
                 "并发写入时两次运行秒级差异 ⇒ determinism FAIL。已改为只记 exportedAt + 布尔事实（newest_mtime 标记），"
                 "修复后 --determinism PASS（sha b8226d22…）",
        "evidence": ["scripts/agent/team_audit.py:check_snapshot",
                     "python scripts/agent/team_audit.py --determinism"],
        "task_id": "task-116", "disposition": "fixed", "mechanized_as": "team_audit.py --determinism（§5.4）",
        "disposition_by": "steward", "disposition_at": now,
        "note": "教训：§5.4 要求「同输入」；任何把实时时钟/mtime 写入输出的检查都会让确定性自检假红。"
                "检查输出应只含来自输入的稳定事实。",
        "proposal_gap": None,
    })
fid2 = "SF-20261025-030"
if fid2 not in ids:
    new.append({
        "finding_id": fid2, "audit_ts": now, "severity": "WARN", "check": "corrects",
        "rule_ref": "artifacts/agent/verify/debate/PROTOCOL.md#3",
        "claim": "更正 SF-20261025-028：该 finding 漏填 rule_ref（非 proposal 必须有 rule_ref，org.md §2.6 B4）。"
                 "其依据是辩论协议 J6'（§3）：position/ 下产物未 git tracked；现已被提交，dq6 转 PASS。",
        "evidence": ["artifacts/agent/verify/debate/position/agent-arch-position.md",
                     "artifacts/agent/verify/debate/position/lead-source-verification.json",
                     "python scripts/agent/team_audit.py --json"],
        "task_id": "task-116", "disposition": "fixed", "mechanized_as": "team_audit.py::deliberation_quality(dq6)",
        "disposition_by": "steward", "disposition_at": now,
        "note": "台账 append-only：SF-028 原行不改；本行是更正记录，审计快照 r3 用本行替换 SF-028（supersede）。",
        "proposal_gap": None,
        "corrects_finding_id": "SF-20261025-028",
    })

# 审计快照 = 台账应用「更正」后的投影（append-only + supersede，不改历史行）
corrections = {row.get("corrects_finding_id"): row for row in existing + new if row.get("corrects_finding_id")}
snapshot_rows = [row for row in existing + new if row["finding_id"] not in corrections]
snapshot_rows.extend(corrections.values())
all_rows = existing + new
body = "\n".join(json.dumps(row, ensure_ascii=False) for row in snapshot_rows) + "\n"
(AUDIT_DIR / "findings.jsonl").write_text(body, encoding="utf-8", newline="\n")
if new:
    with cumulative.open("a", encoding="utf-8", newline="\n") as fh:
        for row in new:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

standards = []
for path_rel, sections in (
    ("AGENTS.md", "§0.5"),
    ("docs/guides/lead-dispatch-rules.md", "全部（含 §1.2b/§1.3b/§5.4/§6.5）"),
    ("docs/guides/agent-team-lessons.md", "全部（含 L9.6/L9.7）"),
    ("scripts/agent/team_audit.py", "检查清单 + --determinism + deliberation_quality"),
):
    p = repo / path_rel
    standards.append({
        "path": path_rel,
        "sections": sections,
        "sha256": hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
        "read_at": now,
    })

receipt = {
    "schema": "steward-standards-read/v1",
    "audit_ts": now,
    "round": "r3",
    "tool": "team_audit.py@" + hashlib.sha256(
        (repo / "scripts/agent/team_audit.py").read_bytes()).hexdigest()[:12],
    "standards": standards,
    "determinism": {
        "checked": True,
        "command": "python scripts/agent/team_audit.py --determinism",
        "result": "PASS（除 generatedAt 外逐字节一致；sha b8226d22…）",
    },
    "not_read": [
        "docs/guides/agent-team-org.md#§13（本轮只读 §2.3/§2.6，未逐条复核 §13 台账）",
        "src/**（产品代码质量/性能不在 steward 审计范围）",
        "session 正文（按设计不读，只作证据引用）",
    ],
}
(AUDIT_DIR / "standards_read.json").write_text(
    json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print(f"r3 findings: {len(all_rows)}（累计 {len(existing)}+{len(new)}）")
for item in standards:
    print(item["path"], item["sha256"][:16])
