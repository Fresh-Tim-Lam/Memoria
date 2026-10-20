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
fidelitySignature = sha256( 规范化投影 B )
```

**签名内容**：块数 + kind 序列 + tag 序列 + 已排版公式块数 + 行内公式块数 + **归一化文本**

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
