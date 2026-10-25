# task-147 · R0 数据损坏修复：文件尾 ≥2 换行时保存丢 1 个尾换行

> **风险等级 R0（I4 数据损坏）**。状态：**已修复 + 改前红/改后绿双向证据齐全 + 全门禁绿**（工作区未 commit，等 Lead 统一提交）。
> 前置：`task-144` 已关闭并提交 `a8d5956d`；开工基线 **HEAD=`ff0c374c`**；`app.js` 工作区开工时**无他人未提交改动**；
> `collectEditorBody` / `_restoreDocTailNL` 的 `git diff -U0` **0 命中**（render-perf 预占函数证明已复核）。

---

## 0. 结论（一句话）

`collectEditorBody()` 的 DOM 复算结果**恒等于 canonical 去掉最后一个尾换行**，但旧代码用
`!body.endsWith("\n")` 判断"是否需要补回"——当文件尾是 `\n\n` / `\n\n\n` 时 `body` 仍以 `\n` 结尾，
被误判成"已有尾换行"而**少补 1 位**；`syncToDisk()` 用同一个函数 ⇒ **每篇这样的文件第一次编辑并保存后，
磁盘永久少 1 个尾换行**。修复 = 只改 `collectEditorBody` 一处，按真源标记**无条件补 1 位**。

---

## 1. 改动（单点，`git diff -U0` 只有一个 hunk）

```
git diff --numstat -- src/memoria/ui/static/app/js/app.js   →  7  1
git diff -U0    -- src/memoria/ui/static/app/js/app.js   →  @@ -129 +129,7 @@   ← 唯一 hunk
```

`collectEditorBody()` 尾部：

```diff
     }).join("\n");
-    const out = _restoreDocTailNL(body);
+    // task-147（R0）：DOM 复算 `body` 恒等于 canonical 去掉最后一个尾换行
+    //   （后端 `lines = body.splitlines()` 恰好丢掉末尾那一项），所以"是否补 1 位"只看真源标记，
+    //   不能再用 `!b.endsWith("\n")` —— 文件尾为 `\n\n` / `\n\n\n` 时 body 仍以 `\n` 结尾，
+    //   会被误判成"已有尾换行"而少补 1 位 ⇒ 保存即永久丢 1 字节（R-01 未覆盖边界）。
+    //   ⚠️ 不要合并 `_restoreDocTailNL`：它的另外两处调用（快照恢复）输入是**完整 body**，
+    //   那里"已带尾换行就跳过"是对的，改成无条件补会**多**一个换行。
+    const out = _docEndsWithNL() ? body + "\n" : body;
```

**为什么不改 `_restoreDocTailNL` 本身**：它还有两个调用点（现 `app.js:7703` / `11831`，
`const _snapBody = _restoreDocTailNL(snap.body)`）输入是**完整 body**（快照里存的正文），
那里 `!b.endsWith("\n")` 是正确判据；一起改会在每次撤销/重做时**多**一个换行。

**等价性依据**（task-147 记录、Lead 已独立验证）：
设 `B` = 后端 `load_document` 的 `body`（LF 归一），`L = B.splitlines()`，`R = "\n".join(L)`：
```
R = B[:-1]（当 B 以 \n 结尾）  ⇒  R.endswith("\n")  ⟺  B.endswith("\n\n")
⇒ 正确回补 = (B 以 \n 结尾 ? R + "\n" : R)      ← 与字符判据无关
```

---

## 2. 证据①：**改前红矩阵**（先证红，再改）

### 2.1 白盒单测（真实源码抽取 + `node:vm` + 最小 DOM 桩，**逐字节判据**）

测试：`scripts/benchmark/maintenance/tail_newline_roundtrip_test.js`（沿用 `edit_cut_undo_test.js` 手法：
按花括号配平从 `app.js` 抽取 `_docEndsWithNL` / `_restoreDocTailNL` / `collectEditorBody` **真实源码**）。
日志：`doc-body-tail-newline-fix-RED.log`

| 尾形态 | 插入 | 删除 | 拆行 |
|---|---|---|---|
| 无 | PASS 66/66 | PASS 62/62 | PASS 66/66 |
| `\n` | PASS 67/67 | PASS 63/63 | PASS 67/67 |
| **`\n\n`** | **FAIL 67/68** | **FAIL 63/64** | **FAIL 67/68** |
| **`\n\n\n`** | **FAIL 68/69** | **FAIL 64/65** | **FAIL 68/69** |

⇒ **6 FAIL / 6 PASS**：红只出现在"尾 ≥2 换行"边界（**绿的存在证明不是全坏**，即判据有判别力）。
失败明细均为**尾部少 1 字节**，例如：
```
尾=\n\n × insert：首个差异字节#67 got(67)=" …123456\n" exp(68)="…123456\n\n"
                  hex got[35360a] exp[35360a0a]
```
**并且**单测额外记录到 **4 例"净长度巧合"**（`blank×insert`、`blank×split`、`blank2×insert`、`blank2×split`）：
`len(got) == len(编辑前 canonical)` 但字节不同 ⇒ 正是 task-141 里"长度判据会放过、字节判据抓住"的现场复现。

### 2.2 真机（真实应用 + WebView2，**保存后比对磁盘字节**）

夹具：`doc-body-tail-newline-fixture-gen.py` 生成 4 篇独立文档（正文相同，仅尾形态不同，**CRLF**）。
探针：`doc-body-tail-newline-probe.mjs`（4 篇 × 3 编辑 + 重开；期望值**独立计算**，不从 DOM 回读）。
改前日志：`doc-body-tail-newline-realapp-RED.log`，JSON：`doc-body-tail-newline-realapp-RED.json`

```
SUMMARY: ok=false  failures=14  docs=4  steps=12
tail-none.md   tail=""      ok=true    ← 对照（改前也绿）
tail-nl.md     tail="\n"    ok=true    ← 对照（改前也绿）
tail-blank.md  tail="\n\n"  ok=false   ← 3 编辑 + reopen 全红
tail-blank2.md tail="\n\n\n" ok=false  ← 3 编辑 + reopen 全红
```
红的具体读数（逐字节，不是长度）：
```
tail-blank  × insert：磁盘 got=314B(tail 303038e380820d0a)  exp=316B(tail 38e380820d0a0d0a)
                      state.doc.body got(…"EE-008。\n")  exp(…"E-008。\n\n")   memoryBodyEqual=false
tail-blank2 × insert：磁盘 got=316B(38e380820d0a0d0a)      exp=318B(80820d0a0d0a0d0a)
```
⇒ 改前**真机**：磁盘确实少 1 个 CRLF、内存真源少 1 个 `\n`；两篇对照文档（无尾换行、单尾换行）全绿。

---

## 3. 证据②：**改后逐字节比对**（保存 → 重开）

### 3.1 白盒单测：**12/12 PASS**（`doc-body-tail-newline-fix-GREEN.log`）

| 尾形态 | 插入 | 删除 | 拆行 |
|---|---|---|---|
| 无 | PASS 66/66 | PASS 62/62 | PASS 66/66 |
| `\n` | PASS 67/67 | PASS 63/63 | PASS 67/67 |
| `\n\n` | **PASS 68/68** | **PASS 64/64** | **PASS 68/68** |
| `\n\n\n` | **PASS 69/69** | **PASS 65/65** | **PASS 69/69** |

`总组合: 12  PASS: 12  FAIL: 0`，且"净长度巧合"用例数 = **0**。

### 3.2 真机：**4 篇 × 3 编辑 + 重开 = 12/12 逐字节相等**（`doc-body-tail-newline-realapp.log` / `.json`）

| 文档 | 尾 | insert 后磁盘 | delete 后 | split 后 | 重开后 |
|---|---|---|---|---|---|
| tail-none | 无 | 312B 相等 | 311B 相等 | 313B 相等 | body+磁盘保持 313B |
| tail-nl | `\n` | 314B 相等（tail `…0d0a`） | 313B | 315B | 315B 保持 |
| **tail-blank** | `\n\n` | **316B 相等（tail `…0d0a0d0a`）** | **315B** | **317B** | **317B 保持** |
| **tail-blank2** | `\n\n\n` | **318B 相等（tail `…0d0a0d0a0d0a`）** | **317B** | **319B** | **319B 保持** |

`SUMMARY: ok=true failures=0 docs=4 steps=12`。
每一步都同时满足：① 编辑器 DOM 行 == 模型；② **磁盘字节 == 期望字节**；③ `state.doc.body` == 期望 canonical；
④ 重开（`openFile` 同文件）后 body 与磁盘字节仍保持。

### 3.3 判别力自证（改前红 / 改后绿，同一探针、同一夹具）

为证明"真机探针能抓住这个 bug"，**临时把 `collectEditorBody` 回退到 HEAD 版**跑真机，再恢复修复：

```
回退后：unit exit=1；真机 SUMMARY ok=false failures=14（blank/blank2 全红，两对照全绿）→ exit=1
恢复后：unit exit=0；真机 SUMMARY ok=true  failures=0                        → exit=0
恢复证明：git diff --numstat = 7  1（单点 hunk 仍在，且未误留回退）
```
并且 `tests/test_tail_newline_roundtrip.py`（pytest 包装）在回退版上**实测 FAILED**、修复版上 **1 passed**
⇒ 该守卫不是"永远绿"的装饰。

### 3.4 任务本身的方法论教训（本轮新增）

**我写的第一版单测是假绿**：夹具用 `bodyFromLines(lines, tailNL)` 构造 canonical，该函数只会补 **1 个** `\n`
⇒ `\n\n` / `\n\n\n` 两个用例被悄悄退化成 `\n`，12 组合全绿（测试没有判别力）。
修法：canonical 直接 = 基础行 + **该形态的字面尾部**；`tailNL` 只表达"是否有尾换行"。
**教训**：Lead 让审自己的测试 —— 用同一把尺子："**如果缺陷真的存在，我这个判据会不会恰好看不见它？**"
（第一版正是"看不见"；修正后红/绿分明。已与 `doc-body-staleness-analysis.md` §10 的判据纪律对齐。）

---

## 4. 证据③：**未动快照两处**（`git diff -U0` 行号范围）

```
$ git diff -U0 -- src/memoria/ui/static/app/js/app.js
@@ -129 +129,7 @@
```
唯一 hunk 只覆盖 `collectEditorBody` 的 `out` 行（原 129 → 新 129-135）。
快照两处仍在、内容未变（行号因 +6 行注释而顺移）：

```
7703:    const _snapBody = _restoreDocTailNL(snap.body);   ← 原 7697，内容未改
11831:   var _snapBody = _restoreDocTailNL(snap.body);     ← 原 11825，内容未改
```
且 `_restoreDocTailNL` 函数体本身**零 diff**（`git diff` 不含它）。

---

## 5. 门禁（第一手实跑；HEAD=`ff0c374c` + 本修复）

| 门禁 | 结果 |
|---|---|
| 全量 pytest | **1475 passed / 0 failed**（基线 1474 + 新增 `test_tail_newline_roundtrip.py` 1 条；无 regress） |
| node --check | 全仓非 vendor JS **66/66** 通过；新增 `tail_newline_roundtrip_test.js` 亦通过 |
| i18n_selftest | **FAIL 行数 0** |
| team_audit | **FAIL=0，机检全绿**（WARN=54 / INFO=24） |
| 12 交互剧本 | **12/12，failed=0**（24.7s） |
| **task-141 滚动回归** | **不退化**：huge `57914→57922`（Δ8，heldWithinOneBlock=true，restores=1）；medium `2180→2180`（Δ0）——与修复前逐值相同 |

---

## 6. 相邻风险（**只报不改**，按任务边界）

**LF-only 文件保存后可能变 CRLF**（与本 bug 独立）：`save_document()` 用 `compose_markdown(body, fm)` 后以
**文本模式** `open(tmp, "w")` 写（`src/memoria/services/document.py:319-349`），Windows 下会把 `\n` 译为 `\r\n`；
而读入 `open(..., "r")` 会把 CRLF 归一为 LF。⇒ **LF 文件经"编辑+保存"会被统一成 CRLF**（字节变化，非内容变化）。
本夹具刻意用 CRLF 以隔离该因素；**本轮未修、未纳入判据**，建议单开条目（定性、影响面、修复方案：`newline=""` 或保留原行尾风格）。

---

## 7. 边界与披露

- 真机测试**只用 `%TEMP%` 的 KB 副本**（每用例重置为 pristine）；**未触碰** `docs/example/AAA_Vocab/`、未写用户 KB。
- 真机探针启动了两个短命实例（端口 9583；改前红/改后绿各一次，其中含一次"临时回退"再恢复）；
  用户 `Package\Memoria.exe` 全程未运行（前后 PID 快照均为空、一致）；端口均释放；safe-kill 只杀自己 Start-Process 的 PID。
- 改前红证据有**两类**：① 白盒单测 6/12 红（真实源码抽取）；② 真机 14 项红（磁盘/内存均少 1 字节）。
  另：task-141 的 `doc-body-staleness-runtime.json` + 文件字节对比（219740→219739）是**更早的独立真机红**，可并读。
- 本轮改动：`src/memoria/ui/static/app/js/app.js`（+7/−1 单点 hunk）+ 新增
  `scripts/benchmark/maintenance/tail_newline_roundtrip_test.js`、`tests/test_tail_newline_roundtrip.py`。
  其余全部是 `artifacts/agent/verify/todo/doc-body-tail-newline-*` 证据文件。
- **不 commit**（按纪律）。

---

## 8. 建议后续（Lead 决策，不擅自改台账）

1. `risk-management.md` **R-01** 建议从"已修"改为"**已修（含尾 ≥2 换行边界，task-147）**"，关闭依据挂本报告；
   §6 的 LF→CRLF 相邻风险单开登记（新发现，不搭车改检查项）。
2. 若希望把"逐字节判据"变成**机制**而不是记忆，可考虑把
   `scripts/benchmark/maintenance/tail_newline_roundtrip_test.js` 的矩阵扩到"撤销/重做"路径（`_srcApplySnapshot`）——
   本轮已在 diff 上证明那两处未动、语义正确，但**未真机回环**（与 R-01 残余登记一致）。

---

## 9. 产物清单

```
src/memoria/ui/static/app/js/app.js                                    ← 修复（+7/−1，单 hunk）
scripts/benchmark/maintenance/tail_newline_roundtrip_test.js           ← 白盒矩阵（12 组合，逐字节）
tests/test_tail_newline_roundtrip.py                                   ← pytest 守卫（改前实测会红）
artifacts/agent/verify/todo/doc-body-tail-newline-fixture-gen.py       ← 4 尾形态夹具生成器
artifacts/agent/verify/todo/doc-body-tail-newline-fixture/kb/          ← 夹具 KB（4 文档，CRLF）
artifacts/agent/verify/todo/doc-body-tail-newline-probe.mjs            ← 真机逐字节探针（保存→重开）
artifacts/agent/verify/todo/doc-body-tail-newline-run.ps1              ← 真机运行器（临时 KB 副本 + safe-kill）
artifacts/agent/verify/todo/doc-body-tail-newline-fix-RED.log          ← 白盒改前红矩阵
artifacts/agent/verify/todo/doc-body-tail-newline-fix-GREEN.log        ← 白盒改后绿矩阵
artifacts/agent/verify/todo/doc-body-tail-newline-realapp-RED.log/.json← 真机改前红（14 failures）
artifacts/agent/verify/todo/doc-body-tail-newline-realapp.log/.json    ← 真机改后绿（12/12 逐字节 + 重开）
artifacts/agent/verify/todo/doc-body-tail-newline-task141-regression.log ← task-141 滚动回归
```
