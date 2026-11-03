# S9 后端检索 · 冻结稿 v1（候选）

> **依据**：`multilevel-graph-vision.md`；`S9-charter.md`；`S9-RULINGS.md`。
> **上游冻结**：S0–S8 九份 v1 + `S3-ADDENDUM-1`、`S6-ADDENDUM-1` —— 不得违反。
> **输入**：A-v2（`e6018a7b…`）、B-v2（`50da91a4…`）、异议-v2（`362482f1…`）。
> **状态**：冻结候选 v1，待 SE 工程校核（task-338）与 Lead 独立机检后冻结；冻结前不写产品代码。

---

## 0. 一句话口径

S9 只产出 **candidate/ranking**：请求带 `kb_id/dimension/filters/budget{max_candidates,max_tokens=4000,max_latency_ms=500}/expected_edition`；候选带 `kind/status/score/components/reason/edition/rank`；索引只写 `.memoria/cache/graph/retrieval/`、可重建、edition 绑定；召回/排序 **semantic-only**；评估用 edition-pinned golden + 可执行命令，S8 gate 消费。

## 1. 规范性条款（S9-1..S9-12）

### S9-1 定位与边界
- S9 只产 candidate/ranking；**不写图谱/不改事实/不做 presence**；S7 消费、S4 取景、S10 写入、S6 单一真源；不绕过 S4/S7；不写 sidecar。
- **机检**：无写路径；只读；边界。

### S9-2 接口
- `RetrievalRequest{kb_id, query, query_type, dimension_id?, filters, budget, expected_edition?}`；
  `filters = {kb_id?, level_id?, view_family_id?, dimension_id?, file?, section?, anchor?, kind?}`；
  `budget = {max_candidates, max_tokens=4000, max_latency_ms=500, cursor?}`。
- `Candidate{kind ∈ {kp,cluster,edge,file,anchor}, status ∈ {ok,degraded,unknown}, data_state, id/ref, score∈[0,1], components, reason, edition, rank}`；稳定游标（绑定 edition/query_hash）。
- **`request.kb_id` 唯一权威**；`filters.kb_id` 若存在必须相等，否则 `GRAPH_TOOL_INPUT_INVALID`；弃 `ref_type`（统一 `kind`）。
- **机检**：schema 白名单；游标稳定；跨 edition `GRAPH_EDITION_STALE`。

### S9-3 索引/存储
- FTS/embedding/graph adjacency 全部**派生、可重建、edition 绑定**；只写 `.memoria/cache/graph/retrieval/`；不写 sidecar；索引 metadata 含 `model_id/dim/license`、`edition`、`rebuildable=true`。
- v1 edition 变化 ⇒ **全量重建 + 原子切换**（增量 future）；并发锁；审计。
- **机检**：路径；可重建；edition；原子切换；无 sidecar 写入。

### S9-4 召回
- `query_type ∈ {keyword, vector, graph, hybrid}`；graph 仅**单 seed + semantic 1 跳**（多 seed future）；hybrid 权重 `0.4/0.4/0.2` 为**假设，需 golden 校准**；结构/引用/extend 边语义贡献=0；无 semantic ⇒ KP-only + 可见降级；embedding off ⇒ keyword-only。
- **机检**：四值；单 seed；贡献 0；无 semantic 降级。

### S9-5 排序/打分
- score∈[0,1] + components；来源/归一化/权重显式；`tie-break=(score desc, hop asc, kind, canonical_id)`；每候选可解释 reason；结构/引用边语义贡献=0。
- **机检**：score 范围；components；tie-break；可解释。

### S9-6 过滤/权限/范围
- kb/level/view_family/dimension/file/section/anchor/kind 白名单；越权/不存在可见失败；不泄漏隐藏内容/计数。
- **机检**：过滤生效；越权错误；无泄漏。

### S9-7 预算/延迟/分页/截断
- `max_candidates/max_tokens/max_latency_ms` 显式；超 token ⇒ `truncated=true, truncation_reason="token_budget"`；超候选/超时同理；游标绑定 edition/query_hash；冷/热、embedding on/off 分列。
- **机检**：截断可见；游标稳定；环境分列。

### S9-8 与图谱交互
- candidate id 对齐 `kp/cluster(run_id/cluster_key)/edge/file/anchor`；`frame_id` 仅引用（S5 派生）；expand 交 S4/S5；不绕过 S4。
- **机检**：id 对齐；frame_id 只引用；无绕过。

### S9-9 失败/降级
- 索引缺失/stale/edition 不匹配/无 semantic/embedding 关闭/超时 ⇒ 可见错误/降级；`GRAPH_RETRIEVAL_UNAVAILABLE`/`GRAPH_EDITION_STALE`；不编造。
- **机检**：失败可见；错误码；无编造。

### S9-10 评估/回归（可执行）
- **golden**：`docs/design/multilevel-graph/golden/S9-golden-set.json`（唯一路径，edition-pinned，含 no_semantic 子集；schema/sha 冻结）；
- **命令**：`python scripts/verify/eval-retrieval.py --kb <kb> --golden <path> --out <metrics.json>`；exit 0 成功/非 0 失败；
- **指标**：recall@k / NDCG@k / MRR / coverage / no_semantic / sem_purity / latency；输出 JSON + sha；**2× 确定性**；
- **阈值**：初始 provisional（recall@5≥0.80、NDCG@10≥0.70、MRR≥0.70、coverage≥0.90、sem_purity=1.0），发布前需基线校准；相对回归容差 ±5%；未校准前 soft；
- S8 `GATE-RET` 引用命令/exit/产物 sha。
- **机检**：golden 存在 sha；eval exit；metrics sha；2× 一致。

### S9-11 缓存/更新/一致性
- edition 变化新索引；v1 全量重建 + 原子切换；并发锁；不写事实源；审计；S10 写入后 edition 失效触发重建。
- **机检**：重建；原子切换；审计；无事实写入。

### S9-12 与 S10 边界
- S10 写 KP/语义边；写后 edition 变化触发 S9 失效/重建；S9 不设计 KP、不自动推断语义；刷新触发方 S10。
- **机检**：边界；无 KP 设计；触发关系。

## 2. 跨议题裁决（R-S9-1..R-S9-5）

- **R-S9-1**：budget 含 `max_tokens=4000`；超 token 显式 `token_budget`。
- **R-S9-2**：可执行 eval（golden/命令/exit/metrics sha/阈值/2×）；S8 gate 引用。
- **R-S9-3**：枚举/schema 统一（query_type 四值、filters 含 kind、kind/status/data_state、tie-break、max_latency_ms=500、弃 ref_type）。
- **R-S9-4**：单 seed+1 跳；权重假设；语义贡献 0；embedding metadata；无 semantic 降级。
- **R-S9-5**：只用 S6 `GRAPH_*`；索引 cache 域/可重建/edition/原子切换；S10 失效。

## 3. S9a 定稿（候选，SE 校核）

- golden 唯一路径 `docs/design/multilevel-graph/golden/S9-golden-set.json`；eval 命令 `scripts/verify/eval-retrieval.py`；产物 `artifacts/agent/verify/graph/retrieval/<run>.json`；GATE-RET。
- embedding 默认沿用构建内置 `paraphrase-multilingual-MiniLM-L12-v2`（dim 384，Apache-2.0），metadata 记录；模型变更走 S9 修订。
- 索引 v1 全量重建（edition 变化）+ 原子切换；增量 future。
- `filters.kb_id` 校验规则见 S9-2；hybrid 默认，无 semantic 自动 keyword。

## 4. 冻结前机检（SE + Lead）

M-S9-1 边界；M-S9-2 schema/游标/edition；M-S9-3 索引路径/可重建/原子切换；M-S9-4 召回/semantic-only；M-S9-5 排序/tie-break；M-S9-6 过滤/权限；M-S9-7 预算/截断；M-S9-8 id 对齐；M-S9-9 失败降级；M-S9-10 eval/golden/2×；M-S9-11 一致性；M-S9-12 S10 边界 + 工程图 `PARSE_OK`。

## 5. 冻结后

- S10（agent 设计知识点）；0.5 实现按 S6a + S8 DoD + S9 检索契约；golden/阈值在实现前校准。

## 6. 变更控制

- 加字段/指标/阈值：S9 修订 + 决策；删/改边界/分数字义/索引域：重开 S9；阈值校准写回修订（不重开）。
