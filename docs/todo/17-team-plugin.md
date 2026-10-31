# 17. 团队插件完善项（team-plugin / Agent Teams；2026-10-25 登记，todo-owner） — 活跃详情（原文逐字）

> **本文件是 `docs/todo.md §17` 的活跃详情**（2026-10-26 索引化搬迁，**原文逐字**，未改写）。
> **状态事实源 = `docs/todo.md` 索引行**；本文件只放详情。历史归档仍在 `docs/design/**`，不在此重复。

<a id="p0"></a><a id="p1"></a><a id="p2"></a><a id="p3"></a><a id="p4"></a>

## 原文（逐字，自 docs/todo.md 搬迁）

## 17. 团队插件完善项（team-plugin / Agent Teams；2026-10-25 登记，todo-owner）

> **依据（L8）**：计划正文在 [design/team-plugin-roadmap.md](design/team-plugin-roadmap.md)（P0–P4 逐条验收）+ [vision](design/team-plugin-vision.md)；本表只做**索引与状态**，不复制正文。
> **范围**：团队插件（DSH Agent Teams）自身能力完善，**不占产品版本**（0.4.8/0.4.9/0.5.0 节奏不变）。**状态**：P0 ⏳（前置=DSH 重建，需人时间窗）｜P1 ⏳（含 P1-8）｜P2 部分（P2-4 ✅ / P2-1 ❌）｜P3 ⏳｜P4 ⏳（digest 先行）。

| 阶段 | 条目（可 grep：team-plugin / 团队插件 / Agent Teams / P0–P4 / P1-8） | 状态 | 指针/验收 |
| --- | --- | --- | --- |
| P0 | 版本对齐与契约升级（v3→v4；「声明>插件」改拒绝，默认开关 off） | ⏳ 待做 | roadmap P0-1..P0-5；`contractNotice status=ahead` |
| P1 | 义务强制化：mode 必填拒绝 / complete 证据增强 / claim 写域冲突拒绝 / team_decide / 声明≠事实证据契约 / digest 骨架 / 用户文档校验 | ⏳ 待做 | roadmap P1-1..P1-7 |
| **P1-8** | **研讨会/辩论编排（`team_debate`）** | ⏳ 待做（本轮手工 fixture 已证重复、易漏） | 见下方「P1-8 实证」；fixture=本轮 KG 辩论四阶段产物 |
| P2 | 监督角色（P2-0..P2-6；**P2-1 ❌ 已验证不可行**；**P2-4 ✅ 已落地**） | 🔄 部分 | 见下方「P2 细节」；`scripts/agent/release_preflight.py` |
| P3 | 场景 profile（角色/触发/审查/写域/交付物/文档模板）+ 3 场景试点 | ⏳ 待做 | roadmap P3-1..P3-4 |
| P4 | 产品化：用户可读 digest 先行 → Memoria 学习/复习场景 → AOCI/Xerj → 独立 DSH 插件包 | ⏳ 待做 | roadmap P4-1..P4-5；**P4-5 纪律项单列**：对外分发前必须内部跑满 2 个版本；vision §9（digest 5 分钟三问） |

**P2 细节（不美化）**：P2-0 = Lead 代持定时唤醒（`schedule_create` → resume Lead → `send_message` 唤醒 supervisor）；**P2-1 ❌ 已验证不可行**（四工具挂载=是、调用=拒；`subagent_session`；换 preset/升级 v4 无效）；P2-2 模板 / P2-3 schema / P2-4 ✅ `release_preflight.py` / P2-5 wrapper 原型 / P2-6 S1–S6。

**P1-8 实证（本轮 KG 辩论，2026-10-25）**：Lead 手工编排 = 4 `spawn_teammate` + 8 `send_message` + 4 `wait_agent` + 2 份 Lead 文书 + 阶段状态手工维护；产出 **13 条裁决**、推翻 task-86 D1、四提案全部自推翻 ⇒ 重复/易漏/不可机检。
**L10 说明（证据→建议）**：本条不是凭感觉加项——fixture 完整（14 次工具调用 + 13 条裁决可复核）；建议做成插件工具（`team_debate`）而不是再写文档规范。
**P2-1 事实（不美化）**：teammate 工具表挂载 schedule 四件套=**是**，调用=**全部被拒**；`schedule_create`/`schedule_delete` 同样被拒；**会话类型级禁止，换 preset/升级 v4 均无效** ⇒ 监督角色只能走 P2-0（Lead 代持）+ B（契约门禁）。
**不做什么**：不把团队插件塞进 0.4.8/0.4.9/0.5.0；不因本项改产品发布节奏；不恢复「teammate 自触发」（已证不可行）。

***
