# 记忆卡：arch-contract

<!-- team-memory-card/v1 · bounded to 8 KiB · omitted 3 older section(s) · truncated: true -->

## arch-contract · 用户态移出安装目录：ui-settings/agent.json 改存 %LOCALAPPDATA%，换包不再丢配置与最近库列表
<!-- task-id: task-160 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-160「用户态移出安装目录：ui-settings/agent.json 改存 %LOCALAPPDATA%，换包不再丢配置与最近库列表」：artifacts/agent/verify/todo/user-state-relocation.md, artifacts/agent/verify/todo/user-state-relocation-swap-sim.py, src/memoria/util/user_state.py, src/memoria/storage/ui_settings.py, src/memoria/services/agent/llm/config.py, tests/test_user_state_relocation.py
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
（本段会话没有记录到失败的调用）
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）





## arch-contract · 修用户态迁移策略：改为按 mtime 较新者胜（升级不丢设置）—— 版本更新机制的前置条件
<!-- task-id: task-179 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-179「修用户态迁移策略：改为按 mtime 较新者胜（升级不丢设置）—— 版本更新机制的前置条件」：artifacts/agent/verify/update-mechanism/migration-mtime-wins.md, artifacts/agent/verify/update-mechanism/migration-tmig6-realmachine.py, src/memoria/util/user_state.py, src/memoria/storage/ui_settings.py, src/memoria/services/agent/llm/config.py, tests/test_user_state_mtime_migration.py
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
（本段会话没有记录到失败的调用）
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）




## arch-contract · 发布包格式保证：release-manifest 完整性清单 + 发布侧硬门禁（不做签名）
<!-- task-id: task-181 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-181「发布包格式保证：release-manifest 完整性清单 + 发布侧硬门禁（不做签名）」：artifacts/agent/verify/release-format/report.md, src/memoria/services/verify/manifest.py, scripts/agent/release_manifest.py, scripts/agent/release_format_gate.py, docs/design/release-format.md, tests/test_release_format.py
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
- 工具 edit 失败：Error: cannot edit "D:\AAA_Jupyter\Memoria\src\memoria\services\verify\manifest.py": file changed since it was read — re-read the file, then retry
- 工具 edit 失败：Error: old_string matched 2 times in "D:\AAA_Jupyter\Memoria\src\memoria\services\verify\manifest.py"; provide a more specific old_string or set replace_all to true
- 工具 edit 失败：Error: old_string was not found in "D:\AAA_Jupyter\Memoria\src\memoria\services\verify\manifest.py"
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）



## arch-contract · 发布包格式保证：release-manifest 完整性清单 + 发布侧硬门禁（不做签名）
<!-- task-id: task-181 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-181「发布包格式保证：release-manifest 完整性清单 + 发布侧硬门禁（不做签名）」：artifacts/agent/verify/release-format/format-gate-wiring.md, scripts/agent/release_preflight.py, artifacts/agent/verify/release-format/report.md, src/memoria/services/verify/manifest.py, scripts/agent/release_format_gate.py, docs/design/release-format.md, tests/test_release_format.py
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
- 工具 team_task_update 失败：Error: only an in-progress task can complete
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）


## arch-contract · 研讨会 Phase 1：图谱/索引驱动 agent 检索 —— 四方独立提案（R1–R8）
<!-- task-id: task-191 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-191「研讨会 Phase 1：图谱/索引驱动 agent 检索 —— 四方独立提案（R1–R8）」：artifacts/agent/verify/debate/kg-retrieval/PROPOSAL-arch-contract.md, artifacts/agent/verify/debate/kg-retrieval/r4_wrongpin_probe.py, artifacts/agent/verify/debate/kg-retrieval/r4-wrongpin-probe.json, artifacts/agent/verify/debate/kg-retrieval/r4_anchor_probe.py, artifacts/agent/verify/debate/kg-retrieval/r3_stale_precision_probe.py
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
（本段会话没有记录到失败的调用）
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）

## arch-contract · 第二次研讨会：逐个问题攻破 —— 当前议题「KP 边界重算的代价」，四人从各自角度同时上
<!-- task-id: task-199 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-199「第二次研讨会：逐个问题攻破 —— 当前议题「KP 边界重算的代价」，四人从各自角度同时上」：artifacts/agent/verify/debate/kg-retrieval/round2/Q1-arch-contract.md, artifacts/agent/verify/debate/kg-retrieval/round2/q1_allkb_probe.py, artifacts/agent/verify/debate/kg-retrieval/round2/q1-allkb.json
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
（本段会话没有记录到失败的调用）
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）
