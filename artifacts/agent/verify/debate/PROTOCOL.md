# 辩论协议（FROZEN）

> **状态**：FROZEN @ 2026-10-25T00:49:53+08:00
> **冻结依据**：Phase 1 四方独立提案 → Phase 2 Lead 并集合并（0 条自创）→ Phase 3 四方异议（19 条）→ Phase 4 逐条裁决（26 条 ruling）→ Phase 5 冻结
> **配套文件**：`freeze-v2.json`（F1 冻结物）｜`PINNED-PROPOSALS.json`（提案/异议 sha 冻结）｜`ruling/rulings.jsonl`（26 条裁决）｜`proposals/`（4 份提案）｜`protocol-objections/`（4 份异议）
> **适用范围**：本文只约束**本次 Memoria agent 能力架构辩论**，不是通用团队规范。
> **可复核**：任何第三方凭上述 5 类磁盘产物即可重算每条裁决（J6'）。

---

## 0. 三条元原则

- **M1 合法性来源**：裁决的合法性来自「证据 + 可复核 + falsifier」，**不来自 Lead、人或多数的点头**。
  人的**决策权 100% 保留**，但推翻可复核裁决须走 `authority_override`（见 §7）。
  ← arch-contract §3-1、steward §3-2、R-C4
- **M2 证据优先于人数**：票数只作"值得关注"的信号，永不作为关闭争议的依据。
  任何「多数/一致」措辞必须附 `independent_roots > 1`，否则记 `unsupported-majority`。
  ← agent-arch R2、arch-contract R3、steward R3、R-C17
- **M3 诚实中立**：登记 `unknowns` / `not_doing` 不算缺陷；但**未登记任何未知不构成「更成熟」**，反可能触发 `coverage_gap`。
  ← agent-arch R5 + R-C15

---

## 1. 证据层

- **E1 证据身份**：每条证据必须有 `source_identity = kind + ref (+ sha/commit)`：
  `ev:file:<path>#L<n>` / `ev:commit:<sha>` / `ev:bench:<id>` / `ev:spec:<spec>#<sec>` / `ev:doc:<path>#<h>` / **`ev:counterexample:<id>`**
  脱离身份的引用**无效**。 ← metrics R3、steward R3、arch-contract R1、R-C5
- **E1' 反例**：`ev:counterexample` 必填 `claim_ref`（被证伪的主张）+ `evidence` + `argument`；`replay` 可选，缺 `replay` 按普通引用计权。
  ← arch-contract §4.3、R-C5
- **E2 同源去重**：同一 `source_identity` 被多方引用 ⇒ 合并为 1 份，标注「由 N 方共同引用」；统计须分开报 **独立来源数 / 引用次数**。
  ← agent-arch R2、steward R3、R-C17
- **E3 共享假设单列**：未验证前提必须登记 `assumption_id` + 指派检验者 + **`due_by`（检验期限）**；逾期未检验 ⇒ 自动降为「未检验」，不得作裁决依据。
  ← agent-arch R3、arch-contract R2、steward §5、R-C24
- **E4 可复现才有效**：省 token/省时/更快类主张必须有 `ev:bench:<id>`；评审者有权要求复现，**复现失败 = 证据作废**。
  ← arch-contract R5、metrics §4.1
- **E4.2** `ev:bench:<id>` 最低溯源 8 项：同 commit / 同语料 / 同任务集 / 同脚本 / 同轮数 / 冷热口径 / ≥3 重复或完整分布 / 原始产物落盘带 sha。缺一不认。 ← metrics、R-C11
- **E4.3** **跨口径不可相减**：commit / 语料 / 任务集三者不全相同 ⇒ 数字不得相减、不得用于裁决。 ← metrics、R-C11
- **E5 不一致必须披露（强制二分）**：(a) 逐字节一致 **或** (b) 报告 ≥5 次完整分布（median + min–max + 每次原始值）；
  **二者皆不满足 ⇒ 该数据不得用于裁决**（不是"建议补充"，是**不可用**）。 ← metrics R4、R-C10

---

## 2. 提案层

- **P1 对称举证**：任何"否决/反对"必须同时给出 ① 证据 ② 最小修补或替代入口。
  想不出替代时**明说"未尝试"，转为 `conditional_object`**（须给 `reversal_condition`），**仍进 J4 异议建档**。
  ← agent-arch R1、arch-contract R1、R-C6
- **P2 不得要求缺席证明（含充分性判据）**：
  - **(a) 禁止句式**：任何一方不得被要求证明「不存在 / 没有遗漏」。
  - **(b) 提案者义务**：三张表 `checked[]` / `not_examined[]` / `out_of_scope[]` 对同一 F1 冻结枚举构成**分割**（并集完整、两两不相交）；缺项记 `coverage_gap`。
  - **(c) 有效质疑形态**：只能是「漏了 X：「ev:具体身份」+ X 属冻结 scope 的证明」；"清单看起来不全"**不受理**。
  - **(d) 抽查纪律**：裁决随机选 N=3 条 `checked`（种子记入裁决）；失败 1 条 ⇒ 该提案 `examined` 降 `unverified`；≥2 条 ⇒ coverage 整段作废 + `integrity` FAIL。
  - **(e) 谎报重罚**：`checked` 被证伪 ⇒ `false_claim` ⇒ 该方全部 coverage 声明降 B 级 + 取消 P4/M3 豁免。
  ← agent-arch §4.4、steward、R-C3、R-C14
- **P3 预算与时序对称**：同等时间/篇幅预算内未回应不判负；**上限须相等且在轮次开始前公布**，事后调整 = `baseline_mutation`。
  ← agent-arch R5、R-C18
- **P4 诚实中立（含判据）**：`unknowns` / `not_doing` 是合法交付物；豁免以**存在 `if_true_then`**（若该未知为真则结论如何变）为前提，写不出者不享受豁免。
  ← agent-arch R5、R-C2、R-C16

---

## 3. 裁决层

- **J1 逐条对照**：裁决必须对每条被驳回立场逐条对照其证据；**每条 claim 必须列 `supporting_evidence_ids`**。
  ← agent-arch R4、steward、R-C25
- **J2' 少数派唯一证据（防无限阻塞）**：被驳回立场若持 `unique_evidence`，裁决须逐条写 `unique_evidence_handled: accepted|rejected|deferred + 理由`。
  `deferred` 须同时满足：① 裁决方**核验** `unique_evidence` 成立 ② 指派检验者 ③ 给 `deadline` ④ **阻塞方承担举证义务**。
  **逾期自动降 `rejected` 并入 J4**；唯一例外是人在期限前显式延长（记 `authority_override`）。
  ← steward R4、arch-contract R3、agent-arch R4、R-C7
- **J3 可证伪**：每条裁决必须给 `falsifiers`（什么证据出现则本裁决撤回）。
  ← arch-contract R4
- **J4 少数意见原样冻结**：少数派异议单独建档（`rejected-objections`），原样进冻结产物，不得摘要化或删除。
  ← arch-contract R3、agent-arch R4
- **J5 不许加料**：最后一轮不得引入辩论中从未出现的新证据/新要求据此终局判负；新要求只进下一轮。
  ← agent-arch §3.2
- **J6' 可复算（简化版）**：放弃全过程哈希链，改 **3 个冻结检查点**（`freeze-v2.json` / `phase1_submissions` / `ruling.json`）+ `evidence_ledger` + 裁决→证据映射。
  **强制力来自存储位置**：辩论产物必须进 **git**（或复制到非 ignore 路径），以 **git blob sha** 而非工作区字节为准。
  ← steward R5 + 主动降级、R-C21

---

## 4. 独立性与冻结

- **F1 冻结基准**：Phase 0 冻结「问题陈述 + 可接受判据 + 标准版本(sha256) + `expected_categories`」。
  实现见 `freeze-v2.json`。冻结后变更 = `baseline_mutation`，**必须重开受影响 Phase**。 ← steward R1、R-C22
- **F2' 可证明的独立性**：
  - `read_set` 每项含 `path` + **LF 归一化 sha256** + `read_at`
  - **机器证据优先**：Phase 1 窗口内 `team_trajectory` 的 `file_read` 不得含他人提案
  - `mtime`/`sha` 仅作辅助（**提交晚 ≠ 读过**）
  - 目录枚举/仅见文件名不算互读，但须在 `unread_declared` 声明
  - 轨迹缺失或截断 ⇒ 标 `independence: unverifiable`（不指控、也不计独立票）
  ← steward R2、arch-contract、R-C8

---

## 5. 度量专有（仅适用度量证据）

- **B1 口径预签署**：基准口径须**测量前**多方签署，测量后不得单方修改。
  **范围限定**：仅约束本协议生效后的**新测量**；协议前既有产物记 `pre-protocol-evidence`，
  可引用但支撑"省 token"类主张时降 **B 级**。 ← metrics R1、agent-arch、R-C19
- **B2 对比对称**：被测双方须同会话、同语料、同任务、同轮数。 ← metrics R2
- **B3 首选解读权 ≠ 否决重解权**：测量者的首选解读记录不可剥夺，但**不得否决他人重解**；
  机器校验 `interpretation.authority=primary-recorder` 只允许出现在 `evidence_kind=bench` 上。 ← metrics R5、agent-arch、R-C1、R-C20
- **B4 不认的"省 token"声明（六类，以下列为全部判据，非举例）**：
  - **B4.a** 只报输入不报输出 ⇒ 须齐报 `prompt`/`completion`/`total` + 加权成本
  - **B4.b** 只报单次不报分布 ⇒ 须报 ≥5 次 median + min–max + 每次原始值（与 E5 联合生效）
  - **B4.c** 换口径对比 ⇒ commit/语料/任务集不全同不得相减、不得用于裁决
  - **B4.d** 用压缩率代替绝对 token ⇒ 须同时给绝对值与压缩率
  - **B4.e** 只测"能否跑通"不测"省不省" ⇒ 须分离 `functional_pass` 与 `token_delta`
  - **B4.f** 把开销藏进 system prompt / tools schema 后只对比 per-call ⇒ 须报**总账单**（system + schema + messages + completions）
  ← metrics §4.2、R-C9
- **B5 业界惯例**：可作背景动机，**不可作裁决证据**。
- **B6 口径不可票决**：不得以「多数人认为该口径合理」推翻度量口径 —— 语料是否密封、是否可复跑是**物理事实**。 ← metrics、R-C13

---

## 6. N1（参与者提案，非 Lead 规则）

**N1：架构辩论开始前必须先检验共享假设 A1「MCP 化一定增 token 开销」。**
- 指派检验者：`metrics-baseline`
- 判据必须含 **「零新增 schema」对照组**（否则无法区分是 MCP 化导致还是功能增加导致）
- **N1 不预设方向**：若 A1 被证伪（MCP 实际更省），同样照实报
← metrics-baseline（诚实标注为新增建议，援引 E3 末句作为最接近的既有依据）、R-C12

---

## 7. 人的推翻机制（CONFLICT-4）

人有 **100% 最终决策权**，但推翻可复核裁决须落成独立事件 `authority_override`，含：
1. 书面理由
2. 指名被推翻的 `ruling_id`
3. 给 `falsifier`，**或**显式声明「不基于可检验理由」
4. 进独立档，**不入 `ruling-log`**

**核心约束：`authority_override` 不得在此后被引用为「证据结论」。**
⇒ 三个月后，组织决定不得被读成「证据表明该方案错了」。
← arch-contract、agent-arch、steward、R-C4

---

## 8. Phase 1 独立性实测结论（steward 审计）

| 提案 | F2 声明合规 | Phase 1 窗口读他人提案 | 结论 |
|---|---|---|---|
| agent-arch | 部分（无 sha） | 无 | 独立成立；IND-1 其声称读过 measurement-guidelines 但轨迹无对应 file_read ⇒ `unverifiable` |
| metrics-baseline | 不合规（无 read_set） | 无 | 独立成立 |
| arch-contract | 不合规（无 read_set） | 无 | 独立成立（轨迹截断 ⇒ 宜标 unverifiable） |
| steward | 合规（path+sha） | 无 | 独立成立 |

- **内容相似度**：8-gram Jaccard 两两最高 **1.16%** ⇒ 无抄袭迹象
- **IND-3**：3/4 提案不符合 F2 现行格式 —— 记为**规则未给 schema 的实证**，不计参与者过失
- **IND-4**：`artifacts/**` 不进 git ⇒ 提案可静默改写 ⇒ 已由 J6' 的「必须进 git」修正
← steward、R-C26

---

## 9. 规则来源溯源表（45 条全部可追溯）

| 规则 | 来源 |
|---|---|
| M1 / M2 / M3 | arch-contract §3-1、steward §3-2 / agent-arch R2、arch-contract R3、steward R3 / agent-arch R5 + R-C15 |
| E1 / E1' / E2 / E3 / E4 / E4.2 / E4.3 / E5 | metrics R3、steward R3、arch-contract R1、R-C5 / arch-contract §4.3、R-C5 / agent-arch R2、steward R3、R-C17 / agent-arch R3、arch-contract R2、steward §5、R-C24 / arch-contract R5、metrics §4.1 / metrics、R-C11 / metrics、R-C11 / metrics R4、R-C10 |
| P1 / P2 / P3 / P4 | agent-arch R1、arch-contract R1、R-C6 / agent-arch §4.4、steward、R-C3、R-C14 / agent-arch R5、R-C18 / agent-arch R5、R-C2、R-C16 |
| J1 / J2' / J3 / J4 / J5 / J6' | agent-arch R4、steward、R-C25 / steward R4、arch-contract R3、agent-arch R4、R-C7 / arch-contract R4 / arch-contract R3、agent-arch R4 / agent-arch §3.2 / steward R5、R-C21 |
| F1 / F2' | steward R1、R-C22 / steward R2、arch-contract、R-C8 |
| B1–B6 | metrics R1–R5、agent-arch、R-C19、R-C20、R-C9、R-C13 |
| N1 | metrics-baseline（标注为参与者新增建议）、R-C12 |
| §7 override | arch-contract、agent-arch、steward、R-C4 |

**Lead 自创规则数 = 0。**（26 条裁决全部对应某方异议或两方冲突的调和）

---

## 10. 本协议不解决的问题

- **防不了「全员都没想到」**（共同知识盲区）。只能防「想到了但被压下去」与「伪独立」。
  对策是硬要求提案者引用 **≥3 个外部独立来源**（MCP 规范 / 其他项目实践 / 学术或工程测量），且不得同作者同材料。
- **`unique_evidence` 是否真 unique、共享假设是否"合理"** 属语义判断，机器不判，只查"是否被处理 / 是否有 falsifier / 是否标注有条件"。
- **`deliberation_quality` 机检尚未实现**：按「先条款后检查」，协议冻结后才做，且每个检查先有必红 fixture。

---

## 11. 裁决索引

26 条裁决见 `ruling/rulings.jsonl`，编号 `R-C1` … `R-C26`：
- `R-C1`–`R-C4`：4 个 CONFLICT 裁决
- `R-C5`–`R-C8`：arch-contract 的 4 个 object
- `R-C9`–`R-C13`：metrics-baseline 的 4 个 object + N1
- `R-C14`–`R-C20`：agent-arch 的 7 个 object
- `R-C21`–`R-C26`：steward 的 3 个 object + 3 项补强 + 独立性审计结论

**未被采纳的异议**：2 条（均在同一冲突 R-C7 中，理由已给 `unique_evidence_handled`）。
其余 24 条全部采纳（含 3 条以修改形式采纳）。
