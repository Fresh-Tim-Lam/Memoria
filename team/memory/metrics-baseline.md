# 记忆卡：metrics-baseline

<!-- team-memory-card/v1 · bounded to 8 KiB · omitted 1 older section(s) · truncated: true -->

## metrics-baseline · 0.5.x 基线测量：大知识库 agent 上下文膨胀与缓存命中低的真实归因（真库 数字通信原理）
<!-- task-id: task-190 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-190「0.5.x 基线测量：大知识库 agent 上下文膨胀与缓存命中低的真实归因（真库 数字通信原理）」：artifacts/agent/verify/kg-agent-retrieval/BASELINE-190-2026-10-27.md, artifacts/agent/verify/kg-agent-retrieval/baseline-190.json, artifacts/agent/verify/kg-agent-retrieval/composition-190.json, artifacts/agent/verify/kg-agent-retrieval/baseline_measure.py, artifacts/agent/verify/kg-agent-retrieval/composition_breakdown.py
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
（本段会话没有记录到失败的调用）
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）



## metrics-baseline · Lead 裁决
### Lead 裁决（下一个人该知道的 3 件事）
authority: lead
- 度量基线已交付且质量高：BASELINE-190（21 轮/116 iterations/135 calls/峰值 845,926=1M 的 84.6%/命中率 94.17%/compaction 8 次），并固定冻结快照 phase3-session-snapshot.jsonl 供后续复算。
- 两次自撤是本轮标杆：把工具结果放大系数从 10.94× 改为按存活轮算 1.16×，并指出 token 放大≠费用放大（命中单价为未命中 1/50，真实费 2.3%）；把 iteration KPI 降为候选（算术非测量）。撤回质量高于维持结论。
- 方法论贡献已沉淀：会话文件是活的（16→19→21 轮），任何基于会话的测量必须引冻结快照；新增 M12（索引上线后 Δhit ≥ −5pp）作为否决条件。本成员退休，度量产物与方法学保留。


## metrics-baseline · 【已关闭·已过期】task-60 P6 收口全域验收（0.4.4 已发布、门已过；产物在 p6-closure-*，缺最终汇总报告；与 task-62 同源）
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-11「[metrics-agent] 真机应用度量：WebView2 远程调试 + 页面内打点 + 人工/自动偏差校验」：（未绑定产物）
- 完成任务 task-21「[metrics-baseline] 补契约 C1 实测用例：编辑一块 ⇒ 其余块 id 不变（旧实现必须判红）」：（未绑定产物）
- 完成任务 task-22「[metrics-baseline] 建「渲染保真度」指标 + 结构签名（阶段 2 的核心验收工具）」：（未绑定产物）
- 完成任务 task-24「[metrics-baseline] 性能操作覆盖矩阵 + P_old 基线 + 预算表（阶段 2 前置，与保真度并列）」：（未绑定产物）
- 完成任务 task-25「[metrics-baseline] P0-b 渲染保真覆盖面补齐（图片/链接/高亮/表格/mermaid/行内公式/其它 surface/窗口化口径）+ S_old v2」：（未绑定产物）
- 完成任务 task-27「[metrics-baseline] 真机补测：kpHover 时延 + A10 行内公式 + agent 面板/助手弹窗/复阅卡最小结构」：（未绑定产物）
- 完成任务 task-31「[metrics-baseline] P2c 前置：真机公式/mermaid 渲染就绪判定工具（三态 + 判别力自证）」：（未绑定产物）
- 完成任务 task-33「[metrics-baseline] P5 前半：渲染层全量回归 + 冻结基线 S_render_frozen（P4 前置）」：（未绑定产物）
- 完成任务 task-38「[metrics-baseline] 增量失效量化：改一个块/公式/链接时，实际波及多少」：（未绑定产物）
- 完成任务 task-43「[metrics-baseline] S14 危险面验证：幽灵块（AST有/DOM无）被编辑时是否丢字或写错块」：（未绑定产物）
- 完成任务 task-45「[metrics-baseline] 真机验证：选区→composer 的精确行列引用（源码/预览/气泡三宿主 + 后端往返）」：（未绑定产物）
- 完成任务 task-46「[metrics-baseline] P5 后半：性能总闸（全操作 × 新旧对照 × 两次自检 × 低并发）」：（未绑定产物）
- 完成任务 task-47「[metrics-baseline] P6 前置：补齐 L1（wall-time 双侧）+ L3（7 操作工作量计数）——A/B 能力最后窗口」：（未绑定产物）
- 完成任务 task-54「[metrics-baseline] P6c 前置：8 个真机脚本补 config 隔离 + 复验两份冻结基线是否被 ambient 污染」：（未绑定产物）
- 完成任务 task-55「[metrics-baseline] 裁决：重建冻结语料与 p5_perf 基线 + 补「冻结语料只读 + 前后 sha 校验」守卫」：（未绑定产物）
- 完成任务 task-57「[metrics-baseline] L6：把 KB 守卫接到其余 8 个真机脚本（只改脚本，不跑测量）」：（未绑定产物）
- 完成任务 task-58「【已关闭·已完成】task-58 保真签名确定性 + frozen-v2 重建（实交付 s_render_frozen_v2 + signature-determinism-report.md）」：artifacts/agent/verify/signature-determinism-report.md, artifacts/baseline/s_render_frozen_v2
- 完成任务 task-60「【已关闭·已过期】task-60 P6 收口全域验收（0.4.4 已发布、门已过；产物在 p6-closure-*，缺最终汇总报告；与 task-62 同源）」：artifacts/agent/verify/p6-closure-alert.md, artifacts/agent/verify/p6-closure-fidelity-run1.json, artifacts/agent/verify/p6-closure-highlight.json
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
- 工具 edit 失败：Error: old_string was not found in "D:\AAA_Jupyter\Memoria\scripts\benchmark\surface\run_probe.py"
- 工具 edit 失败：Error: old_string was not found in "D:\AAA_Jupyter\Memoria\scripts\benchmark\surface\cdp.mjs"
- 工具 edit 失败：Error: cannot edit "D:\AAA_Jupyter\Memoria\scripts\benchmark\surface\run_probe.py": file changed since it was read — re-read the file, then retry
- 工具 read 失败：Error: cannot read "D:\AAA_Jupyter\Memoria\src\memoria\ui\pywebview.py": not found
- 工具 edit 失败：Error: cannot edit "D:\AAA_Jupyter\Memoria\scripts\benchmark\surface\realapp_measure.mjs": file changed since it was read — re-read the file, then retry
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）

## metrics-baseline · 退役豁免（Lead）
### 退役豁免（Lead）
authority: lead
- 豁免项：force: task-11, task-21, task-22, task-24, task-25, task-27, task-31, task-33, task-38, task-43, task-45, task-46, task-47, task-54, task-55, task-57, task-58, task-60
- 理由：metrics-baseline 名下 18 个历史完成任务（task-11…task-60）均为早前会话已关闭项，其完成证据在 artifacts/agent/verify 与 docs/todo.md §12 台账，无法逐条经 team_task_update 重新落卡；以 force 退休并审计留痕。退休目的：腾出 roster 名额给研讨会新设的 C 源（优秀开源取证）专员，人已要求"研讨会重新展开、再带人进来"
