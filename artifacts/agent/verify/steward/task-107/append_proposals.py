#!/usr/bin/env python3
"""追加 task-107 期间产生的 3 条 proposal 到 team/steward/findings.jsonl（append-only，不改历史行）。"""
import json
from datetime import datetime, timezone
from pathlib import Path

path = Path("team/steward/findings.jsonl")
now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
existing = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
existing_ids = {row["finding_id"] for row in existing}


def proposal(fid, claim, evidence, note, gap):
    assert fid not in existing_ids, f"重复 finding_id: {fid}"
    return {
        "finding_id": fid, "audit_ts": now, "severity": "WARN", "check": "proposal",
        "rule_ref": None, "claim": claim, "evidence": evidence, "task_id": None,
        "disposition": "proposal", "mechanized_as": None,
        "disposition_by": "steward2", "disposition_at": now, "note": note,
        "proposal_gap": gap,
    }


new = [
    proposal(
        "SF-20261024-014",
        "机检 audit_determinism：team_audit.py 连跑两次除 generatedAt 外应逐字节一致"
        "（Lead 实测 run1/run2 仅时间戳不同，证明 FAIL=0 可复现）",
        ["Lead 2026-10-24 自检：run1 sha=df4d82fb…/18854B，run2 sha=a6b16994…/18854B，差异仅 generatedAt",
         "scripts/agent/team_audit.py"],
        "Lead 已实测通过；由 Lead 批准后可在 team_audit.py 新增 audit_determinism（连跑两次比对，排除 generatedAt）",
        "现行规范没有「机检必须确定性/可复现」条款 ⇒ 只能建议新增，不能直接变成检查（防过拟合）",
    ),
    proposal(
        "SF-20261024-015",
        "写域粒度太粗：目录级 writeScopes 制造假重叠 WARN（当前 11 条 write_scope 中 9 条是"
        "「共享根 vs 其子路径」，只有 2 条是同文件真重叠：task-85↔task-91 ask.py/compaction.py）",
        ["team_audit.py write_scope：task-86/94 的 artifacts/agent/verify 根 vs task-103/107 子目录",
         "task-86 docs/design 根 vs task-90 具体文件",
         "task-85 src/memoria/services 根 vs task-92 services/agent",
         "task-85 与 task-91 同文件 ask.py / compaction.py（真重叠）"],
        "推荐 (a)+(b)：① 条款约定「写域到文件/任务专属子目录；共享产出根不作 writeScope」"
        "② write_scope 判据分级：共享根 vs 其子路径 ⇒ INFO；同文件/同子目录 ⇒ WARN；"
        "③ 增强（P2）用 git show --name-only 反查实际改动 vs 声明写域",
        "现行 lead-dispatch-rules §1.2 只写「写域重叠 ⇒ 排队」，未规定声明粒度/分级判据 ⇒ proposal",
    ),
    proposal(
        "SF-20261024-016",
        "mode_policy 未区分「显式未决定」与「历史缺 mode」：dispatch_log 现已支持 --mode-explicit false，"
        "但 team_audit::mode_policy 仍把它计入「缺 mode 无法判定」",
        ["scripts/agent/dispatch_log.py:--mode-explicit false（task-107）",
         "scripts/agent/team_audit.py::check_mode_policy"],
        "建议 team_audit 的 mode_policy 把 modeExplicit=false 单列 WARN「显式未决定」；"
        "属既有检查判据细化，需 Lead 批条款后改",
        "AGENTS.md §0.5 L9 只说「不传 mode = 没做决策」，未规定「显式未决定」如何判定 ⇒ proposal",
    ),
]

with path.open("a", encoding="utf-8", newline="\n") as fh:
    for row in new:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
print(f"appended {len(new)} proposals; total now {len(existing) + len(new)}")
for row in new:
    print(" ", row["finding_id"], row["claim"][:60])
