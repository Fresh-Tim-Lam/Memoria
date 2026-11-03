# S8 裁决（Lead）：并集、异议处置与修订轮

> **依据**：`multilevel-graph-vision.md`；`S8-charter.md`；
> 上游冻结 S0/S1/S2/S3(+ADDENDUM-1)/S4/S5/S6(+ADDENDUM-1)/S7（`241b1e1e…/6676c71d…/92bb0041…/0ca4ea0e…/2576f6c8…/7f4c4515…/40f12e5f…/70dd8748…`）。
> **输入**：提案 A（`114acd53…`）、提案 B（`c59570d0…`）、异议（`b53d2fa8…`）。
> **状态**：S8 **未冻结**；两版无 P0，3 条 P1 需冻结前修。本文件是修订轮唯一依据。

## 0. Lead 复核

| 项 | 复核动作 | 结论 |
|---|---|---|
| P1-1 X-RULE 漏 non-shown 节点 | 读 A 指标定义与 S4/S6/S3-ADDENDUM-1 | **成立**：节点也有 presence/rule_id；只算边会让节点抑制时 P0 仍 100% |
| P1-2 G6 路径冲突（A audit vs B artifacts） | 读 S6-8 与 A/B | **成立**：G6 路径未在 S6 冻结；必须唯一，否则基线/CI 分裂 |
| P1-3 CI 缺 G7 gate | 读 A S8-9 与 S8-6 | **成立**：写工具回归无法阻断；必须有 G-G7 P0 |
| 其余点名 | 指标可机判/G6/G7/性能/可解释/semantic-only/故障/CI/DoD/S9-S10 | 方向 PASS；P2 合并 |

## 1. 跨议题裁决（R-S8-1..R-S8-6）

### R-S8-1 X-RULE 覆盖节点+边（P1-1）
- **裁决**：`X-RULE` 定义改为 **`(non-shown nodes with rule_id + non-shown edges with rule_id) / (all non-shown nodes + all non-shown edges)`**，目标 **100%**；同时给 **`X-NODE-RULE`**、**`X-EDGE-RULE`** 分项；`rule_id=null` 的 non-shown 一律记失败；机检用 VM/Admission fixture（节点+边）。
- **理由**：S4/S6 要求节点/边逐条 presence/rule_id；只算边会留盲区。

### R-S8-2 G6 快照唯一路径（P1-2）
- **裁决**：G6 快照/基线**唯一落盘域 = `.memoria/agent/audit/graph/g6/`**（S6-8 audit 域）；`artifacts/agent/verify/graph/g6/` 只放**人类可读报告/副本**，不得作为基线/CI 事实源；`snapshot_id = sha256(canonical(G6_SNAPSHOT without snapshot_id))`；基线更新需 `decision_id`，旧快照保留；CI 读 audit 域。
- **机检**：路径唯一；基线/CI 同源；sha 可复算。

### R-S8-3 CI 增加 G-G7 P0 gate（P1-3）
- **裁决**：CI P0 gates 增加 **`G-G7`**：断言 `write_attempts=0`、`read_only=100%`、G7 引用 G6 `run_ids/frame_ids`、**无正文/excerpt/PII**；命令/exit code/产物 sha 进 S8；与 S8-6 指标一致；失败阻断。
- **机检**：G-G7 存在；失败 exit≠0；产物 sha。

### R-S8-4 性能假设与来源（P2）
- **裁决**：`60fps/30fps/180ms/200/400` 来自 S3/S4，属硬/冻结值；**P95 交互/首开/切页签/Admission 标注「假设，需实测基线校准」**，不得写成已冻结阈值；冷/热/参考硬件/样本 N≥30 必须写明；CI 无 GPU 时性能只在本地参考硬件门禁，结果附环境。

### R-S8-5 故障矩阵与 flaky（P2）
- **裁决**：故障注入补 **renderer budget** 与 **S9 unavailable** 两类；flaky 统一为「P0 不 flaky；诊断性重试最多 3 次；阈值不得因 flaky 下调」；C-REGISTRY 的 `signed=false` 不是失败（S6 可选签名），单独记录。

### R-S8-6 字段/DoD/隐私（P2）
- **裁决**：`X-SUMMARY` 与 S4 `suppressed_summary/rule_histogram` 字段统一；`snapshot_id` 公式固定；DoD：**I-07 只验 2D P0，3D capability=false**；G7 只存 id/anchor 引用/counts，不存正文/excerpt/PII，保留 90 天或 100k 条/≤64MB（S8 冻结）。

## 2. 修订轮任务

**A-v2**：X-RULE 节点+边（含分项）；G6 路径 audit 域；CI G-G7；性能假设标注；故障补 renderer/S9；flaky/签名/字段/DoD。
**B-v2**：同口径 X-RULE；G6 路径改 audit；CI G-G7；补 A 的指标表/G7 阈值/DoD；统一 flaky/字段。
**SE（task-333）**：等 v2 齐后校核 + G6/G7 命令/CI 接入/DoD 映射 + `PARSE_OK`。

## 3. S8 冻结门禁

1. A-v2/B-v2 关闭 R-S8-1..6（逐条证据）；
2. SE 工程校核 PASS（G6/G7 命令/CI/DoD、mermaid）；
3. Lead 独立机检（指标覆盖/阈值来源/X-RULE 节点/路径唯一/CI gate/DoD/隐私）；
4. 与 S0–S7 无冲突；
5. 冻结 `S8-metrics-v1.md` 并写决策。

## 4. 边界

不写产品代码；不改 S0–S7 冻结稿；S8 冻结前不开工实现；修订保留旧版。
