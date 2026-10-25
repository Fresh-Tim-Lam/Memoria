# task-157 · 有序列表 `start > 1` 往返被重编号（10.→1.）—— 可达性调查 + 修复

> 状态：**已修复**（4 个小改 + 单测）；四项结论齐全；门禁全绿；**未 commit**。
> 基线：`a0c7dfd9`（task-155 一期已提交）；用户库只读。
> 结论定性：**R0（用户文件被静默改动）—— 已真机证实可达，非 INFO**。

---

## 0. 四问结论（Lead 要求先只读调查）

| # | 问题 | 结论 | 证据 |
|---|---|---|---|
| ① | `generateBlock` 输出是否会被写回文档/磁盘？ | **会（R0 可达）** | 代码路径 + 真机（见 §1） |
| ② | 用户在有序列表里改一个字符，保存后数字会不会变？ | **源码模式：不会；预览模式：会**（`10.`→`1.`） | 真机 A/B（§2） |
| ③ | AST 有没有 `start`？ | **有**（`10.`→start=10，`1.`→null）；但**只有 start 不够**，还需逐项 `item.number`（§3） | `ordered-list-static.log` |
| ④ | 引用块内有序列表是否同样受影响？ | **是**（往返 + 真机 C：编辑同块普通段落即触发 `> 10.`→`> 1.`） | static + 真机 C |

**可达性判定：写盘可达，定 R0。** Lead 的"若只有显示则 P1"分支不成立。

---

## 1. ① 写回链路（代码路径，逐个 file:line）

```
app.js:11903  function commit(block, cursor, nativeDone)            ← 预览编辑提交（普通输入）
app.js:11916  function commitSelection(block, blockIndex, …)        ← 选区替换
   ↓
app.js:11906 / 11919   spliceBlockSource(cursor.blockIndex, G.generateBlock(block))
app.js:11384  spliceBlockSource(blockIndex, newBlockSrc):
               state.doc.body = merged.join("\n");  state.doc.lines = merged;   → markDirty → autosave 写盘
同类写回点（同一模式）：
app.js:13281（格式刷多块）、12348/12356/12730（列表拆分/合并/编辑项）、
13477（结构转换）、13606、13930、12640/12692/12700/12709（图片/块拆分）
```
⇒ `G.generateBlock()` 的产物**直接成为文档源码**，不是"仅显示"。

## 2. ② 真机（临时 KB 副本，CDP 真实按键；`ordered-list-realapp.log/.json`）

夹具 `docs/ord.md`：`10. ten / 11. eleven`、`3. three / 4. four`、`> 前言段落` + `> 10. qten / > 11. qeleven`。

| 场景 | 编辑动作 | 修复前磁盘 | 修复后磁盘 |
|---|---|---|---|
| A 源码模式（对照） | `10. ten` 行尾输入 X | `10. tenX / 11. eleven` ✅ 不变 | 同左 ✅ |
| **B 预览模式** | 预览列表项 `ten` 内输入 Y | **`1. tenY / 2. eleven`**（R0） | **`10. tenY / 11. eleven`** ✅ |
| **C 预览模式** | 引用块**普通段落**末尾输入 W | **`> 1. qten / > 2. qeleven`**（R0，④） | **`> 10. qten / > 11. qeleven`** ✅ |

**关键点**：C 说明**编辑同一引用块里的普通段落**就会把整块（含内部有序列表）重新生成 ⇒ 一期新能力同样中招。
修复前还观察到 `3. three / 4. four` 被并到同一松散列表后变成 `12./13.`（见 §4 的"逐项编号"必要性和 D4/D5 测试）。

## 3. ③ 为什么"只改 source-gen 用 block.start"还不够

静态探针（`ordered-list-static.log`）：
```
"10. ten\n11. eleven"  → list.start=10
"1. one\n2. two"       → start=null
"> 10. ten…"           → 引用内 list.start=10
```
AST 已有 `start`。**但** CommonMark 的松散列表会把"空行分隔的同类型有序列表"**合并成一个 list**：
```
"10. ten\n11. eleven\n\n3. three\n4. four\n"  → 一个 list（4 项，start=10）
```
⇒ 若按 `start + idx` 编号，后两项会被写成 `12./13.`（真机 B 的实际观察）。
所以修复需要**逐项真实手写序号**（`item.number`），`start` 只覆盖"连续从首项编号"的常见情形。

## 4. 修复（4 文件，小改；未 commit）

| 文件 | diff | 内容 |
|---|---|---|
| `ast.js` | +5 | `listItem(children, extra)` 支持 `extra.number`（有序项真实序号） |
| `parser.js` | +2 | 列表收集时 `number: cIt.ordered ? parseInt(marker,10) : null` |
| `source-gen.js` | +28/−2 | ① 新增 `canUseItemNumbers(node)`：**该层所有有序项都有真实序号** ⇒ 逐项回写；否则整层回退 `base + idx`（结构编辑新建的 item 无 number ⇒ 保持旧的"重新编号"语义）。② `start` 基数（`listBaseNumber`）供回退用。③ 嵌套子列表同样按各自序号/基数 |
| `mapper.js` | +5 | `listPrefixLen` / `listItemPrefixLen` 优先用 `item.number` 的位数（松散列表里 `3.` 与 `12.` 宽度不同 ⇒ 否则列号偏 1） |

**为什么这样设计**：
- 编辑文本/格式（AST 项完整保留）⇒ 逐项回写 ⇒ **数字永不被动**（B/C 场景）。
- 结构编辑（Enter 拆项/删项）走 app.js `A.list(ordered, newItems)`（无 number）⇒ 该层整体 `base+idx`，与改动前行为一致，不会出现重复编号。
- `1.` 起编号的列表行为完全不变（`base=1`, 无 number 时同旧）。

## 5. 红 → 绿（同一单测 `scripts/benchmark/maintenance/ordered_list_start_test.js`）

- **改前红**（`ordered-list-RED.log`，回退 4 文件到 `a0c7dfd9` 跑）：`PASS=27 FAIL=16`
  —— B 往返 13 例（`3.`/`10.`/`9.`/`99.`/引用内/嵌套/松散合并/大数字…）、C1/C2/C3 编辑后保真、D4 列宽。
- **改后绿**（`ordered-list-GREEN.log`）：`PASS=43 FAIL=0`。
  - B：14 个样本**逐字节往返** + 幂等（含 `> 10.`、松散合并 `10,11,3,4`、嵌套继续编号 `2,3,4`、`99/100`）。
  - C：编辑 item 后编号保持（普通列表 / 引用内列表 / 混合嵌套）。
  - D：列宽 `10.`=4、`100.`=5、`> 10.`=6、松散列表 `3.`=3、`> 10.` 引用内=6。
- **回归单测全绿**：`blockquote_roundtrip_test`（80）、`blockquote_typing_sequence_test`（39）、`trailing_space_input_test`（62）、`edit_cut_undo_test`（E30）、`blockquote_list_test`（47）、`scheduler_vm_test`、`m6b_adjust_test`。

## 6. 门禁

| 门禁 | 结果 |
|---|---|
| `pytest -q tests` | **1485 passed / 0 failed**（基线 1475 不降） |
| `node --check` 全仓非 vendor JS | **66/66** |
| `i18n_selftest` | **FAIL=0** |
| 12 交互剧本 | **12/12** |
| `team_audit` / `prompt_drift` | **FAIL=0**（我的 4 文件不在提示词依赖里；Lead 的 `a0c7dfd9` 已清掉 kb-spec 两处） |

## 7. 已知残余（如实登记，未纳入本轮）

**结构编辑会重新编号该层**：在有序列表里 **Enter 拆项 / 删项 / 调整层级**时，app.js 会用
`A.list(block.ordered, beforeItems/afterItems/newItems)` 重建列表（无 `number`）⇒ source-gen 该层回退 `base+idx`，
表现为"从该列表首项起连续编号"。
- 与"只改一个字也被静默重编号"（本任务 R0）**不同级**：那是用户没动编号却被改；这里用户确实在改列表结构。
- 若要连结构编辑也保编号，需改 app.js 那 3 个重建点（不在 task-157 写域）⇒ 建议归入 **task-156**（引用块二期，本来就要动 app.js 的列表假设）或单列。
- 已知触发点：`app.js:12348 / 12356 / 12730`（列表拆分/合并/编辑项）、`13897`（子列表重建）。

## 8. 产物与边界

```
artifacts/agent/verify/todo/ordered-list-renumber.md          ← 本报告
scripts/benchmark/maintenance/ordered_list_start_test.js      ← 新单测（A-E + INFO）
artifacts/agent/verify/todo/ordered-list-RED.log              ← 改前红（16 FAIL）
artifacts/agent/verify/todo/ordered-list-GREEN.log            ← 改后绿（43/0）
artifacts/agent/verify/todo/ordered-list-static.log/.js       ← AST/往返静态证据
artifacts/agent/verify/todo/ordered-list-fixture-gen.py       ← 夹具（CRLF，含引用内有序列表）
artifacts/agent/verify/todo/ordered-list-realapp-probe.mjs    ← 真机探针（A/B/C 三场景）
artifacts/agent/verify/todo/ordered-list-run.ps1              ← 运行器（safe-kill + 临时 KB）
artifacts/agent/verify/todo/ordered-list-realapp*.log/.json   ← 真机证据（改前 R0 / 改后保真）
```
**边界**：真机只用 `%TEMP%` KB 副本；未触碰 `docs/example/AAA_Vocab/**`；用户 `Package\Memoria.exe`
（PID 37620）前后一致；端口 9587 已释放；**不 commit**。
