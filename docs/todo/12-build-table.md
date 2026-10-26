# §12 知识库与维护机制 · 施工总表 — 活跃详情（原文逐字）

> **本文件是 `docs/todo.md §12` 的活跃详情**（2026-10-26 索引化搬迁，**原文逐字**，未改写）。
> **状态事实源 = `docs/todo.md §12` 索引行**；本文件只放详情（施工总表原文 + 注记）。
> 历史归档（A/D/F 收口、G 认领表）仍在 [design/ledger-archive-2026.md](../design/ledger-archive-2026.md)；验证方法论在 [design/maintenance-benchmark.md](../design/maintenance-benchmark.md) §9，不在此重复。
> 行级锚点：`#b2` `#b3` `#b6` `#b7` `#b8` `#c4` `#e3`；节区：`#intro` `#a` `#d` `#f` `#g` `#h` `#verify` `#residual`。

<a id="intro"></a><a id="a"></a><a id="d"></a><a id="f"></a><a id="g"></a><a id="h"></a><a id="verify"></a><a id="residual"></a>
<a id="b2"></a><a id="b3"></a><a id="b6"></a><a id="b7"></a><a id="b8"></a><a id="c4"></a><a id="e3"></a>

## 原文（逐字，自 docs/todo.md §12 搬迁）

## 12. 知识库与维护机制 · 施工总表（2026-09-09 建立）

> 目的：把「知识库数据一致性 + 维护作业」类机制/任务统一登记为施工总表。设计取向（2026-09-09 用户确立）：**借鉴操作系统手段把维护当「任务/作业」组织** —— 调度内核（优先级/去重/idle/epoch 陈旧丢弃/flush）、写盘分级（缓存+原子替换+延迟批量 fsync 屏障）、后台化与合并、切文件/关库/退出为屏障点。
> **触发点约束（2026-09-10 用户确立）**：维护动作只允许两类触发点 —— **后台（自动、不阻塞交互）** 或 **用户显式**（打开库/刷新/构建/点击）；**交互热路径禁止任何同步重活**。任务立项与评审均以此作业化/屏障语义为考量。详见 [maintenance-jobs.md](design/maintenance-jobs.md)。

### A. 一致性 / 注册内核

A1–A8 整段收口（sidecar 镜像/校验/级联、manifest 基线差分、pending 路径同步、图片注册表、KP range 双端定位 heal、词法索引后台化、原子写、`forward_only` 终点锚修复），已按规则 8.4 出表，见 §10。

### B. 操作 / 作业

| # | 任务 | 现状 |
| --- | --- | --- |
| B2 | 文件夹重命名 `dir_rename`（整树移动 + 逐文件级联） | 🔄 K2 待真机验收（代码与 RPC 齐备，partial 级联失败已上屏；无验收落盘） |
| B3 | F2 快捷键（文件/文件夹，捕获阶段 + 仅拦可见弹窗） | 🔄 K2 待真机验收（`file-tree.js:438-463` 齐备，无验收落盘） |
| B6 | md 相对路径链接在目录重命名时自动改写 | ❌ 已知边界（待扩展）：`document.py:697-780` 仅物理移动 + `apply_path_move`，`storage/path_cascade.py` 全函数不触碰 md 正文 |
| B7 | 导出知识库包（bundle） | ⏳ K3 待评审：design 草稿在案（[export-plan.md](design/export-plan.md) §8 四个打开问题未拍板）；无实现（无 `export_execute`；`index.html:60` 导出菜单仍 disabled） |
| B8 | 构建 `build_kb` 末尾 `openFile(同路径, {skipNav:true})` 跳过 `flushDurableBarrier` → 构建期间**未落盘编辑**（<1.5s autosave 窗口）可能被磁盘内容覆盖 | 🔴 K1 ⚠️ 待运行时确认（静态取证：`app.js` buildKb 末尾 openFile 的 flush 分支被 skipNav 跳过；来源 agent-guide/06 §7） |

### C. 视图 / 静默刷新

| # | 任务 | 现状 |
| --- | --- | --- |
| C4 | 图谱**增量更新**（增量在布局与数据层，非帧绘制；原「局部刷新」表述已修正） | ⏳ K1：G4 拆分后续项，方案 S1–S4 见 `results/g4-gate-summary-2026-09-09.json`；`applyDelta` 零命中，`graph-engine.js:62` 仍整体替换 |

### D. 渲染 / 显示

D1、D2 已收口，见 §10。

### E. 测试 / 文档 / 规范

| # | 任务 | 现状 |
| --- | --- | --- |
| E3 | design：export-plan / maintenance-jobs / durable-flush（草稿，2026-09-09 复核恢复 export-plan；durable-flush 为 G4 M6a 设计） | ⏳ K3 待评审：durable-flush 已评审锁定（`durable-flush.md:3,82-88`）；export-plan 与 maintenance-jobs 仍未拍板 |

### F. §2.5 开放发现 · 待评估补录（2026-09-09 代码复核，均确认存在）

F01（KB 完整性检查/审计 `validate_kb` + 静默检查 + 徽标）、F02（路径漂移检测/修复 `detect_path_moves`/`repair_path_cascade`）、F03（图片引用诊断/修复 `diagnose_image_refs`/`fix_unregistered_image_refs`）均已确认存在并出表（见 §10）；三者后续由 G5.1–G5.3 的后台化/调度化/CLI 补全承接。

### G. 团队任务板 12 条无主任务：认领与顺序（2026-10-23，todo-owner）

> **判定纪律（2026-10-23 新增，Lead 纠正）**：判「过期/已完成」**必须两条都查** —— ① 任务书点名的产物是否存在；② 全仓搜**功能等价物**（换名/换实现也算）。只查 ① 会系统性高估「过期」数量（task-61 即假阴性：任务书点名的 `nav-interactions.json`/`run_nav.py` 不存在，但实交付是 `nav_entries.mjs`）。
> **2026-10-25 移出**：原 12 行认领表与处置汇总已归档 → [design/ledger-archive-2026.md §10.6](design/ledger-archive-2026.md)（原文逐字；腾出版面给 task-134「出生即死」台账与建议条款）。
### H. 待裁决 · 建议新增条款（L10：只建议、不落检查）

> 【**建议新增条款（待裁决）**】UI 追加块必须有 **JS 运行时冒烟**
> **问题**：`assert "xxx" in src` / `node --check` / `pytest` 都只能证明**文本存在与语法合法**，不能证明**代码在 IIFE 里可达**。本轮实证（task-134）：文档资源附件块 headless 全绿（`pytest 1474 passed`、`node --check` 静默、源码断言通过），但**真机从未生效**（拖文档报「只支持图片」，6 天无人发现）。
> **候选做法**：**A** 只对「IIFE 门面 `return` 之后」做静态可达性审计（轻、可自动化；`audit_deadcode.py` 已实证 59 个 JS 全扫可行，输出 `issues` 列表）｜**B** 加真机/JS 运行时冒烟（重，需 Electron 环境）｜**C** 只做文档约定 + code review 清单（最轻）。
> **现状**：A 已由 task-134 的 `audit_deadcode.py` 实证可行（59 个 JS 全扫、`issues: []`）；B 的成本需另估。
> **2026-10-25 Lead 裁决（已回填）**：**不落 A 作为门禁** —— 依 L10，指不到现行条款的发现只能建议新增；`audit_deadcode.py` **允许作为诊断工具手动跑（不进 CI/门禁）**；是否落成条款仍待**人**裁决。
> **待裁决**：选 A / B / C / 不做。按 L10：只建议、不擅自变成检查；落成机检须人裁决。

### 验证机制分配（2026-09-09）

> 该表属**施工期验证方法论**（"每项用什么手段验、通过标准是什么"），按规则 8.3 已移到 [design/maintenance-benchmark.md §9](design/maintenance-benchmark.md)（原地不再维护副本）；通用基线（`py_compile` / `node --check` / i18n `rows=0` 等）以 [AGENTS.md §2.2](../AGENTS.md) 的验证阶梯为准。

**§12 遗留（非门禁项）**：打开库 `sync_kb_pending` 全库扫描 \~1.06s（G5.4 实测）；`kp_panel` 作业在文件切换瞬间偶发 `expected str, bytes or os.PathLike object, not NoneType` 失败（真机 2026-09-10 日志），待排查触发条件。

***
