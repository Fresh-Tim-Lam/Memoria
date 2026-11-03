# S8 独立异议与 A/B 差异

> **依据（不可改写）**：`multilevel-graph-vision.md` U-1..U-35；上游冻结 S0–S7 八份 v1 + `S3-ADDENDUM-1`/`S6-ADDENDUM-1`，不得违反；`S8-charter.md`。
> **对象**：`S8-metrics-proposal-A.md`（主办研究，sha **`114acd53f438bf3879afba347b9038f389090e3794892d1dc4fc69cea6cdcb80`**，22,544 B）与 `S8-metrics-proposal-B.md`（本复核方，sha **`c59570d0a4fff0e4bb03c5e126783e30463f6421bc29aab7125683354d4c42d2`**，15,494 B）。
> **独立性**：B 于 00:22:42 落盘，A 于 00:23:22 才出现；B 写作时未读 A。以下为写完后对照，逐项列、不合并。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S0–S7 冻结。

---

## 0. A/B 差异总表（S8-1..S8-12）

| 议项 | A 的立场（A-v1） | B 的立场（B-v1） | 差异与判断 |
|---|---|---|---|
| S8-1 框架 | 7 类 + P0/soft 双轨；指标表字段/失败 | 同类；metric schema/命令/exit | 一致；A 表更细（每类 P0/soft 对于）；B 更强调 command/exit。 |
| S8-2 G6 | 字段严格 S6；**路径 `.memoria/agent/audit/graph/g6/`**；基线 decision_id | 字段严格 S6；**路径 `artifacts/agent/verify/graph/g6/`**；baseline | **关键差异**：G6 路径 A/B 不同，S6 未冻结 G6 路径（A §14.2 自列）；需 Lead/SE 冻结（P1-2）。字段一致。 |
| S8-3 正确性/确定性 | C-HAC-DET/C-REGISTRY/C-PRESENCE/C-SUBSET/C-CLOSURE/C-TIE/C-SCHEMA；P0 100% | 同核心；阈值/两跑；无 C-REGISTRY 签名细节 | 一致；A 更细（C-REGISTRY sign）；B 需补 signed=false 处理（P2）。 |
| S8-4 性能/预算 | P-NODES/P-EDGES/P-BUDGET P0；FPS/ANIM/P95/首开 soft；条件/假设 | 60fps/180ms/200/400；冷热/样本/p95；CI soft | 一致；A 数值更全（P95/首开为假设）；B 条件相似；两者均需实测基线（P2-1）。 |
| S8-5 可解释性 | X-RULE **仅 non_shown edges**；X-SUMMARY/UNKNOWN/TRUNC/DEGRADE；P0 | rule_id 解释率覆盖 **suppressed/unknown 节点/边**；DOM/事件/快照；P0 | **关键差异**：A X-RULE 只算边，漏 non-shown **节点** presence/rule_id（S4/S6 要求节点/边逐条）；B 更完整（P1-1）。A 需修。 |
| S8-6 G7 | A-WRITE/A-READONLY/A-REF/A-UNKNOWN/A-TOKEN/A-CALLS/A-DEGRADE/A-AUDIT；写=0 P0；G7 引用 G6 | 同核心；write_attempts=0；ref/unknown/truncation；G7 引用 G6 | 一致；A 阈值更细（ref≥99%/unknown≤20%/calls≤8）；B 较简。 |
| S8-7 数据质量 | D-SEM-PURITY P0；semantic only；结构/reference 不计；no_semantic 合法 | 同 | 一致；A 表更细（D-SEM-EDGE/KP/NOSEM/COV/CURATION）。 |
| S8-8 故障注入 | 6 类：预算/空语义/stale/缺失/非法/审计失败；回放/G6 diff | 预算/no_semantic/stale/missing/invalid/audit + renderer budget/S9 unavailable；回放 | 一致；B 覆盖更宽（renderer/S9）；A 缺 renderer/S9（P2-3）。 |
| S8-9 CI | P0：schema/det/presence/subset/closure/audit/no-write/G6/mermaid；**未列 G7 gate**；本地性能/ flaky 3 次 | P0：G6/schema/mermaid/presence/VM/G7 write=0/fault；本地/CI 同 harness；flaky | **关键差异**：A CI P0 清单未显式含 G7 write_attempts=0/ref（虽有 A-WRITE P0 指标）；B 有；需补（P1-3）。 |
| S8-10 DoD | I-01..I-13 全 P0；不做项；P0 全 PASS | 同；I 表/阻断/退出 | 一致；A 更细（每 I 验收句）。 |
| S8-11 存储/隐私 | G6 audit 路径；G7 90 天/100k/64MB；无正文 | G6 artifacts；G7 90 天/大小；无正文 | 一致；路径需统一（P1-2）；A G7 保留更细。 |
| S8-12 S9/S10 | 只消费；指标归 S9/S10；不算法 | 同 | 一致。 |

**总判断**：A 在指标表/P0/soft/性能/G7 阈值/DoD 细节上更强；B 在 X-RULE 节点覆盖、故障矩阵宽度、CI G7 gate、G6 路径（相对 A audit 路径）上更完整。**P1 集中在 X-RULE 节点、G6 路径冲突、CI G7 gate**。

---

## 1. 异议（按严重度；P0=违反 S0–S7；P1=冻结前必须裁；P2=后续/SE）

### P1-1（A）`X-RULE` 只统计 non-shown **边**，漏 non-shown **节点** 的 presence/rule_id 解释

- **议项**：S8-5（S4 R-S4-4；S6-5/ADDENDUM-1；S3）。
- **异议**：A 的 `X-RULE = non_shown edges with rule_id / non_shown edges` 只覆盖边。S4/S6 的候选载体要求**全部候选节点/边**逐条 presence/rule_id（节点 presence 由 S3-ADDENDUM-1 加入 VM 白名单）；若某节点被 suppressed/unknown 且无 rule_id，X-RULE 仍 100%，但可解释性失败（无法解释“为什么节点没出现”）。B 的指标覆盖 suppressed/unknown 节点/边，更完整。A S8-5 正文写“所有 suppressed/unknown 可解释”，但公式不覆盖节点，属实现漏洞。
- **反例**：节点 `role=member` 被预算抑制且 `rule_id=null`；边全部有 rule_id ⇒ X-RULE=100% PASS，但节点无法解释。
- **修复**：`X-RULE = (# non-shown nodes with rule_id + # non-shown edges with rule_id) / (# non-shown nodes + # non-shown edges)`，阈值 100% P0；另加 `X-NODE-RULE`/`X-EDGE-RULE` 分项；机检 VM/AdmissionResult 节点+边；B 同口径。
- **严重度**：presence 可解释性 P0 ⇒ **P1（冻结前）**。

### P1-2（A/B）G6 快照路径 A 与 B 不一致，S6 未冻结 G6 路径

- **议项**：S8-2（S6-11 G6；S6-8 路径；S6a 接口）。
- **异议**：A S8-2 路径 `.memoria/agent/audit/graph/g6/<snapshot_id>.json`（A §14.2 自列“S6 未冻结 G6 路径”）；B 用 `artifacts/agent/verify/graph/g6/<snapshot_id>.json`。S6-8 只冻结 audit `.memoria/agent/audit/graph/`（append-only）与 cache `.memoria/cache/graph/`；G6 作为全链路快照既非纯 audit 也非 cache，路径未在 S6 冻结。S8 若冻结 A/B 不同路径，S6a/CI/baseline 会分裂；同一 snapshot_id 两处、G6 diff/基线引用不唯一。
- **反例**：CI 按 A 路径找 G6；本地按 B 路径生成；baseline 指向另一个；G6 快照漏检。
- **修复**：Lead/SE/S6a 冻结唯一路径（推荐 S6-8 的 audit 域 `.memoria/agent/audit/graph/g6/`，因 G6 是审计快照、不可变、不 GC；`artifacts/agent/verify` 只放 CI 报告/校验产物）；S8-2 写死；A/B 统一；机检路径/基线/sha。
- **严重度**：G6 验收硬门禁 ⇒ **P1（冻结前）**。

### P1-3（A）S8-9 CI P0 清单未显式含 G7 `write_attempts=0`/引用完整率 gate

- **议项**：S8-9（S7 G7；S8-6 A-WRITE P0；S8 章程判据 6）。
- **异议**：A S8-1/S8-6 已把 `A-WRITE`（write_attempts=0）列为 P0，但 S8-9 的 CI gate 清单只有 `G-AUDIT/G-NOWRITE`（无 sidecar/写工具）与 G6/schema 等，**没有显式 `G-G7`**；B 的 CI P0 有 `G7 write_attempts=0`。若 CI 不跑 G7，P0 指标仅文档存在，无法阻断；S8 章程要求“P0 硬门禁必须机器可判”和 G7 写尝试=0 硬约束。
- **反例**：实现引入写工具或 write 参数，G7 指标检测到 write_attempts>0，但 CI gate 未执行 ⇒ 合并通过。
- **修复**：S8-9 增加 `G-G7`：运行 G7 fixture/工具调用审计，断言 `write_attempts=0`、`read_only=100%`、G7 引用 G6、无正文；P0 阻断；exit code/命令/产物 sha；与 S8-6 指标一致。
- **严重度**：G7 写边界 P0 ⇒ **P1（冻结前）**。

### P2 清单

| # | 项 | 判断/修复 |
|---|---|---|
| P2-1 | 性能阈值来源：A P95/首开/切页签为假设；B 同；S3 仅 60/180/200/400 | Lead/SE 用实测基线定 P95/首开；A/B 标注假设；CI 性能只相对回归；不得把假设当既成事实 |
| P2-2 | A `C-REGISTRY` 签名验证：S6 history signed 可选，`signed=false` 合法 | 指标需区分 `signed=true` 验签 vs `signed=false` 允许/G6 标记；不得把未签名当失败 |
| P2-3 | A 故障矩阵缺 renderer budget exceeded/S9 unavailable；B 有 | A 补两类；故障覆盖预算/空/stale/缺失/非法/审计 + renderer/S9；回放确定 |
| P2-4 | A S8-9 flaky 3 次 vs B 2 次/隔离 | S8 统一 flaky 政策：P0 不 flaky；重试仅诊断；隔离需 owner/issue；阈值不放宽 |
| P2-5 | A G7 路径/保留：`.memoria/agent/audit/graph/g7` 90d/100k/64MB；B 同域 | S8a 冻结；G7 聚合可重算；无正文；G6 路径 P1-2 同步 |
| P2-6 | A S8-5 `X-SUMMARY` vs S4 `suppressed_summary` 字段；B summary 字段 | 统一 S4/S6 字段名；机检 summary count==suppressed_count |
| P2-7 | A S8-8 回放/G6 diff 无 `seed`/环境字段 | 回放固定 seed/edition/env；G6 envelope 记录 env；2x sha |
| P2-8 | A G6 `snapshot_id=sha256(S6 fields+g6_version)`；S6 G6 已含 g6_version | 避免重复；冻结 canonical 字段集；B 同 |
| P2-9 | A/B DoD I-07 3D capability=false / 2D only | 统一：2D P0；3D 接口 P0、实现不做；DoD 不夹带 3D |
| P2-10 | A/B G7 token 阈值（A token/call≤4000/8 calls） | S8 统一；采样/隐私；不把均值掩盖尾部 |

---

## 2. 点名审查结论

1. **指标可机判（定义/公式/阈值/命令/exit/sha）**：A/B 方向 **PASS**；A 表更细；**P1-1 X-RULE 公式漏节点**；**P1-3 CI G7 gate 缺失**。
2. **G6 与 S6 一致/可复跑/不可变**：A/B 字段严格 S6 **PASS**；**路径冲突 P1-2**；G6 不可变/基线决策 PASS。
3. **G7 与 S7 一致/写尝试=0**：A/B 指标一致；A-WRITE P0 **PASS**；**CI gate 缺失 P1-3**；G7 引用 G6 PASS。
4. **性能数值来源/测量条件**：A/B **PASS**（60/180/200/400 来自 S3/S4；P95/首开假设已标注；冷热/样本/硬件/CI 本地分开）；P2-1 实测基线。
5. **可解释性/降级可机测**：A/B **PASS**（VM/Admission fixture + DOM/aria + 事件/快照，不靠人工）；A X-RULE 节点漏 P1-1。
6. **数据质量 semantic only/语料误判**：A/B **PASS**（D-SEM-PURITY P0；结构/reference 不计；no_semantic 合法 vs algorithm_failed 分离）。
7. **故障注入覆盖/回放确定性**：A 6 类/B 更宽 **PASS**；A 缺 renderer/S9（P2-3）；回放固定 fixture/2x sha PASS。
8. **回归门禁/CI flaky/本地 vs CI**：A/B **PASS**（P0 CI、性能本地、flaky 策略、同 harness）；A G7 gate P1-3；flaky 次数 P2-4。
9. **0.5 DoD/I-01..13/阻断级别**：A/B **PASS**（I-01..13 全 P0、不做项、P0 全 PASS 退出）；3D 2D only PASS。
10. **S9/S10 边界**：A/B **PASS**（指标归 S9/S10；S8 只消费/接口；不夹带算法）。

---

## 3. 最严重 3 条（给 Lead 裁决顺序）

1. **P1-1（A）X-RULE 只算 non-shown 边，漏 non-shown 节点**：S4/S6 要求节点/边逐条 presence/rule_id（S3-ADDENDUM-1 节点 presence 已进 VM）；节点被抑制无 rule_id 时 X-RULE 仍 100%，可解释性 P0 失效。修复：联合分母（节点+边）100%；加 X-NODE-RULE/X-EDGE-RULE；B 同口径。
2. **P1-2（A/B）G6 路径 A `.memoria/agent/audit/graph/g6/` vs B `artifacts/agent/verify/graph/g6/`，S6 未冻结**：同一 snapshot_id 两处、baseline/CI 分裂。修复：Lead/SE/S6a 冻结唯一路径（推荐 audit 域 `.memoria/agent/audit/graph/g6/`；artifacts 只放报告），S8-2 写死，A/B 统一；机检路径/sha/基线。
3. **P1-3（A）S8-9 CI P0 清单缺 G7 gate**：A-WRITE 是 P0 但 CI 未执行；写工具回归无法阻断。修复：加 `G-G7`（write_attempts=0/read_only=100%/引用 G6/无正文），P0 exit/命令/产物 sha；与 S8-6 一致。

## 4. 结论

- **两版无 P0**；A 指标表/性能/G7/DoD 细节更强；B X-RULE/故障矩阵/CI G7/路径更完整。
- **P1-1/P1-2/P1-3 冻结前必修**；P2 包括性能假设基线、C-REGISTRY signed=false、故障矩阵 renderer/S9、flaky 政策、G6 snapshot_id 重复、G7 保留/隐私、DoD 3D。
- 未写产品代码/契约，未 commit；差异逐项列出未静默合并。

> 参考锚：S8 章程 S8-1..12；S6-11 G6；S6-8 路径；S7-12 G7；S4 R-S4-4；A S8-2/S8-5/S8-9；B S8-2/S8-5/S8-9。
