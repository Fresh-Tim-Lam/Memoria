# task-120（0.5.0-S1 粒度化）阶段报告

> **状态**：**S1c 完成（R-D2 正则统一）**；S1a / S1b 未开始。
> **写域内改动**：`src/memoria/services/heading_proposals.py`、`src/memoria/services/document.py`、
> `scripts/benchmark/maintenance/section_headings_census.py`（新）。
> **未改**：`src/memoria/services/agent/section_index.py`（**尚未创建**，S1a 才建，避免建无消费者的模块）。
> **未 commit**（Lead 统一提交）。

---

## 1. S1c 交付了什么（R-D2）

### 1.1 两套正则 → 一套实现

| 原 | 原正则 | 处置 |
|---|---|---|
| `services/document.py:420` | `^(#{1,6})\s+` | **删除**（含那行上方的 `_HEADING_RE` 定义），改调唯一实现 |
| `services/heading_proposals.py:9` | `^(#{2,6})\s+` | **删除**，本模块成为唯一实现（`scan_headings()`） |

**唯一实现落在 `services/heading_proposals.py`，不是 `services/agent/section_index.py`——理由（分层，非口味）**：

`document.py` 现有依赖链是 `document → range_proposals → heading_proposals`（`document.py:68` 已 import `merge_range_proposals`）。
若把扫描器放进 `services/agent/`，`services.document` 就要**反依赖 agent 子包**；
而 `services/agent/__init__.py` 明文承诺"本包自身不导入任何子模块，避免…"——
把 agent 包塞进 `document` 的依赖闭包会让那条承诺变成刀尖。
故扫描器在 **services 层**，`agent/section_index.py`（S1a）作为**消费者** import，方向与既有架构一致（agent → services）。

### 1.2 C5：级别范围写死在一处

```python
HEADING_LEVEL_MIN = 1
HEADING_LEVEL_MAX = 6
HEADING_RE = re.compile(r"^(#{%d,%d})\s+" % (HEADING_LEVEL_MIN, HEADING_LEVEL_MAX))
```
正则**由常量拼出**，不再有第二份字面量（census 断言 `HEADING_RE.pattern == r"^(#{1,6})\s+"`）。
`heading_proposals` 的"哪些级别值得提议"拆成**策略常量** `PROPOSABLE_LEVEL_MIN/MAX = 1/6`（D.5 要求分开命名）。

### 1.3 C1 落地

`scan_headings()` 先算 frontmatter 边界（首行 `---` → 下一个 `---`，找不到闭合线则视为无）与围栏区间
（``` / ~~~，同字符且长度 ≥ 开启者才闭合，未闭合延伸至文末），再匹配 heading。
`document.py` 的 KP end 重建也改为走它（原实现在代码块里的 `# 注释` 处**提前截断 KP**）。

---

## 2. 验证：h1 提案数 0 → 279（Lead 要求的即时验证项）

**产物**：`artifacts/agent/verify/todo/s1c-headings-census.json`
（`sha256=9771f8274057c7acad954af88a479ceaabbc6c6506e9f3c4f1b683770d77cf99`，两次运行 sha 相同 ⇒ 确定性）
**复跑**：
```bash
python scripts/benchmark/maintenance/section_headings_census.py \
  --json artifacts/agent/verify/todo/s1c-headings-census.json
# 期望最后一行 == RESULT: PASS；退出码 0
```

### 2.1 与实测基线**逐字段**一致（parity）

基线取自 `artifacts/agent/verify/debate/assumptions/as-section-range-measure.json::totals`（脚本读产物，不写死）：

| 字段 | 期望 | 实测 |
|---|---|---|
| docs | 229 | ✅ 229 |
| awareHeadingCount（围栏感知真值） | 3517 | ✅ 3517 |
| naiveHeadingCount（朴素口径） | 3609 | ✅ 3609 |
| falseHeadingInFence | 92 | ✅ 92 |
| falseHeadingInFrontmatter | 0 | ✅ 0 |
| duplicateTextCount | 33 | ✅ 33 |
| h1 | **279** | ✅ **279** |
| levelDist | {1:279, 2:1574, 3:1545, 4:118, 5:1} | ✅ 逐级一致 |

### 2.2 两处行为变化（数字完全可解释）

| 指标 | 旧 | 新 | 解释 |
|---|---|---|---|
| **h1 提案数** | **0** | **279** | 旧正则最小级别 2 ⇒ h1 恒不提议 |
| 围栏内被误当 heading 的 h2..h6 | 71 | 0 | C1 生效（92 个误判里 21 个是 h1、71 个是 h2..h6） |
| 提议总数 | 3309 | 3517 | **+208 = +279(h1) − 71(围栏内 h2..h6 误判)**，脚本断言该等式成立 |
| h1 口径 | naive 300 | aware 279 | 300 − 21(围栏内 h1) = 279 ✅ |

### 2.3 单元断言（census 内，全绿）

C5：h1..h6 全识别 / `#######` 不是 heading / 常量 == (1,6) / 正则由常量拼出；
C1：围栏内 `#` 不计入、`~~~` 未闭合围栏延伸至文末、frontmatter 内 `#` 不计入；
C2：同名 h3 靠 `parent_path` 区分（`('案例 1',)` vs `('案例 2',)`）、`line_no` 是原文件 1-based；
D.1：`## 标题 ##` → `标题`（ATX 闭合 `#` 剥离）；
R-D2：h1 进入提议。

---

## 3. 诚实披露（三件必须说清的事）

### 3.1 "全仓无第二套 heading 正则"是**有范围的**，不是全仓

census 用 `tokenize` 排除注释/docstring 后，扫描 `src/**/*.py` 的全部 heading 字面正则落点：

| 落点 | 状态 |
|---|---|
| `services/heading_proposals.py` | **UNIFIED**（唯一实现，且自无字面量——由 C5 常量拼出） |
| `services/mention_proposals.py:26,47,57` | **PENDING**（section kind 的 mention 提议，需独立验收） |
| `services/search_aux.py:22` | **PENDING**（检索噪音清洗，非寻址语义） |
| `services/suggest_metadata.py:10` | **PENDING**（元数据建议的噪音清洗） |
| `ui/static/app/js/{lexer,markdown-preview,app,math-normalize}.js` | **OUT OF SCOPE**（前端解析链，task-120 写域不含前端，且任务明令"不改前端"） |

⇒ 准确表述应是：**写路径的两处（document / heading_proposals）已统一；其余 3 个 py 模块 + 前端为已登记债务**。
census 把这份债务清单钉成 `PENDING_UNIFICATION` 白名单：**出现白名单外的新落点 ⇒ FAIL**，即"债务不许增长"是机检的，
不靠记性。未统一的部分需要各自的行为验收（改它们会动检索/提议语义），故不在本任务写域内。

### 3.2 我没有为了"修好测试"去改测试期望值

`tests/test_doc_anchors.py` 要求文档里的 `document.py:<行号>` 与源码一致。我第一版改动让 `document.py` 净增 4 行 ⇒
`def save_document` 从 319 漂到 320。按该测试自己写的纪律（"① 压成等量替换；② 重取锚点并更新文档；**不许**把期望值改成实际值"），
我选了 ①：**把改动压成净 0 行**（`git diff --numstat` = `9 9`），并逐个核对：14 个受监控符号的行号与 HEAD **完全相同**。

### 3.3 ⚠️ `test_doc_anchors.py` 在 HEAD 上**已经是红的**（不是我的改动导致）

用 HEAD 版本文档与工作区版本分别复算（脚本见 §6），结论：

| 项 | HEAD | 我的改动后 |
|---|---|---|
| 通过 / 总数 | **1 / 14** | **1 / 14** |
| 已坏的锚点 | 13 个（`_agent_kb`、`agent_session_delete`、`save_document`、`validate_kb` …） | 同上，**逐个相同** |
| 因我改动而新坏的 | — | **0 个** |

另：`tests/test_preview_block_commit.py::test_the_keystroke_path_skips_the_o_document_restamp` 也红，
失败点是 **JS 字符串断言**（`app.js` 里 `if (!keepLineMap) stampBlockLines(preview, _doc);` 不存在）——
与本任务无关（本轮未改任何前端文件）。

⇒ 两个红项均为**既有失败**。修复它们需要改 `docs/**`（锚点重取）与前端断言，都**不在 task-120 写域内**，
建议单开任务（我不擅自越界改）。

---

## 4. 门禁与回归（S1c 范围）

| 项 | 结果 |
|---|---|
| `python -m py_compile` 两改动文件 | ✅ 0 |
| `section_headings_census.py` | ✅ PASS（exit 0） |
| 两次运行 sha256 一致 | ✅ `e9c4021a5761e293…`（census 内嵌 sha） |
| `pytest -k "document or range or proposal"` | 57 passed / 14 failed，**14 个全为既有失败**（§3.3 有逐项归因） |
| 行漂移 | `document.py` 9/9（净 0）；`heading_proposals.py` 全量重写（预期） |
| 未改 `src/**` 其它文件、未改前端、未 commit | ✅ |

---

## 5. 需要 Lead 确认的 3 个设计判断（我给了默认值，但都可一行改回）

| # | 判断 | 现状 | 若你不同意 |
|---|---|---|---|
| **D-S1c-1** | **h1 是否值得提议成 KP range** | 已改为提议（`PROPOSABLE_LEVEL_MIN = 1`）。副作用：只含一个 h1 的文档会得到"整篇 range"提议；嵌套提议本来就有（h2 ⊃ h3），h1 只是多一层 | 把 `PROPOSABLE_LEVEL_MIN` 改回 `2`（一处常量，不动正则） |
| **D-S1c-2** | **`document.py` 的 KP end 重建是否要 fence-aware** | 已改为 fence-aware（C1 一致）。行为 delta：KP 的 end 不再被代码块里的 `# 注释` 提前截断 ⇒ 少数 sidecar 的 end 会变长（更正确，但确实是行为变化） | 回退该处为"共享实现但仅行首匹配"（我会保留共享正则、只去掉围栏过滤，并在报告里记为新债） |
| **D-S1c-3** | **ATX 闭合 `#` 是否从提议名剥离** | 已剥离（`## Foo ##` → `Foo`，原为 `Foo ##`） | 改回：`normalize_title` 只做 trim/折叠 |

---

## 6. 复现与产物

```bash
# S1c 验收（parity + 279 + 单元断言 + 正则落点清单）
python scripts/benchmark/maintenance/section_headings_census.py \
  --json artifacts/agent/verify/todo/s1c-headings-census.json
```
- 产物：`artifacts/agent/verify/todo/s1c-headings-census.json`（5,653 B，`sha256=9771f827…`）
- 基线：`artifacts/agent/verify/debate/assumptions/as-section-range-measure.json`（脚本读它比对，不写死数值）
- 既有红项归因脚本（临时，未入库）：对比 `git show HEAD:<src>` 与工作区的符号行号 + 文档实际锚点

---

## 7. 下一步（S1a / S1b，未开始）

- **S1a**：新建 `services/agent/section_index.py`，实现 `outline / section / snippet`；
  C2（父级路径+行号双锚）/ C3（`AMBIGUOUS_SECTION`，**不得取首个**）/ C4（`#L` 一等回退）在**消费侧**实现；
  失败语义 `NOT_FOUND`（带候选）/ `AMBIGUOUS_SECTION`（候选列表）/ `UNSUPPORTED`；预算 800/4,000/600 tok + `part i/n` + next cursor。
- **S1b**：`replace_section` 写 op（复用 `propose_write→plan→compile→apply` 唯一写者链，`expect` 双锚，单撤销，回执粒度）。
- 两者都会在同一个 `section_index.py` 文件里落地（写域的另一个新文件），届时再补对应报告节。
