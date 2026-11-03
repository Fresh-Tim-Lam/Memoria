# S6 数据契约提案 B（独立复核方）

> **依据**：`multilevel-graph-vision.md` U-1..U-35；上游冻结 `S0-terms-v1.md`（`241b1e1e…`）、`S1-dimensions-v1.md`（`6676c71d…`）、`S2-clustering-v1.md`（`92bb0041…`）、`S3-visual-v1.md`（`0ca4ea0e…`）+ `S3-ADDENDUM-1`、`S4-render-v1.md`（`2576f6c8…`）、`S5-nav-v1.md`（`7f4c4515…`），不得违反；本场 `S6-charter.md`。
> **性质**：独立复核方提案；写作时**未读** `S6-contract-proposal-A.md`（尚未落盘）；写完再对照，差异见 `S6-objections.md`。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S0–S5 冻结。
> **日期**：2026-11-03（Asia/Shanghai）。

---

## 0. 总原则（S6 是收口，不是改语义）

1. **单一真源**：产品事实只在 DataSource（`.memoria` manifest/sidecars/正文）；VM/frame/簇 run/registry/audit/G6 均为**派生或审计**，不得与 DataSource 双写。DataSource 只读 API；派生层不反向写事实。
2. **D-3**：不得新增产品 sidecar/拓扑段；派生缓存可删除重建；审计 append-only 可追溯但不是产品事实。
3. **schema 必须齐全**：字段/类型/枚举/默认/失败码/所有者/版本；每个失败码有命名空间、严重度（fail-closed/degraded/fallback）、i18n key、retryable。
4. **S0–S5 冻结语义不改**：S6 只落契约；0.5 边界不得夹带 S7–S10 或未冻结字段。
5. **ER/DFD/状态图**：S6a 定稿；S6 B 给实体/关系/DFD/ST 需求；同版本 mermaid `PARSE_OK`。
6. **G6 可复跑**：snapshot 含 edition/registry/run/frame 身份与 sha；同输入同输出。
7. **兼容**：旧 graph-groups 分组不是簇；旧 graph payload 无 presence；v1 无破坏性迁移，派生层可重建，回滚=删除缓存。

### 0.1 实体/关系总表（ER 需求）

| 实体 | 事实/派生 | 身份 | 关键字段 |
|---|---|---|---|
| `DATASOURCE` | 事实（只读） | `data_source_id` = edition sha | edition/corpus_manifest_sha/version |
| `KP` | 事实 | `kp_id` canonical | name/range_ok/level membership refs |
| `EDGE` | 事实 | `edge_id` canonical | source/target/base_type/contain_kind/label/provenance |
| `VIEW_FAMILY` | 冻结坐标 | `view_family_id` | family_id/basis/dimension_id/level_chain |
| `LEVEL` | 冻结坐标 | `level_id` | index/view_family_id |
| `DIMENSION` | 版本化配置（派生） | `dimension_id` | kind/status/version/relation_sources/direction/hop/termination |
| `REGISTRY_HISTORY` | 审计（不可变） | `content_sha256` | version/previous_sha/relation_sources/active_dimensions/decision_id |
| `CLUSTER_RUN` | 派生缓存 | `cluster_run_id` | edition/level/family/algorithm/params/status |
| `CLUSTER` | 派生 | `(run_id,local_seq)` | cluster_key/members/member_count/representative/root_exempt |
| `MEMBERSHIP` | 派生 | `(run_id,cluster_id,kp_id)` | role=member |
| `VM` | 派生投影 | `view_model_id` | nodes/edges/level_label/dimension_id |
| `NAV_FRAME` | Presentation | `frame_id=sha256(frame_spec)` | focus/level/dim/hop/mode/stack refs |
| `AUDIT_EVENT` | 审计 append-only | `event_id` | actor/action/decision/sha/reason |
| `G6_SNAPSHOT` | 审计 | `snapshot_id` | edition/registry/run/frame/metrics sha |

**关系**：DATASOURCE 1—N EDGE/KP；VIEW_FAMILY 1—N LEVEL；CLUSTER_RUN 1—N CLUSTER/ MEMBERSHIP；EDGE 派生 VM；NAV_FRAME 请求 S4 得 VM；AUDIT/G6 引用上述 id。

---

## S6-1 契约范围与单一真源

**规则**：ER/DFD 覆盖 DataSource→候选→Admission→VM→Renderer、S5 frame、registry/history、cluster run/membership、audit/G6。**唯一可写事实** = DataSource 的现有产品存储（manifest/sidecars/正文），由现有产品代码维护；S6 不新增写路径。派生链：
```
DataSource(只读) → EDITION/VIEW_FAMILY → (S9候选) → S4 Admission → VM → S3 Renderer
                                      → S2 run → cluster/membership
S5 NAV_FRAME → frame_spec → S4
```
**禁止**：VM 回写 DataSource；S5 写 S2 run；S4 写 registry；S3 写事实；cluster cache 当事实；sidecar 新拓扑段；audit 当产品事实。
**机检**：写 API 白名单只有现有产品写入；派生层只读 DataSource；DataSource 无 cluster/VM 字段；D-3 sidecar schema 无新增拓扑段。
**反例**：把 cluster/membership 写入 `.memoria/sidecars`；VM/frame 持久化当事实；registry 运行时写产品；audit 被当查询真源。
**边界**：现有 sidecar 已含旧图数据；迁移/读取策略见 S6-10；缓存缺失重建。
**U 映射**：U-1、U-21、U-32。
**建议裁决**：冻结单一真源/只读边界/ER 实体；S6 不新增写路径。
**证据等级**：A（现有 `collector.py`/`.memoria` 数据结构；S0 D-3/S0-11）+ R。

---

## S6-2 DataSource / GraphView / C-* 契约

**schema**（只读）：
```
DataSource = {
  data_source_id: sha256(canonical(corpus_manifest + sidecar bytes)),  # 唯一 edition
  corpus_manifest_sha: string64,
  kps: [{kp_id, canonical_id, name?, range_ok:boolean, level_refs[]}],
  edges: [{edge_id, source, target, base_type∈{contain,reference,extend},
           contain_kind?∈{structural,semantic}, label?∈{semantic,structural,navigation},
           provenance:{state∈{asserted,inferred,missing}, source}, data_edge_ids?}],
  view_families: [...], levels: [...]
}
```
- `E_relation_min` 只加不删（S1）；`kind` 不在 DataSource，由 VM 派生；DataSource 不存 cluster/VM/frame/presence。
- 读取失败：`DS_READ_FAILED`（fail-closed）；edition 不匹配：`DS_EDITION_MISMATCH`（stale/事务失败）。
**机检**：schema 校验；DataSource 无派生字段；CRC/sha；只读接口（无写方法）；E_relation_min 覆盖；kind 仅 VM。
**反例**：DataSource 存 presence/cluster；映射时改 edge type；写回 sidecar。
**边界**：manifest 缺；sidecar 可选；旧图数据无 label（默认 structural/reference 按 S0-1）；空 KB。
**U 映射**：U-1、U-10、U-27。
**建议裁决**：冻结 DataSource schema/只读/E_relation_min/失败码。
**证据等级**：A（现有 collector/edge_derivation；S0-1/S1）+ R。

---

## S6-3 维度注册表与 history schema

**registry schema**：S1 字段表 + `registry_sha256`；`history_ref`；v1 active 集合 `{hierarchy, association}`。
**history entry schema（不可变 append-only）**：
```
REGISTRY_HISTORY_ENTRY = {
  version:string(semver), content_sha256:string64, previous_sha256:string64|null,
  relation_sources:[string], active_dimensions:[string],
  algorithm_version?, decision_id:string, created_at:ISO8601,
  signature?: {alg:"ed25519",key_id, sig}  # 可选；位置见下
}
```
- 存储：`<design>/multilevel/registry-history/<content_sha>.json` 或只追加 JSONL；**content-addressed、旧版按 content_sha 可取**；registry 带 `history_ref`，末条 `content_sha == registry_sha`。
- 签名：S6 不强制签名（本地仓库），但**若启用**签名为 detached `.sig` 与 entry sha 绑定；签名 key 不进 registry；审计事件记录 key_id/decision_id。
- 校验：`new.relation_sources ⊇ old`；删除/改名 ⇒ `S0_REOPEN_REQUIRED`；`DIM_*` 失败码；history 断链 ⇒ `REG_HISTORY_BROKEN`（fail-closed）。
**机检**：字段/类型/枚举/默认；history 链；跨版本只增；registry_sha；旧版可取；失败码。
**反例**：history 只存 sha 不存 sources（无法自包含）；原地改 history；registry 与 history 末条不一致；删除旧源。
**边界**：首版 previous=null；空 history invalid；签名缺失允许；历史文件缺失→fail-closed。
**U 映射**：U-9、U-10、U-12、U-25。
**建议裁决**：冻结 schema/history 自包含/不可变/签名可选/失败码。
**证据等级**：A（S1/R-S1-9）+ R。

---

## S6-4 簇 run / membership / 身份 schema

```
CLUSTER_RUN = {
  cluster_run_id = sha256(canonical(corpus_manifest_sha, view_family_id, level_id,
                      algorithm_id, algorithm_version, params_hash)),
  parent_run_id:string|null, level_id, view_family_id,
  algorithm_id:"hac-average", algorithm_version, params_hash,
  status ∈ {ok,no_semantic_edges,partial_disconnected,size_exceeded,algorithm_failed},
  edition_sha, created_at
}
CLUSTER = {run_id, local_seq:int, cluster_key:string64,
           member_count:int, representative:boolean, root_exempt:boolean}
MEMBERSHIP = {run_id, cluster_id, kp_id, role:"member", source:"derived_cluster"}
cluster_key = sha256(canonical(sorted(member_canonical_ids), algorithm_id, version, params_hash))
```
- `params_hash` 字段集冻结（S2 R-S2-10）：algorithm_id/version、weight_policy=semantic_uniform、linkage=average、tie_break=min_canonical_id、cut_policy、MANDATORY?、tau_coh/tau_bridge、n_max 等。
- 五状态：`ok/no_semantic_edges/partial_disconnected/size_exceeded/algorithm_failed`；状态必须显式；无簇 coverage=0 合法。
- stale/curation：curation 引用 `{run_id,local_seq,cluster_key}`；key 不匹配 ⇒ stale，不静默套用；run 不进 VM。
**机检**：run_id 可复算；params_hash 字段完整；状态枚举；membership 同族 partition/跨族多归属；curation 引用完整；VM 无 run。
**反例**：run_id 随机/缺 level；cluster_key 当实例 id；状态静默；membership 单值；curation 只 key。
**边界**：首 run；无簇；size_exceeded；parent 缺失。
**U 映射**：U-6、U-21、U-31。
**建议裁决**：冻结 run/membership/身份/五状态/stale 契约。
**证据等级**：A（S2 R-S2-4/9/10/12）+ R。

---

## S6-5 Visual / VM schema

**VM schema（S3 白名单 + ADDENDUM-1）**：
```
VM = {
  schema_version:"vm/v1", view_model_id:string64,
  level_id?, level_label?, dimension_id?, view_family_id?,
  nodes:[{id,kind∈{kp,cluster},label,role∈{member,focus},
          member_count?,representative?,root_exempt?,range_ok?,
          layout_group?{semantic:false}, presence?∈{shown,suppressed,unknown}, rule_id?}],
  edges:[{id,source,target,base_type,contain_kind?,label?,display_type?,
          presence,rule_id?,state?,hop?,aggregate_count?,data_edge_ids?}]
}
```
- `data_edge_ids` 只审计/`expand_data_edges`，Renderer schema **拒绝读取**；`aggregate_count` 由取景层显式给，不遍历 data_edge_ids；`presence/rule_id` 只在 view-status，不改事实。
- `token_map`：S3 token 表；2D/3D capabilities 由 Renderer 提供，不进 VM。
- 失败码：`VM_SCHEMA_INVALID`/`VM_UNKNOWN_FIELD`（fail-closed）；`RENDER_BUDGET_EXCEEDED`（Renderer 校验）。
**机检**：白名单/类型/枚举；节点/边 presence；layout_group.semantic=false；data_edge_ids 不读；2D/3D id 集一致。
**反例**：VM 带 nav/mode/metrics/run；Renderer 读 data_edge_ids；节点 presence 缺失（ADDENDUM-1 后）。
**边界**：无簇 VM；full VM；空 VM；旧 VM 版本。
**U 映射**：U-6、U-19、U-27、U-33。
**建议裁决**：冻结 VM schema/token map/审计字段/Renderer 禁读。
**证据等级**：A（S3/R-S3-9/ADDENDUM-1）+ R。

---

## S6-6 Frame / presence / rule_id schema

```
FRAME_SPEC = {level_id, view_family_id, dimension_id,
              focus_id:string|null, hop_budget:1|2|null, new_hop:boolean,
              mode:"default"|"full", budget:{max_nodes:int,max_edges:int}}
ADMISSION_RESULT = {
  candidates:{nodes:[{id,presence,rule_id?,hop?}], edges:[...]},
  mandatory_ids:[string], shown/suppressed/unknown counts,
  budget, candidate_scope:"default"|"candidate_scope", subset_reserved_ids:[]
}
```
- presence 三值；11 类 rule_id（S4 R-S4-5）；MANDATORY 公式（S4 R-S4-10）；`candidate_scope`；`reserved(shown(default))`；失败码：`S4_BUDGET_INVALID`/`S4_FOCUS_UNRESOLVED`/`S4_INVALID_DATA`；subset 失败码 `S4_SUBSET_VIOLATION`。
- S5 只构造 FRAME_SPEC；S4 输出 ADMISSION_RESULT/VM；S5 不算 presence。
**机检**：字段/枚举/失败码；MANDATORY；候选完整；presence/rule_id；subset 构造；预算同源。
**反例**：S4 只输出 shown；rule_id 自由文本；budget 两套；subset 只断言。
**边界**：预算 0；初始失败；full 失败；unknown 多。
**U 映射**：U-15、U-16、U-18、U-27。
**建议裁决**：冻结 frame/admission/presence/rule_id/失败码。
**证据等级**：A（S4 R-S4-3/4/5/7/9）+ R。

---

## S6-7 Nav schema（T01–T30 表↔图）

```
NAV_FRAME = {frame_id=sha256(canonical(frame_spec)), edition_sha, focus_id|null,
             level_id, view_family_id, dimension_id, hop_budget, new_hop,
             mode, budget, origin{from_frame_id,via_cluster_id,via}, stack_ref?}
NAV_STACK_ENTRY = {snapshot: NAV_FRAME 的 canonical 子集}
NAV_EVENT = {type∈{OPEN_GRAPH,DATA_READY,...,TOGGLE_EXPAND,CORPUS_CHANGED,RESET},
             payload 白名单}
```
- `frame_id` 派生自 frame_spec，**不消费 S4 未冻结字段**；edition 由 S5 本地派生；持久化只 level0 frame+mode+dimension；MAX_STACK=50；T01–T30 唯一真源，S5a 由表生成 148 边（S5 R-S5-9/12）。
- 失败码：`S5_ILLEGAL_TRANSITION`/`S5_FRAME_INVALID`/`S5_STACK_OVERFLOW`/`S5_PERSIST_INVALID`。
**机检**：schema；frame_id 可复算；表↔图生成；持久化白名单；无未冻结字段。
**反例**：frame_id 来自 S4 未定义字段；S5a 手画；持久化深栈；VM 含 frame。
**边界**：初始/失败/栈满/重开。
**U 映射**：U-7、U-19、U-24。
**建议裁决**：冻结 nav schema/T01–T30/S5a 生成/失败码。
**证据等级**：A（S5 R-S5-9/12）+ R。

---

## S6-8 存储/审计/GC/版本/D-3

**规则**：
```
事实：.memoria/manifest + sidecars + 正文（现有产品写）
派生缓存：.memoria/cache/multilevel/<edition>/<level>/<family>/<run_id>.json
审计：.memoria/audit/multilevel/*.jsonl（append-only）
G6：artifacts/agent/g6/<snapshot_id>.json（或 cache）
```
- 缓存 key=edition/run_id；可删除重建；GC 按 LRU/年龄/edition 失效；旧 run 保留审计；缓存 schema 带 registry_sha/algo/params；**不新增 sidecar/新拓扑段**。
- 审计事件：curation/agent 请求/决策/invalid transition/focus recovery；append-only，不修改。
**机检**：写路径白名单；缓存可重建；D-3 sidecar schema 无新增；GC 不删事实；审计不可变。
**反例**：簇写 sidecar；缓存当事实；GC 删用户数据；审计可改写。
**边界**：缓存缺失/损坏；edition 变更；GC 删除旧 run；回滚。
**U 映射**：U-21、U-31、U-32。
**建议裁决**：冻结缓存/审计/GC/D-3/版本。
**证据等级**：A（S0 D-3；现有 `.memoria`）+ R。

---

## S6-9 错误/失败语义统一

**命名空间**：
```
DS_* (DataSource/edition)
DIM_* (registry/dimension)
S2_* (cluster run/identity/state)
S3_*/VM_* (visual schema/VM)
S4_* (admission/presence/budget/subset)
S5_* (nav/frame/stack)
REG_* (history)
G6_* (snapshot)
S6_* (contract/schema/version)
```
**错误对象**：`{code,namespace,severity∈{fail_closed,degraded,fallback},retryable:boolean,i18n_key,detail?,correlation_id}`；用户文案只来自 i18n key；S2–S5 错误码映射表；未知码 fail-closed；不得自由文本。
**机检**：码唯一/命名空间/映射覆盖；i18n key 存在；severity 合法；未知码 fail-closed。
**反例**：同一错误多码；中文文案硬编码；severity 缺失；未知码静默。
**边界**：初始失败/降级/回退；i18n 缺 key；跨 KB。
**U 映射**：U-32、U-34。
**建议裁决**：冻结命名空间/错误对象/映射/i18n 归属。
**证据等级**：A（S2–S5 失败码）+ R。

---

## S6-10 兼容/迁移/回滚

**规则**：
- 旧 `graph-groups.js` 并查集分组 **不是 cluster**；S2 cluster 新派生，旧分组不迁移、不写回；旧 graph payload 缺 presence/label，按 S0-1 默认（structural/reference），不伪造 semantic。
- edition 兼容：DataSource 版本/字段缺失→`DS_SCHEMA_MISMATCH` fail-closed 或显式降级；旧 VM/nav/frame 版本→`S6_VERSION_UNSUPPORTED`。
- **v1 无破坏性迁移**；不重写用户 KB/sidecar；回滚=删除派生缓存/恢复旧 edition；不删产品数据。
**机检**：无迁移写入；旧数据只读；版本校验；回滚可重建；无 sidecar 改写。
**反例**：把旧分组写 sidecar；迁移改用户正文；旧版 VM 静默渲染；回滚删事实。
**边界**：旧 KB 无新字段；旧 graph cache；edition 切换。
**U 映射**：U-1、U-21、U-32。
**建议裁决**：冻结不迁移/只读/版本/回滚策略。
**证据等级**：A（现有 graph-groups/collector；D-3）+ R。

---

## S6-11 G6 快照/复跑/度量

```
G6_SNAPSHOT = {
  snapshot_id, edition_sha, corpus_manifest_sha, registry_sha, nav/ run ids,
  level_id, view_family_id, dimension_id, focus_id, hop, mode, budget,
  candidate/mandatory/shown/suppressed/unknown counts,
  rule_id_histogram, presence_histogram, max_hop, closure/behind violations,
  subset_ok, deterministic_sha256,
  run_id/cluster_count/coverage/status, nav states/transitions,
  command/args/version
}
```
- snapshot 只读、内容寻址；同输入同 sha；复跑脚本 `python -m ... g6 --edition ...`；阈值 S8。
**机检**：字段齐全；sha 可复算；复跑 2x 同结果；privacy（无正文）；版本。
**反例**：缺 edition/registry；只报计数；随机时间；含正文。
**边界**：空 KB；无簇；full；失败态。
**U 映射**：U-32、U-34。
**建议裁决**：冻结 G6 字段/复跑/阈值归属。
**证据等级**：A（S3–S5 G6 要求）+ PI（字段）。

---

## S6-12 0.5 交付边界

**规则**：0.5 只实现 S0–S6 冻结内容：
```
做：DataSource 读；H/A 维度注册表/激活；S2 run/簇（E_sem 可用时）；S4 候选/presence/budget/subset；S3 2D Renderer（3D 接口预留，不承诺实现）；S5 导航（drill/back/new_hop/dimension/full）；no_semantic_edges UX；agent 只读/candidate run；G6 快照。
不做：S7–S10 全量；语义边自动生成/自动 curation；旧 graph-groups 迁移；深栈持久化/URL 深导航；3D 视觉完整实现；跨 KB 合并。
依赖：semantic curation（若 E_sem=0，0.5 显示 no_semantic_edges 合法）；S8 阈值；S9 候选检索。
验收：S6a ER/DFD/ST；S0–S5 条款；G6 可复跑；无 D-3 违规；无并行事实源。
```
**机检**：范围清单/不做项/依赖/门禁；0.5 不引入未冻结字段；实现计划另立。
**反例**：0.5 顺手做 semantic 自动/迁移；把未冻结字段写契约；承诺 3D。
**边界**：E_sem=0；旧 KB；无 3D；agent 只读。
**U 映射**：U-32、U-34。
**建议裁决**：冻结 0.5 做/不做/依赖/验收；S6a 定稿后进入实现。
**证据等级**：A（S0–S5 冻结范围）+ PI（排期）。

---

## 附：S6 章程预注册判据自检

| 判据 | 本提案 |
|---|---|
| ER/DFD/ST 定稿一致 | S6-1 实体表 + S6-7 T01–T30；S6a SE 定稿 |
| 每 schema 字段/类型/枚举/默认/失败码/单一真源 | S6-2..S6-7 |
| 缓存可重建/D-3/审计 | S6-8 |
| 失败码统一/i18n | S6-9 |
| G6 可复跑 | S6-11 |
| 0.5 边界 | S6-12 |
| A/B 差异逐条 | 见 `S6-objections.md`（写完对照） |
| 不写产品代码/契约/commit | 本文件只写设计 |

> 独立声明：本文件写作时未读 `S6-contract-proposal-A.md`（尚未落盘）；差异与判断见 `S6-objections.md`，逐项列不合并。
