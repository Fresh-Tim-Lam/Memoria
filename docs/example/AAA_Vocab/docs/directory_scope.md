# Directory Scope Spec（目录收录范围规范 · 次生规范）

> **文档性质**：**次生规范（secondary spec）**。本文件不由 Memoria 分发，属本知识库自行约定的补充规则。
> **上游权威（冲突时以它们为准）**：`.memoria/agent/kb-spec.zh-CN.md`（主规范）、`vocab_format.md`（条目撰写格式）。
> **适用范围**：仅限本知识库 `AAA_Vocab`。
> **状态**：生效中，2026-09-13。

---

## 1. 目的

主规范 [kb-spec.zh-CN.md §5](<../.memoria/agent/kb-spec.zh-CN.md>) 只规定"按主题规划目录树"，未规定**哪类内容进哪个目录**；`vocab_format.md` 的措辞是 `word/phrase`（[L2](<vocab_format.md>)、[L14](<vocab_format.md>)、[L18](<vocab_format.md>)），**同时允许单词与短语**。

本规范在此之上**收紧 `vocab/` 的收录范围**：`vocab/` 只收单词。短语另设目录。

> **分工说明**：`vocab_format.md` 定义**条目怎么写**（格式）；本规范定义**条目进哪个目录**（范围）。两者不冲突，各管一层，**不修改** `vocab_format.md` 任何内容。

## 2. 目录与收录范围

| 目录 | 收录内容 | 示例 |
|---|---|---|
| `vocab/` | **仅单词**：单一词形 | `blend`、`heritage`、`secluded`、`renovation` |
| `expressions/` | **多词短语、习语、固定搭配** | `hustle and bustle`、`flee the nest` |

### 2.1 判定标准（唯一依据：标题是否含空格）

| 形态 | 归类 | 说明 |
|---|---|---|
| 标题**不含空格** | `vocab/` | 含无空格合成词（`breathtaking`、`picturesque`） |
| 标题**含空格** | `expressions/` | 短语、习语、固定搭配一律如此 |

- 连字符不作为判定依据，只以**空格**为准（如 `large-scale` 不含空格，属单词，入 `vocab/`）。
- 一词多义、词形变化（复数/过去式）**不**拆分为多条。

## 3. 条目格式

两个目录的条目**均沿用** `vocab_format.md` 的七段模板（其 `[WORD / PHRASE]` 写法对短语同样适用），不另立格式。

## 4. 命名与 sidecar

| 项 | 规则 |
|---|---|
| 文件名 | 英文 kebab-case（短语用连字符连接：`flee the nest` → `flee-the-nest.md`） |
| 正文标题 H1 | 词条原文，**含空格原样写**（`# flee the nest`） |
| KP `id` | 与文件名同名的 kebab-case slug，**全库唯一** |
| KP `name` | 与正文 H1 **完全一致** |
| sidecar 路径 | **镜像 md 路径**：`expressions/x.md` → `.memoria/sidecars/expressions/x.memoria.yaml` |

## 5. 移动条目时的约束

1. **移动只改路径，不改 `id`**：`[[kp-id]]` 是 id 寻址，跨目录移动后正文 wikilink **无需改动**。
2. **必须同步改 sidecar 的 `file:` 字段**，使其指向新路径。
3. 移动后 `kp_targets.json`、`pending.json` 等**产品生成文件**会由「构建」自动刷新，**禁止手写**。
4. 跨目录移动属主规范 [§7.3](<../.memoria/agent/kb-spec.zh-CN.md>) 所列「先问用户」的操作，**执行前必须列清单确认**。

## 6. 自检清单

1. `vocab/` 下所有条目标题**不含空格**。
2. `expressions/` 下所有条目标题**含空格**。
3. 每个 md 的对应 sidecar 的 `file:` 字段指向正确路径。
4. 所有 `[[id]]` 目标仍存在（移动不改 id，故应全部有效）。
5. 自检完成后提示用户在 Memoria 执行「构建」「检查」。

## 7. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-13 | 初版；由会话中用户指出「`flee the nest` 不是单词，vocab 只收单词」驱动建立，并将 `hustle and bustle`、`flee the nest` 两条从 `vocab/` 迁至 `expressions/` |
