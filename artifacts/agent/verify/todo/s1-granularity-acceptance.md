# task-120（0.5.0-S1 粒度化）独立验收报告

> **验收者**：arch-contract（Lead 指派）。**对象**：agent-arch 的 task-120 交付。
> **方法**：所有脚本/断言/pytest **独立复跑**，自己算 sha，不采信 agent-arch 任何自报数字。
> **结论预览**：**5 项必查 + pytest 全绿，但 3 条建议 + 1 条范围澄清需 Lead 知悉后才签收。**

---

## 0. 验收结论

| 项 | 结论 |
|---|---|
| 复跑 5 脚本 + pytest | **全 PASS**，sha 独立复算一致 |
| ① 三把工具在工具面 | ✅ 39 工具，outline/section/snippet 均 handler 非空且真返回内容 |
| ② 唯一写者链 | ✅ KNOWNOPS 18 / COMPILED 17 / primitives 恒为 `edit_body` |
| ③ R-S1B-4 修复 | ✅ `INVALID_SELECTOR` 全链，真语料复验通过，无 `sections[0]` 静默回退 |
| ④ 回退 | ✅ A13 三断言通过，但**证据定性需 Lead 知悉**（见 §4） |
| ⑤ 密封性 | ✅ sha 两次一致、config 未污染、replace_op 用 tempfile、不写 docs/example |

**总体判定**：**通过，可签收，附 3 条建议 + 1 条范围澄清（非阻断）**。

---

## 1. 复跑结果（独立复算）

| 脚本 | 我的复跑结果 | sha（前 16 hex，**我自算**） | agent-arch 自报 | 一致 |
|---|---|---|---|---|
| section_headings_census | PASS | `e9c4021a…` | `e9c4021a` | ✅ |
| section_read_api | PASS（A1–A14） | `6ef86927…` | `6ef86927` | ✅ |
| section_replace_op | PASS | `11a955e8…` | `11a955e8` | ✅ |
| section_kp_end_impact | NO_IMPACT | — | NO_IMPACT | ✅ |
| section_granularity_ab | PASS | `8873fbf0…` | `8873fbf0` | ✅ |
| pytest（agent_* / doc_anchor） | **106 passed** | — | 106 passed | ✅ |

---

## 2. ① 三把工具在工具面（独立核）

- `build_kb_tools(tempfile)` 返回 **39** 个工具（+3）；`outline/section/snippet` 三把均 `in` 列表。
- 三把 `handler` 均 `callable`（非空）。
- **真体料实测**（不只看声明）：
  - `outline({file:'DeepLearning/ELU.md'})` → 返回 25 个标题列表（"ELU激活函数完整报告 (L1-228)"…）✅
  - `section({file,line:215})` → 正确定位 "「7. 总结」(L215-228，h2)"，返回**该节正文** ✅
- 反例（上次 gate 死字段形态）**排除**：不只是"声明存在"，handler 真能返回内容。

---

## 3. ② 唯一写者链（独立核）

- `KNOWN_OPS` = **18**（含 `OP_REPLACE_SECTION`）✅
- `COMPILED_OPS` = **17** ✅
- `section_replace_op.py` B1 断言：`primitives=['edit_body']` ✅（没有新写原语）
- 实测多场景：h1 替换 / h2 替换 / 同名+path 消歧 / 围栏不截断 / expect 不符拒，全部 `primitives=['edit_body']` 或正确报错。

---

## 4. ③ R-S1B-4 修复（P1 生产缺陷，Lead 亲自查出）

**代码层核（非只看红绿日志）**：

| 检查 | 结果 |
|---|---|
| `section_index.py` 的 `heading is None` 分支 | ✅ 第 326 行，**两条路径都返回 `INVALID_SELECTOR`**（修饰符却无 heading → 报错；完全无选择器 → 报错），无 fall-through |
| `grep "sections\[0\]" src/` | 共 **2 处**：`import_engine.py:273`（**不同语义**，是 section 的 segment_index，非取首个标题）+ `section_index.py:327`（注释，说明"不再静默回 sections[0]"）。**无真正的 `return sections[0]`** ✅ |
| `grep "heading is None" section_index.py` | **仅 1 处**（第 326 行），正是拒绝分支 ✅ |
| 真语料复验（Lead 给的例子） | `near_line` 单独给 → `Error: …INVALID_SELECTOR…` ✅；`line=215` → "「7. 总结」(L215-228)" ✅ |

**结论**：R-S1B-4 修复到位，不是注释空谈。

---

## 5. ④ 回退（>50% 自适应）—— 证据定性判断

**这是 agent-arch 自己标注的薄弱点，我独立判断如下**：

### 5.1 A/B 的"回退 0/20 触发"能否作为回退有效证据？—— **不能，agent-arch 自己的判断是对的**

**我的独立证据**：`section_granularity_ab.py` 的 `build_tasks()` 第 96 行：
```python
cand = [h for h in heads[1:] if h.level >= 2]
```
任务目标节**跳过第一个 heading、且级别 ≥2**。这类节天然是**小节**（占全文比例小），所以**任务构造本身就决定了 0/20 触发回退**——不是"回退机制被证明有效"，而是"回退机制在这个任务集里根本没机会被触发"。

### 5.2 我补充的一个关键数据（用上一轮 as-section-range 产物）

真实语料里 **>50% 全文的节只有 7/3517 = 0.20%**（且多是"单节文档"边缘情况）。

⇒ **这意味着两件事**：
1. A13 的合成用例证明的是"回退**逻辑正确**"，不是"回退**在生产有价值**"——agent-arch 的定性正确；
2. **但反过来，回退的风险权重极低**：99.8% 的节都不触发回退，即使回退有 bug，影响面也只有 0.2%。

⇒ **我的判断**：回退的正确性证据 = **A13 三断言（触发/不误伤/预算保护）已足够**，不需要更多真机证据。因为：(a) 逻辑已用合成用例逐条验证；(b) 生产触发表面积仅 0.2%，不值得为它烧真机额度。**agent-arch 问"连 A13 也不够"，我的答案是：A13 够，甚至因为触发表面积小，回退验收应降权而非加码。**

### 5.3 A/B 两臂公平性（我主动抽查，看有没有"给 B 臂开小灶"）

- **A 臂**：`read_document(offset/limit=2000)` 分页，最多 8 轮；`find_sentence` 先 `search_kb` 命中则停。
- **B 臂**：`snippet`/`section`/`outline`，最多 8 轮。
- **公平性核**：两臂都从**同一个 `build_kb_tools()`** 的 handler 调用；都用**固定策略**（不是真实模型）；命中判据相同（anchor in text）。
- **无开小灶**：B 臂的 `section(heading=…)` 直接 1 轮，对应 A 臂的"按意图直取"，语义对称。唯一不对称是 B 臂多了 fallback 字段（`fallback_used`），但那是**观测字段**不是策略优势。

**结论**：A/B 两臂公平，无开小灶。

---

## 6. ⑤ 密封性（独立核）

| 检查 | 结果 |
|---|---|
| 连跑两次 granularity_ab | sha 前 16 均 `8873fbf0`，**一致** ✅ |
| config/ 是否污染 | `git status config/` **空** ✅ |
| replace_op 是否写 docs/example | 读脚本确认用 `tempfile.mkdtemp(prefix="memoria-s1b-")`（第 178 行），**不碰仓库 KB** ✅ |

**但我发现一个与 task-120 无关、却需要 Lead 知悉的脏状态**（见 §8）。

---

## 7. agent-arch 三条已知限制 —— 我的独立判定

### 限制 1：A/B 是代理指标（完成率无真机证据）

**判定**：**算关闭条件 2 的充分证据，但需在签收记录里显式标注"完成率未证"**。

理由：
- 代理指标（检索充分性 + 固定策略轮数）**证明了它承诺证明的东西**：token 侧收益 + U3 不反升；
- "完成率不降 >10%"是**另一个命题**，代理指标**不能**证明它，但 A/B 的 veredict 里已诚实写 `nature: PROXY`（第 318 行），且 `note` 写"完成率需 metrics-baseline 真机补"（第 352 行）。
- **我的判断**：token 侧收益已足够支撑"S1 前进"；完成率是**下一阶段**（真机任务集）的事，不该卡在本轮。**前提**：签收时把"完成率未证"作为**已知债务**登记，而不是假装关闭了。

### 限制 2：R-D2 "债务不许增长"机检是否真会 FAIL

**判定**：**会 FAIL（对 Python 有效），但有一个范围澄清必须点明**。

我读了 census 代码，确认机检 `_scan_py_heading_re`（第 296 行 `if not name.endswith(".py")`）**只扫 `.py`**。`PENDING_UNIFICATION` 白名单只列 3 个 py 模块（`mention_proposals.py`/`search_aux.py`/`suggest_metadata.py`）。

**但我发现 agent-arch 验收包措辞的盲区**：它说"仍有 3 个 py 模块 + **前端自带正则**"，而**前端 JS 的 `#{1,6}` 完全不被 census 覆盖**。我 grep 到前端有至少 **5 处** heading 正则（`lexer.js:69`、`markdown-preview.js:883`、`app.js:8001`、`app.js:11723`、`math-normalize.js:34`），这些**不在白名单、也不被扫描**。

**这是不是 bug？—— 不是**。因为 R-D2 的目标是"**agent 后端寻址语义**统一"，前端 `lexer/parser/markdown-preview` 是**渲染层**，本就该有独立的 `#` 解析，不该被 agent 的 census 管。

**但有一个命名/文档风险**：如果未来有 agent **误以为** `section_headings_census.py` 是"全仓唯一 heading 正则"的保证，会误判前端也被覆盖。**建议**（非阻断）：在 census 脚本 docstring 里加一句"只覆盖 agent 后端寻址语义，前端渲染层正则不在本机检范围"。

### 限制 3：kb.py +181 行漂移

**判定**：需确认没有顺手改其它 docs。我 spot-check 了 `docs/design/dsh-agent-port.md` 是 +§12 的新增（agent-arch 自报），未发现其它 docs 改动。但**这条我不能完全独立验证**（需要 git diff 全量比对 docs/，超出本轮验收范围）。**建议 Lead 在提交时用 `git diff --stat docs/` 复核**，确认只有 `dsh-agent-port.md` 一个文档改动。

---

## 8. ⚠️ 一个与 task-120 无关、但需 Lead 知悉的脏状态

`git status docs/example/AAA_Vocab/.memoria/` 显示 **30+ 个 sidecar 被修改 + 2 个删除**（manifest.yaml、大量 `sidecars/**/*.memoria.yaml`、`writing/part2/1.memoria.yaml` 被删）。

**核实**：
- 这些文件**最近 3 小时内无修改时间**（`LastWriteTime` 过滤为空）⇒ **不是本轮（agent-arch 或我）造成的**；
- 是**更早就存在的未提交工作区脏状态**。

**为什么在这个验收里提**：这些 `.memoria/` 是我跑 read_api / granularity_ab 时的**测量基线态**。虽然测量的是 `.md` 原文（heading 解析不依赖 sidecar），但**严格讲**，测量若声称"密封"，应声明是基于这个脏工作区态跑的。**这不影响 heading 结论**（heading 解析只读 md 文本），但影响"测量可复现性"的完整性声明。

**建议**：Lead 在收口时确认这 30+ sidecar 改动是谁的、是否应提交或回滚。**不是我、不是 agent-arch（本轮）造成的。**

---

## 9. 最终签收判定

**通过**，条件如下（建议 Lead 在派发日志里记这 4 条）：

1. **A/B 代理指标**：作为"S1 前进"的 token 侧证据成立；"完成率不降"登记为**已知债务**，交 metrics-baseline 真机补，不假装关闭。
2. **回退证据定性**：A13 三断言足够；因真实触发表面积仅 0.2%，回退验收降权，不追加真机额度。
3. **census 范围澄清**：机检只覆盖 agent 后端 py 正则，前端渲染层不在内；建议在 docstring 加一句防未来误读。
4. **脏状态**：AAA_Vocab/.memoria 的 30+ sidecar 改动非本轮造成，Lead 收口时需确认归属。

**agent-arch 的交付质量**：5 项必查全过，已知限制诚实自报，A/B 脚本没有给 B 臂开小灶，R-D2 白名单机检对 Python 是真会 FAIL 的（不是糊弄）。唯一需要改进的是**验收包措辞的精确性**（"前端自带正则"未说清"不在机检范围"），属文档清晰度问题，不属代码缺陷。
