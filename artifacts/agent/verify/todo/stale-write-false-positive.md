# task-164 — 无外部写者时的 `stale_write`「文件已被改动」误报：根因与修复

> 基线：**HEAD `9eb0a23b`**（开工时 `git status -- src/memoria/ui/static/app/js/app.js` 干净；本轮只改 app.js + tests + 本目录，未 revert 任何人改动）。
> ⚠️ **工作区现状披露**：app.js 当前还包含 **sync-mapper 的未提交改动**（链接面板 resize，`_linkPanelResizeTo` 等 hunk）——那是别人在飞的工作，我**原样保留**未动。我的改动 = `syncToDisk/_syncToDiskOnce/_saveInFlight/_noteWrittenVersion/_wasWrittenByUs` + guard force 分支 + aria 注释。
> ⚠️ **临时回滚窗口披露**：为做“修复前 vs 修复后”同脚本对照，我先 `git checkout -- app.js` 跑了一次 pre-fix 验证（约 90s），再用**回滚前保存的工作区快照**恢复。快照包含 sync-mapper 当时已存在的未提交改动并已恢复；但若 sync-mapper 恰在这 90s 内向 app.js 写入新内容，可能未包含在该快照中 —— **请 Lead 让 sync-mapper 核对其最新改动是否完整**（当前 diff 中其 link-panel-resize hunk 可见）。
> 证据目录：`artifacts/agent/verify/todo/stale-write-false-positive/`
> · `stale_repro.py` / `stale-repro.json`（定位探针）
> · `stale_verify.py`（两向验证，同一脚本跑修复前/后）
> · `stale-verify-before.json`（修复前）/ `stale-verify-after.json`（修复后）

---

## 1. 结论（先说根因）

**不是「正常保存成功后没写回 version」**——那条路径确实写回：
`app.js#L408` 传 `state.doc?.version`，`#L412` 成功后 `state.doc.version = res.version`（修复前代码）。
实测连续 13 次正常保存，版本链 13/13 自洽（每次 base_version == 上次响应 version == 盘上 sha；见 `stale-repro.json` 的 save 日志）。

**真因是「version 写回没有归属校验」**：
```
保存 A 的请求在飞
  → 用户/程序切到文件 B（openFile(B) 完成，state.doc = B，state.doc.version = B 的版本）
  → A 的 save 响应回来
  → 旧代码：#L412 无条件执行 state.doc.version = A 的新 version
  ⇒ B 的 state.doc.version 被替换成 A 的 sha
  → 下一次保存 B：base_version = A 的 sha ≠ 盘上 B 的 sha
  ⇒ 后端 guard_save 返回 stale_write ⇒ 弹「文件已被改动」三选一
```
**此时没有任何外部写者**（B 盘上内容一直是 B 自己上一次保存的版本）——正是人报的误报。
用户 KB 的审计还显示它**反复发生**：`教材/03_第3章…md` 在 16:31:58 / 16:33:46 / 16:33:53 连续 3 次 `manual-force`（人三次点「以我为准」），与“版本反复被污染 → 每次保存都误报”的形态一致（`<用户KB>/.memoria/agent/sessions/manual-force.jsonl`）。

> 说明：人描述“编辑行首（数字）”是**触发时刻的表象**（该操作前后伴随切文件/切视图等会 openFile 的动作）；根因与点击位置无关。可迁移的判据是：**只要保存进行中发生了文档切换，旧版本就可能写进新文档**。

---

## 2. 逐次对照表（修复前，真机、真文件）

**2.1 正常连续保存（无切换）：13/13 一致** —— `stale-repro.json`

| # | base_version（请求） | 后端响应 version | 保存后盘上 sha | 之前是否已有我方成功保存 |
|---|---|---|---|---|
| 1..13 | 每次 == 上一次响应的 version（如 `7d5808d3→8e88219e→40c87c7d→…`） | 同左 | == 响应 version | 是（第 2 次起） |

⇒ 排除候选 (a) 的“完全没写回”形态；(c)/(e) 也无失配（body 与 version 同源，见 §3）。

**2.2 复现误报（跨文件切换发生在 A 的自动保存进行中，无外部写者）** —— `stale-verify-before.json`

| 事件 | base_version | 后端当前盘上 sha | 结果 |
|---|---|---|---|
| A（教材/03）保存响应 | `02ef51da…` | 写后 `3f6694b1…`（A 新版本） | ok；**此时 state.doc 已切到 README**，旧代码把 `3f6694b1` 写进 README 的 version |
| 切到 README 后检查 | README `state.doc.version = 2e19476e…`（A 的版本） | README 盘上 `825f9a4f…` | **versionMatchesDisk = false**（污染成立） |
| README 下一次保存 | base_version `2e19476e…`（A 的） | README 盘上 `825f9a4f…` | **stale_write + 弹出「文件已被改动」（README）** |
| 后续 5+1 轮编辑保存 | — | 盘上不再变化 | 全部 stale，误报循环（与人 3 次 force save 形态一致） |

⇒ 分歧起点 = **A 的保存响应到达时 state.doc 已不是 A** 的那一次；该次之前有我方成功保存，但问题不是“未更新”，而是“更新给了错的文件”。

---

## 3. 候选根因逐条排除

| 候选 | 判定 | 证据 |
|---|---|---|
| (a) 保存成功没把 version 写回 | **被 diff 与实测证伪** | 修复前 `#L408/#L412` 确实有 `state.doc.version = res.version`；13 连保存链 13/13 自洽（每次 base == 上次响应 version == 盘上 sha）。假设 (a) 不成立 |
| (b) 自动保存并发（两次 save 在飞）自我撞车 | 风险存在但**不是本次真因**；本轮已用串行化消除 | 真机连续打字 12 批：同一时刻 in-flight 始终 ≤1（防抖 1500ms + save 60–90ms）；直接并发同 base 调后端可控但**无法自然复现**用户形态 |
| (c) 发送 body 与 base_version 口径不一致 | 排除 | body 来自 `collectEditorBody()`，version 来自 `load_document`/上次 save；13 次保存后 base 与盘上 sha 逐次相等；task-147 尾换行逻辑不参与 version 计算 |
| (d) 行号区点击触发额外写盘 | 排除 | 真机“点行号区→编辑→保存”6/6 全部 ok、version==disk；gutter 无独立写盘路径（无监听） |
| (e) 后端 version 计算口径 ≠ 校验口径 | 排除 | `file_version.py#L27-L37` 同一 `file_version()` 同时用于 `load_document` 的 version 与 `guard_save` 的比对（sha256 原始字节）；实测每次 base == 上次写后 sha |
| **(f) 保存响应的 version 未校验文档归属**（真因；与 (b) 同为“时序类”，但不是并发 save） | **确认** | §2.2 + 修复前 `stale-verify-before.json`：A 的**单次** save 响应在切换文件后把 A 的 version 写进 B；修复后同脚本 `stale-verify-after.json` 不再复现 |

---

## 4. 修复（`src/memoria/ui/static/app/js/app.js`）

三条不变量（都不放松后端 sha 判据，真报仍由后端 + 对话框兜底）：

1. **归属校验（真因修复）**：`syncToDisk` 保存前快照 `savePath/saveDoc`；响应回来后**仅当 `state.currentPath === savePath && state.doc === saveDoc`** 才回写 `state.doc.version`。旧的无条件写法删除。
2. **串行化**：`syncToDisk` 外层包一层 `_saveInFlight`；同一时刻最多一个 `save_document` 在飞，后到者等前一个完成、若仍 dirty 再用**最新** version 保存（避免自我撞车）。
3. **自伤 stale 自愈**：模块内登记“我方写出的 version”（`_noteWrittenVersion`，每个 path 最近 20 个）。若 stale 响应的 `current_version` 属于该集合 ⇒ 盘上那一版就是**我们自己**写的，不是外部写者 ⇒ 校正 version 并自动重试（上限 2 次），不弹框。
   - **真报不丢**：外部写者的内容 sha 不会出现在我方集合里 ⇒ 仍走 `onSaveFailed → showConflictDialog`（真机实测见 §5）。
   - 强制保存（「以我为准」）分支同步：只写回所属文档（`st.currentPath === path`）并登记 version。
4. 附带：`_silentRefreshKpPanel()` / `_previewCacheDrop()` 改用 `savePath`（不再受切换后的 `state.currentPath` 影响）。

`git diff --stat`：`src/memoria/ui/static/app/js/app.js | 186 +++++++++++---`（+166/−20，含注释与串行化/自愈块）；`tests/test_stale_write_version_ownership.py` 新增 4 条结构回归。

---

## 5. 两向真机验证（同一脚本 `stale_verify.py`，同 commit、同真文件）

| 项 | 修复前（`stale-verify-before.json`） | 修复后（`stale-verify-after.json`） |
|---|---|---|
| A. 保存中切文件 → B 的 version 是否等于盘上 | **false**（B 被写成 A 的 sha `2e19476e…`） | **true**（`825f9a4f…`） |
| A. 之后在 B 编辑保存 | **stale_write + 弹框（误报）** | **ok，无弹框** |
| B. 外部进程真改盘后保存（真报） | — | **stale_write ×1 + 弹出「文件已被改动」+ force 按钮存在** ✅ |
| C. 连续 5 次行首 + 1 次行号区点击编辑 | 6/6 version 与盘不符、盘上无写入 | **6/6 versionMatchesDisk=true**，无新增弹框 |
| 终态 | version ≠ 盘上 sha | **version == 盘上 sha** |

修复前/后差异**全部来自 app.js 改动**（同脚本、同真文件副本、同机 WebView2）。

---

## 6. 门禁

| 门禁 | 结果 |
|---|---|
| `pytest -q`（基线 1516） | **1520 passed / 0 failed**（107s；含新增 4 条结构回归；原 1516 基线全绿） |
| `node --check`（前端全部 js + app.js） | **0 fail** |
| `scripts/i18n_selftest.js` | **PASS，exit 0** |
| `scripts/agent/prompt_drift_check.py` | **FAIL=0，exit 0** |
| `scripts/agent/team_audit.py` | **FAIL=0**（80 条中 WARN 51/INFO 29，均既有） |
| 12 交互剧本 | **12/12，failed=0**（28.1s，`scripts/benchmark/surface/results/raw-interaction-t164-final_9eb0a23b.json`；runner 打印“剧本 12 个，失败 0 个”） |

### 6.1 因本次重构而更新的 2 个既有测试（守住意图，未削弱）

改动后旧断言押的是**旧实现字面量**，必须随实现更新；两条测试的**原意图都保留**：

| 测试 | 旧断言（旧字面量） | 新断言（新机制） | 守住的意图 |
|---|---|---|---|
| `tests/test_write_conflicts.py::test_frontend_wires_version_token_and_conflict_dialog` | `call("save_document", state.currentPath, body, state.doc?.version || "")`；`if (state.doc && res.version) ...`；`onSaveFailed(..., state.currentPath, ...)` | `call("save_document", savePath, body, saveDoc?.version || "")`；`state.currentPath === savePath && state.doc === saveDoc`；`onSaveFailed(..., savePath, ...)`；并显式断言旧的无条件回写**不存在** | **保存必须带 version token**、**stale_write 必须接三选一弹窗**、**apply 忙位让路**——三条意图全部原样保留，还多钉了“version 有归属”这条新契约 |
| `tests/test_display_preload.py::test_every_invalidation_trigger_is_wired` | `_previewCacheDrop(state.currentPath)`（写盘成功分支） | `_previewCacheDrop(savePath)` | **“写盘成功 ⇒ 该路径预览缓存作废”**（只把“哪条路径”从“当前文档”收紧为“本次保存的文档”，失效触发意图不变） |

### 6.2 建议（源码字面量断言的系统性风险，转架构侧）

- **风险模式**：`assert 'a; b; c' in js` 把「实现的一行连写」当成契约——合法的路径/变量重命名或加守卫都会红，测试从“保护行为”变成“冻结实现”。本次两个失败即此形态。
- **建议**：结构守卫断言 **最小可辨识片段**（断 `call("save_document"` + `saveDoc?.version` 两个独立片段，而不是整行）；或优先断**语义/行为**（如真机脚本产出的 JSON：version==disk、stale 次数、对话框是否出现），把字面量断言降为“辅助”。
- 本次已按“最小片段 + 新契约”改写，未删除任何原意图断言；长期建议架构侧评估把这类 JS 结构测试迁到真机/行为层，或统一改为片段级断言。

---

## 7. 诚实边界（unknowns / not_doing）

- **未复刻用户当时的精确点击序列**：用户被问到时只说“编辑行首（数字）”。我们复现的是**同一机制的触发形态**（保存进行中切文件）；用户 KB 的 3 次 force save 与误报循环与该机制一致，但“当时到底哪一步触发了 openFile”不可从现有日志唯一确定（`mapping-debug.log` 16:31:49–54 显示的是预览区 click→beforeinput，未包含文件切换日志）。
- **未改后端**：`file_version.py` / `guard_save` 一行未动，真冲突判据保持原样（不放松）。
- **未动 `docs/example/**`、`Package/**`**；未 commit。
- **不是“必现”**：修复前也需要“保存进行中切换文档”这一时序；修复后该时序不再污染。跨文件切换的其他路径（force 分支）已同规则覆盖；若还有其他“写盘但前端不知道新 version”的内部写者（如 `build_kb` / `fix_unregistered_image_refs`），仍可能造成**同形**误报——本轮未发现用户场景涉及，登记为 unknown，未扩大改动面。
