# 需求补全模板 v0.1（`comp.requirement-completer`）

> **状态**：P1 组件模板（2026-10-31，task-266；设计资产，非 conventions）。
> **组件**：`comp.requirement-completer`（`callable=false` / `executor.kind=role`；SOP：`docs/design/components-v0.2.md#sop-requirement-completer`）。
> **输入**：`rawRequest`（人的原话，逐字）+ `corpusRefs[]`（语料锚：`path#anchor` / URL+日期）。
> **输出**：`completedRequirement`（每行 5 列：原话 / 推断需求 / 设计决定 / 理由 / 可验证判据；可加第 6 列类别）+ `assumptions[{text,ifWrongImpact}]` + `openQuestions[]`。
> **依赖**：`artifacts/agent/plugin-design/REQUIREMENTS-TRACE.md` 五列格式；`docs/design/meta-protocol-v0.2.md §3.3 附`（语料库）。
> **边界**：只做模板+样例；不做补全 agent 工具化；不新建事实源；不改 conventions。

---

## 1. 固定结构

```markdown
# 需求补全：<rawRequest 摘要>

## rawRequest（逐字）
> <人的原话逐字，不改写>

## corpusRefs
| # | 语料锚（path#anchor / URL） | 支撑什么 |
|---|---|---|

## completedRequirement（5 列必填）
| # | 原话 | 推断需求 | 设计决定 | 理由 | 可验证判据 | 类别（可选） |
|---|---|---|---|---|---|---|

## assumptions
| id | text | ifWrongImpact |
|---|---|---|

## openQuestions（≤3，只允许产品可见二选一）
| id | 问题（选项 A/B） |
|---|---|
```

### 字段约定

| 字段 | 必填 | 规则 |
|---|---|---|
| `rawRequest` | 是 | 逐字原话；不得改写/合并 |
| `corpusRefs[]` | 是 | 至少 1 条；每条有可核对的 path#anchor 或 URL+日期 |
| `completedRequirement[]` | 是 | **≥5 行**；5 列（原话/推断需求/设计决定/理由/可验证判据）**每格非空**；可加 `category` |
| `assumptions[]` | 是 | 每条含 `text` + `ifWrongImpact`（若假设错，影响是什么） |
| `openQuestions[]` | 是 | **≤3 条**；只能问「产品可见效果」的二选一；格式 `选项 A：…；选项 B：…`（正则见 §3） |

### 纪律（来自 REQUIREMENTS-TRACE 与 META-PROTOCOL）

1. 解释性判断必须留痕（推断需求/决定/理由/替代解释），不得只活在对话里；
2. 不可实现/不划算的判断必须给证据锚（file:line / 实验 / 票号）；
3. 只向人问“看得到的效果”的二选一；**不问**层数/字段/命名等模型内部结构；
4. 人的原话是意图级需求，不是规格：补全的是“可执行需求”，不是替人改需求；
5. 本模板不新增事实源；补全结果回填到任务/`REQUIREMENTS-TRACE` 既有载体。

---

## 2. 样例（INBOX-20261030-01 B 段）

> 见 `artifacts/agent/plugin-design/REQUIREMENTS-COMPLETION-INBOX-20261030-01.md`（人读）与同名 `.json`（机器读）。
> 该样例：7 行 completedRequirement（5 列非空率 100%）、3 条 assumptions（均含 ifWrongImpact）、3 条 openQuestions（A/B 形式）。

---

## 3. 可机检验收（样例校验器）

样例校验器（本仓样例实现，**不是**补全 agent 的工具化）：
`python artifacts/agent/plugin-design/validate_requirement_completion.py --analysis <json> --selftest`

| 检查 | 规则 |
|---|---|
| rows | `len(completedRequirement) >= 5` |
| 5 列非空率 | 每行 `original/inferred/decision/reason/criterion` 全部非空 ⇒ 100% |
| assumptions | 每条 `text` 非空且 `ifWrongImpact` 非空 |
| openQuestions | 数量 ≤3；每条 `question` 匹配 `选项 A：…选项 B：…`（正则 `选项\s*A\s*[：:]` 且 `选项\s*B\s*[：:]`） |
| 空输入 | 文件不存在/JSON 坏 ⇒ exit 2（不许“没输入=通过”） |
| 红样例 | rows<5、任一列空、缺 ifWrongImpact、openQuestions>3、非 A/B 格式 ⇒ exit 1 |

## 4. 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-31 | v0.1 | 首版（task-266）：5 列 trace + assumptions + openQuestions 模板 + JSON 变体 + 样例 |
