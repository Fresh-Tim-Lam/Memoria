# `deliberation_quality` v0 交付报告（task-116）

> **实现**：`scripts/agent/team_audit.py::check_deliberation_quality`（commit `e6741e48`）
> **提案**：`artifacts/agent/verify/debate/PROTOCOL-v1.1-PROPOSAL.md`（F-2/F-3/F-4/F-6/F-1）
> **证据**：`artifacts/agent/verify/steward/task-116/{selftest,determinism,pre-commit-audit,post-commit-audit}.{txt,json}`
> **时间**：2026-10-25T01:1x+08:00

---

## 1. 判据 → 条款映射（先条款后检查）

| dq | 级别 | 判据 | 依据（PROTOCOL.md） |
|---|---|---|---|
| dq1 | **FAIL** | 每条证据身份 `ev:<kind>:<ref>` 合法、kind ∈ E1 六类、ref 无说明文字、目标可追（file/doc 存在；commit 存在；id 类非空） | §1 E1 / E1' |
| dq2 | **FAIL** | `rejected` 非空 ⇒ 每条被驳回立场有 `unique_evidence_handled`（顶层列表长度匹配 **或** per-item 非空） | §3 J2' |
| dq3 | **FAIL** | 每条裁决 `falsifiers` 非空 | §3 J3 |
| dq4 | **FAIL** | 每条裁决 `supporting_evidence` 非空且每个 id 可追 | §3 J1 |
| dq5 | **FAIL** | `freeze.standards` 非空、question/criteria 非空、决策标准 sha（LF 归一化）与磁盘一致；`PINNED-PROPOSALS` sha 一致 | §4 F1 / F2' |
| dq6 | **FAIL** | 辩论目录下所有文件必须 git tracked | §3 J6' |
| dq7 | WARN→FAIL | 每条裁决有 `objection_ids`（v1.1 将升级为双向覆盖） | §3 J4 / task-113 关闭条件 |
| dq8 | WARN→FAIL | 有 `evidence_ledger` 时：每条 `source_identity` + `independent_group`；缺失 ⇒ WARN（F-6 待裁决） | §1 E2 |
| dq9 | WARN→FAIL | 提案含 coverage 三表（checked/not_examined/out_of_scope） | §2 P2 |
| dq10 | WARN→FAIL | `deferred` 有期限且未超期 | §3 J2' |

**宽限**：dq7-dq10 在 `DEBATE_WARN_UNTIL=2026-11-08` 前 WARN，之后自动转 FAIL（与 §5.4/§6.5 先例一致）。

**盲区声明（不假装检查）**：`unique_evidence` 是否**真** unique、共享假设是否"合理"、证据是否**足以**支撑结论——语义判断交评审/人。

---

## 2. 必红 fixture（selftest 内，缺一不可）

| fixture | 注入 | 断言 |
|---|---|---|
| `dq1-red` | 证据写成 `ev:file:.gitignore（含 artifacts/）#L15` | FAIL 含 `dq1` |
| `dq2-red` | rejected 1 条但无 UEH（顶层 [] 且 per-item 空） | FAIL 含 `dq2` |
| `dq3-red` | `falsifiers: []` | FAIL 含 `dq3` |
| `dq4-red` | `supporting_evidence: []` | FAIL 含 `dq4` |
| `dq5-red` | `freeze.standards: []` | FAIL 含 `dq5` |
| `dq5b-red` | PINNED 里 `PROTOCOL.md` sha 改 0 | FAIL 含 `pinned sha` |
| `dq5c-tooling` | 标准条目标 `role=机检实现` 且 sha 漂移 | **不得 FAIL**，必须有 WARN「工具实现类」 |
| `dq6-red` | 提交后新增未跟踪文件 | FAIL 含 `dq6` |
| `dq-green` | 完整合规 fixture（git tracked、sha 匹配、证据可解析） | 无 FAIL（dq8/dq9 WARN 允许） |

`--selftest` 全绿；`--determinism` PASS（连跑两次除 `generatedAt` 外逐字节一致，sha `c37ede23…`，compared_findings=74）。

---

## 3. 真实产物上的运行结果（关键）

### 3.1 实现后、提交前（`pre-commit-audit.json`）
```
dq1-dq5 PASS（含 dq5 tooling WARN，见 §4）
dq6 FAIL：4 个辩论产物未 git tracked：
  PROTOCOL-v1.1-PROPOSAL.md（本任务）
  audit/pre-commit-audit.json（本任务证据，已移出辩论目录）
  position/agent-arch-position.md（并行任务 task-115）
  position/lead-source-verification.json（并行任务 task-115）
```
⇒ **dq6 在真实数据上确实会红**（不是只在 fixture 里红）。

### 3.2 提交本任务产物后（`post-commit-audit.json`）
```
dq1-dq5 PASS
dq6 FAIL：2 个未跟踪文件（均属并行 task-115，不在本任务写域）：
  artifacts/agent/verify/debate/position/agent-arch-position.md
  artifacts/agent/verify/debate/position/lead-source-verification.json
```
**结论**：本任务 6 条 FAIL 判据中 **dq1-dq5 已 PASS**；**dq6 剩余 FAIL 是并行任务的产物未提交**（J6' 的预期行为），
等 Lead/agent-arch 提交 `position/` 后自动转绿。**我没有替别人提交越权文件，也没有把 dq6 降级**。

基线（post-commit）：`team_audit.py` **FAIL=2（均为上述 dq6）/ WARN=50 / INFO=22**；其余检查无回归。

---

## 4. 一个实现决定（需 Lead 知晓/可选裁决）

`freeze-v2.json` 同时冻结了 5 个「标准」，其中 `scripts/agent/team_audit.py` 的 role 是「机检实现」。
task-116 改了 team_audit.py ⇒ 其 sha 必然漂移。若 F1 字面执行（任何冻结标准变 ⇒ FAIL），**任何机检实现提交都会让 dq5 假红**（自指悖论）。
v0 采取：**决策标准**（AGENTS/rules/lessons/org）sha 不符 ⇒ FAIL；**tooling**（role 含"机检/实现"）漂移 ⇒ WARN + v1.1 建议正式分离。
**替代方案（如果你更倾向严格 F1）**：Lead 记一条 `baseline_mutation`（reopen=[]，reason=机检实现随 task-116 更新），我改回一律 FAIL。二者我都能实现，**我选了不阻断裁决的 WARN**，因为 tooling 不是"裁决依据"。
已写进 `PROTOCOL-v1.1-PROPOSAL.md §7`。

## 5. F-6 判断（`evidence_ledger` 适用范围）

**架构辩论起强制，本协议辩论不追溯。** 理由：① 本轮证据已 pinned 且进 git，台账新增信息近零；
② 架构辩论有 `ev:bench:*` 与外部资料，E2/M2 才有真实消费者；③ 追溯=重写冻结产物（违反 append-only）；
④ 不强制则 M2「independent_roots>1」无法执行 ⇒ 义务必须落在唯一有意义的阶段。
落地建议：`freeze` 增 `evidence_ledger_required_from` 标记；声明后 dq8 才是 FAIL。详见 v1.1 提案 §4。

## 6. v1.1 提案 5 项 + 顺带发现

| # | 项 | 要点 |
|---|---|---|
| 1 | F-2 UEH schema | 顶层列表 + `rejection_index/disposition/reason/deadline`，无 rejected 必 `[]`；废弃 per-item 布尔 |
| 2 | F-3 objection_ids | Phase 3 分配 `OBJ-<member>-<n>`；Phase 4 双向覆盖；生成 `ruling-index.json` |
| 3 | F-4 rules-index | rule_id 全局唯一（B4.a–f，**现在 B4 重复 6 次**）；PROTOCOL 变 ⇒ 必须重生成（`protocol_sha256_lf` 对账）；统一"45 条"口径（一级+子规则） |
| 4 | F-6 evidence_ledger | 见 §5 |
| 5 | F-1 教训 | Phase 0 出口门禁：freeze 必须过 dq5 才允许开 Phase 1（不许事后补） |

顺带发现（待裁）：`PINNED-PROPOSALS.json` 未含 `freeze-v2.json`/`rules-index.json` 自身 sha；
"冻结物五件套"需定义（避免自指可用 git blob sha）。

## 7. 复跑

```powershell
python scripts/agent/team_audit.py --selftest
python scripts/agent/team_audit.py --determinism
python scripts/agent/team_audit.py --json   # 看 check=deliberation_quality
```
