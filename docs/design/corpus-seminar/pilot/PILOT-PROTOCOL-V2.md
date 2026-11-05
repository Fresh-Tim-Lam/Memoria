# PILOT-PROTOCOL-V2 — agent bulk + 人类只裁决/抽检（协议 v2）

> **状态**：v2 协议已生效，取代 v1“人类双标全量 50 KP”默认路线。
> **背景（人反馈 2026-11-05）**：G3 要求人读/标 126k 字符全文太重；且 G1/G2 人类作答也有错。
> **决策**：Lead 与人确认走 **方案 1+2**：
> - **主路径（Mode A）**：两个独立 agent 按 `ANNOTATION-MANUAL.md` v1.1 做 bulk 标注（A/B 互不看），人类只做**裁决 + 抽检**（只看分歧 + 随机 5 KP / 5 对，**约 1–2 h，不读全文**）；
> - **备选（Mode B）**：纯 agent，不找人类；报告必须标 `human_unvalidated=true`，**0.5 不解禁**；
> - **可选（Mode C）**：v1 全人类双标（`HUMAN-ANNOTATION-KIT.md`）保留，**默认不做**（1–2 天）。
> **约束**：本协议/工具**不生成任何人类或 agent 标签**、不伪造 IAA；标签由独立 agent run 产出、由人类填裁决。

## 1. 模式

| 模式 | 人类参与 | 人类时间 | 报告标记 | 0.5 |
|---|---|---|---|---|
| **A：agent_bulk_human_adjudication**（默认） | 只看 spotcheck 包（分歧 + 5+5 抽样），填裁决 | **60–90 min**（协调+裁决+签收，≤2 h） | `human_iaa=false`、`human_adjudication=true`、`not_c8_conclusion=true` | **仍 HOLD**（不是双人 IAA） |
| **B：pure_agent**（备选） | 无 | 0 | `human_iaa=false`、`human_unvalidated=true`、`not_c8_conclusion=true` | 不解禁 |
| C：full-human（可选，默认不做） | 两名真人全量独立标 50 KP/60 对 | 13–21 h（v1 KIT） | `human_iaa=true`（仅两人都完成且 C8 达线时） | 由 Lead 决策 |

> **C8 口径**：A/B 都**不是** C8 要求的“两名人类独立标注 IAA”；Mode A 是人类**裁决/抽检** agent 结果。C8 是否达线由 Lead/人依 C0 决策；本协议不预设结论。

## 2. 阶段工作量表

| 阶段 | 内容 | 执行者 | 人类时间 | 机器 | 产出 |
|---|---|---|---|---|---|
| G0 | 准备：手册 v1.1、chapter、候选池、模板/工具校验 | 协调人 + 机器 | 5 min（核对） | 自动检查 | 环境就绪 |
| G1 | agent 训练/自检 20 项（手册示例 + 自测） | **机器**（agent 自检） | 0 | agent run | 自检记录 |
| G2 | agent 试标 10 项（合成 trial，答案在协调人） | **机器**（agent 试标） | 0 | agent run | trial 记录（不计 IAA） |
| **G3** | **agent-a / agent-b 各自独立标 50 KP**（v1.1 §1，1.1–1.8 正文） | **两个独立 agent run** | **0**（内容多 → 机器 bulk） | bulk | `agent-labels/agent-a/kps.agent-a.jsonl`、`agent-b/...` |
| G4 | 锁定 G3 后发候选池（60 对，无标签） | 协调人/机器 | 0 | 自动 | 池就绪 |
| **G5** | **agent-a / agent-b 各自独立判定 60 候选对**（edge/no_edge + 类型/方向/证据/置信） | **两个独立 agent run** | **0**（内容多 → 机器 bulk） | bulk | `pool-judgments.agent-a|b.jsonl` |
| G6 | **人类只看 spotcheck 包**：全部分歧项 + 随机 5 KP / 5 对（±260 字符上下文），填 `adjudication-log.jsonl` | **人类** | **60–90 min** | 机器生成包 | `spotcheck/SPOTCHECK-PACK.md` + `adjudication-log.jsonl` |
| G7 | 生成报告（agent 间一致性 + 人类裁决一致率分开；脚本） | 机器 | 10 min（核签） | 脚本 | `iaa-report-v2-*.json` |
| G8 | 归档：sha256、工时、签收、结果摘要 | 协调人 | 10 min | 自动 | verify 归档 |

**HUMAN_BUDGET_MINUTES: total_min=75 total_max=120 G0=5 G1=0 G2=0 G3=0 G4=0 G5=0 G6=60-90 G7=10 G8=10**

> 人类**不读 126k 全文**：只读 spotcheck 包（每项 ≤ ±260 字符窗口；总上下文远小于全文）。需要原文时只看包内引用片段。
> 人类总计 **≤2 h**（含协调与签收），不是 v1 的 13–21 h。

## 3. 两个独立 agent（A/B）的独立性契约

- **独立 run**：agent-a 与 agent-b 是两个独立会话/上下文；**互不查看对方文件**；都不看任何人类/既有草案标签。
- **输入**：`ANNOTATION-MANUAL.md` v1.1 + `chapter.txt`（只读）+（G5 才给）候选池。
- **禁止**：把同一 agent 的输出复制成两份；把 pilot 机器草案（`annotations/kps.single.jsonl` 等）当输入；agent 之间共享上下文/文件。
- **产出规范**：
  ```
  artifacts/corpus/pilot/agent-labels/agent-a/
    kps.agent-a.jsonl            # 50 KP（45–55），annotator="agent-a", status="agent_annotator_draft"
    pool-judgments.agent-a.jsonl # 60 对，annotator="agent-a"
  artifacts/corpus/pilot/agent-labels/agent-b/...（agent-b）
  ```
- **校验**（提交前，机器）：
  ```powershell
  python scripts/corpus/validate_human_labels.py --annotator-type agent --role a `
    --kps artifacts/corpus/pilot/agent-labels/agent-a/kps.agent-a.jsonl `
    --pool-judgments artifacts/corpus/pilot/agent-labels/agent-a/pool-judgments.agent-a.jsonl
  # role b 同理
  ```
  校验规则与 human-kit 相同（schema/越界/重叠/section/端点/quote sha/数量），仅角色标记不同。
- **注意**：`agent-labels/` 目录当前**为空**（本任务不生成标签）；工具默认路径指向它，待 agent run 产出后即可运行。

## 4. 人类抽检包（G6）

```powershell
python scripts/corpus/make_spotcheck_pack.py `
  --out artifacts/corpus/pilot/spotcheck/SPOTCHECK-PACK.md `
  --json-out artifacts/corpus/pilot/spotcheck/spotcheck-pack.json
```

- 包内容 = **全部分歧项**（KP span 边界/类型/存在性；边存在性/类型/方向；超出上限截断并计数）
  \+ **随机 5 KP + 随机 5 对**（seed 373，可复核；无分歧项）。
- 每项只给 `chapter.txt` 的 **±260 字符窗口**（标出 span 位置、左右是否截断），**不含全文**；
  机器 JSON 记录 `chapter_chars`、`context_chars_total`、占比、`est_human_minutes`。
- 人类在 Markdown/JSON 中填：`decision`（`采 A` / `采 B` / `重判：<结论>` / `无法裁决`）、`level`（A/B/C）、`reviewer`、`date`；
  保存为 `artifacts/corpus/pilot/spotcheck/adjudication-log.jsonl`（一行一项）。
- 人类时间约 **60–90 min**（约 20–35 项 × 1.5–2 min + 协调/签收）；不要求读全文。

## 5. 报告（G7）

```powershell
# Mode A（默认）：需要两位 agent 标签 + 人类 adjudication-log
python scripts/corpus/make_iaa_report_v2.py --mode agent_bulk_human_adjudication `
  --out artifacts/agent/verify/corpus/pilot/iaa-report-v2-agent-bulk.json

# Mode B（备选）：仅两位 agent 标签，无人签收
python scripts/corpus/make_iaa_report_v2.py --mode pure_agent `
  --out artifacts/agent/verify/corpus/pilot/iaa-report-v2-pure-agent.json
```

报告字段（分开、不可混写）：

| 字段 | 含义 | 用途 |
|---|---|---|
| `agent_vs_agent` | agent-a vs agent-b 的 unitizing α / 类型 κ+raw / 边 tuple F1 / 有向池一致率 | **advisory**：评估 agent 可复现性，不是人类 IAA |
| `human_adjudication_agreement` | 人类接受 A / 接受 B / 重判 / 无法裁决 的比例（按分歧/抽检分组） | 人类**裁决一致率**；目标 ≥0.80（质量信号） |
| `human_adjudication_complete` | 包内所有项是否都有裁决 | 未完成 → `human_unvalidated=true` |
| `human_iaa` | **恒为 false**（v2 没有双人全量 IAA） | 禁止被改写成 true |
| `human_unvalidated` | pure_agent 或无完整人类裁决时为 true | 0.5 不得解禁 |
| `not_c8_conclusion` | 恒 true | 报告不构成 C8 结论 |

**Mode B 的硬约束**：`human_iaa=false`、`human_unvalidated=true`、`not_c8_conclusion=true`；
纯 agent 数值不得被引用为 C8 证据，0.5 继续 HOLD。

## 6. 验收/退回条件

| 检查 | 通过 | 退回 |
|---|---|---|
| agent 标签 | `validate_human_labels.py --annotator-type agent` exit 0；45–55 KP；池 60 对全覆盖 | exit 1/2；数量越界 |
| 独立性 | 两个独立 agent run；无交叉/无既有草案输入 | 同一输出复制/共享上下文 |
| spotcheck 包 | 只含分歧+5+5；总上下文 < 全文 50%；每项窗口 ≤ ±260+span | 塞全文/超窗口 |
| 人类裁决 | 包内项全部裁决；耗时 ≤2 h；adjudication-log 非空 | 未完成/超时 → 补齐或降级 Mode B |
| 报告 | Mode A：`human_iaa=false`、`human_adjudication=true`；Mode B：`human_unvalidated=true` | 出现 `human_iaa=true` 或漏标记 |

## 7. 与旧 HUMAN-KIT 的关系

- `HUMAN-ANNOTATION-KIT.md`（v1 全人类双标）**保留为可选 full-human 路线（Mode C），默认不再执行**；
  其中培训/试标/模板/校验器仍可复用。
- v2 校验器复用同一脚本（只加 `--annotator-type agent`）；v2 裁决用 `make_spotcheck_pack.py` + `make_iaa_report_v2.py`，
  v1 的 `make_adjudication_sheet.py` 仅适用于“两名人类全量”场景。
