# 图谱引擎性能基准（graph benchmark）

> 位置与口径标记（对应 `docs/design/graph-benchmark.md`）。台账条目：`docs/todo.md` §4 **G05**。

## 快捷运行

```powershell
# 单次采集（打印 JSON；--out 可落盘）—— 小档约 40 秒
node scripts\benchmark\graph\render_l1.mjs
node scripts\benchmark\graph\render_l1.mjs --scales 100,500 --patterns small_world --frames 30

# 帧预算 A/B：0 = 关闭预算（复现"每帧固定 maxTicksPerFrame 个 tick"的旧行为）
node scripts\benchmark\graph\render_l1.mjs --scales 1000 --patterns small_world --frames 30 --frame-budget 0
node scripts\benchmark\graph\render_l1.mjs --scales 1000 --patterns small_world --frames 30 --frame-budget 8

# 只看图结构（秒级，不算布局/渲染）：成本由「最大连通分量」决定，排查 tick 耗时先看这个
node scripts\benchmark\graph\render_l1.mjs --structure-only --scales 300,1000,3000,5000

# 分项剖面：pair / links / center / integrate 各占多少 + `dist2<1` 守卫命中率（默认关闭的 opts.profile）
node scripts\benchmark\graph\render_l1.mjs --profile --scales 1000,5000 --patterns star --frames 120

# Barnes-Hut A/B（同 build）：--no-bh 走精确 O(N²)；--bh-theta 调近似程度（默认 0.9）
node scripts\benchmark\graph\render_l1.mjs --scales 5000 --patterns star --frames 30 --no-bh
node scripts\benchmark\graph\render_l1.mjs --scales 5000 --patterns star --frames 30 --bh-theta 1.2

# 锚定一次基线/对照（盖 commit + 语料指纹，落盘 results/）
python scripts\benchmark\graph\anchor_render_baseline.py --label baseline

# A/B 对照（产出对照表 + 门禁判定）
python scripts\benchmark\graph\compare_ab.py `
  --before scripts\benchmark\graph\results\render-baseline-target_346e5f95.json `
  --after  scripts\benchmark\graph\results\render-after-d1_346e5f95.json

# 目标档（真实规模 300~5000）—— 注意：一轮约 12 分钟（warmup 本身是 O(N²)×160 tick 且不受帧预算约束）
python scripts\benchmark\graph\anchor_render_baseline.py --label baseline-target `
  --scales 300,1000,3000,5000 --patterns small_world,partitioned,star --frames 30
```

> **采集成本定位**：目标档（5000）一轮约 **12 分钟** ⇒ 作为**里程碑门禁**；
> 日常提交门禁用小档（`--scales 50,100,250,500,1000`，约 40 秒）或 `--structure-only`（秒级）。

## 产物

- `results/render-<label>_<sha>.json`：原始数据（含 `meta`：commit / 工作区状态 / 语料指纹 / 采集命令）
- `results/render-<label>_<sha>.md`：分账表 + 静止每秒代价 + 布局质量 + 口径边界
- **改造前基线**（A/B 参照，两套）：
  - 小档 50–1000：`results/render-baseline_346e5f95.md`
  - **目标档 300–5000**：`results/render-baseline-target_346e5f95.md`

## 受控语料

复用 `MemoriaGraphSynthetic.syntheticGraph(n, pattern, {seed})`（`src/memoria/ui/static/app/js/graph-synthetic.js`）：
`n ∈ [50,100,250,500,1000]`、`pattern ∈ [small_world, partitioned, star]`，确定性 seed。
语料指纹见产物 `meta.corpus_digest`（计数口径），用于确认两次对照用的是同一语料。

## 口径边界（引用结论时必须一起给出）

1. **无头环境没有真 canvas**：绘制只测「调用次数 + JS 侧耗时」，**不含光栅化与 GPU** —— 真机 `drawMs` 会高于本层。
2. 真机 ≥60 节点时布局跑在 **Web Worker**；本层是同一份 `graph-layout-sim-core.js` 在**主线程**的口径，绝对值有偏差、量级可比。
3. **真帧率 / 长任务 / 3D 必须走 L2 浏览器层**（设计文档 §4.2，待建），本层不能替代。
4. 只覆盖 **2D**；3D 需 WebGL。

## 门禁口径（`compare_ab.py` 的判定依据）

- **L1 判两项**：布局**单 tick p50 ≤ 20ms**、**整帧 p95 ≤ 33ms**。
- **仅记录不判定**：绘制耗时与调用次数（真机光栅化口径须走 L2）、边长分布（参考项）。
- **布局质量底线**（用户 2026-09-16 定）：**节点不重叠 + 合理分散**，量化指标 `minNodeDist` / `nnDistP50` 将在 P2 前置步骤加入，
  且必须在**固定 tick 数**下测量 —— 否则"少跑 tick"会被误判成质量退化。

## 帧预算（D1）

`graph-layout-sim-core.js` 的 `runTicksWithBudget(tickFn, opts)`：最多 `maxTicksPerFrame` 个 tick，
累计耗时达 `frameBudgetMs`（默认 **8ms**）即收手、**至少 1 个**；`≤0` = 关闭。
2D/3D/worker 三处循环共用它，布局的 `runFrameTicks()` 是 `start()` 与本采集器的**同一入口**（口径不会漂）。

> **warmup（装载）用「工作量上限」而非计时**：`sim-core.WARMUP_PAIR_TICK_CAP = 8e7`（≈ 1000 节点 × 160 tick 的现状）。
> N ≤ 1000 行为完全不变，更大图按 (1000/N)² 缩减 ⇒ 实测装载统一压到 **~4.2–4.4s**
> （此前 5000 节点 **136s**，且 worker 就绪超时仅 3s 会让它回退到主线程跑完 = 界面卡死）。见设计文档 §1.1 X4。
> 用工作量而非计时是为了让**布局结果与机器无关、可复现**。

## 已知热点（2026-09-16，见设计文档 §5.4 / §5.5）

- **排斥核**是单 tick 的 **98.4–99.9%**（center / links / integrate 合计 <2%）⇒ 优化对象唯一。
- 精确 O(N²) 路径：计算一对 ≈ **51–70 ns**、被 skip 跳过的槽位 ≈ **6.3 ns**。
- **Barnes-Hut（默认）**：5000 节点 star 单 tick **745 → 33.9ms**（θ=1.2，22×），操作数降 **67×**（37 次交互/节点）。
  但每次交互 **192 ns**，是精确路径的 **3.5×** —— 根因是每 tick 分配 ~1.2 万格子对象 + 指针追逐 + 递归。
  **下一个瓶颈就在这里**（D2b：树扁平化/免分配，估 2–3×）。
- `dist2 < distanceMin` 守卫（近重合节点）命中率 **≈ 0**（star 5000：5 次 / 15 亿次迭代）——
  "它是性能热点"的假设已证伪，且旧版的 `Math.random()` 抖动已被 `distanceMin` 下限取代（换来布局确定性）。

## 维护提醒

- `render_l1.mjs` 里的 `VIEW_OPTS` 必须与 `src/memoria/ui/static/app/js/graph-settings.js` 的 `DEFAULTS` 保持一致。
  原因：`GraphView2D._layoutOptsFromView()` 会把视图 opts **无条件**写进布局 opts（`graph-view-2d.js:315-329`），
  视图缺键就会把 `undefined` 覆盖到布局默认值上，导致 `rep = undefined × alpha = NaN` → 整个仿真发散成 NaN（**静默无报错**）。
  采集器已内置守卫：`layout.opts` 必需键或节点坐标一旦非有限就**直接抛错**，不产出垃圾数据。
- 改 `graph-settings.js` 的 `DEFAULTS` 时，请同步 `VIEW_OPTS`。
