# S9 独立异议与 A/B 差异

> **依据（不可改写）**：`multilevel-graph-vision.md` U-1..U-35；上游冻结 S0–S8 九份 v1 + `S3-ADDENDUM-1`/`S6-ADDENDUM-1`，不得违反；`S9-charter.md`。
> **对象**：`S9-retrieval-proposal-A.md`（主办研究，sha **`fa2d2092ec988306d4783acc36556a842100efd8e028a39fdc935d529a97c2a6`**，20,185 B）与 `S9-retrieval-proposal-B.md`（本复核方，sha **`a95545dd692b57a00810c91f84a26a4960d1210fd8c7d5001ee1588e0c7c4c19`**，14,006 B）。
> **独立性**：B 于 00:38:11 落盘，A 于 00:39:33 才出现；B 写作时未读 A。以下为写完后对照，逐项列、不合并。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S0–S8 冻结。

---

## 0. A/B 差异总表（S9-1..S9-12）

| 议项 | A 的立场（A-v1） | B 的立场（B-v1） | 差异与判断 |
|---|---|---|---|
| S9-1 边界 | 只 candidate/ranking；不写/不做 presence；S7/S4/S10 边界 | 同 | 一致。 |
| S9-2 接口 | request/candidate/response schema；query_type `keyword/vector/graph/hybrid`；budget `{max_candidates,timeout_ms,cursor}`；filters 无 `kind`；candidate `ref_type`+score_components/reason/edition/rank；cursor 绑定 edition | query_type `keyword/vector/hybrid/graph_expand/lookup`；budget 含 `max_tokens`；filters 含 `kind`；candidate 含 `status`；cursor 签名/opaque | **关键差异**：A budget **缺 max_tokens**（S9-7/S7 token 预算要求）；query_type/filters/status 枚举不同，需冻结（P1-1/P2-3）。 |
| S9-3 索引 | FTS/embedding/graph；cache 域；edition；可重建；graph adjacency semantic-only | 同 | 一致；A 字段更细。 |
| S9-4 召回 | keyword/vector/graph semantic 1 跳/hybrid；无 semantic 降级；结构/ref 不进语义 | 同 | 一致。 |
| S9-5 排序 | score 归一化/权重（0.4/0.4/0.2）；tie-break `(score,hop,canonical_id)`；reason；结构/ref=0 | 同核心；tie-break 含 kind | 一致；权重/枚举需冻结（P2）。 |
| S9-6 过滤/权限 | 单 KB/白名单；越权可见失败；不泄漏 | 同核心；filters 含 kind | 一致；A filters 缺 kind（P2-3）。 |
| S9-7 预算/延迟 | `max_candidates=50, timeout_ms=800`；truncated/reason；cursor；冷热 | `max_candidates/max_tokens/max_latency_ms`；truncated；cursor；冷热 | **A 缺 max_tokens**（P1-1）；B 有。 |
| S9-8 图谱交互 | id 对齐 kp/cluster/run/edge/frame；expand 交 S4/S5；S9 不产 presence | 同 | 一致。 |
| S9-9 失败/降级 | 索引缺失/stale/edition/no_semantic/不可用；`GRAPH_*` | 同 | 一致。 |
| S9-10 评估 | R-RECALL@k/R-NDCG@k/R-MRR/R-COVERAGE/R-DET/R-SEM-PURITY；golden；S8 消费；阈值“基线不降” | 同核心；指标较简；无命令/exit/snapshot | 一致；A 更细但**无 eval 命令/exit/快照**（P1-2）。 |
| S9-11 缓存/更新 | edition 绑定/增量/失效/原子切换/审计 | 同 | 一致。 |
| S9-12 S10 | S10 写/S9 失效重建；不设计 KP | 同 | 一致。 |

**总判断**：A 在接口字段/索引/评估指标上更强；B 在 token 预算/filters/status 上更完整。**P1 集中在 A 缺 max_tokens、评估不可执行**；P2 为 query_type/filters/status 枚举冻结。

---

## 1. 异议（按严重度；P0=违反 S0–S8；P1=冻结前必须裁；P2=后续/SE）

### P1-1（A）`budget` 缺 `max_tokens`，与 S9-7/S7 token 预算不一致

- **议项**：S9-7/S9-2（S7 token、S8 token 指标；S9 charter S9-7）。
- **异议**：A S9-2 的 `budget` 只有 `{max_candidates, timeout_ms, cursor}`，**没有 `max_tokens`**；S9-7 只讲候选数/延迟，没有 token 预算。S9 charter 明确“token/候选数/延迟预算”；S7 `graph_*` 工具默认 `max_tokens=4000`，S8 G7 `A-TOKEN` 依赖 token 预算；S9 不声明/不截断 token，S7 只能在工具层再截，可能导致“S9 返回超 token 候选 + S7 静默/二次截断”，隐藏 token 超限；S9-7 的 truncated 也无 `reason=token`。
- **反例**：S9 返回 200 个候选（每候选长摘要）超 4000 token；S7 工具截断/超预算；S9 未标 token truncated，G7 token 指标无法归因。
- **修复**：S9-2 budget 加 `max_tokens`（默认 4000，S8/S9 可调）；S9-7 超 token ⇒ `truncated=true, truncated_reason="token_budget"`；候选摘要/字段按 token 裁剪并标记；机检 token 计数/截断可见；与 S7/S8 同源。B 已有 max_tokens，A 需补。
- **严重度**：预算/token 契约 ⇒ **P1（冻结前）**。

### P1-2（A/B）S9-10 评估只有指标/“基线不降”，缺可执行命令/exit code/golden 快照/阈值

- **议项**：S9-10（S9 章程判据 8；S8 消费）。
- **异议**：A/B 都定义 recall@k/NDCG/MRR/coverage/确定性，但**没有 eval 命令、exit code、golden set 路径/sha、snapshot 产物、阈值/回归判定**；A 仅写“基线不降”，B 类似。S9 章程要求“评估 metrics/golden set/阈值明确（S9 定义，S8 消费）”、预注册判据“阈值/回归”；只有指标名不足，无法机判，也无法让 S8 gate 引用。A §14 自列 golden 来源/阈值待定。
- **反例**：实现声称 recall@k 0.8，但无 golden 文件/命令/exit；S8 只能人工；golden 变更不可追溯；两次结果不同无判定。
- **修复**：S9-10 增加：golden set schema/路径（edition/query/labels/query_type/hidden）、eval 命令（如 `python scripts/benchmark/graph/retrieval_eval.py --golden ... --out ...`）、exit code、指标 JSON/snapshot sha、阈值（基线不降 + 绝对下限/回归容差）、两次确定性；S8 `GATE-RET` 引用；无 semantic/embedding off 单列。
- **严重度**：评估可机判 ⇒ **P1（冻结前）**。

### P2-3（A/B）`query_type`/`filters`/`candidate.status` 枚举与 schema 未统一

- **议项**：S9-2（S7 candidate_ref；S9 schema 可机检）。
- **异议**：A query_type `{keyword,vector,graph,hybrid}`、filters 无 `kind`、CandidateRef 无 `status`；B query_type `{keyword,vector,hybrid,graph_expand,lookup}`、filters 含 `kind`、CandidateRef 含 `status{ok,unknown,stale}`。同一 S9 接口两套枚举，S7/S8 消费不一致；`lookup`/`graph_expand` 语义未定义；`kind` 过滤缺失会让 agent 无法只取簇/边。
- **修复**：S9 冻结唯一枚举：query_type（推荐 `keyword/vector/graph/hybrid`，lookup 作为 query_type? 或 lookup 由 S7 lookup 单独）；filters 加 `kind∈{kp,cluster,edge,file,anchor}`；CandidateRef 加 `status{ok,unknown,stale}`（unknown 显式、stale 引用）；机检 schema/枚举；A/B 统一。
- **严重度**：接口 schema/可机检 ⇒ P2（冻结前补）。

### P2 清单

| # | 项 | 修复 |
|---|---|---|
| P2-1 | A budget `timeout_ms=800` vs B `max_latency_ms=500` | S8/S9 冻结统一名/值；超时可见；冷热/硬件 |
| P2-2 | A tie-break `(score,hop,canonical_id)` vs B 加 kind | 统一 tie-break 字段；B 的 kind 是否影响排序需说明（避免结构偏好语义） |
| P2-3 | A filters 缺 `kind`；B 有 | 统一 filter schema（含 kind/dimension） |
| P2-4 | A candidate 无 `status`；B 有 | 统一 status（ok/unknown/stale）+ edition；unknown≠无 |
| P2-5 | A S9-2 candidate `ref_type` vs S7 `kind` 命名 | 统一 candidate kind/ref_type；S7 消费映射 |
| P2-6 | A S9-9 无 `data_state` 字段；B 无 | 返回 data_state（no_semantic）与 degraded_reason；S7/S8 消费 |
| P2-7 | hybrid 权重 0.4/0.4/0.2 未校准 | golden 校准；权重入 index/config 版本；结构/ref=0 |
| P2-8 | embedding 模型/维度/许可未定 | 记录 model_id/dim/license；disabled 降级 |
| P2-9 | 多 seed/graph 召回 | 单 seed+1 跳；多 seed 需 S4/S5 对齐，不夹带 |
| P2-10 | S9 新错误码 | 只用 S6 `GRAPH_*`；新增须 S6-ADDENDUM；`GRAPH_RETRIEVAL_UNAVAILABLE` 已扩 |

---

## 2. 点名审查结论

1. **只产 candidate/不写图谱/不绕 S4/S7**：A/B **PASS**（只 candidate/ranking；无写；S4 presence；S7 消费；S10 写）。
2. **candidate_ref schema/分页/edition 可机检**：A/B **PASS**；A 缺 status/kind；B 更全；P2-3/P2-4。
3. **索引路径 S6 派生域/可重建/不写 sidecar**：A/B **PASS**（`.memoria/cache/graph/...`；edition；可重建；无 sidecar）；A 更细。
4. **召回/排序 semantic-only/无 semantic**：A/B **PASS**（graph 只 semantic；结构/ref 不进 score；no_semantic 降级）；P2-7 权重。
5. **过滤/权限/泄漏**：A/B **PASS**（单 KB/白名单/可见失败/不泄漏）；A filters 缺 kind P2-3。
6. **预算/延迟/分页**：A **P1-1 缺 max_tokens**；B 有；truncated/cursor PASS。
7. **与 S4/S5/S6 id 对齐**：A/B **PASS**（kp/cluster/run/edge；不产 presence/VM；expand 交 S4/S5）。
8. **失败/降级（索引缺失/stale/edition/无 semantic/不可用）**：A/B **PASS**（`GRAPH_*`/可见/不编造）；data_state P2-6。
9. **评估/golden/确定性/S8 消费**：A/B 有指标/golden/确定性；**P1-2 缺命令/exit/snapshot/阈值**。
10. **缓存/更新/一致性**：A/B **PASS**（edition 绑定/增量/失效/原子切换/审计；不写事实）。
11. **S10 边界**：A/B **PASS**（S10 写/S9 失效重建/不设计 KP）。

---

## 3. 最严重 3 条（给 Lead 裁决顺序）

1. **P1-1（A）budget 缺 `max_tokens`**：S9 charter/S7/S8 明确 token 预算；A 只 max_candidates/timeout，S9 不截 token ⇒ S7 二次截断/超 token 不可见；G7 A-TOKEN 无法归因。修复：加 `max_tokens`（默认 4000），S9-7 超 token `truncated=true, reason=token_budget`，机检；B 已有。
2. **P1-2（A/B）S9-10 评估不可执行**：只有指标名/golden 方向/“基线不降”，无 eval 命令、exit code、golden 路径/sha、snapshot、阈值/回归判定；S8 无法消费、无法机判。修复：冻结 golden schema/路径、eval 命令/exit、指标 JSON/sha、阈值/回归容差、2x 确定性；S8 gate 引用。
3. **P2-3（A/B）query_type/filters/status 枚举未统一**：A/B 两套枚举，S7/S8 消费不一致；`lookup` 未定义；A filters 缺 `kind`；A candidate 无 status。修复：S9 冻结唯一 query_type/filter/status schema，A/B 统一，机检。

## 4. 结论

- **两版无 P0**；A 在接口/索引/评估指标上更强；B 在 token 预算/filters/status 上更完整。
- **P1-1/P1-2 冻结前必修**；P2 包括 timeout/权重/tie-break/data_state/embedding/多 seed/新错误码。
- 未写产品代码/契约，未 commit；差异逐项列出未静默合并。

> 参考锚：S9 章程 S9-1..12；S7-8/S7-12；S8-12；S6-8/S6-11；A S9-2/S9-7/S9-10；B S9-2/S9-7/S9-10。
