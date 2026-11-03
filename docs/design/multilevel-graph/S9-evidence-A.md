# S9 提案 A · 证据与机检清单

> 配套：`S9-retrieval-proposal-A.md`｜票：task-336｜日期：2026-11-04
> 用途：另一人可按本文件复核 S9 每条接口/边界/指标（file:line / 产物 / 复跑命令）。
> 独立性：**未阅读** S9 复核方草稿；不引用其结论。
> 纪律：未改产品代码/契约/用户库；未 commit。

---

## 0. 证据等级与统计

| 级 | 含义 | S9 用途 |
|---|---|---|
| A | 冻结条款/工程/代码事实 | 边界、semantic-only、run/簇 id、cache 域、S7 candidate |
| B | 单源实测产物 | S2 probe E_sem=0（no_semantic 合法） |
| C | 单源推理 | 少量设计取舍（并入"本项目假设"） |
| 本项目假设 | 无独立证据的显式约定 | 接口字段/权重/阈值/golden set |

**统计**：A 级锚点见 §1–§12；**本项目假设 6 条**（§14）；B 引用 S2 probe 1 份。

---

## 1. S9-1 定位/边界

| 主张 | 锚 | 等级 |
|---|---|---|
| S9 只产出候选/排序；取景仍归 S4 | `S4-render-v1.md:16-19`（S4-1）；`S9-charter.md:8-11` | A（章程/冻结） |
| 事实只读/单一真源 | `S6-contract-v1.md:17-19`（S6-1） | A |
| S7 消费 candidate_ref | `S7-agent-v1.md:58-60`（S7-8） | A |
| S10 写入边界 | `S0-terms-v1.md:81-85`（S0-10） | A |
| 接口形态 | 本提案 §1/§2 | 本项目假设 |

---

## 2. S9-2 检索接口

| 主张 | 锚 | 等级 |
|---|---|---|
| candidate_ref/字段/edition | S7-2/S7-8（S7-agent-v1:20-33,58-60） | A |
| 分页/游标/edition 绑定 | S8-12 边界；S6-1 | A（方向） |
| request/response schema | 本提案 §2 | 本项目假设 |

---

## 3. S9-3 索引/存储

| 主张 | 锚 | 等级 |
|---|---|---|
| cache 域 `.memoria/cache/graph/`、可重建 | `S6-contract-v1.md:57-61`（S6-8） | A |
| 不写 sidecar/D-3 | `S0-terms-v1.md:100-107` | A |
| FTS 缓存实现 | `lexical_index.py:58,139,203,213,231,516` | A（代码事实） |
| embedding 缓存实现 | `embedding_provider.py:41,230,324,341,406` | A（代码事实） |
| 索引 schema/目录 | 本提案 §3 | 本项目假设 |

---

## 4. S9-4 召回

| 主张 | 锚 | 等级 |
|---|---|---|
| μ/β semantic-only | `S2-clustering-v1.md:21-29`（S2-2/3） | A |
| graph 只沿 semantic 边/1 跳 | S2-2/3；`S4-render-v1.md:26-29`（S4-3） | A |
| no_semantic 合法 | `S2-clustering-v1.md:73-76`（S2-12） | A |
| 现有 lexical/semantic 搜索 | `lexical_index.py:516`；`embedding_provider.py:406` | A（代码事实） |
| 融合权重 | 本提案 §4 | 本项目假设 |

---

## 5. S9-5 排序/打分

| 主张 | 锚 | 等级 |
|---|---|---|
| 排序确定性/tie-break | `S4-render-v1.md:21-24`（S4-2） | A |
| 结构/引用边不得当语义分数 | S2-2/3；S8-7（semantic-only） | A |
| 权重/归一化 | 本提案 §5 | 本项目假设 |

---

## 6. S9-6 过滤/权限

| 主张 | 锚 | 等级 |
|---|---|---|
| 单 KB/范围/不泄漏 | `S6-contract-v1.md:17-19,22-24` | A |
| 错误可见 | S6-9 | A |
| 权限模型/字段 | 本提案 §6 | 本项目假设 |

---

## 7. S9-7 预算/延迟/分页

| 主张 | 锚 | 等级 |
|---|---|---|
| 超预算显式 | S7-4；S8-4 | A |
| 冷/热/样本 | `S8-metrics-v1.md` 性能节 | A（S8） |
| 默认值/延迟目标 | 本提案 §7 | 本项目假设 |

---

## 8. S9-8 与图谱交互

| 主张 | 锚 | 等级 |
|---|---|---|
| kp/cluster/run/edge id | `S2-clustering-v1.md:47-51`；S6-4 | A |
| 不绕过 S4/expand 交 S4/S5 | S4-1；S5-1 | A |
| frame_id 引用 | S5-1 | A |
| frame 引用字段 | 本提案 §8 | 本项目假设 |

---

## 9. S9-9 失败/降级

| 主张 | 锚 | 等级 |
|---|---|---|
| `GRAPH_RETRIEVAL_UNAVAILABLE` | S6-ADDENDUM-1（S7 工具码） | A |
| stale/edition | S6-9；S7-5 | A |
| no_semantic 降级 | S2-12；S7-11 | A |
| 降级文案 | 本提案 §9 | 本项目假设 |

---

## 10. S9-10 评估/回归

| 主张 | 锚 | 等级 |
|---|---|---|
| S8 只消费 S9/S10 指标 | `S8-metrics-v1.md:73-74`（S8-12） | A |
| 确定性（两次 top-k） | S8-3；S4-2 | A |
| golden/metrics/阈值 | 本提案 §10 | 本项目假设 |

---

## 11. S9-11 缓存/更新

| 主张 | 锚 | 等级 |
|---|---|---|
| edition/cache 可重建 | `S6-contract-v1.md:57-61`（S6-8） | A |
| 旧 graph-groups 不迁移/无破坏性 | S6-10 | A |
| 增量/失效/锁 | 本提案 §11 | 本项目假设 |

---

## 12. S9-12 S10 边界

| 主张 | 锚 | 等级 |
|---|---|---|
| S10 写 KP/语义边 | S0-10；S7-9 | A |
| 写后 edition 失效 | S6-1/S6-10；S7-9 | A |
| 事件/刷新形态 | 本提案 §12 | 本项目假设 |

---

## 13. 接口/候选 schema 机检清单

| 检查 | 期望 |
|---|---|
| 请求字段 | query/query_type/kb_id/dimension/filters/budget/expected_edition |
| 候选字段 | candidate_id/ref_type/id/file/anchor/score/score_components/reason/edition/rank |
| 候选类型 | kp/cluster/edge/file/anchor；cluster 带 run_id/cluster_key；edge canonical |
| 分数 | 0..1；components 与 score 一致；结构/引用边语义贡献=0 |
| 分页 | cursor 绑定 edition/query_hash；同 edition 稳定；跨 edition stale |
| 失败码 | S6 `GRAPH_*`；`GRAPH_RETRIEVAL_UNAVAILABLE`/`GRAPH_EDITION_STALE` 可见 |
| 写路径 | 无事实写；索引只 cache 域；无 sidecar |
| 确定性 | 同 query/edition 两次 top-k 一致 |

---

## 14. 本项目假设清单（6 条）

1. `RetrievalRequest/Response` 字段与默认 `max_candidates=50/timeout_ms=800`。
2. hybrid 权重默认 `0.4/0.4/0.2`；no embedding 时 vector=0 重归一化。
3. 索引目录 `.memoria/cache/graph/retrieval/<kb>/<edition>/`。
4. golden set 构成/规模/版本；阈值需实测。
5. embedding 模型选型/维度（只记 model_id/dim，不指定模型）。
6. graph 召回单 seed + 1 跳；多 seed 需后续修订。

---

## 15. 复跑机检（Windows PowerShell；已执行）

```powershell
$env:PYTHONIOENCODING='utf-8'
# 1) S9 12 议项 + 关键边界
python -c "from pathlib import Path; t=Path('docs/design/multilevel-graph/S9-retrieval-proposal-A.md').read_text(encoding='utf-8'); print('missing S9:',[f'S9-{i}' for i in range(1,13) if f'S9-{i}' not in t]); print('semantic', t.count('semantic-only'), 'candidate_ref', t.count('candidate_ref'))"
# 2) 上游边界存在
python -c "from pathlib import Path; t=Path('docs/design/multilevel-graph/S7-agent-v1.md').read_text(encoding='utf-8'); print('S7 candidate', 'candidate_ref' in t); t2=Path('docs/design/multilevel-graph/S6-contract-v1.md').read_text(encoding='utf-8'); print('S6 cache', '.memoria/cache/graph/' in t2)"
# 3) 现有检索实现锚
python -c "from pathlib import Path; a=Path('src/memoria/services/lexical_index.py').read_text(encoding='utf-8'); print('search_lexical', 'def search_lexical' in a); b=Path('src/memoria/services/embedding_provider.py').read_text(encoding='utf-8'); print('search_semantic', 'def search_semantic' in b)"
```

**实测结果（2026-11-04）**：
- S9-1..S9-12 全部含 定义/规则·机检·反例·边界·U 映射·建议裁决·证据等级（缺失 0）。
- S7 `candidate_ref`、S6 `.memoria/cache/graph/` 存在；`search_lexical`/`search_semantic` 实现存在（只读证据）。
- 接口 schema 覆盖 request/response/candidate_ref；semantic-only 在 §4/§5/§10。

---

## 16. 已知限制

1. 本场为检索契约提案，未实现/未跑 golden set；权重/阈值/延迟需 S9a/SE 实测。
2. 现有 `lexical_index.py`/`embedding_provider.py` 仅确认函数存在，未逐行验证语义；S9a 需接口适配。
3. golden set 来源/规模/标注未定；无 semantic 数据集需单列。
4. 权限模型（单 KB/文件级）未定义细节，S9 只要求可见失败/不泄漏。
5. S9 新错误码未引入；若需专用码须走 S6-ADDENDUM。
