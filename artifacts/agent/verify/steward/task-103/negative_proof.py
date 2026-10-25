#!/usr/bin/env python3
"""task-103 自证脚本：steward_self_audit 的两个负例必须红，恢复后必须绿。"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

repo = Path(".").resolve()
audit_dir = repo / "team/steward/audit-2026-10-24"
receipt = audit_dir / "standards_read.json"
findings = audit_dir / "findings.jsonl"
log: list[str] = []


def run_audit() -> tuple[int, dict, list[dict]]:
    proc = subprocess.run(
        [sys.executable, "scripts/agent/team_audit.py", "--json"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    data = json.loads(proc.stdout)
    self_audit = [f for f in data["findings"] if f["check"] == "steward_self_audit"]
    return proc.returncode, data, self_audit


receipt_backup = receipt.read_text(encoding="utf-8")
findings_backup = findings.read_text(encoding="utf-8")
try:
    # 负例 1：篡改收据里的标准 sha256 ⇒ 必须 FAIL「用缓存标准审计」
    modified = json.loads(receipt_backup)
    modified["standards"][0]["sha256"] = "0" * 64
    receipt.write_text(json.dumps(modified, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    code, data, self_audit = run_audit()
    log.append("=== 负例1：篡改 standards_read 的 AGENTS.md sha256（模拟「用缓存标准审计」）===")
    log.append(f"audit exit={code}; summary={data['summary']}")
    for item in self_audit:
        log.append(f"[{item['severity']}] {item['message']}")
    log.append("")
    receipt.write_text(receipt_backup, encoding="utf-8")  # 先恢复，保证负例2 只测自己的判据

    # 负例 2：插入非 proposal 且 rule_ref 不可解析的 finding ⇒ 必须 FAIL「把偏好当规范」
    bad = {
        "finding_id": "SF-20261024-999",
        "audit_ts": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "severity": "WARN", "check": "selftest",
        "rule_ref": "docs/guides/not-exist.md#1",
        "claim": "负例：rule_ref 指向不存在的文件",
        "evidence": ["selftest"], "task_id": None, "disposition": "open",
        "mechanized_as": None, "disposition_by": None, "disposition_at": None, "note": None,
    }
    findings.write_text(findings_backup + json.dumps(bad, ensure_ascii=False) + "\n", encoding="utf-8")
    code, data, self_audit = run_audit()
    log.append("=== 负例2：插入 rule_ref 不可解析且非 proposal 的 finding ===")
    log.append(f"audit exit={code}; summary={data['summary']}")
    for item in self_audit:
        log.append(f"[{item['severity']}] {item['message']}")
    log.append("")
finally:
    receipt.write_text(receipt_backup, encoding="utf-8")
    findings.write_text(findings_backup, encoding="utf-8")

# 恢复后必须回到绿
code, data, self_audit = run_audit()
log.append("=== 恢复后（期望：steward_self_audit = INFO，audit exit=0）===")
log.append(f"audit exit={code}; summary={data['summary']}")
for item in self_audit:
    log.append(f"[{item['severity']}] {item['message']}")

output = "\n".join(log) + "\n"
out_path = repo / "artifacts/agent/verify/steward/task-103/negative-proofs.txt"
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(output, encoding="utf-8")
print(output)
