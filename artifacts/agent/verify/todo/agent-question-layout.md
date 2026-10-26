# task-162 选择题卡片排版重做（纵向堆叠 + 解释 2 行 clamp）报告

> 人：「一个选项常常由选项+解释，你的排版是各占选项的一半，会话栏窄的时候解释字数多撑爆高度」。
> Lead 定位正确：`app.css` 里 `.-agent-question-opt` 横向 flex，`-label` 与 `-desc` 分栏 ⇒ 窄栏 desc 可用宽度趋 0 ⇒ 逐字换行爆炸。

---

## 0. 结论速览
- ✅ 选项改为**永远纵向**：单选/勾选框 + 选项名一行（省略号）→ 解释独立一行，**2 行 clamp**。
- ✅ **实测（同一真机探针、同一夹具）**：会话栏 260px 宽 + 10 选项长解释
  - **改前 14,624px → 改后 771px（−94.7%，减少 13,853px）**；单选项行高 **1,441px → 58px**；解释 **1,431px → 31px（2 行）**。
- ✅ 完整解释不丢：**聚焦展开**（键盘可达，`focus-within`）+ **选中保持展开**（`input:checked`）+ **hover 原生 title**（选项名/解释都有）。
- ✅ 单选/多选徽标、禁用态、已答态（`--done` opacity 0.72）、自定义输入框、答题/提交流程**未改**。
- ✅ 同类排版清单已排查（见 §5），本任务只改选择题卡片。

---

## 1. 改动（2 个文件，小 diff）
```
app.css            +39/−5   （只替换 .-agent-question-opt / -label / -desc 三块 + 展开规则）
agent-question.js  +2/−2    （只给 label/desc 加 title 属性；无逻辑/答案形状改动）
```
- 布局：`display:grid; grid-template-columns:auto minmax(0,1fr)`；input 与 label 同一行，**desc `grid-column:1/-1` 独占下一行**。
- 选项名：`white-space:nowrap; overflow:hidden; text-overflow:ellipsis`（1 行，不撑高）。
- 解释：`display:-webkit-box; -webkit-line-clamp:2; overflow:hidden; max-height:calc(2*1.4em)`（WebView2 实测 clamp 生效；`scrollHeight 77 > clientHeight 31`）。
- 展开（不破坏总高度上限，只展开当前项）：
  `.-agent-question-opt:focus-within .desc, .-agent-question-opt:has(input:checked) .desc { display:block; -webkit-line-clamp:unset; max-height:none; }`
- title：`title="${esc(option.label)}"` / `title="${esc(option.description)}"`。

---

## 2. 实测方法与判据（不是截图估算）
- 真机 WebView2（pywebview）+ **真实渲染器** `window.MemoriaAgentQuestion.cardEl(row)` 建卡，注入 `width:260px` 容器（容器 padding 8 ⇒ **卡片内容宽 244px**，比 260 更保守），每选项：长名称 + 约 140 字长解释 × 10 项。
- 同一探针先后跑「改前 HEAD」与「改后工作区」，数值来自 `getBoundingClientRect()`。
- 产物：`agent-question-layout-before.json` / `agent-question-layout-after.json` + 日志 + 截图。

### 数值（会话栏 260px ≈ 卡片内容 244px）
| 指标 | 改前 | 改后 | 变化 |
|---|---|---|---|
| 卡片总高 `. -agent-question` | **14,624 px** | **771 px** | **−94.7%** |
| 10 选项容器 `. -agent-question-opts` | 14,465 px | 612 px | −95.8% |
| 单选项行高（典型） | 1,441 px | 58 px | −96.0% |
| 单条解释高度 | 1,431 px（无 clamp，约 93 行） | 31 px（2 行 clamp） | −97.8% |
| 选项名行高 | 19 px | 17 px | — |
| 展开（聚焦首项） | 14,624（本来就全高） | **833 px**（仅首项 desc 31→92，其余不变） | +62px |
| 已答态（失焦） | 14,624 | 771 px | — |

**上限判据**：会话栏 260px + 10 选项卡片总高 **≤ 900px** 作为接受线；实测 **771px**，通过。
宽栏 700px 对照：改前 757px（行 56）→改后 771px（行 58，+14px/+1.8%）；这是"永远纵向、不做宽窄两套布局"的既定代价（Lead 明确要求不自行加自适应），换来单一回归面与窄栏安全。

---

## 3. 完整解释的获取（不丢信息）
- **键盘**：Tab 到选项 input ⇒ `:focus-within` 展开该条全文（实测 card 771→833，desc 31→92）；其余行保持 2 行。
- **选中**：点击选中后若失焦，`:has(input:checked)` 仍保持展开（实测 selected: cardHeight 833、descHeight 92、`hasSupport=true`）。
- **鼠标**：hover 原生 `title` 显示全文（实测 `descTitle` 为完整解释；选项名也有 title，防省略号丢信息）。
- 展开只作用于当前项，不会把 10 项卡片重新撑爆。

---

## 4. 语义未变（实测/代码事实）
- 单选徽标：`modeBadge="单选"`；多选卡片 `modeBadge="多选"` 且 `input[type=checkbox]` 2 个（单选 radio 逻辑未动）。
- 已答态：`.-agent-question--done` 下 `. -agent-question-item` `opacity=0.72` 实测保持；卡片高度不变。
- 自定义输入框 `.-agent-question-custom` 样式/提交流程未改；`collect()`/`submitCard()` 未动。
- 禁用态：未新增/覆盖任何 `input` 状态样式（只加了 `margin:0; align-self:center`），`disabled` 仍走 UA 表现。
- 未动 i18n 键、未动答题轮询/收起逻辑。

---

## 5. 同类「横向 label + flex:1 desc」排查清单（本任务只改选择题）
方法：扫 `app.css` 的 `display:flex` + 子项 `flex:1/1 1 auto` + `min-width:0` 块，并人工核对同类卡片模板。
| 位置 | 规则 | 窄栏风险 | 结论 |
|---|---|---|---|
| `app.css:6051` `. -agent-tool`（`agent-panel.js:5154-5160` 工具行） | 横向 `flex-wrap:wrap`，summary `nowrap+ellipsis` | 低：不换行、可 wrap | 安全，未改 |
| `app.css:7156` `. -agent-approve-cmd`（审批卡命令） | 已是 `flex-direction:column` | 无 | 安全 |
| `app.css:5424/5429` `. -hist-row` / `. -hist-title` | 横向标题 `nowrap+ellipsis` | 低 | 安全 |
| `app.css:5919` `.plan-op-name`（计划操作行） | `flex:1 1 auto; min-width:0`，兄弟行 `nowrap` | 低 | 安全 |
| `agent-panel.js:710-723` sources 行 | 纵向 box 内 span | 无 | 安全 |
| `app.css:1694` `. -toolbar-search-main` / `1956` `. -config-item-main` | 列 / `flex-wrap:wrap` | 低 | 安全 |
| `app.css:3457` `#tabs`、`4345` `. -block-edit-tools` | 横向滚动 | 低（滚动而非换行） | 安全 |
| **`app.css:6551` `. -agent-question-opt`**（本任务） | 横向 label + flex:1 desc，desc **无 clamp、可无限换行** | **高：本次实测 14,624px** | **已改纵向** |

未发现其它"解释放在 flex 剩余宽度里且可无限换行"的卡片；如后续新增同类，建议沿用本次纵向 + clamp 形态。

---

## 6. 真机截图（`artifacts/agent/verify/todo/agent-question-layout-screens/`）
- `before-narrow-260.png`（改前：10 选项卡片 14,624px）
- `before-wide-700.png`（改前宽栏）
- `after-narrow-260.png`（改后窄栏：纵向、名称 1 行、解释 2 行省略号）
- `after-wide-700.png`（改后宽栏，仍是同一纵向布局）
- `after-expanded-focus.png`（聚焦首项：该条展开全文，其余保持 2 行）
- `after-selected-expanded.png`（点击选中后失焦仍展开）
- `after-done-260.png`（已答态：opacity 0.72、高度不变）

---

## 7. 门禁（本轮）
- `pytest -q tests`：**1516 passed**（与基线一致）
- `node --check`：66 个非 vendor JS 全过
- `i18n_selftest`：PASS（exit 0）
- `team_audit`：**FAIL=0**；`prompt_drift`：FAIL=0 exit 0；12 剧本 12/12
- 真机探针 exit=0；用户 `Memoria.exe` PID 48812 前后一致；端口 9595 已释放；未写 `docs/example/AAA_Vocab/**`

---

## 8. 产物
```
artifacts/agent/verify/todo/
  agent-question-layout.md                 （本报告）
  agent-question-layout-probe.mjs          （真机探针：真实渲染器 + 260/700 测量 + 展开/选中/已答）
  agent-question-layout-run.ps1            （launcher：临时 KB/config、端口 9595）
  agent-question-layout-before.json/.log   （改前：14,624px）
  agent-question-layout-after.json/.log    （改后：771px）
  agent-question-layout-screens/*.png      （10 张，含改前/改后/宽窄/展开/已答）
```

## 9. 限制（如实）
1. 探针用 260px 固定容器注入真实卡片（未打开真实 agent dock 会话），CSS/渲染器与真实卡片完全一致；容器 padding 使卡片内容宽 244px，比 260 更保守。
2. 展开依赖 `:has()`（本 WebView2 实测支持）；键盘路径另有 `:focus-within` 兜底。
3. 宽栏比旧横向略高（+2px/行）：按 Lead 要求**不做宽窄自适应**，保持单一回归面。
4. 禁用态未新增样式（仅依赖 UA + 既有 disabled 规则），因此没有"禁用态新旧差异"。
