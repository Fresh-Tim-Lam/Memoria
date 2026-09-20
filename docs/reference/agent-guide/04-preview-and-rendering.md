# 04 · 预览与渲染

> **用途**：记录预览区「三视图怎么切、渲染管线各层边界、渲染后 DOM 长什么样、KP 范围高亮的两种语义、渲染失败怎么提示」，供集成方与后续 Agent 对齐实现；**渲染语法**（`[[\h]]`/`[[\c]]`/图片属性/公式/表格写法等）以 [preview-formats.md](../preview-formats.md) 为权威，本篇只写**渲染结果与交互**。
> **目标读者**：在 Memoria 之上做集成/移植的 Agent 与人；给 Memoria 前端写改动的人。
> **关联文档**：[README.md](./README.md)（维护约定）、[preview-formats.md](../preview-formats.md)（**语法权威**）、[03-editor-and-formatting.md](./03-editor-and-formatting.md)（编辑器与格式工具）、[architecture.md](../architecture.md)（分层与数据流）、[i18n-inventory.md](../i18n-inventory.md)。
> **状态**：生效中，2026-09-15。

---

## 1. 区域概览

```
.-view-toggle                                   （index.html:189-193）
└─ .-view-btn[data-view=source|preview|split]

#editor-split                                   （index.html:199；class 由 JS 切换，app.js:1601-1603）
├─ #editor-pane.-pane  > #editor.-editor        （源码视图容器，滚动容器）
└─ #preview-pane.-pane > #preview.-preview.markdown-body
   ├─ .-preview-content                         （renderer 产出的根容器，renderer.js:51-52）
   │  └─ .-src-block × N                        （每个 AST block 一个，带 data--block-index / data--src-line）
   └─ #-preview-range-band                      （KP 范围高亮条，按需创建/移除，app.js:11179-11186）

#preview-status                                 （index.html:198；渲染告警条，在 #editor-header 下方）
```

三态显隐由 `#editor-split` 上的 class 决定：`view-source` 隐藏 `#preview-pane`、`view-preview` 隐藏 `#editor-pane`、`view-split` 两者并排且中间 1px 分隔线（`app.css:3425`-`3459`）。

## 2. 三视图切换

| 项 | 现状 | 锚点 |
|---|---|---|
| 状态源 | `state.viewMode`，初值 `localStorage["-view"] \|\| "source"` | `app.js:20` |
| 切换入口 | `.-view-btn` 的 click → `setViewMode(btn.dataset.view)`；持久化也写 `localStorage["-view"]` | `app.js:12411`-`12413`、`1571`-`1573` |
| 切换动作 | ① 从源码编辑器 `collectEditorBody()` 收回正文、清 `preview_body` 缓存；② `renderEditor` + `await renderPreview`；③ 若 `_dirty` 立即 `syncToDisk()` | `app.js:1575`-`1595` |
| 位置锚点 | 切换前记录 `anchorLine = _getViewTopSrcLine(prevMode)`（视图顶部对应的**源码行号**） | `app.js:1596`-`1600`、`1632`-`1656` |
| 位置恢复 | 目标为 `split` → 两侧都 `_scrollToSrcLine(anchor)`；否则先试 `_scrollToSrcLine(mode, anchor)`，成功即跳过，失败才回退按 `scrollTop` 数值恢复 | `app.js:1613`-`1628`、`1659`-`1687`、`1689`-`1715` |
| 分栏滚动同步 | `#editor-pane` / `#preview-pane` 的 `scroll` 双向联动，用 `splitSyncLock` + `requestAnimationFrame` 防回环；**无条件启用** | `app.js:1517`-`1540`、`12416`-`12417` |
| **「分栏自动定位」配置项** | **没有**。设置四页（显示/搜索/检查/图谱）与 `ui-settings.json` 中都没有分栏同步/自动定位开关；`splitSyncLock` 也非持久化状态 | `display-settings.js:9`-`20`、`241`-`251`；`search-settings.js`/`check-settings.js` 无相关键（grep `split` 仅命中 `app.js:1518`-`1537`） |
| 源码↔预览光标互指 | 仅分栏下生效：源码光标 → 预览块 `.-preview-cursor`；预览光标 → 源码行 `.-sync-cursor` 假光标 | `edit-handler.js:192`-`206`、`293`-`302` |

## 3. 渲染管线（各层职责）

| 层 | 一句话职责 | 锚点 |
|---|---|---|
| 前置归一（可选模块） | `MemoriaMathNormalize.normalize` 先做公式/定界符归一；模块缺失时原样透传 | `markdown-preview.js:44`-`49`；`math-normalize.js:4` |
| 图片路径重写 | 在解析前把相对图片路径改写成 `/files/...` 编码路径（裸 URL 与 `<...>` 尖括号形式都覆盖） | `app.js:2000`-`2016`、`2018`-`2026` |
| `lexer.js` | 单行源码 → Token 数组（行首标记、加粗/斜体/代码/公式/链接/图片/`[[…]]` 等），Token 带 `srcStart/srcEnd` 供位置映射 | `lexer.js:50`-`56`、`349`-`414` |
| `parser.js` | Token[]（按行）→ AST：`parseInline` 处理行内配对，`parseBlocks` 处理块级（标题/列表/引用/表格/代码块/公式/图片），`parse/parseRange` 是入口；块经 `emit()` 落盘源码行区间 | `parser.js:39`、`316`-`499`、`276`、`288` |
| `ast.js` | 只定义节点类型契约与工厂函数（无依赖），是全链路共同的类型事实源 | `ast.js:9`-`46`、`48`-`120` |
| `source-gen.js` | AST → 源码文本（Parser 的逆操作），单 block 生成用于写回源码行 | `source-gen.js:1`-`38` |
| `renderer.js` | AST → DOM：每个 block 一个 `.-src-block` 元素，行内节点递归渲染；另提供 `renderRange` 做区间增量渲染 | `renderer.js:50`-`62`、`70`-`259`、`445`-`489` |
| `mapper.js` | 三向坐标转换：`domToAst`（DOM 光标 → block/nodePath/offset）、`astToDom`（反向）、`astToSrc`/`srcToAst`（含 inline 语法前后缀长度换算），并持有当前 `_doc` | `mapper.js:424`、`560`、`782`、`299`、`1133`-`1143` |
| 渲染编排 | `renderPreview` 串联：归一 → `P.parse` → `M.setDoc` → `R.render` → 写 DOM → `stampBlockLines` → 禁编辑 → 链接后处理 → Mermaid/Lightbox → MathJax | `app.js:1828`-`1948` |

**增量渲染**：预览区编辑提交后不重建整棵树，而是 `renderRange(doc, i, i+1, .-preview-content)` 替换单个 block，随后重新 `stampBlockLines`、重跑 `MathJax.typesetPromise`、`postProcessWikilinks` + `bindPreviewLinks`（`app.js:7714`-`7729`）。

## 4. 渲染后的 DOM 与样式类

所有块级元素带 `.-src-block` + `data--block-index`；渲染后由 `stampBlockLines` 补 `data--src-line` / `data--src-line-end`（1-based）——值**直接取自 `parser.js` 的 `emit()` 落盘区间** `block.srcLine` / `block.srcLineEnd`（**块↔源码行的单一事实源**，2026-09-20 起；此前是 `app.js` 就地复写一套块边界启发式，两套判定在「缩进列表项 / 引用块 / 围栏长度」等处不一致，实测 223/274 份文档行号漂移、最大 871 行 ⇒ 预览带与 KP 高亮落到错位置）。仅当块缺该字段、或末块行号超出当前 body 行数（公式归一化曾插行）时才退回启发式（`app.js:1866`-`1867`；`parser.js:293`-`307`）。

| 渲染物 | DOM 结构 | 样式类 / 关键属性 | 锚点 |
|---|---|---|---|
| 空行 | `<div class="-src-block -blank-block"><br></div>` | **预览纵向间距的唯一来源**（各 block `margin:0`） | `renderer.js:74`-`79`；`app.css:3459`-`3494`、`3533`-`3536` |
| 段落 | `<p class="-src-block">`（空段落补 `<br>`） | — | `renderer.js:90`-`97` |
| 标题 | `<h1..h6 class="-src-block">`（空标题补 `<br>`） | 字号按 `--preview-font-size` 等比：h1×1.857 / h2×1.429 / h3×1.143 | `renderer.js:81`-`88`；`app.css:3483`-`3513` |
| 分隔线 | `<hr class="-src-block">` | 1px 上边框 | `renderer.js:162`-`166`；`app.css:3499`-`3531` |
| 引用 | `<blockquote class="-src-block">` 内含若干 `<p>`（内层**不带** `-src-block`，否则映射错乱） | 左侧 3px 竖线 | `renderer.js:168`-`185`；`app.css:3491`-`3523` |
| 列表 | `<ol\|ul class="-src-block">` + `<li>`；有序列表首项 >1 时写 `start` | 空项补 `<br>` | `renderer.js:187`-`205` |
| 表格 | `<table class="-src-block -table"><thead><tr><th>…<tbody><tr><td>` | 单元格文本再走 inline 解析（失败退化纯文本） | `renderer.js:207`-`235`、`28`-`44`；`theme/memoria.css:542`-`552` |
| 代码块 | `<pre class="-src-block -code-block"><code class="language-<lang>">原文` | **无语法高亮**（无 highlight.js/Prism 依赖），只有 `language-*` 类名与主题底色 | `renderer.js:99`-`107`；`theme/memoria.css:525`-`526` |
| Mermaid | 先渲染为 `<pre class="-src-block -mermaid"><code class="language-mermaid">`，随后整块被替换为 `<div class="-mermaid-container -src-block" data--block-index><svg>` | 失败替换为 `<div class="-mermaid-error -src-block">` + `preview.mermaidFail` 文案 | `renderer.js:244`-`252`；`markdown-preview.js:194`-`225`；`app.css:4023`-`4073` |
| 块级公式 | `<div class="-src-block -math-block">` 初始 textContent 为 `$$formula$$`，MathJax 排版后内部变为 `<mjx-container display="true">` | 居中、上下 0.75rem | `renderer.js:109`-`114`；`app.css:2962`-`2994` |
| frontmatter | `<pre class="-src-block -frontmatter">` | 无专属 CSS | `renderer.js:237`-`242` |
| 图片块 | `<p class="-src-block -image-block">` + `<img class="-preview-image">` + `<span class="-image-caption" data--image-caption>` | 对齐加 `-image-align-left/center/right`；默认 `max-width:35%`，有 width/height 属性时内联尺寸 + `max-width:100%`；`name=hide` → caption `display:none` | `renderer.js:116`-`160`；`app.css:3812`-`3850`、`3988`-`3997` |
| 行内加粗/斜体/删除线 | `<strong>` / `<em>` / `<strong><em>` / `<del>` | — | `renderer.js:310`-`330` |
| 行内代码 | `<code>` | 主题底色 | `renderer.js:332`-`335` |
| 荧光笔 | `<span class="-hl -hl-<color>" style="background-color:…">`（带前景色时再加 `style.color`） | 颜色由 renderer 内联样式决定，CSS 类仅作 fallback | `renderer.js:337`-`344`；`app.css:3795`-`3830` |
| 字体色 | `<span style="color:…">`（**无 class**） | — | `renderer.js:346`-`350` |
| 字号/`[[\b]]`/`[[\i]]`/`[[\u]]`/上下标 | `<span style="font-size/font-weight/font-style/text-decoration">`、`<sup>`、`<sub>` | — | `renderer.js:352`-`384` |
| wiki 链接 | `<a class="-wikilink" data--target>` → 后处理加 `memoria-link` + `data-link-target/-type/-line` + `role=link` | 可跳转：`-link-resolved` + `tabindex=0` + title=`preview.link.jump`；断链：`-link-broken memoria-broken-link` + `tabindex=-1` + title=`cfg.linkClick.unboundTitle`；目标集未知：`-link-pending` | `renderer.js:386`-`392`；`app.js:6260`-`6286`；`app.css:1648`-`1721` |
| 普通链接 | `<a href>`（`contentEditable=false`） | KB 内 `.md` 的相对链接被容器级委托转为应用内打开（不触发 WebView 导航） | `renderer.js:394`-`399`；`app.js:6322`-`6354` |
| 行内公式 | `<span class="-math" contenteditable="false" data-formula>`（文本 `$formula$`）；MathJax 后为 `<mjx-container data--inline-math="true" data-formula>` | 被选区覆盖时加 `-sel-covered`（浏览器不给原子块画选区） | `renderer.js:422`-`428`；`app.js:1929`、`1956`-`1993`、`9978`-`10022`；`app.css:3807`-`3839` |

不可编辑元素白名单：渲染后分两轮把 `mjx-container, pre, code, table, svg, .-mermaid-container, .-mermaid-error, .-lightbox-overlay` 以及非编辑块整块设为 `contentEditable="false"`（`app.js:1887`-`1889`、`1914`-`1924`）。

**Lightbox**：渲染后给预览内每个 `<img>` 加 `cursor:zoom-in` 与双击监听，双击时向 `body` 追加 `.-lightbox-overlay`（含 `.-lightbox-image`），单击遮罩即移除（`markdown-preview.js:496`-`519`；样式 `app.css:4004`-`4049`，`z-index:99999`）。同一双击事件在编辑模式下还会先退出图片编辑模式（`edit-handler.js:1604`-`1609`）。

## 5. 预览区交互

| 交互 | 行为 | 锚点 |
|---|---|---|
| 单击（编辑模式开） | 可编辑块 → `syncFromSelection("click")` 同步源码光标；不可编辑块 → **不同步**（把焦点留给 dblclick）；图片块空白处 → 光标停靠到 img 左/右侧（按点击点在图片中线左右判定） | `edit-handler.js:711`-`758` |
| 单/双击图片 | 单击 → 进入图片编辑工具栏；双击 → Lightbox（并退出编辑模式） | `edit-handler.js:1616`-`1647`、`1604`-`1609` |
| 双击公式 | `.-math` 或 `mjx-container[data--inline-math]` → 行内公式编辑模式（全选公式文本） | `edit-handler.js:1569`-`1587`、`983`-`1059` |
| 双击其他不可编辑块 | 进入块编辑模式（表格/代码块/公式块/mermaid/frontmatter） | `edit-handler.js:1589`-`1612`、`1064`-`1165` |
| 链接 hover | `mouseenter` → 图谱高亮该链接（`is-graph-link-focus` 类）；按住鼠标拖拽期间抑制（`e.buttons` 非 0 即不触发） | `app.js:6362`-`6369`、`6511`-`6523`、`8`-`10` |
| 链接 title | 可跳转/断链/多目标各有文案键（`preview.link.jump`、`cfg.linkClick.unboundTitle` 等） | `app.js:6276`、`6280`；`i18n/zh-CN.js:881`-`894` |
| 链接 click | `onMemoriaLinkClick`：断链 → 打开链接编辑器；多目标 → 候选选择器；单目标 → 跳转。画笔模式下不跳转 | `app.js:6130`-`6170`；`6362`-`6371` |
| 链接右键 | `bindLinkContextMenu`：编辑链接 / 复制目标 key / 复制显示文本 / 断开 / 移除路由 | `app.js:6234`-`6248`；`link-context-menu.js:94`-`160` |
| 选区右键（与源码区差异） | 预览区菜单**多出样式项**（加粗/斜体/荧光笔▾/字体色▾）与「复制 Markdown」；源码区同款菜单只有复制/创建链接/设为知识点 | `app.js:9566`-`9635`（预览）、`9533`-`9540`（源码）；`link-context-menu.js:182`-`226` |
| 折叠光标右键 | 仅「粘贴」+「插入图片」 | `app.js:9557`-`9563`；`link-context-menu.js:231`-`259` |
| 图片右键 | 交给图片子系统（替换/删除引用），预览菜单不处理 | `app.js:9551`-`9552`；`image-tools.js:192`-`198` |
| 行内公式拖拽选中 | `contenteditable=false` 原子块无法原生拖选，另实现「按下公式整体选中 + 拖拽扩展」 | `app.js:12468`-`12553` |
| 原生右键屏蔽 | 全局捕获阶段：`#editor,#preview` 只 `preventDefault`（保留自定义菜单）；工具栏/取色面板/上下文菜单额外 `stopPropagation` | `app.js:10736`-`10748` |

## 6. KP 范围高亮的两种语义

源码行用 `#line-<n>` 的类切换，预览区用浮层条 `#-preview-range-band`（绝对定位，跟随 `[data--src-line]` 块的包围盒，`app.js:11149`-`11190`）。**精度：块级**——带取的是「与查询行区间相交的块」的**并集包围盒**，块内不做行级细分；因此引用的行落在长块（代码块/表格/列表）内部时，带的起止会扩到整块（起始行号小于请求行号，属已知近似，非漂移）。

| | `highlightRange`（跳转语义） | `markRangeQuiet`（静默标记） |
|---|---|---|
| 意图 | 定位到某 KP / 行提示：**要把视线带过去** | 用户正在看屏幕（改范围/创建 KP）时**只标出来** |
| 源码行类 | `in-range` + `kp-highlight-flash`（并去掉 `fade-out`） | 仅 `in-range` |
| 滚动 | `scrollIntoView({block:"start", behavior:"smooth"})`（源码视图或分栏时才滚源码） | **不滚动** |
| 预览浮层 | `highlightPreviewRange(..., {scroll:true, flash:true})` | `{scroll:false, flash:false}`——**不清旧 band**，只重算位置 |
| 自动消失 | 800ms 后加 `fade-out`（1.5s 过渡），2500ms 后整体清除 | 不自动消失，由下一次 `dismissKpRangeHighlight()` 清除 |
| 锚点 | `app.js:11050`-`11083` | `app.js:11034`-`11048` |
| 调用方 | `openFile({kpId})` 跳转（`app.js:1488`）、`onKpClick`（`10939`）、搜索结果定位（`1114`、`12312`、`12380`） | KP 保存/创建提交后（`app.js:4667`、`11932`） |
| 第三种：错误高亮 | `highlightRangeWithError` 用 `kp-error-flash`（红色、无 `fade-out`、不自动清除），并给 KP 列表项加 `.error-highlight` | `app.js:11086`-`11118`；`app.css:3642`-`3699` |

hover 高亮是第四种轻量形态：`highlightKpHover` 加 `in-range kp-hover`，不闪烁、不自动清除，且仅当没有闪烁计时器时才动预览 band（`app.js:10993`-`11012`）。

## 7. 渲染边界与错误提示

| 情形 | 表现 | 文案键 | 锚点 |
|---|---|---|---|
| 渲染模块缺失（`Parser/Renderer/Mapper` 任一为空） | 预览区替换为 `<p class="-preview-loading">` | `preview.loadNotReady` | `app.js:1850`-`1853`、`app.css:3564`-`3596` |
| 全量渲染进行中 | 先写入 `<p class="-preview-loading">渲染中…</p>` 占位，渲染完成后被替换 | `preview.rendering` | `app.js:1856`-`1858` |
| 渲染抛异常 | 预览区显示失败文案（带异常串），并显示告警条 | `preview.renderFail`、`preview.selfcheck` | `app.js:1934`-`1938`、`2046`-`2082` |
| 链接一致性告警 | `#preview-status` 加 `warn`，提示未挂接的配置入口 | `preview.linkAuditHint` | `app.js:2035`-`2044` |
| TeX 错误 / 公式未渲染 | 仅当报告带 `messages`/`mathErrors` 时才出现 `<details><summary>TeX 错误</summary>`；**AST 主渲染路径不调用 `diagnose()`**，故主预览实际不会出现该详情块。**2026-09-20**：该块 `<summary>` 的展开标记不再用浏览器 UA 原生三角 —— 全库 `<details>/<summary>`（**含 `.markdown-body` 里用户自己写的 `<details>`**）统一换成 dsh 三角（闭合右向、`[open]` 旋转 90°），规则由 `agent-panel.js` 末尾块注入（唯一 path 见 [01 篇 §2.4 伪流式行与 §6](./01-shell-and-layout.md)） | `preview.math.texError`、`preview.math.noRendered`、`preview.math.rawDelims` | `app.js:2062`-`2074`；`markdown-preview.js:1310`-`1350`（仅 `renderToElement`/`1398` 调用） |
| 渲染成功 | 隐藏告警条，状态栏右侧写公式统计 | `preview.okDetail` | `app.js:2052`-`2061` |
| MathJax 未就绪 | 渲染流程 `await MathJax.startup.promise` + `await typesetPromise`，**主预览路径无超时**；公式会先以 `$…$` 源码文本显示，排版完成后替换为 `mjx-container` | `preview.math.timeout`（仅辅助预览路径用） | `app.js:1903`-`1910`；`markdown-preview.js:17`-`42`（400×50ms）、`app.js:11518`-`11520` |
| Mermaid 渲染失败 | 该块变为 `.-mermaid-error` 红框块，内含错误文案 | `preview.mermaidFail` | `markdown-preview.js:214`-`223`；`app.css:4037`-`4073` |
| 图片加载失败 | 该 `<img>` 加红色虚线描边 + 半透明，`alt` 追加缺失标记，`title` 写文件名 | `img.missing` | `image-tools.js:546`-`564` |
| 重入保护 | 渲染进行中再次请求 → 置 `_renderPending`，当前渲染结束后自动补渲染一次最新文档；依赖 DOM 的高亮/定位须 `await _waitRenderSettled()` | — | `app.js:1717`-`1734`、`1829`-`1837`、`1940`-`1947`、`1454`-`1456` |

## 8. i18n key 前缀（代表键）

| 前缀 | 代表键 | 说明 |
|---|---|---|
| `view.*` | `view.source`、`view.previewTitle`、`view.toggleAria` | 视图切换按钮 |
| `preview.*` | `preview.rendering`、`preview.renderFail`、`preview.okDetail`、`preview.selfcheck`、`preview.linkAuditHint`、`preview.mermaidFail` | 预览状态与失败提示 |
| `preview.math.*` | `preview.math.texError`、`preview.math.timeout`、`preview.math.noRendered` | 公式诊断（部分仅辅助预览路径使用） |
| `preview.link.*` | `preview.link.jump`、`preview.link.unresolved`、`preview.link.multi` | 链接 title 与状态 |
| `cfg.linkClick.*` | `cfg.linkClick.unboundTitle` | 断链 title |
| `menu.*` | `menu.copyMarkdown`、`menu.paste`、`menu.insertImage` | 预览区右键菜单 |

键值全文见 [i18n-inventory.md](../i18n-inventory.md)（`i18n/zh-CN.js:575`-`583`、`877`-`904`）。

## 9. 代码锚点表

| 主题 | 文件:行 |
|---|---|
| 视图按钮 DOM / 切换绑定 | `index.html:189`-`193`；`app.js:12411`-`12413` |
| `setViewMode` | `app.js:1567`-`1629` |
| 视图顶部行号 / 滚动到行 | `app.js:1632`-`1656`、`1659`-`1687` |
| 视图滚动位置存取 | `app.js:1689`-`1715` |
| 分栏双向滚动同步 | `app.js:1517`-`1540`、`12416`-`12417` |
| 三态显隐 CSS | `app.css:3413`-`3459` |
| 渲染主编排 `renderPreview` | `app.js:1828`-`1948` |
| 行内公式 mjx 标记 | `app.js:1956`-`1994` |
| 图片路径重写 | `app.js:2000`-`2026` |
| 渲染重入保护与 settled 等待 | `app.js:1717`-`1734`、`1940`-`1947` |
| 预览状态条渲染 | `app.js:2028`-`2082` |
| `stampBlockLines`（data--src-line） | `app.js:1741`-`1826` |
| wiki 链接后处理 / 绑定 | `app.js:6250`-`6287`、`6346`-`6372` |
| 链接点击 / hover 图谱高亮 | `app.js:6130`-`6233`、`6494`-`6545` |
| KB 内 `.md` 链接委托 | `app.js:6289`-`6354` |
| 预览右键菜单（选区 / 光标） | `app.js:9544`-`9637` |
| 原生右键屏蔽 | `app.js:10715`-`10751` |
| 公式拖拽选中 | `app.js:12468`-`12553` |
| KP 高亮（静默 / 跳转 / 错误 / hover） | `app.js:11034`-`11118`、`10993`-`11012` |
| KP 高亮条布局与清除 | `app.js:11136`-`11208` |
| KP 高亮 CSS | `app.css:3546`-`3591`、`3634`-`3691` |
| `lexer.tokenize` | `lexer.js:50`-`56`；`349`-`414` |
| `parser.parse/parseInline/parseBlocks` | `parser.js:276`、`39`、`316`-`499` |
| AST 类型契约 | `ast.js:9`-`46` |
| `source-gen` | `source-gen.js:13`-`38` |
| `renderer.render/renderBlock/renderInline/renderRange` | `renderer.js:50`-`62`、`70`-`260`、`303`-`436`、`445`-`489` |
| Mapper 三向转换 | `mapper.js:299`、`424`、`560`、`782`、`1133`-`1163` |
| 增量渲染单块 | `app.js:7714`-`7729` |
| Mermaid / Lightbox / MathJax 辅助 | `markdown-preview.js:182`-`225`、`496`-`519`、`17`-`42` |
| 图片加载失败提示 | `image-tools.js:546`-`564` |
| 预览相关 CSS（块/行内/公式/图片/Mermaid/Lightbox） | `app.css:3459`-`3596`、`3708`-`3748`、`3823`-`3839`、`3840`-`3850`、`3963`-`4073` |

## 10. 未证实 / 待确认

- ⚠️ 待确认（代码路径存在矛盾风险，未能运行时取证）：块级公式块在被双击编辑后，退出时用 `blockEl.textContent` 重建源码（`edit-handler.js:1130`、`1450`-`1483`）；而块级公式的 DOM 在 MathJax 排版后已由 `$$formula$$` 文本替换为 `mjx-container`（`renderer.js:109`-`114` + `app.js:1903`-`1910`）。若排版产物在 `textContent` 中非空，则写回的公式内容可能不是原始 TeX。**需运行时确认**。
- ✅ **已核实并加固（2026-09-20）**：Mermaid 渲染成功/失败时生成的替换容器**已复制** `.-src-block` 与 `data--block-index` / `data--src-line` / `data--src-line-end`（`markdown-preview.js:223`-`228`、`236`-`240`；原文"未复制"的推断与代码不符，已改正）。同时把复制条件从 `if (pre.classList.contains("-src-block"))` 放宽为「属性存在即带过去」（嵌套块如引用/列表内的 mermaid，其 `<pre>` 自身无 `.-src-block`，原来会整块丢掉行号属性 ⇒ 对该块不可见）。**行号系消费者**（`#-preview-range-band`、`_getViewTopSrcLine`、`previewBlockRange` 等）依赖 `[data--src-line]` 而非 `.-src-block`，故只补属性即可。
- ✅ **已修（2026-09-20）**：`#-preview-range-band` 原为**一次性像素定位**（渲染流程里量一次 `getBoundingClientRect` 就定死 `top/height`），而 Mermaid/MathJax 的最终高度常在 `mermaid.render` / `typesetPromise` 的 promise **之后**才定型（SVG 内文本量算、字体、图片解码都会晚一拍），长文件里这些变化累积在高亮行上方 ⇒ band 停在被抬升前的位置。实测（`test-content.md` 第 300 行）：band 8813 → 块 8980（**+167px 偏移**，且不自恢复；另一页面状态实测 **−302px**）。修法：band 上记 `dataset.srcRange`（`app.js:11330`），文件尾新增「预览带跟随布局」块用 `ResizeObserver` 盯内容容器 + 图片 `load/error` 捕获，尺寸一变即按记录区间重算（`app.js:12863`-`12896`）。**取证**：跳转后连续采样，band 与目标块同步从 8813 走到 8980（delta 恒 0）⇒ 布局后移被跟住。
- ⚠️ 待确认（文案占位符）：主预览成功分支固定调用 `showPreviewReport({ ok: true })`（`app.js:1932`），未传 `mathRendered/mathExpected`；而 `T()` 对未提供参数只保留 `{rendered}` 字面量（`i18n.js:66`-`71`），故状态栏统计可能显示未替换的占位符。需运行时观察状态栏确认。
- ⚠️ 待确认：MathJax 在主预览路径无超时（`app.js:1905`-`1910`）；若 MathJax 永不就绪，`_renderingPreview` 将长期为真并走「排队重跑」分支（`app.js:1830`-`1837`），实际表现（是否卡在 `渲染中…` 占位）未做运行时验证。
- ⚠️ 未实现但界面/代码有痕迹：`.-code-block` / `.-math-block` / `.-table` / `.-frontmatter` / `.-mermaid` 这些类名在 `app.css` 中**没有对应选择器**（表格/代码的观感来自 `theme/memoria.css` 的 `.markdown-body` 规则）；`markdown-preview.js` 的 `renderHtml` / `renderToElement` / `diagnose` / `renderHighlightSyntax` 属**另一条（marked 版）渲染链**，主预览不使用（`app.js:11494` 仅在定位辅助弹窗里调用 `renderHtml`）。
- ⚠️ 未验证：`.-link-multi`（多目标链接）类的样式与判定在 AST 主链路上的实际赋值点；`postProcessWikilinks` 只写 `-link-resolved` / `-link-broken` / `-link-pending`（`app.js:6274`-`6285`），`-link-multi` 由后续链接解析流程设置，本次未逐处取证。
