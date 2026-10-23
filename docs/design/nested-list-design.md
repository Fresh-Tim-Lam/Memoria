# 多级列表（嵌套列表）设计 — 0.4.7 任务 4

> 状态：**设计中**（2026-10-23）。实现前先定稿，避免边写边改。
> 关联：[longterm-plan-2026-10.md](longterm-plan-2026-10.md)、[AGENT.md](../../AGENT.md)

## 1. 需求（用户原话）

> 「我忘记了 `-` 还有多级的，memoria 现在没有做多级就是比如 `- ...` / `\t- ...` / `  - ...`，
>  空格数量不要紧好像，关键是对齐」

⇒ 判定层级的依据是**对齐（缩进深度）**，不是精确空格数。Tab 与空格都接受。

## 2. 现状（已实测）

| 输入 | 解析结果 | 回写 |
|---|---|---|
| `- a\n  - b\n  - c\n- d` | `list(1..1) para(2..2) para(3..3) list(4..4)` | 现已等价 ✅（`e374463f` 修复前是 `-b`） |
| `- a\n\t- b\n\t- c\n- d` | 同上，全降级段落 | 同上 |
| `- a\n    - b\n        - c` | 同上 | 同上 |

- **不认识缩进列表**（缩进行首个 token 是缩进 `text`，不走列表分支）
- **数据损坏已修复**（`e374463f`：marker 后的分隔空格现在保真）
- 渲染层、编辑层**完全没有层级概念**

## 3. 存储模型（已定：嵌套）

用户选择**嵌套存储**（语义最正确）：

```js
// AST.list
{
  type: "list",
  ordered: false,
  start: null,          // 有序列表起始编号（既有字段）
  items: [              // 顶层项
    {
      type: "list_item",
      children: [ /* inline */ ],     // 本项自己的行内内容
      // ★ 新增：本项的子列表（可空）
      list: { type: "list", ordered, start, items: [...] } | null,
      // ★ 新增：本项源码行号（1-based），供逐字节重建
      srcLine: 1,
      // ★ 新增：本项缩进原文（Tab 或 N 空格），供逐字节重建
      indent: "",
    },
    ...
  ],
}
```

### 为什么把 `list` 放 item 上而不是 `children` 数组里

`children` 现在装的是**行内节点**（text / code / math / link …）。若把 `list` 塞进
`children`，所有遍历 `children` 的代码（渲染、`firstTextPath`、`renderedLenOfNodes` …）
都可能把它当行内节点处理 ⇒ 大面积隐患。
⇒ **单独一个 `list` 字段**，遍历逻辑可显式判 `if (item.list)`。

## 4. 层级判定规则

```
每项计算「缩进宽度」：
  Tab  = 4（视觉对齐；不参与"最多 4 空格"的 CommonMark 规则）
  空格 = 1
  混合  = Tab 计 4 + 空格计数
层级 = 该宽度在**同块内所有项宽度集合**中的升序名次（0,1,2,…）
```
- **不要求**固定步长（2 空格 / 4 空格都行）—— 用户说"空格数量不要紧，关键是对齐"
- 但要求**同一父级下所有兄弟项宽度一致**；若某行宽度既不等于父级也不等于任一已有兄弟级，
  取"最接近的较小层级"（宽松解析，不报错）
- **Tab 与空格视为等价**（同一宽度视为同层）

## 5. 解析算法（parser）

```
扫描连续列表行（含松散列表的空行跳过），对每行：
  1. 取缩进宽度 w 与 marker（- / * / + / N.）
  2. 维护一个「缩进宽度栈」stack = [w0, w1, ...]
     · 若 w > stack.top：push(w) ⇒ 该项是**上一项的**子列表第一项
     · 若 w == stack.top：同级兄弟
     · 若 w < stack.top：弹栈直到 top ≤ w
       · 若结果 top == w：同级
       · 若 top < w < 旧 top：取最近较小层（宽松）
  3. 用栈深（push 后的长度-1）作为 level
  4. 建树：level 0 的项进顶层 items；level N 的项进「最近一个 level N-1 项的 list」
```

**有序/无序混排**：子列表可以是不同 `ordered`（`- a` 下面挂 `1. b` 合法）。
⇒ 每个层级各自维护一个 list 节点（若同层 marker 类型变化，按现有规则**开新列表**）。

## 6. 回写（source-gen）

递归生成：每个 item 一行 `indent + marker + " " + inline`，然后若有 `item.list`，
**紧接着**递归生成子列表（子列表的 `indent` = 本项 `indent` + 子列表基准缩进）。

**逐字节保真要点**：
- `item.indent` 保存**原文**（Tab 保持 Tab，N 空格保持 N 空格）⇒ 不统一成 2 空格
- `itemSrcLine` 保留（用于松散列表项间空行重建，见 Bug C）
- 子列表内部的项间空行同样按 `itemSrcLine` 差重建

## 7. 渲染（render-core.js）

```html
<ul class="-list">
  <li class="-list-item">
    <span>a</span>
    <ul class="-list -list--nested" data--level="1">
      <li>b</li>
    </ul>
  </li>
</ul>
```
- CSS：`. -list--nested { margin-left: 1.5em; }`（对齐缩进，不引入额外列表符号）
- **可选中/可编辑**：每层 `<li>` 都要有 `data--src-line`，
  且 `_blockLineMap` 的映射需要能定位到"子项的行"

## 8. 编辑行为（本次范围）

| 操作 | 行为 |
|---|---|
| Enter 在末项 | 新增同级项 |
| Enter 在**空**子项 | **退一级**（变成父级同级项）—— 与主流编辑器一致 |
| Tab / Shift+Tab | 降级 / 升级（缩进 +1 层 / −1 层） |
| Backspace 在行首 | 先退级；已在顶层则退列表（现有行为） |

⚠️ **Tab/Shift+Tab 可能与"插入缩进字符"的既有行为冲突**，需先确认 `keys` 层如何分发。

## 9. 影响面（必须逐个检查）

| 文件 | 改动 | 风险 |
|---|---|---|
| `lexer.js` | 无（缩进已作为 text 产出） | 低 |
| `parser.js` | 列表分支重写（栈式建树） | **高** |
| `ast.js` | `listItem` 增加 `list` / `srcLine` / `indent` | 中 |
| `source-gen.js` | 递归生成 + 逐字节保真 | **高** |
| `render-core.js` | 嵌套 `<ul>` 渲染 | 中 |
| `app.css` | `. -list--nested` 缩进样式 | 低 |
| `app.js` | `deleteSelectionMulti` / `backspaceAtBlockStart` / `splitParagraph` 的列表分支要能处理层级 | **高** |
| `markdown-preview.js` | 可能有独立渲染路径（需核查） | 中 |

## 10. 验收标准（硬性）

1. **逐字节回写保真**：新增探针 `nested_list_roundtrip_test.mjs`，
   覆盖 ≥12 组（2/4 空格、Tab、混合、有序/无序嵌套、松散列表带空行、3 层深）
2. **现有门禁全绿**：惰性 6/6、12 剧本 12/12、blockquote 80、trailing 62、
   edit_cut 28、edit_drag 38、scheduler_vm、纪律守卫、bugc-baseline 6/6
3. **真机验证**：打开含多级列表的文档，预览区显示嵌套缩进；Tab/Shift+Tab 生效
4. **无数据损坏**：任何编辑操作后，源码多级结构完整

## 11. 分阶段（每阶段独立提交）

| 阶段 | 内容 | 状态 | 提交 |
|---|---|---|---|
| **前置** | lexer 空格保真（数据损坏）| ✅ | `e374463f` |
| **N1** | `ast.js` + `parser.js` 栈式建树 | ✅ | `c09b4a09` |
| **N2** | `source-gen.js` 递归回写 | ✅ | `c09b4a09` |
| **N3** | `render-core.js` 嵌套渲染 + CSS | ✅ | `2eef3e34` |
| **N5** | 编辑入口清 `srcLine`（契约落地）| ✅ | `bd215680` |
| **修补** | 嵌套 `<ul>` 不再带 `-src-block` | ✅ | `9bdb1211` |
| **N4** | `mapper` 嵌套支持 + Tab/Shift+Tab | ✅ | `17c20c62` |

## 12. 实现结果（2026-10-23 完成）

### 最终数据结构
```js
item = {
  type: "list_item",
  children: Inline[],      // 本项自己的行内内容
  list: { ... } | null,    // ★ 子列表（嵌套），放 item 上而非 children 里
  srcLine: number,         // 源码行号（解析产物；编辑后必须清空）
  indent: string,          // 缩进原文（Tab 保持 Tab）
}
```

### 层级判定（实际实现，与设计稿的差异）
设计稿原写「Tab 与空格视为同层」，实现时发现**无法可靠换算**（2/4/8 空格都常见）：
⇒ 改为**按缩进宽度排序**：Tab=4、空格=1，同块内升序名次即层级。
用户统一用 Tab 或统一用 2/4 空格都能正确嵌套；只有「Tab 与 2 空格混用」时按 4>2 排序。

### `srcLine` 生命周期契约（重要）
| 阶段 | 可信性 | 处理 |
|---|---|---|
| 解析后未编辑 | ✅ 准确 | 用于补项间空行（松散列表逐字节重建）|
| 一经编辑 | ❌ 失真 | **必须**调 `_invalidateListItemLines(block)` 递归清空 |
| 不清空的后果 | — | 凭空多补空行（实测删一个子项多 1 空行）|

`source-gen` 侧另有兜底：整棵树 `srcLine` 非严格单调 ⇒ 判定已编辑 ⇒ 不用它补空行。

### Tab 语义（用户 2026-10-23 确认）
| 位置 | Tab | Shift+Tab |
|---|---|---|
| 列表项内 | **降级**（AST 结构移动）| **升级** |
| 普通段落内 | 插入 **4 空格** | 不拦（交浏览器）|

### 真机验证
`run_nested_tab.py` + `nested_list_tab_probe.mjs`（harness + Edge + 真实鼠标点击）
```
T0-setup ✅ · T0b-list-block-found ✅ · DIAG-hit ✅
T0c-click-lands-on-target ✅（listItemIndex=2）
T1 降级 ✅ · T2 升级 ✅ · T3 段落 4 空格 ✅
⇒ PASS 7/7
```

## 13. 仍未做（明确记录，不粉饰）

| 项 | 说明 |
|---|---|
| **Enter 在空子项上退一级** | 主流编辑器行为；尚未实现（现有 Enter 只会新增同级项）|
| **Backspace 在子项行首先退级** | 现有 `backspaceAtBlockStart` 仍按扁平项处理 |
| **3 层嵌套的升降级** | 探针只覆盖 2 层 |
| **无序列表内嵌有序子列表的升降级** | 未验证 |
| **`listPath` 跨块选区** | 未验证 |
| **惰性渲染路径下的 `-src-block` 计数** | 只在非惰性路径验证 |

