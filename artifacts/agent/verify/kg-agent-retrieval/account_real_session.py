"""用真实会话算账：大知识库（数字通信原理）agent 的 token 与费用。

数据源：<KB>/.memoria/agent/sessions/*.jsonl（真实会话记录）
计价：复用仓库 pricing.py（唯一事实源，含高峰/空闲双档）
"""
import io
import json
import os
import sys

ROOT = r"D:\AAA_Jupyter\Memoria"
sys.path.insert(0, os.path.join(ROOT, "src"))
from memoria.services.agent.llm import pricing  # noqa: E402

KB = r"D:\AAA_Courses\数字通信原理"
SESS = os.path.join(KB, ".memoria", "agent", "sessions")

print("=" * 74)
print("大知识库 agent 真实账单（%s）" % KB)
print("=" * 74)
print("价目：%s（核对日期 %s，单位 元/1M tokens）" % (pricing.CURRENCY, pricing.PRICE_TABLE_UPDATED))
for k, v in pricing.PRICES["deepseek-flash"].items():
    print("  deepseek-flash %-6s 空闲 %.2f / 高峰 %.2f" % (k, v[0], v[1]))
print("  ⇒ 未命中是命中的 %.0f 倍（空闲档）" % (pricing.PRICES["deepseek-flash"]["miss"][0] /
                                          pricing.PRICES["deepseek-flash"]["hit"][0]))
print()

files = sorted(f for f in os.listdir(SESS) if f.endswith(".jsonl")) if os.path.isdir(SESS) else []
if not files:
    sys.exit("  无会话文件")

for fname in files:
    path = os.path.join(SESS, fname)
    rows = []
    kinds = {}
    with io.open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = rec.get("type") or rec.get("kind") or "?"
            kinds[t] = kinds.get(t, 0) + 1
            rows.append(rec)

    print("-" * 74)
    print("会话 %s（%.1f KB，%d 行）" % (fname, os.path.getsize(path) / 1024, len(rows)))
    print("  记录类型分布：%s" % kinds)

    # 提取带 token 用量的记录（容错多种结构）
    usage_rows = []

    def walk(o):
        if isinstance(o, dict):
            if any(k in o for k in ("prompt", "cache_hit", "completion")):
                if isinstance(o.get("prompt"), (int, float)) or isinstance(o.get("cache_hit"), (int, float)):
                    usage_rows.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    for r in rows:
        walk(r)

    # 去重（同一对象可能被多处引用）
    seen = set()
    uniq = []
    for u in usage_rows:
        key = (u.get("prompt"), u.get("cache_hit"), u.get("cache_miss"), u.get("completion"), u.get("ts"))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(u)
    usage_rows = uniq
    print("  带 token 用量的记录：%d 条" % len(usage_rows))
    if not usage_rows:
        print("  （本会话没有可计价的 usage 明细）")
        continue

    tot_hit = tot_miss = tot_out = 0
    cost_total = 0.0
    cost_hit = cost_miss = cost_out = 0.0
    priced = 0
    unpriced = 0
    per_turn = []
    for u in usage_rows:
        r = pricing.turn_cost(u, model="deepseek-v4-flash", moment_ms=u.get("ts"))
        h = int(u.get("cache_hit") or 0)
        p = int(u.get("prompt") or 0)
        c = int(u.get("completion") or 0)
        m = int(u.get("cache_miss") or max(0, p - h))
        tot_hit += h
        tot_miss += m
        tot_out += c
        per_turn.append((p, h, m, c, r))
        if r and r.get("priced"):
            priced += 1
            cost_total += r["total_cost"]
            cost_hit += r["hit_cost"]
            cost_miss += r["miss_cost"]
            cost_out += r["output_cost"]
        else:
            unpriced += 1

    print()
    print("  逐轮（prompt / 命中 / 未命中 / 输出 / 命中率 / 本轮费用元）")
    for i, (p, h, m, c, r) in enumerate(per_turn, 1):
        rate = (h / p * 100) if p else 0
        cost = ("%.4f" % r["total_cost"]) if (r and r.get("priced")) else "—"
        print("    #%-2d  %8d  %8d  %8d  %7d  %6.1f%%  %s" % (i, p, h, m, c, rate, cost))

    print()
    tot_prompt = tot_hit + tot_miss
    print("  合计：")
    print("    prompt tokens = %d（命中 %d / 未命中 %d）" % (tot_prompt, tot_hit, tot_miss))
    print("    completion    = %d" % tot_out)
    print("    缓存命中率     = %.2f%%" % (tot_hit / tot_prompt * 100 if tot_prompt else 0))
    print("    可计价轮次 %d / 不可计价 %d" % (priced, unpriced))
    if cost_total:
        print("    费用：合计 %.4f 元" % cost_total)
        print("          = 命中 %.4f + 未命中 %.4f + 输出 %.4f" % (cost_hit, cost_miss, cost_out))
        print("    其中「未命中输入」占总费用 %.1f%%" % (cost_miss / cost_total * 100))
        print("    若命中率 90%%：未命中 %.4f 元、合计 %.4f 元（省 %.0f%%）"
              % (tot_prompt * 0.1 * pricing.PRICES['deepseek-flash']['miss'][0] / 1e6,
                 cost_total - cost_miss + tot_prompt * 0.1 * pricing.PRICES['deepseek-flash']['miss'][0] / 1e6,
                 (cost_miss - tot_prompt * 0.1 * pricing.PRICES['deepseek-flash']['miss'][0] / 1e6)
                 / cost_total * 100))
        print("    若命中率 0%%： 未命中 %.4f 元" % (tot_prompt * pricing.PRICES['deepseek-flash']['miss'][0] / 1e6))

    # 上下文增长
    if len(per_turn) >= 2:
        first = per_turn[0][0]
        last = per_turn[-1][0]
        print()
        print("  上下文增长：首轮 prompt %d → 末轮 %d（×%.1f，增加 %d tokens）"
              % (first, last, last / first if first else 0, last - first))
        mx = max(per_turn, key=lambda t: t[0])
        print("    最大单轮 prompt = %d tokens（第 %d 轮）"
              % (mx[0], per_turn.index(mx) + 1))
