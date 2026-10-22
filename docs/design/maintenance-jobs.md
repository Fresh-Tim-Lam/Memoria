# 维护作业与静默同步（Maintenance Jobs & Silent Sync）

> **用途**：把 Memoria 中所有“数据保存后的派生维护”统一为**后台作业（job）子系统**来设计与演进。文档给出：为何要用 OS 的任务/调度视角、作业模型与调度内核设计、前端/后端执行边界、全量作业登记表、以及分阶段推进与验收。解决三类已知痛点：①正文换行导致 KP range 重锚后界面要等手动刷新才更新；②“创建知识点”等慢作业阻塞用户连续操作；③重命名/写回后派生视图（树、图谱、预览带、面板）状态不一致。
> **目标读者**：项目负责人（评审范围/优先级/阶段）；实施 Agent（按登记表与阶段落地内核与各作业）。
> **关联文档**：[meta-rules.md](../conventions/meta-rules.md)（规范书写）；[image-features.md](../reference/image-features.md)（图片注册表/自动检查）；[export-plan.md](./export-plan.md)（同“按阶段+验证”的推进范式）；[i18n.md](../conventions/i18n.md)（文案不进内容）；[AGENT.md](../../AGENT.md)（边界与单一事实源）。
> **状态**：草稿（待评审），2026-09-09。

---

## 1. 背景与动机

当前派生维护散落各处：保存里顺带重锚 range/图片注册表、`_write_sidecar` 同步重建词法索引、图谱与检查靠手动按钮、图片自动检查靠前端长间隔轮询。缺失的是**统一的任务语义**，导致：

1. **可见滞后**：保存时 range 已被后端修正，但知识点面板要等手动刷新（首期已做 KP 面板静默刷新，见下文 §6）。
2. **队头阻塞**：创建知识点这类慢 RPC 被用户**同步等待**，想连续创建下一个就卡住。
3. **派生视图不一致**：重命名/写回后文件树、KP 面板、预览范围带、图谱彼此可能短暂不一致。
4. **重复/浪费**：同一路径多次写会触发多次全量重建（如词法索引），缺少合并与陈旧丢弃。

本方案用 OS 任务视角统一解决：给每类维护一个“作业”，交给**调度器**排队、合并、按优先级与空闲时间执行，并由同步点保证一致性。

## 2. 核心视角：把维护作业当作 OS 任务

| OS 概念 | Memoria 对应 |
|---|---|
| 进程 / 线程 / 作业 | 每类维护 = 一个**作业**（job） |
| 中断 / 软中断 | 用户动作产生“待处理”标记（编辑、保存、创建、重命名、悬停） |
| 调度器 | 统一作业调度：去重合并 → 按优先级出队 → 空闲执行 |
| 优先级 / 队头阻塞 / 优先级反转 | 一致性作业高于展示作业；慢作业不得堵住快作业；低优持有锁时可临时提升 |
| 时间片 / 空闲执行 | UI 主线程不可抢占 → `requestIdleCallback`/分片协作式跑轻活；重活下放线程池 |
| 抢占 / epoch（版本号） | 作业基于旧快照 → 被新版本**废弃/重启** |
| 同步屏障 / 检查点 | 文件切换/关库前 `flush`；保存成功 = 检查点，下游才消费 |
| 幂等 / 重试 | 每类作业带 dedupeKey 与幂等执行，失败可重试无副作用 |
| 缓存失效链 | 写后失效：正文 → sidecar → manifest/注册表 → 索引 → 图谱 |
| 触发点约束（2026-09-10 确立） | 维护动作只有两类合法触发点：**后台调度**（自动、不阻塞交互）或**用户显式**（打开库/刷新/构建/点击）；**交互热路径（切换文件、输入、点击）禁止任何同步重活**。读路径只读已就绪快照，未就绪时用上一版并登记后台重建（最终一致） |

## 3. 作业模型与调度内核

### 3.1 作业字段（建议）

```
{
  id,            // 唯一（用于观测）
  kind,          // 类型：doc_save / kp_range_resync / registry_doc / kp_create / index_rebuild / graph_build / cleanup / validate ...
  path,          // 作用对象（md 相对路径 / KB 根 / 全库）
  priority,      // 见 §3.3 优先级表
  dedupeKey,     // 合并键：同 key 同参数的新作业顶替旧作业（drop-newer 或 drop-older 由 kind 定）
  epoch,         // 快照版本：入队时记录；执行前与全局比较，过期则丢弃
  cancelable,    // 是否可被新作业取消
  maxIdleMs,     // 允许多久空闲内完成（前端分片）；超时转后台/降级
  created_at, executed_at, status, // {queued, running, done, dropped, error}
  result, error,
}
```

### 3.2 前端调度内核（单例）

- **入队**：`schedule(jobSpec)` → 若 `dedupeKey` 已存在：按 kind 语义覆盖（保存类合并新参数；重建类丢弃 pending 旧版）。重复去抖用现成 SAVE_DEBOUNCE/RENDER_DEBOUNCE 参数化。
- **出队**：优先执行**关键一致性**作业；其次在 `requestIdleCallback`（无则 setTimeout 兜底）执行展示级作业；一次只跑一个协作式任务，`yield` 给渲染。
- **epoch 检查**：每个作业执行前比较 `job.epoch` 与 `state.gen`（每次正文/结构变更 +1）；过期则 `dropped`，不产生副作用。
- **flush(sync point)**：文件切换/关库/退出前同步等待关键队列（doc_save、kp_range_resync）完成；展示级队列可丢弃。
- **观测**：`console.log("[job] …")` 沿用现有日志体系；不新增 UI 弹窗。

### 3.3 优先级表（草案，评审可调）

| 优先级 | 作业 | 理由 |
|---|---|---|
| P0 一致性 | doc_save、kp_range_resync、registry_doc、rename_cascade | 写盘/元数据一致性，用户即将依赖 |
| P1 交互 | kp_create、kp_update | 用户显式创建/编辑知识点；**入队后立即放行 UI**，后台续跑 |
| P2 派生视图 | kp_panel_refresh、preview_range_redraw、file_tree_refresh | 静默、低干扰 |
| P3 后台重活 | index_rebuild（词法/embedding）、registry_full、graph_build、cleanup、validate、image_auto_check | 空闲执行/定时/手动 |
| P1 交互 | lazy_materialize（预览物化） | 视口可见性优先；P1 可借用 P2/P3 份额（§3.5）；单批 ≤100 块，余量续排 |
| P2 派生视图 | lazy_typeset（公式排版） | 让路给物化；单批 ≤60（滚动中）/≤200（静止）公式，余量续排 |
| P3 后台重活 | lazy_evict（工作集淘汰） | 仅首屏建成/滚动停止后执行；单批 ≤60 块，绝不进滚动帧 |

**渲染作业与维护作业共用同一内核**：`lazy_materialize` / `lazy_typeset` / `lazy_evict` 只是 `kind` 不同的
`MemoriaScheduler.schedule()` 作业，与 `kp_panel_refresh`、`index_rebuild` 等享受同样的去重合并、`epoch`
陈旧丢弃、优先级排序与帧预算（§3.5）。它们的 P1/P2/P3 仍按本表数字小者优先；`lazy_typeset` 的
`LAZY_MATH_MERGE_MAX_WAIT`（500ms）是**合并截止期**（deadline），不是第二个调度源——到点必排，
但正常路径仍由 Scheduler 出队。

### 3.4 执行边界（前后端）

- **前端**：协作式分片 + RPC；展示级轻作业在本线程空闲执行；绝不因派生刷新阻塞输入。
- **Python 后端**：IO/CPU 重活放**线程池**（`concurrent.futures` 或独立 worker 线程 + 队列），RPC 快速返回 `accepted`；完成事件经轮询或回调刷新前端。GIL 下 CPU 密集用线程+`ThreadPoolExecutor` 仍受 GIL，但本应用重活以 IO/文件/YAML 为主，必要时才考虑进程。**（✅ G5.3 已落地：`services/executor.py` 线程池 + 作业表；`validate_kb_async` 提交即返回 + `job_status` 轮询，见 §7 首期取轮询；资源级串行仍由作业自身加锁，如 M3 的 `_lex_lock`）**
- **原子性**：所有写盘沿用“tmp + `os.replace`”；作业失败只回滚自身，不影响其它队列。

### 3.5 帧预算 / 公平份额（M5.1，2026-10-22）

**帧窗口与累计。** 一次 `pump()` 只排一个 `runFrame()`；`runFrame()` 打开帧窗口
`{start, used, jobs, units, over}`。每个作业单元结束后把**同步执行时间**累加到 `frame.used`：
`run(ctx)` 只计“调用到第一个 `await`”的前缀；async generator 计 `next()` 的前缀；`steps` 计单步前缀；
promise 作业跨帧恢复时无法再切分前缀，退化为该切片的墙钟。`await` RPC / 定时器的等待时间**不计入**
帧预算（否则一次 50ms RPC 会被误判为长任务）。

**出队。** `QUEUE + SUSPENDED` 统一按 `(priority, id)` 升序取队首；帧内循环直到：
① 队列为空；② `frame.used >= limit`；③ `frame.used + estimate(next) > limit`（不把大概率超预算的作业硬塞进本帧）；
④ 当前作业显式让出 / 切片耗尽。帧尾仍有作业 ⇒ `requestAnimationFrame(runFrame)` 续帧
（后台标签页 rAF 被节流时挂 50ms 定时兜底）；否则解析 `flush()` 的 waiter。

**借用规则（公平份额）。**

```
limit(job) = frameBudgetMs                              // priority <= 1：P0/P1 整帧，含 P2/P3 份额
           = max(1, frameBudgetMs - criticalReserveMs)  // 有 P0/P1 待执行时，P2/P3 只用剩余份额
           = frameBudgetMs                              // 无关键作业时 P2/P3 也可用整帧
```

P0/P1 不因 P2/P3 在跑而等待；P2/P3 的挂起作业与 P0/P1 同场按优先级竞争，下一帧 P0 先被取到，
因此不会出现“低优持有预算 ⇒ 高优饿死”的优先级反转。抢占只发生在**作业/切片边界**，不能中断一段同步 JS。

**切片语义。** 三种等价写法（均为增量，旧 `run` 不受影响）：协作式 `maxSliceMs + ctx.shouldYield()/ctx.yield()`；
async generator（每次 `yield` 是一个单元）；`steps[]`（每个函数是一个单元）。`ctx` 提供
`maxSliceMs / now() / frameUsedMs() / shouldYield() / yield()`；`ctx.yield()` 结束本帧并在下一帧恢复**同一个
run 调用**（不重跑）。`shouldYield()` 为真当：单帧单元数达 `maxUnitsPerFrame`、声明了 `maxSliceMs` 且本切片已用尽、
帧预算用尽、或更高优先级作业在排队。切片挂起的作业进 `SUSPENDED`，仍参与优先级排序。
`maxSlices`（默认 1000）防止调用方永远 yield 造成活锁；`maxUnitsPerFrame`（默认 1000）防止零耗时单元饿死渲染。

**参数默认值。**

| 参数 | 默认 | 位置 | 说明 |
|---|---:|---|---|
| `frameBudgetMs` | 12 | `configure()` | 每帧作业预算；运行期可调 |
| `criticalReserveMs` | 4 | `configure()` | 关键作业排队时 P2/P3 不得占用的保留额；自动夹到预算内 |
| `maxSlices` | 1000 | `configure()` | 单作业切片上限（活锁保护） |
| `maxUnitsPerFrame` | 1000 | `configure()` | 单帧作业单元上限 |
| `maxSliceMs` | 0 | job spec | 0=不切片；>0 启用协作/自动切片 |
| `estimateMs` | null | job spec | 显式预估；缺省用 kind 的 EMA（`0.7*旧 + 0.3*实测`，冷启动 1ms） |

`configure(opts)` 返回当前生效配置，只做参数合并/夹取，不影响已入队作业。

**观测。** `MemoriaScheduler.counters()`：

| 字段 | 含义 |
|---|---|
| `budget_exceeded` | `frame.used > frameBudgetMs` 的帧数（帧级，每帧最多 +1） |
| `frames_used` | 至少执行/恢复了一个作业单元的帧数 |
| `slice_count` | 跨帧让出次数（协作 yield + 自动切片挂起） |
| `max_frame_ms` | 历史单帧最大**同步作业**耗时（不含合成/绘制/`await`） |
| `scheduled/executed/merged/dropped/queue_max` | 语义不变 |

另有 `status()`、`[job]` 日志、`window.__jobTrace`（200ms 批量写 `logs/job-trace.log`）。

**渲染作业的接入现状。** 三个 `lazy_*` 作业**没有**声明 `maxSliceMs`，而是用自身批上限 + 余量续排实现协作：
`lazy_materialize` 每批 ≤`LAZY_FLUSH_MAX`(100) 块；`lazy_typeset` 每批 ≤60（滚动中）/≤200（静止）公式；
`lazy_evict` 每批 ≤`LAZY_EVICT_BATCH_MAX`(60) 块。因此它们的**单批是不可抢占单元**，其耗时直接计入
`max_frame_ms`；批上限就是单帧上界的主要来源。前序 A/B 实测（真机，`__MEMORIA_LAZY=true`，4001 块文档，
本轮未复测）：打开链路调度器开 median **219ms** vs 关 **554ms**（−60%）。逐次 counters 读数见
`artifacts/agent/verify/scheduler-realmachine-2026-10-22.json`。

**2026-10-22 真机计数（4001 块，pywebview + WebView2，空转 rAF 基线 p50 8.3ms）。**

| 场景 | `max_frame_ms`（每轮） | 中位 | `budget_exceeded` / `frames_used` | `slice_count` | rAF p50 / p95 |
|---|---|---:|---|---:|---|
| 快速拖到底（80 帧，5 轮） | 57.5 / 341.5 / 160.6 / 224.9 / 116.0 | 160.6 | 48–102 / 88–111（55–92%） | 0 | 267–392 / 708–1667ms |
| 慢滚（30 步 ×100ms，4 轮） | 137.5 / 72.7 / 214.4 / 69.5 | 105.1 | 30–58 / 75–108（40–65%） | 0 | 92–142 / 292–483ms |

逐 job 归因（对 `schedule().run` 的同步前缀计时，不改调度语义）：

- **9 轮中 8 轮的 `max_frame_ms` 等于该轮 `lazy_evict` 的最大单次同步耗时**（57.5–341.5ms，p95 最高 264.2ms）；
  慢滚第 4 轮由 `lazy_materialize`（69.5ms）略高于 `lazy_evict`（66.7ms）；
- `lazy_materialize` 37.6–90.4ms；`lazy_typeset` 同步前缀仅 0.4–3.6ms（MathJax 真开销在 `await` 之后，按设计不计入）；
- `slice_count=0`：三个 `lazy_*` 均未声明 `maxSliceMs`，单批不可抢占。

**结论（如实）**：`lazy_evict` 的 60 块单批是当前唯一稳定越过 200ms 的作业；"帧预算应远小于 200ms"
在本轮**未达成**（9 轮中 3 轮 >200ms），且 `budget_exceeded` 占 55–92% 的帧。下一轮应把 `lazy_evict`
改为 `maxSliceMs + ctx.shouldYield()/ctx.yield()`，或把 `LAZY_EVICT_BATCH_MAX` 降到 20–30；
本轮不改 `src/**`。滚动期 rAF 间隔远大于内核帧耗时（p50 92–392ms）⇒ 主要卡顿仍在调度器之外
（滚动同步补齐 + 布局/绘制），不能只靠帧预算解决。

**已知限制。**

1. **异步 `await` 不计预算**：一次 `await` 之后的大段同步渲染无法归因到内核，`max_frame_ms` 会低估；
   这是刻意取舍（避免 RPC 延迟污染预算）。
2. **协作式、非抢占**：一整段同步 JS 不能被中断。未切片作业的单批耗时 = 单帧下界，
   超过预算时只由 `budget_exceeded` / `max_frame_ms` 如实暴露（**是度量，不是故障**）。
3. **切片粒度 = 单元粒度**：两次 `yield` 之间、单个 step 之内无法再切；单元自身 40ms 仍会超预算。
4. **空尾切片**：generator 的 `done` 要到下一帧 `next()` 才发现，`frames_used`/`slice_count` 各 +1。
5. **`replace`/`dropStale` 只作用于未启动作业**：切片拉长了“运行中”窗口，同键新作业不会顶替已挂起的旧作业；
   已启动作业也不会被 `bumpEpoch` 中途丢弃（避免半完成副作用）。
6. **`flush()` 可能跨多帧**：关键路径应用 P0/P1；大队列下 P2/P3 的 flush 墙钟会大于旧版一次性执行。
7. **后台标签页**：50ms 定时兜底保证推进，但会偏离 rAF 节奏；隐藏页的真实调度精度未验证。

### 3.6 调度纪律守卫与允许的例外（2026-10-22）

**规则。** 新增“派生维护 / 批次推进”只能通过 `MemoriaScheduler.schedule({kind, key, priority, run})`。
禁止在 `src/memoria/ui/static/app/js/**` 里新写：① 零延时 `setTimeout(fn, 0)` 充当调度队列；
② `requestIdleCallback` 自建空闲调度；③ 自续 `requestAnimationFrame` 驱动的批次循环。
守卫：`python scripts/check_scheduler_discipline.py`（扫描 62 个 JS 文件，注释中的示例不计），
退出码 0=PASS；命中打印 `文件:行:片段`。

**白名单机制。** 脚本内 `WHITELIST` 每条 = `文件 + 规则 + 代码锚点 + max + 理由`。锚点按**代码行**匹配，
行号漂移不影响；锚点消失会判“白名单陈旧”并 FAIL（强制收口）；同一锚点允许的命中数用 `max` 卡死，
防止在白名单函数里悄悄多塞一处。新增例外必须**同时**改脚本与本节。

**允许的例外（按机制归类；完整清单见脚本 `WHITELIST`）。**

| 类别 | 代表位置 | 为什么不是“手写调度队列” |
|---|---|---|
| 调度器自身降级/续帧 | `scheduler.js`（`idle()` / `requestFrame()`） | 它就是调度器；无 `requestIdleCallback`/rAF 时的退化路径，不能再调度自己 |
| DOM 落定 / 布局同步 | `agent-panel.js` chip 同步；`edit-handler.js` 选择区恢复 | 让浏览器先完成重排，再同步读取尺寸/恢复选区；单次，不推进队列 |
| 渲染耗时打点 | `app.js` 双 rAF 标记 `frame1`/`paint` | 只记录“这一帧真的画完”，不执行任何作业 |
| 惰性管线时序例外 | `app.js` 滚动同步补齐、typeset 单宏任务边界、`MATERIALIZE_ALL` 批间让出、投机预渲染 | 单次边界/有界重试/门禁测试 API；预渲染整篇 parse+render 约 1s，12ms 预算装不下（见下“技术债”） |
| 动画 / 布局循环 | `graph-layout-2d/3d.js`、`graph-view-3d.js`、`graph-settings.js` | 每帧只做布局 tick 或渲染；不是作业队列 |
| 调试 / 资源就绪 | `keys-debug.js`、`markdown-preview.js`（Mermaid 重试） | 调试探针 / 有界依赖等待（`MAX_TRIES`） |

2026-10-22 基线：`PASS: 扫描 62 个 JS 文件；无新增手写调度；白名单 28 条全部命中（共 36 处：timeout0=13 / idle=3 / raf=20）`。

**已知技术债（本轮不迁移，已在白名单注明理由）。**
① 投机预渲染用 `requestIdleCallback(timeout=4000)` 跑整篇 parse+render（~1s，不可切片），无法直接交给 12ms 帧预算；
迁移前需先把预渲染切成 generator/steps。② 三个 `lazy_*` 作业仍是“批上限 + 续排”，未用 `maxSliceMs`；
单批超预算时只能靠 `budget_exceeded` 观测。这两项都不属于“新增债”，但也不应当作长期终态。

## 4. 静默刷新：不打扰原则

派生视图更新必须满足：**不改正文、不动光标、不滚预览/源码、不弹窗、不抢输入焦点**。

| 视图 | 静默更新方式 | 现状 |
|---|---|---|
| 知识点面板 | 保存后 `ranges_resynced>0` → 防重入地重取 doc 后 `renderKpList` | ✅ 已首期落地（app.js `_silentRefreshKpPanel`） |
| 预览范围带 | 抽出“仅重绘范围带、无滚动/闪烁”的轻量路径（区别于 `highlightRange` 的 scroll+flash）；在新范围就绪后静默重绘 | ✅ 2026-09-10：`markRangeQuiet`（只标记、不滚不闪、不自动消失）用于「改范围 / 创建知识点」；跳转仍走 `highlightRange`。编辑路径本就静默（M6b 实时映射），无需另接 |
| 源码高亮 | 编辑中由实时映射自洽；仅在重锚结果与行号不符时局部更新 | ⏳ 阶段 P2 |
| 文件树 | rename 后统一重映射+`refreshFiles`（已随重命名 pipeline） | ✅ |
| 图谱 | **增量更新**（增量在布局与数据层，非帧绘制）：引擎 `applyDelta` + 受影响子图局部松弛；完整重建仍走 P3 | ⏳ G4 拆分后续项（方案 S1–S4，见 g4-gate-summary） |
| 侧车/注册表落盘 | 后端作业内完成，前端不感知 | ✅ |

## 5. 作业登记表（单一事实源，新增作业在此登记）

| 作业 | 触发点 | 优先级 | 可合并 | 当前归属 |
|---|---|---|---|---|
| doc_save | 输入停止（SAVE_DEBOUNCE）/文件切换前 flush | P0 | ✅（同 path 合并） | syncToDisk（已有防抖） |
| durable_flush | 文件切换/关库/退出屏障（fsync 批量） | P0 | ✅（合并） | ✅ M6a 已实现并**门禁通过**（2026-09-09）：save_document barrier 默认 + flush_durable RPC + 前端 3s 防抖兜底；证据 `results/durable-flush-2026-09-09.json`（inline 89.35 → barrier 24.62ms）+ 崩溃注入 15/15。**2026-09-14 对账修正**：原写"待真机回归"，与 to-dolist §12 E7 门禁记录矛盾 |
| manifest_touch_batch | 保存后（manifest 单条更新 ~50ms/次） | P2 | ✅（合并+延迟） | ✅ 模块 pending overlay + 屏障批量落盘（2026-09-09），G4 门禁含"连续保存单次落盘"证据。**2026-09-14 对账修正**：原写"待回归" |
| kp_range_resync | doc_save 成功后同事务 | P0 | ✅（并入 doc_save） | 已并入 `_resync_kp_ranges_after_edit` |
| registry_doc | doc_save 成功后 | P0 | ✅ | 已并入 `_update_registry_for_doc` |
| rename_cascade | 文件/文件夹重命名 | P0 | ❌（独占） | rename_file/rename_dir 已实现 |
| kp_create / kp_update | 用户确认/编辑知识点 | P1 | ❌ | ✅ 2026-09-09 提速（JSON+单文件同步+关窗先于图谱）485ms 保持内联；M6b 拍板：保持内联不入队，改为正文编辑行范围实时同步（区域内 Enter 并入/删行收缩，保存后 resync 权威校正） |
| kp_panel_refresh | ranges_resynced>0 | P2 | ✅ | `_silentRefreshKpPanel` 已落地 |
| preview_range_redraw | 重锚就绪 | P2 | ✅ | ✅ 2026-09-10 已实现：`markRangeQuiet`（只标记范围，不滚动/不闪烁/不自动消失）用于「修改范围 / 创建知识点」，`app.js:11021`（调用点 `app.js:4649,11914`）。**2026-09-14 对账修正**：原写"未实现（P2）"与同文件 §4 矛盾 |
| index_rebuild | 侧车写后（词法）/配置变更（embedding） | P3 | ✅（合并） | ✅ M3 后台化（2026-09-09）：锁+合并 daemon 重建，写路径不阻塞；search/切库/关库前 wait |
| kp_index_rebuild | 侧车写后（KP id 集合）/文件增删改（stem）/显式刷新 | P3 | ✅（合并 + 逐文件增量） | ✅ G5.4（2026-09-10）：读路径只读 `.memoria/kp_targets.json` 轻量快照（零构建），写后失效 + 后台增量重建（逐 sidecar mtime+size 缓存）；打开库只秒读快照，不触发全库重活 |
| graph_build | 显式“构建” | P3 | ✅ | 手动 |
| cleanup / validate / image_auto_check | 显式 / 长间隔 | P3 | ✅ | ✅ G5.3 后端执行器（2026-09-10）：`validate_kb_async` 提交线程池即返回 + `job_status` 轮询；同库同 kind 排队顶替合并 |
| file_tree_refresh | 树/结构变更 | P2 | ✅ | refreshFiles |
| lazy_materialize | IO 收集到视口占位块 / 滚动停止同步补齐 | P1 | ✅（`lazy-materialize:<最小块号>` 顶替 + `dropStale`） | ✅ 2026-10-22 M5：`MemoriaScheduler` 作业；单批 ≤100 块，余量续排 |
| lazy_typeset | 新物化块含公式 / 队列达 400 块 / 500ms 合并截止 | P2 | ✅（`lazy-typeset:<首块号>` 顶替 + `dropStale`） | ✅ 2026-10-22：Scheduler 作业；滚动中 ≤60、静止 ≤200 公式/批 |
| lazy_evict | 首屏建成 / 滚动停止（50ms 去抖） | P3 | ✅（单键 `lazy-evict` 顶替） | ✅ 2026-10-22：Scheduler 作业；单批 ≤60 块，保留 4 屏工作集 |

## 6. 阶段规划（每阶段含验证，通过后再进下一阶段）

| 阶段 | 内容 | 验证 |
|---|---|---|
| P0 | 现状固化：本次已落地的 保存重锚 + KP 面板静默刷新 视为基线 | rename-test：结尾行回车→auto-save→面板行号自动更新（无需手动刷新） |
| P1 | 后端作业化改造：慢 RPC（kp_create 等）改“接受作业+立即放行 UI”，完成事件轮询刷新；词法索引重建移出保存同步路径（可并入 P3） | 连续快速创建 2+ 个 KP 不等待；`py_compile`/browser 流程通过 |
| P2 | 前端调度内核 + preview_range_redraw 轻量路径 + 图谱/树局部刷新 | idle 下作业合并：同文件多次写只触发 1 次重锚与 1 次索引刷新；预览带静默重绘不滚动 |
| P3 | 全量重活入线程池与定时队列；作业登记表补齐；观测日志 | 大库打开/保存期间 UI 无卡顿；日志能区分 queued/running/dropped |

## 7. 打开问题（评审拍板）

- P1 的"完成事件"通道：轮询（简单、有延迟）vs 后端主动回调（前端无 ws 基础设施）——建议首期**轮询**，后续再议。
- 词法索引重建频率：侧车每次写都重建过重；建议改为按 doc 去重合并，触发 `index_rebuild` 作业。
- embedding 索引是否纳入本机制（P3 依赖模型加载）——建议先不纳入，保持现状。

## 8. 落地即登记

本设计评审通过后：阶段每完成一项，在此文档登记修订记录（同 docs-management 修订记录表）并将对应"当前归属"列更新；新增作业种类必须先登记 §5 表再实现。

- 2026-10-22：M5.1 帧预算/公平份额 + 渲染作业接入。新增 §3.5（算法/参数/切片/观测/限制）、
  §3.6（调度纪律守卫与允许例外）；§3.3 补 `lazy_materialize`(P1)/`lazy_typeset`(P2)/`lazy_evict`(P3)；
  §5 补 3 行登记。守卫 `scripts/check_scheduler_discipline.py` 基线 PASS（62 文件 / 28 条白名单 / 36 处）。
  真机 counters 读数见 `artifacts/agent/verify/scheduler-realmachine-2026-10-22.json`（快速滚动 5 轮）
  与 `scheduler-realmachine-slow-2026-10-22.json`（慢滚 4 轮）；9 轮中 3 轮 `max_frame_ms` >200ms，
  均由 `lazy_evict` 单批贡献（见 §3.5 结论；本轮不改 `src/**`）。

- **W3.3 批尾布局核对（`app.js::_tailScheduleVerify`，2026-10-23 登记）**：`rAF` 回调发生在渲染**前**，
  因此读取 `pane.scrollHeight` 仍会强制布局；该处刻意「rAF → `setTimeout(0)`」越过渲染边界后再做一次
  **一次性**同步核对（用于校验预测高度与真实 scrollHeight 的偏差）。由 `_tailVerifyScheduled` 去重，
  **不构成作业队列**，属结构性例外，已进守卫白名单。
