# UI 契约（视觉层硬约束 + 机检）

> **用途**：规定 Memoria 视觉层**人机都必须遵守**的硬约束（主题 token / 颜色 / 尺寸 / 层级 / 图标），每条约束都对应一个可执行机检；并给出**现状基线**，让"样式债"从"看起来还行"变成可复跑的数字。
> **目标读者**：改样式的 AI Agent（本仓 `ui-designer` 常驻 Owner）、项目负责人（拍板视觉决定）、代码评审者。
> **关联文档**：设计语言与实施史见 [ui-visual-language.md](../design/ui-visual-language.md)（视觉 SSOT，本文不复制其内容）；层级速查见 [agent-guide/01 §2.9](../reference/agent-guide/01-shell-and-layout.md)；前端模块约定见 [frontend-modules.md](./frontend-modules.md)；文档归置规则见 [docs-management.md](./docs-management.md)。
> **状态**：生效中（2026-10-26，v1：约束 + 机检 + 基线；存量违规按基线冻结，新增违规一律红）。
> **机器可读部分**：本文中所有 ```json ui-contract:*``` 代码块是**脚本唯一读取的登记块**（`scripts/check_ui_contract.py`）。改登记 = 改契约；脚本不认识"自然语言里的暗示"。

---

## 0. 适用范围与单一事实源

| 层 | 唯一事实源 | 本契约的角色 |
|---|---|---|
| 主题 token（颜色/字体/阴影/滚动条/动效） | `src/memoria/ui/static/theme/memoria.css`（深色 `:root` 基准）+ `theme/light.css`（`html[data-theme="light"]` 覆盖） | 规定"怎么定义、怎么引用、深浅如何成对"并机检 |
| 结构样式（布局/组件） | `src/memoria/ui/static/app/css/app.css` | 规定"什么能写、什么禁止"并机检 |
| 设计语言/档位/实施史 | [docs/design/ui-visual-language.md](../design/ui-visual-language.md) | **引用不复制**；本契约只引用其已拍板的档位（圆角/描边/阴影/滚动条） |
| 层级速查（人读） | [agent-guide/01 §2.9](../reference/agent-guide/01-shell-and-layout.md) | 本契约的 z-index 登记块是**机检 SSOT**，两者冲突时以登记块为准并要求同步速查 |
| 组件契约钉子（单组件） | `tests/test_*_style.py` 等（如 [test_checkbox_dot_style.py](../../tests/test_checkbox_dot_style.py)） | 本契约做**横向**检查；单组件语义钉子仍在 tests，二者互补 |

**红线（本契约不覆盖，别在这里找）**：文案/i18n（见 [i18n.md](./i18n.md)）、信息架构与布局结构（见设计文档）、业务逻辑（JS 域 Owner）。

---

## 1. 主题 token 规则

**T1（新增 token）**：任何新颜色、阴影、字体族、滚动条/动效档，必须**先在 `theme/memoria.css` 的 `:root` 定义**，若为颜色类还必须在 `theme/light.css` 给出浅色取值；不得在组件规则里直接写字面量。
**T2（引用）**：结构样式里颜色/阴影/字体只准 `var(--token)`；`var()` 必须**带兜底**或该 token 已定义（机检 C7 会抓"只在浅色定义/根本没定义"）。
**T3（深浅成对）**：颜色 token 必须深浅成对；确实要深浅同值的，写进 `token-policy.light_override_allowlist` 并在下方登记理由。浏览器原生控件相关的 `scrollbar-color` 等标准属性若关闭了 `::-webkit-scrollbar`，必须按既有做法显式 `auto` 收口（详见 `app.css` 滚动条块注释）。

当前 token 全量清单（由 `python scripts/check_ui_contract.py --token-table` 生成，共 59 个 `:root` token + 5 个浅色专有 + 14 个 `app.css` 局部 token）：

| 类别 | token | 深色 | 浅色 | 备注 |
|---|---|---|---|---|
| 背景 | `--bg-primary/secondary/tertiary` | `#1e1e1e / #252526 / #333333` | `#ffffff / #f6f6f6 / #ececec` | 三大层，使用次数 35/59/61 |
| 背景 | `--bg-hover / active` | `#2a2d2e / #2c2c2d` | `#ececec / #e2e7f0` | hover 41 次；列表 hover=selected 同色 |
| 背景 | `--bg-toolbar / -hover / -input` | `#3c3c3c / #4a4a4a / #2b2b2b` | `#e7e7e7 / #dcdcdc / #ffffff` | 顶栏专用 |
| 背景 | `--bg-elevated / --bg-input` | **未定义（走兜底）** | `#ffffff` | 浅色专有，深色靠调用点兜底 ⇒ 见 §7 缺口 |
| 文字 | `--text-primary/secondary/bright` | `#cccccc / #858585 / #ffffff` | `#2f2f2f / #6b6b6b / #000000` | 使用 104/145/56 次，最热 |
| 文字 | `--text-muted` | **未定义（走兜底）** | `#8a8a8a` | 浅色专有 ⇒ §7 缺口 |
| 强调 | `--accent / --accent-hover / --accent-soft` | `#007acc / #1f8ad2 / rgba(0,122,204,.2)` | `#0066bf / #00559f / rgba(0,102,191,.12)` | |
| 强调 | `--theme-color` | `#007acc` | **沿用深色（未覆盖）** | 使用 123 次；与 `--accent` 是双别名 ⇒ §7 缺口 |
| 描边 | `--border / --border-light` | `#3c3c3c / #4c4c4c` | `#d6d6d6 / #bfbfbf` | `--border` 177 次 |
| 描边 | `--border-sep` | `#303030` | `#e8e8e8` | 区域分隔线专用档（U4） |
| 描边 | `--border-color / --border-subtle` | **未定义** | `#d6d6d6 / #e8e8e8` | 浅色专有 ⇒ §7 缺口 |
| 状态 | `--success / --error / --warning` | `#4ec9b0 / #f14c4c / #ce9178` | `#107c41 / #cd3131 / #a86400` | |
| 阴影 | `--shadow-soft / float / overlay` | 定义在 `app.css` 局部 `:root`（与主题无关） | 同左 | 浮层投影只准用这三档 |
| 字体 | `--font-sans / --font-mono` | 全仓唯一定义点 | 沿用深色 | 见 `memoria.css` 末尾 Windows CJK 注释 |
| 字号/缩放 | `--preview-font-size` 等 5 个 | **JS 写入**（`display-settings.js` 挂到 `<html>`） | 同左 | 见 §1.1 |
| 滚动条 | `--scrollbar-hit / -inset / -thumb-idle/-hover/-drag` | 定义在 `app.css` 局部 `:root` | 沿用深色 | 浅色滚条另有 `light.css` 规则但被 `!important` 收口盖住 ⇒ §7 缺口 |
| 动效 | `--motion-fast / --motion-base / --motion-ease` | 定义在 `app.css` 局部 `:root` | 同左 | 全站过渡只用这三档 |
| 代码/图表 | `--tk-* / --mmd-* / --graph-*` | 主题内成对定义 | 成对定义 | 图表类由 JS 读 `getComputedStyle`，CSS 内使用次数少不代表无人用 |

### 1.1 JS 写入的 token（唯一允许的"非 CSS 定义"来源）

```json ui-contract:token-policy
{
  "js_written_tokens": [
    "---cp-hue-thumb",
    "--agent-font-size",
    "--editor-font-size",
    "--font-brand",
    "--font-content",
    "--lineno-ch",
    "--memoria-i18n-range",
    "--preview-font-size"
  ],
  "ignore_undefined_tokens": []
}
```

> 这些 token 由 JS `style.setProperty()` 挂在 `<html>` 上（用户设置驱动），C7 把它们视为"已定义"。新增此类 token 必须登记到本块。

---

## 2. 硬约束 C1–C7

> 违规分两级：**FAIL**（新增即红，阻断）与 **WARN**（不阻断，提示）。存量违规已在基线冻结（§6），**只有新增违规会失败**；清债时用 `--update-baseline` 让基线变小。

### C1 禁止 `!important`（除登记豁免）

- **规则**：只有"必须盖过 JS 内联样式/后加载且特异度更高的旧规则/无障碍兜底"这三类用法可以 `!important`，且必须在下方 `important-exemptions` 逐条登记**理由**。
- **反例**：为了盖过同文件里另一条普通规则而 `!important` —— 应该提高选择器特异性或调整书写顺序（参考 `test_checkbox_dot_style.py`：它明确禁止在勾选圆点块里用 `!important`，因为"日后无法再覆盖"）。
- **机检**：C1；未登记即 FAIL。

### C2 禁止硬编码颜色

- **规则**：`color/background/border/box-shadow/…` 的颜色值必须 `var(--token)`。唯一豁免：**自定义属性（`--x`）的定义本身**（token 声明）——`theme/*.css` 定义主题 token，`app.css` 局部 `:root` 定义结构 token（`--shadow-*`/`--scrollbar-*`/`--motion-*`）；它们的右值是颜色字面量属正常。
- **中性 alpha**：`rgba(0,0,0,α)` / `rgba(255,255,255,α)` 只允许出现在 `box-shadow/text-shadow`（阴影的通用中性层），且优先走 `--shadow-*`；出现在 `color/background/border` 即 FAIL。
- **机检**：C2（FAIL=颜色字面量，WARN=中性 alpha 阴影）。

### C3 禁止魔法 px

- **字号/行高**：必须 `rem`（跟随"显示 → 字号/界面缩放"设置，禁止 px）。
- **圆角**：只用既有档位 **4 / 6 / 8 / 12 / 999**（来自 ui-visual-language B-6），且"圆角 ≤ 内边距"（浮层菜单因此停在 4px）。
- **间距**（padding/margin/gap）：只用既有偶数栅格 **0/2/4/6/8/10/12/14/16/20/24/32/40/48/64**；离格值会与相邻块对不齐（WARN）。
- **机检**：C3。

### C4 禁止同一范围/常量双源

- **规则**：同一范围/默认值（`{min,max,def,step}`）只允许一个事实源；其它文件若必须写守卫，必须**同口径**并由机检**逐字段**对齐（命名捕获组：`min`/`max`/`def` 已覆盖）。
- **实证**：2026-10-26 `contentMinPx` 下限 320→180 只改了 `display-settings.js` 时，`agent-panel.js` 的 `v >= 320 && v <= 560` 会把设置静默打回 360 —— 用户看到"拖了不生效"且无报错。这正是 C4 存在的原因。
- **覆盖面**：`min`/`max`（范围守卫）+ `def`（默认值守卫，`agent-panel.js` 的 `CONTENT_MIN_PX = 360`）；新增字段只需在契约登记块里加命名组与守卫，不需要改脚本。
- **机检**：C4（口径漂移 = FAIL；当前一致但双写 = WARN，等收口到单一导出）。

### C5 z-index 必须登记

- **规则**：CSS 里每个数值 `z-index` 都必须在 §4 登记表里（层 id + 允许的选择器子串）；层级高低关系写成关系条目。**登记表是层级唯一事实源**，`agent-guide/01 §2.9` 只是人读速查。
- **机检**：C5（未登记 = FAIL；登记了但 CSS 找不到 = WARN 过期；已知债务 = WARN）。

### C6 内联 SVG 图标规格

见 §5；机检 C6（未登记 / 13px 多段细描边 / 状态差异不可分 / 缺 aria-label·title / 非 currentColor = FAIL）。

### C7 主题 token 一致性

- **规则**：`var(--x)` 无兜底时，`--x` 必须在 `:root`（或本体局部 token / JS 写入白名单）定义；颜色 token 必须深浅成对。
- **机检**：C7（"仅浅色定义且无兜底" = FAIL；"颜色 token 浅色未覆盖" = WARN；"仅靠兜底" = WARN）。

---

## 3. 组件视觉规格（基础档位）

> 档位来自 [ui-visual-language.md](../design/ui-visual-language.md) 的已拍板项（B-6 圆角 / B-7 描边 / B-9 阴影 / B-10 滚动条 / A 档动效）。**新组件从这里取值，不要自造档位。**

| 组件 | 必须 | 禁止 |
|---|---|---|
| **按钮** | 基础 `.-btn`（+ `.primary/.secondary/.danger`，小号 `.-btn--sm`）；高度由内距与 `font-size: 0.75rem` 决定；圆角 **4px**；中性描边 **0.5px `var(--border)`**；hover 用 `--bg-hover`/`--border-light`/`--text-bright`；禁用 `opacity: .45` | 自造 ad-hoc 按钮样式；1px 中性描边；hover 用硬编码色；danger 用实心红底（保留"透明底+红字"） |
| **图标按钮** | 22×22 命中区（`inline-flex` 居中）；颜色 `currentColor` 由父级 `color` 控制；只放图标 + `aria-label`/`title` | 无文字又无 aria/title 的图标按钮；图标内硬编码颜色（无法跟状态色） |
| **输入/下拉** | 背景 `--bg-secondary`/`--bg-input`；中性描边 0.5px；focus 用 `outline: 1px solid var(--theme-color)`（或 `:focus-visible` 统一 2px 环）；圆角 4px；原生 `<select>` 一律 `appearance: base-select` 定制（**禁止**自绘下拉） | 裸 `Arial` 字体（继承链会错）；`input type=color`（pywebview 下不可用，见 hard-constraints） |
| **卡片** | 背景 `--bg-secondary`；描边 0.5px `--border`；圆角 4px（大容器 12px）；hover 换 `--border-color` 或主题色 | 硬编码背景/阴影；用 1px 实线堆层次 |
| **浮层**（popover/menu/dropdown/datalist） | `position: fixed`（top layer 或高 z 档）；阴影三档之一（`--shadow-soft/float/overlay`）；圆角 4px（受内距限制）；出入用 `--motion-fast/base`；`:focus-visible` 可见 | 无登记 z-index；`backdrop-filter` 滥用（只允许模态背板同一处）；自造动效时长 |
| **模态** | `.-modal` 统一入口（z=1000 已登记）；背板 `rgba(0,0,0,.42)` + `blur(2px)`（`--shadow-*`/背板属登记例外）；圆角 12px；标题/底部结构沿用 `.-modal-header/footer` | 第二个模态实现；模态内再放全屏遮罩 |
| **徽标/标签** | `.-badge`（10px/600/`--theme-color`/`--accent-soft`/圆角 4px）；`.-tag`/`.-chip` 属同族，颜色只准"主题色系/状态色系"变量 | 新增第 3 种"徽标"画法；用 emoji 当状态点 |
| **状态点/指示** | 用 `--success/--warning/--error`；指示线用 `inset box-shadow`（不占布局） | 硬编码 `#22c55e` 之类；用字符 `●` 拼状态 |
| **滚动条** | 全站唯一维护点 = `app.css` 滚动条末尾块（可见滑块 2px、透明轨道、三档透明度）；top layer 浮层（`::picker(select)`）必须**逐条镜像**同一套令牌 | 第二处写 `::-webkit-scrollbar`；同时写 `scrollbar-width/color`（会让 WebKit 伪元素整块失效） |
| **动效** | `--motion-fast: 120ms` / `--motion-base: 160ms` / `--motion-ease`；`prefers-reduced-motion` 兜底块是**全局唯一**的 4 条 `!important` 例外 | 新写 `transition: all`；新时长档；`animation` 无减少动效兜底 |
| **字体** | 正文 `var(--font-sans)`，代码 `var(--font-mono)`；字号只用 rem 档（0.625/0.6875/0.75/0.8125/0.875/1rem） | 裸 `monospace`（Windows 中文回退 SimSun）；px 字号 |

---

## 4. z-index 登记表

> **机检 SSOT = 下面的登记块**；`agent-guide/01 §2.9` 是可读速查，冲突时以本表为准并同步速查。新增浮层必须先在登记块加层，再写 CSS。

| z | 层 id | 用途 | 允许选择器（子串） |
|---|---|---|---|
| 0 | `z0_internal` | 输入镜像层（在 textarea 之下） | `.-agent-composer-mirror` |
| 1 | `z1_micro` | 局部微层：伪元素/内部叠层/顶栏内 spacer | `.-assist-*::before/after`、`.-toolbar-badge`、`.-toolbar-search-field`、`.-preview-range-band`、`#agent-input.-agent-chips-on`、`.-titlebar-drag-spacer` |
| 2 | `z2_local` | 局部层：缩放按钮、顶栏右组 | `.-mmd-zoom-btn`、`.toolbar-right` |
| 3 | `z3_graph_hint` | 图谱提示 / 缩放条 | `.-graph-hint--overlay`、`.-mmd-zoombar` |
| 3 | `z3_link_panel_rs_edge` | 链接面板缩放手（面板内叠层，边缘） | `.-link-panel-rs` |
| 4 | `z4_toolbar_groups` | 顶栏左/右组（内部浮层锚点） | `.toolbar-left`、`.toolbar-actions` |
| 4 | `z4_link_panel_rs_corner` | 链接面板缩放手（面板内叠层，四角） | `.-link-panel-rs--ne`、`--nw`、`--se`、`--sw` |
| 5 | `z5_window_controls` | 窗口三键 | `.-window-controls` |
| 6 | `z6_search_wrap` | 顶栏搜索包裹层（下拉锚点） | `.toolbar-search-wrap` |
| 10 | `z10_resizers` | 拖拽柄 / 行内浮层 | `#agent-dock-resizer`、`#sidebar-resizer`、`.-edge-target-datalist` |
| 20 | `z20_link_suggest` | 链接目标建议浮层 | `.-link-target-suggest` |
| 40 | `z40_costtip` | 常驻成本浮层 | `.-agent-costtip` |
| 50 | `z50_toolbar` | 顶栏整条 | `#toolbar` |
| 60 | `z60_file_menu` | 文件菜单 | `.-tb-file-menu` |
| 61 | `z61_file_submenu` | 文件子菜单 | `.-tb-file-submenu` |
| 62 | `z62_sel_add` | 选区「加入对话」按钮 | `.-agent-sel-add` |
| 90 | `z90_review_summon` | 复习召唤面板 | `#-review-summon` |
| 900 | `z900_link_panel` | 链接面板（可驻留浮动面板） | `.-link-panel` |
| 1000 | `z1000_modal` | 模态 | `.-modal` |
| 9000 | `z9000_search_panel` | 搜索结果面板 | `.-toolbar-search-panel` |
| 10000 | `z10000_resize_layer` | 窗口缩放手柄层 | `.-win-resize-layer` |
| 10050 | `z10050_context_menu` | 右键菜单 / 格式下拉 | `.-context-menu`、`.-fmt-dropdown-menu` |
| 12000 | `z12000_flash` | flash 反馈卡片 | `#-flash-host` |
| 20000 | `z20000_color_picker` | 取色器遮罩 | `.-color-picker-mask` |
| 99999 | `z99999_lightbox` | 图片灯箱 / 启动遮罩 | `.-lightbox-overlay`、`html.-booting` |

```json ui-contract:z-index-registry
{
  "layers": [
    {"id": "z0_internal", "z": 0, "selector_contains": [".-agent-composer-mirror"], "file": "app/css/app.css"},
    {"id": "z1_micro", "z": 1, "selector_contains": [".-assist-preview::before", ".-assist-preview::after", ".-toolbar-badge", ".-toolbar-search-field", ".-preview-range-band", "#agent-input.-agent-chips-on", ".-titlebar-drag-spacer"], "file": "app/css/app.css"},
    {"id": "z2_local", "z": 2, "selector_contains": [".-mmd-zoom-btn", ".toolbar-right"], "file": "app/css/app.css"},
    {"id": "z3_graph_hint", "z": 3, "selector_contains": [".-graph-hint--overlay", ".-mmd-zoombar"], "file": "app/css/app.css"},
    {"id": "z3_link_panel_rs_edge", "z": 3, "selector_contains": [".-link-panel-rs"], "file": "app/css/app.css", "note": "task-168：链接面板 8 方向缩放手（面板内叠层，边缘命中区）"},
    {"id": "z4_toolbar_groups", "z": 4, "selector_contains": [".toolbar-left", ".toolbar-actions"], "file": "theme/memoria.css"},
    {"id": "z4_link_panel_rs_corner", "z": 4, "selector_contains": [".-link-panel-rs--ne", ".-link-panel-rs--nw", ".-link-panel-rs--se", ".-link-panel-rs--sw"], "file": "app/css/app.css", "note": "task-168：四角缩放手压过边缘（4 > 3），角落滑动时优先命中角落"},
    {"id": "z5_window_controls", "z": 5, "selector_contains": [".-window-controls"], "file": "app/css/app.css"},
    {"id": "z6_search_wrap", "z": 6, "selector_contains": [".toolbar-search-wrap"], "file": "app/css/app.css"},
    {"id": "z10_resizers", "z": 10, "selector_contains": ["#agent-dock-resizer", "#sidebar-resizer", ".-edge-target-datalist"], "file": "app/css/app.css"},
    {"id": "z20_link_suggest", "z": 20, "selector_contains": [".-link-target-suggest"], "file": "app/css/app.css"},
    {"id": "z40_costtip", "z": 40, "selector_contains": [".-agent-costtip"], "file": "app/css/app.css"},
    {"id": "z50_toolbar", "z": 50, "selector_contains": ["#toolbar"], "file": "theme/memoria.css"},
    {"id": "z60_file_menu", "z": 60, "selector_contains": [".-tb-file-menu"], "file": "app/css/app.css"},
    {"id": "z61_file_submenu", "z": 61, "selector_contains": [".-tb-file-submenu"], "file": "app/css/app.css"},
    {"id": "z62_sel_add", "z": 62, "selector_contains": [".-agent-sel-add"], "file": "app/css/app.css"},
    {"id": "z90_review_summon", "z": 90, "selector_contains": ["#-review-summon"], "file": "app/css/app.css"},
    {"id": "z900_link_panel", "z": 900, "selector_contains": [".-link-panel"], "file": "app/css/app.css"},
    {"id": "z1000_modal", "z": 1000, "selector_contains": [".-modal"], "file": "app/css/app.css"},
    {"id": "z9000_search_panel", "z": 9000, "selector_contains": [".-toolbar-search-panel"], "file": "app/css/app.css"},
    {"id": "z10000_resize_layer", "z": 10000, "selector_contains": [".-win-resize-layer"], "file": "app/css/app.css"},
    {"id": "z10050_context_menu", "z": 10050, "selector_contains": [".-context-menu", ".-fmt-dropdown-menu"], "file": "app/css/app.css"},
    {"id": "z12000_flash", "z": 12000, "selector_contains": ["#-flash-host"], "file": "app/css/app.css"},
    {"id": "z20000_color_picker", "z": 20000, "selector_contains": [".-color-picker-mask"], "file": "app/css/app.css"},
    {"id": "z99999_lightbox", "z": 99999, "selector_contains": [".-lightbox-overlay", "html.-booting"], "file": "app/css/app.css"}
  ],
  "relations": [
    {"id": "filemenu-above-toolbar", "upper": "z60_file_menu", "lower": "z50_toolbar", "status": "ok"},
    {"id": "linkpanel-corner-above-edge", "upper": "z4_link_panel_rs_corner", "lower": "z3_link_panel_rs_edge", "status": "ok", "note": "四角命中区要盖住边缘命中区，否则角落拖动会被边缘抢走"},
    {"id": "submenu-above-menu", "upper": "z61_file_submenu", "lower": "z60_file_menu", "status": "ok"},
    {"id": "seladd-above-toolbar", "upper": "z62_sel_add", "lower": "z50_toolbar", "status": "ok"},
    {"id": "linkpanel-above-toolbar", "upper": "z900_link_panel", "lower": "z50_toolbar", "status": "ok"},
    {"id": "modal-above-linkpanel", "upper": "z1000_modal", "lower": "z900_link_panel", "status": "ok"},
    {"id": "modal-above-filemenu", "upper": "z1000_modal", "lower": "z60_file_menu", "status": "ok"},
    {"id": "resize-above-modal", "upper": "z10000_resize_layer", "lower": "z1000_modal", "status": "ok"},
    {"id": "flash-above-modal", "upper": "z12000_flash", "lower": "z1000_modal", "status": "ok", "note": "反馈必须盖住弹窗（弹窗会遮底栏）"},
    {"id": "C10-modal-vs-search", "upper": "z9000_search_panel", "lower": "z1000_modal", "status": "known-issue", "note": "C10 登记在案：搜索面板 9000 > 模态 1000，弹窗可被搜索面板遮挡"},
    {"id": "C10-modal-vs-contextmenu", "upper": "z10050_context_menu", "lower": "z1000_modal", "status": "known-issue", "note": "C10 登记在案：右键菜单 10050 > 模态 1000"},
    {"id": "C10-modal-vs-colorpicker", "upper": "z20000_color_picker", "lower": "z1000_modal", "status": "known-issue", "note": "C10 登记在案：取色器 20000 > 模态 1000"}
  ]
}
```

**层级纪律**：
1. 新浮层先登记再写 CSS；同一 z 值允许多个同类层（如菜单/下拉共用 10050），跨类复用必须写进 `note`。
2. 模态（1000）是"页面级最上层"的基准；任何高于它的层都必须有明确理由（反馈、系统级交互、灯箱），并在 relations 里登记。
3. 已知 C10（模态低于多个浮层）是**登记债务**，机器只 WARN；修复时同时改表与速查。

---

## 5. 内联 SVG 图标规格（含 13px 可辨性判据）

### 5.1 结构规格

| 项 | 规格 |
|---|---|
| 容器 | 内联 `<svg>`（零前端依赖硬约束）；必须有 `aria-hidden="true" focusable="false"`（装饰性） |
| viewBox | **`0 0 16 16`** 为默认档；例外必须登记（现有：上下文环 `0 0 20 20`、文件类型图标构建器动态 viewBox） |
| 渲染尺寸 | **13px / 16px** 两档（13px 用于密集工具条，16px 用于独立按钮）；`width`/`height` 属性或 CSS 任选其一，但必须是这两档 |
| 颜色 | `stroke="currentColor"` / `fill="currentColor"`；**禁止**在图标内硬编码色值（唯一例外：data-URI mask 内部 `#000`） |
| 描边 | `stroke-width` **1.3**（默认档）～**1.6**（需要更"立"的轮廓时）；`stroke-linejoin="round"`；13px 档有效描边 = `1.3 × 13/16 ≈ 1.06` 设备像素（DPR=1）⇒ 低于 `1.2` 会开始断裂 |
| 形状 | **13px 档优先"单个闭合轮廓"**；需要两笔以上时，至少有一笔是闭合形或带填充，**禁止"多条不闭合细线拼形状"**（2026-10-26 实证：v1 四条细路径 + stroke 1.4 在 13px 坍缩成一条线，像 "T" 不像图钉。**来源声明**：v1 源码未提交、已不在工作区，机检 fixture 是**按 Lead 描述重建的合成反例**，不冒充历史原文） |
| 浅填充 | **推荐手法**：单闭合轮廓 + `fill="currentColor"` + CSS `fill-opacity ≈ 0.15–0.3` 让轮廓在 13px 立住；同时可承载状态语义（浅填充=未选，实心=已选）。实测 2× 截图中，未钉（浅填充）与已钉（实心）在同一 13px 尺寸下均可辨 |
| 状态差异 | 多态图标（如钉住/未钉住）必须至少有一个**机器可查**的差异通道：`fill-opacity` 差 ≥ 0.3 或颜色 token 不同；差异必须在 CSS 里可见（登记 `states`） |
| 可发现性 | 图标按钮必须有 `aria-label` + `title`（悬停提示）；`aria-pressed` 等状态语义按控件语义给 |
| 例外登记 | 现有例外：上下文环（viewBox 20、数据驱动半径）、文件类型图标构建器（动态 viewBox/内容）、data-URI mask 三角（`#000` + 非直接渲染）。新例外必须在 registry 登记理由 |

### 5.2 13px / 16px 可辨性判据（清单式，机器 + 人各判一半）

> 判据不是"单独看像不像"——13px 下任何线性图标单独看都难辨认。真正要判的是下面三条；前两条机器可查，第三条必须在设计/评审时逐条勾选并留记录。

| # | 判据 | 机器可查？ | 判定方式 |
|---|---|---|---|
| ① | **与相邻控件可区分**：同一行里不能有两个"形态相近"的图标（细线/实心/圆形）承担不同语义；相邻若是文字按钮，图标需有足够墨量（不是一条线） | ❌ 半自动 | 登记表要求填 `adjacent`（相邻元素），评审时对照截图勾选；机器只校验"已填" |
| ② | **状态差异一眼可分**：多态图标的两种状态在 13px 下 fill-opacity/颜色差 ≥ 阈值 | ✅ | C6 读 CSS 的 `states` 求差（≥0.3） |
| ③ | **可发现性**：图标按钮有 `title` + `aria-label`；`aria-pressed` 等状态语义齐 | ✅ | C6 查生成代码符号体内是否同时设置 `aria-label` 与 `title` |

**13px 结构判据（机器）**：有效描边 ≥ 1.0 设备像素；**不闭合细描边路径数 ≤ 1**；若有闭合轮廓则建议有 fill 支撑（≥0.15）；图标图形占 viewBox 的有效跨度 ≥ 45%（避免"图在 16 里只画 6"导致实际更小）。

### 5.3 图标登记块

```json ui-contract:icons
{
  "icons": [
    {
      "id": "mask-triangle",
      "file": "app/js/agent-panel\\.js",
      "marker": "xmlns=\"http://www.w3.org/2000/svg\"",
      "dynamic_expected": true,
      "allow_fill_values": ["#000"],
      "note": "data-URI mask 三角：fill #000 作 mask 源色，非直接渲染 ⇒ 允许硬编码黑"
    },
    {
      "id": "link-panel-pin",
      "file": "app/js/app\\.js",
      "marker": "stroke-width=\"1.6\"",
      "viewBox": "0 0 16 16",
      "sizes": [13],
      "css_file": "app/css/app.css",
      "states": [
        {"name": "unpinned", "selector_contains": ".-link-panel-pin .-pin-shape"},
        {"name": "pinned", "selector_contains": ".-link-panel-pin[aria-pressed=\"true\"] .-pin-shape"}
      ],
      "discoverability": {"aria_label": true, "title": true, "symbol": "_linkPanelUpdatePin"},
      "adjacent": "标题文字 + [预览][源码] 分段按钮 + [全部打开][−][×]",
      "note": "2026-10-26 Lead 验收：单闭合轮廓 + 浅填充 .22 + stroke 1.6，13px 可辨（v1 四条细描边 stroke 1.4 被否）"
    },
    {
      "id": "link-icons",
      "file": "app/js/agent-panel\\.js",
      "marker": "x=\"5.75\"",
      "viewBox": "0 0 16 16",
      "sizes": [13],
      "adjacent": "链接文本（12px 正文）",
      "note": "复制/外开两枚描边图标（闭合 rect + 一条 L 形 path），stroke 1.3"
    },
    {
      "id": "context-ring",
      "file": "app/js/agent-panel\\.js",
      "marker": "-ctx-ring-track",
      "dynamic_expected": true,
      "viewBox": "0 0 20 20",
      "note": "上下文环：viewBox 0 0 20 20 + stroke-width 2 + 半径数据驱动 ⇒ 登记例外（非 16 viewBox）"
    },
    {
      "id": "file-tree-icon-builder",
      "file": "app/js/file-tree\\.js",
      "marker": "${box}",
      "dynamic_expected": true,
      "allow_fill_values": ["currentColor"],
      "note": "文件类型图标构建器：viewBox/内容来自 icon 定义表，fill=currentColor ⇒ 只核对登记存在"
    }
  ]
}
```

> 说明：`mermaid-zoom-btn` 是**预留占位**（源码里未找到静态 `<svg>` 时 C6 不报"未匹配"，因为动态登记）；删掉它前先确认无新图标。文件类型图标构建器（`file-tree.js`）与上下文环（`agent-panel.js`）见下方 ⚠️ 说明。

**已知动态构建器（机检只核对存在，不做逐属性检查）**：
- `app/js/file-tree.js:680` —— `svg(icon)` 构建器：`viewBox`/内容来自 icon 定义表，`fill="currentColor"`；13px 下是否可辨由"图标定义表逐项审查"负责（后续接入）。
- `app/js/agent-panel.js:7063` —— 上下文环：`viewBox 0 0 20 20`、`stroke-width 2`、半径数据驱动；属登记例外。
- `app/js/agent-panel.js:3130` —— data-URI mask 三角（`#000` 例外）。
---

## 6. 机检用法与基线

```bash
python scripts/check_ui_contract.py                 # 对基线跑；新增 FAIL ⇒ 退出码 1
python scripts/check_ui_contract.py --selftest      # 22 条内置 fixture 自测（每条约束必红 + 正例必绿 + 3 条阳性/阴性对照）
python scripts/check_ui_contract.py --json artifacts/agent/verify/ui/ui-contract-report.json
python scripts/check_ui_contract.py --token-table   # 生成 §1 的 token 清单
python scripts/check_ui_contract.py --update-baseline   # 重落基线（只允许变小；变大需 --force）
python scripts/check_ui_contract.py --strict        # 基线项也算 FAIL（清零阶段的 CI 用）
```

- **基线文件**：`artifacts/agent/verify/ui/ui-contract-baseline.json`（含 FAIL/WARN 数与逐条 `file:line:selector`）。
- **基线语义**：指纹 `rule|file|selector|prop|value` **不含行号** ⇒ 行号漂移不破基线；改值/改选择器 = 新增（红）。基线只允许变小；"已修复"会在输出里列出。
- **CI/门禁接入建议**：`--strict` 留到清债阶段；当前阶段只要求"新增不红"。门禁台账登记行由 Lead/thodo-owner 落 `docs/todo.md §12`。

### 6.1 现状基线（2026-10-26，HEAD `9242d236` + app.css 工作区含 task-168 未提交改动；详见 JSON）

| 约束 | FAIL | WARN | 说明 |
|---|---|---|---|
| C1 `!important` | **0**（37 条声明已逐条登记豁免） | 0 | 全部属"收口旧规则/无障碍/内联覆盖"三类，理由见 `important-exemptions` |
| C2 硬编码颜色 | **176** | 7 | 状态色回退值、链接/选区高亮、按钮实心色、调色板；中性 alpha 阴影 7 条 WARN |
| C3 魔法 px | **21** | 30 | 字号 px 8 条 + 圆角离档 13 条；间距 WARN 30 条（1/3/5/7/11/13px） |
| C4 双源范围 | 0 | **2** | `min/max`（`agent-panel.js:231`）与 `def`（`agent-panel.js:224` 的 `CONTENT_MIN_PX`）各一条；均与 `display-settings.js` 同口径，待 JS 侧收口 |
| C5 z-index | **0**（36 条声明全部登记） | 3 | C10 已知层级债务（登记在案） |
| C6 图标 | **0** | 0 | 4 个登记项（3 个动态构建器只核对登记）；13px 结构判据已由 fixture 证明能红 |
| C7 token 一致性 | **13** | 19 | `--bg`×5（未定义无兜底，真 bug）、`--border-subtle`×3、`--text-muted`×5；WARN 含 `--theme-color` 浅色未覆盖 |
| **合计** | **210** | **61** | 存量 271 条；**新增即红**，不要求一次清零 |

> 完整逐条 `file:line` 见 `artifacts/agent/verify/ui/ui-contract-baseline.json`；人读摘要见同目录 `ui-contract-baseline.md`。
> C7 的真缺陷已由真机 computed-style 探针实测确认（`artifacts/agent/verify/ui/theme_probe.mjs` → `theme-probe.json`），不是"读代码推断"。

```json ui-contract:style-policy
{
  "colors": {
    "token_files": ["theme/memoria.css", "theme/light.css"],
    "neutral_alpha_allowed_props": ["box-shadow", "text-shadow"]
  },
  "px": {
    "rem_only_props": ["font-size", "line-height"],
    "radius_tiers_px": [4, 6, 8, 12, 999],
    "spacing_grid_px": [0, 2, 4, 6, 8, 10, 12, 14, 16, 20, 24, 32, 40, 48, 64],
    "spacing_props": ["padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
                      "margin", "margin-top", "margin-right", "margin-bottom", "margin-left",
                      "gap", "row-gap", "column-gap"]
  }
}
```

```json ui-contract:important-exemptions
{
  "exemptions": [
    {"id": "E1-collapse-width", "file": "^app/css/app\\.css$", "selector_contains": ["-sidebar--collapsed", "-agent-dock--collapsed", "-agent-dock--auto-hidden", "-agent-dock--responsive-hidden"], "prop_in": ["width"], "reason": "折叠态必须压过 JS 内联宽度与展开态宽度；折叠是布局开关，不是视觉偏好"},
    {"id": "E2-hidden-utility", "file": "theme/memoria\\.css$", "selector_contains": [".hidden"], "prop_in": ["display"], "reason": "全局隐藏工具类必须压过任意 display；全仓唯一允许的 display !important"},
    {"id": "E3-reduced-motion", "file": "^app/css/app\\.css$", "selector_contains": ["*, *::before, *::after"], "prop_in": ["animation-duration", "animation-iteration-count", "transition-duration", "scroll-behavior"], "reason": "无障碍兜底：必须压过全站所有动画/滚动声明，否则用户设置 reduce 无效"},
    {"id": "E4-scrollbar-single-source", "file": "^app/css/app\\.css$", "selector_contains": ["::-webkit-scrollbar", "html, html *"], "reason": "滚动条外观唯一维护点：需收口 theme/memoria.css 与 light.css 里后加载、特异度更高的旧规则（注释见 app.css 滚动条块）"},
    {"id": "E5-nav-btn", "file": "theme/memoria\\.css$", "selector_contains": [".nav-btn"], "prop_in": ["font-size", "padding"], "reason": "顶栏通用 button 规则（.toolbar-center button）特异度更高，导航按钮复用同款外观需压过；后续可改特异性替代"},
    {"id": "E6-preview-link-state", "file": "^app/css/app\\.css$", "selector_contains": [".-preview .memoria-link"], "reason": "预览链接的可用/多链接/断链/hover 状态必须压过 .markdown-body a 基础规则（同元素双语义：基础链接 vs 可解析链接）"},
    {"id": "E7-mjx-inline", "file": "^app/css/app\\.css$", "selector_contains": ["mjx-container"], "prop_in": ["display"], "reason": "MathJax 会给容器写内联 display:block；行内公式必须压过它"},
    {"id": "E8-block-editing", "file": "^app/css/app\\.css$", "selector_contains": [".-src-block.-block-editing"], "prop_in": ["contenteditable", "cursor"], "reason": "源块编辑态要覆盖子元素（pre/code/svg/mjx）的默认光标与可编辑性；注意 `contenteditable` 不是 CSS 属性（浏览器忽略），属既有无效声明，登记豁免=暂不改行为，待 UI 域单独评估删除"},
    {"id": "E9-image-thumb", "file": "^app/css/app\\.css$", "selector_contains": [".-image-card-thumb"], "prop_in": ["height", "max-height"], "reason": "缩略图高度需压过图片自身的内联尺寸（markdown 图片可带 width/height 属性）"},
    {"id": "E10-mermaid-override", "file": "theme/mermaid\\.css$", "reason": "mermaid 渲染器会给生成的 SVG 写内联 style 与属性；本文件是唯一覆盖层，必须 !important 才能统一节点/连线/标签的深浅主题观感（文件内每条独立声明均在注释里留了依据）"}
  ]
}
```

```json ui-contract:range-ssot
{
  "ranges": [
    {
      "id": "contentMinPx",
      "ssot_file": "app/js/display-settings.js",
      "ssot_regex": "CONTENT_MIN_RANGE\\s*=\\s*\\{[^}]*?\\bmin:\\s*(?P<min>\\d+)[^}]*?\\bmax:\\s*(?P<max>\\d+)[^}]*?\\bdef:\\s*(?P<def>\\d+)",
      "guards": [
        {"file": "app/js/agent-panel.js", "regex": "v\\s*>=\\s*(?P<min>\\d+)\\s*&&\\s*v\\s*<=\\s*(?P<max>\\d+)"},
        {"file": "app/js/agent-panel.js", "regex": "CONTENT_MIN_PX\\s*=\\s*(?P<def>\\d+)"}
      ],
      "note": "2026-10-26 实证：下限 320→180 只改 display-settings.js 时，agent-panel.js 的旧守卫会把值静默打回默认 360。守卫与事实源必须同口径；最终应收口为跨模块单一导出。C4 用**命名捕获组逐字段**比对（min/max/def 都覆盖；step 暂无外部守卫）。"
    }
  ]
}
```

---

## 7. 未决与登记

### 7.1 主题缺口（C7 结果，**已量**）

| # | 缺口 | 证据 | 状态 |
|---|---|---|---|
| G1 | `--border-subtle` / `--text-muted` 在 app.css 被**无兜底**引用，但深色 `theme/memoria.css` 未定义 | `app.css:179/1644/1659/1660/2507/2879/2904`；真机探针 `theme-probe.json`：深色下 `color` 落到 `rgb(204,204,204)`（=正文色）、`border-top-color` 落到 `rgb(133,133,133)`/`rgb(204,204,204)`（亮线），浅色正确（`#8a8a8a`/`#e8e8e8`）；对照组（已定义 token + 字面量）读数正确 | **已定性为真缺陷**；修法建议 (b) 引用点加兜底（`var(--text-muted, var(--text-secondary))` / `var(--border-subtle, var(--border))`），待 app.css 当前写入者提交后执行 |
| G2 | `--theme-color` 无浅色覆盖 | 探针：浅色 `theme=#007acc / accent=#0066bf` | 双别名漂移，待拍板（推荐 light.css 补 `--theme-color: #0066bf`） |
| G3 | `--bg-elevated/--bg-input/--border-color` 仅浅色定义（深色靠调用点兜底） | C7 WARN | 属"浅色专有 + 兜底"模式，可接受；若清债则补深色定义 |
| G4 | 浅色滚动条三档 opacity 被滚动条块的 `!important` 覆盖，light.css 的 `::-webkit-scrollbar-thumb` 规则实际失效 | `app.css:5259-5271` vs `light.css:86-91` | 待真机观感确认；改法：三档 alpha 做成 token 并在 light.css 覆盖 token |
| G5 | `app.css:4393 contenteditable: true !important` | 不是 CSS 属性，浏览器忽略 | 死声明；删除属行为变更，登记待议 |

### 7.2 其他登记

- **C10 弹窗层级**：见 §4 relations（已登记债务）。
- **`contentMinPx` 的双源覆盖面**：`min/max` 由范围守卫覆盖、`def` 由默认值守卫（`CONTENT_MIN_PX = 360`）覆盖；机检用命名捕获组逐字段比对（2026-10-26 补强）。**代码侧收口到单一导出**由 JS 域 Owner 执行，本契约只负责"一旦漂移立刻红"。
- **图标定义表审查**（`file-tree.js` 的文件类型图标 20+ 枚）尚未逐项过 13px 判据，属后续批次。

---

## 8. 变更记录

| 日期 | 变更 | 证据/产物 |
|---|---|---|
| 2026-10-26 | v1 生效：C1–C7 约束 + `scripts/check_ui_contract.py`（19 条 selftest）+ 现状基线 + z-index 登记表（36 条声明全登记）+ 内联 SVG 规格（含 13px 判据） | `artifacts/agent/verify/ui/ui-contract-baseline.json`、`ui-owner-inaugural.md` |
| 2026-10-26 | C4 检测面补强 v1.1：改用**命名捕获组逐字段**比对（min/max/def；step 预留）；新增 `def` 守卫（`CONTENT_MIN_PX = 360`）；**剥 JS 注释**后再匹配（避免 agent-panel.js:67 说明注释被误报为第二事实源）；selftest 19→**22 条** | `scripts/check_ui_contract.py`、`ui-contract-baseline.json`（C4 WARN 1→2） |
| 2026-10-26 | 主题缺口 G1/G2 **真机实测定性**（Edge headless + 真实 CSS + computed style；含阳性对照组）：G1 = 真缺陷（深色 6 处 muted 文字退化为正文色、2 处淡线变亮线），G2 = 双别名漂移 | `artifacts/agent/verify/ui/theme_probe.mjs`、`theme-probe.json`、`theme-probe-{dark,light}.png` |
