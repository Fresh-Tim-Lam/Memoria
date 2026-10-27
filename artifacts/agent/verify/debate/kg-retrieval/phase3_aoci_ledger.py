"""Phase 3 / C 方：AOCI ledger 复核（攻击 A 的证据）。

问题：外部研究把 "34 次 maintain 里 32 次 repair_required" 当作 "AOCI 太重/别搬" 的证据。
本脚本从 `.aoci/ledger.jsonl` 直接重算，检验两种解释：
  H-rot   ：repair_required 表示 AOCI 维护不断失败（索引腐化/实现烂）
  H-strict：repair_required 是 AOCI 的机器校验门禁在按设计工作（报修后修复重提、最终收敛）
判据：每次 repair_required 之后，是否在短时间窗口内出现 ok 的 update/maintain（收敛）；repair 原因是否可从 ledger 区分。

用法：python artifacts/agent/verify/debate/kg-retrieval/phase3_aoci_ledger.py --json phase3-aoci-ledger.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import os
import statistics
from collections import Counter

REPO = r"D:\AAA_Jupyter\Memoria"
LEDGER = os.path.join(REPO, ".aoci", "ledger.jsonl")


def parse_ts(value: str) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return None


def _eventual_success(events: list[dict], repair_rows: list[dict]) -> dict:
    """每次 repair_required 之后，**最终**是否出现成功写入（ok 的 update/finalize），窗口 2h / 不限。"""
    write_ops = ("update_entries_batch", "update_entries_batch_recover", "auto_finalize")
    out = {"within_2h": 0, "any_time": 0, "details": []}
    for row in repair_rows:
        t0 = parse_ts(row.get("ts"))
        hit_2h = None
        hit_any = None
        for later in events:
            if later is row:
                continue
            if str(later.get("op")) not in write_ops:
                continue
            if str(later.get("result")) != "ok":
                continue
            t1 = parse_ts(later.get("ts"))
            if not t0 or not t1 or t1 <= t0:
                continue
            hit_any = later
            if (t1 - t0).total_seconds() <= 7200:
                hit_2h = later
                break
        out["within_2h"] += 1 if hit_2h else 0
        out["any_time"] += 1 if hit_any else 0
        out["details"].append(
            {
                "repair_ts": row.get("ts"),
                "repair_op": row.get("op"),
                "ok_within_2h": bool(hit_2h),
                "ok_any_time": bool(hit_any),
                "ok_op": (hit_any or {}).get("op"),
                "ok_ts": (hit_any or {}).get("ts"),
            }
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    events = []
    with io.open(LEDGER, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    events.sort(key=lambda e: str(e.get("ts") or ""))

    by_op: dict[str, list[dict]] = {}
    for e in events:
        by_op.setdefault(str(e.get("op")), []).append(e)

    def durations(rows: list[dict]) -> dict:
        vals = [float(r.get("duration_ms") or 0) / 1000.0 for r in rows]
        if not vals:
            return {}
        return {
            "n": len(vals),
            "median_s": round(statistics.median(vals), 1),
            "mean_s": round(sum(vals) / len(vals), 1),
            "max_s": round(max(vals), 1),
            "sum_s": round(sum(vals), 1),
        }

    ops_summary = {
        op: {
            "n": len(rows),
            "results": dict(Counter(str(r.get("result")) for r in rows)),
            "duration": durations(rows),
            "source": dict(Counter(str(r.get("source")) for r in rows)),
            "tool_calls": sorted({int(r["aoci_tool_calls"]) for r in rows if "aoci_tool_calls" in r}),
        }
        for op, rows in by_op.items()
    }

    # maintain 序列：每次 repair_required 后 30 分钟内是否出现 ok 的写/维护
    maintain = by_op.get("maintain", [])
    write_ops = ("update_entries_batch", "update_entries_batch_recover", "maintain")
    converged = []
    for idx, row in enumerate(maintain):
        if str(row.get("result")) != "repair_required":
            continue
        t0 = parse_ts(row.get("ts"))
        nxt = None
        for later in events:
            if later is row:
                continue
            op = str(later.get("op"))
            if op not in write_ops:
                continue
            t1 = parse_ts(later.get("ts"))
            if not t0 or not t1 or t1 <= t0:
                continue
            if (t1 - t0).total_seconds() <= 1800:
                nxt = later
                break
        converged.append(
            {
                "ts": row.get("ts"),
                "duration_s": round(float(row.get("duration_ms") or 0) / 1000.0, 1),
                "paths_count": row.get("paths_count"),
                "aoci_tool_calls": row.get("aoci_tool_calls"),
                "next_write_within_30m": (
                    {"op": nxt.get("op"), "result": nxt.get("result"), "ts": nxt.get("ts")} if nxt else None
                ),
            }
        )

    # repair_required 的后续事件（任意 op）样本，帮助判断"报修后发生了什么"
    def next_after(rows: list[dict], row: dict, k: int = 2) -> list[dict]:
        try:
            i = rows.index(row)
        except ValueError:
            return []
        return [
            {"op": r.get("op"), "result": r.get("result"), "ts": r.get("ts"),
             "duration_s": round(float(r.get("duration_ms") or 0) / 1000.0, 1),
             "aoci_tool_calls": r.get("aoci_tool_calls")}
            for r in rows[i + 1 : i + 1 + k]
        ]

    repair_rows = [r for r in events if str(r.get("result")) == "repair_required"]
    repair_samples = [
        {"ts": r.get("ts"), "op": r.get("op"), "duration_s": round(float(r.get("duration_ms") or 0) / 1000.0, 1),
         "next": next_after(events, r, 2)}
        for r in repair_rows[:12]
    ]

    dates = Counter(str(e.get("ts"))[:10] for e in events)
    report = {
        "ledger": LEDGER,
        "events": len(events),
        "time_range": [events[0].get("ts"), events[-1].get("ts")] if events else [],
        "ops": ops_summary,
        "repair_required": {
            "count": len(repair_rows),
            "by_op": dict(Counter(str(r.get("op")) for r in repair_rows)),
            "maintain_total": len(maintain),
            "maintain_repair": sum(1 for r in maintain if str(r.get("result")) == "repair_required"),
            "convergence": converged,
            "converged_within_30m": sum(1 for c in converged if c["next_write_within_30m"]),
            "convergence_30m_results": {
                str(k): v
                for k, v in Counter((c["next_write_within_30m"] or {}).get("result") for c in converged).items()
            },
            "eventual_success": _eventual_success(events, repair_rows),
            "samples": repair_samples,
        },
        "remove_entry": {
            "count": len(by_op.get("remove_entry", [])),
            "results": dict(Counter(str(r.get("result")) for r in by_op.get("remove_entry", []))),
            "paths_count_sum": sum(int(r.get("paths_count") or 0) for r in by_op.get("remove_entry", [])),
            "dates": dict(Counter(str(r.get("ts"))[:10] for r in by_op.get("remove_entry", [])).most_common(8)),
        },
        "events_by_date": dict(sorted(dates.items())),
    }
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
