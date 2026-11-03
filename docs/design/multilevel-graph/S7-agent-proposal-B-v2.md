# S7 agent 如何使用图谱提案 B-v2（独立复核方修订版）

> **依据（唯一裁决依据）**：`docs/design/multilevel-graph/S7-RULINGS.md`（R-S7-1..R-S7-6）+ `S6-ADDENDUM-1.md`；上游冻结 `S0-terms-v1.md`（`241b1e1e…`）、`S1-dimensions-v1.md`（`6676c71d…`）、`S2-clustering-v1.md`（`92bb0041…`）、`S3-visual-v1.md`（`0ca4ea0e…`）+ `S3-ADDENDUM-1`、`S4-render-v1.md`（`2576f6c8…`）、`S5-nav-v1.md`（`7f4c4515…`）、`S6-contract-v1.md`（`40f12e5f…`）+ `S6-ADDENDUM-1`，不得违反。
> **输入**：B v1（`2293ddd3…`）、A v1（`2508e8bc…`）、`S7-objections.md`（`65f65bf8…`）。A-v2 写作时尚未落盘；本文件先独立完成（完成后才对照 A-v2，见 `S7-objections-v2.md`）。
> **性质**：独立复核方修订提案；不覆盖旧版；不写产品代码/契约；未 commit。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S7-RULINGS/S0–S6 冻结。
> **日期**：2026-11-03（Asia/Shanghai）。

---

## 0. B-v2 变更表（相对 B v1；逐条落 R-S7）

| # | 位置 | B v1 | B-v2（依据） | 类型 |
|---|---|---|---|---|
| 1 | S7-3/S7-5 | 工具 `graph.focus/.../path?/query?` | **5 个 snake_case 只读工具**：`graph_focus/graph_explain_edge/graph_expand_cluster/graph_summary/graph_resolve_ref`；**v1 无 path/query**（future 另开修订）（R-S7-1/R-S7-3） | 修正 |
| 2 | S7-2/S7-4 | AgentView 边含 suppressed，解释口径未定 | **`ViewResponse.edges[]` 只含 shown**；suppressed/unknown 只给 `suppressed_summary{rule_id:count}`+`rule_histogram`；`graph_explain_edge` 受控解释 suppressed（R-S7-2） | 修正 |
| 3 | S7-5/S7-7 | 错误表缺失/未映射 S6；引用无解析入口 | **错误码表逐码映射 S6 + S6-ADDENDUM-1**（legacy/i18n/severity/audit_id）；新增 `graph_resolve_ref` 只读解析（R-S7-1/R-S7-3） | 并集 |
| 4 | S7-2/S7-7 | `underlying_edge_count` 等 | **字段统一**：`view_model_id/frame_id(仅审计)/aggregate_count/member_count`；不新增同义字段（R-S7-4） | 修正 |
| 5 | S7-5 | 幂等定义模糊；expand 可能碰 S5 | **幂等键 `(tool,args,edition,budget)`**；`graph_expand_cluster` 不改 S5 nav/stack；写请求 `GRAPH_WRITE_FORBIDDEN`（R-S7-5） | 修正 |
| 6 | S7-4/S7-12 | 默认/G7 归属简 | 默认 `max_tokens=4000/max_nodes=200`（S8 可调）；G7 引用 G6、不复制事实；S9/S10 边界（R-S7-6） | 确认 |

---

## 0.1 覆盖矩阵（U + S0–S6）

| U# | 落点 | U# | 落点 |
|---|---|---|---|
| U-2/U-3 | agent 使用=S7-2/S7-3 | U-6 | 簇摘要=S7-4 |
| U-10/U-11 | 维度=S7-10 | U-12/U-13 | 查询/证据=S7-3/S7-7 |
| U-14 | 生成/引用=S7-7 | U-15 | 一跳=S7-3 |
| U-17 | 不带背后图=S7-3 | U-19 | KP/簇=S7-3 |
| U-27 | presence/存无=S7-2/S7-4 | U-32 | token/预算=S7-4/S7-12 |
| S4/S5 | focus/nav=S7-3/S7-9 | S6 | schema/错误/审计=S7-5/S7-7 |

---

## S7-1 定位与边界（只读 + AgentQuery 读路径）

**规则**：v1 agent **只读**；只能经 **AgentQuery 服务/5 个只读工具** 读 View/解释/引用；不得直接读 `DataSource` raw 边、文件系统、缓存字节、sidecar/manifest/registry；不写任何图谱状态。
**读路径（唯一）**：
```
agent → graph_* 只读工具 → AgentQuery → DataSource(只读投影)/GraphView(S2 run)/S4 Admission/resolve index
                                    ↘ 不得绕过 AgentQuery 读 raw file/cache/sidecar
```
- 事实只来自 DataSource；View/VM/缓存是派生；导航 frame 是 Presentation；agent 不持有/修改 S5 导航。
- 写路径不存在于 S7；curation/写只走 S10 工具 + 审计/人工确认。
**机检**：工具只读；无文件路径/写参数；AgentQuery 是唯一读入口；无 raw DataSource 边直读；无 sidecar 写；audit。
**反例**：agent `cat` 文件/读 sidecar；直接读 DataSource.edges；写 registry；把缓存当事实。
**边界**：旧 KB/无 sidecar；只读权限；S10 写后 edition；多 KB。
**U 映射**：U-2、U-3、U-29、U-34。
**建议裁决**：冻结 v1 只读/AgentQuery 唯一读路径/不写/不绕 DataSource。
**证据等级**：A（S6-1/S6-10；S0 D-3）+ R。

---

## S7-2 agent 可见层（View + presence 解释）

**规则**：agent 默认看 **View + presence/rule_id 解释 + 引用**；**不直接看 raw 边**，不把 VM/缓存当事实。`ViewResponse` schema：
```
ViewResponse = {
  view_model_id,                    # S6 VM（唯一视图身份）
  frame_id?,                        # 仅当由导航帧触发；仅审计，不作事实
  level_id, view_family_id, dimension_id, data_state,
  nodes[{id,kind∈{kp,cluster},label,role:"member",member_count?,
         presence?,rule_id?,kp_ref?{kp_id,file,line,anchor},cluster_ref?{cluster_id,run_id,cluster_key}}],
  edges[{id,type,contain_kind?,label?,presence,rule_id?,
         source,target,aggregate_count?,state?}],   # 只 presence=shown
  suppressed_summary{rule_id:count}, rule_histogram,
  counts{node,edge,cluster}, presence_histogram, coverage,
  truncated, omitted, token_estimate, edition_sha
}
```
- `edges[]` **只 shown**；suppressed/unknown 不列原始边，只给 summary/直方图；`graph_explain_edge` 逐条受控解释。
- `data_edge_ids` 不可见；`aggregate_count` 为 S6/S4 字段；不把 shown 当“事实存在”。
**机检**：schema/白名单；edges 全 shown；summary/直方图；presence/rule_id；无 data_edge_ids；VM 不作事实。
**反例**：edges 含 suppressed 原始边；把 VM 当 DataSource；cluster label 当 KP 证据；shown 当事实。
**边界**：no_semantic；空 VM；full；unknown 多；cluster 无 anchor。
**U 映射**：U-2、U-6、U-13、U-14、U-27。
**建议裁决**：冻结 ViewResponse/edges shown/摘要/解释分离/VM 派生。
**证据等级**：A（S3 VM/S4 presence；S6-5；R-S7-2）+ R。

---

## S7-3 查询接口（5 工具；focus 一跳/expand 一层）

**5 个只读工具（R-S7-1/R-S7-3）**：
```
graph_focus{level_id, view_family_id, dimension_id, focus_id, hop=1, mode=default,
            budget{max_tokens,max_nodes}} -> ViewResponse
graph_explain_edge{edge_id, frame_id?} -> EdgeExplanation
graph_expand_cluster{cluster_id, run_id, level_id, dimension_id?, budget} -> ViewResponse
graph_summary{level_id, view_family_id?, dimension_id?} -> SummaryResponse
graph_resolve_ref{ref{kp_id?|file+line|anchor?}} -> RefResolution
```
- `graph_focus`：H 当前层视图 / A `F={focus}` 恰好一跳；默认 hop=1；**无隐式 2 跳**；A 无 focus → `GRAPH_TOOL_INPUT_INVALID`（detail focus_required）。
- `graph_expand_cluster`：只 drill 一层（S5 CLICK_CLUSTER 的只读子集；**不改 S5 nav/stack**）；不递归/不闭包。
- `graph_explain_edge`：可解释 suppressed/unknown 的 `{presence,rule_id,claim_type,evidence}`；不返回背后图/批量隐藏边。
- `graph_resolve_ref`：解析 `kp_id/file+line/anchor`，返回 `{resolved,kp_id,file,line,anchor,stale,claim_type}`；**解析走 DataSource/索引，不读文件系统**。
- **v1 无 `graph_path`/`graph_query`**；未来多跳必须显式 `allow_two_hop` + S5 `EXPLICIT_NEW_HOP`，另开 S7 修订；不得夹带。
**机检**：工具集恰好 5；名称 snake_case；无 path/query；focus 一跳；expand 一层；resolve 只读；errors。
**反例**：自动 2 跳；expand 递归；path/query 夹带；explain 返回背后图。
**边界**：A 无 focus；cluster 无子；edge 不在 frame；ref  stale；no_semantic。
**U 映射**：U-10、U-11、U-15、U-17、U-19、U-22。
**建议裁决**：冻结 5 工具/无 path/focus 一跳/expand 一层/resolve_ref。
**证据等级**：A（S4 R-S4-1/2；S5；R-S7-1/R-S7-3）+ R。

---

## S7-4 展开与 token 预算（只 shown + 显式截断）

**规则**：
- 默认 `max_tokens=4000`、`max_nodes=200`（S8 可调）；S4 budget 同源。
- 超预算：先降层级摘要（cluster label/member_count/coverage），再显式 `truncated=true`、`truncated_reason∈{token_budget,budget_nodes}`、`omitted{node,edge}`；**禁止静默截断**。
- `suppressed_summary{rule_id:count}` + `rule_histogram`；`unknown_count`+reasons；不列 suppressed 原始边。
- `token_estimate` 可复算；`coverage` 显示（no_semantic=0）。
**机检**：默认值可配；truncated/omitted 显式；summary/直方图；不静默；token_estimate。
**反例**：超预算静默；把 suppressed 当无；unknown 省略；summary 隐藏 coverage=0。
**边界**：budget 0；空视图；无簇；full；大图。
**U 映射**：U-3、U-13、U-16、U-27、U-32。
**建议裁决**：冻结预算/摘要/显式截断/suppressed-unknown 解释。
**证据等级**：A（S4 budget；S3-11；S6-6；R-S7-2/R-S7-6）+ R。

---

## S7-5 工具面/错误码/幂等/审计

**工具 schema/返回**：5 个只读工具（S7-3）；返回 envelope：
```
{ok, data, meta{view_model_id, frame_id?, budget_used, truncated, edition_sha},
 errors[], audit_id, idempotency_key}
```
**错误码表（逐码映射 S6 + S6-ADDENDUM-1）**：
| S7 canonical | 来源 | legacy_code | severity | i18n | audit_id |
|---|---|---|---|---|---|
| `GRAPH_TOOL_INPUT_INVALID` | S6-ADDENDUM-1 | `GRAPH_INTERNAL` | error | `graph.tool.input_invalid` | required |
| `GRAPH_TOOL_BUDGET_EXCEEDED` | S6-ADDENDUM-1 | `GRAPH_BUDGET_INVALID` | warn | `graph.tool.budget_exceeded` | required |
| `GRAPH_ANCHOR_STALE` | S6-ADDENDUM-1 | `GRAPH_EDITION_STALE` | warn | `graph.tool.anchor_stale` | required |
| `GRAPH_RETRIEVAL_UNAVAILABLE` | S6-ADDENDUM-1 | `GRAPH_INTERNAL` | error | `graph.tool.retrieval_unavailable` | required |
| `GRAPH_WRITE_FORBIDDEN` | S6-ADDENDUM-1 | `GRAPH_INTERNAL` | error | `graph.tool.write_forbidden` | required |
| `GRAPH_TOOL_AUDIT_FAILED` | S6-ADDENDUM-1 | `GRAPH_INTERNAL` | error | `graph.tool.audit_failed` | required |
| `GRAPH_FRAME_ID_INVALID` | S6 | — | error | `graph.error.frame` | required |
| `GRAPH_PRESENCE_INVALID` | S6 | — | error | `graph.error.presence` | required |
| `GRAPH_BUDGET_INVALID` | S6 | — | error | `graph.error.budget` | required |
| `GRAPH_SUBSET_VIOLATION` | S6 | — | error | `graph.error.subset` | required |
| `GRAPH_EDITION_STALE` | S6 | — | warn | `graph.error.edition` | required |
| `GRAPH_DIM_UNKNOWN`/`GRAPH_DIM_NOT_ACTIVE` | S6（S1） | `DIM_*` | error | `graph.error.dimension` | required |
| `GRAPH_INTERNAL` | S6 | — | error | `graph.error.internal` | required |
- 未知码 ⇒ `GRAPH_INTERNAL`；所有错误带 audit_id；i18n 归 UI。
**幂等**：键 `(tool,args,edition,budget)`；同键同结果；只读；审计每次调用（`AUDIT_EVENT{call_id,tool,params_hash,edition,status,error_code,audit_id}`）；
**无写工具**：写请求/写参数 ⇒ `GRAPH_WRITE_FORBIDDEN`；`graph_expand_cluster` 不写 S5 nav/stack。
**机检**：5 工具/schema；错误表覆盖/映射；幂等键；audit；无写；expand 无 nav 变更。
**反例**：错误码自造；同参不同结果；无 audit；expand 改 stack；写工具。
**边界**：stale/空/budget/并发只读。
**U 映射**：U-29、U-32、U-34。
**建议裁决**：冻结 5 工具/错误表/幂等/审计/无写。
**证据等级**：A（S6-9 + ADDENDUM-1；S7-RULINGS R-S7-1/3/5）+ R。

---

## S7-6 写权限边界

**规则**：v1 agent 不可写图；无写工具/写参数；curation 仅 S10 工具+审计/人工确认；禁止 sidecar/manifest/registry/S2 run/VM/cache 写；写后 edition 变化，S7 只能读新 edition（stale→refresh）。
**机检**：无写工具；写请求 `GRAPH_WRITE_FORBIDDEN`；audit；S10 边界。
**反例**：agent 写 sidecar；S7 提供 write；curation bypass；写 registry。
**边界**：S10 写后；人工 curation；权限失败。
**U 映射**：U-29、U-34。
**建议裁决**：冻结 v1 不可写/写仅 S10/禁 sidecar。
**证据等级**：A（S6-1/S6-10；R-S7-5）+ R。

---

## S7-7 证据/引用契约（resolve_ref）

**规则**：
```
EvidenceRef{kp_id?, file?, line?, anchor?, cluster_key?, run_id?, edge_id?}
claim{text, claim_type∈{graph_relation,source_assertion}, refs[], unknown?{reason}}
graph_relation: 必须 edge_id + 端 anchor；
source_assertion: 必须 kp_id+file+line/anchor；
cluster: cluster_key+run_id+member_count；
unknown: 显式；不得当“无关系”。
```
`graph_resolve_ref` 解析 ref：`{resolved,kp_id,file,line,anchor,stale,claim_type}`；解析走 DataSource/索引，不读文件系统；stale/不可解析 ⇒ `GRAPH_ANCHOR_STALE`/unknown。
**机检**：claim_type/refs；graph_relation/source_assertion 必填；cluster/run；resolve_ref 可解析；unknown；引用率。
**反例**：无 ref；编造行号；cluster 只 label；unknown 省略；直接读文件。
**边界**：KP 无 file；anchor stale；多归属；旧 KB。
**U 映射**：U-12、U-13、U-14、U-19、U-27。
**建议裁决**：冻结双类型引用/解析工具/unknown/机检。
**证据等级**：A（S6 DataSource；S2 cluster；R-S7-1/R-S7-4）+ R。

---

## S7-8 与 S9 检索接口

**规则**：S7 只定义消费；S9 提供候选/召回/排序（candidate_ref schema 归 S9）；S7 用 `graph_focus(focus_id=candidate)`/explain/expand，不定义 recall/score；S9 错误传播 `GRAPH_RETRIEVAL_UNAVAILABLE`；空候选/无 semantic 降级显式，不编造。
**机检**：S7 无检索实现/正文扫描；S9 candidate refs；错误映射；无 semantic 无簇。
**反例**：S7 定义 ranking/扫正文；S9 空结果 S7 编簇；score 当事实。
**边界**：S9 挂/空/无 semantic/跨 KB/stale。
**U 映射**：U-2、U-14、U-15、U-17、U-32。
**建议裁决**：冻结 S7/S9 边界/错误传播/无 semantic 降级。
**证据等级**：A（S7 章程；S6-2）+ R。

---

## S7-9 与 S10 边界

**规则**：S10 设计/写 KP/语义边；S7 只读消费、不调用 S10 写；S10 写后 edition/缓存失效，S7 返回 `GRAPH_EDITION_STALE`，要求 refresh；不混用旧新 edition。
**机检**：S7 无 S10 写；edition stale；缓存按 edition；S10 审计/人工确认。
**反例**：S7 自动写；旧 View 当新；S10 草稿当事实。
**边界**：S10 批量写/部分失败；edition 变；旧缓存。
**U 映射**：U-29、U-32、U-34。
**建议裁决**：冻结 S7 只读/S10 写/edition stale/刷新。
**证据等级**：A（S6-1；S10 章程）+ R。

---

## S7-10 多维度/多归属

**规则**：查询显式 `dimension_id`（默认 H；A 必须显式）、`view_family_id`；响应 `scope`；多归属 `memberships[]` 只列当前 scope，不合并；不把某一维当全局。
**机检**：默认 H/A 显式；scope/memberships；不合并；单维。
**反例**：默认混 H/A；合并多归属；跨族无 scope。
**边界**：多归属；无族；A/H 切换。
**U 映射**：U-10、U-11、U-12、U-21。
**建议裁决**：冻结显式维度/多归属解释/默认标注。
**证据等级**：A（S1 D-5；S2 多归属）+ R。

---

## S7-11 失败/降级（显式不编造）

**规则**：`no_semantic_edges` ⇒ KP+layout_group，无簇，coverage=0；budget ⇒ `GRAPH_TOOL_BUDGET_EXCEEDED`/truncated；数据缺失 ⇒ `GRAPH_ANCHOR_STALE`/`GRAPH_TOOL_INPUT_INVALID`；unknown 关系 ⇒ unknown/reason；S9 挂 ⇒ `GRAPH_RETRIEVAL_UNAVAILABLE`；stale ⇒ `GRAPH_EDITION_STALE`；agent 不得编造。
**机检**：错误码/state/truncated；no_semantic；unknown；stale；不编造。
**反例**：编簇/编引用；未知当无；截断不标；stale 混用。
**边界**：空 KB；预算 0；S9 挂；写后 stale。
**U 映射**：U-13、U-14、U-27、U-32。
**建议裁决**：冻结显式降级/错误码/不编造。
**证据等级**：A（S2-12/S4/S6-9）+ R。

---

## S7-12 可观测/验收（G7 引用 G6）

**规则**：每次查询记录 G7 事件；G7 引用 G6 的 `run_ids/frame_ids/edition`，不复制事实；指标：tool_calls、tokens、ref_completeness、unknown_ratio、truncation_ratio、write_attempts=0、error_histogram；阈值 S8；G7 不含正文。
**机检**：G7 字段；引用 G6；审计；指标可复算；无正文。
**反例**：G7 含正文；不引用 G6；写尝试不记；指标缺失。
**边界**：空会话；no_semantic；截断；S9 挂。
**U 映射**：U-29、U-32、U-34。
**建议裁决**：冻结 G7/G6 引用/指标；阈值 S8。
**证据等级**：A（S6-11；R-S7-6）+ R。

---

## 附：R-S7 自检（6 条）

| 裁决 | B-v2 落位 |
|---|---|
| R-S7-1 resolve_ref 只读/审计/DataSource | S7-3/S7-5/S7-7（graph_resolve_ref；AgentQuery 读路径） |
| R-S7-2 edges 只 shown + summary + explain | S7-2/S7-4（ViewResponse.edges shown；suppressed_summary；explain 受控） |
| R-S7-3 5 snake_case 工具/无 path/错误表映射 | S7-3/S7-5（5 工具；无 path/query；错误表 S6+ADDENDUM-1） |
| R-S7-4 字段统一 | S7-2（view_model_id/frame_id 审计/aggregate_count/member_count） |
| R-S7-5 幂等/expand 无 nav/写 forbidden | S7-5（幂等键；expand 不改 S5；GRAPH_WRITE_FORBIDDEN） |
| R-S7-6 默认/G7/S9-S10 | S7-4/S7-12/S7-8/S7-9（4000/200；G7 引用 G6；边界） |

> 独立声明：B-v2 先于 A-v2 完成（A-v2 落盘后才对照）；差异与判断见 `S7-objections-v2.md`；未写产品代码/契约，未 commit。
