# frontend-modules.md — 前端 JS 模块化与「不再往 app.js 堆」规范

> **用途**：定义前端 JS 的**模块边界与依赖方式**，确立「新功能主体不进 `app.js`、旧代码触及即搬」的增量规则，遏制单文件堆砌。
> **目标读者**：改动前端（`src/memoria/ui/static/**`）的人与 AI Agent。
> **关联文档**：[docs-management.md](./docs-management.md)（文档归置）、[directory-organization.md](./directory-organization.md)（目录职责）、`docs/reference/agent-guide/`（功能·交互说明）。
> **状态**：生效中，2026-09-15。

---

## 1. 背景（问题与证据）

| 文件 | 行数 | 说明 |
|---|---|---|
| `src/memoria/ui/static/app/js/app.js` | **12,933** | 496 KB，是第二名的 **6.7 倍** |
| `src/memoria/ui/static/app/js/edit-handler.js` | 1,919 | 预览区编辑 |
| `src/memoria/ui/static/app/js/markdown-preview.js` | 1,537 | 预览渲染 |

> 证据：2026-09-15 `Get-ChildItem src/memoria/ui/static/app/js/*.js | Sort-Object Length -Descending`。

**根因**：`app.js` 是**单一 IIFE**，`state`、`$(...)`、`log`、`markDirty`、`closestLineEl`、`focusLineContent` 等皆为**闭包私有**且被上千处调用。外部文件拿不到它们 → 新功能要么就地写进 `app.js`，要么先做一次导出重构；实践上总是倾向就地写。

**已发生的后果**（本轮实例）：

1. **同一件事两份实现**：预览区键盘选区在 `edit-handler.js`，源码区键盘选区在 `app.js`，规则相同、代码各写一遍。
2. **跨文件私有导出缝合点**：`EH.wordLeft / EH.wordRight` 被用来让 `app.js` 借用 `edit-handler.js` 的私有函数——这是症状，不是设计。

---

## 2. 规则

### R1　新功能主体不进 `app.js`

新增前端能力 → 新建 `src/memoria/ui/static/app/js/<feature>.js`（kebab-case，按功能命名），并在 `index.html` 增加一行 `<script>`（依赖在前；模块自身只做「定义 + 装配」）。`app.js` 顶多留**装配用的一小段**。

### R2　显式依赖注入，不偷看闭包

新模块**不得**读取 `app.js` 的闭包私有符号；由宿主在装配点显式传入：

```js
// app.js（装配点，唯一允许出现在 app.js 的新代码形态）
window.MemoriaSelSource.init({
  editor, closestLineEl, offsetWithinLine,
});
```

### R3　单向依赖

模块只通过 `init` 钩子或 `window.Memoria*` 命名空间与宿主交互；`app.js` 不直接改模块内部状态。模块自持状态，对外只暴露行为方法。

### R4　触及即搬（增量，禁止大爆炸重写）

改动 `app.js` 中**边界清晰**的一块时，顺手把它搬出。约束：

- 一次只搬**一件**功能；
- **纯搬移不改语义**（行为改动与搬移分成两次提交/两轮验证，避免"测试结果失真"）；
- 搬完必须 `node --check <file>`，并在真机上复测**同一场景**。

### R5　共享工具唯一实现

跨区域复用的纯函数（词边界、行内文本偏移、Range 渲染等）放**共享文件**（如 `selection-core.js`），禁止用 `EH.xxx` 这类私有导出在文件之间"互相借"。

### R6　内核最后搬

`state` / `$()` / `log` / `markDirty` 等被全局依赖的内核项**留到最后**，或先抽成 `app-core.js` 再由 `app.js` 解构引用。**不允许**为了"整份拆干净"而发起一次性全量重构。

---

## 3. 目标顺序（候选清单，按边界清晰度）

| 顺序 | 目标 | 现状 |
|---|---|---|
| 1 | `selection-core.js` + `sel-preview.js` + `sel-source.js`（本规范首例） | `sel-source.js` 已落地；core / preview 待搬 |
| 2 | 源码编辑器行操作（行合并/拆分、`dragSelect`） | 部分已随 sel-source 迁出 |
| 3 | 公式/选区右键菜单、导入导出流程 | 待搬 |
| 4 | 知识库检查面板、图谱入口、设置面板、文件树交互 | 待搬 |

---

## 4. 自查清单（提交前逐条打勾）

- [ ] 本次**新增**的代码是否落在 `app.js`？（是 → 退回）
- [ ] 新模块是否只依赖 `init` 传入的钩子？（无闭包越权）
- [ ] 是否引入/残留跨文件私有符号借用（`EH.`、读别人闭包）？
- [ ] 若为搬移：是否**未改语义**，且 `node --check` + 真机同场景复测通过？
- [ ] `index.html` 是否登记了新 `<script>`（含加载顺序）？

---

## 5. 修订记录

| 日期 | 修订 |
|---|---|
| 2026-09-15 | 初版：确立 R1–R6；首例落地 `sel-source.js`（源码区键盘 + 鼠标选区迁出 `app.js`，并修鼠标跨行选区锚点丢失）；登记 `conventions/README.md` / `README.cn.md` 与 [docs-management.md §4.2](./docs-management.md) |
