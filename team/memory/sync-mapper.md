# 记忆卡：sync-mapper

<!-- team-memory-card/v1 · bounded to 8 KiB · omitted 8 older section(s) · truncated: true -->

## sync-mapper · 有序列表 start&gt;1 往返被重编号（10.→1.）：先判定是否可达写盘（若可达则 R0），再定修法
<!-- task-id: task-157 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-157「有序列表 start&gt;1 往返被重编号（10.→1.）：先判定是否可达写盘（若可达则 R0），再定修法」：artifacts/agent/verify/todo/ordered-list-renumber.md, scripts/benchmark/maintenance/ordered_list_start_test.js, artifacts/agent/verify/todo/ordered-list-RED.log, artifacts/agent/verify/todo/ordered-list-GREEN.log, artifacts/agent/verify/todo/ordered-list-static.log, artifacts/agent/verify/todo/ordered-list-realapp.log, artifacts/agent/verify/todo/ordered-list-realapp.json, artifacts/agent/verify/todo/ordered-list-realapp-after.log, src/memoria/ui/static/app/js/ast.js, src/memoria/ui/static/app/js/parser.js, src/memoria/ui/static/app/js/source-gen.js, src/memoria/ui/static/app/js/mapper.js
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
（本段会话没有记录到失败的调用）
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）





## sync-mapper · 选择题卡片排版重做：选项名/解释改纵向堆叠 + 解释 2 行 clamp（窄栏不再撑爆高度）
<!-- task-id: task-162 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-162「选择题卡片排版重做：选项名/解释改纵向堆叠 + 解释 2 行 clamp（窄栏不再撑爆高度）」：src/memoria/ui/static/app/css/app.css, src/memoria/ui/static/app/js/agent-question.js, artifacts/agent/verify/todo/agent-question-layout.md, artifacts/agent/verify/todo/agent-question-layout-before.json, artifacts/agent/verify/todo/agent-question-layout-after.json, artifacts/agent/verify/todo/agent-question-layout-probe.mjs
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
（本段会话没有记录到失败的调用）
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）




## sync-mapper · 跳转小窗改 8 方向自由缩放（去掉原生右下角小把手）+ 从左侧/上方拉伸时位置同步
<!-- task-id: task-168 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-168「跳转小窗改 8 方向自由缩放（去掉原生右下角小把手）+ 从左侧/上方拉伸时位置同步」：src/memoria/ui/static/app/js/app.js, src/memoria/ui/static/app/css/app.css, artifacts/agent/verify/todo/link-panel-resize.md, artifacts/agent/verify/todo/link-panel-resize-task168.patch, artifacts/agent/verify/todo/link-panel-resize.json, artifacts/agent/verify/todo/link-panel-resize-probe.mjs
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
（本段会话没有记录到失败的调用）
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）



## sync-mapper · 分栏模式编辑 mermaid 时源码区被抢滚动：预览刷新后自动定位把 mermaid 块顶对齐，打断编辑
<!-- task-id: task-170 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-170「分栏模式编辑 mermaid 时源码区被抢滚动：预览刷新后自动定位把 mermaid 块顶对齐，打断编辑」：src/memoria/ui/static/app/js/app.js, tests/test_split_preview_scroll_sync_guard.py, artifacts/agent/verify/todo/split-mermaid-edit-scroll.md, artifacts/agent/verify/todo/split-mermaid-edit-scroll-before.json, artifacts/agent/verify/todo/split-mermaid-edit-scroll-after.json, artifacts/agent/verify/todo/split-mermaid-edit-scroll-verify.mjs
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
- 工具 edit 失败：Error: cannot modify "D:\AAA_Jupyter\Memoria\src\memoria\ui\static\app\js\app.js": file has not been read — read the file, then retry
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）


## sync-mapper · 版本更新机制：检查更新（受出网开关）+ 下载安装包 + 手动操作说明（不自动替换）
<!-- task-id: task-180 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-180「版本更新机制：检查更新（受出网开关）+ 下载安装包 + 手动操作说明（不自动替换）」：src/memoria/services/update.py, src/memoria/presentation/api/ui.py, src/memoria/ui/static/app/js/update-settings.js, src/memoria/ui/static/app/js/graph-settings.js, src/memoria/ui/static/app/i18n/zh-CN.js, src/memoria/ui/static/app/i18n/en.js, tests/test_update_mechanism.py, tests/test_update_ui_contract.py, artifacts/agent/verify/update-mechanism/update-mechanism.md, artifacts/agent/verify/update-mechanism/update-e2e-normal.json, artifacts/agent/verify/update-mechanism/update-e2e-offline.json
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
- 工具 team_task_update 失败：Error: only an in-progress task can complete
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）

## sync-mapper · 修复预览/跳转小窗三问题：图片编辑后闪到开头 + 小窗 mermaid 未渲染 + 关闭小窗改按钮定位
<!-- task-id: task-198 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-198「修复预览/跳转小窗三问题：图片编辑后闪到开头 + 小窗 mermaid 未渲染 + 关闭小窗改按钮定位」：src/memoria/ui/static/app/js/app.js, src/memoria/ui/static/app/js/image-tools.js, src/memoria/ui/static/app/js/edit-handler.js, src/memoria/ui/static/app/i18n/zh-CN.js, src/memoria/ui/static/app/i18n/en.js, tests/test_preview_panel_images_mermaid.py, artifacts/agent/verify/todo/preview-panel-images-mermaid/task-198-report.md, artifacts/agent/verify/todo/preview-panel-images-mermaid/t198-real.json, artifacts/agent/verify/todo/preview-panel-images-mermaid/t198-real-red-b1.json, artifacts/agent/verify/todo/preview-panel-images-mermaid/t198-real-red-b2b3.json
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
- 工具 edit 失败：Error: cannot edit "D:\AAA_Jupyter\Memoria\src\memoria\ui\static\app\js\app.js": file changed since it was read — re-read the file, then retry
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）
