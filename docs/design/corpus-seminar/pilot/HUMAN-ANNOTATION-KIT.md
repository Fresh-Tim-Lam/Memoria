# HUMAN-ANNOTATION-KIT — 人类双标注执行包（pilot）

> **状态**：执行包已就绪，**等待两名人类标注者**；本包**不生成任何人类标签/IAA**。
> **依据**：C0 冻结稿 + R-C0-1/3；`ANNOTATION-MANUAL.md` **v1.1**；task-369 agent 干跑（`IAA-DRY-RUN.md`）；task-370 P0 修订；人 2026-11-05 选“方案 1：两名真人独立标注”。
> **重要**：task-369 的 agent 干跑值**不可复用**（α=1.0 是 v1.0 手册泄漏导致虚高；κ 退化；类型分歧）；人类 IAA 必须由两名真人按 v1.1 重新独立标注。

## 1. 角色与独立性

| 角色 | 谁 | 职责 |
|---|---|---|
| annotator-a | 人类标注者 1 | 培训/试标/50 KP/60 候选对；只写自己的文件 |
| annotator-b | 人类标注者 2 | 同上，**独立**进行 |
| coordinator | 协调人（Lead 指派） | 分发、独立性守门、校验、裁决组织、IAA 报告、归档 |
| adjudicator | 裁决人（可含 C 级 Lead） | 对差异表做 A/B/C 裁决并记录 |

**独立性硬规则**（违反即整批退回，见 `COORDINATOR-CHECKLIST.md`）：

1. 两名标注者**互不看**对方文件、不讨论具体条目（规则疑问只找协调人）。
2. 标注前**不得查看 pilot 既有标注草案/产物**（协调人保证不可见；分发只给 v1.1 手册 + `chapter.txt` + 自己的模板）。
3. **先 KP 后候选对**：KP 提交并校验通过（G3）前，候选池不可见。
4. 不得使用外部模型/网络代答；不得把 agent/他人答案当自己的判断。

## 2. 交付物与本包结构

```
docs/design/corpus-seminar/pilot/
├── HUMAN-ANNOTATION-KIT.md      ← 本文件（总流程）
├── ADJUDICATION-SHEET.md        ← 裁决表说明
└── ANNOTATION-MANUAL.md         ← v1.1（标注规则唯一来源）

artifacts/corpus/pilot/human-kit/
├── START-HERE.md                ← 标注者上手页
├── TIME-LOG.csv                 ← 工时记录模板（一行一阶段）
├── annotator-a/                 ← 空白模板（无任何既有标注）
│   ├── README.md
│   ├── kps.annotator-a.template.jsonl
│   ├── pool-judgments.annotator-a.template.jsonl
│   ├── trial-10.template.jsonl
│   └── adjudication-log.template.jsonl
├── annotator-b/                 ← 同上（角色 b）
└── coordinator/
    ├── COORDINATOR-CHECKLIST.md ← 门禁 G0–G8 + 命令 + 退回条件
    ├── TRAINING-20.md           ← 培训 20 项（指向手册示例，不含本语料答案）
    ├── trial/TRIAL-TEXT.txt     ← 试标合成文本
    ├── trial/TRIAL-10.md        ← 试标说明
    └── trial/TRIAL-10-ANSWERKEY.json ← 答案（仅协调人持有）
```

**安全约束**：`human-kit/` 内**不得**出现 pilot 既有标注文件或其链接；模板只含 `_template` 行与 schema；可由机器测试 grep 断言（`tests/corpus/test_human_kit.py`）。

## 3. 执行流程（G0 → G8）

| 阶段 | 内容 | 产出 | 预计人类工时 |
|---|---|---|---|
| G0 | 分发 + 独立性确认（只给手册 v1.1/chapter/自己模板） | 签名确认（协调人存档） | 0.3 h |
| G1 | **培训 20 项**（`TRAINING-20.md`，协调人带读） | 各 ≥18/20 | 1–1.5 h/人 |
| G2 | **试标 10 项**（`trial/`，答案只在协调人处） | `trial-10.annotator-<角色>.jsonl`；各 ≥8/10 | 0.5–1 h/人 |
| G3 | **正式 50 KP**（1.1–1.8 正文；45–55 可接受） | `kps.annotator-<角色>.jsonl` + 校验 exit 0 | 2–3 h/人 |
| G4 | 协调人**锁定 G3** 后才发候选池（60 对，无标签） | 候选池只读副本/路径 | 0.2 h |
| G5 | **60 候选对判定**（edge/no_edge + 类型/方向/证据/置信） | `pool-judgments.annotator-<角色>.jsonl` + 校验 exit 0 | 2–3 h/人 |
| G6 | **裁决**（`make_adjudication_sheet.py` 生成差异表；A/B/C 填结论） | `coordinator/ADJUDICATION-SHEET.generated.md` + 裁决日志 | 3–5 h（合计） |
| G7 | **IAA 报告**（`make_iaa_report.py`，强制 human） | `artifacts/agent/verify/corpus/pilot/human-iaa-report.json` | 0.5–1 h |
| G8 | 归档（最终文件 + sha256 + 工时） | 验证目录归档 | 0.3 h |

**合计**：约 **13–21 人类工时**（C7 上限 2 人 × 2 天 ≈ 32 人时，含协调/裁决）；超预算**缩规模不降质量**（优先保 KP + 60 对全覆盖，必要时减少 query）。

## 4. 命令（canonical；协调人执行，标注者可自查 G3/G5）

```powershell
# G1/G2 无命令（人工评分）；G2 评分用答案 key 在 coordinator/trial/

# G3/G5：校验人类标注文件（exit 0 通过；1 不合规；2 输入缺失）
python scripts/corpus/validate_human_labels.py --role a `
  --kps artifacts/corpus/pilot/human-kit/annotator-a/kps.annotator-a.jsonl `
  --pool-judgments artifacts/corpus/pilot/human-kit/annotator-a/pool-judgments.annotator-a.jsonl `
  --json-out artifacts/corpus/pilot/human-kit/coordinator/validation-annotator-a.json
# （role b 同理；--min-kps/--max-kps/--expected-pool 可显式指定）

# G6：差异表（只读两位人类文件；不读 pilot 机器草案标签）
python scripts/corpus/make_adjudication_sheet.py `
  --out artifacts/corpus/pilot/human-kit/coordinator/ADJUDICATION-SHEET.generated.md `
  --json-out artifacts/corpus/pilot/human-kit/coordinator/adjudication-summary.json

# G7：人类 IAA 报告（annotator-a vs annotator-b；强制 annotator_type=human；缺数据 exit 2）
python scripts/corpus/make_iaa_report.py `
  --adjudications artifacts/corpus/pilot/human-kit/annotator-a/adjudication-log.jsonl `
  --out artifacts/agent/verify/corpus/pilot/human-iaa-report.json
```

> 规则：**G3/G5 校验未 exit 0 不得进入下一阶段**；**G7 缺任一人类文件/为空 → exit 2**（不生成报告、不伪造指标）；报告 `annotator_type` 不是 `human` 则不得用于 C8。

## 5. 验收与 IAA（C8 / R-C0-1）

| 指标 | 合格线 | 报告字段 |
|---|---|---|
| KP span unitizing α（+boundary F1） | ≥0.67（目标 0.8） | `kp_span_unitizing_alpha` |
| KP 类型 Cohen κ（+raw agreement；退化需标注） | κ≥0.67（目标 0.8） | `kp_type_cohen_kappa` / `kp_type_raw_agreement` |
| 边 tuple-set F1（type+方向+端点） | ≥0.70（目标 0.80） | `edge_tuple_f1` |
| 有向池一致率 + 方向反转清单 | 报告项（不作门槛） | `edge_pool_agreement_kappa` / `edge_pool_direction_reversals` |
| 裁决一致率 | ≥0.80 | `adjudication_agreement` |
| 10% 抽检 | 必须 | 协调人记录 |

- **不达线 → 不得扩主集**（C8）；pilot 不达线 → 修订 C 系列/标注协议。
- `NOT_APPLICABLE`/缺数据不算通过。
- 报告引用时必须写明：`annotator_type=human`、样本量、缺失处理、裁决数；agent 干跑值不得混入。

## 6. 时间与成本记录

- `TIME-LOG.csv`（`human-kit/TIME-LOG.csv`）：`date,annotator,role,stage,items,minutes,notes`；stage ∈ `training20|trial10|kps|pool60|adjudication|iaa_report|coordination`。
- 协调人负责汇总并写入最终报告/`WORKLOG`（C7 实际工时）。

## 7. 退回条件（任一出现即退回，不进入 IAA）

1. G1 <18/20 或 G2 <8/10 且未补培训；
2. 校验器 exit 1/2；KP<45/>55；池判定未覆盖 60 对；
3. 独立性违反（互看/看既有标注/KP 前看池/外部代答）；
4. 路径/文件名/`annotator` 标记不符 canonical；
5. `assertion_span` 越界/quote 与 chapter 不一致/sha 不符；edge 缺 rationale 或方向；no_edge 带类型；
6. 时间日志缺失。

## 8. 明确不做

- 本任务**不生成任何人类标签**、不填任何模板、不伪造 IAA、不写用户库、不 commit。
- 不复制/链接 pilot 既有标注文件到 `human-kit/`。
- 不改 C0 冻结稿；手册规则以 v1.1 为准。
