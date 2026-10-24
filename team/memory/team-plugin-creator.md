# 记忆卡：team-plugin-creator

<!-- team-memory-card/v1 · bounded to 8 KiB · omitted 13 older section(s) · truncated: true -->

## 仍未闭环（已如实告知）
1. **`team_preflight` 不在 Lead 工具清单**：字节级核对重建后 asar 确认工具定义已在包内（`team_preflight` 9 次、`MEMORY_WRITE_VALUE_SCHEMA` 2 次），仓库无静态 tool 白名单；判断是会话工具清单快照早于重建——请 Lead 重启后开新会话复查，并把真实工具列表发我。已同时把 `TEAM_PLAN_REF_REQUIRED` 文案改为内联四条义务，避免依赖该工具造成死循环。
2. 轨迹为读取时物化、非实…（结论已截断）
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
- 工具 edit 失败：Error: cannot edit "D:\deepseek-harness\packages\experimental\agent-team\tests\team.spec.ts": file changed since it was read — re-read the file, then retry
- 工具 edit 失败：Error: cannot modify "D:\deepseek-harness\packages\experimental\agent-team\tests\team.spec.ts": file has not been read — read the file, then retry
- 工具 edit 失败：Error: cannot modify "D:\deepseek-harness\packages\experimental\tool-agent-team\tests\tool-team.spec.ts": file has not been read — read the file, then retry
- 工具 edit 失败：Error: cannot edit "D:\deepseek-harness\packages\experimental\agent-team\src\memory.ts": file changed since it was read — re-read the file, then retry
### 我留下的坑 / 下一个人该从哪开始
authority: machine
- 未完成任务 task-108「BUG-1b 残留：inherit 路径仍注入未截断的 assistant 原文（卡已修好，inherit 没修）」（pending）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方「最近结论」时请人工标注被推翻项）

## team-plugin-creator · BUG-1b 残留：inherit 路径仍注入未截断的 assistant 原文（卡已修好，inherit 没修）
<!-- task-id: task-108 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-87「DSH 插件：记忆卡 + 成员记忆继承（E1–E5 插件强制点 / 8KiB 卡 / 50KiB 注入预算）」：packages/experimental/agent-team/src/memory.ts, packages/experimental/agent-team/src/roster.ts, packages/experimental/tool-agent-team/src/index.ts, packages/experimental/agent-team/tests/team.spec.ts, docs/persistence-changes/2026-10-24-team-memory-cards.md
- 完成任务 task-89「DSH 插件：把义务变成工具返回值 —— team_preflight + 版本级任务强制 planRef（不依赖 Lead 记忆）」：packages/experimental/agent-team/src/preflight.ts, packages/experimental/agent-team/src/task-board.ts, packages/experimental/tool-agent-team/src/index.ts, packages/experimental/agent-team/tests/team.spec.ts, docs/persistence-changes/2026-10-24-team-preflight-planref.md
- 完成任务 task-95「轨迹追踪 L1+L2：结构化工作轨迹事件流（不是 transcript）+ 可查询投影」：packages/experimental/agent-team/src/trajectory.ts, packages/experimental/agent-team/tests/trajectory.spec.ts, packages/experimental/tool-agent-team/src/index.ts, packages/experimental/agent-team/README.md, docs/tool-catalog.md
- 完成任务 task-105「插件契约版本 + 升级通知 + 项目合规检查 —— 让其他项目团队知道插件变了（人：真实工程经验，必须遵循规范）」：packages/experimental/agent-team/src/contract.ts, packages/experimental/agent-team/tests/contract.spec.ts, docs/guides/team-plugin-migration.md, packages/experimental/tool-agent-team/src/index.ts, packages/experimental/agent-team/src/index.ts
- 完成任务 task-106「插件缺陷修复批：记忆卡归属/内容范围/正文泄漏（严重）+ completed 任务改派 + 轨迹单任务限额 + 主动物化」：packages/experimental/agent-team/src/memory.ts, packages/experimental/agent-team/src/roster.ts, packages/experimental/agent-team/src/task-board.ts, packages/experimental/agent-team/tests/team.spec.ts, packages/experimental/agent-team/tests/trajectory.spec.ts
- 完成任务 task-108「BUG-1b 残留：inherit 路径仍注入未截断的 assistant 原文（卡已修好，inherit 没修）」：packages/experimental/agent-team/src/memory.ts, packages/experimental/agent-team/tests/team.spec.ts, packages/experimental/agent-team/README.md
- 最近结论（原文，未经裁决）：本轮两项任务均已完成并回报 Lead；task-108 按指令未开工。

## task-106（缺陷批，已验收 6/7，剩余 BUG-5 路径问题由 Lead 自行在 Memoria 侧补）
提交 `cf1b2a9cf7`（23 files, +521/−118）：
- **BUG-1**：完成任务卡改为写入 **`task.ownerName` 的卡**，事实只列本任务 evidence（`taskScopedEvents` 按 completion turn 限定），**assistant 正文彻底不进卡**；完成者≠owner 时只记一行「代完成任务」。回归测试断言 ①Lead 卡无主段 ②owner 卡有 ③段内无历史 task id ④无 transcript。
- **BUG-2**：`completed` 任务可改 owner——须带非空 `reason` **且**原 owner 已 retired/inactive（比 Lead 的"或"更严，已获采纳），审计 `phase: reassign` / `outcome: owner-corrected`。
- **BUG-3**：轨迹改按任务分文件 `team/trajectory/<member>/<task>.jsonl`，**每任务** 64 KiB 上限（800 事件 >150 KB 实测截断到 ≤65536 + `truncated: true`）。
- **BUG-4**：complete / retire 时**主动物化**轨迹文件，不必先查询（两个 e2e 实测）。
- BUG-5 机制说明已写入 DSH 两包 README（中英）。

## task-105（契约版本 + 通知机制，已交付待验收）
提交 `2d6278db9c`（27 files, +946/−69）+ `c93fc082fa`（+48 文档）：
- `contract.ts`：`TEAM_CONTRACT_VERSION = 2` + 8 个 change id 的 changelog（含本日全部语义变更）；测试断言常量/changelog 一致。
- 项目声明 `team/plugin-contract.json`（配置 `contractPath`）；四态 `missing/outdated/ahead/ok` 实测，**ok 时零 notice**。
- 通知出现在工具响应：`spawn_teammate` / `team_task_create` / `team_task_update` / `retire_teammate` 带 `contractNotice`，另新增只读 `team_contract`（第 16 个工具）。
- 审计：`phase: contract` / `update-required|ok`，同一 notice 只审一次。
- 硬阻断：落后 ≥2 版本 ⇒ 写工具 `TEAM_CONTRACT_TOO_OLD`，只读工具仍可用；落后 1 版本仅警告（均已实测）。
- 文档：`docs/guides/team-plugin-migration.md`（中英成对，含每项"错误/怎么改" + Design/Impact/Rollback/Verification），迁移文档与 changelog 有机械核对测试；README/目录已同步 16 工具。

## 验证
- `vitest` **174 passed**（team + tool 两个包，含 contract.spec 8 例、服务契约 2 例、工具契约 1 例、BUG 回…（结论已截断）
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
- 工具 edit 失败：Error: cannot edit "D:\deepseek-harness\packages\experimental\agent-team\tests\team.spec.ts": file changed since it was read — re-read the file, then retry
- 工具 edit 失败：Error: cannot modify "D:\deepseek-harness\packages\experimental\agent-team\tests\team.spec.ts": file has not been read — read the file, then retry
- 工具 edit 失败：Error: cannot modify "D:\deepseek-harness\packages\experimental\tool-agent-team\tests\tool-team.spec.ts": file has not been read — read the file, then retry
- 工具 edit 失败：Error: cannot edit "D:\deepseek-harness\packages\experimental\agent-team\src\memory.ts": file changed since it was read — re-read the file, then retry
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方「最近结论」时请人工标注被推翻项）
