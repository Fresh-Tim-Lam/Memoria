# Memoria v0.4.10

> 55 commits since v0.4.9: the knowledge graph becomes readable, the app can check for and download updates, and eleven issues you reported are fixed — including two more silent-write data-corruption paths.

## English

### Why upgrade

Three things make this update worth installing:

1. **The knowledge graph finally looks like the knowledge it represents.** Node size now varies continuously with how connected a note is, the layout is deterministic (it stops jumping every time you open the graph), and labels no longer pile into an unreadable soup.
2. **The app can now check for updates and download the installer package for you** — with your explicit action, never automatically replacing anything. This was the last gate you asked for before releases resume.
3. **Eleven fixes you reported**, plus **two more silent-file-write R0 bugs** (the ordered-list renumbering and the multi-paragraph quote overwrite). Together with the trailing-newline fix shipped in v0.4.9, the known silent-write class is now closed for the reported edit paths.

This is a **PATCH release** (0.4.9 → 0.4.10) under this project's 0.x rule: everything here is a capability increment or a fix, not a change of architecture, execution carrier, or external contract shape. Large effort does not mean a large version number.

### 1. Knowledge graph visualization v0: readable, stable, explainable

The v0 design was frozen after a four-way review (four independent proposals, cross-objections, then rulings), together with the KG ontology v0. What changed for you:

- **Node size is now meaningful and continuous.** Previously every node had the same 6 px radius. Size now follows connectivity on a continuous scale from **75 % to 165 % of the base** — radius **4.50–9.90 px**, no discrete tiers or bands. 3D keeps all nodes the same size on purpose: in 3D, "big" would be read as "close", so size would fight depth perception instead of adding meaning.
- **The layout no longer jumps.** The force layout uses a deterministic seed, so the same corpus plus the same seed produces **byte-identical node coordinates every time you open the graph**, and your position is preserved within a session. Opening the graph twice used to trigger a fresh random layout.
- **Labels stop hiding the graph.** With 134 labels drawn unconditionally, the graph was buried under text. Labels now use LOD and collision avoidance: higher-degree labels win collisions, secondary labels are hidden above a density threshold and appear on hover.
- **Instrumentation for the next decision.** E1 (node-radius changes) and E2 (graph style switches) are recorded, so future visual decisions are based on data rather than taste. The acceptance metrics were registered before implementation (T-label: at least 16 of 20 random labels readable, 80 %; T-stable: byte-identical coordinates across two opens).

### 2. Update check and installer download (new)

- **Controlled by the outbound-network switch.** When outbound access is off, the update check makes **zero requests** (verified: no request reached the mock release server at all). When on: an automatic check 6 s after start at most once per 24 h, plus a manual **Check for updates** button.
- **Privacy:** only a standard HTTP GET with a `Memoria/<version>` User-Agent. No cookies, no authorization headers, no local data.
- **Download with visible progress and cancel.** Both the lite and the full package are offered (lite recommended by default; the full package is an explicit choice with a size warning). Cancelling leaves **no `.part` half-file** behind.
- **The downloaded package is checked before it is offered.** If it contains `release-manifest.json`, the app verifies structure and integrity and says exactly: "package structure and integrity checked (no digital signature)". If there is no manifest, it says plainly that file integrity was **not** checked. No "tamper-proof", "secure", "signed" or "unforgeable" wording is allowed anywhere, by design.
- **It never replaces the app for you.** The UI gives the four-step manual procedure (close the app, replace only the application folder, keep `%LOCALAPPDATA%\Memoria\config`, do not delete `hf/` when updating with the lite package) and a button that opens the download folder.
- **Your settings now survive upgrades.** Configuration, API key and recent knowledge-base list moved out of the install folder into `%LOCALAPPDATA%\Memoria\config`. Replacing the install folder no longer loses them; the migration merges per key with the newer file winning.

### 3. Eleven fixes you reported

- **Source pane: Ctrl+X works again.** A native cross-line cut silently deleted only part of the selection; the cut is now handled by the editor and byte-verified.
- **Quote-block lists work end to end.** Typing `- ` creates a nested list inside a quote; Enter continues it, Backspace merges or downgrades it, leaving the list works, Tab / Shift+Tab change level, and ordered-list numbers are preserved.
- **No more console-window flashing in the release build.** Seven subprocess launches were missing `CREATE_NO_WINDOW`; all seven are fixed and guarded by a test.
- **Replacing the installer package no longer loses settings** (see the user-state item above).
- **The false "File changed" alarm is gone.** Editing the first character of a line in source mode triggered a stale-write warning. The real cause was that the version write-back did not check which file it belonged to, so a version from another file contaminated the comparison.
- **Every link click opens the panel first — even a single link.** Clicking no longer jumps you away immediately; you get a look-first panel, and a button takes you to the editor when you decide.
- **The link panel v2 is a draggable, resizable tool.** Move it by its title bar, collapse it to a narrow strip, switch between rendered preview and source, step through multiple candidates in one single document area, pin it, and resize freely in eight directions. Position, size and mode are remembered.
- **Choice cards no longer explode in height.** At a 260 px wide conversation pane with 10 options, total card height went from **14,624 px to 771 px (−94.7 %)**; the explanation is clamped to two lines and expands when the option is focused or selected, so no information is lost.
- **The session input box has an explicit height handle**, and the context-usage ring moved from the status bar to just below the input box.
- **Editing mermaid in split view no longer steals the source pane's scroll position.** The preview's scroll echo was being mistaken for a user scroll.
- **The top-bar "Refresh" / "Build" labels now say what they do** (they are still separate actions).

### 4. Two more silent-write R0 bugs closed

- **Preview editing renumbered ordered lists and wrote the change to disk.** `10.` became `1.` and the corrupted numbering was saved. Number preservation is now part of splitting on Enter, deleting across items and pasting.
- **Preview editing a multi-paragraph quote overwrote the first paragraph.** The overwrite path is fixed; multi-paragraph quotes now round-trip correctly.

Both were verified at the byte level, including a deliberate revert to prove the test can turn red. The first R0 in this class (one trailing newline lost on save) shipped in v0.4.9.

### 5. Release packages now carry an integrity manifest

Every release now ships a `release-manifest.json`: per-file SHA-256 and byte size, generated **from the release zip itself** (not from the build folder), with canonical bytes so two people can diff two manifests meaningfully. A release-side format gate validates **the zip** — top-level structure, bidirectional hashing (no missing or smuggled files), version consistency, zip hygiene (no duplicate entries, no path traversal, no trailing data after EOCD), and a sensitive-content scan: a zip that contains private `config/` files or an API-key pattern is rejected before it can be published.

Being honest about the boundary: **there is no digital signature**. The gate catches format errors, missing files, extra files, zip corruption and incomplete downloads — it **cannot** detect a deliberate replacement whose hashes were recomputed. The UI and the release notes use the same limited wording on purpose.

The build folder deliberately keeps a local API key for real-machine testing; the gate never inspects that folder, only the zip that actually ships. That is the right boundary: check what you publish, not where it came from.

The gate already paid for itself during implementation: it found three runtime leftovers in the real `Package/` folder — including diagnostic logs that contained the maintainer's absolute paths and window coordinates — and forced them out of the distribution instead of silently shipping them.

### 6. Engineering governance (brief)

- UI contract C1–C7 with style machine checks and a 270-entry current-state baseline.
- Test-assertion granularity criteria B-test-literal-1..4, machine-checked; a length-based threshold that measurement falsified was replaced.
- `docs/todo.md` index-ized: 65,445 → 24,132 bytes, details moved to `docs/todo/`.
- `prompt_drift` closed five silent-pass surfaces and is now wired into `team_audit`.
- `release_preflight.py` gained `VERSION-NOTE-PUBLISHED`: the "most recently published version" note in `version.md` must equal the tag being released.
- L1 "create the task before spawning" is now machine-checkable; B-danger-1 forbids checkout/reset in the shared workspace.

### Known debts

- The update check and download were validated on a real WebView2 app against a **mock** GitHub Releases endpoint; the live GitHub release path has not been exercised end to end yet.
- The release format gate verifies structure and integrity only; without signatures it cannot detect deliberate tampering with recomputed hashes (documented and reflected in the UI wording).
- KG node-size decision U-KGV-2 is still open:
- **Three KG acceptance checks are human-gated and were not run in this release**: node-size ends distinguishable (T-size-1), label readability around 80% (T-label), and the 3D depth-misreading check (T-depth). The automated ones (T-size-2/3/4, T-census, T-stable) are in the test suite; these three need a person and are tracked as U-KGV-5 instead of being marked done. when you change the base `nodeRadius` away from 6, the 75 %–165 % range currently scales with the new base; keeping a fixed 6 px base remains an alternative.
- The R0 fixes were byte-verified on the reported edit paths; other edit paths were not exhaustively fuzzed.

### Download

| Package | Notes |
|---|---|
| `Memoria-v0.4.10-win64.zip` | Full package (about 1.18 GB), built-in models, works offline |
| `Memoria-v0.4.10-win64-lite.zip` | Lite package (about 35 MB), no `hf/` models; embedding / rerank need the network on first use |

Unzip and run `Memoria.exe`. Your settings live in `%LOCALAPPDATA%\Memoria\config`, so you can replace the application folder safely.

### Verification (release-candidate run)

`pytest` 1618 passed / 0 failed; `team_audit` FAIL=0; the package format gate was validated end to end on a staging copy of the package (and proven to fail on a forbidden leftover); the update mechanism passed T-upd-1..9 (zero requests when outbound is off, progress, cancel, size and manifest checks); the KG acceptance metrics were registered before implementation.

## Cost (Agent compute)

- **Magnitude**: roughly **CNY 250-600** (estimate; not itemised).
- **Accounting basis**: v0.4.10 is counted **separately** from the earlier v0.4.7–v0.4.9 block that was already disclosed as merged, so the two figures are never added together. The figure is estimated from team session rounds, the number of commits (55) and team size; token-level accounting was never recorded, so this is an estimated order of magnitude, not a metered bill.
- **Cost structure (one line)**: most of the budget went to real-machine verification (WebView2 instances, CDP probes, time-series measurements) and to the design reviews for KG visualization, not to writing code.

---

## 中文

### 为什么要升级

这次更新值得装的三件事：

1. **知识图谱终于像它表示的知识了。** 节点大小现在随连接度连续变化；布局是确定性的（同一个库、同一个种子，每次打开坐标字节级一致，不再每次重排）；标签也不再糊成一片。
2. **应用能检查更新并帮你下载安装包** —— 由你明确操作，绝不自动替换。这是你要求的最后一道发版前置闸门。
3. **你报的 11 个问题已修复**，另外**再关闭两个会静默改文件的 R0**（有序列表重编号、多段引用覆盖第 1 段）。加上 v0.4.9 已修的尾换行，已报告的静默写入问题这一类到此关闭。

按本项目 0.x 硬规则，这是 **PATCH 版**（0.4.9 → 0.4.10）：本次全是有上限的能力增量与修复，不是执行载体、架构范式或外部契约形态的根本变化。**工作量大不等于版本号大。**

### 1. 知识图谱可视化 v0：可读、稳定、可解释

v0 设计是四方独立提案 → 交叉异议 → 逐条裁决后冻结的，与 KG 本体 v0 一起定稿。对你的实际变化：

- **节点大小有意义且连续。** 以前所有节点都是 6 px 半径；现在按连接度在**基准的 75 %–165 %** 之间连续变化，即半径 **4.50–9.90 px**，不设挡位。3D 故意保持等大：在 3D 里「大」会被读成「近」，大小会和深度线索打架，而不是增加信息。
- **布局不再跳。** 力导向布局使用确定性种子：同一个库 + 同一个种子，**每次打开节点坐标字节级一致**，且会话内保留位置。以前每打开一次就重新随机排一次。
- **标签不再淹没图形。** 134 个标签无条件全画时，图被文字盖住。现在标签做 LOD 与避让：连接度高的标签优先，密度超过阈值时隐藏次要标签、悬停再显示。
- **为下一个决定留下数据。** E1（节点半径改动）、E2（图谱风格切换）开始记录，后续视觉决策看数据而不是审美。验收指标在实现前就登记了（T-label：随机 20 个标签至少读出 16 个，80 %；T-stable：两次打开坐标字节级一致）。

### 2. 检查更新与下载安装包（新）

- **受出网开关控制。** 出网关闭时，检查更新**零请求**（实测：mock 发布服务一条请求都没收到）。打开时：启动后 6 秒自动检查（24 小时内最多一次）+ 手动「检查更新」按钮。
- **隐私：** 只用标准 HTTP GET + `Memoria/<版本>` 的 User-Agent；无 Cookie、无 Authorization、不发送本地数据。
- **下载有进度、可取消。** 提供 lite 与 full 两个包（默认推荐 lite；full 需显式选择并提示体积）。取消后**不留 `.part` 半成品**。
- **下载后先校验再提供。** 包里带 `release-manifest.json` 时校验结构与完整性，文案严格为「已校验包结构与完整性（不含数字签名）」；没有清单就明确说「文件完整性未被校验」。UI 一律禁止「防篡改 / 安全 / 已签名 / 不可伪造」这类表述。
- **绝不自动替换。** 界面给出四步手动替换说明（关闭应用、只替换应用文件夹、保留 `%LOCALAPPDATA%\Memoria\config`、用 lite 升级时不要删 `hf/`），并可直接打开下载文件夹。
- **换安装包不再丢配置。** 配置、API key、最近库列表已从安装目录移到 `%LOCALAPPDATA%\Memoria\config`；迁移改为按 key 合并、较新文件胜出。

### 3. 你报的 11 个修复

- **源码区 Ctrl+X 恢复可用**：跨行原生剪切会静默只删一部分；改由编辑器接管并做逐字节校验。
- **引用块内列表全闭环**：引用块里敲 `- ` 生成列表；Enter 续列、Backspace 合并/降级、退出列表、Tab / Shift+Tab 升降级都可用，有序列表编号保持不变。
- **发布版不再闪控制台窗口**：7 处子进程启动缺 `CREATE_NO_WINDOW`，全部修复并有测试守卫。
- **换发行包不再丢设置**（见上面的用户态迁移）。
- **「File changed」误报修好**：源码模式编辑行首会触发 stale-write 警告。真因是 version 写回没校验归属，别的文件的 version 污染了比较。
- **链接点击统一「小窗优先」**：即使单链接也先出面板让你看一眼，而不是立刻跳走；决定后再用按钮拉到编辑区。
- **链接面板 v2**：标题栏可拖动、可折叠成窄条、预览/源码可切换、多候选在同一个文档显示区内切换、可钉住、八方向自由缩放；位置、尺寸、模式都会记住。
- **选择题卡片不再撑爆高度**：会话栏 260 px 宽 + 10 个选项时，卡片总高度 **14,624 px → 771 px（−94.7 %）**；解释默认两行截断，聚焦/选中时展开全文，信息不丢。
- **会话输入框加了显式高度把手**，上下文用量圆环从底栏移到输入框下方。
- **分栏模式编辑 mermaid 不再抢源码区滚动**：预览的滚动回声被误判成了用户滚动。
- **顶栏「刷新 / 构建」文案改成意图可辨**（仍是两个独立动作）。

### 4. 再关两个静默改文件的 R0

- **预览编辑会把有序列表重编号并写盘**：`10.` 变成 `1.`，而且改坏后的编号被保存。现在 Enter 拆项、跨项删除、粘贴都保持编号。
- **预览编辑多段引用会覆盖第 1 段**：覆盖路径已修，多段引用现在能正确往返。

两条都做了逐字节验证，并做了「把修复回退后必须变红」的判别力自证。这一类的第一个 R0（保存丢一个尾换行）已在 v0.4.9 修复。

### 5. 发布包现在带完整性清单

每次发布都会生成 `release-manifest.json`：逐文件 SHA-256 + 字节数，**从发布 zip 本身**生成（不是从构建目录），使用规范化字节（两个人各自生成的清单可以直接 diff）。发布侧格式门禁校验**这个 zip**：顶层结构、双向哈希（不缺文件、不夹带文件）、版本一致、zip 卫生（无重复条目 / 无路径穿越 / EOCD 后无尾随数据），以及敏感内容扫描：zip 里出现私有 `config/` 文件或 API key 形态，就不允许发布。

诚实边界：**没有数字签名**。门禁能抓格式错误、缺文件、多文件、zip 损坏、下载不完整，**抓不到**「替换文件并重算哈希」的有意篡改。UI 与发布说明使用同一套有限表述，是刻意为之。

构建目录里会保留一份本地测试用的 API key（真人真机测试需要）；门禁**从不检查构建目录，只检查真正发出去的 zip**。这才是正确的边界：校验你发布的东西，而不是它从哪来。

这条门禁在实现期间已经回本：它在真实 `Package/` 里抓到三个运行时残留，包括含维护者本机绝对路径与窗口坐标的诊断日志，并强制把它们清出分发包，而不是静默发出去。

### 6. 工程治理（简）

- UI 契约 C1–C7 + 样式机检 + 270 条现状基线。
- 测试断言粒度判据 B-test-literal-1..4 机检化（实测推翻了一个基于长度的阈值）。
- `docs/todo.md` 索引化：65,445 → 24,132 B，详情外移到 `docs/todo/`。
- `prompt_drift` 修掉 5 个静默放行面，并接入 `team_audit`。
- `release_preflight.py` 新增 `VERSION-NOTE-PUBLISHED`：`version.md` 里「最近已发布版本」必须等于本次 tag。
- L1「先建任务再 spawn」可机检；B-danger-1 禁止对共享工作区 checkout/reset。

### 已知债务

- 检查更新与下载是在**真机 WebView2 + mock GitHub Releases 服务**上验证的；**尚未对真实 GitHub 发布路径做端到端验证**。
- 发布包格式门禁只校验结构与完整性；没有签名，无法发现「替换并重算哈希」的有意篡改（已在文档与 UI 文案中如实标注）。
- KG 节点大小有一个未决项 U-KGV-2：
- **KG 有三项验收需要真人判读，本轮未做**：节点大小两端可辨（T-size-1）、标签可读性约 80%（T-label）、3D 深度误读检查（T-depth）。可机检的（T-size-2/3/4、T-census、T-stable）都已在测试里；这三项需要人参与，登记为 U-KGV-5，而不是标记为已完成。当你把基准 `nodeRadius` 调离 6 时，75 %–165 % 区间目前随新基准缩放；「固定以 6 px 为基准」仍是备选。
- R0 修复在已报告的编辑路径上做了逐字节验证；其他编辑路径未做穷举 fuzz。

### 下载

| 包 | 说明 |
|---|---|
| `Memoria-v0.4.10-win64.zip` | 完整版（约 1.18 GB），内置模型，离线可用 |
| `Memoria-v0.4.10-win64-lite.zip` | 轻量版（约 35 MB），不含 `hf/` 模型；首次使用 embedding / rerank 需联网 |

解压后运行 `Memoria.exe`。你的设置保存在 `%LOCALAPPDATA%\Memoria\config`，替换应用文件夹不会丢。

### 验证（发布候选轮）

`pytest` 1618 passed / 0 failed；`team_audit` FAIL=0；包格式门禁在真实包的暂存副本上端到端验证通过（并证明有禁止残留时会红）；更新机制 T-upd-1..9 通过（出网关闭零请求、进度、取消、大小与清单校验）；KG 验收指标在实现前预先登记。

## 造价（Agent 算力）

- **量级**：约 **250–600 元人民币**（估算，非逐项计量）。
- **统计口径**：v0.4.10 **单独统计**，不并入此前已披露为合并统计的 v0.4.7–v0.4.9 块（两个口径不相加）。依据 = 会话轮次 + 提交量（55 个提交）+ 团队规模；token 级台账未记录，因此这是估算量级，不是计量账单。
- **成本结构（一句话）**：主要花在真机验证（WebView2 实例、CDP 探针、时间序列测量）与 KG 可视化的设计评审上，不是写代码。
