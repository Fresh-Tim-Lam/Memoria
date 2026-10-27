"""用真实会话算账（v2）：读 loop/end 的 data.usage，按回合计价。

真实字段：prompt_tokens / cache_read_tokens / cache_miss_tokens / completion_tokens / time
计价：复用仓库 pricing.py（含高峰/空闲双档，逐轮定时档）
"""
import io
import json
import os
import sys

ROOT = r"D:\AAA_Jupyter\Memoria"
sys.path.insert(0, os.path.join(ROOT, "src"))
from memoria.services.agent.llm import pricing  # noqa: E402

KB = r"D:\AAA_Courses\数字通信原理"
p = os.path.join(KB, ".memoria", "agent", "sessions",
                 "session-20261027T011706Z-0cb419b6.jsonl")

turns = []          # (time_ms, prompt, hit, miss, out)
lm = 0
with io.open(p, encoding="utf-8", errors="replace") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("type") == "loop/end":
            u = (r.get("data") or {}).get("usage") or {}
            lm += 1
            turns.append({
                "i": lm, "time": r.get("time"), "model": (r.get("data") or {}).get("model"),
                "prompt": int(u.get("prompt_tokens") or 0),
                "hit": int(u.get("cache_read_tokens") or 0),
                "miss": int(u.get("cache_miss_tokens") or 0),
                "out": int(u.get("completion_tokens") or 0),
                "iters": (r.get("data") or {}).get("iterations"),
            })

print("=" * 78)
print("真实账单：大知识库 %s" % KB)
print("会话：session-20261027T011706Z-0cb419b6.jsonl（16 轮对话 / 475 行事件）")
print("=" * 78)
print("单价（deepseek-flash，元/1M）：")
for k in ("hit", "miss", "output"):
    lo, hi = pricing.PRICES["deepseek-flash"][k]
    print("  %-6s 空闲 %.2f / 高峰 %.2f" % (k, lo, hi))
print("  ⇒ 未命中 ≈ 命中的 %.0f 倍" %
      (pricing.PRICES["deepseek-flash"]["miss"][0] / pricing.PRICES["deepseek-flash"]["hit"][0]))
print()

print("逐轮（prompt / 命中 / 未命中 / 输出 / 命中率 / 本回合计价）")
print("-" * 78)
tot = {"prompt": 0, "hit": 0, "miss": 0, "out": 0}
c_hit = c_miss = c_out = 0.0
for t in turns:
    row = {"prompt": t["prompt"], "cache_hit": t["hit"],
           "cache_miss": t["miss"], "completion": t["out"], "time": t["time"]}
    r = pricing.turn_cost(row, t["model"] or "deepseek-v4-flash")
    rate = t["hit"] / t["prompt"] * 100 if t["prompt"] else 0
    peak = "峰" if pricing.is_peak(t["time"]) else "闲"
    cost = (r["hit_cost"] + r["miss_cost"] + r["output_cost"]) if r else None
    if cost is not None:
        c_hit += r["hit_cost"]
        c_miss += r["miss_cost"]
        c_out += r["output_cost"]
    for k in tot:
        tot[k] += t[k]
    print("  #%-2d %s  %7d  %7d  %7d  %6d  %5.1f%%  %s"
          % (t["i"], peak, t["prompt"], t["hit"], t["miss"], t["out"], rate,
             ("%8.5f 元" % cost) if cost is not None else "     —"))

total_cost = c_hit + c_miss + c_out
print("-" * 78)
print("合计：")
print("  prompt tokens = %d（命中 %d / 未命中 %d）"
      % (tot["prompt"], tot["hit"], tot["miss"]))
print("  completion    = %d" % tot["out"])
print("  命中率        = %.2f%%" % (tot["hit"] / tot["prompt"] * 100 if tot["prompt"] else 0))
print("  费用 = %.5f 元" % total_cost)
print("       = 命中 %.5f + 未命中 %.5f + 输出 %.5f" % (c_hit, c_miss, c_out))
print("  未命中输入占总费用 %.1f%%" % (c_miss / total_cost * 100 if total_cost else 0))
print()
print("平均每轮：prompt %d tokens，费用 %.5f 元"
      % (tot["prompt"] / len(turns), total_cost / len(turns)))
print()

# 敏感度：命中率变化对费用的影响
unit = pricing.PRICES["deepseek-flash"]
print("敏感度（同一批 prompt tokens，全按空闲档估）：")
base_miss = tot["miss"]
for rate in (0.0, 0.5, 0.8, 0.9, 0.95, 0.99):
    miss = tot["prompt"] * (1 - rate)
    hit = tot["prompt"] * rate
    c = hit * unit["hit"][0] / 1e6 + miss * unit["miss"][0] / 1e6 + tot["out"] * unit["output"][0] / 1e6
    print("  命中率 %4.0f%% ⇒ 未命中 %9.0f tokens，输入费用 %.5f 元（相对当前 %+.0f%%）"
          % (rate * 100, miss, c,
             (c - total_cost) / total_cost * 100 if total_cost else 0))

# 上下文增长
print()
ps = [t["prompt"] for t in turns]
print("上下文规模：首轮 %d，最大 %d（第 %d 轮），末轮 %d"
      % (ps[0], max(ps), ps.index(max(ps)) + 1, ps[-1]))
print("  均值 %d；>100K 的轮次 %d/%d"
      % (sum(ps) // len(ps), sum(1 for x in ps if x > 100000), len(ps)))
print()
print("参照：deepseek 上下文窗口 1M ⇒ 本会话峰值占用 %.1f%%"
      % (max(ps) / 1_000_000 * 100))
