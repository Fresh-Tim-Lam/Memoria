# 4. 图谱 — 活跃详情（原文逐字）

> **本文件是 `docs/todo.md §4` 的活跃详情**（2026-10-26 索引化搬迁，**原文逐字**，未改写）。
> **状态事实源 = `docs/todo.md` 索引行**；本文件只放详情。历史归档仍在 `docs/design/**`，不在此重复。

<a id="g01"></a><a id="g02"></a><a id="g05"></a>

## 原文（逐字，自 docs/todo.md 搬迁）

## 4. 图谱

| ID | 任务 | 状态 |
| --- | --- | --- |
| G01 | R07 图谱推理·新边提议（建议边不自动写入，用户逐条采纳/忽略；需先定边属性专章）+ 梳理现实阅读/学习/复习场景中的知识点边类型 | 🔄 K1（边类型体系 `graph/edge_types.py:10-29` + 手动建边 `ui.py:775` 已实现；无 `suggest_edge`/提议 RPC，新边提议未实现） |
| G02 | Bug：边抑制之后点击构建/刷新，图谱仍然显示该边 | 🔴 |
| G05 | 图谱节点渲染算法优化，提升渲染性能，设置benchmark单独对图谱引擎性能测试 | 🔄 K1（**主体已达成，待补最后一步**；规划与逐项实测数据全部在 [design/graph-benchmark.md](design/graph-benchmark.md)。已落地：**D1 帧预算化**（目标档整帧 p95 大降）、**D2 Barnes-Hut 近似排斥**（`graph-bh-tree.js`，θ=0.9，`bh:false` 保留精确路径供同 build A/B）、**X3**（`distanceMin` 下限 + 位移上限取代 `Math.random()`）、**X4 装载卡死根治**（warmup 工作量上限 + worker 超时）。**未达标项**：单 tick ≤20ms 仅 partitioned 达标，small\_world/star 仍 33–35ms ⇒ 下一步 **D2b 树扁平化/免分配**（估 2–3×，目标 \~10ms）。用户已定：不设节点间距指标、不作质量门禁） |

***
