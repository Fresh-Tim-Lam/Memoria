# 预览渲染：支持的格式与样式（Preview Formats & Styles）

> **用途**：Memoria 主预览区（`#preview`）对源正文支持哪些书写格式、各自渲染成什么样子、有哪些交互与边界。给内容生产者（写文档的人 / 生成正文的 Agent）与排查渲染问题的维护者提供**准确的当前实现说明**。
> **目标读者**：知识库内容生产者（含 Agent）· 维护者（排查预览渲染问题时先读本页）。
> **关联文档**：[markdown-form-std.md](../conventions/markdown-form-std.md)（`[[]]` 语法体系与 sidecar 存储契约）；[image-features.md](./image-features.md)（图片功能机制）；[architecture.md](./architecture.md)（前端模块与数据流）；[glossary.md](./glossary.md)（术语）。
> **状态**：生效中。核验于 2026-09-01，与 `ui/static/app/` 当前源码一致。源码行号随实现演进可能漂移，以行为描述为准。
> **提示词关联**：程序内 Agent 整理提示词 `resources/agent-prompts/organize.zh-CN.md` §7「正文书写格式」要点以本页为权威源；渲染行为变更后若与要点失配，请同步该提示词（防双份漂移）。

---

## 1. 总览

- **主预览走 AST 渲染管线**，不是通用 Markdown 库：源码正文 → 图片路径重写（`app.js rewriteMdImagePaths`）→ `lexer.js` 词法 → `parser.js` 块/行内 AST → `renderer.js` AST→DOM（每块一个 `. -src-block`）→ 行号打标（`stampBlockLines`）→ 后处理（Mermaid、图片 Lightbox、MathJax 排版、链接解析）。
- **`markdown-preview.js`（marked / GFM 管线）在主预览中只被借用**三样能力：本地图片路径重写、Mermaid 渲染、图片 Lightbox。它自己的 `renderHtml` 只用于知识点范围预览的"Markdown 模式"（辅助面板），两者行为差异已在文中标注。
- 主容器：`#preview`，类 `-preview markdown-body`（index.html）；内部内容容器 `. -preview-content`。
- 编辑态（打开"编辑"开关）时 `#preview` 为 `contenteditable`，可直接在预览改正文；只读态仅供浏览（链接可点，右键无编辑菜单）。
- **Frontmatter、代码、公式、Mermaid、表格、图片块无论编辑态与否都不可直接编辑**（内部 `contenteditable=false`）；编辑态下双击这些块进入对应"块编辑"面板，见 §6。

## 2. 块级书写格式与渲染效果

| 源码写法 | 预览渲染 | 说明 |
|---|---|---|
| 空行 | `. -blank-block`（内含 `<br>`） | 块间纵向间距的唯一来源 |
| `# …` ～ `###### …` | `h1`～`h6`（类 `-src-block`） | 空标题补占位 |
| 连续普通行 | `p` | 空段补占位 |
| ``` ````lang`…```` ` 或 `~~~lang…~~~` | `pre`（`. -code-block`）＋`code.language-<lang>` | **纯文本，无语法高亮**；代码内 `$` 不排版（MathJax 跳过 pre/code） |
| 独占行 `$$`…`$$` | MathJax 块级公式 | 文本按 `$$公式$$` 排版 |
| `![alt](url "title")` 独立行 | `. -image-block`：`img`＋下方 `. -image-caption`（显示 alt） | 存储位置与路径写法见 §4.4，属性见 §4.3；默认限宽 35%，见 §5 |
| `---` / `***` / `___`（≥3 个） | `hr` | |
| `> …` 连续行 | `blockquote`（内层为普通 `p`） | |
| `- `/`* `/`+ `/`1. `…` | `ul`/`ol` | 松散列表；有序/无序切换视为新块 |
| 含表头行＋分隔行的 `|` 表格 | `table`（`. -table`） | th/td 纯文本 |
| ``` ````mermaid`…```` ` | Mermaid 图（`. -mermaid-container`，svg 居中） | 语法错误显示 `. -mermaid-error` 红框 |
| 文档首部 `---` YAML 块 | `pre` 原文显示 | **不隐藏**，以代码块形式可见 |

**标准 Markdown 的 HTML 直通不可用**：正文里的原始 HTML 标签按字面文本显示，不生成 DOM。**裸 URL 不会自动成链**（需 `[text](url)` 或 `[[…]]`）。

## 3. 行内书写格式

| 写法 | 渲染 | 备注 |
|---|---|---|
| `**加粗**` / `__加粗__` | `<strong>` | `***粗斜体***` 也支持 |
| `*斜体*` / `_斜体_` | `<em>` | |
| `~~删除~~` | `<del>` | |
| `` `行内代码` `` | `<code>` | |
| `\x` | 转义字面字符 | |
| `$…$` | MathJax 行内公式（`. -math`） | **只匹配单行**，不能跨行；多行用块级 `$$` |
| `[text](url)` | `<a>`（可点击，跳转新窗口/外链） | |
| `[[目标]]` 或 `[[目标\|显示文本]]` | `. -wikilink`（知识点链接） | 语法见 §4.1 |
| `[[\…\|文本]]` | 字样式命令 | 语法见 §4.2 |

## 4. Memoria 扩展语法

### 4.1 知识点链接（无 `\` 前缀）

| 语法 | 含义 |
|---|---|
| `[[kp-id]]` | 链接到知识点 `kp-id` |
| `[[kp-id\|显示文本]]` | 链接＋自定义显示文本 |

- 链接渲染后按绑定状态三态着色：已绑定（`-link-resolved`，主题色实线下划线）/ 未绑定（`-link-broken`，灰、不可点，点击弹链接编辑器）/ 待绑定提议（`-link-pending`，虚线下划线）。
- **主预览中 `#type` 后缀不会被拆分**：`[[kp#edge\|文本]]` 整个作为目标参与解析，不产生边类型小标签（与辅助 marked 面板不同）。
- 悬停时联动图谱高亮对应节点；点击跳转目标文件/定位；右键弹链接菜单。

### 4.2 字样式命令（`[[\` 前缀；`]]` 收尾，不嵌套）

| 写法 | 渲染效果 |
|---|---|
| `[[\h\|文本]]` | 高亮，默认黄底 `#fff3cd` |
| `[[\h:bg\|文本]]`、`[[\h:bg:fg\|文本]]` | 指定底色/前景色 |
| `[[\c:color\|文本]]` | 字体颜色 |
| `[[\s:size\|文本]]` | 字号（size 为 CSS 值，如 `20px`、`1.2em`） |
| `[[\b\|文本]]` / `[[\i\|文本]]` | 粗体 / 斜体 |
| `[[\u\|文本]]` / `[[\sup\|文本]]` / `[[\sub\|文本]]` | 下划线 / 上标 / 下标 |

- 命令内部**不嵌套**字样式命令；要叠加效果用 Markdown 语法（如 `[[\h:green\|**加粗**]]`）。`]]` 按行内第一个 `]]` 收尾。
- **高亮底色名**（bg）：`yellow`(默认 `#fff3cd`)、`green`、`red`、`blue`、`orange`。**前景/字色名**（fg/color）：`red`、`green`、`blue`、`orange`、`yellow`、`purple`、`gray`。命名色与 `#RRGGBB`（及任意 CSS 颜色名）均可直通。
- 渲染方式：高亮为 `span.-hl`（inline 底色 + 已知色名加 `. -hl-<name>` fallback 类）；字色为 inline `style.color`。
- 参数段最多两段（`bg:fg`），与 `markdown-form-std.md` 描述的 `id` 参数 / `<mark>` 类渲染**不一致**——该契约描述的是辅助 marked 管线的能力。主预览的带名高亮记录仍存 sidecar `highlights[]`，但正文预览不再按 `data-hl-id` 走 `<mark>` 分支。

### 4.3 图片属性（title 位 `key=value` 逗号列表）

```
![说明文字](url "width=300,align=center")
```

| key | 取值 | 渲染效果 |
|---|---|---|
| `width` / `height` | 数字（px）或带单位（`300px`/`50%`） | img 内联尺寸；一旦设显式尺寸，`max-width` 放宽到 100%（解除默认 35% 钳制） |
| `align` | `left`/`center`/`right` | 图片块容器对齐（`. -image-align-*`） |
| `name-size` | 尺寸值 | 下方名称（alt）字号 |
| `name` | `hide` | 隐藏下方名称 |

未知 key 忽略并 `console.warn("[img-attrs] …")`，不破坏渲染。

### 4.4 图片存储位置与路径写法

**存储位置约定**

- 知识库内图片统一放入**知识库根的隐藏目录 `.memoria/images/`**（该目录不在文件树 / 文档扫描范围，可在「图片管理」视图中浏览、插入、清理）。
- 编辑器「插入图片 / 替换图片」会把所选本地图**自动复制入库**到 `.memoria/images/`（MD5 去重，正文只写引用）。
- 删除正文图片块**仅删引用**，磁盘文件保留（其他文档可能仍在引用）。

**正文里的路径写法**（主预览 `app.js rewriteMdImagePaths` → `markdown-preview.js rewriteLocalImagePaths`）

| 写法 | 含义 | 示例 |
|---|---|---|
| `https://…` / `data:…` / `/…` 开头 | 原样不动（远程 / 数据 / 绝对路径） | `![图](https://example.com/a.png)` |
| `.memoria/images/x.png`（不以 `./` 开头） | **推荐新约定**：相对**知识库根** | `![结构图](.memoria/images/arch.png)` → 渲染为 `/files/.memoria/images/arch.png` |
| `./x.png`（以 `./` 开头） | 旧语义兼容：相对**当前文件所在目录** | 文件 `sub/a.md` 内 `![图](./img/x.png)` → 指向 `sub/img/x.png` |
| `../…` / 含 `..` 上跳 | **非法**：逃出知识库根，静态服务判路径逃逸 → 404 | `![图](../.memoria/images/x.png)` → 应写 `.memoria/images/x.png` |
| 路径含空格 / 中文 | 用尖括号 `<…>` 包裹（编辑器插入图片默认写成该形式） | `![图](<.memoria/images/屏幕截图 2026.png>)` |

- 相对路径解析基准只有两种：无 `./` → 知识库根；有 `./` → 当前文件所在目录。**两种基准都不接受 `..` 上跳**：引用 KB 根 `.memoria/images/` 的资产时，不因文件位于子目录而推导 `../.memoria/…`，一律直接写无前缀的 `.memoria/images/…`（KB 根相对与文件深度无关）。
- 相对路径统一转成 `/files/<编码路径>` 再加载；`\` 一律按 `/` 处理，路径段自动做 URL 编码。
- 显示属性放在 title 位，语法见 §4.3：`![alt](url "width=300,align=center")`。

## 5. 样式与主题

- **字号**：预览基础字号由 CSS 变量 `--preview-font-size` 控制，默认 `14px`；“设置 → 显示 → 文字”滑块（12–28px）同时设置预览（`--preview-font-size`）与源码编辑器（`--editor-font-size`）。整体界面缩放由“缩放比例”控制根字号（rem 化布局），与文字字号独立。
- **排版**：`. -preview` 内联 `padding`、`line-height 1.6`；标题比例来自 `markdown-body`：`h1 1.625rem`＋下边框、`h2 1.25rem`、`h3 1rem`；块级 `p/h1–h6/ol/ul/pre/hr` margin 归零；引用左侧 3px 主题色边框。
- **代码**：行内 `<code>` 与块级 `<pre>` 均为主题背景色（`.markdown-body`），无语法高亮配色。
- **表格**：`border-collapse`、宽 100%、th/td 1px 边框、表头主题浅底。
- **链接态**：见 §4.1；图谱联动焦点有紫色高亮环。
- **图片**：默认 `max-width: 35%`（大图等比缩小不撑破布局）、圆角；下方 caption 灰字。
- **公式**：MathJax 容器 `max-width 100%`、横向可滚动、不可选中（避免误改）。
- **Mermaid**：容器浅底、居中、圆角、svg 限宽；失败显示红框错误提示。
- **Lightbox**：双击图片全屏放大，黑色半透明遮罩，点遮罩关闭。
- **选区覆盖**：行内公式等不可编辑元素被选中时，JS 补画蓝色高亮框（`. -math.-sel-covered`）。
- **知识点定位**：KP 范围带（`. -preview-range-band`，半透明蓝带，错误为红）；源码↔预览同步光标（`. -preview-cursor` / `. -sync-cursor`）；预览拖选整行范围（`. -src-block.is-drag-select`）。

## 6. 交互行为

| 场景 | 行为 |
|---|---|
| 单击链接 | 跳转目标文件/定位；broken 链弹链接编辑器；多目标弹选择器 |
| 悬停链接 | 图谱联动高亮节点 |
| 右键链接 | 链接菜单（编辑/删除/加链） |
| 单击图片（编辑态） | 进入图片编辑工具栏（对齐/尺寸/名称字号/名称显隐/图片管理） |
| 双击图片 | 全屏 Lightbox 放大（点击遮罩关闭） |
| 双击代码块（编辑态） | “编辑代码块”面板，语言下拉（js/python/bash/json/html/css/sql/mermaid） |
| 双击 Mermaid（编辑态） | “编辑思维导图”，类型下拉（graph TD / sequenceDiagram / classDiagram / stateDiagram-v2 / erDiagram / gantt） |
| 双击公式/行内公式（编辑态） | 编辑数学公式面板（含常用符号按钮） |
| 双击表格（编辑态） | 编辑表格（加行/加列） |
| 点击正文（编辑态） | 光标同步到源码对应行（分栏/源码视图）；不可编辑块不映射，保证双击可用 |
| 只读态 | 右键无编辑菜单；单击不同步光标；“编辑模式关闭”时按 ↑/↓ 滚动预览（滚轮效果） |

## 7. 已知边界与注意事项

1. **代码块无语法高亮**；`frontmatter` 原文以 `pre` 显示（不隐藏）。
2. **任务列表**（`- [ ]`）：主预览按普通列表文本渲染，**无勾选框**。
3. 图片默认仅显示到 35% 宽——若显式给了 `width`/`height` 则放宽到 100%（防溢出）。嫌图太小先查是否有 `width` 属性。
4. 正文改动后预览取后端 `preview_body`（带缓存）；涉及正文的写入后须让后端失效 `preview_body`（本地编辑、粘贴、导入、撤销等已统一处理），否则预览不更新。
5. 主预览的 `[[…]]` 不支持 `#type` 拆分与 marked 管线的 `<mark>`/`id` 高亮分支（§4.2）；跨管线行为不一致时以主预览为准。
6. 代码调试日志（`[img-rewrite]`/`[img-debug]`）与 `console.warn("[img-attrs] …")` 当前仍在输出，非故障。
7. `markdown-form-std.md` 为 `[[]]` 语法**契约**（含 sidecar 存储），本文档描述**主预览实际渲染**；两者冲突处（如高亮 id 参数）以本页为准。
