# S5 裁决（Lead）：并集、异议处置与修订轮

> **依据**：`multilevel-graph-vision.md`；`S5-charter.md`；
> 上游冻结 S0/S1/S2/S3(+ADDENDUM-1)/S4 `241b1e1e…/6676c71d…/92bb0041…/0ca4ea0e…/2576f6c8…`。
> **输入**：提案 A `S5-nav-proposal-A.md`（`6eee4f66…`）、提案 B `S5-nav-proposal-B.md`（`81066c59…`）、`S5-objections.md`。
> **状态**：S5 **未冻结**；无 P0，3 条 P1（A）+ 1 条 P1（B）必修。本文件是修订轮唯一依据。

## 0. Lead 复核

| 项 | 复核动作 | 结论 |
|---|---|---|
| P1-1 A S5a 图与表不一致 | 对 A S5a（FullExpanded 独立状态）与 S5-2（声明为正交复合） | **成立**：状态图机检必 FAIL；复合状态必须正交表达且图表逐条一致 |
| P1-2 维度切换能否 back | 读 A（清空 history）与 B（push 可 back） | **成立**：S5-4 可逆栈与 S5-7 冲突；必须裁 |
| P1-3 S4 失败事务性 | 读 A（先 push 后调 S4）与 B（未定义） | **成立**：失败会留下 push 过的 stack/半改 frame；必须事务化 |
| P1-4 B 不可达 FullExpanded/缺状态 | 读 B 状态集与 FULL_TOGGLE | **成立**：B 设 FullExpanded 状态但无进入边；且缺 Loading/Degraded/Stale/Overview/RelationDeepened |
| 其余点名 | frame 不进 VM/点击/一跳/NEW_HOP/focus 生命周期/S3-S4-S1-S2 边界/a11y | 全 PASS；P2 合并 |

## 1. 跨议题裁决（R-S5-1..R-S5-8）

### R-S5-1 S5a 状态图与转移表逐条一致（P1-1）
- **裁决（冻结）**：`FullExpanded`/`EmptyNoSemantic` **不得作为独立主状态**，必须表达为**正交变量**（如 `mode ∈ {default, full}`、`data_state ∈ {ok, empty_nosemantic}`）；`Focused` 的 UI 焦点与 `Stale` 必须补全在**所有**适用主状态上的进出边；S5a 必须由转移表**逐条生成/对照**，`mermaid PARSE_OK`，且机检「表↔图」一致（状态集/边集/事件集完全相同）。

### R-S5-2 维度切换可逆（P1-2）
- **裁决（冻结）**：维度切换 **push 当前 frame、可 back 恢复**（focus/level/dimension/hop/mode 全部恢复）；不得清空 history；`history` 只在 `CLOSE/RELOAD` 或显式 `RESET` 时清空。若某实现确需"切回"动作，必须与 back 语义一致且可见。
- **机检**：dimension switch 后 back == 切换前 canonical frame；history 非空。

### R-S5-3 导航转移事务化（P1-3）
- **裁决（冻结）**：任何导航动作必须**先构造 `nextFrame`（不修改当前 frame/stack）→ 请求 S4 → 成功才 commit**；任一步失败（`S4_BUDGET_INVALID`/`FOCUS_UNRESOLVED`/`DIM_*`/非法转移）必须保持**转移前 canonical state/frame/stack**（diff=0），并可见（初始帧失败→`Degraded`；非初始→提示并保持原 frame）。禁止先 push 后回滚式"半事务"。
- **机检**：失败注入（S4 返回错误）后 canonical diff=0；无孤立 stack 项。

### R-S5-4 主状态并集（P1-4）
- **裁决**：主状态集合 = `{Idle, Loading, Degraded, Overview, Focused, HierarchyDrilled, RelationExpanded, RelationDeepened, Stale}`（A 的集合）；`FullExpanded`/`EmptyNoSemantic` 为正交变量（R-S5-1）；B 必须吸收；每个主状态必须有进入/离开边（无不可达状态），`CLOSE/RELOAD` 全局转移。
- **机检**：可达性分析；无不可达/死状态；表↔图一致。

### R-S5-5 Focused 语义
- **裁决**：`Focused` 是**主状态**（表示"有取景焦点"），但**不得改变 `frame.focus`**；UI 选择/hover 仍为瞬态、不进 VM；`focus` 丢失恢复=最近祖先/根（A 的栈回溯保留）。
- **机检**：`Focused` 转移不改 frame.focus；selection 不进 VM。

### R-S5-6 栈与重开
- **裁决**：`MAX_STACK=50`；BREADCRUMB_TO 截断中间栈（保留 target 前项）；重开 KB/应用只恢复 `level0` frame + `mode` + `dimension`（不恢复深栈，D-ST-07）；stack 去重=同 `(focus,level,dimension,mode)` 不重复 push。
- **机检**：栈上限/去重；重开只恢复白名单字段。

### R-S5-7 全展开与 drill
- **裁决**：`mode=full` 与 drill/back 正交；drill 不强制退出 full；请求 S4 full 时需满足 S4 的 candidate 超集前提；失败按 R-S5-3 事务化。
- **机检**：full 下 drill 保持 mode；失败 diff=0。

### R-S5-8 并集与 P2
- A 的状态集/Loading/Degraded/Stale/RelationDeepened/origin/edition/a11y/G6 为主干；B 的严格 VM/focus 一跳/维度可 back 并入；
- P2 合并：frame_id/edition 与 S4 frame_spec 对齐；复合状态优先级；`Focused` vs `frame.focus` 命名；BREADCRUMB_TO 截断；重开白名单；去抖统一 300ms；EmptyNoSemantic 恢复转移；G6 字段统一；URL/书签 schema 归 S6a/后续。

## 2. 修订轮任务

**A-v2**：落实 R-S5-1..R-S5-8；重画 S5a（正交变量、补全边、表↔图逐条一致）；更新 `S5-nav-proposal-A-v2.md`。
**B-v2**：落实 R-S5-1..R-S5-8（吸收 A 主状态、移除不可达 FullExpanded、维度可 back、事务化）；产出 `S5-nav-proposal-B-v2.md` + `S5-objections-v2.md`。
**SE 工程校核（task-317）**：等 v2 齐后执行（含 S5a 复验）。

## 3. S5 冻结门禁

1. A-v2/B-v2 关闭全部 R-S5 与 P1（逐条证据）；
2. SE 工程校核 + S5a PASS；
3. Lead 独立机检（状态可达/闭包/表↔图、frame 不进 VM、点击语义、drill/back、维度可 back、事务化、NEW_HOP、focus 生命周期、重开白名单）；
4. 与 S0–S4 无冲突；
5. 冻结 `S5-nav-v1.md` 并写决策。

## 4. 边界

不写产品代码；不改 S0–S4 冻结稿；S5 冻结前不开工实现；所有修订保留旧版。
