#!/usr/bin/env python
"""IAA 执行器：KP span unitizing α / boundary F1 + KP 类型 κ + 语义边 tuple-set F1 + 池一致率。

- unitizing α **直接复用 C0a 的** `scripts/verify/corpus/unitizing_alpha.py`（同一实现，不另写算法）；
- 只处理**两位标注者**：A = 本 pilot 草案；B = 独立第二标注者（`iaa/README.md` 协议）；
- 缺失/样本不足一律返回 null 并显式标注，不默认 0（C8 缺失处理）；
- 无第二标注者数据时 `report` 返回 `status=insufficient_second_annotator` 且 exit 2，
  不伪造任何 IAA 数值。

用法：
  # 1) 生成 unitizing_alpha.py 的输入（用于单独复核 α）
  python scripts/corpus/iaa_runner.py prepare-alpha \
      --kps-a artifacts/corpus/pilot/annotations/kps.single.jsonl \
      --kps-b artifacts/corpus/pilot/iaa/kps-second-annotator.jsonl \
      --out artifacts/corpus/pilot/iaa/unitizing-alpha-input.json

  # 2) 直接用 C0a 脚本算 α
  python scripts/verify/corpus/unitizing_alpha.py \
      --input artifacts/corpus/pilot/iaa/unitizing-alpha-input.json \
      --out artifacts/corpus/pilot/iaa/unitizing-alpha-result.json

  # 3) 生成完整 IAA 报告（α/κ/边 F1/池一致率）
  python scripts/corpus/iaa_runner.py report \
      --kps-a artifacts/corpus/pilot/annotations/kps.single.jsonl \
      --kps-b artifacts/corpus/pilot/iaa/kps-second-annotator.jsonl \
      --edges-a artifacts/corpus/pilot/annotations/edges.single.jsonl \
      --edges-b artifacts/corpus/pilot/iaa/edges-second-annotator.jsonl \
      --pool artifacts/corpus/pilot/iaa/edge-candidate-pool.jsonl \
      --out artifacts/corpus/pilot/iaa/iaa-report.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "verify" / "corpus"
sys.path.insert(0, str(REPO_SCRIPTS))
from unitizing_alpha import unitizing_alpha, UnitizingError  # noqa: E402

THRESHOLDS = {"unitizing_alpha": 0.67, "cohen_kappa": 0.67, "edge_tuple_f1": 0.70}
S0_TYPES = {"contain", "reference", "extend"}


# ---------------------------------------------------------------- 基础指标
def cohen_kappa(pairs: list[tuple[str, str]]) -> dict:
    """两标注者名义类别一致性；样本不足/单类别时 kappa=null（显式）。"""
    n = len(pairs)
    if n == 0:
        return {"kappa": None, "observed_agreement": None, "expected_agreement": None,
                "n": 0, "categories": [], "note": "no_pairs"}
    categories = sorted({a for a, _ in pairs} | {b for _, b in pairs})
    agree = sum(1 for a, b in pairs if a == b) / n
    pa = {c: sum(1 for a, _ in pairs if a == c) / n for c in categories}
    pb = {c: sum(1 for _, b in pairs if b == c) / n for c in categories}
    pe = sum(pa[c] * pb[c] for c in categories)
    if pe >= 1.0:
        kappa = 1.0 if agree == 1.0 else 0.0
        note = "no_expected_disagreement"
    else:
        kappa = (agree - pe) / (1.0 - pe)
    return {"kappa": round(max(-1.0, min(1.0, kappa)), 6),
            "observed_agreement": round(agree, 6),
            "expected_agreement": round(pe, 6),
            "n": n, "categories": categories,
            "category_counts_a": {c: sum(1 for a, _ in pairs if a == c) for c in categories},
            "category_counts_b": {c: sum(1 for _, b in pairs if b == c) for c in categories},
            "note": note if pe >= 1.0 else "ok"}


def tuple_set_f1(gold: set[tuple], pred: set[tuple]) -> dict:
    """边 tuple 集合 F1（type+方向+端点）。缺失端点/自造 tuple 按 FP/FN 计。"""
    tp = len(gold & pred)
    fp = len(pred - gold)
    fn = len(gold - pred)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = None
    if precision is not None and recall is not None and precision + recall > 0:
        f1 = 2 * precision * recall / (precision + recall)
    return {"precision": None if precision is None else round(precision, 6),
            "recall": None if recall is None else round(recall, 6),
            "f1": None if f1 is None else round(f1, 6),
            "tp": tp, "fp": fp, "fn": fn,
            "gold_size": len(gold), "pred_size": len(pred)}


def span_iou(a: dict, b: dict) -> float:
    a0, a1 = a["start"], a["end"]
    b0, b1 = b["start"], b["end"]
    inter = max(0, min(a1, b1) - max(a0, b0))
    union = (a1 - a0) + (b1 - b0) - inter
    return inter / union if union > 0 else 0.0


def match_kp_spans(gold: list[dict], pred: list[dict], min_iou: float = 0.5) -> dict:
    """按 IoU 贪心一对一匹配两个标注者的 KP span（同 section 优先）。"""
    gold_rows = [{"id": k["id"], "span": k["spans"][0], "section": k.get("section_key"),
                  "type": k.get("concept_type")} for k in gold]
    pred_rows = [{"id": k["id"], "span": k["spans"][0], "section": k.get("section_key"),
                  "type": k.get("concept_type")} for k in pred]
    candidates = []
    for g in gold_rows:
        for p in pred_rows:
            if g["section"] and p["section"] and g["section"] != p["section"]:
                continue
            iou = span_iou(g["span"], p["span"])
            if iou >= min_iou:
                candidates.append((iou, g["id"], p["id"]))
    candidates.sort(key=lambda x: (-x[0], x[1], x[2]))
    used_g, used_p = set(), set()
    pairs = []
    for iou, gid, pid in candidates:
        if gid in used_g or pid in used_p:
            continue
        used_g.add(gid)
        used_p.add(pid)
        pairs.append({"gold_id": gid, "second_id": pid, "iou": round(iou, 6)})
    return {
        "pairs": pairs,
        "unmatched_gold": sorted({g["id"] for g in gold_rows} - used_g),
        "unmatched_second": sorted({p["id"] for p in pred_rows} - used_p),
        "gold_count": len(gold_rows), "second_count": len(pred_rows),
        "matched_count": len(pairs),
    }


# ---------------------------------------------------------------- 数据装载
def _load_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("_template"):
            continue
        rows.append(row)
    return rows


def _spans_of(kps: list[dict]) -> list[dict]:
    return [{"start": k["spans"][0]["start"], "end": k["spans"][0]["end"], "label": "kp"}
            for k in kps if k.get("spans")]


def alpha_input(kps_a: list[dict], kps_b: list[dict]) -> dict:
    try:
        annotations = [_spans_of(kps_a), _spans_of(kps_b)]
        result = unitizing_alpha(annotations)
    except UnitizingError as exc:
        return {"annotations": [[], []], "error": str(exc)}
    return {"schema": "unitizing-alpha-input/v1",
            "note": "label 统一为 'kp'：本指标只测 unitizing/边界，不测类别；类别一致性用 κ。",
            "annotations": annotations,
            "computed": result}


def edge_tuple_set(rows: list[dict], positive_field: str = "label") -> set[tuple]:
    out = set()
    for row in rows:
        if row.get("label") not in ("edge", "positive", True) and not row.get("type"):
            continue
        etype = row.get("type")
        if etype not in S0_TYPES:
            continue
        source, target = row.get("source"), row.get("target")
        if not source or not target:
            continue
        direction = row.get("direction") or "source->target"
        out.add((etype, source, target, direction))
    return out


def pair_presence(rows: list[dict]) -> set[frozenset]:
    out = set()
    for row in rows:
        if row.get("label") in ("edge", "positive", True) or row.get("type"):
            source, target = row.get("source"), row.get("target")
            if source and target:
                out.add(frozenset((source, target)))
    return out


# ---------------------------------------------------------------- 报告
def build_report(kps_a: list[dict], kps_b: list[dict], edges_a: list[dict],
                 edges_b: list[dict], pool: list[dict] | None,
                 adjudications: list[dict] | None = None,
                 sections: list[dict] | None = None) -> dict:
    if kps_b:
        alpha_in = alpha_input(kps_a, kps_b)
        alpha = alpha_in.get("computed", {})
    else:
        alpha = {"alpha": None, "observed_disagreement": None, "expected_disagreement": None,
                 "n_units": 0, "n_pairs": 0, "n_annotators": 1, "missing_segments": None,
                 "boundary_f1": None, "labels": [],
                 "note": "insufficient_second_annotator"}
    matching = match_kp_spans(kps_a, kps_b)

    # KP 类型 κ（仅对匹配上且双方都给了 concept_type 的 KP）
    type_pairs = []
    a_by = {k["id"]: k for k in kps_a}
    b_by = {k["id"]: k for k in kps_b}
    for m in matching["pairs"]:
        ta = a_by[m["gold_id"]].get("concept_type")
        tb = b_by[m["second_id"]].get("concept_type")
        if ta and tb:
            type_pairs.append((ta, tb))
    kappa = cohen_kappa(type_pairs) if type_pairs else {
        "kappa": None, "n": 0, "note": "no_second_annotator_types_or_no_matches"}

    gold_tuples = edge_tuple_set(edges_a)
    pred_tuples = edge_tuple_set(edges_b)
    edge_f1 = tuple_set_f1(gold_tuples, pred_tuples)

    pool_agreement = None
    if pool and edges_b:
        gold_pairs = pair_presence(edges_a)
        pred_pairs = pair_presence(edges_b)
        yes_no = []
        for item in pool:
            key = frozenset((item["source"], item["target"]))
            yes_no.append(("edge" if key in gold_pairs else "no_edge",
                           "edge" if key in pred_pairs else "no_edge"))
        pool_agreement = cohen_kappa(yes_no)

    insufficient = len(kps_b) == 0 or len(edges_b) == 0
    status = "insufficient_second_annotator" if insufficient else "computed"
    result = {
        "schema": "corpus-pilot-iaa-report/v1",
        "status": status,
        "thresholds": THRESHOLDS,
        "sample_sizes": {"kp_a": len(kps_a), "kp_b": len(kps_b),
                         "edges_a": len(edges_a), "edges_b": len(edges_b),
                         "pool": len(pool) if pool else 0,
                         "adjudications": len(adjudications) if adjudications else 0},
        "missing_handling": {
            "kp_spans": "未标/空 span 不入 α 分母；缺失段数由 unitizing_alpha 报告",
            "kp_types": "仅统计双方都有 concept_type 且 span IoU>=0.5 的匹配对",
            "edges": "未裁决冲突不计 TP；缺端点计 FP/FN",
            "pool": "池外边（extra-*）计入 pred；池由 A 候选构造，recall 仅池内可估",
        },
        "kp_span_unitizing_alpha": alpha or {"alpha": None, "note": "not_computed"},
        "kp_span_matching": matching,
        "kp_type_cohen_kappa": kappa,
        "edge_tuple_f1": edge_f1,
        "edge_pool_agreement_kappa": pool_agreement,
        "per_section_alpha": {},
        "pass": {
            "kp_span_alpha": bool(alpha.get("alpha") is not None
                                  and alpha["alpha"] >= THRESHOLDS["unitizing_alpha"]),
            "kp_type_kappa": bool(kappa.get("kappa") is not None
                                  and kappa["kappa"] >= THRESHOLDS["cohen_kappa"]),
            "edge_tuple_f1": bool(edge_f1.get("f1") is not None
                                  and edge_f1["f1"] >= THRESHOLDS["edge_tuple_f1"]),
        },
        "adjudication_agreement": None,
    }
    if adjudications:
        judged = [r for r in adjudications if r.get("decision")]
        agreed = [r for r in judged if r.get("decision") in ("accept", "confirmed", "pass")]
        result["adjudication_agreement"] = {
            "n": len(judged),
            "consistent": len(agreed),
            "rate": round(len(agreed) / len(judged), 6) if judged else None,
        }
    # 分 section α（可选；sections.json 提供 page 区间）
    if sections and alpha.get("alpha") is not None:
        by_sec = []
        for sec in sections:
            a_spans = [s for s in _spans_of(kps_a) if sec["start"] <= s["start"] < sec["end"]]
            b_spans = [s for s in _spans_of(kps_b) if sec["start"] <= s["start"] < sec["end"]]
            if not a_spans and not b_spans:
                continue
            try:
                by_sec.append({"section_key": sec["page_id"],
                               **unitizing_alpha([a_spans, b_spans])})
            except UnitizingError as exc:
                by_sec.append({"section_key": sec["page_id"], "alpha": None, "note": str(exc)})
        result["per_section_alpha"] = {r["section_key"]: r for r in by_sec}
    return result


# ---------------------------------------------------------------- 自检
def _fixture(perfect: bool) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    a = [{"id": "kp-a", "spans": [{"start": 0, "end": 10}], "concept_type": "concept",
          "section_key": "s1"},
         {"id": "kp-b", "spans": [{"start": 12, "end": 22}], "concept_type": "term",
          "section_key": "s1"},
         {"id": "kp-c", "spans": [{"start": 24, "end": 34}], "concept_type": "concept",
          "section_key": "s1"}]
    b = [dict({k: v for k, v in row.items()}) for row in a]
    if not perfect:
        b[0]["spans"] = [{"start": 0, "end": 8}]
        b[0]["concept_type"] = "term"
    edges_a = [{"id": "edge-a", "label": "semantic", "type": "contain", "source": "kp-a",
                "target": "kp-b", "direction": "source->target"},
               {"id": "edge-b", "label": "semantic", "type": "reference", "source": "kp-b",
                "target": "kp-c", "direction": "source->target"}]
    edges_b = [dict(e) for e in edges_a] if perfect else [dict(edges_a[0])]
    return a, b, edges_a, edges_b


def self_test() -> dict:
    a, b, ea, eb = _fixture(True)
    perfect = build_report(a, b, ea, eb, pool=None)
    a2, b2, ea2, eb2 = _fixture(False)
    broken = build_report(a2, b2, ea2, eb2, pool=None)
    ok = (perfect["kp_span_unitizing_alpha"].get("alpha") == 1.0
          and perfect["kp_type_cohen_kappa"].get("kappa") == 1.0
          and perfect["edge_tuple_f1"].get("f1") == 1.0
          and broken["edge_tuple_f1"]["f1"] is not None and broken["edge_tuple_f1"]["f1"] < 1.0
          and broken["kp_type_cohen_kappa"]["kappa"] is not None
          and broken["kp_type_cohen_kappa"]["kappa"] < 1.0)
    return {"ok": ok, "perfect": {k: perfect[k] for k in
                                  ("kp_span_unitizing_alpha", "kp_type_cohen_kappa",
                                   "edge_tuple_f1")},
            "disagreement": {k: broken[k] for k in
                             ("kp_span_unitizing_alpha", "kp_type_cohen_kappa",
                              "edge_tuple_f1")}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Corpus pilot IAA runner")
    ap.add_argument("command", choices=["prepare-alpha", "report", "self-test"])
    ap.add_argument("--kps-a", default="artifacts/corpus/pilot/annotations/kps.single.jsonl")
    ap.add_argument("--kps-b", default="artifacts/corpus/pilot/iaa/kps-second-annotator.jsonl")
    ap.add_argument("--edges-a", default="artifacts/corpus/pilot/annotations/edges.single.jsonl")
    ap.add_argument("--edges-b", default="artifacts/corpus/pilot/iaa/edges-second-annotator.jsonl")
    ap.add_argument("--pool", default="artifacts/corpus/pilot/iaa/edge-candidate-pool.jsonl")
    ap.add_argument("--adjudications", default="artifacts/corpus/pilot/iaa/adjudication-log.jsonl")
    ap.add_argument("--sections", default="artifacts/corpus/pilot/source/sections.json")
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)
    try:
        if args.command == "self-test":
            res = self_test()
            print(json.dumps(res, ensure_ascii=False, indent=2))
            return 0 if res["ok"] else 1

        kps_a = _load_jsonl(Path(args.kps_a))
        kps_b_path = Path(args.kps_b)
        kps_b = _load_jsonl(kps_b_path) if kps_b_path.exists() else []
        if args.command == "prepare-alpha":
            if not kps_b:
                print(json.dumps({"ok": False, "error": "insufficient_second_annotator",
                                  "message": f"第二标注者文件缺失/为空: {kps_b_path}"},
                                 ensure_ascii=False), file=sys.stderr)
                return 2
            res = alpha_input(kps_a, kps_b)
            if "error" in res:
                print(json.dumps({"ok": False, "error": res["error"]}, ensure_ascii=False),
                      file=sys.stderr)
                return 1
            payload = {"schema": res["schema"], "note": res["note"],
                       "annotations": res["annotations"]}
            if args.out:
                out = Path(args.out)
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8", newline="\n")
            print(json.dumps({"ok": True, "annotations": [len(x) for x in payload["annotations"]],
                              "alpha_preview": res["computed"]}, ensure_ascii=False, indent=2))
            return 0

        edges_a = _load_jsonl(Path(args.edges_a))
        edges_b_path = Path(args.edges_b)
        edges_b = _load_jsonl(edges_b_path) if edges_b_path.exists() else []
        pool = _load_jsonl(Path(args.pool)) if Path(args.pool).exists() else []
        adjs = _load_jsonl(Path(args.adjudications)) if Path(args.adjudications).exists() else []
        sections_doc = json.loads(Path(args.sections).read_text(encoding="utf-8")) \
            if Path(args.sections).exists() else None
        sections = sections_doc["sections"] if sections_doc else None
        report = build_report(kps_a, kps_b, edges_a, edges_b, pool, adjs, sections)
        if args.out:
            out = Path(args.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8", newline="\n")
        print(json.dumps({"status": report["status"], "sample_sizes": report["sample_sizes"],
                          "pass": report["pass"]}, ensure_ascii=False, indent=2))
        return 2 if report["status"] == "insufficient_second_annotator" else 0
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": type(exc).__name__, "message": str(exc)},
                         ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
