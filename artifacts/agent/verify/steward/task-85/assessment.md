# task-85 只读评估：图谱审计启动重复跑（是否值得做缓存）

> **执行**：steward（只读分析，**未改任何产品代码**）；**时间**：2026-10-26T08:5x+08:00
> **结论先行**：**不建议按原方案做"mtime+size 签名缓存"**。原任务的两个前提已被 task-84 改变：
> ①「0.3s 在关键路径」**已不成立**（task-84 已把 `validate_kb` + `loadGraphData` 移出 bootAutoOpen 关键路径）；
> ② 缓存失效判据的正确性风险 vs 剩余收益（≈0.37s **后台** CPU）不成比例。
> 建议：**降级/关单**；若仍要省，优先做"启动只跑 1 次审计"的零风险改动（需前端配合，另立任务），而不是加缓存。

## 1. 现状核实（2026-10-26 亲测）

- `audit_kb_graph_links` 全仓 **4 个调用点**：
  - `graph/kb_build.py:325`（显式 build 时，非启动路径）
  - `services/document.py:2131` `get_graph_data()`（**启动路径** `loadGraphData()`，app.js:1728）
  - `services/document.py:2152` `get_graph_audit()`（检查弹窗/按需）
  - `services/document.py:2184` `validate_kb()`（**启动路径** `validate_kb_async`，app.js:1116）
- **实测单次成本**（baseline KB「数字通信原理」29 md 文件）：**369.6 / 368.9 / 381.6 ms**（3 次）。
  ⇒ 启动期 2 次 = **≈0.74s 后台 CPU**（不是 0.6s，且比 task-85 记录的 306ms 更慢）。
- **P1 去重已生效**：`submitAsyncValidate()` 与 `scheduleSilentValidate()` 都走 `validate_kb_async`，
  后端 `coalesce_running=True`（task-69 P1，`boot-p1-executor-coalesce.log`）⇒ 同一 kind+key 不会重复跑。
  所以 task-85 说的"跑 3 次"现在实际是 **2 次**（validate 1 + graph_data 1），不是 3 次。
- **关键路径已被 task-84 移除**：task-84（completed，writeScopes `app.js`/`kb-check.js`）把 `validate_kb` 与
  `loadGraphData` 移出 `bootAutoOpen` 关键路径；`app.js:1082` 注释也明确 `runKbValidate ≈1026ms` 是旧的同步路径，
  新路径用异步提交 + 轮询。
  ⇒ **缓存对"首屏/自动打开首个文件"的端到端时间收益 ≈ 0**；只省启动后台 CPU（与首屏渲染抢 CPU 约 0.37s）。

## 2. "mtime+size 签名缓存"能不能做对？（可行性/风险）

- **输入全集**需要覆盖：所有 md 的**内容**、sidecar 内容、以及 `build_target_kp_resolver(kb_path)` 读取的对象
  （kp id/别名/链接目标解析依赖，需逐一确认，容易漏）。
- **保守判据的最低要求**：
  1. 键 = 排序后的 `(rel, size, mtime_ns)` + sidecar 同构 + resolver 输入；
  2. **TOCTOU 双检**：审计前后各算一次键，只有两次一致才写入缓存（否则宁可不命中）；
  3. 负例 ≥4 类（改 md / 改 sidecar / 增删文件 / 改链接目标）必须失效。
- **仍然存在的错误命中面**：① 同 size + 同 mtime_ns 的替换（git checkout/恢复/rsync 可发生）；
  ② resolver 读取了未纳入键的文件；③ 审计进行中文件被改（双检可挡，但要读两遍）。
- **错误代价 vs 收益**：错误命中 ⇒ 用户看到**错误的断链告警**（"文档链接坏了"），
  比 0.37s 后台 CPU 严重得多；而 task-85 自己写的优先级规则（"若端到端已 ≤2500ms 这条降为 P2"）
  在 task-84 之后应直接判为 **收益不足**。

## 3. 若仍要"启动只算 1 次"，零风险的替代（推荐给 Lead 决策）

**方案 A（推荐，零缓存风险）**：`get_graph_data` **不再内联审计**，只返回图数据；
前端改为在首屏后空闲时调用 `get_graph_audit()`（RPC 已存在）再刷新 "图谱告警"侧栏。
- 收益：启动期审计 2 次 → 1 次（省 ≈0.37s 后台 CPU），无失效判据、无错误命中风险；
- 代价：图谱告警提示延后到空闲请求（用户几乎无感）；需改 `ui/static/**`（**不在 task-85 写域**，应另立任务且归 UI Owner）。
**方案 B**：validate 的结果复用给 graph_data —— 本质仍是缓存（同 §2 风险），不推荐。

## 4. 结论与建议

1. **task-85 按原方案（服务层 mtime+size 缓存）不建议做**：前提（关键路径 0.3s）已被 task-84 推翻，
   剩余收益 ≈0.37s 后台 CPU，风险是用户可见的错误断链告警 + 缓存维护成本；
2. 建议 **关闭 task-85**（或降为"won't fix / 记录在案"），并在台账写清"task-84 已移除关键路径收益"；
3. 若 Lead 仍想省这 0.37s：另立 **方案 A**（前端惰性 `get_graph_audit`）任务，写域 `ui/static/**`，
   验收 = 启动期 `audit_kb_graph_links` 调用计数 2→1 + 无告警回归；
4. 无论哪条，**都必须先测负例**（task-85 已列 4 类），且**禁止用跳过审计换速度**。

## 5. 复跑（只读）

```powershell
python artifacts/agent/verify/steward/task-85/eval.py   # 成本实测 + 调用点/前端路径盘点
```

## blind_spots

- 未测完整端到端 boot（需起服务/探针；本轮只测单次审计成本与调用点静态证据）；
- 未逐一核对 `build_target_kp_resolver` 读取的全部输入（若要实施缓存，必须先做这一步）；
- 未评估 P0-a lexical cache 对 audit 的影响（两者是不同缓存，未串联验证）。
