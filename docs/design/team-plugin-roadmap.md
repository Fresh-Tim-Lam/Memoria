# Team 插件路线图：从当前 v3/v4 到「核心开发主体」

> **状态**：设计稿（2026-10-25）｜**作者**：`todo-owner`｜配套：`team-plugin-vision.md`（为什么/做什么）
> **版本策略**：本文用「阶段」而不是版本号，避免与产品版本（0.4.8/0.5.0）混淆；每个阶段可独立验收。
> **图例**：✅ = 本轮已验证可行（有证据）｜⚠️ = 机制存在但未原型/未验证｜❓ = 需查 DSH API（当前查不到或不确定）｜🔧 = 需改 DSH 插件代码

---

## 0. 当前状态（2026-10-25，实测）

| 项 | 值 | 证据 |
| --- | --- | --- |
| 运行中团队插件版本 | **3**（`contractNotice.pluginVersion=3`） | 本会话所有任务完成回执里的 `contractNotice` |
| 项目声明契约版本 | **4**（`team/plugin-contract.json` `contractVersion:4`） | 文件 + `status:ahead` |
| DSH 源码里团队插件版本 | **4**（`TEAM_CONTRACT_VERSION = 4`） | `D:\deepseek-harness\packages\experimental\agent-team\src\contract.ts:13` |
| 团队工具数 | 17（spawn/send/list/wait/interrupt/retire/memory/trajectory/preflight/task create/get/list/update/contract/model 等） | `tool-agent-team/README.md` |
| 契约机制 | `team/plugin-contract.json` + `contractNotice`（不阻断） | `contract.ts:100-207` |
| 调度机制 | Host-owned schedule，到期 **resume 原 Session** 投递 | `docs/subsystems/schedule.md:5,251-252`；`apps/desktop-host/package.json` 依赖 `@deepseek-ai/dsh-schedule` |
| 工具拦截机制 | `tools/execute` wrapper（`repeat-tool-reminder` / `timeout-policy` 同机制） | `docs/subsystems/tools.md:65,313` |

**核心矛盾**：源码已是 v4、项目声明 v4，但**运行中的 App 仍是 v3** ⇒ 任何"依赖 v4 行为"的设计必须先解决「插件版本 vs 声明版本」的兼容与升级路径（本文件 §1 的 P0）。

---

## 阶段 P0：版本对齐与契约升级（前置，1–2 天）

**目标**：消除"声明了但插件不支持"的假绿。

| # | 任务 | 可验证完成定义 | 类型 |
| --- | --- | --- | --- |
| P0-1 | 查清 v3→v4 差异：源码 `TEAM_CONTRACT_VERSION=4` 相对运行 v3 多了什么（`reviewedChanges` 11 条 vs 运行版本行为） | 产出差异表（逐条：工具/返回值/拒绝条件），每条附 `file:line` 或"查不到" | ⚠️ 需对照源码 |
| P0-2 | **插件升级路径**：重建 DSH App 使运行插件 = 源码 v4；或明确锁定 v3 并降 `team/plugin-contract.json` 到 3 | 重建后 `contractNotice.status` 从 `ahead` → 消失（或 `declaredVersion=3` 且无 mismatch）；记录一次实测收据 | 🔧 |
| P0-3 | 契约升级策略：声明 > 插件 ⇒ **版本级任务拒绝**（而非仅通知） | 造一个声明 v99 的临时项目 fixture，跑 `team_task_create`（版本级）必须被拒；恢复 fixture | 🔧 需插件代码（契约 v5 候选） |
| P0-4 | 明确 v3/v4 双版本兼容窗口（若某些项目仍用 v3）：插件对 v3 声明只警告不拒；v4 声明才启用新义务 | 单测/文档表：声明版本×插件版本 的 4 种组合行为 | ⚠️ 设计 |

**为什么先做 P0**：本轮 0.5.0 越序发布的根因之一就是"机制版本与声明不一致时只发通知"；不先解决，后续所有"契约强制"都可能落空。

---

## 阶段 P1：把「靠记住」的义务全部变成强制点（2–3 周）

**目标**：vision §3 表里 12 条义务，凡工具层可强制的都强制；不可强制的显式下沉。

| # | 任务 | 可验证完成定义 | 类型 |
| --- | --- | --- | --- |
| P1-1 | `spawn_teammate` 缺 `mode` ⇒ **拒绝**（替代 `args.mode ?? 'standard'`，`tool-agent-team/src/index.ts:617`） | 单测：不传 mode ⇒ 错误码；传错值 ⇒ 错误码；现有调用全部补 mode | 🔧 + ✅ 缺口已证 |
| P1-2 | `complete` 证据增强：evidence 项加 `kind`（commit/report/artifact）与存在性校验（commit 必须 `git cat-file -e`；report 必须非空且含被完成任务 id） | 三条负例必须红：不存在的 commit、空 report、路径存在但内容无关；现有 evidence 不回归 | 🔧 中等 |
| P1-3 | `claim` 写域冲突 ⇒ **拒绝**（复用现有 `write_scope` 检查逻辑；当前只是 WARN） | 两个存活成员 claim 重叠写域 ⇒ 第二个被拒并提示；`team_task_update(edit)` 改窄写域后可通过 | 🔧 需 task-board 代码 |
| P1-4 | `team_decide` 工具（写 `team/decisions.jsonl`，schema 校验 Decision/Why/Alternatives）+ repo `pre-commit` hook 检查 T1/T3 提交 | 插件侧：`team_decide` 落盘可被 `decide.py check` 验证；repo 侧：故意提交无 trailer 的 T1 提交 ⇒ hook 拒（先证红） | 🔧 + 下沉 A |
| P1-5 | 「声明≠事实」证据契约：`team_preflight` 返回义务中增加"claim 必须绑定可执行验证（测试名/命令/真机证据路径）" | 以本轮 8 个实例为 fixture：每条声明若拿不出绑定验证 ⇒ 报告/任务标记 `unverified`，不能升 ✅ | ⚠️ 设计 + 部分机检 |
| P1-6 | 用户可读 digest 的**最小骨架**：`team_digest` 工具（读任务板+decisions+最近 artifact，输出 markdown） | 对当前版本生成一份 digest，包含：版本目标/实际/偏离/未闭环/证据锚；人工按 vision §9 三条测试通过 | ⚠️ 需设计格式 |
| P1-7 | 用户可见文档同样纳入 artifact_refs 校验（防止 digest 引用不存在路径） | `team_audit.py` 对 `docs/design/team-plugin-*.md` 的路径引用检查 FAIL=0 或仅历史 WARN | ✅ 已有脚本可复用 |

**P1 完成定义（整体）**：视界测试 = 新会话里让一个 teammate 尝试"跳过证据关闭任务 / 不传 mode spawn / 重叠写域 claim"三种违规，**全部被工具拒绝**；同时 `team_audit.py FAIL=0`。

---

## 阶段 P2：监督型角色机制（1–2 周）

**依赖**：P0 完成（版本对齐）+ P1-1/2（工具拒绝基础设施）。

| # | 任务 | 可验证完成定义 | 类型 |
| --- | --- | --- | --- |
| P2-1 | **验证 teammate 能否用 schedule 工具**：spawn 一个 teammate，让它 `schedule_create` 一条 1 分钟后提醒；到点观察该 teammate 是否被 Host resume 并收到提醒 | 一次真实会话证据：提醒到期 ⇒ teammate 新回合开始 ⇒ 输出确认；若失败，记录缺什么（preset 未挂载/权限） | ⚠️ 1 次验证，最能定性 |
| P2-2 | **supervisor 角色模板**：recurring reminder（如每日 09:00/每 2h）+ 审查任务书（任务板快照/未闭环/最近产物/输出格式） | supervisor 连续 2 个周期产出的 review 报告落盘，且报告里每条结论有证据锚；被审对象能收到并响应 | ✅ 若 P2-1 成功 |
| P2-3 | **审查报告格式与挂账**：review artifact schema（verdict/证据/建议/时间）+ 结论自动挂任务板（债务/任务） | 报告 schema 校验通过；至少 1 条 review 结论被转成任务并有 owner | 🔧 小 |
| P2-4 | **release 前置审查门**（方案 B）：repo release 脚本检查 supervisor review artifact + decisions，缺失则拒 | 造一个"无 review artifact"的发版分支 ⇒ 脚本拒绝（先证红）；补 review 后通过 | ✅ 下沉 A，可立即做 |
| P2-5 | （可选）插件 `tools/execute` wrapper 原型：拒绝一个指定工具 | 10 行 wrapper 让某工具调用返回拒绝；记录 wrapper 是否覆盖其他插件工具 | ⚠️ 原型验证 |

**P2 完成定义（整体）**：至少一个 supervisor 实际运行 ≥2 个周期，产出 ≥2 份有人跟进结论的 review 报告；release 脚本对"无审查"必红。

---

## 阶段 P3：场景 profile 与可复用骨架（2–3 周）

**依赖**：P1（kernel 强制点）。

| # | 任务 | 可验证完成定义 | 类型 |
| --- | --- | --- | --- |
| P3-1 | 定义 `team/profile/<name>.json` schema（角色/触发/审查/写域/交付物/文档模板） | schema 校验工具；至少 3 个 profile 实例（软件仓库/知识库创作/学习复习）通过校验 | ⚠️ 设计 |
| P3-2 | kernel 与 profile 的分离校验：profile 不得关闭 kernel 强制点（如不得声明"complete 不需要 evidence"） | 造违规 profile ⇒ 拒绝加载；合法 profile ⇒ 加载并生成对应任务书模板 | 🔧 需插件支持 |
| P3-3 | 一个真实场景试点（建议知识库内容创作，风险低）：按 profile 拉起 4 角色跑 3 天 | 产出：章节交付物 + 审查报告 + digest；用户按 vision §9 测试能读懂 | ⏳ 试点 |
| P3-4 | 团队自维护（论点③）：profile/契约变更走"提议→审查→迁移→版本+1"流程，且变更本身留 Decision | 一次真实的 profile 变更：有提议文档、审查记录、迁移说明、版本号；可由 `team_audit` 复算 | ⚠️ 设计 |

**P3 完成定义（整体）**：同一套 kernel 下，至少 2 个场景 profile 各跑出一次可读 digest；改动 profile 不需要改插件代码。

---

## 阶段 P4：产品化（DSH 插件 / Memoria 场景 / AOCI+Xerj）（4–8 周，需人裁决投入）

**依赖**：P1–P3（内部跑通 + 用户可读产物）。

| # | 任务 | 可验证完成定义 | 类型 |
| --- | --- | --- | --- |
| P4-1 | **用户可读文档体系**：每个版本/项目自动生成 `docs/design/<project>-digest.md`（目标/实际/决定/证据/代码锚点） | 用 Memoria 0.4.7 数据生成一份完整 digest，用户/新人按 §9 三项测试通过 | ⚠️ 设计 + 工具 |
| P4-2 | **Memoria 场景接入**：学习/笔记/复习场景的 profile 能拉起小团队，产物直接落 `.memoria/` | 一个真实学习任务跑完：知识点拆分→出题→复习计划→review，产物落库且可回放 | ❓ 需 Memoria 侧接入点（RPC/事件），未验证 |
| P4-3 | **AOCI/Xerj 集成**：角色启动时用 AOCI 恢复系统认知、用 Xerj 检索决策/历史 | teammate 能调用 aoci/xerj MCP 工具（需验证 MCP 是否随 spawn 继承）；一次任务里至少用一次 | ⚠️ 未验证 |
| P4-4 | **独立 DSH 插件包**：kernel 固化 + profile 可配置 + 版本契约；可被其他项目安装 | 另一个示例项目用插件拉起团队并跑通 P1 的三种拒绝 | 🔧 分发/打包 |
| P4-5 | 发布策略：对外分发前必须先在 Memoria 内部跑满 2 个版本（避免"实验室范式"直接给用户） | 内部至少 2 个版本使用记录 + 0 次越序/回滚 | ⚠️ 纪律 |

**P4 完成定义（整体）**：外部项目安装插件即可获得 kernel 强制点；Memoria 一个真实学习场景跑通；用户能读懂 digest。

---

## 1. 依赖关系与推荐顺序

```
P0（版本对齐，1–2d）
  ↓
P1（义务强制化，2–3w）
  ↓
P2（监督角色，1–2w）—— P2-1 验证可提前到 P1 期间做（1 次 spawn 即可）
  ↓
P3（profile + 试点，2–3w）
  ↓
P4（产品化，4–8w，需人批准投入）
```

**可立即做、无依赖的三件**（建议本周内）：
1. **P2-1**：1 次 spawn 验证 teammate 能否用 schedule（决定 A 方案成立与否，成本 10 分钟）。
2. **P2-4**：release 脚本前置检查（repo 侧，1 天）。
3. **P1-1**：`mode` 缺失拒绝（若允许改 DSH 插件代码；否则先加机检 FAIL）。

## 2. 每阶段的风险

| 阶段 | 主要风险 | 缓解 |
| --- | --- | --- |
| P0 | 重建 App 影响当前会话（工具表快照） | 在新会话验证；记录升级前后 `contractNotice` |
| P1 | 拒绝变多 ⇒ 流程变慢/误拒 | 每条拒绝配"如何修复"提示 + 必红/必绿 fixture |
| P2 | supervisor 变成"又一个看板"（写了没人看） | 报告结论必须挂任务板 + 下一周期复查上一周期结论 |
| P3 | profile 变成"配置地狱" | 只允许 6 个字段；kernel 不允许关闭；一个场景先试点 |
| P4 | 产品化过早，用户拿到半成品 | P4-5 内部跑满 2 版本；digest 验收先于分发 |

## 3. 与产品版本的关系（不混版）

- 本路线图**不占用** 0.4.8（KG 调研 + P1 修复）与 0.5.0（架构重构）的版本范围。
- 建议团队插件能力迭代**独立于产品版本**（它服务团队自己，不是 Memoria 功能）；若要随产品发布，需人单独裁决（类似 0.5.0 的 R1 门）。
