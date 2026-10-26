# task-169 — 会话输入框「显式高度把手」+ 上下文用量圆环移到输入框下方

> 基线：**HEAD `f21307ac`**（task-164 + task-168 合并提交之后）。
> 开工时 `git status -- app.css agent-panel.js i18n` 只有 `app.css` 一处非我改动待确认；
> 实测当前 `git diff -- app.css` 的 74 行**全部是本次任务**（原生 resize 两行 + 末尾追加块），未 revert 任何 ui-designer 已合入内容。
> 未 commit；未动 `docs/example/**`、`Package/**`、`src/memoria/services/**`。

## 人原话

> 「会话输入框只需要调整高，因为宽是自适应」
> 「上下文占用的那个样式不要显示在底栏，应该显示在输入框底下」

---

## 1. 改了什么

### A. 输入框：去掉原生小把手 → 显式高度把手（只调高）

| 项 | 实现 |
|---|---|
| 原生把手 | `app.css: .-agent-input` `resize: vertical` → **`resize: none`**（人嫌「尴尬」的小把手消失） |
| 显式把手 | `agent-panel.js#setupComposerResize()` 惰性创建 `#agent-input-resize`，**紧贴输入框下边缘**（`input.nextSibling`），与框同宽 331px、**命中区高 10px**，`cursor: ns-resize`，hover/focus/拖拽时把手变主题色 |
| 只调高度 | 拖拽只写 `input.style.height`；**宽度恒 100%**（不写 width，实测拖前/拖后宽度 331→331） |
| 上下夹 | `min-height`(computed 44px) ~ **60% 视口**（`COMPOSER_HEIGHT_MAX_RATIO=0.6`；实测 max-height=492.6px @ innerHeight 821）；窗口变小时自动重新夹紧 |
| 跟手 | `pointerdown + setPointerCapture`（指针移出/出窗口仍继续）；拖拽映射：**底部把手向上拖 = 变高**（composer 底边锚定，框向上长），向下拖 = 变矮 |
| 键盘可达 | 把手 `tabIndex=0` + `ArrowUp/ArrowDown` 每次 24px（受同一夹紧） |
| 记住高度 | 写入 `ui_settings.agent.composerHeightPx`（统一入口，浅合并安全；不碰 `layout`）；**300ms 防抖**只落盘“最新高度”（避免多次 read-modify-write 乱序把旧值写成最终值——首版真机抓到过 211 被 187 覆盖） |
| i18n | 新增 `agent.input.resizeHint`（zh/en 双语文案，悬停提示“只调高，宽度自适应”） |

### B. 上下文用量圆环：从底栏 → 输入框下方

| 项 | 实现 |
|---|---|
| 宿主 | `renderContextRing()` 不再 `#status-bar.appendChild`；改为在 `. -agent-composer` 内惰性建 `#agent-ctx-ring-row`，`insertBefore(actions)` ⇒ 位于**输入框下方、发送按钮行上方**，右对齐（不抢输入焦点，尺寸保持 14px） |
| 底栏 | 底栏**不再挂环**（实测 `#status-bar #agent-ctx-ring` 不存在）；旧节点 `#status-ctx-ring` 若残留则移除；CSS 额外 `#status-bar #status-ctx-ring{display:none}` 兜底 |
| 四态语义（一条不改） | ① 缺失 ⇒ **灰环 + “上下文用量未知…”**，不报错不瞎报 0%；② 比例 = **chars÷chars**（`contextUsageView` 未改）；③ `over`（>threshold≈80%）⇒ 警示色 `#ffd75e`；④ 悬停 title/aria 含 `字符 / 上限（百分比）` 与 **“已压缩 N 次”** |
| 底栏 token 口径 | `#status-agent` 的 base token 文本路径**完全未动**（`renderStatusUsage` 先写 token，`applyContextUsageToStatus` 只追加/不动 base）；底栏仍有 `#status-agent`，环不在其中 |
| 诊断出口 | `MemoriaAgentPanel.renderContextRingForTest(view)`（**仅供探针**，与生产同一 `renderContextRing`）—— 四态真机验证用 |

**文件**：`src/memoria/ui/static/app/js/agent-panel.js`（+166/−10 左右）、`src/memoria/ui/static/app/css/app.css`（+74/−2）、`i18n/zh-CN.js`、`i18n/en.js`（各 +4）、`tests/test_agent_composer_resize_ctxring.py`（新增 4 条结构回归）。

---

## 2. 真机验证（pywebview + WebView2；脚本 `verify.py`，数据 `verify.json`，截图 `shots/`）

### A. 输入框（关条件 1/4）

| 断言 | 实测 |
|---|---|
| 原生 resize 已去掉 | `getComputedStyle(#agent-input).resize = "none"` |
| 显式把手存在、在输入框下边缘、命中区 ≥8px | 把手 331×10px，`input.nextElementSibling === handle`，parent=`.-agent-composer`，cursor=`ns-resize`，title=中文提示 |
| 只调高、宽度不变 | 拖拽前 h=52.59px / w=331px ⇒ 向上拖 110px 后 **h=163px / w=331px**（`only_height: true`） |
| 上下夹 | min-height=44px；max-height=492.6px（=60%×821） |
| 键盘可微调 | 点击把手聚焦后 ↑×2：163 → **211px** |
| 高度被记住 | `ui_settings.agent.composerHeightPx = 211`；**重启 app 后**输入框高度 = 211px、style=`211px`，`matches: true` |

### B. 圆环四态（关条件 2/4）

| 态 | 实测输出 |
|---|---|
| 未知 | `class="-ctx-ring -ctx-ring--unknown"`；title/aria「上下文用量未知（旧会话或尚未载入）」 |
| 正常 62% | `class="-ctx-ring"`；title「字符预算：19.8k / 32k 字符（62%）」 |
| over 81% | `class="-ctx-ring -ctx-ring--warn"`；title「…（81%）」+ 警示色（见 `04_ring_over.png` 黄环） |
| 压缩过 | title「…（38%） · 已压缩 3 次」 |

四个态共同断言：`inComposer=true`（在 `. -agent-composer` 内）、`belowInput=true`（圆环 top ≥ 输入框 bottom）、`statusBarHasRing=false`（底栏无环）。

### C. 底栏 token 口径（关条件 3）

- `#status-agent` 元素仍在底栏（`statusAgentPresent=true`），环不在其中；
- token 文本由 base `renderStatusUsage` 写入、字符预算只追加，**代码路径未改**；单测 `test_compact_budget_never_clobbers_the_token_segment`（断言 token 段原样保留）本次全绿。
- 诚实说明：探针环境无真实 LLM 会话 ⇒ 截图里 `#status-agent` 文本为空（无 token 可显示）；**口径未丢由代码路径 + 单测证明**，不是靠截图。

### D. 截图（`shots/`）

```
01_composer_initial.png        初始（未知灰环在输入框下方）
01b_handle_hover.png           把手 hover 高亮 + ns-resize
02_status_bar_no_ring.png      底栏：无环（token 格仍在）
03_after_resize.png            调高后：把手 + 下方圆环 + 发送行不重叠
04_ring_unknown/normal/over/compacted.png   四态
05_after_restart.png           重启后高度保持
```

**调高后不重叠、不被遮挡**：调高到 163px/211px 后圆环 `y=745`，输入框 `bottom≈729`，发送行在圆环下方（截图 03/05 可见）。

---

## 3. 门禁（新基线 1520）

| 门禁 | 结果 |
|---|---|
| `pytest -q` | **1524 passed / 0 failed**（88s；新基线 1520 + 本次 4 条结构回归） |
| `node --check`（前端全部 js） | **0 fail** |
| `i18n_selftest.js` | **PASS，exit 0**（新增 resizeHint zh/en 配对） |
| `team_audit.py` | **FAIL=0**（80 条：WARN 51 / INFO 29，均既有） |
| 12 交互剧本 | **12/12，failed=0**（30.9s；`scripts/benchmark/surface/results/raw-interaction-t169-final_f21307ac.json`） |

---

## 4. unknowns / not_doing

- **环的“未知态”在未开过会话时也常显灰环**：这与 task-144 原行为一致（状态格渲染时即挂环），不是本次新增；若人希望“无 agent 面板时彻底不显示”，需另立规则（未做）。
- **未做横向调整**：宽恒 100%（人明确「宽度自适应」）。
- **高度上限用 60% 视口**：按任务书建议值；若人希望更小/更大，改一个常量即可（`COMPOSER_HEIGHT_MAX_RATIO`）。
- **`docs/reference/i18n-inventory.md` 未重生成**：不在本任务写域（i18n 文案已双写、`i18n_selftest` 通过）。
- **未引入第三方库**：把手与 SVG 环全部原生实现（零前端依赖约束）。
