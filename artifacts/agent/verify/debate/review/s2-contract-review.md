# S2 契约文档初稿评审（task-128）

> **评审者**：arch-contract（对抗评审）。**对象**：`docs/design/agent-service-contract.md`（96 行初稿）+ 相关实现现状。
> **时机**：实现中途（`agent-arch` 正在写 facade），**提前反馈避免返工**。
> **方法**：读文档 + 读代码 + **可执行实验**（临时脚本，已清理）。**未改 `src/**`**，未 commit。
> **HEAD**：工作区有 agent-arch 的 S2 在途改动（`apply.py +20` / `observation.py +55`）。

---

## ⚠️ 事后更新（2026-10-25 02:05 之后，**必须优先读这一节**）

> **`agent-arch` 在我完成评审后创建了 `src/memoria/services/agent/service_contract.py`（194 行，`??` 未跟踪）。**
> 它第 3-8 行写明 **R-S2-7 的决定**：
> - **写侧有真消费者**（R-S2-3 声明位 / W1 令牌 / W4 审批**需要唯一入口承载**，否则三条没有落点）⇒ **建**
> - **读侧无消费者** ⇒ 不抽（我 §1 的论证对读侧成立，对写侧**不成立**）
>
> ⇒ **我的 §1 结论需要修正**：我说"facade 无消费者 ⇒ 不该建"，
> 但那只验证了**读侧**（`section_index` 单一实现）。**写侧的三条强制确实需要一个统一入口** ——
> 分散在 `kb.py` / `ui.py` / 未来 MCP 的调用点各自实现一遍，正是"同一规则多处复制"的老问题。
>
> **修正后的结论**：
> - ✅ **读侧不抽 facade** —— 与 R-S2-9 一致，我的论证成立
> - ✅ **写侧建 facade** —— R-S2-7，`agent-arch` 的论证成立（我漏看了写侧的消费者）
> - ⇒ **R-S2-9「不建独立 facade 模块」需精确化为「不建读侧 facade」**，否则会误伤已落地的写侧 facade
>
> **这是本次评审的第三处自我修正**（前两处：plan 结构假阴性、未查 kb.py 就判"完全可绕过"）。
> 共同模式：**我验证的是"评审那一刻的代码状态"，而代码在评审后继续演进**。
> ⇒ 评审结论必须绑定"我看到的代码时刻"，过时部分应标注而非固化为裁决。

---

## 0. 一句话结论（**基于评审时刻 02:02 的代码状态**）

**契约文档的方向是对的，但三条必查全部指向同一个病：文档描述了"目标态"，而代码里"保护并不存在"。**

| # | 必查项 | 判定 |
|---|---|---|
| ① facade 有没有消费者 | **不该建独立 facade 模块**（无第二实现、无替换计划）→ 给替代方案 |
| ② 收私有够不够 | **(a)(b)(c) 都不够**；实测 **W1 令牌有效但 opt-in 可绕过** + **W2 闸不在 apply_plan 里** |
| ③ W4 不对称 | **缺口比文档写的更严重**——核心写 op 在 auto 档**全部 risky=False 自动放行** |

> **② 的结论经过一次自我纠正**（详见 §2）：初测以为"W2/W1 完全可绕过"，
> 复查发现 agent-arch **已实现 W1 清关令牌**（`observation.py:207-229`），令牌本身有效；
> 但它是 **opt-in（只在 `origin=="agent"` 时校验）**，省略该字段即可绕过。
> 结论从"完全没保护"修正为"**有保护但可被省略字段绕过**"，修复方案也因此更精确。

---

## 1. ① facade 这层抽象有没有消费者

### 1.1 事实核（独立验证，不采信文档）

| 检查 | 结果 | 证据 |
|---|---|---|
| `service_contract.py` 是否存在 | **不存在** | `Test-Path` = False；`Get-ChildItem -Filter *contract*/*facade*` 空 |
| facade 是否有实现 | **无**（文档 §6.3 自承"尚未收口"） | `agent-service-contract.md:96` |
| `section_index` 有几个实现 | **只有 1 个** | `Get-ChildItem -Filter *section*` → 仅 `section_index.py` |
| 有无替换计划 | **无**（文档未提、代码无抽象基类/协议） | 无 `Protocol` / `ABC` / 多实现 |

### 1.2 判定：**这层独立 facade 模块不该建**（按 R-R2 无消费者即移出）

**理由三条**：

1. **「内部实现可替换」在本仓没有现实需求**：`section_index` 只有 1 个实现，且它本身是**刚从 task-120 新建的**（不是历史遗留）。为"将来可能换"而加一层间接，是典型的**架构美观而非必要约束**。
2. **代价是实打实的**：
   - 多一层 = **bug 藏身处**（facade 的转发逻辑错配参数，是这类代码最常见的 bug）；
   - **栈变深**（`propose_write → facade → validate_plan`，调试时多跳一次）；
   - **多一份契约要维护**（本文档 96 行，且 §5 要把"版本承诺"绑在 facade 上 ⇒ 以后每次改 section_index 都要同步 facade 契约）。
3. **最关键的证据：W1–W4 的保护本来就不在"收口"上**。我在 ② 用实验证明：**W2 闸根本不在 `apply_plan` 里**。所以"把调用收口到 facade"**并不能**带来 W1–W4 的保护——它只是把"没人主动调 apply_plan"变成"通过 facade 调"。**保护来自闸的位置，不来自入口的层数。**

### 1.3 最小替代方案（P1 要求：不能只用否决代替设计）

**不建 `service_contract.py`，改用「薄校验函数 + 闸下沉」**：

```
方案 B（推荐）：
1. 读侧：直接在 tools/kb.py 现有的 3 把工具里调 section_index（现状已经是这样，文档 §6.3 也承认）
   —— 不额外加一层，只把「错误码统一」抽成 section_index 内的一个 _to_tool_error() 小函数。
2. 写侧：把 W1/W2 的强制下沉到 apply_plan 内部（见 §2 的修复），而不是靠 facade 转发。
3. 契约文档保留，但改名定位为「调用约定」而非「facade 模块规格」——它约束的是"谁能调、什么语义"，
   不承诺"有一个 XxxService 类"。
```

**这个方案省下的**：一个模块、一层转发、一份版本承诺。
**代价**：如果将来真出现第二实现（例如 S3 MCP 需要不同实现），那时再加 facade 也不算晚——**在此之前它只是负担**。

**若 Lead/agent-arch 坚持要 facade**，则必须给出：**什么事件会触发第二实现的出现**（falsifier），否则就是无消费者的抽象。

---

## 2. ② `apply_plan` 收私有在 Python 里够不够 —— **实验证明：不够，且我修正了自己的初判**

> **⚠️ 本节经历了一次自我纠正，如实记录。**
> 我最初的实验（plan 不带 `origin` 字段）得到 `status: ok, 文件被改` ⇒ 初判"W2 完全可绕过"。
> 但随后读 `kb.py:3269-3273` 发现 **agent-arch 已经实现了 W1 清关令牌**（`observation.py:207-229`
> `issue_clearance` / `consume_clearance` + `apply.py:536-562` 校验）。
> 补测后结论**变了**：令牌**有效**，但**只在 `plan.origin == "agent"` 时才校验**。
> 若我不做这次补测，会给出一个**错的、过时的**头号结论。

### 2.1 完整绕过矩阵（实测）

| # | plan 形态 | 结果 | 文件被改 |
|---|---|---|---|
| **A** | **不写 `origin` 字段**（外部直调） | **`status: ok`** | **✅ 被改了** |
| **B** | `origin: "agent"` + 无令牌 | `error / WRITE_GATE_BYPASS` | ❌ 未改 |
| **C** | `origin: "agent"` + 伪造形态合法 txid | （B 的同一路径）拒 | ❌ 未改 |

**判读**：
- **B/C 证明令牌机制本身有效** —— agent-arch 的 W1 实现是对的，值得肯定；
- **A 证明它可被"不声明 origin"完全绕过** —— 这是**白名单式的 fail-open**：只有自称 agent 的才检查，
  而"绕过工具层直调"恰恰最可能**不声明**自己是 agent。

### 2.2 根因（两条，缺一不可）

**根因 1：W1 令牌是 opt-in（可通过省略字段跳过）**
`apply.py:554`：
```python
if isinstance(plan, Mapping) and str(plan.get("origin") or "") == "agent":
    # 才校验令牌
```
⇒ 不写 `origin` ⇒ 整段令牌校验被跳过 ⇒ 直接落盘。

**根因 2：W2 闸**根本不在** `apply_plan` 里**
- W2 实现：`observation.gate_ops()`（`observation.py:139`）
- **唯一调用点**：`kb.py:3266` `_observation_block(...)` —— 在**工具层 `_bound()`** 里
- `apply_plan`（`apply.py:525`）内部**没有** `gate_ops`

⇒ 即使令牌机制修好（改成 fail-closed），W2 仍然是"绕过工具层就没有"。

### 2.3 txid 可伪造性（独立于令牌）

| 实验 | 结果 |
|---|---|
| 不给 txid | `invalid_plan` 拒（**但不是真防护**——`apply_plan` 会从 `compiled.get("txid")` 补，`apply.py:572`） |
| 伪造**非法形态** txid | `backup_failed` 拒（`backup._check_txid` 只校验**形状**） |
| **伪造「形态合法」任意 txid**（`20260101T000000Z-99`） | **`status: ok`，写入成功** |

⇒ **txid 只校验形状，不校验来源。** 令牌与 txid 是**两套独立机制**，令牌管"是不是 agent 签发的"，txid 只管"备份目录名合法"。

### 2.4 三个候选方案评估（Lead 给的 (a)(b)(c)）

| 方案 | 够用吗 | 原因 |
|---|---|---|
| **(a) 只改名 `_apply_plan`** | ❌ **不够** | Python 下划线只是约定。`from apply import _apply_plan` 照样 import；且**本次实验就是这样做的**（只是一个没加下划线）。它连"看起来"都挡不住。 |
| **(b) txid 必须由 facade 签发** | ⚠️ **方向对，但当前实现是 opt-in** | 见 2.2 根因 1。**改成 fail-closed（无 origin 也要求令牌）才是对的。** |
| **(c) 内部断言调用栈** | ❌ **过强且脆弱** | 异步/重入/测试 mock 下极易误伤；保护的是"调用来源"而非"保护生效"，治标。 |

### 2.5 我的最小修补（P1 要求可执行替代）

**三条改动，按优先级**：

```
【P0】根因 1 修复：令牌校验改 fail-closed
  apply.py:554 的 `if plan.get("origin") == "agent"` 条件**删除**，
  改为：**任何** apply_plan 调用都要求有效令牌（或显式 `system_bootstrap=True` 白名单，
       且该白名单只能由内部调用点使用，不可从 plan 外部指定）。
  理由：opt-in 的保护等于没有保护——攻击者只要不声明就跳过。

【P0】根因 2 修复：W2 闸下沉到 apply_plan 内部
  在 apply_plan 开头（backup.snapshot_pre_images 之前）追加 `observation.gate_ops(...)`。
  这样无论谁调用（工具层 / S3 MCP / 直调），W2 都必然生效。
  ⚠️ 注意：gate_ops 需要 kb_path + session_id + ops，这些 apply_plan 都有入参。

【P1】txid 来源校验（可选，若确实要"签发"语义）
  用进程内私有对象做凭证：facade 生成 `TxidToken`（不可序列化、构造器私有），
  apply_plan 要求 isinstance 检查。
  不用 HMAC（引入新秘密管理面）。跨进程（S3 MCP）时需重设计 ⇒ 说明 txid 签发
  更适合作为**审计归属**的软约束，而非进程内强制。
```

**证明"够用"的验收实验**（agent-arch 实现后我会重跑）：
```
A. plan 不写 origin，观察表为空 ⇒ 期望 status=error, code=FS_NOT_OBSERVED 或 WRITE_GATE_BYPASS, 文件未改
B. plan.origin=agent，无令牌 ⇒ 期望同上（当前已通过）
C. 伪造形态合法 txid + 无令牌 ⇒ 期望拒（当前通过）
```

---

## 3. ③ W4 不对称保护 —— **缺口比文档写的更严重**

### 3.1 文档怎么说的

`agent-service-contract.md:74`：「核心 `propose_write` **没有**同款'写能力声明位'」。

### 3.2 我查到的实际情况

**① 核心写工具的审批档 = auto 档下"常规写自动放行"**

| 证据 | 内容 |
|---|---|
| `permission_presets.py:31` | `auto-approval`（**默认档**）→ `GuardedPolicy`（常规写自动放行，命中风险才问） |
| `approvals.py:182` | `RISKY_OPS = {rename_file, delete_file, move_file, delete_kp, rename_kp}` —— **只有 5 个** |
| `approvals.py:185-203` `write_is_risky()` | ops 非空且动词不在 `RISKY_OPS` ⇒ 返回 **False**（免问） |

**② 实测（我跑的）**：

```
replace_lines      risky=False   ← 自动放行
insert_lines       risky=False   ← 自动放行
replace_section    risky=False   ← 自动放行
upsert_kp          risky=False   ← 自动放行
create_file        risky=False   ← 自动放行
rename_file        risky=True
delete_file        risky=True
```

⇒ **核心写工具在默认 auto 档下，最常见的 5 类写操作全部不问人。**

### 3.3 与插件侧的不对称（这才是真缺口）

| 侧 | 保护 | 时机 |
|---|---|---|
| **插件声明** | `permissions.write` 非空 ⇒ `approval ≠ auto` | **装载期**拒（`plugins.py:294-299`） |
| **核心 `propose_write`** | 无声明位；靠 `write_is_risky` 运行时判断 | **运行时**，且常规写恒 False |

⇒ **同一个能力，作为插件装进来受"装载期硬拒"，作为核心内置则"自动放行"。** 这正是文档 §3.4 说的问题，但文档把它写成"缺口"而没写清**严重程度**：不是"少一个声明位"，而是**默认档下核心写操作实质上无审批**。

### 3.4 最小修补（可执行）

**不要求"核心写也必须人工确认"**（那会毁掉 auto 档的意义）。真正要补的是**能让外部调用方"声明自己需要什么权限"的位**：

```
给 propose_write 增加可选参数 `capability` (读自 plan 信封):
  - plan 带 `capability: {write: true}` ⇒ 走与插件同款的硬校验（auto 档拒绝）
  - plan 不带 ⇒ 保持现状（核心内置 agent 的正常路径，auto 放行）
  - 但 S3 MCP 入口**强制要求**带 `capability`（外部调用方必须声明）
⇒ 这样：核心内置不被打扰，外部入口受同款约束。
```

**可测断言**：构造 `plan{capability:{write:true}}` + auto 档 ⇒ **分发前拒绝**（不是运行时才拒）。

---

## 4. 逐节完整性检查

| 节 | 判定 | 问题 |
|---|---|---|
| **§1 fan-in/out 是否与实际调用图一致** | ⚠️ **部分不一致** | §1.2 写侧 fan-out 图里 `propose_write → validate_plan → approval.decide → compile_plan → apply_plan`。但实际调用顺序是 `kb.py:3194 apply_plan(...)`，**approval 在 `registry.invoke` 层**（`kb.py:3261 _observation_block` 附近），不在图里画的"plan 内部链"。**图的层归属错了**：`approval.decide` 与 `_observation_block` 都在**工具分发层**，不在 plan→compile→apply 这条链上。 |
| **§2 错误码有无遗漏** | ⚠️ **有遗漏** | 缺 `FS_NOT_OBSERVED` 的**触发前置**说明；缺 `invalid_plan` 的子码（`missing_field`/`empty_text`/`bad_plan_version`/`overlapping_edits` 等，实测至少 4 个）；缺 `backup_failed`。**错误码表是契约，漏了就不是稳定契约。** |
| **§3 W1-W4 是否可判红** | ✅ **可判红，但 W2/W1 的 fixture 设计会失败** | §3.1 W2 fixture「未任何读就写 ⇒ FS_NOT_OBSERVED」——**若按我实验的方式测（直接调 apply_plan）会失败**，因为 W2 不在那里。fixture 必须明确"经由 `propose_write` 工具层"才成立，否则测的是一个不存在的保护。 |
| **§4 幂等** | ⚠️ **§4「写幂等」是空话** | 「同一 txid 重放 ⇒ 已应用则不再重复应用」——**我没找到任何"按 txid 查已应用集"的实现**。`backup.snapshot_pre_images` 在批次已存在时返回 `backup_failed`（`backup.py:219`），这**不是幂等，是拒绝**。幂等应该是"重放返回相同成功结果"，不是"第二次报错"。**建议：改成"同 txid 重放 ⇒ 返回相同结果（幂等）或明确报 `duplicate_txid`（非幂等但可预期）"，二选一并写实。** |
| **§5 版本策略** | ⚠️ **半空话** | 「facade 用 `@dataclass`/显式签名暴露；只增不改」——但 **facade 模块不存在**（§6.3 自承）。这条承诺的是**一个还不存在的东西**。若采纳我 §1.3 的替代方案（不建 facade），本节的"版本承诺只在 `service_contract.py` 的 facade 面上"**整条需要重写**。 |
| **§6 已知缺口是否诚实** | ✅ **诚实** | 三条缺口（W1 apply_plan 仍公开 / W4 核心无声明位 / 读侧未收口）**都属实**，我逐条验证过。**这是本稿最好的部分。** |

---

## 5. 我要求改的（按优先级）

| # | 改动 | 理由 |
|---|---|---|
| **1** | **把 W2 闸下沉到 `apply_plan` 内部**（不是靠 facade 收口） | 实验证明 W2 可完全绕过；这是唯一根治 |
| **2** | **§1.2 fan-out 图修正层归属**：`approval.decide` 与 `_observation_block` 属**工具分发层**，不在 plan→compile→apply 链上 | 图画错了会误导实现者把审批放进 apply |
| **3** | **§2 错误码补全**：`backup_failed` + `invalid_plan` 子码（至少 4 个） | 契约表不全 = 不是稳定契约 |
| **4** | **§4 写幂等改实**：要么实现"按 txid 查已应用集"，要么改写成"重复 txid ⇒ `duplicate_txid` 拒绝" | 当前描述与代码行为不符（实际是拒绝不是幂等） |
| **5** | **§3.4 W4 补 `capability` 参数方案** | 让外部入口受约束、核心不被打扰 |
| **6** | **§5 版本策略随 §1 的 facade 决定重写** | 若不建 facade，承诺对象变了 |
| **7** | **`apply_plan` txid 凭证若要做，用进程内私有对象 + 声明"跨进程需重设计"** | HMAC 会引入新秘密管理面 |

---

## 6. 自利检查

| 我的主张 | 对我（评审者）有利吗 |
|---|---|
| ① 不建 facade | **否**——反而是劝 agent-arch 少写代码 |
| ② 闸下沉（而非收私有） | **否**——这是更难的实现，对评审者没有特权收益 |
| ③ 补 capability 参数 | **否** |

**三条都不增强评审者权力，无自利嫌疑。** 我也**没有**用"我认为不该建"去要求任何否决权——按 P1 给了完整替代方案（§1.3 + §2.5）。

---

## 7. 复现

实验脚本已清理（结论固化在 §2.1/§2.3/§3.2 的表格里）。要复跑：

```python
# 关键三行（W2 绕过）
kb = 临时 KB（含 target.md，从未 read）
plan = {v:1, intent:…, txid:"20260101T000000Z-01",
        ops:[{op:"replace_lines", op_id:"o1", file:"target.md",
              range:{start:3,end:3}, expect:"原内容第一行", text:"新内容"}]}
apply_plan(kb, plan, session_id="s", txid="20260101T000000Z-01")
# 实测 → status=ok, file_changed=true（W2 被绕过）
```
