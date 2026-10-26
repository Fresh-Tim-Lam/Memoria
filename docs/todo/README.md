# docs/todo/ —— 台账附件目录（活跃详情）

> **用途**：存放 `docs/todo.md` **活跃详情**的附件文档（每节一份 `<NN>-<slug>.md`），使 `todo.md` 退化为**索引**。
> **目标读者**：项目负责人（用户）与 AI Agent（维护台账者）。
> **关联文档**：[todo.md](../todo.md)（索引页）、[docs-management.md](../conventions/docs-management.md) §4.2（台账规则与预算）。

## 规则（2026-10-26 人批准）

1. **唯一事实源**：`todo.md` 只放 **ID / 标题 / 状态 / 一行摘要 / 详情链接**；本目录放**详情**（原文逐字搬迁，可再整理但不得丢信息）。
2. **一个章节一份**：`<NN>-<slug>.md`（如 `13-agent-panel.md`）。单节过大允许 `<NN>-<slug>-<part>.md`，不建子目录。
3. **必须有索引行**：本目录每个 `.md`（本 README 除外）必须被 `todo.md` 至少一个链接引用；孤儿 = WARN。
4. **禁止双事实源**：同一段详细内容**不得**既在 `todo.md` 又在附件各写一版（状态以 todo 索引行为准，详情以附件为准）。
5. **历史归档仍进 `docs/design/`**：本目录只放**活跃/现役**详情；已收口条目按既有规则归档到 `docs/design/**`（如 `ledger-archive-2026.md`、`agent-panel-batches.md`），不搬进本目录。
6. **机检**：`python scripts/check_todo_size.py` 会校验 体积/单元格/死链/孤儿/未索引化，并含 `--selftest`。

## 现役文件

| 文件 | 对应 todo 章节 | 搬迁日期 | 大小 |
| --- | --- | --- | --- |
| [00-focus.md](00-focus.md) | §0 当前进行中（焦点） | 2026-10-26 | 2251 B |
| [01-config-window.md](01-config-window.md) | §1 配置窗口 | 2026-10-26 | 2253 B |
| [02-links.md](02-links.md) | §2 链接系统 | 2026-10-26 | 1234 B |
| [03-search.md](03-search.md) | §3 检索引擎 | 2026-10-26 | 1507 B |
| [04-graph.md](04-graph.md) | §4 图谱 | 2026-10-26 | 1714 B |
| [05-editor.md](05-editor.md) | §5 编辑器/富文本 | 2026-10-26 | 7631 B |
| [06-file-tree.md](06-file-tree.md) | §6 文件树管理 | 2026-10-26 | 1126 B |
| [07-import-media.md](07-import-media.md) | §7 导入与媒体 | 2026-10-26 | 1619 B |
| [08-shell-release.md](08-shell-release.md) | §8 壳与发布 | 2026-10-26 | 2587 B |
| [09-learning-products.md](09-learning-products.md) | §9 学习产品（V2+） | 2026-10-26 | 1487 B |
| [11-notes.md](11-notes.md) | §11 备注/散记 | 2026-10-26 | 1747 B |
| [ideas.md](ideas.md) | 全项目（人的需求原始台账） | 2026-10-27 | 28 条人提出需求/想法 + 1 条补充裁决；状态/去向/时间 |
| [12-build-table.md](12-build-table.md) | §12 知识库与维护机制·施工总表 | 2026-10-26 | 7822 B |
| [13-agent-panel.md](13-agent-panel.md) | §13 应用内对话（Agent 面板） | 2026-10-26 | 21828 B |
| [14-plan-047.md](14-plan-047.md) | §14 0.4.7 收摊计划 | 2026-10-26 | 6926 B |
| [15-plan-048.md](15-plan-048.md) | §15 0.4.8 范围 | 2026-10-26 | 2899 B |
| [16-arch-refactor.md](16-arch-refactor.md) | §16 架构重构 S1–S5（已撤回） | 2026-10-26 | 2653 B |
| [17-team-plugin.md](17-team-plugin.md) | §17 团队插件完善项 | 2026-10-26 | 3722 B |
