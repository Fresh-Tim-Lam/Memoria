# PILOT-PLAN — 开放许可教材 1 章 pilot（单标注草案）

> **状态**：`single_annotator_draft`；**IAA 未做**（需独立第二标注者）；**0.5 保持 HOLD**；本包不发布、不写产品代码、不写用户库、不 commit。
> **手册版本**：**v1.1**（task-370 P0 修订；修订记录见 `MANUAL-REVISION.md`）。**注意**：A 的 50 KP/30 边按 v1.0 规则产出，v1.1 规则下 A 需复核/重标（P1，见 §7 U-10）。
> **依据**：`docs/design/corpus-seminar/C0-corpus-v1.md`（C1–C12 + R-C0-1..6）、`C0-RULINGS.md`、`C0-engineering-check.md`、`C0-URL-DISPOSITION.md`、C0-FREEZE-RECORD；task-369 agent 干跑 `artifacts/agent/verify/corpus/pilot/IAA-DRY-RUN.md`。
> **任务**：`task-368`（建包）+ `task-370`（P0 手册修订）；写域见对应任务。
> **日期**：2026-11-05（Asia/Shanghai）。

## 0. 一句话

用 **OpenStax《Introduction to Business》Chapter 1（CC BY 4.0，Tier A）** 的纯文本快照，产出 **50 KP / 30 语义边 / 14 负例 / 20 query** 的**单人标注草案**，并把「来源→快照→标注→校验→IAA 待办」做成可 2× 复现的工程包；IAA/golden 定稿/b>0.5 一律未做。

## 1. 交付物清单

| # | 产物 | 路径 | 说明 |
|---|---|---|---|
| 1 | 来源/许可记录 | `docs/design/corpus-seminar/pilot/SOURCE-LICENSE.md` | 书/章/URL/HTTP 200+标题/许可页/图表许可/NOTICE/淘汰记录/复验 |
| 2 | NOTICE | `artifacts/corpus/pilot/source/NOTICE.md` | 署名、修改标注、图表、无背书 |
| 3 | 正文快照 | `artifacts/corpus/pilot/source/chapter.txt` | UTF-8/LF；KP span 坐标系（code point，半开区间） |
| 4 | 原始页/证据 | `artifacts/corpus/pilot/source/raw/*.html`、`source/evidence/*` | 逐字节快照 + SPDX/ChooseALicense/仓库 LICENSE |
| 5 | 源清单 | `source/pages.json`、`sections.json`、`snapshot-meta.json`、`fetch-log.json`、`license-evidence.json` | 页/区间/sha/HTTP/标题/verified_at |
| 6 | 标注 spec（人工创作源） | `artifacts/corpus/pilot/annotations/pilot-spec.json` | 块号+句号 → span；唯一人工输入 |
| 7 | KP | `artifacts/corpus/pilot/annotations/kps.single.jsonl` | 50 条 |
| 8 | 语义边 | `artifacts/corpus/pilot/annotations/edges.single.jsonl` | 30 条（S0 三类型；E_sem） |
| 9 | 负例 | `artifacts/corpus/pilot/annotations/edges.negative.single.jsonl` | 14 条（单列） |
| 10 | query/golden | `docs/design/corpus-seminar/pilot/queries.json` | 20 条（4 型各 5；含 no-semantic 对照） |
| 11 | 标注包 manifest | `artifacts/corpus/pilot/annotations/annotations-manifest.json` | 计数/sha/edition |
| 12 | 标注手册 | `docs/design/corpus-seminar/pilot/ANNOTATION-MANUAL.md` | **v1.1**：去泄漏；S0 三类型操作定义；断言/方向/证据规则；concept_type 表+试标；30+ 正/30+ 负/20+ 边界 |
| 13 | 手册修订记录 | `docs/design/corpus-seminar/pilot/MANUAL-REVISION.md` | P0 逐条落实 + 变更表 + 剩余 P1（task-370） |
| 14 | IAA 工具包 | `artifacts/corpus/pilot/iaa/**` + `scripts/corpus/iaa_runner.py` | 第二标注者模板（`iaa/annotator-b/`）、候选对池、执行说明、有向池一致率 |
| 15 | 校验 | `scripts/corpus/validate_pilot.py` | schema/span/证据/许可/Tier/数量/2× 可复现 |
| 16 | 单测 | `tests/corpus/test_pilot_package.py`、`tests/corpus/test_manual_revision.py` | pytest（含负向破坏用例 + 手册 v1.1 防泄漏/规则检查） |
| 17 | 工时/成本 | `artifacts/corpus/pilot/WORKLOG.md` | 实测机器工时 + 待填人工工时 |
| 18 | 验证产物 | `artifacts/agent/verify/corpus/pilot/**` | 2× 校验报告、pytest、sha 清单、agent 干跑报告 |

## 2. 范围与规则

### 2.1 源规则（C2 / R-C0-3）
- 只选 **Tier A**（CC BY / CC BY-SA / CC0 / PD / 自著授权）；本包选 CC BY 4.0。
- Tier B（NC/ND/购买/不可再分发）与 Tier C（不明/禁止/无法核实）**不得进入本包/golden**；淘汰记录见 `SOURCE-LICENSE.md §5`。
- 逐文档记录 license/SPDX/redistribution/DB-right/fair-use/PII（`SOURCE-LICENSE.md §4`）。
- 发布前 NOTICE/许可清单；本包含 `source/NOTICE.md`。
- PII：轻量正则扫描 0 命中；**Presidio 未运行**（未关闭项）。

### 2.2 章节范围
- 纳入：Chapter 1 的 `1-introduction`、`1.1–1.8`、`1-key-terms`、`1-summary-of-learning-outcomes`（11 页，全部进入 `chapter.txt`）。
- KP 只从 **1.1–1.8 正文** 抽取；`intro`（案例叙事）、`key-terms`、`summary` 保留在快照中但**不作为 KP 源**（避免与正文定义重复；`key-terms` 可供第二标注者参考但不作为独立 KP）。
- 不纳入：`Concept Check`、`Ethics Activity`、`Working the Net`、`Critical Thinking Case`、`Preparing for Tomorrow's Workplace Skills`、`Hot Links`（练习/导流页，非断言性知识）。这些块仍在快照中（抽取完整性），但不在 KP/query/golden 中。
- 图片：不重分发图片文件；只保留 caption/credit 文本（图许可逐图见 caption，见 `SOURCE-LICENSE.md §1`）。

### 2.3 KP 规则（C4）
- KP = **单文件连续 span**（`chapter.txt` 中一段连续文本），默认 **1 概念 + 1–3 句解释**，**单 section**、**不重叠**、不嵌套（future）。
- `span` 坐标 = `chapter.txt` 解码后的 **Unicode code point 偏移**，左闭右开 `[start,end)`；文件 UTF-8 无 BOM、LF。
- 允许两种形态：① 段内句区间（默认）；② 相邻 block 组（如列表定义：lead-in + 列表项，仍为连续 span）。两种都必须在**单 section** 内。
- 字段（S10 对齐）：`id / file / spans[{start,end}] / name / name_zh / description / section_key / section_num / concept_type / granularity / evidence[{file,start,end,quote,quote_sha256}] / anchor / status / annotator / annotation_method / manual_version`。
- `name ≤120`、`description ≤500`；`status = single_annotator_draft`；`annotation_method` 明示 IAA 未做。
- 本 pilot 的 `granularity` 全部为 `concept_explanation`；**命题级变体未做**（C4 要求 pilot 试命题级，由 IAA 决定采用哪个——本包如实记为未做，见 §7 U-6）。

### 2.4 语义边规则（C6）
- 类型只用 S0 `E_relation_min`：`contain` / `reference` / `extend`；**三类型的操作定义/判据/方向/正负边界例见 `ANNOTATION-MANUAL.md` v1.1 §2**（v1.0 无定义，是 agent 干跑 8/30 类型分歧的根因）。
- `contain` 必须给 `contain_kind`，本包全部为 `semantic`。
- **E_sem 门槛**：`contain ∧ contain_kind=semantic`，或 `(reference|extend) ∧ label=semantic`；每条边 `e_sem=true`。
- 方向默认 `source→target`；`both` 必须显式且双向证据 → 本 pilot **0 条 both**（没有满足双向证据的对；不是遗漏，是证据门槛），见手册 v1.1 §2.7。
- 每条边：**双端证据 span + 断言证据 span**（三处 `quote_sha256` 可复核）、置信 `high/medium/low`、理由、`status`；断言 span 最低证据与证据来源范围见手册 v1.1 §2.5/§2.6。
- 负例**单列** `edges.negative.single.jsonl`（14 条，含 structural 冒充 semantic / 方向反 / 同类 sibling 误标 reference / 共现当边等）。
- 不允许结构边/引用边冒充语义边。

### 2.5 Query 规则（C7/C9）
- 20 条：keyword / vector / hybrid / graph **各 5 条**；graph 型必须引用语义边（`expected_edge_ids`）。
- **no-semantic 对照** ≥2：`control=true` + `control_kind="semantic_edges_not_required"`（本包 3 条）。
- `expected_kp_ids` 用 KP id；**不要求全部命中**（golden 允许部分命中，`q-hyb-03` 是显式部分命中案例）。
- dev/test：**pilot 仅 1 章，无法按章隔离**；按 query id 预分 14 dev / 6 test，仅用于流程演练，**不作为统计推断**（主集按章隔离）。该限制写入 `queries.json.dev_test_note`。
- 本包只做 golden 设计，**未跑 GATE-RET**（0.5 HOLD）。

### 2.6 Edition（C7）
```
edition = sha256( "corpus-pilot-edition/v1" + "\n" + chapter_sha256
                  + kps_sha + edges_sha + negative_sha + queries_sha + manual_version )
```
实际值见 `annotations-manifest.json` 的 `edition`（由 `make_annotations.py` 计算，`validate_pilot.py` 独立重算）。
**v1.1 注意**：手册已升 v1.1，但 `manual_version`/edition 重算需要重跑 `make_annotations.py`（`artifacts/corpus/pilot/annotations/**` 与 `scripts/corpus/make_annotations.py` 不在 task-370 写域）→ 列为 P1（§7 U-11）；当前 manifest 仍为 v1.0 口径，**不得宣称 edition 已对 v1.1 冻结**。

## 3. 复现流水线（2× 确定性）

所有步骤离线可复现（网络仅用于 §3.1 抓取；已抓取的 raw 已入库，后续步骤不需要网络）。

```powershell
# 3.1 抓取（已完成；复验时才需要网络，命令见 SOURCE-LICENSE.md §7）
#     产物: artifacts/corpus/pilot/source/raw/*.html + evidence/*
# 3.2 从抓取日志生成源清单（离线）
python scripts/corpus/make_source_manifests.py
# 3.3 从 raw HTML 生成确定性纯文本快照（离线）
python scripts/corpus/build_source_snapshot.py
# 3.4 从人工 spec 生成 KP/边/负例/query（离线）
python scripts/corpus/make_annotations.py build
# 3.5 生成 IAA 工具包（候选对池，固定 seed 368；B 模板见 iaa/annotator-b/）
python scripts/corpus/make_iaa_kit.py build
# 3.6 独立校验（含 2× 可复现：重跑 3.2/3.3/3.4 并逐字节比对）
python scripts/corpus/validate_pilot.py --json-out artifacts/agent/verify/corpus/pilot/validate.json
# 3.7 单测
python -m pytest tests/corpus -q
```

预期：3.6 exit 0（全部检查 PASS），3.7 全绿。若任一步失败：**不改数据凑绿**，先定位；失败必须可见（C0a 原则）。

## 4. 标注流程（两阶段；C5）

1. **KP 先行**：按 `ANNOTATION-MANUAL.md` 在 `chapter.txt` 上选 span（块号+句号），写 `pilot-spec.json`；`make_annotations.py` 解析为绝对 span。
2. **边随后**：在已冻结 KP 集上标 S0 语义边（双端 + 断言证据）；同时填负例。
3. **query/golden**：按 4 型写 query，expected 用 KP id；graph 型引边。
4. **自检**：`make_annotations.py build` → `validate_pilot.py` → pytest。
5. **第二标注者**：见 `iaa/README.md` v1.1（B 产物统一放 `artifacts/corpus/pilot/annotations/annotator-b/`；KP 独立标 span → unitizing α；边在无标签候选对池上有向标注 → tuple F1/有向池一致率）。
6. **裁决**：A/B/C 三级（A 标注者自决 / B 复核 / C Lead 终裁），记录在 `iaa/adjudication-log.template.jsonl`。
7. **改手册必须重标受影响样本**（C5）：v1.1 修订后，A 的 50 KP/30 边需按 v1.1 复核（P1，见 §7 U-10）。

## 5. 质量门（本 pilot 当前状态）

| 指标 | C8 合格线 | 当前状态 |
|---|---|---|
| KP span unitizing α（或 boundary F1） | ≥0.67（目标 0.8） | **未做（人类）**；agent 干跑 α=1.0 **不可解释**（手册 v1.0 泄漏导致虚高，见 `IAA-DRY-RUN.md`），v1.1 已去泄漏 |
| KP 类型/方向 Cohen/Fleiss κ | ≥0.67（目标 0.8） | **未做（人类）**；agent 干跑 κ=0.0 退化（A 48 concept+2 term vs B 50 concept），v1.1 补 concept_type 判定表 + raw agreement 报告 |
| 语义边 tuple-set F1 | ≥0.70（目标 0.80） | **未做（人类）**；agent 干跑 F1=0.60（8/30 类型分歧，S0 类型无定义），v1.1 补三类型操作定义 |
| 池一致率（有向） | 报告项（不设门槛） | **未做（人类）**；agent 干跑无向 κ=0.732，v1.1 改有向并单列方向反转 |
| 10% 抽检 + 裁决记录 | 必须 | **未做** |
| 2× 确定性 | 必须 | **已做**（`validate_pilot.py` repro 检查） |
| 许可/Tier/证据 | Tier A + 200+标题 | **已做**（见 `SOURCE-LICENSE.md`） |

**结论**：本包是 `single_annotator_draft`，**不满足 C8 达线条件**；agent 干跑数值不得作为达线证据；0.5 继续 HOLD。

## 6. 与 C0 条款映射

| C0 | 本包落点 |
|---|---|
| C1 用户/成功标准 | 本 PLAN §0/§5；pilot 流程可执行；三层成功标准中仅“标注质量”部分完成（单人）、检索/graph 未跑 |
| C2 来源/许可/隐私 | `SOURCE-LICENSE.md` + `fetch-log.json` + `NOTICE.md`；Tier A；PII 轻量扫描；Presidio 未跑 |
| C3 本体/关系 | KP/边 schema 与 S0 对齐；E_sem 门槛；无新类型 |
| C4 KP 粒度/边界 | 单文件连续 span、单 section、不重叠；命题级变体未做 |
| C5 标注协议 | `ANNOTATION-MANUAL.md` **v1.1**（去泄漏；S0 类型定义；断言/方向/证据规则；concept_type 表+试标；30+/30+/20+、A/B/C、培训/试标）；规则变更见 `MANUAL-REVISION.md` |
| C6 语义边 | 30 条、三类型、方向、双端+断言证据、置信、理由、负例单列、0 条 both 的证据理由 |
| C7 规模/采样/edition/成本 | 50/30/20；edition 公式与实现；`WORKLOG.md` 记录实测工时 |
| C8 质量/IAA | 单标注草案；IAA 工具包 + 阈值 + 报告模板（待执行） |
| C9 评测 | `queries.json` 4 型 + no-semantic 对照；dev/test 限制说明；**未跑 GATE-RET** |
| C10 工具/工作流 | 隔离副本、JSONL+offset、校验脚本、2× 复现、无用户库写入 |
| C11 S10/0.5 | 未启用 S10 写路径；未重跑 0.5；门槛写在本 PLAN §5 |
| C12 交付/维护 | 本 PLAN + manual + 许可/NOTICE + 数据卡位（未写 Datasheet/Croissant，未关闭项 U-7） |

## 7. 未关闭项

| # | 项 | 归属/建议 |
|---|---|---|
| U-1 | 上游 README 与 LICENSE/前言文案不一致 | 发布前法务/OpenStax 确认 |
| U-2 | Presidio 正式 PII 扫描未运行 | 装依赖后补跑，结果入 `artifacts/agent/verify/corpus/pilot/` |
| U-3 | CC 官方许可页本环境不可达 | 已用 SPDX/ChooseALicense/仓库 LICENSE 替代；未冒充 200 |
| U-4 | 中文语料/中文 UTF-8 偏移未验证 | 主集前补中文 pilot（C0 O-C0-2） |
| U-5 | IAA / 10% 抽检 / 裁决 | 需独立第二标注者（≥2 天成本，C7 预算内） |
| U-6 | 命题级变体（C4）未做 | pilot 下一轮补 20 项命题级子集，由 IAA 比较两种粒度 |
| U-7 | Datasheet / Croissant / Data Statement 未产出 | C12 交付包，发布前补 |
| U-8 | GATE-RET 未跑、graph 分型未评估 | 0.5 HOLD；IAA 达线后按 C0-GATE-RET 跑 |
| U-9 | dev/test 无法按章隔离（单章） | 主集按章隔离；pilot 内部分割仅演练 |
| U-10 | A 的 50 KP/30 边仍按 v1.0 规则产出 | v1.1 新增类型/断言/方向规则后，人类 IAA 前 A 必须复核/重标（写域外；需新任务） |
| U-11 | `manual_version`/edition 未随 v1.1 重算 | 重算需重跑 `make_annotations.py`（写域外）；当前 manifest 仍 v1.0 口径，不得宣称 edition 对 v1.1 冻结 |
| U-12 | `make_iaa_kit.py` 未同步 v1.1 模板/路径 | 生成器会覆盖 v1.1 模板登记；列为 P1（写域外），当前以 `iaa/README.md` v1.1 为准 |
| U-13 | B 文件合法性自检未入库 | dry-run 建议增加 span 越界/重叠/quote sha/端点检查；当前由 `iaa_runner.py` 做部分统计，完整 schema 校验列为 P1 |

## 8. 变更记录（v1.1 / task-370）

| 日期 | 变更 | 影响 |
|---|---|---|
| 2026-11-05 | 手册 v1.0 → **v1.1**：删除 §1.1 中 A 的 50 条逐条答案（防 α 泄漏）；补 S0 三类型操作定义与正/负/边界例；补断言 span 最低证据/证据来源/方向（含 both 与反向对）规则；修 P30 类"引语不在 span 内"矛盾；补 concept_type 判定表 + 试标 10 项；统一 B 路径协议为 `annotations/annotator-b/`；`iaa_runner.py` 池一致率改**有向**（+无向 legacy 对照 + 方向反转清单 + raw agreement/κ 退化标记） | 人类 IAA 前必须使用 v1.1；A 标签未改（P1 复核）；见 `MANUAL-REVISION.md` |
