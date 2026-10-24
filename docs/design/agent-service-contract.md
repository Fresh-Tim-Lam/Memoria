# Memoria Agent 进程内服务层契约（0.5.0-S2 / task-121）

> **状态**：初稿（S2 进行中）。本文件是 `position/agent-arch-position.md §3`「唯一写者 + 四道前置」的落地契约。
> **定位**：把散落在 `tools/kb.py` / `plan.py` / `apply.py` / `approvals.py` / `backup.py` / `observation.py`
> 的"约定"收敛成**可证明会拒绝**的稳定 facade。内部实现可替换；facade 不暴露裸文件路径写入。
> **验收**：W1–W4 各 1 条必红 fixture（构造违规路径 ⇒ 必须拒绝，且先证红有判别力），见 `scripts/benchmark/maintenance/contract_*`。

## 1. fan-in / fan-out

### 1.1 读侧 fan-in（三路收口到一处）

| facade 接口 | 语义 | 底层 fan-in | 预算 | 失败语义 |
|---|---|---|---|---|
| `read_outline(file, max_tokens=800)` | 标题树 + 行号区间 + 块计数 | `section_index.build_outline` | ≤800 tok | `NO_HEADINGS`（空文档） |
| `read_section(file, heading\|line, path?, near_line?, level?, part?)` | 单节正文 | `section_index.get_section` / `get_section_part` | ≤4,000 tok/片，`part i/n`+cursor | `SECTION_NOT_FOUND` / **`AMBIGUOUS_SECTION`（不取首个）** / `INVALID_SELECTOR` / `NO_HEADINGS` / `INVALID_LEVEL` |
| `read_snippet(file, query\|line, ctx=±3)` | 命中窗口 | `section_index.get_snippet` | ≤600 tok | `UNSUPPORTED`（query 与 line 都缺） |

**读后写守卫（W2）的观察口径**（见 §3.1）：`read_outline` / `read_section` 读成功即记一次观察；
**`read_snippet` 不记**（片段窗口 = 指针，与 `grep`/`glob`/`search_kb` 同口径"不构成看过这个文件"）。
**此口径必须写死**：未来有人"顺手"给 snippet 补观察，会把「snippet→写」这条本应要求再读一次的路径悄悄放开。

### 1.2 写侧 fan-out（一体入口，内部链固定）

```
propose_write(plan)  ──►  validate_plan        （结构 + 语义校验，任一错误拒整批）
                       ─►  approval.decide      （W4：分发前问；auto 档见 §3.4）
                       ─►  compile_plan         （原语序列，16 个已编译 op）
                       ─►  apply_plan           （W3：先 snapshot_pre_images，失败零写入）
                              └─►  restore_batch （可整批撤销，逐字节回 pre-image）
```

- **入口唯一（W1）**：写只经 `propose_write`。`apply_plan` / `compile_plan` 是**内部实现**，
  facade 不把它们当公开 API；任何新入口（S3 MCP、RPC）只暴露"产 plan"语义，不得直写。
- **txid 强制（W1）**：写链上必须出现 `txid`（信封 `txid` 或 `apply_plan(txid=…)`），
  否则拒绝 —— 这是审计归属与 `restore_batch` 撤销键的锚。见 §3.2 的必红 fixture。

## 2. 错误码（稳定，改名即破坏契约）

| 码 | 层 | 触发 |
|---|---|---|
| `FS_NOT_OBSERVED` | W2 | 未读就写（写目标不在观察表） |
| `FS_NOT_FOUND` | W2 | 读到"不存在"之后要改它 |
| `FS_STALE_VERSION` | W2 | 读后被外部改动（观察 sha ≠ 当前 sha） |
| `SECTION_NOT_FOUND` | 读 | 标题/行号无匹配（带 `suggestions`） |
| `AMBIGUOUS_SECTION` | 读 | 同名多候选且 `path`/`near_line` 无法消歧（**不取首个**） |
| `INVALID_SELECTOR` | 读 | `heading=None` 却给了 `near_line`/`path`/`level` 或完全没给选择器 |
| `NO_HEADINGS` / `INVALID_LEVEL` / `UNSUPPORTED` | 读 | 空文档 / 级别越界 / 非 md 或参数缺 |
| `invalid_plan` / `file_ops_must_be_last` / `ambiguous_section` … | 计划层 | 见 `plan.py::validate_plan` |

## 3. W1–W4 可测断言（每一条对应一条必红 fixture）

### 3.1 W2 读后写守卫（`observation.py`，已接线）
- **机制**：`observation.gate_ops()` 在 `propose_write` 的 `_observation_block` 处裁决。
- **三态**：`unseen` ⇒ `FS_NOT_OBSERVED`；`confirmed absent` ⇒ `FS_NOT_FOUND`；`present@sha` 但 sha 变 ⇒ `FS_STALE_VERSION`。
- **观察源**：`read_document` / `read_kp` / **`read_outline`** / **`read_section`**（R-S2-1 接缝修复）。
  `search_kb` / `grep` / `glob` / **`read_snippet`** 不算。
- **进程内、不落盘**：新进程/新会话空表，resume 后必须重读。
- **必红 fixture**：① 未任何读就写 ⇒ `FS_NOT_OBSERVED`；② `read_section` 后写**必须放行**（不是被自己读闸挡下）；
  ③ `read_snippet` 后写 ⇒ 仍 `FS_NOT_OBSERVED`（片段不构成"看过"）。**fixture 必须传真实 `rel_version`**
  （`record_read(version="")` 会被误判成 `FS_STALE_VERSION`，见 R-S2-1 附注）。

### 3.2 W1 入口唯一 + txid
- **机制**：写只经 `propose_write`；`apply_plan` 是私有实现。
- **必红 fixture**：绕过 facade 直调 `apply_plan`（或缺 `txid` 且信封也没给）⇒ 拒绝。
  （若 txid 强制会破坏 ≥3 处既有调用方，则在 facade 层强制、保留内部签名 —— 实现时先验。）

### 3.3 W3 写前备份
- **机制**：`apply_plan` 第一步 `backup.snapshot_pre_images()`，失败 ⇒ 零写入返回；每批可 `restore_batch()`。
- **必红 fixture**：构造"备份失败"（注入/不可写目录）⇒ 整批不写；写成功后 `restore_batch` 逐字节回 pre-image。

### 3.4 W4 审批在分发前 + 不对称保护（R-S2-3）
- **机制（插件，已有）**：`plugins.py:294-299` `permissions.write` 非空 ⇒ `approval.write ≠ auto`（装载期拒）。
- **机制（运行时）**：`registry.invoke(call, approval=…)` 审批注入在分发前；`GuardedPolicy` 命中 `RISKY_OPS` 才问。
- **缺口（R-S2-3）**：核心 `propose_write` **没有**同款"写能力声明位"。
  facade 要把「写能力必带 write 权限、且 auto 档拒」固化到核心写工具上 —— 否则 S3 暴露 MCP 时，
  这条安全下限对外部插件生效、对核心能力为空。
- **必红 fixture**：构造"核心写能力 + `approval=auto`"⇒ 装载期/分发前拒绝（不是运行时才拒）。

## 4. 幂等

- **写幂等**：同一 `txid` 重放 ⇒ 已应用则不再重复应用（`apply_plan` 按 `txid` 查已应用集）。
- **读幂等**：`outline`/`section`/`snippet` 无副作用；重复调用同结果（预算/截断确定性见下）。
- **观察幂等**：`record_read` 重复记同一 `(rel, sha)` 不改变闸的裁决。

## 5. 版本策略

- facade 用 `@dataclass`/显式签名暴露；**只增不改**（新字段带默认，旧调用方不受影响）。
- 错误码**只增不改**；新增错误码必须登记进本文件 §2。
- `section_index` / `observation` / `approvals` / `backup` 的公开符号是 facade 的**实现依赖**，不单独承诺版本；
  版本承诺只在 `service_contract.py` 的 facade 面上。

## 6. 已知缺口（随实现填，不留到验收）

1. W1：`apply_plan` 仍是模块公开函数（"没人调"≠"调不了"）。
2. W4：核心写能力无声明位（R-S2-3）。
3. 读侧 fan-in 目前是"工具层直接调 `section_index`"，尚未收口到 `service_contract.py`（本文件的 facade 是目标态）。
