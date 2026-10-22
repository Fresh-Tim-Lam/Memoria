# 惰性路径交互门禁（W4.1）：ver-neg-noevict

- 时间：2026-10-22T17:20:52.560406+00:00
- commit：`95356e57`
- 语料：`scripts/benchmark/surface/fixtures/lazy-gate-kb/docs/lazy-gate-1600.md`（fixture 源行数 5785，标记 160 个）
- 剧本：`lazy-gate.json`
- 负向注入：noevict
- 批尾模式：请求 `产品默认`；运行期实测 `pred`
- 浏览器：Edg/155.0.4283.62
- 测量可信门：rAF p50 = 16.6 ms（阈值 ≤ 20 ms）⇒ 可信

## 结论：❌ FAIL（L4-long-scroll, L5-edit-protect）

### 打开（惰性路径）

- 首块可见：**117.5 ms**（预算 500 ms）
- 首屏就绪（≥3 块且有文本）：117.5 ms；墙钟 118.69999999925494 ms
- 块数：3662（占位 3629 / 已物化 33）；行高 22.4 px；度量来源 `probe`；每屏约 31 块

| 检查 | 状态 | 关键读数 |
|---|---|---|
| L0-idle-raf | ✅ PASS | — |
| L1-open-first-screen | ✅ PASS | `open`={"firstVisibleMs": 117.5, "screenReadyMs": 117.5, "wallMs": 118.69999999925494, "stats": {"materialized": 33, "placeholders": 3629, "totalBlocks": 3662, "evictTotal": 0, "keepScree  |
| L2-positions | ✅ PASS | `drift`={"driftPx": 0, "driftLines": 0, "lineDelta": 0} `drift`={"driftPx": 0, "driftLines": 0, "lineDelta": 0} `drift`={"driftPx": 0, "driftLines": 0, "lineDelta": 0} `drift`={"driftPx": 0, "driftLines": 0, "lineDelta": 0}  |
| L3-back-to-top | ✅ PASS | `delta`={"absDeltaLines": 1.1, "lineDelta": 0}  |
| L4-long-scroll | ❌ FAIL | `maxMaterialized`=3662 `evictTotal`=397  |
| L5-edit-protect | ❌ FAIL | `whileFarAway`={"exists": true, "isPlaceholder": false, "stats": {"materialized": 3662, "placeholders": 0, "totalBlocks": 3662, "evictTotal": 397, "keepScreens": 4, "suspended": true, "heightDrif  |

## 失败明细（定位到步骤/断言）

### L4-long-scroll

- `scroll-entire-document` / `eviction-ran-during-long-scroll`：期望 `>397`，实际 `397`（长滚动期间必须新增淘汰（不能只靠此前的淘汰计数））
  - `blocksPerScreen`：31
  - `domLimit`：248
  - `baseHeapMB`：34.07
  - `finalHeapMB`：34.14
  - `peakHeapMB`：35.58
  - `peakDeltaMB`：1.51
  - `retainedDeltaMB`：0.07
  - `strictlyIncreasing`：true
  - `evictTotal`：397
  - `evictDeltaDuringLongScroll`：0
  - `baseEvictTotal`：397
  - `maxMaterialized`：3662
  - `maxDomPreview`：35877
  - `maxViewportPlaceholdersDuringScroll`：0
  - `sabotage`：{"ok": true, "kind": "noevict", "made": 3606, "stats": {"materialized": 3662, "placeholders": 0, "totalBlocks": 3662, "evictTotal": 397, "keepScreens": 4, "suspended": true, "heightDriftPx": 4.4, "anchorFixes": 0, "fsPx": 14, "lhPx": 22.4, "metricsSrc": "probe"}}
  - `samples`：[{"i": 0, "scrollTop": 0, "materialized": 3662, "placeholders": 0, "evictTotal": 397, "heapMB": 34.11, "domPreview": 35877, "vpPlaceholders": 0}, {"i": 1, "scrollTop": 4338, "materialized": 3662, "placeholders": 0, "evictTotal": 397, "heapMB": 34.16, "domPreview": 35877, "vpPlaceholders": 0}, {"i": 2, "scrollTop": 8677, "materialized": 3662, "placeholders": 0, "evictTotal": 397, "heapMB": 34.2, "domPreview": 35877, "vpPlaceholders": 0}, {"i": 3, "scrollTop": 13016, "materialized": 3662, "placeholders": 0, "evictTotal": 397, "heapMB": 34.26, "domPreview": 35877, "vpPlaceholders": 0}, {"i": 4, "scrollTop": 17354, "materialized": 3662, "placeholders": 0, "evictTotal": 397, "heapMB": 34.3, "domPreview": 35877, "vpPlaceholders": 0}, {"i": 5, "scrollTop": 21693, "materialized": 3662, "placeholders": 0, "evictTotal": 397, "heapMB": 34.37, "domPreview": 35877, "vpPlaceholders": 0}, {"i": 6, "scrollTop": 26031, "materialized": 3662, "placeholders": 0, "evictTotal": 397, "heapMB": 34.4, "domPreview": 35877, "vpPlaceholders": 0}, {"i": 7, "scrollTop": 30370, "materialized": 3662, "placeholders": 0, "evictTotal": 397, "heapMB": 34.46, "domPreview": 35877, "vpPlaceholders": 0}, {"i": 8, "scroll
- `scroll-entire-document` / `eviction-not-suspended`：期望 `False`，实际 `True`
  - `blocksPerScreen`：31
  - `domLimit`：248
  - `baseHeapMB`：34.07
  - `finalHeapMB`：34.14
  - `peakHeapMB`：35.58
  - `peakDeltaMB`：1.51
  - `retainedDeltaMB`：0.07
  - `strictlyIncreasing`：true
  - `evictTotal`：397
  - `evictDeltaDuringLongScroll`：0
  - `baseEvictTotal`：397
  - `maxMaterialized`：3662
  - `maxDomPreview`：35877
  - `maxViewportPlaceholdersDuringScroll`：0
  - `sabotage`：{"ok": true, "kind": "noevict", "made": 3606, "stats": {"materialized": 3662, "placeholders": 0, "totalBlocks": 3662, "evictTotal": 397, "keepScreens": 4, "suspended": true, "heightDriftPx": 4.4, "anchorFixes": 0, "fsPx": 14, "lhPx": 22.4, "metricsSrc": "probe"}}
  - `samples`：[{"i": 0, "scrollTop": 0, "materialized": 3662, "placeholders": 0, "evictTotal": 397, "heapMB": 34.11, "domPreview": 35877, "vpPlaceholders": 0}, {"i": 1, "scrollTop": 4338, "materialized": 3662, "placeholders": 0, "evictTotal": 397, "heapMB": 34.16, "domPreview": 35877, "vpPlaceholders": 0}, {"i": 2, "scrollTop": 8677, "materialized": 3662, "placeholders": 0, "evictTotal": 397, "heapMB": 34.2, "domPreview": 35877, "vpPlaceholders": 0}, {"i": 3, "scrollTop": 13016, "materialized": 3662, "placeholders": 0, "evictTotal": 397, "heapMB": 34.26, "domPreview": 35877, "vpPlaceholders": 0}, {"i": 4, "scrollTop": 17354, "materialized": 3662, "placeholders": 0, "evictTotal": 397, "heapMB": 34.3, "domPreview": 35877, "vpPlaceholders": 0}, {"i": 5, "scrollTop": 21693, "materialized": 3662, "placeholders": 0, "evictTotal": 397, "heapMB": 34.37, "domPreview": 35877, "vpPlaceholders": 0}, {"i": 6, "scrollTop": 26031, "materialized": 3662, "placeholders": 0, "evictTotal": 397, "heapMB": 34.4, "domPreview": 35877, "vpPlaceholders": 0}, {"i": 7, "scrollTop": 30370, "materialized": 3662, "placeholders": 0, "evictTotal": 397, "heapMB": 34.46, "domPreview": 35877, "vpPlaceholders": 0}, {"i": 8, "scroll
- `scroll-entire-document` / `dom-within-8-screens`：期望 `≤248 blocks (8 × 31/screen)`，实际 `3662`（#preview 内同时存在的块数（含占位）不得超过视口×8）
  - `blocksPerScreen`：31
  - `domLimit`：248
  - `baseHeapMB`：34.07
  - `finalHeapMB`：34.14
  - `peakHeapMB`：35.58
  - `peakDeltaMB`：1.51
  - `retainedDeltaMB`：0.07
  - `strictlyIncreasing`：true
  - `evictTotal`：397
  - `evictDeltaDuringLongScroll`：0
  - `baseEvictTotal`：397
  - `maxMaterialized`：3662
  - `maxDomPreview`：35877
  - `maxViewportPlaceholdersDuringScroll`：0
  - `sabotage`：{"ok": true, "kind": "noevict", "made": 3606, "stats": {"materialized": 3662, "placeholders": 0, "totalBlocks": 3662, "evictTotal": 397, "keepScreens": 4, "suspended": true, "heightDriftPx": 4.4, "anchorFixes": 0, "fsPx": 14, "lhPx": 22.4, "metricsSrc": "probe"}}
  - `samples`：[{"i": 0, "scrollTop": 0, "materialized": 3662, "placeholders": 0, "evictTotal": 397, "heapMB": 34.11, "domPreview": 35877, "vpPlaceholders": 0}, {"i": 1, "scrollTop": 4338, "materialized": 3662, "placeholders": 0, "evictTotal": 397, "heapMB": 34.16, "domPreview": 35877, "vpPlaceholders": 0}, {"i": 2, "scrollTop": 8677, "materialized": 3662, "placeholders": 0, "evictTotal": 397, "heapMB": 34.2, "domPreview": 35877, "vpPlaceholders": 0}, {"i": 3, "scrollTop": 13016, "materialized": 3662, "placeholders": 0, "evictTotal": 397, "heapMB": 34.26, "domPreview": 35877, "vpPlaceholders": 0}, {"i": 4, "scrollTop": 17354, "materialized": 3662, "placeholders": 0, "evictTotal": 397, "heapMB": 34.3, "domPreview": 35877, "vpPlaceholders": 0}, {"i": 5, "scrollTop": 21693, "materialized": 3662, "placeholders": 0, "evictTotal": 397, "heapMB": 34.37, "domPreview": 35877, "vpPlaceholders": 0}, {"i": 6, "scrollTop": 26031, "materialized": 3662, "placeholders": 0, "evictTotal": 397, "heapMB": 34.4, "domPreview": 35877, "vpPlaceholders": 0}, {"i": 7, "scrollTop": 30370, "materialized": 3662, "placeholders": 0, "evictTotal": 397, "heapMB": 34.46, "domPreview": 35877, "vpPlaceholders": 0}, {"i": 8, "scroll

### L5-edit-protect

- `edit-then-evict-elsewhere` / `eviction-ran-elsewhere`：期望 `>397`，实际 `397`（必须先证明远处真的发生了淘汰，否则“保护”无从谈起）
  - `pick`：{"blockIndex": 1834, "x": 356, "y": 148, "text": "LAZYGATE-MARK-0081 区域标记：本节用于验证大文档的惰性物化与工作集淘汰；标记行号是门禁的文本-位置对齐锚点。", "paneTop": 92, "blockTop": 136.4, "blockBottom": 184, "scrollTop": 69783, "hitTag": "P", "hitBlock": 1834, "hitPh": false}
  - `clickBefore`：{"scrollTop": 69783, "hitTag": "P", "hitBlock": 1834, "hitPh": false, "activeTag": "BODY", "activeId": null, "focusInPreview": false, "rangeCount": 0, "caretBlock": null, "caretOffset": null, "editMode": true, "hasFocus": false, "visibility": "visible", "contentEditable": "true", "pickedExists": true, "pickedPh": false, "tail": {"mode": "pred", "batches": 0, "verifies": 1, "skips": 9, "driftErrPx": 597.6, "deferredReadMs": 0, "shCache": 147331, "predDriftPx": 0, "predTotalPx": 0, "wouldFix": 4, "anchorPredMax": 0.65, "driftMode": "predicted+verified"}}
  - `clickAfter`：{"scrollTop": 69783, "hitTag": "P", "hitBlock": 1834, "hitPh": false, "activeTag": "DIV", "activeId": "preview", "focusInPreview": true, "rangeCount": 1, "caretBlock": 1834, "caretOffset": 4, "editMode": true, "hasFocus": true, "visibility": "visible", "contentEditable": "true", "pickedExists": true, "pickedPh": false, "tail": {"mode": "pred", "batches": 0, "verifies": 1, "skips": 9, "driftErrPx": 597.6, "deferredReadMs": 0, "shCache": 147331, "predDriftPx": 0, "predTotalPx": 0, "wouldFix": 4, "anchorPredMax": 0.65, "driftMode": "predicted+verified"}}
  - `clickAfter250`：{"scrollTop": 69783, "hitTag": "P", "hitBlock": 1834, "hitPh": false, "activeTag": "DIV", "activeId": "preview", "focusInPreview": true, "rangeCount": 1, "caretBlock": 1834, "caretOffset": 4, "editMode": true, "hasFocus": true, "visibility": "visible", "contentEditable": "true", "pickedExists": true, "pickedPh": false, "tail": {"mode": "pred", "batches": 0, "verifies": 1, "skips": 9, "driftErrPx": 597.6, "deferredReadMs": 0, "shCache": 147331, "predDriftPx": 0, "predTotalPx": 0, "wouldFix": 4, "anchorPredMax": 0.65, "driftMode": "predicted+verified"}}
  - `clickAfterType`：{"scrollTop": 69783, "hitTag": "P", "hitBlock": 1834, "hitPh": false, "activeTag": "DIV", "activeId": "preview", "focusInPreview": true, "rangeCount": 1, "caretBlock": 1834, "caretOffset": 9, "editMode": true, "hasFocus": true, "visibility": "visible", "contentEditable": "true", "pickedExists": true, "pickedPh": false, "tail": {"mode": "pred", "batches": 0, "verifies": 1, "skips": 9, "driftErrPx": 597.6, "deferredReadMs": 0, "shCache": 147331, "predDriftPx": 0, "predTotalPx": 0, "wouldFix": 4, "anchorPredMax": 0.65, "driftMode": "predicted+verified"}}
  - `editedBlock`：1834
  - `afterType`：{"text": "LAZYZGATEGATE-MARK-0081 区域标记：本节用于验证大文档的惰性物化与工作集淘汰；标记行号是门禁的文本-位置对齐锚点。", "has": true}
  - `selectionBefore`：{"collapsed": true, "text": "", "anchor": {"offset": 9, "blockIndex": 1834, "textLen": 68, "sample": "LAZYZGATEGATE-MARK-0081 区域标记：本节用于验证大文档的惰性物化与工作集淘"}, "focus": {"offset": 9, "blockIndex": 1834, "textLen": 68, "sample": "LAZYZGATEGATE-MARK-0081 区域标记：本节用于验证大文档的惰性物化与工作集淘"}}
  - `evictTotalBefore`：397
  - `whileFarAway`：{"exists": true, "isPlaceholder": false, "stats": {"materialized": 3662, "placeholders": 0, "totalBlocks": 3662, "evictTotal": 397, "keepScreens": 4, "suspended": true, "heightDriftPx": 4.4, "anchorFixes": 0, "fsPx": 14, "lhPx": 22.4, "metricsSrc": "probe"}, "text": "LAZYZGATEGATE-MARK-0081 区域标记：本节用于验证大文档的惰性物化与工作集淘汰；标记行号是门禁的文本-位置对齐锚点。"}
  - `selectionFarAway`：{"collapsed": true, "text": "", "anchor": {"offset": 9, "blockIndex": 1834, "textLen": 68, "sample": "LAZYZGATEGATE-MARK-0081 区域标记：本节用于验证大文档的惰性物化与工作集淘"}, "focus": {"offset": 9, "blockIndex": 1834, "textLen": 68, "sample": "LAZYZGATEGATE-MARK-0081 区域标记：本节用于验证大文档的惰性物化与工作集淘"}}
  - `back`：{"text": "LAZYZGATEGATE-MARK-0081 区域标记：本节用于验证大文档的惰性物化与工作集淘汰；标记行号是门禁的文本-位置对齐锚点。", "has": true, "isPlaceholder": false}
  - `selectionAfter`：{"collapsed": true, "text": "", "anchor": {"offset": 9, "blockIndex": 1834, "textLen": 68, "sample": "LAZYZGATEGATE-MARK-0081 区域标记：本节用于验证大文档的惰性物化与工作集淘"}, "focus": {"offset": 9, "blockIndex": 1834, "textLen": 68, "sample": "LAZYZGATEGATE-MARK-0081 区域标记：本节用于验证大文档的惰性物化与工作集淘"}}

## 口径与限制

- 「首块可见」= `openFile()` 返回到首个已物化块进入视口（rAF 轮询），不含 MathJax 全量排版完成。
- 「相对漂移」= 同一锚点块在 settle 前后相对视口的屏幕位移 ÷ 实测行高；「绝对位置」= 回顶后首块相对视口顶偏移 ÷ 行高。
- 「DOM ≤ 视口×8」按**同时存在的块数**（含占位）计，视口块数 = `ceil(pane.clientHeight / 实测行高)`；另报告 `#preview` 节点数。
- 堆读数是 Chromium `performance.memory.usedJSHeapSize`（非进程 RSS）；采样前尽量 `gc()`，仍受引擎 GC 时机影响。
- 本门禁跑在**无头 Edge harness**（与 12 剧本同一条 CDP 路径），不是真机 pywebview；真机首开读数另测。
