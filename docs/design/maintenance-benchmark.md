# 维护机制基准（Maintenance Benchmark）

> **用途**：为「维护机制改进」建立可量化的**改造前后（A/B）对照**：定义受控基准知识库、指标与采集点、A/B 流程，以及"每阶段改善必须附基准对照"的门禁规则。回答"加了调度内核/静默刷新/索引作业化后，比之前改善了多少"。当前（2026-09-09）B0/B1 基线已落地、B2 部分（L1 采样 + L2 前端插桩）、KP 创建链路归因闭环（§6.5）；其余按 §7 推进。
> **目标读者**：项目负责人（评审指标/流程）；实施 Agent（按 §7 落地生成器与采集）；验收者（跑 A/B 出对照报告）。
> **关联文档**：[to-dolist.md §12](../to-dolist.md)（施工总表/阶段门禁/验证机制分配）；[maintenance-jobs.md](./maintenance-jobs.md)（作业模型与指标挂钩）；[rename-test 生成器](../../docs/example/rename-test/_gen_rename_test_kb.py)（语料生成范式）；[import-plan.md](../reference/import-plan.md)（headless harness 先例）。
> **状态**：草稿（待评审），2026-09-09。

---

## 1. 目的

以**证据**回答三类问题，替代"看起来更顺"的主观判断：
1. 保存/写回链路的阻塞是否下降（长任务、耗时、重建次数）；
2. 派生刷新（KP 面板/预览带/文件树）是否在不打扰交互的前提下及时收敛（合并/丢弃/队列峰值）；
3. KP 创建等慢作业是否消除队头阻塞（连续创建往返阻塞时长）。

## 2. 指标清单（分主/次）

| 指标 | 含义 | 采集点 | 挂靠机制 |
|---|---|---|---|
| save_p95 / save_median | `save_document` 后端总耗时（含重锚/registry/索引，索引另分项） | Python 计时埋点 | A5/A4/M3 |
| index_rebuild_count / cost_ms | 词法索引重建次数与单次耗时 | `_rebuild_lexical_index` 埋点 | A6/M3 |
| longtask_ms / 次数 | 主线程长任务（>50ms） | PerformanceObserver（前端 flag 开） | M5 调度 |
| job.scheduled / executed / merged / dropped | 调度去重与陈旧丢弃计数 | scheduler.js counters | M5 |
| job.queue_max | 队列峰值 | scheduler.js | M5 |
| kp_create_block_ms | 连续 N 次 KP 创建的往返阻塞时长（同步等待部分） | KP 创建 RPC 前后计时 | M6/B5 |
| panel_update_latency | 保存完成→KP 面板反映新行号的可感知时延 | 事件时间戳 | C2/M2 |
| band_update | 预览带静默重绘后滚动/光标位置保持（布尔/位移） | 真机或 harness | M4/C3 |

## 3. 基准知识库（受控语料）

- **生成器**：`scripts/benchmark/maintenance/gen_maintenance_kb.py`（仿 rename-test 但放大与参数化）。
- 参数：`--scale`（默认档：文件 200、KP 约 600、目录层级 3、同目录多文件、links/tags/别名齐全、纯文件若干、图片引用若干、空目录若干）；确定性 seed，重复生成字节一致。
- 运行位置：KB 生成到 `artifacts/_bench_maintenance/kb`（gitignore，不入库）；结果写 `benchmarks/maintenance/results/<run>.{json,md}`。
- **mini 档**：可直接用现有 `docs/example/rename-test/`（功能正确性冒烟），不进性能基准。

## 4. 分两层采集

- **L1 · headless（Python，可无 UI 在任意 commit 跑）**：直接对临时 KB 调用 DocumentService/RPC 同路径函数，测 save_document 分项、索引重建计数、KP 创建耗时。实现仿 `docs/example/import-test/_harness_import.py`（CannedHost 或直连 service），支持 `python ...  --commits <sha1,sha2>` 在指定 commit 上跑（用 git worktree/临时检出）。
- **L2 · 前端/浏览器**：scheduler 计数器经 `window.MemoriaScheduler.status()` 与 counters 导出；长任务经 PerformanceObserver；保存/切换文件的操作序列由 browser 级 harness 或 `[真机]` 清单驱动，结果存 JSON。

## 5. A/B 流程

1. 同一语料（确定性再生成）在同一台机器、同环境变量。
2. 每组基准 = warmup 1 次 + 采样 N（默认 5）次，输出 median/p95/raw。
3. **改造前基线（已锚定）**：`results/baseline_ae66a012.{json,md}`（commit `ae66a012`，tag `maint-base`），由 `scripts/benchmark/maintenance/anchor_baseline.py` 生成（确定性语料 200 文件/599 KP/333 links；外部计时 `save_document`，median≈123ms）。语料 digest 见该文件。
4. **改造后采集**：同一台机跑 `anchor_baseline.py --sha <改造后commit>` → 产出 `results/baseline_<sha>.json`；口径差异（内部分项 `bench_ms` vs 外部总时）在 md 中注明以便对齐。
5. 汇总为 `scripts/benchmark/maintenance/results/summary.md` 表格：指标 | 改前(引用 baseline) | 改后 | 变化% | 结论(通过/回退)。
6. **门禁规则**：凡"改善"类提交，需附该对照表；无对照或出现关键指标回退（如 save_p95 上升、longtask 增加）→ 打回。基线文件与 tag 用于防"开发堆积后无法还原开发前数据"。

## 6. 仪器化缺口（实现时补）

- scheduler.js：加 counters（scheduled/executed/merged/dropped/queue_max）+ `resetCounters()` + `counters()`。✅ 2026-09-09 已实现（另含 `__BENCH_DISABLE_SCHEDULER` 旁路与 `isBypass()`）。
- document.py：save_document 分项计时（heal/registry 分项）——`MEMORIA_BENCH_TIMING=1` 时返回 `bench_ms`。✅ 2026-09-09 已实现（registry/resync 两分项）。
- 前端：PerformanceObserver 在 `?bench=1` 或环境 flag 下启用并把长任务累计写入状态。⏳ B4 时实现。
- KP 创建链路：前后端各埋一个时间戳键。✅ 2026-09-09 已实现（L2）：前端 `?bench=1` 或 DevTools `window.__bench=true`，链路分 kind=`modal`/`quick` 分段输出 `[KP-BENCH]`（start→check_ok→rpc_ok→ui_done→modal_closed），并写入 `window.__benchLog`；后端归因用 `scripts/benchmark/maintenance/trace_kp_confirm.py`（克隆库计时 + 子阶段插桩）。

## 6.5 实现状态（2026-09-09）

- B0 ✅ 改造前基线已锚定：`results/baseline_ae66a012.{json,md}`（tag `maint-base`），语料 digest `756f3cc3…`，save median≈123ms / p95≈200ms（60 次采样）。
- B1 ✅ `scripts/benchmark/maintenance/gen_maintenance_kb.py`：确定性（两次生成内容一致 PASS）、默认档 200 文件 / ~599 KP / 333 链接、range 可解析 PASS。
- B2 ✅（部分）：scheduler counters + 旁路 PASS；save `bench_ms` PASS；L2 前端插桩与后端归因工具 PASS；PerformanceObserver ⏳ 待 B4。
- B3–B6：未开始。
- **KP 创建链路归因闭环（真实库 `D:\AAA_Courses\软件工程概论`，2026-09-09）**：见 [results/kp-confirm-2026-09-09.json](../scripts/benchmark/maintenance/results/kp-confirm-2026-09-09.json)。要点：① 真机 modal 链 total 2442.6ms→(JSON)981.6ms→(**全部修复后)485.7ms**，其中 rpc 段 2389→706.6→340.5ms，modal_closed 段 158.1→0.5ms（关窗先于图谱刷新生效）；② 后端稳态 confirm 4s(YAML 全量 sync)→515ms(JSON)→285.7ms(+单文件范围同步)；③ 根因=pending.yaml 全量 safe_load/safe_dump 每确认同步执行（JSON 同数据约快 150×）+ 全库 propose 全量重跑；④ 已修：pending 存储 JSON+自动迁移、confirm/delete 改 `sync_pending_for_file`、前端弹窗关窗先于图谱刷新；⑤ 克隆库首写 ~12s 为词法/embedding 冷启动重建伪影，真机热态无此；⑥ 剩余稳态大头=词法索引每次保存全库重建（作业化归 M3/G4）。

## 7. 实施步骤（评审通过后）

| 步骤 | 内容 | 验证 |
|---|---|---|
| B1 | 语料生成器（参数化+确定性） | 两次生成 diff 为空；各档文件/KP 计数符合参数 |
| B2 | 仪器化（L1 timers/counters；scheduler counters；前端 flag） | 埋点输出存在且数值合理 |
| B3 | L1 headless 脚本 + commit A/B runner | 在 ae66a012/f5be88bf 各出一份 JSON |
| B4 | L2 浏览器采集（counters/longtask/panel latency） | 同操作序列两次采集一致（±容差） |
| B5 | summary 报告 + 门禁规则落到 to-dolist §12 | 报告格式稳定；规则被引用 |
| B6 | 首个完整对照报告（scheduler 前后） | 见 summary；据此更新 M5 验收证据 |

## 8. 打开问题（2026-09-09 已决策）

- ~~前端 A/B 是否需"同 build 内开关"~~ ✅ 需要：增加 `window.__BENCH_DISABLE_SCHEDULER=1` 旁路（调度退化为旧同步路径），便于 UI 端同 build A/B；后端仍用 commit 对（涉及后端差异）。
- ~~L2 是否自动化~~ ✅ 直接自动化：用 browser/harness 驱动操作序列并采集（counters / PerformanceObserver / 面板时延）；手动清单仅作兜底。
- ~~语料是否含 embedding~~ ✅ 默认档**关闭**（模型噪声不入维护基准）；预留 `--embed` 档供后续考核完整写链路。

