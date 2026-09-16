# Error Log Format（错题本格式规范 · 次生规范）

> **文档性质**：**次生规范（secondary spec）**。本文件不由 Memoria 分发，属本知识库自行约定的补充规则。
> **上游权威（冲突时以它们为准）**：`.memoria/agent/kb-spec.zh-CN.md`（主规范）、`vocab_format.md`（词条撰写规范）。
> **适用范围**：仅限本知识库 `AAA_Vocab`。
> **状态**：生效中，2026-09-10。

---

## 1. 目的与定位

记录用户在学习过程中**实际产出的错误表达**（口语/写作编译错误、搭配误用、拼写错误、语法错误等），形成可追溯、可统计、可回访的错题事实源。

| 项 | 说明 |
|---|---|
| 存储路径 | `.memoria/agent/review/errors.json` |
| 维护者 | Trae 智能体 |
| 是否被 Memoria 升级覆盖 | **否**（`review/**` 永不被覆盖） |
| 与主规范的关系 | 补足 [kb-spec.zh-CN.md §1](<../../.memoria/agent/kb-spec.zh-CN.md>) 中"学习状态只放 `review/**`"的空白；不新增事实源目录 |

## 2. 硬约束（来自主规范，不可绕过）

1. **只放 `review/**`**：错题属学习状态，**禁止**写进 `*.md` 正文或 `sidecar`（避免污染知识语义）。
2. **不改原文语义**：记录用户的原始错误表达时**原样保留**（含拼写错误），订正另置 `correction` 字段，不做就地改写。
3. **不改 KP id / 不动文件**：错题记录通过 `kp_refs` **引用**已有 KP，不因错题而新建、重命名或移动任何词条。
4. **不手写 `manifest.yaml`**：错题记录不参与构建指纹。
5. **时间戳一律 ISO-8601 带时区偏移**（本库为 `+08:00`），**不得**手写相对时间（如"昨天"）。

## 3. 文件结构

```json
{
  "schema_version": 1,
  "file_type": "error_log",
  "kb": "AAA_Vocab",
  "created_at": "2026-09-10T17:02:02+08:00",
  "updated_at": "2026-09-10T17:02:02+08:00",
  "timestamp_convention": "ISO-8601，带本地时区偏移（Asia/Shanghai = +08:00）",
  "spec_ref": "docs/error_log_format.md",
  "sessions": [],
  "errors": []
}
```

### 3.1 顶层字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `schema_version` | int | 是 | 结构版本，当前 `1`；破坏性变更才 +1 |
| `file_type` | str | 是 | 固定 `error_log` |
| `kb` | str | 是 | 知识库标识 |
| `created_at` / `updated_at` | str | 是 | ISO-8601 带时区 |
| `timestamp_convention` | str | 是 | 时间戳约定说明，防止跨会话误读 |
| `spec_ref` | str | 是 | 指向本规范 |
| `sessions` | array | 是 | 学习场次（见 §3.2） |
| `errors` | array | 是 | 错题条目（见 §3.3） |

### 3.2 `sessions[]`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | str | 是 | 场次 id，形如 `sess-YYYYMMDD-NN` |
| `ts` | str | 是 | 场次开始时间 |
| `topic` | str | 是 | 本次学习主题 |
| `sections` | array[str] | 否 | 本次涉及的题型/环节 |

### 3.3 `errors[]`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | str | 是 | 错题 id，形如 `err-YYYYMMDD-NNN`，**全库唯一** |
| `ts` | str | 是 | 记录时间（ISO-8601 带时区） |
| `session` | str | 是 | 所属 `sessions[].id` |
| `source` | str | 是 | 题号/来源标记（如 `B1`、`C`） |
| `mode` | str | 是 | `translation` / `production` / `recognition` |
| `skill` | str | 是 | `speaking` / `writing` |
| `original` | str | 是 | 用户原始表达，**原样保留**（含错误） |
| `issues` | array | 是 | 问题清单（见 §3.4）；无问题时可为空数组 |
| `correction` | str | 是 | 订正后的目标表达 |
| `kp_refs` | array[str] | 是 | 关联的已有 KP id；**必须是全库已存在的 id**，不得虚构 |
| `status` | str | 是 | `open` / `reviewing` / `resolved` |

### 3.4 `errors[].issues[]`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `type` | str | 是 | 错误类型，见下表枚举 |
| `from` | str | 是 | 原片段的**最小错误单位**（词 / 搭配 / 分句） |
| `to` | str | 是 | 订正后的片段 |
| `note` | str | 是 | 中文说明错因 |

**`type` 枚举**：`spelling`（拼写）、`grammar`（语法）、`collocation`（搭配）、`word_choice`（用词）、`tense`（时态）、`article_plural`（冠词/单复数）、`capitalization`（大小写）、`word_form`（词形）、`register`（语域）。

## 4. 写入规则

1. **追加，不改写**：既有错题条目**只追加新条目**；更正历史条目时保留原条目并新增，不就地覆盖。
2. **一条一错**：`errors[]` 一个元素对应一次用户产出（一个句子/一段话）；其中可含多条 `issues[]`。
3. **最小错误单位**：`issues[].from` 只圈出真正出错的最小片段，不要整句照抄。
4. **必挂 KP**：`kp_refs` 至少一条，且指向已存在的 KP；无对应 KP 时先补 KP（按 `vocab_format.md`），再记错题。
5. **写入前给清单**：批量记录时先列清单请用户确认。
6. **同步 `updated_at`**：每次写入后更新顶层 `updated_at`。

## 5. 与复习系统的关系

- 错题本**不参与** FSRS 调度。到期日/间隔一律由 `.memoria/agent/fsrs.py` 计算，**不得**自行推算。
- 错题的 `kp_refs` 用于把错误**回挂到 KP**；复习出题时可优先覆盖 `status: open` 的错题所涉 KP。
- 复习卡片仍只存 `review/cards.json`，进度仍只存 `review/progress.json`；`errors.json` 是**独立**的第三类文件，互不写入。

## 6. 自检清单

1. JSON 可被解析（`json.load` 无异常）。
2. 所有 `id` 唯一。
3. 所有 `ts` / `created_at` / `updated_at` 均为 ISO-8601 且带时区偏移。
4. 所有 `kp_refs` 指向的 id 在 `.memoria/sidecars/**` 中真实存在。
5. `original` 与用户原话逐字一致（含错误的拼写）。
6. 每条 `errors[]` 至少一条 `issues[]`（纯"可升级但无错"的表达不应记入）。

## 7. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-10 | 初版；由会话中用户"用文件持久化并打时间戳"要求驱动建立 |
