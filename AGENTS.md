# AGENTS.md — Memoria 多 Agent 协作与调度契约

> **用途**：定义 Memoria 仓库内多 Agent 协作的**最小基础集**、事件契约、权限隔离与**可插拔扩展接口**。
> **目标读者**：SOLO 主控 Agent（Trae）与所有子 Agent；人维护者可据此复核。
> **关联文档**：[AGENT.md](AGENT.md)（边界/单一事实源/常见陷阱）、[collaboration.md](docs/guides/collaboration.md)（协作规则）、[maintenance-jobs.md §5](docs/design/maintenance-jobs.md)（作业登记表）、[to-dolist.md §12](docs/to-dolist.md)（门禁台账）。
> **状态**：生效中，2026-09-10。本文件不重复既有规范；冲突时以 `docs/conventions/**` 与 [AGENT.md](AGENT.md) 为准。

---

## 0. 平台硬约束（不可绕过）

- 只有 **SOLO 主控 Agent** 能识别触发条件并调用子 Agent；**子 Agent 不得调用其它子 Agent**。
- 每个子 Agent 拥有**独立隔离上下文**；其内部推理**不会回传**主控。跨 Agent 交接**只能**通过「磁盘产物 + 事件记录」完成，**禁止依赖对话记忆**。
- 因此"事件订阅"是**声明式**的：子 Agent 在注册表声明订阅，由**主控**在事件到达时派发。

## 1. 单一事实源（Single Source of Truth）

| 类别 | 唯一来源 | 写权限 |
|---|---|---|
| 边界/禁止行为 | [AGENT.md](AGENT.md) §6、`docs/conventions/**` | 人（Agent 只读） |
| 范围/门禁台账 | [to-dolist.md §12](docs/to-dolist.md) | `registrar` |
| 作业登记 | [maintenance-jobs.md §5](docs/design/maintenance-jobs.md) | `registrar` |
| 文档索引/登记 | `docs/README.md` 及各级 README、`docs/conventions/docs-management.md` | `registrar` |
| 版本号 | `src/memoria/__version__.py` | 人（Agent 只读） |
| 产品状态 | 各知识库 `.memoria/**`（manifest/sidecars/pending/images） | 应用代码 |
| Agent 注册表 | `artifacts/agent/agents.json` | `registrar` |
| Agent 事件流 | `artifacts/agent/events.jsonl` | 主控（追加） |

- 新增事实源必须先在本表登记；**禁止并行事实源**。`.memoria/cache/**` 视为**可再生缓存**，不作为事实源。

## 2. 基础 Agent 集（RISC，仅 3 个）

> 业务关注点（F01–F03 维护、图片注册表、重命名级联、图谱构建、i18n、打包、检索评测等）**一律作为 `builder` 的作业或工具**，并登记进 [maintenance-jobs.md §5](docs/design/maintenance-jobs.md)，**永不新增独立 Agent**。

### 2.1 builder（构建者）

- **职责**：在**已批准范围**内实施 `src/**`、`docs/**` 内容、`scripts/**` 的变更；变更前后读写**真实文件**，不信任缓存；产出变更事件与自测结果。
- **禁止**：自判门禁通过；改 `Package/**`；手改 `pyproject.toml` 版本；覆盖用户知识库原文；改登记表/索引；`push` 或强推。
- **权限**：Read 全库；Write 限 `src/**`、`docs/**`（非登记类）、`scripts/**`；RunCommand 限 [AGENT.md §3](AGENT.md) 命令；非破坏性 git（`commit` 需用户授权）。
- **触发条件**：① 收到已批准变更任务（含范围+边界+验收标准）；② 收到 `verify.result{pass:false}` 的返工派发。
- **提示词**：`artifacts/agent/prompts/builder.md`。

### 2.2 verifier（验证者）

- **职责**：独立执行仓库**自带验证阶梯**并出证据；**只依据磁盘产物**判定。
- **验证阶梯**（按需执行，产物必须留存）：
  - **L0 静态**：`python -m py_compile <file>` / `node --check <file>`
  - **L1 内核单测**：`node scripts/benchmark/maintenance/scheduler_vm_test.js`、`m6b_adjust_test.js`
  - **L2 A/B（改善类强制，依 to-dolist §12）**：`anchor_baseline.py`、`run_l1.py`、`compare_ab.py`
  - **L3 回归**：`regression_smoke_m6a.py`、`crash_inject_m6a.py`
  - **L4 交互**：[rich-content-test/_harness.py](docs/example/rich-content-test/_harness.py)（[AGENT.md](AGENT.md) Always 要求）
- **禁止**：修改 `src/**` 或 `docs/**`；自行实现修复；引用未落盘的口头结论；接受"无证据的 ✅"。
- **权限**：Read 全库；Write 限 `artifacts/agent/verify/**`、`scripts/benchmark/maintenance/results/**`；RunCommand 限上述验证命令。
- **触发条件**：① 收到 `change.applied`；② 到达门禁检查点；③ 用户显式要求复核。
- **提示词**：`artifacts/agent/prompts/verifier.md`。

### 2.3 registrar（登记官）

- **职责**：维护**单一事实源**（索引/登记/台账）；执行**漂移审计**（见 §5）。
- **禁止**：改代码；改文档正文语义；覆盖用户手改；擅自"顺手修复"漂移（只上报 `state.drift`）。
- **权限**：Read 全库；Edit **仅**登记类文件白名单（§4 矩阵中"写权限=registrar"者）；Write 限 `artifacts/agent/**`；RunCommand 限 `scripts/scan_ui_strings.py`、`scripts/i18n_selftest.js` 等自检脚本。
- **触发条件**：① 收到 `verify.result{pass:true}`；② 新建文档/作业/i18n 键；③ 定时漂移审计；④ 门禁收口前。
- **提示词**：`artifacts/agent/prompts/registrar.md`。

## 3. 事件契约（不可变信封）

```jsonc
{
  "v": 1,                       // Schema 版本；仅破坏性变更才 +1，旧读者必须能忽略未知字段
  "id": "evt_<sha16>",          // 唯一
  "ts": "2026-09-10T02:11:00Z",  // ISO-8601 UTC
  "type": "change.applied",      // 见下表
  "actor": "builder",            // 仅注册表内 agent-id 或 "solo-controller"
  "subject": { "kind": "file|job|doc|kb", "ref": "src/…/ui.py" },
  "priority": 0,                 // P0 一致性 / P1 交互 / P2 派生视图 / P3 后台重活
  "epoch": 7,                    // 快照版本；语义对齐 scheduler.js 的 epoch
  "corr": "task_20260910_a1",    // 关联一次任务的全部事件
  "payload": { },                // 类型专属，只增不改
  "prev": "evt_<sha16>|null",    // 哈希链前驱
  "digest": "sha256:…"           // 对 (prev + 本事件除 digest 外) 规范化后求哈希
}
```

| type | 发出者 | payload 关键字段 |
|---|---|---|
| `task.dispatched` | 主控 | `task`, `scope[]`, `boundaries`, `acceptance[]`, `assignee` |
| `change.proposed` | builder | `intent`, `stages[]`, `asks[]`（Ask First 命中项） |
| `change.applied` | builder | `files[]{path,action,±lines}`, `diffstat`, `self_checks[]`, `commit` |
| `verify.result` | verifier | `gate`, `checks[]{name,cmd,result,artifact}`, `pass`, `ab{baseline,after,delta}` |
| `register.updated` | registrar | `ledgers[]{file,section,action}`, `index_synced[]`, `i18n_keys[]` |
| `state.drift` | registrar | `claims[]{doc,line,claimed,actual}`, `severity`, `product{}` |
| `task.completed` | 主控 | `task`, `gate`, `snapshot_tag`, `events[]` |
| `agent.registered` | 主控 | `id`, `triggers`, `permissions` |

**向后兼容铁律**：① 信封字段名/类型永不改；② 新 `type` 对旧订阅者=未知→忽略；③ payload 只做**追加**，不重命名/不删键；④ 事件**只追加、永不改写/删除**（更正靠新增事件）。

## 4. 权限隔离矩阵

| 路径域 | builder | verifier | registrar | 主控 |
|---|---|---|---|---|
| `src/**`、`scripts/**`（非 results） | R/W | R | R | R |
| `docs/**` 正文 | R/W | R | R | R |
| `docs` 登记类（README 索引 / §5 登记 / docs-management 表 / to-dolist §12 台账） | R | R | **R/W** | R |
| `scripts/benchmark/maintenance/results/**`、`artifacts/agent/verify/**` | R | **R/W** | R | R |
| `artifacts/agent/events.jsonl` | R | R | R | **R/W** |
| `artifacts/agent/agents.json` | R | R | **R/W** | R |
| `Package/**`、`pyproject.toml`(version)、`__version__.py` | — Never — | — Never — | — Never — | — Never — |

## 5. 一致性校验（漂移处理）

1. **哈希链**：逐行重算 `digest` 并校验 `prev` 串联 → 检出篡改/半包写入。
2. **投影一致性**：由 `events.jsonl` 重建 `state.json` 与磁盘现存比对 → 检出 `state.json` 被外部手改。
3. **断言—现实比对**：台账/§5/README 中带证据锚（✅ + 产物路径）的声明，校验其引用的 `artifacts/agent/verify/**`、`results/**` 是否存在且 `pass=true`。
4. **产品状态校验**：复用 `validate_kb` / `audit_manifest_diff` / `detect_path_moves`（**dry-run**）产出 `product{}`，检出 sidecar/md/manifest 漂移。

任一失败 → 发 `state.drift` 并**停止推进**，由主控按 [collaboration.md](docs/guides/collaboration.md) 规则 2（带 2–4 选项 + 推荐）请示用户，**不得静默覆盖用户手改**。

## 6. 扩展接口：新增可插拔 Agent（不改任何既有定义）

新增 Agent 只需两步，**无需修改 builder/verifier/registrar 的提示词或工作流**：

```yaml
# === 追加到 artifacts/agent/agents.json 的 agents[] 数组（唯一改动点）===
- id: linter                      # 英文标识（唯一）
  name: 静态检查员                 # 中文名
  # —— 触发条件（主控据此自动派发；支持事件驱动 / 定时 / 用户显式触发）——
  triggers:
    on_events: [ "change.applied" ]   # 订阅事件：新 Agent 只需订阅，无需改既有流程
    on_schedule: "0 3 * * *"          # 可选：定时（漂移审计类）
    on_user_keywords: [ "lint" ]      # 可选：用户显式触发
  # —— 输入/输出契约（通过磁盘交接，不共享上下文）——
  io:
    input:  [ "change.applied.payload.files" ]    # 读什么
    output: "artifacts/agent/verify/lint/*.json"  # 写什么（事件由主控代发）
  emits: [ "verify.result" ]          # 它会产出的事件类型
  # —— 权限隔离：必须显式声明，越界即拒绝 ——
  permissions:
    read:  [ "src/**", "docs/**" ]
    write: [ "artifacts/agent/verify/lint/**" ]
    exec:  [ "ruff", "npx eslint" ]
  # —— 禁止行为：与平台/仓库红线对齐 ——
  forbidden: [ "edit src/**", "edit docs/**", "git push" ]
  prompt_ref: "artifacts/agent/prompts/linter.md"   # 提示词独立文件，互不污染
```

- 主控在每次事件落盘后扫描 `agents.json` 中 `triggers.on_events` 命中者并派发；**派发逻辑与既有 Agent 无耦合**。
- **卸载**：仅从 `agents.json` 移除条目；其历史事件保留在 `events.jsonl`（只读可追溯）。

## 7. 风险与调试

- **令牌控制**：派发包只含"路径 + 事件 id + 验收标准"，**禁止回灌历史对话**。
- **调试**：`artifacts/agent/events.jsonl` 按 `corr` 过滤即得单任务全链路；`artifacts/agent/drift-report.json` 定位失同步。
- **验证命令**：见 §2.2 阶梯；应用侧可用 `[job]` 日志与 `MemoriaScheduler.counters()` 观测。
- 常见陷阱见 [AGENT.md §7](AGENT.md)。
