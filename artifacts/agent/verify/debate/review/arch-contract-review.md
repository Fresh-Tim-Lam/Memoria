# 对抗评审 · agent-arch 架构立场书（arch-contract）

> **对象**：`position/agent-arch-position.md`（68,766 B / 648 行）
> **前置**：已读 PROTOCOL.md、立场书全文、rulings-lead.jsonl 三条裁决、相关源码。
> **角色**：对抗评审（task-117）。只攻「按原文执行会产生协议想避免的后果」，不攻品味。
> **结论预览**：提案质量高，但**有一条核心 attack 必须裁决**（gate），另两条属可修复的设计债/能力缺口。

---

## §1 逐条质疑

### 质疑 Q-1 【攻击性·核心】`gate` 被当作"省 schema token 杠杆"，但当前代码里 **`kb_has_sidecar` 零求值实现**，且其消费点根本不在工具面投影

**【质疑】**
提案者 §2-Q3 多次断言：gate 是"**被低估的省 schema 成本杠杆**"、"**工具不出现 = 不花 schema token**"，并把 gate「升为一等公民」作为 Q3 的落地要点之一，用它来**对冲 N1 测到的 4,349 token/会话固定成本**（§2-Q4 跨工具规则 #2 原文："schema 固定成本必须被 gate 抵消"）。
但按当前代码执行，**这个对冲是空的**：gate 既不省 schema token，甚至不省已调用的写前校验。

**【规则依据】** PROTOCOL E1（证据身份）、E4（可复现才有效）、P2(b)（覆盖面真伪）。提案者把一个**未实现的机制**当成**已实现的省钱杠杆**来论证，属于 `false_claim`。

**【我的证据】**（全部 file:line，可复核）

1. **`kb_has_sidecar` 全仓库只出现 2 次**，全是"声明"，零"求值"：
   ```text
   grep 'kb_has_sidecar' src/memoria/services/agent/
   → plugins.py:27  (注释："gate 的求值…不在本模块")
   → plugins.py:66  (GATE_VALUES = ("always", "kb_has_sidecar"))
   ```
   也就是说，`kb_has_sidecar` 是 `GATE_VALUES` 这个**合法取值枚举**里的一个字符串，但**没有任何一处代码对"库里是否有 sidecar"求值，来据此裁剪工具面**。

2. **`gate` 字段有解析、有存储、零消费者**：
   - `plugins.py:121` `gate: str = "always"`②字段存在
   - `plugins.py:247-249` 解析时校验 `gate not in GATE_VALUES → bad_field`（会报错，说明它"被认可"）
   - `plugins.py:258` 存进 `ToolDeclaration(gate=gate)`
   - **但 `op_available()`（`plugins.py:536-541`）只看 `tool_id in tool_ids`，完全不读 `self.gate`**
   ```python
   def op_available(self, verb: str) -> bool:
       ids = OP_TOOL_IDS.get(str(verb))
       if not ids or not self.enforced: return True
       return any(tool_id in self.tool_ids for tool_id in ids)   # ← 没有 gate 的任何影子
   ```

3. **即便 gate 求值实现了，它的消费点也不是"工具面投影"**：
   - `plugins.py:473` 注释明说消费链是：`active_plugins(kb_path)` 算能力面 → **`plan.validate_plan()` 用 `op_available()` 闸 op**
   - `plan.py:1044` `if verb in KNOWN_OPS and not active.op_available(verb)` —— 这是**写前拦截**（工具已在 schema 里、模型已经调用它、正在校验阶段才拒），**不是 schema 生成时删工具**。

⇒ 结论：提案者"工具不出现 = 不花 schema token"这句话，在当前代码里**两层都不成立**：
- 第一层（gate 会删工具）—— 求值代码不存在；
- 第二层（删工具发生在 schema 时）—— 现有唯一消费点是写前拦截，工具 schema 早已开进模型上下文。

**【最小修补或替代入口】**
不是"删掉 gate 设计"（gate 的方向可能对），而是**把论断降级为"gap"，并给出 gate 真正要落到的消费点**：
1. 把 §2-Q3 里"gate 是已存在的省 token 杠杆"改写为"**gate 当前是 dead 字段，需要一个『工具面投影器』消费者**：在 `build_kb_tools()`（`kb.py:2867`，提案者自己引用了这个 35 工具的面）之前，按 `active_plugins().tool_ids + gate` 求值，**过滤掉不满足 gate 的工具**，只把存活工具送进 schema"。这才是"工具不出现 = 不花 schema token"的正确落点。
2. 且必须回答 Lead 点名的**会话快照问题**：工具表是 per-session 快照 ⇒ "按库状态变化动态出现/消失"意味着**换库要重新投影**。若投影只在会话启动做一次，跨库切换时 schema 就不刷新。这条必须写进实现约束（falsifier）。

**【若不管会伤害谁】**
- **伤害"省 token"这个产品目标本身**：N1 测出的 4,349 token/会话固定成本，被一个不存在的机制"对冲"了——所有人以为有解药，实际上 schema 成本原样存在。这是最典型的 E3 共享假设没被检验的后果。
- 伤害**后续实现者**：他会相信"gate 已经能裁剪工具面"，在它之上继续设计（如 Q3 的 `budget` 字段与 gate 联动），结果建立在 void 上。

---

### 质疑 Q-2 【攻击性】`tool_schema_ref` / `budget` / `lifecycle.dispose` 三个新字段**当前全部零消费者**，作为契约增量提出违反提案者自己引用的"无消费者即移出"政策

**【质疑】**
Q3 的表提出契约增量：`tool_schema_ref`、`budget`、`lifecycle.dispose`。提案者自己在 §0.1 表格里写「上游对照纪律：每个契约字段必须"有真实消费者"…两条都不满足 ⇒ 移出 v1」（`ev:file:docs/design/agent-plugin-design.md#L15`）。但这三个新字段在本轮立场书里**没有任何消费者**（没有指到任何读它们的代码，因为它们还不存在）。这构成**提案者自己的政策反例**。

**【规则依据】** E1（引用必须可复核——这里引用的是"未来消费者"）、P1（对称举证：新增字段必须给读者）。

**【我的证据】** `plugins.py` 的 `ToolDeclaration` dataclass（`plugins.py:105-121` 附近）当前字段含 `tool_id`/`gate`/`constrain`；`tool_schema_ref`/`budget` 不存在于当前 `PluginDeclaration` 或 `ToolDeclaration`。立场书把它们列为"契约增量"（§2-Q3 表），属于**要新造的字段**，不是"已有字段消费者不足"。提案者没有给任何 `ev:` 指向"谁将读这些字段"。

**【最小修补】**
这条**不是否决**，而是要求**补消费者**：每个新字段必须像 `gate` 一样被追问"谁读它、在哪一步"，且答案必须是**能指到代码接入点**的（如 `budget` 的消费者 = 工具分发层 `Tool.invoke` 的返回截断逻辑）。提案者 Q3 表里"消费者"列写的是"装载器/工具面投影"这类**接口名**，不是**代码接入点**。要求改成 file:line 级（现有 `registry.py` 的 `Tool.invoke`、`tools/kb.py:2867` 的 35 工具组装处）。

**【若不管会伤害谁】**
- **伤害 v1 契约的纯净性**：开了"先加字段、后找消费者"的先例，v1 的 6 字段准入政策（提案者自己引以为豪）会被悄悄架空。
- 伤害**未来生态**：第三方插件照着一堆无消费者的字段写声明，装载器还得"兼容但忽略"，制造新的静默。

---

### 质疑 Q-3 「按 heading 替换一节」当前在写侧**是能力缺失，不是接口包装**

**【质疑】**
提案者 §2-Q4 断言"写侧**不需要新造**……已 patch 式（17 KNOWN_OPS / 16 COMPILED_OPS）……只需回执粒度化 + 预算"。我抽查三类 agent 高频动作：

| 动作 | 现有 op | 覆盖？ | 缺口性质 |
|---|---|---|---|
| 按 heading 替换一节 | 最接近 `replace_lines`（`plan.py:135`）+ `upsert_block`（块级） | ❌ **无 section/heading 语义锚点** | **能力缺失**：没有"定位某 heading 到下一 heading 之间"的锚。必须先用 `read_document` 拿到该节行号，再算 `replace_lines` 的行范围——这是**模型手动算行号**，不是能力 |
| 重命名级联 | `rename_file`（`plan.py:141`）+ `rename_kp`（`plan.py:144`） | ✅ 有（file_ops.py 有 `migrate_sidecar_kp_refs`、`replace_link_id_in_markdown`） | 已有能力 |
| 建新页 | `create_file`（`plan.py:140`） | ✅ 有 | 已有能力 |

**结论**：三类里**只有「按 heading 替换一节」是真缺口**，且是**能力缺失**（缺一个 section 语义定位 + 区间替换的 op），不是"接口包装"。`replace_lines` 覆盖不了它——因为它要求调用方先把 heading 转成行号区间，而"转成行号"这一步恰好是 section 粒度读接口（Q4 的 L1 `section`）要解决的**读侧**能力，写侧没有对应物。

**【规则依据】** P2(c)（攻击覆盖面不全必须给具体身份）；我这里的身份是：`plan.py` 的 `BODY_EDIT_OPS`（`plan.py:152-158`）五项里，**没有 section 锚点 op**。

**【我的证据】** `plan.py:152-158` `BODY_EDIT_OPS = (replace_lines, insert_lines, delete_lines, upsert_block, insert_image_ref)`——全是**行号/块索引**锚，无 `section`/`heading` 语义。`grep 'section|by_heading' src/memoria/services/agent/` 命中里，与"写侧 section 定位"相关的**零**（只有 prompt.py 的 prompt 分节、web.py 的 HTML 标签正则，无关）。

**【最小修补】**
两个方向（我倾向 ①，因为与 Q4 读侧 L1 对称）：
1. **加一个 `replace_section` op**：参数 `{file, heading|kp_id, new_text}`，语义 = "替换该 heading 下到下一个同级/高级 heading 之间"。这样写侧与读侧 L1 `section()` 用**同一套 heading 定位**，agent 不需要手动算行号。这是**能力新增**（工作量不是"回执粒度化"能覆盖的）。
2. 或**坦白改口**：把"写侧不需要新造"改成"写侧有 16 op 已覆盖大部分，**唯「按 heading 替换」需 1 个新 op**"。工作量从提案者暗示的"零新增"变成"新增 1 op + 编译 + 预览 + 测试"。

**【若不管会伤害谁】**
- 伤害**agent 的可用性**：模型每次"改这一节"都要先 `read_document` 拿行号、再心算区间、再 `replace_lines`——多一轮 + 一行号错就改错地方（正是 M-3「记忆型维护」要消灭的心算）。
- 伤害 N1 的收益兑现：N1 说粒度化能省 83-89%，但**读侧粒度化（section）若没有写侧对应 op，模型读完 section 后无法"直接改这个 section"**，被迫回退到手动行号，粒度化收益被写侧拖累。

---

## §2 三个必查点结论

### ① `gate` 升为一等公民 —— **不成立（当前是 dead 机制 + 消费点错位）**

**结论：不成立。** 见 Q-1。双重失败：(a) `kb_has_sidecar` 零求值；(b) 即便求值，消费点是 `plan.validate_plan()` 写前拦截，不是 schema 投影。提案者"工具不出现 = 不花 schema token"在当前代码里是空话。

**缺什么才能改判**：若 `build_kb_tools()` 之前出现一个"按 gate 过滤工具面"的代码路径（file:line），且证明发生在 schema 生成时而非写前，则 gate 的省钱主张当场成立。

### ② §2-Q2 与 R-L2 的兼容性 —— **部分不兼容，M-1 已被 R-L2 否决但立场书正文仍以它为条件**

**结论：部分不兼容（需改立场书，不是改裁决）。**

R-L2 已否决 M-1（"≥1 个真实外部客户端书面需求才立项"），改为"契约层落地后直接交付最小 MCP binding，不等外部需求"。但立场书 §2-Q2 的**条件化交付规则表里，M-1 仍是"触发立项"的第一条件**（`position:390-391`），且 §6 U5 仍把"是否存在真实外部客户端"作为决定 Q2 翻不翻的 unknown（`position:629`）。

**不兼容性**：R-L2 已经说过"**不等外部需求**"，那么"外部客户端是否出现"就不再是 MCP 立项的**门槛**。立场书 P-1（组 0 粒度化先落地）与 D-1（最小集+gate+按需结构化）与 R-L2 **不冲突**（R-L2 也是"契约层落地后"，与 P-1 同向）；但 **M-1 与 R-L2 直接冲突**（一个说"等需求"，一个说"不等"），且 X-1（`position:393` 的"6 个月 <100 次外部调用或无外部客户端 ⇒ 退役"）也**以 M-1 为前提**（R-L2 说"不等需求就做"，那么"无外部调用即退役"这个判据就与"不依赖外部需求"的立项理由自相矛盾——按 R-L2 立项了，半年后没有外部调用，X-1 又把它退役了，等于 R-L2 的"不等需求"白做）。

**最小修补**：立场书 §2-Q2.条件化交付规则表删除/改写 M-1 一行，改为与本裁决一致（"R-L2：契约层落地后直接交付最小 binding"），并把 X-1 的退役判据从"外部调用次数"改为"**绑定层是否被任何代码路径依赖**"（因为按 R-L2，MCP 的存在价值是"交付形态"，不是"外部需求"）。

**若不管会伤害谁**：伤害**裁决的效力**——R-L2 已经否了 M-1，立场书却还拿 M-1 当立项条件，等于让已被否决的论点在正文里以"未来条件"复活，下游 reader 会以为 M-1 仍有效。

### ③ 写侧「不用新造」—— **大体成立，唯「按 heading 替换一节」是能力缺口**

**结论：19/20 成立，1 处不成立。** 见 Q-3。「重命名级联」「建新页」已有 op；「按 heading 替换」缺 section 锚点 op，属**能力缺失**，工作量是新增 1 op + 编译 + 预览 + 测试，不是"回执粒度化"能覆盖的。

---

## §3 对 `not_examined` 的抽查（知识库数据形态）

提案者把「Memoria 知识库数据形态（md/frontmatter/graph/sidecar）」列为 `not_examined`，理由是自己只引了 AGENTS.md 事实源表、未逐字段检查 frontmatter/sidecar/graph，且**自己点出**了 Q4 的 L1 section 粒度依赖 "heading/KP range 的可用性"，"若 sidecar range 解析不可靠，L1 section 会退化为整篇"。

**我的抽查结论**：这条 `not_examined` **诚实且正确**，且它暴露了一个**与之矛盾的设计**：

- 提案者 Q4 的 L1 `section(path, heading|kp_id|line-range)` 依赖"heading → 行区间"与"kp_id → range"的**可靠解析**；
- 但同一个 class 里，写侧（Q-3）没有 section 锚点 op，读侧 section 的锚点来源（heading/KP range）又恰好在 `not_examined` 里——**提案者把一个自己承认没检查的数据形态，当成了 Q4 粒度接口的基础**。

**这条不是攻击"覆盖不全"**（提案者已诚实列入 not_examined），而是指出**依赖倒挂**：Q4 的 L1/L2 建立在"数据形态可解析"这个**未检验前提**上，但它被归到 `not_examined`，而不是 `assumption`。按 E3，这条应该显式登记 `AS-SECTION-RANGE`，并指派 kp-owner 检验"sidecar 的 KP range / heading 定位是否真能产出可靠行区间"，**未检验前，Q4 的 L1 section 应标 "有条件成立"**。

**身份证据**：`freeze-v2.json` 的 expected_categories 含"知识库数据形态"（我按 task 要求用 not_examined 这 1 项做抽查）；提案者 not_examined 表 `owner_to_check: agent-arch（下一轮，或指派 kp-owner）`。

---

## §4 我的自利检查

我放弃过一票否决权（Phase 1 声明）。本评审三条 attack 是否只有对我有利？

| 质疑 | 对我（评审者）有利？ | 说明 |
|---|---|---|
| Q-1 gate 零求值 | **否** | 这是攻击提案者的 false_claim，不增强我的角色权力；反而帮提案者把不实的省钱承诺改诚实 |
| Q-2 新字段零消费者 | **否** | 要求补 file:line 消费者，对双方同等约束 |
| Q-3 写侧缺 section op | **否** | 指出能力缺口，是帮方案变完整，不是剥夺提案者什么 |

三条都不构成"评审者独享的利益"，无自利嫌疑。反过来说，**我没有**用这三条去要求任何"评审者特权"（如否决权、终审权），符合我 Phase 1 的自我约束。

---

## 附：`conditional_object`

- **条件**：若 Q-1（gate）的"工具面投影消费者"在实现阶段被补上（`build_kb_tools()` 前按 gate 过滤 + 跨库重新投影），且提供 file:line + gate 求值测试，则我对"gate 是省 token 杠杆"的 attack **撤回**，转为 accept。
- **reversal_condition**：若 gate 求值被证明仍只发生在 `plan.validate_plan()` 写前拦截、或工具面投影只做一次不随库状态刷新（会话快照），则本 attack 永久成立。

---

## 关闭条件自检

- [x] 每条质疑含【质疑/规则依据/证据/最小修补/伤害谁】
- [x] §2 三个必查点各给明确结论（gate=不成立 / MCP=部分不兼容 / 写侧=19/20 成立）
- [x] 至少 1 条真正攻击性（Q-1 gate zero-value 是硬 false_claim）
- [x] 有 conditional_object 带 reversal_condition
- [x] 报告落 review/arch-contract-review.md
- [x] 未改 src/**
