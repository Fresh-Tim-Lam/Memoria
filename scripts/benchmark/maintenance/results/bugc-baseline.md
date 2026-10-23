# Bug C 基线：列表空行被 parser 吞掉 + source-gen 回写丢空行

> 采集于 HEAD `03394059`，`parser.js` / `source-gen.js` **尚未修改**。
> 这是「改动前」的证据快照，任何修复都必须重新跑同一组用例并对比。

## 现象（用户报）

> 「- 块后的空行在预览区域没有渲染成空行」

## 实测 AST（`node` 直接加载 ast.js → lexer.js → parser.js）

| 源码 | blocks | itemSrcLine |
|---|---|---|
| `- 第一项\n- 第二项\n\n后面一段文字` | `list(1..3) paragraph(4..4)` | `[1,2]` |
| `- a\n- b` | `list(1..2)` | `[1,2]` |
| `- a\n\n- b\n- c` | `list(1..4)` | `[1,3,4]` |
| `- a\n\n\nafter` | `list(1..3) paragraph(4..4)` | `[1]` |
| `1. x\n\n2. y\ntail` | `list(1..3) paragraph(4..4)` | `[1,3]` |

**⇒ 列表**末尾**的空行被并入 `list.srcLineEnd`，AST 里没有对应 `blank_line` 块**（预览自然渲染不出空行）。
项**之间**的空行被正确吸收（CommonMark 松散列表语义，这是对的），但没被回写。

## 实测 source-gen 回写等价性（逐块 `generateBlock` 拼接）

| 源码 | 重生成 | 等价 |
|---|---|---|
| `- 第一项\n- 第二项\n\n后面一段文字` | `- 第一项\n- 第二项\n后面一段文字` | ❌ 丢空行 |
| `- a\n- b` | `- a\n- b` | ✅ |
| `- a\n\n- b\n- c` | `- a\n- b\n- c` | ❌ 丢项间空行 |
| `- a\n\n\nafter` | `- a\nafter` | ❌ 丢 2 个空行 |
| `1. x\n\n2. y\ntail` | `1. x\n2. y\ntail` | ❌ 丢空行 |

**⇒ 只要对含空行的松散列表做任何一次编辑，那些空行就会从源码里永久消失。**

## 根因（代码级）

1. **`parser.js:520-535`** 列表扫描循环把空行 `scan++` 跳过，结束后 `emit(blocks, listNode, lineNum, scan)`
   —— `scan` 已越过末尾空行 ⇒ 列表区间吞掉它们。`itemSrcLine` 已记录每项行号但**未用于收尾**。
2. **`source-gen.js:83-87`** `case T.LIST` 只按 `items` 逐项 `join("\n")`，
   **完全忽略 `itemSrcLine`**（而 parser 注释明确写着「可据相邻两项行号差 > 1 判定其间的空行数 ⇒ 逐字节重建可行」）。

## 修复必须同时改两处

- parser：列表**末尾**空行还给 `blank_line`（`emit` 用最后一个 item 的行号，`i` 从空行继续）
- source-gen：列表**项之间**空行按 `itemSrcLine` 差额补回

## ⚠️ 已知风险（修复前必须解决）

`itemSrcLine` 记录的是**编辑前的源码行号**。用户插入/删除列表项后它就会失效，
若 `source-gen` 盲目按它补空行 ⇒ **编辑后会凭空多出空行**。
⇒ 修复必须同时处理：编辑列表时同步更新 `itemSrcLine`，或在编辑后清空它（退回"无空行"行为）。

## 复跑方式

见同目录 `bugc-baseline.mjs`。