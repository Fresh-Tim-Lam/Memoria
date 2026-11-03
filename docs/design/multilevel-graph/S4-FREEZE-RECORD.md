# S4 冻结记录（Freeze Record）

> **冻结对象**：`docs/design/multilevel-graph/S4-render-v1.md`（12 条规范 + R-S4-1..R-S4-10 + U 覆盖矩阵）。
> **冻结时间**：2026-11-03T20:58+08:00（Asia/Shanghai）。
> **决策**：`dec-20261103-a8070cc5`（Lead；S0 `dec-20261102-a6af89e1`、S1 `dec-20261103-35844b56`、S2 `dec-20261103-ec432887`、S3 `dec-20261103-def8efcf` 已冻结）。
> **状态**：**已冻结**。S5 可开；S0–S6 冻结前仍不写产品代码。

## 1. 冻结产物与身份

| 产物 | 角色 | sha256 |
|---|---|---|
| `S4-render-v1.md`（**冻结稿最终态**） | S4 唯一规范来源 | `2576f6c8472ce5175f6cb1fd878f782e2c128bde675b8925981ee0d63a3f5c94` |
| `S4-engineering-check.md` | SE 工程校核（M-S4-1..12 + X-ADD） | `e189f79f…` |
| `S4-render-proposal-A-v2.md` | 证据链（主办研究） | `634cb9cf…` |
| `S4-render-proposal-B-v2.md` | 证据链（独立复核） | `048b9909…` |
| `S4-objections-v2.md` | 差异/异议 | `a8f10629…` |
| `S4-RULINGS.md` | Lead 裁决（R-S4-1..8） | `efa597aa…` |
| `S3-ADDENDUM-1.md` | VM 节点 presence/rule_id 字段扩展 | `6007e47a…` |
| `ENGINEERING-PLAN.md`（S4 增量） | ER-05/DF-05/ST-05 | `7b66355f…` |

**冻结轮次**：SE 首轮 11 PASS / 1 FAIL（subset 缺 `candidates(full) ⊇ candidates(default)` 前提）；Lead 补前提与机检四项后 SE 复跑 **12/12 PASS、M_fail=[]**；Lead 独立机检（12 条款、R-S4-1..10、F={focus}、无隐式 2 跳、MANDATORY K=2、rule_id、排序键、subset 构造、S3 addendum、候选载体）PASS。冻结身份取最终态 sha `2576f6c8…`。

## 2. S4 冻结了什么（一句话版）

1. **S4 是唯一裁剪者**：只改 `presence ∈ {shown,suppressed,unknown}`，不改事实/type/label/contain_kind；Renderer 只校验/渲染；
2. **focus 一跳**：`F={focus}`，`one_hop(F)` = 恰好一条 `E_relation(D)` 边；不闭包、不带背后图；端点 kind∈{kp,cluster}；
3. **禁止隐式 2 跳**：tier2 只含基座+H 同层；`max_hop(shown) ≤ hop_budget`（默认 1）；2 跳只由 S5 `EXPLICIT_NEW_HOP`；
4. **最小必选集**：A={focus}；H={focus}+first K children；v1 `K=2`（S8 可调）；先保 MANDATORY，其余 `suppressed+rule_id`；仅 MANDATORY 超预算 `S4_BUDGET_INVALID`；S8 保证 `max_nodes ≥ 1+K`；
5. **presence/rule_id 载体**：全部候选节点/边逐条 presence+rule_id（VM 节点字段由 `S3-ADDENDUM-1` 扩展）；`rule_id` 11 类；unknown 仅 4 类触发、unknown≠无关系；
6. **排序键**：`(tier, hop, relation_class, label_rank, canonical_id)`；semantic<structural<navigation<reference；确定性；
7. **维度接入**：`frame_spec.dimension_id`；H 无 hop/contain 下钻；A relation min/hop 1-2；维度只改 presence；未知 fail-closed；
8. **drill**：新 frame（level+1、focus=簇、hop 重置）；只读 S2 run、不重算簇；跨层非 H 边 suppressed；多归属按 `view_family`；
9. **全展开 subset 构造**：同一 Admission/present；`relation_scope=candidate_scope`；前提 `candidates(full) ⊇ candidates(default)`；full reserved(default shown)+同排序填剩余；`budget_full ≥ budget_default`；不成立 ⇒ `S4_BUDGET_INVALID`/显式回退 default；subset 由构造保证；
10. **S5 边界**：S4 纯取景；focus/selection/nav 不进 VM；事件→S5；new_hop 仅 S5；
11. **与 S1/S2 一致**：presence 不改事实；A 不改变簇；run/簇不进 VM；无簇不伪造；
12. **G6 度量**：candidate/mandatory/shown 计数、rule_id 直方图、max_hop、closure/behind=0、deterministic sha、subset_ok、budget、candidate_scope；数值 S8。

## 3. 机检与证据

- SE M-S4-1..12 + X-ADD：`M_fail=[]`、全 PASS；subset 修复证据在 `S4-engineering-check.md`；
- 同版本 mermaid（vendored，sha `9198f632…`）：PLAN 15 图 + 报告 3 图全部 `PARSE_OK`；
- 与 S0–S3 一致性：S0-5 一跳、S0-6 presence、S0-8 无第二数据源、D-3、S1 H/A/D-4、S2 run/簇/多归属/无簇、S3 R-S3-2/R-S3-9/VM 白名单+ADDENDUM-1 全 PASS；
- Lead 独立机检 PASS（见 §1）。

## 4. 未关闭项（不阻塞冻结）

- O-S4-2..11：S3-ADDENDUM 登记、R-S4-9/10 补入 RULINGS、rule_id 命名统一、H 叶焦点 min、cluster 焦点 A 一跳边界、G6 canonical/字段、v1 §2 旧标注与 §1 编号重复（以 §1 为准）。

## 5. 变更控制

- 加 rule_id/优先级/阈值：S4 修订 + 决策；删/改一跳/预算归属/subset/presence 语义：重开 S4；
- S3 节点白名单扩展以 `S3-ADDENDUM-1` 记录，不改 S3 核心；
- 冻结身份 = 本记录 + `S4-render-v1.md`；未记录的字节改动视为破坏冻结。

## 6. 下一步

- S5（导航状态机：click/drill/back/new-hop/focus 生命周期、`EXPLICIT_NEW_HOP` 动作、GraphNavFrame）；S5 必须复用 S4 `frame_spec`/presence 契约；
- 产品实现仍等 S0–S6 冻结。
