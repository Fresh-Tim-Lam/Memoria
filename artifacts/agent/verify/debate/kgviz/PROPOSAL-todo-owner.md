# KG 可视化设计辩论 Phase 1 — B 学习场景 / 产品提案

> 提案方：`todo-owner`（B 学习场景 / 产品）｜2026-10-25
> **独立性声明**：未读取 `PROPOSAL-{render-perf,metrics-baseline,arch-contract}.md`；先读代码 + 真实库 + 学习场景，最后对照 `docs/design/kg-ontology-v0.md`。
> **证据口径**：`ev:file:<path>#L<n>`；数据冻结 `ev:corpus:kgviz-b-1`（见 §7）；本提案**不假设任何语义边**（ontology v0：reference 无断言、v0 不加语义类型）。

---

## 1. 立场摘要（≤10 行）

1. **节点大小必须有且只有一个数值驱动因子，且该因子服务一个可测的用户决策**；默认 = **入度（被引用次数）**，服务「哪些概念被最多条目引用（枢纽/常用）」——不称"重要性"（reference 边无断言，见 ontology §2）。
2. **备选模式 = KP 内容体量（行跨度/chars）**，服务「哪块内容最厚/阅读成本」；两种模式互斥，用户切换，不叠加。
3. **其余候选不进 size**：卡片数（67/133 覆盖、66 个 0）、FSRS 难度（101 卡/67 KP、0 值多且稀疏）、分组规模（Union-Find 实测最大组 **120/133=90.2%**，不可用）、是否当前文件（用 ring/highlight）、已掌握（用 color/opacity）。
4. **映射用分位（p10–p90 clip）+ 面积开方**，不是线性——实测 degree 0–25、内容 707–32,847 chars，线性会把 90% 压成同一点。
5. **半径有界**：world-space 5–18px，屏幕最小 4px（`r_world ≥ 4/zoom`）；设置项 `nodeRadius` 语义改为"最小半径"，新增 `nodeSizeMax`（默认 18），**无数据迁移**。
6. **防双编码**：galaxy 样式现在把 degree 同时编进**颜色和半径**（`graph-view-2d.js#L639,L632`）——必须二选一；默认 force 样式下 color 只承载状态，不承载数值。
7. **布局**：保留力导向，但必须加**位置持久化**（当前每次打开随机初始位置 + `alpha=1` 重排，`graph-layout-2d.js#L37-L51,L244-L246`）——否则空间记忆永远建立不起来。
8. **标签必须做 LOD + 避让**：当前 133 个标签**无条件全画**、固定 10px、无避让（`graph-view-2d.js#L98-L114,L660`）——这是可读性最大瓶颈，比节点大小更严重。
9. **3D 只做探索**：透视会混淆"大=重要"与"大=离得近"；3D 的 size 动态范围必须收紧到 1.0–1.25，并配数值 legend；3D 不用于精确比较。
10. **验收禁止"好看"**：每条编码配任务与判据（找枢纽/比厚度/找当前文件/找复习项），accuracy + time 双指标（§6 Q7）。

---

## 2. 节点大小驱动因子表（Q1 主战场）

> 硬门槛：不服务决策的因子不得做装饰。数据全部来自 `ev:corpus:kgviz-b-1`（live collector + sidecar + review 文件）。

| 候选因子 | 服务哪个决策（人看图时在问什么） | 数据现状 | 视觉可辨（实测/推理） | 与 color/shape/opacity 冲突 | 结论 |
| --- | --- | --- | --- | --- | --- |
| **入度（被引用数）** | 「哪些概念被最多条目引用（枢纽/常用）→ 先看/先学哪些」 | ✅ 现有：edges 已含 source_id/targets；`_galaxyStats` 已算 degree（`graph-view-2d.js#L543-L556`；3D `#L399-L409`），但只在 galaxy 用 | 实测入度 0–18、中位数 2、distinct 14；undirected 0–25、distinct 21；`degree≥10` 有 **26/133**。分位映射后半径桶 12 档 | 与 galaxy 颜色冲突（现状双编码）：默认 force 下 color 不承载数值即可 | ✅ **默认采用**（称"被引用"，不称"重要性"） |
| **KP 内容体量（行跨度/chars）** | 「哪块内容最厚 → 阅读成本/先读哪块」 | ✅ 现有：`nodes[]` 已有 `start_line/end_line/file`（`collector.py#L61-L70` + 实测 node keys）；chars 需读文件体（前端可用行跨度代理） | 实测 chars 707–32,847、median 7,826、distinct 132；半径桶 13 档 | 与 size 互斥（模式切换）；不占 color | ✅ **备选模式**（用户切换，非默认） |
| 卡片数（复习题量） | 「哪块练习题多/复习负担」 | ⚠️ 有数据但**不在图载荷**：`cards.json` 80 卡、覆盖 **67/133** KP、**66 个 KP 为 0**、max 9；需新增后端/API 字段 | 半径桶 8 档但 68/133 挤在 5px | 与 FSRS/掌握度语义重叠 | ❌ 不进 v0（覆盖不足 + 需契约变更）；可作"复习模式"v1 |
| 复习次数 / FSRS 难度 | 「哪些我反复看但没记住 / 哪些最难」 | ⚠️ 101 卡有 FSRS 状态、仅 67 KP；difficulty 0–8.08 但大量 0（新卡）；reps 0–2 | 稀疏长尾，作为 size 大部分节点无值 | 与"已掌握"color 冲突 | ❌ 不进 v0（稀疏 + 需契约）；**若将来用，做 color/ring，不做 size** |
| 是否当前文件 | 「我在哪 / 别丢方向」 | ✅ UI 状态即可（无需数据） | 100% 可辨（ring/描边） | 与 size 不冲突（ring 独立通道） | ✅ 用 **ring/highlight**，不用 size |
| 是否已掌握 | 「哪些已掌握可以跳过」 | ⚠️ 仅 67 KP 有 FSRS 状态；"已掌握"阈值未定义 | color/opacity 可辨 | color 同时用于 hover/target（状态）会互斥 | ❌ v0 不做（颜色通道已被状态占用；需先定"掌握"语义） |
| 分组规模 | 「哪个组大/该看哪个组」 | ❌ Union-Find 实测：14 组，最大 **120/133=90.2%**（`graph-groups.js#L9-L33,L83-L121`） | 无法形成有意义的组 | 与分组色冲突 | ❌ 不可用；分组本身需先修（见 Q5） |

**结论（明确）**：**默认 size = 入度**；**备选 size = 内容体量**；卡片/FSRS/掌握/分组规模都不做 size。

---

## 3. 场景 → 要看什么 → 视觉编码（含 AAA_Vocab 实例数）

| 场景 | 用户在看图时问什么 | 实例（实测） | 需要的视觉编码 | 备注 |
| --- | --- | --- | --- | --- |
| **备考：找高频/枢纽概念** | 哪些词/句型被最多条目引用，先过一遍 | 入度 top：`perilous` 18、`hard though … may be` 16、`heritage` 15；`degree≥10` 有 26 个 | **size=入度** + 标签 LOD（大节点带标签） | 这是人"节点大小不同"最自然的诉求 |
| **判断阅读成本** | 哪个知识点内容最厚，先读/后读 | chars top：International Tourism 32,847、Income Equality 29,042、Describe a time… 20,782；median 7,826 | **size=内容体量模式** + tooltip 显示 chars | 与"枢纽"模式互斥 |
| **复习/查漏** | 今天该复习哪些、哪些反复没记住 | 80 张卡、67 KP 有卡；FSRS 101 条状态 | **color/ring=复习状态**（v1，需契约+定义）；v0 不做 | 大小不承载复习信息（避免误读） |
| **导航/定位** | 我刚点的词/当前文件在哪 | 133 节点；每次跳转有 source/target 高亮（已有） | **ring=当前文件/焦点**（已有 hover/target 色） | 不需要新数据 |
| **写作查用法** | 这个词和哪些词搭配/对比 | 404 条 reference 边、入度 τ 2 | hover 边高亮（已有）+ 标签/详情弹层 | 边语义弱（reference），不承诺关系类型 |
| **3D 探索** | 整体形状/密度分布（不用于精确比较） | 同一 133/404 | 3D 仅 size 动态范围 1.0–1.25 + 深度雾/透明度 + legend | 见 Q4 |

> **对"6 场景=6 视图"的校正（承接 ontology D-KG-10 单根降级）**：本表不再是"6 个视图"主张，而是 **2 个已可做（枢纽/内容体量）+ 1 个定位（ring）+ 2 个待数据（复习/掌握）+ 1 个受限（3D）**。可测实例数已给，可逐条 A/B。

---

## 4. Q2–Q7 回答

### Q2 映射函数（人能不能分辨）
- **分位映射**：`p = clamp(rank_pct, 0.10, 0.90)`；`t = (p-0.10)/0.80`；`r = 5 + 13 * sqrt(t)`（world px）。
  - 为什么 sqrt：半径→面积线性更符合人知觉；为什么分位：长期长尾（degree 中位 2、内容 707–32,847）线性会把 90% 压到 5–6px。
  - 实测桶：degree 12 档、内容 13 档；最小值 5、最大 18（≈3.6× 直径，可辨）。
- **屏幕空间下界**：`r_world = max(r, 4 / zoom_k)`（zoom 缩到 0.25 时仍 ≥16 world px ≈4 screen px，可点中）；不做"屏幕恒定大小"（会丢大小语义）。
- **性能**：2D 133 节点/404 边，逐节点 `arc` 成本可忽略；3D 共享 `SphereGeometry` 已存在（`graph-view-3d.js#L414-L418`），逐 mesh `scale` 已有 galaxy 先例（`#L431-L435,L445`），不需要拆共享几何体。
- **设置项迁移**：`nodeRadius`（4–12，`graph-settings.js#L561`）语义 = **最小半径**；新增 `nodeSizeMax`（默认 18，范围 12–28）；旧值不改，无数据迁移。关闭差异化 = 把 max 设成 = min。

### Q3 度数数据复用
- `_galaxyStats()` 已算出 deg/max（2D `#L543-L556`，3D `#L399-L409`）但只在 galaxy 分支使用 ⇒ **建议提升为通用 node 派生属性**：`engine.nodeDegree(id)`（前端缓存，零契约风险）或 `nodes[].degree/in_degree`（collector 计算，供 agent/UI 共用）。
- **判据**：若只前端缓存，则 agent 侧不可用（与 ontology「image 给 agent 读图」无关，不算矛盾）；若进 collector，则需契约 owner 裁决（新增派生字段，非语义类型，不违反 v0「不加语义类型」）。
- 区分 **入度/出度**：入度=被引用（"枢纽"），出度=引用别处（"这条在讲什么"）；默认用入度，tooltip 两个都显示。

### Q4 3D 特有视觉问题
- **近大远小混淆**：3D 透视下"大 = 重要"与"大 = 离得近"不可区分 ⇒ 3D 下 size 动态范围收紧到 `scale 1.0–1.25`（现状 galaxy 已 1+0.4ratio，`#L431-L435`），并把精确数值放 hover/legend。
- **深度线索**：建议加轻微雾/远处降透明（只在 3D，不影响 2D）；标签 sprite 随节点大小缩放（当前 sprite 以 `nodeRadius` 固定生成，`#L143-L179` ⇒ 差异化后需随 r 重建/缩放）。
- **结论**：3D 只做总览/探索；有向边+精确大小比较一律 2D（承接 KG 本体辩论 Q6 的同一结论）。

### Q5 布局本身
- 现状力导向参数：`linkDistance 108 / repulsion 5200 / velocityDecay 0.8 / alphaDecay 0.045`（`graph-layout-2d.js#L8-L14`；sim-core `#L10-L23`）——**无文档化依据**，登记为 unknown（保留基线，不调参）。
- **稳定性（关键）**：当前每次 `setGraph` 用随机初始位置 + `alpha=1`（`#L37-L51,L244-L246`）⇒ 每次打开大跳，空间记忆无法建立。建议：
  1. **位置持久化**：按 `KB path + graph content hash` 存 localStorage（节点 id→x,y[/z]），打开时恢复；内容变化时新增节点从邻居 anchor 生长（300ms），其余不动；
  2. 仅"重新布局"按钮触发全局 reheat。
- **分组**：Union-Find 实测 90.2% 一组 ⇒ **不能用**。v0 建议：默认不分组；可选"按目录/标签分组"（稳定、可解释）；社区检测（Louvain）放 v1（需 A/B 证明比目录分组好）。
- **新节点动画**：从 anchor 生长 + 300ms 淡入；不做全图重排（会毁空间记忆）。

### Q6 标签与视觉密度
- 现状：**每个节点无条件画标签**（`graph-view-2d.js#L660` → `drawNodeLabel` `#L98-L114`），固定 10px、无避让、无缩放 LOD ⇒ 133 标签在 6px 节点上必然重叠。
- 建议 **LOD**：默认只画 `degree ≥ p75` 或 top 20%（约 26 个）标签 + 焦点/hover 节点标签；zoom 分级（<0.8 只 top15%；0.8–1.5 p50；>1.5 全部但上限 80 个）。
- **避让**：贪心矩形避让 + 空间哈希（`graph-label.js` 现 2.2KB 只做文本截断）—— 建议 v0 简单版（按 y 排序，冲突则隐藏低优先级标签）。
- **毛球态判定**：`labels_visible > 60` 或 `edges/nodes > 4` 或 `平均度 > 8` ⇒ 提示"缩放到局部/切换分组/关闭标签"（承接 D5；当前 404/133≈3.04 未触发）。
- **信息密度预算**：size（1 维）+ color（状态）+ ring（焦点）+ 标签（LOD）≤ 3 通道；边宽/箭头不再编码数值。

### Q7 可测验收（禁止"好看"）
| 任务 | 判据 | 基线 |
| --- | --- | --- |
| T1 找"被引用最多的 3 个节点" | accuracy ≥80%，median time ≤15s（n≥10） | 当前常量半径（无 size） |
| T2 比较两个高亮节点"哪个内容更厚" | accuracy ≥90%，median ≤8s | 无 size 模式 |
| T3 找"当前文件节点" | 100%，≤5s | 无 ring（现仅 hover 色） |
| T4（若做复习色）找"今天到期" | accuracy ≥80% | 无颜色编码 |
| 空间记忆 | 关闭重开图后，找到上次位置节点时间 ≤ 首次的 70% | 随机重排 |
仪表：`nodeClick` 已有（`app.js:1438`）；需新增 hover/zoom/label-toggle 埋点；A/B 同冻结语料。

---

## 5. 可证伪断言（每条"若观察到 X 则本条不成立"）

- **F1 size=入度 服务决策**：若 T1 在 size=入度下相对无 size 无显著提升（accuracy 或 time 任一不改善），则默认 size 不成立，应退回常量或改内容体量。
- **F2 内容体量模式**：若 T2 在内容模式与入度模式无差异（或更差），则内容模式不成立，删除该模式。
- **F3 卡片/FSRS 不进 size**：若将来卡片覆盖 ≥80% 或有 A/B 证据显示复习量作 size 显著改善 T4，则重开此条。
- **F4 分位映射优于线性**：若线性映射在 T1/T2 不劣于分位（且无 90% 同尺寸问题），改用线性（更简单）。
- **F5 位置持久化**：若持久化后"找上次节点"时间无改善（≥首次 100%），则持久化不成立，退回随机布局。
- **F6 标签 LOD**：若默认全标签在 T1/T2 优于 LOD（且可读性评分不低），则不做 LOD，改为仅避让。
- **F7 分组不可用（Union-Find）**：若有人证明 Union-Find 分组能产生非退化的、用户可解释的组（最大组 <60%），则撤销"分组不用"。
- **F8 3D 仅探索**：若 3D 在 T1/T2 上不劣于 2D（时间/正确率），则 3D 可用于决策任务。

---

## 6. unknowns / not_doing（M3）

### unknowns
- **U1**：入度的语义可解释性（reference 边=被引用；用户是否把"大"读成"重要"）——未做用户研究。
- **U2**：内容体量用"行跨度"还是"chars"（行跨度免费但跨 MD 结构差异大；chars 需读文件体）——未定。
- **U3**：标签避让的实现成本与视觉收益（2.2KB 模块是否要重写）——未 измерено。
- **U4**：3D 深度线索（雾/透明度）对"大小比较"的实际影响——无读数。
- **U5**：位置持久化的失效策略（内容大幅变化时哪些节点保留位置）——未设计。
- **U6**：分组（目录/标签 vs 社区检测）在真实库的可解释性——未测。

### not_doing（本轮明确）
- 不做新语义边/类型（承接 ontology v0：不加 prerequisite/contrast/exemplify；size 的驱动只读现有 reference 图）。
- 不让 size 承载"重要性/掌握度/复习紧迫"（没有数据或语义未定义）。
- 不做 3D 精确大小比较/有向边可读性承诺。
- 不调力导向参数（无依据；先保留基线，登记 unknown）。
- 不在 v0 做社区检测分组（先修 Union-Find 误用）。
- 不做"看起来更好看"的验收。

---

## 7. 证据清单与冻结身份

**冻结身份 `ev:corpus:kgviz-b-1`**：HEAD `ff0c374c` + KB dirty 239 文件 + 134 sidecar 聚合 sha256 `0fe6252a1d05a891f9e8ae72b454dba4d8037117550c4ddc2d3935bf8167ac97` + 测量脚本 `artifacts/agent/verify/debate/kgviz/_phase1_measure.py` sha256 `7013715c9ab47ca13c8e11ee0d97a92106af9ce4a40a80eac04f9bcfd5d7acc3`。
**测量源**：现场 `collect_graph_data()`（不用 `.memoria/build/graph.json` 缓存）。

```
ev:file:src/memoria/ui/static/app/js/graph-view-2d.js#L10            nodeRadius: 6（全局常量）
ev:file:src/memoria/ui/static/app/js/graph-view-3d.js#L10            nodeRadius: 6
ev:file:src/memoria/ui/static/app/js/graph-settings.js#L561          rangeField("nodeRadius",4,12,1)
ev:file:src/memoria/ui/static/app/js/graph-view-2d.js#L543-L556      _galaxyStats deg/max
ev:file:src/memoria/ui/static/app/js/graph-view-2d.js#L631-L639      r = radius*(1+ratio*0.5) 仅 galaxy；颜色也按 ratio
ev:file:src/memoria/ui/static/app/js/graph-view-3d.js#L414-L418      SphereGeometry 共享
ev:file:src/memoria/ui/static/app/js/graph-view-3d.js#L431-L435,L445 galaxy 逐 mesh scale
ev:file:src/memoria/ui/static/app/js/graph-view-2d.js#L98-L114,L660   标签无条件全画、10px、无避让
ev:file:src/memoria/ui/static/app/js/graph-label.js#L1-L12           label 模块（仅截断）
ev:file:src/memoria/ui/static/app/js/graph-groups.js#L9-L33,L83-L121 Union-Find 分组（实测 120/133 一组）
ev:file:src/memoria/ui/static/app/js/graph-layout-2d.js#L8-L14,L37-L51,L244-L246 力导向参数/随机初始位置/alpha=1
ev:file:src/memoria/ui/static/app/js/graph-layout-sim-core.js#L10-L23  sim 参数
ev:file:src/memoria/graph/collector.py#L61-L70                       node 字段（id/name/file/start_line/end_line）
ev:file:docs/design/kg-ontology-v0.md#L31-L56                         concept model：reference 无断言
ev:file:docs/design/kg-ontology-v0.md#L75-L83                         v0 不做：不加语义类型/6 场景=6 视图降级
```
