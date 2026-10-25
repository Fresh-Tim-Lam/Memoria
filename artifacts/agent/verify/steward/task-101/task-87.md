# 任务档案：task-87（只读投影）

> 生成 2026-10-24T19:42:03+08:00；源：board team/team-board-snapshot.json@2026-10-24T19:34:19+08:00 (ok) · dispatch-log 35 条 · git 3cd7a13f · decisions missing
> 投影不是事实源，删除可重建（work_record.py task-101）。

## 1. 任务板
- 来源：snapshot.tasks（快照 tasks[] 无 description/时间戳（设计 G2）；live 任务板为准）
- status：**completed**；owner：team-plugin-creator；revision：4
- subject：DSH 插件：记忆卡 + 成员记忆继承（E1–E5 插件强制点 / 8KiB 卡 / 50KiB 注入预算）
- writeScopes：docs/persistence-changes

## 2. 派发记录（1 条）
- 10-24 17:34 `spawn` lead → team-plugin-creator：DSH 插件成员记忆继承：P0 记忆卡（≤8KB，append，带免责）+ P1 inherit（≤50KB 报错不截断）

## 3. 相关提交（git log --grep=task-87，1 条）
- `4059dc78be` 10-24 17:34 feat(team): 记忆卡目录约定（team/memory/）—— 压缩裁决过的记忆，不复制会话

## 4. 决策（关联裁决）
- **NOT_ESTABLISHED**：team/decisions.jsonl 未建立（task-102/task-99 未落地）—— 不是「无决策」

## 5. 证据路径解析（5 条）
- [missing] `packages/experimental/agent-team/src/memory.ts` —— 路径不存在且未被 .gitignore 排除（疑似 DSH 仓库相对路径；不在本仓库 ⇒ 需在 DSH checkout 里验证）
- [missing] `packages/experimental/agent-team/src/roster.ts` —— 路径不存在且未被 .gitignore 排除（疑似 DSH 仓库相对路径；不在本仓库 ⇒ 需在 DSH checkout 里验证）
- [missing] `packages/experimental/tool-agent-team/src/index.ts` —— 路径不存在且未被 .gitignore 排除（疑似 DSH 仓库相对路径；不在本仓库 ⇒ 需在 DSH checkout 里验证）
- [missing] `packages/experimental/agent-team/tests/team.spec.ts` —— 路径不存在且未被 .gitignore 排除（疑似 DSH 仓库相对路径；不在本仓库 ⇒ 需在 DSH checkout 里验证）
- [missing] `docs/persistence-changes/2026-10-24-team-memory-cards.md` —— 路径不存在且未被 .gitignore 排除

## 6. 弯路（memory 卡段）
- 无（卡机制 task-87 刚起步；见 data_gaps）

## 7. 数据缺口（显式，不静默）
- 决策索引未建立（team/decisions.jsonl 不存在；task-102/task-99 未落地）⇒ 裁决字段缺失
- memory 卡中没有该任务段（task-87 卡机制刚起步；「弯路」暂只能从报告/提交反查）

