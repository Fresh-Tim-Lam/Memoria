# S8 冻结记录（Freeze Record）

> **冻结对象**：`docs/design/multilevel-graph/S8-metrics-v1.md`（12 条规范 + R-S8-1..6 + G6/G7 命令 + CI 门禁 + 0.5 DoD）。
> **冻结时间**：2026-11-04T00:30+08:00（Asia/Shanghai）。
> **决策**：`dec-20261104-92880705`（Lead；S0–S7 已冻结）。
> **状态**：**已冻结**。0.5 实现有唯一验收口径；S9/S10 可开。

## 1. 冻结产物与身份

| 产物 | 角色 | sha256 |
|---|---|---|
| `S8-metrics-v1.md`（**冻结稿最终态**） | S8 唯一规范来源 | `c6a135ffb28c848ec351379b57aae99b86f213b1088815eae336e249f58e9f99` |
| `S8-engineering-check.md` | SE 工程校核 + S8a（命令/CI/DoD） | `ab4efa2a…` |
| `S8-metrics-proposal-A-v2.md` | 证据链（主办研究） | `7459b957…` |
| `S8-metrics-proposal-B-v2.md` | 证据链（独立复核） | `76707304…` |
| `S8-objections-v2.md` | 差异/异议 | `0234364a…` |
| `S8-RULINGS.md` | Lead 裁决（R-S8-1..6） | `41828870…` |
| `ENGINEERING-PLAN.md`（S8a） | 27 图（ER-09/DF-09/ST-09） | `53d44762…` |

**冻结轮次**：两版无 P0；第一轮 3 条 P1（X-RULE 漏节点、G6 路径冲突、CI 缺 G-G7）裁决后 A-v2/B-v2 全关闭（无剩余 P1）；SE M-S8-1..12 全 PASS、27 图 `PARSE_OK`；Lead 独立机检（12 条款、X-RULE 节点+边、G6 路径/sha、G-G7、性能冻结/假设、X-SUMMARY、8 故障、semantic-only、DoD、隐私）PASS。

## 2. S8 冻结了什么（一句话版）

1. **指标框架**：7 类；P0 硬门禁（命令/exit/产物 sha）vs soft（趋势/相对回归）；禁止单一指标掩盖失败；
2. **G6 快照**：字段==S6；唯一路径 `.memoria/agent/audit/graph/g6/`；`snapshot_id=sha256(canonical(without snapshot_id))`；不可变、基线 decision_id、旧快照保留、≤1MB；
3. **正确性/确定性**：HAC 100%、run_id 复算、registry 链、presence、subset、closure/behind=0、tie-break；`signed=false` 不算失败；
4. **性能**：冻结值 200/400、60/30fps、180ms（S3/S4）；假设值 P95 交互/首开/切页签/Admission 需实测基线；冷热/参考硬件/N≥30；CI 无 GPU 只本地；
5. **可解释性**：`X-RULE` 节点+边联合 100%（null FAIL）+ `X-NODE-RULE`/`X-EDGE-RULE`；`X-SUMMARY` 对齐 S4；truncated/降级可见、无静默；
6. **G7**：`write_attempts=0`/只读 100% P0；ref≥99%/unknown≤20%/token≤4000/calls≤8 soft；只存 id/anchor/counts、无正文/excerpt/PII；90 天或 100k/≤64MB；
7. **数据质量**：semantic-only，μ/β 输入==E_sem；结构/reference 不计、不得伪造；no_semantic 合法；
8. **故障注入**：8 类（预算/空语义/stale/缺失/非法/审计失败/renderer budget/S9 unavailable）；确定性回放 + G6 diff；
9. **CI**：P0 gates（schema/determinism/X-RULE/subset/closure/audit/no-write/G6/G-G7/mermaid）；P0 不 flaky、重试≤3、阈值不下调；
10. **DoD**：I-01..I-13 映射；I-05/06/07/08 P0 阻断（I-07 只验 2D、3D capability=false），其余 P1；
11. **存储/隐私**：G6 永久；G7 保留/大小；无 PII；
12. **S9/S10 边界**：检索/KP 质量归各自，S8 只消费指标/定义 gate。

## 3. 机检与证据

- SE M-S8-1..12 全 PASS（`M_fail=[]`）；S8a：ER-09/DF-09/ST-09，mermaid 11.16.0（`9198f632…`）**27 图 `PARSE_OK`**；
- 与 S0–S7 一致性：G6 字段/路径、S6 错误码、S7 G7/write=0/隐私、S4 presence/subset、S5 frame/事务、S3 性能预算、S0–S2 单一真源/维度/run — 全 PASS；
- Lead 独立机检 PASS。

## 4. 未关闭项（不阻塞冻结）

- O-S8-1..8：P95 实测校准、G6/G7 保留值、X-RULE 分项阈值、S9 降级实测、flaky 隔离池、G7 隐私抽样、CI 性能边界、DoD 证据路径。

## 5. 变更控制

- 加指标/阈值/gate：S8 修订 + 决策；删/改 P0 门禁/G6 字段/DoD：重开 S8；假设值校准后写回修订（不重开）。

## 6. 下一步

- **S9（后端检索）**、**S10（agent 设计知识点）** 按议程；0.5 实现按 S6a I-01..I-13 + S8 DoD。
