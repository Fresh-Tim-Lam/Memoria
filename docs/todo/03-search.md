# 3. 检索引擎 — 活跃详情（原文逐字）

> **本文件是 `docs/todo.md §3` 的活跃详情**（2026-10-26 索引化搬迁，**原文逐字**，未改写）。
> **状态事实源 = `docs/todo.md` 索引行**；本文件只放详情。历史归档仍在 `docs/design/**`，不在此重复。

## 台账日期标签（2026-11-11 增补；非原文）

> 依据 [ledger-maintenance.md 规则 9](../conventions/ledger-maintenance.md)（日期标签必填）。本块是元数据，不改下方原文逐字表。

| ID | 📅 首次登记 | 🕒 最近复核 | 备注 |
|---|---|---|---|
| S06 | 2026-09-16（回溯，git `322be881` 首见） | 2026-11-11 | 人裁决：搜索留到 **0.7.x** 完善（延后，现在不修） |

<a id="s02"></a><a id="s03"></a><a id="s04"></a><a id="s05"></a><a id="s06"></a>

## 原文（逐字，自 docs/todo.md 搬迁）

## 3. 检索引擎

| ID | 任务 | 状态 |
| --- | --- | --- |
| S02 | R17 SearchKernel v2：双向生长汇合检索（查询侧语义扩张 + 库侧沿图/标签生长，按路径计分） | 💡 K1（未实现：`retrieval_fusion.py:149-161` 有 `graph_hits` 通道但检索未接线） |
| S03 | R16 检索反馈循环·库内模型（点击/有用无用学习，存 `.memoria/`，本地离线可删） | ⏳ K1（未实现：无 `search_feedback.py`，`ui.py` 无反馈 RPC） |
| S04 | R04 智能链接推荐 | 🔄 K1（Lexical 版已实现 `services/link_relevance.py` + `ui.py:626`；LLM 提议层未实现，`model_router.py:17-18` 为空槽） |
| S05 | R05 公式级语义检索 | 🔄 K1（公式归一化已并入语义检索 `services/text_normalize.py:11`；独立公式索引/AST 未做） |
| S06 | 搜索范围偏好跨库残留：上次停在「文件」时，新开库且未打开文件即搜索 → 报 `app.openFileFirst`，而范围按钮为 disabled 态 | 🔴 K1（`app.js:47`、`toolbar-search.js:143-146`；来源 agent-guide/07） |

***
