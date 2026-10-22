# -*- coding: utf-8 -*-
"""task-79 ç»“æžœèšåˆï¼šæŠŠ t79-*.json æŒ‰è‡‚æ±‡æ€»ã€Œå›žæµçŽ‡ / æ·˜æ±°æ¬¡æ•° / å¸§æˆæœ¬ / ä¼˜å…ˆçº§å ç”¨ã€ã€‚

ç”¨æ³•ï¼š
  python scripts/benchmark/surface/_t79_analyze.py --labels v4-r1,v4-r2,voff-r1,voff-r2
  python scripts/benchmark/surface/_t79_analyze.py --glob 't79-v*-r*.json' --out results/t79-summary
"""
from __future__ import annotations

import argparse
import glob
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"


def med(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return round(statistics.median(xs), 2) if xs else None


def pct(xs, p):
    xs = sorted(x for x in xs if isinstance(x, (int, float)))
    if not xs:
        return None
    return round(xs[min(len(xs) - 1, int(len(xs) * p))], 2)


def load(label: str):
    p = RESULTS / f"t79-{label}.json"
    if not p.is_file():
        return None
    return json.loads(p.read_text("utf-8"))


def pos_row(p):
    ws = p.get("workset") or {}
    return {
        "frac": p.get("frac"),
        "max": (p.get("frames") or {}).get("max"),
        "p95": (p.get("frames") or {}).get("p95"),
        "p50": (p.get("frames") or {}).get("p50"),
        "over50": (p.get("frames") or {}).get("over50"),
        "max_frame_ms": (p.get("counters") or {}).get("max_frame_ms"),
        "max_frame_ms_abs": p.get("max_frame_ms_abs"),
        "budget_exceeded": (p.get("counters") or {}).get("budget_exceeded"),
        "mat": ws.get("materialized"),
        "evictTotal": ws.get("evictTotal"),
        "ev": (p.get("events") or {}).get("evict", 0),
        "remat": (p.get("events") or {}).get("remat", 0),
        "back": (p.get("events") or {}).get("back", 0),
        "rebuilds": (p.get("events") or {}).get("rebuilds", 0),
        "batches": (p.get("profile") or {}).get("batches"),
        "settleMs": p.get("settleMs"),
        "tokenDelta": p.get("tokenDelta"),
        "contaminated": bool((p.get("tokenDelta") or 0) > 0 or (p.get("events") or {}).get("rebuilds")),
        "sched_ms": (p.get("sched") or {}).get("ms") or {},
        "sched_exec": (p.get("sched") or {}).get("exec") or {},
        "pkms": (p.get("sched") or {}).get("pkms") or {},
    }


def workload_row(w):
    ev = w.get("events") or {}
    fr = w.get("frames") or {}
    prof = w.get("profile") or {}
    sched = w.get("sched") or {}
    drag = w.get("drag") or w.get("osc") or {}
    before = w.get("before") or {}
    after = w.get("after") or {}
    return {
        "maxMat": drag.get("maxMat"),
        "frames": fr.get("n"),
        "p50": fr.get("p50"),
        "p95": fr.get("p95"),
        "maxFrame": fr.get("max"),
        "maxFrameMsAbs": w.get("max_frame_ms_abs"),
        "over50": fr.get("over50"),
        "over100": fr.get("over100"),
        "ev": ev.get("evict", 0),
        "remat": ev.get("remat", 0),
        "back": ev.get("back", 0),
        "backRate": ev.get("backRatePct"),
        "backDtP50": ev.get("backDtP50"),
        "backDtP95": ev.get("backDtP95"),
        "repeat2": ev.get("repeat2", 0),
        "rebuilds": ev.get("rebuilds", 0),
        "batches": prof.get("batches"),
        "evictBlocks": prof.get("blocks"),
        "evictMs": prof.get("totalMs"),
        "evictMaxMs": prof.get("maxTotalMs"),
        "budget_exceeded": (w.get("counters") or {}).get("budget_exceeded"),
        "exec": (w.get("counters") or {}).get("executed"),
        "sched_ms": sched.get("ms") or {},
        "sched_exec": sched.get("exec") or {},
        "pkms": sched.get("pkms") or {},
        "pk": sched.get("pk") or {},
        "qpk": sched.get("qpk") or {},
        "pressureSchedules": (after.get("pressureSchedules", 0) or 0) - (before.get("pressureSchedules", 0) or 0),
        "pendingSkips": (after.get("pendingSkips", 0) or 0) - (before.get("pendingSkips", 0) or 0),
        "tokenDelta": w.get("tokenDelta"),
        "contaminated": bool((w.get("tokenDelta") or 0) > 0 or (w.get("rebuilds") or 0) > 0),
    }


def summarize_run(run):
    w1d = [pos_row(p) for p in (run.get("w1") or {}).get("down") or []]
    w1u = [pos_row(p) for p in (run.get("w1") or {}).get("up") or []]
    w2 = [workload_row(x) for x in run.get("w2") or []]
    w3 = [workload_row(x) for x in run.get("w3") or []]
    ws = run.get("open", {}).get("stats") or {}
    return {
        "label": run.get("label"),
        "variant": run.get("variant"),
        "threshold": ws.get("pressureScreens"),
        "appjs": (run.get("variantMeta") or {}).get("appjs_sha256"),
        "origin": (run.get("variantMeta") or {}).get("origin"),
        "blocks": ws.get("totalBlocks"),
        "idleP50": (run.get("idleRafBaseline") or {}).get("p50"),
        "visibility": (run.get("visibility") or {}).get("visibility"),
        "w1down": w1d, "w1up": w1u, "w2": w2, "w3": w3,
        "final": run.get("final"),
    }


def arm_of(runs):
    w1all = [r for run in runs for r in run["w1down"]]
    w1d = [r for r in w1all if not r["contaminated"]]
    w2all = [x for run in runs for x in run["w2"]]
    w3all = [x for run in runs for x in run["w3"]]
    w2 = [x for x in w2all if not x["contaminated"]]
    w3 = [x for x in w3all if not x["contaminated"]]
    return {
        "nRuns": len(runs),
        "w1downContaminated": len(w1all) - len(w1d),
        "w2Contaminated": len(w2all) - len(w2),
        "w3Contaminated": len(w3all) - len(w3),
        "w1downMax": med([x["max"] for x in w1d]),
        "w1downMaxP90": pct([x["max"] for x in w1d], 0.9),
        "w1downMaxWorst": max([x["max"] for x in w1d if x["max"] is not None], default=None),
        "w1downP95": med([x["p95"] for x in w1d]),
        "w1downP95P90": pct([x["p95"] for x in w1d], 0.9),
        "w1downMaxFrameMs": med([x["max_frame_ms"] for x in w1d]),
        "w1downMaxFrameMsAbs": max([x["max_frame_ms_abs"] for x in w1d if x["max_frame_ms_abs"] is not None], default=None),
        "w1downOver50": sum(x["over50"] or 0 for x in w1d),
        "w1upMax": med([x["max"] for run in runs for x in run["w1up"] if not x["contaminated"]]),
        "w1upP95": med([x["p95"] for run in runs for x in run["w1up"] if not x["contaminated"]]),
        "w1downBack": sum(x["back"] for x in w1d),
        "w1downEvict": sum(x["ev"] for x in w1d),
        "w1downRebuilds": sum(x["rebuilds"] for x in w1d),
        "w2": compact(w2),
        "w3": compact(w3),
    }


def compact(rows):
    return {
        "n": len(rows),
        "maxMatMed": med([x["maxMat"] for x in rows]),
        "maxMatWorst": max([x["maxMat"] for x in rows if x["maxMat"] is not None], default=None),
        "evMed": med([x["ev"] for x in rows]),
        "backMed": med([x["back"] for x in rows]),
        "backRateMed": med([x["backRate"] for x in rows if x["backRate"] is not None]),
        "backRateWorst": max([x["backRate"] for x in rows if x["backRate"] is not None], default=None),
        "batchesMed": med([x["batches"] for x in rows]),
        "evictMsMed": med([x["evictMs"] for x in rows]),
        "maxFrameMed": med([x["maxFrame"] for x in rows]),
        "maxFrameWorst": max([x["maxFrame"] for x in rows if x["maxFrame"] is not None], default=None),
        "p95Med": med([x["p95"] for x in rows]),
        "maxFrameMsAbs": max([x["maxFrameMsAbs"] for x in rows if x["maxFrameMsAbs"] is not None], default=None),
        "budgetMed": med([x["budget_exceeded"] for x in rows]),
        "pressureSchedMed": med([x["pressureSchedules"] for x in rows]),
        "rebuilds": sum(x["rebuilds"] for x in rows),
        "tokenDelta": sum(x["tokenDelta"] or 0 for x in rows),
        "p1evictMsMed": med([(x["pkms"].get("1|lazy_evict") or 0) for x in rows]),
        "p1evictExecMed": med([(x["pk"].get("1|lazy_evict") or 0) for x in rows]),
        "p1msMed": med([(x["sched_ms"].get("1") or 0) for x in rows]),
        "p3msMed": med([(x["sched_ms"].get("3") or 0) for x in rows]),
        "p1SharePctMed": med([
            (100.0 * (x["sched_ms"].get("1") or 0) / sum((x["sched_ms"].get(k) or 0) for k in x["sched_ms"]))
            if x["sched_ms"] else None for x in rows]),
        "evictP1CountMed": med([(x["pk"].get("1|lazy_evict") or 0) for x in rows]),
        "evictP3CountMed": med([(x["pk"].get("3|lazy_evict") or 0) for x in rows]),
        "matP1CountMed": med([(x["pk"].get("1|lazy_materialize") or 0) for x in rows]),
        "evictJobPerMatJob": med([
            ((x["pk"].get("1|lazy_evict") or 0) / (x["pk"].get("1|lazy_materialize") or 1)) for x in rows]),
    }


def compare_positions(runs_a, runs_b):
    """é€ä½ç½®æ¯”è¾ƒä¸¤è‡‚çš„ frames.max ä¸­ä½æ•°ï¼ˆåŒ probe åºåˆ—ï¼‰ã€‚"""
    da = [r["w1down"] for r in runs_a if r["w1down"]]
    db = [r["w1down"] for r in runs_b if r["w1down"]]
    if not da or not db:
        return None
    n = min(len(da[0]), len(db[0]))
    rows = []
    for i in range(n):
        def clean_vals(runs, key):
            vs = [run[i][key] for run in runs
                  if i < len(run) and not run[i]["contaminated"] and run[i][key] is not None]
            if not vs:  # 全被污染时退回全部样本（并会在打印里看到 ratio 抖动）
                vs = [run[i][key] for run in runs if i < len(run) and run[i][key] is not None]
            return vs
        ma = med(clean_vals(da, "max"))
        mb = med(clean_vals(db, "max"))
        pa = med(clean_vals(da, "p95"))
        pb = med(clean_vals(db, "p95"))
        rows.append({"frac": da[0][i]["frac"], "A": ma, "B": mb,
                     "ratio": round(ma / mb, 3) if ma and mb else None,
                     "p95A": pa, "p95B": pb,
                     "p95ratio": round(pa / pb, 3) if pa and pb else None})
    ratios = [x["ratio"] for x in rows if x["ratio"] is not None]
    return {"rows": rows, "ratioMed": med(ratios), "ratioWorst": max(ratios) if ratios else None,
            "worse10": [x for x in rows if x["ratio"] and x["ratio"] > 1.10],
            "better10": [x for x in rows if x["ratio"] and x["ratio"] < 0.90]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default="", help="é€—å·åˆ†éš”çš„ result label")
    ap.add_argument("--glob", default="", help="é€šé… results ä¸‹çš„ t79 JSON")
    ap.add_argument("--exclude", default="smoke", help="label ä¸­åŒ…å«è¯¥å­ä¸²åˆ™è·³è¿‡")
    ap.add_argument("--out", default=str(RESULTS / "t79-summary"))
    args = ap.parse_args()

    if args.labels:
        labels = [x.strip() for x in args.labels.split(",") if x.strip()]
        files = [RESULTS / f"t79-{x}.json" for x in labels]
    else:
        pat = args.glob or "t79-*.json"
        files = [Path(p) for p in glob.glob(str(RESULTS / pat))]
    runs = []
    for f in files:
        if not f.is_file():
            continue
        if args.exclude and args.exclude in f.stem and not args.labels:
            continue
        runs.append(summarize_run(json.loads(f.read_text("utf-8"))))
    if not runs:
        print("no runs", file=sys.stderr)
        return 2

    by_arm: dict[str, list] = {}
    for r in runs:
        by_arm.setdefault(r["variant"], []).append(r)
    out = {"runs": runs, "arms": {}, "compare": {}}
    for arm, rs in by_arm.items():
        out["arms"][arm] = arm_of(rs)

    def fmt(v):
        return "-" if v is None else str(v)

    print("| arm | runs | thr | W1down max(med/p90/worst) | W1down p95(med) | max_frame_ms(abs) | W2 maxMat(med/worst) | W2 evict(med) | W2 backRate(med/worst) | W2 maxFrame(med/worst) | W3 maxMat(med) | W3 ev/back% | W3 maxFrame(med/worst) | contaminated W1/W2/W3 |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for arm, s in out["arms"].items():
        w2, w3 = s["w2"], s["w3"]
        print(f"| {arm} | {s['nRuns']} | {fmt(by_arm[arm][0]['threshold'])} | "
              f"{fmt(s['w1downMax'])}/{fmt(s['w1downMaxP90'])}/{fmt(s['w1downMaxWorst'])} | {fmt(s['w1downP95'])} | "
              f"{fmt(s['w1downMaxFrameMsAbs'])} | {fmt(w2['maxMatMed'])}/{fmt(w2['maxMatWorst'])} | {fmt(w2['evMed'])} | "
              f"{fmt(w2['backRateMed'])}/{fmt(w2['backRateWorst'])} | {fmt(w2['maxFrameMed'])}/{fmt(w2['maxFrameWorst'])} | "
              f"{fmt(w3['maxMatMed'])} | {fmt(w3['evMed'])}/{fmt(w3['backRateMed'])} | "
              f"{fmt(w3['maxFrameMed'])}/{fmt(w3['maxFrameWorst'])} | "
              f"{s['w1downContaminated']}/{s['w2Contaminated']}/{s['w3Contaminated']} |")

    # å…³é”®æ¯”è¾ƒï¼šV4 vs Voffï¼ˆéš”ç¦» P1 åŽ‹åŠ›å‡çº§ï¼‰ï¼›V4 vs Vpreï¼ˆä¸ŽçœŸå®žä¿®å¤å‰æäº¤ï¼‰
    for a, b in (("V4", "Voff"), ("V4", "Vpre"), ("V3", "V4"), ("V6", "V4")):
        if a in by_arm and b in by_arm:
            c = compare_positions(by_arm[a], by_arm[b])
            if c:
                out["compare"][f"{a}_vs_{b}"] = c
                print(f"\n[{a} vs {b}] W1 down é€ä½ç½® max æ¯”å€¼ (A/B): med={c['ratioMed']} worst={c['ratioWorst']} "
                      f"worse>10%={len(c['worse10'])} better>10%={len(c['better10'])}")
                for row in c["rows"]:
                    if row["ratio"] and (row["ratio"] > 1.10 or row["ratio"] < 0.90):
                        print(f"   @{int(row['frac']*100)}% A={row['A']}ms B={row['B']}ms ratio={row['ratio']}")

    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.with_suffix(".json").write_text(json.dumps(out, ensure_ascii=False, indent=2), "utf-8")
    print("\n[out]", str(outp.with_suffix(".json")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

