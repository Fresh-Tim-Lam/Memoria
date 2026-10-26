# UI 域立岗报告（ui-designer · task-166 第一批）

> 日期：2026-10-26 ｜ 执行者：`ui-designer` ｜ 基线代码：HEAD `9242d236`（app.css 工作区另含他人 task-168 未提交改动，见 §7）
> 交付：**UI 契约 + 机检 + 现状基线 + 视觉一致性审计 + 内联 SVG 图标规格（含 13px 判据）**
> 产物目录：`artifacts/agent/verify/ui/`；契约：`docs/conventions/ui-contract.md`；机检：`scripts/check_ui_contract.py`

---

## 0. 先给结论（TL;DR）

1. **契约已落盘且可机检**：`docs/conventions/ui-contract.md`（规范性；引用 `design/ui-visual-language.md` 与 `agent-guide/01` 而不复制）。7 条硬约束 C1–C7，每条都有机检；`scripts/check_ui_contract.py --selftest` **19/19 PASS**（每条约束至少一条必红 fixture + 正例 + 2 条正向对照）。
2. **现状基线已冻结**：**210 FAIL / 60 WARN（270 条，逐条 file:line 落 JSON）**；对基线重跑 **新增 FAIL=0**（退出码 0），`--strict` 下退出码 1（存量债仍在）。"现状 210 条"从此是可复跑的数字，不再是"看起来还行"。
3. **视觉一致性审计**（只读）：按钮 4 套实现、浮层 12 种（圆角 3 档/底色 4 种/遮罩 3 值）、徽标/标签 14 种（字号 4 档/圆角 4 档）、状态点 5 种尺寸；清单见 `ui-consistency-audit.md`。
4. **图标规格已按真实案例固化**：13px 判据 = 结构判据（禁"多条不闭合细描边"）+ 状态差异阈值（opacity 差 ≥0.3）+ 可发现性（aria-label/title）+ 清单式人工判据（相邻可区分）。机检对 v1 类实现**直接红**（fixture 证明）。
5. **主题缺陷"先量再改"已完成测量**：`--border-subtle` / `--text-muted` 深色未定义且无兜底 = **真缺陷**（真机 computed-style 实测：6 处 muted 文字退化为正文色、2 处淡分隔线变亮线）；`--theme-color` 浅色未覆盖 = 双别名漂移（浅色 `#007acc` vs `--accent #0066bf`）。**本轮未改样式**，修法已定、等 app.css 当前写入者提交后执行。
6. **门禁全绿**：`pytest -q tests` **1516 passed**（= 基线，未降）；`node --check` 62 个 JS **0 fail**；`i18n_selftest` PASS；`team_audit` **FAIL=0**；`prompt_drift_check` **exit 0**。不 commit。

---

## 1. 交付 A：UI 契约（`docs/conventions/ui-contract.md`）

### 1.1 定位与单一事实源（避免"第三份表"）

| 层 | 唯一事实源 | 契约角色 |
|---|---|---|
| 主题 token | `theme/memoria.css`（深）+ `theme/light.css`（浅） | 规定定义/引用/深浅成对 + 机检 |
| 结构样式 | `app/css/app.css` | 规定能写/禁止 + 机检 |
| 设计语言与档位 | `docs/design/ui-visual-language.md`（49KB，已有） | **引用不复制** |
| 层级人读速查 | `docs/reference/agent-guide/01-shell-and-layout.md`（已有） | 契约登记块 = 机检 SSOT，冲突时以登记块为准 |
| 单组件语义钉子 | `tests/test_*_style.py`（如 `test_checkbox_dot_style`） | 本契约做横向检查，互补不重复 |

### 1.2 七条硬约束（每条配机检）

| 约束 | 规则 | 机检结果（当前） |
|---|---|---|
| **C1** `!important` | 只允许 3 类用法：盖过 JS 内联/后加载旧规则、无障碍兜底、收口唯一维护点；**逐条登记理由** | 37 条声明 → **10 条豁免登记**（E1–E10）→ **0 FAIL**。典型：折叠宽度 4、reduced-motion 4、滚动条收口 15、mermaid 覆盖 16、隐藏工具类 1、链接状态机 8、其它 5 |
| **C2** 硬编码颜色 | 颜色必须 `var(--token)`；自定义属性定义本身豁免；中性黑/白 alpha 只许阴影 | **176 FAIL / 7 WARN** |
| **C3** 魔法 px | 字号/行高必须 rem；圆角只 4/6/8/12/999；间距只偶数栅格 | **21 FAIL / 30 WARN** |
| **C4** 双源范围 | `contentMinPx` 180–560 单一事实源；外部守卫必须同口径 | 0 FAIL / **1 WARN**（`agent-panel.js:231` 双写，当前一致但迟早漂移） |
| **C5** z-index | 每个数值 z-index 必须登记（层 id + 允许选择器） | **36 条声明全部登记 → 0 FAIL**；3 WARN = C10 已知层级债务（模态低于搜索/右键/取色器，登记在案） |
| **C6** 内联 SVG | viewBox/尺寸/currentColor/13px 结构/状态差异/可发现性 | **0 FAIL**；4 个登记项（3 个动态构建器只核对存在——如实标注，不假装覆盖） |
| **C7** 主题 token | 无兜底引用必须已定义；颜色 token 必须深浅成对 | **13 FAIL / 19 WARN**（明细见 §3） |

### 1.3 机制要点（防止契约腐烂）

- **基线指纹** `rule|file|selector|prop|value` **不含行号** ⇒ 行号漂移不破坏基线；改值/改选择器 = 新增违规 = 红。
- `--update-baseline` **只允许基线变小**；首次建基线与放宽需 `--force`（写入时记录）。
- `--strict` 供清债阶段：把基线项也当 FAIL。
- 机器可读登记块（契约内 ```json ui-contract:*```）：`style-policy` / `important-exemptions` / `z-index-registry` / `range-ssot` / `icons` / `token-policy`。**登记表在文档里，脚本解析文档** ⇒ 只有一份事实源。

---

## 2. 交付 B：视觉一致性审计（只读，`ui-consistency-audit.md`）

| 族 | 现状 | 严重度 | 建议统一到 |
|---|---|---|---|
| 按钮 | 4 套：`.-btn` 族 / 图标按钮（pin 22×22、`-icon-btn`、`-win-btn` 46×30）/ 工具栏按钮（font 0.75 vs 0.6875、padding 各写）/ 一次性按钮 15+ 处 | P2 | `.-btn` 基准；图标按钮 22×22 + currentColor |
| 浮层 | 12 种：圆角 4/6/8/12 四档、底色 primary/secondary/elevated 三种、遮罩 3 个值（0.42/0.45/0.85）、`-agent-sel-add` 阴影硬编码 | **P2** | 小浮层 = 4px + `--shadow-float` + `--bg-secondary`；大面板/模态 = 12px + overlay；遮罩抽 2 token |
| 徽标/标签 | 14 种：字号 4 档（9/10/11/12px）、圆角 4 档（4/6/8/999）、同语义"短标签"无统一入口 | P2 | 两形态：badge（10px/4px）+ pill（10–11px/999px） |
| 状态点 | 5 种尺寸（3/6/7/10/16px） | P2 | 三档 6/8/10px + 状态色 token |
| 同语义两画法 | 关闭有 5 种（`×` + `.close-btn` / `×` + `.-icon-btn` / CSS 两笔窗口键 / `✕` U+2715 ×2 / 文字菜单项）；"空态提示" 4 种 | P2 | 图标关闭统一 `×` + `.-icon-btn`；空态统一 `.-muted`/`.-empty` |
| **主题适配** | 见 §3（P1 已量化） | **P1** | 先修 token 兜底 + 状态色 token |

---

## 3. 交付 C：内联 SVG 图标规格 + 13px 可辨性判据

### 3.1 规格（写进契约 §5）

- viewBox `0 0 16 16`（例外登记：上下文环 `0 0 20 20`、文件类型图标构建器动态、data-URI mask）；
- 渲染尺寸 **13 / 16px** 两档；颜色 `currentColor`（唯例外：mask 内部 `#000`）；
- stroke-width **1.3（默认）～1.6**；13px 下有效描边 = 1.3×13/16 ≈ 1.06 设备像素（再低会断）；
- **形状纪律**：13px 优先"单个闭合轮廓"；**禁止多条不闭合细线拼形状**；推荐单闭合轮廓 + `fill-opacity ≈0.15–0.3` 浅填充（既立住轮廓又承载状态语义）；
- 状态差异：fill-opacity 差 ≥0.3 或颜色 token 不同（机器可查）；
- 可发现性：图标按钮必须同时有 `aria-label` + `title`。

### 3.2 判据（机器 + 清单，不靠"看图觉得像不像"）

| # | 判据 | 机器？ |
|---|---|---|
| ① 与相邻控件可区分（同排不能两个形态相近图标承担不同语义；相邻是文字按钮时图标需有足够墨量） | 半自动：登记表 `adjacent` 必填 + 评审勾选 |
| ② 状态差异一眼可分（多态 opacity/颜色差 ≥ 阈值） | ✅ C6 读 CSS states 求差 |
| ③ 可发现性（title + aria-label + aria-pressed 等） | ✅ C6 查生成符号体 |

**13px 结构判据（机器）**：有效描边 ≥1.0 设备像素；不闭合细描边路径数 ≤1；闭合轮廓建议有 fill 支撑（≥0.15）；图标图形跨度 ≥45% viewBox。

### 3.3 真实案例的 fixture 来源声明（重要，如实标注）

Lead 给的 v1（"四条细路径 + stroke 1.4 + 13px 坍缩成 T"）是**基于截图的事后描述**；v1 源码**未提交过、已不在工作区**（HEAD 已是 v2 单闭合轮廓 + 浅填充 .22 + stroke 1.6）。
⇒ 机检 fixture 里的 v1 是**按该描述重建的合成反例**，**不冒充历史原文**；重建件在 `--selftest` 中必须判红（C6 必红 fixture），v2 形态必须判绿（C6 绿 fixture）。这条已同步写进契约 §5.1 的"来源声明"。

### 3.4 像素级正负对照（v2 已验收态，2× 截图实测）

| 状态 | 图标 bbox（设备 px @2x） | 实心占比 | 说明 |
|---|---|---|---|
| 未钉住（浅填充 .22） | 16×24 | **0.458** | 轮廓可辨、能看出钉头/收腰/针；Lead 已验收 |
| 已钉住（实心） | 16×24 | **0.596** | 状态差异一眼可分 |

截图 6× 放大留档：`icon-unpinned-left6x.png` / `icon-pinned-left6x.png`（正负对照）。

---

## 4. ★ 主题缺陷：先量再改（Lead 本轮重点）

### 4.1 方法（真机，不是读代码推断）

`artifacts/agent/verify/ui/theme_probe.mjs`（零依赖）：本地静态服务器 + **真实 Edge headless（CDP）** 加载**真实 CSS**（`theme/memoria.css` + `app.css` + `theme/mermaid.css`；浅色再加载 `light.css` 并设 `data-theme="light"`），把 app.css 里**真实使用这些 token 的真实选择器**元素摆进 DOM，读 **computed style**，深/浅各跑一遍。

**阳性对照（证明探针不是瞎的）**：
- 已定义 token `--border-sep`：深色读到 `rgb(48,48,48)`、浅色 `rgb(232,232,232)` ✅
- 显式字面量 `rgb(1,2,3)`：两主题都原样读到 ✅
⇒ 测量通路有效；下面"失效"不是测量误差。

### 4.2 结果（`theme-probe.json` + 两张截图）

| 元素 | 位置 | 深色实测 | 浅色实测 | 判定 |
|---|---|---|---|---|
| `.-suggest-score--muted` | app.css:1644 | `color: rgb(204,204,204)`（**= 正文色**） | `rgb(138,138,138)` | **真缺陷** |
| `.-search-section-label` | 1659 | `rgb(204,204,204)` | `rgb(138,138,138)` | **真缺陷** |
| `.-toolbar-search-scope-btn` | 2507 | `rgb(204,204,204)` | `rgb(138,138,138)` | **真缺陷** |
| `.-link-match-section` | 2904 | `rgb(204,204,204)` | `rgb(138,138,138)` | **真缺陷** |
| `.-link-match-check-placeholder` | 2879 | `rgb(204,204,204)` | `rgb(138,138,138)` | **真缺陷** |
| `.-import-section-title` | 179 | `border-top-color: rgb(133,133,133)`（= currentColor，**亮线**） | `rgb(232,232,232)` | **真缺陷** |
| `.-search-section-label` 边框 | 1660 | `border-top-color: rgb(204,204,204)`（**亮线**） | `rgb(232,232,232)` | **真缺陷** |
| `--theme-color`（别名漂移） | — | `#007acc`（= accent） | `theme=#007acc` vs `accent=#0066bf` | **THEME-ALIAS-DRIFT** |

**结论：三种可能里是第一种 —— 真缺陷。**（不是"只是注释不准"，也不是"两者都不是"）
用户可见症状：深色主题下 6 处"次要文字"与正文同亮度（层次丢失）、2 处本该很淡的分隔线变成偏亮实线（与 U4 `--border-sep` 的减淡工作相悖）；浅色正常。

### 4.3 修法判断（按 Lead 倾向 (b) 起步）

- **推荐 (b) 局部兜底**：把无兜底引用改成 `var(--text-muted, var(--text-secondary))` / `var(--border-subtle, var(--border))`（与既有 `var(--border-sep, var(--border))` 惯例一致，改动面小、可回退、只影响这 7 处）。
- **不建议现在 (a) 补深色定义**：`--text-muted`/`--border-subtle` 是"浅色专有"设计（深色原本用 primary/secondary 的就近档）；在 `:root` 补定义会把**所有**引用点（含当前有兜底的 6 处）的计算结果一起改掉，属视觉决定，需深浅真机截图后再议。
- **`light.css` 头部注释与事实不符**：已登记为独立条目（G1/T4），随修复合入（改注释属 docs，建议由 docs 域处理或授权我改）。
- **执行前置**：当前 `app.css` 有他人未提交改动（`git status` 显示 +50/−3，task-168 链接面板缩放手）⇒ **本轮不动 app.css**，等其提交后按 (b) 落地并给深浅截图。

---

## 5. 机检脚本说明（`scripts/check_ui_contract.py`）

```bash
python scripts/check_ui_contract.py            # 对基线跑：新增 0 FAIL ⇒ exit 0（当前）
python scripts/check_ui_contract.py --selftest # 19/19 PASS（每约束必红 fixture + 正例 + 2 正向对照）
python scripts/check_ui_contract.py --strict   # exit 1（存量 210 FAIL 仍在，供清债阶段）
python scripts/check_ui_contract.py --token-table / --suggest / --json / --update-baseline
```

- 契约是 SSOT：脚本解析 `docs/conventions/ui-contract.md` 里的 `json ui-contract:*` 登记块；**改登记 = 改契约**。
- 性能：全量扫描（app.css 7.8k 行 + 62 个 JS）**< 0.1s**。
- 已知边界（如实）：C6 对动态构建器只核对"登记存在"，不做逐属性检查；C4 目前只覆盖 `{min,max}`（`def` 双源登记为待办）；C3 只检查属性维度（不解析 calc/变量展开）。

---

## 6. 门禁结果

| 门禁 | 结果 |
|---|---|
| `pytest -q tests` | **1516 passed**（基线 1516，未降） |
| `node --check`（app/js 全部 62 个 + 新增 theme_probe.mjs） | **0 fail** |
| `scripts/i18n_selftest.js` | PASS |
| `scripts/agent/team_audit.py` | **FAIL=0**（WARN=51 / INFO=29，均为既有项） |
| `scripts/agent/prompt_drift_check.py` | **exit 0**（FAIL=0） |
| `py_compile scripts/check_ui_contract.py` | 通过 |

**未 commit**（按纪律，Lead 统一提交）。

---

## 7. 写域与协调（需要 Lead 知道的三件事）

1. **`app.css` 当前有他人未提交改动**（`git status`: `M src/memoria/ui/static/app/css/app.css`, +50/−3，内容 = task-168 链接面板 8 方向缩放手 `.-link-panel-rs`）。⇒ 我**没有写 app.css**；新 z-index（3/4）已登记进契约，避免其提交后被机检误判为"未登记"。
2. **写域已按 Lead 批准扩展到 `theme/**`**，但本轮对 theme 只读（含测量）；token 改动待 §4.3 决议 + 深浅截图。
3. **建议登记行（需 Lead 转 todo-owner/registrar，我不写 `docs/todo.md`）**：
   - `docs/conventions/README.md` 索引表加一行：`ui-contract.md | 视觉层硬约束（C1–C7）+ 机检 + 基线 | 改样式的人/AI`（按 docs-management「新文档必登记」）；
   - `docs/todo.md §12` 门禁台账加：`UI 契约机检 scripts/check_ui_contract.py（FAIL/WARN + 基线，新增违规红）`。

---

## 8. 未做 / 下一批（如实）

| 项 | 原因 |
|---|---|
| 清 C2/C3 存量（210 FAIL） | 需要新 token（`--text-on-accent`、`--warn-strong`/`--error-strong`）与成批替换，且 app.css 有他人写入中 |
| 主题 P1 修复（§4.3 (b)） | 等 app.css 写入者提交 + Lead 确认（改动虽是兜底但会改变深色观感） |
| 浮层/徽标/按钮收敛（审计 P2） | 按契约批次执行，需 Lead 排优先级 |
| 文件类型图标表（20+ 枚）逐项过 13px 判据 | 后续批次；当前 C6 只覆盖静态内联 SVG |
| `contentMinPx.def` 双源收口 | 需 JS 域 Owner 协作（跨模块导出） |

---

## 9. 产物清单

| 文件 | 内容 |
|---|---|
| `docs/conventions/ui-contract.md` | 契约（token 清单 / C1–C7 / 组件规格 / z-index 表 / 图标规格 + 登记块） |
| `scripts/check_ui_contract.py` | 机检（C1–C7 + `--selftest` 19 条 + 基线/严格/建基线/JSON/清单） |
| `artifacts/agent/verify/ui/ui-contract-baseline.json` | 基线全量（270 条逐条 file:line） |
| `artifacts/agent/verify/ui/ui-contract-baseline.md` | 基线上读摘要（按约束/文件汇总） |
| `artifacts/agent/verify/ui/ui-contract-report.json` | 最近一次运行明细 |
| `artifacts/agent/verify/ui/ui-consistency-audit.md` | 视觉一致性审计清单（只读） |
| `artifacts/agent/verify/ui/theme_probe.mjs` | 主题缺口测量脚本（真机 CDP，可复跑） |
| `artifacts/agent/verify/ui/theme-probe.json` + `theme-probe-{dark,light}.png` | 主题测量结果 + 截图 |
| `artifacts/agent/verify/ui/icon-{unpinned,pinned}-left6x.png` 等 6 张 | 图标 13px 可辨性 2× 截图放大留档 |
| `artifacts/agent/verify/ui/ui-owner-inaugural.md` | 本报告 |
