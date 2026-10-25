# Team 插件愿景：从「文档记忆」到「插件流水」

> **状态**：设计稿（2026-10-25）｜**作者**：`todo-owner`（应 Lead 派发消化人的长期方向）
> **需求本体（人原话，一字不改）**：
> > 「我想把team的工作范式进行进一步的固化升级，让各种行为动作都不只是依赖对规范文档的记忆，还有遵循团队插件的工作流水（之前有提到一些团队工作方式，我还想到一点，就是**有一些角色需要长期监视别人干活，那他的工作模式就不能是被触发，他要么有规律的自触发点，同时保证自己有很好的团队理解，或者要么有团队契约什么时候必须要这个人监视审查团队运作模式，这个契约不能是只依赖记忆文档，还得有插件支撑**），甚至包括**团队工作改革和自维护，螺旋上升**，并且，**针对不同场景需求，团队的结构和成员角色会有一些不同，但是我相信保证工作质量和效率的方面是存在共性的**，最终我想把team这个插件做成**核心、开发的主体**，甚至有望用于memoria里面服务于学习+记笔记+复习过程中出现的多种场景，**甚至结合memoria aoci xerj成为一个dsh的插件**，让用户不只是面对一个团队不断吐出需求、而无法跟上细节，而是**能够看到规范的成体系的文档，获知各个设计细节甚至代码，成为一个开发新范式**」
> **一句话**：把「应该做」变成「不做就过不去」；把团队工作变成用户可读、可追溯、可验证的成体系产物。

---

## 0. 一句话结论

本轮已经证明：**写在文档里靠"记住"的规范，遵守率就是随机数**（L10 就是被反复打脸后的产物）。因此本设计的核心原则只有一条：

> **凡是「靠记住」的义务，都要变成「不给出就无法通过」的三种强制点：**
> **① 工具拒绝（refusal） ｜ ② 工具返回值（obligation） ｜ ③ 流水线 wrapper（gate）**。
> 超出插件能力边界的（git commit / 发布 / 跨进程），必须显式落成 **repo hook** 或 **记账**，不得假装插件能管。

---

## 1. 论点链（人的 6 条 + 我的 2 条修正）

| # | 论点 | 我的修正/补强 | 本轮实证 |
| --- | --- | --- | --- |
| ① | 现状靠「对规范文档的记忆」⇒ 需要「插件工作流水」 | 精确化为：**把义务做成工具返回值/工具拒绝**，而不是写进文档句子 | ✅ 已验证：`team_preflight` 返回义务、`team_task_create` 版本级任务无 `plan_ref` 直接拒、`complete` 无 evidence 拒、`retire_teammate` fail-closed |
| ② | 监督型角色不能被「事件触发」 | 两个方案（规律自触发 / 契约强制审查点）都需要落到工具/流水线；**"监视者被动等触发=永远不会主动看"** | ⚠️ 部分：机制可行性已查（见 §4），**尚无现成实现** |
| ③ | 团队自身要改革与自维护（螺旋上升） | 需要**版本化契约 + 迁移机制**，否则"改革"只会变成又一份文档 | ✅ 实例：团队插件契约 v3→v4（`contractVersion`/`reviewedChanges`/`contractNotice`），本项目已按 v4 声明（`team/plugin-contract.json`） |
| ④ | 场景不同、结构不同，但质量/效率有共性 | 拆成 **不变层（kernel）+ 可变层（profile）**：kernel 管义务/证据/门禁；profile 管角色/节奏/写域/交付物 | ⏳ 设计（见 §5/§6） |
| ⑤ | team 插件要做成核心/开发主体，用于 memoria 学习+笔记+复习，结合 aoci/xerj 成 DSH 插件 | 拆成两条独立路线：**内部固化**（先）与**对外产品化**（后）；两者不能混在一个版本里 | ⏳ 规划（见 roadmap） |
| ⑥ | 用户能看到成体系文档 + 设计细节 + 代码，而非"团队吐需求但跟不上" | **修正：把"用户可读"从结果提升为一等设计约束 + 验收标准**。否则内部再规范，用户还是看不懂 = 跑偏 | ⏳ 本轮所有产物都是给 Lead/人看的报告，**尚未有面向用户的成体系视图** |
| ⑦ | （我补）插件能力边界 | **插件只能强制"它自己的工具/它注册的流水线"**；git commit、发布流程、跨进程行为需要 repo hook 或 DSH 新 API。不写清这条，设计会变成假承诺 | ⚠️ 已查：`tools/execute` wrapper 可包装工具调用（`docs/subsystems/tools.md:65,313`），但**没有**通用的"拦截第三方工具"之外的自调度 API（见 §8） |

---

## 2. 设计原则：三种强制点 + 两个下沉

| 强制点 | 定义 | 本轮实例 | 何时用 |
| --- | --- | --- | --- |
| **refusal（工具拒绝）** | 参数/状态不满足直接报错，不进入执行 | `team_task_create` 缺 `plan_ref` → 拒；`complete` 无 evidence → 拒；`retire` 无 memory card/ruling → 拒 | 有明确前置条件的**动作** |
| **obligation（工具返回值）** | 工具返回结构化义务清单，调用者必然看到 | `team_preflight(intent)` 返回 4 条义务（consult-todo-owner / audit-ledger / write-plan-section / check-prev-shipped） | 无法用参数表达、需要"提醒但不必阻断"的流程 |
| **gate（流水线 wrapper）** | 包装 `tools/execute`，在调用前后拒绝或补证 | `repeat-tool-reminder` / `timeout-policy` 都是 `tools/execute` wrapper（`docs/subsystems/tools.md:65`） | **跨工具**的硬门（如 release 前必须审查） |
| **下沉 A：repo hook** | 插件管不到的（git commit/CI/发布脚本） | 本轮 `decision_trail` 只能靠 `team_audit.py` 事后 WARN | 提交/发布类硬门 |
| **下沉 B：记账** | 无法强制时，至少留下可审计记录 | `team/decisions.jsonl` + `decide.py` | 可回退决策 |

---

## 3. 现状义务 → 保证方式 → 升级建议（扎根本轮实证）

| # | 义务 | 当前靠什么保证（证据） | 现状缺口 | 升级建议 | 可行性 |
| --- | --- | --- | --- | --- | --- |
| 1 | 版本级规划须 todo-owner 先出计划（L8） | **工具**：`team_preflight` 返回义务 + 版本级任务 `plan_ref` 硬拒（`tool-agent-team/src/index.ts:397,1028`；本轮 task-111/119 实测） | 无（已固化） | 保持；把 preflight 义务扩展为"计划必须含关闭条件/不做什么" | ✅ 已验 |
| 2 | 关闭任务须证据（L3） | **工具**：`complete` 要求 `evidence` 或 `no_artifact_reason`（`index.ts:1129-1177`；本轮多次实测） | 证据只校验"路径存在"，不校验"内容相关" | 加 evidence 类型（artifact/report/commit）与最小校验（如 commit 必须存在、报告必须含关键词）；**渐进，不阻塞** | ✅ 已验（拒绝），增强待做 |
| 3 | 退役须记忆卡 + Lead 裁决 | **工具**：`retire_teammate` fail-closed（v4 契约变更 `retire-fail-closed` / `retire-lead-ruling-required`；`team/plugin-contract.json`） | 无（已固化） | 保持 | ✅ 已验 |
| 4 | spawn 必须显式 mode（L9） | **文档**：AGENTS.md L9 + 机检 WARN | 源码 `const mode = args.mode ?? 'standard'`（`index.ts:617`）⇒ **静默默认仍在**，日志上"忘了想"与"决定用 standard"不可区分 | **refusal**：`spawn_teammate` 缺 `mode` 直接拒（契约 v5 候选）；或至少返回值 `modeExplicit:false` + 警告 | ✅ 已验证缺口；改动需 DSH 插件 |
| 5 | 决策留索引（L10） | **文档 + repo 脚本**：`team_audit.py::decision_trail` 事后 WARN（37 条宽限期；本轮发版记录亦记录"记录偏离≠授权"） | 提交前无强制；T1/T3 触发靠人判断 | **下沉 A**：repo `pre-commit` hook 检查 `Decision:/Why:`；插件侧提供 `team_decide` 工具写 `decisions.jsonl` 并由 release gate 校验 | ⚠️ 插件只能管自己的工具；git 层需 hook |
| 6 | 「声明≠事实」（8 次靠人抓） | **无机器拦截**；仅 `team_audit.py::artifact_refs` 事后检查路径存在 | 文本断言/死代码/量具盲区都拦不住 | **obligation + gate**：preflight 增加"claim 须绑定可执行验证（测试名/真机证据）"；release gate wrapper 检查每条 release note 声明都有 artifact | ⚠️ 需设计，无法一键机检 |
| 7 | 监督者必须主动审查（人痛点②） | **无机制**（当前只有 Lead 被动调度 + 事后审计） | 监视者不被触发就永远不看 | 见 §4（A/B 两方案） | ⚠️ A 部分可行/B 可行但需原型 |
| 8 | 插件契约版本一致性（③） | **工具返回值**：`contractNotice`（`contract.ts:183-207`；本轮 `status=ahead, pluginVersion=3, declaredVersion=4`） | 只发通知，**不阻断**；本项目声明 v4 但运行插件 v3 | **refusal**：声明版本 > 插件版本时，版本级任务直接拒（"升级插件或降声明"二选一） | ✅ 机制已存在；改拒绝需插件代码 |
| 9 | 用户可读的成体系文档（⑥） | **无**（产物散落 `artifacts/agent/verify/**`，人需 Lead 转述） | 用户跟不上细节 | 新增 `team_digest` 工具：从任务板/决策/artifact 生成"人可读的版本叙事 + 索引 + 代码锚点"；产物落 `docs/design/**` | ⏳ 设计（roadmap 阶段 4） |
| 10 | 写域单写者（并发覆盖） | **文档 + 任务板 writeScopes + 机检** | 重叠只是 WARN，不拒 | **refusal**：`claim` 时检测存活成员写域重叠并拒（`write_scope` 已有检查逻辑可复用） | ⚠️ 部分可行（agent-team 有 task-board）；需插件改 |
| 11 | 发布/发版门禁（R1） | **repo 脚本 + 人**（本轮 Lead 亲跑 pytest/node/team_audit） | 无插件级门 | **gate**：`tools/execute` wrapper 拦截 release 类命令，要求先有 review/decision artifact | ⚠️ 需原型（wrapper API 已验证存在） |
| 12 | 记忆卡继承（防"错误记忆更好用"） | **工具**：spawn `memory_cards`/`inherit` + 退役强制卡 | 卡内容质量无校验 | 保持；增加"卡必须含 Lead 裁决段"已有（retire 要求） | ✅ 已验 |

---

## 4. 监督型角色机制（人最具体的痛点）

### 方案 A：规律自触发（supervisor 定时醒来审查）——**❌ 已验证不可行（2026-10-25，机制层禁止）**

> **实测结论**：teammate 的工具表**挂载了** `schedule_list / schedule_create / schedule_update / schedule_delete` 四个工具，
> 但任何调用都被 DSH 拒绝，错误原文：
> ```
> {"code":"subagent_session","message":"A delegated subagent cannot use reminders."}
> ```
> ⇒ 拒绝是**会话类型级**（teammate 被当作 subagent 会话），**不是 preset 缺工具** ⇒ 换 preset / 升级插件 v4 都不能解决；
> 开关在 DSH 的 subagent/session 策略层（推断，错误码与文案可证）。
> **详细证据**：`artifacts/agent/verify/todo/team-plugin-schedule-verify.md`（含 spawn/retire 的 dispatch-log 时间线）。

**原方案（保留供追溯）**：目标是监督者不依赖"别人触发"，按固定节奏醒来读任务板+最近产物、输出审查报告。
原机制设想过：给 supervisor 一个 recurring reminder → Host 到期 resume 原 Session 投递 → supervisor 跑审查工具链。
**该机制对非 subagent 会话成立**（Lead 会话实测 schedule 四工具可用；Host 会 resume 原 Session：`docs/subsystems/schedule.md:5,251-252`），
但 **teammate 会话被策略禁止**，因此不能用于 supervisor。

**替代：Lead 代持定时唤醒（过渡方案）**
1. **Lead** 用 `schedule_create` 设 recurring reminder（如每日 09:00 / 每 2h）——Lead 不是 subagent，schedule 可用（实测）。
2. 到期 Host resume **Lead** 会话；Lead 收到提醒后 `send_message` 给 supervisor（inactive target 会**起一个回合**，`tool-agent-team` 文档：inactive target starts or resumes a turn）。
3. supervisor 执行审查（任务书 + 检查项 S1–S6），产出 review artifact，`team_task_create` 挂结论。
4. **代价**：触发链多一跳（Lead 定时 → Lead 代发），Lead 必须在线/会话可被 resume；supervisor 本身仍不能自触发。

### 方案 B：团队契约强制审查点（release 前必须审查）

**目标**：关键节点（release / 版本关闭 / R1 操作）没有 supervisor 审查就**过不去**。

**机制**：
1. 契约声明：团队 profile 里写「release 前必须存在 supervisor review artifact（含 verdict/证据锚）」。
2. **插件 gate**：注册一个 `tools/execute` wrapper（与 `timeout-policy` 同机制，`docs/subsystems/tools.md:65,313`），在 `release`/发版类工具调用前检查 review artifact；缺失 ⇒ 拒绝并返回"缺什么"。
3. 现状：Memoria 的发布是 **repo 脚本 + Lead 手动**，不是 DSH 工具 ⇒ 插件 gate 覆盖不到；需要 **repo 侧 release 脚本**读 `team/decisions.jsonl`/review artifact 做前置检查，或未来把发版封装成 DSH 工具。

**可行性判定**：
- ✅ **wrapper 机制存在**（`tools/execute` wrapper 是官方支持的扩展点；`repeat-tool-reminder`/`timeout-policy` 是同一机制的两个实例）。
- ⚠️ **未验证**：wrapper 能否"拦截任意工具（含其他插件的工具）"还是只能包装自己注册的工具——文档称 "Around-dispatch view of a ToolExecution. A `tools/execute` wrapper"，倾向可包装全局 dispatch；**需写一个原型（10 行 wrapper 拒绝某个工具）验证**。
- ✅ **repo 侧**：即使插件 gate 不可行，release 脚本前置检查（读 review artifact + decisions）**现在就能做**，属"下沉 A"。

### 推荐（2026-10-25 Lead 裁决 + 验证后修正）

**决策 1 最终 = A 不可行（机制层已证）⇒ 主路径 B（契约 + repo 侧门禁）+ 过渡「Lead 代持定时唤醒 supervisor」。**

1. **A 已判 ❌**：teammate 调用 schedule 被 `subagent_session` 拒绝（错误原文见上）；**换 preset/升级插件都不能解决**。不再把 A 当候选。
2. **B 是主路径**：
   - **repo 侧（已落地）**：`scripts/agent/release_preflight.py` —— 缺 supervisor review artifact（或 verdict≠pass/版本不符）⇒ exit 1；`--selftest` 四条 fixture 自证红/绿。
     ⚠️ **待扩展**：release 规范（标题格式/双语结构/造价段）修好后，把这三项并入检查（Lead 2026-10-25 要求）。
   - **插件侧**：`tools/execute` wrapper 仍是候选（机制存在，未原型验证），不承诺。
3. **过渡方案（Lead 代持）**：Lead 设 schedule 定时 → 到期 resume Lead → Lead `send_message` 唤醒 supervisor（inactive target 起回合）→ supervisor 审查并落 artifact。
4. **共同前提**：审查报告必须**有可验证形状**（verdict/证据锚/时间/被审对象），否则"审查"会变成又一份文档。

### 监督角色的失败模式（Lead 补充 1，必须写进设计）

> **最大的失败模式不是"不触发"，而是"触发了但看不出问题"** —— 每次按时产出"一切正常"的报告 = 没有监督。

因此 supervisor 的审查必须有**明确检查项**与**必报 FAIL 条件**（不能只写"审查一下"）：

| # | 检查项 | 必报 FAIL 的条件（示例） |
| --- | --- | --- |
| S1 | 任务板健康 | 出现 ready 但无 owner 的任务；in_progress 超过约定时长无进展；blocked_by 指向已消失任务 |
| S2 | 证据完整性 | 有任务 `complete` 但 evidence 指向不存在的路径/commit；报告声明与 artifact 不符 |
| S3 | 声明 vs 事实 | 本轮新增/修改的"已修复/已实现"声明，找不到可执行验证（测试/真机证据/矩阵） |
| S4 | 版本与门禁 | 版本号/声明/tag 三者不一致；发版记录缺回滚方案；review artifact 缺失 |
| S5 | 决策留痕 | T1/T3 提交缺 `Decision:/Why:`；重大偏离只有记录、没有授权 |
| S6 | 用户可读性 | 本版本 digest 缺失，或 digest 无法在 5 分钟内回答三个问题（见 §9） |

**输出格式（强制）**：`verdict: pass|fail` + 每项 `检查项 / 结论 / 证据锚 / 建议`；**verdict=fail 必须给出阻断项**，否则报告无效。

---

## 5. 分层模型：kernel（不变）+ profile（可变）

```
┌─ kernel（所有场景共用，插件强制）─────────────────────────────┐
│ K1 义务即工具：preflight 返回义务；缺前置 ⇒ refusal          │
│ K2 证据即完成：complete 必须 evidence/理由；artifact 可校验   │
│ K3 角色生命周期：spawn/retire 显式、fail-closed、记忆卡      │
│ K4 版本三查 + plan_ref + 契约版本一致（声明>插件 ⇒ 拒）      │
│ K5 R1 单向门：不可逆操作先给回滚方案 + 非决策者对抗复核      │
│ K6 可审计：任务板/决策/轨迹/审查报告 均有落盘格式            │
│ K7 用户可读：每个版本的 digest 是交付物（不是副产品）         │
└──────────────────────────────────────────────────────────────┘
              ↑ profile 只能配置这层的参数，不能绕过 K1–K7
┌─ profile（按场景换，声明式）────────────────────────────────┐
│ P1 角色集合（builder/verifier/registrar + 场景专属）         │
│ P2 触发关系（谁在什么事件/节奏被唤醒）                       │
│ P3 审查节奏与审查者（supervisor 何时必须审查）               │
│ P4 写域划分（单写者边界）                                    │
│ P5 交付物形态（代码/文档/知识库/复习卡/报告）                │
│ P6 用户可见文档模板（版本叙事/设计索引/代码锚点）            │
└──────────────────────────────────────────────────────────────┘
```

**为什么这样分**：人说的「质量与效率有共性」= kernel；「不同场景结构与角色不同」= profile。本轮已验证的强制点（preflight/plan_ref/evidence/retire）全部落在 kernel；场景差异（写域、审查节奏、交付物）落在 profile。

---

## 6. 场景矩阵（≥3 个场景）

| 维度 | ① 软件仓库开发（Memoria 当前） | ② 知识库内容创作 | ③ 学习 / 复习陪练 |
| --- | --- | --- | --- |
| 角色 | Lead（调度）+ builder（写代码）+ verifier（真机/门禁）+ registrar（台账）+ supervisor（审查） | Lead + 内容架构师（大纲/类型学）+ 写作者（章节）+ 事实核查员 + supervisor | Lead（陪练）+ 知识点拆分员 + 出题员 + 复习调度员 + supervisor（学习计划偏差审查） |
| 触发 | 任务板事件 + 版本门禁 + supervisor 定时 | 大纲变更 + 章节完成 + 定时审查 | 每日/每周复习周期 + 错题触发 + 周度计划审查 |
| 谁审查谁 | verifier 审 builder；supervisor 审 Lead 的排期与范围；Lead 审交付物 | 事实核查员审写作者；supervisor 审一致性/引用 | 出题员审知识点覆盖；supervisor 审复习计划 vs 实际完成 |
| 交付物 | 代码 + 测试 + 报告 + 发版记录 + digest | 章节 md + 引用清单 + 术语映射 + digest | 复习卡 + 错题本 + 周报 + 掌握度读数 |
| 失败模式 | 声明≠事实、越序发布、死代码 | 事实漂移、引用断链、术语混乱 | 计划不落地、重复刷已会内容、无法解释为什么 |

**共性（kernel 保证）**：所有场景都必须有"证据即完成"与"监督者主动审查"；差别只在 profile 的角色/节奏/交付物。

---

## 7. 与 Memoria / AOCI / Xerj 的关系

| 层 | 现在 | 目标 | 可行性 |
| --- | --- | --- | --- |
| **Memoria 产品** | 用户面对文档编辑器 + agent 对话 | 学习/笔记/复习场景可拉起"小团队"（拆分/出题/复习计划），团队产物直接落库 | ⏳ 需 Memoria 侧插件接入点（RPC/事件）；未验证 |
| **AOCI** | 仓库认知索引（MCP 工具） | 团队角色启动时用 AOCI 恢复"系统认知"，减少"凭记忆" | ⚠️ 本会话 MCP 已有 aoci 工具；**teammate 是否继承 MCP 工具未验证** |
| **Xerj** | 检索/记忆 MCP 服务 | 团队检索历史决策/教训（memory/decisions），避免重复踩坑 | ⚠️ 同上，未验证 |
| **DSH 插件形态** | 团队插件（experimental） | 可作为独立 DSH 插件分发给其他项目；kernel 固化、profile 可配置 | ⏳ roadmap 阶段 4；需解决分发/配置/版本兼容 |

**关键前提**：产品化（⑤）之前必须先让 kernel 在内部跑通并留下"用户可读"的产物（⑥），否则对外分发的是"一个更规范的团队"，而不是"用户能跟上细节的开发范式"。

---

## 8. 不可行 / 做不到 / 缺什么（诚实清单）

| 诉求 | 现状判定 | 缺什么 / 替代路径 |
| --- | --- | --- |
| **teammate 使用 schedule 工具（方案 A）** | ❌ **已验证不可行（2026-10-25）**：四工具都在工具表，但调用被拒 `{"code":"subagent_session","message":"A delegated subagent cannot use reminders."}`；**会话类型级**限制，换 preset 无效 | **替代**：Lead 代持定时（Lead 的 schedule 可用）→ 到期 `send_message` 唤醒 supervisor；或需 DSH 在 subagent/session 策略层开口（本插件做不到） |
| 插件后台定时器自触发（非工具） | ❌ **未发现 API**（`agent-team/src` 无 timer；`agentTeams.sendMessage` 需 caller Agent） | 用 schedule 工具（限 Lead 会话）替代；或需 DSH 提供 host-side activation API |
| 拦截/包装**任意**工具做门禁 | ⚠️ **机制存在**（`tools/execute` wrapper），**未原型验证**是否覆盖其他插件工具 | 10 行 wrapper 原型验证；失败则退到 repo 侧门禁 |
| 插件强制 git commit 带 Decision trailer | ❌ **做不到**（git 在插件外） | repo `pre-commit` hook + `team_audit.py` 事后检查 |
| 插件强制发布流程 | ❌ 发布是 repo 脚本/人操作 | **已落地** repo 侧 `scripts/agent/release_preflight.py`（review artifact 前置检查，exit 1）；待 release 规范修正后扩展标题/双语/造价检查 |
| teammate 继承 AOCI/Xerj MCP 工具 | ⚠️ **未验证** | spawn 后让 teammate 调 aoci/xerj 工具验证 |


---

## 9. 检验标准（防止"内部更规范但用户更看不懂"）

设计是否成功，只看**用户视角**；其中"用户能不能读懂"必须有**可测验收标准**（Lead 补充 2）：

> **定义（可测）：一个未参与本轮的读者，只读 digest（≤2 页），能否在 5 分钟内回答三个问题：**
> **① 这版做了什么？ ② 为什么这么做？ ③ 有什么已知问题？**
> 三问全部答对 ⇒ digest 合格；任何一问答不上 ⇒ 视为用户跟不上，回炉重写 digest（不是"加内容"，而是"减内容/换结构"）。

三条辅助测试：

1. **可追溯测试**：每个用户可见结论都能点到 `Decision:` / 任务板 id / artifact 路径 / 代码锚点（至少一条真实存在）。
2. **一致性测试**：文档声明与代码/测试一致（`team_audit.py::artifact_refs` 类检查对**用户可见文档**同样生效）。
3. **诚实测试**：digest 必须包含"已知问题/未做什么"（参照本 digest 的决策点与 release record 的已知问题段）；只写成绩不写缺口 = 不合格。

如果方案只让团队内部更"规范"但用户还是看不懂 ⇒ 判为跑偏，回炉。
