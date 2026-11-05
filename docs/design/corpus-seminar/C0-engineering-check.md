# C0a 工程校核报告（语料库设计 C 系列）

> **冻结候选**：`docs/design/corpus-seminar/C0-corpus-v1.md` sha256 `fa51fcdc2cb648f68073b6e43c9dd2ba36b66cbdc0821900e64c700c3bb521c3`（95 行）。
> **输入（只读）**：A-v2 `fc9a927a…`、B-v2 `125429dc…`、异议-v2 `ee01ef16…`、`C0-RULINGS.md`；`CHARTER.md`；上游 S0–S10。
> **执行者**：`graph-se-architect`（SE）· **日期**：2026-11-05（Asia/Shanghai）
> **边界**：未改 A/B/冻结稿；未写产品代码；未 commit；0.5 保持 HOLD。
> **结论**：**未达 C 系列冻结门禁（否）**。M-C0-1..11 PASS；**M-C0-12 FAIL**：38 个外部证据 URL 中 **30 个 HTTP 200+标题通过，8 个失败/被阻断（5 FAIL + 3 BLOCKED）**，未满足“全量核验/不得冒充”；其余 C0a（GATE-RET 契约、unitizing α、ER/DFD/ST、PARSE_OK）已完成。

---

## 1. M-C0-1..12 逐项

| M | 判据 | 判定 | 证据 |
|---|---|---|---|
| M-C0-1 | 来源/许可/Tier/隐私 | **PASS** | v1 C2：Tier A/B/C、逐文档 license/SPDX/redistribution/DB-right/fair-use/PII、Presidio+人工、NOTICE；Tier B 不进发布包/golden |
| M-C0-2 | 本体/关系/E_sem 可机检 | **PASS（C0a 补 schema）** | v1 C3 只用 S0 全类型 + SKOS 概念注释；C0a ER-12 补齐 `Concept/KP/Relation/EvidenceSpan/Annotation/Curation/Quality` 字段；`E_sem` 门槛=S10；新增类型须 S0/S1 修订 |
| M-C0-3 | KP 粒度/边界/嵌套 | **PASS** | v1 C4：单文件连续 span、1–3 句、单 section、不重叠；pilot 试命题级变体由 IAA 定；嵌套 future |
| M-C0-4 | 标注协议可执行 | **PASS** | v1 C5：30+ 正例/30+ 负例/20+ 边界例、三级裁决、培训/试标 20 项、改手册重标 |
| M-C0-5 | 边证据/方向/负例 | **PASS** | v1 C6：S0 三类型、方向 source→target / both 物化、双端/断言证据、置信三档、理由、负例单列；结构/引用不冒充 |
| M-C0-6 | 规模/采样/edition/成本 | **PASS（规划值；pilot 实测未验）** | v1 C7：1 章/50 KP/30 边/20 query；主集 10 章/500 KP/300 边/100 query；按章 dev/test；`edition=sha256(files+annotations+manual)`；预算 2 人×2 天≈32 人时，超预算缩规模不降质量 |
| M-C0-7 | IAA 分型/阈值/可执行 | **PASS（合成实现；真实标注待 pilot）** | v1 C8/R-C0-1：span unitizing α、类型/方向 κ、边 tuple-set F1；α/κ≥0.67、F1≥0.70；**C0a 实现 `unitizing_alpha.py` + 6 pytest（边界/重叠/缺失/样本量；完美=1、分歧<0.67）** |
| M-C0-8 | 评测分型/消融/禁聚合 | **PASS（契约）** | v1 C9：三层、GATE-RET 分型、graph 仅 semantic_edges>0 适用、0 命中 FAIL、NA 不算通过、消融/禁合成/禁聚合；C0a 产 `C0-GATE-RET.md` + 可执行 wrapper |
| M-C0-9 | 工具只读/版本/审计/UTF-8 | **PASS（设计）** | v1 C10：隔离副本、用户库只读、不写 sidecar、导出 JSONL/standoff/CoNLL-U/Croissant、schema/证据锚/许可/UTF-8 offset 校验、版本+审计；工具未集成属 pilot 实施 |
| M-C0-10 | S10/0.5 衔接 | **PASS** | v1 C11：agent 只 `propose_write`+evidence、人工确认、产品 curation writer apply、edition→S9 失效；0.5 重跑五条门槛与 R-C0-6 一致 |
| M-C0-11 | 交付/维护/数据卡 | **PASS** | v1 C12：语料快照+golden+手册+许可/NOTICE+Datasheet/Croissant+脚本+变更日志；owner/节奏/edition/废弃；非一次性 demo |
| M-C0-12 | URL 全量核验 + 图 PARSE_OK | **FAIL** | 图：PLAN 36 图 `PARSE_OK`（mermaid 11.16.0 sha `9198f632…`）；**URL：30/38 HTTP 200+标题，5 FAIL（DOI/ISO/LDC 403、EUR-Lex 202）+3 BLOCKED（CC×2、HF）**；未全量通过 |

---

## 2. C0a 交付物

### 2.1 URL 全量核验（FAIL）

- 文件：`docs/design/corpus-seminar/C0-URL-VERIFY.json`（sha256 `851a6fe2…`）。
- 方法：独立 HTTP GET（urllib；对证书链用 unverified TLS；浏览器 UA；HTML `<title>` 正则），**不把提案声称当核验**。
- 结果：38 个唯一 URL；**30 HTTP 200+标题 PASS；5 FAIL；3 BLOCKED**。
- 失败/阻断（需改正/删除/联网环境重跑）：
  1. `https://creativecommons.org/licenses/by/4.0/` — BLOCKED（连接重置）
  2. `https://creativecommons.org/licenses/by-nc/4.0/` — BLOCKED
  3. `https://doi.org/10.1080/19312450802458935` — HTTP 403
  4. `https://doi.org/10.1093/llc/8.4.243` — HTTP 403
  5. `https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32016R0679` — HTTP 202（挑战页，非可读 200）
  6. `https://huggingface.co/docs/hub/datasets-licensing` — BLOCKED（超时）
  7. `https://www.iso.org/standard/66777.html` — HTTP 403
  8. `https://www.ldc.upenn.edu/data` — HTTP 403
- 核心证据覆盖：A-v2 按 C1–C12 每项 ≥2 条通过（C1 3/3、C2 2/3、C3 2/2、C4 3/3、C5 3/3、C6 2/2、C7 3/3、C8 2/2、C9 2/2、C10 4/4、C11 3/3、C12 16/17）；**但“全量 URL”仍不满足**，不能宣称 URL 全核验。
- **最小修**：对 8 项二选一（a）用同主题、可 200+title 的官方替代 URL 并更新证据表；（b）从证据表删除并补足每项 ≥2。重跑生成新 JSON；若需法务/联网环境，交 Lead 执行。**不得把 403/202/超时写成 200。**

### 2.2 GATE-RET 可执行契约（PASS）

- 文件：`artifacts/agent/verify/graph/corpus/C0-GATE-RET.md`（sha256 `8dd3d528…`）。
- 唯一命令：`python scripts/verify/corpus/c0_gate_ret.py --kb <KB> --golden <golden> --out artifacts/agent/verify/graph/corpus/C0-GATE-RET.json`。
- 内部只调用既有 `scripts/verify/eval-retrieval.py`；产物 JSON 带 `json_sha256`（去 `json_sha256/generated_at/exit_code` 后 canonical sha）。
- P0：keyword/vector/hybrid 适用分型 + 2× determinism；graph 仅 `semantic_edges>0` 适用，**pilot 前 soft**（报告不阻断），pilot 后 `--hard-graph` 硬判；NA 不参与分母/不算 PASS；空候选 coverage=0、sem_purity=null。
- 实测：fixture exit 0（graph APPLICABLE/PASS soft）；真实库 exit 0（graph NOT_APPLICABLE，非 graph P0 PASS）；graph-only 失败 soft exit 0、`--hard-graph` exit 1；P0 失败 exit 1。

### 2.3 unitizing α 实现（PASS，合成 fixture）

- `scripts/verify/corpus/unitizing_alpha.py`：unitizing α + observed/expected/boundary_f1/missing；缺失段不默认 0；样本不足 alpha=null；同标注者重叠 fail-closed。
- `tests/corpus/test_unitizing_alpha.py`：**6 passed**（完美=1.0；标签分歧<0.67；边界移位 boundary_f1<1；缺失 alpha=null；<2 标注者/全空/重叠报错；CLI self-test 绿+红）。
- 不碰用户库；无真实标注数据（pilot 前只验算法）。

### 2.4 标注 schema/工具状态图（PASS）

- `ENGINEERING-PLAN.md`（sha `a032c67a…`，**36 图**，mermaid 11.16.0 `9198f632…`，`failedBlocks=0`）：
  - §1.18 **ER-12**：SOURCE_DOCUMENT/LICENSE/CONCEPT/KNOWLEDGE_POINT/RELATION/EVIDENCE_SPAN/ANNOTATION/ADJUDICATION/GOLDEN_ITEM/QUALITY_REPORT；
  - §2.17 **DF-12**：来源→许可/隐私→隔离副本→标注→IAA→裁决→golden→GATE-RET→S10 propose→人工确认→curation→edition→0.5 重跑；
  - §3.15 **ST-12**：Draft→Annotating→Review→Conflict/Adjudicated→Frozen（+ Withdraw）。
- 与 v1 C0a §3 的状态名一致（draft/annotating/review/conflict/adjudicated/frozen）。

---

## 3. 与上游一致性

| 上游 | C0 落点 | 判定 |
|---|---|---|
| S0 `E_relation_min` | C3/C6 全类型、contain_kind、direction both | **一致** |
| S10 KP/边/E_sem/propose_write | C3/C4/C6/C11 同名同义；agent 只提案 | **一致** |
| S9 GATE-RET 分型/NA | C9/C0a 契约：NA 不算 PASS、禁止聚合掩盖 | **一致** |
| S8 DoD/G6/G7 | pilot 重跑门槛/Q-* | **一致** |
| S6 单一真源/路径/D-3 | C10 只读隔离、不写 sidecar；C2 PII | **一致** |

---

## 4. 未关闭项（O-C0-1..5）

| # | 项 | 归属 | 建议 |
|---|---|---|---|
| O-C0-1 | 8 个 URL FAIL/BLOCKED | C0a→Lead/联网环境 | 改正/删除后重跑；不冒充 |
| O-C0-2 | 真实标注数据 IAA/INCEpTION 导出 UTF-8 offset | pilot | 用 unitizing_alpha 跑 pilot |
| O-C0-3 | 许可/教材实际锁定（OpenStax 候选） | pilot/法务 | 逐文档核验；Tier B 不进发布 |
| O-C0-4 | 成本 32 人时/主集规模 | pilot | 记录实际工时，超预算缩规模不降质量 |
| O-C0-5 | graph soft→hard 切换阈值 | pilot 后 | 按 C0-GATE-RET §4 门槛；Lead 决策 |

---

## 5. C 系列冻结工程门禁判定

**否**：M-C0-1..11 PASS；**M-C0-12 FAIL（URL 8/38 未通过）**。修 O-C0-1 后复跑 M-C0-12 即可转「是」；其余工程项（GATE-RET 契约/α/ER/DFD/ST/PARSE_OK）已就绪。

---

## 6. 边界

未改 `C0-corpus-v1.md`/A/B/异议/裁决；未写产品代码；未发布 0.5；未 commit。所有核验产物在 `docs/design/corpus-seminar/`、`scripts/verify/corpus/`、`tests/corpus/`、`artifacts/agent/verify/graph/corpus/`。
