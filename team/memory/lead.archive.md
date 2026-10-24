
<!-- archived team-memory-card section -->
## lead · 设计「成员工作记录机制」（动作/任务/决策三层）+ 定清团队管理员职责边界（人：可能就是一份工作）
<!-- task-id: task-97 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-62「【已关闭·已过期】task-62 P6 收口重跑（0.4.4 已发布、收口门已过；两个真实测量工具缺陷已拆到 task-81）」：（未绑定产物）
- 完成任务 task-65「迁移：预览物化/排版接入 MemoriaScheduler（P1/P2 作业）」：（未绑定产物）
- 完成任务 task-66「调度内核：补帧预算/公平份额（burst 累加器 + 长任务切片）」：（未绑定产物）
- 完成任务 task-67「v0.4.6 P0：工作集淘汰（DOM 回收 + 回滚复用）」：（未绑定产物）
- 完成任务 task-69「【todo-owner 认领·P1·顺序2】冷启动慢（13–23s 才自动打开首个文件；先补 boot 打点）」：src/memoria/services/lexical_index.py, scripts/benchmark/surface/run_boot_profile.py, src/memoria/ui/static/app/js/app.js
- 完成任务 task-76「✅ task-76 结论修正：evict 长批非块数问题（批尾布局 58.7%）；顺带修 purge 静默 no-op」：（未绑定产物）
- 完成任务 task-77「✅ task-70 堆泄漏已修复（MathJax MathItem 持有 detached 子树，−75.3%）」：（未绑定产物）
- 完成任务 task-80「P0：mapper.domToAst 支持嵌套列表 —— 修复 listItemIndex 错位（Tab 升降级的前置阻塞）」：（未绑定产物）
- 完成任务 task-83「P1 task-79 阶段5：粘贴替换跨块选区（新交互语义，进 0.4.7）」：src/memoria/ui/static/app/js/app.js, artifacts/agent/verify/selection-matrix-after-stage5.md
- 完成任务 task-84「P1 task-69：validate_kb + loadGraphData 移出 bootAutoOpen 关键路径（P0-b 已被 P0-a 覆盖，收益 43ms→1.9s）」：src/memoria/ui/static/app/js/app.js, src/memoria/ui/static/app/js/kb-check.js
- 最近结论（原文，未经裁决）：`team_preflight` **在源码里已注册**（`index.ts:618`），但**我的工具清单里没有它**。实测一下我到底能不能调：
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
- 工具 pwsh 失败：Error: SetNamedSecurityInfoW failed (Win32 5): grantWrite(D:\AAA_Jupyter\Memoria)
- 工具 web_fetch 失败：Error: web fetch failed: TypeError: fetch failed
- 工具 read 失败：Error: offset 1845 is out of range for "D:\AAA_Jupyter\Memoria\src\memoria\ui\static\app\i18n\zh-CN.js" (1838 lines)
- 工具 read 失败：Error: offset 1970 is out of range for "D:\AAA_Jupyter\Memoria\src\memoria\ui\static\app\i18n\en.js" (1944 lines)
- 工具 edit 失败：Error: cannot edit "D:\AAA_Jupyter\Memoria\docs\conventions\docs-management.md": file changed since it was read — re-read the file, then retry
### 我留下的坑 / 下一个人该从哪开始
authority: machine
- 未完成任务 task-86「P0-0.4.8 知识图谱调研：知识点类型学 + 关系本体（含方向性）+ 点分布模式（现在只是毛球）」（pending）
- 未完成任务 task-91「0.4.7-2 显示 agent 上下文占用 + 上下文压缩可观测（原 0.4.7 ① 可观测部分）」（pending）
- 未完成任务 task-92「0.4.7-3 skill/plugin 命名统一 + AG21「技能规则面」真机收口（原 0.4.7 ① 命名部分）」（pending）
- 未完成任务 task-93「0.4.7-4 排版响应式：dock 展开时收缩文件树 / 折叠+分屏时切预览（原 0.4.7 ②）」（pending）
- 未完成任务 task-96「带教（mentor）：过程与行为审计 —— 重读标准不靠记忆，产出是「新机检」不是报告」（pending）
- 未完成任务 task-98「steward 注册同步：org.md §2.2 行 + steward 章程 + agents.json 字段统一 + 快照重导出（修当前 team_audit FAIL=1）」（pending）
- 未完成任务 task-99「决策记录协议条款：AGENTS.md §0.5 新增 L9 + lead-dispatch-rules §6 + org.md §2.1 纪律 6（先条款后机检）」（pending）
- 未完成任务 task-100「P0 机检三类：plan_consulted（L8）+ role_registration（org §2.3）+ dead_path_edit（lessons L0.3）+ 各自红 fixture（执行者：steward）」（pending）
- 未完成任务 task-101「work_record.py：任务档案/成员时间线/决策检索/风险清单/doctor 五命令（只读投影，不新增事实源；执行者：steward）」（pending）
- 未完成任务 task-102「decide.py + team/decisions.jsonl：决策 e2b04b 追加/提交 trailer 解析/check/selftest（执行者：steward）」（pending）
- 未完成任务 task-103「P1 机检（decision_trail/model_policy/steward_self_audit）+ findings.jsonl + steward 首轮真实审计（执行者：steward）」（pending）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方「最近结论」时请人工标注被推翻项）


<!-- archived team-memory-card section -->
## lead · 决策记录协议条款：AGENTS.md §0.5 新增 L9 + lead-dispatch-rules §6 + org.md §2.1 纪律 6（先条款后机检）
<!-- task-id: task-99 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-65「迁移：预览物化/排版接入 MemoriaScheduler（P1/P2 作业）」：（未绑定产物）
- 完成任务 task-66「调度内核：补帧预算/公平份额（burst 累加器 + 长任务切片）」：（未绑定产物）
- 完成任务 task-67「v0.4.6 P0：工作集淘汰（DOM 回收 + 回滚复用）」：（未绑定产物）
- 完成任务 task-69「【todo-owner 认领·P1·顺序2】冷启动慢（13–23s 才自动打开首个文件；先补 boot 打点）」：src/memoria/services/lexical_index.py, scripts/benchmark/surface/run_boot_profile.py, src/memoria/ui/static/app/js/app.js
- 完成任务 task-76「✅ task-76 结论修正：evict 长批非块数问题（批尾布局 58.7%）；顺带修 purge 静默 no-op」：（未绑定产物）
- 完成任务 task-77「✅ task-70 堆泄漏已修复（MathJax MathItem 持有 detached 子树，−75.3%）」：（未绑定产物）
- 完成任务 task-80「P0：mapper.domToAst 支持嵌套列表 —— 修复 listItemIndex 错位（Tab 升降级的前置阻塞）」：（未绑定产物）
- 完成任务 task-83「P1 task-79 阶段5：粘贴替换跨块选区（新交互语义，进 0.4.7）」：src/memoria/ui/static/app/js/app.js, artifacts/agent/verify/selection-matrix-after-stage5.md
- 完成任务 task-84「P1 task-69：validate_kb + loadGraphData 移出 bootAutoOpen 关键路径（P0-b 已被 P0-a 覆盖，收益 43ms→1.9s）」：src/memoria/ui/static/app/js/app.js, src/memoria/ui/static/app/js/kb-check.js
- 完成任务 task-99「决策记录协议条款：AGENTS.md §0.5 新增 L9 + lead-dispatch-rules §6 + org.md §2.1 纪律 6（先条款后机检）」：AGENTS.md, docs/guides/lead-dispatch-rules.md, docs/guides/agent-team-org.md
- 最近结论（原文，未经裁决）：# 两批插件任务已派 + 教训已沉淀


## 一、我实测出一个**严重**插件 bug（先说这个）

```
task-97 的 owner = steward，完成它的是我（Lead 调 complete）
⇒ 卡片写进了 lead.md，不是 steward.md          ← 按【调用者】而非【任务 owner】归属
```

**更糟的是内容**：`lead.md` 里 task-97 那段的「我确认的事实」列的是
```
task-62 / 65 / 66 / 67 / 69 / 76 / 77 / 80 / 83 / 84
```
**与 task-97 完全无关** —— 抽取没按任务限定，把历史所有已完成任务全倒进来了。

**最糟**：段里含「最近结论（原文，未经裁决）」= **我的对话原文被搬进了 8 KiB 卡片**。

> **这条卡如果注入给新成员，它会以为 task-62/65/66… 是"前人确认的事实"。比没有卡更危险。**



<!-- archived team-memory-card section -->
## 二、task-106：缺陷批（5 个，全部有现场证据）

| # | 缺陷 | 证据 |
|---|---|---|
| **BUG-1** | 记忆卡：归属错 + 内容范围错 + 正文泄漏 | 上面那条 |
| **BUG-2** | completed 任务不能 reassign | `only a pending or in-progress task can be reassigned`（收口后发现 owner 挂在僵尸成员上，改不了） |
| **BUG-3** | 轨迹 64 KiB 是"整份成员文件"不是"单任务" | 执行者自己承认 |
| **BUG-4** | 轨迹是"读取时物化"，session 被清就拿不到 | 你刚问过要不要清 61 个历史会话 |
| BUG-5 | 新工具不进已存在会话的工具清单 | 我实测：asar 里有定义，当前会话调不到（这个只改文档） |



