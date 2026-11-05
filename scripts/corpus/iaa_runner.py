#!/usr/bin/env python
"""IAA 执行器：KP span unitizing α / boundary F1 + KP 类型 κ(+raw agreement) + 语义边 tuple-set F1 + 池一致率(有向)。

- unitizing α **直接复用 C0a 的** `scripts/verify/corpus/unitizing_alpha.py`（同一实现，不另写算法）；
- 只处理**两位标注者**：A = 本 pilot 草案；B = 独立第二标注者（`iaa/README.md` 协议）；
- **路径协议**：B 产物统一放 `artifacts/corpus/pilot/annotations/annotator-b/`
  （`kps.annotator-b.jsonl` + `pool-judgments.annotator-b.jsonl`）；
- **有向优先**：候选池一致率以池内列出的 `source->target` 方向为准；B 标反向记 `edge_reverse`
  单列（无向 legacy 版本同时保留，仅作对照）；边 tuple 也按方向归一化；
- 缺失/样本不足一律返回 null 并显式标注，不默认 0（C8 缺失处理）；
- 无第二标注者数据时 `report` 返回 `status=insufficient_second_annotator` 且 exit 2，
  不伪造任何 IAA 数值。

用法：
  # 1) 生成 unitizing_alpha.py 的输入（用于单独复核 α）
  python scripts/corpus/iaa_runner.py prepare-alpha \
      --kps-a artifacts/corpus/pilot/annotations/kps.single.jsonl \
      --kps-b artifacts/corpus/pilot/annotations/annotator-b/kps.annotator-b.jsonl \
      --out artifacts/corpus/pilot/iaa/unitizing-alpha-input.json

  # 2) 直接用 C0a 脚本算 α
  python scripts/verify/corpus/unitizing_alpha.py \
      --input artifacts/corpus/pilot/iaa/unitizing-alpha-input.json \
      --out artifacts/corpus/pilot/iaa/unitizing-alpha-result.json

  # 3) 生成完整 IAA 报告（α/κ+raw/边 F1/有向池一致率/方向反转清单）
  python scripts/corpus/iaa_runner.py report \
      --kps-a artifacts/corpus/pilot/annotations/kps.single.jsonl \
      --kps-b artifacts/corpus/pilot/annotations/annotator-b/kps.annotator-b.jsonl \
      --edges-a artifacts/corpus/pilot/annotations/edges.single.jsonl \
      --edges-b artifacts/corpus/pilot/annotations/annotator-b/pool-judgments.annotator-b.jsonl \
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
    if precision is not None and recall is not None:
        f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
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


def directed_tuples(row: dict) -> list[tuple]:
    """把一条记录规范化为有向 tuple `(type, source, target, "source->target")`。

    B 在候选池上标注时 `direction` 是相对**池内 source/target 顺序**的：
    - `source->target`：原样；
    - `target->source`：交换端点（方向错误不再被无向统计吞掉）；
    - `both`：物化两条有向 tuple（C6：both 必须物化两条有向边）。
    """
    etype = row.get("type")
    if etype not in S0_TYPES:
        return []
    source, target = row.get("source"), row.get("target")
    if not source or not target:
        return []
    direction = row.get("direction") or "source->target"
    if direction == "source->target":
        pairs = [(source, target)]
    elif direction == "target->source":
        pairs = [(target, source)]
    elif direction == "both":
        pairs = [(source, target), (target, source)]
    else:
        return []
    return [(etype, s, t, "source->target") for s, t in pairs]


def edge_tuple_set(rows: list[dict], positive_field: str = "label") -> set[tuple]:
    out: set[tuple] = set()
    for row in rows:
        if row.get("label") not in ("edge", "positive", True) and not row.get("type"):
            continue
        out.update(directed_tuples(row))
    return out


def pair_presence(rows: list[dict]) -> set[frozenset]:
    """无向端点对存在性（legacy，仅用于与旧报告可比；主指标用有向）。"""
    out = set()
    for row in rows:
        if row.get("label") in ("edge", "positive", True) or row.get("type"):
            source, target = row.get("source"), row.get("target")
            if source and target:
                out.add(frozenset((source, target)))
    return out


def pool_agreement(pool: list[dict], edges_a: list[dict], edges_b: list[dict]) -> dict:
    """候选池一致率：**有向**为主 + 无向 legacy 对照 + 方向反转清单。

    有向标签 = 池内列出的方向 `source->target` 上是否有边：
    - A：A 的 edge tuple 中存在 (source,target)（池用 A 的方向构造，故 A 正例=listed 方向）；
    - B：B 的判定 `edge` 且 normalized direction 覆盖 listed 方向 → edge；
          `edge` 但只有反向 → 记为 edge_reverse（方向错误，不计入 listed 方向一致）；
          `no_edge` → no_edge；缺判定 → missing（不默认 0，单列）。
    """
    gold_directed = {(t[1], t[2]) for t in edge_tuple_set(edges_a)}
    undirected_gold = pair_presence(edges_a)
    b_by_pair_id = {r.get("pair_id"): r for r in edges_b if r.get("pair_id")}
    b_by_key = {}
    for row in edges_b:
        if row.get("source") and row.get("target"):
            b_by_key[(row["source"], row["target"])] = row
            b_by_key[(row["target"], row["source"])] = row

    directed_pairs: list[tuple[str, str]] = []
    undirected_pairs: list[tuple[str, str]] = []
    reversals: list[str] = []
    missing: list[str] = []
    extras: list[str] = []
    for item in pool:
        key = (item["source"], item["target"])
        row = b_by_pair_id.get(item.get("pair_id")) or b_by_key.get(key)
        gold_pos = key in gold_directed
        if row is None:
            missing.append(item.get("pair_id") or f"{key[0]}->{key[1]}")
            continue
        tuples = directed_tuples(row)
        b_listed = key in {(t[1], t[2]) for t in tuples}
        b_reverse = (item["target"], item["source"]) in {(t[1], t[2]) for t in tuples}
        if b_listed:
            b_label = "edge"
        elif b_reverse:
            b_label = "edge_reverse"
            reversals.append(item.get("pair_id") or f"{key[0]}->{key[1]}")
        else:
            b_label = "no_edge"
        # 有向一致：listed 方向是否都有边
        directed_pairs.append(("edge" if gold_pos else "no_edge",
                               "edge" if b_label == "edge" else "no_edge"))
        # 无向 legacy：只要任一端点对有边即算 edge
        b_undirected = b_label in ("edge", "edge_reverse")
        undirected_pairs.append(("edge" if frozenset(key) in undirected_gold else "no_edge",
                                 "edge" if b_undirected else "no_edge"))
    pool_keys = {frozenset((i["source"], i["target"])) for i in pool}
    for row in edges_b:
        if row.get("label") in ("edge", "positive", True) or row.get("type"):
            key = frozenset((row.get("source"), row.get("target")))
            if key not in pool_keys:
                extras.append(row.get("pair_id") or f"{row.get('source')}->{row.get('target')}")
    directed = cohen_kappa(directed_pairs)
    undirected = cohen_kappa(undirected_pairs)
    return {
        "directed": {**directed,
                     "n_pool": len(pool),
                     "direction_reversals": reversals,
                     "missing_judgments": missing,
                     "b_extra_pairs": extras},
        "undirected_legacy": {**undirected, "n_pool": len(pool)},
        "n_pool": len(pool),
        "direction_reversal_count": len(reversals),
        "missing_count": len(missing),
        "note": ("directed 为主指标：池内反向端点对（如 A 负例中的反向对）在 undirected "
                 "里会被端点集合误判；undirected 仅用于与旧报告对照，不作门槛。"),
    }


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

    # KP 类型：raw agreement（全量）+ Cohen κ（排除 B 自报 uncertain 的项）
    # 取值为枚举型 concept/term/formula/mechanism/procedure/example；κ 在边际极偏时会退化，
    # 报告同时给 raw agreement 并打 degenerate 标记（P0 修订：concept_type 规则 + 退化说明）。
    type_pairs_all = []
    type_pairs_kappa = []
    uncertain_excluded = 0
    a_by = {k["id"]: k for k in kps_a}
    b_by = {k["id"]: k for k in kps_b}
    for m in matching["pairs"]:
        ta = a_by[m["gold_id"]].get("concept_type")
        b_row = b_by[m["second_id"]]
        tb = b_row.get("concept_type")
        if ta and tb:
            type_pairs_all.append((ta, tb))
            if b_row.get("type_uncertain"):
                uncertain_excluded += 1
            else:
                type_pairs_kappa.append((ta, tb))
    raw_agreement = (sum(1 for a, b in type_pairs_all if a == b) / len(type_pairs_all)
                     if type_pairs_all else None)
    kappa = cohen_kappa(type_pairs_kappa) if type_pairs_kappa else {
        "kappa": None, "n": 0, "note": "no_second_annotator_types_or_no_matches"}
    # 退化判定：expected agreement 很高（类别极偏）或某一类占比 >0.9
    degenerate = False
    if kappa.get("expected_agreement") is not None and kappa.get("n"):
        counts_a = kappa.get("category_counts_a", {})
        max_share = max(counts_a.values()) / kappa["n"] if counts_a else 0
        degenerate = kappa["expected_agreement"] >= 0.95 or max_share >= 0.90
    kappa = {**kappa, "raw_agreement": None if raw_agreement is None else round(raw_agreement, 6),
             "raw_n": len(type_pairs_all),
             "excluded_uncertain": uncertain_excluded,
             "degenerate": degenerate,
             "kappa_note": ("degenerate: 类别极偏导致 κ 不可解释，需同时报告 raw agreement"
                            if degenerate else "ok")}

    gold_tuples = edge_tuple_set(edges_a)
    pred_tuples = edge_tuple_set(edges_b)
    edge_f1 = tuple_set_f1(gold_tuples, pred_tuples)

    pool_stats = pool_agreement(pool, edges_a, edges_b) if (pool and edges_b) else None

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
            "kp_types": ("raw agreement 用全部匹配对；κ 额外排除 B 自报 type_uncertain 的项；"
                         "类别极偏时 κ 退化，报告 degenerate + raw_agreement"),
            "edges": "未裁决冲突不计 TP；缺端点计 FP/FN；direction 相对池内 source/target 归一化",
            "pool": ("有向为主：listed 方向一致才算 edge；反向记 edge_reverse（单列）；"
                     "缺判定记 missing 不默认 0；无向版本仅作 legacy 对照"),
        },
        "kp_span_unitizing_alpha": alpha or {"alpha": None, "note": "not_computed"},
        "kp_span_matching": matching,
        "kp_type_cohen_kappa": kappa,
        "kp_type_raw_agreement": {"raw_agreement": kappa.get("raw_agreement"),
                                  "n": kappa.get("raw_n"), "degenerate": kappa.get("degenerate")},
        "edge_tuple_f1": edge_f1,
        "edge_pool_agreement_kappa": (pool_stats["directed"] if pool_stats else None),
        "edge_pool_agreement_kappa_undirected": (pool_stats["undirected_legacy"]
                                                 if pool_stats else None),
        "edge_pool_direction_reversals": (pool_stats["directed"]["direction_reversals"]
                                          if pool_stats else []),
        "edge_pool_missing_judgments": (pool_stats["directed"]["missing_judgments"]
                                        if pool_stats else []),
        "edge_pool_agreement_note": (pool_stats["note"] if pool_stats else None),
        "per_section_alpha": {},
        "pass": {
            "kp_span_alpha": bool(alpha.get("alpha") is not None
                                  and alpha["alpha"] >= THRESHOLDS["unitizing_alpha"]),
            "kp_type_kappa": bool(kappa.get("kappa") is not None
                                  and kappa["kappa"] >= THRESHOLDS["cohen_kappa"]),
            "edge_tuple_f1": bool(edge_f1.get("f1") is not None
                                  and edge_f1["f1"] >= THRESHOLDS["edge_tuple_f1"]),
            "kp_type_kappa_degenerate": bool(kappa.get("degenerate")),
            "note": ("type κ 退化时必须同时引用 raw_agreement，且不得单独用 κ 宣称类型一致性达线"
                     if kappa.get("degenerate") else "ok"),
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
    # 有向池一致率自检：B 把方向写反 → directed 必须判不一致，undirected 仍为一致。
    pool = [{"pair_id": "pair-001", "source": "kp-a", "target": "kp-b"}]
    reversed_b = [{"pair_id": "pair-001", "label": "edge", "type": "contain",
                   "source": "kp-a", "target": "kp-b", "direction": "target->source"}]
    directed = build_report(a, b, ea, reversed_b, pool=pool)
    directed_ok = (directed["edge_pool_agreement_kappa"]["observed_agreement"] == 0.0
                   and directed["edge_pool_agreement_kappa_undirected"]["observed_agreement"] == 1.0
                   and directed["edge_pool_direction_reversals"] == ["pair-001"])
    ok = (perfect["kp_span_unitizing_alpha"].get("alpha") == 1.0
          and perfect["kp_type_cohen_kappa"].get("kappa") == 1.0
          and perfect["edge_tuple_f1"].get("f1") == 1.0
          and broken["edge_tuple_f1"]["f1"] is not None and broken["edge_tuple_f1"]["f1"] < 1.0
          and broken["kp_type_cohen_kappa"]["kappa"] is not None
          and broken["kp_type_cohen_kappa"]["kappa"] < 1.0
          and directed_ok)
    return {"ok": ok,
            "perfect": {k: perfect[k] for k in
                        ("kp_span_unitizing_alpha", "kp_type_cohen_kappa", "edge_tuple_f1")},
            "disagreement": {k: broken[k] for k in
                             ("kp_span_unitizing_alpha", "kp_type_cohen_kappa", "edge_tuple_f1")},
            "directed_pool": {"directed": directed["edge_pool_agreement_kappa"],
                              "undirected_legacy": directed["edge_pool_agreement_kappa_undirected"],
                              "reversals": directed["edge_pool_direction_reversals"]}}


def build_parser() -> argparse.ArgumentParser:
    """CLI 定义（测试也用它验证 P0-6 的 canonical 默认路径）。"""
    ap = argparse.ArgumentParser(description="Corpus pilot IAA runner")
    ap.add_argument("command", choices=["prepare-alpha", "report", "self-test"])
    ap.add_argument("--kps-a", default="artifacts/corpus/pilot/annotations/kps.single.jsonl")
    # P0-6 路径协议：B 的产物统一放 annotations/annotator-b/（见 iaa/README.md §1）
    ap.add_argument("--kps-b",
                    default="artifacts/corpus/pilot/annotations/annotator-b/kps.annotator-b.jsonl")
    ap.add_argument("--edges-a", default="artifacts/corpus/pilot/annotations/edges.single.jsonl")
    ap.add_argument("--edges-b",
                    default="artifacts/corpus/pilot/annotations/annotator-b/pool-judgments.annotator-b.jsonl")
    ap.add_argument("--pool", default="artifacts/corpus/pilot/iaa/edge-candidate-pool.jsonl")
    ap.add_argument("--adjudications",
                    default="artifacts/corpus/pilot/annotations/annotator-b/adjudication-log.jsonl")
    ap.add_argument("--sections", default="artifacts/corpus/pilot/source/sections.json")
    ap.add_argument("--out", default="")
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
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
