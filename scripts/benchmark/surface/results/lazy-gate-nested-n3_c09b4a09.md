# 惰性路径交互门禁（W4.1）：nested-n3

- 时间：2026-10-23T06:13:21.753438+00:00
- commit：`c09b4a09`
- 语料：`scripts/benchmark/surface/fixtures/lazy-gate-kb/docs/lazy-gate-1600.md`（fixture 源行数 5785，标记 160 个）
- 剧本：`lazy-gate.json`
- 负向注入：无
- 批尾模式：请求 `产品默认`；运行期实测 `pred`
- 浏览器：Edg/155.0.4283.62
- 测量可信门：rAF p50 = 16.6 ms（阈值 ≤ 20 ms）⇒ 可信

## 结论：❌ FAIL（L5-edit-protect）

### 打开（惰性路径）

- 首块可见：**189 ms**（预算 500 ms）
- 首屏就绪（≥3 块且有文本）：189 ms；墙钟 189.19999999552965 ms
- 块数：3982（占位 3945 / 已物化 37）；行高 22.4 px；度量来源 `probe`；每屏约 31 块

| 检查 | 状态 | 关键读数 |
|---|---|---|
| L0-idle-raf | ✅ PASS | — |
| L1-open-first-screen | ✅ PASS | `open`={"firstVisibleMs": 189, "screenReadyMs": 189, "wallMs": 189.19999999552965, "stats": {"materialized": 37, "placeholders": 3945, "totalBlocks": 3982, "evictTotal": 0, "keepScreens":  |
| L2-positions | ✅ PASS | `drift`={"driftPx": 0, "driftLines": 0, "lineDelta": 0} `drift`={"driftPx": 0, "driftLines": 0, "lineDelta": 0} `drift`={"driftPx": 0, "driftLines": 0, "lineDelta": 0} `drift`={"driftPx": 0, "driftLines": 0, "lineDelta": 0}  |
| L3-back-to-top | ✅ PASS | `delta`={"absDeltaLines": 1.1, "lineDelta": 0}  |
| L4-long-scroll | ✅ PASS | `maxMaterialized`=127 `evictTotal`=3399  |
| L5-edit-protect | ❌ FAIL | `whileFarAway`={"exists": true, "isPlaceholder": false, "stats": {"materialized": 94, "placeholders": 3888, "totalBlocks": 3982, "evictTotal": 3587, "keepScreens": 4, "pressureScreens": 4, "evict  |

## 失败明细（定位到步骤/断言）

### L5-edit-protect

- `edit-then-evict-elsewhere` / `edit-landed`：期望 `True`，实际 `False`（受信任键盘输入必须落到已物化块里）
  - `pick`：{"blockIndex": 1994, "x": 356, "y": 162, "text": "LAZYGATE-MARK-0081 区域标记：本节用于验证大文档的惰性物化与工作集淘汰；标记行号是门禁的文本-位置对齐锚点。", "paneTop": 92, "blockTop": 151, "blockBottom": 198.6, "scrollTop": 76078, "hitTag": "P", "hitBlock": 1994, "hitPh": false}
  - `clickBefore`：{"scrollTop": 76078, "hitTag": "P", "hitBlock": 1994, "hitPh": false, "activeTag": "BODY", "activeId": null, "focusInPreview": false, "rangeCount": 0, "caretBlock": null, "caretOffset": null, "editMode": false, "hasFocus": false, "visibility": "visible", "contentEditable": "false", "pickedExists": true, "pickedPh": false, "tail": {"mode": "pred", "batches": 1, "verifies": 9, "skips": 74, "driftErrPx": 13185.6, "deferredReadMs": 10, "shCache": 156167, "predDriftPx": 0, "predTotalPx": 0.4, "wouldFix": 37, "anchorPredMax": 0.7, "driftMode": "predicted+verified"}}
  - `clickAfter`：{"scrollTop": 76078, "hitTag": "P", "hitBlock": 1994, "hitPh": false, "activeTag": "BODY", "activeId": null, "focusInPreview": false, "rangeCount": 1, "caretBlock": 1994, "caretOffset": 4, "editMode": false, "hasFocus": true, "visibility": "visible", "contentEditable": "false", "pickedExists": true, "pickedPh": false, "tail": {"mode": "pred", "batches": 1, "verifies": 9, "skips": 74, "driftErrPx": 13185.6, "deferredReadMs": 10, "shCache": 156167, "predDriftPx": 0, "predTotalPx": 0.4, "wouldFix": 37, "anchorPredMax": 0.7, "driftMode": "predicted+verified"}}
  - `clickAfter250`：{"scrollTop": 76078, "hitTag": "P", "hitBlock": 1994, "hitPh": false, "activeTag": "BODY", "activeId": null, "focusInPreview": false, "rangeCount": 1, "caretBlock": 1994, "caretOffset": 4, "editMode": false, "hasFocus": true, "visibility": "visible", "contentEditable": "false", "pickedExists": true, "pickedPh": false, "tail": {"mode": "pred", "batches": 1, "verifies": 9, "skips": 74, "driftErrPx": 13185.6, "deferredReadMs": 10, "shCache": 156167, "predDriftPx": 0, "predTotalPx": 0.4, "wouldFix": 37, "anchorPredMax": 0.7, "driftMode": "predicted+verified"}}
  - `clickAfterType`：{"scrollTop": 72823, "hitTag": "DIV", "hitBlock": 1993, "hitPh": false, "activeTag": "BODY", "activeId": null, "focusInPreview": false, "rangeCount": 1, "caretBlock": 1994, "caretOffset": 4, "editMode": false, "hasFocus": true, "visibility": "visible", "contentEditable": "false", "pickedExists": true, "pickedPh": false, "tail": {"mode": "pred", "batches": 1, "verifies": 9, "skips": 74, "driftErrPx": 13185.6, "deferredReadMs": 10, "shCache": 156167, "predDriftPx": 0, "predTotalPx": 0.4, "wouldFix": 37, "anchorPredMax": 0.7, "driftMode": "predicted+verified"}}
  - `editedBlock`：1994
  - `afterType`：{"text": "LAZYGATE-MARK-0081 区域标记：本节用于验证大文档的惰性物化与工作集淘汰；标记行号是门禁的文本-位置对齐锚点。", "has": false}
  - `selectionBefore`：{"collapsed": true, "text": "", "anchor": {"offset": 4, "blockIndex": 1994, "textLen": 63, "sample": "LAZYGATE-MARK-0081 区域标记：本节用于验证大文档的惰性物化与工作集淘汰；标记行"}, "focus": {"offset": 4, "blockIndex": 1994, "textLen": 63, "sample": "LAZYGATE-MARK-0081 区域标记：本节用于验证大文档的惰性物化与工作集淘汰；标记行"}}
  - `evictTotalBefore`：3497
  - `whileFarAway`：{"exists": true, "isPlaceholder": false, "stats": {"materialized": 94, "placeholders": 3888, "totalBlocks": 3982, "evictTotal": 3587, "keepScreens": 4, "pressureScreens": 4, "evictPressureSchedules": 67, "evictPendingSkips": 0, "suspended": false, "heightDriftPx": 35.4, "anchorFixes": 0, "fsPx": 14, "lhPx": 22.4, "metricsSrc": "probe"}, "text": "LAZYGATE-MARK-0081 区域标记：本节用于验证大文档的惰性物化与工作集淘汰；标记行号是门禁的文本-位置对齐锚点。"}
  - `selectionFarAway`：{"collapsed": true, "text": "", "anchor": {"offset": 4, "blockIndex": 1994, "textLen": 63, "sample": "LAZYGATE-MARK-0081 区域标记：本节用于验证大文档的惰性物化与工作集淘汰；标记行"}, "focus": {"offset": 4, "blockIndex": 1994, "textLen": 63, "sample": "LAZYGATE-MARK-0081 区域标记：本节用于验证大文档的惰性物化与工作集淘汰；标记行"}}
  - `back`：{"text": "LAZYGATE-MARK-0081 区域标记：本节用于验证大文档的惰性物化与工作集淘汰；标记行号是门禁的文本-位置对齐锚点。", "has": false, "isPlaceholder": false}
  - `selectionAfter`：{"collapsed": true, "text": "", "anchor": {"offset": 4, "blockIndex": 1994, "textLen": 63, "sample": "LAZYGATE-MARK-0081 区域标记：本节用于验证大文档的惰性物化与工作集淘汰；标记行"}, "focus": {"offset": 4, "blockIndex": 1994, "textLen": 63, "sample": "LAZYGATE-MARK-0081 区域标记：本节用于验证大文档的惰性物化与工作集淘汰；标记行"}}
- `edit-then-evict-elsewhere` / `edit-content-survives`：期望 `True`，实际 `False`
  - `pick`：{"blockIndex": 1994, "x": 356, "y": 162, "text": "LAZYGATE-MARK-0081 区域标记：本节用于验证大文档的惰性物化与工作集淘汰；标记行号是门禁的文本-位置对齐锚点。", "paneTop": 92, "blockTop": 151, "blockBottom": 198.6, "scrollTop": 76078, "hitTag": "P", "hitBlock": 1994, "hitPh": false}
  - `clickBefore`：{"scrollTop": 76078, "hitTag": "P", "hitBlock": 1994, "hitPh": false, "activeTag": "BODY", "activeId": null, "focusInPreview": false, "rangeCount": 0, "caretBlock": null, "caretOffset": null, "editMode": false, "hasFocus": false, "visibility": "visible", "contentEditable": "false", "pickedExists": true, "pickedPh": false, "tail": {"mode": "pred", "batches": 1, "verifies": 9, "skips": 74, "driftErrPx": 13185.6, "deferredReadMs": 10, "shCache": 156167, "predDriftPx": 0, "predTotalPx": 0.4, "wouldFix": 37, "anchorPredMax": 0.7, "driftMode": "predicted+verified"}}
  - `clickAfter`：{"scrollTop": 76078, "hitTag": "P", "hitBlock": 1994, "hitPh": false, "activeTag": "BODY", "activeId": null, "focusInPreview": false, "rangeCount": 1, "caretBlock": 1994, "caretOffset": 4, "editMode": false, "hasFocus": true, "visibility": "visible", "contentEditable": "false", "pickedExists": true, "pickedPh": false, "tail": {"mode": "pred", "batches": 1, "verifies": 9, "skips": 74, "driftErrPx": 13185.6, "deferredReadMs": 10, "shCache": 156167, "predDriftPx": 0, "predTotalPx": 0.4, "wouldFix": 37, "anchorPredMax": 0.7, "driftMode": "predicted+verified"}}
  - `clickAfter250`：{"scrollTop": 76078, "hitTag": "P", "hitBlock": 1994, "hitPh": false, "activeTag": "BODY", "activeId": null, "focusInPreview": false, "rangeCount": 1, "caretBlock": 1994, "caretOffset": 4, "editMode": false, "hasFocus": true, "visibility": "visible", "contentEditable": "false", "pickedExists": true, "pickedPh": false, "tail": {"mode": "pred", "batches": 1, "verifies": 9, "skips": 74, "driftErrPx": 13185.6, "deferredReadMs": 10, "shCache": 156167, "predDriftPx": 0, "predTotalPx": 0.4, "wouldFix": 37, "anchorPredMax": 0.7, "driftMode": "predicted+verified"}}
  - `clickAfterType`：{"scrollTop": 72823, "hitTag": "DIV", "hitBlock": 1993, "hitPh": false, "activeTag": "BODY", "activeId": null, "focusInPreview": false, "rangeCount": 1, "caretBlock": 1994, "caretOffset": 4, "editMode": false, "hasFocus": true, "visibility": "visible", "contentEditable": "false", "pickedExists": true, "pickedPh": false, "tail": {"mode": "pred", "batches": 1, "verifies": 9, "skips": 74, "driftErrPx": 13185.6, "deferredReadMs": 10, "shCache": 156167, "predDriftPx": 0, "predTotalPx": 0.4, "wouldFix": 37, "anchorPredMax": 0.7, "driftMode": "predicted+verified"}}
  - `editedBlock`：1994
  - `afterType`：{"text": "LAZYGATE-MARK-0081 区域标记：本节用于验证大文档的惰性物化与工作集淘汰；标记行号是门禁的文本-位置对齐锚点。", "has": false}
  - `selectionBefore`：{"collapsed": true, "text": "", "anchor": {"offset": 4, "blockIndex": 1994, "textLen": 63, "sample": "LAZYGATE-MARK-0081 区域标记：本节用于验证大文档的惰性物化与工作集淘汰；标记行"}, "focus": {"offset": 4, "blockIndex": 1994, "textLen": 63, "sample": "LAZYGATE-MARK-0081 区域标记：本节用于验证大文档的惰性物化与工作集淘汰；标记行"}}
  - `evictTotalBefore`：3497
  - `whileFarAway`：{"exists": true, "isPlaceholder": false, "stats": {"materialized": 94, "placeholders": 3888, "totalBlocks": 3982, "evictTotal": 3587, "keepScreens": 4, "pressureScreens": 4, "evictPressureSchedules": 67, "evictPendingSkips": 0, "suspended": false, "heightDriftPx": 35.4, "anchorFixes": 0, "fsPx": 14, "lhPx": 22.4, "metricsSrc": "probe"}, "text": "LAZYGATE-MARK-0081 区域标记：本节用于验证大文档的惰性物化与工作集淘汰；标记行号是门禁的文本-位置对齐锚点。"}
  - `selectionFarAway`：{"collapsed": true, "text": "", "anchor": {"offset": 4, "blockIndex": 1994, "textLen": 63, "sample": "LAZYGATE-MARK-0081 区域标记：本节用于验证大文档的惰性物化与工作集淘汰；标记行"}, "focus": {"offset": 4, "blockIndex": 1994, "textLen": 63, "sample": "LAZYGATE-MARK-0081 区域标记：本节用于验证大文档的惰性物化与工作集淘汰；标记行"}}
  - `back`：{"text": "LAZYGATE-MARK-0081 区域标记：本节用于验证大文档的惰性物化与工作集淘汰；标记行号是门禁的文本-位置对齐锚点。", "has": false, "isPlaceholder": false}
  - `selectionAfter`：{"collapsed": true, "text": "", "anchor": {"offset": 4, "blockIndex": 1994, "textLen": 63, "sample": "LAZYGATE-MARK-0081 区域标记：本节用于验证大文档的惰性物化与工作集淘汰；标记行"}, "focus": {"offset": 4, "blockIndex": 1994, "textLen": 63, "sample": "LAZYGATE-MARK-0081 区域标记：本节用于验证大文档的惰性物化与工作集淘汰；标记行"}}

## 口径与限制

- 「首块可见」= `openFile()` 返回到首个已物化块进入视口（rAF 轮询），不含 MathJax 全量排版完成。
- 「相对漂移」= 同一锚点块在 settle 前后相对视口的屏幕位移 ÷ 实测行高；「绝对位置」= 回顶后首块相对视口顶偏移 ÷ 行高。
- 「DOM ≤ 视口×8」按**同时存在的块数**（含占位）计，视口块数 = `ceil(pane.clientHeight / 实测行高)`；另报告 `#preview` 节点数。
- 堆读数是 Chromium `performance.memory.usedJSHeapSize`（非进程 RSS）；采样前尽量 `gc()`，仍受引擎 GC 时机影响。
- 本门禁跑在**无头 Edge harness**（与 12 剧本同一条 CDP 路径），不是真机 pywebview；真机首开读数另测。
