# Lead 派发规范（Dispatch Rules）

> **读者**：Lead（主控）。
> **用法**：**不要求通读**。按「触发时刻」读对应一节即可（见下方索引）。
> **为什么这么设计**：2026-10-24 复盘发现，**写在文档里靠"记住"的规范，遵守率就是随机数**；
> 只有"让违规在物理上做不到"的规则才稳定生效。因此本文件 95% 的条目都对应一个
> **机检（`team_audit.py`）或工具级拒绝**；纯靠自觉的只剩 3 条，见 §5。
>
> **不变量摘要（每次对话由 AGENTS.md 自动注入，≤15 行）** → 见 [AGENTS.md §0.5](../../AGENTS.md)。
> **配套**：`docs/guides/agent-team-lessons.md`（27 条教训判据，派发前必读三条）。
> **机检**：`scripts/agent/team_audit.py`（11 类）。

---

## 0. 对话被压缩后（**强制重读本节**）

上下文压缩会**确定性地丢掉**：完整规范、任务板细节、未完成事项的因果。
压缩摘要能保留事实，但**不保留约束**。所以压缩后立刻做这 4 件：

```
1. 读 AGENTS.md §0.5 六条不变量（会被宿主自动注入，确认它还在）
2. 跑 team_audit.py —— 拿到当前 FAIL/WARN（这是唯一可信的现状）
3. team_task_list 未完成任务（确认 owner 与写域，别凭摘要干）
4. 确认是否有 in-flight 的后台任务（job_list）—— 摘要有可能会漏
```

**判据**：压缩后**不凭记忆回答"还剩什么要做"**，一律重新查任务板 + 机检。

---

## 1. 要 `spawn_teammate` 时

### 触发
即将创建任何 teammate（无论 fresh 还是 fork）。

### 检查清单（顺序执行，不可跳）

| # | 检查 | 机检 | 违规后果 |
|---|---|---|---|
| 1.1 | **先建任务，再 spawn**（任务存在且 `owner` 已留给该成员） | `dispatch_release::H1` | WARN「派发了但任务板无 owner」 |
| 1.2 | 该任务的 `writeScopes` **必须显式声明**，且与所有存活成员**无交集** | `write_scope`（advisory→spawn 前置） | 重叠 ⇒ **排队，不许并行** |
| 1.3 | 选模型：**默认 `deepseek-flash`**；只有需要长链推理/契约裁决才用 `v4-pro`，且必须在回报里说明理由 | 人工 | — |
| **1.3b** | **选 `mode`（四档，见下）—— 不许不选**。不传 `mode` 会被静默默认为 `standard`，等于"没做决策" | `mode_policy`（待实现） | WARN「未做模式决策」 |
| 1.4 | `context`：**默认 `fresh`**。只有"接续我自己未完成的上下文"才用 `fork` | — | — |
| 1.5 | prompt 必含 5 项：① 任务 id ② 写域 ③ 验收标准 ④ 必读文档（含 lessons 三条）⑤ **卡壳 >N 分钟先回报** | 人工 | — |
| 1.6 | 若为一次性只读调研（不写代码、不需要审计）⇒ **优先用 subagent，不占名册** | — | — |

### 1.3b 模式路由表（DSH 四档，源码 `tool-agent-team/src/index.ts`）

```ts
L43: reasoningEffort = mode === 'mechanical' ? 'off' : mode === 'deep' ? 'high' : undefined
L44: modeModel       = mode === 'deep' ? config.deepModel
                     : mode === 'mechanical' ? config.mechanicalModel : undefined
L448: const mode = args.mode ?? 'standard'      // ← 不传 = 静默默认
```

| mode | 推理链 | 模型 | 该给谁 |
|---|---|---|---|
| **`mechanical`** | **off** | 可配 `mechanicalModel` | **纯执行不可判断的活**：只读扫描 / 统计 / 格式检查 / 生成报告 / 一行修复 / 跑命令取数 |
| `standard` | 默认 | 默认 | 常规实现：多文件、需判断、要自验 |
| `deep` | **high** | `deepModel`（本部署实测 = v4-pro） | 契约裁决 / 架构设计 / 等价性判断 / 高风险评审 |
| `creator` | 默认 | 默认 + creator preset | **改 DSH 插件 / bundle / preset**（唯一能做的模式） |

**强制规则**：`mode` 必须**显式传**。理由 —— 不传就是 `standard`（源码 `args.mode ?? 'standard'`），
日志上「忘了想」与「决定用 standard」完全无法区分。

**两条铁律**：
1. **能用一个命令或一次扫描得出结果的任务，不许用 `standard`/`deep`** —— 那是纯浪费推理链
2. **`deep` 会把模型换成 `deepModel`（v4-pro）** ⇒ 与人「团队统一 flash」冲突 ⇒ 用 `deep` 必须在回报里写明理由，
   否则退化为 `standard` + 显式 `model: deepseek-flash`

### 本轮实证（为什么要 1.3b）
```
2026-10-24 spawn 记录：
  steward  → mode: deep     ← 错：任务是"设计文档"，standard 够；且模型被换成 v4-pro，违反"统一 flash"
  steward2 → mode: standard
  todo-owner / team-plugin-creator → 未传 mode ⇒ 静默默认 standard
⇒ 一次都没用过 mechanical，尽管当天有大量"扫一遍仓库/生成报告/跑命令取数"的活
```


### 本轮实证（为什么要 1.1/1.2）
```
p0-selection / boot-probe 都是【先 spawn 后补任务】⇒ 违反 1.1
⇒ 后来退役时它们名下的 5 条任务变成「幽灵 owner」，机检报 2 条 FAIL
```

### 反面案例（为什么要 1.3 默认 flash）
`team-plugin-creator` 用 **flash** 交付了 R1–R8（127 tests + tsc 0），质量不打折。
`v4-pro` 本轮 3 个成员最终全部退役（成本高、收益未证明更高）。

---

## 2. 要 `team_task_create` 时

| # | 检查 | 机检 |
|---|---|---|
| 2.1 | `owner` 或 `unassigned_reason` **二选一必填**（工具已强制拒绝裸无主任务） | R3（工具级） |
| 2.2 | description 必须含「**关闭条件**」（可验证的判据，不是"做完了"） | 人工 |
| 2.3 | description 必须含「**写域**」 | `write_scope` |
| 2.4 | 若依赖其它任务 ⇒ `blocked_by` 显式声明（别靠口头顺序） | 人工 |
| 2.5 | **先证红原则**：修复类任务的关闭条件必须包含"修复前该用例失败"的证据 | 人工 |

---

## 3. 要 `complete` 收口时

| # | 检查 | 机检 |
|---|---|---|
| 3.1 | 必须有 `evidence`（workspace-relative 路径），工具强制 | R4（工具级） |
| 3.2 | **执行者自报 PASS 不算验收**：Lead 必须亲跑关键门禁，或另派未参与实现的 verifier | 人工（R1 级强制） |
| 3.3 | 判"过期/已完成"**必须同时查** ① 任务书spec'd路径 ② 仓库内**功能等价物**（防假阴性） | 人工 |
| 3.4 | 退役成员名下的任务**必须同轮收口**，否则立刻变幽灵 owner | `stall`（机检 FAIL） |
| 3.5 | 收口后重导快照（`team_snapshot`）并跑 `team_audit` | 人工 |

### 本轮实证
```
3.2: 多个 agent 报「全 PASS」⇒ Lead 复跑后才发现
     · 32 条「红」其实是探针口径错误（showFlashInfo 不经门面）
     · 基线 math/mermaid 的「复制 0/4」部分是探针缺陷
3.4: 退役 p0-selection 后 task-79/75 立刻变幽灵 owner ⇒ 机检 FAIL 2 条
```

---

## 4. 要打包 / 发版 / 改 tag / 强推时（**R1 单向门**）

### 前置（缺一不可）
```
4.1 应用必须完全退出（Memoria.exe 进程数 = 0）—— 否则 EBUSY 残壳
4.2 整目录备份当前 Package（保留回滚点），并打印可直接复制的回滚命令
4.3 预演 ≥3 种失败模式（预 mortem），每种给应对
4.4 核对远端状态：该 tag 是否已存在？若存在且指向不同 commit ⇒ 先决定（删/换号），不要盲推
4.5 版本一致性三查：__version__.py == docs/conventions/version.md §1 == Package/VERSION
```

### 执行
```
4.6 顺序严格：改版本 → 构建 → 验证(Package/VERSION + 实测启动) → commit → tag → push → Release
4.7 「实测启动」= 进程存活 + 窗口出现 + **窗口标题显示正确版本** + 无 crash.log
    （只看 exit code / success:true 不算）
4.8 Release 标题**只写** `Memoria vX.Y.Z`；正文双语（中 → --- → 英），**两段都要造价章节**
```

### 事后
```
4.9  校验双资产 state=uploaded + 大小合理（对照上一版）
4.10 校验 tag 指向发布 commit
4.11 记录到 team/dispatch-log
```

### 本轮实证（为什么 4.4 必须写进规范）
```
我原本准备「删除旧 v0.4.6 tag 并重建」，
查 GitHub API 才发现 【远端根本没有 v0.4.6】—— 本地 tag 从未推送。
⇒ 若按原计划操作，会做出一个多余且不可逆的 tag 删除。
```

---

## 5. 只能靠自觉的 3 条（其余都已下沉）

```
S1. 派发的 prompt 里，必读文档要**点名到节**（别只给路径）
S2. 回报里必须区分「实测」与「推断」，且**明确写未测项**
S3. 任何"看起来成功其实没做"的路径，修法是**让失败可见**，不是"改对就完"
```

**为什么只有这 3 条**：其余 20+ 条都已变成机检或工具拒绝 ——
**规范的价值不在于"我会读它"，而在于"我读不读都得照做"。**

---

## 6. 机检对应表（`team_audit.py` 11 类）

| 类 | 覆盖本文件的 |
|---|---|
| `snapshot_health` | 快照新鲜度/结构 |
| `roster` | §1.1 名册一致性、§3.4 幽灵成员 |
| `stall` | §3.4 幽灵 owner、无人认领 |
| `write_scope` | §1.2 写域重叠、§2.3 写域缺失 |
| `artifact_refs` | §3.1 证据路径存在性 |
| `role_evidence` | 角色是否真在运转（14 天三源证据） |
| `silent_failure` | L2 静默失败（S1–S6） |
| `contract_drift` | 契约声明↔现实（D1–D6） |
| `commit_hygiene` | 提交卫生（H1–H3） |
| `lessons_stale` | 教训库是否在更新 |
| **`dispatch_release`** | **§1.1 spawn↔任务、§4.5 版本三查、§4.10 tag↔commit** |
| `mode_policy` / `plan_consulted` / `role_registration` / `dead_path_edit` | §1.3b 模式路由、L8 计划先行、§2 注册同步、§3 死文件 |
| `decision_trail`（待实现） | **§6 决策记录义务（T1–T3 + 6 条防伪造判据）** |

---

## 6. 要做一个"决策"时（记录义务）

### 触发（T1–T3，任一命中即须记录）
| # | 触发 | 例子 |
|---|---|---|
| **T1 可回退但影响后续走向** | 改代码/改组织资产/改团队规范 | 「P0-b 降为 P1」「退役 3 个 v4-pro」 |
| **T2 判断类（有备选被否）** | 选方案 A 不选 B | 「拒绝复制会话改用记忆卡」「steward 不合并」 |
| **T3 不可回退（R0/R1）** | 发版/迁移数据/强推/删 tag | 「v0.4.6 发布」「删旧 tag」 |

### 检查清单

| # | 动作 | 机检 |
|---|---|---|
| 6.1 | **判定是否触发**（T1/T2/T3；都不命中 ⇒ 不记录，别给所有提交加 trailer） | `decision_trail`（task-102/103 实现） |
| 6.2 | **有提交** ⇒ 在提交信息末尾写 trailer（键名固定，改名会破坏机检）：<br>`Decision:` ≤200 字、非空<br>`Why:` ≤200 字、非空<br>`Alternatives:` ≥1 项且每项含 `rejected:`（发版/回退必填）<br>`Rule-Ref:` 可选，`path#section` 必须能解析<br>`Reversibility:` 可选，∈ {R0,R1,R2}<br>`Human-Directive:` 实现人指令时必填，须为**原文摘录** ≤120 字<br>`Decision-Id:` 可选，形状 `dec-\d{8}-[0-9a-f]{8}` | 同上 |
| 6.3 | **无提交**（纯对话决策）⇒ `python scripts/agent/decide.py append --question ... --choice ... --alternative ... --why ...` | `team/decisions.jsonl` |
| 6.4 | **R0/R1** ⇒ 7 天内找**非决策者**做一次对抗复核（`review.verdict`）；决策者自己复核无效 | 人工 + `decision_trail` |
| 6.5 | **违反的后果**：首两周 **WARN**（不阻断），之后 `team_audit::decision_trail` **FAIL**（收口必须处置） | 分阶段 |

### 防"事后编理由"（6 条机器判据，来自设计稿）
```
A1 时效窗口：决策记录时间必须早于或接近决策生效时间（超窗 ⇒ 标 reconstructed）
A2 reconstructed 标记：事后补写的必须显式标，不得伪装成当时写的
A3 append-only：decisions.jsonl 只追加，永不改写（改 = 伪造）
A4 同提交绑定：trailer 必须在【决策所在那个提交】里，不能事后单独补一个提交
A5 R0/R1 对抗复核：非决策者 7 天内复核
A6 机器不创作 why：decide.py 只落盘人/Lead 写的内容，永不自作理由
```

### 本轮实证（为什么要 6.2）
```
Lead 自省曾说「P0-b 降 P1 的 43ms 理由在 commit 26fa9bc6 里」
steward 抽查该 commit 完整 message：既无 43ms 也无 P0-b
⇒ 理由连 commit 都没进，只存在于已压缩的会话
另：0.4.7 的实施提交 a68ab655(10-23 13:19) 早于台账计划(10-23 22:52)
⇒ 现在跑决策/计划类机检能自动发现，不靠人抓
```

---

## 变更记录

| 日期 | 变更 |
|---|---|
| 2026-10-24 | 首版。来自 0.4.6 一天的实施复盘：靠记忆的规则全漏（writeScope / 远端 tag / 版本权限），靠工具强制的零漏 |
