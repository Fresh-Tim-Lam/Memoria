# C0-AMENDMENT-1 SPEC-DIFF（相对 A/B/SE 的闭合表）

> **对象**：`C0-AMENDMENT-1.md` 可冻结候选 vs `C0-AMENDMENT-1-proposal-A.md`（`7e5c9069…`）、B（`7ab055e9…`）、异议（`9cc7924c…`）、SE 报告（`6f9771a7…`）。
> **原则**：人裁 evaluation-first；B 的 P0 加固 + A 的轻量；未改 A/B/C0 冻结稿；0.5 HOLD；本文件只做差异/闭合说明。

---

## 1. SE 5 组硬缺口闭合表

| SE 缺口 | 本 amendment 闭合位置 | 具体补了什么 | 状态 |
|---|---|---|---|
| **G1** C4 schema/edition/候选重建 | §1.1–§1.5 | 实体字段/枚举/必填/PK-FK；确定性 ID；edition 唯一公式（6 字段 canonical）；generator_id/version/seed；2× canonical sha 相同；accepted 重建；schema 落盘要求 | **CLOSED** |
| **G2** MHA/预注册/池/judge | §2.1–§2.4 | MHA-20 20 题/10dev-10test/4 no-answer 字段；prereg schema/path；独立分层池算法（top-k/随机/邻接/标题/配额/seed/unknown）；judge 表行键/字段/missing | **CLOSED** |
| **G3** 指标/消融/统计 | §3.1–§3.4 | R-RECALL@5 分子分母/unknown；A-ANSWER rubric+baseline；A-REF/U-ACCESS 定义；T-FIND soft；5 变体 ablation、Δ≥0.05、bootstrap CI>0、对照不优；power_ci 规格 | **CLOSED**（效应量数值需 Lead 追认，见 §3 D3） |
| **G4** 六条件 gate 可执行 | §4 | `c0_gate_amendment.py` 输入/输出/exit；C1–C6；C3 `UNVERIFIABLE` 不算 PASS；json_sha256 | **CLOSED** |
| **G5** S9/S10/harness | §5.1–§5.4 | file+section_id join（不扩 kind）；accepted 非事实；隔离 Tier-A 副本 + `pilot_harness=true`；D-3 前后 sha；S10 优先级/0.5 HOLD | **CLOSED**（harness owner/path 需 Lead 追认，见 §3 D1） |

---

## 2. A/B 裁决采纳与不采纳

| 议题 | A | B | 本 amendment 采纳 |
|---|---|---|---|
| C4 单元 | candidate unit（可重叠/嵌套；Jaccard≥0.9） | SectionUnit（section/1–3 段） | **B 的 SectionUnit 为评测单元 + A 的 Candidate 作为检索/导航候选**；拒绝 Jaccard 宽松重建，改精确 2× sha |
| C5 人类 | judge `contains_answer`，20–30 题，≤4h | MHA 20–25 题，answer/citation/no-answer，2 人，4–6h | **B 的 MHA + Lead 的 20 题/人本人 judge/20% 复核/2–3h**；补 pool/judge schema；A 的 ≤4h/仅相关性不采纳为 P0 |
| C8 质量 | 10% 双判、κ 可选、无硬线 | 2 人 answer/citation/κ，合格线 | **B 的 answer/citation/no-answer 锚点**；κ 按本 amendment 只作诊断（人裁）；1+20% 作为省时模式需标注 |
| C9 指标 | S-SEM soft，T-FIND P0 非劣 | edge ablation P0 方向；T-FIND soft | **B 的 edge ablation P0 方向 + T-FIND soft**；补 Δ/CI/对照；A 的 S-SEM soft 不作为 0.5 通过依据 |
| C11 gate | 五条件（无 ablation） | 六条件（含 ablation） | **B 的六条件 + 数值效应量/UNVERIFIABLE** |
| 工具 | 轻量 judge/AB | 较完整 RAG/MHA | 采用 §7.3 的 10 类最小工具；复用 `eval-retrieval.py`/`c0_gate_ret.py`；`make_iaa_report_v2.py` 仅低层一致性/裁决 |

---

## 3. 仍需 Lead 裁决的 3 点

| # | 决策点 | 本 amendment 的建议默认 | 为什么需要 Lead |
|---|---|---|---|
| **D1** | pilot harness 的语义边来源/所有权/路径 | `artifacts/corpus/pilot/harness-kb/<edition>/` 隔离副本；pilot-only harness；`pilot_harness=true`；只写副本；源库 sha 前后一致 | 涉及人裁“隔离 Tier-A 副本 + pilot-only harness”具体 owner、是否允许写副本 sidecar、与 S10/0.5 路径边界 |
| **D2** | 人类复核模式 | H1 人本人判 20 题；4 题（20%）由 H2 独立复核；无 H2 则 `self_consistency`，κ 仅诊断；时间 2–3h 上限 | 人裁“人本人当 judge + 20% 复核”需确认 H2 是否存在、self-consistency 是否可接受、时间预算 |
| **D3** | 消融效应量与 0.5 重跑权限 | Δrecall≥0.05、Δanswer≥0.05；paired bootstrap 95% CI 下界>0；structural/random 不优于 full；否则 0.5 不解禁 | 效应量/阈值属版本决策；Lead 需追认数值并确认“graph 非 NA + ablation 通过”作为 0.5 重跑硬条件 |

> 除 D1–D3 外，本 amendment 的字段/公式/命令/paths 已可交 C0a-2 建工具任务；冻结后 0.5 仍 HOLD，pilot 完成后才讨论重跑。

---

## 4. 与 C0 v1 的关系

- C1/C2/C3 与 C0 v1 不变（来源/许可/Tier、S0 关系类型/E_sem、PII）。
- C4/C5/C6/C7/C8/C9/C10/C11/C12 中与 evaluation-first 冲突的“gold KP/IAA/50 KP 双标”路径被本 amendment 替代；本 amendment 冻结时需对应重开/修订记录。
- 未修改 `C0-corpus-v1.md` 正文；本文件是独立 amendment，冻结后由 Lead 写 freeze record。
