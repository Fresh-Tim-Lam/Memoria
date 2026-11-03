# S7 提案 A-v2：agent 如何使用图谱（只读消费、查询/引用/token 契约）

> **修订依据**：`docs/design/multilevel-graph/S7-RULINGS.md` + `S6-ADDENDUM-1.md`。
> **本文件**：A 修订版；**不覆盖** `S7-agent-proposal-A.md`（v1 `2508e8bc…`），保留审计链。

> **提案方**：主办研究（`gm-seminar-researcher`）｜**票**：task-326｜**日期**：2026-11-03（Asia/Shanghai）
> **最高依据**：`docs/design/multilevel-graph-vision.md`（U-1..U-35）。
> **上游冻结（不得违反）**：S0–S6 七份 v1 + `S3-ADDENDUM-1`（S6 `40f12e5f…`）。
> **本场章程**：`docs/design/multilevel-graph/S7-charter.md`（S7-1..S7-12）。
> **工程输入**：`ENGINEERING-PLAN.md`（I-01..I-13）、现有 agent 面 `resources/agent-prompts/**`、`agent-capabilities/*.json`（只读）。
> **独立性**：未阅读 S7 复核方草稿；本提案独立撰写。
> **纪律**：只写契约；不改产品代码/契约/不 commit。

---

## 0. 总口径

```
agent 只读 → AgentQuery（View + presence/rule_id + 证据锚）→ 回答
事实 = DataSource（只读）；View/VM/缓存是派生；agent 不直接读 DataSource/cache/sidecar/registry
查询复用 S4（focus-only 一跳）与 S5（drill/back，无隐式 2 跳）；写只能走 S10 工具+审计/人工
引用必须 kp_id+file+line/anchor（+ cluster_key/run_id）；unknown/降级显式，不编造。
```

**证据等级**：A（原话/冻结契约/代码事实）；B（单源实测）；C（推理）；**本项目假设**（工具名/token 阈值/G7 字段）。

---

## 1. S7-1 定位与边界（v1 只读）

**定义/规则（一句话）**：v1 agent 对图谱**只读**；只能通过只读 AgentQuery 消费 View/解释层，不得绕过 DataSource、不得写 sidecar/registry/cache、不得改事实。

**形式化**：
```
Agent 权限 = {read_view, read_explain, read_summary, read_anchors}
禁止：write(kb/sidecar/manifest/registry/cache/VM)；
      直接读 DataSource raw edges（只能通过 AgentQuery 的 View 投影）；
      把 VM/缓存/派生簇当事实（facts 只在 DataSource；引用回 kp_id+file+line）
S0-10 三层：
  L_kp（S10 设计 KP） / L_sem（agent 写语义，需证据+审计） / L_view（只请求取景）
S7 = L_view 读契约；L_kp/L_sem 的写路径在 S10，不在 S7
```
**反例**：agent 直接读 sidecar/写 registry；把 cluster run 缓存当事实；绕过 DataSource 查边；在 S7 提供写工具。
**边界**：无 permission 的 agent（只读）；curation 流程（S10）；多 KB（单 KB 只读）；旧缓存。
**机检条件**：
```
- S7 工具全部 read_only=true；无写 API/参数
- 工具输入无 sidecar/registry/cache 路径；无 SQL/文件写
- 回答引用可回到 DataSource anchor；缓存/VM 不作证据
- S6 单一真源/D-3 约束保持
```
**U 映射**：U-1、U-29、U-32、U-34。
**建议裁决**：采纳 v1 只读/只走 AgentQuery/不写 sidecar/不把派生当事实。
**证据等级**：A（S0-10；S6-1/S6-9；U-29）；**本项目假设**（工具面形态）。

---

## 2. S7-2 agent 可见层

**定义/规则（一句话）**：agent 默认看 **GraphView + presence/rule_id 解释 + 证据锚**；不直接看 raw DataSource 边；VM 只是渲染派生，不可作为事实来源。

**形式化**：
```
Agent 可见：
  ViewResponse{view_model_id, edition_sha, frame_id（仅审计，由导航帧触发时）,
               level_id, view_family_id, dimension_id, data_state,
               nodes[], edges[]（仅 presence=shown）,
               clusters[], counts, presence_histogram,
               suppressed_count, unknown_count,
               suppressed_summary{rule_id:count}, rule_histogram,
               truncated, omitted, token_estimate}
  node: {node_id, kind, label, member_count?（cluster 节点）,
         kp_ref?{kp_id,file,line_start,line_end,anchor_id},
         cluster_ref?{cluster_id,run_id,cluster_key,label,member_count}}
  edge: {edge_id, type, contain_kind?, label?, presence=shown, state?,
         source,target, evidence_refs[], aggregate_count}
不可见/不可用作事实：raw DataSource.edges 全量、VM 内部 data_edge_ids、
cache bytes、registry internals、run 内部 params（除引用需要 run_id/key）；
suppressed/unknown 不列原始边，只在 suppressed_summary/rule_histogram/unknown_count；
逐条解释被抑制边只能 graph_explain_edge(edge_id) 受控返回。
```
**反例**：agent 把 VM nodes 当事实；用 cluster label 当 KP 证据；读缓存 JSON 当数据；把 presence=shown 当"事实存在"；批量列 suppressed 原始边。
**边界**：cluster 节点无 KP anchor（需 run/key）；KP 节点 anchor 缺失→unknown；空视图；no_semantic。
**机检条件**：
```
- ViewResponse 字段白名单；无 data_edge_ids/VM 内部字段
- edges[] 全部 presence=shown；无 suppressed/unknown 原始边
- suppressed_summary/rule_histogram 覆盖全部 suppressed/unknown
- node/edge 引用可解析到 DataSource anchor 或 run/key；事实性回答必须带 anchor
```
**U 映射**：U-2、U-6、U-13、U-14、U-27。
**建议裁决**：采纳 View+presence 解释为 agent 可见层；不把 VM/缓存当事实。
**证据等级**：A（S6-5/S6-1；S3-12；S0-9）；**本项目假设**（ViewResponse 字段）。

---

## 3. S7-3 查询接口（focus/one-hop、explain、expand；无隐式 2 跳）

**定义/规则（一句话）**：v1 最小查询 = `graph_focus`（H 层视图 / A focus 一跳）、`graph_explain_edge`、`graph_expand_cluster`（drill 一层）、`graph_summary`、`graph_resolve_ref`（证据解析）；全部复用 S4 focus-only 与 S5 drill 语义，**无隐式 2 跳**；`graph_path` v1 不提供。

**形式化**：
```
graph_focus(kb_id, level_id?, view_family_id?, dimension_id?="hierarchy",
            focus_id?, budget{max_tokens,max_nodes})
  H: 当前 level/partition 视图（S4 MANDATORY/预算）
  A: F={focus}，恰好一跳（S4-3）；不允许隐式 2 跳
  返回 ViewResponse；focus 默认 root；无 focus 的 A 请求 ⇒ GRAPH_TOOL_INPUT_INVALID（missing focus）
graph_explain_edge(kb_id, edge_id, frame_id?)
  → EdgeExplanation（type/contain_kind/label/presence/rule_id/state、
     source/target anchors、aggregate_count、unknown_reason?）
     # 受控解释 suppressed/unknown；不批量列原始边
graph_expand_cluster(kb_id, cluster_id, run_id, level_id, dimension_id?, budget)
  → 子层 ViewResponse（一次 drill；S5 CLICK_CLUSTER 语义；不递归、**不改 S5 nav 状态/stack**）
graph_summary(kb_id, level_id, view_family_id?, dimension_id?)
  → SummaryResponse（clusters[] label/member_count/coverage/counts/data_state）
graph_resolve_ref(kp_id?|file+line|anchor)
  → {resolved, kp_id, file, line, anchor, stale, claim_type}
     # 只读/幂等/审计；解析走 DataSource/索引，不得直读文件系统
graph_path：v1 不提供；若未来需要 >1 跳，必须 S5 EXPLICIT_NEW_HOP + 显式 allow_two_hop 审核
```
**反例**：focus 自动返回 2 跳/闭包；expand 递归展开；explain 返回背后图；path 默认 2 跳；expand 修改 S5 导航栈。
**边界**：无 focus（A 必须显式）；cluster 无子；edge 不在当前 frame；path 请求拒绝；no_semantic。
**机检条件**：
```
- 工具集 = {focus, explain_edge, expand_cluster, summary, resolve_ref}；无 path 工具
- focus 默认 max_hop=1；无 2 跳字段；expand 只一层
- expand 不改 agent/服务端导航状态（纯读）
```
**U 映射**：U-10、U-11、U-15、U-17、U-19、U-22。
**建议裁决**：采纳五工具只读集；focus 一跳；expand 一层；resolve_ref 解析引用；v1 不做 path。
**证据等级**：A（S4-3/R-S4-1..2；S5-3/S5-4；S1-5；S6-1 引用）；**本项目假设**（工具名/参数）。

---

## 4. S7-4 展开与 token 预算（摘要/截断可见）

**定义/规则（一句话）**：每次查询有 `max_tokens`/`max_nodes` 预算；超预算先降为层级摘要，再显式 `truncated/omitted`；`suppressed/unknown` 必须解释；**禁止静默截断**。

**形式化**：
```
budget{max_tokens:int=4000, max_nodes:int=200}   # S8 可调
响应优先级：summary（clusters label/member_count/coverage/counts）
            → 限额节点/边（S4 已选；edges[] 只含 shown）
            → 仍超 ⇒ truncated=true, omitted_counts{node,edge}, truncation_reason
必须字段：presence_histogram{shown,suppressed,unknown}, rule_histogram{rule_id:count},
          suppressed_summary{rule_id:count}, suppressed_count, unknown_count,
          coverage, data_state, token_estimate
suppressed 解释：只按 rule_id 聚合（suppressed_summary/rule_histogram）；不列出被抑制的原始边；逐条解释只能 graph_explain_edge
unknown 解释：unknown_count + unknown_reasons[]；不等于"无关系"
禁止：静默丢节点/边；把 truncated 当完整；把 summary 当完整图
```
**反例**：超预算直接截断不标记；把 suppressed 当不存在；unknown 省略；摘要隐藏 coverage=0；token 估算造假。
**边界**：预算极小（只 summary）；空视图；无簇；full 视图；大图。
**机检条件**：
```
- 超预算必有 truncated/omitted/truncation_reason；不静默
- presence/rule 直方图可复算；unknown_count 与 reasons 一致
- token_estimate 在预算内（超则 summary/错误）
```
**U 映射**：U-3、U-13、U-16、U-27、U-32。
**建议裁决**：采纳预算优先 summary、显式截断/解释；禁止静默。
**证据等级**：A（S4-2/S4-6；S3-11；S6-6）；**本项目假设**（默认 token 值）。

---

## 5. S7-5 工具面（schema/错误码/幂等/审计）

**定义/规则（一句话）**：S7 工具全部只读、显式 schema、`GRAPH_*` 错误码、幂等、每次调用写审计；工具返回不夹带写路径。

**工具 schema（v1）**：
| 工具 | 输入 | 输出 | 写？ | 幂等 |
|---|---|---|---|---|
| `graph_focus` | `kb_id`, `level_id?`, `view_family_id?`, `dimension_id?`, `focus_id?`, `budget?` | ViewResponse | 否 | 是 |
| `graph_explain_edge` | `kb_id`, `edge_id`, `frame_id?` | EdgeExplanation | 否 | 是 |
| `graph_expand_cluster` | `kb_id`, `cluster_id`, `run_id`, `level_id`, `dimension_id?`, `budget?` | ViewResponse | 否 | 是 |
| `graph_summary` | `kb_id`, `level_id`, `view_family_id?`, `dimension_id?` | SummaryResponse | 否 | 是 |
| `graph_resolve_ref` | `kp_id?` \| `file+line` \| `anchor` | `{resolved,kp_id,file,line,anchor,stale,claim_type}` | 否 | 是 |

**ViewResponse（返回 schema 摘要）**：
```
{view_model_id, edition_sha, frame_id（仅审计，若由导航帧触发）,
 level_id, view_family_id, dimension_id, data_state,
 nodes[], edges[]（仅 presence=shown）, clusters[], counts{node,edge,cluster},
 presence_histogram, suppressed_count, unknown_count,
 suppressed_summary{rule_id:count}, rule_histogram,
 coverage, truncated, omitted, token_estimate, scope_note}
```
**错误码（逐码映射 S6 + S6-ADDENDUM-1；全部带 audit_id）**：
| code | 触发 | legacy 映射 | severity | i18n |
|---|---|---|---|---|
| `GRAPH_TOOL_INPUT_INVALID` | 参数缺失/非法/越界 | `GRAPH_INTERNAL`（旧无对应） | error | `graph.tool.input_invalid` |
| `GRAPH_TOOL_BUDGET_EXCEEDED` | max_tokens/max_nodes 连 summary 都不满足 | `GRAPH_BUDGET_INVALID` | warn | `graph.tool.budget_exceeded` |
| `GRAPH_ANCHOR_STALE` | 引用 anchor 版本失效 | `GRAPH_EDITION_STALE` | warn | `graph.tool.anchor_stale` |
| `GRAPH_RETRIEVAL_UNAVAILABLE` | S9 检索不可用/超时 | `GRAPH_INTERNAL` | error | `graph.tool.retrieval_unavailable` |
| `GRAPH_WRITE_FORBIDDEN` | agent 尝试写图/curation | `GRAPH_INTERNAL` | error | `graph.tool.write_forbidden` |
| `GRAPH_TOOL_AUDIT_FAILED` | 工具审计落盘失败 | `GRAPH_INTERNAL` | error | `graph.tool.audit_failed` |
| `GRAPH_INPUT_INVALID` | kb/参数基础非法（S6） | `GRAPH_INPUT_INVALID` | error | `graph.error.input` |
| `GRAPH_EDITION_STALE` | edition 不匹配（S6） | `GRAPH_EDITION_STALE` | warn | `graph.error.edition` |
| `GRAPH_DIM_UNKNOWN/NOT_ACTIVE` | 维度未知/未激活（S1/S6） | 同名 | error | `graph.error.dim` |
| `GRAPH_FRAME_ID_INVALID` | frame_id 不可解析（S6） | `GRAPH_FRAME_ID_INVALID` | error | `graph.error.frame` |
| `GRAPH_INTERNAL` | 未知错误兜底 | `GRAPH_INTERNAL` | error | `graph.error.internal` |
错误结构：{code, canonical_code, legacy_code?, severity, i18n_key, audit_id,
          message, retryable, details}
**幂等/审计**：
```
幂等键 = (tool, args, edition, budget)；同键同结果（read tools 全部幂等）
每次调用追加 AUDIT_EVENT{call_id, tool, kb_id, edition_sha, frame_id（仅审计）,
  params_hash, status, error_code?, token_estimate, at}
graph_expand_cluster 只返回一次 drill 的只读 ViewResponse，不改 S5 nav 状态/stack
无写工具；若调用 write 参数/工具 ⇒ GRAPH_WRITE_FORBIDDEN；审计失败 ⇒ GRAPH_TOOL_AUDIT_FAILED
```
**反例**：工具自动写缓存/审计以外状态；返回字段不稳定；错误只给 free text；无 audit；重复调用产生不同视图。
**边界**：stale edition；kb 不存在；budget 极小；大响应；并发只读。
**机检条件**：
```
- 工具 schema 可校验；全部 read_only；无写路径；工具名 snake_case（5 个）
- 错误码逐码映射 S6+ADDENDUM-1；错误结构含 legacy/severity/i18n/audit_id
- 幂等键 (tool,args,edition,budget)；expand 不改 nav；每次调用有 audit
```
**U 映射**：U-29、U-32、U-34。
**建议裁决**：采纳五只读工具/schema/错误映射/审计/幂等；无写工具、无 path。
**证据等级**：A（S6-9/S6-8；S0-10）；**本项目假设**（工具名/错误名）。

---

## 6. S7-6 写权限边界

**定义/规则（一句话）**：v1 agent **不可写图**；curation 只能走 S10 工具 + 审计/人工确认；禁止直接改 sidecar/registry/cache。

**形式化**：
```
S7 工具集无 write；无 mutation 参数；无 sidecar/registry path 参数
若 curation：S10 工具（不在 S7）需 {evidence_anchor, curated_by, curated_at, decision_id}
  + 审计 + 人工确认（S0-10）；写后 edition 变化，S7 只能读取新 edition（stale→refresh）
禁止：agent 改 .memoria/sidecars/**、manifest、registry/history、cache
```
**反例**：agent 写 sidecar 修正边；S7 提供 `graph_write`；curation 绕过 S10；写 registry。
**边界**：人工 curation；S10 写后刷新；只读 agent 无权限；多 KB。
**机检条件**：
```
- S7 无写工具/写参数；写路径不存在
- curation 只在 S10 工具；审计字段齐全
- S7 对写请求返回 GRAPH_WRITE_FORBIDDEN
```
**U 映射**：U-29、U-32。
**建议裁决**：采纳 v1 只读；curation 仅 S10+审计/人工；禁写 sidecar/registry。
**证据等级**：A（S0-10；S6-1/S6-8 D-3；S2-13）；**本项目假设**（S10 工具形态）。

---

## 7. S7-7 证据/引用契约

**定义/规则（一句话）**：每条图谱关系引用必须带 `kp_id+file+line/anchor`（或 `cluster_key/run_id`）；区分 **graph_relation** 与 **source_assertion**；引用先经 `graph_resolve_ref` 解析（不直读文件）；unknown 显式。

**形式化**：
```
EvidenceRef{kp_id, file, line_start, line_end, anchor_id, occurrence_id?}
ClusterRef{cluster_id, run_id, cluster_key}
EdgeRef{edge_id, type, contain_kind?, label?, presence?, rule_id?, aggregate_count}
回答结构：
  claim{text, claim_type:"graph_relation"|"source_assertion",
        edge_refs[], cluster_refs[], kp_refs[], unknown?{reason}}
graph_relation：图谱里存在的关系（必须 edge_id + 端 anchor）
source_assertion：原文断言（必须 kp_ref/file/line/anchor；不由图谱推导）
unknown：anchor 缺失/关系未计算/数据缺失 ⇒ unknown_reason；不得编造
```
**反例**：只说"相关"无 anchor；把 cluster label 当原文；graph_relation 无 edge_id；unknown 当"无关系"；line 号错。
**边界**：cluster 无 kp anchor（仅 run/key）；边缺 anchor（unknown）；anchor stale；no_semantic。
**机检条件**：
```
- 引用先经 graph_resolve_ref；resolved=false/stale=true ⇒ 显式 unknown
- 每条 claim 有 claim_type + 对应 refs；graph_relation 至少 edge_id；
  source_assertion 至少 kp_id+file+line/anchor
- cluster 引用至少 run_id+cluster_key；unknown 显式
- 引用可解析（anchor 存在）；不可解析 ⇒ unknown/GRAPH_ANCHOR_STALE
```
**U 映射**：U-17、U-19、U-27、U-32。
**建议裁决**：采纳双类型引用 + 强制 anchor/run-key；unknown 显式。
**证据等级**：A（S0-10；S6-1/S6-4；S2-7）；**本项目假设**（字段名/claim_type）。

---

## 8. S7-8 与 S9 检索接口

**定义/规则（一句话）**：S7 只定义消费契约；S9 提供候选/召回/排序；S9 错误/空结果原样传播为可见降级，S7 不自行造图。

**形式化**：
```
S9 → S7：candidate_refs[]（kp/cluster/edge id + score?）、focus 建议、edition
S7 消费：graph_focus(focus_id=candidate) / explain / expand
S9 错误：
  unavailable ⇒ GRAPH_RETRIEVAL_UNAVAILABLE（可见；可返回 KP-only/空）
  empty ⇒ 空视图 + reason；不编造关系
无 semantic edges：S9 仍返回 KP/anchors；S7 data_state=empty_nosemantic，无簇
S7 不定义 recall/ranking/score；不把 score 当事实
```
**反例**：S7 自己扫描正文/建候选；S9 空结果 S7 编造簇；把 score 当关系强度事实。
**边界**：S9 不可用；空结果；无 semantic；跨 KB；stale。
**机检条件**：
```
- S7 无检索实现/无正文扫描；只消费 candidate refs
- S9 错误可映射 GRAPH_RETRIEVAL_UNAVAILABLE；空结果可见
- no_semantic 时无 cluster 节点/不伪造
```
**U 映射**：U-2、U-14、U-15、U-17、U-32。
**建议裁决**：采纳 S7 只定义消费；S9 召回/错误传播；无 semantic 降级显式。
**证据等级**：A（S0-10；S2-12；S6-2）；**本项目假设**（候选 ref schema）。

---

## 9. S7-9 与 S10 边界

**定义/规则（一句话）**：S10 设计/写 KP/语义边；S7 只读消费；S10 写后 edition/缓存失效，S7 必须刷新，不能把旧 View 当新事实。

**形式化**：
```
S10 负责：KP 设计/边界/命名/语义边写入 + 证据/审计/人工确认
S7：只读；不调用 S10 写工具；不缓存跨 edition 结果
写后：edition_sha 变化 ⇒ S7 旧 frame/VM stale；返回 GRAPH_EDITION_STALE，
     要求 refresh/re-fetch，不自动混用旧新
```
**反例**：S7 自动调 S10 写；写后继续用旧 View；把 S10 草稿当事实；S7 设计 KP。
**边界**：S10 批量写；部分写失败；edition 变化；旧缓存。
**机检条件**：
```
- S7 无 S10 写调用；写后旧 edition 请求返回 STALE
- S7 缓存按 edition 键；不跨 edition 复用
- S10 写路径有审计/人工确认
```
**U 映射**：U-29、U-32、U-34。
**建议裁决**：采纳 S7 只读、S10 写、edition 失效刷新；不混用。
**证据等级**：A（S0-10；S2-13；S6-1）；**本项目假设**（S10 工具/刷新流程）。

---

## 10. S7-10 多维度 / 多归属

**定义/规则（一句话）**：agent 必须显式选择 `dimension_id`（默认 H，A 需显式）；多归属簇返回 `memberships[]`，不得把某一维/族当全局。

**形式化**：
```
dimension_id 默认 hierarchy；A 必须显式传 dimension_id="association"
响应含 scope_note：level/view_family/dimension；不声称全局
多归属：cluster 可在多个 (level,view_family,dimension) 出现；
  explanation 返回 memberships[{level_id,view_family_id,dimension_id,run_id,cluster_key}]
  agent 引用必须带所选 scope；不得合并不同族成员
```
**反例**：默认把 H 当全局；A 未显式；多归属合并成一个簇；跨族引用无 scope。
**边界**：multi-family；A/H 切换；无簇；不同 level。
**机检条件**：
```
- 默认 H；A 请求必须显式；响应 scope 字段
- 多归属返回 memberships；不合并
- 引用带 run/key/scope
```
**U 映射**：U-6、U-10、U-11、U-12、U-21、U-31。
**建议裁决**：采纳显式维度/范围 + 多归属解释；不把一维当全局。
**证据等级**：A（S0-7；S1-13；S2-6）；**本项目假设**（memberships 字段）。

---

## 11. S7-11 失败 / 降级

**定义/规则（一句话）**：`no_semantic_edges`、预算不足、数据缺失、unknown 关系必须**可见降级**；agent 不得编造；错误用 `GRAPH_*`。

**形式化**：
```
data_state=empty_nosemantic ⇒ 只返回 KP/摘要，无 cluster；回答必须说明"无 semantic 簇"
预算不足 ⇒ summary/truncated=true + omitted/原因；不静默
数据缺失 ⇒ GRAPH_ANCHOR_STALE/GRAPH_KB_NOT_FOUND；不补造
unknown 关系 ⇒ unknown_count/reasons；不回答"无关系"
retrieval 不可用 ⇒ GRAPH_RETRIEVAL_UNAVAILABLE；可返回空/KP-only
edition stale ⇒ GRAPH_EDITION_STALE；要求 refresh
```
**反例**：无簇编造簇；预算截断不标；数据缺失编造引用；unknown 说无关系；stale 混用。
**边界**：全空 KB；预算 0；部分边 unknown；S9 挂；写后 stale。
**机检条件**：
```
- 每种降级有 state/error/truncated 标记；无静默
- no_semantic 无 cluster；unknown≠无关系
- stale 不混用旧 edition；错误码 GRAPH_*
```
**U 映射**：U-13、U-14、U-27、U-32。
**建议裁决**：采纳显式降级/错误码/不编造。
**证据等级**：A（S2-12；S4-6；S6-9）；**本项目假设**（文案）。

---

## 12. S7-12 可观测 / 验收 / G7 草案

**定义/规则（一句话）**：每次 agent 查询记录 G7 事件（工具/edition/frame/token/truncated/refs/unknown/status）；G7 快照聚合指标；阈值 S8。

**形式化**：
```
G7_EVENT{call_id, tool, kb_id, edition_sha, frame_id, params_hash,
  token_estimate, node_count, edge_count, refs_count, unknown_count,
  suppressed_count, truncated, latency_ms, status, error_code?, at}
G7_SNAPSHOT{g7_version, session_id, edition_sha, calls, tokens_total,
  tool_histogram, ref_completeness, unknown_ratio, truncation_ratio,
  write_attempts(=0), error_histogram,
  g6_run_ids[], g6_frame_ids[]   # 引用 G6，不复制事实}
指标：
  tool_calls, tokens/call, ref_completeness=resolved_refs/refs,
  unknown_ratio=unknown_claims/claims, truncation_ratio,
  retrieval_empty_rate, write_attempts=0
阈值：S8 统一；S7 只定义可观测项
```
**反例**：无 audit；只统计 token 不统计 unknown；G7 含正文隐私；截断率不记；写尝试不记；G7 复制事实而不引用 G6。
**边界**：空会话；no_semantic；预算截断；S9 挂；多 KB。
**机检条件**：
```
- 每次查询有 G7_EVENT；字段可复算
- G7_SNAPSHOT 聚合指标；write_attempts=0
- 不含正文（只 id/anchor/count）
```
**U 映射**：U-29、U-32、U-34。
**建议裁决**：采纳 G7 事件/快照/指标；阈值 S8。
**证据等级**：A（U-32；S6-8/S6-11；S0-10）；**本项目假设**（G7 字段/阈值）。

---

## 13. 覆盖矩阵

| U# | 要点 | S7 落点 |
|---|---|---|
| U-2 | agent 增效/前端价值 | S7-12 |
| U-3 | 海量节点 | S7-4/S7-11 |
| U-6 | 簇节点 | S7-2/S7-10 |
| U-10 | 关联维度 | S7-3/S7-10 |
| U-11 | 跳数 | S7-3 |
| U-12 | 更多维度 | S7-10 |
| U-13 | 非严格连通子图 | S7-2/S7-11 |
| U-14 | 语义小群 | S7-3/S7-11 |
| U-15 | 语义边一跳 | S7-3 |
| U-17 | 背后图不带入 | S7-3/S7-7 |
| U-19 | KP/簇节点 | S7-3/S7-7 |
| U-27 | 边存无/类型 | S7-2/S7-4/S7-7 |
| U-32 | 规模/后端检索 | S7-4/S7-8/S7-12 |

---

## 14. A-v2 变更表（逐条旧→新）

| # | 旧（v1） | 新（v2） | 裁决 |
|---|---|---|---|
| 1 | S7-3/5 四工具，无引用解析 | 增 `graph_resolve_ref`（只读/幂等/审计；走 DataSource/索引）；工具集 5 | R-S7-1 |
| 2 | S7-2/5 ViewResponse.edges 未明确只 shown；S7-4 与 S7-2 口径不一致 | edges[] 只含 shown；suppressed/unknown 只给 `suppressed_summary`+`rule_histogram`；逐条解释由 explain_edge 受控返回 | R-S7-2 |
| 3 | S7-5 工具名/错误码未逐码对齐 S6 | snake_case 5 工具；错误表逐码映射 S6+ADDENDUM-1（legacy/severity/i18n/audit_id）；v1 无 graph_path | R-S7-3 |
| 4 | `view_id`/`underlying_edge_count` | `view_model_id`/`frame_id`（仅审计）/`aggregate_count`；簇 `member_count` | R-S7-4 |
| 5 | 幂等未冻结；expand nav 边界未明确 | 幂等键 `(tool,args,edition,budget)`；expand 不改 S5 nav/stack；写 `GRAPH_WRITE_FORBIDDEN` | R-S7-5 |
| 6 | G7 未引用 G6；默认值散落 | 默认 4000/200（S8 可调）；G7 引用 G6 run_ids/frame_ids；S9 candidate_ref 归 S9；不夹带 S9/S10 | R-S7-6 |

## 15. 仍存争议 / 待 Lead·SE 裁决

1. **`graph_path` 是否 v1 提供**：本提案不提供；若需要必须显式 `allow_two_hop` + S5 `EXPLICIT_NEW_HOP`，是否放入 v1 待裁。
2. **token 预算默认值**：4000/200 为建议，S8 定；摘要降级阈值需 UX 定。
3. **S9 candidate_ref schema**：S7 只定义消费，S9 具体字段（kp/cluster/edge id/score）需 S9 接口定。
4. **S10 curation 写后刷新**：S7 只报 stale，刷新由 agent/工具编排还是 S9 自动，需 S10/S9 定。
5. **G7 指标阈值/隐私**：只记 id/anchor/计数，具体保留期/上报需 S8。
6. **Curation 人工确认**：确认人/界面归 S10/S3，S7 不定义。

---

## 16. 证据锚

```text
原话：vision.md:19-20（U-2/U-3）、:23（U-6）、:27-34（U-10..U-17）、:36（U-19）、:66（U-27）、:71（U-32）
S0：S0-terms-v1.md:81-85（S0-10 agent 三层）、:75-79（VM 纯度）、:87-90（S0-11）
S1：S1-dimensions-v1.md:99-107（present/VM）、:13-15（H/A）
S2：S2-clustering-v1.md:73-76（无簇）、:42-45（多归属）、:47-51（run）
S3：S3-visual-v1.md:36-39（presence）、:71-75（VM 白名单）
S4：S4-render-v1.md:26-29（focus 一跳）、:31-34（无隐式 2 跳）、:41-44（presence/rule）
S5：S5-nav-v1.md:16-19（frame）、:31-34（drill/back）、:47-50（维度可 back）
S6：S6-contract-v1.md:17-19（单一真源）、:39-43（VM）、:64-66（错误）、:75-78（0.5）
工程：ENGINEERING-PLAN.md:933-945（I-01..I-13）
现有 agent 面：resources/agent-prompts/**、agent-capabilities/*.json（只读证据，未展开）
```
