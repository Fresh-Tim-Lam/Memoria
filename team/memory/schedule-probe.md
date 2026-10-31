# 记忆卡：schedule-probe

<!-- team-memory-card/v1 · bounded to 8 KiB · omitted 0 older section(s) · truncated: false -->

## schedule-probe · Lead 裁决
### Lead 裁决（下一个人该知道的 3 件事）
authority: lead
- 探针结论（决定性，已记入 team-plugin 设计）：teammate 的 schedule 四个工具【挂载=是、可用=否】。运行时一律被拒，错误原文 {"code":"subagent_session","message":"A delegated subagent cannot use reminders."}，连 schedule_delete 也被拦 ⇒ 未创建任何提醒、无需清理。
- 关键判读：拒绝是【会话类型级】（subagent_session）而非「preset 缺工具」⇒ 换 preset 解决不了；开关在 DSH 的 subagent/session 策略层，不在团队插件 preset 层（此条为推断，非验证结论）。
- 对设计的影响：方案 A（teammate 规律自触发）【不可行】。监督角色只能走 B（契约+repo 侧门禁强制审查），或由 Lead 侧代持定时并主动唤醒 supervisor（Lead 非 subagent 会话，schedule 可用）。

## schedule-probe · 一次性探针：验证 teammate 的 preset 是否挂载 schedule 工具（用完即退休）
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
（没有需要补录的已完成任务；各任务证据见其完成段落）
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
（本段会话没有记录到失败的调用）
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）
