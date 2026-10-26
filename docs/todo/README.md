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

| 文件 | 对应 todo 章节 | 搬迁日期 | 说明 |
| --- | --- | --- | --- |
| [13-agent-panel.md](13-agent-panel.md) | §13 应用内对话（Agent 面板） | 2026-10-26 | AG01–AG108 行原文 + 注记（逐字）；行级锚点 `#ag01`… |
| [12-build-table.md](12-build-table.md) | §12 知识库与维护机制·施工总表 | 2026-10-26 | 施工总表原文 + 节区注记（逐字）；行级锚点 `#b2`…`#e3`、节区 `#intro`…`#residual` |
