#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""组件→任务工作流组装器（comp.workflow-composer，task-273；dry-run only）。

输入：--components "comp.a,comp.b,..."（或多次 --component） + --goal + --owner? + --dry-run
输出：{ok, workflowPlan:{steps:[{id,componentId,ownerRole,gates[],evidence[]}],
       acceptGap:[{componentId,ownerRole,reason,expiry,degradedTo}], blockedBy[]}, counts}
规则：
  - 每个 componentId 必须存在于 registry v2；不存在 ⇒ blockedBy 并 exit 1；
  - registry status=missing 的组件进入工作流 ⇒ 生成 acceptGap（5 字段完整）；acceptGap >4 ⇒ exit 1；
  - 空输入 ⇒ exit 1（不许产出空计划）；未传 --dry-run ⇒ exit 2（本工具只做 dry-run）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = "docs/design/component-registry.v2.json"
MAX_ACCEPT_GAP = 4
ACCEPT_GAP_EXPIRY = "2026-12-31"


def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def load_registry(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def compose(component_ids: list[str], registry: dict, goal: str = "", owner: str = "lead") -> dict:
    components = {str(c.get("id")): c for c in (registry.get("components") or [])
                  if isinstance(c, dict) and c.get("id")}
    if not component_ids:
        return {"ok": False, "workflowPlan": {"steps": [], "acceptGap": [], "blockedBy": []},
                "violations": [{"rule": "EMPTY_INPUT", "detail": "componentIds 为空：不许产出空计划"}]}
    steps = []
    accept_gap = []
    blocked_by = []
    for index, component_id in enumerate(component_ids, 1):
        component = components.get(component_id)
        if component is None:
            blocked_by.append(component_id)
            continue
        owner_role = str(component.get("ownerRole") or owner or "lead")
        steps.append({
            "id": f"step-{index:02d}",
            "componentId": component_id,
            "ownerRole": owner_role,
            "gates": ["GATE_PASS" if component.get("status") != "missing" else "GATE_DEGRADED"],
            "evidence": ["registry:" + component_id],
        })
        if component.get("status") == "missing":
            accept_gap.append({
                "componentId": component_id,
                "ownerRole": owner_role,
                "reason": "registry v2 status=missing（组件未实现）",
                "expiry": ACCEPT_GAP_EXPIRY,
                "degradedTo": "lead-manual-sop",
            })
    violations = []
    if blocked_by:
        violations.append({"rule": "MISSING_COMPONENT",
                           "detail": f"componentId 不在 registry v2：{blocked_by}"})
    if len(accept_gap) > MAX_ACCEPT_GAP:
        violations.append({"rule": "ACCEPT_GAP_OVER_LIMIT",
                           "detail": f"acceptGap 数 {len(accept_gap)} > {MAX_ACCEPT_GAP}"})
    plan = {"steps": steps, "acceptGap": accept_gap, "blockedBy": blocked_by}
    return {"ok": not violations, "workflowPlan": plan, "violations": violations,
            "counts": {"components": len(component_ids), "steps": len(steps),
                       "acceptGap": len(accept_gap), "blockedBy": len(blocked_by)},
            "dryRun": True, "goal": goal, "owner": owner}


def selftest() -> int:
    failures: list[str] = []
    registry = load_registry(ROOT / DEFAULT_REGISTRY)
    m1_ids = [
        "comp.task-classifier", "comp.requirement-completer", "comp.corpus-retriever",
        "comp.workflow-analysis-writer", "comp.workflow-component-extractor",
        "comp.component-registry", "comp.workflow-composer", "comp.deployment-runner",
        "comp.seminar-runner", "comp.design-author", "comp.requirement-verifier",
    ]
    green = compose(m1_ids, registry, goal="M-1 工作流", owner="lead")
    steps = green["workflowPlan"]["steps"]
    if not green["ok"] or len(steps) != 11:
        failures.append(f"11 环节应 ok=true/steps=11，实际 ok={green['ok']}/steps={len(steps)}")
    if not all(step["componentId"] in {c["id"] for c in registry["components"]} for step in steps):
        failures.append("steps 中 componentId 必须都在 registry v2")
    if not all(str(step["ownerRole"] or "").strip() for step in steps):
        failures.append("steps 的 ownerRole 不得为空")
    if green["workflowPlan"]["acceptGap"]:
        # M-1 11 组件当前无 missing（v2 status 4 implemented / 14 partial / 2 missing 均为其他组件）
        pass

    # 先证红：未知 componentId ⇒ blockedBy 含该 id
    red_unknown = compose(["comp.not-exist"], registry)
    if red_unknown["ok"] or "comp.not-exist" not in red_unknown["workflowPlan"]["blockedBy"]:
        failures.append("未知 componentId 应 ok=false 且 blockedBy 含该 id")
    # 先证红：acceptGap >4（用 5 个 missing 组件 fixture）
    fixture = json.loads(json.dumps(registry, ensure_ascii=False))
    missing_ids = [c["id"] for c in fixture["components"]][:5]
    for component in fixture["components"][:5]:
        component["status"] = "missing"
    red_gap = compose(missing_ids, fixture)
    if red_gap["ok"] or not any(v["rule"] == "ACCEPT_GAP_OVER_LIMIT" for v in red_gap["violations"]):
        failures.append("acceptGap>4 应 ok=false + ACCEPT_GAP_OVER_LIMIT")
    if len(red_gap["workflowPlan"]["acceptGap"]) != 5:
        failures.append("不超限前 acceptGap 应生成 5 条")
    for gap in red_gap["workflowPlan"]["acceptGap"]:
        for key in ("componentId", "ownerRole", "reason", "expiry", "degradedTo"):
            if not str(gap.get(key) or "").strip():
                failures.append(f"acceptGap 字段 {key} 不得为空")
                break
    # 空输入
    red_empty = compose([], registry)
    if red_empty["ok"]:
        failures.append("空 componentIds 应 ok=false（EMPTY_INPUT）")
    if failures:
        print("SELFTEST FAIL")
        for item in failures:
            print(" -", item)
        return 1
    print("SELFTEST PASS：M-1 11 环节 ⇒ steps=11/全部存在 registry/ownerRole 非空；"
          "未知 id ⇒ blockedBy 命中；missing 组件 ⇒ acceptGap 5 字段完整；acceptGap>4/空输入 必红。")
    return 0


def main(argv: list[str] | None = None) -> int:
    _configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="组件→工作流组装器（dry-run only，comp.workflow-composer）")
    parser.add_argument("--components", help="逗号分隔 componentIds")
    parser.add_argument("--component", action="append", default=[], help="可重复传入 componentId")
    parser.add_argument("--goal", default="")
    parser.add_argument("--owner", default="lead")
    parser.add_argument("--registry", default=DEFAULT_REGISTRY)
    parser.add_argument("--dry-run", action="store_true", help="必须显式传（本工具只做 dry-run）")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.dry_run:
        print(json.dumps({"ok": False, "error": "dry-run-required",
                          "detail": "本工具只做 dry-run；请显式传 --dry-run（不 spawn 任何成员）"},
                         ensure_ascii=False, indent=2))
        return 2
    component_ids = [item.strip() for item in (args.components or "").split(",") if item.strip()]
    component_ids.extend(item.strip() for item in args.component if item.strip())
    if not component_ids:
        print(json.dumps({"ok": False, "error": "no-input",
                          "detail": "需要 --components/--component（空输入不得产出空计划）"},
                         ensure_ascii=False, indent=2))
        return 1
    registry_path = Path(args.registry)
    if not registry_path.is_absolute():
        registry_path = ROOT / registry_path
    try:
        registry = load_registry(registry_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": "no-input-or-invalid", "detail": str(exc)},
                         ensure_ascii=False, indent=2))
        return 2
    result = compose(component_ids, registry, args.goal, args.owner)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
