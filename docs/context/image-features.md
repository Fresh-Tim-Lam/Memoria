# 图片功能（Image Features）

> **用途**：Memoria 图片板块的功能说明与内部机制，供维护者与 AI Agent 理解、调试图片相关问题。
> **目标读者**：维护者 / AI Agent（遇到图片渲染、路径、加载问题时先读本页）。
> **关联文档**：[logging.md](../standards/logging.md)（日志规范）、`design/system-design.md`（架构）、[markdown-form-std.md](../standards/markdown-form-std.md)（`[[]]` 语法体系，图片归入正文块）。

---

## 1. 功能总览

| 模块 | 能力 | 入口 |
|------|------|------|
| 预览渲染 | `![alt](url)` → `<img>`，保留 alt，限宽缩放 | `renderer.js` `T.IMAGE` → `.m0-preview-image` |
| 路径转换 | 本地相对路径 → `/files/<relPath>` API URL | `markdown-preview.js` `rewriteLocalImagePaths` |
| 静态服务 | `/files/` 路由，8 种图片 MIME，防目录穿越 | `presentation/static_server.py` |
| Lightbox | 单击放大查看（overlay 点击关闭） | `markdown-preview.js` `attachImageLightbox` |
| 编辑交互 | 图片块不可编辑、双击进源码编辑模式、Lightbox 优先于光标映射 | `edit-handler.js` |
| 保存校验 | 只允许保存 `.md`（防二进制写坏） | `services/document.py` `save_document` |
| 诊断日志 | 服务端 `[STATIC]` + 前端 `[img-rewrite]`/`[img-debug]` | 见 §6 |

## 2. 渲染链路

```
源码 ![alt](./images/x.png)
  → app.js renderPreview: rewriteMdImagePaths(body)   // AST 解析前，源码层重写
  → parser.js: image(alt, url) 节点                    // 拿到已是服务端路径
  → renderer.js T.IMAGE: <img class="m0-preview-image" src=url alt=alt>
  → markdown-preview.js attachImageLightbox(preview)   // 挂 Lightbox
```

- **alt 保留**：`renderer.js` 直接把 `block.alt` 写入 `<img alt>`，预览无 alt 兜底时仍有语义。
- **限宽缩放**：`.m0-preview img { max-width: 35%; height: auto; border-radius: 4px }`——大图等比缩小，不撑破布局。
- **行号映射**：图片块按单行计（`app.js` 注释 `heading / paragraph / image / hr → 1 line`），参与源码↔预览行号定位。

## 3. 路径解析与转换（核心机制）

`markdown-preview.js rewriteLocalImagePaths(html)` 的正则只处理 `<img src="...">`，按前缀分三类：

| 路径形态 | 处理 |
|---------|------|
| `http(s):` / `data:` / `/` 开头 | 跳过（远程/数据/绝对路径不动） |
| 本地相对（如 `./images/x.png`） | 去 `./` → 拼当前文件目录 → 按段 `encodeURIComponent` → 拼 `apiBase + "/files/" + relPath` |

- **当前文件目录**：`app.js renderPreview` 计算 `currentFileDir`（文件相对 KB 根目录的所在目录）注入 `setCurrentFileDir(dir)`；KB 根由 `setKbRootForImages(root)` 注入（打开知识库/启动时调用）。
- **同源**：静态服务器即 UI 宿主，`apiBase` 默认空串，图片与页面同源，无跨域。
- **源码层入口**：`app.js rewriteMdImagePaths(md)` 只匹配 `![...](./相对路径)`，委托 `MP.rewriteLocalImagePaths` 后取回改写后 src——保证 AST 解析前路径已服务端化。
- **跨平台**：`\` 统一转 `/`，Windows/Unix 路径都兼容。

**服务端安全（防目录穿越）** `static_server.py _serve_kb_file`：
段级 `urllib.parse.unquote` 解码 → `os.path.normpath(join(kb, decoded))` → Windows 小写化 → `startswith(kb_norm)` 前缀校验；逃逸返回 404 并记 `[STATIC] ... 路径逃逸 ...`。

## 4. 交互设计

**单击 Lightbox（300ms 守卫）**：
- 单击 → 延迟 300ms 后创建 `.m0-lightbox-overlay` + `.m0-lightbox-image`（z-index 99999，overlay 点击关闭）
- **300ms 内二次点击 = 双击** → 取消开箱，交给 dblclick 进编辑模式——单击/双击互不吞没

**双击编辑模式**：dblclick 进入图片块编辑（`edit-handler.js`），把 `<img>` 替换为源码文本（从 `#editor` 对应行取原文 `![alt](url "title")`）供修改。

**不可编辑与焦点**：
- 图片块在 `_nonEditableSet()` 中（`edit-handler.js`）——点击时不抢焦点
- 编辑模式下 `preview mouseup` 对图片所在 `m0-src-block` 跳过同步（`skip sync (allow dblclick)`）——点击不触发光标映射跳转，让 Lightbox 接管
- **图片块不设 `contenteditable=false`**（与代码块/公式/表格不同）：避免浏览器对 img 的渲染不一致；其"不可编辑"完全由 mouseup 跳过 + dblclick 编辑模式实现

**交互优先级**：`Lightbox(单击) > 双击编辑 > 光标映射`。

## 5. 静态文件服务

- 路由：`static_server.py create_app` 拦截 `files/` 前缀 → `_serve_kb_file()`；其余走 `bottle.static_file`（UI 静态资源）
- MIME：`_IMG_MIME`（.png/.jpg/.jpeg/.gif/.svg/.webp/.bmp/.ico → `image/*`）；JS 另设 `_JS_MIME`
- KB 根同步：打开/切换/关闭知识库时 `set_kb_root`/置 None（`api/ui.py`）
- 响应：`200 + Content-Type + Content-Length`，日志含 `(MIME: ..., {fsize} bytes)`
- 文件缺失：`[STATIC] ... 文件不存在 ...` → 404 `File not found in KB`

## 6. 日志速查与故障排查

| 前缀 | 位置 | 内容 |
|------|------|------|
| `[STATIC]` | 服务端 | `set_kb_root`、提供文件（MIME+size）、路径逃逸、文件不存在 |
| `[img-rewrite]` | 前端 | 重写前后 URL（`{src} → {url} (relPath=...)`）；`SKIP: _kbRootForImages 未设置` |
| `[img-debug]` | 前端 | 加载态（`naturalWidth/complete/display/width/height/maxWidth`）；`LOAD ERROR: {src}`；`LOAD OK: {src} naturalWidth: N` |

**排查流程**（图片不显示时）：
1. 看服务端是否有 `[STATIC] 文件不存在` / 404 → 文件或路径问题
2. 看前端 `[img-rewrite]` 是否把相对路径转成了 `/files/...` → 未转说明 `_kbRootForImages`/`currentFileDir` 未注入
3. 看 `[img-debug] LOAD ERROR` → 网络/服务问题；`LOAD OK` 但 `naturalWidth: 0` → 加载失败（占位 0）
4. 检查 KB 根是否初始化（`/_kb_root_diag` 诊断路由返回 `{"kb_root": ...}`）

## 7. 设计蓝图（用户设计意图，未实现）

> 来源：2026-08-26 用户澄清。图片板块的目标**不是** HTTP 缓存，而是**图片资产管理**：用户在编辑器中选择图片后，图片被直接复制持久化到知识库内某个文件夹，并能对图片执行删除 / 插入 / 替换 / 修改（大小、对齐）。

### 7.1 图片持久化（复制入库）

- **目标流程**：编辑器内"选择图片" → 文件复制到知识库 `.memoria/images/`（KB 隐藏元数据目录内，**不进入文件树 / 文档扫描**）→ 正文写入引用 → 图片与知识库同生共死，不依赖外部路径。
- **路径约定（已定）**：正文统一写**相对 KB 根的路径** `.memoria/images/x.png`；渲染时由 `rewriteLocalImagePaths` 以 KB 根为基准解析为 `/files/.memoria/images/x.png`。✅ 2026-08-26 落地：`./` 开头 → 相对当前文件目录（旧语义兼容）；其他相对路径 → KB 根基准。
- **重名策略（建议）**：自动去重——同名自动追加序号（`x.png` → `x-1.png`），不覆盖、不报错。
- **删除语义（已确认）**：删除正文图片块**仅删引用，磁盘文件保留**，其他文档仍可引用，不误删。
- **入库 API（✅ 2026-08-26 阶段 C 落地）**：`select_image_file()`（对话框选图）/ `import_image(local_path)`（复制入库，扩展名白名单 + 重名去重）/ `list_images()`（列资产）——`DocumentService` 新增，`UIAPI` 暴露，双壳宿主（pywebview/PyQt6）均实现 `pick_image_file`。

### 7.2 图片管理能力

| 能力 | 说明 | 现状 |
|------|------|------|
| 插入 | 选择本地图片 → 复制入库 `.memoria/images/` → 正文插入引用 | ✅ 阶段 D 落地：双入口——① 编辑器格式栏"图片"按钮（仅当**文本光标位于预览区**时可点，灰=不可点，`selectionchange` 驱动实时刷新）；② 预览区右键菜单"插入图片"（主入口）；均插入到光标所在块之后。**内容去重**（2026-08-28）：相同内容图片重复插入复用已有副本（MD5 比对，不产生 `-1` 新副本） |
| 删除 | 删除正文图片块（仅删引用，文件保留） | ✅ 阶段 D 落地：预览右键"删除图片（仅删引用）"，磁盘文件保留（`list_images` 仍返回） |
| 替换 | 选中图片换一张，保留/更新引用 | ✅ 阶段 D 落地：预览右键"替换图片"，保留 alt/title 仅换 url |
| 修改大小 | 控制显示尺寸（宽度/比例） | ⏳ 阶段 E（title 参数列表 → 内联样式） |
| 修改对齐 | 居中 / 靠左 / 靠右 | ⏳ 阶段 E |
| 查看 | 单击 Lightbox 放大 | ✅ 已实现 |
| 光标定位/换行 | 图片左右侧可停靠光标，Enter 可在图片前后换行 | ✅ 2026-08-28 落地：IMAGE 块支持 offset 0（img 前）/1（img 后）AST↔DOM 映射（`mapper.js`）；方向键 Case A/B 图片停靠导航、点击图片空白按 x 坐标停靠左右侧、空行块可方向键进入（`edit-handler.js`）；Enter 在图片前→上方插空行、图片后→下方插空行，且用原始源码行回写避免 `/files/` 绝对化污染相对路径（`app.js` splitParagraph 图片分支）。harness 二次复验 PASS |
| 注册/未使用图片 | 扫描全部文档引用建立注册表；未注册（未被引用）图片可识别与清理 | ✅ 2026-08-28 落地：`list_images` 带 `referenced`/`referencedBy`；`unused_images` 列出未注册图片；`cleanup_unused_images` 清理（只删未引用资产，绝不误删）。**保存后自动清理**：`save_document` 成功后自动删除全库无引用的图片（返回 `cleanedImages`，前端 flash 提示"已清理 N 张未使用图片"） |

> 图片资产位于 `.memoria/` 内、文件树不可见 → 需要一个"图片管理视图"（浏览/插入/删除）承载以上能力，作为后续 UI 规划项。
> **实施路线**：分阶段开发方案见 [image-asset-dev-plan.md](../design/image-asset-dev-plan.md)（A 内核 title 扩展 / B 路径基准 / C 入库 API / D 插入入口 / E 属性渲染 / F 管理视图，每阶段可交互验证）。

### 7.3 属性语法（已定：链接 title 扩展，纳入 Memoria 语法体系）

- **语法**：`![alt](path "width=300,align=center")`——复用 Markdown 标准 title 参数位，为 `key=value` 逗号分隔参数列表。
- **编译内核**：✅ 2026-08-26 阶段 A 落地：lexer/parser/ast/renderer/source-gen 已解析并回写 title（`AST.image` 携带 `title` 字段，`<img title>` 渲染，编辑往返保留）。参数列表解析（`width=`/`align=`）属阶段 E 待实施。
- **体系维护**：与历代 Memoria 语法一脉相承——属性不散落在 HTML 或前端特判里，而是进编译内核；落地时同步扩展 `standards/markdown-form-std.md` 的图片节点定义，保证图片在预览中的功能定位清晰、语法可版本化演进。

## 8. 已知限制与待办

| 项 | 状态 | 说明 |
|----|------|------|
| HTTP 缓存头（Cache-Control/ETag） | **未实现** | 每次请求都重新读盘；可加缓存头让浏览器复用，减少重复加载（**非当前优先方向**，见 §7） |
| PNG 签名校验 / 损坏图 Pillow 再生成 | **未实现** | 项目记忆曾记录该能力，但当前代码库无 PIL 依赖、无校验逻辑 |
| 用户可见的加载失败提示 | **未实现** | 仅 console 日志，无 toast/占位图/失败样式；预览整体失败有 `预览失败: ...`，图片单张失败无 UI |
| 图片 `contenteditable` | 有意不设 | 由交互层保证不可编辑（见 §4），非缺陷 |
| 图片插入/持久化/删除/替换 | ✅ 阶段 C/D 已落地 | 插入/替换/删除（仅删引用）全链路通过 harness 交互验证；剩余 大小/对齐（阶段 E）与管理视图（阶段 F） |

## 9. 测试用例

`docs/example/rich-content-test/test-content.md` 含六类用例（2026-08-28 起本地相对路径用例改用 KB 根基准 `.memoria/images/`，旧 `images/` 临时目录已删除）：
- 网络大图 / 网络小图（远程路径不重写）
- 本地图 `.memoria/images/test-image.png`（KB 根相对 → `/files/.memoria/...`）
- 带标题 KB 根路径图 `.memoria/images/photomode_18092025_224424.png "测试标题"`（KB 根基准 + title 解析）
- 带标题图（title 解析；`.memoria/images/` 内的另一张，见 `_image-edit-test.md`）
- 可点击放大图（Lightbox）
- 校验点：`[img-rewrite]` 日志、`LOAD OK` 日志、Lightbox 开合、图片块双击编辑

调试用测试素材与脚本见 `docs/example/rich-content-test/`（`_harness.py`、`_image-edit-test.md`）。
