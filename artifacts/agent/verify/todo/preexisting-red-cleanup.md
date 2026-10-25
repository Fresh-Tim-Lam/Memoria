# 23 个预存红测试清偿报告

> **任务**：task-129 ｜ **Owner**：`doc-consistency` ｜ **日期**：2026-10-25
> **结果**：`pytest -q tests` **23 failed → 2 failed / 1460 passed**（+23 通过；剩 2 项为**产品代码缺陷**，按纪律只报不修）。
> **改动**：仅 `tests/**`（13 个测试文件）；未动 `src/**`；未 commit。

---

## 0. 前后对比

| 项 | 修复前 | 修复后 |
|---|---|---|
| failed | **23** | **2** |
| passed | 1437 | **1460** |
| 剩余失败性质 | — | `system_clipboard.py` 带 UTF-8 BOM（**产品代码缺陷**，③） |

---

## 1. ① `review_due_list` 的 `read_only` 口径 —— **判定：测试名单过时（工具声明正确）**

**证据链**：
1. 工具声明 `kb.py`：`name="review_due_list"` … `read_only=True`，描述写「**只读、免审批**」；同文件块注 **明文**写「`review_due_list` 只读 ⇒ `read_only=True`（免审批）」。
2. **实测处理器** `_review_due_list`：只调 `_review_run_fsrs(kb, ["due", ...])` 读今日到期 + 过滤 disabled + 组装 JSON ⇒ **不落盘**；对照 `_review_grade` 调 `["grade", ...]`（写状态）确实 `read_only=False`。
3. **实测全量**：`read_only=False` 的恰好是 `propose_write / pwsh / cmd / review_cards_upsert / review_card_disable / review_grade / review_error_add / review_feedback_add` —— `review_due_list` 不在其中（实测 `read_only=True`）。

**修法**：从 `tests/test_agent_tools_read.py` 的排除名单中移除 `review_due_list`（`tests/test_review_modal.py:605` 同类名单一并修）。
**未改工具声明**，因为工具确实只读——若为了让测试绿而把工具改成 `read_only=False`，会让一个**纯读**工具被迫走审批，是实质退化。

---

## 2. ② 18 个前端静态测试 —— 逐项分类（**全部 A 类，无 B/C**）

> A 类定义：测试断言了**旧行为**；下方每条均给出「代码行为确实变了且新行为正确」的证据。

| # | 测试 | 类 | 证据（代码现况） | 修法 |
|---|---|---|---|---|
| 1 | `test_agent_tools_read::test_new_read_tools_registered_and_read_only` | **A** | 见 §1 | 名单移除 `review_due_list` |
| 2 | `test_agent_questions::test_tool_is_registered_last_and_only_once` | **A** | `KB_TOOL_NAMES` 由 24→**39** 项，尾部追加 `review_summon/review_revoke/read_resource`（S3 MCP）⇒ 固定负下标整体失效 | 改按符号 `index()` + 相对次序 |
| 3 | `test_agent_scratch::test_scratch_tools_are_registered_read_only_and_closed` | **A** | 同上（原 `[-13:-9]`） | 同上 |
| 4 | `test_agent_session_query_trace::test_new_session_query_tools_registered_and_read_only` | **A** | 同上（原 `[-23:-19]` 等 4 条） | 同上 |
| 5 | `test_agent_tools_reference::test_reference_tools_registered_declared_and_read_only` | **A** | 同上（原 `[-19:]`） | 改为 `index("resolve_reference")` → `index("review_feedback_add")` 切片 |
| 6-7 | `test_agent_web::test_tools_are_registered_read_only[web_search\|fetch_url]` | **A** | 同上（原 `[-15:-13]`） | `index("web_search")` + 连续两把 |
| 8-9 | `test_agent_question_card`：`index_loads_the_card_as_the_last_script` / `card_styles_exist_and_reuse_tokens` | **A** | ① `index.html` 末位已由 `review-modal.js` → `review-manage.js`（新增 review-summon/manage），且中间新增 net-settings 等 ⇒ `[-7:]` 窗口失效；② CSS 测试用 `css.rsplit(marker)[1]` 取「marker 后**全部**」，把后续追加的 8+ 个块（含复习卡 `color:#fff`）算进本块 | ① 改相对次序；② 只取「marker → 下一个 `/* =====`」之间的块 |
| 10 | `test_review_modal::test_index_has_review_button_and_loads_module_last` | **A** | 同上（末位 review-manage.js） | 改相对次序 |
| 11 | `test_review_modal::test_review_attempts_list_read_only_registered_and_others_still_approved` | **A** | §1 同源（`review_due_list` 被误列写工具） | 名单移除并**新增** `review_due_list` 只读断言 |
| 12 | `test_review_modal::test_review_due_start_attaches_latest_feedback_only_when_present` | **A** | **实测**：`_review_feedback_add` 带 `score:3` ⇒ 按 docstring「带 verdict/1-4 score 折算落调度（写 progress.json）」⇒ s1 被排到未来，due 由 `[g1,m1,s1]`→`[g1,m1]`、progress.json 被创建。原测试用带 score 的调用验证「最近一条反馈」，与调度耦合 | 第二次调用去掉 `score`（保留「latest 覆盖 first」原意） |
| 13 | `test_review_modal::test_review_feedback_add_writes_kind_feedback_with_backup_and_audit` | **A** | 实测 `_review_feedback_rating`：`score:0.5` 不在 1-4 ⇒ 回落 `verdict:"partial"` ⇒ rating=2 ⇒ **必写 progress.json**（与反馈同批备份/撤销） | 断言由「不建 progress.json」改为「按设计创建」，保留「不改 cards.json」 |
| 14 | `test_agent_panel_token::test_thinking_and_process_text_use_the_same_markdown_pipeline` | **A** | P4e：两处均升级为 `renderAssistantBody(..., { final: true })`（最终文本走 render-core，公式/代码/列表都渲染） | 断言补第三实参 |
| 15 | `test_agent_panel_token::test_thinking_body_is_always_rendered_never_raw_text` | **A** | 同上 | 同上 |
| 16 | `test_display_preload::test_preload_renders_off_screen_without_touching_the_visible_ui` | **A** | P6a：`app.js` 注释明确「预渲染缓存与普通渲染**同源（render-core）**，**不得再走 legacy `R.render`**」⇒ 实为 `_rcRenderer().renderDocument(ast).container` | 断言更新为 render-core 路径 + 反向断言禁止回退 |
| 17 | `test_nav_predictor::test_policy_is_forwarded_and_hit_rate_is_measured` | **A** | **S8 修复后的正确行为**：`sanitize()` 只遍历 `DEFAULTS` 键、无 passthrough ⇒ `navPredictor`/`navHalfLifeDays` 会被清洗掉 ⇒ 转发**必须**用原始 `policy`（`app.js` 实为 `setPolicy(policy \|\| {})`）。原断言钉的是**修复前的错误行为** | 断言改为 `policy` + 反向断言禁止 `next` |
| 18 | `test_nav_predictor::test_index_loads_nav_modules_after_tab_order` | **A** | 末位已非 review-modal.js | 改相对次序 |

### ② 分类汇总
- **A 类（测试过时）：18/18**
- **B 类（代码回归）：0**
- **C 类（测试写错）：0**

---

## 3. ③ `system_clipboard.py` 源完整性 —— **判定：真实产品代码缺陷（BOM），报 Lead 派单**

**证据**：
1. 该文件前 3 字节 = `EF BB BF`（**UTF-8 BOM**）。
2. `test_source_integrity.py:49` 明确规则「`src/**/*.py` 首行不得有 BOM」，与仓库统一规范一致（该测试文件头注明 BOM 属"静默变坏"三类之一）。
3. `test_source_compiles` 失败信息：`SyntaxError: invalid non-printable character U+FEFF`（测试用 `read_text(encoding="utf-8")` 保留 BOM 再 `compile()`）。
4. 注意：`py_compile` **能**通过（它按 `utf-8-sig` 解码），所以这不是"文件根本不能用"，而是**违反仓库无 BOM 规范 + 在按裸 utf-8 读取的工具链下会炸**。
5. **全仓扫描**：`src/**` 下**仅此 1 个** `.py` 带 BOM。

**判定**：**测试规则正确、不过时；是产品代码缺陷**。
**修法建议（需 src 写权限，非本任务写域）**：把该文件转存为 **UTF-8 无 BOM**（内容不变，仅去 `EF BB BF` 三字节）。
```powershell
# 供派单者参考（不执行）：
#   $t = [IO.File]::ReadAllText($p)  # 自动识别并剥离 BOM
#   [IO.File]::WriteAllText($p, $t, (New-Object Text.UTF8Encoding($false)))
```
**风险**：极低（纯编码头，Python 3 两种读法结果一致）；建议与下个触及该文件的改动一并做。

---

## 4. 纪律遵守情况

| 纪律 | 履行 |
|---|---|
| 不许为了让测试绿而放宽断言 | ✅ 无一条断言被删除或放宽：① 保持"只读"严格性反而更严（新增 `review_due_list` 只读断言）；② 每条都附"代码行为确实变了"的证据；③ 只报不修 |
| 不动 `src/**` | ✅ 仅改 `tests/**` |
| 逐项分类、不批量平移 | ✅ 18 项按各自证据分别修，未批量替换 |
| 预存红不阻塞 S3/S4/S5 | ✅ 未触碰 S3 的 MCP 新文件；`read_resource` 等新工具仅作为"扩容原因"被提及 |
| 与 S3 冲突检查 | ✅ `KB_TOOL_NAMES` 新增项不影响修法（改为符号相对位置后**天然兼容任意追加**），无冲突 |

---

## 5. 发现的**工作区脏数据**（非我所改，如实报告）

跑全量 `pytest` 后 `git status` 显示两处**不属于本任务**的残留：

| 路径 | 现象 | 判断 |
|---|---|---|
| `tests/probe-kb/scale/scale-5k.md` | 第 1 行被塞入约 1500 个 `z` 字符（`## 规zzzz…模档位 · 单元 0`）、末行丢失换行 | **既有脏数据**：文件 `LastWriteTime` = **2026-10-20 20:32**（4 天前 P3b 会话期），而我改的 13 个测试**均不引用 `probe-kb`**（已 grep 验证为空） |
| `tests/probe-kb/.memoria/`（未跟踪） | 出现 `manifest.yaml`/`pending.json`/`kp_targets.json` 及其 `.bak`、`agent/fsrs.py` 等 | 某次把 `tests/probe-kb` 当真实库跑过写入（harness/交互测试副作用） |

**我没有清理这两处**，原因：① 不在本任务写域（`tests/**` 虽含，但这是**语料数据**不是测试代码，动它会改变后续探针/基准的口径）；② 无法确认是否有其他成员正依赖当前状态；③ 清理属"改数据"，应由 Lead 判断是否立项。
**建议**：`git checkout -- tests/probe-kb/scale/scale-5k.md` 恢复语料；`tests/probe-kb/.memoria/` 加进 `.gitignore` 或删除（它是运行期产物，不应入仓）。

---

## 6. 附带观察（非本任务三项，供 Lead 判断是否立项）

1. **`.-rm-front { color: #fff }`**：复习卡正面用 `background: var(--error)` + `color: #fff` 硬编码前景色。这不在两个被检查的 CSS 块内（故测试修好后不再误报），但**本身**违反"样式复用令牌"的惯例，且 `#fff` 在浅色/深色主题下对比度未验证。建议纳入前端规范清扫。
2. **工具面已 39 项**且持续追加：本次把 6 处"固定负下标"改为"符号相对位置"，这类脆性断言未来应作为 review 检查项（新增工具时不必改测试）。
3. `test_agent_tools_reference` 原 `[-19:]` 语义是"引用两把起到底"——本次改为到 `review_feedback_add` 为止，其后 `review_summon/review_revoke/read_resource` 由各自测试守护。若希望"从引用两把到末尾全部固定"，需同步维护该尾部清单（会再次变脆），故未采用。
