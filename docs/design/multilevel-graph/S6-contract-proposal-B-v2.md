# S6 数据契约提案 B-v2（独立复核方修订版）

> **依据（唯一裁决依据）**：`docs/design/multilevel-graph/S6-RULINGS.md`（R-S6-1..R-S6-6）；上游冻结 `S0-terms-v1.md`（`241b1e1e…`）、`S1-dimensions-v1.md`（`6676c71d…`）、`S2-clustering-v1.md`（`92bb0041…`）、`S3-visual-v1.md`（`0ca4ea0e…`）+ `S3-ADDENDUM-1`、`S4-render-v1.md`（`2576f6c8…`）、`S5-nav-v1.md`（`7f4c4515…`），不得违反。
> **输入**：B v1（`f9eb5c13…`）、A v1（`af67ca9f…`）、`S6-objections.md`（`82ecfa9b…`）。A-v2 写作时尚未落盘；本文件先独立完成（完成后才对照 A-v2，见 `S6-objections-v2.md`）。
> **性质**：独立复核方修订提案；不覆盖旧版；不写产品代码/契约；未 commit。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S6-RULINGS/S0–S5 冻结。
> **日期**：2026-11-03（Asia/Shanghai）。

---

## 0. B-v2 变更表（相对 B v1；逐条落 R-S6）

| # | 位置 | B v1 | B-v2（依据） | 类型 |
|---|---|---|---|---|
| 1 | S6-objections | B 提 P1-3「VM role 应 {member,focus}」 | **撤回（WITHDRAWN, misread S3）**：S3 冻结 `role∈{member}`；focus/selected/hover 是 Presentation 瞬态；B-v2 采用 `role:"member"`（R-S6-3） | 撤回 |
| 2 | S6-7/S6-9 | 用 frame_id 但未明确禁 nav_id/失败码 | **S6-7 全部 `frame_id`**；禁止 `nav_id` 字段（仅文档别名）；失败码 `GRAPH_FRAME_ID_INVALID`；NAV_STACK/ EVENT/G6/curation 全 frame_id（R-S6-1） | 强化 |
| 3 | S6-6 | FRAME_SPEC 字段较简但需明确边界 | **FRAME_SPEC 只含 S4 冻结字段**：level/view_family/dimension/focus/hop/new_hop/mode/budget；**frame_id/edition 不属于 S4 输入**：frame_id=S5 派生、edition=S5 本地（R-S6-2） | 修正 |
| 4 | S6-3 | history 可选签名但 schema 简 | **吸收 `signature?{alg:"ed25519"|"hmac-sha256",key_id,sig}`**；签名位置 `.memoria/config/graph/history/...sig`（或字段，S6a 定）；验证失败 `GRAPH_HISTORY_SIGNATURE_INVALID` fail-closed；`signed=false` 时 G6 标记（R-S6-4） | 并集 |
| 5 | S6-8 | 路径 `.memoria/cache/...` 未统一 | **统一路径**：cache `.memoria/cache/graph/`；registry/history `.memoria/config/graph/`；audit `.memoria/agent/audit/graph/`；GC cache 20 run/90 天；history 永不 GC；audit append-only；D-3；旧 graph-groups 不迁移（R-S6-5） | 修正 |
| 6 | S6-9/S6-11/S6-12 | 多命名空间/G6 简/0.5 简 | **`GRAPH_*` canonical + `legacy_code` 映射**；未知 `GRAPH_INTERNAL`；G6 字段/阈值按裁决；0.5 边界按 A（2D 先发/3D capability=false/不做 S7–S10）（R-S6-6） | 并集 |
| 7 | S6-4/S6-5/S6-12 | CLUSTER 无 μ/β/label；token map 简；0.5 清单简 | **吸收 A**：CLUSTER μ/β/label/label_key；`VISUAL_ENCODING_MAP`/`RendererCapabilities`；G6 字段；0.5 接口清单；补 S5 T30/`RESET`/事件集 | 并集 |

---

## 0.1 实体/关系（ER 定稿输入）

| 实体 | 归属 | 身份 | 关键字段 |
|---|---|---|---|
| `DOCUMENT`/`KP_CONCEPT`/`KP_OCCURRENCE` | 事实（只读） | canonical id | 正文/位置/range_ok |
| `EDGE_CANDIDATE`/`EDGE_PROVENANCE` | 事实（只读） | edge_id | type/contain_kind/label/provenance |
| `DATASOURCE` | 事实投影（只读） | `data_source_sha` | edition/manifest/sha |
| `LEVEL`/`VIEW_FAMILY` | 冻结坐标 | level/view_family id | level_chain/basis/dimension |
| `DIMENSION`/`DIMENSION_HISTORY` | 版本化配置/不可变审计 | dimension_id/content_sha | status/version/signature |
| `CLUSTER_RUN`/`CLUSTER`/`MEMBERSHIP` | 派生缓存 | run_id/(run,local_seq) | status/params/cluster_key/μ/β |
| `VIEW_MODEL` | 派生投影 | view_model_id | nodes/edges/presence |
| `GRAPH_NAV_FRAME`/`NAV_STACK_ENTRY` | Presentation | `frame_id` | focus/level/dimension/hop/mode |
| `AUDIT_EVENT` | append-only 审计 | event_id | actor/action/decision |
| `G6_SNAPSHOT` | 审计 | snapshot_id | sha/fields |

---

## S6-1 契约范围与单一真源

**规则**：事实只存在 `.md` + `.memoria` sidecar/manifest（只读给图）；DataSource 是事实投影；GraphView/run/VM/frame 派生；S6 不新增写路径。**禁止并行事实源/双写**；D-3 不写产品 sidecar/新段。
**形式化**：
```
FactSource = .md 正文 + .memoria sidecar/manifest（现有产品/curation 写）
DataSource = read-only projection(FactSource)
GraphView = DataSource + S2 run（派生）
VM = S4 Admission（派生缓存）
NAV_FRAME = Presentation 视图状态（非事实）
禁止：图写 sidecar/new topology；VM/run 回写事实；第二份 KP/边事实；把 view 出现当 membership
```
**机检**：写白名单；DataSource 无 cluster/VM/frame 字段；派生缓存重建；D-3 schema 无新段；同一事实只有一个权威。
**反例**：簇/run 写 sidecar；VM 直接读库绕过 DataSource；并行边表；view 写 membership。
**边界**：sidecar 缺失/损坏；manifest edition 变；旧 graph payload 只读；多 KB 不跨库。
**U 映射**：U-1、U-29、U-32、U-34。
**建议裁决**：冻结实体归属/单一真源/只读 DataSource/D-3。
**证据等级**：A（`collector.py`/`.memoria`；S0 D-3）+ R。

---

## S6-2 DataSource / GraphView / C-* 契约

**DataSource schema**：
| 字段 | 类型 | 枚举/默认 | 失败码 |
|---|---|---|---|
| `schema_version` | string | `"ds-v1"` | `GRAPH_SCHEMA_INVALID` |
| `data_source_sha` | string64 | — | `GRAPH_EDITION_INVALID` |
| `corpus_manifest_sha` | string64 | — | `GRAPH_EDITION_INVALID` |
| `collect_version` | string | — | `GRAPH_EDITION_INVALID` |
| `nodes[]` | KP_NODE[] | `kind="kp"` | `GRAPH_NODE_INVALID` |
| `edges[]` | EDGE[] | type/contain_kind/label 枚举 | `GRAPH_EDGE_INVALID` |
| `read_only` | bool | true | `GRAPH_MUTATION_FORBIDDEN` |
| `warnings[]` | string[] | [] | — |

```
KP_NODE{node_id:"kp:<id>", kind:"kp", kp_id, label, description?, file,
        occurrence_ids[], range_ok:boolean=true, provenance}
EDGE{edge_id:canonical(type|source|target), type∈{contain,reference,extend},
     contain_kind∈{structural,semantic}|null, label∈{semantic,structural,navigation}|null,
     source,target, direction, provenance?}
GraphView{view_id, level_id, view_family_id, basis, run_id?, nodes[], edges[], partition[]}
GraphViewNode{node_id, kind∈{kp,cluster}, cluster_ref?}
接口：get_kp/list_kp/get_edge/list_edges/expand_data_edges(ids) ⊆ DataSource.edges
```
- `E_relation_min` 只加不删（S1）；DataSource 不含 cluster/VM/frame/presence；只读。
- 失败：`GRAPH_SCHEMA_INVALID`/`GRAPH_EDITION_INVALID`/`GRAPH_NODE_INVALID`/`GRAPH_EDGE_INVALID`/`GRAPH_MUTATION_FORBIDDEN`。
**机检**：schema/枚举/只读；DataSource 无派生字段；`expand_data_edges ⊆ edges`；edition sha。
**反例**：DataSource 存 presence/cluster；写回 sidecar；改 edge type；缺 provenance 当 semantic。
**边界**：manifest 缺；sidecar 可选；旧图数据缺 label（按 S0-1 默认 structural/reference）；空 KB。
**U 映射**：U-1、U-10、U-27。
**建议裁决**：冻结 DataSource/GraphView/接口/失败码。
**证据等级**：A（现有 collector/edge_derivation；S0/S1）+ R。

---

## S6-3 维度注册表与 history schema

**DIMENSION**：S1 字段表 + `registry_sha256/history_ref`；v1 active `{hierarchy,association}`。
**DIMENSION_HISTORY_ENTRY（不可变 append-only）**：
```
{version:string(semver), content_sha256:string64, previous_sha256:string64|null,
 relation_sources:[string], active_dimensions:[string],
 decision_id:string, created_at:ISO8601,
 signature?:{alg:"ed25519"|"hmac-sha256", key_id:string, sig:string}}
```
- 存储：`.memoria/config/graph/history/<content_sha>.json`；`<content_sha>.sig` 或字段（S6a 定）；旧版保留、按 content_sha 取；registry `history_ref` 末条 content_sha==registry_sha。
- 签名：`signed=false` 允许但 G6 标记；验证失败 ⇒ `GRAPH_HISTORY_SIGNATURE_INVALID` fail-closed；key_id/decision_id 审计；不重开 S1。
- 跨版本：`new.relation_sources ⊇ old`；删除/改名 ⇒ `S0_REOPEN_REQUIRED`；断链 ⇒ `GRAPH_HISTORY_BROKEN`；`GRAPH_DIM_*` 失败码。
**机检**：字段/枚举/签名/链/只增；registry_sha；旧版可取；失败码。
**反例**：history 只 sha 无 source；原地改；签名只口头；删旧源；registry 与末条不一致。
**边界**：首版 previous=null；空 history invalid；签名缺失 allowed；历史丢失 fail-closed。
**U 映射**：U-9、U-10、U-12、U-25。
**建议裁决**：冻结 schema/history/签名/只增/失败码。
**证据等级**：A（S1/R-S1-9；R-S6-4）+ R。

---

## S6-4 簇 run / membership / 身份 schema

```
CLUSTER_RUN{cluster_run_id = sha256(canonical(corpus_manifest_sha, view_family_id,
             level_id, algorithm_id, algorithm_version, params_hash)),
            parent_run_id|null, level_id, view_family_id, algorithm_id:"hac-average",
            algorithm_version, params_hash, status∈{ok,no_semantic_edges,
            partial_disconnected,size_exceeded,algorithm_failed}, edition_sha}
CLUSTER{cluster_id=f"{run_id}:{local_seq}", run_id, local_seq,
        cluster_key, member_count, mu, beta, representative, root_exempt,
        label, label_key}
MEMBERSHIP{run_id, cluster_id, kp_id, role:"member", source:"derived_cluster"}
CLUSTER_EDGE{edge_id, run_id, cluster_id, kind∈{internal_sem,bridge_sem}, data_edge_ids[]}
params_hash 字段集={algorithm_id,algorithm_version,weight_policy="semantic_uniform",
  linkage="average",tie_break="min_canonical_id",cut_policy,min_cluster_size,
  tau_coh,tau_bridge,n_max}
cluster_key=sha256(canonical(sorted(member_canonical_ids))+algorithm_id+version+params_hash)
```
- 同 `(level,view_family)` 单归属；跨族/层/维多归属；v1 不设上限；`cluster_key` 非实例 id；curation 引用 `{run_id,local_seq,cluster_key}`，key 不匹配 stale；run 不进 VM。
**机检**：run_id/params_hash 可复算；五状态；membership partition；cluster_key；curation；VM 无 run。
**反例**：run_id 缺 level/随机；cluster_key 当 id；状态静默；单值 nodeToGroup；curation 只 key。
**边界**：首 run；无簇；size_exceeded；parent 缺失；多归属。
**U 映射**：U-6、U-21、U-31。
**建议裁决**：冻结 run/membership/身份/μβlabel/五状态/stale。
**证据等级**：A（S2 R-S2-4/9/10/12）+ R。

---

## S6-5 Visual / VM schema

**VM schema**（S3 + ADDENDUM-1；**role 固定 `member`**，focus 是 Presentation 瞬态，不写 VM）：
```
VM{schema_version:"vm/v1", view_model_id:string64,
   level_id?, level_label?, dimension_id?, view_family_id?,
   nodes:[{id,kind∈{kp,cluster},label,role:"member",
           member_count?,representative?,root_exempt?,range_ok?,
           layout_group?{semantic:false},
           presence?∈{shown,suppressed,unknown}, rule_id?}],
   edges:[{id,source,target,base_type,contain_kind?,label?,display_type?,
           presence,rule_id?,state?,hop?,aggregate_count?,data_edge_ids?}]}
```
- `data_edge_ids` 仅审计/`expand_data_edges`，Renderer 禁读；`aggregate_count` 显式不遍历；`presence/rule_id` 是 view-status 不改事实；Renderer 只渲染 shown。
- `VISUAL_ENCODING_MAP{selector, token_kind∈{color,size,shape,opacity,dash,icon,label}, token_value, priority, fallback, map_sha256}`；`RendererCapabilities{backend,supportsAnimation/Keyboard/Aria,maxNodes,maxEdges,capabilities_sha}`；2D/3D 同 VM id 集。
- 失败：`GRAPH_VM_SCHEMA_INVALID`/`GRAPH_VM_UNKNOWN_FIELD`/`GRAPH_RENDER_BUDGET_EXCEEDED`。
**机检**：白名单/枚举/role==member；presence/rule_id；layout_group.semantic=false；data_edge_ids 不读；token map sha；2D/3D capabilities。
**反例**：VM 带 nav/mode/metrics/run/focus；role=focus（非 S3）；Renderer 读 data_edge_ids；2D/3D id 不同。
**边界**：无簇 layout_group；node presence；3D capability=false；空 VM。
**U 映射**：U-3、U-16、U-27、U-33。
**建议裁决**：冻结 VM/token/capabilities/审计禁读；role 固定 member（R-S6-3）。
**证据等级**：A（S3/R-S3-9/ADDENDUM-1；R-S6-3）+ R。

---

## S6-6 Frame / presence / rule_id schema

**FRAME_SPEC（严格 S4 输入，无 frame_id/edition）**：
```
FRAME_SPEC{level_id, view_family_id, dimension_id, focus_id|null,
           hop_budget:1|2|null, new_hop:boolean=false,
           mode:"default"|"full", budget{max_nodes:int,max_edges:int}}
frame_id = sha256(canonical(FRAME_SPEC))     # S5 派生，不传 S4
edition = S5 本地（corpus/manifest），不传 S4
```
**ADMISSION_RESULT**：
```
PRESENCE_RECORD{candidate_id, kind:"node"|"edge", presence∈{shown,suppressed,unknown},
                rule_id, hop?, aggregate_count?}
ADMISSION_RESULT{candidates[], mandatory_ids[], shown/suppressed/unknown counts,
                 budget, subset_proof?, errors[]}
RULE_IDS 11 类 = dimension.sources, dimension.direction, dimension.level.cross_layer,
                 hop.budget, node.budget, edge.budget, cluster.folded,
                 endpoint.unresolved, source.unavailable, admission.undecided, invalid.data
unknown 仅 endpoint.unresolved/source.unavailable/admission.undecided/invalid.data
MANDATORY：A={focus}；H={focus}+first K children（K=2，S8 可调）
subset_proof：candidates(full)⊇candidates(default) ∧ reserved(full)==shown(default)
             ∧ budget_full≥budget_default
```
**失败码**：`GRAPH_FRAME_INVALID`/`GRAPH_HOP_INVALID`/`GRAPH_PRESENCE_RULE_MISSING`/`GRAPH_BUDGET_INVALID`/`GRAPH_SUBSET_UNPROVEN`/`GRAPH_FOCUS_UNRESOLVED`/`GRAPH_RENDER_BUDGET_EXCEEDED`。
**机检**：FRAME_SPEC 字段==S4；presence/rule_id；MANDATORY；subset；失败码。
**反例**：FRAME_SPEC 带 frame_id/edition；presence 只 shown；unknown 当无关系；subset 仅断言。
**边界**：预算 0/不足；initial 失败；full 失败；unknown。
**U 映射**：U-3、U-16、U-18、U-27、U-32。
**建议裁决**：冻结 FRAME_SPEC/Admission/rule/MANDATORY/subset/失败码；frame_id/edition 在 S5。
**证据等级**：A（S4 R-S4-1..10；R-S6-2）+ R。

---

## S6-7 Nav schema（frame_id + T01–T30 + 事件集）

```
GRAPH_NAV_FRAME{frame_id=sha256(canonical(FRAME_SPEC)), edition:string,
                focus_id|null, level_id, view_family_id, dimension_id,
                hop_budget, new_hop, mode, budget,
                origin{from_frame_id,via_cluster_id,via}, stack_ref?}
NAV_STACK_ENTRY{seq, frame_id, focus_id, level_id, view_family_id, dimension_id,
                hop_budget, new_hop, mode, budget}
NAV_EVENT{event_id, type∈21 events, payload, frame_id, at}
```
- 21 事件：`OPEN_GRAPH, DATA_READY, DATA_FAILED, RETRY, DATA_REFRESHED, CLOSE, RELOAD, RESET, CLICK_KP, CLICK_CLUSTER, CLICK_EDGE, CLICK_BACKGROUND, BACK, BREADCRUMB_TO, FOCUS_NODE, FOCUS_CLEAR, FOCUS_LOST, SELECT_DIMENSION, EXPLICIT_NEW_HOP, TOGGLE_EXPAND, CORPUS_CHANGED`。
- T01–T30 **唯一真源**（S5 附录 A）；S5a 由表生成 148 边；含 `T29 RESET`/`T30 Stale RESET`；`frame_id` 禁 nav_id；持久化只 level0 frame+mode+dimension；MAX_STACK=50。
- 失败：`GRAPH_NAV_FRAME_INVALID`/`GRAPH_FRAME_ID_INVALID`/`GRAPH_NAV_EVENT_INVALID`/`GRAPH_STACK_OVERFLOW`/`GRAPH_PERSIST_INVALID`/`GRAPH_ILLEGAL_TRANSITION`。
**机检**：frame_id 派生；S6 schema 字段==S5；T30/事件；S5a 生成；持久化白名单；事务 diff=0。
**反例**：nav_id；FRAME_SPEC 带 frame_id；S5a 手画；深栈持久化。
**边界**：初始/失败/栈满/重开。
**U 映射**：U-7、U-19、U-24。
**建议裁决**：冻结 nav schema/T01–T30/S5a/frame_id/持久化/失败码。
**证据等级**：A（S5 R-S5-9/12；R-S6-1）+ R。

---

## S6-8 存储 / 审计 / GC / 版本 / D-3

**统一路径**：
```
派生缓存：.memoria/cache/graph/<edition>/<level>/<family>/<run_id>.json
registry/history：.memoria/config/graph/{registry.json,history/<content_sha>.json,.sig}
审计：.memoria/agent/audit/graph/*.jsonl（append-only）
G6：.memoria/cache/graph/g6/<snapshot_id>.json（或 artifacts/agent/g6/）
```
- 缓存可删除重建；GC：cache 保留最近 20 个 run 或 90 天（先到者）；history 永不 GC；audit append-only 不 GC。
- **D-3**：禁止写 `.memoria/sidecars/**` 或新拓扑段；旧 `graph-groups` 不迁移，只读 fallback 默认关闭。
- 审计：curation/agent 请求/决策/非法转移/focus recovery；不可修改；不回写事实。
**机检**：写路径白名单；缓存重建同 contract；无 sidecar 写；GC 不删事实；history/audit 保留。
**反例**：簇写 sidecar；缓存当事实；GC 删用户数据；旧分组迁移。
**边界**：缓存缺失/损坏；edition 变；GC；回滚删缓存。
**U 映射**：U-21、U-31、U-32。
**建议裁决**：冻结统一路径/GC/审计/D-3/旧分组忽略。
**证据等级**：A（S0 D-3；R-S6-5）+ R。

---

## S6-9 错误 / 失败语义统一

**canonical**：`GRAPH_*`；**legacy_code 映射** S2–S5 旧码（如 `S4_BUDGET_INVALID`→`GRAPH_BUDGET_INVALID`、`DIM_UNKNOWN`→`GRAPH_DIM_UNKNOWN`、`RENDER_BUDGET_EXCEEDED`→`GRAPH_RENDER_BUDGET_EXCEEDED`）。
**错误对象**：`{code:GRAPH_*, namespace:"GRAPH", severity∈{fail_closed,degraded,fallback}, retryable:boolean, i18n_key, detail?, correlation_id, legacy_code?}`；未知错误 `GRAPH_INTERNAL`（不静默）；i18n key 归 UI（S3）；用户文案不硬编码。
**机检**：码唯一/映射覆盖；severity；i18n key 存在；未知码 fail-closed；legacy 映射。
**反例**：多命名空间；自由文本；未知静默；severity 缺失；i18n 硬编码。
**边界**：初始失败/降级/回退；legacy 旧码；缺 i18n。
**U 映射**：U-32、U-34。
**建议裁决**：冻结 `GRAPH_*` canonical + legacy 映射 + 错误对象/i18n 归属。
**证据等级**：A（S2–S5 失败码；R-S6-6）+ R。

---

## S6-10 兼容 / 迁移 / 回滚

**规则**：旧 `graph-groups` 并查集分组**不是簇**；不迁移、不写 sidecar；v1 无破坏性迁移；旧 graph payload 缺 label 按 S0-1 默认；edition/version 不匹配 fail-closed 或显式降级；回滚=删除派生缓存/恢复旧 edition，不删事实。
**机检**：无迁移写入；旧数据只读；版本校验；缓存可重建；无 sidecar 改写。
**反例**：旧分组写 sidecar；迁移改正文；旧 VM 静默渲染；回滚删事实。
**边界**：旧 KB/旧 cache/edition 切换。
**U 映射**：U-1、U-21、U-32。
**建议裁决**：冻结不迁移/只读/版本/回滚。
**证据等级**：A（现有 graph-groups/collector；D-3）+ R。

---

## S6-11 G6 快照 / 复跑 / 度量

```
G6_SNAPSHOT{g6_version, data_source_sha, run_ids[], registry_sha, vm_sha,
            frame_sha, nav_sha, rule_histogram, node_count, edge_count,
            subset_ok, determinism_sha, closure_violations, behind_violations,
            coverage, status, command/args/version}
```
- 阈值（R-S6-6）：`determinism=100%`、`subset_ok=true`、`closure_violations=0`、`behind_violations=0`；其他数值 S8。
- snapshot 内容寻址；同输入同 sha；复跑脚本；不含正文；失败态可见。
**机检**：字段齐全；sha 可复算；2x 同结果；阈值；无正文。
**反例**：缺 data_source/run/registry；只计数；随机；含正文。
**边界**：空 KB；无簇；full；失败。
**U 映射**：U-32、U-34。
**建议裁决**：冻结 G6 字段/阈值/复跑。
**证据等级**：A（S3–S5 G6；R-S6-6）+ R。

---

## S6-12 0.5 交付边界与 S6a 接口清单

**0.5 做**：
```
DataSource 只读；registry H/A；S2 HAC run/簇/成员（无 semantic ⇒ no_semantic 合法）；
S4 admission/预算/rule_id；S3 2D Renderer/VM/事件/a11y；S5 drill/back/dimension/full（事务化）；
no_semantic_edges UX；agent 只读/candidate run；G6 快照。
```
**0.5 不做**：
```
3D 渲染实现（只留同签名接口+capability=false）；agent 写/自动 semantic；跨库；
时间维；图编辑器；破坏性迁移；簇/成员写产品 sidecar；第二事实源；
未冻结新边类型/新维度；URL 深导航 schema（S6a/后续）。
```
**验收门禁**：S6a schema/ER/DFD/ST 与 S0–S5 一致（mermaid `PARSE_OK`）；G6 阈值；无 D-3；缓存重建；VM 纯度/2D-3D 同签名；nav 事务 diff=0；失败码命名空间/i18n；a11y/性能预算。
**S6a 接口清单**：DataSource/GraphView，DIMENSION/HISTORY，CLUSTER_RUN/CLUSTER/MEMBERSHIP，VM/VM_NODE/VM_EDGE，FRAME_SPEC/ADMISSION_RESULT，GRAPH_NAV_FRAME/STACK/EVENT，CACHE/AUDIT/G6；字段/失败码/路径与本文一致。
**机检**：做/不做/依赖/验收；未冻结语义不进入；S6a 定稿。
**反例**：0.5 顺手自动 semantic/迁移/3D；把未冻结字段写契约。
**边界**：E_sem=0；旧 KB；无 3D；agent 只读。
**U 映射**：U-32、U-34。
**建议裁决**：冻结 0.5 做/不做/接口/验收；S6a 后进入实现。
**证据等级**：A（S0–S5 范围；R-S6-6）+ PI（排期）。

---

## 附：R-S6 自检（6 条）

| 裁决 | B-v2 落位 |
|---|---|
| R-S6-1 frame_id 唯一 | S6-7（frame_id；禁 nav_id；失败码 GRAPH_FRAME_ID_INVALID） |
| R-S6-2 FRAME_SPEC 严格 S4 | S6-6（只 S4 字段；frame_id/edition S5 派生） |
| R-S6-3 role 撤回 | S6-5 role:"member"；S6-objections-v2 标 WITHDRAWN |
| R-S6-4 history 签名 | S6-3（signature? 字段/`.sig`；验证失败码；signed=false G6） |
| R-S6-5 路径/GC/D-3 | S6-8（cache/config/audit 路径；20 run/90 天；history 不 GC；旧分组不迁移） |
| R-S6-6 GRAPH_*/G6/0.5 | S6-9/S6-11/S6-12（canonical+legacy；G6 字段/阈值；0.5 边界） |

> 独立声明：B-v2 先于 A-v2 完成（A-v2 落盘后才对照）；差异与判断见 `S6-objections-v2.md`；未写产品代码/契约，未 commit。
