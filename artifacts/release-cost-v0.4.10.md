# Memoria v0.4.10 — 造价（Agent compute cost）

> **用途**：v0.4.10 Release body 的造价段独立底稿（量级 + 核算依据 + 成本结构 + 不确定性）。
> 规则见 [release-copy.md §3](../conventions/release-copy.md)：**量级 / 统计口径 / 成本结构** 三者缺一不可，
> 且「造价与收益必须成对出现」。
> **作者**：release-manager（2026-10-26）。**草稿，待 Lead/人确认后再发布；不 commit。**

---

## English

### Magnitude

Roughly **CNY 250-600** (estimate; not itemised).

### Accounting basis

- **Counted separately.** v0.4.10 is estimated **on its own**, not merged into the earlier
  v0.4.7–v0.4.9 block that was already disclosed as one merged figure. The two figures are
  **never added together** (doing so would double-count shared sessions).
- **What the estimate is based on:** session rounds, the number of commits in this release
  (55 since v0.4.9), and team size. There is **no token-level ledger** for these sessions,
  so the number is an estimated order of magnitude, not a metered bill.
- **What it includes:** code, real-machine verification (WebView2 instances, CDP probes,
  time-series measurement), two design-review rounds for KG visualization, gate work, and
  release-material preparation.
- **What it excludes:** the human's own review time; electricity/hardware; and any future
  work (known debts are listed in the release body, not costed here).
- **Why a range and not a point value:** the missing token ledger means the uncertainty is
  in the tens of percent, not in single digit yen. Publishing a precise-looking number
  would be false precision.

### Cost structure (one line)

Most of the budget went to **real-machine verification and design review**, not to writing
code: repeating measurements on a real WebView2 app, chasing root causes that only appear on
real machines, and running the four-way KG visualization review (independent proposals,
cross-objections, rulings).

### If you need an exact number

An exact figure would require a token-level ledger (per-session input/output tokens and unit
price). That ledger does not exist for this block; adding it retroactively is not possible —
only future releases can start metering.

---

## 中文

### 量级

约 **250–600 元人民币**（估算，非逐项计量）。

### 统计口径

- **单独统计。** v0.4.10 单独估算，**不并入**此前已披露为合并统计的 v0.4.7–v0.4.9 块；
  两块数字**不相加**（相加会把共享会话重复计费）。
- **估算依据**：会话轮次 + 本版提交量（自 v0.4.9 起 55 个提交）+ 团队规模。
  这些会话**没有 token 级台账**，因此这是估算量级，不是计量账单。
- **包含**：写代码、真机验证（WebView2 实例 / CDP 探针 / 时间序列测量）、
  KG 可视化的两轮设计评审、门禁建设、发版材料准备。
- **不包含**：人自己的审阅时间；电费/硬件；后续工作（已知债务在 Release body 里登记，不计价）。
- **为什么给区间而不是一个数**：没有 token 台账，误差在几十个百分点量级；
  写一个看起来很精确的数字等于**假精确**。

### 成本结构（一句话）

主要花在**真机验证与设计评审**，不是写代码：在真实 WebView2 上反复测量、
追只在真机上出现的根因、以及 KG 可视化的四方评审（独立提案 → 交叉异议 → 逐条裁决）。

### 如果要精确数字

需要 token 级台账（每轮输入/输出 token + 单价）。这一块没有台账，事后无法补录；
只有从下一个版本开始才能做到计量。

---

## 附：为什么不能只写「大量改进」

`release-copy.md §3` 明确：**禁止只写「优化了多少」而不写「花了多少」**。
造价与收益必须成对出现；没有量级/口径的「造价」不可核对，等于没写。
