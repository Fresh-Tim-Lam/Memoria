# Team 插件方向：一页半摘要（给人看）

> 2026-10-25｜`todo-owner` 消化｜完整设计：`docs/design/team-plugin-vision.md`｜路线图：`docs/design/team-plugin-roadmap.md`

## 你要解决的那件事

你说的是：**团队不能只靠"记住规范"工作，要把义务做进插件流水；监督者要有自触发或契约强制审查；团队要能自我改革；不同场景要能换结构但保留共性；最终 team 插件要成为核心开发主体，让用户看到成体系的文档/细节/代码，而不是只被团队不断喂需求。**

我对这句话的理解（一句话）：**把「应该做」变成「不做就过不去」，同时让团队的工作对用户可读、可追溯。**

## 我们已经在做的（本轮实证，不是设想）

| 机制 | 现状 | 结论 |
| --- | --- | --- |
| `team_preflight(intent)` 返回义务清单 | 计划前必调，义务是**工具返回值** | ✅ 已固化，模板可复用 |
| 版本级任务缺 `plan_ref` | 工具**直接拒绝** | ✅ 已固化 |
| `complete` 无 evidence | 工具**直接拒绝** | ✅ 已固化（证据内容校验还不够） |
| `retire_teammate` 无记忆卡/Lead 裁决 | fail-closed | ✅ 已固化 |
| spawn 缺 `mode` | 源码 `args.mode ?? 'standard'` ⇒ **静默默认** | ❌ 仍是"靠记住"，建议改成拒绝 |
| 决策 trailer（L10） | 只有 `team_audit` 事后 WARN | ❌ 提交层无强制，需 repo hook |
| 「声明≠事实」8 次 | 全靠人抓 | ❌ 无机器拦截 |
| 监督者主动审查 | **无机制** | ❌ 待建（本方向重点） |

## 监督角色：两个方案的可行性（你要的结论）

**方案 A（规律自触发）**：✅ **可行**，但走"schedule 工具"而不是"插件后台定时器"。
- 证据：DSH 的 schedule 是 Host-owned，**到期会 resume 原 Session 投递提醒**（`docs/subsystems/schedule.md:5,251-252`；`apps/desktop-host/package.json` 已依赖 `@deepseek-ai/dsh-schedule`）。
- ⚠️ **唯一未验证关键点**：**teammate 的 preset 是否挂载 `tool-schedule`**（工具是 preset-scoped）。验证成本 = spawn 一个 teammate 让它调 `schedule_list`，10 分钟。
- 若不可用：改 teammate preset，或给团队插件加 `team_reminder` 工具。

**方案 B（契约强制审查点）**：✅ **可行**，两个落点：
- **repo 侧**（现在就能做）：发版/release 脚本前置检查"是否有 supervisor 审查 artifact"，缺失即拒。
- **插件侧**（需原型）：`tools/execute` wrapper 是官方扩展点（`docs/subsystems/tools.md:65,313`），可包装工具调用做门禁；但**尚未验证能否拦截其他插件的工具**（10 行原型可定论）。

**推荐：A + B 先做 A，B 的 repo 侧立即上，插件侧等原型。**

## 分层模型（解决"不同场景不同团队但有共性"）

- **kernel（所有场景共用，插件强制）**：义务即工具 / 证据即完成 / 角色生命周期 fail-closed / 版本三查+plan_ref / R1 单向门 / 可审计 / 用户可读 digest。
- **profile（按场景换，声明式）**：角色集合 / 触发关系 / 审查节奏 / 写域 / 交付物 / 用户文档模板。
- 三个场景（软件仓库开发 / 知识库内容创作 / 学习复习陪练）的角色表、审查关系、交付物已在 vision §6。

## 诚实的边界（不假装插件万能）

| 做不到 / 需确认 | 缺什么 / 替代 |
| --- | --- |
| 插件后台定时器自触发 | 无 API；用 schedule 工具（Host resume）替代 |
| 插件强制 git commit 带 Decision | git 在插件外；用 repo pre-commit hook |
| 插件强制发布流程 | 发布是脚本/人；用 release 脚本前置检查 |
| 拦截任意工具做门禁 | `tools/execute` wrapper 机制存在，**未原型验证** |
| teammate 能用 AOCI/Xerj MCP | **未验证**（MCP 是否随 spawn 继承） |

## 需要你裁决的 3 个决策点

1. **监督角色先走哪条**：
   - **A（推荐）** 先做 schedule 自触发（10 分钟验证 + supervisor 模板），B 的 repo 侧检查同期上；
   - B 先做契约强制审查门（改动大、涉及发版流程）；
   - 暂不做（保持现状）。
2. **插件版本策略（v3→v4）**：
   - **A（推荐）** 先重建 DSH 让运行插件=源码 v4，并把"声明>插件"改成**拒绝版本级任务**；
   - B 锁定 v3，把项目声明降回 3（避免"声明了但插件不支持"）；
   - C 只发通知（现状，不推荐）。
3. **产品化优先级**：
   - **A（推荐）** 先把内部 kernel 跑通 + 生成"用户可读 digest"（P1–P3），再谈 DSH 插件分发；
   - B 优先做独立 DSH 插件包（对外分发）；
   - C 优先接 Memoria 学习/复习场景（产品化先行）。

（完整路线图：P0 版本对齐 → P1 义务强制化 → P2 监督角色 → P3 profile+试点 → P4 产品化；每阶段都有可验证完成定义与"需查 DSH API"标注。）
