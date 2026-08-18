# 预览区编辑同步 — 编译器基础设施重构方案

---

## 0. 为什么旧方案不成立

### 0.1 当前架构的本质缺陷

```
用户输入 "##" → sourceEdit 插入源码 → reRender → 预览 DOM 变了
                                              ↑
                          光标位置还是按"段落"算的，但 DOM 已经是"标题"了
                          → 映射错位
```

**根因**：源码文本和渲染 DOM 之间没有中间表示（IR）。源码是"平面字符串"，编辑器对它做的所有操作都是字符串拼接，不理解语法语义。当用户输入 `##`、`- `、`> ` 等语法标记时，源码变了，但光标位置计算器不知道"这行从段落变成了标题"，仍然按旧语义计算偏移。

### 0.2 编译器视角的正确架构

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────────────┐
│  Source  │ ──→ │   AST    │ ──→ │  Rendered │     │   User Edit       │
│  (text)  │     │  (tree)  │     │   DOM     │     │  (keyboard/mouse) │
└──────────┘     └──────────┘     └──────────┘     └────────┬─────────┘
     ↑                ↑                                    │
     │                │              ┌──────────┐           │
     │                └──────────────│ Position  │←──────────┘
     │                               │  Mapper   │
     │                               └──────────┘
     │
     └──── Source Generator (AST → text) ──────────────┘
```

**AST 是唯一真理**。编辑修改 AST，然后从 AST 重新生成源码、重新渲染、重新计算光标位置。一切位置计算都基于 AST 节点的语义，而非字符串偏移。

### 0.3 "##" 编辑的完整流程

```
状态: 源码 "Hello world", AST: Paragraph(Text("Hello world"))
      渲染: <p>Hello world</p>
      光标: AST 位置 (blockIndex=0, nodePath=[0], offset=0)

用户输入 "## ":
  1. 映射: AST 位置 → 源码列 0，插入 "## "
  2. 源码变为 "## Hello world"
  3. 重新 parse: AST 变为 Heading(level=2, Text("Hello world"))
     ↑ 注意: AST 节点类型变了！Paragraph → Heading
  4. 源码生成: AST → "## Hello world"
  5. 重新渲染: <h2>Hello world</h2>
  6. 光标恢复: AST 位置 (blockIndex=0, nodePath=[0], offset=0)
     → Mapper 知道 Heading 有 "## " 前缀（3 字符）
     → 渲染偏移 = 0 (在 "H" 之前)
     → 源码列 = 3 (在 "## " 之后)
```

### 0.4 旧 Phase 0-7 为什么不成立

| 旧假设 | 现实 |
|--------|------|
| 每个 block 独立，类型不变 | 用户输入 `##` 会让 paragraph 变 heading |
| 标题前缀 `### ` 是 block 级属性 | 它是 AST 节点的属性，不是字符串前缀 |
| 光标映射 = 列偏移计算 | 光标映射 = AST 节点内位置 + 节点语义 |
| sourceEdit 是简单字符串操作 | sourceEdit 需要触发 re-parse 以更新 AST |

---

## 1. 光标定位机制：三个坐标系

### 1.1 坐标系定义

```
┌──────────────────────────────────────────────────────────────────┐
│  坐标系 A: 源码坐标 (line, col)                                     │
│  例: line=5, col=3  → 源码第 5 行第 3 列                            │
│  问题: 插入/删除字符后 col 会漂移，标题前缀 "##" 让 col 语义不明确     │
│  使用: 仅用于保存到文件、在源码编辑器（CodeMirror）中显示光标           │
├──────────────────────────────────────────────────────────────────┤
│  坐标系 B: AST 坐标 (blockIndex, nodePath, offset)  ← 唯一真理     │
│  例: blockIndex=2, nodePath=[0,1], offset=3                        │
│      → 第 2 个 block 的第 0 个 inline 子节点的第 1 个子节点的 offset=3│
│  优势: 语义稳定，不受字符插入/删除影响，不受前缀/后缀影响              │
│  使用: 所有编辑操作、光标状态存储、跨帧追踪                           │
├──────────────────────────────────────────────────────────────────┤
│  坐标系 C: DOM 坐标 (anchorNode, anchorOffset)                      │
│  例: textNode#123, offset=5                                        │
│  问题: 浏览器唯一能给的坐标，但每次渲染后 DOM 是新对象，引用失效       │
│  使用: 仅在"当前帧"内有效，用于接收用户输入事件和设置光标              │
└──────────────────────────────────────────────────────────────────┘
```

### 1.2 转换链路

```
用户点击/方向键
    │
    ▼
DOM 坐标 (anchorNode, offset)     ← 浏览器给的
    │
    │  domToAst()                  ← Mapper 模块
    ▼
AST 坐标 (blockIndex, nodePath, offset)  ← 唯一真理，存储在这里
    │
    │  编辑操作修改 AST
    │  SourceGen 生成源码
    │  Re-parse 更新 AST（仅当结构变化时）
    ▼
AST 坐标 (新的 blockIndex, nodePath, offset)  ← 重解析后可能变化
    │
    │  astToDom()                  ← Mapper 模块
    ▼
DOM 坐标 (新的 anchorNode, offset) ← 设置给浏览器
```

### 1.3 Mapper 的四个核心函数

```javascript
// DOM → AST：浏览器给了光标位置，算出 AST 中的位置
domToAst(domNode, domOffset) → {
  blockIndex: number,    // 哪个 block
  nodePath: number[],    // 穿过 inline 节点的路径
  offset: number         // 在最终 Text 节点中的偏移
}

// AST → DOM：AST 位置算出 DOM 中对应的 Range
astToDom(blockIndex, nodePath, offset) → Range  // 可直接 setSelection

// 源码 → AST：CodeMirror 光标同步到 AST
srcToAst(line, col) → { blockIndex, nodePath, offset }

// AST → 源码：AST 光标同步到 CodeMirror
astToSrc(blockIndex, nodePath, offset) → { line, col }
```

### 1.4 AST 坐标为何"语义稳定"

```
场景: 在 "Hello world" 的段落中，光标在 "world" 的 "w" 前面

AST 坐标: { blockIndex: 3, nodePath: [0], offset: 6 }
            ↑                ↑            ↑
         第 3 个 block    Paragraph 的     Text("Hello world")
                         第一个子节点      中 offset=6 = "w" 前

用户在 "Hello" 前输入 "## ":
  → AST 修改: Text("Hello world") → Text("## Hello world")
  → SourceGen: "## Hello world"
  → Re-parse: block 3 从 Paragraph 变成了 Heading(2)
  → 新 AST: { blockIndex: 3, nodePath: [0], offset: 9 }
             ↑ 位置不变，但 offset 变成了 9 (因为 "## " 是 3 个字符)

  → astToDom(3, [0], 9):
     Mapper 知道 Heading(2) 有前缀 "## " (3 字符)
     Text("Hello world") 的 offset=9 映射到真实文本 "Hello world" 的 offset=6
     渲染偏移 = 6 (在 "w" 前面)
     → DOM Range: 在 "Hello world" 文本节点的 offset=6 处
```

**关键**：blockIndex 和 nodePath 在结构不变时是稳定的，只有 offset 随编辑变化。Mapper 负责处理前缀/后缀的偏移计算。

### 1.5 对比旧方案的脆弱性

| | 旧方案（源码坐标） | 新方案（AST 坐标） |
|---|---|---|
| 存储格式 | `(line=5, col=3)` | `(blockIndex=2, nodePath=[0], offset=3)` |
| 用户在段落前输入 "## " | col 从 0 变成 3，但映射器不知道语义变了 | offset 从 0 变成 3，Mapper 知道 Heading 前缀，正确映射 |
| 删除一个字符 | col 减 1，映射器靠 `renderedOffsetToSrcCol` 遍历 tokens 猜测 | offset 减 1，Mapper 直接定位到 AST 节点 |
| 渲染后恢复 | 通过 `renderedOff` 反查源码列，O(n) | 通过 AST 位置直接计算 DOM 位置，O(log n) |
| 嵌套格式 | Bold(Highlight(Text)) 中，源码列需要手动累加前缀 | Mapper 递归处理每层前缀，自动累加 |

---

## 2. 性能策略：增量 vs 全量

### 2.1 编辑分两类

| 编辑类型 | 示例 | 频率 | 是否 re-parse | 是否全量渲染 |
|----------|------|:---:|:---:|:---:|
| 纯文本编辑 | 在段落中间输入 "a"、Backspace | ~90% | ❌ | ❌ 只渲染 1 个 block |
| 纯文本编辑 | 在粗体/荧光笔中改文本 | ~5% | ❌ | ❌ 只渲染 1 个 block |
| 结构性编辑 | 输入 "## "（段落变标题） | ~3% | ✅ 单行 | ❌ 只渲染 1 个 block |
| 结构性编辑 | 按 Enter（拆分 block） | ~2% | ✅ 受影响行 | ❌ 只渲染 2 个 block |
| 方向键 | ArrowLeft/Right/Up/Down | 频繁 | ❌ | ❌ 不渲染 |

### 2.2 性能对比

| | 旧方案（当前） | 新方案 AST + 增量 |
|---|---|---|
| 普通打字 | 全量 reRender（~20-50ms） | 增量渲染单 block（~1-3ms） |
| 结构性编辑 | 全量 reRender（~20-50ms） | 增量 re-parse + 增量渲染（~5-10ms） |
| 1000 行文档 | 每次都全量渲染，明显卡顿 | 只渲染 1-2 个 block，无感知 |
| 10000 行文档 | 严重卡顿 | 只渲染 1-2 个 block，仍然流畅 |

### 2.3 增量渲染策略

```
编辑发生后:
  1. 确定受影响的 block 范围（通常是 1-2 个 block）
  2. 对这些 block 重新执行 SourceGen → Re-parse → Render
  3. 用新的 DOM 片段替换旧的 DOM 片段
  4. 恢复光标到新 DOM 中的对应位置

全量渲染仅发生在:
  - 文档初次加载
  - 用户手动触发刷新
  - 涉及 >5 个 block 的结构变化（罕见）
```

---

## 3. 编译器 Pipeline 总览

```
Phase 1  ──→ Phase 2  ──→ Phase 3  ──→ Phase 4  ──→ Phase 5  ──→ Phase 6
AST定义     Lexer       Parser      SourceGen    Mapper      Renderer
(types)    (text→tok)  (tok→AST)   (AST→text)  (AST↔pos)   (AST→DOM)
                                                         │
                                                    Phase 7
                                                 EditHandler
                                              (edit→AST→all)
```

每个 Phase 输出一个独立的、可测试的 JS 模块。Phase N 只依赖 Phase N-1 的接口。

### 文件规划

| 文件 | 模块 | Phase | 核心职责 |
|------|------|:---:|------|
| `m0/js/ast.js` | AST 节点类型定义 | 1 | 类型契约 + 工厂函数 + 遍历工具 |
| `m0/js/lexer.js` | 词法分析器 | 2 | `tokenize(line)` → Token[] |
| `m0/js/parser.js` | 语法分析器 | 3 | `parse(body)` → Document AST |
| `m0/js/source-gen.js` | 源码生成器 | 4 | `generate(doc)` → 源码文本 |
| `m0/js/mapper.js` | 位置映射器 | 5 | `domToAst` / `astToDom` / `srcToAst` / `astToSrc` |
| `m0/js/renderer.js` | AST→DOM 渲染器 | 6 | `render(doc)` → HTMLElement |
| `m0/js/app.js` | 编辑处理器（改造） | 7 | 整合全链路：事件 → AST → 渲染 → 光标 |

### 依赖关系

```
Phase 1 (AST)      ← 无依赖，先做
    ↓
Phase 2 (Lexer)    ← 依赖 Phase 1 的类型定义
    ↓
Phase 3 (Parser)   ← 依赖 Phase 2
    ↓
Phase 4 (SourceGen) ← 依赖 Phase 1，验证 Phase 3
    ↓
Phase 5 (Mapper)   ← 依赖 Phase 1
    ↓
Phase 6 (Renderer) ← 依赖 Phase 3, Phase 5
    ↓
Phase 7 (Edit)     ← 依赖 Phase 3, Phase 4, Phase 5, Phase 6
```

---

## Phase 1: AST 节点类型定义

### 目标

定义所有 AST 节点类型，作为整个 Pipeline 的接口契约。

### 节点层次

```
Document
├── Block[]
│   ├── Frontmatter { yaml: string }
│   ├── BlankLine
│   ├── Heading { level: 1..6, children: Inline[] }
│   ├── Paragraph { children: Inline[] }
│   ├── CodeBlock { lang: string, code: string }
│   ├── MathBlock { formula: string }
│   ├── Image { alt: string, url: string }
│   ├── Table { header: Row, rows: Row[] }
│   ├── Blockquote { children: Block[] }
│   ├── HorizontalRule
│   ├── List { ordered: boolean, items: ListItem[] }
│   └── Mermaid { code: string }
│
└── Inline (行内节点)
    ├── Text { content: string }
    ├── Bold { children: Inline[] }
    ├── Italic { children: Inline[] }
    ├── BoldItalic { children: Inline[] }
    ├── Strikethrough { children: Inline[] }
    ├── Code { code: string }
    ├── Highlight { color: string|null, children: Inline[] }
    ├── FontColor { color: string, children: Inline[] }
    ├── FontSize { size: string, children: Inline[] }
    ├── FontBold { children: Inline[] }
    ├── FontItalic { children: Inline[] }
    ├── FontUnderline { children: Inline[] }
    ├── FontSuperscript { children: Inline[] }
    ├── FontSubscript { children: Inline[] }
    ├── BgColor { color: string, children: Inline[] }
    ├── WikiLink { target: string, display: string }
    ├── Link { text: string, url: string }
    ├── MathInline { formula: string }
    └── Escape { char: string }
```

### 每个节点的 key 字段

```typescript
interface AstNode {
  type: string;
  // 源码范围（parser 填充）
  sourceRange?: { startLine: number; startCol: number; endLine: number; endCol: number };
  // 渲染文本长度（renderer 填充，用于映射）
  renderedLength?: number;
}
```

### 产出文件

`m0/js/ast.js` — 纯类型定义 + 工厂函数 + 节点遍历工具

```javascript
window.MemoriaAST = {
  // 工厂函数
  text(content)        → { type: "text", content }
  bold(children)       → { type: "bold", children }
  heading(level, children) → { type: "heading", level, children }
  paragraph(children)  → { type: "paragraph", children }
  blankLine()          → { type: "blank_line" }
  document(blocks)     → { type: "document", blocks }
  // ... 所有节点类型

  // 遍历工具
  walk(node, visitor)  → 深度优先遍历
  findNode(node, predicate) → 查找节点
  getText(node)        → 提取纯文本内容
  getNodeAt(node, path) → 按路径获取节点
};
```

### 验证方式

| 测试 | 操作 | 验证 |
|------|------|------|
| 创建节点 | `MemoriaAST.heading(2, [MemoriaAST.text("Hi")])` | `{type:"heading", level:2, children:[{type:"text", content:"Hi"}]}` |
| 提取文本 | `MemoriaAST.getText(headingNode)` | `"Hi"` |
| 遍历 | `MemoriaAST.walk(doc, (n) => types.push(n.type))` | 收集所有节点类型 |
| 路径访问 | `MemoriaAST.getNodeAt(doc, [0, 0, 1])` | 正确获取嵌套节点 |

---

## Phase 2: Lexer（词法分析器）

### 目标

将单行源码字符串解析为 Token 数组。纯函数，无副作用。

### 输入输出

```
输入: "### **Hello** [[\\h:blue|world]]"
输出: [
  { type: "heading_prefix", value: "### ", srcStart: 0, srcEnd: 3 },
  { type: "bold_open",      value: "**",  srcStart: 4, srcEnd: 5 },
  { type: "text",           value: "Hello", srcStart: 6, srcEnd: 10 },
  { type: "bold_close",     value: "**",  srcStart: 11, srcEnd: 12 },
  { type: "text",           value: " ",   srcStart: 13, srcEnd: 13 },
  { type: "highlight_open", value: "[[\\h:blue|", srcStart: 14, srcEnd: 24 },
  { type: "text",           value: "world", srcStart: 25, srcEnd: 29 },
  { type: "highlight_close", value: "]]", srcStart: 30, srcEnd: 31 },
]
```

### 设计要点

1. **状态机扫描**：逐字符推进，遇到 `#`、`*`、`[`、`$`、`\` 等特殊字符尝试匹配
2. **最长匹配优先**：`###` 在行首优先匹配为 heading_prefix，`***` 匹配为 bold_italic_open
3. **开闭标记分离**：`**` 分为 `bold_open` 和 `bold_close`（Parser 需要配对）
4. **转义处理**：`\*` → 一个 `text` token，值为 `*`
5. **每个 token 携带 srcStart/srcEnd**：Parser 和 Mapper 的直接输入

### 产出文件

`m0/js/lexer.js`

```javascript
window.MemoriaLexer = {
  tokenize(sourceLine, srcOffset = 0) → Token[]
};
```

### 验证方式（独立可测试，在浏览器控制台运行）

| # | 输入 | 预期 Token 类型序列 |
|---|------|---------------------|
| 1 | `hello` | `[text("hello")]` |
| 2 | `**bold**` | `[bold_open, text("bold"), bold_close]` |
| 3 | `### heading` | `[heading_prefix, text("heading")]` |
| 4 | `[[\h:blue\|高亮]]` | `[highlight_open, text("高亮"), highlight_close]` |
| 5 | `**粗** [[\h\|荧光]]` | `[bold_open, text, bold_close, text, highlight_open, text, highlight_close]` |
| 6 | `***bold italic***` | `[bold_italic_open, text("bold italic"), bold_italic_close]` |
| 7 | `$E=mc^2$` | `[math_inline_open, text("E=mc^2"), math_inline_close]` |
| 8 | `\*not bold\*` | `[text("*not bold*")]` |
| 9 | `[[\sub\|H]]2O` | `[font_sub_open, text("H"), font_sub_close, text("2O")]` |
| 10 | `[link](url)` | `[link_open, text("link"), link_close]` |
| 11 | `![alt](url)` | `[image_open, text("alt"), image_close]` |
| 12 | `- list item` | `[list_prefix, text("list item")]` |
| 13 | `> quote` | `[blockquote_prefix, text("quote")]` |
| 14 | `## ` | `[heading_prefix]` (空文本也应该产出) |

---

## Phase 3: Parser（语法分析器）

### 目标

将 Token 数组解析为 AST。分两层：
- **BlockParser**：全文 → Block[]
- **InlineParser**：单行 Token[] → Inline[]

### 3.1 InlineParser

```
输入: [bold_open, text("Hello"), bold_close, text(" world")]
输出: [Bold(Text("Hello")), Text(" world")]
```

配对逻辑：遇到 `bold_open` → 递归解析内部直到 `bold_close` → 产出 Bold 节点。

### 3.2 BlockParser

```
输入: 全文 Token[][] (每行一个 Token 数组)
输出: Document(Block[])

识别规则（按优先级）:
  1. frontmatter: `---` 开头
  2. 空行: tokens 为空或只有空白
  3. 围栏代码块: 首行以 ``` 或 ~~~ 开头
  4. 数学块: 首行是 $$
  5. 标题: 首 token 是 heading_prefix
  6. 水平线: 首行是 --- 或 *** 且只有这些
  7. 图片: 首 token 是 image_open
  8. 引用: 首 token 是 blockquote_prefix
  9. 列表: 首 token 是 list_prefix
  10. 表格: 包含 | 分隔符
  11. 段落: 默认
```

### 产出文件

`m0/js/parser.js`

```javascript
window.MemoriaParser = {
  parseInline(tokens)  → Inline[],
  parseBlocks(body)    → Block[],
  parse(body)          → Document,
  // 增量解析：只解析 body 中指定行范围
  parseRange(body, startLine, endLine) → Block[]
};
```

### 验证方式 — Round-trip 测试

| # | 输入源码 | parse → AST → 检查 |
|---|----------|-------------------|
| 1 | `hello` | `Document(Paragraph(Text("hello")))` |
| 2 | `**bold** text` | `Document(Paragraph(Bold(Text("bold")), Text(" text")))` |
| 3 | `# Title\n\nParagraph` | `Document(Heading(1, Text("Title")), BlankLine, Paragraph(Text("Paragraph")))` |
| 4 | `[[\h:blue\|高亮]]` | `Document(Paragraph(Highlight("blue", Text("高亮"))))` |
| 5 | `- item1\n- item2` | `Document(List(false, [ListItem(Text("item1")), ListItem(Text("item2"))]))` |
| 6 | `` ```js\ncode\n``` `` | `Document(CodeBlock("js", "code"))` |
| 7 | `![alt](url)` | `Document(Image("alt", "url"))` |
| 8 | `> quote line` | `Document(Blockquote(Paragraph(Text("quote line"))))` |
| 9 | 空行 | `Document(BlankLine)` |
| 10 | `**粗** [[\h\|荧光]] *斜*` | 3 个 Inline 节点正确嵌套 |

---

## Phase 4: Source Generator（源码生成器）

### 目标

从 AST 重新生成源码文本。这是 Parser 的逆操作。

**为什么需要它**：编辑修改 AST 后，需要生成新的源码文本写入文件。但更重要的是，**round-trip 保真度**是验证整个 Parser 正确性的标准。

### 核心约束

```
对于任意合法源码 S:
  generate(parse(S)) === S   (Round-trip 保真)
```

### 产出文件

`m0/js/source-gen.js`

```javascript
window.MemoriaSourceGen = {
  generateBlock(block)  → string,
  generateInline(node)  → string,
  generate(doc)         → string,   // 全文生成
  generateRange(doc, startBlock, endBlock) → string  // 增量生成
};
```

### 生成规则（每种节点 → 源码语法）

| AST 节点 | 生成规则 |
|----------|----------|
| `Text("hello")` | `"hello"` |
| `Bold(children)` | `"**" + generate(children) + "**"` |
| `Heading(2, children)` | `"## " + generate(children)` |
| `Highlight("blue", children)` | `"[[\\h:blue|" + generate(children) + "]]"` |
| `Highlight(null, children)` | `"[[\\h|" + generate(children) + "]]"` |
| `Paragraph(children)` | `generate(children)` |
| `BlankLine` | `""` (空字符串) |
| `CodeBlock("js", "code")` | `"```js\ncode\n```"` |
| `Image("alt", "url")` | `"![alt](url)"` |

### 验证方式 — Round-trip 测试

| # | 输入 | 验证 |
|---|------|------|
| 1 | `hello` | `generate(parse("hello")) === "hello"` |
| 2 | `**bold**` | `generate(parse("**bold**")) === "**bold**"` |
| 3 | `### Hi **there**` | `generate(parse("### Hi **there**")) === "### Hi **there**"` |
| 4 | `[[\h:blue\|高亮]]` | `generate(parse("[[\\h:blue|高亮]]")) === "[[\\h:blue|高亮]]"` |
| 5 | 全文 mixed | `generate(parse(fullDoc)) === fullDoc` |

---

## Phase 5: Position Mapper（位置映射器）

### 目标

在 AST 坐标、源码坐标、DOM 坐标之间做双向映射。这是整个编辑系统的核心引擎。

### 接口

```javascript
window.MemoriaMapper = {
  // ── DOM ↔ AST ──
  // DOM 光标位置 → AST 坐标
  domToAst(domNode, domOffset) → { blockIndex, nodePath, offset },

  // AST 坐标 → DOM Range
  astToDom(blockIndex, nodePath, offset) → Range,

  // ── 源码 ↔ AST ──
  // 源码行/列 → AST 坐标
  srcToAst(line, col) → { blockIndex, nodePath, offset },

  // AST 坐标 → 源码行/列
  astToSrc(blockIndex, nodePath, offset) → { line, col },

  // ── 底层工具 ──
  // 源码列 → 渲染偏移（给定 AST 节点）
  srcColToRendered(node, srcCol) → { renderedOffset, targetNode },

  // 渲染偏移 → 源码列（给定 AST 节点）
  renderedToSrcCol(node, renderedOffset) → { srcCol, targetNode },
};
```

### 设计要点

1. **基于 AST 语义**：不是字符串偏移计算，而是根据节点类型理解前缀/后缀
2. **Heading 前缀**：`Heading(level=2)` → 前缀 `"## "` 长 3 字符，不占用渲染文本
3. **Bold 标记**：`Bold` → 前缀 `**` 和后缀 `**` 各 2 字符，不占用渲染文本
4. **Highlight 标记**：`Highlight("blue")` → 前缀 `"[[\\h:blue|"` 和后缀 `"]]"` 不占用渲染文本
5. **递归处理**：`Bold(Highlight(Text("x")))` → 渲染文本是 `"x"`，源码是 `"**[[\\h:blue|x]]**"`, 总共 17 个字符

### 核心算法：`srcColToRendered`

```
输入: Bold(Text("Hello")), srcCol=4  (用户点击了源码第 4 列)

  Bold 节点:
    prefix = "**"  (2 字符)
    children = [Text("Hello")]
    suffix = "**"  (2 字符)

  srcCol=4: 在 Bold 内部 (2 <= 4 < 2+5)
    → 递归进入 Text("Hello"), srcCol=4-2=2
    → Text 无 prefix/suffix，直接返回 offset=2
    → 渲染偏移 = 2
```

### 验证方式

| # | AST 节点 | 输入 | 预期输出 |
|---|----------|------|----------|
| 1 | `Text("hello")` | `srcColToRendered(_, 2)` | `{ renderedOffset: 2, node: Text }` |
| 2 | `Bold(Text("hi"))` | `srcColToRendered(_, 3)` | `{ renderedOffset: 1, node: Text("hi") }` |
| 3 | `Bold(Text("hi"))` | `renderedToSrcCol(_, 1)` | `{ srcCol: 3, node: Text("hi") }` |
| 4 | `Heading(2, Text("Hi"))` | `srcColToRendered(_, 4)` | `{ renderedOffset: 1, node: Text("Hi") }` |
| 5 | `Highlight("blue", Text("x"))` | `srcColToRendered(_, 10)` | `{ renderedOffset: 0, node: Text("x") }` |
| 6 | `Bold(Highlight(null, Text("x")))` | `srcColToRendered(_, 5)` | `{ renderedOffset: 0, node: Text("x") }` (穿过 Bold 和 Highlight 两层) |

---

## Phase 6: Renderer（AST → DOM 渲染器）

### 目标

将 AST 渲染为 `contenteditable` DOM，每个文本节点标记其源位置。

### 渲染规则

| AST 节点 | DOM 输出 | 样式类 |
|----------|----------|--------|
| `Document` | `<div class="m0-preview-content">` | |
| `Heading(level)` | `<h{level} class="m0-src-block" data-m0-src-line="N">` | |
| `Paragraph` | `<p class="m0-src-block" data-m0-src-line="N">` | |
| `BlankLine` | `<div class="m0-src-block m0-blank-block" data-m0-src-line="N"><br></div>` | |
| `Bold` | `<strong>` | |
| `Italic` | `<em>` | |
| `Highlight(color)` | `<span class="m0-hl" style="background:...">` | |
| `Code` | `<code>` | |
| `WikiLink` | `<a class="m0-wikilink">` | |
| `MathInline` | `<span class="m0-math">` (MathJax 处理) | |
| `Image` | `<img>` | |
| ... | ... | |

### 产出文件

`m0/js/renderer.js`

```javascript
window.MemoriaRenderer = {
  render(doc) → HTMLElement,           // 全量渲染
  renderBlock(block) → HTMLElement,    // 单 block 渲染
  renderInline(node) → HTMLElement | Text,
  // 增量渲染：替换 doc 中指定范围的 block
  renderRange(doc, startBlock, endBlock, container) → void
};
```

### 验证方式

| # | 输入 AST | 渲染后 DOM 检查 |
|---|----------|----------------|
| 1 | `Document(Paragraph(Text("hi")))` | `<p class="m0-src-block">hi</p>` |
| 2 | `Document(Heading(2, Text("Hi")))` | `<h2 class="m0-src-block">Hi</h2>` |
| 3 | `Document(BlankLine)` | `<div class="m0-blank-block"><br></div>` |
| 4 | `Document(Paragraph(Bold(Text("b"))))` | `<p><strong>b</strong></p>` |
| 5 | `Document(Image("alt", "url"))` | `<p><img alt="alt" src="url"></p>` |
| 6 | 提取所有块的 textContent | 与 `MemoriaAST.getText(doc)` 对比一致 |

---

## Phase 7: Edit Handler（编辑处理器）

### 目标

将所有编辑操作统一为：DOM 事件 → AST 坐标 → 修改 AST → 增量生成源码 → 增量 re-parse → 增量渲染 → 恢复光标。

### 7.1 编辑流程（含增量策略）

```
用户编辑 (keydown / input / compositionend)
    │
    ▼
┌─────────────────────────────────────────────┐
│ 1. 获取当前光标位置                           │
│    DOM 事件 → Mapper.domToAst()              │
│    → { blockIndex, nodePath, offset }       │
│    → 存储为 state.cursorAST                  │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│ 2. 判断编辑类型                              │
│    isStructural = 是否改变块类型/结构？       │
│    affectedBlocks = 受影响的 block 范围       │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│ 3. 在 AST 上应用编辑                         │
│    editAST(doc, position, operation) → {     │
│      newDoc,                                │
│      affectedBlocks: [startIdx, endIdx],     │
│      newCursor: { blockIndex, nodePath, offset } │
│    }                                        │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│ 4. 增量生成源码                              │
│    SourceGen.generateRange(doc, start, end)  │
│    → 写回 sourceEditor 受影响行              │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│ 5. 增量 re-parse（仅当 isStructural）        │
│    Parser.parseRange(newSource, start, end)  │
│    → 替换 doc.blocks[start..end]            │
│    → 重新计算 newCursor（类型可能变化）       │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│ 6. 增量渲染 DOM                             │
│    Renderer.renderRange(doc, start, end)    │
│    → 替换预览区中对应 DOM 片段               │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│ 7. 恢复光标位置                              │
│    Mapper.astToDom(newCursor) → Range       │
│    → window.getSelection().addRange(range)  │
└─────────────────────────────────────────────┘
```

### 7.2 关键场景处理

#### 场景 A：输入 "## " 使段落变标题

```
初始: Paragraph(Text("Hello"))
用户在 "Hello" 前输入 "## ":
  1. AST 位置: blockIndex=0, nodePath=[0], offset=0
  2. isStructural = true (块首插入 "## " 可能改变类型)
  3. editAST: insertText("## ") → Text("## Hello")
  4. SourceGen: "## Hello"
  5. Re-parse: Heading(2, Text("Hello"))  ← 节点类型变了！
  6. Re-render: <h2>Hello</h2>
  7. 新光标: blockIndex=0, nodePath=[0], offset=0
     → astToDom: Heading(2) 的 Text 节点 offset=0 → 渲染偏移=0
     → 源码列 = 3 (## + 空格)
```

#### 场景 B：在标题中间按 Enter

```
初始: Heading(2, Text("Hello world"))
用户在 "Hello" 和 "world" 之间按 Enter:
  1. AST 位置: blockIndex=0, nodePath=[0], offset=5
  2. isStructural = true (标题不能跨行)
  3. editAST: Heading 拆为两个 Paragraph:
       Paragraph(Text("Hello"))
       Paragraph(Text("world"))
  4. SourceGen: "Hello\nworld"  (不再有 ## 前缀)
  5. Re-parse: 两个 Paragraph block
  6. Re-render: 两个 <p> block
  7. 新光标: blockIndex=1, nodePath=[0], offset=0 (第二个 Paragraph 开头)
```

#### 场景 C：在 "## 标题" 中删除 "##"

```
初始: Heading(2, Text("Title"))
光标在 Heading 的 Text 第一个字符（渲染 offset=0）:
  1. AST 位置: blockIndex=0, nodePath=[0], offset=0
  2. 特殊处理: 光标在 Heading 的 Text 开头时，Backspace 删除整个前缀
  3. editAST: Heading(2, Text("Title")) → Paragraph(Text("Title"))
  4. SourceGen: "Title"
  5. Re-parse: Paragraph(Text("Title"))
  6. Re-render: <p>Title</p>
```

#### 场景 D：方向键在混合格式中移动

```
初始: Paragraph(Bold(Text("b")), Text(" "), Italic(Text("i")))
渲染: <p><strong>b</strong> <em>i</em></p>
state.cursorAST: { blockIndex: 0, nodePath: [0, 0], offset: 0 }

用户按 ArrowRight:
  → offset+1=1, 仍在 Bold.Text("b") 内
  → srcCol = Mapper.astToSrc(...) → col=3
  → DOM Range = Mapper.astToDom(...) → <strong> 文本节点 offset=1
  → setSelection(range)

用户继续按 ArrowRight (离开 "b"):
  → offset=1 离开 Bold.Text → 进入父节点 Bold
  → cursorAST 变为 { blockIndex: 0, nodePath: [1], offset: 0 }  (Text(" "))
  → srcCol = 5, DOM Range 在 " " 文本节点 offset=0
```

### 7.3 编辑操作 → AST 修改表

| 用户操作 | AST 修改 | isStructural |
|----------|----------|:---:|
| 输入字符 `c` | 在当前 Inline Text 节点 offset 处插入 `c` | ❌ |
| Backspace (Text 中间) | 删除 Text 节点 offset-1 处字符 | ❌ |
| Backspace (Text 开头) | 合并到前一个 Inline 节点 | ❌ |
| Backspace (Heading 文本开头) | 删除 Heading 前缀，节点变 Paragraph | ✅ |
| Delete (Text 中间) | 删除 Text 节点 offset 处字符 | ❌ |
| Delete (Text 末尾) | 合并后一个 Inline 节点 | ❌ |
| Enter (段落中间) | 拆分 Block 为两个 Block | ✅ |
| Enter (空行) | 空行变为 Paragraph，光标在开头 | ✅ |
| Enter (标题中间) | 标题拆分为两个 Paragraph | ✅ |
| 输入 "## " (段落开头) | Paragraph → Heading | ✅ |
| 输入 "- " (段落开头) | Paragraph → ListItem | ✅ |
| ArrowLeft/Right | cursorAST.offset ± 1 | ❌ |
| ArrowUp/Down | cursorAST.blockIndex ± 1 | ❌ |

### 产出文件

修改 `m0/js/app.js`，重写 `bindPreviewSelectInteraction` 中的编辑处理逻辑。

### 验证方式

| # | 场景 | 操作 | 验证 |
|---|------|------|------|
| 1 | 段落输入 | 在 "Hello" 中输入 "X" | 源码 "HelloX"，AST 正确，渲染正确，光标在 "X" 后 |
| 2 | ## 变标题 | 在 "text" 前输入 "## " | 源码 "## text"，AST 变为 Heading(2)，渲染 `<h2>`，光标正确 |
| 3 | 标题删 ## | 在 "## Title" 的 "T" 前按 Backspace | 源码 "Title"，AST 变为 Paragraph，渲染 `<p>` |
| 4 | 标题中 Enter | 在 "## A B" 的 "A" 后按 Enter | 源码 "A\nB"，两个 Paragraph block |
| 5 | 粗体输入 | 在 "**ab**" 的 "a" 后输入 "c" | 源码 "**acb**"，AST Bold(Text("acb")) |
| 6 | 粗体 Backspace | 在 "**ab**" 的 "b" 后按 Backspace | 源码 "**a**"，AST Bold(Text("a")) |
| 7 | 方向键跨格式 | 在 Bold+Italic 中 ArrowRight | 逐字符移动，不跳飞 |
| 8 | IME 中文 | 输入 "测试" | 源码正确，AST 正确，渲染正确 |
| 9 | Round-trip | 任意编辑后 | `generate(parse(source)) === source` |
| 10 | verifySync | 任意编辑后 | 所有块匹配，无 MISMATCH |
| 11 | 性能 | 1000 行文档中打字 | 无感知延迟，只渲染 1 个 block |

---

## 3. 日志/验证系统

### 日志开关

```javascript
const MAP_LOG = true;
```

### 日志文件

```
{kb_path}/mapping-debug.log
```

### 日志事件类型

| 标签 | 触发时机 | 包含信息 |
|------|----------|----------|
| `CURSOR:domToAst` | DOM 光标 → AST 坐标 | domNode, domOffset → blockIndex, nodePath, offset |
| `CURSOR:astToDom` | AST 坐标 → DOM 光标 | blockIndex, nodePath, offset → domNode, domOffset |
| `CURSOR:astToSrc` | AST 坐标 → 源码坐标 | blockIndex, nodePath, offset → line, col |
| `AST:edit` | AST 被修改 | 操作类型、修改前后 AST 片段 |
| `AST:typeChange` | 节点类型变化 | 旧类型 → 新类型（如 Paragraph→Heading） |
| `AST:reparse` | 源码重新解析 | 解析耗时、节点数、受影响行范围 |
| `EDIT:sourceEdit` | 源码被修改 | line, col, op, text, oldLine |
| `VERIFY MISMATCH` | 同步校验失败 | 源块行号、源码内容 vs 预览块内容，差异类型 |
| `VERIFY OK` | 同步校验通过 | 行号、确认一致 |
| `VERIFY SUMMARY` | 校验结束 | 总块数、OK/MISMATCH/SKIP 统计 |

### 单元测试：每个 Phase 的自测代码

每个 Phase 2-6 的 JS 文件底部包含自测代码：

```javascript
// lexer.js 底部
if (typeof window !== "undefined") {
  (function test() {
    const assert = (cond, msg) => {
      if (!cond) console.error("FAIL:", msg);
      else console.log("PASS:", msg);
    };

    const tokens = MemoriaLexer.tokenize("**bold**");
    assert(tokens.length === 3, "bold token count");
    assert(tokens[0].type === "bold_open", "bold_open");
    assert(tokens[1].type === "text" && tokens[1].value === "bold", "bold text");
    assert(tokens[2].type === "bold_close", "bold_close");

    console.log("Lexer tests done");
  })();
}
```

### 关键诊断规则

| 现象 | 检查点 |
|------|--------|
| `domToAst` 返回 null | 点击的 DOM 节点不在 AST 对应的 block 内 |
| `astToDom` 返回 null | 渲染后 DOM 节点不匹配，可能是增量渲染 bug |
| `typeChange` 未触发 | 结构性编辑未被识别，isStructural 判断有误 |
| `MISMATCH diff` 持续增大 | 增量渲染未覆盖所有受影响的 block |
| 方向键瞬移到远端 | keydown 未走 `astToDom`，走了浏览器默认行为 |
| 编辑后预览内容不变 | EditHandler 未调用 `renderRange` |
| Round-trip 失败 | SourceGen 或 Parser 有 bug |

---

## 4. 与旧代码的关系

Phase 7 完成后，以下旧代码将被删除：

| 旧代码 | 位置 | 替代者 |
|--------|------|--------|
| `parseInlineTokens` | markdown-preview.js | `Parser.parseInline` |
| `splitSourceBlocks` | markdown-preview.js | `Parser.parseBlocks` |
| `annotateSegments` | markdown-preview.js | `Renderer.render` (直接基于 AST) |
| `renderedOffsetToSrcCol` | app.js | `Mapper.renderedToSrcCol` |
| `rangeToBlockCol` 中的 token 遍历 | app.js | `Mapper.srcColToRendered` |
| `getBlockPrefixLen` | app.js | `Mapper` (AST 节点自带语义) |
| `isAtBlockEnd/Start` | app.js | 已删除 |
| `_blockHasText` | app.js | 已删除 |

---

## 5. 还原方案

每个 Phase 独立，可独立回退：

1. 删除 `ast.js` / `lexer.js` / `parser.js` / `source-gen.js` / `mapper.js` / `renderer.js`
2. 恢复 `markdown-preview.js` 中的旧函数
3. 恢复 `app.js` 中的旧编辑逻辑
4. 恢复 HTML 中的 script 加载顺序