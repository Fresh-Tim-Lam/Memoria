# 组件命名规范 v0.1（设计资产）

> **状态**：**设计资产（已按 Lead 2026-10-31 裁决 1 落 `docs/design/`）**；文件头声明：**待人类批准后升为 `docs/conventions/components.md`**。在升格前，本文件是组件/分类/元协议 id 命名与校验的**唯一依据**。
> **依据**：Lead 2026-10-31 裁决（命名不直升 conventions；registry 落 `docs/design/` 为唯一事实源）+ `INBOX-20261030-01` 消化（`COMPONENT-DECOMPOSITION-v0.1.md §5`）。
> **Owner**：`plugin-todo-owner`（本轮）；后续维护：`steward`（memoria-tooling）/ 人类批准升格。
> **关联**：`component-registry.v1.json`（同名唯一事实源）、`artifacts/agent/plugin-design/component-registry.v1.json`（证据副本，须 byte-identical）、`artifacts/agent/plugin-design/COMPONENT-DECOMPOSITION-v0.1.md`（拆解表）、`artifacts/agent/plugin-design/META-PROTOCOL-v0.1.md`（元协议）。
> **生效边界**：本文件只约束**命名与校验**，不改变任何现有契约/裁决；Agents **不得**直接修改 `docs/conventions/**`（人类单一事实源），只能提交本文件 + 建议 diff。

---

## 1. 适用范围与权威顺序

| 对象 | 命名载体 | 权威来源 |
|---|---|---|
| 组件 id | `component-registry.v1.json` 的 `components[].id` | 本文件 §2.1 + registry |
| registry 文件名 | `component-registry.v1.json` | 本文件 §2.2 + Lead 裁决 2 |
| JSON 字段名 | registry 各键 | 本文件 §2.3 |
| 分类 id（任务定性） | `META-PROTOCOL-v0.1.md §2` | 本文件 §2.4 |
| 元协议 id | `META-PROTOCOL-v0.1.md` 文件头 | 本文件 §2.5 |
| 协议 id（既有） | `team/protocols.json` + `docs/guides/team-protocols.md` | 既有 R-06/C-01 双命名空间（本文件只引用，不改） |

**权威顺序（冲突时）**：`docs/conventions/**`（人类单一事实源）> 本文件 > 各组件文档。本文件与 conventions 冲突处一律以 conventions 为准，并在 §6 记录待修。

---

## 2. 命名规则

### 2.1 组件 id

- 形式：`comp.<kebab-case>`；例：`comp.task-classifier`、`comp.component-reuse-judge`。
- 正则：`^comp\.[a-z0-9]+(-[a-z0-9]+)*$`。
- 语义：`comp.` 是命名空间前缀（与协议 id 的"命名空间前缀 + 点路径"先例一致：`tool.peerMessage.hops` / 团队 kebab-case，见 R-06/C-01）。
- **禁止**：临时起名、大写、下划线、重复语义（同 id 不同义 ⇒ FAIL；沿用 `docs/design/agent-plugin-design.md §1` 的"同名不同义即装载失败"先例）。

### 2.2 registry 文件名与位置

- 唯一事实源：`docs/design/component-registry.v1.json`（tracked；Lead 2026-10-31 裁决 2）。
- 证据副本：`artifacts/agent/plugin-design/component-registry.v1.json`（gitignored；**内容必须与源 byte-identical**）。
- 文件名规则：`kebab-case` + `vN` 版本后缀（`docs/conventions/docs-management.md §1` 的 kebab-case 先例；`vN` 表 schema 主版本）。

### 2.3 JSON 字段名

- camelCase（v9 schema 先例：`schema/team-protocols.schema.json` 的 `registryVersion`/`protocols`/`additionalProperties`）。
- 根必填键：`schema`、`registryId`、`version`、`updatedAt`、`source`、`owner`、`status`、`namingRule`、`sourceOfTruth`、`canonicalPath`、`evidenceCopy`、`summary`、`components`。
- 组件必填键：`id`、`version`、`name`、`summary`、`inputs`、`outputs`、`preconditions`、`failureStates`、`sideEffects`、`idempotent`、`composesWith`、`implementedBy`、`status`、`reuse`、`matchedExisting`、`namingBasis`。
- `inputs[]` 元素：`{name, type, required?}`；`implementedBy`：`{kind∈{tool,doc,convention,missing}, ref}`；`status∈{implemented,partial,missing}`；`reuse∈{reuse,complete,new}`。

### 2.4 分类 id（任务定性）

- 形式：`cls.<kebab-case>`；例：`cls.defect-fix`、`cls.team-work-design`。
- 正则：`^cls\.[a-z0-9]+(-[a-z0-9]+)*$`；取值集合以 `META-PROTOCOL-v0.1.md §2` 表为准（新增类别须先改元协议并记录）。

### 2.5 元协议 id

- 形式：`meta.<kebab-case>`；例：`meta.task-classification`。
- 正则：`^meta\.[a-z0-9]+(-[a-z0-9]+)*$`。

### 2.6 与既有命名空间的关系（只引用不改）

- 工具名：`team_*`（v9 先例：`team_protocol_list`/`team_snapshot`/`team_trajectory`）。
- 协议 id：内置 `tool.<camelCase.path>`、团队自订 kebab-case（R-06/C-01；`schema/team-protocols.schema.json` 已表达）。
- 本文件新增的 `comp.`/`cls.`/`meta.` 三个命名空间**不占用**协议命名空间；三者之间不复用前缀。

---

## 3. 校验规则（可机检清单）

1. **id 正则**：所有 `components[].id` 匹配 `^comp\.[a-z0-9]+(-[a-z0-9]+)*$`；`cls.`/`meta.` 按 §2.4/§2.5。
2. **id 唯一**：`components[].id` 无重复（排序后相邻不等）。
3. **版本**：每个组件 `version` 匹配 `^\d+\.\d+\.\d+$`；registry 根 `version` 亦同。
4. **必填键非空**：§2.3 所列组件必填键均存在且非空（数组可空仅当有文档说明）。
5. **引用完整性**：`composesWith[]` 的每个 id 必须存在于 `components[].id`；`implementedBy.ref` 非空；`matchedExisting[].ref` 非空。
6. **状态一致性**：`status=missing` ⇒ `implementedBy.kind=missing`；`status=implemented|partial` ⇒ `implementedBy.kind∈{tool,doc,convention}`。
7. **双副本一致**：`docs/design/component-registry.v1.json` 与 `artifacts/agent/plugin-design/component-registry.v1.json` 的 SHA-256 相等（命令见 §5）。
8. **摘要一致**：根 `summary.total/reuse/complete/new/missingPure/missingPartial` 与实际数组计数一致（reuse 计 `reuse=reuse`；new 计 `reuse=new`；missingPure 计 `status=missing`）。

---

## 4. registry schema 摘要（供校验器实现）

```
component-registry/v1 (JSON, UTF-8 no BOM, camelCase)
├─ schema: "component-registry/v1"
├─ registryId: string            e.g. "memoria-team-components"
├─ version: semver               "0.1.0"
├─ updatedAt: ISO8601+08:00
├─ source: "INBOX-20261030-01"
├─ owner: member-id
├─ status: string
├─ namingRule: { componentId, note, anchors[] }
├─ sourceOfTruth: "docs/design/components-v0.1.md"
├─ canonicalPath: "docs/design/component-registry.v1.json"
├─ evidenceCopy: "artifacts/agent/plugin-design/component-registry.v1.json"
├─ summary: { total, reuse, complete, new, missingPure, missingPartial }
└─ components: [ Component ]      (17 项，字段见 §2.3)
```

---

## 5. 一致性检查与只读校验（实现由 `steward` 承接；本轮只给命令草案）

**一致性（双副本必须相等）**：
```powershell
(Get-FileHash 'docs/design/component-registry.v1.json' -Algorithm SHA256).Hash -eq `
(Get-FileHash 'artifacts/agent/plugin-design/component-registry.v1.json' -Algorithm SHA256).Hash
# 期望输出：True
```
**解析 + 关键字段（只读）**：
```powershell
$r = Get-Content 'docs/design/component-registry.v1.json' -Raw -Encoding UTF8 | ConvertFrom-Json
$r.components.Count                                   # 17
($r.components | Where-Object { $_.id -notmatch '^comp\.[a-z0-9]+(-[a-z0-9]+)*$' }).Count  # 0
($r.components | Group-Object id | Where-Object Count -gt 1).Count                          # 0
```
**引用完整性**：
```powershell
$ids = $r.components.id; $bad = $r.components.composesWith | Where-Object { $ids -notcontains $_ }
$bad.Count                                            # 0
```
> `scripts/agent/**` 的**正式实现**（校验器/CI 检查）本轮不做：Lead 2026-10-31 裁决 3 明确写域不扩，后续由 `steward`（memoria-tooling）承接；本文件只提供规则与命令草案。

---

## 6. 变更与升格流程

1. **升格（待人类批准）**：人批准后，把本文件内容迁入 `docs/conventions/components.md`（由人/人类授权的 registrar 操作；Agent 不直接写 `conventions/**`），并在 `docs/conventions/README` 登记。
2. **日常变更（Agent 可做）**：只改 `docs/design/components-v0.1.md` + `docs/design/component-registry.v1.json`（唯一事实源）+ 同步 artifacts 副本；每次变更在 §8 追加记录，并在 registry 根 `updatedAt`/`version` 同步（破坏性命名变更 → registry 版本 minor/major 递增）。
3. **校验器变更**：规则变更需同时更新 §3 清单与（未来的）`scripts/agent/` 校验器；`steward` 承接。
4. **与 conventions 冲突**：以 conventions 为准，在 §8 记 conflict 并提 diff 建议，不静默改。

---

## 7. 未决 / 待人类批准

1. **升格**：本文件 → `docs/conventions/components.md`（需人类批准；批准前本文件是唯一依据）。
2. `comp.`/`cls.`/`meta.` 三个命名空间是否与未来插件侧别的命名冲突（组件化二/三期再复核）。
3. 校验器的落地形态（`steward` 承接）：独立脚本 vs 并入 `team_audit.py`（后者是团队机检入口，倾向后者，待裁）。
4. registry 的 `evidenceCopy` 字段是否需要在过渡期后移除（当前保留以便审计回链）。

---

## 8. 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-31 | v0.1 | 首版：按 Lead 裁决 1/2 从 `COMPONENT-DECOMPOSITION-v0.1.md §5` 升为 `docs/design/` 设计资产；定义 comp./cls./meta. 命名、registry schema、校验与双副本一致性检查；未改 `docs/conventions/**`，待人类批准升格 |
