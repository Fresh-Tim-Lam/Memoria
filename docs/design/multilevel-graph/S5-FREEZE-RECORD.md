# S5 冻结记录（Freeze Record）

> **冻结对象**：`docs/design/multilevel-graph/S5-nav-v1.md`（12 条规范 + R-S5-1..R-S5-12 + T01–T30 规范表 + S5a 生成器）。
> **冻结时间**：2026-11-03T21:28+08:00（Asia/Shanghai）。
> **决策**：`dec-20261103-e188aa2c`（Lead；S0–S4 已冻结）。
> **状态**：**已冻结**。S6 可开；S0–S6 冻结前仍不写产品代码。

## 1. 冻结产物与身份

| 产物 | 角色 | sha256 |
|---|---|---|
| `S5-nav-v1.md`（**冻结稿最终态**） | S5 唯一规范来源（含 T01–T30、S5a 投影） | `7f4c4515599784c16501edf21fe1ff9d46efa08d36074ad1de7e0fb49240fe17` |
| `S5-engineering-check.md` | SE 工程校核 + S5a 生成器输出（148 边） | `3683074f…` |
| `S5-nav-proposal-A-v2.md` | 证据链（主办研究） | `538506a4…` |
| `S5-nav-proposal-B-v2.md` | 证据链（独立复核） | `84ba06f7…` |
| `S5-objections-v2.md` | 差异/异议 | `dde1f9d0…` |
| `S5-RULINGS.md` | Lead 裁决（R-S5-1..8） | `8285a8b3…` |
| `ENGINEERING-PLAN.md`（S5 增量） | ER-06/DF-06/ST-06+S5a | `c6f3d861…` |

**冻结轮次**：SE 首轮 9 PASS / 3 FAIL（v1 未附表/S5a）；补 T01–T30 + S5a 投影后 11 PASS / 1 FAIL（T05 展开 149 vs 声明 148）；T05 修为 `ALL\{Idle}`（Idle CLOSE no-op 不计数）后 **12/12 PASS、M_fail=[]**，生成器输出 `states=9/events=21/unique_edges=148/duplicates={}/unreachable=[]`；Lead 独立机检（12 条款、R-S5-1..12、30 表行、148、T05、9 状态、S5a、VM 边界）PASS。冻结身份取最终态 sha `7f4c4515…`。

## 2. S5 冻结了什么（一句话版）

1. **GraphNavFrame**（focus/level/view_family/dimension/hop/new_hop/mode/budget/origin/edition/history）**只在 Presentation、不进 VM**；S5 只构造 `frame_spec` 给 S4，不算 presence；
2. **frame_id = sha256(canonical(frame_spec))**；edition 由 S5 从 corpus/manifest 派生本地校验；不消费 S4 未冻结字段；
3. **9 主状态** + 正交 `mode ∈ {default,full}` / `data_state ∈ {ok,empty_nosemantic}`；T01–T30 规范表为唯一真源；**`(state,event)` 唯一**；S5a 由表生成（148 条唯一边），表↔图一致；
4. **点击按 kind 唯一分流**：KP→编辑器（frame/stack 不变）、簇→drill；edge→selection；background→清 selection；hover/focus 不改导航；
5. **drill/back**：push/弹栈恢复 focus/level/dimension/hop/mode；`MAX_STACK=50`、去重、`BREADCRUMB_TO` 截断；重开只恢复 level0+mode+dimension；
6. **维度切换可逆**：push 当前 frame，back 恢复；history 只在 CLOSE/RELOAD/RESET 清空；
7. **`EXPLICIT_NEW_HOP` 唯一**：A 维/focus/hop=1 → hop=2/new_hop=true；幂等；默认路径无 2 跳；
8. **FOCUS_LOST/DATA_REFRESHED** 转移存在且恢复可达；focus 丢失→最近祖先/根；
9. **事务化导航**：clone→nextFrame/nextStack→S4→成功才 commit；失败 canonical diff=0；初始帧失败→`Degraded`，非初始保持原 frame；
10. **full 与 drill 正交**，full 请求满足 S4 candidate 超集；失败按事务化；
11. **S3 事件→S5 动作**、payload 无导航；渲染器无导航动作；VM 纯度（D-4）；
12. **可访问性/持久化/度量**：键盘等价动作、aria-live、只持久化 mode/dimension/level0 frame、G6 导航指标。

## 3. 机检与证据

- SE M-S5-1..12 + S5a：`M_fail=[]`；生成器 `unique_edges=148`、`duplicate_state_event={}`、`unreachable_states=[]`、无禁用主状态；
- 同版本 mermaid（vendored，sha `9198f632…`）：PLAN 18 图 + 报告 3 图全部 `PARSE_OK`；
- 与 S0–S4 一致性：S0-9/D-4、S3 R-S3-2/事件、S4 frame_spec/presence/R-S4-9、S1 H/A、S2 run/无簇、D-3 全 PASS；
- Lead 独立机检 PASS。

## 4. 未关闭项（不阻塞冻结）

- O-S5-3..10：frame_id/edition schema（S6a）、300ms 去抖细节、URL/书签（S6a）、G6 字段、BREADCRUMB 截断细节、多归属祖先规则、事务失败注入测试（S6/S8）。

## 5. 变更控制

- 加状态/事件/动作：S5 修订 + 决策；删/改状态机语义/点击语义/new_hop/frame 字段：重开 S5；
- T01–T30 是规范表；S5a 由生成器生成，手工改图视为破坏冻结；
- 冻结身份 = 本记录 + `S5-nav-v1.md`。

## 6. 下一步

- **S6（数据契约收尾）**：ER/DFD 定稿、run/registry/history/VISUAL/NAV/CACHE 的 schema、存储/审计/GC、S4/S5 需求收口；S6a 工程图纸；
- S0–S6 全部冻结后，才进入产品实现（0.5 图谱板块）。
