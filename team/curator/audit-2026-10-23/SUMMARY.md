# Curator 审计摘要（2026-10-23）

> 采集时间：2026-10-23T21:40:42+08:00；采集器：`scripts/agent/curator_audit.py`（只读）。
> 每条结论附复跑命令；删除建议**未执行**，需人类确认（P5）。

## 1. 结论先行

- **派发可追溯**：dispatch-log 12 条，最新 2026-10-23T21:27:36+08:00，check=True。
- **团队资产体积**：66.7 MB / 789 文件；未引用大文件候选 0.0 MB。
- **旧事件流**：events.jsonl exists=False ⇒ Trae 触发器 0 次。

## 2. 证据与判定

| # | 结论 | 证据 |
|---|---|---|
| F1 | Trae 事件流（events.jsonl）不存在 ⇒ 旧 on_events 触发器 0 次；DSH 下仅 dispatch-log 生效 | Test-Path artifacts/agent/events.jsonl = False; dispatch-log count=12, ok=True |
| F2 | 历史角色提示词 3/3 份超过 30 天未改动 ⇒ 判 inactive（保留历史） | team/prompts/builder.md age=43.3d; team/prompts/registrar.md age=43.2d; team/prompts/verifier.md age=43.2d |
| F3 | 非退役角色全部具备真实触发通道 | agents.json agents[].trigger_channel.mechanism 逐项检查 |
| F4 | 存在 14 天内无磁盘产出证据的 Owner | inactive owners = ['arch-contract', 'doc-consistency', 'metrics-baseline', 'kp-owner', 'settings-owner', 'team-steward', 'surface-new', 'todo-owner', 'team-curator']（窗口 14 天，依据 verify 报告 mtime） |
| F5 | artifacts/agent 体积 66.7 MB；未引用的大文件可清理 0.0 MB（需人类确认） | 789 files; cleanup candidates=0; post-cleanup≈66.7 MB |

## 3. 运行时 Owner 活性（14 天窗口，磁盘证据）

> 判据口径：仅以 `artifacts/agent/verify/**` 中**文件名含 owner 名**的报告 mtime 为据；
> 不含提交/任务板/领域内其他报告 ⇒ 判 `inactive` 只能作为**待复核线索**，不能直接当结论。

| Owner | 匹配报告数 | 最新报告 | 天数 | 判定 |
|---|---|---|---|---|
| `render-perf` | 2 | 2026-10-19T21:25:06+08:00 | 4.0 | active |
| `sync-mapper` | 1 | 2026-10-18T23:50:08+08:00 | 4.9 | active |
| `arch-contract` | 0 | — | — | inactive |
| `doc-consistency` | 0 | — | — | inactive |
| `metrics-baseline` | 0 | — | — | inactive |
| `kp-owner` | 0 | — | — | inactive |
| `settings-owner` | 0 | — | — | inactive |
| `team-steward` | 0 | — | — | inactive |
| `surface-new` | 0 | — | — | inactive |
| `todo-owner` | 0 | — | — | inactive |
| `team-curator` | 0 | — | — | inactive |

## 4. 清理候选（P5，待人类确认，**未删除**）

候选合计 **0.0 MB**；清理后预计 **66.7 MB**。

| 文件 | MB | 最后修改 | 精确文件名被引用 | 同族前缀被引用（需人工判断） |
|---|---|---|---|---|

## 5. 最该改的一件事

**把 dispatch-log 变成 Lead 收口必跑项**：每次 spawn/send/收口后立刻 `python scripts/agent/dispatch_log.py append ...`，
收口前跑 `python scripts/agent/dispatch_log.py check`。否则「谁在干活」仍只能靠 813 个磁盘文件反推。

## 6. 复跑命令

```powershell
$env:PYTHONIOENCODING='utf-8'
python scripts/agent/dispatch_log.py check
python scripts/agent/dispatch_log.py --selftest
python scripts/agent/curator_audit.py --json
powershell -Command "(Get-Content team/agents.json -Raw | ConvertFrom-Json).agents | Select-Object id,status"
powershell -Command "Get-ChildItem artifacts/agent -Recurse -File | Measure-Object Length -Sum"
git status --short docs/guides artifacts/agent
```
