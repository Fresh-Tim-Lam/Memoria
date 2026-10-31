# 设计评审清单 v0.1（`comp.design-reviewer`）

> **状态**：P1 组件清单（2026-10-31，task-268；设计资产，非 conventions）。
> **组件**：`comp.design-reviewer`（`callable=false` / `executor.kind=role`；SOP：`docs/design/components-v0.2.md#sop-design-reviewer`）。
> **用途**：给“设计文档/设计决定”提供**可行性（feasibility）+ 规范性（conformance）**两栏评审清单与 finding 格式，使评审结论可追溯、可复核。
> **边界**：评审意见仍由人/Lead 裁；本清单不自动改设计文档；不新增事实源。
> **机器可读**：`artifacts/agent/plugin-design/DESIGN-REVIEW-CHECKLIST-v0.1.json`（字段：`id/category/ruleRef/question/evidenceRequired`）。

## 1. 清单（13 项，覆盖 5 份 conventions 文档）

| # | 类别 | ruleRef | 问题 | 需要证据 |
|---|---|---|---|---|
| FC-01 | conformance | `docs/conventions/docs-management.md#1` | 新设计文档是否按命名/位置规则落位？ | 文件路径 + §1 引用 |
| FC-02 | conformance | `docs/conventions/docs-management.md#2` | 是否在对应索引登记、未被重复事实源替代？ | 索引行 diff/引用 |
| FC-03 | conformance | `docs/conventions/markdown-form-std.md#3` | 标题/表格/代码块是否合规（不跳级/有表头/带语言）？ | 行号或 lint |
| FC-04 | conformance | `docs/conventions/test-assertion-granularity.md#2` | 验收判据是否可机检（命令+期望输出）？ | 命令 + exit |
| FC-05 | conformance | `docs/conventions/frontend-modules.md#1` | 涉及前端时模块边界/依赖方向是否合规？ | 模块图/import |
| FC-06 | conformance | `docs/conventions/meta-rules.md#2` | 不采纳/暂缓意见是否按规则 2 标记并留理由？ | ❌/⏳ + 理由 |
| FC-07 | conformance | `docs/conventions/refs-system.md#1` | 引用锚（file:line/#§/票号/URL）是否可解析？ | 锚清单 + 抽样 |
| FS-01 | feasibility | `docs/conventions/test-assertion-granularity.md#3` | 声称能力是否有可执行入口；没有则标 manual 而非假装具备？ | 入口路径/manual 标注 |
| FS-02 | feasibility | `docs/conventions/docs-management.md#1` | 数量/清单是否与唯一事实源一致（无过期计数）？ | 计数来源 + 复算命令 |
| FS-03 | feasibility | `docs/conventions/ledger-maintenance.md#1` | 是否引入平行台账/事实源？ | 引用路径清单 |
| FS-04 | feasibility | `docs/conventions/docs-management.md#2` | 依赖（前置文档/工具/角色）是否真实存在？ | 存在性检查输出 |
| FS-05 | feasibility | `docs/conventions/meta-rules.md#1` | 评审结论是否给出可执行建议（改哪个文件/§）？ | finding.recommendation |

> 覆盖文档：`docs-management` / `markdown-form-std` / `test-assertion-granularity` / `frontend-modules` / `meta-rules` / `refs-system` / `ledger-maintenance`（≥5 满足）。

## 2. Finding 格式（无 ruleRef 拒收）

```json
{"id": "F-01", "ruleRef": "docs/conventions/<file>.md#<anchor>",
 "severity": "FAIL|WARN|INFO",
 "evidence": "<路径:行/§/命令输出>",
 "recommendation": "<改哪个文件/哪一节，怎么改>"}
```

硬约束：`ruleRef` 非空且指向存在的 conventions 文档；`evidence` 非空；`recommendation` 非空。违反 ⇒ 校验器 exit 1（先证红：空 ruleRef 必拒收）。

## 3. 使用方式

1. 评审者按 §1 逐项检查，产出 findings（JSON + 人读记录）；
2. 运行样例校验器：`python artifacts/agent/plugin-design/validate_design_review.py --checklist <checklist.json> --findings <findings.json>`;
3. 结论交 Lead/人裁；本清单不自动修改设计文档，也不代签。

## 4. 样例

`artifacts/agent/plugin-design/DESIGN-REVIEW-COMPONENT-DECOMPOSITION-v0.1.md`（评审 COMPONENT-DECOMPOSITION-v0.1，5 条 findings 全部带 ruleRef）。

## 5. 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-31 | v0.1 | 首版（task-268）：13 项 checklist（feasibility/conformance）+ finding 格式 + 校验器 |
