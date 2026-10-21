# P4 EditCore 方案（编辑层）

> **状态**：设计稿（2026-10-21）
> **前置**：P5 前半已冻结 `S_render_frozen`（13/13 全绿，commit `a358df18`）
> **风险等级**：**最高** —— 前四片只写 DOM，本片开始写**真源**

---

## 0. 一句话结论

**P4 不是"重写编辑器"，而是"让 new 插头驱动同一套编辑内核，同时暴露块级增量接口"。**

依据：`legacy-surface.applyEdit()` 的五个 kind **全是门面委托**——真实编辑逻辑在
`window.MemoriaEditSync`（app.js:7697）与 `window.MemoriaApp.surface`，**不在渲染层**。

```js
// legacy-surface.js:165-186
applyEdit: function (op) {
  var es = _es();                                    // MemoriaEditSync
  case "insertText":   return es.insertText(op.text);
  case "splitBlock":   return es.splitParagraph();
  case "mergeBlock":   return es.backspace();
  case "deleteRange":  return _app().surface.deleteRange(...);
  case "replaceRange": return _app().surface.replaceRange(...);
}
```

**⇒ P4 的工程量取决于"编辑内核与渲染层的耦合度"，不是"编辑器有多少功能"。**

---

## 1. 现有资产盘点（已核实）

| 资产 | 位置 | 规模 | 归属 |
|---|---|---|---|
| **编辑内核** | `window.MemoriaEditSync`（app.js:7697） | 方法 30+ | legacy 专用，但**与渲染层解耦** |
| 编辑入口 | `MemoriaEditHandler`（edit-handler.js） | 84KB / 1999 行 | 事件绑定层 |
| 块级写回门面 | `MemoriaApp.surface.setBlockSource` | 已有 | **P4 可直接复用** |
| 撤销/重做 | `EditSync.beginUndoGroup/undo/redo` | 已有 | **P4 可直接复用** |
| 块身份 | `BlockIndex` | 阶段 1 | **P4 的核心** |
| 新渲染器 | `render-core.js` | P2a–P2c | 已冻结等价 |

**关键：`EditSync` 是按"块"操作的**（`splitParagraph` / `revertBlock` / `applyStyle`），
**它的数据结构与 `BlockIndex` 天然对齐**。

---

## 2. P4 的四条硬约束（来自阶段 2 计划与今日裁决）

### C1. `applyBlockPatches` 块级增量接口（人机并发编辑的前提）

```js
applyBlockPatches(patches: Array<{blockId, srcLineStart, srcLineEnd, newText}>): void
```

**为什么必须**：`docs/design/concurrent-edit-infrastructure.md` 的 B/C/D 三层全部依赖它。
没有它，agent 只能"整篇 setText"，人机并发编辑无从谈起。

**验收**：改 3 个块后，**光标位置不变、其余块 DOM 未重建**（用 MutationObserver 证）。

### C2. S13 一并修复（编辑路径本来就要重写）

`collectEditorBody()` 按 `.-line-content` 逐行 `join("\n")`，**丢文件尾 `\n`**。

**验收**：编辑 → 保存 → 重开，**逐字节比对磁盘与内存 body**。

### C3. 编辑不丢字（最高优先级验收）

**这是 P4 与前三片的本质区别**：

| | P2a–P2c | P4 |
|---|---|---|
| 方向 | AST → DOM（单向） | **双向**（编辑 → 真源 → 重渲） |
| 失败后果 | 看得见的渲染错 | **数据损坏** |

**验收**：随机编辑序列（插入/删除/拆分/合并/撤销）× 每个操作后保存 → 重开 → 逐字节比对。

### C4. 渲染等价不回归

P4 改动后，`S_render_frozen` 的 13 文档矩阵**必须仍全绿**。
这是"编辑层没污染渲染层"的直接证明。

---

## 3. 切片（P4a → P4d）

| 片 | 内容 | 出口 |
|---|---|---|
| **P4a** | 接线：`new-surface.applyEdit/undo/redo` → 复用 `EditSync`；new 渲染下编辑可用 | 基本编辑（插入/删除/拆分/合并）可用，签名仍 0 diff |
| **P4b** | **S13 修复** + `collectEditorBody` 保尾换行 | 编辑 → 保存 → 重开逐字节一致 |
| **P4c** | **`applyBlockPatches`** 块级增量接口 + 光标保持 | 改 3 块后光标不变、其余块 DOM 未重建 |
| **P4d** | 编辑不丢字的随机序列验收 + `S_render_frozen` 回归 | 随机序列 100% 通过 |

---

## 4. 风险与缓解

| 风险 | 后果 | 缓解 |
|---|---|---|
| **编辑内核与 `#editor` DOM 强耦合** | new 渲染下编辑完全不可用 | P4a 先做**可行性验证**（spike），不通立即回报 |
| 撤销栈与新渲染不同步 | 撤销后画面错乱 | 复用同一份 `EditSync` 撤销栈，**不新建** |
| 编辑后签名必然变（内容变了） | 无法用签名判等 | P4 的判等 = **legacy 与 new 在同一编辑序列后的签名相同**，不是"编辑前后相同" |
| 改编辑路径把渲染改坏 | 回退 P5 结论 | 每个切片后跑 `S_render_frozen` 回归 |

---

## 5. P4a 的第一步：可行性 spike（不确定就先证明）

**在动任何代码之前，先回答一个问题**：

> new 渲染出的 `#preview` DOM，能否被 `EditSync` 的编辑操作正确驱动？

`EditSync` 依赖的部分选择器（如 `.-src-block` / `.-line-content`）在 new 渲染下是否都存在？

**spike 交付**：一个只读探测脚本，在 `switchTo('new')` 后检查：
1. `EditSync` 需要的所有 DOM 选择器是否命中
2. 在 new 渲染下模拟一次 `insertText`，看是否写进真源
3. 若失败，**明确列出缺哪些选择器/属性**

**只有 spike 通过，才开始 P4a 的正式接线。**

---

## 6. 与其它文档的关系

| 文档 | 关系 |
|---|---|
| `stage2-plan.md` | P4 的定义 + `applyBlockPatches` 约束 |
| `concurrent-edit-infrastructure.md` | C1 的需求来源（人机并发编辑 B/C/D 层） |
| `render-fidelity-contract.md` | P4 的判等工具与 `S_render_frozen` 基线 |
| `block-identity-design.md` | 块身份契约（`applyBlockPatches` 的单位） |
| `display-refactor-charter.md` §8 | S13 登记处 |
