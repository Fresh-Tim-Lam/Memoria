# C0-AMENDMENT-1 工程校核（evaluation-first）

> **对象**：C0 修订 A（`7e5c9069…`，21,085 B）、B（`7ab055e9…`，19,007 B）、异议（`9cc7924c…`，11,785 B）；Lead 拟采 **B 的 P0 加固 + A 的轻量**。
> **基线**：`C0-corpus-v1.md`（冻结，`080d0860…`）、`C0-RULINGS.md`、`C0-engineering-check.md`、`C0-GATE-RET.md`、`scripts/verify/corpus/unitizing_alpha.py`、`eval-retrieval.py`、`c0_gate_ret.py`；S0–S10 冻结；0.5 HOLD。
> **执行者**：`graph-se-architect`（SE）· **日期**：2026-11-05
> **边界**：未改 A/B/C0/冻结稿；未写产品代码；未 commit。
> **结论**：**需澄清（暂不可直接冻结）**。方向（evaluation-first、B 的 P0 加固）可工程化，且有 2 项 PASS、1 项有条件 PASS；但 **C4 schema/edition/候选重建、C5 池与 judge 表、C9 指标/消融/统计、C11 六条件可机检、S9/S10 衔接** 仍有硬缺口。补齐 §3 的 6 项最小定义后可冻结。

---

## 1. 逐项结论

| # | 校核项 | 判定 | 理由（证据） |
|---|---|---|---|
| **A1** | C4 SectionUnit/candidate 字段可机检 | **需澄清** | B 给 SectionUnit 字段（B:51–54）；A 给 CANDIDATE/ACCEPTED/EDGE_CANDIDATE/PROVENANCE（A:226–236）；但**无统一 JSON schema/枚举/必填/唯一键**，candidate 与 SectionUnit 主键/外键关系未冻结；`status`/`kind` 枚举分散 |
| **A2** | edition 公式 | **需澄清** | A:239 仅写 `sha256(源+候选+accepted+问题+脚本)`；**无 canonical 序列化、排序、manifest 字段、脚本版本**；不同实现不可复算 |
| **A3** | 候选可重建 | **需澄清（偏 FAIL）** | A:37 只要求“同 edition 两次 Jaccard≥0.9”，**不是精确重建**；无生成器 id/版本/seed/canonical 候选 sha；ACCEPTED 也须可复建 |
| **A4** | C5 20–25 题/非实现者/预注册/独立分层池 | **需澄清** | B:75–83 有题字段与出题人独立；**无预注册文件 schema/path**；A:63 只写 top1/top3/随机负例；B:246 有 `section-qrels` 但**无池化算法/seed/分层配额/unknown 规则**；Lead 的“系统 top-k+随机/邻接/标题；unknown 不计 TP”未落入提案 |
| **A5** | judge 表结构 | **需澄清** | B:83 只列 `answer_correct/citation_supported/abstained/time`；**无表 schema/行键/职业/裁决字段/缺失处理**；A 的 judge 只判 `contains_answer`，与 Lead 的 answer/citation/no-answer 合成不一致 |
| **A6** | C8 人类锚点/1+20%复核/4–6h | **有条件 PASS** | B:108–113 定义 answer/citation/no-answer、κ/一致率/裁决；20–25 题、1 章、rubric 预写时 **4–6h 可信（上限需计时）**；但 Lead 的“1 人+20% 复核”只能对 20% 估一致性，κ 置信区间很宽，需明确**仅诊断**；A 的 10%/≤4h 偏乐观（异议 P1-1） |
| **A7** | C9 指标可执行 | **需澄清（偏 FAIL）** | R-RECALL@5 分子/分母未定义（required_facts? acceptable_sections? unknown 处理）；A-ANSWER 的“≥基线”基线未定义；A-REF/U-ACCESS 无评分表/测试法；GATE-RET 可复用但 SectionUnit 不在 S9 candidate kind；**edge ablation 只有方向，无命令/runner/随机 seed/效应量**；T-FIND soft 可接受；统计功效/CI 只有“待验证”，无方法 |
| **A8** | C11 0.5 六条件可机检 | **需澄清** | ①MHA answer/citation/no-answer 可机检（需 scorer）；②section relevance κ+recall 缺 SectionUnit evaluator；③“达预注册效应量”无数值/CI，**不可机检**；④无写/⑤2× 可复用；⑥A/B soft PASS；整体不能仅凭现有 `c0_gate_ret.py` 判 six conditions |
| **A9** | 许可/Tier/不写用户库 | **PASS** | C2 Tier A/B/C 不变；Tier B 不进发布/golden；MHA/答案/引用也受 Tier/edition（B:225–229）；候选/标注只写隔离工作区，不写用户 sidecar |
| **A10** | 工具影响 | **PASS（清单）** | 见 §4：`eval-retrieval.py`/`c0_gate_ret.py` 可复用 L2；`iaa_runner.py`/`make_iaa_report_v2.py` 仅复用低层一致性/裁决，**不能直接算 MHA**；`unitizing_alpha.py` 对 MHA 非必需；需新增 8 类最小工具 |
| **A11** | S0–S10/0.5 冲突 | **需澄清（存在冲突）** | SectionUnit 不属于 S9 `candidate_ref.kind∈{kp,cluster,edge,file,anchor}`；`accepted` 与 S10 事实/sidecar 写路径关系未定义；C9 要求 graph 消融 P0，而 0.5 无 semantic 写路径、S10 尚未启用；C0 不能自行改变 S9/S10 |

---

## 2. 关键缺口与最小修（按阻塞排序）

### G1 C4 schema/edition/重建（A1–A3）

**问题**：字段文字可读，但不能直接生成 validator；edition 不可复算；candidate 只承诺 Jaccard。
**最小修（冻结前写进 C0a/AMENDMENT）**：

1. 冻结 JSON Schema（`amendment-schema/v1`）：
   - `SectionUnit{section_id PK, file, heading, line_start, line_end, edition_sha, text_hash, parent_section?}`
   - `Candidate{candidate_id PK, kind∈{kp,section,paragraph,formula,example,table,edge}, source_span{file,line_start,line_end,anchor_id,structure_type}, title, aliases[], summary?, parent_section, proposed_by∈{structure,agent,retrieval}, confidence[0,1], status∈{candidate,accepted,rejected}, edition, evidence_refs[], created_at}`
   - `EdgeCandidate{edge_candidate_id PK, source,target,type∈{contain,reference,extend},contain_kind?∈{structural,semantic},label?,direction∈{source_to_target,both},evidence_refs[],confidence,status,edition}`
   - `Accepted{accepted_id, candidate_id FK, accepted_by, accepted_at, reason, edition}`；`Provenance{...}`。
2. **edition 唯一公式**：
   `edition_sha256 = sha256(canonical({schema_version, source_manifest_sha256, candidates_sha256, accepted_sha256, questions_sha256, evaluator_script_sha256}))`；所有列表按主键排序、UTF-8、`sort_keys`；写入 manifest。
3. **精确重建**：生成器 `generator_id/version/seed` 固定；2× 生成 candidate 集 `sha256(canonical(sorted candidates))` 必须相同（不是 Jaccard 0.9）；accepted 由主键 + edition 重建。

### G2 C5 池/题/judge 表（A4–A5）

**问题**：Lead 的独立分层池、unknown 规则、judge 表结构未在 A/B 中冻结。
**最小修**：

1. `MHA-20.json` schema：`question_id, question, type∈{fact,definition,procedure,comparison,multi-hop,no-answer}, required_facts[], acceptable_sections[{section_id,grade 0–3}], reference_answer, citation_required, no_answer, held_out∈{dev,test}, author(≠implementer), prereg_version`。
2. **独立分层池**：
   - 每层配额（章/题型/难度）；每问题候选 = 系统 top-k + 固定 seed 随机 + 邻接 section + 标题匹配；
   - 记录 seed、每层数量、池覆盖率；**unknown/未判 ≠ TP**；qrels 只由独立 judge 生成；
   - dev/test 按 **section** 隔离，test 只跑一次。
3. **judge 表**（CSV/JSONL schema）：
   `question_id, candidate_section_id, judge_id, round, answer_correct∈{correct,partial,incorrect}, citation_support∈{supported,partial,unsupported}, abstained(bool), time_s, conflict, adjudication, rationale_sha`；每行唯一键 `(question_id,section_id,judge_id,round)`；缺失显式 `missing=true`。
4. 预注册文件 `preregistration.json`：题量、分层、pool 算法/seed、指标、P0/soft、效应量、停止规则、falsifiers。

### G3 C9 指标/消融/统计（A7）

**问题**：指标定义与可执行 runner 不完整；edge ablation 是最关键 P0 方向，但没有数值效应量/命令。
**最小修**：

1. 定义 `R-RECALL@5 = (# 问题中 at least one acceptable_section in top-5) / N`；`unknown` 不计 TP；报告 pooling coverage。
2. `A-ANSWER`：correct/partial/incorrect rubric 明确定义，baseline 固定为同 edition 的旧呈现/关键词基线；`A-REF` 按 citation_support=supported 的比例；`U-ACCESS` 加可执行检查（keyboard/aria）。
3. **edge ablation 预注册 P0 方向**：
   - 变体：`full` vs `no_semantic_edge`（同节点/同 lexical index）vs `structural_edge` vs `random_edge`（固定 seed）vs `keyword_only`；
   - 指标：section recall@5、A-ANSWER、A-REF；同题/同 edition；2× 确定性；
   - 预注册效应量（如 Δrecall≥0.05、Δanswer≥0.05，或 MDE 按 20 题功效计算），bootstrap CI；full > no_sem 且 CI 不含 0，structural/random 不优于 full，否则 0.5 不解禁。
4. 新增 `power_ci.py`（bootstrap/MDE）并报告样本量；T-FIND 保持 soft。

### G4 C11 六条件可机检（A8）

在 `c0_gate_ret.py` 之外新增 `c0_gate_amendment.py`，读取：
`MHA-answers.csv`、`section-qrels.json`、`ablation.json`、`metrics.json`、edition manifest、write-guard 结果；逐条输出 PASS/FAIL + 证据路径 + exit；其中条件③需先冻结效应量数值（G3），否则只能 `SOFT/UNVERIFIABLE`，不能算通过。

### G5 S9/S10 衔接冲突（A11）

- **S9**：`SectionUnit` 不能直接作为 `candidate_ref`（S9 固定 kinds）；必须映射（如 `file:...` + section metadata）或提出 S9 修订，C0 不能单方面扩展。评测层可用 SectionUnit，但检索候选/排序仍用 S9 candidate；两者需明确 join key。
- **S10**：`accepted` 只是评测标签，**不是事实**；若要变成 S10 KP/语义边，必须走 `propose_write → 人工确认 → 产品 curation writer → sidecar`，C0 pilot 不写 sidecar。C0 的 edge ablation 需要 semantic 边，而 0.5/S10 尚未启用写路径 ⇒ pilot 必须用离线语料构建/产品 writer 才能产生可评测语义边；否则 graph 仍 NA，C11③不可能执行。**这是 0.5 HOLD 下的关键矛盾，需 Lead 裁决 pilot 语义边来源。**
- S10 的 Q-EVIDENCE/Q-SEM-PURITY/GATE-KP 仍适用；C0 evaluation-first 不能替代 S10 的写路径与质量门。

---

## 3. 可复用的现有工具

| 工具 | 复用程度 | 说明 |
|---|---|---|
| `scripts/verify/eval-retrieval.py` | **高（L2）** | 分型 retrieval、NA、typed gate 已可执行；需把 SectionUnit qrels 映射到候选（或新增 section scorer） |
| `scripts/verify/corpus/c0_gate_ret.py` | **高** | P0 keyword/vector/hybrid + graph soft；可作 C11 检索子条件 |
| `scripts/corpus/iaa_runner.py` | **中** | unitizing α/κ/tuple F1 可用于候选诊断；**不覆盖 MHA answer/citation** |
| `scripts/corpus/make_iaa_report_v2.py` | **中** | 裁决一致率/报告框架可参考；输入是 KP/边/裁决日志，需 adapter 才能用于 MHA |
| `scripts/verify/corpus/unitizing_alpha.py` | **低** | gold KP IAA 已降为诊断；MHA 不需要 span IAA |
| `scripts/corpus/make_spotcheck_pack.py`/`validate_human_labels.py` | **低–中** | 可用于证据包/人工裁决 UI 参考，需改 MHA 字段 |
| `scripts/benchmark/surface/run_interaction.py` | **低** | 不是 time-to-find A/B 工具；A/B 需新 harness |

## 4. 最小新增工具清单（不要求现在实现）

1. `scripts/corpus/amendment_schema.py` + `schemas/amendment-v1.json`：SectionUnit/Candidate/EdgeCandidate/Accepted/Provenance/Question/MHAAnswer/Judge。
2. `scripts/corpus/build_section_units.py`、`validate_section_units.py`（heading/range/text_hash/edition）。
3. `scripts/corpus/build_candidates.py`（确定性 `generator_id/version/seed`；canonical candidate sha）。
4. `scripts/corpus/build_mha_questions.py` + `preregister.py`（非实现者出题；MHA-20/prereg）。
5. `scripts/corpus/build_evidence_pool.py`（独立分层池；seed/配额/unknown；section-qrels）。
6. `scripts/corpus/score_mha.py`（answer/citation/no-answer/裁决；κ/agreement；CSV→metrics）。
7. `scripts/corpus/eval_section_recall.py`（SectionUnit recall/NDCG/MRR；join S9 candidates）。
8. `scripts/corpus/run_edge_ablation.py`（full/no-sem/structural/random/keyword-only；同节点/同 lexical；2×）。
9. `scripts/corpus/power_ci.py`（bootstrap/MDE/功效；A/B paired）。
10. `scripts/verify/corpus/c0_gate_amendment.py`（C11 六条件；输出证据/exit/JSON sha）。

---

## 5. 冻结建议

**需澄清，暂不可冻结**。最小冻结条件（全部写进 AMENDMENT/C0a）：

1. G1 JSON schema + edition canonical 公式 + 精确候选重建；
2. G2 MHA/pool/judge 表 schema + 预注册；
3. G3 指标公式 + edge ablation 效应量/命令 + power/CI；
4. G4 六条件 gate 的可执行件；
5. G5 S9 SectionUnit 映射与 S10 pilot 语义边来源的 Lead 裁决。

补齐后本 SE 可转 **可冻结**；0.5 继续 HOLD，pilot 不应在未补 G3/G5 前启动。

## 6. 与 0.5/S10 的风险

- 0.5 当前真实库 0 semantic edge ⇒ graph NA；C11③ ablation P0 在 0.5 上不可执行，必须先产 semantic 语料/离线评测。
- 若 C0 直接把 `accepted` 当事实或写 sidecar，违反 S10/D-3；必须保持 evaluation-only。
- 20–25 题 + 1+20% 复核的 κ 只能作诊断；不能把 20% 一致性写成全量人类 IAA。
