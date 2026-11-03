# S7 agent 如何使用图谱提案 B（独立复核方）

> **依据**：`multilevel-graph-vision.md` U-1..U-35；上游冻结 `S0-terms-v1.md`（`241b1e1e…`）、`S1-dimensions-v1.md`（`6676c71d…`）、`S2-clustering-v1.md`（`92bb0041…`）、`S3-visual-v1.md`（`0ca4ea0e…`）+ `S3-ADDENDUM-1`、`S4-render-v1.md`（`2576f6c8…`）、`S5-nav-v1.md`（`7f4c4515…`）、`S6-contract-v1.md`（`40f12e5f…`），不得违反；本场 `S7-charter.md`。
> **性质**：独立复核方提案；写作时**未读** `S7-agent-proposal-A.md`（尚未落盘）；写完再对照，差异见 `S7-objections.md`。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S0–S6 冻结。
> **日期**：2026-11-03（Asia/Shanghai）。

---

## 0. 总原则

1. **v1 agent 只读**：不写图谱、不写 sidecar/manifest/registry、不写 S2 run；curation 只走 S10 工具 + 审计/人工确认（S7 不定义写工具）。
2. **事实只来自 DataSource**（`.md` + sidecar/manifest 的只读投影）；VM/缓存/导航 frame 是派生/视图状态，**不得当事实**；agent 默认看 `View + presence/rule_id 解释`，不直接看 raw 边。
3. **查询复用 S4/S5**：focus 一跳（F={focus}，默认 hop=1）、无隐式 2 跳、2 跳只能显式 `new_hop`；不实现第二套取景/闭包。
4. **token 预算可见**：层级摘要、`truncated`/`truncated_reason`、`suppressed/unknown` 计数；**禁止静默截断/编造**。
5. **引用可机检**：`kp_id+file+line`（或 anchor）、`cluster_key/run_id`；区分「图谱关系」与「原文断言」；unknown 显式。
6. **工具面稳定**：只读工具、`GRAPH_*` 错误码、幂等、每次调用审计；不夹带 S9/S10 设计。

### 0.1 覆盖矩阵（U + S0–S6）

| U# | 落点 | U# | 落点 |
|---|---|---|---|
| U-2/U-3 | agent 使用图谱=S7-2/S7-3 | U-6 | 簇摘要=S7-4 |
| U-10/U-11 | 维度=S7-10 | U-12/U-13 | 查询/证据=S7-3/S7-7 |
| U-14 | 生成/引用=S7-7 | U-15 | 一跳=S7-3 |
| U-17 | 不带背后图=S7-3 | U-19 | KP/簇=S7-3 |
| U-27 | presence/存无=S7-2/S7-4 | U-32 | token/预算=S7-4/S7-12 |
| S4/S5 | focus/nav 语义=S7-3/S7-9 | S6 | schema/错误/审计=S7-5/S7-7 |

---

## S7-1 定位与边界（只读）

**规则**：S7 冻结 **agent 消费图谱的契约**，不设计图谱语义。v1 agent **只读**：
- 可读：DataSource 只读投影、GraphView、VM、presence/rule_id、S2 run/membership（只读摘要）、引用；
- 不可写：DataSource/sidecar/manifest/registry/S2 run/VM/缓存/导航状态；
- 不绕过 DataSource 直读 sidecar 原始字节；不把派生缓存当事实；curation/写路径属 S10。
**形式化/机检**：
```
agent_capabilities = {read:["dataSource","graphView","vm","presence","refs","runSummary"],
                      write:[]}
assert no write tools in v1; no sidecar/manifest/registry mutation
assert agent read API 只经 DataSource/S6 contract；无 raw file 写/改
assert audit every call
```
**反例**：agent 直接改 sidecar；把 VM 当事实回答"库里有什么"；写 registry；绕过 DataSource 读内部缓存。
**边界**：旧 KB/无 sidecar；只读权限；S10 写后 edition 变；多 KB。
**U 映射**：U-2、U-3、U-29、U-34。
**建议裁决**：冻结 v1 只读/不写 sidecar/事实只来自 DataSource/S10 写边界。
**证据等级**：A（S6-1/S6-10；S0 D-3）+ R。

---

## S7-2 agent 可见层（View + 解释，不当事实）

**规则**：agent 默认看 **View 层**（VM + presence/rule_id 解释），不直接看 raw 边；需要事实时用引用回 DataSource（只读）。可见层：
```
AgentView = {
  view_model_id, level_id, view_family_id, dimension_id,
  nodes[{id,kind,label,role:"member",member_count?,presence?,rule_id?}],
  edges[{id,type,display_type,presence,rule_id?,aggregate_count?}],
  summary{presence histogram, suppressed/unknown reasons},
  refs[]，
  truncated/truncated_reason?
}
```
- VM 是派生视图，不是事实；presence 只解释"为何显示/不显示"，不改事实；`data_edge_ids` 不直接暴露（需要时 `explain` 只给审计计数/引用，Renderer 禁读仍有效）。
**机检**：AgentView schema；presence/rule_id 可解释；不把 VM 当 DataSource；raw edge 不直接给 agent（除 explain 的受控投影）；`data_edge_ids` 不出现在 AgentView。
**反例**：回答"图谱里有 X 边"仅凭 VM shown；把 cluster 当事实；把 suppressed 当不存在。
**边界**：no_semantic_edges；空 VM；full mode；unknown 多；cluster 无成员摘要。
**U 映射**：U-2、U-3、U-27、U-32。
**建议裁决**：冻结 AgentView/派生不当事实/presence 解释/受控 explain。
**证据等级**：A（S3 VM/S4 presence；S6-5）+ R。

---

## S7-3 查询接口（focus/expand/explain/path）

**最小查询集（只读）**：
```
graph.focus(level, view_family, dimension, focus_id, hop=1, mode=default, budget)
  -> AgentView（S4_FRAME_SPEC；F={focus}；无隐式 2 跳）
graph.expand(cluster_ref | kp_id, direction=hierarchy|association, budget)
  -> 下层/一跳 View（H drill 一层；A 一跳；复用 S2 run/S4；不闭包）
graph.explain(edge_id | node_id | cluster_ref)
  -> {presence, rule_id, type/contain_kind/label, provenance,
      data_edge_ids_count?, refs, source_assertion?}
graph.path?(from_ref, to_ref, max_hops≤3, explicit=true)
  -> 显式有界路径（可选；不得作为默认取景；不产生 presence）；无路径/超界显式
```
- 所有查询构造 `S4_FRAME_SPEC` 调用 S4；**不得自行计算 presence**；H drill 复用 S2 run，A 一跳复用 S1/S4；2 跳只能 `new_hop=true`（S5 显式），agent 默认无。
- `expand(cluster)` 只展开一层（不是闭包）；`path` 为可选查询，需显式参数，不能用于默认视图/多跳污染。
**机检**：query→S4 frame_spec；F={focus}；默认 hop=1；无隐式 2 跳；expand 一层；path 显式/有界；presence 来自 S4。
**反例**：agent 自动 BFS 2 跳；expand 递归闭包；path 无界；自己算 presence；把 path 当事实。
**边界**：cluster 无子；A 无邻居；no_semantic；path 无解；多归属。
**U 映射**：U-6、U-10、U-12、U-13、U-15、U-17、U-19、U-32。
**建议裁决**：冻结最小查询集/复用 S4/S5/无隐式 2 跳/expand 一层/path 显式有界。
**证据等级**：A（S4 R-S4-1/2；S5 nav；S2）+ R。

---

## S7-4 展开与 token 预算（显式截断）

**规则**：
- 每次调用有 `token_budget`/`max_nodes`/`max_edges`；S4 budget 同源（S8 定值）。
- 层级摘要：cluster 用 `label + member_count + representative`，不展开全部成员；需要成员时显式 `expand`/`list_members`（只读）。
- 超预算：**显式** `truncated=true`、`truncated_reason∈{budget_nodes,budget_edges,token_budget}`、`kept_counts`、`suppressed_counts`；不得静默截断。
- `suppressed/unknown`：逐条给 `rule_id`；unknown 不等于"无关系"；agent 回答必须保留这些字段或摘要。
**机检**：budget 字段；truncated 显式；无静默截断；摘要字段；suppressed/unknown/rule_id；token 计数可复算。
**反例**：超预算直接少返回不标记；把 suppressed 当不存在；只给 shown；cluster 展开全部成员超 token。
**边界**：budget=0；空视图；unknown 多；full；单 cluster 大。
**U 映射**：U-6、U-27、U-32。
**建议裁决**：冻结 token/节点预算/摘要/显式截断/suppressed-unknown 解释。
**证据等级**：A（S4 budget；S3-11；S6 G6）+ R。

---

## S7-5 工具面（MCP/内部）

**工具 schema（v1 只读）**：
```
graph.focus{level_id,view_family_id,dimension_id,focus_id,hop=1,mode=default,budget}
graph.expand{target_id,target_kind∈{cluster,kp},direction∈{hierarchy,association},budget}
graph.explain{target_id,target_kind∈{edge,node,cluster}}
graph.path?{from,to,max_hops≤3}
graph.query?{...}  # 可组合的只读查询，不引入新语义
```
- 返回 envelope：`{ok, data, meta{view_model_id,frame_id?,truncated,budget_used}, errors[], audit_id}`；错误 `GRAPH_*` + `legacy_code`；只读工具**幂等**（同参数同结果/同 audit 结果 sha）；每次调用写 audit（`.memoria/agent/audit/graph/`）。
- 无写工具；无 `graph.curate` v1；不暴露 DataSource 写/registry 写。
**机检**：schema/参数枚举/返回；错误码；幂等 2x；audit 事件；无写工具；未知工具 fail-closed。
**反例**：工具返回 raw sidecar；写工具；错误码不统一；无 audit；同参数不同结果（未标 stale）。
**边界**：预算/空/失败/无 semantic；MCP 断开；超时。
**U 映射**：U-3、U-32、U-34。
**建议裁决**：冻结 v1 只读工具集/schema/envelope/错误码/幂等/审计/无写工具。
**证据等级**：A（S6-9；现有 agent tools）+ R。

---

## S7-6 写权限边界

**规则**：v1 agent **不可写图**；写操作（建立/修改 KP、语义边、curation、registry）只能由 S10 定义的工具执行，且需审计/人工确认；S7 不定义写工具/写 schema。若未来开放，必须走 S10 + S7 修订，禁止直接改 sidecar/manifest/registry/S2 run/VM。
**机检**：agent tool registry 无写工具；文件沙箱/权限只读；audit 记录任何写尝试为拒绝；S10 边界。
**反例**：agent 直接写 sidecar；改 registry JSON；写 S2 run；通过 shell 写 `.memoria`。
**边界**：S10 工具存在但 v1 未启用；人工 curation；权限失败。
**U 映射**：U-29、U-34。
**建议裁决**：冻结 v1 不可写/写路径仅 S10+审计/禁止 sidecar。
**证据等级**：A（S6-1/S6-10；S0 D-3）+ R。

---

## S7-7 证据/引用契约

**规则**：回答必须带可机检引用：
```
REF = {kind∈{kp,edge,cluster,run,file_anchor},
       kp_id?, edge_id?, cluster_key?, run_id?, file?, line?, anchor?}
```
- KP 引用必须 `kp_id + file + line`（或稳定 anchor）；cluster 引用 `cluster_key + run_id`（+ member 摘要）；run 引用 `run_id`；file/line 与 DataSource/正文一致。
- 区分 **图谱关系**（来自 EDGE，`type/provenance`）与 **原文断言**（`file/line`，可能不被图谱覆盖）；unknown 必须 `unknown:true` + reason；不得把图投影当原文。
- 引用完整性可机检：每个结论至少一个 REF；file 存在、line 在范围；ref 可解析。
**机检**：REF schema；kp/file/line；cluster_key/run_id；关系 vs 断言字段；unknown；引用率。
**反例**：无引用；编造行号；把 VM 当原文；cluster 只给 name；unknown 省略。
**边界**：KP 无 file；anchor 无行号；多归属；旧 KB。
**U 映射**：U-12、U-13、U-14、U-19、U-27。
**建议裁决**：冻结 REF/引用必填/关系-断言区分/unknown/机检。
**证据等级**：A（DataSource KP/file/line；S2 cluster_key/run_id）+ R。

---

## S7-8 与 S9 检索接口

**规则**：S7 只定义 agent 消费契约；S9 提供候选/召回（检索算法、排序、索引），S7 不实现/不定义；S9 返回的候选必须可经 DataSource/S4 校验后进入 AgentView；错误传播 `GRAPH_*`；无 semantic edges 时 S9 可返回空候选，S7 降级为 no_semantic 视图，不伪造语义。
**机检**：S9 接口字段（候选 id/score/provenance）与 S7 边界；S7 不包含检索算法；无 semantic 降级；错误传播。
**反例**：S7 定义 BM25/embedding；S9 直接返回 VM 当事实；无 semantic 时伪造簇。
**边界**：S9 不可用/超时；候选空；无 E_sem；多 KB。
**U 映射**：U-10、U-11、U-17、U-32。
**建议裁决**：冻结 S7/S9 边界/候选校验/错误传播/无 semantic 降级。
**证据等级**：A（S7 章程范围；S9 后续）+ R。

---

## S7-9 与 S10 边界

**规则**：S10 设计/写入知识点与语义边；S7 只读消费；写后 edition/registry 变化 ⇒ S7 view **stale**，必须重新 queried，不得用旧缓存当事实；S7 不定义写工具、不触发写；写路径审计/人工确认属 S10。
**机检**：S7 无写；edition 变化→stale；缓存不跨 edition；S10 工具不在 S7 registry。
**反例**：S7 顺手 curation；旧 VM 跨 edition；把 S10 草案当事实。
**边界**：S10 写后刷新；旧 edition 查询；审计。
**U 映射**：U-29、U-32、U-34。
**建议裁决**：冻结 S7 只读/S10 写/edition stale/写后刷新。
**证据等级**：A（S6 edition；S10 charter）+ R。

---

## S7-10 多维度/多归属

**规则**：每次查询必须显式 `dimension_id`（H/A）与 `view_family_id`；返回 `dimension_id/view_family_id`；多归属簇/节点只按当前 `view_family` 解释，列出 `membership` 摘要但不合并/不汇总全局；不得把某一维当全局；未指定时默认 H/level0/root，并在 meta 标明。
**机检**：dimension/family 显式/默认；返回字段；多归属 membership 摘要；不合并；单维（S1 D-5）。
**反例**：默认混 H/A；把多归属合并计数；某一维当全局；跨族簇不标 family。
**边界**：多归属；无族；A/H 切换；旧 KB。
**U 映射**：U-10、U-11、U-12、U-21。
**建议裁决**：冻结显式 dimension/family/多归属解释/默认标注。
**证据等级**：A（S1 D-5；S2 多归属）+ R。

---

## S7-11 失败/降级（显式不编造）

**规则**：失败必须可见、可解释：
```
GRAPH_* error envelope {code,severity,retryable,i18n_key,detail,correlation_id}
no_semantic_edges => AgentView KP+layout_group，coverage=0，不伪造簇
budget_insufficient => truncated=true + reason + kept/suppressed counts
data_missing/stale => GRAPH_DATA_UNAVAILABLE/GRAPH_EDITION_MISMATCH，回退默认/提示
unknown relation => unknown=true + rule_id，不是"无"
```
- agent 不得编造缺失元素；降级有明确 mode；重试策略有限。
**机检**：错误码/severity/retryable；no_semantic；budget；data/stale；unknown；无编造（引用检查）。
**反例**：无 semantic 编簇；预算不足静默；unknown 当无；旧 edition 当新。
**边界**：空 KB；only KP；S9 不可用；S4 失败；低 token。
**U 映射**：U-10、U-13、U-27、U-32。
**建议裁决**：冻结失败 envelope/降级/no_semantic/unknown/不编造。
**证据等级**：A（S2/S4/S6 失败码）+ R。

---

## S7-12 可观测/验收（G7 草案）

**规则**：每次调用可观测：
```
G7_SNAPSHOT = {g7_version, call_id, tool, params_sha, view_model_id/frame_id?,
               token_in/out, kept_node/edge, suppressed/unknown counts,
               truncated, citation_completeness, unknown_ratio, latency_ms,
               error_code?, audit_id, edition_sha}
```
指标：工具调用数、token 用量、命中率、引用完整率、unknown 比例、截断率、延迟；阈值 S8；审计可追溯；G7 不写事实。
**机检**：G7 字段；token/引用/unknown/截断；audit_id；可复跑；阈值 S8。
**反例**：无 token/引用指标；只统计成功；G7 含正文。
**边界**：失败/截断/空；多 KB。
**U 映射**：U-32、U-34。
**建议裁决**：冻结 G7 字段/指标/audit；阈值 S8。
**证据等级**：A（S3/S4/S6 G6/G7）+ PI（字段）。

---

## 附：S7 章程预注册判据自检

| 判据 | 本提案 |
|---|---|
| v1 agent 只读/写路径 S10 | S7-1/S7-6 |
| 只看 View/解释，不当事实/不绕 DataSource | S7-2 |
| 查询复用 S4/S5、无隐式 2 跳 | S7-3 |
| 引用契约可机检 | S7-7 |
| token/截断/unknown 显式 | S7-4/S7-11 |
| 工具/错误/审计 | S7-5 |
| S9/S10 边界 | S7-8/S7-9 |
| A/B 差异逐条 | 见 `S7-objections.md` |
| 覆盖 U-2/3/6/10/11/12/13/14/15/17/19/27/32 | §0.1 |
| 不写产品代码/契约/commit | 本文件只写设计 |

> 独立声明：本文件写作时未读 `S7-agent-proposal-A.md`（尚未落盘）；差异与判断见 `S7-objections.md`，逐项列不合并。
