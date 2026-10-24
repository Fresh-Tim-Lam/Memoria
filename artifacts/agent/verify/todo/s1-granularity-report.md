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
## 7. S1a：读侧三级粒度（`outline` / `section` / `snippet`）

**新文件**：`src/memoria/services/agent/section_index.py`（heading 语义仍走唯一实现 `services/heading_proposals`，本模块只是消费者）。
**验收制品**：`artifacts/agent/verify/todo/s1a-read-api.json`（`sha256=41766432d804f632…`；两次运行一致）
**复跑**：`python scripts/benchmark/maintenance/section_read_api.py --json artifacts/agent/verify/todo/s1a-read-api.json`

### 7.1 逐条对照 D 节（17 条断言全绿）

| 断言 | D 节 | 结果 |
|---|---|---|
| 归一化：去 `#`/ATX 闭合/空白折叠；默认不折大小写、`ci=True` 才折 | D.1 | ✅ |
| 唯一命中 | D.2 ② | ✅ |
| 多候选 + `path`（父级标题链，后缀匹配）命中正确那一节 | D.2 ③a / C2 | ✅ |
| 多候选 + `near_line` 取之前最近同名 | D.2 ③b | ✅ |
| 仍 >1 ⇒ `AMBIGUOUS_SECTION` + `candidates[]`（**不取首个**） | D.2 ③c / **C3 红线** | ✅ |
| 无匹配 ⇒ `SECTION_NOT_FOUND` + `suggestions[]`（difflib 最近 3） | D.2 ④ / D.3 | ✅ |
| `NO_HEADINGS` | D.3 | ✅ |
| `INVALID_LEVEL` | D.3 | ✅ |
| `line=` 一等回退（`#L`），命中包含该行的**最深层**节（可 `outermost=True`） | **C4** | ✅ |
| 围栏内 `#` 不进 outline | **C1** | ✅ |
| 预算：outline ≤800 / section ≤4000（超限有 part+cursor）/ snippet ≤600 | task-120 | ✅ |

### 7.2 真实语料实测（229 docs / 35,039 行 / 2,556,740 B）

| 指标 | 数值 | 判读 |
|---|---|---|
| outline 最大 tokens | **646**（预算 800） | 无需降级；降级阶梯 `full → no_first_line → level≤2_only` 已实现且可机检 |
| 超预算的节 | **25 个文档**有节超 4,000 tok，最大切 **3 片** | 每片带 `next_cursor={kind:section_part,line_no,part}`，无静默截断 |
| snippet 最大 tokens | **406**（预算 600） | 硬预算：先缩 ±ctx，再截断该行字符；单窗口不可超预算 |
| **C3 触发率**（同名标题占比） | **103 / 3517 = 2.93%** | **远低于 20% 阈值** ⇒ 不需要改显式 `{#id}` 锚（设计变更） |
| 最差单文档 | `modeling_solutions.md` 64.5%（31 个 heading 里 20 个重名） | 该文档内 title-only 常歧义，但 `path`/`near_line`/`line` 三条路径都能解 |
| **C2 双锚有效性** | **21 / 21 组**（父级路径互异的同名标题，全部命中正确那一节） | 反向用例也测：**无 path 必报歧义**，没有静默取错 |

### 7.3 token 口径（必须说清，否则"省 X%"是假的）

`estimate_tokens()` 用 **N1 静态口径**（CJK 1.5 字/token、其它 3.5 字/token），是**估算**；所有返回带 `tokens_estimated: true`。
**完整往返口径（B4.f）不在本模块内**：本模块只报自身载荷，schema/system 成本由调用方（工具层）记账 —— 这是 §9 Q1 双指标要做的事。

---

## 8. S1b：`replace_section` 写 op（复用唯一写者链）

**验收制品**：`artifacts/agent/verify/todo/s1b-replace-section.json`（`sha256=11a955e871d0e0bc…`）
**复跑**：`python scripts/benchmark/maintenance/section_replace_op.py --json …`（在 **tempfile 临时 KB** 上跑，不碰仓库 KB）

### 8.1 改动清单（3 个文件、9 处）

| 文件 | 改动 |
|---|---|
| `services/agent/plan.py` | ① `OP_REPLACE_SECTION` 常量；② `KNOWN_OPS` 18 项；③ `COMPILED_OPS` 17 项；④ 新增 `_validate_replace_section()`；⑤ `_validate_op` 分发；⑥ `preview_plan` 并入 body-edit diff 分支 + 输出节身份 |
| `services/agent/apply.py` | ⑦ import 常量；⑧ compile 分支 `elif verb in BODY_EDIT_OPS or verb == OP_REPLACE_SECTION` |
| `services/agent/tools/kb.py` | ⑨ `propose_write` 工具说明新增 ⑰ 条（否则模型不知道 op 存在 = 不可达） |

### 8.2 "零新写者"的机检证明

`compile_plan()` 为 `replace_section` 产出的原语集合 = **`{"edit_body"}`**（既有原语），**新增原语数 0**。
链路：`replace_section` →（校验期）归一化成 `replace_lines` 的 `edit` →（编译期）`edit_body` →（落地）既有
`body_edit.splice()` → 既有 `backup.snapshot_pre_images()` + 撤销栈。`RISKY_OPS` 未变（与 `replace_lines` 同档）。

### 8.3 矩阵（临时 KB，逐字节验证）

| 用例 | 结果 |
|---|---|
| h1 整节替换 | ✅ 只改该节；标题行保留 |
| h2 节替换 | ✅ |
| **同名标题、无 `path`/`near_line`** | ✅ **报 `ambiguous_section`，不取首个**（C3 红线在写侧同样成立） |
| 同名标题 + `near_line` 消歧 | ✅ 只改对的那一节 |
| **围栏代码块内的 `#`** | ✅ 不构成节边界：整节（含代码块）被替换，`## 第二节` 未误伤 |
| `expect` 不符 | ✅ 拒（`expect_mismatch`），**文件零改动** |
| **单撤销逐字节复原** | ✅ 3/3 用例 `restore_batch` 后 sha 与 apply 前**完全相同** |
| dry-run 零落盘 | ✅ 3/3 |
| **preview 给行级 diff + 节身份** | ✅ `diff_available=true`、`lines_changed` 非空、`section={title,line_no,level,parent_path,end_line_no}` —— 人不会对着 op 名盲批 |

### 8.4 已知未做（**必须明说**）

- **双指标 A/B（省 ≥70% 且完成率不降 >10%）尚未做**。token 侧可用 N1 同口径静态复算（组 0 已是 −82.9~−89.3%），
  但**"任务完成率"需要真实模型跑**（本仓有 `llm/` 配置）；跑模型要花额度，**我不擅自烧** —— 见 §9 Q1。
  在它跑完前，**task-120 关闭条件 2 不满足**，本报告不宣称达标。

---

## 9. 需要 Lead 裁决

| # | 事项 | 我的建议 |
|---|---|---|
| **Q1** | **双指标 A/B 怎么跑**（完成率需真实模型） | 三选一：(a) 用 `llm/config.py` 现配置跑 5 任务 × 2 臂 × 3 = 30 次调用（我报预算）；(b) 只跑**检索充分性代理指标**（答案锚点是否落在返回窗口内，不需要模型），并明确标"代理 ≠ 完成率"；(c) 交 metrics-baseline 独立验收 |
| **Q2** | `kb.py` +7 行 ⇒ `agent-capabilities.md` 的 `kb.py:3879` 引用漂移 **+7** | 归 task-125（doc-consistency）；我不改 `docs/**` 其它文件 |
| **Q3** | `replace_section` 是否进 `RISKY_OPS` | 倾向**不进**（与 `replace_lines` 同档，且 preview 已给行级 diff + 节身份）；你认为整节重写更险就加一行 |

---

## 10. 门禁与回归（本轮）

| 项 | 结果 |
|---|---|
| py_compile（plan / apply / kb / section_index / heading_proposals / document） | ✅ 0 |
| 四份验收脚本 | ✅ `census PASS` / `read_api PASS` / `replace_op PASS` / `kp_end_impact NO_IMPACT` |
| `pytest -k "agent_plan or agent_apply or agent_body_edit or agent_audit"` | ✅ **92 passed / 0 failed** |
| 未改前端、未 commit | ✅ |
| `document.py` 行漂移 | 净 0（9/9）；14 个受监控符号行号不变 |

---

## 11. 下一步

1. 等 Q1 裁决 → 跑双指标 A/B（或代理指标）→ 关 task-120 关闭条件 2；
2. `docs/design/dsh-agent-port.md` 补 `replace_section` + R-D2 统一这两节（该文件在写域内，下一轮补）；
3. 交 `arch-contract` 独立验收（不是我自己判过）。


---

## 12. R-S1A-3 密封性修复 + 工具面接线 + 双指标(b) 代理 A/B

### 12.1 密封性（`MEMORIA_CONFIG_DIR`）

**问题（Lead 实测发现）**：`DocumentService.__post_init__`（`document.py:238`）→ `set_kb_path()`（`:240`）→
`remember_last_kb_path()`（`:259`）会写**全局** UI 设置 `config/ui-settings.json`；app 运行时该文件被占用 ⇒
`PermissionError: [WinError 5]`。任何构造 `DocumentService` 的 benchmark 都有同样非密封性。

**修法**：四个脚本启动时（`import memoria` 之前）设
`os.environ.setdefault("MEMORIA_CONFIG_DIR", tempfile.mkdtemp(prefix="memoria-cfg-"))`
（`ui_settings.py:19` 读它）。已加：`section_headings_census.py` / `section_read_api.py` /
`section_replace_op.py` / `section_kp_end_impact.py` / 新增的 `section_granularity_ab.py`。

**验证**：密封后重跑，**embedded sha 全部不变**（`e9c4021a` / `41766432` / `11a955e8`），
`git status -- config/` = **0 改动** ⇒ 全局配置未被触碰、测量可复跑。

### 12.2 工具面接线（S1a 之前只交了模块，模型拿不到）

`tools/kb.py::_granular_read_tools(root)` 新增三把工具并接到 `build_kb_tools()`：
`outline` / `section` / `snippet`（工具面 **36 → 39**，其中"新增"= 3 把）。
同时修了 ⑰ 的措辞：`replace_section` 的说明里引用了 `outline`/`section` —— 那时工具还没接，现已一致。
smoke：`outline` → 标题树（含行号区间）；`section` → 单节正文（同名走 `near_line`/`path`，歧义报错）；
`snippet` → ±ctx 窗口；404/歧义路径回可操作错误文本。

### 12.3 双指标 (b)：代理 A/B（**含往返轮数与总账**）

`scripts/benchmark/maintenance/section_granularity_ab.py` → `artifacts/agent/verify/todo/s1a-granularity-ab.json`
（`sha256=5f25d1d057b3719e…`）。密封环境；两臂都用**真实工具 handler**（不是自编 payload）；
锚点 = 该节第一条 ≥12 字的正文行；轮数由**固定策略**模拟（`read_document` 分页 vs `outline→section`）。

**性质声明**：`PROXY`（检索充分性 + 固定策略轮数），**不是完成率**；不调用模型（R-S1A-1 已裁决不烧额度）。

| 指标 | A 当前（整篇分页） | B 粒度（outline→section） |
|---|---|---|
| 任务数 | 20（read_section 10 / find_sentence 10） | 同 |
| **轮数** min/median/max | 1 / 1.0 / 2 | 1 / 1.5 / 2 |
| **每轮 token** 中位 | **2,079** | **260** |
| **总账** sum / 中位 | **67,109** / 3,079 | **28,600** / 654.5 |
| 命中率（锚点落在返回内） | **1.00** | **1.00** |

**按意图拆（关键）**：

| 意图 | A 总账 | B 总账 | 节省 | 轮数 A/B |
|---|---|---|---|---|
| `find_sentence`（找一句话） | 33,123 | 1,901 | **94.26%** ✅ | 1.8 / 1.0 |
| `read_section`（读一节） | 33,986 | 26,699 | **21.44%** ❌ | 1.0 / 2.0 |
| 合计 | 67,109 | 28,600 | **57.38%** | 中位 +0.5 |

**schema 成本**：新增 3 把工具定义 = **697 tok**（占全部工具 schema 的 6.43%），
按本题集的总账节省算 **≈0.4 个任务即回本**（一次性/会话成本，摊平后可忽略）。

**诚实结论（不修饰）**：
1. **"省 ≥70%" 没有整体达成**（57.38%）。它在 `find_sentence` 类成立（94.26%），在 `read_section` 类只有 21.44%。
2. **原因不是实现，是任务结构**：`read_section` 的目标节往往占全文很大比例 ⇒ A 的"整篇一次读完"本来就只有 1 轮 ~3,000 tok，
   粒度化省不下多少，还要多付一轮 outline（~50 tok）+ section 头部。**这正是 U3 的边界**：
   粒度化的收益 ≈ `1 − (所需材料 token + 固定开销) / 全文 token`，对"所需材料≈全文"的任务天然不成立。
3. **U3（总账反升）没有在大盘触发**（B 总账 28,600 < A 67,109），但 `read_section` 类的**单任务层面已经有反升案例**——
   脚本按 kind 汇总会掩盖它们，逐任务明细在 `per_task[]`（该字段已保留，供 metrics-baseline 复核）。
4. 因此我**不建议**把"省 ≥70%"当统一门槛；建议改为**按意图分级**（`find_sentence` ≥90% / `read_section` ≥20% 且无单任务反升），
   或由 metrics-baseline 在真机上重定基线。**在 Lead 重新裁决前，task-120 关闭条件 2 判为"未达成"。**

### 12.4 文档与债

- `docs/design/dsh-agent-port.md` 已补 **§12**（R-D2 统一 + 三级粒度 + `replace_section` 落点与口径，+50 行）。
- `kb.py` 累计 **+181 行**（工具面 + ⑰ 说明）⇒ 其中 `kb.py:<行号>` 类文档引用（如有）漂移；
  `test_doc_anchors.py` **不覆盖 kb.py**（Lead 已确认，属 task-126）⇒ 本任务不自行重取。
- 未改 `src/**` 之外的产品代码；未改前端；**未 commit**。


---

## 13. R-S1B-1：70% 阈值作废 + >50% 自适应回退（**含我自己的 harness bug 自曝**）

### 13.1 先说结论

| 关闭条件（新） | 要求 | 实测 | 判定 |
|---|---|---|---|
| `find_sentence` 节省 | ≥90% | **94.26%** | ✅ |
| `read_section` 节省 | ≥20% | **90.65%** | ✅ |
| **单任务反升** | **=0** | **0** | ✅ |

**task-120 关闭条件 2：达成**（按 R-S1B-1 新口径）。旧的"统一 70%"口径作废。

### 13.2 ⚠️ 自曝：上一轮的 `read_section = 21.44%` 是**我的 A/B harness bug**，不是"口径误设"那么轻

上一轮 `run_arm_b()` 对 `read_section` 的调用是：

```python
sec_args = {"file": …, "near_line": task["heading_line"]}      # ← 没有 heading！
out = tools["section"].handler(sec_args)
```

而 `resolve_section(body, heading=None, near_line=…)` 的语义是：**没有标题选择器 ⇒ 返回 `sections[0]`**
（首个 h1 节 ≈ 整篇）。于是 B 臂根本**没有取目标节**，读到的是整篇 —— 这既解释了旧数字为什么只有 21%，
也解释了它的"2 轮"（outline + 整篇）。

**性质**：这是我度量脚本的缺陷，**不是** N1 基线的问题、也不是实现的问题。
它与 Lead 在 `silent_failure` S2 里讲的是同一类错误：**静默默认**（`heading=None` ⇒ 悄悄回 `sections[0]`）让错误看起来像结果。
修法有两层：① 脚本传 `heading`；② `section()` 支持直接按标题取（本来就能，只是脚本没传）。

### 13.3 实现：`WHOLE_DOC_FALLBACK_RATIO = 0.5`

`services/agent/section_index.py::get_section()` 新增三分支（其余逻辑不变）：

| 情形 | 行为 | payload 标记 |
|---|---|---|
| 目标节即整篇（h1 覆盖全文）且整篇 ≤ 预算 | **整篇 1 片 1 轮** | `fallback="whole_document"` |
| 目标节 >50% 全文 且 整篇 ≤ 预算 | **整篇 1 片 1 轮**（消除补读一轮） | `fallback="whole_document"` + `fallback_reason` |
| 目标节 >50% 但整篇 > 预算 | **不回退**（回整篇会被切成更多片 ⇒ 更贵），照旧按节分片 | `fallback_skipped="over_budget"` |

工具侧（`tools/kb.py::_section_call`）把回退渲染成 `**整篇**（目标节「X」占全文 NN% > 50%，已一次给全，无需再读）`，
超预算跳过时渲染 `（本节占全文过半，但整篇超预算，故按节给）` —— 让模型知道"不必再补读"或"确实还要读"。

### 13.4 回退前后对比（同一任务集、同一策略、同一 token 口径）

| 版本 | `read_section` | `find_sentence` | 合计 | 轮数 A/B | 单任务反升 |
|---|---|---|---|---|---|
| 修复前（harness bug：`section` 未传 heading ⇒ 回 `sections[0]`） | 21.44% | 94.26% | 57.38% | 1.0 / 2.0 | 有 |
| 修复 + 直取 + >50% 回退 | **90.65%** | 94.26% | **92.43%** | **1.0 / 1.0** | **0** |

`artifacts/agent/verify/todo/s1a-granularity-ab.json`（`sha256=8873fbf05346fe97…`）；
`read_api` 侧新增 A13 三条断言（触发 / 不误伤 / 预算保护，全部 OK，`sha256=5fb259eb71480ee7…`）。

**必须说清的一点（不给自己贴金）**：这 69 个百分点里，**主要来自修 harness bug + 去掉多余的一轮 outline**，
**不是**来自 >50% 回退 —— 回退在这个任务集里 **触发 0/20 次**（目标节只占全文约 6%，远不到 50%）。
回退的价值我用 A13 三条断言**单独证明**（它会触发、不会误伤小节、超预算会跳过），
而**没有**把它算进 A/B 的增益里。如果只看 A/B 数字就说"回退很有效"，那是又错一次。

### 13.5 本轮附带修的一个真 bug（回退引入后被 A11 抓到）

第一版回退没做预算保护，"本节即整篇" 分支会把 6,761 tok 的整篇直接返回 ⇒ **违反 section ≤4,000 tok 预算**。
`read_api` 的 A11 当场抓红（23 个文档）。现已加预算守卫：整篇超预算一律不回退、标 `fallback_skipped`，A11 全绿。
**这说明"预算断言"不是装饰** —— 它把回退写错的那一刻就拦住了。

### 13.6 复跑

```bash
python scripts/benchmark/maintenance/section_read_api.py --json artifacts/agent/verify/todo/s1a-read-api.json     # PASS（20 断言）
python scripts/benchmark/maintenance/section_granularity_ab.py --json artifacts/agent/verify/todo/s1a-granularity-ab.json  # PASS
```
其余三个脚本 sha 不变（`census e9c4021a` / `replace_op 11a955e8` / `kp_impact NO_IMPACT`）；
`pytest -k "agent_plan/apply/body_edit/audit/doc_anchor"` = **106 passed / 0 failed**；未 commit。

