# 复习卡题型与作答交互需求（R4 设计稿）

> **用途**：把「复习只有一种交互 —— 看题面、揭晓、点四档熟悉度」这个现场问题，整理成可施工的需求，交给 Memoria 开发者。
> **来源**：AAA_Vocab 知识库使用者本人的使用反馈 + 智能体的磁盘实测（会话 `session-20260921T111525Z-ab1ac72c`），不是凭空设计。
> **取证日期**：2026-10-11（行号 / 张数对应当日 19:20 前后磁盘内容）；**21:29 复核**：写入端已放开新题型，见 §1.6。
> **上游**：`docs/memoria_feature_requests.md`（R0–R3）——本文件是其中 **R4** 的设计稿。
> **本文件不建知识点**（属产品文档，与 `docs/agent_specification.md`、`docs/requirements.md` 同类）。

---

## 0. 一句话

现状：**复习面板只有一种交互** —— 看题面 → 揭晓答案 → 点「重来 / 困难 / 良好 / 简单」。（写入端已能造新题型，但面板不认，见 §1.6）
目标：**先按题型作答**（选择 / 填空 / 写），客观题机器判分，主观题把作答交给智能体反馈；熟悉度档位由**答题结果派生**，而不是当题目本身。

---

## 1. 现场证据（2026-10-11 实测）

### 1.1 卡池只有三种「闪卡」型

`.memoria/agent/review/cards.json`（19:20 时共 86 张；21:29 复核为 90 张，见 §1.6）：

| `type` | 张数 | 形态 |
|---|---|---|
| `basic` | 36 | `front` 提问 → `back` 答案（含 19 张错题卡，`cards.json:6-186`） |
| `cloze` | 49 | 例句挖 `{{c1::…}}` → 揭晓原句 |
| `reverse` | 1 | 正反互换 |

三者本质相同：**题面 + 答案两段自由文本**。没有任何字段承载「选项」「正确答案」「可接受答案」「评分要点」。

### 1.2 唯一的交互写入口是「评分」

`.memoria/agent/sessions/ui-review.jsonl` 的 seq 0–10（11 条，2026-10-11 19:10–19:19 本地）全部是同一形状：

```json
{"type": "review/write", "data": {"tool": "review.grade.ui",
 "rel_path": ".memoria/agent/review/progress.json", "card_id": "...", "grade": 2}}
```

→ 面板把 **FSRS 的四档评分**当成了**答题界面**：没有输入框、没有选项、没有判分。
`progress.json` 的 `log` 同步有 11 条（`next_due` 全部由 `fsrs.py` 算出，这条是对的）。

### 1.3 「熟悉度」不是答题

四档（`grade` 1..4）是 **FSRS 的复习质量输入**（Again / Hard / Good / Easy），语义是「我刚才表现得怎么样」。
把它放在**作答之前**、且作为**唯一交互**，等于让使用者替机器判分 —— 使用者反馈原话：**「选择题/填空题能够选或者填，而不是选择我熟悉与否」**。

### 1.4 生成端也只造两种题

`.memoria/agent/scratch/seed_cards.py`（v2）只产出 `cloze`（从例句挖空）与 `basic`（自检 / 口述）；无 MCQ、无短答、无开放题。

### 1.5 ⚠ 规格分叉：这些题型**早就写进规格了**

`docs/agent_specification.md` 里早就定义过，只是**一条都没实现**：

| 位置 | 已定义的内容 | 实现状态 |
|---|---|---|
| `docs/agent_specification.md:34`（§2.3） | **三种题型**：`:37` A. Multiple Choice（干扰项取混淆矩阵 / 已学词）· `:46` B. Short Answer · `:52` C. Fill-in-the-Blank | ❌ 0 条落地 |
| `docs/agent_specification.md:92`（§3.2） | 复习模式：「逐个呈现题目 → **收集作答** → **立即给出正确答案与解释**」 | ❌ 只有评分 |
| `docs/agent_specification.md:176`（§5.2） | 评估原则：渐进难度、语境考查、**即时反馈**、错因解释 | ❌ 只有四档 |

→ 这不是新设计，是**既有规格未实现**。R4 应被视为**补齐 §2.3 / §3.2**，不是另起炉灶。

### 1.6 复核实测：写入端**已经**放开了新题型（2026-10-11 21:29）

在同一会话内真机写入 4 张新题型卡，**全部通过**（`review_cards_upsert` 逐次回「已写入」）：

| 卡 | `type` | 用到的判分字段 | 结果 |
|---|---|---|---|
| `blend#mcq` | `mcq` | `options` / `answer` / `explain` | ✅ 落库 |
| `blend#gapfill` | `gapfill` | `answer` / `accept` / `explain` | ✅ 落库 |
| `resonate-with#short` | `short` | `explain`（评分要点写在 `back`） | ✅ 落库 |
| `blend#produce` | `produce` | `explain`（评分要点写在 `back`） | ✅ 落库 |

随后 `python .memoria/agent/fsrs.py init` 四张全 `{"status": "ok", "state": "new", "due": "2026-10-11"}`；卡池 86 → **90** 张。

⇒ **写入端已完成**：`type` 现已覆盖 §2 表中除「`cloze` 升级输入框」外的全部题型。**字段是平铺的**（`options` / `answer` / `accept` / `explain` 直接挂在卡对象上），**不是** §2 曾建议的嵌套 `question` 对象 —— 施工请以实际 schema 为准。

**未变的部分**（同为 21:29 实测）：

- `.memoria/agent/sessions/ui-review.jsonl` 仍 **12 行**，`seq 0–10` 的写入口**仍然只有** `review.grade.ui` ⇒ 面板**没有**作答面、没有判分、也没有作答文本的去处；
- 「重来」= `grade 1` 的原状未变。

⇒ 缺口**不是「能不能写」，而是「写了面板不认」**：智能体已能造 `mcq` / `gapfill`，但复习面板大概率仍按 `basic` 闪卡渲染（新题型的实际呈现方式待开发者确认）。**R4 的施工重点应从「扩数据模型」下移到 §3 交互 + §4 反馈回路。**

---

## 2. R4.1 数据模型：`type` 扩型 + `question` 对象（向后兼容）

**现状（2026-10-11 21:29 更正）**：`review_cards_upsert` 已**接受** `mcq` / `gapfill` / `short` / `produce`（实测 4 张全部落库，见 §1.6）⇒ **写入端无需再改 schema**，卡池侧的瓶颈只剩呈现与作答交互（§3 / §4）。
> 本稿 v1 曾据工具契约判定「`type` 硬枚举 ⇒ 智能体无法造新题型」；该判断已被实测推翻，保留此更正以免误导施工。

建议 `schema_version: 1 → 2`，**纯增量**：旧三型与 `front` / `back` 语义一字不改，新增题型 + 一个可选 `question` 对象。

```json
{
  "card_id": "blend#mcq-nuance",
  "kp_id": "blend",
  "file": "vocab/blend.md",
  "type": "mcq",
  "front": "选词填空",
  "back": "解析……",
  "question": {
    "stem": "The city is a ______ of historical heritage and modernity.",
    "options": ["blend", "mix", "combination", "compound"],
    "answer": [0],
    "explain": "a blend of 强调成分融为一体、和谐统一；mix 偏「放在一起但仍可分辨」。"
  },
  "grading": { "mode": "auto" },
  "source": "agent:sidecar",
  "created_at": "<UTC ISO-8601>"
}
```

建议的题型与 `grading.mode`：

| `type` | 作答方式 | 判分 | 必需字段 |
|---|---|---|---|
| `mcq` | 点选项 | `auto` | `options`（≥2）· `answer`（下标数组，支持多选）· `explain` |
| `gapfill` | 输入框填词 | `auto` | `answer`（主答案）· `accept`（可接受写法白名单） |
| `basic` / `reverse` | 心里作答 | `self` | 现有字段（**不变**） |
| `cloze` | **可升级**：有 `accept` ⇒ 输入框；无 ⇒ 维持揭晓 | `auto` / `self` | 现有字段 + 可选 `accept` |
| `short` | 单行输入 | `agent` 或 `self` | `expected`（参考答案）· `rubric`（要点） |
| `produce` | 多行写作 / 翻译 | `agent` | `prompt`（任务）· `rubric` · 可选 `model_answer` |

**新增硬校验**（同时落进工具与生成脚本）：

1. `mcq`：`options` ≥ 2 且互不重复；`answer` 下标全部合法；`explain` 非空；
2. `gapfill` / 带 `accept` 的 `cloze`：`accept` 非空（为空则退回 `self`）；
3. `short` / `produce`：`rubric` 与 `expected` 至少有一个；
4. **题干不得泄露答案**（沿用现有 `answer_leak` 规则，并把 `options` 纳入检查）；
5. 旧卡**零改动**仍合法（新字段全部可选）。

---

## 3. R4.2 交互：先作答，再（才）出现档位

```
题面 → 按题型渲染作答面 → 提交 → 判分 → 显示正确答案 + 解析 → 档位（自动派生，可覆盖）→ 下一题
```

- `mcq`：选项按钮，选中即提交（不需要「揭晓」按钮）；
- `gapfill` / 带 `accept` 的 `cloze`：单行输入框，回车提交；
- `produce` / `short`：多行输入框 + 「交给智能体」按钮；
- `basic` / `reverse`：维持现状（揭晓 + 自评）。

**判分 → 档位映射（建议，最终由产品定）**：

| 作答结果 | 建议档位 |
|---|---|
| 错 | 1 `Again` |
| 对，但用了提示 / 二次尝试 | 2 `Hard` |
| 对 | 3 `Good` |
| 对且秒答（可选用时阈值） | 4 `Easy` |

**红线（不可违反）**：`due` 一律由 `.memoria/agent/fsrs.py` 计算 —— 面板与智能体都不许自己推日期；学习状态只落 `.memoria/agent/review/**`，**不许**进 sidecar。

---

## 4. R4.3 开放题 → 智能体反馈回路

使用者原话：**「开放题要能够输入给你进行反馈」**。当前架构下这条路**物理上不存在**：面板只往 `progress.json` 写评分，作答文本没有任何去处，智能体也没有工具能读到它。

分三阶段落地（每阶段可独立交付）：

**P0（最小可用，不改数据模型）**
多行输入框 + 「把这道题连我的答案发给智能体」按钮 → 预填进对话。智能体用现有 `read_kp` / `read_document` 取原文给反馈，**不落盘**。

**P1（作答可追溯）**
新增 append-only 事实源 `.memoria/agent/review/attempts.jsonl`，每行一条：

```json
{"ts": "<UTC ISO-8601>", "card_id": "blend#produce", "kp_id": "blend",
 "answer": "用户原文", "verdict": "auto|self|pending", "grade": 2, "elapsed_ms": 41000}
```

配套一把**只读**领域工具 `review_attempts_list`（供智能体读「待反馈」的作答）。
**不要让智能体直写 `progress.json`**（既有红线，见上游需求单 §3.1）。

**P2（反馈回到卡上）**
新增领域工具 `review_feedback_add`（智能体写：`card_id` + `attempt_ts` + 反馈正文 + `verdict`）→ 面板在卡面展示反馈、标记「已反馈」，并允许把反馈**计入档位**（仍由 `fsrs.py` 写调度）。

---

## 5. R4.4 承接上轮实测：「重来」按钮 + 同词多卡

| 现状 | 问题 | 需求 |
|---|---|---|
| 四档里的「重来」 | 文案像「再出一题」，实际是 **Again 评分 + 前进到下一张**（`.memoria/agent/review/progress.json:1024`：`grade 1` → `scheduled_days 1`） | 改名为「**忘了 / 再来**」并**补一句说明**；若确实要做「同词换题」，需要一个独立按钮 |
| 一个 KP 一张卡（`<kp_id>#cloze`） | 同一个词无法换个角度再考 | 支持**同词多卡**（`<kp_id>#mcq` / `#gapfill` / `#produce`…）与**同词轮换**（本库已手工验证：`blend` 现有 3 张，`cards.json:426` / `:826` / `:836`） |

---

## 6. R4.5 生成端：源材料**已经够造这些题**

以 `vocab/blend.md` 为例：

| 源位置 | 现成素材 | 可造题型 |
|---|---|---|
| `vocab/blend.md:61`（Gap-fill）+ `:78-79`（**🔑 Answer Key**） | 题目与答案都在 | `gapfill`（带 `accept`） |
| `vocab/blend.md:45`（**⚔️ Confusion Matrix**：本词 + 两个近义词 × 4 个维度） | 天然干扰项 | `mcq`（辨析题） |
| `vocab/blend.md:9`（释义 + Speaking/Writing example） | 双向释义 | `short`（词→义 / 义→词） |
| `vocab/blend.md:60`（**🎯 Active Output Drills**：`:64` Speaking scenario · Writing scenario · `:71` Word-weaving） | 天然开放题 | `produce` |
| 19 张错题卡（`card_id` = `err-*`） | `front` 就是【汉译英】原句 = 天然产出题 | `produce`（agent 判分，逐处 diff） |

→ `seed_cards.py` 需从「只会挖空」升级为**按源材料选型出题**，并沿用现有 4 项硬校验 + §2 新增 5 条。

---

## 7. 验收标准

| # | 做法 | 期望 |
|---|---|---|
| A6 | 写入 1 张 `mcq` + 1 张 `gapfill` + 1 张 `produce` | ✅ **已通过（2026-10-11 21:29）** —— 3 张全部落库、`fsrs.py init` 均 ok；`type: mcq` 并未被拒，见 §1.6 |
| A7 | 故意写一张 `answer: [9]`（越界下标）的 `mcq` | **被拒**，错误信息点明 `card_id` 与原因，且整批不落盘 |
| A8 | 复习一张 `mcq` | 界面**只出现选项**，四档不再是主交互；点对 → 自动 `Good`，点错 → 自动 `Again` |
| A9 | 复习一张 `gapfill`，输入大小写不同的正确词 | 按 `accept` 判对，并显示解析 |
| A10 | 复习一张 `produce`，写 2 句 | 作答出现在 `attempts.jsonl`；智能体读到并给反馈；反馈回到卡面 |
| A11 | 判分后看 `progress.json` | `log` 新增一条，`due` 由 `fsrs.py` 算出（面板 / 智能体均未自算日期） |
| A12 | 拿一张无 `question` 字段的旧卡复习 | 仍然合法、仍可复习（向后兼容） |

---

## 8. 非目标

- ❌ 通用 JSON 写入（上游需求单 §3.1 已否）；
- ❌ 智能体直写 `progress.json`；
- ❌ 把作答 / 掌握度写进 sidecar（知识语义与学习状态必须分离）；
- ❌ 语音评分、整篇写作批改（属 `docs/agent_specification.md:273` §10.1 的后续扩展，本批不做）。

---

## 9. 待拍板（需开发者 / 使用者定的开放问题）

1. `gapfill` 判分是否容忍词形与大小写（建议：`accept` 白名单 + 大小写不敏感）；
2. 开放题是否要智能体**打分**，还是**只给反馈**、档位由使用者确认（建议后者：反馈可解释，分数不必可复现）；
3. `attempts.jsonl` 是否记用时（`elapsed_ms`）—— 记了才支撑 `Easy` 的自动判定；
4. 同词多卡是否要**上限**（避免一个词生成十几张、把队列淹没）。

---

**文档状态**：草案 v2（2026-10-11 21:29 修订：更正 §1.1 / §2 的写入端判断，补 §1.6 实测）。**提出方**：AAA_Vocab 知识库智能体（在库内实测取证）。
**上游**：`docs/memoria_feature_requests.md`（R0–R3）；**规格依据**：`docs/agent_specification.md` §2.3 / §3.2 / §5.2。
