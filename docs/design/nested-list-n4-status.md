# N4 升降级：实现现状与阻塞（2026-10-23）

> 状态：**部分实现，真机验证暴露设计冲突**。关联 [nested-list-design.md](nested-list-design.md)

## 已实现

1. `MemoriaEditSync.indentListLevel(dir)`（`app.js`）：AST 层升降级 + 单撤销单元
2. Tab / Shift+Tab 按键接入（`edit-handler.js`）

## 真机验证结果（`run_nested_tab.py` / `nested_list_tab_probe.mjs`）

| 检查 | 结果 | 说明 |
|---|---|---|
| T0-setup | ✅ | `openFile` 打开 fixture，源码正确 |
| T0b-list-block-found | ✅ | 定位到列表块 |
| **T1 列表项内 Tab** | ❌ | **没有降级，反而插入 2 空格**（走了兜底路径） |
| T2 列表项内 Shift+Tab | ⚠️ | 断言虚过（body 未变时也满足"2 空格"期望）⇒ **实为未生效** |
| T3 普通段落内 Tab | ✅ | 正确插入 2 空格（`"  plain para"`） |

## 根因（诊断证据）

```
DIAG-t1: cursorAST = { bi: 6, np: [1, 0], off: 3 }
         ret = false          ← indentListLevel 返回 false
         body: "- 第  二项"    ← 兜底路径插了 2 空格
```

**两个叠加问题**：

### ① `nodePath` 语义冲突（核心阻塞）
现有 6 处代码一律按 **`nodePath[0]` = 顶层 item 下标、`nodePath.slice(1)` = inline 路径** 解释：
```
L10992/11143/11236/11686/11819/12142:  itemIdx = nodePath[0]
L11071: splitInlineAt(children, nodePath.slice(1), offset)
```
而 `indentListLevel` 里我写的「逐层下钻」把**所有前缀数字都当层级下标** ⇒
`np=[1,0]` 被解释成「顶层 items[1] → 它的 list → items[0]」，
但实际含义是「顶层 items[1] → 它的 inline 子节点 [0]」⇒ `return false`。

### ② `listItemIndex` 是**扁平 li 索引**
`getPreviewCursor()` 产出的 `listItemIndex` 对应 `blockEl.querySelectorAll("li")` 的下标（深度优先展开），
现有 `_blockLineMap` + `listItemIndex` 用它定位源码行。
嵌套后「扁平索引 → 树路径」需要新映射函数。

## 待定的设计方案（三个选项）

| 方案 | 做法 | 影响面 |
|---|---|---|
| **A** | `nodePath` 前缀改为「每层 item 下标」，同步改写现有 6 处消费代码 | **大**（6 处核心编辑路径），但语义统一 |
| **B** | `EH.cursorAST` 增加独立字段 `listPath: [0,1,0]`，`nodePath` 保持原义 | 中（只加字段 + 只在新代码用），**但需在 `syncFromSelection` 里填充** |
| **C** | 用**扁平 `listItemIndex`** 反查树路径（新函数 `flatLiToTreePath()`）| 小（不动 nodePath），但每次升降级都要遍历树 |

**推荐 C**：改动最小、不动既有 6 处代码、不动 `syncFromSelection`。
代价是每次操作遍历一次列表树（列表项通常 <100，可接受）。

## 下一步（不在本次提交范围）

1. 实现 `flatLiToTreePath(block, flatIdx) → { parentList, index, parentItem }`
2. `indentListLevel` 改用 `EH.listItemIndex`（而非 nodePath）定位项
3. 探针 T2 断言改为**强断言**（先记录 Tab 前后 body，再断言「确实变化且方向正确」）
4. 补 3 层嵌套的升降级用例

## 当前风险（已确认）

- **Tab 在列表项内会插入 2 空格**（兜底路径）—— 这是**错误行为**，用户按 Tab 会看到空格而不是降级
- `indentListLevel` 目前**所有情况下返回 false** ⇒ Tab 永远走兜底
- **建议**：要么按上面 C 方案修完，要么**先移除 Tab 接入**避免产生错误行为
