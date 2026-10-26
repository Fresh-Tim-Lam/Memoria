# UI 视觉一致性审计（只读清单）

> **用途**：第一批立岗交付 B —— 找出"同类控件不同实现 / 同一语义两种画法 / 主题适配缺口"，给出 **file:line + 严重度 + 建议统一目标**。
> **状态**：只读审计，**本轮不改样式**（改动需先经契约 + 基线确认，避免"改完又被下一轮推翻"）。
> **数据来源**：`src/memoria/ui/static/**` 静态解析（2026-10-26，HEAD `9242d236` + app.css 工作区含 task-168 未提交改动）；主题缺口另由真机 computed-style 探针 `theme_probe.mjs` 实测（见 `theme-probe.json`）。
> **配套**：契约 [ui-contract.md](../../../docs/conventions/ui-contract.md)、机检 `scripts/check_ui_contract.py`、基线 `ui-contract-baseline.json`。

严重度口径：**P1** = 用户可见且已有量化证据（对比度不达标/失效声明）；**P2** = 观感/维护性问题（同类控件不一致，用户不一定指出）；**P3** = 结构建议。

---

## 1. 按钮族：至少 4 套"按钮"实现并存

| # | 族 | 代表 | 现状 | 严重度 | 建议统一到 |
|---|---|---|---|---|---|
| B1 | 标准按钮 | `.-btn` + `.primary/.secondary/.danger` + `.-btn--sm`（`app.css:22-108`） | 有完整语义体系（唯一"有规范"的族） | — | **基准** |
| B2 | 图标按钮 | `.-icon-btn`（如 `index.html:274` kp-close）、`.-link-panel-pin`（22×22） | 尺寸/命中区不统一：pin 22×22、`-icon-btn` 无显式尺寸、`-win-btn` 46×30 | P2 | 图标按钮统一 **22×22 命中区 + `currentColor` + `background: transparent`** |
| B3 | 工具栏按钮 | `.toolbar-actions button`（`memoria.css:132`）、`.mode-btn`（`:366`）、`.tab`（`:432`）、`.-view-btn`（`app.css:3594`）、`.-fmt-btn`（`:3616`） | 各自 `padding/font-size` 不同（0.25rem 10px vs 0.125rem 8px vs 0.25rem 8px） | P2 | 工具栏档：`font-size: 0.75rem`、`padding: 0.25rem 10px`、圆角 4px；紧凑档 `.-btn--sm` |
| B4 | 一次性按钮（14+ 处） | `.-check-open-btn`(904)、`.-config-btn`(1092)、`.-kp-range-actions button`(1909)、`.-link-add-row button`(3366)、`.-cp-row button`(3883)、`.-cp-presets button`(3857)、`.-math-sym-btn`(4369)、`#proposal-banner button`(4699)、`.-tb-file-menu button`(4951)、`.-tb-file-submenu button`(5014)、`.-mmd-zoom-btn`(7034)、`.-review-grade-btn`(7212)、`.-kp-tag-chip-btn`(1843)、`#welcome button`(memoria:486)、`#graph-controls button`(memoria:401) | 每个都自己写 `background/border/padding/border-radius`；圆角有 4px 也有 3px（`-kp-tag-chip-btn`=999 合理，`-agent-composer-chip`=3px 不在档位），hover 色各写各的 | **P2** | 能复用 `.-btn`/`.-btn--sm` 的复用；确属特殊形态（窗口三键/缩放按钮/色块）在契约 §3 登记例外 |
| B5 | 关闭按钮 | 见 §2 | 5 种实现 | **P1/P2** | 统一为一套 `.-icon-btn` + 统一字符（见 §2） |

---

## 2. 同一语义两种画法

| # | 语义 | 现状（实现 × 位置） | 严重度 | 建议 |
|---|---|---|---|---|
| S1 | **关闭** | ① `×` 字符 + `.close-btn`（文件页签 `app.js:2042`，title=i18n）；② `×` + `.-icon-btn`（弹窗 `index.html:274` kp-close、`:209` 等）；③ `-win-btn--close` 用 CSS 两笔伪元素画（`app.css:2331`）；④ `✕` U+2715（`image-tools.js` 2 处、`gap` 等）；⑤ 文字「关闭 / 关闭知识库」（菜单项，`index.html:87`，语义不同、可保留） | **P2** | 图标形式统一 `×`（U+00D7）；`✕` 的 2 处改 `×`；所有图标关闭按钮统一 `.-icon-btn`（尺寸/api 一致）；「关闭知识库」属动作菜单，不算 |
| S2 | **状态点/圆点** | `.-pick-dot`(16px, `2775`)、`.-link-legend-dot`(10px, `2809`)、`.-agent-statusbar-dot`(7px, `5101`)、`.-agent-tool-dot`(6px, `6059`)、`.-tree-dot`(3px ::after, `6381`)、`.-link-panel-tag` 前缀点 | P2 | 状态点定三档 **6 / 8 / 10px**（点与文字基线对齐），超出的按档位收敛；颜色只用 `--success/--warning/--error/--text-secondary` |
| S3 | **"无描述/空态"提示** | `.-muted`（11px `--text-secondary`）、`.-edge-no-build`（`#888` 硬编码）、`.-empty`（`memoria.css:639`）、`.-link-match-check-placeholder` | P2 | 统一 `.-muted` + `--text-secondary`；空态用 `.-empty`；删除 `#888` 字面量 |
| S4 | **危险操作** | `.-btn.danger`（透明底红字）vs `.-kp-delete-btn`（自带一套）vs `.-rm-badge-dis`（实心 `--error` 底 + `#fff`） | P2 | 危险"按钮"统一 `.-btn.danger`；危险"徽标"可实心但走 `--error` + `--text-bright`（或新 `--text-on-accent`） |

---

## 3. 浮层族：12 种浮层、圆角 3 档、底色 4 种、阴影 3 档（部分硬编码）

| # | 浮层 | 位置 | 圆角 | 阴影 | 底色 | 严重度 | 问题 |
|---|---|---|---|---|---|---|---|
| O1 | 链接面板 `.-link-panel` | app.css:7500 | 12px | `--shadow-float` | `--bg-secondary` | — | 与"大容器/模态"同档，合理（可拖动驻留面板） |
| O2 | 复习召唤 `#-review-summon` | 7325 | 12px | `var(--shadow-overlay, var(--shadow-soft))` | `--bg-secondary` | P3 | 双重兜底写法（overlay 已定义，不需要再兜 soft） |
| O3 | 取色器 `.-color-picker` | 3759 | 12px | `--shadow-overlay` | `var(--bg-primary, #fff)` | P3 | 兜底 `#fff` 是硬编码色（浅色主题会露出白底，深色下若 token 失效会白块） |
| O4 | 模态 `.-modal-box` | 4726 附近 | 12px | `--shadow-overlay` | `--bg-tertiary`? | P2 | **底色是 bg-tertiary，而 O1/O2 是 bg-secondary；同类"大浮层"三种底色** |
| O5 | flash 卡片 `.-flash-error/info` | 2649 | **8px** | `--shadow-overlay` | `var(--bg-elevated, #252526)` | P2 | 圆角 8px 不在小浮层档（4px）；兜底 `#252526` 硬编码 |
| O6 | 成本浮层 `.-agent-costtip` | 5349 | **6px** | `--shadow-float` | `--bg-primary` | P2 | 6px 是唯一在用小浮层圆角；建议 4px 或登记"贴附浮层"档 |
| O7 | 选区按钮 `.-agent-sel-add` | 5787 | 4px | `0 1px 4px rgba(0,0,0,.12)` **硬编码** | `--bg-primary` | **P2** | 硬编码阴影（同 `--shadow-soft` 但 alpha 不同：0.12 vs 0.2） |
| O8 | 菜单族：右键 `.-context-menu`(3043) / 格式下拉 `.-fmt-dropdown-menu`(3651) / 文件菜单 `.-tb-file-menu`(4934) / 子菜单(4994) | 4px | `--shadow-float` | **`--bg-primary`（右键）vs `--bg-secondary`（其余 3 个）** | **P2** | 同语义菜单三种底色（primary/secondary）→ 统一 `--bg-secondary`（或 elevated） |
| O9 | 搜索面板 `.-toolbar-search-panel` | 2556 | 4px | `--shadow-float` | `var(--bg-elevated, var(--bg-secondary))` | P3 | 用了 bg-elevated（浅色专有 token）⇒ 深色走兜底 secondary，OK 但依赖 §7 缺口 |
| O10 | 行内建议 `.-edge-target-datalist` | 1315 | 4px | `--shadow-soft` | `--bg-primary` | P3 | soft 档在小浮层里唯一，建议与 O8 同档 float 或登记 |
| O11 | 灯箱 `. -lightbox-overlay/image` | 4607/4617/4637 | 4px | `--shadow-overlay` + 内部 `rgba(0,0,0,.6)` 底 | 遮罩 `rgba(0,0,0,.85)` | P3 | 遮罩值 0.85 vs 模态背板 0.42 vs 取色器 0.45 → **三档遮罩值不统一**，建议抽 `--mask-backdrop`、`--mask-scrim` |
| O12 | 文件/格式/搜索 top-layer | — | — | — | — | P3 | 若上 `appearance: base-select` 类 top layer，必须镜像细滚条（已有规范见 `ui-visual-language` §4 实施记录 C） |

**浮层统一建议**：小浮层（菜单/下拉/建议/提示）统一 **圆角 4px + `--shadow-float` + `--bg-secondary`**；大面板/模态统一 **12px + `--shadow-overlay`**；新增例外必须进契约 §3。遮罩色抽 2 档 token（scrim/backdrop）。

---

## 4. 徽标/标签族：同一语义（短标签）4 种字号 × 4 种圆角

| 实现 | 位置 | 字号 | 圆角 | 底色 |
|---|---|---|---|---|
| `.-badge` | app.css:3 | 0.625rem | 4px | `--accent-soft` |
| `.-check-badge` | 886 | 0.625rem | 4px | 状态色 rgba（硬编码） |
| `.-edge-type-badge` | 1260 | 0.625rem | 4px | ? |
| `.-toolbar-badge` | 2224 | **0.5625rem** | **6px** | 硬编码 |
| `.-tag` | 3547 | **0.5625rem** | 4px | `--bg-tertiary` |
| `.-img-tag` | 4525 | 0.625rem | **8px** | 状态色 rgba（硬编码） |
| `.-config-tag` | 1967 | 0.5625rem | 4px | `--bg-tertiary` |
| `.-hist-badge` | 5437 | 0.625rem | **999px** | `--theme-color` + `#ffffff` |
| `.-link-panel-badge` | 7742 | 0.625rem | **999px** | ? |
| `.-link-panel-tag` | 7777 | 0.625rem | **999px** | `--bg-tertiary` |
| `.-kp-tag-pick` | 1789 | 0.6875rem | 999px | `--bg-primary` |
| `.-proposal-chip` | 4710 | 0.6875rem | 4px | `--bg-secondary` |
| `.-agent-composer-chip` | 5848 | ? | **3px** | `--accent-soft` |
| `.-rm-badge-dis` | 7397 | 0.6875rem | 4px | `--error` 实心 |

严重度 **P2**。建议：定 **两种**标签形态 ——「徽标 badge」= 10px/4px 圆角/轻底；「胶囊 pill」= 10–11px/999px/轻底；状态徽标（error/warning）沿用 badge 形态但颜色走状态 token。`.-agent-composer-chip` 的 3px 圆角不在档位（改 4px）。

---

## 5. 主题适配缺口（证据 = 真机 computed-style + 对比度计算）

### 5.1 P1｜真缺陷：`--border-subtle` / `--text-muted` 深色未定义且**无兜底** ⇒ 深色主题声明失效

> 探针：`artifacts/agent/verify/ui/theme_probe.mjs`（真实 Edge headless + 真实 CSS + 真实选择器元素），产物 `theme-probe.json` + `theme-probe-dark.png` / `theme-probe-light.png`。

| 元素（真实选择器） | 位置 | 深色 computed（实测） | 浅色 computed（实测） | 判定 |
|---|---|---|---|---|
| `.-suggest-score--muted` | app.css:1644 | `color: rgb(204,204,204)`（= 正文色，**muted 不明显了**） | `rgb(138,138,138)` | **真缺陷** |
| `.-search-section-label` | 1659 | `rgb(204,204,204)`（同上） | `rgb(138,138,138)` | **真缺陷** |
| `.-toolbar-search-scope-btn` | 2507 | `rgb(204,204,204)` | `rgb(138,138,138)` | **真缺陷** |
| `.-link-match-section` | 2904 | `rgb(204,204,204)` | `rgb(138,138,138)` | **真缺陷** |
| `.-link-match-check-placeholder` | 2879 | `rgb(204,204,204)` | `rgb(138,138,138)` | **真缺陷** |
| `.-import-section-title` | 179 | `border-top-color: rgb(133,133,133)`（= currentColor/正文次要色，**亮线**） | `rgb(232,232,232)`（正确淡线） | **真缺陷** |
| `.-search-section-label` border | 1660 | `border-top-color: rgb(204,204,204)`（**亮线**） | `rgb(232,232,232)` | **真缺陷** |

**对照组（证明探针不是瞎的）**：已定义 token `--border-sep` ⇒ 深 `rgb(48,48,48)` / 浅 `rgb(232,232,232)`；显式字面量 `rgb(1,2,3)` 原样读到。⇒ 测量通路有效。

**结论**：**真缺陷**（不是"注释不准"）。用户可见症状：深色主题下 6 处"次要文字"与正文同亮度、2 处分隔线变成偏亮实线（与 `--border-sep` 的 U4 减淡工作相悖）。
**修法建议**（按 Lead 倾向 (b) 起步，待 app.css 当前写入者提交后再动）：
- 引用点加兜底：`var(--text-muted, var(--text-secondary))`、`var(--border-subtle, var(--border))`（与 `--border-sep` 既有惯例一致，局部、可回退）；
- **不动** `theme/memoria.css` 定义（补定义会改变所有引用点的计算结果，属视觉决定，另议）；
- `light.css` 头部注释"它们在深色下仍走各自 var() 的兜底值"与事实不符 ⇒ 单独登记（§5.4）。

### 5.2 P2｜`--theme-color` 浅色未覆盖 ⇒ 与 `--accent` 双别名漂移

实测：深色 `theme=#007acc / accent=#007acc`；浅色 `theme=#007acc / accent=#0066bf`。
影响：浅色主题下所有用 `--theme-color` 的 123 处（状态栏底、焦点描边、选中态、主按钮）仍是深色蓝 `#007acc`，与用 `--accent` 的 15 处不一致。
建议（二选一，需拍板）：(a) `light.css` 补 `--theme-color: #0066bf`（一处、影响 123 处但语义正确）；(b) 组件逐步改用 `--accent` 并删 `--theme-color`（改动面大）。**推荐 (a)**。

### 5.3 P1｜深色配色直接用在浅色主题：状态色对比度不达标（量化）

浅色主题没有覆盖这些硬编码色（`light.css` 只覆盖了 4 个状态类）：

| 色值 | 用在哪 | 深底 `#1e1e1e` 对比 | 浅底 `#ffffff` 对比 | WCAG 4.5 正文 |
|---|---|---|---|---|
| `#e3b341` | `.-check-badge--warning` 文字 (app.css:901) | 8.57 | **1.95** | ❌ |
| `#ffd75e` | 若干 warn 文字 (2123 等) | 12.01 | **1.39** | ❌ |
| `#ffb3a7` | 若干 error/diff 文字 (2126/2141) | 9.73 | **1.71** | ❌ |
| `#ff7b72` | `.-check-badge--error` 文字 (896) | 6.61 | **2.52** | ❌ |
| `#d29922` | `.-graph-audit-warn` / `#status-stats` (2083/2092) | 6.6 | **2.52** | ❌（light.css 已对 2 个类覆盖为 `#8a5a00`，但 `-check-badge--warning` 等未覆盖） |
| `#07a05c` / `#c47f00` | `.-img-tag-used/unused` (4534/4535) | 4.9 / 5.1 | 3.4 / 3.3 | ⚠️ 大字可、正文不足 |

**建议**：新增两个语义 token `--warn-strong` / `--error-strong`（深浅成对）并替换这些字面量；或在 `light.css` 逐类覆盖（沿用已有 `#8a5a00` 的做法）。属 C2 清债的一部分。

### 5.4 P2｜其它主题适配缺口

| # | 缺口 | 证据 | 建议 |
|---|---|---|---|
| T1 | **11 处 `rgba(0,122,204,*)` 硬编码**：浅色主题 accent 是 `#0066bf`，但这些选区/高亮透明度仍按深色蓝算 | `app.css:1446/1457/1491/1492/1496/1522/4106/4136/4186/4191/4203` | 改用 `--accent-soft` 或新 `--accent-α` 系列 token（`color-mix()` 已在用，可 `color-mix(in srgb, var(--accent) 25%, transparent)`） |
| T2 | `#fff` 用于 accent 底上文字（19 处） | `app.css:54/61/2237/2254/2360/…` | 新增 `--text-on-accent`（深浅可不同），或接受 `--text-bright`（浅色下是黑，不适用） |
| T3 | 浅色滚动条三档 opacity 被 `!important` 收口盖过 | `app.css:5259-5271`（!important 用 `--scrollbar-thumb-*`）vs `light.css:86-91`（后被覆盖） | 把三档 alpha 做成 token 并在 `light.css` 覆盖 token；属 C1/E4 范围内的整改 |
| T4 | `light.css` 头部注释与事实不符（声称 6 个"被引用的未定义 token"都走兜底） | `theme/light.css:6-9` vs §5.1 | 改注释（单独登记，随 §5.1 修复一起） |

---

## 6. 内联 SVG 图标一致性（与契约 §5 配套）

| # | 现状 | 证据 | 严重度 | 建议 |
|---|---|---|---|---|
| I1 | 4 类图标体系：stroke 描边（`agent-panel.js:4632`，viewBox16/13px/stroke1.3）、fill 轮廓（`file-tree.js` 构建器）、混合（链接面板 pin：单闭合轮廓+fill+stroke1.6）、data-URI mask（三角/上下文环） | 见契约 icons 登记块 | P2 | 新增图标按契约 §5 分档；混合态只允许「闭合轮廓 + 浅填充 + stroke」，且必须登记 |
| I2 | 13px 可辨性**已有实证教训**：v1 四条细描边（stroke 1.4）在 13px 坍缩成"一条线/T"；v2 单闭合轮廓+浅填充 .22+stroke 1.6 被 Lead 接受 | `artifacts/agent/verify/todo/link-panel-v2-screens/P9-pin-icon-*.png` + 本次 2× crop（`icon-*-left6x.png`） | P1（已修复） | 判据写进契约 §5.2；机检 C6 对"多条不闭合细描边"直接 FAIL（selftest 有必红 fixture） |
| I3 | 文件类型图标表（20+ 枚）尚未逐项过 13px 判据 | `file-tree.js` 构建器 | P3 | 后续批次：把 icon 定义表纳入 C6 逐项审查 |
| I4 | `✕`(U+2715) 与 `×`(U+00D7) 混用（2 vs ~100） | `image-tools.js` 2 处 | P2 | 统一 `×` |

---

## 7. 审计结论（只读，不改）

1. **按钮/浮层/徽标三类都有"没有统一入口"的问题**，但都能收敛到少数档位；优先做**浮层底色/阴影/圆角**与**徽标 2 形态**，因为它们成片出现、统一收益最高。
2. **最硬的缺口是主题层**：`--border-subtle`/`--text-muted` 深色失效已被真机 computed-style 证实（P1），状态色在浅色主题对比度 1.4–2.5 已被量化（P1）。这两项应排在"清 C2 硬编码色"之前或同时做。
3. 图标规格已按 Lead 的真实案例固化为**结构判据 + 清单式判据**；v1 那种"多条细线拼形状"会被 C6 直接判红（fixture 证明）。
4. 本审计**不建议**一次全改：按契约先把"新增违规拦住"，存量按以下批次清：① 主题 P1（两 token 兜底 + 状态色 token）→ ② 浮层/徽标收敛 → ③ 按钮族收敛 → ④ C2/C3 存量清零。
