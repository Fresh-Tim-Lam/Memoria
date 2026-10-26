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
| `[[id\|text]]` | 带显示文本的链接 | `[[mdp\|马尔可夫决策过程]]` |

> **⚠️ 边类型不写在正文里（2026-10-26 订正）**
>
> 曾经的 `[[id#type]]` / `[[id#type|text]]`（如 `[[mdp#prerequisite]]`）是**遗留写法，已废弃，不要用**：
> 构建时 `strip_known_wikilink_edge_hints()` 会把这个片段**从正文剥离并回写文件** ⇒ **静默修改用户正文**：
> 实测 `[[d#extend]]` 会被剥成 `[[d]]`（遗留写法，勿用）。副作用还不止改正文：预览期该链会断开；链接不在任何 KP range 内时，
> 类型根本进不了 sidecar ⇒ **正文被改而类型也丢了**。
>
> **正确写法**：边类型只写 **sidecar**（`<文件>.memoria.yaml`）的 `links[].edge_type` / `edges[].type`，
> 正文保持纯 `[[id]]` / `[[id|text]]`。权威依据见 `src/memoria/graph/edge_types.py:3-5`
> （"sidecar `links[].edge_type` / `edges[].type`：唯一权威来源；正文 `[[target]]` 不含 `#类型`"）。
>
> - 可用类型：`reference`（引用/相关）、`extend`（扩展/下游）、`contain`（父子，**由标题层级自动派生，禁止手标**）。
> - 遗留片段映射（仅供迁移读入 sidecar，**不是推荐写法**）：`#prerequisite` / `#analogy` / `#ref` → `reference`；
>   `#extend` → `extend`；`#contain` → `contain`（`WIKILINK_HINT_ALIASES`，`edge_types.py:41-48`）。
> - `#heading-anchor` 这类**非类型**片段不属于本规则（原样保留，见 `is_wikilink_edge_type_fragment()`）。

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

## 图片节点属性规范（阶段 E，2026-08-28 生效）

图片使用标准 Markdown 图片语法，title 位扩展为**属性参数列表**：

```
![alt](url "key1=value1,key2=value2")
```

### 支持的属性 key（白名单）

| key | 取值 | 渲染效果 |
|-----|------|---------|
| `width` | 数字（→px）或带单位（`300px` / `50%`） | `<img>` 内联 `width`，与 `max-width:35%` 约束共存 |
| `height` | 同上 | `<img>` 内联 `height`（覆盖默认 `height:auto`） |
| `align` | `left` / `center` / `right` | 图片块容器对齐 class（`.m0-image-align-*`，`text-align` 实现） |

### 语法示例

| 需求 | 写法 |
|------|------|
| 300px 居中 | `![图](.memoria/images/x.png "width=300,align=center")` |
| 50% 宽左对齐 | `![图](.memoria/images/x.png "width=50%,align=left")` |
| 纯标题（非属性） | `![图](.memoria/images/x.png "测试标题")` —— 整体按普通 title 处理 |

### 解析与容错规则

- title 按逗号拆段，**每段必须匹配 `key=value`**（key 为字母/数字/下划线/连字符）才按属性解析；任一段不匹配 → 整个 title 按普通图片标题处理（`<img title>` 工具提示）。
- 未知 key（如 `foo=1`）→ 忽略并在渲染时 `console.warn("[img-attrs] ...")`，不破坏渲染。
- 非法尺寸值（如 `width=abc`）→ 忽略，图片保持默认尺寸。
- 属性存于 AST 节点 `attrs` 字段（`parseImageAttrs`，ast.js），源码回写时保留原始 title 字符串，编辑往返不丢。
- 与 `[[]]` 体系关系：图片语法独立于 `[[]]`，不受荧光笔/链接分类规则影响；图片属性解析不触碰 `[[]]` 解析器。
