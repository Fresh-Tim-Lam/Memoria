# S5 章程：导航状态机（点击、下钻、返回、新一跳、焦点生命周期）

> **依据（不可改写）**：`multilevel-graph-vision.md`（U-1..U-35）。
> **上游冻结**：`S0-terms-v1.md`（`241b1e1e…`）、`S1-dimensions-v1.md`（`6676c71d…`）、`S2-clustering-v1.md`（`92bb0041…`）、`S3-visual-v1.md`（`0ca4ea0e…`+`S3-ADDENDUM-1`）、`S4-render-v1.md`（`2576f6c8…`），**不得违反**；逐议项（U-34）。
> **状态**：S5 章程 V1（Lead 起草）。本场冻结前不写产品代码。
> **日期**：2026-11-03（Asia/Shanghai）。

## 1. 目的

把「点击一个簇 → 深入一层；返回；新一跳；焦点/选择」落成**可机检的导航状态机**（`GraphNavFrame` + 转移表 + 不变量），
并冻结 S5 与 S4（取景请求）、S3（事件）、S1/S2（维度/簇）的接口边界。S5 是「点击后真的深入一层」的实现层。

## 2. 不在范围

- 取景/presence 计算（S4 已冻结；S5 只构造 `frame_spec` 并消费结果）；
- 渲染视觉（S3 已冻结）；
- 数据契约（S6；S5 给需求）；
- 键盘/读屏细节视觉（S3 已给 a11y 基线，S5 只定义语义动作）。

## 3. 议项清单（逐项裁决；一项未裁决不得跳下一项）

每项产出：定义/规则、机检条件、反例、边界用例、U 映射、建议裁决、证据等级；S5a 另出状态图。

| 编号 | 议项 | 必须回答 |
|---|---|---|
| S5-1 | 导航状态与边界 | `GraphNavFrame` 字段（focus/level/hop/new_hop/dimension/history）；只在 Presentation，不进 VM（S0-9/D-4）；S5 只发 `frame_spec` 给 S4 |
| S5-2 | 状态机全表 | 状态集合（如 `Idle/Focused/HierarchyDrilled/RelationExpanded/FullExpanded/EmptyNoSemantic`）；转移表（事件×状态→新状态）；不变量；非法转移 fail-closed |
| S5-3 | 点击语义 | `nodeClick(kind)`：kp→跳编辑器（U-20）；cluster→drill（进入下一层）；edgeClick/backgroundClick 语义；不混用；S3 事件→S5 动作映射 |
| S5-4 | drill/back/面包屑 | drill：level+1、focus=簇、hop 重置、入栈；back：弹栈恢复（focus/level/dimension）；重新打开时状态恢复；栈上限/去重 |
| S5-5 | `EXPLICIT_NEW_HOP` | 唯一显式 2 跳动作；允许条件（A 维、有 focus、hop_budget 允许）；效果；幂等/重复触发；与 default 路径隔离 |
| S5-6 | 焦点/选择生命周期 | focus vs selection 区别；selection 何时清空（drill/back/dimension switch）；焦点丢失/删除/重聚类后如何恢复；默认 frame（无 focus 时的视图） |
| S5-7 | 维度切换 | 切换维度：hop 重置、focus 保留/清空、history 处理；与 S1 单维度/组合槽位一致；未知维度 fail-closed |
| S5-8 | 全展开开关 | 与 drill/focus 正交；开关状态持久化；切换不破坏 focus；与 S4 subset 契约一致 |
| S5-9 | 与 S4 接口 | `frame_spec` 构造（focus/level/hop/new_hop/dimension/budget）；同输入同 frame；S5 不计算 presence；`S4_BUDGET_INVALID` 的处理（回退/提示） |
| S5-10 | 与 S3 事件契约 | 最小事件集映射；payload；渲染器无导航；事件去重/防抖；hover 不改变导航状态 |
| S5-11 | 与 S1/S2 一致 | H 下钻 vs A 扩展的状态差异；只读 S2 run；不重算簇；无簇时 `EmptyNoSemantic` 状态与恢复 |
| S5-12 | 可访问性/持久化/度量 | 键盘等价动作（Enter/Space/Escape/Backspace/方向键）、aria-live 导航播报、导航历史与 URL/书签（如适用）、性能（frame 切换延迟）、G6 导航指标 |

## 4. 预注册判据（会前写死）

1. 状态机可机检：状态/事件/转移表闭包；非法转移 fail-closed；无不可达/死状态；
2. `GraphNavFrame` 字段冻结且**不进 VM**；S5 只发 `frame_spec`，不计算 presence；
3. 点击语义按 `kind` 唯一；kp 跳编辑器、cluster 下钻；不混用；
4. drill/back 是可逆栈（同路径可恢复 focus/level/dimension）；hop 重置语义明确；
5. `EXPLICIT_NEW_HOP` 唯一且与默认路径隔离；重复触发幂等；
6. 维度切换/全展开与 focus 交互明确；未知维度 fail-closed；
7. 与 S4 的 `S4_BUDGET_INVALID`/`candidates(full)` 契约一致；与 S3 事件/VM 纯度一致；
8. 两份独立提案（A/B）差异逐条列出并裁决；
9. 覆盖矩阵（U-1/4/7/8/9/15/20/22/24/26/29 + S0–S4 相关）无缺失；
10. SE 工程校核 + **S5a 状态图**（同版本 mermaid `PARSE_OK`）；
11. 不写产品代码、不改契约、不 commit。

## 5. 输入与预读

- 原话：`multilevel-graph-vision.md`；
- 上游冻结：S0/S1/S2/S3/S4 五份 v1 + FREEZE-RECORD + S3-ADDENDUM-1；
- 工程：`ENGINEERING-PLAN.md`（含 S4 ST-05）、四份 engineering-check；
- 只读代码锚：`app.js` 图谱点击入口/`graph-engine.js`/`graph-view-*`（现状证据，非设计结论）。

## 6. 角色与交付

| 角色 | 成员 | 交付 |
|---|---|---|
| 主办研究（提案 A） | `gm-seminar-researcher` | `S5-nav-proposal-A.md` + 证据 |
| 独立复核（提案 B + 异议） | `gm-seminar-verifier` | `S5-nav-proposal-B.md` + `S5-objections.md` |
| 软件工程专家（含 S5a 状态图） | `graph-se-architect` | `S5-engineering-check.md` + `ENGINEERING-PLAN.md` 状态图增量 |
| 并集与裁决 | Lead | `S5-RULINGS.md` → `S5-nav-v1.md`（冻结候选） |

## 7. 冻结门禁

1. A/B 独立完成 + 差异清单 + 异议关闭（P0/P1 逐条证据）；
2. SE 工程校核 PASS（状态机/`GraphNavFrame`/frame_spec/事件/S5a 状态图、与 S0–S4 一致）；
3. Lead 独立机检（状态闭包、非法转移、frame 字段、点击语义、drill/back、new_hop、focus 生命周期、VM 纯度）；
4. 与 S0–S4 无冲突；
5. 满足后冻结 `S5-nav-v1.md` 并写决策；否则回修订轮。

## 8. 变更控制

- 冻结后加状态/事件/动作：S5 修订 + 决策；删/改状态机语义/点击语义/new_hop/frame 字段：重开 S5；
- 本场无产品代码；S0–S6 全冻结前不开工实现。
