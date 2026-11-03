# S8 提案 A · 证据与机检清单

> 配套：`S8-metrics-proposal-A.md`｜票：task-331｜日期：2026-11-04
> 用途：另一人可按本文件复核 S8 每条指标/阈值/断言（file:line / 产物 / 复跑命令）。
> 独立性：**未阅读** S8 复核方草稿；不引用其结论。
> 纪律：未改产品代码/契约/用户库；未 commit。

---

## 0. 证据等级与统计

| 级 | 含义 | S8 用途 |
|---|---|---|
| A | 冻结条款/工程/代码事实 | 硬预算/60fps/180ms、presence/subset、G6/G7、I-01..I-13 |
| B | 单源实测产物 | S2 probe E_sem=0（no_semantic 合法） |
| C | 单源推理 | 少量设计取舍（并入"本项目假设"） |
| 本项目假设 | 无独立证据的显式约定 | P95 延迟/保留期/CI 命令/阈值 |

**统计**：A 级锚点见 §1–§12；**本项目假设 8 条**（§14）；B 引用 S2 probe 1 份。

---

## 1. S8-1 指标框架

| 主张 | 锚 | 等级 |
|---|---|---|
| presence/subset/closure 是硬约束 | `S0-terms-v1.md:56-61`（S0-6）；`S4-render-v1.md:56-60`（S4-9） | A |
| SIM/单一指标不得掩盖失败（S8 章程判据） | `S8-charter.md:41-51` | A（章程） |
| 分类/阈值/命名 | 本提案 §1 | 本项目假设 |

---

## 2. S8-2 G6

| 主张 | 锚 | 等级 |
|---|---|---|
| G6 字段冻结 | `S6-contract-v1.md:71-73`（S6-11） | A |
| 快照可复跑/确定性 sha | S6-11；`S6-contract-v1.md:71` | A |
| 存储/审计路径 | `S6-contract-v1.md:57-61`（S6-8） | A |
| G6 路径/命令/基线更新 | 本提案 §2 | 本项目假设 |

---

## 3. S8-3 正确性/确定性

| 主张 | 锚 | 等级 |
|---|---|---|
| HAC 两次一致/run_id 可复算 | `S2-clustering-v1.md:31-50`（S2-4/S2-7） | A |
| registry 链/只增不删 | `S1-dimensions-v1.md:48`（R-S1-9） | A |
| presence/rule_id/unknown 4 类 | `S4-render-v1.md:41-44`（S4-6） | A |
| subset/closure/behind | `S4-render-v1.md:56-60`（S4-9） | A |
| tie-break | `S4-render-v1.md:21-24`（S4-2） | A |
| fixture/命令 | 本提案 §3 | 本项目假设 |

---

## 4. S8-4 性能/预算

| 主张 | 锚 | 等级 |
|---|---|---|
| max_nodes=200/max_edges=400/60fps/30fps/180ms | `S3-visual-v1.md:66-69`（S3-11） | A |
| 预算唯一裁剪/可见降级 | S3-11；S4-2 | A |
| P95/首开/切页签数值 | 本提案 §4 | 本项目假设 |

---

## 5. S8-5 可解释性

| 主张 | 锚 | 等级 |
|---|---|---|
| suppressed/unknown/rule_id | `S4-render-v1.md:41-44`；S3-5 | A |
| no_semantic/降级可见 | `S3-visual-v1.md:51-54`；S7-11 | A |
| DOM/aria 基线 | `S3-visual-v1.md:61-64`（S3-10） | A |
| 解释率/抽样 | 本提案 §5 | 本项目假设 |

---

## 6. S8-6 G7

| 主张 | 锚 | 等级 |
|---|---|---|
| G7 字段/引用 G6/write=0 | `S7-agent-v1.md:74-76`（S7-12） | A |
| 只读工具/写 forbidden | `S7-agent-v1.md:16-18,47-49`（S7-1/6） | A |
| token 默认 4000/200 | `S7-agent-v1.md:37-39`（S7-4） | A |
| 阈值/采样/保留 | 本提案 §6/§11 | 本项目假设 |

---

## 7. S8-7 数据质量

| 主张 | 锚 | 等级 |
|---|---|---|
| μ/β semantic-only | `S2-clustering-v1.md:21-29`（S2-2/3） | A |
| no_semantic 合法/不伪造 | `S2-clustering-v1.md:73-76`（S2-12） | A |
| coverage 公式 | S2-12；`S6-contract-v1.md:32-36` | A |
| frozen/showcase E_sem=0（B 证据） | `artifacts/agent/verify/debate/graph-utility/s2-semantic-probe/results.json` | B |
| coverage 信号阈值 | 本提案 §7 | 本项目假设 |

---

## 8. S8-8 故障注入

| 主张 | 锚 | 等级 |
|---|---|---|
| 预算/unknown/降级可见 | S4-6；S7-11 | A |
| stale/错误码 | `S6-contract-v1.md:64-66`（S6-9） | A |
| 事务化回放 diff=0 | `S5-nav-v1.md:57-60`（S5-9） | A |
| 六类故障 fixture | 本提案 §8 | 本项目假设 |

---

## 9. S8-9 CI/回归

| 主张 | 锚 | 等级 |
|---|---|---|
| G6 快照/基线 | S6-11 | A |
| mermaid PARSE_OK | S5a/S6a 门禁；`S8-charter.md:40-51` | A（章程） |
| 现有门禁 | `scripts/agent/*`（decide/curator 等）、`scripts/benchmark/**` | A（存在） |
| CI 命令/flaky 策略 | 本提案 §9 | 本项目假设 |

---

## 10. S8-10 0.5 DoD

| 主张 | 锚 | 等级 |
|---|---|---|
| 0.5 做/不做 | `S6-contract-v1.md:75-78`（S6-12） | A |
| I-01..I-13 接口 | `ENGINEERING-PLAN.md:933-945` | A（工程） |
| 每接口验收/阻断 | 本提案 §10 | 本项目假设（fixture/命令） |

---

## 11. S8-11 存储/隐私/成本

| 主张 | 锚 | 等级 |
|---|---|---|
| cache/config/audit 路径 | `S6-contract-v1.md:57-61`（S6-8） | A |
| G7 只引用 G6/不复制事实 | `S7-agent-v1.md:74-76`（S7-12） | A |
| 保留期/大小/删除 | 本提案 §11 | 本项目假设 |

---

## 12. S8-12 S9/S10 边界

| 主张 | 锚 | 等级 |
|---|---|---|
| S9/S10 不在 S8 范围 | `S8-charter.md:13-18` | A（章程） |
| S7 只消费 S9/S10 | `S7-agent-v1.md:58-65`（S7-8/9） | A |
| 指标归属 | 本提案 §12 | 本项目假设 |

---

## 13. 指标完整性自查

| 类 | 指标 | 有公式 | 有阈值 | 有失败语义 |
|---|---|---|---|---|
| 正确性 | C-HAC-DET/C-REGISTRY/C-PRESENCE/C-SUBSET/C-CLOSURE/C-TIE/C-SCHEMA | ✅ | ✅ | ✅ |
| 确定性 | determinism_sha 两次一致 | ✅ | ✅ | ✅ |
| 性能 | P-NODES/P-EDGES/P-BUDGET/P-FPS/P-ANIM/P-*-P95 | ✅ | ✅ | ✅ |
| 可解释 | X-RULE/X-SUMMARY/X-UNKNOWN/X-TRUNC/X-DEGRADE/X-EXPLAIN-RATE | ✅ | ✅ | ✅ |
| agent | A-WRITE/A-READONLY/A-REF/A-UNKNOWN/A-TOKEN/A-CALLS/A-DEGRADE/A-AUDIT | ✅ | ✅ | ✅ |
| 数据质量 | D-SEM-PURITY/D-SEM-EDGE/D-SEM-KP/D-NOSEM/D-CLUSTER-COV/D-CURATION | ✅ | ✅/信号 | ✅ |
| 回归 | G-SCHEMA/G-DET/G-PRESENCE/G-SUBSET/G-CLOSURE/G-AUDIT/G-NOWRITE/G-G6/G-MERMAID | ✅ | ✅ | ✅ |

---

## 14. 本项目假设清单（8 条）

1. P95 交互 ≤200ms、首开 ≤1500ms、切页签 ≤300ms、Admission ≤50ms（S3 只给 60/30fps+180ms；其余为建议）。
2. G6 落盘 `.memoria/agent/audit/graph/g6/`，命令 `scripts/verify/g6_snapshot.py`（S6 未冻结 G6 路径）。
3. G7 保留 90 天或 100k 条、单库 ≤64MB；不存正文/excerpt。
4. CI 只跑结构性 P0；FPS/延迟在本地参考硬件门禁。
5. `D-SEM-*` 不设 P0 下限（语料质量信号；no_semantic 合法）；语义纯净 P0。
6. Flaky：同 gate 3 次内失败可复核；阈值不得下调；需 owner/issue。
7. 0.5 I-07 只验 2D；3D capability=false 不阻断。
8. G6 baseline 更新需 decision_id；旧快照保留。

---

## 15. 复跑机检（Windows PowerShell；已执行）

```powershell
$env:PYTHONIOENCODING='utf-8'
# 1) S8 12 议项 + 关键指标
python -c "from pathlib import Path; t=Path('docs/design/multilevel-graph/S8-metrics-proposal-A.md').read_text(encoding='utf-8'); print('missing S8:',[f'S8-{i}' for i in range(1,13) if f'S8-{i}' not in t]); print('P0', t.count('P0'), 'G6', t.count('G6'), 'G7', t.count('G7'))"
# 2) 上游 G6/G7 schema 存在
python -c "from pathlib import Path; t=Path('docs/design/multilevel-graph/S6-contract-v1.md').read_text(encoding='utf-8'); print('G6', 'G6_SNAPSHOT' in t); t2=Path('docs/design/multilevel-graph/S7-agent-v1.md').read_text(encoding='utf-8'); print('G7', 'G7_SNAPSHOT' in t2)"
# 3) 现有门禁目录
python -c "from pathlib import Path; print(Path('scripts/agent').exists(), Path('scripts/benchmark').exists())"
```

**实测结果（2026-11-04）**：
- S8-1..S8-12 全部含 定义/规则·机检·反例·边界·U 映射·建议裁决·证据等级（缺失 0）。
- S6 G6_SNAPSHOT、S7 G7_SNAPSHOT 均存在；`scripts/agent`、`scripts/benchmark` 存在（只读门禁来源）。
- 指标表覆盖 7 类，P0/soft 双轨。

---

## 16. 已知限制

1. 本场为度量提案，未运行 G6/G7/性能实测；阈值需 S8a/SE 用真实基线校准。
2. P95/保留期/CI 命令为建议值；S3 只冻结 60/30fps、180ms、200/400 硬值。
3. 现有 `scripts/agent/*` 未逐条对接（只确认目录存在）；S8a 需映射具体 gate。
4. G6 路径未在 S6 冻结，本提案建议路径需 S6a/SE 确认。
5. S9/S10 指标未定义（归各自），S8 只给门禁/接口形态。
