# 10 · 磁盘布局与宿主嵌入

> **用途**：说清 ①一个知识库目录里**究竟有什么文件、谁写的、能不能删、是不是事实源**；②要把 Memoria 前端**嵌进别的宿主**（Electron / 其它 webview / iframe）时，前后端各自提供了什么、缺什么、必须自建什么。
> **目标读者**：外部集成方（把 Memoria 嵌进插件 / 桌面壳 / 智能体的人）、维护 `.memoria/**` 数据契约的人、排查"文件被谁改了"的人。
> **关联文档**：[README.md](./README.md)（本套用法与维护约定）、[../hard-constraints.md](../hard-constraints.md)（红线）、[../architecture.md](../architecture.md)（分层——注意其 `/rpc` 描述已过时，见 §5）、[../../design/kb-agent.md](../../design/kb-agent.md)（知识库侧智能体契约）、[../../design/deepseek-harness-integration.md](../../design/deepseek-harness-integration.md)（对外能力面分析）、[01-shell-and-layout.md](./01-shell-and-layout.md)（窗口 chrome 与顶栏拖拽区）。
> **状态**：生效中，2026-09-19。

---

**证据锚约定**：`文件:行号` 以仓库根为基准。前端 `src/memoria/ui/static/app/**`（下称 `index.html` / `js/*.js`）；后端 `src/memoria/**`（写 `presentation/`、`storage/`、`services/`、`app/shell/`）。

## 1. 区域概览

### 1.1 一个知识库目录的完整结构

```
<知识库>/                                   ← 用户选定的目录（= KB 根）
├── *.md 与 <子目录>/*.md                   知识正文（事实源 ①；扫描入口 storage/scanner.collect_md_files）
└── .memoria/                              隐藏目录：被扫描器整体跳过（storage/constants.py:11-17）
    ├── manifest.yaml                      磁盘快照（产品「构建」/保存后维护）manifest.py:31-32、136-144
    ├── manifest.yaml.bak                  上次写入的备份（storage/atomic_yaml.py:15-43）
    ├── sidecars/                          KP 元数据（事实源 ②）sidecar.py:75-82
    │   └── <与 md 同构的镜像路径>.memoria.yaml
    ├── pending.json                       待确认提议队列（事实源 ③-候选）storage/pending.py:33-35
    ├── pending.yaml                       旧格式（只读兼容：读到即迁移为 JSON 并删除）pending.py:54-77
    ├── kp_targets.json                    派生索引（打开库可秒读）services/kp_index.py:162-183
    ├── images/                            图片资产（正文以相对 KB 根路径引用）document.py:828-833
    │   └── registry.json                  运行期图片注册表（打开图片管理器时全量重建）document.py:976-1040
    ├── cache/                             可再生缓存，**可整目录删**（hard-constraints.md:50）
    │   ├── lexical/index.json + jieba/    lexical 倒排 + 分词缓存：lexical_index.py:58、lexical_tokenizer.py:17
    │   ├── embeddings/index.json          向量索引：embedding_provider.py:42
    │   ├── search_aux/                    检索辅助：search_aux.py:26
    │   └── models/manifest.json           本地模型清单：model_router.py:59
    ├── build/                             「构建」产物（图/链接/自查报告）graph/kb_build.py:218-231
    └── agent/                             Trae 智能体工具包（services/kb_agent.py:40-42）
        ├── README.md · prompt.zh-CN.md · kb-spec.zh-CN.md · preview-formats.md · fsrs.py
        ├── .kit.json                     版本清单（无时间戳 → 保证幂等）kb_agent.py:74-81
        ├── review/                       cards.json / progress.json —— **产品永不覆盖**（kb_agent.py:8、114）
        └── sessions/                     **应用内对话的会话事实源**（JSONL，append-only）
            └── <session-id>.jsonl        session/store.py:56-66、169-237（M1b 起由 `ask()` 写；M1c 起可被面板历史下拉**只读**列出/载入；**M1 收尾起可被 `agent_session_delete` 删除**；**M2 起事件面新增 `compaction`（长会话压缩）、`compaction/prune`（工具结果裁剪）与 `session/title`（会话标题）记录**——产品**唯一**允许写知识库的位置，见 §2.15）
```

**不在知识库里的那一份**：UI 偏好（含语言、字号、缩放、图谱参数、窗口最近列表）写在**程序目录** `config/ui-settings.json`（`storage/ui_settings.py:11-28`），可用环境变量 `MEMORIA_CONFIG_DIR` 改址；旧位置 `~/.memoria/ui-settings.json` 会自动迁移一次（ui_settings.py:14-15、31-43）。**应用内对话的端点配置**另存程序目录 `config/agent.json`（`services/agent/llm/config.py:164-174`；同受 `MEMORIA_CONFIG_DIR` 控制）。→ **知识库可携带（知识+会话），UI/端点偏好不可携带**。

### 1.2 数据分类（谁写 / 能否删 / 是否事实源）

| 类别 | 成员 | 谁写 | 能否删 | 事实源？ |
|---|---|---|---|---|
| 知识正文 | `*.md` | 产品服务层（`save_document`）或外部 agent（须走服务层，见 §2.10） | **不能**（删=丢知识） | ✅ ① |
| KP 元数据 | `.memoria/sidecars/**` | 产品服务层（`save_sidecar`） | **不能**（KP 权威在此，kb-agent.md:94） | ✅ ② |
| 磁盘快照 | `.memoria/manifest.yaml` | 产品（`save_manifest` / `ensure_manifest_baseline`） | 可删：下次打开即重建基线（manifest.py:147-152） | ⚠️ 不是知识事实源，是**一致性基准** |
| 待确认提议 | `.memoria/pending.json` | 产品（导入/建议流程，`save_pending`） | 可删：丢未确认队列，不影响已落盘知识 | ⚠️ 提议队列 |
| 学习状态 | `.memoria/agent/review/**` | 外部智能体 / `fsrs.py` | 可删：丢复习进度 | ✅ ③（kb-agent.md:70 口径） |
| 派生索引 | `.memoria/kp_targets.json`、`.memoria/cache/**`、`.memoria/build/**` | 产品（可重建） | 可删，下次读写自动重建 | ❌ |
| 图片资产 | `.memoria/images/**`（含 registry.json） | 产品（插入/清理 RPC） | 图片文件删=正文引用悬空（检查会报）；registry 可删（重建） | 图片本体≈事实源 |
| 工具包 | `.memoria/agent/{README,prompt,kb-spec,preview-formats,fsrs.py,.kit.json}` | 产品（`install_kb_agent`，升级时覆盖） | 可删：删目录即完全回滚（kb-agent.md:252） | ❌ 分发物 |
| 对话会话 | `.memoria/agent/sessions/*.jsonl` | 产品服务层（应用内对话 `ask()` → `SessionStore`，session/store.py:169-237；**M1 收尾起亦可由 `agent_session_delete` 删除**） | 可删：丢对话记录（过程数据，非知识） | ⚠️ 会话事实源（对话自身的权威记录；**不是**知识事实源）。M1c 起由 `agent_sessions_list` / `agent_session_load` **只读**列出与载入（ui.py:1258-1328），并作为续聊的上下文来源（history.py:307-322，**M2 起先应用 `compaction` 压缩、再兜底截断**）；**M1 收尾起 `agent_session_delete` 可删单份会话**（ui.py:1329-1367，会话目录是产品自己管理的运行时产物 ⇒ 这是**产品首次允许写知识库**，范围仅限该目录） |
| UI 偏好 | `config/ui-settings.json`（`layout` 段 + **M1 收尾新增的顶层 `agent` 段**；2026-09-18 起 `agent.lastSessionByKb` 为**按库**记的「上次会话」映射，见 §2.15） | 前端 → `save_ui_settings` | 可删（回默认值） | ❌ |
| 端点配置 | `config/agent.json` | 前端（对话面板）→ `agent_save_config` → `llm/config.py::save_config` | 可删（回默认端点，需重新配置） | ❌（含密钥，**仅本地文件**） |

## 2. 逐处细节

### 2.1 `*.md`（知识正文）

- **扫描口径**：`SKIP_DIR_NAMES = {".memoria", ".git", ".build", "__pycache__", "node_modules"}`（constants.py:11-17）；`.memoria/` 不进文件树、不参与构建与校验（kb-agent.md:39）。
- **写入链路（唯一合法路径）**：RPC `save_document`（ui.py:200）→ `DocumentService.save_document`（document.py:317-384）：读原文件保留 frontmatter（335-338）→ **tmp + `os.replace` 原子写**（341-347，`MEMORIA_FSYNC` 等策略见 `durable_flush`）→ 清内存缓存（351）→ 更新 manifest（353-359，M6a 走延迟 pending）→ 增量维护图片注册表（365）→ 重新锚定 KP range（376）。
- 重命名/移动/删除走各自 RPC（`rename_*` / `delete_*` / 路径级联修复），不是直接改文件名。
- ⚠️ **文档与代码相反的一处**：[../hard-constraints.md](../hard-constraints.md):31 写"`save_document` 成功后清理全库未引用图片（物理删除）"，代码注释与实现**明确不做**：清理只在用户显式调用 `cleanup_unused_images`（document.py:320-322；ui.py:867；前端 image-tools.js:443、474）。

### 2.2 `.memoria/manifest.yaml`（快照，不是知识源）

- 结构：`{schema_version, updated_at, files: [{path, md_mtime, md_size, md_sha256, sidecar_mtime, sidecar_sha256}, …]}`（manifest.py:35-62、136-144、111-133）。
- 写入用 `save_sidecar()` → `atomic_write_yaml()`（manifest.py:144；atomic_yaml.py:46-56）：**先备份 `.bak`** → `.tmp` → `fsync` → `replace`。
- 读侧会叠加内存里的延迟 touch（M6a，manifest.py:75-108、126-128），故磁盘内容可能比内存视图"旧一点"，这是有意设计。
- 缺失时 `ensure_manifest_baseline` 用当前磁盘重建（manifest.py:147-152），打开库时会调（document.py:269）。

### 2.3 `.memoria/sidecars/**`（KP 权威）

- 路径：`<kb>/.memoria/sidecars/<与 md 同构相对路径>.memoria.yaml`（sidecar.py:66-82）；读取时**回退**旧路径（与 md 同目录的 `<stem>.memoria.yaml`，sidecar.py:85-98）——**写用 canonical、读要容忍旧路径**。
- KP 解析只读 sidecar，md 的 frontmatter 不参与（kb-agent.md:94）→ 改 KP 必须写 sidecar。
- 写入 `save_sidecar` → `atomic_write_yaml`（sidecar.py:116-117），同样留有 `.bak`。

### 2.4 `.memoria/pending.json`（待确认提议）

- 结构 `{schema_version?, items: []}`；`load_pending` 强制保证 `items` 是数组（pending.py:85-87）。
- 写入 `save_pending` → `_atomic_write_json`（备份 + tmp + fsync + replace，pending.py:42-51、91-93）。
- 旧 `pending.yaml` 一旦读到即迁移并删除，同时清理 `.bak`（pending.py:54-77）。
- 语义：导入/建议流程**不静默修改**正文，未定稿内容进这里（[../import-spec.md](../import-spec.md):47）。

### 2.5 `.memoria/kp_targets.json`（派生索引）

- 结构 `{schema_version, built_at, ids[], stems{}, pairs[[file, kp_id]]}`（kp_index.py:166-183）。写：后台重建 + 原子替换；**写后失效**（`invalidate_kp_targets` 只 bump 版本、标 `ready=False`，保留旧快照供读兜底，kp_index.py:139-159）。
- 打开库时先尝试秒读持久化快照，失败才同步重建（document.py:262-263）。

### 2.6 `.memoria/images/**`

- 目录：`<kb>/.memoria/images/`（document.py:828-833）；入库规则：复制本地图片，**内容去重（MD5）+ 重名追加序号 + 永不覆盖**（hard-constraints.md:30）。
- 正文引用写**相对 KB 根的路径**（如 `.memoria/images/x.png`），渲染前由 `rewriteLocalImagePaths` 改写为 `/files/...`（hard-constraints.md:32）。
- `registry.json` 是运行期注册表：打开图片管理器触发全量扫描重建（document.py:899、976-1040）；`save_document` 只做**增量**维护（document.py:365）。删未引用图片只在显式 RPC（ui.py:867）。

### 2.7 `.memoria/cache/**` 与 `.memoria/build/**`

- `cache/`：全部**可再生**（hard-constraints.md:50），四类子目录见 §1.1；任何"删掉就重算"的假设都成立。
- `build/`：产品「构建」按钮写入（kb_build.py:218-231，`_write_json` 直接写文件、非原子）；删除只丢上一份构建报告，不影响知识。

### 2.8 `.memoria/agent/**`（工具包）与 `review/**` 不被覆盖

- `install_kb_agent(kb_path)`（kb_agent.py:84-145）：写入 `FILE_MAP` 的 5 个文件 + `.kit.json`；**内容一致则跳过**（`skipped`，121-123）；`.kit.json` 不含时间戳以保证重复安装幂等（74-81）；所有写入走 `_atomic_write`（临时文件 + fsync + replace，56-71）。
- `review/`：只 `mkdir`，**从不写入**（kb_agent.py:114）；权威表述见 kb-agent.md:70、223（"升级时按版本覆盖其余文件，`review/` 一律保留"）。
- 分工：`README/prompt/kb-spec/preview-formats/fsrs.py` 仅产品写；`review/cards.json` 由智能体写；`review/progress.json` 由 `fsrs.py` 写（kb-agent.md:56-66）。

### 2.9 `config/ui-settings.json`（程序目录，非知识库）

- 定位顺序：`MEMORIA_CONFIG_DIR` → `install_root()/config/`（ui_settings.py:18-25）；`settings_path()` 为唯一入口（27-28）。
- 写入：**浅合并**（嵌套 dict 也按一层合并）+ `tmp` + `os.replace`（ui_settings.py:58-75）。
- 读接口 `get_ui_settings()` 返回 `{status, settings, config_dir, settings_file, settings_rel}`（ui.py:647-658）→ 设置弹窗底部那行"设置保存在程序目录：{path}"就是这么来的（graph-settings.js:859-882）。
- **已知顶层键**：`layout`（`sidebarWidth` / `agentDockWidth` / `agentDockCollapsed` 等）、`last_kb_path` / `recent_kbs`、主题与显示设置、`check`/`graph`/`search` 设置段，以及 **M1 收尾新增的 `agent` 段**（对话面板偏好，见 §2.15）。**2026-09-18 起** `agent` 段的「上次会话」由全局单键 `lastSessionId` 改为**按库映射** `lastSessionByKb`（`{ "<库标识>": "<会话 id>" }`，库标识由 `kbKey()` 归一化；旧键读取时一次性迁移并删除）。**浅合并的坑**：直接传 `{layout:{agentDockWidth}}` 会整段替换 `layout`（抹掉 `sidebarWidth`）；`{agent:{…}}` 同理会替换 `agent` 段。前端因此统一走「先 `get_ui_settings` 读旧段 → 合并 → `save_ui_settings`」。⚠️ 嵌套浅合并**无法删除键**，而面板需要移除旧键/陈旧库条目 ⇒ `agent` 段改走**两步写**「先置 `agent:null`（非 dict ⇒ 后端整体替换）再写目标对象」（`writeAgentPrefs()`，agent-panel.js:359-364）。`layout` 走 `saveDockLayout()`（agent-panel.js:302-313），两者都绝不触碰对方的顶层段。

### 2.10 写入纪律（红线）

1. **三个事实源**：`*.md`（正文）＋ `.memoria/sidecars/**`（KP 元数据）＋ `agent/review/**`（学习状态），职责分离，学习状态**不得**写进 sidecar（kb-agent.md:70）。
2. **禁止 silent 写入**：未定稿内容进 `pending.json` 走确认流程（import-spec.md:47）；外部 agent **不得**直写 `*.md` / `sidecars/**` / `manifest.yaml` / `pending.json`（deepseek-harness-integration.md:166）。
3. **原子写 + 写后索引失效**：md 走 tmp+replace（document.py:341-347）；yaml/json 走 `atomic_write_yaml` / `_atomic_write_json`（带 `.bak`）；KP 写入后索引失效（kp_index.py:153-159）。
4. **外部 agent 的会话/日志属"过程数据（可删）"，不是知识事实源**（deepseek-harness-integration.md:87、114、268）。
5. ⚠️ **口径不一致（须知情）**：`AGENTS.md §1` 按"产品状态＝各知识库 `.memoria/**`"归类；kb-agent.md:70 说三源是 md+sidecars+review；deepseek-harness-integration.md:87 说"知识库事实源 = sidecars + manifest + pending"。**代码事实**：sidecar＝KP 权威、manifest＝磁盘快照、pending＝提议队列、review＝学习状态，四者性质不同，任何单一列表都会以偏概全。

### 2.11 前端桥 `js/bridge.js`

| 项 | 证据 | 说明 |
|---|---|---|
| 就绪事件名 | bridge.js:7 | `READY = "memoriaready"`（自定义事件，派发在 `window`） |
| 宿主 A：pywebview | bridge.js:96-104 | 监听 `pywebviewready`，或脚本加载时 `window.pywebview.api` 已存在 → `installApi()` |
| 宿主 B：PyQt6 QWebChannel | bridge.js:69-94、106-111 | 当 `qt.webChannelTransport` 存在或 UA 含 `QtWebEngine` 时启动：`new QWebChannel(transport, cb)`，取 `channel.objects.bridge`；每 **25ms** 重试、最多 **400** 次（约 10s）；后端注册点 pyqt6.py:268-273（对象名 `bridge`） |
| 对外接口 | bridge.js:113-119 | `MemoriaBridge = { api(), onReady(fn), installApi(api), installQtApi(bridge), makeQtApi(bridge) }` |
| 统一契约点 / `onReady` 时序 | bridge.js:22-27、56-67 | `installApi()` 把宿主对象挂到 **`window.memoria.api`** 并派发 `memoriaready`；`onReady(fn)` 在 `api()` 已就绪时**立即同步执行**，否则 `addEventListener(READY, fn, {once:true})` |
| Qt 侧方法代理 | bridge.js:9-20、29-49 | `makeQtApi` 返回 `Proxy`：任意属性名 → `bridge.invoke(name, JSON.stringify(args))`；返回值若为字符串则 `JSON.parse`；`then` 属性刻意返回 `undefined` 防被当 thenable |

### 2.12 没有桥时会发生什么

| 层面 | 表现 | 证据 |
|---|---|---|
| `MemoriaBridge` 对象 | **仍存在**（脚本无条件定义），但 `api()` 返回 `undefined` | bridge.js:113-119、56-58 |
| 启动链 | `MemoriaBridge.onReady` 永不触发 → `bindEvents()` 与各子系统 `init()` **全部不执行** | app.js:12676-12687（boot 是唯一入口；各模块自身不做 DOMContentLoaded 初始化） |
| 界面 | 静态 HTML 可见：`#welcome` 欢迎页显示（`#editor-wrap` 默认 `hidden`）、顶栏按钮只有外观、文件树/KP 列表为空、状态栏停在 `app.status.ready`「就绪」 | index.html:144-148、149；app.js:212-215 |
| 交互 | 点「设置」无反应（`#btn-settings` 未绑）、F2 无效（`_lastSel` 恒空）、搜索框可输入但一切后端调用最终报 `app.apiUnavailable`「API 不可用: {fn}」 | graph-settings.js:950；file-tree.js:445-465；app.js:385-387；i18n/zh-CN.js:484 |
| 窗口三键 | `#window-controls` 保持 `hidden`（HTML 默认即 hidden；`initWindowChrome` 无 `get_window_chrome` 时直接返回） | index.html:101-105；window-chrome.js:301-308 |
| 例外 | 不依赖桥的纯前端行为照旧可用：字号/缩放快捷键（本地存储）、取色面板、格式栏选区涂抹等 | app.js:12203-12216 等 |

> 结论：**没有桥 = 只能看到一个"壳"**。集成方的第一优先级是提供 `window.memoria.api`（或 QWebChannel `bridge.invoke`），否则整站不启动。

### 2.13 后端：静态服务、端口与"RPC"真相

| 项 | 证据 | 说明 |
|---|---|---|
| 路由 | static_server.py:114、130 | **只有两条**：`GET /`（手动读 `app/index.html`，注入资源版本 `?v=<启动时间戳>`，static_server.py:96-128）与 `GET /<path:path>`（`files/` 前缀 → KB 文件；`_kb_root_diag` → 诊断；其余 `bottle.static_file`，130-154） |
| 响应头 / 安全头 | static_server.py:94、126-128、151-153 | UI 页面与静态资源都带 `Cache-Control: no-store, no-cache, must-revalidate` + `Pragma: no-cache`；**`/files/` 的响应不带 no-store**（91 只设 Content-Type/Length）。全仓**无** `X-Frame-Options` / `Content-Security-Policy`（grep 零命中，index.html 也无 CSP meta）→ **iframe 不会被响应头拦截**（但也无 origin 校验，见 §5.3） |
| `/files/` 防穿越 | static_server.py:56-91 | 段级 unquote → `normpath` → 大小写归一 → KB 根前缀 + **目录边界**双重校验；不合格 404（hard-constraints.md:33） |
| **`/rpc`** | **不存在** | 全仓路由只有上面两条（`@app.get` 仅 static_server.py:114、130）。⚠️ [../architecture.md](../architecture.md):21-23、44 与 deepseek-harness-integration.md:96、150 都写"static_server 的 `/rpc` 暴露 UIAPI 93 方法"——**该路由在当前代码中不存在** |
| 真实调用路径 A | pywebview.py:471-484 | `webview.create_window(url=create_app(), js_api=api, …)`：WSGI app 交给 pywebview 托管，方法经 **`window.pywebview.api`** 暴露（非 HTTP） |
| 真实调用路径 B | pyqt6.py:224-273、api_rpc.py:14-67 | `StaticServerThread` 起本地 HTTP 只提供**静态资源**；方法经 **QWebChannel 单槽** `UIAPIRpc.invoke(method: str, args_json: str) -> str`（JSON 入、JSON 出、`default=str` 兜底） |
| 端口/绑定 | static_server_thread.py:11-35 | pyqt6：`_free_port()` 先 `bind(("127.0.0.1", 0))` 取随机端口，再 `make_server("127.0.0.1", port)`，daemon 线程 `memoria-static` |
| 单进程单库 | static_server.py:31、46-53；ui.py:34-35、126-127 | `_kb_root` 是**模块级全局**，由 `UIAPI` 在开库/关库时 `set_kb_root(...)` → 一个后端进程同时只能服务**一个**知识库 |

### 2.14 无窗口模式现状（对外部宿主是硬约束）

**结论：当前不存在任何 headless 入口。** 静态服务只在 GUI 启动流程里随壳一起起来：

- 唯一启动链：`app/shell/__init__.py:12-24` → `pywebview.run()`（pywebview.py:455-509，静态服务= `create_app()` 交给 webview）或 `pyqt6.run()`（pyqt6.py:224-225，`StaticServerThread().start()`）。
- 命令行只有一个面向**知识库运维**的 CLI：`memoria validate|repair-paths|diagnose-images`（cli/main.py:111-125），**不含**起服务、也不加载前端。
- 因此"不启 GUI 就能浏览器访问 Memoria UI"目前**做不到**（deepseek-harness-integration.md:151 亦承认 T3 需新代码）。

### 2.15 应用内对话：9 个 RPC、会话事实源、多轮续聊、长会话压缩、工具结果裁剪、会话标题、会话检索与「停止/删除」（2026-09-17 落地，2026-09-18 增补 M1c、M1 收尾与用量统计，2026-09-19 增补 M2 压缩、裁剪、会话标题与会话检索工具）

M1「对话」面板（**2026-09-17 第二轮起挂在右侧 `#-agent-dock`**，前端见 [01 篇 §2.4](./01-shell-and-layout.md)）共 9 个 RPC：
**4 个为 2026-09-17 新增**（`presentation/api/ui.py:1177-1225`：`agent_get_config` 1177-1183、`agent_save_config` 1184-1193、`agent_ask_start` 1194-1213、`agent_ask_poll` 1214-1225），**2 个为 2026-09-18（M1c）新增的只读会话历史**（ui.py:1258-1328：`agent_sessions_list` 1258-1300、`agent_session_load` 1301-1328），
**2 个为 2026-09-18（M1 收尾）新增**（`agent_ask_cancel` ui.py:1226-1252、`agent_session_delete` ui.py:1329-1367），
**1 个为 2026-09-18（用量可视化）新增的只读用量统计**（`agent_usage_stats` ui.py:1368-1400，见 §2.17）；
除下表中 `agent_ask_start` 的**追加可选参数**（`session_id`）、`agent_ask_poll` 的**追加字段**（`cancelled`）、
`agent_sessions_list` 的**追加字段**（`capped`）、`loop/end.usage` 的**追加字段**（三个 cache 字段，见 §2.17）外，
**未改任何既有方法的语义与签名**；`save_ui_settings` 新增顶层 `agent` 段（非本表 RPC）。
**M2（2026-09-19）起**：会话事件面新增三条记录 —— 第 8 类 `compaction`（长会话压缩）、第 9 类 `compaction/prune`（工具结果裁剪）与第 10 类 `session/title`（**会话标题，log-only**），都是**纯追加**、**不新增 RPC、不 bump `SESSION_FORMAT_VERSION`**，分别见下方「长会话压缩」「工具结果裁剪」「会话标题」；同轮新增**第 6 个只读知识库工具** `search_sessions`（**也不新增 RPC** —— 它只在模型回合内部可用，前端不调用），见下方「会话检索工具」。

| 方法 | 签名 | 返回 |
|---|---|---|
| `agent_get_config` | `()` | `{status:"ok", enabled, base_url, model, timeout_s, has_key, key_masked, source, config_file, config_rel, config_keys}` |
| `agent_save_config` | `(patch: dict)` | 同 `agent_get_config`（写后回读）；`patch` 白名单键 `base_url`/`api_key`/`model`/`timeout_s`/`enabled`，非法键返回 `{status:"error", code:"config_error", message}` |
| `agent_ask_start` | `(question: str, kb_path: str \| None = None, session_id: str \| None = None)` | `{status:"ok", job_id, job_status:"running"}` 或 `{status:"error", code, message}`（`no_kb`/`empty_question`/`net_disabled`/`no_base_url`/`busy`）。**`session_id` 为 M1c 追加的可选参数**：省略/为空 ⇒ 全新会话（与原语义完全一致）；非空 ⇒ **续聊**（见下方「多轮续聊」）。**单飞 `busy` 可被 `agent_ask_cancel` 立即解除** |
| `agent_ask_poll` | `(job_id: str, cursor: int = 0, reasoning_cursor: int = 0)` | `{status:"running"\|"done"\|"error", job_id, delta, cursor, reasoning_delta, reasoning_cursor, answer, anchors, tool_calls, usage, session_id, stop_reason, iterations, error, code, cancelled, elapsed_ms}`；未知作业返回 `code:"unknown_job"`。**`cancelled` 为 M1 收尾追加字段**（只增）：被停止的作业为 `status:"done"` + `stop_reason:"aborted"` + `cancelled:true` + `answer`=已生成片段。**`reasoning_cursor` / `reasoning_delta` 为 AG08 追加**（只增不改）：模型的思考增量与正文**各自独立游标**（文本侧 `delta`/`cursor` 语义一行未改）；思考**只在流式期间可见、不落会话文件** ⇒ 重载页面/载入旧会话都不显示过往思考（有意偏差，上游 dsh 会持久化；见 [01 篇 §2.4](./01-shell-and-layout.md)） |
| `agent_ask_cancel` | `(job_id: str)` | **M1 收尾新增**。真取消：置取消令牌 ⇒ 后端停止消费模型流（关闭底层 HTTP 响应）、**立即**释放单飞 busy。`{status:"ok", job_id, cancelled, job_status}`；未知作业 ⇒ `{status:"error", code:"unknown_job", message, job_id, cancelled:false}`；**已结束的作业 ⇒ `{status:"ok", cancelled:false}`**（幂等，不抛异常） |
| `agent_sessions_list` | `(kb_path: str \| None = None)` | `{status:"ok", sessions:[{session_id, modified_at(epoch 毫秒), turn_count, preview(前 80 字), title, capped}], count}`；按文件修改时间倒序、**最多 30 条**（`SESSION_LIST_LIMIT`，ui.py:1251）；`capped` 为 **M1 收尾追加字段**（见下「去读放大」）。**`title` 的语义在 M2 变了**（值更短更贴题）：优先是**折叠出的会话标题**（`session/title` 事件 —— 模型标题或确定性兜底），没有标题事件时才回落到「首条提问前 40 字」（M1 行为）；口径见下「会话标题」。单份会话损坏只跳过该条。**只读、不写盘** |
| `agent_session_load` | `(session_id: str, kb_path: str \| None = None)` | `{status:"ok", session_id, messages:[{role:"user"\|"assistant", text, anchors?}]}`；未知/非法会话 ⇒ `{status:"error", code:"unknown_session", message}`。**只读、不写盘** |
| `agent_session_delete` | `(session_id: str, kb_path: str \| None = None)` | **M1 收尾新增，产品首次允许写知识库**。只删 `<kb>/.memoria/agent/sessions/<id>.jsonl`；id 由 `session_file()` 的正则校验（防目录穿越）+ 一道**目录归属校验**（`realpath(父目录) == realpath(sessions_dir)`）双保险。`{status:"ok", deleted:true, session_id}`；id 非法/会话不存在 ⇒ `code:"unknown_session"`；删除失败（占用/权限）⇒ `code:"session_failed"` |
| `agent_usage_stats` | `(kb_path: str \| None = None, session_id: str \| None = None)` | **2026-09-18（用量可视化）新增，只读**。聚合会话 `loop/end.usage`：`{status:"ok", kb_path, sessions:[按会话汇总], turns:[逐轮行], summary:{sessions, turns, prompt, completion, total, cache_hit, cache_miss, hit_rate, estimated_turns, cache_unknown_turns}}`；`session_id` 省略 ⇒ 全库。**命中率在 cache 数据未知时为 `None`**（不写 0）。未知/非法会话 ⇒ `code:"unknown_session"`；读取失败 ⇒ `code:"usage_failed"`。口径见 §2.17 |

- **密钥边界（硬约束）**：`agent_get_config` / `agent_save_config` **只回掩码**（`mask_secret`，llm/config.py:94-101），明文密钥不进入任何返回值、日志、异常或 DOM；面板输入框保存后即清空，已存密钥只作 placeholder。
- **配置落点**：`config/agent.json`（程序目录，与 `ui-settings.json` 同级；`config_file_path()` llm/config.py:164-174）。读路径为「环境变量 → 该文件 → 默认值」（`load_config()` llm/config.py:202-241，环境变量名见该模块头表）；写路径为**浅合并 + tmp/`os.replace` 原子写**（`save_config()` llm/config.py:284-330），`api_key` 仅在传入非空新值时覆盖——避免面板的掩码占位把已存密钥清空。键 `enabled`（允许出网）缺省视为 **true**（`is_enabled()` llm/config.py:265-281；`timeout_s` 空值同表"不修改"语义）。**改这个文件的 UI 入口**：**2026-09-19 起**为设置弹窗（工具栏「设置」）的 **「对话」页签**（`#settings-body-agent`；原为 dock 头部的「设置」按钮 + 「网络」checkbox，两者已移除；字段 id 未变）——
- **偏好落点（M1 收尾；2026-09-18 改为按库记）**：`config/ui-settings.json` 的**顶层 `agent` 段**里的 `lastSessionByKb`——`{ "<库标识>": "<会话 id>" }` 的映射，**每个知识库各自记一份**自己的「上次会话」（提问成功 / 手动载入 / 自动恢复时写入；**清空对话时只删本库条目**，不动别的库）。库标识由 `kbKey()`（agent-panel.js:324-327）把知识库路径归一化后得到：`/`→`\`、去尾分隔符、Windows 上再 `toLowerCase()`（NTFS 大小写不敏感），读/写/迁移/清理**全部**经它，避免同一库分裂成多条。读写统一走 `readAgentPrefs()`（:330-338）、`setLastSessionId()`（:370-383）、`clearLastSessionId()`（:386-401）、`writeAgentPrefs()`（:359-364，两步写见 §2.9），**绝不覆盖 `layout` 段**。**旧版全局单键 `agent.lastSessionId` 兼容策略＝一次性迁移**：`restoreLastSession()`（:928-945）在映射里没有本库条目但存在旧键时，把旧键当候选，**只有它在当前库下确实能载入时才认领**（写入映射并删除旧键），载入失败则不迁移、不删除（留给它原本所属的库认领）；此后不再读写旧键。
- **不存在跨库会话（显式声明）**：会话目录**按库分**（`<kb>/.memoria/agent/sessions/`），系统提示注入的也是**当前库**规范（`services/agent/prompt.py`：`build_system_prompt()` 按固定段落顺序「基础身份 → 运行环境 → 知识库指令文件 → 可用工具 → **用户引用（`@路径`）** → 回答要求」拼装，空段消失；其中「用户引用」段**只在本次请求的工具集含 `read_document` 时**才追加——语义移植自上游 `context/file-reference` 并按「`read` 工具是否在场」同构门控，prompt.py:194-218（段落）、262-263（门控））。因此**一个会话只属于建立它的那个知识库**：切换知识库时必须作废当前会话态并由新库自己的 `lastSessionByKb` 条目恢复；**任何"把 A 库的会话 id 交给 B 库"的行为都是缺陷**（前端以 `sessionKb` 作兜底断言，绝不把别的库的 id 发给后端；后端也按传入 `kb_path` 解析会话文件）。将来若要做**全局助手**，应**另立一个不依赖知识库的会话位置**，而不是复用库内 `sessions/`。
- **会话事实源**：`<kb>/.memoria/agent/sessions/<session-id>.jsonl`（`services/agent/session/store.py:56-66`）。首行 header、其后每行一个事件（`seq` 连续、append-only、撕裂尾部对读者不可见）；由 `ask()` 写（ask.py:311-335）。事件类型既有 7 类（`user/message` / `assistant/message` / `tool/call` / `tool/result` / `step/start` / `step/error` / `loop/end`，写入点 loop.py:302-398 与 ask.py:335），**M2（2026-09-19）起新增第 8 类 `compaction`、第 9 类 `compaction/prune` 与第 10 类 `session/title`**（形状与回放口径见下「长会话压缩」「工具结果裁剪」「会话标题」）。`session_id` 随 `agent_ask_poll` 的最终结果返回，面板状态行显示。
- **多轮续聊（M1c）**：`session_id` 指向的会话文件**已存在**时，`ask()` 先按 `session/history.py::build_history()`（history.py:340-359）把它回放成消息序列，作为 `messages=` 传给 `loop.run(question, messages=history)`（ask.py:318、353）——**回放发生在追加本轮 `user/message` 之前**，故历史里不含本轮问题、不会被重复加入；`session_id` 省略或文件不存在 ⇒ 全新会话，行为与 M1b 一致；`ask(replay=False)` 可显式关闭回放（测试/脚本用，ask.py:284）。事件 → 消息的映射：`user/message`→user、`assistant/message`→assistant（含 `tool_calls`）、`tool/result`→tool（`tool_call_id` 对齐），`tool/call`/`step/*`/`loop/end` 跳过；`compaction` 按下方「长会话压缩」的口径回放（摘要替换被覆盖区间）；`compaction/prune` 按「工具结果裁剪」的口径回放（工具结果正文就地换成「头 + 标记 + 尾」）。
- **回放保真度（全保真，仅异常轮降级）**：`ToolCall` 可用 `{id,name,arguments}` 完整重建，且 OpenAI 兼容适配器正是按 `tool_call_id`/`tool_calls` 序列化（`llm/providers/openai_compatible.py:374-391`），故**带工具的轮次原样回放**（assistant 带 tool_calls + 紧随其后的 tool 消息）。唯一降级分支：某条 assistant 的 `tool_calls` 与随后的 `tool/result` **无法一一配对**（`id` 为空/数量不等/顺序不符，正常写作只在进程崩在工具执行中途出现）⇒ **整轮丢弃**，保证输出里绝不出现孤立 `tool_calls` 或孤儿 `tool` 消息（违规会被端点 400）。**容量上限与截断策略**：最多 **40 条消息**（`MAX_HISTORY_MESSAGES`，history.py:104）/ **32000 字符**（`MAX_HISTORY_CHARS`，history.py:106），**从最新往旧保留**整条消息，至少保留最新 1 条（单条超预算也保留，否则续聊会凭空丢掉当前上下文）；截断后若首部是被截掉 assistant 的 `tool` 消息，则一并丢弃以保持序列合法（`_truncate()`，history.py:295-309）。**M2 起截断退居兜底**：`build_history()` 先应用 `compaction` 压缩与 `compaction/prune` 裁剪、再做上述截断（history.py:340-359）。
- **长会话压缩（M2，2026-09-19；`compaction` 事件）**：新模块 `services/agent/compaction.py`（**纯标准库**，语义移植自上游 `packages/compaction/compaction` + `compaction-basic`，pin `0d1f5000`）。阈值/保留是**字符预算**（本地无「上下文窗口」概念，故用比例乘字符预算；上游是比例乘 context window）：触发阈值 `compact_threshold_chars()` = `MAX_HISTORY_CHARS(32000) × COMPACT_THRESHOLD_RATIO(0.8)` = **25600 字符**，尾部**逐字保留** `retain_chars()` = `× RETAIN_RATIO(0.16)` = **5120 字符**（compaction.py:105-107、188-197）。其余常量：`MIN_SPAN_CHARS = 2000`（**本地新增**下限）、`SUMMARY_MAX_TOKENS = 8192`、`SUMMARY_RETRY_POLICY`（`max_retries=1`、`total_timeout_s=60`）、`SUMMARY_OPEN_TAG`/`SUMMARY_CLOSE_TAG`、`CHECKPOINT_PREAMBLE`、`COMPACTION_INSTRUCTION`（8 段结构化 Markdown 骨架的中文落法，compaction.py:105-172）。
  - **区域选择（`select_span()`，compaction.py:272-312）**：被压缩区间恒为**前缀**（最旧那一段）；切割点必须**工具配对平衡**（`balanced_cuts()`，compaction.py:253-269 = 上游 `toolPairingBalancedBefore` 的「未闭合工具调用数」折叠，不得落在 assistant 的 `tool_calls` 与其 `tool/result` 之间）；满足「尾部 ≥ 5120 字符」时**尽量多压**（取最靠后的合法切割点）；另有两条本地下限：覆盖量 ≥ 2000 字符、区间内至少含一条 `user/message`。`select_span()` 另有可选 `effective_chars`（见下「工具结果裁剪」）。
  - **摘要调用（`summarize_span()`，compaction.py:315-381）**：**同一份 `system` + 同一份 `tools` + 被覆盖区间的消息**，把 `COMPACTION_INSTRUCTION` 作为**最后一条 `user` 消息**追加（上游理由：让这次辅助调用成为上一次已路由请求的真实前缀，从而复用 provider 的 KV 缓存，`summarizer.ts:24-30`）；摘要固定 **8 段结构化 Markdown**、空段写 `(none)`、遇到旧 `<compacted-summary>` 要**合并**而非照抄。
  - **fail-closed**：无终止事件 / `error` / `aborted` / `max-tokens` / 返回了工具调用 / 正文为空 ⇒ 抛 `CompactionError`（compaction.py:175-176），**不产出半份摘要**。
  - **落盘形状**（由 `ask._compact_if_needed()` 落盘，ask.py:248-258）：`{"summary": "<摘要正文>", "shadowed": [seq…], "shadowed_chars": <int>, "model": "<摘要模型名>", "usage": {…}?}`；`usage` 与 `loop/end.usage` **同形状**（来自新公开的 `loop.usage_payload()`，loop.py:133-143），省略表示端点未上报。
  - **回放口径（`history._compaction_plan()` / `_replay()`，history.py:190-215 / 223-287）**：被 `shadowed` 覆盖的 seq **全部跳过**；摘要在**该区间最旧那条 seq 的位置**出一条 `user` 消息（= 时序仍在原处，**不是**追加在末尾），正文由 `frame_summary()`（compaction.py:201-203）包上 preamble 与 `<compacted-summary>` 标签；**链式压缩**（后一次覆盖前一次区间、含前一条 `compaction` 记录自身）只出**最新**那份合并摘要；**无效记录**（`shadowed` 为空 / 摘要为空）忽略，不吞掉任何事件。`build_history()` = **先应用压缩与裁剪、再兜底截断**（history.py:340-359）。
  - **调用时机与容错（`ask()`，ask.py:321-334）**：在**追加本轮 `user/message` 之前**做裁剪+压缩（故被处理的历史不含本轮问题）；只有「回放后的历史字符量 > 阈值」才尝试（`_history_chars()` / `_compact_if_needed()`，ask.py:167-266）；**裁剪与压缩失败都不打断提问**——`summarize_span()` 自身 fail-closed，`ask()` 只记 warning、按**未压缩**历史继续；落过事件则**重新回放**，让本轮请求用上裁剪与摘要视图。压缩与主回合**共用同一份 `system` + 工具集**（`build_loop()` 新增可选 `registry` / `system` 关键字参数，ask.py:128-129、147）以对齐 KV 前缀。
  - **纯追加、不 bump `SESSION_FORMAT_VERSION`**：`compaction` 是新增记录类型，三个既有读者对未知 type 一律**跳过**而非报错（`history._replay()` 落到未知 type 就 `index += 1`；`conversation_messages()` 只认 `user`/`assistant`；`usage_report` 只认 `loop/end`）⇒ 旧版本读新文件只是**降级为「没有压缩」**（把被覆盖区间逐字重发），既不误读也不崩——等价上游 `ignorable: true`；按上游「只有结构变更才 bump」的规则不 bump（`SESSION_FORMAT_VERSION = 1`，store.py:49-50）。
  - **摘要调用的 token 用量不进 benchmark、也不进面板状态栏用量格**：它记在 `compaction.usage` 里，但 `scripts/benchmark/usage/report_usage.py` 与面板口径都只认 `loop/end` ⇒ 压缩的开销对二者**不可见**（已在 [../../design/dsh-agent-port.md §6.8](../../design/dsh-agent-port.md) 的「已知缺口」登记；将来给报告加 `kind=compaction` 一类行即可）。
- **工具结果裁剪（M2，2026-09-19；`compaction/prune` 事件）**：新模块 `services/agent/pruner.py`（**纯标准库**，语义移植自上游 `packages/compaction/compaction-tool-result-pruner`，pin `0d1f5000`；§6.8 曾登记为「留后」，本轮补上）。**免模型**：把超预算的旧工具输出换成「**头 4096 码点 + 标记 + 尾 1024 码点**」的定长形态（阈值 **8192 码点**，三个数与 `PRUNE_MARKER` 字面量均与上游默认值/同名字面量一致，pruner.py:69-77）。
  - **只在压力已确认时才裁**（触发条件同压缩：回放后的历史 > 25600 字符），且**裁完若已低于阈值就免掉这次摘要调用**（上游原话：*trimming may relieve enough token pressure to skip summarization*）—— 故它是压缩的**省钱前置**，本身**零模型调用**（`ask._compact_if_needed()`，ask.py:177-266）。
  - **不回环**：`PruneBudgets` 在**构造期**校验「头 + 标记 + 尾 ≤ 阈值」（pruner.py:98-120）⇒ 产出恒**不超过阈值**且**严格短于**原文 ⇒ 重复运行不会再改；幂等判据是「该 `seq` 已出现在某条 `compaction/prune` 里」（`prune_records()`）。已被 `compaction` 覆盖的 `seq` 直接跳过（那些本就不进请求）。
  - **回放安全**：**原 `tool/result` 事件逐字留在日志里**（append-only），只有**发给模型**的请求用裁剪视图 —— 检索（`search_sessions`）、`agent_session_load`、用量报告、审计看到的仍是原文。
  - **落盘与回放**：一条 `compaction/prune` 记 `{pruned:[{seq, id, chars_before, chars_after, head, tail}], chars_removed}`；`history.build_history()` 按记录里**落盘的预算**就地重建（`pruner.apply_budget()`，history.py:155-169）⇒ 回放结果**不随默认常量变化漂移**；**形状不全的记录整条忽略**（fail-safe：宁可让模型看原文，也不拿半截预算切正文）；同一 `seq` 被多条记录覆盖时**后写覆盖**（与压缩同口径）。
  - **与区域选择的账**：`compaction.event_chars()` / `select_span()` 新增可选 `effective_chars`（`seq → 有效字符数`），**被裁过的工具结果按裁剪后的长度计账**（compaction.py:219-251、272-312）—— 否则会按原文高估尾部大小、把本可逐字保留的轮次也压掉；该参数是普通 dict，故 `compaction` 与 `pruner` **零耦合**。
  - **与上游的差异**：上游裁剪是一次**表面替换**（追加新 `tool/result` + `surfaceOp: replace` + 紧随其前的影子定价事件）；本地**不能为同一个 `tool_call_id` 追加第二条 `tool/result`**（回放会把同一调用配成两条工具消息、端点 400）⇒ 改为「记录 + 回放期就地重建」。不移植影子定价（`shadowedTokenCount`，本地无 token 计量服务；改用字符量，与 `compaction.shadowed_chars` 同口径）、不移植「替换写入失败 ⇒ 整轮失败」（本地 fail-open，与压缩同口径）。上游工具结果是 `ContentBlock[]`（富块零成本直通），本地是**纯字符串**；预算是**码点**不是 token（上游同款已知限制）。
- **会话标题（M2，2026-09-19；`session/title` 事件）**：新模块 `services/agent/title.py`（**纯标准库**，语义移植自上游 `packages/session/session-title` + `session-title-llm` + `session-title-first-prompt-llm`，pin `0d1f5000`；**不吃** `-all-prompts`（每轮重算不值）、投影框架、`session/title-llm-request` 预派发记录、`rename()` —— 见 [../../design/dsh-agent-port.md §6.11](../../design/dsh-agent-port.md)）。**log-only**：标题**绝不进模型输入**（回放跳过它、`event_chars` 计 0、`search_sessions` 的语义抽取也不含它），只服务于**会话列表**。
  - **来源与「最新者胜」**：`fallback`（确定性兜底，**零模型调用、零网络**）→ `provider`（模型标题，**覆盖**兜底）。事件形状 `{"title", "message_seqs":[seq…], "source":{"kind",…}}`；`provider` 来源另带 `usage`（**本地扩展**，形状同 `loop/end.usage`，但**不进** benchmark / 面板状态栏 —— 那两处只扫 `loop/end`）。
  - **兜底节律**（`title.ensure_fallback()`；调用点 ask.py:276-286）：**追加本轮提问之后**若会话还没有标题，就按**首条合格人类消息**（规范化后非空）派生一条 —— 首 **8 个词**（whitespace 分词）且 ≤ **96 UTF-8 字节**（`fallback_title()`，title.py:214-223）。老会话再聊一句也会补上它。
  - **模型节律**（`first-prompt`，`title.auto_title()`，title.py:434-472）：**恰好一条**合格人类消息时（= 每个会话的**首轮**）跑一次辅助调用并落一条 `provider` 标题；次轮起一次都不发。调用形状：**自带的 system 提示**（`title_system_prompt()`：只输出一行纯文本标题、不要引号/Markdown/代码 + 目标长度）+ **一条 `user` 消息**（把选材消息**框成 JSON** `[{seq,text}]`，正文无法破坏结构分隔；`frame_messages()`），`max_tokens = 96`、输入 ≤ **32768 字节**、超时 **20s** + 一次重试。
  - **落点与容错**（ask.py:276-322）：两步都在 `ask()` 内 —— ① 追加提问后落兜底；② **主回合之后**跑首轮一次的模型标题（本地**没有异步标题服务**，故面板 `done` 会晚一个**极小**辅助调用的时间，**仅每会话首轮一次**）；**被取消的那一轮不生成**；两步都 **fail-open**（失败只记 warning）。
  - **规范化**（`clean_title_text()` / `truncate_title_utf8()` / `normalize_title()`，title.py:178-212）：去 OSC / CSI / 其余两字节 ESC 序列、非空白 C0/C1 控制字符、**方向与隐形控制字符**；空白折叠成单空格；按 **UTF-8 字节**截断（**不切开码点**）；任何来源上限 **120 字节**。**空标题记录视作没有**（继续用前一条有效标题）。
  - **列表口径**：`summarize_events()` 用 `title.fold_title()` 取**最后一条非空** `session/title`；`summarize_session_file()` 的**原始行扫描**另找 `"session/title"` 行、只对**最后一个命中行**解码（history.py:409-412、464-469），与折叠**同口径**；两处都没有标题事件时才回落到「首条提问前 40 字」。**前端**：左栏「历史」列表的行标题 = `title || preview`（agent-panel.js:1946-1949，`histTitle`）—— 后端从 M1c 起就返回 `title`，但前端此前一直只用 `preview`，M2 才接上。
- **会话检索工具（M2，2026-09-19；`search_sessions`）**：第 6 个只读知识库工具（`services/agent/tools/kb.py:566-592`；`KB_TOOL_NAMES` kb.py:73-80），后端是新模块 `services/agent/session/query.py`（**纯标准库**，语义移植自上游 `packages/session-query/session-query` 的 `extraction.ts` + `filters.ts` 与 `session-query/tool-session-query`，pin `0d1f5000`；**不吃** `session-query-sqlite`（本地不引索引）与 `session-log-export`（导出 UI）—— 见 [../../design/dsh-agent-port.md §6.9](../../design/dsh-agent-port.md)）。用途是回答「我们之前聊过什么 / 上次说到哪」这类问题：它检索的是**过去与本知识库的对话记录**，与知识库文档检索（`search_kb`）**是两件事**。
  - **可检索文本（`event_text()`，query.py:125-146）**：只有"第一方语义事件"贡献文本 —— `user/message`→`text`、`assistant/message`→`content` + 各 `tool_calls` 的 `name`/`arguments`、`tool/result`→`content`；`tool/call`/`step/*`/`loop/end`（`_STRUCTURAL`，query.py:108）与**未知 type 一律空**（上游口径：未知事件不因载荷里恰好有字符串就变成可检索）。**本地扩展一行**：`compaction`→`summary` —— 被压缩掉的旧对话只剩这份摘要，不检索它等于把那段对话从检索面抹掉；故上面「长会话压缩」那条**不减少**可检索内容。
  - **匹配口径（`compile_text_pattern()`，query.py:149-159）**：**字面量** —— 按空白切词、逐词 `re.escape`（查询永远只是数据、不是可执行的正则语法）、词间以 `\s+` 连接（**空白弹性**）、大小写不敏感 + Unicode 感知；空查询抛 `SessionQueryError`。
  - **命中形状（与文档锚点刻意区分）**：工具结果把命中写成「**会话 `<id>` 第 N 条**」，**明确不产生 `文件:行号` 锚点**（那是知识库文档引用的形状，混用会让模型把对话记录当成库内出处）；无命中时提示「这里检索的是历史对话，找资料请用 `search_kb`」。
  - **有界（query.py:93-105、230-236）**：单份文件 2 MiB（同 `SESSION_SCAN_MAX_BYTES` 同值同意图）、跨会话扫描 ≤ 500 份（默认 50，按 `modified_at` 倒序取最新）、单页命中 ≤ 200；工具面 `limit` 1–20、默认 5；`limit=0` **合法**（返回空），负数/非整数 fail loud。**性能**：先在**不解码的字节串**上做 ASCII 小写化后的逐词存在性预筛（`bytes.lower()` 只影响 ASCII，故"判否"安全），全词命中才解析该文件；`title`/`turn_count` 复用 `summarize_session_file()` 的原始行扫描（与 `agent_sessions_list` 同一口径，不整体 `json.loads`）。
  - **偏差（引用时须一并给出）**：语料是**磁盘上的会话文件**（无 live 会话注册表、无 SQLite FTS 索引）；组间排序按 `modified_at` 倒序（**最近聊过的先出**）而非上游的**相关性**排序（本地无评分器）；`snippet` 取首个匹配点前后各 80 字符 + 省略号（**窗口算法未逐字对齐**上游）；不移植游标 `SessionSearchCursor` / `lineage` / `trace` / 宿主可观测性；工具面**不返回** `capped` 事实。
- **会话历史视图**：`agent_sessions_list` 逐份算摘要；`agent_session_load` 用 `conversation_messages()`（history.py:447-479）产出**渲染视图**——只出 `user`/`assistant`、**不含** `tool` 消息，每轮只出**一条** assistant 气泡（= 该轮最后一条非空 `assistant/message`，与实时渲染一致）。**锚点归属口径**：该轮全部 `tool/result.anchors` 去重后挂在该轮那条 assistant 气泡上（跨轮不混淆；轮内取并集）。
- **去读放大（M1 收尾，`agent_sessions_list`）**：摘要改走 `history.py::summarize_session_file()`（history.py:396-444）的**原始行扫描**——全程在**字节串**上找 `"user/message"` 子串计 `turn_count`（不解码整份文件、不整体 `json.loads`），只对**首个命中行**解码 + `json.loads` 一次取预览；单份文件读取上限 `SESSION_SCAN_MAX_BYTES` = **2 MiB**（`capped:true` 表示超限、统计被截断，且**丢弃末段半行**不计），`size` 复用 `list_sessions()` 已 stat 到的字节数以免重复 stat。**`turn_count` 语义因此是「扫描上限内的 `user/message` 事件行数」**。实测（30 份会话 / 3.4 MiB / 每份 114.5 KiB）：**12.4–13.9 ms → 4.8–5.6 ms（约 2.2–2.7×）**；单份 3.0 MiB 病态会话：**10.4 ms → 1.4–1.7 ms（≈6.4–7.5×，`capped=true`）**。口径更严的 `summarize_session()` 仍保留给需要精确计数的调用方。
- **伪流式、真增量与并发**：`agent_ask_start` 把一次同步 `ask()` 提交到**独立单线程执行器**（`services/agent/ask_stream.py::AskJobManager`，建池与 `thread_name_prefix="agent-ask"`），**不占用** `MaintenanceExecutor` 的 2 个 worker；增量来自 `ask(on_text=...)`（ask.py:283、350 → loop.py:253-254，消费 provider 的 `TextDelta`），`agent_ask_poll` 按 `cursor` 返回新增文本（`snapshot()`）。**同一时刻只允许一个 ask 在飞**，重复提交返回 `busy`（但被停止/已取消者不再占位）。续聊的 `session_id` 经 `AskJob.resume_session_id` 透传到 `ask(session_id=...)`。**面板作业固定用收紧的重试策略**（`retry_policy=PANEL_RETRY_POLICY`，见 §2.16）。**M1 收尾起是"真增量"**：`llm/providers/openai_compatible.py:296-311` 用 `response.read1(_READ_SIZE)` 读响应体（`HTTPResponse.read(n)` 在「无 Content-Length / `Connection: close`」的 SSE 上会阻塞到 EOF 或读满 n 字节，实测 3.6s 的流只在结束时返回一整块 ⇒ 增量投递与取消都失效）；`read1` 至多触发一次底层读，SSE 帧一到即返回（实测逐帧 90B/0.3s）。**AG11（2026-09-19）起前端逐行渲染**：后端 `delta`/`cursor` **契约一行未改**（本节与上表口径继续有效）；面板侧新增纯函数分割器 `js/agent-stream-buffer.js`（`window.MemoriaStreamBuffer.split`），把累计文本切成 `safe` 可渲染前缀（走既有 markdown 路径 ⇒ 表格给完一行即渲染一行）与未成型尾部（代码块 / `$$` 公式 / frontmatter 未闭合时进等待区 + 转圈，闭合后再渲染）——细节见 [01 篇 §2.4「伪流式与等待计时」](./01-shell-and-layout.md) 与 01 篇 §7 本轮 AG11 段。
- **「停止」= 真取消（M1 收尾，替换旧「忽略本次」）**：`loop.py::CancelToken`（`threading.Event`）经 `ask(cancel=...)` 透传进 `AgentLoop`，在**三个检查点**观察——每轮迭代前（loop.py:295-299）、**流式逐事件**（loop.py:248-250）、每次工具调用后（loop.py:380-383）。取消时 `_stream_once` **停止消费生成器并 `stream.close()`**（令 provider 的 `with closing(response)` 关闭底层 HTTP 响应、不再收完），`stop_reason = StopReason.ABORTED`、**保留已生成的部分文本为 `answer`**，正常发 `loop/end`（`stop_reason="aborted"`）落盘、**不抛异常**；`AskJob.cancel()` 同时把作业**立即**收敛为 `done/aborted` 并释放单飞 busy（`ask_stream.py`），工作线程随后的 `succeed()/fail()` 不再改写状态（只补会话 id）。**边界（如实声明）**：取消是**协作式**的——阻塞在一次 `read1()` 上时须等该分片到达才返回；被取消那一轮**不写 `assistant/message`**（会话文件里只有 `user/message` + `loop/end(aborted)`），故刷新/恢复后该轮只剩用户气泡。
- **「清空对话」（生成中亦可用）**：本地面板清空 + **删掉当前库在 `agent.lastSessionByKb` 里的条目**（只删本库，不动别的库），且**顺带调 `agent_ask_cancel`**（避免丢弃结果却继续烧 token）。**2026-09-19**：独立按钮 `#agent-clear` 已退役（入口改为左栏「历史」页签的「＋ 新会话」），上述语义一行未变。
- **恢复上次会话（M1 收尾；2026-09-18 起按库）**：面板打开（`init` / dock 展开）或**切换知识库**（`app.js` 在 `initKb:454`/`openKbAt:564`/`closeKb:602` 调 `panel.onKbChanged()`）时，从 **`agent.lastSessionByKb[<当前库>]`** 取该库自己的上次会话 id，若其会话文件仍存在 ⇒ 自动 `agent_session_load` 并设为当前会话（下一句即续聊）；**不存在则静默忽略**（不报错、不提示），并**清掉该陈旧条目**（避免每次打开都重试）。⚠️ **不得**用别的库的 id：不存在跨库会话（见上一条）。
- **写入范围与「会话目录可写」边界（M1 收尾更新）**：此前本面板除会话 JSONL 外**不写知识库任何内容**（工具面自带零写入守卫）。M1 收尾**首次**开放一个写入口——`agent_session_delete` **只删** `<kb>/.memoria/agent/sessions/<id>.jsonl`：该目录是**产品自己管理的运行时产物**（会话事实源，不是知识内容），删除是**产品对自己产物的管理动作**，与"零写入正文/sidecar/manifest/pending"的边界不冲突；正文、sidecar、manifest、图片等**仍一律不碰**。删除后的可见影响：该对话无法再续聊（历史下拉里消失），知识本身不受影响。
- **宿主嵌入注意**：这 9 个方法与其它 RPC 一样经 `window.memoria.api` / QWebChannel 单槽调用（§2.13），**没有** HTTP `/rpc`（`/rpc` 仅存在于测试 harness）；宿主若只实现最小桥，对话面板会在 `agent_get_config` 缺失时抛 `app.apiUnavailable` 并就地显示错误（不静默）。

### 2.16 重试与失败分类（2026-09-18，M1 收尾）

**目标**：确定性连接失败（重试必然同样失败）**立即失败**；瞬时故障仍按上游退避重试；交互面板的等待有界；最终错误串如实带重试次数。

| 失败类别 | 例子 | 稳定 code | 可重试 |
|---|---|---|---|
| **确定性连接失败** | 连接被拒（WinError 10061）、DNS 解析失败、TLS 证书校验失败、无效 URL | `UNREACHABLE`（**新增**） | ❌ |
| 瞬时故障 | 超时、连接重置 / 中断 / broken pipe、5xx、429 | `TIMEOUT` / `TRANSPORT` / `SERVER` / `RATE_LIMIT` | ✅（现行为不变） |
| 其它永久失败 | 401/403、配额、上下文超限、400/413/422、协议错 | `AUTH` / `QUOTA` / `CONTEXT_WINDOW_EXCEEDED` / `INVALID_REQUEST` / `PROTOCOL` | ❌（现行为不变） |

- **分类落点**：新增稳定 code `UNREACHABLE`（`llm/errors.py:62`），**刻意不进** `RETRYABLE_CODES`（errors.py:70——本轮**未增未删**，仍为 `EMPTY_RESPONSE`/`RATE_LIMIT`/`SERVER`/`TIMEOUT`/`TRANSPORT`），而是列入 `_TERMINAL_CODES`（errors.py:87）。判定函数 `is_unreachable()`（errors.py:205）先剥开 `urllib.error.URLError.reason` 再按底层异常分类；`is_retryable()` 的裸 `OSError` 分支改为「非确定性才可重试」（errors.py:247）。端点带内报错文本里的确定性措辞（`connection refused` / `getaddrinfo` / `certificate verify failed` / `unknown url type` 等）也在 `classify_detail()` 里归 `UNREACHABLE`（errors.py:96、345-347），而 `connection reset/aborted/broken pipe` 仍归 `TRANSPORT`。
- **适配器落点**：`_transport_error()`（`llm/providers/openai_compatible.py:485-497`）在**建立连接**（:281）与**读取响应**（:303）两条路径统一分类；非数字端口等 `http.client.InvalidURL` 单独捕获（:272-277）。消息含**目标 URL + 底层原因 + 「确定性失败，不会重试」**，形如：`连接模型端点 http://127.0.0.1:9/v1/chat/completions 失败：目标端口拒绝连接（<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>）；确定性失败，不会重试`。
- **面板路径的等待上限**：库层默认值保持上游口径（`max_retries=5` / `initial_delay_s=0.5` / `max_delay_s=10` / `total_timeout_s=120`，`llm/retry.py:52-56`，**本轮未改**）；`ask_stream.py` 为**交互路径**显式构造更紧的 `PANEL_RETRY_POLICY`（`max_retries=2`、`total_timeout_s=20`，ask_stream.py:82-84）并传给 `ask()`（ask_stream.py:257）。理由：面板是「人在等」的交互路径，等待必须有界——2 次重试足以覆盖偶发抖动（退避上限 0.5+1.0≈1.5s），20s 是"还能等"与"像卡死"的分界（前端另有 5 分钟轮询兜底）；库层作为通用调用面保留上游默认。
- **重试次数可见**：`AgentLoop` 把 `iter_with_retry` 的 `on_retry` 接进计数器（loop.py:238-246），最终 `error` 串在发生重试时追加「（已重试 N 次）」（`_retry_note()`，loop.py:146-150；**N=0 不加**），并在 `step/error` 观测事件里附 `retries`（loop.py:307-310）；`AgentLlmError` 的公开字段未变。
- **A/B 实测（必拒连端点）**：`base_url=http://127.0.0.1:9/v1` 走 `agent_ask_start` + 轮询——修复前 **27578ms**（= 6 次尝试 × 2.06s 单次拒绝耗时 + 5 次退避 15.5s，与人工实测 27986ms 同量级）⇒ 修复后 **2281ms**（1 次尝试、重试日志 0 行）；RPC 侧 `code:"ask_failed"`（`ask_failed` 是作业兜底 code），`error` 为上面那条含 URL 的原文。
- **前端呈现**：面板的 code 映射（`agent-panel.js:132-157`）**未新增、未改动**；LLM 失败一律经 `ask_failed` 兜底显示本地化文案 + **后端原文**（原文即含 URL 与"确定性失败，不会重试"，agent-panel.js:1235-1239）。

### 2.17 Agent 用量：端点字段映射、`loop/end.usage`、RPC 与报告脚本（2026-09-18，为 token benchmark 打前置）

**目标**：把"这次调用花了多少 token、其中多少命中缓存"这类**事实数据**完整落盘并可聚合，
为后续 token benchmark / A-B 对照提供前置。**不引入任何价格表**（成本换算由使用方按当时的公开价自行乘）。

**1) `Usage` 的缓存字段**（`services/agent/llm/types.py:109-152`）

| 字段 | 含义 | 来源 |
|---|---|---|
| `cache_read_tokens` | 命中的缓存（输入）token | 端点上报（见下映射） |
| `cache_write_tokens` | 写入缓存的 token | 端点上报（**当前两个内置映射都不产出**，保持 `None`） |
| **`cache_miss_tokens`** | **本轮新增**：未命中的缓存（输入）token | 端点上报，或 OpenAI 形态下由 `prompt_tokens - cached` 补出 |

- `plus()` 已同步合并三者（`_sum_optional`：任一侧为 `None` 取另一侧，两侧皆 `None` 得 `None`）；
  `UsageMeter.add()/to_dict()/reset()`（`llm/usage.py:105-159`）同步累计与输出 `cache_miss_tokens`。
- **只增字段**：既有字段名与语义未改；老读者忽略未知键即可（`loop/end.usage` 载荷同样只增键）。

**2) 端点 `usage` → 缓存字段的映射**（`llm/providers/openai_compatible.py:428-464` 的 `_usage_from_wire`）

| 端点形态 | 读什么 | 映射 |
|---|---|---|
| **DeepSeek**（优先） | 顶层 `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens` | → `cache_read_tokens` / `cache_miss_tokens` |
| **OpenAI 风格**（兜底） | `prompt_tokens_details.cached_tokens` | → `cache_read_tokens`；未命中量按 `prompt_tokens - cached` **可推才推** |
| 两者皆缺 | — | 三个 cache 字段保持 `None` = **未知** |

**`estimated` 语义未变**：只有端点**完全没给** `usage` 时才由 `estimate_usage()` 置 `estimated=True`
（`openai_compatible.py:384-385`）；**给了 usage 但缺 cache 字段不算估算**（`estimated=False`，cache 为 `None`）。
用户端点是 `api.deepseek.com`，此前只读 OpenAI 风格字段 ⇒ `cache_read_tokens` 恒为 `None`、命中率无从计算，本条即修此缺陷。

**3) `loop/end.usage` 载荷**（`loop.py::usage_payload()`，loop.py:133-143；`loop/end` 事件（loop.py:390-398）、`AskResult.usage` 与**压缩事件 `compaction.usage`** **共用同一形状**）

`{prompt_tokens, completion_tokens, total_tokens, estimated, cache_read_tokens, cache_write_tokens, cache_miss_tokens}`
（前 4 键既有，后 3 键本轮起随 `loop/end` 与 `agent_ask_poll.usage` 一并返回；`AskResult` 的公开字段未改）。

**4) RPC `agent_usage_stats`**（ui.py:1368-1400）—— **只读**，见 §2.15 表；
实现是 `services/agent/usage_report.py::usage_stats()`，与 CLI 报告脚本同一份口径。

**5) 报告脚本** `scripts/benchmark/usage/report_usage.py`（目录与命名对齐 `scripts/benchmark/graph/`，README 中文单语）

```powershell
python scripts\benchmark\usage\report_usage.py --kb <知识库> [--label <标签>] [--session <会话 id>] [--out <目录>]
```

- 产物 **JSON + MD 双份**（`results/usage-<label>_<sha>.json|.md`）：JSON 供后续 A/B，MD 供人读
  （总览 / 按会话 / 按轮次 / **口径与限制**，含来源 commit 与生成时间）；
- **只读知识库**：只读 `<kb>/.memoria/agent/sessions/*.jsonl`，除 `--out` 外不写任何位置；
  `--out` 落在知识库内会被**直接拒绝**；
- 读取走**原始行扫描 + 字节上限**（复用/参照 `session/history.py::summarize_session_file()` 的做法）：
  全程在字节串上找 `"loop/end"` 子串、只对命中行解码，单份文件最多读 `SCAN_MAX_BYTES = 2 MiB`
  （超限会话标 `capped:true`，只统计上限内的轮次并丢弃末段半行）⇒ 大文件不会把内存打爆。

**6) 口径与已知限制**（引用数字时必须一起给出）

- **一轮** = 一条 `loop/end` 事件（一次提问里全部模型步数之和），**不是**"一次模型请求"；
- **命中率未知 ≠ 0**：本轮改动之前落盘的**老会话**没有 cache 字段 ⇒ 其轮次计入
  `cache_unknown_turns` 且**不参与**命中率分母，命中率返回 `None`（报告显示「未知」）。
  逐轮行的 `hit_rate = cache_hit / prompt`（`prompt <= 0` 或 `cache_hit is None` ⇒ `None`）；
  汇总的 `hit_rate` 只在 cache 已知的轮次上算（同上）。
  显式上报 `cache_read_tokens = 0` 是**已知**（命中率 0%），与"未知"不同（有单测覆盖）；
- **会话文件未记录模型名**，故逐轮行不含 `model`；
- `cache_miss_tokens` 在 OpenAI 形态下是**推出来的**（端点只给命中量），DeepSeek 形态下是端点直报。
- **压缩（M2）的摘要调用用量不在本报告、也不在面板状态栏用量格的统计面内**：它记在 `compaction.usage`
  里（与 `loop/end.usage` 同形状，来自同一 `usage_payload()`），但本报告与面板口径都**只认 `loop/end`**
  ⇒ 压缩的开销对二者**不可见**（已在 [../../design/dsh-agent-port.md §6.8](../../design/dsh-agent-port.md)
  的「已知缺口」登记；将来给报告加 `kind=compaction` 一类行即可，见 §2.15「长会话压缩」）。

**7) 前端状态栏用量格** `#status-agent`：显示最近一轮紧凑摘要与悬停拆分（布局/交互见 [01 篇 §2.7](./01-shell-and-layout.md)）；
本会话累计由面板**自行累加**（不新增 RPC 轮询），载入历史会话时因会话视图不含 usage 而从 0 起算。

## 3. 交互流程

**3.1 首帧 → boot**：请求 `/` → 返回注入了 `?v=` 的 index.html（no-store）→ 按 index.html:432-484 的顺序加载脚本（graph-* → *-settings → `vendor/qwebchannel.js` → `bridge.js` → `window-chrome.js` → 编辑管线 → i18n 包 → `i18n.js` → `scheduler.js` → `app.js` → 各子系统，末位是 `agent-panel.js`:484）→ bridge.js 立即安装（pywebview 已有 api）或轮询等待（Qt）→ `installApi()` → 派发 `memoriaready` → app.js 的 `onReady` 回调执行 `bindEvents()` → 导入流/搜索/图片/检查/智能体/文件树/**对话面板** `init()`（app.js:12850-12856）→ `initKb()`（读启动库路径）→ `initWindowChrome()`。

**3.2 一次 RPC 往返**：前端 `call("name", ...)`（app.js:385-387）→ `window.memoria.api.name(...args)`：
- pywebview：直接调用宿主对象方法（pywebview 内部完成序列化）；
- PyQt6：`bridge.invoke("name", JSON.stringify(args))` → 后端 `UIAPIRpc.invoke` 解析 args、`getattr(UIAPI, method)(*args)`、`json.dumps(result, ensure_ascii=False, default=str)`（api_rpc.py:44-67）→ 前端 `parseRpcResult` 反序列化（bridge.js:9-20）。
- 返回约定：业务失败统一 `{status: "error", message}`（各 API 方法一致，如 ui.py:659-660、766-771）；前端 `call()` 在方法不存在时抛 `app.apiUnavailable`。

**3.3 嵌入时序要点**：宿主应先起后端与静态服务，**再去加载页面**；桥必须在 `bridge.js` 执行前或 `memoriaready` 派发前就绪，否则只能靠两条兜底（pywebview 的 `pywebviewready`；Qt 的 25ms×400 轮询）。开库后才会 `set_kb_root`，故 `/files/...` 在开库前一律 404（static_server.py:56-61）。

## 4. i18n key 前缀

本篇涉及面很窄，但集成方会碰到：

| 前缀 / 键 | 出现位置 | 说明 |
|---|---|---|
| `settings.configPath` | graph-settings.js:874-876；zh-CN.js:644 | 设置弹窗底部：`设置保存在程序目录：{path}`（`{path}` 来自 `get_ui_settings().settings_rel`） |
| `modal.settings` / `common.close` | index.html:323、360 | 设置弹窗骨架（静态节点，随语言刷新） |
| `app.openKbFirst` / `app.openFileFirst` | 各 RPC 前置校验失败的提示（如 kb-check.js:623-625） | 未开库时的统一文案 |
| `agent.err.<code>` | js/agent-panel.js:132-157（`ERR_KEYS`）、160（`GENERIC_CODES`）、680-708（`errorText`/`errorDetail`/`fullErrorText`）；zh-CN.js:646-662 | 对话面板把后端 agent RPC 的**稳定 code** 映射为文案（`no_kb`/`busy`/`no_base_url`/`unknown_session`/`session_failed`/**`cancel_failed`（M1 收尾新增）**/`MISSING_CREDENTIAL`/`RATE_LIMIT` …）；**未登记的 code 回退后端中文 `message`**；兜底 code（`ask_failed`/`config_error`）额外拼后端原文（LLM 失败原因只在原文里）。**`agent_usage_stats` 本轮新增的 `usage_failed` / `unknown_session` 走同一兜底**（**2026-09-19 起前端已调用该 RPC**：dock 状态 bar 第四槽的缓存命中率，见 01 篇 §2.4；其这两个 code 仍走"未登记 code 回显后端原文"的兜底） |
| `agent.history.*` | index.html:227-231（**2026-09-19 起 = dock 的「当前会话」行**）；js/agent-panel.js:1946-1949（`histTitle`）、1991-2059（`renderHistoryList`）、2151-2168（`refreshHistory`）、878-915（`loadSession`）；zh-CN.js:610-614 | 会话列表（**2026-09-19 起在左栏「历史」页签**）：`none`（「（新会话）」，dock 当前会话行的空态）/`capped`（「（已截断）」，M1 收尾）/`delete`（行内删除按钮）；行标题/元信息用 `textContent` 写入（不注入 HTML） |
| `agent.stopped` / `agent.stopTitle` / `agent.status.stopped` | js/agent-panel.js:620-626（`messageEl` 的 `rec.stopped` 分支）、1402-1426（`stop()`）；index.html:237；zh-CN.js:610-611、629 | M1 收尾：生成中按钮文案「停止」（旧 `agent.abandon*` 已废除）、助手气泡后的「（已停止）」标注、状态行「已停止…」 |
| `agent.status.elapsed` | js/agent-panel.js:840-859（`tickWait`/`startWait`/`stopWait`）；zh-CN.js:625 | 等待计时后缀（`{n}s`），与 `agent.status.thinking` 由 `statusLine()` 拼成「生成中… Ns」 |
| `agent.statusBar.*` | index.html:248（静态节点，**空**）；js/agent-panel.js:752-828（`renderStatusUsage` 等）；zh-CN.js:635-645 | 本轮新增 9 键：`span` / `spanCache`（紧凑摘要，如 `↑8.7k ↓233 · 命中 62%`）、`line` / `cache` / `cacheUnknown` / `estimated` / `session` / `sessionCache` / `hint`（`title` 多行拆分，`\n` 连接）；命中率未知时**不渲染** `spanCache` 段。**2026-09-19 再追加 `hitRate`**（「缓存命中率 {rate}」/ `Cache hit {rate}`）—— dock 状态 bar 第四槽（原「历史（N 轮）」），追加在两个语言包末尾 `Object.assign` 块（zh-CN.js:1263-1265、en.js:1345-1347）⇒ 上表所有 `zh-CN.js:<行号>` 锚点未动 |
| `check.issue.<code>` | app.js:258-268（`localizeCheckIssue` + `rawLookup`） | **唯一**会翻译后端消息的机制：当前语言包有该 code 模板才翻译，否则原样显示后端中文 `message` |
| 后端返回的其它 `message` | ui.py / document.py / import_engine.py | **一律中文原样透传**，不参与 i18n（conventions/i18n.md:5.1 只对检查 issue 与少量 `backend.*` 键例外） |

## 5. 边界与已知坑

### 5.1 可嵌入性结论（要在非 pywebview 宿主里显示 Memoria）

| # | 必须满足 | 现状 | 需自建 |
|---|---|---|---|
| 1 | **后端能无窗口运行** | ❌ 无 headless 入口，服务随 GUI 起（§2.14） | 新增（或接受"必须拉起 GUI 进程"这一前提） |
| 2 | **宿主提供桥** | 契约点已固定：`window.memoria.api` 或 QWebChannel `bridge` 的 `invoke(method, argsJson)` | 宿主实现；最少需 `get_kb_path/open_kb/load_document/save_document/get_ui_settings/save_ui_settings`（`get_window_chrome` 可省，缺则窗口三键隐藏，window-chrome.js:304-308；**该 RPC 还返回 `min_width/min_height`（2026-09-18 起 1000×600），前端用它夹 JS 侧边缘缩放**——宿主自建时应一并声明自己的窗口最小尺寸，见 §5.4） |
| 3 | **端口与实例绑定** | pyqt6 路径已回环 + 随机端口；但 `_kb_root` 是进程级全局 | **一库一进程**；多库并存须多进程 |
| 4 | **静态资源可由任意 HTTP 服务提供** | ✅ 无 CSP / X-Frame-Options 拦截；iframe 可行 | 自建服务时应照抄 `no-store` 与 `?v=` 注入（防 WebView 复用旧 JS） |
| 5 | **顶栏拖拽区在 iframe 内的表现** | `.pywebview-drag-region` 在真实路径上会被 JS 改成 `no-drag`（window-chrome.js:349-351、333-335），且拖动绑定只发生在 `initWindowChrome()` 的 frameless 分支（339-397） | 无 `get_window_chrome()` 时**不绑任何拖动**：顶栏（含 `#app-badge`、底栏 `#status-kb`）是普通 DOM，不会拖动宿主窗口；副作用为零，但"可拖"的观感是假象 |

### 5.2 给集成方的自检清单

- [ ] 后端进程已起，`GET /` 返回 200 且 `Content-Type: text/html; charset=utf-8`
- [ ] `GET /app/js/bridge.js` 200，响应头含 `Cache-Control: no-store`
- [ ] 开库后 `GET /files/<KB 相对路径>` 能取到图片；未开库时 404（说明 `_kb_root` 未设）
- [ ] 桥已装：控制台 `window.memoria.api` 非空且 `MemoriaBridge.api()` 返回同一对象
- [ ] `memoriaready` 已派发（间接判据：`#welcome h1` 被写入版本号，window-chrome.js:303-307）
- [ ] 点「设置」能打开设置弹窗 → 说明 `bindEvents()` 已跑（app.js:12676-12687 已通过）
- [ ] 状态栏从「就绪」切换到库/文件统计 → 说明 `initKb()` 与各子系统 init 已完成
- [ ] 保存链路：`save_document` 返回 `{status:"ok"}`，磁盘 md mtime 变化且 `.memoria/manifest.yaml` 被更新
- [ ] 未开库时提示文案为 `app.openKbFirst`（而非空白）→ i18n 初始化正常
- [ ] 宿主窗口三键：无 `get_window_chrome` 时必须由宿主自己隐藏，不要依赖 `#window-controls`（它默认 hidden，但一旦有桥就可能被显示）

### 5.3 已知坑

1. **`/rpc` 不存在、且无 headless 入口**（本篇两处关键矛盾）：[../architecture.md](../architecture.md):21-23、44 与 deepseek-harness-integration.md:96、150 的"`/rpc` 暴露 UIAPI 93 方法"是**过时描述**——当前只有 `/` 与 `/<path:path>`，方法调用走 pywebview `js_api` 或 QWebChannel `invoke`，故"HTTP POST /rpc 驱动 Memoria"现在跑不通；而"只跑服务不跑窗口"必须新增代码（deepseek-harness-integration.md:151 与代码一致）。
2. **"保存自动清理图片"是错的**：hard-constraints.md:31 与代码相反（document.py:320-322；ui.py:867）。
3. **事实源口径三处不一致**（AGENTS.md §1 / kb-agent.md:70 / deepseek-harness-integration.md:87）——按 §2.10 第 5 条理解。
4. **一个进程只能服务一个库**：`_kb_root` 模块全局（static_server.py:31）。
5. **KB 文件响应没有 `no-store`**：`/files/` 只设 Content-Type/Length（static_server.py:91），外部宿主可能缓存图片；静态资源则有 no-store。
6. **兼容路径仍在**：读 sidecar 会回退旧路径（sidecar.py:90-98），读 pending 会迁移旧 YAML 并**删除** `pending.yaml`（pending.py:54-77）——外部工具若还在写旧文件，行为会突然改变。
7. **`.bak` 会出现在磁盘上**：yaml/json 原子写前都会 `copy2` 一份 `<name>.bak`（atomic_yaml.py:22-43；pending.py:45）→ 集成方遍历目录时要忽略 `*.memoria.yaml.bak` / `manifest.yaml.bak` / `pending.json.bak`。
8. **`.memoria/build/` 的写入不是原子的**（kb_build.py:222-227 直接 `write_text`），崩溃可能留下半包报告；它可删，不影响知识。
9. **无任何 origin/令牌校验**：pyqt6 路径的静态服务绑 `127.0.0.1` 且只读知识库文件，但**桥本身不校验调用方**（QWebChannel 不受同源限制）——同机任意页面只要拿到桥就能读写知识库；deepseek-harness-integration.md:150 也标注"该面当前无令牌"。
10. **跨进程并发写无互斥**：服务层的原子写只保证单次写入不半包，不提供文件级锁；GUI 与外部智能体同时写同一 md 属未定义行为（deepseek-harness-integration.md:120 已列为 X9）。

### 5.4 宿主窗口最小尺寸（2026-09-18 起 1000×600）

- **单一事实源**：`src/memoria/app/shell/host.py:7-15` 的 `WINDOW_MIN_WIDTH = 1000` / `WINDOW_MIN_HEIGHT = 600`（宿主协议模块，与 `WindowHost` 同文件）。**三处引用**：pywebview 壳 `create_window(min_size=(…))`（pywebview.py:480）、PyQt6 壳 `window.setMinimumSize(…)`（pyqt6.py:233）、`UIAPI.get_window_chrome()` 的 `min_width/min_height`（ui.py:662-675）与 `window_resize_to()` 的下限夹取（ui.py:677-684）；`scripts/diag_webview.py:98` 亦用同一常量；前端 `window-chrome.js:16` 的兜底默认值同步为 `{w:1000,h:600}`（RPC 不可用时才生效）。**改一处即全局一致**，不要再散落硬编码。
- **取 1000 的理由**：三栏并排所需宽度 = 左栏默认 17.5rem(280) + 右栏 dock 默认 22rem(352) + 文档区保底 `CONTENT_MIN_PX=360` ≈ 992 ⇒ 取整 1000，使最小窗口下 dock 仍正常显示（不触发 `-agent-dock--auto-hidden`）。高度沿用 600。
- **由谁执行**：最小尺寸是**窗口管理器层**的约束（pywebview `min_size` / Qt `setMinimumSize` 最终交给 OS），**不是** CSS 或 JS 能强制的；`get_window_chrome` 里的数值只是给前端在 JS 侧拖拽缩放时做同样的夹取，二者需保持同值。宿主自建（iframe 嵌入）时须自行声明；浏览器/CDP 环境下的"视口"不受它限制（见 01 篇 §7 本轮"未取证"条）。

## 6. 代码锚点表

| 要点 | 锚点 |
|---|---|
| 知识库目录约定 / 跳过目录 | storage/constants.py:1-17 |
| md 保存链路（原子写 + 缓存 + manifest + 图片注册表 + KP 重锚） | services/document.py:317-384 |
| 图片清理只在显式 RPC | services/document.py:320-322、1104；presentation/api/ui.py:867；js/image-tools.js:443、474 |
| manifest 结构 / 原子写 / 基线重建 | storage/manifest.py:35-62、111-152；storage/atomic_yaml.py:46-56 |
| sidecar 路径与旧路径回退 | storage/sidecar.py:66-98、116-117 |
| pending JSON 与旧 YAML 迁移 | storage/pending.py:33-93 |
| kp_targets 派生索引 | services/kp_index.py:139-183；services/document.py:248-265 |
| 图片目录 / 注册表 / 入库规则 | services/document.py:828-833、896-1040 |
| cache 与 build 子目录 | services/lexical_index.py:58；lexical_tokenizer.py:17；embedding_provider.py:42；search_aux.py:26；model_router.py:59；graph/kb_build.py:218-231 |
| 智能体工具包安装（幂等 / 不覆盖 review） | services/kb_agent.py:20-31、40-42、56-81、84-145 |
| UI 偏好磁盘文件与迁移 | storage/ui_settings.py:11-75；presentation/api/ui.py:647-658 |
| 前端桥（READY / pywebview / QWebChannel / 代理） | js/bridge.js:7、9-20、22-27、29-49、56-67、69-111、113-119 |
| 启动顺序与 boot 唯一入口 | js/app.js:12676-12687；js/index.html:372-415 |
| 无桥时的窗口三键处理 | js/window-chrome.js:301-308、330-337 |
| 窗口最小尺寸常量（唯一事实源） | src/memoria/app/shell/host.py:7-15（引用：pywebview.py:480、pyqt6.py:233、ui.py:662-684、window-chrome.js:16；见 §5.4） |
| 静态服务路由 / no-store / 资源版本注入 | presentation/static_server.py:94-156 |
| `/files/` 防穿越与 MIME | presentation/static_server.py:19-28、56-91 |
| PyQt6 静态服务线程与随机端口 | app/shell/static_server_thread.py:11-35；app/shell/pyqt6.py:224-225、268-273 |
| pywebview 启动（WSGI + js_api） | app/shell/pywebview.py:455-509 |
| QWebChannel 单槽 RPC 契约 | app/shell/api_rpc.py:14-67 |
| 对话面板 9 个 RPC / 伪流式作业 / 真取消 / 配置与偏好读写 / 会话历史与删除 / 用量统计 | presentation/api/ui.py:1155-1400（配置 1155-1193、问答 1194-1225、取消 1226-1252、会话列表 1258-1300、载入 1301-1328、删除 1329-1367、用量统计 1368-1400）；services/agent/ask_stream.py:1-400；services/agent/llm/config.py:164-174、247-330；storage/ui_settings.py:58-75（顶层 `agent` 段） |
| **重试与失败分类**（确定性立即失败 / 瞬时重试 / 面板等待上限 / 错误串带重试次数） | services/agent/llm/errors.py:62、70、87、96、205、247、345-347；services/agent/llm/providers/openai_compatible.py:272-277、281、303、485-497；services/agent/llm/retry.py:52-56；services/agent/ask_stream.py:96-98；services/agent/loop.py:146-150、238-246、307-311（§2.16） |
| **Agent 用量**（`Usage` 缓存字段 / 端点字段映射 / `loop/end.usage` / 只读 RPC / 报告脚本） | services/agent/llm/types.py:109-152（`Usage`，`cache_miss_tokens`）、132-145（`plus()`）；services/agent/llm/usage.py:105-159（`UsageMeter`）；services/agent/llm/providers/openai_compatible.py:428-464（`_usage_from_wire`）；services/agent/loop.py:133-143（`usage_payload()`）、390-398（`loop/end`）；services/agent/usage_report.py:1-225；presentation/api/ui.py:1368-1400；scripts/benchmark/usage/report_usage.py（§2.17） |
| **系统提示组装**（固定段落顺序 / 「用户引用（`@路径`）」段与其门控） | services/agent/prompt.py:12（段落顺序）、194-218（`FILE_REFERENCE_SECTION`）、221-222（`_has_tool`）、225-283（`build_system_prompt`，门控 262-263）、286-292（`prompt_debug_info`）；tests/test_agent_loop.py:489-506（§2.15） |
| 对话会话 JSONL 存储 / 历史重建（压缩 + 裁剪 + 回放与截断）/ 摘要扫描（去读放大）/ 续聊入口 | services/agent/session/store.py:56-66、169-237；services/agent/session/history.py:1-541（`COMPACTION` 124、`_TITLE_TYPE_MARK` 141、`_tool_message` 168-183、`_compaction_plan` 203-229、`compaction_shadowed` 231-233、`_replay` 236-300、`_truncate` 308-322、`conversation_events` 325-327、`replay_events` 330-350、`build_history` 353-372、`summarize_session` 398-400、`_title_from_line` 409-412、`summarize_session_file` 423-481、`conversation_messages` 484-516）；services/agent/ask.py:110-444（`build_loop` 130-173、`_history_chars` 175-183、`_compact_if_needed` 185-274、`_append_fallback_title` 276-286、`_maybe_generate_title` 288-322、`ask` 324-444、`replay` 340、`cancel` 341、回放注入 374、`messages=history` 411） |
| **长会话压缩（M2，`compaction` 事件）**（阈值/保留字符预算 / 区域选择与工具配对 / 摘要调用与 KV 前缀 / fail-closed / 落盘形状与回放口径） | services/agent/compaction.py:1-381（常量 105-172、`compact_threshold_chars` 188-190、`retain_chars` 193-197、`frame_summary` 201-203、`event_chars` 219-251、`balanced_cuts` 253-269、`select_span` 272-312、`summarize_span` 315-381）；services/agent/session/history.py:124、203-229、353-372；services/agent/ask.py:185-274、377-390；services/agent/loop.py:133-143（`usage_payload()`）；services/agent/session/store.py:49-50（`SESSION_FORMAT_VERSION`，**不 bump**）；tests/test_agent_compaction.py:1-465（§2.15、§7） |
| **工具结果裁剪（M2，`compaction/prune` 事件）**（阈值/头/尾预算与构造期「不得变长」校验 / 纯函数切片与 `tail=0` 分支 / 清单幂等与跳过被压缩覆盖的 seq / 记录的 fail-safe 回放与后写覆盖 / 区域选择按有效字符计账） | services/agent/pruner.py:1-234（`PRUNE` 69、`PRUNE_MARKER` 71、预算常量 73-77、`PruneError` 83-84、`PruneBudgets` 98-120、`apply_budget` 123-131、`applied_chars` 134-136、`prune_text` 139-150、`_records` 153-162、`prune_records` 164-171、`prune_applied` 174-194、`prune_plan` 197-234）；services/agent/session/history.py:22、36-46、168-183、236-300、353-372；services/agent/compaction.py:219-251、272-312；services/agent/ask.py:185-274、258-266；tests/test_agent_pruner.py:1-373（§2.15、§6.10） |
| **会话标题（M2，`session/title` 事件）**（规范化与字节截断 / 合格消息与折叠 / 确定性兜底 / 模型标题的框定与 fail-closed / `first-prompt` 节律 / log-only 不进模型输入 / 列表口径） | services/agent/title.py:1-472（事件名与限额 108-125、控制序列与隐形字符模式 131-144、`TitleError` 146-148、`TitleMessage`/`TitleSnapshot`/`TitleCall` 151-175、`clean_title_text` 178-190、`truncate_title_utf8` 192-207、`normalize_title` 209-212、`fallback_title` 214-223、`title_message` 230-244、`collect_title_messages` 246-261、`fold_title` 263-295、`_append` 297-318、`ensure_fallback` 320-335、`title_system_prompt` 337-347、`frame_messages` 349-356、`generate_title` 358-432、`auto_title` 434-472）；services/agent/session/history.py:23、48-55、141、409-412、464-469；services/agent/ask.py:276-286、288-322、391-417；js/agent-panel.js:1946-1949（`histTitle`）；tests/test_agent_title.py:1-425（§2.15、§6.11） |
| **会话检索（M2，`search_sessions` 工具）**（语义文本抽取 / 字面量匹配与防正则注入 / 摘要窗 / 过滤子 AND-OR / 四重有界化 / 字节级预筛 / 命中写成「会话 `<id>` 第 N 条」且不产生文档锚点） | services/agent/session/query.py:1-380（常量 95-107、`_STRUCTURAL` 110、`event_text` 127-148、`compile_text_pattern` 151-161、`snippet` 164-178、`SessionEventHit` 181-190、`SessionGroupHit` 192-202、`_Filters` 204-230、`_limit` 232-239、`_prefilter_ok` 241-249、`_scan` 251-302、`search_session` 308-334、`search_sessions` 336-380）；services/agent/tools/kb.py:73-80（`KB_TOOL_NAMES`）、83-84（`DEFAULT_SESSION_HITS` / `MAX_SESSION_HITS`）、446-482（`_search_session_history`）、566-592（工具声明）；tests/test_agent_session_query.py:1-355（§2.15、§6.9） |
| **真取消**（取消令牌 / 三个检查点 / 作业面收敛与幂等） | services/agent/loop.py:73-101（`CancelToken`）、216-218（`_cancelled`）、248-264（检查点② 与 `stream.close()`）、295-299（①）、380-386（③）；services/agent/ask_stream.py:107-241（`AskJob`：`note_reasoning` 151-160、`fail`/`succeed` 162-194、`cancel()` 196-209、`snapshot` 双游标 211-241）、337-353（`AskJobManager.cancel()`）、356-375（`poll`，`reasoning_cursor` 追加参数） |
| 壳选择 / CLI（无 headless） | app/shell/__init__.py:12-24；cli/main.py:111-125 |
| 后端消息本地化（仅 check.issue） | js/app.js:258-268 |

## 7. 未证实 / 待确认

- ⚠️ **本轮（2026-09-19 第四轮：M2 会话标题 `session/title`）已取证 / 未取证**。已取证：
  - **静态**：`py_compile` 全过（新模块 `services/agent/title.py` + 3 个改动文件 `services/agent/session/history.py`、`services/agent/ask.py`、`services/agent/loop.py`（仅 docstring 一行））；`node --check` `agent-panel.js` 通过；`node scripts/i18n_selftest.js` 12/12 PASS；`python scripts/scan_ui_strings.py` 仍为 `files=3 rows=5`（**无新增硬编码候选** —— 本次前端只改取值、未加文案）。
  - **单测**：`pytest -q` **184 passed**（原 153 + 新增 **31** 例 `tests/test_agent_title.py`，1-425 行）。覆盖：规范化（CSI / OSC / **未终结 OSC** / 两字节 ESC、非空白 C0-C1、方向与隐形字符、空白折叠、**按 UTF-8 字节截断且不切开码点**、非法上限 5 例）；合格消息与折叠（非人类 / 空白 / 纯控制字符不合格、`through_seq` 上界、**最后一条非空标题胜出**）；兜底（首条消息前 8 词 / 96 字节、只落一次、已有标题或没有合格消息则跳过）；模型调用（**请求形状**：system = `title_system_prompt()`、单条 `user`、正文以固定前缀开头且其后是 `[{seq,text}]` 的合法 JSON、`max_tokens=96`；正常返回带 usage；**fail-closed 七路**：error / aborted / max-tokens / tool-calls / content-filter / 空正文 / 无终止事件；输入超限与空选材**一次请求都不发**；`AgentLlmError` 被包成 `TitleError`；取消）；节律（恰好一条合格消息才生成，两条则不发请求）；端到端（首轮落 `fallback` + `provider` 两条且后者带 `usage`、**次轮不再生成**、**被取消的轮次只留兜底**、**标题调用失败不影响问答**、老会话再聊一句补兜底但不做模型标题、**标题永不进模型输入**（主回合请求无标题字样 + `build_history` 不多出消息 + 列表扫描与折叠同口径））。
  - **浏览器实测**（harness 端口 **8645**，`MEMORIA_HARNESS_KB` 指向临时库、`MEMORIA_CONFIG_DIR` 隔离；**不需要模型** —— 会话文件里的 `session/title` 由脚本直接写入，provider 标题在后、兜底在前）：`/rpc` `agent_sessions_list` 返回 `title = "多层感知机的要点"`（**折叠出的 provider 标题**，既不是 `preview` 也不是首条提问）；浏览器里 `#agent-history` 的选项为 `{value: "session-title-demo", text: "多层感知机的要点（1 轮）"}`、`optionCount = 2`、未禁用；`#-agent-dock` 与 `#agent-input` 均存在（面板已初始化）。
  - **口径（已写进 §2.15）**：① 标题 **log-only**：不进消息序列、不进模型输入、不被 `search_sessions` 检索；② 来源最新者胜（`fallback` → `provider`），兜底零成本、模型标题**每会话首轮一次**；③ 被取消的轮次不生成；④ 列表 `title` 优先取折叠标题，没有标题事件才回落「首条提问前 40 字」；⑤ 标题调用用量记在 `session/title.usage`，但**不进** benchmark / 面板状态栏（只扫 `loop/end`）。
  - **未取证**：① 真实模型端点下**标题的质量与语言选择**（只做静态 + 单测 + 假 provider + 手写会话文件；用户 `config/agent.json` 是真密钥、**刻意不调用**）；② 真机上「首轮多等一个极小辅助调用」的实际手感（本地无异步标题服务，见 §6.11 的取舍 1）；③ 长会话列表里标题过长时的换行观感（下拉宽度由 `.-agent-history-select` 决定，本次未改样式）。语义偏差与取舍详见 [../../design/dsh-agent-port.md §6.11](../../design/dsh-agent-port.md)。
- ⚠️ **上一轮（2026-09-19 第三轮：M2 工具结果裁剪 `compaction/prune`）已取证 / 未取证**。已取证：
  - **静态**：`py_compile` 全过（新模块 `services/agent/pruner.py` + 4 个改动文件 `services/agent/session/history.py`、`services/agent/compaction.py`、`services/agent/ask.py`、`services/agent/session/query.py`（后者仅 docstring 补一行偏差说明））。
  - **单测**：`pytest -q` **153 passed**（原 132 + 新增 **21** 例 `tests/test_agent_pruner.py`，1-373 行）。覆盖：纯函数（恰好等于阈值不裁；头+标记+尾形状与长度上界；**`tail=0` 不把整串当末段**；预算非法值 7 例构造期拒绝，含「头+标记+尾 > 阈值」；清单只挑超预算 `tool/result`、跳过非工具事件与未超预算者；幂等 + 跳过被 `compaction` 覆盖的 seq；畸形记录整条忽略）；回放（记录就地生效、**原事件逐字保留**、不带裁剪表即原始视图、未知 seq 忽略、同一 seq **后写覆盖**）；计账（`event_chars` 覆盖表命中/未命中、`select_span` 按有效字符选区间 —— 同一组事件在有效视图下由 `(0,4)` 变为 `None`）；端到端（**裁完够用 ⇒ 只发 1 次模型调用**且主回合请求含标记、无被删中段；裁完仍超 ⇒ 照常压缩且**摘要器读到裁剪视图**；预算内一次多余调用都不发；仅追加 + `seq` 连续 + 不落任何 `compaction*`）。
  - **口径（已写进 §2.15）**：① 触发条件与压缩同（回放历史 > 25600 字符），**免模型**，裁完够用即**免掉**一次摘要调用；② 阈值 8192 / 头 4096 / 尾 1024 **码点**，`PRUNE_MARKER` 与上游逐字一致；③ **原事件留在日志里**，只有发给模型的请求用裁剪视图（检索/载入/报告/审计仍是原文）；④ 记录里带 `head`/`tail` ⇒ 回放**不随默认预算漂移**，形状不全则整条忽略。
  - **修掉的坑（写作期自查）**：`tail=0` 时 `text[-0:]` 会退化为整串 —— 已用显式分支 + 单测钉住。
  - **未取证**：① 真实模型端点下「裁剪后模型是否仍答得对」（**信息有损**，上游同样列为已知限制；用户 `config/agent.json` 是真密钥、**刻意不调用**）；② 裁剪耗时未做 A/B 墙钟（纯字符串切片、线性复杂度，但**未实测**）。语义偏差与取舍详见 [../../design/dsh-agent-port.md §6.10](../../design/dsh-agent-port.md)。
- ⚠️ **更前一轮（2026-09-19 第二轮：M2 会话检索 `search_sessions`）已取证 / 未取证**。已取证：
  - **静态**：`py_compile` 全过（新模块 `services/agent/session/query.py` + 1 个改动文件 `services/agent/tools/kb.py`）。
  - **单测**：`pytest -q` **132 passed**（原 104 + 新增 **28** 例 `tests/test_agent_session_query.py`，1-355 行）。覆盖：语义文本抽取规则表（语义事件取值正确、结构性/未知 type 返回空、`compaction` 取 `summary`、`tool_calls` 的 name+arguments 入文）；字面量匹配（正则元字符与 `\d`/`.*` 当字面量、空白弹性、大小写不敏感 + Unicode、空查询报错）；摘要窗（命中居中、两侧省略号、空白折叠）；会话内检索（`seq` 升序、`types` 子句内 OR、`time`/`seq` 区间、`limit=0` 返回空、会话不存在返回空、非法 limit/会话 id 报错）；跨会话（`modified_at` 倒序分组、`sessions_limit` 夹紧、`hit_limit` 每会话上限、`best` = 最小 `seq`、`title`/`turn_count` 取自 `summarize_session_file`）；字节预筛（ASCII 大小写差异仍能命中）；工具面（`KB_TOOL_NAMES` 与 `build_kb_tools()` 实际工具集**逐项一致**、只读、命中写成「会话 `<id>` 第 N 条」**且不含 `文件:行号`**、空 query 报错、无命中时提示改用 `search_kb`、`limit` 生效）。
  - **口径（已写进 §2.15）**：① 只检索**第一方语义事件**的文本（未知 type 不因载荷里有字符串就变成可检索）；② `compaction.summary` **参与检索**（本地扩展）；③ 工具命中形如「会话 `<id>` 第 N 条」、**不产生 `文件:行号` 锚点**；④ 四重有界（单文件 2 MiB / 跨会话 ≤ 500 份 / 单页 ≤ 200 / 工具面 ≤ 20）。
  - **修掉一个真 bug**：`limit=0` 原仍返回 1 条（上限判断从 `hits.append` 之后移到之前，query.py:288-289），由新写的 `test_search_session_respects_limit` 逮到。
  - **未取证**：① 真实模型端点下模型**是否会在该用 `search_sessions` 时用对**（工具选择正确性）—— 只做静态 + 单测 + 工具面形状核对，用户 `config/agent.json` 是真密钥、**刻意不调用**；② 大库（几百份会话）下的扫描耗时未做 A/B 计时（有界性有单测，但**未实测墙钟**）；③ 真实鼠标/前端交互无关（本块**无前端改动**）。语义偏差与取舍详见 [../../design/dsh-agent-port.md §6.9](../../design/dsh-agent-port.md)。
- ⚠️ **更早一轮（2026-09-19 第一轮：M2 长会话压缩 `compaction`）已取证 / 未取证**。已取证：
  - **静态**：`py_compile` 全过（新模块 `services/agent/compaction.py` + 4 个改动文件 `services/agent/session/history.py`、`services/agent/ask.py`、`services/agent/loop.py`、`services/agent/usage_report.py`）。
  - **单测**：`pytest -q` **104 passed**（原 81 + 新增 **23** 例 `tests/test_agent_compaction.py`，1-465 行）。覆盖：区域选择（工具配对切割点 / 尾部逐字保留 / 最小覆盖量 / 必须含用户消息 / 尽量多压）；回放（原位替换、链式只出最新、无效记录不吞事件、**工具配对完好**、可关压缩取原始视图）；摘要器 fail-closed 六例（error / aborted / max-tokens / 空正文 / 工具调用 / 取消）+ 请求形状（指令在最后一条 user、对话前缀原样保留）；端到端（长会话自动压缩并落 `compaction`、主回合请求**不再含被覆盖旧料**、**压缩失败照常答题**、短会话一次多余调用都不发、**仅追加**：既有记录逐条不变 + seq 连续 + 仍是「一行一 JSON」）。
  - **口径（已写进 §2.15 / §2.17）**：① 阈值 25600 字符 / 尾部保留 5120 字符（= 32000 × 0.8 / 0.16）；② `compaction` 事件**纯追加、不 bump `SESSION_FORMAT_VERSION`**（旧读者降级为「没有压缩」）；③ 摘要调用用量记在 `compaction.usage`，**不进 benchmark、也不进面板状态栏用量格**。
  - **未取证**：① 真实模型端点下的**摘要质量**与**压缩前后 A/B**（M2 门禁之一；上下文长度易量，**回答可回溯性**需真人用真实库对照，用户 `config/agent.json` 是真密钥、**刻意不调用**）；② 真实鼠标拖拽手势（沿用旧条目）。语义偏差与取舍详见 [../../design/dsh-agent-port.md §6.8](../../design/dsh-agent-port.md)。
- ⚠️ **上一轮（2026-09-18：Agent 用量可视化 + 用量报告）已取证 / 未取证**。已取证：
  - **静态**：`py_compile` 7 个 Python 文件（`llm/types.py`、`llm/usage.py`、`llm/providers/openai_compatible.py`、`loop.py`、`usage_report.py`、`api/ui.py`、`scripts/benchmark/usage/report_usage.py`）、`node --check` 3 个前端文件（`agent-panel.js`、`i18n/{zh-CN,en}.js`）、`node scripts/i18n_selftest.js` 12/12 PASS、`python scripts/scan_ui_strings.py`（files=3 rows=5，**无新增硬编码候选**）。
  - **单测**：`pytest tests/ -q` **80 passed**（新增 `tests/test_agent_usage.py` 13 例）——DeepSeek 形态（顶层 `prompt_cache_hit_tokens`/`prompt_cache_miss_tokens`）/ OpenAI 形态（`prompt_tokens_details.cached_tokens`，未命中量按 `prompt - cached` 补）/ 两者皆缺 `cache_read_tokens is None` 且**不**误置 `estimated` / SSE 全链路落 `UsageEvent` / `Usage.plus()` 与 `UsageMeter` 合并含 None 的混合 / `loop/end.usage` 载荷带三 cache 键 / 命中率计算 / `cache_unknown_turns` 计数 / 命中率未知为 `None`（显式 `0` 仍算**已知** 0%）/ 扫描上限 `capped` 且只统计上限内轮次。
  - **真实样本**（`python scripts/benchmark/usage/report_usage.py --kb docs/example/AAA_Vocab --label real-sample`）：**1 会话 / 3 轮 / 输入 128,907 + 输出 4,504 = 133,411 tokens**、**命中率「未知」**（不是 0%）、`cache_unknown_turns=3`、`estimated_turns=0`；产物 `scripts/benchmark/usage/results/usage-real-sample_6451d258.{json,md}`。**只读证据**：KB 全量 100 个文件的 (相对路径, SHA256) 快照在脚本运行前后**完全一致**。
  - **端到端 11/11 PASS**（本地假 SSE 端点，usage 带 DeepSeek cache 字段：`prompt=8713`/`completion=233`/`cache_hit=5402`/`cache_miss=3311`；harness `/rpc` 直转真实 `UIAPI` + headless Edge（`--headless=new`）+ CDP（websocket-client 直连，断言在 Python 侧）；`MEMORIA_CONFIG_DIR` 指向临时目录，KB 亦为临时目录；脚本与产物在仓库外临时目录）：
    - ③ **boot**：脚本全就绪后装桥（`window.pywebview`）并派发 `pywebviewready` ⇒ `memoria.api` 可用、`#agent-messages` 渲染空态（证明 `MemoriaAgentPanel.init()` 已执行）；
    - ⑧ `#status-agent` 出现，文本 **`↑8.7k ↓233 · 命中 62%`**（与端点 5402/8713=62.0% 一致）；
    - ⑨ `title`（多行）含 `缓存：命中 5402 / 未命中 3311 / 命中率 62%` 与 `本会话累计 1 轮：…` + `本会话累计缓存：…`；
    - ⑩ 无活动时 `#status-agent` 文本与 title 皆空且 `getComputedStyle(...).display === "none"`（不占位）；
    - ⑪ 先折叠 dock（`clientWidth=0`）再点 `#status-agent` ⇒ `clientWidth=351`（dock 重新可见）；
    - ⑫ 会话文件 `loop/end.usage` = `{prompt_tokens: 8713, completion_tokens: 233, total_tokens: 8946, estimated: false, cache_read_tokens: 5402, cache_write_tokens: null, cache_miss_tokens: 3311}`；假端点侧 `hits=1`。
  - **配置隔离证据**：真实 `config/agent.json`（SHA256 `C9CFC8B72271A4FA382270F4210BC59063432CA8F417DED86CCB0FB54CD01D50`）与 `config/ui-settings.json`（`DBAE36E137DF802C08DC071E5C3A61DCB37A2F9AB9854DC498E114E4E2E0A326`）在整个验证期间**未变**（harness 与报告脚本均指向临时目录）。
  - **顺带的 harness 发现（非本轮引入，属既有前端装载顺序特性）**：桥若在 **document-start** 就绪（`window.pywebview.api` 在 `bridge.js` 之前存在），`bridge.js:102` 会立刻 `installApi` + 派发 `memoriaready`，而 `app.js` 紧随其后加载、其 `MemoriaBridge.onReady` 回调**立即执行**——此时 `agent-panel.js`（`index.html` 末位）尚未加载，`MemoriaAgentPanel?.init?.()` 落空（`MemoriaImportFlow` / `MemoriaToolbarSearch` / `MemoriaImageTools` / `MemoriaKbCheck` / `MemoriaKbAgent` / `MemoriaFileTree` 等同样在 `app.js` 之后加载的模块同理）。生产路径不受影响（pywebview/Qt 的 `pywebviewready` 在脚本加载后异步到达）；但对**同步提供桥的宿主**这是一个既有的装载顺序脆弱点，本轮仅如实记录、未改代码。
  - **未取证**：真实模型端点（`api.deepseek.com`）下的**命中率数值**与 `cache_write_tokens`（用户 `config/agent.json` 是真密钥，**刻意不调用**）；`#status-agent` 的悬停 `title` 在真机不同主题/`uiScale` 下的换行观感。
- ⚠️ 待确认（未能取证）：pywebview 内部如何托管 WSGI app（是否真的监听某 TCP 端口、端口能否从 JS 侧读到）——bridge.js 不使用端口，`window.pywebview.api` 不经 HTTP，故本次未取证。
- ⚠️ 待确认（未能取证）：`.memoria/build/` 下具体产物文件名与数量（只取证了 `_build_dir()` 与 `_write_json` 的写入方式，未穷举调用点）。
- ⚠️ 待确认（未能取证）：`.memoria/images/registry.json` 的字段结构（仅取证其存在与重建时机）。
- ⚠️ 待确认（未能取证）：iframe 场景下前端 `localStorage`（`-i18n`、`-display-settings`、`-graph-settings`、`-sidebar-*`）归属哪个 origin、是否与宿主共享；以及复用 `StaticServerThread`（`wsgiref.simple_server`，单线程阻塞）时的并发能力——均未在真实环境验证。
- ⚠️ 待确认（未能取证）：`.memoria/agent/review/**` 的 `cards.json`/`progress.json` 结构与字段（kb-agent.md:195-200 有描述，本次未读 `fsrs.py` 实现核对）。
- ⚠️ **本轮（2026-09-18：M1 收尾打磨四件事——真取消 / 会话列表去读放大 / 恢复上次会话 / 删除会话）已取证 / 未取证**。已取证：
  - **去读放大 A/B（`agent_sessions_list`）**：临时知识库造 **30 份**会话（共 3.4 MiB、每份 114.5 KiB、每份 10 轮）分别计时（`time.perf_counter` 包一次 `agent_sessions_list`，取 5 次最小值）：**改动前（逐份 `summarize_session()` 整体回放）12.25–13.89 ms → 改动后（`summarize_session_file()` 原始行扫描 + 2 MiB 上限）4.75–5.63 ms**，两轮复测约 **2.2–2.7×**；**单份 3.0 MiB 病态会话：10.39–10.54 ms → 1.39–1.65 ms（≈6.4–7.5×，`capped=true`）**；摘要与旧实现逐条比对**完全一致**（等价性另有单测断言，含中文/引号/反斜杠/转义换行）。样本量说明：**实测就是 30 份**（`SESSION_LIST_LIMIT` 上限）。
  - **会话删除（`agent_session_delete`）**：单测覆盖正常删除（删除后知识库逐文件 SHA256 只少该 JSONL）与 8 种非法/未知 id（`../decoy`、`..\decoy`、`a/b`、`..`、空串、空白、中文 id、不存在 id）——**全部结构化返回 `code:"unknown_session"` 且知识库快照逐字节不变**；端到端在真实浏览器里验证「两次点击确认」与"3 秒复位"（详见 [01 篇 §7](./01-shell-and-layout.md)）。
  - **真取消（`agent_ask_cancel`）**：端到端（慢速假 SSE 端点）验证停止后 `loop/end.stop_reason="aborted"`、部分文本保留、`busy` 立即释放；**假端点侧观察到客户端在第 2 个分片后就关闭连接**（`frames_sent=2/15`、`aborted=true`）⇒ 后端确实不再收完模型流。
  - **顺带的行为变更（同一轮必须修）**：`llm/providers/openai_compatible.py` 的响应体读取由 `response.read(_READ_SIZE)` 改为 `response.read1(_READ_SIZE)`。独立实测：`HTTPResponse.read(65536)` 在「无 Content-Length / `Connection: close`」的 SSE 上**阻塞到 EOF**（3.6s 的流只在结束时返回一整块 1094B），`read1` 则逐帧返回（0.02/0.32/0.62/… s 各 90B）——这是"真增量 + 可取消"的前置条件，也是面板「生成中…」从"整段一次性上屏"变为真打字机的原因。
  - **偏好落点**：`ui-settings.json` 顶层新增 `agent` 段（`{lastSessionId}`）；端到端断言写入后 `layout.sidebarWidth` 仍在、刷新页面能自动恢复上次会话、会话文件不存在时静默空态。
  - **测试与静态**：`pytest tests/ -q` **67 passed**（新增 `tests/test_agent_cancel.py` 6 例 + `tests/test_agent_history.py` 5 例）；`py_compile` 6 个 Python 文件、`node --check` 4 个前端文件、`node scripts/i18n_selftest.js` 12/12 PASS、`python scripts/scan_ui_strings.py`（files=3 rows=5，**无新增硬编码候选**）。
  - **配置隔离证据**：真实 `config/ui-settings.json`（SHA256 `3BC0ACC487865714FBDD2993B4C9EE6D1D55CBF7AFA46482DAA48B3D5228D894`）与 `config/agent.json`（`C9CFC8B72271A4FA382270F4210BC59063432CA8F417DED86CCB0FB54CD01D50`）运行前后**完全一致**。
  - **未取证**：① 真实模型端点下的取消/恢复/删除观感（用户 `config/agent.json` 是真密钥，**刻意不调用**）；② 被取消那一轮的 `assistant/message` 不落盘（见 [01 篇 §7 待拍板项](./01-shell-and-layout.md)）；③ 多知识库间切换时的恢复路径（只验证了刷新页面）。
- ⚠️ **前一轮（2026-09-18 前半：M1 收尾——确定性连接失败不重试 + 面板世代号作废）已取证 / 未取证**。已取证（**必拒连端点 `http://127.0.0.1:9/v1` 走 `agent_ask_start` + `agent_ask_poll`，`MEMORIA_CONFIG_DIR` 指向临时目录**）：端到端耗时 **27578ms → 2281ms**（单次连接拒绝实测 ≈2063ms；修复前 = 6 次尝试 × 2.06s + 5 次退避 15.5s，与人工实测 27986ms 同量级），修复后重试日志 **0 行**、错误消息含目标 URL 与「确定性失败，不会重试」；同轮新增 12 例单测（确定性失败不可重试 / 瞬时故障仍可重试 / 假时钟下 `total_timeout_s` 放弃 / 重试计数回调 / 错误串含「已重试 N 次」/ 面板策略取值与作业传参），`pytest tests/ -q` **56 passed**。前端「清空对话 / 忽略本次」作废语义的端到端断言见 [01 篇 §7](./01-shell-and-layout.md)。**未取证**：真实模型端点下的重试节奏与文案观感（用户 `config/agent.json` 是真密钥，**刻意不调用**）；面板**未做** `UNREACHABLE` 的本地化文案（前端未加 code 映射，经 `ask_failed` 兜底 + 后端原文呈现）。
- ⚠️ **M1c（2026-09-18：多轮续聊 + 会话历史）已取证 / 未取证**。已取证（**harness `/rpc` + 本地假 SSE 端点（照 `scripts/agent_llm_smoke.py --mock` 的帧格式），`MEMORIA_CONFIG_DIR` 指向临时目录，脚本与产物在仓库外临时目录**；27/27 PASS）：两次连续提问（`agent_ask_start`/`agent_ask_poll`）共用同一 `session_id`，第二次请求体（假端点侧记录）含第一轮的 user/assistant 消息且末尾是当前问题；`agent_sessions_list` 返回该会话（`turn_count=2`、`preview=第一问`、`modified_at` 毫秒）；`agent_session_load` 返回两轮 4 条消息；未知会话 ⇒ `code:"unknown_session"`；两次提问只**新增** `.memoria/agent/sessions/<id>.jsonl`，两个只读 RPC 前后 KB 文件快照（相对路径 → SHA256）完全一致；真实 `config/agent.json`（SHA256 `c9cfc8b7…`）与 `config/ui-settings.json`（`88f65cd1…`）前后一致。另：**事件类型全集已核实**（M1c 当时 7 类：`user/message`、`assistant/message`、`tool/call`、`tool/result`、`step/start`、`step/error`、`loop/end`，写入点 loop.py:302-398 与 ask.py:297；**M2（2026-09-19）起新增第 8 类 `compaction`**，见 §2.15），回放口径见 §2.15。**未取证**：① 真实模型端点下的续聊效果（用户 `config/agent.json` 里是真密钥，刻意不调用）；② 前端 `#agent-history` 下拉的原生点击/禁用态与等待计时在真机上的观感（端到端走 `/rpc`，未开浏览器）；③ 长会话（> 40 条 / > 32000 字符）截断后的模型表现（截断有单测断言）。
- ⚠️ **上一轮（2026-09-17：对话面板与端点配置）未取证**：① 真实模型调用下 `agent_ask_poll` 的增量节奏（SSE 分片 → 250ms 轮询的实际观感）与 `answer` 覆盖流式文本的效果（需真实端点）；② `config/agent.json` 被外部（非本面板）手改后的行为只做了「读时生效」的推理，未在真机验证；③ `agent_ask_poll` **不返回完整文本**（只返回 `delta`），故宿主若想在多端同时渲染同一作业，需按 `cursor` 自持缓冲（M1c 未改此语义）。
