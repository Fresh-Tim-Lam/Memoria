# K5 实现方案：底层渲染重构（预览区）

> **状态**：2026-09-28 初稿，**待拍板，未施工**。
> **这份文档是什么**：K5a / K5b / K5c 的**实施步骤**（逐文件、逐函数、可回滚、可验收）。
> **这份文档不是什么**：不是设计论证（论证与调研出处见 [preview-render-pipeline.md §3.9](preview-render-pipeline.md)），也不是事实源（状态仍在 [todo.md §13](../todo.md) 与 [docs-management.md §4.2](../conventions/docs-management.md)）。
> **来源**：人「我们先不管（打字当帧），先 commit 当前版本，然后我们**着手关于窗口化渲染的研究和底层渲染重构**」+ 评审追问（对称性 / 复杂度 / 高度账本）。

---

## 0. 一句话

把「**谁在打字那一刻写 DOM**」还给浏览器，把「**位置↔像素**」交给一张高度账本，最后才谈窗口 —— 窗口化是这两件的**附属品**，不是先行件。

| 期 | 内容 | 需要窗口化吗 | 治什么 |
|---|---|---|---|
| **K5a** | 输入所有权反转 + 块内 DOM 复用 + 热路径去 O(文档) | **不需要** | 「打字不是当帧出现」 |
| **K5b** | 高度账本（估算先行 + 实测回填 + 前缀和增量） | **不需要** | 「跳转/切模式落点漂」 |
| **K5c** | 视口化（CM6 式 `viewport`） | 是（它的正题） | 「大文档滚动/冷渲染」 |

---

## 1. 三个口径先对齐

### 1.1 「预览—源码对称」对称在哪、不对称在哪（评审问题 ①）

**对称的是结果**（两侧内容互为镜像）：源码改 → 预览同步；预览改 → 源码同步。这一点现在的实现就是这样，不动。

**不对称的是"打字那一刻谁写 DOM"**：

| | 源码区（`.-line-content`） | 预览区（`.-src-block` 内的 inline） |
|---|---|---|
| DOM 形态 | **纯文本行**（一行一个元素，没有 inline 结构） | **结构化**（段落/标题/列表/`<strong>`/`<code>`/MathJax 容器） |
| 我们现在怎么做 | **从不 `preventDefault`** —— 浏览器原生敲，我们只在 `input` 上（80 ms 防抖）重读文本 | **`preventDefault`** 一切，路由到 AST 管线自己改 DOM |
| 为什么不同 | 原生编辑**破坏不了**它的结构（它没有结构） | 原生编辑**会破坏**结构：把 `<strong>` 删一半、跨块删除、把块拆开 |

⇒ 「对称」的正确读法是：**预览侧向源码侧看齐（能不拦就不拦），但只在"拦不拦都不破坏结构"的范围内**。那个范围恰好是：

- ✅ **`insertText`**（纯插入，插在哪就是光标处）—— **反转**（本方案 A1）
- ❌ **`deleteContentBackward` / `deleteContentForward`** —— 可能跨块合并 / 拆块，读回要处理块合并语义 ⇒ **继续拦**
- ❌ **`insertParagraph`** —— 结构性（拆段），**继续拦**
- ❌ **`insertCompositionText`** —— 规范规定**不可取消**（Chrome 实测 `e.cancelable === false`）；而且我们现在**本来就放行**，只在 `compositionend` 提交

> 结论（R12）：**只反转 `insertText`**。理由不是"复杂度低"，而是**只有它在"对称"与"不破坏结构"之间同时成立**。
> 附带收益：反转后，**预览区与源码区的打字口径一致**（都是原生先写、我们后同步）—— 这才是你说的对称。

### 1.2 块内复用：方案 ① vs ② 的**算法时间复杂度**（评审问题 ②）

> 人澄清：「我说的复杂度是**算法时间复杂度**不是实现难度」⇒ 本节按复杂度重写（原先答的是"实现量"，那是次要判据）。

先定义：`n` = 该块内 inline 节点数，`m` = 该块的 markdown 字符数（≈ 文本长度），`d` = 本次改动碰到的字符数（打字时 `d = 1`），`N` = 全篇字符数。

| 成本项 | ① 同类型块只改文本节点 | ② inline 文本级 diff（利用"模型已知改动"） |
|---|---|---|
| 结构判定 | **Θ(n)** —— 要比对新旧 inline 序列（读两边） | **Θ(d)** —— 改动是本模块自己算出来的，**不需要判定**（Lexical 那条口径："它知道自己改了什么"） |
| DOM 写入 | Θ(n) → **加"值没变就不写"守卫后降到 Θ(d)** | Θ(d) —— 只写变化的那几个文本节点 |
| 本块 markdown 生成 | **Θ(m)** —— 两边共同的**下界**（`G.generateBlock(block)`，源码面板要用它） | 同 |
| **块内小计** | Θ(n + m) → 加守卫后 **Θ(d + m)** | **Θ(d + m)** |
| 外层（两者都要付） | **Θ(N)**：`spliceBlockSource()` 每键整篇 `split`/`join`（`app.js:7699-7708`） | 同 |

**答案**：**② 的算法时间复杂度严格更低一阶** —— ① 的判定是 Θ(块大小)，② 是 Θ(改动量)。

**但它在本仓当前形态下不构成瓶颈，三条理由**：

1. **有共同下界 Θ(m)**：每次按键都要 `G.generateBlock(block)` 出本块 markdown（源码面板要用）⇒ 块内阶数差只决定**下界之上还剩多少**，不影响下界本身。
2. **① 加一句守卫就抹平写入项**：`if (node.nodeValue !== v) node.nodeValue = v;` ⇒ ① 的写入量也掉到 Θ(d)，只剩"判定是 Θ(n) 次**读**"（读 `nodeValue` 比写便宜约一个量级）。**加上这一句之后，① 与 ② 同阶。**
3. **更外层还挂着 Θ(N)**：`spliceBlockSource()` 每键 `state.doc.body.split("\n")` + `join("\n")` 是 **Θ(全篇)**（§2 A3 的靶子）。**Θ(N) 没拿掉之前，块内 Θ(n) 与 Θ(d) 的差不是瓶颈。**

⇒ **选 ① 的理由不是"实现简单"，而是"在 Θ(N) 还挂着的时候，先付 ② 的复杂度不划算"。**
⇒ **什么时候改选 ②**：A0 的读数若显示"**重渲块**"那一段才是大头（而不是"锚点 / 源码 / 脏标记"），说明 Θ(N) 已不是瓶颈、块内项浮上来 ⇒ 那时改 ②（再往下甚至要动"增量 markdown 生成"，因为 Θ(m) 是硬下界）。

> **实现量**（① ~40 行 / ② ~200+ 行）是**次要判据**，不构成决策依据 —— 上面那张表才是答案。

### 1.3 什么是「高度账本」（评审问题 ③）

**定义**：一张表，**每块一行** —— `{blockIndex, srcStart, srcEnd, estHeight, realHeight?}`。
`estHeight` 由**块类型 + 文本长度**估算（CM6 `HeightOracle.heightForLine()` 的思路）；实测后写 `realHeight` 并**只重算失效点之后的前缀和**（Monaco `CustomLine.prefixSum` 的朴素做法）。

**它解决三件事**：

1. **总高** ⇒ 滚动条长度（不用把整篇挂进 DOM 也能有正确的滚动范围）；
2. **位置 ↔ 像素双向换算** ⇒ 跳转落点 / `scrollIntoView` / `_getViewTopSrcLine` / `_restorePlainPosition`；
3. **高度变化后补 `scrollTop`**（滚动锚定）⇒ 这是"上下飘"的正解。

**为什么现在必需**：MathJax 排版与懒加载图片都是**后到**的 ⇒ 你量到的高度**不是最终高度**（AG104 那次"二次校准"就是在给这个打补丁）。
**"持久化"的含义**：把实测高度存盘（`<kb>/.memoria/cache/**`，`AGENTS.md §1` 的"可再生缓存"），下次打开同一文档不必重新量、不跳动。
> **2026-09-28 人审：「可以有」** ⇒ 本节的**高度账本（K5b）方向确认**，R14 先按"内存 only"做。

---

## 2. K5a：输入所有权反转 + 块内复用 + 去 O(文档)

### A0（**第一步，必须先做**）：先取数，别猜

**为什么**：我在 §3.9 ⑤ 列的 7 笔成本，是**代码事实**（都带行号，可复核），但**"每笔占多少毫秒"没有实测**。凭猜去优化就是"堆积错误"。

**怎么做**：把 `commit()` 里那条 `[EDIT] 按键提交 Xms`（`app.js:8188`，现在只在 > 20 ms 时打）拆成 5 段，仍然只在 > 20 ms 时打：

```
[EDIT] 38ms = 锚点 4 · 源码 12 · 重渲块 9 · 光标 3 · 脏标记 10   （行 1→1 · 块 812 · 全篇 5900 行）
         ↑         ↑          ↑           ↑         ↑
    syncFromSelection  spliceBlockSource  reRenderBlock  restoreCursor  markDirty
                       + patchEditorLines
```

- 落点：`edit-handler.js` 的 `bindBeforeInput`/`bindComposition` 记 `t0`，`commit()` 内部五处打点。
- **产物**：真机在 5900 行文档上打十来个字，把 `[EDIT]` 行发回来。
- **出口**：据此决定 A3 里"做哪几笔"（**很可能只做 1–2 笔，甚至一笔都不用做**）。
- **不做这一步的后果**：A3 会变成"我猜哪笔贵就改哪笔"。

### A1：预览区 `insertText` 反转（**核心**）

**现状**（`edit-handler.js:822-866`）：`insertText` 也走 `e.preventDefault()` + `EditSync.insertText(arg)` ⇒ **字符要等我们改完 DOM 才画出来**。

**改成**：

```js
// edit-handler.js bindBeforeInput（只列 insertText 这一支）
if (inputType === "insertText") {
  if (!e.data) return;
  // ① 记录"插入点"的 AST 坐标（此刻 DOM 还没变，锚点最准）
  if (!EH.dockAfter) syncFromSelection("beforeinput");
  // ② 锚点不合法（不在可编辑块上 / 停在不可编辑块边界）⇒ 退回老路（拦 + 自己改）
  if (!EH.cursorAST || EH.dockAfter) { e.preventDefault(); EditSync.insertText(e.data); return; }
  // ③ **不 preventDefault** ⇒ 浏览器原生插入（当帧可见）
  EditSync.acceptNativeInsert(e.data, EH.cursorAST);
  return;
}
```

`app.js` 的 `MemoriaEditSync` 新增两个出口（与既有 `_scheduleBlockRepaint` 同族）：

```js
var _pendingNative = null, _nativeAfterPaint = 0;
function acceptNativeInsert(text, anchor) {           // 只排队，不当刻改 AST
  if (!_pendingNative) _pendingNative = { text: "", anchor: cloneCursor(anchor) };
  _pendingNative.text += text;                        // 一拍内连敲多次 ⇒ 合并成一次
  if (_nativeAfterPaint) return;
  _nativeAfterPaint = requestAnimationFrame(function () {          // rAF 在"绘制前"跑
    _nativeAfterPaint = setTimeout(flushPendingSync, 0);           // setTimeout 在"这一帧画完之后"跑
  });
}
function flushPendingSync() {                          // ★ flush 清单里的每个入口都要调它
  if (_nativeAfterPaint) { cancelAnimationFrame(_nativeAfterPaint); clearTimeout(_nativeAfterPaint); _nativeAfterPaint = 0; }
  var p = _pendingNative; if (!p) return;
  _pendingNative = null;
  var EH = window.MemoriaEditHandler;
  if (EH) EH.cursorAST = p.anchor;                     // 用拍前记下的锚点
  insertText(p.text, true /*forceGroup*/, true /*nativeDone*/);
}
```

**时序**（这是"当帧出现"的全部秘密）：

```
任务1  beforeinput（我们只记锚点、不 preventDefault）
        → 浏览器把字写进 DOM          ← 此刻 DOM 已对
        → input 事件
──────── 任务1 结束 ⇒ 浏览器 style/layout/paint ★ 字符在这一帧画出来（我们没挡它）
帧开始  rAF
帧绘制  下一帧的 paint（我们的同步还没跑）
任务2  setTimeout(0) → flushPendingSync()
        → AST 更新 + 源码面板 patchEditorLines + 脏标记
        → commit(nativeDone=true) ⇒ 只推迟"渲染态归一"（180 ms 停手后）
```

**四条必须同时成立的护栏**：

1. **组合中不排队**：`EH._composing` 为真时 `beforeinput` 早就 return 了（既有逻辑），`flushPendingSync()` 也要在 `_composing` 时**直接把待办交给 `compositionend`**（不自己 flush）；
2. **结构性转换要当刻画**：`insertText()` 里的 `convertStructuralBlock()`（`# ` → 标题）**会改块类型**，此时"DOM 是原生结果"这个前提破了 ⇒ `insertText` 里比对 `block.type` 前后是否变化，**变了就强制走 `nativeDone=false` 的当刻重渲**（否则那 180 ms 里 DOM 是段落、AST 是标题，`domToAst` 会漂）；
3. **原生路不动选区**：`nativeDone=true` 时 `commit()` **不要**调 `restoreCursor()` 的"设 Range"那半截，只更新 `EH.cursorAST`（浏览器已经把光标放对了；`sel.removeAllRanges()+addRange()` 反而会打断下一次 IME）；
4. **flush 清单（白名单）**—— 下列入口**执行前必须先 `flushPendingSync()`**；清单漏一处就是"AST 落后 DOM"⇒ 编辑错位：
   - `MemoriaEditSync` 的**每个**出口：`insertText` / `insertParagraph` / `backspace` / `deleteForward` / `deleteSelection` / `commitRange` / `applySnapshot`(undo/redo) / `commitSelection` / `revertBlock` / `flushRepaint`
   - `getEditContext()`（所有编辑的公共前置）
   - `markDirty()` 之前（写盘读的是 `state.doc.body`）
   - `setViewMode()` / `openFile()` / `activateTab()`（切模式/换文件会 `collectEditorBody()` + 整篇重渲）
   - `_previewCacheStash()` / `_previewCacheRestore()`（缓存里存的必须是已同步的 DOM）
   - `scheduleEditorRangesResolve()` 的定时器回调（它 `collectEditorBody()` 后发给后端）
   - `beforeinput` 的非 insertText 分支（backspace/enter/delete：它们要基于最新 AST 算）
   - `bindComposition` 的 `compositionstart`（组合开始前要把 pending 落定）
   - `selectionchange` / `mouseup`（光标移动 ⇒ 锚点语义变了）
   - `keydown` 的 Ctrl+Z/Ctrl+Y（undo/redo 前）
   → **对策**：把 `flushPendingSync()` 做成**幂等 + 极便宜**（无待办时一个 `if` 就返回），然后**逐个入口加**；再写一个开发期自检：`getEditContext()` 里若 `_pendingNative` 非空就直接 `console.error("漏 flush")`（把"漏掉清单"变成一条看得见的报错，而不是静默错位）。

**验收**：真机"打字当帧出现"＝**是**（预览区直输 ASCII 与中文 IME 各一次）；`ada⏎啊SD…` 行首退格仍正确；`pytest` 不掉。
**回滚**：`localStorage["-native-typing"]="0"` ⇒ `acceptNativeInsert` 直接转 `insertText(text, false, false)`（= 回到 AG105 的行为）。

### A2：块内 DOM 复用（R13 → 选 ①）

**现状**：`reRenderBlock()` → `R.renderRange(_doc, i, i+1, container)` **整块替换**（换掉该块的整个 DOM 子树，含 MathJax 容器）。

**改成**：`R.renderRange()` 前置一步"同构则只改文本节点"：

- 取旧块元素 `old` 与新块 HTML；
- **判据**：`block.type` 相同 **且** inline 子节点类型序列相同（`text/bold/italic/code/link/wikilink/...`，MathJax 容器视为"同"）；
- 成立 ⇒ 走**只改文本节点与属性**的快路（`nodeValue` / `href` / `class`），**不建元素、不换元素**；
- 不成立（类型变了 / 结构变了）⇒ 退回现在的整块替换。
- MathJax 容器：同构时**保留**该子树（不改它），只在"公式内容真的变了"时让它整块重建。

**收益**：DOM 元素替换数从"整块"降到 **0** ⇒ 不再触发该块的 reflow/paint 级联，也不会把光标所在的文本节点换掉。
**验收**：`pytest` 新增钉子（同构 ⇒ 元素引用不变；异构 ⇒ 元素被替换）。
**风险**：判据写松了会把"该重建的"判成"同构" ⇒ 视图与 AST 分叉。**对策**：判据只允许"文本内容差异"，任何结构差异一律整块重建（保守优先）。

### A3：热路径去 O(文档)（**按 A0 的读数选择性做**）

候选（**从 A0 读数里挑真正贵的那 1–2 笔做**，不要一次全做）：

| 候选 | 改法 | 注意 |
|---|---|---|
| `spliceBlockSource()`（`app.js:7699`） | `state.doc.lines` **原地 `splice`**（不重建数组）；`state.doc.body` 改成**惰性重建** | ⚠️ **undo 快照**存的是 `state.doc.body`（`recordUndo`）—— 若 `lines` 改成原地 splice，快照就不能再握数组引用；body 仍需在**推快照时**重建一次（`join`）。**所以这一笔的净收益 = 省掉"split + concat + 数组分配"，只保留 join**，是否值得看 A0 读数 |
| `logCursorContext()`（`edit-handler.js:522`） | 加开关**默认关**（`localStorage["-ctx-debug"]`）；或改成"只在锚点不合法时打" | 它每次按键都做 `document.querySelector('.-src-block[data--block-index="N"]')`（**全篇属性选择器扫描**）+ TreeWalker + 块文本拼接 + 两条日志字符串拼接 —— **纯白工**，是 7 笔里最没道理的一笔 |
| `restoreCursor()`（`app.js:7743`） | 原生路只更新 `EH.cursorAST`（见 A1 护栏 3）；非原生路保留 | 顺带去掉"每键 `sel.removeAllRanges()+addRange()`"这个 IME 风险点 |

**验收**：A0 那五段读数里，被改的那一段显著下降；总时长 ≤ 8 ms。

---

## 3. K5b：高度账本（**不需要窗口化也吃一半收益**）

**新建** `src/memoria/ui/static/app/js/block-metrics.js`（**纯函数**，可 `node` 直跑断言）：

```js
// 账本 = 每块一行；estHeight 是估算，realHeight 是实测（可缺）
{ blockIndex, srcStart, srcEnd, estHeight, realHeight? }
```

- `estimate(block)`：按块类型给基线（heading 1–6 / paragraph / list / code / table / math_block / mermaid / blank）+ 文本长度折算（`HeightOracle.heightForLine()` 的思路）；
- `prefixSums(ledger)`：前缀和（块 → 文档内 top）；`invalidate(fromIndex)` 只重算失效点之后；
- `atHeight(y)` / `atSrcLine(line)` / `topOf(blockIndex)`：**位置 ↔ 像素双向**；
- `applyMeasured(index, height)`：回填实测 + 只重算其后前缀和 + **返回该块 top 的变化量**（交给调用方补 `scrollTop`）。

**接线（先只换"落点"，不动 DOM 所有权）**：

| 现有函数 | 现在怎么做 | 改成 |
|---|---|---|
| `_getViewTopSrcLine(mode)`（`app.js:1690`） | 从容器 top 起 **逐块 `getBoundingClientRect` 探** | 查账本 `atHeight(scrollTop)` |
| `_scrollToSrcLine(mode, line)`（`app.js:1717`） | 找到目标块再 `getBoundingClientRect` 差值 | `scrollTop = ledger.topOf(block) - 容器偏移` |
| `_restorePlainPosition()` | 按源码行定位（同款逐块探） | 同上 |
| **`_reanchorJumpScroll()`（AG104）** | 事后 ~350 ms / ~1.4 s **再对准两次** | **可以撤掉** —— 落点由账本保证；账本在实测回填时**补 `scrollTop`** |

**落点**：内存 only（R14 推荐）；持久化到 `<kb>/.memoria/cache/**` 是可选项（`AGENTS.md §1` 的"可再生缓存"）。
**验收**：5900 行文档上跳转 / 切模式落点**不漂**（判定口径：跳完读"首屏第一块的 `data--src-line`"应命中目标行 ±1）；`block-metrics.js` 有 node 单测（估算/实测自洽 + 前缀和失效点重算正确）。

---

## 4. K5c：视口化（窗口化的正确形态）

**前置条件（硬门槛）**：K5a + K5b 都已落地并取证。**未成立不许开工**（K4a 就是在缺配套件的情况下一路翻车的）。

在 K5b 的账本之上，把"窗口"做成 CM6 式 `viewport`：

| 件 | 规则 |
|---|---|
| **视口** | `viewport = 可见区 ± Margin`，**必须包住可见区** |
| **迟滞** | `viewportIsAppropriate()` 式：可见区**快撞到窗口边缘**、或窗口比需要的大出 2×Margin，才重算；`bias` 让缓冲带**朝滚动方向倾斜** |
| **窗口移动** | **只处理两端进出的块**（Monaco `ViewLayerRenderer`），**不重建整窗** |
| **滚动锚定** | 顶部锚点块 + 文档内 top，**每轮统一补偿一次** `scrollTop`；滚到底不补 |
| **定位** | **先查账本**（`getViewport(bias, scrollTarget)`），**禁止"先物化再量"** |
| **光标/选区** | composition 与光标所在块**永不摘走**；主选区不在窗口内 ⇒ **为其额外建单行窗口** |
| **禁止** | **不做"过渡终点整篇物化"**（CM6 只有 `printing` 才关窗口化） |

**"谁拥有 DOM"**：K5a 已经答了 —— **模型拥有结构、浏览器拥有当帧输入**（与 CM6 同构）。这是开工前必须先写在文档里的那一句（§3.8 ④-2 要求的）。
**验收（三条同时成立，缺一不算）**：真机 **滚动流畅 + 编辑不卡 + 跳转准**；**且设置里能一键关掉回到整篇渲染，关掉不改变正确性**（AG96 逃生门口径）。
**默认值**：先**默认关**，人肉开关跑一周无事故再切默认开。

---

## 5. 逐期验收与回滚

| 期 | 验收（可跑） | 回滚 |
|---|---|---|
| **K5a-A0** | `[EDIT]` 五段读数落到真机日志 | —（只加读数，不改行为） |
| **K5a-A1** | 真机"当帧出现＝是"（ASCII + 中文各一次）；`ada⏎…` 行首退格正确；`pytest` 不掉 | `localStorage["-native-typing"]="0"` |
| **K5a-A2** | 新钉子：同构 ⇒ 元素引用不变；异构 ⇒ 重建 | 常量开关 `RENDER_REUSE_INLINE` 置 `false` |
| **K5a-A3** | A0 读数里被改的那段下降；总时 ≤ 8 ms | 逐笔独立，各自 revert |
| **K5b** | 跳转/切模式落点不漂（±1 行）；`block-metrics.js` node 单测 | 落点函数逐个换回"逐块探" |
| **K5c** | 三条同时成立 + 关掉不改变正确性 | 设置开关（默认关） |

**全程红线**（来自既有教训，不许再犯）：
- 不许"先物化再量"；不许"整篇物化"；不许在**半所有权**状态下推进窗口化；
- 任何一期失败 ⇒ **整体回退该期**，不在上面打补丁（AG97 的教训）。

---

## 6. 待拍板汇总

| ID | 问题 | 推荐 | 理由 |
|---|---|---|---|
| **R12** | 输入所有权反转的范围 | **只 `insertText`** | 见 §1.1：只有它在"对称"与"不破坏结构"之间同时成立 |
| **R13** | 块内复用判据 | **① 同类型只改文本节点**（+ 必须带"值没变就不写"守卫） | 见 §1.2：**复杂度上 ② 更低一阶（Θ(d) vs Θ(n)）**，但共同下界 Θ(m) 与更外层的 Θ(N) 使它当前不构成瓶颈；**A0 读数若显示"重渲块"为大头 ⇒ 改选 ②** |
| **R14** | 高度账本持久化 | **内存 only**（先） | 先简单；持久化留下的是一致性问题。**2026-09-28 人审 §1.3：「可以有」** ⇒ 高度账本（K5b）方向确认 |
| **R15** | "谁拥有 DOM" | **模型拥有结构、浏览器拥有当帧输入** | 与 CM6 同构；K5c 的开工前提 |

## 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-28 | 初稿：K5a（A0 取数 / A1 输入所有权反转 / A2 块内复用 / A3 去 O(文档)）+ K5b（高度账本 `block-metrics.js`）+ K5c（视口化）+ 逐期验收与回滚 + R12–R15 汇总。**未施工** |
| 2026-09-28 | **按人澄清重写 §1.2**：「我说的复杂度是**算法时间复杂度**不是实现难度」。改为按 `n`（块内 inline 节点数）/ `m`（本块 markdown 字符数）/ `d`（本次改动字符数）/ `N`（全篇字符数）逐项列复杂度：**② 严格更低一阶**（判定 Θ(d) vs ① 的 Θ(n)）；但 ① 加"值没变就不写"守卫后写入量同为 Θ(d) ⇒ **同阶**；且两者共同下界 Θ(m)、外层还挂着 Θ(N) ⇒ ① 是本形态下的合理选择，**A0 读数若显示块内是大头则改选 ②**。R13 行同步 |
| 2026-09-28 | **人审 §1.3：「可以有」** ⇒ **高度账本（K5b）方向确认**（R14 先按"内存 only"）。§1 三问至此收口：① 对称性（R12）/ ② 复杂度（R13）/ ③ 高度账本（R14 方向）|
