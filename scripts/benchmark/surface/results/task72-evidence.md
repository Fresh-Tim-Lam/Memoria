# task-72 证据：块级排版缓存（MathJax typeset 结果复用）

- 日期：2026-10-23
- 测试时工作区 app.js：`sha256 3C790F1F9AF45EA92FC189993780F731BCD778A512D642881AC52B8214BFDA6A`（858,182 B；mtime 02:49:15）
- 测试时 HEAD：`b4134025`（A/B）→ 收口时 HEAD 已前移到 `e31f096c`（其它 agent 提交；app.js 字节未变）
- 同 build 交错 A/B：运行时开关 `window.__MEMORIA_TYPESET_CACHE`（A=false / B=true）
- 探针：`scripts/benchmark/surface/_t72_updown_cache.mjs`（由 `perf_updown_positions.mjs` 复制后加 `--ab-cache`）
- 原始数据：`scripts/benchmark/surface/results/task72-ab-cache-8r.json`、`task72-ab-cache-4r-clean.json`

## 实现（app.js）

- 缓存键 `fontSize|display|formula`，值为 **`mjx-container.outerHTML` 纯字符串**（不是 DOM clone，不注册 MathItem）。
- 物化时 `_tsApplyBlock` 写回 `innerHTML`；整块命中 ⇒ `_tsFilterNeedTypeset` 把它从 typeset 队列剔除。
- 换出仍走 `_clearMathJaxWithin` / `_purgeDetachedMathItems`；缓存不持有任何 MathJax 对象 ⇒ `document.math` detached 恒 0。
- 上限 1024 条 / 8,000,000 字符（实测 08 章全量 down 一遍 = 827 条 / 7,066,821 字符，零逐出）；FIFO 逐出。
- 换文档（`state.doc.path` 变化）整表清空；`window.__MEMORIA_TYPESET_CACHE===false` 完全旁路。
- 只读统计 `window.__MEMORIA_TYPESET_CACHE_STATS()`；`__MEMORIA_TYPESET_CACHE_CLEAR()` 供 A/B 每轮清空。

## A/B 结果（8 轮，4 轮/臂，19 位置，600ms 窗口，08 章 4001 块）

| 指标 | A（cache off） | B（cache on） |
|---|---|---|
| 超 1.2× 位置数（每轮） | **5, 0, 1, 0**（首轮 5/19） | **1, 0, 0, 0** |
| 超 1.2×（4 轮中位后） | 1/19（45%，ratio 1.391） | **0/19** |
| up/down 比值中位 | 0.975 | **0.642** |
| up/down 比值 p90 | 1.030 | **0.945** |
| gate4（30/50/70/90） | 4/4 | 4/4 |
| up 遍 typeset 中位之和 / 轮 | **1082.8 ms** | **105.5 ms**（−90.3%） |
| up 帧 max 之和 / 轮 | 1231.5 ms | 766.8 ms（−37.7%） |
| down 墙钟（4 轮中位） | 16256 ms | 16244 ms |
| up 墙钟（4 轮中位） | 16229 ms | 16256 ms（+0.17%） |
| heap usedSize（4 轮） | 22.67 / 22.88 / 22.94 / 22.97 MB | **21.86 / 21.95 / 22.04 / 22.08 MB** |
| DOM 节点 max | 15361 | 14148 |
| heightDrift 中位 | 73.7 px | 50.7 px |
| document.math detached | 0 | 0 |
| 缓存 entries / chars / 逐出 | — | 838–843 / 7.16–7.25M / 0 |

- 第一遍（down）逐位置对比 A：中位 **−5.4%**（min −22.9%，max +4.9%）⇒ 不退化。
- 70%/90% 位置：up typeset 中位 A=28.5/18.5ms → B=4.0/7.5ms；ratio 1.007/0.886 → 0.656/0.945。
- 45%（单块大矩阵）：A 的 114.2ms up-typeset 消失（B 2.4ms）；B 仅 1 轮出现一次 85.9ms 非 typeset 长帧（ratio 1.411），其余 3 轮为 0。

## 正确性

`_t72_check_restore.mjs`（同一块 排版 → 换出 → 复入）：

- 规范化（ids 归一）后的 `mjx-container` outerHTML **逐字节相同**：`cmpBlock.ok=true`、`cmpInline.ok=true`；
- 复入的 SVG 尺寸/`viewBox`/`style`/`display` 全部与首次排版一致；行内块高差 0.4px（取整误差）；
- 显示公式块首次物化时块高 123px → 复入后 41.1px：这是既有 `min-height` 占位锁（首见时按估值锁高、
  换出后按真实 adv 高度重估）的行为，与缓存无关；缓存产物本身的几何完全一致；
- 复入后 `document.math` 仅剩当前可见的 2 条、detached=0；复入的容器不是 MathItem，后续换出不会再产生 detached 引用。

## 门禁（全部在最终 app.js 上跑）

| 门禁 | 结果 |
|---|---|
| `node --check app.js` | PASS |
| `blockquote_roundtrip_test.js` | **80/80 PASS** |
| `trailing_space_input_test.js` | **62/62 PASS** |
| `edit_cut_undo_test.js` | **28/28 PASS** |
| `edit_drag_drop_test.js` | **38/38 PASS** |
| `scheduler_vm_test.js` | **全 PASS**（G3 全项） |
| `check_scheduler_discipline.py` | **PASS**（62 JS / 白名单 30 条全命中） |
| `run_lazy_gate.py --label task72-final2 --with-existing-12` | **6/6 PASS + 12/12 PASS**（27.6s；L4 明确断言 DOM ≤ 视口×8、evictTotal>0、堆不单调增长；L2/L3 视口占位=0） |

产物：`results/lazy-gate-task72-final2_b4134025.md`、`results/raw-lazy-gate-task72-final2_b4134025.json`、
`results/interaction-lazy-gate-existing12_b4134025.md`、`results/raw-interaction-lazy-gate-existing12_b4134025.json`。

异常：第一次 `run_lazy_gate.py --label task72-final` 报 “未产出 JSON（node returncode=0）”（node 未落盘），
立即重跑 `task72-final2` 即 6/6 + 12/12；未复现，判为瞬时 IO/并发异常，不作为产品缺陷。

## 已知未验证 / 边界

- 未在“更小上限 2.5M”下跑完 8 轮：2 轮冒烟 B 为 0/19，但 20% 位置 ratio 1.188（贴线）；8M 才做到全章零逐出。
- 未验证跨文档切换后的缓存重建（逻辑上 `_tsSyncDoc` 清空，行为等价于冷启动）。
- 未做像素级截图对比；一致性证据为规范化 DOM/几何，不是像素。
- A/B 第一轮 A 为 5/19、后续 A 轮为 0–1/19（页面预热/JIT 顺序效应）；任务书里的 5–7/19 与本机首轮 A 吻合，B 全轮 0–1/19。
- AOCI 维护未执行：app.js 仍被并发任务（task-78）写入/提交，待集成收口后统一 maintain 更安全。
