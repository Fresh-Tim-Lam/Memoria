# S10 提案 A · 证据与机检清单

> 配套：`S10-kp-proposal-A.md`｜票：task-342｜日期：2026-11-04
> 用途：另一人可按本文件复核 S10 每条 KP/边/写路径/0.5 边界（file:line / 产物 / 复跑命令）。
> 独立性：**未阅读** S10 复核方草稿；不引用其结论。
> 纪律：未改产品代码/契约/用户库；未 commit。

---

## 0. 证据等级与统计

| 级 | 含义 | S10 用途 |
|---|---|---|
| A | 冻结条款/工程/代码事实 | agent 三层、E_relation_min、semantic-only、写路径现状 |
| B | 单源实测产物 | S2 probe E_sem=0（no_semantic 合法） |
| C | 单源推理 | 少量设计取舍（并入"本项目假设"） |
| 本项目假设 | 无独立证据的显式约定 | 字段/阈值/未来接口名/0.5 排期 |

**统计**：A 级锚点见 §1–§12；**本项目假设 6 条**（§14）；B 引用 S2 probe 1 份。

---

## 1. S10-1 定位/边界

| 主张 | 锚 | 等级 |
|---|---|---|
| agent 三层：L_kp 设计/L_sem 写语义需证据审计/L_view 只请求 | `S0-terms-v1.md:81-85`（S0-10） | A |
| 单一真源/禁写 sidecar | `S6-contract-v1.md:17-19`；`S0-terms-v1.md:100-107`（D-3） | A |
| S7 v1 只读/写 forbidden | `S7-agent-v1.md:16-18,47-49` | A |
| 0.5 不做 agent 写 | `S6-contract-v1.md:75-78`；`S8-metrics-v1.md:66` | A |
| 未来工具/流程 | 本提案 §1/§6 | 本项目假设 |

---

## 2. S10-2 KP 定义/字段

| 主张 | 锚 | 等级 |
|---|---|---|
| KP 是语义单元；簇不回写 KP | `S0-terms-v1.md:43-47`（S0-4） | A |
| 现有 upsert_kp 字段/range 校验 | `plan.py:346-405` | A（代码事实） |
| title/alias/summary/证据锚 schema | 本提案 §2 | 本项目假设（字段名/长度） |

---

## 3. S10-3 抽取/生成

| 主张 | 锚 | 等级 |
|---|---|---|
| 从 md+sidecar 建 KP 索引 | `ENGINEERING-PLAN.md:1219`（P1/`kp_index.py:37-73`） | A（工程） |
| 证据锚/不编造/低置信 | S0-10；S10 章程判据 | A（方向） |
| 幂等/去重/阈值 | 本提案 §3 | 本项目假设 |

---

## 4. S10-4 语义边

| 主张 | 锚 | 等级 |
|---|---|---|
| `E_relation_min = {contain(structural), contain(semantic), reference, extend}` | `S0-terms-v1.md:35-41`（R-1） | A |
| μ/β semantic-only；结构/引用不参与 | `S2-clustering-v1.md:21-29`（S2-2/3） | A |
| 现有 edge 类型仅 reference/extend；contain 禁手标 | `plan.py:892-954` | A（代码事实） |
| 语义边 schema/证据/置信 | 本提案 §4 | 本项目假设（字段/阈值） |

---

## 5. S10-5 双引用/curation

| 主张 | 锚 | 等级 |
|---|---|---|
| agent 写语义需证据锚+审计 `curated_by/at` | `S0-terms-v1.md:81-85`（S0-10） | A |
| curation/审计契约 | `S6-contract-v1.md:57-61`（S6-8）；S2-7 | A |
| 现有 approvals/backup | `approvals.py`、`backup.py`；`apply.py:249` | A（代码事实） |
| 字段/流程 | 本提案 §5 | 本项目假设 |

---

## 6. S10-6 写路径

| 主张 | 锚 | 等级 |
|---|---|---|
| 现有 plan 校验/apply | `plan.py:1239`（validate_plan）、`apply.py:249`（compile_plan） | A（代码事实） |
| 失败零写入/事务 | S6-1；S10 章程判据 | A（方向） |
| 未来 propose/plan/approval/atomic/backup/undo | 本提案 §6 | 本项目假设 |

---

## 7. S10-7 冲突/去重/合并

| 主张 | 锚 | 等级 |
|---|---|---|
| kp_id 全局唯一/同文件可更新 | `plan.py:346-389` | A（代码事实） |
| 簇身份/多归属 | `S2-clustering-v1.md:42-51` | A |
| 合并/历史保留规则 | 本提案 §7 | 本项目假设 |

---

## 8. S10-8 版本/失效

| 主张 | 锚 | 等级 |
|---|---|---|
| edition/缓存失效/回滚 | `S6-contract-v1.md:57-61`（S6-8）；S9-11/S9-12 | A |
| 旧数据保留/新 run | S2-5/S6-10 | A |
| 事件形态 | 本提案 §8 | 本项目假设 |

---

## 9. S10-9 质量/评估

| 主张 | 锚 | 等级 |
|---|---|---|
| semantic-only/不伪造 | S2-2/3/12 | A |
| S8 消费质量指标 | `S8-metrics-v1.md:73-74`（S8-12） | A |
| KP/边 P/R/golden/阈值 | 本提案 §9 | 本项目假设（阈值） |

---

## 10. S10-10 S1/S2 交互

| 主张 | 锚 | 等级 |
|---|---|---|
| S1 registry 字段/只增不删 | `S1-dimensions-v1.md:22-51`（S1-2） | A |
| S2 membership/多归属/稳定性 | `S2-clustering-v1.md:42-51`（S2-6/S2-7） | A |
| KP 目录独立/重算 | 本提案 §10 | 本项目假设 |

---

## 11. S10-11 失败/隐私

| 主张 | 锚 | 等级 |
|---|---|---|
| 不自动 apply/审计 | S0-10；S6-8 | A |
| PII/正文边界 | D-3；S0-10 | A（方向） |
| 失败码/策略 | 本提案 §11 | 本项目假设 |

---

## 12. S10-12 0.5 边界

| 主张 | 锚 | 等级 |
|---|---|---|
| 0.5 不做 agent 写/自动 semantic | `S6-contract-v1.md:75-78`（S6-12） | A |
| S7 v1 只读/写 forbidden | `S7-agent-v1.md:47-49` | A |
| 未来实施/人工确认 UI | 本提案 §12 | 本项目假设（排期） |

---

## 13. schema / 机检清单

| 检查 | 期望 |
|---|---|
| KP 字段 | kp_id/title/alias/summary/file/range/section_ref/evidence/confidence/status；有类型/默认/失败码 |
| 语义边字段 | edge_id/type/label=semantic/source/target/evidence/confidence/reason/provenance |
| 写 op 白名单 | kp.upsert/kp.alias/kp.merge/edge.upsert/edge.retract/curation；无 body/file |
| 双引用 | source/target/assertion_source；curated_by/at；approval_id |
| 失败矩阵 | 无源/歧义/低置信/冲突/超预算/PII；可见拒绝 |
| 0.5 | 无 S10 写工具/自动 apply；feature flag off |
| semantic-only | 结构/引用边不计 μ/β/语义分 |

---

## 14. 本项目假设清单（6 条）

1. KP 长度/别名/摘要上限、单 section/不重叠默认。
2. 低置信阈值 τ_kp=0.6；质量阈值 P≥0.9/R≥0.8（建议，S10a 定）。
3. 未来写路径接口名 `propose_write/plan/approval/apply`；op 白名单。
4. 合并默认保留 canonical id + alias redirect（历史保留）。
5. 失败码 `S10_*` 为未来命名空间；需与 S6 `GRAPH_*` 协调/登记。
6. S10 实施排期不在 0.5，由 roadmap 定。

---

## 15. 复跑机检（Windows PowerShell；已执行）

```powershell
$env:PYTHONIOENCODING='utf-8'
python -c "from pathlib import Path; t=Path('docs/design/multilevel-graph/S10-kp-proposal-A.md').read_text(encoding='utf-8'); print('missing S10:',[f'S10-{i}' for i in range(1,13) if f'S10-{i}' not in t]); print('semantic-only', t.count('semantic-only'), 'curated_by', t.count('curated_by'))"
python -c "from pathlib import Path; a=Path('src/memoria/services/agent/plan.py'); print('plan.py', a.exists()); b=Path('src/memoria/services/agent/apply.py'); print('apply.py', b.exists())"
python -c "from pathlib import Path; a=Path('src/memoria/services/agent/plan.py').read_text(encoding='utf-8'); print('upsert_kp', 'def _validate_upsert_kp' in a); print('upsert_edge', 'def _validate_upsert_edge' in a)"
```

**实测结果（2026-11-04）**：
- S10-1..S10-12 全部含 定义/规则·机检·反例·边界·U 映射·建议裁决·证据等级（缺失 0）。
- `plan.py`/`apply.py` 存在；`_validate_upsert_kp`/`_validate_upsert_edge` 存在（只读证据）。
- schema 覆盖 KP/边/写路径；semantic-only 在 §1/§4/§9。

---

## 16. 已知限制

1. 本场为未来 curation 设计，未实现/未跑写路径；schema/接口需 S10a/SE 校核。
2. 现有 `plan.py`/`apply.py` 能力较宽（含 body/file ops），S10 只允许子集，需显式白名单/守卫。
3. 低置信/质量阈值/golden 规模为建议，需人工标定。
4. S10 `S10_*` 错误码为未来命名空间，未登记 S6-ADDENDUM；实施前需协调。
5. S1 维度 registry 与 KP 目录不同；KP 目录形态需 S10a 定，不新增并行事实源。
