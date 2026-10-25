# task-140 · 跳转滚动定位修复（`block:"start"` → 不变量驱动）

> **状态**：代码已改完 + 测试断言已同步 + **真机三场景时间序列验证完成（2026-10-25）**。
> 真机证据：`jump-scroll-fix-timeseries.json` / `jump-scroll-fix-timeseries-math.json`（3 轮 × 7 场景，跨轮次逐值一致）。
> **未 commit**。写域：`src/memoria/ui/static/app/js/app.js`、`tests/test_preview_block_commit.py`。

---

## 1. 一句话根因

**用了不该用的量**：旧实现用「把元素顶到顶部」这个**动作**去表达「修正排版漂移」这个**意图**。
动作与意图不匹配 ⇒ 居中后又被拉回顶部、已可见也被强行滚动、且方向永远"向下挪一点"。

---

## 2. 我确定的不变量（先问"要保证什么"，再问"怎么实现"）

| 编号 | 不变量 | 依据 |
|---|---|---|
| **I1** | 目标范围**任意部分已可见** ⇒ **一个像素都不动** | 人原话：「如果正在显示的内容已经有目标的部分区域（至少），仍然进行了滚动定位 … 不需要滚动定位」 |
| **I2** | 目标完全不可见 ⇒ **整体居中**（不是顶对齐） | 人原话：「滚动定位确实…在文本显示区域的中间」（这是**被认可**的行为）；「过一小会就把目标的开始行对齐到编辑区域的顶部，**错误**」 |
| **I3** | 二次校准**只补偏移，绝不重设落点** | AG104 原目标只是「修排版漂移」；重设落点是越界 |
| **I4** | 用户一旦自己滚动/点击/触摸/按键 ⇒ 立刻放弃校准 | 既有 guard（`_jumpAnchorGuard`），**完整保留** |

---

## 3. 改动清单

### 3.1 `scrollIntoView` 全量清单（改前 / 改后）

| # | file:line | 函数 | 改前 | 改后 | 理由 |
|---|---|---|---|---|---|
| 1 | `app.js:15612` | `highlightPreviewRange`（**预览区跳转主路径**） | `first.scrollIntoView({block:"start", behavior:"smooth"})` | **删除**，改调 `_jumpScrollToRange(preview, laid)` | 违反 I1+I2；`start` 是症状①②③的直接来源 |
| 2 | `app.js:15639` | `_reanchorJumpScroll` **350ms tick** | `first.scrollIntoView({block:"start", behavior:"auto"})` | **删除**，改 `pane.scrollTop += drift` | 症状①「过一小会被拉顶部」的直接来源；违反 I3 |
| 3 | `app.js:15639` | `_reanchorJumpScroll` **1400ms tick** | 同上 | 同上 | 同上 |
| 4 | `app.js:15470` | `highlightRange`（**源码区**跳转） | `firstSource.scrollIntoView({block:"start", behavior:"smooth"})` | 改调 `_scrollSourceRangeIntoViewCentered(startLine, endLine)` | **同病**：把目标首行顶到编辑区顶部，且已可见也硬滚 |
| 5 | `app.js:15505` | `highlightRangeWithError`（检查面板"打开"跳转） | 同上 | 同上 | 同上 |
| — | `app.js:15437` | `scrollEditorToLine` | `block:"center"` | **不动** | 已是居中，符合 I2 |
| — | `app.js:1552` | `gotoGraphAuditIssue` | `block:"center"` | **不动** | 已是居中 |
| — | `app.js:15550` | `highlightKpListItemWithError`（**左侧 KP 列表**） | `block:"center"` | **不动** | 不在跳转滚动域（列表项定位，居中已对） |
| — | `app.js:3223` | 配置面板链接匹配 | `block:"nearest"` | **不动** | 非文档跳转域 |
| — | `app.js:3670` | 配置面板链接项 | `block:"nearest"` | **不动** | 同上 |

**改后全仓 `app.js` 已无 `block:"start"` 的代码使用**（仅剩 3 处注释在说明历史 bug）。

### 3.2 新增/重写的函数

#### ① `layoutPreviewRangeBand` 返回**几何**（关键修复）

```js
// 旧：只返回 first，把已算好的 top/bottom 并集丢掉了 —— 那恰是跳转唯一需要的不变量
return first;
// 新：
return { first: first, band: band, top: top, bottom: bottom };
```
零高目标（空行 band 高 0）也返回几何，不再提前 `return first`。

#### ② `previewRangeViewportRect(preview, laid)`

把 `laid.top/bottom`（相对 `#preview` border-box）换算到 **`#preview-pane` 视口坐标**：
```js
const offset = preview.getBoundingClientRect().top - pane.getBoundingClientRect().top;
top = laid.top + offset;  bottom = laid.bottom + offset;
```
> **为什么不能直接用 `#preview`**：`.-preview` 有 `padding: 1.5rem 40px 48px`（`app.css:3907`），
> 且 `#preview-pane` 才是 `overflow:auto` 的滚动容器（`app.css:3878-3881`）。用错参照系会把 48px 下内边距算进"目标底边"。

#### ③ `_jumpScrollToRange(preview, laid)` —— 首次落点

```js
// I1：任意部分可见 ⇒ 不动
if (visibleBottom - visibleTop > EPS) { _jumpExpectedOffset = null; return "already-visible"; }
// I2：完全不可见 ⇒ 居中；目标比视口高 ⇒ 顶边贴齐
const targetTop = rect.viewportH > rect.height ? (rect.viewportH - rect.height) / 2 : 0;
_jumpExpectedOffset = targetTop;
pane.scrollTop += rect.top - targetTop;
```

#### ④ `_reanchorJumpScroll` —— 二次校准（**只补偏移**）

```js
if (_jumpExpectedOffset === null || _lastJumpPane !== pane) return;  // 本次没居中 ⇒ 完全不打扰
// 350ms / 1400ms：
if (rect.top >= 0 && rect.bottom <= rect.viewportH) return;          // 已整体可见 ⇒ 不动
pane.scrollTop += (rect.top - expected);                             // 只补差值
// 绝不 scrollIntoView
```
保留：`_jumpAnchorGuard` 顶掉旧轮、`["wheel","mousedown","touchstart","keydown"]` once 监听、`tick(350); tick(1400)`。

#### ⑤ `_scrollSourceRangeIntoViewCentered(startLine, endLine)` —— 源码侧同 I1/I2

用 `#editor-pane`（`.-pane`，`overflow:auto`）做视口，量 `#line-start` 的 top 与 `#line-end` 的 bottom。

### 3.3 测试断言同步（**必须先说，因为它原本锁住了 bug**）

`tests/test_preview_block_commit.py:167` 原文：

```python
assert 'first.scrollIntoView({ block: "start", behavior: "auto" });' in js   # ← 守着 bug
```

这条测试**把 bug 当作期望行为固化了**。已改为断言新不变量：

```python
assert 'first.scrollIntoView({ block: "start", behavior: "auto" });' not in js, "二次校准不得重设落点（task-140）"
assert "pane.scrollTop += drift;" in js, "二次校准只补漂移差值"
assert "function _jumpScrollToRange(" in js
assert "already-visible" in js and "centered" in js
assert 'scrollIntoView({ block: "start"' not in js, "跳转域内不得再出现顶对齐（task-140）"
# AG104 原目标仍保留：
assert "tick(350); tick(1400);" in js
assert '["wheel", "mousedown", "touchstart", "keydown"].forEach(function (ev) {' in js
```

> 这是本任务最重要的一条元发现：**"绿灯"不代表行为正确，它也可能代表 bug 被写成了契约**。

---

## 4. 三症状 → 修复对应

| 症状（人原话） | 修复 |
|---|---|
| ①「过一小会就把目标的开始行对齐到编辑区域的顶部」 | 二次校准删掉 `scrollIntoView({block:"start"})`，改成 `scrollTop += drift`（且已可见时不动） |
| ②「已有目标的部分区域，仍然进行了滚动定位」 | `_jumpScrollToRange` 的 I1 分支：任意部分可见 ⇒ return，不动 |
| ③「从上往下滚的固定模式，哪怕应该从下往上」 | 居中落点由 `delta = rect.top - targetTop` 决定符号 ⇒ 目标在上方时 delta 为负（向上滚），下方时为正（向下滚）。不再有"居中后再向下挪" |

---

## 5. I1 的严格程度：Lead 已裁决 = A（保留当前实现）

我按人原话实现了 **A：任意部分可见（>1px）⇒ 不滚**。

**Lead 裁决（2026-10-25）= A，保留当前实现**，依据：人原话明确给了「至少」这个条件，35% 阈值是他没要求的；
高亮 band 的 flash 已经提供"点到了"的反馈。

**替代方案 B（仅作后备，不实施）**：把 I1 收紧为

```
可见高度 ≥ min(目标高, 视口高 × 0.35)  ⇒ 不滚
低于该阈值                            ⇒ 最小滚动补足（不居中、不顶对齐）
```

**触发条件**：只有真人反馈「点了没反应」时才切 B，且**只改 `_jumpScrollToRange` 的 I1 分支一处**。

### 5.1 真机数据顺带证实了 A 的副作用确实存在（非缺陷，是裁决结果）

| 场景 | 前置可见像素 | 点击后 scrollTop 变化 |
|---|---|---|
| C-bottom（目标顶边在视口底边，露出 24px） | 24px | **0（一像素不动）** |
| C-top（目标底边在视口顶边，露出 17.6–23.6px） | 17.6–23.6px | **0** |

⇒ 「只露一丝」时画面确实不动，符合 A 的预期语义；可见性反馈由 band flash 承担。

---

## 6. 真机三场景时间序列验证（2026-10-25 完成）

> 上一实例的 shell 挂死在 `0xC0000142`（连 `echo` 都起不来），本节全部由同名新实例在 shell 恢复后**实测**。
> 产物：`jump-scroll-fix-timeseries.json`（plain 文档）、`jump-scroll-fix-timeseries-math.json`（公式文档）、
> `jump-scroll-fix-run.log`（启动/清理/隔离记录）。脚本：`jump-scroll-fix-launch.py` / `jump-scroll-fix-run.ps1` / `jump-scroll-fix-probe.mjs`。

### 6.1 测量装置（可复跑、密封）

| 项 | 做法 | 为什么必须这样 |
|---|---|---|
| **启动** | `jump-scroll-fix-launch.py`：真实 `memoria.app.desktop.main()`，只额外设 `webview.settings['REMOTE_DEBUGGING_PORT']` | **不能只设 `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS`**：pywebview 6.2.1 在 `platforms/edgechromium.py:82` 显式赋值 `props.AdditionalBrowserArguments`，一旦显式设置，WebView2 **忽略该环境变量**（实测：`msedgewebview2.exe` 命令行里没有 `--remote-debugging-port`，端口不监听）。本实例踩过一次，render-perf 在 task-133 独立踩过同一个坑 |
| **配置隔离** | `MEMORIA_CONFIG_DIR` = `%TEMP%\memoria_jumpscroll_<pid>_<rand>`（**全新空目录**）；清掉 `MEMORIA_UI_SETTINGS` | 不继承开发机 `ui-settings.json`（本仓 task-53/54 事故：ambient 配置会让测量结论依赖机器设置） |
| **KB** | 自建 fixture `artifacts/agent/verify/todo/jump-scroll-fix-fixture/kb` | **不碰 `docs/example/AAA_Vocab`**（用户实时库）；也不写冻结语料 |
| **进程安全** | 只杀 `Start-Process` 得到的 PID；杀前由 `safe-kill.psm1` 校验命令行含本次端口（端口放在 launcher 的 argv[1] ⇒ 可校验）；开始/结束各拍一次用户 `Package\Memoria.exe` PID 快照 | task-49 事故：旧脚本"凭端口反查 PID + 杀进程树"误杀了用户的应用。本次三次运行前后快照均为 `47596`（一致） |
| **驱动入口** | `MemoriaApp.surface.revealRange(start,end)` = 契约 §3.1 跳转入口 → 内部 `highlightRange → highlightPreviewRange` | 与"点知识点列表项跳转"走**同一条滚动代码**，只是调用点不同；不是另写一条测量专线 |
| **采样** | 页面内 `performance.now()` + 页面内 `setTimeout`，采样点 25/100/250/350/500/700/900/1100/1400/1600/2000ms | 避免 CDP 往返抖动；采样点覆盖要求的 0/100/350/500/1400/1600/2000 并有冗余 |
| **前置硬闸** | `window.__MEMORIA_LAZY=false`（`app.js:8345` 明示这是回归专用通道）+ 断言 `.-pv-placeholder`==0 + `vp>200` + `maxScroll>2*vp` | 惰性物化的**占位高度估值**是第二个变量，混进来就分不清"跳转错了"还是"占位算错了" |
| **语料** | `docs/jump-long.md`：313 个 DOM 块、纯文本（主判据）；`docs/jump-math.md`：267 块、**12 个 display 公式**（AG104 场景） | 两篇都通过前置闸（placeholders=0），视口 `vp=707` |

### 6.2 主判据：三场景时间序列（plain 文档，vp=707，**3 轮逐值一致**）

| 场景 | 前置（scrollTop / 目标顶边 / 可见像素） | 跳转后落点 | 目标顶边（期望 `(707−h)/2`=**329.7**） | 方向 | 350ms 后漂移 |
|---|---|---|---|---|---|
| **A 目标在视口上方** | 5115 / −150.3 / **0** | **4635**（−480） | **329.7** | 上 ✅ | **0** |
| **B 目标在视口下方** | 0 / 796.8 / **0** | **467.1**（+467） | **329.8** | 下 ✅ | **0** |
| **C-bottom 已部分可见（底边裁切）** | 4826 / +683 / **24** | **4826（0 变化）** | 683（不滚，保持用户所见） | 无 ✅ | **0** |
| **C-top 已部分可见（顶边裁切）** | 5533 / −24 / **23.6** | **5533（0 变化）** | −24（不滚） | 无 ✅ | **0** |

**时间序列（A 场景，round 1；B/C 同形）**：跳转在 `revealRange` 同步返回前就已落到最终值，之后 11 次采样**完全不动**：

```
t(ms)     28   105   260   355   511   713   904  1104  1404  1604  2004
scrollTop 4635 4635  4635  4635  4635  4635  4635  4635  4635  4635  4635   ← changedAt = []
targetTop 329.7 ×11
```

⇒ 关闭条件「**跳转后 1.5s 内 scrollTop 不再变化**」**不仅成立，而且更强**：从 28ms 到 2004ms **全程**零变化（连一次"小幅校准"都没有）。
旧 bug 的签名（`350ms 被拉到顶部`）在数据里对应的就是 `targetTop → 0`；本实现三轮均为 **329.7**，离 0 有 330px。

**断言逐条判定（3 轮均一致）**：

| 不变量 | A | B | C-bottom | C-top | 判定 |
|---|---|---|---|---|---|
| I2 完全不可见 ⇒ **居中**（targetTop≈329.7，不是 0） | 329.7 | 329.8 | 不适用（未滚） | 不适用 | ✅ 3/3 轮 |
| 旧 bug 签名「顶对齐」 | 否 | 否 | 否 | 否 | ✅ 3/3 轮 |
| ③ 方向由几何决定（非固定向下） | 上 | **下** | 无 | 无 | ✅ |
| I1 任意部分可见 ⇒ **一像素不动** | — | — | Δ=**0** | Δ=**0** | ✅ 3/3 轮 |
| 跳转后 350ms 起无漂移 | 0 | 0 | 0 | 0 | ✅ |

### 6.3 AG104：二次校准**只补偏移、绝不重设落点**（I3，DRIFT 注入场景）

主判据里 plain 文档没有排版漂移（`_mathPending` 已落定后才跳），所以 350/1400ms 校准不动作。
为了**真正逼出 drift 分支**，加 `DRIFT` 场景：跳转后 ~70ms 在目标块**前**插入 400px 占位（等价于 MathJax/图片晚到把目标往下推）。

| t(ms, round1) | 27 | 108 | 264 | **360** | 513 | 714 | 903 | 1103 | 1403 | 1603 | 2003 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| scrollTop | 4635 | 4635 | 4635 | **5035** | 5035 | … | … | … | … | … | 5035 |
| targetTop | 329.7 | **729.7**（被推下 400） | 729.7 | **329.7** | 329.7 | … | … | … | … | … | 329.7 |

- 校准**只补了 drift = 400px**（`scrollTop += 400`），把目标顶边**还原到居中位 329.7**；
- **没有**把目标顶对齐到 0（旧实现在这里会再做一次 `scrollIntoView({block:"start"})` ⇒ targetTop→0）；
- 校准发生在 ~352–360ms（3 轮：360/352/356），**之后 1600/2000ms 不再变化**（driftAfter350=0）；
- 同一序列在公式文档（12 个 `mjx-container`）复现：2512 → **2912**（+400）→ targetTop 335.4（期望 335.9）。

### 6.4 探针**判别力**自证（OLD-SIM 对照，防"只能判绿的探针"）

在**同一页面、同一目标块**上，按旧实现语义重放（`scrollIntoView({block:"start"})`，并在 350/1400ms 再各来一次）。
**明确标注：OLD-SIM 是按旧语义的合成重放，不是旧构建二进制**；旧代码本身由 §3.1 的 `git diff` 证明（5 处 `block:"start"` 已删除）。

| 对照场景 | 新实现（实测） | OLD-SIM（实测） | 说明 |
|---|---|---|---|
| A（目标在上方） | targetTop **329.7**，centered=true | targetTop **−0.3**，topAligned=**true** | 探针能区分"居中"与"顶对齐" |
| C-bottom（已露 24px） | scrollTop **4826→4826（不动）** | scrollTop **4826→5509（滚了 683px）**，targetTop=**0** | 探针能发现"已可见仍强行滚动 + 顶对齐" |

⇒ 同一把尺子在新实现上判绿、在旧语义上判红：**绿灯不是因为尺子坏了**。

### 6.5 结论与诚实边界

**结论**：I1（已可见不滚）、I2（不可见则居中）、I3（二次校准只补偏移）、③（方向由几何决定）在真机上全部有数据支撑；
关闭条件 1（失败复现→时间序列）与 3（1.5s 内不再变化）**达成**；旧 bug 签名（顶对齐）在任意场景均未出现。

**边界（不要把结论外推）**：
1. 两篇 fixture 都是 **< 1000 块、非惰性**文档；**惰性/超长文档是另一个变量**，属 task-141（本条是其 `blocked_by`，必须串行）。
2. 真机上没有逐像素重放"鼠标点击知识点列表项"，用的是该点击的**下游真实入口** `revealRange`（差别只在调用点，不在滚动逻辑）。
3. OLD-SIM 是旧语义的合成重放（见上），不是启动旧构建；
4. 本节的"零漂移"是**关掉惰性 + 等 `_mathPending` 落定**后的基线；真实环境若有图片晚加载，落到 §6.3 的 drift 分支（已验证只补偏移）。
---

## 7. 门禁复跑（**第一手实测**，2026-10-25 新实例）

> 上一实例因 shell `0xC0000142` 无法跑任何命令，以下全部由本实例在 shell 恢复后实跑。HEAD = `e030dc1d`（`app.js` / `tests/test_preview_block_commit.py` 仍是**未提交**工作区改动）。

| 门禁 | 命令 | 结果 | 判定 |
|---|---|---|---|
| 静态语法（全仓非 vendor JS） | `node --check` × **66** 个文件（`src/**/*.js`，排除 vendor） | **0 failed** | ✅ |
| 目标测试文件 | 含在下方全量跑内（`tests/test_preview_block_commit.py`） | 通过 | ✅ |
| **全量 pytest** | `python -m pytest -q tests` | **1474 passed / 0 failed**（1 warning），51.7s | ✅ 与基线一致 |
| 12 交互剧本 | `python scripts/benchmark/surface/run_interaction.py` | **12/12 通过，failed=0**，25.6s（`interaction-legacy-golden_e030dc1d.md`：结论 ✅ 全部剧本跑通） | ✅ |
| i18n 自检 | `node scripts/i18n_selftest.js` | 8 项全 PASS | ✅ |
| team_audit | `python scripts/agent/team_audit.py` | **FAIL=0**（WARN=52 / INFO=25，均为既有写域共享类，无 FAIL），结论「机检全绿」 | ✅ |

> 说明（避免误读）：12 剧本那条命令的 PowerShell 外层 `exit=1` 来自 `python` 把 **jieba 构建日志写 stderr**、被 PS 当成 `NativeCommandError`；
> 判据以产物 JSON 为准：`{"ok":true,"scenarios":12,"failed":0}` 且 md 结论为「✅ 全部剧本跑通」。

---
## 8. 回归风险

| 风险 | 评估 | 缓解 |
|---|---|---|
| **R-a `layoutPreviewRangeBand` 改了返回类型**，其它调用方可能按旧签名用 | **中**。全库 4 处调用：`highlightPreviewRange`(已改)、`_reanchorJumpScroll`(已改)、`watchPreviewBandLayout`(只做副作用，忽略返回值 ✅)、无其它 | 已 grep 逐个核对 |
| **R-b 源码区改用 `pane.scrollTop +=` 而非 `scrollIntoView(smooth)`** ⇒ 失去平滑动画 | 低（这是刻意：平滑动画本身就会让落点"漂"一会儿，与 I3 冲突） | 如需动画可后续加 `scrollTo({top, behavior:"smooth"})`，但**不改变落点语义** |
| **R-c 双栏模式下两侧都滚** | 中。`highlightRange` 会同时滚源码区与预览区 | 保持既有语义（两侧都要定位）；两侧各自走自己的 I1/I2 |
| **R-d `#preview-pane` 的 `clientHeight` 含 padding** | 低。`clientHeight` = padding box 高度（含上下 padding、不含 border），与 `getBoundingClientRect().top` 的 border 原点差一个 border-top（`.-pane` 无 border 声明 ⇒ 0） | 已在报告记录；若后续给 `.-pane` 加 border 需复查 |
| **R-e 目标比视口还高**（长 KP） | 已处理：`viewportH > height` 才居中，否则顶边贴齐 0 | 二次校准会持续把顶边钉在 0（`drift` 收敛到 0 后 `< 1px` 停止），不抖动 |
| **R-f 用户手滚后仍被校准** | 低。guard 完整保留；且新增 `_jumpExpectedOffset === null` 短路 | — |
| **R-g 与 task-141 冲突** | 已知。141 `blocked_by` 140，串行 | — |

---

## 9. 未做 / 待裁决

1. **§5 的 I1 严格度裁决**（A 严格 / B 阈值）—— 等 Lead/人。
2. **全部运行时验证**（因 shell 故障）。
3. 报告 §6 的三场景时间序列数据。
4. 若采纳 B，需再改 `_jumpScrollToRange` 的 I1 分支（一处判断）+ 补测。
