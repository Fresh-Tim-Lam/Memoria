# S6 提案 A-v2：数据契约收尾与 0.5 交付边界

> **修订依据**：`docs/design/multilevel-graph/S6-RULINGS.md`（R-S6-1..R-S6-6）。
> **本文件**：A 修订版；**不覆盖** `S6-contract-proposal-A.md`（v1 `af67ca9f…`），保留审计链。

> **提案方**：主办研究（`gm-seminar-researcher`）｜**票**：task-320｜**日期**：2026-11-03（Asia/Shanghai）
> **最高依据**：`docs/design/multilevel-graph-vision.md`（U-1..U-35）。
> **上游冻结（不得违反）**：S0（`241b1e1e…`）、S1（`6676c71d…`）、S2（`92bb0041…`）、S3（`0ca4ea0e…`+`S3-ADDENDUM-1`）、S4（`2576f6c8…`）、S5（`7f4c4515…`）。
> **本场章程**：`docs/design/multilevel-graph/S6-charter.md`（S6-1..S6-12）。
> **工程输入**：`ENGINEERING-PLAN.md`（ER/DFD/ST + P24–P31）、五份 engineering-check、`collector.py`/`edge_derivation.py`/`.memoria` sidecar/manifest。
> **独立性**：未阅读 S6 复核方草稿；本提案独立撰写。
> **纪律**：只写契约设计；不写产品代码/不改契约/不 commit。

---

## 0. 总口径

```
S0–S5 冻结语义 → S6 实现契约（schema/存储/错误/迁移/G6）→ 0.5 实现计划
单一真源：事实（.md + .memoria sidecar/manifest）只读 → DataSource → 派生（GraphView/run/VM/frame）
派生缓存可删除重建；D-3：不写产品 sidecar/新段；VM 纯；导航状态只在 Presentation。
```

**证据等级**：A（冻结条款/工程/代码事实）；B（单源实测）；C（推理）；**本项目假设**（路径/阈值/命名等显式约定）。

---

## 1. S6-1 契约范围与单一真源

**定义/规则（一句话）**：S6 只定义 DataSource/GraphView/VM/Frame/Nav/registry/run/cache/audit 的**只读契约与派生规则**；事实仍是 `.md` + `.memoria` sidecar/manifest；禁止并行事实源，禁止把派生写回产品 sidecar/新段（D-3）。

**实体范围（ER 定稿输入）**：
| 类 | 实体 | 归属 | 写入者 |
|---|---|---|---|
| 事实 | `DOCUMENT`、`KP_CONCEPT`、`KP_OCCURRENCE`、`EDGE_CANDIDATE`、`EDGE_PROVENANCE`、`.memoria` sidecar/manifest | 产品事实源 | 现有 product/curation（只读给图） |
| 配置 | `DIMENSION`/`DIMENSION_HISTORY`、`LEVEL`、`VIEW_FAMILY` | 版本化配置 | registry 管理流程 |
| 派生 | `CLUSTER_RUN`、`CLUSTER`、`MEMBERSHIP`、`CLUSTER_EDGE`、`CLUSTER_STABILITY`、`VIEW_MODEL`、`G6_SNAPSHOT` | 可再生缓存 | 图服务 |
| 视图状态 | `VIEW_FRAME`、`GRAPH_NAV_FRAME`、`NAV_STACK_ENTRY`、selection | Presentation/会话 | S5/Presentation |
| 审计 | `AUDIT_EVENT` | append-only 审计事实 | 服务/UI |

**单一真源规则**：
```
FactSource = .md 正文 + .memoria sidecar/manifest（只读；图不得写）
DataSource = FactSource 的只读投影（可重建；不新增事实字段）
GraphView = DataSource + S2 run 的视图投影（派生）
VM = S4 Admission 的派生结果（派生；缓存可重建）
Frame/Nav = Presentation 视图状态（不是事实；不进 VM）
禁止：graph 写 sidecar/新段；VM 写回 DataSource；run/簇写入产品 sidecar；第二份 KP/边事实
```
**与 `.memoria` 关系**：
```
sidecar：提供 KP 元数据、links、contain curation overlay 输入（只读）
manifest：提供 corpus_manifest_sha/collect_version（只读）
build：派生缓存（可删）；不写 `.memoria/sidecars/**` 或 manifest
```
**反例**：把 cluster/membership 写进 sidecar（D-3）；VM 直接读库绕过 DataSource；并行维护第二份边表；把 view 出现当 membership。
**边界**：sidecar 缺失/损坏；manifest edition 变化；旧 graph payload 只读；多 KB 不跨库。
**机检条件**：
```
- 事实源写路径只有现有 product/curation；图服务写权限白名单不含 sidecar/manifest
- DataSource 只读；派生缓存删除后可重建同一 contract 输出
- 无并行事实源（同一 KP/边只有一个权威来源）
- D-3：无 sidecar/新段写入断言
```
**U 映射**：U-1、U-29、U-32、U-34。
**建议裁决**：采纳实体归属/单一真源/只读 DataSource/D-3。
**证据等级**：A（S0-10/D-3；`collector.py:46-99`；`ENGINEERING-PLAN.md:201-222`）；**本项目假设**（缓存/审计路径）。

---

## 2. S6-2 DataSource / GraphView / C-* 契约

**定义/规则（一句话）**：DataSource 是只读事实投影；GraphView 是 `(level,view_family)` 的派生视图；S0 C-1..C-6 差异均已冻结，S6 只落 schema 与接口。

**DataSource schema（只读）**：
| 字段 | 类型 | 枚举/默认 | 失败码 |
|---|---|---|---|
| `schema_version` | string | `"ds-v1"` | `GRAPH_SCHEMA_INVALID` |
| `kb_path` | string | — | `GRAPH_INPUT_INVALID` |
| `corpus_manifest_sha` | string(64) | — | `GRAPH_EDITION_INVALID` |
| `collect_version` | string | — | `GRAPH_EDITION_INVALID` |
| `nodes[]` | KP_NODE[] | kind=`kp` | `GRAPH_NODE_INVALID` |
| `edges[]` | EDGE[] | 见下 | `GRAPH_EDGE_INVALID` |
| `read_only` | bool | `true`（常量） | `GRAPH_MUTATION_FORBIDDEN` |
| `warnings[]` | string[] | `[]` | — |

```
KP_NODE{node_id:"kp:<id>", kind:"kp", kp_id, label, description?, file, occurrence_ids[],
        range_ok:bool=true, provenance{...}}
EDGE{edge_id:canonical(type|source|target), type∈{contain,reference,extend},
     contain_kind∈{structural,semantic}|null, label∈{semantic,structural,navigation}|null,
     source,target, direction, provenance?}
接口（只读）：
  get_kp(kp_id) / list_kp(filter) / get_edge(edge_id) / list_edges(filter)
  expand_data_edges(ids) ⊆ DataSource.edges    # R-3
```
**GraphView schema**：
```
GraphView{view_id, level_id, view_family_id, basis, run_id?, nodes[], edges[], partition[]}
GraphViewNode{node_id, kind∈{kp,cluster}, cluster_ref?{run_id,local_seq}, label}
GraphViewEdge{edge_id, type, contain_kind?, label?, source,target, data_edge_ids?（审计）}
partition：同 (level,view_family) 不交、并=K_f（S0-2）；跨族可重叠
```
**C-* 冻结映射**：
| C | 内容 | S6 落点 |
|---|---|---|
| C-1 | `view_family` 唯一定义 | GraphView.view_family_id / run scope |
| C-2 | 事件集 `nodeClick/edgeClick/backgroundClick` | S6-5 VM/S3 事件 |
| C-3 | bridge 只作 edge state + 成员统计 | S6-4/S6-5 |
| C-4 | partition 机检对象 `(level,view_family)` | GraphView.partition |
| C-5 | `DIMENSION.status` 枚举 | S6-3 registry |
| C-6 | capabilities 由 Renderer 提供、不进 VM | S6-5 |
**反例**：DataSource 含 cluster/VM 字段；GraphView 跨族合并；DataSource 可写；用 view 出现当成员。
**边界**：空 KB；无 semantic；多归属；sidecar 损坏 warning；旧 payload。
**机检条件**：
```
- DataSource schema/字段/只读；EDGE canonical id；E_relation_min 只增不删
- GraphView partition 断言；kind∈{kp,cluster}；跨族不合并
- C-1..C-6 与冻结条款一致；DataSource 无 cluster run/VM 状态
```
**U 映射**：U-1、U-4、U-21、U-31、U-32。
**建议裁决**：采纳 DataSource/GraphView schema 与 C-* 冻结映射。
**证据等级**：A（S0-2/S0-3/S0-7/R-2/R-3；`collector.py:46-99`；`edge_derivation.py:787-793`）；**本项目假设**（字段名/接口名）。

---

## 3. S6-3 维度注册表与 history schema

**定义/规则（一句话）**：DIMENSION 字段/枚举/默认/失败码按 S1；history 为 append-only 不可变链；跨版本只增不删；history 断链/字段不符 fail-closed；删除/改名关系源 ⇒ `S0_REOPEN`。

**DIMENSION schema（S1 冻结 + S6 存储字段）**：
| 字段 | 类型 | 枚举/默认 | 失败码 |
|---|---|---|---|
| `id` | string | 唯一 | `GRAPH_DIM_ID_INVALID` |
| `name` | string | 非空 | `GRAPH_DIM_NAME_INVALID` |
| `kind` | enum | `hierarchy_navigation`\|`relation_expansion` | `GRAPH_DIM_KIND_INVALID` |
| `basis.kind` | enum(派生) | 必须=map(kind) | `GRAPH_DIM_KIND_MISMATCH` |
| `relation_sources` | string[] | H=[]；A⊇E_relation_min | `GRAPH_DIM_SOURCES_INVALID` |
| `direction` | enum | `down/up/both/out/in`；H=down，A=both | `GRAPH_DIM_DIRECTION_INVALID` |
| `hop_unit` | enum | `edge`\|`n/a`；H=n/a | `GRAPH_DIM_HOP_UNIT_INVALID` |
| `hop_default`/`hop_max` | int|null | H=null；A=1/2 | `GRAPH_DIM_HOP_INVALID` |
| `termination.*` | mixed | 见 S1 | `GRAPH_DIM_TERMINATION_INVALID` |
| `status` | enum | `reserved/active/deprecated`；默认 reserved | `GRAPH_DIM_STATUS_INVALID` |
| `priority` | int | 唯一；默认 0 | `GRAPH_DIM_PRIORITY_DUPLICATE` |
| `version` | string | 非空 | `GRAPH_DIM_VERSION_INVALID` |
| `history_ref` | string | 末条 content_sha==registry_sha | `GRAPH_DIM_HISTORY_REF_INVALID` |
| `fallback_policy` | enum | `allow/forbidden`；默认 allow | `GRAPH_DIM_FALLBACK_INVALID` |
| `registry_sha` | string(64) | canonical hash | `GRAPH_DIM_REGISTRY_SHA_INVALID` |

**DIMENSION_HISTORY_ENTRY schema（append-only；R-S6-4）**：
```
history_id = content_sha = sha256(canonical(entry 不含 signature))
entry{history_id, version, relation_sources[], active_dimensions[],
      previous_sha|null, decision_id, created_at, author, payload_sha,
      signature?: {alg:"ed25519"|"hmac-sha256", key_id:string, sig:string},
      signed: bool}
retrieval: get_history(content_sha) -> entry（缺失 ⇒ GRAPH_HISTORY_MISSING）
签名位置：同目录 detached `<content_sha>.sig` 或 `signature` 字段落盘（S6a 二选一；不得只口头）
无签名：signed=false；G6 快照必须标记 signed=false（不阻断读取）
签名验证失败 ⇒ fail-closed GRAPH_HISTORY_SIGNATURE_INVALID
校验：previous_sha 链闭合；末条 content_sha==registry_sha；
      new.relation_sources ⊇ old.relation_sources；删除/改名 ⇒ S0_REOPEN
```
**反例**：history 可改写/删除；跨版本删关系源不报 S0_REOPEN；registry 缺字段/重复 priority；把 `graphStyle` 当维度。
**边界**：首次 registry（previous=null）；reserved 维度；history 文件损坏；旧版本取回。
**机检条件**：
```
- 字段/枚举/默认/失败码完整；registry_sha 可复算
- history 链闭合、只追加、content_sha 唯一；末条绑定 registry
- 只增不删；删除/改名触发 S0_REOPEN；未知/保留 fail-closed
```
**U 映射**：U-8、U-9、U-24、U-25、U-34。
**建议裁决**：采纳 registry/history schema、不可变链、只增不删/S0_REOPEN。
**证据等级**：A（S1-2/S1-11/R-S1-9；`ENGINEERING-PLAN.md` registry）；**本项目假设**（history 存储路径/签名字段）。

---

## 4. S6-4 簇 run / membership / 身份 schema

**定义/规则（一句话）**：run 由 6 元组稳定编码；`params_hash` 字段集按 S2 冻结；cluster 身份 = `cluster_id(run_id+local_seq)` + `cluster_key`；membership 多归属；五状态；stale/curation 必须双引用 run+key。

**CLUSTER_RUN schema**：
| 字段 | 类型 | 枚举/默认 | 失败码 |
|---|---|---|---|
| `run_id` | string(64) | 公式见下 | `GRAPH_RUN_ID_INVALID` |
| `corpus_manifest_sha` | string(64) | — | `GRAPH_EDITION_INVALID` |
| `level_id`/`view_family_id` | string | — | `GRAPH_SCOPE_INVALID` |
| `algorithm_id`/`algorithm_version` | string | `hac-average` | `GRAPH_ALGO_INVALID` |
| `params_hash` | string(64) | 字段集下 | `GRAPH_PARAMS_INVALID` |
| `params` | object | `{weight_policy:"semantic_uniform",linkage:"average", tie_break:"min_canonical_id", cut_policy,target_k,min_cluster_size,n_max,tau_coh,tau_bridge}` | `GRAPH_PARAMS_INVALID` |
| `status` | enum | `ok/no_semantic_edges/partial_disconnected/size_exceeded/algorithm_failed` | `GRAPH_RUN_STATUS_INVALID` |
| `parent_run_id` | string|null | 上一层同 family | `GRAPH_PARENT_INVALID` |
| `edition_sha` | string(64) | — | `GRAPH_EDITION_INVALID` |

```
run_id = sha256(canonical(corpus_manifest_sha, view_family_id, level_id,
                         algorithm_id, algorithm_version, params_hash))
CLUSTER{cluster_id = f"{run_id}:{local_seq}", run_id, local_seq,
        cluster_key, member_count, mu, beta, representative, root_exempt,
        label, label_key}
MEMBERSHIP{run_id, cluster_id, kp_id, role:"member", source:"derived_cluster"}
CLUSTER_EDGE{edge_id, run_id, cluster_id, kind:"internal_sem"|"bridge_sem", data_edge_ids[]}
```
**身份/多归属/stale**：
```
cluster_id 是 run-scoped 实例 id；cluster_key = sha256(canonical(sorted(member_canonical_ids))
  + algorithm_id + algorithm_version + params_hash)（D-2）
同一 (level,view_family) 内单归属；跨族/层/维多归属；v1 不设上限
stale：corpus_manifest/params/algorithm/registry 变化 ⇒ 新 run；旧 run 只读
curation 引用必须 {run_id, cluster_key}；key 不匹配 ⇒ stale（拒用）
```
**反例**：用内容哈希当实例 id；run_id 不含 level；membership role=bridge；单值 nodeToGroup；旧 run 被覆盖；curation 只记 key。
**边界**：no_semantic_edges（全 singleton）；algorithm_failed；multi-membership；旧 run GC。
**机检条件**：
```
- run_id 公式可复算；params 字段集完整；五状态枚举
- cluster_id/key 可复算；同族单归属；跨族多归属
- 旧 run 只读；curation 双引用；stale 可判定
```
**U 映射**：U-6、U-13、U-14、U-21、U-31。
**建议裁决**：采纳 run/cluster/membership schema、五状态、双引用身份。
**证据等级**：A（S2-7/S2-11/R-S2-10；D-2/D-3；`ENGINEERING-PLAN.md:209-212`）；**本项目假设**（参数默认值/S8 范围）。

---

## 5. S6-5 Visual / VM schema

**定义/规则（一句话）**：VM 严格按 S3 白名单 + ADDENDUM-1（节点 presence/rule_id），token/encoding map 可机检，`data_edge_ids` 可审计但 Renderer 禁读，capabilities 由 Renderer 提供。

**ViewModel schema**：
| 字段 | 类型 | 枚举/默认 | 失败码 |
|---|---|---|---|
| `view_model_id` | string | — | `GRAPH_VM_ID_INVALID` |
| `level_id`/`level_label?` | string | — | `GRAPH_VM_LEVEL_INVALID` |
| `dimension_id` | enum | H/A | `GRAPH_VM_DIM_INVALID` |
| `view_family_id` | string | — | `GRAPH_VM_FAMILY_INVALID` |
| `nodes[]` | VM_NODE[] | kind∈{kp,cluster}；presence? see addendum | `GRAPH_VM_NODE_INVALID` |
| `edges[]` | VM_EDGE[] | presence, rule_id | `GRAPH_VM_EDGE_INVALID` |

```
VM_NODE{id, kind, label, role:"member", member_count?, aggregate_count?,
        representative?, root_exempt?, range_ok?, layout_group?{semantic:false},
        presence?∈{shown,suppressed,unknown}, rule_id?}
VM_EDGE{id, source,target,type,contain_kind?,label?,display_type,
        presence∈{shown,suppressed,unknown}, rule_id?,
        state?:"bridge_only", hop?, underlying_hop_count?, aggregate_count?,
        data_edge_ids?（仅审计；Renderer 禁读）}
VISUAL_ENCODING_MAP{selector, token_kind∈{color,size,shape,opacity,dash,icon,label},
                    token_value, priority, fallback, map_sha256}
RendererCapabilities{backend:"2d"|"3d", supportsAnimation/Keyboard/Aria,
                    maxNodes:int, maxEdges:int, capabilities_sha}
```
**规则**：只画 `presence=shown`；`data_edge_ids` 审计禁读；`aggregate_count` 显式不遍历；2D/3D 同 VM id 集；未知 presence fail-closed。
**反例**：VM 带 metrics/nav/mode；Renderer 读 data_edge_ids；node presence 未按 addendum；2D/3D id 不同。
**边界**：无簇 layout_group；node presence 扩展；capabilities 3D 不可用；空 VM。
**机检条件**：
```
- VM 白名单/字段/枚举；node/edge presence+rule_id（addendum）
- token map 可机检（selector→token）；map_sha256 可复算
- Renderer 无 data_edge_ids 读取/无重算；2D/3D capabilities 显式
```
**U 映射**：U-3、U-16、U-27、U-33。
**建议裁决**：采纳 VM/visual schema 与 addendum、Renderer 禁读 data_edge_ids。
**证据等级**：A（S3-12/R-S3-9；S3-ADDENDUM-1；`ENGINEERING-PLAN.md:224-250`）；**本项目假设**（token map 字段名）。

---

## 6. S6-6 Frame / presence / rule_id schema

**定义/规则（一句话）**：`FRAME_SPEC` 是 S4 输入；`ADMISSION_RESULT` 携带全部候选节点/边逐条 presence/rule_id；presence 三值、11 类 rule_id、MANDATORY/budget/subset 证明与失败码统一。

**FRAME_SPEC schema（严格等于 S4 冻结输入；R-S6-2）**：
```
S4_FRAME_SPEC{level_id, view_family_id, dimension_id, focus_id,
              hop_budget:1|2|null, new_hop:bool=false,
              mode:"default"|"full", budget{max_nodes,max_edges}}
# 仅以上字段进入 S4；不得含 frame_id/edition/nav_id
S5 派生：frame_id = sha256(canonical(S4_FRAME_SPEC))
S5 本地：edition_sha 由 S5 从 corpus_manifest/collect_version 派生并本地校验
NAV_FRAME（Presentation）= S4_FRAME_SPEC + frame_id + edition_sha
失败码：GRAPH_FRAME_ID_INVALID / GRAPH_EDITION_INVALID
```
**PRESENCE_RECORD / ADMISSION_RESULT**：
```
PRESENCE_RECORD{candidate_id, kind:"node"|"edge", presence∈{shown,suppressed,unknown},
                rule_id, hop?, aggregate_count?}
ADMISSION_RESULT{candidates[], mandatory_ids[], shown/suppressed/unknown counts,
                 budget, subset_proof?, errors[]}
RULE_IDS（11 类）= {dimension.sources, dimension.direction,
  dimension.level.cross_layer, hop.budget, node.budget, edge.budget,
  cluster.folded, endpoint.unresolved, source.unavailable,
  admission.undecided, invalid.data}
unknown 仅 endpoint.unresolved/source.unavailable/admission.undecided/invalid.data
MANDATORY：A={focus}；H={focus}+first K children（K=2，S8 可调）
subset_proof：candidates(full)⊇candidates(default) ∧ reserved(full)==shown(default)
             ∧ budget_full≥budget_default
```
**失败码**：
`GRAPH_FRAME_ID_INVALID`、`GRAPH_HOP_INVALID`、`GRAPH_PRESENCE_RULE_MISSING`、`GRAPH_BUDGET_INVALID`、`GRAPH_SUBSET_UNPROVEN`、`GRAPH_FOCUS_UNRESOLVED`、`GRAPH_RENDER_BUDGET_EXCEEDED`。
**反例**：presence != shown 也画；rule_id 不在枚举；unknown 当"无关系"；MANDATORY 超预算整屏失败；full 无 subset proof；把 frame_id/edition 塞进 S4 输入。
**边界**：预算恰好/不足；unknown；空候选；full candidate 超集不成立；初始帧失败。
**机检条件**：
```
- presence 三值；每条候选有 rule_id；unknown 仅 4 类
- MANDATORY 可枚举且 ≤cap；仅 MANDATORY 超预算 ⇒ BUDGET_INVALID
- subset 构造证明；S4_FRAME_SPEC 字段集严格；frame_id 由 S5 可复算；失败码可枚举
```
**U 映射**：U-3、U-16、U-18、U-27、U-32。
**建议裁决**：采纳 frame/presence/rule schema、MANDATORY/subset 证明、失败码。
**证据等级**：A（S4-2/4/5/6/9；R-S4-1..10）；**本项目假设**（错误码命名由 S6-9 统一）。

---

## 7. S6-7 Nav schema（GraphNavFrame/NAV_STACK/NAV_EVENT，T01–T30）

**定义/规则（一句话）**：`GraphNavFrame`/`NAV_STACK_ENTRY`/`NAV_EVENT` 只在 Presentation；**唯一导航身份是 `frame_id`**（`nav_id` 仅为文档别名，不作 schema 字段）；`frame_id` 由 S5 从 `S4_FRAME_SPEC` 派生；T01–T30 为唯一真源，S5a 由表生成；持久化只白名单。

**GraphNavFrame schema**：
| 字段 | 类型 | 枚举/默认 | 失败码 |
|---|---|---|---|
| `frame_id` | string | `sha256(canonical(S4_FRAME_SPEC))`（S5 派生） | `GRAPH_FRAME_ID_INVALID` |
| `focus_id` | string|null | 进入图后非空 | `GRAPH_NAV_FOCUS_INVALID` |
| `level_id`/`view_family_id` | string | — | `GRAPH_NAV_SCOPE_INVALID` |
| `dimension_id` | enum | H/A | `GRAPH_NAV_DIM_INVALID` |
| `hop_budget`/`new_hop` | int|null / bool | H=null；A 1/2；默认 false | `GRAPH_NAV_HOP_INVALID` |
| `mode` | enum | `default/full` | `GRAPH_NAV_MODE_INVALID` |
| `budget` | object | `{max_nodes,max_edges}` | `GRAPH_NAV_BUDGET_INVALID` |
| `origin` | object | `{from_frame_id,via_cluster_id,via}` | `GRAPH_NAV_ORIGIN_INVALID` |
| `edition_sha` | string(64) | — | `GRAPH_EDITION_INVALID` |

```
NAV_STACK_ENTRY{seq, frame_id, focus_id, level_id, dimension_id, hop, new_hop,
                mode, origin_cluster_id, via}
NAV_EVENT{event_id, type, payload, frame_id, at}
事件集（21）：OPEN_GRAPH, DATA_READY, DATA_FAILED, RETRY, DATA_REFRESHED,
 CLOSE, RELOAD, RESET, CLICK_KP, CLICK_CLUSTER, CLICK_EDGE, CLICK_BACKGROUND,
 BACK, BREADCRUMB_TO, FOCUS_NODE, FOCUS_CLEAR, FOCUS_LOST,
 SELECT_DIMENSION, EXPLICIT_NEW_HOP, TOGGLE_EXPAND, CORPUS_CHANGED
```
**T01–T30 表（冻结；唯一真源）**：直接引用 `S5-nav-v1.md:117-155` 附录 A 30 组（S6 不重写语义，只给机器格式）：
```
NAV_TRANSITION{id:"T01".."T30", from:set<state>, event, guard, action, to:set<state>|SELF}
约束：主状态 9；FullExpanded/EmptyNoSemantic 为 mode/data_state 正交变量（非状态）；
     (state,event) 唯一；ALL\{Idle} CLOSE 展开 8 边；全表展开 148 边；
     S5a 由表逐条生成；PARSE_OK；表/图状态集、边集、事件集一致
```
**持久化白名单**：
```
保存：level0 frame + mode + dimension + 设置；不保存深栈/selection/UI focus（D-ST-07）
frame_id = sha256(canonical(S4_FRAME_SPEC))（S5 R-S5-9；S5 派生，不传 S4）
```
**反例**：把 nav 写进 VM；`nav_id` 作 schema 字段；frame_id 自造；持久化深栈；T01–T30 与 S5a 不一致；FullExpanded 当状态。
**边界**：Idle CLOSE no-op；Stale RESET；空栈 BACK；维度切换 push；恢复 level0。
**机检条件**：
```
- Nav schema 字段/枚举/失败码；frame_id 可复算
- T01–T30 与 S5 v1 附录 A 完全一致；S5a 由表生成；表/图集合一致
- 持久化白名单；VM 无 nav；CLOSE/RELOAD/RESET 清 history
```
**U 映射**：U-1、U-4、U-7、U-8、U-9、U-24、U-29。
**建议裁决**：采纳 Nav schema、T01–T30 唯一真源、持久化白名单。
**证据等级**：A（S5-1..S5-12/R-S5-9..12；`S5-nav-v1.md:117-155`）；**本项目假设**（NAV_EVENT 字段/存储）。

---

## 8. S6-8 存储 / 审计 / GC / 版本

**定义/规则（一句话）**：派生缓存可删除重建；审计 append-only；GC 只删派生；`edition`/stale 可判定；D-3 禁止写产品 sidecar/新段。

**存储布局（建议；S6a 定稿）**：
```
事实：.memoria/sidecars/**、manifest（只读）
配置：.memoria/config/graph/registry.json、history/<content_sha>.json
派生缓存：.memoria/cache/graph/{level}/{view_family}/{run_id}.json
          .memoria/cache/graph/vm/<frame_id>_<edition>.json
审计：.memoria/agent/audit/graph/events.jsonl（append-only）
G6：artifacts/graph/g6/<snapshot_id>.json
```
**CACHE_MANIFEST schema**：
```
cache_manifest{cache_schema_version, cache_key=sha256(canonical(contract_version,
  edition_sha, run_id/frame_id)), generated_at, source_edition_sha,
  contract_version, rebuildable:true, files[]{path,sha256,bytes}}
```
**AUDIT_EVENT schema**：
```
audit_event{event_id=sha256(canonical(seq,kind,actor,payload)), seq, at, kind,
            actor, payload, prev_event_id|null}
kind ∈ {run.create,run.adopt,run.gc,curation.ref,agent.request,
        nav.transition,error,registry.update,migration}
```
**GC/version**：
```
GC 只删派生缓存：保留 adopted/current + 最近 N=20 run 或 90 天（先到者）；registry history 永不 GC；审计 append-only 不 GC；不删事实
版本：contract_version(semver)、cache_schema_version、registry_version、
      vm_schema_version、nav_schema_version；不兼容 ⇒ 缓存 miss/重建
stale：edition_sha 不匹配 ⇒ stale；不自动重取景（提示）
D-3：禁止写 .memoria/sidecars/**、manifest、产品新段
回滚：删除派生缓存/清 registry 新版本（history 保留）→ 旧版读取；事实不变
```
**反例**：缓存写 sidecar；GC 删 registry history/审计/事实；版本不兼容仍读；stale 自动重取景；审计可改。
**边界**：缓存损坏；GC 并发；registry 新版本回滚；cache miss；edition 变。
**机检条件**：
```
- 缓存路径不在事实源；删除后重建同 contract 输出
- cache_manifest sha/rebuildable 完整；审计 append-only/链
- GC 不删事实；stale 可判定；D-3 无写
```
**U 映射**：U-29、U-32、U-34。
**建议裁决**：采纳存储/审计/GC/版本策略；路径由 S6a 定稿。
**证据等级**：A（S0-10/D-3；S2-11；`ENGINEERING-PLAN.md:201-222,562`）；**本项目假设**（具体路径/GC 数值）。

---

## 9. S6-9 错误 / 失败语义统一

**定义/规则（一句话）**：统一命名空间 `GRAPH_*`；每个失败码声明 `origin(S2–S5)`、`policy(fail-closed/degrade/fallback)`、`i18n_key`；未知错误不静默。

**失败码表（节选/完整命名空间）**：
| 码 | origin | 策略 | i18n |
|---|---|---|---|
| `GRAPH_INPUT_INVALID` | DS | fail-closed | `graph.error.input` |
| `GRAPH_EDITION_INVALID/STALE` | S4/S5 | fail-closed/提示 | `graph.error.edition` |
| `GRAPH_SCHEMA_INVALID` | S3/S6 | fail-closed | `graph.error.schema` |
| `GRAPH_DIM_ID_INVALID/KIND/SOURCES/DIRECTION/HOP/STATUS/...` | S1 | fail-closed | `graph.error.dim` |
| `GRAPH_DIM_UNKNOWN/NOT_ACTIVE/COMBINATION_UNSUPPORTED` | S1 | fail-closed | `graph.error.dim` |
| `GRAPH_REGISTRY_INVALID/HISTORY_MISSING/HISTORY_CHAIN` | S6 | fail-closed | `graph.error.registry` |
| `GRAPH_HISTORY_SIGNATURE_INVALID` | S6 | fail-closed | `graph.error.registry` |
| `GRAPH_RUN_ID_INVALID/PARAMS_INVALID/RUN_STATUS_INVALID` | S2 | fail-closed | `graph.error.run` |
| `GRAPH_CLUSTER_ALGO_FAILED/SIZE_EXCEEDED` | S2 | degrade/empty | `graph.error.cluster` |
| `GRAPH_FRAME_ID_INVALID/HOP_INVALID` | S4/S5 | fail-closed | `graph.error.frame` |
| `GRAPH_PRESENCE_RULE_MISSING` | S4 | fail-closed | `graph.error.presence` |
| `GRAPH_BUDGET_INVALID` | S4 | fail-closed/degrade | `graph.error.budget` |
| `GRAPH_SUBSET_UNPROVEN` | S4 | fallback default | `graph.error.full` |
| `GRAPH_RENDER_BUDGET_EXCEEDED` | S3 | fail-visible | `graph.error.render_budget` |
| `GRAPH_NAV_ILLEGAL_TRANSITION` | S5 | fail-closed | `graph.error.nav` |
| `GRAPH_NAV_FOCUS_INVALID` | S5 | recover root | `graph.error.focus` |
| `GRAPH_CACHE_CORRUPT` | S6 | rebuild | `graph.error.cache` |
| `GRAPH_MIGRATION_UNSUPPORTED` | S6 | fail-closed | `graph.error.migration` |
| `GRAPH_INTERNAL` | S6 | fail-visible | `graph.error.internal` |

**canonical / legacy**：`GRAPH_*` 为唯一 canonical；每条错误记录 `{canonical_code, legacy_code?}`，legacy 保留 S2–S5 旧码（如 `S4_BUDGET_INVALID`/`S5_ILLEGAL_TRANSITION`）供审计与迁移；新 API 只返回 canonical。
**映射**：S2 `no_semantic_edges` 不是错误（`data_state`）；S4 `S4_BUDGET_INVALID` → `GRAPH_BUDGET_INVALID`；S5 `S5_ILLEGAL_TRANSITION` → `GRAPH_NAV_ILLEGAL_TRANSITION`；DIM_* → `GRAPH_DIM_*`；history 签名失败 → `GRAPH_HISTORY_SIGNATURE_INVALID`。
**反例**：同一个失败多套名字；未知错误静默；错误改写事实；i18n 文案在渲染器。
**边界**：初始帧失败/非初始失败；降级 vs fail-closed；旧码兼容。
**机检条件**：
```
- 失败码命名空间/字段完整；origin/policy/i18n 映射
- 未知错误不静默；错误不写事实；文案在 i18n 资源
- S2–S5 错误码可映射
```
**U 映射**：U-29、U-32、U-34。
**建议裁决**：采纳 `GRAPH_*` 命名空间 + 映射/策略/i18n；未知错误 `GRAPH_INTERNAL`。
**证据等级**：A（S1–S5 失败码；`ENGINEERING-PLAN.md` 错误/DFD）；**本项目假设**（码名/策略）。

---

## 10. S6-10 兼容 / 迁移

**定义/规则（一句话）**：不做破坏性迁移；旧 graph-groups/旧 payload 只读/忽略，新契约重新派生；edition 不兼容 ⇒ stale/重建；回滚 = 删派生缓存/回退契约版本，事实不变。

**迁移矩阵**：
| 旧对象 | 处置 | 迁移？ |
|---|---|---|
| `graph-groups.js` 前端分组 | 不再作为簇；由 S2 run 重算 | 否（忽略） |
| 旧 payload `loadPayload` | 只读 fallback（可选） | 否 |
| 旧缓存 `.memoria/build/**` | cache_schema 不匹配 ⇒ 重建 | 派生 |
| registry 旧版 | history 保留；只增不删 | 是（只追加） |
| sidecar/manifest | 只读；不改结构 | 否 |
| 旧 graph 审计/交互计数 | 不导入为图事实 | 否 |
**规则**：
```
无破坏性迁移：不删/不改用户事实；不写 sidecar/新段
edition 兼容：contract_version/cache_schema/registry_version 匹配才复用缓存
回滚：删除新缓存/关闭 feature flag/契约版本回退；旧只读 fallback 可用
失败：不兼容 ⇒ GRAPH_MIGRATION_UNSUPPORTED（可见），不静默降级
```
**反例**：迁移改写 sidecar；删旧数据；cache 版本不匹配仍读；回滚改事实；旧 graph-groups 当簇。
**边界**：旧 KB 无 registry；旧缓存损坏；rollback 后旧 payload 缺字段；future version。
**机检条件**：
```
- 迁移不写事实；旧 sidecar/manifest sha 不变
- cache_schema/contract_version 检查；不兼容重建/拒绝
- 回滚不改变事实；旧 graph-groups 不进入簇
```
**U 映射**：U-29、U-32、U-34。
**建议裁决**：采纳“忽略旧 groups/派生重建/无破坏性迁移/可回滚”。
**证据等级**：A（S0-10/D-3；S2-11；`graph-groups.js:83-134` 现状无版本）；**本项目假设**（fallback 策略）。

---

## 11. S6-11 G6 快照 / 复跑 / 度量

**定义/规则（一句话）**：G6 快照是契约输出（DataSource/run/registry/VM/frame/nav/token）的规范化哈希；可复跑命令、sha 稳定、阈值明确；不含随机/时间敏感字段（除 created_at 外）。

**G6_SNAPSHOT schema（R-S6-6 统一字段）**：
```
G6_SNAPSHOT{g6_version, snapshot_id, created_at, contract_version,
  data_source_sha, run_ids[], registry_sha,
  vm_sha, frame_ids[], frame_sha, nav_sha,
  rule_histogram{rule_id:count}, node_count, edge_count,
  subset_ok:bool, determinism_sha, closure_violations:0, behind_violations:0,
  edition{corpus_manifest_sha, collect_version},
  history_signed:bool, command, tool_env}
snapshot_id = sha256(canonical(snapshot 除 snapshot_id/created_at))
```
**复跑/阈值**：
```
命令示例：python scripts/verify/g6_snapshot.py --kb <kb> --level L0 --dim H
复跑：同 edition/contract/registry/params ⇒ deterministic_sha256 相同
阈值（S8 可调）：determinism 100%；subset_ok=true；closure/behind=0；
  render budget 内；G6 输出无 sidecar 写入；schema 校验 PASS
```
**反例**：sha 含时间；随机排序；不同环境浮点；只截屏无数据；snapshot 含正文隐私。
**边界**：空 KB；no_semantic；多归属；full/default 两快照；跨机器。
**机检条件**：
```
- snapshot 字段/sha 可复算；命令可复跑；同输入同 sha
- 阈值可断言；隐私字段不含正文
- 与 DataSource/run/VM/frame/nav 引用闭合
```
**U 映射**：U-29、U-32、U-34。
**建议裁决**：采纳 G6 schema/复跑/阈值；命令路径 S6a 定。
**证据等级**：A（U-32；S3-11/S4-12/S5-12 G6 字段）；**本项目假设**（命令/阈值）。

---

## 12. S6-12 0.5 交付边界与 S6a 接口清单

**定义/规则（一句话）**：0.5 只实现已冻结语义的 v1 子集：DataSource 只读、H/A、S2 run、S4 admission、S3 2D 渲染、S5 导航基础、缓存/审计/G6；3D/agent 写/自动语义等明确不做；验收门禁与 S6a 接口清单固定。

**0.5 实现范围**：
| 能力 | 0.5 | 说明 |
|---|---|---|
| DataSource 只读/KP/边 | ✅ | facts 投影 |
| registry H/A | ✅ | v1 单维度 |
| S2 HAC run/簇/成员 | ✅ | 无 semantic ⇒ no_semantic 合法 |
| S4 admission/预算/rule_id | ✅ | 唯一裁剪 |
| S3 2D Renderer/VM/事件/a11y | ✅ | 2D 先发 |
| S3 3D Renderer | ⛔ 不做（接口/capabilities 预留） | S3 同签名契约保留 |
| S5 Nav 基础（drill/back/dimension/full） | ✅ | 事务化 |
| agent 写/自动 semantic | ⛔ | S10 后续 |
| 跨 KB/时间维/图编辑 | ⛔ | S0-11 范围外 |
| 旧 graph-groups 迁移 | ⛔ 忽略 | 派生重建 |
**明确不做（0.5）**：
```
S7–S10 不在 0.5（agent 使用/度量/后端检索/知识点设计后续场次）
3D 渲染实现、agent 自动 semantic、跨库、时间维、图编辑器、
破坏性迁移、把簇/成员写产品 sidecar/新段、第二事实源、
未冻结的新边类型/新维度、URL 深导航 schema（S6a/后续）
```
**验收门禁**：
```
1) S6a schema/ER/DFD/ST 与 S0–S5 一致；mermaid PARSE_OK
2) G6 deterministic/sha 稳定；subset_ok；closure/behind=0
3) 无 sidecar/manifest 写入（D-3）；缓存可删重建
4) VM 纯度/2D-3D 同签名（3D 可 capability=false）；nav 事务 diff=0
5) 失败码命名空间/映射；a11y 基线；性能预算
```
**S6a 接口清单**：
```
ER：DataSource/GraphView/VM/Frame/Registry/History/Run/Cluster/Membership/
    VisualEncodingMap/RenderBackend/NavFrame/Stack/Audit/G6
DFD：P1/P2/P3/P4/P5/P6/P7/P8/P9/P10 + P24–P31（S4）
ST：T01–T30 + S5a；VIEW_FRAME/GRAPH_NAV_FRAME
API：get_kp/list_edges/expand_data_edges; get_registry/get_history;
     list_runs/get_run; build_vm(frame_spec); Renderer.getCapabilities/render/update/
     dispose/on; nav.apply(event); g6.snapshot()
```
**反例**：0.5 偷偷做 3D/agent 写；把旧 groups 迁移；写 sidecar；扩展未冻结维度；验收只截图。
**边界**：2D-only capability；无 semantic 数据；旧 KB；性能低端。
**机检条件**：
```
- 0.5 范围表与 S0-11 一致；不做项有守卫/feature flag
- 验收门禁可执行；S6a 接口清单闭合
- 3D capability=false 时 Renderer 仍同签名
- 无 sidecar 写入/无第二事实源/G6 可复跑
```
**U 映射**：U-3、U-16、U-27、U-32、U-33、U-34。
**建议裁决**：采纳 0.5 范围/不做项/验收门禁/S6a 接口清单；3D 实现延后但接口保留。
**证据等级**：A（S0-11 范围；S3-6 2D/3D 同签名；S5 导航；U-32/U-34）；**本项目假设**（0.5 子集/验收阈值）。

---

## 13. 覆盖矩阵

| 侧 | 覆盖 | 落点 |
|---|---|---|
| S0 | S0-2/3/6/7/8/9/10/11，R-1..R-3，D-1..D-5 | S6-1/S6-2/S6-5/S6-6/S6-9 |
| S1 | registry/H/A/present/组合 | S6-3/S6-6 |
| S2 | run/簇/成员/身份/五状态/多归属 | S6-4 |
| S3 | VM/visual/presence/capabilities/预算 | S6-5/S6-6 |
| S4 | frame/presence/rule/MANDATORY/subset | S6-6 |
| S5 | GraphNavFrame/T01–T30/S5a/持久化 | S6-7 |
| U | U-32/34 + 前序 U 相关 | 各条 U 映射 |

---

## 14. A-v2 变更表（逐条旧→新）

| # | 旧（v1） | 新（v2） | 裁决 |
|---|---|---|---|
| 1 | S6-7（L310）`nav_id` 作为 schema 字段 | 统一 `frame_id`；`nav_id` 仅文档别名；失败码 `GRAPH_FRAME_ID_INVALID`；STACK/EVENT/G6/curation 全用 frame_id | R-S6-1 |
| 2 | S6-6（L264）FRAME_SPEC 含 frame_id/edition | `S4_FRAME_SPEC` 只留 S4 冻结字段；frame_id/edition 由 S5 派生/本地、不进 S4 输入 | R-S6-2 |
| 3 | S6-5 VM_NODE.role | 保持 `role:"member"`（S3 原文；B 的 role 异议撤回） | R-S6-3 |
| 4 | S6-3（L147）history 无签名 | `DIMENSION_HISTORY_ENTRY.signature?{alg,key_id,sig}`；signed 标记；`GRAPH_HISTORY_SIGNATURE_INVALID` | R-S6-4 |
| 5 | S6-8（L356）路径 `.memoria/build`、`.memoria/audit` | `.memoria/cache/graph/` 派生、`.memoria/config/graph/` registry/history、`.memoria/agent/audit/graph/` append-only；D-3 | R-S6-5 |
| 6 | S6-9 错误码未明确 canonical/legacy | `GRAPH_*` canonical + `legacy_code` 映射；未知 `GRAPH_INTERNAL` | R-S6-6 |
| 7 | S6-11 G6 字段 | `g6_version/data_source_sha/run_ids/registry_sha/vm_sha/frame_sha/nav_sha/rule_histogram/counts/subset_ok/determinism_sha/closure=0/behind=0` | R-S6-6 |
| 8 | S6-12 0.5 边界 | 2D 先发/3D capability=false；不做 agent 写/自动 semantic/跨库/时间维/编辑器/破坏性迁移；S7–S10 不在 0.5 | R-S6-6 |

## 15. 仍存争议 / 待 Lead·SE 裁决

1. **history 签名的落盘形态**：同目录 detached `.sig` 或 `signature` 字段二选一（R-S6-4 已允许），需 S6a 定；算法 `ed25519`/`hmac-sha256` 的 key 管理。
2. **旧 payload fallback**：0.5 是否保留旧 `loadPayload` 只读回退（默认关闭），还是完全新渲染；R-S6-5 只规定默认关闭。
3. **G6 命令/阈值**：脚本路径与阈值已按 R-S6-6 固定语义，具体脚本实现/CI 接入需 S6a 定。
4. **3D 实现时机**：0.5 只 2D、3D capability=false（R-S6-6 已裁），具体排期在 0.5 实现计划定。
5. **GC 执行方式**：自动/手动、并发清理的锁策略需 S6a 定（N=20/90 天已裁）。

---

## 16. 证据锚

```text
S0：S0-terms-v1.md:21-95（S0-1..S0-11）、:100-107（R/D）、:114-156（U 矩阵）
S1：S1-dimensions-v1.md:22-51（registry schema）、:57-67（H/A）、:99-107（present/VM）
S2：S2-clustering-v1.md:17-81（S2-1..S2-13）、:48-50（run/params）
S3：S3-visual-v1.md:36-75（presence/VM/预算）、S3-ADDENDUM-1（node presence）
S4：S4-render-v1.md:26-75（一跳/presence/subset/VM）
S5：S5-nav-v1.md:16-75、:117-155（T01–T30）、S5-RULINGS
工程：ENGINEERING-PLAN.md:150-222（ER/实体）、:562,583,660（P4/P5/P6）、:1026-1048（ST）、:980-1024（P24–P31）
代码：collector.py:46-99；edge_derivation.py:787-793；graph-groups.js:83-134；graph-engine.js:167-216；app.js:1661-1677；nav-stack.js:23-36
```
