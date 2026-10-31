# 任务定性元协议 v0.2（META-PROTOCOL）

> **docId**：`doc.meta.task-classification`（**文档 id**；不是协议注册 id）
> **候选协议 id**：`workflow-task-classification`（合法 kebab，符合 `schema/team-protocols.schema.json` 的 pattern；**当前为候选手册，未注册进 `team/protocols.json`**，登记需 `registryVersion 2` 且由 Lead/人裁）
> **版本**：v0.2（2026-10-31）｜**状态**：draft-pending-review（v0.1 评审 32 条后修订；等 seminar 复评）
> **来源**：`INBOX-20261030-01`（人 2026-10-30 15:58 口述，Lead 逐字转录）
> **Owner**：`plugin-todo-owner`｜写域：`docs/design/**`、`artifacts/agent/plugin-design/**`
> **关联**：`docs/design/components-v0.2.md`（命名/registry/SOP）、`docs/design/component-registry.v2.json`、`docs/design/component-registry.schema.json`、`docs/design/component-classification.cases.json`（golden cases）、`docs/guides/team-protocols.md`（P-01–P-08）、`team/protocols.json`（registryVersion 1）
> **本版修复**（对应评审编号）：**C-01**（id 统一为合法 kebab + docId 分离）、**C-02**（锚点修正）、**C-05**（状态一致）、**A-06**（判定反例/部署归属）、**B-09**（golden cases 落文件）、**A-05**（角色写职责名+spawn 契约，不写死成员 id）。

---

## 0. 一句话

**任务定性 = 在任何派发/执行之前，把「人的原始请求」判定为五类之一，并据此选择处理流转、责任人与验收物；判定必须留痕、可更正、可机检（golden cases）。**

- 位置：Lead 之前或由 Lead 执行；`plugin-todo-owner` 对 INBOX 条目做二次核对。
- 强制力：**当前只能是「文档约定 + 审计」**；工具级强制属 M-3（不越序，见 §4）。
- 非目标：不做任务拆分/排期/验收判定（各流程负责）。

---

## 1. 触发条件（何时必须定性）

| # | 触发信号 | 说明 |
|---|---|---|
| T1 | 请求含动作词：开团队/派活/研讨/设计/落地/实现/修复/发布/打包/部署 | 需要选流程 |
| T2 | 任务 subject/description 提及版本号 `X.Y.Z` | 触发 release 相关判定（并触发 `planRef`：P-03） |
| T3 | 跨域/跨仓（不同 domain、不同 writeScope、Memoria↔DSH） | 需定主责与验收 |
| T4 | 打包/发版/改 tag/强推/迁移数据（R1 单向门） | 必须 release 流转 + 独立验收（`docs/guides/agent-team-org.md §4` 第 6 步） |
| T5 | 请求有歧义/语料不足（只说 B 内容） | 先补全（`comp.requirement-completer`） |
| T6 | INBOX 收到 `raw` 条目 | 消化前必须先定性（`todo-requirement.schema.json` 要求 `category` 字段） |

**不需要定性**：纯查询/只读检索；单文件小改且无跨域；Lead 自己的 git 状态类操作。事后发现漏判按 §6 更正。

---

## 2. 判定表（信号 → 类别；每类带反例）

| 类别 id | 名称 | 判定信号（满足任一） | 反例（像但不归入） |
|---|---|---|---|
| `cls.defect-fix` | 缺陷修复 | 含 bug/异常/回归/坏了/修复/不通过；已定位到现有行为错误 | "把某功能补上"=新能力→infra/team-work-design；性能优化无 bug 证据→先 research-forensics |
| `cls.release` | 版本发布 | 含发版/发布/tag/打包/资产/上线；**且**涉及交付版本或发布包 | 只改版本号注释/changelog 草案→infra-change；"修复 1.2.3 版本引入的回归"→**defect-fix**（见 §5 案例） |
| `cls.team-work-design` | 团队工作分析与设计 | 含开团队/研讨/设计/工作流/组件化/落地/实施方案；产出=分析文本/设计文档/组件 | 只做一次性取证报告→research-forensics；只改 repo 结构/脚本→infra-change |
| `cls.infra-change` | 基础设施改造 | 改依赖/脚本/CI/插件契约/目录结构/构建配置；**部署/上线基础设施**（不涉及版本发布） | 纯数据迁移且只执行既定方案→仍 infra；改文档正文/规范→team-work-design |
| `cls.research-forensics` | 纯取证调研 | 只要求查清楚/取证/对比/评估/给证据，明确不产生代码/设计决定 | 取证后要求落地→team-work-design；纯读文件回答→无需定性 |

**判定优先级（冲突时）**：`release`（仅当同时含发布/版本交付动作）> `infra-change` > `defect-fix` > `team-work-design` > `research-forensics`。
**A-06 修正**：`hasVersion` **不得单独触发 release**——只有"版本号 + 发布动作"同时出现才走 release；"修复某版本回归"优先 defect-fix；"部署/上线工作流"归 infra-change（无版本交付时）。

---

## 3. 每类处理流转（角色用**职责名**，不写死成员 id；spawn 契约见 registry `roleTemplates`）

> 角色映射：`lead`（主控）、`steward`（团队管理员/过程审计）、`team-plugin-creator`（插件守护）、`plugin-design-seminar`（研讨主持，动态 spawn：domain=seminar/group=plugin-design/workKind=seminar）、`plugin-design-architect`（设计作者，动态）、`plugin-design-researcher`（取证，动态）、`plugin-todo-owner`（台账，动态）、`verifier`（独立验收，未参与实现）。**动态角色不在 `team/agents.json`**，按 roleTemplates 的 spawn 契约临时创建（A-05/C-02 修正）。

### 3.1 `cls.defect-fix`（缺陷修复）
复现/最小化 → 建任务（owner+writeScope+验收）→ 修+自测 → 独立验收（先证红→修复→回归）→ Lead 收口（evidence 必填）。验收人=Lead；R1 级必独立 verifier。失败退回：无复现/证据不足→回步骤 1。

### 3.2 `cls.release`（版本发布）
版本级计划 + `plan_ref`（P-03）→ Lead 三查 + R1 独立验收派发 → 打包/发布资产 → Lead 亲跑门禁（`scripts/agent/release_preflight.py`）+ 远端核对 → 汇报用户（`comp.user-report`）。失败退回：任何三查/门禁失败停发版，回计划；禁止先发后补。

### 3.3 `cls.team-work-design`（团队工作分析与设计；本 INBOX 案例）
定性 → **需求补全**（`comp.requirement-completer`，依赖五类语料）→ 研讨（`comp.seminar-brief-author` → `comp.seminar-runner`：独立提案→并集→交叉异议→Lead 裁决→冻结）→ 设计（`comp.design-author`，可被 `comp.design-reviewer` 质疑可行性/规范性）→ 测试（`comp.requirement-verifier`，需求→证据矩阵）→ 汇报（`comp.phase-gate` → `comp.user-report`，Lead 可直接转用户）→ 缺失能力登记（`comp.plugin-gap-recorder` → `comp.inbox-digester`）。
**语料库（补全依据）**：团队现状（`team/agents.json`、`docs/guides/agent-team-org.md`）｜既有协议（`docs/guides/team-protocols.md` P-01–P-08、`team/protocols.json`）｜成熟工作流（`docs/guides/team-plugin-improvement-spec.md` R1–R9、`docs/guides/team-plugin-overhaul-spec.md`、`docs/guides/dsh-agent-teams-contract.md`）｜开源 skill（`%USERPROFILE%\.agents\skills\`，引用必须给路径/命令）｜正反案例（`docs/guides/agent-team-lessons.md`、`artifacts/agent/plugin-design/EVIDENCE-OSS.md`、`team/dispatch-log.jsonl`；网上材料须 URL+访问日期+许可）。

### 3.4 `cls.infra-change`（基础设施改造）
影响面+回滚方案 → 变更设计（含迁移/兼容判据）→ 实现+自测 → 独立 verifier 回归（旧会话/旧数据）→ 收口（触契约则同步迁移文档）。失败退回：无回滚方案不启动；跨仓变更先定证据记录约定。

### 3.5 `cls.research-forensics`（纯取证调研）
问题清单+证据等级 → 只读取证（逐条锚）→ 评审锚是否支撑结论、未核标【待核】→ 若落地则转 design/infra。失败退回：无锚结论退回；未核不得伪装结论。

---

## 4. 与 `team_preflight` / `protocols.json` 的挂接（强制力诚实标注）

**现状事实**（`docs/guides/team-protocols.md §1`）：注册表 8 条协议中**只有 P-01 / P-02 会真正拒绝**；P-03–P-08 为 audit（其中 P-03/P-04/P-05 原生拒绝由插件代码实现，P-06 事后机检，P-07/P-08 人工评审）。**"任务定性"当前没有工具级拒绝点** ⇒ v0.2 仍是**约定 + 审计**；工具强制属 **M-3**（不越序，另开议题）。

| 元协议要素 | 执行载体 | 强制力（诚实） |
|---|---|---|
| 定性记录（category+flow+owner） | 任务 description 首行 `定性: cls.<x>`；`team/decisions.jsonl` Decision 行 | **audit**（无工具校验） |
| 发布类必须 `planRef` | 插件原生 `TEAM_PLAN_REF_REQUIRED`/`TEAM_PLAN_REF_MISMATCH`；注册表 P-03 登记 | **format/refuse（插件已实现）** |
| 收口必须有 evidence | 插件 `TEAM_TASK_EVIDENCE_REQUIRED`；注册表 P-02 | **semantics/refuse（插件已实现）** |
| 先建任务再 spawn | `scripts/agent/team_audit.py::l1_task_before_spawn`；注册表 P-06 | **audit（事后机检）** |
| 定性/流转遵守 | golden cases 机检（`component-classification.cases.json`）+ `steward` 过程审计 | **audit** |
| 未来：定性工具化 | 候选 `team_classify`/preflight 吸收；**属 M-3** | **待裁** |

**注册规则（C-01 修正）**：①`comp.`/`cls.`/`doc.` 命名空间**不注册**进 `team/protocols.json`；②要注册的协议用合法 id：kebab（`^[a-z][a-z0-9-]{2,63}$`，如 `workflow-task-classification`）或内置 `tool.<camelCase.path>`；③元协议文档 id 用 `doc.meta.task-classification`，与协议注册 id 分离。

---

## 5. Golden cases（可执行判定自检；文件=`docs/design/component-classification.cases.json`）

| case | 输入（原话/任务） | 期望类别 | 为什么 |
|---|---|---|---|
| C01 | "修复 1.2.3 版本引入的回归 bug" | `cls.defect-fix` | A-06：版本号不单独触发 release |
| C02 | "发版 1.2.3，打包并核对资产" | `cls.release` | 版本+发布动作 |
| C03 | "开研讨团队研讨图层面板设计并落地" | `cls.team-work-design` | 设计+落地 |
| C04 | "把 __pycache__ 从 git 移除并修审计脚本" | `cls.infra-change` | 结构/脚本改造 |
| C05 | "查一下 n8n 和 LangGraph 的编排差异，给证据，不落地" | `cls.research-forensics` | 纯取证 |
| C06 | "帮我把这套工作流部署一下" | `cls.infra-change` | 部署基础设施（无版本交付） |
| C07 | "修一下按钮点击无反应" | `cls.defect-fix` | 现有行为错误 |
| C08 | "给组件库加一个 user-report 组件" | `cls.team-work-design` | 设计/组件产出 |
| C09 | "打包 DSH 桌面应用" | `cls.release` | 单向门：打包=发布动作 |
| C10 | "帮我看下这段 PR 描述的措辞" | `UNCLASSIFIED`→人工/取证 | 无命中关键词，需人工或先取证（记录假设） |

**运行方式（校验器待 TD-03；当前可手工/临时脚本）**：读 cases JSON，对每条跑 §2 判定函数，比对 expected；不符即 FAIL 并输出 case id。

---

## 6. 失败态与更正（append-only）

| 失败态 | 判据 | 处理 |
|---|---|---|
| `UNCLASSIFIED` | 五类都不命中 | 暂停派发；只问产品可见二选一，或转取证并记录假设 |
| `MISCLASSIFIED` | 事后出现反例 | 按 `docs/conventions/meta-rules.md` 规则 2 标记（✅/❌/⏳）；`team/decisions.jsonl` append 更正 Decision，重走流转 |
| `CLASSIFIED_BUT_UNTRACED` | 有定性但无记录 | `steward` 过程审计开 finding；补记录后继续 |
| `MISSING_CORPUS` | 补全缺语料 | 降级 research-forensics 先取证；列"缺什么语料"，不得编造 |

---

## 7. 验收判据（v0.2，可执行）

1. **cases 通过**：`component-classification.cases.json` 10/10 命中（C01/C02/C06 为 A-06 重点）；未命中即 FAIL（输出 case id）。
2. **落痕**：INBOX 每个 raw 条目回执含 `classification: cls.<x>` + flow + 验收人；抽查 10 张新任务 description 首行含 `定性: cls.<x>`。
3. **不假强制**：文档不得出现"工具强制定性"表述；工具化建议统一标"候选/M-3/待裁"。
4. **可更正**：每条更正有 append-only 记录（decisions/INBOX 回执）。

---

## 8. 状态（v0.1 未决 → 本版处理；C-05 修正）

| v0.1 未决 | v0.2 状态 |
|---|---|
| 命名是否升 conventions | **已裁（Lead 2026-10-31）**：不直升，落 `docs/design/`（v0.2 见 components-v0.2.md §2） |
| registry 落点 | **已裁**：`docs/design/` 为唯一事实源；v0.2 为 `component-registry.v2.json`（v0.1 保留历史） |
| 第二步写域 | **已裁**：不扩写域，只出票清单（TICKET-DRAFTS-v0.1.md），实现归 steward/creator |
| task-classifier 与 preflight | **已裁**：v0.1 保持文档约定、不并入工具（M-3 不越序）；v0.2 继续文档约定 + golden cases |
| 五类之外是否加类别 | **未裁**（保留；出现漏判再升） |
| 协议注册 | **未注册**：候选 id `workflow-task-classification` 合法，但登记需 registryVersion 2 + Lead 裁（本轮不登记） |

---

## 9. 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-30 | v0.1 | 首版（5 类判定/流转/伪代码/挂接/验收） |
| 2026-10-31 | v0.2 | 按 M-1 评审 32 条修订：C-01 id 合法化（docId 分离 + 候选 kebab id）；C-02 锚点修正（schema 实际路径、去不存在文档、动态角色改职责名）；C-05 状态同步；A-06 判定反例（版本号/部署）；A-05 角色职责名+spawn 契约；B-09 golden cases 落文件；强制力标注复核（仅 P-01/P-02 refuse） |
