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

### 3.4 执行边界（前后端）

- **前端**：协作式分片 + RPC；展示级轻作业在本线程空闲执行；绝不因派生刷新阻塞输入。
- **Python 后端**：IO/CPU 重活放**线程池**（`concurrent.futures` 或独立 worker 线程 + 队列），RPC 快速返回 `accepted`；完成事件经轮询或回调刷新前端。GIL 下 CPU 密集用线程+`ThreadPoolExecutor` 仍受 GIL，但本应用重活以 IO/文件/YAML 为主，必要时才考虑进程。
- **原子性**：所有写盘沿用“tmp + `os.replace`”；作业失败只回滚自身，不影响其它队列。

## 4. 静默刷新：不打扰原则

派生视图更新必须满足：**不改正文、不动光标、不滚预览/源码、不弹窗、不抢输入焦点**。

| 视图 | 静默更新方式 | 现状 |
|---|---|---|
| 知识点面板 | 保存后 `ranges_resynced>0` → 防重入地重取 doc 后 `renderKpList` | ✅ 已首期落地（app.js `_silentRefreshKpPanel`） |
| 预览范围带 | 抽出“仅重绘范围带、无滚动/闪烁”的轻量路径（区别于 `highlightRange` 的 scroll+flash）；在新范围就绪后静默重绘 | ⏳ 阶段 P2 |
| 源码高亮 | 编辑中由实时映射自洽；仅在重锚结果与行号不符时局部更新 | ⏳ 阶段 P2 |
| 文件树 | rename 后统一重映射+`refreshFiles`（已随重命名 pipeline） | ✅ |
| 图谱 | 结构变更后以 P2 作业触发节点/标签局部刷新；完整重建仍走 P3 | ⏳ 阶段 P2 |
| 侧车/注册表落盘 | 后端作业内完成，前端不感知 | ✅ |

## 5. 作业登记表（单一事实源，新增作业在此登记）

| 作业 | 触发点 | 优先级 | 可合并 | 当前归属 |
|---|---|---|---|---|
| doc_save | 输入停止（SAVE_DEBOUNCE）/文件切换前 flush | P0 | ✅（同 path 合并） | syncToDisk（已有防抖） |
| durable_flush | 文件切换/关库/退出屏障（fsync 批量） | P0 | ✅（合并） | ✅ M6a 已实现（2026-09-09）：save_document barrier 默认 + flush_durable RPC + 前端 3s 防抖兜底；待真机回归 |
| manifest_touch_batch | 保存后（manifest 单条更新 ~50ms/次） | P2 | ✅（合并+延迟） | ✅ 模块 pending overlay + 屏障批量落盘（2026-09-09）；待回归 |
| kp_range_resync | doc_save 成功后同事务 | P0 | ✅（并入 doc_save） | 已并入 `_resync_kp_ranges_after_edit` |
| registry_doc | doc_save 成功后 | P0 | ✅ | 已并入 `_update_registry_for_doc` |
| rename_cascade | 文件/文件夹重命名 | P0 | ❌（独占） | rename_file/rename_dir 已实现 |
| kp_create / kp_update | 用户确认/编辑知识点 | P1 | ❌ | ✅ 2026-09-09 提速（JSON+单文件同步+关窗先于图谱）485ms 保持内联；作业化是否仍需待 M6b 拍板 |
| kp_panel_refresh | ranges_resynced>0 | P2 | ✅ | `_silentRefreshKpPanel` 已落地 |
| preview_range_redraw | 重锚就绪 | P2 | ✅ | 未实现（P2） |
| index_rebuild | 侧车写后（词法）/配置变更（embedding） | P3 | ✅（合并） | ✅ M3 后台化（2026-09-09）：锁+合并 daemon 重建，写路径不阻塞；search/切库/关库前 wait |
| graph_build | 显式“构建” | P3 | ✅ | 手动 |
| cleanup / validate / image_auto_check | 显式 / 长间隔 | P3 | ✅ | 定时/手动 |
| file_tree_refresh | 树/结构变更 | P2 | ✅ | refreshFiles |

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
