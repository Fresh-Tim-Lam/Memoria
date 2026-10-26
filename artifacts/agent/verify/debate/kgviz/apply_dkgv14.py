"""Phase 4 增补 D-KGV-14（t(d) 口径修正）—— 幂等。"""
import io
import sys

P = "docs/design/kg-visualization-v0.md"
r = io.open(P, encoding="utf-8", newline="").read()
MARK = "D-KGV-14 · t(d) 的口径修正"

if MARK in r:
    print("  SKIP（已应用）D-KGV-14")
else:
    OLD = """**v0 取 A**：Phase 3 已论证分位在结构上消除长尾、自带上下界（`arch-contract` 因此撤回
「sizeScale 必须」）。连续分位与"分桶分位"的唯一区别是**没有档边界**，长尾优势保留。
A 的代价（同 degree 跨库半径不同）由 **tooltip 显示 degree 原值** 兜住；
⇒ **验收必须用同一语料**（见 §7 三元组与 §8 T-census）。"""
    NEW = """**v0 取 A（口径已修正，见下）**：Phase 3 已论证分位在结构上消除长尾、自带上下界
（`arch-contract` 因此撤回「sizeScale 必须」）。连续分位与"分桶分位"的唯一区别是**没有档边界**。

### ⚠️ D-KGV-14 · t(d) 的口径修正（实现时发现的设计缺陷）

> 本文件最初写 `t = percentile-rank`（纯 ECDF）。实现时发现**纯 ECDF 有算术缺陷**：
> 设 degree 分布为 `[1,1,1,2,3]`，ECDF 给出 `t(1)=0.6 / t(2)=0.8 / t(3)=1.0`
> ⇒ **最小值的 t=0.6 而不是 0**（因为 min 本身有并列，占 3/5）⇒ **永远到不了 R_MIN**，
> T-size-4 的范围验收必然失败。

**修正后的口径（v0 冻结）**：
```
t(d) = rank_of_distinct_degree(d) / (n_distinct_degree - 1)
  · 末尾 distinct degree ⇒ t = 1 ⇒ radius = 9.90
  · 首个 distinct degree ⇒ t = 0 ⇒ radius = 4.50
  · 同 degree ⇒ 同半径（并列正确共享半径）
  · 无档位、无取整、无平台
```
**为什么这仍然符合"连续变化"**：连续的本意是「每个不同的 degree 得到各自的半径，端点都取到」，
不是「按 ECDF 累积概率分布」。修正后两端都可达、无平台、单调不减 —— 这才是可验收的连续。

实现位置：`graph-engine.js` 的 `MemoriaGraphSizing`（函数名 `percentileRankT` 是历史命名，
语义已是 distinct-degree 归一化 rank ⇒ 后续小改时重命名为 `normalizedRankT`）。

A 的代价（同 degree 跨库半径不同）由 **tooltip 显示 degree 原值** 兜住；
⇒ **验收必须用同一语料**（见 §7 三元组与 §8 T-census）。"""
    if OLD not in r:
        sys.exit("ABORT: 未命中 D-KGV-14 锚点")
    r = r.replace(OLD, NEW, 1)
    io.open(P, "w", encoding="utf-8", newline="").write(r)
    print("  OK D-KGV-14，%d 字节" % len(r))
