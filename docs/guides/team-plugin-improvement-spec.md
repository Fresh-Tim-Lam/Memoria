# 团队插件改进规格（DSH Agent Teams）

> **来源**：2026-10-23 第三轮团队复盘（Curator r3）。**只出规格，不实现**——本轮运行时
> `app.asar` 是 **10-21 构建**，源码 10-23 15:52 才有 `creator` 支持 ⇒ Creator 模式当前不可用，
> 需重打包 + 重启才生效（见 §5）。
> **对照材料**：`docs/prompts/tmp.md`（插件用法）、
> `D:\deepseek-harness\packages\experimental\tool-agent-team\src\index.ts`（工具注册）、
> `docs/guides/agent-team-status.md`（Memoria 现状）、`docs/guides/agent-team-org.md`（组织）。
> **每一条需求都来自一次**真实事故**，不是"最好有"**；每条给 `理由` + `验收方式`。

---

## 0. 一句话结论

现有 11 个工具足以**跑**团队，但不足以**证明**团队在跑。缺口集中在三类：
**① 事实不落盘（roster/派发/收口）② 约束不 fail-closed（done 无产物也能过）③ 无周期触发**。
其中 ①③ 只能 DSH 侧修；② Memoria 侧已用 `dispatch_log.py` 守卫 + `team_audit.py` 9 类机检补了大半。

---

## 1. 需求总表（按优先级）

| ID | 需求 | 归属 | 事故来源 | 优先级 |
|---|---|---|---|---|
| **R1** | roster 可落盘（`list_agents` 的机器可读快照） | **DSH 必须改** | 三方对账缺一角：快照 11 名 vs 实况 13 名，无人发现 | P0 |
| **R2** | 派发自动审计日志（spawn/send/retire → append-only JSONL） | **DSH 必须改** | A5：11 次 spawn 全无记录，60+ 任务只有 3 条 done | P0 |
| **R3** | `team_task_create` 强制 owner（或显式 `unassigned` 理由） | **DSH 必须改** | 12 条未完成任务 **0 条有 owner**，`stall`/`write_scope` 检查全部空转 | P0 |
| **R4** | `complete` 必须绑定产物（artifact/evidence 字段） | **DSH 必须改** | "做完了"不可验证；Memoria 侧已用 dispatch-log 补，但任务板本体仍无绑定 | P1 |
| **R5** | `team_snapshot` 工具（任务板 + roster 导出 JSON 到指定路径） | **DSH 必须改** | C1：手写快照写错字段名（`name` vs `target`）⇒ FAIL=10 且无法回滚 | P1 |
| **R6** | 周期触发（scheduled task / session-start hook） | **DSH 必须改** | DSH 无 cron ⇒ Curator 只能靠人喊；D1/D2 漂移存活 43 天 | P1 |
| **R7** | `spawn_teammate` 暴露 `preset` / `toolFilter` / `persona` | **DSH 必须改** | 写域只能靠提示词，无法工具级约束（Curator 能改 `src/**` 而无拦截） | P2 |
| **R8** | 每个 teammate 的 token/耗时统计进 `list_agents` | **DSH 必须改** | 无法回答"常驻 Owner 比 spawn 便宜吗"——组织决策缺成本数据 | P2 |
| **R9** | 重建 `app.asar`（含 creator preset）并给出重启指引 | **DSH 必须改** | 源码有 `creator`、运行中的 asar 没有 ⇒ 规格落地但不可用 | P0（阻塞） |
| **M1** | 派发日志 fail-closed + 更正协议 | **Memoria 侧✅已做** | S1–S6；done 无产物被拒；3 条死链按 `corrects` 修 | — |
| **M2** | 9 类机检（含 silent_failure / contract_drift / commit_hygiene） | **Memoria 侧✅已做** | 修掉两处假绿（写域无输入、12 条无主任务） | — |
| **M3** | 组织改造（standby 三分 + 退役 4 名 + §13 风险分级） | **Memoria 侧✅已做** | 9 个 Owner 全 inactive 却对外称"在运转" | — |
| **M4** | 收口 4 命令纪律写进 org.md §10.1 | **Memoria 侧✅已做** | 机检不跑 = 没有 | — |

---

## 2. DSH 必须改的（逐条）

### R1 roster 可落盘（P0）

**问题**：`list_agents` 只返回给模型看，**不落盘**。于是"文档 ↔ 快照 ↔ 实况"三方对账里，
第三方永远缺失；`team_audit.py` 只能比前两方 ⇒ 漂移必然发生。实测：快照 `members` 11 名、
`org.md` 称 11 名，同一时刻 `list_agents` 返回 **13 名**（`curator-r3` 与 `team-curator` 并存）。

**规格**：新增 `team_snapshot`（或 `list_agents { writeTo: "<path>" }`），字段固定：

```jsonc
{ "schema":"team-roster/v1", "exportedAt":"<ISO>",
  "limit":{"maxMembers":16,"used":12},
  "members":[{"target":"...","role":"lead|teammate","status":"running|inactive|provisioning|failed",
              "model":"...","mode":"fresh|fork","description":"..."}] }
```

**理由**：没有落盘就没有对账；`status` 是唯一能区分"在跑/闲置/创建中"的机器事实。
**验收**：
1. `team_snapshot` 产出的文件可被 `json.load`；
2. Memoria 侧 `team_audit.py::roster` 增加第三方比对后，**人为 spawn 一个成员 → 机检必须 FAIL**（先证红）；
3. 快照 `exportedAt` 晚于最后一次 roster 变更。

### R2 派发自动审计日志（P0）

**问题**：`spawn_teammate`/`send_message`/`retire_teammate` **不写任何仓库文件**。
Memoria 靠 Lead 手工 `dispatch_log.py append`，实测 11 次 spawn 只有 1 条 spawn 记录（且 ts 是补记值，
spawn→done 相差 1 秒）。"谁在干活"只能靠 789 个磁盘文件反推。

**规格**：`agent-team` 插件增加配置：

```yml
agent-team:
  auditLog: "team/dispatch-log.jsonl"   # 相对 workspace；append-only JSONL
  auditFields: [ts, actor, phase, target, task, outcome]
```

事件映射：`spawn_teammate→spawn`、`send_message→message`、`retire_teammate→retire`、
`team_task_update{complete}→task.complete`。**DSH 只写自己的事实**（谁派给谁、何时、结果态），
语义字段（`report`/`desc`）仍由 Memoria 侧补。

**理由**：A5 的根因不是"Lead 忘了"，而是**没有任何机制要求记**；要求模型每轮手写日志 =
一定会漏（实测漏 90%+）。
**验收**：跑一次 `spawn → send → retire`，日志自动出现 3 条；`ts` 单调；
与 Memoria 手写行**共存**（同格式、同文件），并用 `python scripts/agent/dispatch_log.py check` 校验通过。

### R3 `team_task_create` 强制 owner（P0）

**问题**：本轮实测 `team-board-snapshot.json` **12 条未完成任务，0 条有 `owner` 字段**，
连 `writeScopes` 也是 0 条 ⇒ `stall`（只扫 in_progress）、`write_scope`、`artifact_refs`
三个检查**全部空转**，而机检输出仍报"全绿"（Memoria 侧已补「输入不足」WARN 兜底）。

**规格**：`team_task_create` 二选一：给 `owner`（成员 target）或给 `unassigned_reason`。
`team_task_update{claim}` 是唯一能把任务变成"有人"的通道；`status=in_progress` 而 `owner` 为空 ⇒ 拒绝。

**理由**：**无人认领的任务 = 不会有人在等它**，但它占着任务板且让所有活性判据失真。
**验收**：`team_task_create` 不带 owner 且不带理由 ⇒ 报错；带 `unassigned_reason` ⇒ 成功且
快照里该字段可见；`status=in_progress` 且无 owner ⇒ 拒绝。

### R4 `complete` 绑定产物（P1）

**规格**：`team_task_update { action:"complete", evidence:[{path, sha256?}] }`；
`complete` 时 `evidence` 为空 ⇒ 拒绝（或需 `no_artifact_reason`）。

**理由**：与 Memoria 侧 `dispatch_log.py --phase done` 的 fail-closed 同构；
两处都堵住，"完成声明"才真的可验证。
**验收**：空 evidence 的 complete 被拒；带路径的 complete 在 `team_task_get` 里能读回该字段。

### R5 `team_snapshot` 工具（P1）

**问题**：快照是 Lead **手写 JSON**。C1 实测：把 `target` 写成 `name` ⇒ 检查器 FAIL=10，
而 `artifacts/` 当时无 git 历史 ⇒ 无法回滚，只能读源码反推格式。

**规格**：与 R1 合并实现（一个工具同时导出 roster + 任务板）：

```jsonc
{ "schema":"team-board-snapshot/v3", "exportedAt":"<ISO>",
  "limit":{...}, "members":[...], "retired":[...],
  "tasks":[{"id","status","owner","subject","writeScopes","blockedBy","revision"}] }
```

**理由**：**凡是人能手工写错的格式，都不该由人手工写。**
**验收**：导出文件直接通过 Memoria `team_audit.py` 的 `snapshot_health` + `roster`（FAIL=0），
无需人工改字段。

### R6 周期触发（P1）

**问题**：DSH 无 cron（`tmp.md` §C 边界明确写了）。Curator 只能靠"用户喊一句"或 Lead 显式派发。
结果：D1/D2 类契约漂移存活 43 天，靠用户偶然问"审视团队插件"才暴露。

**规格**（二选一，成本递增）：
- **R6a（最小）**：`session_start` hook —— 新会话启动时若 `git status` 显示团队资产有未提交变更，
  或距上次审计 > N 天，注入一条 reminder 到 Lead 的 system prompt（"该跑 `team_audit.py` 了"）。
- **R6b（完整）**：`schedule` 支持（已有 `schedule_create` 工具在 harness 层，但 Team 侧无入口）
  —— 允许声明 `on_schedule` 的 teammate 任务，到点自动 spawn 一次 Curator。

**理由**：**没有触发通道的检查等于没有检查**（这正是本轮在 Memoria 侧修的病）。
**验收**：R6a：把审计间隔设成 0 天 → 新会话必须出现 reminder；设成 365 天 → 不出现。
R6b：声明 `every_seconds: 60` 的任务，2 分钟内必须被自动派发一次。

### R7 暴露 `preset` / `toolFilter` / `persona`（P2）

**现状**：`tmp.md` §C 明确写「`persona` / `tool_filter` / 裸 `preset` 目前是**服务级 API**，
`spawn_teammate` 只暴露 `mode`/`model`」。⇒ Curator 的"只能写团队资产"**没有任何工具级约束**。

**规格**：`spawn_teammate` 增加可选 `preset`、`toolFilter:{deny:[...]}`、`persona`。
**理由**：让写域约束从"提示词自觉"变成"工具不存在"。这也是 `tmp.md` 自己列的能力缺口。
**验收**：`spawn_teammate{toolFilter:{deny:["write","edit"]}}` 的 teammate **无法**调用 write
（调用即工具不存在错误），而读/跑命令仍可用。

### R8 teammate 成本统计（P2）

**规格**：`list_agents` 每个成员带 `usage:{inputTokens,outputTokens,toolCalls,lastTurnMs}`。
**理由**：Q4 的组织决策（常驻 vs 一次性）现在只能靠感觉。没有成本数据，"9 个 Owner 该不该退役"
永远吵不清。**验收**：跑一个 teammate 一轮后，`usage` 三项均 > 0；父会话汇总可见。

### R9 重建 `app.asar`（P0，阻塞项）

**事实**：运行中的 `app.asar` 是 **10-21 构建**；`creator` preset 在源码 **10-23 15:52** 才加入
⇒ 本轮 `spawn_teammate({mode:"creator"})` 不可用，只能用 `standard` 模式 + 提示词顶替。

**规格**：重打包 + 明确重启指引；在 UI/日志里打印 `app.asar` 构建时间，
使"源码有、运行时没有"这类错配**当轮可见**而不是靠人猜。
**验收**：`spawn_teammate({mode:"creator"})` 成功；新成员回复中出现 `plugin_manager` / `cordis`；
启动日志含 asar 构建时间戳。

---

## 3. Memoria 侧自己就能做的（本轮已完成 / 仍可做）

| ID | 内容 | 状态 | 证据 |
|---|---|---|---|
| M1 | `dispatch_log.py`：done 无 `--report` ⇒ 退出码 2 不写入；`--no-report-reason` 显式豁免；`corrects` 更正协议（append-only 下唯一合法修法） | ✅ 本轮 | `--selftest` 红 7 类 PASS；3 条死链已按协议更正 |
| M2 | `team_audit.py` 9 类检查：新增 `silent_failure`(S1–S6) / `contract_drift`(D1–D6) / `commit_hygiene`(H1–H3)；修掉 2 处假绿 | ✅ 本轮 | `--selftest` 红 fixture 20 项断言 PASS；实仓 FAIL=0 |
| M3 | 组织改造：state 三分（active/standby/retired）、退役推荐队列、§13 风险分级 R0/R1/R2 | ✅ 本轮 | `org.md §2.3 / §13`；`agents.json` schema v3 |
| M4 | 收口 4 命令纪律（`team_audit` ×2 + `dispatch_log` ×2） | ✅ 本轮 | `org.md §10.1` |
| M5 | **仍可做**：`scripts/agent/team_dispatch.ps1` 一条命令 = append + 跑 4 机检 + 落报告 | ⏳ 未做 | 降低"忘了跑检查"的概率 |
| M6 | **仍可做**：把 `list_agents` 输出手工存档进快照（R1 未落地前的替代） | ⏳ 未做 | 需 Lead 每轮手工，成本高但可行 |

---

## 4. 为什么不是"每个改动都派 agent"

成本口径（今日实测）：73 提交 / 天，若每条都派独立审查 ≈ 73 次固定开销。
风险分级后 **R2 约 3–6 次/天**（`commit_hygiene` H1+H2+H3 命中集），
R0/R1 靠机检 + 同轮自检覆盖。详见 `org.md §13.1`。

---

## 5. 生效路径（本轮不可绕过）

1. DSH 侧：`pnpm run build`（或项目既有打包脚本）重建 `app.asar`；
2. 重启桌面应用（**当前 Web GUI 不会自动加载新 asar**）；
3. 再 `spawn_teammate({mode:"creator"})` 验证 R9 验收条件；
4. R1–R8 需要改 `packages/experimental/tool-agent-team/**` 与 `agent-team` 运行时，
   属 DSH 宿主改动，**不在 Memoria 仓库内**；Memoria 侧只能出规格 + 提供机检验收。

---

## 6. 附：本轮核对过的插件事实（避免规格过时）

| 事实 | 出处 | 影响 |
|---|---|---|
| 11 个 Team 工具（spawn/send/list/wait/interrupt/update/retire + 4 个 task） | `tmp.md §D`；`index.ts` 11 处 `scoped.tools.register(defineTool(...))` | 无"导出/快照/审计日志"类工具 |
| `maxMembers` 默认 16，只数 teammate | `tmp.md §五`；`agent-team-profile/cordis.patch.yml` | 11 名常驻占 69% 名额，其中仅 2 名有证据 |
| 无 cron | `tmp.md §C 边界` | Curator 无法周期性触发（R6） |
| `persona`/`toolFilter`/`preset` 仅服务级 | `tmp.md §C 边界` | 写域无法工具级约束（R7） |
| Creator mode 需 `creatorPreset`（默认 `cordis`）在 profile 内 | `tmp.md §五` | 运行中 asar 无此 preset ⇒ 不可用（R9） |
