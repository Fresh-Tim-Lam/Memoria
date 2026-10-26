# task-186 交付报告：启动蒙层 + 星河动画 + 空灵音效（默认静音 / reduced-motion / 可降级）

> 状态：**完成，待收口**（不 commit）；owner：ui-designer；日期 2026-10-27。
> **收口结果**：全仓 pytest **1645 passed / 0 failed**；node --check 0；i18n PASS；team_audit FAIL=0；12 剧本 12/12；真机验收 **15 PASS / 0 FAIL**。

## 0. 变更清单（4 个文件 + 测试 + 证据）

| 文件 | 改动 | 行数 |
|---|---|---|
| `src/memoria/ui/static/app/js/splash.js` | **新增**：蒙层/星河/合成音效/设置小节，生命周期与降级全部在此（IIFE 自包含，无外部依赖） | 新文件 ~730 行 |
| `src/memoria/ui/static/app/css/app.css` | **文件末尾追加** splash 样式（覆盖层、静态星空降级、设置小行、reduced-motion 兜底） | +~170 行（纯追加） |
| `src/memoria/ui/static/app/index.html` | **+1 行** `<script src="/app/js/splash.js"></script>`（放在应用脚本之前；新模块必须接线——这是唯一一处非 js/css/i18n 的改动，特此显式申报） | +1/-0 |
| `src/memoria/ui/static/app/i18n/{zh-CN,en}.js` | 各自**末尾 Object.assign** 追加 `splash` 段（不推位任何既有 `i18n:<行号>` 锚点） | +~16 行/文件 |
| `tests/test_splash_animation.py` | 新增 13 条回归（接线/时长预算/默认静音/持久化/reduced-motion/降级/零资源/纯函数/证据存在） | 新文件 |
| `artifacts/agent/verify/todo/splash-animation/**` | 真机探针 `probe_splash.mjs` + 启动器 + 冷启动测量（`measure_boot.mjs`、`run_boot_measure.ps1`）+ 交错 A/B 脚本 + `verify.json` + 截图 | 新目录 |

**没动**：`docs/**`、`Package/**`、`services/**`、既有"外框跑马灯"（`html.-booting` 的 logo 脉冲 + 顶部进度条，app.css 原块一行未改）。

## 1. 两条真实回归的修复（Lead 指出，必须单独说明）

### ① app.css 用了 `!important` → 已移除，改"提高特异性"
- 原写法（reduced-motion 兜底）：`. -memoria-splash, .-memoria-splash * { animation: none !important; transition: none !important; }`。
- 现写法：`html .-memoria-splash, html .-memoria-splash * { animation: none; transition: none; }`
  —— `html` 前缀把特异性从 `(0,1,0)` 提到 `(0,1,1)`，天然压过基础类选择器，**不需要 `!important`**（与 `tests/test_checkbox_dot_style.py` 守的纪律一致：留出日后可覆盖空间）。
- 加了两道回归钉子：
  - `test_splash_css_never_uses_important`：splash 样式区**代码里**出现 `!important` 即红（注释里讲反例不算）；
  - `test_reduced_motion_...` 内也断言 `!important not in` 该块代码。
- 复核：`app.css` 中 splash 区代码 `!important` 计数 = **0**（既有 37 处 `!important` 全在 splash 块之前，未触碰）。

### ② `test_splash_animation` 全仓跑挂、单跑过
- 根因：那段时间我在做**T-splash-2 的 A/B 测量**，脚本会临时切换 `index.html`（开关 splash script）与临时改写 `splash.js`（变体注入），随后才恢复；release-manager 恰好在此期间跑全仓 pytest ⇒ 读到**瞬时不一致的工作区**（单跑时文件已恢复，故通过）。
- 处置：删除所有临时改写；A/B 归因脚本已改为**必须自带备份/恢复并断言恢复成功**（`ab_interleaved.py` 末尾断言 `index.html` 已恢复 on 状态）；收口前全仓 pytest 连续两次 **0 failed**（1645 passed）。
- 教训已固化进证据目录脚本注释：**测量期间禁止让工作区处于"半改"状态跑别人**（A/B 一律用自带 restore 的脚本，且不与其他门禁并发）。

## 2. T-splash-1..8 实测

真机：`memoria.app.desktop`（独立临时 KB + 独立 `MEMORIA_CONFIG_DIR`，不碰用户库/设置），CDP 读 DOM/状态。`verify.json` **15 checks / 0 fail**。

| 验收 | 结果 | 证据（verify.json） |
|---|---|---|
| **1 冷启动出现；刷新/二次打开不出现** | ✅ | cold：`everShown=true firstShownAt=…650 fadeStart=…498 removedAt=…825 fadeReason=ready`（停留 848ms，截图有）；reload：`hasEl=false everShown=false`（sessionStorage 标记） |
| **2 不延长启动（改前基线 + 改后对照）** | ✅ | 见 §3：**交错 A/B：on 3242 vs off 3281 → delta = −39ms**（on 不慢于 off）；页内口径 on 1136 vs off 1107 |
| **3 reduced-motion ⇒ 无动画、只有静态蒙层+文字** | ✅ | `mode=static reducedMotion=true canvasDisplay=none brandAnimation=none`，brand rect 216×51、hint 有字（截图 `shot-reduced-motion-static.png`） |
| **4 音效默认关；开启有声音/可调音量/持久化** | ✅ | 默认 `checkbox=false volume=35`；点击开 ⇒ `audioStarted=true`；音量 80%；`ui_settings.splash={"sound":true,"volume":0.8}`；刷新后 `prefs={"sound":true,"volume":0.8}` |
| **5 音频被拒（模拟 autoplay 拒绝）⇒ 启动不受影响、无报错** | ✅ | `audioBlocked=1 audioStarted=false`、**0 未捕获异常**、`-booting` 正常移除、无 flash 报错 |
| **6 无 Canvas/GPU ⇒ 降级静态、不白屏** | ✅ | 强制 static：`mode=static canvasDisplay=none`，静态蒙层 + 文字仍在（截图 `shot-force-static-fallback.png`） |
| **7 零网络请求** | ✅ | 运行时：外部 origin 资源 = `[]`；代码：无 `fetch/XMLHttpRequest/new Audio/http(s)://`、无 `url(`、无图片/音频/字体文件名；音效 = Web Audio **现场合成**（无音频文件） |
| **8 门禁** | ✅ | pytest **1645 passed / 0 failed**；node --check 0；i18n PASS；team_audit FAIL=0（WARN/INFO 为存量）；`run_interaction.py` **12/12**（exit 0） |

## 3. T-splash-2 方法论：为什么用"交错 A/B"，以及为了不拖慢启动做了什么

**噪声教训（重要）**：顺序测（先全 before、再全 after）会被系统漂移污染 —— 实测同一天两次 before 为 **1897 vs 2081ms**（+184ms，与本功能无关；当时机器上还有其它 agent 在跑基准/全仓测试）。故最终口径为**交错 A/B**：每一轮交替 on/off，让两臂共同承受同一噪声；且额外用页内口径 `removed_at - performance.timeOrigin`（剔除 WebView2 进程启动的方差）。

- 最终：**on 3242ms vs off 3281ms（delta −39ms）**，页内 on 1136ms vs off 1107ms —— 在测量噪声内，**没有变慢**（`ab-interleaved.json`）。
- 归因过程中发现并修掉两处真实开销（都由交错 A/B 归因实验定位）：
  1. **逐帧星空的 rAF 与"应用首屏"抢主线程**：初版 60fps canvas ⇒ delta **+124~193ms**。改为**一次性绘制 + CSS transform/opacity 动画**（主线程零占用），并把画布从"双层 1.4×DPR1"瘦身为"单层 1.16×DPR0.6"（省掉绝大部分纹理上传）。
  2. **启动关键路径上的 `get_ui_settings` RPC**：与首屏 RPC 高峰抢桥，实测 delta 仍在 **+124ms** 左右。改为**启动期只用 localStorage 快路径**（每次设置变更都会同步写它）+ **淡出后**再同步 ui_settings 权威值 ⇒ delta 掉到噪声内（−39ms）。
- 视觉没有被这两项优化牺牲：星河仍可见（一次绘制 + 漂移/闪烁/流星 CSS 动画），截图见 `shot-cold-splash.png`。

## 4. 设计取舍（可复核）

- **浮层覆盖整个客户区**（`position:fixed; inset:0; z-index:2147483000`），淡出 **320ms**；淡出开始即 `pointer-events:none`（不挡输入）。
- **无最短停留**：`-booting`（既有"跑马灯"结束 = 首个文档已打开/8s 兜底）消失 ⇒ **立即**淡出；**上限 1200ms**、绝对兜底 5000ms（任何异常都保证消失）。
- 冷启动判定：`sessionStorage['memoria.splash.seen']` ⇒ 同窗口会话刷新/换库不再出现（换库不重载页面 ⇒ 天然不出现）。
- 音效：Web Audio 合成（A 大三和弦 + 9 度 + 高八度铃 + 程序生成混响，2.4s，无文件）；默认 `sound:false`；自动播放被拒 ⇒ 静默 + `__memoriaSplashStats.audioBlocked` 计数（可观测，不弹窗）。
- 设置：包装既有「显示」页签的 `renderSettingsBody`（**不新增页签/不新增 index.html 结构**），开关 + 音量（0-100，默认 35%），走既有 `save_ui_settings` 的 `splash` 段（不新增路径）。
- reduced-motion：JS 不启动动画 + CSS 用 `html` 前缀特异性禁用（无 `!important`），只留深空渐变 + 静态星点 + 文字。

## 5. 复现

```powershell
# 真机验收（T1/T3/T4/T5/T6/T7）——自动起应用、独立 KB/config、跑完关进程树
powershell -NoProfile -ExecutionPolicy Bypass -File artifacts/agent/verify/todo/splash-animation/run_splash_probe.ps1 -NodeExe <node.exe> -Port 9900
# 冷启动 A/B（交错；自带 index.html 备份/恢复断言）
python artifacts/agent/verify/todo/splash-animation/ab_interleaved.py
new-Item ... # 结果：ab-interleaved.json
```

## 6. 边界与遗留

- **未 commit**；`index.html` 的 +1 行 script 接线已在 §0 显式申报（新模块加载的必要条件）。
- A/B 测量脚本会临时改 `index.html`/`splash.js` —— 全部自带恢复断言；**不要在别的门禁并发时跑**（已把这条教训写进脚本注释与 §1②）。
- 遗留可选项（本次未做，等 Lead/人拍板）：`splash.js` 目前 ~730 行内联于单文件；若将来要"可换皮肤/多套动画"，再拆 assets（当前刻意零资源、零请求）。

---

# v2（2026-10-27）：人反馈「不要蓝色 / 主题色 / 白主题怎么办 / 星点要动且体现使用痕迹」

## 人原话
> 「加载蒙皮的背景不要蓝色，可以给一点渐变，主色调是设置里面的主题色；你有思考白色主题加载动画该咋办你可以找人调研；另外我希望黑色蒙皮的星空的星点不是静态，而是能够体现用户使用痕迹的，这一点你也可以找人研讨」

## 做了什么

### ① 背景：从"固定蓝色太空"改成"主题中性渐变 + 主题色光晕"
- 暗色：中性深灰渐变 `#17181a → #101113 → #0a0b0c`（不再是 navy 蓝底），叠加主题色光晕
  `color-mix(in srgb, var(--theme-color) 14%/10%/7%, transparent)`（带 `rgba(0,122,204,…)` 兜底声明，旧 WebEngine 也能看）。
- 亮色：`#fbfcfd → #f3f5f8 → #e9edf2` + 同款主题色光晕（更淡，14%→亮色 opacity 0.5）+ 一层浅色雾提升星点对比。
- **主色 = 主题色**：光晕、使用痕迹星、星轨、流星、品牌字辉光全部取 `var(--theme-color)`，不再出现固定蓝色调
  （测试断言：区域里 `#0b1026/#070a18/rgba(84,124,255` 等旧色必须不存在）。
- 全部走既有 token + `color-mix`，不新增颜色常量；`!important` 仍为 0（靠 `html` 前缀特异性）。

### ② 白色（浅色）主题的蒙层
- 品牌字用 `--text-bright`（浅色主题 = #000）⇒ 截图实测 `rgb(0,0,0)`，不是"白字白底"。
- 星点颜色改由 `--splash-star` 变量控制（暗色 `rgba(232,238,250,.85)`、浅色 `rgba(46,58,84,.55)`）。
- 浅色背景上"星点"改用主题色 + 深灰，并在天空中部加了一团极淡白雾 ⇒ 有星空感、又不脏。
- 证据：`shot-light-theme-splash.png`（真机、`data-theme=light`）。

### ③ 星点不静态（原来 26s 漂移在 <1s 的蒙层里看起来是静止的）
- 画布挂两个常驻 CSS 动画：`memoria-splash-drift 8.5s`（漂移）+ `memoria-splash-twinkle 3.6s`（闪烁）；
  另有 `memoria-splash-meteor 5.2s` 流星（主题色）。
- reduced-motion 下三个动画全部关闭（媒体查询 + JS 不启动动画双保险），只留静态蒙层 + 文字（原 T-splash-3 不变）。

### ④ "使用痕迹"星图（星点 = 你打开/编辑过的笔记）
- 数据：`localStorage["memoria.splash.stars.v1"] = {v:1, stars:[{p:相对路径, n:打开次数, t:最近时间, e:编辑次数}], updated}`，
  容量 **240**（按 `traceScore = n*0.4 + 最近度*2 + e*0.3` 淘汰）；**只在本机、只存路径/次数/时间，不含正文、不上报**。
- 绘制：每篇笔记 = 一颗星，位置 = 路径稳定哈希（同一篇每次都在同一处，用户能"养出"自己的星座）；
  亮度/大小按最近程度四档（<1 天 / <7 天 / <30 天 / 更久）；最近的星带主题色柔光；按使用时间连成淡淡"星轨"。
- 文案：「已点亮 {n} 颗星 · 你走过的笔记」；首次使用无痕迹 ⇒「你的星图会随使用点亮」（中英都加了键）。
- 记录：`app.js` 在**打开成功**（`setStatus(relPath, stats)` 同一行追加）与**保存成功**（同一行追加）调用
  `MemoriaSplashTrace.noteOpen/noteSave` ⇒ **零行漂移**、失败静默，绝不影响打开/保存。
- 首次冷启动验证：自动打开的文档已写入 1 颗星（探针 T-splash-10a `打开过的笔记星数=1`）。

## 验收（真机探针 v2：**21 PASS / 0 FAIL**）
| 新增 | 结果 | 证据 |
|---|---|---|
| T-splash-9 亮色主题蒙层 | ✅ | `data-theme=light`、`stats.theme=light`、品牌字 `rgb(0,0,0)`、`shot-light-theme-splash.png` |
| T-splash-9c 星点非静态 | ✅ | 画布 `animationName = memoria-splash-drift, memoria-splash-twinkle` |
| T-splash-10 使用痕迹 | ✅ | 真实埋点：`打开过的笔记星数=1`；注入 3 颗已知星后 `traceCount=3`、文案「已点亮 3 颗星 · 你走过的笔记」、`shot-usage-traces.png` |
| T-splash-2 复测（v2 后） | ✅ | 交错 A/B 3 轮：on 2233/2254/2321 vs off 2299/2306/2777 ⇒ **delta −52ms**（不慢于改前） |
| 门禁 | ✅ | 全仓 pytest **1649 passed / 0 failed**；node 0；i18n PASS；team_audit FAIL=0；12 剧本 12/12 |

## 关于"找人调研/研讨"
本会话是 teammate（subagent 层级），**不能再 spawn subagent（depth 限制）**，因此没有另找成员；
我按仓库既有 token/样式纪律自己做了取舍，并把可复核的判据都写进了测试与截图。若需要第二意见，
建议由 Lead 派另一个成员做一次"浅色主题 + 星图数据模型"的对抗复核。

## v2 改动文件（仍未 commit）
`src/memoria/ui/static/app/js/splash.js`（主题/星图/文案）、`app/css/app.css`（v2 主题渐变块）、
`app/i18n/zh-CN.js` / `en.js`（traces 文案）、`app/js/app.js`（2 处**同行**埋点，零行漂移）、
`tests/test_splash_animation.py`（+4 条：主题/动态/痕迹/纯函数），
`artifacts/agent/verify/todo/splash-animation/{probe_splash.mjs,verify.json,ab-interleaved.json,shot-*.png,REPORT.md}`。
