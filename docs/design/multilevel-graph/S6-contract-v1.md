# S6 数据契约 · 冻结稿 v1（候选）

> **依据**：`multilevel-graph-vision.md`；`S6-charter.md`；`S6-RULINGS.md`。
> **上游冻结**：S0（`241b1e1e…`）、S1（`6676c71d…`）、S2（`92bb0041…`）、S3（`0ca4ea0e…`+ADDENDUM-1）、S4（`2576f6c8…`）、S5（`7f4c4515…`）——不得违反。
> **输入**：A-v2（`9e71d540…`）、B-v2（`4e262068…`）、异议-v2（`a495564b…`）。
> **状态**：冻结候选 v1，待 SE 工程校核 + S6a 定稿（task-322）与 Lead 独立机检后冻结；冻结前不写产品代码。

---

## 0. 一句话口径

事实只来自 `.md` + `.memoria` sidecar/manifest（**只读**）；DataSource 只读，GraphView/run/VM 全部派生；Frame/Nav 是 Presentation 视图状态；派生缓存可删除重建；**禁止并行事实源、禁止 D-3 写 sidecar**；S0–S5 的 schema 在此收口为可实现的 ER/DFD/状态图。

## 1. 规范性条款（S6-1..S6-12）

### S6-1 契约范围与单一真源
- **事实源**：`.md` 正文 + `.memoria/sidecars/**` + `manifest.yaml`（只读）；DataSource 只读投影；GraphView/run/VM 派生；Frame/Nav 为视图状态。
- **禁止**：并行事实源、双写、D-3 向 sidecar 写簇/run、把派生缓存当事实。
- **机检**：写路径白名单；事实文件未被产品写；缓存可删重建。

### S6-2 DataSource / GraphView / C-*
- **DataSource**：`{kps, edges, canonical_id, expand(handle)}` 只读；`E_relation_min` 按 S0-6；`kind∈{kp,cluster}`。
- **GraphView**：按 `(level, view_family)` partition；C-1..C-6 映射按 S0；`data_state ∈ {ok, empty_nosemantic}`。
- **机检**：只读接口；partition 键；kind 枚举。

### S6-3 维度注册表与 history schema
- `DIMENSION_REGISTRY{registry_version, contract_version, dimensions[]}`；`DIMENSION{id,label,kind,relation_sources[],direction,default_hop,hop_budget,view_families[],reserved?,provenance}`（字段/枚举按 S1）。
- `DIMENSION_HISTORY_ENTRY{content_sha, previous_sha, registry_version, created_at, created_by, signature?{alg:"ed25519"|"hmac-sha256", key_id, sig}}`；**append-only**；`content_sha` **不含 signature**；落盘形态（detached `<content_sha>.sig` 或 entry 字段）由 S6a 定；无签名 `signed=false` + G6 `history_signed=false`。
- **只增不删**；删除/改名 ⇒ `S0_REOPEN_REQUIRED`；签名验证失败 ⇒ `GRAPH_HISTORY_SIGNATURE_INVALID`。
- **机检**：history 链可复算；只增不删；跨版本 `new⊇old`。

### S6-4 簇 run / membership / 身份
- `CLUSTER_RUN{run_id, level_id, view_family_id, dimension_id, edition_sha, params_hash, algorithm, status, created_at}`；`run_id = sha256(level|view_family|dimension|edition|params_hash|algorithm)`（S2 六元组）。
- `CLUSTER_MEMBERSHIP{cluster_id, run_id, cluster_key, kp_id, role:"member", weight}`；多归属允许；`cluster_id = run:local_seq`；身份 `cluster_key`（D-2）。
- 五状态 `ok/no_semantic_edges/partial_disconnected/size_exceeded/algorithm_failed`；curation 双引用 `run_id+cluster_key`。
- **机检**：run_id 可复算；membership 多归属；五状态；无结构边伪造语义。

### S6-5 Visual / VM schema
- VM `{view_model_id, level_id, level_label, dimension_id, view_family_id, nodes[], edges[]}`。
- `VM_NODE{id, kind:"kp"|"cluster", label, role:"member", member_count?, aggregate_count?, representative?, root_exempt?, range_ok?, layout_group?{semantic:false}, presence?, rule_id?}`；`focus` **不是 VM role**（Presentation 瞬态）。
- `VM_EDGE{id, type, state, presence?, data_edge_ids?}`；`data_edge_ids` 仅审计/expand，**Renderer 禁读**。
- `VISUAL_ENCODING_MAP{token,value}` 可机检；2D/3D capabilities 独立。
- **机检**：白名单字段；role=member；presence/rule_id（S3-ADDENDUM-1）；禁读字段。

### S6-6 Frame / presence / rule_id
- `S4_FRAME_SPEC{level, view_family, dimension_id, focus, hop, new_hop, mode, budget}`（**严格 S4 冻结字段**）。
- `NAV_FRAME = S4_FRAME_SPEC + {frame_id, edition_sha}`；`frame_id=sha256(canonical(S4_FRAME_SPEC))` **由 S5 派生**，`edition_sha` 由 S5 本地派生/校验，**不进 S4 输入**。
- `PRESENCE_RULE`：presence 三值；`rule_id` 11 类；unknown 仅 `endpoint.unresolved/source.unavailable/admission.undecided/invalid.data`；MANDATORY/subset 构造按 S4。
- 失败码：`GRAPH_FRAME_ID_INVALID`、`GRAPH_PRESENCE_INVALID`、`GRAPH_SUBSET_VIOLATION`、`GRAPH_BUDGET_INVALID`。
- **机检**：字段集 == S4；frame_id 可复算；rule_id 枚举。

### S6-7 Nav schema
- `GraphNavFrame{focus, level, view_family, dimension, hop, new_hop, mode, budget, origin, edition, history, frame_id}`；`NAV_STACK_ENTRY{frame_id, canonical_frame_ref, ts}`；`NAV_EVENT{event_id, type, payload}`（payload 无导航字段）。
- 9 主状态 + 正交 `mode`/`data_state`；T01–T30 唯一真源（`S5-nav-v1.md` 附录 A）；S5a 由表生成 148 边；`frame_id` 统一（禁 `nav_id` schema 字段）；持久化白名单 `mode/dimension/level0 frame`。
- **机检**：字段 == S5；表↔图；失败码 `GRAPH_FRAME_ID_INVALID`。

### S6-8 存储 / 审计 / GC / 版本
- `.memoria/cache/graph/`：派生缓存（可删重建；布局 S6a 定；GC 20 run 或 90 天）；
- `.memoria/config/graph/`：registry/history（history 永不 GC）；
- `.memoria/agent/audit/graph/`：append-only 审计（不 GC）；
- **禁止**写 sidecar 簇/run（D-3）；旧 `graph-groups` 不迁移，只读 fallback 默认关闭；edition/cache 不匹配 ⇒ 重建。
- **机检**：路径白名单；缓存删除后重建；D-3。

### S6-9 错误 / 失败语义
- **`GRAPH_*` canonical**，保留 S2–S5 旧码为 `legacy_code` 映射；未知 `GRAPH_INTERNAL`；i18n key 归 UI；fail-closed/降级/回退按各上游条款。
- **机检**：错误码命名空间；映射表；无静默。

### S6-10 兼容 / 迁移 / 回滚
- 旧 graph-groups/旧 payload：不迁移；只读 fallback 默认关闭；edition 不匹配重建；回滚=删派生缓存+回退设置；无破坏性迁移。

### S6-11 G6 快照 / 复跑
- `G6_SNAPSHOT{g6_version, data_source_sha, run_ids[], registry_sha, vm_sha, frame_ids[], frame_sha, nav_sha, rule_histogram, node_count, edge_count, subset_ok, determinism_sha, closure_violations:0, behind_violations:0, history_signed}`。
- 阈值：determinism=100%、subset_ok=true、closure/behind=0；复跑命令与路径由 S6a 定。

### S6-12 0.5 交付边界
- **做**：DataSource/H/A、run、S4 取景/presence、VM/2D Renderer、导航基础、缓存、G6；
- **不做**：3D 实现（同签名接口 + `capability=false`）、agent 写、自动 semantic、跨库、时间维、图编辑器、破坏性迁移；S7–S10 不在 0.5。
- S6a 输出实现接口清单（DataSource/Run/S4/Nav/Renderer/Cache/Audit/G6）。

## 2. 跨议题裁决（R-S6-1..R-S6-6）

- **R-S6-1**：`frame_id` 唯一（禁 `nav_id` schema；失败码 `GRAPH_FRAME_ID_INVALID`）。
- **R-S6-2**：`S4_FRAME_SPEC` 严格 S4 字段；frame_id/edition 为 S5 派生/本地，不进 S4。
- **R-S6-3**：`VM_NODE.role:"member"`；B 的 role 异议撤回（S3 原文 role∈{member}）。
- **R-S6-4**：history 可选 `signature?` + 失败码；`content_sha` 不含 signature；signed=false G6 标记。
- **R-S6-5**：路径 cache/config/audit 三分；D-3；GC 只删派生。
- **R-S6-6**：`GRAPH_*` canonical + legacy 映射；G6 字段/阈值统一；0.5 边界按 §S6-12。

## 3. S6a ER/DFD/状态图要求（SE）

- **ER**：DOCUMENT、KP_CONCEPT、KP_OCCURRENCE、EDGE_CANDIDATE、EDGE_PROVENANCE、DIMENSION_REGISTRY、DIMENSION_HISTORY_ENTRY、CLUSTER_RUN、CLUSTER_MEMBERSHIP、NODE_VIEW、EDGE_VIEW、S4_FRAME_SPEC、NAV_FRAME、NAV_STACK_ENTRY、NAV_EVENT、CACHE_ENTRY、AUDIT_ENTRY；关系与基数逐条。
- **DFD**：DataSource 只读 → GraphView/run → S4 取景 → VM → Renderer；registry 校验 → history；audit/GC；失败回退。
- **状态图**：run 生命周期、registry 版本、错误/回滚、S5a 引用。
- 全部 vendored mermaid `PARSE_OK`；与 S0–S5 逐条映射。

## 4. 覆盖矩阵（S0–S5 + U）

| 上游 | S6 落点 |
|---|---|
| S0-2/6/8、D-2/D-3 | S6-1/S6-2/S6-8 |
| S1 全字段/history | S6-3 |
| S2 run/五状态/多归属 | S6-4 |
| S3 VM/ADDENDUM-1/禁读 | S6-5 |
| S4 frame/presence/subset | S6-6 |
| S5 T01–T30/frame_id/持久化 | S6-7 |
| U-32/34 | S6-1/S6-12 |

## 5. 冻结门禁

1. A-v2/B-v2 关闭 R-S6-1..6；
2. SE 工程校核 + S6a 定稿 PASS（mermaid `PARSE_OK`）；
3. Lead 独立机检（字段集/失败码/单一真源/缓存可重建/G6/0.5 边界）；
4. 与 S0–S5 无冲突；
5. 冻结 `S6-contract-v1.md` 并写决策；**S0–S6 全冻结 → 0.5 实现计划**。

## 6. 变更控制

- 加 schema 字段/失败码：S6 修订 + 决策；删/改单一真源/迁移/0.5 边界：重开 S6；S6a 为工程定稿，不改语义。
