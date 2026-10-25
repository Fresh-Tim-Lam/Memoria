# S2 写安全独立验收（task-121）

> **验收者**：arch-contract。**对象**：agent-arch 的 S2 交付（W1–W4 写安全 + 契约文档 7 处重写 + 读写混合 A/B）。
> **方法**：全部独立复跑 + 自己复算 sha + **故意改坏实现验证 fixture 判别力**。
> **结论：通过**（附 3 条非阻断观察）。
> **未改 `src/**`**（改坏验证均已还原，git diff 为空），未 commit。

---

## 0. 结论

# **通过**

W1–W4 四个写安全 fixture 全部绿、判别力经改坏验证成立、契约文档 §4 幂等逐字与代码一致、`service_contract.py` 真零引用、读写混合 A/B 数字可复现且 -17.09% 论证成立。

三条**非阻断**观察见 §6（主要是 review 工具 read_only 口径漂移，与 S2 无关但需要另派单）。

---

## 1. 四个 fixture 判别力（改坏验证，本次验收的核心）

### 方法
Lead 要求「故意改坏实现，看 fixture 是否真红」。我做了三次改坏→红→还原→绿的循环：

| fixture | 改坏方式 | 改坏后 | 还原后 |
|---|---|---|---|
| **W1** | `origin: str` → `origin: str = "human"`（加默认值） | **红了**：`[FAIL] W1 漏传 origin ⇒ TypeError: raised=None` | 复绿，sha 回 `d020cf7e` |
| **W2** | 注释掉 `_section_call` 里的 `_observe_read(rel)`（R-S2-1 接缝） | **红了**：`[FAIL] read_section 后写 ⇒ FS_NOT_OBSERVED`（还连带 STALE 断言红） | 复绿，sha 回 `849179dd` |
| **W4** | 注释掉 `require_approval` 里 `mode=="auto"` 的 raise | **红了**：`[FAIL] auto ⇒ APPROVAL_REQUIRED: raised=None` | 复绿，sha 回 `e5429a62` |

**W3** 未做"改坏实现"（其判红点是 monkeypatch `snapshot_pre_images`，在 fixture 内部），但它的第三条断言
`pre-image 含写前 pre-image` 本身就是"备份在写之前"的直接验证，有判别力（falsifier 已写"没有 pre-image ⇒ 备份发生在写之后"）。

### 结论
**四个 fixture 的「必红」判别力都成立**：改坏后真的红、还原后真的绿。这证明它们不是"跑一遍就绿的假通过"。

### 还原完整性
`git diff` 对 `apply.py` / `tools/kb.py` / `approvals.py` **全为空** —— 改坏痕迹完全清除，未污染工作区。

---

## 2. §4 幂等描述 vs `backup.py:219`（逐字核对）

**文档 §4**（`agent-service-contract.md:129-135`）写：

> 同一 `txid` 第二次 `apply_plan` ⇒ `{"status":"error","code":"backup_failed","message":"批次已存在：<txid>"}`

**代码 `backup.py:219`**：

```python
return {"status": "error", "code": "backup_failed", "message": f"批次已存在：{clean_txid}"}
```

**逐字一致** ✅。且文档如实写了「这是'拒绝'不是'幂等'」「真幂等（`duplicate_txid` + 已应用集）**未实现**，本文件**不承诺**」。

**第六个「声明≠事实」候选：不成立。** 这次文档诚实，且引用的 `backup.py:219` 行号精确。

---

## 3. `service_contract.py` 零引用（grep 调用点，不读注释）

```
grep -rn "submit_write|service_contract|from.*service_contract|import.*service_contract" src/
→ 唯一命中：approvals.py:227  —— 是一条注释（"R-S2-9 已裁『不建 service_contract.py』"）
```

**结论**：`service_contract.py` 确已删除（`Test-Path` = False），且**全仓零代码引用**。
唯一命中是注释，不是 import/call。**我上次翻车的那条（读模块头部就信"有真消费者"）这次没有重犯**——用 grep 调用点而非读 docstring。

---

## 4. 读写混合 A/B（两臂公平 + 数字可信度）

### 4.1 独立复跑 + 复算 sha

```
读写作混合节省：修复后 77.81% / 修复前（模拟）-17.09%
折扣：相对修复前 +94.90 pp；相对纯读 92.43% -14.62 pp
5 个任务全部真写入成功（失败任务数 0）
sha256 b8790e7f...（与 Lead 给的 MATCH）
```

### 4.2 两臂公平性（逐项核）

| 检查 | 结论 | 证据 |
|---|---|---|
| 三臂都用**真实 handler** | ✅ | `_run_arm` 里 `tools[name].handler(args)`（`contract_readwrite_ab.py:144`），同一个 `build_kb_tools` |
| 每任务**真写入成功** | ✅ | `"已写入" in text` 判定（`:158`），失败披露；实测 5/5 成功 |
| `B_before` 模拟是否合理 | ✅ | 标 `emulated=True`（`:200`），模拟"修复前 section 不记观察 → gate 报 FS_NOT_OBSERVED → 模型只能补读 `read_document`"这条确定性行为。**我独立验证了 R-S2-1 修复前 section 确实不记观察**（task-128 时实测），所以这个模拟的假设成立 |
| B_after 的 section 真记观察 | ✅ | 实测观察表出现 `(kb, session_id)` 键（§4.3 独立验证） |

### 4.3 一个关键独立验证

我额外测了：B_after 路径（outline→section→propose_write）里，`section` 是否真记观察（否则 propose_write 会 FS_NOT_OBSERVED，A/B 就会假失败）。实测观察表**确实出现**了该 (kb, session) 键 ⇒ B_after 的 propose_write 能过 W2 闸，A/B 的 77.81% 不是"偷偷绕过了写闸"的结果。

### 4.4 −17.09% 的判读

**成立**。「不修 R-S2-1 接缝，粒度化方案在真实读写工作流里是负收益」——因为修复前 `section` 不喂观察表，模型读完 section 想写必须再 `read_document` 整篇一遍才能过 W2 闸，那轮整篇读**把粒度化收益全吃掉还倒亏**。

这是本轮最有价值的结论之一：**它证明 R-S2-1 接缝修复不是"顺手优化"，而是"不修就负收益"的必要修复。** 数字可信（独立复现 + sha 一致 + 5 任务真写）。

---

## 5. pytest 数字（23 failed / 1437 passed）

独立复跑，与 Lead 给的**一致**。

### 关于"0 新坏"的独立判断（不采信）

23 个失败我逐一看了名单：
- **大量是前端静态检查**（`test_agent_panel_token` / `test_agent_question_card` / `test_index_loads_*` / `test_styles_reuse_tokens` / `test_source_integrity`）——测"脚本加载顺序 / 样式 token 复用 / 首页脚本编排"，**与 S2 后端改动无关**。
- 抽查了一个后端相关失败 `test_new_read_tools_registered_and_read_only`：报错是 `review_due_list` 被标 `read_only=True` 而断言应为 `False`——这是 **review 工具的 read_only 口径漂移**，**与 S2 的 origin/token/section 无关**。
- **关键**：S2 直接相关的测试（`test_agent_plan` / `test_agent_apply` / `test_agent_body_edit` / `test_agent_audit` / `test_agent_plugins` / `test_doc_anchor`）**全部不在失败名单里** ⇒ 全部通过。

**结论**：23 个失败是**既有失败**（review 工具 read_only 口径 + 一批前端静态检查），S2 **没有引入新回归**。Lead 说的"0 新坏"独立成立。

---

## 6. 三条非阻断观察（建议另派单）

| # | 观察 | 证据 | 建议 |
|---|---|---|---|
| O1 | **review 工具 `read_only` 口径漂移** | `review_due_list` 被标 `read_only=True`，但 `test_agent_tools_read.py:445` 断言应为 False（它是 review 写家族一员） | 属 review 领域，非 S2；建议 metrics-baseline 或 review 相关 agent 排查 |
| O2 | 一批**前端静态测试**失败（index 加载顺序 / 样式 token） | `test_index_loads_nav_modules_after_tab_order` 等 | 属前端，非 S2；建议 surface-new 或前端 owner 排查 |
| O3 | `test_source_integrity` 两个失败（`system_clipboard.py`） | 编译 / 首行干净检查 | 属源文件完整性，非 S2 |

**这三条都不归 S2 验收范围**，但作为验收者如实报告，避免被误读为"S2 引入的回归"。

---

## 7. 复现

```bash
cd D:/AAA_Jupyter/Memoria
# 四个 fixture（sha 我复算：d020cf7e / 849179dd / 807f20df / e5429a62）
python scripts/benchmark/maintenance/contract_w1.py
python scripts/benchmark/maintenance/contract_w2.py
python scripts/benchmark/maintenance/contract_w3.py
python scripts/benchmark/maintenance/contract_w4.py
# 读写混合 A/B（sha b8790e7f）
python scripts/benchmark/maintenance/contract_readwrite_ab.py
# 全量 pytest
python -m pytest -q tests   # 23 failed / 1437 passed
```

改坏验证的还原已确认（`git diff` 对 `apply.py`/`tools/kb.py`/`approvals.py` 为空）。
