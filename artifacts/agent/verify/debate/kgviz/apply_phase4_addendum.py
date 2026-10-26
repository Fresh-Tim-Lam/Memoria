"""Phase 4 增补 D-KGV-14/15/16：t(d) 口径修正、T-double 澄清、3D 光晕等大。"""
import io
import sys

P = "docs/design/kg-visualization-v0.md"
r = io.open(P, encoding="utf-8", newline="").read()


def must(old, new, label):
    global r
    if old not in r:
        sys.exit("ABORT: 未命中 " + label)
    print("  OK", label)
    r = r.replace(old, new, 1)


# ── D-KGV-14：t(d) 口径修正（render-perf 发现纯 ECDF 达不到端点）──
must("""**v0 取 A**：Phase 3 已论证分位在结构上消除长尾、自带上下界（`arch-contract` 因此撤回
「sizeScale 必须」）。连续分位与"分桶分位"的唯一区别是**没有档边界**，长尾优势保留。
A 的代价（同 degree 跨库半径不同）由 **tooltip 显示 degree 原值** 兜住；
⇒ **验收必须用同一语料**（见 §7 三元组与 §8 T-census）。""", """**v0 取 A（口径已修正，见下）**：Phase 3 已论证分位在结构上消除长尾、自带上下界
（`arch-contract` 因此撤回「sizeScale 必须」）。连续分位与"分桶分位"的唯一区别是**没有档边界**。

### ⚠️ D-KGV-14 · t(d) 的口径修正（实现时发现的设计缺陷）

> 本文件最初写 `t = percentile-rank`（纯 ECDF）。实现时发现**纯 ECDF 有算术缺陷**：
> 设 degree 分布为 `[1,1,1,2,3]`，ECDF 给出 `t(1)=0.6 / t(2)=0.8 / t(3)=1.0`
> ⇒ **最小值 `t=0.6` 而不是 0**（因为 min 本身有并列，占 3/5）⇒ **永远到不了 R_MIN**，
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
⇒ **验收必须用同一语料**（见 §7 三元组与 §8 T-census）。""", "D-KGV-14 t口径")

# ── D-KGV-15：T-double 澄清 ────────────────────────────────────
must(r, "| **T-double** | 同一节点同时用颜色+大小编码 degree ⇒ 检查双重编码冲突 | 有冲突 ⇒ 二选一 |",
     """| **T-double** | 【澄清后】检查两视觉通道是否编码**不同变量**或**方向相反**；\n同变量冗余编码（颜色与大小都编码 degree，且方向一致）⇒ **不视为冲突**（强化而非矛盾） | 有真冲突 ⇒ 二选一 |""",
     "D-KGV-15 T-double")

must("""> ★ **T-size-3 是"连续 vs 分桶"的直接证据**：若实现里其实偷偷按档位取整，""",
     """> **D-KGV-15（T-double 澄清）**：galaxy 风格同时用颜色与大小编码 degree ⇒
> 这是**同变量冗余编码**，判定为**允许**（冗余强化 ≠ 冲突）。
> 真正的冲突是：颜色编码 A 变量、大小编码 B 变量，或两者方向相反（一个说大一个说小）。
> T-double 的实现应检查后者，不应对前者报错。

> ★ **T-size-3 是"连续 vs 分桶"的直接证据**：若实现里其实偷偷按档位取整，""", "D-KGV-15 说明")

# ── D-KGV-16：3D 光晕等大 ─────────────────────────────────────
must("""**falsifier**：若 3D 深度判读任务正确率 ≥80% 且归一组显著优于等大组 ⇒ 可撤回。""",
     """**falsifier**：若 3D 深度判读任务正确率 ≥80% 且归一组显著优于等大组 ⇒ 可撤回。

### D-KGV-16 · 3D 光晕（galaxy halo）也必须等大

```
发现：节点 mesh 已 scale=1（等大），但 galaxy 的 halo（装饰性发光）仍随 degree 变
⇒ 光晕是【表观的尺寸线索】⇒ 若随 degree 变，等于绕过"3D 不做大小编码"的裁决
⇒ 裁决：3D 光晕半径【不随 degree 变化】（统一值或仅随 zoom 变化）
```

**理由**：D-KGV-04 的裁决依据是"3D 里尺寸通道不可解释（透视 1.78× 混淆）"。
如果 mesh 等大但光晕随度数变大，用户在 3D 里**仍然看到"度数大的看起来更大"** ⇒
该裁决被装饰层绕过。判据必须是"用户在 3D 里是否感知到尺寸差异"，而不是"mesh.scale 是否等于 1"。""",
     "D-KGV-16 3D光晕")

io.open(P, "w", encoding="utf-8", newline="").write(r)
print("  设计文档更新完成：%d 字节" % len(r))
