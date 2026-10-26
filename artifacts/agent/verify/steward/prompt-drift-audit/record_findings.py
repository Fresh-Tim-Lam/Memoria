#!/usr/bin/env python3
"""追加 2026-10-26 的 6 条 finding：SF-036（freeze --refreeze proposal）+ SF-037..041（prompt-drift 守卫缺口）。"""
import json
from datetime import datetime, timezone
from pathlib import Path

p = Path("team/steward/findings.jsonl")
rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
ids = {row["finding_id"] for row in rows}
now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

items = [
    {
        "finding_id": "SF-20261026-036",
        "severity": "WARN", "check": "proposal", "rule_ref": None,
        "claim": "freeze 机制没有 --refreeze：标准变更时只能人工改 freeze-v2.json（Lead 已记 design gap）。"
                 "本提案建议独立脚本 scripts/agent/freeze_refreeze.py：--check 只读比对（与 dq5 同 content_sha256 口径）、"
                 "--apply 仅漂移时 append-only 追加 standards_updated（reason/rule_ref/commit/changed + baseline_mutation 结论）、"
                 "拒绝空 reason/坏 rule_ref/无变更重复写/决策标准变更未声明 reopen；落点不塞进 team_audit.py（避免自指重签循环）。",
        "evidence": ["artifacts/agent/verify/steward/PROPOSAL-freeze-refreeze.md",
                     "artifacts/agent/verify/debate/freeze-v2.json#standards_updated",
                     "scripts/agent/team_audit.py::check_deliberation_quality(dq5)"],
        "task_id": "task-110", "disposition": "proposal", "mechanized_as": None,
        "proposal_gap": "现行条款（F1/B3）只规定 freeze 内容与收据口径，未规定冻结物更新的可审计流程；"
                        "建议新增 L12（冻结物更新）后再实现。",
        "note": "按 L10：无条款 ⇒ 先 proposal；最小可用版可先只做 --check（只读零风险）。",
    },
    {
        "finding_id": "SF-20261026-037",
        "severity": "WARN", "check": "prompt_drift_check", "rule_ref": "AGENTS.md#0.5 L6",
        "claim": "PD-1（高）：prompt_drift_check 在'检查无法执行'时只报 WARN 并继续（如 edge_types.py 读不到 ⇒ C3 跳过），"
                 "而 team_audit 门禁只在 FAIL>0 时红 ⇒ 整道门禁可能失效但显示绿（'看起来成功其实没做'）。"
                 "探针 C 实测：edge_types 置空 ⇒ FAIL=0/WARN=1/exit=0。",
        "evidence": ["scripts/agent/prompt_drift_check.py:715-717",
                     "artifacts/agent/verify/steward/prompt-drift-audit/probe-output.txt",
                     "scripts/agent/team_audit.py::check_prompt_drift"],
        "task_id": None, "disposition": "open", "mechanized_as": None,
        "note": "建议：'未执行'必须是 FAIL/exit 2（或带 check_status=not_run），门禁把 not_run 当红；只有'确证无问题'才绿。",
        "proposal_gap": None,
    },
    {
        "finding_id": "SF-20261026-038",
        "severity": "WARN", "check": "prompt_drift_check", "rule_ref": "AGENTS.md#0.5 L6",
        "claim": "PD-2：C2 点分字段分支只校验 SNAKE 段；camelCase/其它段既不校验也不进 unclassified，无任何 finding。"
                 "探针 A 实测：`range.fake_snake_field` ⇒ FAIL（对照）；`range.fakeCamelField` ⇒ 无 finding（伪造符号隐形）。",
        "evidence": ["scripts/agent/prompt_drift_check.py:636-641",
                     "artifacts/agent/verify/steward/prompt-drift-audit/probe-output.txt"],
        "task_id": None, "disposition": "open", "mechanized_as": None,
        "note": "建议非 SNAKE 段进 unclassified（至少 INFO），或对点分路径做字段白名单/代码字面量校验。",
        "proposal_gap": None,
    },
    {
        "finding_id": "SF-20261026-039",
        "severity": "WARN", "check": "prompt_drift_check", "rule_ref": "AGENTS.md#0.5 L6",
        "claim": "PD-3：C1 的'隐藏分发路径探测'显式跳过路径含 kb_agent/ui.py/build.py 的文件（最可能藏目录扫描复制的位置），"
                 "等于探测对最可能文件永远不报。",
        "evidence": ["scripts/agent/prompt_drift_check.py:464",
                     "artifacts/agent/verify/steward/prompt-drift-audit/audit.md#PD-3"],
        "task_id": None, "disposition": "open", "mechanized_as": None,
        "note": "建议去掉'路径含名字'跳过条件，改精确 pattern：发现 iterdir/glob/rglob+agent-prompts 即 WARN（含这些文件）。",
        "proposal_gap": None,
    },
    {
        "finding_id": "SF-20261026-040",
        "severity": "WARN", "check": "prompt_drift_check", "rule_ref": "AGENTS.md#0.5 L6",
        "claim": "PD-4：C1 孤儿检测只用 src_dir.iterdir() 顶层文件；resources/agent-prompts/** 子目录里的孤儿文件不报。",
        "evidence": ["scripts/agent/prompt_drift_check.py:441",
                     "artifacts/agent/verify/steward/prompt-drift-audit/audit.md#PD-4"],
        "task_id": None, "disposition": "open", "mechanized_as": None,
        "note": "建议 rglob(\"*\") + 相对路径，保留 APP_INTERNAL_ASSETS 白名单。",
        "proposal_gap": None,
    },
    {
        "finding_id": "SF-20261026-041",
        "severity": "WARN", "check": "prompt_drift_check", "rule_ref": "AGENTS.md#0.5 L6",
        "claim": "PD-5：C3 同行任意位置出现 LEGACY_QUALIFIERS（不要/禁止/遗留…）即整行豁免。"
                 "探针 B 实测：推荐式 [[某#contain]]+同句无关'不要写错别字' ⇒ 无 finding（推荐语法被静默放过）。",
        "evidence": ["scripts/agent/prompt_drift_check.py:739-740",
                     "artifacts/agent/verify/steward/prompt-drift-audit/probe-output.txt"],
        "task_id": None, "disposition": "open", "mechanized_as": None,
        "note": "建议限定词必须紧邻 wikilink（邻近窗口匹配），不用整行 includes。",
        "proposal_gap": None,
    },
]

added = 0
with p.open("a", encoding="utf-8", newline="\n") as fh:
    for item in items:
        if item["finding_id"] in ids:
            continue
        row = {"audit_ts": now, "evidence": [], "task_id": None, "mechanized_as": None,
               "disposition_by": "steward", "disposition_at": now, "note": None,
               "proposal_gap": None, **item}
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        added += 1
print(f"appended {added}; total rows: {len(rows) + added}")
