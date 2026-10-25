# 0.4.8 task-144：UI 四项（侧栏展缩 / 文档区保底宽度可配 / 上下文圆环 / 窗口恢复体感）

**日期** 2026-10-25 · **执行** render-perf · **未 commit**（Lead 统一提交）
改动文件：`app.css`、`app.js`（仅文件末尾追加 ⑥ 的 37 行，**未碰** `_restoreDocTailNL` / `collectEditorBody`）、
`agent-panel.js`、`display-settings.js`、`i18n/zh-CN.js`、`i18n/en.js`、`pywebview.py`、`docs/reference/i18n-inventory.md`（脚本再生成）
+ 本目录测量/复现脚本与数据。

---

## 〇、结论速览（数字都带口径）

| 项 | 结论 | 关键数据 |
|---|---|---|
| ① 侧栏展缩卡顿 | **已改善未根治**：长文档掉帧 −20~28%，但 `width` 是布局属性，动画期全文档 reflow 无法消除 | 长/左栏 >33ms 掉帧 **5.0→4.0/周期**，max 66.7→58.4ms；长/右栏 **5.0→3.6/周期**；普通文档改前 0 掉帧、改后 **0 掉帧**（mean 8.28ms） |
| ② 文档区保底宽度可配 | **完成**：设置→显示新增 320–560（默认 360）+ 人话解释 + 落盘 + 动态读取 + 非法值夹紧 | 真机断言：默认 360、存 480 生效（agent-panel 读到 480）、9999→560、100→320、恢复 360 |
| ④ 上下文用量圆环 | **完成**：底栏长文字→状态栏最右 SVG 环（零依赖）+ tooltip 完整数字；task-91 四条语义保留 | 真机：环在 `#status-bar`、未知灰环带 title；长文字不再出现在底栏视觉行（视觉隐藏 span 保留可访问性/测试契约） |
| ⑥(a) 恢复动画抑制 | **已实现防御性抑制；"右栏重放动画"在本 harness 两轮均未复现**（如实登记，不写成"已修好"） | 事件流：窄/最大化两种条件恢复瞬间**都没有 resize**（仅 blur/visibility/focus）；dock class 恒 `-agent-dock`、inline width 恒 `22rem`、rect 恒 352，**无"收缩→伸展"状态变化** |
| ⑥(b) 先黑屏 | **设了窗口背景色（按落盘主题），但本 harness 未复现黑屏** | OS 截图 40ms/帧：改前/改后恢复后首帧非黑均 ≈19–22ms（分辨率不足以判「人眼黑屏」）；诚实登记 |
| ⑥(c) logo 先出后等 | **完成**：`html.-booting` 期间 logo 轻脉冲 + 顶部 2px 不确定进度条；首个文档/8s 移除 | 真机：就绪后 `-booting` 已移除（断言）；启动亚秒级时间线未取到（app 就绪前 CDP 接不上，如实说明） |

---

## ① 侧栏展缩卡顿（先基线 → 改 → 同口径对比）

**口径**：页面内 `requestAnimationFrame` 间隔（ms）+ `PerformanceObserver(longtask)`；真实鼠标点顶栏按钮
（`#btn-toggle-sidebar` / `#btn-agent`），每次采样 700ms；长文档 fixture = 1800 段落（约 3600 块）的 `big.md`；
普通文档 = `tests/probe-kb/README.md`。**同时看分布（p50/p95/max）与掉帧数，不只看均值。**

| 场景（同一脚本、同一机器） | 帧数/5 周期 | >33.4ms 掉帧 / 周期 | mean | p95 | max | longtask |
|---|---|---|---|---|---|---|
| 改前 长/左栏 | 555 | **5.0** | 10.09 | 8.6 | 66.7 | 6 |
| 改后 长/左栏 | 591 | **4.0（−20%）** | 9.51 | 8.5 | 58.4（−12%） | 4 |
| 改前 长/右栏 | 558 | **5.0** | 10.04 | 8.7 | 75.0 | 1 |
| 改后 长/右栏 | 594 | **3.6（−28%）** | 9.53 | 8.5 | 66.7 | 4 |
| 改前/改后 普通文档 | — | **0 / 0** | 8.25 / 8.28 | 8.4 | — | 0 |

**改动**（`app.css`）：
- `#-sidebar` / `#-agent-dock`：`transition: width/min-width 0.18s ease` → **`0.12s ease-out`**（帧数减少）；
- 两栏加 **`contain: layout`**（隔离侧栏内部重排；**不加 `paint`** —— 拖拽柄在左缘外 3px，paint 裁切会缩小可抓面积，与既有注释一致）。
- **未选 transform 方案**：会改变拖拽柄（边缘外 3px）定位语义，回归面大；本轮已实测改后点击仍有多帧宽度变化（动画正常）、拖拽柄逻辑未动。

**边界（重要）**：`width`/`min-width` 是布局属性 ⇒ 动画期间每帧仍要全文档 reflow；本轮是「减少帧数 + 缩小重排范围」，**不是零掉帧**。
**Lead 的备选 A（即时切换，`transition: none`）可行性**：改动 1 行（两栏 transition 置 none）+ 删除对应动画注释；
风险低：①无动画期 reflow（长文档掉帧应直接归零）；②拖拽柄位置逻辑不变（宽度仍由布局决定，柄随侧栏边缘移动，只是不再插值）；
③用户主动开关的"平滑感"消失（VS Code 侧栏本身即瞬时）。是否采用需**人裁决**（product decision，本轮不擅改）。
raw：`frames-before.json`、`frames-after1.json`、`frames-after2.json`（本目录）。

---

## ② 文本区最小宽度可配置（完成）

- **设置项**：设置 → 显示 → 「文档区宽度 / 文档区保底宽度（px）」，`range` 320–560、step 10、**默认 360**；
  附人话解释：「文档区最小保留宽度。调大后，窗口变窄时对话栏会更早自动隐藏，把空间让给文档。」+ 范围/默认值说明。
- **持久化**：沿用 `-display-settings` localStorage + `save_ui_settings({display})` 磁盘通道；重开生效（`hydrateFromDisk` 走 `pickKnown`）。
- **非法值**：`load()`/`pickKnown` 双处夹紧到 320–560（实测 9999→560、100→320）。
- **生效链路**：`agent-panel.js` 的 `currentContentMinPx()` 读 `MemoriaDisplaySettings.getContentMinPx()`（缺席回退 360），
  `availableDockPx() = #main 内宽 − 左栏 − 当前保底值`；`applyAll()` 仅在**用户改动**该值后派发一次 `resize`
  （启动首帧不额外重排），task-93 的假想几何 + 迟滞（720/760）逻辑未改。
- 真机断言（`verify-144.json` 14/14 PASS）：字段/范围/解释存在、默认 360、存 480 落盘且 agent-panel 读到 480、夹紧、恢复 360。

---

## ④ 上下文用量改圆环（完成）

- **形态**：`#status-bar` 最右新增 SVG 环（14×14，两圆 `stroke-dasharray`，旋转 -90°；**零第三方依赖**），
  底栏不再显示长文字；`#status-agent` 的 token 短行原样保留。
- **tooltip / 可访问性**：`title` + `aria-label` = `字符预算：{chars} / {max} 字符（{percent}%）`，
  有压缩时追加 `· 已压缩 {n} 次`；环样式 `<80%` 中性 / `≥80%`（`chars > threshold_chars`，≈阈值）警示黄 `#ffd75e`（蓝底与既有 `. -stat-warn` 同源）/ 缺失：灰环 + 「上下文用量未知（旧会话或尚未载入）」。
- **task-91 四条语义**（逐条保留）：缺失不报错、比例 `chars / max_chars`（字符÷字符、`contextUsageView` 未改）、
  `over` 判定不变、`compacted_times` 进 tooltip（"压缩发生过"的证据）。
- **与既有 pytest 契约的兼容**：`test_compact_budget_never_clobbers_the_token_segment` 要求 `#status-agent.textContent`
  仍含 compact 文案（"只追加不覆盖"）⇒ 实现为**视觉隐藏 span**（`clip: rect(0 0 0 0)`，可访问性保留）
  + 环 tooltip；node 无 DOM 单测环境走 `textContent` 回退。**不为了让测试过而删可访问性，也不为了可访问性保留视觉长串。**
- **i18n**：新增 `agent.statusBar.compactRingTitle` / `compactRingUnknown`（中英双语）+ `settings.display.contentMin*`（中英），
  `scripts/scan_ui_strings.py` 已再生成 `docs/reference/i18n-inventory.md`。

---

## ⑥ 窗口恢复体感

### (a) 抑制恢复过渡 —— 已实现；**原现象两轮未复现**（如实登记）

**实现**（`app.js` 末尾追加，未动其它函数）：`visibilitychange`（恢复可见）/ `focus` 时给 `<html>` 加 `.-no-transition`，
CSS 只关左右侧栏 `width/min-width` 过渡（`html.-no-transition #-sidebar,#-agent-dock{transition:none}`，
选择器 (1,1,1) 已高于原 (1,0,0)，**不用 !important** —— 有测试禁止该块 `!important`）；240ms 后移除。
实测：恢复后 `-no-transition=true`，320ms 后为 false；正常用户开关仍有多帧宽度变化（动画未被永久关闭）。

**Lead 假设验证（恢复时响应式联动重跑 ⇒ dock 先塌再展）—— 两轮真机测量均未坐实**：
用 8ms 采样记录 `innerWidth / visibility / resize 事件 / dock class+inline width+rect`：

| 条件 | 恢复瞬间 resize？ | innerWidth 前后 | dock class 变化 | inline width | rect |
|---|---|---|---|---|---|
| 窄窗（OS resize 到 1000×700，实测 innerWidth 984） | **无**（仅 blur + visibilitychange×2） | 984 → 984 一致 | 恒 `-agent-dock` | 恒 `22rem` | 恒 352 |
| Win32 最大化后最小化→恢复（innerWidth 1920） | 恢复时**无**（resize 只出现在"最大化"动作本身） | 1920 → 1920 | 恒 `-agent-dock` | 恒 `22rem` | 恒 352 |

⇒ 在本 harness 中 **dock 从未收缩过**（没有"伸展"可复现），也没有恢复瞬间的 resize/响应式重跑证据。
因此**没有**据此改 `applyResponsiveLayout`（避免"未坐实的假设驱动行为变更"）。建议下一步：
- 在真人复现时开一个临时调试口（`MemoriaAgentPanel.dockMetrics()` + `applyResponsiveLayout(reason)` 落 `console.debug`），
  采集一次"发生问题"的 reason/class 时间线；或提供具体条件（最小化前窗口尺寸、是否最大/贴边、DPI 缩放、dock 是否手动折叠/自动隐藏）。
- 若坐实是响应式重跑，再按 Lead 方案在恢复首帧跳过响应式重算 + 保持快照。当前 `-no-transition` 只抑制 CSS 过渡，**不改变决策**。

### (b) 先黑屏 —— 已按落盘主题设窗口背景色；**黑屏未复现**（不写成"已修"）

- 查：pywebview **6.2.1** 支持 `background_color`；原 `create_window` 未设置（默认窗口底色可疑）。
- 改：`pywebview.py` 新增 `_theme_background_color()`：读 `ui-settings.json` 的 `layout.theme`（theme-mode.js 同源落盘；
  `system` 读注册表 `AppsUseLightTheme`），深色 `#1e1e1e`（= `memoria.css --bg-primary`）/ 浅色 `#ffffff`；
  `create_window(..., background_color=...)` + 启动诊断行 `run window-background <color>`。
- 实测（OS 截图 40ms/帧）：改前/改后恢复后首帧非黑均 ≈19–22ms，**本 harness 未复现"黑屏"**（40ms 采样分辨率不够判人眼黑屏；
  也可能只在特定 GPU/窗口动画/冷启动条件出现）。**诚实结论：设了背景色（不亏）但未证明黑屏消失**，需真人确认。

### (c) 加载感（logo 先出后等）—— 完成

- CSS（`app.css` 末尾）：`html.-booting .logo-icon` 轻脉冲 + `html.-booting::before` 顶部 2px 不确定进度条；
  `prefers-reduced-motion` 下关闭动画。
- JS（`app.js` 末尾）：启动即加 `-booting`，首个文档打开（`state.currentPath`）或 8s 兜底后移除（实测就绪后已移除）。
- **基线的诚实说明**：app 就绪前 CDP 接不上，未取到"logo→内容"的亚秒级启动时间线；本项以「视觉加载态存在 + 就绪后移除」为验收，
  未伪造时间线。

---

## 门禁（全部实跑）

| gate | 结果 |
|---|---|
| `pytest -q` | ✅ **1474 passed / 0 failed**（中途 2 个失败已修：单测无 `renderContextRing` 的隔离环境 → 存在性保护；CSS 块禁 `!important` → 提高选择器特异性） |
| 产品 JS `node --check` | ✅ **67/67** |
| `i18n_selftest` | ✅ PASS（中英双语；`scan_ui_strings` inventory 已更新） |
| `team_audit` | ✅ **FAIL=0**（WARN=54 / INFO=24） |
| 12 交互剧本 | ✅ **12/12 失败 0**（24.8s；`raw-interaction-t144-final_2c9014a8.json`） |

## 预占函数证明（给 task-147 / R0）

`git diff -U0 -- src/memoria/ui/static/app/js/app.js` 的全部内容 = **文件末尾新增 37 行 `memoriaBootUX`**（⑥ 用）；
`git diff` 中对 `_restoreDocTailNL` / `collectEditorBody` 的改动 = **0 行**（grep 无命中）。
本任务未触碰这两个函数，task-147 可直接开工。

## 文件与产物

改动：`src/memoria/ui/static/app/{css/app.css, js/app.js, js/agent-panel.js, js/display-settings.js, i18n/zh-CN.js, i18n/en.js}`、
`src/memoria/app/shell/pywebview.py`、`docs/reference/i18n-inventory.md`（生成）。
本目录：`ui144_measure.py`、`frames-{before,after1,after2}.json`、`ui144_restore.py`、`restore-{before,after}.json`、
`ui144_repro_restore.py`、`repro-restore-{narrow,max}.json`、`ui144_verify.py`、`verify-144.json`、
`shots/{statusbar_ring.png,settings_content_min_width.png}`、`os_series.py`。

复现命令：
```powershell
python artifacts/agent/verify/todo/ui-perf-and-settings/ui144_measure.py after2 frames
python artifacts/agent/verify/todo/ui-perf-and-settings/ui144_restore.py after
python artifacts/agent/verify/todo/ui-perf-and-settings/ui144_repro_restore.py narrow
python artifacts/agent/verify/todo/ui-perf-and-settings/ui144_verify.py
```

## 剩余风险 / 交接

1. ①：当前 120ms + contain 只减 20~28% 掉帧；若人仍觉卡，建议二选一（即时切换 / transform+拖拽柄适配），**需人裁决**。
2. ⑥(a)："右栏先塌再展"未复现；`-no-transition` 是防御性抑制，不改变响应式决策；复现条件待采集。
3. ⑥(b)：背景色已按主题设置，但黑屏未证实/未复现。
4. `#status-agent` 里的长文字改为视觉隐藏 span：屏幕阅读器仍可读，但若后续要彻底移除该文案，需同步更新 `test_compact_budget_never_clobbers_the_token_segment`（当前保留以守既有契约）。
5. 测量脚本每次只 kill 自己 launch 的 PID；本机测量前后已 `Get-CimInstance` 核实无残留 Memoria 实例。
