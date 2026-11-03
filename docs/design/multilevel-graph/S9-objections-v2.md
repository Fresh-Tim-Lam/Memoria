# S9 异议与 A/B 差异 v2（复核方修订版对照）

> **依据（唯一裁决依据）**：`docs/design/multilevel-graph/S9-RULINGS.md`（sha `820198b8…`，R-S9-1..R-S9-5）。
> **对象**：`S9-retrieval-proposal-A-v2.md`（主办研究，sha **`e6018a7bacb9e81fc210a720b532d1ea89acb923bece3873c5c70a0df6472bc0`**，23,470 B）与 `S9-retrieval-proposal-B-v2.md`（本复核方，sha **`50da91a44e51ca4ff7db831177052da93bd9116fa6b0f23676c97802d860d500`**，16,460 B）。
> **性质**：B-v2 以 R-S9 为依据独立修订，完成后对照 A-v2；逐项列差异、不合并。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S9-RULINGS/S0–S8。

---

## 0. R-S9 关闭矩阵

| 裁决 | A-v2 | B-v2 | 判定 |
|---|---|---|---|
| R-S9-1 budget/max_tokens/截断 | `{max_candidates,max_tokens=4000,max_latency_ms=500,cursor?}`；token 截断 | 同 | **关闭** |
| R-S9-2 可执行 eval | golden 路径/schema/sha、eval-retrieval 命令/exit、metrics JSON+sha、阈值/2×、S8 gate | 同（路径/命令名不同，P2-1） | **关闭** |
| R-S9-3 枚举/schema | query_type 4 值无 lookup；filters kind；candidate kind/status/data_state；tie-break `(score,hop,kind,canonical_id)`；弃 ref_type；500 | 同 | **关闭** |
| R-S9-4 单 seed/权重/边/embedding | 单 seed+1 跳；权重假设；结构/ref 0；embedding model/dim/license | 同 | **关闭** |
| R-S9-5 错误码/索引/一致性 | 只用 S6 GRAPH_*；cache 域；edition/原子；S10 失效 | 同 | **关闭** |

**结论**：R-S9-1..5 两版**全部关闭**；无 P0/P1；剩余 P2 为 golden 路径/命令名/阈值校准/embedding 选型（S9a/SE）。

---

## 1. A-v2 / B-v2 逐项差异（S9-1..S9-12）

| 议项 | A-v2 | B-v2 | 差异与判断 |
|---|---|---|---|
| S9-1 边界 | 只 candidate/不写/不绕 S4/S7 | 同 | 一致。 |
| S9-2 接口 | request/candidate schema；query_type 4；filters 含 kind；candidate kind/status/data_state；无 ref_type；budget 四字段；cursor edition | 同 | 一致；A 表格更细。 |
| S9-3 索引 | FTS/embedding/graph；cache；edition；可重建；embedding model/dim/license；原子/manifest | 同 | 一致。 |
| S9-4 召回 | keyword/vector/graph single seed 1 hop/hybrid；权重 0.4/0.4/0.2 假设；structural/ref 0；no_semantic | 同 | 一致。 |
| S9-5 排序 | score 归一化/tie-break `(score,hop,kind,canonical_id)`/reason/结构 0 | 同 | 一致。 |
| S9-6 过滤/权限 | 单 KB/白名单/可见失败/不泄漏 | 同 | 一致。 |
| S9-7 预算/延迟 | max_candidates/max_tokens/max_latency_ms=500；truncated/reason；cursor；冷热 | 同 | 一致。 |
| S9-8 图谱交互 | id 对齐/expand 交 S4/S5/不产 presence | 同 | 一致。 |
| S9-9 失败/降级 | 索引/stale/edition/no_semantic/不可用；S6 GRAPH_* | 同 | 一致。 |
| S9-10 评估 | golden（A 路径 `.memoria/agent/audit/graph/golden/`，候选）；eval-retrieval 命令/exit/metrics sha/2×/S8 gate | golden（B 路径 `docs/.../golden/`）；`retrieval_eval.py` 命令/exit/metrics sha/2×/S8 gate | **路径/命令名不同（P2-1）**；指标一致。 |
| S9-11 缓存/更新 | edition/增量/失效/原子切换/审计 | 同 | 一致。 |
| S9-12 S10 | S10 写/S9 失效重建 | 同 | 一致。 |

**总判断**：两版在 R-S9 核心上已收敛；A-v2 表格/schema 更细；B-v2 指标表/golden 契约更紧凑。**无新增 P0/P1**；剩余 P2 为 S9a/SE 冻结细节。

---

## 2. 仍未解决 3 点（P2；S9a/SE 冻结）

### P2-1 golden 路径与 eval 命令名 A/B 不一致
- **现状**：A-v2 golden 路径 `.memoria/agent/audit/graph/golden/S9-golden-set.json`（候选；S9a 定稿唯一），B-v2 用 `docs/design/multilevel-graph/golden/S9-golden-set.json`；A 命令 `python scripts/verify/eval-retrieval.py`，B `python scripts/benchmark/graph/retrieval_eval.py`；R-S9-2 允许 S9a 定稿唯一，但当前两版不同。
- **影响**：S8 gate/CI/golden sha 两个路径；本地/CI 两套命令；golden 双源会破坏“唯一 sha”。
- **建议**：S9a/SE 冻结唯一 golden 路径（推荐 `docs/design/multilevel-graph/golden/S9-golden-set.json`（评审可读且 edition-pinned），`artifacts/agent/verify` 只放 eval 产物）与唯一 eval 命令/参数/exit/产物路径；A/B 统一；机检路径/sha/命令。
- **证据**：R-S9-2；A S9-10；B S9-10。

### P2-2 hybrid 权重/eval 阈值/golden 规模未校准
- **现状**：两版 `0.4/0.4/0.2` 标“假设，需 golden 校准”；recall/NDCG/MRR 阈值/回归容差、golden 规模/来源（A §14）均待 S9a/SE 实测；当前无法把 soft 假设升为冻结阈值。
- **影响**：检索质量验收只能趋势/基线不降，不能固定阻断；权重不当可能偏向 keyword/vector；golden 过小过拟合。
- **建议**：S9a 建 edition-pinned golden（含 no_semantic 子集），跑权重扫描/基线，冻结权重与阈值/容差；未校准前保持假设/soft；S8 `GATE-RET` 只引用命令/exit/产物。
- **证据**：R-S9-4；A S9-4/S9-10；B S9-4/S9-10。

### P2-3 embedding 模型/维度/许可与索引成本未定
- **现状**：两版只要求记录 `model_id/dim/license`；具体模型选型、维度、许可、索引大小/构建成本、增量 vs 全量未定；embedding 关闭的 keyword-only 降级已定义。
- **影响**：索引体积/成本/合规（license）不可预估；模型升级影响 edition/index；CI 无 embedding 时行为需固定。
- **建议**：S9a/SE 冻结 model_id/dim/license、索引大小上限、增量/全量策略、embedding off 的 keyword-only 降级；索引 metadata 记录；license 审计；模型变更走 S9 修订。
- **证据**：R-S9-4/R-S9-5；A S9-3/S9-14.3；B S9-3。

---

## 3. 点名审查结论（v2）

1. **只产 candidate/不写/不绕 S4/S7**：A/B **PASS**（只 candidate/ranking；无写；S4 presence；S7 消费；S10 写）。
2. **candidate_ref schema/分页/edition 可机检**：A/B **PASS**（kind/status/data_state；无 ref_type；cursor 绑定 edition；分页稳定）。
3. **索引在 S6 派生域/可重建/不写 sidecar**：A/B **PASS**（`.memoria/cache/graph/retrieval/`；edition；可重建；原子切换；无 sidecar）。
4. **召回/排序 semantic-only/无 semantic**：A/B **PASS**（graph 单 seed+1 跳；结构/ref 贡献 0；no_semantic KP-only）；权重假设 P2-2。
5. **过滤/权限/泄漏**：A/B **PASS**（单 KB/白名单/可见失败/不泄漏）。
6. **预算/延迟/分页**：A/B **PASS**（max_candidates/max_tokens=4000/max_latency_ms=500；token 截断；cursor）。
7. **与 S4/S5/S6 id 对齐**：A/B **PASS**（kp/cluster/run/edge；不产 presence/VM/frame；expand 交 S4/S5）。
8. **失败/降级**：A/B **PASS**（索引缺失/stale/edition/no_semantic/不可用；S6 `GRAPH_*`；可见）。
9. **评估/golden/确定性/S8 消费**：A/B **PASS**（golden schema/路径/命令/exit/metrics sha/2×/S8 gate）；路径/命令 P2-1，阈值 P2-2。
10. **缓存/更新/一致性**：A/B **PASS**（edition/增量/失效/原子/审计；不写事实）。
11. **S10 边界**：A/B **PASS**（S10 写/S9 失效重建/不设计 KP）。

---

## 4. 最严重 3 条 / 结论

1. **P2-1 golden 路径/命令名不统一**：A `.memoria/agent/audit/graph/golden/` + `scripts/verify/eval-retrieval.py`；B `docs/.../golden/` + `scripts/benchmark/graph/retrieval_eval.py`；S9a/SE 冻结唯一路径/命令/exit/产物，A/B 统一，机检 sha。
2. **P2-2 权重/阈值/golden 规模未校准**：0.4/0.4/0.2 与 recall/NDCG/MRR 阈值/容差为假设；S9a 用 edition-pinned golden（含 no_semantic）校准并冻结；未校准前 soft/基线不降。
3. **P2-3 embedding model/dim/license/成本未定**：S9a/SE 冻结模型/维度/许可/索引大小/增量策略；embedding off keyword-only 降级；metadata/license 审计；模型变更走修订。

- **两版无 P0/P1**；R-S9-1..5 全部关闭；A-v2 schema/表格更细，B-v2 eval 指标表/枚举更显式。未写产品代码/契约，未 commit；差异逐项列出未静默合并。

> 参考锚：R-S9 `S9-RULINGS.md:19-40`；A-v2 S9-2/S9-7/S9-10；B-v2 同项。
