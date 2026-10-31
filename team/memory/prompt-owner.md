# 记忆卡：prompt-owner

<!-- team-memory-card/v1 · bounded to 8 KiB · omitted 0 older section(s) · truncated: false -->

## prompt-owner · 打包 Agent 提示词与代码行为对齐：resources/agent-prompts/** 审计修复 + 建立 prompt_drift_check.py 机检（人要求设专员长期维护）
<!-- task-id: task-151 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-151「打包 Agent 提示词与代码行为对齐：resources/agent-prompts/** 审计修复 + 建立 prompt_drift_check.py 机检（人要求设专员长期维护）」：artifacts/agent/verify/todo/prompt-drift-audit.md, scripts/agent/prompt_drift_check.py, resources/agent-prompts/kb-spec.zh-CN.md, resources/agent-prompts/kb-agent-readme.md, resources/agent-prompts/kb-agent.zh-CN.md, src/memoria/services/kb_agent.py
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
- 工具 edit 失败：Error: old_string was not found in "D:\AAA_Jupyter\Memoria\scripts\agent\prompt_drift_check.py"
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）



## prompt-owner · prompt_drift_check 接入 team_audit 门禁（Lead 已授权）+ organize.zh-CN.md 纳入维护 + 指纹重签流程
<!-- task-id: task-152 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-152「prompt_drift_check 接入 team_audit 门禁（Lead 已授权）+ organize.zh-CN.md 纳入维护 + 指纹重签流程」：scripts/agent/team_audit.py, scripts/agent/prompt_drift_check.py, resources/agent-prompts/organize.zh-CN.md, artifacts/agent/verify/todo/prompt-drift-audit.md
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
- 工具 edit 失败：Error: cannot modify "D:\AAA_Jupyter\Memoria\scripts\agent\prompt_drift_check.py": file has not been read — read the file, then retry
- 工具 read 失败：Error: offset 1500 is out of range for "D:\AAA_Jupyter\Memoria\scripts\agent\prompt_drift_check.py" (1435 lines)
- 工具 read 失败：Error: offset 300 is out of range for "D:\AAA_Jupyter\Memoria\artifacts\agent\verify\todo\prompt-drift-audit.md" (282 lines)
- 工具 edit 失败：Error: cannot edit "D:\AAA_Jupyter\Memoria\scripts\agent\prompt_drift_check.py": file changed since it was read — re-read the file, then retry
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）


## prompt-owner · 修 prompt_drift 的 5 个静默放行面（PD-1 高：检查未执行只报 WARN ⇒ 门禁仍绿）+ 实现 freeze --refreeze 提案
<!-- task-id: task-158 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-158「修 prompt_drift 的 5 个静默放行面（PD-1 高：检查未执行只报 WARN ⇒ 门禁仍绿）+ 实现 freeze --refreeze 提案」：scripts/agent/prompt_drift_check.py, scripts/agent/freeze_refreeze.py, scripts/agent/team_audit.py, artifacts/agent/verify/todo/prompt-drift-audit.md
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
- 工具 edit 失败：Error: cannot edit "D:\AAA_Jupyter\Memoria\scripts\agent\prompt_drift_check.py": file changed since it was read — re-read the file, then retry
- 工具 edit 失败：Error: ReplaceFileW EIO (Win32 1175): D:\AAA_Jupyter\Memoria\scripts\agent\prompt_drift_check.py
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）

## prompt-owner · GitHub 宣传体系：README 双语重写 + 仓库描述/topics + tag/Release 规范 + 断言—证据表（对标 Obsidian）
<!-- task-id: task-182 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-182「GitHub 宣传体系：README 双语重写 + 仓库描述/topics + tag/Release 规范 + 断言—证据表（对标 Obsidian）」：README.md, README.cn.md, docs/marketing/claims.md, docs/marketing/repo-metadata.md, docs/marketing/tag-release-spec.md, artifacts/agent/verify/marketing/promo-rewrite.md
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
（本段会话没有记录到失败的调用）
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）
