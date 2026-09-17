# 10 · 磁盘布局与宿主嵌入

> **用途**：说清 ①一个知识库目录里**究竟有什么文件、谁写的、能不能删、是不是事实源**；②要把 Memoria 前端**嵌进别的宿主**（Electron / 其它 webview / iframe）时，前后端各自提供了什么、缺什么、必须自建什么。
> **目标读者**：外部集成方（把 Memoria 嵌进插件 / 桌面壳 / 智能体的人）、维护 `.memoria/**` 数据契约的人、排查"文件被谁改了"的人。
> **关联文档**：[README.md](./README.md)（本套用法与维护约定）、[../hard-constraints.md](../hard-constraints.md)（红线）、[../architecture.md](../architecture.md)（分层——注意其 `/rpc` 描述已过时，见 §5）、[../../design/kb-agent.md](../../design/kb-agent.md)（知识库侧智能体契约）、[../../design/deepseek-harness-integration.md](../../design/deepseek-harness-integration.md)（对外能力面分析）、[01-shell-and-layout.md](./01-shell-and-layout.md)（窗口 chrome 与顶栏拖拽区）。
> **状态**：生效中，2026-09-15。

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
        └── review/                       cards.json / progress.json —— **产品永不覆盖**（kb_agent.py:8、114）
```

**不在知识库里的那一份**：UI 偏好（含语言、字号、缩放、图谱参数、窗口最近列表）写在**程序目录** `config/ui-settings.json`（`storage/ui_settings.py:11-28`），可用环境变量 `MEMORIA_CONFIG_DIR` 改址；旧位置 `~/.memoria/ui-settings.json` 会自动迁移一次（ui_settings.py:14-15、31-43）。→ **知识库可携带，UI 偏好不可携带**。

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
| UI 偏好 | `config/ui-settings.json` | 前端 → `save_ui_settings` | 可删（回默认值） | ❌ |

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
| 窗口三键 | `#window-controls` 保持 `hidden`（HTML 默认即 hidden；`initWindowChrome` 无 `get_window_chrome` 时直接返回） | index.html:87；window-chrome.js:286-293 |
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

## 3. 交互流程

**3.1 首帧 → boot**：请求 `/` → 返回注入了 `?v=` 的 index.html（no-store）→ 按 index.html:383-434 的顺序加载脚本（graph-* → *-settings → `vendor/qwebchannel.js` → `bridge.js` → `window-chrome.js` → 编辑管线 → i18n 包 → `i18n.js` → `scheduler.js` → `app.js` → 各子系统）→ bridge.js 立即安装（pywebview 已有 api）或轮询等待（Qt）→ `installApi()` → 派发 `memoriaready` → app.js 的 `onReady` 回调执行 `bindEvents()` → 导入流/搜索/图片/检查/智能体/文件树 `init()` → `initKb()`（读启动库路径）→ `initWindowChrome()`。

**3.2 一次 RPC 往返**：前端 `call("name", ...)`（app.js:385-387）→ `window.memoria.api.name(...args)`：
- pywebview：直接调用宿主对象方法（pywebview 内部完成序列化）；
- PyQt6：`bridge.invoke("name", JSON.stringify(args))` → 后端 `UIAPIRpc.invoke` 解析 args、`getattr(UIAPI, method)(*args)`、`json.dumps(result, ensure_ascii=False, default=str)`（api_rpc.py:44-67）→ 前端 `parseRpcResult` 反序列化（bridge.js:9-20）。
- 返回约定：业务失败统一 `{status: "error", message}`（各 API 方法一致，如 ui.py:659-660、766-771）；前端 `call()` 在方法不存在时抛 `app.apiUnavailable`。

**3.3 嵌入时序要点**：宿主应先起后端与静态服务，**再去加载页面**；桥必须在 `bridge.js` 执行前或 `memoriaready` 派发前就绪，否则只能靠两条兜底（pywebview 的 `pywebviewready`；Qt 的 25ms×400 轮询）。开库后才会 `set_kb_root`，故 `/files/...` 在开库前一律 404（static_server.py:56-61）。

## 4. i18n key 前缀

本篇涉及面很窄，但集成方会碰到：

| 前缀 / 键 | 出现位置 | 说明 |
|---|---|---|
| `settings.configPath` | graph-settings.js:874-876；zh-CN.js:651 | 设置弹窗底部：`设置保存在程序目录：{path}`（`{path}` 来自 `get_ui_settings().settings_rel`） |
| `modal.settings` / `common.close` | index.html:289、298 | 设置弹窗骨架（静态节点，随语言刷新） |
| `app.openKbFirst` / `app.openFileFirst` | 各 RPC 前置校验失败的提示（如 kb-check.js:623-625） | 未开库时的统一文案 |
| `check.issue.<code>` | app.js:258-268（`localizeCheckIssue` + `rawLookup`） | **唯一**会翻译后端消息的机制：当前语言包有该 code 模板才翻译，否则原样显示后端中文 `message` |
| 后端返回的其它 `message` | ui.py / document.py / import_engine.py | **一律中文原样透传**，不参与 i18n（conventions/i18n.md:5.1 只对检查 issue 与少量 `backend.*` 键例外） |

## 5. 边界与已知坑

### 5.1 可嵌入性结论（要在非 pywebview 宿主里显示 Memoria）

| # | 必须满足 | 现状 | 需自建 |
|---|---|---|---|
| 1 | **后端能无窗口运行** | ❌ 无 headless 入口，服务随 GUI 起（§2.14） | 新增（或接受"必须拉起 GUI 进程"这一前提） |
| 2 | **宿主提供桥** | 契约点已固定：`window.memoria.api` 或 QWebChannel `bridge` 的 `invoke(method, argsJson)` | 宿主实现；最少需 `get_kb_path/open_kb/load_document/save_document/get_ui_settings/save_ui_settings`（`get_window_chrome` 可省，缺则窗口三键隐藏，window-chrome.js:289-293） |
| 3 | **端口与实例绑定** | pyqt6 路径已回环 + 随机端口；但 `_kb_root` 是进程级全局 | **一库一进程**；多库并存须多进程 |
| 4 | **静态资源可由任意 HTTP 服务提供** | ✅ 无 CSP / X-Frame-Options 拦截；iframe 可行 | 自建服务时应照抄 `no-store` 与 `?v=` 注入（防 WebView 复用旧 JS） |
| 5 | **顶栏拖拽区在 iframe 内的表现** | `.pywebview-drag-region` 在真实路径上会被 JS 改成 `no-drag`（window-chrome.js:334-336、318-320），且拖动绑定只发生在 `initWindowChrome()` 的 frameless 分支（324-365） | 无 `get_window_chrome()` 时**不绑任何拖动**：顶栏（含 `#app-badge`、`#kb-indicator`）是普通 DOM，不会拖动宿主窗口；副作用为零，但"可拖"的观感是假象 |

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
| 无桥时的窗口三键处理 | js/window-chrome.js:286-293、315-322 |
| 静态服务路由 / no-store / 资源版本注入 | presentation/static_server.py:94-156 |
| `/files/` 防穿越与 MIME | presentation/static_server.py:19-28、56-91 |
| PyQt6 静态服务线程与随机端口 | app/shell/static_server_thread.py:11-35；app/shell/pyqt6.py:224-225、268-273 |
| pywebview 启动（WSGI + js_api） | app/shell/pywebview.py:455-509 |
| QWebChannel 单槽 RPC 契约 | app/shell/api_rpc.py:14-67 |
| 壳选择 / CLI（无 headless） | app/shell/__init__.py:12-24；cli/main.py:111-125 |
| 后端消息本地化（仅 check.issue） | js/app.js:258-268 |

## 7. 未证实 / 待确认

- ⚠️ 待确认（未能取证）：pywebview 内部如何托管 WSGI app（是否真的监听某 TCP 端口、端口能否从 JS 侧读到）——bridge.js 不使用端口，`window.pywebview.api` 不经 HTTP，故本次未取证。
- ⚠️ 待确认（未能取证）：`.memoria/build/` 下具体产物文件名与数量（只取证了 `_build_dir()` 与 `_write_json` 的写入方式，未穷举调用点）。
- ⚠️ 待确认（未能取证）：`.memoria/images/registry.json` 的字段结构（仅取证其存在与重建时机）。
- ⚠️ 待确认（未能取证）：iframe 场景下前端 `localStorage`（`-i18n`、`-display-settings`、`-graph-settings`、`-sidebar-*`）归属哪个 origin、是否与宿主共享；以及复用 `StaticServerThread`（`wsgiref.simple_server`，单线程阻塞）时的并发能力——均未在真实环境验证。
- ⚠️ 待确认（未能取证）：`.memoria/agent/review/**` 的 `cards.json`/`progress.json` 结构与字段（kb-agent.md:195-200 有描述，本次未读 `fsrs.py` 实现核对）。
