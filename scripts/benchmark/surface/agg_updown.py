# -*- coding: utf-8 -*-
"""W3.2 逐位置第二遍/第一遍聚合器（可复核、可重跑）。

用途：把 `perf_updown_positions.mjs` 落盘的 JSON 聚合成一张逐位置表，
**只使用 harness 的 `rows[].ratio = upMax/downMax` 与绝对 `downMax/upMax`**，
不再引入第二套临时口径（第 90 轮教训：临时聚合脚本必须落盘）。

用法：
    python scripts/benchmark/surface/agg_updown.py <result.json> [<result2.json> ...]
    python scripts/benchmark/surface/agg_updown.py --json out.json <result.json> ...   # 另存聚合 JSON

输出：每个文件一张表（19 位置：down/up 的 max 中位、比值中位、是否 >1.2），
      以及 `keyPositions`（30/50/70/90%）判定与总体 median/p90/超 1.2 位置数。
`--ab` 模式下按 arm 分开聚合（与 harness 的 `summary.ab` 同口径）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _med(xs):
    xs = sorted(x for x in xs if isinstance(x, (int, float)))
    return xs[len(xs) // 2] if xs else None


def _num(x):
    return isinstance(x, (int, float))


def analyze_rounds(rounds):
    if not rounds:
        return None
    npos = len(rounds[0]["rows"])
    per_pos = []
    for i in range(npos):
        ratios = [r["rows"][i]["ratio"] for r in rounds if _num(r["rows"][i].get("ratio"))]
        downs = [r["rows"][i]["downMax"] for r in rounds if _num(r["rows"][i].get("downMax"))]
        ups = [r["rows"][i]["upMax"] for r in rounds if _num(r["rows"][i].get("upMax"))]
        per_pos.append({
            "pct": round(rounds[0]["rows"][i]["frac"] * 100),
            "ratioMed": _med(ratios),
            "downMed": _med(downs),
            "upMed": _med(ups),
        })
    ratios = sorted(x["ratioMed"] for x in per_pos if _num(x["ratioMed"]))
    key = []
    for target in (30, 50, 70, 90):
        row = min(per_pos, key=lambda x: abs(x["pct"] - target))
        key.append({"pct": target, "ratio": row["ratioMed"],
                    "pass": _num(row["ratioMed"]) and row["ratioMed"] <= 1.2,
                    "down": row["downMed"], "up": row["upMed"]})
    return {
        "n": len(rounds),
        "perPos": per_pos,
        "ratioMed": ratios[len(ratios) // 2] if ratios else None,
        "ratioP90": ratios[min(len(ratios) - 1, int(len(ratios) * 0.9))] if ratios else None,
        "over12": [x["pct"] for x in per_pos if _num(x["ratioMed"]) and x["ratioMed"] > 1.2],
        "gate4": sum(1 for k in key if k["pass"]),
        "keyPositions": key,
        "maxUpFrame": max((x["upMed"] for x in per_pos if _num(x["upMed"])), default=None),
        "maxDownFrame": max((x["downMed"] for x in per_pos if _num(x["downMed"])), default=None),
        "heapMax": max((r.get("heap", {}).get("usedMB", 0) for r in rounds), default=None),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("results", nargs="+", help="perf_updown_positions.mjs 产出 JSON")
    ap.add_argument("--json", default="", help="把聚合结果另存为 JSON")
    ap.add_argument("--ab", action="store_true", help="按轮次 arm 分开聚合")
    args = ap.parse_args()

    out = {}
    for path in args.results:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        rounds = d.get("rounds") or []
        print("=" * 78)
        print("文件:", path)
        print("head:", d.get("head"), "| order:", (d.get("summary") or {}).get("order"),
              "| window:", (d.get("summary") or {}).get("windowMs"), "ms",
              "| rAF p50:", (d.get("idleRafBaseline") or {}).get("p50"))
        print("并发:", d.get("concurrencyBefore"), "->", (d.get("summary") or {}).get("concurrency", {}).get("after"))
        groups = {"all": rounds}
        if args.ab:
            groups = {}
            for r in rounds:
                groups.setdefault(r.get("arm") or "?", []).append(r)
        res = {}
        for name, rs in groups.items():
            s = analyze_rounds(rs)
            if not s:
                continue
            res[name] = s
            print("-" * 78)
            print(f"[{name}] n={s['n']} ratioMed={s['ratioMed']} p90={s['ratioP90']} "
                  f"over12={len(s['over12'])} gate4={s['gate4']}/4 "
                  f"maxUp={s['maxUpFrame']} maxDown={s['maxDownFrame']} heapMax={s['heapMax']}MB")
            print("  pct | downMed | upMed | ratio")
            for x in s["perPos"]:
                flag = "  >1.2" if _num(x["ratioMed"]) and x["ratioMed"] > 1.2 else ""
                print(f"  {x['pct']:3d} | {x['downMed']!s:>7} | {x['upMed']!s:>5} | {x['ratioMed']!s:>5}{flag}")
            print("  key:", ", ".join(f"{k['pct']}%={k['ratio']}({'PASS' if k['pass'] else 'FAIL'})" for k in s["keyPositions"]))
        out[path] = res
    if args.json:
        Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print("\n[out]", args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
