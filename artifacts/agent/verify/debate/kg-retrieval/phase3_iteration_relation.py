"""Phase 3 / C 方：iteration / loop / tool-call 的精确关系（回应 D 的 U-P3）。

数据：冻结快照 phase3-session-snapshot.jsonl（可复现，非活会话）。
定义（来自代码与事件语义，待交叉核对）：
  · 一个 user 轮（turn）= 一次用户消息触发的一次 agent loop；
  · 一个 iteration = 一次 LLM 请求/响应（事件 step/start + assistant/message 各一次）；
  · 一个 iteration 可产生 0..N 个 tool/call（并行调用），随后 loop 继续下一次 iteration；
  · loop/end 是"一轮结束"，其 usage 是整轮所有 iteration 的聚合。
本脚本验证：assistant/message 数 == step/start 数 == Σ loop/end.iterations？
            tool/call 与 tool/result 是否一一对应？
            每次 iteration 内的并行 tool call 分布？
"""

from __future__ import annotations

import argparse
import io
import json
from collections import Counter

PATH = r"D:\AAA_Jupyter\Memoria\artifacts\agent\verify\debate\kg-retrieval\phase3-session-snapshot.jsonl"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    events = []
    with io.open(PATH, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    steps = [e for e in events if e.get("type") == "step/start"]
    assistants = [e for e in events if e.get("type") == "assistant/message"]
    calls = [e for e in events if e.get("type") == "tool/call"]
    results = [e for e in events if e.get("type") == "tool/result"]
    loops = [e for e in events if e.get("type") == "loop/end"]
    users = [e for e in events if e.get("type") == "user/message"]

    # 逐轮：iterations、calls；并建立 iteration -> calls 映射
    turns = []
    cur = {"iterations": 0, "calls": 0, "assistant_msgs": 0, "loop": None}
    per_iteration_calls: list[int] = []
    pending_calls_in_iteration = 0
    for e in events:
        t = e.get("type")
        d = e.get("data") or {}
        if t == "assistant/message":
            cur["assistant_msgs"] += 1
            cur["iterations"] += 1
            pending_calls_in_iteration = len(d.get("tool_calls") or [])
            per_iteration_calls.append(pending_calls_in_iteration)
        elif t == "tool/call":
            cur["calls"] += 1
        elif t == "loop/end":
            cur["loop"] = d
            turns.append(cur)
            cur = {"iterations": 0, "calls": 0, "assistant_msgs": 0, "loop": None}

    loop_iters = [int((t["loop"] or {}).get("iterations") or 0) for t in turns]
    report = {
        "snapshot": PATH,
        "counts": {
            "user/message": len(users),
            "loop/end": len(loops),
            "step/start": len(steps),
            "assistant/message": len(assistants),
            "tool/call": len(calls),
            "tool/result": len(results),
        },
        "relation": {
            "assistant_messages_equals_step_starts": len(assistants) == len(steps),
            "assistant_messages_equals_sum_loop_iterations": len(assistants) == sum(loop_iters),
            "sum_loop_iterations": sum(loop_iters),
            "tool_calls_equal_results": len(calls) == len(results),
            "calls_per_iteration": round(len(calls) / len(assistants), 3) if assistants else None,
            "iterations_per_turn": round(len(assistants) / len(turns), 3) if turns else None,
            "loop_iters_equals_assistant_msgs_per_turn": [
                {"turn": i + 1, "loop_iters": it, "assistant_msgs": t["assistant_msgs"], "calls": t["calls"]}
                for i, (it, t) in enumerate(zip(loop_iters, turns))
            ],
        },
        "per_iteration_tool_calls": {
            "distribution": dict(Counter(per_iteration_calls)),
            "total_iterations": len(per_iteration_calls),
            "iterations_with_0_calls": sum(1 for n in per_iteration_calls if n == 0),
            "iterations_with_multi_calls": sum(1 for n in per_iteration_calls if n > 1),
            "max_calls_in_one_iteration": max(per_iteration_calls) if per_iteration_calls else 0,
        },
        "turn_table": [
            {
                "turn": i + 1,
                "loop_iterations": it,
                "assistant_msgs": t["assistant_msgs"],
                "tool_calls": t["calls"],
            }
            for i, (it, t) in enumerate(zip(loop_iters, turns))
        ],
    }
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
