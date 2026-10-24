# 记忆卡：lead

<!-- team-memory-card/v1 · bounded to 8 KiB · omitted 3 older section(s) · truncated: true -->

## 二、task-106：缺陷批（5 个，全部有现场证据）

| # | 缺陷 | 证据 |
|---|---|---|
| **BUG-1** | 记忆卡：归属错 + 内容范围错 + 正文泄漏 | 上面那条 |
| **BUG-2** | completed 任务不能 reassign | `only a pending or in-progress task can be reassigned`（收口后发现 owner 挂在僵尸成员上，改不了） |
| **BUG-3** | 轨迹 64 KiB 是"整份成员文件"不是"单任务" | 执行者自己承认 |
| **BUG-4** | 轨迹是"读取时物化"，session 被清就拿不到 | 你刚问过要不要清 61 个历史会话 |
| BUG-5 | 新工具不进已存在会话的工具清单 | 我实测：asar 里有定义，当前会话调不到（这个只改文档） |


## 三、task-105：契约版本 + 升级通知（你今天的新要求）

**问题**：一天内插件发生了 **4 次破坏性语义变更**，其他项目团队**完全不知道**：
```
planRef 必填            ← 老项目建版本任务会突然被拒
retire fail-closed      ← 退役会突然失败
同名重生解析语义变更
新增 team_trajectory
```

**设计**（写进任务了）：
```
① 插件侧 TEAM_CONTRACT_VERSION 常量 + changelog（每次破坏性变更 +1）
② 项目侧 team/plugin-contract.json 声明（contractVersion + acknowledgedAt + reviewedChanges）
③ 【核心】任何 team_* 工具响应里带 contractNotice：
      missing  → 你没声明，请看迁移指南
      outdated → 你落后 N 个版本，这是你缺的每一条 breaking change
      ahead    → 你的声明比插件新，该…（结论已截断）
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
- 未完成任务 task-98「steward 注册同步：org.md §2.2 行 + steward 章程 + agents.json 字段统一 + 快照重导出（修当前 team_audit FAIL=1）」（pending）
- 未完成任务 task-102「decide.py + team/decisions.jsonl：决策 e2b04b 追加/提交 trailer 解析/check/selftest（执行者：steward）」（pending）
- 未完成任务 task-103「P1 机检（decision_trail/model_policy/steward_self_audit）+ findings.jsonl + steward 首轮真实审计（执行者：steward）」（pending）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方「最近结论」时请人工标注被推翻项）

## lead · steward 注册同步：org.md §2.2 行 + steward 章程 + agents.json 字段统一 + 快照重导出（修当前 team_audit FAIL=1）
<!-- task-id: task-98 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-66「调度内核：补帧预算/公平份额（burst 累加器 + 长任务切片）」：（未绑定产物）
- 完成任务 task-67「v0.4.6 P0：工作集淘汰（DOM 回收 + 回滚复用）」：（未绑定产物）
- 完成任务 task-69「【todo-owner 认领·P1·顺序2】冷启动慢（13–23s 才自动打开首个文件；先补 boot 打点）」：src/memoria/services/lexical_index.py, scripts/benchmark/surface/run_boot_profile.py, src/memoria/ui/static/app/js/app.js
- 完成任务 task-76「✅ task-76 结论修正：evict 长批非块数问题（批尾布局 58.7%）；顺带修 purge 静默 no-op」：（未绑定产物）
- 完成任务 task-77「✅ task-70 堆泄漏已修复（MathJax MathItem 持有 detached 子树，−75.3%）」：（未绑定产物）
- 完成任务 task-80「P0：mapper.domToAst 支持嵌套列表 —— 修复 listItemIndex 错位（Tab 升降级的前置阻塞）」：（未绑定产物）
- 完成任务 task-83「P1 task-79 阶段5：粘贴替换跨块选区（新交互语义，进 0.4.7）」：src/memoria/ui/static/app/js/app.js, artifacts/agent/verify/selection-matrix-after-stage5.md
- 完成任务 task-84「P1 task-69：validate_kb + loadGraphData 移出 bootAutoOpen 关键路径（P0-b 已被 P0-a 覆盖，收益 43ms→1.9s）」：src/memoria/ui/static/app/js/app.js, src/memoria/ui/static/app/js/kb-check.js
- 完成任务 task-98「steward 注册同步：org.md §2.2 行 + steward 章程 + agents.json 字段统一 + 快照重导出（修当前 team_audit FAIL=1）」：docs/guides/agent-team-org.md, team/agents.json, team/team-board-snapshot.json
- 完成任务 task-99「决策记录协议条款：AGENTS.md §0.5 新增 L9 + lead-dispatch-rules §6 + org.md §2.1 纪律 6（先条款后机检）」：AGENTS.md, docs/guides/lead-dispatch-rules.md, docs/guides/agent-team-org.md
- 最近结论（原文，未经裁决）：§7 现在排在 §6 前面 —— 调换顺序：
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
- 未完成任务 task-103「P1 机检（decision_trail/model_policy/steward_self_audit）+ findings.jsonl + steward 首轮真实审计（执行者：steward）」（pending）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方「最近结论」时请人工标注被推翻项）
