# 惰性路径交互门禁（W4.1）：ab2-base-legacy

- 时间：2026-10-22T18:44:04.274169+00:00
- commit：`d40e5fc8`
- 语料：`artifacts/_kbwork_perf_edu/教材/08_第8章_差错控制编码.md`（fixture 源行数 5879，标记 0 个）
- 剧本：`lazy-gate-4001.json`
- 负向注入：无
- 批尾模式：请求 `legacy`；运行期实测 `legacy`
- 浏览器：Edg/155.0.4283.62
- 测量可信门：rAF p50 = 16.5 ms（阈值 ≤ 20 ms）⇒ 可信

## 结论：✅ PASS

### 打开（惰性路径）

- 首块可见：**265.19999999925494 ms**（预算 500 ms）
- 首屏就绪（≥3 块且有文本）：265.2999999988824 ms；墙钟 267.09999999962747 ms
- 块数：4001（占位 3974 / 已物化 27）；行高 22.4 px；度量来源 `probe`；每屏约 30 块

| 检查 | 状态 | 关键读数 |
|---|---|---|
| L0-idle-raf | ✅ PASS | — |
| L1-open-first-screen | ✅ PASS | `open`={"firstVisibleMs": 265.19999999925494, "screenReadyMs": 265.2999999988824, "wallMs": 267.09999999962747, "stats": {"materialized": 27, "placeholders": 3974, "totalBlocks": 4001, "e  |
| L4-long-scroll | ✅ PASS | `maxMaterialized`=147 `evictTotal`=2383  |

## 口径与限制

- 「首块可见」= `openFile()` 返回到首个已物化块进入视口（rAF 轮询），不含 MathJax 全量排版完成。
- 「相对漂移」= 同一锚点块在 settle 前后相对视口的屏幕位移 ÷ 实测行高；「绝对位置」= 回顶后首块相对视口顶偏移 ÷ 行高。
- 「DOM ≤ 视口×8」按**同时存在的块数**（含占位）计，视口块数 = `ceil(pane.clientHeight / 实测行高)`；另报告 `#preview` 节点数。
- 堆读数是 Chromium `performance.memory.usedJSHeapSize`（非进程 RSS）；采样前尽量 `gc()`，仍受引擎 GC 时机影响。
- 本门禁跑在**无头 Edge harness**（与 12 剧本同一条 CDP 路径），不是真机 pywebview；真机首开读数另测。
