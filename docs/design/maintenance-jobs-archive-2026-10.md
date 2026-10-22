# 作业登记明细归档（2026-10-23 自 `docs/design/maintenance-jobs.md §5` 迁入）

> **用途**：承接 `docs/design/maintenance-jobs.md §5` 的**逐字明细**（每项作业的实现状态、证据锚、对账修正原文）。§5 只保留 `kind / 触发点 / 优先级 / 去重键 / 归属` 索引列；**作业登记与去重键的单一事实源仍是 §5**，本文件只存明细，不得据此新增或变更作业。
> **目标读者**：维护者 / verifier / registrar / 后续作业 Owner。
> **关联文档**：[maintenance-jobs.md](./maintenance-jobs.md)（§5 索引 + 作业模型）、[docs-management.md](../conventions/docs-management.md)（体积预算与归档规则）、[ledger-maintenance.md](../conventions/ledger-maintenance.md)（台账规则）。
> **状态**：归档明细，生效中（2026-10-23）；原文迁出前版本 `56690378`，可 `git log -S` 追溯。

## A. §5 原表（迁出前逐字保留）

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

## B. 迁移说明

- **迁出前**：§5 = 3584 B（17 行 / 20 个 kind）；整份文档 = 25513 B。
- **迁出后**：§5 = 2,523 B，只保留索引列；本文件约 5.1 KB，原表每行逐字保留（含 2026-09-14 对账修正原文与证据锚）。
- **未改变**：作业 kind 集合、条数、优先级、去重键语义与归属；§3.5 / §3.6 / §8 及其余章节零字节改动。
- **校验**：`python scripts/check_jobs_size.py` 断言索引与归档的 kind 集合/条数/优先级/去重键一致；`--verify-verbatim 56690378` 断言本文件原表逐字等于 `56690378:docs/design/maintenance-jobs.md §5`。
