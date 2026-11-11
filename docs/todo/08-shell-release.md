# 8. 壳与发布 — 活跃详情（原文逐字）

> **本文件是 `docs/todo.md §8` 的活跃详情**（2026-10-26 索引化搬迁，**原文逐字**，未改写）。
> **状态事实源 = `docs/todo.md` 索引行**；本文件只放详情。历史归档仍在 `docs/design/**`，不在此重复。

## 台账日期标签（2026-11-11 增补；非原文）

> 依据 [ledger-maintenance.md 规则 9](../conventions/ledger-maintenance.md)（日期标签必填）。本块是元数据，不改下方原文逐字表。

| ID | 📅 首次登记 | 🕒 最近复核 | 备注 |
|---|---|---|---|
| P08 | 2026-11-11 | 2026-11-11 | 架构已定（人 2026-11-11 裁决）；状态 ⏳ K1 待实现·待 Worker 端点；未实现 |

<a id="p01"></a><a id="p02"></a><a id="p03"></a><a id="p04"></a><a id="p05"></a><a id="p06"></a><a id="p07"></a><a id="p08"></a>

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

## P08 · 发布版启动后台写回使用频次（当日/总量）到项目 HTML 展示页，并屏蔽本地开发/测试实例

> 📅 首次登记: 2026-11-11
> 🕒 最近复核: 2026-11-11（人裁决架构；**待实现 / 待 Worker 端点**）

**需求（人 2026-11-11，Lead 转述要点）**：新版本 release 应用一打开就触发后台任务；修改（增加 1）项目 HTML 富展示页的一项内容——使用频次（当日、总量）；**本地应用的使用频次必须屏蔽**，以便知道真实用户量。

**状态**：`⏳ K1 待实现·待 Worker 端点（架构已定；阻塞点 = serverless 计数后端尚未提供）`。**未实现；未写任何 token；未改 `site/**`。**

### 已定架构（2026-11-11 人裁决，据 Lead 转述）

1. **计数后端**：按 Lead 推荐，用**无客户端 token 的 serverless 计数**（Cloudflare Worker + D1/KV，或等价轻量 API）。**安全前提（保留）**：客户端不持有可写 token；任何"把可写 GitHub PAT 嵌入客户端"的方案都需重开安全评审。
2. **页面读 JSON**：新增/读取 `site/stats.json`，**不由客户端直接改 `index.html`**；写入方 = serverless 后端（或发布流程生成 JSON）。
3. **本地屏蔽**：本地 `Memoria-release-test` / dev 态**内部强制禁用**；设置里再提供面向用户的开关。
4. **后台任务约束**：不阻塞启动、失败静默但可诊断、不重试风暴、离线不报错。
5. **披露**：页面/设置说明**匿名计数**。

### 待确认方案（Lead 建议；**尚未实现，不得写成已实现**）

- **去重**：首次启动生成随机 `install_id`（UUID，存 `%LOCALAPPDATA%\Memoria` 本地，**不做设备指纹**）；服务端按 `install_id` 去重；`今日活跃 = 当日 distinct install_id`、`累计用户 = 全部 distinct install_id`。另可单独记 `今日启动次数 / 累计启动次数`，避免把"频次"与"用户数"混为一谈。
- **启动时机**：主窗口显示且首屏初始化完成后，延迟约 **3–5 秒**在后台线程发一次；**每进程一次**，不 await、不阻塞、不重试风暴。
- **页面展示建议**：`今日活跃设备 / 累计设备`；如需要再加 `今日启动 / 累计启动`。
- **本地屏蔽判据**：dev 非 `sys.frozen`、`Memoria-release-test` 路径/构建标记、`MEMORIA_DISABLE_USAGE_STATS=1`；设置项**默认开、可关**。

### 实现前仍需定 / 必须满足（未决）

1. **Worker 端点契约与 URL 配置**：在"客户端不可写 token"前提下如何接收计数（建议端点只接受受控发布流程/签名，不直接暴露匿名可写，否则仍可被刷）；端点未提供前只能等待。
2. **`site/stats.json` schema 与写入策略**：字段（today_active/total_active/today_launch/total_launch）、时区（Asia/Shanghai）、并发写冲突（若经 GitHub Contents API 写 JSON 需处理 409/sha；若后端存储则发布时生成 JSON）。
3. **`install_id` 存储/清理/隐私文案**：写入位置、卸载是否删除、设置说明如何写。
4. **设置项 UI**：默认开/可关；与"release-test/dev 内部强制禁用"的优先级。
5. **测试方案**：`Memoria-release-test` 构建必须验证"零上报"（断网/屏蔽标记下无请求、不报错）。

### 现状证据锚（只读）

- `site/index.html`：静态落地页（中/英/部署说明三段），**当前无使用频次展示位**（文件内无统计数字区块）。
- `site/README.md:4`：`site/` 是发布物，会被 GitHub Actions 原样上传；`:21` 发布 `path: site`；`:22` 改内容需同步 `index.html` 与 `GUIDE.md`。
- `.github/workflows/pages.yml:36-38`：`upload-pages-artifact` 的 `path: site` ⇒ **只有 `site/**` 上站**，计数展示改动落点在此。
- 关联：I-15（版本更新机制，已落地 `be4e9dec`）；I-32（`Package-test/` 与 `Package/` 同级；与 `Memoria-release-test` 的命名/关系待统一）。

---
