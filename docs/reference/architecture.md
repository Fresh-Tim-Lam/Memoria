# 系统架构总览（Architecture）

> **用途**：Memoria 整体架构说明——壳层、服务端、前端模块、数据流与存储布局，供维护者与 AI Agent 理解系统全貌。
> **目标读者**：维护者 / AI Agent（改代码前建立全局认知；深入设计见 `design/system-design.md`）。
> **关联文档**：[glossary.md](./glossary.md)（术语表）；[hard-constraints.md](./hard-constraints.md)（硬约束）；[design/system-design.md](../design/system-design.md)（设计文档）。

---

## 1. 总体形态

Memoria 是**本地桌面应用**：Python 后端 + 原生 JS 前端，跑在 WebView 壳中。无云端依赖，全离线。

```
┌────────────────────────── 桌面壳（Shell）──────────────────────────┐
│  pywebview（默认） | pyqt6（备选，自定义无边框窗）                   │
│  MEMORIA_SHELL 环境变量选择；MEMORIA_FRAMELESS=1 → window-chrome   │
└──────────────────────────────┬─────────────────────────────────────┘
                               │ WebView2 / QtWebEngine
┌──────────────────────────────▼─────────────────────────────────────┐
│  presentation/static_server.py（bottle）                            │
│   · /          → UI 静态资源（index.html + js/css）                  │
│   · /files/    → 知识库文件（防目录穿越）                             │
│   · /rpc       → 前端 ↔ 后端 API 桥（M0API）                         │
└──────────────────────────────┬─────────────────────────────────────┘
                               │
┌──────────────────────────────▼─────────────────────────────────────┐
│  后端分层：domain/ → range/ → storage/ → services/ → presentation/   │
└─────────────────────────────────────────────────────────────────────┘
```

## 2. 壳层（app/shell/）

| 壳 | 说明 |
|----|------|
| `pywebview.py` | 默认壳（WebView2 后端），开发态/发布态均用 |
| `pyqt6.py` | 备选壳（QtWebEngine），用于自定义无边框窗口场景 |
| `host.py` / `window_win32.py` | 窗口宿主与 Win32 控制（frameless 拖拽、系统菜单） |
| `static_server_thread.py` | 独立线程跑 bottle 静态服务器 |

启动链：`app.py → app/desktop.py（DPI 抬升 + UTF-8 stdio 兜底）→ app/shell/launch_shell() → resolve_shell_kind()`。DPI 设置必须在任何窗口创建**之前**（见 [hard-constraints.md](./hard-constraints.md)）。

## 3. 服务端（presentation/）

- `static_server.py`：bottle 应用。三路由：UI 静态资源、`/files/<kbRelPath>` 知识库文件（段级 unquote → normpath → 前缀校验防穿越）、`/rpc` 桥接 `api/ui.py` 的 M0API。
- `api/ui.py`：前后端 RPC 契约（文档加载/保存、搜索、KP 操作、图片管理、导入等）。
- `paths.py`：路径解析（KB 根、应用数据目录）。

## 4. 后端分层

| 层 | 职责 | 关键文件 |
|----|------|---------|
| `domain/` | 领域类型 | range.py（Range/snippet/line_hint）、locator |
| `range/` | snippet + line_hint 定位算法 | locator.py、constants.py |
| `storage/` | 文件系统读写 | sidecar.py、manifest.py、pending.py、atomic_yaml.py、scanner.py、markdown.py |
| `services/` | 应用服务 | document.py（文档）、kp_index/kp_resolver（KP）、search_kernel.py（检索内核）、link_*（链接）、import_engine.py（导入） |
| `presentation/` | 桥接与静态服务 | api/ui.py、static_server.py |

## 5. 前端（ui/static/app/）

| 模块 | 职责 |
|------|------|
| `parser.js` + `ast.js` | Markdown → AST 编译（`[[]]` 语法、图片属性解析） |
| `renderer.js` | AST → DOM 渲染（公式/代码/表格/图片/高亮） |
| `source-gen.js` | DOM 编辑 → 源码回写 |
| `edit-handler.js` | 块编辑交互（图片工具栏、代码/公式双击编辑、光标定位） |
| `markdown-preview.js` | 预览渲染、图片路径重写、Lightbox |
| `mapper.js` | 源码 ↔ 预览双向光标映射 |
| `bridge.js` | 后端 RPC 桥封装 |
| `app.js` | 主控制器（视图模式、tab、工具栏、图片管理、粘贴管线） |
| `graph-*.js` | 知识图谱引擎（2D d3-force / 3D three.js + Barnes-Hut octree） |
| `kp-context-menu.js` / `link-context-menu.js` | 右键菜单 |

**数据流**：`source → parser（AST）→ renderer（DOM）→ preview`；预览直接编辑（`contenteditable=plaintext-only`）→ `mapper` 回写源码 → 80ms debounce 重渲染。图片等不可编辑块为 `contenteditable=false` 原子单元。

## 6. 存储布局

```
<KB>/
  .memoria/                  # 隐藏元数据目录（文件树/文档扫描不可见）
    sidecars/<rel>/<name>.memoria.yaml   # 侧车：KP 定义、range、links、edges
    manifest.yaml            # KB 级清单（schema_version、KP 注册）
    pending.yaml             # 待建/待处理项
    images/                  # 入库图片（KB 根相对路径 .memoria/images/x.png）
    cache/                   # 检索缓存（lexical / embeddings / search_aux）
  <docs>.md                  # 正文（frontmatter + `[[]]` 链接）
```

- **侧车**：`schema_version: 1`、`file:`、`knowledge_points[]`（id/name/range{start,end:{snippet,line_hint}}/links/edges）。
- **正文 ↔ 侧车分离**：链接路由表存 frontmatter；KP 区域由文件位置定义，区域内链接归属该 KP。

## 7. 版本与构建

- 版本唯一事实源：[`__version__.py`](../../memoria/__version__.py) → pyproject dynamic attr → 构建/UI/打包全跟随。
- 发布：`packaging/build_release.cmd`（PyInstaller）→ `Package/` 目录（含 lib/、VERSION、manifest.json）。
- `Package/lib/` 必须与 `src/` 代码版本一致（硬约束，见 hard-constraints）。
