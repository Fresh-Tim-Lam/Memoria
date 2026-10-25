# KG 设计辩论 · Phase 1 提案【C：agent 检索语义】

> **提案方**：agent-arch（C 线）。**日期**：2026-10-25。**纪律**：未读另外三方提案（`PROPOSAL-{arch-contract,todo-owner,metrics-baseline}.md` 全部未打开）；未改 `src/**`；未 commit。
> **数据快照**：2026-10-25 20:20–20:45（本机 `docs/example/**` 含用户 live app 的未提交改动；结论不依赖具体数字，见 §2.4）。**代码快照**：当前 working tree（未 commit）。
> **证据记号**：`ev:file:<path>#L<n>`（代码）；`ev:measure:<id>`（本提案 §8 可复现测量）；`ev:session:<kb>/<file>.jsonl#L<n>`（真实 agent 会话日志）。

---

## 1. 立场摘要（≤10 行）

1. **“边对 agent 有价值”目前是未被证明的假设，而不是事实**。agent 没有任何边读取接口；`docs/example` 下全部 **35 个真实会话**里 agent **从未**传过 `edge_type`、只建过 2 条边且全默认 reference。
2. 边现在唯一真正的 agent 消费者是 `validate_kb` 的**图一致性警告**（写质量诊断），不是检索/推理。
3. 因此“边该不该存在”的答案取决于它服务谁：**给人看的图**（颜色/结构）可以存在；**给 agent 用的语义关系**必须先证明能改变一个 agent 决策，否则不该进 agent 契约。
4. **agent 不该填边类型**：`contain` 由几何派生（从未被写），`reference` 是 100% 默认桶，`extend` 只出现在 demo 数据（9 条 HEAD + 11 条未提交），真实用户库 0 条。
5. **link 与 edge 的分开有意义，但类型属于 edge（语义关系），不属于 link（正文锚点）**；现在 `links[].edge_type` 是同一语义的第二事实源，且两套归一化器允许集合不同（含 `contain` 在 link 上被静默改写成 `reference`）。
6. 建议：**类型由系统推断/派生，agent 只覆盖（且默认不暴露）**；`prerequisite`/`exemplify` 在出现真实消费者（复习排序/检索）前**不要加**（对齐项目 R-R2“无消费者字段移出”）。
7. 唯一值得为 agent 新建的边能力是**反向邻接（谁引用了我）**：现在只能扫全库 sidecar（AAA_Vocab 实测 **43,880 tok**），有接口后一次回答约 **≤60 tok**。但在 A/B 证明它改善回答前，应标为 unknown，不落地。
8. 图是**给人看的**；2D/3D 只共享同一份 edges，类型只影响颜色、relevance 只影响弹簧强度 ⇒ 2D/3D 差异与 agent 无关。
9. 与 task-86 已裁 D1–D6：D2/D3/D4/D5 兼容；**D1(a) 的 prerequisite/exemplify 部分推翻**（不存在于枚举、无消费者、0 数据）；D6(a) 部分保留意见（外部对标回答不了 agent 价值，只有本地 A/B 能）。

---

## 2. 【边在代码里到底被谁读】清单（本节最关键）

方法：全仓 `grep edge_type`（`src/memoria/**/*.py` **144 行**命中、`static/app/js/**` 另计），逐点打开确认“读来做什么、谁消费”。

### 2.1 真实读取点（19 条）

| # | 位置 | 读什么 | 读来做什么 | 最终消费者 |
|---|---|---|---|---|
| R1 | `ev:file:src/memoria/graph/edge_derivation.py#L480`（`derive_link_edges`；类型在 L534/L566） | `links[].edge_type` / `target_edges` | links[] + instances 行号 → 推导 `reference/extend` 边 | 图数据 |
| R2 | `ev:file:src/memoria/graph/edge_derivation.py#L643`（L659 `normalize_edge_type(edge.type)`） | `edges[].type` | sidecar 纯边 → 图边（`origin=sidecar_edge`，`derived=false`） | 图数据 |
| R3 | `ev:file:src/memoria/graph/edge_derivation.py#L296`（L333 硬编码 `"contain"`） | 不读类型：KP range 嵌套 | 几何派生 contain 边（`origin=range`） | 图数据 |
| R4 | `ev:file:src/memoria/graph/collector.py#L44` | 调用 R1/R2/R3 | 汇总 `{nodes[],edges[]}` | 图数据 |
| R5 | `ev:file:src/memoria/graph/kb_build.py#L324` | `collect_graph_data()` | 生成报告 + 写 `.memoria/graph.json` | 导入/导出报告 |
| R6 | `ev:file:src/memoria/services/document.py#L2124`（`get_graph_data`，L2131 带 `graph_audit`） | 全部边 | RPC 给前端 | **UI 渲染** |
| R7 | `ev:file:src/memoria/services/ui.py#L372` | 同上 | RPC 桥 | UI |
| R8 | `ev:file:src/memoria/graph/link_audit.py#L92`/`#L315`（L103 用 `derive_file_graph_edges`） | 派生边（对比正文 wikilink 与 links） | 产出 7 类一致性 issue | **agent（唯一）**：`validate_kb` 的 `graph_audit` 段（`ev:file:src/memoria/services/agent/tools/kb.py#L443-L445`）+ UI 报告 |
| R9 | `ev:file:src/memoria/services/document.py#L1466-L1501` | `link_audit`/`graph_link_audit` | 保存回执里带一致性诊断 | 写路径/UI |
| R10 | `ev:file:src/memoria/storage/sidecar_validate.py#L294`（`edge_type` 归一）、L312、L344-349、L386-391 | `edges[].type` / `links[].edge_type` / `target_edges` | 类型合法性、targets 非空 | 写闸/校验 |
| R11 | `ev:file:src/memoria/services/agent/plan.py#L187`（`PLAN_EDGE_TYPES`）、L421、L897 | 计划的 `edge_type` 参数 | **只允许 `{reference,extend}`**，其他报 `bad_edge_type` | agent 写路径 |
| R12 | `ev:file:src/memoria/services/agent/tools/kb.py#L3548-L3552` | 不读：只是 **tool description 文案** | 告诉模型有 `upsert_edge` | agent 提示词面 |
| R13 | `ev:file:src/memoria/graph/edge_types.py#L14`/`#L55-L58`/`#L61-L66` | 自身常量 | 3 类型枚举；缺省 relevance `contain .9 / reference .7 / extend .6`；**link 归一化只允许 reference/extend** | 全模块 |
| R14 | `ev:file:src/memoria/services/link_md.py#L6`、`ev:file:src/memoria/graph/kb_build.py#L72-L87` | 正文 `[[id#hint]]` | 把遗留 `#prerequisite/#extend` 迁移进 `links[].edge_type` 并从正文剥离 | 迁移（一次性） |
| R15 | `ev:file:src/memoria/services/link_relevance.py#L9` | `edge_type` | 计算 link relevance（写路径默认值） | 写路径 |
| R16 | `ev:file:src/memoria/services/import_engine.py#L455`、`ev:file:src/memoria/services/import_executor.py#L276` | 图数据 | 导入后重建报告（仅统计） | 导入报告 |
| R17 | `ev:file:src/memoria/ui/static/app/js/app.js#L4335-L4384`、`#L4507`、`#L4647-L4655`、`#L5778-L5779` | `edge_type` | **人工**建/删边、类型下拉（只有 reference/extend）、relevance 滑杆、边徽标 | 人（UI） |
| R18 | `ev:file:src/memoria/ui/static/app/js/graph-engine.js#L7-L10`、`#L23`、`#L103-L104`；`ev:file:src/memoria/ui/static/app/js/graph-view-2d.js#L604`；`ev:file:src/memoria/ui/static/app/js/graph-view-3d.js#L499` | `edge.type` | **只影响颜色**（`EDGE_COLORS`），无过滤/无排序/无折叠 | 人（渲染） |
| R19 | `ev:file:src/memoria/ui/static/app/js/graph-layout-2d.js#L234-L235`（`ev:file:src/memoria/ui/static/app/js/graph-layout-3d.js#L251-L252`） | `edge.relevance` | `strengthScale = 0.55 + rel*0.9` 弹簧强度 | 人（布局视觉） |

### 2.2 零读取点（“缺席”本身就是关键证据）

| 位置 | 实测 | 说明 |
|---|---|---|
| `src/memoria/services/search_kernel.py` | `edge/graph/links` **0 命中** | agent 检索主路径（`search_kb` → `search()`）**完全不碰边** |
| `src/memoria/services/lexical_index.py`、`search_aux.py`、`body_locate.py` | 0 命中 | 索引记录里没有 links/edges |
| `src/memoria/services/retrieval_fusion.py#L149-L161` | `graph_hits` 参数**全仓 0 调用方** | RRF 里有 `"graph": 0.5` 通道权重，但**没有任何生产者**（占位死代码） |
| `src/memoria/services/agent/section_index.py`（S1 粒度读） | `edge/graph/links` **0 命中** | 选“读哪一节”只看 heading，不用边 |
| `src/memoria/services/agent/trace_index.py`（S5 trace） | 0 命中 | 调用级成本记录不含边相关调用 |
| `src/memoria/services/agent/prompt.py` | 0 命中 | 系统提示词不教模型用边 |
| `src/memoria/services/agent/mcp_server.py` | 4 把工具（outline/section/snippet/propose_write） | 跨进程面**没有**边读取 |
| **`src/memoria/retrieval/**`** | **目录不存在** | 任务要求复核的路径不存在；检索实现分散在 `services/search_kernel.py` 等（见上） |
| `read_document` / `read_kp` / `kb_overview` 输出 | `ev:file:src/memoria/services/agent/tools/kb.py#L289-L330`、`#L337-L377`、`#L380-L409` | 只回正文 + KP 清单（file/line/name/snippet）；**不回 links/edges/类型** |
| `resolve_reference`（`ev:file:src/memoria/services/agent/tools/kb.py#L2648`） | 解析**一条**引用 token | 只回“指向什么/是否存在/候选”，不回边列表与类型 |

**结论 A（可复核）**：Python 侧读 `edges`/`edge_type` 的，只有 **图数据生产（R1–R5）、UI RPC（R6/R7）、一致性审计（R8/R9）、写闸校验（R10/R11）、迁移/导入（R14-R16）**。**唯一到达 agent 的边信息是 `validate_kb` 里按上限裁剪后的一致性 issue 行**（R8）。
**结论 B**：agent 的检索、选节、读取、写作、复习路径**都没有**边参与；`retrieval_fusion` 的 graph 通道是**无生产者的占位**。

### 2.3 一个附带发现的“声明≠事实”

`ev:file:src/memoria/graph/collector.py#L47-L49` 的 docstring 写“边仅由两类来源构建（**不读侧车 edges[]**、不扫描正文 wikilink）”，但同文件 L79-L84 明确调用 `derive_sidecar_edges()`（读 `edges[]`，R2）与 `derive_link_edges()`。**文档与代码相反**——这正是本项目反复出现的形态，建议登记（不影响本提案结论）。

### 2.4 数据事实（自测，非转述）

`ev:measure:kg-c-20261025T2035`（脚本与命令见 §8）。

- **类型枚举 3 种**（`contain/reference/extend`，`ev:file:src/memoria/graph/edge_types.py#L14`）；**但存在 3 套不同“允许集合”**：
  - 文件格式校验接受 3 种（`ev:file:src/memoria/storage/sidecar_validate.py#L294` 用 `EDGE_TYPES`；而 `links[].edge_type` 在 L344-350 只允许 2 种、其他报错）；
  - agent 写路径只接受 **2 种**（`ev:file:src/memoria/services/agent/plan.py#L187`）；
  - UI 建边只给 **2 种**（`ev:file:src/memoria/ui/static/app/js/app.js#L4507`、`#L5778-L5779`）；
  - `links[].edge_type` 归一化把 `contain` **静默改写成 `reference`**（`ev:file:src/memoria/graph/edge_types.py#L61-L66`）。
- **四个代表库（working tree，2026-10-25 20:30）**：

| 库 | nodes | 图边 | contain | reference | extend | 显式 edges[]（纯边） | links | 平均度 | 平均入度 | 最大入度 |
|---|---|---|---|---|---|---|---|---|---|---|
| AAA_Vocab | 133 | 404 | 0 | **404** | 0 | 2（全 reference） | 429（**全 reference**） | 6.08 | 3.04 | 18 |
| 行政法 | 49 | 44 | 21（`origin=range`） | 23（`origin=link`） | 0 | 0 | 22（全 reference） | 1.80 | 0.90 | 5 |
| examples | 55 | 83 | 28（range） | 44（link） | 11（link） | 1（reference） | 42（31 ref / 11 ext) | 3.02 | 1.51 | 12 |
| showcase | 35 | 73 | 0 | 62（link） | 11（link） | 0 | 64（55 ref / 9 ext） | 4.17 | 2.09 | 7 |

- **全 12 个带 sidecar 的库**：显式 `edges[]` **合计 3 条，全 reference**（AAA_Vocab 2 + examples 1）；`contain` 在 sidecar 中**从未出现**（0 条）。
- **`extend` 的出处**：`git grep "edge_type: extend" HEAD` 只有 **9 行，全部在 `docs/example/showcase`（官方 demo）**；`examples` 里的 11 条在 HEAD 中不存在（属工作区未提交的 live 改动）；**真实用户库（行政法/AAA_Vocab）0 条**。
- **与 Lead 给的“479/479”的核对**：我**无法复现 479**。现测 AAA_Vocab：links 429（全 reference）、图边 404（全 reference）、sidecar 中 `edge_type: reference` 行 472（含 `target_edges`）；HEAD 已提交子集只有 185 行。`docs/example` 有大量未提交 live 改动 ⇒ 479 应是**另一时刻的快照**。**“reference 占比 100%”这一结论成立**；具体数字请以本次 `ev:measure` 为准（M1：数字随活库漂移，不要引用旧值）。

### 2.5 agent 的真实行为（35 个会话 JSONL）

`ev:measure:kg-c-agent-sessions`（`docs/example/**/.memoria/agent/sessions/*.jsonl`，35 个文件）：

| 查询 | 结果 | 含义 |
|---|---|---|
| `"edge_type"` 出现次数 | **0** | agent **从未**传过边类型参数（所有写边都走默认） |
| `"create_edge"`（原语落地） | **2 条 apply 事件，1 个会话**（2026-10-07） | agent 建纯边 = 全库历史 2 次 |
| `"apply_link_instances"`（attach_links） | 13 行 / 2 个会话 | agent 连“挂链接”都极少做（正文链接多来自 UI/导入） |
| `upsert_edge` op 实际执行 | 0（4 处提及全在 agent 的自然语言推理里） | agent 在会话中**反复权衡后决定不用** `upsert_edge`（session-20260921… L695-L785：多次自问“要用 upsert_edge 吗”，结论是“不需要/不能修”） |

**结论 C**：不存在“agent 选类型”的行为数据；现存 2 条 agent 纯边是**默认值产物**。这与 Lead 的“479/479 全默认”方向一致，且更强：**agent 连边都几乎不建**。

---

## 3. agent 动作 → 需要什么边 → 现在有没有 → token 代价

| # | agent 动作（真实存在的） | 需要什么边 | 现在有没有 | 若走“读边”的 token 代价（实测/估算） |
|---|---|---|---|---|
| A1 | `search_kb` 找资料 | 不需要边（词法/语义已够） | 无边参与；图通道有占位无生产者 | 0 |
| A2 | `outline`/`section` 决定“读哪一节”（S1） | `contain`（结构） | **不需要**：outline 直接给 heading 树（≤800 tok/篇）；contain 由 KP range 派生、与 heading 不完全等价但同属结构信息 | 读 contain 边 ≈ 每个 KP 一条，AAA_Vocab 133 条 ≈ 1.2k–3k tok，**比 outline 贵** |
| A3 | 判断“这两个概念为什么相关”（回答解释性） | 出边 `reference/extend` + 目标名 | **出边已免费**：正文里的 `[[id]]` 随 `read_document`/`section` 一起返回（0 边际 token）；只有“类型/relevance”需额外读 | 出边类型：约 9 tok/条（实测模板） |
| A4 | **反向问题**：“谁引用了我/这个概念的上下游” | 入边（无类型要求，或按类型过滤） | **没有**：只能全库扫 sidecar。AAA_Vocab **43,880 tok**；行政法 4,581；examples 7,322；showcase 5,449 | 有接口后：平均入度 3.04 × ~9 tok ≈ **27–60 tok**（AAA_Vocab），≈ **488×** 省 |
| A5 | 写作时保持术语一致 / 避免重复 | 相似/别名，不是 link 语义 | `suggest_kp_merge` 是 **UI 专用**（`ui.py#L266`），不是 agent 工具；agent 用 `search_kb` 近似名称检索 | 不涉及边 |
| A6 | 写作“必挂链/建边”（kb-spec 规范要求） | 写 link / 写纯边 | 有：`attach_links`（写 links[]）、`upsert_edge`（写 edges[]，默认 reference） | upsert_edge op ≈ 30–60 tok；但**写后 agent 读不回**，只能靠 `validate_kb` 的 issue 行 |
| A7 | 写后自检 | 图一致性 issue | **有**（唯一在用的边消费）：`validate_kb` 的 `graph_audit` 段；AAA_Vocab 实测 **107 条**（missing_sidecar_link 78 / instance_outside_kp 23 / virtual_link 4 / unresolved_target 2），examples 8，showcase 1，行政法 0 | 上限 20 条/文件、40 行明细（`MAX_ISSUES_IN_REPORT=20`，`ev:file:src/memoria/services/agent/tools/kb.py#L71`）≈ 300–600 tok |
| A8 | 复习出题 / 判断前置知识 | `prerequisite`（依赖） | **不存在**：枚举里没有 prerequisite；遗留 `#prerequisite` 被别名成 **reference**（`ev:file:src/memoria/graph/edge_types.py#L18`），语义已丢；复习路径不读边 | 无（类型不存在） |
| A9 | 跨进程（MCP）做同样动作 | 任意 | MCP 只有 4 把读/写工具，无 edge 读取 | 无 |

**硬门槛（按任务要求）**：
- `contain`：agent 用不上（outline 已覆盖结构），**人也只是看颜色**。⇒ 保留为**派生视图属性**（现状即如此），**不进 agent 契约、不新增存储**。
- `reference`：agent 目前用不上；**唯一潜在真实价值是 A4 反向查询**（未证明）；人的消费 = 颜色。⇒ 作为默认桶保留，但**不要把“选它”当 agent 能力**。
- `extend`：唯一消费 = 颜色 + demo 数据；真实库 0 条；**说不清人拿它看什么**。⇒ **应从 agent 面移除；文件格式是否保留请人裁决**（若保留，标注“历史/展示用”）。
- **纯边（有 edge 无 link）**：3 条，全部默认 reference；agent 读不到、`link_audit` **完全不过审计**（`ev:file:src/memoria/graph/link_audit.py#L103` 取到 `_sidecar_edges` 后**从未使用**）、图里只有颜色。⇒ 当前价值≈0；除非 A4 接口落地并把纯边纳入审计，否则**不该作为 agent 可写能力存在**。

---

## 4. Q2 / Q3 / Q4 / Q5 逐条回答

### Q2【重要】边的存在性：从 agent 角度

**事实**：知道一条边，agent **今天**能做的新事只有两件：
1. 在 `validate_kb` 输出里看到“某条 link 没同步/目标解析不到/某行不在 KP 内”（A7）——这是**写质量诊断**，不是推理；
2. 若未来有反向邻接读取（A4），能回答“谁引用了我/我的上下游”——**当前不存在，且未证明这会改善回答**。

**除此之外**：出边在正文 `[[id]]` 里已经可见（0 边际 token）；类型只影响颜色；纯边不可读不可审计。

**“有 edge 无 link”对 agent 的价值**：**今天是 0**（不可读、不过审计、只上色）。它唯一的意义是让**人**的图更完整，或者表达“正文无法/不宜挂锚的关系”。但若 agent 之后也读不到，那 agent 写它只是为满足规范（会话证据显示 agent 正是这样权衡的）。
**⇒ 存在性判定权**：应归**消费者**，不归“图好看”。建议规则：
- (a) 有 **agent 决策消费者**且有可测收益 ⇒ 存 + 可读；
- (b) 有**明确的**人看视图消费者 ⇒ 存（标注 human-only）；
- 两者都没有 ⇒ 不存，或存了也只当“视图投影”（不写进 sidecar、不进 agent 契约）。
当前 `reference/extend` 只满足 (b) 的“颜色”；纯边两者都不满足。

**顺带**：如果人的问题是“边只是文字给个跳转解释入口？”，代码事实是——**正文 wikilink 与语义边是两条链**：`[[id]]`（正文锚点）→ 构建时投影为边；纯边只存在于 sidecar。图把两者合成一份 edges（`derived=true/false`、`origin=link/range/sidecar_edge`），但**这个 provenance 只有 Python 审计用，UI 不展示**（`app.js` 无 `derived` 命中）。所以“边=跳转”在体验上成立，在数据上不成立；这个区别**目前没有给任何人看到**。

### Q3【边类型空间】从 agent 可用性角度 —— **不该让 agent 填类型**

**复核 Lead 给的事实**：
- 枚举 3 种：✅ `ev:file:src/memoria/graph/edge_types.py#L14`；
- agent 能设 2 种：✅ `ev:file:src/memoria/services/agent/plan.py#L187`（reference 默认 / extend），`contain` 被明确“禁手标”（`ev:file:src/memoria/services/agent/tools/kb.py#L3551` 文案）；
- “479/479 全 reference”：**数字我复现不出**（见 §2.4），但**比例结论成立**：现测 AAA_Vocab links 429/429 reference、图边 404/404 reference；全仓显式边 3/3 reference；`extend` 仅 demo（9 条 HEAD）；**35 个真实会话 0 次传类型**。

**结论：让 agent 填类型没有价值，应改为“系统推断 + agent 只推翻（且默认不暴露参数）”**。理由（证据）：
1. **零使用**：35 会话 `"edge_type"` 命中 0；agent 建边 2 次全默认（§2.5）。
2. **零区分度**：`reference` 是 100% 默认桶；`extend` 只出现在 demo。用类型区分“语义”的假设没有数据支撑。
3. **零消费者**：类型只进颜色（R18）；布局只读 relevance（R19），不读 type。agent 侧无任何读取（R8 是 issue，不是类型）。
4. **三套允许集合 + 静默改写**（§2.4）：同一字符串 `contain` 在 edge 合法、在 link 被改写成 reference ⇒ 类型契约现在是**不一致**的，让 agent 选只会放大歧义。
5. **agent 自己在会话里也这么判**：session-20260921 反复权衡 `upsert_edge` 后选择不用（L695-L785）；它把边当“正文挂不了链时的补丁”，而不是“语义选择”。

**建议的替代**（顺序即优先级）：
- S1：**agent 面移除 `edge_type` 参数**（`upsert_edge`/`attach_links` 都不再收类型；系统默认 `reference`，`contain` 只由几何派生）；写回执里可以回“已建默认 reference 边”。
- S2：**统一归一化器**：link 与 edge 用同一个 `normalize_edge_type`；`contain` 要么全允许要么全禁（建议只在派生层出现）。
- S3：等出现**真实消费者**（例如复习排序读 prerequisite、检索读反向邻接）时，再加**派生类型**并给它命名消费者；届时 agent 也只是“确认/推翻系统推断”，不是自由填空。

### Q4【重要】link 类型 vs edge 类型：分开有意义，但**类型属于 edge**

代码事实（`ev:file:src/memoria/graph/edge_types.py#L3` 声明的“唯一权威来源”其实是两个字段）：
- **link** = 正文锚点记录：`anchor_text / targets / instances[{line}] / display_text / edge_type / relevance / target_edges`——回答“**这段正文的哪个位置**可以跳到哪”（`derive_link_edges` 必须拿到 `instances[].line` 且落在 KP range 内才产生边，`edge_derivation.py#L536-L560`）。
- **edge** = 语义关系记录：`source_id / targets / type / relevance`（纯边 `origin=sidecar_edge`，无行号；从 link 投影来的边 `origin=link`，带行号）。
- 图把它们**合并成一份 edges**；`derived`/`origin` 标记只有 Python 审计用，UI 不展示（§4-Q2 末）。

**从 agent 角度**：
- 若 agent 要“读什么/为什么相关” ⇒ 它要的是**语义关系**（edge），不是锚点行号；
- 若 agent 要“改这段正文的跳转” ⇒ 它要的是**写原语**（link），不是关系类型；
- 现状把 `edge_type` **同时**放在 link 与 edge 上，等于同一语义有**两个事实源**（还有 `target_edges` 第三层覆盖）⇒ 一致性成本高，且已产生静默改写/迁移别名。

**建议**：agent 面**只暴露 edge（语义）作为读概念**（前提是它真被用）；link 只作为**写原语**存在。`links[].edge_type` 降级为“历史/投影默认值”，不再作为 agent 可设参数。这样 Q4 的“该用哪个”就不再是歧义。

### Q5【主战场】每条边必须服务一个具体 agent 决策

见 §3 表。归纳：
- **能服务且有实现**：A7 写后自检（graph_audit）——**唯一已存在的 agent 价值**，且它服务的是“写对”而非“想对”。
- **能服务但未实现**：A4 反向邻接（潜在 488× token 节省）——**必须先 A/B 证明改善**，否则不做。
- **已被正文/其他工具覆盖**：A2 结构（outline）、A3 出边（正文 `[[id]]`）。
- **完全无服务**：`extend` 类型、纯边（读不到 + 不过审计）、`prerequisite`（不存在）。
- **token 代价汇总**：出边 0 边际；反向查询现状 43.9k tok → 接口化后 ~27–60 tok；graph_audit 300–600 tok；contain 读边 > outline。

---

## 5. Q1 / Q6 / Q7（与 task-86 D1–D6 兼容）

**Q1 学习场景（简述，承认不是我的主战场）**：真正与学习相关的是“前置依赖排序”，它需要 `prerequisite` 边 + 复习消费者。两者都不存在（枚举无 prerequisite；复习路径不读边；遗留 `#prerequisite` 被别名成 reference）。⇒ **学习场景今天不能为任何边类型提供合法性**。若复习域要它，应由该域给出消费者接口后再加。

**Q6 2D/3D 差异**：agent 不读图。2D/3D 共享同一 `graph-engine` + 同一份 edges；差异只在视觉（3D 光晕/深度）。类型只影响颜色（R18）、relevance 只影响弹簧强度（R19）。⇒ **图是给人看的**；“图要不要给 agent 读”的答案是：**不要读图，读数据**（如果将来要，读的是 edges API，与 2D/3D 无关）。人的角度 2D/3D 的取舍应回到渲染性能/可发现性（不是我这条线）。

**Q7 与 task-86 已裁 D1–D6**：

| 裁决 | 本提案判断 |
|---|---|
| **D1=(a)** 关系本体 4 类（contain/reference/prerequisite/exemplify） | **部分推翻**：`prerequisite`/`exemplify` **不在枚举**（`ev:file:src/memoria/graph/edge_types.py#L14` 只有 3），也没有消费者/数据；`prerequisite` 还被别名成 reference（语义丢失）。建议：**先接受现有 3 类中的 contain（派生）+reference（默认），`extend` 降级；在出现消费者前不加新类型**（对齐 R-R2）。 |
| **D2=(b)** 跨域边允许但默认过滤 | **兼容（人视角）**；agent 视角无消费者 ⇒ 现在谈不上过滤。若未来做 A4 反向读取，过滤应按**token 预算/度数上限**（AAA_Vocab 平均入度 3.04、最大 18），而不是按域。 |
| **D3=(c)** 未知类型回落但留痕 warn | **兼容**，但注意：agent 从不传类型 ⇒ 该路径只服务人与遗留迁移；且 `kb-spec.zh-CN.md` 仍在教 `[[kp-id#extend]]` 语法（5 个库的指令文件都有），而代码会**剥离**它 ⇒ **指令文档已过时**，建议修（这是“声明≠事实”的一条）。 |
| **D4=(a)** 0.5 只做域概览 + 邻域聚焦 | **兼容**：本提案不向 0.5 加边工作；只建议一个**小改**（agent 面去掉 edge_type 参数 + 统一归一化），可放 0.5 或 v1，取决于人是否要动写 API。 |
| **D5=(a)** 默认 force + 毛球提示 | **兼容**：数据支持其阈值——AAA_Vocab reference 占比 100%（触发），行政法 52% / examples 53%（不误报）。 |
| **D6=(a)** 不再补外部对标 | **部分保留**：外部对标回答不了“agent 是否该读边”；**只有本地 A/B 能**（A3/A4 的收益）。建议登记为实验待办而非再写调研文档。 |

---

## 6. 可证伪断言（每条：若观察到 X 则本条不成立）

| # | 断言 | falsifier（可执行） |
|---|---|---|
| F1 | agent 没有任何“边读取”接口 | 在 `src/memoria/services/agent/**` 找到任一工具把 edges/edge_type 返回给模型（除 `validate_kb` 的 graph_audit issue） ⇒ 本条不成立 |
| F2 | 边类型只影响颜色，不影响任何排序/过滤/布局/检索 | 在 `static/app/js/**` 或 Python 找到 `type` 参与过滤/排序/扩召回/布局力计算 ⇒ 本条不成立（`relevance` 不算：它只影响弹簧强度） |
| F3 | agent 从不填非默认边类型 | 任一真实会话 JSONL 的 tool 参数出现 `"edge_type": "extend"` ⇒ 本条不成立（现测 35 会话 0 命中） |
| F4 | `extend` 在真实用户库中 0 条、仅 demo/历史数据 | 在非 `docs/example/showcase` 的 KB 中找到 `edge_type: extend` ⇒ 本条不成立（工作区 examples 有 11 条未提交，属 demo 库，需人判定是否算“真实使用”） |
| F5 | 反向邻接今天只能全库扫 sidecar | 找到已有 API/tool 返回“谁引用了我”且 token < 1k ⇒ 本条不成立 |
| F6 | 纯边（edges[]，无 link）不可被 agent 读取，且不进入一致性审计 | 找到读纯边的 agent 路径，或 `link_audit` 使用 `_sidecar_edges` ⇒ 本条不成立（现测 L103 取到后未用） |
| F7 | `contain` 无任何作者写入面 | 找到允许 agent/UI 写 `contain` 的入口 ⇒ 本条不成立（现测 agent=`PLAN_EDGE_TYPES` 拒；UI 下拉无 contain；文件校验接受但 0 数据） |
| F8 | 图的 provenance（derived/origin/link vs pure edge）不给人看 | UI 任一界面展示“边是派生/手写”⇒ 本条不成立（现测 `app.js` 无 `derived` 命中） |

---

## 7. unknowns / not_doing

**unknowns（每条给 if-true-then）**
- **U1**：1-hop/反向邻接扩召回是否真的改善回答质量或降低总 token？
  *if_true* ⇒ A4 应进 v1（做只读 `edges_of(kp, direction, types)` + 预算截断）；*if_false* ⇒ 边对 agent 零收益，按“人视图”定位，不进 agent 契约。
- **U2**：人是否真的在看边的**类型颜色/徽标**？
  *if_true* ⇒ type 保留在人类 UI（继续只做颜色）；*if_false* ⇒ type 可整体移出（含文件格式）。
- **U3**：AAA_Vocab 107 条 graph_audit issue 是 app 同步缺陷还是用户手改造成？
  *if_app bug* ⇒ 应先修同步（边机制“看起来有、实际坏”）；*if_user edits* ⇒ validate_kb 的边诊断价值更高。
- **U4**：Lead 的“479”来自哪个库/时刻？
  *if_另一个 KB/旧快照* ⇒ 结论不变（比例结论稳定）；*if_总库数* ⇒ 我的口径需与 Lead 对齐后再引用数字。
- **U5**：跨进程 MCP 的外部 agent 是否需要边？
  *if_true* ⇒ MCP 工具面 +1（只读邻接），但这会打破 S3 的 4 工具预算；需要重开 schema 预算讨论。
- **U6**：`target_edges`（每目标单独类型/relevance，AAA_Vocab 43 条、examples 7 条）是否有人手工用过？
  *if_never* ⇒ 与 `edge_type` 一起降级为历史字段。

**not_doing**
- 不做新的外部对标调研（D6 精神；外部资料回答不了 agent 价值问题）。
- 不在本 Phase 改 `src/**`（本提案纯设计）；S1/S2 的写 API 简化需 Lead 裁决后再排期。
- 不做 2D/3D 视觉/布局工作（非本线）。
- 不设计 prerequisite/exemplify 落地（无消费者，加了就是第二个“无消费者字段”）。
- 不迁移/清洗现有 `extend` 数据（先由人裁决 type 去留）。
- 不新增存储格式（“人视图边”可继续由 links 投影，纯边是否保留见硬门槛）。

---

## 8. 附录：复现命令与原始测量

**关键 grep（只读，可复跑）**
```bash
# 谁读 edge_type
grep -rn "edge_type" src/memoria --include=*.py | wc -l        # 81
grep -rn "edge_type" src/memoria/ui/static/app/js | wc -l      # 见 R17-R19
# 检索是否用边
grep -n "edge\|graph\|links" src/memoria/services/search_kernel.py   # 0
grep -rn "graph_hits" src/memoria --include=*.py                     # 只有定义/内部使用，无调用方
# agent 是否读边
grep -n "edge\|graph" src/memoria/services/agent/section_index.py src/memoria/services/agent/trace_index.py  # 0
# 纯边是否被审计
grep -n "_sidecar_edges" src/memoria/graph/link_audit.py   # 只在 L103 赋值，从未使用
# agent 实际行为
grep -c '"edge_type"' docs/example/*/.memoria/agent/sessions/*.jsonl | grep -v ':0' || echo "0 hits"
grep -l '"create_edge"' docs/example/*/.memoria/agent/sessions/*.jsonl | wc -l   # 1 个会话
```

**测量脚本（本次在 `$TEMP` 运行，未入仓；核心逻辑可复跑）**
```python
# 1) sidecar 分布：load_sidecar_for_md → 统计 links[].edge_type / edges[].type
# 2) 图分布：memoria.graph.collector.collect_graph_data(kb) → Counter(e.type, e.origin, e.derived)
# 3) 度数：source_id/targets 聚合 → avg/max in-degree
# 4) token：memoria.services.agent.section_index.estimate_tokens → 全 sidecar JSON 求和
# 5) 审计：memoria.graph.link_audit.audit_kb_graph_links(kb) → issue code 计数
# 6) 会话行为：grep JSONL（见上）
```
**原始测量（`ev:measure:kg-c-20261025T2035`）**
```json
{
  "AAA_Vocab": {"nodes":133,"edges":404,"by_type":{"reference":404},
    "by_origin":{"link":402,"sidecar_edge":2},"links":429,"links_raw_type":{"reference":429},
    "target_edges":43,"explicit_edges":2,"avg_degree":6.08,"avg_in_degree":3.04,"max_in_degree":18,
    "sidecar_tokens_all_files":43880,"audit_issues":{"missing_sidecar_link":78,"instance_outside_kp":23,"virtual_link":4,"unresolved_graph_target":2}},
  "行政法": {"nodes":49,"edges":44,"by_type":{"contain":21,"reference":23},
    "by_origin":{"link":23,"range":21},"links":22,"links_raw_type":{"reference":22},
    "explicit_edges":0,"avg_degree":1.8,"avg_in_degree":0.9,"max_in_degree":5,
    "sidecar_tokens_all_files":4581,"audit_issues":{}},
  "examples": {"nodes":55,"edges":83,"by_type":{"contain":28,"reference":44,"extend":11},
    "links":42,"links_raw_type":{"reference":31,"extend":11},"target_edges":7,
    "explicit_edges":1,"avg_degree":3.02,"avg_in_degree":1.51,"max_in_degree":12,
    "sidecar_tokens_all_files":7322,"audit_issues":{"virtual_link":6,"unresolved_graph_target":2}},
  "showcase": {"nodes":35,"edges":73,"by_type":{"reference":62,"extend":11},
    "links":64,"links_raw_type":{"reference":55,"extend":9},"explicit_edges":0,
    "avg_degree":4.17,"avg_in_degree":2.09,"max_in_degree":7,
    "sidecar_tokens_all_files":5449,"audit_issues":{"missing_instances_row":1}}
}
```

**独立性声明**：本 Phase 仅读取 `PROTOCOL.md`、task-86 产物（`kg-research-phase1/2/3.md`）、`src/**`、`docs/example/**`、会话 JSONL；**未读取**任何其他提案文件。
