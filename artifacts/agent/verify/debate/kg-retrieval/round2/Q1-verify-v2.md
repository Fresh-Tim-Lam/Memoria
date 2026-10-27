# Q1 复核 v2：对 `Q1-research.md` v2（§13 证据层）的独立验真

> **复核员**：agent-index-verifier。**对象**：`round2/Q1-research.md` v2，sha256 `fb49ba06b21e90aed6d2a163ce32d72d434587826fb9fa50174398f4443439b0`（65,343 B，562 行；本轮首次按此 sha 复核）。
> **新增产物**：`round2/scripts/q1_revision_probe.py`（sha256 `bb8bf50a63ad464a…`）→ `round2/data/q1-revision.json`（sha256 `4921c8dda8f3eb22…`）。
> **旧对象**：v1（`01fda8ce…`）的 `Q1-verify.md` / `Q1-verify-addendum.md` 只对 v1 有效，本报告不覆盖它们。
> **纪律**：不 commit、不改研究员文件；只读语料；独立复算。本轮新增了外部核验（arXiv 摘要、GitHub API 许可/路径）与产品代码实测。

## 0. 结论总表

| Lead 指定复核项 | 结论 | 一句话 |
|---|---|---|
| ① §13.1 证据分层（13 条主张各标【论】/【码】/【源】/【语】/【经验判断】） | **部分通过** | 分层规则 R-a/b/c 与 13 行三源表**存在**；但「每条都带统一标签」不成立（表里是列+定性文字），且 **#2/#3/#4 的定性偏宽**、**#1 被低估**（漏掉可用的两源） |
| ② §13.2 声称读过的模块/文件行号抽查 | **通过** | 我抽查了 **20 处** file:line（不止 3 处），**全部真实存在且语义匹配**；HEAD sha、dirty 工作区声明也属实 |
| ③ 主动把孤儿 0.0%/anchor 99.7%/69%/61.8%/28.6% 标【语】并承认 | **部分通过** | §13.4/§13.5b 文字确实承认且标了【语】；但 **§0/§4/§5.1/§6.1/§7/§9 的正文仍以「通过证据/结论」形式保留旧数**，同一文件出现两套数（正是本项目反复踩的坑） |
| ④ §13.5/13.5b 逐条对账我的 13 项 + S1–S9 + C1–C7 | **部分通过** | 覆盖基本齐全（12 行表承运 13 项）；但 **C1 的「已加解释」不成立**（见下），且更正表本身新增了 3 处数字/口径错误 |
| ⑤ §13.6 的 C1–C14 是否都能落到 file:line、有无编造 | **部分通过** | C1–C8/C10–C14 可落到代码·文档行号或概念事实；**C9 的「快照差」归因是未验证编造**（设计草案明确写同一 14:09:46 快照）；C2 的行号引用小幅偏移 |
| ⑥ 「结论不变但依据换源」是否真的换了 | **部分通过** | **A1 / A2 / B 真换源**（代码事实）；**C 的「粒度方向三源支撑」不成立**（E08 变量错配，见 §2）；且正文旧论证未清理 |
| 附：那两条论文是否被正确引用、结论是否被夸大 | **引用正确、结论被夸大** | 标题/URL/摘要均对；但 **E08 的倒 U 是对「检索返回的 chunk 数」**，不能支撑「索引单元应更小/切片粒度」；E09 只证明「语义切分不必」，不证明「heading 更优」 |
| 附：仍标【经验判断】的 13 条里，有没有本可补证的 | **有 4 处漏证** | #1（代码+开源=两源被忽略）、#5（本仓外部研究已给「字符偏移」证据）、#12（**可用代码实测**，我实测了）、#10（可选 E05/E06，但需 caveat） |

> 一句话：**v2 是实质性改进**（项目对齐与 A1/A2/B 的代码依据真实、可核；HEAD 三元组已补；修订产物可复跑），
> 但 **C 的设计依据仍是「类比 + 变量错配的论文」**，且**修订层没有合并回正文**，导致同一文件两套数、两套结论口径。

---

## 1. 论文验真（Lead 重点 1）

我用 arXiv 摘要原文核对（2026-10-27 抓取，URL 见下），与材料/外部 E 表逐项对照：

| 论文 | 材料引用 | 原文事实 | 判定 |
|---|---|---|---|
| **E08** arXiv:2409.01666 | 「OP-RAG：检索块数↑→答案质量先升后降（倒 U，需有界）」 | 标题 *In Defense of RAG in the Era of Long-Context Language Models*；摘要原文：**"as the number of retrieved chunks increases, the answer quality initially rises, and then declines, forming an inverted U-shaped curve"**；甜点区指「比整段长上下文质量更高且 token 更少」 | **引用准确**（标题/URL/变量都对）。**但不能支撑**材料 #2 的「索引单元应是'小单元匹配/大单元阅读'（切片+kp_ids[]）」：倒 U 的自变量是**检索时喂给模型的 chunk 数量（k）**，不是**索引侧单元大小/切片粒度**。它支持「检索/上下文预算必须有界、A/B 要扫多档预算」（#4、§8.3 的 F 建议），**不支持「把索引单元切小」** |
| **E09** arXiv:2410.13070 | 「语义切分成本不被稳定收益抵消」 | 标题 *Is Semantic Chunking Worth the Computational Cost?*；摘要原文："computational costs associated with semantic chunking are not justified by consistent performance gains"（对比 fixed-size chunking，三任务） | **引用准确**。但注意：E09 只证明「语义切分不必」，**不证明「heading 结构切分更优」**（它没测 heading 结构）。材料 #3 用 E09 作「用结构边界」的【论】略宽；#3 真正撑住的是【码】heading 唯一入口 +【源】LlamaIndex MarkdownNodeParser，**仍算两源可接受** |

**结论**：两条论文**没有编造、没有引错标题**；夸大点在**把 E08 的「检索 k」当成「索引单元粒度」用**。
材料自己在 §13.3-#2 写了「具体预算数字无三源」、#4 写「1200 字不是三源结论」，但 **§8.1-3 又写「粒度方向有三源支撑（v2 换源）」**——与 §13.3 自相矛盾（见 §5）。

### 开源（OSS）验真

- LlamaIndex：GitHub API 实测 `license.spdx_id = MIT`（LICENSE 头 "The MIT License Copyright (c) Jerry Liu"）；commit `8797f52b` 的 `llama-index-core/llama_index/core/node_parser/text/` 下**确有 `sentence_window.py`**（API 列目录核实）。`HierarchicalNodeParser` 在 E12 里引自官方文档（不是 text/ 目录），材料的引用方式与 E12 记录一致。**通过**。
- Aider：GitHub API 实测 `license.spdx_id = Apache-2.0`；`aider/repomap.py` 存在（E17 记录其 L49 `map_tokens=1024`、L56 `map_mul_no_files=8`）。**许可通过**；具体源码行号我未逐行复核，标"无法判断"（不影响结论）。
- 材料 §13.3 脚注声明「LlamaIndex/Aider 的许可与路径沿用 E 记录，未重复抓取源码」——**诚实**，且与我的独立核验一致。

---

## 2. §13.2 项目对齐抽查（Lead 重点 2）——**通过**

我抽查（实际逐处打开源码/文档核对，共 **20 处**，Lead 只要求 3 处）：

| 引用 | 实测 | 语义匹配 |
|---|---|---|
| `kb.py:337-377` `_read_kp` | 337 行 `def _read_kp`；349 `start = entry.start_line or 1`；350 `end = entry.end_line or start`；377 `return ToolOutput(...)`；全文无 `range_ok` 判断 | ✅ |
| `kb.py:364` | `header = f"知识点 {key}（{entry.name}）@ {entry.file}:{start}-{end}"`（回显 kp_id） | ✅ |
| `kb.py:248` | `search(text, ..., modes="lexical", ...)`（agent 只用 lexical） | ✅ |
| `kp_index.py:23-25,62-64,81-83` | `range_ok/start_line/end_line` 字段与赋值、`start_line=None if not ok` | ✅ |
| `locator.py:18-66,67+` | `locate_snippet`（18 起）/`resolve_range`（67 起），hint 优先 | ✅ |
| `kp_resolver.py:5,18` | import 与 `resolve_range(...)` 调用 | ✅ |
| `search_kernel.py:58-63,101-123` | `mode`/`use_rrf = mode in ("both","full")`/分支 | ✅ |
| `retrieval_fusion.py:47-52,68-94,145-161` | `DEFAULT_CHANNEL_WEIGHTS` 含 `"graph": 0.5`（:51）；RRF 68-94；`graph_hits` 149/160-161 | ✅（`search_kernel` 确无传参） |
| `kb.py:4583-4584,4705-4732,4749-4753` | 卡片/进度常量；`cid = card.get("card_id")`；`"kp_id": card.get("kp_id")`；progress.json 的 `data["cards"][card_id]` | ✅（progress 确按 card_id） |
| `collector.py:44-86`（:55-65） | node id = kp_id | ✅ |
| `edge_derivation.py:53-65,146-163,296-344,480-592` | `strictly_contains`/`sources_for_link_instance`/`derive_contain_edges`/`derive_link_edges` | ✅ |
| `history.py:582-591` | `_dedupe` 按 `(file, line, kp_id)` | ✅ |
| `document.py:285-298` + `atomic_yaml.py:15-40,46,65` | `_write_sidecar`→`save_sidecar_for_md`；`write_backup` 单代 `.bak`；`atomic_write_yaml`；`restore_from_backup` | ✅ |
| `backup.py:155,529,642-643` + `apply.py:619,670-677` | `snapshot_pre_images`、`restore_batch`、`except OSError` 返回 `restore_failed`+written；apply 的 pre-image 与 rollback | ✅ |
| `file_version.py:57-66` | `guard_save` 只在 UI 保存做 base_version | ✅ |
| `heading_proposals.py:171` | `def scan_headings` | ✅ |
| `docs/design/kg-agent-index-v0.md:82-93,110-112,135-137,183-186,220-226,283-284` | slice 字段 / 三判据 / 预算 / §6.3 切分 / M4 / U1-U2，**行号全部命中** | ✅ |
| `docs/design/kg-ontology-v0.md:20,137-143,171-177` | agent 不读边 / 节点字段 / 边能力前置 | ✅ |
| HEAD sha `1b3f6787…` | `git rev-parse HEAD` = `1b3f6787a47a670e1bd2e4d671291efaa271fe6b`（2026-10-27 15:00:40，即含上一轮复核入库的提交） | ✅ |
| 工作区 dirty `docs/example/AAA_Vocab/.memoria/**` | `git status` 确含这些修改（共 557 行 dirty） | ✅ |

⇒ **② 通过**：§13.2 不是"假装读过"，引用准确、语义匹配。

---

## 3. C1–C14 冲突对账（Lead 重点 3）——**部分通过（13/14 可追溯，C9 有编造）**

| # | 能否落到行号/事实 | 判定 |
|---|---|---|
| C1 设计 §3.2 字段 vs 现网 schema | 设计 `:82-93`；我逐字段核了现网 sidecar（仅 id/name/range.{start,end}.{snippet,line_hint}/tags） | ✅ 真实 |
| C2 草案 3000 tok vs R7.1 1200 字 | 设计 `:180-187`（§6.3 起 180；`③ 单元 >3,000 tok` 在 `:184`，落在材料引用范围内）；3,000/0.4247≈7,063 字算术对 | ✅ |
| C3 R2 用 69% 支撑切片 | PHASE4-RULINGS `:77` 原文「教材 KP 下 >1200 字占 69.0%…确实过粗，需要切片」 | ✅ |
| C4 非标题起点无同级标题 | `heading_proposals.py:171` 只产出 heading；定义层面成立 | ✅ |
| C5 `_read_kp` 回显 kp_id 且不检查 range_ok | `kb.py:364` / `:349` | ✅ |
| C6 R3 ④ graph 权重未标 | `retrieval_fusion.py:51` 有 `"graph": 0.5`；`search_kernel` 不传 `graph_hits` | ✅ |
| C7 C 回滚=删字段 vs 落位未定 | 材料自述未裁（无外部行号，属"未决"，不是可核事实） | ✅（自述） |
| C8 设计 §8.1 M4 要覆盖率门禁 vs 无字段 | 设计 `:222`；sidecar 无 `anchor_verified`/`section_number` | ✅ |
| C9 基线数字 358/98.9/8 vs 实测 357/98.6/5 | **材料解释为「快照差（草案来自更早快照）」——无证据，且设计草案 `:24` 明确写「358 KP，**14:09:46 快照**」、`:41` 同节写 8 坏/98.9%** | ❌ **编造风险**：应与"无法归因"并列（草案自身 358/357 不一致），不能声称"更早快照"而不给证据 |
| C10 A1 只改 hint 不够 | `resolve_range` 的 `end_snippet_not_found` 分支（`locator.py:95-102`） | ✅ |
| C11 字段/门禁语义 | 与 C1/C2 同源；材料自述改写 R2 契约 | ✅ |
| C12 ontology 禁用长度判据 | `kg-ontology-v0.md:156` | ✅ |
| C13 检索集成成本/R3 | R3 见 `PHASE4-RULINGS.md:88-98`；`search_kernel` 无结构通道 | ✅ |
| C14 证据三元组 | §1 已补 HEAD/manifest/taken_at，三项实测真实 | ✅ |

**没有发现其他编造**；C9 是唯一"用未验证因果解释差异"的条目，必须改为「未归因/需查草案基线来源」。

---

## 4. 更正表（§13.5/13.5b）数字复核——发现 3 处新错误

我用自己独立数字 + `q1-revision.json` 对照：

| 更正项 | 材料 v2 | 我的复核 | 判定 |
|---|---|---|---|
| §13.5-1 五口径 | literal-hint 530.5 / start→end.hint 536 / raw-resolved 526 / clamped 484 / heading 581 | **数值本身可复跑**；但 `literal_hint` 的 n=**354**、`raw_resolved` 的 n=**352**，其余 357 —— **五口径不是同一人群**，材料未标 n（我上一轮反复要求"同人群"） | ⚠️ 需标 n |
| §13.5-2 A2 会变 | 「≥97.8%：产品 349/357；本脚本 357/357（336+16+5）」 | 产品口径 349/357 与我一致；但**"357/357=100%"是脚本引擎产物**（其 raw end 与 boundary 永不相等），不能当产品事实引用；应只保留"≥97.8%" | ⚠️ 两值并置易被误引 |
| §13.5-3 总字数 | +16.3%（478,069→555,798） | 与 json 一致；我独立 raw→heading 为 +16.0%（引擎差） | ✅ |
| §13.5-4 read_kp token | 「约 714–722；1,700×0.4247=722；复核员 1,686→714」 | 1,700×0.4247=721.99 ✅；但 **1,686×0.4247=716**（不是 714；714 是我上一轮用 0.4237 的数） | ⚠️ 小错 |
| §13.5-5 病态放大 | 「只有 2 条 1.5–1.6 万；**其余 6 条**为 9,511/1,427/341/219（另有 2 条原本 1.2–1.8 万）」 | `pathological_repaired_textbook` 共 **6** 条：16,056 / 15,387 / 9,511 / 1,427 / 341 / 219 ⇒ 除 2 条外应是「**其余 4 条**」，不是 6 条；"另有 2 条"来自 `pathological_all`（原本就大，非本句"其余"） | ❌ 计数错 |
| §13.5-6 图谱边 | A1 62→56、A2 62→53 | 与我独立复算一致（我上一轮数据），产品基线 357 nodes/62 edges 一致 | ✅ |
| §13.5-8 比特率 context | 3 次、前文 40 字互异 | 与 json/我的复算一致 | ✅ |
| §13.5-9 跨库 22 cards | 收回、不作损失量 | §13.5 已收回；但 **§9 `:318` 仍写「在 5 库 22 cards / 9 progress 上是真实损失」** | ❌ 正文残留 |
| §13.5b 声称「复核员 13 项已逐条吸收」 | 表 12 行 | 13 项实质覆盖（部分行承运 2 项），但未逐项编号；C1 的「已加解释」不成立（见 C9） | ⚠️ 表述偏松 |

---

## 5. 「结论不变但依据换源」验真（Lead 重点 4）——部分通过

### 5.1 真的换了的部分（✅）

- **A1**：原「20.7% end 坏」（语料）→ 现「`range_ok` 已产出但 `_read_kp` 不检查（`kb.py:349`）」（**代码事实**）。换源成立。
- **B 否决**：现依据 = 4 类消费者（卡/图/会话/链接）+ 无 txid/原子回滚/写锁（代码事实）+ `card_id` 幂等（`kb.py:4749-4753`）。换源成立。
- **A2 否决**：现首要依据 = 非标题起点无「同级标题」（定义/代码语义），长度只作成本。换源成立（措辞也由"永久否决"降为"本轮证据下否决"，§8.2 尾）。
- 我上一轮/追加指出的 A1「整批 txid」、B「原子回滚/写锁」、`read_kp` 二传、缺 HEAD sha——**v2 都已按代码事实改正**（§4.D/§13.5-7/§13.6-C10/C14）。

### 5.2 没真正换的部分（❌/⚠️）

1. **C 的「粒度方向三源支撑」是标签换了、证据没换对**：
   - §8.1-3 写「粒度方向有三源支撑（v2 换源）…E08 + E09 + LlamaIndex」；
   - E08 的自变量是**检索 chunk 数**（见 §1），不是索引单元大小；E09 只证明「语义切分不必要」；LlamaIndex 的 SentenceWindow 是「句子匹配 / 窗口阅读」的**类比**，且 C 的切片是「小单元阅读」（比现 KP 更短，见 §4.C「agent 看到更细的切片」），与「大单元阅读」的类比方向相反。
   - 材料自己的 §13.3-#2 也承认「代码侧只到结构可用，切片未实现」「具体预算数字无三源」；**§8.1-3 的"三源支撑"与 §13.3 自相矛盾**。
   ⇒ C 的设计方向仍应标「类比 + 经验判断」，不能称三源。
2. **正文未与 §13 合并，旧数/旧结论仍在**（同一文件两套数）：
   - §4.A1 `:126` 仍写「失败回滚：…**整批撤销一个 txid**」（§13.5-7 已判前提不成立）；`:129` 仍写「实测 3 条病态…否则 **6 条** KP 会变成巨块」（§13.5-5 已改 2 条）。
   - §4.A2 `:135/:137/:139` 仍是「**94.1%** 会变」「+**74%**」「**+20.4%**」「**726** → 约 1,265 tok」「**粒度问题更严重了**」——全部被 §13.5-2/3/4 更正。
   - §5.1 `:183` 仍是「94.1% range 变；教材中位 +74% 字」。
   - §6.1 `:218-219` 仍标「✅ 通过（推荐口径）」「✅ 通过」——§6.2 v2 注已说不能进包。
   - §7 `:249-258` 仍以表格 + 「判定/U1 的答案」形式给出 range_ok **100%**、section **99.7%**、并结论「**R1 不需要先做锚点重建大工程**」——而 §13.5b **S9 明说「99.7% 降为语料观测；是否重建锚点是工程/人的决策，本材料不代替」**。**两处直接冲突**。
   - §9 `:316`「6 条…1.6 万字」、`:317`「94% range 变更」、`:318`「5 库 22 cards / 9 progress 是真实损失」——全部是 §13.5-5/2/9 已更正/收回的内容。
   - §4.D `:172` 仍把「69% >1200 字」「726 tok」当"真实代价"论述（§13.4 说 69% 只能作迁移成本）。
   - 「本节优先」只是**文档补丁声明**；决策包只要引 §0/§4/§5/§7/§9 就会拿到被 §13 推翻的数字。这是本项目已被烧过的"同一文件两套口径"，**不能靠一句"以 §13 为准"消除**。
3. **§0 仍把「孤儿 0.0%」「anchor 99.7%」列为"支撑推荐的成本事实"**（虽有 v2 注说降级），而 §13.4 说它们"不用于设计论证"；表述不彻底。

---

## 6. 【经验判断】13 条中的"本可补证却没补"（Lead 重点 5）

| # | 主张 | 现状 | 可补的证据（本仓已有 / 可实测） | 判定 |
|---|---|---|---|---|
| 1 | 身份=kp_id、不新建第二套语义 id | 标「代码为主+开源类比 ⇒ **经验判断**」 | 按 Lead 的"至少两源（论文/代码/开源）"：本仓代码（4 类消费者）+ LlamaIndex `BaseNode.id_`/`NodeRelationship`（MIT）= **已经是 2 源** | **漏证（低估）**：可升为「代码+开源两源」 |
| 5 | anchor gate 三判据 | 标「无外部对照（产品特有）⇒ 经验判断」 | 本仓 Phase 1 外部研究 `PROPOSAL-external-research.md:74,93-98` 已给外部做法：**锚点 = id + 内容哈希 + 字符偏移（LlamaIndex `start_char_idx/end_char_idx`, E11），行号只作显示**，与 R1 的"范围可解析/hint 会漂"同向；材料 0 次引用 `start_char_idx`/`字符偏移` | **漏证**：至少可引 E11 + 本仓 R4 结论作【源】，不必停留在"无外部对照" |
| 12 | A1 修复后 R1 gate 可上线 | 标「工程约束（经验判断）」 | **我用产品 `resolve_range` 实测**：对 5 条 `end_snippet_not_found` 的 KP，按 A1 规则（end 夹到下一同级标题、**取边界前最后一个非空行**重建 `end.snippet`+`line_hint`）后 **5/5 变 `ok=True`**（例如 `数字通信的特点` 110→176 行，`ok=True`）；但若直接用边界空行做 snippet 会仍失败——说明该主张**可代码验证且必须写明"非空行"细节** | **漏证（可实测）**：可从"经验"升为【码】+ caveat |
| 10 | C 的收益 = 少往返 | 标「待验证假设（U3 A/B）」 | 这是正确的待验证项；若想给弱支撑，可用本仓 E 表 E05/E06（Self-RAG/Adaptive-RAG 的检索次数控制），但两者需训练，**只能当反例/对照**；材料不引反而更稳 | **不算漏证**（保持待验证是对的） |

> 结论：#1、#5、#12 三条本可再补一源/实测，v2 仍留作"经验判断"（#12 我直接给出了可复跑实测）。

---

## 7. 不能进决策包（v2 增量）

1. **C 的「粒度方向有三源支撑」**：E08 变量错配、E09 不支持 heading、LlamaIndex 是反向类比；与材料自己的 §13.3-#2 矛盾。C 只能按"类比 + 经验判断 + Q3/U3 A/B"进包。
2. **C9「快照差」归因**：无证据（设计草案写同一 14:09:46 快照），属编造因果，须改"未归因"。
3. **§13.5-5 病态计数**（其余 6 条 ≠ 4 条）、**§13.5-1 五口径不同 n（354/357/352/357/357）**、**§13.5-4 714 应由 716 替代**、**A2「357/357」是脚本引擎值不是产品事实**——更正表本身不能带这些错进包。
4. **正文旧数/旧结论**（§4.A1 `:126/:129`、§4.A2 `:135/:137/:139`、§5.1 `:183`、§6.1 `:218-219`、§7 `:249-258`、§9 `:316-318`、§4.D `:172`）：未与 §13 合并前，任何"引用 §0–§12"的决策包条目都不可靠。
5. **§7 的「R1 不需要重建」结论**与 §13.5b-S9 直接冲突；以 §13.5b 为准（不由材料替人决策），但正文必须删。

## 8. 可以进决策包（v2 通过项）

1. **§13.2 项目对齐**：20 处引用真实且语义匹配（Lead 要求 3 处，我核了 20 处）；HEAD sha/manifest/时间三元组补齐且实测为真。
2. **A1 / A2 / B 的代码依据**（read_kp 不检查 range_ok、`kp_index` 字段已产出、4 类消费者、无原子回滚/写锁、`card_id` 幂等）——本轮确实换成了代码事实。
3. **复核更正的数值**（凡与 `q1-revision.json` + 我的独立复算一致者）：A2 ≥97.8%（产品口径）、总字数 +16.3%/16.0%、read_kp ~714–722 tok（系数 0.4247）、比特率 context 可消歧、A1 只有 2 条 >1.5 万字、图谱 A1/A2 边 churn、`source_hash` 补入。
4. **新产物可复跑**：`q1_revision_probe.py` 2 次运行输出 sha256 均为 `4921c8dda8f3eb22…` = 作者 `q1-revision.json`（我另复制脚本、仅改路径常量，逻辑零改动）。
5. **论文/OSS 引用本身**：E08/E09 标题、URL、摘要方向正确；LlamaIndex=MIT / Aider=Apache-2.0 经 GitHub API 独立核实；LlamaIndex 在 `8797f52b` 确有 `sentence_window.py`。
6. **仍须带标签的项**：所有 `【语】` 观测只能按 §13.4 的"仅迁移成本/最坏输入"进包（与上一轮一致）。

## 9. 证据身份与复跑

| 证据 | sha256 前 16 |
|---|---|
| 复核对象 `round2/Q1-research.md` v2 | `fb49ba06b21e90ae` |
| 新增脚本 `round2/scripts/q1_revision_probe.py` | `bb8bf50a63ad464a` |
| 新增数据 `round2/data/q1-revision.json` | `4921c8dda8f3eb22` |
| 我的复跑副本 `round2/scripts-verify/repro/q1_revision_probe_repro.py` | `a9d1577efab983e0` |
| 我的复跑输出 `round2/scripts-verify/repro/q1-revision.json` | `4921c8dda8f3eb22`（与作者一致） |
| HEAD（实测） | `1b3f6787a47a670e1bd2e4d671291efaa271fe6b` |
| 本报告 | 以磁盘 sha256 为准（自引用不内嵌） |

```powershell
# 复跑（我的临时副本，仅把 HERE/DATA 改到 scripts-verify/repro，逻辑零改动）
python artifacts/agent/verify/debate/kg-retrieval/round2/scripts-verify/repro/q1_revision_probe_repro.py
# 2 次输出 sha256 均为 4921c8dda8f3eb22…，与 round2/data/q1-revision.json 完全一致
```

> 本轮只做 Q1 v2；v1 的 `Q1-verify.md` / `Q1-verify-addendum.md` 继续只对旧 sha 有效。未 commit、未修改研究员文件。
