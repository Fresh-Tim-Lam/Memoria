# KG-viz 研讨会 Phase 1 提案 · D 架构/契约（arch-contract）

> **独立性声明**：**未读取** `PROPOSAL-{render-perf,todo-owner,metrics-baseline}.md`（Phase 1 硬要求）。
> **前置约束**：`docs/design/kg-ontology-v0.md`（冻结版，不得矛盾）。
> **协议**：`artifacts/agent/verify/debate/PROTOCOL.md`（FROZEN）。
> **纪律**：不改 `src/**`；不 commit；**每个"字段存在/不存在"的断言都带 `ev:file:<path>#L<n>`**。

---

## 1. 立场摘要（≤10 行，可被逐条反驳）

1. **前端图谱走的是 `collect_graph_data`（collector），不是 `kb_build`** —— 实测同一冻结语料：
   collector 给 **404 边 / 9 字段 node**，kb_build 给 **454 边**。
   `ev:file:src/memoria/services/document.py#L2127-L2130`（`get_graph_data()` → `collect_graph_data`）
   ⇒ **这解释了 KG 辩论 C4 的全部数字分歧（404 vs 454）**，不是口径漂移，是**两条后端路径**。
2. **节点 node 字段全集实测为 9 个，无 `degree`**：
   `description / end_line / file / id / kp_id / label / name / range_ok / start_line`
   （`ev:file:src/memoria/graph/collector.py#L61-L70` + `ev:file:src/memoria/graph/kp_index.py#L76` `entry_to_dict`）
   ⇒ **任何"按度数调节点大小"的视觉编码，当前引用的字段不存在。**
3. **度数现在由前端 `_galaxyStats()` 现算，且只在 galaxy 风格用**：
   `ev:file:src/memoria/ui/static/app/js/graph-view-2d.js#L543-L556`（遍历 `engine.links`，缓存键 = `links.length`）
4. **主张：度数**应**进 collector**（作为 `node.degree`），但**只作为派生字段、不进 sidecar 事实源**；
   并且**计算口径必须唯一** —— 由后端算，前端只读。
5. **主张：视觉属性（radius/color/alpha）留在渲染层，绝不进数据层**。
   数据层只提供**语义量**（degree / card_count / reps），渲染层负责**映射函数**。
6. **反直觉主张：FSRS 参数（stability/difficulty）不该驱动节点大小** —— 它们是**卡片级派生值**，
   且 `progress.json` 的键是 **card_id 不是 kp_id**（实测 101 卡片键），**按 kp 聚合需要 join**，
   属于"视觉编码引用了一个不是按节点组织的数据"。
7. **2D/3D 必须共享同一份"语义量"，但可以有不同映射函数** —— 3D 现用 `* 0.85`
   （`ev:file:src/memoria/ui/static/app/js/graph-view-3d.js#L414`），这是**渲染常量**，不是数据差异。

---

## 2. 【核心交付】驱动因子 → 事实源 → 事实/派生 → 前端是否重算（总表）

> 判据列说明：**事实源** = 谁是唯一权威；**性质** = 事实（可直接写入）/ 派生（可算出、不得进事实源）；
> **2D/3D 读哪** = 实际读取路径；**前端重算** = 是否会让前端与后端产生两套口径。

| # | 驱动因子 | 事实源（现状） | 性质 | 2D/3D 读哪 | 前端重算风险 | 结论 |
|---|---|---|---|---|---|---|
| **F1** | **度数（degree）** | ❌ **不存在于 node**（`ev:file:src/memoria/graph/collector.py#L61-L70`） | **派生**（由 edges 算出） | 前端 `_galaxyStats()` 现算（`ev:file:...graph-view-2d.js#L543-L556`） | 🔴 **高**：前端从 `engine.links` 算，后端 edges 是另一套 ⇒ **两套口径** | **应提升为 `node.degree`（collector 产出）** |
| **F2** | **KP 内容长度** | ✅ md 正文（`ev:file:src/memoria/graph/collector.py#L71` `start_line/end_line`） | **可派生**（`end_line - start_line`） | 前端有 `start_line/end_line` | 🟢 低（同一字段两端都有） | **不需新字段**；若要用，前端自己算行数差 |
| **F3** | **卡片数** | ✅ `.memoria/agent/review/cards.json`（实测 114 卡，含 `kp_id`） | **派生**（按 `kp_id` 聚合） | **前端不读**（图谱数据不含复习数据） | 🔴 **高**：需新 RPC 或塞进 node ⇒ 跨域耦合 | **不该进 node**；若要，走独立 RPC（见 U3） |
| **F4** | **复习次数（reps）** | ✅ `.memoria/agent/review/progress.json` → `cards[card_id].reps` | **派生**（FSRS 状态） | **前端不读** | 🔴 **高**：键是 **card_id 不是 kp_id**（实测 101 卡），按节点聚合需 **join cards.json 的 kp_id** | **不该进 node**；聚合口径需明确定义（见 U4） |
| **F5** | **FSRS 参数**（stability/difficulty/due/state） | ✅ `progress.json.cards[card_id]`（`ev:measure:kgviz-probe`：字段 `state/due/stability/difficulty/reps/lapses/last_review`） | **派生**（算法算出的调度参数） | **前端不读** | 🔴 **高**：同上，且**不是按 kp 组织** | **不该驱动节点大小**（见 §5-F5 论证） |
| **F6** | **是否当前文件** | 🔴 **会话态，无持久字段**（`graph-engine.js` 无 active/current 字段，实测零命中） | **会话态**（非事实、非派生，是 UI 状态） | 前端自有 | 🟢 无（纯 UI） | **留渲染层**，不进数据 |
| **F7** | **是否已掌握** | ⚠️ 可派生自 `progress.json.cards[*].state`（`learning/review/...`） | **派生**（且需按 kp 聚合） | 前端不读 | 🔴 高 | **不该进 node**（同 F4/F5） |
| **F8** | **边类型（edge.type）** | ✅ `collector` 的 `edges[].type` | **事实**（sidecar 写入） | 前端直接读 | 🟢 无 | **已足够**（v0 不改，遵 `kg-ontology-v0.md` §4） |
| **F9** | **relevance（边的权重）** | ✅ `edges[].relevance`（缺省按 type，`ev:file:src/memoria/graph/edge_types.py#L26-L30`） | **事实**（sidecar 可写，缺省派生） | 前端读（力导向弹簧强度） | 🟢 无 | **已足够** |
| **F10** | **毛球态判定量** | ❌ 不存在（需算 `最大分组占比` / `reference 占比`） | **派生**（从 edges 算） | 前端可算 | ⚠️ 中 | 见 §7 |

### 2.1 总表的三个关键结论

**(a) 唯一"该进数据层"的因子是 F1（degree）**，其余 5 个（F3/F4/F5/F7）都**不该进 node**——
因为它们的事实源在**复习域**（`review/*.json*`），而 node 属于**图谱域**（`graph/collector.py`）。
**跨域塞字段 = 契约污染**（详见 §4）。

**(b) 当前"视觉编码引用不存在字段"的唯一实例是 degree** —— 但它是**前端自己补上的**（`_galaxyStats`），
所以不是"引用了不存在字段"，而是 **"引用了口径不一致的派生值"**。

**(c) F6（是否当前文件）是会话态**，既非事实也非派生 —— 它**只能留渲染层**，任何"进数据层"的尝试都是错的。

---

## 3. 【专节】度数数据的归属：前端算 vs collector 算

### 3.1 现状（两套口径的具体证据）

| 侧 | 怎么算 | 证据 |
|---|---|---|
| **前端** | 遍历 `this.engine.links`，source/target 各 +1 | `ev:file:src/memoria/ui/static/app/js/graph-view-2d.js#L546-L551` |
| **后端** | `collect_graph_data()` 产 `edges[]`，**但不算 degree** | `ev:file:src/memoria/graph/collector.py#L86` 返回 `{status,nodes,edges}`，node 无 degree |

**两套口径的差异点**：
1. **数据源不同**：前端 `engine.links` 是**加载到引擎的链接**（可能被过滤/去重后），后端 `edges[]` 是**全量边**。
2. **缓存键弱**：`_galaxyCache.version = links.length`（`:544`）—— **边数不变但端点变化时缓存不失效**。
3. **只在 galaxy 用**：`_galaxyStats()` 只被 galaxy 着色调用（Phase 1 观察），非 galaxy 风格**根本不显示度数**。

### 3.2 我的主张：**度数进 collector，但作为"派生的只读字段"**

```
位置：collect_graph_data() 返回前，从 edges[] 算 degree 填进 node.degree
形状：node.degree: int   （每条边对 source 与 target 各 +1，与前端 _galaxyStats 同语义）
       可选 node.in_degree / out_degree（若将来要做有向视觉编码）
计算口径：唯一 —— 后端算一次，前端只读，前端不再自己遍历 links
缓存键：不需要缓存（随 graph_data 一起返回，天然一致）
```

**为什么不留给前端（P1 要求给理由 + 替代）**：
- **理由**：前端算 = 需要 `engine.links` 与后端 `edges` 完全一致；但引擎可能做过滤/合并（`graph-log-layout` 有 `dedupe`），
  ⇒ **两套口径必然漂移**。KG 辩论已证明"同一语义两套来源"是本轮反复出事的地方（`edge_types.py#L3` 的双事实源）。
- **替代（若坚持前端算）**：必须让前端从**后端返回的 edges 原样**算，且**缓存键改成 edges 的内容哈希**而非 length。
  这仍然比"后端算"多一处重复实现。

### 3.3 反对意见预案：会不会造成"契约污染"？（Lead 明确问）

**会，但可控。判据是"这个字段是不是图谱域自己的量"。**

| 字段 | 域归属 | 进 node 合适吗 |
|---|---|---|
| `degree` | **图谱域**（由本域的 edges 算出） | ✅ **合适** —— 它不需要任何跨域数据 |
| `card_count` | 复习域（`review/cards.json`） | ❌ 不合适 —— 需跨域 join |
| `reps` / `stability` | 复习域 | ❌ 不合适 —— 同上 |
| 是否当前文件 | 会话域（UI） | ❌ 不合适 —— 非持久量 |

⇒ **`degree` 与其它五个因子的本质区别：它是"图谱自身边的函数"，不是"跨域业务数据"。**
这是我能给出的最干净的边界判据。

### 3.4 给 agent 侧的价值（KG 辩论已定 agent 不读边）

**如实说明**：KG 辩论已确认 **agent 不读 `graph_data`**（`ev:file:src/memoria/services/agent/section_index.py#L207` 走 `parent_path` 而非图谱）。
⇒ **`node.degree` 对 agent 无价值**，它**只服务前端可视化**。

**但这不构成"不该进 collector"的理由**——collector 本身就是**为前端服务**的数据层（`document.py#L2127` 是 UI RPC 的唯一入口）。
**要防止的是"为了 agent 将来可能用"而加字段**（YAGNI），而不是"为前端加字段"。

---

## 4. 【核心】视觉属性 vs 数据属性的分层主张

### 4.1 我的分层（这是本次提案的中心主张）

```
┌─ 数据层（collector / graph_data）──────────────────────────┐
│  只放【语义量】：node.degree / edge.type / edge.relevance    │
│  规则：① 必须由图谱域自身数据算出或存储                       │
│       ② 不得依赖复习/会话等跨域数据                           │
│       ③ 前端不得重算（重算 = 第二事实源）                     │
├─ 映射层（渲染配置，前端 settings）──────────────────────────┤
│  负责"语义量 → 视觉量"：                                      │
│    radius   = f(degree, nodeRadiusBase, sizeMode)            │
│    color    = f(edge.type)  /  group                        │
│    alpha    = f(isActive, isHover)          ← 会话态在此      │
│    force    = f(edge.relevance)             ← 已有            │
├─ 渲染层（canvas/WebGL）────────────────────────────────────┤
│  nodeRadius / linkDistance 等常量、galaxy 视觉变体            │
└───────────────────────────────────────────────────────────┘
```

### 4.2 具体到"节点大小"（人的原始诉求）

| 层 | 放什么 | 现状 | 我的主张 |
|---|---|---|---|
| **数据层** | `node.degree`（语义量） | ❌ 不存在 | **新增**（§3.2） |
| **映射层** | `sizeMode: "uniform" \| "degree"`、`sizeScale` | ⚠️ 只有 `nodeRadius: 6` 常量（`ev:file:...graph-view-2d.js#L10`）+ `rangeField(4,12,1)` 整体缩放（`graph-settings.js:561`） | **新增 `sizeMode` + `sizeRange`**（映射函数参数，非数据） |
| **渲染层** | `nodeRadius` 常量、3D 的 `*0.85` | ✅ 已有 | **保留**（作为 `sizeMode=uniform` 时的值） |

⇒ **节点大小 = 数据层给语义量（degree）+ 映射层给函数 + 渲染层给常量**，三层各司其职。
**关键**：`sizeMode` 是**设置项**（跟 `graphStyle` 同级），不是数据字段。

### 4.3 为什么"尺寸"不该作为数据字段（回答 Q4）

**3D 技术约束**：3D 用共享几何体（`ev:file:src/memoria/ui/static/app/js/graph-view-3d.js#L414` `this.opts.nodeRadius * 0.85`）。
若"逐节点尺寸"，每个节点需要独立 scale —— **这是渲染实现细节，不是数据契约**。

⇒ **"尺寸"不是数据，是"数据 × 映射函数"的结果**。
把 width/height/radius 存进 node = **把渲染决策烧进数据层**，一旦换渲染器就作废。

---

## 5. 逐条回答 Q1–Q7

### Q1 节点大小驱动因子（见 §2 总表 + 逐因子论证）

**关键否证：F5（FSRS 参数）不该驱动节点大小**，理由：
1. **它不是按节点组织的**：`progress.json.cards` 键是 `card_id`（实测 101 卡），
   `ev:measure:kgviz-probe`：`{"err-20260910-001": {state, due, stability, difficulty, reps, lapses, last_review}}`
   ⇒ 要按 kp 聚合必须 `cards.json`（有 `kp_id`）join `progress.json`（有 FSRS 值）——**两次跨域 join**。
2. **一个 kp 可能有 0..N 张卡**：聚合方式（max? mean? 最弱那张？）**没有唯一答案** ⇒ 口径争议。
3. **stability/difficulty 是算法内部量**，不是用户可感知的"重要性"。用它调大小会**误导**（难度高 ≠ 重要）。

### Q2 映射函数从"契约可表达"角度

**主张：映射函数必须是"纯函数 + 参数在设置里"，不得内联魔数。**

现状问题：`graph-view-2d.js:631` `let r = opts.nodeRadius + (isHover || isExtSource ? 3 : isExtTarget ? 2 : 0)`
—— **内联三元表达式**，无参数、无文档 ⇒ **无法测试、无法调参、无法解释**。

**主张形状**：
```
sizeMode: "uniform" | "degree"
sizeRange: [minRadius, maxRadius]          // 对应 rangeField(4,12,1)
sizeScale: "linear" | "sqrt" | "log"       // 度数长尾时 sqrt/log 更合理
```
**理由**：度数分布是长尾（KG 辩论实测最大度 27、中位数 5）⇒ 线性映射会让多数节点不可见，**必须支持 sqrt/log**。
这是**契约可表达性**问题：如果不支持 `sizeScale`，长尾数据下"大小编码"实际不可用。

### Q3【主战场】度数归属（见 §3 全节）

### Q4 3D 的契约问题（见 §4.3）

补一条：**2D/3D 共享同一份 `nodes/edges` 是现状且应保持**
（`ev:file:src/memoria/ui/static/app/js/graph-engine.js` 单引擎），
**"尺寸"作为映射层属性，2D/3D 各自有映射参数（如 3D 的 `*0.85`）但共享数据。**

### Q5 布局参数存在哪

| 参数 | 现状 | 依据 | 我的主张 |
|---|---|---|---|
| `linkDistance: 108` / `repulsion: 5200` / `linkStrength: 0.28` 等 | **常量**（`ev:file:...graph-layout-2d.js#L8-L22`）+ 设置项（`graph-settings.js` 有 `linkDistance` 滑块） | 混合 | **保留现状**：常量作默认值，设置项可覆盖 |
| `distMode: "grid"` / `groupSpacing: 260` | **常量**（`:22-23`） | 无设置项 | **建议暴露为设置项**（域概览需要） |
| `relevance → linkStrength` | 已有映射（`ev:file:...graph-layout-2d.js#L366` 用 `linkDistance`） | — | 保留 |

**关键**：布局参数**全部是渲染层**，**不进数据契约**。

### Q6 标签显示策略：渲染决策还是数据字段

**主张：纯渲染决策。**
证据：`labelMode: "name_short"` / `labelMaxLen: 8` 是**设置项**
（`ev:file:src/memoria/ui/static/app/js/graph-settings.js#L12-L13`），
`ev:file:src/memoria/ui/static/app/js/graph-view-3d.js#L618` `labelKeys = ["labelMode","labelMaxLen","nodeRadius"]` 是**渲染参数**。
⇒ **标签策略不引用任何数据字段，只在渲染层**。**v0 不改**。

### Q7 可测验收（我只给"字段可测性"）

| 字段/量 | 可测性 | 测法 |
|---|---|---|
| `node.degree` | ✅ **完全可测** | 后端单测：构造 3 节点 2 边，断言 `degree==[1,2,1]`；对冻结语料断言 `sum(degree)==2*len(edges)` |
| `sizeRange`/`sizeScale` | ✅ 可测 | 纯函数单测：给定 degree 分布断言 radius 在 `[min,max]` 且单调 |
| 毛球态阈值（最大分组占比） | ⚠️ 可测但**依赖分组算法** | 见 §7 |
| FSRS 因子 | ❌ **不可测**（未定义聚合口径） | 这正是我反对它进 node 的理由之一 |

---

## 6. 可证伪断言（每条"若观察到 X 则本条不成立"）

| # | 断言 | Falsifier |
|---|---|---|
| **V1** | **前端图谱数据来自 `collect_graph_data`，不是 `kb_build`** | 若 `document.get_graph_data()` 改调 `build_knowledge_base` ⇒ V1 不成立（则 404/454 分歧随之消失） |
| **V2** | **collector 的 node 无 `degree` 字段** | 若 `collect_graph_data()` 返回的 node 含 degree ⇒ V2 不成立 |
| **V3** | **`_galaxyStats()` 只在 galaxy 风格被调用** | 若发现非 galaxy 路径也调它 ⇒ V3 不成立（度数已在用，不需新增） |
| **V4** | **`progress.json.cards` 的键是 card_id 而非 kp_id** | 若键中存在 `kp_id` 形态（如 `blend`）⇒ V4 不成立，FSRS 可按节点直取 |
| **V5** | **`degree` 属图谱域、`card_count`/`reps` 属跨域** | 若 collector 已能访问 review 数据（如同进程读 `review/*.json`）⇒ 边界判据需重议 |
| **V6** | **节点大小应三层分离（数据 degree / 映射 sizeMode / 渲染 nodeRadius）** | 若 3D 逐节点尺寸无性能代价（实测可接受）⇒ 可简化为"直接存 size" |
| **V7** | **visual 字段（radius/color/alpha）不该进 graph_data** | 若发现现有 graph_data 已含 visual 字段 ⇒ 说明先例存在，我的分层主张需调整 |

---

## 7. 毛球态判定需要什么字段（承接 KG 辩论 D5）

`kg-ontology-v0.md#L110` 已裁：**最大分组占比（99.2% 能可靠判"没修好"；不能当验收）**。

**我的契约判断**：
- **不需要新数据字段** —— 它是 **`node.group` 的函数**（分组在前端算，`computeGraphGroups`）。
- **但需要 `node.group` 有稳定归属**：现在分组由前端 `graph-groups.js` 算（Union-Find），**无后端字段**。
- ⇒ **毛球判定 = front-only 派生量**，`reference 占比 = count(edge.type=="reference")/count(edges)` 可直接从 edges 算。

**结论**：毛球态判定**零新增字段**，但**判定逻辑必须与"域分组"共用同一份 group 计算**，否则两套分组。

---

## 8. unknowns / not_doing（按 M3，每条带 if_true_then）

| # | 类型 | 内容 | if_true_then |
|---|---|---|---|
| **U1** | unknown | `engine.links` 与后端 `edges` 是否 1:1（引擎是否过滤） | 若 1:1 ⇒ 前端算 degree 与后端算等价，F1"应进后端"的紧迫性降低 |
| **U2** | unknown | 长尾度数下线性映射是否真的不可用 | 若实测多数节点仍可见 ⇒ `sizeScale: sqrt/log` 可推迟 |
| **U3** | unknown | 卡片数/复习状态是否真需要出现在图上 | 若产品不需要 ⇒ F3/F4/F5/F7 全部 not_doing，跨域 join 问题消失 |
| **U4** | unknown | 一个 kp 多卡时的聚合口径（max/mean/worst） | 若无共识 ⇒ **不能做"掌握度驱动大小"**，只能做 degree |
| **U5** | unknown | 3D 逐节点尺寸的性能代价 | 若 <5% 帧率下降 ⇒ V6 的三层分离可简化为"直接存 size" |
| **N1** | not_doing | 复习域数据进图谱（F3/F4/F5/F7） | 跨域污染 + 聚合口径未定义；若要需单独立项 |
| **N2** | not_doing | 标签策略改动 | Q6：纯渲染决策，现状够用 |
| **N3** | not_doing | 布局参数暴露为数据字段 | Q5：全部是渲染层 |
| **N4** | not_doing | 逐节点尺寸作为数据字段 | §4.3：渲染实现细节，非契约 |

---

## 9. 复现命令

```powershell
# 冻结语料（复用 KG 辩论口径）
$tmp = Join-Path $env:TEMP 'kgviz-probe'
Copy-Item 'docs\example\AAA_Vocab' $tmp -Recurse

# 1. 证明前端走 collector 而非 kb_build
python -c "from memoria.graph.collector import collect_graph_data; d=collect_graph_data(r'$tmp'); print(len(d['nodes']), len(d['edges']))"
#   ⇒ 133 404   （kb_build 则给 454）

# 2. 证明 node 无 degree
python -c "from memoria.graph.collector import collect_graph_data; d=collect_graph_data(r'$tmp'); print(sorted(d['nodes'][0].keys()))"
#   ⇒ ['description','end_line','file','id','kp_id','label','name','range_ok','start_line']

# 3. 证明 progress.json 键是 card_id
python -c "import json;d=json.load(open(r'$tmp/.memoria/agent/review/progress.json',encoding='utf-8'));print(list(d['cards'])[:3])"
```

---

## 10. 自利检查

| 我的主张 | 对我有利吗 |
|---|---|
| degree 进 collector（要改后端代码） | **否**——是更多的工作量，且要动 `collector.py` |
| 反对 F3/F4/F5/F7 进 node | **否**——否决了 4 个"看起来炫"的视觉编码 |
| 视觉属性留渲染层 | **否**——限制了我方领域（契约）的扩张 |

**无自利嫌疑**；本提案**主动否决了 4 个候选因子**（其中 3 个是数据现成的、看起来最容易做的）。
