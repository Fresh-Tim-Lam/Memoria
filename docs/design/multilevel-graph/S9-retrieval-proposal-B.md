# S9 后端检索提案 B（独立复核方）

> **依据**：`multilevel-graph-vision.md` U-1..U-35；上游冻结 `S0`（`241b1e1e…`）、`S1`（`6676c71d…`）、`S2`（`92bb0041…`）、`S3`（`0ca4ea0e…`+ADDENDUM-1）、`S4`（`2576f6c8…`）、`S5`（`7f4c4515…`）、`S6`（`40f12e5f…`+ADDENDUM-1）、`S7`（`70dd8748…`）、`S8`（`…`），不得违反；本场 `S9-charter.md`。
> **性质**：独立复核方提案；写作时**未读** `S9-retrieval-proposal-A.md`（尚未落盘）；写完再对照，差异见 `S9-objections.md`。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S0–S8 冻结。
> **日期**：2026-11-04（Asia/Shanghai）。

---

## 0. 总原则

1. **S9 只产 candidate/ranking**：不写图谱/DataSource/sidecar/registry/VM/frame；最终 presence 由 S4、agent 工具由 S7；S9 不得绕过 S4/S7。
2. **索引在 S6 派生域**：`.memoria/cache/graph/`；可重建、edition 绑定；不写事实/sidecar。
3. **semantic-only**：结构/引用边不得当语义分数/语义召回；无 semantic 时只返回 KP/关键词候选，不伪造簇/语义。
4. candidate schema 可机检：id/kind/score/reason/refs/edition；分页稳定；edition 显式。
5. 失败/降级可见（`GRAPH_*`）；不编造；过滤/权限不泄漏。
6. 评估指标/golden set/确定性由 S9 定义，S8 消费；S10 写后失效/重建。
7. 不产生第二事实源。

### 0.1 覆盖矩阵（U + S0–S8）

| U# | 落点 | U# | 落点 |
|---|---|---|---|
| U-2/U-3 | 检索价值=S9-1/S9-4 | U-6 | 簇/S9-4 |
| U-10/U-11 | 维度/S9-6 | U-12/U-13 | 维度/连通/S9-4/S9-6 |
| U-14/U-15 | 语义召回/S9-4 | U-17 | 不绕 S4/S9-8 |
| U-19 | KP/簇/S9-2 | U-27 | presence/存无/S9-8 |
| U-32 | 预算/延迟/S9-7 | S6 | 索引域/S9-3 |
| S7 | 消费/S9-1 | S8 | 指标/S9-10 |

---

## S9-1 定位与边界（只产 candidate）

**规则**：S9 是检索/召回/排序层；输入 query/filter/budget/edition，输出 candidate/ranking；**不写图谱、不改事实、不产 VM/presence、不计算导航**。S7 消费 candidate；S4 做最终取景/presence；S10 写语义/KP；S9 不设计图谱。
**形式化/机检**：
```
S9(input) -> CandidatePage[]（只读）
禁止：写 DataSource/sidecar/registry/VM/frame/cache 事实；改 KP/边；调用 S4 替代取景；写 S10
assert tool/service read_only；无 mutation API；无 sidecar 路径；audit
```
**反例**：检索器缓存写 sidecar；返回 VM/presence；直接改边分数写入事实；S9 实现取景。
**边界**：无索引；空 query；多 KB；S7 未启用；S10 写后。
**U 映射**：U-2、U-3、U-32、U-34。
**建议裁决**：冻结只产 candidate/不写/不绕 S4/S7。
**证据等级**：A（S6-1/S6-10；S7-8；S0 D-3）+ R。

---

## S9-2 检索接口（schema/分页/edition）

**schema**：
```
RetrievalRequest{
  request_id, kb_id, query, query_type∈{keyword,vector,hybrid,graph_expand,lookup},
  level_id?, view_family_id?, dimension_id?,
  filters{kp_ids?, file?, section?, anchor?, kind∈{kp,cluster,edge}?},
  budget{max_candidates:int=50,max_tokens:int=4000,max_latency_ms:int=500},
  expected_edition?:string64, page?:{cursor?|offset?}, include_cluster?:bool
}
CandidateRef{
  candidate_id, kb_id, kind∈{kp,cluster,edge,file,anchor}, id,
  edition_sha, level_id?, view_family_id?, dimension_id?,
  score:number[0,1], reason:string[], refs{kp_id?,file?,line?,anchor?,cluster_key?,run_id?,edge_id?},
  status∈{ok,unknown,stale}
}
CandidatePage{request_id, edition_sha, candidates[], next_cursor?, truncated:boolean,
              truncated_reason?, total_estimate?, meta{latency_ms,index_version}}
```
- `expected_edition` 不匹配 ⇒ `GRAPH_EDITION_STALE`；响应 edition 必填。
- 分页游标 = signed/opaque `(edition, query_hash, filters_hash, sort_key, last_id)`；同 query/edition/filters 稳定；不得 raw offset 漂移。
- IDs 对齐 S6：kp_id/edge_id/cluster_key/run_id；不产出 VM/frame。
**机检**：schema/枚举/edition/cursor 稳定；分页同结果；无写字段；id 对齐。
**反例**：无 edition；offset 分页跨刷新漂移；cursor 可伪造/泄漏；返回 frame_id。
**边界**：空结果；大页；多 KB；S10 写后 edition 变。
**U 映射**：U-6、U-10、U-12、U-19、U-32。
**建议裁决**：冻结 request/candidate/page schema/edition/稳定游标/id 对齐。
**证据等级**：A（S6 schema；S7 candidate_ref 归 S9）+ R。

---

## S9-3 索引/存储

**规则**：
```
索引路径：.memoria/cache/graph/index/<edition>/<index_type>/
index_type∈{fts,embedding,adjacency,meta}
索引 metadata: {index_version, edition_sha, source_data_source_sha, config_sha, built_at, model_id?}
可重建：从 DataSource 全量/增量重建；删除索引可恢复；不写 sidecar/manifest
```
- FTS 索引 KP label/正文片段（受权限/隐私）；embedding 存向量（模型 id/version）；adjacency 存 semantic 邻接（仅 E_sem）用于 graph_expand。
- 索引不是事实；版本/edition 绑定；不写 `.memoria/sidecars`。
**机检**：路径在 cache 域；metadata/edition；可重建；无 sidecar 写；索引删除后重建同结果。
**反例**：索引写 sidecar；跨 edition 复用；不可重建；embedding 模型未记录。
**边界**：索引缺失/损坏；大 KB；增量；模型升级。
**U 映射**：U-1、U-32。
**建议裁决**：冻结索引域/类型/metadata/可重建/不写 sidecar。
**证据等级**：A（S6-8 路径；S6-10）+ R。

---

## S9-4 召回策略（semantic-only）

**规则**：
```
keyword: FTS 匹配 query（KP label/正文片段；权限过滤后）
vector: embedding 相似（KP/簇摘要）；模型/config 记录
graph_expand: 从 seed 沿 E_sem（semantic）扩展；结构/reference/extend 不进入语义召回/分数
hybrid: 合并去重 + 加权；权重 config；无 semantic 时只用 keyword/vector KP
no_semantic: 返回 KP 候选/空簇；data_state=empty_nosemantic；不伪造簇
```
- **结构/引用边不得当语义分数/召回**；contain structural 只可用于 scope/partition，不产生 semantic candidate/score；reference/extend 不得当语义。
- 无 semantic 时 cluster 候选为空；不伪造。
**机检**：召回只用 E_sem（graph_expand）；结构/ref 不进 score；无 semantic 行为；候选可解释。
**反例**：用 structural 边扩展簇；reference 边加分；no_semantic 造簇。
**边界**：无 semantic；小语料；多 KB；query 为空。
**U 映射**：U-6、U-13、U-14、U-15、U-27。
**建议裁决**：冻结召回类型/semantic-only/无 semantic 降级。
**证据等级**：A（S2 E_sem；S8-7 semantic-only）+ R。

---

## S9-5 排序/打分

**规则**：
```
score∈[0,1]，由 normalize(加权 components)；
components: keyword_score, vector_score, graph_semantic_score（仅 E_sem）, exact_match,
            recency?（可选，不改变语义）, cluster_affinity?
weights 冻结/配置；score 可解释 reason[]
tie-break: (score desc, kind_rank, canonical_id asc)；确定性
结构/引用边不得进入 semantic component；score 不是事实/置信度
```
- 同输入同 edition/config ⇒ 同排序；分数可复算；归一化/分数段记录。
**机检**：score 可复算；tie-break；结构/ref 不进 semantic；确定性 2x；reason。
**反例**：结构边加分；随机 tie；score 当事实；不可复算。
**边界**：并列分数；多 KB；模型/权重变化（edition/config 版本）。
**U 映射**：U-14、U-15、U-32。
**建议裁决**：冻结分数组成/normalize/tie-break/确定性/semantic-only。
**证据等级**：A（S2/S8-7）+ PI（权重/归一化）。

---

## S9-6 过滤/权限/范围

**规则**：
```
filters: kb_id, level/view_family/dimension, file/section/anchor, kind
权限：按 kb/agent 权限过滤；隐藏内容在检索前过滤；越权不可见；
失败：无权限/不存在 ⇒ GRAPH_INPUT_INVALID（detail unauthorized/not_found）或 S6 扩展码；
不泄漏隐藏文件/正文/行号；不返回被过滤项计数细节（防止推断）
```
- 不做“先返回后过滤”；不泄漏 hidden。
**机检**：filter 生效；越权 failed/empty；无 hidden 泄漏；无计数侧信道。
**反例**：返回隐藏文件路径；越权返回空但泄漏总数；过滤在排序后。
**边界**：多 KB；文件权限；空 filter；anchor 越权。
**U 映射**：U-12、U-32。
**建议裁决**：冻结过滤/权限/可见失败/不泄漏。
**证据等级**：A（S6-1；S7 只读）+ R。

---

## S9-7 预算/延迟/分页

**规则**：
```
budget: max_candidates=50, max_tokens=4000, max_latency_ms=500（S8 可调）
超预算：truncated=true + reason∈{candidates,tokens,latency}；不静默
分页：cursor 稳定；next_cursor=null 表示完；总估计可选
冷/热分开；索引预热；超时⇒GRPH_RETRIEVAL_UNAVAILABLE 或截断可见
```
**机检**：预算字段；truncated/reason；cursor 稳定；超时可见；冷热记录。
**反例**：静默截断；cursor 跨 edition 复用；超时返回半页无标记。
**边界**：空结果；大候选；延迟抖动；多页。
**U 映射**：U-3、U-32。
**建议裁决**：冻结预算/截断/分页/延迟降级。
**证据等级**：A（S8-4 性能条件）+ PI（默认值）。

---

## S9-8 与图谱交互（S4/S5/S6 id 对齐）

**规则**：
```
candidate_id/id 必须来自 S6 实体：kp_id/edge_id/cluster_key/run_id；不新造
S7: candidate -> graph_focus(focus_id) / explain / expand; S9 不产 presence/VM
S4: S9 候选是 P4 candidate 输入之一；S4 做 presence/预算/唯一裁剪
S5: 导航 frame 由 S5；S9 不产 frame/焦点历史
expand cluster: 用 cluster_key+run_id 取子层候选；S9 不绕过 S4 取景
```
**机检**：id 可解析到 S6；S9 无 presence/VM/frame；S4/S5 边界；expand 一层/无隐式 2 跳。
**反例**：S9 返回自造 cluster id；返回 VM；跳过 S4 直接渲染；给 2 跳。
**边界**：无簇；多归属；跨层；S7 未消费。
**U 映射**：U-17、U-19、U-27、U-32。
**建议裁决**：冻结 id 对齐/S4 最终取景/S5 导航/S9 不产 VM。
**证据等级**：A（S4/S5/S6/S7 边界）+ R。

---

## S9-9 失败/降级

**规则**：
```
索引缺失/损坏 => GRAPH_RETRIEVAL_UNAVAILABLE（可见；可回退 keyword/空）
stale/edition mismatch => GRAPH_EDITION_STALE；不混用旧索引
无 semantic => data_state=empty_nosemantic；KP-only；不伪造簇
不可用/超时 => GRAPH_RETRIEVAL_UNAVAILABLE；S7 可见降级
输入非法/越权 => GRAPH_INPUT_INVALID/扩展码；fail-closed
```
- 失败不编造；错误映射 S6 `GRAPH_*`；S7 原样传播；重试有限；审计。
**机检**：错误码/可见降级；无编造；stale 不混用；索引缺失回退；审计。
**反例**：索引坏返回空当“无结果”；stale 混用；无 semantic 编簇；静默。
**边界**：空索引；部分损坏；超时；多 KB。
**U 映射**：U-27、U-32。
**建议裁决**：冻结失败矩阵/错误码/可见降级/不编造。
**证据等级**：A（S6-9；S7-11）+ R。

---

## S9-10 评估/回归

**规则**：
```
metrics: recall@k, NDCG@k, MRR, coverage, latency p95, empty rate
golden set: {golden_set_id, edition_sha, queries[], relevant_ids[]/grades[], hidden}
确定性: 同 query/edition/config 2x 同 ranking/score；hash
S8 消费：S9 定义算法/阈值，S8 只引用/回归门禁；S9 不写 S8 指标
```
- golden set 版本化、edition-pinned；hidden 防过拟合；评估可复跑；不泄漏。
**机检**：指标公式；golden set；2x 确定性；S8 只消费；无过拟合泄漏。
**反例**：动态 golden set；S9 用 S8 阈值改算法；评估不稳定。
**边界**：小 golden；no_semantic；多 KB；模型升级。
**U 映射**：U-32、U-34。
**建议裁决**：冻结指标/golden set/确定性/S8 消费边界。
**证据等级**：A（S8-12 边界）+ PI（阈值）。

---

## S9-11 缓存/更新/一致性

**规则**：
```
索引按 edition 键；S10 写后 edition 变 ⇒ 重建/失效；stale 索引不服务
增量更新/重建；并发读安全；不写事实；audit
缓存清理不影响事实；索引可重建；崩溃恢复可重试
```
**机检**：edition 键；stale 不服务；重建一致；并发/审计；无事实写。
**反例**：跨 edition 复用；写事实；重建不一致；并发脏读。
**边界**：S10 批量写；部分更新；删索引；多 KB。
**U 映射**：U-32、U-34。
**建议裁决**：冻结 edition/重建/并发/审计。
**证据等级**：A（S6-8/S6-10；S10 边界）+ R。

---

## S9-12 与 S10 边界

**规则**：S10 设计/写 KP/语义边；S9 不设计 KP/不写；S10 写后 edition 变化 ⇒ S9 重建/失效；刷新由 S10 触发、S9 消费；S9 不定义 S10 质量指标。
**机检**：S9 无 KP/语义写；S10 边界；edition 失效；指标归 S10。
**反例**：S9 自动写语义边；用 S9 分数当 KP 质量；S9 设计 KP。
**边界**：S10 未实现；批量写；旧 edition。
**U 映射**：U-29、U-32、U-34。
**建议裁决**：冻结 S9/S10 边界/失效/重建。
**证据等级**：A（S6；S10 章程）+ R。

---

## 附：S9 章程预注册判据自检

| 判据 | 本提案 |
|---|---|
| 只产 candidate/不写事实/边界 | S9-1/S9-8 |
| schema/score/reason/edition/分页 | S9-2 |
| 索引可重建/cache 域/不写 sidecar | S9-3 |
| semantic-only/无 semantic | S9-4/S9-5 |
| 过滤/权限/不泄漏 | S9-6 |
| 预算/延迟/截断 | S9-7 |
| 失败/降级 | S9-9 |
| 评估/golden/确定性/S8 | S9-10 |
| 缓存/更新/一致性 | S9-11 |
| S10 边界 | S9-12 |
| A/B 差异逐条 | 见 `S9-objections.md` |
| 不写产品代码/契约/commit | 本文件只写设计 |

> 独立声明：本文件写作时未读 `S9-retrieval-proposal-A.md`（尚未落盘）；差异与判断见 `S9-objections.md`，逐项列不合并。
