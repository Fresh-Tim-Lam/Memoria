# S0 裁决（Lead）：并集、异议处置与冻结门禁

> **依据（不可改写）**：`docs/design/multilevel-graph-vision.md`（U-1..U-35）；
> `docs/design/multilevel-graph-seminar-agenda.md` V0.2；`S0-charter.md`。
> **输入**：提案 A `S0-terms-proposal-A.md`（sha `0fddb4c6…`）、提案 B `S0-terms-proposal-B.md`（sha `48e29f3d…`）、
> 异议 `S0-objections.md`、SE 校核 `S0-engineering-review.md` 与 `ENGINEERING-PLAN.md`。
> **状态**：S0 **未冻结**；A 必须按 §3 修订后复评。本文件即修订轮的唯一裁决依据。
> **日期**：2026-11-02（Asia/Shanghai）。

## 0. Lead 亲自复核过的关键点（不是转述）

| 复核项 | 动作 | 结论 |
|---|---|---|
| P0-1：A 把关联维度窄化为只走语义边 | 读 A L139/L170/L174-176 与 U-10 原话 | **成立**：A 的 `E_sem(D)` 只允许语义边；U-10 原话明确含「包含关系、引用、语义关联等等」⇒ 必须改为 `E_relation(D)` |
| P0-2：A 的 `kind: kp|cluster|bridge` | 读 A L306 与 U-19 原话 | **成立**：U-19 只允许「知识点 / 代表连通子图的节点」两类；bridge 只能作为 role/state |
| P1-1：层内划分 vs U-21 多归属 | 读 A L160/L244 与 U-21 | **成立**：需把 partition 限定在「同一 (level, 视图族)」内，跨视图族/维度允许重叠 |
| P1-2：A 全展开 `edges=all_data_edges` | 读 A L223/L274 与 U-27 | **成立**：兼容区也须走 `present(e,ctx)`，否则同一数据出现两种语义读法 |
| P1-3：A T3「决策绑定」不可机检 | 读 A L41/L65（自标本项目假设） | **成立**：T3 降级为消费者准入清单/评测准入，不作语义定义必要条件 |
| P1-4：A 缺 stable cluster_id | 读 A S0-4 与 B L164-165 | **成立**：采纳 B 的稳定性要求，但按 D-2 调整（见 §2） |
| SE S0-6「边存无」无承载 | 读 SE review §1.2 / §9.4 | **成立**：冻结稿必须写死 ctx + presence 三值 + 缺席原因 rule_id |
| SE 三张图 Mermaid 可解析 | 核 SE 报告 `PARSE_OK` 声明 | 采纳为**计划级**证据；冻结前须按 G-1 用**同版本** mermaid 复验 |
| B 的 U-10 修正 | 读 B L97/L164-165 与 B S0-5 R1 | **成立**：B 已用 `E_relation(D)`，覆盖正确；B 仍有自身 P1 需补 |

## 1. 逐议项裁决（S0-1..S0-12）

> 记号：**采纳 A** / **采纳 B** / **并集**；「修订项」是 A/B 下一版必须落进去的内容。

| 项 | 裁决 | 修订项（A 为主） |
|---|---|---|
| S0-1 语义 | **并集**：A 的 T1 可命名 / T2 可真假 / T4 非偶然 + B 的现有可核字段闸门（type+provenance+assertion_source / contain_kind / curated_by·at）；T3 降级为「消费者准入清单/评测准入」，不作定义必要条件 | A 改写 S0-1；把 T3 移出定义；写明字段闸门与三段标签（semantic/structural/navigation） |
| S0-2 层次与粒度 | **采纳 A 的划分形式化 + 限定作用域**：partition 只在「同一 (level, 视图族)」内要求；最小粒度机检伪代码必须给出（叶子 kind=kp、叶子 id ⊆ K、无 cluster 叶子；cluster 展开到底全为 KP） | A 补机检伪代码 + partition 作用域 + 与 S0-7 的接口 |
| S0-3 维度 | **采纳 A 的槽位模板 + 修正关联维度边源**：association 的挂接/计跳边 = `E_relation(D)`（contain(structural/semantic)、reference、semantic extend 等，U-10），semantic/structural 仅作**标签**；reserved 槽位只登记、不得进渲染分支 | A 把 `E_sem(D)` 改 `E_relation(D)`；补开放槽位登记格式（S0-3 修订） |
| S0-4 簇 | **并集**：A 的 μ/β 公式 + B 的稳定身份；按 D-2 采用「run-scoped cluster instance id + stable cluster_key」 | A 补 stable 身份（见 D-2）；删「每层簇族必须互斥完备」的全局措辞，改为视图族内 |
| S0-5 一跳 | **B 的 U-10 覆盖 + A 的方向定义**：恰好一条 `E_relation(D)` 边、按 dir(D)、不闭包、跨维重置；只渲染端点+边，不带背后子图（U-17） | A 改 `E_relation(D)`+方向；B 补 dir(D) 与「跨维重置」 |
| S0-6 选择性渲染/存无 | **A 的边状态枚举 + B 的 present 唯一判据 + SE 的 ctx/presence 三值/rule_id**；全展开也走 `present(e,ctx_full)`；视图缺席 ≠ 数据缺席 | A 重写 S0-6：`presence ∈ {shown,suppressed,unknown}` + `ctx` + `rule_id`；full_expand 不得 `all_data_edges` |
| S0-7 多归属 | **并集**：A 的 Role/provenance + B 的「membership 多对多、无单值 parent」；删除「层内单归属」硬约束，改为「同一视图族内单归属，跨视图族/维度多归属」；S0 不设上限（S2/S6 定） | A 删除层内单归属硬约束；B 保留多对多；两者都写「成员关系 ≠ 视图出现」 |
| S0-8 默认 vs 全展开 | **并集**：A 的焦点保持/映射 + B 的同 DataSource/同 Renderer/同 present 参数退化；禁止第二数据源；开关是 Presentation 正交区 toggle | A 把 full 改 present 化；B 补焦点映射 |
| S0-9 渲染接口 | **A 的字段/能力/事件 + B 的 kind 约束**：`kind ∈ {kp,cluster}`；bridge 用 `role/state`；2D/3D 同签名后端；渲染器不取数、不做语义判断；`modeToggle/navigateBack` 不进渲染器契约（归导航服务） | A 改 kind；移出导航/模式；B 补 capabilities/事件清单 |
| S0-10 agent 边界 | **并集**：A 的三层角色表（KP 设计主导 / 语义可写但须证据+审计、不得自动推断 semantic / 取景设计执行不做渲染）+ B 的确定性取景服务 | A/B 各自补对方要点；写死「agent 不得直接改渲染状态」 |
| S0-11 不做什么 | **并集**（约 15 条）：A 13 条 + B 的「不把 cluster/membership 写产品 sidecar」「不新增产品拓扑段」等；每条绑定执行点 | A/B 合并成一份清单（Lead 并集由 A 起草） |
| S0-12 术语映射 | **A 的映射表 + B 的三段（DataSource→ViewModel→Renderer）与 present/semantic_edges 映射**；冲突项写迁移/回滚 | A 补 present/semantic_edges/三段；B 补旧术语覆盖 |

## 2. 跨议题裁决（D-1..D-5，SE 提请）

- **D-1 层次 vs 多归属**：partition 只约束「同一 (level, 视图族)」；跨层次嵌套、跨维度/跨视图族允许重叠。**采纳 A 形式化+限定作用域**。
- **D-2 cluster 身份**：簇实例 id = `cluster_run_id + 局部序号`（run 可追溯）；另存 `cluster_key = sha256(sorted(member_canonical_ids) + algorithm_id + version + params_hash)` 作可复算/去重键。**不采纳**「cluster_id 直接=内容哈希」——成员一变就会让 curation/审计引用失效。curation 引用必须同时记录 run 与 key。
- **D-3 membership 持久化**：S0 **不允许**把簇/成员关系写入产品 sidecar 或新增产品段；semantic 边的 curation overlay 仍按 v0.3 契约走。未来簇 curation 必须等 S6 契约，S0 只登记需求。
- **D-4 ViewModel 纯度**：ViewModel **不含**导航状态与模式开关（A 原字段需移出）；导航状态单独由 S5 状态机管理；全展开是 Presentation 层参数。
- **D-5 维度组合**：v1 **同一视图只激活一个维度**；维度组合留开放槽位，S1 再裁。

## 3. 修订轮任务（A/B 各自独立改，不许合并成一份）

**A 修订（主办研究）**：按 §1「修订项（A 为主）」+ D-1..D-5 改：
1. P0-1：`E_sem(D)` → `E_relation(D)`（S0-1/S0-3/S0-5 全改）；
2. P0-2：ViewModel `kind ∈ {kp, cluster}`，bridge 改 `role/state`；
3. P1-1：S0-2 补机检伪代码 + partition 作用域；
4. P1-2：full_expand 走 `present(e,ctx_full)`，不得 `all_data_edges`；
5. P1-3：T3 降级为消费者准入清单；
6. P1-4：补 D-2 的 run-scoped id + cluster_key；
7. SE S0-6：补 ctx + presence 三值 + rule_id；
8. 并集 B 的 U-10 关系源、三段架构、present 映射；D-4/D-5 落实到字段。
**交付**：`S0-terms-proposal-A-v2.md`（不改旧文件，保留审计链）。

**B 修订（独立复核）**：补 P1-1 机检伪代码；补 dir(D)/跨维重置；补焦点映射；按 D-4/D-5 调整 ViewModel；补 capabilities/事件清单；**不得**照抄 A v2（保持独立判断，差异清单更新到 `S0-objections-v2.md`）。

**SE 冻结前机检**：在 A-v2/B-v2/异议-v2 齐后，按 `S0-engineering-review.md` 的 M-1..M-12 做冻结前机检；用**同版本** mermaid（记录版本）复验三张图；产 `S0-freeze-check.md`（逐项 PASS/FAIL + 证据），FAIL 则退回 A/B。

## 4. S0 冻结门禁

1. A-v2 / B-v2 / 异议-v2 三份齐，且 P0-1、P0-2、P1-1..P1-4 全部关闭（逐条证据）；
2. SE 的 M-1..M-12 全 PASS；三张图复验 PASS；
3. Lead 复跑机检并抽查 3 条关键判定（E_relation、kind 约束、present 唯一）；
4. 覆盖矩阵 U-1..U-35 无缺失；S0-charter §3 的 12 议项都有裁决；
5. 满足则产出 `S0-terms-v1.md`（冻结稿）并写入决策；否则回修订轮。

## 5. 边界

- 本裁决不写产品代码；S0 冻结前不进入 S1；A/B/SE 均不得改 `src/**`。
- 所有修订必须保留旧版文件（版本化），禁止覆盖历史。
