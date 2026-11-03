# S9 后端检索提案 B-v2（独立复核方修订版）

> **依据（唯一裁决依据）**：`docs/design/multilevel-graph/S9-RULINGS.md`（R-S9-1..R-S9-5）；上游冻结 `S0`（`241b1e1e…`）、`S1`（`6676c71d…`）、`S2`（`92bb0041…`）、`S3`（`0ca4ea0e…`+ADDENDUM-1）、`S4`（`2576f6c8…`）、`S5`（`7f4c4515…`）、`S6`（`40f12e5f…`+ADDENDUM-1）、`S7`（`70dd8748…`）、`S8`（`c6a135ff…`），不得违反。
> **输入**：B v1（`a95545dd…`）、A v1（`fa2d2092…`）、`S9-objections.md`（`bb7728cd…`）。A-v2 写作时尚未落盘；本文件先独立完成（完成后才对照 A-v2，见 `S9-objections-v2.md`）。
> **性质**：独立复核方修订提案；不覆盖旧版；不写产品代码/契约；未 commit。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S9-RULINGS/S0–S8 冻结。
> **日期**：2026-11-04（Asia/Shanghai）。

---

## 0. B-v2 变更表（相对 B v1；逐条落 R-S9）

| # | 位置 | B v1 | B-v2（依据） | 类型 |
|---|---|---|---|---|
| 1 | S9-2/S9-7 | budget `{max_candidates,max_tokens,max_latency...}` 不精确 | **budget 冻结 `{max_candidates,max_tokens=4000,max_latency_ms=500,cursor?}`**；超 token `truncated=true,reason="token_budget"`；G7 可归因（R-S9-1） | 修正 |
| 2 | S9-10 | 评估指标/golden 无命令 | **可执行 eval 契约**：golden 路径/schema/sha、`eval-retrieval` 命令/exit、指标 JSON+sha、阈值/回归容差、2× 确定性、无 semantic 单列；S8 gate 引用（R-S9-2） | 新增 |
| 3 | S9-2/S9-5/S9-6 | 枚举分散（lookup/ref_type/status） | **query_type 4 值（无 lookup）**；filters 固定含 kind；candidate kind/status/data_state；tie-break `(score,hop,kind,canonical_id)`；**弃 ref_type**；延迟 500（R-S9-3） | 修正 |
| 4 | S9-4/S9-5 | 多 seed/权重未冻结 | **单 seed+semantic 1 跳**；多 seed future；权重 0.4/0.4/0.2 假设；结构/ref 语义贡献 0；embedding `model_id/dim/license` 记录（R-S9-4） | 修正 |
| 5 | S9-9/S9-3/S9-11 | 错误码/索引/一致性较简 | 只用 S6 `GRAPH_*`（新码 S6-ADDENDUM）；索引 `.memoria/cache/graph/retrieval/` 可重建/edition/原子切换；S10 失效重建（R-S9-5） | 修正 |
| 6 | S9-1..12 | 未吸收 A 的 schema/指标/S9-11 | 吸收 A 的 request/candidate schema、R-* 指标、S9-11 原子切换；A/B 差异见 `S9-objections-v2.md` | 并集 |

---

## 0.1 检索指标总表

| ID | 定义/公式 | 阈值 | 证据 |
|---|---|---|---|
| R-RECALL@k | `relevant retrieved@k / all relevant`（按 query_type） | golden 基线；不降 | eval JSON |
| R-NDCG@k | 归一化折损累计增益 | 基线不降 | eval JSON |
| R-MRR | `mean(1/rank_first_relevant)` | 基线不降 | eval JSON |
| R-COVERAGE | 有候选 query 比例；semantic coverage | 信号 | eval JSON |
| R-DET | 同 query/edition/config 两次 top-k 一致 | 100% | 2× eval sha |
| R-SEM-PURITY | 结构/引用边进入语义分数/召回次数 | 0 | score_components |
| R-NO-SEM | 无 semantic 子集行为（KP-only、无簇） | 100% 正确降级 | eval no_semantic |
| R-LATENCY | 检索 p95（冷/热，keyword/vector/hybrid 分开） | 假设；S8/S9a 基线 | eval latency |
| R-EMPTY | 空结果率（按 query_type） | 信号 | eval JSON |

---

## S9-1 定位与边界（只产 candidate）

**规则**：S9 只产 `candidate/ranking`；不写图谱/DataSource/sidecar/registry/VM/frame；不做 presence/取景/导航/渲染；S7 消费 candidate；S4 做最终 presence；S10 写 KP/语义边；S6 单一真源。
**形式化/机检**：
```
S9 output = candidates[]/score/reason/edition
禁止：写 sidecar/manifest/registry/事实；计算 presence/rule_id；产 VM/frame；绕过 S4/S7
assert S9 read-only；索引仅 .memoria/cache/graph/retrieval/；audit
```
**反例**：S9 返回 shown/VM；写 sidecar；改 KP；直接渲染。
**边界**：无索引；S10 写中；S4 失败；无 semantic。
**U 映射**：U-1、U-2、U-32、U-34。
**建议裁决**：冻结只产候选/不写/不绕 S4/S7。
**证据等级**：A（S6-1/S6-8/S7-8；S0 D-3）+ R。

---

## S9-2 检索接口（统一 schema/budget/枚举）

**RetrievalRequest（冻结）**：
```
{
  request_id, kb_id, query, query_type∈{keyword,vector,graph,hybrid}, # 无 lookup
  level_id?, view_family_id?, dimension_id?,
  filters{kb_id, level_id?, view_family_id?, dimension_id?, file?, section?, anchor?, kind?},
  budget{max_candidates:int=50, max_tokens:int=4000, max_latency_ms:int=500, cursor?:string},
  expected_edition?:string64
}
```
**CandidateRef（冻结；无 ref_type）**：
```
{
  candidate_id, kb_id, kind∈{kp,cluster,edge,file,anchor}, id,
  edition_sha, level_id?, view_family_id?, dimension_id?,
  score:number[0,1], score_components{keyword,vector,graph},
  reason⊆{keyword_match,vector_match,semantic_hop,hybrid_fusion,filter},
  refs{kp_id?,file?,line_start?,line_end?,anchor?,cluster_id?,cluster_key?,run_id?,edge_id?},
  rank, status∈{ok,degraded,unknown}, data_state∈{ok,empty_nosemantic},
  hop:0|1
}
```
**CandidatePage**：
```
{request_id, edition_sha, candidates[], next_cursor?, total_estimated?,
 truncated:boolean, truncated_reason?∈{candidates,tokens,latency},
 data_state, degraded_reason?, meta{latency_ms,index_version}, audit_id}
```
- 超 token ⇒ `truncated=true, truncated_reason="token_budget"`（R-S9-1）；超候选/延迟同理；不静默。
- cursor = opaque `(edition, query_hash, filters_hash, sort_key, last_id)`；跨 edition 拒绝 `GRAPH_EDITION_STALE`；分页同 edition 稳定。
- IDs 对齐 S6：kp_id/edge_id/cluster_key/run_id；不产 frame。
**机检**：schema/枚举白名单；budget 四字段；token 截断可见；cursor 绑定 edition；分页无重复/漏；id 对齐。
**反例**：lookup/ref_type；budget 缺 max_tokens；cursor 跨 edition；超 token 不标；无 status。
**边界**：空结果；大 k；无 semantic；多 KB；S10 写后。
**U 映射**：U-6、U-10、U-12、U-19、U-32。
**建议裁决**：冻结 request/candidate/page schema/四值/无 lookup/token/游标/id。
**证据等级**：A（S6/S7/S8；R-S9-1/R-S9-3）+ R。

---

## S9-3 索引/存储

**规则**：
```
路径：.memoria/cache/graph/retrieval/<kb_id>/<edition>/<index_type>/
index_type∈{fts,embedding,adjacency,meta}
RetrievalIndex{index_version,kb_id,edition_sha,source{manifest_sha,collect_version},
  fts{tokenizer,index_sha}, embedding{model_id,dim,license,enabled,index_sha},
  graph{run_ids[], adjacency:{semantic_edges_only:true}, index_sha},
  compatible{contract_version,s6_contract_sha}}
manifest: index_manifest{index_version,edition_sha,shas,rebuildable:true}
```
- 只从 DataSource/S2 run 构建；索引只写 cache 域；不写 sidecar/manifest/registry；edition 变⇒新目录；旧索引只读/可 GC；可删除重建；原子切换 manifest；graph adjacency 只 E_sem。
**机检**：路径 cache；edition/model/license；可重建；无 sidecar；index_sha；原子切换。
**反例**：索引写 sidecar；跨 edition；结构边进 adjacency；不记 model/dim/license。
**边界**：无 embedding；无 semantic；索引损坏；并发重建。
**U 映射**：U-1、U-13、U-14、U-32。
**建议裁决**：冻结 cache 域/类型/metadata/可重建/edition/原子。
**证据等级**：A（S6-8；S2 semantic-only；R-S9-5）+ R。

---

## S9-4 召回策略（单 seed+1 跳；semantic-only）

**规则**：
```
keyword: FTS（KP label/正文片段）
vector: embedding cosine（enabled 且 model/version 匹配）
graph: 单 seed/focus，沿 E_sem 1 跳；不闭包/不 2 跳；多 seed future（另开修订）
hybrid: keyword+vector+graph 融合；权重 0.4/0.4/0.2 为假设，golden 校准；缺来源权重=0
无 semantic: graph 空，仅 keyword/vector KP，data_state=empty_nosemantic；不伪造簇
结构/reference/extend: 语义贡献=0，不作为 graph 召回/分数；只可 scope/filter
```
**机检**：graph 单 seed+1 跳；仅 E_sem；结构/ref 贡献 0；no_semantic 降级；权重可配/记录。
**反例**：多 seed/2 跳；结构边召回；无 semantic 造簇；权重未记录。
**边界**：无 embedding；小语料；多 KB；S10 写中。
**U 映射**：U-1、U-2、U-13、U-14、U-15、U-17。
**建议裁决**：冻结四类召回/单 seed+1 跳/semantic-only/权重假设/无 semantic。
**证据等级**：A（S2-2/3/12；S4-3；R-S9-4）+ R。

---

## S9-5 排序/打分

**规则**：
```
score = normalize(w_kw*keyword + w_vec*vector + w_graph*graph_semantic)
components 0..1；w 默认 (0.4,0.4,0.2)（假设，golden 校准）；缺来源权重=0
tie-break = (score desc, hop asc, kind, canonical_id asc)   # R-S9-3
reason/score_components 可审计；结构/ref 对 score 贡献=0
确定性：同 query/edition/config 同排序；score∈[0,1]
```
**机检**：tie-break 四元；score 可复算；结构/ref=0；2× 一致；reason。
**反例**：随机排序；结构加分；tie-break 缺 kind；不可复算。
**边界**：同分；缺 embedding；大候选。
**U 映射**：U-2、U-13、U-14、U-27。
**建议裁决**：冻结归一化/权重假设/tie-break/结构 0/确定性。
**证据等级**：A（S4-2；S2；R-S9-3/R-S9-4）+ PI（权重）。

---

## S9-6 过滤/权限/范围

**规则**：
```
filters 固定白名单：kb_id, level_id?, view_family_id?, dimension_id?, file?, section?, anchor?, kind?
单 KB；跨 KB/越权/不存在 ⇒ 可见 GRAPH_INPUT_INVALID/GRAPH_TOOL_INPUT_INVALID（detail）；
过滤在召回/打分前；不泄漏隐藏内容/计数；不返回其他 KB 文件/行号；空结果合法
```
**机检**：白名单；单 KB；越权可见失败；无 hidden 泄漏/计数侧信道；过滤前置。
**反例**：跨 KB；越权返回其他文件；先返回后过滤；total 泄漏。
**边界**：空 filter；不存在 file；anchor stale；权限只读。
**U 映射**：U-12、U-32。
**建议裁决**：冻结白名单/单 KB/权限失败/不泄漏。
**证据等级**：A（S6-1/S6-2；S7）+ R。

---

## S9-7 预算/延迟/分页（max_tokens）

**规则**：
```
budget{max_candidates=50,max_tokens=4000,max_latency_ms=500,cursor?}
超候选/ token/延迟 ⇒ truncated=true + truncated_reason∈{candidates,tokens,latency}；
tokens 用 token_budget；不静默；不编造候选
cursor 绑定 edition；同 edition 稳定；cold/warm 分开；p95 记录环境
超时/不可用 ⇒ 返回已有候选+truncated 或 GRAPH_RETRIEVAL_UNAVAILABLE（可见）
```
**机检**：四字段；token 截断 reason；cursor 稳定；超时可见；冷热/环境。
**反例**：缺 max_tokens；静默截断；cursor 跨 edition；超时空。
**边界**：空结果；大候选；冷索引；多页。
**U 映射**：U-2、U-3、U-32。
**建议裁决**：冻结 budget/token/延迟/截断/游标/冷热。
**证据等级**：A（S7-4；S8-4；R-S9-1）+ PI（默认值）。

---

## S9-8 与图谱交互（id 对齐）

**规则**：
```
candidate id 对齐 S6：kp_id/edge_id/cluster_key/run_id；不新造
S7: candidate -> graph_focus/explain/expand；S9 不产 presence/VM
S4: S9 候选是候选输入；S4 唯一取景/presence/budget
S5: frame 由 S5；S9 不产/改 frame
expand: cluster candidate 带 run_id/cluster_key；交 S7 graph_expand_cluster→S4/S5
```
**机检**：id 可解析；S9 无 presence/VM/frame；expand 一层；不绕 S4。
**反例**：自造 cluster id；返回 VM；给 2 跳；改 frame。
**边界**：多归属；无簇；跨层；S4 失败。
**U 映射**：U-6、U-10、U-15、U-19、U-27。
**建议裁决**：冻结 id 对齐/S4 取景/S5 导航。
**证据等级**：A（S2/S4/S5/S6）+ R。

---

## S9-9 失败/降级

**规则**：
```
索引缺失/损坏 ⇒ 可重建；不可 ⇒ GRAPH_RETRIEVAL_UNAVAILABLE（可见）
edition/stale ⇒ GRAPH_EDITION_STALE；不混用旧索引
无 semantic ⇒ data_state=empty_nosemantic；KP-only；不伪造簇
embedding unavailable ⇒ keyword-only + degraded_reason=embedding_disabled
超时/非法/越权 ⇒ GRAPH_RETRIEVAL_UNAVAILABLE/GRAPH_INPUT_INVALID/GRAPH_TOOL_INPUT_INVALID
只用 S6 GRAPH_*；新码须 S6-ADDENDUM；不编造
```
**机检**：错误码/可见降级；stale 不混用；no_semantic 无簇；不编造；audit。
**反例**：索引坏返回空成功；stale 混用；编簇；静默。
**边界**：空索引；部分损坏；超时；多 KB。
**U 映射**：U-13、U-14、U-27、U-32。
**建议裁决**：冻结失败矩阵/错误码/可见降级/不编造。
**证据等级**：A（S6-9/S7-11；R-S9-5）+ R。

---

## S9-10 评估/回归（可执行 eval 契约）

**golden set schema/路径**：
```
路径：docs/design/multilevel-graph/golden/S9-golden-set.json（S9a 定稿唯一；替代 .memoria audit 副本）
GoldenSet{
  golden_set_id, version, kb_id, edition_sha, created_at,
  queries:[{query_id, query, query_type∈{keyword,vector,graph,hybrid},
            filters?, relevant:[{kind,id,grade?}], tags?[]}],
  hidden:boolean, no_semantic_subset:boolean
}
```
**eval 命令/产物**：
```
python scripts/benchmark/graph/retrieval_eval.py \
  --golden docs/design/multilevel-graph/golden/S9-golden-set.json \
  --kb <kb> --edition <sha> --out artifacts/agent/verify/graph/retrieval_eval/<run_id>.json \
  --sha256
exit 0 = PASS；非 0 = FAIL
指标 JSON{ eval_version, golden_sha, edition, metrics{recall@k,ndcg@k,mrr,coverage,
  no_semantic_ok, sem_purity, latency_p50/p95}, determinism_sha, runs:2 }
```
**阈值/回归**：golden 基线（版本化）；recall/NDCG/MRR 不降（容差 S9a）；`R-DET=100%`（2× top-k/sha 一致）；`R-SEM-PURITY=0`；无 semantic 子集 100% 正确降级；阈值变更需 S9 决策。
**S8 消费**：S8 `GATE-RET` 引用该命令/exit/产物 sha；S8 不定义 S9 阈值/算法。
**机检**：golden 存在/sha；eval exit；指标 JSON/sha；2× 一致；阈值/回归；无 semantic 单列。
**反例**：无命令/exit；golden 无 sha/edition；指标无 JSON；动态 golden；2× 不一致；S8 自定算法。
**边界**：无 semantic；小 golden；embedding off；多 KB。
**U 映射**：U-2、U-13、U-14、U-32。
**建议裁决**：冻结 golden schema/路径/eval 命令/exit/指标 JSON+sha/阈值/2×；S8 gate。
**证据等级**：A（S8-12；S9-10；R-S9-2）+ PI（阈值/容差）。

---

## S9-11 缓存/更新/一致性

**规则**：
```
索引按 edition 目录；S10 写后 edition 变 ⇒ invalidate/rebuild；旧索引只读
增量/全量由 S9a 定；graph adjacency 按 run 重建；manifest 原子切换
并发：同一 kb/edition 构建锁；读旧到新 ready；不写事实；audit build/rebuild/invalidate
```
**机检**：edition/原子/锁/审计；无事实写；旧新不混用；重建同输出。
**反例**：跨 edition；写事实；并发半索引；无审计。
**边界**：S10 批量/部分写；索引损坏；多进程。
**U 映射**：U-29、U-32。
**建议裁决**：冻结 edition/原子切换/重建/审计。
**证据等级**：A（S6-8/S6-10；R-S9-5）+ R。

---

## S9-12 与 S10 边界

**规则**：S10 设计/写 KP/语义边；S9 不设计/不写；S10 写后 edition 变化 ⇒ S9 失效/重建；刷新由 S10 触发、S9 消费；S9 不定义 S10 质量指标。
**机检**：S9 无写；S10 边界；edition 失效；指标归 S10。
**反例**：S9 写语义；用 S9 分数当 KP 质量；S9 设计 KP。
**边界**：S10 未实现/批量写/旧 edition。
**U 映射**：U-29、U-32、U-34。
**建议裁决**：冻结 S9/S10 边界/失效/重建。
**证据等级**：A（S6；S10 章程）+ R。

---

## 附：R-S9 自检（5 条）

| 裁决 | B-v2 落位 |
|---|---|
| R-S9-1 budget/max_tokens | S9-2/S9-7（四字段；token 截断 reason） |
| R-S9-2 可执行 eval | S9-10（golden/schema/sha/命令/exit/JSON+sha/阈值/2×/S8 gate） |
| R-S9-3 枚举/schema | S9-2/S9-5/S9-6（四 query_type 无 lookup；filters kind；candidate kind/status/data_state；tie-break；无 ref_type；500） |
| R-S9-4 单 seed/权重/边 | S9-4/S9-5（单 seed+1 跳；权重假设；结构/ref 0；embedding model/dim/license） |
| R-S9-5 错误码/索引/一致性 | S9-3/S9-9/S9-11（S6 GRAPH_*；cache 域；edition/原子；S10 失效） |

> 独立声明：B-v2 先于 A-v2 完成（A-v2 落盘后才对照）；差异与判断见 `S9-objections-v2.md`；未写产品代码/契约，未 commit。
