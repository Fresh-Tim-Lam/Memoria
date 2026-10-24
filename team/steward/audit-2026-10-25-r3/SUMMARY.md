# steward 第三轮审计（r3）—— task-116 后重读标准

> **触发**：task-116 修改了 `scripts/agent/team_audit.py`（r2 收据里该标准 sha 已过期 ⇒ `steward_self_audit` 按设计 FAIL=2）。
> **处置**：重读标准写 r3（不改 r2 收据）。**审计者**：steward；**时间**：2026-10-25T01:2x+08:00
> **收据**：`standards_read.json`（4 标准新 sha）/ `findings.jsonl`（台账 30 行 → 快照 29 条，含 1 条更正记录 supersede）

## 1. 标准 sha 复验（r3）

| 标准 | sha256（LF 归一化） |
|---|---|
| AGENTS.md | `6c87fe55077c4a73…`（未变） |
| docs/guides/lead-dispatch-rules.md | `488d7ebd78c917e2…`（未变） |
| docs/guides/agent-team-lessons.md | `f2f86b090d6e088a…`（未变） |
| scripts/agent/team_audit.py | 新值（task-116 实现变更） |

`determinism`：PASS（`team_audit.py --determinism`，sha `b8226d22…`，compared_findings=74）。

## 2. 本轮变更引发的自查修复

1. **`snapshot_health` 的确定性缺陷（SF-029，已修）**：原实现把 `artifacts/agent/verify` 的实时 mtime
   写进 finding message/evidence；并发写入时两次 determinism 运行差 1 秒 ⇒ §5.4 自检假红。
   已改为只记 `exportedAt` + `newest_mtime` 布尔事实；修复后 `--determinism` **PASS**。
   **教训**：检查输出只能包含来自输入的稳定事实，不得包含实时时钟/mtime。
2. **SF-028 更正（SF-030，supersede）**：原 finding 漏填 `rule_ref`（违反 org.md §2.6 B4 对非 proposal 的要求）。
   r3 台账追加 SF-030 作为更正记录（`corrects_finding_id`），**审计快照用 SF-030 替换 SF-028**；
   SF-028 原行保留（append-only 不改历史）。其依据补为 `PROTOCOL.md §3 J6'`，且 position/ 产物已提交 ⇒ dq6 转 PASS。

## 3. 当前机检状态（本轮实跑）

- `deliberation_quality`：**dq1-dq6 全部 PASS**（INFO：rulings=26 / 证据引用=35 / pinned=9）；
  dq5 对 `role=机检实现` 的 team_audit.py 报 tooling WARN（不阻断，v1.1 建议正式分离）；
  dq8/dq9 宽限 WARN（evidence_ledger 与 coverage 属架构辩论阶段）；dq10 INFO。
- `steward_self_audit`：r3 收据生效后 INFO。
- 其余检查无回归。

## blind_spots（本轮未审计什么）

1. **语义判断**：`unique_evidence` 是否真 unique、共享假设是否"合理"、证据是否足以支撑结论——机器不判。
2. **架构辩论尚未开始**：`coverage` 三表、`evidence_ledger`、M2 的独立来源计数在下一阶段才有输入。
3. **并行任务产物**：task-114/115 的 `position/**` 只在"是否 git tracked"层面被 dq6 检查，内容正确性不在本轮。
4. **本轮未重跑 product/性能门禁**（非 steward 域；由 metrics-baseline 负责）。
