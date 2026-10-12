# 复习卡（Review Cards）工作交接文档

> **用途**：把「复习卡」这项工作**整体交接出去** —— 接手人/Agent **只看本文件**即可接手，无需读聊天记录。
> **性质**：**权威汇总**。本工作的设计历史此前被**追加**在 `docs/design/preview-render-refactor.md`（K5「预览渲染重构」）末尾（见 §8），**属产出时的放置不当**；本文件是它的**权威入口**。
> **状态日期**：2026-10-12（对应 `HEAD` 附近提交见 §2）。
> **本文件不写代码、不改口径**；接口真伪以 `文件:行号` 为准，未取证处**如实标注**。

---

## ① 一句话目标 + 人的原话需求

**一句话**：把复习从「对话里出题作答 / 一个手动点进去的模态面板」，升级为**可被 agent 呼出的悬浮矩形卡**；客观题**先作答、由后端判分**，主观题**交 agent 判分**，**答案不回前端**。

**与 K5 的关系**：复习功能最初作为 **R3「复习卡管理视图」** 被登记为 **K5 显示子系统的「视图需求」**（`docs/design/preview-render-refactor.md:822` 起 `## 附 R3`）。但 K5 文档本体是「**预览渲染重构**」的方案（改的是预览/源码双栏渲染），与复习卡是**两件事**。R3a / R3a-2 / R4 / R4-3 一路**追加**在该文档末尾 —— 这就是本次交接要纠正的「放置不当」。

**人的原话（逐字，含出处）**：

- **悬浮卡形态（逐字，已落盘）**：「本身复习卡片就是可以智能体呼出的一张矩形卡片，而不是一个手动点击进入的面板，当然用户可以手动点击面板进入 agent 设置好的卡片，以防没有及时回复 agent，悬浮卡片撤回不显示」—— 出处：`docs/design/preview-render-refactor.md:1133`（R4-3 节原文引用）。
- **题型/作答（逐字，已落盘）**：「**选择题/填空题能够选或者填，而不是选择我熟悉与否**」—— 出处：`docs/example/AAA_Vocab/docs/review_card_requirements.md:47`。
- **开放题反馈（逐字，已落盘）**：「**开放题要能够输入给你进行反馈**」—— 出处：`docs/example/AAA_Vocab/docs/review_card_requirements.md:163`。

**以下三句在仓内未落盘逐字原文（来源＝任务派发描述 / 父 agent 转述，本次未能在 `docs/**` 与 `docs/example/**/.memoria/**/sessions/**.jsonl` 中检索到逐字文本，**如实标注、不作“已核实”**）**：

- 「**答案不回前端 / 判分交后端与 agent**」——**注意**：这条的**裁定事实**在仓内有据（`preview-render-refactor.md:1089` 记「人已批准」「答案默认不回前端」，判分放后端或交 agent），但**逐字措辞**未在仓内找到。
- 「**不需要兼容我们没有用户**」——**未在仓内找到逐字文本**；旁证：提交 `7609c763` 的标题为「`review_due_list` 返回纯 JSON（**去掉了向后兼容**）」，语义与之一致，但**不能据此认定逐字原话**。
- 「**沙盒先搁置**」——**未在仓内找到任何文本**（`docs/**` 与示例库 sessions 检索均 0 命中），**无法核实**。

---

## ② 现状总表（一眼看清做到哪了）

**已完成（各带提交 sha；sha 与说明取自 `git log` 与 `docs/conventions/docs-management.md §4.2` 台账行）**：

| 阶段 | 提交 sha | 日期 | 一句说明 + 关键读数 |
|---|---|---|---|
| **R2 基础五工具** | `d82e2cd2` | 2026-10-10 | `review/**` 事实源的五把领域工具 + `fsrs.py` 静默坑改 fail-closed |
| **R3a 方案 + R3a-2 补录** | `64946583` | 2026-10-11 | 模态弹窗方案（文档）；台账把 R3 入 K5 |
| **R3a 实现（模态复习界面）** | `952789ec` | 2026-10-11 | 模态复习界面 + 卡面旧式公式误判修复 |
| **R3a-2 卡面来源修正** | `7609c763` | 2026-10-11 | `review_due_list` 直返**整段纯 JSON**（含卡面+状态），去掉人读文本段、**不做向后兼容** |
| **R3a-2 幻影卡修复** | `1bbe6036` | 2026-10-11 | `review_grade` 拒绝不存在的 `card_id`（工具层 + fsrs 层**双层 fail-closed**），不再静默建幻影卡 |
| **R4 P0** | `da433b3b` | 2026-10-11 | `type` 放开 7 种 + 判分字段 `judge/options/answer/accept/explain/input` + 按类型硬校验。`pytest 1399→1410` |
| **R4.2** | `7d56514e` | 2026-10-11 | **后端答案隔离**（`_review_ui_hide_answers`）+ 后端判分入口 `review_submit_one`。传输层直证：UI 取卡 `answer/accept/explain` 命中 **0**、`options` 保留；agent 工具仍命中 9。`pytest 1410→1414` |
| **R4.3** | `e6ac8ae3` | 2026-10-11 | 作答交互：`mcq` 选项 / `gapfill` 输入 / 带 `answer|accept` 的 `cloze` 输入。`pytest 1414→1418` |
| **R4.2 补记（按需揭晓）** | `99a9356b` | 2026-10-12 | `cloze` 取卡把 `front` 挖空为 `{{cN::}}`、整键剔 `back`；新增只读 **`review_reveal_one`** 只在 cloze 翻面时调。`pytest 1421→1426` |
| **R4 P1** | `cf1301b6` | 2026-10-12 | 作答记录 **`attempts.jsonl`** + 只读工具 `review_attempts_list` + `short/produce` 输入框解锁。`pytest 1426→1433` |
| **R4 P2** | `bf854d9b` | 2026-10-12 | agent 反馈写回 **`review_feedback_add`** + 作答 `attempt_id` + `review_attempts_list` 预过滤 + UI 显示上次反馈。`pytest 1433→1440` |

> R4 P0 条目对应台账行：`docs/conventions/docs-management.md:340`；R4.2 → `:341`；R4.3 → `:342`；R4.2 补记 → `:343`；R4 P1 → `:344`；R4 P2 → `:345`；R4-3 方案 → `:346`。

**方案已出、未施工**：

- **悬浮卡形态（R4-3）**：设计已落盘（`docs/design/preview-render-refactor.md:1131` 起 `## 附 R4-3`），**未改任何 `src/**`**。边界：**v1 只支持「作业进行中」呼出**（复用现有 250ms 轮询）；**作业结束后**要呼出/撤回想生效须 **v2** 新增「面板打开时的低频空闲心跳（≈5–10s）」。待拍板项 10 条（见 §5）。

**小项待办（未做）**：见 §5 末。

---

## ③ 架构与接口（接手人最需要的）

> 行号均为 2026-10-12 磁盘实况。**唯一接口事实源**：`src/memoria/services/agent/tools/kb.py`（agent 工具）、`src/memoria/presentation/api/ui.py`（UI 专用 RPC）、`resources/agent-prompts/fsrs.py`（调度内核）。

### 3.1 数据文件（`<kb>/.memoria/agent/review/`）

| 文件 | 定位（`文件:行号`） | 用途 / 写者 |
|---|---|---|
| `cards.json` | 常量 `REVIEW_CARDS_REL`，`src/memoria/services/agent/tools/kb.py:4135` | **卡定义**（`card_id/type/front/back/source/kp_id/file/judge/options/answer/accept/explain/input/disabled…`）。**只经工具写**（`review_cards_upsert` / `review_card_disable`，带备份+撤销）；**UI 只读** |
| `progress.json` | 常量 `REVIEW_PROGRESS_REL`，`kb.py:4136` | **调度状态 + 复习日志**。**唯一写者 = `fsrs.py`**（`resources/agent-prompts/fsrs.py:8`「本脚本读写」、`:185` 原子写）；UI 经 `review_grade_one` 间接写 |
| `errors.json` | 常量 `REVIEW_ERRORS_REL`，`kb.py:4137` | **错题本**；只经 `review_error_add` 追加（备份+撤销） |
| **`attempts.jsonl`** | 常量 `REVIEW_ATTEMPTS_REL`，`kb.py:4982` | **作答/反馈流水**（**追加式 JSONL**，只追加、不改写、不删除）。**两种记录**：作答记录**无 `kind`**（读端缺省视作 `"answer"` —— `_review_record_kind`，`kb.py:5188`）、反馈记录带 **`kind:"feedback"`**。写入口：`_review_append_attempt`（`kb.py:4998`，只被 UI 调）+ `_review_append_feedback`（`kb.py:5255`，被 `review_feedback_add` 调）；都不注册为工具 |
| `evaluations/**` | 目录（示例：`docs/example/AAA_Vocab/.memoria/agent/review/evaluations/{9_18_1.json,9_18_2.json}`） | **写作批改结构化记录**（既有产物）。**取证：`src/**` 中检索 `evaluations` 为 0 命中** ⇒ **不属**闪卡工具链的读写对象（来源＝示例库文件 + `docs/example/AAA_Vocab/docs/memoria_feature_requests.md:40` 的描述） |
| `backups/**` | 备份根：`.memoria/agent/backups/<session_id>/<txid>/{journal.json, files/<原相对路径>}`，见 `src/memoria/services/agent/backup.py:14` | 写入前的 pre-image 备份 + 栈式撤销，非复习专属 |

### 3.2 UI 专用 RPC（**只挂 `UIAPI`，agent 经 `ToolRegistry` 取不到**）

| RPC 名 | 定义 / 注册（`ui.py:行号`） | 干什么 | 是否写盘（写哪个文件） |
|---|---|---|---|
| `review_due_start` | `_review_ui_due` 定义 `:2258`；注册 `UIAPI.review_due_start` `:2355` | 取某日到期卡（整段 JSON），返回前**后端剔答案**（§3.4 规则①）；并挂载上次反馈 | **否**（只读） |
| `review_grade_one` | `_review_ui_grade` 定义 `:2287`；注册 `:2356` | 给一张卡评 1..4（内部走 `fsrs.py grade`） | **是**：写 `progress.json`（写前备份 `snapshot_pre_images`） |
| `review_submit_one` | `_review_ui_submit_one` 定义 `:2384`；注册 `:2476` | 客观题**后端判分**（`auto`）并揭晓 `answer/explain`；`judge∈{agent,self}` ⇒ `unjudged`；未知 id ⇒ `unreviewable` | **是**：**追加写 `attempts.jsonl`**（R4 P1 起；**不写** `cards.json`/`progress.json`） |
| `review_reveal_one` | `_review_ui_reveal` 定义 `:2524`；注册 `:2566` | `cloze` 翻面时**按需揭晓**：从 `cards.json` **原样读**返回完整 `front/back`+`answer/accept/explain`（不挖空、不剔 `back`） | **否**（只读） |

### 3.3 agent 工具（经 `ToolRegistry`；装配点 `build_kb_tools()`，`kb.py:673`）

**复习领域工具 7 把**（`文件:行号` 为 `Tool(...)` 定义）：

| 工具 | 定义（`kb.py:行号`） | 审批 | 说明 |
|---|---|---|---|
| `review_cards_upsert` | `:4652` | **过审批**（`read_only=False`，`:4691`） | 建/改卡；整批坏一条即拒绝整批 |
| `review_card_disable` | `:4693` | **过审批**（`:4709`） | 禁卡 / 恢复调度（不删定义） |
| `review_due_list` | `:4711` | **过审批**（`:4726`） | 回**整段纯 JSON**，**含答案**（agent 是判分方，故保留）；内部走该库 `fsrs.py due` |
| `review_grade` | `:4728` | **过审批**（`:4745`） | 评分 1..4；幂等键 = `card_id + 评审日` |
| `review_error_add` | `:4747` | **过审批**（`:4787`） | 追加一条错题到 `errors.json` |
| `review_attempts_list` | `:5128` | **免审批**（`read_only=True`，`:5151`） | 只读作答/反馈流水；支持 `card_id`/`kind`/`verdict`/`since`/`limit` |
| `review_feedback_add` | `:5364` | **过审批**（`read_only=False`，`:5389`） | agent 写回反馈（`kind:"feedback"`）到 `attempts.jsonl` |

**`scratch_*` 四把 + `pwsh`/`cmd`**：

| 工具 | 定义（`kb.py:行号`） | 审批 |
|---|---|---|
| `scratch_list` / `scratch_read` / `scratch_write` / `scratch_delete` | `:3908` / `:3917` / `:3931` / `:3949`（`_scratch_tools` `:3900`） | **免审批**（四把均按默认 `read_only=True` 声明，含写/删 —— 见 `kb.py:3839` 注释） |
| `pwsh` / `cmd` | `:4091` / `:4104` | **过审批**（`read_only=False`，`:4102` / `:4115`） |

> **总口径**：`read_only=False` 的工具在 `registry.invoke()` 分发前**一律过审批门**（`kb.py:4643`）；agent 驱动时逐次审批（防「模型不可信」）。**人驱动（点 UI 按钮）的那 4 条 RPC 免审批**（R3a-2.5 拍板：按按钮的是人、且正看着卡面做决定）。

### 3.4 答案隔离规则（三条 + 两处边界）

**规则**：

1. **UI 取卡在后端剔答案**：`_review_ui_hide_answers`（`ui.py:2372`）逐卡 `pop` 掉 `answer`/`accept`/`explain`（**保留 `options`**）；隐藏键常量 `_REVIEW_UI_HIDDEN_KEYS`（`ui.py:2369`）。**不依赖「前端不渲染」这种隐性契约**。
2. **`cloze` 挖空**：`_review_ui_blank_cloze`（`ui.py:2490`）把 `front` 的 `{{cN::…}}` 挖空为 `{{cN::}}`，`_review_ui_blank_cloze_card`（`ui.py:2500`）**整键剔除 `back`**（`self` cloze 翻面靠 token 回填，不需要整段 `back`）。
3. **按需揭晓**：`review_reveal_one`（`ui.py:2524`）**只在 `cloze` 翻面时**调（前端唯一调用点 `src/memoria/ui/static/app/js/review-modal.js:713`，函数 `revealForFlip` `:706`，每卡缓存一次）。

**两处边界（如实）**：

- **桌面壳的桥是通用的**（pywebview 走 `js_api` 方法枚举、PyQt6 走 `getattr`）⇒ **页内任意 JS 都能按名调用 `review_reveal_one`**；当前隔离靠「调用点收敛到唯一一处 + 静态钉子」，**没有运行期白名单**（既有 RPC 亦无）。来源：`preview-render-refactor.md:1107`（残留风险条）。
- **`cloze` 答案文本写在 `front` 里 ⇒ 属固有限制**（挖空是补救，不是根治）；来源：同上。

### 3.5 FSRS 边界（三条硬事实）

1. **调度只由 `fsrs.py` 算**：`compute_next_state`（`resources/agent-prompts/fsrs.py:279`）；`cards.json` 脚本只读（`fsrs.py:7`）、`progress.json` 脚本读写（`fsrs.py:8`）。工具/UI **不自算日期**（`review_due_list` 内部走 `fsrs.py due`）。
2. **`grade` 不校验 `due`**：`op_grade`（`fsrs.py:423`）只做 `(card_id, review_date)` 幂等判断，**从不校验这张卡「今天是否到期」** ⇒ **可评集合必须由 `review_due_list` 界定**。（实测：评一张不在到期内的卡照样 exit 0 并改写状态 —— `preview-render-refactor.md:1016`。）
3. **`grade` 幂等**：幂等键 = `(card_id, review_date)`（`fsrs.py:426-427`）⇒ **同日同卡只落第一条**，重复评分 / 改分**均不生效**（首分胜出）⇒ **同日改分做不到**。跨天重试 = 次日新评（不是重试）。

---

## ④ 已知欠账与坑（逐条 + 严重度）

| # | 欠账/坑 | 严重度 | 出处/说明 |
|---|---|---|---|
| 1 | **`attempts.jsonl` 无轮转 / 无上限 ⇒ 会无限增长** | **中**（长期运行） | `preview-render-refactor.md:1115`；建议按天或按条数轮转，**未做** |
| 2 | **`attempts.jsonl` 并发追加无跨进程锁**（`open(...,"a")` 单次 write + flush；桌面单进程单库几乎不并发，但**无原子保证**） | **低–中** | 同上；`kb.py:5032` / `:5259` |
| 3 | **`elapsed_ms` 是前端自报、可伪造**（后端只做非负兜底，无法验真） | **中**（若被当考核依据） | `preview-render-refactor.md:1110`；`_review_normalize_elapsed` `kb.py:4989`。**宜作度量**（观察卡顿/阅读耗时趋势），**非考核依据** |
| 4 | **`short`/`produce` 需 agent 回判才闭环**（否则永远 `unjudged`；agent 长期不回判 ⇒ 卡一直挂 `unjudged`） | **中** | `preview-render-refactor.md:1115`；`review_feedback_add` 是闭环工具 |
| 5 | **落盘失败后重试成功会再写一条**（append-only，不去重） | **低–中** | `preview-render-refactor.md:1115` |
| 6 | **「拖动浮层卡」与「空闲心跳」在仓内无先例**（属**新增机制**） | **中**（施工风险） | `preview-render-refactor.md:1257`。浮层本体有先例（`.-agent-sel-add` `app.css:5623`、`#-flash-host` `app.css:2543`、`.-modal` `app.css:4560`），但**「可拖拽移动的浮层卡片」与「无作业时的空闲心跳」无先例** |
| 7 | **`review_submit_one` 落盘失败的行为**：抛错 ⇒ RPC 回 `record_failed`/`temporary`；**界面显示「作答记录失败」且不假装成功**，允许重试（沿用「不做乐观更新」红线） | 说明（非 bug） | `ui.py:2464`；`preview-render-refactor.md:1111` |
| 8 | **`review_due_list` 返回值 `total` 含反馈记录**（`attempts.jsonl` 两种记录混存）⇒ 统计需按 `kind` 过滤 | **低**（易误用） | `preview-render-refactor.md:1127`；`_review_attempts_prefilter` `kb.py:5193` |
| 9 | **`elapsed_ms` 进不了卡 schema**（卡 `additionalProperties:false` 会拒）⇒ 只能落在 `attempts.jsonl` | 说明 | `preview-render-refactor.md:1097` |

---

## ⑤ 待办清单

### 5.1 悬浮卡（R4-3，方案已出、未施工）

- **v1（最小可用 · 只作业进行中）**：agent 工具 `review_summon(card_id?)` / `review_revoke()`（方案建议**免审批**）；`agent_ask_poll` 载荷追加 `pending_summons`（只增不改）；前端悬浮卡（右下固定、可拖拽、单卡槽、就地作答复用 R4.3）；全局开关 + 三道限流。
- **v2（完整）**：**面板打开时的低频空闲心跳（≈5–10s）** ⇒ 作业结束后仍能投递呼出与及时撤回；面板关闭时心跳必须停止；可选多卡队列。
- **10 条待定（需人拍板）**（逐字见 `preview-render-refactor.md:1244-1253`）：① 默认开还是关；② 位置（右下？可拖拽？位置是否落盘）；③ 一次一张（单卡槽）还是队列；④ v1 是否够用（是否必须做 v2 空闲心跳）；⑤ 呼出范围（仅今日到期 vs 允许任意卡）；⑥ `review_summon`/`review_revoke` 是否过审批（方案推荐**免审批**）；⑦ 频率上限具体数值（同卡冷却/全局冷却/snooze）；⑧ 呼出/撤回是否落持久审计、落哪里（方案推荐 **v1 内存态、不落盘**）；⑨ 撤回时「用户已开始作答」的处理（方案建议保留到本次交互结束）；⑩ 手动入口（模态）打开时是否直接展示「被呼出的那张」。

### 5.2 小项

- **`attempts.jsonl` 轮转/上限**（见 §4-1）。
- **`attempts.jsonl` 跨进程锁**（见 §4-2）。
- **`docs/todo.md` 的 396 行重排处置** —— ⚠️ **本次未能取证**：`docs/todo.md` **全文仅 370 行**，且全仓检索 `396`/`重排处置` 无对应条目。**来源＝任务派发描述（父 agent 转述），仓内无法核实，行号不可信、此处不落具体行号**。
- **`docs/example/AAA_Vocab` 的 `fsrs.py` 拷贝刷新** —— ✅ **已取证属实**：`docs/example/AAA_Vocab/.memoria/agent/fsrs.py` 与 `resources/agent-prompts/fsrs.py` 的 SHA256 **不同**（前者与 `docs/example/rich-content-test/.memoria/agent/fsrs.py` 相同），即示例库内的拷贝**落后于**权威 `resources/agent-prompts/fsrs.py`，需刷新。（⚠️ `docs/example/**` 为**只读禁改区**，刷新须经人。）

---

## ⑥ 怎么验证与复现

### 6.1 交互复现（L4，AGENTS.md 要求）

- **探针 harness**：`docs/example/rich-content-test/_harness.py` —— **bottle 静态服务 + `UIAPI` over HTTP(/rpc) + 注入 pywebview 桥**。用法：`python _harness.py` → `http://127.0.0.1:8642/`（`_harness.py:2-3`）。可用环境变量覆盖库/端口：`MEMORIA_HARNESS_KB`（默认 `docs/example/rich-content-test`）、`MEMORIA_HARNESS_PORT`（默认 `8642`）（`_harness.py:25-26`）。
- **CDP 探针范式**：`scripts/benchmark/surface/cdp.mjs`（Node ≥22 内置 `WebSocket`/`fetch`，零依赖）。用法见文件头 `:8-11`：`--selftest` / `--probe --url … --kb-root … --cases … --out …`。打字走 `Input.dispatchKeyEvent` 出**真实** `keydown`（`:13-16`）。

### 6.2 「临时库造卡」最小步骤（取证/复现用）

> **原则**：**不要动** `docs/example/AAA_Vocab`（禁改区）。新建临时库目录，自造 `.memoria/agent/review/cards.json`，并从 `resources/agent-prompts/fsrs.py` 拷一份到临时库的 `.memoria/agent/fsrs.py`（R3a-2 的临时库 `artifacts/_review_fsrs_verify/` 就是这个做法，见 `preview-render-refactor.md:1008`）。

1. 建临时库目录 `<TMP_KB>/`，造 `<TMP_KB>/.memoria/agent/review/cards.json`（顶层 `{schema_version, updated_at, cards:[…]}`，每卡至少 `card_id/type/front/back/source`；`cloze` 的 `front` 用 `{{c1::…}}`）。
2. 拷 `resources/agent-prompts/fsrs.py` → `<TMP_KB>/.memoria/agent/fsrs.py`。
3. 起 harness 指到临时库：`MEMORIA_HARNESS_KB=<TMP_KB> python docs/example/rich-content-test/_harness.py`。
4. `cdp.mjs --probe --url http://127.0.0.1:8642/ --kb-root <TMP_KB> …` 跑断言。

### 6.3 测试基线（2026-10-12 实测）

- `python -m pytest tests/ -q` —— **基线 1440**（任务口径；本次交接首次观察 `doc_anchor` 单跑输出 `14 passed, 1426 deselected` ⇒ 合计 1440）。**如实补记**：交接期间工作树**已带与复习无关的既有未提交改动**，`pytest --collect-only` 实测收集数为 **1441**（比 1440 多 1，经受控实验证明**与本交接的 3 处文档改动无关**：把新文档移出仓库 / `git stash` 两处文档改动后，收集数仍为 1441）。`-k doc_anchor` 恒为 **14**。
- `python -m pytest tests/ -q -k doc_anchor` —— **14**（守卫 `文件:行号` 锚点；测试体 `tests/test_doc_anchors.py`）。
- `node scripts/i18n_selftest.js` —— **12 行全 PASS**。

---

## ⑦ 纪律与红线（接手人必须知道）

- **零行漂移**：改动既有文件时**只允许「同行等量替换」或「文件末尾追加」**；**严禁**在既有函数/表格中间插行（会推移上方所有 `<文件>:<行号>` 锚点）。参照先例注释 `kb.py:4132-4133`、`markdown-preview.js:1906-1908`。
- **`.memoria/**` 由应用代码写**：**agent 不直写**产品状态；复习卡的写入口是领域工具 / UI 路径（`AGENTS.md §1`）。
- **`docs/example/AAA_Vocab` 只读**（`docs/example/**` 为禁改区）。
- **新增事实源必须先登记 `AGENTS.md §1`**：`attempts.jsonl` **已登记**（`AGENTS.md §1`：复习作答记录 → `<kb>/.memoria/agent/review/attempts.jsonl` → 应用代码（UI 路径 `review_submit_one`；append-only，不撤销））。
- **不改** `Package/**`、`AGENTS.md`、`pyproject.toml`(version)、`src/memoria/__version__.py`（这些是**人写/人授权**文件）。**agent 不改 `src/**` 的登记类与版本**。
- **git**：非破坏性操作；**不 `push` / 不强推**；commit 需用户授权。

---

## ⑧ 文档放置说明（如实）

- **设计历史散布处**：本工作的设计历史被**追加**在 `docs/design/preview-render-refactor.md` 末尾的四个附节 —— `## 附 R3a`（`:837`）、`## 附 R3a-2`（`:1006`）、`## 附 R4`（`:1083`）、`## 附 R4-3`（`:1131`），另有更早的 `## 附 R3`（`:822`）。
- **性质判定**：这**属产出时的放置不当**（图省事「零行漂移、不新建文件」，结果模糊了该文档「预览渲染重构」的语义边界）。
- **本文件为权威汇总**：接手复习卡工作**以本文件为准**；上文四节保留为**产出时的历史记录**。
- **为何不把那几节搬过来**：`preview-render-refactor.md` 内部及**其他文档**有**大量按行号引用**该文件的锚点（例如 `docs/conventions/docs-management.md:340` 引用 `preview-render-refactor.md:854`）——**搬走那几节会破坏这些锚点**。故**只在原处 4 个标题行加指针**（同行替换、行号不变），不搬迁正文。
- **既有先例取证（用于定路径/命名）**：仓内**未找到**「交接 / handoff / onboarding」类**文档文件的既有命名与位置先例** —— `docs/**` 检索 `handoff/onboarding` 为 0 文件；`docs/README.*` 只把「接入新 AI / 交接」指向 `reference/` 全部 + `guides/README.md` + `conventions/README.md`（**无单一交接文档**）。故本次取 `docs/design/`（其职责＝「设计文档与决策记录」，见 `docs/README.md:18`）与 kebab-case 英文名（同目录先例：`durable-flush.md` / `export-plan.md` 等），命名为 **`docs/design/review-cards-handoff.md`**，与设计历史所在的 `preview-render-refactor.md` **同目录相邻**。
