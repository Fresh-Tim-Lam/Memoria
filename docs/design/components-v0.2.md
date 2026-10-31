# 组件库规范 v0.2.1（设计资产 · canonical snapshot）

> **canonical snapshot（v0.2.1，2026-10-31；以下 sha256 为权威版本身份）**
> - `docs/design/component-registry.v2.json`：`97b5d8c3a3c643d4b96b0fc827766641a10283dc48c1894fb1e8f351a39c8446`（95,972 B；dataVersion `0.2.1`；status accepted）
> - `docs/design/component-registry.schema.json`：`bd4d317705e52663d1210f21e1cb8d4de4422339c4831b6967c5e0ebc89a5cb1`（16,955 B）
> - `docs/design/todo-requirement.schema.json`：`a603b4ed309064b4010de1c98d6d7429f731a4251c22dd96a37e5be9d68fbc02`（3,080 B）
> - `docs/design/meta-protocol-v0.2.md`：`e5b6cacc435d7850651eed28543e4f93fe51cc37cc45626002745f5592cbe5ee`（13,506 B）
> - `docs/design/component-classification.cases.json`：`d7ce39e6a0816484ab28ac09f4c6ec1e2548825df19c94e4b6a2176045c51a82`（5,840 B；含 acceptGap canonical 5 条）
> - `docs/design/components-v0.2.md`（本文件）：**自身 sha256 由 Lead 交付回执给出**（避免自引用；v0.2.1 落盘后计算）
> **Status: accepted 2026-10-31（Lead 冻结；M-1 复评 P0 13/13 PASS，见 `SEMINAR-COMPONENTS-M1/REVIEW-v0.2.2-final.md`）**
> **状态**：accepted（2026-10-31；M-1 复评 P0 13/13 PASS，golden cases canonical 31 机跑 PASS + 1 MANUAL；见 REVIEW-v0.2.2-final.md）
> **依据**：Lead 2026-10-31 P0-1…P0-5 与复评裁决；`SEMINAR-COMPONENTS-M1/objections.md`（32 条）+ `REVIEW-v0.2.md`（剩余 4 项）+ `golden-cases/`（31 条）；`INBOX-20261030-01`。
> **Owner**：`plugin-todo-owner`｜写域：`docs/design/**`、`artifacts/agent/plugin-design/**`｜**不 commit**（Lead 审后提交）。
> **v0.2 → v0.2.1 关系**：v0.2（6 文件，快照已由复评核验）；v0.2.1 修复 A-01/A-04/C-02/C-03；v0.1（`docs/design/components-v0.1.md` + `component-registry.v1.json`，Lead commit `b28c6cf7`）保留历史。tracked 状态：v0.1 已 tracked；v0.2.1 **待 Lead `git add` + commit**（本组不写 tracked）。

---

## 1. 32 条异议 → v0.2 修订对照

| 编号 | 异议摘要 | v0.2 修订 |
|---|---|---|
| A-01 | kind=tool 名不副实 | **v0.2.1**：4 个已落地脚本组件改 `callable:true` + `executor.kind=tool` + `entrypoint=scripts/agent/comp_*.py` + `argsSchema/returnsSchema`（见 §4 清单）；其余 16 个 `callable:false`+role/manual+SOP。schema 条件强制（callable⇒tool+args/returns；manual⇒role/manual+sopRef） |
| A-02 | reuse=4 过度声明 | 新增 `reuseKind∈{callable,template,role,convention,manual-sop,none}`；4 个 reuse 均标 role/template（非 callable），文档 §3 措辞改为"可参照/人工执行" |
| A-03 | I/O 不可接 | `typeVocabulary`（25 种受控类型：primitive/enum/object/array/ref）+ 所有 outputs 必填 `schemaRef`（`#/typeVocabulary/<type>`，结构化类型内联 schema）；`requirement-completer` 的 trace 改为 **7 列** |
| A-04 | 自举不可行 | `acceptGapPolicy`（registry 根）+ `workflow-composer` 契约：missing 组件进入工作流必须产出 acceptGap（componentId/ownerRole/reason/expiry/degradedTo=manual-sop），降级人工 SOP、不阻塞；每流 ≤4 条。**v0.2.1**：`validate_registry_v2.py --check acceptGap` 已实现，**acceptGap canonical 5/5 PASS**（全可用 PASS / 缺组件无 gap FAIL / gap 完整 PASS / gap 缺字段 FAIL ×2：GC-04-04 缺 ownerRole、GC-04-05 缺 degradedTo） |
| A-05 | 锚绑定动态成员名 | 新增 `roleTemplates`（duty/durable/spawn{domain,group,workKind}）；组件 `ownerRole` 只引职责名，不写死 teammate id |
| A-06 | 判定可击穿 | META v0.2 §2/§5：`hasVersion` 不单独触发 release；"修复某版本回归"→defect-fix；"部署"→infra-change（无版本交付）；10 条 golden cases 落文件 |
| A-07 | 审批无记录 | preconditions 支持 `check.kind=approved`（args.ref=team/decisions.jsonl）+ `manual:true`；无机制的显式标 manual |
| A-08 | sideEffects/idempotent 不足 | sideEffects 改为 `{kind,target,reversible}`；idempotent 改为 `{value,dedupeKey}` |
| B-01 | 无 schema/校验器 | 新增 `component-registry.schema.json`（draft 2020-12）+ registry 根 `$schema`；校验/交叉引用脚本见 §7（steward 的 TD-01 承接正式校验器） |
| B-02 | preconditions 全散文 | 每条 precondition 必带 `check` 或 `manual:true`（schema anyOf 强制）；check.kind ∈ file-exists/approved/author-not-in/env/schema-valid/human-review/custom/cross-check |
| B-03 | failureStates 无检测/恢复 | 改为 `{id,detect{kind,args},recover{action,ownerRole,retry},severity}`；HOP_BLOCKED→route-via-lead；BOARD_FULL→排队+Lead 清位 |
| B-04 | ref 混散文 | `ref` 结构化：`{kind:path\|tool\|role\|doc\|missing, path?,anchor?,tool?,role?,expected?,note?}`；缺失写 kind=missing+expected |
| B-05 | 自定义 type DSL | `typeVocabulary` 受控词汇（text/markdown/path/path-list/json-object/json-array/member-ref/component-id/component-id-list/registry-file/task-category/priority/reuse-decision/questions-brief/gap-record/trace-rows/evidence-list/handoff-package/user-summary/workflow-plan/matrix-rows/analysis-doc/sop-id/gate-result/workflow-analysis） |
| B-06 | reuse 口径冲突 | 唯一权威 `reuseDecision∈{reuse,complete,new}`；`matchedExisting[].decision` 仅作证据（不参与聚合）；数据已对齐（reuse 4/complete 11/new 5） |
| B-07 | 缺执行/权限/端口映射 | 新增 `ownerRole/writeScope/permissions`；`composesWith` 改对象 `{targetId,mapping:[{fromOutput,toInput}],optional?}`；文档 §3 给"另一 agent 能否接"判据 |
| B-08 | 版本/生命周期不足 | 根 `schemaVersion=2.0.0` + `dataVersion=0.2.0`；组件 `version/interfaceVersion` + `lifecycle{since,reviewedBy?,supersedes?,deprecatedAt?}` |
| B-09 | 验收不可执行 | golden cases 文件 + 校验脚本（`tools/validate_registry_v2.py`）+ 本文件 §7 命令；META v0.2 §7 验收改为"跑 cases 10/10" |
| C-01 | 协议 id 不合法/两个 id | 元协议文档 id=`doc.meta.task-classification`；候选注册 id=`workflow-task-classification`（合法 kebab，未注册）；命名规则 §2 明确 comp./cls./doc. 不进 protocols |
| C-02 | 锚点失效 | **v0.2.1 实测**：全部 ref 改为结构化可解析形式（`#§N`/`#Lx-Ly`/path）；**锚点审计 `refs=55 failures=0`**；修正 6 处：user-report→`docs/design/plugin-todo-inbox.md#L9-L9`、task-classifier→components-v0.2 `#§4`、reuse-judge→`#§5`、naming→docs-management `#§3`、inbox-digester→TODO `#§1`、seminar-runner→SEMINAR-M1 `#§7`；不存在的 `team-plugin-migration.md` 不再引用 |
| C-03 | "tracked"不成立 | **v0.2.1**：6 个 v0.2.1 文件已就绪（当前 `git status` 仍为 `??`，**待 Lead `git add`+commit**，本组不 commit）；artifacts 证据副本 **6/6 已补**（含 `components-v0.2.md`），校验器断言 byte-identical |
| C-04 | 三命名空间无登记 | registry `namingRule.namespaces[]`：comp./cls./doc. 不注册进 protocols；tool./kebab 可注册；含 pattern 与用途 |
| C-05 | META/COMPONENT 状态不一致 | META v0.2 §8 全部标已裁/未裁；本文件 §9 同源；naming-convention 状态改 partial（规范已落，校验器待 TD-01） |
| C-06 | naming-convention 仍 missing | registry：`status=partial`、`executor.kind=role`、`reuseDecision=complete`；校验器缺口留在 gaps（GAP-B01-CHECKER） |
| D-01 | 缺用户可读汇报 | 新增 `comp.user-report`（user-summary 结构化：做了什么/证据/未决/代价/下一步；`phase-gate` 输出连到它） |
| D-02 | 缺研讨任务书生成 | 新增 `comp.seminar-brief-author`（rawRequest+corpus → questions-brief/proposerPlan；模板=SEMINAR-M1-QUESTIONS.md） |
| D-03 | 缺 todo 需求规范 schema/校验 | 新增 `docs/design/todo-requirement.schema.json` + `comp.todo-requirement`（写入前/消化前校验；字段：title/source/复现/证据/期望/验收/owner/writeScope/优先级/关联 INBOX/status） |
| D-04 | 缺组件库治理 | 显式缺口 `GAP-D04-GOVERNANCE`（manual SOP：steward 按评审→入库→弃用流程人工执行；后续票） |
| D-05 | 缺独立性核验 | `GAP-D05-INDEPENDENCE`（manual SOP：逐字声明+文件读审计+主持人工核验）；seminar-runner precondition 已写 manual |
| D-06 | 缺需求-证据矩阵 schema | `GAP-D06-MATRIX`（manual SOP：matrix-rows 类型手填，TD-12 前）；design-author→requirement-verifier 映射已建 |
| D-07 | 缺文档归位闭环 | `GAP-D07-DOCS-PLACEMENT`（manual SOP：inbox-digester 输出后按 docs-management 人工归位+索引） |
| D-08 | 记忆型无存储/检索 | `GAP-D08-MEMORY-STORE`（manual SOP：artifacts 文档+后续接轨迹 v2/memory card 的票） |
| D-09 | 正反案例库无来源 | `GAP-D09-CORPUS-CASES`（manual SOP：URL+访问日期+许可；来源清单待补） |

---

## 2. 命名规范 v0.2

### 2.1 命名空间表（C-04）

| 前缀/形式 | 用途 | 正则 | 可注册进 `team/protocols.json` |
|---|---|---|---|
| `comp.` | 组件 id | `^comp\.[a-z0-9]+(-[a-z0-9]+)*$` | **否** |
| `cls.` | 任务定性分类 id | `^cls\.[a-z0-9]+(-[a-z0-9]+)*$` | **否** |
| `doc.` | 文档内 id（元协议等） | `^doc\.[a-z0-9.]+$` | **否** |
| `tool.` | 内置协议 id | `^tool(?:\.[a-z][a-zA-Z0-9]*)+$` | **是**（内置） |
| kebab | 团队自订协议 id | `^[a-z][a-z0-9-]{2,63}$`（如 `workflow-task-classification`） | **是**（需登记） |

**规则**：①组件/分类/文档 id 不得冒充协议 id；②要进协议注册表的 id 必须匹配 `schema/team-protocols.schema.json` 的 pattern（实际路径：`artifacts/agent/plugin-design/schema/team-protocols.schema.json`）；③元协议文档 id=`doc.meta.task-classification`，候选注册 id=`workflow-task-classification`（未注册）。

### 2.2 文件与字段
- 文件/目录：kebab-case（`docs/conventions/docs-management.md §1`）；registry 文件名 `component-registry.v2.json`（kebab + `vN` 主版本）。
- JSON 字段：camelCase（v9 schema 先例：`schema/team-protocols.schema.json`）。
- 锚点格式（C-02）：`path#L<a>-L<b>` 或 `path#§section`；`ref` 必须结构化（B-04）。

### 2.3 角色（A-05）
组件只引 `ownerRole`（职责名）；动态角色由 `roleTemplates` 的 spawn 契约创建（domain/group/workKind），**不得**把 `plugin-design-*`/`plugin-todo-owner` 写成 `team/agents.json` 常驻成员。

---

## 3. registry v2 格式与"可复用"判据

- 根：`$schema` / `schemaVersion` / `dataVersion` / `namingRule` / `roleTemplates` / `typeVocabulary` / `acceptGapPolicy` / `summary` / `gaps` / `components[]`。
- **callable/manual（A-01）**：`callable=true` 必须 `executor.kind=tool` + `entrypoint` + `argsSchema` + `returnsSchema`（schema 条件强制）——当前 **4 个**（见 §4 清单）；其余 **16 个** `callable=false` ⇒ `executor.kind∈{role,manual}` + `sopRef`。无组件再以 manual 冒充工具。
- **I/O（A-03/B-05）**：inputs/outputs 的 `type` 必须 ∈ `typeVocabulary`；所有 outputs 必填 `schemaRef`（`#/typeVocabulary/<type>`）；结构化类型（questions-brief/gap-record/handoff-package/user-summary/workflow-plan/analysis-doc/trace-rows/matrix-rows）带内联 JSON Schema 或外部 schema 路径。
- **preconditions（B-02）**：每条有 `check{kind,args}` 或 `manual:true`；审批类 `check.kind=approved`。
- **failureStates（B-03）**：每条 `detect{kind,args}` + `recover{action,ownerRole,retry}` + `severity`。
- **sideEffects/idempotent（A-08）**：`{kind,target,reversible}`；`{value,dedupeKey}`。
- **composesWith（B-07）**：`{targetId,mapping[{fromOutput,toInput}],optional?}`；校验器检查 fromOutput 存在、targetId 存在。
- **reuse（B-06）**：`reuseDecision` 为唯一权威；`matchedExisting[].decision` 只作证据。
- **"另一 agent 能否接"判据**：给定 id，仅读 registry 即可回答输入（类型/必填）、输出（schemaRef）、前置（check/manual）、失败（detect/recover）、副作用（target/reversible）、幂等（dedupeKey）、组合（mapping）、执行者（role/SOP）、状态。

---

## 4. SOP 手册与 callable 清单（registry `sopRef` 指向本节）

> 每条 SOP：**触发 → 步骤 → 证据 → 失败处理**。**16 个 manual 组件**按下方 SOP 表由人工/角色执行。

**callable（tool）4 个**（A-01；脚本由 `steward` 实现并 tracked，commit `54db680c`；本组只登记，不改脚本体）：

| 组件 | entrypoint | CLI（argsSchema） | returnsSchema（JSON 输出） |
|---|---|---|---|
| `comp.task-classifier` | `scripts/agent/comp_task_classifier.py` | `--board <path>` / `--classify <text>` / `--json` / `--selftest`（只读） | `{ok,ruleSource,classification:{category,priority,flow,owner,acceptance}}` 或 `{tasks:[{taskId,hasClassification,classification,flowValid,violations[]}]}` |
| `comp.component-registry` | `scripts/agent/comp_component_registry.py` | `--registry <path>` / `--list` / `--id <componentId>` / `--json` / `--selftest` | `--list → {rows:[{id,name,status,reuse,implementedBy}]}`；`--id → 完整组件对象`；未知 id exit 2 |
| `comp.component-reuse-judge` | `scripts/agent/comp_component_reuse_judge.py` | `--candidates <json>` / `--registry <path>` / `--json` / `--selftest` | `{ok,decisions:[{componentId,decision,matchedId,anchor,reason}],coverageGaps[],summary{total,reuse,complete,new,coverageGaps}}` |
| `comp.naming-convention` | `scripts/agent/comp_naming_convention.py` | `--registry <path>` / `--docs <path>` / `--json` / `--selftest` | `{ok:bool,violations:[{ruleId:R1..R8,componentId,detail}],counts{...}}`；违规 exit 1 |

> **需 steward 对齐（本组不越权改 `scripts/agent/**`）**：`comp_component_registry.py` / `comp_component_reuse_judge.py` 的 `--selftest` 仍按 v0.1 的 17 组件/4-9-4 断言；v0.2.1 应改为 v2 的 20 组件 / reuse 4 / complete 11 / new 5（Lead 已记录为 steward 后续对齐项；本组只在交付说明标注）。

**manual 16 个的 SOP 表**：

| SOP | 触发 | 关键步骤 | 证据 | 失败处理 |
|---|---|---|---|---|
| `#sop-task-classifier` | 新请求/INBOX raw | ①读 META v0.2 §2 ②按 §5 优先级判定 ③写 `定性: cls.<x>` + flow + owner | 任务 description 首行/decisions 行 | UNCLASSIFIED→人工二选一或取证 |
| `#sop-requirement-completer` | 请求含糊（B 内容） | ①查五类语料 ②写 7 列 trace ③列假设+ifWrongImpact ④openQuestions≤3 | REQUIREMENTS-TRACE 行/hasref | MISSING_CORPUS→先取证 |
| `#sop-corpus-retriever` | 补全/分析缺证据 | ①按 scope 检索 ②每条给 path#anchor/URL+日期 ③未核标未核 | 证据清单 | NO_ANCHOR→退回补锚 |
| `#sop-workflow-analysis-writer` | 需求已补全 | ①按 analysis-doc schema 写 stages(11) ②标 memoryType ③decisions/openItems | analysis 文档 JSON | 无证据→补证据 |
| `#sop-workflow-component-extractor` | 分析文本落盘 | ①逐环节映射组件 ②对照 registry 判 reuse ③unmatched 列人工 | 候选组件 JSON | EXTRACTION_LOSS→人工补映射 |
| `#sop-component-registry` | 组件库加载/变更 | ①跑 schema 校验 ②跑交叉检查 ③变更走 acceptGap/gap 记录 | 校验输出+哈希 | INVALID_SCHEMA→按错误修 |
| `#sop-component-reuse-judge` | 候选组件待判 | ①读 registry ②逐条 reuse/complete/new ③锚 path#/§ | decisions 表 | ANCHOR_MISSING→补锚 |
| `#sop-naming-convention` | 新 id/文件 | ①查 §2.1 正则 ②重名检查 ③不合规给建议 | verdict JSON | NO_RULE→先落规范 |
| `#sop-workflow-composer` | 组装工作流 | ①取组件列表 ②missing 组件登记 acceptGap 降级 ③环检测 ④输出 plan | workflowPlan JSON | CYCLE→重排/拆阶段 |
| `#sop-deployment-runner` | 需打包/新会话 | ①确认人批窗口 ②0 进程 ③打包 ④新会话验收 ⑤留证据 | 构建产物+新会话证据 | ASAR_LOCKED→退 app 重试 |
| `#sop-plugin-gap-recorder` | 发现插件缺失 | ①按 todo-requirement schema 记录 ②证据路径 ③复现命令 | gap-record JSON/INBOX 草稿 | GAP_UNPROVEN→补证据 |
| `#sop-inbox-digester` | INBOX raw 已定性 | ①校验 schema ②消化成票/文档 ③回执 ④按 docs-management 归位 | 回执+票清单 | BOARD_FULL→排队等 Lead 清位 |
| `#sop-seminar-runner` | Lead 放行议题 | ①brief ②独立提案 ③并集 ④交叉异议 ⑤Lead 裁决 ⑥冻结+sha256 | SEMINAR-*.md | HOP_BLOCKED→经 Lead 代转 |
| `#sop-design-author` | 裁决已冻结 | ①按 conventions 写文档/schema ②每条参照/理由/放弃条件 ③迁移清单 | 设计文档+schema | SPEC_CONFLICT→conventions 优先 |
| `#sop-design-reviewer` | 设计文档待评 | ①可行性/规范性 checklist ②finding 带 ruleRef ③对齐项目全貌 | findings JSON | NO_RULE_REF→补 ruleRef |
| `#sop-requirement-verifier` | 设计完成待测 | ①需求逐条→测试 ②先证红 ③矩阵回填 ④unknown 不算 pass | 矩阵+红证 | FALSE_GREEN→Lead 复核 |
| `#sop-phase-gate` | 阶段结束 | ①产出/证据/责任人齐 ②gateResult ③handoffPackage | dispatch-log/handoff | GATE_BYPASSED→不得静默通过 |
| `#sop-user-report` | gate 通过 | ①按 user-summary 字段写 ②附 evidence 路径与未决 ③Lead 可直接转发 | user-summary 文档 | REPORT_WITHOUT_EVIDENCE→补证据 |
| `#sop-seminar-brief-author` | 请求要开研讨 | ①定议题（产品可见） ②问题清单+纪律 ③proposer 分工+验收 | questions-brief JSON | BRIEF_TOO_VAGUE→改写不写内部结构 |
| `#sop-todo-requirement` | 新 INBOX 条目 | ①按 todo-requirement schema 校验 ②缺字段补 ③放行消化 | validationReport JSON | SPEC_INCOMPLETE→补齐 |

---

## 5. 覆盖缺口（显式人工 SOP；不假装已做）

见 registry `gaps[]`（11 条）：D-04 治理、D-05 独立性、D-06 矩阵 schema、D-07 文档归位、D-08 记忆型存储、D-09 案例库来源、A-04 自举（acceptGap 已解）、A-05 动态角色（roleTemplates 已缓解）、A-07 审批记录（manual+decisions 引用）、B-01 校验器（TD-01）、C-03 tracked（v0.1 已提交/v0.2 待提交）。
**纪律**：gap 的 `expiry` 到期未关必须由 `steward` 复评；不得把 gap 写成"已完成"。

---

## 6. 自举与 acceptGap 规则（A-04）

1. `workflow-composer` 的输入组件若 `status=missing`，**允许组装**，但必须为每个 missing 组件输出 `acceptGap{componentId,ownerRole,reason,expiry,degradedTo:manual-sop}`；
2. 该阶段自动降级为对应 SOP（§4），不阻塞后续阶段；
3. `maxGapsPerWorkflow=4`；超过即 FAIL（避免整条流程都由空组件拼成）；
4. acceptGap 必须写入 workflowPlan 并在 user-report 的 openItems 中披露；
5. 本轮 INBOX 工作流含 4 个 missing（extractor/reuse-judge/naming 校验器/composer），按此规则可组装，缺口见 GAP-A04-BOOTSTRAP。

---

## 7. 校验与验收（可执行）

**命令（本机 Python 3.12 + jsonschema 4.23 已实测通过）**：
```bash
python artifacts/agent/plugin-design/tools/validate_registry_v2.py                 # = --check all
python artifacts/agent/plugin-design/tools/validate_registry_v2.py --check anchors  # 锚点审计：refs=75 failures=0（含 20 sopRef）
python artifacts/agent/plugin-design/tools/validate_registry_v2.py --check acceptGap # acceptGap canonical：5/5 PASS
# 期望：SCHEMA: VALID / components: 20 {reuse:4, complete:11, new:5, statusImplemented:4, statusPartial:14, statusMissing:2, callable:4, manual:16} / callable:[4 个] / ANCHOR AUDIT: refs=75 failures=0 / ACCEPT-GAP CASES: 5/5 / RESULT: OK
```
**已通过的检查（v0.2.1 实测）**：JSON Schema（draft 2020-12）结构校验；`composesWith` 引用与 mapping 的 fromOutput 存在性；outputs `schemaRef` 可解析到 typeVocabulary；inputs/outputs type ∈ 词汇表；ownerRole ∈ roleTemplates；summary 与实际计数一致；**锚点审计 0 失败（含 20 条 sopRef）**；**acceptGap 5 条 canonical golden cases 全 PASS（GC-04-01…05）**；6 个 artifacts 证据副本与 docs 源 byte-identical。
**待 steward（TD-01）**：把上述检查固化为正式校验器/CI（先独立跑，Lead 批准才并入 `team_audit`）；并把 4 个脚本的 `--selftest` 断言从 v0.1 的 17/4/9/4 对齐到 v2 的 20/4/11/5。
**golden cases**：`docs/design/component-classification.cases.json`（classification 10 条 + **acceptGap canonical 5 条，validator 默认运行源**；META v0.2 §5 判定表） + `SEMINAR-COMPONENTS-M1/golden-cases/`（31 条评审契约来源；旧 04 文件用 `owner` 字段，已被 canonical 5 条取代，不再作为运行源）。

---

## 8. 权威与锚点

1. **唯一事实源**：`docs/design/component-registry.v2.json`（v0.2）；`docs/design/components-v0.2.md`（本文件，规范/命名/SOP）；`docs/design/component-registry.schema.json`（结构）。
2. **证据副本（6/6）**：`artifacts/agent/plugin-design/{component-registry.v2.json, component-registry.schema.json, components-v0.2.md, todo-requirement.schema.json, meta-protocol-v0.2.md, component-classification.cases.json}`（须与 docs 源 byte-identical；校验器断言）。
3. **锚点**：只用实际存在路径；`schema/team-protocols.schema.json` 的真实路径是 `artifacts/agent/plugin-design/schema/team-protocols.schema.json`；不存在的 `docs/guides/team-plugin-migration.md` 不再引用（用 `V9-MIGRATION.md`）。
4. **v0.1 历史**：`docs/design/components-v0.1.md` + `component-registry.v1.json`（Lead commit `b28c6cf7`）；v0.2 审后由 Lead 提交（本组不 commit）。
5. **动态角色**：只写 roleTemplates 职责名+spawn 契约（A-05）。

---

## 9. 版本与升格

| 项 | 值 |
|---|---|
| 设计版本 | **v0.2.1**（v0.2 复评剩余 4 项 P0 修复：A-01/A-04/C-02/C-03） |
| registry `schemaVersion` / `dataVersion` | `2.0.0` / `0.2.1` |
| 组件 `version` / `interfaceVersion` | `0.2.0` / `1.0.0` |
| 命名规范升格 | 待人类批准后，把本文件 §2 迁入 `docs/conventions/components.md`（本组不直接改 conventions） |
| v0.2.1 提交 | **待 Lead `git add` + commit**（C-03：本组不写 tracked、不 commit） |

---

## 10. 未决（等复评/Lead 裁）

1. 4 个脚本的 `--selftest` 仍按 v0.1 断言（17/4/9/4），需 `steward` 对齐到 v2（20/4/11/5）；本组不越权改 `scripts/agent/**`。
2. `comp.workflow-composer`/`comp.user-report` 等 dsh-plugin 票的排期与单向门窗口（第二批，Lead 排）。
3. B-06 的 `matchedExisting` 证据与 `reuseDecision` 是否需要自动聚合校验（TD-01 校验器可加）。
4. golden cases 全 31 条 RUNNER（含 06-07 跨文档列检查）仍待 steward 的正式校验器；本组只实现 acceptGap canonical 5 条与锚点审计。
5. `docs/design/components-v0.1.md` 是否加"superseded by v0.2"标记（Lead 决定；v0.2 未改 v0.1 文件）。
