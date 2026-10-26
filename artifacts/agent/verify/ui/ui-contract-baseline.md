# UI 契约现状基线（机检冻结快照）

> 机器可读版本：`ui-contract-baseline.json`（**逐条** rule/severity/file/line/selector/prop/value）；
> 生成命令：`python scripts/check_ui_contract.py --update-baseline`；契约：`docs/conventions/ui-contract.md`。
> 语义：基线内违规**不阻断**（存量债），新增违规才 FAIL；基线只允许变小（`--force` 例外）。

## 汇总

| 约束 | FAIL | WARN |
|---|---|---|
| C2 | 176 | 7 |
| C3 | 21 | 30 |
| C4 | 0 | 1 |
| C5 | 0 | 3 |
| C7 | 13 | 19 |
| **合计** | **210** | **60** |

## 主要集中点（file × rule 计数）

| 文件 | 约束 | 条数 |
|---|---|---|
| `app/css/app.css` | C2 | 168 |
| `app/css/app.css` | C3 | 44 |
| `app/css/app.css` | C7 | 31 |
| `theme/memoria.css` | C2 | 10 |
| `theme/light.css` | C2 | 5 |
| `theme/mermaid.css` | C3 | 4 |
| `theme/memoria.css` | C3 | 3 |
| `` | C5 | 3 |
| `app/js/agent-panel.js` | C4 | 1 |
| `theme/light.css` | C7 | 1 |

## 需要优先看的条目（C7 主题 token / C4 双源 / C3 字号圆角 FAIL）

- `app/css/app.css:3938` [C3][FAIL] `.-editor` — 字号/行高必须用 rem（跟随“界面缩放/字号”设置），禁止 px (14px)
- `app/css/app.css:3953` [C3][FAIL] `.-preview` — 字号/行高必须用 rem（跟随“界面缩放/字号”设置），禁止 px (14px)
- `app/css/app.css:4013` [C3][FAIL] `.-preview .-math-pending .-math::after, .-preview .-math-pending .-mat` — 圆角不在档位 [4, 6, 8, 12, 999] 内（档位来自 ui-visual-language B-6） (3px)
- `app/css/app.css:4032` [C3][FAIL] `.-preview h1.-src-block` — 字号/行高必须用 rem（跟随“界面缩放/字号”设置），禁止 px (14px)
- `app/css/app.css:4033` [C3][FAIL] `.-preview h2.-src-block` — 字号/行高必须用 rem（跟随“界面缩放/字号”设置），禁止 px (14px)
- `app/css/app.css:4034` [C3][FAIL] `.-preview h3.-src-block` — 字号/行高必须用 rem（跟随“界面缩放/字号”设置），禁止 px (14px)
- `app/css/app.css:5574` [C3][FAIL] `.-hist-row--referenced` — 圆角不在档位 [4, 6, 8, 12, 999] 内（档位来自 ui-visual-language B-6） (3px)
- `app/css/app.css:5586` [C3][FAIL] `.-agent-think` — 圆角不在档位 [4, 6, 8, 12, 999] 内（档位来自 ui-visual-language B-6） (3px)
- `app/css/app.css:5652` [C3][FAIL] `.-agent-stream-wait-raw` — 圆角不在档位 [4, 6, 8, 12, 999] 内（档位来自 ui-visual-language B-6） (3px)
- `app/css/app.css:5851` [C3][FAIL] `.-agent-composer-chip` — 圆角不在档位 [4, 6, 8, 12, 999] 内（档位来自 ui-visual-language B-6） (3px)
- `app/css/app.css:7043` [C3][FAIL] `.-mmd-zoom-btn` — 字号/行高必须用 rem（跟随“界面缩放/字号”设置），禁止 px (13px)
- `app/css/app.css:7084` [C3][FAIL] `.-mmd-zoombar` — 字号/行高必须用 rem（跟随“界面缩放/字号”设置），禁止 px (11px)
- `app/css/app.css:7089` [C3][FAIL] `.-mmd-zoombar` — 圆角不在档位 [4, 6, 8, 12, 999] 内（档位来自 ui-visual-language B-6） (5px)
- `app/css/app.css:7103` [C3][FAIL] `.-mmd-zoombar .-mmd-zoom-btn` — 字号/行高必须用 rem（跟随“界面缩放/字号”设置），禁止 px (13px)
- `app/css/app.css:7110` [C3][FAIL] `.-mmd-zoombar .-mmd-zoom-btn` — 圆角不在档位 [4, 6, 8, 12, 999] 内（档位来自 ui-visual-language B-6） (3px)
- `app/css/app.css:7806` [C3][FAIL] `.-link-panel-rs:hover, .-link-panel-rs.-active` — 圆角不在档位 [4, 6, 8, 12, 999] 内（档位来自 ui-visual-language B-6） (3px)
- `theme/memoria.css:78` [C3][FAIL] `*::-webkit-scrollbar-thumb` — 圆角不在档位 [4, 6, 8, 12, 999] 内（档位来自 ui-visual-language B-6） (3px)
- `theme/memoria.css:337` [C3][FAIL] `#group-tabs::-webkit-scrollbar-thumb` — 圆角不在档位 [4, 6, 8, 12, 999] 内（档位来自 ui-visual-language B-6） (3px)
- `theme/mermaid.css:79` [C3][FAIL] `.-mermaid-container .nodeLabel, .-mermaid-container .node foreignObjec` — 字号/行高必须用 rem（跟随“界面缩放/字号”设置），禁止 px (13px)
- `theme/mermaid.css:84` [C3][FAIL] `.-mermaid-container text.nodeLabel, .-mermaid-container text .tspan` — 字号/行高必须用 rem（跟随“界面缩放/字号”设置），禁止 px (13px)
- `theme/mermaid.css:107` [C3][FAIL] `.-mermaid-container .noteText > tspan, .-mermaid-container .noteText` — 字号/行高必须用 rem（跟随“界面缩放/字号”设置），禁止 px (12.5px)
- `app/js/agent-panel.js:231` [C4][WARN] `contentMinPx` — 同一范围在 app/js/display-settings.js 之外又写了一份（当前一致，但迟早漂移；应收口到单一导出） ((180, 560))
- `app/css/app.css:179` [C7][FAIL] `.-import-section-title` — `--border-subtle` 只在浅色主题定义、深色无定义且此处无兜底 ⇒ 深色下该声明失效 (--border-subtle)
- `app/css/app.css:1644` [C7][FAIL] `.-suggest-score--muted` — `--text-muted` 只在浅色主题定义、深色无定义且此处无兜底 ⇒ 深色下该声明失效 (--text-muted)
- `app/css/app.css:1659` [C7][FAIL] `.-search-section-label` — `--text-muted` 只在浅色主题定义、深色无定义且此处无兜底 ⇒ 深色下该声明失效 (--text-muted)
- `app/css/app.css:1660` [C7][FAIL] `.-search-section-label` — `--border-subtle` 只在浅色主题定义、深色无定义且此处无兜底 ⇒ 深色下该声明失效 (--border-subtle)
- `app/css/app.css:1817` [C7][WARN] `.-kp-tag-pick--cand-system` — `--text-muted` 未定义，仅靠兜底值（深浅主题下都走 fallback，属未收口） (--text-muted)
- `app/css/app.css:2507` [C7][FAIL] `.-toolbar-search-scope-btn` — `--text-muted` 只在浅色主题定义、深色无定义且此处无兜底 ⇒ 深色下该声明失效 (--text-muted)
- `app/css/app.css:2566` [C7][WARN] `.-toolbar-search-panel` — `--bg-elevated` 未定义，仅靠兜底值（深浅主题下都走 fallback，属未收口） (--bg-elevated)
- `app/css/app.css:2603` [C7][WARN] `.-search-field input` — `--bg-input` 未定义，仅靠兜底值（深浅主题下都走 fallback，属未收口） (--bg-input)
- `app/css/app.css:2652` [C7][WARN] `.-flash-error` — `--bg-elevated` 未定义，仅靠兜底值（深浅主题下都走 fallback，属未收口） (--bg-elevated)
- `app/css/app.css:2670` [C7][WARN] `.-flash-info` — `--bg-elevated` 未定义，仅靠兜底值（深浅主题下都走 fallback，属未收口） (--bg-elevated)
- `app/css/app.css:2873` [C7][FAIL] `.-link-match-row.is-substring .-link-match-badge, .-link-match-row.is-` — `--text-muted` 只在浅色主题定义、深色无定义且此处无兜底 ⇒ 深色下该声明失效 (--text-muted)
- `app/css/app.css:2879` [C7][FAIL] `.-link-match-check-placeholder` — `--text-muted` 只在浅色主题定义、深色无定义且此处无兜底 ⇒ 深色下该声明失效 (--text-muted)
- `app/css/app.css:2904` [C7][FAIL] `.-link-match-section` — `--text-muted` 只在浅色主题定义、深色无定义且此处无兜底 ⇒ 深色下该声明失效 (--text-muted)
- `app/css/app.css:3762` [C7][WARN] `.-color-picker` — `--border-color` 未定义，仅靠兜底值（深浅主题下都走 fallback，属未收口） (--border-color)
- `app/css/app.css:3784` [C7][WARN] `.-cp-preview` — `--border-color` 未定义，仅靠兜底值（深浅主题下都走 fallback，属未收口） (--border-color)
- `app/css/app.css:3792` [C7][WARN] `.-cp-sv` — `--border-color` 未定义，仅靠兜底值（深浅主题下都走 fallback，属未收口） (--border-color)
- `app/css/app.css:3824` [C7][WARN] `.-cp-hue::-webkit-slider-runnable-track` — `--border-color` 未定义，仅靠兜底值（深浅主题下都走 fallback，属未收口） (--border-color)
- `app/css/app.css:3840` [C7][WARN] `.-cp-hue::-moz-range-track` — `--border-color` 未定义，仅靠兜底值（深浅主题下都走 fallback，属未收口） (--border-color)
- `app/css/app.css:3877` [C7][WARN] `.-cp-hex` — `--border-color` 未定义，仅靠兜底值（深浅主题下都走 fallback，属未收口） (--border-color)
- `app/css/app.css:3886` [C7][WARN] `.-cp-row button` — `--border-color` 未定义，仅靠兜底值（深浅主题下都走 fallback，属未收口） (--border-color)
- `app/css/app.css:3982` [C7][WARN] `.-preview .-pv-placeholder` — `--pv-placeholder-bg` 未定义，仅靠兜底值（深浅主题下都走 fallback，属未收口） (--pv-placeholder-bg)
- `app/css/app.css:4011` [C7][WARN] `.-preview .-math-pending .-math::after, .-preview .-math-pending .-mat` — `--pv-placeholder-bg` 未定义，仅靠兜底值（深浅主题下都走 fallback，属未收口） (--pv-placeholder-bg)
- `app/css/app.css:6479` [C7][WARN] `.-plugins-err` — `--danger` 未定义，仅靠兜底值（深浅主题下都走 fallback，属未收口） (--danger)
- `app/css/app.css:7385` [C7][FAIL] `.-review-manage-toolbar input[type="search"]` — `--bg` 未在 theme/memoria.css(:,local/JS) 定义且无兜底 ⇒ 该声明在运行期无效 (--bg)
- `app/css/app.css:7386` [C7][FAIL] `.-review-manage-toolbar select` — `--bg` 未在 theme/memoria.css(:,local/JS) 定义且无兜底 ⇒ 该声明在运行期无效 (--bg)
- `app/css/app.css:7391` [C7][FAIL] `.-review-manage-card` — `--bg` 未在 theme/memoria.css(:,local/JS) 定义且无兜底 ⇒ 该声明在运行期无效 (--bg)
- `app/css/app.css:7395` [C7][WARN] `.-rm-cid` — `--mono` 未定义，仅靠兜底值（深浅主题下都走 fallback，属未收口） (--mono)
- `app/css/app.css:7396` [C7][WARN] `.-rm-type` — `--theme-color-soft` 未定义，仅靠兜底值（深浅主题下都走 fallback，属未收口） (--theme-color-soft)
- `app/css/app.css:7396` [C7][FAIL] `.-rm-type` — `--bg` 未在 theme/memoria.css(:,local/JS) 定义且无兜底 ⇒ 该声明在运行期无效 (--bg)
- `app/css/app.css:7403` [C7][FAIL] `.-rm-field input, .-rm-field select, .-rm-field textarea` — `--bg` 未在 theme/memoria.css(:,local/JS) 定义且无兜底 ⇒ 该声明在运行期无效 (--bg)
- `app/css/app.css:7624` [C7][WARN] `.-link-panel-doc pre` — `--border-subtle` 未定义，仅靠兜底值（深浅主题下都走 fallback，属未收口） (--border-subtle)
- `theme/light.css:0` [C7][WARN] `light-override` — 颜色 token `--theme-color` 没有浅色覆盖 ⇒ 浅色主题沿用深色取值（#007acc） (#007acc)

## 说明

- **C1 `!important` = 0 FAIL**：37 条声明已逐条登记豁免（契约 `important-exemptions`，每条含理由），检查确实跑过。
- **C2 硬编码颜色 176 FAIL**：主要是状态色回退值、链接/选区高亮、按钮实心色、调色板；清零需要新 token（如 `--text-on-accent`）与替换批次，不在本批完成。
- **C3 21 FAIL**：字号 px 8 条 + 圆角离档若干；**WARN 30 条**是间距离格（1/3/5/7px）。
- **C7 13 FAIL**：`--bg`×5（未定义且无兜底，真 bug）、`--border-subtle`×3、`--text-muted`×5 —— 已由真机 computed-style 探针确认为**真缺陷**（见 `theme-probe.json` / `ui-owner-inaugural.md`）。
- **C5 3 WARN** = C10 已知层级债务（模态低于搜索/右键/取色器），登记在案，不是新问题。
- 完整逐条清单见 JSON（270 条）。

