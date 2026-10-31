# 记忆卡：agent-arch

<!-- team-memory-card/v1 · bounded to 8 KiB · omitted 3 older section(s) · truncated: true -->

## agent-arch · 0.5.0-S4 扩展点：工具面投影消费者（gate 复活或移出，R-R1）+ 三字段移出 v1（R-R2）
<!-- task-id: task-123 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-123「0.5.0-S4 扩展点：工具面投影消费者（gate 复活或移出，R-R1）+ 三字段移出 v1（R-R2）」：artifacts/agent/verify/todo/s4-extension-report.md, artifacts/agent/verify/todo/s4-extension-acceptance.md, artifacts/agent/verify/todo/s4_gate_removal_discrimination.py, artifacts/agent/verify/todo/s4_sample_plugin/check.py, artifacts/agent/verify/todo/s4_sample_plugin/README.md, src/memoria/services/agent/plugins.py, src/memoria/services/agent/tools/registry.py, docs/design/agent-plugin-design.md
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
（本段会话没有记录到失败的调用）
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）





## agent-arch · Lead 裁决
### Lead 裁决（下一个人该知道的 3 件事）
authority: lead
- 裁决：S1-S4 全部通过独立验收（section 粒度化 / 写安全 W1-W4 / MCP 薄绑定 / 扩展点）。三次主动自我更正均被采纳并记录：origin 做成 plan 字段导致 fail-open、grep 行首锚点漏了内联写法（真实 15 处全 always）、改签名后只跑子集就报 PASS。
- 未完成：task-132（AMBIGUOUS_SECTION 候选缺 preview ⇒ 消歧实际靠猜，属本轮第 7 个「声明≠事实」形态；section_index.py 已加 preview 但报告未写）与 S5（trace 跨边界：调用级成本字段 + 容量淘汰 + MCP _meta 透传）。
- 模型边界（人要求）：本成员必须运行在 deepseek-flash（V4.1 Flash）。部署 profile 已改为 deepModel/mechanicalModel=deepseek-flash 且 allowProModel=false 并重建 App；team/model-overrides.json 亦钉死。不得以任何方式走 Pro 模型。




## agent-arch · 修 S1 遗留缺陷：AMBIGUOUS_SECTION 候选缺内容预览 ⇒ 消歧实际靠猜
<!-- task-id: task-132 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-132「修 S1 遗留缺陷：AMBIGUOUS_SECTION 候选缺内容预览 ⇒ 消歧实际靠猜」：artifacts/agent/verify/todo/s1b2-disambiguation-preview-report.md, artifacts/agent/verify/todo/s1b2-red-before-fix-tool-layer.txt, artifacts/agent/verify/todo/s1b2-preview-final-run1.json, artifacts/agent/verify/todo/s1b2-pytest-final.txt, src/memoria/services/agent/section_index.py, src/memoria/services/agent/tools/kb.py, src/memoria/services/agent/mcp_server.py, src/memoria/services/agent/plan.py, scripts/benchmark/maintenance/section_disambiguation_preview.py
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
（本段会话没有记录到失败的调用）
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）



## agent-arch · 0.5.0-S5 trace 跨边界：调用级成本字段 + 查询聚合 + 容量淘汰 + MCP _meta 透传
<!-- task-id: task-124 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-124「0.5.0-S5 trace 跨边界：调用级成本字段 + 查询聚合 + 容量淘汰 + MCP _meta 透传」：artifacts/agent/verify/todo/s5-trace-report.md, artifacts/agent/verify/todo/s5-pytest-final.txt, src/memoria/services/agent/trace_index.py, src/memoria/services/agent/audit.py, src/memoria/services/agent/tools/kb.py, src/memoria/services/agent/loop.py, src/memoria/services/agent/mcp_server.py, docs/design/dsh-agent-port.md, scripts/benchmark/maintenance/trace_cost_s5.py
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
- 工具 glob 失败：Error: glob search failed (exit 2): rg: tests/agent: IO error for operation on tests/agent: 系统找不到指定的文件。 (os error 2)
- 工具 read 失败：Error: cannot read "D:\AAA_Jupyter\Memoria\artifacts\agent\verify\todo\s1b-4-red-before-fix.txt": binary file
- 工具 team_task_update 失败：Error: team task "task-132" is owned by another member
- 工具 edit 失败：Error: old_string matched 2 times in "D:\AAA_Jupyter\Memoria\src\memoria\services\agent\tools\kb.py"; provide a more specific old_string or set replace_all to true
- 工具 team_task_update 失败：Error: task mutation requires its owner or Team Lead
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）


## agent-arch · 修控制台弹窗闪烁：7 处子进程启动全缺 CREATE_NO_WINDOW（agent 每次跑 pwsh 都闪一下）
<!-- task-id: task-159 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-159「修控制台弹窗闪烁：7 处子进程启动全缺 CREATE_NO_WINDOW（agent 每次跑 pwsh 都闪一下）」：artifacts/agent/verify/todo/console-flash-fix.md, artifacts/agent/verify/todo/console-flash-fix/experiment.json, artifacts/agent/verify/todo/console-flash-fix/pe_subsystem.py, artifacts/agent/verify/todo/console-flash-fix/run_flash_experiment.py, artifacts/agent/verify/todo/console-flash-fix/pytest.txt, src/memoria/util/proc.py, tests/test_console_no_window.py, src/memoria/services/agent/shell_exec.py
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
- 工具 edit 失败：Error: cannot modify "D:\AAA_Jupyter\Memoria\src\memoria\services\agent\tools\kb.py": file has not been read — read the file, then retry
- 工具 edit 失败：Error: cannot modify "D:\AAA_Jupyter\Memoria\src\memoria\app\runtime.py": file has not been read — read the file, then retry
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）

## agent-arch · 研讨会 Phase 1（C 方·agent 检索/token 经济）：检索路径、工具结果预算、省轮次论证
<!-- task-id: task-195 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-195「研讨会 Phase 1（C 方·agent 检索/token 经济）：检索路径、工具结果预算、省轮次论证」：artifacts/agent/verify/debate/kg-retrieval/PROPOSAL-agent-arch.md, artifacts/agent/verify/debate/kg-retrieval/scripts/session-analysis.json, artifacts/agent/verify/debate/kg-retrieval/scripts/kb-granularity.json, artifacts/agent/verify/debate/kg-retrieval/scripts/analyze_session.py, artifacts/agent/verify/debate/kg-retrieval/scripts/kb_granularity.py
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
（本段会话没有记录到失败的调用）
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）
