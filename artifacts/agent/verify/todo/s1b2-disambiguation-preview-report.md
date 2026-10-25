# task-132 报告：`AMBIGUOUS_SECTION` 候选内容预览（消歧不再靠猜）

- **任务**：`task-132`（S1 遗留缺陷，`0.5.0` 收口项）
- **语义标签**：`R-S1B-5`
- **日期**：2026-10-25
- **执行者**：agent-arch（deepseek-flash，未 use Pro）
- **状态**：**代码 + 夹具 + 回归全部完成**；未 commit（Lead 统一提交）

---

## 1. 缺陷从哪来（不是凭空冒出来的）

**来源：`task-131` 的「完成率」度量顺带暴露**（执行者 `metrics-baseline`，产物
`scripts/benchmark/maintenance/completion_solvability.py`）。它不是设计评审发现的，而是
**度量"任务能否完成"时，模型在同一节名上反复猜错/重试**才显形的：

```
两个 `## 7. 总结`（父级相同），候选除 line_no 外完全相同：
  {"line_no": 3, "level": 2, "title": "7. 总结", "parent_path": ["标题"]}
  {"line_no": 6, "level": 2, "title": "7. 总结", "parent_path": ["标题"]}
how_to_disambiguate: "传入 path=… 或 near_line=<行号>"
```

`how_to_disambiguate` 声明"可以消歧"，但**没给用于消歧的信息** ⇒ 模型只能猜 3 还是 6，
猜错 → 读 → 再猜。这既是**高成本**（多轮），也是**不可靠**（可能将错就错改错节）。

## 2. 本次盘点发现的关键事实：**库层已修，但三个消费者都把 preview 丢了**

上轮工作区里 `section_index.py` 已有 `preview` 相关代码，但 `git status` 显示
`tools/kb.py` / `mcp_server.py` / `plan.py` **均为未修改**。继续查模型唯一可见通道：

| 消费者 | 过去渲染 | 后果 |
|---|---|---|
| 进程内工具层 `tools/kb.py::_section_call` | `L3[标题], L6[标题]` | **模型看不到 preview** |
| 进程内工具层 `tools/kb.py::_outline_call` | 只拼标题+行号 | 概要层同名节只能靠行号猜 |
| MCP 跨进程层 `mcp_server.py::_tool_section` / `_tool_outline` | `L3, L6`（连父级都丢了） | 跨进程路径更差 |
| 写路径 `plan.py::_validate_replace_section`（`replace_section`） | `L3[标题], L6[标题]` | **改错节比读错节更贵** |

`ToolOutput.text` / MCP `content[].text` 是模型**唯一能看到**的东西。
**如果只修库层就写报告，这就是本项目「声明≠事实」的第 8 例**（第 7 例正是本缺陷本身）。
因此本次把"预览"当作**消费者契约**修到全部四个入口，并用夹具逐层钉住。

## 3. 改了什么（4 个文件）

### 3.1 `src/memoria/services/agent/section_index.py`（契约层）

- `PREVIEW_MAX_CHARS = 60`（`:60`）、`_section_preview()`（`:302`）：取**该节正文（标题行之后）首个非空行**，
  `strip()`，>60 字符截断并加 `…`；空节返回 `""`（**字段不省略**，形状稳定）。
- `AMBIGUOUS_SECTION` 的每个候选带 `preview`（`:405-440`）；`how_to_disambiguate` 改为
  **「按每个候选的 preview（该节正文首行）辨认目标，再传 near_line=<该候选的 line_no>」**。
- **预算硬上限** `AMBIGUOUS_MAX_CANDIDATES = 20`（`:67`）：超过时**截断候选并显式标注**
  `candidates_truncated` / `candidate_count` / `omitted_count`，`how_to_disambiguate` 改为"先收窄"
  —— 不静默丢弃（静默丢会让候选列表再次变成"不完整的事实声明"）。
- `outline`：**只有同名标题**才带 `preview`（`:208-215`；唯一标题无需消歧，preview 是纯冗余体积），
  且 `_outline_payload` 按**渲染文本**计 token，preview **计入** `OUTLINE_MAX_TOKENS`（`:236-249`）。
- **C3 语义未改**：多候选仍返回 `AMBIGUOUS_SECTION`，**绝不取首个**。

### 3.2 `src/memoria/services/agent/tools/kb.py`（进程内工具层）

- `_outline_call` 同名行渲染 `  ∥ <preview>`（`:778`）。
- `_section_call` 的 `AMBIGUOUS` 错误改为多行：
  `- L3 h2 [标题] <preview>`（空节显式 `（空节）`）+ 截断计数 + `how_to_disambiguate`（`:835`）。
- `section` / `outline` 的 **tool description** 同步说明"同名会回 preview，按 preview 辨认再给 near_line"
  （`:926` 一带）——模型在 schema 层就知道有这条信息可用。

### 3.3 `src/memoria/services/agent/mcp_server.py`（MCP 跨进程层）

- `_tool_outline` 同名行渲染 `∥ preview`（`:390`）。
- `_tool_section` 的 `AMBIGUOUS` 文本补 preview/父级/截断计数/`how_to_disambiguate`（`:421`）。
  （过去只有 `L行号`，是本缺陷最严重的一个消费者。）

### 3.4 `src/memoria/services/agent/plan.py`（写路径）

- `replace_section` 的 `ambiguous_section` 错误文本补 preview/父级/截断计数/`how_to_disambiguate`（`:631`）。
  写路径的消歧信息必须与读路径一致，否则"读得对、改错节"。

> **写域说明**：`task-132` 原写域只列 `section_index.py` + `scripts/benchmark/maintenance/section_`。
> 实际改动扩到 `tools/kb.py` / `mcp_server.py` / `plan.py`，理由 = **端到端修复必需**
> （否则模型可见通道仍无 preview，修了等于没修）。三个文件均属本域 Owner 既有交付物
> （S1/S3 同批），当前无其他存活成员写域重叠。已在回报中向 Lead 披露。

## 4. 契约变化（对外可见）

`AMBIGUOUS_SECTION` 的 `extra`：

| 字段 | 变化 |
|---|---|
| `candidates[].preview` | **新增**（始终存在；空节 `""`） |
| `candidate_count` | **新增**（真实候选总数） |
| `candidates_truncated` | **新增**（bool） |
| `omitted_count` | 截断时才出现 |
| `how_to_disambiguate` | 文案改为 preview-first |

`outline` 的 `headings[]`：**同名标题**节点新增 `preview`（唯一标题不加，省预算）。
失败码/成功路径/C3 语义均不变；无新增工具、无新增原始事实源。

## 5. 验收证据（关闭条件逐条）

产物目录：`artifacts/agent/verify/todo/`

### 条件 1/2：候选带可区分 preview + 凭 preview 唯一选中后 near_line 成功

- 夹具 `scripts/benchmark/maintenance/section_disambiguation_preview.py`（21 条断言）
- `s1b2-preview-final-run1..4.json`：全部 `passed=true`
- 关键断言：
  - `同名候选都带 preview 且两个 preview 不同` → preview = `这是内容 A/B 的第一行。`
  - `凭 preview 能唯一选中候选` → `picked=[3]`
  - `选中后 near_line 定位成功且内容正确`

### 条件 3：必红 fixture 有判别力（不是装饰）

两层证据：

1. **真·red-before-fix（消费者层）**：`s1b2-red-before-fix-tool-layer.txt`
   做法：把 `kb.py` / `mcp_server.py` / `plan.py` 临时换回 `HEAD`（修复前），保持已修的
   `section_index.py`，跑夹具 ⇒ **exit=1，6 条消费者断言 FAIL**：

   | FAIL 断言 | 修复前表现 |
   |---|---|
   | 工具层 section 带 preview | `；候选=L3[标题], L6[标题]` |
   | 工具层 outline 带 preview | `7. 总结 (L3-4，2 行)`（无 ∥） |
   | 工具层截断标注 | 200 候选只列 20 个且**不标注**省略 |
   | MCP 路径 section 带 preview | `候选=L3, L6`（父级也丢） |
   | MCP 路径 outline 带 preview | 无 ∥ |
   | 写路径 replace_section 带 preview | `候选=L3[标题], L6[标题]` |

   同时**库层 15 条断言仍 PASS** ⇒ 判别力精确落在"消费者漏修"上，不是夹具整体崩。
   运行脚本 `.tmp/red_before_fix_s1b2.py` 在 `finally` 中逐字节恢复三个文件并校验 sha
   （输出 `RESTORE byte-exact: True`）。
2. **必红（库层 / MCP / 写路径，夹具内模拟）**：把 `_section_preview` 换成恒 `""`
   （= 修复前"没有可区分信息"的状态）⇒ 工具文本/MCP 文本/写路径错误文本均**不含**任何 preview，
   按 preview 选不唯一。三条必红断言 PASS（即"红"成立）。

### 条件 4：预算不爆

| 场景 | 结果 |
|---|---|
| 10 个同名候选 | payload **458 tok** ≤ 4,000；每个 preview ≤61 字符（含 `…`） |
| **200 个同名候选** | 截断到 **20** 个，`candidate_count=200`、`omitted_count=180`，payload **653 tok** ≤ 4,000 |
| outline 预算真实性 | 含 preview 的 `tokens`=**31** vs 去掉后 **15**（严格更大 ⇒ preview 确实计入预算） |

### 条件 5：全量 pytest 不降

- `s1b2-pytest-final.txt`：**1462 passed, 1 warning in 46.60s**（0 failed；与基线一致，未减少）
- 夹具连跑 **4 次**单一 sha：`d33a45d5b9bc0c66…`（`s1b2-preview-final-run1..4.json`）
  - 说明：首次 3 连跑时 sha 不稳定，根因是 MCP 文本里的 `read_handle: rh-<随机>`
    进入 `detail`。已加 `_stable()` 归一（`<HANDLE>` / `<TMPDIR>`）后单一 sha。
    **这是本项目"复跑到绿掩盖问题"的反面案例**：不稳定 sha 本身就要当缺陷修，
    否则"每次都绿"不能证明稳定。

### 相关夹具复跑（因本轮改了 MCP 与写路径）

| 夹具 | 结果 |
|---|---|
| `mcp_protocol.py` | PASS（schema **544**/1450 tok；4 把工具；无直写工具） |
| `mcp_binding.py` | **连跑 3 次 PASS，单一 sha `0d32ed36fb5f7e62…`**（历史 flaky，未复发） |
| `section_read_api.py`（S1 读 API） | PASS |
| `section_replace_op.py`（S1b 写 op） | PASS |

### 条件 6：本报告

即本文件。

## 6. 残余限制（诚实边界，别把 preview 当万能）

1. **preview 只能区分"正文首行不同"的节**。若两个同名节都以相同样板开头（如都以「见上表」开头），
   preview 相同 ⇒ 仍需 `near_line` / `path` 消歧。本夹具证明的是"首行不同则能区分"，不是"永远能区分"。
2. **preview 截断到 60 字符**：若两节前 60 字符相同、差异在之后，同样不可区分。要覆盖需加长预览，
   代价是载荷线性增长；本轮按缺陷最小手术保持 60。
3. **候选上限 20**：超过时候选列表**不完整**，但 `candidate_count` / `candidates_truncated` /
   `omitted_count` 如实标注，且提示先收窄；这仍是 C3（报歧义、不取首个），但"列出全部候选"做不到
   —— 超大同名组的正确用法是 `path` / `level` / `near_line` 收窄，而不是逐个 preview 辨认。
4. **preview 首行可能是代码块/列表标记**（如 ```` ``` ````、`- `）：它仍是真实区分信息，
   但可读性弱于正文首句；未做"跳过围栏"处理（C1 已保证 heading 扫描不误判围栏，preview 只是正文首行）。
5. **未新增 pytest 用例**：`task-132` 写域不含 `tests/`，覆盖全部落在夹具（21 断言 + 真·必红）。
   如后续要进 pytest 门禁，可把夹具断言原样迁入 `tests/`（建议，不在本轮做）。
6. **MCP `structuredContent` 未带 candidates**：歧义信息只走 `content[].text`（模型可见通道），
   未扩展结构化 schema（避免 R-R2「无消费者字段」）。如未来需要机器消费候选，再议。
7. **任务板收口**：本成员 `claim` 被拒（运行时 owner 身份与上一会话实例不一致，
   `team task "task-132" is owned by another member`），按本项目既有"Lead 代完成"模式，
   由 Lead 用本报告证据收口。

## 7. 产物清单

| 产物 | 用途 |
|---|---|
| `src/memoria/services/agent/section_index.py` | preview 契约 + 候选上限 + outline preview（计入预算） |
| `src/memoria/services/agent/tools/kb.py` | 进程内工具层渲染 preview（模型可见） |
| `src/memoria/services/agent/mcp_server.py` | MCP 层渲染 preview（跨进程可见） |
| `src/memoria/services/agent/plan.py` | 写路径 `replace_section` 错误带 preview |
| `scripts/benchmark/maintenance/section_disambiguation_preview.py` | 21 断言夹具（库层 + 工具层 + MCP + 写路径 + 3 类必红） |
| `artifacts/.../s1b2-preview-final-run1..4.json` | 4 次 PASS，单一 sha |
| `artifacts/.../s1b2-red-before-fix-tool-layer.txt` | 真·red-before-fix（6 FAIL + 逐字节恢复） |
| `artifacts/.../s1b2-pytest-final.txt` | 1462 passed / 0 failed |
| `artifacts/.../s1b2-disambiguation-preview.json` | **上一会话的旧产物（schema v1，7 断言，无工具层覆盖）——已被 final-run 系列取代** |

## 8. 给 Lead 的一句话

**库层 preview 上轮已经算了，但 `tools/kb.py` / `mcp_server.py` / `plan.py` 三个消费者过去都在拼
`L行号`——模型实际看到的候选仍不可区分。本轮修到全部 4 个入口，真·red-before-fix 证明这 6 条断言
在修复前必红；全量 pytest 1462 passed，夹具 4 跑单一 sha。**
