# 8. 壳与发布 — 活跃详情（原文逐字）

> **本文件是 `docs/todo.md §8` 的活跃详情**（2026-10-26 索引化搬迁，**原文逐字**，未改写）。
> **状态事实源 = `docs/todo.md` 索引行**；本文件只放详情。历史归档仍在 `docs/design/**`，不在此重复。

<a id="p01"></a><a id="p02"></a><a id="p03"></a><a id="p04"></a><a id="p05"></a><a id="p06"></a><a id="p07"></a>

## 原文（逐字，自 docs/todo.md 搬迁）

## 8. 壳与发布

| ID | 任务 | 状态 |
| --- | --- | --- |
| P01 | M5 收尾：图标/安装体验、更新通道（非 Windows 壳后续再议） | 🔄 K1（图标已落地 `resources/icons/**`、`packaging/build.py:101-113`；安装器与更新通道未实现） |
| P02 | R10 新手引导（首开 KB / 空文件树 / 无 KP 引导流；示例库一键打开） | ⏳ |
| P03 | R13 UI 语言切换 | 🔄 K1（前端已完成 `js/i18n.js:14-15` + 设置→显示即时切换；壳端未做，原生对话框标题硬编码中文 `app/pywebview_host.py:152/171/194`；不自动翻译 md 正文） |
| P04 | Windows 右键文件夹「以 Memoria 打开」+ 打开前安全检查（2026-08-29 登记，详情见下） | ⏳ |
| P05 | `static_server` 的 `_kb_root` 是模块全局 → 一进程只能服务一个知识库（多库/多实例与外部宿主嵌入受阻） | ⏳ K1（`static_server.py`；与 D2 集成 X10 相关；来源 agent-guide/10） |
| P06 | 打包态在**他人机器**启动崩溃（pythonnet 初始化失败，2026-09-18 用户报于 v0.3.4-lite 分发） | 🔄 K2（**根因 = Mark-of-the-Web**；修复 = 随包 `Memoria.exe.config` + 失败可读弹窗 + 交付面补系统要求；v0.3.4 已重建并替换资产。证据 `artifacts/p06-motw-e2e.txt`。待在报错机器复验。详情见下） |
| P07 | UI 视觉收敛（滚动条 / 标签栏滚轮 / 圆角五档 / 描边 0.5px + **分隔线档** **`--border-sep`** / 阴影三档 / **横条统一 33px（`--bar-h`）** / 侧栏页签条去 13.2px 白留 / 发送按钮右对齐） | 🔄 K2（`app.css` 末尾块 + 原位改值；harness 8651–8659 实测数字见 agent-guide/01 §6–§7 与 design/ui-visual-language.md §4。**未取证**：0.5px 在 1x 仍上取整为 1px、真实 hover/滚轮、真机观感） |
| <br /> | <br /> | <br /> |

**P04 / P06 详情已出表（2026-10-22 P4）**：右键集成与打开前安全检查的 6 项校验、P06 的 MotW 根因/修复/证据/遗留，均已**逐字**迁入 [design/packaging-release.md](design/packaging-release.md)；本表只留状态与一行摘要。
***
