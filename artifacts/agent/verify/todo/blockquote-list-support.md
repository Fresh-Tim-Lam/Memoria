# task-155 · 引用块内列表（`> - item`）—— **只读调查结论**（未改任何 src）

> 状态：**第一步（调查）完成，等 Lead 决定本轮范围**。本轮**零 src 改动**、无 commit。
> 基线：HEAD=`225110bb`（task-147 已提交；task-150 修复仍在工作区未提交，与本调查无关）。
> 人原话：「我需要在 `> ` 里面使用 ` - `」。

---

## 0. 一句话结论

**AST 是唯一瓶颈**：`> - item` 被解析成「引用块里的**普通段落文本** `- item`」，
因此**预览**（AST→render-core）也不显示列表；但**源码往返已经逐字节保真**（现状不会损坏数据）。
要支持"在引用里敲 `- ` 得到列表"，需要 **parser+SourceGen+mapper+render-core 四处联动（一期）+ 编辑管线适配（二期）**，不是单点改动。

---

## 1. ① parser / lexer：**不支持**（AST 实证）

脚本：`blockquote-list-probe.js`（node 加载真实 `ast/lexer/parser/source-gen/mapper`，只读）。
日志：`blockquote-list-probe.log`。

```
src="> - a\n> - b"
AST = blockquote{ prefixes:["> ","> "], children:[
        paragraph{ text:"- a" },
        paragraph{ text:"- b" } ] }
```
- lexer 的列表前缀（`lexer.js:76-106`）只在 **`i === 0`（行首）** 识别；
  `blockquote_prefix` 在 i=0 被吃掉后，`- ` 已不在行首 ⇒ 永远不会产生 `list_prefix`。
- parser 的引用分支（`parser.js:482-501`）对每个引用行**一律** `AST.paragraph(parseInline(...))`，
  明确写着「每行解析为一个独立段落」⇒ 引用块 children **只能装段落**。

**但**：`generate(parse(src)) === src` 且二次往返幂等（9 个样本全绿，含 `> - $x$ **bold**`、`> 1. a`、`> > - a`、`> a\n>\n> - b`）。
⇒ **现状源码层无数据风险**：用户的 `> - item` 保存/加载不会丢字符（只是没有列表语义）。

## 2. ② 现有文档里已经有人这么写（真实用户内容）

`docs/example/AAA_KnowledgeBase/MachineLearning/Eigen_Face.md:155-158`（只读检索，未改）：
```
153: > **特征人脸法 = PCA + SVD技巧 + 投影降维 + 最近邻识别**
154: >
155: > - 从一堆人脸中提炼出 $ k $ 个“基础脸型”（特征人脸）
156: > - 每张人脸表示为这些基础脸型的加权组合（$ k $ 个系数）
157: > - 识别时比较两张脸的系数向量是否接近
158: > - 原始需要 $ d^2 $ 个数，现在只需要 $ k $ 个数（$ k \ll d^2 $）
```
**当前渲染**：引用块内的**普通段落文本**（字面 `- `），不是列表（真机证据见 §3）。
⇒ 这不是"没人用的边缘语法"，用户库里已经有 4 行在等它变成列表。

## 3. ③ 预览也不渲染列表（真机 DOM 实证）

真机（临时 KB 副本 + CDP，`blockquote-list-realapp.log` / `-realapp.json`）：
```
预览 blockquote HTML = "<p>- item one</p><p>- item two</p>"
blockquote 内 <ul> 数 = 0，<li> 数 = 0
```
**为什么**：预览不是 marked（`markdown-preview.js` 的 marked 只用于别处），而是
`app.js:2650-2670` → `P.parse(body)` → **`render-core.renderDocument(_doc)`** 的 **AST 渲染**；
`render-core.js:395-410` 的 blockquote 渲染器**把 children 一律包成 `<p>`** + `renderInlineList(inner.children)`：
```js
blockquote: function (block, blockIndex) {
  var el = _newBlockEl("blockquote", "", blockIndex);
  for (...children...) {
    var qEl = document.createElement("p");
    renderInlineList(inner.children, qEl);   // ← 只当行内内容，列表语义在这里被抹掉
    el.appendChild(qEl);
  }
}
```
⇒ **只改 parser 不够**：render-core 的 blockquote 分支必须能渲染子块级 list。

## 4. ④ 列号映射（mapper）：现假设"每 child 一行"，扩展后必须加行跨度表

现状（`mapper.js:400-428` 正向 / `548-575` 反向）：
```
qLineIdx = line - lineCount;              // 1 个 child = 1 行
line += qIdx;                             // 反向同理
col   = 2（blockPrefixLen(BLOCKQUOTE) 常量 "> "）
```
**引入嵌套列表后**：一个 child 会占多行（`blockquote([list([li,li])])` = 1 child / 2 行），
`line - lineCount` 不再等于 child 下标。**实证**（假 AST 注入）：
```
blockquote([ list(a,b) ]) 下：
  srcToAst(1, 2)（第 2 行） = { blockIndex:0, nodePath:[], offset:0 }   ← 第 2 行**无法映射**
  astToSrc(0,[0,0],0)       = { line:0, col:2 }                          ← 只落到第 1 行
```
**另发现一个既有缺陷（非本任务引入，但扩展时必须一起修）**：
mapper 的前缀宽度写死 `2`，而 E28 允许 `>` / `>> ` 等非标准前缀：
```
">abc"   内容起点实际 col=1，astToSrc 反向给 col=2  ⇒ 偏 1 列
">> abc" 内容起点实际 col=3，反向给 col=2        ⇒ 偏 1 列
```
⇒ 任何扩展都应按 `block.prefixes[child]` 的真实长度算列（与 SourceGen 的 E28 口径对齐）。

**SourceGen 风险实证（最容易写坏文件的一处）**：手工构造「引用块内列表」AST 后：
```
generateBlock(blockquote([list(a,b)])) = "> - a\n- b"
                                              ↑ 第二行**丢了 `> ` 前缀**
```
⇒ 若"只扩 parser 不改 source-gen"，保存即把 `> - b` 写成 `- b`（**逐字节损坏，且是静默的**）。
这正是 Lead 担心的"改一处、别处坏"在此任务上的具体形态。

---

## 5. 改动面统计（"为什么不能一把梭"）

| 文件 | `blockquote` 相关命中 | 性质 |
|---|---|---|
| `app.js` | **28 行**（12018/12038-43/12118-57/12981/13122/13285-13541/13601-13660） | EditSync 的 insertText / splitParagraph / deleteSelection / 跨段删除 / 结构转换，多处写死 `A.blockquote([A.paragraph(nodes)])`、`nodePath[0]=段落索引` |
| `mapper.js` | 10 | 正/反向列号映射（§4） |
| `surface/render-core.js` | 4（395-410） | 预览渲染（§3） |
| `parser.js` | 3（482-501） | AST 生成（§1） |
| `source-gen.js` | 1（70-81） | 逐字节回写（§4 已证会丢前缀） |
| `lexer.js` | 2 | 行首列表前缀（§1） |
| `edit-handler.js` | 0（但依赖 EditSync） | 预览区输入最终落到上述 AST 形状 |

## 6. 真机交互现状（"为什么用户觉得没法用"）

临时副本里 `> plain quote line`，把光标放到 `> ` 之后敲 `- `：
```
源码行  " > - plain quote line"      ← 只是多了两个字符
预览    <p>- plain quote line</p>    ← 仍是段落文本，没有 bullet/缩进
```
静态原因：`convertStructuralBlock`（app.js:12053）**只对 `block.type === "paragraph"` 生效**；
而引用块是 `blockquote`，内层是它的 children 段落 ⇒ 敲 `- ` 不会触发列表转换。

---

## 7. 建议（等 Lead 裁）

### 推荐：**拆两期**
**一期（数据层，纯 AST/渲染/回写；不改编辑交互）**
1. lexer/parser：引用块内按「剥离前缀后的行组」递归识别块级结构（至少 list；有序/无序/嵌套）。
2. blockquote 增加「行跨度」信息（如 `block.lineSpans` / 每 child 的 `srcLine/srcLineEnd`），**保持 `prefixes` 逐字节回写**。
3. SourceGen：按行跨度 + `prefixes` 回写每一行（含列表子项行）—— 硬指标：`> - item` 保存重开**逐字节相等**。
4. render-core：blockquote 的 child 是 list 时渲染 `<ul>/<ol>`（可直接复用现有 list 渲染器）。
5. mapper：正/反向都走行跨度表；前缀宽度按 `prefixes[i]` 真实长度（顺带修 `>`/`>> ` 的既有 off-by-one）。
- 验收：既有 `Eigen_Face.md:155-158` 变成列表且**编辑保存后字节不变**；列号测试含 `>`/`>> `/`> - `（有序含 ≥10 项）。
- 一期上线效果：**已有 `> - ` 文档开始显示为列表**；但"敲 `- ` 自动生成列表"仍不生效。

**二期（编辑器交互）**
- 引用内敲 `- ` → 转 `blockquote([list])`；Enter 续列/子级缩进；Backspace 合并/降级；
- 跨段选中删除、Ctrl+Z 单撤销；EditSync 五个函数按新形状适配。
- 二期回归面 = 上表 app.js 28 处 + EditSync；建议一期合并稳定后再单独立项。

### 若"本轮不做"（替代方案）
现状**不损坏数据**：用户可以在源码里写 `> - item`（保存重开字节保真），只是显示为普通段落、没有列表样式。
替代：`> 段落` 分行 + 空行分段，或把列表放引用块外面。**不建议长期**——用户库已有 4 行真实用例。

### 不推荐
- **只改 parser 不改 source-gen**：会丢 `> ` 前缀（§4 实证）。
- **只让预览渲染列表、AST 不动**：预览与源码/编辑两套事实源，列号与编辑会立刻错位（本项目已多次踩过"第二坐标系"）。
- **只做"敲 `- ` 的编辑器转换"**：转换目标 AST 必须是 `blockquote([list])`，仍要一期全套支持，没有捷径。

---

## 8. 产物（只读调查）

```
artifacts/agent/verify/todo/blockquote-list-support.md          ← 本报告
artifacts/agent/verify/todo/blockquote-list-probe.js            ← AST/SourceGen/mapper 只读探针
artifacts/agent/verify/todo/blockquote-list-probe.log           ← 其输出（9 样本 + 假 AST 注入）
artifacts/agent/verify/todo/blockquote-list-fixture-gen.py      ← 真机夹具（CRLF，临时 KB 副本）
artifacts/agent/verify/todo/blockquote-list-fixture/kb/
artifacts/agent/verify/todo/blockquote-list-realapp-probe.mjs   ← 真机现状探针（预览 DOM / 敲 `- `）
artifacts/agent/verify/todo/blockquote-list-run.ps1              ← 运行器（safe-kill + 临时 KB）
artifacts/agent/verify/todo/blockquote-list-realapp.log/.json    ← 真机证据
```

**边界**：只读调查；真机只用 `%TEMP%` KB 副本；未触碰 `docs/example/AAA_Vocab/**`；
用户 `Package\Memoria.exe`（PID 37620）前后一致；端口 9586 已释放；**未改任何 src、未 commit**。

---

# 9. 一期实施结果（2026-10-26，Lead 批准"一期 + 顺手修 mapper 前缀 off-by-one"）

## 9.1 改动（4 个 src + 1 个单测；未 commit）

| 文件 | diff | 内容 |
|---|---|---|
| `parser.js` | +35/−9 | 引用分支改为：剥前缀 → `parseBlocks` 子解析 → **仅 list 子块保留**（行号换算为绝对），其它子块**逐行还原段落**（保持 `> # x` 等旧语义不变）；每个 child 落 `srcLine/srcLineEnd`（**行跨度单一事实源**） |
| `source-gen.js` | +33/−9 | blockquote 按每个 child 的行跨度**逐行**取前缀回写；修「多行 child 从第二行起丢 `> ` 前缀」（实测旧产物 `"> - a\n- b"`）；无跨度旧 AST 保留 F3 契约（prefixes 不等长 ⇒ 全默认 `> `） |
| `surface/render-core.js` | +37/−2 | blockquote 渲染器支持内层 `<ul>/<ol>`（递归嵌套、有序 `<ol start>`）；**内层列表不带 `-src-block`/`data--block-index`**（不虚增块数、不污染惰性门禁）；`blank_line` 内层保持旧 `<p><br>` 观感 |
| `mapper.js` | +164/−43 | ① 引用前缀宽度改用 `block.prefixes` **真实长度**（修 `>abc` 实际 col1→旧给2、`>> abc` 实际 col3→旧给2 的既有 off-by-one）；② 引用行归属改用 child 行跨度（不再"1 child = 1 行"）；③ 新增引用内列表的正/反向映射（`nodePath=[childIdx,itemIdx,…]`） |
| `scripts/benchmark/maintenance/blockquote_list_test.js` | 新增 | 一期验收单测：A AST、B 15 个样本逐字节往返+幂等、C 9 个 mapper 列号、D 旧 AST 防御 |

**未改** `app.js`（二期才动 28 处假设）、`edit-handler.js`、CSS。

## 9.2 红 → 绿（同一测试，改前后各跑一次）

- **改前红矩阵**（`blockquote-list-RED.log`）：`PASS=32 FAIL=13`
  —— A2/A3/A4/A5/A6（引用内无 list）、C1/C2/C3/C4（前缀/列表列号）、C6/C7/C8/C9（正向映射）；**B 往返基线全绿**。
- **改后**：`PASS=47 FAIL=0`（原 45 + 新增 D1/D2 旧 AST 守卫）。
- 逐字节样本含：`> - a\n> - b`、Eigen_Face 真实四行、`>` 空引用行、`>abc`、`>> abc`、`> > abc`、松散列表（`> - a\n>\n> - b`）、嵌套缩进、有序列表、行内数学/加粗/代码。
- **相关既有单测全绿**：`blockquote_roundtrip_test.js`（E28，80 项）、`blockquote_typing_sequence_test.js`（39 项）、`trailing_space_input_test.js`（62 项）、`edit_cut_undo_test.js`（E30 全 PASS）、`scheduler_vm_test.js`、`m6b_adjust_test.js`。

## 9.3 真机验收（临时 KB 副本，`blockquote-list-realapp.log/.json`）

```
① 预览：blockquote 内 <ul> 数=3，<li> 数=6
   HTML 片段 = <ul class="-src-list -quote-list"><li>item one</li><li>item two</li></ul>
   （含 Eigen_Face 真实形态：`>` 空引用行 + 3 个 `> - ` 项，全部渲染为列表）
② 编辑保存后：引用行 9 → 9，**逐字节相等 = true**（编辑落点在第 1 行标题，非引用行）
③ 重开（openFile 同文件）：仍 <ul>=4 / <li>=7（多出的是探针用例敲出的 `> - plain quote line`），
   说明保存→重开后列表语义稳定、不丢前缀
```
**一期局限（按 Lead 要求明确写死）**：在引用里**敲 `- ` 仍不会生成列表**（`convertStructuralBlock` 只作用于
`paragraph` 块，引用块是 `blockquote`）——真机步骤 ③ 实测：敲完只是字面 `> - plain quote line`。这是**预期**，二期补。

## 9.4 门禁

| 门禁 | 结果 |
|---|---|
| `pytest -q tests` | **1485 passed / 0 failed**（基线 1475，不降；增量来自其他任务新增测试，非本轮） |
| `node --check` 全仓非 vendor JS | **66/66** |
| `i18n_selftest` | **FAIL=0** |
| 12 交互剧本 | **12/12** |
| `prompt_drift_check` | **FAIL=2**，均为 `resources/agent-prompts/kb-spec.zh-CN.md`：① `edge_types.py` 属 **task-154** 改动；② `render-core.js` 属本任务，但工具要求**同一提示词的所有变更依赖一起确认**，单签被拒。`organize.zh-CN.md` 的 render-core 依赖已复核并重签成功 |
| `team_audit` | **FAIL=2**（同源 = 上面 kb-spec 2 条；其余机检绿） |

**待 Lead/arch-contract 处理**：复核 `kb-spec.zh-CN.md` 中 `edge_types.py` 断言后，一条命令同时重签两个依赖即可：
```
python scripts/agent/prompt_drift_check.py --resign resources/agent-prompts/kb-spec.zh-CN.md \
  --dep src/memoria/graph/edge_types.py --dep src/memoria/ui/static/app/js/surface/render-core.js \
  --note "<复核说明：edge_types 断言 + render-core 内层列表渲染断言均仍成立>"
```

## 9.5 相邻发现（非本轮引入，仅登记）

1. **有序列表 `start > 1` 往返会重编号**（既有行为，与引用无关）：`10. ten\n11. eleven` → `1. ten\n2. eleven`
   （source-gen 按 idx 重新编号）。单测里以 INFO 记录，不纳入一期判据。
2. **用户可见变化**：`Eigen_Face.md:155-158` 等已有 `> - ` 内容在本期后**开始显示为列表**（预期收益）。

## 9.6 二期交接（另立任务，blocked_by = task-155 + task-154）

开工**第一步不是改代码**，而是产出 **app.js 28 处 blockquote 假设清单 + 每处影响判定**
（Lead 明确要求；其中可能有几处"当前写法恰好兼容新 AST 形状"不需要改）。
范围：敲 `- ` 转换、Enter 续列/缩进、Backspace 合并/降级、跨段删除、Ctrl+Z 单撤销；EditSync 五函数适配。

