# 阶段工作流分析文本模板 v0.1（`comp.workflow-analysis-writer`）

> **状态**：P1 组件模板（2026-10-31，task-265；设计资产，非 conventions）。
> **组件**：`comp.workflow-analysis-writer`（`callable=false` / `executor.kind=role`，SOP：`docs/design/components-v0.2.md#sop-workflow-analysis-writer`）。
> **用途**：把一次真实的团队工作（"记忆型"分析）落成**固定结构**，供后续 `comp.workflow-component-extractor`（TD-05）稳定拆分；模板本身不实现解析器。
> **规则源**：`artifacts/agent/plugin-design/COMPONENT-DECOMPOSITION-v0.1.md §1`（原话环节→阶段→组件映射）；
> **11 阶段口径**：§1 的 7 个阶段行 + "跨阶段（研讨→设计→测试→汇报）"按 A 内容拆为 4 段 ⇒ **11 阶段**（见 §1 映射表；与 TD-05 fixture 的 `stages(11)` 对齐）。
> **机器可读**：JSON 变体 schema = `component-registry.v2.json#/typeVocabulary/analysis-doc`（`meta`/`stages`/`decisions`/`openItems` 必填，stage 必填 `id/name/actor/inputs/outputs`），本模板额外要求 `gates/evidence` 字段。

---

## 1. 固定结构（Markdown 模板）

```markdown
# <分析标题>

## meta
- memoryType: memory        # 必填：记忆型（固定值 "memory"）
- source: <原始请求 id / 文档路径>   # 必填
- author: <角色 id>                  # 必填
- date: <YYYY-MM-DD>                 # 必填

## stages
<!-- 恰好 11 个；每个 stage 用二级标题或表格行，字段齐全 -->
### S00 <阶段名>
- id: S00
- name: <阶段名>
- actor: <执行角色 id>
- inputs: [<输入物>]
- outputs: [<产出物>]
- gates: [<通过门>]
- evidence: [<证据路径或命令>]

### S01 ...（共 11 个，S00–S10）

## decisions
| id | decision | why | alternatives | decidedBy | date |
|---|---|---|---|---|---|

## openItems
- [ ] <未决项 + 影响 + 谁负责>
```

### 字段约定

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `meta.memoryType` | `"memory"` | 是 | 固定标记，表示"记忆型分析文本" |
| `meta.source` | string | 是 | 原始请求 id（如 `INBOX-20261030-01`）或分析来源文档 |
| `meta.author` | string | 是 | 分析执行角色（`team/agents.json` 或 roleTemplates 的 id） |
| `meta.date` | `YYYY-MM-DD` | 是 | 分析日期 |
| `stages[].id` | `S00`..`S10` | 是 | 11 个，顺序固定（见 §2） |
| `stages[].name` | string | 是 | 阶段名 |
| `stages[].actor` | string | 是 | 角色/组件执行者 |
| `stages[].inputs` | string[] | 是 | 非空 |
| `stages[].outputs` | string[] | 是 | 非空 |
| `stages[].gates` | string[] | 是 | 通过门（可为空数组，但字段必须在） |
| `stages[].evidence` | string[] | 是 | 证据锚（路径/命令/票号；可为空数组但字段必须在） |
| `decisions[]` | object[] | 是 | 可空数组但字段必须在；每条含 `id/decision/why/decidedBy/date` |
| `openItems[]` | string[] | 是 | 可空数组但字段必须在 |

---

## 2. 11 阶段固定表（与 COMPONENT-DECOMPOSITION §1 的映射）

| # | id | 阶段 | 执行者（组件/角色） | 对应 §1 行 |
|---|---|---|---|---|
| 1 | S00 | 任务定性 | `comp.task-classifier` / `lead` | §1 行1（0 定性） |
| 2 | S01 | 需求补全 | `comp.requirement-completer` / `steward` | §1 行2（1 补全） |
| 3 | S02 | 语料检索 | `comp.corpus-retriever` / `plugin-design-researcher` | §1 行3（1 补全-语料库） |
| 4 | S03 | 阶段工作流分析（写作） | `comp.workflow-analysis-writer` | §1 行4（2 分析） |
| 5 | S04 | 后处理拆分 | `comp.workflow-component-extractor` | §1 行5（3 拆分） |
| 6 | S05 | 组件入库 / 复用判定 | `comp.component-registry` + `comp.component-reuse-judge` | §1 行6（4 入库） |
| 7 | S06 | 工作流组装 | `comp.workflow-composer` | §1 行7（5 组装/部署） |
| 8 | S07 | 部署 | `comp.deployment-runner` | §1 行7（5 组装/部署） |
| 9 | S08 | 研讨（提案→并集→异议→裁决→冻结） | `comp.seminar-brief-author` + `comp.seminar-runner` | §1 行9（跨阶段，A 内容前段） |
| 10 | S09 | 设计 / 独立评审 | `comp.design-author` + `comp.design-reviewer` | §1 行9（跨阶段，A 内容中段） |
| 11 | S10 | 测试验证 → 汇报/转用户 → 缺失登记 | `comp.requirement-verifier` + `comp.phase-gate` + `comp.user-report` + `comp.plugin-gap-recorder`/`comp.inbox-digester` | §1 行9（跨阶段，A 内容后段）+ §1 行8（6 缺失登记） |

> **为什么是 11**：§1 有 7 个"阶段行"；跨阶段行（研讨→设计→测试→汇报）按 A 内容拆为 S08/S09/S10 三段，且"缺失登记"并入 S10 出口 ⇒ 7 + 4 = 11。TD-05 fixture 按本表消费。

---

## 3. 可解析 JSON 变体（供 TD-05 / 解析器消费）

```json
{
  "schema": "workflow-analysis/v0.1",
  "meta": {"memoryType": "memory", "source": "INBOX-20261030-01", "author": "steward", "date": "2026-10-31"},
  "stages": [
    {"id": "S00", "name": "任务定性", "actor": "lead",
     "inputs": ["raw request"], "outputs": ["classification"],
     "gates": ["分类合法"], "evidence": ["task description 定性行"]}
  ],
  "decisions": [{"id": "D-1", "decision": "…", "why": "…", "alternatives": "…", "decidedBy": "lead", "date": "2026-10-31"}],
  "openItems": ["…"]
}
```

> 兼容 `component-registry.v2.json#/typeVocabulary/analysis-doc`：`meta`（必填 memoryType/source/author）、`stages`（必填 id/name/actor/inputs/outputs）、`decisions`、`openItems`；
> 本模板额外要求每个 stage 带 `gates`/`evidence`（可空数组，但字段必须存在）。

---

## 4. 使用方式

1. 按 §1 填 Markdown（人读）+ §3 填同名 JSON（机器读）；两者内容同源。
2. 用样例校验器自检（本仓样例实现）：`python artifacts/agent/plugin-design/validate_analysis_sample.py --analysis <json>`（见样例文件）。
3. 通过后交给 `comp.workflow-component-extractor`（TD-05）拆分；本模板不实现拆分器。

## 5. 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-31 | v0.1 | 首版（task-265）：固定 meta/stages(11)/decisions/openItems + JSON 变体 + 11 阶段映射表 |
