# 团队真实状态（2026-10-23 审计）

> 用途：记录 Memoria 多 Agent 协作的**实际运行机制**，与 [AGENTS.md](../../AGENTS.md) 的**契约描述**区分开。
> 触发原因：用户要求「审视团队插件现状，看你们到底有没有真的在维护团队，把一些真的没用的下岗」。

---

## 1. 结论先行

**契约描述的三角色事件驱动协作，在当前 DSH 载体下从未运行过。**

| 契约声明 | 实测 | 证据 |
|---|---|---|
| builder / verifier / registrar 三角色 | 注册表有条目，但**从未被触发** | `agents.json` 存在；`events.jsonl` **不存在** |
| 事件驱动派发（`change.applied` → verifier）| **0 次** | `artifacts/agent/events.jsonl` 不存在 |
| `prompt_ref` 指向的角色提示词 | **43 天零改动** | `builder.md` 2026-09-10 15:02；`registrar.md` / `verifier.md` 2026-09-10 15:43 |
| 角色按 `permissions` / `forbidden` 隔离 | **无实际意义**（无执行体）| 三个条目只是 JSON 声明 |

**实际使用的机制**（DSH 载体）：
```
Lead（单点）
  + spawn_teammate / subagent（一次性执行体，同一套工具，换任务书）
  + 共享任务板（team_task_create / claim / complete）
  + send_message（跨 agent 通信）
  + 磁盘报告（artifacts/agent/verify/**、scripts/benchmark/**/results/**）
```

---

## 2. 退役处理（2026-10-23）

`agents.json` 的三个条目**保留但标记退役**（不删除：保留契约历史，避免后来人误以为在运转）。

标记字段：
```json
"status": "retired-in-dsh",
"retired_at": "2026-10-23",
"retired_reason": "DSH 载体下事件驱动派发未启用（events.jsonl 从未落盘）；
                   实际协作由 Lead + spawn_teammate + 任务板代劳。保留仅为历史与语义参考。"
```

**同时**：`AGENTS.md` 的 §0/§2 段落加醒目说明，指向本文件。

---

## 3. 待清理资产（需人类确认）

`artifacts/agent/` 当前 **813 文件 / 750.1 MB**：

| 类别 | 规模 | 处置 |
|---|---|---|
| 一次性调试产物（`heap-*.json.gz`、`p6c-new-diag-*.json`）| ~600 MB（最大单文件 61.4 MB）| **待确认后删除** |
| 有价值报告（`*.md`、`REPORT.md`）| 较小 | 保留 |
| 可复跑脚本（`.mjs`、`.py` 探针）| 较小 | 保留（已入库或可复跑） |

**删除原则**：只删「产出后未被任何提交/文档引用」的**中间产物**，且保留同名 `.md` 报告。

---

## 4. 能力缺口（本次审计发现）

| 缺口 | 依据 | 现状 |
|---|---|---|
| **团队自我维护** | 本次审计需人工翻查 813 文件才发现注册表空转 | **已提出** `curator`（创造模式）agent 提示词：`docs/guides/curator-agent-prompt.md`，**待能改 DSH 宿主的人批准** |

---

## 5. 复跑方式

```powershell
cd D:\AAA_Jupyter\Memoria
$env:PYTHONIOENCODING="utf-8"

# 1) 注册表与事件流
if (Test-Path "artifacts\agent\events.jsonl") { "events.jsonl 已存在" } else { "events.jsonl 不存在 ⇒ 事件派发未启用" }
(Get-Content "artifacts\agent\agents.json" -Raw | ConvertFrom-Json).agents | Select-Object id, status

# 2) 提示词活性
Get-ChildItem "artifacts\agent\prompts" | Select-Object Name, LastWriteTime

# 3) 资产体积
Get-ChildItem "artifacts\agent" -Recurse -File | Measure-Object Length -Sum |
  ForEach-Object { "{0:N1} MB / {1} 文件" -f ($_.Sum/1MB), $_.Count }
```
