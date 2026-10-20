# 显示子系统接口契约（View Surface Contract）

> **状态**：2026-09-28 初稿，**待评审**；**未施工**。
> **这份文档的地位**：它是**两个插头共用的「插口」定义** —— `LegacySurface`（现有实现）与 `NewSurface`（从 0 重做）**都必须满足它**。冲突时以本文为准；**本文未定义的，实现自由**。
> **它不是**：设计论证（见 [preview-render-refactor.md](preview-render-refactor.md) §1.6–§1.10）、实施步骤（见同文档 §2–§4）、实施台账。
> **来源**：人「**在原来的地方改动牵涉东西很多，要不我们把这个接口化，然后按照需求专门从 0 开始做，一一把接口对齐**」+「**老实现和新实现是"两个插头"**」+「**整个显示区域涉及的接口，所有有关显示的**」+「对话栏气泡**也是 memoria 语法、也能点击跳转**，只是不需要编辑」。

---

## 0. 术语与立场

| 词 | 含义 |
|---|---|
| **真源（source of truth）** | **正文文本**（`state.doc.body` / `lines`）。**不是 AST**（见 §1.5） |
| **渲染内核 RenderCore** | **只读**：文本 → 块 DOM + 可激活的 wikilink / KP |
| **可编辑外壳 EditSurface** | 在 RenderCore 之上加**编辑**（光标 / IME / 事务 / 撤销 / 冻结 / 落点） |
| **宿主 Host** | 现有 `app.js` 那一侧：文件、页签、写盘、后端 RPC、设置、KP 列表 |
| **插头 Surface** | 一个完整实现（`LegacySurface` / `NewSurface`）。宿主**只认本文接口** |

**三条立场（写死，避免以后争）**：

1. **宿主不直接改 DOM**；引擎**不写磁盘、不调后端**。所有跨界都走本文的入口 / 回调。
2. **存在"DOM 领先真源"的窗口**（§3.3）。这是**允许的**，代价是**每个读真源的入口都要先 flush**；清单见 §3.3，漏一处即违约。
3. **性能不是可选要求**：契约里带**预算**（§5 C9）。

---

## 1. 分层与消费者

```
┌──────────────────────────── RenderCore（只读，无状态或弱状态）────────────────────────────┐
│  文本 ──▶ 块 DOM（-src-block[]，带稳定块 id）＋ wikilink / KP 可激活                        │
└───────────────┬───────────────────────────────┬──────────────────────────────────────────┘
                │                               │
      消费者 A：预览栏                      消费者 B：对话栏助手气泡（流式、只读）
      （接 EditSurface）                     （只接 RenderCore）
```

**分层铁律**：消费者 B **不得**依赖 EditSurface 的任何能力；反之 EditSurface **可以**依赖 RenderCore 的**全部**能力。

---

## 2. RenderCore（只读）

### 2.1 接口

```js
createRenderCore(opts) -> Core

Core.renderAll(text, container) -> { blocks: BlockHandle[], text: string }
Core.appendChunk(chunk, container) -> { blocks: BlockHandle[] }      // 流式（助手气泡用）
Core.activateLinks(root, onActivate) -> void                        // wikilink / KP 绑定 + 解绑
Core.measure(container) -> { nodes, blocks, bytes }                 // 读数
Core.dispose(container) -> void
```

- `BlockHandle`：`{ id, srcStart, srcEnd, el, kind }`。**`id` 稳定**（§5 C1），`srcStart/srcEnd` 是源码行区间。
- `opts`：`{ resolveLink, resolveKp, renderMath, renderMermaid, lazyImages }` —— 由宿主注入**能力**，内核不自带后端知识。
- **两个入口的必要性**：`renderAll`（预览栏：整篇 + 可编辑）与 `appendChunk`（气泡：流式追加）**同一套渲染语义** —— 这是 R18 追加修正带来的（§1.10 A′）。

### 2.2 不变量（契约测试依据）

| # | 不变量 |
|---|---|
| **I1** | **同文本 ⇒ 等价 DOM**：同一份文本经 `renderAll` 与逐块 `appendChunk` 重建，**块序列与每块文本内容逐字相同** |
| **I2** | **保真**：渲染**不得改写**真源文本；内核**不接受**"渲染后把文本写回去"的路径 |
| **I3** | **块身份稳定**：文本不变时重复渲染，同一逻辑块的 `id` 不变（下标位移不得改变 id）|
| **I4** | **内容之外无 DOM**：内核往容器里写的元素**只在 `.-src-block` 之内**（或明确标注的装饰容器）—— 不得在块内混入"非内容 DOM"（见 §1.8 结论 B 的旧债）|

### 2.3 错误与降级

- 解析器抛错 / 未就绪 ⇒ **渲染成纯文本块**并回调 `onDegraded(reason)`；**不得**留下空容器。
- MathJax / Mermaid 未就绪 ⇒ 先以源码态显示，就绪后**由内核内部**升级（宿主不参与）。

---

## 3. EditSurface（可编辑外壳）

### 3.1 接口（宿主 → 引擎）

```js
mount(container, host) -> void          // container 由宿主提供；引擎接管其内容
setText(text, cause) -> void            // cause ∈ open | switch | reload | external
setMode(mode) -> void                   // source | split | preview
applyEdit(op) -> void                   // ★ 唯一内容变更入口；op 见下
undo() / redo() -> void
revealRange(startLine, endLine, opts) -> void     // 跳转落点（opts: {scroll, flash})
getScrollAnchor() -> Anchor             // 切模式 / 换文件时取
setScrollAnchor(a) -> void
getSrcRangeForSelection() -> SrcRange | null
isBlockFrozen(blockId) -> boolean       // §3.4；宿主/装饰也可问
destroy() -> void
```

- **`op`（EditOp）**：对真源的一次变更。**这是"同步"的唯一入口**（§1.7）。
  ```js
  { kind: 'insertText' | 'deleteRange' | 'splitBlock' | 'mergeBlock' | 'replaceRange',
    at: { blockId, path, offset } | { startLine, startCol },
    text?, range?, cause: 'user' | 'ime' | 'paste' | 'undo' }
  ```
- **宿主永远不传"像素"或"DOM 节点"**，只传**文本坐标**。

### 3.1bis 门面键名对照（实现现状）

> **为什么单列**：宿主（`surface/legacy-surface.js`）经 `MemoriaApp.surface` 门面取用引擎能力，而门面受"零行漂移"约束只能**追加新键**，且部分能力在实现里是「`EditOp` 的 `kind`」或「§3.1 未列的方法」⇒ 门面**键名与 §3.1 方法名并非 100% 同名**。本小节把「门面键 ↔ 契约位置 ↔ 内部实现」列为事实，**只为消歧义，不改动 §3.1 语义**。

`MemoriaApp.surface` 共 **11 键**（定义于 `src/memoria/ui/static/app/js/app.js` 的 `window.MemoriaApp.surface = { … }`）：

| # | 门面键 | 契约位置 | 映射到的内部实现 |
|---|---|---|---|
| 1 | `setBlockSource(blockIndex, src)` | §3.1 无（`applyEdit` 的**块级等价入口**，源自 mermaid 门面） | `window.__blockLineMap` + 改 `state.doc` + `renderEditor` + `renderPreview({incremental})` |
| 2 | `getBlockSourceRange(blockIndex)` | §3.1 无（只读读数） | `window.__blockLineMap[i]` → `{startLine, endLine}` |
| 3 | `getBlockSourceText(blockIndex)` | §3.1 无（只读读数） | `state.doc.lines.slice(startLine, endLine + 1)` |
| 4 | `setMode(mode)` | §3.1 `setMode(mode)` | `setViewMode(mode)` |
| 5 | `collectText()` | **§3.1 无对应方法**（是 §3.2 `onTextChange` 的真源读数来源） | `collectEditorBody()` |
| 6 | `revealRange(startLine, endLine, opts)` | §3.1 `revealRange(startLine, endLine, opts)` | `highlightRange`（band + flash，含 AG104 二次校准）；`opts.scroll === false` ⇒ `markRangeQuiet` |
| 7 | `getScrollAnchor()` | §3.1 `getScrollAnchor()` | `_getViewTopSrcLine(state.viewMode)` |
| 8 | `setScrollAnchor(a)` | §3.1 `setScrollAnchor(a)` | `_scrollToSrcLine(a.mode, a.srcLine)` |
| 9 | `deleteRange(range)` | **§3.1 无此方法**：对应 `EditOp` 的 `kind: 'deleteRange'` | `_surfaceSpliceRange(range, null)` |
| 10 | `replaceRange(range, text)` | **§3.1 无此方法**：对应 `EditOp` 的 `kind: 'replaceRange'` | `_surfaceSpliceRange(range, text)` |
| 11 | `applySelectionStyle(formatType, color, range, force)` | **§3.1 无此方法**（样式类编辑，非文本坐标 op） | `MemoriaEditSync.applyStyle(...)` |

**四个非同名键的归属**（消除"契约与实现命名不一致"这一未来分歧点）：

- `collectText` —— §3.1 **无**对应方法名；它是 §3.1「真源」的对外读数出口，§3.2 `onTextChange(text, cause)` 的 `text` 即取自它。
- `replaceRange` / `deleteRange` —— **不是 §3.1 的方法名，而是 `EditOp` 的 `kind` 取值**（§3.1：`op.kind ∈ { insertText, deleteRange, splitBlock, mergeBlock, replaceRange }`）。门面把这两个 `kind` 提为方法，属"等价入口"，粒度 = **整行、1-based 含端点**（列信息忽略）。
- `applySelectionStyle` —— §3.1 **无**此方法；样式类编辑在契约里归 §3.1 `applyEdit(op)` 的语义面，实现走 `MemoriaEditSync.applyStyle`（`range` 为 DOM `Range`），故以独立键暴露。
- 另注：§3.1 中的 `mount` / `setText` / `applyEdit` / `undo` / `redo` / `getSrcRangeForSelection` / `isBlockFrozen` / `destroy` **不在** `MemoriaApp.surface` 门面上（由插头适配器按契约直连，或尚未开窗）。

### 3.2 宿主回调（引擎 → 宿主）

| 回调 | 时机 | 宿主该做什么 |
|---|---|---|
| `onTextChange(text, cause)` | **真源变化时**（可能在 flush 之后，见 §3.3） | 更新 `state.doc`、同步源码面板、`markDirty()` |
| `onCursorChange(srcRange \| null)` | 光标/选区变化 | 源码侧假光标、KP 高亮、格式工具条可用性 |
| `onLinkActivate(target)` | 用户点了 wikilink / KP | 打开目标 / 跳转 |
| `onRevealRequest(kind, payload)` | 引擎需要宿主做（如"打开那个文件") | 执行并**不回调**引擎（单向） |
| `onMeasure(stats)` | 每轮渲染/交互后 | 读数面板 |
| `onDegraded(reason)` | 内核降级 | 记日志（可选提示） |

### 3.3 时序契约（**最重要的一节**）

**允许**：引擎在用户输入当帧**只让浏览器写 DOM**，把"更新真源"推迟到**这一帧画完之后**（`rAF → setTimeout(0)`）。

**代价与义务**：于是存在一个 **DOM 领先真源的窗口**。在此窗口内，**任何读真源的入口都必须先 `flush()`**。清单：

| # | 入口 | 为什么 |
|---|---|---|
| F1 | `applyEdit` 的**每个** `op` | 要基于最新真源算坐标 |
| F2 | `undo` / `redo` | 快照语义 |
| F3 | `getSrcRangeForSelection` | 返回的坐标必须与真源一致 |
| F4 | `getScrollAnchor` / `setScrollAnchor` | 锚点是"源码行"语义 |
| F5 | `revealRange` | 落点要对得上真源 |
| F6 | `setMode` / `setText` | 换视图/换文件前必须落定 |
| F7 | `destroy` | 销毁前必须落定（否则丢字） |
| F8 | 宿主的 `onTextChange` 消费方：写盘、缓存暂存、KP 解析、对话引用 | 都读真源 |

**自检**：任何入口若检测到"仍有未落定变更"，必须 **`console.error("漏 flush")`**（开发期），**不静默**。

**性能预算（契约的一部分）**：按键 → 更新真源 ≤ **16 ms**（5900 行文档）；`flush()` 无待办时 ≤ **0.1 ms**。

### 3.4 冻结规则（三层所有权的执行点）

```
isBlockFrozen(blockId) := 正在块编辑 ‖ 正在图片 caption 编辑
                       ‖ IME 组合中且光标在此块 ‖ 非折叠选区跨过此块
```

**引擎义务**：命中冻结的块，**不重建、不摘除、不搬走、不复用其子节点**。

---

## 4. 双插头协议

### 4.1 注册与切换

```js
SurfaceRegistry.register(name, factory)   // name: 'legacy' | 'new' | …
SurfaceRegistry.current()                 // 当前插头名
SurfaceRegistry.switchTo(name, ctx)       // 运行时切换（设置项或控制台）
```

切换必须是**无损**的：文本、光标、滚动锚点、当前视图模式**交接**（§4.2）。

### 4.2 交接（switchTo 的契约）

```
1. 老插头 flush()  →  取出 { text, cursor, anchor, mode, frozen }
2. 老插头 destroy()
3. 新插头 mount() + setText(text) + setMode(mode) + setScrollAnchor(anchor)
4. 新插头恢复光标
5. 若任一步失败 ⇒ 回滚到老插头，并 onDegraded('switch-failed')
```

### 4.3 能力声明（capabilities）

插头**声明**自己支持什么；宿主据此**显式降级**（而不是静默失效）：

```js
surface.capabilities -> {
  virtualization: boolean,     // 只渲染视口
  incrementalRender: boolean,  // 块级复用
  blockEdit: boolean,          // 代码/公式/表格/mermaid 块编辑
  imageCaption: boolean,
  findInPage: 'native' | 'builtin' | 'unsupported',   // ← 视口化的已知代价（§1.8 #16）
}
```

### 4.4 失败与回退

- 插头 `mount` 抛错 / 关键不变量违约 ⇒ **自动切回 legacy**（不许留在半坏状态）。
- 切换状态**必须可见**（设置项里显示当前插头）。

### 4.5 ★ 插头方法语义表（`surface-new` 施工依据，2026-10-20）

> **给谁看**：`surface-new`（新渲染管线 RenderCore 的 owner）实现 `surface/new-surface.js` 的 13 个占位方法时，**以本表为准**。
> **原则**：契约 owner 是 `arch-contract`；凡本表与实现冲突，以本表 + 上游 §3/§4 为准，回报 Lead，勿自行改对方文件。

#### 4.5.1 方法清单（13 个，与 `new-surface.js` 一 一对应）

§3.1 列了 12 个；`flush`（§4.2 交接第一步）补齐为第 13 个。**每个方法失败语义二选一：`throw`（契约违规，宿主回滚）或 `降级`（如实上报 `onDegraded`，不伪造成功）——绝不允许静默吞错或返回假值。**

| # | 方法 | 职责 | 入参 | 出参 | 调用时机 | 失败语义 | P2a 必须实现？ |
|---|---|---|---|---|---|---|---|
| 1 | `mount(container, host)` | 引擎接管 `container` 内容；`host` = §3.2 回调集；**首次挂载不重放 setText/setMode**（避免加载期刷顶/重渲） | container(HTMLElement), host(callbacks) | void | 插头首次激活 / switchTo | `throw`（mount 失败 = 插头不可用 ⇒ 回滚 legacy） | ✅ 是（骨架：空挂载即可） |
| 2 | `setText(text, cause)` | 全量替换正文并**全量重建**块树 | text(str), cause∈{open,switch,reload,external} | void | 打开/换文件/切换接手 | `throw` | ✅ 是（RenderCore 主入口） |
| 3 | `setMode(mode)` | 切视图（source/split/preview）；**删 DOM 前先 flush**（F6） | mode∈{source,split,preview} | void | 视图按钮/快捷方式 / **§4.2 交接第④步（无条件调用）** | **仅非法 mode 抛错**；合法 mode 必须接受并记录（见下） | ✅ **必须**（接受并记录 mode，可查询）；**DOM 视图切换延后 P2b** |
| 4 | `applyEdit(op)` | **唯一内容变更入口**；op 见 §3.1；**每个 op 前先 flush**（F1） | op(EditOp) | void | 打字/结构编辑/粘贴/撤销 | `throw`（编辑语义错误 = 数据不一致） | ⚠️ 可 `throw NotImpl`（P2a 只渲染不编辑） |
| 5 | `undo()` | 撤销一步；**前先 flush**（F2） | — | void | Ctrl+Z | `throw NotImpl`（未实现撤销也允许，见 §4.5.3） | ❌ 可 `throw NotImpl` |
| 6 | `redo()` | 重做一步；**前先 flush**（F2） | — | void | Ctrl+Y | 同上 | ❌ 可 `throw NotImpl` |
| 7 | `revealRange(startLine, endLine, opts)` | 跳转落点：滚到行区间 + 可选 band/flash；**前先 flush**（F5） | 1-based 含端点；opts{scroll,flash} | void | 点链接/KP/搜索/检查 | `onDegraded`（落点失败不致命） | ⚠️ 可先 `throw NotImpl`（P2a 无跳转） |
| 8 | `getScrollAnchor()` | 取当前滚动锚点（**源码行**语义，非像素）；**前先 flush**（F4） | — | Anchor{srcLine,mode} | 切模式/换文件前 | 返回 null 或抛 | ⚠️ 可 `throw NotImpl` |
| 9 | `setScrollAnchor(a)` | 恢复滚动锚点；**前先 flush**（F4） | Anchor | void | 切回/换文件恢复 | `onDegraded` | ⚠️ 可 `throw NotImpl` |
| 10 | `getSrcRangeForSelection()` | 当前选区 → 源码坐标；**前先 flush**（F3） | — | SrcRange\|null（无选区） | 选区→链接/样式/KP | 返回 null（无选区不算是错） | ⚠️ 可 `throw NotImpl` |
| 11 | `isBlockFrozen(blockId)` | 冻结判定（§3.4）；命中 ⇒ 该块**不重建/不摘除/不复用** | blockId | boolean | 块内编辑/公式/表格时 | 查不到 ⇒ **保守返回 true** | ✅ 是（P2a 至少返回 false 或保守 true） |
| 12 | `destroy()` | 销毁引擎实例、清引用；**前先 flush**（F7） | — | void | switchTo 切走 / 关闭 | 尽力而为，不抛 | ✅ 是 |
| 13 | `flush()` | 把"DOM 领先真源"窗口内的未落定变更**落地到真源**；无待办 ≤0.1ms | — | 交接包 `{text,cursor,anchor,mode,frozen}` | §4.2 交接第 1 步 + F1–F7 每入口前 | `throw`（flush 失败 = 丢字，严重） | ✅ 是（P2a 可返回当前快照） |

#### 4.5.2 切换交接顺序（§4.2 展开，每步对新插头的要求）

```
① 老插头 flush()   → 交接包 {text, cursor, anchor, mode, frozen}
   要求：flush 必须**把未落定变更落地**（否则切过去丢字）；返回的 text 是唯一真源。
② 老插头 destroy() → 清引用、不摘 #editor-split（DOM 归宿主）
   要求：destroy 幂等；不得在此抛错阻断回滚。
③ 新插头 mount(container, host)
   要求：空挂载即可；**首次挂载（old==null）不重放 setText/setMode**（registry.js 已如此）。
④ 有交接包时：setText(text,'switch') → setMode(mode) → setScrollAnchor(anchor) → 恢复光标
   要求：各步**顺序不能乱**（先正文、再模式、再锚点、最后光标）；恢复光标走 revealRange(不滚动不闪)。
⑤ 任一步失败 ⇒ 回滚：老插头 mount + setText/setMode/setScrollAnchor + onDegraded('switch-failed')
   ★ 回滚也必须**不抛**（尽力而为）；若回滚也失败，_current/_instance 置 null（不留半坏态）。
```

**哪步失败必须回滚**：① flush 异常、③ mount 抛错、④ 任一 `setText/setMode/setScrollAnchor` 抛错——**都回滚**。⑤ `onDegraded` 后不得再试图"半切换"。

#### 4.5.3 P2a 最小可用子集（5 类块：paragraph/heading/listItem(+list)/blockquote/horizontalRule）

**P2a 各方法的"必须实现 / 可暂缺"分级**——`new-surface.js` 骨架已全部抛 NotImpl，`surface-new` 填充时按下表把方法从"占位抛错"改成真实现；**标"可抛 NotImpl"的继续抛是合法的**，但标"必实现"的**必须**接住：

| 方法 | P2a 是否实现 | 依据 |
|---|---|---|
| `mount` / `setText` / `flush` / `destroy` | ✅ **必实现** | 渲染最小闭环 |
| `setMode` | ✅ **必实现（接受并记录）；DOM 视图切换可延后到 P2b** | §4.2 交接第④步**无条件**调 `setMode`：若本方法抛 `NotImpl`，throw 会被 catch ⇒ 回滚 ⇒ `switchTo('new')` **永远失败**（`surface-new` 实测）。故本方法**不属于"可抛 NotImpl"之列**：必须接受合法 mode 并**记录**（交接后 `getMode() === 请求值`），但**不得伪造视图 DOM**（P2a 三视图 DOM 仍归宿主 `app.js`）；**非法 mode 必须抛错**。这是 P2a 的已知偏离（见 §4.5.5 K2），P2b/P3 补真正的视图切换 |
| `applyEdit` / `undo` / `redo` | ❌ 可抛 NotImpl | P2a 只渲染不编辑（§0：RenderCore 只读优先） |
| `revealRange` / `getScrollAnchor` / `setScrollAnchor` / `getSrcRangeForSelection` | ⚠️ 可抛 NotImpl | P2a 无跳转/无选区 |
| `isBlockFrozen` | ✅ 建议返回 `false`（恒不冻结） | 5 类块都非冻结类型；比抛错更"可用" |

**红线（防"伪造可用"）**：`surface-new` **不得**实现一个"返回假空值但看起来能用"的方法（如 `applyEdit` 返回空而不抛）——那样 C11 会在 NewSurface 未真正编辑时被误判等价。**未实现就抛 NotImpl，是契约允许且鼓励的诚实降级。**

**★ 反例纪律（与 `metrics-baseline` 的同名纪律呼应）**

> **契约不得要求实现者绕过宿主交接序列才能被切换。**
> 任何"**按契约字面实现就永远切不过去**"的条款，都是**契约缺陷**，不是实现者的错。
> **判定方法**：把该条款代进 §4.2 交接序列走一遍——若任一步的合法实现会让整条序列必然失败（throw 被 catch ⇒ 回滚），则该条款必须放宽（降级为"接受并记录"）或调整交接序列。

**本条的成因（留痕）**：§4.5.3 曾把 `setMode` 列入"可抛 NotImpl"，而 §4.2 第④步无条件调它 ⇒ 两者相乘 = `switchTo('new')` 必然失败。`surface-new` 实测踩到后才暴露——**契约自相矛盾不会在纯文档评审里现形，只在"实现者严格照做"时爆炸**。教训：**新增"可抛/可缺"条款时，必须与 §4.2/§3.3 的调用序列交叉验证**。

#### 4.5.4 与 BlockIndex 的边界（`surface-new` 必须按此接线）

新管线（RenderCore 内嵌于 EditSurface 外壳）在**这些时机**操作单例 `window.MemoriaApp.blockIndex`：

| 方法 | BlockIndex 动作 | reset？ | 说明 |
|---|---|---|---|
| `setText(text, cause)` | `beginStamp({reset:true})` → 逐块 `upsert` → `commit()` | ✅ reset | 全量重建（文本全换）；`cause` 决定是否真换文件 |
| （将来的）块级增量 | `beginStamp()`（不 reset）→ `upsert(id 显式)` → `commit()` | ❌ 不 reset | 局部路径：显式 id 就地更新（G1 裁决） |
| `flush()` | **不碰** BlockIndex | — | flush 落定的是**真源文本**，不是索引 |
| `isBlockFrozen(blockId)` | 只读 `BlockIndex.get(id)` / 不写 | — | 冻结是时变状态（R6，方法形态） |

**id 语义（Lead 裁决 task-22，勿弄反）**：**id 标识身份，不保证内容不变**。局部路径同 id 就地更新 ⇒ 被编辑块 id 不变；整篇重 parse 才按内容哈希换 id。内容变化信号 = `onPatched.changedIds` / `domVersion` / 行区间，**不是 id**。

#### 4.5.5 ⚠️ 已知契约偏离表（`surface-new` 必读）

> 登记**契约与实现之间已确认的缺口/不一致**。每条给：现象、为什么违反契约、建议归属、纳入时机。
> **凡在表内的偏离，`surface-new` 都应知道"它迟早要补"，不得把它当作可长期忽略的差异。**

##### K1 · `capabilities` 字段名（已修，记录留痕）

`new-surface.js` 的 `capabilities` 字段曾是 P1 占位期临时写的 `{supportsEdit, supportsViewport, supportsStableBlockId, implemented}`，与 §4.3 正式字段 `{virtualization, incrementalRender, blockEdit, imageCaption, findInPage}` 不一致。
- **处置**：已改回 §4.3 字段名（2026-10-20）。
- **教训**：**先定契约字段再写骨架**——占位期用临时字段名，会被后来者当成契约照抄。

##### K2 · `setMode` 的视图切换延后到 P2b/P3 ★（2026-10-20 登记）

**现象**：P2a 只做渲染（5 类块 AST→DOM），**不做三视图（source/split/preview）的真实 DOM 切换**——那仍由宿主 `app.js` 负责。但 §4.2 交接第④步**无条件**调 `next.setMode(mode)`。

**为什么曾是契约缺陷**：§4.5.3 早期把 `setMode` 列进"可抛 NotImpl" ⇒ 与 §4.2 第④步相乘 = throw 被 catch ⇒ 回滚 ⇒ **`switchTo('new')` 永远失败**。`surface-new` 实测踩到。**这是契约文档内部冲突，不是实现者的锅**（成因与纪律见 §4.5.3 的"反例纪律"）。

**现行条款（已统一）**：
- **必须接受合法 mode 并记录**（交接后 `getMode() === 请求值`，可查询）；
- **不得伪造视图 DOM**（P2a 三视图 DOM 仍归宿主）；
- **仅非法 mode 抛错**；
- 移交：`switchTo('new')` 可成功（不再被 setMode 堵死）。

**建议归属 / 纳入时机**：**P2b / P3** 补真正的 DOM 视图切换（届时 `setMode` 拥有完整语义）。
**当下对 `surface-new` 的指引**：`setMode(mode)` 落成「校验 + 存 `_mode` 字段」即可，**不要**做 DOM 切换、也不要抛 NotImpl。

##### K3 · "等价"的确定性边界：不得把随机量纳入对比基线 ★（2026-10-20 登记）

**为什么登记**：契约里多处用"逐字/逐字节等价"（§2.2 **I1**、§5 **C10/C11**、§4.5.5 K4）。但实测证明 **DOM 里存在合法的非确定性**——若把整棵 DOM 逐字节做对比基线，会**周期性假红**，实现者会被迫去"消除"本来不该消除的东西。

**实测证据（本项目已踩到）**：
- **mermaid** 每次渲染生成**随机 SVG id**（`#mermaid-vppr1439` vs `#mermaid-yjl12f8b`），CSS 选择器全部带该前缀 ⇒ 整个 `<style>` 块与 `id` 属性每轮都不同。`run_fidelity.py` 与 `S_old v2` 对比时，5 个文件里只有含 mermaid 的那个"diff"，**抹掉随机 id 后 0 diff**。
- **MathJax** 生成的 `mjx-*` 内部 id/编号同理。

**条款（新增，约束所有等价性断言）**：

> **"等价"必须定义在一个确定性投影上，不得要求整棵 DOM 逐字节相同。**
> 合规的对比口径至少包含：**块序列（kind 顺序）** + **每块的规范化文本**（`textContent` 去空白）。
> **必须归一化**（在对比前抹掉）：随机/递增 id（`mermaid-*`、`mjx-*` 内联 id）、行内 `<style>` 的选择器 id 前缀、时间戳类属性。
> **不得**把"随机量为零差异"写成验收要求——那是**不可实现的确定性**。

**对 `metrics-baseline` comparator 的呼应**：其 `signatureNorm` 若未落盘会导致"文本恒空 ⇒ 只比 kind+tag 就判 match"的**假 match**（工具侧缺陷，由 `metrics-baseline` 修）。本条从**契约侧**给出正面对口径：**签名必须包含文本，且必须对上述随机量归一化**——两者缺一即不可信（**假 match** 与 **假 diff** 是同一个确定性问题的两面）。

##### K4 · 链接层后处理散落在 `app.js`（**legacy 的插头面不完整**）★

**现象**：`legacy` 的"公开插头面"（§3.1 的 13 个方法 + RenderCore）**不包含链接层**。两段后处理只存在于 `app.js` 私有闭包里，不在 `SurfaceHost` / RenderCore 契约内：

| 函数 | 位置 | 做了什么 | 依赖 app.js 私有状态 |
|---|---|---|---|
| `postProcessWikilinks(root)` | `app.js`（`function postProcessWikilinks`） | 给 `.-wikilink` **补 class/attr**：`memoria-link` / `role=link` / `data-link-target` / `data-link-type` / `data-link-line`（**读 `data--src-line` 反查行号**）；并按目标集合判 **resolved / broken / pending 三态**（加 `-link-resolved` / `-link-broken` / `-link-pending` + `tabindex` + `title`） | `state.linkTargetSet`、`state.doc.link_overrides`（侧车路由）、`T()` i18n |
| `bindPreviewLinks(root)` | `app.js`（`function bindPreviewLinks`） | 给 `.memoria-link` **绑 4 类事件**：click（`onMemoriaLinkClick`）、mouseenter/mouseleave（`highlightGraphFromLink` 图谱联动）、contextmenu（`bindLinkContextMenu`）；容器级委托把 KB 内 `.md` 链接转应用内打开 | `onMemoriaLinkClick`、`highlightGraphFromLink`、`bindLinkContextMenu`、`state.graphLinkFocusEl` |

**为什么算契约偏离**：
1. §5 **C8「交互存活」明确要求"wikilink 可点"**——即这是**契约已承诺的能力**，但实现不在插头面内 ⇒ **契约承诺与实际归属不符**；
2. RenderCore 的定位是"文本 → 块 DOM + **可激活的 wikilink / KP**"（§0.细则、§2.1 `activateLinks`）——`activateLinks` **在契约里存在（§2.1），但 legacy 侧没有对应实现**，它散在 `app.js`；
3. ⇒ **新管线要做到与 legacy 逐字节等价，迟早必须把这两段纳入契约**，否则 `06-links-and-kp.md` 这类含链接文档**永远 diff**（C11 永远不可能绿）。

**建议归属：`P2b`（代码/表格/图片片）——不是 P4（编辑层）。**

**契约角度的理由（3 条）**：
1. **它属于"渲染内核"而非"编辑外壳"**：§1 分层铁律写明 `RenderCore`（只读）负责"块 DOM + 可激活的 wikilink / KP"，消费者 B（助手气泡）**只接 RenderCore** 也要"能点击跳转"（§1 消费者 B 定义）。**气泡不需要编辑却需要链接可点** ⇒ 链接层必须在 RenderCore 侧，与编辑层无关 ⇒ **放 P4 会错层**。
2. **它与"块类型渲染"同批**：`postProcessWikilinks` 读 `data--src-line`（块行区间）——与块渲染同源；P2b 正好在扩块类型（代码/表格/图片），链接是块内 inline 元素，**同批处理内聚度最高**。
3. **P4 编辑层的验收是"编辑不丢字/光标不错位"**，与"链接可点"无关；把链接塞进 P4 会让 P4 范围失控。

**纳入时机（建议）**：**P2b 开工时**，把以下内容**正式写进契约**，而不是等 P4：
- §2.1 `activateLinks(root, onActivate)` 补**完整语义**（三态判定、补哪些 attr、事件绑定归属）；
- §3.2 `onLinkActivate(target)` 明确**由 RenderCore 触发**（而非宿主自己扫描）；
- **依赖注入**：`state.linkTargetSet` / `link_overrides` / i18n **必须由宿主以 `opts.resolveLink` 注入**（§2.1 的 `opts` 已有 `resolveLink` 位）——**内核不得读宿主私有 state**；
- C8 的断言补"新管线链接三态与 legacy 逐项一致"。

> **给 `surface-new` 的当下指引**：P2a（5 类块）**不涉及**链接层 ⇒ 可暂不实现；但**别在块渲染里顺手把链接写死成纯文本**（那样 P2b 要返工）。块内 wikilink 应渲染成 `<span class="-wikilink" data--target="…">`（与 legacy 同结构），**后处理留给契约补齐后的 `activateLinks`**。

---

## 5. 契约测试清单（对接一致性套件）

> 每条都是**行为**断言（不是"源码里有某个字符串"），跑在真浏览器里；语料与脚本见 `tests/probe-kb/`。

| # | 断言 | 怎么测 |
|---|---|---|
| **C1** | 块 id 稳定 | 改一处文本 → 其余块的 id 全部不变 |
| **C2** | 文本保真 | 打开 + 不编辑 + 保存 ⇒ 磁盘文件**逐字不变** |
| **C3** | 打字当帧可见（**两条都要**） | ① **硬指标**：预览栏受信任单键输入时 **`beforeinput.defaultPrevented === false`**（= 原生插入被允许 ⇒ 那一刻 DOM 归浏览器）；② 输入后同帧读 DOM 已含该字符 —— ⚠️ **2026-09-28 基线实测确认：② 单独用不具区分力**（legacy 在同一任务内同步写 DOM，也能过），故 **① 才是判据** |
| **C4** | 真源不落后 | 打字后立刻 `getSrcRangeForSelection()`，坐标与 DOM 一致 |
| **C5** | 冻结不破 | 块编辑中触发块级重渲 ⇒ `textarea` 仍在文档里、内容不丢 |
| **C6** | 落点准确 | `revealRange(L, L)` ⇒ 首屏第一块的 `srcStart ≤ L ≤ srcEnd`（±1 行） |
| **C7** | 切模式不漂 | preview ↔ split ↔ source 各切一次，锚点行不变 |
| **C8** | 交互存活 | 任意重渲/复用/视口移动后：wikilink 可点、图片可双击进编辑、高亮 band 位置正确 |
| **C9** | 性能预算 | 5900 行文档：按键→真源 ≤ 16 ms；滚动 200 次无长任务 > 50 ms |
| **C10** | 两消费者一致 | **同一文本**：预览栏 DOM 与气泡 DOM 的**块序列 + 每块文本**逐字相同 |
| **C11** | 插头等价 | 同一操作脚本跑 legacy 与 new，**逐字文本 + 落点行号**一致（不一致时人来裁） |
| **C12** | 无损切换 | `switchTo('new')` 再 `switchTo('legacy')` ⇒ 文本/光标/锚点回到原处 |

---

## 6. 明确**不承诺**（划出去，避免范围蔓延）

| 不承诺 | 理由 |
|---|---|
| 知识图谱（2D/3D）的任何行为 | 独立渲染器 + 独立数据 |
| 检查 / 配置 / KP 弹窗 | 表单 |
| 助手气泡的**流式时序**细节（节流、增量粒度） | 由宿主与气泡自己定；内核只承诺 I1 |
| 磁盘格式、后端 RPC、写盘时机 | 宿主的责任 |
| 光标/选区的**像素级**语义（只用源码坐标） | 契约以**文本坐标**为准 |
| 未来形态（如单栏 live preview 模式） | 见 §1.6 ⑤ 与 R16；不在本契约内 |

---

## 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-28 | **首次「legacy 契约基线」体检完成**（`scripts/benchmark/surface/run_probe.py --label legacy-baseline`，产物 `results/probe-legacy-baseline_43ee02c7.{json,md}` + 中间证据 `raw-probe-legacy-baseline_43ee02c7.json`）。**绿**：C2 文本保真（逐字 485 B == 磁盘）、C3、C4。**红**：**C6 落点**（头/中命中，**尾目标因"文档末尾滚动钳制"无法置顶** —— 已区分"落点错"与"钳制"）、**C7 切模式锚点漂 Δ=2 行**、**C9 性能**（`scale-5k` 5000 行打 30 字：**median 17.5 ms / p95 23.7 / max 46.7**，预算 ≤16 ms ⇒ 超；页面 `[EDIT]` 与读数互证）。**未测**：C1（legacy 无块 id，`data--block-index` 是位置下标）、C5、C8、C10、C11/C12（`new` 插头不存在）—— **未默认成绿**。**两条由基线逼出的修正**：① **C3 的口径改了**（见上表）—— 原断言"同帧读 DOM 已含该字符"对 legacy 也成立（它同任务内同步写 DOM），**不具区分力** ⇒ 判据改为 `beforeinput.defaultPrevented === false`；② 记录一条**应用侧潜在缺陷**：增量重渲 `reRenderBlock → renderRange` 会**换掉块节点**，而行数不变时 `keepLineMap` 会**跳过 `stampBlockLines`** ⇒ 被编辑块节点**瞬时不带 `data--src-line`**（探针读取需用编辑前捕获的行号）。**环境事实**：驱动 = **Node 24 内置 `WebSocket`/`fetch` 直连 Edge CDP**（`scripts/benchmark/surface/cdp.mjs`），**零新依赖**；`selenium` 因本机网络受限未用 |
| 2026-09-28 | 初稿：两层（RenderCore / EditSurface）+ 双插头协议 + 时序契约（flush 清单 F1–F8）+ 冻结规则 + 契约测试 C1–C12 + 不承诺清单。**未施工** |
