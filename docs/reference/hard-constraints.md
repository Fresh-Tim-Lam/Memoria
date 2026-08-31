# 硬约束（Hard Constraints）

> **用途**：沉淀本项目**不可违反的既定事实**——来自踩坑修复的教训与明确的设计决策。任何改动若与之冲突，必须先与用户确认。
> **目标读者**：维护者 / AI Agent（每次改动前快速扫一遍与本区域相关的条目）。
> **关联文档**：[glossary.md](./glossary.md)（术语）；[architecture.md](./architecture.md)（架构）；[image-features.md](./image-features.md)（图片细节）。

---

## 1. 运行与平台

- **DPI**：任何窗口创建前必须抬升进程 DPI 感知（desktop.py `_set_dpi_awareness`），否则高缩放下系统对话框（文件夹选择等）满屏。
- **Windows 编码**：frozen/windowed 下 stdout/stderr 为 cp1252，直接 print 中文崩溃；一律走容错流（`_SafeStream`）/ `_log()` 容错 helper，harness 启动时 reconfigure 为 UTF-8。
- **QWebEngineView**（pyqt6 壳）必须 `PreventContextMenu`，避免与前端自定义右键菜单冲突。

## 2. 编辑与渲染

- **预览缓存铁律**：任何本地修改 `state.doc.body` 的路径必须同步 `state.doc.preview_body = null`，否则预览永远渲染旧缓存（表现为"源码有反应、预览要刷新"）。
- **渲染重入**：`renderPreview` 有 `_renderingPreview` 守卫；渲染中被跳过的新请求必须置 `_renderPending` 并在完成后续跑，否则连续编辑时预览停在旧内容。
- **源码是唯一编辑入口**：预览是渲染视图 + 光标映射；预览可 `contenteditable="plaintext-only"` 直改，但非文本块（公式/代码/表格/图片/SVG/Mermaid）必须 `contenteditable=false`。
- **方向键跳过不可编辑块**：光标遇 CODE/MATH/MERMAID/TABLE/FRONTMATTER 整体跳到下一可编辑块（原子单元）。
- **视图切换/分栏**：位置锚定用 `#editor-pane`/`#preview-pane`（滚动容器）+ `getBoundingClientRect()`/`scrollTop` 计算，不用 `scrollIntoView`；分栏滚动双向同步须加锁防死循环。
- **行内数学** `$...$` 不得跨行；块级用 `$$...$$`（独立行、无尾随空格）。`wrapBlockMath` 必须 HTML 转义 `& < >`；`\text{}` 内容用 `\ ` 转义下划线。
- **前端事件派发**：全局自定义事件（如 `memoria:image-attr`）必须用 `document.dispatchEvent`（window 事件不传播到 document 监听器）。

## 3. 图片

- **单击编辑 / 双击放大**：单击图片进编辑工具栏（保留 `<img>` 显示）；双击 Lightbox 放大；交互优先级 `单击编辑 > 双击 Lightbox > 光标映射`。
- **属性写回时序**：`memoria:image-attr` 处理器必须 `async` 且 `await applyImageEditLines(...)` **渲染完成后**再 `reenterImageEdit`（detached DOM bug 教训——setTimeout(0) 会抓到旧 DOM，后续操作全失效）。
- **退出编辑恢复而非删除**：图片编辑退出时恢复进入时记录的 `imgOrigStyle`，不能无条件删 width/max-width（否则写回值被清、退回 35% 钳制）。
- **入库路径**：图片复制到 KB 根 `.memoria/images/`，正文写 KB 根相对路径；重名追加序号（`x.png` → `x-1.png`），内容去重（MD5）优先复用；**永不覆盖**。
- **保存自动清理**：`save_document` 成功后清理全库未引用图片（物理删除）；临时移除引用再保存即删资产——已接受的取舍。
- **路径重写**：本地相对图片路径在 AST 解析前由 `rewriteLocalImagePaths` 改写为 `/files/...` API URL；Enter 前后处理图片行必须用原始 source line（不能用 generateBlock，否则 `/files/` 绝对化污染相对路径）。
- **静态服务安全**：`/files/` 路由段级 unquote → normpath → 小写化 → KB 根前缀校验，逃逸 404。

## 4. 图谱

- **边模型**：全部关系统一为 `edges[]`（type: contain/reference/extend）；链接派生边与纯边分离；多目标路由表存 frontmatter。
- **Contain 边**：只由**同一文件内**标题层级生成，不跨文件；可用 `no_build: true` 抑制而非删除。
- **节点不受斥力**：力模拟只用弹簧力 + 中心引力 + 碰撞箱（soft constraint `(r-d)/d*strength`，预测量下一帧位置，dx 微调防除零）；节点永不锁定。
- **高亮语义**：主节点高亮只影响直接出边目标（一层）；环色保留；跳转用 `highlightName` 精确匹配标题文本而非行号近似。
- **拖动保位**：2D 拖拽结束不得用未更新的 `d.x/d.y` 覆盖 `fx/fy`；拖拽中 `alphaTarget(0.3)` 保活模拟。
- **3D 兜底**：2D 节点 >1000 时用 3D WebGL + Barnes-Hut octree（O(n log n)）。

## 5. 存储与检索

- **虚链悬空**：`[[unknown-id]]` 必须保持悬空，禁止自动创建空文件；`[[id|text]]` 保留原显示文本。
- **唯一映射**：一个 id 全局唯一映射到一个文件，避免歧义；文件名即身份（frontmatter `file id` 字段已废弃）。
- **最小单元**：KP 是概念最小单元；文件是容器（可含多 KP）；KP 区域由文件位置定义。
- **检索两级结构**：文件级初筛 + 概念级精排；跳转以概念 id 为键。
- **渲染/检索缓存**：`.memoria/cache/`（lexical/embeddings/search_aux）可重建，不得手工编辑。

## 6. 构建与版本

- **版本单一入口**：只改 `src/memoria/__version__.py`；pyproject 为 dynamic attr，**禁止**手改 pyproject 版本号、禁止任何其他硬编码。
- **Package/lib 同步**：`Package/lib/` 必须与 `src/` 保持同版本代码，改动前端/后端后发布前必须重新构建同步。
- **构建唯一入口**：`packaging/build_release.cmd`（PyInstaller）；`packaging/` 是唯一受支持的构建/运行发布态方式。

## 7. 协作与 UI

- **色板**：`.m0-hl-colors`/`.m0-fc-colors` 必须水平单行（nowrap + max-width:360px + overflow-x:auto），禁止换行。
- **取色器**：必须用应用内弹层（`m0-color-picker-mask`，z-index 20000），**禁止**原生 `<input type=color>`（pywebview 下系统对话框不可用）；面板须含确定/取消；打开时不要自动聚焦 hex 输入框。
- **自定义色块**：删除走右键菜单，点菜单项才删；点外部/Esc 只关菜单；内置预设色不可删。
- **跨块选区**：`_commitMultiStyle` 必须容忍空行块作为选区起点/终点（空块跳过 splitInlineAt）。
- **导航**：←/→ 栈空时必须禁用；文件树选中文件只更新高亮、不整体重渲染（保持展开态）；tab 内滚动位置按视图/面板保存恢复。
