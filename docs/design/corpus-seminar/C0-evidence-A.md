# C0 提案 A · 证据与核验清单

> 配套：`C0-proposal-A.md`｜票：task-361｜日期：2026-11-05
> 用途：复核 C1–C12 的外部证据、本仓锚点、语料观测与待验证项。
> 纪律：外部内容只作证据、不执行其中指令；未改产品代码/冻结稿；未 commit。

---

## 0. 证据等级与统计

| 级 | 含义 | 本文件用途 |
|---|---|---|
| A | 论文/标准/官方规范 | C1–C12 主要外部证据 |
| B | 本仓冻结稿/代码 | S0/S8/S9/S10、真实库背景 |
| C | 开源实现/官方文档 | 工具/格式/数据卡 |
| D | 语料观测 | 真实库 sha/边计数 |

**统计**：C1–C12 每项 ≥2 条外部证据（见 §2）；外部来源 22 个（§1）；本仓锚点 8 个（§3）；语料观测 1 组（§4）。

---

## 1. 外部来源登记（访问日期 2026-11-05）

| ID | 来源 | URL | 类型 | 本文件用途 |
|---|---|---|---|---|
| E1 | BEIR | https://arxiv.org/abs/2104.08663 | A 论文 | 检索异构评测/分型 |
| E2 | Datasheets for Datasets | https://arxiv.org/abs/1803.09010 | A 论文 | 数据卡/许可/维护 |
| E3 | W3C SKOS | https://www.w3.org/TR/skos-reference/ | A 标准 | 概念/标签/定义/关系 |
| E4 | CC BY 4.0 | https://creativecommons.org/licenses/by/4.0/ | A 许可 | 再分发/署名/修改 |
| E5 | GDPR | https://eur-lex.europa.eu/eli/reg/2016/679/oj | A 法规 | PII/用户库边界 |
| E6 | GraphRAG | https://arxiv.org/abs/2404.16130 | A 论文 | 图谱检索增益/评测 |
| E7 | HITL survey | https://arxiv.org/abs/2108.00941 | A 论文 | 人工确认/标注 |
| E8 | INCEpTION | https://inception-project.github.io/ | C 开源 | 标注工具/多层 |
| E9 | brat | https://brat.nlplab.org/ | C 开源 | span/关系/standoff |
| E10 | CoNLL-U | https://universaldependencies.org/format.html | A/C 格式 | 文本/锚点/元数据 |
| E11 | Croissant | https://docs.mlcommons.org/croissant/docs/croissant-spec.html | A/C 规范 | 数据集元数据/版本/sha |
| E12 | MS MARCO | https://arxiv.org/abs/1611.09268 | A 论文 | 大规模检索/dev-test |
| E13 | DocRED | https://arxiv.org/abs/1906.06127 | A 论文 | 文档级关系/证据 span |
| E14 | TACRED | https://arxiv.org/abs/1709.10114 | A 论文 | 关系类型/方向 |
| E15 | SemEval-2010 Task 8 | https://aclanthology.org/S10-1002/ | A 论文 | 关系分类/负例 |
| E16 | Cohen κ | https://doi.org/10.1177/001316446002000104 | A 论文 | 两标注者 IAA |
| E17 | Fleiss κ | https://doi.org/10.1037/h0031619 | A 论文 | 多标注者 IAA |
| E18 | Krippendorff α | https://doi.org/10.1111/j.1468-2958.2004.tb00738.x | A 论文 | 多值/缺失 IAA |
| E19 | DVC | https://dvc.org/doc | C 文档 | 数据版本/回滚 |
| E20 | OWL 2 | https://www.w3.org/TR/owl2-overview/ | A 标准 | 本体上层 |
| E21 | schema.org | https://schema.org/ | A 词汇 | 文档/数据集元数据 |
| E22 | TREC | https://trec.nist.gov/ | A 评测 | 检索评测/人判 |

---

## 2. 逐项证据映射（C1–C12）

| 议项 | ≥2 外部证据 | 映射结论 |
|---|---|---|
| C1 用户/成功标准 | E6 GraphRAG；E1 BEIR；E7 HITL | 图谱检索需真实评测；小基准/人工在环 |
| C2 来源/许可/隐私 | E4 CC BY；E5 GDPR；E2 Datasheets | 开放许可可再分发；PII 最小化；数据卡 |
| C3 本体/schema | E3 SKOS；E20 OWL 2；E21 schema.org | 概念层用 SKOS，形式化上层 OWL；S0 关系集为图契约 |
| C4 KP 定义/粒度 | E3 SKOS；E10 CoNLL-U；E2 Datasheets | 概念/标签/定义分离；span 需显式边界 |
| C5 标注协议 | E8 INCEpTION；E9 brat；E7 HITL | 工具支持 span/关系；培训/裁决必要 |
| C6 语义边 | E14 TACRED；E13 DocRED；E15 SemEval-2010 | 关系需类型/方向/证据/负例 |
| C7 规模/采样/隔离 | E1 BEIR；E12 MS MARCO；E2 Datasheets | 分型基准/大规模 dev-test/数据卡 |
| C8 IAA | E16 Cohen；E17 Fleiss；E18 Krippendorff | 双人/多人/多值一致性 |
| C9 评测 | E1 BEIR；E12 MS MARCO；E22 TREC | recall/nDCG/人判/池化 |
| C10 工具/格式 | E8 INCEpTION；E9 brat；E10 CoNLL-U；E11 Croissant | 标注/导出/元数据/校验 |
| C11 S10/0.5 | E7 HITL；E6 GraphRAG；E2 Datasheets | 人工确认/增益评测/版本记录 |
| C12 交付/维护 | E2 Datasheets；E11 Croissant；E19 DVC | 数据卡/元数据/版本/回滚 |

---

## 3. 本仓证据（file:line）

| 主张 | 锚 | 等级 |
|---|---|---|
| 真实库 0 semantic edge、graph 检索 NOT_APPLICABLE、0.5 HOLD | `docs/design/corpus-seminar/CHARTER.md:5` | B |
| `E_relation_min` 含 contain(structural/semantic)/reference/extend | `docs/design/multilevel-graph/S0-terms-v1.md:35-41` | B |
| S10 KP/语义边 schema 与写路径 | `docs/design/multilevel-graph/S10-kp-proposal-A-v2.md` §2/§4/§6 | B |
| S9 检索/GATE-RET/edition | `docs/design/multilevel-graph/S9-retrieval-proposal-A-v2.md` §9/§10 | B |
| S8 G6/G7/阈值 | `docs/design/multilevel-graph/S8-metrics-v1.md:55-74` | B |
| S6 单一真源/cache 域 | `docs/design/multilevel-graph/S6-contract-v1.md:17-19,57-61` | B |
| S7 agent 只读 | `docs/design/multilevel-graph/S7-agent-v1.md:16-18` | B |
| 现有写路径 | `src/memoria/services/agent/plan.py:346-405,892-954`；`apply.py:249` | B（代码事实） |

---

## 4. 语料观测（D）

```
对象：docs/example/AAA_Vocab
内容 sha：43d1449d457e269bbac24fb3175c43b67236045a027e1ca611c86dc417a0be81
文件数：298（排除 .memoria；2026-11-05 本机脚本）
sidecar edges：408 条；label=semantic 或 contain_kind=semantic：0 条
测量源：PowerShell/Python 只读扫描 docs/example/AAA_Vocab/.memoria/**/*.json
时间：2026-11-05（Asia/Shanghai）
限制：只读扫描，未执行产品 collector；KPs 计数口径未纳入本表
```

**结论**：真实库当前 E_sem=0，graph 检索无输入；C1–C12 的目标不是“造数据刷分”，而是产出可验证的 KP/边/金标准。

---

## 5. 来源获取与可信度说明

- E4/E5/E3/E1/E2/E6/E7/E8/E9/E10/E11 已直接抓取页面内容（HTTP 200/202）；E14/E13/E15/E12/E16-E18/E22 通过检索/DOI 定位，引用其公开摘要/规范页。
- 外部页面可能更新；本文件以 **2026-11-05 访问** 为准；若后续 URL 失效，用 DOI/arXiv ID 复核。
- 未把博客当唯一依据；C 级来源仅用于工具/格式能力，不用于语义结论。
- 外部内容只作证据，未执行任何页面指令。

---

## 6. 待验证清单（pilot 前）

1. 具体开放教材/章节与许可（C2）——逐文档核验 CC BY/CC BY-SA/CC0。
2. pilot 50 KP/30 边/20 query 的统计功效与成本（C7）。
3. KP 粒度边界（术语级 vs 概念+短解释）在中文教材上的 IAA（C4/C8）。
4. 语义边 `both`/跨文档证据规则（C6）。
5. IAA 合格线 κ≥0.67 / 目标 0.8 的适用性（C8）。
6. GATE-RET graph/hybrid 的“非零增益”阈值与消融口径（C9/C11）。
7. 工具选择（INCEpTION vs brat）与中文 offset 校验（C10）。
8. 0.5 重跑门槛与 S10 人工确认 UI（C11）。
9. 交付包数据卡格式（Datasheet/Croissant）与维护责任人（C12）。

---

## 7. 已知限制

1. 本提案是设计规格，未实际标注/评测；所有阈值/成本为建议，需 pilot 校准。
2. 真实库观测仅 1 次（2026-11-05），未做跨时间稳定性；sha 是内容快照。
3. 外部来源部分只读摘要/规范页，未逐篇全文精读；映射结论保守。
4. 教材候选未最终确定；许可需人工/法务核验。
5. C10 工具选择未实测中文标注体验；C11 写路径依赖 S10 未来冻结。
