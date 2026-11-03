# S2 提案 A · 证据与机检清单

> 配套：`S2-clustering-proposal-A.md`｜票：task-300｜日期：2026-11-03
> 用途：另一人可按本文件复核 S2 每条断言（file:line / 产物 / 复跑命令）。
> 独立性：**未阅读** S2 复核方草稿（S2-clustering-proposal-B / S2-objections）；不引用其结论。
> 纪律：未改产品代码/契约/schema/用户库；未 commit。

---

## 0. 证据等级与统计

| 级 | 含义 | S2 用途 |
|---|---|---|
| A | 原话/冻结契约/决策/可复跑代码事实 | 簇定义、≠连通分量、多归属、身份、D-3、R-3 |
| B | 单源实测产物 | **本场 frozen probe**（μ/β/算法结果） |
| C | 单源推理 | 少量设计取舍（已并入"本项目假设"） |
| 本项目假设 | 无独立证据的显式约定 | 权重、τ 默认值、算法 seed/tie、run 粒度 |

**统计**：A 级锚点见 §1–§13；B 级 1 份（frozen probe）；**本项目假设 9 条**（§15）。

---

## 1. S2-1 簇定义与边界

| 主张 | 锚 | 等级 |
|---|---|---|
| 簇 = 语义内聚小群（非严格连通子图/非严格连通分量） | `vision.md:30-31`（U-13/U-14） | A |
| 簇/代表子图节点的定义与身份 | `S0-terms-v1.md:43-47`（S0-4） | A |
| 现有 `graph-groups` = 并查集闭包（严格分量式） | `src/memoria/ui/static/app/js/graph-groups.js:2`（头部注释）、`:83`（`computeGraphGroups`）、`:123-126`（`nodeToGroup` 单值） | A |
| partition 作用域 `(level, view_family)` | `S0-terms-v1.md:30-33,39,101`（S0-2/R-2）；`S1-dimensions-v1.md:13-15` | A |
| 多归属规则 | `S0-terms-v1.md:65-68`（S0-7） | A |
| 单点/空/全库一簇规则 | 本提案 §1；S0-2 V1–V6 | 本项目假设（singleton 豁免/root 例外） |

---

## 2. S2-2 内聚度 μ

| 主张 | 锚 | 等级 |
|---|---|---|
| U-14 按语义关系划分小群（内聚依据） | `vision.md:31`（U-14） | A |
| 簇定义要求 μ/β（S0 未给公式） | `S0-terms-v1.md:43-47`（S0-4 只给条件名，未给度量） | A |
| 权重策略/τ_coh 默认值/密度公式 | 本提案 §2 | 本项目假设 |
| frozen 语料实测 μ 分布（B） | 本文件 §14 probe：Louvain 块 13→0.046、12→0.047、9→0.086、8→0.125、7→0.143、3→0.333、2→0.5；连通分量 25→0.0233 | B |

---

## 3. S2-3 桥 β

| 主张 | 锚 | 等级 |
|---|---|---|
| 簇允许零星桥（不能要求零跨边） | `vision.md:30`（U-13）；`S0-terms-v1.md:45`（S0-4"零星桥"） | A |
| β 公式/τ_bridge=0.15/诊断量 | 本提案 §3 | 本项目假设 |
| frozen probe：13 块 β≈0.077、12≈0.088、其余 0 | 本文件 §14 | B |

---

## 4. S2-4 划分算法

| 主张 | 锚 | 等级 |
|---|---|---|
| 禁止把 graph-groups（并查集）当簇 | `graph-groups.js:2,83`；U-13/U-14 | A |
| 分层/代表子图节点需要非严格分量划分 | `vision.md:23-24`（U-6/U-7）、`:30-31`（U-13/U-14） | A |
| Louvain/CNM/HAC 候选与 v1 选型/降级 | 本提案 §4 | 本项目假设（算法选择） |
| frozen probe：Louvain 与 CNM 结果一致；Louvain 297 块/278 singleton/最大 13；连线 296 分量；连通分量 25 块 μ 不达标而 Louvain 拆 13+12 达标 | 本文件 §14 | B |

---

## 5. S2-5 稳定性

| 主张 | 锚 | 等级 |
|---|---|---|
| 不可变 run/版本可追溯 | `ENGINEERING-PLAN.md:401-412`（CLUSTER_RUN）、`:452-455`（run_id/cluster_id/key 约束） | A（工程草案） |
| 稳定性度量记录实体 | `ENGINEERING-PLAN.md:439-447`（CLUSTER_STABILITY）、`:458` | A（工程草案） |
| 触发条件/全量重算/Jaccard 匹配规则 | 本提案 §5 | 本项目假设 |

---

## 6. S2-6 多归属

| 主张 | 锚 | 等级 |
|---|---|---|
| 成员关系≠视图出现；同族单归属、跨族/维多归属 | `S0-terms-v1.md:65-68`（S0-7）；`vision.md:38`（U-21） | A |
| membership 多对多、禁止单值 parent | `ENGINEERING-PLAN.md:111-121,211,423-430`（MEMBERSHIP 多对多） | A（工程草案） |
| 现实现 `nodeToGroup` 单值必须废弃 | `graph-groups.js:123-126` | A |
| v1 不设上限、S6 可配 | 本提案 §6 | 本项目假设 |

---

## 7. S2-7 簇身份

| 主张 | 锚 | 等级 |
|---|---|---|
| run-scoped id + cluster_key（D-2） | `S0-terms-v1.md:45,104`（S0-4/D-2）；`S0-RULINGS.md:46` | A |
| run_id 稳定编码/cluster_id local_seq/cluster_key 公式 | `ENGINEERING-PLAN.md:452-455,209-211` | A（工程草案） |
| local_seq 排序/curation stale 规则 | 本提案 §7 | 本项目假设（S6a 可细化） |

---

## 8. S2-8 嵌套与展开

| 主张 | 锚 | 等级 |
|---|---|---|
| 层次划分/最小粒度 KP | `S0-terms-v1.md:30-33`（S0-2）；`vision.md:43-44`（U-28） | A |
| 展开/下钻是 H 导航（无 hop） | `S1-dimensions-v1.md:57-65`（S1-4 H） | A |
| H 派生边映射谓词/data_edge_ids（允许空集） | `S1-dimensions-v1.md:59-66`（R-S1-11） | A |
| refinement/degenerate/root_exempt | 本提案 §8 | 本项目假设 |

---

## 9. S2-9 簇与边

| 主张 | 锚 | 等级 |
|---|---|---|
| 聚合/折叠边必须带 `data_edge_ids`，expand ⊆ DataSource | `S0-terms-v1.md:56-61,102`（S0-6/R-3）；`S1-dimensions-v1.md:59-66` | A |
| CLUSTER_EDGE internal/bridge + data_edge_ids | `ENGINEERING-PLAN.md:431-438,457` | A（工程草案） |
| 桥呈现归 S4 | `S2-charter.md:35`（S2-9 必须回答） | A |

---

## 10. S2-10 簇与维度

| 主张 | 锚 | 等级 |
|---|---|---|
| H 产生层次划分；A 只扩可见集合、不产生簇 | `S1-dimensions-v1.md:13-15,57-66`（H/A） | A |
| 簇属于 H view_family、A 不改 membership | 本提案 §10 | 本项目假设（机检实现） |
| 多归属不写产品 sidecar | `S0-terms-v1.md:105`（D-3）；`S0-RULINGS.md:47` | A |

---

## 11. S2-11 持久化缓存

| 主张 | 锚 | 等级 |
|---|---|---|
| 簇是派生缓存，不写产品 sidecar/新段 | `S0-terms-v1.md:105`（D-3）；`ENGINEERING-PLAN.md:458-459`；`kg-ontology-v0.md:162-177`（`.memoria/build` 可再生） | A |
| 缓存可重建/旧 run 只读/原子写 | 本提案 §11；ER 草案 | 本项目假设（S6 定路径） |

---

## 12. S2-12 度量与验收

| 主张 | 锚 | 等级 |
|---|---|---|
| 规模不是问题、关键后端检索 | `vision.md:71`（U-32） | A |
| CLUSTER_STABILITY 实体/指标记录 | `ENGINEERING-PLAN.md:439-447` | A（工程草案） |
| 指标清单/G6 快照/数值门禁归 S8 | 本提案 §12 | 本项目假设（阈值） |

---

## 13. S2-13 与 agent

| 主张 | 锚 | 等级 |
|---|---|---|
| agent 只请求确定性取景服务、不改渲染状态 | `S0-terms-v1.md:81-85`（S0-10）；`S1-dimensions-v1.md`（S1-14） | A |
| agent 只读取景（P9 只读） | `ENGINEERING-PLAN.md:301-303,469-473` | A |
| 重聚类服务/审计/只读缓存 | 本提案 §13 | 本项目假设（服务签名） |

---

## 14. frozen probe（B 级实测；可复跑）

**目的**：验证 μ/β 可计算、Louvain 与 CNM 的确定性/差异、连通分量为何不能当簇。

**输入**：`artifacts/agent/verify/debate/kg-retrieval/round2/frozen/数字通信原理`（357 KP、62 边，S0 B 级已知语料）。**方法**：`collect_graph_data` 取 DataSource；构图，边权 `semantic=1.0 / contain(structural)=0.5 / extend=0.3 / reference=0.2`；分别跑 `networkx.community.louvain_communities(weight, seed=42)`、`greedy_modularity_communities(weight)`、`connected_components`。

**结果（2026-11-03 本机）**：

| 方法 | 块数 | singleton | 最大块 | 关键 μ/β |
|---|---|---|---|---|
| Louvain（seed=42） | 297 | 278 | 13 | 13: μ0.0462/β0.0769；12: μ0.047/β0.0882；9: μ0.0861/β0；8: μ0.125；7: μ0.143；3: μ0.333；2: μ0.5 |
| Greedy modularity | 297 | 278 | 13 | 同 Louvain 的块分布（该语料上一致） |
| Label propagation | 304 | 278 | 9 | 9: μ0.0861；4 块出现 β0.58/0.27（桥多） |
| 严格连通分量（graph-groups 式） | 296 | 278 | **25** | 25 块 μ≈0.0233 < τ0.04 ⇒ 不应作为一个簇 |

**结论**：
1. μ/β 可复算，且能区分"大而松"的连通分量（25 块 μ 0.0233）与拆分后的内聚块（13+12 块 μ 0.046/0.047）；
2. Louvain/CNM 在该语料上一致（支持"v1 主选 Louvain、CNM 降级"）；
3. 大量 singleton 是稀疏语料的现实，S2 要求"允许 singleton、不伪造聚合"，不要求簇数越多越好；
4. 阈值 τ_coh=0.04/τ_bridge=0.15 由该 probe 得出，**live 语料须 S8 复标定**（S2 不把数值当永久契约）。

**复跑片段（非产品代码）**：
```python
# 依赖：networkx（3.6.1）；读取 frozen 语料 → collect_graph_data
import sys, networkx as nx
from memoria.graph.collector import collect_graph_data
g = collect_graph_data(kb_path); G = nx.Graph()
for e in g["edges"]:
    a, b = e["source_id"], e["targets"][0]
    w = 1.0 if e.get("contain_kind") == "semantic" else {"contain": 0.5, "extend": 0.3, "reference": 0.2}.get(e["type"], 0.1)
    G.add_edge(a, b, weight=w)
# 重复运行验证确定性
p1 = nx.community.louvain_communities(G, weight="weight", seed=42)
p2 = nx.community.louvain_communities(G, weight="weight", seed=42)
assert {frozenset(c) for c in p1} == {frozenset(c) for c in p2}
```

---

## 15. 本项目假设清单（9 条，评审可逐条推翻）

1. 权重策略：semantic=1.0 / structural contain=0.5 / extend=0.3 / reference=0.2（"关系证据强度"，不等于语义真值）。
2. τ_coh=0.04、τ_bridge=0.15（由 frozen probe 得出；S8 复标定，允许配置）。
3. 单点块允许且 μ 豁免；全库一簇仅 L0 root（root_exempt=true）。
4. v1 主选 deterministic seeded Louvain（seed、节点序、tie-break 固定），CNM 降级，HAC 备选。
5. 失败路径 `degraded`（singleton partitions + warning），禁止并查集伪装簇。
6. cluster_run 粒度：每 view_family 一个 run 含所有层（嵌套父子同 run）；ER-03 的 `CLUSTER_RUN.level_id` 建议 S6a 改 `level_chain_id`/nullable。
7. run_id/cluster_local_seq/cluster_key 的 canonical 序列化与排序规则（S6a 冻结细节）。
8. v1 不设 membership 上限（`max_memberships_per_kp=null`，S6 可配）。
9. 稳定性门禁（Jaccard≥0.8 等）不在 S2 冻结，S8 定；S2 只定测量与记录。

---

## 16. 代码锚复核（本机可复跑）

| # | file:line | 断言 | 实测 |
|---|---|---|---|
| 1 | `src/memoria/ui/static/app/js/graph-groups.js:2` | 并查集闭包（反例） | OK |
| 2 | `graph-groups.js:83` | `computeGraphGroups` | OK |
| 3 | `graph-groups.js:123-126` | `nodeToGroup` 单值 | OK |
| 4 | `src/memoria/ui/static/app/js/graph-engine.js:167-181` | 全量 payload | OK |
| 5 | `src/memoria/ui/static/app/js/app.js:1845` | get_graph_data 单入口 | OK |
| 6 | `src/memoria/graph/collector.py:46-99` | DataSource | OK |
| 7 | `src/memoria/graph/edge_derivation.py:787-793` | canonical edge id | OK |

---

## 17. 覆盖矩阵（S2 相关）

| 侧 | 项 | 落点 |
|---|---|---|
| U | U-6/U-13/U-14/U-15/U-17/U-21/U-22/U-31 | 提案 §14.1（逐项映射） |
| S0 | S0-2/S0-4/S0-6(R-3)/S0-7/D-2/D-3 | 提案 §14.2 |
| S1 | H/A 分工、view_family、R-S1-11 | 提案 §14.2 |
| 工程 | ER-03（CLUSTER_RUN/CLUSTER/MEMBERSHIP/CLUSTER_EDGE/CLUSTER_STABILITY） | `ENGINEERING-PLAN.md:385-462` |

---

## 18. 已知限制

1. μ 的加权密度对语料规模/稀疏度敏感；τ_coh 默认值只由 frozen probe 标定，live 必须复标定（S8）。
2. probe 使用 networkx 实现；产品若不引入该依赖，需按 §4 伪代码自实现（S6/S9 决定），算法行为可能不同但确定性要求不变。
3. run 粒度/ER 字段（`CLUSTER_RUN.level_id`）与 ER-03 草案有差异，需 S6a 联签；本提案只给需求。
4. 单点块/root_exempt/degenerate_refinement 的 UI 呈现归 S3/S4，S2 只定义语义与标记。
5. G6 快照的"语义统计不得含 structural cluster"依赖 G6 侧落实，S2 提供 `source=derived_cluster` 标记。
