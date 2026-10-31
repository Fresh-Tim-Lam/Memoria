# 记忆卡：render-perf

<!-- team-memory-card/v1 · bounded to 8 KiB · omitted 15 older section(s) · truncated: true -->

## render-perf · 实现布局确定性种子 + 会话内保位（D-KGV-07）—— 解决"每次打开图谱布局大跳"
<!-- task-id: task-176 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-176「实现布局确定性种子 + 会话内保位（D-KGV-07）—— 解决"每次打开图谱布局大跳"」：artifacts/agent/verify/todo/kgviz-layout-seed.md, artifacts/agent/verify/todo/kgviz-layout-seed/verify_seed.json, artifacts/agent/verify/todo/kgviz-layout-seed/shots/01_graph2d_seeded.png, artifacts/agent/verify/todo/kgviz-layout-seed/shots/stable3_run1.png, artifacts/agent/verify/todo/kgviz-layout-seed/shots/stable3_run2.png, artifacts/agent/verify/todo/kgviz-layout-seed/shots/stable3_run3.png, artifacts/agent/verify/todo/kgviz-layout-seed/shots/04_graph3d_seeded.png, tests/test_kgviz_layout_seed.py, src/memoria/ui/static/app/js/graph-engine.js, src/memoria/ui/static/app/js/graph-layout-2d.js, src/memoria/ui/static/app/js/graph-layout-3d.js, scripts/benchmark/surface/results/raw-interaction-t176-final_f43c4478.json
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
- 工具 edit 失败：Error: cannot modify "D:\AAA_Jupyter\Memoria\src\memoria\ui\static\app\js\graph-layout-2d.js": file has not been read — read the file, then retry
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）



## render-perf · 实现图标签 LOD/避让（D-KGV-06）—— 解决"134 标签淹没图形、淹没大小差异"
<!-- task-id: task-177 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-177「实现图标签 LOD/避让（D-KGV-06）—— 解决"134 标签淹没图形、淹没大小差异"」：artifacts/agent/verify/todo/kgviz-label-lod.md, artifacts/agent/verify/todo/kgviz-label-lod/verify_label.json, artifacts/agent/verify/todo/kgviz-label-lod/shots/01_label_lod.png, artifacts/agent/verify/todo/kgviz-label-lod/shots/02_hover_hidden_label.png, artifacts/agent/verify/todo/kgviz-label-lod/shots/03_zoom_more_labels.png, artifacts/agent/verify/todo/kgviz-label-lod/shots/04_red_all_labels.png, artifacts/agent/verify/todo/kgviz-label-lod/shots/05_graph3d_label_lod.png, tests/test_kgviz_label_lod.py, src/memoria/ui/static/app/js/graph-label.js, src/memoria/ui/static/app/js/graph-view-2d.js, src/memoria/ui/static/app/js/graph-view-3d.js, scripts/benchmark/surface/results/raw-interaction-t177-final_48547803.json
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
- 工具 edit 失败：Error: old_string matched 2 times in "D:\AAA_Jupyter\Memoria\src\memoria\ui\static\app\js\graph-view-2d.js"; provide a more specific old_string or set replace_all to true
- 工具 read 失败：Error: offset 300 is out of range for "D:\AAA_Jupyter\Memoria\artifacts\agent\verify\todo\kgviz-label-lod\verify_label.py" (238 lines)
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）


## render-perf · 实现 KG 埋点 E1/E2（D-KGV-08）—— KG 落地最后一项，让已冻结的裁决能被执行
<!-- task-id: task-178 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-178「实现 KG 埋点 E1/E2（D-KGV-08）—— KG 落地最后一项，让已冻结的裁决能被执行」：artifacts/agent/verify/todo/kgviz-telemetry.md, artifacts/agent/verify/todo/kgviz-telemetry/verify_telemetry.json, artifacts/agent/verify/todo/kgviz-telemetry/graph-telemetry.jsonl, artifacts/agent/verify/todo/kgviz-telemetry/shots/01_settings_telemetry.png, tests/test_kgviz_telemetry.py, src/memoria/storage/graph_telemetry.py, src/memoria/presentation/api/ui.py, src/memoria/ui/static/app/js/graph-settings.js, scripts/benchmark/surface/results/raw-interaction-t178-final_17edfe3e.json
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
- 工具 edit 失败：Error: cannot modify "D:\AAA_Jupyter\Memoria\src\memoria\ui\static\app\js\graph-settings.js": file has not been read — read the file, then retry
- 工具 team_task_update 失败：Error: only an in-progress task can complete
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）

## render-perf · 补齐 KG 设计未落地项：毛球态判定阈值重定（D-KGV-09）+ T-double 检查（D-KGV-15）
<!-- task-id: task-187 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-187「补齐 KG 设计未落地项：毛球态判定阈值重定（D-KGV-09）+ T-double 检查（D-KGV-15）」：artifacts/agent/verify/todo/kgviz-hairball-tdouble.md, artifacts/agent/verify/todo/kgviz-hairball-tdouble/verify_hairball_tdouble.json, artifacts/agent/verify/todo/kgviz-hairball-tdouble/shots/01_graph2d_galaxy_tdouble.png, artifacts/agent/verify/todo/kgviz-hairball-tdouble/verify_hairball_tdouble.py, tests/test_kgviz_hairball_tdouble.py, src/memoria/ui/static/app/js/graph-groups.js, src/memoria/ui/static/app/js/graph-engine.js, scripts/benchmark/surface/results/raw-interaction-t187-final_0337954e.json
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
（本段会话没有记录到失败的调用）
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）
