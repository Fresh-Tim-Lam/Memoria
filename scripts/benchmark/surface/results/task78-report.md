# task-78 收口报告：大文档惰性工作集偶发超 8 屏

- 日期：2026-10-23
- 代码：`17ee05d9`（task-78 修复，已并入 HEAD `48241f30`）
- 语料：`artifacts/_kbwork_perf_edu/教材/08_第8章_差错控制编码.md`（4001 块，5879 源行）
- 结论：**已定位根因并修复**；4001 块长滚 `maxMaterialized` 从 **232（legacy 最差）/157（pred）** 降到 **117–170**，均 ≤240；P2 积压注入下从 **3684 → 130**。

## 1. 根因（代码级）

惰性管线有两条队列共用 `MemoriaScheduler`：

| 作业 | 优先级 | 来源 |
|---|---|---|
| `lazy_materialize`（物化） | **P1** | IO / 滚动 rAF |
| `lazy_typeset`（MathJax 排版） | **P2** | 每次物化后入队 |
| `lazy_evict`（淘汰） | **P3** | 只在滚动停止 50ms 后 `_lazyScheduleEvict()` |

调度器每帧按优先级取作业（`scheduler.js` `_pick`）。长滚期间只要 P1/P2 队列持续非空，
**P3 可以连续多帧甚至整轮滚动一次都排不到** ⇒ 工作集"只装入、不回收"。这不是淘汰逻辑算错，
而是**优先级饥饿**。

机制验证（`_t78_probe.py` 在页面内每 60ms 注入一个 P2 忙等作业，模拟 typeset 积压，6s 连续拖动）：

| 版本 | 6s 拖动期间 evictDelta | maxMaterialized | 滚动结束物化块 |
|---|---|---|---|
| 修复前 | **49** | **3684** | 3734 / 4001 |
| 修复后 | **2631** | **130** | 104 |

（`results/t78-drag-pred-sealed-base.json` / `-sealed-fix.json`）

次要缺陷：`_lazyEvictNow` 在 `_lazyPending` 非空时直接 `return 0`，**且不再续排**。
淘汰只在"滚动停止"重新排队；连续滚动时 50ms debounce 不触发 ⇒ 一次让路就可能把淘汰链永久丢掉。

### 为什么 pred 更差

pred 批尾不做强制布局（`_tailVerifyNow` 延后），主线程把更多时间留给物化/typeset ⇒ P1/P2
积压更深、P3 饥饿窗口更宽。legacy 每批 `scrollHeight`/anchor rect 的强制布局反而拖慢了管线。
复核者看到的 381（legacy）/991（pred）与这一机制一致；具体数值取决于当轮 CPU/帧率。

### 为什么 4001 块才出现

保留窗口 = 视口 + 上下各 4 屏 = 9 屏像素。该文档约 30 块/屏（`ceil(720/22.4)`），但块平均高
2.5–3 行 ⇒ 稳态 80–170 块，距 240 只有 1–2 个物化批的余量。3662 块 fixture 稳态 99–104，
余量更大；机器/负载稍有抖动，4001 块就会在某个 130ms 采样点越线（门禁按"块数"而非像素计）。

## 2. 修法（仅 `app.js`）

1. **压力感知的淘汰优先级**：新增 `_lazyEvictIsPressure(cc,pane)`（物化块 > 4 屏块数）。
   `_lazyScheduleEvict(pressure)` 在压力下把同一个 `lazy_evict` 作业以 **P1** 排队，否则 P3；
   仍只经 `MemoriaScheduler` 执行，不新增手写调度。同 key 去重，且 P3 请求不得把已排队的 P1 顶掉。
2. **让路但不断链**：`_lazyEvictNow` 因待物化让路时，重新排一次淘汰（P3），物化排空后立即接上。
3. **从物化路径主动布防**：`_lazyFlushNow` 开始/结束与 `_lazySyncMaterializeViewport` 结束时
   调用 `_lazyMaybeScheduleEvict()`；开始处先排淘汰（id 早于续排的下一批物化）⇒ 不会连续两批
   物化都压在淘汰前面。
4. 新增诊断字段：`pressureScreens` / `evictPressureSchedules` / `evictPendingSkips`。
5. **未改**：保留窗口 4 屏、单批 60、占位高度/换出锚定、`render-core`、scheduler、门禁脚本。

## 3. 同 build A/B（密封副本，交替 A/B）

为避开 `app.js` 被 task-72 并发写（见计划单"事故"一节），A/B 用 `_t78_gate.py` 把
`src/memoria/ui/static` 复制到临时目录、按 git rev 替换 `app/js/app.js`，再调用**官方**
`lazy_gate.mjs`；除 app.js 版本外全部同源同机。门禁锁串行，测量门（rAF p50）全过。

| 场景 | 版本 | maxMaterialized | 限值 | 峰值位置 | 视口占位 | peakΔMB | retainedΔMB |
|---|---|---:|---:|---|---:|---:|---:|
| 4001 pred | 78de3d2f（修复前） | 157 | 240 | step 12（37%） | 0 | 65.9 | 6.74 |
| 4001 pred | HEAD | **122** | 240 | step 19（59%） | 0 | 51.1 | 6.78 |
| 4001 pred | HEAD（复跑） | **150** | 240 | step 24（75%） | 0 | 50.7 | 6.78 |
| 4001 legacy | 78de3d2f | **232** | 240 | step 19（59%） | 0 | 59.0 | 6.67 |
| 4001 legacy | HEAD | **170** | 240 | step 32（100%） | 0 | 60.3 | 6.68 |
| 4001 legacy | HEAD（复跑） | **117** | 240 | step 32（100%） | 0 | 60.7 | 6.58 |
| 3662 fixture 6 项 | 78de3d2f | 99 | 248 | — | 0 | 17.3 | 1.91 |
| 3662 fixture 6 项 | HEAD | 100 | 248 | — | 0 | 18.0 | 1.96 |

- 4001 两种模式修复后都 ≤170；复跑顺序交替（pred→legacy→pred→legacy），差异是运行间噪声，
  **pred 不再系统性更差**（122/150 vs legacy 170/117）。
- 高度漂移（连续拖动 5s / ~3800 次换出的累计 `heightDriftPx`）：修复前 32.3px → 修复后 30.5px，
  未增大（`t78-drag-pred-drift-base.json` / `-fix.json`）。
- 堆：4001 pred 峰值增量 65.9→51 MB；legacy 59→60.7 MB（同量级）；驻留增量 6.6–6.8 MB 不变。

## 4. 门禁

| 门禁 | 结果 | 证据 |
|---|---|---|
| 惰性门禁 6/6（3662 fixture，HEAD） | PASS | `raw-t78sealed-sealed-default-fix.json` |
| 4001 专项 3/3（pred/legacy） | PASS | `raw-t78sealed-sealed-fix-*.json` |
| 12 剧本 | 12/12 | `raw-interaction-lazy-gate-existing12_c3262cb6.json` |
| `blockquote_roundtrip_test.js` | 80/80 | 本轮 stdout |
| `trailing_space_input_test.js` | 62/62 | 本轮 stdout |
| `scheduler_vm_test.js` | 全 PASS | 本轮 stdout |
| `check_scheduler_discipline.py` | PASS（62 文件，30 条白名单全命中） | 本轮 stdout |
| `node --check app.js` | OK | 本轮 |

## 5. 复现命令

```powershell
# 密封 A/B（官方 lazy_gate，只替换 app.js 版本）
python scripts/benchmark/surface/_t78_gate.py --app-rev 78de3d2f --scenarios scripts/benchmark/surface/scenarios/lazy-gate-4001.json --label base-legacy --tail-mode legacy
python scripts/benchmark/surface/_t78_gate.py --app-rev HEAD     --scenarios scripts/benchmark/surface/scenarios/lazy-gate-4001.json --label fix-legacy  --tail-mode legacy

# 饥饿故障注入（P2 积压）
python scripts/benchmark/surface/_t78_probe.py --mode pred --app-rev HEAD --step-px 900 --duration 6000 --p2-load-ms 100
```

## 6. 未验证 / 残余风险

1. 全部测量在**无头 Edge harness**；真实 WebView2 的"偶发"未在空载机器上复现（空载基线 157/232）。
   故障注入证明的是机制，不是某一台真机的具体数值。
2. 未在**机器级并发负载**（其他 agent 的 python/wv2）下重复官方门禁；本轮 A/B 串行且门禁锁独占，
   但采样时系统仍有其他 agent 的浏览器进程（msedge 51 / wv2 24）。复核者看到的 991 很可能就是
   这种负载下的饥饿窗口。
3. 阈值 240 未改。保留窗口是"9 屏像素"，若某文档几乎全是单行块，即使淘汰不滞后，块数也可能
   接近/超过 240；本 4001 文档实测最大 170，未触发。若将来出现单行块大文档，应改判据为
   "保留窗口内块数 + 1 屏"或按像素+块数双限，而不是继续加压力阈值。
4. 当前工作区 `app.js` 仍含 task-72 未提交改动（与 HEAD 不同）；本报告所有 sealed 结果按 git rev
   取件，不受工作区并发写影响。
