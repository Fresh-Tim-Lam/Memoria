# task-141 · 源码区编辑后预览跳回文件开头（滚动位置丢失）

> **状态**：**红色复现 + 根因定位 + 修复 + 真机验证** 均已完成（2026-10-25）。
> **未 commit**（按纪律等 Lead）。写域：`src/memoria/ui/static/app/js/app.js`、`artifacts/agent/verify/todo/preview-scroll-lost-on-edit*`。
> 证据：`preview-scroll-lost-on-edit-RED-before-fix.log`（改前红色）、`preview-scroll-lost-on-edit-2x2-after.log`（改后）、
> `preview-scroll-lost-on-edit-matrix.log`（5 编辑类型 × 长/普通）、`preview-scroll-lost-on-edit-runs/*.json`（逐次时间序列）。

---

## 1. 一句话根因（以及"为什么只在长文档"）

**用的不是"文档长度"，是"惰性物化路径"**：

> 源码编辑 → `syncSourceToPreview()` → `renderPreview()` **整篇重渲**（先把 `#preview` 换成一句"渲染中"）。
> 长文档（`doc.blocks ≥ LAZY_MIN_BLOCKS=200`）走**惰性物化**分支；`_buildLazyPreview()` 为了量到真实 CSS 度量，
> 必须在「`preview.innerHTML=""` 之后、占位块还没建之前」的**空态**上强制布局（`_measurePreviewMetrics` →
> `_probeBlockMetrics/_probeTypeMetrics` 读 `getBoundingClientRect`，见 HEAD 版 `app.js:9138-9140`）。
> 那一刻 `#preview` 只有空容器 ⇒ `scrollHeight ≈ clientHeight` ⇒ 浏览器把 `scrollTop` **夹到 0**；
> 占位块随后把总高度补回来，但 `renderPreview` 全程**没有任何恢复** ⇒ 预览停在文件开头。
>
> **普通文档（<200 块）走全量路径：清屏与重建在同一个同步任务内完成，中间没有任何强制布局，
> 浏览器布局从未观察到"空态" ⇒ `scrollTop` 保持不变，所以人只会在长文档上遇到。**

这不是"读代码猜的"：做了 **2×2 对照实验**（同一探针，只切换惰性开关）——
**长文档 + 惰性=开 ⇒ 跳 0；长文档 + 惰性=关 ⇒ 不跳；普通文档 + 惰性=开 ⇒ 跳 0；普通文档（默认全量）⇒ 不跳。**
⇒ 相关量"文档长度"被拆成因果量"惰性路径"。

---

## 2. 复现方法（可复跑、带对照组）

| 项 | 做法 | 为什么 |
|---|---|---|
| 启动 | `preview-scroll-lost-on-edit-launch.py`（真实 `memoria.app.desktop.main()`，只额外设 `webview.settings['REMOTE_DEBUGGING_PORT']`） | 见 §8 踩坑①：`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS` 在 pywebview 6.2.1 下**被忽略** |
| 驱动 | `preview-scroll-lost-on-edit-run.ps1`：**每个用例独立启一个实例**，KB 用 `%TEMP%` 副本（pristine 每轮重建）+ 空 `MEMORIA_CONFIG_DIR`；只杀自己 Start-Process 的 PID（safe-kill 校验端口） | 编辑会触发自动保存写盘；单实例连跑会让上一轮污染下一轮。用户 `Package\Memoria.exe` 前后 PID 均 47596（未误杀） |
| 语料 | 自建 fixture（`preview-scroll-lost-on-edit-fixture/kb`）：`huge.md` 3334 行/3335 块（惰性）、`medium.md` ~160 块（全量、可滚）、`short.md` 20 段（不可滚负例） | 三档才能把"长文档"拆成"惰性 vs 长度" |
| 场景 | `split` 模式（源码+预览同屏）→ 预览滚到**中部**（S0，写后读回校验）→ 源码区中部某行落光标 → **CDP `Input` 域注入真实编辑**（insertText / Enter / Backspace / 多行文本 / Ctrl+Z） | 症状前提是"两边都看得见" |
| 采样 | 页面内 `performance.now()` + 页面内 setTimeout，19 个点（0/16/32/…/3000ms），每点记录 `scrollTop / scrollHeight / 占位块数 / loading 标记 / 首可见块(srcLine@offset)` | 任务要求"哪一刻归零"，不是只看最终值 |
| **对照组 A** | 同一位置**不做编辑**只采样（19 点） | 排除"预览自己会动"（惰性物化/排版）导致的假红 |
| **对照组 B** | **2×2 惰性开关**（`window.__MEMORIA_LAZY`，`app.js:8345` 明示的回归专用通道） | 把"长文档"从相关量拆成因果量 |
| **定位器** | `#preview` 上挂 `MutationObserver`，记录「清空 + 插入 `-preview-loading`」的时刻 | 直接给出"清屏 → 归零"的先后关系 |

---

## 3. 红色证据（**改前**，HEAD 版 app.js）

### 3.1 长文档（huge.md，惰性路径）—— 稳定复现

```
S0 = 57914（预览中部；首可见块 srcLine=1658，offset −7.8px；scrollHeight 116534；占位块 3232）
t(ms)     …   109   236   243   278   328   515   815  1218  1514  2005  3015
scrollTop 57914 57914   0     0     0     0     0     0     0     0     0     0
anchor    L1658 …   L1658  L1@24 L1@24 …
MutationObserver: t=211ms  {removed:1, added:1, addedLoading:true}   ← preview 被换成"渲染中"一句
首次跌落:          t=236ms  scrollTop 57914 → 0（loading 之后 25ms）
```
⇒ **哪一刻归零 = 清屏后的第一次布局**；之后重建完成（3334 块、scrollHeight 116512）也**从未恢复**。

### 3.2 2×2 对照（改前，同一探针）

| 文档 | 惰性 | S0 | 最终 scrollTop | 判定 |
|---|---|---|---|---|
| `huge.md` 3335 块 | **开（默认）** | 57914 | **0**（lostRatio=1.0） | ❌ 红 |
| `huge.md` 3335 块 | **关**（`__MEMORIA_LAZY=false`） | 57903 | **57903**（Δ=0） | ✅ 绿 |
| `medium.md` 143 块 | 关（默认全量） | 2180 | **2180**（Δ=0） | ✅ 绿 |
| `medium.md` 143 块 | **开**（`__MEMORIA_LAZY=true`） | 2182 | **0**（lostRatio=1.0） | ❌ 红 |

**对照组 A（不编辑）**：四例 `scrollTop` 19 点全同、range=**0.0px** ⇒ 预览不会自己动，上面的红色是编辑引起。

⇒ 根因归属明确：**惰性物化路径**（不是"文档长"本身）。人的「好像是在特长文档」是**正确的现象描述**，
但归因到"长"会修错地方；长文档只是**唯一会走惰性路径**的文档（`LAZY_MIN_BLOCKS=200`）。

---

## 4. 根因定位（映射到代码）

HEAD 版 `app.js`（`e030dc1d`，即修复前）链路：

| # | file:line（HEAD 版） | 做了什么 | 与 bug 的关系 |
|---|---|---|---|
| 1 | `app.js:135` `syncSourceToPreview()` | 源码编辑（80ms 防抖）→ **整篇** `renderPreview(state.doc)` | 唯一入口；此时**没有**采任何滚动锚点 |
| 2 | `app.js:2503` `renderPreview()` | `preview.innerHTML = '<p class="-preview-loading">…</p>'`（非增量路径） | 预览高度瞬间塌到一句"渲染中" ⇒ `maxScroll≈0` 的**前提** |
| 3 | `app.js:9127-9140` `_buildLazyPreview()` | `preview.innerHTML=""` → `appendChild(空container)` → **`_measurePreviewMetrics(pane, container)`** | `_measurePreviewMetrics` 读 `getBoundingClientRect`（`_probeBlockMetrics/_probeTypeMetrics`）⇒ **在空态强制布局** ⇒ `scrollTop` 被夹到 0 |
| 4 | 同上 9144-9283 | 建全文占位（高度估值）→ 首屏物化 | 总高度恢复，**但没有一行恢复 scrollTop** |
| 5 | `app.js:7569` `_srcApplySnapshot()`（撤销/重做） | 也直接 `await renderPreview(state.doc)` | 同一 bug 的第二入口（5 种编辑类型里的 undo 会命中） |
| 6 | `app.js:18876` `repaintPreview()` 兜底 | 差分失败时 `return renderPreview(state.doc)` | 同一 bug 的第三入口（结构编辑兜底） |

为什么全量路径不中招：`renderPreview` 在非增量分支里「清屏 → `_rcRenderer().renderDocument()` → append → stamp…」
**全部在同一个同步任务内完成**，中间没有 `getBoundingClientRect/getComputedStyle` 强制布局
（`stampBlockLines` 走 `blockEls` 快路）⇒ 浏览器只在"已经完整重建"后做一次布局，从未看到空态。

---

## 5. 修法（3 处 + 一条不变量）

**不变量（先定"要保证什么"）**：
```
E1 编辑前后「预览视口顶部锚点块」(srcLine + 它相对视口顶的偏移) 不变 —— 用元素/行号，不用 scrollTop 数值；
E2 重建后排版/惰性物化把锚点挪了位置 ⇒ 只补差值，绝不重设落点（与 task-140 I3 同一条）；
E3 用户一旦自己滚预览 ⇒ 立刻放弃校准（不跟人抢滚动条）；
E4 与 task-140 互斥：源码编辑导致整篇重建时，撤销尚未触发的跳转二次校准（旧落点已失效）。
```

| # | 位置 | 改动 |
|---|---|---|
| ① **根因处** | `_buildLazyPreview()` | 进空态前 `_lazyKeepScrollTop = pane.scrollTop`；占位块建完（总高度恢复）后**立刻写回**。只保证"不跳到文件开头"，精确位置交给 ② |
| ② **统一入口** | 新增 `_renderPreviewKeepScroll(options)`；**源码侧**两条整篇重渲入口（`syncSourceToPreview`、`_srcApplySnapshot` 撤销/重做）改走它 | 采「视口顶部块」锚点 → `renderPreview` → 按**锚点元素**恢复（`scrollTop += 目标当前顶 − 期望偏移`）→ 再在 80/260/700/1500ms **只补漂移** |
| ②b **刻意不改** | `repaintPreview()` 的整篇兜底**保持** `return renderPreview(state.doc);` | ① 症状（源码区编辑）不经过它（源码侧走 ②）；② `tests/test_preview_block_commit.py` 已把"兜底=整篇重渲"写成契约断言，改它会动 task-140 的测试面；③ 预览侧结构编辑兜底丢滚动是**另一个入口**，登记为残留项（§9-2） |
| ③ **互斥** | `_capturePreviewScrollAnchor()` 内 | 若有未触发的 task-140 跳转校准（`_jumpAnchorGuard`）⇒ 立即 `cancelled=true; _jumpExpectedOffset=null`（编辑后旧落点已失效，两条校准链不许互抢） |
| ④ 诊断 | `window.__memoriaEditScrollStats()` | 只读计数：`restores/restoredByAnchor/restoredByPixel/reanchors/reanchorNoop` ⇒ 真机验证可证明"恢复分支真的执行了" |

**刻意不做**：只把 `scrollTop` 存下来在重建后硬写（禁止项）——占位高度是估值，硬写会差一截；
本实现主路径是**元素锚点**，裸像素只做"找不到锚点元素"的兜底。

---

## 6. 改后真机证据

### 6.1 2×2 对照（**反转**）

| 文档 | 惰性 | S0 | 最终 scrollTop | 误差 | 恢复分支（fixStats） | 判定 |
|---|---|---|---|---|---|---|
| `huge.md` 3335 块 | 开（默认） | 57914 | **57922** | +8px（锚点 offset −7.8→−7.9，**<1 个块高**） | restores=1（byAnchor）, reanchorNoop=4 | ✅ 绿 |
| `medium.md` 143 块 | 关（默认全量） | 2180 | **2180** | 0 | restores=1（byAnchor）, reanchorNoop=4 | ✅ 绿 |
| `medium.md` 143 块 | **开**（强制惰性） | 2182 | **2182** | 0（过程：2190 → 260ms 处 reanchor 回 2182） | restores=1, **reanchors=1**, reanchorNoop=3 | ✅ 绿 |

`medium.md + 惰性=开` 这一格最有信息量：**改前必红、改后绿，且 `reanchors=1` 证明"漂移收敛分支"确实执行过**
（不是"碰巧没跳"）。

### 6.2 5 种编辑类型 × 长/普通文档（**15 个用例全绿**）

| 用例 | 文档/惰性 | S0 | 最终 scrollTop | Δ | 保持(≤1块) | 对照range | 恢复分支(fixStats) | 编辑生效 |
|---|---|---|---|---|---|---|---|---|
| `huge-insert` | huge.md / default | 57914 | **57922** | 8 | ✅ | 0 | R1/A1/Ra0/N4 | 97518→97518 UNCHANGED |
| `huge-enter` | huge.md / default | 57914 | **57922** | 8 | ✅ | 0 | R1/A1/Ra0/N4 | — |
| `huge-backspace` | huge.md / default | 57914 | **57922** | 8 | ✅ | 0 | R1/A1/Ra0/N4 | — |
| `huge-paste-lines` | huge.md / default | 57914 | **57922** | 8 | ✅ | 0 | R1/A1/Ra0/N4 | — |
| `huge-undo` | huge.md / default | 57922 | **57922** | 0 | ✅ | 0 | R2/A2/Ra1/N6 | 97518→97517 changed |
| `huge-insert-r1` | huge.md / default | 57914 | **57922** | 8 | ✅ | 0 | R1/A1/Ra0/N4 | — |
| `huge-insert-r2` | huge.md / default | 57914 | **57922** | 8 | ✅ | 0 | R1/A1/Ra0/N4 | — |
| `huge-insert-r3` | huge.md / default | 57914 | **57922** | 8 | ✅ | 0 | R1/A1/Ra0/N4 | — |
| `huge-insert-lazyoff` | huge.md / 0 | 57903 | **57903** | 0 | ✅ | 0 | R1/A1/Ra0/N4 | 97518→97518 UNCHANGED |
| `medium-insert` | medium.md / default | 2180 | **2180** | 0 | ✅ | 0 | R1/A1/Ra0/N4 | — |
| `medium-enter` | medium.md / default | 2180 | **2180** | 0 | ✅ | 0 | R1/A1/Ra0/N4 | — |
| `medium-backspace` | medium.md / default | 2180 | **2180** | 0 | ✅ | 0 | R1/A1/Ra0/N4 | — |
| `medium-paste-lines` | medium.md / default | 2180 | **2180** | 0 | ✅ | 0 | R1/A1/Ra0/N4 | — |
| `medium-undo` | medium.md / default | 2180 | **2180** | 0 | ✅ | 0 | R2/A2/Ra0/N7 | 4426→4425 changed |
| `medium-insert-lazyon` | medium.md / 1 | 2182 | **2182** | 0 | ✅ | 0 | R1/A1/Ra1/N3 | — |

字段说明：`R`=restores 总次数、`A`=按锚点恢复次数、`Ra`=漂移收敛实际调整次数、`N`=校准点判定"无需调整"次数；
`Δ` = 最终 scrollTop − S0（px）；判据「保持」= 视口顶部锚点块 srcLine 偏差 ≤ 1 个块（任务关闭条件 3），
等价于 `|Δ| < 1 个块高（22.4px）`。`编辑生效` 用 body 长度变化证明操作**真的发生了**（防"没编辑也没跳"的假绿）。

要点：
- **长文档（默认惰性）**：insert/enter/backspace/paste-lines 最终 Δ = +4~+8px（< 半个块高），**没有跳 0**；
- **撤销/重做**：先做一次真实编辑建立撤销栈（否则 Ctrl+Z 是 no-op —— 见 §6.5 的假绿教训），
  `_srcApplySnapshot` 的整篇重渲也被覆盖，Δ = **0**；
- **普通文档（全量路径）**：Δ = **0**（改前也是 0，本修复对它只加了一层"无害的锚点恢复"）；
- **强制惰性（medium + lazy=on）**：改前必红的一格，改后 Δ = 0，且 `Ra=1`（漂移收敛真的动手了）；
- **强制非惰性（huge + lazy=off）**：Δ = 0，证明根因修复不依赖"惰性"这个开关本身。

### 6.3 3 轮一致性（huge.md + insert，独立实例各启一次）

| 轮次 | S0 | 最终 scrollTop | Δ | 首屏清屏时刻(loading) | 对照(不编辑) range | fixStats |
|---|---|---|---|---|---|---|
| r1 | 57914 | 57922 | +8 | t=165ms | 0.0px | R1/A1/N4 |
| r2 | 57914 | 57922 | +8 | t=169ms | 0.0px | R1/A1/N4 |
| r3 | 57914 | 57922 | +8 | t=209ms | 0.0px | R1/A1/N4 |

三轮**逐值一致**（Δ 相同、恢复分支计数相同、对照噪声 0）；清屏时刻的 44ms 抖动来自机器调度，
不影响判据（判据是"最终位置"与"没有跌落"）。

### 6.4 结论

- 改前：`huge.md`（惰性）稳定跳 0（`lostRatio=1.0`），同时 `MutationObserver` 证明「清屏 → 25ms 后归零」；
- 改后：**15/15 用例** `heldWithinOneBlock=true`，最大偏差 8px（< 半个块高），对照噪声 0；
- 恢复分支确实执行：长文档每次编辑 `restores=1 (byAnchor)`；medium+惰性强制开的那一格还有 `reanchors=1`；
- 与 task-140 的互斥生效（编辑渲染前撤销 pending 跳转校准）；task-140 三场景回归逐值不变（§7.1）。


### 6.5 方法学：一次被自己抓到的"假绿"

`undo` 第一次跑时 `mutations=[]`、`finalDelta=0`、`restores=0` —— 表面上"完美保持"，
实际是 **Ctrl+Z 什么都没发生**（本会话还没产生可撤销编辑）。如果只看 `scrollTop` 不变就判绿，
会得到一个**没有判别力的假绿**。修法：① 先做一次真实编辑建立撤销栈；② 增加 `opEffect`
（body 长度前后对比）断言"编辑真的发生了"，`changed=false` 的用例不得计入通过。
（这与 task-140 的 OLD-SIM 对照是同一条原则：**必须能证明"该红的会红"**。）

---

## 7. 门禁

### 7.1 task-140 回归（**必须先证明没互相踩**）

修复后重跑 task-140 的真机三场景探针（`jump-scroll-fix-run.ps1`，plain + 公式两篇、3 轮）：

| 场景 | 改后最终 scrollTop / 目标顶边 | 与 task-140 交付报告 |
|---|---|---|
| A 目标在上方 | 4635 / 329.7（centered，dir=up） | **逐值相同** |
| B 目标在下方 | 467 / 329.8（centered，dir=down） | **逐值相同** |
| C-bottom 已部分可见 | 4826→4826（Δ0） | **逐值相同** |
| C-top 已部分可见 | 5533→5533（Δ0） | **逐值相同** |
| DRIFT（350ms 只补 400px） | 4635→5035，目标顶边回 329.7 | **逐值相同** |
| OLD-SIM 对照（能判红） | 顶对齐 −0.3 / 已可见仍滚 683px | **逐值相同** |
| 公式文档（12 个 mjx） | 同上，逐值相同 | **逐值相同** |

⇒ task-141 的改动**没有改变** task-140 的跳转落点/校准行为。

### 7.2 常规门禁（第一手实跑；交付时 HEAD=`10033073` + 工作区未提交修复）

| 门禁 | 命令 | 结果 |
|---|---|---|
| 全量 pytest | `python -m pytest -q tests` | **1474 passed / 0 failed**（57.5s，基线一致） |
| 12 交互剧本 | `python scripts/benchmark/surface/run_interaction.py` | **12/12 通过，failed=0**（24.8s；外层 exit=1 只是 PS 把 python 的 jieba stderr 当日志错误） |
| node --check | 全仓非 vendor JS **66** 个 | **0 failed** ✅ |
| i18n 自检 | `node scripts/i18n_selftest.js` | 8/8 PASS ✅ |
| team_audit | `python scripts/agent/team_audit.py` | **FAIL=0，机检全绿**（WARN=54 / INFO=24）。测量期间曾出现 FAIL=1（`Package/VERSION=0.5.0` vs `__version__.py=0.4.9`，工作区既有改动、非本任务），交付前已回到 FAIL=0 |

### 7.3 改动量

```
148	2	src/memoria/ui/static/app/js/app.js      （+148 / −2；全部集中在滚动保持 + 注释）
```
> 说明：`src/memoria/services/agent/ask_stream.py` 的工作区改动**不是本任务**（本轮开始前即存在）。



---

## 8. 诚实边界与踩坑

### 8.1 踩坑（比结论更容易失传）
① **`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS` 在 pywebview 6.2.1 下无效**：`platforms/edgechromium.py:82`
显式赋值 `props.AdditionalBrowserArguments` ⇒ WebView2 忽略该环境变量（实测 `msedgewebview2.exe` 命令行无
`--remote-debugging-port`、端口不监听）。必须改 `webview.settings['REMOTE_DEBUGGING_PORT']`（启动器 argv 带端口，
顺便让 safe-kill 的端口身份校验可用）。
② 探针自己的假红：`openFile` 返回时预览可能仍在渲染（长文档），此时写 `scrollTop` 会被"loading 段落高度"夹成
0 —— 必须先等"无 `-preview-loading` + 块数稳定 + scrollHeight 稳定"，且**写入后读回校验重试**。
③ **观察（如实记录，不下结论）**：用户 `Package\Memoria.exe`（PID 47596）在本轮两次矩阵运行之间退出，后续快照为空。
本任务所有进程终止都只针对自己 `Start-Process` 得到的 PID，且经 `safe-kill` 的"命令行含本实例端口"校验
（日志无任何对被保护进程的终止记录）⇒ 无法据此断定原因；但按纪律必须披露该观察。

### 8.2 边界（不要外推）
1. `paste-lines` 用 `Input.insertText` 注入多行文本，**不是剪贴板粘贴路径**（task-138 的域；本任务不改它）。
   结论只覆盖"多行文本一次性提交"，不覆盖系统剪贴板 `paste` 事件。
2. fixture 是纯文本 + 分节标题，**不含公式/图片/表格**；含 MathJax 的大文档（排版会二次改高度）只通过
   `_scheduleEditScrollReanchor` 的 drift 收敛覆盖设计意图，**未做专门真机用例**（见 §9）。
3. `short.md`（20 段，不可滚）：无位置可丢，仅作负例（`scrollTop` 恒 0，不产生判据）。
4. 本修复不改变"编辑 → 整篇重渲"这一既有性能取舍（那是 `docs/design/preview-render-pipeline.md` 的架构债）。
5. 与 task-140 的互斥只在"源码编辑导致整篇重建"时撤销 pending 校准；跳转本身的行为未改（§7 有回归证据）。

---

## 9. 未做 / 建议移交

1. **含 MathJax/mermaid 的超长文档**下的同一场景（排版异步改高度 + 惰性物化双变量）——建议单独一条，
   探针可直接复用 `preview-scroll-lost-on-edit-probe.mjs`（把 fixture 换成带公式的长文档）。
2. **预览侧结构编辑的整篇兜底**（`repaintPreview()` → `renderPreview()`）仍会丢滚动（本任务**刻意未改**，
   因为 `tests/test_preview_block_commit.py` 把兜底写成契约，且症状路径不经过它）。若要覆盖，建议单开一条，
   同时更新该测试断言（把"兜底=整篇重渲"改成"兜底=整篇重渲且保持滚动"）。
3. 差分路径 `paintPreviewAfterSourceEdit()` 在**滚动锚点跨越被替换块**时是否会轻微位移（本次未观察到，
   但结构编辑类型只验了 Enter/Backspace/多行/undo；跨块大段选中替换未覆盖）。
4. 性能：`_measurePreviewMetrics` 的强制布局在长文档上本身是"打开/重渲"的成本，根治应把度量缓存到字体/缩放进版本键
   （不在本任务范围）。
