# S10 章程：agent 设计知识点与语义边（KP 定义、抽取、curation、写路径、质量）

> **依据（不可改写）**：`multilevel-graph-vision.md`（U-1..U-35），尤其 U-12/13/14/19/21/22/25/27/32。
> **上游冻结**：S0–S9 十份 v1（+ S3/S6 ADDENDUM），**不得违反**；逐议项（U-34）。
> **状态**：S10 章程 V1（Lead 起草）。本场是设计研讨最后一场；冻结前不写产品代码。
> **日期**：2026-11-04（Asia/Shanghai）。

## 1. 目的

冻结 **agent 如何设计知识点（KP）与语义边**：KP 的定义/粒度、从原文抽取、语义边类型/方向/证据、双引用与 curation、写路径（propose_write/plan/backup/undo/audit）、冲突/去重/合并、版本失效（S9 重建）、质量评估、与 S1 registry/S2 clustering 的交互、失败/隐私、以及与 0.5 的边界。
S10 不实现 0.5；本场只产出未来 agent 自动 curation 的设计规格。

## 2. 不在范围

- 0.5 实现（0.5 明确不做 agent 自动 semantic/写图）；
- 图谱 UI（S3–S5）、数据契约（S6）、agent 消费（S7）、检索（S9）；
- 具体 LLM prompt 工程（本场只定义输入/输出契约与证据要求）。

## 3. 议项清单（逐项裁决；一项未裁决不得跳下一项）

每项产出：定义/规则、机检条件、反例、边界用例、U 映射、建议裁决、证据等级。

| 编号 | 议项 | 必须回答 |
|---|---|---|
| S10-1 | 定位与边界 | agent 只写 KP/语义边（不写事实正文）；与 S6 单一真源/S10 写范围；0.5 不做；人工确认 |
| S10-2 | KP 定义/粒度 | KP 是什么（可标注的语义单元）；最小/最大粒度；与 section/KP range 关系；title/alias/summary 字段 |
| S10-3 | KP 抽取/生成 | 从 md/sidecar 抽取；证据锚（file/line/anchor）；不得编造；低置信处理；幂等/去重 |
| S10-4 | 语义边设计 | 关系类型集合/方向/命名；语义 vs 结构；证据/置信；不得用结构/引用边伪造语义；边可解释 |
| S10-5 | 双引用/curation | provenance（source_id/target_id/assertion_source）；`curated_by/curated_at`；人工确认；undo |
| S10-6 | 写路径 | propose_write/plan evidence/atomic/backup/undo/audit；禁绕过；失败零写入；批处理 |
| S10-7 | 冲突/去重/合并 | 重复 KP/别名/同义边；冲突保留 vs 合并；人工裁决；历史保留 |
| S10-8 | 版本/失效 | edition 变化；S9 索引失效/重建；S6 cache；旧 KP/边保留；回滚 |
| S10-9 | 质量/评估 | KP/边 precision/recall；golden；人工抽检；置信阈值；错误类型 |
| S10-10 | 与 S1/S2 交互 | KP → registry/history；KP → cluster membership；cluster 稳定性；多归属 |
| S10-11 | 失败/降级/隐私 | 无源/歧义/低置信/冲突/超预算；不自动 apply；PII/正文边界；审计 |
| S10-12 | 与 0.5 边界 | S10 设计不在 0.5；未来版本实施；人工确认 UI 才可 apply；不影响 0.5 DoD |

## 4. 预注册判据（会前写死）

1. agent 只写 KP/语义边，不写事实正文；事实只读；与 S6 单一真源一致；
2. KP 定义/粒度/字段明确；证据锚可机检；不得编造；
3. 语义边类型/方向/证据/置信明确；**结构/引用边不得当语义**；
4. 双引用 + `curated_by/at` + 人工确认 + undo；禁绕过 propose_write；
5. 写路径原子/备份/零写入失败/审计；批处理可回滚；
6. 冲突/去重/合并规则明确；历史保留；人工裁决；
7. edition 变化 ⇒ S9 失效/重建；旧数据可回滚；
8. 质量指标/golden/阈值/人工抽检明确；
9. 与 S1 registry/S2 clustering 交互明确；
10. 失败/降级/隐私可见；不自动 apply；0.5 边界明确；
11. 两份独立提案差异逐条裁决；SE 校核 PASS；
12. 不写产品代码、不改契约、不 commit。

## 5. 输入与预读

- 原话：`multilevel-graph-vision.md`；
- 上游冻结：S0–S9 十份 v1 + 两 ADDENDUM；
- 工程：`ENGINEERING-PLAN.md`（30 图 + I-01..I-13）；S6 curate_contain 现状（只读）；
- 现有实现：`src/memoria/services/agent/plan.py`/`apply.py`/`sidecar`（只读证据）。

## 6. 角色与交付

| 角色 | 成员 | 交付 |
|---|---|---|
| 主办研究（提案 A） | `gm-seminar-researcher` | `S10-kp-proposal-A.md` + 证据 |
| 独立复核（提案 B + 异议） | `gm-seminar-verifier` | `S10-kp-proposal-B.md` + `S10-objections.md` |
| 软件工程专家 | `graph-se-architect` | `S10-engineering-check.md` + KP/边/写路径图 + `PARSE_OK` |
| 并集与裁决 | Lead | `S10-RULINGS.md` → `S10-kp-v1.md`（冻结候选） |

## 7. 冻结门禁

1. A/B 独立完成 + 差异清单 + 异议关闭（P0/P1 逐条证据）；
2. SE 工程校核 PASS（KP/边/写路径/失效/质量，与 S0–S9 一致）；
3. Lead 独立机检（边界/证据/语义/双引用/写路径/冲突/质量/0.5 边界）；
4. 与 S0–S9 无冲突；
5. 满足后冻结 `S10-kp-v1.md` 并写决策。

## 8. 变更控制

- 加字段/指标/阈值：S10 修订 + 决策；删/改写范围/KP 定义/语义边语义：重开 S10；
- 本场无产品代码；S10 实现不在 0.5。
