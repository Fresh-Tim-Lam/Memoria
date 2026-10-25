# 团队工作记录机制 与 团队管理员（Steward）设计

> **状态**：设计稿（待 Lead 批准后拆实现任务）。**未生效**。
> **作者**：steward（deepseek-flash），2026-10-24。
> **读者**：Lead（批准/执行者）、人（可复核）、未来任何一代 steward / 带教。
> **依据**：task-97；人 2026-10-24 原话；`AGENTS.md §0.5`、`docs/guides/lead-dispatch-rules.md`、
> `docs/guides/agent-team-lessons.md`、`docs/guides/agent-team-org.md`、`scripts/agent/team_audit.py`（11 类）。
> **本文的证据规则**：所有数字标 **[实测]**（本次可复跑，命令见附录 D）或 **[推断]**。
> 没有第三种写法。

---

## 0. 结论摘要（先给结论，再给论证）

1. **记录机制 = 3 个写入通道 + 1 个只读投影。**
   动作层用 DSH 插件的结构化轨迹（task-95，不另起炉灶）；任务层用**机器生成的档案投影**（不手写）；
   决策层用**决策索引**（`choice + alternatives + 一句话 why + 证据指针`），**不是决策文库**。
2. **角色 = 1 个（steward），三条输出通道**（组织资产 / 过程审计 / 决策索引维护）。
   **建议把 task-96 的独立 `mentor` 角色取消**，其内容并入 steward 章程（理由见 §3.2）。
3. **首期真正的产品 = 6 个新机检**，其中 **3 个今天就能落地**（已有现行条款可引），
   另 3 个需要先补协议条款（**先有条款，后有检查**——这是防过拟合的硬顺序，见 §5）。
4. **决策层的核心不是"写更多文档"，而是"把已经发生的决策变成可查询的索引"。**
   Lead 的 4 个例子里有 3 个其实已经在磁盘上（commit / README / 任务书），
   缺的是**结构化 + 可查询 + 时效可验**，不是再写一遍。
5. **角色合法性来源 = 机器审 steward**（`standards_read` 收据 + `rule_ref` 可解析 + 转换率指标），
   人/Lead 只做抽查。一个不能被机器审的审计者，就是新的单点风险（§6）。

---

## 1. 现状盘点（先查现状，不凭空设计）

### 1.1 数据源实测表

| 数据源 | 体量 **[实测]** | 粒度 | 写入者 | 缺口 |
|---|---|---|---|---|
| `team/dispatch-log.jsonl` | 32 行 / 8,637 B；覆盖 10-20～10-24 | spawn/message/done/retire/backfill | Lead | **只有生命周期，没有中间过程**；无 `model` 字段（模型事故无从机检） |
| `team/team-board-snapshot.json` | 48,733 B；93 任务 / 8 成员；`exportedAt=18:01:09+08` | 任务 | Lead 导出 | `tasks[]` **只有 7 字段**（id/status/subject/owner/writeScopes/blockedBy/revision），**无 description / evidence / 时间戳**；`completedRecent` 只留 10 条 ⇒ **任务档案缺半边** |
| 任务板（live） | 97+ 任务含 completed；`team_task_list` 返回 description/revision/evidence | 任务 | 所有成员（工具） | 无 created/updated 时间戳 ⇒ **算不出"领取→关闭"时长与卡顿** |
| `git log` | 555 commits；近 3 天 210；近 50 条提交信息平均 **1,227 字符** | 提交 | Lead/人 | 正文里**有**理由（38 行含"因为/取舍/替代/放弃"），但 **0 条结构化**：近 60 条提交中 `Decision:/Alternatives:/Rule-Ref:` trailer = **0** |
| `artifacts/agent/verify/**` | 139 份报告 / 921 条路径引用 **[实测，team_audit]** | 报告 | 成员 | 报告是**产出**，不是过程；且 `artifacts/` 被 gitignore（无版本追溯） |
| session（DSH 会话） | Lead 报 42.6 MB/长会话 **[推断/引自 Lead]** | 全量对话 | 宿主 | 没人读得动；**只能作为证据引用，永不进上下文** |
| `team_audit.py` | 90,894 B / 12 检查类 | 状态 | 只读机检 | 检查**状态**（名册/写域/幽灵 owner），**不检查"怎么干活"** |
| `team/memory/` | 目前仅 README（卡机制 task-87 实现中） | 成员经验 | 插件/Lead | 尚无一张真实卡 |

### 1.2 五个结构性缺口（这五个就是本设计的靶子）

**G1｜决策理由不可查询（决策层空白）**
- 近 3 天 210 个提交里，38 行出现"理由类"词（`因为|理由|取舍|替代|放弃|不选|拒绝`）**[实测]**；结构化 trailer = 0。**[实测]**
- 抽查 Lead 点的例子 `26fa9bc6`（"P0-b 从 P0 降 P1 / 43ms"）：完整 message 中 **未见 "43ms" 或 "P0-b"** **[实测]** ⇒ 比 Lead 的自省更严重：**连"埋在 commit 里"都没做到**，理由只在会话里。
- 后果：会话一压缩，按 `AGENTS.md §0`"压缩摘要能保留事实，但不保留约束"的同一机理，**理由先于事实丢失**。

**G2｜任务档案缺半边（任务层不完整）**
- 快照 `tasks[]` 不含 description / evidence / 时间戳 **[实测，见 1.1]**，而"完整任务档案"需要这三者。
- `team_task_list` 有 description/evidence，但**无时间戳**，且一次只能拉一页 100 条（202 KB spill）。
- "弯路"没有落点：报告里偶有记录，但**不结构化、不按任务索引**。

**G3｜快照时效没有"审计前"门禁**
- 现状：`snapshot_health` 会 WARN"快照可能过期"，但**没人处置也不阻断**。
- 实测：快照 18:01 导出；`agents.json` 18:09 被改（新增 steward）；task-95/96/97 18:05 创建 ⇒ 快照**缺 3 条任务 + 1 个新角色**。
- 判据：**审计必须在新鲜快照上做**，否则 steward 会审计一个不存在的世界。

**G4｜动作层不存在**
- `dispatch-log` 只有开头和结尾（32 行），中间过程（读了什么、写了什么、跑了什么门禁、失败几次）**完全缺失**。
- 于是"规范不到位 / 指示歧义 / 风险动作"三类问题**只能靠 Lead 事后回忆**发现——本轮人抓到 Lead 三次同类失误，全部属于这一类。

**G5｜新角色注册不是原子操作（设计第一天就被机检抓到）**
- 当前 `team_audit.py` = **FAIL=1 / WARN=39 / INFO=9** **[实测 18:2x]**，唯一 FAIL 是：
  `contract_drift: active 角色 steward 既不在 roster 成员中、也未声明 roster_alias`。
- 根因：注册一个角色要改 **3 处**（`agents.json` / `org.md §2.2` / DSH roster）+ **重导出快照**，
  而机检只做**两两比对**（agents↔snapshot、org↔snapshot），**没有"三方全等 + 快照晚于注册修改"的检查**。
- 这类漂移已重复发生 ≥3 次（`curator` vs `team-curator` vs `curator-r3`；v4 修复"7 个成员只存在于 org"；本次 steward）。
  ⇒ 满足"同一问题只应发生一次"的机检条件（§7 `role_registration`）。

---

## 2. 三层记录机制

### 2.0 总图与数据所有权（先定"谁唯一拥有哪份数据"，再谈格式）

```
                     ┌────────────── 写入通道（3 个）──────────────┐
  动作层 L1   DSH 插件 ──自动──▶ team/trajectory/<member>.jsonl（append-only；不进 git）
             Lead ──手工──▶ team/dispatch-log.jsonl（生命周期；进 git）
  任务层 L2   任何成员 ──工具──▶ 共享任务板（意图/状态/evidence）
             成员 ──完成时──▶ team/memory/<member>.md §我试过但失败的路（弯路）
  决策层 L3   决策者 ──提交时──▶ git commit trailer（有提交的决策）
             决策者 ──决策时──▶ team/decisions.jsonl（无提交的决策）
             规划者 ──规划时──▶ docs/todo.md §N + planRef（范围/顺序决策）
                     │
                     ▼
              ┌── 只读投影（1 个）──┐
              │ scripts/agent/work_record.py  │  按成员/任务/决策/风险查询；
              │   join: 任务板 × dispatch-log × git × evidence        │  不存量、不手写、不产生第二事实源
              └──────────────────┘
```

**数据所有权表（防重复、防两套口径——教训 L1.1 的教训）**

| 数据 | 唯一写入者 | 唯一存储 | **禁止出现在** |
|---|---|---|---|
| 派发生命周期（谁被招募/派发/退役） | Lead | `team/dispatch-log.jsonl` | 轨迹、任务板 description |
| 工具动作（读/写/门禁/失败/重试/风险动作） | 插件（自动） | `team/trajectory/*.jsonl` | dispatch-log（永不加入工具调用行）、报告正文 |
| 任务意图与状态（要什么/什么状态/证据路径） | 所有成员（经工具） | 共享任务板 | 报告 |
| 交付证据（产物/命令/读数） | 执行者 | 报告文件 + `task.evidence` | 决策记录（只引用指针） |
| **决策理由**（选了什么/放弃什么/为什么） | **决策者本人** | commit trailer / `team/decisions.jsonl` | 报告正文（可引用，不复制） |
| 组织标准（规则/派发/章程） | Lead + 人 | `AGENTS.md` / `docs/guides/**` / `team/agents.json` | **steward 的任何缓存/报告**（只能引用 + sha256） |
| 会话原文 | 宿主 | session | 任何人的上下文（仅作证据引用：file+turn） |

> **唯一性判据**：如果同一事实在磁盘上有两处可写副本，它一定会分叉（教训 L1.1 已实测：
> `dispatch_log.py` 与 `team_audit.py` 对 `no_report_reason` 判定相反，产生假红）。
> 所以本设计**只允许"引用"，不允许"复制"**。

### 2.1 动作层（L1）：结构化轨迹，不是 transcript

**结论：直接采用 task-95 的 L1 规格，steward 不另行设计事件格式。** 本设计只补三件事：

**(a) 与 `dispatch-log` 的边界（写死，不许互相长）**

| 问题 | 归属 |
|---|---|
| 谁被 spawn / message / retire？何时？结果？ | `dispatch-log`（组织级） |
| 该成员在任务里读了哪些文件、写了哪些文件、跑了哪些门禁、失败几次、重试几次？ | `trajectory`（工作级） |
| 两者怎么 join？ | 共同键 `task`（任务 id）+ `member`（成员 id）。**不允许靠 ts 近似匹配** |

**(b) 建议在 task-95 的 5 条最小集合上**新增 2 类事件（需 Lead 批准并转给 team-plugin-creator）：

| 新增事件 | 为什么必须 | 能查出的问题 |
|---|---|---|
| `kind:"decision"`（含 `decision_id` / `alternatives_count` / `reversibility`） | 决策层要能在**动作发生的那一刻**留下指针，而不是事后回忆 | "事后编理由"从"无法判定"变成"时间戳可验"（§2.3 A1） |
| `kind:"gate_run"` 增加 `ok:false` 后的下一步（`continued` / `stopped`） | 现有规格只记"跑了门禁"，不记"门禁红了之后干了什么" | **门禁失败后继续**（lessons §7 R1 风险动作） |

**(c) 风险动作分类（直接映射 `agent-team-lessons.md §7`，机检可用）**

| 标记 | 触发（在 trajectory 里可判定） | 依据 |
|---|---|---|
| `risk:R0` | 删用户 KB 文件、`git checkout/restore/reset` 作用于 `src/**`、清 KB | lessons §7 + 2026-10-24 "两次摧毁 agent 未提交工作" |
| `risk:R1` | `git push --force`、`git tag -d`、发版/打包、迁移数据 | `AGENTS.md §0.5 L5`、`lead-dispatch-rules.md §4` |
| `risk:gate_fail_continue` | `gate_run.ok=false` 后同一任务仍继续写 | lessons L2.2（让失败可见） |
| `risk:write_without_read` | `file_write` 前同任务内无该文件 `file_read`（由事件流派生，不新增事件） | DSH 文件策略 + `AGENTS.md §0.5 L7` 精神 |

> **Phase 0 兜底（重要）**：task-95 未落地前，动作层的可用代理 = `git`（改了什么）+ `dispatch-log`（谁被派）+ 报告 mtime。
> steward **不等插件也能开始审计**（§8 分期 P0）；但 `write_without_read` / `retries` 两类必须等 task-95。

**(d) 与 session 的边界**
session 是**原始证据**，只在报告里以 `session:<session-id>#turn=N` 形式引用；
steward 不读 session 正文（42MB，且读了会污染判断），也不复制到 trajectory。

### 2.2 任务层（L2）：任务档案 = 机器生成的投影，不是新存储

**结论：不新建"任务档案库"。** 任务档案 = `work_record.py` 在查询时 join 出来的**只读投影**：

```
任务档案(task-XX) = 任务板条目（意图/状态/evidence/owner）
                  + dispatch-log 中 task=task-XX 的行（谁被派、何时 done）
                  + git log 中 提交信息含 "task-XX" 的提交（改了什么、什么时候）
                  + 报告文件（evidence 指向的磁盘产物）
                  + 决策索引中 task 字段=task-XX 的决策（裁决）
                  + memory 卡中该任务的段（弯路，若已生成）
```

**为什么必须是投影而不是存储**：三个来源各自有唯一写入者（表 2.0），
再存一份档案 = 第四份可写副本 ⇒ 必然分叉。**投影的判据：删掉投影文件，重启可逐字节重建。**

**"弯路"的落点（不新增存储）**：`team/memory/<member>.md` 的
`### 我试过但失败的路`（`team/memory/README.md` 已定义结构）。任务完成时由插件抽取（task-87 E1），
steward 只检查"有返工特征的任务是否有对应卡段"（P2 检查，依赖 task-95 的 `retries`）。

**"裁决"的落点**：决策索引（§2.3），任务只存 `decision_id` 指针。

**P1 插件建议（R10，交 team-plugin-creator 评估）**：快照 `tasks[]` 补 `description`（截断 ≤500B）、
`evidence`、`createdAt`、`updatedAt`。**没有 createdAt/updatedAt，所有"卡了多久"的判据都无法机检**（G2/G3）。

### 2.3 决策层（L3）：决策索引，不是决策文库

**核心判断（这是本设计最值钱的一条）：**
> 决策记录**不应该**再写一篇论证文章。论证文章已经存在（commit 正文 / README / 设计稿 / 报告）。
> 缺的是：**选了什么、放弃什么、一句话为什么、证据在哪**——这四样加起来 200～400 字节，可查询、可校验。

因此决策记录 = **索引行**，长论证留在它指向的文档里（`evidence[].ref`）。

#### 2.3.1 三个写入通道

| 通道 | 适用 | 载体 | 格式 | 体量 **[估算]** |
|---|---|---|---|---|
| **D1 commit trailer** | 有提交的决策（改代码/改组织资产/发版） | git commit message | 键值 trailer（见 2.3.2） | ~150–400 B/提交 |
| **D2 `team/decisions.jsonl`** | 没有提交的决策（拒绝提案、选型、角色去留、流程改动） | append-only jsonl（进 git） | 见 2.3.3 | ~600 B/条 |
| **D3 `planRef` + `docs/todo.md §N`** | 范围/顺序/版本级规划决策 | 台账章节 + 任务 `planRef` | task-89 已定义强制 | 已在台账预算内 |

> 三通道的**分工判据**：这条决策**会不会改变仓库字节**？
> 会 ⇒ D1（与改变它的提交同 commit）；不会（只是"决定不做/不做那个"） ⇒ D2；
> 是"某版本做什么、先做什么" ⇒ D3（`planRef` 强制链已在 task-89）。

#### 2.3.2 D1：commit trailer 键表（与 `git interpret-trailers` 兼容）

```
<subject>

<body —— 保留原有详细说明，不动>

Decision: 本轮只发 v0.4.6，0.4.7「收摊」顺延到下一版
Alternatives: 同时发 0.4.6+0.4.7 (rejected: 收摊范围未审计、无 planRef — task-88); 只发 0.4.7 不发 0.4.6 (rejected: 0.4.6 已冻结且含修复)
Why: 两个版本的范围与验收标准都未定，合并发版会让"发布"承担未审计的范围
Rule-Ref: AGENTS.md#0.5 L8; docs/guides/lead-dispatch-rules.md#4
Reversibility: R1
Human-Directive: 人 2026-10-24「0.4.7 是收摊」——据此把 0.4.7 视为范围已定，但顺序仍需 todo-owner 产出
```

| 键 | 必填条件 | 约束（机检） |
|---|---|---|
| `Decision:` | 触发提交（T1–T3）**必填** | ≤200 字符，一句话，**写"选了什么"** |
| `Alternatives:` | T1/T3 与 `Reversibility: R1` 必填 | ≥1 个被拒选项，每个带 `(rejected: ...)`；只写"没有备选"需 `no_alternative_reason` |
| `Why:` | 触发提交必填 | ≤200 字符；**不允许为空或"见正文"**（正文不可查询） |
| `Rule-Ref:` | 可选 | `path#section`，必须能解析（见 §5 机制 1） |
| `Reversibility:` | 可选（默认 R2） | `R0|R1|R2`，与 lessons §7 对齐 |
| `Human-Directive:` | 实现人指令时必填 | ≤120 字符，**原文摘录**（防"替人加戏/曲解人"） |
| `Decision-Id:` | 可选 | `dec-YYYYMMDD-<sha8>`；与 D2 记录互链 |

#### 2.3.3 D2：`team/decisions.jsonl` schema

```jsonc
{"id":"dec-20261024-a1b2c3d4","ts":"2026-10-24T18:40:00+08:00","decided_by":"lead",
 "scope":"member-memory",                          // 自由标签，用于检索
 "question":"新成员如何继承前任经验：复制会话 vs 记忆卡",
 "choice":"记忆卡（≤8KB，append，带免责）",
 "alternatives":[{"option":"复制整段会话","why_rejected":"42.6MB×5=210MB 且会传播已推翻结论"}],
 "why":"载体可 git diff、可审计；错误项已剔除",
 "evidence":[{"kind":"doc","ref":"team/memory/README.md#为什么不是复制记忆","sha256":"<file sha>"}],
 "rule_refs":["docs/guides/agent-team-lessons.md#1"],
 "reversibility":"R2",
 "decision_id":"dec-20261024-a1b2c3d4",            // 与 D1 互链
 "task_id":"task-87",
 "reconstructed":false,                              // 见 A2
 "supersedes":null,
 "review":{"by":null,"at":null,"verdict":null}}     // R0/R1 需对抗复核，见 A5
```

**校验（`decide.py append` 在写入前 fail-closed，与 `dispatch_log.py` 同一风格）**：
① `id` 形状合法且不与历史重复；② `ts` ≥ 文件最后一行 `ts`（单调）；③ `decided_by` ∈ `agents.json` 或 `"human"`；
④ `alternatives` 非空，或 `no_alternative_reason` 非空；⑤ 每条 `evidence.ref` 中 `kind=doc|commit|task|report` 必须可解析
（文件存在 / commit 存在 / 任务存在）；⑥ `reconstructed` 必填布尔。

#### 2.3.4 谁写（Q1 的正面回答）

| 层 | 谁写 | 何时 | 为什么不是别人 |
|---|---|---|---|
| D1 | **决策者本人**（通常是 Lead；也可由成员在其提交里写） | 提交时（与改动同一 commit） | 理由在决策者脑里；换人写 = 二次加工 = 编理由 |
| D2 | **决策者本人** | 决策后 ≤10 分钟 | 同上；`decide.py` 提供 3 行命令，不增加认知负担 |
| D3 | **todo-owner**（范围/顺序）+ Lead（发版取舍） | 规划时 | task-89 已强制 `planRef` |
| 索引/去重/时效检查 | **steward** | 每轮审计 | steward **只做抽取和校验，永不创作 `why`** |
| 事后补录 | 任何人，但必须 `reconstructed:true` | 补录时 | 不禁止补录（禁不掉），但**让"补录"可识别**（A2） |

**三个方案的取舍（Q1 要求的权衡）**：

| 方案 | 自评偏差 | 深度 | Lead 负担 | 结论 |
|---|---|---|---|---|
| 自己写 | 有 | 高 | 低（3 行×触发提交） | **采用**，用 A1–A6 压制自评偏差 |
| 机器抽 | 无 | **浅**（只能抽已有文本，不能产生"为什么"） | 无 | **只用于抽取/索引，不用于创作** |
| Lead 代写他人决策 | 无 | 中 | 高 | 不采用（Lead 不知道成员权衡） |
| steward 事后重构 | 可能 | 中 | 低 | **只允许 `reconstructed:true`**，且不计入"决策已记录"指标 |

#### 2.3.5 防"事后编理由"：6 条机制（每条都给机器判据）

| # | 机制 | 机器判据 | 能防什么 / 防不了什么 |
|---|---|---|---|
| **A1** | **时效窗口** | D2 的 `ts` 必须 ≥ `evidence[].mtime - 120s` 且 ≤ **依赖该决策的第一个提交时间 + 120s**；D1 的 trailer 必须**在该提交内**（`git show -s --format=%B <sha>` 自查），不是后一个提交补 | 防"决策后很久补记录"。**防不了**"当场就编一个漂亮理由" |
| **A2** | **`reconstructed` 标记** | 若 `ts` 晚于 `evidence[].mtime + 10min` 或晚于依赖提交 ⇒ 必须 `reconstructed:true`；未标 ⇒ FAIL | 防"补录伪装成当场记录"；让"编的理由"永远带标签 |
| **A3** | **append-only + 更正协议** | `git log --numstat -- team/decisions.jsonl` 中任何提交 `removed > 0` ⇒ FAIL；更正必须新增 `{"corrects":{...}}` 行（与 `dispatch-log.py --corrects-*` 同协议） | 防"改历史理由" |
| **A4** | **同提交绑定** | T1–T3 触发提交必须**自身**带 trailer；后一个提交带不算 | 防"先做后补"（追溯标签但改变不了时序事实） |
| **A5** | **R0/R1 对抗复核** | `reversibility ∈ {R0,R1}` 的记录，7 天内必须有 `review.by`（非决策者）且 `verdict ∈ {accepted,challenged}`；`challenged` 必须附理由 | 防"单方叙事"——**自己写可以，但要有人挑刺** |
| **A6** | **机器永不创作** | `decide.py` / 提取器 / steward 报告中，`why`/`alternatives` 字段只能来自人输入的原文；审计报告只能**引用**（带 `decision_id`），不得改写 | 防"AI 帮着编一个合理理由" |

> **诚实边界**：以上只能让"事后编理由"**有痕迹**，不能让它**不可能**。
> 真正让它变少的是 A4 + `decision_trail` 机检的持续压力（第一次漏 = WARN，第二次 = 任务，第三次 = 该检查应已生效）。

#### 2.3.6 触发条件（什么算"必须记录"的决策；精确、可机检、避免过度触发）

| ID | 触发条件（精确） | 必填键 | 依据 |
|---|---|---|---|
| **T1 发版/版本号** | 提交改 `src/memoria/__version__.py` 或 `Package/VERSION` 或 `pyproject.toml` 的 version 行；或 subject 匹配 `^chore\(release\)` | `Decision/Why/Alternatives/Rule-Ref` + task-89 的 `planRef` | `AGENTS.md L5`、§4 发版 |
| **T2 单向门/组织资产** | 提交改 `Package/**`、`team/agents.json`、`AGENTS.md`、`docs/guides/lead-dispatch-rules.md`、`docs/guides/agent-team-org.md`；或删除 ≥20 行 | `Decision/Why`（R1 加 `Alternatives`） | `agent-team-org.md §13.1 R2`、`lead-dispatch-rules.md §4` |
| **T3 自修/回退** | subject 命中 `_SELF_FIX_RE`（`team_audit.py` 现有正则）或 `^Revert ` / `revert` | `Decision/Why/Alternatives` | `commit_hygiene H1`、lessons §7 |
| **T4 人指令** | 无法机检（steward 人工识别） | `Human-Directive` | 防替人加戏 |
| **不触发** | 常规 `feat/fix/docs/test`（不涉 T1–T3） | — | 控制负担 |

**触发比例实测**（近 3 天 210 提交）**[实测]**：T1=5、T2=12、T3 窄口径≈4 ⇒ 合计约 **21/210 ≈ 10%**。
按每条 ~250 B 计，**≈ 5 KB/3 天 ≈ 50 KB/月**——对 Lead 是**每 10 个提交写 3 行**，对仓库是可忽略体量。

#### 2.3.7 Lead 给的 4 个例子 → 每个落到哪个通道（证明"够用"）

| 例子 | 现状（实测） | 本机制下的落法 |
|---|---|---|
| 为什么是 0.4.6 而不是 0.4.7 | 只在会话 | **D3**：`docs/todo.md §14` 写"0.4.6 已带走 ③④；0.4.7 顺延" + **D1**：发版提交 `Decision/Alternatives` |
| 为什么 P0-b 从 P0 降 P1（43ms） | `26fa9bc6` 正文**未见 43ms** **[实测]** | **D1** 在该提交加 `Decision: P0-b 降为 P1（收益仅 43ms）`；同时任务报告写读数（证据）；插件轨迹 `kind:decision` 留指针 |
| 为什么拒绝"复制会话"改"记忆卡" | `team/memory/README.md` 已有论证表 | **D2** 一条索引：`choice=记忆卡`、`alternatives=[复制会话]`、`evidence=team/memory/README.md#...`（**长论证不复制**） |
| 为什么退役 3 个 v4-pro | commit `de27855a` 正文 | **D1**：`Human-Directive: 统一 flash，v4-pro 删掉` + `Decision` + `Alternatives`（保留 v4-pro 做长链） |

> 注意第 3 条：**现有文档已经能承担"论证文库"**。决策索引只是给它一个 200B 的门牌号。
> 这正是"索引不是文库"的证据：4 个例子里 2 个几乎零额外写作成本。

### 2.4 读取接口（`scripts/agent/work_record.py`，P0 实现）

四条查询，输出 Markdown（人读）+ JSON（机读）：

```
python scripts/agent/work_record.py task   --id task-95           # 任务档案（意图/证据/弯路/提交/决策）
python scripts/agent/work_record.py member --id todo-owner --since 7d  # 成员时间线
python scripts/agent/work_record.py decision --grep "0.4.6"        # 决策检索（question/choice/alternatives/why/evidence）
python scripts/agent/work_record.py risk   --since 7d              # R0/R1 动作清单（来自 trajectory + git）
python scripts/agent/work_record.py doctor                          # 自查：数据源缺失/陈旧/不可解析
```

**体量控制**：单任务档案输出 ≤ 8 KB（超长自动摘要 + `--full` 才展开）；决策检索默认 5 条 / ≤4 KB。
**明确不做**：不生成全团队"周报"（没人读）；不导出 session 文本。

---

## 3. 角色边界：一套还是两套

### 3.1 推荐：**一套（steward），三条输出通道**

| 通道 | 内容 | 写权限 | 输出 |
|---|---|---|---|
| ① 组织资产 | 名册/`agents.json`/`org.md`/任务板卫生/快照时效 | **只读 + 提案 diff**（Lead 执行） | 资产审计结论 + 修订提案 |
| ② 过程审计 | 规范不到位/指示歧义/风险动作 | 只读 | **新机检 + finding 任务 + 协议修订提案** |
| ③ 决策索引维护 | 抽取 trailer、去重、时效检查、`reconstructed` 标记 | 只读源 + 只写索引 | `team/decisions-index.jsonl`（机器生成）+ 漏记清单 |

### 3.2 为什么不是两个角色（方案 2 被否，含对 Lead 论证的修正）

Lead 的理由是"两人都要看全部工作 ⇒ 重复读数据 + 协调成本"。**这个理由在插件落地后会失效**——
如果动作层是机器生成的轨迹，读数据成本趋近于零，两个人也可以各读各的。
**所以真正否掉方案 2 的理由是另外两条**：

1. **判据的唯一性（教训 L1.1）**：两名审计者会对同一条证据给出不同判据。
   本仓库已实测过"同一判据两个实现 ⇒ 一个判 PASS 一个判 FAIL"（`no_report_reason` 假红）。
   审计判据比机检判据更主观，分叉概率更高。
2. **决策索引必须有唯一 owner**：决策层是"组织的记忆"，两个 owner 会出现两条互相覆盖的决策链
   （谁记、记哪条、`reconstructed` 谁判）。这与"单一事实源"直接冲突。

**同时否掉 task-96 的独立 `mentor` 角色**：task-96 的定位表（Lead/TODO Owner/团队管理员/带教）
在本设计里就是 steward 的三条通道 + todo-owner 的既有职责；**独立 mentor 会制造第 4 个"读全部工作的人"**，
且它的验收标准（"至少 1 条固化成机检"）与 steward 完全相同。
⇒ **建议：task-96 保留但改性质**——从"设立 mentor 角色"改为"steward 的过程审计通道落地"（owner=steward，依赖 task-95）。

### 3.3 内部分离：4 条硬边界（把"一个角色"关进笼子）

| # | 边界 | 为什么 | 机检投影 |
|---|---|---|---|
| B1 | **不写标准**：不得直接改 `AGENTS.md` / `lead-dispatch-rules.md` / `org.md` / `agents.json`，只能提 diff | 审自己写的规则 = 自评偏差 | 提交文件 ⊆ 声明写域（`steward_self_audit`） |
| B2 | **不 gate**：只给 severity，不给阻断权 | 阻断权在机检/人（人 2026-10-24 口径） | 无 gate 代码路径；finding 只是任务 |
| B3 | **不代写决策**：不补 `why`、不补 `alternatives`、不改写引用 | A6（机器永不创作） | `decisions.jsonl` 的 `author` 字段不含 steward |
| B4 | **不自审自己的检查实现**：新增检查必须由另一成员只读复核 | 自己写检查自己审 = 假绿温床（lessons L0.3/L1.1） | R1 级改动按 `org.md §13` 派独立复核 |

### 3.4 什么时候应该拆成两个角色（可判定触发，写下来防"以后拍脑袋"）

满足**任一**即提交 Lead 裁决拆分（拆成 `steward`=资产 / `mentor`=过程）：

1. **量**：连续 4 周，每周"需新增机检"的 finding > 3 条，且单轮审计的读取 + 产出 > 2 小时；
2. **瓶颈**：出现"因为 steward 未审计完，任务无法收口"的情况 ≥2 次/月（说明它已被当成 gate，违反 B2）；
3. **域冲突**：过程审计结论与组织资产维护结论**互相矛盾**（例如：某成员过程违规但资产上必须保留），此时一个角色无法同时给出两个方向的建议。

### 3.5 我反驳 Lead 的 3 处（点名，不客气）

**反驳 1｜"finding 必须进任务板"——应分级，否则任务板变垃圾场**
- 数据 **[实测]**：本轮 `team_audit` 产生 49 条 finding，其中 **WARN=39**。若每条进任务板，
  等于在 97 条任务上再堆 39 条低价值任务；`org.md §10.2` 的"任务卡死"治理会立刻被稀释。
- 建议：**FAIL 级 ⇒ 24h 内必须有任务（或挂到已有任务）；WARN 级 ⇒ 进 finding ledger（§6.2），同一条 7 天内第二次出现才建任务；INFO ⇒ 只记录**。
- 这样仍满足 Lead 的意图（"不允许只写 md"）：ledger 是机检可查的**结构化**记录，且有强制 disposition（open→task/fixed/dismissed/mechanized），
  **比一条孤立任务更容易死亡**（任务会被忘掉，ledger 的 `open>14d` 会报警）。

**反驳 2｜"真正的产品是新机检"——准确说是"被批准的条款 → 新机检"**
- 若 steward 可以直接把"发现"变成"检查"，它就把**自己的偏好**固化成法律——这正是 Q6 要防的过拟合。
- 建议硬顺序：**finding 必须能指到现行条款（`rule_ref` 可解析）；指不到 ⇒ 只能提"建议新增条款"，
  由 Lead/人批准后再写检查。** 检查本身是条款的投影，不是条款的来源。
- 附带收益：这条顺序让 steward **无法**用一个检查来证明自己是对的（检查红 = 条款红，不是 steward 对）。

**反驳 3｜"两条独立输出通道"——应是三条，且决策索引维护是独立工作量**
- 决策索引需要**持续**做：抽取 trailer、与 D2 去重合并、标记 `reconstructed`、检查 A5 对抗复核是否到期。
  这些既不是"资产"也不是"审计"，但有独立失败模式（索引漏抽 = 决策层静默失效）。
- 若硬塞进审计通道，会出现"审计报告写了结论，但索引没更新"⇒ 查询接口返回旧世界。
- 因此建议：通道 ③ 有**自己的完成判据**（每次审计后 `work_record.py decision --doctor` = 0 漏抽）。

---

## 4. 六个必答问题（逐条，结论 + 机制 + 残余风险）

### Q1 决策层记录怎么落盘？由谁写？

**落盘**：三通道（§2.3.1）——有提交的进 **commit trailer**（D1），无提交的进 **`team/decisions.jsonl`**（D2），
范围/顺序进 **`docs/todo.md §N` + planRef**（D3）；由 `work_record.py` 生成统一只读索引。
**由谁写**：**决策者本人在决策时刻写**（Lead 为主）。steward 只抽取/校验/索引，**永不创作 `why`**。
**防事后编理由**：A1 时效窗口 + A2 `reconstructed` 标记 + A3 append-only + A4 同提交绑定 + A5 R0/R1 对抗复核 + A6 机器不创作。
**为什么不写长文**：长论证已在 commit/README/设计稿；索引只放 `choice + alternatives + 一句 why + 证据指针`（200–400 B）。

**残余风险（明确写）**：当场编一个漂亮理由无法防；只能靠 A5 的对抗复核（R0/R1）和跨成员视角削弱。

### Q2 动作层与 dispatch-log / session 的边界？如何不重复、不爆炸？

**边界**：dispatch-log = **组织级生命周期**（谁被招募/派发/退役、何时闭合）；trajectory = **工作级动作**（读了/写了/跑了/失败/重试/风险动作）；session = **原始对话**（只作证据引用，永不进上下文）。
**不重复**：数据所有权表（§2.0）——每个字段只有一个写入者与一个存储；轨迹**只存 digest/路径**，不存文件内容与 diff。
**不爆炸**：单任务轨迹 ≤64 KB（task-95 硬上限）+ 滚动截断标 `truncated:true`；单成员单周 ≤2 个任务 ⇒ ≤128 KB；
全团队月量见 §4-Q4。

### Q3 一套角色还是两套？

**一套（steward）**，三条通道（§3.1）。核心理由是**判据唯一性 + 决策链唯一 owner**，不是"省名额"。
task-96 的独立 `mentor` **不设立**，改为 steward 的过程审计通道落地（§3.2）。
拆分触发条件写死（§3.4），避免以后拍脑袋。

### Q4 记录的体量预算？

| 层/通道 | 单条 | 单任务 | 单成员/月 | 全团队/月 **[估算]** | 存储位置 |
|---|---|---|---|---|---|
| dispatch-log | ~270 B/行 | 2–4 行 ≈ 1 KB | ~10 行 ≈ 2.7 KB | ~30 KB | git |
| L1 trajectory | ~200–300 B/事件 | ≤64 KB（硬上限） | 2 任务 ≈ 128 KB | ~30 任务 ≈ **1–2 MB** | `artifacts/`（不进 git） |
| L2 任务档案 | 生成，不存量 | 8 KB/次查询（不落盘） | — | 0 | — |
| L3 D1 trailer | ~250 B/条 | — | ~10 条/周 ≈ 10 KB | ~50 KB | git |
| L3 D2 decisions | ~600 B/条 | — | — | ~15 KB | git |
| L3 audit findings ledger | ~300 B/条 | — | — | ~40 KB | git |
| memory cards（弯路） | ≤8 KB/卡 | 1 段/任务 | — | ≤240 KB | git |
| **合计（进 git）** | | | | **≈ 0.4 MB/月** | |
| **合计（含轨迹）** | | | | **≈ 1.5–2.4 MB/月** | |

**对比**：Lead 报的长会话 42.6 MB **[推断/引自 Lead]** ⇒ 轨迹层约为会话的 **1/20**，
且只占 `artifacts/`；真正进版本库的组织记忆 **≈0.4 MB/月**（比现有 139 份 verify 报告还小）。
**读取成本预算**：steward 每轮重读标准 ≤50 KB（§6.1 明细）+ 本轮新数据 ≤60 KB + 输出 ≤20 KB。

### Q5 谁来审你？（合法性来源）

**四层，主力是机器（§6）**：
1. **`steward_self_audit` 机检**（P1）：`standards_read` 收据 sha256 与当前文件不一致 ⇒ **FAIL**（用缓存标准审计）；
   每条 finding 的 `rule_ref` 不可解析且未标 `proposal` ⇒ **FAIL**（把偏好当规范）。
2. **转换率指标**：连续 4 轮 `mechanized=0` 且 findings>5 ⇒ WARN「只唠叨不落地」（"同一个问题只应发生一次"的反面度量）。
3. **轮值同侪复核**：每轮审计报告由**一名不同成员**只读复核，在 `review.json` 里写 `accepted|challenged` + 理由（一次约 5 分钟）。
4. **人抽查**：人可随时按 `standards_read` 收据验证"它真的读了"，或直接推翻任一条 finding。

**合法性来源的表述**：steward **没有写标准的权力、没有阻断权、不能创作决策理由**；
它的每条结论都必须能被另一个模型用同一份 `standards_read` + 同一批证据重放。
**可替换性**：清空 steward 的上下文，新 steward 只靠磁盘应能跑出同类结论——这是最终验收（§8.4）。

### Q6 如何避免过拟合（把自己的偏好当规范）？

| 失败模式 | 机制 | 机检投影 |
|---|---|---|
| 凭印象报违规 | `rule_ref` 必须解析到**现存文件的现存章节**；解析失败 ⇒ 只能 `disposition:"proposal"` | `steward_self_audit` |
| 用自己的检查证明自己 | 检查必须挂到**已批准条款**；新条款由 Lead/人批准（反驳 2 的硬顺序） | 检查注册表（`team_audit.py` 头部注释必须写 `rule_ref`） |
| 只报容易报的 | 覆盖声明：报告必须写"本轮**没有**审计什么"（盲区清单） | 报告结构校验（缺 `blind_spots` ⇒ WARN） |
| 报太多 | FAIL/WARN/INFO 分级 + WARN 不建任务（反驳 1）；FP（被 Lead 驳回）率 >30% 的检查必须重写或下线 | `finding.disposition=dismissed` 统计 |
| 把"我不知道"写成"没问题" | 检查必须有 `checked_count`；=0 判 FAIL（lessons L1.1） | 沿用现有 `team_audit` 口径 |
| 把上一轮结论当标准 | `rule_ref` 只允许 `path#section`，**不允许**"上轮我说过"；`standards_read` 每次重读 | `steward_self_audit` |

---

## 5. 本轮 5 条教训 → 首批机检（这是"真正产品"的示范）

> 判定：**能在现行规范里找到条款的**（可立即算违规）标 ✅；**找不到的**标 🆕（只能先提"建议新增条款"，
> 批准后才变成违规）——**这条区分本身就是防过拟合的落实**。

### 5.1 映射总表

| # | 本轮教训 | 新机检 | 现行条款（rule_ref） | 状态 | 严重度 |
|---|---|---|---|---|---|
| 1 | 整轮没咨询 todo-owner 就排 0.4.7 范围 | `plan_consulted` | `AGENTS.md §0.5 L8`（"版本级规划必须由 todo-owner 产出并写进 docs/todo.md；Lead 不得凭记忆排期"） | ✅ 可立即违规 | WARN→FAIL |
| 2 | 写了 8 条不变量防"靠记忆"，回头又靠记忆排期 | 同上（L8 的机检投影）+ `decision_trail` 的 T1 `planRef` 校验 | `AGENTS.md §0.5 L8` + task-89 的 `planRef` | ✅/🆕 各半 | FAIL |
| 3 | agent 报"全 PASS"，复跑发现 32 条是探针口径错误 | `claim_scope`（结论必须声明未测边界） | `agent-team-lessons.md §6 L6.4`（"明确写未测项"）+ `L1.5`（断言打在用户可见输出） | ✅ 可立即违规 | WARN |
| 4 | 修了 `p5perf_workload2.mjs` 才发现它无入口 | `dead_path_edit`（改了无引用文件） | `agent-team-lessons.md §0 L0.3`（"测试必须走被测路径"） | ✅ 可立即违规 | WARN |
| 5 | spawn 用 `mode:deep` 导致 v4-pro，违反"统一 flash" | `model_policy`（成员模型必须白名单） | **无**（只有 `agents.json` 的 note / commit）⇒ 需先新增 `org.md §2.1 维护纪律 6` | 🆕 需新增条款 | FAIL |
| 6 | 新角色注册三处不同步（ steward 自己） | `role_registration`（三方全等 + 快照晚于注册修改） | `agent-team-org.md §2.3 执行纪律 1`（"必须在同一轮 ① 更新本表与 §2.2 ② 重导出快照 ③ 清理队列"） | ✅ 可立即违规 | FAIL |
| 7 | steward 自己是否靠谱 | `steward_self_audit` | **无** ⇒ 需先新增 `org.md` steward 章程 | 🆕 需新增条款 | FAIL |

### 5.2 三个 P0 检查的具体判据（Lead 可直接拿去实现）

#### ① `plan_consulted`（已在当前仓库上复现真实违规）

```
输入：git log --since=N --name-only --format=@@%H|%ad|%s；docs/todo.md 的 -S 历史；__version__.py 当前版本
步骤：
  1) 版本家族 V = {X.Y.*}，X.Y 取自当前版本
  2) 对每个 V：
       t_impl = min(提交 ts | 提交信息含 V 且 改动含 src/ 或 scripts/ 且 不含 docs/)
       t_plan = min(提交 ts | 提交改动 docs/todo.md 且 diff 中新增行含 V)
  3) t_impl 存在 且（t_plan 不存在 或 t_plan > t_impl）⇒ WARN（首月）→ FAIL
     message: "版本 V 的实施提交(${t_impl})早于台账计划落盘(${t_plan}) 26h —— 违反 AGENTS.md §0.5 L8"
rule_ref: AGENTS.md#§0.5 L8
红 fixture：临时 git 仓里先提交含 V 的 src 改动，再提交含 V 的 docs/todo.md ⇒ 必红
```
**当前仓库预期结果 [实测]**：`0.4.7` 的 `t_impl=10-23 13:31`（`e374463f`），`t_plan=10-24 18:00`（`d35d4395`）
⇒ **该检查在 10-23 就会报红，早于人 2026-10-24 抓到 Lead。** 这是"同一个问题只发生一次"的直接证据。

#### ② `role_registration`（当前 FAIL 的更锋利版本）

```
三个来源：
  A = agents.json 中 status=active 的 id（含 roster_alias 展开）
  B = org.md §2 + §2.2 解析出的 owner id
  C = snapshot.members[].target（+ 同 id 字段）
判据 1：A == B == C（三方全等；别名展开后比较）⇒ 否则 FAIL，打印三方差集
判据 2：snapshot.exportedAt 必须晚于 agents.json / org.md 的 mtime ⇒ 否则 WARN「快照不可能反映注册修改」
judge_ref: docs/guides/agent-team-org.md#§2.3 执行纪律 1
红 fixture：三份 fixture 各缺一个成员 ⇒ 三种 FAIL 都要出现
```
**当前预期 [实测]**：A 含 steward，B/C 不含 ⇒ FAIL；且 `exportedAt 18:01 < agents.json mtime 18:09` ⇒ WARN。

#### ③ `dead_path_edit`

```
输入：近 N 天每个提交的改动文件 f（限 src/**、scripts/**；排除 tests/ 与白名单入口）
步骤：refs = git grep -l "<basename(f)>" HEAD -- ':(exclude)<f>'
      若 refs 为空 且 f 不在白名单（入口脚本需在文件头 5 行内标 `@entry`）
      ⇒ WARN "修改了无引用文件，先确认它在生产/测试路径上（lessons L0.3）"
rule_ref: docs/guides/agent-team-lessons.md#L0.3
红 fixture：新建一个无人引用的 .mjs 并提交 ⇒ 必红；给同文件加 @entry ⇒ 必绿
```
> 白名单必须**从仓内实测生成**（否则第一次全红 = 假红灾难，lessons L1.2）。
> 建议白名单初值 = 近 30 天被 `python`/`node` 直接调用的入口（可由 `git grep` 反查）。

### 5.3 需要新条款的两个检查（先协议、后检查）

**`model_policy`** 需要的条款（建议加到 `org.md §2.1 维护纪律` 第 6 条）：
> 6. **模型默认 `deepseek-flash`**；任何成员使用其它模型必须 Lead 在 `agents.json` 该成员上记
>    `model_exemption: {reason, approved_at, approved_by}`，并在收口报告披露。无豁免的非 flash 成员 = FAIL。
>    （依据：人 2026-10-24「团队统一 flash」；本次事故：spawn 用 `mode:deep` 导致成员变 v4-pro。）

**`decision_trail` + `steward_self_audit`** 需要的条款：`AGENTS.md §0.5 L9` + `lead-dispatch-rules.md` 新增 §6（决策记录）
+ `org.md §2.2/steward 章程`。**建议文本见附录 A/B。**

---

## 6. Steward 的工作机制（读完批准即可照做）

### 6.1 每次审计必做（"重读标准"的机械化）

```
1. 新鲜度：team_snapshot 重导出（或确认 exportedAt ≥ 最近一次任务/agents.json 变更）
2. 重读标准（≤50 KB，必须记 sha256，禁止用缓存文本）：
     AGENTS.md §0.5                     （≤15 行）
     docs/guides/lead-dispatch-rules.md （全文 7.5 KB）
     docs/guides/agent-team-lessons.md  （全文 11.7 KB）
     docs/guides/agent-team-org.md §2.3/§10/§13（按需分节，≤10 KB）
     scripts/agent/team_audit.py 检查清单（头部注释 + grep '^def check_'，≤2 KB）
3. 跑机检：python scripts/agent/team_audit.py --json（拿现状 FAIL/WARN）
4. 跑工作记录投影：python scripts/agent/work_record.py doctor + 四条查询
5. 产出：
     team/steward/audit-<date>/standards_read.json   ← 读了什么（path + sha256 + 行数）
     team/steward/audit-<date>/SUMMARY.md            ← ≤20 KB，人读
     team/steward/audit-<date>/findings.jsonl        ← 结构化 finding + disposition
     （原始大产物放 artifacts/agent/verify/steward/，不进 git）
6. finding 处置：FAIL ⇒ 24h 内建任务；WARN ⇒ ledger；重复 ≥2 次 ⇒ 建任务
7. 转换：把可机检的 finding 变成 `team_audit` 新检查类（需 Lead 批准条款/写域）
8. 自审：跑 `steward_self_audit`（P1 前手工核对同样判据）
```

### 6.2 finding ledger（`team/steward/findings.jsonl`，append-only，进 git）

```jsonc
{"finding_id":"SF-20261024-001","audit_ts":"2026-10-24T18:40+08:00",
 "severity":"WARN","check":"plan_consulted","rule_ref":"AGENTS.md#§0.5 L8",
 "claim":"0.4.7 的实施提交早于台账计划落盘 26h","evidence":["git:e374463f","git:d35d4395"],
 "task_id":null,
 "disposition":"open",                  // open|fixed|dismissed|mechanized
 "mechanized_as":null,                  // 如 "team_audit.py::plan_consulted"
 "disposition_by":null,"disposition_at":null,"note":null}
```

**生命周期（机检）**：`open>14d` ⇒ WARN；`severity=FAIL` 且 `open>24h` 且 `task_id=null` ⇒ FAIL；
`dismissed` 必须有 `disposition_by` + `note`（防静默忽略）。

### 6.3 `standards_read.json`（防"落伍"的收据）

```jsonc
{"audit_ts":"...","tool":"team_audit.py@<sha256>",
 "standards":[
   {"path":"AGENTS.md","sha256":"…","sections":["§0.5"],"read_at":"..."},
   {"path":"docs/guides/lead-dispatch-rules.md","sha256":"…","sections":["全部"],"read_at":"..."},
   {"path":"docs/guides/agent-team-lessons.md","sha256":"…","sections":["全部"],"read_at":"..."}
 ],
 "not_read":["docs/guides/agent-team-org.md#§13（本轮无 R1 改动）"]}
```
**判据**：`sha256` 与磁盘当前文件不一致 ⇒ **FAIL「用缓存标准审计」**。
`not_read` 非空必须写理由——这是**盲区声明**，不是免责。

---

## 7. 落地计划（分期 + 任务板拆分）

### 7.1 分期

| 期 | 依赖 | 内容 | 为什么能先做 |
|---|---|---|---|
| **P0（现在）** | 无 | ① 设计批准 ② `plan_consulted` / `role_registration` / `dead_path_edit` 三个机检 ③ `work_record.py`（dispatch+任务板+git 三源） ④ `decide.py` + `decisions.jsonl` ⑤ steward 章程注册 | 不依赖 task-95；条款已在盘上 |
| **P1（task-95/87 生效后）** | task-95 轨迹、task-87 记忆卡 | ⑥ `decision_trail`（T1–T3 + 抽取索引） ⑦ `model_policy` ⑧ `steward_self_audit` ⑨ `claim_scope` | 需要轨迹/卡/新条款 |
| **P2（观察 2 周后）** | P1 数据 ≥2 周 | ⑩ `read_before_write`（没读就写） ⑪ `card_on_retire`（有返工但无卡） ⑫ 同侪复核轮值 | 需要足够样本否则全是假红 |

### 7.2 任务板拆分（建议 Lead 按此创建/改派；含 owner / writeScopes / 关闭条件 / 依赖）

| # | 任务 | owner | writeScopes | 关闭条件 | 依赖 |
|---|---|---|---|---|---|
| **T1** | **steward 章程注册**：`org.md` 新增 §2.2 行 + steward 章程节（B1–B4/通道/自审）；`agents.json` steward 条目补 `tier/model/write_scope/forbidden/prompt_ref`；重导出快照；`team_audit` FAIL 归零 | **Lead**（DSH 操作 + 标准写权限） | `docs/guides/agent-team-org.md`、`team/agents.json`、`team/team-board-snapshot.json` | `python scripts/agent/team_audit.py` FAIL=0 且 `role_registration` 三方全等 | 本设计批准 |
| **T2** | **决策记录协议**：`AGENTS.md §0.5 + L9`、`lead-dispatch-rules.md` 新增 §6（D1 键表/触发 T1–T4/示例）、`org.md §2.1` 纪律 6（model_policy 条款）；附录 A/B 文本直接采用 | **Lead**（标准文件只有 Lead 有权写） | `AGENTS.md`、`docs/guides/lead-dispatch-rules.md`、`docs/guides/agent-team-org.md` | 三处条款落地 + 条款里每条都有 `rule_ref` 可被机检解析 | 本设计批准 |
| **T3** | **P0 机检三类**：`plan_consulted` / `role_registration` / `dead_path_edit` 写进 `team_audit.py` + 红 fixture 自测（`--selftest` 必须能红） | **steward** | `scripts/agent/team_audit.py`、`artifacts/agent/verify/steward/**` | `--selftest` PASS（红 fixture 各自必红）；三检查在当前仓库跑出预期（`plan_consulted` 应报 0.4.7）；排除假红白名单有实测依据 | T2（条款），可并行写 |
| **T4** | **`work_record.py`**：任务档案 / 成员时间线 / 决策检索 / 风险清单 / `doctor` 五命令 + 自测；数据源缺失必须显式报错（不静默空） | **steward** | `scripts/agent/work_record.py`、`artifacts/agent/verify/steward/**` | ① 用 task-95/96/97 跑通（任务档案含 owner/evidence/相关提交）② 数据源缺失时 doctor 报 FAIL ③ 单任务输出 ≤8 KB | 无（P0 可做） |
| **T5** | **`decide.py` + 决策索引**：append 校验（§2.3.3 六条）、`decisions.jsonl` 建库、trailer 解析、`work_record decision` 联调 | **steward** | `scripts/agent/decide.py`、`team/decisions.jsonl`、`artifacts/agent/verify/steward/**` | ① 用 4 个历史决策（§2.3.7）回填 2 条 `reconstructed:true` ② 非法记录被拒（缺 alternatives/时间倒流/坏 evidence）③ 与 dispatch-log 一样有 selftest | T2 |
| **T6** | **`decision_trail` 机检**（T1–T3 检测 + trailer 抽取 → 索引） | **steward** | `scripts/agent/team_audit.py`、`artifacts/agent/verify/steward/**` | 红 fixture：构造缺 trailer 的 T1 提交 ⇒ 必红；当前仓库近 3 天预期 ~19 条（宽限期 WARN） | T2 + T3（同文件串行） |
| **T7** | **`model_policy` 机检** | **steward** | `scripts/agent/team_audit.py` | 红 fixture：把快照某成员 model 改 v4-pro ⇒ 必红；当前全 flash ⇒ 绿 | T2 条款 |
| **T8** | **`steward_self_audit` + `standards_read`** | **steward** | `scripts/agent/team_audit.py`、`team/steward/**`、`artifacts/agent/verify/steward/**` | ① 篡改 standards_read 的 sha ⇒ 必红 ② 不可解析 rule_ref ⇒ 必红 ③ `open>14d` finding ⇒ WARN | T1 章程 |
| **T9** | **插件侧增补（转 team-plugin-creator）**：task-95 事件集加 `kind:"decision"` + `gate_run` 的 `continued/stopped`；快照 `tasks[]` 增 `description/evidence/createdAt/updatedAt` | **team-plugin-creator** | DSH 仓库 | 与 task-95 同一套测试口径；事件样本含 decision；快照字段可被 `work_record.py` 消费 | task-95 |
| **T10** | **首轮审计**（验收本机制）：用真实数据跑一次，≥3 findings 且至少 1 条降级为 proposal、至少 1 条固化成机检 | **steward** | `team/steward/**`、`artifacts/agent/verify/steward/**`、任务板 | 报告 + findings.jsonl + 至少 1 个新检查落地；`steward_self_audit` 绿 | T1–T8 |

> **串行化提醒**：T3/T6/T7/T8 都写 `scripts/agent/team_audit.py` ⇒ **同一时刻只能一个在写**（`writeScopes` 会告警）。
> 顺序：T3 → T6 → T7 → T8（其中 T6/T7/T8 可在 T3 后由 Lead 决定是否合批）。

### 7.3 `agents.json` 改动建议（**不直接改**，交 Lead）

steward 现有条目（Lead 18:09 已加）建议补齐/收紧如下字段：

```jsonc
{
  "id": "steward",
  "name": "团队管理员（steward）",
  "status": "active",
  "tier": "resident-l2",              // 非领域常驻（与 todo-owner 同级）
  "model": "deepseek-flash",          // 人 2026-10-24 统一 flash；供 model_policy 机检
  "scope": "teammate",
  "input_contract": [
    "重读：AGENTS.md §0.5 / lead-dispatch-rules / lessons / org §2.3·§10·§13 / team_audit 检查清单（每次，禁缓存）",
    "机器投影：work_record.py（任务档案/成员时间线/决策索引/风险清单）",
    "team/steward/findings.jsonl（历史 finding 生命周期）"
  ],
  "output_contract": [
    "team/steward/audit-<date>/{standards_read.json, SUMMARY.md, findings.jsonl}",
    "新机检（写 team_audit.py；需 Lead 批准条款与写域）",
    "协议修订提案 diff（不改标准文件本体）",
    "finding 任务（FAIL 24h 内；WARN 走 ledger）"
  ],
  "write_scope": [
    "team/steward/**",
    "scripts/agent/steward_*.py",
    "scripts/agent/team_audit.py（仅新增检查类，不改既有判据语义）",
    "artifacts/agent/verify/steward/**"
  ],
  "forbidden": [
    "直接改 AGENTS.md / lead-dispatch-rules.md / agent-team-org.md / team/agents.json（只能提案）",
    "创作或改写决策的 why / alternatives",
    "阻断任务或发 gate（只给 severity）",
    "用缓存标准审计（必须带 standards_read sha256）",
    "git push --force"
  ],
  "prompt_ref": "docs/guides/team-work-record-and-steward-design.md",
  "emits": ["steward.audit", "steward.finding", "steward.proposal"]
}
```
（现状 entry 已有 `write_scopes`/`note`，字段名与其它成员不一致：其它成员用 `write_scope`；**建议统一为 `write_scope`**，
否则 `contract_drift` 未来若校验字段名会产生新分叉。）

### 7.4 `agent-team-org.md` 改动建议（**不直接改**，交 Lead）

1. **§2.2 表格新增一行**（与 todo-owner 同级，不进 §2 领域计数）：

```markdown
| `steward`（团队管理员） | 组织资产维护（名册/agents.json/org/任务板卫生/快照时效）+ 过程审计（规范/指示/风险动作）+ 决策索引维护；**产品是新机检与协议修订，不是报告**；不阻断、不写标准、不代写决策 | 不拥有代码领域；两条证据来源 = 机器投影 + 每次重读的现行标准 |
```

2. **新增 §2.6「steward 章程」**（约 25 行）：B1–B4 边界、三条通道、`standards_read` 收据、
   finding 生命周期、自审机制（§6.3/6.2）、拆分触发条件（§3.4）。
3. **§2.3 执行纪律 1 补一句**：注册新角色 = 改 3 处 + 重导出快照，**由 `role_registration` 机检三方全等**。
4. **§2.1 维护纪律新增第 6 条**：模型默认 flash + `model_exemption`（§5.3 文本）。

### 7.5 验收：怎么证明这套机制在工作（4 条可测判据）

1. **决策可查询**：对 §2.3.7 的 4 个问题，`work_record.py decision --grep` 在 5 秒内返回
   `choice + alternatives + why + evidence`（允许 2 条带 `reconstructed:true`）。
2. **同一问题只发生一次**：每个已确认 finding 在 30 天内有 disposition；**≥50% 的 FAIL 级 finding 最终变成机检**
   （`mechanized`）。
3. **steward 可替换**：清空上下文后新 steward 仅凭磁盘跑出同类 finding（无隐藏知识）——这是本设计对"不共享记忆"的最终检验。
4. **体量不超标**：`git count-objects -v` 级别的月增 ≤1 MB（team/ 内）；单任务轨迹 ≤64 KB（task-95 已定）。

---

## 8. 未决项（需 Lead / 人裁决；我不假装确定）

| # | 未决 | 我的建议 | 为什么不能自己定 |
|---|---|---|---|
| U1 | steward 是否**直接**持有 `scripts/agent/team_audit.py` 写权限 | 建议持有（只新增检查类），但每次新增走 T1 章程 + 独立复核 | "审计者改审计器"是 B4 边界，需 Lead 裁决风险 |
| U2 | task-96 独立 `mentor` 是否取消 | 建议取消独立角色，改为 steward 过程通道（§3.2）；task-96 改属 steward | 角色编制是人/Lead 的决定 |
| U3 | `decision_trail` 的宽限期长度（WARN→FAIL） | 建议 2 周（约 20 个触发提交的样本） | 影响 Lead 日常提交负担，需 Lead 拍板 |
| U4 | 决策索引的**旧历史回填范围** | 建议只回填 §2.3.7 的 4 条（其余不回填，避免大规模重构理由） | 回填会诱发"事后编理由"，需人同意边界 |
| U5 | R0/R1 对抗复核的**轮值成员池** | 建议 `arch-contract` / `doc-consistency` / `metrics-baseline` 轮值（只读 5 分钟） | 涉及他人工作负荷 |
| U6 | `claim_scope` 的误报率 | 建议先 WARN 观察 2 周再定阈值 | 报告风格差异大，样本不足 |
| U7 | 轨迹存储位置（`team/trajectory/` 还是 `artifacts/`） | 建议 `artifacts/`（体量大、不进 git）；但**决策/ledger 必须进 git** | 影响"可追溯性"与仓库体积，需 Lead 定 |

**我这次明确没做的事（诚实边界）**：
- **没有**读任何 session（42MB；按设计不应读）；因此"过程层"结论全部来自磁盘证据，不是会话记忆。
- **没有**直接改 `team/agents.json` / `org.md` / `AGENTS.md` / `lead-dispatch-rules.md`（只有提案）。
- **没有**创建 `team/steward/**` 目录（不在本任务写域）；T4/T5 落地时才建。
- **没有**验证 `artifacts/` 之外的历史报告是否可靠（只抽查了 1 条 commit，不代表全量）。
- 体量估算中的"42.6 MB 会话"是**引自 Lead**，未独立测量。

---

## 附录 A：决策 trailer 校验规则（给 `decide.py` / `team_audit.py` 实现者）

```
KEY            必填（触发）      校验
Decision:      T1/T2/T3        非空、≤200 字符、不含"见正文"
Alternatives:  T1/T3/R1        ≥1 项且每项含 "rejected:"；否则须 no_alternative_reason
Why:           T1/T2/T3        非空、≤200 字符
Rule-Ref:      可选            path#section 必须解析（文件存在 + 标题存在）
Reversibility: 可选            ∈ {R0,R1,R2}
Human-Directive: 人工识别        实现人指令时必填，≤120 字符，须为原文摘录
Decision-Id:   可选            形状 dec-\d{8}-[0-9a-f]{8}；与 D2 互链
```

## 附录 B：`AGENTS.md §0.5` 建议新增 L9（Lead 批准后加入）

```
L9. 决策必须留索引：可回退的决策（改代码/发版/改组织资产/回退）在提交内写 Decision/Why（发版与回退另加 Alternatives）；
    不可回退决策（R0/R1）7 天内由非决策者做一次对抗复核；无提交的决策写入 team/decisions.jsonl。
    无法指到现行条款的"发现"只能作为建议新增，不得直接变成检查。
```

## 附录 C：`lead-dispatch-rules.md` 建议新增 §6 的骨架

```
## 6. 要做一个"决策"时（记录义务）
6.1 判定是否触发（T1–T3，见 design §2.3.6）
6.2 有提交：在提交信息末尾写 trailer（模板见 design §2.3.2）
6.3 无提交：python scripts/agent/decide.py append --question ... --choice ... --alternative ... --why ...
6.4 R0/R1：7 天内找非决策者复核（review.verdict）
6.5 违反的后果：首两周 WARN；之后由 team_audit::decision_trail FAIL（不阻断合并，但收口必须处置）
```

## 附录 D：本文实测数据的复跑命令

```powershell
# 体量
(Get-Item team/dispatch-log.jsonl).Length; (Get-Item team/team-board-snapshot.json).Length
# 提交/触发比例（近 3 天）
git log --since='3 days ago' --oneline | Measure-Object -Line
git log -60 --format='%B' | Select-String '^(Decision|Alternatives|Rule-Ref):' | Measure-Object -Line   # ⇒ 0
# 0.4.7 计划-实施时序（本设计的关键证据）
git log --all --oneline --grep='0.4.7' --format='%h %ad %s' --date=format:'%m-%d %H:%M'
git log -S'0.4.7' --format='%h %ad %s' --date=format:'%m-%d %H:%M' -- docs/todo.md
# 当前机检基线
python scripts/agent/team_audit.py
# 角色三方一致性（当前 FAIL 的根因）
git ls-files team/ | Select-String 'steward'; Select-String team/agents.json -Pattern '"id": "steward"'
```
