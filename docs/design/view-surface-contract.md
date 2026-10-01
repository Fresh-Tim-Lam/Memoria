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
