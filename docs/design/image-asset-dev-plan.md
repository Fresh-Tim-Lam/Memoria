# 图片资产管理——分阶段可交互验证开发方案

> **用途**：图片板块（资产管理：插入 / 持久化 / 删除 / 替换 / 大小 / 对齐）的分阶段开发方案。每阶段独立可交互验证，避免大改后无法定位问题。
> **目标读者**：维护者 / AI Agent（实施本方案时按阶段推进，每阶段完成必须跑通"可交互验证"再进下一阶段）。
> **关联文档**：[image-features.md](../reference/image-features.md)（功能说明与内部机制，§7 为设计蓝图）；[markdown-form-std.md](../conventions/markdown-form-std.md)（`[[]]` 语法体系，阶段 E 需扩展）；[docs-management.md](../conventions/docs-management.md)（登记）。

---

## 1. 目标与设计决策（已确认）

- **持久化**：选图 → 复制到 KB 根 `.memoria/images/`（隐藏元数据目录，不进文件树/文档扫描）→ 正文写 KB 根相对路径 `.memoria/images/x.png`。
- **属性语法**：`![alt](path "width=300,align=center")` 链接 title 扩展，编译内核解析 → `<img>` 内联样式。
- **删除**：删正文引用保留磁盘文件；`.memoria/` 文件树不可见 → 需图片管理视图。
- **重名**（建议）：自动追加序号（`x.png` → `x-1.png`），不覆盖不报错。

## 2. 现状盘点（调研结论，全部核实）

| 项 | 现状 | 影响 |
|----|------|------|
| 编译内核 title | `matchBracketLink` 只取第一个 `)`，`![alt](url "title")` 的 title 混进 url → 图片加载失败；AST 仅 `{type,alt,url}`；source-gen 回写不带 title | **阶段 A 必须修**，否则任何带 title 的图片都是坏的 |
| 行内 image | `renderInline` 无 `T.IMAGE` 分支，图片与文字同行不渲染 | 已知限制，图片需独占一行（本方案不改） |
| 路径重写 | `rewriteLocalImagePaths` 按**当前文件目录**拼路径；`.memoria/images/x.png`（KB 根基准）会拼错 → 404 | **阶段 B 调整**为 KB 根基准（`./` 开头保持旧语义） |
| 静态服务 | `/files/` 已能服务 `.memoria/` 子目录（防穿越只校验 KB 根之下） | 无需新路由；**阶段 B 顺手修** `startswith` 无路径边界缺陷（`C:\kb` 前缀可被 `C:\kb-evil` 绕过） |
| 插入入口 | 无任何"选图/插入"入口（工具栏 / 右键菜单 / 粘贴 / 拖拽均无） | **阶段 C/D** 从零建 |
| 后端文件 API | 有 create/delete/rename（rename 仅改名不移动）；**无"复制外部文件入库"** | **阶段 C** 新增 |
| 隐藏目录 | `SKIP_DIR_NAMES`（constants.py:9）+ `list_files` 跳过点开头目录 → `.memoria/images/` 天然对文件树隐藏 | 符合设计 |
| 交互验证 | `docs/example/rich-content-test/_harness.py`：bottle + /rpc 透传 + 桥注入，全部 UIAPI 可调 | **每阶段验证工具** |

## 3. 阶段划分总览

```
A 编译内核 title 扩展 ──► E 属性渲染落地（大小/对齐）
B 路径基准 + 静态服务 ──► C 后端入库 API ──► D 前端插入入口 ──► F 图片管理视图 + 收尾
```

| 阶段 | 名称 | 依赖 | 验收标准（可交互） | 状态 |
|------|------|------|------|------|
| A | 编译内核 title 扩展 | — | harness 中带 title 的图片正常显示、编辑往返不丢 title | ✅ 2026-08-26 完成 |
| B | 路径基准与静态服务加固 | — | 子目录文件中 `.memoria/images/...` 引用显示正常；逃逸请求 404 | ✅ 2026-08-26 完成 |
| C | 后端图片入库 API | — | console 调 API 选图 → 落盘 `.memoria/images/` + 返回相对路径 + 重名去重 | ✅ 2026-08-26 完成 |
| D | 前端插入入口 | C | 工具栏按钮选图 → 正文插入语法 → 预览渲染 + 可撤销 | ✅ 2026-08-26 完成 |
| E | 属性渲染落地（大小/对齐） | A | `![alt](path "width=300,align=center")` → 300px 居中；与 Lightbox/双击编辑兼容 | ✅ 2026-08-28 完成 |
| F | 图片管理视图 + 收尾 | C/D | 视图列出全部图片（含注册状态）、插入/删除（仅删引用）可操作、清理未使用图片 | ✅ 2026-08-28 完成 |

A/B 相互独立可并行；C 与 A/B 无耦合，可先做。

---

## 4. 阶段 A：编译内核 title 扩展

**目标**：让 `![alt](url "title")` 被正确解析、保存、渲染、回写（title 是阶段 E 属性语法的基础）。

**改动点**（最小改动面，已定位）：

| 文件:行 | 位置 | 改动 |
|---------|------|------|
| lexer.js:383-398 | `matchBracketLink` | 解析可选 title 段（`"..."`），返回 `{alt, url, title, fullLen}` |
| lexer.js:119-128 | token 生成 | 把 title 写入 `image_close` token value（或挂到 token 属性） |
| parser.js:92-103 / 378-383 | `parseInline` / `parseBlocks` 图片分支 | `AST.image(alt, url, title)` |
| ast.js:176-179 | `image` 工厂 | 签名加 `title`，节点结构 `{type, alt, url, title}` |
| renderer.js:84-93 | `T.IMAGE` | `img.title = block.title`（阶段 E 再扩展为 attrs） |
| source-gen.js:64-65 | `T.IMAGE` 回写 | `"![" + alt + "](" + url + " \"" + title + "\")"` |
| app.js:2446-2454 | `rewriteMdImagePaths` 正则 | 路径捕获组后加可选 `(?:\s+"[^"]*")?`，否则带 title 的相对路径会跳过重写 |

**交互验证**：
1. `python _harness.py` → 打开 `test-content.md`，临时追加一行 `![图](./images/test-image.png "测试标题")`。
2. 检查：图片显示（`LOAD OK`）、`<img title="测试标题">`、`[img-rewrite]` 成功转 `/files/...`。
3. 双击进编辑模式 → 源码应含完整 `![图](./images/test-image.png "测试标题")`；保存后再打开不丢 title。

**验收**：带/不带 title 的图片都正常；无 title 图片行为回归不变。

---

## 5. 阶段 B：路径基准与静态服务加固

**目标**：正文 `.memoria/images/x.png`（KB 根基准）正确解析；修复 `/files/` 防穿越边界缺陷。

**改动点**：
- `markdown-preview.js:538-559` `rewriteLocalImagePaths`：**分流**——`./` 开头 → 保持"当前文件目录"拼接（旧语义）；其他相对路径（如 `.memoria/images/x.png`）→ 以 KB 根为基准（`relPath = clean` 不再前置 `_currentFileDir`）。
- `static_server.py:42-72` `_serve_kb_file`：`startswith(kb_norm)` 改为 `startswith(kb_norm + os.sep)`（或 `Path.is_relative_to`），堵住 `C:\kb-evil` 前缀绕过。
- 可选：`DocumentService.set_kb_path` 初始化 `kb/.memoria/images/` 目录（阶段 C 需要）。

**交互验证**：
1. 新建 `docs/example/rich-content-test/aaa/deep.md`，正文写 `![图](../.memoria/images/x.png)`（先手工放一张测试图到 `.memoria/images/`）。
2. 打开文件 → `[img-rewrite]` 应显示 `/files/.memoria/images/x.png`，图片显示。
3. 浏览器地址栏访问 `http://127.0.0.1:8642/files/../kb-evil/secret.png`（构造逃逸）→ 应 404 并出现 `[STATIC] 路径逃逸` 日志。
4. 回归：`./images/test-image.png` 相对当前文件目录的旧写法仍正常。

**验收**：KB 根基准与旧相对路径语义共存；逃逸不可绕过。

---

## 6. 阶段 C：后端图片入库 API

**目标**：选图 → 复制持久化到 `.memoria/images/` → 返回相对路径；重名自动去重；防目录穿越。

**改动点**：
- `presentation/api/ui.py` `UIAPI` 新增：
  - `select_image()` → 调 `WindowHost` 文件对话框（限图片类型，参考 `pywebview_host.py:148` `pick_import_files`）→ 返回选中的本地路径。
  - `import_image(local_path)` → 校验扩展名（白名单 8 种）→ 复制到 `kb/.memoria/images/`，重名追加序号（`x.png`→`x-1.png`）→ 返回 `{relPath: ".memoria/images/x.png", ok: true}`。
  - `list_images()` → 列出 `.memoria/images/` 全部文件（阶段 F 用）。
  - 安全：仅接受对话框返回的本地路径；KB 根内不允许覆盖已有文档路径。
- `pywebview_host.py` 新增 `pick_image_file`（或复用 `create_file_dialog` 的 OPEN_DIALOG + 图片类型过滤）。

**交互验证**（harness console）：
```js
await memoria.api.select_image()          // 弹系统对话框选图
await memoria.api.import_image("C:/.../a.png")
// → {relPath: ".memoria/images/a.png"}
await memoria.api.import_image("C:/.../a.png")  // 再插一次
// → {relPath: ".memoria/images/a-1.png"}（重名去重）
```
检查：文件落盘 `kb/.memoria/images/`；浏览器访问 `/files/.memoria/images/a.png` 可显示。

**验收**：选图→落盘→可服务全链路通；重名不覆盖；非法扩展名拒绝。

---

## 7. 阶段 D：前端插入入口 ✅ 2026-08-26

**目标**：用户可一键插入图片，正文落正确语法。

**改动点**：
- `index.html:175` 插入入口位于 **`#editor-header` 格式栏**（`.m0-format-bar` 末尾，色▾ 之后）：`<button id="btn-insert-image" class="m0-fmt-btn" data-insert-image="1" disabled>图片</button>`，**不在**全局工具栏 `.toolbar-actions`（原工具栏按钮已移除）。
- `app.js:1487-1597` 图片插入与管理函数块：
  - `startInsertImage(insertAtLine?)`：`select_image_file` → `import_image` → `insertSourceLine(text, insertAtLine)`；alt 取文件名去扩展名；无 KB/无文档先 setStatus 提示。
  - `insertSourceLine(text, lineNum?)`：源码编辑器插入**独占行**（图片须独占一行才渲染）；定位优先级：编辑器 selection 锚点行 → lineNum 指定行 → `previewCursorSourceLine()`（预览光标所在 `.m0-src-block` 的 `data-m0-src-line`，鼠标在预览区编辑时生效）→ 最后一行；`_srcPushBefore` 入撤销栈 → 建行 DOM（`.m0-line`+`.m0-lineno`+`.m0-line-content`）→ `renumberSourceLines` → `_srcAfterEdit` → 光标定位 → `scheduleRenderSync` + `markDirty`。
  - `applyImageEditLines(lines)`：整文档重写 + 入撤销栈（替换/删除共用）。
  - `showImageContextMenu(x,y,lineNum)`：复用 `showTreeContextMenu`（`#m0-ft-context-menu`），菜单项"替换图片"/"删除图片（仅删引用）"。
  - `replaceImageAtLine(lineNum)`：选图入库 → 正则解析原行 → 保留 alt/title 换 url → `applyImageEditLines`。
  - `deleteImageAtLine(lineNum)`：splice 删行 → `applyImageEditLines`（仅删引用，磁盘文件保留）。
  - `previewHasCaret()` / `refreshImageInsertAvailability()`：按钮可用性**跟随文本光标（caret）是否位于预览区 `#preview` 内**——`disabled = !previewHasCaret()`；不依赖鼠标 hover（用户指定：灰=不可点，文本光标在预览区闪烁才可点）。
- `app.js:9461-9496` 预览区右键分支：`img.m0-preview-image` → `showImageContextMenu`（替换/删除）；**折叠光标右键** → `showForCursor(e, {onPaste, onInsertImage})` 菜单含"粘贴"/"插入图片"，`insLine` 在菜单弹出前由 `previewCursorSourceLine()` 捕获并传给 `startInsertImage`。
- `link-context-menu.js:207-235` `showForCursor` 支持 `ctx.onInsertImage` → 渲染"插入图片"菜单项（hint：选择图片并复制入库 .memoria/images）。
- `app.js:11897-11900` bindEvents 绑定按钮点击 + **`document` 级 `selectionchange` 监听**刷新可用状态（点击预览区/编辑器、方向键移动光标均触发）+ 初始禁用；`setViewMode` 视图切换后刷新。
- `app.css:3012-3017` `.m0-fmt-btn:disabled` 灰显样式（opacity .35 + not-allowed）。
- 撤销支持：插入/替换/删除均走 `_srcPushBefore`/`_srcAfterEdit`，与源码编辑共享撤销栈（Ctrl+Z/Ctrl+Y 在 `#editor` keydown 处理，app.js:7262-7270）。

**交互验证（harness + browser 自动化，全链路）**：
1. 工具栏 `.toolbar-actions` 内**无** `#btn-insert-image`；格式栏内含之且初始 disabled ✅
2. 可用性：初始灰显不可点 → 点击预览区（文本光标在预览区闪烁）按钮可点 → 光标切回源码编辑器按钮立即灰显 ✅
3. 预览光标定位插入：文本光标置于预览区后点击"图片"按钮 → 图片插入到**预览光标所在块之后**（`#line-N` 后），`![test-image-N](.memoria/images/test-image-N.png)`（重名去重递增）✅
4. 预览区**右键（光标折叠）** → `#m0-link-context-menu` 含"粘贴"/"插入图片" → 点"插入图片" → 插入到右键光标块之后 ✅
5. 图片右键回归：`#m0-ft-context-menu` 含"替换图片"/"删除图片（仅删引用）" ✅
6. 预览渲染、撤销/重做、替换、删除（仅删引用）此前已全通（见下）

**已记录的小问题（非阻塞，后续产品侧评估）**：插入成功的状态提示"图片已入库"在 `renderPreview` 末尾的 `showPreviewReport`（app.js:2608-2636）执行后约 170ms 被 `state.currentPath` 覆盖为当前文件名，用户可见层面几乎瞬间消失。属全应用通用行为（任何触发渲染的状态消息都会被覆盖），非图片模块回归；可在后续统一调整状态栏优先级。

**验收**：插入（按钮/右键双入口）/撤销/替换/删除（仅删引用）全通。

**后续修复（2026-08-26）**：
1. **图片行被旧式公式启发式误判为数学块**：`math-normalize.js:41-43` `isLegacyFormulaLine` 新增排除——`![alt](path)` 图片行不参与 legacy 公式判定（alt 含下划线如 `photomode_21072025_160332` 曾命中 `MATH_RE` 的 `_`，整行被包成 `$$...$$` → MathJax 渲染、永不产生 `<img>`）。修复后含下划线 alt 的图片正常渲染；已验证 L5/L10 无回归。
2. **插入按钮可用性由"严格预览区 hover"改为"跟随文本光标"**：用户实际使用反馈——把编辑光标放进预览区（闪烁）后，鼠标移到按钮时按钮因离开预览区已灰，点不了（严格 hover 的固有体验问题）。现改为 `selectionchange` 驱动（app.js:1580-1595 `previewHasCaret`）：**文本光标在 `#preview` 内 → 可点；否则灰**。已验证：光标在预览区 disabled=false、在编辑器 disabled=true，L5/L9/L10 图片渲染与数学块残留无回归。
3. 夹具注：`_image-edit-test.md` L31 引用 `.memoria/images/photomode_05082025_151020.png`，磁盘实际为 `photomode_05082025_151058.png`（文件缺失 → 预期 LOAD ERROR 日志，保留作文件缺失素材；如需显示可改引用）。

**后续落地（2026-08-28）：图片注册与清理机制 + 旧 images/ 目录迁移**：

1. **注册机制**（`document.py:559-653`）：
   - `_scan_image_refs()`：扫描 KB 全部 md 文档的 `![...](...)` 引用，仅注册规范化后指向 `.memoria/images/` 的引用（源码 `.memoria/images/x.png` 或 API 形式 `/files/.memoria/images/x.png`），返回 `{文件名: [引用它的文档相对路径]}`；`./images/x.png`（文档目录相对语义）与远程 URL 不注册。
   - `list_images()` 增强：每张图片带 `referenced`（是否被引用）与 `referencedBy`（引用文档列表）。
   - `unused_images()`：返回未注册（未被任何文档引用）图片列表。
   - `cleanup_unused_images(rel_paths=None)`：清理未注册图片——`rel_paths` 为空清全部；传列表则只删其中属于未注册集合的（**绝不误删已引用资产**）。API 层（`ui.py`）暴露 `unused_images` / `cleanup_unused_images`。
2. **数据清理**：`rich-content-test` 知识库清理 3 个未引用图片（`photomode_05082025_151002.png`、`photomode_05082025_151058.png`、`photomode_31072025_095110.png`）；后又合并/清理重复副本 `150952-1/-2` 与验证误删的 `151058-1`、`31072025_135333`（见第 6 点），当前剩余 5 张全部已注册。
3. **旧临时目录迁移**：`images/`（旧开发临时图片位置）已删除；`images/test-image.png` 与 `.memoria/images/test-image.png` 内容一致（MD5 相同）→ 直接删目录，3 处引用更新为正式资产：`_image-edit-test.md` L6 → `.memoria/images/test-image.png`、L11 → `/files/.memoria/images/test-image.png`；`test-content.md` L82 → `.memoria/images/test-image.png`。已验证迁移后渲染正常（L6/L11/L36 全部 LOAD OK）、`unused_images` 返回 `images:[]`、`cleanup_unused_images` 返回 `deleted:[]`。
4. 阶段 F 管理视图将复用 `list_images`（含注册状态）+ `unused_images`/`cleanup_unused_images`。
5. **导入内容去重**（`document.py:509-570`）：`import_image` 复制前先计算源图 MD5，与 `.memoria/images/` 已有图片逐一比对——存在内容相同（MD5 一致）的图片则**直接复用已有副本**（返回其 relPath，`deduped=true`），不再产生新副本；仅同名且内容不同才追加 `-1` 序号。已合并历史重复副本 `photomode_05082025_150952-1.png`（内容与 `150952.png` 相同）→ 更新 `test-content.md` 引用为 `150952.png` 并删除 `-1` 文件。验证：同一文件连续两次 `import_image` 返回相同 relPath 且 `deduped=true`，目录数量不变，渲染无回归。**注意：用户侧 `-1/-2` 副本若再次出现，多为未重启应用加载旧代码所致（旧逻辑仅按文件名重名去重）。**
6. **保存后自动清理未引用图片**（`document.py:252-288` + `app.js`）：`save_document` 成功后自动调用 `cleanup_unused_images()`——全库文档无引用的图片从 `.memoria/images/` 物理删除，返回 `cleanedImages` 清单；前端 `syncToDisk` 收到非空 `cleanedImages` 时 `showFlashInfo` 提示"已清理 N 张未使用图片"。验证：覆盖保存 `_image-edit-test.md` 仅保留一张引用 → `cleanedImages` 返回仅被该文件引用的 2 张（`151058-1`、`31072025_135333`），恢复原文后其余 5 张（被 `test-content.md` 等引用）不受影响。**副作用**：验证过程中这两张图片被物理删除且无备份，`_image-edit-test.md` 中对应引用已移除（保留 L31 `151020` 作文件缺失素材）。**风险提示**：编辑中临时移除引用（剪切/粘贴中间态）后保存会触发清理，属用户选定的策略。
7. **图片左右光标 + Enter 换行**（2026-08-28，用户反馈"图片左右侧光标无法抵达、无法换行"）：此前 IMAGE 块被 `_nonEditableSet` 整体不可编辑，`domToAst`/`astToDom` 对无 children 简单块只映射 offset 0（无法区分图片左右），`splitParagraph` 对 image 直接 return false，且 Lightbox 点击遮罩吞 selection——四层原因叠加导致光标无法停在图片两侧。修复：
   - `mapper.js`：`domToAst` 简单块边界分支（L721-726）——`domOffset>0` 返回 `{nodePath:[], offset:1}`（图片后），否则 `offset:0`（图片前）；`astToDom` 简单块分支（L818-821）——`offset>0` 用 `_rangeInContainer(blockEl, childNodes.length)` 停 img 后，否则 img 前。
   - `edit-handler.js`：新增 `isImageBlock`/`imageStopOffset`/`placeCursorInImageBlock`（L358-388）；`placeCursorInBlock` 空块 atEnd 放元素末尾；方向键 **Case A**（当前块为图片且光标已停靠）按 dir 决定"图片内换侧"或"跳到相邻可编辑块"（L732-742）、**Case B**（相邻块为图片）停靠到 `dir>0?img前:img后`（L767-771）；mouseup 点击图片块空白按点击 x 相对 img 中点停靠 img 左/右（L675-688）；`isAtBlockEdge` 空块视为边界（L505-513）使空行块可方向键进入图片停靠。
   - `app.js` `splitParagraph` 图片专用分支（L8726-8767）：Enter 在图片前 → 上方插空行、图片后 → 下方插空行（`imgCursor.nodePath` 为空数组判断）；**用 `state.doc.lines[imgRange.startLine]` 原始源码行而非 `generateBlock` 重生成**，避免 AST 绝对化 url（`/files/...`）污染相对路径。
   - **验证（harness + browser 二次复验全部 PASS）**：图片后 Enter → 下方插空行且图片行保持 `.memoria/images/` 相对路径（无 `/files/` 前缀）；空行块 ArrowRight → 光标停图片块 img 前（`domToAst={offset:0}`）；图片前 Enter → 上方插空行、图片行源码不变。Package/lib 已同步（哈希一致）。

---

## 8. 阶段 E：属性渲染落地（大小/对齐）✅ 2026-08-28

**目标**：title 参数列表 → 编译内核 attrs → `<img>` 内联样式，同步扩展语法规范。

**已落地改动**：
- `ast.js`：`parseImageAttrs(title)`（L182-193）——title 按逗号拆段，每段须匹配 `key=value`（key 为字母/数字/下划线/连字符）才按属性解析；任一段不匹配 → 整个 title 回退普通标题。`image()` 工厂携带 `attrs` 字段（`{type, alt, url, title, attrs}`）。
- `renderer.js` `T.IMAGE`（L103-127）：白名单应用——`width`/`height` 经 `_normalizeImageSize` 规范化（纯数字补 `px`，`px`/`%` 原样，非法值忽略）写 `<img>` 内联样式，且 `img.style.maxWidth = "100%"`（显式尺寸生效、防溢出，覆盖默认 `max-width:35%` 钳制）；`align=center/left/right` → 容器 `.m0-image-align-*` class；未知 key → `console.warn("[img-attrs] ...")` 忽略。
- `app.css`：`.m0-preview .m0-image-block.m0-image-align-center/left/right { text-align: ... }`。
- `edit-handler.js`：双击编辑图片提示文案更新为 `![alt](url "width=300,align=center")`。
- `conventions/markdown-form-std.md`：新增"图片节点属性规范"章节（key 白名单、语法示例、解析与容错规则、与 `[[]]` 体系关系）。
- source-gen 无需改动：attrs 存于 title 原始字符串，回写 `![alt](url "title")` 天然保留，编辑往返不丢。

**交互验证（harness + browser 两轮，全部 PASS）**：
1. 6 类用例（300px 居中 / 50% 左 / align=right / 普通 title / width=200,foo=1 / height=120）：
   - 全部图片真实加载（naturalWidth=1920，LOAD OK，无 LOAD ERROR）
   - items[0] `width=300,align=center` → rectW=300、水平居中偏移 0px
   - items[1] `width=50%,align=left` → rectW=490（=block 980/2，50% 精确生效，修复前被 35% 钳到 343）
   - items[2] `align=right` → 右缘精确贴容器右
   - items[3] `测试标题` → 无属性应用，img.title 保留
   - items[4] `width=200,foo=1` → rectW=200，`[img-attrs] 未知图片属性 key=foo` warn，不破坏渲染
   - items[5] `height=120` → rectH=120（宽按比例 213）
2. 编辑往返：源码模式确认完整 `![宽300居中](.memoria/images/... "width=300,align=center")` 保留；save_document 后重开属性不丢。
3. 无 title / 无属性图片回归不变（自然宽度、无多余 style）。
4. 期间修复测试夹具：`.memoria/images/` 中 `test-image.png`、`photomode_29072025_010313.png` 被此前 auto-cleanup 验证副作用误删（test-content.md 当时处于污染态），已将 test-content.md 两处悬空引用更新为现存图片（`photomode_21072025_160332.png`、`photomode_18092025_224424.png`）。

**验收**：大小/对齐三种形态生效且可编辑往返；无 title 图片回归不变。已达成。

---

## 9. 阶段 F：图片管理视图 + 收尾 ✅ 2026-08-28

**目标**：因 `.memoria/images/` 文件树不可见，提供独立视图管理图片资产。

**已落地改动**：
- `app.js` 新增图片管理模态（`openImageManager`，L1662-1840）：
  - 复用 `.m0-modal` 样式；工具栏含统计（`共 N 张 · 已引用 X · 未使用 Y`）、刷新、清理未使用图片按钮；网格卡片列表（缩略图 `/files/...` + 文件名 + 大小 `fmtImageSize` + 引用状态标签 `已引用 N`/`未使用` + 引用文档列表）。
  - **插入**：`insertSourceLine("![name](relPath \"width=300\")")` 插入当前文档（复用阶段 D 通道，带 width 属性）。
  - **删除（已引用）**：确认弹窗 → "仅删引用" → 从当前文档过滤该图引用行（`applyImageEditLines`，磁盘文件保留）；当前文档无引用时提示"需先在其他文档移除引用"。
  - **删除（未使用）**：确认弹窗 → "连文件删" → `cleanup_unused_images([relPath])` 物理删除。
  - **清理未使用图片**：`unused_images()` 列出 → 确认弹窗（含前 5 文件名）→ `cleanup_unused_images()` 全清 → 状态条提示删除数量。
- 入口：文件树空白右键菜单新增"图片管理…"项（L689）。
- `app.css`：图片管理模态样式（L3709-3811，网格/卡片/缩略图/标签/按钮）。

**交互验证（harness + browser 两轮，全部 PASS）**：
1. 右键打开视图：7 张卡片（6 已引用 + 1 未使用探测图），stat 正确，缩略图全部加载，`已引用 N` 标签与引用文档一致。
2. 插入：编辑器出现 `![ai_neon_street](.memoria/images/ai_neon_street.png "width=300")`。
3. 删除-已引用：确认弹窗"仅删引用" → 当前文档引用消失、磁盘文件保留、引用计数刷新。
4. 清理未使用（完整确认流程）：确认弹窗显示 1 张 → "清理" → 列表刷新 6 张、磁盘文件删除、toast"已清理 1 张未使用图片"，无 JS 异常。
5. 已知交互（非缺陷）："仅删引用"若触发保存，会连带触发"保存后自动清理"删除其他未引用图（用户选定策略，见 L167）；验证中探测图曾因此被提前清理。

**验收**：管理视图全功能可用；删除默认安全（已引用图只删引用不删文件）。已达成。

**交互优化（2026-08-28 二次，用户指定交互方案）**：Lightbox 改双击触发；单击图片直接进入编辑工具栏；对齐/大小/管理入口全部移入块编辑工具栏（`#block-edit-bar`）。

改动点：
- `markdown-preview.js` `attachImageLightbox`：移除"单击延迟 300ms 开箱"旧逻辑，改为 `img` `dblclick` 直接建 `.m0-lightbox-overlay` + 大图（overlay 点击关闭）。`e.preventDefault()` 不阻止冒泡，让 edit-handler 的 dblclick 分支可先退编辑再放大。
- `edit-handler.js`：
  - `_BLOCK_TOOLS.image.tools` 返回工具栏 HTML：**对齐按钮**（左/中/右，`data-align`）+ **大小滑条**（`#img-size-slider`，50–800 step10）+ 当前值显示（`#img-size-val`）+ **图片管理按钮**（`#img-mgr-btn`）。
  - `enterBlockEditMode` 图片专用分支：**保留 `<img>` 显示**（不再替换为源码文本），`EH.blockEditMode = {blockType:"image", srcStart, originalContent, imgEl, imgAttrs}`；渲染工具栏 + `_initImageTools()` + 块加 `m0-block-editing`（虚线框高亮）。
  - `parseImageAttrsFromLine(line)`：正则提取 title 参数列表，拆出 width/height/align 初始化工具栏状态。
  - `_initImageTools()`：对齐按钮点击（active 高亮 → `dispatchImageAttr({align})`）；滑条 `input` 实时改 `imgEl.style.width`（`maxWidth=100%` 防溢出）+ 更新数值显示、`change` 提交 `dispatchImageAttr({width})`；管理按钮派发 `memoria:open-image-manager`。
  - `dispatchImageAttr(attrs)`：**必须在 `document` 上派发** `CustomEvent("memoria:image-attr", {detail:{srcLine, attrs}})`（app.js 监听 document）。
  - `exitBlockEditMode` 图片分支：清临时内联样式、移除高亮、恢复工具栏（**无文本写回**）。
  - 新增 preview `click` 监听：编辑模式 + 点击 `.m0-image-block` → `enterBlockEditMode`（单击进编辑）；dblclick 图片块 → 先 `exitBlockEditMode` 再交由 Lightbox 放大；dblclick 早退条件改为 `blockType !== "image"`（否则图片退出编辑不可达）。
  - 新增 `EH.reenterImageEdit(srcLine)`：属性写回后按 `data-m0-src-line` 重进编辑。
- `app.js`：
  - `updateImageAttrsLine(line, attrs)`：正则提取 title 参数列表，width/align 已存在则原位替换、不存在则追加，返回新源码行。
  - `memoria:image-attr` 监听：写回 `lines[srcLine-1]` → `applyImageEditLines(lines)`（入撤销栈）→ `setTimeout` 调 `EH.reenterImageEdit(srcLine)` 重进编辑（写回后渲染完成前不丢编辑态）。
  - `memoria:open-image-manager` 监听 → `openImageManager()`。
- `app.css`：`.m0-block-editing.m0-image-block img` 虚线 outline、`.m0-img-align-btn.active` 高亮、`.m0-img-size-slider`（96px accent-color）、`.m0-img-size-val`。

**交互验证（browser，8/9 PASS）**：单击进编辑（label=编辑图片、activeAlign=center、blockEditMode 含 imgAttrs）✅；左对齐（源码 `align=left` + 预览 `m0-image-align-left` + 工具栏保持）✅；大小滑条 width=200（源码 `width=200` + slider=200 + img 内联 200px；唯一 FAIL 为"渲染 rect≈200"——视口仅 484px 下 `max-width:100%` 把图压到 109px，环境布局限制非代码缺陷）✅；双击放大（Lightbox 出现 + 编辑态退出 + 工具栏隐藏）✅；图片管理入口（模态打开）✅；点空白退出编辑 ✅；无 JS 异常 ✅。

**坑记录**：事件派发 window/document 不匹配——`dispatchImageAttr`/管理入口最初用 `window.dispatchEvent`，而 app.js 在 `document` 上监听，window 派发的事件**不会传播到 document 监听器**，对齐/大小/管理 3 功能全部失效；统一改 `document.dispatchEvent` 后修复。

---

## 10. 验证工具与通用注意事项

- **harness**：`cd docs/example/rich-content-test && python _harness.py` → `http://127.0.0.1:8642/`。注意 `initKb` 会切到 remembered KB——需先 `await memoria.api.set_kb_path(r"d:\AAA_Jupyter\Memoria\docs\example\rich-content-test")` 再刷新。
- **编码**：Windows 管道 stdout 默认 cp1252，Python 侧中文日志（如 `[STATIC] ... 设为 ...`）会 `UnicodeEncodeError` 崩溃。`_harness.py` 开头已加 `sys.stdout/stderr.reconfigure(encoding="utf-8")`；`static_server.py` 统一走容错 `_log()`（`print` 包 `try/except (UnicodeEncodeError, OSError)`），打包态窗口应用 stdout 为 None 也不会炸。
- **开发态**：`python -m memoria` 直接跑，`[img-rewrite]`/`[img-debug]`/`[STATIC]` 三段日志闭环排查。
- **每次改动后**：`docs/reference/image-features.md` §7 设计蓝图标注阶段状态；`markdown-form-std.md`（阶段 E）登记语法。
- **回归重点**：无 title / 无属性图片、相对路径旧写法、Lightbox、双击编辑、源码↔预览往返。

## 11. 风险与开放问题

| 风险/问题 | 说明 | 应对 |
|-----------|------|------|
| title 解析改动面广（lexer/parser/ast/renderer/source-gen 7 处） | 牵一发动全身 | 阶段 A 用最小改动 + 全回归用例守护 |
| `rewriteLocalImagePaths` 分流策略 | `./` 与裸路径语义混用可能混乱 | 文档明确语义；旧 KB 图片若用 `./images/...` 不受影响 |
| 图片管理视图的"使用计数" | 需扫描全库 | 复用 `scan_wikilinks` 同层扫描逻辑，仅统计图片语法 |
| `.memoria/images/` 与知识库导出/备份 | `.memoria` 是元数据根，导出静态 HTML 时应含图片 | 阶段 F 收尾时确认导出链路 |
| symlink/junction 越界 | `_serve_kb_file` 不解析链接 | 低概率，阶段 B 评估是否 `realpath` 校验 |
