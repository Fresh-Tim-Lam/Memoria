# 惰性路径交互门禁（W4.1）：recovered

- 时间：2026-10-22T18:44:38.605519+00:00
- commit：`d40e5fc8`
- 语料：`scripts/benchmark/surface/fixtures/lazy-gate-kb/docs/lazy-gate-1600.md`（fixture 源行数 5785，标记 160 个）
- 剧本：`lazy-gate.json`
- 负向注入：无
- 批尾模式：请求 `产品默认`；运行期实测 `pred`
- 浏览器：Edg/155.0.4283.62
- 测量可信门：rAF p50 = 16.5 ms（阈值 ≤ 20 ms）⇒ 可信

## 结论：✅ PASS

### 打开（惰性路径）

- 首块可见：**107.29999999888241 ms**（预算 500 ms）
- 首屏就绪（≥3 块且有文本）：107.29999999888241 ms；墙钟 108.59999999962747 ms
- 块数：3662（占位 3626 / 已物化 36）；行高 22.4 px；度量来源 `probe`；每屏约 31 块

| 检查 | 状态 | 关键读数 |
|---|---|---|
| L0-idle-raf | ✅ PASS | — |
| L1-open-first-screen | ✅ PASS | `open`={"firstVisibleMs": 107.29999999888241, "screenReadyMs": 107.29999999888241, "wallMs": 108.59999999962747, "stats": {"materialized": 36, "placeholders": 3626, "totalBlocks": 3662, "  |
| L2-positions | ✅ PASS | `drift`={"driftPx": 0, "driftLines": 0, "lineDelta": 0} `drift`={"driftPx": 0, "driftLines": 0, "lineDelta": 0} `drift`={"driftPx": 0, "driftLines": 0, "lineDelta": 0} `drift`={"driftPx": 0, "driftLines": 0, "lineDelta": 0}  |
| L3-back-to-top | ✅ PASS | `delta`={"absDeltaLines": 1.1, "lineDelta": 0}  |
| L4-long-scroll | ✅ PASS | `maxMaterialized`=113 `evictTotal`=3316  |
| L5-edit-protect | ✅ PASS | `whileFarAway`={"exists": true, "isPlaceholder": false, "stats": {"materialized": 94, "placeholders": 3568, "totalBlocks": 3662, "evictTotal": 3498, "keepScreens": 4, "pressureScreens": 4, "evict  |

## 口径与限制

- 「首块可见」= `openFile()` 返回到首个已物化块进入视口（rAF 轮询），不含 MathJax 全量排版完成。
- 「相对漂移」= 同一锚点块在 settle 前后相对视口的屏幕位移 ÷ 实测行高；「绝对位置」= 回顶后首块相对视口顶偏移 ÷ 行高。
- 「DOM ≤ 视口×8」按**同时存在的块数**（含占位）计，视口块数 = `ceil(pane.clientHeight / 实测行高)`；另报告 `#preview` 节点数。
- 堆读数是 Chromium `performance.memory.usedJSHeapSize`（非进程 RSS）；采样前尽量 `gc()`，仍受引擎 GC 时机影响。
- 本门禁跑在**无头 Edge harness**（与 12 剧本同一条 CDP 路径），不是真机 pywebview；真机首开读数另测。
