# R-S2-11 文档修改建议（精确 diff）· arch-contract

> **用途**：给 `agent-arch` 直接采用的替换文本。对象：`docs/design/agent-service-contract.md`。
> **依据**：task-128 评审 + Lead 裁决 R-S2-8/9/10/11。
> **我不改文档**（只给文本），由 `agent-arch` 落到文件。

---

## 总原则（Lead 的裁决定调）

> **契约文档承诺未实现的行为，它自己就成了新的「静默默认」。**

本轮已抓到四个同源形态：`gate`（声明不读）/ `constrain`（注释称已消费）/ `heading=None`（静默默认）/
现在加上 **§4 幂等（文档承诺未实现）**。

⇒ 本次修改的判据：**每一条都必须是"代码此刻的实际行为"，不是"目标态"**。
凡属目标态的，一律标 `[目标态·未实现]` 并写清何时落地。

---

## 一、§1 fan-in/fan-out 图（错的是**层归属**）

### 现状（`agent-service-contract.md:22-30`）

```
propose_write(plan)  ──►  validate_plan        （结构 + 语义校验，任一错误拒整批）
                       ─►  approval.decide      （W4：分发前问；auto 档见 §3.4）
                       ─►  compile_plan         （原语序列，16 个已编译 op）
                       ─►  apply_plan           （W3：先 snapshot_pre_images，失败零写入）
                              └─►  restore_batch （可整批撤销，逐字节回 pre-image）
```

### 问题
把 `approval.decide` 画进了 `propose_write → validate_plan → compile_plan → apply_plan` 这条链。
**实际不是**：审批与 W2 观察闸都在**工具分发层**（`kb.py::_write_proposal_tools._bound()`，`:3265-3273`），
在 `propose_write` 的 handler 被调用**之前**；`apply_plan` 内部**没有**审批，也没有 `gate_ops`。

### 建议替换为

```markdown
### 1.2 写侧 fan-out（一体入口，内部链固定）

**必须区分两层**（此前本图把两层混成一条链，属文档错误）：

```
【工具分发层】（registry.invoke → tool handler 之前）
  _observation_block  ──►  W2：observation.gate_ops()      ← kb.py:3266
  approval.decide     ──►  W4：GuardedPolicy/write_is_risky ← 分发前问
  issue_clearance     ──►  W1：过闸后签发一次性令牌        ← observation.py:207

【计划执行链】（工具 handler 内部）
  propose_write(plan)
    ├─► validate_plan     （结构 + 语义校验，任一错误拒整批）
    ├─► compile_plan      （原语序列，17 个已编译 op）
    └─► apply_plan        （W3：先 snapshot_pre_images，失败零写入）
           └─► restore_batch（可整批撤销，逐字节回 pre-image）
```

- **W2 与 W4 不在计划执行链上**：它们在工具分发层。⇒ 直接调 `apply_plan` **不会**经过它们
  （这是 §3.2 R-S2-8 要把 `origin` 提为必填参数的原因）。
- **W3 在 `apply_plan` 内部**（`snapshot_pre_images` 是该函数第一步）。
```

---

## 二、§2 错误码（缺 5 项）

### 现状（`agent-service-contract.md:39-48`）

只列了 W2 三码、读侧五码、以及一行 "`invalid_plan` / `file_ops_must_be_last` / `ambiguous_section` …"。

### 问题
1. **`backup_failed` 完全缺失**——但它是 W3 的核心失败码（`backup.py:219`），且**也是 §4 幂等现状的真实返回码**。
2. **`invalid_plan` 的子码一个都没列**——实测至少 4 个，且这些都是调用方需要区分的（能否修复取决于子码）。
3. **`WRITE_GATE_BYPASS` 未列**——它是 R-S2-1/W1 的核心码（`observation.CODE_GATE_BYPASS`）。

### 建议：在 §2 表格后追加

```markdown
### 2.1 计划层与写入层的稳定码（**补全**；此前只写了 `invalid_plan` 一个笼统码）

| 码 | 层 | 触发 | 调用方可做什么 |
|---|---|---|---|
| `invalid_plan` | 计划层 | 计划的**总类**失败，`errors[]` 里带具体子码 | 按子码逐一修 |
| ├ `bad_plan_version` | 计划层子码 | `plan.v` 不是 `1` | 补 `v:1` |
| ├ `missing_field` | 计划层子码 | 缺 `op_id` / `txid` / 某 op 必填字段 | 补字段 |
| ├ `empty_text` | 计划层子码 | `replace_lines`/`insert_lines` 的 `text` 为空 | 改用 `delete_lines` |
| ├ `overlapping_edits` | 计划层子码 | 同一批里两条编辑的行区间重叠 | 拆成两批或合并 |
| └ `expect_mismatch` | 计划层子码 | `expect` 与当前正文不符 | 重读文件再提 |
| `file_ops_must_be_last` | 计划层 | 文件级 op 之后还有别的 op | 调整 op 顺序 |
| `ambiguous_section` | 计划层 | `replace_section` 同名多候选且无法消歧 | 补 `path` 或 `near_line` |
| `backup_failed` | 写入层 W3 | 写前备份失败 / **批次目录已存在（同 txid 重放）** | 换 txid 或查已有批次 |
| `WRITE_GATE_BYPASS` | 写入层 W1 | 声称 `origin=agent` 但无有效清关令牌 | 走 `propose_write` 提交 |

> **稳定承诺**：上表每一码都是"改名的破坏性变更"。新增码只能追加。
```

---

## 三、§4 幂等（**当前是空话——这是本次最需要改的一节**）

### 现状（`agent-service-contract.md:79-83`）

```markdown
## 4. 幂等

- **写幂等**：同一 `txid` 重放 ⇒ 已应用则不再重复应用（`apply_plan` 按 `txid` 查已应用集）。
- **读幂等**：`outline`/`section`/`snippet` 无副作用；重复调用同结果（预算/截断确定性见下）。
- **观察幂等**：`record_read` 重复记同一 `(rel, sha)` 不改变闸的裁决。
```

### 问题（实测，不是推测）

「`apply_plan` 按 `txid` 查已应用集」——**全仓不存在这个实现**：
```
grep -r "already_applied|applied_set|duplicate_txid|_applied" src/memoria/services/agent/
→ 0 命中（唯一"幂等"字样在 kb.py:4763，讲复习卡"同日同卡不叠加"，与 plan 写无关）
```
**实际行为**：同 txid 第二次调用 ⇒ `backup.snapshot_pre_images()` 发现批次目录已存在
⇒ 返回 `{"status":"error","code":"backup_failed","message":"批次已存在：<txid>"}`（`backup.py:219`）。

⇒ **那是"报错"，不是"幂等"**。
- 幂等的定义：重放返回**相同成功结果**。
- 当前行为：重放**报错**。
- 两者对调用方的语义完全不同（幂等可安全重试；报错则重试即失败）。

### 建议替换为

```markdown
## 4. 幂等（**按当前实际行为写；含一条已知缺口**）

- **写幂等：❌ 不幂等（当前行为 = 重复 txid 直接拒绝）**
  - 实测：同一 `txid` 第二次 `apply_plan` ⇒ `{"status":"error","code":"backup_failed",
    "message":"批次已存在：<txid>"}`（`backup.py:219`；批次目录存在性即天然去重键）。
  - 语义定性：**这是"拒绝"，不是"幂等"**。调用方**不得**把"重放"当作安全重试
    （重放会失败，且不会返回上次的结果）。
  - 好处（如实）：因为拒绝，**不会重复写盘**——重复应用这个最坏后果不会发生。
  - 缺口：无法"重放拿到相同成功结果"。若将来需要真正的幂等重放，
    需新增 `duplicate_txid` 语义 + 记录已应用集，属**未实现**（勿在文档里先承诺）。
  - **[目标态·未实现]** 若采纳真幂等：`apply_plan` 命中已应用 txid 时返回
    `{status:"ok", replayed:true, ...上次结果}`，而不是报错。
- **读幂等**：`outline`/`section`/`snippet` 无副作用；同一输入重复调用返回相同结果
  （预算/截断为确定性算法，已在 `section_read_api.py` A11 验证）。
- **观察幂等**：`record_read` 重复记同一 `(rel, sha)` 不改变闸的裁决（`observation` 用 dict 覆盖写）。
```

---

## 四、§5 版本策略（**R-S2-9 需精确化：不建读侧 facade，写侧已在 `service_contract.py`**）

### ⚠️ 事态更新（2026-10-25 02:05）
`agent-arch` 已创建 `src/memoria/services/agent/service_contract.py`（194 行，`??` 未跟踪），
内含 `submit_write()` 唯一写入口 + `WRITE_CAPABILITY` 声明位，承载 R-S2-3 / W1 / W4 三条。
其头部写明 **R-S2-7：只做写侧（写侧有真消费者），读侧不抽（无消费者）**。

⇒ **R-S2-9「不建独立 facade 模块」应精确化为「不建读侧 facade」**，否则会误伤已落地的写侧 facade。
我 task-128 评审的 §1 只验证了读侧，**对写侧的论证不成立**（详见评审报告的事后更新节）。

### 现状（`agent-service-contract.md:85-91`）

```markdown
## 5. 版本策略

- facade 用 `@dataclass`/显式签名暴露；**只增不改**（新字段带默认，旧调用方不受影响）。
- 错误码**只增不改**；新增错误码必须登记进本文件 §2。
- `section_index` / `observation` / `approvals` / `backup` 的公开符号是 facade 的**实现依赖**，不单独承诺版本；
  版本承诺只在 `service_contract.py` 的 facade 面上。
```

### 问题
原文可以基本保留（因为 `service_contract.py` **确实存在**了），但需补两点：
1. **读侧没有 facade**，原文第 3 条"`section_index` 是 facade 的实现依赖"对读侧不成立
   —— 读侧的 `section_index` 就是**直接契约面**。
2. 需写明**写侧 facade 的消费边界**（哪些是契约、哪些是实现细节）。

### 建议替换为

```markdown
## 5. 版本策略（R-S2-7/9：写侧 facade 有消费者，读侧不抽）

- **写侧**：`service_contract.py` 是契约面 —— `submit_write()` 签名、`WRITE_CAPABILITY` 语义、
  `ContractViolation.code` 集合（`APPROVAL_REQUIRED` / `INVALID_PLAN` / `WRITE_GATE_BYPASS`）。
  **只增不改**：新参数带默认值；错误码只增；**必填参数一旦引入不得回退为可选**。
- **读侧**：**不抽 facade**（R-S2-9）。`section_index.{build_outline, get_section, get_section_part,
  get_snippet}` 的**错误码集合就是契约面**，直接承诺；`tools/kb.py` 的三把读工具是它的消费者。
  **延迟抽取的触发条件**：S3（MCP 薄绑定）需要以非 Tool 形态暴露读侧时，再按真实调用形态抽。
- **审批/备份/观测**：`approvals.write_is_risky` / `observation.gate_ops` / `backup.snapshot_pre_images`
  的**语义**属契约（被 §3 的必红 fixture 钉住），其**内部实现**不承诺。
- 新增错误码必须登记进本文件 §2.1。
```

---

## 五、§3.2 W1（把 R-S2-8 写进去）

### 现状（`agent-service-contract.md:62-65`）

```markdown
### 3.2 W1 入口唯一 + txid
- **机制**：写只经 `propose_write`；`apply_plan` 是私有实现。
- **必红 fixture**：绕过 facade 直调 `apply_plan`（或缺 `txid` 且信封也没给）⇒ 拒绝。
  （若 txid 强制会破坏 ≥3 处既有调用方，则在 facade 层强制、保留内部签名 —— 实现时先验。）
```

### 问题
1. 说"`apply_plan` 是私有实现"——**它不是**（`apply.py:525` 是模块公开函数，无下划线）。
2. "绕过 facade 直调 ⇒ 拒绝"——**当前不成立**（R-S2-8 要修的就是这个）。
3. 引用"facade"——facade 已裁不建（R-S2-9）。

### 建议替换为

```markdown
### 3.2 W1 入口唯一 + txid（R-S2-8：`origin` 提升为**函数必填参数**）

- **机制（当前，fail-open，待修）**：`apply.py:554` 只在 `plan.origin == "agent"` 时校验清关令牌
  ⇒ **不写 `origin` 即跳过全部校验**（实测：plan 无 origin ⇒ `status:ok`，文件被改）。
- **机制（R-S2-8，目标态）**：
  ```python
  apply_plan(..., *, origin: str)     # 无默认值 ⇒ 漏传 = TypeError（签名级 fail-closed）
  ```
  - `kb.py:3194` → `origin="agent"` + `gate_token`
  - `ui.py:1661` → `origin="human"`（人类"确认卡点应用"路径，观察表必然为空，故无令牌）
  - `origin` 缺失/空/未知 → 拒（**不得**默认成 `human`）
- **为什么用参数而非 plan 字段**：plan 由前端构造并经 `agent_plan_apply` 传回，是**不可信输入**；
  省略字段即绕过。函数参数由**调用点**决定，新调用方**必须显式表态**，漏传在签名层就是 `TypeError`。
- **诚实边界（必须写进文档，勿再造成"声明即事实"）**：
  进程内方案**无法区分**"真正的人类 UI 调用"与"显式传 `origin="human"` 的恶意调用"。
  R-S2-8 解决的是"漏传静默"，不解决"撒谎"。
- **必红 fixture**：① 漏传 `origin` ⇒ `TypeError`；② `origin=""`/`"xxx"` ⇒ 拒；
  ③ `origin="agent"` 无令牌 ⇒ `WRITE_GATE_BYPASS`，且**备份未创建**（实测备份目录 0 个）。
```

---

## 六、§3.4 W4（R-S2-10：不加进 RISKY_OPS，用 capability 显式化）

### 现状（`agent-service-contract.md:71-77`）

已写"缺口（R-S2-3）：核心 `propose_write` 没有同款写能力声明位"，方向对，但**没写清等级差异**。

### 建议在 §3.4 末尾追加

```markdown
- **等级差异必须显式写明（R-S2-10）** —— 两者**不是同一等级**的保护：

  | 侧 | 保护 | 时机 | 强度 |
  |---|---|---|---|
  | **插件声明** | `permissions.write` 非空 ⇒ `approval.write ≠ auto` | **装载期**拒 | 硬（装不进来） |
  | **核心写** | `write_is_risky()` 命中 `RISKY_OPS` 才问 | **运行时**策略判定 | 软（auto 档放行） |

  实测（`RISKY_OPS = {rename_file, delete_file, move_file, delete_kp, rename_kp}`）：
  `replace_lines` / `insert_lines` / `replace_section` / `upsert_kp` / `create_file`
  **在默认 auto 档全部 `risky=False`（不问人）**。

- **修法（R-S2-10，明确否决"加进 RISKY_OPS"）**：把 `replace_lines` 等加入 `RISKY_OPS`
  = 让 agent 每改一行都停下问人 ⇒ **功能不可用**（R-S1A-2 已裁过同一件事）。
  正确做法：新增 `WRITE_CAPABILITY` 声明位（落在 `approvals.py`，它本就是审批域），
  让"我要什么权限"**显式化且可查询**；**S3 MCP 入口强制要求**声明。
  核心内置 agent 路径不受影响。
```

---

## 七、§6 已知缺口（**保留，但按现状更新**）

§6 是本稿最好的部分（诚实）。建议只做两处增补：

```markdown
## 6. 已知缺口（随实现填，不留到验收）

1. **W1（R-S2-8，待修）**：`apply_plan` 仍是模块公开函数，且令牌校验是 `origin=="agent"` 的 opt-in
   ⇒ 省略 origin 即跳过。修法见 §3.2（`origin` 提升为必填参数）。
2. **W4（R-S2-10，待修）**：核心写能力无 `WRITE_CAPABILITY` 声明位；且与插件侧的
   "装载期硬拒"不是同一等级（见 §3.4 等级表）。
3. **读侧 fan-in**：仍是"工具层直接调 `section_index`"，**且这是 R-S2-9 的正式落点**
   （不建独立 facade 模块）—— 本项从"缺口"改为"**既定架构**"，不再记为待补。
4. **§4 写幂等**：当前是"重复 txid 拒绝"而非幂等；真幂等未实现（见 §4 的 `[目标态·未实现]`）。
```

---

## 八、修改后的自查清单（给 `agent-arch`）

改完请逐条确认：
- [ ] §1.2 图里**不再**把 `approval.decide` / `_observation_block` 画在计划执行链上
- [ ] §2.1 含 `backup_failed` / `WRITE_GATE_BYPASS` / `invalid_plan` 全部子码
- [ ] §4 写幂等**不再**声称"已实现"；明确写"当前是拒绝、不是幂等"
- [ ] §5 **不再**引用 `service_contract.py`
- [ ] §3.2 含 R-S2-8 的 `origin` 必填参数 + 诚实边界（不能区分"撒谎"）
- [ ] §3.4 含等级差异表，且明确**不把** `replace_lines` 加进 `RISKY_OPS`
- [ ] §6 第 3 项从"缺口"改为"既定架构"
