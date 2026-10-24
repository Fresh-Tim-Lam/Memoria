# 辩论协议协商摘要（task-113）

**结论**：协议已冻结，`PROTOCOL.md`（commit 48ca704e）。

| 阶段 | 产物 | 规模 |
|---|---|---|
| Phase 1 四方独立提案 | `protocol-proposals/*.md` | 4 份 |
| Phase 2 Lead 并集合并 | `protocol-v1.md` | 25 条规则，Lead 自创 0 |
| Phase 3 四方异议 | `protocol-objections/*.md` | 19 条 objection |
| Phase 4 逐条裁决 | `ruling/rulings.jsonl` | 26 条裁决 |
| Phase 5 冻结 | `PROTOCOL.md` + `freeze-v2.json` + `PINNED-PROPOSALS.json` + `rules-index.json` | 36 条规则 |

**Phase 5 独立审计**：`audit/steward-phase5-audit.md`
- pinned sha 9/9 MATCH；26 裁决 falsifiers 26/26 非空；抽检 5/5；Lead 自创 0；产物 15/15 git tracked
- 7 条 finding，F-1（freeze.standards 为空）已于 2026-10-25 修复，sha 由 Lead 独立复算 5/5 MATCH

**未被采纳**：2 条（同一冲突 R-C7 内的两个极端），理由与 `unique_evidence_handled` 已给。
