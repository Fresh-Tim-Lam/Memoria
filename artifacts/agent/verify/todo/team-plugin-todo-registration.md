# task-148 报告：团队插件完善项进 todo.md + P1-8 研讨会编排登记

> 2026-10-25｜执行 `todo-owner`｜写域：`docs/todo.md`、`docs/design/team-plugin-roadmap.md`、`docs/design/ledger-archive-2026.md`、本报告。
> 纪律：**不 commit**；未改 `src/**`；先实测余量再规划。

## 0. 一句话结果

团队插件 P0–P4（含新增 **P1-8 研讨会/辩论编排**）已登记进 `docs/todo.md §17`（可 grep：`team-plugin` / `团队插件` / `Agent Teams` / `P1-8` / `team_debate`），roadmap 同步回写；
因余量仅 **183 B（实测）**，先归档 §14.6–§14.7（**实测 4,019 B**）到 ledger §10.11，再写 §17。
**最终实测 64,976 B / 524 行（余量 560 B），`check_todo_size.py` PASS；`team_audit.py` FAIL=0。**

## 1. 实测体积（先测后规划）

| 阶段 | 实测 |
| --- | --- |
| 改动前 | `65,353 B / 538 行`（余量 **183 B**） |
| 归档 §14.6 未测项 + §14.7 实际完成/偏离 | **4,019 B** → `ledger-archive-2026.md §10.11`（原文逐字） |
| 新增 §17（P0–P4 + P1-8 索引表 + 证据段） | 约 3.7 KB（初稿超 2 个单元格 200B，已缩短并移细节到表后段落） |
| 改动后 | **`64,976 B / 524 行`（余量 560 B）**，PASS |

## 2. 改动清单（file:line:what）

| # | 位置 | 改动 |
| --- | --- | --- |
| 1 | `docs/todo.md:504` | 新增 **§17 团队插件完善项（team-plugin / Agent Teams；2026-10-25 登记）**：引言（L8 依据/范围/状态）+ P0/P1/P1-8/P2/P3/P4 六行索引表 + P2 细节 + P1-8 实证 + L10 说明 + 不做什么 |
| 2 | `docs/todo.md:511-516` | P0–P4 各行（roadmap 指针、状态、验收）；**P1-8 行**（`team_debate`：Phase1–5 状态机 + 独立性/0 自创/ rulings/falsifier/ev 要求） |
| 3 | `docs/todo.md:520` | **P1-8 实证**：4 `spawn_teammate` + 8 `send_message` + 4 `wait_agent` + 2 份 Lead 文书 + **13 条裁决** + 四提案自推翻；L10 证据→建议 |
| 4 | `docs/todo.md:449-455` | §14.6/§14.7 改为**指针**（原文逐字在 ledger §10.11） |
| 5 | `docs/design/ledger-archive-2026.md:249` | 新增 **§10.11**：原 §14.6–§14.7 原文（48 行，逐字） |
| 6 | `docs/design/team-plugin-roadmap.md:65` | P1-7 后新增 **P1-8 研讨会/辩论编排** 行（阶段状态机 + 验收=本轮 fixture 重放得等价裁决 + 实证） |

**未改动**：`docs/design/team-plugin-vision.md`、`src/**`、其它 §13/§14/§15/§16 内容（除 §14.6/7 指针化）。

## 3. 关闭条件对照

| 条件 | 结果 |
| --- | --- |
| 1. P0–P4 各有条目 + 指针（可 grep） | ✅ §17 六行；grep 命中：`team-plugin` 5 / `团队插件` 4 / `Agent Teams` 3 / `P1-8` 4 / `team_debate` 2 |
| 2. 新增 P1-8，带本轮 14 次调用/13 条裁决实证 | ✅ §17 行 + 「P1-8 实证」段（含 L10 证据→建议） |
| 3. `check_todo_size.py` PASS | ✅ **实测** 64,976 B / 524 行，余量 560 B |
| 4. roadmap 回写 P1-8 + P2-1/P2-4 状态 | ✅ P1-8 已加（L65）；P2-1 **❌ 已验证不可行**（错误码 `subagent_session`）与 P2-4 **✅ 已落地** `release_preflight.py` 已在 roadmap/§17 双处标明 |
| 5. `team_audit.py` FAIL=0 | ✅ FAIL=0（WARN 54 / INFO 24，均既有历史项） |
| 6. 产物 | ✅ 本报告 |

## 4. 关键内容摘录（便于 Lead 复核）

**P2-1（不美化）**：teammate 工具表挂载 schedule 四件套=**是**；调用=**全部被拒**；错误码
`{"code":"subagent_session","message":"A delegated subagent cannot use reminders."}`；
`schedule_create`/`schedule_delete` 同样被拒 ⇒ **会话类型级禁止，换 preset/升级 v4 均无效**；
监督角色过渡 = **P2-0 Lead 代持定时唤醒**。

**P1-8 fixture（L10）**：本轮 KG 辩论 = 4 次 spawn + 8 次 send_message + 4 次 wait_agent + 2 份 Lead 文书 + 手工阶段状态；产出 13 条裁决、推翻 task-86 D1、四提案全部自推翻 ⇒ 流程重复/易漏/不可机检 ⇒ 建议做成 `team_debate` 插件工具（非文档规范）。

**P4-5 纪律项单列**：对外分发前必须内部跑满 2 个版本（§17 P4 行已单列）。

## 5. 校验与复跑

```powershell
python scripts/check_todo_size.py
$env:PYTHONIOENCODING='utf-8'; python scripts/agent/team_audit.py | Select-String 'FAIL='
git diff --numstat -- docs/todo.md docs/design/ledger-archive-2026.md docs/design/team-plugin-roadmap.md
Select-String -Path docs/todo.md -Pattern 'team-plugin|团队插件|Agent Teams|P1-8|team_debate'
Select-String -Path docs/design/team-plugin-roadmap.md -Pattern 'P1-8'
Select-String -Path docs/design/ledger-archive-2026.md -Pattern '^### 10\.11|^### 14\.6|^### 14\.7'
```

`git diff --numstat`：todo **+25/−39**、ledger **+48/−0**、roadmap **+1/−0**。

## 6. 未测项 / 风险

1. 余量仅 **560 B**：下次台账更新（如 P1-8 落地登记）必须先实测，不足继续按 §10.x 归档。
2. §14.6/§14.7 现为指针，原文在 ledger §10.11（已在 §14 内注明）。
3. roadmap 的 P1-8 验收依赖"本轮 fixture 重放"，**重放工具尚未实现**（属 P1-8 实现阶段）。
4. 未验证 `docs/design/team-plugin-vision.md` 与 roadmap 是否有新矛盾（本轮未发现；按写域只读 vision）。
