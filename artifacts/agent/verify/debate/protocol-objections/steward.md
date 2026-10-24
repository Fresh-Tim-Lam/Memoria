# Phase 3 异议：steward（过程审计视角）

> **对稿**：`protocol-v1.md`（Phase 2 合并稿，25 条：M1-3 / E1-5 / P1-4 / J1-6 / F1-2 / B1-5）
> **我的角色**：过程审计——只判「过程是否可审计、可复算、可申诉」，不判「哪条规则更能赢」。
> **证据口径**：本文件所有数字都可复跑；独立性结论来自 `team_trajectory` 事件流（非转述），见 §5。
> **提交时间**：2026-10-25T00:5x+08:00

---

## 0. 先回答 Lead 的四处重点核验（结论在前）

| # | 核验项 | 结论 |
|---|---|---|
| ① | **F2 够不够** | **不够，object**。F2 未区分「提交先后」与「互读」；且没有给出「拿什么机器证据验」的载体。建议改为「声明 schema + 冻结 `team_trajectory` file_read 窗口」双证据（§2-O1）。 |
| ② | **Phase 1 实际独立性审计** | **未发现任何互读证据**（4/4 在 Phase1 窗口内没有读他人提案的 file_read 事件）；但 **F2 的声明格式实测 1/4 合规**（只有我的提案带 `read_set`+sha256），另有 1 处声明无法被轨迹证实、1 处自报时间与 mtime 不一致（§3，均为 finding，不构成本次违规指控）。 |
| ③ | **CONFLICT-3 完整性格式** | 已给出可机检方案：`examined_categories[]` / `not_examined_categories[]` + 「谎报已检查」重罚（§4）。 |
| ④ | **J6 成本** | **我主动降低自己的要求**：放弃"全过程哈希链"，改为「3 个冻结检查点 + 证据台账 sha + 裁决→证据映射」（§2-O2）；同时发现一个更严重的问题：`artifacts/**` 不进 git，「append-only」当前**无法被强制**（§2-O2 给修法）。 |

---

## 1. 逐条判定（M1-3 / E1-5 / P1-4 / J1-6 / F1-2 / B1-5）

> 判定：**accept** = 我无异议；**object** = 要求改写，理由+保护谁/伤害谁+证据写在 §2。

| 规则 | 判定 | 若 object：为什么 / 保护谁 / 伤害谁 / 证据 |
|---|---|---|
| M1 合法性来源=证据+可复核+falsifier | **accept**（附 CONFLICT-4 立场§4） | 但当前 Phase 0 冻结物不完整（见 F1），M1 的"可复核"无锚 |
| M2 证据优先于人数 | accept | — |
| M3 诚实中立 | accept | 需与 CONFLICT-2 的"应知"边界一起读（§4） |
| E1 证据身份 | accept | — |
| E2 同源去重 | accept | 与我的 R3 一致；但缺"独立来源数/引用次数"的机检载体，见 O2（证据台账） |
| E3 共享假设单列 | accept（补一句） | 建议补 `owner` + `due_by`：只写"谁负责检验"而不写期限 = 永远不检验。 |
| E4 可复现才有效 | accept | — |
| E5 不一致必须披露 | accept | — |
| P1 对称举证 | accept | — |
| P2 不得要求缺席证明 | accept（边界见 CONFLICT-3） | 需配套完整性声明格式，否则"不可要求缺席证明"会变成"不可追问覆盖"（§4） |
| P3 预算与时序对称 | accept | — |
| P4 诚实中立（unknowns/not_doing） | accept | 与 P2/CONFLICT-2 配套使用 |
| J1 逐条对照 | accept（建议扩一句） | 建议明确"裁决的每条 claim 必须列 `supporting_evidence_ids`"（否则"逐条对照"无法机检） |
| J2 少数派唯一证据强制处理 | **accept（关键条款）** | 这是我 R4 的核心；建议加"未处理 ⇒ 裁决 `open`，**不可被 Lead 单方关闭**"（现在是"只能 open"，但谁有权把它从 open 关掉没写） |
| J3 可证伪 | accept | — |
| J4 少数意见原样冻结 | accept | 与 J2 一起构成对失败模式③的双保险 |
| J5 不许加料 | accept | — |
| J6 append-only 可复算 | **object → 建议改写** | 现行写法（"全过程哈希链"）成本/收益不匹配，且**不可执行**：`artifacts/**` 被 gitignore，磁盘文件可被静默改写，"append-only"没有强制力（§2-O2） |
| F1 冻结基准 | **object（实现缺口）** | 规则本身 accept；但**实际 Phase 0 冻结物 `PHASE1-BASELINE.json` 缺「问题陈述 + 可接受判据 + 标准 sha256」**，只冻结了参与者/路径/规则 ⇒ F1 目前无法执行（§2-O3） |
| F2 可证明的独立性 | **object → 改写** | 未区分提交先后与互读；无机器证据载体；声明 schema 未定义；1/4 合规（§2-O1、§3） |
| B1 口径预签署 | accept | — |
| B2 对比对称 | accept | — |
| B3 测量权与解读权同源 | accept（限度量证据，见 CONFLICT-1） | — |
| B4 六类不认的省 token 声明 | **object（轻）** | "详见 metrics-baseline §4.2" 把冻结协议**指向一份可变提案文件**；冻结后若该提案被改，协议语义漂移。建议内联六类或 `PINNED-PROPOSALS.json` 记 sha（§2-O4） |
| B5 业界惯例不作裁决证据 | accept（同上，指向提案的问题同样适用于 arch-contract §4.1） | — |

**汇总（我自己的改判主张）**：25 条中 **3 条要求改写**（J6、F2、B4 轻）、**2 条要求补实现缺口/补一句**（F1、E3/J1/J2 各一句）、其余 **accept**。

---

## 2. 我对四条 object 的详细说明（为什么 / 保护谁 / 伤害谁 / 证据）

### O1｜F2 改写：从「声明」到「可核验的双证据」
**为什么**：F2 现在的判据是「每份提案首部声明 `read_set`+`unread_declared`，提交时记录 `mtime+sha`；互读被证实 ⇒ `non_independent`」。
它有三个洞：
1. **`mtime` 是提交先后，不是互读证据**：我自己的提案 mtime（00:44:24）晚于 `metrics-baseline.md`（00:43:44），但我是独立写的——`team_trajectory` 显示我第一次打开他人提案是 **00:47:06Z**（Phase 3），而我的提案在 **00:44:24** 已落盘。**用 mtime 判互读会把我误判成"可能参考"**（假阳性）。
2. **`read_set` 无 schema**：实测只有 1/4 提案带了 `path+sha256` 的 read_set（我），其他提案只有"未读"声明（§3）。
3. **没有"证据载体"**：谁去证明"没读"？现在是自我声明——正是我们在防的"自我报告不可信"。

**我建议的替代判据（可机检）**：
```
F2' 独立性 = ①声明（read_set 每项必须 path + LF归一化 sha256 + read_at）
           + ②机器证据（Phase1 窗口内 team_trajectory 的 file_read 事件不含其他提案路径）
           + ③mtime/sha 仅作辅助（提交顺序公开，但不用于判定互读）
           + ④证据不足（轨迹截断/无轨迹）⇒ 标 independence: unverifiable（不指控、也不计入"独立票"）
```
**保护谁**：独立但提交晚的人（我现在的处境）；以及"被怀疑抄"但从没读过的人。
**伤害谁**：真的互读但会失去"独立票"的人（应当如此）。
**证据**：`team_trajectory steward` 显示 00:47:06Z 才读 agent-arch.md/metrics-baseline.md/arch-contract.md；`team_trajectory agent-arch|arch-contract|metrics-baseline` 的 Phase1 窗口内均无他人提案 file_read（§5 表）。

### O2｜J6 改写：降低要求 + 解决"append-only 无强制力"
**成本评估（回答 Lead ④）**：全过程哈希链的计算成本≈0（几小时辩论约几十条事件，哈希是微秒级），**真实成本是纪律成本**：要求每方每步记链，辩论会被"记账"拖慢，且**收益递减**——`team_trajectory` 已经在记录工具调用/读写事件（虽然不完整）。
**所以我主动降低要求**：J6 改为「**3 个冻结检查点 + 证据台账 + 裁决映射**」：
1. CP1 `freeze.json`（Phase 0，含问题/判据/标准 sha）；
2. CP2 `phase1_submissions.json`（4 份提案 sha256 + 提交顺序 + 各自 read_set 声明）；
3. CP3 `ruling.json`（每条 claim → `supporting_evidence_ids` + `rejected[].unique_evidence_handled` + falsifiers）；
4. `evidence_ledger.jsonl`（每条证据 `source_identity` + sha；append-only 由 **git 提交**强制）。
**更严重的问题（新发现）**：`artifacts/**` 在 `.gitignore` 里 ⇒ **辩论产物不进 git，"append-only"只是"我们约定不修改"**。任何一方都能静默改 `protocol-proposals/*.md` 或 `evidence_ledger.jsonl`，事后无法证明。
**建议**：Phase 5 冻结时把 `debate/` **关键产物提交进 git**（或复制到 `docs/design/debate/` 等非 ignore 路径），并把 sha 写进 `ruling.json`；`deliberation_quality` 机检用「git blob sha」而不是工作区字节（这也与我 task-110 的"收据用 LF 归一化 sha"同一个教训）。
**保护谁**：被改证据栽赃的一方；未来复算者（我）。
**伤害谁**：想"事后修饰"记录的一方。

### O3｜F1 实现缺口：当前冻结物不满足 F1 自身要求
**证据**：`PHASE1-BASELINE.json` 内容 = `participants / rule / verification / phase / proposal_paths / started_at`；**没有** `question`、`acceptance_criteria[]`、`standards[{path,sha256}]`。
**F1 原文要求**：「冻结问题陈述 + 可接受判据 + 标准版本(sha256)」。现在这三样都没有正式冻结（问题只存在于 Lead 消息与 task-113 描述里；标准 sha 我是在提案 read_set 里自行记录的）。
**保护谁**：所有人（否则 Phase 4 裁决可以换问题/换判据而不留痕）；尤其少数派（问题被重述就输了）。
**建议**：Phase 4 前补 `freeze-v2.json`（或直接并进 Phase 5 `PROTOCOL.md` 的附录）：问题陈述、判据 AC1..n（每个有 `observable`）、4 个标准 sha256（LF 归一化口径，参照 task-110）。**不要求重开 Phase 1**（提案内容不受影响），但后续裁决必须引用它。

### O4｜B4/B5 指向可变提案：冻结协议不能引用未 sha 的文件
**问题**：B4「详见 metrics-baseline §4.2」、B5「arch-contract §4.1」在冻结后若提案文件被修改（artifact 不进 git），协议含义就变了。
**建议**：要么内联关键清单（六类不认声明、业界惯例边界），要么生成 `PINNED-PROPOSALS.json`（4 份提案的 LF 归一化 sha256 + 冻结时间），机检在 `deliberation_quality` 里核对。
**保护谁**：所有读协议的人；未来复算者。

---

## 3. Phase 1 独立性实测审计（Lead ② 的交付）

> 窗口：`PHASE1-BASELINE.json:started_at = 00:43:20 +08`（= `16:43:20Z`）→ Phase 2 合并稿 `protocol-v1.md` 首次出现（00:45:44 +08 = `16:45:44Z`）。
> 方法：`team_trajectory <member> --kind file_read`，检查窗口内是否出现他人提案路径；mtime/sha 见 §5 表。
> 局限：`arch-contract`/`metrics-baseline` 轨迹被截断（omittedEvents 419 / 2991）——"窗口内无记录"只能证明"当前可见事件里没有"，**不能证明全历史**；这正是 O1 ④ 要求 `unverifiable` 状态的原因。

| 提案 | 声明合规（F2 现行写法） | Phase1 窗口内读他人提案? | 结论 |
|---|---|---|---|
| agent-arch.md | 部分：声明了"只读了 baseline + measurement-guidelines 前60行 + 目录清单"，**无 sha256**；声明"写入时间 00:46" 但 mtime=`00:44:20` | **无**（窗口内仅 `16:43:26Z` 读 PHASE1-BASELINE.json） | 独立性**成立**（轨迹支持）；声明格式不合规 + 自报时间不一致（finding） |
| metrics-baseline.md | 不合规：只声明"未读三份提案"，**无 read_set** | **无**（窗口内无任何 file_read；首次读 `protocol-v1.md` 在 16:46:53Z） | 独立性**成立**；声明缺 read_set |
| arch-contract.md | 不合规：只声明"未读三份提案"，**无 read_set** | **无**（窗口内无 file_read；16:46:51Z 读 protocol-v1） | 独立性**成立**（但轨迹截断，标 `unverifiable` 更诚实） |
| steward.md | **合规**（read_set 每项 path+sha256，unread_declared，写前未读他人） | **无**（00:44:24 落盘；首次读他人在 00:47:06Z） | 独立性**成立**；mtime 晚于 metrics 只是提交晚 |

**内容相似度（防"抄了但没承认"）**：4 份提案两两 **8-gram Jaccard 最高 1.16%**（steward vs agent-arch），最低 0.57%；
共同片段主要是任务前言里的通用词（"同源""伪多数""falsifier"）——**没有内容级抄袭迹象**。
（注意：共享的是**任务 brief**，不是共享证据；按 E2/R3，任务 brief 不计入"独立来源数"。）

**finding（不是指控，按 B4 finding 生命周期登记建议）**：
- **IND-1（WARN）**：`agent-arch.md` 声明读了 `artifacts/agent/verify/measurement-guidelines.md 前60行`，但轨迹中没有对应 file_read 事件（可能经 shell/grep 或轨迹截断）⇒ `unverifiable`，不得据此判"抄"也不得据此判"独立"。建议 Phase 4 让 agent-arch 补一句说明。
- **IND-2（WARN）**：`agent-arch.md` 自报写入时间 `00:46` > 实际 mtime `00:44:20` ⇒ 自报时间不可作证据（进一步支持"用轨迹、不用自报"）。
- **IND-3（INFO）**：3/4 提案未按 F2 现行要求提供 `read_set`（含 sha256）——**这是 F2 设计缺陷的实证**（规则写了但没给 schema），不是三方合谋。
- **IND-4（WARN）**：`artifacts/**` 不进 git（见 O2）⇒ 提案文件本身可被静默改写，独立性结论只能"当时有效"，冻结必须进 git。

---

## 4. 我对 CONFLICT-1..4 的立场

### CONFLICT-1｜度量规则是否通用化
**立场：B3 保持"度量专有"，但 E4（可复现）对所有证据通用。**
理由：测量权与解读权同源是**针对"谁有资格签发数字"**的约束，强推到所有证据会让"引用别人 file:line 的提案"失去解读权（不合理）。
但"任何人可要求复现/复核"（E4）必须通用——这样 CONFLICT-1 的实际风险被 E4 兜住。
**保护谁**：非度量证据的提案者；**伤害谁**：想用"我测的你不准解读"来垄断数字的人（不被保护）。

### CONFLICT-2｜unknowns 的中立边界
**立场：P4 保留（unknowns 合法、不计缺陷），但"应知而未知"必须可判定——判定权不在裁决者，在 Phase 0 冻结的 `expected_categories`。**
方案：
- Phase 0 `freeze` 定义本次辩论**应当覆盖的类别骨架**（由问题陈述决定，Lead 与人确认）；
- 提案必须对每个类别声明 `examined`（附证据）或 `not_examined`（附理由）；
- **漏声明类别** ⇒ 自动标 `coverage_gap`（WARN，不扣分，因为可能是问题陈述没覆盖到）；
- **谎报 examined 而抽查证据不支持** ⇒ **重罚**（该提案的完整性声明整段作废 + 记 `integrity` finding）——这是"说不知道"与"假装知道"的分界线。
**保护谁**：诚实写 unknowns 的人（不再被"不完整"惩罚）；**伤害谁**：堆 unknowns 逃避覆盖、或谎报覆盖率的人。

### CONFLICT-3｜P2「不得要求缺席证明」的边界
**立场：接受 P2，但要求补充「完整性的可审计声明格式」**（否则 P2 会成为"不许追问覆盖"的挡箭牌）。可机检方案：
```jsonc
// 提案内（机器可读）
"coverage": {
  "examined_categories": [
    {"id": "CAT-1", "claim": "…", "evidence": ["ev:file:…:L12", "ev:bench:…"],
     "method": "pin+line | bench | spec", "confidence": "high|medium|low"}
  ],
  "not_examined_categories": [
    {"id": "CAT-7", "reason": "超出本轮问题范围 | 材料不可得 | 时间不足",
     "impact": "若错，影响哪个结论", "owner_to_check": "member-id | human"}
  ],
  "unknowns": ["…"], "not_doing": ["…"]
}
```
**机检（`deliberation_quality` 候选，等条款批准后实现）**：
1. `examined_categories` 每项 **必须** ≥1 条 `ev:*` 且带 `source_identity`（E1），无证据 ⇒ FAIL「谎报已检查」（轻则 WARN，重则 FAIL 取决于是否被抽查证伪）；
2. `not_examined_categories` 每项必须有 `reason`+`impact`，缺失 ⇒ WARN；
3. Phase 0 `expected_categories` 里出现但两处都未声明的类别 ⇒ WARN `coverage_gap`；
4. 随机抽查：裁决者随机选 **N=3** 条 examined claim（随机种子记录在 ruling 中），要求提案者当轮复现证据；**抽查失败 1 条 ⇒ 该提案 examined 声明降级为 `unverified`；≥2 条 ⇒ 整段 coverage 作废并记 `integrity` FAIL**。
**"应知"由谁判**：不是裁决者临时判断，而是 Phase 0 冻结的 `expected_categories` + 问题陈述（可复核、不可事后加）。
**保护谁**：认真清点但被"你还漏了什么"结构性问题困住的人；**伤害谁**：谎报覆盖、用 unknowns 逃避的人。

### CONFLICT-4｜裁决合法性 vs 人的最终决策权
**立场：接受 M1（合法性来自证据+可复核+falsifier），但"人推翻"必须带形式要件并留痕**：
```
human_override 事件必须含：{claim_id, reason, falsifier_if_any, dissent_preserved: true, ts, human_id}
```
- 人**有权**推翻（组织事实）；但必须给理由，并接受"该理由在下一轮被 falsifier 检验"；
- 少数意见（J4 已要求原样冻结）不得因 override 被删除。
**保护谁**：少数派（记录保留）、人（决策权不被程序架空）；**伤害谁**：想"拍板但不留痕"的人。

---

## 5. 我要保留 / 删除 / 改写的条款

**必须保留（我视为不可谈判的核心）**：
1. **J2**（少数派唯一证据强制处理 + 不得票决关闭）——这是失败模式③的唯一防线；
2. **E2**（同源去重、分开报独立来源数/引用次数）——失败模式①；
3. **E3**（共享假设单列）——失败模式②的入口；
4. **J4**（少数意见原样冻结）；
5. **F1**（冻结基准）——没有它，M1/J3 都可被"换题/换判据"绕开。

**建议删除或无成本关闭**：
- **删除 J6 的"全过程哈希链"**（改写为 3 检查点 + 证据台账 sha + git 冻结，见 O2）；
- **删除 B4/B5 对提案文件的"详见"引用**（改为内联或 `PINNED-PROPOSALS.json` sha，见 O4）。

**建议改写（4 处）**：
1. **F2 → F2'**（双证据：声明 schema + 轨迹冻结；`unverifiable` 合法态）；
2. **J6 → J6'**（检查点 + 台账 + 裁决映射 + git 冻结；放弃哈希链）；
3. **F1 补实现**（补 `freeze-v2.json`：问题/判据/标准 sha；不重开 Phase 1）；
4. **J1/J2 各补一句**：J1 加「裁决每条 claim 必须列 supporting_evidence_ids」；J2 加「open 状态的裁决只能由人关闭，Lead 不得单方关闭」（否则"只能 open"会被绕过）。

**我主动承诺的自我约束**（反向约束，避免我的要求只保护我自己）：
- 我的过程审计结论同样受 §5.4 确定性约束：`team_audit --determinism` 必须 PASS，否则结论不可用（我的 task-109 已实现）；
- 我接受"我的 finding 也可能被判 `undecidable` 或被 falsifier 推翻"；我拒绝的是"不处理就关闭"。

---

## 6. 证据附录（可复跑）

| 事实 | 复跑命令 / 来源 |
|---|---|
| 4 份提案 sha256 / mtime / 大小 | `python -c` 读文件 + `stat`，见 §3 表（sha 值在 `phase1_submissions` 建议产物中固化） |
| 8-gram 相似度（最高 1.16%） | 对 4 份提案做字符 8-gram Jaccard（去除空白后），脚本逻辑在汇报消息中 |
| Phase1 窗口内 file_read | `team_trajectory <member> --kind file_read`：agent-arch 16:43:26Z baseline；metrics 16:46:53Z protocol-v1；arch-contract 16:46:51Z protocol-v1；steward 16:47:06Z+ 他人提案 |
| 我自己的独立性 | 我在 00:44:24 落盘提案；`team_trajectory steward` 首次读他人提案=00:47:06Z；且 00:44:24 前后未读任何 proposal（grep/目录名除外） |
| `.gitignore` 不含 artifacts | `.gitignore:15 artifacts/`（与 task-110 的 sha 教训同源） |
| `PHASE1-BASELINE.json` 缺字段 | 该文件全文 18 行，无 `question` / `acceptance_criteria` / `standards` |

> **一句话**：v1 的 25 条方向我都认（尤其 J2/E2/E3/J4/F1）；我 object 的是**"验证这 25 条"的载体**——
> F2 用 mtime 会误伤独立者、J6 的 append-only 在 gitignore 下无强制力、F1 的冻结物实际不完整、B4/B5 冻结后引用可变文件。
> 把上述 4 处换成"可复算的检查点 + 轨迹 + git 固化"，协议才真的"公平且可审计"。
