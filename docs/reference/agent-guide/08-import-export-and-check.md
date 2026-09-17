# 08 · 导入导出与检查

> **用途**：把「文件 → 导入」向导（源选择 → 预览 → 冲突决策 → 结果）、「文件 → 导出」（当前为占位）与「检查」体系（弹窗 / 角标 / 静默后台检查 / 后台作业可观测 / 刷新与构建）写到可据以定位实现的粒度。
> **目标读者**：在 Memoria 之上做集成 / 移植 / 对齐的 Agent 与人；给 Memoria 写前端改动的人。
> **关联文档**：[README.md](./README.md)（本套用法与维护约定）、[01-shell-and-layout.md](./01-shell-and-layout.md)（顶栏 / 状态栏 / 弹窗层级）、[../import-spec.md](../import-spec.md)（**导入格式与流程权威**）、[../preview-formats.md](../preview-formats.md)（渲染语法）、[../../design/export-plan.md](../../design/export-plan.md)（导出设计稿）、[../../design/maintenance-jobs.md](../../design/maintenance-jobs.md)（作业登记）、[../i18n-inventory.md](../i18n-inventory.md)（文案清单）。
> **状态**：生效中，2026-09-15。

---

**证据锚约定**：`文件:行号` 以仓库根目录为基准。前端在 `src/memoria/ui/static/app/**`（下称 `index.html` / `app.css` / `js/*.js`）；后端在 `src/memoria/presentation/**` 与 `src/memoria/services/**`。**格式契约以 [../import-spec.md](../import-spec.md) 为权威**，本篇只写界面与交互。

## 1. 区域概览

```
顶栏 #toolbar                                   index.html:35
├── .toolbar-actions
│   ├── .-tb-file > #btn-file                   index.html:46-47（「文件」菜单按钮）
│   │   └── #file-menu                          index.html:48-60
│   │       ├── #file-menu-import               index.html:50   → 导入向导（唯一入口）
│   │       └── #file-menu-export               index.html:51   disabled（占位）
│   ├── #btn-refresh                            index.html:62
│   ├── #btn-build                              index.html:63
│   └── .-toolbar-btn-wrap                      index.html:64-67（app.css:1756-1762）
│       ├── #btn-check                          index.html:65
│       └── #btn-check-badge .-toolbar-badge    index.html:66（app.css:1768-1799）

弹窗（body 层，#app 外；index.html:222-368）
├── #import-conflict-modal .-modal              index.html:322-337（承载 源选择/预览/冲突/提示词/格式说明）
├── #import-result-modal .-modal                index.html:339-352（导入结果）
└── #check-modal .-modal.-modal-check           index.html:268-283（知识库检查）

状态栏 #status-bar                              index.html:212-215
└── #status-stats                               app.js:281-333（含检查统计块，可点击 → 检查弹窗）
```

## 2. 逐处细节

### 2.1 导入入口与向导骨架

| 项 | 证据 | 说明 |
|---|---|---|
| 入口 | index.html:50；app.js:12109-12112 | 「文件」菜单 →「导入」：`closeFileMenu()` 后 `MemoriaImportFlow.start()` |
| 未开库 | import-flow.js:43-46 | **悬浮卡片**（直调 `showFlashError`，与「创建 Trae 智能体」未开库时同一处样式）提示 `app.openKbFirst`；不写底栏 |
| 首次呈现 | import-flow.js:47-51 | `_resetState()` → `renderKindChooser()` → 标题 `import.chooseTitle`「选择导入源」→ **移除 `#import-conflict-modal` 的 `hidden`** |
| 按钮可见性状态机 | import-flow.js:64-69、255-256 | 「确认导入」`#import-conflict-confirm` 与「复制报告」`#import-conflict-copy-report` 默认隐藏，**仅在扫描完成进入预览后**出现 |
| 标题栏 | index.html:325-328；import-flow.js:71-76 | 标题是 header 内第一个 `<span>`，由 `setTitle()` 逐阶段改写（源选择 / 预览 / 提示词 / 格式说明） |

### 2.2 第 1 步：源类型选择

`renderKindChooser()`（import-flow.js:80-104）渲染 `.-import-kind-list` 内**四张卡**（`.import-kind-card`，app.css:173-186）：

| 卡片 | 键 | 说明文案 | 证据 |
|---|---|---|---|
| AI 整理（平面文件） | `import.kindFlat` | 「外部 Agent 产出的 --- 分段 .txt」 | import-flow.js:84 |
| Markdown 目录 | `import.kindMdDir` | 「选择目录递归迁移 .md（纯文件直接入库，frontmatter 建 KP）」 | import-flow.js:85 |
| 知识库包 | `import.kindBundle` | 「合并完整包（.md + sidecar）」 | import-flow.js:86 |
| **Agent 整理提示词** | `import.copyAgentPrompt` | 第 4 张卡，**不是导入源**，而是同弹窗内的辅助视图 | import-flow.js:87 |

点击卡片 → `pickSource(kind)`（import-flow.js:106-131）：`__prompt` → `loadPrompt()`（不弹文件选择框）；其余 → `_busy` 防重入 → 状态栏 `import.picking` → `select_import_sources(kind)`（ui.py:967-997）：`flat_file` 弹**多选文件**并读为 `{name, content}`，`md_dir` / `kb_bundle` 弹**目录**选择器并返回 `[{path}]`。`status==="error"` → 状态栏 `picked.message || import.failed`；**`sources` 为空视为用户取消**，直接 `return`（弹窗停留在源选择、标题不变、无任何提示）。目录类在无 `pick_directory` 的壳上返回「当前壳不支持目录选择」（ui.py:988-990）。

### 2.3 第 2 步：预扫描与清单预览

`scanPreview()`（import-flow.js:242-258）：状态栏 `import.preScanning` → `import_scan(kind, sources)`（ui.py:999-1013；后端要求已开库、kind 合法、sources 非空）→ 成功则缓存 `_preview`（含 `preview` JSON 与 `markdown`）、`_conflicts = preview.conflicts`，标题改 `import.previewTitle`，调 `renderPreview()`，并**解禁**确认导入 / 复制报告。失败 → 状态栏 `res.message || import.preScanFailed`，弹窗留在源选择态。

`renderPreview()`（import-flow.js:260-355）自上而下：

| 区块 | 证据 | 内容 |
|---|---|---|
| 摘要 | import-flow.js:271-283 | `.-import-scan-summary` + `-stat-ok`，文案 `import.pvSummary`：新建 / 覆盖 / 重命名 / 跳过 / 无变更 / 新增 KP / 冲突（字段取自 `preview.summary`） |
| 操作行 | import-flow.js:286-292 | 「复制反馈(JSON)」`data-feedback="json"`、「复制反馈(Markdown)」`data-feedback="md"`；**仅在有冲突时**追加「应用到全部」`data-apply-all="1"`（`.btn-bar--start`） |
| 冲突区 | import-flow.js:295-319 | 标题 `import.secConflicts`；每项 `.-import-conflict-item[data-cidx][data-kind]`：头行 = `import.confKindFile`「文件」或 `confKindKp`「KP」+ `c.subject` + `c.detail`；决策为 `<select data-cselect>`，选项取 `c.options`（缺省 `["skip","overwrite","rename"]`，文案 `import.skip/overwrite/rename`）；选 `rename` 时并排显示 `<input.-import-rename-input data-crename>`（占位 `import.newRelPh` / `import.newIdPh`） |
| 文件清单 | import-flow.js:322-329 | 标题 `import.secFiles (N)`；每条 `<code>rel_path</code>` + `import.act_<action>`（`new/overwrite/rename/skip/unchanged`）+ 该文件的 `kp_ids` |
| KP 清单 | import-flow.js:332-339 | 标题 `import.secKp (N)`；每条 `<code>id</code>` + name + `· source`；`range===null && source!=="plain"` 追加 `import.rangePending`；空列表显示 `import.noKp` |
| Markdown 回显 | import-flow.js:342-344 | 只读 `textarea#import-conflict-report-text`，初值 `_preview.markdown`（同时是复制反馈的落点） |

`toggleRenameInput()`（import-flow.js:357-361）负责 select 值与重命名输入的显隐联动。**「应用到全部」**（import-flow.js:363-386）用 **`window.prompt`** 收集动作，须归一化命中 `skip|overwrite|rename`（否则状态栏 `import.applyAllInvalid`），命中则写回所有 select；`rename` 时按 `c.subject` 预填 `<base>-2.md`（文件）或 `<base>-2`（KP）并展开重命名输入。

### 2.4 第 3 步：执行与结果页

| 项 | 证据 | 说明 |
|---|---|---|
| 决策收集 | import-flow.js:413-430 | 以 `c.subject`（rel_path 或 kp_id）为键：普通动作取 select 值；`rename` 取重命名输入值（空则回退 `c.subject`），编码为 `"rename:<新名>"` |
| 执行 | import-flow.js:432-446 | 状态栏 `import.running` → `import_execute(kind, sources, decisions)`（ui.py:1015-1053；后端只接受 `skip` / `overwrite` / `rename:`，否则整单报错）；失败 → 状态栏 `import.failed`，**预览弹窗不关**（可改决策后重试） |
| 成功收尾 | import-flow.js:442-445、448-466 | 关预览弹窗并 `_resetState()` → `afterImportRefresh`：`refreshFiles` → `loadLinkTargets` → `loadGraphData` → `refreshKbPendingSummary` → 若有当前文件则 `openFile(skipNav)` → 状态栏 `import.doneTitle` + `import.doneStats`「{files} 文件 · {kp} KP」 |
| 结果页 | import-flow.js:470-504 | 标题行按 `errors.length` 取 `import.resultPartial`（`-stat-error`）或 `import.resultOk`（`-stat-ok`）；统计 `import.resultStats2`（新建/无变更/覆盖/重命名/跳过/sidecar/导入 KP）与 `import.resultStatsKp`（KP 新增/覆盖/重命名/跳过）；有错误则 `import.errorsLabel` + `<ul>` 逐条 |
| 关闭路径 | import-flow.js:506-513、521-528 | 预览弹窗：X /「取消」/ backdrop / 成功后自动关；结果弹窗：X /「确定」/ backdrop |
| 幂等与重复导入 | import-spec.md:91-95；import-flow.js:479-484 | 以内容指纹判定：同路径同指纹计入 `files_unchanged`（「无变更」），不产生重复；结果页分列 `files_written` / `files_unchanged` / `files_overwritten` |
| 对既有内容的影响 | import-flow.js:484；ui.py:1044 | 显式给出 `sidecars_written`（会创建/更新 sidecar）；`afterImportRefresh` 重载图谱数据（`loadGraphData`，app.js:1051-1075）以反映新增边 |

### 2.5 提示词与格式说明视图（同一弹窗内的辅助页）

- **Agent 整理提示词**（import-flow.js:133-180）：`get_agent_prompt("zh-CN")`（ui.py:1055-1070，读 `resources/agent-prompts/organize.zh-CN.md`）→ 标题 `import.promptTitle`；4 条用法列表 + 只读 textarea（rows=16）+「复制提示词」+「查看格式说明（Markdown 支持）」。
- **格式说明**（import-flow.js:184-225）：`get_reference_doc("preview-formats.md")`（ui.py:1108-1140，白名单；开发态读 `docs/reference/preview-formats.md`，发布态读 `resources/docs/`）→ 标题 `import.formatDocTitle`；来源行 `import.formatDocSource` + 只读 textarea（rows=20）+「复制格式说明」+「返回提示词」。
- **复制反馈**（import-flow.js:227-238、390-409）：来源为 prompt / json（`JSON.stringify(_preview.preview, null, 2)`）/ markdown；优先 `navigator.clipboard.writeText`，随后把文本写入 `#import-conflict-report-text`（存在时）；成功与失败都只报 `import.copyDone`（见 §5.3）。

### 2.6 导出（当前为占位，未实现）

`#file-menu-export` 带 **`disabled`**（index.html:51），标签 `toolbar.export`「导出」、title `toolbar.exportTitle`「导出知识库（预留，待后续版本）」（zh-CN.js:510-511），**无任何 JS 处理器**（全前端只有 i18n 定义）。设计稿见 [../../design/export-plan.md](../../design/export-plan.md)：目标形态为知识库包（bundle）导出（`kb_bundle` 的逆过程），本期不含静态 HTML / PDF / 合并导出，状态「草稿（待评审）」。

### 2.7 检查入口与「检查」弹窗

| 元素 | 证据 | 说明 |
|---|---|---|
| 顶栏按钮 + 角标 | index.html:64-67 | `#btn-check` 与 `#btn-check-badge`；角标在 `.-toolbar-btn-wrap`（`position:relative`）内绝对定位到按钮右下（`translate(calc(55% - 3px), calc(42% - 3px))`，app.css:1785），`pointer-events:none` |
| 打开弹窗 | kb-check.js:642、622-633 | 未开库给错误样式提示 `app.openKbFirst`（底栏转红 + 浮层）；否则先显示弹窗并用**缓存报告**渲染（`state.kbValidateReport`），随后以 `silent:true` 跑一次刷新 |
| 弹窗骨架 | index.html:268-283；app.css:456-463 | `.-modal-box.-modal-check`（宽 `min(720px,94vw)`、max-height 82vh、min-height 22.5rem）；正文 `#check-body.-check-body` 可滚动；标题 `check.modalTitle` |
| 底部按钮 | index.html:276-281 | 「重新检查」`#check-rerun`（`check.rerun`）、「复制报告」`#check-copy`（`check.copy`）、spacer、「关闭」`#check-dismiss`（`common.close`）；右上 X `#check-close` |

**弹窗正文**（`renderCheckModalBody`，kb-check.js:308-497）：

| 区块 | 条件 | 证据 |
|---|---|---|
| 统计行 | 恒有 | kb-check.js:321-325：`check.summaryChecked{files}` + `check.word.error(s)` / `check.word.warning(s)`，非零数字着色（`-stat-error` / `-stat-warn`） |
| 全库 | `kb_integrity` 有 error/warning | kb-check.js:336-348，标题 `check.section.kb`；路径多值以 ` · ` 连接 |
| 路径变更 | `path_moves` 非空 | kb-check.js:350-370，标题 `check.section.pathMoves` +「修复路径」`#check-repair-paths`（`check.repairBtn`）+ 说明 `check.note.pathMovesRepair`；每条 `from → to`，hint 取 `check.pathmove.match`（`md_sha256`）或 `check.pathmove.drift`（`sidecar_drift`） |
| 文件清单 | manifest 有问题，或 `path_moves` 为空 | kb-check.js:372-394，标题 `check.section.manifest`；仅在「有 manifest 问题且无路径变更」时给「更新文件清单」`#check-sync-manifest`（`check.syncManifestBtn`，避免与路径修复冲突）；无问题时显示 `check.note.manifestBaseline` / `manifestConsistent` |
| 各文件问题 | `vr.files[]` | kb-check.js:396-405，每文件一个 `-check-section`（标题为该文件路径），先 errors 后 warnings |
| 图谱建边 | `graph_audit.files[]` 中有 issues | kb-check.js:407-418，标题 `check.section.graphEdges` |
| 空结果态 | 以上全空 | kb-check.js:420-428，`check.noProblems`「未发现配置或图谱问题。」；报告对象缺失时渲染 `check.empty`「暂无检查结果」（kb-check.js:311-314） |

**条目结构**（`checkItemHtml`，kb-check.js:281-306）：`.-check-item.-check-item--{error|warning}` > 徽标 `.-check-badge--error|--warning`（`check.badge.error|warning`）+ 主列（本地化消息 `localizeCheckIssue` + 可选路径 `.-check-item-path`）+「打开」按钮 `.-check-open-btn[data-check-open][data-check-kp][data-check-line][data-check-kind]`（`check.open`）。

**条目跳转**（kb-check.js:478-496）：点击「打开」→ `closeCheckModal()` → `openFile(path, { kpId, errorHighlight:{kind, kpId, line} })`；`errorHighlight` 在 `openFile` 内优先于普通 `kpId` / `lineHint`，按「链接问题 → 高亮该行 / KP 问题 → 高亮 KP 范围并标红左栏 KP 项 / 行号 → 单行高亮」三支处理（app.js:1463-1483）。

**两个修复动作**：

- 「修复路径」（kb-check.js:444-476）：先 `window.confirm(check.confirm.repair)`；确认后状态栏 `check.status.repairing` → `repair_path_cascade(true)`；成功/部分成功 → 状态栏 `check.status.pathRepaired` + `check.status.repairedStats{done}/{total}`，重映射已开标签（`remapOpenTabsAfterPathRepair`）、按需重开当前文件、`refreshFiles` + `loadGraphData`，最后重跑检查；失败 → `check.status.repairFailed`。
- 「更新文件清单」（kb-check.js:430-442）：状态栏 `check.status.syncStart` → `sync_manifest` → 成功 `check.status.manifestUpdated` + `check.countDocs` 并自动重跑检查；失败 → `check.status.syncFailed`（若返回 `blocked` 且带 `path_moves`，仍重跑检查，让用户先修路径）。

**重新检查**：`#check-rerun` → `runKbValidate({silent:false})`（kb-check.js:646），走**同步** RPC `validate_kb`（ui.py:385-388），与静默路径的异步作业不同（§2.9）。

**复制报告**（kb-check.js:499-620）：文本由 `buildCheckReportText()` 生成——`# 知识库检查报告` + 知识库路径 + `check.report.time`（`toLocaleString()`）+ `check.report.statLine`，再按 `## 全库` / `## 路径变更` / `## 文件清单` / `### <文件>` / `## 图谱建边` 分节，条目为 `- [错误|警告] <code> <本地化消息>`，有详情追加 `  → <详情>`，全空则追加 `check.noProblems`。写剪贴板 `writeClipboard()` 先试 `navigator.clipboard.writeText`，**reject 时回退** `document.execCommand("copy")`（临时 off-screen textarea）；成功 → 状态栏 `check.copyDone` **且**绿色 flash 卡片，失败 → `setStatusError(check.copyFailed)`（底栏转红 + 红色卡片）；无缓存报告 → 状态栏 `check.empty`。语言切换后由 `MemoriaI18n.addRefresh` 重绘角标 / 状态栏统计 / 已打开的弹窗（kb-check.js:656-665）。

### 2.8 检查角标与状态栏统计

| 项 | 证据 | 说明 |
|---|---|---|
| 角标数值与配色 | kb-check.js:113-139；app.css:1792-1799 | `total = errors + warnings`；`total<=0` → 清空文本 + `.hidden` + `aria-hidden="true"` + 清 title；否则文本为 `total`（**>99 显示 `99+`**）；有 error → `.-toolbar-badge--error`（红 `#da3633`）+ title `check.badge.tooltipErrors/tooltipMixed`，仅 warning → `--warn`（`#9e6a03`）+ `tooltipWarnings` |
| 刷新时机 | kb-check.js:141-145、248-260、187-195 | `applyCheckIndicators()` 同时刷角标与状态栏；同步、异步（`applyAsyncValidateReport`）、语言切换三条路径共用 |
| 状态栏「检查统计」块 | kb-check.js:94-107；app.js:289-303 | 有 error/warn 时以 `check.stat.head`「检查」+ 着色 `check.stat.errors/warnings.{one,many}` 拼块，并给 `#status-stats` 打 `data-kb-check="1"`；无问题且报告 `status==="ok"` 且当前无文件统计时显示 `check.stat.pass`「检查通过」；`graph_audit.summary.warn_count` > 0 时追加 `check.stat.graphTodo` |
| 状态栏点击与复位 | app.js:12219-12227；kb-check.js:673 | 点击：有 `data-kb-check` → `openCheckModal()`，否则有 `data-graph-audit-goto` → 跳到首个图谱审计问题；关库时 `resetIndicators()` = `updateCheckButtonBadge(null)` → 角标隐藏 |

### 2.9 静默后台检查（间隔 / 开关 / 作业轮询）

设置项在「设置 → 检查」页（graph-settings.js:772、803-807；check-settings.js:160-183）：

| 项 | 选项 / 默认 | 作用 | 证据 |
|---|---|---|---|
| 「检查间隔」`silentCheckIntervalSec` | `[0, 30, 60, 120, 300, 600]` 秒，**默认 120** | 背景检查周期；文案 `check.settings.off/seconds/minutes` | check-settings.js:8、12、154-158、171-174 |
| 「启用静默检查」`silentCheckEnabled` | **默认 true** | 间隔为 0 时该项 `disabled` 且强制 false；说明见 `check.settings.noteMain/noteOff` | check-settings.js:11、53-55、90-94、170-179 |

执行链：

1. 开库后 `initKb()` 先跑一次**同步**完整检查，再 `startKbSilentCheck()`（app.js:472-473）；关库时 `closeKb()` 调 `stopKbSilentCheck()`（kb-check.js:242-244）。
2. `MemoriaCheckSettings.startSilentCheck(runFn)` → `setInterval(runFn, getIntervalMs())`（check-settings.js:134-142）；间隔为 0 或未启用则不起定时器（check-settings.js:111-115）。
3. 每次触发 → `scheduleSilentValidate()`：向 `MemoriaScheduler` 入队 `kb_check`（`key="kb:"+kbPath`、`priority:3`、`replace:true`、`dropStale:true`、`gen=epoch()`）；**忙时跳过**（`__memoriaHasPendingEdits()` = 脏 / 待保存 / 待渲染，app.js:167）并 `S.note()` 记录（kb-check.js:155-179）。
4. 真正执行时调 `submitAsyncValidate()`（kb-check.js:198-240）：`validate_kb_async`（ui.py:392-399，提交线程池）→ 每 **400ms** 轮询 `job_status`，超时 **120s**；`done` → 应用报告（同角标/状态栏/弹窗逻辑，`silent:true` 时不写状态栏正文，kb-check.js:248-260）；`error` → note；`superseded` → 记录「已被新作业顶替」；轮询期间关库则丢弃结果。

### 2.10 后台作业的前端可观测性

| 项 | 证据 | 说明 |
|---|---|---|
| `[job]` 控制台日志 | scheduler.js:83-95、136-220 | 所有调度事件经 `console.log("[job] " + msg)`；含「入队 <kind:key> #id prio=N queue=M」「合并(顶替)/(忽略新)」「执行」「陈旧丢弃 (gen a < b)」「失败」；计数器 `scheduled/executed/merged/dropped/queue_max`（scheduler.js:242-253） |
| 检查作业日志文本 | kb-check.js:167、173、204、208、211、226、230、235、239 | 「丢弃（已无打开的知识库）」「跳过（编辑/待保存未收敛，等下轮）」「已提交后台作业 #id」「完成（后台作业 #id，Nms）」「已被新作业顶替（合并）」「轮询超时（作业仍在后台执行）」等 |
| 可选落盘追踪 | scheduler.js:43-81、97-99 | 置 `window.__jobTrace = true` 时日志以 200ms 批量写 `logs/job-trace.log`（经 `write_debug_log`），`beforeunload` 前 flush |
| 后端作业状态机与观测接口 | executor.py:24-28、44-68、97-144；ui.py:392-412 | `queued → running → done\|error`，同 `kind+key` 的 queued 作业被顶替为 `superseded`；`status()` 返回 `elapsed_ms`，`done` 带 `result`、`error` 带 `error`；接口 `validate_kb_async` / `job_status` / `jobs_snapshot` |
| 用户可见反馈 | — | **前端不发浮层提示、不显示进度条**；排队/完成/跳过只在控制台与状态栏（角标 + 统计块）体现 |

### 2.11 「刷新」与「构建」

| 按钮 | 证据 | 行为 | 执行中表现 |
|---|---|---|---|
| 刷新 `#btn-refresh` | index.html:62；app.js:12192-12197 | 依次 `refreshFiles` → `loadLinkTargets` → `loadGraphData` → 若有当前文件则 `openFile(skipNav)`。**不跑检查、不改磁盘配置** | 无禁用、无状态栏提示、无进度 |
| 构建 `#btn-build` | index.html:63；app.js:1012-1049 | `build_kb`（同步链接配置并生成图谱）→ `refreshFiles` / `loadLinkTargets` / `loadGraphData` / 重开当前文件 | 执行期间按钮 `disabled`（app.js:1018、1047）；状态栏 `graph.build.building`「构建中…」+ `buildingDetail`；完成 `graph.build.done` + `doneDetail{msg,n}`，有 `warn_count` 时再拼 `doneKinds`（按 `audit.by_kind` 汇总）；未开库仅状态栏提示、按钮不置灰（app.js:1013-1016） |

## 3. 交互流程

**3.1 导入**：「文件」→「导入」→ 源选择（4 卡之一）→ 系统文件/目录选择器 → `import_scan` 预览（摘要 / 冲突 / 文件清单 / KP 清单）→ 逐项或「应用到全部」选 `skip|overwrite|rename` →「确认导入」→ `import_execute` → 关预览弹窗 → 刷新文件树/链接目标/图谱/待确认摘要并重开当前文件 → 结果弹窗（统计 + 错误）→「确定」。任一步的错误只写状态栏，弹窗保留决策现场以便重试。

**3.2 提示词**：源选择页第 4 张卡 → 载入 `resources/agent-prompts/organize.zh-CN.md` → 复制发给外部 Agent → 外部 Agent 产出平面文件 → 回到第 1 张卡继续导入。

**3.3 检查**：点「检查」→ 弹窗立即用缓存渲染 + 后台静默重跑（异步作业、完成即刷新弹窗）→ 需要时点条目「打开」跳到文件 / 行 / KP → 或「修复路径」/「更新文件清单」→ 或「复制报告」离线排查 →「关闭」。「重新检查」走同步 RPC 立即刷新。

**3.4 静默检查**：开库跑一次完整检查 → 每 `silentCheckIntervalSec`（默认 120s）入队一次 `kb_check` → 空闲时执行 → 提交线程池作业并轮询 → 完成则静默更新角标与状态栏。用户在设置页改间隔或开关时，`MemoriaCheckSettings.notifyChange()` 重启定时器，`kb-check.js` 的 `onChange` 在已开库时再 `startKbSilentCheck()` 一次（kb-check.js:650-654）。

## 4. i18n key 前缀

| 前缀 | 覆盖 | 代表键（zh-CN.js 行号） |
|---|---|---|
| `import.*` | 向导全部阶段：源卡、提示词、格式说明、预览、冲突、动作、结果 | `conflictTitle/resultTitle/copyReport/confirmImport/preScanning/preScanFailed/failed/running/doneTitle/doneStats/chooseTitle/kindFlat…/picking/promptTitle/formatDocTitle/previewTitle/pvSummary/copyJson/copyMarkdown/applyAll/applyAllPh/applyAllInvalid/secConflicts/confKindFile/secFiles/secKp/rangePending/noKp/act_*/resultPartial/resultOk/resultStats2/resultStatsKp/errorsLabel/skip/overwrite/rename/copyDone`（791-858） |
| `check.*` | 弹窗、分节、条目、角标、状态栏统计、静默检查设置 | `modalTitle/rerun/copy/copyDone/copyFailed/report.*/badge.*/open/empty/noProblems/summaryChecked/word.*/stat.*/section.*/repairBtn/syncManifestBtn/note.*/pathmove.*/confirm.repair/status.*/countDocs/settings.*`（667-756） |
| `toolbar.*` | 文件菜单项与顶栏按钮 | `toolbar.file/open/import/export/exportTitle/refresh/refreshTitle/build/buildTitle/check/checkTitle/settings`（496-526） |
| `graph.build.*` | 构建状态文案 | `graph.build.building/buildingDetail/done/doneDetail/doneKinds/failed`（917-923） |
| `settings.tab.*` | 设置页签 | `settings.tab.search`「检索」、`settings.tab.check`「检查」（642-649） |

## 5. 边界与已知坑

1. **导入入口被绑定了两次**：`#file-menu-import` 在 app.js:12109-12112 与 import-flow.js:518 各绑一次 `start()`；因 `bindEvents()` 先于 `MemoriaImportFlow.init()` 执行（app.js:12677-12678），点一次「导入」会连跑两遍 `start()`（两次 `_resetState()` + `renderKindChooser()`）。当前 `start()` 无 RPC，仅表现为重复渲染；若将来在其中加 RPC 会被调两次。
2. **源卡是 4 张不是 3 张**：第 4 张「Agent 整理提示词」不是导入源（import-flow.js:87、109-111）。
3. **复制反馈无失败分支**：`catch(() => done())` 与「无 clipboard API 直接 `done()`」都会报 `import.copyDone`（import-flow.js:401-406；`copyRawText` 同 227-238），即**失败也提示已复制**；且未像检查报告那样回退 `execCommand`（对比 kb-check.js:577-602）。
4. **「应用到全部」用原生 `window.prompt`**（import-flow.js:366）：依赖宿主 webview 支持提示框，返回值还需手工归一化（非法输入才提示 `import.applyAllInvalid`）。
5. **结果页没有「打开新文件」链接**：import-spec.md:152 描述「结果报告（… + 打开新文件链接）」，实现只有统计与错误列表（import-flow.js:470-504），也没有复制按钮（复制反馈只存在于预览阶段）。
6. **导入后不自动构建图谱**：`afterImportRefresh()` 只 `loadGraphData()` 重读数据（import-flow.js:452），不调 `build_kb`；与 import-spec.md:152「建议构建图谱以同步链接边」一致——需手动点「构建」。
7. **取消与失败都不回退阶段**：用户取消文件选择（`sources` 为空）静默 `return`（import-flow.js:122）；`import_scan` 失败时弹窗仍显示源选择卡、错误只在状态栏（import-flow.js:247-250）。
8. **`import.*` 有 4 个未被引用的键**：`scanSummary`（847）、`conflictCount`（848）、`sourceLine`（849）、`resultStats`（856）在 `js/**` 检不到调用点，属旧版对话框遗留。
9. **`#btn-import` 兼容绑定指向不存在的节点**：index.html 无 `#btn-import`，import-flow.js:520 的绑定永远空转。
10. **「重新检查」是同步阻塞**：`#check-rerun` 走 `validate_kb`（同步 RPC），大库会卡住界面；且执行期间按钮**不置灰**，存在重复点击并发风险。静默路径才用 `validate_kb_async` + 轮询（kb-check.js:646 vs 198-240）。
11. **静默检查会被导航「陈旧丢弃」**：入队时记 `gen=epoch()` 且 `dropStale:true`（kb-check.js:158-164），而 `openFile()` 每次切换文件都 `bumpEpoch()`（app.js:1384）。若「入队后、执行前」用户切换了文件，该轮后台检查被丢弃，只能等下一个间隔周期——频繁浏览时静默检查可能长期不落地。
12. **静默检查无 UI 反馈**：排队 / 跳过 / 完成 / 顶替只进控制台 `[job]` 与可选 `logs/job-trace.log`（§2.10）；用户侧只能看到角标与状态栏随之变化。
13. **角标截断到 `99+`** 但 title 仍显示真实 `{err}/{warn}`（kb-check.js:127-138）。
14. **角标挂在按钮包装层上**：`.toolbar-btn-wrap` 为 `position:relative`、角标 `translate(calc(55% - 3px), calc(42% - 3px))`（app.css:1785），故角标**溢出按钮右下角**而非贴合内角；`pointer-events:none` 保证不吞点击。
15. **弹窗层级**：`#import-*` / `#check-modal` 与所有 `.-modal` 同为 `z-index:1000`（app.css:4218），低于搜索面板 9000、右键菜单 10050、flash 浮层 12000；也没有「只许一个弹窗」的中央约束（见 01 篇 §2.8）。
16. **检查条目路径多值时只打开第一段**：`paths.length > 1` 时以 ` · ` 拼接展示，但 `data-check-open` 取首个 path（kb-check.js:340-345），点「打开」只会打开第一个文件。

## 6. 代码锚点表

| 要点 | 锚点 |
|---|---|
| 导入 / 结果 / 检查弹窗 HTML | index.html:322-337、339-352、268-283 |
| 文件菜单项（导入 / 导出占位） | index.html:46-60 |
| 导入入口与两次绑定 | app.js:12109-12112；import-flow.js:518-520 |
| 源卡渲染与选择 | import-flow.js:80-131 |
| 预扫描与预览渲染 | import-flow.js:242-355 |
| 重命名联动 / 应用到全部 / 决策收集 | import-flow.js:357-386、413-430 |
| 执行、刷新、结果页、关闭 | import-flow.js:432-513、521-528 |
| 提示词与格式说明视图 / 复制反馈 | import-flow.js:133-238、390-409 |
| 导入后端 API | ui.py:967-997、999-1013、1015-1053、1055-1070、1108-1140 |
| 导入向导 CSS | app.css:172-211、4207-4324 |
| 导入契约（格式 / 幂等 / 冲突 / 预览字段 / UI 流程） | ../import-spec.md:51-170 |
| 导出设计（未实现） | ../../design/export-plan.md；zh-CN.js:510-511 |
| 检查按钮与角标 | index.html:64-67；app.css:1756-1799；kb-check.js:113-145 |
| 检查弹窗渲染与条目 | kb-check.js:281-306、308-497 |
| 检查条目跳转 | kb-check.js:478-496；app.js:1463-1483 |
| 修复路径 / 更新文件清单 | kb-check.js:430-476 |
| 复制报告（文本 / 剪贴板 / flash 卡片） | kb-check.js:499-620 |
| 打开 / 关闭 / 重新检查 / 语言刷新 | kb-check.js:622-666 |
| 静默检查调度与作业轮询 | kb-check.js:147-244；check-settings.js:111-146 |
| 检查设置页 | check-settings.js:8-13、44-57、154-183、203-223；graph-settings.js:772、803-807 |
| 状态栏统计与点击 | app.js:281-333、12219-12227；kb-check.js:94-107 |
| 前端调度器与 `[job]` 日志 | scheduler.js:43-99、122-225、242-253 |
| 后端执行器状态机 | executor.py:24-28、44-68、97-144；ui.py:392-412 |
| 刷新 / 构建 | app.js:12192-12197、1012-1049；zh-CN.js:917-923 |
| 开库即检查 + 启动静默检查 | app.js:468-473 |

## 7. 未证实 / 待确认

- ⚠️ 待确认（未能取证）：`window.prompt` 在 pywebview / WebView2 宿主下是否可用（若被屏蔽，「应用到全部」将无反应，仅返回空串而报 `import.applyAllInvalid`）。未在真机验证。
- ⚠️ 待确认（未能取证）：导入结果页是否另有「打开新文件」入口（状态栏或文件树高亮）——未在 `js/**` 检到，但与 import-spec.md:152 的描述不一致，留待复核。
- ⚠️ 待确认（未能取证）：`import.*` 的 4 个遗留键（§5.8）是否仍被旧版动态弹窗（`pre_scan_import` / `execute_import` 兼容分支，ui.py:895-963）使用——该分支在 `index.html` 找不到对应容器。
- ⚠️ 待确认（未能取证）：`validate_kb` 同步 RPC 在大库上的实际阻塞时长未实测；「重新检查」重复点击是否真的并发未验证（§5.10）。
- ⚠️ 待确认（未能取证）：静默检查「陈旧丢弃」在真实使用中的发生频率（§5.11 由 `gen` / `dropStale` / `bumpEpoch` 三点推断，未做运行时观测）。
- ⚠️ 待确认（未能取证）：改间隔时定时器被重启两次（`check-settings.js` 的 `notifyChange()` → `restartSilentCheck()`，同时 `onChangeHandler` → `kb-check.js startKbSilentCheck()`），是否导致首轮检查被推迟/重复触发未验证。
- ⚠️ 待确认（未能取证）：`jobs_snapshot`（ui.py:407-412）在前端未检到调用点，是否仅供外部 harness 使用未确认。
