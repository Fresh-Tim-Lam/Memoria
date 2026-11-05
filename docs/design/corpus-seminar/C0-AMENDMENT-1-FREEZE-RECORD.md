# C0-AMENDMENT-1 冻结记录（evaluation-first）

> **冻结对象**：`docs/design/corpus-seminar/C0-AMENDMENT-1.md`
> **sha256**：`1fc31cdc8cdfd4b794387013db99a52a7685d999a6c51838fcb39bf73851ee9a`
> **决策**：`dec-20261105-d3030e4c`；裁决 D1–D3 见 `C0-AMENDMENT-1-RULINGS.md`。
> **状态**：**已冻结**；替代 C0 v1 的 C4/C5/C8/C9/C11；0.5 **HOLD**。

## 1. 冻结原因

人裁定：人类 KP 切分不可靠、培训成本巨大、最终呈现面向人；C0 v1 的 gold KP/人类 IAA 路线不成立。A/B 独立提案 + SE 校核后，amendment 把语料从“标注答案”改为“评测仪器”：

- KP/SectionUnit 为导航/检索候选，不要求唯一真值；
- 人只判问题→证据（answer/citation/no-answer）与呈现 A/B；
- 语义边只作 `edge_candidate`，用 ablation 证明价值；
- 0.5 解禁改任务/呈现指标，不再用 IAA 达线。

## 2. 冻结内容（摘要）

| 项 | 冻结值 |
|---|---|
| Schema | SectionUnit/Candidate/EdgeCandidate/Accepted/Provenance，主外键/枚举/必填；edition 6 字段 canonical 公式；generator id/version/seed；2× canonical sha 相同 |
| MHA | 20 题（10 dev/10 test，含 4 no-answer）；非实现者出题；预注册；独立分层池 top-k10+随机10+邻接5+标题5/cap20/seed；unknown 不计 TP |
| Judge | H1 人本人 20 题，2–3h；H2 无 ⇒ self_consistency 仅诊断；κ 只报告；judge-sheet 行键/字段/missing |
| 指标 | R-RECALL@5≥0.80；A-ANSWER≥baseline；A-REF=1.0；no-answer 100%；U-ACCESS；T-FIND soft；GATE-RET 分型 |
| Ablation | full/no_semantic/structural_control/random_control/keyword_only；Δrecall/Δanswer≥0.05；paired bootstrap 95% CI 下界>0；控制不优于 full |
| 0.5 gate | C1–C5 硬门（C6 A/B soft）；graph 非 NA + ablation 通过；C3 无数值=`UNVERIFIABLE` 不算 PASS |
| 语义边来源 | 隔离 Tier-A 副本 `artifacts/corpus/pilot/harness-kb/<edition>/`；`pilot_harness=true`；不写用户库/产品路径；源库 sha 零变化 |
| S9 | `file+section_id` join，不扩 candidate kind；accepted 非事实 |
| 人类 | H1=人本人；20% self-consistency 仅诊断；人时 2–3h |

## 3. 机检/证据

- A/B 提案、异议、SE 校核、Lead D1–D3 裁决；
- 10 类最小工具尚未实现（C0a-2）；本冻结只冻结规格；
- 0.5 仍 HOLD；pilot 未完成前不重跑 GATE-RET。

## 4. 未关闭

- C0a-2 工具实现；
- judge 包/盲判/人 2–3h；
- pilot harness 运行与 ablation；
- C11 六条件 gate 实现；
- 0.5 正式发布另走版本计划。

## 5. 变更控制

任何字段/公式/阈值/路径改动：修订本 amendment + 决策；不得静默改 C0 v1/S0–S10。
