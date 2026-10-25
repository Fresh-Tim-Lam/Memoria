# 验证报告：teammate 能否使用 schedule 工具（监督角色方案 A 可行性）

> 2026-10-25｜执行：`todo-owner`（task-142）｜**结论：方案 A 不可行（机制层禁止，非"未验证"）**

## 0. 一句话结论

**teammate 的工具表挂载了 schedule 四件套，但任何调用都被 DSH 以会话类型级拒绝**
⇒ 监督角色**不能**用"teammate 自设 schedule 提醒"实现规律自触发；换 preset 也解决不了。
**监督角色主路径改为 B（契约 + repo 侧门禁）+ 过渡方案「Lead 代持定时并主动唤醒 supervisor」。**

## 1. probe 原始结论（Lead 转述 `schedule-probe` 的逐字回报）

```
① 工具表里有没有：有。schedule_list / schedule_create / schedule_delete / schedule_update 四个都在工具集里
② 实际调用 schedule_list 返回：被拒
   错误原文 {"code":"subagent_session","message":"A delegated subagent cannot use reminders."}
   schedule_create 同样被拒；连 schedule_delete 也被拒 ⇒ 未创建任何提醒，无需清理
③ 一句话：teammate【挂载=是、可用=否】
   拒绝是【会话类型级】(subagent_session) 而非「preset 缺工具」
   ⇒ 换 preset 解决不了；开关在 DSH 的 subagent/session 策略层，不在团队插件 preset 层（此条为推断）
```

## 2. 执行链证据（可复核）

| 时间（UTC+8） | 事件 | 证据 |
| --- | --- | --- |
| 19:20:29 | Lead spawn `schedule-probe`（mechanical，一次性探针） | `team/dispatch-log.jsonl` `phase=spawn target=schedule-probe` |
| 19:20:~ | probe 调 `schedule_list` / `schedule_create` / `schedule_delete` | 全部被拒，错误码见上（probe 回报，Lead 转述） |
| 19:21:49 | Lead retire `schedule-probe` | `team/dispatch-log.jsonl` `phase=retire target=schedule-probe` |

**失败原因归类（推断，已标注）**：错误码 `subagent_session` + 文案 "A delegated subagent cannot use reminders." ⇒
DSH 把 teammate 会话归为 subagent 会话，Host 的 reminder 服务对 subagent 会话**主动拒绝**；
这是**策略层**（不在团队插件 v3/v4 的 preset 或工具表里），因此"改 preset / 加工具 / 升级 v4"都不能解决。

## 3. 三条路裁决（Lead 已判）

| 路 | 判定 | 依据 |
| --- | --- | --- |
| A：teammate 规律自触发 | **❌ 不可行（机制层禁止）** | 错误码 `subagent_session`；不是"不稳" |
| B：契约 + repo 侧门禁强制审查 | ✅ **主路径**（保留） | `release_preflight.py` 已落地（待 release 规范修正后扩展检查项） |
| 过渡：Lead 代持定时唤醒 supervisor | ✅ **过渡方案** | Lead 不是 subagent 会话，schedule 可用（Lead 实测四工具在且能调）；到期 Lead `send_message` 给 supervisor（inactive target 会起回合）⇒ supervisor 执行审查 |

## 4. 对设计文档的影响（已同步）

- `team-plugin-vision.md §4`：A 从"待验证"改为 **「已验证不可行（附错误码原文）」**；主路径 = B + Lead 代持定时。
- `team-plugin-vision.md §8`：更新"做不到"表（teammate schedule = ❌ 已证；插件后台定时器 = ❌ 无 API）。
- `team-plugin-roadmap.md`：P2-1 改为"已验证不可行"；新增 P2-0（Lead 代持过渡）；决策 1 结果写进 §0.1。
- `team-plugin-digest.md`：决策 1 结论更新为"B + Lead 代持"。

## 5. task-142 关闭条件对照

| 条件 | 结果 |
| --- | --- |
| 真实 spawn 证据 | ✅ dispatch-log 有 spawn/retire 记录；probe 真实调用被拒（错误码原文） |
| 明确判定 + 对 vision/roadmap 影响 | ✅ A 判不可行；主路径改 B + Lead 代持；文档已更新 |
| 产物 | ✅ 本报告 |
