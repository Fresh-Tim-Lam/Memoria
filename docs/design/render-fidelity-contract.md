# 渲染保真度契约（Render Fidelity Contract）

> 状态：生效中（2026-10-20）　｜　负责人：`metrics-baseline`　｜　任务：task-22
> 工具：`scripts/benchmark/surface/fidelity.mjs`（投影+断言+签名）、`fidelity_cli.mjs`（CLI）、`run_fidelity.py`（harness 驱动+报告）
> 风险依据：[render-fidelity-risks.md](../../artifacts/agent/verify/render-fidelity-risks.md)（render-perf 只读评估）
> 当前基线：[`results/fidelity-baseline_<sha>.{json,md}`](../../scripts/benchmark/surface/results/)

---

## 0. 为什么需要这份契约

现有指标（C1–C12 / 交互金标准 / C9 性能）全是**代理指标**：

| 现有指标 | 测的是 | **测不到** |
|---|---|---|
| C1–C12 | 契约语义（块身份、同步、落点…） | **渲染结果对不对** |
| 交互金标准 | 选区 + 块可见文本 | **DOM 结构**（元素类型、嵌套、公式节点、内联格式） |
| C9 / P2 性能闸 | 按键时延与 DOM 写入量 | 同上 |

⇒ **一个把 `<table>` 渲染成 `<p>`、把 `$$` 公式渲染成纯文本、丢掉 90% 内联格式的重构，
可以让全部旧指标保持绿。**

阶段 2 要**替换渲染管线**，没有保真度指标 = 没有验收能力。本契约补上这一层。

---

## 1. 两个可比投影

对每份文档，在**页面内**构造两个结构投影，然后逐项断言。

### 1.1 投影 A（期望，来自唯一真源）

`window.MemoriaParser.parse(doc.body).blocks` → 每块：

```
{ kind, level?, lang?, itemsCount?, headerCount?, rowsCount?, inlineKinds{}, mathInlineCount }
```

**关键约束（首版踩过坑）**：
- **只取顶层 blocks**，**不得递归展开 `blockquote` 内层段落**。
  依据 `renderer.js:171-188`：内层渲染成普通 `<p>` 且**不带 `-src-block`** ⇒ DOM 投影里没有它们。
  若 AST 侧也展开，后续所有块下标整体前移 ⇒ A2 大面积假红（实测 21–24 处）。
- 必须与 DOM 来自**同一份文档快照**（见 §5.1 自洽守卫）。

### 1.2 投影 B（实测，来自 DOM）

`#preview .-src-block` → 每块：

```
{ tag, kindClass, blockIndex, textNorm, hasKindClass, textEmpty }
```

**块类型的反推规则**（依据 `renderer.js:70-262` 的实际产出）：

| AST kind | DOM 形态 | 有 kindClass？ |
|---|---|---|
| `paragraph` | `<p>` | ❌ |
| `heading` | `<h1>`…`<h6>` | ❌ |
| `horizontal_rule` | `<hr>` | ❌ |
| `blockquote` | `<blockquote>` | ❌ |
| `list` | `<ul>` / `<ol>` | ❌ |
| `table` | `<table>` | ✅ `-table` |
| `blank_line` | `<div>` | ✅ `-blank-block` |
| `code_block` | `<pre>` | ✅ `-code-block` |
| `math_block` | `<div>` | ✅ `-math-block` |
| `image` | `<p>` | ✅ `-image-block` |
| `frontmatter` | `<pre>` | ✅ `-frontmatter` |
| `mermaid` | `<pre>` → **后处理成 `<div class="-mermaid-container">`** | ✅ |
| `code_block(lang=mermaid)` | 同上（parser 无 MERMAID 分支） | ✅ |

> **⚠️ 多数块本来就不带 kindClass**。因此判据是**「从 (tag, class) 反推 kind」再与 AST 比**，
> 而不是「要求 AST kind 去匹配 kindClass」——后者会让每个文档全红（首版实测）。

---

## 2. A 级 · 硬门槛（必须全绿，零假阳性）

**任何一条 A 级红 ⇒ 判 FAIL，不得进入阶段 2 验收。**

### A1 块数一致

```
DOM `.-src-block` 数  ==  parse(body).blocks.length
```

### A2 块序 + 块类型一致

- **块序**：`data--block-index` 序列必须严格为 `0,1,2,…,n-1`（它是位置下标，正适合做序比对）；
- **块类型**：逐位从 `(tag, kindClass)` 反推 kind，与 AST kind 比对，不得有 mismatch。

> 这是**最该保留的一条**：阶段 2 动的就是块级增量重渲 / BlockIndex / 行区间投射，
> 典型故障正是**块序错乱、块被吞、类型错配**。它无需归一规则、几乎零假阳性。

### A3 公式保真（轻量版，**环境敏感**）

**两个前提（缺一即误判）**：

1. **只在「期望公式数 > 0」时才比** —— `0 === 0` 不算通过，防空文档假绿；
2. **按「包含已排版节点的块数」去重计数**，不数裸节点 —— 因预渲染/缓存命中后
   `.-math` 与 `mjx-container` **可并存**（合法中间态）。

断言内容：
- 块级：AST `math_block` 数 == DOM 中含 `mjx-container` 的 `-math-block` 块数；
- 行内：AST 含 `math_inline` 的**块数** == DOM 中含 `mjx-container[data--inline-math="true"]` 的块数；
- **残留检查（环境无关，永远生效）**：不得存在未排版的裸 `.-math`（含 `$…$` 文本）或 `mjx-merror`。

**⚠️ 环境限制（已实测，有据）**：

| 环境 | 公式排版 | A3 可用性 |
|---|---|---|
| **无头 Edge** | **排不完**（`mjx-container` ≈ 3，宽限耗尽也等不到） | **「已排版」断言不适用** ⇒ 记为 `inconclusive`，**不判 FAIL**；仅保留残留检查 |
| **真机**（WebView2 + GPU） | 排得完（270 个，~1.2–1.5 s） | 完整判据生效 |

依据：[realapp-measurement-protocol.md](realapp-measurement-protocol.md) §1 实测对照表。
⇒ **要完整判 A3，必须用真机模式**：`fidelity_cli.mjs --cdp http://127.0.0.1:9500`。

**禁止**用 `getBBox` / 尺寸 / 可见性判定（会引入布局依赖与抖动）——只用**属性存在性**。

### A4 静默空白看门狗（W1 + W2）

**原设计会误报**，故拆成两条可观测断言：

#### W1（**只针对「有 kindClass 的块」**）

若 `textContent` 去空白后为空，**且该块的 AST kind 不在「允许空文本」白名单**
`{paragraph, heading, list_item, list, blank_line}` 内 ⇒ **FAIL**。

> 合法来源：空 `PARAGRAPH`/`HEADING`/`LIST_ITEM` 占位（`renderer.js:87/96/204` 补 `<br>`）。

#### W2（**只数「无 kindClass 的块」**，不做文本断言）

无 kindClass 的块的 `tag` 必须落在已知白名单
`{h1..h6, p, hr, blockquote, ul, ol, table}` 内 ⇒ 否则 **FAIL**。

> **不对 classless 块做文本断言**（反推不出 kind）。
> 原判据「classless 数 == DOCUMENT/LIST_ITEM 容器数」是**错的**——多数块本来就不带 kindClass，
> 用它会让每个文档全红（首版实测 10–20 处假红）。

**W1/W2 抓的是**：新增/改名 kind 落进 `renderer.js:257`（块级）/ `:436`（内联 `default: return createTextNode("")`）
时**内容静默消失**——这是该失真的**唯一可观测信号**。

---

## 2.5 新增 A 级（task-25 · 渲染保真覆盖面补齐）

> 补齐主预览块级骨架之外的用户可见渲染物。**共性原则：只在「源/期望 > 0」时判定**
> （`0 === 0` 不算通过，防空文档假绿）；「无头恒空」类需真机/数据，不据空判绿。

| 断言 | 覆盖物 | 判据 | 环境 |
|---|---|---|---|
| **A5 图片** | `img[src]` 存在且非空 | 源有 `image` 块 => DOM 至少 1 个 `img` 且都带非空 `src`。**不查 `naturalWidth`**（懒加载/无头不可靠） | headless-ok |
| **A6 链接** | 三类分别判（见 §2.5.1） | 源有 `link`/`wiki_link` => ①**broken wiki** 不要求 href、只要 `data-link-target` 非空且 `tabindex=-1`；②**resolved wiki** 只要 `data-link-target` 非空且 `tabindex=0`；③**普通 md 链接** `a[href]` 必须非空；④全文无残留 `[[x]]` | headless-ok |
| **A7 代码高亮** | `language-*` class | fence 块（语言非空、**非 mermaid**）=> 对应 `code` 带 `language-<lang>`。token 数 = B 级 | headless-ok |
| **A8 表格** | 行列数 vs AST `rows` | 行数 = header?1+rows、列数 = 首行 cell 数。**不比列对齐**（AST 无此字段） | headless-ok |
| **A9 可见效果下限** | bold/italic/code/link/image/mark/font_* | 源有此标记 => DOM 对应元素数 **>0**（只查非零，避开不可反推；精确计数 B 级） | headless-ok |
| **A10 行内公式按块计数** | `\$...\$` vs 块内已排版节点 | 每块行内公式数 == 该块 `mjx-container[data--inline-math=\"true\"]` 数 | **需真机**（无头 inconclusive） |
| **A11 mermaid** | 真出 `svg` + `viewBox` 非空 + 无错误占位 | 源有 mermaid => `.-mermaid-container` 内含 `svg[viewBox]`，无 `.-mermaid-error` | headless-ok（SVG 生成不依赖 MathJax） |

**A10 无头 inconclusive 的原因**：无头 MathJax 只排 ≈3 个（真机 270，见
[realapp-measurement-protocol.md](realapp-measurement-protocol.md) §1）。无头下 A10 的「按块数量一致」
不可判，仅记录；完整判定与判别力验证在真机（`--cdp`）。

### 2.5.0 A6 链接规格（三类，**不要退回"所有 a 都必须有 href"**）

> **曾经的错误规格**：`a[href]` 必须非空。实测 legacy 的 wikilink **无论 resolved 还是 broken 都不设 href**
> （`app.js:6339-6360` 只加 class / `tabindex` / `title`，从不 `setAttribute('href')`），跳转靠 JS click +
> `data-link-target`。于是含 broken wiki 的真实文档（如 `scale-5k` 的 270 个）会被**假红**。

| 类 | DOM 特征 | 判据 |
|---|---|---|
| **broken wiki** | `-link-broken` + `memoria-broken-link`，`tabindex=-1` | `data-link-target` 非空；`tabindex` **不得**为 0；**不要求 href**（不可跳转是正确行为） |
| **resolved wiki** | `-link-resolved` / `-link-multi`，`tabindex=0` | `data-link-target` 非空；`tabindex` **不得**为 -1；**不要求 href** |
| **pending wiki** | `-link-pending` | 合法中间态，不判 |
| **普通 md 链接** | 上述 class 都没有 | `a[href]` **必须**非空 |

**为什么 broken 是正常态**：「先写 `[[概念]]` 再补页面」是用户日常写作的常态。把 broken 当失败，
任何含未解析 wiki 的文档都会永远红，而我们会误以为"新管线坏了"——**是尺子错了，不是实现错了**。

**判别力自证**（在 `artifacts/_link_fixture_kb` 上，含 3 resolved + 2 broken + 2 ordinary）：

| 变异 | 期望 | 实测 |
|---|---|---|
| `resolved-not-focusable`（resolved 改 `tabindex=-1`） | 红 | ✅ 抓到 1/1 |
| `broken-focusable`（broken 改 `tabindex=0`） | 红 | ✅ 抓到 1/1 |
| `ordinary-nohref`（普通链接清空 href） | 红 | ✅ 抓到 1/1 |

---

### 2.5.1 未覆盖（须登记，不假装覆盖）

- **agent 面板流式**（`.-agent-msg-body`）、**助手弹窗 / 复阅卡**：✅ **已用「副本 + 夹具」关闭**。
  做法（`scripts/benchmark/surface/make_agent_fixture.py`）：
  1. **复制** KB 到 `artifacts/_realapp_fixture_kb/`（**绝不污染 `docs/example/**` 与用户库**，实测源 KB 保持 git 干净）；
  2. 注入 `.memoria/agent/sessions/<id>.jsonl`（user/message + assistant/message，含 markdown/表格/代码/公式）；
  3. 注入 `.memoria/agent/review/cards.json`（1 张含公式的卡）；
  4. 真机 `--cdp` 下点「历史」页签 → 点夹具会话行（真实用户路径），断言 `.-agent-msg-body` 块数>0、无占位；
     调 `window.MemoriaReviewModal.open()`（`review-modal.js:814` 真实入口）打开弹窗，断言 `.-review-body` 块数>0、公式已排。
  
  **实测结果**（mode=real）：agent 助手气泡 **8 块 + strong/em/table/pre + 1 个已排公式**；
  复阅卡 `listItems=1`；弹窗 `blocks=1, mathJax=1`。两者 `usesSrcLineAttr=0` ⇒ **确认不依赖 `data--src-line`**（P4b 已移除）。
- **导出**：当前无稳定可自动化入口（可能走系统文件对话框）=> 登记缺口。
- **窗口化口径**：默认取**全渲染模式**基线（开口径①）；子集孔径（②）另记录，非默认。

---

## 3. B 级 · 记录但不阻断（`warn`，只进报告）

**B 级红不判 FAIL**，仅作为趋势与排查线索。

### B5 文本保真（**必须先归一**）

归一规则（按序施加，7 条）：

1. **公式**：两侧都剥外层 `$` / `$$` 再比；
2. **列表 / 引用**：只比内容，容器标记从 AST 侧剥除；
3. **空块**：`""` ≡ `<br>`-only ≡ `\u00a0`；
4. **frontmatter / mermaid**：剥围栏后比；
5. **wiki / link**：**只比显示文本**，不比 target / url；
6. **表格**：先比「行数×列数 + 纯文本」，格式交给结构项；
7. **最后**才做 `\s+` 折叠 + `trim`（公式须走第 1 条单独比，否则空格被吃）。

> **不先归一定会让大库全红 ⇒ 指标退化成「永远红的形式」，失去门槛意义**
> （render-perf 评估 §3 列出 12 类天然不等，均为当前实现的事实而非 bug）。

### B6 结构保真（**只比 AST 层真实存在的字段**）

heading level / list 项数 / table 行数 / code fence 语言 / 引用嵌套。

> **不比「表格列对齐」**——它在 AST 层**就不存在**（`ast.js:203 table(header, rows)`），
> 那是解析期即丢，属于**不可满足的断言**。

### B7 内联格式（**只记录，永不 FAIL**）

按块记录 `strong / em / code / a / img / highlight` 计数。

> **降级理由**：`BOLD_ITALIC` 与 `BOLD` 同为 `<strong>`（`renderer.js:323`）、
> 5 种 `font_*` 是无 class 的 `<span>`（`:349-377`）⇒ **DOM→AST 不可反推**，硬比必大量假阳性。

---

## 4. 全局签名（阶段 2 的核心工具）

```
fidelitySignature = sha256( 规范化投影 B )   // v2：含 A5–A11 DOM 投影，obj 内带 v:2 标记
```

**签名版本**：

| 版本 | 涵盖断言 | 状态 |
|---|---|---|
| **v1** | A1–A4 + B5–B7 | **保留，标 `superseded`**（基线 `fidelity-baseline_19971759.json`） |
| **v2** | A1–A11 + B5–B7 | **当前生效**（基线 `fidelity-Sold-v2_<sha>.json`） |

> **中途不得换口径**：阶段 2 用 `S_old v2` 做新旧对比；v1 仅作历史参考，不参与阶段 2 判定。

**签名内容**：块数 + kind 序列 + tag 序列 + 已排版公式块数 + 行内公式块数 + **归一化文本**
   +（v2 新增）img/anchor/lang/table/effect-floor/mermaid 计数

**⚠️ 文本归一化必须排除易变内容**：
- `mermaid` / `-mermaid-container` / `-mermaid-error` 块的文本 → 置为占位符
- `-math-block` 的文本 → 置为占位符

> **理由**：mermaid 渲染成 `<svg>` 后，其内部节点 id、`<style>` 内容**每次生成都不同**（随机）；
> 公式排版产物同理。若纳入签名，**签名永远不稳定**，diff 工具直接废掉
> （实测：`04-non-editable.md` 两次运行签名不一致，就是这条）。
> 这两类的保真由 **A2（kind）+ A3（数量）** 覆盖，不依赖文本。

### 4.1 阶段 2 用法

| 步骤 | 动作 |
|---|---|
| 1 | 在当前（旧）实现上产出 **`S_old`** 基线 → `results/fidelity-baseline_<sha>.json` |
| 2 | 新实现产出 **`S_new`** |
| 3 | 逐文档比 `S_old` vs `S_new`：**diff 必须为 0**，或**每一项都被显式归类** |
| 4 | 归类的两个合法类别：**bug**（回退修复）/ **有意变更**（需在 PR 说明） |

---

## 5. 执行

### 5.1 前提：**A 级在 HEAD 必须全绿**

> **「HEAD 全绿」是这套指标能被当作门槛的前提。**
> 任一 A 级在 HEAD 上就是红的 ⇒ 要么是真 bug（有价值，先修），要么是指标设计缺陷（先修指标）。
> **不要拿红的指标去判阶段 2。**

**自洽守卫（必须有）**：`openDoc` 后必须等到

```
parse(state.doc.body).blocks.length == #preview .-src-block 数
```

否则 AST 与 DOM 来自**不同文档快照**，逐位比对必然错位（实测导致 21–24 处假红）。
另需：`localStorage`/启动尾动作会**异步自动打开默认文件覆盖 currentPath** ⇒ 必须重试确认。

### 5.2 两种模式（**互斥，语义不同**）

| 模式 | 参数 | 行为 | 适用 |
|---|---|---|---|
| **harness** | `--url http://127.0.0.1:<port>/` | CLI 自起无头 Edge → 导航到该 URL | CI / 常规（A3 受限） |
| **真机 attach** | `--cdp http://127.0.0.1:9500` | 只 attach，不启浏览器、不导航 | **完整 A3** |

```powershell
# harness 模式（推荐日常）
python scripts\benchmark\surface\run_fidelity.py --label baseline

# 真机模式（完整 A3 公式判据）
node scripts\benchmark\surface\fidelity_cli.mjs --cdp http://127.0.0.1:9500 `
     --files corpus/04-non-editable.md --out results\fidelity-realapp.json
```

### 5.3 基线文档（≥3 个，覆盖不同结构）

| 文档 | 覆盖 |
|---|---|
| `corpus/03-block-boundaries.md` | 小文档、块边界、空行、列表 |
| `corpus/04-non-editable.md` | **表格 + 公式 + mermaid**（教材型） |
| `corpus/07-extremes.md` | 219 块、表格 + 列表、行内公式 |

---

## 5.4 渲染就绪判定（P2c 前置 · 公式 / mermaid 异步）

> **为什么需要**：MathJax 与 mermaid 都是异步渲染（MathJax 实测 2712 行教材约 2.0–2.2s；
> mermaid 逐块 `await`，无全局句柄）。**早取快照 = 假 diff；晚取 = 白等。**
> 没有可靠的"渲染完成"信号，P2c 的签名对比全是假数据。

### 5.4.1 三态 + inconclusive

| 状态 | 含义 | 可否据此判等 |
|---|---|---|
| `ready` | 语义完成 **且** idle 稳定 | ✅ 唯一可信 |
| `timeout` | 到期仍未满足 | ❌ **绝不冒充 ready** |
| `failed` | 有明确失败证据（如 `.-mermaid-error`） | ❌ |
| `inconclusive` | **无头**（MathJax 排不完 ≈3 vs 真机 270） | ❌ 不判绿也不判红 |

### 5.4.2 判据（两条腿，缺一不可）

| 渲染物 | 语义完成判据 |
|---|---|
| **公式** | **待排容器口径**：`expected = 已产出 mjx-container 数 + 尚未产出 mjx 的容器数`（未排的行内 `.-math` span 与未排的 `.-math-block`）。完成判据 = `nonEmpty >= expected`；并 await `state._mathPending`（应用自己的 `typesetPromise` 链 = 最强信号） |
| **mermaid** | `residualSrc === 0`（无残留 `code.language-mermaid`）且每个 `.-mermaid-container` 内 `svg[viewBox]` 非空；出现 `.-mermaid-error` ⇒ 立即 `failed` |

**idle**：连续 **3 帧**「已排版数 + 容器数 + svg 数 + 待排容器数」不变。

#### ⚠️ 两个已修正的计数口径错误（务必不要写回去）

| # | 错误写法 | 后果 | 正确写法 |
|---|---|---|---|
| **1** | `expected = querySelectorAll('.-math, [data-formula]').length` | `data-formula` **只挂在 mjx-container 上**（`app.js:2069`），typeset 后同一公式同时命中两个选择器 ⇒ **重复计数**。`corpus/02-inline-edges.md`（1 行内/0 块）得到 `expected=2 typeset=1` ⇒ **永远差 1 ⇒ timeout**。scale-5k 因 135+135 恰好 270=270 才侥幸没暴露 | 按**待排容器**计：`expected = typeset + pendingInline + pendingBlock` |
| **2** | 把 `data-formula` 当作 A3/完整性的**依赖判据** | `data-formula` **从来不是 A3 的判据**（本文件 §2 注释明写"不要求 data-formula"）。据此构造"删 data-formula ⇒ 应红"的变异是**错的** | A3 依赖 `mjx-container` 的有无与数量；变异应用 drop-math-block / 去 `data--inline-math` / 坏 mermaid viewBox 等**真依赖**项 |

**idle**：连续 **3 帧**「已排版数 + 容器数 + svg 数」不变。

**真实性守卫**：判 `ready` 但 `expected > 0 且 nonEmpty === 0` ⇒ 降级 `timeout`（`ready-but-zero-typeset`）。

### 5.4.3 ⛔ 三条被禁的做法（历史踩坑）

| 禁止 | 原因 |
|---|---|
| **固定 `sleep(N)`** | 随文档规模失准（曾 `sleep(2500)` 仍不够 ⇒ 假红） |
| **`getBBox`** | 无头/不可见时恒为 0 |
| **「固定帧等待」当就绪判据** | kpHover 教训：两帧 16.7ms 是**帧成本**，不是渲染完成 |

> 帧只用于 **idle 稳定性**；**语义完成由 DOM 事实决定**。

### 5.4.4 判别力自证（硬要求）

| 自证 | 构造 | 期望 | 实测 |
|---|---|---|---|
| **S1 抢拍不误报** | 注入 40 个未排版公式占位（expected 270→310） | 不得 ready | ✅ `snapshotNow=not-ready`；`waitForRenderReady` 802ms 后 `timeout` |
| **S2 坏 mermaid** | 注入 `.-mermaid-error` | `failed` | ✅ `failed` |
| **S3 timeout** | `minFrames=999999` + `timeoutMs=120` | `timeout` | ✅ `timeout`(127.7ms) |
| **S0 正常就绪**（真机） | `scale-5k.md` | `ready` | ✅ 公式 **270/270**、mermaid **135/135**、等待 **25.8ms** |

> **S1 的教训**：验证"判据不误报"**必须确定性地制造被测量状态**。
> 前两版试图靠时序（重开文档 / 人为延迟 typeset）都失败 —— 因为命中**预览 DOM 缓存**
> （`previewCacheMax` 最小夹到 1，无法禁用），根本没进入"渲染中"。

### 5.4.5 接入方式

`fidelity_cli.mjs` 在取快照**前**等待就绪，结果写入
`documents[<file>].renderReady`（三态 + `elapsedMs` + 计数 + `appPending`）。

**不进入签名**：`renderReady` / 耗时是产物字段；`signatureNorm` 内**无**易变字段。

参数：`--ready-timeout <ms>`（默认 30000）。

---

## 5.5 新旧管线对比（阶段 2 唯一判等工具）

> **归属**：`scripts/benchmark/surface/compare_signatures.mjs` 是阶段 2 **唯一**的比较器。
> 任何其它人/Agent **不得另写第二个 comparator**（避免两套判据并存）。

### 5.5.1 命令

```bash
# 1) 取 legacy 基线投影（会写入 signatureNorm + nondetStripped）
python scripts/benchmark/surface/run_fidelity.py --label legacy-base

# 2) 取待比较侧投影（P2a 阶段由 surface-new 的临时 driver 产出，见 §5.5.4）
#    产物格式与上一步相同：results/fidelity-<label>_<sha>.json

# 3) 按 kind 过滤对比（P2a 默认只声明它已实现的 5 类块）
node scripts/benchmark/surface/compare_signatures.mjs \
     --baseline scripts/benchmark/surface/results/fidelity-legacy-base_<sha>.json \
     --current  scripts/benchmark/surface/results/fidelity-<new-side>_<sha>.json \
     --supported paragraph,heading,listItem,list,blockquote,hr \
     --out artifacts/agent/verify/compare-p2a.json
```

退出码：`0` = 无 diff（可含 `unsupported`）；`1` = 存在 `diff`；`2` = 输入错误。

### 5.5.2 三种结论的语义（**关键，务必区分**）

| 结论 | 含义 | 是否算失败 |
|---|---|---|
| **`match`** | 该 kind 双方投影**完全一致**（**逐块比 `{tag, textNorm}`**） | 否 |
| **`diff`** | 该 kind **双方都支持**，但投影**不一致** | ✅ **是** |
| **`unsupported`** | 该 kind **至少一方未实现** | ❌ **不算失败**（仅记录） |
| **`schema_error`** | 该侧**缺少/无法解析 `signatureNorm`** | ✅ **是（绝不静默 match）** |
| `missing` | 某文档只在一侧存在 | 是（输入不完整） |

> **为什么必须有 `unsupported`**：P2a 的 `new` 只实现 5 类块（paragraph / heading /
> listItem / list / blockquote / hr），其余 kind（table / mermaid / code_block / math_block /
> image / blank…）**尚未实现**。若把它们造成的差异一并算 `diff`，P2a **永远红、无法推进**。
> 因此：**未实现 ≠ 退化**。只有「双方都声称支持、结果却不同」才是真回归。

### 5.5.2.1 ⚠️ 反例：比较器**不得依赖上游未落盘的字段**

**这次真实踩到的坑（必写死，防复发）**：

`compare_signatures.mjs` 早期版本从 `run1.signatureNorm` 取每块文本，而
`run_fidelity.py` 当时**并不落盘 `signatureNorm`** ⇒ 两侧文本恒为空
⇒ 只比 `{kind, tag}` ⇒ **即使 new 管线把 5 类块的文本全渲染错，也会报「0 diff」**。

这是本项目**第三个「假通过」家族成员**（前两个：`END_TO_START` 被 catch 吞、A15 `failed:0` 误当 pass）。

**铁律（适用于所有判等工具）**：

> **任何「字段缺失 ⇒ 值恒空 ⇒ 比较相等 ⇒ 判通过」的路径都是假通过。**
> 比较器必须：① 显式校验输入 schema，缺失即 **`schema_error` 失败**；
> ② 比较粒度必须**含内容**（`textNorm` / 归一化 HTML），不能只比结构标签。

**修复三件套**（均已落地）：

1. `fidelity_cli.mjs` 落盘 `run1.signatureNorm`（+ `nondetStripped`），新旧两侧**同 schema、`v:2`**；
2. 比较器逐块比 `{tag, textNorm}`（`fragment()` → `JSON.stringify` 全等）；
3. `signatureNorm` 缺失/不可解析 ⇒ `schema_error` ⇒ **FAIL**。

### 5.5.3 自证（工具本身可用）

| 自证 | 做法 | 期望 | 实测 |
|---|---|---|---|
| **G-a 双跑一致** | legacy 快照 vs legacy 快照 | `diff=0`、`PASS`、exit 0 | ✅ `match=18 diff=0 unsupported=12` |
| **G-b 注入必报** | 改动一处 paragraph 文本 | 报 `diff`、`FAIL`、exit 1 | ✅ `diff=5`、exit 1 |
| **G-c unsupported 不计失败** | 只改动未支持的 `-table` | 仍 `PASS`、exit 0 | ✅ `diff=0`、exit 0 |
| **G-d 文本必须参与** | kind/tag 全同、只改 `textNorm` | 报 `diff`、exit 1 | ✅ `diff=5`、exit 1 |
| **G-e 缺字段必失败** | 两侧均缺 `signatureNorm`（旧 schema） | `schema_error`、exit 1（**不得静默 match**） | ✅ `schema_error=5`、exit 1 |

### 5.5.1.1 真机模式（`--cdp`）与无头模式（默认）

> **两种模式绝不能混跑**：真机 MathJax 排 270 个、无头只排 ≈3 ⇒ 混着比 = **假 diff**。
> `run_fidelity.py` 会把 `mode` 写进 JSON 与报告头，下游可据此拒绝跨模式比较。

```bash
# ── 无头（默认，CI 友好；不需要应用在跑）──
python scripts/benchmark/surface/run_fidelity.py --label headless-base

# ── 真机（直连已运行应用的 CDP；本 runner 不起 harness）──
python scripts/benchmark/surface/run_fidelity.py \
     --cdp http://127.0.0.1:9500 \
     --kb tests/probe-kb \
     --files scale/scale-5k.md \
     --label real-p2c \
     --ready-timeout 60000 \
     --timeout 600
```

**启动真机的完整封装**（含整树清理 + 端口释放确认）：

```powershell
powershell -File scripts/benchmark/surface/run_fidelity_real.ps1 \
    -Kb tests\probe-kb -Files scale/scale-5k.md -Label real-p2c -ReadyTimeout 60000
```

| 参数 | 说明 |
|---|---|
| `--cdp <endpoint>` | **真机模式**：直连已运行应用；**不启动 harness**、不复制语料。与 `--url` 语义互斥（`fidelity_cli.mjs` 内亦有校验） |
| `--ready-timeout <ms>` | 渲染就绪等待上限（公式/mermaid 异步），原样透传 `fidelity_cli.mjs` |
| `--kb` | 真机模式下**仅用于校验目录存在**（应用已在自己的 KB 上运行） |

**产物**：`documents[<file>].renderReady` = `{status, elapsedMs, math, mermaid, appPending, frames}`；
JSON 顶层 `mode` = `real` / `headless`。

> **只有 `renderReady.status === 'ready'` 的快照可用于判等**；
> `timeout`/`failed` 表示快照可能早取或渲染异常；`inconclusive`（无头）**不据此判绿也不判红**。

---

### 5.5.4 `new` 侧投影入口（**当前临时，将被正式取代**）

P2a 阶段由 `surface-new` 在 `artifacts/agent/verify/` 写**临时 driver**：
`openFile → switchTo('new') → 等块数自洽 → 取 A 级投影`，
**必须复用 `fidelity.mjs` 的 `PROBE_SOURCE` / 归一化 / 签名**，**禁止复制投影逻辑**。

> **计划**：该临时 driver 将在后续由 `run_fidelity.py --surface legacy|new|dual` 正式化取代，
> driver 随之退休。本契约在该入口落地后更新本节。

---

## 6. 自证判别力（硬要求）

### 6.1 变异测试：每个变异都必须被判红

| 变异 kind | 注入动作 | 应及时红的断言 | 实测 |
|---|---|---|---|
| **`drop-block`** | 删掉一个块 | **A1 块数** | ✅ 抓到 3/3 |
| **`reorder`** | 打乱 `data--block-index` | **A2 块序** | ✅ 抓到 3/3 |
| **`empty-block`** | 把某块内容清空 | **A4 W1** | ✅ 抓到 2/3 |
| `math` | 删掉公式节点 | A1 / A2 | ✅ 抓到 1/3（仅含公式的文档） |
| `char` | 改块内 1 个字符 | **B5 文本（warn）** | ❌ A 级**按设计不抓**（B5 只记录） |

> **`char` 抓不到是设计正确，不是缺陷**：A 级刻意不含文本比对（文本噪声大、需归一），
> 文本保真由 B5（warn）负责。

**判定语义（与常规相反）**：变异模式下「**判红 = 通过**」。
`run_fidelity.py --mutate <kind>` 若某类变异**一个文档都没抓到** ⇒ 退出码 1（该变异无判别力）。

### 6.2 复现性：不动时连跑 2 次签名**必须完全相同**

实测（HEAD 基线）：

| 文档 | run1 签名 | run2 签名 | 一致 |
|---|---|---|---|
| `03-block-boundaries.md` | `6071cc337566…` | `6071cc337566…` | ✅ |
| `04-non-editable.md` | `17dcfe9147c7…` | `17dcfe9147c7…` | ✅ |
| `07-extremes.md` | `5edc6c8e06ea…` | `5edc6c8e06ea…` | ✅ |

---

## 7. 适用范围与局限

| # | 局限 | 说明 |
|---|---|---|
| L1 | **A3 在无头环境不完整** | 无头排不完公式 ⇒ 「已排版」断言记 `inconclusive`。完整判 A3 需真机 `--cdp`。 |
| L2 | **B5/B6/B7 只记录不阻断** | 阶段 2 若把文本或样式改坏，**A 级不会红**，需人看 B 级报告。这是刻意的信噪比权衡。 |
| L3 | **内联格式不做 kind 级判定** | 见 §3 B7：DOM→AST 不可反推。 |
| L4 | **表格列对齐不在契约内** | AST 层即无该字段。 |
| L5 | **只覆盖「渲染正确性」，不覆盖性能** | 性能见 [phase1-performance-gate.md](phase1-performance-gate.md) 与 C9。 |
| L6 | **单块增量重渲路径覆盖有限** | 当前基线是**整篇渲染**后的快照；P2 的 `reRenderBlock` 局部路径需另跑（编辑后取快照）才能覆盖。 |
| L7 | **签名对块顺序敏感** | 这是**有意的**（A2 就是抓块序错乱）；若阶段 2 有意改变块序，必须显式归类。 |

---

## 8. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-10-20 | 初版。A/B 分级；A3 环境敏感处理；W1/W2 按 Lead 收紧判据实现；签名排除 mermaid/公式易变文本；变异判别力自证 |
| 2026-10-20 | **task-25 覆盖面补齐**：新增 A5 图片 / A6 链接 / A7 代码高亮(class) / A8 表格行列 / A9 可见效果下限 / A10 行内公式按块 / A11 mermaid 七条断言。基线文档扩为 5 个（+05-images 图片样本、+README 加粗样本） |
| 2026-10-20 | **签名升级 v2**：纳入 A5-A11 DOM 投影，obj 内带 `v:2`；v1 基线保留标 `superseded`。落盘 `fidelity-Sold-v2_<sha>.json` |
| 2026-10-20 | 判别力自证：新增 6 个变异（img-src/strip-lang/drop-td/kill-mermaid-svg/strip-bold 全部判红；strip-inline-formula 无头 inconclusive，判别力在真机）。复现性 5 文档签名 2 次一致 |
| 2026-10-20 | **签名归一化落地**：内置剥离非确定 id（mermaid 随机 SVG id、MathJax `MJX-*` id、CSS `#id` 选择器引用、`data-block-id`），并纳入签名 `htmlFingerprint`。自证：只换随机 id ⇒ 签名不变；真改内容 ⇒ 签名变 |
| 2026-10-20 | **对比机制自证 + `compare_signatures.mjs`**（阶段 2 唯一比较器）：按 kind 过滤，`match`/`diff`/`unsupported` 三态，**`unsupported` 不计失败**（未实现 ≠ 退化）。自证：legacy-vs-legacy 0 diff、注入必报 diff、未支持 kind 仍 PASS。见 §5.5 |
| 2026-10-20 | **修「假 match」漏洞**（第三个假通过家族）：早期比较器依赖未落盘的 `signatureNorm` ⇒ 文本恒空 ⇒ 只比 kind+tag ⇒ 误判 0 diff。已修：落盘 `signatureNorm`（同 schema v:2）、逐块比 `{tag,textNorm}`、缺失即 `schema_error` 失败。自证 G-d（文本变必红）/G-e（缺字段必失败）均通过。见 §5.5.2.1 |
| 2026-10-21 | **渲染就绪判定**（P2c 前置，§5.4）：公式/mermaid 异步就绪三态 `ready`/`timeout`/`failed` + 无头 `inconclusive`；**禁止固定 sleep / getBBox / 固定帧等待**。真机 270 公式 135 mermaid 就绪 25.8ms；S1/S2/S3 判别力自证全过；无头全 inconclusive |
| 2026-10-21 | **`run_fidelity.py` 补 `--cdp` / `--ready-timeout`**（§5.5.1.1）：真机模式直连 CDP、不启 harness；`mode` 标注进 JSON/报告，**真机与无头不得混跑**。真机实测 `scale-5k`：`renderReady=ready`、公式 **270/270**、mermaid **135/135**、等待 22.5ms。无 `--cdp` 时行为不变（4 组回归 0 diff） |
