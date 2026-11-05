# C0-AMENDMENT-1（evaluation-first 语料库设计 · 可冻结候选）

> **依据**：人裁 `dec-20261105-d3030e4c`（evaluation-first）；`C0-corpus-v1.md`（冻结 `080d0860…`）；A `7e5c9069…`、B `7ab055e9…`、异议 `9cc7924c…`、SE 校核 `6f9771a7…`。
> **状态**：**冻结候选**；只修订 C4/C5/C6/C7/C8/C9/C10/C11/C12 中与之冲突的表述；C1/C2/C3 与 C0 v1 不变。冻结后由 Lead 写 `C0-AMENDMENT-1-FREEZE-RECORD.md`。**0.5 继续 HOLD**。
> **边界**：本文件不写产品代码、不改 C0 v1/A/B、不 commit；所有 pilot 写入只发生在隔离 Tier-A 副本（`pilot_harness=true`）。

---

## 0. 不可协商的不变量

1. **evaluation-first**：不再把 KP span/边当唯一 gold，不要求 gold KP IAA；人类只做 **answer/citation/no-answer/section relevance** 锚点。
2. **人类 judge**：人本人（非实现者）判 20 题；20% 复核；κ/一致率只作**诊断**，不作 0.5 硬线。
3. **pilot-only harness**：语义边仅在隔离 Tier-A 副本的 pilot harness 生成；所有 sidecar 写只发生在该副本；用户库/产品路径零写入。
4. **accepted ≠ 事实**：`Accepted` 是评测标签；未经 S10 `propose_write→人工确认→产品 curation writer` 不得成为 S10 事实/sidecar。
5. **禁止**：合成数据、聚合掩盖、`NOT_APPLICABLE` 当 PASS、模型 judge 单独作 P0、test 调参、跨 edition 比较。

---

## 1. Schema / edition / 重建（闭合 SE G1）

### 1.1 通用编码与身份

- `canonical(x)` = UTF-8 字节，`json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",",":"))`。
- `sha256(x)` = 64 位小写 hex；`sha256_canonical(x)=sha256(canonical(x))`。
- 所有数组按主键**升序**；`evidence_refs` 按字符串排序；时间 `YYYY-MM-DDTHH:MM:SSZ`。
- ID 正则 `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`；sha 字段 `^[0-9a-f]{64}$`。
- **确定性 ID**（可重建的关键）：
  - `section_id = "sec_" + sha256_canonical({file,heading,line_start,line_end})[:16]`
  - `candidate_id = "cand_" + sha256_canonical({kind,file,line_start,line_end,structure_type,title})[:16]`
  - `edge_candidate_id = "ecand_" + sha256_canonical({source,target,type,contain_kind,label,direction})[:16]`
  - `accepted_id = "acc_" + sha256_canonical({target_kind,target_id,edition_sha256})[:16]`
  - `provenance_id = "prov_" + sha256_canonical({source_id,target_id,assertion_source,evidence_refs})[:16]`
- 同一 edition 内主键唯一；重复 ⇒ `DUPLICATE_ID`，整批拒绝（fail-closed）。

### 1.2 实体字段（必填 `*`；枚举固定；`?` 可空）

| 实体 | 字段 |
|---|---|
| **SectionUnit** | `schema_version* const "c0-amendment-1/v1"`, `section_id*`, `file*`(repo 相对), `heading*`, `line_start*`(int≥1), `line_end*`(≥start), `edition_sha256*`, `text_hash*`(sha), `parent_section?`(FK section_id) |
| **Candidate** | `candidate_id*`, `kind*∈{kp,section,paragraph,formula,example,table,edge}`, `source_span*{file*,line_start*,line_end*,anchor_id?,structure_type*∈{heading,paragraph,formula,example,table,list}}`, `title*`(≤200), `aliases*[]`, `summary?`(≤500), `parent_section?`(FK), `proposed_by*∈{structure,agent,retrieval}`, `confidence*`[0,1], `status*∈{candidate,accepted,rejected}`, `edition_sha256*`, `evidence_refs*[]`, `created_at*` |
| **EdgeCandidate** | `edge_candidate_id*`, `source_id*`(FK candidate), `target_id*`(FK candidate), `type*∈{contain,reference,extend}`, `contain_kind?∈{structural,semantic}`（type=contain 时必填）, `label?`（reference/extend 可 `semantic`；contain 不允许）, `direction*∈{source_to_target,both}`, `evidence_refs*[]`, `confidence*`[0,1], `status*∈{candidate,accepted,rejected}`, `edition_sha256*` |
| **Accepted** | `accepted_id*`, `target_kind*∈{candidate,edge_candidate}`, `target_id*`(FK 对应实体), `accepted_by*`, `accepted_at*`, `reason*`, `edition_sha256*`；唯一键 `(target_kind, target_id, edition_sha256)` |
| **Provenance** | `provenance_id*`, `source_id*`, `target_id?`, `assertion_source*∈{author,editor,agent,retrieval}`, `evidence_refs*[]`, `curated_by*`, `curated_at?`, `decision_id?`, `edition_sha256*` |

- Candidate `status=accepted` 必须存在唯一 `Accepted{target_kind:"candidate"}`；EdgeCandidate `status=accepted` 必须存在唯一 `Accepted{target_kind:"edge_candidate"}`；否则 `ACCEPTED_RECORD_MISSING`。
- EdgeCandidate `type=contain` 必须有 `contain_kind`；`label` 仅 reference/extend 可为 `semantic`；`both` 在评分时物化两条有向边（不写两份记录）。
- 外键必须指向同 edition 记录；跨 edition ⇒ `FOREIGN_KEY_EDITION_MISMATCH`。

### 1.3 edition 唯一公式（冻结）

```text
edition_sha256 = sha256(canonical({
  "schema_version": "c0-amendment-1/v1",
  "source_manifest_sha256": sha256(canonical(source_manifest)),
  "candidates_sha256": sha256(canonical({
      "section_units": section_units_sorted_by_section_id,
      "candidates": candidates_sorted_by_candidate_id,
      "edge_candidates": edge_candidates_sorted_by_edge_candidate_id
  })),
  "accepted_sha256": sha256(canonical(accepted_sorted_by_accepted_id)),
  "questions_sha256": sha256(canonical(MHA_20_document)),
  "evaluator_script_sha256": sha256(canonical(evaluator_manifest))
}))
```

- `source_manifest` = `{file,sha256,size}` 按 file 排序的数组；只含 Tier-A 源。
- `evaluator_manifest` = `{path,sha256,version}` 排序数组（评测脚本/工具/本文件 sha）。
- **不接受**以 mtime/时间戳/随机序作为 edition 输入。

### 1.4 候选生成器与 2× 重建

- `candidate_generation.json`（随候选集落盘）：
  `{generator_id*:"c0-candidate-builder", generator_version*:"1.0.0", generator_seed*: uint64, input_sha256*, output_sha256*, algorithm_id*:"section-structure-v1"}`
- 生成算法契约：输入 `section_units`（按 section_id 排序）；按 `file,line_start,line_end,structure_type` 生成候选；同 ID 冲突时保留 `structure_type` 优先级 `heading>formula>table>example>paragraph>list`；输出按 `candidate_id` 升序。
- **重建验收**：同一 edition + generator_id/version/seed 运行两次；`sha256_canonical(candidates_bundle)` **必须完全相同**（2× canonical sha 相同）。**Jaccard≥0.9 不接受**。
- Accepted 重建：`accepted.json` 只引用 candidate_id；候选集 sha 不一致 ⇒ edition 不匹配，拒绝加载。

### 1.5 JSON Schema 落盘

冻结实现必须落 `schemas/c0-amendment-1.schema.json`（draft 2020-12，`additionalProperties:false`），覆盖上述实体 + MHA + judge 行；`required` 精确等于上表 `*` 字段；枚举/正则/唯一键由 validator 执行。**schema sha 纳入 evaluator_manifest。**

---

## 2. MHA-20 / 预注册 / 独立分层池 / judge 表（闭合 G2）

### 2.1 MHA-20.json（20 题 pilot）

路径（规范，pilot 前冻结）：`docs/design/corpus-seminar/pilot/MHA-20.json`。
顶层：`{schema_version:"c0-amendment-1/v1", mha_version:"1.0.0", edition_sha256, prereg_sha256, questions:[20]}`；**恰好 20 题**，10 dev / 10 test；其中 **4 道 no-answer**（2 dev/2 test）；test 只跑一次。

每题字段：

| 字段 | 类型/约束 |
|---|---|
| `question_id*` | `q_` 前缀，唯一 |
| `question*` | 非空；不得直接复制源文完整句（防字面匹配） |
| `type*` | `fact/definition/procedure/comparison/multi-hop/no-answer` |
| `required_facts*` | 1–5 个字符串（答案必须包含的要点） |
| `acceptable_sections*` | 1–3 个 `{section_id* FK, grade* 0–3}`；grade≥2 为 relevant；按 section_id 排序 |
| `reference_answer*` | 1–3 句，来自源文/可复核 |
| `citation_required*` | bool |
| `no_answer*` | bool（与 type=no-answer 一致） |
| `held_out*` | `dev/test` |
| `author*` | 非实现者 ID |
| `prereg_version*` | 与 preregistration 对应 |

- `author` 不得在 `implementer_ids`（预注册中列出）内；test 题不得进入 prompt/调参/训练。
- 题集 sha = `sha256_canonical(MHA_20_document)`，写入 prereg 与 edition。

### 2.2 preregistration.json

路径：`docs/design/corpus-seminar/pilot/preregistration.json`（冻结后只读；pilot 运行写副本到 `artifacts/corpus/pilot/preregistration.json`，sha 必须相同）。

字段：
```
{schema_version, amendment_sha256, decision_id,
 source_manifest_sha256, mha_sha256, questions_count:20,
 dev_test_split:{dev:10,test:10}, no_answer_count:4,
 pool:{algorithm_version,seed,top_k:10,random_n:10,adjacency_n:5,title_n:5,cap_per_question:20,strata:[]},
 metrics:{p0:[...],soft:[...]},
 ablation:{variants:[...],delta_recall_min:0.05,delta_answer_min:0.05,ci:"bootstrap-95-percentile",resamples:10000,seed:uint64,
           structural_not_better_than_full:true, random_not_better_than_full:true},
 human:{judge_id, review_fraction:0.20, review_count:4, time_budget_min:120, time_budget_max:180},
 falsifiers:[...],
 created_at, prereg_sha256?}
```
- **必须早于**候选/题/池生成冻结；任何修改 ⇒ 新 amendment + 新 edition。

### 2.3 独立分层池算法（冻结）

对每题（`seed` 全局 uint64）：
1. **系统 top-k**：`k=10`，来自 S9 检索（仅 SectionUnit，见 §5）；
2. **随机**：`random.Random(seed + int(question_id_suffix))` 从 edition 全部 SectionUnit 抽 10；
3. **邻接**：acceptable_sections 的前/后各 2 个相邻 section，最多 5；
4. **标题**：heading token 与问题 token 有重叠的 section，最多 5；
5. 去重（section_id）；按 `(stratum, -retrieval_score, section_id)` 排序；每问题上限 20；至少保留 4 个负例（grade=0）。
- 记录 `pool/<question_id>.json`：`{question_id,seed,counts:{top_k,random,adjacency,title},candidate_section_ids[]}`。
- **unknown 规则**：未 judge 的 section 为 `unknown`；**不计 TP**；R-RECALL 只在 judged relevant 上算，另报 pool coverage（judged/total）。
- 分层配额：按 `chapter × question_type × difficulty` 预注册；每层至少 1 题；不得只覆盖 top-k。

### 2.4 judge 表 schema

路径：`artifacts/corpus/pilot/judge/judge-sheet.jsonl`（一行一判断）；审查包 `artifacts/corpus/pilot/judge/judge-pack.json`。
行键：`(question_id, section_id, judge_id, round)` 唯一；`round∈{1,2,3}`（1 primary、2 review、3 adjudication）。
字段：
```
question_id*, section_id*, judge_id*, round*, role*∈{judge,reviewer,adjudicator},
answer_correct?∈{correct,partial,incorrect},
citation_support?∈{supported,partial,unsupported},
abstained? bool, time_s? number, conflict? bool,
adjudication?∈{accept_primary,overturn,no_decision},
rationale_sha? sha256（只存 hash，不存原文/PII）,
missing* bool（显式缺失；true 时 answer/citation 可为 null）
```
- 主判：20 题全判；复核：**4 题（20%）**由第二 reviewer 独立判；冲突由 adjudicator 裁；κ/一致率只诊断。
- 缺行/缺失必须 `missing=true`，不得默认 correct。

---

## 3. 指标 / 消融 / 统计（闭合 G3）

### 3.1 R-RECALL@5（P0）

- 第 q 题 relevant = `{section_id | grade≥2}`；`top5_q` = 检索 top-5 candidate 映射后的 section_id（映射见 §5）。
- `recall_q = |top5_q ∩ relevant_q| / |relevant_q|`；no-answer 题不计入 recall 分母。
- `R-RECALL@5 = mean_q recall_q`；只对 20 题中非 no-answer 题求均值。
- `unknown`/未判 section 不计 TP；若 `top5_q` 含无法映射的候选，不计 TP（不得默认命中）。
- **pool coverage** 单独报告（judged sections / pool sections）；未覆盖不能宣称全 qrels。

### 3.2 其他指标

| 指标 | 定义 | 类型 |
|---|---|---|
| `R-NDCG@5` | 以 acceptable_sections grade 0–3 为 gain 的 NDCG@5；unknown 不计 | soft |
| `A-ANSWER` | 人判 rubric：correct=1.0 / partial=0.5 / incorrect=0；主判均值；冲突按 adjudication | **P0**：≥0.80 且 ≥预注册 baseline（同题/同 edition 的旧呈现） |
| `A-REF` | 引用支持：supported=1 / partial=0.5 / unsupported=0；`A-REF = sum(support)/N_citation_required` | **P0**：=1.0（partial 不算通过） |
| `U-ACCESS` | 8 项检查：键盘 tab 顺序、焦点可见、无键盘陷阱、aria-label/role、可读名称、对比度 AA、reduced-motion、屏幕阅读器名称；每项 0/1，`U-ACCESS=通过数/8` | **P0**：=1.0；无法运行 ⇒ `UNVERIFIABLE`，不算通过 |
| `T-FIND` | A/B 配对会话找到答案的中位时间 | **soft**（仅报告） |
| `P-PREF`/`A-ITER/TOK`/`S-SEM` | A/B 偏好/迭代/边增益 | soft（方向） |

### 3.3 edge ablation（P0 方向）

- 变体（同题/同 edition/同节点/同 lexical index）：
  1. `full`：全部 semantic edge；
  2. `no_semantic`：移除全部 semantic edge，保留结构/引用边与 lexical；
  3. `structural_control`：semantic 边替换为同数量结构边；
  4. `random_control`：端点随机置换（同数量/同度分布，seed 固定）；
  5. `keyword_only`：无 graph 分量。
- `ablation.json` 记录每个 variant 的 `R-RECALL@5/A-ANSWER/A-REF`、per-question、edition、seed、2× sha。
- **P0 方向判据**（预注册数值）：
  - `Δrecall = full.R-RECALL@5 − no_semantic.R-RECALL@5 ≥ 0.05`；
  - `Δanswer = full.A-ANSWER − no_semantic.A-ANSWER ≥ 0.05`；
  - 两者 95% bootstrap percentile CI（10,000 次，按 question 配对，seed 固定）下界 **>0**；
  - `full.R-RECALL@5 ≥ structural_control/random_control`（点估计；控制不得优于 full）；
  - 任一不满足 ⇒ graph 无贡献，0.5 不解禁（或明确“只上检索、不上 graph”，需 Lead 裁决）。
- 缺数值效应量/CI ⇒ 条件③ `UNVERIFIABLE`，不得判 PASS。

### 3.4 power_ci.py 规格

输入：`ablation.json`（per-question 配对）；输出 `metrics.json`：
`{n_questions, delta_recall, delta_answer, ci_recall:{low,high,level:0.95}, ci_answer:..., resamples:10000, seed, mde, method:"bootstrap-percentile-paired"}`。
- 20 题只作 pilot；报告 CI 宽度与 MDE；不把 p 值/单点当结论。

---

## 4. 六条件 gate（闭合 G4）

路径：`scripts/verify/corpus/c0_gate_amendment.py`（C0a-2 实现，本次只冻结规格）。

```bash
python scripts/verify/corpus/c0_gate_amendment.py \
  --mha docs/design/corpus-seminar/pilot/MHA-20.json \
  --answers artifacts/corpus/pilot/judge/judge-sheet.jsonl \
  --qrels artifacts/corpus/pilot/pool/section-qrels.json \
  --ablation artifacts/corpus/pilot/ablation/ablation.json \
  --metrics artifacts/corpus/pilot/ablation/metrics.json \
  --edition artifacts/corpus/pilot/edition.json \
  --out artifacts/agent/verify/corpus/C0-AMENDMENT-1-GATE.json
```

输出：`{conditions:{c1..c6:{status:PASS|FAIL|UNVERIFIABLE,evidence,value}}, overall, exit_code, json_sha256}`。
- 条件：
  - **C1 MHA**：A-ANSWER≥0.80 且≥baseline；A-REF=1.0；no-answer 正确率=100%。
  - **C2 section**：R-RECALL@5≥0.80；weighted κ **只报告/诊断，不作硬门**；NA/unknown 不算 PASS。
  - **C3 ablation**：§3.3 数值判据全部满足；缺效应量/CI ⇒ `UNVERIFIABLE`。
  - **C4 无写**：`pilot_harness=true`；源库 sha 前后一致；无用户/产品 `.memoria` 写；无 sidecar 越界。
  - **C5 determinism**：同 edition 2× metrics sha 相同。
  - **C6 A/B soft**：盲/随机/同 UI 报告存在 ⇒ `PASS`；预注册跳过 ⇒ `NOT_RUN`；缺失 ⇒ `UNVERIFIABLE`。**C6 只报告，不阻断**（soft 不冒充 P0）。
- `UNVERIFIABLE` 不得算 PASS；`overall=PASS` 仅当 **C1–C5 全 PASS**（C6 为 soft 记录，不参与 overall）；exit 0/1/2。

---

## 5. S9 / S10 / pilot harness（闭合 G5）

### 5.1 S9 join（不扩 kind）

- **不改 S9 candidate kinds**（仍是 `kp/cluster/edge/file/anchor`）。
- SectionUnit 映射：`(file, line_start, line_end)` 与检索候选的 file/range 相交 ⇒ 映射到 `section_id`；落 `artifacts/corpus/pilot/section-join.json`：`{candidate_ref, section_id, basis:"file+range", edition_sha256}`。
- 评价 `top5_q` 由映射得到；无法映射的候选不计 TP（unknown）。
- SectionUnit 的 `section_id` 只存在于评测层与 join 文件，**不进入 S9 `candidate_ref`**；若未来要 S9 原生 section 候选，须 S9 修订。

### 5.2 accepted 非事实

- `Accepted` 只表示“评测采用该候选”，不写 sidecar、不写 `.memoria` 事实源、不调用产品 curation writer；不得作为 S10 事实。
- 若要把 accepted 变 S10 KP/边：另走 `S10 propose_write → 人工确认 → 产品 curation writer → sidecar`；pilot 不做。

### 5.3 pilot-only harness（人裁方案）

- 允许在**隔离 Tier-A 副本** `artifacts/corpus/pilot/harness-kb/<edition>/` 生成 sidecar/语义边；此副本是 pilot 资产，**不是用户库/产品路径**。
- 所有 harness 产物必须带 `pilot_harness=true`、`source_sha256`、`edition_sha256`；harness 只读源教材，写只写副本。
- 完成后对源库做 D-3 前后 sha 比对：零变化；任何写入源库/产品路径 ⇒ C4 FAIL，pilot 作废。
- 0.5 仍 HOLD；pilot harness 不接入 0.5 产品，不改变 S10 写路径/错误码/契约。

### 5.4 S10 优先级

- S0 关系类型/E_sem/S10 `Q-EVIDENCE/Q-SEM-PURITY` 不变；pilot 的 semantic 边仍是候选/评测标签，不能宣称 S10 质量已验收。
- 0.5 解禁仍需 C11 六条件 + S10/0.5 各自决策；本 amendment 不解除 HOLD。

---

## 6. 人类 judge 流程（人本人）

- **角色**：`judge_id=H1`（人本人，非实现者）；**20 题**；预计 **2–3h**，记录 `time_s`。
- **复核**：4 题（20%）由 `H2` 独立复核（不同人）；若无 H2，`review_mode="self_consistency"`（H1 间隔重判），κ 只诊断，不得当独立 IAA。
- **流程**：
  1. 冻结 `preregistration.json` / `MHA-20.json` / edition；
  2. 生成盲判包（题 + 候选 section 片段，隐藏系统来源/排序）；
  3. H1 判 answer/citation/no-answer（judge-sheet round=1）；
  4. H2 复核 4 题（round=2）；冲突 → adjudicator（round=3）；
  5. 计算 A-ANSWER/A-REF/no-answer/κ（κ diagnostic）；
  6. 归档 judge-sheet + 实际工时 + 争议率；超 3h 缩题（记 `time_budget_exceeded=true`），不降 rubric。
- **κ**：answer/citation 用 Cohen κ（或加权 κ）；只报告 `kappa`/`agreement`/`n`/`missing`，**不设硬线**；争议率 >30% ⇒ 修题/候选后重跑，不增标注量。
- **judge 包路径**：`artifacts/corpus/pilot/judge/judge-pack.json`、`judge-sheet.jsonl`、`adjudication-log.jsonl`。

---

## 7. Falsifiers / 风险 / 工具清单

### 7.1 Falsifiers（任一成立 ⇒ 结果无效，不得解禁）

1. C3 ablation 不显著（Δ<0.05 或 CI 含 0）⇒ graph/语义边无贡献。
2. C1 人类 answer/citation 与模型/实现者自评一致率 <0.60，或 κ<0.4（诊断）⇒ 评测不可靠。
3. `keyword_only` 已达 R-RECALL@5≥0.80 且 graph 无增量 ⇒ SectionUnit/图无价值。
4. 题集泄漏（实现者出题/test 进 prompt/test 调参）⇒ 结果无效。
5. A/B 差异可由数据量/布局/学习效应解释 ⇒ 不是图谱收益。
6. 实际 ≤4h 只能做 10 题/1 人 ⇒ 功效不足，不能解禁 0.5。
7. 许可/Tier 不允许发布 MHA 源文/答案 ⇒ 交付不可发布。
8. 语义边只提升“引用存在”不提升 answer/citation ⇒ 边是装饰。
9. pool coverage <0.80 或 unknown 被计 TP ⇒ recall 不可信。
10. harness 写用户库/产品路径 ⇒ pilot 作废。

### 7.2 风险

许可/Tier 不变；PII/答案/引用也受 Tier/edition；20 题统计功效有限；单人类 judge 偏差；harness 与产品路径混淆；S10 未启用导致 semantic 边只在副本中；0.5 HOLD。

### 7.3 最小工具清单（C0a-2）

1. `amendment_schema.py` + `schemas/c0-amendment-1.schema.json`
2. `build_section_units.py` / `validate_section_units.py`
3. `build_candidates.py`（generator_id/version/seed；2× canonical sha）
4. `build_mha_questions.py` + `preregister.py`
5. `build_evidence_pool.py`（独立分层池；unknown/qrels）
6. `score_mha.py`（answer/citation/no-answer/κ）
7. `eval_section_recall.py`（SectionUnit join S9；R-RECALL@5/NDCG）
8. `run_edge_ablation.py`（5 variants；seed；2×）
9. `power_ci.py`（paired bootstrap/MDE）
10. `c0_gate_amendment.py`（C1–C6）

复用：`eval-retrieval.py`（L2）、`c0_gate_ret.py`（检索 P0）、`iaa_runner.py`/`make_iaa_report_v2.py`（仅低层一致性/裁决；MHA 需 adapter）。

---

## 8. 冻结门禁

1. 本 amendment 的 schema/公式/paths 被 Lead 接受；
2. SE 复核 §1–§7 字段/命令一致性；
3. Lead 独立机检（schema/edition/池/judge/ablation/gate/harness/S9/S10）；
4. 写 `C0-AMENDMENT-1-FREEZE-RECORD.md`（decision id、sha、范围、0.5 HOLD）；
5. 冻结后再建 C0a-2 工具任务；pilot 未完成前 0.5 不重跑。
