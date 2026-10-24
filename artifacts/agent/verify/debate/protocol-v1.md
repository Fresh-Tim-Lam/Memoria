# 辩论协议 v1（Phase 2 合并稿，待 Phase 3 异议）

> **这份文件由 Lead 合并，不新增任何规则。**
> 每条规则末尾的 `←` 标明它来自哪份提案的哪一条；无 `←` 者视为 Lead 自创，应立即删除。
> 冲突处标 `CONFLICT-n`，Phase 3 各方提异议，Phase 4 Lead 逐条裁决。

## 0. 目的与三条元原则

**目的**：让架构辩论的结论来自证据，而不是票数、权威或共享假设。

- **M1 合法性来源**：裁决的合法性来自「证据 + 可复核 + falsifier」，**不来自 Lead、人或多数的点头**。
  ← arch-contract §3-1、steward §3-2
  注：**决策权**仍属人（组织事实），但人推翻可复核裁决时必须给理由并接受 falsifier 检验。
  ⇒ 见 `CONFLICT-4`
- **M2 证据优先于人数**：票数只作"值得关注"的信号，永不作为关闭争议的依据。
  ← agent-arch R2、arch-contract R3、steward R3
- **M3 诚实中立**：写"不确定什么 / 不做什么"不算缺陷。
  ← agent-arch R5；`CONFLICT-2` 见 §7

## 1. 证据层

- **E1 证据身份**：每条证据必须有 `source_identity = kind + ref (+ sha/commit)`
  （`ev:file:<path>#L<n>` / `ev:commit:<sha>` / `ev:bench:<id>` / `ev:spec:<spec>#<sec>` / `ev:doc:<path>#<h>`）。
  脱离身份的引用**无效**。 ← metrics-baseline R3、steward R3、arch-contract R1
- **E2 同源去重**：同一 `source_identity` 被多方引用 ⇒ **合并为 1 份**，标注「由 N 方共同引用」。
  统计必须分开报 **独立来源数 / 引用次数**，不得只报引用次数。 ← agent-arch R2、steward R3
- **E3 共享假设单列**：任何结论依赖的未验证前提必须显式登记 `assumption_id`，
  且**逐条指派"谁负责检验它"**。未检验的共享假设 ⇒ 该结论自动降级为"有条件成立"，不得作裁决依据。
  ← agent-arch R3、arch-contract R2、steward §5
- **E4 可复现才有效**：主张"省 token / 省时 / 更快"必须有 `ev:bench:<id>`；
  评审者有权要求复现，**复现失败 = 证据作废**。 ← arch-contract R5、metrics-baseline §4.1
- **E5 不一致必须披露**：同一现象多次测量不一致时，禁止择一引用，必须报完整分布
  （或证明逐字节一致）。 ← metrics-baseline R4

## 2. 提案层

- **P1 对称举证**：任何"否决/反对"必须同时给出 ① 证据、② 最小修补或替代方案的入口；
  想不出替代时必须**明说"未尝试"并降级为提问**，不得以否决形式出现。 ← agent-arch R1、arch-contract R1
- **P2 不得要求缺席证明**：任何一方都不得被要求证明"不存在/没有遗漏"。
  强主张（如"全量移植"）以**覆盖面清单 + 已知盲区声明**评价，不以"证明无遗漏"评价。 ← agent-arch §4.4
- **P3 预算与时序对称**：各方在同等时间/篇幅预算内未回应，不判负；也不得因回应晚而降低效力。 ← agent-arch R5
- **P4 诚实中立**：`unknowns` 与 `not_doing` 是**合法交付物**，不得因此扣分。 ← agent-arch R5

## 3. 裁决层

- **J1 逐条对照**：裁决必须对每条被驳回立场逐条对照其证据，不得整体打包。 ← agent-arch R4、steward §3-1
- **J2 少数派唯一证据强制处理**：被驳回立场若持有其他立场**没有的** `unique_evidence`，
  裁决必须逐条写 `unique_evidence_handled: accepted|rejected|deferred + 理由`；
  缺失 ⇒ 该裁决只能 `open`，**禁止票决关闭**。 ← steward R4、arch-contract R3、agent-arch R4
- **J3 可证伪**：每条裁决必须给 `falsifiers`（什么证据出现则本裁决撤回）。 ← arch-contract R4
- **J4 少数意见原样冻结**：少数派异议必须**单独建档**（`rejected-objections`），原样进入冻结产物，
  不得被摘要化或删除。 ← arch-contract R3、agent-arch R4
- **J5 不许"加料"**：最后一轮不得引入辩论中从未出现的新证据/新要求据此终局判负；
  新要求只能进下一轮。 ← agent-arch §3.2
- **J6 append-only 可复算**：全过程哈希链日志，任何第三方只凭磁盘产物即可重算结论。 ← steward R5

## 4. 独立性与冻结

- **F1 冻结基准（Phase 0）**：冻结「问题陈述 + 可接受判据 + 标准版本(sha256)」；
  冻结后任何变更 = `baseline_mutation` 事件，**必须重开受影响的 Phase**。 ← steward R1
- **F2 可证明的独立性**：每份提案首部声明 `read_set`（文件+sha256）与 `unread_declared`，
  提交时记录 `mtime + sha`。互读被证实 ⇒ 标 `non_independent`，**不占独立票**。 ← steward R2

## 5. 度量专有（仅适用于度量类证据）

- **B1 口径预签署**：基准口径必须在**测量前**由多方签署，测量后不得单方修改。 ← metrics-baseline R1
- **B2 对比对称**：被测双方必须在同一次会话、同语料、同任务、同轮数下测。 ← metrics-baseline R2
- **B3 测量权与解读权同源**：测量者的解读不可被剥夺。 ← metrics-baseline R5；`CONFLICT-1` 见 §7
- **B4 不认的"省 token"声明**（六类，详见 metrics-baseline §4.2），
  其中最关键：**把工具调用开销藏进 system prompt 后只对比 per-call**。 ← metrics-baseline §4.2
- **B5 业界惯例**：可作背景动机，**不可作裁决证据**。 ← metrics-baseline §4.3、arch-contract §4.1

## 6. 来源溯源表

| 规则 | 来源 |
|---|---|
| M1 | arch-contract §3-1、steward §3-2 |
| M2 | agent-arch R2、arch-contract R3、steward R3 |
| E1 | metrics-baseline R3、steward R3、arch-contract R1 |
| E2 | agent-arch R2、steward R3 |
| E3 | agent-arch R3、arch-contract R2、steward §5 |
| E4 | arch-contract R5、metrics-baseline §4.1 |
| E5 | metrics-baseline R4 |
| P1 | agent-arch R1、arch-contract R1 |
| P2 | agent-arch §4.4 |
| P3 | agent-arch R5 |
| P4 | agent-arch R5 |
| J1 | agent-arch R4、steward §3-1 |
| J2 | steward R4、arch-contract R3、agent-arch R4 |
| J3 | arch-contract R4 |
| J4 | arch-contract R3、agent-arch R4 |
| J5 | agent-arch §3.2 |
| J6 | steward R5 |
| F1 | steward R1 |
| F2 | steward R2 |
| B1 | metrics-baseline R1 |
| B2 | metrics-baseline R2 |
| B3 | metrics-baseline R5 |
| B4 | metrics-baseline §4.2 |
| B5 | metrics-baseline §4.3、arch-contract §4.1 |

## 7. 冲突清单（待 Phase 3 异议 / Phase 4 裁决）

- **CONFLICT-1｜度量规则是否通用化**
  metrics-baseline R5（测量权与解读权同源）适用范围是「度量证据」还是「所有证据」？
  若通用化 ⇒ 每个结论只能由提出者解读，可能过强；若仅度量 ⇒ 非度量结论的解读权归属未定。
- **CONFLICT-2｜unknowns 的中立边界**
  agent-arch R5 主张"不确定什么不计缺陷"；但若提案者大量堆 `unknowns` 可逃避完整性责任。
  需要裁决：「应知而未知」是否扣分，以及凭什么判"应知"。
- **CONFLICT-3｜P2「不得要求缺席证明」的边界**
  该条防止结构性必败，但可能被用来拒答"你漏了什么"。需要裁决：覆盖面清单的最低充分性由谁判、按什么标准。
- **CONFLICT-4｜裁决合法性 vs 人的最终决策权**
  M1 说合法性不来自"人批准"；但组织事实是人有最终决策权。
  需要裁决：人推翻可复核裁决时的形式要件（是否必须给理由+falsifier+是否记录为 dissent）。

## 8. 本稿未做的事

- 未新增任何提案中没有的规则（若有请指出，我会删）。
- 未实现机检（`deliberation_quality`）—— 按"先条款后检查"，等协议冻结后再做。
- 未对 CONFLICT-1..4 做任何预判。
