# KG 设计辩论 · Phase 1 提案 · A 架构/契约（arch-contract）

> **独立性声明**：本提案**未读取** `PROPOSAL-{todo-owner,agent-arch,metrics-baseline}.md`（Phase 1 硬要求）。
> 所有代码事实由我自行 `grep`/读源码/跑数据核实，**不引用 Lead 转述作为证据**。
> **协议**：遵守 `artifacts/agent/verify/debate/PROTOCOL.md`（FROZEN）。证据身份按 E1 标注。

---

## 1. 立场摘要（≤10 行，可被逐条反驳）

1. **Q2：边与链接在代码里【已经解耦】，但共用一个枚举——这是当前设计的真实状态，不是"要不要解耦"的问题。**
   证据：`ev:file:src/memoria/graph/edge_derivation.py#L548`（link 无 instances ⇒ 不产边）+
   `ev:file:src/memoria/graph/edge_derivation.py#L296`（contain 从行区间推导，无 link）+ 实测 2 条 `edges[]` 无对应 link。
2. **Q4：该拆成两个正交概念——但不是"拆成两个枚举"，而是"拆成两个字段"**：
   `link.type`（**链接语义**：为什么这段文字能跳过去）与 `edge.type`（**图谱语义**：这两个知识点是什么关系）。
   理由：现在 `ev:file:src/memoria/graph/edge_types.py#L3` 声明两者同一来源，但
   `ev:file:src/memoria/services/agent/plan.py#L187` `PLAN_EDGE_TYPES` **只有 2 种**（缺 contain）
   ⇒ **同一个枚举的两端已经不对称**，这个不等式是设计缺陷的显式证据。
3. **反直觉主张：0.5 不该改数据结构，该先修"枚举不对称"。**
   因为 429/429 link 全产边、479 条数据 100% reference，**拆字段的收益在数据为 0 时无法验证**；
   而"link 只能 reference/extend、edge 有 contain"这个**已有不对称**是可以立刻修的契约债。
4. **Q5：我支持"每条边必须服务一个决策"，但判据只能挂在【用户可视化决策】上，不能挂在 agent 检索上。**
   实测：`get_graph_data()` 在 Python 侧零调用者，**agent 侧从不读图谱**——
   ⇒ 图谱与 agent 检索是两套未打通的数据通路，这个架构事实比"边该不该存在"更值得上报。
5. **我在写作过程中自我证伪了 2 条**（F4 部分、F5 完全）与之前的 1 条 task-86 裁决（D1 的 exemplify），见 §3 §Q7。

---

## 2. Q1–Q7 逐条回答

### Q1 学习场景 × 知识组织（明确承认我不专长）

**本项我能力受限，如实标注**：我不具备教育/认知科学的专业判断。

我能给的**代码/契约侧**观察（不给学习理论）：
- 现有边类型对"学习路径"的支撑：`prerequisite` **不在枚举里**（`ev:file:src/memoria/graph/edge_types.py#L14`），
  且被 alias 成 reference（`ev:file:src/memoria/graph/edge_types.py#L18`）
  ⇒ **当前数据模型无法表达"先学什么"**。
- 这条是我在 task-86 §3 已论证的（`ev:file:artifacts/agent/verify/kg-research-phase1.md`），本提案不重复。

**`not_doing` 登记**：学习场景分层、认知负荷、教学法映射——留给 todo-owner（产品视角）与 metrics-baseline。

### Q2【核心】边的存在性：edge 是否必须"有 link 才有"？

#### 我的主张：**不需要，而且现在就不是** —— 但需要**显式契约化**

#### 证据（我自己核的，非转述）

| 事实 | 证据 | 含义 |
|---|---|---|
| link 无 `instances` ⇒ **不产边** | `ev:file:src/memoria/graph/edge_derivation.py#L548` `if not lines: continue` | **有 link 无 edge 已合法** |
| `contain` 边**从行区间推导**，不需要任何 link | `ev:file:src/memoria/graph/edge_derivation.py#L296` `derive_contain_edges` | **有 edge 无 link 已合法** |
| `sidecar edges[]` **直接声明边**，不经 link | `ev:file:src/memoria/graph/edge_derivation.py#L643` `derive_sidecar_edges` | 同上 |
| 实测 AAA_Vocab：`edges[]` 直声明的边 **2 条**（无对应 link） | `ev:bench:kg-debate-vocab-links`（复现见 §7） | **数据层已存在"有 edge 无 link"** |
| 实测 429 条 link **全部有 instances**（都产边） | 同上 | "有 link 无 edge"在**这个库**未出现，但代码允许 |

#### 结论

**边与链接在代码层已经正交，但契约层没有承认这件事。**

现在的契约（`ev:file:src/memoria/graph/edge_types.py#L3`）说
「`links[].edge_type` / `edges[].type`：唯一权威来源」——
这句话把两个**独立的产边来源**（link 派生 vs 区间/直声明）说成"同一个来源"，是**契约不精确**。

#### 若解耦（其实只是"把已存在的解耦写明"），图会变什么样？

**不会变。** 因为解耦的**代码行为已经如此**，只是没写进契约。
**这是本提案最容易被驳的点，我主动标出**：
> 若有人能指出"现有 link 与 edge 存在**隐式绑定**（如某处代码强制 link 必须产边）"，则本条不成立。

我查过 `derive_link_edges` 全流程，未发现强制绑定。

### Q3 边类型空间（从契约可表达角度看）

#### 主张：**0.5 只该往枚举里加 1 个（`prerequisite`），不加其他**

| 候选 | 是否进枚举 | 契约层理由 | 证据/依据 |
|---|---|---|---|
| `contain` | **已有** | 自动推导，零作者负担 | `ev:file:src/memoria/graph/edge_types.py#L10` |
| `reference` | **已有** | 兜底 | `ev:file:src/memoria/graph/edge_types.py#L11` |
| `extend` | **已有** | 扩展/延伸 | `ev:file:src/memoria/graph/edge_types.py#L12` |
| **`prerequisite`** | **建议加** | **唯一能回答"先学什么"，且可传递** | `ev:file:artifacts/agent/verify/kg-research-phase1.md`（方向性论证） |
| `exemplify` | **暂不加** | 与 reference 的**语义边界不可判定**（见下） | — |
| `synonym`/`derived`/`contrast` | **不加** | 需 NLP，误判代价 > 收益 | task-86 已论证 |

**为什么 `exemplify` 我改主意了（推翻自己 task-86 D1）**：
task-86 我建议加 `exemplify`。**现在我认为不该在 0.5 加**，理由：
- **"例证"与"引用"的边界无法从数据判定**：范文提到一个词，是"例证"还是"泛指提及"？
  区分需要**判断该词在段落中的角色**，而段落角色没有数据字段（`ev:file:src/memoria/graph/edge_derivation.py#L296` 只做区间包含，不做角色）。
- 若强行加，作者**无法可靠填写**（479/479 默认值的历史已证明作者不填），最终仍是 100% reference。
- **`prerequisite` 不同**：它的判定不需要 NLP——**人可以明确说"这个必须先学"**，是**意图型**关系，不是**推断型**。这是两者本质区别，也是我改变立场的依据。

### Q4【核心】link 类型 vs edge 类型：一个枚举还是两个正交概念？

#### 我的主张：**两个正交概念，但 0.5 用一个枚举 + 一个"不对称修正"，拆字段留 v1**

#### 先看当前的不对称（这是最硬的证据）

| 枚举 | 值 | 证据 |
|---|---|---|
| `EDGE_TYPES` | `{contain, reference, extend}`（**3 个**） | `ev:file:src/memoria/graph/edge_types.py#L14` |
| `PLAN_EDGE_TYPES` | `{reference, extend}`（**2 个，缺 contain**） | `ev:file:src/memoria/services/agent/plan.py#L187` |
| agent 工具可选 | `reference`（默认）\| `extend`，**contain 禁手标** | `ev:file:src/memoria/services/agent/tools/kb.py#L3551` |

⇒ **`contain` 能出现在 edge 里，但写不进 link**（因为它是推导出来的，不是链接写出来的）。

**这个不对称本身就是"link 类型 ≠ edge 类型"的证明**——如果两者真是同一个概念，
就不会出现"edge 有 3 种、link 只能 2 种"。

#### 我的结论（分两步，0.5 只做第一步）

**第一步（0.5，不加字段）**：承认并文档化「**link 类型是 edge 类型的子集**」：
```
link.type  ∈ {reference, extend}        （作者可选的链接语义）
edge.type  ∈ {contain, reference, extend}（图谱边类型，contain 由推导产生）
+ 显式约束：link.type 只能映射到 {reference, extend}，不得映射到 contain
```
**代价**：零代码改动（现状已如此），只需契约文档写明 + 加一条断言测试。

**第二步（v1，拆字段）**：若将来要加 `prerequisite`（意图型关系），**它会暴露"一个枚举不够"**：
- `prerequisite` 作为 **edge.type** 合理（A 是 B 的前置）
- 但它作为 **link.type** 是否合理？**不一定**——"这段文字引用了 B"不等于"这段文字声明了 A→B 的前置关系"。
⇒ **届时必须拆成两个字段**，否则会出现"link.type=prerequisite 但实际只是引用"的语义污染。

**为什么 0.5 不拆**（P1 要求：给理由 + 替代）：
- **数据为 0 时无法验证拆分收益**：479 条数据 100% reference，拆了也没数据填；
- **拆字段要动 schema + 迁移**，而 0.5 是"最小可行"，风险不匹配；
- **替代入口**：先用"link 类型是 edge 类型子集"这条文档化约束（零成本），
  等 `prerequisite` 真要落地时再拆——**那时拆的依据是真实需求，不是预测**。

### Q5 每条边必须服务一个具体决策

#### 主张：**支持，但要限定"决策"包括【渲染/导航】决策**

> **⚠️ 本节我写完初稿后自我推翻了一次，如实记录。**
> 初稿我断言「`contain` 服务 agent 的 RAG 检索」。**核实后这是错的**：
> `get_graph_data()` 在 Python 侧**无任何调用者**（仅 `ev:file:src/memoria/services/document.py#L2124` 定义，消费者是前端 RPC），
> 且 **agent 侧（`src/memoria/services/agent/**`）从不读 `graph_data`/`edges`**——
> agent 的层级来自 `section_index.parent_path`（`ev:file:src/memoria/services/agent/section_index.py#L207`，标题结构解析，与图谱 contain 无关）。

修正后的表：

| 边类型 | 服务的决策 | 决策主体 | 若删掉会怎样 |
|---|---|---|---|
| `contain` | "这一节包含哪些子节"（**层级导航/折叠**） | **用户（前端可视化）** | 前端失去层级折叠；**不影响 agent** |
| `reference` | "这两个东西相关" | 用户（导航） | 用户失去"相关"入口 |
| `extend` | "这是延伸阅读" | 用户 | 与 reference 现状难区分 |
| `prerequisite`（拟加） | "**我该先学什么**" | **用户** | **无法回答学习顺序** |

**修正后的关键结论（比初稿更硬）**：
**目前所有边类型都只服务"用户可视化决策"，没有一条服务"agent 检索决策"。**
⇒ Q5 的判据变成：**若某条边连"用户可视化决策"都不服务，它就该删**；
而"服务 agent 决策"这条论证路径**在当前架构里是空的**。

**这是一个值得上报的架构事实**：图谱与 agent 检索是**两套独立数据通路，未打通**。

### Q6 2D/3D 差异（数据结构与渲染契约角度）

#### 主张：**数据结构零差异，渲染契约差异只在"视口裁剪"，不在"边语义"**

证据：
- 2D/3D 共享同一套 layout 契约（10 个方法），差异只在坐标维度：
  `ev:file:src/memoria/ui/static/app/js/graph-layout-2d.js` vs `graph-layout-3d.js`（同 `linkDistance:108` 默认）
- `graphStyle` 的 `galaxy` 是**纯视觉变体**，不改点位计算
  （`ev:file:src/memoria/ui/static/app/js/graph-view-2d.js#L566` 只改背景色）

⇒ **"边的存在性/类型"在 2D/3D 完全一致**，不存在"2D 保留边、3D 隐藏边"的契约分歧。
若将来要做 3D 的"边深度淡化"，那是**渲染层视觉规则**，不进入数据契约。

### Q7 与 task-86 已裁 D1–D6 的兼容

#### 我主动推翻自己的两处

| task-86 裁决 | 我现在的立场 | 依据 |
|---|---|---|
| **D1 = (a) 4 个类型**（contain/reference/prerequisite/**exemplify**） | **推翻 exemplify**，改为 3 个（contain/reference/+prerequisite，extend 保留） | §Q3：exemplify 与 reference 边界不可从数据判定，是**推断型**关系；prerequisite 是**意图型**，可人工填 |
| **D4 = (a) 0.5 只做域概览 + ego** | **仍成立** | 本提案不涉及可视化范围，只涉及数据契约 |

#### 其余裁决兼容性

| 裁决 | 状态 | 说明 |
|---|---|---|
| D2 = (b) 跨域边允许但默认过滤 | **仍成立** | 与"边存在性解耦"无关 |
| D3 = (c) 回落 + 留痕 warn | **仍成立，且本提案强化它** | §4 会加一条：`link.type → edge.type` 的映射回落必须可计数 |
| D5 = (a) 默认 force + 毛球态提示 | **仍成立** | 渲染层，不受影响 |
| D6 = (a) 不补外部对标 | **本提案改变立场** | 见 §6 unknowns U2：辩论本身要求"调研依据"，我承认 task-86 外部调研不足 |

---

## 3. 可证伪的设计断言（每条写"若观察到 X 则本条不成立"）

| # | 断言 | Falsifier |
|---|---|---|
| **F1** | 边与 link 在代码层已解耦（有 link 无 edge、有 edge 无 link 都可发生） | 若在 `edge_derivation.py` 找到"link 必须产边"的强制代码路径 ⇒ F1 不成立 |
| **F2** | `link.type` 的可表达空间（2 种）严格小于 `edge.type`（3 种） | 若 `PLAN_EDGE_TYPES` 实际含 contain（`plan.py:187` 被改）⇒ F2 不成立 |
| **F3** | `exemplify` 无法从现有数据字段可靠判定 | 若发现某个已有字段能区分"例证"vs"泛指提及" ⇒ F3 不成立，exemplify 应加入 |
| **F4** | 0.5 拆 link/edge 字段的收益**在多数库**无法验证（全局非默认率 3.57%） | ⚠️ **已部分自我证伪**：`examples` 库非默认率 **26.2%（11/42 extend）**，超过我设的 10% 阈值。⇒ **F4 仅在 AAA_Vocab/english-kb/行政法 成立（0%），在 examples/showcase 不成立**。这反而说明：**拆字段的收益是库相关的**，不能一概而论 |
| **F5** | ~~`contain` 服务 agent 决策（RAG 检索粒度）~~ | ❌ **本条已自我证伪**：`graph_data` 在 Python 侧无调用者，**agent 侧（`src/memoria/services/agent/**`）从不读 `graph_data`/`edges` 做检索**；agent 的层级来自 `section_index` 的 `parent_path`（标题解析，`ev:file:src/memoria/services/agent/section_index.py#L207`）。⇒ **`contain` 边只服务前端可视化，不服务 agent 检索** |

---

## 4. 数据/契约变更清单（要动什么、什么形状）

### 0.5（最小，零 schema 变更）

| # | 变更 | 文件 | 形状 |
|---|---|---|---|
| **C1** | 文档化「link.type ⊂ edge.type」约束 | `docs/design/agent-plugin-design.md` 或新 `kg-contract.md` | 声明 + 理由 + 反例 |
| **C2** | 加一条断言测试：`PLAN_EDGE_TYPES ⊂ EDGE_TYPES` 且 `contain ∉ PLAN_EDGE_TYPES` | 新建 `tests/test_graph_contract.py` 或加到现有 | `assert PLAN_EDGE_TYPES <= EDGE_TYPES` |
| **C3** | （若 D3 落地）`link.type → edge.type` 映射回落计数 | 写侧回执 | `edge_type_fallback: N` |

**零数据迁移**（不动任何 sidecar）。

### v1（拆字段，条件触发）

| # | 变更 | 形状 |
|---|---|---|
| **C4** | sidecar `links[]` 增可选 `type` 字段（与 `edge_type` 并存） | `links[].type ∈ {reference, extend, prerequisite}`（link 语义） |
| **C5** | `links[].edge_type` 保留但语义收窄为"派生 edge 的类型" | 向后兼容：缺 `type` ⇒ 沿用 `edge_type` |

---

## 5. 迁移路径（零丢失）

### 0.5 的迁移：**无**

C1–C3 都不改数据，479 条 link / 454 条边**原样保留**。

### v1 拆字段时的迁移（若触发）

```
步骤 1  读：links[].type ?? links[].edge_type ?? "reference"     （新读旧，兼容）
步骤 2  写：新代码写 links[].type，同时写 edge_type 保持旧读者可读（双写）
步骤 3  校验：对全库跑 diff，确认 type→edge_type 映射后与旧 edge_type 完全一致
步骤 4  清理：一个版本后移除双写（旧字段标 deprecated）
零丢失保证：步骤 3 的 diff 为空才允许进入步骤 4
```

---

## 6. unknowns / not_doing（按 M3，登记才合法）

### unknowns（每条带 `if_true_then`）

| # | unknown | if_true_then | 谁来验 |
|---|---|---|---|
| **U1** | `prerequisite` 的真实填充率会是多少？ | 若 <5% ⇒ 加类型无意义，应回到 reference + 用户手动排序 | todo-owner（产品判断） |
| **U2** | 外部业界是否已有"link 类型 vs edge 类型分离"的成熟实践？ | 若 Obsidian/Anki 已证明必须分离 ⇒ 我 §Q4 的"0.5 不拆"应提前到 v1 之前 | **本提案承认未做外部调研**（task-86 同缺陷），需补 |
| **U3** | ~~`contain` 是否真的被 RAG 使用？~~ | ✅ **已自查解决**：**否**。`get_graph_data()` Python 侧零调用者，agent 侧不读图谱 ⇒ contain 只服务前端。**这推翻了我初稿的 F5 与 Q5 初版** | 已验 |

> **另外我承认一个方法缺陷（U2 的延伸）**：我 task-86 与本次提案**都未做外部业界调研**。
> 人这次的原话直指「你们到底做了多少调研，怎么做，依据什么」——**这是对我 task-86 的有效批评**。
> 我的辩护只能是：代码考古发现了"机制层有、数据层没有"这个**别人没看到的事实**；
> 但我不否认"没做业界对标"是**真实缺口**（见 U2）。
| **U4** | 2D/3D 是否真的需要对边做不同处理？ | 若是 ⇒ Q6 结论需修正 | agent-arch |

### not_doing（明确不做）

| # | 不做什么 | 理由 |
|---|---|---|
| N1 | 学习场景/认知科学分层 | 非我专长（Q1 已声明） |
| N2 | 可视化点分布模式 | task-86 已裁（D4），本提案不重复 |
| N3 | 外部本体论对标（RDF/OWL） | task-86 已裁 D6，但**本提案承认这是缺陷**（U2） |
| N4 | 自动推断 exemplify/synonym 等 | 需 NLP，无数据字段支撑 |

---

## 7. 复现

```bash
# 数据核（Q2 的 2 条 edges[] 无 link、429 link 全有 instances）
$tmp = Join-Path $env:TEMP 'kg-debate-vocab'
Copy-Item 'docs\example\AAA_Vocab' $tmp -Recurse      # 用户库只读复制
# 统计脚本见本提案写作时的临时脚本（已清理，逻辑：遍历 sidecars/*.yaml 的 links[]/edges[]）

# 代码核
grep -n "EDGE_TYPES\|PLAN_EDGE_TYPES" src/memoria/graph/edge_types.py src/memoria/services/agent/plan.py
grep -n "if not lines" src/memoria/graph/edge_derivation.py
```

---

## 8. 自利检查（P1 精神）

| 我的主张 | 对我有利吗 |
|---|---|
| Q4「0.5 不拆字段，只文档化」 | **否**——这是更少的代码工作，但也是更保守（可能被批"不作为"） |
| 推翻自己 task-86 的 D1（去掉 exemplify） | **否**——推翻自己的既有结论是成本，不是收益 |
| Q2「解耦已存在」 | **否**——若成立，说明我之前 task-86 没发现这个，是我的疏漏 |

**无自利嫌疑**；且 D1 的推翻是主动的。
