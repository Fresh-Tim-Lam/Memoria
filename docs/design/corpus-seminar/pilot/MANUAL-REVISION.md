# MANUAL-REVISION — 标注手册 v1.0 → v1.1（task-370 P0 修订记录）

> **任务**：`task-370`（P0 手册修订）。
> **依据**：task-369 agent 干跑 `artifacts/agent/verify/corpus/pilot/IAA-DRY-RUN.md`：机制可跑但数值不可解释（α=1.0 由手册泄漏导致；边 tuple F1=0.60 主因 S0 三类型无操作定义；κ 退化）。
> **状态**：手册 v1.1 已交付；**IAA 仍未做**（本次修订**不产生**任何新 IAA 数值，也不把 agent 干跑当人类 IAA）。
> **未改声明**：A 的标签文件逐字节未改（`kps.single.jsonl` sha `5cf52ba8…`、`edges.single.jsonl` sha `95a020ed…`、`edges.negative.single.jsonl` sha `412dac8a…`）；C0/冻结稿未改；不写用户库；不 commit；task-369 的 B 干跑文件只读。

## 1. P0 逐条落实

| # | 干跑暴露的问题 | v1.1 处置 | 落点 | 机器验收 |
|---|---|---|---|---|
| **P0-1** | 手册 §1.1 逐条列出 A 的 50 KP 概念/句数/span 写法 → B 的 α 必然虚高（干跑 α=1.0） | **删除全部逐条答案**；改为「判定流程 + 粒度规则（R1–R6）+ 本章之外的合成教学示例」；明确“若看到 A 产物请退回” | `ANNOTATION-MANUAL.md` §1.1–§1.5 | `test_manual_has_no_a_unitization_leak`（手册不得出现 `kp-\d{3}`/`edge-\d{3}`；旧 P30 说明不得存在）；示例 32 正 / 32 负 / 22 边界 |
| **P0-2** | 手册只说“只允许 contain/reference/extend”，无判据/方向/边界；干跑 8/30 类型分歧全来自此 | 补 **S0 三类型操作定义**（判据/方向/典型动词/反例）+ **决策树**；每类 **6 正例 / 6 负例 / 4 边界例**；明确“整体-部分/子类型（contain）、度量-表示/影响-关联（reference）、因果-结果/派生-扩展（extend）”；补“一步推理/断言 span 最低证据”（high=直接断言；medium=一步推理/表格；两步以上→no_edge） | 手册 §2.0–§2.5 | `test_manual_s0_type_definitions_and_examples`（每类 ≥5/≥5/≥3）；`test_manual_assertion_evidence_and_direction_rules` |
| **P0-3** | 旧 P30 写“定义 + 引语（2 句）”，但引语实际在更后句 → 自相矛盾 | 删除旧 P30 逐条说明；新增 **R3 引语自洽规则**：描述中引用的引语必须落在 span 内；明确 **定义句 vs 定义句+机制句（至多 2 句、同一概念）** 的取舍 | 手册 §1.2 R2/R3 | `test_manual_p30_style_self_consistency_rule`（禁止旧“2 句 + 引语”表述） |
| **P0-4** | 断言 span 证据范围（表格/Summary/Key Terms 可用否）与 `direction=both`/反向端点对记法未定，A/B 门槛不一致 | 新增 **§2.6 证据来源范围表**：正文默认可用；表格仅辅助断言（≤medium）；Summary 仅佐证、不得唯一断言；Key Terms 不作 edge 断言；图注/出处不可。新增 **§2.7 方向规则**：反向端点对记 `direction: target->source`（不是 no_edge）；`both` 必须两条独立断言并物化两条有向 tuple；“反向负例”判 no_edge | 手册 §2.6/§2.7 | `test_manual_assertion_evidence_and_direction_rules` |
| **P0-5** | `concept_type` 有枚举无判定规则；A=48 concept+2 term vs B=50 concept → κ=0 退化 | 新增 **§1.6 判定表**（concept/term/mechanism/procedure/formula/example + 判定顺序）+ **试标 10 项（含答案，不计 IAA）**；明确“不确定填 concept + `type_uncertain=true`”；报告**同时给 raw agreement**，κ 退化必须标注、不得单独引用 | 手册 §1.6；`iaa_runner.py` 类型指标 | `test_manual_concept_type_table_and_trial`（CT1–CT10 恰好 10）；`test_type_raw_agreement_and_kappa_degenerate`；`test_type_uncertain_excluded_from_kappa` |
| **P0-6** | 路径协议不一致：`iaa/README.md` 要求 `iaa/*-second-annotator.jsonl`，干跑产物在 `annotations/annotator-b/*` | **统一为 `artifacts/corpus/pilot/annotations/annotator-b/`**（`kps.annotator-b.jsonl` + `pool-judgments.annotator-b.jsonl` + `adjudication-log.jsonl`）；新增 canonical 模板 `iaa/annotator-b/*.template.jsonl`；旧 `iaa/*-second-annotator.template.jsonl` 标废弃；`iaa_runner.py` 默认路径同步；`iaa-kit-manifest.json` 增 `canonical_b_dir`/`v11_files` | `iaa/README.md` v1.1、`iaa/annotator-b/`、`iaa-kit-manifest.json`、`iaa_runner.py` | `test_iaa_readme_path_protocol_unified`；`test_canonical_templates_exist_and_parse`；`test_iaa_runner_cli_defaults_point_to_annotator_b` |
| **P0-7** | 池一致率用**无向**端点集合，方向错误被吞（干跑无向 κ=0.732，反向对双计） | `iaa_runner.py` 池一致率改**有向为主**：`edge_pool_agreement_kappa`=有向；`edge_pool_agreement_kappa_undirected`=legacy 对照；新增 `edge_pool_direction_reversals` / `edge_pool_missing_judgments`；`directed_tuples()` 归一化 `target->source`/`both`；edge tuple F1 同步方向归一化；报告加 `edge_pool_agreement_note` 说明无向不可作门槛 | `scripts/corpus/iaa_runner.py`；`iaa/README.md` §4 | `test_directed_pool_agreement_detects_reversal`；`test_directed_tuples_normalization`；`test_pool_agreement_ignores_reverse_negatives_under_directed`；`iaa_runner.py self-test` 含有向自检 |

## 2. 变更表（v1.0 → v1.1）

| v1.0 章节/内容 | v1.1 处置 |
|---|---|
| §1.1 正例“30+，全部来自本包 50 KP”（含 kp 编号与句数） | **删除**；改为 §1.3“32 条合成教学示例（本章之外）”，不出现任何本语料 KP/边编号 |
| §1.2 负例 36 条（部分引用本语料具体块/section 与 A 的取舍） | 重写为 32 条**合成**非 KP 示例，只保留判据 |
| §1.3 边界例 25 条（含 kp 编号与具体 span 取舍） | 重写为 22 条合成边界例 + 裁决 |
| 无粒度规则 | 新增 §1.2 R1–R6（定义句 vs 机制句；引语自洽；block-group span；不重叠；正文优先） |
| 无 concept_type 规则 | 新增 §1.6 判定表 + 判定顺序 + `type_uncertain` + 试标 10 项 |
| §2“语义边判定”（只有判定顺序与 2 个反例） | 新增 §2.0–§2.8：三类型操作定义/方向/判据；三类型正负边界例；决策树；断言 span 最低证据；证据来源范围；方向（both/反向对）；置信 |
| §2 只提 `direction=both` 必须显式 | 明确 both 的标注与统计物化规则；反向端点对记 target->source（不记 no_edge） |
| §0 只有字段表（无 B 提交协议） | 新增 §0.1–§0.4：B 独立性、两个 canonical 产物、提交格式、路径协议 |
| §3/§4 裁决/抽检（保留） | 保留并补充：裁决记录模板、10% 抽检数量（≥5 KP/≥3 边/≥6 池对）、改手册重标 |
| §5 培训/试标（保留） | 保留；补充 concept_type 试标 10 项与“复核人预抽 20 span、不含 A 切分” |
| §6 报告要求（v1.0 无） | 新增：raw agreement + κ 退化标注；有向池一致率为主；缺失单列；agent 干跑不得当证据 |
| `iaa/README.md`（v1.0 路径 `iaa/*-second-annotator.jsonl`） | 重写 v1.1：canonical `annotations/annotator-b/`；方向/断言证据/有向指标；旧路径标废弃 |
| `iaa_runner.py`（无向池一致率、无 raw agreement） | 最小修：有向池一致率 + legacy 对照 + 方向反转清单 + tuple 方向归一化 + type raw/退化/uncertain + 默认路径 |

## 3. 干跑数值的重新解释（**仍是 agent 干跑，不是人类 IAA**）

用 task-369 的 B 产物与修订后的运行器重跑（仅作工具回归，不产生新的人工标注）：

| 指标 | 旧运行器（干跑报告） | v1.1 运行器重跑 | 解释 |
|---|---|---|---|
| KP span α | 1.000 | 1.000（boundary F1 0.990） | **仍不可解释**：B 的产物是在 v1.0 泄漏手册下标的；v1.1 去泄漏后**必须由人类重新独立标注**，该数值不能复用 |
| KP type | κ=0.000（observed 0.960，退化） | κ=0.000 + **raw agreement 0.960** + `degenerate=true` | 报告现在同时给 raw 与退化标记，不再单独用 κ 下结论 |
| 边 tuple F1 | 0.600 | 0.600（类型分歧仍在；A 标签未改） | v1.1 已定义三类型；A 需按 v1.1 复核（P1）后才能重算“规则一致后的 F1” |
| 池一致率 | 无向 κ=0.732（方向被吞） | **有向 κ=0.733（52/60）**、无向 legacy 0.667（50/60）、方向反转 0 | 有向版与干跑的 pair 级一致 52/60 对齐；无向版把 A 的反向负例误判为端点对，证明旧指标不可作主指标 |
| 方向反转 | 未测量 | 0（本次 B 未标反向边；清单字段已就绪） | 若未来 B 标反向，`direction_reversals` 会单列 |

## 4. 剩余 P1（未在本任务关闭）

| # | 项 | 原因/归属 |
|---|---|---|
| P1-1（=§7 U-10） | A 的 50 KP/30 边按 v1.1 规则复核/重标 | 写域外（`artifacts/corpus/pilot/annotations/**` 不在 task-370）；C5 要求改手册重标受影响样本 |
| P1-2（=U-11） | `manual_version` / edition 重算 | 需重跑 `make_annotations.py`（写域外）；当前 manifest 仍 v1.0 口径，不得宣称 edition 对 v1.1 冻结 |
| P1-3（=U-12） | `make_iaa_kit.py` 同步 v1.1 模板/路径 | 写域外；当前 `iaa-kit-manifest.json` 已手补 `v11_files`，生成器重跑会覆盖 |
| P1-4（=U-13） | B 文件合法性自检（span 越界/重叠/quote sha/端点 id） | dry-run 建议 7；可加 `iaa_runner.py --validate-b`，写域内但非本次 P0 最小修 |
| P1-5 | 用**人类**第二标注者执行 IAA（培训+试标+正式） | 需人；预估 10–16 人时（+P0 修订 3–5 h），C7 32 人时内 |
| P1-6 | 裁决日志真实文件（非模板） | 人类 IAA 阶段产出 |
| P1-7 | 以 v1.1 协议重跑一次 **agent** 干跑（仅工具回归，非人类 IAA） | 可在 P1-1 之后做；不得作为达线证据 |
| P1-8 | `WORKLOG.md` 补记 task-370 机器工时/成本 | 写域外（`artifacts/corpus/pilot/WORKLOG.md` 不在 task-370 写域）；本修订的实际校验见 `artifacts/agent/verify/corpus/pilot/manifest.json` |

## 5. 验收与证据（本任务）

```powershell
python -m pytest tests/corpus -q                       # 全绿（含 test_manual_revision.py + test_pilot_package.py + test_unitizing_alpha.py）
python scripts/corpus/validate_pilot.py                # 1783/1783 PASS（含 2× 复现；A 标签/manifest 未变）
python scripts/corpus/iaa_runner.py self-test          # exit 0（合成 fixture，非 IAA）
```

- **手册 v1.1** 不再包含本语料的逐条 unitization（机器测试 `test_manual_has_no_a_unitization_leak` 强制）。
- **三类型定义/正负边界例齐**（机器测试计数）。
- **P0-7 有向池一致率**有独立单测（方向反转可被识别；反向负例不再误伤）。
- 人工复核建议：随机取手册 §1.3–§2.3 的示例，让未参与本包的标注者照手册尝试切 5 个新 span、判 5 个池对，确认“只看 v1.1 能否独立标”。

## 6. 边界声明

- 本修订**未产生**任何 IAA 数值；§3 的重跑是**工具回归**，输入为 task-369 的 agent 干跑 B 产物，不能作为 C8 证据。
- 未改 A 标签、未改 C0/冻结稿、未写用户库、未 commit。
- 手册 v1.1 是 pilot 级文件；对 C0 的任何解释冲突以 C0 冻结稿 + Lead 裁决为准。
- 本次修订**不伪造**任何标注/IAA/许可数据；所有新增示例均为合成教学示例。
