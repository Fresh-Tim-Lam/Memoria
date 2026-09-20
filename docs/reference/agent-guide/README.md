# Memoria 功能 · 排版 · 交互说明书（Agent 版）

> **用途**：把「Memoria 界面上有什么、每一处长什么样、怎么交互」写到**可据以工作**的粒度——供外部集成方（如把 Memoria 嵌进 dsh 的插件、Trae 智能体）与后续 Agent 快速建立准确心智模型，避免按猜测改代码、按印象写适配。
> **目标读者**：在 Memoria 之上做集成 / 移植 / 对齐的 Agent 与人；给 Memoria 写前端改动的人。
> **关联文档**：[architecture.md](../architecture.md)（分层与数据流）、[preview-formats.md](../preview-formats.md)（**渲染语法权威**）、[hard-constraints.md](../hard-constraints.md)（红线）、[import-spec.md](../import-spec.md)（导入契约）、[i18n-inventory.md](../i18n-inventory.md)（文案清单）、[glossary.md](../glossary.md)（术语）、[kb-agent.md](../../design/kb-agent.md)（知识库侧智能体契约）。
> **状态**：生效中（随代码演进维护），2026-09-15。

---

## 1. 怎么用这份说明书

1. **先读 01** 建立坐标系（窗口 → 顶栏 → 侧栏 → 文档区 → 状态栏），再按你要动的区域跳转对应篇。
2. 每篇末尾的**代码锚点表**能直接定位到 `src/memoria/ui/static/app/**` 的实现位置。
3. **渲染语法**（`[[\h]]` / `[[\c]]` / 图片属性 / 公式 / Mermaid 等）以 [preview-formats.md](../preview-formats.md) 为权威，本套只描述"渲染后的 DOM 与交互"，不重复语法清单。
4. 写前端改动前先读 §3 维护约定 —— 本套记录的是**现状**，改完要同步更新受影响段落。
5. 见到 **⚠️ 待确认** 的条目：当时未能从代码取证，**不要当作事实使用**。

## 2. 篇目

| # | 文件 | 覆盖范围 | 状态 |
|---|---|---|---|
| 01 | [01-shell-and-layout.md](./01-shell-and-layout.md) | 窗口外壳与整体布局：窗口 chrome / 顶栏（**含「对话」开关 `#btn-agent`**）/ 侧栏（**3 页签**）/ **右侧「对话」停靠栏 `#-agent-dock`**（§2.4，含**文档区最小宽度保护 `CONTENT_MIN_PX=360`**：期望宽度 vs 生效宽度、空间不足自动隐藏且不回写盘；**历史会话下拉 `#agent-history`** 与**等待计时「生成中… Ns」**）/ 文档区 / 状态栏 / flash 浮层 / 弹窗层级 / 缩放 | ✅ 417 行 |
| 02 | [02-file-tree-and-nav.md](./02-file-tree-and-nav.md) | 文件树与导航：树渲染 / 右键菜单 / F2 / 标签页 / 前进后退 / 空态 | ✅ 259 行 |
| 03 | [03-editor-and-formatting.md](./03-editor-and-formatting.md) | 编辑器与格式：源码编辑 / 格式工具栏 / 编辑块工具栏 / 撤销重做 / 粘贴复制 | ✅ 240 行 |
| 04 | [04-preview-and-rendering.md](./04-preview-and-rendering.md) | 预览与渲染：三视图切换 / 渲染管线 / 渲染后 DOM 与交互 / KP 高亮语义 | ✅ 194 行 |
| 05 | [05-knowledge-points.md](./05-knowledge-points.md) | 知识点：KP 列表 / hover / KP 弹窗各页 / 配置窗三 Tab / 待确认 / 范围编辑 | ✅ 228 行 |
| 06 | [06-links-and-graph.md](./06-links-and-graph.md) | 链接与图谱：链接创建·编辑·删除 / 边类型 / 2D·3D 图谱 / 样式与分组 / **§2.10 引用解析与引用审计（agent 侧只读，2026-09-20）** | ✅ 319 行 |
| 07 | [07-search-and-images.md](./07-search-and-images.md) | 检索与图片：搜索框与范围 / 结果跳转 / 图片插入·管理·属性·诊断 | ✅ 253 行 |
| 08 | [08-import-export-and-check.md](./08-import-export-and-check.md) | 导入导出与检查：导入向导（三源/冲突/结果）/ 导出（预留）/ 检查面板与徽标 | ✅ 253 行 |
| 09 | [09-settings-i18n-and-shortcuts.md](./09-settings-i18n-and-shortcuts.md) | 设置页签 / 语言切换 / 快捷键总表 | ✅ 260 行 |
| 10 | [10-data-layout-and-host-embedding.md](./10-data-layout-and-host-embedding.md) | 磁盘布局与事实源 / 红线 / **把 Memoria 嵌进别的宿主**（桥、无窗口模式、iframe 可行性）；§2.15 为应用内对话的 **6 个 RPC**（含 M1c **只读会话历史** `agent_sessions_list` / `agent_session_load`）、**多轮续聊**（按 `session_id` 回放，容量上限 40 条 / 32000 字符）与 `config/agent.json`、会话 JSONL | ✅ 297 行 |

## 3. 首轮取证发现的既有文档错误（待修）

撰写本套时逐处对代码取证，发现**既有文档/规范与代码不符**，本套以代码为准并把清单留在此处：

| 位置 | 文档说法 | 代码事实 | 影响 |
|---|---|---|---|
| [deepseek-harness-integration.md](../../design/deepseek-harness-integration.md) §4.2/§7.1、[architecture.md](../architecture.md):21-23,44 | 「`static_server` 的 **`/rpc`** 暴露 UIAPI」 | `static_server.py` 只有 `@app.get("/")`(:114) 与 `@app.get("/<path:path>")`(:130)，**无 `/rpc`**。真实调用链：pywebview `js_api`（`app/shell/pywebview.py:471-484`）或 PyQt6 QWebChannel 单槽 `UIAPIRpc.invoke`（`presentation/api/api_rpc.py:44-67`） | ⚠️ **高**：任何"HTTP POST /rpc 驱动 Memoria"的集成方案**现在跑不通**。注意：`/rpc` 是**测试 harness**（`docs/example/rich-content-test/_harness.py`，本地忽略目录）自建的端点，不是产品能力 —— 本套 10 篇中凡提 `/rpc` 均指 harness |
| [hard-constraints.md](../hard-constraints.md):31 | 「保存自动清理未引用图片（物理删除）」 | `services/document.py:317-323` 明确：保存**不触发**图片清理；清理只在显式 RPC `cleanup_unused_images`（`ui.py:867`） | ⚠️ 中：按该条设计实现会**误删仍被引用的图片** |
| [AGENTS.md](../../../AGENTS.md) §1、[kb-agent.md](../../design/kb-agent.md):70、deepseek-harness-integration.md 「事实源」口径 | 三处表述不一致 | 以 AGENTS.md §1 为单一事实源表，另两处需对齐 | ⚠️ 低：口径漂移 |

> 以上**本次未擅自修改**（涉及项目负责人维护的契约与参考文档）。

## 4. 维护约定

**触发条件**：新增/修改 Memoria 界面、交互、快捷键或渲染行为后。

1. **事实源是代码**：每处描述必须带 `文件:行号` 证据锚。无锚点的描述视为未证实，不得作为工作依据。
2. **只写现状，不写愿望**：与 [ledger-maintenance.md](../../conventions/ledger-maintenance.md) 同口径 —— 文档描述的是"代码现在怎么做"，不是"设计打算怎么做"；未做的写进「未证实/待确认」并注明。
3. **不重复权威**：渲染语法 → [preview-formats.md](../preview-formats.md)；导入格式 → [import-spec.md](../import-spec.md)；文案键 → [i18n-inventory.md](../i18n-inventory.md)；红线 → [hard-constraints.md](../hard-constraints.md)。本套只做**引用 + 补充界面/交互层**。
4. **新增区域即登记**：新界面区域/弹窗/快捷键 → 在对应篇补一节，并在本文 §2 篇目表更新。
5. **本套不是契约**：对外契约（双方必须遵守的约定）放 [docs/conventions/](../../conventions/README.md)；本套是"理解性参考"。
6. **改动登记**：批量修订本套时，在 [docs-management.md §4.2](../../conventions/docs-management.md) 追加一行。
