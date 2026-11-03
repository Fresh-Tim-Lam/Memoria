# S8 异议与 A/B 差异 v2（复核方修订版对照）

> **依据（唯一裁决依据）**：`docs/design/multilevel-graph/S8-RULINGS.md`（sha `41828870…`，R-S8-1..R-S8-6）。
> **对象**：`S8-metrics-proposal-A-v2.md`（主办研究，sha **`7459b9576a1271d7290ed35b7879e86845b78fa60625116670849d70180b8ec7`**，26,277 B）与 `S8-metrics-proposal-B-v2.md`（本复核方，sha **`76707304b70adcf3b6b46aca1a37ae3bb4a4aa4651f7f6b824dffe6be640f240`**，20,348 B）。
> **性质**：B-v2 以 R-S8 为依据独立修订，完成后对照 A-v2；逐项列差异、不合并。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S8-RULINGS/S0–S7。

---

## 0. R-S8 关闭矩阵

| 裁决 | A-v2 | B-v2 | 判定 |
|---|---|---|---|
| R-S8-1 X-RULE 节点+边/分项/null 失败 | X-RULE 联合公式 100%；X-NODE/X-EDGE；`rule_id=null` FAIL；VM/Admission fixture | 同 | **关闭** |
| R-S8-2 G6 audit 路径/snapshot_id/基线 | `.memoria/agent/audit/graph/g6/` 唯一；artifacts 只报告；`snapshot_id=sha256(canonical(G6 without snapshot_id))`；baseline decision_id/旧快照 | 同 | **关闭** |
| R-S8-3 CI G-G7 | S8-9 加 `G-G7` P0：write=0/read_only=100%/引用 G6/无正文；命令/exit/产物 sha；失败阻断 | 同 | **关闭** |
| R-S8-4 性能冻结 vs 假设 | 60/30/180/200/400 标 S3/S4 冻结；P95/首开/切页签/Admission 标假设；冷热/硬件/N≥30；CI 本地 | 同 | **关闭** |
| R-S8-5 故障/flaky/signed | 补 renderer budget/S9 unavailable；P0 不 flaky/诊断≤3/阈值不降；signed=false 不失败 | 同 | **关闭** |
| R-S8-6 DoD/隐私/字段 | I-07 只 2D P0/3D capability=false；X-SUMMARY 对齐 S4；G7 90 天/100k/64MB/无正文 | 同 | **关闭** |

**结论**：R-S8-1..6 两版**全部关闭**；无 P0/P1；剩余为 S8a/SE 的路径/命令/阈值基线细节（P2）。

---

## 1. A-v2 / B-v2 逐项差异（S8-1..S8-12）

| 议项 | A-v2 | B-v2 | 差异与判断 |
|---|---|---|---|
| S8-1 框架 | 7 类 + P0/soft 对于；metric 字段完整 | 同类 + 总表（定义/公式/阈值/gate/证据/失败） | 一致；A 表按类，B 总表更紧凑；无冲突。 |
| S8-2 G6 | 字段严格 S6；audit 路径；snapshot_id 公式；baseline decision_id/旧快照；envelope `tool_env` | 同；envelope `env{...}`/`report_copy_path` | 一致；envelope 字段命名差异（P2-1），不参与 sha。 |
| S8-3 正确性/确定性 | C-HAC/C-REGISTRY（signed=false 不失败）/C-PRESENCE/C-SUBSET/C-CLOSURE/C-TIE/C-SCHEMA | 同；C-REGISTRY 分档 | 一致；A 表更细。 |
| S8-4 性能 | P-NODES/P-EDGES/P-BUDGET P0；FPS/ANIM/P95/首开/切页签/Admission soft；冻结 vs 假设分离 | 同；总表 + 条件 | 一致；A 更细；P95/首开假设均待基线（P2-2）。 |
| S8-5 可解释性 | X-RULE 联合 100%；X-NODE/X-EDGE；X-SUMMARY S4 字段；DOM/事件/快照 | 同 | 一致。 |
| S8-6 G7 | A-WRITE/A-READONLY/A-REF/A-UNKNOWN/A-TOKEN/A-CALLS/A-DEGRADE/A-AUDIT；ref≥99/unknown≤20/token≤4000/calls≤8 | 同；阈值表 | 一致；阈值均为建议（P2-3）。 |
| S8-7 数据质量 | D-SEM-PURITY P0；semantic only；结构/reference 不计；no_semantic 合法 | 同 | 一致。 |
| S8-8 故障 | 8 类含 renderer budget/S9；回放/2x sha/G6 diff；flaky 统一 | 同 | 一致。 |
| S8-9 CI | P0 清单含 G-G7；命令/exit/产物；本地性能；flaky | 同 | 一致；**命令名/脚本路径 A/B 不同（P2-1）**。 |
| S8-10 DoD | I-01..I-13 P0；I-07 2D P0/3D capability=false；不做项 | 同 | 一致。 |
| S8-11 存储/隐私 | G6 audit；G7 90d/100k/64MB；无正文 | 同 | 一致；保留值 PI（P2-3）。 |
| S8-12 S9/S10 | 指标归各自；不算法 | 同 | 一致。 |

**总判断**：两版在 R-S8 核心上已收敛；A-v2 指标表/DoD 细节更细；B-v2 总表/命令 gate/G7 gate 更显式。**无新增 P0/P1**；剩余 P2 为 S8a/SE 落盘细节。

---

## 2. 仍未解决 3 点（P2；S8a/SE 冻结）

### P2-1 命令名/脚本路径与 G6/G7 envelope 字段未统一
- **现状**：A-v2/B-v2 的 G6 复跑/G-G7/G6-G7 命令名与路径不同（A 示例 `scripts/verify/g6_snapshot.py`；B 示例 `scripts/benchmark/graph/g6_snapshot.py`；G-G7 `scripts/verify/g7_gate.py`）；G6 envelope A `tool_env`、B `env/report_copy_path`。命令/路径未冻结，CI/本地可能各跑一套；envelope 不参与 sha 但审计/报告字段不统一。
- **影响**：同一 G6 快照/CI gate 两个命令路径；G-G7 产物 sha 不一致；审计字段不同。
- **建议**：S8a/SE 冻结唯一脚本路径/命令参数/产物路径；G6/G7 envelope 字段统一（不参与 canonical）；CI 与本地同脚本；机检命令/exit/产物 sha。
- **证据**：R-S8-2/R-S8-3；A S8-2/S8-9；B S8-2/S8-9。

### P2-2 性能假设值（P95/首开/切页签/Admission）缺实测基线
- **现状**：两版均把 `P95 交互≤200ms、首开≤1500ms、切页签≤300ms、Admission≤50ms` 标为“假设，需实测基线校准”；R-S8-4 要求标注、不是冻结。当前无参考硬件基线，无法把 soft 假设升级为 P0/冻结。
- **影响**：性能验收只能相对回归/趋势，不能以固定 P95 阻断；若误当冻结值会误判低端/CI。
- **建议**：S8a 跑参考硬件基线（N≥30、冷/热、P50/P95/max），把实测值写回 S8；未校准前保持 soft/假设；CI 只相对回归±20%告警；不得把假设写死。
- **证据**：R-S8-4；A S8-4；B S8-4。

### P2-3 G7/G6 保留期与 G7 阈值仍为建议值
- **现状**：G7 90 天/100k 条/≤64MB、`A-REF≥99%/A-UNKNOWN≤20%/A-TOKEN≤4000/A-CALLS≤8` 均为 S8 建议/PI；R-S8-6 只冻结“90 天/100k/64MB”作为 S8 值，但阈值/隐私保留需 S8a/隐私评审确认；G6 ≤1MB/快照、基线永久也为建议。
- **影响**：未确认前 G7 阈值不能作为 P0；保留期/大小影响成本/隐私；若实现按建议值硬编码，后续修订需改契约。
- **建议**：S8a/隐私评审冻结 G7 保留/大小/字段白名单与阈值（或明确 soft/趋势）；G7 只存 id/anchor/counts、无正文/excerpt/PII；G6 不可变/基线永久；成本监控；数值变更走 S8 修订。
- **证据**：R-S8-6；A S8-11；B S8-11；S7 G7。

---

## 3. 点名审查结论（v2）

1. **指标可机判（定义/公式/阈值/命令/exit/sha）**：A/B **PASS**（总表/命令/exit/产物；X-RULE 联合；G-G7）；命令路径 P2-1。
2. **G6 与 S6 一致/可复跑/不可变**：A/B **PASS**（字段严格 S6；audit 唯一路径；snapshot_id 公式；baseline decision_id/旧快照；不可变）。
3. **G7 与 S7 一致/写尝试=0**：A/B **PASS**（G7 字段/引用 G6；A-WRITE=0 P0；G-G7 CI；无正文）。
4. **性能数值来源/测量条件**：A/B **PASS**（60/30/180/200/400 冻结；P95/首开假设；冷热/硬件/N≥30；CI 本地）；基线 P2-2。
5. **可解释性/降级可机测**：A/B **PASS**（X-RULE 节点+边联合 100%、分项、null FAIL；X-SUMMARY S4 字段；DOM/aria/事件/快照；不靠人工）。
6. **数据质量 semantic only/语料误判**：A/B **PASS**（D-SEM-PURITY P0；结构/reference 不计；no_semantic 合法 vs algorithm_failed 分离）。
7. **故障注入/回放**：A/B **PASS**（8 类含 renderer budget/S9；2x sha/G6 diff；失败可见）；回放环境字段 P2-1。
8. **回归门禁/CI flaky/本地 CI**：A/B **PASS**（P0 含 G-G7；本地性能；P0 不 flaky/诊断≤3/阈值不降；同 harness）；命令路径 P2-1。
9. **0.5 DoD/I-01..13/阻断**：A/B **PASS**（I-01..13 P0；I-07 2D P0/3D capability=false；不做项；P0 全 PASS 退出）。
10. **S9/S10 边界**：A/B **PASS**（指标归各自；不算法/阈值；只消费）。

---

## 4. 最严重 3 条 / 结论

1. **P2-1 命令/脚本路径与 G6/G7 envelope 未统一**：A/B 示例命令不同（`scripts/verify/...` vs `scripts/benchmark/graph/...`）；S8a/SE 冻结唯一命令/路径/产物 sha，CI 与本地同脚本。
2. **P2-2 性能假设值缺实测基线**：P95/首开/切页签/Admission 是假设，不得当冻结；S8a 跑参考硬件 N≥30 冷热基线，写回 S8；未校准前 soft。
3. **P2-3 G7/G6 保留/阈值仍为建议**：G7 90d/100k/64MB、ref/unknown/token/calls 阈值需 S8a/隐私评审确认；G7 无正文/excerpt/PII；G6 不可变/基线永久；数值变更走 S8 修订。

- **两版无 P0/P1**；R-S8-1..6 全部关闭；A-v2 指标表/DoD 更细，B-v2 总表/G-G7/故障矩阵更显式。未写产品代码/契约，未 commit；差异逐项列出未静默合并。

> 参考锚：R-S8 `S8-RULINGS.md:19-38`；A-v2 S8-2/S8-5/S8-9/S8-10；B-v2 同项；S6-11 G6；S7-12 G7。
