# task-150 · 源码区剪切（Ctrl+X）不可用 —— 根因修正 + 完全接管修复

> 用户反馈（两次）：「还是没有办法使用剪切」→「**是在源码区域**」。
> 状态：**已修复 + 改前红/改后绿真机双向证据 + 失败路径已验 + 全门禁绿**（工作区未 commit，等 Lead 统一提交）。
> 基线：**HEAD=`225110bb`**（task-147 修复已提交）；开工时 `app.js` / `edit-handler.js` 工作区无他人未提交改动。
> 本轮修改：`app.js`（+136/−0）、`i18n/zh-CN.js`、`i18n/en.js`（各 +3）；**未动** `edit-handler.js`、未 commit。

---

## 0. 台账先说：旧"剪切已修"条目到底修了什么、为什么没覆盖源码区（声明≠事实）

**旧条目：E30「Ctrl+X 后再粘贴，剪切的内容重现」→ 2026-10-22 归档为 ✅ 已闭环**
（证据锚：`docs/design/ledger-archive-2026.md §10.4.1`；提交 `002b5506` + `1b6956e3`；`edit_cut_undo_test.js` 28/28 + 探针 20/20。）

**它的范围原文（`docs/design/editor-input-defects-2026-10.md:57-63`）明确只覆盖预览区：**
```
影响面：预览区富文本编辑的剪贴板路径（【源码区是否同样待真机确认】）
定位线索：beforeinput 只拦截 … （edit-handler.js:834-855）；#preview 上…
```
以及 `docs/todo.md:105`（E33）与 `editor-input-defects…:108` 都写：「**E30 只修了 Ctrl+X（`deleteByCut`）**」
—— 指的是 `edit-handler.js:962` 那一个 `preview.addEventListener("beforeinput")`。

**结论（如实指出，不为台账好看而绕开）：**
1. 旧修复**不是回归**，而是**从未覆盖源码区**：源码区（`#editor`）根本没有 cut/copy/beforeinput 处理，
   全仓只有 `editor.addEventListener("paste", …)`（`app.js:8222` 附近），源码区靠浏览器**原生 cut**。
2. E30 的验收判据全部是**预览区**动作（"预览区选中一段 → Ctrl+X …"），
   而"源码区是否同样"这行字在归档时**没有被任何测试/探针回答**就直接 ✅ 了。
3. 用户「**还是**没有办法使用剪切」正好落在这条**未验证的边界**上。
   **建议台账**：E30 归档条目补一行"源码区未覆盖（2026-10-25 用户复报 → task-150，已修，见本报告）"；
   源码区 cut 单独立项登记（E35 或新 ID），不要并进 E30 的 ✅。

---

## 1. Lead 推断的修正（真机实测后据实修正，不硬套）

Lead 推断：「原生 cut 在多 contenteditable 根选区上**失效**，源码区靠原生 cut ⇒ 不可用」。
**机理对了一半，失败模式更坏**。真机（WebView2，CDP 真实按键，4 组用例）实测：

| 用例 | 选区 | 剪贴板 | 文档删除 | 撤销 | 结论 |
|---|---|---|---|---|---|
| S1 单行剪切 | 第3行 6–18 列 | ✅ 正确 | ✅ 正确 | ✅ 一次 | **原生单行 cut 可用**（不是"完全不可用"） |
| S2 跨行剪切 | 第3行 10 列 → 第5行 6 列 | ✅（近似全文，CRLF 行尾） | ❌ **只删了第一个 `.-line-content` 根内的部分** | ✅ | **静默部分删除/内容残留（比失效更坏）** |
| S5 整行跨行剪切 | 第3行行首 → 第4行行尾 | ❌ **还丢了空行**（块边界被吞） | ❌ 删错 | ✅ | 同上，且序列化也不可信 |
| S3 单行复制 | 同行 | ✅ | 不删 | — | 可用 |
| S4 跨行复制 | 跨行 | ✅（CRLF 行尾） | 不删 | — | **跨行原生 copy 可用**（与 cut 不同！） |
| P1 预览区跨块剪切（对照） | 跨块 | ✅ | ✅ | ✅ | 预览区正常（E30 修复有效） |

红矩阵原始读数（`source-cut-RED.json`）：`SUMMARY ok=false failures=6 cases=6`，其中
S2 `domLines=false body=false disk=false`：
```
期望(跨行剪切后) 第2行 = "第2行：AAA-00" + 合并 "C-003 第四行内容。"
实际(原生部分删) 第2行 = "第2行：AAA-00"      ← 只删了首根内的部分，其余内容残留
磁盘 gotBytes=283 / expBytes=213（逐字节不等）
```
⇒ **必须完全接管 cut**：既不能只修 DOM 结构，也不能"让浏览器删、我们再补剪贴板"。

**关于 `Selection.toString()` 的旁证**：跨行选区时它**只返回第一个可编辑根内的文本**
（S2 实测 `"\n"`、S4 实测首行尾部），这正是"多根选区"不可靠的直接证据；
而浏览器自己的 copy 路径另有序列化（能拿全文、但用 CRLF、且**块边界会丢空行**）。

---

## 2. 设计选择（任务要求回答）

**选：接管原生 cut（keydown Ctrl+X → `preventDefault` + 自己写剪贴板 + 自己走源码编辑管线删除）。**

| 方案 | 结论 | 理由 |
|---|---|---|
| **A. 接管 cut**（本实现） | ✅ 采用 | 与预览区 E30 的既有做法一致；改动局限在源码编辑器的 keydown 分支；不动 DOM 结构 ⇒ 行号/假光标/KP 高亮/选区 API 全部无回归面 |
| B. 把 `#editor` 改成单一 contenteditable 让原生可用 | ❌ v0 不采用 | `.-line-content` 的"每行一根"是行号、行高亮、假光标、`#line-N` 定位、KP 范围等大量逻辑的基座；重构回归面不可控，收益只是"省一个事件处理器" |
| C. 只修跨行（单行继续原生） | ❌ 不采用 | 会形成"两种剪贴板语义"（原生 CRLF / 我们 LF），且单行原生在空行/块边界上也有序列化差异 ⇒ **完全接管才没有半接管风险** |

**接管后的不变量（三条硬约束逐条落实）：**
1. **写剪贴板失败 ⇒ 可见报错且不删内容**：先 `await writeClipboardText(text)`，返回 false ⇒
   `setStatusError(T("srcEdit.cutClipboardFailed"))`（底栏红字 + 顶部浮层**双通道**）+ 直接 return，
   **不进入删除**。新增 i18n：`srcEdit.cutClipboardFailed`（zh/en 各 1 键）。
2. **单个撤销单元**：删除前只调一次 `_srcPushBefore()`（并把 `_srcCoalesceAt` 归零），
   DOM 删除是程序化修改（不触发 input 事件）⇒ 撤销栈只多 1 帧；真机 Ctrl+Z **一次**恢复（S1/S2/S5 均验）。
3. **不半接管**：keydown 里 `e.preventDefault()` 先于一切 ⇒ 原生**既不写剪贴板也不删内容**；
   剪贴板由我们写，真机断言的是**精确 LF 文本**（不是 CRLF、不是 sentinel 旧值）。
   复制（Ctrl+C）**保持原生**（真机证明可用，且保留富文本剪贴板能力）⇒ 复制不参与"接管"，无半接管问题。

**剪贴板行尾选择**：写 **LF**（与文档模型/预览区语义一致）。外部应用粘贴由 Windows 处理为换行；
真机断言 `clipboard === 期望文本` 精确相等。复制路径保持原生 CRLF（Windows 惯例），只在"内容"维度断言（归一化比较）。

---

## 3. 改动（3 个文件，可机械复核）

### 3.1 `src/memoria/ui/static/app/js/app.js`（+136/−0）
在 `deleteCrossLineSelection` 之后新增 5 个模块级函数（均为 task-150 私有）：
```
_srcColInLine(node, offset, contentEl)   行内字符偏移（支持 range 端点=元素节点）
_srcLinePlainText(contentEl)             行纯文本（剔除 .-sync-cursor 假光标，与 collectEditorBody 同口径）
_srcSelectionPlan()                      选区 → {kind, loEl/hiEl, loOff/hiOff, loText/hiText, text, range}
_srcApplyCutPlan(plan)                   按计划删 DOM（单行 range.deleteContents+normalize；跨行保留首段+末段、删中间行、重编号、放光标）
_srcCutExecute(plan)                     async：先写剪贴板（失败⇒可见报错+不删）→ _srcPushBefore → 删 → _srcAfterEdit → 光标可见性 → scheduleRenderSync/markDirty
```
并在 `editor.addEventListener("keydown", …)` 顶部新增（在 Ctrl+Z 分支之前）：
```js
if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "x") {
  const cutPlan = _srcSelectionPlan();
  if (!cutPlan) return;          // 无选区：交还原生（不会删任何东西）
  e.preventDefault();            // 完全接管：原生不得再写剪贴板/删内容
  _srcCutExecute(cutPlan).catch((err) => syncLog("srcCut: 异常 " + ((err && err.message) || err)));
  return;
}
```
**未改**：`edit-handler.js`（预览区 cut/copy/E30 逻辑一律不动）、源码区 `paste` 监听、拖拽路径、`_restoreDocTailNL`。

### 3.2 i18n（各 +3 行）
```
zh-CN.js: srcEdit.cutClipboardFailed = "剪切失败：未能写入剪贴板，内容未删除（可重试）"
en.js   : srcEdit.cutClipboardFailed = "Cut failed: could not write to the clipboard — nothing was deleted (you can retry)."
```

---

## 4. 真机证据（红 → 绿，同一探针/同一夹具/同一按键）

工具链（全部落盘，可复跑）：
```
artifacts/agent/verify/todo/source-cut-fixture-gen.py   ← 自建 KB：docs/cut.md（8 行，CRLF）+ docs/second.md
artifacts/agent/verify/todo/source-cut-probe.mjs        ← 7 用例 × 6 判据（CDP 真实按键 + OS 剪贴板读回）
artifacts/agent/verify/todo/source-cut-clipboard.ps1    ← 剪贴板 UTF-8 读回助手（中文已验证）
artifacts/agent/verify/todo/source-cut-run.ps1          ← 临时 KB 副本 + safe-kill 运行器（-FixMode 开关）
```
每个用例都独立验证：① 剪贴板内容（先写 sentinel 证明"本次覆盖"）② 编辑器 DOM 行 ③ `state.doc.body`
④ 保存后**磁盘逐字节** ⑤ Ctrl+Z **一次**恢复 ⑥ 切文件再切回**不回魂**。

### 4.1 改前红矩阵（`source-cut-RED.log` / `source-cut-RED.json`）
`ok=false failures=6`：S1/S3/S4/P1 绿（证明"不是全坏"，判据有判别力）；**S2、S5 红**（跨行剪切部分删除 + 磁盘字节不符）。

### 4.2 改后绿矩阵（`source-cut-after.log` / `source-cut-realapp.json`）
`ok=true failures=0 cases=7`：
```
S1 单行剪切  clipboard=true domLines=true body=true disk=true undo=true noResurrect=true
S2 跨行剪切  selectRange=true clipboard=true domLines=true body=true disk=true undo=true noResurrect=true
S3 单行复制  clipboard=true domLines=true body=true disk=true undo=true noResurrect=true
S4 跨行复制  selectRange=true clipboard=true domLines=true body=true disk=true undo=true noResurrect=true
S5 整行跨行剪切 selectRange=true clipboard=true domLines=true body=true disk=true undo=true noResurrect=true
P1 预览区跨块剪切（对照） clipboard=true previewBodyChanged=true undo=true noResurrect=true
```
- 剪切用例的剪贴板是**精确 LF**（`clipExact`），不是归一化近似 ⇒ 无双写/旧值。
- 磁盘是**逐字节相等**（CRLF 夹具；保存文本模式写 CRLF，与 task-147 登记的行尾风险无关）。

### 4.3 失败路径（构造，`-FixMode` 才跑）
在页面内打桩 **三条写剪贴板通道**（后端 RPC `clipboard_set_text` / `navigator.clipboard.writeText` /
`document.execCommand`）后执行 Ctrl+X：
```
F1 ok=true：contentKeptOnFailure=true  visibleError=true  clipboardStillSentinel=true
visibleErrorRaw = {
  statusInfo: "剪切失败：未能写入剪贴板，内容未删除（可重试）",   statusErrorClass: true,
  flashText:  "剪切失败：未能写入剪贴板，内容未删除（可重试）",   flashErrorCount: 1 }
```
⇒ 用户可见（底栏红字 + 顶部浮层），内容**一个字符都没删**，剪贴板仍是 sentinel（证明没有"半写"）。

### 4.4 判别力自证
临时 `git checkout` 回退到 HEAD 跑同一探针 → `failures=6`（S2/S5 红）；恢复后 → `failures=0`；
恢复后 `git diff --numstat` = `136 0`（无残留/无回退）。

---

## 5. 门禁（第一手实跑）

| 门禁 | 结果 |
|---|---|
| `pytest -q tests` | **1475 passed / 0 failed**（当前基线，不降） |
| `node --check` 全仓非 vendor JS | **66/66 通过**（含 `app.js`、两个 i18n 文件） |
| `i18n_selftest.js` | **FAIL=0** |
| `team_audit.py` | **FAIL=0，机检全绿**（WARN=53 / INFO=24） |
| 12 交互剧本 | **12/12，failed=0**（32.6s） |
| 预览区 cut（P1 对照） | 不回归（同探针绿） |

---

## 6. 边界与披露

- 真机测试**只用 `%TEMP%` 的 KB 副本**（每用例重置 pristine）；未触碰 `docs/example/AAA_Vocab/`、未写用户库。
- 探针启动短命实例（端口 9585，红/绿各一次）；用户 `Package\Memoria.exe`（PID 37620）全程未动、前后 PID 一致；端口已释放。
- 过程披露：判别力自证用过一次"临时 `git checkout` 回退 + 从 `.tmp` 备份恢复"，恢复后已核对 diff=136/0。
- **未改** `edit-handler.js`（预览区 E30 路径零风险）；**未动** E33 拖拽路径；`src/memoria/services/agent/*.py` 的两个改动**不是本轮**（开工前已在工作区），提交时请只取本报告的 3 个文件 + artifacts。
- 本任务不涉及尾换行（task-147 已独立覆盖）；夹具用 CRLF 是为了让"磁盘逐字节"有稳定期望。

---

## 7. 建议后续（Lead/台账决策，不擅自改）

1. **E30 归档条目补注**：范围仅预览区；源码区未覆盖（用户 2026-10-25 复报 → task-150）。
2. 新增源码区剪贴板条目（E35 或新 ID），证据挂本报告；关闭条件已满足（红/绿 + 失败路径 + 撤销 + 不回魂）。
3. 可选（不在本任务范围）：跨行**复制**若要 LF 一致性可同样接管，但会失去富文本剪贴板能力，建议保持现状（真机已证明可用）。
4. 拖拽移动（E33）仍是"只进 DOM 不进源码"风险，建议按其原条目继续。

---

## 8. 产物清单

```
src/memoria/ui/static/app/js/app.js                       ← 修复（+136/−0：_srcCut* 5 函数 + keydown Ctrl+X 分支）
src/memoria/ui/static/app/i18n/zh-CN.js                   ← +3（srcEdit.cutClipboardFailed）
src/memoria/ui/static/app/i18n/en.js                      ← +3（同上 en）
artifacts/agent/verify/todo/source-cut-fixture-gen.py      ← 夹具生成器（CRLF）
artifacts/agent/verify/todo/source-cut-fixture/kb/         ← 夹具 KB
artifacts/agent/verify/todo/source-cut-probe.mjs           ← 真机探针（7 用例 × 6 判据 + 失败注入）
artifacts/agent/verify/todo/source-cut-clipboard.ps1       ← OS 剪贴板读回助手
artifacts/agent/verify/todo/source-cut-run.ps1             ← 运行器（临时 KB + safe-kill + -FixMode）
artifacts/agent/verify/todo/source-cut-RED.log/.json       ← 改前红矩阵（S2/S5 红）
artifacts/agent/verify/todo/source-cut-after.log           ← 改后绿矩阵
artifacts/agent/verify/todo/source-cut-realapp.json        ← 改后绿 JSON（含 F1 失败路径证据）
```
