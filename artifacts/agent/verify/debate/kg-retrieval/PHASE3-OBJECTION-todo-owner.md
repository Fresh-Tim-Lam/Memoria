# KGR 研讨会 Phase 3 交叉异议 — B（知识组织 / 学习视角）

> 提案方：`todo-owner`（B）｜2026-10-27｜Phase 3（独立性已解除）
> **读入集**：`PHASE2-MERGE.md` 全文；`PROPOSAL-corpus-analysis.md`、`PROPOSAL-agent-arch.md`（C）、`PROPOSAL-todo-owner.md`（自）、`ACCOUNT`/`BASELINE-190` 摘要；代码 `retrieval_fusion.py`、`tools/kb.py`、`kg-ontology-v0.md`、`collector.py`。
> **证据身份（E1）**：`ev:file:<repo-rel>#L<n>`｜`ev:bench:kg-retrieval-b-1`（脚本 `b_measure*.py`，产物 `b-measure.json` sha256 `973E6415…` / `b-measure-kp.json` `2A5676F6…`）。
> **纪律**：每条带「撤回条件」（falsifier）；**含 2 条自打（O-B3、O-B7）**。

---

## 1. 结论摘要（先给裁决建议）

1. **「索引单元不用 KP」这个结论目前证据不足**：语料的 93.3% 证据只证明 **KP 起点=标题**，不证明 **标题边界=坏边界**；真正坏的是 **end 边界**（2.4 一条吞 17,344 字）与 OCR/重名（C9 已是共识）。建议改成「**修边界 + 保 KP 身份 + 切片只作返回视图**」。
2. **更严重的问题：双方对"KP 尺寸"的测量口径不一致**（我用 `end.line_hint` 得 p50 **526 字**；语料得 p50 **1,822 字**，p90 9,421，差 3.5×）——而锚点恰恰是已知 37% 歧义的对象。**我自己的数据也建立在这个未修锚点上**（自打 O-B3）。在统一口径前，"KP 太大/太碎"都不该当裁决依据。
3. **C 的「索引=RRF 第 3 通道」只能解决"相关"，解决不了"顺序"与"跨章节综合"**：RRF 是 rank 融合（`retrieval_fusion.py#L7,L68-L95`），而学习顺序需要前置关系——本体已裁边不服务 agent、35 会话 0 次 edge_type（`kg-ontology-v0.md#L13,L27-L28`）；7/15 问题需跨 ≥2 KP（`PROPOSAL-corpus-analysis.md#L187`）而 top-k 并列候选不是综合路径。
4. **我的双字段 description（scope+note）也要打**：单字段现状已 0/357 落盘（`PHASE2-MERGE.md#L186`），加第二个字段更可能降低落盘率；且 C4 已实测**单字段问句型**就能把 hit@3 做到 76.9%（`PHASE2-MERGE.md#L45`）。建议 v1 只做一个字段（O-B7）。
5. 建议 Phase 4 的裁决顺序：**先统一测量口径（O-B3）→ 再定单元（O-B1/O-B2）→ 再定通道（O-B4/O-B5/O-B6）**；否则在 3.5× 的口径差上裁"KP 是否可用"，等于用未修锚点裁决锚点问题。

---

## 2. 异议表

| 编号 | 攻击对象 | 反驳 | 证据 | 建议改成什么 | 什么证据能让我撤回 |
| --- | --- | --- | --- | --- | --- |
| **O-B1** | 语料：「KP 是标题切分 ⇒ 不是学习单元 ⇒ 索引单元不用 KP」（C3；`PROPOSAL-corpus-analysis.md#L57-L61,L281`） | ① **从起点推断单元性质是无效推理**：93.3% 起点=标题行，恰恰说明**用户按标题组织内容**；标题是语义边界不是缺陷。② 真正的问题是 **end 边界**：同文件 `2.4 希尔伯特变换及应用` 一条吞 **17,344 字**、`非均匀量化` 13,057 字——这是"终点取错"，不是"起点在标题"。③ 语料自己的 K2 指出**编辑后 section 数不变**（标题结构稳定，`PHASE2-MERGE.md#L121`）⇒ 标题反而比块更稳定。④ 5.0% 非知识点/28.6% 重名/11.2% OCR 脏都是**质量缺陷**（C9 已列为共识），不是"标题切分"的必然结果。 | `ev:file:artifacts/agent/verify/debate/kg-retrieval/PROPOSAL-corpus-analysis.md#L57-L61`（93.3% 与 17,344 字并置）、`#L271`（层级须按编号还原）、`#L122-L124`（非知识点 5.0% 分类）；`PHASE2-MERGE.md#L121`（section 数稳定）、`#L39-L43`（C3 表述）；`ev:bench:kg-retrieval-b-1`（我的 span 分布）。 | 命题改为「**修 KP 的 end 边界**（end = 下一同级标题或预算上限；清洗 OCR/重名）+ **KP 保留为语义身份**；索引单元 = 该 KP 在预算内的**切片视图**」。不推翻 KP，先修边界。 | 若对 357 条按"下一同级标题"重算 end 后，仍有 **>30% 的 KP span >1,200 字**（说明标题级本身粒度粗）⇒ 我承认必须换单元，撤回"标题边界可用"。 |
| **O-B2** | 语料：「不要复用现有 357 条当索引，必须重建」（`PROPOSAL-corpus-analysis.md#L281`） | 其证据实际证明的是**覆盖不足**（只覆盖 4/14 章、61.8% token 无 KP、`PHASE2-MERGE.md#L149,L188-L190`），不是"单元选错"。把覆盖问题当单元问题 ⇒ 需要迁移 **357 个 kp_id**，而 kp_id 是 FSRS 复习、link、图谱节点、review 的共同锚（`collector.py#L55-L65`；`kg-ontology-v0.md#L140` node 字段含 kp_id）。重建索引 = 制造两套对象，成本远高于"补覆盖 + 修边界"。 | `ev:file:PHASE2-MERGE.md#L149,L188-L190`（覆盖缺口）；`PROPOSAL-corpus-analysis.md#L281`；`ev:file:src/memoria/graph/collector.py#L55-L65`（图节点 id=kp_id）；`ev:file:docs/design/kg-ontology-v0.md#L140`（node 字段 kp_id）。 | 拆两件事：① **覆盖** = 按章/节生成"派生切片"（确定性、可自动，**不新建 id**，切片带 `kp_ids[]`）；② **语义** = 保留 KP id 并建 `KP→切片` 映射（93.3% 起点=标题 ⇒ 映射成本低）。索引条目 = 切片；**不允许**两套对象各自维护。 | 若 `KP→切片` 映射产生 **>20% 无归属 KP**，或 FSRS/link 迁移成本实测高于"映射方案"，我撤回"保留 KP 身份"。 |
| **O-B3** ★**自打** | 我（B §2.1）与语料（§2.1）对**KP 尺寸的测量口径** | 我算 p50 **526 字**、p90 2,918、>3,000 字 9.3%；语料算 p50 **1,822 字**、p90 **9,421**（`PROPOSAL-corpus-analysis.md#L18,L53`）——**差 3.5×**。差异来自我直接用 `range.end.line_hint` 当结束行（而 end 锚点本身 37% 歧义、18.8% 静默锚错、还有 range 反转，`PHASE2-MERGE.md#L29,L188`）。**我先要求别人修锚点，却拿未修锚点的数据论证"KP 太大"——同一种毛病。** | `ev:bench:kg-retrieval-b-1`（`b_measure2.py` 用 `range.end.line_hint`；max=18,198 与语料 max 18,198 一致但 p50 差 3.5×）；`ev:file:PHASE2-MERGE.md#L29,L188`（锚点缺陷）；`PROPOSAL-corpus-analysis.md#L18,L53`。 | **先统一口径再裁**：定义 `kp_end = end.line_hint（若 ≥ start 且 < 下一同级标题）else 下一同级标题`；两方用同一脚本重算并冻结快照（sha256）；R8 预注册该口径。"KP 粒度不可用"降级为"待重算"。 | 重算后 **p50<800 且 >3,000 字占比<10%** ⇒ 我撤回"KP 粒度不可用"的核心论据，单元之争降级为"覆盖+边界修复"（O-B1/O-B2 成立）。 |
| **O-B4** | C：「索引作为现有 RRF 的第 3 条通道」（`PROPOSAL-agent-arch.md#L15`） | ① RRF 只用 **rank** 融合（`RRF_K=60`、`reciprocal_rank_fusion`），数学上不携带"前置/顺序"信息（`retrieval_fusion.py#L7,L68-L95`）。② 学习需要的"先学什么"= 前置关系；当前本体明确边不服务 agent、edge_type 三选一且 35 会话 0 次（`kg-ontology-v0.md#L13,L20,L27-L28`）⇒ **第三通道没有可用的顺序数据**，只能表达"相关度"。③ C 自己的 KPI 是 iterations/answer，但"排序更好"≠"探索更少"——除非索引输出直接给出**计划**。 | `ev:file:src/memoria/services/retrieval_fusion.py#L7,L68-L95,L145-L161`（graph 仅占位/权重 0.5）；`ev:file:docs/design/kg-ontology-v0.md#L13,L20,L27-L28`；`PROPOSAL-agent-arch.md#L15,L112`；`PHASE2-MERGE.md#L63-L66`。 | 第 3 通道只承诺「**相关候选**」，不宣称"学习顺序"；顺序由**确定性结构序**（`section_number`/章序）兜底；若未来有前置关系，必须来自**人确认字段**并单列 A/B，不进 v0。 | 若 A/B 显示"加第 3 通道后 iterations/answer 显著下降（≥1 轮）且无需任何顺序信息" ⇒ 我撤回"顺序缺口"这条（说明这批问题不需要顺序）。 |
| **O-B5** | C：跨章节综合靠 3rd 通道 + L0/L1 routing（`PROPOSAL-agent-arch.md#L61-L77,L119`） | 语料实测 **7/15（46.7%）问题需跨 ≥2 KP 综合**（`PROPOSAL-corpus-analysis.md#L187`）；RRF 输出是 **k 个并列候选**，不是"覆盖全部子问题的集合"；C 的改动主体是"露 kp_id + read_kp 切片窗"，**没有 query 分解/覆盖目标** ⇒ 跨章节问题仍会落回 read_document 探索（实测 37 次 read_document、36 次同章、集中在探索轮，`PROPOSAL-agent-arch.md#L119`）。 | `ev:file:artifacts/agent/verify/debate/kg-retrieval/PROPOSAL-corpus-analysis.md#L187`；`PROPOSAL-agent-arch.md#L61-L77,L119`；`PHASE2-MERGE.md#L37,L42`；`ev:bench:kg-retrieval-b-1`（KP 跨文件分布）。 | 索引条目加 **coverage 标签**（回答哪些子问题/对象/对比项）；检索输出 **slice 集**（覆盖全部子问题的最小集）+ 显式 `plan` 步（子问题→切片）；验收单列"跨章节综合"子集（≥10 题，`PROPOSAL-metrics-baseline.md#L80` T2 已定义）。 | 若真实跨章节问题在"仅 RRF 第 3 通道"下 A/B 已达标（iterations 不高于方案组、答对率不降）⇒ 我撤回"需要 coverage/plan"。 |
| **O-B6** | C：「read_kp 加 offset/limit 即可解决粒度」（`PROPOSAL-agent-arch.md#L77`） | 粒度问题**不只是长度**：C 自己实测 kp_id 对模型不可见是主因（`#L44-L49`：id 从不出现在模型可读文本）；且 read_kp 单次均 **1,431 tok**（`#L54`）远低于工具放大后的成本，真正放大器是 **grep 34,249 字符**（`PHASE2-MERGE.md#L60`）。在"end 边界未修"（O-B3）的情况下加 offset/limit，等于**在坏边界上切窗**；先露 id + 工具预算（grep 250 命中封顶）收益更确定。 | `ev:file:PROPOSAL-agent-arch.md#L44-L54,L77`；`PHASE2-MERGE.md#L59-L60`；`ev:file:src/memoria/services/agent/tools/kb.py#L344-L369`（read_kp 整段）。 | 顺序：① 露 `kp_id`（两行改动，`kb.py` 的 `read_document` 清单行/search_kb 命中行）→ ② 工具结果预算（grep 封顶）→ ③ 再评估 offset/limit；KPI 用 iterations/answer（C 自己的 KPI）。 | 若露 id 后 read_kp 采用率仍 <10%，且剩余差异由粒度解释（对照 A/B）⇒ 我承认 offset/limit 是必要主修，撤回"先别加"。 |
| **O-B7** ★**自打** | 我自己（B §3.2）的 `scope`+`note` 双字段 | ① 双字段**增加作者负担**：单字段现状已 **0/357** 落盘（`PHASE2-MERGE.md#L186`），没有证据表明拆两字段会提高落盘率，反而更可能更低。② C4 实测**单字段问句型** hit@3 已达 **76.9%**（`PHASE2-MERGE.md#L45`）⇒ 机器可判性不必靠第二个字段。③ 我说 `note` 能"维持人的动机"（`PROPOSAL-todo-owner.md#L83`）——**这正是我自己的未测项**（同文件 `#L195`：description 的 ROI 未测）⇒ 我犯了"用一个未验证动机论证字段设计"的错。 | `ev:file:PHASE2-MERGE.md#L45,L186`；`ev:file:artifacts/agent/verify/debate/kg-retrieval/PROPOSAL-todo-owner.md#L83,L195`（未测项自认）。 | v1 只做**一个** `description` 字段：问句型 1–2 句（含"何时不该读"+判别词），复用现有 KP description 字段（`document.py#L1875`）；`note` 不落 schema，易错点从 review/错题**派生展示**（非事实源）。落盘率 <70% 时**不得**把索引收益计入验收。 | 若双字段 A/B 的落盘率 **≥单字段**（人更愿意写 note），且 note 可见性显著提升维护量 ⇒ 我撤回并恢复双字段。 |

---

## 3. 被攻击后我改了哪些自方主张（自打落点）

1. **KP 尺寸证据（O-B3）**：承认我用了未修锚点算 span；在统一口径前，我不再用 526/9.3% 支撑"KP 太碎/太大"。改为：先修 end 边界并重算（预注册脚本+快照）。
2. **双字段 description（O-B7）**：撤回 v1 双字段，改为单字段问句型；`scope/note` 只保留为**内容要素**（问句里内含"何时不该读"），不作为两个 schema 字段。等 A/B 证明 `note` 的维护价值再拆。
3. **单元主张的表述（O-B1）**：把"KP 不是学习单元"降级为"**KP 的 end 边界当前不可靠**"；保留 KP 身份，切片只是视图（需带 `kp_ids[]` 映射，O-B2）。
4. **未变的主张**：索引分层预算（C5 已并入）、先接现有检索栈（C2）、R8 指标（答对率不得降）。

## 4. 新增/更新的 unknowns（M3）

- **U-6（O-B3）**：KP 边界口径未统一 ⇒ 任何"KP 尺寸"结论都不可裁决；需两方同一脚本重算（我认领，语料方复核）。
- **U-7（O-B2）**：`KP→切片` 映射的孤儿率未测；映射质量决定"保留 KP"是否可行。
- **U-8（O-B5）**：跨章节问题的"最小覆盖切片集"能否被现有工具表达/评测，未验证。
- **U-9（O-B7）**：单字段问句型的**人工落盘率**（写完 357 条需要多少分钟）未测；这是 description 方案成败的关键，比 hit@3 更早暴露。

## 5. falsifiers（汇总，供 Phase 4 直接引用）

```
O-B1 若重算后 >30% KP 仍 >1,200 字        ⇒ 我撤回"标题边界可用"
O-B2 若 KP→切片孤儿 >20% 或迁移成本更高    ⇒ 我撤回"保留 KP 身份"
O-B3 若重算 p50<800 且超 3,000 字 <10%     ⇒ 我撤回"KP 粒度不可用"论据
O-B4 若 3rd 通道使 iterations 降 ≥1 且无需顺序 ⇒ 我撤回"顺序缺口"
O-B5 若仅 RRF 3rd 已达标跨章节 A/B        ⇒ 我撤回"需要 coverage/plan"
O-B6 若露 id 后 read_kp 采用率仍 <10%      ⇒ 我撤回"先别加 offset/limit"
O-B7 若双字段落盘率 ≥ 单字段              ⇒ 我撤回"v1 单字段"
```

## 6. 复跑

```powershell
# 我的 KP 尺寸证据（O-B3 的争议源）
python artifacts/agent/verify/debate/kg-retrieval/b_measure2.py   # p50 526 的来源（end.line_hint 口径）
# 产物 sha256：b-measure.json 973E6415… / b-measure-kp.json 2A5676F6…
```
