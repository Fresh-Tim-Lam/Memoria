# 不可编辑块的光标跳过机制

## 1. 问题描述

在预览区编辑模式下，方向键（↑↓←→）移动光标时，光标会**进入**不可直接编辑的块（代码块、Mermaid 图表、数学公式块、表格等），导致：
- 光标卡在 SVG 图表内部无法离开
- 需要多次按键才能跳过
- `domToAst` 返回 null，光标同步失败

**期望行为**：光标将不可编辑块视为一个"原子"，一次按键直接跳过：
```
...nnss | B s nsn  →  ArrowRight  →  ...nnssB | s nsn
                     ArrowDown                   ArrowDown
```

## 2. 不可编辑块类型

| AST 类型 | 渲染元素 | 不可编辑原因 |
|----------|----------|-------------|
| `code_block` | `<pre contentEditable="false">` | 浏览器原生禁止 |
| `code_block` (lang=mermaid) | `<pre>` + Mermaid SVG | Mermaid 替换为 SVG |
| `math_block` | `<div>` + MathJax `mjx-container` | MathJax 替换内容 |
| `table` | `<table contentEditable="false">` | 表格结构复杂 |
| `frontmatter` | `<pre contentEditable="false">` | YAML 元数据 |

## 3. 三层防护架构

### 层1: 容器级 `contentEditable="false"`

**文件**: [app.js](file:///d:/AAA_Jupyter/Memoria/src/memoria/ui/static/m0/js/app.js) `renderPreview` 步骤7

在 Mermaid/MathJax 渲染**之后**，遍历所有 `.m0-src-block`，对不可编辑类型的 block 设置 `contentEditable="false"`：

```javascript
var _nonEditableTypes = { code_block: 1, math_block: 1, mermaid: 1, table: 1, frontmatter: 1 };
preview.querySelectorAll('.m0-src-block').forEach(function (blkEl) {
    var bi = parseInt(blkEl.getAttribute("data-m0-block-index"), 10);
    if (!isNaN(bi) && _doc.blocks[bi] && _nonEditableTypes[_doc.blocks[bi].type]) {
        blkEl.contentEditable = "false";
        blkEl.querySelectorAll('pre, code, table, svg, mjx-container').forEach(function (el) {
            el.contentEditable = "false";
        });
    }
});
```

**卡点**: Mermaid 渲染（步骤5）在 `contentEditable` 设置（步骤4）**之后**执行，Mermaid 创建的新 SVG 没有 `contentEditable="false"`。步骤7 在 Mermaid 渲染后重新设置解决了此问题。

### 层2: keydown 事件 — AST-first 边界检查

**文件**: [edit-handler.js](file:///d:/AAA_Jupyter/Memoria/src/memoria/ui/static/m0/js/edit-handler.js) `bindPreviewClick` 中的 keydown 处理器

在浏览器移动光标**之前**，先查询当前 AST 位置：

```
keydown 事件
    ↓
获取当前 blockIndex (getBlockIndexFromSelection)
    ↓
┌─ Case A: 当前 block 不可编辑 → preventDefault + 跳到下一个可编辑 block
├─ Case B: 在 block 边界 + 下一 block 不可编辑 → preventDefault + 跳过
└─ Case C: 正常移动 → 让浏览器处理，setTimeout(0) 后检查
```

#### Case A: 当前 block 不可编辑
```
if (isNonEditableBlock(curBlkIdx)) {
    e.preventDefault();  // 阻止浏览器移动
    skipIdx = findEditableBlockIndex(curBlkIdx, dir);
    placeCursorInBlock(skipIdx, dir < 0);
}
```

#### Case B: 在边界 + 下一 block 不可编辑
```
if (isAtBlockEdge(dir)) {
    nextBlk = curBlkIdx + dir;
    if (isNonEditableBlock(nextBlk)) {
        e.preventDefault();  // 阻止浏览器移入
        skipIdx = findEditableBlockIndex(nextBlk, dir);
        placeCursorInBlock(skipIdx, dir < 0);
    }
}
```

#### Case C: 正常移动后检查
```
setTimeout(0);
newBlk = getBlockIndexFromSelection();
if (isNonEditableBlock(newBlk)) → 跳过
else if (newBlk < 0) → 用 currentCursor.blockIndex 回退 + 跳过
```

### 层3: `placeCursorInBlock` 空行处理

**卡点**: 空行 block（`blank_line`）没有文本节点，`TreeWalker.nextNode()` 返回 null，`placeCursorInBlock` 返回 false，光标无法定位。

**修复**: 当没有文本节点时，直接在 block 元素上放置光标：
```javascript
if (!first) {
    var r0 = document.createRange();
    r0.setStart(el, 0);
    r0.collapse(true);
    sel.removeAllRanges();
    sel.addRange(r0);
    return true;
}
```

## 4. 辅助函数

### `isNonEditableBlock(blockIndex)`
查询 AST `_doc.blocks[blockIndex].type`，检查是否在不可编辑类型集合中。

### `findEditableBlockIndex(fromIndex, direction)`
从 `fromIndex + direction` 开始遍历，跳过所有不可编辑 block，返回第一个可编辑 block 的索引。

### `getBlockIndexFromSelection()`
从浏览器 `Selection.anchorNode` 向上查找 `.m0-src-block` 祖先，读取 `data-m0-block-index`。

### `isAtBlockEdge(direction)`
用 TreeWalker 查找 block 内首/末文本节点（跳过 `contentEditable="false"` 子元素），检查光标是否在该节点开头/末尾。

### `placeCursorInBlock(blockIndex, atEnd)`
用 TreeWalker 找首/末文本节点，设置 Range。空行 block 直接在元素上放置光标。

## 5. 当前 Bug 分析

### Bug: 光标仍然进入代码块

**日志证据** (`docs/output.md`):
```
[EH] click: L25 C0 (block 24)       ← 用户点击空行 block 24
[EH] domToAst: not in any valid block  ← ArrowDown 后光标不在任何 block
[EH] arrow:ArrowDown: not on a valid block  ← 重复 7 次
[EH] arrow:ArrowDown: L34 C0 (block 26)  ← 最终到达 block 26
```

**根因分析**:
1. Block 24 是空行，`isAtBlockEdge(1)` 返回 false（没有文本节点）
2. Case B 不触发
3. Case C: 浏览器把光标移入代码块
4. `getBlockIndexFromSelection()` 返回 -1（光标在 `contentEditable="false"` 元素内）
5. 回退到 `currentCursor.blockIndex = 24`
6. `nb = 25`, `isNonEditableBlock(25)` = true
7. `findEditableBlockIndex(25, 1)` = 26
8. `placeCursorInBlock(26, false)` → **失败**（block 26 也是空行，没有文本节点）
9. 光标留在代码块内
10. 下一次 ArrowDown: `currentCursor` 未更新（syncFromSelection 失败），重复以上

**修复**: `placeCursorInBlock` 空行处理（层3）+ 文件日志验证

## 6. 文件日志系统

### 后端 API
**文件**: [m0.py](file:///d:/AAA_Jupyter/Memoria/src/memoria/presentation/api/m0.py) `write_debug_log`

```python
def write_debug_log(self, filename: str, body: str) -> dict:
    logs_dir = os.path.join(..., "logs")  # d:\AAA_Jupyter\Memoria\logs
    with open(full, "a", encoding="utf-8") as f:
        f.write(body)
```

### 前端 `flog()` 函数
**文件**: [edit-handler.js](file:///d:/AAA_Jupyter/Memoria/src/memoria/ui/static/m0/js/edit-handler.js)

```javascript
function flog(tag, msg) {
    _flogBuf.push(_fts() + " #" + _flogSeq + " [" + tag + "] " + msg);
    setTimeout(_flogFlush, 200);  // 200ms 批量刷新
}
function _flogFlush() {
    api.write_debug_log("block-skip-debug.log", content);
}
```

### 日志标签

| 标签 | 含义 |
|------|------|
| `═══` | 分隔线 |
| `KEY` | keydown 事件入口 |
| `GBI` | getBlockIndexFromSelection |
| `NED` | isNonEditableBlock |
| `FEI` | findEditableBlockIndex |
| `EDGE` | isAtBlockEdge |
| `PCB` | placeCursorInBlock |
| `CASA` | Case A 处理 |
| `CASB` | Case B 处理 |
| `CASC` | Case C 处理 |

### 日志文件位置
`d:\AAA_Jupyter\Memoria\logs\block-skip-debug.log`

## 7. 已完成 vs 待验证

### 已完成
- [x] 三层防护架构设计
- [x] Case A/B/C 逻辑实现
- [x] `contentEditable="false"` 在 Mermaid 渲染后重新设置
- [x] `placeCursorInBlock` 空行 block 处理
- [x] 文件日志系统（后端 API + 前端 flog）
- [x] 全管线日志埋点（KEY → GBI → NED → FEI → EDGE → PCB → CASA/B/C）

### 待验证
- [ ] 空行 block 的 `placeCursorInBlock` 修复是否生效
- [ ] Case C 回退逻辑是否正确跳过代码块
- [ ] `isAtBlockEdge` 对空行 block 返回 false 是否导致 Case B 漏触发
- [ ] ArrowUp 从代码块下方回退是否对称工作

## 8. 相关文件索引

| 文件 | 作用 |
|------|------|
| [edit-handler.js](file:///d:/AAA_Jupyter/Memoria/src/memoria/ui/static/m0/js/edit-handler.js) | 方向键处理、块跳过逻辑、文件日志 |
| [app.js](file:///d:/AAA_Jupyter/Memoria/src/memoria/ui/static/m0/js/app.js) | `renderPreview` 步骤7、`contentEditable` 设置 |
| [mapper.js](file:///d:/AAA_Jupyter/Memoria/src/memoria/ui/static/m0/js/mapper.js) | `domToAst`、`astToSrc` 坐标映射 |
| [m0.py](file:///d:/AAA_Jupyter/Memoria/src/memoria/presentation/api/m0.py) | `write_debug_log` 后端 API |
| [m0.css](file:///d:/AAA_Jupyter/Memoria/src/memoria/ui/static/m0/css/m0.css) | `.m0-block-editing` 样式 |
