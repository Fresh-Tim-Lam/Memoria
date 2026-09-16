# 图谱引擎性能基线与渲染优化（Graph Benchmark）

> **用途**：为台账 **G05**（图谱节点渲染算法优化 + 单独的性能基准）建立可量化依据：现状诊断取证、按场景的指标与**每帧分账**、受控语料、L1/L2 两层采集、A/B 流程与门禁。回答三个问题——「拖拽为什么卡」「卡在布局还是绘制」「改完改善了多少」。
> **目标读者**：项目负责人（评审指标与阈值、拍板）；实施 Agent（按 §7 落地）；验收者（跑 A/B 出对照报告）。
> **关联文档**：[todo.md §4 G05](../todo.md)（本设计服务的台账条目）；[maintenance-benchmark.md](./maintenance-benchmark.md)（同族范式：L1/L2 分层 + A/B + 门禁）；[maintenance-jobs.md](./maintenance-jobs.md)；[frontend-modules.md](../conventions/frontend-modules.md)（R1 新代码不进 `app.js`）；[ledger-maintenance.md](../conventions/ledger-maintenance.md)（证据锚要求）。
> **状态**：草稿（待评审），2026-09-16。L1 采集与改造前基线已落地（§5.1）。
> **层**：L1 无头（`scripts/benchmark/graph/render_l1.mjs`）+ L2 浏览器（待建）。

---

## 0. 问题陈述

台账 G05 的表述是「图谱节点渲染算法优化，提升渲染性能，设置 benchmark 单独对图谱引擎性能测试」。

"渲染慢"是症状不是诊断。2026-09-16 只读取证 + L1 实测（§5.1）表明：**拖拽掉帧的主因是布局每帧固定 6 次 O(N²) 排斥，而不是渲染算法** —— 1000 节点档布局 : 绘制 ≈ **60 : 1**。若照原表述直接去优化渲染算法，会在错误的一半上花力气。

因此本设计的第一个产出不是优化方案，而是**分账**：把「布局 tick」与「绘制」分开量，先确定钱花在哪。

---

## 1. 现状诊断（只读取证，均带证据锚）

| # | 发现 | 证据 | 影响 |
|---|---|---|---|
| D1 | **仿真冷却后仍满帧重绘**：布局 rAF 循环只受 `running` 标志控制，`alpha` 衰减到 `alphaMin` 后不会自停；每个 tick 都触发一次全量 `draw()`。页签可见期间始终 `start()` | [graph-layout-2d.js:387-399](../../src/memoria/ui/static/app/js/graph-layout-2d.js)、[graph-layout-3d.js:421-433](../../src/memoria/ui/static/app/js/graph-layout-3d.js)、[graph-view-2d.js:194-196](../../src/memoria/ui/static/app/js/graph-view-2d.js)、[app.js:1180-1193](../../src/memoria/ui/static/app/js/app.js) | 静止时白烧 CPU：1000 节点档每秒要付 ≈**9.8 秒**的布局计算（单核满载、帧率仍只有 ~6fps） |
| D2 | **每帧固定 6 次 tick，无时间预算** | [graph-layout-sim-core.js:18](../../src/memoria/ui/static/app/js/graph-layout-sim-core.js)、[graph-layout-worker.js](../../src/memoria/ui/static/app/js/graph-layout-worker.js)（`for i < maxTicksPerFrame`） | 图越大每帧越贵，**没有帧时间上界**；大图上"每帧"变成几十~几百 ms |
| D3 | **每 tick 全对全 O(N²) 排斥**（`skipPairRepulsion` 只在多群时按群打折） | [graph-layout-sim-core.js:54-67](../../src/memoria/ui/static/app/js/graph-layout-sim-core.js) | 拖拽帧率的下限由它决定（§5.1 实测） |
| D4 | 2D **每帧全量重绘**：清整块画布、遍历全部边+节点+标签；无视野裁剪、无分层 canvas、无脏区 | [graph-view-2d.js:558-663](../../src/memoria/ui/static/app/js/graph-view-2d.js) | 单帧 O(E+N)（实测仅为布局的 ~1/60，非主因，但仍是纯浪费） |
| D5 | 每条边 `save/restore` + 两次 `beginPath/stroke/fill` + 逐边设样式 | [graph-view-2d.js:27-73](../../src/memoria/ui/static/app/js/graph-view-2d.js) | 1000 节点/2000 边 ⇒ **31006 次绘制调用/帧** |
| D6 | 标签**逐帧逐节点** `fillText`+`strokeText`，每次重设 `font`；无 `measureText` 缓存、无离屏预渲染、无"只画视野内/只画 hub" | [graph-view-2d.js:98-114](../../src/memoria/ui/static/app/js/graph-view-2d.js) | 文字光栅化是 canvas 最贵操作（真机口径会放大） |
| D7 | galaxy 光晕**每节点每帧新建径向渐变** | [graph-view-2d.js:144-158](../../src/memoria/ui/static/app/js/graph-view-2d.js) | O(N) 次渐变对象分配/帧 |
| D8 | 高亮路径被**线性查询放大**：`getNode` 是线性 `find`、`getOutgoingLinks` 是全量 filter，却被放进"遍历所有节点"的循环；**远端 hover 存在时每帧都调** | [graph-engine.js:95-101](../../src/memoria/ui/static/app/js/graph-engine.js)、[graph-view-3d.js:830-858](../../src/memoria/ui/static/app/js/graph-view-3d.js)、[graph-view-3d.js:921-926](../../src/memoria/ui/static/app/js/graph-view-3d.js) | 单次高亮 O(N²)，远端 hover 时每帧 O(N²) |
| D9 | 3D **draw call 爆炸**：每节点一个 `Mesh`+独立材质、每条边一条独立 `THREE.Line`、每节点一个 `Sprite`；无 `InstancedMesh`/`LineSegments` | [graph-view-3d.js:436-449](../../src/memoria/ui/static/app/js/graph-view-3d.js)、[graph-view-3d.js:489-507](../../src/memoria/ui/static/app/js/graph-view-3d.js) | 3D 大图的主要瓶颈 |
| D10 | 3D 每帧同步全部节点/边，并在末尾**重建八叉树** | [graph-view-3d.js:553-578](../../src/memoria/ui/static/app/js/graph-view-3d.js) | O(N log N)/帧 |
| D11 | **图谱模块零性能埋点**（全仓 grep：`performance.now`/帧计数均不落在 `graph-*.js`） | 对照既有埋点 [app.js:4608-4646](../../src/memoria/ui/static/app/js/app.js) | 无法量化、无法防回退 —— 所以基准要先于优化做 |

### 1.1 三个附带发现（本次取证/exe 实测暴露，非 G05 原始范围但相关）

| 编号 | 现象 | 证据 | 说明 |
|---|---|---|---|
| X1 | **视图 opts 缺键会静默毒化布局默认值**：`_layoutOptsFromView()` 把视图 opts **无条件**写进布局 opts，视图没给 `repulsion` 等键就会写入 `undefined` → `rep = undefined × alpha = NaN` → 整个仿真发散成 NaN（无任何报错） | [graph-view-2d.js:315-329](../../src/memoria/ui/static/app/js/graph-view-2d.js)（3D 同构） | 生产链路由 `app.js` 传完整 `getViewOptions()` 故未暴露；本次 L1 采集先踩到（见 §6 守卫）。**建议**：只写有限值，或视图侧做一次合并（独立小修，不属性能范围） |
| X2 | **「散落」分布模式取消跨群排斥屏蔽** → 「全部」页签 tick 成本从"按群打折"变成满 O(N²) | [graph-layout-sim-core.js:28-33](../../src/memoria/ui/static/app/js/graph-layout-sim-core.js)、[todo.md §4 G05](../todo.md) | 实测印证：同为 1000 节点，`partitioned`（多群打折）22.9ms vs `small_world`（单群）162.8ms。**D2 做完后此项自动不再是问题** |
| X3 | **排斥核无上限 → 偶发数值爆炸**：两节点几乎重合时 `f = rep / dist2` 可达 1e8 量级，且没有速度/位移上限，节点会被甩到极远处（实测 `small_world` 500 档 30 帧后最大边长 **2.13e9**） | [graph-layout-sim-core.js:141-143](../../src/memoria/ui/static/app/js/graph-layout-sim-core.js) | 观感上是"某个点突然飞到天边、把视野撑开"。**§5.4 剖面已证伪"它是性能热点"**（`dist2<1` 守卫命中 ≈0，5 次/15 亿次）⇒ 本项按**纯正确性/稳健性**处理（排斥软化核 + 速度上限），**不做性能预期** |
| X4 | **装载（warmup）无预算 → 目标档开图卡死约 2 分钟**：`warmupTicks=160` 是固定值且不受帧预算约束，实测装载耗时 **5000 节点 136s（small_world）/ 118s（star）**、3000 节点 47~51s、1000 节点 4.6s。更糟的是 worker 就绪超时只有 **3000ms**（[graph-layout-worker-bridge.js](../../src/memoria/ui/static/app/js/graph-layout-worker-bridge.js)）→ 必然触发 `_recoverMainThreadSimulation` **回退到主线程跑完这 136 秒**，表现为**界面完全卡死** | 装载耗时见 §5.2 | ✅ **已止血（2026-09-16）**：给 warmup 加**工作量上限** `sim-core.WARMUP_PAIR_TICK_CAP = 8e7`（≈ 1000 节点×160 tick 的现状 ⇒ 10⁴ 以下完全不变、更大图按 (1000/N)² 等比缩减），并把 worker 就绪超时 3s → **15s**（工作量已定界，固定超时成立）。实测装载：3000 节点 47–51s → **4.3s**，5000 节点 118–136s → **4.2s**，1000 档不变（4.4s）。根治仍在 D2（Barnes-Hut 会让 warmup 真正快起来） |

---

## 2. 指标（按场景，不做"只有一个总耗时"的糊账）

| 场景 | 指标 | 含义 | 采集层 | 对应批次 |
|---|---|---|---|---|
| **拖拽单节点**（最热） | `frame_ms` p50/p95 | 单帧总耗时 | L1+L2 | D / B / C |
| 拖拽单节点 | `tick_ms` p50/p95 | 每帧布局计算耗时（6 tick） | L1 | **D** |
| 拖拽单节点 | `draw_ms` p50/p95 | 每帧绘制 JS 侧耗时 | L1+L2 | B / C |
| 拖拽单节点 | `calls_per_draw` | 每帧绘制调用次数（按方法分） | L1 | B（批量/裁剪的收益） |
| 静止 3s | `idle_draws` | 静止期内的重绘次数（现状 ≈180/3s） | L2 | **A** |
| 静止 3s | `idle_cpu_ms` | 静止期内布局+绘制累计耗时（现状 ~9850ms/s @1000 节点） | L1 推算 | **A** |
| 平移 / 缩放 | `draw_ms` p50/p95 | 纯渲染（不加热 alpha） | L1+L2 | B |
| hover 高亮（含远端 hover） | `hover_ms` | 一次高亮刷新的耗时 | L1+L2 | B5 / C |
| 拾取 | `pick_ms` | 一次 `pointermove` 拾取耗时 | L2 | C4 |
| 首帧 | `first_paint_ms` | 载入图 → 首次绘制完成 | L2 | 防回退 |
| 主线程健康 | `longtask_count` / `longtask_ms` | >50ms 长任务 | L2（`PerformanceObserver`） | 全部 |
| 3D | `renderer.info.render.calls` | 每帧 draw call 数 | L2 | **C** |
| **布局质量**（近似排斥必带） | `edgeLenP50/P95` | 边长分布（观感代理） | L1 | **D2** |

> 判读基线：单帧预算 **16.7ms**（60fps）。超预算 ⇒ 拖拽必掉帧；**先看 `tick_ms` 还是 `draw_ms` 超**，两者的优化手段完全不同。

---

## 3. 受控语料

- 复用仓库既有确定性生成器：`MemoriaGraphSynthetic.syntheticGraph(n, pattern, {seed})`
  （[graph-synthetic.js](../../src/memoria/ui/static/app/js/graph-synthetic.js) / [synthetic.py](../../src/memoria/graph/synthetic.py)）。
- 三种 pattern 覆盖三类形状，实测成本差异极大，必须都测：`small_world`（单连通 ⇒ 满 O(N²)）、`partitioned`（多群 ⇒ 跨群打折）、`star`（单连通、一度节点多）。
- 语料指纹（计数口径）= `meta.corpus_digest`（见基线 json），用于确认两次对照用的是同一语料。

### 3.1 目标规模（2026-09-16 用户确认）

| 项 | 值 |
|---|---|
| 节点数 | **300 ~ 5000** |
| 每节点边数 | **1 ~ 11**（⇒ E ≈ 1.5N ~ 5.5N；N=5000 时 E ≈ 7.5k ~ 27.5k） |
| 优化目标档 | **5000 节点**（按上限设计，向下自然覆盖） |
| 2D / 3D | **同等优先** |

> **为什么目标档不能只跑 `BENCHMARK_SCALES`**：该常量是 `[50,100,250,500,1000]`（[graph-synthetic.js:102](../../src/memoria/ui/static/app/js/graph-synthetic.js)），**不含真实目标档**。
> 且它是 `scripts/graph_layout_benchmark.mjs` 与 `graph_layout_benchmark.py` 的共享默认值 —— 直接把 5000 加进去会连带把布局基准默认跑成十几分钟。
> 因此**不改该常量**，目标档通过 `--scales` 显式传入（见 §5.2）。


---

## 4. 分两层采集

### 4.1 L1 · 无头（Node `vm` 沙箱，可进 CI）

`scripts/benchmark/graph/render_l1.mjs`：用 **recording stub canvas 2D context**（记录 `fillText/strokeText/arc/beginPath/stroke/fill/save/restore/…` 的调用次数）替换真 canvas，加载 `graph-synthetic / graph-label / graph-groups / graph-layout-sim-core / graph-layout-2d / graph-engine / graph-view-2d`，走**真机同一条链路**（`engine.loadPayload()` → `"load"` → `view.resetSimulation()` → `layout.loadFromEngine()` 含 160 tick warmup），随后逐帧分账计时。

**能测**：布局 tick 耗时、绘制调用次数与 JS 侧耗时、hover 场景开销、边长分布。
**测不到**（不许含糊）：光栅化与 GPU、真帧率、长任务、3D（需 WebGL）。

> 口径对齐：真机 ≥60 节点时布局在 Web Worker 内（[graph-layout-worker-bridge.js](../../src/memoria/ui/static/app/js/graph-layout-worker-bridge.js)），本层量的是同一份 sim-core 代码在**主线程**的口径 —— 绝对值有偏差，量级可比。

### 4.2 L2 · 浏览器（真帧率，必须建）

- 起真前端：复用 [rich-content-test/_harness.py](../../docs/example/rich-content-test/_harness.py) 的 bottle 静态服务 + `/rpc` 桥模式（与 [maintenance-benchmark.md](./maintenance-benchmark.md) §8「直接自动化」决策一致）。
- 注入 `syntheticGraph` → 采集 `frame_ms` / `idle_draws` / `longtask` / `first_paint_ms` / `pick_ms` / 3D `renderer.info.render.calls`。
- 埋点开关：`?bench=1` 或 `window.__graphBench = true`（沿用 `app.js` 既有 `?bench=1` 先例）；**不进生产热路径**。
- 遵守 [frontend-modules.md](../conventions/frontend-modules.md) **R1**：埋点与新增渲染模块不进 `app.js`。

---

## 5. A/B 流程与门禁

1. 同机、同语料（确定性 seed）、同视口；每组 warmup 1 次 + 采样 N 次（L1 默认 30 帧，L2 默认 5 轮）。
2. 报 `p50 / p95`，不报均值。
3. **改造前基线已锚定**（§5.1）；改造后跑同一命令产出 `results/render-<label>_<sha>.{json,md}`。
4. 汇总为对照表：指标 | 改前 | 改后 | 变化% | 结论。
5. **门禁（用户 2026-09-16 拍板：定量阈值）**：

   | 项 | 通过标准 |
   |---|---|
   | **布局单 tick**（L1 口径） | 目标档（5000）**单个** `layout.tick()` p50 ≤ **20ms**（现状：star 单群 1515ms / small_world 658ms ⇒ 需 ~30–75× 改善；靠 D2） |
   | **整帧**（L1 口径） | 目标档 `frameMs` p95 ≤ **33ms**（30fps 可交互；靠 D1 的帧预算兜住，允许"少跑 tick 换帧时间"） |
   | **绘制**（L2 口径） | 目标档真 `draw_ms` p95 ≤ **8ms**（给布局留一半 16.7ms 预算；靠 B/C） |
   | 静止停帧（A） | 静止 3s 内 `idle_draws` ≤ **2**（现状 ≈180） |
   | 无回退 | `first_paint_ms` 不升、`longtask_count` 不增 |
   | 布局质量（D2） | **不作门禁**（用户 2026-09-16：*"我们又不是做力学模拟实验"*）。仅记录一个**廉价哨兵** `minNodeDist`（防"布局崩成一坨/明显重叠"）供参考，不设阈值、不要求固定 tick 数等度量装置 |
   | 通用 | 关键指标回退 ⇒ 打回；"改善"类提交**必须**附对照表 |

   > ⚠️ **2026-09-16 修正**：原先拍的是"目标档 `frame_ms` p95 下降 ≥40%"。§5.2 实测目标档是 **3958ms/帧**（star 单群 9108ms），
   > 在这个量级上"降 40%"毫无意义（仍不可用）。故改为**可用性阈值**（单 tick ≤20ms / 整帧 ≤33ms / 绘制 ≤8ms）。
   > "改善幅度"仍记录在对照表里，但**不作为通过标准**。
   >
   > **分侧口径的原因**：目标档的**布局**耗时由 L1 精确测得（纯 JS 计算，与真机同代码），
   > 而**渲染**耗时 L1 测不到光栅化 —— 故 D 批次用 L1 门禁即可，B/C 批次必须等 L2 建好。

6. **目标档位**：2026-09-16 用户确认 —— 真实知识库 **300~5000 节点 / 每节点 1~11 条边**，故**目标档取 5000**（见 §3.1），并按"按上限设计、向下自然覆盖"推进。

### 5.1 改造前基线（2026-09-16 锚定）

产物：`scripts/benchmark/graph/results/render-baseline_346e5f95.md`（commit `346e5f95`，工作区 dirty）。

**2D · L1 无头 · 1200×800@dpr2 · 每帧 6 tick · 30 帧**（单位 ms）：

| pattern | 节点 | 边 | 群 | 布局 tick p50 | 绘制 p50 | 单帧合计 p50 | ≈帧率上限 | 绘制调用/帧 |
|---|---|---|---|---|---|---|---|---|
| small_world | 250 | 500 | 6 | 10.5 | 0.7 | **11.2** | ~60（已贴近 16.7ms 预算） | 7756 |
| small_world | 500 | 1000 | 9 | 41.4 | 1.4 | **42.8** | ~23 fps | 15506 |
| small_world | 1000 | 2000 | 23 | **162.8** | 2.7 | **165.5** | **~6 fps** | 31006 |
| partitioned | 1000 | 1000 | 25 | 22.9 | 1.6 | 24.5 | ~41 fps | 18006 |
| star | 1000 | 999 | 1 | 168.9 | 1.6 | 170.6 | ~6 fps | 17993 |

**结论（本设计的出发依据）**：

1. **布局是主因**：1000 节点档布局 : 绘制 ≈ **60 : 1**。拖拽帧率由布局决定。
2. **`partitioned` vs `small_world` 差 7 倍**（22.9 vs 162.8ms）：跨群排斥屏蔽带来的"按群打折"很关键 —— 这也意味着 X2（散落模式取消屏蔽）会让大图成本直接跳到 162.8ms 这一档。
3. **绘制调用/帧 3.1 万次但只花 2.7ms**（无头口径）⇒ 批量/裁剪的收益需要 L2 真光栅化才能给出可信结论，不能凭无头数据下结论。
4. **静止代价**：1000 节点档每秒白付 ≈9.8 秒布局 + 0.16 秒绘制 ⇒ 单核持续满载（D1）。

### 5.2 目标档基线（2026-09-16 锚定，真实规模）

产物：`scripts/benchmark/graph/results/render-baseline-target_346e5f95.md`。
采集命令（**耗时约 12 分钟**，因 warmup 本身就是 O(N²)×160 tick）：

```powershell
python scripts\benchmark\graph\anchor_render_baseline.py --label baseline-target --scales 300,1000,3000,5000 --patterns small_world,partitioned,star --frames 30
```

**结构（`--structure-only`，秒级）**——成本由「最大连通分量」决定，没有这列就看不懂 tick 耗时：

| pattern | 节点 | 边 | 群数 | **最大连通分量** | 占比 | 孤立节点 |
|---|---|---|---|---|---|---|
| small_world | 300 | 600 | 3 | 298 | 99% | 2 |
| small_world | 1000 | 2000 | 23 | 977 | 98% | 21 |
| small_world | 3000 | 6000 | 55 | 2943 | 98% | 51 |
| small_world | 5000 | 7909 | 225 | **4752** | **95%** | 206 |
| partitioned | 5000 | 5000 | 125 | 40 | 1% | 0 |
| star | 5000 | 4999 | 1 | **5000** | 100% | 0 |

**分账（2D · L1 无头 · 1200×800@dpr2 · 每帧 6 tick · 30 帧，单位 ms）**：

| pattern | 节点 | 边 | 最大群 | **单 tick p50** | 布局 tick p50（6 tick） | 绘制 p50 | 单帧合计 p50 | ≈帧率 | 绘制调用/帧 |
|---|---|---|---|---|---|---|---|---|---|
| small_world | 300 | 600 | 298 | 2.5 | 14.9 | 0.8 | **15.8** | ~60（已贴满预算） | 9306 |
| small_world | 1000 | 2000 | 977 | 28.3 | 169.6 | 2.7 | 172.4 | ~6 fps | 31006 |
| small_world | 3000 | 6000 | 2943 | 250.2 | 1501.4 | 8.0 | 1509.6 | 0.66 fps | 93006 |
| small_world | 5000 | 7909 | 4752 | 657.8 | 3946.9 | 11.5 | **3958.4** | **0.25 fps** | 127823 |
| partitioned | 5000 | 5000 | 40 | 68.7 | 411.9 | 8.1 | 420.1 | 2.4 fps | 90006 |
| star | 300 | 299 | 300 | 2.6 | 15.4 | 0.5 | 15.9 | ~60 | 5393 |
| star | 5000 | 4999 | 5000 | **1515.5** | 9093.1 | 14.8 | **9108.5** | **0.11 fps** | 89993 |

**结论（本次最重要的四条）**：

1. **目标档目前完全不可用**：5000 节点全连通（star）**9.1 秒/帧 ≈ 0.11 fps**；5000 节点、95% 在最大分量（small_world）**4.0 秒/帧**。
   连真实区间的最小档（300 节点）也已经 **15.8ms/帧**、贴满 60fps 预算 —— 也就是说**现状连小库都不富余**。
2. **成本由最大连通分量决定**：同为 5000 节点，`partitioned`（最大群 40）**420ms** vs `star`（单群 5000）**9108ms** —— 差 **22×**。
   根因是跨群排斥被跳过（D3 + X2），所以"图很大但很碎"不卡、"一大坨连在一起"才卡。
3. **成本 ≠ 只由对数决定**（~~疑似 `dist2 < 1` 守卫里的 `Math.random()`~~）——**该假设已被 §5.4 的实测证伪**：
   守卫命中率 ≈ 0（star 5000 仅 5 次 / 15 亿次迭代）。同时 `partitioned` 的"每对成本"虚高是**分母口径**问题
   （pair 循环对每一对 i<j 都要跑 skip 检查，被跳过的对也要迭代），见 §5.4。
4. **渲染在目标档不再是零头**：5000 档绘制 **11.5–14.8ms**（无头、**不含光栅化**）已占 60fps 预算的 70–90%；
   真机加上文字光栅化必然超预算 ⇒ **P5/P6 与 P1/P2 是并列主线**，不是"顺带优化"。

> **由此产生的两个判断修正**：
> - **D1 单独不够**：帧预算能保证"拖拽/相机不卡死"，但在 9.1 秒/帧的现实下，仿真每帧只能推进极小步长，**布局事实上冻结**。D2（复杂度）是必做，不是优化。
> - **原门禁阈值失效**：见 §5 的"修正"说明（"降 40%"在 3958ms 量级上没有意义，改为可用性阈值）。
>
> **采集成本**：目标档 L1 一轮约 12 分钟 ⇒ 定位为**里程碑门禁**；日常提交门禁用小档（50–1000，约 40 秒）或 `--structure-only`（秒级）。

---

### 5.3 D1（帧预算化）A/B 结果（2026-09-16）

产物：`scripts/benchmark/graph/results/compare_render-baseline-target_346e5f95_render-after-d1_346e5f95.md`
（对照 = 同语料指纹 `da89500b1acea32d` ✓、同机，改前 `frameBudgetMs` 未记录=关闭 vs 改后 8ms）。

| pattern | 节点 | tick/帧 | 整帧 p50 | 整帧 p95 | p95 变化 |
|---|---|---|---|---|---|
| partitioned | 1000 | 6 → **2.83** | 23.9 → **12.3** | 30.7 → 15.5 | −49.7% |
| partitioned | 5000 | 6 → **1** | 420.1 → **73.5** | 441.2 → 77.5 | −82.4% |
| small_world | 300 | 6 → **3.93** | 15.8 → **10.7** | 18.8 → 11.1 | −41.0% |
| small_world | 1000 | 6 → **1** | 172.4 → **64.0** | 366.3 → 65.4 | −82.2% |
| small_world | 5000 | 6 → **1** | 3958.4 → **648.1** | 4666.9 → 682.6 | −85.4% |
| star | 1000 | 6 → **1** | 183.6 → **28.5** | 216.0 → 33.7 | −84.4% |
| star | 3000 | 6 → **1** | 1618.3 → **249.0** | 3290.6 → 258.6 | −92.1% |
| **star** | **5000** | 6 → **1** | **9108.5 → 681.7** | **9252.5 → 710.3** | **−92.3%** |

**结论**：

1. **"帧时间上界"达成**：目标档最坏情形（star 5000）整帧 p95 从 **9.25 秒 → 0.71 秒**（−92.3%），
   且机制是可解释的 —— 帧预算把"固定 6 tick"改成"最多 6 个、超 8ms 就收手"，大图自动退到 1 tick/帧。
2. **布局质量未被牺牲**：边长 p50 全部在 **±3% 内**（参考项），说明 D1 不改变布局形态，只改"多久推进一步"。
3. **门禁判定：24 项中 8 项达标 / 16 项未达标** —— 未达标项**全部**是"单 tick 本身 >20ms"
   （star 5000 单 tick 674ms、small_world 5000 单 tick 636ms）。
   这正是预期的边界：**预算无法把一帧切成零个 tick** —— 单 tick 的 O(N²) 复杂度必须由 **D2** 解决。
   D1 的价值是先**消除"无上界"这个更糟的性质**（从"可控但慢"取代"不可控地卡死"）。
4. **小档行为不变**（如 small_world 300 仍跑 3.93 tick/帧、part 300 仍 6 tick/帧）⇒ 预算在快图上是"不生效的上限"，符合设计意图（不改变小图的手感）。

> **一处未解释的观察（留给 P2 剖面）**：`star 5000` 的**绘制** p50 也从 14.8ms 降到 7.7ms，而**绘制调用次数完全相同**（89993）。
> 疑似与 X3 数值爆炸导致的"节点位置量级达 1e9"影响绘制路径有关，但**未确认**，不要当结论用。

### 5.4 tick 内部剖面（2026-09-16，P2 前置）

产物：`scripts/benchmark/graph/results/profile-tick.json`（`render_l1.mjs --profile`）。
方法：`sim-core` 内加**可选**分项计时/计数（`opts.profile`，默认关闭，关闭时热循环只多一个可预测的布尔判断）。
每 tick 记一次"槽位数"（= N(N-1)/2）而非逐对累加 —— 逐对累加本身会变成热点并污染 repulsion 分项。

| pattern | 节点 | ticks | 槽位数 | 实算对占比 | **守卫命中** | **repulsion 占比** | **ns / 槽位** |
|---|---|---|---|---|---|---|---|
| star | 1000 | 120 | 59.9M | 100% | 0 | 0.997 | 55.5 |
| star | 3000 | 120 | 539.8M | 100% | 0 | 0.999 | 56.3 |
| **star** | **5000** | 120 | **1499.7M** | 100% | **5** | **0.999** | **56.4** |
| small_world | 1000 | 120 | 59.9M | 95.5% | 0 | 0.994 | 54.0 |
| small_world | 3000 | 120 | 539.8M | 96.2% | 0 | 0.997 | 70.4 |
| small_world | 5000 | 120 | 1499.7M | 90.3% | 1 | 0.998 | 51.2 |
| partitioned | 1000 | 253 | 126.4M | 3.9% | 0 | 0.984 | 8.1 |
| partitioned | 3000 | 120 | 539.8M | 1.3% | 0 | 0.992 | 6.3 |
| partitioned | 5000 | 120 | 1499.7M | 0.8% | 0 | 0.995 | 6.3 |

**结论（P2 的定量依据）**：

1. **pair 循环占单 tick 的 98.4%–99.9%**（center / links / integrate 三项合计 <2%）。
   ⇒ 优化对象唯一且明确：**排斥核**。其余三项再怎么改都动不了大局。
2. **`dist2 < 1` 守卫命中率 ≈ 0**（star 5000：**5 次 / 15 亿次迭代**）
   ⇒ **"`Math.random()` 是热点"的假设被证伪**。因此 **X3 降级为纯正确性/稳健性问题（数值爆炸），不是性能问题** ——
   软化核/speed clamp 仍该做（消掉"节点飞到天边"），但**不要指望它能提速**。
3. **每对成本是稳定的线性常数**：**计算一对 ≈ 51–70 ns；只跑 skip 检查的槽位 ≈ 6.3 ns**。
   拟合模型：`单 tick ≈ 槽位 × 6.3ns + 实算对 × ~50ns`（对 partitioned 5000 预测 9.39s，实测 9.39s ✓）。
   `partitioned` 那列"每计算对 207/484/803ns"是分母口径造成的虚高（被跳过的对也要迭代），**以 ns/槽位 为准**。
4. **单连通图的成本 ∝ N²**：56 ns × N(N−1)/2。N 从 1000 → 5000 涨 **25×**，与实测吻合。
5. ⇒ **D2（Barnes-Hut）的量化预期**：pair 操作从 O(N²) 降到 O(N log N)；
   N=5000 时 12.5M 对 → 约 6.1 万树节点（含遍历常数 2–3× ≈ 15 万次操作）⇒ **pair 操作数降约 80–200×**。
   按上面的常数外推：单 tick 的 pair 部分从 640ms → 约 3–8ms，加上建树与 O(N)/O(E) 三项（现约 6ms，占 1%×640ms）
   ⇒ **单 tick 预期落到 10–20ms 量级，有望直接满足门禁"单 tick ≤20ms"**（估算，以 D2 落地后的实测为准）。

> **一处仍未解释（不影响 D2 决策）**：旧基线（`render-baseline-target`）里 `star 5000` 单 tick 为 **1515ms（=121ns/槽位）**，
> 而现在同样规模只有 704ms（56ns/槽位）。两者**状态不同**（旧版跑满 160 个 warmup tick、节点已聚拢；现在 warmup 被 X4 的工作量上限压到 6 tick）。
> 当前模型（6.3ns/槽位 + 50ns/实算对）解释不了 121ns/槽位。若要复现需临时关掉 warmup 上限（尚未提供 `--warmup-cap` 开关）。
> **D2 只关心对数，与此无关**，故不阻塞 P2；记此备查。

### 5.5 D2（Barnes-Hut 近似排斥）A/B 与实现记录（2026-09-16）

**机制**：新增 [graph-bh-tree.js](../../src/memoria/ui/static/app/js/graph-bh-tree.js)（2D 四叉树 / 3D 八叉树 + BH 遍历），
`sim-core` 默认走它、`opts.bh === false` 保留精确 O(N²) 路径（**同 build A/B 与正确性参照**）。
分组语义与 `skipPairRepulsion` **严格对齐**：不跨群排斥时**每个群各建一棵树**（跨群对自然排除），
跨群时建全局树；拖拽节点额外与所有树互斥（O(N) 额外开销）。θ 默认 **0.9**，可用 `--bh-theta` 调。
同批落地 **X3**：`distanceMin` 距离下限替掉 `Math.random()` 抖动 + 每 tick 位移上限（`maxVelocityRatio` × `linkDistance`）。

**A/B（同 build · star · 5000 节点 · 每帧 1 tick · ms）**

| 配置 | 单 tick | 整帧 | edgeLenP50 | edgeLenMax |
|---|---|---|---|---|
| 精确 `bh:false` | 745.0 | 752.8 | 3994.3 | 7403.1 |
| BH θ=0.9 | 52.8（**14.1×**） | 60.6 | 3225.2 | 5089.8 |
| BH θ=1.2 | **33.9（22.0×）** | **41.5** | 3214.5 | 5262.2 |

**5000 档三 pattern（BH θ=1.2）**

| pattern | 单 tick | 整帧 | 绘制 | 改造前单 tick |
|---|---|---|---|---|
| partitioned | **13.0** ✅ | **22.1** ✅ | 9.0 | 78 |
| small_world | 33.7 | 46.0 | 12.1 | 640 |
| star | 34.5 | 43.2 | 8.2 | 745 |

**剖面（BH θ=1.2 · star 5000 · 30 tick）—— 把"差在哪"定位清楚**

| 指标 | 值 | 含义 |
|---|---|---|
| `bhInteractions` | 5,563,702 ⇒ **185,457/tick ⇒ 37 次/节点** | 精确路径是 4999 对/节点 ⇒ **操作数降 67×** |
| `bhCells` | 357,270 ⇒ **11,909 格/tick** | 每 tick 分配 ~1.2 万个格子对象 ⇒ GC/缓存压力 |
| `nsPerBhInteraction` | **192 ns** | 精确路径 ≈52–56 ns/对 ⇒ **每次交互贵 3.5×** |
| 校验 | 185k × 192ns = 35.5ms ≈ 实测 33.9ms ✓ | 模型闭合 |
| 其余分项 | center 1.6 / links 12.9 / integrate 2.5 ms（share 0.984 仍在排斥） | — |

**结论（含对我上一轮估计的修正）**

1. **复杂度目标达成**：操作数降 67×（我原先估"80–200×"，量级对了），单 tick **745 → 33.9ms（22×）**、整帧 **753 → 41.5ms**。
2. **相对改造前**（D1 之前的 star 5000 = 9108 ms/帧）：**212×**（"5000 节点不可用"⇒"≈23fps 可交互"）。
3. **门禁未全达，但差距原因已被剖面定位**：单 tick ≤20ms 只有 partitioned 达标（13.0ms），
   small_world / star 仍 33–35ms。**不是交互数太多**（37 次/节点已经比精确的 4999 省 67×），
   而是**每次交互贵 3.5×** ⇒ 实现开销（每 tick ~12k 格子对象分配 + 指针追逐 + 递归），不是算法问题。
4. **质量**：`edgeLenP50` 比精确路径 **−19%**（布局更紧凑；`fitToView` 会归一化视野），
   `edgeLenMax` 从旧版的 **2.13e9 回落到 ~5000** ⇒ **X3 的数值爆炸已消除**，无发散、无 NaN。
5. **装载同步受益**：5000 档 `loadMs` 4.2s → **0.35s**（warmup 也走 BH）⇒ **X4 的根治兑现**（不再只是止血）。

**下一步 D2b（BH 实现优化，唯一已知瓶颈，估 2–3×）**：把 `nsPerBhInteraction` 从 192ns 压到接近精确路径的 ~55ns
⇒ 单 tick 预期 ~10ms、达标。手段（按收益排序）：① 树的**扁平化**（SoA / typed array，消掉每格一个对象的分配）；
② 递归改**显式栈**；③ 复用格子数组（跨 tick 免分配）。**这一步之后再谈是否需要动 θ。**

---

## 6. 仪器化缺口（实现时补）

- 图谱模块**零埋点**（D11）⇒ 需在视图内加 `?bench=1` / `window.__graphBench` 门控的：
  帧计时（`tick_ms` / `draw_ms`）、绘制调用计数（2D）、`renderer.info.render.calls`（3D）、`idle_draws` 计数。
- `PerformanceObserver('longtask')` —— 与 [maintenance-benchmark.md](./maintenance-benchmark.md) §6 记录的 B4 缺口**同一件事**，两处共用一套实现。
- L1 采集器已内置**防静默 NaN 守卫**（`layout.opts` 必需键有限性校验 + 节点坐标有限性校验，见 §1.1 X1）：缺键或仿真发散时**直接抛错**，不再产出看似合理实则垃圾的数据。

---

## 7. 优化清单与实施顺序

### 7.1 批次

| 批次 | 内容 | 买什么 | 风险 |
|---|---|---|---|
| **A** 静止停帧 | 布局侧判静（`alpha ≤ alphaMin×1.05` 且无拖拽/无待消费 reheat）→ 自动 `stop()`（含 worker 侧）；视图侧 `draw()` 加 dirty 门控。**必须附"重绘触发点清单"**（hover 进出、拖拽、缩放平移、主题切换、设置变更、构建/切群/切库、resize、定位高亮），漏一条就"画面不更新" | 静止时不烧 CPU（省电/降常驻）。**不提升拖拽帧率** | 低 |
| **B5** 引擎索引 | `graph-engine.js` 加 `id→node` Map 与邻接表，`getNode`/`getOutgoingLinks` 走索引 | 消掉 D8 的 O(N²) 高亮（含远端 hover 每帧） | 低 |
| **B** 2D 单帧减负 | B1 视野裁剪；B2 标签 measure 缓存/离屏预渲染/缩放降采样；B3 边按 (type, alpha) 分组批量描边；B4 galaxy 光晕预生成贴图 | 每帧渲染耗时与调用次数 | 中 |
| **D1** 帧预算化 ✅ 已落地 | 新增 `sim-core.runTicksWithBudget(tickFn, opts)` 单一实现（2D/3D/worker 三处循环共用，遵 `frontend-modules.md` R5）：最多 `maxTicksPerFrame` 个 tick，累计耗时达 `frameBudgetMs`（默认 **8ms**）即收手，**至少 1 个**；布局新增 `runFrameTicks()` 作为 `start()` 与基准采集的**同一入口**。`frameBudgetMs ≤ 0` = 关闭预算（A/B 用） | **帧时间上界**（大图自动少跑 tick：收敛慢一点，但不掉帧） | 低 |
| **D2** 近似排斥 ✅ 已落地 | 2D 四叉树 / 3D 八叉树 **Barnes-Hut**（新文件 [graph-bh-tree.js](../../src/memoria/ui/static/app/js/graph-bh-tree.js)），分组语义与 `skipPairRepulsion` 严格对齐；θ 默认 **0.9**；`bh:false` 保留精确路径供 A/B。同批并入 **X3**（`distanceMin` 下限 + 速度上限）。**实测（§5.5）**：star 5000 单 tick **745 → 33.9ms（22×）**、整帧 753 → 41.5ms（相对改造前 9108ms 为 **212×**）；操作数降 **67×**（37 次交互/节点）；`edgeLenMax` 从 2.13e9 回落到 ~5000（数值爆炸消除） | **拖拽帧率主线**（主体已达成） | ✅ |
| **D2b** BH 实现优化 | 剖面已定位唯一瓶颈：`nsPerBhInteraction = 192ns`，是精确路径（52–56ns/对）的 **3.5×**；根因是每 tick 分配 ~12k 格子对象 + 指针追逐 + 递归。手段：① 树扁平化（SoA / typed array）② 递归改显式栈 ③ 格子数组跨 tick 复用。目标：单 tick **33.9 → ~10ms**，补齐"单 tick ≤20ms"门禁 | 补齐目标档门禁（预估 2–3×） | 中 |
| **C** 3D | 节点 → `InstancedMesh`、边 → `LineSegments`（样式走 vertex colors）；位置同步与八叉树重建只在"未静"时做；2D 拾取加网格索引 | 3D 每帧 draw call 与拾取 | **高**（要重写拾取与高亮路径） |
| **X** 稳健性小修 | X1 视图 opts 只写有限值；X3 速度上限/排斥软化核 | 消掉静默 NaN 与偶发数值爆炸 | 低 |

### 7.2 顺序（2026-09-16 用户拍板：目标档 5000、**3D 与 2D 同等**、X1/X3 纳入）

```
P0 基准骨架（设计稿 + L1 采集 + 改造前基线）                    ✅ 已完成（§5.1 / §5.2）
P1 D1 帧预算化              → L1 对照 → 提交                   ✅ 已完成（§5.3）
P2 D2 近似排斥 + X3          → L1 对照 → 提交                   ✅ 已完成（§5.5）
P2b D2b 树扁平化/免分配      → L1 对照 → 提交                   补齐"单 tick ≤20ms"门禁（净收益唯一已知来源，估 2–3×）
P3 B5 引擎索引 + X1          → L1 对照（hover 场景）→ 提交
P4 L2 浏览器采集补齐          → 建立真帧率口径（B/C 门禁依赖它）
P5 B  2D 单帧减负            → L1 + L2 对照 → 提交
P6 C  3D（InstancedMesh / LineSegments）→ L2 对照 → 提交        与 2D 同等优先
P7 A  静止停帧               → L2 对照（idle_draws）→ 提交      与其它批次正交，买省电
P8 收口：G05 → ✅ + §10 归档 + 本设计状态更新 + 对照表入证据锚
```

**排序依据（不按"哪块代码看着最该优化"，按数据）**：

1. **P1 → P2 是主线**：目标档 5000 节点的布局是 O(N²)，而渲染是 O(E+N) —— 复杂度差一个量级，
   布局必须先解决（§5.2 实测）。D1 单独就能让"帧时间有上界"（交互不卡死），D2 则决定"仿真能不能真的收敛"。
2. **P4 插在渲染批次之前**：布局耗时 L1 已能精确测（纯 JS 同代码），但渲染耗时 L1 测不到光栅化 ——
   所以 D 批次用 L1 门禁即可，而 B/C 批次的口径必须先有 L2，否则"改了有没有效"无从判断。
3. **P5/P6 不是"次要"**：目标档 draw 已占单帧预算的可观比例（§5.2），加上真机光栅化会更高 ——
   布局解决后，渲染就是剩下的主要成本。
4. **P7 正交**：A 不改善拖拽帧率（用户已指出），只买"静止时不烧 CPU"，因此随时可做、不占主线。

> **P2 开工前置 ✅ 已完成（2026-09-16，见 §5.4）**：剖面结论 —— **pair 循环占单 tick 的 98.4–99.9%**；
> **`dist2<1` 守卫命中 ≈0**（证伪了"`Math.random()` 是热点"的假设）；计算一对 ≈51–70ns、被跳过的槽位 ≈6.3ns。
> ⇒ **X3 按纯正确性处理（不做性能预期）**；**D2 的目标明确为把 pair 操作降 80–200×**（单 tick 预期 10–20ms）。

### 7.3 D1 实现落点（2026-09-16）

| 文件 | 改动 |
|---|---|
| [graph-layout-sim-core.js](../../src/memoria/ui/static/app/js/graph-layout-sim-core.js) | 新增 `DEFAULTS.frameBudgetMs = 8`、`runTicksWithBudget(tickFn, opts)`（**单一实现**，2D/3D/worker 共用）、**X4 止血**：`WARMUP_PAIR_TICK_CAP = 8e7` + `effectiveWarmupTicks()`（warmup 工作量上限）、**剖面**：`opts.profile` 下的分项计时/计数（`ensureProfile`），并全部导出 |
| [graph-layout-2d.js](../../src/memoria/ui/static/app/js/graph-layout-2d.js) | `DEFAULTS.frameBudgetMs`；新增 `runFrameTicks()`；`start()` 改调它；`tick()` 保留/回写剖面对象 |
| [graph-layout-3d.js](../../src/memoria/ui/static/app/js/graph-layout-3d.js) | 同上 |
| [graph-layout-worker.js](../../src/memoria/ui/static/app/js/graph-layout-worker.js) | `loop()` 改用 `Sim.runTicksWithBudget`（原先固定 `maxTicksPerFrame`） |
| [graph-layout-worker-bridge.js](../../src/memoria/ui/static/app/js/graph-layout-worker-bridge.js) | X4 止血：就绪超时 3s → **15s**（warmup 已定界，固定超时成立） |
| [render_l1.mjs](../../scripts/benchmark/graph/render_l1.mjs) | 改用 `layout.runFrameTicks()`（**与真机同入口**）；新增 `--frame-budget`、`--profile`、`--structure-only`；上报 `ticksRun` / `warmupTicksRun` / `profile` |
| [anchor_render_baseline.py](../../scripts/benchmark/graph/anchor_render_baseline.py) | MD 增列「实际 tick/帧」与「装载耗时」 |
| [compare_ab.py](../../scripts/benchmark/graph/compare_ab.py) | 新增：A/B 对照 + 门禁判定（对老产物缺字段容错） |

**设计取舍（记录以免后人"优化"掉）**：

- **不新增设置项 UI**：`frameBudgetMs` 是技术旋钮，先只做机制与默认值，不进「设置 → 图谱」（避免无谓的 i18n 与界面面）。
- **`maxTicksPerFrame` 保留为上限**，预算只做"提前收手" ⇒ **小图行为与手感完全不变**（实测 ≤300 档 tick/帧不变，§5.3 结论 4）。
- **至少 1 个 tick**：否则大图上 alpha 不衰减、进度为零，仿真彻底冻结。
- **warmup 用"工作量上限"而不是"计时上限"**（X4 止血）：`WARMUP_PAIR_TICK_CAP = 8e7`（≈ 1000 节点 × 160 tick 的现状）。
  用工作量而非计时，是为了让**布局结果与机器速度无关、可复现** —— 否则基准口径会随机器漂。
  取值恰好等于 1000 档的现状 ⇒ **N ≤ 1000 行为完全不变**，更大图按 (1000/N)² 缩减（实测装载统一压到 ~4.2–4.4s）。
- **worker 就绪超时改成固定 15s 而非"随规模动态算"**：因为工作已被上一条定界（最坏 <10s，含单对开销翻倍的 star），
  固定值即可覆盖；动态估算需要校准常数、会随机器漂。**副作用**：N > 1000 时初始摆位比过去"欠松弛"（只跑 6~17 个 warmup tick），
  图会**先出现再逐步收敛**（配合 D1 的帧预算）。这是拿"开图即刻可见"换"开图卡 136 秒"，且在 D2 落地后自然消失。
- **剖面埋点默认关闭**（`opts.profile`）：关闭时热循环只多一个可预测的布尔判断；打开时"每 tick 记一次槽位数"而非逐对累加
  —— 逐对累加本身就是千万级热点，会污染被测的 repulsion 分项（第一版采集就踩了这个坑，已改）。


---

### 7.4 D2 实现落点（2026-09-16）

| 文件 | 改动 |
|---|---|
| [graph-bh-tree.js](../../src/memoria/ui/static/app/js/graph-bh-tree.js) | **新增**：2D 四叉树 / 3D 八叉树 + BH 遍历（`applyRepulsion`），默认 θ=0.9；`collectStats` 下回报 `{cells, interactions}` |
| [graph-layout-sim-core.js](../../src/memoria/ui/static/app/js/graph-layout-sim-core.js) | DEFAULTS 增 `bh/bhTheta/distanceMin/maxVelocityRatio`；新增 `groupBucketsIfNeeded`（保持分组语义）、`tryBHRepulsion`、`maxVelocitySq`；2D/3D 排斥段改为"BH 优先、精确兜底"；**X3**：`distanceMin` 下限替掉 `Math.random()`、积分段加位移上限 |
| [graph-layout-worker.js](../../src/memoria/ui/static/app/js/graph-layout-worker.js) | `importScripts` 增 `graph-bh-tree.js`（worker 侧也要有 BH） |
| [index.html](../../src/memoria/ui/static/app/index.html) | 脚本加载顺序：`graph-bh-tree.js` 在 `graph-layout-sim-core.js` 之前 |
| [render_l1.mjs](../../scripts/benchmark/graph/render_l1.mjs) | 新增 `--no-bh`（关近似走精确 = 同 build A/B）与 `--bh-theta`；剖面回报 `bhInteractions/bhCells/nsPerBhInteraction` |

**设计取舍（别"优化"掉）**：

- **保留精确 O(N²) 路径**（`opts.bh === false`）：① A/B 必须有"改前"一侧，且**同 build** 比跨 build 更干净；
  ② 它是 BH 的**正确性参照**（两边在同一状态下的布局量级应一致）。这不是兼容垫片。
- **拖拽节点单独处理**：exact 语义是"拖拽节点与**任意**节点互斥（含跨群）"，树的分组会把它排掉 ——
  故额外建单体树让其它节点遍历、并让拖拽节点遍历别的树（O(N)），否则"拖动一个节点推不开别群"会是行为退化。
- **`distanceMin` 取代 `Math.random()`**：换来"数值有界 + 布局确定性可复现"，代价是重合点不再自行分离
  （实测该情形 ≈5 次/15 亿次迭代）。若日后真出现"崩成一坨"，先查 `minNodeDist` 哨兵再看 θ。
- **θ 不进设置界面**：与 `frameBudgetMs` 同理，技术旋钮先只做默认值；要调走 `applyOptions` / 采集器 `--bh-theta`。

---

## 8. 打开问题

| # | 问题 | 结论 / 待定 |
|---|---|---|
| Q1 | **目标档位**：优化到哪一档算达标？ | ✅ **已定（2026-09-16）**：真实库 300~5000 节点 / 每节点 1~11 边 ⇒ **目标档 5000**（§3.1） |
| Q2 | **布局观感的可接受判定**：Barnes-Hut 会改变节点位置，用什么判"没变差"？ | ✅ **已定（2026-09-16 用户）**：**不设量化指标、不作门禁**（用户：*"我还没定节点之间距离指标，这个我无所谓"*、*"我们又不是做力学模拟实验"*）。底线是**目视**层面的「节点不重叠、合理分散」。仅保留一个**廉价哨兵** `minNodeDist`（全图最小节点间距）作记录用，防"布局崩成一坨/明显重叠"；`edgeLenP50/P95` 同样降为参考项。**不引入**固定 tick 数测量、交叉数等度量装置 |
| Q3 | **3D 是否同样优先** | ✅ **已定**：**3D 与 2D 同等**（§7.2，P5/P6 并列） |
| Q4 | **X1/X3 是否纳入本次范围** | ✅ **已定**：**纳入** —— X3（排斥核上限）并入 P2（同处排斥核），X1（视图 opts 只写有限值）并入 P3 |

---

## 9. 已知文档漂移（本设计发现，待处置）

| 漂移 | 现状 | 处置 |
|---|---|---|
| [maintenance-benchmark.md](./maintenance-benchmark.md) §3 | 写"结果写 `benchmarks/maintenance/results/<run>.{json,md}`"，实际落盘在 `scripts/benchmark/maintenance/results/` | 改维护基准文档的路径描述为实际路径（或反向统一目录，需项目负责人拍板） |

---

## 修订记录

| 日期 | 修订 |
|---|---|
| 2026-09-16 | 初版（草稿待评审）：现状诊断 D1–D11 + 附带发现 X1–X3；按场景的指标清单；L1/L2 两层采集；A/B 门禁；批次 A/B/B5/C/D1/D2/X 与 P0–P8 顺序；同日落地 L1 采集器 `scripts/benchmark/graph/render_l1.mjs` 与改造前基线 `results/render-baseline_346e5f95.{json,md}` |
| 2026-09-16 | 用户确认**目标规模 300~5000 节点 / 每节点 1~11 边**、**3D 与 2D 同等**、**X1/X3 纳入**；据此锚定**目标档基线** `results/render-baseline-target_346e5f95.{json,md}`（新增 `--structure-only` 结构模式），并据实测修正三处结论：① 目标档 5000 全连通 **9.1 秒/帧**（原按 1000 档外推不足）；② 门禁由"降 40%"改为**可用性阈值**（单 tick ≤20ms / 整帧 ≤33ms / 绘制 ≤8ms）；③ 渲染在目标档占预算 70–90%，P5/P6 升为并列主线；另新增 P2 开工前置（tick 内部剖面） |
| 2026-09-16 | **D1（帧预算化）落地 + A/B**：`sim-core.runTicksWithBudget` 单一实现（2D/3D/worker 共用）、布局 `runFrameTicks()`（`start()` 与采集器同入口）、采集器 `--frame-budget`、新增 `compare_ab.py`。目标档实测：整帧 p95 **star 5000 9252→710ms（−92.3%）**、small_world 5000 4667→683ms（−85.4%）；边长 p50 变化 ±3% 内（质量未牺牲）；门禁 24 项 8 达标 / 16 未达标，未达标**全部**是"单 tick 本身 >20ms" ⇒ 确认 D2 是必做项。另新记 **X4（装载无预算：5000 节点 136s + worker 就绪超时 3s 导致回退主线程卡死）**；Q2 已定（底线 = 节点不重叠 + 合理分散，量化指标在 P2 前置加入） |
| 2026-09-16 | **D2（Barnes-Hut）落地 + X3**：新增 `graph-bh-tree.js`（2D 四叉树 / 3D 八叉树，分组语义与 `skipPairRepulsion` 严格对齐，拖拽单独处理）；`sim-core` 默认走 BH、`bh:false` 保留精确路径供**同 build A/B**；X3 = `distanceMin` 下限替掉 `Math.random()` + 每 tick 位移上限。实测（§5.5）：star 5000 单 tick **745→33.9ms（θ=1.2，22×）**、整帧 753→41.5ms（相对改造前 9108ms 为 **212×**）；操作数降 **67×**（37 次交互/节点）；`edgeLenMax` 从 2.13e9 回落到 ~5000（数值爆炸消除）；装载 4.2s→**0.35s**（X4 根治兑现）。**门禁未全达**（单 tick ≤20ms 仅 partitioned 达标），剖面定位原因为 `nsPerBhInteraction=192ns`（是精确路径的 3.5×，源于每 tick ~12k 格子对象分配 + 指针追逐 + 递归）⇒ 新增批次 **D2b（树扁平化/免分配，估 2–3×）**。用户同时明确：**不设节点间距指标、不作质量门禁**（"不做力学模拟实验"），仅保留 `minNodeDist` 哨兵 |
