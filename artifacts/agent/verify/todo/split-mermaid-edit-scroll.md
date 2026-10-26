# 分栏模式编辑 mermaid：预览刷新把源码区抢滚（块顶对齐）— 根因 + 修复

> 人补充：「你得用很长的源码区域 mermaid，在中间编辑才会看到源码的 **跳**」。
> 本轮夹具正是：**932 行 / 454 块的长文档**，mermaid 在**中段 line 605**，光标放到源码视口**中间（45%）**编辑。
> 短文档（133 行 / 65 块）实测**不复现** —— 只有块数 ≥ `LAZY_MIN_BLOCKS=200` 走惰性预览路径时才会每敲一字重演（见 §2）。

---

## 0. 结论
1. **具体是 `_onSplitPaneScroll("preview")` → `_scrollToSrcLine("source", 预览顶行)` 在滚源码区**：
   预览整篇重渲时被清空/插入「渲染中」，浏览器把 `previewPane.scrollTop` 夹到 0，随后
   `_restorePreviewScrollAnchor` 写回旧位置 —— 这两次**程序化** scroll 事件被当成「用户滚动预览」，
   于是反向同步把源码区对齐到「预览顶行 = 当前 mermaid 块顶部」。
2. **「刷一下」与「定位到顶」是同一根因**（本次实测范围内）：
   - 源码区**没有**整体重建：`#editor` 的 childElementCount 全程 932 不变，24 次输入只产生 24 个
     `characterData` mutation（无 childList/无 innerHTML 重建）；因此源码区没有"白屏闪"。
   - 真正看到的是 **scrollTop 被 JS 改写**（滚动条/正文整体位移），也就是"刷"的来源；
     而写它的就是上面那条「预览→源码」定位同步。预览自己确实整篇重建（~46k mutation），
     但那是预览侧，不是源码侧。
3. 修复：**源码编辑触发的整篇预览重渲窗口内，禁止分栏反向同步**（`_previewRenderInFlight` 计数），
   并把锚点恢复/漂移补偿这些程序化滚动标记为 split 回声。非编辑态的「跟随滚动」完全不动（实测双向往返正常）。
4. 修复后真机：**长源码 + mermaid 居中编辑，连续 24 字符，源码区 scrollTop 24 次采样完全不变**；
   预览正常刷新（mermaid 图新增节点、svg 长度 +1694）；普通段落/代码块/公式块/表格同样稳定。

---

## 1. 证据：谁在滚（RED，修复前 HEAD 01a2d3c8 + 同一夹具/探针）
产物：`artifacts/agent/verify/todo/split-mermaid-edit-scroll-before.json` / `.log`
探针：`split-mermaid-edit-scroll-verify.mjs`（真机 WebView2，真实 app.js；控制台 PID 48812 前后一致）。

```
mermaid 段（centered：块顶 line605 滚到视口顶部后，光标行放视口 45%）
before: epScroll=18708, sourceTop=603, previewTop=603
逐字符 24 次输入：epSeries = [18690, 18690, … 18690]  ← 第一字就被改成块顶
epMoved = true

sourceScrollSets 唯一一条（JS 赋值，带调用栈）：
  editor-pane scrollTop 18708 → 18690
  栈：
    at HTMLDivElement.set [as scrollTop]
    at _scrollToSrcLine (app.js:2532)
    at _onSplitPaneScroll (app.js:2383)
    at HTMLDivElement.<anonymous> (app.js:2401)   ← preview-pane 的 scroll 监听
```

同一探针在早先「块顶对齐」场景（更长的 mermaid 内容、块顶贴着视口）还抓到更大跳变：
`epSeries=[18942×6, 19142, 19131, …]`（第 7 字 **+200px**），`sourceScrollSets` 同样来自
`_scrollToSrcLine ← _onSplitPaneScroll("preview")`。→ **同一条函数链**。

### 候选逐个排除
| 候选 | 结论 | 证据 |
|---|---|---|
| (a) 编辑→预览「把编辑块滚到可视区」 | ❌ 非本跳变来源。E26 `_keepCaretVisible` 只做"越界才补最小差值"，在贴边场景实测仅 6px；本跳变栈是 `_scrollToSrcLine`。 | RED `sourceScrollSets` 栈；E26 只在 `_keepCaretVisible` 栈中出现 |
| (b) 预览→源码反向同步 | ✅ **元凶** | 栈：scroll 事件 → `_onSplitPaneScroll("preview")` → `_scrollToSrcLine("source", line)` |
| (c) 源码区整体重建 → scrollTop 归零再恢复 | ❌ 源码区 DOM 未重建（child count 932 恒定；mutation 全为 characterData） | MutationObserver 计数；编辑器 childElementCount |
| (d) 浏览器 scroll anchoring（原生） | ❌ 原生不会产生带 JS 栈的 scrollTop set；所有源码变化都命中 JS setter 栈 | 探针 wrap `Element.prototype.scrollTop` 的 setter |
| (e) 保存/写盘后 re-sync | ❌ 输入时间线内无 source 重置；保存不在该窗口触发 | 日志/时间线 |

### 为什么必须是"长源码区、mermaid 在中间"
- 短文档（133 行/65 块）走全量预览：重渲后 preview scrollTop 基本由浏览器保住，
  不会发生「0 → 恢复锚点」的程序化滚动 ⇒ 不触发反向同步（实测 `epMoved=false`）。
- 长文档（932 行/454 块 ≥ `LAZY_MIN_BLOCKS=200`）走惰性预览：每次 debounce 重渲都会
  `preview.innerHTML = 渲染中`（clamp 到 0）→ `_restorePreviewScrollAnchor` 写回 21100+；
  这两次 scroll 事件就是每字的"抢滚"触发源。mermaid 在中间时，预览顶行/源码顶行正好落在
  该块附近，于是源码被"块顶对齐"。

---

## 2. 修复（app.js，+20/−1）
### 2.1 重渲窗口禁止分栏反向同步（根因处）
```js
// app.js:272
var _previewRenderInFlight = 0;   // 计数，不用 boolean：重渲可能重入/排队

// app.js:387  async function _renderPreviewKeepScroll(options) {
_previewRenderInFlight++;
try { return await renderPreview(...); }
finally {
  if (anchor) { _restorePreviewScrollAnchor(anchor); _scheduleEditScrollReanchor(anchor); }
  // 恢复/清空产生的 scroll 事件在本任务之后才派发 ⇒ 多等两帧再放开（配对递减）
  requestAnimationFrame(() => requestAnimationFrame(() => {
    _previewRenderInFlight = Math.max(0, _previewRenderInFlight - 1);
  }));
}

// app.js:2392  function _onSplitPaneScroll(mode, pane) {
if (state.viewMode !== "split" || splitSyncLock) return;
if (_previewRenderInFlight > 0) return;   // ← 根因守卫：重渲窗口内不反向同步
if (_consumeSplitEcho(mode, pane)) return;
...
```
> 守卫放在 `_consumeSplitEcho` **之前**：否则清空/恢复的第一次 scroll 会把 echo 消费掉，
> 恢复位置的下一次事件仍会把源码拽走（RED 正是这个顺序）。

### 2.2 程序化滚动统一标记为回声（补漏）
- `_restorePreviewScrollAnchor` 的**元素锚点**与**裸像素兜底**两条路径，set 之后 `_markSplitEcho("preview", pane)`；
- `_scheduleEditScrollReanchor` 的 80/260/700/1500ms 漂移补偿，`pp.scrollTop += drift` 之后同样标记。
- 只影响"由代码滚动 preview"的识别，不改变用户滚动的跟随逻辑。

---

## 3. 修复后验证（GREEN，同一夹具/探针，真机）
产物：`split-mermaid-edit-scroll-after.json` / `.log`

| 项 | RED（pre-fix） | GREEN（post-fix） |
|---|---|---|
| 长源码 + mermaid 居中，24 字输入 | ep 18708→18690（第一字即跳），`sourceScrollSets=1`（`_scrollToSrcLine←_onSplitPaneScroll("preview")`） | **epSeries 24 项恒 18669**，`sourceScrollSets=[]` ✅ |
| 预览仍刷新 | previewChanged=true（+6 文本 / +1694 svg） | true；mermaid 图新增 新A/新B/新C 节点（截图） ✅ |
| 普通段落编辑 2 字 | epMoved=true（同 bug） | ep 569 恒定 ✅ |
| js 代码块编辑 4 字 | epMoved=true | ep 19133 恒定 ✅ |
| 公式块编辑 4 字 | epMoved=true | ep 19280 恒定 ✅ |
| 表格编辑 2 字 | epMoved=true | ep 19425 恒定 ✅ |
| 非编辑态：预览滚动→源码跟随 | true | **true** ✅ |
| 非编辑态：源码滚动→预览跟随 | true | **true** ✅ |

截图：
- RED：`split-mermaid-edit-scroll-screens-before/before-before.png`、`before-after-mermaid.png`
- GREEN：`split-mermaid-edit-scroll-screens/after-before.png`、`after-after-mermaid.png`、`after-after-all.png`
  （after-after-mermaid 可见：源码区停在 line 603-623 的 mermaid 附近，右侧图已出现 新A/新B/新C）

---

## 4. 门禁
- `pytest -q tests` → **1526 passed**（基线 1524 + 新增 2 例回归测试）
- 新增 `tests/test_split_preview_scroll_sync_guard.py`（55 行，2 例）：
  - 重渲窗口计数存在、`_onSplitPaneScroll` 守卫在 `_consumeSplitEcho` 之前、计数配对递减；
  - 锚点恢复/漂移补偿必须标记 split 回声。
- `node --check` 66 文件 0 失败；`i18n_selftest` PASS；`prompt_drift` FAIL=0；12 剧本 **12/12**
- `team_audit` → **FAIL=1（外部，不是本任务）**：
  `deliberation_quality: dq6 4 个辩论产物未被 git 跟踪`（kgviz PHASE3 的 4 个文件）
  —— 属其他 owner 的辩论产物，本任务未触碰；需 Lead/对应 owner 处理。
- 真机 PID 48812 前后一致；端口 9598 已释放；未写 `docs/example/**`、`Package/**`；未 commit。

---

## 5. 产物
```
artifacts/agent/verify/todo/
  split-mermaid-edit-scroll.md                 （本报告）
  split-mermaid-edit-scroll-verify.mjs         （GREEN 验证探针：mermaid 居中 24 字 + 四类回归 + 双向跟随）
  split-mermaid-edit-scroll-run.ps1            （运行器，端口 9598）
  split-mermaid-scroll-probe.mjs / run.ps1     （RED 定位探针：scrollTop setter/栈 + MutationObserver）
  split-mermaid-edit-scroll-before.json/.log   （修复前 RED 证据）
  split-mermaid-edit-scroll-after.json/.log    （修复后 GREEN 证据）
  split-mermaid-edit-scroll-screens-before/    （RED 截图）
  split-mermaid-edit-scroll-screens/           （GREEN 截图）
  split-mermaid-fixture-gen.py / split-mermaid-fixture/  （932 行长文档夹具）
```

## 6. 限制（如实）
1. 探针用 CDP `Input.insertText`（真实 input 事件路径）+ 程序化设置光标；不是物理键盘逐键，但输入事件、
   预览 debounce、渲染与滚动同步链路都是生产路径。
2. 夹具 932 行/454 块；短文档走全量路径不复现（已在报告说明阈值 200）。
3. 未做录屏；提供 RED/GREEN 截图与逐字 scrollTop 采样 JSON。
4. 本修复只挡「源码编辑触发的整篇预览重渲」窗口；其他路径（切页签/跳转/窗口 resize）的既有滚动恢复逻辑未改。
