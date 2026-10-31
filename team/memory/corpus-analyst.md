# 记忆卡：corpus-analyst

<!-- team-memory-card/v1 · bounded to 8 KiB · omitted 0 older section(s) · truncated: false -->

## corpus-analyst · 研讨会 Phase 1（语料分析）：教材知识库的 KP 粒度/可判性/真实提问分布/锚点稳定性实测
<!-- task-id: task-193 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-193「研讨会 Phase 1（语料分析）：教材知识库的 KP 粒度/可判性/真实提问分布/锚点稳定性实测」：artifacts/agent/verify/debate/kg-retrieval/PROPOSAL-corpus-analysis.md, artifacts/agent/verify/debate/kg-retrieval/data/manual-judgments.json, artifacts/agent/verify/debate/kg-retrieval/data/sample20.json, artifacts/agent/verify/debate/kg-retrieval/data/kp_inventory.json, artifacts/agent/verify/debate/kg-retrieval/scripts/01_kp_inventory.py
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
（本段会话没有记录到失败的调用）
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）



## corpus-analyst · 研讨会 Phase 1.5：怎样科学地建索引（判据/信源顺序/时机成本/质量保证/覆盖策略/不该建）
<!-- task-id: task-196 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-196「研讨会 Phase 1.5：怎样科学地建索引（判据/信源顺序/时机成本/质量保证/覆盖策略/不该建）」：artifacts/agent/verify/debate/kg-retrieval/INDEXING-R9R10R13R14.md, artifacts/agent/verify/debate/kg-retrieval/data/index-method.json, artifacts/agent/verify/debate/kg-retrieval/data/ch03-descriptions.json, artifacts/agent/verify/debate/kg-retrieval/data/corpus-snapshot.json, artifacts/agent/verify/debate/kg-retrieval/scripts/07_index_method.py, artifacts/agent/verify/debate/kg-retrieval/scripts/08_corpus_snapshot.py
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
- 工具 edit 失败：Error: cannot modify "D:\AAA_Jupyter\Memoria\artifacts\agent\verify\debate\kg-retrieval\PROPOSAL-corpus-analysis.md": file has not been read — read the file, then retry
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）


## corpus-analyst · R13 反事实检验：按书序是否只是"用户恰好在读第3章"的过拟合；前沿优先是否更好
<!-- task-id: task-197 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-197「R13 反事实检验：按书序是否只是"用户恰好在读第3章"的过拟合；前沿优先是否更好」：artifacts/agent/verify/debate/kg-retrieval/R13-COUNTERFACTUAL.md, artifacts/agent/verify/debate/kg-retrieval/data/r13-counterfactual.json, artifacts/agent/verify/debate/kg-retrieval/data/real-usage.json, artifacts/agent/verify/debate/kg-retrieval/scripts/09_real_usage_across_kbs.py, artifacts/agent/verify/debate/kg-retrieval/scripts/10_r13_counterfactual.py, artifacts/agent/verify/debate/kg-retrieval/INDEXING-R9R10R13R14.md
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
- 工具 edit 失败：Error: cannot modify "D:\AAA_Jupyter\Memoria\artifacts\agent\verify\debate\kg-retrieval\INDEXING-R9R10R13R14.md": file has not been read — read the file, then retry
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）

## corpus-analyst · Lead 裁决
### Lead 裁决（下一个人该知道的 3 件事）
authority: lead
- 真实语料分析已完成：KP 粒度/可判性 45%/覆盖 4-14 章/同名碰撞/锚点歧义 37% 等，全部绑固定 sha256 快照、脚本可复跑；并主动完成 R13 反事实证明「按书序」是过拟合（真实 4 库 前沿优先 2 胜 2 平 0 负）。
- 人 2026-10-27 裁定 AAA_Courses 语料维护很差、无榜样价值 ⇒ 其全部数字降级为【D 源：数据现实/迁移成本】，不得再作设计论证依据；该约束已写入证据分级规则。
- 主动撤回 4 处自方主张（KP 太碎/太大证据、双字段、按书序、冷启动兜底表述），撤回质量高于维持结论；本成员退休，语料观测数据保留备查。
