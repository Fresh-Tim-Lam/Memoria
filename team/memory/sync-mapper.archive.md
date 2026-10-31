
<!-- archived team-memory-card section -->
## sync-mapper · Lead 裁决
### Lead 裁决（下一个人该知道的 3 件事）
authority: lead
- task-140 代码已完成并经 Lead 代跑门禁：app.js +161/−13，全仓已无 block:"start" 代码，node --check exit 0，pytest tests/test_preview_block_commit.py 9 passed，全量 1474 passed / 0 failed，12 剧本 12/12。核心修法：layoutPreviewRangeBand 改返回几何 {first,band,top,bottom}（旧签名丢掉目标 top/bottom 并集，那正是跳转唯一需要的不变量）；previewRangeViewportRect 换算到 #preview-pane 视口坐标；_reanchorJumpScroll 只补 drift、绝不 scrollIntoView；源码侧同病一并修。
- Lead 裁决 I1 = A（严格「任意部分已显示即不滚」，保留当前实现）。人明确给了「至少」这个条件，35% 阈值是他没要求的；高亮 flash 已提供反馈；若真人反馈「点了没反应」再切 B（仅改 _jumpScrollToRange 的 I1 分支）。关键元发现：tests/test_preview_block_commit.py:167 原本 assert block:"start" 存在 —— 测试把 bug 写成了契约，绿灯在保护错误行为。
- 未完成（新实例继续）：① 三场景真机时间序列断言（目标在视口上方/下方/已部分可见 + 「1.5s 内 scrollTop 不再变化」，探针在报告 §6）② 补完报告数据 ③ 通过后 claim task-141。原实例 shell 0xC0000142 连 echo 都起不来，已如实上报未谎报绿灯。







<!-- archived team-memory-card section -->
## sync-mapper · [sync-mapper] 修 S1/S2：画笔生命周期收尾 + 只读态样式闸门
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-10「[sync-mapper] 修 S1/S2：画笔生命周期收尾 + 只读态样式闸门」：（未绑定产物）
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
- 工具 grep 失败：Error: tool call timed out after 30000ms
- 工具 edit 失败：Error: old_string matched 2 times in "D:\AAA_Jupyter\Memoria\src\memoria\ui\static\app\js\app.js"; provide a more specific old_string or set replace_all to true
### 我留下的坑 / 下一个人该从哪开始
authority: machine
- 未完成任务 task-140「跳转滚动定位三处行为不符：延迟被拉顶部 / 已可见仍滚动 / 固定向下（根因已定位 app.js:15612+15639 block:"start"）」（in_progress）
- 未完成任务 task-141「特长文档：预览区已滚到中部时，源码区一修改预览就跳到文件开头（滚动位置丢失）」（pending）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）






## sync-mapper · 退役豁免（Lead）
### 退役豁免（Lead）
authority: lead
- 豁免项：force: task-10
- 理由：该实例 shell 出现 0xC0000142 DLL 初始化失败（连 echo 都起不来），无法继续验证。task-10 是历史任务、与本轮无关，其卡片段缺失不构成本次回收的阻塞。task-140 代码已完成且经 Lead 代跑门禁全绿（node --check 0 / pytest 1474 passed / 12 剧本 12/12），剩余真机时间序列验证与 task-141 由同名新实例继续，Lead 裁决已写入 memory card。






<!-- archived team-memory-card section -->
## sync-mapper · 跳转滚动定位三处行为不符：延迟被拉顶部 / 已可见仍滚动 / 固定向下（根因已定位 app.js:15612+15639 block:"start"）
<!-- task-id: task-140 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-140「跳转滚动定位三处行为不符：延迟被拉顶部 / 已可见仍滚动 / 固定向下（根因已定位 app.js:15612+15639 block:"start"）」：artifacts/agent/verify/todo/jump-scroll-fix.md, artifacts/agent/verify/todo/jump-scroll-fix-timeseries.json, artifacts/agent/verify/todo/jump-scroll-fix-timeseries-math.json, artifacts/agent/verify/todo/jump-scroll-fix-run.log
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
- 工具 edit 失败：Error: cannot edit "D:\AAA_Jupyter\Memoria\artifacts\agent\verify\todo\jump-scroll-fix-run.ps1": file changed since it was read — re-read the file, then retry
- 工具 team_task_update 失败：Error: task mutation requires its owner or Team Lead
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）






<!-- archived team-memory-card section -->
## sync-mapper · 特长文档：预览区已滚到中部时，源码区一修改预览就跳到文件开头（滚动位置丢失）
<!-- task-id: task-141 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-141「特长文档：预览区已滚到中部时，源码区一修改预览就跳到文件开头（滚动位置丢失）」：artifacts/agent/verify/todo/preview-scroll-lost-on-edit.md, artifacts/agent/verify/todo/preview-scroll-lost-on-edit-summary.json, artifacts/agent/verify/todo/preview-scroll-lost-on-edit-RED-before-fix.log, artifacts/agent/verify/todo/preview-scroll-lost-on-edit-2x2-after.log, artifacts/agent/verify/todo/preview-scroll-lost-on-edit-matrix.log, artifacts/agent/verify/todo/preview-scroll-lost-on-edit-task140-regression.log, src/memoria/ui/static/app/js/app.js
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
- 工具 edit 失败：Error: cannot edit "D:\AAA_Jupyter\Memoria\artifacts\agent\verify\todo\jump-scroll-fix-run.ps1": file changed since it was read — re-read the file, then retry
- 工具 team_task_update 失败：Error: task mutation requires its owner or Team Lead
- 工具 team_task_update 失败：Error: team task "task-141" is owned by another member
- 工具 edit 失败：Error: cannot modify "D:\AAA_Jupyter\Memoria\src\memoria\ui\static\app\js\app.js": file has not been read — read the file, then retry
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）






<!-- archived team-memory-card section -->
## sync-mapper · R0 数据损坏：文件尾部 ≥2 换行时保存丢 1 个尾换行并写进磁盘（collectEditorBody 单点修复 + 逐字节比对测试）
<!-- task-id: task-147 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-147「R0 数据损坏：文件尾部 ≥2 换行时保存丢 1 个尾换行并写进磁盘（collectEditorBody 单点修复 + 逐字节比对测试）」：artifacts/agent/verify/todo/doc-body-tail-newline-fix.md, artifacts/agent/verify/todo/doc-body-tail-newline-fix-RED.log, artifacts/agent/verify/todo/doc-body-tail-newline-fix-GREEN.log, artifacts/agent/verify/todo/doc-body-tail-newline-realapp-RED.log, artifacts/agent/verify/todo/doc-body-tail-newline-realapp-RED.json, artifacts/agent/verify/todo/doc-body-tail-newline-realapp.log, artifacts/agent/verify/todo/doc-body-tail-newline-realapp.json, scripts/benchmark/maintenance/tail_newline_roundtrip_test.js, tests/test_tail_newline_roundtrip.py, src/memoria/ui/static/app/js/app.js
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
（本段会话没有记录到失败的调用）
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）






<!-- archived team-memory-card section -->
## sync-mapper · 源码区剪切（Ctrl+X）不可用：每行独立 contenteditable ⇒ 跨行选区原生 cut 失效；源码区缺 cut/copy 处理（预览区有）
<!-- task-id: task-150 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-150「源码区剪切（Ctrl+X）不可用：每行独立 contenteditable ⇒ 跨行选区原生 cut 失效；源码区缺 cut/copy 处理（预览区有）」：artifacts/agent/verify/todo/source-cut-fix.md, artifacts/agent/verify/todo/source-cut-RED.log, artifacts/agent/verify/todo/source-cut-RED.json, artifacts/agent/verify/todo/source-cut-after.log, artifacts/agent/verify/todo/source-cut-realapp.json, artifacts/agent/verify/todo/source-cut-probe.mjs, artifacts/agent/verify/todo/source-cut-run.ps1, artifacts/agent/verify/todo/source-cut-fixture-gen.py, src/memoria/ui/static/app/js/app.js, src/memoria/ui/static/app/i18n/zh-CN.js, src/memoria/ui/static/app/i18n/en.js
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
- 工具 edit 失败：Error: ReplaceFileW EIO (Win32 1175): D:\AAA_Jupyter\Memoria\src\memoria\ui\static\app\js\app.js
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）







<!-- archived team-memory-card section -->
## sync-mapper · 引用块（> ）内支持列表项（- ）：AST 现状是"children 只能装段落"⇒ 先查 parser 是否支持再定范围
<!-- task-id: task-155 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-155「引用块（> ）内支持列表项（- ）：AST 现状是"children 只能装段落"⇒ 先查 parser 是否支持再定范围」：artifacts/agent/verify/todo/blockquote-list-support.md, scripts/benchmark/maintenance/blockquote_list_test.js, artifacts/agent/verify/todo/blockquote-list-RED.log, artifacts/agent/verify/todo/blockquote-list-realapp.log, artifacts/agent/verify/todo/blockquote-list-realapp.json, src/memoria/ui/static/app/js/parser.js, src/memoria/ui/static/app/js/source-gen.js, src/memoria/ui/static/app/js/mapper.js, src/memoria/ui/static/app/js/surface/render-core.js
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
- 工具 edit 失败：Error: cannot modify "D:\AAA_Jupyter\Memoria\src\memoria\ui\static\app\js\mapper.js": file has not been read — read the file, then retry
- 工具 edit 失败：Error: cannot modify "D:\AAA_Jupyter\Memoria\artifacts\agent\verify\todo\blockquote-list-support.md": file has not been read — read the file, then retry
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）






