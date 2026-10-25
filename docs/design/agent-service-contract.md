# Memoria Agent 服务层调用约定（0.5.0-S2 / task-121）

> **本文件是"调用约定"，不是某个模块的规格说明书**（R-S2-15）。S2 的产出是**约定 + 可证明会拒绝的 fixture**，
> 不新建 facade 模块：写侧契约面 = `apply_plan(origin=…)` 签名 + `approvals.WRITE_CAPABILITY` + 稳定错误码；
> 读侧契约面 = `section_index` 的四个函数与其错误码。
> **验收**：W1–W4 各 1 条必红 fixture，见 `scripts/benchmark/maintenance/contract_w{1,2,3,4}.py`。
> **本文件每一条都对应已落地代码或已登记缺口** —— 文档承诺未实现的行为，本身就是新的「静默默认」。

## 1. fan-in / fan-out

### 1.1 读侧 fan-in（三路收口到一处实现）

| 接口 | 语义 | 底层 fan-in | 预算 | 失败语义 |
|---|---|---|---|---|
| `outline(file, max_tokens=800)` | 标题树 + 行号区间 + 块计数 | `section_index.build_outline` | ≤800 tok | `NO_HEADINGS` |
| `section(file, heading\|line, path?, near_line?, level?, part?)` | 单节正文 | `section_index.get_section` / `get_section_part` | ≤4,000 tok/片，`part i/n`+cursor | `SECTION_NOT_FOUND` / **`AMBIGUOUS_SECTION`（不取首个）** / `INVALID_SELECTOR` / `NO_HEADINGS` / `INVALID_LEVEL` |
| `snippet(file, query\|line, ctx=±3)` | 命中窗口 | `section_index.get_snippet` | ≤600 tok | `UNSUPPORTED` |

**读后写（W2）的观察口径**：`outline` / `section` 读成功即记一次观察；**`snippet` 不记**
（片段窗口 = 指针，与 `grep`/`glob`/`search_kb` 同口径"不构成看过这个文件"）。
该口径写死在 `tools/kb.py::_granular_read_tools` 的 docstring 里 —— 未来给 snippet 补观察会把
「snippet→写」这条本应要求再读的路径悄悄放开（R-S2-1 的接缝修复就栽在这类静默默认上）。

### 1.2 写侧 fan-out（**两层，不能画成一条链**）

```
【工具分发层】（registry.invoke → tool handler 之前）
  _observation_block  ──►  W2：observation.gate_ops()           ← tools/kb.py
  approval.decide     ──►  W4：GuardedPolicy / write_is_risky    ← 分发前问
  issue_clearance     ──►  W1：过闸后签发一次性清关令牌          ← observation.py

【计划执行链】（工具 handler 内部）
  propose_write(plan)
    ├─► validate_plan     （结构 + 语义校验，任一错误拒整批）
    ├─► compile_plan      （原语序列，17 个已编译 op）
    └─► apply_plan(origin=…)
           ├─► W1：origin 合法性 + agent 令牌消费（**备份之前**）
           ├─► W3：snapshot_pre_images（失败 ⇒ 零写入）
           ├─► 原语执行 → 写后哈希 → 审计
           └─► restore_batch（可整批撤销，逐字节回 pre-image）
```

- **W2 与 W4 不在计划执行链上**：它们在**工具分发层**。⇒ 直接调 `apply_plan` 不经过它们
  （这正是 §3.2 把 `origin` 提升为**函数必填参数**的原因：让"绕过入口"至少变成显式撒谎，而不是静默漏检）。
- **W3 在 `apply_plan` 内部**（`snapshot_pre_images` 是该函数第一步）。
- **人类路径**：`ui.agent_plan_apply` 直接调 `apply_plan(..., origin="human")`（确认卡点"应用"），
  不经过 agent 的读后写闸（观察表按 `session_id` 记账，人类路径的 `ui-plan` 会话必然为空）。

## 2. 错误码（稳定，改名即破坏契约）

### 2.1 计划层与写入层

| 码 | 层 | 触发 | 调用方可做什么 |
|---|---|---|---|
| `invalid_plan` | 计划层 | 计划**总类**失败，`errors[]` 带子码 | 按子码逐一修 |
| ├ `bad_plan_version` | 子码 | `plan.v` 不是 `1` | 补 `v:1` |
| ├ `missing_field` | 子码 | 缺 `op_id` / `txid` / 某 op 必填字段 | 补字段 |
| ├ `empty_text` | 子码 | `replace_lines`/`insert_lines` 的 `text` 为空 | 改用 `delete_lines` |
| ├ `overlapping_edits` | 子码 | 同批两条编辑行区间重叠 | 拆批或合并 |
| └ `expect_mismatch` | 子码 | `expect` 与当前正文不符 | 重读文件再提 |
| `file_ops_must_be_last` | 计划层 | 文件级 op 之后还有别的 op | 调整顺序 |
| `ambiguous_section` | 计划层 | `replace_section` 同名多候选且无法消歧 | 补 `path` / `near_line` |
| `backup_failed` | 写入层 W3 | 写前备份失败 / 批次目录已存在（**同 txid 重放**） | 换 txid 或查已有批次 |
| `WRITE_GATE_BYPASS` | 写入层 W1 | `origin="agent"` 但无有效清关令牌 | 走 `propose_write` 提交 |
| `WRITE_ORIGIN_REQUIRED` | 写入层 W1 | `origin` 为空/未知值（漏传则是 `TypeError`） | 调用点显式声明 `agent`/`human` |
| `APPROVAL_REQUIRED` | 审批 | 核心写能力 + `approval=auto`（或注入策略拒绝） | 改用 `confirm` 档 |

### 2.2 读侧

`SECTION_NOT_FOUND`（带 `suggestions`）/ `AMBIGUOUS_SECTION`（带 `candidates`，**不取首个**）/
`INVALID_SELECTOR` / `NO_HEADINGS` / `INVALID_LEVEL` / `UNSUPPORTED`。

### 2.3 观察闸（W2）

`FS_NOT_OBSERVED`（未读就写）/ `FS_NOT_FOUND`（读到"不存在"后又要改）/ `FS_STALE_VERSION`（读后被外部改）。

> **稳定承诺**：上表每一码改名都是破坏性变更；新增码只能**追加**并登记进本节。

## 3. W1–W4 可测断言（各 1 条必红 fixture）

### 3.1 W2 读后写守卫（`observation.py`，已接线）
- **机制**：`observation.gate_ops()` 在 `propose_write` 的 `_observation_block` 处裁决；观察源 =
  `read_document` / `read_kp` / `read_outline` / `read_section`。
- **进程内、不落盘**：新进程/新会话空表，resume 后必须重读。
- **必红 fixture**（`contract_w2.py`）：未读就写 ⇒ `FS_NOT_OBSERVED`；`section` 后写**必须放行**；
  `snippet` 后写 ⇒ 仍 `FS_NOT_OBSERVED`；读后被外部改 ⇒ `FS_STALE_VERSION`
  （版本号必须用真实 `rel_version`，空串会被误判成 STALE）。

### 3.2 W1 入口唯一 + `origin`（R-S2-8，**已实现**）

```python
apply_plan(..., *, origin: str)     # 无默认值 ⇒ 漏传 = TypeError（签名级 fail-closed）
```

- 调用点：`tools/kb.py` → `origin="agent"` + `gate_token`；`ui.py` → `origin="human"`。
- `origin` 为空/未知 ⇒ 拒 `WRITE_ORIGIN_REQUIRED`（**不得默认成 human**）。
- `origin="agent"` ⇒ 必须携带 **一次性清关令牌**（`observation.issue_clearance` 签发、
  `consume_clearance` 消费）；缺失/无效/已用过 ⇒ `WRITE_GATE_BYPASS`，且**在任何备份与写盘之前**拒。
- **为什么用参数而非 plan 字段**：plan 由前端构造并经 `agent_plan_apply` 传回，是**不可信输入**，
  省略字段即绕过（arch-contract 实测过 fail-open）。函数参数由**调用点**决定，漏传在签名层就是 `TypeError`。
- **诚实边界（不许再写成"不可绕过"）**：
  1. 令牌强度上限 = 「`gate_ops` 曾通过」，**不是**「agent 真的读过」——
     `observation.record_read()` 是公开函数，恶意模块可伪造"读过"再拿令牌；
  2. 进程内**无法区分**"真正的人类 UI 调用"与"显式传 `origin="human"` 的恶意调用"。
  ⇒ W2/W1 防的是**无意绕过（漏调闸）**，不是恶意模块；真正的强制边界在**进程边界**（S3 MCP）。

### 3.3 W3 写前备份
- `apply_plan` 第一步 `backup.snapshot_pre_images()`，失败 ⇒ **零写入**返回 `backup_failed`；
  每批可 `restore_batch()` **逐字节**回 pre-image。
- **必红 fixture**（`contract_w3.py`）：构造备份失败 ⇒ 整批不写；写成功后 `restore_batch` 逐字节一致。

### 3.4 W4 审批：**两处保护，等级不同**（R-S2-10）

| 侧 | 保护 | 时机 | 强度 |
|---|---|---|---|
| **插件声明** | `permissions.write` 非空 ⇒ `approval.write ≠ auto` | **装载期**硬拒（`plugins.py`） | 强（装不进来） |
| **核心写能力** | `approvals.WRITE_CAPABILITY.require_approval()` | **运行时**（分发前）判定 | 弱（调用点自己按档问） |

- 实测 `RISKY_OPS = {rename_file, delete_file, move_file, delete_kp, rename_kp}`：`replace_lines` /
  `insert_lines` / `replace_section` / `upsert_kp` / `create_file` 在默认 auto 档**全部不问人**。
- **明确否决"把这些 op 加进 RISKY_OPS"**：那等于 agent 每改一行都停下问人 ⇒ 功能不可用（R-S1A-2 同款裁决）。
  ⇒ 改用 `approvals.WRITE_CAPABILITY` 把"我要什么权限"**显式化且可查询**；
  **S3 MCP 入口强制要求声明**，内置 agent 路径不受影响。
- **必红 fixture**（`contract_w4.py`）：核心写能力 + `approval=auto` ⇒ 分发前 `APPROVAL_REQUIRED`；
  插件声明 `permissions.write` 非空 + `approval.write=auto` ⇒ 装载期拒（两条**等级不同**，都要红）。

## 4. 幂等（**按当前实际行为写；含一条已知缺口**）

- **写幂等：❌ 不幂等 —— 当前行为是"重复 txid 直接拒绝"**
  - 实测：同一 `txid` 第二次 `apply_plan` ⇒ `{"status":"error","code":"backup_failed",
    "message":"批次已存在：<txid>"}`（批次目录存在性即天然去重键）。
  - 定性：**这是"拒绝"，不是"幂等"**。调用方不得把"重放"当作安全重试（重放会失败，且不返回上次结果）。
  - 如实的好处：因为拒绝，**不会重复写盘** —— "重复应用"这个最坏后果不会发生。
  - 缺口：无法"重放拿到相同成功结果"。真幂等（`duplicate_txid` + 已应用集记录）**未实现**，
    本文件**不承诺**。
- **读幂等**：`outline`/`section`/`snippet` 无副作用，同输入同结果（预算/截断确定性已在 A11 验证）。
- **观察幂等**：`record_read` 重复记同一 `(rel, sha)` 不改变闸的裁决。

## 5. 版本策略（不建 facade 模块：R-S2-9/15）

- **写侧契约面**（承诺"只增不改"）：
  `apply_plan` 的 `origin` 必填参数与其取值域、`gate_token` 语义、
  `approvals.WRITE_CAPABILITY` 与 `CODE_APPROVAL_REQUIRED`、以及 §2 的错误码集合。
  **必填参数一旦引入不得回退为可选**（那是把 fail-closed 悄悄改回 fail-open）。
- **读侧**：**不抽 facade**（R-S2-9）。`section_index.{build_outline, get_section, get_section_part,
  get_snippet}` 与 `tools/kb.py` 三把读工具就是契约面，其错误码直接承诺。
  **延迟抽取的触发条件**：S3（MCP 薄绑定）需要以**非 Tool 形态**暴露读侧时，按真实调用形态再抽。
- **内部实现不承诺**：`observation` / `backup` / `approvals` 的内部结构可变，但 §3 的**行为**被 fixture 钉住。
- 新增错误码必须登记进 §2。

## 6. 已知缺口（随实现填，不留到验收）

1. **W1 的边界**：`origin` 是**调用点自述**，不是可信身份；进程内无法区分"人类 UI"与"撒谎的 human"
   （见 §3.2 诚实边界）。真正的强制边界在进程边界（S3）。
2. **W4 的等级差**：核心写能力只有"运行时策略判定"，没有插件那样的"装载期硬拒"（§3.4）。
3. **读侧 fan-in**：工具层直接调 `section_index` —— 这是 R-S2-9 的**既定架构**，不是待补缺口。
4. **§4 写幂等**：当前是"重复 txid 拒绝"，真幂等未实现。
5. **状态字段无消费者**：`plugins.py` 的 `gate` / `constrain` 仍是**解析但不求值**的死字段
   （R-R1 已裁；S4/task-123 才做投影消费者）。本契约不依赖它们。
