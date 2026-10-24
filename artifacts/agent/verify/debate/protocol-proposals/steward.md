# 辩论协议提案（过程审计视角）—— steward2 独立提案

> **Phase**：Phase 1（独立提案）
> **角色**：过程审计（只管"这场辩论会不会变成走过场"，不裁决架构内容对不对）
> **提交时间**：2026-10-25T00:46+08:00（Asia/Shanghai）
> **独立性声明（本文件首部即受自己 §2-R2 约束）**：
> ```json
> {
>   "read_set": [
>     {"path": "AGENTS.md", "section": "§0.5", "sha256": "6c87fe55077c4a73e2d14df8757683994c5da100dea913970452c5eea0cc8e5b"},
>     {"path": "docs/guides/lead-dispatch-rules.md", "section": "§1.2b/§1.3b/§5.4/§6", "sha256": "488d7ebd78c917e2c62b71c20635d1111a275a60306b5b742bb4247387beeb39"},
>     {"path": "docs/guides/agent-team-lessons.md", "section": "全部（含 L9.6/L9.7）", "sha256": "f2f86b090d6e088a734e640bb6552af591eaa7d8f7d41199e227ef95a9b71268"},
>     {"path": "docs/guides/agent-team-org.md", "section": "§2.3/§2.6", "sha256": "fd91c21ff75901edb84807fa6faeb4e8b4d4270d8c8bed20c19042f184d72872"},
>     {"path": "scripts/agent/team_audit.py", "section": "检查清单 + --determinism", "sha256": "e6f16ef1720084690354d82d189f5614b5354fd54560c21fe7417d8331a6cc51"}
>   ],
>   "unread_declared": [
>     "artifacts/agent/verify/debate/protocol-proposals/agent-arch.md",
>     "artifacts/agent/verify/debate/protocol-proposals/arch-contract.md",
>     "artifacts/agent/verify/debate/protocol-proposals/metrics-baseline.md",
>     "任何其他成员在 Phase 1 的提案（含草稿、消息摘要、口头转述）"
>   ],
>   "cross_read_events": [],
>   "note": "本文件写完后，其 sha256 与 mtime 由 Lead/审计在 Phase 1 关闭时记录；在此之前我不读他人提案。"
> }
> ```
> 我声明：**本提案未参考任何其他成员的 Phase 1 提案**；如 Leader/其他成员在我提交前后发现互读证据（mtime 先后 + 内容相似），
> 请按本文件 §2-R2 把我的提案标为 `non_independent`，不占独立票。

---

## 1. 我可能怎样被不公平对待（先写危险，再写规则）

**危险 1：事后无阻断权 ⇒ 我的 finding 只能被"记录"，不能被"纠正"。**
我只能审计已经发生的辩论；若协议不规定「审计窗口 + 违约后果 + 重开条件」，裁决方可以合法地说
"你提得太晚了 / 已经定稿了"。于是过程违约变成台账上的一行记录，而不是任何改变。

- **我会怎么被吃掉**：我的 finding 被归入"流程改进建议"（不触发重开），或要求我"等下一轮"；下一轮又有新的事后理由。
- **受损方**：持唯一反证的少数派（他们的证据从此只存在于归档中）；以及**未来所有审计**——先例一旦成立，审计=装饰。
- **我要的保障**：协议必须**预先声明**「过程违约的后果」（见 §2-R4/R5），并规定"审计发现 unique evidence 未被裁决 ⇒ 裁决不可关闭"，
  不是等我喊，而是规则自动使裁决无效。

**危险 2：「什么算公平」由裁决方单方面定义，我被排除在定义之外。**
如果问题陈述、可接受判据、证据等级、甚至"什么算过程证据"都由主席/多数派在辩论中临时定义，
我的检查器会被**按结果定制**（"这条不算"），或被要求"只查格式、不查实质"。
更隐蔽的形式：让我在 Phase 1 也提"架构提案"，从而把我的审计角色和参战角色混在一起——我的过程 finding 会被读成"输了的一方在抱怨"。

- **我会怎么被吃掉**：判据后置（先有结论再挑判据）；或判据写成我无法执行的形状（主观词、无证据锚）。
- **受损方**：少数派、外部复核者、以及裁决本身的可信度（无法证明"按同一把尺子量的"）。
- **我要的保障**：§2-R1 在 Phase 0 冻结**问题陈述 + 判据 + 标准版本**，冻结物有 sha256；冻结后改题必须显式记录并重开受影响 Phase；
  同时明确**审计者不参与架构裁决**（角色分离写进协议），避免"既当运动员又当裁判"的怀疑。

**危险 3：我的证据被降级为"程序瑕疵"，或反过来被当成"对架构结论的否决"。**
两个方向的滥用都会让我失效：
（a）把**实质问题**（同源伪多数、共享假设、少数派被压）重分类为"流程细节"，从而不改变结论；
（b）把**流程问题**当成"结论无效"的自动否决权，结果没人再敢让我审计，或我被指控"用流程绑架实质"。

- **我会怎么被吃掉**：裁决书只写"已记录 audit findings"，不写"这些 finding 改变了哪条评估"；或只写"因程序瑕疵结论作废"，不写"哪些证据仍然成立"。
- **受损方**：双方（实质讨论被流程噪音淹没；或程序被当成武器）。
- **我要的保障**：§2-R5 要求**每条裁决 claim 显式映射到过程证据**（包括"本条不受 X finding 影响，因为…"）；
  §3 明确"程序违约的后果是**重开受影响条目**，不是整场作废"。

---

## 2. 协议必须保证的规则（每条写：违反 → 谁受损）

### R1（冻结基准）Phase 0 必须冻结「问题陈述 + 可接受判据 + 标准版本」，冻结物带 sha256；冻结后变更 = `baseline_mutation` 事件，必须重开受影响 Phase。

- **规则**：Phase 0 产出 `debate/freeze.json`：`question`、`acceptance_criteria[]`（每条必须可判定：什么观测算满足/不满足）、
  `standards[{path, sha256}]`（至少 AGENTS.md §0.5、lead-dispatch-rules、agent-team-lessons、agent-team-org §2.6、team_audit.py）、`frozen_at`、`frozen_by`。
  辩论期间任何标准被修改（我的 `steward_self_audit` 机制本来就会让收据过期）⇒ 记 `baseline_mutation`，**并决定重开范围**（Phase 2 重读 / 全部重跑），
  不允许"边辩边改题"或"标准变了接口径不变"。
- **若违反谁受损**：
  - **所有参与者**：基于不同版标准的论证不可比，等于各说各话；
  - **后加入者**：不知道规则已变，按旧版理解发言；
  - **审计者（我）**：无法复算"按哪版标准判的对"；
  - **最终采用者**：拿到一个"在某个未记录时间点的标准下成立"的结论。

### R2（可证明的独立性）每份 Phase 1 提案必须声明 `read_set`（读过的文件 + sha256）与 `unread_declared`，并在提交时记录文件 mtime + sha256；互读被证实 ⇒ 该提案标 `non_independent`，不得计入独立票数。

- **规则**：提案首部（本文件示范）放机器可读的 `read_set`/`unread_declared`；Lead 在 Phase 1 关闭后**统一发布**每份提案的
  `{path, sha256, mtime_first_seen}` 列表与提交顺序；任何 mtime 矛盾（如 A 的提案 mtime 晚于 B 但内容引用 B 的独有措辞）⇒ 标 `non_independent`。
  允许"读过同一标准"（那是共享基准，R3 会去重），但**不允许**在 Phase 1 互读提案。
- **若违反谁受损**：
  - **持少数证据的成员**：伪独立共识会以"多票"压掉唯一反证；
  - **决策者**：基于回声（echo）做决定，误以为已充分检验；
  - **审计/复核者**：无法区分"真一致"与"同源回声"；
  - **组织**：下一轮没人再相信"独立提案"这四个字。

### R3（证据同源去重）每条 supporting_evidence 必须有 `source_identity`（kind + ref + sha/commit）；同一 source_identity 的多条引用只算 1 份证据；**票数 ≠ 证据数**。

- **规则**：`evidence_ledger.jsonl` 每条登记 `evidence_id`、`source_identity`、`provider`、`claims[]`、`independent_group`（同源组 ID）。
  裁决统计只能报「独立来源数」与「引用次数」两个分开的数；任何"5 人支持"的说法必须能回答"这 5 人引的是不是同一份材料"。
- **若违反谁受损**：
  - **真相**：重复引用被读成"多方验证"，制造假多数；
  - **少数派**：1 份反证 vs 5 次同源引用的"票数"；
  - **后来者**：回看记录会以为当时有 5 份独立证据，实际只有 1 份、且可能已失效。

### R4（少数派唯一证据强制裁决）被驳回的立场若持有其他立场没有的 `unique_evidence`，裁决必须逐条写 `unique_evidence_handled`（accepted / rebutted+理由 / out-of-scope+理由）；未处理 ⇒ 裁决不可关闭，禁止用票数直接关闭。

- **规则**：裁决书 `ruling.json` 的 `rejected[]` 每项必须带 `unique_evidence_handled[]`；"unique" 按 R3 的 `source_identity` 判定
  （该证据的 independent_group 不出现在任何未被驳回立场的证据里）。若某条 unique evidence 未被处理，裁决状态只能是 `open`，
  可升级到人裁决 —— **票数不能替代处理**。
- **若违反谁受损**：
  - **少数派**：唯一证据被票数埋掉（人点名的第三种失败模式）；
  - **裁决者**：裁决在事后被证明"漏掉关键反证"，信誉受损；
  - **全体**：错误结论被采纳的成本由所有人承担。

### R5（全过程 append-only 且可复算）辩论过程写 append-only 日志（哈希链，统一 UTC 时间戳），裁决的每条 claim 映射到证据 id；任何第三方只凭磁盘产物即可重放「谁在何时读了/写了什么、裁决是否覆盖了全部证据」。

- **规则**：`deliberation.jsonl` 事件类型见 §4；每条带 `seq/prev_sha256/ts_utc/payload_sha256`；禁止就地修改历史事件（更正=新增 `correct` 事件）。
  裁决书写 `claims[] -> evidence_ids[]`，并显式回答"哪些 process finding 影响了哪条 claim"（防止 §1-危险 3 的两个滥用）。
- **若违反谁受损**：
  - **被裁决方**：无法申诉（没有可复核的过程记录）；
  - **审计者（我）**：没有输入，只能凭转述；
  - **组织**：辩论结论不可复现 ⇒ 下次没人愿意按这个流程走；
  - **人（最终裁决者）**：被要求在不完整过程上拍板。

---

## 3. 我认为不可接受的裁决方式（2 条）

### 不可接受 1：**票决关闭**——用多数票（或加权票数）直接关闭，而不逐条回应少数派的 unique evidence。
理由：票数衡量的是"有多少人这么说"，不是"证据有多硬"；当少数派握着唯一反证时，票决关闭等于**用程序消灭证据**（人点名的失败模式③）。
我不接受把"多数通过"当作"已处理证据"的替代品；也不接受把 unique evidence 标成"已被考虑"但不写处置理由。
**可接受替代**：逐条 `unique_evidence_handled` 后再关闭；处理不了的升级到人。

### 不可接受 2：**不可复核的裁决 / 裁决先于证据冻结**——裁决依据只存在于会话记忆或口头结论；或裁决在过程日志与证据冻结之前给出；或 supporting_evidence 指向的材料没有 sha、允许事后修改。
理由：没有冻结和哈希，事后无法证明"裁决时依据的就是这份材料"；我的 `steward_self_audit` 已证明"标准变而收据旧"会让一切全绿结论失效，
辩论裁决是同一类问题。**可接受替代**：先冻结 `evidence_ledger`（含 sha），再出 `ruling.json`，再允许申诉窗口。

> 附一条**我不能接受的处理我的 finding 的方式**（虽不属"裁决方式"本身，但影响公平）：
> 把"过程违约"处理成"整场作废"或"完全忽略"两个极端。正确处置是**重开受影响的条目**并保留其余有效结论（见 R5 的 claim 映射）。

---

## 4. 我需要的证据形式（过程证据怎么留，这是过程审计的域）

> 以下文件名是提案，不等于已批准条款；Phase 5 若采纳，应把 §4 的形状变成 `team_audit.py` 新检查
> `deliberation_quality`（参照我 task-109 的做法：条款先批、检查后写、每个判据有必红 fixture）。

### 4.1 `debate/freeze.json`（Phase 0，一次写入）
```json
{
  "schema": "debate-freeze/v1",
  "question": "一句话问题陈述（冻结后不得悄悄改）",
  "acceptance_criteria": [
    {"id": "AC1", "text": "…", "observable": "什么观测算满足/不满足"},
    {"id": "AC2", "text": "…", "observable": "…"}
  ],
  "standards": [{"path": "AGENTS.md", "sha256": "…"}, {"path": "docs/guides/lead-dispatch-rules.md", "sha256": "…"}],
  "frozen_at": "2026-10-25T00:46:00+08:00",
  "frozen_by": "lead"
}
```
另：`debate/baseline_mutations.jsonl`（append-only）记录标准/问题变更：`mutation_id`、`field`、`old_sha/new_sha`、`reason`、`reopen_phases[]`、`ts`。

### 4.2 提案头（每份 `protocol-proposals/*.md` 首部，机器可读）
```json
{"proposal_id": "steward", "submitted_at": "...", "read_set": [{"path": "...", "sha256": "..."}],
 "unread_declared": ["其他成员提案"], "cross_read_events": [], "declared_role": "process-audit"}
```
Lead 在 Phase 1 关闭后发布 `phase1_submissions.json`：每份的 `sha256` + `mtime_first_seen` + 提交顺序。
> 独立性核验：① 声明与 mtime 一致；② 内容相似度异常（同一独有措辞同时出现在两份提案）⇒ 人工复核并标 `non_independent`。

### 4.3 `debate/deliberation.jsonl`（append-only、哈希链、统一 UTC）
事件类型（每条 `seq, prev_sha256, ts_utc, actor, event, payload, payload_sha256`）：
```
phase_open / proposal_submitted / evidence_registered / objection_raised /
cross_read_detected / ruling_issued / ruling_rejected / freeze / correct
```
要求：`cross_read_detected` 一旦出现，必须同时写"影响范围"（哪条 claim 受影响）；`correct` 只能追加，不得改旧行。

### 4.4 `debate/evidence_ledger.jsonl`（append-only）
```json
{"evidence_id": "ev-001", "source_identity": {"kind": "doc|commit|report|task", "ref": "...", "sha256": "..."},
 "independent_group": "src-group-1", "provider": "actor-id", "claims": ["C1"], "status": "verified|unverifiable|conflicting",
 "note": "同源组：与 ev-002 引同一材料，按 R3 只算 1 份"}
```
裁决统计必须分开输出：`independent_source_count` 与 `citation_count`。

### 4.5 `debate/ruling.json`（每条裁决可反推）
```json
{"schema": "debate-ruling/v1", "ruling_id": "...", "decider": "lead|human", "decided_at": "...",
 "claims": [
   {"claim_id": "C1", "decision": "accept|reject|conditional", "positions": ["...", "..."],
    "supporting_evidence_ids": ["ev-001"],
    "unique_evidence_handled": [
      {"evidence_id": "ev-009", "holder": "minority", "disposition": "rebutted|accepted|out-of-scope", "reason": "…"}
    ],
    "falsifiers": ["若观测到 X，则本裁决撤回"],
    "conditions": [{"assumption": "共享假设文本", "if_false": "结论失效的动作"}],
    "process_findings_considered": [{"finding_id": "SF-…", "effect": "none|reopen|evidence-discounted", "reason": "…"}]}
 ],
 "decision_ref": {"kind": "commit|decisions.jsonl", "ref": "…"},
 "rule_refs": ["docs/guides/lead-dispatch-rules.md#6"]}
```

### 4.6 我的过程审计收据 `debate/audit/steward-audit.json`
- `standards_read`（sha256，同 `steward_self_audit` 口径）+ `determinism`（§5.4，机检可复现）；
- `claims_checked[]`：逐条 verdict（`process_ok` / `process_violation` / `undecidable`）+ `rule_ref` + `evidence`；
- `undecidable_reasons[]`：明确"我判不了什么、为什么"（例如"unique evidence 是否真的 unique 需语义判断，机器只能查是否被处理"）；
- `not_read_declarations`：我未读他人提案的声明（与 §4.2 互证）。

### 4.7 Phase 5 机器判据映射（**待 Lead 批条款后实现，不先写检查**）
| 候选判据（Lead 给的参考 + 我的补充） | 处置 | 依据 |
|---|---|---|
| 裁决的 `supporting_evidence_ids` 全属同一 `independent_group` 且无独立来源 | WARN「可能同源伪多数」 | R3 |
| `rejected[].unique_evidence_handled` 缺失或为空，而被驳回立场有 unique evidence | **FAIL「少数派唯一证据未被裁决」** | R4 |
| `falsifiers` 为空（裁决不可反驳） | WARN | R5 |
| 结论依赖 `conditions[].assumption` 但未标「有条件」 | WARN | R2/§1-危险3 |
| `baseline_mutation` 存在但 `reopen_phases` 为空 | **FAIL「改题未重开」** | R1 |
| 提案 `read_set`/mtime 与 Phase1 顺序矛盾、或互读被证实 | WARN→FAIL「伪独立」 | R2 |
| `deliberation.jsonl` 断链/哈希不符/时间倒流 | **FAIL「过程不可复算」** | R5 |
| `ruling.json` 的 claim 无法映射到 evidence_ledger | FAIL「裁决无证据」 | R5 |

我会按 `task-103/109` 的既有纪律实现：**每条判据先有条款、每个新增检查先有必红 fixture**；本文件只是提案，不是已批准条款。

---

## 5. 我对本次辩论的具体要求（可直接执行的最小集）

1. **Phase 0 冻结**：`freeze.json`（问题 + 判据 + 5 个标准 sha）由 Lead 写；冻结前不开始 Phase 2。
2. **Phase 1 独立性**：每份提案首部加 §4.2 的 JSON；Lead 在 Phase1 关闭后**一次性**发布 `phase1_submissions.json`（sha + mtime + 顺序）。
3. **证据登记**：Phase 2/3 的所有论据进 `evidence_ledger.jsonl`，带 `source_identity` 与 `independent_group`；裁决统计分开报"独立来源数/引用次数"。
4. **裁决模板**：Phase 4/5 用 `ruling.json`（§4.5），至少覆盖：`unique_evidence_handled`、`falsifiers`、`conditions`、`process_findings_considered`。
5. **过程日志**：`deliberation.jsonl` append-only + 哈希链；任何更正用 `correct` 事件。
6. **审计窗口**：裁决 `ruling.json` 落盘后 24h 内我可提 process finding；**涉及 unique evidence 未处理 / 过程不可复算的 finding 使裁决保持 `open`**（不是整场作废）。
7. **角色分离**：我的产出只限过程审计与机检实现；我不对"架构哪个更好"投票，也不替裁决者写 `why`（沿用 A6 机器不创作）。

---

## 6. 我承认的局限（免得这份协议被当成"过程万能"）

1. **我能证明"独立性/处理/可复算"，不能证明"证据本身为真"**；语义真假仍需评审与人。
2. **mtime 可被操纵**（复制文件可改 mtime）⇒ 我会把"mtime 顺序"当**辅助证据**，主证据是 `sha256 + 提交顺序 + 内容互引检测`；三者矛盾时标 `undecidable` 并上报。
3. **本协议对"共享假设"只能要求标注条件、指出 falsifier，不能自动判定假设是否合理**——这是评审的活。
4. 我自己也可能犯错：我的审计收据必须可被 Lead/任何人复算（`--determinism` + sha），**不接受"相信我"**。
