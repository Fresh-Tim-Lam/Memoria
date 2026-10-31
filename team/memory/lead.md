# 记忆卡：lead

<!-- team-memory-card/v1 · bounded to 8 KiB · omitted 19 older section(s) · truncated: true -->

## lead · 0.4.7-3 skill/plugin 命名统一 + AG21「技能规则面」真机收口（原 0.4.7 ① 命名部分）
<!-- task-id: task-92 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-92「0.4.7-3 skill/plugin 命名统一 + AG21「技能规则面」真机收口（原 0.4.7 ① 命名部分）」：artifacts/agent/verify/todo/0.4.7-task-92-naming.md, src/memoria/ui/static/app/i18n/zh-CN.js, src/memoria/ui/static/app/i18n/en.js, docs/design/agent-capabilities.md, docs/design/agent-plugin-design.md, docs/design/agent-skills.md
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
- 工具 edit 失败：Error: cannot modify "D:\AAA_Jupyter\Memoria\docs\todo.md": file has not been read — read the file, then retry
- 工具 team_task_update 失败：Error: stale team task "task-90" revision 1; current revision is 3
- 工具 team_task_update 失败：Error: only an in-progress task can complete
- 工具 team_task_update 失败：Error: reassigning a completed task requires reason: pass why the owner record is wrong (the correction is written to the dispatch audit log)
- 工具 retire_teammate 失败：Error: retire refused: memory card "team/memory/render-perf.md" has no section for completed task(s) task-19. Complete the tasks through team_task_update so the card is recorded, or retry retire_teammate with force:true and a non-empty reason (the waiver is audited)
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）




## lead · 0.5.0 R1 级重验收：S1–S5 在当前 HEAD（含 0.4.7/0.4.8 改动）重新证明
<!-- task-id: task-139 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-139「0.5.0 R1 级重验收：S1–S5 在当前 HEAD（含 0.4.7/0.4.8 改动）重新证明」：artifacts/agent/verify/todo/0.5.0-acceptance-reverify.md, docs/conventions/version.md, artifacts/agent/verify/todo/0.5.0-doc-sync.md
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
- 工具 edit 失败：Error: cannot edit "D:\AAA_Jupyter\Memoria\docs\conventions\version.md": file changed since it was read — re-read the file, then retry
- 工具 edit 失败：Error: old_string was not found in "D:\AAA_Jupyter\Memoria\docs\conventions\version.md"
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）



## lead · P0-0.4.8 知识图谱调研：知识点类型学 + 关系本体（含方向性）+ 点分布模式（现在只是毛球）
<!-- task-id: task-86 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-86「P0-0.4.8 知识图谱调研：知识点类型学 + 关系本体（含方向性）+ 点分布模式（现在只是毛球）」：artifacts/agent/verify/kg-research-phase1.md, artifacts/agent/verify/kg-research-phase2.md, artifacts/agent/verify/kg-research-phase3.md
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
- 工具 edit 失败：Error: cannot edit "D:\AAA_Jupyter\Memoria\docs\conventions\version.md": file changed since it was read — re-read the file, then retry
- 工具 edit 失败：Error: old_string was not found in "D:\AAA_Jupyter\Memoria\docs\conventions\version.md"
- 工具 team_task_update 失败：Error: only an in-progress task can complete
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）


## lead · 代完成任务 task-140
### 代完成记录
authority: machine
- 代完成任务 task-140「跳转滚动定位三处行为不符：延迟被拉顶部 / 已可见仍滚动 / 固定向下（根因已定位 app.js:15612+15639 block:"start"）」（owner=sync-mapper；主记忆段写入 owner 的卡）

## lead · Release 规范机器化：三条硬规则做成 preflight 机检（标题严格相等 / 双语 EN 在 ZH 前 / 造价含量级），每条配必红 fixture
<!-- task-id: task-143 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-143「Release 规范机器化：三条硬规则做成 preflight 机检（标题严格相等 / 双语 EN 在 ZH 前 / 造价含量级），每条配必红 fixture」：scripts/agent/release_preflight.py, docs/conventions/release-copy.md, docs/conventions/version.md, docs/guides/operations.md, artifacts/agent/verify/todo/release-standard-must-red.md, artifacts/agent/verify/todo/release-standard-audit.md
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
- 工具 edit 失败：Error: cannot edit "D:\AAA_Jupyter\Memoria\docs\conventions\version.md": file changed since it was read — re-read the file, then retry
- 工具 team_task_create 失败：Error: active teammate "release-manager" not found; no journal generation exists for "release-manager" (31 roster rows, none with that name) (durable journal: render-perf:retired, sync-mapper:retired, render-impl:retired, mapper-fix:retired, jump-fix:retired, arch-contract:active, doc-consistency:active, metrics-bas…
- 工具 team_task_update 失败：Error: stale team task "task-140" revision 1; current revision is 2
- 工具 team_task_update 失败：Error: only an in-progress task can complete
- 工具 team_task_update 失败：Error: team task "task-143" is owned by another member
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）
