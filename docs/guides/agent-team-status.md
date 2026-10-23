# 团队真实状态（2026-10-23 审计 + P1–P4 落地后）

> 用途：记录 Memoria 多 Agent 协作的**实际运行机制**与**已完成改造**，与 [AGENTS.md](../../AGENTS.md) 的
> 「Trae 载体历史契约」区分开。规格来源：[team-plugin-overhaul-spec.md](team-plugin-overhaul-spec.md)。

---

## 1. 结论先行

**契约描述的三角色事件驱动协作在 DSH 载体下从未运行；本轮已把它标为历史，并补齐真实触发通道与派发日志。**

| 契约声明 | 实测（2026-10-23） | 证据 |
|---|---|---|
| builder / verifier / registrar 三角色 | 注册表已标记 `retired-in-dsh`，不再运行 | `agents.json` → `retired_agents[]` |
| 事件驱动派发（`events.jsonl`） | **0 次**（文件不存在），旧事件类型不再产生 | `Test-Path artifacts/agent/events.jsonl` |
| 角色提示词 | 3 份保留为历史，mtime 仍为 2026-09-10 | `agents.json` → `prompt_ref` |
| 实际协作机制 | **Lead + 动态 teammate（领域 Owner）+ 共享任务板 + `send_message` + 磁盘报告** | [agent-team-org.md §2](agent-team-org.md) |
| 派发可追溯 | 已新增 append-only `team/dispatch-log.jsonl`（8 条，含回填与本轮收口） | `python scripts/agent/dispatch_log.py check` |

**执行载体（当前）**：
```
Lead（单点，用户直接对话）
  + spawn_teammate（mode: mechanical/standard/deep/creator）+ send_message + 共享任务板
  + dispatch-log.jsonl（每次派发/收口追加，Lead 职责）
  + 磁盘报告（artifacts/agent/verify/**、领域报告）
  + Curator（creator 模式 teammate，按关键词/显式派发触发）
```

---

## 2. 本轮已落地（对应规格 P1–P5）

| 阶段 | 动作 | 验收证据 |
|---|---|---|
| **P1 单一载体** | `AGENTS.md` 顶部加「历史载体警告」；§2 标注三角色已退役；三份旧 prompt 保留 | `grep -n "历史载体警告" AGENTS.md`；`agents.json` 中 3 个 `retired-in-dsh` |
| **P2 注册表重写** | `agents.json` → schema v2：`agents[]` = lead / executor / auditor / registrar / curator（各带 `trigger_channel` / `input_contract` / `output_contract` / `evidence_path`）；旧三角色进 `retired_agents[]`；旧事件类型进 `event_stream.legacy_event_types` | `python scripts/agent/curator_audit.py --json` → `registry.missing_trigger_channel = []` |
| **P3 派发日志** | `scripts/agent/dispatch_log.py`（append/check/selftest）+ `team/dispatch-log.jsonl` | `python scripts/agent/dispatch_log.py check` 退出码 0；`--selftest` PASS |
| **P4 Curator 上线** | DSH 侧新增 `spawn_teammate({mode:"creator"})`（Creator 模式 preset，工具含 `plugin_manager` / `tool-cordis` / 技能）；本文件与 `curator_audit.py` 即首次运行产物 | `team/curator/audit-2026-10-23/{raw.json,SUMMARY.md}`；`agents.json` 实际被修改 |
| **P5 资产清理** | ✅ 已完成：删除 28 个未引用大文件 / **683.48 MB**（人类确认后执行）；**.md 报告 114 份全部保留** | `team/curator/audit-2026-10-23/cleanup-deleted.json`（删除清单）；`Get-ChildItem artifacts/agent -Recurse -File \| Measure-Object Length -Sum` → 66.7 MB |

> 收口机检：`python scripts/agent/team_audit.py` → **FAIL=0**（修复 `artifacts/agent/verify/` 下误命名为
> `*.md` 的目录后；该目录含 3 个诊断 JSON，已改名为普通目录，数据未删）。

### 2.1 Curator 的唯一写域

Curator = `spawn_teammate({mode:"creator"})` 的 teammate，系统提示词见 [curator-agent-prompt.md](curator-agent-prompt.md)。
它在 DSH 下**没有**路径级硬隔离（DSH 沙箱只支持 read-only / workspace-write / danger-full-access），
`write_scope` 由 `agents.json` + 提示词 + 工具过滤约束；**删除类操作必须人类确认**。

### 2.2 触发通道（真实存在，无 cron）

| 触发 | 机制 | 证据 |
|---|---|---|
| 任务板 | `team_task_create` → `claim` → `complete` | `team_task_list` 历史 + dispatch-log |
| 显式派发 | Lead `spawn_teammate` / `send_message` | dispatch-log |
| 关键词 | 「审视团队」/「验证」/「复核」/「登记」 | 会话历史 |
| 定时 | **DSH 宿主无 cron** ⇒ 不做定时，不得假装有 | — |

---

## 3. 资产清理结果（P5，已完成）

`artifacts/agent/`：**750.2 MB / 816 文件 → 66.7 MB / 789 文件**（`.md` 报告 114 份全部保留）。
删除 28 个「未被任何提交/文档引用」的调试转储（`heap-*.json.gz` 6 个、`p6*-diag/v2/fidelity *.json` 20 个、
`print_prototype/*.json` 2 个），合计 **683.48 MB**，经人类确认后执行。

- 删除清单（含每个文件体积）：`team/curator/audit-2026-10-23/cleanup-deleted.json`
- 清理后审计（体积/引用检查）：`team/curator/audit-2026-10-23/{raw.json,SUMMARY.md}`
- 删除原则：只删「产出后未被任何提交/文档引用」的中间产物；所有 `.md` 报告与可复跑脚本保留。

---

## 4. 重新采集审计（任何人可复跑）

```powershell
cd D:\AAA_Jupyter\Memoria
$env:PYTHONIOENCODING="utf-8"

# 1) 派发可追溯 + 自测
python scripts/agent/dispatch_log.py check
python scripts/agent/dispatch_log.py --selftest

# 2) 团队资产与角色触发通道（只读采集，写 audit-<date>/）
python scripts/agent/curator_audit.py --date 2026-10-23

# 3) 注册表 / 旧事件流 / 体积
(Get-Content "team\agents.json" -Raw | ConvertFrom-Json).agents | Select-Object id, status
if (Test-Path "artifacts\agent\events.jsonl") { "events.jsonl 已存在" } else { "events.jsonl 不存在 ⇒ 旧事件派发未启用" }
Get-ChildItem "artifacts\agent" -Recurse -File | Measure-Object Length -Sum |
  ForEach-Object { "{0:N1} MB / {1} 文件" -f ($_.Sum/1MB), $_.Count }
```

---

## 6. 结构性缺陷：团队"单一事实源"没有版本历史（2026-10-23 Lead 发现）

**事实**：`artifacts/agent/**` 被 `.gitignore:15` 的 `artifacts/` 整个忽略 ⇒
```
git ls-files artifacts/agent/  →  0 个文件
```
⇒ `agents.json`（AGENTS.md §1 声明的"单一事实源"）、`dispatch-log.jsonl`、
`team-board-snapshot.json`、curator 审计产物 **全部无版本历史**。

**后果（已实际发生）**：
1. 2026-10-23 早上 `artifacts/baseline-kb/.../hw-003-frequency-response.md` 被某 agent 覆盖，
   **无 git 历史可恢复**，最终靠 150+ 份运行副本才找回；
2. 同日 Lead 重导出 `team-board-snapshot.json` 时写错成员字段名（`name` vs `target`），
   **覆盖后无法回滚**，只能靠读 `team_audit.py` 源码反推正确格式。

**影响面**：任何 agent 都能静默覆盖团队定义，审计链断裂。这与"团队可信"的核心目标直接冲突。

**✅ 已修（2026-10-23，用户裁决选 B）**：团队资产迁到顶层 `team/`（**入库**）：
```
team/agents.json                    角色注册表（原 artifacts/agent/agents.json）
team/dispatch-log.jsonl             派发日志
team/team-board-snapshot.json       任务板快照
team/prompts/{builder,verifier,registrar}.md
team/curator/audit-2026-10-23/      Curator 审计产物
```
**不搬**：`artifacts/agent/verify/**`（109 份验证报告，是**产物**不是源）仍留在 artifacts/。
迁移脚本 `scripts/agent/migrate_team_assets.py`（`--check` 幂等 / `--apply` 执行），
已同步更新 14 处引用（AGENTS.md / docs/guides/* / 3 个 python 脚本 / tmp.md / 审计产物自身）。
验证：`team/` 未被 gitignore（`git check-ignore team/agents.json` ⇒ exit 1）；
`dispatch_log.py check` / `team_audit.py` / `curator_audit.py` 均绿。

**原候选修法（保留供回溯）**：
| 方案 | 做法 | 代价 |
|---|---|---|
| A | `.gitignore` 加 `!artifacts/agent/` 例外 | 团队资产入库；`artifacts/` 其余仍忽略 |
| B | 团队资产搬到 `docs/agent/` 或 `team/` | 路径变更需同步改脚本/文档 |
| C | 不改路径，加"写入前快照"机制（`.bak` + sha） | 治标，仍无 diff |
| D | 保持现状，靠 dispatch-log + curator 审计留痕 | 仍无历史，仅事后可查 |

**推荐 A**（最小改动、语义清楚：团队资产是"源"不是"产物"）。
