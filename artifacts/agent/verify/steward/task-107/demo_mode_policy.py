#!/usr/bin/env python3
"""task-107 联调证据：mode_policy 对「新写入的 spawn 行」能给出可判定结论。

不写真实 team/dispatch-log.jsonl（append-only 且不伪造历史）：用临时日志 + AuditContext 调真实检查函数。
"""
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "scripts/agent")
import team_audit as ta  # noqa: E402

repo = Path(".").resolve()
now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

rows = [
    # 历史行（task-107 之前）：缺 mode —— 应只作为"无法判定"计入 WARN 目标
    {"ts": now, "actor": "lead", "phase": "spawn", "target": "legacy-1", "task": "task-x"},
    {"ts": now, "actor": "lead", "phase": "spawn", "target": "legacy-2", "task": "task-y"},
    # 新行（task-107 之后）：带显式 mode —— 应可判定、不产生 WARN
    {"ts": now, "actor": "lead", "phase": "spawn", "target": "new-mech",
     "task": "task-107", "mode": "mechanical", "modeExplicit": True},
    {"ts": now, "actor": "lead", "phase": "spawn", "target": "new-std",
     "task": "task-107", "mode": "standard", "modeExplicit": True},
]

with tempfile.TemporaryDirectory(prefix="mode-policy-demo-") as tmp:
    log_path = Path(tmp) / "dispatch-log.jsonl"
    log_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    ctx = ta.AuditContext(
        repo=repo,
        snapshot_path=repo / ta.DEFAULT_SNAPSHOT,
        org_path=repo / ta.DEFAULT_ORG,
        verify_dir=repo / ta.DEFAULT_VERIFY_DIR,
        dispatch_path=log_path,
    )
    ta.check_mode_policy(ctx)
    print("=== mode_policy 对「2 条历史缺 mode + 2 条新记录显式 mode」的判定 ===")
    for finding in ctx.findings:
        print(f"[{finding.severity}] {finding.message}")
        print(f"         证据：{finding.evidence}")

    # 另一个函数：dispatch_log.py 的 check 对同一日志给出 mode_coverage
    import dispatch_log as dl  # noqa: E402
    report = dl.check(log_path, max_age_days=36500)
    print()
    print("=== dispatch_log.py check 的 mode_coverage ===")
    print(json.dumps(report["mode_coverage"], ensure_ascii=False))
    print(f"warnings={len(report['warnings'])}（应只命中 2 条历史行）")
    for warning in report["warnings"]:
        print(f"  - line {warning['line']} {warning['target']}：{warning['check']}")
