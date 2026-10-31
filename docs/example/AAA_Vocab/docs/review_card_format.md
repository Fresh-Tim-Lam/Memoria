# 复习卡编撰规范（Review Cards Format）

> **用途**：本库复习卡（`.memoria/agent/review/cards.json`）**该出成什么题型、卡面怎么写、判分字段怎么填**。解决「题面明明是开放题，复习面板却只给翻面」这一类问题。
> **上游**：`docs/agent_specification.md:34` §2.3（三种题型设计）· `:92` §3.2（收集作答 → 即时反馈）；`docs/review_card_requirements.md`（R4 交互需求稿，属产品侧）。
> **不建知识点**（属体例文档，与 `docs/vocab_format.md` 同类）。
> **状态**：生效中，2026-10-13 立规。

---

## 0. 一句话

**卡面要求学习者「写出内容」的，就一定要给输入框（`cloze` / `gapfill` / `mcq` / `short` / `produce`）；只有「心里过一遍就能对答案」的问答、辨析、正反互查，才用 `basic` / `reverse` 翻面自评。**

---

## 1. 题型选择表（先问「卡面要求学习者做什么」）

| 卡面要求的动作 | 该用 | 作答面 | 判分 |
|---|---|---|---|
| 在一句话里填一个词／短语 | `cloze`（带 `accept`）· `gapfill` | 单行输入框 | `auto` |
| 从几个候选里挑一个 | `mcq` | 选项按钮 | `auto` |
| 用**一句话**写出来（释义、介词轨、「为什么不能用另一个」、近义分界） | `short` | 单行输入框 | `agent` |
| 写**多句／成段**（翻译、造句、复述汇总、辨析说明、口语 Part 2 场景） | `produce` | 多行输入框 | `agent` |
| 心里回忆定义、正反互查 | `basic` / `reverse` | 翻面自评 | `self` |

对照依据：`docs/agent_specification.md:46` §2.3 B「Short Answer」本就列了 *Appropriate context usage explanation*（语境用法说明）与 *Nuance distinction between near-synonyms*（近义辨析）—— 这两类**注定是 `short`**，写成 `basic` 就是把产出题降级成再认题。

---

## 2. 判分字段怎么填

- `short` / `produce`：`"judge": "agent"`；`"input": "single"`（一句话）或 `"multi"`（成段）；`back` 放参考答案／方向；`explain` 写**逐条可核对的评分要点**。
- `mcq`：`options`（≥2、互不重复）＋ `answer`（必须 ∈ options）＋ `explain`。
- `gapfill` / 带 `accept` 的 `cloze`：`answer` ＋ `accept`（可接受的写法／大小写）＋ `explain`。
- 判定口径：要点全中 → `correct`；主干对但缺解释／缺一层 → `partial`；动词、介词轨、答案本身错 → `wrong`。

---

## 3. 卡面写法

1. 一张卡只考**一个点**——判分才给得出 `partial`。
2. 题干**不得泄露答案**；要写几样东西就写明（「写出介词轨**并**说清为什么不能用 X」）。
3. 库内有出处的，把 `文件:行号` 写进 `back`，复习时能一键回原文。
4. 考产出（写句子）用**英文题干**更自然；考辨析（说理由）中文更省时间。

---

## 4. 判分路由（`judge: agent` 的卡）

作答落 `.memoria/agent/review/attempts.jsonl`（`verdict: "unjudged"`）→ 智能体用 `review_attempts_list` 取回 → 用 `review_feedback_add` 写判定与反馈 → 折算 1–4 档落调度。
**红线**：`due` 一律由 `.memoria/agent/fsrs.py` 计算；学习状态只落 `.memoria/agent/review/**`，不进 sidecar。

---

## 5. 常见坑

- **`basic` 顶替 `short` / `produce`**：题面写着「写出…并说清…」，界面却只有「翻面」——学习者没有输入位，等于白做。（本规范立规起因：`impart-instil-cultivate#2`。）
- 题干泄露答案；一张卡塞三四个考点。
- `explain` 写成「回正文再看一遍」这类不可核对的空话。
- 「复述整页」类自检卡也应是 `produce`，不是 `basic`。

---

## 6. 变更记录

- **2026-10-13 立规**：§1 题型选择表 · §2 判分字段 · §3 卡面写法 · §4 判分路由。同日按本规范把 4 张 `basic` 卡改为输入型：`impart-instil-cultivate#2` → `short`；`blend#confusion`、`ways-to-say-you-like-something`、`story-roles` → `produce`。
- **2026-10-13 全库改型（第二批）**：写入端支持输入型作答后，按 §1 扫全库 98 张卡，把题面本身就是产出题的 27 张 `basic` 逐张改型并补 §2 评分要点 —— 19 张错题卡 `err-*`（`short` 9 张 / `produce` 10 张）、2 张顽疾改错卡 `drill-*`（`short`）、`blend#collocation` / `resonate-with#confusion` / `describing-heat` / `point-vs-example`（`produce`）、`impart-instil-cultivate#3` / `#4`（`short`）。改后卡池 98 张（`basic` 35 → 8）。
- **2026-10-13 新增开放题 3 张**：`ways-to-say-you-like-something#upgrade`（口语→书面升格）· `story-roles#produce`（Part 2 说一部片子，位置与道德标签分开）· `impart-instil-cultivate#5`（三词造句看介词轨），卡池 98 → 101。
