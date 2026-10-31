# 记忆卡：panel-router-dev

<!-- team-memory-card/v1 · bounded to 8 KiB · omitted 0 older section(s) · truncated: false -->

## panel-router-dev · Lead 裁决
### Lead 裁决（下一个人该知道的 3 件事）
authority: lead
- 引擎/连线重叠这条线由你独占负责：已完成 org 树干单一绘制源（O1/O2 DOM 验证）、走廊规划器 CP1–CP1.2、端口三腿/锚定腿、fenceChannels 接线、J 同参度量、默认 ON 切换（3c61838bd3）；pipe 重叠三套=0、退化段=0、hug=0、gaps 仅 2 对白名单例外。
- 未收口：hub alpha-dev return × gamma-dev out 端对端 gap=4px（e2e）；e2e 度量已进共享 metrics（41191a76f1 RED）。已否决的修法：planner clash 环（claimFixed 不参与）、final-path 平移（引入新 A14-5/P2short 回归）。正解方向：在 claimFixed/固定腿规划阶段加端对端净空 ≥8px。
- 纪律：flag 默认 ON 是当前产品路径；不得加白名单掩盖这条 4px；每步 commit、先证红；度量必须复用 tests/helpers/corridorMetrics.ts，禁写第二套；改前 read，禁 reset --hard。

## panel-router-dev · 引擎路由/连线重叠的独占责任人（接手 CP1.1）：走廊按端口方位分配后 A* 走不通与折返问题，flag 默认 OFF 下推进，不改断言。
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
（没有需要补录的已完成任务；各任务证据见其完成段落）
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
- 工具 edit 失败：Error: old_string was not found in "D:\deepseek-harness\packages\experimental\client-ui-agent-team\src\client\panel\engine\astar.ts"
- 工具 edit 失败：Error: cannot edit "D:\deepseek-harness\packages\experimental\client-ui-agent-team\src\client\panel\engine\corridors.ts": file changed since it was read — re-read the file, then retry
- 工具 edit 失败：Error: old_string was not found in "D:\deepseek-harness\packages\experimental\client-ui-agent-team\src\client\panel\engine\corridors.ts"
- 工具 edit 失败：Error: cannot edit "D:\deepseek-harness\artifacts\agent\panel-ui\corridor-dev\measure.mts": file changed since it was read — re-read the file, then retry
- 工具 edit 失败：Error: cannot edit "D:\deepseek-harness\packages\experimental\client-ui-agent-team\src\client\panel\engine\edges.ts": file changed since it was read — re-read the file, then retry
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）
