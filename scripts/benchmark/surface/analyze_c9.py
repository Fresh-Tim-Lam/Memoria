# -*- coding: utf-8 -*-
"""C9 度量口径**离线复核器**（re-derivation / audit tool）。

用途（也是本次修复的自验工具）：
  取任意一份 raw `satellite surface-probe-raw/*` JSON，按
  `docs/design/benchmark-measurement-protocol.md` 的口径**重算** C9 统计，并与 raw 内
  `verdict` 对照 ⇒ 证明 (a) 统计实现正确；(b) 判据能区分「同一分布的合理波动」与「真实回归」。

两种输入：
  1. **v2 raw**（新探针产物）：含 `measurement.samples`（逐键一行）⇒ 直接重算全部口径；
  2. **v1 raw**（历史 baseline，12 份）：只有 `editsRaw` 的一次性**批量**序列 ⇒
     用 `--legacy-batch` 对"批量口径污染"做诊断，并**演示**旧判据为何不可判。

用法：
    python scripts/benchmark/surface/analyze_c9.py --dir scripts/benchmark/surface/results
    python scripts/benchmark/surface/analyze_c9.py --raw <raw.json> [--json]

口径要点（与协议一致）：
    · 预算判在「每轮 median 的中位数」上（median-of-medians），不判单值也不判 max；
    · 判绿/红之前先看噪声：键间 IQR/median、键间 p95/median、轮间相对极差；
      任一超阈值 ⇒ **inconclusive**（度量状态，不是性能状态）；
    · 一次性连发的批量序列**不得**用最小值冒充单键成本（重复采样的 min 只抬高，偏向变松）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_RESULTS = HERE / "results"

# 必须与 cdp.mjs 的 C9_DEFAULTS 保持一致（协议 §9）
NOISE_DEFAULTS = {
    "maxIqrOverMedian": 0.25,
    "maxP95OverMedian": 1.60,
    "maxRoundSpread": 0.20,
    "minLiveKeys": 20,
}
BUDGET_MS = 16.0


# ─────────────────────────────────────────────────────────────────────────────
# 统计原语（与 cdp.mjs 的 describeSamples 同口径：线性插值分位、IQR/median）
# ─────────────────────────────────────────────────────────────────────────────
def quantile(sorted_v: list[float], q: float):
    if not sorted_v:
        return None
    h = (len(sorted_v) - 1) * q
    lo, hi = int(h // 1), int(-(-h // 1))
    if lo == hi:
        return sorted_v[lo]
    return sorted_v[lo] + (sorted_v[hi] - sorted_v[lo]) * (h - lo)


def describe(arr):
    v = sorted(x for x in arr if isinstance(x, (int, float)))
    if not v:
        return None
    med = quantile(v, 0.5)
    q1, q3 = quantile(v, 0.25), quantile(v, 0.75)
    return {
        "n": len(v),
        "min": v[0],
        "median": med,
        "p95": quantile(v, 0.95),
        "max": v[-1],
        "mean": sum(v) / len(v),
        "q1": q1,
        "q3": q3,
        "iqr": q3 - q1,
        "iqrOverMedian": (q3 - q1) / med if med else None,
        "p95OverMedian": (quantile(v, 0.95) / med) if med else None,
    }


def describe_runs(run_medians):
    v = [x for x in run_medians if isinstance(x, (int, float))]
    if not v:
        return None
    med = quantile(sorted(v), 0.5)
    spread = (max(v) - min(v)) / med if med else None
    return {"R": len(v), "perRoundMedian": v, "median": med, "min": min(v), "max": max(v), "spread": spread}


def decide(per_key: dict, runs: dict, budget: float = BUDGET_MS, noise: dict | None = None) -> dict:
    th = dict(NOISE_DEFAULTS, **(noise or {}))
    if not per_key or not runs:
        return {"decision": "gray", "reasons": ["no-samples"]}
    reasons = []
    if per_key["n"] < th["minLiveKeys"]:
        reasons.append("samples=%s < minLiveKeys=%s" % (per_key["n"], th["minLiveKeys"]))
    if per_key["iqrOverMedian"] is not None and per_key["iqrOverMedian"] > th["maxIqrOverMedian"]:
        reasons.append("IQR/median=%.3f > %.2f" % (per_key["iqrOverMedian"], th["maxIqrOverMedian"]))
    if per_key["p95OverMedian"] is not None and per_key["p95OverMedian"] > th["maxP95OverMedian"]:
        reasons.append("p95/median=%.3f > %.2f" % (per_key["p95OverMedian"], th["maxP95OverMedian"]))
    if runs["spread"] is not None and runs["spread"] > th["maxRoundSpread"]:
        reasons.append("roundSpread=%.3f > %.2f" % (runs["spread"], th["maxRoundSpread"]))
    within = runs["median"] is not None and runs["median"] <= budget
    decision = "gray" if reasons else ("green" if within else "red")
    return {
        "decision": decision,
        "withinBudget": within,
        "medianOfMedians": runs["median"],
        "noiseObserved": {
            "iqrOverMedian": per_key["iqrOverMedian"],
            "p95OverMedian": per_key["p95OverMedian"],
            "roundSpread": runs["spread"],
            "liveKeys": per_key["n"],
            "rounds": runs["R"],
        },
        "reasons": reasons or ["噪声在阈值内，判据可判"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# v2 raw：直接按协议重算
# ─────────────────────────────────────────────────────────────────────────────
def recompute_v2(ev: dict) -> dict:
    m = ev.get("measurement") or {}
    samples = m.get("samples") or []
    rounds = sorted({s.get("round") for s in samples if isinstance(s.get("round"), int)})
    per_round = {}
    for r in rounds:
        rs = [s for s in samples if s.get("round") == r]
        per_round[r] = {
            "keys": len(rs),
            "appendMs": describe([s.get("appendMs") for s in rs]),
            "fromKeyMs": describe([s.get("fromKeyMs") for s in rs]),
        }
    primary_keys = describe([s.get("appendMs") for s in samples])
    control_keys = describe([s.get("fromKeyMs") for s in samples])
    primary_runs = describe_runs([per_round[r]["appendMs"]["median"] for r in rounds if per_round[r]["appendMs"]])
    control_runs = describe_runs([per_round[r]["fromKeyMs"]["median"] for r in rounds if per_round[r]["fromKeyMs"]])
    noise = ((m.get("config") or {}).get("noise")) or ev.get("verdict", {}).get("noise", {}).get("thresholds")
    verdict = decide(primary_keys, primary_runs, ev.get("budgetMs", BUDGET_MS), noise)
    return {
        "kind": "v2-restated",
        "primary": {"metric": "appendMs", "perKey": primary_keys, "rounds": primary_runs},
        "control": {"metric": "fromKeyMs", "perKey": control_keys, "rounds": control_runs,
                    "perKeyMin": min((s.get("fromKeyMs") for s in samples if s.get("fromKeyMs") is not None), default=None)},
        "verdictRestated": verdict,
        "rawVerdict": ev.get("verdict"),
        "agrees": (ev.get("verdict") or {}).get("decision") == verdict["decision"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# v1 raw：批量序列诊断（历史 baseline）
# ─────────────────────────────────────────────────────────────────────────────
def diagnose_legacy_batch(ev: dict) -> dict:
    """旧 raw 只有一次性连发的序列。此处**证明**旧判据不可判，并量化批量污染。"""
    edits = ev.get("editsRaw") or ev.get("edits") or []
    fk = [e.get("fromKeyMs") for e in edits if isinstance(e.get("fromKeyMs"), (int, float))]
    if not fk:
        return {"error": "no fromKeyMs"}
    cold, live = fk[0], fk[1:]                    # 第 1 键承担冷启动
    d = describe(live)
    s = sorted(live, reverse=True)
    top3 = sum(s[:3]) / 3.0
    rest = sum(s[3:]) / max(1, len(s) - 3)
    # 旧判据（max <= 16）与契约（median <= 16）分别作用在同一批数据上
    old_pass = d["max"] <= 16
    contract_pass = d["median"] <= 16
    # 「按旧判据」的批量口径若用 min 冒充单键成本（错误做法）会得到什么
    misused_min = min(live)
    return {
        "kind": "v1-legacy-batch",
        "n": len(fk),
        "coldFirstKeyMs": cold,
        "batch": d,
        "top3OverRest": top3 / rest if rest else None,
        "top1OverMedian": s[0] / d["median"] if d["median"] else None,
        "oldCriterion_maxLE16": old_pass,
        "contractCriterion_medianLE16": contract_pass,
        "misusedPerKeyMin": misused_min,
        "note": "一次性连发 ⇒ 这批数字是**批量**时延；min 不是单键成本估计（重复采样取 min 只抬高）。",
    }


def load_raw(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def analyze_file(p: Path) -> dict:
    raw = load_raw(p)
    ev = ((raw.get("cases") or {}).get("sel_scroll_stress") or {}).get("evidence") or {}
    if not ev:
        return {"file": p.name, "skip": "no C9 evidence"}
    label = p.name.replace("raw-", "").replace(".json", "")
    if (ev.get("measurement") or {}).get("samples") is not None:
        out = recompute_v2(ev)
    elif ev.get("keyToSource") or ev.get("editsRaw"):
        out = {"kind": "v1", "legacy": diagnose_legacy_batch(ev), "keyToSourceV1": ev.get("keyToSource")}
    else:
        out = {"kind": "unknown"}
    out["file"] = p.name
    out["run"] = label
    out["schema"] = raw.get("schema")
    return out


def _fmt(v, nd=1, suffix=""):
    if v is None:
        return "—"
    if isinstance(v, str):
        return v
    return ("%." + str(nd) + "f") % v + suffix


def report(results: list[dict]) -> str:
    L = []
    v2 = [r for r in results if r.get("kind") == "v2-restated"]
    v1 = [r for r in results if r.get("kind") == "v1"]
    L.append("# C9 口径离线复核\n")
    if v2:
        L.append("## 新口径（v2 raw，可判）\n")
        L.append("| run | R | warmup | n(key) | min | median | p95 | max | IQR | IQR/med | 轮间spread | 判定 |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for r in v2:
            pk, pr = r["primary"]["perKey"], r["primary"]["rounds"]
            v = r["verdictRestated"]
            L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | **%s** |" % (
                r["run"], pr["R"], "—", pk["n"], _fmt(pk["min"]), _fmt(pk["median"]), _fmt(pk["p95"]),
                _fmt(pk["max"]), _fmt(pk["iqr"], 2), _fmt(pk["iqrOverMedian"], 3),
                _fmt(pr["spread"], 3), v["decision"]))
        bad = [r["run"] for r in v2 if not r["agrees"]]
        L.append("\n- 与 raw 内 verdict 一致：%s" % ("**是**" if not bad else "**否**（%s）" % ", ".join(bad)))
    if v1:
        L.append("\n## 历史基线（v1 raw = 一次性连发 30 键，仅供诊断）\n")
        L.append("| run | n | 首键(冷) | median | p95 | max | 顶3/其余 | max/median | 旧判据 max≤16 | 契约 median≤16 |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for r in v1:
            lg = r.get("legacy") or {}
            if "batch" not in lg:
                continue
            b = lg["batch"]
            L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
                r["run"], b["n"], _fmt(lg["coldFirstKeyMs"]), _fmt(b["median"]), _fmt(b["p95"]),
                _fmt(b["max"]), _fmt(lg["top3OverRest"], 2), _fmt(lg["top1OverMedian"], 2),
                "✅过" if lg["oldCriterion_maxLE16"] else "❌超",
                "✅过" if lg["contractCriterion_medianLE16"] else "❌超"))
        L.append("\n- 这批数据的 `keyToSource` 是**批量**读数；它们之间 14.0→26.2 ms 的差异**不能**据此判为噪声，")
        L.append("  也**不能**用 `min` 冒充单键成本（上表故意不给 min 作为判据）。")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="C9 度量口径离线复核")
    ap.add_argument("--raw", action="append", default=[], help="单份 raw JSON（可多次）")
    ap.add_argument("--dir", default=None, help="目录（取 raw-*.json）")
    ap.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    ap.add_argument("--out", default=None, help="把报告写到文件")
    args = ap.parse_args(argv)

    paths: list[Path] = []
    for r in args.raw:
        paths.append(Path(r))
    if args.dir:
        paths.extend(sorted(Path(args.dir).glob("raw-*.json")))
    if not paths:
        paths.extend(sorted(DEFAULT_RESULTS.glob("raw-*.json")))
    if not paths:
        print("[analyze_c9] 没有输入 raw", file=sys.stderr)
        return 2

    results = [analyze_file(p) for p in paths]
    results = [r for r in results if not r.get("skip")]
    if args.json:
        text = json.dumps(results, ensure_ascii=False, indent=2)
    else:
        text = report(results)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print("[analyze_c9] 写出 %s（%d 份 raw）" % (args.out, len(results)))
    else:
        # Windows 控制台默认 cp1252/cp936 ⇒ 显式 UTF-8 输出，避免 UnicodeEncodeError
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
