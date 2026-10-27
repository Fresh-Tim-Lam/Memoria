"""为 C 方提案补齐最后几个数：迭代次数、read_kp 发生在哪些轮、逐轮成本。"""

from __future__ import annotations

import io
import json

PATH = r"D:\AAA_Courses\数字通信原理\.memoria\agent\sessions\session-20261027T011706Z-0cb419b6.jsonl"


def main() -> int:
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

    turns = []
    cur = {"calls": [], "usage": None, "iters": None}
    for e in events:
        d = e.get("data") or {}
        if e.get("type") == "tool/call":
            cur["calls"].append(str(d.get("name")))
        elif e.get("type") == "loop/end":
            cur["usage"] = d.get("usage") or {}
            cur["iters"] = d.get("iterations")
            turns.append(cur)
            cur = {"calls": [], "usage": None, "iters": None}

    total_iter = sum((t["iters"] or 0) for t in turns)
    print("turns:", len(turns), "total iterations:", total_iter)
    print("iterations per turn:", [t["iters"] for t in turns])
    for i, t in enumerate(turns, 1):
        kp = [j for j, name in enumerate(t["calls"]) if name == "read_kp"]
        if kp:
            print(f"turn {i}: read_kp at call index {kp} / total {len(t['calls'])} calls; seq names={t['calls']}")
    hit = sum(int((t["usage"] or {}).get("cache_read_tokens") or 0) for t in turns)
    miss = sum(int((t["usage"] or {}).get("cache_miss_tokens") or 0) for t in turns)
    prompt = sum(int((t["usage"] or {}).get("prompt_tokens") or 0) for t in turns)
    out = sum(int((t["usage"] or {}).get("completion_tokens") or 0) for t in turns)
    print(f"prompt={prompt} hit={hit} miss={miss} out={out} hit_rate={hit/prompt*100:.2f}%")
    print("avg iterations/turn:", round(total_iter / len(turns), 2), "tool calls/turn:", round(sum(len(t["calls"]) for t in turns) / len(turns), 2))
    print("out per iteration:", round(out / total_iter, 1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
