# S9 冻结记录（Freeze Record）

> **冻结对象**：`docs/design/multilevel-graph/S9-retrieval-v1.md`（12 条规范 + R-S9-1..5 + 接口/索引/评估/golden + S9a）。
> **冻结时间**：2026-11-04T00:49+08:00（Asia/Shanghai）。
> **决策**：`dec-20261104-bdfd1434`（Lead；S0–S8 已冻结）。
> **状态**：**已冻结**。0.5 检索实现/评估有唯一口径；S10（agent 设计知识点）可开。

## 1. 冻结产物与身份

| 产物 | 角色 | sha256 |
|---|---|---|
| `S9-retrieval-v1.md`（**冻结稿最终态**） | S9 唯一规范来源 | `42f364233fe1e7d08d0d0811c98a64117ebd9c0ed30a53a3d17793269a5b7dbe` |
| `S9-engineering-check.md` | SE 工程校核 + S9a（含 M-S9-1 复跑） | `904c5093…` |
| `S9-retrieval-proposal-A-v2.md` | 证据链（主办研究） | `e6018a7b…` |
| `S9-retrieval-proposal-B-v2.md` | 证据链（独立复核） | `50da91a4…` |
| `S9-objections-v2.md` | 差异/异议 | `362482f1…` |
| `S9-RULINGS.md` | Lead 裁决（R-S9-1..5） | `820198b8…` |
| `ENGINEERING-PLAN.md`（S9a） | 30 图（ER-10/DF-10/ST-10） | `39e74438…` |

**冻结轮次**：两版无 P0；第一轮 2 P1 + 1 P2（budget 缺 token、评估不可执行、枚举未统一）裁决后 v2 全关闭；SE 首轮 M-S9-1 FAIL（`id/ref` vs S7 `candidate_ref`），Lead 最小修后复跑 `M_fail=[]`，30 图 `PARSE_OK`；Lead 独立机检 PASS。

## 2. S9 冻结了什么（一句话版）

1. **边界**：只产 candidate/ranking；不写图谱/不改事实/不做 presence；S7 消费、S4 取景、S10 写入、S6 单一真源；
2. **接口**：`RetrievalRequest{kb_id,query,query_type,dimension_id?,filters,budget,expected_edition?}`；`Candidate{candidate_ref,kind,status,data_state,score,components,reason,edition,rank}`；稳定游标；
3. **budget**：`{max_candidates,max_tokens=4000,max_latency_ms=500,cursor?}`；超 token `truncated=true,reason=token_budget`；
4. **索引**：FTS/embedding/graph adjacency 回退到 S6 派生域；只写 `.memoria/cache/graph/retrieval/`；可重建、edition 绑定、v1 全量重建+原子切换、不写 sidecar；
5. **召回/排序**：`query_type∈{keyword,vector,graph,hybrid}`；graph 单 seed+semantic 1 跳；hybrid 0.4/0.4/0.2 假设；结构/引用边语义贡献=0；无 semantic KP-only+降级；score∈[0,1]/components/tie-break；
6. **过滤/权限**：kb/level/view_family/dimension/file/section/anchor/kind；越权/不存在可见失败；不泄漏；
7. **与图谱**：candidate_ref 对齐 kp/cluster/run/edge/file/anchor；frame_id 仅引用；不绕过 S4/S5；
8. **失败/降级**：索引缺失/stale/edition/无 semantic/embedding off/超时可见；只用 S6 `GRAPH_*`；新码须 ADDENDUM；
9. **评估**：golden `docs/design/multilevel-graph/golden/S9-golden-set.json`；`scripts/verify/eval-retrieval.py`；exit/指标 JSON+sha/阈值/回归/2× 确定性；S8 `GATE-RET`；
10. **一致性**：edition 变化重建；原子切换；并发锁；审计；S10 写后失效触发；
11. **S9a**：golden 唯一路径、eval 命令、产物路径、MiniLM dim384 Apache-2.0、v1 全量重建；
12. **S10 边界**：S10 写 KP/语义边；S9 不设计 KP、不自动推断语义。

## 3. 机检与证据

- SE M-S9-1..12 全 PASS（`M_fail=[]`）+ S9A PASS；PLAN 30 图 `PARSE_OK`；
- 与 S0–S8 一致性：S6 路径/错误、S7 candidate_ref/预算、S8 G6/G7、S4 presence、S5 frame、S0–S2 单一真源/维度/run — 全 PASS；
- Lead 独立机检 PASS。

## 4. 未关闭项（不阻塞冻结）

- O-S9-1..6：golden 规模/校准、hybrid 权重、embedding 记录/许可、原子切换实现、golden 隐私、S10 写后重建延迟。

## 5. 变更控制

- 加字段/指标/阈值：S9 修订 + 决策；删/改边界/分数字义/索引域：重开 S9；阈值校准写回修订（不重开）。

## 6. 下一步

- **S10（agent 设计知识点）**：最后一场；之后 0.5 实现全面推进。
