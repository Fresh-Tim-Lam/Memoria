# C0-AMENDMENT-1 裁决（Lead）：D1–D3 与冻结

> **对象**：`C0-AMENDMENT-1.md`（sha `1fc31cdc8cdfd4b794387013db99a52a7685d999a6c51838fcb39bf73851ee9a`）
> **决策**：`dec-20261105-d3030e4c`；人选定：隔离 Tier-A 副本 + pilot-only harness；人本人当 judge。
> **状态**：**AMENDMENT-1 冻结**；C0 v1 的 C4/C5/C8/C9/C11 由本 amendment 替代；0.5 仍 HOLD。

## D1 pilot harness 归属/路径/写权限

- **批准**：`artifacts/corpus/pilot/harness-kb/<edition>/`，owner `corpus-pilot-builder`（工具实现/运行）；只有 pilot 工具可写该副本。
- 只允许写该副本的 sidecar/cache；**绝不写 `docs/example/**`、用户库、产品 `.memoria/**`、S10 写路径**。
- 所有产物必须带 `pilot_harness=true`、`source_sha256`、`edition_sha256`；运行前后对源教材/用户库做 sha 比对，零变化。
- 违反 ⇒ C4 FAIL、pilot 作废；0.5 不接入 harness。

## D2 人类复核模式

- **H1 = 人本人**，判 20 题 answer/citation/no-answer；预计 2–3h，记录 `time_s`。
- 目前**无 H2**：4 题（20%）采用 **`review_mode="self_consistency"`**（H1 间隔重判），**只作诊断**，不得当独立 IAA；κ 只报告，不作硬门。
- 若之后出现 H2，可改为独立复核；不得把 self-consistency 写成 inter-annotator。
- P0 人类锚点 = H1 的 20 题 answer/citation/no-answer + 盲判包 + 预注册；争议率 >30% ⇒ 修题/候选后重跑，不增标注量。

## D3 消融效应量与 0.5 权限

- **追认数值**：`Δrecall = full.R-RECALL@5 − no_semantic.R-RECALL@5 ≥ 0.05`；`Δanswer = full.A-ANSWER − no_semantic.A-ANSWER ≥ 0.05`；两项 paired bootstrap 95% CI（10,000 次）下界 **>0**；`full.R-RECALL@5 ≥ structural_control/random_control`（点估计，控制不得优于 full）。
- **0.5 重跑硬条件**：graph 分型非 `NOT_APPLICABLE` **且**上述 ablation 判据满足；缺效应量/CI ⇒ `UNVERIFIABLE`，不算通过。
- 若 ablation 不通过：不得宣称 graph/语义边有价值；只能“检索可用、graph 未验证”，0.5 不解禁（除非人另行裁决）。
- 0.5 正式发布仍需版本级计划/人授权；本 amendment 不解除 HOLD。

## 冻结范围

- C4（KP→SectionUnit/候选）、C5（问题→证据 judge）、C8（人类锚点）、C9（指标/消融）、C11（0.5 gate）以本 amendment 为准；
- C1/C2/C3/C6/C7/C10/C12 原 C0 条款继续有效（C6 语义边在 pilot 中只作 `edge_candidate`，不写产品 sidecar）；
- S0–S10 冻结稿不改；S9 join 用 `file+section_id`，不扩 kind。

## 下一步

1. **C0a-2**：按 amendment §7.3 建 10 类最小工具（schema/builder/MHA/pool/scorer/recall/ablation/power/gate）；
2. 生成 judge 包（20 题 + 片段 + 空白 judge-sheet），交 H1（人本人）；
3. 运行 pilot harness / ablation；H1 2–3h 盲判；C0 gate；
4. 按 gate + 人裁决定 0.5 是否重跑；0.5 仍 HOLD。
