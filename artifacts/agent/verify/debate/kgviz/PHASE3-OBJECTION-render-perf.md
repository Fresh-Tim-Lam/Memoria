# KGViz Phase 3 交叉异议 · D 渲染/性能（render-perf）

> **作者**：`render-perf`（D，渲染/性能视角）
> **HEAD**：`d9341bd1`（本文件写作时；Phase 1 提案冻结于 `247de134`）
> **输入**（Phase 3 允许互读，已全部读）：
> `artifacts/agent/verify/debate/PROTOCOL.md`（FROZEN，sha256 LF 归一化未在此重复计算）
> `artifacts/agent/verify/debate/kgviz/PHASE2-UNION.md`（sha256 `980f425c420d984a…`）
> `PROPOSAL-{arch-contract,todo-owner,metrics-baseline}.md` + 本人的 `PROPOSAL-render-perf.md`（sha256 `414cc66539f7985c…`）
> `PHASE3-OBJECTION-{arch-contract,todo-owner,metrics-baseline}.md` + `phase3-v2-discriminability.json`（sha `5bd0db9e…`）+ `USER-RULING-node-size-range.md`
> `docs/design/kg-ontology-v0.md`（sha256 `2f02b5552a94ef56…`）
> **约束**：本文件是 task-174 的**唯一**产物；不改 `src/**`、不改他人文件、不 commit。
> **证据身份**：`ev:file:<repo-rel>#L<n>`（行号按 `d9341bd1` 工作区核对）/ `ev:bench:<id>` / `ev:corpus:<id>` / `ev:doc:<path>#<sec>`。E1 缺身份的引用在本文件**不出现**。
> **人裁决优先**：`USER-RULING-node-size-range.md`（75%–165%、3 档、分位映射）**优先于**本文件一切档数异议；本文件只做**支撑 + 残余风险**，不翻案。

---

## 0. 结论摘要（先给可裁决结论）

| # | 冲突 | 我的 Phase 3 立场（一句话） | 与 Phase 2 的变化 |
|---|---|---|---|
| **V1** | 内容体量做备选 size 模式 | 支持 [B] 的 Phase 3 撤回（只进 tooltip）；若 v1 做，需 chars 字段 + T2 A/B | 与 [A] Phase 1 一致，[B] 已撤回，**无异议** |
| **V2** | 可辨档数 | **接受人裁决 3 档**；但「2px 判据」是**工程先验非人类实测**，v0 必须配 3 档渲染验收（T-size），失败阈值触发降 2 档 | 我从 5 档**降为 3 档**（人范围 4.5–9.9 内物理上限） |
| **V3** | sizeScale 是否必须有 | **分位映射 ≠ sizeScale（已证明）**；契约应声明 `kind:"quantile" + 相对性 + 阈值/tie 规则`，**不需要** linear/sqrt/log 枚举（[D] 已撤回，我补证明与残缺） | 新增：分位映射的 **tie 退化** 会让「每档人口均衡」失实（实测 59/35/40） |
| **V4** | 3D 大小 | 维持 **v0 不新增 3D 大小语义**；1.78× 透视混淆 + 人给定 2.2× 范围 ⇒ 最坏 **3.9×** 表观差，语义不可解释。[B] 已撤回 1.0–1.25 | 新增量化 3.9× 与「不做的收益」 |
| **V5** | 标签裁剪是否 size 前置 | **修正我自己**：标签不是**帧成本**前置（134 节点仅占 20–33% of 0.5–0.6ms），但是**可读性前置**；75% 只在 N=3000 合成场景成立。v0 必须先做标签 LOD，但不是「不然会卡」 | **我撤回「性能前置」表述**，保留「可读性前置」 |
| **V6** | 布局稳定性进 v0 | [B] 主张成立（5 次真机：两次 reset 的平均位移均值 199.4px（范围 185.6–219.2）、p90≈398px、92.5–97.8% 节点动）；但 v0 最小修法是**确定性种子 + 会话内保位**，跨会话持久化 v1 | 给可复跑分布证据，支持「v0 会话内稳定 / v1 持久化」 |
| **V7** | 埋点进 v0 | 支持 [C] 收窄后的两字段（+style/zoom）；**labelHover 逐帧写是性能反模式**，须会话末聚合 | 新增性能边界 |
| **V8** | 毛球态零新增字段 | **成立**（前端 nodes/links/groups 足够，O(N+E) 一次）；但 [B] 的阈值在**当前语料**上只命中 label 一条（labels=134>60，edgenode=3.02<4，avgdeg=6.03<8）⇒ 触发条件需重定 | 新增阈值矛盾证据 |
| **§8** | D 的跨场修正是否仍成立 | **成立**（同语料实测 collector 154 vs kb_build 198）；`kg-ontology-v0.md §5.2` **已改**，不需要新的语义裁决；**但**修正不完整：`kb_build` 会**改写 md/sidecar**（build 有副作用），且 §5.1 语料不可复现、§5.3 的 99.2% 已过期 | 新增「build 副作用 + 语料不可复现」两项残差 |

**一句话**：性能上「画得出来」不是风险（134 节点 2D draw ≈0.5–0.6ms，3D render 0.86ms/634 calls 都是预算内）；**风险在「画出来人看不懂」与「测量基线不可复现」**——后者会让 Phase 4 的裁决数字在发布后无法辩护。

---

## 1. 测量口径先行（E4.2 / E4.3 / E5 自查）

### 1.1 本文件用到的语料身份

| id | 内容 | 状态 |
|---|---|---|
| `ev:corpus:p3-live-134` | 工作区 `docs/example/AAA_Vocab` 的**现场副本**（含 126 个 md 修改、241 项 worktree 变更、265 个未跟踪文件含 146 个 `.md`；`.memoria/build/graph.json` 存在）。collector：**134 节点 / 404 边**。KB 内容文件（非 `.memoria/` 的常规文件 + `.memoria/sidecars/**`）清单 sha256 = `583ed4ed4ccf2b72…`（545 文件） | **可复跑但不可从 git 复现**（工作区脏；见 1.2） |
| `ev:corpus:p3-head-aaa` | `git archive d9341bd1 docs/example/AAA_Vocab`（169 文件）：collector **61 节点 / 154 边**；`kb_build` 同语料 **198 边** | **可从 commit 复现**（内容清单可由 archive 重算） |
| `ev:corpus:kgviz-b-1` | [B] 声明的冻结语料 | **未给可复核 manifest（见 1.2）⇒ 我方无法判定其等同上面任一项** |

> **诚实说明**：Phase 1 四家都报 133/134 节点、404 边，这个数字来自**工作区现场**（`ev:corpus:p3-live-134`），**不是任何 commit 的状态**。我用 `git archive` 复算：`ff0c374c` / `9eb0a23b` / `d9341bd1` 三个 commit 的 AAA_Vocab 全部是 **61 节点/154 边**。即：辩论用的语料在 git 里不存在，只在某台机器的工作区存在。
> ⇒ 这不是指控谁造假；是 **F1 冻结基准 / E4.2「同语料」在本次研讨会事实上未满足**。Phase 4 若直接冻结阈值，会把这批不可复现数字带进发布。

### 1.2 新发现（E4.2 违规，必须披露）

1. **工作区语料是脏的，且改动不是本任务造成的**：
   `git status --porcelain docs/example/AAA_Vocab` = **241 项**（126 个 `.md` 修改、`.memoria` sidecar/manifest 修改、**265 个未跟踪文件（含 146 个 `.md`）**、并有 `.memoria/build/graph.json` 152KB）。我**没有 revert 任何一项**。
2. **提交态与工作区语料不同**：HEAD `docs/example/AAA_Vocab` archive = 169 文件/61 KP/154 边；工作区副本 = 545 文件（md+sidecar）/134 KP/404 边。
   ⇒ 若 Phase 4 写「在冻结语料上 134 节点/404 边」，发布后任何人在干净 clone 上复跑都得到 61/154，**数字无法辩护**。
3. **`kb_build` 有副作用**（本文件 §2.3 详述）：同一份未 build 副本 collector 给 404 边；在它上面跑一次 `build_knowledge_base` 后，collector 给 **454 边**（md/sidecar 被 `strip_known_wikilink_edge_hints` 与 `save_sidecar_for_md` 改写）。
   ⇒ 「404 vs 454」不纯是函数差异，**还掺了 build 对源数据的一次性迁移**。任何 degree/边统计必须标注 **pre-build / post-build**。

### 1.3 本文件证据类型与 E4.2 状态

| bench id | 类型 | 可复跑性 / E4.2 |
|---|---|---|
| `ev:bench:phase1-viz-bench` | Phase 1 真机 canvas 2D/3D draw + 合成规模曲线（`viz-bench.json` sha256 `f53a7379bbe42dc8…`） | 同 commit/脚本/语料**齐全**；原始 json 在 repo。可引用 |
| `ev:bench:p3-live-2d-draw` | 134 节点真机 `draw()` 计时（300 次中位数、2D 面板 279×580） | 单机 5×2 组；原值见 §4.5；脚本为一次性探针（TEMP，未入库）⇒ **E4.2 记为 partial**：只支撑「量级」不支撑「1% 级比较」 |
| `ev:bench:p3-live-layout` | 134 节点真机 `resetSimulation()` 两次的位置位移 | **5 次完整分布原值**见 §3.6（E5 满足）；脚本同上一行 |
| `ev:bench:p3-frozen-calc` | HEAD archive 上 collector/degree/groups/映射占位计算 | 确定性计算，连跑 2 次逐字节一致；复现命令见 §9 |
| `ev:bench:p3-v2-pixel` | Pillow 64×64 圆半径像素差代理 | 确定性；**明确声明 ≠ 人类可辨** |

**E4.3（跨口径不可相减）声明**：本文件**不把** `ev:corpus:p3-live-134` 的数字与 `ev:corpus:p3-head-aaa` 的数字相减或直接比较；同一表内只用同一语料，跨语料只报「两个独立口径各自的值」。

---

## 2. ★ §8 跨场修正裁决（本任务唯一可能触发「改冻结本体」的入口）

### 2.1 ① 那条跨场修正现在是否仍成立？——**成立，且更强**

`ev:file:src/memoria/services/document.py#L2124-L2141`：两个函数确实分叉：
```
L2124-L2132  get_graph_data() → collect_graph_data()      ← app.js 的图数据来源
L2134-L2141  build_kb()      → build_knowledge_base()    ← build 产线
```
`ev:file:src/memoria/ui/static/app/js/app.js#L1804-L1819`：`loadGraphData()` 调 `call("get_graph_data")`，**前端只走 collector 路径**。
同语料（`ev:corpus:p3-head-aaa`，61 节点）实测：collector **154 边** vs `build_knowledge_base` 产出的 `graph.json` **198 边** ⇒ **函数差异在「同一份源数据」上可复现**（不是快照差异）。

### 2.2 ② 是否需要改本体？——**§8 这一点不需要新增裁决**（但有两处残差，见 2.3）

`ev:doc:docs/design/kg-ontology-v0.md#§5.2`（L98-L120）已经写了 2026-10-25T20:40 的更正（两条后端路径 +「前端只走 collector」+「454 那套前端看不到」）。该更正的**核心结论仍然正确**。

**我不同意把它再当成「需要改冻结文档」的入口**：D-KG-02 的语义裁决没有需要改的字句；继续改它只会增加冻结文档的变更成本，而真正的问题在下面两处**可复现性**。

### 2.3 ③ 但我发现该修正**不完整**（新证据，供 Phase 4 决定是否现在改）

**残差 A（影响：所有边数/degree 数字；必须现在处理）**
「两条路径」不是同一份源数据的两个只读视图：**`kb_build` 会改写源 md 与 sidecar**。
```
ev:file:src/memoria/graph/kb_build.py#L293-L298   strip_known_wikilink_edge_hints + open(full,"w")  ← 改 md 正文
ev:file:src/memoria/graph/kb_build.py#L312        save_sidecar_for_md(...)                            ← 改 sidecar
```
实测（同一临时副本，`ev:corpus:p3-live-134` 的未 build 快照）：
```
before build : collector 404 edges
after build  : collector 454 edges（同目录再 collect）
```
⇒ 「404 vs 454」= **函数差异 + build 对源数据的一次性迁移**；本体 §5.2 把它写成纯「两条后端路径」，**低估了 build 的写副作用**。
影响面：节点大小 = degree ⇒ 图里节点大小会随「该 KB 有没有跑过 build」变化；若发布说明/验收未记录 build 状态，用户会看到「同一 KB 两次打开大小不同」——这正是要避免的「看起来有、实际没有」类问题。
建议（不新增语义裁决，只加一句冻结约束）：`kg-ontology-v0.md §5.1/§5.2` 增补「**任何边/degree 测量必须记录 build 状态（pre/post + build 产物 sha）**」。是否现在改：**必须现在改（1 句注释级）**，否则 Phase 4 的 KGViz 验收会在发布后被 build 与否推翻。需 Lead/人重签（冻结文档）。

**残差 B（影响：毛球态 negative gate 阈值；建议现在改）**
`ev:doc:docs/design/kg-ontology-v0.md#§5.3`（L134）写「最大分组占比（99.2% 能可靠判"没修好"）」。
我的实测（同算法 `computeGraphGroups` Union-Find，`ev:corpus:p3-live-134`）：**15 个分量，最大 120/134 = 89.55%**；`ev:corpus:p3-head-aaa`：11 分量，最大 50/61 = 81.97%。
D 在 Phase 3 已自认 132/133=99.2% 是**更早语料**的过期数字（`PHASE3-OBJECTION-arch-contract.md#L338-L351`）。
⇒ 冻结文档里的 99.2% 在当前可复现的两个语料上都**达不到**（82% / 89.6%）⇒ 作为 gate 阈值它**永远不会触发**，等于该 gate 不存在。
建议：改成「按实测区间 80%–90% 设为 **>80% 即触发**，且必须同时显示实际数值与语料身份」，并注明 99.2% 为过期快照。是否现在改：**建议现在改**（Phase 4 要用它做 V8 验收）；不改的代价是 Phase 4 冻结一个永不触发的 gate。

**残差 C（影响：所有 Phase 1 数字；必须现在处理，但不需要改裁决语义）**
§5.1 冻结语料写明「182 文件 / sha 051deb78…」；我在当前 HEAD 上**无法复现**：`git archive HEAD docs/example` = **218 文件**、sha 不同；`docs/example/AAA_Vocab` 子树 169 文件；工作区副本又是 545 文件（md+sidecar）。⇒ §5.1 的「冻结语料」本身不可复核（F1 违规）。
建议：Phase 4 冻结前**重新冻结语料**（commit + path + 内容 manifest sha256 + build 状态），并把本次 `ev:corpus:p3-live-134` 的 manifest sha `583ed4ed…` 作为候选快照之一；否则所有「133/134 节点、404 边」的裁决在发布后无法重算。

**§8 一句话裁决**：**D 的发现成立、且已在 §5.2 更正；不需要新的语义裁决。但冻结本体需要 3 处小修（build 状态、§5.3 阈值、§5.1 语料），这些是「可复现性/阈值」问题，不是「图谱设计」翻案。建议 Lead 把 3 处打包成人可批的最小 diff。**

---

## 3. V1–V8 逐条表态（打别人 + 自证）

### V1 内容体量做不做备选 size 模式 —— 无异议（接受 [B] 撤回）

- [B] 已在 Phase 3 撤回 v0 要求（`PHASE3-OBJECTION-todo-owner.md#§1.3`），与 [A] Phase 1 立场一致：**只进 tooltip**。
- 我补一条 v1 准入条件（若将来做）：`nodes[]` 没有 chars 字段（`ev:file:src/memoria/graph/collector.py#L61-L70` 9 字段）；用行跨度代理只有 **p50=105→max=327 = 3.1×** 的动态范围（[A] Phase 1 实测），不足以驱动 3 档；要做 chars 必须新字段 + A/B T2。
- **falsifier**：若 T2（比厚度）在 chars 模式下 accuracy ≥80% 且中位耗时 ≤15s、显著优于 tooltip 对照组 ⇒ 我撤回「只进 tooltip」的 v0 立场（升级 v1 候选）。

### V2 可辨档数 —— **接受人裁决 3 档**，但把「判据来源」和「验收」钉死

人裁决（`USER-RULING-node-size-range.md`）：范围 4.5–9.9px、**3 档**、按 **A 的 ≥2px 判据**、2.70px 步长。我接受，且这正是我 Phase 1 判据在**更窄范围**下的算术结果（我 Phase 1 的 5 档对应直径 8–24px；人把上界压到 9.9px 后，2px 半径步长最多 3 档）。

**但必须写清（防第二次误读）**：
1. **「2px 判据」是我的工程先验，不是人类实测**。我在 Phase 1 写「档间屏幕直径差 ≥4px（半径 2px）」，依据是 Bertin 类「大小是低精度通道 + 分档优于连续」+ 4px 步长在 133 节点密度下的保守估计；**没有人类判读数据**。C 的 Phase 3 已正确指出我这条「同样是猜的且未标注」——我接受该批评，并在此**正式标注为 heuristic**。
2. 用户裁决采用它是**policy**（比 DS-1 实验更快更准），不是 measurement；因此 **v0 必须配验收**：渲染 3 个 quintile 节点，做「挑出最大的 3 个」任务（15 trials/人，n≥5），**accuracy ≥90%** 才发布；若 <80% ⇒ 按人裁决 §4 的降级路径降为 2 档（步骤 5.4px）。
3. **分位映射的 tie 退化**（新证据，直接影响「3 档」落地）：`ev:corpus:p3-live-134` 的 degree 大量并列（distinct 21 / 134 节点），按 1/3、2/3 分位切 3 档实测人口 = **59 / 35 / 40**（不是 45/45/44）；即 **44% 节点挤在最小档 4.5px**。如果 Phase 4 采用「分位映射 ⇒ 每档人口均衡」的说法，需要额外定义 **tie 规则**（按节点 id 稳定排序补足，或允许不均并在 tooltip 显示档位）。
4. **物理量（像素）**：`ev:bench:p3-v2-pixel`（Pillow 64×64，仅代理）显示 r4.5→r7.2 改变 3.03% 像素、r7.2→r9.9 改变 2.64%；r6→r8（2px 步长）2.25%。**这组数字不是人类可辨性**——真机有反锯齿 +1px 常量（C 的 `render_margin` 9 行全部 overflow=1.0，`phase3-v2-discriminability.json`），差分时抵消，不改变 3 档算术。
- **falsifier**：真人验收 accuracy <80% ⇒ 降 2 档；若某天 DS-1 测出 2px 不可辨 ⇒ 3 档作废（人裁决已给降级路径）。

### V3 sizeScale 是否 v0 必须有 —— **分位映射 ≠ sizeScale；契约需要声明的是「相对性 + 阈值」，不是枚举**

[D] 已在 Phase 3 撤回「必须」（`PHASE3-OBJECTION-arch-contract.md#§3`）。我用两条证据把「不等价」钉死（这是本任务点名要的）：

**(1) 数学构造**：分位映射是 **rank / 经验 CDF** 变换：
`r(d) = bins[#{d' ≤ d} / N]`，阈值 = 当前语料的经验分位数；`sizeScale ∈ {linear, sqrt, log}` 是**参数化值变换** `r = rmin + (rmax-rmin)·f(d/dref)`，两者类别不同：
- 分位映射**没有固定 dref**：阈值随语料变。
- 值变换**不保证每档人口**：人口由分布决定。

**(2) 实测不可互相表达**（`ev:corpus:p3-live-134`，同一 degree 序列）：
```
degree=5 在 live 语料分位映射 → r=8；若语料换成 degree 0..25 均匀分布，同一 degree=5 → r=4
（阈值：[0,3,4,6,9,25] vs [0,5,10,15,20,25]）
⇒ 同一语义值（degree=5）在两种语料上映射到不同半径 ⇒ 「分位映射」等价于「相对编码」而非绝对 sizeScale
```
同一语料上，线性/sqrt/log 的人口分布也完全不同（live 语料 5 档：linear `[41,66,20,4,2]`、sqrt `[13,28,66,23,3]`、log `[13,11,59,45,5]`、quantile `[41,17,25,24,26]`）⇒ **分位不是三者中任何一个的换元**。
**结论**：契约必须写 `sizeMapping.kind: "quantile"` + `thresholds`（或 `tiePolicy`）+ **`relative: true`**（同一节点在不同 KB 中大小不同，tooltip 必须显示 degree 与档位）；写 `sizeScale: linear|sqrt|log` 反而**无法表达**人裁决选定的分位方案。D 的「契约要可表达」诉求成立，但它要的字段名错了——Phase 4 应冻结 `kind/tiePolicy/relative` 三元，而不是 `sizeScale` 枚举。
- **falsifier**：若能构造一个 `sizeScale` 参数组合，在 **≥3 个不同度分布语料**上同时复现分位映射的档位人口（±5%）⇒ 我撤回「不等价」。

### V4 3D 大小 —— **维持 v0 不做**；量化 1.78× 与「不做的收益」

**(1) 透视混淆量化**（引用 Phase 1 真机 bench，**跨口径声明**：该数字来自 133 节点工作区语料，不与 §1 的 134/61 数字相减）：
```
ev:bench:phase1-viz-bench real3d: fov=50, cameraPos [-273.3, 0.97, 1820.45]
nodeDistanceMin=1374.88  nodeDistanceMax=2447.01  p50=1912.43
apparentRadiusRatioMax = 2447.01/1374.88 = 1.78
```
**(2) 与 user 范围叠加**：人给定半径 4.5–9.9 ⇒ 重要性本身最大 2.20×。3D 里表观大小 ∝ 半径/距离，最坏组合：
`(9.9/1374.88) / (4.5/2447.01) = 3.92×`
⇒ 一个**不重要**的节点可以看起来比**重要**节点大近 4 倍；「大 = 重要」在 3D 中不可解释。
**(3) 为什么「不做」比「做」好**（不是成本问题）：
- 3D 的成本完全够：`ev:bench:phase1-viz-bench` real3d = 634 calls / 407 geometries / 116 textures / **0.86ms**；galaxy 分支已经是**共享 SphereGeometry + mesh.scale**（`ev:file:src/memoria/ui/static/app/js/graph-view-3d.js#L414-L434`：`_nodeGeo` 共享，`scale = 1 + ratio*0.4`）⇒ **逐节点大小 = 0 额外几何/0 额外 draw calls**。所以 D 隐忧的「要拆共享几何体」不存在，[D] 也已撤回（`PHASE3-OBJECTION-arch-contract.md#§0.2`）。
- 真正的代价是**语义/交互**：若做屏幕空间归一（scale ∝ 距离），环绕/缩放时节点大小会连续变化 ⇒ 用户会把「大小在动」误读成数据在变；且消除透视深度线索（3D 只剩 fog/透明度，而当前 fog=False）⇒ 深度任务更差。
- 2D 已经承载 size；3D 的任务定位是「探索/找关系」，不是「比大小」（与 KG 本体辩论 Q6 一致）。
- 现有 3D galaxy 的 `scale=1+ratio*0.4`（1.0–1.4）是**既有装饰**，v0 **不扩大、不接线到默认 force**；若要保留，文档必须标「非语义」。
- **falsifier**：若真人 3D 深度任务（V-08「谁更近」）在 1.78× 混淆下仍 ≥80%，且「大小+归一化」组显著优于「等大+颜色」组 ⇒ 我撤回「v0 不做 3D 大小」。

### V5 标签裁剪是否 size 前置 —— **修正我自己：不是帧成本前置；是可读性前置**

**Phase 1 我说的「标签占 75% 成本」在什么范围成立**（`ev:bench:phase1-viz-bench` synth2d）：
```
N=800 : nodes_only 0.44 vs with_labels 1.57 ⇒ 标签 +1.13ms（72%）
N=1500: 0.86 vs 2.82 ⇒ +1.96ms（69%）
N=3000: 1.64 vs 7.07 ⇒ +5.43ms（77%）
```
**在真实 v0 规模（134 节点）不成立**（`ev:bench:p3-live-2d-draw`，2D 面板 279×580，300 次 draw 中位数）：
```
无标签 0.4ms → 有标签 0.5–0.6ms（3 次运行：0.6/0.5/0.6），标签占比 20%–33%
若把 fillText/strokeText 全禁：draw 中位数 0.4ms，与有标签差 0.0–0.2ms（低于计时噪声）
```
⇒ **修正**：我 Phase 1 的「上大小编码前必须先做标签裁剪（性能理由）」**在 v0 语料规模下不成立**；它只在 N≥800 成立。但标签仍是 **可读性前置**：134 个 10px 标签**无条件全画**、无避让（`ev:file:src/memoria/ui/static/app/js/graph-view-2d.js#L98-L114, L700`），节点半径变大后重叠只会更糟；且按 [B] 的阈值 labels>60 当前已命中。
**因此 v0 顺序保留「先标签 LOD、后大小」**，但理由改为**可读性**，不是「不然会掉帧」。LOD 成本：隐藏标签 = 少一次 fillText/strokeText（每标签 ~µs 级）；不做 sprite 池也能在 v0 用绘制条件实现。
- **falsifier**：若实测 134 节点有标签 draw ≥16.7ms（60fps 预算）⇒ 恢复「性能前置」；若标签 LOD 后找节点任务（V-06 中位 ≤15s）无改善 ⇒ 标签不是可读性瓶颈，我撤回「前置」排序。

### V6 布局稳定性进不进 v0 —— [B] 主张成立；我支持「v0 会话内稳定 / v1 跨会话持久化」

**代码证据**（[B] 的主张我独立核实）：
- 随机初始位置：`ev:file:src/memoria/ui/static/app/js/graph-layout-2d.js#L37-L51`（`Math.random()` 角度/半径）
- 每次 setGraph `alpha = 1`：`ev:file:src/memoria/ui/static/app/js/graph-layout-2d.js#L244-L250`
- 无 seed/无位置持久化（全文件无 `seed`/`localStorage`/位置存储）

**真机量化**（`ev:bench:p3-live-layout`，134 节点，同一 app 会话内 `resetSimulation()` 两次、各 settle 2.5s；5 次独立运行，逐次原值）：
```
run1 mean=219.2 median=199.5 p90=468.5 max=708.5  moved>1px=93.3%
run2 mean=199.4 median=174.8 p90=395.8 max=589.7  moved>1px=97.8%
run3 mean=193.7 median=176.0 p90=398.5 max=903.8  moved>1px=95.5%
run4 mean=185.6 median=157.8 p90=383.3 max=732.0  moved>1px=95.5%
run5 mean=210.6 median=181.4 p90=442.6 max=749.2  moved>1px=92.5%
median(5) = 199.4px；min–max = 185.6–219.2px；p90 中位 ≈ 398.5px
```
⇒ 「每次打开都大跳」成立（中位单节点动 ~200px、p90 ~398px、92.5–97.8% 节点动）。用户无法建立空间记忆。

**但 v0 的最小修法不是持久化**：跨会话持久化要新增 ui_settings 键 + graph hash 校验 + 陈旧布局失效策略（成本/风险都高于 v0 收益）；**确定性种子**（`seed = hash(KB path + graph content digest)`）即可让「同图每次打开位置一致」，且**零存储**。建议：
```
v0：seeded PRNG + 同 hash 下复用引擎内位置（会话内）+ 换图才 reset（≤1 处函数，约 10 行）
v1：ui_settings 持久化 + 「重新布局」显式按钮（与人裁决 §5② 一致）
```
- **falsifier**：若 seeded 后同图两次 open 的位置位移仍 p90 >100px（种子没覆盖布局随机源，例如 worker 侧另有随机）⇒ v0 也必须做持久化（升级范围）。

### V7 埋点进 v0 —— 支持 [C] 收窄后两字段；给性能边界

- [C] 已把四字段收窄为两字段（`PHASE3-OBJECTION-metrics-baseline.md#§3.3`），[D] 对 `node_radius_px`/`node_degree` 的「派生字段契约」异议（`PHASE3-OBJECTION-arch-contract.md#§7.2-7.3`）成立：埋点里应记**渲染值 + 当时参数**（例如 `radius_px`、`sizeMode`、`quantileThresholds`、`degree` 与 `degreeSource:"collector"`），否则同一 radius 不可解释。
- **性能边界（我的职责）**：`nodeClick` 每点击 1 次 = 1 次内存记录，成本 ~µs；`zoom` 必须**在手势结束/节流末**记 1 次（禁止 per-frame），`labelHover` **v0 不做**（mousemove 高频，逐事件写会制造 0.1–1ms/帧级抖动，反而变成新的性能问题）；若将来做，只累计「会话结束时的 hover 次数/时长」。
- 隐私：接受 [C] P1/P2（不记正文、不建画像）作为硬边界。
- **falsifier**：若交互 bench 显示加入埋点后 typing/draw 退化 >5% ⇒ 我要求所有逐事件埋点退化为聚合计数。

### V8 毛球态零新增字段 —— **成立**；但 [B] 的阈值组合在当前语料自相矛盾

**证明「前端够用」**：
- 所需量：节点数、边数、平均度、最大分组占比、标签数 —— 全部由已加载 payload 可得：
  `ev:file:src/memoria/ui/static/app/js/graph-groups.js#L83-L121`（Union-Find 计算 groups，含 size）
  `ev:file:src/memoria/ui/static/app/js/graph-view-2d.js#L583-L596`（`_galaxyStats` degree Map）
  `ev:file:src/memoria/graph/collector.py#L61-L70`（node 9 字段，无 group/degree；**不需要新增**）
- 成本：一次 Union-Find = O(N+E)，134 节点/404 边下 <0.1ms 量级（同 `_galaxyStats` 每次 load 一次）；不需要后端字段、不需要 RPC。
⇒ [D] 的「零新增字段」方向成立（`PHASE3-OBJECTION-arch-contract.md#§8` 也只要求「统一分组口径」，不是新增字段）。

**但阈值存在问题**（`ev:corpus:p3-live-134`）：
| [B] Phase 1 阈值 | 当前语料实测 | 是否命中 |
|---|---|---|
| labels > 60 | **134** | ✅ 命中（且远超） |
| edges/nodes > 4 | **404/134 = 3.02** | ❌ |
| 平均度 > 8 | **6.03** | ❌ |
⇒ 若 Phase 4 直接照抄「三条件任一成立」，该图**开局即毛球态**（因为标签永远 >60），提示会常驻——这就是「阈值不是为了触发而写」。必须改成**组合条件或按实测校准**：例如 `labels>60 且 (edges/nodes>4 或 maxGroupShare>0.85)`，或把标签条件改成 `标签总宽/画布面积`（更贴近可读性）。另：Union-Find 分组本身语义不可用（最大组 89.55%），所以 **group 只能当最大占比指标，不能当视觉分组**。
- **falsifier**：若交互测试显示「常驻提示」不影响使用（用户可忽略且不误操作）⇒ 阈值矛盾降级为文案问题；若分组算法在真实 KB 上不是 90% 单组 ⇒ 我撤回「分组语义不可用」。

---

## 4. 自证四题（本任务点名）

### 4.1 V3 自证：分位映射 ≠ sizeScale（见 §3-V3 完整证明）
摘要：rank 变换 vs 参数值变换；同一 degree 在不同分布语料映射到不同半径（实测 deg=5 → 8 vs 4）；人口分布不可互换（quantile `[41,17,25,24,26]` vs linear/sqrt/log）。契约应写 `kind:"quantile" + relative + thresholds/tiePolicy`。

### 4.2 V4 自证：1.78× 量化 + 为什么不做（见 §3-V4）
摘要：透视距离比 1.78；叠加人范围 2.2× ⇒ 最坏表观 3.92×；3D 成本不是问题（共享几何 + scale，0 额外 draw），问题是语义不可解释 + 环绕期大小抖动；v0 不做，保留既有 galaxy 装饰但标非语义。

### 4.3 V8 自证：前端分组够用（见 §3-V8）
摘要：groups 由 `graph-groups.js` 前端算，O(N+E)；实测 15 分量/最大 89.55%；零新增字段成立；但阈值组合需按实测校准，且 group 不可当视觉分组。

### 4.4 V5 自证：标签占 75% 成本（见 §3-V5）
摘要：75% 只在合成 N=3000；真实 134 节点 20–33%（0.4→0.5–0.6ms）。**我撤回性能前置表述**，保留可读性前置。

### 4.5 帧预算总表（用户问「画出来会不会卡」）

| 场景 | 实测 | 成本判断 |
|---|---|---|
| 2D 134 节点全量 draw（含 134 标签 + 404 边） | **0.5–0.6ms**（`ev:bench:p3-live-2d-draw`，279×580 canvas） | 60fps 预算 16.7ms 的 **3–4%**，无压力 |
| 2D 节点半径 4/6/9/12 变化 | 0.56–0.65ms（`ev:bench:phase1-viz-bench`，差异在噪声内） | **大小编码本身零增量**；无需共享几何体（2D 本来就是逐节点 arc） |
| 2D 每节点标签（N=3000 合成） | +5.43ms（1.64→7.07） | **只有超大图才成为瓶颈**；v0 134 节点不需要 sprite 池 |
| 3D 134 节点 render | 634 calls / 407 geometries / 116 textures / **0.86ms**（`ev:bench:phase1-viz-bench`，跨口径） | 预算内；逐节点大小用共享 `_nodeGeo`+`mesh.scale` ⇒ **0 额外 draw calls**（`graph-view-3d.js#L417,L434`） |
| 布局 reset | 2.5s settle（非帧成本，是打开时的一次性成本） | 可接受；seed 后仍是同量级，**不会增加帧成本** |

⇒ **帧预算不是本设计的关键闸门**；关键闸门是「可读性验收」与「测量可复现」。

---

## 5. 「画成这样人能不能看懂」——比帧预算重要（Lead 点名）

**结论先行**：按当前设计（2D 3 档大小 + 全量标签），**人能看出「大小有差别」，但看不出「这是重要性的差别」**，因为：
1. **大小与标签相互干扰**：134 个标签无避让，节点变大后标签重叠更严重；大小差异会被标签密度淹没（需要 LOD 后重测）。
2. **3 档对应的面积比**（人裁决 4.5/7.2/9.9）：面积比 1:2.56:4.84（`(9.9/4.5)^2`）；中间档 7.2 与 4.5 的面积差 +156%，可辨性在物理上足够，但**语义上没有任何东西告诉用户「大小 = 被引用次数」**——必须有 legend/tooltip（`degree=5（档 2/3）`）。
3. **3D**：如 V4，深度混淆与重要性通道重叠 3.9× ⇒ 3D 里大小不可解释；若坚持 3D 大小，用户必须做「先判断远近再判断大小」的两步推理，任务成功率无数据支持。
4. **双编码冲突**：galaxy 风格现在把 degree 同时编进颜色与半径（`ev:file:src/memoria/ui/static/app/js/graph-view-2d.js#L669-L687`），人无法判断「大且蓝」是两倍重要还是一次编码；v0 必须二选一（默认 force 用大小，galaxy 用颜色，禁止双编码）。

**建议的可测判据（v0 验收，替代「好不好看」）**：
| 任务 | 操作 | 通过阈值 | 采集方式 |
|---|---|---|---|
| T-size（大小语义） | 给图 + legend，问「下列 3 个节点哪个被引用最多」 | accuracy ≥90%（15 trials ≥5 人）| 真人 A/B（DS 类）；无埋点也可纸面/远程 |
| T-label（标签可读） | 给名字，找节点并点击 | 中位 ≤15s（[C] V-06 原阈值）| 需埋点或屏幕录制 |
| T-depth（3D） | 给图问「A/B 谁更近」 | accuracy ≥80%（若 3D 做大小则必须过）| 真人 A/B |
| T-double（双编码） | 问「颜色和大小的含义是否相同」 | 正确回答 ≥90% 或 legend 明确二选一 | 真人访谈 |

**如果只能做一件事**：先做标签 LOD + legend/tooltip（成本低、直接改善「看懂」），再做 3 档大小；否则大小差异会被标签噪声掩盖，等于又回到「人看不出大小」的原始抱怨。

---

## 6. 对他人具体主张的异议清单（§12 要求「必须打别人的」）

| 编号 | 被异议主张（来源） | 我的异议 | 证据 | 撤回条件 |
|---|---|---|---|---|
| D-O1 | [B] 「12–13 档可辨」（Phase 1） | **物理上不成立**：人范围 4.5–9.9px 下 12 档相邻半径差 ≈0.49px < 反锯齿 1px 常量 | 人裁决 §3；`phase3-v2-discriminability.json` render_margin overflow=1.0 | [B] 已撤回（`todo-owner#§1.1`），本条关闭 |
| D-O2 | [C] 「3px 判据 ⇒ 4 档」 | 3px 判据在**人给定范围**下只给 2 档，不能把 C 的 4 档与 A 的 3 档混引 | 人裁决 §3-4（3 档依据 A 的 2px，非 C 的 3px） | 若 DS-1 证明 3px 才是真阈值 ⇒ 档数按 2 档改，我撤回对 C 判据的适用范围异议 |
| D-O3 | [B] 「布局稳定性是 v0 硬伤」 | 证据成立（5 次真机）但**单根**，且 v0 最小修法是确定性种子而非持久化；「空间记忆是 v0 目标」无证据 | 本文件 §3-V6 五组原值；`graph-layout-2d.js#L37-L51,L244-L250` | [B] 已主动降级（`todo-owner#§1.2`）；若真机 A/B 显示 seed 后任务仍失败 ⇒ 升级持久化 |
| D-O4 | [B] 「标签是比大小更严重的问题」 | 方向同意，但**成本理由不适用 v0 规模**（134 节点 20–33%、0.5–0.6ms）；严重性在可读性不在帧率 | 本文件 §3-V5；`phase1-viz-bench` synth2d 表 | 若 134 节点带标签 draw ≥16.7ms 或标签导致的找节点任务不达标 ⇒ 我撤回「成本不是前置」 |
| D-O5 | [D] 「3D 逐节点尺寸要拆共享几何体」 | 不需要：galaxy 分支共享 `_nodeGeo` + `mesh.scale`（`graph-view-3d.js#L417,L434`）；真成本是语义不是几何 | 同左；[D] 已撤回（`arch-contract#§0.2`） | 关闭 |
| D-O6 | [C] 埋点四字段（Phase 1） | 方向对但**逐事件写有性能风险**；收窄为 2 字段 + zoom 手势末聚合；labelHover 延后 | 本文件 §3-V7 | 若交互 bench 显示埋点退化 >5% ⇒ 全面改聚合 |
| D-O7 | [D] 「零新增字段」（V8） | 成立，但**分组口径必须统一**且 group 不可当视觉分组（最大组 89.55%）；[B] 阈值组合当前语料自相矛盾 | 本文件 §3-V8 实测表 | 若分组算法改进后最大组 <50% ⇒ group 可作视觉分组，我撤回「不可用」 |
| D-O8 | 冻结文档 §5.3「99.2% 可判没修好」 | 当前可复现语料为 81.97%（HEAD）/ 89.55%（live），99.2% 是过期快照；阈值永不触发 | §2.3 残差 B | 若存在一份可复现语料其最大组占比 ≥99% ⇒ 我撤回「过期」判断，但需给语料身份 |

---

## 7. unknowns（P4：必须带 `if_true_then`）/ not_doing

| id | 未知 | if_true_then（对结论的影响） |
|---|---|---|
| U-P3-1 | 真人可辨档数（2px 判据是否正确） | 若真实阈值是 3px ⇒ 3 档降 2 档（人裁决已写降级路径）；若 1.5px 可辨 ⇒ 可在同范围内做 4 档 |
| U-P3-2 | 冻结语料在本机 HEAD 不可复现（§5.1 sha 051deb 对不上） | 若 Phase 4 能提供冻结语料 commit+manifest ⇒ 所有 133/134/404 数字可升级为可复现；否则 Phase 4 数字只能标「一期快照，不可重算」 |
| U-P3-3 | 3D 深度比在可复现语料上的实际值（本任务 3D 面板未进入 active/layout-ready，未能复测；1.78 来自 Phase 1 跨口径） | 若实测 <1.2 ⇒ V4 的「3D 不可解释」强度下降（但仍需屏幕归一）；若 >2 ⇒ 更强 |
| U-P3-4 | 用户真实 KB（`D:\AAA_Courses\软件工程概论`，133+ KP）的度分布是否同长尾 | 若同长尾 ⇒ 分位/3 档映射可沿用；若均匀 ⇒ 应改 sizeScale 绝对映射（我愿改判） |
| U-P3-5 | build 跑过之后用户看到的大小是否与文档一致（build 副作用） | 若 build 后 collector 边数变化导致可见大小变化 ⇒ 必须在 tooltip/说明中标注 build 状态，否则用户会认为 bug |
| U-P3-6 | 埋点事件对真实交互帧的影响 | 若 >5% 退化 ⇒ 全部埋点聚合化 |

**not_doing（本轮明确）**：不修改 `src/**`；不做真人实验（无被试）；不评价「好不好看」；不为超大图（1000+）做 sprite 池/instancing（等有真实 1000+ KB 再做）；不写 Phase 4 裁决（那是 Lead 职责）。

---

## 8. 复跑命令与环境（E4.2 最低可复现信息）

**环境**：Windows 10/11，Python 3（repo `.venv`），Node（probe），WebView2 / Edge 155；repo HEAD `d9341bd1`。
**语料**：
```powershell
# 工作区现场副本（辩论语料；脏，含 126 md 修改 + .memoria/build）
robocopy docs\example\AAA_Vocab $env:TEMP\memoria_p3_corpus /E /NFL /NDL /NJH /NJS /NP
Remove-Item $env:TEMP\memoria_p3_corpus\.memoria\build -Recurse -Force  # 避免 build 缓存
# 内容清单 sha（md+sidecar）: 583ed4ed4ccf2b72…（545 文件）
# 提交态对照：
git archive d9341bd1 docs/example/AAA_Vocab -o $env:TEMP\av_head.tar   # collector 61/154
```
**计算（collector/degree/groups/映射）**：
```powershell
.venv\Scripts\python.exe -c "import sys;sys.path.insert(0,'src');from memoria.graph.collector import collect_graph_data;d=collect_graph_data(r'$env:TEMP\memoria_p3_corpus');print(len(d['nodes']),len(d['edges']))"
# ⇒ 134 404
```
**真机 2D draw / 布局位移探针**（本次用 `%TEMP%\kgviz_p3_probe.py`，launch_ctl + probe112；一次性脚本，未入库）：
```
打开 2D 图谱 tab（先点 #btn-toggle-sidebar 展开侧栏）→ 等 simNodes>0
draw 计时：v.draw() ×300 中位数；标签成本：patch CanvasRenderingContext2D.prototype.fillText/strokeText 为空实现后同测
布局：record simNodes 坐标 → v.resetSimulation() → settle 2.5s → 再 record → 重复一次
```
**像素代理**（Pillow，64×64 圆）：`r4.5→7.2 changed_ratio=0.0303；r7.2→9.9=0.0264；r6→8=0.0225` —— **仅渲染差异代理，不是人类可辨数据**。
**证据索引**：
- `ev:file:src/memoria/ui/static/app/js/graph-view-2d.js#L10,L98-L114,L422,L669-L687`
- `ev:file:src/memoria/ui/static/app/js/graph-layout-2d.js#L37-L51,L244-L250`
- `ev:file:src/memoria/ui/static/app/js/graph-view-3d.js#L396-L434`
- `ev:file:src/memoria/ui/static/app/js/graph-groups.js#L83-L121`
- `ev:file:src/memoria/ui/static/app/js/app.js#L1804-L1819`
- `ev:file:src/memoria/services/document.py#L2124-L2141`
- `ev:file:src/memoria/graph/kb_build.py#L293-L312`
- `ev:file:src/memoria/graph/collector.py#L61-L70`
- `ev:doc:docs/design/kg-ontology-v0.md#§5.1,§5.2,§5.3`
- `ev:bench:phase1-viz-bench`（`viz-bench.json` sha `f53a7379…`）；`ev:bench:p3-live-2d-draw` / `ev:bench:p3-live-layout` / `ev:bench:p3-frozen-calc` / `ev:bench:p3-v2-pixel`（本文件 §1.3 记录原值与边界）
- `ev:corpus:p3-live-134`（manifest sha `583ed4ed…`）/ `ev:corpus:p3-head-aaa`

---

## 9. 我要求 Phase 4 直接写入 v0 文档的条款（按优先级）

```
P0（否则数字发布后无法辩护）
  V0-1 语料冻结：commit + path + 内容 manifest sha256 + build 状态（pre/post + build sha）
       基线候选 = ev:corpus:p3-live-134（manifest 583ed4ed…）或重新冻结
  V0-2 边/degree 数字必须标注「collector 路径」与 build 状态；禁止引用 .memoria/build 数字作设计依据
P1（人裁决落地必需）
  V0-3 大小：4.5–9.9px、3 档（依据 A 的 2px heuristic，非人类实测）、分位映射 + tiePolicy + relative:true
  V0-4 tooltip/legend 必须给出 degree 与档位（否则大小无语义）
  V0-5 标签 LOD 先于大小（可读性理由）；134→标签数阈值按实测校准
  V0-6 禁止双编码（galaxy 颜色与大小同源二选一）
  V0-7 3D v0 不新增大小语义；既有 galaxy 装饰标「非语义」
  V0-8 毛球态：零新增字段 + 前端 Union-Find；阈值用实测（如 >0.80–0.85），不用过期 99.2%
  V0-9 验收：T-size（≥90%）、T-label（≤15s）、T-depth（≥80%，仅当 3D 做大小）、T-double（≥90%）
P2（v1）
  V1-1 布局跨会话持久化（ui_settings + graph hash + 失效策略）
  V1-2 内容体量模式（chars 字段 + T2 A/B）
  V1-3 埋点扩展（labelHover 聚合、review 色）
```

---

*本文件是 task-174 唯一产物；写作于 HEAD `d9341bd1` 工作区。未 commit，未改任何 `src/**`，未 revert 他人改动（`docs/example` 的脏状态在 §1.2 披露）。*
