# 惰性路径交互门禁（W4.1）：ver-neg-viewport-placeholder

- 时间：2026-10-22T17:21:21.221329+00:00
- commit：`95356e57`
- 语料：`scripts/benchmark/surface/fixtures/lazy-gate-kb/docs/lazy-gate-1600.md`（fixture 源行数 5785，标记 160 个）
- 剧本：`lazy-gate.json`
- 负向注入：viewport-placeholder
- 批尾模式：请求 `产品默认`；运行期实测 `pred`
- 浏览器：Edg/155.0.4283.62
- 测量可信门：rAF p50 = 16.4 ms（阈值 ≤ 20 ms）⇒ 可信

## 结论：❌ FAIL（L2-positions）

### 打开（惰性路径）

- 首块可见：**115.09999999962747 ms**（预算 500 ms）
- 首屏就绪（≥3 块且有文本）：115.09999999962747 ms；墙钟 116.59999999962747 ms
- 块数：3662（占位 3629 / 已物化 33）；行高 22.4 px；度量来源 `probe`；每屏约 31 块

| 检查 | 状态 | 关键读数 |
|---|---|---|
| L0-idle-raf | ✅ PASS | — |
| L1-open-first-screen | ✅ PASS | `open`={"firstVisibleMs": 115.09999999962747, "screenReadyMs": 115.09999999962747, "wallMs": 116.59999999962747, "stats": {"materialized": 33, "placeholders": 3629, "totalBlocks": 3662, "  |
| L2-positions | ❌ FAIL | `drift`={"driftPx": 0, "driftLines": 0, "lineDelta": 0} `drift`={"driftPx": 0, "driftLines": 0, "lineDelta": 0} `drift`={"driftPx": 0, "driftLines": 0, "lineDelta": 0} `drift`={"driftPx": 0, "driftLines": 0, "lineDelta": 0}  |
| L3-back-to-top | ✅ PASS | `delta`={"absDeltaLines": 1.1, "lineDelta": 0}  |
| L4-long-scroll | ✅ PASS | `maxMaterialized`=109 `evictTotal`=3239  |
| L5-edit-protect | ✅ PASS | `whileFarAway`={"exists": true, "isPlaceholder": false, "stats": {"materialized": 89, "placeholders": 3573, "totalBlocks": 3662, "evictTotal": 3414, "keepScreens": 4, "suspended": false, "heightD  |

## 失败明细（定位到步骤/断言）

### L2-positions

- `position-30pct` / `settled-viewport-placeholders-0`：期望 `0`，实际 `1`（滚动停稳后视口里不得有未物化的空白占位）
  - `fraction`：0.3
  - `target`：{"targetBlock": 1101, "blockSrcLine": 1736, "blockSrcLineEnd": 1736, "scrollTop": 43967, "targetLine": 1736}
  - `settledMs`：139
  - `before`：{"vpPlaceholders": 0, "vpRealBlocks": 21, "topLine": 1735, "topBlockIndex": 1100, "topBlockTop": 60.4, "ratio": 0.3}
  - `after`：{"vpPlaceholders": 1, "vpRealBlocks": 20, "topLine": 1735, "bottomLine": 1760, "topBlockIndex": 1100, "topBlockTop": 60.4, "ratio": 0.3, "vpTextLen": 477}
  - `drift`：{"driftPx": 0, "driftLines": 0, "lineDelta": 0}
  - `markersVisible`：[{"id": "LAZYGATE-MARK-0049", "line": 1738}]
  - `markerNear`：[{"id": "LAZYGATE-MARK-0049", "line": 1738}]
  - `sourceTextCheck`：{"blocksChecked": 7, "sourceSpan": {"from": 1735, "to": 1760}, "renderedFeatures": 170, "matchedFeatures": 170, "ratio": 1, "hits": ["t:0049", "t:lazygate-mark-0049", "t:1280", "t:token-0049-a", "t:the", "t:quick", "t:brown", "t:fox", "t:jumps", "t:over", "t:lazy", "t:dog"], "ok": true, "stale": [], "details": [{"idx": 1100, "line": 1735, "end": 1735, "len": 20, "kind": "text", "matched": 6, "hits": ["t:0049", "c:惰性", "c:性门", "c:门禁", "c:禁样", "c:样章"], "head": "第 49 节 · 惰性门禁样章 0049"}, {"idx": 1103, "line": 1738, "end": 1738, "len": 63, "kind": "text", "matched": 36, "hits": ["t:lazygate-mark-0049", "c:区域", "c:域标", "c:标记", "c:本节", "c:节用"], "head": "LAZYGATE-MARK-0049 区域标记：本节用于验证大文档的惰性物化与工"}, {"idx": 1106, "line": 1741, "end": 1741, "len": 219, "kind": "diagram", "matched": 86, "hits": ["t:1280", "t:token-0049-a", "t:the", "t:quick", "t:brown", "t:fox"], "head": "本节讨论第 49 组样本的物化与淘汰行为：设输入序列为 x 49 = ∑ k ="}, {"idx": 1109, "line": 1744, "end": 1744, "len": 8, "kind": "text", "matched": 2, "hits": ["c:观察", "c:察项"], "head": "49.2 观察项"}, {"idx": 1112, "line": 1747, "end": 1752, "len": 112, "kind": "text", "matched": 54, "hits": ["c:观察", "c:察项", "c:占位", "c:位块", "c:块高", "c:高度"], "head": "观察项 A
  - `vpBlocks`：[{"idx": 1100, "line": 1735, "end": 1735, "len": 20, "kind": "text", "head": "第 49 节 · 惰性门禁样章 0049"}, {"idx": null, "line": 1736, "head": ""}, {"idx": 1102, "line": 1737, "end": 1737, "len": 0, "kind": "text", "head": ""}, {"idx": 1103, "line": 1738, "end": 1738, "len": 63, "kind": "text", "head": "LAZYGATE-MARK-0049 区域标记：本节用于验证大文档的惰性物化与工作集淘汰；标记行号是门禁的文本-位置对齐锚点。"}, {"idx": 1104, "line": 1739, "end": 1739, "len": 0, "kind": "text", "head": ""}, {"idx": 1105, "line": 1740, "end": 1740, "len": 0, "kind": "text", "head": ""}, {"idx": 1106, "line": 1741, "end": 1741, "len": 219, "kind": "diagram", "head": "本节讨论第 49 组样本的物化与淘汰行为：设输入序列为 x 49 = ∑ k = 1 4 α k y k，在窗口宽度为 1280 的视口内，只有落入工作集的块会被真正排版；其余块保持占位（高度由实测行"}, {"idx": 1107, "line": 1742, "end": 1742, "len": 0, "kind": "text", "head": ""}, {"idx": 1108, "line": 1743, "end": 1743, "len": 0, "kind": "text", "head": ""}, {"idx": 1109, "line": 1744, "end": 1744, "len": 8, "kind": "text", "head": "49.2 观察项"}, {"idx": 1110, "line": 1745, "end": 1745, "len": 0, "kind": "text", "head": ""}, {"idx": 1111, "line": 1746, "end": 1746, "len": 0, "kind": "text", "head": ""}, {"idx": 1112, "line": 1747, "end": 1752, "len": 112, "kind": "text", "head": "观察
  - `sourceExcerpt`："\n## 第 49 节 · 惰性门禁样章 0049\n\n\nLAZYGATE-MARK-0049 区域标记：本节用于验证大文档的惰性物化与工作集淘汰；标记行号是门禁的文本-位置对齐锚点。\n\n\n本节讨论第 49 组样本的物化与淘汰行为：设输入序列为 $x_{49} = \\sum_{k=1}^{4}\\alpha_k y_k$，在窗口宽度为 1280 的视口内，只有落入工作集的块会被真正排版；其余块保持占位（高度由实测行高 22.4 推算，不硬编码像素）。实验标记 `TOKEN-0049-A` 用于确认文本没有串位；英文段落 the quick brown fox jumps over the lazy dog, sample 49, width 1280.\n\n\n### 49.2 观察项\n\n\n- 观察项 A：占位块高度必须由实测行高推算，禁止硬编码。\n- 观察项 B：滚动停止 50ms 内，视口内占位块数应回到 0。\n- 观察项 C：远处块允许被淘汰；被编辑/选中的块必须保留。\n- 观察项 D：滚回原位时绝对行号漂移 ≤5 行。\n\n\n> 引用 0049：工作集淘汰是“缺页换出”，不是渲染裁剪；占位必须保高。\n\n\n---\n\n\n## 第 50 节 · 惰性门禁样章 0050\n"
  - `sabotage`：{"ok": true, "replacedBlockIndex": 1101, "sabotageIndex": "sabotage", "kind": "viewport-placeholder"}

## 口径与限制

- 「首块可见」= `openFile()` 返回到首个已物化块进入视口（rAF 轮询），不含 MathJax 全量排版完成。
- 「相对漂移」= 同一锚点块在 settle 前后相对视口的屏幕位移 ÷ 实测行高；「绝对位置」= 回顶后首块相对视口顶偏移 ÷ 行高。
- 「DOM ≤ 视口×8」按**同时存在的块数**（含占位）计，视口块数 = `ceil(pane.clientHeight / 实测行高)`；另报告 `#preview` 节点数。
- 堆读数是 Chromium `performance.memory.usedJSHeapSize`（非进程 RSS）；采样前尽量 `gc()`，仍受引擎 GC 时机影响。
- 本门禁跑在**无头 Edge harness**（与 12 剧本同一条 CDP 路径），不是真机 pywebview；真机首开读数另测。
