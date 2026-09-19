# UI 视觉语言对照与改进方向（Memoria vs dsh）

> **用途**：只谈**视觉细节**（色彩/排版/间距/形状/层次/动效/组件质感），**不谈布局与信息架构**。给出一份可评审的对照表 + 改进分档 + 不建议照搬项。
> **读者**：用户（拍板）、后续 UI 改动的人。
> **素材**：dsh 侧来自对只读检出 `dsh-src/`（上游 `deepseek-harness`）的穷尽检索（结论均带 `文件:行号`）；Memoria 侧来自对 `src/memoria/ui/static/**` 的实测计数（下文标注统计口径）。
> **状态**：待讨论（2026-09-19）。**实施状态唯一来源 = [../todo.md §13](../todo.md) 的 AG06**（本文不复制状态）。
> **前提**：用户意见是"更喜欢 dsh 的 UI 风格"；但 Memoria 现有风格**内部非常统一**（含后加的 agent 面板）。因此本文的目标不是"换成 dsh"，而是**找出"统一却不显高级"的具体差距**，逐项决定借不借。

---

## 0. 一句话结论

dsh 的观感来自四件很具体的事：**① 三层语义令牌（`--dsw-static-* → --dsw-alias-* → --dsw-specific-*`）；② 字号/圆角/描边都收敛在少数几档上，且比 Memoria 大一档；③ 用 0.5px 发丝描边 + 极淡柔光做层次，几乎不用重阴影；④ 状态变化都有 100–300ms 的过渡与明确的 focus 环。**
Memoria 现有风格统一，但**尺度偏小、档位偏碎、几乎不动、缺少令牌中间层** —— 这四条正是"看着整齐但不显精致"的来源。

---

## 1. 差异的本质（四条主轴）

| 主轴 | dsh | Memoria | 后果 |
|---|---|---|---|
| **令牌化** | 三层：静态色板 → 语义别名 → 专用；特性组件**只准**用 `--dsw-alias-*`（规范在 `docs/web-styling.md:17`，带测试门禁） | 一层：`theme/{memoria,light}.css` 直接给语义名（`--bg-primary`/`--accent`/`--border`…），组件间**大量直接写 16 进制与 rgba** | 换主题/微调对比度要改很多点；深色/浅色只能整体复制 |
| **视觉密度** | 正文 14px（且**用户可调** 12–17px），控件高 32–36px，列表行 8/10px 内距 | `app.css` 4984 行中 `font-size` 计数：**0.75rem(12px)×61、0.6875rem(11px)×55、0.625rem(10px)×27**、0.8125rem×17、0.875rem×6 | 全局比 dsh 小 1–2 档 ⇒ "紧凑但吃力"，细节显得密而碎 |
| **形状与层次** | 圆角收敛在 8/10/12/18/20/24/999（按钮胶囊 **18px**、弹窗 24px）；**0.5px 发丝描边**（规范 `docs/web-styling.md:25`）+ `corner-shape: superellipse(1.5)`；阴影 4 档 + `elevation-*`（描边画在 box-shadow 内，不占布局） | `app.css` 圆角：**2px×52、4px×19、3px×13、6px×9**、8px×4、7px×3、5px×2 ⇒ 十档、以 2–4px 为主；`box-shadow` 37 处、`backdrop-filter` 2 处 | 2px 圆角 + 1px 实线边框 = 典型的"工程师界面"；层次靠边框不靠光 |
| **反馈与动效** | 统一 motion 令牌（`--ds-ease-in-out`、0.1/0.2/0.3s）+ 组件级 100/120/150/160/200ms；**39 处 `prefers-reduced-motion`**；hover/selected 同色、focus 统一 `outline: 2px solid`（22 处） | `transition` 全文件仅约 12 处（0.06/0.1/0.12/0.18s，另 5 处 1.5s 属动画）；**`prefers-reduced-motion` = 0**；focus 依赖浏览器默认 | 交互"硬切"、键盘可达性弱；这是**最容易被感知**的差距 |

---

## 2. 逐维度对照

| 维度 | dsh（证据） | Memoria（实测） | 建议 |
|---|---|---|---|
| **色彩体系** | 三层令牌；品牌近黑/近白（`brand-primary`），"蓝"只用于 business/link（`design-platform.css:157-233`） | 单层：深色 `--bg-primary:#1e1e1e`/`--accent:#007acc`（`theme/memoria.css:5-15`）；浅色 `#ffffff`/`#0066bf`（`theme/light.css:16-31`） | 引入**中间层别名**（`--surface-1/2/3`、`--line-subtle`、`--ink-1/2/3`），新代码只写别名 |
| **主题机制** | `body[data-ds-dark-theme]` 属性切换 + `color-scheme`（`boot-theme.ts:31`） | 换 `theme/*.css` 文件（整体替换） | 保持文件级切换亦可；但**令牌名要统一**，避免深色主题模板里漏项 |
| **排版** | px 刻度 24/20/16/14/13/12/11 + `-strong`(500)；行高固定配对 22/20/18；**正文可调 12–17px**（`gradient-shadow-text.css:55-129`） | rem 刻度，主用 10/11/12px；行高零散 | ① 主用字号**上移一档**（10→11、11→12、12→13）；② 行高成对固定；③（可选）正文可调轴 |
| **字体族** | 含完整 CJK 回退链，注释解释**不加裸 `monospace`**（Windows 下 CJK 会落 SimSun）（`base.css:4-10`） | `font-family` 出现 14 处（多点重复声明） | 收敛到**一处**声明，并把这条 Windows 陷阱写进注释 |
| **间距** | 无 spacing 令牌，但高频值收敛在 4/6/8/10/12/16/24 | 未统计；部分靠 flex-gap | 定 4 的倍数口头规范即可，不必上令牌 |
| **圆角** | 收敛到 8/10/12/18/20/24/999；按钮胶囊 18px | 十档、以 2/3/4px 为主 | 收敛为 **4/6/8/12/999** 五档；主按钮从"2px 方角"改 999 或 8px |
| **描边** | 中性描边统一 **0.5px**（Chromium 画成 1 设备像素），状态/虚线保留 1px | 1px 实线为主 | 中性描边试 **0.5px**（视觉立刻变"薄"） |
| **阴影/层次** | 4 档阴影 + `elevation-*`（0.5px 描边内画 + 两层柔光）；弹窗背板 `bg-mask-1` + `blur(2px)` | 37 处 `box-shadow`、2 处 `backdrop-filter` | 定 2 档阴影（浮层/模态）+ 1 档柔光；浮层加极淡背板 |
| **动效** | 令牌 + 100–300ms；扫光/点阵/脉冲等"活着"的细节；`prefers-reduced-motion` 39 处 | 几乎无过渡；无 reduced-motion | **优先补**：hover/展开/淡入 120–160ms + 全站 `prefers-reduced-motion` 兜底 |
| **组件细节** | 按钮 4 形态（实底/幽灵/**0.5px 描边**/工具条），无独立 danger；输入框 focus 只换 border-color；列表 **hover=selected 同色**；**无斑马纹**；Tag 7 tone / Pill；自定义 8px 滚动条（`Button.module.css:38-71`、`Rows.module.css:13-20`、`scrollbar.css:17-26`） | 按钮/输入框/列表分散在各处样式；滚动条走系统默认 | ① 列表 hover 与选中**用同一底色**；② 滚动条统一细窄样式；③ 把"标签/胶囊"抽成组件 |
| **图标** | 内联 SVG、`currentColor`、16/14px 为主（79 个） | 混用字符/emoji/SVG？ | 长期统一到内联 SVG + `currentColor` |
| **CSS 组织** | CSS Modules + 6 张全局表；**禁** Tailwind/组件库（`web-styling.md:16`）；`data-*` 做变体 | 两个大文件（`app.css` 4984 行、`memoria.css`）+ 各模块 CSS | 不必改架构；但**新样式不再塞进 `app.css`**（见 §4-C） |

---

## 3. 诊断：为什么"整齐"却不像 dsh

1. **一切小一格**：10/11px 的字 + 2px 的角 + 1px 的线，三者叠加就是"工程师工具"的印象；dsh 是 14px + 18px 胶囊 + 0.5px 线。
2. **档位碎**：圆角 10 档、字号 9 档 ⇒ 相邻区域圆角各不相同，眼睛会读到"没对齐"。
3. **层次靠边框**：dsh 用"发丝线 + 柔光 + 极淡背板"造深度；Memoria 用 1px 实线把每个区域框起来。
4. **状态无过渡**：切换面板/展开目录/悬停行都是硬切，缺少"活的"感觉；且**完全没有** reduced-motion 兜底。

---

## 4. 改进分档（可分别拍板）

### A 档：零风险、纯增益（✅ **已于 2026-09-19 实施**，用户选择"直接把 A 档 5 项做掉"）
1. **补 `prefers-reduced-motion` 兜底**（现在 0 处）—— 无障碍合规，且不影响任何现有观感。
2. **补 hover/展开/淡入的过渡**（120–160ms，统一缓动）—— 只加 `transition`，不改色值不挪位置。
3. **字体族收敛到一处**，并把"Windows CJK 不加裸 `monospace`"这条陷阱写进注释。
4. **统一 focus 环**：`outline: 2px solid var(--theme-color); outline-offset: 2px` —— 键盘可用性直接提升。
5. **列表 hover 与选中同底色**（对齐 dsh 的做法）。

**实施记录（2026-09-19）**——改法一律"**追加在文件末尾 / 单行内替换**"，故既有 `app.css`(4984→5076 行) 与 `memoria.css`(639→654 行) 的**行号锚点零漂移**：

| 项 | 落地位置 | 实测证据 |
|---|---|---|
| ③ 字体族 | `theme/memoria.css` **末尾新增** `:root{--font-sans;--font-mono}`（**全仓唯一定义点**，`memoria.css:650,652`）；9 处散落的 `Consolas,…` 写法**逐行替换**为 `var(--font-mono)`（`app.css:1367/1406/2836/3816/3872/4663/4695/4729/4752`、`memoria.css:550`）；`body` 的 sans 链改为 `var(--font-sans)`（`memoria.css:67`） | 浏览器实测：`--font-mono` / `--font-sans` 均解析出值；`body` 计算字体族已含 `PingFang SC`/`Microsoft YaHei`；全仓**再无**裸 `Consolas…monospace` 写法（残留 0 处）。**修掉一个真坑**：`--font-mono` 此前**从未定义**（2836 原写作 `var(--font-mono, monospace)`）⇒ 代码区中文实际落到 SimSun |
| ① reduced-motion | `app.css` 末尾块（5002-5011） | 浏览器实测：样式表里能读到 `@media (prefers-reduced-motion: reduce)` 及其四条 `!important` 内规则 |
| ② 过渡 | `app.css` 末尾块（5016-5047）+ 两个时长/一条缓动令牌（4992-4997） | 浏览器实测：`.-tree-item` 计算 `transition-property: background-color, color, border-color, box-shadow`、`duration: 0.12s`、`timing: cubic-bezier(0.4,0,0.2,1)` |
| ⑤ 选中态 | `app.css` 末尾块（5069-5076）：`.-tree-item.active` 由 `--bg-active` 并入 `--accent-soft` + `inset 2px 0 0 var(--theme-color)` | 浏览器实测：带 `.active` 的树项计算背景 = `rgba(0,122,204,0.2)`（= `--accent-soft`）、`box-shadow = rgb(0,122,204) 2px 0 0 inset`；口径同步登记到 [agent-guide/02 §2.1](../reference/agent-guide/02-file-tree-and-nav.md)（原有锚点写错，一并修正） |
| ④ focus 环 | `app.css` 末尾块（5052-5067），**只作用于 `:focus-visible`**（鼠标点击不出现）⇒ 与各组件既有 `:focus` 并存 | 样式表里确认规则存在且被解析（`outline: 2px solid var(--theme-color); outline-offset: 2px`）。**⚠️ 视觉未取证**：harness 的 CDP 合成输入环境下 `:focus-visible` **恒不匹配**（连真实 Tab 键走进 `agent-send`/`agent-clear` 也是 `false`）⇒ 计算样式恒为 `0px none`，属**测量环境限制**、非规则问题；真机观感需用户确认 |

> 说明：A 档刻意**不改任何尺寸/间距/色相**，故不需要截图比对；唯一观感变化是 ⑤（浅色主题下树选中从灰蓝 `#e2e7f0` 变主题色淡底 + 左侧细线）。

### B 档：中等、需要试点（改观感，但要挨个过一遍页面）
6. **圆角收敛为 4/6/8/12/999 五档**，按"容器 > 内部控件 > 胶囊"分级替换（`app.css` 里 2px×52 处是主要工作量）。
7. **中性描边 1px → 0.5px**（分隔线/卡片外框），状态色与虚线保持 1px。
8. **主字号上移一档**（10→11、11→12、12→13）；行高成对固定。
9. **层次改为"两档阴影 + 柔光"**，浮层加极淡 `backdrop-filter`。
10. **细窄滚动条**（统一 8px、透明轨道、圆角拇指），与 dsh 一致。—— ✅ **已于 2026-09-19 实施**（**不经 U 拍板，用户直接下达指令**：「memoria 所有的滚条都太粗了，流行的 ide 方案是改很细而且在鼠标进入对应区域的时候才明显，否则几乎消失」）。实际落法比本项原设想更贴近 IDE：**轨道命中区 10px（含滑块两侧 4px 透明 border）⇒ 可见滑块仅 2px**、透明轨道/角落、三档不透明度（静止 0.18 / 指针进入该滚动区域 0.45 / 压在滑块上或拖拽 0.72）。**并顺手揭出一个根因**：`theme/memoria.css:73-74` 把 `scrollbar-width: thin` / `scrollbar-color` 写在 `body` 上，这两个标准属性**可继承**且在 Chromium ≥121 生效时会令浏览器**整块忽略** `::-webkit-scrollbar` ⇒ 全应用退回 Windows 原生粗滚动条；新块强制二者回 `auto` 收口。实施记录与逐项实测证据见 §4-B′；同轮还实现「顶部文件标签栏滚轮 = 横向滚动」（用户同一句里提出的第二件事）。

### B′. B-10 实施记录（2026-09-19）

| 项 | 落地位置 | 实测证据（harness 端口 8651） |
|---|---|---|
| 细滚动条 | `app/css/app.css` **末尾追加块** `5078-5136`（`:root` 五个 `--scrollbar-*` 令牌 + `html[data-theme="light"]` 三档覆盖 + 五条 `::-webkit-scrollbar*` 规则） | `#tabs` / `#editor-pane` / `#kp-list` 三个滚动容器：轨道 `10px`、滑块 `border-top-width 4px` + `background-clip: content-box` + `border-radius 999px`、`background-color` 解析为 `rgba(140,148,158,0.18)`（**非** `rgba(0,0,0,0)` ⇒ `var()` 在滚动条伪元素里解析成功）、轨道透明；`getComputedStyle(document.body).scrollbarWidth/scrollbarColor` 均为 `auto` |
| 标签栏滚轮 | `app/js/app.js` **末尾追加 IIFE** `12864-12888`（`#tabs` 上 `wheel` → `scrollLeft`，`ctrlKey` 不抢、无溢出时交还默认行为） | `#tabs.dataset.wheelBound = "1"`；8 标签溢出（`1024/496`）下派发 `deltaY=120` ⇒ `scrollLeft 0→120→240` 且 `defaultPrevented=true`，反向回退并在 `0` 钳住 |
| ⚠️ 未取证 | — | **「按需显形」0.45/0.72 两档与真实滚轮**：harness 无法派发真实鼠标移动/滚轮（`browser_click` 无 `mousemove`、hover 工具不触发 CSS `:hover`、OS 级输入 0 事件）⇒ 只有 CSSOM 静态证据（规则与变量原文已读到），**真实 hover 观感需真机确认**；标签栏因滚动条 6→10px 少掉的 4px 高度（文字未裁）观感亦待真机 |

> 说明：本项与 A 档同样**不换色相、不挪布局**；唯一尺寸后果是滚动容器内容区比改前少 4px（轨道 6→10px），换来的可见滑块由 6px 降到 2px。

### C 档：大改、建议单独评审
11. **引入 `--dsw` 式中间别名层**（`surface/line/ink` 三级）并把现有组件逐步迁移 —— 这是"以后能整体调风格"的前提，但要动所有样式。
12. **正文字号可调轴**（用户设置里 12–17px）。
13. **`app.css` 拆分**：新样式按模块落文件，`app.css` 只留全局与布局（现在 4984 行的单文件是后续所有 UI 改动的税）。

---

## 5. 不建议照搬的部分

| 项 | 原因 |
|---|---|
| `corner-shape: superellipse(1.5)` | 依赖很新的 Chromium；Memoria 目标含旧 WebView2，回退后形状会变，属"高成本低收益" |
| 品牌色改近黑/近白 | dsh 的品牌观感来自其产品定位；Memoria 的蓝是既有识别度（`--accent`），换掉会伤一致性 |
| 字号单位从 rem 改 px | dsh 是 px；Memoria 用 rem 更好（跟随系统缩放）。**保留 rem**，只调档位 |
| 无 `danger` 按钮形态 | Memoria 有"删除文件/删除 KP"等真实危险操作，**保留**明确的危险色按钮 |
| 斑马纹 | dsh 没有；Memoria 表格也少，不需要 |

---

## 6. 待拍板

| ID | 问题 | 选项 | 影响 |
|---|---|---|---|
| **U1** | A 档（5 项零风险改进）是否直接做？ | ✅ **已定：① 全做**（2026-09-19 用户选择，实施记录见 §4-A） | — |
| **U2** | 圆角收敛（B-6） | ① 收敛为 4/6/8/12/999（推荐） ② 只把主按钮改胶囊 ③ 不动 | 观感变化最大的一项 |
| **U3** | 主字号上移一档（B-8） | ① 全站上移 ② 只上移面板/长文本区 ③ 不动 + 提供字号设置 | 信息密度会下降，需接受 |
| **U4** | 0.5px 描边（B-7） | ① 试做分隔线 ② 分隔线+卡片框 ③ 不做 | 细微但"精致感"关键 |
| **U5** | 别名令牌层（C-11） | ① 现在做 ② 等 UI 改完再统一做 ③ 不做 | 决定未来改风格的代价 |
| **U6** | 正文可调字号（C-12） | ① 做 ② 不做 | 与 U3 相关 |

---

## 7. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-19 | 初版（待讨论）：四条主轴（令牌化 / 视觉密度 / 形状与层次 / 反馈与动效）+ 12 维度对照表（dsh 侧带 `文件:行号`，Memoria 侧带实测计数）+ 4 条诊断 + A/B/C 三档改进（A 5 项零风险、B 5 项试点、C 3 项大改）+ 5 项不照搬及原因 + U1–U6 待拍板。登记 `docs-management.md §4.2`，状态行落在 `todo.md §13`（AG06） |
| 2026-09-19 | **A 档 5 项实施完毕**（U1 = ①）：字体族收敛（新增 `--font-sans`/`--font-mono` 唯一来源，9 处散落写法改 `var()`，**顺带修掉 `--font-mono` 从未定义 ⇒ 代码区中文落 SimSun 的真坑**）、`prefers-reduced-motion` 兜底、四属性交互过渡（120ms + 统一缓动）、`:focus-visible` 统一焦点环、树选中态并入 `--accent-soft` + 左侧主题色细线；改法全部"末尾追加 / 单行替换"⇒ 行号锚点零漂移。逐项实测证据见 §4-A「实施记录」（④ 的视觉表现因 harness CDP 环境 `:focus-visible` 恒不匹配而**未取证**，已如实标注）。B/C 档与 U2–U6 仍待拍板 |
| 2026-09-19 | **B-10（细窄滚动条）实施完毕**（**不经 U 拍板，用户直接指令**；同一句里还要求"顶部文件标签 bar 鼠标在这个区域滚轮应该可以控制滚条"）：滚动条改为"轨道命中区 10px + 4px 透明 border 内缩 ⇒ **可见滑块 2px** + 透明轨道 + 三档不透明度（0.18 / 0.45 / 0.72）"，并**修掉根因** —— `memoria.css:73-74` 的 `scrollbar-width: thin`/`scrollbar-color` 写在**可继承**的 `body` 上，在 Chromium ≥121 生效时会让浏览器整块忽略 `::-webkit-scrollbar` 而退回 Windows 原生粗滚动条，故新块用 `!important` 把二者强制回 `auto` 并收口 `memoria.css:76-80` 与 `light.css:86-91` 两处旧定义（滚动条外观此后**只此一处**维护）；新增 `app.js` 末尾 IIFE 把 `#tabs` 区域内的滚轮纵向增量转成横向滚动（与 `bindGraphGroupTabWheel` 同口径）。改法仍为"末尾追加"⇒ `app.css` 5076→5136 行、`app.js` 12862→12888 行，**既有行号锚点零漂移**。实测证据与**未取证项**（真实 hover / 真实滚轮在 harness 无法派发，只有 CSSOM 静态证据）见 §4-B′。B-6/7/8/9 与 U2–U6 仍待拍板 |
