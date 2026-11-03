# S9 提案 A-v2：后端检索（候选召回、排序、过滤、预算、评估与一致性）

> **修订依据**：`docs/design/multilevel-graph/S9-RULINGS.md`（R-S9-1..R-S9-5）。
> **本文件**：A 修订版；**不覆盖** `S9-retrieval-proposal-A.md`（v1 `fa2d2092…`），保留审计链。

> **提案方**：主办研究（`gm-seminar-researcher`）｜**票**：task-336｜**日期**：2026-11-04（Asia/Shanghai）
> **最高依据**：`docs/design/multilevel-graph-vision.md`（U-1..U-35）。
> **上游冻结（不得违反）**：S0–S8 九份 v1 + `S3-ADDENDUM-1` + `S6-ADDENDUM-1`。
> **本场章程**：`docs/design/multilevel-graph/S9-charter.md`（S9-1..S9-12）。
> **工程输入**：`ENGINEERING-PLAN.md`（27 图、I-01..I-13）、S8 G6/G7 规范；现有检索面 `src/memoria/services/lexical_index.py`、`embedding_provider.py`（只读证据）。
> **独立性**：未阅读 S9 复核方草稿；本提案独立撰写。
> **纪律**：只写检索契约；不写产品代码；不改 S0–S8 冻结稿；不 commit。

---

## 0. 总口径

```
S9 = 检索层：只产出 candidate/ranking（含 score/reason/edition），不写图谱/不改事实。
事实仍来自 S6 DataSource（只读）；S9 索引是派生缓存（可重建、edition 绑定）。
S7 消费 candidate_ref；S4 做最终取景/presence；S10 写 KP/语义边并触发重建。
semantic-only：结构/引用边不得进入语义召回/分数；no_semantic 合法且必须可见。
```

**证据等级**：A（冻结条款/工程/代码事实）；B（实测产物）；C（推理）；**本项目假设**（接口字段/阈值/golden set）。

---

## 1. S9-1 定位与边界

**定义/规则（一句话）**：S9 只产出 `candidate_ref`/排序，不写图谱、不改事实、不做 presence；与 S7（消费）、S4（取景）、S6（事实/缓存域）、S10（写入）边界固定。

**形式化**：
```
S9 输出 = {candidates[], ranking, score, reason, edition_sha}
S9 不做：写 sidecar/manifest/registry/cache（除自己的派生索引）、改 KP/边、
        计算 presence/rule_id、渲染、导航、最终取景
S7：消费 candidate_ref → graph_focus/explain/expand
S4：唯一取景/presence/budget；S9 candidate 只是候选，不等于 shown
S10：写 KP/语义边；写后 edition 变化 → S9 失效/重建
S6：事实只读；S9 索引只写 S6 cache 域；D-3 禁 sidecar
```
**反例**：S9 直接返回 shown/VM；S9 写 sidecar/registry；S9 把 candidate 当最终取景；S9 改 KP。
**边界**：无索引；S10 写入中；S4 取景失败；无 semantic。
**机检条件**：
```
- S9 无事实写路径；索引只写 .memoria/cache/graph/**；无 sidecar
- 输出候选不含 presence=shown/VM 字段；不声称最终取景
- candidate_ref 可被 S7/S4 消费；edition 绑定
```
**U 映射**：U-1、U-2、U-32、U-34。
**建议裁决**：采纳只产出候选/排序、不写事实/不做取景；边界固定。
**证据等级**：A（S7-1/S7-8；S4-1；S6-1/S6-8；S0-10）；**本项目假设**（接口形态）。

---

## 2. S9-2 检索接口

**定义/规则（一句话）**：S9 接口显式 query/query_type/kb_id/dimension/filters/budget/expected_edition，输出 `candidate_ref`（含 id/file/anchor/score/reason/edition）与稳定游标。

**RetrievalRequest schema**：
| 字段 | 类型 | 枚举/默认 | 失败码 |
|---|---|---|---|
| `query` | string | 非空；长度上限（S9a） | `GRAPH_INPUT_INVALID` |
| `query_type` | enum | `keyword/vector/graph/hybrid`；默认 hybrid | `GRAPH_INPUT_INVALID` |
| `kb_id` | string | 单 KB；非空 | `GRAPH_INPUT_INVALID` |
| `dimension_id` | enum | `hierarchy/association`；默认 hierarchy | `GRAPH_DIM_UNKNOWN` |
| `filters` | object | `{level_id?,view_family_id?,file_prefix?,section?,anchor?}` | `GRAPH_INPUT_INVALID` |
| `budget` | object | `{max_candidates=50,timeout_ms=800,cursor?}` | `GRAPH_TOOL_BUDGET_EXCEEDED`（S7） |
| `expected_edition` | string(64)? | 可选；不匹配 stale | `GRAPH_EDITION_STALE` |

**CandidateRef schema**：
```
{candidate_id, kind ∈ {kp,cluster,edge,file,anchor},
 status ∈ {ok,degraded,unknown}, data_state ∈ {ok,empty_nosemantic},
 kp_id?, cluster_id?, run_id?, cluster_key?, edge_id?,
 file?, line_start?, line_end?, anchor?,
 score:0..1, score_components{keyword,vector,graph},
 reason ∈ {keyword_match,vector_match,semantic_hop,hybrid_fusion,filter},
 edition_sha, rank, matched_terms?[]}
```
**RetrievalResponse**：
```
{candidates[], next_cursor?, total_estimated?, truncated:bool,
 truncation_reason?, edition_sha, query_hash, audit_id, degraded_reason?, scores_meta}
```
**分页**：`next_cursor` 不透明，含 `(edition, query_hash, rank/tie)`；同 edition 稳定；edition 变 ⇒ `GRAPH_EDITION_STALE`；不得跨 edition 拼接。
**反例**：query 空/超长；cursor 明文偏移跨 edition；无 score 理由；candidate 无 edition/kind/status；分页重复/漏。
**边界**：空结果；单 KB；超大 k；cold/warm；无 semantic。
**机检条件**：
```
- request/response schema 可校验；candidate kind/status/data_state 枚举白名单
- score/reason/edition 必填；cursor 绑定 edition；无 ref_type
- 同请求同 edition 结果确定；分页拼接无重复/漏
```
**U 映射**：U-2、U-10、U-11、U-32。
**建议裁决**：采纳 request/response/candidate_ref schema（kind/status/data_state）与 edition 游标。
**证据等级**：A（S7-2/S7-8；S6-1；S8-12）；**本项目假设**（字段/默认值）。

---

## 3. S9-3 索引 / 存储

**定义/规则（一句话）**：索引 = FTS/embedding/graph adjacency，全部派生、可重建、edition 绑定；只写 S6 `.memoria/cache/graph/`，不写 sidecar/config 事实。

**索引 schema**：
```
RetrievalIndex{
  index_version, kb_id, edition_sha, built_at, source{manifest_sha, collect_version},
  fts{tokenizer, postings, doc_count, index_sha},
  embedding{model_id, dim, license, vectors[], index_sha, enabled},
  graph{run_ids[], adjacency{semantic_edges_only:true}, index_sha},
  compatible{contract_version, s6_contract_sha}
}
路径：.memoria/cache/graph/retrieval/<kb_id>/<edition_sha>/
manifest：index_manifest{index_version, edition_sha, shas, rebuildable:true}
```
**规则**：
```
只从 DataSource/S2 run 构建；不写 sidecar/manifest/registry；
edition 变 ⇒ 新索引目录，旧索引只读/可 GC；可删除重建；
embedding 可 disabled（keyword-only）；graph adjacency 只含 semantic 边
```
**反例**：索引写 sidecar；跨 edition 复用；结构边进 graph adjacency；embedding 不记 model/dim。
**边界**：无 embedding；无 semantic；索引损坏；重建并发。
**机检条件**：
```
- 索引路径在 cache 域；无事实写；可删除重建同输出
- edition/model/source 记录；graph adjacency 只 semantic
- index_sha 可复算；compatible 检查
```
**U 映射**：U-1、U-13、U-14、U-32。
**建议裁决**：采纳 FTS/embedding/graph 索引、cache 域、可重建/edition 绑定。
**证据等级**：A（S6-8 路径；S2-2/3 semantic-only；现有 lexical/embedding 缓存实现）；**本项目假设**（索引字段/目录）。

---

## 4. S9-4 召回策略

**定义/规则（一句话）**：召回 = keyword/vector/graph semantic expand/hybrid；图谱只沿 semantic 边扩展；无 semantic 时禁用 graph、返回 KP-only；不得伪造语义。

**形式化**：
```
keyword: FTS/lexical（KP label/body/alias）
vector: embedding cosine（若 enabled）
graph: **单 seed** + semantic 边 1 跳（S4 focus-only 对齐；不闭包/不 2 跳；多 seed 标 future）
hybrid: 融合 keyword+vector+graph（权重可配；默认 keyword 0.4/vector 0.4/graph 0.2，**假设值，需 golden 校准**）
无 semantic：graph 召回为空；返回 keyword/vector KP + degraded_reason=no_semantic_edges
结构/引用边：不得进入 graph 语义召回；可作过滤器/候选 ID 对齐，不作为语义分数
```
**反例**：用 contain/structural 边做语义召回；无 semantic 伪造簇；graph 闭包 2 跳；vector 关闭仍声称 hybrid。
**边界**：空 query；单字；无 embedding；S10 写入中；多 KB。
**机检条件**：
```
- graph 召回边类型只 semantic；结构/引用边权重=0/不进入
- no_semantic 时 graph 空 + degraded 可见；无伪造簇
- 1 跳限制；query_type 与实际召回一致
```
**U 映射**：U-1、U-2、U-10、U-13、U-14、U-15、U-17。
**建议裁决**：采纳四类召回、单 seed+semantic 1 跳（多 seed future）、semantic-only、无 semantic 降级；权重标假设。
**证据等级**：A（S2-2/3/12；S4-3；S0-6；现有 search_lexical/search_semantic）；**本项目假设**（融合权重）。embedding 索引须记 `model_id/dim/license`（license 供合规审计）。

---

## 5. S9-5 排序 / 打分

**定义/规则（一句话）**：分数来源/归一化/融合显式，排序确定性、tie-break 固定、每候选可解释；结构/引用边不得进入语义分数。

**形式化**：
```
score = normalize(w_kw*keyword + w_vec*vector + w_graph*semantic_graph)
components{keyword,vector,graph} 各自 0..1；w 可配；缺来源权重=0
参数化：default w=(0.4,0.4,0.2)；no embedding ⇒ w_vec=0 归一化
排序键：(score desc, hop asc, kind, canonical_id)
tie-break：kind 按 {kp,cluster,edge,file,anchor} 固定序，再 canonical_id；无随机/时间
reason：命中来源/语义跳/融合；score_components 可审计
semantic-only：structural/reference 对 score 贡献=0，且不得用于 graph 分量
```
**反例**：随机排序；结构边加分；score 不归一化；无 reason；同分不稳定。
**边界**：全 0 分；缺 embedding；同分；大候选。
**机检条件**：
```
- 同 query/edition 排序 deterministic；tie-break 可复算
- 结构/引用边语义贡献=0；score_components 与 score 一致
- 每候选有 reason；score∈[0,1]
```
**U 映射**：U-2、U-13、U-14、U-27。
**建议裁决**：采纳显式融合/归一化/确定性 tie-break `(score,hop,kind,canonical_id)`/可解释；结构边零语义分。
**证据等级**：A（S4-2 tie-break；S2-2/3；S8-7）；**本项目假设**（权重）。

---

## 6. S9-6 过滤 / 权限 / 范围

**定义/规则（一句话）**：过滤限单 KB/level/view_family/dimension/file/section/anchor；越权/不存在可见失败；不泄漏隐藏内容/计数。

**形式化**：
```
filters 白名单；kb_id 必须单 KB；跨 KB ⇒ GRAPH_INPUT_INVALID
level/view_family 必须合法；dimension active；file/section/anchor 只读校验；kind 与 candidate kind 对齐
越权/不存在：可见错误（不返回其他 KB/隐藏内容）；不得用 total 泄漏
过滤后空结果合法；不伪造 candidate
```
**反例**：跨 KB 搜索；越权返回其他文件；用 total 泄漏隐藏数量；filter 未校验。
**边界**：空 filter；不存在 file；anchor 失效；权限只读。
**机检条件**：
```
- 单 KB/白名单过滤；跨 KB/越权错误可见
- 不泄漏隐藏内容/计数；空结果合法
- filter 字段不进入 score 伪造
```
**U 映射**：U-32、U-34。
**建议裁决**：采纳单 KB/白名单过滤/可见失败/不泄漏。
**证据等级**：A（S6-1/S6-2；S8 边界）；**本项目假设**（权限模型）。

---

## 7. S9-7 预算 / 延迟 / 分页

**定义/规则（一句话）**：候选数/token/延迟有预算；超预算显式 `truncated` 或降级，不静默；分页游标稳定，冷/热分别测。

**形式化**：
```
budget{max_candidates=50, max_tokens=4000, max_latency_ms=500, cursor?}
超 token ⇒ truncated=true, truncation_reason="token_budget"（与 S7 默认 4000 一致；G7 可归因）
超时/超量 ⇒ truncated=true + reason（"latency_budget"/"candidate_budget"）
延迟测量：cold/warm，keyword/vector/hybrid 分开；P50/P95；参考硬件/embedding on/off
分页：cursor 绑定 edition/query_hash/rank；同 edition 稳定；不跨 edition
超预算不编造候选；返回已有候选 + truncated/next_cursor
```
**反例**：静默截断；cursor 跨 edition；超时返回空不报；冷热混测。
**边界**：k 极大；超时；无 embedding；索引冷。
**机检条件**：
```
- 超 token 可见 truncated=true/reason=token_budget；超时/候选数同理；不静默
- max_latency_ms 默认 500；cursor 稳定/不可跨 edition；分页无重复漏
- 冷/热记录；延迟有环境
```
**U 映射**：U-2、U-3、U-32。
**建议裁决**：采纳预算/超时显式、稳定游标、冷热测量。
**证据等级**：A（S7-4 max_tokens=4000；S8-4 测量条件）；**本项目假设**（max_candidates/max_latency_ms 默认）。

---

## 8. S9-8 与图谱交互

**定义/规则（一句话）**：candidate 的 id 与 S4/S5/S6 对齐（kp/cluster/run/edge/frame）；expand 取候选后仍由 S4 取景；S9 不绕过 S4。

**形式化**：
```
candidate_ref.id 对齐：
  kp → canonical kp_id；cluster → cluster_id(run_id+seq)+cluster_key；
  edge → canonical edge_id；file/anchor → DataSource anchor；
  frame → 可选 frame_id 仅引用 S5 当前帧，不创建/不改
S9 不计算 presence/rule_id；S4 唯一取景
expand：S9 返回 cluster candidate（run_id/cluster_key）；S7 graph_expand_cluster
        交给 S4/S5；S9 不直接返回子图 shown
```
**反例**：S9 自己返回 shown 子图；candidate cluster 无 run/key；绕过 S4 直接渲染；frame_id 自造。
**边界**：多归属簇；无 frame；S5 导航中；S4 失败。
**机检条件**：
```
- id 对齐；cluster 必带 run_id/cluster_key；edge canonical
- S9 无 presence/VM 字段；expand 不返回 shown
- frame_id 只引用不改
```
**U 映射**：U-6、U-10、U-15、U-19、U-32。
**建议裁决**：采纳 id 对齐、expand 交给 S4/S5、S9 不绕过 S4。
**证据等级**：A（S2-7；S4-1/S4-3；S5-1；S6-4）；**本项目假设**（frame 引用字段）。

---

## 9. S9-9 失败 / 降级

**定义/规则（一句话）**：索引缺失/stale/edition/无 semantic/不可用均可见降级；不编造；错误用 S6 `GRAPH_*`。

**形式化**：
```
索引缺失 ⇒ 可重建则重建；否则 GRAPH_RETRIEVAL_UNAVAILABLE（可见）
edition 不匹配 ⇒ GRAPH_EDITION_STALE；不混用旧索引
无 semantic ⇒ keyword/vector KP-only + degraded_reason=no_semantic_edges
embedding 关闭 ⇒ keyword-only + degraded_reason=embedding_disabled
超时/不可用 ⇒ GRAPH_RETRIEVAL_UNAVAILABLE；可返回部分 + truncated
不得：伪造 candidate/簇/分数；静默回退不标
```
**反例**：索引坏仍返回空成功；stale 混用；无 semantic 伪造簇；超时不报。
**边界**：索引损坏；S10 写入中；embedding 模型缺失；无 KB。
**机检条件**：
```
- 每种失败有可见 code/degraded_reason；无静默
- stale 不混用；no_semantic 无簇；候选不伪造
- 可重建/部分结果有 truncated
```
**U 映射**：U-13、U-14、U-27、U-32。
**建议裁决**：采纳显式失败/降级、不编造、S6 错误码。
**证据等级**：A（S6-9；S7-11；S2-12）；**本项目假设**（降级文案）。

---

## 10. S9-10 评估 / 回归

**定义/规则（一句话）**：S9 定义 recall@k/NDCG@k/MRR/coverage 与 golden set/确定性；S8 只消费；阈值/回归归 S9（S8 gate 引用）。

**eval 契约（可执行）**：
```
golden 路径（唯一）：.memoria/agent/audit/graph/golden/S9-golden-set.json
  （候选；S9a 定稿唯一；若用 docs/.../golden 亦须同 sha，不得双源）
golden schema：
  {golden_version, kb_id, edition_sha, queries[{query_id, query, query_type,
   dimension_id?, filters?, labels[{kind,id,grade(0..3),reason}]}],
   dataset_flags{no_semantic:bool}, sha256}
  文件 sha256 与内容 sha 可复算；labels 不由检索器生成
命令：python scripts/verify/eval-retrieval.py --kb <kb>   --golden <golden.json> --out <metrics.json>
exit：全部指标满足阈值 ⇒ 0；回归超容差/缺 golden/sha 不符 ⇒ ≠0
指标 JSON：{eval_version, golden_sha, edition_sha, query_count,
  metrics{recall@k,ndcg@k,mrr,coverage}, by_query_type{...},
  determinism{run1_sha,run2_sha,equal:true}, passed:bool, failed_metrics[]}
metrics.json 自身 sha256 记录；2× 复跑要求 determinism.equal=true
阈值：recall@k/ndcg@k/mrr 由 S9a 基线定；回归容差（建议相对下降 ≤2%，
  绝对值不低于基线-0.02；S9a 定）；no_semantic 数据集单列，不混入主指标
S8 gate 引用：`eval-retrieval` 命令 + metrics.json sha + exit code
```
**指标表（与 eval JSON 对应）**：
| ID | 定义/公式 | 阈值/证据 |
|---|---|---|
| `R-RECALL@k` | `relevant retrieved@k / all relevant` | S9a 基线；golden labels |
| `R-NDCG@k` | 归一化折损累计增益（grade 0..3） | 基线不降（容差 S9a） |
| `R-MRR` | `mean(1/rank_first_relevant)` | 基线不降 |
| `R-COVERAGE` | 有候选 query 比例；semantic coverage | 信号 |
| `R-DET` | 两次 run top-k/metrics 一致 | 100% |
| `R-SEM-PURITY` | 结构/引用边进入语义分数次数 | 0 |
**反例**：无 golden/命令/exit；metrics 无 sha；golden 与测试混用；结构边标 relevant；只测 keyword；2× 不确定。
**边界**：无 semantic；小 golden；多 KB；embedding off；golden edition 不匹配。
**机检条件**：
```
- golden/路径/schema/sha 可复算；eval exit=0/非0 可判
- metrics JSON 含 sha/阈值/失败项；2× determinism
- 结构/引用边语义分=0；no_semantic 单列；S8 gate 引用
```
**U 映射**：U-2、U-13、U-14、U-32。
**建议裁决**：采纳可执行 eval 契约（golden/命令/exit/metrics sha/阈值/2×/S8 gate 引用）。
**证据等级**：A（S8-12 边界；S8 指标消费）；**本项目假设**（golden 路径/命令/阈值）。

---

## 11. S9-11 缓存 / 更新 / 一致性

**定义/规则（一句话）**：索引增量/失效/重建与 edition 绑定；并发安全；不写事实源；审计可追溯。

**形式化**：
```
edition 变化 ⇒ 新索引目录；旧索引只读/可 GC
增量：FTS/embedding 按文件/内容指纹增量；graph adjacency 按 run 重建
失效：S10 写后 event 触发 invalidate；S9 不主动改事实
并发：同一 kb/edition 构建锁；读旧索引直到新索引 ready；原子切换 manifest
审计：build/rebuild/invalidate 事件写 S6 audit；不写 sidecar
```
**反例**：写 sidecar；edition 变化复用旧索引；并发半索引；无审计。
**边界**：构建中查询；索引损坏；多进程；大 KB。
**机检条件**：
```
- 索引只 cache 域；edition 绑定；旧索引可读/新索引原子切换
- 重建可复跑；并发锁；审计事件
- 无事实写
```
**U 映射**：U-29、U-32。
**建议裁决**：采纳 edition 绑定/增量/失效/原子切换/审计。
**证据等级**：A（S6-8/S6-10；现有 lexical/embedding 缓存）；**本项目假设**（增量策略）。错误码只用 S6 `GRAPH_*`；新码须 `S6-ADDENDUM`。

---

## 12. S9-12 与 S10 边界

**定义/规则（一句话）**：S10 设计/写 KP/语义边；写后 edition 变化触发 S9 重建/失效；S9 不设计 KP、不自动推断语义。

**形式化**：
```
S10 写 → edition_sha 变化 / write event → S9 invalidate/rebuild
S9 只消费 DataSource/S2 run；不写 KP/边；不自动 semantic
写入中：旧索引只读；新 edition ready 后原子切换
S9 的 evaluation/golden 可引用 S10 的 KP，但不定义其质量
```
**反例**：S9 自己写 KP/边；S10 写后不失效；S9 自动补语义。
**边界**：批量写；部分写；回滚；多 KB。
**机检条件**：
```
- S9 无写 KP/边路径；edition 变化失效
- 旧/新索引不混用；S10 写路径有审计
```
**U 映射**：U-29、U-32、U-34。
**建议裁决**：采纳 S10 写入/S9 失效重建；S9 不设计 KP。
**证据等级**：A（S0-10；S6-10；S7-9）；**本项目假设**（事件形态）。

---

## 13. 覆盖矩阵

| 侧 | 覆盖 | 落点 |
|---|---|---|
| S0 | semantic-only/单一真源 | S9-1/S9-4/S9-5 |
| S1/S2 | H/A、run/簇、no_semantic | S9-4/S9-8 |
| S4 | 取景/presence/一跳 | S9-1/S9-8 |
| S5 | frame/导航 | S9-8 |
| S6 | 事实/cache/错误 | S9-1/S9-3/S9-9/S9-11 |
| S7 | candidate_ref/工具 | S9-2/S9-8 |
| S8 | G6/G7/指标消费 | S9-10 |
| U | U-2/10/11/13/14/15/17/19/27/32/34 | 各条 |

---

## 14. A-v2 变更表（逐条旧→新）

| # | 旧（v1） | 新（v2） | 裁决 |
|---|---|---|---|
| 1 | S9-2/7 budget 无 max_tokens | `{max_candidates,max_tokens=4000,max_latency_ms=500,cursor?}`；超 token `truncated=true, reason="token_budget"`；G7 可归因 | R-S9-1 |
| 2 | S9-10 只有指标名 | 可执行 eval：golden 路径/schema/sha、`eval-retrieval` 命令/exit、metrics JSON+sha、阈值/容差、2× 确定性、no_semantic 单列、S8 gate 引用 | R-S9-2 |
| 3 | S9-2 `ref_type`/filters/latency 不统一 | `query_type` 四值无 lookup；filters 含 `kind`；candidate `kind/status/data_state`；弃 `ref_type`；tie-break `(score,hop,kind,canonical_id)`；`max_latency_ms=500` | R-S9-3 |
| 4 | S9-4 未钉单 seed/权重/embedding license | 单 seed+semantic 1 跳（多 seed future）；`0.4/0.4/0.2` 标假设；结构/引用边贡献=0；embedding `model_id/dim/license` | R-S9-4 |
| 5 | S9 错误码/索引/S10 失效未统一 | 只用 S6 `GRAPH_*`（新码须 ADDENDUM）；索引 `.memoria/cache/graph/retrieval/` 可重建/edition/原子切换/不写 sidecar；S10 写后失效重建 | R-S9-5 |

## 15. 仍存争议 / 待 Lead·SE 裁决

1. **golden set 来源/规模**：需 S9a/SE 提供；无 semantic 数据集单列，阈值需实测。
2. **hybrid 权重/归一化**：默认 0.4/0.4/0.2 为建议，需 golden 校准。
3. **embedding 模型/维度/许可**：S9 只记 model_id/dim；具体模型选型需 SE/运维。
4. **graph 召回是否允许多 seed**：本提案单 focus/seed + 1 跳；多 seed 需 S4/S5 对齐。
5. **索引增量策略**：FTS/embedding 增量 vs 全量重建，需 SE 定。
6. **S9 接口是否新增错误码**：本提案只用 S6 已有 `GRAPH_*`；若需 `GRAPH_RETRIEVAL_*` 新码须 S6-ADDENDUM 扩展。

---

## 16. 证据锚

```text
S0：S0-terms-v1.md:56-61（presence）、:75-79（VM）、:81-85（agent 边界）、:100-107（D-3）
S1：S1-dimensions-v1.md:57-67（H/A）、:99-107（present）
S2：S2-clustering-v1.md:21-29（μ/β semantic-only）、:47-51（run）、:73-76（no_semantic）
S4：S4-render-v1.md:16-19（唯一裁剪）、:26-34（focus-only）
S5：S5-nav-v1.md:16-19（frame）、:31-34（drill/back）
S6：S6-contract-v1.md:17-19（单一真源）、:22-24（DataSource/View）、:57-66（缓存/错误）
S7：S7-agent-v1.md:20-33（ViewResponse/工具）、:58-60（S9 边界）
S8：S8-metrics-v1.md:73-74（S9/S10 边界）
工程：ENGINEERING-PLAN.md:933-945（I-01..I-13）
现有实现（只读证据）：lexical_index.py:58,139,203,213,231,516；embedding_provider.py:41,230,324,341,406
```
