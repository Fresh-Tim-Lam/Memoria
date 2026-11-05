#!/usr/bin/env python
"""标注一致性：Krippendorff **unitizing α**（span/边界/重叠/缺失）。

为什么需要它（C0a / C8 / R-C0-1）：
- KP 是 **span**（start/end），不是二分类；Cohen/Fleiss κ 不能处理边界与重叠。
- 本实现把全部标注者的 span 边界切成原子区间（unitizing），逐区间比较标签；
  缺失段不强行记 0，而是从观测/期望分母中排除，并显式报告缺失数。

输出：
  alpha / observed_disagreement / expected_disagreement /
  n_units / n_pairs / missing_segments / boundary_f1 / labels

CLI：
  python scripts/verify/corpus/unitizing_alpha.py --input annotations.json --out result.json
  python scripts/verify/corpus/unitizing_alpha.py --self-test
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

MISSING = "__MISSING__"


class UnitizingError(ValueError):
    pass


def _validate_span(span: dict) -> tuple[int, int, str]:
    if not isinstance(span, dict):
        raise UnitizingError("span 必须是对象")
    start, end, label = span.get("start"), span.get("end"), span.get("label")
    if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
        raise UnitizingError(f"非法 span 边界：{span!r}")
    if not isinstance(label, str) or not label:
        raise UnitizingError(f"span 缺 label：{span!r}")
    return start, end, label


def _normalize(annotations: Sequence[Sequence[dict]]) -> list[list[tuple[int, int, str]]]:
    if not isinstance(annotations, list) or len(annotations) < 2:
        raise UnitizingError("unitizing α 至少需要 2 名标注者")
    out: list[list[tuple[int, int, str]]] = []
    for idx, spans in enumerate(annotations):
        if not isinstance(spans, list):
            raise UnitizingError(f"标注者 {idx} 的 spans 必须是数组")
        rows = [_validate_span(s) for s in spans]
        rows.sort(key=lambda x: (x[0], x[1]))
        for a, b in zip(rows, rows[1:]):
            if b[0] < a[1]:
                raise UnitizingError(f"标注者 {idx} 存在重叠 span：{a} / {b}（同一标注者不得重叠）")
        out.append(rows)
    if not any(out):
        raise UnitizingError("没有任何 span，无法计算 α")
    return out


def _boundaries(rows: list[list[tuple[int, int, str]]]) -> list[int]:
    pts = {0}
    for spans in rows:
        for s, e, _ in spans:
            pts.add(s)
            pts.add(e)
    return sorted(pts)


def _label_at(spans: list[tuple[int, int, str]], start: int, end: int) -> str:
    for s, e, lab in spans:
        if s <= start and end <= e:
            return lab
    return MISSING


def _boundary_f1(rows: list[list[tuple[int, int, str]]]) -> float | None:
    """边界点集合的成对 F1（start/end 点，多标注者对均值）。"""
    sets = [{(s, "s") for s, _, _ in spans} | {(e, "e") for _, e, _ in spans} for spans in rows]
    vals: list[float] = []
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            a, b = sets[i], sets[j]
            if not a and not b:
                continue
            tp = len(a & b)
            p = tp / len(a) if a else 0.0
            r = tp / len(b) if b else 0.0
            vals.append(0.0 if p + r == 0 else 2 * p * r / (p + r))
    return round(sum(vals) / len(vals), 6) if vals else None


def unitizing_alpha(annotations: Sequence[Sequence[dict]]) -> dict:
    """计算 unitizing α；缺失段从成对比较中排除；样本不足时 alpha=None。"""
    rows = _normalize(annotations)
    n = len(rows)
    bounds = _boundaries(rows)
    # 原子区间及每个标注者的标签
    units: list[tuple[int, int, list[str]]] = []
    missing_segments = 0
    for start, end in zip(bounds, bounds[1:]):
        seg_len = end - start
        if seg_len <= 0:
            continue
        labels = [_label_at(spans, start, end) for spans in rows]
        missing_segments += sum(1 for x in labels if x == MISSING)
        units.append((start, end, labels))

    # 观测不一致：仅对至少两个非缺失标签的区间成对计算
    disagree_weight = 0.0
    pair_weight = 0.0
    n_pairs = 0
    for start, end, labels in units:
        seg_len = end - start
        idx = [i for i, x in enumerate(labels) if x != MISSING]
        for a in range(len(idx)):
            for b in range(a + 1, len(idx)):
                n_pairs += 1
                pair_weight += seg_len
                if labels[idx[a]] != labels[idx[b]]:
                    disagree_weight += seg_len
    observed = (disagree_weight / pair_weight) if pair_weight else None

    # 期望不一致：按标注者内标签长度分布（缺失不计）
    label_weights: dict[str, float] = {}
    total_weight = 0.0
    for start, end, labels in units:
        seg_len = end - start
        for x in labels:
            if x == MISSING:
                continue
            label_weights[x] = label_weights.get(x, 0.0) + seg_len
            total_weight += seg_len
    if total_weight:
        probs = [w / total_weight for w in label_weights.values()]
        expected = 1.0 - sum(p * p for p in probs)
    else:
        expected = None

    labels = sorted(label_weights)
    if observed is None:
        alpha = None
        note = "insufficient_pairs"
    elif expected is None or expected <= 0:
        alpha = 1.0 if observed == 0 else 0.0
        note = "no_expected_disagreement"
    else:
        alpha = 1.0 - observed / expected
        note = "ok"

    return {
        "alpha": None if alpha is None else round(max(-1.0, min(1.0, alpha)), 6),
        "observed_disagreement": None if observed is None else round(observed, 6),
        "expected_disagreement": None if expected is None else round(expected, 6),
        "n_units": len(units),
        "n_pairs": n_pairs,
        "n_annotators": n,
        "missing_segments": missing_segments,
        "boundary_f1": _boundary_f1(rows),
        "labels": labels,
        "note": note,
    }


def _fixture(perfect: bool) -> list[list[dict]]:
    # 两个标注者：3 个 span；perfect=True 完全一致；否则标签全部互换。
    a = [{"start": 0, "end": 4, "label": "definition"},
         {"start": 5, "end": 9, "label": "claim"},
         {"start": 10, "end": 15, "label": "example"}]
    b = [dict(s) for s in a]
    if not perfect:
        for s in b:
            s["label"] = {"definition": "example", "claim": "claim", "example": "definition"}[s["label"]]
    return [a, b]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Krippendorff unitizing alpha (span annotations)")
    ap.add_argument("--input", help="JSON: {annotations:[[{start,end,label}...],...]}")
    ap.add_argument("--out", help="结果输出 JSON")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    try:
        if args.self_test:
            good = unitizing_alpha(_fixture(True))
            bad = unitizing_alpha(_fixture(False))
            ok = (good["alpha"] == 1.0 and bad["alpha"] < 0.67
                  and good["observed_disagreement"] == 0.0)
            res = {"ok": ok, "perfect": good, "disagreement": bad}
            print(json.dumps(res, ensure_ascii=False, indent=2))
            return 0 if ok else 1
        if not args.input:
            ap.print_help()
            return 2
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
        res = unitizing_alpha(payload["annotations"])
        res["input_sha256"] = __import__("hashlib").sha256(Path(args.input).read_bytes()).hexdigest()
        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(json.dumps(res, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                                      encoding="utf-8")
        print(json.dumps(res, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:  # noqa: BLE001 —— 可见失败，不静默
        print(json.dumps({"ok": False, "error": type(exc).__name__, "message": str(exc)},
                         ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
