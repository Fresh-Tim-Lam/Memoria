# 记忆卡：steward

<!-- team-memory-card/v1 · bounded to 8 KiB · omitted 5 older section(s) · truncated: true -->

## steward · P1 机检收口（--determinism / write_scope 分级 / mode_policy 显式未决定）+ 第二轮真实审计（SF-014/015/016 已由 d95712e3 批准）
<!-- task-id: task-109 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-100「P0 机检四类：plan_consulted（L8）+ role_registration（org §2.3）+ dead_path_edit（lessons L0.3）+ mode_policy（L9）+ 各自红 fixture」：scripts/agent/team_audit.py, artifacts/agent/verify/steward/task-100/SUMMARY.md
- 完成任务 task-101「work_record.py：任务档案/成员时间线/决策检索/风险清单/doctor 五命令（只读投影，不新增事实源；执行者：steward）」：scripts/agent/work_record.py, artifacts/agent/verify/steward/task-101/SUMMARY.md
- 完成任务 task-102「decide.py + team/decisions.jsonl：决策 e2b04b 追加/提交 trailer 解析/check/selftest（执行者：steward）」：scripts/agent/decide.py, team/decisions.jsonl, scripts/agent/work_record.py, artifacts/agent/verify/steward/task-102/SUMMARY.md
- 完成任务 task-103「P1 机检（decision_trail/model_policy/steward_self_audit）+ findings.jsonl + steward 首轮真实审计（执行者：steward）」：scripts/agent/team_audit.py, team/steward/audit-2026-10-24/SUMMARY.md, team/steward/findings.jsonl, team/steward/audit-2026-10-24/standards_read.json, artifacts/agent/verify/steward/task-103/SUMMARY.md
- 完成任务 task-107「dispatch_log.py 记录 spawn 的 mode / modeExplicit（让 mode_policy 可判定；task-100 遗留）」：scripts/agent/dispatch_log.py, artifacts/agent/verify/steward/task-107/SUMMARY.md, artifacts/agent/verify/steward/task-107/demo-mode-policy.txt, team/steward/findings.jsonl
- 完成任务 task-109「P1 机检收口（--determinism / write_scope 分级 / mode_policy 显式未决定）+ 第二轮真实审计（SF-014/015/016 已由 d95712e3 批准）」：scripts/agent/team_audit.py, team/steward/audit-2026-10-24-r2/SUMMARY.md, team/steward/findings.jsonl, team/steward/audit-2026-10-24-r2/standards_read.json, artifacts/agent/verify/steward/task-109/SUMMARY.md
- 最近结论（原文，未经裁决）：## 交付完成（steward2，4 个任务全部收口）

### 任务总账
| task | 状态 | commit | 交付物 |
|---|---|---|---|
| **task-101** | ✅ completed | `d5dd44fc` | `scripts/agent/work_record.py` 五命令只读投影（task/member/decision/risk/doctor；单任务 ≤8 KB，101 任务实测 max 5047 B；evidence 三态 `exists/gitignored/missing`；selftest 红绿全验） |
| **task-100** | ✅ completed | `b4fc17e1` | P0 四类机检：`plan_consulted`（报出 0.4.7 实施早于计划）/ `role_registration`（三方 9/9/9 + 快照时效）/ `dead_path_edit`（12 个无入口文件；机检 63.6s→15.0s 批量 grep）/ `mode_policy`（14 条 spawn 全缺 mode ⇒ 显式"无法判定"，不静默绿） |
| **task-102** | ✅ completed | `c9765330` | `scripts/agent/decide.py`（append fail-closed 六条+A1/A2、parse-commit 无 trailer 显式 exit 3、check、11 类红 selftest）+ `team/decisions.jsonl`（回填 2 条 reconstructed 决策）+ `work_record.py doctor` 对 decisions **WARN→FAIL** 收紧 |
| **task-103** | ✅ completed | `9d06e7a1` | P1 三类机检（`decision_trail` / `model_policy` / `steward_self_audit`）+ `team/steward/findings.jsonl`（13 条带 disposition）+ 首轮真实审计收据（4 标准 sha256 MATCH、8 步、blind_spots）+ 2 个负例必红自证 |

另：登记 **task-107**（`dispatch_log.py --mode`，unassigned 待 Lead 指派）；交付 `dead-paths-full.txt`（12 文件清单：basename / 最近 commit / 引用数）。

### 当前基线（提交后亲跑）
```
team_audit.py                  FAIL=0  WARN=50  INFO=14   （19 类检查）
work_record.py doctor          PASS（decisions 2 条 OK；仅 trajectory WARN）
decide.py check                PASS（2 条 / bad=0）
decide.py parse-commit 9d06e7a1 status:ok（自身提交带 L10 trailer）
```

### 留给 Lead / 人的 open 项
- **SF-002**：12 个 benchmark 无入口文件 → 等 Lead/人三选一（@entry / 归档 / 删除）
- **SF-003**：task-107（dispatch_log 记 mode）指派后 `mode_policy` 才能从"无法判定"转为可判定
- **SF-004**：37 个历史提交缺 trailer（宽限至 2026-11-07；历史不回改，新提交起带 trailer）
- **SF-009**：task-95（trajectory）未落地 ⇒ 动作层仍是最大审计盲区
- **标准变更提醒**：任何标准文件（AGENTS/rules/lessons/team_audit.py）再…（结论已截断）
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
- 工具 team_task_update 失败：Error: team task "task-100" is owned by another member
- 工具 edit 失败：Error: old_string was not found in "D:\AAA_Jupyter\Memoria\scripts\agent\team_audit.py"
- 工具 edit 失败：Error: cannot modify "D:\AAA_Jupyter\Memoria\scripts\agent\dispatch_log.py": file has not been read — read the file, then retry
- 工具 edit 失败：Error: cannot edit "D:\AAA_Jupyter\Memoria\scripts\agent\team_audit.py": file changed since it was read — re-read the file, then retry
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方「最近结论」时请人工标注被推翻项）
