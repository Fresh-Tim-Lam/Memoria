#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""组件复用判定器（comp.component-reuse-judge，task-263）。

判定来源：`COMPONENT-DECOMPOSITION-v0.1.md §3/§4`（复用/完善/新建三栏 + 锚点=组件 id 或文档 §）。
依赖：TD-01（`comp_naming_convention`）、TD-02（`comp_component_registry.load_registry`，加载前先校验）。

用法：
    python scripts/agent/comp_component_reuse_judge.py --candidates <json> [--registry <path>]
    python scripts/agent/comp_component_reuse_judge.py --selftest

输出（stdout JSON）：
    {"ok": bool,
     "decisions": [{"componentId","decision":"reuse|complete|new","matchedId":str|null,
                    "anchor":str,"reason":str}],
     "coverageGaps": [{"componentId","reason"}],
     "summary": {"total","reuse","complete","new","coverageGaps"},
     "violations": [...]}
退出码：0=全过；1=有 violation（无 anchor/非法 anchor/空输入/非法 decision）；2=无输入/用法错误。
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

def _configure_utf8_stdio() -> None:
    """管道/重定向下 stdout 可能是 cp1252 等非 UTF-8 编码：统一转 UTF-8，避免全角字符 traceback。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _utf8_stdio_probe() -> bool:
    """selftest 内部断言：对自身输出做 UTF-8 写入不抛异常（防回归）。"""
    try:
        sys.stdout.write("UTF-8 探针：✓\n")
        sys.stdout.flush()
    except (UnicodeEncodeError, UnicodeDecodeError):
        return False
    return (sys.stdout.encoding or "").lower().replace("-", "") == "utf8"


_configure_utf8_stdio()

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from comp_component_registry import RegistryInvalid, UnknownComponent, load_registry
    from comp_naming_convention import ValidationError
except Exception as exc:  # pragma: no cover
    print(json.dumps({"ok": False, "error": "DEPS_UNAVAILABLE", "detail": str(exc)},
                     ensure_ascii=False, indent=2))
    raise SystemExit(2)

DEFAULT_REGISTRY = "docs/design/component-registry.v1.json"
DECISIONS = {"reuse", "complete", "new"}
SIMILARITY_THRESHOLD = 0.72
ANCHOR_ID_RE = re.compile(r"^component:(comp\.[a-z0-9]+(-[a-z0-9]+)*)$")
ANCHOR_DOC_RE = re.compile(r"^doc:([^\s#]+)(?:#(.+))?$")


def _norm_text(component: dict) -> str:
    parts = [str(component.get("name") or ""), str(component.get("summary") or "")]
    for field in ("inputs", "outputs"):
        for item in component.get(field) or []:
            if isinstance(item, dict):
                parts.append(str(item.get("name") or ""))
                parts.append(str(item.get("type") or ""))
    return re.sub(r"\s+", "", " ".join(parts).lower())


def _similarity(a: dict, b: dict) -> float:
    return difflib.SequenceMatcher(None, _norm_text(a), _norm_text(b)).ratio()


def _match_candidate(candidate: dict, registry_components: list[dict]) -> tuple[dict | None, float]:
    best, score = None, 0.0
    for comp in registry_components:
        s = _similarity(candidate, comp)
        if s > score:
            best, score = comp, s
    return best, score


def _anchor_exists(anchor: str, registry_ids: set[str]) -> bool:
    m = ANCHOR_ID_RE.match(anchor)
    if m:
        return m.group(1) in registry_ids
    m = ANCHOR_DOC_RE.match(anchor)
    if m:
        target = ROOT / m.group(1).replace("\\", "/")
        return target.is_file()
    return False


def _candidate_anchor(candidate: dict) -> tuple[bool, str]:
    """返回 (anchor_key_present, anchor_value)。"""
    if "anchor" in candidate:
        value = candidate.get("anchor")
        return True, "" if value is None else str(value).strip()
    return False, ""


def judge(candidates: list[dict], registry: dict) -> dict:
    components = [c for c in (registry.get("components") or []) if isinstance(c, dict)]
    registry_ids = {str(c.get("id")) for c in components if c.get("id")}
    by_id = {str(c.get("id")): c for c in components if c.get("id")}
    decisions: list[dict] = []
    violations: list[dict] = []
    coverage_gaps: list[dict] = []

    if not candidates:
        return {"ok": False, "decisions": [], "coverageGaps": [],
                "summary": {"total": 0, "reuse": 0, "complete": 0, "new": 0, "coverageGaps": 0},
                "violations": [{"componentId": None, "rule": "EMPTY_INPUT",
                                "detail": "candidates 为空：空输入不得判过"}]}

    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            violations.append({"componentId": None, "rule": "BAD_CANDIDATE",
                               "detail": f"candidates[{index}] 不是对象"})
            continue
        cid = candidate.get("id")
        anchor_present, anchor = _candidate_anchor(candidate)
        requested = candidate.get("requestedDecision")
        if requested is not None and requested not in DECISIONS:
            violations.append({"componentId": cid, "rule": "BAD_REQUESTED_DECISION",
                               "detail": f"requestedDecision={requested!r} 不在 {sorted(DECISIONS)}"})
            continue

        # ① 显式 anchor：component:<id> 或 doc:<path>#<§>（reuse/complete 必须可核对）
        if anchor_present:
            if not anchor:
                violations.append({"componentId": cid, "rule": "EMPTY_ANCHOR",
                                   "detail": "reuse/complete 不允许空 anchor（禁止「相似但未核对」）"})
                continue
            if not _anchor_exists(anchor, registry_ids):
                violations.append({"componentId": cid, "rule": "INVALID_ANCHOR",
                                   "detail": f"anchor 指向不存在的组件/文档：{anchor}"})
                continue
            m = ANCHOR_ID_RE.match(anchor)
            matched_id = m.group(1) if m else None
            if matched_id:
                matched = by_id.get(matched_id) or {}
                decision = "reuse" if matched.get("status") == "implemented" else "complete"
                reason = (f"显式 anchor 指向现有组件 {matched_id}；"
                          f"其 status={matched.get('status')!r} ⇒ {decision}")
                decisions.append({"componentId": cid, "decision": decision,
                                  "matchedId": matched_id, "anchor": anchor, "reason": reason})
            else:
                decisions.append({"componentId": cid, "decision": "reuse", "matchedId": None,
                                  "anchor": anchor, "reason": "显式 anchor 指向现成文档/§，判定为可复用"})
            continue

        # ② 自匹配：id 精确命中 registry ⇒ complete（已存在，不是新建；17/17 的验收规则）
        exact = by_id.get(str(cid)) if cid else None
        if exact is not None:
            decisions.append({"componentId": cid, "decision": "complete", "matchedId": str(cid),
                              "anchor": f"component:{cid}",
                              "reason": "id 精确命中 registry（自匹配）⇒ complete（已有此组件，非新建）"})
            continue

        # ③ 相似匹配 ⇒ complete（“现有组件改名/语义等价”）
        best, score = _match_candidate(candidate, components)
        if best is not None and score >= SIMILARITY_THRESHOLD:
            matched_id = str(best.get("id"))
            decisions.append({"componentId": cid, "decision": "complete", "matchedId": matched_id,
                              "anchor": f"component:{matched_id}",
                              "reason": f"语义相似度 {score:.3f} ≥ {SIMILARITY_THRESHOLD} ⇒ 归入现有组件"
                                        f" {matched_id} 的完善项（不新建）"})
            continue

        # ④ 无匹配 ⇒ new（记录 coverage gap；anchor 记为 no-match 供核对）
        decisions.append({"componentId": cid, "decision": "new", "matchedId": None,
                          "anchor": "new:no-match",
                          "reason": f"候选与 registry 全部组件最高相似度 {score:.3f} < {SIMILARITY_THRESHOLD} "
                                    f"⇒ 判定为新建（写 coverageGaps 供人复核）"})
        coverage_gaps.append({"componentId": cid,
                              "reason": f"无现有组件覆盖（最高相似度 {score:.3f}）"})

    summary = {"total": len(decisions), "reuse": 0, "complete": 0, "new": 0,
               "coverageGaps": len(coverage_gaps)}
    for decision in decisions:
        if decision["decision"] in summary:
            summary[decision["decision"]] += 1
    # 输出契约：decision 三值、reuse/complete 必须有 anchor
    for decision in decisions:
        if decision["decision"] not in DECISIONS:
            violations.append({"componentId": decision["componentId"], "rule": "BAD_DECISION",
                               "detail": decision["decision"]})
        if decision["decision"] in ("reuse", "complete") and not decision.get("anchor"):
            violations.append({"componentId": decision["componentId"], "rule": "EMPTY_ANCHOR",
                               "detail": "reuse/complete 缺 anchor"})
    return {"ok": not violations, "decisions": decisions, "coverageGaps": coverage_gaps,
            "summary": summary, "violations": violations}


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def selftest() -> int:
    failures: list[str] = []
    if not _utf8_stdio_probe():
        failures.append("UTF-8 输出探针失败：管道下 stdout 不是 UTF-8（全角字符会 traceback）")
    registry = load_registry(DEFAULT_REGISTRY)
    comps = registry["components"]

    # ① 用 registry 自身 17 条当 candidates ⇒ 0 new、17 complete（自匹配规则）
    self_result = judge(comps, registry)
    if not self_result["ok"]:
        failures.append("self-match: 不应有 violation")
    if self_result["summary"]["new"] != 0:
        failures.append(f"self-match: new 应为 0，实际 {self_result['summary']['new']}")
    if self_result["summary"]["complete"] != len(comps):
        failures.append(f"self-match: complete 应={len(comps)}，实际 {self_result['summary']['complete']}")
    if any(d["anchor"] != f"component:{d['componentId']}" for d in self_result["decisions"]):
        failures.append("self-match: 每条 anchor 应指向自身 component:<id>")

    # ② 现有组件改名 ⇒ complete 且 anchor 指向现 id
    renamed = json.loads(json.dumps(comps[0], ensure_ascii=False))
    renamed["id"] = "comp.renamed-task-classifier"
    renamed_result = judge([renamed], registry)
    renamed_decision = renamed_result["decisions"][0]
    if renamed_decision["decision"] != "complete":
        failures.append(f"renamed: 应 complete，实际 {renamed_decision['decision']}")
    if renamed_decision["matchedId"] != comps[0]["id"]:
        failures.append(f"renamed: matchedId 应={comps[0]['id']}，实际 {renamed_decision['matchedId']}")
    if renamed_decision["anchor"] != f"component:{comps[0]['id']}":
        failures.append(f"renamed: anchor 应指向现 id，实际 {renamed_decision['anchor']}")

    # ③ 空 anchor 复用候选 ⇒ violation（exit 1）
    empty_anchor = judge([{"id": "comp.empty-anchor", "requestedDecision": "reuse", "anchor": "",
                           "name": "空锚", "summary": "x"}], registry)
    if empty_anchor["ok"] or not any(v["rule"] == "EMPTY_ANCHOR" for v in empty_anchor["violations"]):
        failures.append("empty-anchor: 应 ok=false 且命中 EMPTY_ANCHOR")
    # 无效 anchor ⇒ violation
    bad_anchor = judge([{"id": "comp.bad-anchor", "requestedDecision": "reuse",
                         "anchor": "component:comp.not-exist", "name": "x", "summary": "y"}], registry)
    if bad_anchor["ok"] or not any(v["rule"] == "INVALID_ANCHOR" for v in bad_anchor["violations"]):
        failures.append("bad-anchor: 应 ok=false 且命中 INVALID_ANCHOR")

    # ④ 全新候选 ⇒ new + coverageGaps；decision 三值
    new_candidate = {"id": "comp.brand-new-thing", "name": "全新能力ZZZ", "summary": "完全不同语义QWE",
                     "inputs": [], "outputs": [], "preconditions": [], "failureStates": [],
                     "sideEffects": [], "idempotent": True, "composesWith": [],
                     "implementedBy": {"kind": "missing", "ref": ""}, "status": "missing",
                     "reuse": "new", "matchedExisting": [], "namingBasis": "x"}
    new_result = judge([new_candidate], registry)
    if new_result["decisions"][0]["decision"] != "new":
        failures.append("new-candidate: 应判 new")
    if new_result["summary"]["coverageGaps"] != 1 or len(new_result["coverageGaps"]) != 1:
        failures.append("new-candidate: coverageGaps 计数应为 1")
    if not all(d["decision"] in DECISIONS for d in new_result["decisions"]):
        failures.append("decision 出现了三值之外的取值")

    # ⑤ 空输入 ⇒ FAIL（不得空过）
    empty_result = judge([], registry)
    if empty_result["ok"]:
        failures.append("empty-input: 应 ok=false")

    if failures:
        print("SELFTEST FAIL")
        for item in failures:
            print(" -", item)
        return 1
    print("SELFTEST PASS：自匹配 17/17 complete & 0 new；改名候选 complete 且 anchor 指向现 id；"
          "空 anchor/坏 anchor 必红（exit 1）；全新候选 new + coverageGaps=1；空输入必 FAIL。")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="组件复用判定器（comp.component-reuse-judge）")
    parser.add_argument("--candidates", help="候选组件 JSON（数组，或 {candidates:[...]}）")
    parser.add_argument("--registry", default=DEFAULT_REGISTRY)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.candidates:
        print(json.dumps({"ok": False, "error": "no-input",
                          "detail": "需要 --candidates（无输入不得判过）"}, ensure_ascii=False, indent=2))
        return 2
    try:
        registry = load_registry(args.registry)
    except ValidationError as exc:
        print(json.dumps({"ok": False, "error": "no-input-or-invalid", "detail": str(exc)},
                         ensure_ascii=False, indent=2))
        return 2
    except RegistryInvalid as exc:
        print(json.dumps({"ok": False, "error": "REGISTRY_INVALID", "violations": exc.violations},
                         ensure_ascii=False, indent=2))
        return 1
    candidates_path = Path(args.candidates)
    if not candidates_path.is_absolute():
        candidates_path = ROOT / candidates_path
    try:
        payload = json.loads(candidates_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(json.dumps({"ok": False, "error": "no-input-or-invalid", "detail": str(exc)},
                         ensure_ascii=False, indent=2))
        return 2
    candidates = payload.get("candidates") if isinstance(payload, dict) else payload
    if not isinstance(candidates, list):
        print(json.dumps({"ok": False, "error": "no-input-or-invalid",
                          "detail": "candidates 必须是数组"}, ensure_ascii=False, indent=2))
        return 2
    result = judge(candidates, registry)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
