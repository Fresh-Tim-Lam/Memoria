# Memoria 统一 `[[]]` 语法体系

## 设计原则

1. **统一括号**：所有 Memoria 扩展语法都使用 `[[...]]` 双方括号
2. **`\` 前缀区分**：`\` 前缀表示系统格式命令，无 `\` 前缀为知识点链接
3. **不嵌套**：`[[\...]]` 内部不嵌套 `[[\...]]`，粗体/斜体等用 Markdown 语法
4. **栈式解析**：解析器跟踪 `[[`/`]]` 深度，正确处理内部链接

## 语法总览

### 链接（无 `\` 前缀）

| 语法 | 含义 | 示例 |
|------|------|------|
| `[[id]]` | 知识点链接 | `[[mdp]]` |
| `[[id#type]]` | 带边类型的链接 | `[[mdp#prerequisite]]` |
| `[[id\|text]]` | 带显示文本的链接 | `[[mdp\|马尔可夫决策过程]]` |
| `[[id#type\|text]]` | 完整形式 | `[[mdp#prerequisite\|前置知识]]` |

### 荧光笔 `\h`

| 语法 | 含义 | 渲染 |
|------|------|------|
| `[[\h\|text]]` | 默认黄色高亮 | `<mark>text</mark>` |
| `[[\h:color\|text]]` | 指定背景色 | `<mark class="hl-color">text</mark>` |
| `[[\h:bg:fg\|text]]` | 背景+前景色 | `<mark class="hl-bg" style="color:fg">text</mark>` |
| `[[\h:id\|text]]` | 命名高亮 | `<mark data-hl-id="id">text</mark>` |
| `[[\h:id:color\|text]]` | 命名+背景色 | `<mark class="hl-color" data-hl-id="id">text</mark>` |
| `[[\h:id:bg:fg\|text]]` | 命名+背景+前景 | `<mark class="hl-bg" style="color:fg" data-hl-id="id">text</mark>` |

**已知背景色**：`yellow`(默认)、`green`、`red`、`blue`、`orange`

**已知前景色**：`red`、`green`、`blue`、`orange`、`yellow`、`purple`、`gray`

也支持 CSS 色值（如 `#e91e63`），此时使用 inline style 而非 CSS 类。

### 字体颜色 `\c`

| 语法 | 含义 | 渲染 |
|------|------|------|
| `[[\c:color\|text]]` | 字体颜色 | `<span class="m0-fc-color">text</span>` |

### 粗体 `\b`

| 语法 | 含义 | 渲染 |
|------|------|------|
| `[[\b\|text]]` | 粗体 | `<strong class="m0-fmt-b">text</strong>` |

### 斜体 `\i`

| 语法 | 含义 | 渲染 |
|------|------|------|
| `[[\i\|text]]` | 斜体 | `<em class="m0-fmt-i">text</em>` |

## 混合格式

`[[\...]]` 不嵌套，内部用 Markdown 语法实现粗体/斜体：

| 需求 | 写法 |
|------|------|
| 黄底粗体 | `[[\h\|**重点**]]` |
| 绿底斜体 | `[[\h:green\|*强调*]]` |
| 黄底红字 | `[[\h:yellow:red\|内容]]` |
| 黄底红字粗斜体 | `[[\h:yellow:red\|***内容***]]` |
| 纯红字粗体 | `[[\c:red\|**内容**]]` |
| 纯粗体（无需语法） | `**内容**` |
| 荧光笔内嵌链接 | `[[\h:green\|参见 [[mdp]]]]` |

## 嵌套链接处理

`[[\h:green|参见 [[mdp]]]]` 中，内部 `[[mdp]]` 的 `]]` 不应提前闭合外层荧光笔。

解析器采用**栈式深度计数**：扫描时遇到 `[[` 深度+1，遇到 `]]` 深度-1，深度归零时才闭合外层命令。

## Sidecar 存储

荧光笔高亮记录存储在 sidecar `highlights[]` 中，结构与 `links[]` 同构：

```yaml
highlights:
  - id: hl-exam
    color: yellow
    anchor_text: "考试必考知识点"
    instances:
      - line: 15
    note: "2024年真题"
```

## 参数分类规则（`\h` 后的 token）

| token 数 | 分类逻辑 |
|----------|----------|
| 0 | 默认黄底 |
| 1 | 已知色→背景色；否则→id |
| 2 | 两个已知色→bg:fg；id+已知色→id:bg；已知色+未知→bg:fg；id+未知→id:fg |
| 3 | id:bg:fg |
