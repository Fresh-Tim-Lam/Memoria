# 改造 Team 能力 —— 交给创造模式 Agent 的完整规格

> **本文用途**：这是一份**改造指令 + 验收标准**，不是角色提示词。
> 交给能修改 DSH 宿主 / 有权改团队资产的人（或未来的创造模式 agent），
> 由它按本规格把 Memoria 的 team 能力从「Trae 时代空壳」改造成「DSH 下能自我维护的团队」。
>
> **写于**：2026-10-23 实测审计之后。
> **配套**：`docs/guides/agent-team-status.md`（当前真实状态 + 复跑命令）、
> `docs/guides/curator-agent-prompt.md`（创造模式 agent 的系统提示词）。

> **实施状态（2026-10-23）**：P1 / P2 / P3 / P4 / P5 均已完成并通过验收（P5 经人类确认后执行，
> `artifacts/agent` 750.2 MB → **66.7 MB**）。DSH 宿主侧没有新增独立 agent 模式，而是用
> `spawn_teammate({mode:"creator"})` 提供 Creator 模式 Curator（preset `cordis`）。
> 实际落地与偏差见文末 **第七部分：实施状态与偏差**。

---

# 第一部分：现状（实测，可复跑）

## 1.1 四个团队资产层的真实状态

| 层 | 文件 | 实测结论 |
|---|---|---|
| 角色注册表 | `team/agents.json` | 3 条目（builder / verifier / registrar）字段齐全，但**从未被触发** |
| 角色提示词 | `team/prompts/*.md` | 3 份，mtime 全部 **2026-09-10**（43 天零改动） |
| 事件流 | `artifacts/agent/events.jsonl` | **不存在**（文件自身注明「契约预留，当前未落盘」）|
| 团队契约 | `AGENTS.md` §0–§7 | 描述「主控派发 + 事件订阅」，**DSH 下不成立** |
| DSH 实操指引 | `docs/guides/dsh-agent-teams-contract.md` | 描述「Lead + spawn_teammate + 任务板」，**与实际一致** |

## 1.2 结论

```
契约（AGENTS.md） 描述的是 Trae/SOLO 载体
实操（dsh-*.md）  描述的是 DSH 载体
⇒ 两套并存，没人声明哪一套作废
⇒ 新人读 AGENTS.md 会以为 builder/verifier/registrar 在运转（实际 0 次）
```

## 1.3 资产体积

`artifacts/agent/` = **813 文件 / 750.1 MB**，其中约 **600 MB** 是一次性调试产物
（`heap-*.json.gz` 61.4MB×2、`p6c-new-diag-*.json` 30MB×8）—— 产出后无任何提交/文档引用。

---

# 第二部分：改造目标（要变成什么样）

## 2.1 终态定义

改造完成后，团队应满足**四条可验证属性**：

| # | 属性 | 验证方式 |
|---|---|---|
| **T1** | **单一载体** | 团队契约只有一份「当前有效」描述，另一份明确标为历史 |
| **T2** | **每个角色有触发通道** | 每个 non-retired 角色，能指出其触发机制（事件/任务板/关键词/定时）并找到 ≥1 条运行记录 |
| **T3** | **产出可追溯** | 每个角色的产出物能被 `git log` / 文档引用追到；未被引用的中间产物定期清理 |
| **T4** | **自我维护** | 存在一个 `curator` 角色，能独立执行审计并**修改**团队资产（不是只出报告） |

## 2.2 角色设计（改造后的目标形态）

**保留 3 个真实角色 + 新增 1 个：**

| 角色 | 触发 | 输入 | 输出 | 与现状差异 |
|---|---|---|---|---|
| **Lead** | 用户直接对话 | 用户需求 + 任务板 | 任务板条目、派发、最终复核、提交 | 新增：**必须记录派发决策**（写 `team/dispatch-log.jsonl`）|
| **执行者**（原 builder，改名 `executor`）| 任务板认领 | `team_task_*` 任务描述 | 代码/文档变更 + 自测结果 + 磁盘报告 | 去掉 `events.jsonl` 依赖，改任务板 |
| **审计者**（原 verifier，改名 `auditor`）| Lead 显式派发 或 关键词 | 被执行者声明的变更 + 门禁脚本 | `artifacts/agent/verify/**` 报告 | 去掉 `on_events: ["change.applied"]`（该事件不存在）|
| **登记官**（原 registrar，保留）| Lead 显式派发 或 定时 | 审计通过结果 | 更新 `docs/README.md` 索引 / `todo.md` §12 / `maintenance-jobs.md` §5 | 去事件依赖；**新增**：清理过期登记 |
| 🆕 **Curator** | 定时（每周）或关键词「审视团队」 | 团队资产 + 任务板历史 + 磁盘产物 | 审计报告 + **直接修改** `agents.json` / prompts / 契约 | **全新**；它是唯一能改团队定义的角色 |

## 2.3 触发器重设计（去掉不存在的事件流）

**删除**：`on_events: ["change.applied"]` / `["verify.result"]` —— 这两个事件从未产生。

**改为四种真实可验证的触发**：

| 触发类型 | 机制 | 可验证证据 |
|---|---|---|
| **任务板** | `team_task_create` → agent `claim` → `complete` | 任务板历史（`team_task_list` 可见 status/owner）|
| **显式派发** | Lead `spawn_teammate` / `send_message` | `team/dispatch-log.jsonl`（新增）|
| **用户关键词** | 会话中命中 "审视团队" / "验证" / "复核" | 会话历史 |
| **定时** | DSH 宿主 cron（若支持）| 调度日志 |

**若 DSH 宿主不支持 cron** ⇒ Curator 只能靠「用户关键词 + Lead 派发」触发，**必须在契约里写明这个限制**，不要假装有定时。

---

# 第三部分：Agent 模式定义规格（给 DSH 宿主）

## 3.1 需要新增的 agent 模式

```jsonc
{
  "id": "curator",
  "name": "团队策展人",
  "description": "审计并维护多 Agent 团队本身：注册表/prompts/契约/技能。唯一的团队定义写权限持有者。不碰产品代码。",
  "prompt_ref": "docs/guides/curator-agent-prompt.md",

  // 工具集（DSH 侧映射到实际工具名）
  "tools_required": [
    "read", "write", "edit", "glob", "grep", "pwsh",   // 读写 + 跑审计命令
    "team_task_list", "team_task_create", "team_task_get", "team_task_update",  // 读任务板历史（判据必需）
    "spawn_teammate"                                     // 可派临时执行体做采集
  ],

  // 写域：只允许团队资产
  "write_scope": [
    "team/agents.json",
    "team/prompts/**",
    "team/dispatch-log.jsonl",
    "team/curator/**",
    "docs/guides/agent-team-status.md",
    "docs/guides/curator-agent-prompt.md",
    "docs/guides/dsh-agent-teams-contract.md",
    "AGENTS.md",
    "resources/agent-skills/**"
  ],
  "write_forbidden": [
    "src/**", "Package/**", "pyproject.toml", "src/memoria/__version__.py",
    "docs/todo.md",                        // 台账正文只能提议，不能直改
    "<kb>/.memoria/**"                     // 用户知识库
  ],

  // 触发
  "triggers": {
    "on_schedule": "0 3 * * 1",            // 每周一 03:00（若宿主支持；不支持则省略）
    "on_user_keywords": ["审视团队", "团队审计", "curator"],
    "on_explicit_dispatch": true
  }
}
```

## 3.2 关键要求：**它必须能读任务板历史**

`active` 判据之一是「任务板有人认领」。若 Curator 读不到 DSH 任务板，
它只能靠磁盘产物推断，可靠性大打折扣。

**⇒ DSH 宿主需向 Curator 暴露 `team_task_list`（含历史，不仅是 pending）**。
若无法提供 ⇒ 在契约里写明「Curator 只能基于磁盘证据审计，任务板维度不可验证」。

---

# 第四部分：分阶段交付（每阶段可独立验收）

## P1：单一载体（最小可行，~1 小时）

**动作**：
1. `AGENTS.md` §0/§2 加醒目标注：
   ```
   > ⚠️ 本文 §0–§7 描述的是 **Trae/SOLO 载体（历史）**。
   > 当前 DSH 载体的真实机制见 docs/guides/agent-team-status.md。
   > agents.json 中的 builder/verifier/registrar 已在 DSH 下退役。
   ```
2. `agents.json` 三个条目加 `status: "retired-in-dsh"` + `retired_at` + `retired_reason`
3. `docs/guides/agent-team-status.md` 已存在（本次审计产出）

**验收**：`grep -c "retired-in-dsh" team/agents.json` = 3；`AGENTS.md` 顶部有警告块。

## P2：注册表重写为 DSH 真实分工（~2 小时）

**动作**：
1. `agents.json` 的 `agents[]` 重写为：`lead` / `executor` / `auditor` / `registrar` / `curator`
2. 每个角色写清：`trigger_channel`（任务板/显式派发/关键词/定时）、`input_contract`、`output_contract`、`evidence_path`
3. **删除** `event_types` 中的 `change.*` / `verify.result` / `state.drift`（无产生通道），
   或保留但标注 `"note": "DSH 载体下未启用"`

**验收**：每个 non-retired 角色都能指出其 `trigger_channel`，且该通道在 DSH 中真实存在。

## P3：派发日志（让「谁真的在干活」可验证，~1 小时）

**动作**：新建 `team/dispatch-log.jsonl`（append-only），每次 `spawn_teammate` / `send_message` 追加：
```json
{"ts":"...","actor":"lead","target":"executor-15fc7d0c","task":"task-80","phase":"spawn","desc":"mapper 嵌套支持"}
{"ts":"...","actor":"executor-15fc7d0c","task":"task-80","phase":"done","outcome":"pass","report":"..."}
```

**验收**：跑一个任务后，`dispatch-log.jsonl` 有起止两条；能被 `curator` 用于判 `active`。

## P4：Curator 上线（需 DSH 支持，~需宿主改造）

**动作**：
1. 按第 3 节在宿主中注册 `curator` 模式
2. 用 `docs/guides/curator-agent-prompt.md` 作为系统提示词
3. 首次运行产出：`team/curator/audit-<date>/{raw.json,SUMMARY.md}`

**验收**：
- Curator 能独立产出审计报告 AND **实际修改** `agents.json`（不是只报告）
- 报告里每条结论附可复跑命令
- 有「最该改的一件事」结论

## P5：资产清理（~30 分钟，需人类确认）

**动作**：删除 ~600MB 一次性调试产物。

**前置**：先列清单（文件名/体积/最后修改/是否被引用），**人类确认后**才删。

**验收**：`artifacts/agent/` 体积从 750MB 降到 < 150MB，且所有 `.md` 报告保留。

---

# 第五部分：验收总表

| 编号 | 属性 | 检查命令 | 通过标准 |
|---|---|---|---|
| V1 | 单一载体 | `grep -n "retired-in-dsh" team/agents.json` | 3 条；`AGENTS.md` 有警告块 |
| V2 | 触发通道 | 读 `agents.json` 每个角色 | non-retired 角色均有真实存在的 `trigger_channel` |
| V3 | 派发可追溯 | `wc -l team/dispatch-log.jsonl` | > 0，且最近一条 ≤ 7 天 |
| V4 | 产出被消费 | `git log --oneline --all -- <report>` | 每个角色至少一份报告被引用过 |
| V5 | Curator 可自我维护 | 跑一次 curator | 产出 audit raw+summary，且**实际改了**至少一个团队资产 |
| V6 | 资产体积 | `Get-ChildItem artifacts\agent -Recurse -File \| Measure-Object Length -Sum` | < 150 MB |
| V7 | 无空转角色 | Curator 报告 | 无 `status=active` 但 14 天无运行证据的角色 |

---

# 第六部分：给改造者的硬约束

1. **不要删除 `agents.json`/`prompts/`** —— 标记退役，保留历史（有语义参考价值）。
2. **不要假装有事件流** —— `events.jsonl` 要么真的实现落盘，要么在契约里明确「未启用」。
3. **不要给 Curator 产品代码写权限** —— 它的价值在于「独立于产品工作」。
4. **不要让它自审自批** —— Curator 的审计结论必须能被人类复核（附命令）。
5. **不要造没有触发通道的角色** —— 这正是本次要修的病。
6. **删除不可逆资产前必须人类确认**（清单 + 体积 + 引用检查）。
7. **每个阶段的验收必须可复跑** —— 命令写进交付物，不是口头结论。

---

# 附：当前可立即执行的部分（无需 DSH 改造）

若宿主改造暂时排不上，**P1 + P2 + P3 + P5 可以现在就做**（都是仓库内文件，不需要新 agent 模式）：

- P1 标退役 —— 15 分钟
- P2 重写注册表 —— 1 小时
- P3 建派发日志 —— 30 分钟
- P5 清理 600MB —— 30 分钟（需确认）

**只有 P4（Curator 上线）需要 DSH 宿主支持。**

---

# 第七部分：实施状态与偏差（2026-10-23 回填）

> 本部分记录**实际交付**，与上文要求不一致处以本部分为准；验收命令均可直接复跑。

## 7.1 阶段状态

| 阶段 | 状态 | 交付物 / 证据 |
|---|---|---|
| **P1 单一载体** | ✅ 完成 | `AGENTS.md` 顶部「历史载体警告」+ §2 退役标注；`agents.json` 的 `retired_agents[]` 含 3 个 `retired-in-dsh`；旧 prompt 保留 |
| **P2 注册表重写** | ✅ 完成 | `agents.json` schema v2：`agents[]` = lead / executor / auditor / registrar / curator，全部带 `trigger_channel`；旧事件类型移入 `event_stream.legacy_event_types` |
| **P3 派发日志** | ✅ 完成 | `team/dispatch-log.jsonl`（append-only）+ `scripts/agent/dispatch_log.py`（append/check/selftest）；已回填 5 条历史 + 1 条本轮收口记录 |
| **P4 Curator 上线** | ✅ 完成 | DSH `spawn_teammate({mode:"creator"})`（Creator preset `cordis`）；首次审计产物 `team/curator/audit-2026-10-23/{raw.json,SUMMARY.md}`；**实际修改**了 `agents.json` / `AGENTS.md` / 契约 / status |
| **P5 资产清理** | ✅ 完成（人类确认后执行） | 删除 28 个未引用大文件 / **683.48 MB**；保留 `.md` 114 份；删除清单 `team/curator/audit-2026-10-23/cleanup-deleted.json`；体积 **750.2 MB → 66.7 MB**；`team_audit.py` FAIL 1→0（修复误命名为 `.md` 的目录） |

## 7.2 与原文的偏差（重要）

| 原文要求 | 实际落地 | 原因 |
|---|---|---|
| §3.1 在宿主注册 `curator` agent 模式 | 不新增 host agent 模式；Lead 用 `spawn_teammate({mode:"creator"})` 创建 Creator 模式 teammate，人格/写域来自 `curator-agent-prompt.md` + `agents.json` | DSH 的 agent preset 是组合式插件，`cordis` preset 已提供 `plugin_manager` / `tool-cordis` / 创造技能；spawn 模式是更小、可回滚的接入点 |
| §3.1 `on_schedule: "0 3 * * 1"` | **不支持**：DSH 宿主无 cron；Curator 仅「关键词 + 显式派发」触发 | 不假装有定时（契约已写明） |
| §3.1 `write_scope` 只允许团队资产 | **advisory（提示词 + 工具过滤 + 审计）**，DSH 沙箱无子路径白名单 | 沙箱只有 read-only / workspace-write / danger-full-access；删除类操作必须人类确认 |
| P3「每次 spawn/send 自动追加」 | 宿主不会自动写仓库文件；由 **Lead 调 `dispatch_log.py append`** 追加 | 派发日志是团队资产，不是 DSH 内部事件；用脚本降低漏记成本，`check` 作为收口门禁 |
| §3.2「`team_task_list` 含历史」 | 已满足：`team_task_list` 返回 pending/in_progress/completed；`team_task_get` 取单条 | 无需额外改造 |
| V1 期望 `grep -c "retired-in-dsh"` = 3 | ✅ 满足（`retired_agents[]` 中 3 条） | — |

## 7.3 验收总表（实测命令）

| 编号 | 检查命令（PowerShell，工作目录 = 仓库根） | 通过标准 | 实测 |
|---|---|---|---|
| **V1** | `(Select-String -Path team/agents.json -Pattern "retired-in-dsh").Count` + `Select-String -Path AGENTS.md -Pattern "历史载体警告"` | 3 + 有警告块 | ✅ 3 / 1 |
| **V2** | `python scripts/agent/curator_audit.py --json \| python -c "import json,sys; d=json.load(sys.stdin); print(d['registry']['missing_trigger_channel'])"` | `[]` | ✅ `[]` |
| **V3** | `python scripts/agent/dispatch_log.py check` | 退出码 0 且 `count>0`、latest ≤7 天 | ✅ 8 条，latest 2026-10-23（含历史回填 + 本轮收口 + P5；真实派发的 spawn/done 成对记录从下一次派发开始产生） |
| **V4** | `git log --oneline --all -- artifacts/agent/verify/<report>.md` + 报告引用检查 | 每个角色至少一份报告被引用 | ✅ Curator 首次审计已引用报告；其余角色按任务复核 |
| **V5** | 跑 `python scripts/agent/curator_audit.py --date <date>` 并检查实际修改 | 产出 raw+summary 且**实际改**团队资产 | ✅ `audit-2026-10-23/` + `agents.json` v2（首次运行由本会话 Lead 兼 Curator 执行；`spawn_teammate({mode:"creator"})` 路径由 DSH 单测覆盖） |
| **V6** | `Get-ChildItem artifacts/agent -Recurse -File \| Measure-Object Length -Sum` | < 150 MB | ✅ 66.7 MB（789 文件，`.md` 114 份保留） |
| **V7** | 读 Curator SUMMARY `owner_activity` | 无「active 但 14 天无证据」的角色 | ⚠️ 采集器按报告名匹配，`inactive` 项需人工复核（见 SUMMARY §3 口径说明） |

## 7.4 最该改的一件事

**把 dispatch-log 变成 Lead 收口必跑项**：每次 spawn/send/收口后 `append`，收口前 `check`。
否则「谁在干活」仍只能靠 789 个磁盘文件反推。

## 7.5 复跑入口

```powershell
cd D:\AAA_Jupyter\Memoria
$env:PYTHONIOENCODING="utf-8"
python scripts/agent/dispatch_log.py check
python scripts/agent/dispatch_log.py --selftest
python scripts/agent/curator_audit.py --date 2026-10-23
```

详见 [agent-team-status.md](agent-team-status.md) 与
`team/curator/audit-2026-10-23/SUMMARY.md`。
