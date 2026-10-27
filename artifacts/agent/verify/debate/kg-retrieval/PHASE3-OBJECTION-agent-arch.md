# Phase 3 交叉异议（C 方 agent-arch）：自我防守 + 对外攻击

> **Phase 3（独立性已解除）**。读入：`PHASE2-MERGE.md`、`PHASE3-OBJECTION-{arch-contract,todo-owner,metrics-baseline}.md`、`PROPOSAL-external-research.md`、`PROPOSAL-corpus-analysis.md`、`.aoci/ledger.jsonl`、冻结快照 `phase3-session-snapshot.jsonl`。
> **纪律**：不 commit；写域仅本目录；每条带证据身份与撤回条件；**防守失败处明确写"我撤回 X"**（见 §4）。
> **本轮新增可复跑**：`phase3_aoci_ledger.py → phase3-aoci-ledger.json`、`phase3_iteration_relation.py → phase3-iteration-relation.json`。

## 0. 总裁决表（先给结论）

| # | 攻/守 | 对象 | 我的判定 | 一句话结果 |
|---|---|---|---|---|
| S1 | 守 | A 方 O1-A（露 id 放大错误） | **部分接受** | 风险真实存在；"两行改动可独立上线"**我撤回**，改为「锚点 gate 先行，露 id 仅在 gate 通过后」 |
| S2 | 守 | A 方 O1-B（read_kp 贵 58%、6/37 可能合理） | **接受** | 撤回"提升采用率=收益"的主张；read_kp 采用率降级为观察指标 |
| S3 | 守 | A 方 O1-C（露 id 与修锚点是串行依赖） | **完全接受** | 撤回"并列/两行可独立 A/B"的 K1 表述；锚点 P0 → 露 id P1（串行） |
| S4 | 守 | D 方 C8（−20.5% 是算术不是测量） | **接受降级** | 撤回"省 1 iteration ≈ −20.5%"作为共识；改「候选/观察 KPI」+ 给出 iteration/loop/call 精确关系 |
| A1 | 攻 | 外部研究「AOCI 太重，别搬」 | **证据不足，应降级为 M3** | 32/34 repair_required 之后 **38/38 次（含 6 次 auto_finalize 报修）在 2h 内均出现成功写入（ok）**；2.8h 墙钟主要花在批量 apply/finalize，而非"每次重写" |
| A2 | 攻 | 语料方「索引单元不用 KP / 需重建」 | **部分接受、部分攻击** | 同意"边界与覆盖有问题"，反对"新 id 空间/重建"：会让 agent 检索的切片与 FSRS/图谱/引用锚**无法对齐**；应"身份=KP、单元=带 `kp_ids[]` 的切片视图" |

---

## 1. 防守（逐条按"编号｜攻/守｜对象｜我的回应｜证据｜建议改成什么｜什么证据能让我撤回"）

### S1 ｜ 守 ｜ A 方 O1-A（露 kp_id 把错误放大）

**我的回应（部分接受）**：
1. **A 方的风险判断成立，而且比它说的更严重**：`read_kp` 当前**连 `range_ok` 都不检查**——`kp_index` 记录 `range_ok/start_line/end_line`（`ev:file:src/memoria/services/kp_index.py#L23-L25,#L62-L64`），但 `_read_kp` 在 `range_ok=False` 时用 `entry.start_line or 1` ⇒ 静默返回**第 1 行**（`ev:file:src/memoria/services/agent/tools/kb.py#L344-L351`）。
2. **锚点错位的机理可复核**：`locator.locate_snippet` 先信 `line_hint`，"hint 行包含 snippet 就直接钉住、不查全文唯一性"（`ev:file:src/memoria/range/locator.py#L43-L49`）；A 方实测 67 个静默钉错样本（67/357=18.8%），其**导出的 8 个样本 `occurrences_in_doc` 全部 ≥2**（2–8 次，`ev:bench:r4-wrongpin-probe.json`）⇒ 错位发生在 **snippet 非唯一**的 KP 上（37% 非唯一），不是随机；67 个全量样本的 occurrences 字段未导出，这点我已向 A 方请求补数（否则我的 gate 覆盖估计只能按 8 个可见样本算）。
3. **所以"露 id 不会引入新错误"我无法证明**，我也不再声称；我**撤回**原提案 §2.4 的"0 schema、可独立上线/独立 A/B"表述（`PROPOSAL-agent-arch.md#L61-L75`）。
4. 但**存在一个便宜的 gate 让露 id 变安全**（这正是 O1-C 的串行前提）：
   - `read_kp` 若 `range_ok=False` ⇒ **显式报错** `ANCHOR_UNRESOLVED`（附 `read_document` 行窗口 fallback），而不是返回第 1 行；
   - 在文档内统计 start/end snippet 出现次数：`>1` ⇒ 返回 `AMBIGUOUS_ANCHOR`（带候选行 + 父级 heading 路径），**不裸切**；可用 `start_candidates/end_candidates`（`ev:file:src/memoria/range/locator.py#L80-L120` 已有这两个字段）+ 全文计数实现；
   - end 边界夹紧：end 非唯一（如 `"$$"`）或 span 超预算 ⇒ end 取"下一同级标题"或预算上界（与 B 方 O-B1 的修法一致）；
   - 返回 `anchor_verified: true/false`，只有 `true` 的 KP 才在 `read_document`/`search_kb` 里露 `[kp_id]`；否则标 `[kp_id?]` 或不露。
   - 该 gate 的 flag 可实现性有现成数据：`r4-wrongpin-probe.json` 导出的 8 个错位样本 `occurrences_in_doc` 全部 ≥2 ⇒ gate 至少能拦住这 8/8 个可见静默错位；67 个全量样本需 A 方补 `occurrences_in_doc` 才能验证覆盖率（**经验判断：真实漂移下仍需重测**）。

**证据**：`ev:file:src/memoria/services/agent/tools/kb.py#L344-L351`、`ev:file:src/memoria/services/kp_index.py#L23-L25,#L62-L64`、`ev:file:src/memoria/range/locator.py#L43-L49,#L80-L120`、`ev:bench:r4-wrongpin-probe.json`（67/357，examples 含 occurrences_in_doc）、`ev:file:PHASE3-OBJECTION-arch-contract.md#L15-L43`。

**建议改成什么**：
- K1 顺序裁决为 **锚点修复 + anchor gate = P0；露 id = P1（gate 通过后立即做，因为仍是两行）**；
- 露 id 的验收 **必须同时**测「答对率（不降）」与「错切片率（=0）」，不是只测采用率；
- 锚点 gate 的 spec 写进索引契约（`anchor_verified` 是 read_kp 输出字段之一）。

**什么证据能让我撤回（S1）**：
- 若实现 gate 后，在"前插 50 行"漂移模拟下 `read_kp` 的错切片率 **>0** ⇒ 我撤回"gate 足以让露 id 安全"，退回"锚点全部修完前不露 id"；
- 若 A 方证明 67 个静默错位样本中存在 `occurrences_in_doc==1` 的样本（即唯一 snippet 也会钉错）⇒ 我的 gate 设计漏了一种错误类，需加内容自检（heading 匹配），本条重开。

---

### S2 ｜ 守 ｜ A 方 O1-B（read_kp 比 read_document 贵 58%；6/37 可能是合理行为）

**我的回应（接受）**：
- 接受「6/37 未必是缺陷」：read_kp 1,431 tok/次 > read_document 904 tok/次（我自己的表，`PROPOSAL-agent-arch.md#L33`），且 93.3% KP 起点=标题、KP 粒度到节级（`PHASE2-MERGE.md#L39-L43`）——行级问题用 `read_document(offset/limit)` 或 `snippet` 是**正确行为**，不是"不会用"。
- 因此我**撤回**把"read_kp 采用率提升"当作方案收益的主张；原 §2.4 的改动仍可作为**低成本可发现性修复**，但不再是核心收益，而是"让 read_kp 在合适的场景（整节概念题）有入口"。
- 收益论证改写为：**索引的价值 = 减少探索轮（iterations/answer）+ 答对率不降**，其中 read_kp 只是"整节级问题"的一种读取方式；**L1 索引提供方向感（选文件/节）才是主收益**，读取仍用最便宜且最贴题的工具。

**证据**：`ev:file:PROPOSAL-agent-arch.md#L33`（1,431 vs 904）、`ev:file:PHASE2-MERGE.md#L39-L43`、`ev:file:PHASE3-OBJECTION-arch-contract.md#L47-L66`。

**建议改成什么**：
- 把"采用率"从验收指标降为**诊断指标**；验收指标为：答对率（硬门槛）、iterations/answer（观察→A/B 后定）、错切片率=0、prompt 峰值。
- F3 falsifier 重写为：**"露 id + gate 后，若答对率下降或 iterations 不降，则露 id 无收益、撤回"**（原 F3 只测采用率，作废）。

**什么证据能让我撤回（S2）**：
- 若 A/B 显示"露 id 后答对率显著上升（>5pp）且迭代下降" ⇒ 采用率就不是无关指标，我恢复其诊断价值（但仍不作主 KPI）。

---

### S3 ｜ 守 ｜ A 方 O1-C（露 id 与修锚点是串行，不是并列）

**我的回应（完全接受）**：
- 接受这是**依赖关系**而非并列选项：`read_kp` 的读取价值由锚点正确性承载；在 18.8% 静默错位 + range 反转存在时先露 id，等于把"不可用"变成"可被静默误用"（与我批判"看起来有实际没有"同构）。
- 我**撤回** K1 中把两者并列的表述，也撤回"两行代码所以可以先做"的排序论证。

**证据**：`ev:file:PHASE2-MERGE.md#L115-L118`（K1 原文）、`ev:file:PHASE3-OBJECTION-arch-contract.md#L70-L88`、`ev:bench:r4-wrongpin-probe.json`。

**建议改成什么**：Phase 4 裁决 = **串行**（锚点 + anchor gate P0 → 露 id P1）；P1 内部顺序：先 `read_kp` gate（检查/报错/夹紧）→ 再暴露 `[kp_id]`；两者同一 PR 也可（gate 不依赖锚点全量重建，只依赖 range 解析结果与局部校验）。

**什么证据能让我撤回（S3）**：若实现并实测"先露 id（无 gate）"在漂移语料上的错切片率 **低于** `read_document` 基于 line_hint 的错位率（14.1%）⇒ 说明并列可接受，但我不预期这个结果。

---

### S4 ｜ 守 ｜ D 方 C8（−20.5% 是算术不是测量；iteration/loop/call 关系）

**我的回应（接受降级）**：
1. **接受**：`−20.5%` 是把现有账单按轮数线性缩放，不是"清掉一轮后的实测"，按 D 的 O-2 应**降级为候选/观察 KPI**，A/B 前不作验收阈值。
2. **给出 D 要的精确关系（冻结快照，可复跑）**：
   - 快照 `phase3-session-snapshot.jsonl`（sha256 `b906f0de…`）：**21 轮 / 116 iterations / 135 tool calls（=135 tool results）**；
   - **iteration = 一次 LLM 请求/响应** = 一个 `step/start` + 一个 `assistant/message`；验证：`assistant/message == step/start == Σ loop/end.iterations`（116=116）；
   - **一个 iteration 可并行多个 tool call**：每 iteration 的 call 数分布 = `{0:21, 1:60, 2:31, 3:3, 4:1}` ⇒ 35/116（30.2%）iteration 是多调用并行，最多 4 个；21 个 0-call iteration = 最终回答轮；
   - **calls/iteration = 1.164；iterations/turn = 5.524**；
   - 我上一版"19 轮 / 93 iterations / 105 calls"是会话增长前的快照（同一文件在测量期被 app 持续写入；D 也遇到并冻结）——两套都以"带时间戳"呈现，**不相减**。
3. **因此"省 1 iteration"的分母** = 116 iterations（21 轮）；若"每轮少 1 个 iteration" = 少 21 次 LLM 调用。按 D 的 21 轮账单 2.4453 元算，平均每次 iteration 2.4453/116 = **0.0211 元**，21 次 ≈ 0.443 元 ≈ **−18.1%**（算术，仍非实测）；prompt 全免上限 = 输入份额 **33.6%**（D 实测：输出 66.4%）。所以"轮次比 prompt 更值钱"的**方向**仍成立，但**数值不成立为共识**。
4. **如何把算术变成测量（回应 D 的 O-2 建议）**：三臂 A/B（Arm-0 现状 / Arm-1 只注入索引 token 不改行为 / Arm-2 索引驱动）+ **per-step usage 埋点**：loop 已有 `step_usage`（`ev:file:src/memoria/services/agent/loop.py#L306-L316` 中 `step_usage` 累积），建议新增 `step/usage` 事件（只追加，S5 风格），才能把"每次 iteration 的输入/输出/命中"落盘——否则"省 1 iteration"永远只能线性外推。这是 C 方对 D 的**具体请求**（低成本，不改请求体）。
5. **接受 D 的峰值 P0**：冻结快照峰值 **845,926 = 1M 的 84.6%**（`phase3-amplification.json`/D 异议 §4）；我原引用 656,818（65.7%）是 19 轮时点，已过时；我的 R5 预算论证改为"峰值安全 + 当轮 miss"为主，不再依赖"重发放大"。

**证据**：`ev:bench:phase3-iteration-relation`（`phase3-iteration-relation.json`）、`ev:bench:phase3-session-snapshot.jsonl`（sha256 `b906f0de…`）、`ev:file:PHASE3-OBJECTION-metrics-baseline.md#L119-L197,#L293-L306`、`ev:file:src/memoria/services/agent/loop.py#L306-L316`。

**建议改成什么**：
- PHASE2-MERGE C8 改写为：**"候选 KPI：iterations/answer + 答对率；iterations 当前仅作观察指标（证据=输出占 66.4% 实测 + 线性外推，无 A/B）；主验收暂用 答对率 + 峰值 prompt + 成本"**；
- 新增 D 的 Arm-1 对照 + `step/usage` 埋点作为 Phase 4 的实验前置。

**什么证据能让我撤回（S4）**：三臂 A/B 显示 Arm-2 轮数显著下降但费用**上升**（索引成本吃掉收益）⇒ 我撤回"轮次是主杠杆"，改为"轮次是观察指标，索引成本需先受控"。

---

## 2. 攻击 A ｜ 外部研究：「AOCI 太重，别搬」——**证据不足，应降级为 M3**

**对方主张**（摘其原文）：`PROPOSAL-external-research.md#L15`：「AOCI = 模型策展+哈希基线+验证回环（质量强、**每次维护都要花模型 token+机器时间**：ledger 实测 maintain 中位 48.3s / 批量写入 97.6s，34 次 maintain 里 32 次 repair_required…）」；`#L121` 建议「把每次变更都模型重写换成块级哈希定位+只重写变更块」；`#L166` 自己承认 `duration_ms` 语义未验证、**不含模型 token**。

**我的攻击（从 ledger 逐条重算）**：
1. **32/34 repair_required ≠ "烂"：它在 ledger 里是"门禁-修复-收敛"**。我对 `.aoci/ledger.jsonl`（228 事件）重算（`ev:bench:phase3-aoci-ledger`）：
   - maintain 34 次：**32 repair_required + 2 error**，中位 48.1s（与外部一致）；全 ledger 共 38 次 repair_required（maintain 32 + auto_finalize 6）；
   - **38/38 次 repair_required 之后，2 小时内均出现一次成功写入（`update_entries_batch`/`recover`/`auto_finalize` 的 `ok`）**；30 分钟内 31/32 有后续写尝试，但结果分布是 `ok 25 / error 4 / rejected 2 / 无 1` ⇒ 不是"一次就过"，是**报修→修复重试→收敛**（工具契约明说 repair_required 必须完整处理再重提）——这是门禁按设计工作，不是"索引腐化/实现烂"。
2. **2.8h 墙钟的结构与"每次维护都昂贵"不符**：228 事件合计 10,049.9s 的分布是—
   `auto_finalize 3,674.9s（35 次，中位 107.4s）/ update_entries_batch 2,775.6s（32 次，中位 95.4s）/ maintain 1,641.5s（34 次，中位 48.1s）/ overview 851.3s / cognition_check 809.2s / …`。
   **主要成本在批量 apply/finalize 的机器侧（含哈希/校验/IO），不是"34 次 maintain 的模型重写"**；且 `aoci_tool_calls` 在 ledger 里是 1/次（单批调用）。另有 **91 次 remove_entry 全部发生在 2026-10-11 一天**（一次性清理），不是持续开销。
3. **"别搬"的结论方向可能对，但证据链不成立**：
   - 它没读到 AOCI 源码（自己承认），ledger **不含模型 token**（自己承认）⇒ "质量强/每次都要花模型 token"里，"花多少"**未测量**；
   - 32/34 这个数字**无法区分**「校验太严（门禁摩擦，可工程化改善）」与「索引腐化（实质质量差）」，而这两种解释对"该不该学它"结论相反——它把前者当成了后者；
   - 它推荐的"块级哈希定位+只重写变更块"恰好是 AOCI 的**便宜部分**（哈希基线），而它反对的"每次重写回环"是 AOCI 的**昂贵部分**；其证据支持的是一个**更窄**的结论（"别照抄完整回环"），不支持"AOCI 太重/质量不可信"。

**证据**：`ev:file:.aoci/ledger.jsonl`（228 事件；重算脚本 `phase3_aoci_ledger.py`）+ `ev:bench:phase3-aoci-ledger`（`phase3-aoci-ledger.json`）+ `ev:file:PROPOSAL-external-research.md#L15,#L42,#L121,#L166` + 本会话 `aoci_maintain` 工具契约（"repair_required 必须完整处理并重提"）。

**建议改成什么**：
- 把结论从"AOCI 太重，别搬"改为 **"AOCI 的完整重写回环不搬；其证据身份/哈希基线/软失效可搬；维护成本 = 机器侧批量 apply/finalize（实测 2.8h/17 天，含一次性清理），模型 token 未测（M3）"**；
- 在 P3-3（索引由谁建）里把"AOCI 太重"标为 **`unverified`/M3**，不要作为弃用理由；
- 若仍要弃用回环，理由用设计选择（"我们不需要人审语义"），不要用质量数据。

**什么证据能让我撤回（A1）**：
- 若 AOCI 源码/保留的 candidate 文件显示 `repair_required` 的 finding 主要是**语义重写类**（而不是 schema/格式/证据绑定类），且同一批 KP 反复报修多次才收敛 ⇒ "门禁严"解释弱化，我撤回；
- 若 ledger 的 `duration_ms` 被证明包含模型 token 往返（而非仅机器耗时）⇒ "2.8h 只是机器时间"的限定失效，我撤回成本归因那半条；
- 若 32 次报修中收敛窗口 >30min 的占多数（我算法 30min 窗口可能过严/过松需复核原始 ts）⇒ 收敛率结论需重算。

---

## 3. 攻击 B ｜ 语料方：「索引单元不用 KP / 需重建」——**身份与单元必须分开**

**对方主张**（摘其原文）：`PROPOSAL-corpus-analysis.md#L16`「现有 KP 不能直接当索引单元…前提是重建而不是复用」；`#L18/#L61`「93.3% 起点=标题 ⇒ 机械映射，不是学习单元；`2.4` 一条吞 17,344 字」；`#L281`「不要复用现有 357 条当索引…索引必须重建」。
**B 方已反打**（我同意其方向）：`PHASE3-OBJECTION-todo-owner.md#L24-L25`（O-B1/O-B2）——93.3% 起点=标题只证明起点，不证明标题边界坏；坏的是 end 边界；且 KP 尺寸两方口径差 3.5×（526 vs 1,822 字，均基于未修锚点）。

**我补的一刀（agent 检索角度）：若索引单元与 KP 不同源，会切断三样 agent 真正能用的东西**：

1. **FSRS 复习信号无法进入检索**：复习卡以 `kp_id` 为锚（真实 `cards.json` **105/114 张含 `card_id`+`kp_id`**，9 张缺 `kp_id` 需补/迁移；review 工具行含 `kp_id`，`ev:file:src/memoria/services/agent/tools/kb.py#L4732`）⇒ 若切片是另一套 id，agent 无法用"到期/薄弱 KP"给切片排序或过滤——这是**唯一不花 LLM token 的个性化信号**。
2. **"用户已复习"与"agent 已读"无法对齐**：本会话 37 次 read_document 中 36 次读同一章（`PROPOSAL-agent-arch.md#L33`）——没有 KP↔切片映射时，agent 无法知道某切片对应的 KP 是否刚被复习过，重复读已掌握内容 / 漏掉到期薄弱点，两个方向都会发生；R8 的"iterations/answer"收益也就无从谈起（因为无法把复习状态折进路由）。
3. **引用/图谱/链接锚会分裂**：图节点 `id = kp_id`（`ev:file:src/memoria/graph/collector.py#L55-L65`）、ontology node 字段含 `kp_id`（`ev:file:docs/design/kg-ontology-v0.md#L139-L140`）、会话 anchors 按 `(file,line,kp_id)` 去重（`ev:file:src/memoria/services/agent/session/history.py#L583-L587`）、kb 工具 anchors 带 `kp_id`（`ev:file:src/memoria/services/agent/tools/kb.py#L211-L227,#L283,#L319`）⇒ 新建一套 slice id 等于**第二套对象**，正是 B 方 O-B2 警告的迁移成本（357 kp_id + FSRS/link/图谱）。

**我的判定**：
- **接受语料方的"边界与覆盖有问题"**（end 边界坏、覆盖 4/14 章、OCR/重名/反转）；
- **反对"重建/新 id 空间"**：索引单元可以是"带预算的切片视图"（200–1200 字），但**语义身份必须仍锚在 `kp_id`**：
  `slice = {slice_id, parent_kp_id, kp_ids[], section_number, range, content_hash}`，检索结果**必须同时返回 `kp_id`**（可多值），引用仍写 `文件:行号` + 可选 `[kp_id]`。
- 这样：语料方的"切片粒度/预算"、B 方的"复习/边界"、我的"RRF 通道 + 路由"三者就不冲突；`kp_ids[]` 由 93.3% 起点=标题这个事实保证映射成本低（B 方 O-B2 已给出同构方案）。

**证据**：`ev:file:PROPOSAL-corpus-analysis.md#L16,#L18,#L61,#L281`；`ev:file:PHASE3-OBJECTION-todo-owner.md#L24-L25`（O-B1/O-B2）；`ev:file:src/memoria/services/agent/tools/kb.py#L4732`；`ev:file:docs/example/AAA_Vocab/.memoria/agent/review/cards.json`（114 张，105 张含 `kp_id`）；`ev:file:src/memoria/graph/collector.py#L55-L65`；`ev:file:docs/design/kg-ontology-v0.md#L139-L140`；`ev:file:src/memoria/services/agent/session/history.py#L583-L587`；`ev:file:src/memoria/services/agent/tools/kb.py#L211-L227,#L283,#L319`。

**建议改成什么**：
- 语料方结论从「不要复用 KP / 必须重建」改为「**修 end 边界 + 补覆盖 + 清洗；索引单元 = 切片视图，身份 = kp_id + slice 映射**」；
- Phase 4 明确：**不允许出现第二套语义 id**；`slice_id` 只做视图键，`kp_ids[]` 强制非空（映射失败该切片不入索引，而不是新建对象）；
- 首次建库预算里加一条"`KP→slice` 孤儿率"验收（B 方 O-B2 已提 ≤20%）。

**什么证据能让我撤回（A2）**：
- 若语料方能证明"`KP→slice` 映射孤儿率 >20%"或"FSRS/link 迁移成本 < 映射成本"（实测），我撤回"必须保留 kp_id 身份"；
- 若 A/B 显示"agent 用 FSRS 到期信号排序切片"对 iterations/answer **无改善**，我撤回第 1 条收益论据（但仍保留引用/图谱锚一致性理由）；
- 若切片 id 能稳定 join 回 kp_id 且成本可忽略（例如切片天生带 heading 编号、映射 100%），那"第二套对象"风险下降，我对"重建"的反对弱化为"迁移成本需实测"。

---

## 4. 我这轮明确撤回/降级的东西（防守失败清单）

| # | 原主张（我的提案） | 处置 | 触发 |
|---|---|---|---|
| R-1 | 「露 id = 两行改动，可独立上线/独立 A/B」 | **撤回** | O1-A/O1-C：依赖锚点正确性，必须串行 + gate |
| R-2 | 「read_kp 采用率 6/37 是缺陷，提升采用率是收益」 | **撤回**（降为诊断） | O1-B：6/37 可能合理；1,431 tok 更贵 |
| R-3 | 「省 1 iteration ≈ −20.5%」 | **降级**为线性外推/候选 KPI | D O-2：算术≠测量；且 iteration≠call |
| R-4 | R5 用"放大 10.94×"论证禁全量注入 | **改口径**：按 D 修正 1.16×（存活），价值改为峰值/当轮 miss + Lost-in-Middle | D O-1 |
| R-5 | K1「锚点与露 id 可并列」 | **撤回** | O1-C |
| R-6 | 峰值 65.7%（656,818）为安全线 | **更新**：峰值已 845,926=84.6%（21 轮冻结快照），P0 安全 | D O-3/§4 |

**未撤回**（仍主张）：L0/L1/L2 预算分层（≤300/≤800/单次≤1.5k，禁止整库注入）；索引作为 RRF 第 3 通道且保留 lexical（`retrieval_fusion.py#L145-L152`）；描述必须"可判"；答对率是硬门槛；`kp_id` 作为跨 FSRS/图谱/引用的唯一语义身份。

---

## 5. 防御性补强（我主动给 Phase 4 的裁决素材）

1. **anchor gate 的最小 spec（可直接实现）**：`read_kp` 输出增加 `anchor_verified`/`anchor_warnings[]`；规则：`range_ok==False → ANCHOR_UNRESOLVED`；start/end snippet 全文出现 >1 → `AMBIGUOUS_ANCHOR`（带候选+heading 路径）；end 非唯一或 span>预算 → 夹到下一同级标题；只有 `anchor_verified` 的 KP 在工具输出里露 id。成本：每次 read_kp 一次全文件行扫描（数千行，`locator` 已做类似操作，经验判断为毫秒级）。
2. **iteration 可测量化**：在 loop 的 `step_usage` 处追加 `step/usage` 事件（只追加，不改请求体），使"省 1 iteration"从算术变实测（回应 D 的 U-P3/O-2）。
3. **R8 双门槛**：主门槛 = 答对率不降（硬）；观察 = iterations/answer + 峰值；成本只在两者都不恶化时才计入验收。Arm-1（只注入索引 token）必须有（D 设计）。

---

## 6. 新增 unknowns（M3，带 `if_true_then`）

| id | 未知 | if_true_then |
|---|---|---|
| U-C1 | anchor gate 后 read_kp 的错切片率是否真为 0（未实现） | 若 >0 ⇒ 撤回"gate 足以安全露 id" |
| U-C2 | 每次 iteration 的独立成本（无 step usage） | 若实测"省 1 iteration"远低于 −18% ⇒ 撤回"轮次更有价值"的方向性结论 |
| U-C3 | AOCI `repair_required` 的原因构成（schema/格式 vs 语义重写） | 若以语义重写为主且反复 ⇒ 我对外部研究的攻击减弱，承认"回环重" |
| U-C4 | `KP→slice` 映射孤儿率与 FSRS 作为检索先验的实际收益 | 若孤儿>20% 或无收益 ⇒ 撤回"必须保留 kp_id 身份"的强主张 |
| U-C5 | 索引注入对缓存命中率的影响（D 的 M12） | 若掉 >5pp ⇒ 索引净收益可能为负，需把 M12 列入否决条件 |

---

## 7. 产物与复跑

| 文件 | 内容 | sha256 |
|---|---|---|
| `phase3_aoci_ledger.py` → `phase3-aoci-ledger.json` | AOCI ledger 228 事件重算（op/耗时/repair 收敛/remove_entry 分布） | 见文件 |
| `phase3_iteration_relation.py` → `phase3-iteration-relation.json` | 冻结快照 21 轮 / 116 iterations / 135 calls 的精确关系与并行分布 | 见文件 |
| `phase3-session-snapshot.jsonl`（D 冻结，复用） | 会话快照 | `b906f0defb8b987b…` |
| `r4-wrongpin-probe.json`（A 方，复用） | 67/357 静默错位样本（含 occurrences_in_doc） | A 方提供 |

复跑：
```bash
python artifacts/agent/verify/debate/kg-retrieval/phase3_aoci_ledger.py --json artifacts/agent/verify/debate/kg-retrieval/phase3-aoci-ledger.json
python artifacts/agent/verify/debate/kg-retrieval/phase3_iteration_relation.py --json artifacts/agent/verify/debate/kg-retrieval/phase3-iteration-relation.json
```

## 8. 一句话

**我接受 O1-A/O1-B/O1-C 与 C8 的降级：露 id 不是"两行独立收益"，而是"锚点 gate 之后的可发现性"；6/37 可能本来就是对的行为；−20.5% 是算术、iteration 与 call 是 1.164:1 的关系（21 轮 116 iterations/135 calls）。** 对外我打两处：**AOCI 的 32/34 repair_required 在 ledger 里是"门禁-修复-31/32 收敛"，2.8h 主要花在批量 apply/finalize，不足以支持"AOCI 太重"的结论**；**索引单元可以是切片，但语义身份必须留在 kp_id，否则 FSRS/图谱/引用的锚全断，agent 也无法用"已复习/到期"做路由**。
