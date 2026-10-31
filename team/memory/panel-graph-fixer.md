# 记忆卡：panel-graph-fixer

<!-- team-memory-card/v1 · bounded to 8 KiB · omitted 8 older section(s) · truncated: true -->

## panel-graph-fixer · Lead 裁决
### Lead 裁决（下一个人该知道的 3 件事）
authority: lead
- 引擎/连线重叠这条线由你独占负责：已完成 org 树干单一绘制源（O1/O2 DOM 独立验证通过）、CP1 走廊规划器、CP1.1 端口方位三腿分配；未完成三腿 A* 走不通（assembled 3/6、hub 1/15 显式 corridor-full）与画出的边仍带折返。
- 纪律：flag teamCorridorRouting 默认 OFF、不重建 bundle 抢冻结、每小步 commit、改文件前先 read、不许改断言或放宽容差；失败必须显式（unrouted），不许拼接成假路径。
- 交接：artifacts/agent/panel-ui/cp11-handoff.md 含当前 HEAD、三腿规则、二分思路与复现命令；后续由 Lead 新招的接手者继续，不再由你推进。


## panel-graph-fixer · 引擎能力检测：HUB（一个 agent 连 12 个同事 / 15 条边）—— 边不丢、胶囊压线、不压卡、不穿卡、扇出可读
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-232「图区必须画对：Fit 生效（zoom≤100%，全节点在视口）+ 监督者顶部独立泳道 + 胶囊 100% 在线上（四个硬指标）」：artifacts/agent/panel-ui/browser-check/fixer-232.png, artifacts/agent/panel-ui/browser-check/fixer-232-metrics.json, packages/experimental/client-ui-agent-team/src/client/panel/pipeGeometry.ts, packages/experimental/client-ui-agent-team/src/client/panel/PipeMap.tsx, packages/experimental/client-ui-agent-team/tests/pipe-geometry.client.spec.ts
- 完成任务 task-234「图引擎阶段 1：纯函数引擎（layout/camera/capsules/diff/step）+ 六条 headless 断言（不接组件）」：packages/experimental/client-ui-agent-team/src/client/panel/engine/layout.ts, packages/experimental/client-ui-agent-team/src/client/panel/engine/capsules.ts, packages/experimental/client-ui-agent-team/tests/engine/acceptance.client.spec.ts, artifacts/agent/plugin/verify/engine-A1-A6.json, artifacts/agent/plugin/verify/engine-redproof/SUMMARY.md, tools/engine-redproof.mjs
- 完成任务 task-236「MVP-2：把拼装出的 Memoria 同构团队在成员页正确显示（25 成员 / 5 组 / 四指标全绿 / 未分组标注）」：artifacts/agent/panel-ui/browser-check/236-tier-a.png, artifacts/agent/panel-ui/browser-check/236-tier-a.json, artifacts/agent/panel-ui/browser-check/236-tier-b.png, artifacts/agent/panel-ui/browser-check/236-tier-b.json, packages/experimental/client-ui-agent-team/src/client/dev/assembledSnapshot.ts, packages/experimental/client-ui-agent-team/src/client/panel/pipeGeometry.ts, tools/cdp-measure-assembled.mjs
- 完成任务 task-237「引擎能力检测：HUB（一个 agent 连 12 个同事 / 15 条边）—— 边不丢、胶囊压线、不压卡、不穿卡、扇出可读」：artifacts/agent/panel-ui/browser-check/hub-237.png, artifacts/agent/panel-ui/browser-check/hub-237-metrics.json, artifacts/agent/panel-ui/browser-check/crossing-237.png, artifacts/agent/panel-ui/browser-check/crossing-237.json, packages/experimental/client-ui-agent-team/src/client/panel/pipeGeometry.ts, tools/cdp-measure-hub.mjs
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
- 工具 edit 失败：Error: cannot edit "D:\deepseek-harness\packages\experimental\client-ui-agent-team\src\client\panel\PipeMap.tsx": file changed since it was read — re-read the file, then retry
- 工具 write 失败：Error: cannot write "D:\deepseek-harness\packages\experimental\client-ui-agent-team\src\client\panel\PipeMap.tsx": file changed since it was read — re-read the file, then retry
- 工具 edit 失败：Error: cannot edit "D:\deepseek-harness\packages\experimental\client-ui-agent-team\tests\panel.client.spec.tsx": file changed since it was read — re-read the file, then retry
- 工具 edit 失败：Error: cannot modify "D:\deepseek-harness\packages\experimental\client-ui-agent-team\tests\pipe-geometry.client.spec.ts": file has not been read — read the file, then retry
- 工具 ask_user_question 失败：Error: human interaction is unavailable while the calling agent is owned by another live agent; include the unresolved question or decision in the child agent's final result
### 我留下的坑 / 下一个人该从哪开始
authority: machine
- 未完成任务 task-242「关系总览：26 个 agent 同屏 + 组织结构边（lead→组长→组员 / lead→未分组，25 条）+ 与管道边视觉可区分」（in_progress）
- 未完成任务 task-243「几何收口：路由从卡片边缘出发（穿卡归零）+ 组带空白收紧 + 虚线距卡 ≥6px（并重跑 A1–A6 与 242 六条）」（pending）
- 未完成任务 task-247「折叠态必须有"组节点"并正确重定向组内外连线（含聚合胶囊）+ 每框多端口动态分布（≥8px 间距、边端点必在端口上）」（in_progress）
- 未完成任务 task-249「引擎设计·连线重叠（独占责任）：共线重叠 max=0 + 8px 间距 + 交叉角 15° + 正交/折弯/stub/胶囊全达标（含根因与不变量论证）」（in_progress）
- 未完成任务 task-252「底部细节栏整合：单一实现，悬浮=preview（离开即消失）、点击=pinned（持久）、点空白/Esc/切页签即消失」（pending）
- 未完成任务 task-257「路由性能 L1：网格分桶 + routeCache + 增量路由（30 边首次 p95 <200ms、增量 <30ms、命中 <5ms）」（pending）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）

## panel-graph-fixer · 退役豁免（Lead）
### 退役豁免（Lead）
authority: lead
- 豁免项：force: task-232, task-234, task-236, task-237
- 理由：上下文耗尽且 CP1.1 未收口；已完成工作均已在 commit（b3834e181a、cf9a2c7c41）与交接文件 artifacts/agent/panel-ui/cp11-handoff.md 中固化，历史任务 task-232/234/236/237 的记忆卡章节缺失属登记历史遗留，不影响 code/evidence 追溯；经 Lead 裁决以 force 退役，引擎/重叠线转交新成员 panel-router-dev。
