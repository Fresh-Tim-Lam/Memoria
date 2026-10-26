# task-183 交付报告：「缓存命中率」从状态条移到会话栏底部（输入框下方，与上下文圆环同一行）

> 状态：**完成**（未 commit，按纪律）；owner：ui-designer；日期 2026-10-26。
> 真机证据：`verify.json`（19 条 DOM 断言，19 PASS / 0 FAIL）+ 5 张截图；机检：pytest 1624 / node 0 fail / i18n PASS / team_audit FAIL=0 / 12 剧本 12/12。

## 0. 开工基线（Lead 要求先记）

- `git log --oneline -3` HEAD = `be4e9dec`（feat(update) …）
- 开工前 `git status --porcelain -- src` **干净**：`agent-panel.js` / `app.css` 无未提交改动（没有别的 agent 正在写这两个文件）。
- 进入本任务前唯一未提交项（上一批 Lead 已批准方向的 C4 机检补强）：`docs/conventions/ui-contract.md`、`scripts/check_ui_contract.py` —— **与本任务无关**，见 §7。

## 1. 改了什么（4 个文件，全部在写域内）

| 文件 | 改动 | 行数 |
|---|---|---|
| `src/memoria/ui/static/app/js/agent-panel.js` | ① `renderStatusBar()` 事实串第 4 槽（缓存命中率）**原位换成注释**，数组 4→3 项；② `return {` 之前新增「缓存格」块（约 102 行）：`cacheHitDetailLines()`（纯函数，hit/miss/rate 口径）、`ensureCacheRow()`、`renderCacheHit()`，并用既有"包装而非改行"模式包 `renderStatusBar` / `renderStatusUsage` | `+107 / -4`（净 +103；见 §2 零漂移核验） |
| `src/memoria/ui/static/app/css/app.css` | **文件末尾追加** 24 行：`.-agent-ctx-ring-row { gap: .5rem }`、`.-agent-cache-hit{…}`、`#agent-ctx-ring{order:0}` | `+24 / -0`（纯追加） |
| `tests/test_agent_cache_indicator.py` | 新增 6 条回归（结构不变量 + `cacheHitDetailLines` node 实跑 + i18n 键 + CSS 规则） | 新文件 |
| `artifacts/agent/verify/todo/agent-panel-cache-indicator/**` | 真机探针套件（见 §3）：`probe.mjs` / `run_probe.ps1` / `launch_with_cdp.py` / `make_fixture.py` / `verify.json` / 5 张截图 | 新目录 |

**没动**：`i18n/*`（全部复用既有键，无新键）、`app.js`、`index.html`、`docs/design/**`、`docs/example/**`、`Package/**`、`src/memoria/services/**`；圆环渲染器 `renderContextRing()` **一行未改**；状态点 4 态、出网/模型/余额事实串、输入框高度把手、面板折叠态均未动。

## 2. 布局决定 + 零行漂移核验

- **位置**：与圆环**同一行**（task-169 的 `#agent-ctx-ring-row`，composer 内、输入框下方、发送按钮行上方），沿用该行 `justify-content: flex-end` ⇒ 右侧成组：`（左）圆环` `（右）缓存命中率 60%`，两者 gap 8px。
- **顺序**：CSS `#agent-ctx-ring{order:0}` / `.-agent-cache-hit{order:1}` ⇒ 不论 DOM 谁先创建，视觉恒为「圆环在左、文字在右」。
- **字号/颜色**：11px / `--text-secondary`，与它原来所在的 `.-agent-statusbar`（`app.css:5100` 起 `font-size:.6875rem`）完全一致 ⇒ 移动前后观感连续、不抢输入框焦点。
- **窄宽**：`min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap` ⇒ 260px 面板也不换行、不挤压圆环（实测见 T6）。
- **零行漂移核验**（本仓 312 处 `app.css:<行号>` + 大量 `agent-panel.js:<行号>` 文档锚点）：
  - `git diff -U0` 显示 agent-panel.js 只有 4 个 hunk：`-1 +1`（BOM 行，已恢复）之外，`-1959,3/+1959,3`、`-1968/+1968`、`+7495,102`、末尾 `+1`（空行）；**新增块插在 `return {`（原 7495 行）之前**，故此前所有行号不变；
  - `docs/**` 中对 `agent-panel.js` 行号 ≥7300 的引用实测 **0 处**（脚本统计），故 7495 之后的整体下移不影响文档锚点；
  - app.css 只追加在文件末尾 ⇒ 既有锚点零漂移。

## 3. 验收实测（真机 `memoria.app.desktop`，DOM 证明而非截图）

探针：`artifacts/agent/verify/todo/agent-panel-cache-indicator/run_probe.ps1` → 启动真实应用（独立临时 KB `tests/probe-kb` 副本 + 独立 `MEMORIA_CONFIG_DIR`，不碰用户库/用户设置）→ `probe.mjs` 通过 CDP 用 `Runtime.evaluate` 读 DOM/`getBoundingClientRect`/`getComputedStyle`。
JSON：`verify.json`（`checks` 数组逐条含 detail 数据）。**19 PASS / 0 FAIL**。

| 验收 | 结果 | 实测证据（来自 verify.json） |
|---|---|---|
| **T1** 状态条不再有命中率 | ✅ | `#agent-statusbar` 文本 = `"模型 deepseek-chat · 网络 · —"`（不含"缓存命中率/Cache hit"）；`#agent-cache-hit` 父节点 = `#agent-ctx-ring-row`（`cacheInStatusbar=false`）；事实串内旧槽选择器命中 0 个 |
| **T2** 在输入框下方 + 与圆环不相交 | ✅ | `cache.top=743.61` ≥ `input.bottom=727.61`；`ring={left:1162.98,right:1176.98}` / `cache={left:1184.98,…}` ⇒ `ring.right ≤ cache.left`；与 `.-agent-composer-actions`（`top=765`）不重叠；font-size=11px、color=rgb(133,133,133) |
| **T3** 悬停明细完整（hit/miss/rate） | ✅ | 无会话：`["缓存：未知（端点未上报，或为本次改动之前的旧会话）","缓存命中率 —"]`；载入 fixture 会话（`loop/end.usage` cache_read=60/cache_miss=40/prompt=100）后：`["缓存：命中 60 / 未命中 40 / 命中率 60%","缓存命中率 60%"]`；`aria-label == 可见文本` |
| **T4** 状态条无空壳 | ✅ | facts = 3 项、空段 0、分隔符 2（`"模型 deepseek-chat · 网络 · —"`）；第 4 槽既无节点也无空白 |
| **T5** 输入框调高/调低后跟随 | ✅ | 真指针拖 `#agent-input-resize`：52.6 → **133** → **44** px；两次 `cache.top ≥ input.bottom`、与圆环不相交、`cache.bottom(759) ≤ actions.top(765)` 不被遮挡 |
| **T6** 260px / 520px 不换行错乱 | ✅ | `setDockWidthForTest()` 实测 dock=260.0 / 520.0px：`cache` 单行（h=15.39）、`row.scrollWidth ≤ clientWidth+1`、与圆环不重叠、左右都在 composer 内 |
| **T7** 门禁 | ✅ | `pytest -q tests` → **1624 passed**（基线 1618 + 本任务 6 条，不降）；`node --check agent-panel.js` → 0；`node scripts/i18n_selftest.js` → PASS；`python scripts/agent/team_audit.py` → **FAIL=0**（WARN=56 INFO=30）；`run_interaction.py` → **剧本 12 个，失败 0 个**（`interaction-legacy-golden_*.md` 结论"✅ 全部剧本跑通"，exit 0） |

截图（附件，非判定依据）：`shot-t3-session-loaded.png`、`shot-t5-resized-input.png`、`shot-t6-260px.png`、`shot-t6-520px.png`、`shot-final.png`。

## 4. 数据与刷新路径（为什么不新增键/为什么仍显示"未知"）

- 文本：`agent.statusBar.hitRate`（既有键，"缓存命中率 {rate}"），值来自只读 RPC `agent_usage_stats(session_id).summary.hit_rate`（`hitRatePercent()`；未知 = `—`，**绝不瞎报 0%**）。
- 悬停 title：`cacheHitDetailLines(lastUsage, sessionUsage, rate)` —— 复用既有 4 个键 `agent.statusBar.cache / cacheUnknown / sessionCache / hitRate`，口径与底部 `#status-agent` 完全一致（命中/未命中/命中率 + 本会话累计缓存）。
- 刷新：包装 `renderStatusBar` 与 `renderStatusUsage` ⇒ 覆盖提交/轮询/定稿/出错/停止/清空/载入会话/换库/换语言/成本节拍（成本块本身也调 `renderStatusBar`）。初次模块求值时挂载一次（无会话 ⇒ "缓存命中率 —"）。
- 为什么能放心复用：原先第 4 槽就只显示"缓存命中率 xx%"，明细本来就在 `#status-agent` 的 title 里；现在把同一批明细挂到**新位置**，用户悬停新位置即可看到，且不新增第二条口径。

## 5. ⑤ 关于「token 用量是不是同类」——现状说明（按任务要求只报告，不擅自扩大）

- **本轮 token 用量**：仍在**应用最底部状态栏** `#status-bar #status-agent`（`renderStatusUsage()` 写 `↑prompt ↓completion` 文本 + 完整 title：本轮/本会话累计/缓存明细/click 提示），**没有**挪到输入框下方。
- **上下文占用**：圆环（输入框下方，task-169）+ 其 tooltip（字符口径 chars/max）。
- **缓存命中率**：本次已移到输入框下方（与圆环同行）。
- 三者是**不同口径**：token 计量（本轮/累计）、上下文预算（字符/上限）、缓存命中率（hit÷prompt）。本轮只按任务把"缓存命中率"与"上下文占用圆环"归位到同一区，**未动 token 行**。
- 建议（**未实施，等拍板**）：若人希望 token 用量也进"会话栏底部"，那是另一批改动 —— 会牵动 `#status-agent` 的既有契约（`tests/test_agent_panel_token.py` 多条断言、`renderStatusUsage` 的 base 文本、底部状态栏布局），建议单开任务并给真机截图验收。

## 6. 复现方式

```powershell
# 1) fixture（复制 tests/probe-kb + 写入固定会话；会重建本目录 kb/）
python artifacts/agent/verify/todo/agent-panel-cache-indicator/make_fixture.py
# 2) 真机 DOM 验收（自动起应用、独立 KB/config、跑 T1–T6、关进程树）
powershell -NoProfile -ExecutionPolicy Bypass -File artifacts/agent/verify/todo/agent-panel-cache-indicator/run_probe.ps1 -Port 9623 -NodeExe <node.exe>
# 期望：T1–T6: 19 PASS / 0 FAIL，产物 verify.json
```

> 关键技术坑（已固化在 `launch_with_cdp.py` 注释里）：本仓 pywebview 在 `EdgeChrome.__init__` 里显式设置 WebView2 `AdditionalBrowserArguments`，而 WebView2 只在"属性未设置"时读 `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS` 环境变量 ⇒ 只设环境变量拿不到 CDP 端口。改用 pywebview 自己的 `settings['REMOTE_DEBUGGING_PORT']` 即可，**生产代码零改动**。后续任何真机 CDP 验收可复用这个启动器思路。

## 7. 边界与遗留

- **未 commit**（纪律）：`agent-panel.js`、`app.css`、新增 `tests/test_agent_cache_indicator.py`、新增证据目录，等 Lead 统一提交。
- **上一批未提交项**（与本任务无关，Lead 已知）：`docs/conventions/ui-contract.md` + `scripts/check_ui_contract.py` 的 C4 `def` 覆盖补强（selftest 22/22、基线 210 FAIL / 61 WARN）。
- **未改** i18n（无需新键 ⇒ 无 i18n 行号漂移）；未改 `docs/**`（文档索引/todo 登记由 Lead 负责）。
- 回退：`git checkout -- src/memoria/ui/static/app/js/agent-panel.js src/memoria/ui/static/app/css/app.css && rm tests/test_agent_cache_indicator.py`（零数据迁移、零 DOM 结构破坏，旧节点无残留）。
