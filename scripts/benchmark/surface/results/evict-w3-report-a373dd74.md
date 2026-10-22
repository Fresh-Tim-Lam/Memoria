# W3 首项 · `lazy_evict` 单批长帧 —— 真机复测与修法报告（task-76）

- 仓库：`D:\AAA_Jupyter\Memoria`　｜　基线 commit：`a373dd74`（工作区另有他人未提交改动；本任务只动
  `src/memoria/ui/static/app/js/app.js` + 两个探针脚本）
- 口径：真机 pywebview + WebView2，`MEMORIA_MODE=dev`、`MEMORIA_DEBUG=0`（关 DevTools 观察者效应）、
  `MEMORIA_FRAMELESS=0`、独立 `MEMORIA_CONFIG_DIR`、KB=`artifacts/_kbwork_perf_edu`、
  文档 `教材/08_第8章_差错控制编码.md`（4001 块）、`window.__MEMORIA_LAZY=true`、窗口 1264×821、DPR 1。
- 测量门：每轮开始前先量**空转 rAF**（145 帧）必须 `p50 ≤ 20ms`，否则拒跑（最小化窗口会把 rAF 节流到 1Hz，
  实测会量出 0.2ms 的假读数）——本报告所有有效轮次 `p50 = 8.3ms`。
- 探针：`scripts/benchmark/surface/perf_evict_frames.mjs`（9 轮 + 逐 job 归因 + 淘汰分段）、
  `scripts/benchmark/surface/perf_evict_heap3.mjs`（3 遍滚动堆稳定性）。

## 1. 结论先说

1. **当前 HEAD 上「`lazy_evict` 单批 >200ms」不可复现**：9 轮 `max_frame_ms` 全部 ≤200ms（最大 **181.1ms**）。
   单批耗时分解显示 **淘汰块本身只占 ~13%**；长批的主项是**批尾一次强制布局**（~59%），不是"60 块太多"。
2. **但发现并修复了一个真实的快拖堆回退**（比长帧更严重）：HEAD 在**快速拖动**下 `document.math` 涨到
   4455 条（4446 条 detached）、JS 堆 16.2MB → **130MB**；修好后 9 轮稳定在 **21.4–22.6MB**、
   3 遍滚动 20.83 / 21.32 / 21.53MB（+2.4% / +1.0%）。
3. **切片方案实测是负收益，已回退**：`maxSliceMs=8 + ctx.yield()` 把 `max_frame_ms` 压到 ≤112.9ms，
   但同轮 rAF p95 从 ~160ms 升到 **190–310ms**、拖到底墙钟 3.7–7.2s → **9.6–13.3s**、高度漂移
   1.0k px → **34.7k px**。按"用户可见帧"判据它不是改善，故不采用（数据见 §5）。
4. 因此 **`LAZY_EVICT_BATCH_MAX` 保持 60 不变**：降批只会增加"每批固定布局"的次数（见 §3 分解），
   `slice_count` 维持 0（未采用切片，验收第 2 条不适用）。

## 2. 9 轮真机 `max_frame_ms`（快速 5 + 慢滚 4）

| 轮 | 类型 | `max_frame_ms` | `slice_count` | `lazy_evict` 单次最大 | 本轮淘汰块数 | 堆（GC 后） |
|---:|---|---:|---:|---:|---:|---:|
| 1 | 快拖 80 帧 | 181.1 | 0 | 181.1 | 3913 | 21.44 |
| 2 | 快拖 | 148.3 | 0 | 148.3 | 3996 | 22.07 |
| 3 | 快拖 | 154.2 | 0 | 154.2 | 4001 | 22.24 |
| 4 | 快拖 | 77.9 | 0 | 77.9 | 3993 | 22.41 |
| 5 | 快拖 | 147.3 | 0 | 147.3 | 4009 | 22.50 |
| 6 | 慢滚 30×100ms | 62.2 | 0 | 54.5 | 2470 | 22.37 |
| 7 | 慢滚 | 64.8 | 0 | 56.9 | 2421 | 22.43 |
| 8 | 慢滚 | 70.8 | 0 | 65.8 | 2455 | 22.48 |
| 9 | 慢滚 | 54.5 | 0 | 54.5 | 2480 | 22.52 |

同 build 复跑（3 轮快拖，证明不是单次侥幸）：186.9 / 136.5 / 149.6ms，堆 22.9–23.1MB。

**对照：基线（HEAD 原样，批 60，无切片）** 9 轮 `max_frame_ms` = 12.4 / 34.6 / 35.5 / 33.7 / 40.0 /
23.3 / 20.8 / 51.0 / 65.3（max 65.3），但堆 = 92.4 / 107 / 114.8 / 122.5 / **130.2**MB（打开时 16.2MB）
—— 即"帧很快"是带泄漏跑出来的，且泄漏本身会随轮次继续涨。

## 3. 单批耗时分解（`window.__MEMORIA_EVICT_PROFILE`，默认关闭）

第 1 轮累计（66 批 / 3913 块 / 批均约 35.6ms）：

| 段 | 累计 ms | 占比 | 说明 |
|---|---:|---:|---|
| keep（保留窗口二分 + 读 rect） | 391.4 | 16.7% | 4 次二分共享一次布局 |
| scan（候选收集 + 评分 + 排序） | 149.0 | 6.3% | 4001 个子节点遍历 |
| read（换出前 60 块 rect/adv 量测） | 12.2 | 0.5% | 与上一条同一次布局 |
| **apply（`replaceWith` + 占位 + IO + BI 同步）** | **299.8** | **12.8%** | **每块边际仅 0.077ms** |
| 其中 BlockIndex 同步 | ~0.1 | ~0.004% | `BI.get()` O(1)，可忽略 |
| **typesetClear（含 purge）** | **116.6** | **5.0%** | purge 仅 9.7ms（0.4%） |
| 批尾（`scrollHeight` + 锚点 rect 强制布局 + 队列清理） | 1379.1 | **58.7%** | 每批一次全篇强制布局（~21ms，尖峰 150–180ms） |

⇒ 「60 块太多」不是主因：60 块的真实淘汰成本 ≈ 4.6ms（apply 0.077ms/块）；长批来自**每批一次的强制布局**，
与批大小近似无关。**降批 = 增加批次数 = 增加强制布局次数**，方向相反；切片同理（每批被拆成两帧，
每帧各自触发一次读后布局），实测也更差（§5）。

## 4. 修的是什么：快拖下的 MathJax 泄漏（堆 130MB → 22MB）

`§3` 的分解与 `max_frame_ms` 都说明单批没有 200ms 级问题，但 §2 的堆数据暴露出**另一条真实回退**：

- 现象（HEAD 原样，快拖 1 轮后）：`document.math` **4455 条 / 4446 条 `typesetRoot.isConnected===false`**，
  JS 堆 16.2 → 92.4MB，2 轮 93.6MB，3 轮 130MB（正是 task-70 修掉的那个泄漏形态）。
- 根因 A：`_purgeDetachedMathItems()` 写的是 `doc.math.remove(stale)`（传数组），而 MathJax
  `MathList.remove(...items)` 是**变参**签名 ⇒ **静默 no-op**。页面内实测：`remove([it])` 条数不变，
  `remove(...items)` 才下降（4455→4448→4397）。⇒ task-70 的"兜底"从未生效。
- 根因 B：`_lazyFlushMathNow` 把队列里的块**无条件**交给 `MathJax.typesetPromise(batch)`；
  快拖时这些块早已被 `lazy_evict` 换出 ⇒ 排版发生在 **detached 子树**上，创建的 `MathItem` 在
  淘汰批的 `typesetClear` **之后**才出现，没人再清。
- 改法（只改 `app.js`）：
  1. `_purgeDetachedMathItems`：`doc.math.remove.apply(doc.math, stale.slice(i, i+500))`（分块，防变参栈风险）；
  2. `_lazyFlushMathNow`：排版前 `batch = batch.filter(el => el && el.isConnected)`；全被淘汰则只 reveal 不排版。
- 效果：9 轮堆 21.44→22.52MB；3 遍滚动 20.83/21.32/21.53（+2.4%/+1.0%）；`document.math` 回顶 0 条、滚到
  25/50/75% 为 49/33/79 条且 **detached 全 0**；`-math-pending`、`-math-hidden` 均 0；可见 `mjx-container`
  5/10/25 个（公式正常）。⇒ 「没有为了切片把 typesetClear 漏掉」这条成立，而且比修前更严（不再给死块排版）。

## 5. 切片方案（已实现→实测→回退，留档）

`maxSliceMs: 8` + 块边界 `await ctx.yield()`（含"让出期间滚走 >1 屏则放弃剩余块"与"用户位移时不补偿锚点"）：

| 指标 | 基线（HEAD，批 60） | 切片（8ms） | 回退后（本报告最终） |
|---|---|---|---|
| 9 轮 `max_frame_ms` max | 65.3 | 112.9 | 181.1 |
| `slice_count`（第 1 轮） | 0 | 20 | 0 |
| 快拖墙钟（第 1/5 轮） | 3.7s / 7.2s | 13.3s / 11.3s | 13.4s / 12.9s |
| rAF p95（快拖） | 78–173ms | 192–322ms | 302–322ms |
| 高度漂移累计 | 1.0k px | 34.7k px | 1.3k px |

切片确实把"单片同步耗时"钉住了（`maxApplyMs` ≤ 9.5ms，`maxMathClearMs` ≤ 5.9ms），但代价是**批次数翻倍**
⇒ 强制布局次数翻倍 ⇒ 用户可见帧更差、淘汰吞吐下降。故回退。

## 6. 验收对照

| 验收 | 结果 |
|---|---|
| 9 轮 `max_frame_ms` 全 ≤200 | **PASS**（181.1 / 148.3 / 154.2 / 77.9 / 147.3 / 62.2 / 64.8 / 70.8 / 54.5；复跑 186.9/136.5/149.6） |
| `slice_count > 0`（若采用切片） | **不适用**（切片实测负收益，已回退；`slice_count=0`） |
| 淘汰不退化 | **PASS**：滚到底 materialized 55–107 块（视口 821px ≈ 37 块/屏 ⇒ ≤8 屏 = 296 块的上限），`#preview` 节点 5,171–6,135；回顶 4,018 节点 / 35 块，3 遍不增长；`evictTotal` 9 轮累计 29,738 > 0 |
| 堆不回退 | **PASS**：21.44→22.52MB（9 轮）；3 遍回顶 GC 后 20.83/21.32/21.53（+2.4%/+1.0%，≤+10%） |
| 12 剧本 / blockquote / trailing_space / scheduler_vm / 纪律 | **PASS**：12/12（0 失败，38.7s）、80/80、62/62、scheduler_vm 全 PASS、`check_scheduler_discipline.py` PASS（62 文件 / 白名单 28 条全命中）；`node --check` / `git diff --check` 通过 |

## 7. 未验证 / 边界（如实）

1. **帧读数的 A/B 不是密封的**：基线轮次在会话早期（同机 `msedgewebview2=18 / python=4`），最终轮次在
   `msedgewebview2=24 / python=5`（另有 agent 实例在跑）下测得；两轮 CPU 采样 11–23%。
   **跨轮次的 `max_frame_ms` 差异不能全部归因于代码**；确定性的差异是堆（同一会话内可重复：12.8→21.5 vs 92→130）。
   尝试补做"同负载交错 A/B"时，重启实例的 `openFile()` 竞态导致 08 章未打开（探针已改为 loud-fail 并加重试）。
2. **181ms 的余量只有 1.1×**：主项是批尾强制布局，受机器负载影响；未做"慢机/4 核"降级测量。
3. **未复现历史 341.5ms**：历史数据是 heap 修复前、且机器并发不同；本机在 heap 修复前的 build（`a7944d74` 的
   app.js）测得 18.4/15.5/35.5ms + 堆 95/169/212MB，说明"长帧"与"泄漏"在本机不是同一时刻的同一现象。
4. **未动** `scheduler.js` / `render-core.js` / `app.css` / `lexer|parser|source-gen`；未提交 commit。
5. 解剖探针 `window.__MEMORIA_EVICT_PROFILE` 常驻但**默认关闭**（关闭时只多一次判空）；开启后每批多约 140 次
   `performance.now()`（实测 <0.05ms/批），但报告里的 `max_frame_ms` 均为**开启探针**下测得（对两 build 同等）。

## 8. 产物

- `scripts/benchmark/surface/results/evict-frames-final-a373dd74.json`（最终 9 轮，主证据）
- `scripts/benchmark/surface/results/evict-frames-final-rerun2.json`（同 build 复跑 3 轮）
- `scripts/benchmark/surface/results/evict-frames-baseB-a373dd74.json`（基线 9 轮）
- `scripts/benchmark/surface/results/evict-frames-prefix-a7944d74.json`（heap 修复前 build，3 轮）
- `scripts/benchmark/surface/results/evict-frames-after-a373dd74.json`（切片实验 9 轮，负结果留档）
- `scripts/benchmark/surface/results/evict-heap3-final.json`（3 遍滚动堆稳定性）
- 探针：`scripts/benchmark/surface/perf_evict_frames.mjs`、`scripts/benchmark/surface/perf_evict_heap3.mjs`
