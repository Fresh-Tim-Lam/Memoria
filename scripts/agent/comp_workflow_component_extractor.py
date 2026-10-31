#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分析文本拆分器（comp.workflow-component-extractor，task-270）。

输入：--analysis <md>（TD-08 模板产物，`docs/design/workflow-analysis-template-v0.1.md`）+ --registry v2
输出：{candidates:[{id,version,inputs[],outputs[],preconditions[],failureStates[],implementedBy,status,reuse,namingBasis}],
       unmatched:[{stepId,reason}]}
只读解析：**不写 registry**；候选需人工/评审后才入库。

用法：
    python scripts/agent/comp_workflow_component_extractor.py --analysis <md> [--registry <path>]
    python scripts/agent/comp_workflow_component_extractor.py --selftest
退出码：0=有候选且无 unmatched；1=unmatched/空输入；2=无输入/坏参数。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = "docs/design/component-registry.v2.json"
SAMPLE_ANALYSIS = "artifacts/agent/plugin-design/WORKFLOW-ANALYSIS-M1-v0.1.sample.md"

# COMPONENT-DECOMPOSITION §1 的 11 环节映射（与 TD-08 模板 §2 表一致）
STAGE_COMPONENT_MAP = {
    "S00": "comp.task-classifier",
    "S01": "comp.requirement-completer",
    "S02": "comp.corpus-retriever",
    "S03": "comp.workflow-analysis-writer",
    "S04": "comp.workflow-component-extractor",
    "S05": "comp.component-registry",
    "S06": "comp.workflow-composer",
    "S07": "comp.deployment-runner",
    "S08": "comp.seminar-runner",
    "S09": "comp.design-author",
    "S10": "comp.requirement-verifier",
}
STAGE_IDS = list(STAGE_COMPONENT_MAP)
STAGE_HEADING_RE = re.compile(r"^###\s+(S\d{2})\b\s*(.*)$")
FIELD_RE = re.compile(r"^-\s*(id|name|actor|inputs|outputs|gates|evidence)\s*[:：]\s*(.*)$")


def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _parse_list(text: str) -> list[str]:
    raw = text.strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    return [item.strip().strip("'\"") for item in raw.split(",") if item.strip()]


def parse_analysis(text: str) -> list[dict]:
    stages: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        match = STAGE_HEADING_RE.match(line.strip())
        if match:
            current = {"id": match.group(1), "name": match.group(2).strip(),
                       "actor": "", "inputs": [], "outputs": [], "gates": [], "evidence": []}
            stages.append(current)
            continue
        if current is None:
            continue
        field_match = FIELD_RE.match(line.strip())
        if not field_match:
            continue
        key, value = field_match.group(1), field_match.group(2).strip()
        if key == "id":
            current["id"] = value or current["id"]
        elif key == "name":
            current["name"] = value or current["name"]
        elif key == "actor":
            current["actor"] = value
        elif key in ("inputs", "outputs", "gates", "evidence"):
            current[key] = _parse_list(value)
    return stages


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract(stages: list[dict], registry: dict) -> dict:
    registry_components = {str(c.get("id")): c for c in (registry.get("components") or [])
                           if isinstance(c, dict) and c.get("id")}
    by_stage = {stage["id"]: stage for stage in stages}
    candidates: list[dict] = []
    unmatched: list[dict] = []
    for stage_id in STAGE_IDS:
        component_id = STAGE_COMPONENT_MAP[stage_id]
        stage = by_stage.get(stage_id)
        if stage is None:
            unmatched.append({"stepId": stage_id, "reason": "analysis 缺少该阶段（期望 11 环节之一）"})
            continue
        registry_component = registry_components.get(component_id)
        if registry_component is None:
            unmatched.append({"stepId": stage_id,
                              "reason": f"映射组件 {component_id} 不在 registry v2"})
            continue
        candidates.append({
            "id": component_id,
            "version": str(registry_component.get("version") or "0.1.0"),
            "inputs": stage.get("inputs") or [],
            "outputs": stage.get("outputs") or [],
            "preconditions": stage.get("gates") or [],
            "failureStates": [],
            "implementedBy": {"kind": "missing", "ref": ""},
            "status": "missing",
            "reuse": "complete",
            "namingBasis": f"components-v0.2 §2.1；mapped from {stage_id}（{stage.get('name', '')}）",
        })
    # 未映射的 stage 也进 unmatched
    for stage in stages:
        if stage["id"] not in STAGE_COMPONENT_MAP:
            unmatched.append({"stepId": stage["id"], "reason": "stage id 不在 11 环节映射表"})
    return {"candidates": candidates, "unmatched": unmatched}


def _candidate_complete(candidate: dict) -> bool:
    for key in ("id", "version", "inputs", "outputs", "preconditions",
                "failureStates", "implementedBy", "status", "reuse", "namingBasis"):
        if key not in candidate:
            return False
    return bool(candidate["id"] and candidate["version"] and candidate["inputs"]
                and candidate["outputs"] and candidate["namingBasis"])


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def selftest() -> int:
    failures: list[str] = []
    sample_path = ROOT / SAMPLE_ANALYSIS
    sample_text = sample_path.read_text(encoding="utf-8")
    registry = json.loads((ROOT / DEFAULT_REGISTRY).read_text(encoding="utf-8-sig"))
    registry_sha_before = _sha256(ROOT / DEFAULT_REGISTRY)

    stages = parse_analysis(sample_text)
    if len(stages) != 11:
        failures.append(f"样例 analysis 应解析出 11 阶段，实际 {len(stages)}")
    green = extract(stages, registry)
    if len(green["candidates"]) < 11:
        failures.append(f"candidates 应 >=11，实际 {len(green['candidates'])}")
    if green["unmatched"]:
        failures.append(f"完整 fixture 的 unmatched 应为空，实际 {green['unmatched']}")
    if not all(_candidate_complete(c) for c in green["candidates"]):
        failures.append("候选必填字段完整率应 100%")

    # 先证红：删掉 S10 阶段 ⇒ unmatched 恰含 S10
    red_text = re.sub(r"###\s+S10\b.*\Z", "", sample_text, flags=re.S)
    red_stages = parse_analysis(red_text)
    red = extract(red_stages, registry)
    if {"stepId": "S10"} not in [{k: u[k] for k in ("stepId",)} for u in red["unmatched"]]:
        failures.append(f"删 S10 后 unmatched 应含 S10，实际 {red['unmatched']}")
    if len(red["candidates"]) != 10:
        failures.append(f"删 S10 后 candidates 应为 10，实际 {len(red['candidates'])}")

    # 空输入：无阶段 ⇒ extract 返回全部 unmatched（调用方 exit 1）
    empty = extract([], registry)
    if len(empty["candidates"]) != 0 or len(empty["unmatched"]) != 11:
        failures.append("空 analysis 应 0 candidates + 11 unmatched")

    # 不写 registry
    if _sha256(ROOT / DEFAULT_REGISTRY) != registry_sha_before:
        failures.append("extractor 改动了 registry（违反只读边界）")

    if failures:
        print("SELFTEST FAIL")
        for item in failures:
            print(" -", item)
        return 1
    print("SELFTEST PASS：样例 11 阶段 ⇒ candidates=11、unmatched=[]、必填字段 100%；"
          "删 S10 ⇒ unmatched 含 S10 且 candidates=10（先证红）；空 analysis ⇒ 0 候选+11 unmatched；registry 未被改写。")
    return 0


def main(argv: list[str] | None = None) -> int:
    _configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="分析文本拆分器（comp.workflow-component-extractor，只读）")
    parser.add_argument("--analysis", help="TD-08 analysis markdown 路径")
    parser.add_argument("--registry", default=DEFAULT_REGISTRY)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.analysis:
        print(json.dumps({"ok": False, "error": "no-input", "detail": "需要 --analysis（无输入不得判过）"},
                         ensure_ascii=False, indent=2))
        return 2
    analysis_path = Path(args.analysis)
    if not analysis_path.is_absolute():
        analysis_path = ROOT / analysis_path
    if not analysis_path.is_file():
        print(json.dumps({"ok": False, "error": "no-input-or-invalid",
                          "detail": f"analysis 不存在：{analysis_path}"}, ensure_ascii=False, indent=2))
        return 2
    registry_path = Path(args.registry)
    if not registry_path.is_absolute():
        registry_path = ROOT / registry_path
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": "no-input-or-invalid", "detail": str(exc)},
                         ensure_ascii=False, indent=2))
        return 2
    stages = parse_analysis(analysis_path.read_text(encoding="utf-8-sig"))
    result = extract(stages, registry)
    result["ok"] = bool(result["candidates"]) and not result["unmatched"]
    result["counts"] = {"stages": len(stages), "candidates": len(result["candidates"]),
                        "unmatched": len(result["unmatched"])}
    result["analysis"] = str(analysis_path.relative_to(ROOT)).replace("\\", "/") if analysis_path.is_relative_to(ROOT) else str(analysis_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
