# 持久化 flush 屏障（durable_flush）设计方案

> 状态：**草稿（待评审）**，2026-09-09。
> 关联：[maintenance-jobs.md](./maintenance-jobs.md)（作业模型/登记表）；[to-dolist.md §12](../to-dolist.md)（G4/M6a 门禁）；[maintenance-benchmark.md](./maintenance-benchmark.md)（A/B 依据）。
> A/B 依据：[results/compare_ae66a012_d1894ba1.md](../scripts/benchmark/maintenance/results/compare_ae66a012_d1894ba1.md)（2 轮 ABBA：base 158.6ms vs HEAD 180.5ms，**+13.8%**）。

## 1. 背景与目标

`save_document`（M1 起）正文写为 `tmp + flush + os.fsync + os.replace`，每次保存强制 fsync。同盘微基准 fsync 约 +10–22ms/次，与 A/B 的 Δ~22ms 吻合 → **fsync 是 ~15% 保存回退的直接来源**（刻意安全成本，非 bug）。

目标：**把"落盘持久化"从每次保存内联，收拢为调度内核的 `durable_flush` 屏障作业**——正文写降级为 `tmp + os.replace`（进程崩溃安全、立即返回），fsync 只在**显式保存 / 文件切换 / 关库 / 退出**屏障批量执行。附带把 `manifest_touch`（~50ms/次，保存绝对大头）批量合并。

## 2. 现状

| 环节 | 现状 | 成本 |
|---|---|---|
| 正文写 | `tmp+fsync+os.replace`（内联） | ~10–22ms |
| manifest 单条 touch | `load_manifest` + 改 1 条 + `save_manifest`（原子 yaml 全量写） | ~50ms/次（分项剖析中位数） |
| registry / KP resync | `save_document` 内联 | ~10ms + ~8ms |

保存路径合计中位数 ~77ms（60 文件合成语料 clean 环境）。

## 3. 目标模型：写盘两级

1. **候选写（candidate）**：`tmp + os.replace`。进程崩溃/中断安全（旧文件或新文件二选一，无半包）；立即返回。
2. **持久化（durable）**：对候选写后的目标文件执行 `os.fsync`（打开文件 handle fsync）。只在屏障执行。

```text
编辑 → 自动保存(save_document: tmp+replace, 记入 dirty 集)
   → [显式保存 | 切文件 | 关库 | 退出] 屏障
       → durable_flush 作业: 对 dirty 集逐个 fsync → 清空
```

## 4. 后端实现要点

- `DocumentService` 增加进程内 **dirty 集**（`set[str]`，正文路径）与锁。
  - `save_document(rel, body)`：写 `tmp+os.replace`；把 `rel_norm` 加入 dirty 集；`bench_ms` 增加 `durable_deferred` 标记（`MEMORIA_BENCH_TIMING=1`）。
  - `durable_flush()`：遍历 dirty 集，对每个文件 `open(...,'rb')` 后 `os.fsync(f.fileno())` 或按 handle 打开写句柄 fsync；成功后清空集合；返回 `{flushed:n, ms}`。任何文件失败保留在集合重试。
  - 显式"保存"路径与各**写 sidecar/manifest 的关键写**保持原有即时持久化语义（见打开问题 Q1）。
- **RPC**：新增 `flush_durable`；在 RPC 层与 `beforeunload`/host 退出钩子衔接。
- **兼容开关**（A/B 用）：`MEMORIA_FSYNC_MODE=inline|barrier`（默认 barrier 后续版本切换；inline 保留旧行为；off 仅供测量）。
- 词法/embedding 等重活仍按 M3 独立后台化，不在本文档范围。

## 5. 前端屏障触发点（候选）

| 屏障事件 | 处理 |
|---|---|
| 显式保存（工具栏/快捷键保存） | `flush_durable()` 同步等待（用户预期"已保存"=已落盘） |
| 文件切换（openFile / tab 切换 / nav） | 切换前调用 `flush_durable()`（复用现有 flush 队列语义） |
| 关闭知识库 closeKb | 同步 flush |
| 应用退出（beforeunload / host close） | 尽力同步 flush（WebView 关闭窗口有超时上限，超时放弃） |
| 连续编辑长 idle | 不设自动 fsync（保持 barrier 语义） |

## 6. manifest_touch_batch（并入同一屏障还是独立防抖）

- 方案 A（并入屏障）：`save_document` 只更新内存 entries + 标记 `manifest_dirty`，`durable_flush` 一次性写 manifest —— 每次保存省 ~50ms，切文件/关库时付一次全量写。
- 方案 B（独立防抖）：保存后 debounce ~2s 合并写一次 manifest，不等屏障（减少"切文件时才突然写"的长尾）。
- 建议 **A 为主 + B 的防抖作为长 idle 兜底**（参考打开问题 Q2）。
- 影响面梳理：`touch_manifest_entry` 调用点（save_document / _write_sidecar / rename 等）在批量化后需保证顺序一致（后写覆盖先写、remove 与 add 合并）。

## 7. 崩溃语义分析（对照 M1）

| 崩溃类型 | M1（内联 fsync） | 本方案（barrier fsync） |
|---|---|---|
| 进程崩溃/写入中断 | 完整新文件或旧文件 | 同左（`tmp+os.replace` 保证） |
| 掉电（电源丢失） | 新内容已 durable | 自动保存后、屏障前掉电 → 可能回退到上次屏障内容（**有窗口**） |
| 编辑器侧影响 | — | 需保留"脏/未持久化"状态提示或依赖自动保存防抖（打开问题 Q3） |

取舍：崩溃窗口只影响**自动保存的最新一次**；显式保存与切文件/关库仍即时 durable。符合"编辑过程高频自动写可容忍极短掉电窗口，关键动作 durable"的产品语义。

## 8. 验证对照（出口门禁，G4 M6a）

| 项 | 手段 | 通过标准 |
|---|---|---|
| L1 A/B | `MEMORIA_FSYNC_MODE=inline` vs `barrier`（同 build）跑 run_l1/compare_ab | barrier 相对 inline 的 median Δ 显著下降，接近基线 ae66a012 水平（预期找回 ~20ms+）；记录进 results |
| 崩溃注入 | 半程 kill 写进程后重启：无半包正文（沿用 M1 中断脚本扩展） | PASS |
| 屏障生效 | 切文件/关库/退出后重开：最近内容存在；dirty 集收敛为空 | `[真机]` + 脚本断言 |
| manifest 批量 | 连续保存 N 次：manifest 只落盘 1 次（计数断言）；文件可读 | PASS |
| 回归冒烟 | rename-test / showcase 临时副本全流程 | PASS 后再 commit `G4` |

## 9. 打开问题（评审拍板后才施工）

- **Q1** 显式"保存"是否必须即时 fsync？（建议：是，保证用户语义）
- **Q2** manifest 批量采用方案 A（并入屏障）还是 A+B（防抖兜底）？（建议 A+B）
- **Q3** 自动保存与屏障间的掉电窗口是否需要 UI 提示（脏标记/未持久化角标），还是维持静默？
- **Q4** barrier 默认 fsync 模式切换的版本策略：随 G4 一次切换，还是先保留 `MEMORIA_FSYNC_MODE` 开关一段时间？
