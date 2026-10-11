# Memoria 功能需求单（来自 AAA_Vocab 使用现场）

> **用途**：把「用这个知识库备考雅思」过程中真实撞到的功能缺口，整理成可施工的需求，交给 Memoria 开发者。
> **来源**：本知识库智能体与使用者本人的实际操作记录（会话 `session-20260921T111525Z-ab1ac72c`），不是凭空设计。
> **取证日期**：2026-10-10（所有行号对应当日磁盘内容）。
> **本文件不建知识点**（属产品文档，与 `docs/agent_specification.md`、`docs/requirements.md` 同类）。

---

## 0. 摘要

| # | 需求 | 状态 |
|---|---|---|
| **R1** | 智能体**受控执行命令**（跑 `fsrs.py`、批处理脚本） | **✅ 已交付且已挂上本库工具集**（`pwsh` / `cmd`，逐次审批，回传 stdout / exitCode / 耗时）——实测可用（§3.2） |
| **R2** | `review/**` 事实源的**受控写入**（领域工具，而非通用 JSON 写） | **✅ 已交付 5 把**：`review_cards_upsert` / `review_card_disable` / `review_due_list` / `review_grade` / `review_error_add`——实测写入成功且可撤销（§3.2） |
| **R3** | **复习卡管理视图** | 待开发（归 K5 显示子系统那条线） |
| **R0** | 附带发现：**规格分叉**——`docs/requirements.md` §4 的存储方案**从未实现** | **✅ 已裁定**：权威＝`error_log_format.md` + `fsrs.py`；§4 已标注「历史设计稿」（§2.3） |

---

## 1. 现场（**R1/R2 交付前**，2026-10-10）：智能体能做什么、不能做什么

> ⚠ 本节记录的是**交付前**的受限状态；其中「不能」两条当日已解决，**当前状态以 §3.2 为准**。

| 能力 | 现状 | 后果 |
|---|---|---|
| 读 `*.md`、sidecar、任意文本 | ✅ | —— |
| 写 `*.md`、sidecar（KP / 链接） | ✅ | —— |
| **执行命令** | ❌（本知识库智能体工具集内没有 shell） | `fsrs.py` 的 `due` / `init` / `grade` **一步都走不了**；只能写脚本交人点运行 |
| **写 JSON 事实源** | ❌（写入工具只覆盖 `.md` 与 sidecar） | `review/cards.json`、`review/errors.json` **一个字都写不进去** |

两件事合起来 = **复习系统在智能体手里是「死」的**：调度器在位，卡片文件不存在，复习一次都没转起来。

### 1.1 `review/` 下真有什么（2026-10-10 实测）

```
.memoria/agent/review/
  errors.json                    # 错题本（921 行，事实源，agent 要写）
  evaluations/9_18_1.json        # 写作批改结构化记录（261 行）
  evaluations/9_18_2.json
  # cards.json    ← 不存在
  # progress.json ← 不存在
```

> `evaluations/*.json` 字段为 camelCase（`matchedTask` / `annotatedEssayHtml` / `grammarHighlights`），与智能体产物（snake_case）风格不同，**推测由应用侧写作批改功能写入——待确认**。

---

## 2. 证据：既成契约（不是我们的设计，是已经跑起来的约定）

### 2.1 `fsrs.py` 对 `cards.json` 的真实要求

`.memoria/agent/fsrs.py:188-208`（`load_card_ids`）：

- 顶层**必须是对象**，且 `cards` **必须是 list**（否则抛 `FsrsError`）；
- 逐项只取 **`card_id`（必须是 str）**；
- **✅ 已改 fail-closed（2026-10-10）**：坏条目**不再静默跳过** —— 缺 `card_id`（或非 str）会抛 `FsrsError` 并列出下标。**本库副本实测已是新版**（`.memoria/agent/fsrs.py:188-208` 的 `load_card_ids` 内含 `fail-closed` 与下标清单），通告中的「需刷新」在本库**不适用**。

其余字段（`front` / `back` / `type` / `kp_id` / `file`）`fsrs.py` **完全不读** ⇒ 它们是**显示侧**字段，由 UI / 智能体消费。

### 2.2 `cards.json` 的权威形状（已存在，只是没写进任何文档）

`.memoria/agent/fsrs.py:501-525`（`_prepare_kb`，作者自检时写出的示例）：

```json
{
  "schema_version": 1,
  "updated_at": "<UTC ISO-8601>",
  "cards": [
    {
      "card_id": "...",
      "kp_id": "...",
      "file": "a.md",
      "type": "basic",
      "front": "...",
      "back": "...",
      "source": "agent",
      "created_at": "<UTC ISO-8601>"
    }
  ]
}
```

> 本知识库已按此形状写好生成脚本 `.memoria/agent/scratch/seed_cards.py`（字段与上述示例**逐字一致**，未自创字段）。

**✅ 三个待明确项已裁定（2026-10-10，Memoria 开发者）**：

1. `type` ∈ `basic | cloze | reverse` 三个都允许：`basic` = front 问 / back 答；`cloze` = front 里用 `{{c1::…}}` 标记挖空、back 放完整原文；`reverse` = 正反互换。
2. `source` 允许命名空间（它是追溯标签、不是枚举）⇒ `agent:errors.json` / `agent:sidecar` 合法，不加新字段。
3. `kp_id` / `file` 允许空串 `""`（**不是 `null`**）—— 保持字段存在且为 `str` 的一致形状；空串＝无知识点锚点的卡（如错题卡），追溯靠 `source`。

> **追加硬规则**：`cloze` 卡 front 若无 `{{c1::…}}` 标记 ⇒ 工具**拒绝整批**。**落卡状态**：本库 `cards.json` 已建 **80 张**（19 错题 + 61 KP），2026-10-10 23:55 落地；此后一律走 `review_cards_upsert`，**不再直接写盘**（§3.2）。

### 2.3 ⚠ 规格分叉：`docs/requirements.md` §4 与实现不符

| 位置 | 描述 | 磁盘现实 |
|---|---|---|
| `docs/requirements.md:255-270` | 数据必须存 `.memoria/learning_records/`，一词一 YAML | **零文件**（该目录不存在） |
| `docs/requirements.md:311-343` | 进度存 `progress_summary.json`，含 `mastery_level` 0-5 | 实际是 `review/progress.json` + FSRS-5（`fsrs.py` 读写） |
| `docs/error_log_format.md:105-107` | 卡片只存 `review/cards.json`、进度只存 `review/progress.json`、`errors.json` 是**独立第三类**，互不写入 | ✅ 与实现一致 |
| `docs/agent_specification.md:25,184` | 指向 `requirements.md` §3 的间隔重复算法 | 实际算法是 FSRS-5（`fsrs.py` 模块头声明，19 参数） |

**✅ 已裁定（2026-10-10）**：权威 = `docs/error_log_format.md` + `fsrs.py`（实现）。`docs/requirements.md` §4（`learning_records/*.yaml`、`progress_summary.json`、`mastery_level`）**已在本库标注为「历史设计稿，从未实现」**（见该文件 §4 顶部警示），**不要照它写文件**。

### 2.4 `errors.json` 的既成 schema（供 `review.error_add` 参照）

顶层（`.memoria/agent/review/errors.json:1-10`）：`schema_version` / `file_type` / `kb` / `created_at` / `updated_at` / `timestamp_convention` / `spec_ref` / `sessions[]` / `errors[]`。

字段与枚举约束见 `docs/error_log_format.md`：

- `skill` ∈ {`speaking`, `writing`}；
- `type` ∈ 9 个枚举值（`spelling`/`grammar`/`collocation`/`word_choice`/`tense`/`article_plural`/`capitalization`/`word_form`/`register`）——**没有 `punctuation`**；
- `kp_refs` **至少一条**且必须指向已存在的 KP；
- `original` 须与用户原话**逐字一致**。

> **已知违规 2 处**（现存于文件中）：有 2 条用了枚举外的 `punctuation`。
> 这恰好说明**为什么需要领域工具**：现在全靠智能体自觉，已经漏了。

---

## 3. R2 设计建议：领域工具，而不是「通用 JSON 写入」

**不建议**开放通用 JSON 写入（哪怕限定 `review/**`）：事实源一旦能被任意写入，schema 就没人守了。

建议这 5 个工具：

| 工具 | 作用 | 关键约束 |
|---|---|---|
| `review.cards_upsert` | 建/改卡，**收数组**（60+ 张卡不能一张一个调用） | 按 `card_id` 幂等；**schema 校验 + 拒绝坏卡**（不许静默跳过）；写入前备份；可撤销 |
| `review.card_disable` | 禁卡（不删定义，只停止调度） | 保留下一次到期日以便恢复 |
| `review.due_list` | 取今日到期 | 内部调 `fsrs.py due`，**不许自己算日期** |
| `review.grade` | 评分 1..4 | 内部调 `fsrs.py grade`（幂等键 = card_id + review_date） |
| `review.error_add` | 追加错题 | 按 §2.4 校验 `skill` / `type` 枚举、`kp_refs` 非空且存在 |

### 3.1 非目标

- ❌ 通用 JSON / YAML 写入；
- ❌ 让智能体直接改 `progress.json`（它只该由 `fsrs.py` 写）；
- ❌ 把学习状态写进 sidecar（知识语义与学习状态必须分离）。

### 3.2 已交付（2026-10-10，本库实测）

| 工具 | 实测结果 |
|---|---|
| `pwsh` / `cmd` | ✅ 已挂上本库智能体工具集；每条命令弹审批，回传 stdout / stderr / exitCode |
| `review_cards_upsert` | ✅ 实测写入成功：`新增 0 张、更新 2 张，当前共 80 张`，txid `20261010T161234Z-01`；写前自动备份、可撤销 |
| `review_due_list` | ✅ `--date 2026-10-11` 返回 **80 张到期**（内部走本库 `fsrs.py`，未自行推算日期） |
| `review_card_disable` / `review_grade` / `review_error_add` | ✅ 已挂上（`grade` 幂等键 = card_id + 评审日；`error_add` 校验枚举 + `kp_refs` 存在性 + `original` 逐字） |

**建卡纪律（硬约束）**：卡片定义**不得**直接写 `cards.json` —— 一律走 `review_cards_upsert`（schema 硬校验 + 备份 + 可撤销）；`progress.json` **只由** `fsrs.py` 写。

---

## 4. R3 复习卡管理视图

**必需**：

1. 卡片列表：`card_id` / `type` / 所属 `file` / `state` / **next due** / `reps` / `lapses`；
2. **单卡编辑**（front / back）——卡面例句抽错、口吻不对时，人要能修；
3. **禁卡 / 删除**；
4. 顶部显示「今日到期 N 张」并一键进入复习。

**可选**：按来源过滤（`kp_id` / 错题 id）。

**非必需**：统计图表（没有它也能用）。

---

## 5. 验收标准

| # | 做法 | 期望 |
|---|---|---|
| A1 | 用 `review.cards_upsert` 写入 60 张卡 | `python .memoria/agent/fsrs.py due --date <今天>` 返回 60 张 |
| A2 | 故意写一张缺 `card_id` 的卡 | **被工具拒绝**，而不是静默丢弃（对照 §2.1 的坑） |
| A3 | 写入后点「撤销这一批」 | `due` 回到写入前的结果 |
| A4 | 追加一条错题 | `errors.json` 仍是合法 JSON，`spec_ref` / `sessions` 未被破坏 |
| A5 | 智能体请求执行 `python fsrs.py due` | 弹出审批（显示完整命令 / cwd / 超时），批准后回传 stdout / exitCode |

---

## 6. 附录：已有产物

- **`.memoria/agent/scratch/seed_cards.py`**（**v2：不写任何文件**）：按 sidecar 与 `errors.json` 生成 `review_cards_upsert` 的 `cards` 参数，内置 4 项硬校验（字段齐全 / `type` 枚举 / `cloze` 必须含 `{{c1::…}}` / 题面不得泄露答案），支持 `--emit-json` 与 `--changed-only`。v1 的「写 cards.json + 调 `fsrs.py init`」能力已删除——那是工具交付前的临时通道。
- **本需求单的提出方**：AAA_Vocab 知识库智能体。**2026-10-10 起它已获得 shell（`pwsh` / `cmd`，逐次审批）与 5 把 `review_*` 工具**，R0–R2 全部闭环（实测见 §3.2）。
