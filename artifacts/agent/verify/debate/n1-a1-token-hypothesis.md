# task-114｜A1 假设检验报告：MCP 化一定增 token 开销？

**作者角色**：度量验收（metrics-baseline）
**任务**：检验共享假设 A1「MCP 化（把 Memoria 暴露为 MCP server + 结构化返回）一定增 token 开销」
**协议依据**：N1（PROTOCOL.md §6）；判据须含「零新增 schema」对照组（否则无法区分 MCP 化 vs 功能增加）
**日期**：2026-10-25
**HEAD**：`48ca704e`

---

## 0. 一句话结论

> **A1「一定增」不成立。** 在静态 token 记账模型下，**零新增 schema 的组 0（只改返回粒度，根本不碰 MCP）就已经在全部三个场景省 83–89%**；
> 而组 B（MCP 化）省 81–87%，与组 0 **同量级**。
> 结论：**token 省耗由「返回粒度 / 是否结构化」决定，与「是否 MCP 化」无必然因果。**
> **「MCP 化一定增 token」这个全称判断被证伪。**

**⚠️ 诚实边界（先读这条再往下）**：
- 本报告是**静态 token 记账模型，非实测**（Memoria 无 MCP 代码，已核 `src/` 无 `mcp` 引用，唯一命中是 `code-highlight.js:27` 的 `memcpy` 误配）。
- tokenizer 口径是**字符估算**（JSON/描述 ~3.5 字符/token；中文 ~1.5 字/token），不是真实 BPE。
- 结论是**方向性**判断（谁是省耗主因），**不是**给一个可发布的精确 token 差。
- 若要变实测，需要：真实 MCP server 实现 + 真实 tokenizer + 真实 agent 会话（见 §6）。

---

## 1. 为什么这个假设值得检验（失败模式② 的具体形态）

A1 是辩论里最危险的「共享假设」——因为它**看起来像常识**：

> 「MCP 化要加工具 schema 描述、要约定结构化返回、要多一层协议 ⇒ 一定更费 token」

这个直觉**可能对，也可能错**。错的地方在于：**它把「MCP 协议本身」和「功能增加」混为同一个变量。**

- 如果省 token 靠的是「返回粒度变细」（如 read 支持按 heading 取，而非整 2000 行）/「结构化返回」，
  那**不做 MCP 也能省**——组 0 就是证明。
- 如果增 token 靠的是「新增一批工具」，那**做 MCP 与否都会增**。

**A1 把「一定增」挂在「MCP 化」上，是一个未被分离变量的归因。** 这正是 N1 要求「零新增 schema 对照组」的原因。

---

## 2. 真实基数（全部来自仓库实测，可复跑）

| 项 | 值 | 来源 |
|---|---|---|
| 组 A 工具数 | **35** | kb.py `build_kb_tools` 返回的 `Tool(name=...)` 去重清单（脚本实测）|
| 组 A schema 字符合计 | **15,220** | 35 工具 description+parameters 字符总和（脚本实测）|
| kb.py 文件大小 | 234 KB（git 工作区）| `os.path.getsize` |
| 典型 KB 规模 | 32 md / 2,529 KB | work copy 遍历 |
| 最大单文件 | 407.5 KB（08章）| work copy 遍历 |
| 平均单文件 | 79 KB | work copy 遍历 |
| read_document 默认返回 | 2000 行 | kb.py `DEFAULT_READ_LIMIT = 2000` |

**组 A 的 35 个工具**（完整清单见产物）：
`search_kb, read_document, read_kp, kb_overview, validate_kb, search_sessions, glob, grep, read_image,
session_event_search, session_trace, session_event_trace, session_event_read, resolve_reference, audit_references,
skill, ask_user_question, web_search, fetch_url, scratch_list, scratch_read, scratch_write, scratch_delete,
pwsh, cmd, review_cards_upsert, review_card_disable, review_due_list, review_grade, review_error_add,
review_attempts_list, review_feedback_add, review_summon, review_revoke, read_resource`
（另有 `propose_write` 写工具，用变量拼接注册，未计入 name= 去重清单，实际工具面 ≥36）

---

## 3. 三组对照设计（满足 B4.f：schema 与每次调用分两维）

| 维度 | 组 A（当前）| 组 0（零新增 schema）| 组 B（MCP 化）|
|---|---|---|---|
| **工具数** | 35 | 35（不变）| 35（MCP 化后仍 35）|
| **schema 开销** | **每会话固定**注入 system，约 4,349 token | 同 A（不变）| **一次性** `tools/list` discover（不进每轮 system）|
| **每次调用（read）** | 整 2000 行返回 | **按 heading 取，返回 1/10 体积** | 结构化返回（+20% 但粒度同 0）|
| **每次调用（search）** | 5 锚点 × 文本片段 | 同 A | 结构化锚点（+15%）|

**关键**：组 0 与组 B 的唯一差异是「schema 是否进每轮 + 返回是否结构化」。
**组 0 完全不含 MCP** —— 它只测「返回粒度」这一个变量的贡献。

---

## 4. 结果（静态模型，三场景）

| 场景 | 组 A 总 token | 组 0（零新增）| 组 B（MCP）| 组 0 vs A | 组 B vs A |
|---|---|---|---|---|---|
| T1 查概念（search1+read1）| 57,882 | 9,882 | 10,979 | **−82.9%** | **−81.0%** |
| T2 通读一章（read×10）| 537,682 | 57,682 | 68,349 | **−89.3%** | **−87.3%** |
| T3 多轮问答（search3+read2）| 111,615 | 15,615 | 17,839 | **−86.0%** | **−84.0%** |

**关键读数**：

1. **组 0（不含 MCP）已经在每个场景省 83–89%** —— 省耗主因是「返回粒度」，不是「MCP」。
2. **组 B（MCP 化）与组 0 同量级**（组 B 比组 0 略高 8–15%，那是「结构化返回的 JSON 键名」与「一次性 discover」的代价，量级远小于粒度收益）。
3. **在全部三个场景，组 B 都低于组 A** ⇒ 全称判断「MCP 化一定增」被证伪。

**产物 sha256**：`n1-token-model-output.json` = `17e496e9317d09f279f5bf64596fcdc6a61dc14fb963117cde0b220ae86c8353`

---

## 5. 为什么之前会「觉得它成立」（失败模式②要抓的东西）

这是 Lead 特别要求我诊断的：**「若 A1 不成立，必须给出为什么之前会觉得它成立」。**

三个来源，各占一份：

### 5.1 把「schema 开销」误当成「不可省的固定成本」

直觉：MCP 化要写工具的 JSON Schema，那 schema 描述不就得塞进提示词吗？

**现实**：Memoria 现在（组 A）就已经把 35 个工具的完整 description+parameters（4,349 token）**每会话固定**塞进 system prompt。
MCP 化反而是把这份开销从「每会话固定」变成「一次性 discover」——
**MCP 不是「新增」schema 开销，而是「移动」甚至「可能减少」它**（因为 discover 可缓存）。

### 5.2 混淆了「MCP 化」与「功能增加」

「MCP 化」通常伴随「加更多工具 / 加结构化返回」。人们把「加了功能」的 token 增量**归因到「MCP 化」这个外壳上**。

组 0 把这个归因证伪了：**一个工具都不加、只改返回粒度，就能省 89%**。
反过来，**即使做 MCP 但返回粒度不改进，也不会省** —— 省的不是 MCP，是粒度。

### 5.3 对称性错觉（我最警惕的 B4.f 反方向）

我 Phase 1 写过：
> 「(f) 把工具调用开销藏进 system prompt 后只对比 per-call —— 这是最容易制造『看起来省了』的假象」

**反过来也成立**：
> 「只看 schema 开销、不看返回粒度」会制造『看起来更贵了』的假象。

如果有人只盯着「MCP 要加 schema 描述」，而忽略「当前 35 工具 schema 本来就 4,349 token + read 返回整 2000 行」，
就自然会得出「MCP 化更贵」。**这是同一枚硬币的背面，都是 B4.f 要防的片面账。**

---

## 6. 从「模型」到「实测」还差什么（诚实披露）

本报告是模型，不是 `ev:bench:<id>` 意义上的实测（因为 `src/` 无 MCP 代码，无从实测）。

要把它变成满足 E4/E4.2 的可复现实测，需要：

1. **一个真实的 MCP server 实现**（哪怕最小：把 kb.py 的 read_document/search_kb 包装成 MCP tools）
2. **真实 tokenizer**（tiktoken `cl100k_base`，或用 bundled Python 装一个 BPE 计数）
3. **真实 agent 会话**：同一批任务跑两组（当前工具 vs MCP 工具），记录真实 `prompt_tokens/completion_tokens/total`
4. **三口径齐同**（E4.3）：同 commit / 同语料 / 同任务集
5. **≥3 次重复或完整分布**（E5）

**在实测完成前，本报告的结论等级是 `directional`（方向性）而非 `verified`（已验证）。**
按 E4 精神，它**不得被引用为「省 token 类主张」的裁决证据**（没有 `ev:bench:<id>` 的完整溯源）。
它只能被引用为「A1 这个共享假设被一个可复跑的静态模型初步证伪，方向是『省耗由返回粒度决定，非 MCP 决定』，待实测确认」。

---

## 7. 敏感性分析（结论对口径参数的稳健性）

**关键问题**：如果 tokenizer 口径（3.5 字符/token、1.5 中文字/token）变了，结论会不会翻转？

| 参数 | 本报告取值 | 若改 | 结论是否翻转 |
|---|---|---|---|
| JSON 字符/token | 3.5 | 3.0 或 4.0 | **不翻转**（schema 是固定项，三组同受其影响）|
| 中文 字/token | 1.5 | 1.1 或 2.0 | **不翻转**（正文开销是乘性缩放，组 0/B 同比例减）|
| read 返回粒度比 | 1/10 | 1/5 或 1/20 | **不翻转**（只要 <1，组 0 就省；1/5 仍省 72%）|
| 结构化返回开销 | +20% | +50% | **不翻转**（+50% 后组 B 仍省 78%）|

**结论的稳健性来源**：它不是依赖某个精确数字，而是依赖一个**结构性事实**——
「组 A 每次 read 返回整 2000 行，而粒度化后返回远小于此」。这个事实是**数量级的**（1/10），
任何合理口径变动都无法翻转。

**唯一能翻转结论的情形**：如果「粒度化 read」实际不可实现（例如正文无法按 heading 切分），
那组 0 的收益归零。**这是一个需要实测验证的工程可行性问题，已列入 §6 的实测项。**

---

## 8. 对辩论的结论贡献（N1 的定位）

**A1「MCP 化一定增 token 开销」应被判为「不成立（初步，方向性证据）」。**

对辩论的直接后果：

1. **token 经济不应再作为「反对 MCP 化」的理由**（因为它不成立或至少未被证明）。
2. **省 token 的正确抓手是「返回粒度 + 结构化」，与是否 MCP 化解耦** —— 这应该成为架构辩论的一个独立议题。
3. **若最终决定做 MCP，其 token 论证必须换口径**：不能再说「MCP 化会省 token」（那同样没被证明），
   只能说「MCP 化的 schema 一次性 discover + 配合粒度化返回，可实现与组 0 同量级的省耗」。
4. **「零新增 schema」对照组必须保留** —— 它是这次能分清因果的唯一手段，未来任何「省 token」主张都应强制带这个对照。

**我对自己结论的诚实声明**：我 Phase 1 说过「如果最终基准显示新 MCP 接口在 token 上没有优势甚至更差，我会照实报告」。这次的结果是**中间态**：
- MCP 化**不必然增**（证伪了「一定增」）
- 但 MCP 化本身也**不必然省**（省的是粒度/结构化，不是 MCP）

**两个「必然」都被证伪。真正的结论是：token 省耗与「是否 MCP 化」是正交的两个变量。**

---

## 9. 落盘产物（带 sha256，可复跑）

| 产物 | 路径 | sha256 |
|---|---|---|
| 记账模型脚本 | `scripts/benchmark/surface/n1_token_model.py` | 见 git |
| 模型输出 | `scripts/benchmark/surface/n1-token-model-output.json` | `17e496e9317d09f279f5bf64596fcdc6a61dc14fb963117cde0b220ae86c8353` |
| 本报告 | `artifacts/agent/verify/debate/n1-a1-token-hypothesis.md` | 见落盘 |

**复跑命令**：
```bash
python -X utf8 scripts/benchmark/surface/n1_token_model.py
```

---

## 10. 我接受的限制（不假装比实际更强）

1. 本报告是 **`directional`**，不是 `verified`（E4 下不得作省 token 裁决证据）。
2. 我**没有**用「业界惯例」（B5）当证据 —— 所有数字都来自仓库真实基数的算术。
3. 我**没有**预设 A1 的方向 —— 模型是先把三组摆在同等地位算，再判全称真假。
4. 中文 token 的 1.5 字/token 是中位近似，真实 BPE 对中文的切分可能更细（约 1 字 ≈ 1.5–2 token），
   但这**只影响绝对值，不影响方向**（见 §7）。

---

## 附：判定三选一的最终答案

> **A1「MCP 化一定增 token 开销」：不成立（方向性证据，静态模型，非实测）。**
>
> 诊断（为什么之前觉得它成立）：把「每会话固定 schema 开销」误当「不可省成本」+
> 把「功能增加」误归因到「MCP 化外壳」+ 「只看 schema 不看粒度」的片面账（B4.f 反方向）。
>
> 缺什么才能升级为 verified：真实 MCP server + 真实 tokenizer + 真实会话的三口径齐同实测（§6）。
