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
| **图标** | 内联 SVG、`currentColor`、16/14px 为主（79 个） | 混用字符/emoji/SVG？ | 长期统一到内联 SVG + `currentColor`。**2026-09-20 起**「三角」这一族已收敛到**全库一枚**：主题区 glyph（文件树 twisty / 目录 / 文件类型）走 `file-tree.js` 的内联 SVG；`<details>/<summary>` 的展开标记与格式栏两个色板按钮的下拉 caret 由 `agent-panel.js` 末尾块从**同一枚** `triangleRight` 派生 data-URI mask 注入（不再有 UA 原生标记与 U+25BE 字符） |
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
| ③ 字体族 | `theme/memoria.css` **末尾新增** `:root{--font-sans;--font-mono}`（**全仓唯一定义点**，`memoria.css:650,652`）；9 处散落的 `Consolas,…` 写法**逐行替换**为 `var(--font-mono)`（`app.css:1339/1406/2836/3816/3872/4663/4695/4729/4752`、`memoria.css:550`）；`body` 的 sans 链改为 `var(--font-sans)`（`memoria.css:67`） | 浏览器实测：`--font-mono` / `--font-sans` 均解析出值；`body` 计算字体族已含 `PingFang SC`/`Microsoft YaHei`；全仓**再无**裸 `Consolas…monospace` 写法（残留 0 处）。**修掉一个真坑**：`--font-mono` 此前**从未定义**（2836 原写作 `var(--font-mono, monospace)`）⇒ 代码区中文实际落到 SimSun |
| ① reduced-motion | `app.css` 末尾块（5002-5011） | 浏览器实测：样式表里能读到 `@media (prefers-reduced-motion: reduce)` 及其四条 `!important` 内规则 |
| ② 过渡 | `app.css` 末尾块（5016-5047）+ 两个时长/一条缓动令牌（4992-4997） | 浏览器实测：`.-tree-item` 计算 `transition-property: background-color, color, border-color, box-shadow`、`duration: 0.12s`、`timing: cubic-bezier(0.4,0,0.2,1)` |
| ⑤ 选中态 | `app.css` 末尾块（5069-5076）：`.-tree-item.active` 由 `--bg-active` 并入 `--accent-soft` + `inset 2px 0 0 var(--theme-color)` | 浏览器实测：带 `.active` 的树项计算背景 = `rgba(0,122,204,0.2)`（= `--accent-soft`）、`box-shadow = rgb(0,122,204) 2px 0 0 inset`；口径同步登记到 [agent-guide/02 §2.1](../reference/agent-guide/02-file-tree-and-nav.md)（原有锚点写错，一并修正） |
| ④ focus 环 | `app.css` 末尾块（5052-5067），**只作用于 `:focus-visible`**（鼠标点击不出现）⇒ 与各组件既有 `:focus` 并存 | 样式表里确认规则存在且被解析（`outline: 2px solid var(--theme-color); outline-offset: 2px`）。**⚠️ 视觉未取证**：harness 的 CDP 合成输入环境下 `:focus-visible` **恒不匹配**（连真实 Tab 键走进 `agent-send`/`agent-clear` 也是 `false`）⇒ 计算样式恒为 `0px none`，属**测量环境限制**、非规则问题；真机观感需用户确认 |

> 说明：A 档刻意**不改任何尺寸/间距/色相**，故不需要截图比对；唯一观感变化是 ⑤（浅色主题下树选中从灰蓝 `#e2e7f0` 变主题色淡底 + 左侧细线）。

### B 档：中等、需要试点（改观感，但要挨个过一遍页面）
6. **圆角收敛为 4/6/8/12/999 五档**，按"容器 > 内部控件 > 胶囊"分级替换（`app.css` 里 2px×52 处是主要工作量）。—— ✅ **已于 2026-09-19 实施**
7. **中性描边 1px → 0.5px**（分隔线/卡片外框），状态色与虚线保持 1px。—— ✅ **源码已改，但实测在 DPR=1 下无视觉收益**（见下方「实施记录 A」第 2 行）
8. **主字号上移一档**（10→11、11→12、12→13）；行高成对固定。—— ❌ **按建议未做**：应用已有「显示 → 字号 / 界面缩放」（`display-settings.js:11-18` 的 `previewFontSize` 与 `uiScale`），再动 CSS 档位会与之职责重叠、且白丢信息密度。**该条同时关闭 U3 与 U6**（正文可调轴早已存在）。
9. **层次改为"两档阴影 + 柔光"**，浮层加极淡 `backdrop-filter`。—— ✅ **已于 2026-09-19 实施**（记录见下方「实施记录 A」）
10. **细窄滚动条**（统一 8px、透明轨道、圆角拇指），与 dsh 一致。—— ✅ **已于 2026-09-19 实施**（**不经 U 拍板，用户直接下达指令**：「memoria 所有的滚条都太粗了，流行的 ide 方案是改很细而且在鼠标进入对应区域的时候才明显，否则几乎消失」）。实际落法比本项原设想更贴近 IDE：**轨道命中区 10px（含滑块两侧 4px 透明 border）⇒ 可见滑块仅 2px**、透明轨道/角落、三档不透明度（静止 0.18 / 指针进入该滚动区域 0.45 / 压在滑块上或拖拽 0.72）。**并顺手揭出一个根因**：`theme/memoria.css:73-74` 把 `scrollbar-width: thin` / `scrollbar-color` 写在 `body` 上，这两个标准属性**可继承**且在 Chromium ≥121 生效时会令浏览器**整块忽略** `::-webkit-scrollbar` ⇒ 全应用退回 Windows 原生粗滚动条；新块强制二者回 `auto` 收口。实施记录与逐项实测证据见下方「实施记录 B」；同轮还实现「顶部文件标签栏滚轮 = 横向滚动」（用户同一句里提出的第二件事）。

### 实施记录 A：B-6 圆角 / B-7 描边 / B-9 阴影（2026-09-19）

**改法**：三处都在**原位改数值 / 换 `var()`**（**行数不变** ⇒ `app.css`/`memoria.css` 既有行号锚点零漂移，比"末尾追加覆盖"更干净、不会留下两份口径）；只有"必须新增声明"的两件事（阴影令牌、背板模糊）追加在文件末尾（`app.css:5110-5140`）。

| 项 | 落地 | 实测证据（harness 端口 8652，Chromium，DPR=1，797×776） |
|---|---|---|
| **B-6 圆角** | 1/2/3px→**4px**、5/7px→**6px**、10px→**12px**、`2px 0 0 2px`→`4px 0 0 4px`、`2px 2px 0 0`→`4px 4px 0 0`、`5px 5px 0 0`→`6px 6px 0 0`、`0 0 5px 5px`→`0 0 6px 6px`；**`.modal-box` 4px→12px**（唯一"大容器"档位落地。选它是因为实测 `.-modal-header`/`.-modal-footer` **无自身底色**、只有边线，所以放大圆角不会在角上露出直角；若换成有底色的子块则会露角） | 全页 712 元素取值分布（**6 个不同值**）：`0px`×623 / `4px`×74 / `12px`×9 / `4px 4px 0 0`×3 / `6px`×2 / `50%`×1；**1/2/3/5/7/10px 全部清零**。点值：`.-modal-box` = **12px**、`.-agent-input` = 4px ✓；`#tabs .tab` = `0px` —— **这是正确的**，`.tab` 从未声明过圆角（方形标签是原设计），非缺陷 |
| **B-7 描边** | app.css **95 处** + memoria.css **14 处** `1px solid var(--border[*])` 改 **0.5px**（含 `.markdown-body hr`、以及两个硬编码中性色 `#ccc`/`#d0d5dd`）；**保留 1px 的 19 处**＝状态色（`--theme-color`/`--error`/`rgba(244,71,71,.35)`）6 + 图标色 `currentColor` 2 + 虚线 10 + 调色板私有变量 `var(--border-color, #d0d0d0)` 7（该组属独立的调色板内部链，未动） | ⚠️ **关键负面结论**：全部声明确实写进了 CSSOM（105 条规则含 `0.5px`，无任何 1px 覆盖），但**计算值一律是 `1px`、全页 `0.5px` 计数 = 0** —— DPR=1 下 Blink 把非 0 的 <1px 边框**上取整到 1 个设备像素**，因此**在 100% 缩放的 Windows 上视觉上是 no-op**。受控探针复核：注入 `border-top: 0.5px` 与 `1px`（同色 `rgb(60,60,60)`）两块，`getComputedStyle` **都返回 `1px`**。真正细线只出现在 **DPR≥2**（200% 缩放 / HiDPI）——那时 0.5px = 1 设备像素才是真发丝。**125%/150% 缩放下的表现未取证**（无法改 DPR）。**待用户定夺的替代路径**（本轮未做）：① 保留 0.5px（HiDPI 收益、1x 无害）＋把 `--border` 调淡一档（这是 1x 下唯一能真正"变轻"的手段）；② 用 `box-shadow` 画线（同样受 1 设备像素下限约束，不解决）；③ 撤回 B-7 |
| **B-9 阴影** | 10 处浮层投影就地换 **`var(--shadow-soft)` / `var(--shadow-float)` / `var(--shadow-overlay)`**：`soft` → `.-edge-target-datalist`；`float` → `.-toolbar-search-panel`、`.-context-menu`、`.-link-target-suggest`、`.-fmt-dropdown-menu`、`.-tb-file-menu`、`.-tb-file-submenu`；`overlay` → `.-flash-error`/`.-flash-info`、`.-color-picker`、`.-lightbox-image`、`.-modal-box`。每档是 dsh 式**近层 + 远层柔光**两层结构（此前是 10 个各写各的单层值，10 种半径/浓度）。**按语义保留原样**（不是投影）：15 处 `inset` 指示线、4 处 `0 0 0 Npx` 指示环、`.-win-btn--max` 的 `4px -4px 0 0` 两笔（"还原"图标本身）、2 个滑块拇指。模态背板 `background` 0.55→**0.42** + 新增 `backdrop-filter: blur(2px)` | 令牌解析 ✓：`--shadow-soft` = `0 1px 4px rgba(0,0,0,0.2)`、`--shadow-float` = `0 4px 12px rgba(0,0,0,0.28), 0 12px 32px rgba(0,0,0,0.16)`、`--shadow-overlay` = `0 8px 24px rgba(0,0,0,0.34), 0 24px 64px rgba(0,0,0,0.28)`。`.-modal-box` 计算 `box-shadow` = overlay **双层**；`.-tb-file-menu` / `.-tb-file-submenu` / `.-fmt-dropdown-menu` / `.-toolbar-search-panel` 计算值 = float **双层**且与令牌串逐字一致；`.-modal-backdrop` 计算 `background: rgba(0,0,0,0.42)` + `backdrop-filter: blur(2px)` ✓（模态已实开）
| ⚠️ **未取证** | — | ① **`.context-menu`、`.-link-target-suggest`、`.-edge-target-datalist`、`.-flash-*`、`.-color-picker`、`.-lightbox-image`、`.-kp-tag-pick`、`8px` 档实例当前都不在 DOM 里**（需特定交互才创建）⇒ 只核到 CSSOM 规则，未核计算值；② 真机 WebView2 的观感（12px 模态圆角、双层阴影的柔和度、背板模糊的性能与观感、4px 控件圆角是否偏圆）；③ 已落盘两张截图（设置模态 / 默认主界面）**本轮未逐像素比对"改前 vs 改后"**（没有改前基线） |

> **一处必须说清的取舍**：**浮层菜单的圆角没有跟着提升档位**（仍是 4px 档）。原因是这些菜单的 `padding` 只有 4px 垂直、0 水平，子项 hover 底色**整宽铺满** ⇒ 圆角一旦超过内边距就会在角上"露底"；常规解法是给菜单加 `overflow: hidden`，但那会**裁掉绝对定位的子菜单**（`.-tb-file-submenu` 就可能是子元素）。所以按"圆角 ≤ 内边距"的纪律停在 4px。

> 说明：B-6/B-9 的观感变化集中在"控件比原来圆一档 + 模态明显更圆 + 引用层次由硬边变成两层柔光"；B-7 在 100% 缩放下与本轮之前**完全一致**。

### 实施记录 B：B-10 细滚动条（2026-09-19；上一轮登记时称 §4-B′）

| 项 | 落地位置 | 实测证据（harness 端口 8651） |
|---|---|---|
| 细滚动条 | `app/css/app.css` **末尾追加块** `5046-5104`（`:root` 五个 `--scrollbar-*` 令牌 + `html[data-theme="light"]` 三档覆盖 + 五条 `::-webkit-scrollbar*` 规则） | `#tabs` / `#editor-pane` / `#kp-list` 三个滚动容器：轨道 `10px`、滑块 `border-top-width 4px` + `background-clip: content-box` + `border-radius 999px`、`background-color` 解析为 `rgba(140,148,158,0.18)`（**非** `rgba(0,0,0,0)` ⇒ `var()` 在滚动条伪元素里解析成功）、轨道透明；`getComputedStyle(document.body).scrollbarWidth/scrollbarColor` 均为 `auto` |
| 标签栏滚轮 | `app/js/app.js` **末尾追加 IIFE** `12864-12888`（`#tabs` 上 `wheel` → `scrollLeft`，`ctrlKey` 不抢、无溢出时交还默认行为） | `#tabs.dataset.wheelBound = "1"`；8 标签溢出（`1024/496`）下派发 `deltaY=120` ⇒ `scrollLeft 0→120→240` 且 `defaultPrevented=true`，反向回退并在 `0` 钳住 |
| 细滚动条再收一档（同日更晚） | 同一末尾块，**原位改两个数值、行数零漂移**：`html *::-webkit-scrollbar { height: 6px → 3px }`（app.css:5084）、滑块 `border-width: …4px → 1px`（app.css:5097） | 用户："图谱的子图页签的滚轮也要同步做细" → 追问后："我发现他做的和显示区域的文件页签一样粗，都要细一点"。**harness 8659** 实测（深/浅各一遍）：`#tabs`、`#sidebar-graph-group-tabs` gutter 均 **3px**（改前 6px）、首标签 **27 → 30px**；`#tab-bar` / `.-graph-group-bar` 仍 **34px**（`--bar-h` 对齐未破）；纵向 `#editor-pane` / `#hist-list` 仍 **10px**；两条滚轮 `defaultPrevented=true` 且 `scrollLeft` 位移 |
| **细滚动条覆盖「浮层」**（`::picker(select)`，2026-09-23） | `app/css/app.css` 末尾 `@supports (appearance: base-select)` 块内六条 `…::picker(select)::-webkit-scrollbar*`（**逐条镜像**上面那套令牌与几何：`--scrollbar-hit` / `--scrollbar-inset` / `--scrollbar-thumb-idle\|hover\|drag`） | 用户：「字体设置的下拉滚条请你保持和其他统一的细滚条，纳入 ui 设计规范」。**为什么必须显式镜像**：`html *::-webkit-scrollbar`（app.css:5082-5108）**够不到** picker —— 它在 top layer 且是伪元素，实测浮层自身滚条一直是**平台默认 15px**（把全局宽度改成 33px 也只让面板内容变窄，浮层滚条纹丝不动）。可读判据：`getComputedStyle` **读不了**链式滚动条伪元素（恒 `""`）⇒ 改用**布局量**：浮层内容盒 476px（select 478），首 `<option>` 宽 **466 = 476 − 10**（平台默认会是 ≈461）。**两条硬约束**（探针实测）：① **必须带 `::picker(select)`**，只写 `select…::-webkit-scrollbar` 无效；② **不能**同时写 `scrollbar-width/scrollbar-color` —— 标准属性一非 `auto`，Chromium 就整块忽略 `::-webkit-scrollbar`（实测 466 vs 443），只剩"细 + 单色"，丢掉内缩与三档 |
| ⚠️ 未取证 | — | **「按需显形」0.45/0.72 两档与真实滚轮**：harness 无法派发真实鼠标移动/滚轮（`browser_click` 无 `mousemove`、hover 工具不触发 CSS `:hover`、OS 级输入 0 事件）⇒ 只有 CSSOM 静态证据（规则与变量原文已读到），**真实 hover 观感需真机确认**；标签栏因滚动条 6→10px 少掉的 4px 高度（文字未裁）观感亦待真机；**同日晚再收一档（横向 3px）后的真机观感**（3px 是否"够细"、静止档 alpha 0.18 下 2px 滑块是否仍可见）同样待真机；**浮层的 2px 滑块**同理（`::picker(select)` 的滚动条无法截图/hover，只有 `466 = 476 − 10` 这一条布局证据） |

> 说明：本项与 A 档同样**不换色相、不挪布局**；唯一尺寸后果是滚动容器内容区比改前少 4px（轨道 6→10px），换来的可见滑块由 6px 降到 2px。

### 实施记录 C：设置区「可折叠子版块」+ 字体下拉（2026-09-23，用户要求"纳入 ui 设计规范"）

来源 = 人四句：「设置中 文字还要添加字体类型，这个字体是 markdown 预览的文字和 agent 对话栏中渲染的文字，还支持修改顶栏 "MEMORIA" 的字体，不同语言可以设置不同字体」→「你新添加的这些框的 ui 样式违反整体设计……你应该给下拉可选样式而不是输入」→「下拉不用全展开，可以加滚条」→「字体设置的下拉滚条请你保持和其他统一的细滚条，纳入 ui 设计规范；设置其他地方也可也效仿 Agent 页签的子版块设计可展缩」。

| 规范项 | 落点 | 口径（实测证据） |
|---|---|---|
| **字体档一律是「可定制原生 select」** | `app/css/app.css` 末尾 `@supports (appearance: base-select)` 块（控件由 `display-settings.js::fontSelect()` 产出；两个 CSS 变量的写者是 `applyFonts()`） | 用 `appearance: base-select` 而不是自造下拉：键盘 / IME / 无障碍语义仍由浏览器给。**作用域刻意收窄**（只命中 `[data-display-font-lang]` / `[data-display-setting="fontBrand"]`）⇒ `#display-theme` / `#display-language` 仍是 `appearance: auto`。`@supports` 兜底：老浏览器整块失效、退回原生浮层 |
| **设置区下拉统一字体与高度** | `app/css/app.css` 末尾 `.-settings-field select { font-family: var(--font-sans); min-height: 1.75rem }` | `base-select` 会继承父级字体（原生控件默认吃 UA 的 `Arial`），且它是 flex 盒、闭合态比原生**矮 2px** ⇒ 不统一就会让同页 5 个下拉互相不对齐（正是人抱怨的同一类问题）。实测（harness 8663）：五个下拉 `fontFamily` 同一串、`height` 全 `28px`、`padding` 全 `4px 6px`、宽 `478px` |
| **浮层限高 + 用全站细滚条** | 同 `@supports` 块：`::picker(select) { max-height: 8.75rem; overflow-y: auto; overscroll-behavior: contain }` + 六条 `::-webkit-scrollbar*` | 限高档位取 `8.75rem`（与既有可滚浮层 `.-edge-target-datalist` 同档）⇒ 16 行内容（384px）只画约 6 行、其余滚。滚条见「实施记录 B」最后一行（`466 = 476 − 10`） |
| **浮层的圆形/描边/阴影** | 同 `::picker(select)` 规则 | `border-radius: 4px`（B-6 档）+ `border: 0.5px solid var(--border)`（B-7 档）+ `box-shadow: var(--shadow-float)`（B-9 档）+ `background: var(--bg-secondary)` ⇒ 与既有浮层菜单同一套语言，不是系统菜单长相 |
| **设置区「折叠子版块」= 统一组件** | `graph-settings.js::foldSettingsSections()`（末尾追加）+ 调用点**同行追加**在 `setSettingsTab()` 的 if/else 链之后；样式 `.-settings-section` / `-head` / `-body` | 六个页签（2D / 3D / 节点群 / 检索 / 检查 / 显示）的 `<section class="-settings-section">` 一律折成 `<details open>` + `<summary class="-settings-section-head">`。**一条共享路径**：六个 renderer 一行未改、字段 id 与事件绑定原样保留（移动节点，不重建 HTML）。**默认展开**：是"可收起"而非"默认藏起来"。三角标记复用 `agent-panel.js` 注入的**全局** `details > summary::before`（2026-09-20 那枚 dsh 三角），不另画 |
| **折叠头的排版 = 应用既有小标题那一档** | `app/css/app.css` 末尾 `.-settings-section-head { font-size: 0.75rem; font-weight: 600; padding: 0.5rem 0 }` | 对齐 `.-settings-heading`（`app.css:912-917`）⇒ **折叠前后观感一致**（只有 `padding: 0.5rem 0` 取代原来的 `margin-bottom: 8px`，上下 8px 兼作点击热区）；Agent 页那两个头也随之并入同一规范 |

实测（harness **8663**，Chromium 142；两处 JS/CSS 回归全绿）：六页 `details` 数 = `3 / 3 / 1 / 1 / 1 / 4`、残留 `<section>` **0**、全部 `open=true`、summary 文本 = 原 `<h3>` 文本、内部 `<h3>` **0**；Agent 页仍是 2 个 `details`（「对话」开 /「能力插件」合）且 `#agent-settings` / `#agent-save-config` / `#agent-base-url` 仍在、`.-plugins-row = 1`；**真实点击 `<summary>`** ⇒ `open` true→false、`details` 高 **124 → 33**、后续小节整体上移 91px、`elementFromPoint` 同点由 `SELECT` 变为下一节的 `SUMMARY`（body 确实不再绘制）、`.-settings-form` 仍可滚（`scrollHeight 891 > clientHeight 519`）；折叠后字段仍生效（`#display-theme → light` ⇒ `<html data-theme="light">` + `localStorage["-theme-mode"]="light"`）。**未取证**：① 浮层 2px 滑块的**真机观感**（无法截图、无法 hover）；② `details` 展开/收起**动画**未做（原生瞬时，故无过渡项）；③ `base-select` 在**不支持** `appearance: base-select` 的老 WebView2 上的观感（整块 `@supports` 失效 ⇒ 退回原生浮层，本轮无老版本可测）。

> 口径澄清（避免误读）：`appearance: base-select` **只是"让原生 select 可写样式"**，不是自造控件 —— 值与 `change` 语义、键盘、IME 全由浏览器负责；这也是它优于"自绘下拉"的核心理由（自绘还要另做 `position: fixed` + 视口避让，因为设置弹窗 `#settings-body` 是 `overflow: hidden`、`.-settings-form` 是 `overflow-y: auto`，绝对定位浮层会被裁）。

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
| **U2** | 圆角收敛（B-6） | ✅ **已定：① 收敛为 4/6/8/12/999**（2026-09-19「B 全做」，记录见 §4 实施记录 A） | — |
| **U3** | 主字号上移一档（B-8） | ✅ **已定：③ 不动**（2026-09-19「B 全做」时按建议未做；已有 `uiScale` / `previewFontSize` 设置） | 信息密度不下降 |
| **U4** | 0.5px 描边（B-7） | ✅ **已定并已实施（2026-09-19）：保留 0.5px ＋ 追加 `--border-sep` 专用档** —— 深色 `#3c3c3c`→**`#303030`**、浅色 `#d6d6d6`→**`#e8e8e8`**（各自对 `--bg-secondary` 的对比 1.388→1.161、1.344→1.134，均 −16%）；消费点 **16 处** chrome 横条/区域竖边。**顶栏刻意除外**：深色 `--bg-toolbar` 就是 `#3c3c3c`（旧边框本就"看不见"，换新档反而冒出深线 1.196）、浅色 `--bg-toolbar #e7e7e7` 与新档 `#e8e8e8` 几乎同色（1.009，线会消失）。**为何不直接调淡 `--border`**（实测数据）：它是**19 条规则**"tertiary 背景 + 自身描边"的轮廓色（`.-agent-input` / `.-agent-history-select` / `.-settings-field select` / `.-config-btn` / `#graph-controls button` / `.tab` …），而 `--bg-tertiary` 正是 `#333333`/`#ececec` ⇒ 调淡会让这些控件轮廓**消失**；故本档只给"分隔线"用 | 1x 下唯一可见手段；已完成 |
| **U5** | 别名令牌层（C-11） | ① 现在做 ② 等 UI 改完再统一做 ③ 不做 —— **仍未定**（B 档已收口，是这个问题的决策时机） | 决定未来改风格的代价 |
| **U6** | 正文可调字号（C-12） | ✅ **已定：② 不做 —— 早已存在**（`display-settings.js:11-18` 的 `previewFontSize` 12–28px + `uiScale` 0.8–1.5，Ctrl+=/-/0） | — |

---

## 7. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-19 | 初版（待讨论）：四条主轴（令牌化 / 视觉密度 / 形状与层次 / 反馈与动效）+ 12 维度对照表（dsh 侧带 `文件:行号`，Memoria 侧带实测计数）+ 4 条诊断 + A/B/C 三档改进（A 5 项零风险、B 5 项试点、C 3 项大改）+ 5 项不照搬及原因 + U1–U6 待拍板。登记 `docs-management.md §4.2`，状态行落在 `todo.md §13`（AG06） |
| 2026-09-19 | **A 档 5 项实施完毕**（U1 = ①）：字体族收敛（新增 `--font-sans`/`--font-mono` 唯一来源，9 处散落写法改 `var()`，**顺带修掉 `--font-mono` 从未定义 ⇒ 代码区中文落 SimSun 的真坑**）、`prefers-reduced-motion` 兜底、四属性交互过渡（120ms + 统一缓动）、`:focus-visible` 统一焦点环、树选中态并入 `--accent-soft` + 左侧主题色细线；改法全部"末尾追加 / 单行替换"⇒ 行号锚点零漂移。逐项实测证据见 §4-A「实施记录」（④ 的视觉表现因 harness CDP 环境 `:focus-visible` 恒不匹配而**未取证**，已如实标注）。B/C 档与 U2–U6 仍待拍板 |
| 2026-09-19 | **B-10（细窄滚动条）实施完毕**（**不经 U 拍板，用户直接指令**；同一句里还要求"顶部文件标签 bar 鼠标在这个区域滚轮应该可以控制滚条"）：滚动条改为"轨道命中区 10px + 4px 透明 border 内缩 ⇒ **可见滑块 2px** + 透明轨道 + 三档不透明度（0.18 / 0.45 / 0.72）"，并**修掉根因** —— `memoria.css:73-74` 的 `scrollbar-width: thin`/`scrollbar-color` 写在**可继承**的 `body` 上，在 Chromium ≥121 生效时会让浏览器整块忽略 `::-webkit-scrollbar` 而退回 Windows 原生粗滚动条，故新块用 `!important` 把二者强制回 `auto` 并收口 `memoria.css:76-80` 与 `light.css:86-91` 两处旧定义（滚动条外观此后**只此一处**维护）；新增 `app.js` 末尾 IIFE 把 `#tabs` 区域内的滚轮纵向增量转成横向滚动（与 `bindGraphGroupTabWheel` 同口径）。改法仍为"末尾追加"⇒ `app.css` 5076→5136 行、`app.js` 12862→12888 行，**既有行号锚点零漂移**。实测证据与**未取证项**（真实 hover / 真实滚轮在 harness 无法派发，只有 CSSOM 静态证据）见 §4「实施记录 B」。B-6/7/8/9 与 U2–U6 仍待拍板 |
| 2026-09-19 | **B 档其余四项处置完毕**（用户选「B 全做」，并按建议把 B-8 排除）：**B-6 圆角** 收敛为 4/6/8/12/999（+50% 圆形、0），全页 712 元素只剩 6 个取值、1/2/3/5/7/10px 清零（4px×74 / 12px×9 / 6px×2…）；**B-9 阴影** 10 处浮层投影收敛为 `--shadow-soft/float/overlay` 三档令牌（每档近层+远层柔光），模态背板 0.55→0.42 + `backdrop-filter: blur(2px)`；**B-7 0.5px 描边** 109 处已改，但**实测在 DPR=1 下计算值仍是 1px（Blink 把非 0 的 <1px 边框上取整到 1 设备像素）⇒ 100% 缩放下视觉无变化**，仅 DPR≥2 有真发丝收益，已在 U4 提出「把 `--border` 调淡」这一 1x 下唯一可见的替代；**B-8 未做**（已有 `uiScale`/`previewFontSize`，避免两套口径）。**改法与前两轮不同**：B-6/B-7/B-9 全是**原位改数值 / 换 `var()`**（**行数不变** ⇒ 行号锚点零漂移，且不留两份口径），只有阴影令牌与背板模糊追加在 `app.css:5110-5140`。**一处刻意取舍**：浮层菜单圆角**不提升档位**（padding 仅 4px 垂直/0 水平，子项 hover 整宽铺底 ⇒ 圆角超内边距会"露底"，而加 `overflow:hidden` 会裁掉绝对定位的子菜单）。逐项实测与未取证项见 §4「实施记录 A」；U2/U3/U6 已定、U4 派生新问题、U5 仍待定 |
| 2026-09-19 | **对话面板前两行 ↔ 显示区上两栏 对齐 + 标签栏横向滚条收窄上贴**（用户反馈，**不属 B/C 档设计项**，故不进 U 表）：`app.css` 末尾新增 `5170-5190` 块 + 滚条规则**原行改值**（行数零漂移 ⇒ `5046-5104`/`5138-5168` 两组既有锚点未移动）。**先量后改**（harness 8654，root 17.6px）：改前 `.-agent-head` **36.75** / `.-agent-history` **46.16** vs `#tab-bar` **39.5** / `#editor-header` **41.38**；改后 **39.5/78**（与 `#tab-bar` 逐像素一致）与 **41.36/119.36**（差 0.02px），`.-agent-messages` 顶边 121.41→119.36 也对齐编辑区。滚条：横向轨道 10→**6px**、滑块 `border-width: 0 4px 4px`（上 0）⇒ 可见 2px 且贴上沿（改前 10px 轨道居中滑块在标签下留 10px 空带），纵向仍 10px / 可见 2px。详见 `reference/agent-guide/01` §6 与 §7 |
| 2026-09-19 | **统一「栏高」`--bar-h`＝1.875rem**（横条内容高 **33px** @root17.6 / 28px @root16；整条含自身 1px 下边框 = **34px**）—— 用户反馈"`#editor-header` 太粗了、对应的左右侧栏也要同步粗细度、`#toolbar` 也可以细一点"。改后实测：`#toolbar` 38.5→**33**、`#tab-bar` 39.5→**34**、`#editor-header` 41.38→**34**、左栏页签条 30.19→**34**、`.-agent-head` 39.5→**34**、`.-agent-history` 41.36→**34**；**同一带（33→67）左/中/右三条 top 与 bottom 两两相等**，下一带（67→101）中/右亦相等。**改法**：既有规则里的 `2.1875rem` 全部**原行替换**为 `var(--bar-h, 1.875rem)`（`memoria.css` 7 处 + `app.css` 4 处，**行数不变 ⇒ 锚点零漂移**），`app.css:5142-5172` 末尾块定义令牌并补 4 条"既有规则里没有高度声明"的（`.-agent-head` / `.-agent-history` / `#editor-header` / 左栏页签条）；三处内距**原位收窄**（`#editor-header` 0.5→0.25rem、`.-agent-head` 0.4375→0.25rem、`.-agent-history` 0.3125→0.125rem）以装下内容 —— 子元素溢出实测除 `#toolbar` 那 **0.5px 顶部（改动前就存在、被视口裁掉）** 外全为 0。**这是"一处可调"的设计轴：想再细/再粗只改 `--bar-h`**。属布局/密度微调，**不进 U 表** |
| 2026-09-19 | **U4 落地：区域分隔线专用档 `--border-sep`**（用户从"还剩什么可做"里选中这条）—— 定义在 `theme/memoria.css` 末尾（`:root { --border-sep: #303030 }`）与 `theme/light.css` 末尾（`html[data-theme="light"] { --border-sep: #e8e8e8 }`），**16 处** chrome 横条/区域竖边把 `var(--border)` 改成 `var(--border-sep, var(--border))`（脚本按行号精确替换，**行数零漂移**）。**实测（harness 8658，Chromium，DPR=1，797×736）**：令牌解析 `#303030` / `#e8e8e8`；深色 6 条分隔线计算色**全部** `rgb(48,48,48)`，对各自背景对比 **1.388 → 1.160（−16%）**；浅色全部 `rgb(232,232,232)`，对比 **1.344 → 1.134（−16%）**；**控件回归红线通过**：`.-agent-input` / `.-agent-history-select` / `.-config-btn` 边框仍是 `rgb(60,60,60)`（画在 `--bg-tertiary #333333` 上，对比 1.145）；`borderBottomWidth` 仍为 1px（0.5px 在 DPR=1 被上取整 —— 这正是要做颜色补偿的原因）。**实测抓到两处意外并已处理**：㈠ 深色 `--bg-toolbar` **就是 `#3c3c3c`**（与旧边框同色）⇒ 顶栏那条边原本"看不见"，换新档反而冒出一条更深线（1.196）；㈡ 浅色 `--bg-toolbar #e7e7e7` 与新档 `#e8e8e8` 几乎同色（实测对比 **1.009**）⇒ 线会消失。**故顶栏（`memoria.css:100`）刻意保留 `var(--border)`**，两套主题都维持原观感。**未取证**：① 真机 WebView2 观感（−16% 是否够、或过头），② 浅色主题下**控件**轮廓的实测值 —— 该次强切 `data-theme` 落在**隐藏标签页**（`document.hidden=true`）导致 120ms 过渡冻结在深色值，只能由 CSS 声明与该作用域 `--border = #d6d6d6` 推断（非实测），③ 125%/150% 缩放下的观感 |
| 2026-09-20 | **「三角」全库收敛到一枚 dsh 三角 + 无侧车「暗淡」态复校** —— 用户两句原话："agent 思考过程展开的『三角形』字符也要换掉，全仓库『三角形』都要换"；"原 memoria markdown 文件在配置过和没有配置过会显示两种图标一个清晰一个暗淡，请你延续这种设计"。**三角**：唯一 path 字面量仍留在 `file-tree.js:629`（dsh `ui-primitives` 的 `IconTriangleRightFill14`，MIT，pin 0d1f5000）；`agent-panel.js` 末尾块新增 `triangleMaskUrl()`（从 `window.MemoriaTreeIcons.icon("triangleRight")` 取回**同一枚** SVG → 抽出 `d` → 拼成 data-URI mask，实测 `d` 长 194 字符、`viewBox="0 0 14 14"`、mask 串长 414）与 `installTriangleStyles()`（注入 `<style id="-memoria-triangle">`），**一次覆盖全库所有 `details > summary` 标记**（AG08 思考块 / markdown 预览里的用户 `<details>` / 公式诊断块 / 链接「高级」/ 系统建议块）**与格式栏两个色板按钮的 `::after` caret**；`index.html:168/180` 文案末尾的 U+25BE 字符删除（**原行内改写、行号未变**），`app.js:10686` 注释同步改写。规则**整条注入**而不进 app.css 静态块：静态块只能给到 `mask-image`，JS 缺席时伪元素会以 `currentColor` 画成实心方块；整条注入则"零规则 ⇒ 原生标记照旧"。**暗淡态**：状态源是后端 `list_files` 每项的 `has_sidecar`（`file-tree.js:181` 给行加 `.no-sidecar`），清晰/暗淡仍走同一个 `opacity` 轴，仅把 **0.45 → 0.55**（`app.css:5601-5613` 末尾覆盖）。**为什么调（按 token 值算的合成对比，非渲染实测）**：dsh 单色 glyph 的 mark 层是细笔画，深色主题 `#cccccc` 画在 `#252526` 上 —— 清晰 0.85 → **7.30:1**，暗淡 0.45 → **3.10:1**、0.55 → **3.93:1**；浅色主题 `#2f2f2f` 画在 `#f6f6f6` 上 —— 清晰 **7.82:1**，暗淡 0.45 → **2.54:1**（低于 3:1 非文本阈值，偏"几乎看不见"）、0.55 → **3.24:1** ⇒ 两态对比仍一眼可辨，且暗淡态不再糊掉。**行号**：两个 JS 末尾块（2820-2890 / 2892-2962）+ `app.css` 末尾块（5585-5599 / 5601-5613）+ 两个语言包末尾 `Object.assign`（`agent.generating`）⇒ 既有锚点零漂移。**未取证**：本轮**无浏览器工具** ⇒ 未做真机/DOM 观感验证（三角的尺寸/垂直对齐、`<summary>` 行高变化、格式栏按钮宽度是否因 caret 变化、深浅主题观感均未实测；对比度是按 token 值算的**估算**）；仍**无截图**。逐项取证与命令见 `reference/agent-guide/01` §7 |
| 2026-09-23 | **设置区「可折叠子版块」+ 字体下拉（第三版定稿）+ 细滚动条覆盖浮层** —— 用户四句（见 §4「实施记录 C」来源段），末句明确要求**「纳入 ui 设计规范」**。① **折叠子版块成为设置区的统一组件**：六个页签（2D / 3D / 节点群 / 检索 / 检查 / 显示）的 `<section class="-settings-section">` 由 `graph-settings.js::foldSettingsSections()` **就地折成 `<details open>` + `<summary class="-settings-section-head">`** —— **移动节点**（六个 renderer 一行未改、字段 id 与事件绑定原样保留）、默认**展开**（"可收起"而非"默认藏起来"）、一条共享路径（调用点**同行追加**在 `setSettingsTab()` 的 if/else 链之后 ⇒ 下方锚点零漂移）；折叠头排版**对齐 `.-settings-heading` 那一档**（0.75rem / 600 / `padding: 0.5rem 0`）⇒ 折叠前后观感一致，Agent 页那两个头也并入同一规范。② **字体档 = 可定制原生 select**（`appearance: base-select`，只命中 `[data-display-font-lang]` / `[data-display-setting="fontBrand"]`）⇒ 键盘 / IME / 无障碍仍归浏览器；**浮层**用 `::picker(select)` 限高 `8.75rem` + 复用 B-6/B-7/B-9 档（4px 圆角 / 0.5px 描边 / `--shadow-float`）；**不用自绘下拉**（自绘需 `position: fixed` + 视口避让 —— 设置弹窗 `#settings-body` 是 `overflow: hidden`、`.-settings-form` 是 `overflow-y: auto`，绝对定位浮层会被裁）。③ **浮层滚条纳入「细滚动条」规范**：全局 `html *::-webkit-scrollbar` **够不到** top layer 里的 picker（实测浮层自身一直是平台默认 15px）⇒ 在 `@supports` 块内**逐条镜像**同一套 `--scrollbar-*` 令牌与几何（10px 命中区 + 4px 两侧内缩 = 可见 2px + 三档）；两条硬约束已实测（必须带 `::picker(select)`；不许同时写 `scrollbar-width/color`，否则 Chromium 整块忽略 `::-webkit-scrollbar`）。④ **设置区下拉统一** `font-family: var(--font-sans)` + `min-height: 1.75rem`（`base-select` 继承父级字体、且是 flex 盒比原生矮 2px ⇒ 不统一会让同页 5 个下拉互不对齐）。**实测（harness 8663 + `AAA_Vocab` 临时副本 + 临时 `MEMORIA_CONFIG_DIR`）**：六页 `details` = 3/3/1/1/1/4、残留 `<section>` 0、全 `open=true`、summary = 原 `<h3>` 文本；**真实点击 summary** ⇒ `open` true→false、`details` 124→33、后续上移 91px、`elementFromPoint` 同点改命中下一节 `SUMMARY`；`.-settings-form` 仍可滚（891 > 519）；折叠后 `#display-theme → light` 仍写盘（`-theme-mode=light`）；浮层首 `<option>` 宽 **466 = 476 − 10**（平台默认会 ≈461）⇒ 命中我们的细滚条；五个下拉 `fontFamily` / `height`(28px) / `padding` 全一致；Agent 页 2 个 `details` 未受影响。**未取证**：浮层 2px 滑块的**真机观感**（无法截图 / 无法 hover）、老 WebView2（不支持 `base-select`）上的回退观感、`details` 无展开动画（原生瞬时）。**另记一条环境坑**：8660 端口上有一台 **2026-09-19 遗留的 harness 进程**与本次并行监听（`SO_REUSEADDR`）⇒ 请求被两个进程**随机**接管，出现过 `Memoria v0.3.4` 与「未知方法 agent_plugins」这种旧码假象；**换到干净端口 8663 复验后全部通过**，且该遗留进程仍在（PID 33736），后续取证前应先确认端口只有一台在听 |
| 2026-09-23 | **行内代码 `` `文字` `` 的配色对齐上游** —— 用户：「对于 `文字` 这种样式，memoria 统一把他颜色改一下，和上游的这个样式的颜色对齐」。**上游口径**（本地检出 `D:\deepseek-harness` 可查，非推测）：`packages/client/ui-primitives/src/markdown/MarkdownText.module.css:146-156` 的 `.markdown :not(pre) > code` **只声明底色**（`background-color: var(--dsw-alias-markdown-inline-code)`）、**不声明文字颜色**（随正文）；该令牌取值在 `packages/client/ui-theme/src/styles/design-platform.css:215`（亮）= `--dsw-static-neutral-bluish-100` = `rgb(235, 238, 242)`、`:307`（暗）= `…-850` = `rgb(44, 44, 46)`。**本地改法**（两处都零行漂移）：① 新增配色档 `--code-inline-bg`（`theme/memoria.css` 末尾 `:root` / `theme/light.css` 末尾 `html[data-theme="light"]`，**逐字取上游色值**，理由与出处写在 `memoria.css` 末尾注释里）；② `.markdown-body code`（`memoria.css:546-553`，仍 8 行）的 `background` 改 `var(--code-inline-bg, var(--bg-tertiary))`（**带旧值兜底**，同 `--border-sep` 写法）、文字色由本地自创的 `var(--warning)`（橙 `#ce9178`）改为 **`inherit`（随正文）**。消费点**只有这一处**（预览 / 对话正文 / 计划卡共用同一渲染器 ⇒ 改一处即"统一"），块级代码 `.markdown-body pre code` 本就随正文色，未动。**实测（harness 8656 + `AAA_Vocab` 临时副本 + 真机 `.-preview.markdown-body` 宿主，fresh 节点量）**：暗色 `background-color = rgb(44, 44, 46)`、`color = rgb(204, 204, 204)`（= `--text-primary`，**不再是** `--warning #ce9178`）；临时切 `data-theme="light"` 后 `rgb(235, 238, 242)` / `rgb(47, 47, 47)`。钉子：新增 `tests/test_inline_code_color.py`（5 例：令牌 + 兜底 / 文字随正文且不许回到 `--warning` / 两套取值逐字等于上游且浅色档在 light 作用域内 / 注释留上游出处 / app.css 里不许另给行内代码配色）。**未取证**：① 浅色档在 `--bg-primary #ffffff` 上的对比仅 ≈1.14 —— **上游同样是淡的**，故按"对齐上游"取值；是否要更明显属观感取舍（说一句即调 `--code-inline-bg` 一处）；② 真机 WebView2 观感与 125%/150% 缩放未验；③ 仍**无截图** |
| 2026-09-24 | **「思考过程」那一行的小三角回到全库同一枚 + 预览链接文本可被选中/复制** —— 用户两句：「"思考过程"左侧的小三角符号太小了，而且距离有点远，中间有空」；「选区复制的时候，"跳转"的文本没有被复制进去」。**① 三角（尺寸 + 间距两处根因，都在既有规则里量出来的）**：`agent-panel.js::installTriangleStyles()`（2026-09-20 注入的全局 `details > summary::before`）给全库标记画的是**文件树那枚 9×9 mask 三角**，而 `app.css:6140-6150` 的 `.-agent-think-summary::before`（类选择器，特异性更高）把它改写成 `border-left: 5px` + 上下 `4px` 的 **5×8 小三角** ⇒ 只有这一处比别处小一圈；同时注入规则还给了 `margin-right: 0.3125rem`（5px），与 `.-agent-think-summary` 的 flex `gap: 0.375rem`（6px）**叠加成 11px** —— 既有注释只提到 gap，故此前没人发现"中间有空"。改法（`app.css` 末尾追加一个覆盖块，见 `.-agent-think-summary` / `::before` 两条）：三角恢复成与文件树同一枚（`width/height: 0.5625rem` + `border: 0`）、`margin-right: 0`、`gap: 0.25rem`、`align-items: baseline → center`。**实测（harness 8667 + 桩模型端点 8799）**：`getComputedStyle(summary,'::before')` = `width/height 9px`、`borderLeftWidth 0px`、`marginRight 0px`、mask 为 data-URI；`gap 4px`、`alignItems center`。**② 链接可选中**：`app.css:3945-3949` 的 `.-preview .memoria-link { user-select: none }`（连带 `mjx-container`）会让 Chromium 把**链接自身的可见文字排除在选区之外** ⇒ 跨链接拉选再复制，锚文本整段丢失。追加覆盖块改为 `user-select: text`（`cursor: pointer` 与点击跳转不受影响 —— 选中不阻止 click）。**实测**：同作用域内新建的 `.memoria-link` 节点 `userSelect` / `webkitUserSelect` 均为 `text`（改前为 `none`）。**说明**：两条都是"末尾追加、同特异性靠后生效"⇒ `app.css` 既有行号锚点零漂移；`mjx-container` 的 `user-select: none` **刻意保留**（公式是 MathJax 渲染产物，选中没有可复制意义）。**未取证**：① 无截图人眼复核（三角观感、拉选高亮是否覆盖链接）；② 未见真机上"鼠标跨链接拉选 → 剪贴板"的逐字比对 —— 本轮自动化探针里 `Selection.toString()` 读不到内容（`textNodeContained=false`），只拿到计算样式这一级证据。台账：`docs/todo.md` §13 的 **AG58** |
