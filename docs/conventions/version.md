# Memoria 版本规范

> **用途**：定义版本号格式、唯一事实源、一致性约束与升级流程，使源码、构建产物、UI 显示三处版本统一且可追踪。
> **目标读者**：项目负责人（用户）与 AI Agent（凡涉及版本变更或打包必读）。
> **关联文档**：[meta-rules.md](./meta-rules.md)（规范书写元规则）；[directory-organization.md](./directory-organization.md)（目录组织）。

## 1. 当前版本

| 项 | 值 |
|----|----|
| 当前版本 | **0.4.6** |
| 版本阶段 | 0.x（未稳定，接口可变更） |
| 版本类型 | SemVer：`MAJOR.MINOR.PATCH` |

## 2. 版本号格式与递增规则

格式：`MAJOR.MINOR.PATCH`（必要时 `-prerelease`）。

| 位 | 何时递增 | 示例 |
|----|---------|------|
| MAJOR | 破坏性重构（不兼容） | 1.0.0 → 2.0.0 |
| MINOR | 新增功能（兼容） | 0.2.0 → 0.3.0 |
| PATCH | Bug 修复（兼容） | 0.2.0 → 0.2.1 |

0.x 阶段约定：MINOR 可用于较大的功能里程碑（如本次 0.1.0 → 0.2.0 伴随窗口壳重构与整理）。

## 3. 唯一事实源（Single Source of Truth）

版本号**只定义在一处**：

```
src/memoria/__version__.py
    __version__ = "0.2.0"
```

升级版本 = 只改这一个文件。

## 4. 版本一致性约束

| 文件 | 要求 | 强制方式 |
|------|------|---------|
| `src/memoria/__version__.py` | 唯一事实源 | — |
| `pyproject.toml` `[project].dynamic = ["version"]` | 通过 `[tool.setuptools.dynamic] version = {attr = "memoria.__version__.__version__"}` 从 `__version__.py` **动态读取**，无需人工同步 | setuptools 打包时自动解析 |

> 早期版本曾硬编码 `pyproject.toml [project].version` 并由 `packaging/build.py` 校验一致性（不一致拒绝构建）。2026-08-29 起改为 dynamic version，**升级版本只需改 `__version__.py` 一处**。

手动校验（读取当前版本）：

```powershell
python -c "import sys; sys.path.insert(0,'packaging'); import build; print(build._read_version())"
```

## 5. 版本消费链路

### 运行时（UI 显示）

```
__version__.py
  ├─ UIAPI.get_window_chrome() → {version}
  │    └─ 前端 window-chrome.js：document.title / 欢迎页 h1 / 顶栏 badge（v0.2.0）
  └─ 壳窗口标题：pywebview.py / pyqt6.py（"Memoria v0.2.0"）
```

### 构建产物

```
__version__.py
  └─ packaging/build.py _read_version()
       ├─ Package/VERSION
       ├─ Package/manifest.json → "version"
       └─ Package/config/README.txt（{version} 模板替换）
```

### 安装元数据

```
__version__.py
  └─ pyproject.toml [project].dynamic + [tool.setuptools.dynamic] attr 读取
       └─ pip 安装 / 打包元数据（同一来源，天然一致）
```

## 6. 升级版本步骤

1. 修改 `src/memoria/__version__.py` 为 `"x.y.z"`（唯一一处）
2. 更新本文件「当前版本」与「变更记录」表
3. 构建发布：`packaging\build_release.cmd --no-clean`
4. 验证：
   - `Package\VERSION` 内容 = `x.y.z`
   - 启动发布包后顶栏 badge / 欢迎页 / 窗口标题显示 `vx.y.z`
5. 打 tag 与发布：tag 用 `vx.y.z`；GitHub Release 资产按 [operations.md §5.1](../guides/operations.md) 命名（`Memoria-vx.y.z-win64.zip` 完整包 + `Memoria-vx.y.z-win64-lite.zip` 轻量包，**两者同时上传**）

## 7. 变更记录（CHANGELOG）

> 约定：每次升级在此追加一行。格式：`版本号（日期）｜ 变更要点`。

| 版本 | 日期 | 变更 |
|------|------|------|
| 0.4.6 | 2026-10-24 | **主题：编辑正确性 + 冷启动 + 团队治理** ① **跨块选区四种操作全部可用**（复制/剪切/删除/粘贴替换）—— 此前选区跨到引用块/表格/代码/公式/mermaid 时整段操作被**静默放弃**（DOM 已 preventDefault、剪贴板已写 ⇒ 粘贴后原位残留）；现支持 blockquote 按内部段落粒度、表格/代码/公式/mermaid 按**原子块整体删除**（含删除摘要提示、单次 Ctrl+Z 逐字节复原、frontmatter 继续拒绝并给可见提示）；粘贴替换改为**单次 commitRange**（单撤销，无"删了没粘上"半成品态）。矩阵 146/146 PASS（8 类块 × 3 跨度 × 4 操作 × 5 类断言）。② **冷启动 15.4s → 2.4s（−84%）** —— 根因不是打开文件，而是打开之前的图谱分组标签：293 个分组逐组调 `ensure_lexical_index`，**无进程内缓存**，每次重新 json.load 4.4MB ⇒ 11.4s；加 (mtime,size) 双失效缓存后 **279× 加速（13259ms → 47ms）**；再把图谱数据与全库校验移出关键路径（复用既有 `validate_kb_async` + P3 调度），端到端 4443 → 2430ms。③ **openFile 启动期静默失效**修复 —— 早期调用先"宣称用户已导航"再去做会失败的 RPC ⇒ 污染并作废启动自动打开，整轮一篇文档都不开且无任何报错；改为**副作用之前先判可用性**，失败返回明确 `failed` + 原因。④ **多级列表** —— 栈式建树/递归回写/嵌套渲染/Tab·Shift+Tab 真正升降级（含 srcLine 失真保护）。⑤ **惰性块物化收口 W3.x** —— 块级排版缓存、工作集淘汰与回滚复用、占位高度逐类型校准（+3.41%→+1.04%）、淘汰饥饿修复（maxMaterialized 3228→146）、MathJax MathItem 释放（堆 −75.3%）。⑥ **测量工具可信化** —— 归一化规则加 canary 自检（`ruleNeverMatched`）、wrap 三态化（`"unsupported"` 不是 0）、修 `p5perf_workload` 从未 `W.reset()` 导致 M1/M2 结构性恒 0 的假零工作量；"修死文件不算修"补到 v2 生产路径。⑦ **团队治理体系** —— 机检 6→9 类（修 3 处假绿/假红：检查输入被裁剪、同一数据两工具判定相反、检查器世界模型过窄）、DSH 插件改进 R1–R8（`team_snapshot` 机器生成快照、审计日志、强制 owner、complete 绑产物、preset/tool_filter）、打包=单向门协议（预验/整目录备份/回滚/完整性校验）。 |
| 0.4.5 | 2026-10-22 | **主题：底层重构 + 优化（合并发布）**  **发布级 bug 修复 + 两处性能修复**：① **修复「预览视图下打开文档时公式全部不渲染」** —— vendor 缺 `boldsymbol` 等 4 个 MathJax 扩展，而真实教材大量用 `\boldsymbol`（语料 1,101 次/15 篇）⇒ autoload 404 ⇒ 整个 `typesetPromise` 被 reject ⇒ 2,850 公式一个都不排（仅一行 console 日志，`queuePreviewMathTypeset` 的 `.catch` 吞掉，无重试）。修法：`[+]` 只留真实存在的 6 个扩展 + `macros: { boldsymbol: ["\\mathbf{#1}",1] }`；实测 mjx **0 → 2,850**，打包版端到端验证通过。② **B1 修 O(n²)** —— `stampBlockLines` 每块 `body.split("\n")`（4,001 块 × 5,879 行），Node 实测 **721ms → 0.8ms**；打开 08 章 **−22%**、最大冻结 **−30%**。③ **A** `renderDocument` 改 DocumentFragment 一次挂载（实测无显著增益，仅整洁化）。**诚实披露**：打开 2,850 公式章节仍需 ~2.9s（浏览器 style 1.85s + layout 1.03s，由「一次性建 4,001 块 DOM」造成）；数量级改善（惰性块物化）立项 0.4.6 |
| 0.4.4 | 2026-10-22 | **显示子系统内核重构「鸠占鹊巢」（P6 四段）**：① **单一渲染内核** —— 删除 legacy 渲染器 `renderer.js`（514 行）与 `legacy-surface.js`（298 行），`render-core` 成为唯一渲染实现（整篇 `renderDocument` + 块级 `renderBlock`/`renderRange`）；② **插头机制移除** —— boot 只 `switchTo('new')`，未注册插头走 `onDegraded('unknown-surface')` + 保持当前 + 明确 reject（不静默回退）；③ **3 个临时开窗改依赖注入** —— `createRenderCore({ host })` 取代 `window.MemoriaApp.surface.*` 全局门面；④ **29 个 `renderPreview` 调用点一字未动**（换实现不换签名）。**实测**：渲染等价 13/13（块级签名 + A 级 11 项 + astCount/domCount）、12 交互剧本 12/12、代码块高亮 435 块/2189 span/0 mismatch。**如实披露**：P1 首开 / P2 打字 / P3 切页签三项工作量计数与重构前**逐字节相同**（无性能改善），本次价值在架构与可维护性 |
| 0.4.3 | 2026-09-28 | **预览渲染：窗口化整体回退 + 编辑热路径块级化与「原生优先」（AG93–AG105）；同期并入 0.4.2 之后累积的两批（联网 N 线 / K4a 窗口化，后者已在本版内回退）**。① **知识库 Agent**：**联网 N 线**（`web_search` / `fetch_url`，工具面 18 → 24；按 `Content-Encoding` 解压 + 二进制判据重写 + 域名名单**逐跳**校验 `WEB_BLOCKED_DOMAIN`）+ **能力插件契约**（`NET_CATALOG` 出网族目录、工具级能力闸 `_outbound_guard()` 顺带得到逐库启停、库级参数 schema 首例、域名名单两层：机器级 ∪ deny / ∩ allow）+ **脚本工作区**（`services/agent/scratch.py`：路径双校验把写面锁在 `<kb>/.memoria/agent/scratch/`、单文件 1 MiB / 总量 20 MiB / ≤200 文件 / 超时 5–300s / stdout 各 64 KiB / 环境变量白名单；模型面只有 `scratch_list/read/write/delete` 四把，**执行权留在人手上的面板「运行」**）。② **预览性能（K4a 一线，**已整体回退**）** —— 曾落地"加载过渡窗口化"（占位块 + 按屏定窗 + 双向扩张 + 高度回填补偿 + 分帧物化 + 逃生门开关），真机读数一度把切页签从 1.3–3.4 s 压到 **311/352 ms**、池占用 35.7 MB → 3.4 MB；但它是一整套虚拟滚动引擎，**定位错 / 编辑卡死 / 滚不动 / 卡在一窗里出不去**反复出现 ⇒ 人拍板「**回退到落地窗口化之前，我们回到全量渲染**」，代码侧删净（`memoriaPreviewWindow` 模块 790 行 / 全部挂钩点 / `.-pv-spacer` / 设置开关 / 策略键 / 23 例测试），预览回到**整篇渲染 + 原生滚动**。**保留下来的**：缓存池智能替换（GDSF 老化 + TinyLFU 入场闸 + Hyperbolic 按占用）、**导航预测器**（`js/nav-model.js` 截断 PPR + 全局 PageRank 先验 + `js/nav-predictor.js` 包装导航五出口，落 `<kb>/.memoria/cache/nav/transitions.jsonl`）、脚本工作区设置页与随包技能包。③ **预览编辑热路径** —— 结构性提交（回车拆段 / 退格合并 / 跨块删除 / 边界插空行 / 图片块 / 撤销重做）全部改走新 `paintPreviewAfterSourceEdit()`：**全量解析 + 公共前后缀差分 ⇒ 只重建真正变化的块**（不再"整篇重解析 + 重建 30 万节点 + 整篇 MathJax/mermaid + 先插『渲染中』占位把高度塌掉"），任一不变量不成立即退回整篇；差分基准改为 `_domBlockSig`（修我引入的 AST↔DOM 错位：「`ada⏎啊SD…` 行首退格后预览只剩 `ada`」）。按键热路径继续瘦身：源码面板增量更新 `patchEditorLines()`（原来每键整篇重建 5888 行元素）、后处理只对单块、跳过 O(文档) 的 `stampBlockLines()`、常驻诊断埋点 `keys-debug.js` 改按需开启（`localStorage["-keys-debug"]="1"` 或 `?kdbg=1`）、新增 `[EDIT] 按键提交 Xms` 读数（>20 ms 才打）。④ **原生优先与落点** —— 预览区打字不再"每键重渲那一块"：IME 路径（`compositionend`）DOM 由浏览器原生写好，只把"渲染态归一"推迟到停手 ~180 ms；**切模式位置漂移修复**（锚点与滚动位置改为在重渲染**之前**采集 —— 修 AG82 `keepPosition()` 随窗口化回退被删掉所导致的**回归**）；**跳转落点二次校准**（`scrollIntoView` 时排版未落 ⇒ ~350 ms / ~1.4 s 各再对准一次，用户一动即放弃）。⑤ **文档与台账** —— 新增 `docs/design/preview-render-refactor.md`（**K5 实现方案**：输入所有权反转 / 高度账本 / 视口化三期 + 验收与回滚）与 `design/preview-render-pipeline.md §3.9`（CodeMirror 6 / ProseMirror / Lexical / Monaco / Ace 调研：**窗口化七件配套件 ↔ K4a 逐条对照**、明确不抄清单、我们热路径还剩下的 7 笔成本带行号）；AG01–AG57 归档 `docs/design/agent-panel-batches.md`、`docs/todo.md` 402 KB → 46 KB 之后继续按 AG 编号登记。`pytest -q` **1399 passed** |
| 0.4.2 | 2026-09-22 | **知识库 Agent「写面」打通（dsh 移植 M3）+ 权限 / 守卫 / 插件 + 交互与视觉收口**：① **写模块主链** —— `propose_write` 提议（工具面第一次能写）→ 计划确认卡（一份计划一张卡、状态原地推进、长文本悬浮看全）→ apply（编译器 + 原语白名单 + **整批回滚**）；配套**写前备份 / 撤销一步 / 重做一步**、**审计事件层**、**写冲突保护**（版本令牌 + 「以我为准」先备份再覆盖）。落盘一律走既有原语，不新造写实现。② **写能力覆盖** —— 文件级 `create_file` / `rename_file` / `move_file` / `delete_file`；正文级 `replace_lines` / `insert_lines` / `delete_lines`（**移出**风险表：判据是"不可逆"，而它有逐字 `expect` + 备份 + 整批撤销）、块级重建 `upsert_block`（代码块 / mermaid / 公式）、图片引用 `insert_image_ref`；sidecar 结构三件套 `upsert_edge` / `delete_kp` / `rename_kp`（全库级联）；库级 `rebuild_manifest`（等价界面「构建」，「清单陈旧」那类账 agent 自己就能收）。③ **两道闸** —— **读后写守卫**（语义移植上游 `fs/fs-observation-policy`：未读即写 `FS_NOT_OBSERVED`、读到过但当时不存在 `FS_NOT_FOUND`、版本变了 `FS_STALE_VERSION`；`create_file` 免读、写后刷新观察版本）与**审批档位**（手动 / 自动 / 完全访问 + **逐条确认卡** + `approval/asked`·`approval/decided` 审计事件；上游 `never` 改名 `allow-all` —— 同名反义易误判）。④ **能力插件声明面**（`services/agent/plugins.py`，守「插件目录内不含可执行代码」铁律；`kb.*` ↔ 落盘原语的**命名桥**单列一处）+ 技能面（`/name` 用户手势、只扫用户原文）。⑤ **读面**：`read_document` 可读**非 markdown 文本**（`.txt` / `.csv` / 源码；UTF-8 BOM 吃掉 + GB18030 回退；含 NUL 的二进制明确拒并指路 `read_image`），写面仍只认 `.md`。⑥ **交互 / 视觉** —— 思考改**按步多段**（与工具行天然交错；摘要行移出圆角气泡；气泡内可滚轮翻看；「展开」只**变高一点** 20rem）、**回合过程折叠**（对齐上游 compact 档 + 可按轮展开）、生成中**可上翻**（粘底语义，不再被每帧拽回底部）、回复底部「**用量 + 复制**」同一行、文件树图标两态**颜色轴**（已配置着主题色 / 未配置灰且浅）+ 缩进**折角紧贴图标**、空输入框 ↑/↓ 翻「发过的内容」、Ctrl+Enter 框内换行（修镜像层与光标错位）、每轮结束自动刷新工作区。⑦ **上游对齐**：移除「连续调用工具 8 轮上限」（上游明写**没有内置轮次预算**）。⑧ **修复** —— 写路径 `WinError 5` 全仓收口（写路径统一 `replace_with_retry`）、`move_file` 的 `to_dir` 口径（`""` / `.` / `./` = 库根；计划期与落地期收口到同一个 `normalize_target_dir()`）、`propose_write` 三条"读不出怎么改"的错误信息改成可照做、**字样式命令** `[[\h\|…]]` 不再被当 wikilink、`mapping-debug.log` / `undo-debug.log` 不再写进知识库根（改落 `.memoria/cache/**`）、设置「显示」页签滚不动、写路径全废（`body_edit.py` 缩进）与「分批写入断在半路」。`pytest -q` **1103 passed** |
| 0.4.1 | 2026-09-20 | **知识库 Agent 面板（dsh 移植 M1–M2 收尾 + 引用板块 + 跳转高亮修复）**：① **上游读面** —— `read_document` 分页续读（`offset`/`limit`，默认且上限 2000 行）+ 新增只读 `glob` / `grep` / `read_image`（校验层；缺多媒体「眼睛」插件即明确报 `UNSUPPORTED_IMAGE_INPUT`，不伪造成功），工具面由「知识库根」改为**工作区允许根列表**（`.memoria/**` 默认可见，为将来越出根目录留位）；② **会话查询五工具补全** —— `session_event_search` / `session_trace` / `session_event_trace` / `session_event_read`（只读、限本库、`session_id` 必填）；③ **引用板块** —— 只读 `resolve_reference` / `audit_references`（五类引用逐条回「指向什么 / 歧义候选 / 建议下一步」，不猜）。④ **引用机制** —— 选区引用带**源码位置**（`@路径#L3C2-L5C7`，预览区已到字符级）、会话片段引用（`@[标题](dsh-session:s1#seq:3c12-3c48)`，输入框用短别名、发送前展开成完整 URI）、对话内引用渲染成 chip 并标出「起 / 止」、打字框镜像层把 token 渲染成引用块（可拖文件树 / 拖顶栏页签入对话栏）。⑤ **跳转高亮** —— 块↔源码行映射收敛到 parser **单一事实源**（修「预览高亮位置错、行号偏小」：274 份 md 中 223 份存在错位的根因）、高亮带跟随 Mermaid/MathJax 布局、预览「源坐标」改**按需现算**（不写 DOM，编辑态与只读态同一路径）。⑥ **历史行右键菜单**（重命名 / 删除 + 悬浮提示），删除改应用内确认弹窗；新增 RPC `agent_session_rename`（**追加**一条 `session/title`，最新者胜，回放零改动）。⑦ 上游引用类收尾：时间上下文（`context/time-context`）与模型切换告知（`core/agent` `model-selection`）。⑧ **文档** —— 新增多 Agent 协作契约 [`AGENTS.md`](../../AGENTS.md)、能力插件与写模块总设计 [`agent-plugin-design.md`](../design/agent-plugin-design.md)（活文档）、发布与「连不上先试本地代理」运维规范。`pytest -q` **356 passed** |
| 0.4.0 | 2026-09-20 | **知识库 Agent 面板（dsh 移植 M1–M2）**：① **M1** —— 代码级移植 LLM 能力（纯标准库）+ Agent 主体只读竖切打通、多轮续聊与会话历史、真取消 / 恢复上次会话 / 删除会话；② **M2** —— `@路径` 上下文引用、跨会话引用（`context/session-reference`）、长会话自动压缩成 checkpoint、历史会话检索工具 `search_sessions`、会话标题（`session/title`）与免模型旧工具结果裁剪；③ **用量可视化** —— 状态栏余额槽 + 成本浮层（官方价目表 / 逐轮峰谷价）、每轮 token 用量行、状态栏刷新间隔可配。**UI 视觉收敛**：A/B 档 token 落地（圆角 4/6/8/12/999、描边 0.5px、三档阴影）、统一 `--bar-h` 栏高与 `--border-sep` 分隔线、滚动条变细并按需显形、状态 bar 四槽语义色、设置弹窗新增「对话」页签。**文件树 / 图标 / 流式渲染**：目录可折叠（记忆 + 重渲守卫）、借用 dsh 自有图标替换 emoji、文件树拖拽引用入对话栏、助手气泡渲染 Markdown（净化 + 锚点保留）+ 流式中间缓冲逐行渲染（AG11）。**打包分发修复**：P06 双击闪退根因 = Mark-of-the-Web（pythonnet / `Assembly.LoadFrom`），随包 `Memoria.exe.config`（`loadFromRemoteSources`）修复并重建 Release 资产（已在 0.3.4 行同名重构建登记）。**示例**：公开 IELTS 词汇库 `docs/example/AAA_Vocab/` 与上手 / 部署指引（`site/`） |
| 0.3.4 | 2026-09-16 | **图谱性能（G05 主体，目标档 5000 节点）**：① **D1 帧预算化** —— `sim-core.runTicksWithBudget`（2D/3D/worker 共用，默认 8ms、至少 1 tick），帧时间从此有上界（目标档整帧 p95 9252→710ms）；② **D2 Barnes-Hut 近似排斥**（新 `graph-bh-tree.js`，2D 四叉树 / 3D 八叉树，θ=0.9，分组语义与 `skipPairRepulsion` 严格对齐；`bh:false` 保留精确 O(N²) 路径供同 build A/B）；③ **X3 数值稳健**（`distanceMin` 距离下限取代 `Math.random()` 抖动 + 每 tick 位移上限 ⇒ 消掉边长 2.13e9 的数值爆炸，布局确定性可复现）；④ **X4 装载卡死根治**（warmup 工作量上限 + worker 就绪超时 3s→15s）。合计：5000 节点整帧 **9108ms → 41.5ms（212×，≈23fps）**、装载 **136s → 0.35s**。新增图谱性能基准 L1 采集器 `scripts/benchmark/graph/`（结构 / 分项剖面 / θ / 同 build A/B / 对照判定）与设计稿 [docs/design/graph-benchmark.md](../design/graph-benchmark.md) |
| 0.3.4 | 2026-09-16 | 图谱「分布模式」新增**「散落」**：孤立节点不再被固定在群组网格上，而是随机散落在圆盘/球内、只受"向原点中心力 + 节点间排斥"支配（连通群仍靠连边抱团、互相推开），避免节点多时聚成一个球；分布模式可持久化 |
| 0.3.4 | 2026-09-16 | 修复「构建」按钮**连点导致重复构建**（多条构建指令排队，表现为"构建完又构建"）：改为幂等 —— 在飞标志独立于按钮 `disabled`，重复请求直接忽略 |
| 0.3.4 | 2026-09-18 | **同名重新构建并替换 Release 资产（未改版本号）**：修复部分机器上「解压后双击即崩」。根因 = Mark-of-the-Web —— zip 解压出的文件被 Windows 写入 `Zone.Identifier`（ZoneId=3），.NET Framework 的 `Assembly.LoadFrom` 拒绝加载来源为「Internet 区域」的程序集（HRESULT `0x80131515`），pywebview 的 WinForms 后端正是这样加载随包 pythonnet 的 `Python.Runtime.dll`，失败后只报 `Failed to resolve Python.Runtime.Loader.Initialize`。**修法**：随包 `Memoria.exe.config`（`<loadFromRemoteSources enabled="true"/>`，.NET 官方开关；`packaging/templates/` 新增模板、`build.py` 拷贝并校验、两份 zip 清单同步加入），另在启动失败时弹可读提示（`packaging/app_release.py::_show_fatal_dialog()`）。**顺带**：两份 zip 不再打 `Package\config\`（避免把维护者本机的 `ui-settings.json` 发出去）。无数据格式变更，直接覆盖升级即可（详见 `docs/todo.md` §8 P06） |
| 0.3.3 | 2026-09-16 | **浅色主题**（深色/浅色/跟随系统，含知识图谱 2D/3D、代码块高亮、Mermaid 全套颜色 token）+ 顶栏灰底/底栏告警配色；**图标系统**：`scripts/icons/` 流水线（源图 → 多尺寸 ico + 运行时同步，命名约定与忽略规则见 docs/reference/icon-system.md）+ 手绘稿清理/配色对调工具 `recolor_icon.py`；代码块语法高亮（python/cpp/c/js/ts/json/bash，零依赖）；Mermaid 主题化（连线/节点/子图，走 themeVariables）+ 分栏模式滚动反弹修复；键盘选区与跨块删除修正（预览/源码双区 Shift 逐字符、Ctrl+Shift 按词、撤销后重锚、终点可落空行；跨块删除改用真实源码行表 `__blockLineMap`）；围栏代码块内 `=` 不再被误判为公式；侧栏宽度持久化（WebView2 私有模式不保留 localStorage，改落盘 `ui-settings.json`）；打包仅同步应用图标本体（草稿/备份/候选图不再进入发布包） |
| 0.3.2 | 2026-09-10 | 检查面板新增「复制报告」（结构化 Markdown 文本，便于粘贴给他人 / Agent 排查）；新增通用轻提示组件 `js/toast.js`（复制类反馈在弹窗内可见，落地 i18n 规范中已登记的 `toast.` 规划）；顶栏右侧拖拽区修正（知识库路径框底部空白不再触发文本选择 / 拖拽复制）；补发布资产命名规范（operations.md §5.1：完整包 `Memoria-v<版本>-win64.zip` + 轻量包 `-win64-lite.zip` 双形态） |
| 0.3.1 | 2026-09-10 | 维护机制迭代（G3–G5）：前端作业调度内核、持久化 flush 屏障、词法索引后台化、KP 行号范围实时同步、F01–F03 维护面收敛（含 CLI `diagnose-images`）。**知识库 Agent**：`.memoria/agent/` 工具包（智能体指令 + 编撰/维护规范 + 支持格式说明 + FSRS 确定性调度脚本），应用内「文件 → 创建 Trae 智能体」一键生成、打开知识库自动补写/刷新、规则可独立升级无需重建智能体。新增多 Agent 协作契约 `AGENTS.md`（builder/verifier/registrar + 可插拔扩展） |
| 0.3.0 | 2026-09-04 | 导入模块：由 0.2.x 单一「平面文件导入」扩展为面向三类场景的完整导入体系（三种导入源、统一内容模型、增量与冲突策略），新增导入前清单预览与面向 Agent harness 的结构化反馈接口（字段名冻结）；版本 0.3.0 同步 `__version__.py` + README 徽标 |
| 0.2.0 | 2026-08-20 | 换壳 pywebview（WebView2）根治首帧冻结；窗口原生动画/顶栏原生拖拽/Aero Snap/Win11 圆角/最大化铺满工作区；打包机制整理（scripts↔packaging 职责划分、构建脚本修复）；m0→app 目录与命名重构；版本统一机制（单一事实源 + 构建校验）；样式笔刷公式映射修复与选区高亮 |
| 0.1.0 | 2026-08 之前 | 早期版本（前置功能基线：知识库浏览、检索、图谱、链接、导入等） |

## GitHub Release 标题规范

**Release 的最开头标题只允许 `Memoria vX.X.X`**，不得带破折号 + 一段话。
```
✅ 允许：Memoria v0.4.7
❌ 禁止：Memoria v0.4.7 —— 惰性块物化（打开大文档 2.9s → 0.38s）
```
版本亮点写在 **Release 正文**（body）里，不写在标题上。

## GitHub Release 必须包含"造价"段

**每个新版本的 Release 正文（body）必须包含一节 `## 造价（Agent 算力）`**，写明：

1. **量级**（如"约数百元人民币"）—— 不要求精确到分，但不得省略
2. **统计口径**：
   - 能精确到单版本 ⇒ 写该版本
   - 无法切分 ⇒ 明确写"X.Y.Z ~ X.Y.W 合并统计"，并说明为何合并
     （例：v0.4.6 的惰性物化是给 v0.4.5 擦屁股 ⇒ 并入 v0.4.5 统计）
3. **成本结构**（一句话）：主要花在哪（写代码 / 建门禁 / 逐轮真机测量归因 / 被推翻的假设）

**禁止**：只写"优化了多少"而不写"花了多少"。造价与收益必须成对出现。

---

## 附录 A. 未发布变更（已实现、待随 0.5.0 发布）

> **状态（2026-10-25 撤回后）**：0.5.0 曾被发布，因违反 §14/§15 的「0.4.7 先发」顺序，
> 经人裁决**撤回**（Release 与 `v0.5.0` tag 已删除，版本号回退 0.4.6）。
> 代码与设计均保留在仓库中，但**不计入任何已发布版本**；正式发布前需先完成 0.4.7 → 0.4.8。

**主题：agent 能力架构重构 —— 有封装、有接口、可扩展、可追踪** 五阶段，每阶段均经独立验收且带**必红夹具**证明守卫真会拒绝。① **S1 三级粒度读** —— `outline`（标题树）/ `section`（单节正文）/ `snippet`（命中窗口）+ 新增 `replace_section` 写 op（复用唯一写者链，不新增写者）；真实语料 229 篇/2.59 MB 实测 **91.70% 可寻址**、2.62% 围栏误判、2.93% 重名；C1–C5 硬条件（剔围栏+frontmatter / 双锚消歧 / 无法唯一必须 `AMBIGUOUS_SECTION` 不取首个 / `#L行号` 一等回退 / 级别范围写死）；R-D2 正则统一（h1 提案 0 → 279）。**读写混合实测省 77.81% token**（纯读 92.43%，混合口径更诚实），**代价轮数 +50%**（12→18 次）。② **S2 写安全四道闸** —— W1 入口唯一（`origin` 必填，签名级 fail-closed，漏传 = TypeError）/ W2 读后写守卫（粒度读已喂观察表，修复前读写混合下粒度化**反而贵 17.09%**）/ W3 写前备份（失败零写入，逐字节撤销）/ W4 分发前审批（核心写能力也有声明位）；契约文档重写（§4 如实写「不幂等」而非承诺幂等）。③ **S3 MCP 薄绑定** —— 手写**零新依赖**无状态 server（600 行），对齐官方 2026-07-28 schema（`server/discover` MUST + `tools/list` + `tools/call`，`-32022`/`-32601`/`-32700`），最小工具集 schema **544 tok**（预算 1450）；跨进程 W2 用 spec 标准答案 SEP-2567 `read_handle` 绑 `(文件, sha256)`；**未与真实 MCP 客户端对拍**，登记为限制。④ **S4 扩展点** —— 第三方**不改核心**即可加工具（声明式 `provides.tools[].impl` + 唯一通用 `SubprocessTool` 适配器，核心零具体工具名；超时真杀进程 30s/1s 实测 1.02s、输出真截断 512KiB→262198B、无插件时 39 把工具逐项不变）；`gate`/`constrain` 移出 v1（实测覆盖率 **0%**：15 处声明全写恒真 `always`）；**扩展工具不是沙箱**，在 W1 写者链之外。⑤ **S5 trace** —— 调用级成本字段（`est_tokens`/`truncated`/`approval`/`write{txid,±lines,undo}`），**隐私硬边界**正文只存 digest+长度+首 256 字符（用第 256 字符后的秘密标记做可证伪断言），容量 6000→5000 且**错误/写路径条目 100% 保留**，`trace_cost_summary` 聚合误差 0，MCP `_meta` OTel 三键 ⇒ 跨进程 `trace_id` 与进程内写路径共享同一 trace。**门禁**：`pytest` **1464 passed / 0 failed**、11 个验收夹具全 PASS、12 交互剧本未跑（本版零前端源文件改动，如实登记为缺口）。**过程**：抓到 8 个「声明≠事实」实例（多为自纠），Lead 3 处疏忽被下属实测纠正。
