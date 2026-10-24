# 文档锚点债清偿 · test_doc_anchors.py 13/14 → 14/14

> **任务**：task-125 ｜ **Owner**：`doc-consistency` ｜ **日期**：2026-10-25
> **结果**：`pytest tests/test_doc_anchors.py` **14 passed**（原 13 failed / 1 passed）。
> **改动**：仅 `docs/**` 锚点行号；未改 `src/**`；未 commit。

---

## 1. 逐项归因（13 个失败项，全 A 类）

测试规则：对每个锚点符号，测 `_symbol_line()` 取源码当前行，再断言 `<basename>:<当前行>` 子串存在于对应文档。13 个失败项全部是 **A 类（仅行号漂移，符号仍在）**，逐一 grep 确认符号存在且行号漂移：

| 符号 | 文件 | 旧行（文档引用） | 新行（源码实测） | 偏差 | 类 |
|---|---|---|---|---|---|
| `_agent_kb` | ui.py | 1306 | **1325** | +19 | A |
| `agent_session_delete` | ui.py | 1382 / 1367 | **1401** | +19 / +34 | A |
| `agent_session_rename` | ui.py | 1419 | **1438** | +19 | A |
| `agent_ask_cancel` | ui.py | 1279 | **1298** | +19 | A |
| `agent_usage_stats` | ui.py | 1475 | **1494** | +19 | A |
| `save_document` | document.py | 317 | **319** | +2 | A |
| `confirm_kp_range` | document.py | 1427 | **1513** | +86 | A |
| `update_kp` | document.py | 1789 | **1875** | +86 | A |
| `rename_kp_id` | document.py | 2004 / 2006 | **2090** | +86 / +84 | A |
| `detach_link_instance` | document.py | 2495 / 2428 | **2581** | +86 / +153 | A |
| `apply_link_instances` | document.py | 2560 | **2646** | +86 | A |
| `wrap_text_as_link` | document.py | 2888 | **2974** | +86 | A |
| `validate_kb` | document.py | 2068 | **2154** | +86 | A |

- **B 类（符号消失/改名）**：0 —— 13 个符号全部经 `_symbol_line` 命中（若消失会 raise AssertionError）。
- **C 类（测试写错）**：0 —— 测试逻辑正确，确实是文档锚点过期。

**漂移根因**：`ui.py` 顶部一个 ~19 行块（`agent_ask_start/poll/sessions_list` 附近）被插入，使 5 个 agent RPC 整体 +19；`document.py` 中部一个 ~86 行块（KP/link 相关函数附近）被插入，使 `confirm_kp_range` 及其后的 8 个函数整体 +86；`save_document` 单独 +2（顶部小改）。

---

## 2. 修了什么（逐符号、逐文件）

按纪律**逐项 grep 确认后**做符号锚定替换（每个替换 = 符号名后紧跟的 `basename:旧行` → `basename:新行`），**未批量平移**、**未碰区间内数字**、**未碰未命名该符号的其它行号**。

改动文件（5 个，与测试 ANCHORS 引用集一致）：

| 文件 | 符号 |
|---|---|
| `docs/design/agent-capabilities.md` | `_agent_kb`、`agent_session_delete`、`save_document`、`confirm_kp_range`、`detach_link_instance`、`apply_link_instances`、`validate_kb` |
| `docs/design/agent-plugin-design.md` | `agent_session_delete`、`save_document`、`confirm_kp_range`、`update_kp`、`rename_kp_id`、`detach_link_instance`、`apply_link_instances`、`wrap_text_as_link` |
| `docs/design/documentation-changelog.md` | `save_document` |
| `docs/reference/hard-constraints.md` | `save_document` |
| `docs/reference/agent-guide/10-data-layout-and-host-embedding.md` | `agent_session_delete`、`agent_session_rename`、`agent_ask_cancel`、`agent_usage_stats`、`save_document` |

---

## 3. 过程中抓到并纠正的 3 处"误伤"（如实记录）

第一版脚本的正则太宽（"符号名后 40 字符内第一个 `basename:N`"），把 3 处**交叉引用**当成了该符号的定义行，已逐处回退：

| 位置 | 误改 | 纠正 | 原因 |
|---|---|---|---|
| `10-guide.md:99` | `document.py:411 → 319` | 回退为 `411` | `:411` 是 `save_document` 内部"增量维护"路径的交叉引用，非其 def 行（319） |
| `agent-plugin-design.md:260` | `document.py:1509 → 1513` | 回退为 `1509` | `:1509` 是 `sync_pending_for_file` 在 `confirm_kp_range` 内的调用点，非 def 行（1513） |
| `agent-capabilities.md:221` | `document.py:2682-2689 → 2646-2689` | 回退为 `2682-2689` | `:2682-2689` 是 `apply_link_instances` 的"all-or-nothing"行为区间，非 def 行（2646） |

（另有 `_agent_kb` 首轮因"basename 在符号名前"而漏改，已手改。）

这印证了任务纪律："**不许批量平移**"——符号名后跟着的第一个行号不一定是它的定义行。

---

## 4. 残留债（未修，如实登记，供 Lead 判断是否另立项）

本测试**只守卫**「符号定义行的 `<basename>:<当前行>` 子串」，以下两类**不在本测试覆盖内**、也**未在本任务修**，是我明确识别出的**未守卫锚点债**：

1. **RPC 区间跨度末尾号**：`10-guide.md §2.15` 的 RPC 列出写法是 `符号名 ui.py:START-END`，我把 START 改为 def 行，但 END 仍是旧号（如 `agent_ask_cancel ui.py:1298-1305`，END 应为约 1330 的下一函数边界；`agent_session_delete ui.py:1401-1418`，END 应为约 1437）。这些 END 是**相邻内部行号**，测试不查。
2. **函数体内交叉引用**：如 `save_document` 内部的 `os.replace :341-347`、frontmatter `:335-338`、`document.py:317-430`/`:317-393`/`:317-368` 这类区间起点（部分已随 `317→319` 更新、部分因无符号名相邻而未动），以及 `confirm_kp_range` 的 `:1386-1399`/`:1414-1419` 等起止行硬校验区间——这些是**函数内部步骤的行号**，漂移同样 +2/+86，但不在本测试 ANCHORS 或断言范围内。

**建议**：若要让"改动会移动锚点"这一守卫覆盖到区间/内部行号，需**扩充测试**（例如为区间起点也加锚点条目，或引入"区间锚"断言）——这超出本任务范围，登记待 Lead 定。

---

## 5. 验收

| 关闭条件 | 结果 |
|---|---|
| 13 项逐项归因（A/B/C + 证据） | ✅ §1 表 |
| A 类全修；B/C 登记 | ✅ 13/13 A 类已修；B=0、C=0 |
| `pytest tests/test_doc_anchors.py` 如实记录 | ✅ **14 passed** |
| 报告落 `artifacts/agent/verify/doc-anchors-debt-2026-10-25.md` | ✅ 本文件 |
| 不改 `src/**` | ✅ 仅动 `docs/**` 5 文件 + 本报告 |

**复跑命令与结果**：
```
python -m pytest tests/test_doc_anchors.py -q
..............                                    [100%]
14 passed in 1.31s
```
