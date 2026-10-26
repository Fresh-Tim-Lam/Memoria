# task-156 · 引用块内列表二期 —— **开工前清单**（app.js blockquote 假设 28 处 + 4 个 `A.list` 重建点）

> 状态：**只读盘点完成，等 Lead 确认后再改代码**（本轮未动 app.js）。
> 基线：HEAD=`d655277e`；`app.js` / `edit-handler.js` 工作区无他人未提交改动（`git status` 已核）。
> 依据：task-155 一期已落地的**新 AST 形状** + 对 app.js 28 个 `blockquote` 命中行逐处读码 + EditSync 全函数链路。

---

## 0. 一页结论

```
静默坏（先修，会产生数据错误/丢内容）：6 处
必须改（新形状下功能不可用/路径错）：     9 处
恰好兼容（无需改）：                     13 处（含 3 行仅注释）
另外「未出现在 28 处里、但必须补分支」： 5 个函数
+ 4 个 A.list 重建点：其中 1 处会让有序列表重新编号（task-157 残余），
  另发现 2 处同类（deleteSelectionMulti / _blockLike）→ 合计 3 处需保号
```

**关键风险一句话**：一期把 `blockquote.children` 从"全是 paragraph、1 child = 1 行"改成
"可为**跨多行**的 list、且 `nodePath` 从 `[child, inline…]` 变为
`[child]` / `[child, itemIdx, inline…]`"。app.js 里所有"按 `nodePath[0]` + 1 child = 1 行 + child 一定是段落"
写死的路径都会**错位或覆盖**——其中 6 处是静默数据错误，必须先修。

---

## 1. 新 AST 形状（一期后，写代码前必须记住）

```
blockquote
  ├─ children[0] = paragraph           ← 普通引用行（1 行）
  ├─ children[1] = list                ← `> - a\n> - b`（**一个 child 占 2 行**）
  │     └─ items[i] = listItem         ← item.srcLine 是"引用切片内相对 1-based"
  └─ children[2] = paragraph
  · block.prefixes[]      每行一个原始前缀（`>` / `> ` / `>> `）
  · 每个 child 有 srcLine / srcLineEnd（**绝对 1-based 闭区间**，一期新增的单一事实源）
  · nodePath 语义：
      children 为 paragraph → [childIdx, …inline]
      children 为 list      → [childIdx, itemIdx, …inline]
```
⚠️ **行号换算公式（二期唯一正确口径）**：
```
child 首行(0-based) = _blockLineMap[blockIndex].startLine + (child.srcLine - block.srcLine)
child 末行(0-based) = _blockLineMap[blockIndex].startLine + (child.srcLineEnd - block.srcLine)
```
禁止再用 `blm.startLine + nodePath[0]`（那只在 1 child = 1 行时成立）。

---

## 2. 28 处 `blockquote` 命中逐条判定

（`fn@L` = 所在函数；"静默坏"= 新形状下会写坏 AST/源码且用户无感知）

| # | 行 | 所在函数 | 现状假设 | 新形状下后果 | 判定 |
|---|---|---|---|---|---|
| 1 | 12125 | `detectStructuralMarker` | `> ` 只在**行首**识别 | 函数本身不处理引用内层；二期要在"剥前缀后的内层行"上复用 | **兼容**（改造点在调用侧） |
| 2 | 12145-46 | `blockContentStart` | 注释：光标必须落到"第一段内部" | 注释仍对，但"第一段"可能不是段落 | 注释需更新 |
| 3 | 12147 | `blockContentStart` | `children[0]` 当段落 → `firstTextPath(qPara.children)` | child 是 list 时 `list.children` 不存在 ⇒ 返回 `nodePath=[0]` 指向 **list 块本身** ⇒ 后续 insertText 会把 list **覆盖成段落**（丢内容） | **静默坏·必改** |
| 4 | 12225-26 | `insertText` | 注释：text 直接挂 blockquote.children 是坏 AST | 说明仍对，但只防了"挂到 children 上"，没防"挂到 list 块上" | 注释需更新 |
| 5 | 12233 | `insertText` | `qPara = children[quoteIdx]` 必须是 paragraph；否则**新建空段落覆盖 `children[quoteIdx]`** | 引用内列表里打字 ⇒ **整个列表被替换成一段文本**（数据丢失），且随后 commit 写盘 | **静默坏·必改（最高优先）** |
| 6 | 12237 | `insertText` | 空引用块补空段落 | 空引用无 list，行为不变 | **兼容** |
| 7 | 12263 | `insertText` | else-if 引用分支：只写 `inlineHost.children=[node]` | 对 child=list 不会走到这里（cursor 已被 12233 抢走）；修好 12233 后这里要对 list item 生效 | **必改（与 5 同批）** |
| 8 | 13088 | `_extractSelectionMiddle` | `isQuote` 时用 `children[quoteIdx].children` 作 inline 根 | child 是 list 时无 `children` ⇒ 返回 null（样式/删除退到 multi 路径） | **必须改（能力缺失，不静默坏）** |
| 9 | 13229 | `_commitMultiStyle` | 跨引用块样式**明确拒绝** + 可见提示 | 引用内列表跨项选中 ⇒ 仍被拒（有提示，无数据损坏） | **兼容**（二期可另议是否支持） |
| 10 | 13392 | `deleteSelectionMulti` | 注释：blockquote/list 是"多段容器" | 注释仍对；但"段"可能是 list child | 注释需更新 |
| 11 | 13397 | `deleteSelectionMulti` | 同块跨段用 `nodePath[0]` 判断 `sSeg/eSeg` | 引用内 list：`nodePath[0]` 是 child 下标，**跨 item 时两者相同 ⇒ 返回 false（删除不可用）**；跨 child 时把 list 当"段"进入后续流程 ⇒ 丢 list | **静默坏·必改** |
| 12 | 13440 | `deleteSelectionMulti` 内 `inlineCtx` | 引用：`children[qi].children` 为 inline 根 | child=list 时 `children` 为空 ⇒ split 失败/空结果；若继续则 13473 重建丢 list | **静默坏·必改** |
| 13 | 13471-73 | 同上 | 结果块 = `A.blockquote([A.paragraph(joined)])` | 把"引用内列表 + 选区合并"压成**单段引用** ⇒ 未被选中的 list 项**全部消失** | **静默坏·必改** |
| 14 | 13495/13498 | 同上 | 引用块行 = `blm.startLine + nodePath[0]` | child 跨多行（list）⇒ 行区间错位 ⇒ **commitRange 删错行**（可能删掉后面未选中内容） | **静默坏·必改** |
| 15 | 13513 | 同上 | 新光标 prefix = `[0]`（引用只可能落在首段） | 结果块若含 list（二期保留形态时）⇒ 光标指向错 | **必改（与 13 同批）** |
| 16 | 13532 | `blockName` 映射 | 仅中文块名 | 不受影响 | **兼容** |
| 17 | 13535 | `_DEL_ORDER` | 仅提示排序 | 不受影响 | **兼容** |
| 18 | 13576 | `_blockLike` | 引用 ⇒ `A.blockquote([A.paragraph(nodes)])` | 删除/粘贴跨引用列表时把 list 压成段落 ⇒ 丢项 | **静默坏·必改** |
| 19 | 13648 | `replaceSelectionWithText` | 起点/终点是 quote/list 时走 `_replaceMulti` | 多行粘贴跨引用列表 ⇒ 见 20/21 | **必改（与 20/21 同批）** |
| 20 | 13708 | `_replaceMulti` 内 `inlineCtx` | 引用：`children[qi].children` inline 根 | 同 12 | **静默坏·必改** |
| 21 | 13754/13755 | `_replaceMulti` | 引用行 = `blm.startLine + nodePath[0]` | 同 14 ⇒ 粘贴**改错行**（可能破坏未选中内容） | **静默坏·必改** |
| 22 | 13767 | `_replaceMulti` | 光标 prefix `[0]` | 同 15 | **必改** |
| 23-28 | （13075-13535 内其余命中为同函数注释/日志/映射，判定同上：13392 注释、13425-13535 同批） | — | — | — | 已并入上表 |

> 说明：28 个命中行里有 4 行是**纯注释**（12145/12146/12225/12226/13392 等），实际要改的代码点集中在
> `blockContentStart / insertText / _extractSelectionMiddle / deleteSelectionMulti / _blockLike / _replaceMulti`。

---

## 3. `blockquote` 没出现、但**必须补分支**的函数（28 处清单之外）

| 函数 | 现状 | 二期缺口 |
|---|---|---|
| `splitParagraph`（12618-12788） | 只处理 paragraph/heading/list/blank_line；**没有 blockquote 分支** | 引用内按 Enter（段落内拆行 / list 项续列）目前 `return false` ⇒ 由于 beforeinput 已 `preventDefault`，表现为**按键无反应**。必须补：paragraph child ⇒ 在引用内拆成两个 paragraph；list item 内 ⇒ 拆成两个 item（同顶层列表语义但写回引用行） |
| `backspaceAtBlockStart`（12377-12468） | 只处理 heading/list/paragraph 的块首退格 | 引用内 list 项行首退格 ⇒ 合并到上一 item / 降级回段落（`> - a` → `> a`）；引用段落行首退格 ⇒ 与上一行合并（含跨 list 边界） |
| `outdentListItem`（12340-12376） | 仅顶层 list；用 `A.list(ordered, beforeItems/afterItems)` 重建 | 引用内 list 的"退列表"（`> - a` → `> a`）需要 blockquote 版本：把 child 由 list 拆成 `[list(before), paragraph(当前项), list(after)]` 并写回该引用块 |
| `indentListLevel`（13801-13940） | `block.type !== "list"` 直接 false | 引用内 list 的 Tab/Shift+Tab 不可用；需以 `blockquote.children[qi]` 为根做同样的树操作，再整块回写 |
| `insertText` 的**引用内 list 分支**（新增） | 无 | 见上表 #5/#7：要把光标解析成 `[childIdx,itemIdx,…]` 并写进 `item.children` |
| `_invalidateListItemLines` 调用点（新增） | 仅顶层 list 结构编辑时调用 | 引用内 list 做任何结构编辑后也必须对**内层 list** 调它（否则 source-gen 按旧 `item.srcLine` 补空行 ⇒ 凭空多空行）；建议封装 `_invalidateQuoteList(block)` |
| `_extractSelectionMiddle`/`_replaceMulti` 的**行区间 helper**（新增） | 各自手写 `blm.startLine + nodePath[0]` | 抽一个 `_childLineRange(blockIndex, child)`（用 §1 公式），delete/paste/split/style 共用，避免 6 处再各写一套 |

---

## 4. 4 个 `A.list(...)` 重建点（task-157 残余）判定

| 行 | 场景 | 是否丢 `number` / 重编号 | 判定 |
|---|---|---|---|
| 12348 / 12356 | `outdentListItem`：拆成 beforeItems / afterItems 两个 list | `beforeItems/afterItems` 复用**原 item 对象**（带 `number`）⇒ `canUseItemNumbers` 为真 ⇒ **数字保留**；新建 list 的 `start` 为空只影响空列表/无 number 项 | **基本安全**（建议顺手传 `start` 更严谨） |
| **12730** | `splitParagraph`：Enter 拆列表项 → `newItems[itemIdx]=A.listItem(sp2.left)` + 新 `A.listItem(sp2.right)`（**两者无 number**） | 混合 ⇒ 该层回退 `base+idx`（且 `A.list(ordered, newItems)` 未传 `start` ⇒ base=1）⇒ **整个有序列表被重编号 1..N** | **需修**（把原 item 的 `number` 继承给左半；右半 = 原号+1；并传 `start`） |
| 13897 | `indentListLevel`：`prevSib.list = A.list(ordered, [])` 后 push 带 number 的原 item | 新子列表 `start` 为空，但 item 有 number ⇒ 逐项回写 ⇒ **数字保留** | **安全**（可传 start 更严谨） |
| **额外** 13468（`deleteSelectionMulti`） | 引用/列表删选中段后重建 `A.list(ordered,[A.listItem(joined)])` | 新 item 无 number ⇒ 被删项所在行会从 `10.` 变 `1.` | **需修**（继承被合并项首项的 number） |
| **额外** 13574（`_blockLike` list 分支） | 粘贴替换到列表项时造单 item list | 同上 ⇒ 该 item 重编号为 1. | **需修** |

> 结论：**task-157 残余比我报告里写的更宽**——不只 12730，`13468/13574` 也会把"被编辑的那一项"重编号为 1.
> 建议在二期顺手统一修：给 `A.listItem` 重建处继承原 `number`（或抽 `_listItemWithNumber(srcItem, children)` helper）。
> 这样二期五类交互（拆项/删项/粘贴/升降级）都不会引出新的"数字被改"。

---

## 5. 二期实施顺序（建议，等 Lead 批）

```
第 0 步（无行为变化，先做地基）
  · 新增 _childLineRange(blockIndex, child)（§1 公式）
  · 新增 _parseEditPath(block, nodePath) → { childIdx, itemIdx|null, inlinePath }（统一 nodePath 语义）
  · 让 blockContentStart / insertText 用这两个 helper（修 #3/#5，先把"静默坏"堵住）

第 1 步（必须改的静默坏）
  · _extractSelectionMiddle / deleteSelectionMulti / _replaceMulti / _blockLike：
    引用 child=list 时走 list item 分支，结果块**保留引用内 list 形态**，行区间用 _childLineRange

第 2 步（二期功能）
  · 引用内敲 `- ` / `1. ` → convertStructuralBlock 扩展（在 blockquote child 上转换成 list child）
  · Enter：paragraph child 拆行 / list item 续列（splitParagraph 补引用分支）
  · Backspace：行首合并/降级（backspaceAtBlockStart 补引用分支）
  · Tab/Shift+Tab：引用内 list 升降级（indentListLevel 补引用分支）
  · 退列表（outdentListItem 引用版）

第 3 步（数字保号）
  · 12730 / 13468 / 13574 继承原 number（见 §4）

每步都要：源码模式 + 预览模式**两条路径真机验**，且**保存后磁盘逐字节**（task-157 方法论）。
```

## 6. 我需要的裁决

1. **批准按 §5 顺序做**吗？（第 0/1 步是"堵静默坏"，第 2 步才是用户要的交互；我建议 0→1→2→3 顺序，中途每步可报进度）
2. 第 3 步（数字保号，涉及 `deleteSelectionMulti`/`_blockLike` 等**非引用块**路径）**是否纳入二期**？
   - 纳入：顺手把 task-157 残余一并清掉，但会扩大二期 diff；
   - 不纳入：二期只保证"引用内 list 数字不被二期改动破坏"，非引用列表的 Enter 拆项重编号继续留残余（另立任务）。
3. `_commitMultiStyle` 跨引用样式（#9）二期**是否也要支持**？我建议**不做**（保持明确拒绝 + 可见提示，避免把样式跨容器语义也一起打开）。

---

## 7. 边界

只读盘点：**未改任何 src**；真机未启动（本步纯读码）；未碰 `docs/example/AAA_Vocab/**`；不 commit。


---

# 8. Step0 / Step1 进度（2026-10-26，Lead 已批准顺序）

## 8.1 Step0（地基，无行为变化）—— 完成
`app.js` 新增 helper 区（marker 包裹，供单测抽取）：
- `_segPos(block, cursor)`：块内「段/项」序位（引用内 list 用 childIdx*100000+itemIdx 细分）
- `_childLineRange(blockIndex, childIdx)`：child 源码行区间（0-based），走一期 `srcLine/srcLineEnd`；旧 AST 兜底 1 child=1 行
- `_quoteItemLineRange(blockIndex, childIdx, itemIdx)`：引用内 list 项的源码行（item.srcLine 是切片相对）
- `_parseEditPath(block, nodePath)`：统一 nodePath 语义（quote 段落 `[child, inline…]` / quote 列表 `[child, item, inline…]` / 顶层 list / 普通 block）

单测：`scripts/benchmark/maintenance/edit_path_helpers_test.js` **PASS=27 FAIL=0**
（覆盖 list 跨行 / paragraph 1 行 / 嵌套 list / 旧 AST 兜底 / 越界 null / 跨项序位）。
相关既有单测全绿：`blockquote_list_test` 47、`ordered_list_start_test` 43、E28 往返 80、键入序列 39、尾随空格 62、E30、m6b、scheduler。

## 8.2 Step1（堵静默坏）—— 代码完成，真机验收被**既有 mapper 缺陷**挡住
已改 5 个函数（app.js +226/−27，未 commit）：
1. `blockContentStart`：引用 child 为 list 时下钻 `[childIdx,itemIdx,…]`（不再指向 list 块本身）
2. `insertText`：引用内 list 时写入 **item.children**（旧实现会新建空段落**覆盖整个 list child** ⇒ R0）；空引用补段落逻辑保留
3. `deleteSelectionMulti`：同块跨段判定改 `_segPos`（跨 item 可判）；`inlineCtx` 下钻 item；结果块**保留 list 形态**；行区间改 `_childLineRange`/`_quoteItemLineRange`；光标 prefix 按 child 形态
4. `_replaceMulti`：同上（inlineCtx / 行区间 / prefix）
5. `_blockLike`：新增 `shapeChild` 参数，引用内 list 的删除/粘贴结果保留"引用+单 item 列表"

### 真机验收（`quote-list-step1-realapp.log/.json`，临时 KB，逐字节）
| 场景 | 结果 |
|---|---|
| A 预览编辑引用内**第 1 段** | ✅ 保存成功；引用行仅该行变（`> 前言段落一A`），list 两行/第二段/第二 list **逐字节不变** |
| B 预览编辑引用内**列表项** | ❌ 内存 body 变 `> B`（**第 1 段被覆盖**），磁盘未保存；目标项未变 |
| C 预览编辑引用内**第 2 段** | ❌ 内存 body 变 `> C`（第 1 段被覆盖） |
| D 预览跨两个列表项选中 Delete | 无效果（body/磁盘均不变）——同根因 + 需 forward-delete 路径，留 Step2 |
| E 源码模式改引用段落行 | ✅ 仅该行变（`> 前言段落一S`），其余逐字节不变 |
| E2 源码模式改引用列表行 | ✅ 仅该行变（`> - q1 tenT`），其余逐字节不变 |
| F/F2 Enter（引用段落内 / 引用列表项内） | **完全无反应**：磁盘不变、`state.doc.body` 也不变（见 §8.4） |

### 根因（**既有缺陷，不是 Step0/1 引入**）
`mapper.js` 的 `domToAst` / `astToDom` **没有 BLOCKQUOTE 分支**（HEAD 版 domToAst 函数体内 blockquote 命中数 = 0）：
- `domToAst` 把 `blockquote.children` 当**内联节点数组**，用整块 textContent 偏移去 `renderedToSrcCol` ⇒ 任何 child>0 的位置（第 2 段、list 项）都被映射回 child0；
- `astToDom` 同样按 inline 路径恢复光标 ⇒ 提交后光标也回到首段。
⇒ **预览编辑多 child 引用块一直是坏的**（首段"碰巧"正确）；一期把 list 放进 children 后暴露更明显。
Step1 的 insertText 修复把"写入 item.children"做对了，但**光标坐标本身就指错**，所以 B/C 仍会覆盖首段。

**需要 Lead 裁决**：把 `mapper.js` 纳入 task-156 写域（最小改 `domToAst`/`astToDom` 各加一个 blockquote 分支），否则 Step1 验收无法通过、Step2 全部交互也无法真机验证。

## 8.4 ③ Enter 影响面确认（Lead 要求单列）
**引用块内按 Enter 完全无反应**（不只是"不拆分"）：
- 引用段落内 Enter：`state.doc.body` 逐字节不变、磁盘不变（`splitParagraph` 无 blockquote 分支 → `return false`；beforeinput 已 `preventDefault` ⇒ 按键被吞）；
- 引用列表项内 Enter：同样完全无反应。
⇒ 这是**独立的用户可感知 bug**（可能比"引用里写列表"更常被踩到：任何多行引用都无法在预览里换行编辑）；建议 Lead 决定是否单独告知人/单列修复任务。源码模式 Enter 不受影响（源码面板是独立的行级编辑器）。


---

# 9. 【既有 R0 判定】预览模式编辑多 child 引用块会覆盖第 1 段并**写盘**
（Lead 要求：先判定"会不会写盘"，再动手改 mapper）

## 结论：**会写盘 = R0，且已发布版本（0.4.9 及之前）就有**
实验条件：**把 app.js 回退到 HEAD（无 Step0/1 改动）**，临时 KB 副本，真机真实按键，只看**磁盘字节**并用 `openFile` 重新打开验证持久化。
夹具 `docs/q.md`（多 child 引用：段落 + 2 项列表 + 段落 + 1 项列表）：
```
> 前言段落一
> - q1 ten
> - q2 eleven
> 后记段落二
> - q3 twelve
```

| 场景 | 编辑位置 | 磁盘是否变化 | 磁盘实际内容（引用行） | 重开验证 |
|---|---|---|---|---|
| A（对照，首段） | 第 1 段末输入 `A` | ✅ 1565ms | `> 前言段落一A`（正确追加，其它行逐字节不变） | — |
| **B（引用内列表项）** | `q1 ten` 末输入 `Y` | ✅ **1576ms** | **第 1 段行被替换为 `> Y`（原"前言段落一"丢失）**；目标项仍 `> - q1 ten` 未变 | ✅ 重开 body 仍是 `> Y` |
| **C（第 2 段）** | `后记段落二` 末输入 `Z` | ✅ **1580ms** | **第 1 段行被替换为 `> Z`（原"前言段落一"丢失）**；目标段仍 `> 后记段落二` 未变 | ✅ 重开 body 仍是 `> Z` |

字节证据（盘上引用行 before → after）：
```
C: ["> 前言段落一", "> - q1 ten", "> - q2 eleven", "> 后记段落二", "> - q3 twelve"]
→ ["> Z",        "> - q1 ten", "> - q2 eleven", "> 后记段落二", "> - q3 twelve"]   ← 第 1 段被覆盖
B: 同上，after[0] = "> Y"
```
产物：`quote-corrupt-head.log` / `quote-corrupt-head.json`（含 reopen.body）。

## 9.1 根因（既有，非 task-155/156 引入）
`mapper.js` 的 `domToAst` / `astToDom` **没有 BLOCKQUOTE 分支**（HEAD 版 `domToAst` 函数体内
blockquote 命中数 = 0，`git show HEAD:` 已核）：
- `domToAst` 把 `blockquote.children` 当**内联节点数组**，用整块 textContent 偏移 `renderedToSrcCol`
  ⇒ 任何 child>0 的位置（第 2 段、list 项）都会被映射回 child0；
- `astToDom` 同样按 inline 路径恢复光标；
- 于是 `insertText` 落在 child0 上（首段被覆盖），随后 `commit()` → `spliceBlockSource` → `markDirty`
  ⇒ **1.5s 后自动写盘**。
"首段碰巧对"说明旧实现是**偶然正确**：只有 child0 的偏移恰好落在首段内。

## 9.2 影响面（如实）
- **0.4.9 及之前所有版本**：在预览模式编辑"多 child 引用块"的**第 2 段及以后**，或**引用内列表项**，
  会**覆盖第 1 段并写盘**（丢用户内容）。
- 单 child 引用块（只有一段）不受影响；源码模式不受影响（源码面板独立行编辑）。
- 本任务一并修：`mapper.domToAst`/`astToDom` 各加 blockquote 分支（按 child 行/段边界映射，
  不再用整块 textContent 偏移），并修 `edit-handler.getPreviewCursor` 的引用块 srcLine（目前被
  block 首行覆盖）。修完后 Step1 真机矩阵重跑（见 §10）。


---

# 10. Step1 重验（mapper + edit-handler 修复后）—— ✅ 全绿

## 10.1 修复内容（按 Lead 批准的扩写域）
| 文件 | diff | 内容 |
|---|---|---|
| `mapper.js` | +157/−0 | ① `_domRenderedOffsetIn(container, domNode, domOffset)`：把"光标→渲染偏移"抽成**任意容器**可用；② `_resolveQuoteDomTarget(block, blockEl, domNode)`：按 DOM 真实父子关系定位引用块**直接 child + 列表项**（复用 `resolveListItem`，嵌套也定位）；③ `domToAst` 新增 BLOCKQUOTE 分支：child 为段落 ⇒ 在 `<p>` 容器内算偏移后映射 `[childIdx, …inline]`；child 为列表 ⇒ 在 `<li>` 容器内算偏移后映射 `[childIdx, itemIdx, …inline]`；④ `astToDom` 新增对称 BLOCKQUOTE 分支（按 child 边界重建 Range）。**不再用整块 textContent 偏移**（旧实现的"首段偶然正确"被废弃）。 |
| `edit-handler.js` | +10/−2 | `getPreviewCursor`：引用块的 `data--src-line` 只是块首行，**不再覆盖** `astToSrc` 的 child/item 行号（一期 mapper 的行跨度映射现在是唯一口径）。 |

## 10.2 真机矩阵（临时 KB，真实按键，**Q 列 = 磁盘字节**）

夹具（多 child 引用：3 段 + 2 个列表）：`> 前言段落一 / > - q1 / > - q2 / > 后记段落二 / > - q3 / > 尾段段落三`

| 场景 | 编辑 | 磁盘变化 | 改动行数 | 目标行命中 | 预览 ul/li |
|---|---|---|---|---|---|
| A | 第 1 段末 `A` | ✅ | **1** | ✅ `> 前言段落一A` | 2/3 |
| **B** | 引用内列表项 `q1 ten` 末 `B` | ✅ | **1** | ✅ `> - q1 tenB` | 2/3 |
| **C** | 第 2 段末 `C` | ✅ | **1** | ✅ `> 后记段落二C` | 2/3 |
| **C3** | 第 3 段末 `C3` | ✅ | **1** | ✅ `> 尾段段落三C3` | 2/3 |
| E | 源码模式：引用段落行末 `S` | ✅ | 1 | ✅ `> 前言段落一S` | — |
| E2 | 源码模式：引用列表行末 `T` | ✅ | 1 | ✅ `> - q1 tenT` | — |
| **D** | 预览跨两列表项选中 + Delete | ✅ | （合并 2→1 项） | ✅ `> - q1 tenq2 eleven`（其它 child 未动） | 2/3 |
| F/F2 | Enter（引用段落内 / 列表项内） | ❌ 未变 | 0 | — | — |

**关键**：每个场景**全部未涉及行/段/项逐字节不变**（`changedCount=1`）；预览在编辑后仍为 2 个 `<ul>`/3 个 `<li>`（列表结构未被打散）。

## 10.3 单测/回归
- 新增 `scripts/benchmark/maintenance/quote_dom_mapper_test.js`：**PASS=7 FAIL=0**（多段引用 / 段落+列表混合 / 列表内多 item / 嵌套列表 / 非法 DOM 不猜）。
- Step0 helper 单测 `edit_path_helpers_test.js`：**PASS=27 FAIL=0**。
- 既有单测全绿：E28 往返 80、E28 键入序列 39、`blockquote_list_test` 47、`ordered_list_start_test` 43、尾随空格 62、E30、`m6b`、scheduler。
- 门禁：`pytest 1485 passed`、`node --check` 66/66、`i18n` FAIL=0、12 剧本 12/12、`team_audit` FAIL=0（`prompt_drift` 对本轮 3 文件无依赖）。

## 10.4 已知限制（如实）
- **引用内嵌套列表**：`domToAst` 的 `nodePath` 仍取"顶层 item 下标"（与顶层 LIST 的既有口径一致），编辑嵌套子项时映射到其**顶层项**——与顶层列表的既有局限同级，不在本期扩大。
- **Enter** 仍无反应（`splitParagraph` 无 blockquote 分支）——Step2 必修项。
- `F/F2` 的"按键被吞"在 Step2 修 `splitParagraph` 后应恢复；届时回归本矩阵。

## 10.5 本轮改动/产物（未 commit）
```
app.js        +227/−27   Step0 helper + Step1 5 处堵静默坏
mapper.js     +157/−0    domToAst/astToDom BLOCKQUOTE 分支 + 2 helper
edit-handler.js +10/−2   getPreviewCursor 引用块行号
scripts/benchmark/maintenance/edit_path_helpers_test.js     (Step0 单测 27)
scripts/benchmark/maintenance/quote_dom_mapper_test.js      (mapper 单测 7)
artifacts/agent/verify/todo/quote-corrupt-head.*            (既有 R0 判定：HEAD 版写盘证据)
artifacts/agent/verify/todo/quote-list-step1-*              (Step1 矩阵/Q 列/日志/JSON)
```


---

# 11. Step2（引用块内交互）—— ✅ 真机全绿

## 11.1 实现（app.js +221/−4，未 commit；仅 Step2 自身改动）
| 交互 | 入口 | 实现 |
|---|---|---|
| ① 敲 `- ` / `1. ` 转换 | `convertStructuralBlock` → `_convertStructuralBlockInQuote` | 取 child 段落生成的**内层行**（不带 `> `），detect marker 后 `P.parseBlocks` 转 list child，原地替换并保留行号跨度；只支持列表标记（标题/嵌套引用受 parser 限制不转） |
| ② Enter 段落拆行 | `splitParagraph` → `_splitParagraphInQuote` | `splitInlineAt` 拆左右，按**原行前缀**生成 `pfx+left` / `pfx+right`，`commitRange` 只替换该行（段首/段末插入空引用行） |
| ② Enter 列表续列 | 同上 | 从**源行**提取 marker/indent（`1.` 右半自动 +1），替换该 item 行两行；空 item + Enter ⇒ 该行变空引用段落（退出列表） |
| ③ Backspace 行首 | `backspaceAtBlockStart` → `_backspaceAtBlockStartInQuote` | 首项 ⇒ 去 marker 退列表；非首项 ⇒ 合并上一项（仅相邻行，防误删松散空行）；段落 ⇒ 合并上一 child（上一 child 是 list 时并入其最后一项，且要求最后一项就是该 child 末行，防嵌套误删） |
| ④ 退列表 | ③ 的首项分支 | `> - a` → `> a`（空项 → `> `） |

**附带修**（都是真机暴露的）：
- `isAtBlockStart` 新增 **blockquote 分支**（按 child/item 的 inline 根判定）——否则引用内行首 Backspace 永远进不了 `backspaceAtBlockStart`（H5/H6/H7 起初全无反应）；
- `_quoteItemLineRange` 行号公式修正：`item.srcLine` 是**引用切片内相对 1-based**（不是相对 list child）⇒ `块首行 + item.srcLine - 1`（旧写法整体偏 1 行，H3/H4/H5/H7 起初改错行/丢行）；
- Step2 Enter 的 lead marker 取 `mLead[0]`（旧写 `mLead[3]` 是 undefined ⇒ 写出 `-undefined…`）。

## 11.2 真机矩阵（临时 KB，真实按键；Q=磁盘字节；行数Δ）

| 场景 | 操作 | 磁盘 | 行数Δ | 引用行结果 | 预览 ul/li |
|---|---|---|---|---|---|
| H1 | 引用段落内敲 `- ` | ✅ | 0 | `> - 前言段落一`（转列表） | 3/4 |
| **H2** | 引用段落内 Enter（段末） | ✅ | **+1** | `> 前言段落一` + `> `（新空引用行） | 2/3 |
| **H3** | 引用列表项 `q1 ten` 内 Enter | ✅ | **+1** | `> - q1 ten` + `> - `（新空项）在 q2 前 | 2/4 |
| **H4** | 空列表项内 Enter（退出列表） | ✅ | +1（累计） | `> - ` → **`> `**（空引用段落，项删除） | 2/3 |
| **H5** | 非首项 `q2` 行首 Backspace | ✅ | **−1** | 合并为 `> - q1 tenq2 eleven` | 2/2 |
| **H6** | 首项 `q1` 行首 Backspace（退列表） | ✅ | 0 | `> q1 ten`（去 marker）；q2 仍是列表 | 2/2 |
| **H7** | 列表后段落行首 Backspace | ✅ | **−1** | 并入上一项：`> - q2 eleven后记段落二` | 1/3 |
| S1 | 源码模式：引用行内 Enter | ✅ | +1 | 行级插入（源码面板逻辑，未受影响） | — |
| S2 | 源码模式：引用行行首 Backspace | ✅ | −1 | 行级合并（同上） | — |

- 每个场景**未涉及行均逐字节不变**（H2/H3 只是插入新行、H5/H7 合并相邻两行、H6 改 marker）。
- **H4 说明**：空 `<li>` 无文本节点，探针显式把选区放进空 `<li>`（与 `restoreCursor` 对空项恢复的状态一致：`anchor=LI`、`<li><br></li>`）后 Enter 即生效 ⇒ 真实用户路径等价。
- Enter 死掉的根因（`splitParagraph` 无 blockquote 分支 + beforeinput 已 preventDefault）已由 H2/H3/H4 修复验证。
- 探测方法修正（方法论）：Enter 必须用 `type:'keyDown', text:'\r'` 的真实序列（`rawKeyDown` 不会触发 `beforeinput insertParagraph`）；源码面板保存有 debounce，必须**等磁盘变化**而不是 sleep。

## 11.3 单测/门禁
- `edit_path_helpers_test.js` 27/0（C 组期望已按"切片相对"语义更新）；`quote_dom_mapper_test.js` 7/0；E28 往返 80、键入序列 39、`blockquote_list_test` 47、`ordered_list_start_test` 43、尾随空格 62、E30、m6b、scheduler 全绿。
- `pytest 1485`（下条消息确认）；`node --check` 66/0；`i18n` FAIL=0；12 剧本 12/12。
- `team_audit` **FAIL=2**：`steward_self_audit` 标准收据陈旧（`scripts/agent/prompt_drift_check.py` / `team_audit.py` 在工作区有**他人未提交修改**；`prompt_drift` 自身 FAIL=0）——不属本任务写域，需 Lead/steward 处置。

## 11.4 已知限制
- 引用内**嵌套列表**仍按顶层 item 下标（与顶层 LIST 既有口径一致），引用内 Tab/Shift+Tab 升降级未做（任务 ②「缩进」若指 Tab/Shift+Tab，需在 Step2.1 或单列；Backspace/Enter 已覆盖"续列/退列表"）。
- 空 item 退出列表在**列表中间**时，会留下 `> ` 空段落并可能让前后列表被 parser 合并为松散列表（与 CommonMark 语义一致，未额外拆列表）。


---

# 12. Step2 收尾：引用内列表 Tab / Shift+Tab（✅ 真机绿）+ 方法论沉淀

## 12.1 实现
- `indentListLevel` 分派：`block.type === "blockquote"` ⇒ `_indentQuoteListLevel(block, cursor, dir)`。
- `_indentQuoteListLevel`：与顶层 `indentListLevel` **同构树操作**，但 ①在 list 的**克隆**上改树（失败/行数变化不污染 AST）；②`_invalidateListItemLines` 后用 `G.generateBlock(cloned)` 生成内层行；③逐行加回**原引用前缀**（`block.prefixes`），只替换该 list child 的行区间；④**行数必须不变**（缩进不增删行）否则拒绝。
- `mapper.domToAst` 引用内 list 分支新增 `listPath`（相对该内层 list 的树路径，来自 `_resolveQuoteDomTarget`/`resolveListItem`），供 Tab 定位（+2 行）。
- 光标：落到被移动项所属**顶层项**开头（nodePath 只支持顶层 item 下标；嵌套精确落点由后续点击决定，与顶层 Tab 的保守行为一致）。

## 12.2 真机（Q=磁盘字节，行数Δ）
| 场景 | 操作 | 磁盘 | 行数Δ | 结果 | 预览 ul/li |
|---|---|---|---|---|---|
| **J1** | `q2 eleven` 行内 Tab（降级） | ✅ | **0** | `> - q1 ten` + `>   - q2 eleven`（挂到 q1 子列表） | 3/3 |
| **J2** | 同一项 Shift+Tab（升级） | ✅ | **0** | 回到 `> - q2 eleven`，**引用行与 pristine 逐字节一致** | 2/3 |

（J2 前探针显式重新聚焦 q2 —— 与真实用户"光标仍在该项"等价；应用侧 Tab 后光标落点为所属顶层项开头，属已知保守行为。）

## 12.3 方法论沉淀（与 task-157「可达性必须走真机 preview-edit」并列）
1. **Enter 必须用 `type:'keyDown', text:'\r'`** 的真实按键序列；`rawKeyDown` **不会**触发 `beforeinput insertParagraph` ⇒ 用 rawKeyDown 测 Enter 会得到"按键完全没反应"的**假阴性**（本轮 F/F2 一开始就踩了这个坑）。
2. **源码面板保存有 debounce**：判"是否写盘/是否生效"必须**轮询磁盘变化**，不能 `sleep(600)` 后读一次（S1/S2 起初误判失败）。
3. **"代码能跑、单测能过、真机一看就错"是独立一类 bug**：本轮 3 个（`isAtBlockStart` 无 blockquote 分支 / `item.srcLine` 切片相对语义 / `mLead[3]` 未捕获组）全部只在真机矩阵暴露 ⇒ 交互类改动必须"S 源码 + P 预览"两条路径都真机验，且**逐行 diff** 而不是只看"变化了没有"。
4. **真机矩阵每一格都是判据**：H3 起初把 q1 复制、q2 丢失，靠"引用行前后对照"抓到；只看 bodyLength/行数变化会漏。


---

# 13. Step3（有序列表数字保号）—— 严格 3 处 + helper ✅ 真机绿

## 13.1 范围（按 Lead 裁决，不许漂移）
- 新增 `_listItemWithNumber(srcItem, children, numberOverride)`：重建列表项时继承原项**手写序号**与缩进；`numberOverride` 给"拆出的右半新项"。
- 改 3 处：`12730`（顶层 list Enter 拆项）/ `13468`（deleteSelectionMulti 重建单 item list）/ `13574`（`_blockLike` 粘贴替换单 item list）。
- **未动**：outdent(12348/12356)、13897（判定当前安全）。
- 说明一处"同站点延伸"：deleteSelectionMulti 的**引用内列表分支**（Step1 加的 `A.blockquote([A.list(...)])`）也用了同一 helper（否则引用内删合并会把 `> 10.` 变 `> 1.`）——它属于 13468 同一调用点，不是新范围。

## 13.2 编号语义（Lead ①要求的"预期序列"）
**原则：只改被编辑行；未触碰行逐字节不变。**
- `10. flat ten` 末 Enter ⇒ `10. flat ten` + **新 `11. `**（右半 = 原号+1）；原 `11. flat eleven` **保持 11.** 不动（源码 marker 可与新项重复；CommonMark 渲染序号按位置连续 = 10,11,12，用户看到不乱）。
- 选区删除合并（10./11. 跨删）⇒ 合并项沿用**起始项** `10.`；被删项行消失；其它项不动。
- 多行粘贴进列表项 ⇒ 首块沿用原号、新尾块 = 原号+1；未触碰的后续项不动。
- 无序列表 / 旧 AST（无 number）⇒ 走既有 `base+idx` 兜底（与改动前一致）。

## 13.3 真机矩阵（Q=磁盘字节；夹具含 `> 10./11./12.` 引用列表 + `10./11.` 顶层列表）
| 场景 | 操作 | 磁盘 | 行数Δ | 结果（关键行） |
|---|---|---|---|---|
| **K1** | 引用内 `10. ten` 末 Enter | ✅ | +1 | `> 10. ten` / **`> 11. `（新）** / `> 11. eleven`（未动）/ `> 12. twelve`（未动） |
| **K2** | 顶层 `10. flat ten` 末 Enter（12730） | ✅ | +2* | `10. flat ten` / **`11. `（新）** / `11. flat eleven`（未动） |
| **K3** | 顶层跨 10./11. 选中 Delete（13468） | ✅ | −1 | `10. flat tenflat eleven`（**保留 10.**） |
| **K4** | 顶层 `10.` 项内多行粘贴（13574） | ✅ | +2* | `10. flat tenX` / `11. Y` / `11. flat eleven`（未动） |
| **K5** | 引用内跨 10./11. 选中 Delete（13468 引用分支） | ✅ | −1 | `> 10. teneleven`（**保留 10.**）/ `> 12. twelve`（未动）/ 顶层列表完整 |
| **K6** | 源码模式改 `11. flat eleven` 行内 | ✅ | 0 | 仅 `11. flat elevenS`，其余逐字节不变 |

\* K2/K4 行数Δ=+2 含 1 行**尾空行**——见 §13.4：**HEAD 基线同样存在，非 Step3 引入**。

**对照 HEAD（ae858b8c，无 Step3）**：同矩阵下 K2/K4 数字为 **1./2./3.**（被重编号），K5 引用合并项为 **> 1.**；施加 Step3 后变为 10./11./11. 与 > 10. ⇒ 保号目标达成。
**未触碰行保序**（子序列断言）K1/K2/K6 全部 true；K3/K4/K5 其它块（引用列表/顶层列表）逐字节不变。

## 13.4 相邻发现（**非 Step3 引入**，如实登记）
**顶层列表结构编辑发生在文档最后一个列表块时，会多一个尾空行**（K2/K4 行数Δ=+2 而非 +1）。
- 已在 **HEAD（无 Step3）** 用同一 probe 复现（Δ 同样 +2）⇒ 既有行为，不是本步引入。
- 影响：多一个空行（内容不丢），属"静默改文件"类；与 task-147 尾换行同族但方向相反。
- 不在 Step3 范围（Step3 只 3 处保号）；建议 Lead 决定：并入后续 task 或单列（我可以下一步只读定位根因）。

## 13.5 单测
`scripts/benchmark/maintenance/list_item_number_test.js`：**PASS=12 FAIL=0**
- 有序继承/override；无序不写 number；旧 AST（srcItem=null / 无 number）不写；indent 继承；
- **松散列表**（10,11,3,4 合并 list）逐项重建后**逐字节往返**；
- **嵌套 list**（5/6/7）重建逐字节往返；有序+无序混合往返。

## 13.6 门禁
`pytest 1485 passed`；node 66/0；i18n FAIL=0；`prompt_drift` FAIL=0 exit 0；`team_audit` **FAIL=0**（r6 重签后已回绿）；12 剧本 12/12。
单测回归：helper 12、edit_path_helpers 27、quote_dom_mapper 7、E28 80、键入 39、引用列表 47、有序 43、尾随空格 62、E30、m6b、scheduler 全绿。
