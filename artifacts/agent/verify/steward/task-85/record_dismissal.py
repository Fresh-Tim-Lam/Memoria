#!/usr/bin/env python3
"""task-85 关单记录：把 Lead 裁决（不做缓存）作为 dismissed finding 追加进台账（append-only）。"""
import json
from datetime import datetime, timezone
from pathlib import Path

p = Path("team/steward/findings.jsonl")
rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
ids = {row["finding_id"] for row in rows}
fid = "SF-20261026-035"
if fid in ids:
    print("already present:", fid)
    raise SystemExit(0)
now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
row = {
    "finding_id": fid,
    "audit_ts": now,
    "severity": "WARN",
    "check": "task-85",
    "rule_ref": "docs/guides/lead-dispatch-rules.md#3",
    "claim": "task-85（图谱审计启动跑 3 次，P2）经只读评估后由 Lead 裁决关单（不做 mtime+size 缓存）。"
             "理由：① task-84 已把 validate_kb + loadGraphData 移出 bootAutoOpen 关键路径 ⇒ 原前提「0.3s 在关键路径」不成立；"
             "② 实测 audit_kb_graph_links 单次 369/369/382ms（baseline 29 md），启动实际 2 次 ≈0.74s 后台 CPU（P1 coalesce 已消掉第 3 次），"
             "缓存对首屏收益≈0、只省约 0.37s 后台 CPU；③ 缓存误命中会让用户看到错误断链告警，信任代价 >> 0.37s；"
             "④ 同 size + 同 mtime_ns 替换、resolver 读未纳入键的文件都是真实误命中面。"
             "方案 A（get_graph_data 不内联审计、前端空闲调已有 get_graph_audit()，启动审计 2→1）留作后续独立任务（需改 ui/static/**）。",
    "evidence": [
        "artifacts/agent/verify/steward/task-85/assessment.md",
        "artifacts/agent/verify/steward/task-85/eval.py",
        "artifacts/agent/verify/boot-p1-backend-report.md",
    ],
    "task_id": "task-85",
    "disposition": "dismissed",
    "mechanized_as": None,
    "disposition_by": "lead",
    "disposition_at": now,
    "note": "Lead 裁决：关单，不做缓存。方案 A 另立 UI 任务（不在 task-85 / steward 写域）。",
    "proposal_gap": None,
}
with p.open("a", encoding="utf-8", newline="\n") as fh:
    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
print("appended", fid, "total rows:", len(rows) + 1)
