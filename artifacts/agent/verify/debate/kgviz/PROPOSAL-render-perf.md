# PROPOSAL — KGViz Phase 1 ｜ A 渲染 / 性能（render-perf）

> 提交：2026-10-25 · 角色：**A 渲染 / 性能** · 证据身份按 `PROTOCOL.md §1 E1`
> 本文件**独立完成**：未读同目录其它 3 份提案（见 §0.2）。**未改 `src/**`**、未 commit。

---

## 0. 独立性与读集（F2'）

### 0.1 read_set（关键文件 + LF 归一化 sha256；`read_at`≈2026-10-25T20:5x+08:00）

| path | sha256 |
|---|---|
| `artifacts/agent/verify/debate/PROTOCOL.md` | `29ab557a1f3862a2274df4db71c0e91f0ccdc5d90ae94dcd09658333ad7aa77b` |
| `docs/design/kg-ontology-v0.md` | `2f02b5552a94ef56cc4363c654b7f091f44227be62a5986b98d6bffb4b71c30f` |
| `src/memoria/ui/static/app/js/graph-view-2d.js` | `6e11e068b5304163b8f84859905f4675f1e2b871e30f5ad4a6d8391db530bcfb` |
| `src/memoria/ui/static/app/js/graph-view-3d.js` | `431019a1f7f93dcb566d75a0927f416ce939aa77a8698b5b93f40f8dc899cbf3` |
| `src/memoria/ui/static/app/js/graph-settings.js` | `d719c0981a41133261a95e2e4e3ce27814ff1d2b1e51eead9df4a4d12f7fd81d` |
| `src/memoria/ui/static/app/js/graph-engine.js` | `8609a86450f76f0548157c18cdc3c68a4baf02f34959737798770b8a5e2a2894` |
| `src/memoria/ui/static/app/js/graph-label.js` | `3e928e84e30606130d1f90ec1ad91744c413516b350440998f42b2c76238fd32` |
| `src/memoria/ui/static/app/js/graph-layout-2d.js` | `bb0acc1cbfaf8bc7c9f67b1233b494f5fb1ff413c11621002f947f9d66c93a55` |
| `src/memoria/ui/static/app/js/graph-layout-3d.js` | `a9ad819d5d00a25dc35c957b6d543c23c5900c3d621f3f79f530bee38fde371b` |
| `src/memoria/ui/static/app/js/graph-layout-sim-core.js` | `691092d60e08d5d62df41ce85d7bc817997453310214f1b14f950ce11a9f67fe` |
| `src/memoria/ui/static/app/js/graph-layout-worker-bridge.js` | `aa7b3b179ed264205d9afc61339189f8a7c962eba267a56ef8275f840267955a` |
| `src/memoria/ui/static/app/js/graph-groups.js` | `4161e4966a6352dd1c5934fa6a574bbf8d392c4c55e5727c6879e57c762655c8` |
| `src/memoria/graph/collector.py` | `2f26cf8ff73b966253484f9038ce55879636ab1fe150d74d38b474204def42cb` |
| `src/memoria/services/kp_index.py` | `b90fb621d17d2c9e410469b5786ff2ce3b02964c55e898e3d1d9bac7595a97d9` |

### 0.2 unread_declared
- **未读**：`PROPOSAL-arch-contract.md`、`PROPOSAL-metrics-baseline.md`、`PROPOSAL-todo-owner.md`（仅目录枚举见文件名；未打开、未读内容）。
- 未读 `phase1-census.json` / `_phase1_measure.py`（含他人测量，读了会污染独立性）。
- ⚠️ **共享假设/同源披露（E2）**：`docs/design/kg-ontology-v0.md#L122-L129` 已含一条“KGViz Phase 1 [arch-contract] 实测：node 字段 9 个、没有 degree”的 Lead 核实记录。我读该文件是协议要求的前置；该事实我**独立在 `collector.py#L61-L70` / `kp_index.py#L76-L84` 复核**，但按 E2 记 **独立根=1（共同引用）**，不当作独立第二根。

---

## 1. 立场摘要（≤10 行，可逐条反驳）

1. **v0 只允许一个节点大小驱动：度数（degree）**。它全量可用（133/133）、已经存在（links）、且能服务一个具体决策（“哪些 KP 是枢纽 / 哪些是孤立点”，与 v0“边服务人看的图 + 写质量诊断”一致）。
2. 大小映射**用分位数 5 档、不用连续线性**：档间屏幕直径差 ≥4px；2D 半径 4/6/8/10/12px（直径 8–24px）。连续映射产生的亚像素差异不可辨，是假精度。
3. **2D 逐节点半径的渲染成本≈0**（实测 133 节点 uniform r=4…12 均 0.56–0.65ms/帧；3000 节点 varied vs uniform 同为 ~1.7ms）。2D 真正的成本大头是**每节点标签**（3000 节点：6.7ms vs 1.7ms，标签占 ~75%）——所以 v0 上大小编码前，必须先做标签裁剪。
4. **3D 不需要拆 SphereGeometry**：现有实现已有“共享几何 + 每节点 Mesh.scale”路径（galaxy 分支就这么做）；逐节点半径**0 额外几何 / 0 额外 draw call**。需要拆几何体的只有 InstancedMesh 方案（实测 1000 节点：逐 Mesh 1.15–1.52ms/帧 vs Instanced 0.03ms，34–50×）。
5. **3D 当前的真实成本是 draw call 数量**：133 节点/404 边 = **634 draw calls / 407 geometries / 116 textures**，`_render()` 0.86ms；若节点扩到 1000，逐边 Line 会到 ~1600 draw（合并 LineSegments 实测 1.71ms→0.01ms），必须先把边合并 + 节点 instancing，否则 3D 大小编码是**在小图上做、到大图就崩**。
6. **3D 里“大小=重要”与“近大远小”不可区分（有实测）**：透视下相机到节点距离 1375–2447，**同一 world 半径的屏幕尺寸最多差 1.78×**；所以 **v0 建议 2D 启用大小编码、3D 保持等大**（3D 用度数颜色即可，颜色已在 galaxy 里实现）。若 3D 必须做大小，必须做屏幕空间归一（scale ∝ 距离）并用标签/描边冗余表达，否则语义不可解释。
7. **其它驱动因子（内容长度/卡片数/复习/FSRS/当前文件/掌握/分组）不作为 v0 大小驱动**：内容长度动态范围仅 3.1× 且“长度/行数”已被 D-KG-07 列为禁用判据；卡片/复习/FSRS 覆盖率只有 **66/133 = 50%** 且需要后端契约变更；当前文件是状态量（改用描边，不占大小通道）；分组规模在组内常量（无 per-node 信息）。
8. 度数应提升为**引擎通用属性**（`node.degree`）一次 O(E) 计算；现在 2D/3D 各算一份、缓存键是 `links.length`（边集变但条数不变时会陈旧——一个已存在的隐患）。
9. 标签是 2D/3D 共同的成本与可读性瓶颈：2D 无避让、3D 每节点一个 sprite/texture；v0 标签策略必须按“悬停/选中/度数 top-K/缩放阈值”裁剪，否则大小编码的收益会被标签成本吃掉。
10. **可测成本闸（成本侧）**：2D `draw()` p95 ≤4ms@1000 节点（含 ≤300 标签）；3D draw calls ≤1200、`_render()` p95 ≤8ms、geometries ≤10（边合并后）、textures ≤ 可见标签数+2。当前基线：2D 0.62ms@133；3D 634 calls/0.86ms@133。

---

## 2. Q1【人的直接问题】节点大小该由什么驱动？

**决策门槛**（沿用 KG 辩论的门槛：每个视觉通道必须服务一个决策）。本项目的“图谱用途”已由 v0 冻结：**人看的图 + 写质量诊断**，不是 agent 推理（`ev:doc:docs/design/kg-ontology-v0.md#L27`）。

| 候选 | ① 服务哪个决策 | ② 现成数据（覆盖率） | ③ 可辨性 / 渲染成本（我的主战场） | ④ 与颜色/形状/透明度冲突 | 结论 |
|---|---|---|---|---|---|
| **度数** | “**哪些 KP 是枢纽 / 哪些孤立**”：找 13 个 0 度孤立点、25 度 hub，决定先补链接还是先读 hub（写质量诊断） | ✅ **全量**：`links` 已在引擎里（`ev:file:graph-engine.js#L16-L31`）；度数现算于 `ev:file:graph-view-2d.js#L543-L556`、`ev:file:graph-view-3d.js#L396-L409` | 实测分布：p50=5 / p90=12 / p99=24 / max=25 / 0 度 13 个；5 档分位可做出 ≥4px 直径差；2D 成本 0 额外（见 §3 表 A） | galaxy 已用颜色编码度数（`ev:file:graph-view-2d.js#L639`、`#L648`；3D `#L431-L434`）⇒ 需规定**同一风格下“颜色与大小”同源或只用其一**，避免双重编码 | ✅ **v0 主驱动** |
| KP 内容长度（end_line−start_line） | “内容厚/薄，值不值得整段读” | ✅ 全量（range_ok 133/133；`ev:file:kp_index.py#L61-L64`） | 实测 p50=105 行、p90=148、max=327 ⇒ p50→max 仅 **3.1×**；若按 5 档会得到 2px 级差异（接近不可辨，需 A/B 验）；2D 成本 0 | 与“长度”语义强绑定；D-KG-07 已把**长度/行数/块数列为禁用判据**（`ev:doc:docs/design/kg-ontology-v0.md#L138`） | ❌ 不作大小；**只进 tooltip** |
| 卡片数 | “复习负担/卡片密度” | ⚠️ **66/133 = 50%** 节点可 join（`cards.json` 114 卡，`kp_id` 唯一 66；实测），且该文件在**后端**（`ev:file:src/memoria/services/agent/tools/kb.py#L4583-L4584`），不在图 payload | 渲染成本 0（数据来了就有）；但一半节点“无信号”必须画成“未知”大小，破坏通道一致性 | 与“未知态”竞争；与度数可能相关（hub 常多卡） | ❌ v0 不做；v1 需覆盖率 ≥90% |
| 复习次数 / FSRS 稳定性·难度 | “找薄弱、找到期” | ⚠️ 后端 `progress.json`（schema/FSRS 5，实测 101 张卡有 state/stability/difficulty/due），覆盖率同 50%；且是**时变量** | 成本 0；但需要**刷新语义**（何时重算）与“今天/历史”口径，否则图一开一合就变 | 与“当前时间”强耦合；与颜色状态（hover/target）冲突面大 | ❌ v0 不做（进 v1 需新 payload + 刷新规则） |
| 是否当前文件 | “当前文档在图中的位置” | ✅ `node.file` + `state.currentPath`（`ev:file:graph-engine.js#L62-L75`；app 内有 currentPath） | 只影响少数节点 ⇒ 描边 1 次/节点，成本可忽略；大小通道会被“状态”污染（今天在 3 个文件间切，节点就跳大小） | 与 hover/focus 描边冲突（都抢描边） | ❌ 作大小；✅ **作描边/光环** |
| 是否已掌握 | “复习进度” | ⚠️ 只可从 FSRS 聚合，覆盖率 50%；时变 | 成本 0；同复习类问题 | 与“到期/难度”共线 | ❌ v0 不做 |
| 分组规模 | “看组大小” | ✅ `engine.groups`（`ev:file:graph-groups.js#L83-L98`） | 组内所有节点同大 ⇒ **无 per-node 信息**；大小差异只会在组间，与“位置/聚类”重复 | 与聚类位置冗余；与度数可能冲突（大组 hub 多） | ❌ 拒绝 |

**结论（Q1）**：v0 的节点大小**只有度数**一个驱动；内容长度进 tooltip；其余候选进 v1 的“契约变更”清单或明确不做。

**“6px 到多少 px 视觉可辨？”**（Q1③ 的正面回答，可测口径）
- 现有节点半径默认 6px（`ev:file:graph-view-2d.js#L10`），标签字号 10px（`ev:file:graph-view-2d.js#L100`）；2D 命中半径是 `nodeRadius+6`=12px（`ev:file:graph-view-2d.js#L422`）。
- 视觉可辨的最小步长按**直径差 ≥4px**（半径差 2px）设计：同一画布上 8/12/16/20/24px 直径的五个圆，人眼可稳定区分；1px 直径差在 133 节点密度下不可靠。
- 因此建议 **2D 半径域 4–12px（直径 8–24px）**：与现有设置范围 4–12 完全一致（`ev:file:graph-settings.js#L561`），不引入新参数；最小 8px 直径保证可点（现命中 12px 仍覆盖），最大 24px ≤ 布局链路间距 108 的 1/4（`ev:file:graph-layout-2d.js#L8`），不会盖住邻居。
- ⚠️ **若半径超过 12px，必须同步改命中半径**：现在 `_pickNode` 用全局 `nodeRadius+6`（`ev:file:graph-view-2d.js#L422`），大节点边缘会点不中。这是“大小编码”的强制配套改动（成本：1 处函数，O(N) 不变）。

---

## 3. Q2【主战场】大小的映射函数与性能

### 3.1 映射函数（提案，可证伪）

```
// 每次 load 时对全图度数求分位（O(N log N) 一次），再落到 5 档：
//   0%,20%,40%,60%,80%,100% 分位（去重后若不足 5 档则合并）
// bin → 半径(px): [4, 6, 8, 10, 12]   // 直径 [8,12,16,20,24]px，档间 ≥4px
r = R_BY_BIN[bin(degree)]
screenR = clamp(r * transform.k, 3, 18)   // 可选：屏幕空间恒显（见 3.2）
```
- **为什么不是线性**：实测度数 p50=5、p90=12、max=25（长尾 2 倍于 p90）；线性会把 90% 节点压进 6–7px，而 5 个离群点吃掉全部上限 —— 这正是人抱怨的“都差不多大”。
- **为什么不是严格 log**：log 在 0 度（13 个节点）与 1–2 度上仍拥挤；分位法保证**每一档都有可见人口**，并且不依赖分布假设。
- **数据依赖**：分位阈值随图变化 ⇒ 同一节点在不同 KB 中大小不同。这是设计选择（相对重要性），必须在 tooltip 里显示 `degree=5（档 3/5）`，否则会被误读成绝对大小。

### 3.2 缩放时：world-space vs screen-space
- 现状：2D 节点/标签都画在 world 坐标（`ctx.scale(k)`，`ev:file:graph-view-2d.js#L573-L574`），所以缩小到 `zoomMin2d=0.02`（`ev:file:graph-settings.js#L39`附近）时 12px 节点变成 0.24px；放大到 2.5 倍又变 30px。
- **建议 v0**：节点半径**屏幕空间恒显**：绘制时用 `r/k`（div 一次/节点，成本≈0），命中半径同步 `/k`；标签同理（10px 屏幕空间），并在 `k` 低于阈值时隐藏标签。
- 证据：逐节点半径与 uniform 的 2D 成本无差异（§4 表 A），所以“恒显”不增加渲染成本；它只改一个算术——但显著改善“缩放后大小语义漂移”。

### 3.3 性能（实测，详见 §4、§6）

| 场景 | 实测 | 口径 |
|---|---|---|
| 真实 2D（133 节点/404 边，260×580 画布） | **0.62ms/帧** | `draw()` ×20，warm |
| 2D `nodeRadius` 4/6/9/12 | 0.63 / 0.63 / 0.56 / 0.65ms | 同上，差异在噪声内 ⇒ 大小编码**免费** |
| 2D 银河风格（径向渐变光晕） | **1.53ms**（2.5×） | 同图；光晕是成本，不是大小 |
| 合成 2D N=800/1500/3000（仅节点+边） | 0.44 / 0.80 / 1.70ms | 900×700 canvas，10 reps |
| 合成 2D 同上 + 每节点标签 | 1.45 / 2.91 / **6.70ms** | 标签占 70–75% |
| 合成 3D 1000 节点：逐 Mesh（共享几何/共享材质） | 1.15ms，1000 draw | 900×700，20 reps，`gl.finish()` |
| 合成 3D 1000 节点：逐 Mesh + 每节点材质（=现有 3D 实现） | 1.52ms，1000 draw | 同上 |
| 合成 3D 1000 节点：**InstancedMesh** | **0.03ms，1 draw** | 同上 |
| 合成 3D 1000 标签 sprite | 1.38ms，1000 draw | 同上 |
| 合成 3D 1600 边：逐边 Line vs 合并 LineSegments | **1.71ms/1600 draw vs 0.01ms/1 draw** | 同上 |
| 真实 3D（133 节点/404 边） | **634 draw calls / 407 geometries / 116 textures；`_render()` 0.86ms；`_syncPositions()` 0.02ms** | 同上，面板强制 260×560 |

**3D 要不要拆共享几何体？——不需要（对“逐节点大小”而言）**：
- 现有 3D 是 `SphereGeometry(r)` 共享 + `Mesh` 逐节点 + `mesh.scale.set(scale)`（`ev:file:graph-view-3d.js#L414-L445`）；galaxy 分支已经按度数 `scale=1+ratio*0.4` 做过逐节点缩放 ⇒ **大小差异只改 scale，几何体/材质/draw call 全不变**。
- 只有 **InstancedMesh** 才需要“单位球 + per-instance matrix”（实测 34–50× 提速的前提），但 InstancedMesh 会**失去逐节点材质/逐节点拾取对象**，拾取需改用 octree/数学判断（现有 3D 已有 octree，`ev:file:graph-view-3d.js#L511-L527`，可复用）。⇒ 这是性能优化项，**不是大小编码的必要条件**。

---

## 4. Q3 度数数据复用

- **现状**：2D/3D 各自 `_galaxyStats()`（`ev:file:graph-view-2d.js#L543-L556`、`ev:file:graph-view-3d.js#L396-L409`），**只在 `graphStyle==="galaxy"` 时调用**（2D `ev:file:graph-view-2d.js#L611-L612`；3D `ev:file:graph-view-3d.js#L423-L424`）。默认风格是 `force`（`ev:file:graph-settings.js#L38`）⇒ **度数算了但默认视图完全不用**。
- **缓存键隐患**：`_galaxyCache.version !== links.length`（`ev:file:graph-view-2d.js#L544-L545`、3D `#L398`）——若一次操作后边数不变但端点变了（例如切分组/过滤后重建 links 的不同子集**恰好同数**），度数会陈旧。虽然概率低，但它会让“大小=度数”直接画错；属于**大小编码的上线前置修复**。
- **提案**：
  1. 新增纯函数 `graph-metrics.js`：`computeDegrees(nodes, links) → {degree: Map, degreeNorm: Map, max, quantileBins}`，O(N+E)，一次；
  2. `GraphEngine.loadPayload()` 末尾调用（`ev:file:graph-engine.js#L62-L95` 是同一 load 管线），把 `degree/degreeNorm` 挂到 node 对象上；`links` 变化时重算；
  3. 2D/3D 的 galaxy 与 size 都读同一字段，删除两处 `_galaxyStats` 复算；
  4. **后端 collector 不新增 degree**：v0 事实是“agent 完全不读边”（`ev:doc:docs/design/kg-ontology-v0.md#L27`），新增后端字段会制造第二条事实源；等 agent 有边消费决策再加（v1 门槛）。
- 成本：O(E)=404（当前）/1600（1000 节点规模），一次几 μs 级；渲染 0 新增。

---

## 5. Q4【主战场】3D 特有视觉问题

### 5.1 深度线索（实测）
- 当前只有透视（`PerspectiveCamera fov=50`，`ev:file:graph-view-3d.js#L272-L273`），**没有雾**（全文件 grep `Fog` 无命中，属于 `unknown` 之外的确定事实）。
- 实测相机到节点距离 **1375–2447**（p50 1912），同一 world 半径的**屏幕尺寸比最大 1.78×**（bench `view3d.depth`）。
- ⇒ **在 3D 里直接加大 world 半径，会把“重要”与“离相机近”混在一起**；人没法从“大”反推“度数高”。

### 5.2 混淆避免（按成本排序）
| 方案 | 成本（实测/模型） | 评价 |
|---|---|---|
| **A. v0 只在 2D 启用大小；3D 保持等大，用度数颜色/亮度** | 0 额外（颜色已在 galaxy 实现） | ✅ **推荐**：语义干净，成本最低 |
| B. 3D 屏幕空间归一：`mesh.scale = r_screen * dist / focal` | 每帧 O(N) 次 scale 更新（1000 节点：矩阵更新约 0.1–0.3ms 量级，模型估算，未实测）；标签 sprite 同步 | 可行，但失去透视深度线索、且每帧需相机距离；**v0 不做** |
| C. 3D 大小 + 描边/光环冗余（大=重要，亮环=重要） | halo per node 增加 **1 draw/节点**（galaxy 已如此：133 节点 +133 sprite）；1000 节点 = +1000 draw（实测 1000 sprite ≈1.38ms） | 成本高，且与“颜色=度数”重复 |
| D. 加雾（Fog）增强深度 | 三角形 4 万级下雾的额外像素成本通常小；**未实测**，登记 unknown | 可作后续 A/B，不作 v0 依据 |

### 5.3 标签 sprite
- 每节点一个 `Sprite`，每个独立 canvas texture（`ev:file:graph-view-3d.js#L143-L183`；texture 尺寸 ≈ text 宽×42px）；实测 133 节点有 **116 textures**（部分被视锥裁剪），1000 labels = 1000 draw/1.38ms（bench）。
- 节点大小变化时，标签 sprite 的 `unit` 只在创建时按基础 r 算（`#L169-L171`），**不会跟着逐节点半径走** ⇒ 若节点变大 2×，标签不变，容易与球体/邻居标签重叠。
- **提案**：标签尺寸与节点**屏幕尺寸**解耦（标签始终屏幕空间固定，例如 10–14px 高）；只对最近 K 个节点 + hover/selected 显示（K≤50）；用 sprite 池复用 canvas/texture（避免每次 rebuild 重新生成 133+ texture，`_rebuildGraph` 目前全量重建 `#L411-L507`）。

---

## 6. Q5 布局本身

- 力导向参数（2D，`ev:file:graph-layout-2d.js#L8-L21`）：`linkDistance=108`、`repulsion=5200`、`alphaMin=.012`、`alphaDecay=.045`、`alphaTarget=.12`、`warmupTicks=160`、`spreadFactor=.42`；3D 同族（`graph-layout-3d.js`）。
- 斥力默认 **Barnes-Hut O(N log N)**（`ev:file:graph-layout-sim-core.js#L21`、`tryBHRepulsion #L97`），保留精确 O(N²) 作为 A/B 对照（`#L191-L192`）；Worker 阈值 `DEFAULT_WORKER_MIN_NODES=60`（`ev:file:graph-layout-worker-bridge.js#L7`），warmup 有 pair-tick 上限（注释 `#L9-L14`）。
- 分组是**并查集连通分量**（`ev:file:graph-groups.js#L9-L31`、`#L80-L98`）⇒ 对稠密图会“吞并”成超大组；实测 AAA_Vocab 默认分组 **14 组**（bench），但最大组占比未测（**unknown**，见 §9）。
- 与大小编码的关系：大小不进布局（斥力不按半径加权）⇒ 大节点会与邻居视觉重叠但布局不避让。按 linkDistance=108：建议 `rMax ≤ 108/8 = 13.5px`（我们取 12），且**不改布局**——把“避免重叠”交给标签裁剪与 hover。
- 新节点入场：现有点击/加载路径会 `resetSimulation()` 全量重排（2D `resetSimulation #L294`，3D `#L593`）；3D `_onLayoutReset → _rebuildGraph()` 会重建 133 Mesh+133 Sprite+404 Line（`ev:file:graph-view-3d.js#L237-L243`）——大规模下这是“入场卡顿”的来源，不是大小编码；登记为 v1 性能项，未测耗时（unknown）。

---

## 7. Q6 标签与视觉密度

- **2D 标签现在“每节点每帧全画”**：`drawNodeLabel` 对每个节点调用（`ev:file:graph-view-2d.js#L98-L113`、调用点 `#L660`），10px 字体、描边+填充；无避让、无视口裁剪。实测成本占比 **70–75%**（N=1500：2.91 vs 0.80ms；N=3000：6.70 vs 1.70ms）。
- **3D 标签**：每节点 sprite（1 draw/节点，`#L480-L487`），无距离裁剪；实测 634 draw 中标签占 ~116–133。
- `graph-label.js` 只有 2.2KB：仅 `resolveNodeDisplayLabel`/truncate/hover html（`ev:file:graph-label.js#L9-L52`），**没有避让算法**（无 collision/quadtree 字样）。 
- **提案（v0 成本可控）**：
  1. 2D：标签显示条件 = hover/选中/当前文件/度数 top-K/缩放≥阈值；其余不画（把 6.7ms 拉回 ≤4ms 目标）；
  2. 2D 避让若要做：**屏幕空间网格 O(N)**（只对已选中的 ≤K 标签），成本与 K 线性；不做全量标签避让（N=3000 时 O(N²) 不可接受）；
  3. 3D：最近 K 个（按相机距离排序）+ 当前文件/hover，K≤50；标签纹理用池复用。
- 成本验证方法：用 bench 脚本的 2D synthetic 变体（labels on/off）作为固定口径。

---

## 8. Q7 可测验收（成本侧，供 C 提案方合并）

| # | 可测项 | 当前基线（同机 WebView2） | 建议闸值（v0） | 测量方法（可复跑） |
|---|---|---|---|---|
| C1 | 2D `draw()` 均值/p95（133 节点/404 边） | 0.62ms | **p95 ≤2ms** | `viz_bench.py` REAL/view2d（20 reps） |
| C2 | 2D `draw()` @1000 节点（含 ≤300 标签） | 模型：无标签 ~0.6–1ms；全标签 ~2–3ms（1500 节点 2.91ms 实测） | **p95 ≤4ms** | synthetic 2D 变体 |
| C3 | 2D 标签成本占比 | 70–75%（N=1500/3000） | **≤50%**（通过显示条件裁剪） | synthetic labels on/off |
| C4 | 2D galaxy 成本倍率 | 1.53 / 0.62 = **2.5×** | **≤3×**（超过则缓存光晕或降级） | REAL nodeRadiusCost.galaxy_r6 |
| C5 | 3D draw calls @133/404 | **634** | **≤800**（133 节点不恶化） | REAL/view3d.render.calls |
| C6 | 3D draw calls @1000/1600（合并边+instancing 后） | 模型：逐 Mesh+逐 Line ≈ 1000+1000+1600+标签 K ≈ 3600+；优化后 ≈ 1（nodes）+1（edges）+K（labels）+1 | **≤1200** | synthetic 3D 表 |
| C7 | 3D `_render()` p95 @133/404 | 0.86ms | **≤8ms**（1000 节点前不应成为瓶颈） | REAL/view3d.renderMs |
| C8 | 3D geometries @133/404 | **407**（1 球 + 404 边 + 2） | **≤10**（边合并后） | REAL/view3d.render.geometries |
| C9 | 3D textures | 116/133 节点（≈1/节点） | **≤可见标签+2**（K≤50 ⇒ ≤52） | REAL/view3d.render.textures |
| C10 | 3D 标签纹理内存 | 模型：w×42×4B/标签；8 字符≈20KB；1000≈20MB | **≤32MB**（K=1000 时也安全） | 公式 + textures 计数 |
| C11 | 3D 同尺寸节点透视差 | **1.78×**（距离 1375–2447） | 若启用 3D 大小：**≤1.2×**（需屏幕空间归一）；否则 0 的大小语义 | REAL/view3d.depth |
| C12 | 2D 大节点可点中（视觉边缘） | 现命中半径全局 12px（`#L422`）⇒ r=12 时边缘点不中 | **0 miss @r−1px 环上 8 方向**（需逐节点命中半径） | 交互测试（可写 eval 侧断言） |

> 口径声明：以上均为**单机、单 WebView2、warm（第 2 次及以后）** 的 CPU 侧绘制时间；`_render()` 不含 GPU 完成（合成 3D bench 用 `gl.finish()` 卡住，真实视图的 0.86ms 只作数量级）。E4.2 8 项见 §11。

---

## 9. 性能/成本表（每种候选视觉编码）

> 2D 成本=每次 `draw()` 的 CPU 时间（实测 133 节点基线 0.62ms）；3D 成本=draw call/几何体/纹理/帧时（实测 133 节点基线 634 calls/0.86ms）。

| 编码 | 2D 成本 | 3D 成本 | 需拆共享几何体？ | 依据（实测/模型） |
|---|---|---|---|---|
| **逐节点半径（world）** | **+0**（0.56–0.65ms @r=4/6/9/12；varied vs uniform 同） | **+0**（共享 SphereGeometry + per-mesh scale 已存在：`graph-view-3d.js#L414-L445`） | ❌ 不需要 | bench REAL.nodeRadiusCost + synthetic 2D |
| 逐节点半径（屏幕空间恒显） | +0（每节点 1 次除 `k`） | 每帧 O(N) scale 更新（1000 节点≈0.1–0.3ms 模型） | ❌ | 模型 + bench matrices 参考 |
| 度数→颜色/亮度（galaxy 已有） | **+0.91ms/帧**（1.53 vs 0.62） | galaxy 增加 halo sprite：+1 draw/节点 + 1 texture/节点（133 节点 ⇒ 634→~767 calls；1000 节点 ⇒ +1000 draw） | ❌ | REAL.galaxy_r6 + 3D 现状（galaxy 未在真实 3D 下测，模型） |
| 度数→大小（2D） | +0 | — | — | 见上 |
| 度数→大小（3D） | — | +0 draw/几何（仅改 `mesh.scale`） | ❌ | 同上（galaxy 已实践） |
| 标签（2D 每节点） | **+3.0ms@1500 / +5.0ms@3000**（占总 70–75%） | — | — | synthetic 2D labels on/off |
| 标签（3D 每节点 sprite） | — | +1 draw/节点 + texture：1000 标签=1.38ms/1000 draw；纹理内存 w×42×4B | ❌（但需 **texture 池**，不是几何体拆分） | synthetic labelSprites1000 + 代码 `#L143-L183` |
| 3D 边：逐边 Line（现状） | — | 404 边=404 draw/404 geometries；1600 边=1.71ms/1600 draw | ❌ | REAL 407 geometries + synthetic edges |
| 3D 边：合并 LineSegments | — | **1 draw，1600 边 0.01ms**；每帧更新 3200 顶点 typed array（实测 0.01ms） | ❌ | synthetic edges/update |
| 3D 节点 InstancedMesh | — | 1000 节点 **0.03ms/1 draw**（vs 1.15–1.52ms/1000 draw） | ⚠️ 需要“单位球 + per-instance matrix”（几何体只需 1 个，不是拆成 N 个） | synthetic instancedMesh |
| 拾取：逐节点命中半径（2D） | +0（O(N) 循环不变） | — | — | `#L420-L435` |
| 描边/光环（当前文件） | ≈0（只画少数节点） | halo sprite 同 galaxy（+draw/节点） | ❌ | 代码 + 3D halo 现状 |
| 雾（3D 深度） | — | 像素级小开销，**未实测** ⇒ unknown | ❌ | 代码无 Fog，登记 unknown |

---

## 10. 可证伪的设计断言（每条：若观察到 X 则本条不成立）

| # | 断言 | 撤回条件（falsifier） |
|---|---|---|
| F1 | 2D 逐节点半径渲染成本可忽略（≤0.1ms@133 节点差异） | 同图 uniform vs 5 档半径的 `draw()` p95 差 >0.5ms（同机重复 5 次） |
| F2 | 2D 成本大头是标签（≥60%） | 关闭标签后 `draw()` 下降 <30% |
| F3 | 3D 逐节点半径无需拆几何体（draw/geometry 不变） | 逐节点 scale 后 `renderer.info.render.calls` 或 `memory.geometries` 增加 >5% |
| F4 | 3D 当前瓶颈是 draw call 数（>500 且随节点线性） | 1000 节点下 draw calls <100 或 `_render` 不随 calls 变化 |
| F5 | 3D 中 world 大小与透视不可区分（同尺寸候选差 >1.5×） | 实测相机距离比 <1.1×（即布局 z 深度被压平） |
| F6 | 度数分位 5 档在 133 节点上可区分 | 5 档中有两档节点数 <5 或档间屏幕直径差 <4px（A/B 视觉测试 <80% 正确率） |
| F7 | 内容长度不宜作大小驱动（动态范围 <4×） | 语料实测 span p50→max ≥4× 且用户能说出“长度”决策 |
| F8 | 卡片/FSRS 数据覆盖率不足（<60%） | 在 ≥2 个真实 KB 上 join 覆盖率 ≥90% |
| F9 | 3D 标签需裁剪（1000 标签成本 >1ms 或纹理 >32MB） | 1000 标签实测 <0.5ms 且内存 <16MB |
| F10 | 边合并后 geometries 可从 407 降到 ≤10 | 合并后仍出现逐边 geometry（实现未按提案做） |
| F11 | 屏幕空间恒显不增加 2D 成本 | 恒显版 `draw()` 比 world 版 >+0.2ms@133 |
| F12 | 大节点命中需逐节点半径（否则边缘点不中） | 在 r=12 节点视觉边缘 8 方向点击，命中率仍 100%（用现有全局 12px 命中） |

---

## 11. bench 溯源（E4.2 八项）

| 项 | 值 |
|---|---|
| 同 commit | `ff0c374c`（HEAD；`a8d5956d` task-144 之后） |
| 同语料 | `docs/example/AAA_Vocab` 的临时副本（`%TEMP%/memoria_viz/AAA_Vocab`；源库只读、未改动）；实测 133 节点/404 边/14 组 |
| 同任务集 | 2D：force r=4/6/9/12 + galaxy；3D：真实 133/404，合成 1000 节点/1600 边 |
| 同脚本 | `artifacts/agent/verify/debate/kgviz/viz_bench.py` |
| 同轮数 | 2D `draw()` 20 reps（radius 变体 15）；3D 合成 20 reps；3D 真实 10 reps；warm 后计时 |
| 冷热口径 | **warm**（首次调用丢弃）；2D/3D 均在同一 app 会话内 |
| ≥3 重复/分布 | 2D 真实值取 20 次均值；合成取 20 次均值；raw per-run 值落盘（`viz-bench.json`） |
| 原始产物 | `artifacts/agent/verify/debate/kgviz/viz-bench.json`（本机跑出，含全部字段） |
| 环境限制 | Windows + pywebview 6.2.1/WebView2、1280×860 窗口；2D/3D 面板**强制 260×560** 以模拟侧栏宽度（真实容器初始 clientWidth=0，未触发 reflow 时会得到 0ms 假数据——脚本已显式 reflow，此为测量陷阱，登记） |

---

## 12. 外部来源（仅背景，按 B5 不作裁决证据）

1. Bertin 视觉变量 / 视觉编码可靠性（[Frontiers 课程材料](https://public-pages-files-2025.frontiersin.org/articles/1671160/file/Presentation_1.pdf/1671160_presentation_1/1)）——支持“大小是低精度通道、分档优于连续”。
2. 网络可视化设计经验（[Visualizing Complexity](https://visualcomplexity.com/visualizing-complexity/)）——支持“先减少视觉元素再编码”。
3. 图绘制中的 level-of-detail / 标签密度与算法-编码分离（[UBC 课程材料](http://www.cs.ubc.ca/%7Etmm/talks/minicourse14/minicourse14-session2.pdf)）——支持“标签需按屏幕空间裁剪”。

---

## 13. unknowns（每条含 if_true_then） / not_doing

### unknowns
| id | 未知 | if_true_then（若为真则结论如何变） |
|---|---|---|
| U1 | 真实 2D `transform.k` 的典型范围（fit 后） | 若 k 常见 <0.5，则“world 大小”视觉更小，屏幕空间恒显优先级↑；F1/F11 需重测 |
| U2 | 真实 3D 在 galaxy 风格下的 draw calls/纹理（本次只测了 force） | 若 galaxy 3D 已 >1200 calls，则 C5/C6 闸值要按 galaxy 基线调整 |
| U3 | 布局 tick 的 CPU 成本（133/1000 节点） | 若 tick >8ms，则“60fps”瓶颈在布局而非绘制，Q5 需优先 |
| U4 | 雾/透明度作为深度线索的实际成本（未实现） | 若 <1ms 且提升可读性，则 3D 大小混淆可用“雾+大小”替代屏幕空间归一 |
| U5 | AAA_Vocab 最大分组占比（Union-Find 是否真吞并 132/133） | 若 >90%，则 Q5 的“分组规模不能作大小驱动”进一步坐实，且 v1 需要图聚类算法 |
| U6 | 用户对 5 档大小的 A/B 可辨率 | 若 <80%，则档数降为 3 档（直径 8/16/24） |
| U7 | 1000+ 节点真实 KB 的度分布 | 若同样长尾，则分位映射成立；若均匀，则可用线性（更低认知负担） |
| U8 | `_render()` 的 0.86ms 是否含 GPU 排队（WebView2） | 若 GPU 实际瓶颈，则 C5–C9 仍有效但 C7 需用 gl.finish 口径重测 |

### not_doing（明确不做）
1. ❌ 不实现任何代码（本文件是设计提案；`src/**` 未改）。
2. ❌ 不做 3D 大小编码（v0）：先把 2D 做对；3D 只保留颜色/亮度。
3. ❌ 不做新布局算法（Barnes-Hut 保留）；不做 Union-Find 分组替换（v1 讨论）。
4. ❌ 不引入第三方库（现有 canvas/THREE 零依赖约束）。
5. ❌ 不做卡片/FSRS/复习数据进图 payload 的契约变更（v1，需后端 + 覆盖率证明）。
6. ❌ 不做“网络/边类型”的视觉编码（边类型 100% reference，见 ontology §1，编码它=编码噪声）。

---

## 14. P2(b) 覆盖声明（本次冻结 scope 的分割）

- **checked[]**：Q1（7 个候选逐条决策门槛）、Q2（映射/上下界/缩放/成本）、Q3（degree 复用/缓存隐患/后端边界）、Q4（深度/混淆/标签/几何体）、Q5（布局参数/分组/入场）、Q6（2D/3D 标签/避让成本）、Q7（C1–C12 成本闸）。
- **not_examined[]**：`phase1-census.json`（他人测量，避免污染独立性）、其他 3 份提案（Phase 1 独立性要求）。
- **out_of_scope[]**：色彩/主题美学（graph-theme.js 的色板选择）、图例与 onboarding 文案、触屏/移动端、a11y 语义（除标注 tooltip 必需信息）、后端 KG 本体（ontology v0 已冻结）。

---

**一句话**：v0 的“节点大小”= **2D 的度数 5 档（8–24px 直径）+ 标签裁剪**；3D 不做大小（透视 1.78× 混淆），3D 要提速先把边合并、节点 instancing；所有主张都给了实测基线、成本表与 falsifier。
