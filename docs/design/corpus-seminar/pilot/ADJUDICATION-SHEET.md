# ADJUDICATION-SHEET — 人类双标注差异裁决表（full-human 可选）

> ℹ️ **v2 默认不使用本表**：protocol v2 的人类参与是“分歧+5 KP/5 对抽检”，见 `PILOT-PROTOCOL-V2.md` 与 `make_spotcheck_pack.py`；本表仅用于可选 full-human（两名真人全量）路线。

> **状态**：模板/生成器已就绪；等待人类标注者文件；**不生成任何标签**。
> **输入**：**只读两位人类标注者**的 `kps.annotator-<a|b>.jsonl` 与 `pool-judgments.annotator-<a|b>.jsonl`。
> **不读** pilot 机器草案标签（`annotations/kps.single.jsonl`、`annotations/edges.single.jsonl`）；不把机器草案当第三方裁决者。
> **依据**：`ANNOTATION-MANUAL.md` v1.1 §2（S0 三类型/方向/证据）与 §4（A/B/C 裁决）；C0 R-C0-1（裁决一致率 ≥0.80）。

## 1. 生成差异表

```powershell
python scripts/corpus/make_adjudication_sheet.py `
  --out artifacts/corpus/pilot/human-kit/coordinator/ADJUDICATION-SHEET.generated.md `
  --json-out artifacts/corpus/pilot/human-kit/coordinator/adjudication-summary.json
```

- 输入缺失/无法解析 → **exit 2**；有差异不影响 exit（差异就是要裁决的内容）。
- 生成表包含：输入 sha256、KP 差异表（span 边界/`concept_type`/缺失对应）、语义边差异表（存在性/类型/方向/池外追加）、统计。

## 2. 差异类型与裁决规则

### 2.1 KP 差异

| kind | 含义 | 裁决建议（按 v1.1） |
|---|---|---|
| `span_boundary` | 同一 KP 边界不同（IoU<1 且匹配） | 对照手册 §1.2 R1/R2：定义句 vs 定义句+机制句；引语必须落在 span 内（R3）；选更符合规则者，必要时“重切” |
| `concept_type` | `concept_type` 不同 | 按手册 §1.6 判定表 + 判定顺序；不确定方的 `type_uncertain` 项只记录不强制一致；仍冲突 → B/C 级 |
| `unmatched_a` | A 有、B 无对应 span | 看 B 是否漏标/合并；采 A / 删除 / 并入匹配项 |
| `unmatched_b` | B 有、A 无对应 span | 同上（对称） |

### 2.2 语义边差异（池内 60 对）

| kind | 含义 | 裁决建议 |
|---|---|---|
| `existence` | 一方 edge、一方 no_edge | 复核 `assertion_span`：无直接断言/仅共现/两步推理 → no_edge（§2.5）；有直接断言 → edge |
| `edge_type` | 类型不同 | 按 §2.0–2.4 决策树：分类/组成→contain；因果/派生→extend；度量/表示/指涉（无机制）→reference |
| `edge_direction` | 方向不同 | 按 §2.7：反向对记 `target->source`；`both` 必须两条独立断言并物化两条有向 tuple；方向错误不得用 no_edge 掩盖 |
| `missing_a/b` | 一方缺该池对判定 | 退回补标；不得默认 0 |
| `extra_a/b` | 池外追加边 | 逐条看端点/断言；可并入正式集（报告单列）或拒绝 |

### 2.3 级别（A/B/C）

- **A 级**：手册已覆盖、由直接断言决定 → 标注者自决，不进入裁决。
- **B 级**：两种合理取舍（边界/一步推理/medium 档位/表格佐证）→ 资深复核裁决。
- **C 级**：规则冲突/手册未覆盖/许可或 S0 类型边界 → **Lead 终裁**；必须留档并回写手册（改手册 → 重标受影响样本 + 升版）。

## 3. 填写方式（裁决人）

- 在生成的表里填 `decision / level / reviewer / date`；`decision` 建议值：`采 A` / `采 B` / `折中` / `重切` / `重判类型` / `重判方向` / `补标` / `删除` / `待 C 级`。
- **不要直接改标注者的原始文件**（保留独立标注审计）；裁决记录写 `annotator-a|b/adjudication-log.jsonl`（模板见 `human-kit/annotator-*/adjudication-log.template.jsonl`）。
- 若某条需要重标，另生成新版本文件（`*.v2.jsonl`）并重新校验；IAA 报告仍以**独立原始标注**为主，裁决用于一致率与最终 golden。

### 裁决日志字段

```json
{"item_id": "pair-017", "source": "adjudication-sheet", "question": "existence: edge vs no_edge",
 "options": ["采 A", "采 B", "重看断言 span"], "level": "B", "decision": "采 B",
 "rationale": "断言句只描述关联，无因果/分类；按 §2.5 仅共现关系 → no_edge",
 "reviewer": "<姓名>", "date": "YYYY-MM-DD", "affected_items": ["pair-017"]}
```

## 4. 裁决一致率（报告字段 `adjudication_agreement`）

```
裁决一致率 = 双方独立判断经复核确认（未被改判）的条目数 / 参与裁决的条目数
```

- 目标 **≥0.80**；与 IAA 分指标并列报告，不得用裁决一致率替代 α/κ/F1。
- 若裁决把大量条目改判，说明手册/培训仍有系统性歧义 → 回到手册修订（C5：改规则 → 重标受影响样本）。

## 5. 空白模板（裁决人可直接复制）

```markdown
| # | kind | 对象 | A | B | 差异说明 | 裁决选项 | 决定 | level | reviewer | date |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 |  |  |  |  |  |  |  |  |  |  |
```

> 生成的完整表在 `artifacts/corpus/pilot/human-kit/coordinator/ADJUDICATION-SHEET.generated.md`；本文件只定义格式与规则。
