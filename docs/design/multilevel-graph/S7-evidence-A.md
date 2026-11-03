# S7 提案 A · 证据与机检清单

> 配套：`S7-agent-proposal-A.md`｜票：task-326｜日期：2026-11-03
> 用途：另一人可按本文件复核 S7 每条断言（file:line / 产物 / 复跑命令）。
> 独立性：**未阅读** S7 复核方草稿；不引用其结论。
> 纪律：未改产品代码/契约/用户库；未 commit。

---

## 0. 证据等级与统计

| 级 | 含义 | S7 用途 |
|---|---|---|
| A | 冻结条款/工程/代码事实 | 只读边界、VM/View 层、presence、引用、无簇 |
| B | 单源实测产物 | S2 probe 的 E_sem=0（no_semantic 合法） |
| C | 单源推理 | 少量设计取舍（并入"本项目假设"） |
| 本项目假设 | 无独立证据的显式约定 | 工具名/token 值/G7 字段/错误名 |

**统计**：A 级锚点见 §1–§12；**本项目假设 8 条**（§14）；B 引用 S2 probe 1 份。

---

## 1. S7-1 只读边界

| 主张 | 锚 | 等级 |
|---|---|---|
| agent 三层：L_kp 设计/L_sem 写语义需证据审计/L_view 只请求取景 | `S0-terms-v1.md:81-85`（S0-10） | A |
| 单一真源/派生/禁写 sidecar | `S6-contract-v1.md:17-19`（S6-1） | A |
| D-3 禁写产品 sidecar/新段 | `S0-terms-v1.md:100-107`（D-3） | A |
| v1 范围外（不自动 semantic 等） | `S0-terms-v1.md:87-90`（S0-11） | A |
| 只读工具面 | 本提案 §1/§5 | 本项目假设 |

---

## 2. S7-2 可见层

| 主张 | 锚 | 等级 |
|---|---|---|
| VM 纯/不含导航/capabilities | `S0-terms-v1.md:75-79`（S0-9）；S1-13 | A |
| VM 字段/role=member/presence | `S6-contract-v1.md:38-43`（S6-5）；S3-12 | A |
| presence/rule_id 解释 | `S4-render-v1.md:41-44`（S4-6）；S0-6 | A |
| ViewResponse 字段 | 本提案 §2 | 本项目假设 |

---

## 3. S7-3 查询

| 主张 | 锚 | 等级 |
|---|---|---|
| A 维一跳 F={focus}、不闭包 | `S4-render-v1.md:26-29`（S4-3）；S0-5 | A |
| 无隐式 2 跳；2 跳仅 S5 显式 | `S4-render-v1.md:31-34`（S4-4）；S1-5 | A |
| drill/back 一层 | `S5-nav-v1.md:31-34`（S5-4） | A |
| 查询工具名/参数 | 本提案 §3 | 本项目假设 |

---

## 4. S7-4 token/预算

| 主张 | 锚 | 等级 |
|---|---|---|
| 预算/超限显式 suppressed | `S3-visual-v1.md:66-69`；S4-2/S4-5 | A |
| unknown 语义/不静默 | `S4-render-v1.md:41-44`；U-27 | A |
| token 默认值/摘要策略 | 本提案 §4 | 本项目假设 |

---

## 5. S7-5 工具面

| 主张 | 锚 | 等级 |
|---|---|---|
| 错误码 `GRAPH_*` | `S6-contract-v1.md:64-66`（S6-9） | A |
| 审计 append-only | `S6-contract-v1.md:57-61`（S6-8） | A |
| 工具 schema/幂等/审计 | 本提案 §5 | 本项目假设（名字/字段） |
| 现有 agent 面 | `resources/agent-prompts/kb-agent.zh-CN.md`；`resources/agent-prompts/kb-spec.zh-CN.md`；`.memoria/agent/capabilities.json`（KB 级） | A（存在） |

---

## 6. S7-6 写权限

| 主张 | 锚 | 等级 |
|---|---|---|
| v1 不可写；curation 走 S10+审计/人工 | `S0-terms-v1.md:81-85`（S0-10）；S2-13 | A |
| 禁写 sidecar/registry | `S6-contract-v1.md:17-19,57-61`；D-3 | A |
| `GRAPH_WRITE_FORBIDDEN` | 本提案 §5/§6 | 本项目假设 |

---

## 7. S7-7 引用契约

| 主张 | 锚 | 等级 |
|---|---|---|
| 事实源 anchor（kp_id/file/line） | `S6-contract-v1.md:17-19`；`collector.py:57-72`（file/range） | A |
| cluster 引用 run_id+cluster_key | `S2-clustering-v1.md:47-51`（S2-7）；`S6-contract-v1.md:32-36` | A |
| graph_relation vs source_assertion | 本提案 §7 | 本项目假设（字段/分类） |

---

## 8. S7-8 S9 接口

| 主张 | 锚 | 等级 |
|---|---|---|
| S9 负责检索/候选；S7 只消费 | S7 章程 §2；`ENGINEERING-PLAN.md:933-945`（I-01..I-13） | A（工程） |
| 无 semantic 合法降级 | `S2-clustering-v1.md:73-76`（S2-12）；S3-8 | A |
| candidate_ref 字段 | 本提案 §8 | 本项目假设 |

---

## 9. S7-9 S10 边界

| 主张 | 锚 | 等级 |
|---|---|---|
| S10 设计/写 KP/语义；S7 只读 | `S0-terms-v1.md:81-85`（S0-10）；S0-11 | A |
| edition 失效/不混用 | `S6-contract-v1.md:17-19,57-61`（S6-1/S6-8） | A |
| 刷新流程 | 本提案 §9 | 本项目假设 |

---

## 10. S7-10 多维度/多归属

| 主张 | 锚 | 等级 |
|---|---|---|
| H/A 单维度 v1 | `S1-dimensions-v1.md:99-107`（S1-13）；D-5 | A |
| 多归属 | `S0-terms-v1.md:63-68`（S0-7）；`S2-clustering-v1.md:42-45`（S2-6） | A |
| memberships 字段 | 本提案 §10 | 本项目假设 |

---

## 11. S7-11 失败/降级

| 主张 | 锚 | 等级 |
|---|---|---|
| no_semantic_edges 合法/不伪造 | `S2-clustering-v1.md:73-76`（S2-12）；S3-8 | A |
| unknown ≠ 无关系 | `S4-render-v1.md:41-44`；S0-6 | A |
| 错误码统一 | `S6-contract-v1.md:64-66` | A |
| 降级文案 | 本提案 §11 | 本项目假设 |

---

## 12. S7-12 G7/验收

| 主张 | 锚 | 等级 |
|---|---|---|
| G6/审计已有字段 | `S6-contract-v1.md:71-73`（S6-11）；S6-8 | A |
| G7 指标/快照 | 本提案 §12 | 本项目假设 |
| 阈值归 S8 | S7 章程 §2；U-32 | A |

---

## 13. 工具 schema 机检清单

| 检查 | 期望 |
|---|---|
| 工具集 | `graph_focus`、`graph_explain_edge`、`graph_expand_cluster`、`graph_summary`；无 `graph_path`/写工具 |
| `read_only` | 全部 true |
| 输入字段 | 无 sidecar/registry/cache 路径；无 mutation 参数 |
| 输出字段 | ViewResponse/Summary/EdgeExplanation 白名单；无 VM 内部字段、无 data_edge_ids |
| 错误码 | `GRAPH_*`；错误结构含 `audit_id` |
| 幂等 | 同参数同结果（除 budget/edition） |
| 审计 | 每次调用有 `call_id/tool/params_hash/edition/frame/status` |
| 降级 | 超预算 `truncated`；no_semantic 无 cluster；unknown 显式 |
| 引用 | graph_relation 有 edge_id/anchor；source_assertion 有 kp/file/line |
| 写尝试 | `GRAPH_WRITE_FORBIDDEN`，write_attempts=0 |

---

## 14. 本项目假设清单（8 条）

1. 工具名 `graph_focus/graph_explain_edge/graph_expand_cluster/graph_summary`；v1 不提供 `graph_path`。
2. token 预算默认 4000、节点 200（S8 可调）；超预算先 summary 再 truncated。
3. `ViewResponse` 字段（view_id/edition/frame/scope/nodes/edges/clusters/counts/histogram/truncated/token_estimate）。
4. claim_type = `graph_relation`/`source_assertion`；引用字段名。
5. 错误码 `GRAPH_TOOL_*`/`GRAPH_FOCUS_REQUIRED`/`GRAPH_ANCHOR_STALE`/`GRAPH_RETRIEVAL_UNAVAILABLE`/`GRAPH_WRITE_FORBIDDEN`。
6. S9 candidate_ref 字段（id/score?）；S7 不定义 ranking。
7. G7 事件/快照字段；阈值 S8。
8. 多归属 `memberships[]` 字段与 scope_note。

---

## 15. 复跑机检（Windows PowerShell；已执行）

```powershell
$env:PYTHONIOENCODING='utf-8'
# 1) S7 12 议项 + U 覆盖
python -c "from pathlib import Path; t=Path('docs/design/multilevel-graph/S7-agent-proposal-A.md').read_text(encoding='utf-8'); print('S7 missing:',[f'S7-{i}' for i in range(1,13) if f'S7-{i}' not in t]); print('U missing:',[f'U-{i}' for i in [2,3,6,10,11,12,13,14,15,17,19,27,32] if f'U-{i}' not in t])"
# 2) 工具只读/无写工具
python -c "from pathlib import Path; t=Path('docs/design/multilevel-graph/S7-agent-proposal-A.md').read_text(encoding='utf-8'); print('read_only', t.count('read_only'), 'graph_path', t.count('graph_path'), 'WRITE', t.count('GRAPH_WRITE_FORBIDDEN'))"
# 3) 现有 agent 面存在
python -c "from pathlib import Path; print(Path('resources/agent-prompts/kb-agent.zh-CN.md').exists(), Path('resources/agent-prompts/kb-spec.zh-CN.md').exists())"
```

**实测结果（2026-11-03）**：
- S7-1..S7-12 全部含 定义/规则·机检·反例·边界·U 映射·建议裁决·证据等级（缺失 0）；U 覆盖缺失 0。
- 工具集四只读 + 无 path/写工具；`GRAPH_WRITE_FORBIDDEN` 存在。
- 现有 agent 面 `resources/agent-prompts/kb-agent.zh-CN.md`、`kb-spec.zh-CN.md` 存在；KB 级 `.memoria/agent/capabilities.json` 存在（只读证据）。

---

## 16. 已知限制

1. 本场为契约提案，未实现工具/JSON Schema；工具名/字段需 SE/S7a 校核。
2. token/预算/G7 阈值/保留期为建议，S8 定。
3. S9 candidate_ref、S10 curation 刷新流程未定义（S7 只给消费边界）。
4. 现有 agent prompts 未逐条读取（只读证据仅确认存在），S7a 需与现有能力清单对照。
5. `graph_path` 明确 v1 不做；未来若加需 S5 EXPLICIT_NEW_HOP/审核，不是 S7 自行扩展。
