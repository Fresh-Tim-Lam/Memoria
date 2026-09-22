# dsh 代码级移植方案（D1′）：把 DeepSeek Harness 的能力逐块吃进 Memoria

> **用途**：把「**逐块移植 `dsh` 的代码、在 Memoria 内长出同等能力**」定为主线，给出包级取舍、M1 端到端切片、Python 落点、许可合规做法、四条红线的落法与分阶段验收。**本文只做方案，不含实施**；§10 的待拍板问题答复后开工。
> **目标读者**：项目负责人（拍板范围与取舍）；后续实施 Agent（据此拆任务）；评审者（核对与既有决策的冲突面）。
> **关联文档**：[deepseek-harness-integration.md](./deepseek-harness-integration.md)（旧稿：D1/D2 二分框架与红线分析，**结论仍有效但不再是主线**）、[kb-agent.md](./kb-agent.md)（知识库 Agent 载体）、[designV0.md](./designV0.md)（离线 / 不进热路径 / 禁止 silent 写入三条红线）、[../../AGENTS.md](../../AGENTS.md)（多层 Agent 协作契约）、[../conventions/directory-organization.md](../conventions/directory-organization.md)。
> **状态**：草稿（待拍板），2026-09-17。上游 pin：`deepseek-ai/deepseek-harness@0d1f5000`（master，2026-09-15T03:16:06Z）。

---

## 0. 结论速览

| # | 结论 | 标记 |
|---|---|---|
| 1 | **主线 = D1′「代码级移植」**：不是让 `dsh` 在后台跑（旧稿 D1 ❌ 否掉），也不是只做对外契约（旧稿 D2 ⏸ 旁支），而是**按包把它的语义重写进 Memoria**，产物是 Python 原生实现。 | ✅（用户 2026-09-17 拍板） |
| 2 | **形态 = 应用内对话 + 远端模型**：Memoria 里直接有对话入口，模型走远端（用户自配端点/密钥）；**不内嵌模型权重与推理运行时**；出网可在应用内开关（默认可用、不强制）。 | ✅（用户拍板） |
| 3 | **许可可行**：上游仓库 LICENSE = **MIT**，npm 包字段 = **BSD-3-Clause**（两处不一致，逐包核 `package.json`），二者均允许修改与再分发 ⇒ 移植合法，但必须做归属与声明（§4）。 | ✅（实测 2026-09-17） |
| 4 | **不能"照目录复制"**：全仓 **12,944 文件 / 3,634 个 `.ts`**，且是 pnpm workspace + tsdown 多层 Host/Client 架构。**按包切、按能力验收**才可行；M1 只用其中 6 个包的核心语义（约 20–40 个 TS 文件量级）。 | ⏳ |
| 5 | **官方"Python SDK"不是我们要的路**：`python/sdk-runtime/` 实为 `runtime-bootstrap.mjs` + `platforms.json`，即**引导一个 Node 运行时的壳**（PyPI wheel 仅 10 KB）⇒ 走它等于让 `dsh` 在后台跑，与意图相反。 | ❌（就本方案而言） |
| 6 | **合规现状（已核实 2026-09-17）**：`LICENSE` **已存在**（MIT，`Copyright (c) 2026 FreshTim`，`730f9a8a Initial commit`）✅；**缺 `THIRD_PARTY_NOTICES`** ⚠️ ⇒ 只需新增第三方声明（§4.3）。 | ⚠️ 待补一处 |

---

## 1. 目标形态（已拍板口径）

| 维度 | 决定 | 出处 |
|---|---|---|
| 交互形态 | **应用内对话**（Memoria 里的对话入口） | 用户 2026-09-17 |
| 模型位置 | **远端**（用户自配端点/密钥）；本地只保留工具类模型（embedding 等） | 用户 2026-09-17 |
| 出网 | **允许**，用户可在应用内开关；不强制联网，**默认可用** | 用户 2026-09-17 |
| 实现形态 | **Python 重写**（逐包语义移植），落 `src/memoria/services/**` | 用户 2026-09-17 |
| 与 `dsh` 运行时的关系 | **不内嵌、不后台运行**；吃的是**代码与语义** | 用户 2026-09-17 |

> **用户原话锚点**（避免后续理解漂移）：「dsh 原本是没有窗口壳体的，我要做的不是把 dsh 的功能映射过来让 dsh 后台偷偷跑，而是把 dsh 的代码一分一分吃过来获取类似的能力。」

---

## 2. 与旧稿的关系（不搞并行事实源）

| 方向 | 旧稿结论 | 现在定位 |
|---|---|---|
| **D1** `dsh` 融入 Memoria（起子进程） | ❌ 踩四条红线 | **不做**（被 D1′ 取代：能力靠移植、进程不引入） |
| **D2** Memoria 作为 `dsh` 能力提供方 | ✅ 几乎零冲突；由**另一项目**推进 | **旁支保留**（对外契约那套结论继续有效，与本方案不冲突） |
| **D1′** 代码级移植（本文） | — | ✅ **主线** |

**需要一并澄清的一处措辞冲突**：`AGENTS.md` 的 RISC 条款写「业务关注点一律作为 `builder` 的作业，**永不新增独立 Agent**」——那是**仓库协作 Agent** 的约束；本方案的"应用内对话 Agent"是**产品功能**，两者不在同一层。建议在 `AGENTS.md` 或 `kb-agent.md` 补一句边界说明（§10 P6）。

---

## 3. 上游事实基线（实测 2026-09-17）

| 项 | 值 | 来源 |
|---|---|---|
| 仓库 | `github.com/deepseek-ai/deepseek-harness`（public，默认分支 `master`，22.7 万 star，最后推送 2026-09-15） | GitHub API |
| 规模 | 12,944 文件；`packages/` 6,630、`apps/` 599、`docs/` 546、`native/` 92、`python/` 46 | 同上 |
| 语言 | TypeScript 3,634 · TSX 385 · Markdown 3,443 · YAML 1,552 | 同上 |
| 许可 | 仓库 `LICENSE` = **MIT**；`@deepseek-ai/dsh` 的 npm 字段 = **BSD-3-Clause**（`deepseek-harness-sdk` 的 `license_expression` = MIT） | GitHub / npm / PyPI API |
| 文档 | **每个包都带 `README.md` + `README.zh.md` + `README.i18n.yaml`**（中英双语，含包地图与依赖关系）⇒ 读懂成本显著降低 | 实测 |
| Python SDK 真相 | PyPI wheel 仅 **0.01 MB**；`python/sdk-runtime/` = `runtime-bootstrap.mjs` + `platforms.json` ⇒ 它是**引导 Node 运行时的壳**，不是 Python 实现 | PyPI / 仓库树 |
| 入口 | `dsh web`（127.0.0.1:3080）／`dsh --profile headless "task"`／`--profile acp`／Python SDK | 旧稿 §3 |

---

## 4. 许可与合规

### 4.1 移植的合法姿势（MIT / BSD-3-Clause 共同要求）

1. **保留版权声明与许可全文**：每块移植代码的文件头注明来源与许可，例：
   ```python
   # Ported from deepseek-harness packages/core/agent-loop (MIT / BSD-3-Clause)
   # Upstream: https://github.com/deepseek-ai/deepseek-harness @ 0d1f5000
   # Copyright (c) DeepSeek; see THIRD_PARTY_NOTICES.md
   ```
2. **不背书条款（BSD-3 第 3 条）**：不得用 `DeepSeek`／`dsh` 的名义为 Memoria 背书或暗示关联。
3. **不复制品牌资产**：logo／图标／品牌规范文件（`BRAND_GUIDELINES*`）一律不取。
4. **派生作品同样开源无冲突**（MIT/BSD 不要求同许可，但要求保留声明）——若 Memoria 将来改为非开源分发，仍须保留声明。

### 4.2 版本 pin 与跟随策略

- pin 上游 commit：**`0d1f5000`**（2026-09-15T03:16:06Z），记录于本文头部与每块代码头。
- **本地只读检出**：`dsh-src/`（仓库根，**已被 gitignore**，登记见 [directory-organization.md §1](../conventions/directory-organization.md)）。`git clone --depth 1` 得到，**HEAD 实测 = `0d1f50007f9bca3f52b06e1c3074fa14d5fb0720`**（与 pin 完全一致），11,239 文件 / 113 MB ⇒ **查上游源码一律用它，不再反复走远端 API**；`git -C dsh-src rev-parse HEAD` 可随时核对是否漂移。
- 跟随节奏：**只在需要某能力时**才去 diff 上游对应包；上游是 developer preview（旧稿 §3：会有破坏性变更），**不做全量同步**。
- 建立 `docs/design/dsh-port-ledger.md`（可选，M2 再定）登记「已吃包 → 上游路径 → pin commit → 本地落点 → 语义偏差」。

### 4.3 合规缺口（既有，需另行处置）

| 项 | 事实（已核实 2026-09-17） | 处置 |
|---|---|---|
| 自身 `LICENSE` | **已有**：MIT，`Copyright (c) 2026 FreshTim`（`730f9a8a Initial commit`，1085 字节） | ✅ 无需新建（P7 因此作废）；若要把署名统一成 `Fresh-Tim-Lam` 可自行改 |
| `THIRD_PARTY_NOTICES.md` | ✅ **已新增（2026-09-19）**：仓库根（该文件名在 [directory-organization.md §1](../conventions/directory-organization.md) 的根目录白名单内）。含 dsh 的 **MIT 原文逐字** + pin `0d1f5000…` + npm 字段 `BSD-3-Clause` 差异说明 + **逐块移植落点表**（本地路径 ↔ 上游包）+ 未移植清单 | 之后每移植一块追加条目 |
| `pyproject.toml` 许可声明 | 未声明 `license` 字段 | 可选：补 `license = "MIT"`（与 `LICENSE` 一致） |

---

## 5. 包级映射表（吃什么 / 不吃什么）

| `dsh` 包 | 规模 | 能力 | 处置 | Memoria 落点 | 阶段 |
|---|---|---|---|---|---|
| `llm/llm` | 140 ts | provider **中立**的模型调用服务（流式、用量） | ✅ 吃 | `services/agent/llm/` | **M1** |
| `llm/llm-pi-ai`（或 `llm-deepseek`） | 内含 | OpenAI / Anthropic / 自建网关适配 | ✅ 吃一个（**OpenAI 兼容**优先） | `services/agent/llm/providers/` | **M1** |
| `llm/llm-retry` · `llm/token-meter` | 内含 | 重试策略、token 计量 | ✅ 吃 | 同上 | **M1** |
| `core/agent-loop` | 118 ts（整组） | **默认循环**：消息→模型→工具→回填 | ✅ 吃（核心） | `services/agent/loop.py` | **M1** |
| `core/system-prompt` | 同上 | system prompt 组装 | ✅ 吃 | `services/agent/prompt.py` | **M1** |
| `core/tools` | 同上 | 工具注册表与调用语义 | ✅ 吃 | `services/agent/tools/` | **M1** |
| `core/session` · `core/scope` | 同上 | 会话与作用域 | ✅ 吃（子集） | `services/agent/session/` | **M1** |
| `core/agent` · `agent-default-model` · `agent-tool-presentation` | 同上 | agent 定义、默认模型、工具呈现 | ✅ 吃 `core/agent` 的 `model-selection`（**模型切换告知**，§6.15）；`agent-default-model` = 已覆盖、`agent-tool-presentation` = **本地不适用**、`core/agent` 的 registry/initiator（Cordis 专有）不吃 —— 逐条证据见 §6.15 | 同上 | **M2** |
| `session/session-persistence` + `-jsonl` + `session-format` | 158 ts（整组） | 会话持久化（jsonl）+ 格式定义 | ✅ 吃**当前格式**（迁移链 `v0→v3` ❌ 不吃） | `services/agent/session/store.py` | **M1** |
| `session/session-projection*` · `stats` · `title*` · `telemetry*` | 同上 | 投影/统计/标题/遥测 | ✅ 吃**标题**（`session-title` + `-llm` + `-first-prompt-llm`，§6.11；`-all-prompts` ❌）；**投影框架与 `stats` ❌ 不吃**（框架是 Cordis registry + 持久缓存 + change feed；`stats` 的 ttft/decode 本地无对应事件面，`turns/steps` 已由 `usage_report`/`summarize` 覆盖 —— 逐条见 §6.15 表）；**telemetry（OTel）❌ 不吃** | `services/agent/title.py` | **M2** |
| `context/agent-instructions` | 39 ts | 工作区指令文件 → 上下文（**只加上下文、不加工具**） | ✅ 吃 | 对接既有 `.memoria/agent/kb-spec*.md` | **M1** |
| `context/*-reference` · `time-context` · `tmux-context` | 同上 | 文件/会话引用、时间、tmux | ✅ 吃文件引用（§6.7）、会话引用（§6.12）与时间上下文（§6.14，只吃文本语义）；tmux ❌ | `services/agent/prompt.py`、`services/agent/session/reference.py` | **M2** |
| `interaction/user-approval` · `tool-ask-user` | 24 ts | 一次性审批、向用户提问（fail-closed） | ✅ 吃**审批**最小面（含 2026-09-22 的会话级档与逐条确认卡）；**`tool-ask-user` 本体仍未移植**：模型**中途向用户提问**的工具（`ask_user_question`）本地无（`ask_user` 在 `src/**` 只作为依赖说明出现一次） | `services/agent/approvals.py`、`services/agent/approval_bridge.py`、`services/agent/permission_presets.py` | **M1**（审批）· 待做（`tool-ask-user`） |
| `interaction/commands` · `permission-presets` | 同上 | slash 命令、权限预设 | **拆分处置（2026-09-22 订正）**：`permission-presets` → ✅ **已落地**（`services/agent/permission_presets.py`：`manual-approval`/`auto-approval`/`all-access` 三档 + 会话级旋钮 + 逐条确认卡 `approval_bridge.py`；本地档位表是**代码常量**，不是上游那种部署可配置的档位表）。`commands` → ⏳ **仍未移植**：`src/**` 内无命令注册表（`register_command` 零命中、`ask()` 无命令入口）⇒ 本地交互一律走文字消息；**但消费方现在出现了** —— compaction 已落地 ⇒ `/compact`（及 `/clear`）有了真实需求 | 前端指令 | M3（`commands` 待做） |
| `credentials/credentials-local` | 19 ts | 本地密钥**引用**（配置写名不写值） | ✅ 已覆盖（**无独立模块**，2026-09-22 核对） | `services/agent/llm/config.py`（`mask_secret()` + `save_config()`：密钥只在传入非空新值时覆盖、面板回显掩码）；原计划的 `services/agent/credentials.py` **不存在** | **M1** |
| `credentials/authorization` | 同上 | 授权流程 | ⏳ **条件性**：**本地不适用**（单端点单密钥，`llm/config.py` 已覆盖"写名不写值"；无 OAuth 端点可授权，§6.15 表）—— **2026-09-22 复核仍不适用**，仅当将来接授权类端点才回来吃 | — | 条件性 |
| `compaction/*` | 33 ts | 长会话压缩、工具输出裁剪、`/compact` | ✅ 吃 `compaction` + `compaction-basic` + `compaction-tool-result-pruner`；`image-offload` / `command-compact` ❌ | `services/agent/compaction.py`、`services/agent/pruner.py` | **M2** |
| `session-query/*` | 48 ts | 会话检索 | ✅ 吃 `session-query` 的 `extraction`+`filters` 与 `tool-session-query`；`session-query-sqlite` / `session-log-export` ❌ | `services/agent/session/query.py` | **M2** |
| `api/*` · `sdk/*` · `bundle/*` | 162+21 ts | Client↔Host 远程层、JSON-RPC、profile 组合 | ❌ 不吃（若将来要对 Trae/ACP 对接，复用旧稿 D2 的 CLI 面即可） | — | — |
| `storage/*` · `skill/*` · `hooks/*` · `guard/*` · `plan/*` · `goal/*` · `todo/*` | — | 非会话持久、技能、钩子、计划 | ⏸ 按需（`skill` 与既有 `.memoria/agent/` 提示词体系可能重合）。**M3 已评**：`skill` 归入 [agent-capabilities.md §2.1](agent-capabilities.md) 的**同一份能力插件契约**（用户技能类；该契约已**不含分类字段**，见其 §2.1「字段演进暂缓」）。**2026-09-22 复核：本行整族除 `skill` 外一个都没吃** —— `skill` 的**规则面**已落（`services/agent/skills.py`：frontmatter 契约 + 发现 + 两段式 + 两个渲染 + 只读工具，见 §6.22）；其余 `storage/*` · `hooks/*` · `guard/*` · `plan/*` · `goal/*` · `todo/*` 仍未吃（其中 `todo_write` 是唯一"看着可直接吃"的小件），且**能力插件契约本体仍未实现**（`capabilities.json` 在 `src/**` 零命中） | — | — |
| `sandbox/*` · `shell/*` · `terminal/*` · `subprocess/*` · `ssh/*` · `lsp/*` · `mcp/*` · `browser-use/*` · `computer-use/*` · `subagent/*` · `workflow/*` · `jobs/*` · `schedule/*` · `native/*` | 大 | 执行与编排 | ❌ **不吃**（Memoria 不让它跑任意命令；也避免 CVE 面） | — | — |

### 5.1 上游读写面 vs 本地现状（对照表，2026-09-20；**写面/备份/审计/守卫各行已于 2026-09-22 订正**）

> **口径**：上游 = 只读检出 `dsh-src/`（pin `0d1f5000`，**未改**）；本地 = `src/**` + `docs/**` 盘上现状。**「未移植」≠「该做」** —— 取舍仍以本节 §5 的 ❌/⏸ 判定与 §10 待拍板为准，本表只陈述事实与风险。所有 `file:line` 均为实际读出（抽查 ≥8 处见 §11 该行）。**2026-09-22 订正**：本表原为 09-20 快照，其中写工具（`write`/`edit`）、写前备份、撤销、审计四行已随 M3 落地而过期 ⇒ 就地更正（订正清单见 §11 本轮行）。

**读工具**

| 项 | 上游（做法 + file:line） | 本地（现状 + file:line 或「未移植」） | 差异与风险 |
|---|---|---|---|
| `read`（行窗读取） | `file_path` + `offset?`（1-based）+ `limit?`；单次默认且最多 **2000 行**、单行 2000 字符、单次 **50 KiB**、文件 ≥10 MiB 走流式（`dsh-src/packages/fs/tool-fs/README.md:46`、`src/read.ts:15`、`src/read-render.ts:11`、`src/read-render.ts:14`、`src/read.ts:21`） | ✅ **已移植分页（2026-09-20，§6.16）**：`read_document` 新增 `offset`/`limit`（默认且最多 **2000 行**、越界 `NOT_FOUND`、截断时正文尾给「续读请把 offset 设为 N」提示），并保留本地 **20,000 字符**预算（`src/memoria/services/agent/tools/kb.py:283-324`、`:688`、`:730-790`；工具声明 `:523-550`） | 分页缺口已补；两处**有意偏差**：① 本地正文不逐行加行号（锚点由知识点清单给出）；② 未截断时不产 EOF footer（旧调用逐字兼容） |
| `read_image` | `file_path`；PNG/JPEG/WebP/GIF，无扩展名按文件签名识别；仅当 `attachments` 挂载时注册（`dsh-src/packages/fs/tool-fs/README.md:47`、`src/index.ts:70-72`） | ⏸ **参数/校验已移植、能力未移植（2026-09-20，§6.16）**：扩展名 + 文件签名 + 「扩展名与签名不一致」三类校验照上游，随后因**缺「多媒体眼睛」插件**而明确拒绝（`UNSUPPORTED_IMAGE_INPUT`，`.../tools/kb.py:1088-1131`；声明 `:650-665`） | 读图归入**未来多媒体能力**（缺一个多媒体的「眼睛」插件，2026-09-20 设计改正）⇒ **不计入读面缺口**；当下的机制约束是 `llm/types.py:87` 的 `Message.content` 是纯文本、`providers/openai_compatible.py:396` 只写字符串；工具已注册但**永不返回图片**，一次调用=一次错误结果；待办措辞=「待『多媒体眼睛』插件」（§6.16） |
| `glob` | `pattern` + `path?`；含隐藏/忽略文件、排除 VCS 元数据；`globMaxResults` 默认 **100**（`dsh-src/packages/fs/tool-fs-search/README.md:48`、`:59-60`） | ✅ **已移植（2026-09-20，§6.16）**：Python 实现、零依赖；上限 **100** 照上游（`.../tools/kb.py:690`、实现 `:911-946`、声明 `:610-627`）；匹配口径照上游（不含 `/` 比文件名/任意深度，含 `/` 比整条路径）；工具面 = **工作区根**（今天 = 库根）—— 结构上是**允许根列表**（`_read_roots()` 今天只含库根），将来支持越出根目录（外部拖入，只读/不可信），可见性/权限由程序施加：**只**排除 VCS 内部目录（`:692`）、`.memoria/**` 默认可见（2026-09-20 改正）；原有 `kb_overview` 仍只列前 **200** 篇（`:70`、`:377`） | 与上游差异：ripgrep glob 方言（`!` 取反、`**` 之外的深度修饰）未全量支持；无 spill 存储 ⇒ 超上限只报计数 + 收窄提示；排序方向取「新→旧」（依据上游单测注释，未真机对照） |
| `grep` | `pattern` + `path?` + `include?`（ripgrep 正则，按文件分组返回 `Line N:` 预览）（`dsh-src/packages/fs/tool-fs-search/README.md:49`） | ✅ **已移植（2026-09-20，§6.16）**：Python `re` 而非 ripgrep；上限 `grepMaxMatches` = **250**、单行预览 **2000 字节**、协作预算 **30s** 照上游（`.../tools/kb.py:694-700`、实现 `:982-1072`、声明 `:628-649`）；原有 `search_kb` 的词法通道仍在（`:238`，命中面仍受 KP 索引限制） | **正则方言不同**（无 `\p{…}`、无 RE2 语义 ⇒ 同一 pattern 结果可能不同）；无 raw-output cap / spill（本地无子进程与 spill 存储），改以单文件 4 MiB 与超时兜底，跳过**报数不静默** |
| 会话检索家族（5 个只读工具） | `session_search` / `session_event_search` / `session_trace` / `session_event_trace` / `session_event_read`；`maxSearchResults=100`、`searchTimeoutMs=30000`；跨会话需 `cwd` 精确相等（`dsh-src/packages/session-query/tool-session-query/README.md:38-39`、`:47-51`） | ✅ **5 个齐了（2026-09-20，§6.17）**：`search_sessions`（§6.9）＋本轮四个 `session_event_search` / `session_trace` / `session_event_trace` / `session_event_read`（四把只读工具，`.../tools/kb.py:1295-1603`；`KB_TOOL_NAMES` 13 个名字 `:73-80`，既有锚点未漂移）。上限照上游：命中 ≤ **100**（`SESSION_EVENT_HITS_CAP` `:1185`）、`before`/`after` ≤ **50**；`search_sessions` 仍每会话只取最强 1 条（`:460`）、默认 5 / 上限 20（`:83-84`）；作用域限本库 | 剩余缺口（逐条见 §6.17 偏差表）：`session_search` 的 11 个过滤器与 `surfaces` 维度未移植；四个工具的 `session_id` **本地必填**（无调用方会话身份）；`session_trace` 因本地无 `parentSession` 写入方而实际恒为「根 + 无后代」；`sourceEventSeqs` / `derivedEventSeqs` 本地无从计算（工具文本明说，不伪造）；上游 `PROMPT_TEXT` 固定指引段未注入；无游标分页与 `searchTimeoutMs` |
| 其余读面（`str_replace_editor` 的 `view`、`todo_write`、`ask_user`、`skill`、web/computer-use/browser-use 等） | 分散在 `packages/fs/tool-str-replace-editor/src/index.ts`、`packages/todo/README.md`、`packages/interaction/tool-ask-user/README.md`、`packages/skill/tool-skill/README.md`、`packages/web/README.md` | ❌ 未移植（无执行面、无待办面、无技能工具、无外网工具） | 与 §5 第 118 行「执行与编排 ❌ 不吃」一致；`ask_user`（向用户提问）本地无，M3 的「逐条确认」交互尚无载体 |

**引用与上下文**

| 项 | 上游（做法 + file:line） | 本地（现状 + file:line 或「未移植」） | 差异与风险 |
|---|---|---|---|
| `@路径` 文件引用 | `@path` 起始/空白后触发、`@"含空格路径"`、目录尾斜杠；选区**不读内容**（`dsh-src/packages/context/file-reference/README.md:32`、`:12`） | ✅ 已移植：`FILE_REFERENCE_SECTION`（`src/memoria/services/agent/prompt.py:194-218`），门控同上游「有读取手段即注入」（`:261` + 名单 `:385-394`） | 已完全移植；两处偏差：① 上游「目录 → list it」本地无列目录工具，改指 `search_kb` 与 `glob`（`:207`）；② 门控名单由「只认 `read_document`」放宽为四个读取工具（`FILE_REFERENCE_TOOLS`，§6.16 门控）；**2026-09-20（§6.18）起** agent 侧另有只读解析与审计（`resolve_reference` / `audit_references` 覆盖本行这类 `@路径`：归一化 + 精确/唯一 basename/唯一后缀分级收敛，越界 fail-closed 拒绝、多义回候选不猜） |
| 跨会话引用 | `@[label](dsh-session:<payload>)` mention + 投影快照；uri 语法与转义（`dsh-src/packages/context/session-reference/README.md`、`src/uri.ts`） | ✅ 已移植：scheme `dsh-session:`、payload = 无填充 base64url(JSON)（`src/memoria/services/agent/session/reference.py:91`、`:102`、`:137`、`:172`）；`max_references ≤ 3` | 投影有意简化：`cwd` / `capturedThroughSeq` 恒 null、快照只进本轮请求不落盘（登记于 `docs/conventions/docs-management.md:143`）；**2026-09-20（§6.18）**：agent 侧可按 URI 解出会话 id 并核对本库会话文件是否存在（`resolve_reference`），`audit_references` 另报「URI 非规范 / id 非法 / 本库无此会话」 |
| `[[id]]` 知识点链接 | **上游无此语法** | ✅ 本地独有：`[[id]]` / `[[id#type]]` / `[[id\|text]]`（`docs/conventions/markdown-form-std.md:16-19`）；悬空目标校验 `ISSUE_UNRESOLVED_TARGET`（`src/memoria/graph/link_audit.py:27`） | 本地发明 ⇒ 无「未移植」可言；**悬空引用校验本地已有**（反向：上游反而是空白）；**2026-09-20（§6.18）起** agent 侧也有同名能力：`resolve_reference` 解 id / 文件名 / 多目标歧义，`audit_references` 逐处报「悬空 / 歧义 / 正文出现但未挂接」（别名判定需文档上下文，故落在审计侧） |
| `文件:行号` 锚点 | 上游只保证 `read` 结果自带行号，无「回答必须带锚点」约定（`dsh-src/packages/fs/tool-fs/README.md:182`） | ✅ 本地独有：工具结果带结构化 `anchors`（`.../tools/registry.py:66-78`）+ 提示词强制写法（`prompt.py:270`）；行号来自 KP range 解析（`.../tools/kb.py:212-215`） | 本地发明，是「答案可核查」的支点；风险=行号依赖 sidecar range 解析，解析失败时退化为 `line_hint`；**2026-09-20（§6.18）起** agent 侧可解单条锚点并全库审计越界行，但**区间锚点（`#L12-L30`）如实回 `unsupported`** —— 本地没有读时投影（AG07 的 L 路线未实施），只核起始行、不校验末端 |
| 时间上下文 | 每步注入时间/浏览器时区/elapsed；`refreshIntervalMs` 调速（`dsh-src/packages/context/time-context/README.md:12`、`:32`） | ✅ 已移植文本语义：`TIME_CONTEXT_SECTION` 无条件注入（`prompt.py:263`）、读数追加在本轮请求末尾（`ask.py:445`） | 有意偏差：读数不落盘、无 elapsed / turn-step、三态时区收敛为一句（§6.14） |
| 指令文件（AGENTS.md 链） | 用户全局 + 项目链、宽到窄、`maxBytes` 预算（base 默认 65,536 B）（`dsh-src/packages/context/agent-instructions/README.md:12`、`:28`） | ✅ 已移植：`load_instructions` / `render_instructions`（`prompt.py:253`），对接既有 `.memoria/agent/kb-spec*.md` | 已移植；差别=本地只有「库内指令」一层，无 user-global 层级 |
| 块级 / 片段引用 | **上游也没有**：`file-reference` 只到路径级，`read` 只有行窗（`README.md:32`、`:46`） | ❌ 未设计（本地亦无） | 属**双方共同空白**，不是「未移植」；若产品要块级引用，两边都得新造；**2026-09-20（§6.18）**：agent 侧两把引用工具**明确不含**这两类（写进工具描述与 §6.18，避免模型误以为能解） |

**写工具**

| 项 | 上游（做法 + file:line） | 本地（现状 + file:line 或「未移植」） | 差异与风险 |
|---|---|---|---|
| `write` | **整篇覆写**：`file_path` + `content`（`dsh-src/packages/fs/tool-fs/README.md:48`、`src/write.ts:74-79`）；覆盖需先读，由 `fs/write-intent` waterfall 决定（`src/write.ts:114`） | ✅ **已落地（走本地模型，2026-09-21/22）**：agent 侧唯一写工具 = `propose_write`（`.../tools/kb.py`，声明 `read_only=False`）；它只产**声明式 plan**，落盘由编译器 + apply 入口完成（`services/agent/plan.py` / `apply.py`），正文仍只经 `DocumentService.save_document()` | 本地**换了模型**（有意）：不是「工具直接写」，而是「plan → 编译器 → 唯一写者」；~~编译器未实施 ⇒ 现在连"整篇覆写"都还没有~~ **2026-09-22 订正：已落地** —— `KNOWN_OPS` **17 个** / `COMPILED_OPS` **16 个**（只剩 `set_kp_range` 只登记不编译；`services/agent/plan.py:86-148`）⇒ "整篇覆写"由 `replace_lines` + `expect` 逐字比对承担；上游那句"覆盖需先读"由**读后写守卫**承接（见下表） |
| `edit` | **字面片段替换**：`old_string` / `new_string` / `replace_all?`，默认唯一匹配否则 `FS_AMBIGUOUS_EDIT`（`README.md:49`、`src/edit.ts:84-93`、`dsh-src/packages/fs/fs-local/src/fsio.ts:814-834`、`:830-832`）；**无行区间参数** | ✅ **等价能力已落地（形态不同，2026-09-21/22）**：行区间写面 = `replace_lines` / `insert_lines` / `delete_lines` / `upsert_block` / `insert_image_ref`（均在 `COMPILED_OPS`），统一落 `edit_body` 原语（`services/agent/body_edit.py`，薄包装 `save_document()`） | 上游是**字面片段替换**（默认唯一匹配，否则 `FS_AMBIGUOUS_EDIT`）；本地是**行区间 + `expect` 逐字原文**（对不上即拒）⇒ 同一意图两种表达，**本地更严**（要求同时给行号与原文）；上游的 `replace_all` 本地无对应语法 |
| 原子写 | 私有 staging 目录 + 独占创建 `wx/0o600` + fsync + link/rename 发布；版本令牌 `dev:ino:size:mtimeNs:ctimeNs`（`dsh-src/packages/fs/fs-local/src/fsio.ts:588-670`、`:620`、`:649`、`:75-77`） | ✅ 已有等价物（人机 UI 路径）：tmp 写 + `os.replace` + fsync 策略（`src/memoria/services/document.py:339-349`） | 原子性对齐；~~**本地无版本令牌** ⇒ 做不到「文件被外部改动则拒绝写」（上游 `FS_STALE_VERSION` 的前提，见 `dsh-src/packages/fs/fs-observation-policy/README.md:42`）~~ **2026-09-22 已补**：本地版本令牌 = 内容 sha256（`storage/file_version.py`）+ 读后写守卫（`services/agent/observation.py` 的 `FS_STALE_VERSION`，见上表「读后写守卫」行）；与上游的余差只是"比较-写非原子" |
| `str_replace_editor`（多命令写面） | 一套工具里的 `view` / `create` / `str_replace` / `insert`（`dsh-src/packages/fs/tool-str-replace-editor/src/index.ts`、`README.md`） | ❌ 未移植 | 与 `read`/`write`/`edit` 功能重叠，属上游「第二套写面」；本地无 |

**把关（沙箱 · 审批 · 权限档）**

| 项 | 上游（做法 + file:line） | 本地（现状 + file:line 或「未移植」） | 差异与风险 |
|---|---|---|---|
| 沙箱三档 | `read-only` / `workspace-write` / `danger-full-access`；由 `ctx.sandbox` + 平台后端在**执行器**强制（`dsh-src/packages/sandbox/README.md:12`、`:29-32`）；`write`/`edit` 在受限后端下才广告 `sandbox_permissions`+`justification`（`src/write.ts:44-54`、`:78`、`README.md:70`） | ❌ 未移植，**§5 第 118 行整组有意不吃**；`src/memoria/services/agent/**` 内 grep `sandbox` **零命中** | 本地是**替换**而非移植：无内核级隔离，改用声明式 `permissions` + realpath 前缀校验（`agent-plugin-design.md:147`）；隔离强度完全不同档 |
| 一次性审批 | `approval/request` waterfall；`ask`/`never` 两种策略，`never` 在服务内**先于** waterfall（不可被 prepend 绕过）；无应答者 = `unavailable` = 失败关闭（`dsh-src/packages/interaction/user-approval/README.md:32`、`:36`、`:78`、`:46`） | ✅ 已移植：`AskPolicy`（`src/memoria/services/agent/approvals.py:127-152`，应答者异常/词汇外/缺席一律 `UNAVAILABLE`）、`NeverPolicy`（`:118-124`）、`DefaultApprovalPolicy`（`:109-115`）；问询在**分发前**（`.../tools/registry.py:265-288`），拒绝即 `DENIED_CODE` | 已移植；**唯一语义放宽**：本地把工具参数也交给应答者（`approvals.py:80-82` 已登记），上游应答者看不到参数 |
| 权限预设（组合档） | 一个 preset = sandbox 档 + approval 档；`/permission` 切换；`custom`/`auto` 保留名（`dsh-src/packages/interaction/permission-presets/README.md:32`、`:56`） | ⏸ 未移植（本地只有一条固定策略、无 sandbox、无 `/` 命令面 ⇒ **≤1 个旋钮**，§5 第 111 行） | 组合层无处可挂；M3 的 `approval` 档（`auto`/`confirm`/`never`）若落地才凑出第二个旋钮（待拍板 P11） |
| 命令注册表 | `ctx.commands.register()`：`/command [input]` 直接对 agent 执行、**不产生模型消息**；agent 作用域可遮蔽全局同名（`dsh-src/packages/interaction/commands/README.md:32`、`:50`、`:54`） | ✅ **已移植最小面**（2026-09-22，见 §6.23）：`services/agent/commands.py` 的**单层扁平**注册表 + `parse_command()` + `command/run`/`command/done` 成对生命周期；挂点在 `ask()`（命中即执行、**不进模型**；未注册名**静默放行**给模型）；内建 `/compact`、`/permission <档位>`；RPC `agent_command_list` + 面板 `/` 提示 | 本地偏差：无 scope 分层、无附件、**无 `/` 补全弹层**（见 §6.23 偏差表） |

**备份 · 审计 · 撤销**

| 项 | 上游（做法 + file:line） | 本地（现状 + file:line 或「未移植」） | 差异与风险 |
|---|---|---|---|
| 写前备份 | **❌ 上游没有**：fs 写路径无 pre-image；Win32 替换调用显式把 backup 参数传 `null`（`dsh-src/packages/fs/fs-local/src/win32.ts:20`） | ✅ **已落地（2026-09-20/21，本地发明）**：`services/agent/backup.py` —— pre-image 逐文件**原字节**副本 + `<session>/<txid>` 批次**整目录原子落位** + 8 MiB/32 MiB 上限 fail-closed + 5 批/10 会话/64 MiB FIFO + 会话**起点快照** `origin/`（不参与淘汰 = 撤销的稳定 base）；由 `apply.py` 在**任何落盘之前**调用，失败即整批不写 | **方向反转**：上游没有备份，我们设计了 ⇒ 属**本地发明**；已上线 ⇒ 写路径的风险面由「写前备份 + 可撤销」承担，而不是靠审批闸门 |
| 撤销 | **❌ 上游没有**（`dsh-src/packages/fs/**` 内 `undo`/`revert` 无实现命中，仅 win32 替换 API 的形参） | ✅ **已落地（2026-09-20/21，本地发明）**：`backup.restore_batch()`（按批次 pre-image 逐字节写回 + 外部改动保护 sha256，默认 fail-closed；`force=True` 时先兜底再覆盖）/ `restore_session()`（一键回对话起点）/ `undo_step()`·`redo_step()`（栈式撤销与重做，写后镜像 `after/` → `after.zip` 分层）；apply 的失败路径也用它做**整批回滚** | 本地发明 ⇒ 与上游的关系是**补空白**：上游无 undo，本地把「可撤销」做成了写入的**可用前提**（不再靠审批兜底）；`undo`/`redo`/`force_save` 都有 `capability/*` 审计留痕（见下行） |
| 审计 | ✅ **上游有**：模型可见 ⟺ 会话日志可重建（`dsh-src/AGENTS.md`），审批成对落 `approval/asked`/`approval/decided`（`user-approval/README.md:86`） | ✅ 本地同类：会话 JSONL 追加事件、工具调用/结果可回放（`src/memoria/services/agent/session/history.py`）；**写路径审计已落地**（`services/agent/audit.py`）：`capability/apply` / `capability/undo` / `capability/redo` / `capability/force_save` 追加进既有会话 JSONL（log-only、fail-open 但如实）；审批成对事件 `approval/asked` / `approval/decided` 亦已落（`services/agent/approval_bridge.py`，载荷对齐上游 `{id, tool, reason}` / `{id, outcome}`） | 已对齐；**余差**：设计里列的 `capability/backup` **未落地**（代码不产该事件，备份信息由 `capability/apply` 载荷的 `backup` 字段承担） |
| 「读后写」守卫 | `fs-observation-policy`：未读 ⇒ `FS_NOT_OBSERVED`、读后被改 ⇒ `FS_STALE_VERSION`；**不跨会话存活**，resume 后须重读（`dsh-src/packages/fs/fs-observation-policy/README.md:42`、`:126`） | ✅ **2026-09-22 已补**（`services/agent/observation.py` + `tools/kb.py::_observation_block()` 的写闸）：`read_document`/`read_kp` 成功即记 `present@sha256`（读到不存在记 `confirmed absent`），只有 `create_file` 免读；未读 ⇒ `FS_NOT_OBSERVED`、读到过但当时不存在 ⇒ `FS_NOT_FOUND`、读后内容变 ⇒ `FS_STALE_VERSION`；观察**进程内、不跨会话**，写成功后 `_refresh_observations()` 刷新版本（上游 `fs/observed` 同口径） | 原判定：「写能力上线前必须补；否则漏声明 `read_only` 的工具只能靠审批挡，而不是靠状态校验」—— 写机制 2026-09-21 全线放开后这条**已兑现**。语义对照与偏差见 §11 本轮行 |

**技能与命令**

| 项 | 上游（做法 + file:line） | 本地（现状 + file:line 或「未移植」） | 差异与风险 |
|---|---|---|---|
| `storage/*`（非会话持久） | 注册表 + backend + 原子写（`dsh-src/packages/storage/README.md`、`storage-json/src/atomic.ts`） | ❌ 未移植（§5 第 117 行 ⏸ 按需） | 本地无对应需求：会话是 JSONL、配置走既有链路 |
| **`skill` 到底是什么形态** | **声明式目录包 + 渐进披露**：① 落在扫描根的 `<name>/SKILL.md` 或平铺 `<name>.md`（**嵌套 `**/SKILL.md` 不发现**）；② YAML frontmatter 必填 `name`（kebab-case）+`description`，可选 `whenToUse`/`metadata`/`disable-model-invocation`/`user-invocable`；③ **目录与正文两段式** —— 发现只解析 frontmatter 进目录，正文每次 `load` 重读（无需版本/缓存失效）；④ 根表按 rank 排序（**2026-09-22 补全**：`project-dsh`(`.dsh/skills`)=100 / `project-agents`(`.agents/skills`)=200 / `runtime`（进程内注册）=250 / `custom`=300 / `user-dsh`(`~/.dsh/skills`，跳 `.system`)=400 / `user-agents`(`~/.agents/skills`)=500 / `bundled`=600；project 根由**向上找 `.git`** 定出）；⑤ **权限/可见性只表达为两个布尔**：`modelInvocable` × `userInvocable` 四组合，注册表全留；⑥ 模型面由**另一个包** `tool-skill` 提供（`dsh-src/packages/skill/skill-filesystem/README.md:36`、`:38`、`:42`、`:48-54`；`skill/skill/README.md:55`、`:12`、`:32`） | ✅ **规则已落地（2026-09-22，§6.22）**：`services/agent/skills.py`（frontmatter 契约 + 发现 + rank 遮蔽 + 两种渲染）+ 只读工具 `skill`（`tools/kb.py` 文件末）+ 提示词「可用技能」段（`prompt.py`，门控同 `skill` 工具在场且有技能）；来源目录 = `<kb>/.memoria/agent/skills/**`（平铺 `<name>.md` 或目录包 `<name>/SKILL.md`）。**有意不落四块**：目录 watcher、注册表的"层"、持久目录消息、`/name` 用户手势（故 `user-invocable` / `disable-model-invocation` **照上游解析但本地暂无用户入口**） | **规则照搬、结构重落**：上游「渐进披露」的核心 —— **摘要（目录）与正文（load 时才读）两段** —— 本地已同构；差的是它外面那四层脚手架（注册表层 / watcher / 持久目录消息 / 用户手势），本地没有对应设施（逐条理由见 §6.22 偏差表） |

**其它差距**

| 项 | 上游（做法 + file:line） | 本地（现状 + file:line 或「未移植」） | 差异与风险 |
|---|---|---|---|
| 工具注册与扩展点 | `defineTool`（name/description/parameters/**output/render**/execute）注册即进 prompt；管线 `tools/pre-execute` waterfall → `guard` 单调守卫 → `tools/execute` → `tools/post-execute` → `tools/result`；`restrict` 掩码按 agent 收窄（`dsh-src/packages/core/tools/README.md:32-58`、`:28`、`:81`、`:85`、`:103`） | ✅ 已移植核心：`Tool` dataclass（`.../tools/registry.py:102-118`）+ `invoke` 管线（`:226-305`，含参数校验、审批、错误归一）；❌ 未移植：output/render/展示、`restrict` 掩码、多事件瀑布、PTC mode | 够 M1/M2；**扩展点缺失** ⇒ 第三方加工具时没有收口处，只能改 `registry.py` 本体 |
| 模型可见 ⟺ 落盘 | dsh 硬规：任何进模型请求的内容必须能从会话日志重建（`dsh-src/AGENTS.md`） | ⏸ **有意例外 3 处**：时间上下文、模型切换告知、跨会话引用快照均「只进本轮请求、不落盘」（`docs/conventions/docs-management.md:143`、`:150`、`:151`） | 回放无法重建当轮真实输入；每处都已登记理由（护读路径成本），但汇总看是**成体系的偏差**，值得单列一节复核 |
| 工具结果有界 | 上游处处设界（read 三重 cap、glob/grep cap、session-query cap） | ✅ 本地也有界：`DEFAULT_TOP_K=5` / `MAX_BODY_CHARS=20_000` / `MAX_FILES_IN_OVERVIEW=200` / `MAX_ISSUES_IN_REPORT=20`（`.../tools/kb.py:64-71`）+ 错误文本归一（`registry.py:57-63`） | 已对齐；唯一空隙：`read_kp` 的正文片段无独立字节上限（只受 KP 范围约束，`kb.py:341`） |

**① 已完全移植的**：上游**读面四工具**（`read` 的行窗分页 → `read_document` 的 `offset`/`limit`；`glob`；`grep`；`read_image` 的参数与校验，2026-09-20 §6.16；读图**能力**归未来多媒体「眼睛」插件）；`@路径` 文件引用（含门控与「读过前不得声称看过」）；跨会话引用 `dsh-session:`（语法逐字对齐，偏差已登记）；时间上下文文本语义；库内指令文件注入；审批语义（`ask`/`never`/fail-closed/分发前询问）；工具注册表与「失败也是结果」的错误归一。

**② 本地替换了上游模型的**：① **写面** —— 上游是 `write`/`edit` 工具直接落盘，本地改为 **plan + 编译器 + 唯一写者**（`agent-capabilities.md:75`、`:223`），理由是「禁止 silent 写入」红线要求写路径可枚举、可审计；② **沙箱** —— 上游用内核级三档隔离，本地改为**声明式 `permissions` + realpath 前缀校验**（`agent-plugin-design.md:147`），理由是不引入执行面；③ **引用体系** —— 上游只有路径级 mention，本地另造 `[[id]]` 与 `文件:行号` 两种库内引用（`markdown-form-std.md:16-19`、`prompt.py:270`）。

**③ 我们完全没设计 / 没移植的（gap 清单；2026-09-22 重刷）**：**读面** `read` 分页、`glob`、`grep` 已于 2026-09-20 移植（§6.16）⇒ 读面**无缺口**（图片不算读面缺口：缺的是**多媒体「眼睛」插件**）；**会话查询家族 5 个工具**已于 2026-09-20 齐备（§6.17；偏差表逐条登记仍未移植的过滤器、`surfaces`、调用方会话身份与 `parentSession` 数据源）；~~**写面** 备份与撤销（有设计未实施）、「读后写」版本守卫、行/块级编辑 op~~ **写面已全部落地（2026-09-20/22）** —— 备份与撤销（`services/agent/backup.py`）、读后写版本守卫（`services/agent/observation.py`）、行/块级编辑 op（`COMPILED_OPS` 11 个，含 `upsert_block` / `insert_image_ref`）与文件级 op（`create_file` / `rename_file` / `delete_file` / **`move_file`**（2026-09-22 补，见 `agent-plugin-design.md` §7 2.6 + §8 依赖表：R2 的"文件相对引用"按**拦**落地））；**把关** 沙箱（**有意不吃**）、~~权限预设组合档~~（**已落地 2026-09-22**）、命令注册表（**仍未移植，但消费方已出现**）；**技能** 的**规则面已于 2026-09-22 落地**（§6.22：frontmatter 契约 + 目录/正文两段式 + 调用策略 + `skill` 工具 + 提示词目录段）—— **仍缺** watcher / 注册表层 / 持久目录消息 / `/name` 用户手势，且能力插件契约本体 `capabilities.json` 仍零命中；**其它** 工具管线的瀑布/守卫/掩码扩展点、`ask_user` 提问面（均未移植）。其中 **「备份 + 撤销」与「沙箱」是本表唯一两处「本地与上游方向相反」的项**：前者我们比上游**多做且已上线**了一层（上游无 pre-image/undo），后者我们主动放弃了上游的一层（不引执行面）。

---

## 6. M1 切片：应用内对话 + 读库问答（竖切，只读）

### 6.1 能力边界

- **有**：应用内对话框 →（可选）检索知识库 → 远端模型 → 带 `文件:行号` 锚点的回答；会话可持久化、可回溯；密钥本地引用；出网开关。
- **无**：不写库（无 `*.md` / `.memoria/**` 写入）、不执行命令、不联网检索（除模型端点）、不做压缩与长会话优化。

### 6.2 需要的上游语义清单（文件级，按包）

| 上游 | 取什么 |
|---|---|
| `packages/llm/llm` | provider 中立调用接口（请求/流式/用量/取消） |
| `packages/llm/llm-pi-ai` | **OpenAI 兼容端点**适配（用户可配 base_url + key） |
| `packages/llm/llm-retry` · `token-meter` | 重试/退避、token 计量 |
| `packages/core/agent-loop` | 单轮与多轮循环、工具调用回填、终止条件 |
| `packages/core/system-prompt` | prompt 组装（含工具描述、指令文件注入位） |
| `packages/core/tools` | 工具注册表 + JSON schema + 调用/错误语义 |
| `packages/core/session` · `scope` | 会话与作用域最小面 |
| `packages/session/session-persistence(-jsonl)` · `session-format` | 只取**当前**格式的 jsonl 读写 |
| `packages/context/agent-instructions` | 指令文件发现与注入 |
| `packages/interaction/user-approval` · `tool-ask-user` | 审批/提问（无应答 = 拒绝） |
| `packages/credentials/credentials-local` | 本地密钥引用 |

### 6.3 建议的 Python 落点（待批 P1）

```
src/memoria/services/agent/
├── __init__.py
├── loop.py            ← core/agent-loop 语义
├── prompt.py          ← core/system-prompt
├── approvals.py       ← interaction/user-approval + tool-ask-user（fail-closed）
├── credentials.py     ← credentials/credentials-local
├── llm/               ← llm/llm + providers/openai_compatible.py + retry.py + usage.py
├── session/           ← session 持久化（jsonl）+ 投影最小面
└── tools/             ← 只读工具：search / read_doc / graph / validate（复用既有 services + CLI --json 同源）
```

- 前端：`src/memoria/ui/static/app/js/agent-panel.js` + i18n 键 `agent.*`；RPC 走既有 `ui.py` 面少量新增方法（**不改**既有 93 个方法语义）。
- **契约单一事实源不变**：提示词/规范仍以 `.memoria/agent/**` 与 `resources/agent-prompts/**` 为准，移植来的 `context/agent-instructions` 只负责"发现并注入"，不另立副本。

### 6.4 验收（M1）

| 层 | 判据 |
|---|---|
| 静态 | `py_compile` 全部通过；前端 `node --check`；i18n 扫描 `rows=0` |
| 单测 | provider 适配用**本地假端点**（不联网）；循环/工具/审批各有单测；`python -m pytest tests/agent` |
| 红线 | 断网可用（除模型调用）；密钥只落在本地配置且不出现在日志；出网可一键关 |
| **无写入** | 跑完一轮对话后 `git status` 干净（`.memoria/**` 无变化） |
| 真机 | 应用内提问 → 回答带 `文件:行号` 锚点；关掉出网开关后对话明确报错而非静默降级 |

### 6.5 M1a 实施记录（2026-09-17：只吃 `llm` 包，已落地）

**新增文件**（未改任何既有文件）：`src/memoria/services/agent/__init__.py`、`services/agent/llm/{__init__,types,errors,config,provider,retry,usage}.py`、`llm/providers/{__init__,openai_compatible}.py`、`scripts/agent_llm_smoke.py`（可复用冒烟工具，`--mock` 离线可跑）、`tests/test_agent_llm.py`（21 例，全离线）、仓库根 `THIRD_PARTY_NOTICES.md`。

**验收证据（实施者与本人各自复跑）**：

| 命令 | 结果 |
|---|---|
| `python -m py_compile` × 12 新文件 | **12/12 OK** |
| `python -m pytest tests/test_agent_llm.py -q` | **21 passed**（5.6s） |
| `python scripts/agent_llm_smoke.py --mock` | 流式回答 + `[usage] prompt=36 completion=9 total=45 estimated=no` + `[finish] reason=stop` |
| 禁用依赖扫描（`httpx`/`requests`/`openai`/`aiohttp`） | **0 命中**（纯标准库） |
| 文件头来源注释 | **12/12** 含上游包 + pin commit + 许可 |
| `git status` | 只有新增未跟踪文件，无既有文件被改 |

**语义偏差与取舍（上游 → 本地）**：① 同步生成器而非 async、**无取消面**（M1 无长跑需求；UI 阻塞留待接入应用层）；② 流式**只在尚未产出事件时重试**，已投递分片后失败以带 `failure` 的终止事件结束、**不重放**；③ `llm-pi-ai` 只取 OpenAI 兼容分支，手写 HTTP + SSE（不引其 SDK），不发 `stream_options.include_usage`、只取 `choices[0]`；④ 内容块收敛为纯文本；⑤ 未移植 `llm-retry` 的 `always` 模式，新增 `total_timeout_s`；⑥ `token-meter` 只做计量、无会话回放；⑦ 配置查找顺序 `MEMORIA_AGENT_CONFIG` → `MEMORIA_CONFIG_DIR` → 仓库根 `config/`（**发布包形态需靠 `MEMORIA_CONFIG_DIR` 覆盖**，接入应用层时对齐）；⑧ 本地网关允许不带密钥发送（兼容自建/回环端点）。

**未实测**：真实远端端点（用户本地自测）、`stream_options` 支持度、端点是否随流返回 usage。原始侦察与逐文件对照见 `artifacts/dsh-port-llm/notes.md`（该目录为临时区）。

> 上游 `llm/*` 四行（见 §5）**已落地**；下一步按 §6.2 继续吃 `core`（loop/system-prompt/tools/session）。

### 6.6 M1b 实施记录（2026-09-17：吃 `core` + `session` + `context` + `interaction`，已落地）

**新增文件**（11 个 / 2,236 行；未改任何既有文件）：`services/agent/{loop,prompt,approvals,ask}.py`、`services/agent/tools/{__init__,registry,kb}.py`、`services/agent/session/{__init__,store}.py`、`scripts/agent_ask.py`、`tests/test_agent_loop.py`。

**验收证据（实施者与本人各自复跑）**：

| 命令 | 结果 |
|---|---|
| `py_compile` × 13 新文件 | 全过 |
| `python -m pytest tests/test_agent_loop.py tests/test_agent_llm.py -q` | **33 passed** |
| `python scripts/agent_ask.py --mock --kb <库副本> "这个知识库大概有什么内容？"` | 假 provider 先发 `search_kb` → 带锚点结果 → 最终答案；`[stop] reason=final-answer iterations=2`；`[anchors] rl-intro.md:13 / deep-learning.md:19 / supervised.md:41 / …` |
| **零写入**（运行前后逐文件 `mtime_ns + size` 对比） | 差异**只有** `.memoria/agent/sessions/<id>.jsonl`；原 `docs/example/showcase` 未被触碰；jieba 词典缓存被重定向到系统 temp（日志可见） |

**语义偏差与取舍（上游 → 本地）**：① **`max_iterations` 默认 0 = 无上限**（2026-09-22 改正：原为本地新增的 8；人「怎么有连续调用工具的 8 轮上限，上游都没有」⇒ 回归上游口径 —— 上游 README 明说"没有内置轮次预算"，失控靠用户取消；本地保留 `>0` 时的硬上限能力给测试/特殊场景，另留一条 `UNBOUNDED_ITERATIONS` 的防御性出口）；未移植并行工具、取消信号、runtime context、请求 header 冻结；② 工具错误统一 `Error: <msg> (<CODE>)`（`UNKNOWN_TOOL`/`INVALID_ARGUMENTS`/`DENIED`/`TOOL_FAILED`），只支持 JSON Schema 子集；③ 会话格式自持 `SESSION_FORMAT_VERSION=1`，**与上游 v3 不互通**（未移植 zstd / v0→v3 迁移链 / 跨进程锁 / 崩溃 closer）；④ 指令文件注入进 **system 段**（而非会话消息序列 ⇒ 不回放、不可压缩）；⑤ 审批比上游更严：**只读免审批、写类一律拒绝**（fail-closed），`ask_user_question` 未注册（M1 无问答 UI）；⑥ **只走 lexical 检索**（embedding 需 torch + 权重，与离线优先冲突）；⑦ 零写入靠"**重定向 + 抑制**"4 个库内写点（jieba 缓存 / lexical 缓存 / search_aux / manifest 保存）——属本地新增机制，**将来新增写点必须同步维护该清单**（已写进 docstring）；⑧ `credentials` 不单独实现（`llm/config.py` 已覆盖，M3 需多凭据时再评估）。

**未实测**：真实远端端点（用户本地自测）；真实库上的检索召回质量。

> M1 后端竖切至此打通（提问 → 检索 → 带锚点回答 → 会话落盘）；剩余 M1 部分为**前端对话面板 + 出网开关**，M2 为 compaction 与 session-query。

### 6.7 M2 上半实施记录（2026-09-18：吃 `context/file-reference`，已落地）

> 用户拍板：**先补完上下文引用**（M2 的四块里最小的一块）。compaction 的落盘口径同时拍板为「持久化进会话 JSONL」——见 §8 表下注。

**范围界定（先摸清上游才敢动手）**：`context/file-reference` 只做两件事 ——
① 一段**固定的模型可见说明**（`FILE_REFERENCE_PROMPT`），且**只在 `read` 工具在场时注入**；
② 给编辑器用的路径补全服务（`file-reference-local` / `WorkspaceFileSearch`）。
**它不把被引用文件的内容塞进请求** —— 内容仍由模型自己用读取工具取。
故本块很小：本地只吃 ①，并**顺带修掉前端 `@` 语法的两处保真缺口**（下）。

**改动**（2 个既有文件 + 1 个测试文件，无新增模块 —— §5 映射表里本行「本地落点」原本就是 `—`）：

- `services/agent/prompt.py`
  - 新增常量 `FILE_REFERENCE_SECTION`：上游 `FILE_REFERENCE_PROMPT` 的**逐条中文落法**，四层语义一条不少 —— ① `@` 前缀 token 是用户**明确圈定**的库内路径；② 尾斜杠＝目录；③ 其余＝文件，需要时用 `read_document` 读取，**在真正读过之前不得声称已经看过**；④ `@"..."` 表示含空格。
  - 新增小工具 `_has_tool()`；`build_system_prompt()` 在**工具段之后、回答要求之前**按上游门控注入（**仅当 `read_document` 在场** —— 对齐上游 `ctx.tools.get('read') === undefined ? '' : FILE_REFERENCE_PROMPT`：模型没有读取手段时，教它"去读"没有意义）。
  - **删除**今天早些时候临时塞进「基础身份」段的那一行（被独立段落取代）。
  - 模块来源注释由两个上游包扩为**三个**（新增 `packages/context/file-reference`）。
- `ui/static/app/js/agent-panel.js`
  - `MENTION_RE` 换成上游 `activeAtToken` 语义的**四分组式**（前导 / 完整 token / 带引号路径 / 裸路径）。
  - 新增 `formatMention()`（上游 `formatFileMention` 语义）；`linkifyUser()` 按新分组重写；`insertMention()` 改用它生成 token。
- `tests/test_agent_loop.py`：新增 `test_system_prompt_gates_file_reference_section_on_read_tool`（在场含该段 / 不在场不含）。

**修掉的两处前端保真缺口（旧实现是真缺陷，不是优化）**：

1. **邮箱误判**：旧 `MENTION_RE`（`/@([^\s@]+)/g`）没有"token 开头"约束 ⇒ 用户消息里的 `a@b.com` 会被**误渲染成引用 chip**。上游 `activeAtToken` 明确规定 `@` 须为行首或前导空白。
2. **含空格路径**：旧实现完全无法表示含空格的路径 —— 我当时把它写进文档当作"与 `ANCHOR_RE` 同口径的已知限制"。上游有 `@"..."` 形式专治此事，本轮补上（该"已知限制"在 01 篇已作废）。

**语义偏差与取舍（上游 → 本地）**：

- 上游那段是**英文**且要求"逐字固定"；本地按仓库既有口径**落为中文**（与其余 5 个段落语言一致），**上游英文原文留在 `FILE_REFERENCE_SECTION` 上方注释里**以备对照；
- 上游目录条目是 `list it`（上游有列目录工具），本地**没有**列目录工具 ⇒ 改指 `search_kb`；
- 上游对**目录**用 `@"dir/`（**留开引号**，便于编辑器继续逐级下钻），本地交互是"选中即完成" ⇒ **闭合**引号（`@"dir with space/"`），让消息文本良构；
- 上游的路径补全服务（`WorkspaceFileSearch`，387 行 fuzzy 路径搜索）**不移植**：本地引用由文件树拖拽产生，不需要 `@` 触发的补全弹层。若将来要 `@` 补全，可按需再吃该包；
- **未**顺带吃 `time-context`（注入当前时间）与 `session-reference`（跨会话引用）—— 两者同属 M2 引用类，留作后续小块。

**验收证据**：

| 手段 | 结果 |
|---|---|
| `py_compile` / `node --check` | 全过 |
| `pytest -q` | **81 passed**（+1 例门控测试） |
| harness 浏览器实测（8642；`MEMORIA_CONFIG_DIR` 指向临时目录隔离；先经 RPC 置 `agent_save_config(enabled=true, base_url=http://127.0.0.1:9/v1)`，使"发送"能走到气泡渲染） | 一条含 `@a.md` / `@"docs/IELTS vocab.md"` / `@"dir with space/"` / `a@b.com` / 裸 `@` / 行首 `@line-start.md` 的消息 ⇒ **4 个 chip**：`data-agent-file = ["a.md","docs/IELTS vocab.md","dir with space","line-start.md"]`、`data-agent-dir = [null,null,"1",null]`；`a@b.com` 与裸 `@` **保持原样、未被识别**。插入侧合成拖拽载荷：`docs/IELTS vocab.md`→`@"docs/IELTS vocab.md" `、`dir with space`→`@"dir with space/" `、`plain.md`→`@plain.md `、`docs/example`→`@docs/example/ ` |
| 依赖面 | 纯标准库 / 纯浏览器原生 API，**零新依赖** |

**未实测**：真实模型端点下该段落的实际引导效果（只做静态 + 单测 + 渲染核对，未调真实模型）；真实鼠标拖拽手势。

**文档**：`reference/agent-guide/01` §2.4 两行（chip 渲染 / 拖拽插入）+ §5 坑 17 重写 + §6/§7 按实测重取；`10` §2.15 段落顺序 + §6 新增「系统提示组装」行；`conventions/docs-management.md §4.2` 登记。

### 6.8 M2 compaction 实施记录（2026-09-18：吃 `compaction/compaction` + `compaction-basic`，已落地）

> 用户拍板落盘口径 = **持久化进会话 JSONL**（见 §8 表下注）。**读码后更正一条**：本条**不需要**
> bump `SESSION_FORMAT_VERSION` —— 理由见下。

**范围界定**：上游 `compaction/` 有 5 个子包，本地只吃两个：

| 上游包 | 吃否 | 理由 |
|---|---|---|
| `compaction`（接缝 / 不变量 / 工具配对） | ✅ | 切割点平衡与 fail-closed 判据的核心语义 |
| `compaction-basic`（区域选择 + 摘要器） | ✅ | 阈值/保留比例、8 段骨架、KV 前缀对齐 |
| `compaction-tool-result-pruner` | ❌ 留后（**2026-09-19 已由 §6.10 补上**） | 免模型的旧工具输出裁剪，价值独立、可单独落地 |
| `compaction-image-offload` | ❌ | 本地无图片内容块 |
| `command-compact` | ❌ | slash 命令，M1 已定不做（P5） |

**改动**（1 个新模块 + 4 个既有文件 + 1 个新测试文件）：

- **新增 `services/agent/compaction.py`**（语义移植自 `compaction/{compaction,compaction-basic}`）：
  - 常量 `COMPACT_THRESHOLD_RATIO = 0.8` / `RETAIN_RATIO = 0.16`（上游 `config.ts:20-23` 同值）、
    `SUMMARY_MAX_TOKENS = 8192`（同上游默认）、`SUMMARY_RETRY_POLICY`（`max_retries=1`，对齐上游
    `compactionRetries` 默认 1）；**本地新增** `MIN_SPAN_CHARS = 2000`；
  - `COMPACTION_INSTRUCTION` = 上游 8 段骨架（Primary Request…Critical Context）的**中文落法**：
    段名与顺序、以及四条规则（逐字保留确切路径/命令/错误串、忠实记录用户纠正、不得提及本次压缩、
    只输出正文且不调用工具）+「旧 checkpoint 要**合并**不要照抄」一条不少；上游英文原文留在上方注释；
  - `CHECKPOINT_PREAMBLE` + `SUMMARY_OPEN_TAG`/`CLOSE_TAG` + `frame_summary()`（上游 `frameSummary`）；
  - `balanced_cuts()` = 上游 `tool-pairing.ts::toolPairingBalancedBefore` 的折叠语义（未闭合工具调用数）；
  - `select_span()`：尾部逐字保留 ≥ `retain_chars()` → 切割点必须平衡 → 尽量多压 → 两条本地下限
    （覆盖量 ≥ `MIN_SPAN_CHARS`、区间内至少一条 `user/message`）；区间恒为**前缀**；
  - `summarize_span()`：**同一份 system + tools + 被覆盖区间消息**，指令**只在最后**（上游注释给的理由
    是复用 provider 的 KV 前缀缓存）；fail-closed：无终止事件 / `error` / `aborted` / `max-tokens` /
    返回工具调用 / 正文为空 → `CompactionError`。
- `session/history.py`：新增事件类型常量 `COMPACTION`、`conversation_events()`、`replay_events()`；
  `_compaction_plan()` + `_replay(skip=/emit_at=)` —— 被覆盖的 seq 全部跳过，并在**区间最旧那条 seq 的
  位置**出一条摘要 `user` 消息（时序仍在原处）；`build_history()` 先应用压缩、再做兜底截断。
- `ask.py`：`build_loop()` 新增可选 `registry` / `system`（预置则不就地重建，省略时行为不变）；
  `ask()` 在追加本轮 `user/message` **之前**调 `_compact_if_needed()` —— 超预算才压，且**失败不打断
  提问**（`summarize_span()` 自身 fail-closed，这里只记 warning、按未压缩历史继续）；压缩成功即
  **重新回放**，让本轮请求用上摘要视图。
- `loop.py`：`_usage_payload()` 提为公开 `usage_payload()`（压缩事件与 `loop/end`、`AskResult.usage`
  共用同一用量形状，避免第三份拷贝）；`usage_report.py` 的文档引用同步。

**为什么不动 `SESSION_FORMAT_VERSION`（更正 §8 下注里我先写的那句）**：`compaction` 是**纯追加**的
记录类型，且三个既有读者对未知 type 都是**跳过**而非报错 —— `history._replay()` 落到未知 type 就
`index += 1`、`conversation_messages()` 只认 user/assistant、`usage_report` 只认 `loop/end`。故旧版本
读新文件会**降级为「没有压缩」**（把被覆盖区间逐字重发），既不误读也不崩 —— 正等价于上游要求的
`ignorable: true` 语义。按上游规则（只有**结构**变更才 bump），本变更不 bump。

**验收证据**：

| 手段 | 结果 |
|---|---|
| `py_compile`（新模块 + 4 改动文件） | 全过 |
| `pytest -q` | **104 passed**（原 81 + 新增 **23** 例 `tests/test_agent_compaction.py`） |
| 覆盖点 | 区域选择（工具配对切割点 / 尾部逐字保留 / 最小覆盖量 / 必须含用户消息 / 尽量多压）；回放（原位替换、链式只出最新那份、无效记录不吞事件、**工具配对完好**、可关压缩取原始视图）；摘要器 fail-closed 六例（error / aborted / max-tokens / 空正文 / 工具调用 / 取消）+ 请求形状（指令在最后一条 user、对话前缀原样保留）；端到端（长会话自动压缩并落 `compaction`、主回合请求**不再含被覆盖旧料**、**压缩失败照常答题**、短会话一次多余调用都不发、**仅追加**（既有记录逐条不变 + seq 连续 + 仍是「一行一 JSON」）） |
| 依赖面 | 纯标准库，**零新依赖** |

**语义偏差与取舍**：① 阈值/保留由「上下文窗口比例」改为**字符预算比例**（本地无 context window
概念、也不内嵌权重）；② 不移植上游 `compaction/start` + `compaction/end` 事务对与锁 —— 单写者 +
仅追加，一条记录足够；③ 上游记 `shadowedSeqs` + `shadowedTokenCount`（启发式 token 价），本地记
`shadowed`（seq）+ `shadowed_chars`（字符，与 `event_chars()` 同口径）；④ 本地新增两条下限。

**已知缺口（本轮未做）**：① **摘要调用的用量不进 benchmark** —— 它记在 `compaction.usage`（与
`loop/end` 同形状），但 `scripts/benchmark/usage/report_usage.py` 只扫 `loop/end` ⇒ 报告**不含**压缩
开销（要做就是给报告加一类行）；② `compaction-tool-result-pruner` 未吃（**2026-09-19 已由 §6.10 补上**）；③ 无手动触发（上游 `/compact`，
本地方案 P5 已定不做 slash 命令）。

**未实测**：真实模型端点下的**摘要质量**与「压缩前后 A/B」（§8 的 M2 门禁 —— 上下文长度易量，
**回答可回溯性**需真人用真实库对照）。

**文档**：`reference/agent-guide/10` 会话格式表新增 `compaction` 事件 + 回放口径；`conventions/docs-management.md §4.2` 登记。

### 6.9 M2 session-query 实施记录（2026-09-19：吃 `session-query/session-query` + `session-query/tool-session-query`，已落地）

**范围界定**：上游 `session-query/` 有 4 个子包，本地只吃两个（且第一个只吃其中两个文件）：

| 上游包 | 吃否 | 理由 |
|---|---|---|
| `session-query`（抽取 / 过滤 / 语料 / 游标 / 可观测性的接缝） | ✅ **部分** | 只吃 `extraction.ts`（语义文本抽取）与 `filters.ts`（字面量匹配编译）；`corpus` / `cursor` / `tracing` / `observation` 不吃 |
| `tool-session-query`（把检索暴露成工具） | ✅ | 对应本地新工具 `search_sessions` |
| `session-query-sqlite`（SQLite FTS 索引 + 分页游标） | ❌ | 本地不引索引：随库走的 jsonl 就是语料，纯标准库实现 |
| `session-log-export`（导出 UI + 客户端组件） | ❌ | 导出界面，本轮不做 |

**改动**（1 个新模块 + 1 个既有文件 + 1 个新测试文件）：

- **新增 `services/agent/session/query.py`**（约 370 行，语义移植自 `session-query` 的 `extraction.ts` + `filters.ts`）：
  - **语义文本抽取 `event_text()`**（query.py:125-146）：只有"第一方语义事件"贡献可检索文本 —— `user/message`→`text`、
    `assistant/message`→`content` + 各 `tool_calls` 的 `name`/`arguments`、`tool/result`→`content`；
    `tool/call`/`step/*`/`loop/end`（`_STRUCTURAL`，query.py:108）与**未知 type 一律空**（上游口径：未知事件不因
    载荷里恰好有字符串就变成可检索）。**本地新增一行**：`compaction`→`summary` —— 被压缩掉的旧对话只剩这份摘要，
    不检索它等于把那段对话从检索面抹掉（上游无该事件，属本地扩展）。
  - **字面量匹配 `compile_text_pattern()`**（query.py:149-159）：查询被当**数据**而非可执行语法 —— 按空白切词、
    **逐词 `re.escape`**（杜绝正则注入）、词间以 `\s+` 连接（**空白弹性**）、整条 `IGNORECASE | UNICODE`；
    空查询抛 `SessionQueryError`。
  - **摘要窗 `snippet()`**（query.py:162-176）：空白先折叠成单空格，取**首个匹配点前后各 `SNIPPET_WIDTH(80)` 字符**，
    被裁剪的一侧补 `…`。
  - **过滤子 `_Filters`**（query.py:202-227）：沿用上游「**子句间 AND、子句内取值 OR**」；本地实现
    `types`/`time`/`seq`/`text` 四类（上游另有 `surface`，本地无"表面"概念 —— 压缩覆盖由 `history` 在回放层处理）。
  - **有界化**（query.py:230-236、常量 93-105）：单份文件 `SESSION_QUERY_MAX_BYTES = 2 MiB`（与
    `history.SESSION_SCAN_MAX_BYTES` 同值同意图）、跨会话扫描份数 ≤ 500、单页命中 ≤ 200；`limit=0` **合法**（返回空）；
    负数/非整数 fail loud。
  - **性能**：`_prefilter_ok()`（query.py:239-246）在**不解码的字节串**上做 ASCII 小写化后的逐词存在性检查，
    全词命中才解析该文件（`bytes.lower()` 只影响 ASCII A–Z，故"判否"是安全的）；`search_sessions()` 复用
    `list_sessions()` 已 `stat` 到的 `size`，不重复 stat。
- `services/agent/tools/kb.py`：`KB_TOOL_NAMES` 增 `search_sessions`（kb.py:73-80）；新增
  `_search_session_history()`（kb.py:446-482）与工具声明（kb.py:566-592，`query` 必填 / `limit` 1–20、默认 5）。
  **命中以「会话 `<id>` 第 N 条」标识、明确不产生 `文件:行号` 锚点** —— 那是文档引用的形状，混用会让模型把
  对话记录当成库内出处；无命中时提示「这里检索的是**历史对话**，找资料请用 `search_kb`」。全工具只读。
- `tests/test_agent_session_query.py`（**28 例**）；`tests/test_agent_loop.py:224` 的硬编码工具清单改为
  `list(KB_TOOL_NAMES)`（同一文件新增的不变量测试 `test_kb_tool_names_match_built_tools` 正是防这类漂移）。

**语义偏差与取舍（上游 → 本地）**：

1. **语料不同**：上游是 `ctx.sessions`（live 优先）+ SQLite FTS；本地没有 live 会话注册表、也不引索引，
   语料就是**磁盘上的会话文件**（`list_sessions()` 已按 `modified_at` 倒序）。
2. **排序口径改为「最近聊过的先出」**：上游按「该会话最强匹配事件」做**相关性**排序；本地没有相关度评分器
   ⇒ 组间按 `modified_at` 倒序、组内按 `seq` 升序。已登记为偏差。
3. **`snippet` 的窗口算法未逐字对齐**：上游只说"匹配点附近的纯文本摘录"，本地实现为前后各 80 字符 + 省略号。
4. **不移植**：不透明游标 `SessionSearchCursor`（分批给 SQLite 分页用，本地用显式 `limit`）、
   `lineage`/`trace`（会话谱系与事件溯源，本地无 fork/派生会话）、`tracing.ts`/`observation.ts`（宿主可观测性）。
5. **预筛的大小写折叠只对 ASCII 成立**：非 ASCII 的大小写折叠只在解析后生效；这只影响"要不要解析该文件"的
   性能判断，**不影响命中正确性**（预筛判否只会跳过文件，而可解析的命中必然先在字节层命中过）。
6. **`capped` 事实不进 `search_session()` 的返回** —— 需要它的调用方用 `history.summarize_session_file()`
   （会话列表已在用）。

**验收证据**：

| 手段 | 结果 |
|---|---|
| `py_compile`（新模块 + 1 改动文件） | 全过 |
| `pytest -q` | **132 passed**（原 104 + 新增 **28** 例 `tests/test_agent_session_query.py`） |
| 覆盖点 | 抽取规则表（语义事件取值正确；结构性/未知 type 返回空；`compaction` 取 `summary`；`tool_calls` 的 name+arguments 入文；空段被丢）；字面量匹配（正则元字符与 `\d`/`.*` 当字面量、空白弹性、大小写不敏感 + Unicode、空查询报错）；摘要窗（命中居中、两侧省略号、空白折叠）；会话内检索（按 `seq` 升序、`types` 白名单子句内 OR、`time`/`seq` 区间、**`limit=0` 返回空**、会话不存在返回空、非法 limit/会话 id 报错）；跨会话（按 `modified_at` 倒序分组、`sessions_limit` 夹紧、`hit_limit` 每会话上限、`best` = 最小 `seq`、`title`/`turn_count` 来自 `summarize_session_file`）；字节预筛（ASCII 大小写差异仍能命中）；工具面（`KB_TOOL_NAMES` 与 `build_kb_tools()` 实际工具集**逐项一致**、只读、命中写成「会话 `<id>` 第 N 条」**且不含 `文件:行号`**、空 query 报错、无命中时提示改用 `search_kb`、`limit` 生效） |
| 依赖面 | 纯标准库，**零新依赖** |

**修掉的一个真 bug**：`limit=0` 原本仍返回 1 条 —— 上限判断从 `hits.append` **之后**移到**之前**
（query.py:286-287）；新写的 `test_search_session_respects_limit` 逮到它。

**已知缺口（本轮未做）**：① **会话标题**（`session/title*` + 投影）仍是 M2 剩余项；② `session-reference`
（跨会话引用）未吃 —— 上下文引用目前只支持 `@路径`（文件/目录），不支持引用某个会话；③ 工具面不返回 `capped`；
④ 无相关度排序（见偏差 2）。

**未实测**：真实模型端点下模型**是否会在该用 `search_sessions` 时用对**（工具选择正确性）—— 只做了静态 + 单测 +
工具面形状核对，未调真实模型。

**文档**：`reference/agent-guide/10` §2.15 新增「会话检索工具」条 + 会话事件面补 `compaction` 可检索一行 + §6/§7
按实测重取；`conventions/docs-management.md §4.2` 登记。

### 6.10 M2 工具结果裁剪实施记录（2026-09-19：吃 `compaction/compaction-tool-result-pruner`，已落地）

> §6.8 曾把本包登记为「❌ 留后（价值独立、可单独落地）」—— 本轮补上，故 §8「M2 剩余」相应更新。

**改动**（1 个新模块 + 4 个既有文件 + 1 个新测试文件）：

- **新增 `services/agent/pruner.py`**（约 230 行，语义移植自上游该包 `config.ts` + `types.ts` + `index.ts`）：
  - 常量 `PRUNE_MARKER`（上游同名字面量 `\n\n[... tool result middle pruned ...]\n\n` 逐字照抄）、
    `PRUNE_THRESHOLD_CHARS = 8192` / `PRUNE_HEAD_CHARS = 4096` / `PRUNE_TAIL_CHARS = 1024`（同上游默认值）、
    事件类型 `PRUNE = "compaction/prune"`（对齐上游事件名）；
  - `PruneBudgets`（对齐上游 `ResolvedConfig` + `resolveConfig` 的**构造期**校验）：`threshold` 正整数、
    `head`/`tail` 非负整数、**`head` + 标记 + `tail` ≤ `threshold`** —— 最后一条保证裁剪**永不增长**；
  - `prune_text()`（对齐 `pruneContent`）：≤ 阈值返回 `None`（不改），否则取**前 `head` 码点 + 标记 +
    后 `tail` 码点**。码点口径直接是 `len(str)`（Python `str` 无 UTF-16 代理对，等价上游
    `codePointLength()`）；`tail=0` 走显式分支（`text[-0:]` 会把整串当末段的经典陷阱）；
  - `apply_budget()`（回放用）：按**记录里落盘的**预算重建正文；`applied_chars()` = `head+标记+tail`；
  - `prune_plan()`（对齐 `pruneSession` 的候选筛选）：只挑 `tool/result` 且正文超阈值的；**幂等**
    （已有 `compaction/prune` 记录里的 seq 跳过）+ 可传 `skip`（调用方传「被 `compaction` 覆盖的 seq」，
    那些本来就不进请求）；每条记 `{seq, id, chars_before, chars_after, head, tail}`；
  - `prune_records()` / `prune_applied()`：前者取「已裁过的 seq」（幂等判据），后者给回放用的
    `seq -> (head, tail)`（**后写覆盖**；**形状不全的记录整条忽略** —— fail-safe：宁可让模型看到原文，
    也不拿半截预算去切正文）。
- `session/history.py`：新增事件表行 + 「工具结果裁剪回放」小节；`_tool_message()` 接受裁剪表、
  `_replay()` / `replay_events()` 新增 `prune` 参数、`build_history()` 自动应用落盘的裁剪记录；
  新增公开小工具 `compaction_shadowed()`（`_compaction_plan()[1]` 的出口，供裁剪器跳过）。
- `compaction.py`：`event_chars()` 与 `select_span()` 新增可选 `effective_chars`（`seq -> 有效字符数`）
  —— **被裁过的工具结果在日志里仍是原文**，区域选择必须按**有效视图**计量，否则会高估尾部大小、
  把本可逐字保留的轮次也压掉。`effective_chars` 是普通 dict，故 `compaction` 与 `pruner` **零耦合**。
- `ask.py::_compact_if_needed()`：压力确认后**先裁、再压**（对齐上游 `compaction-basic` 的调用位次）——
  1) `prune_plan(events, skip=compaction_shadowed(events))`，有料就落一条 `compaction/prune`；
  2) 重算 `build_history()`，**若已低于阈值就直接返回**（免掉这次摘要调用 —— 上游原话
     *trimming may relieve enough token pressure to skip summarization*）；
  3) 仍超阈值则照常 `select_span(events, effective_chars=...)` + `summarize_span()`，
     且摘要器读**裁剪视图**（`replay_events(covered, prune=prune_applied(events))`）。
  返回值语义由「是否压过」放宽为「**是否落了事件**」（裁剪也算），调用方据此重新回放。

**落盘形状**（单写者 + 仅追加，一条记录覆盖一轮的全部裁剪项）：

```jsonc
{"pruned": [{"seq": 42, "id": "call_1", "chars_before": 30022, "chars_after": 5159,
             "head": 4096, "tail": 1024}], "chars_removed": 24863}
```

**为什么是「一条记录 + 回放期重建」而不是上游的「替换事件 + surfaceOp」**：上游把裁剪做成一次**表面替换**
（追加新 `tool/result` 并 `sourceEventSeqs` 指向原事件，前置 `compaction/prune` 影子定价事件）。本地没有
`Session.surface` / `surfaceOp` 抽象，且**不能为同一个 `tool_call_id` 追加第二条 `tool/result`** ——
回放会把同一调用配成两条工具消息，端点直接 400。故改为「记录 `seq` + 记录实际预算」，由 `history.py`
在回放时**就地**重建。收益与上游等同：原事件**逐字留在日志里**（检索/导出/审计看原文，只有发给模型的
请求用裁剪视图），且因为预算随记录落盘，回放结果**不随默认常量变化而漂移**。

**语义偏差与取舍（上游 → 本地）**：

1. **内容模型退化**：上游工具结果是 `ContentBlock[]`（富块零成本直通、相对顺序不变）；本地是**纯字符串**
   ⇒ 切片作用于整串，无富块通路（M1 只有只读文本工具）。
2. **不移植影子定价**（`shadowedTokenCount`，本地无 token 计量服务）：改用字符量 `chars_before` /
   `chars_after` / `chars_removed`，与 `compaction.shadowed_chars` 同口径。
3. **不移植 `surfaceOp` / `Session.surface`**（见上）；也**不移植**「替换写入失败 ⇒ 整轮同步失败」——
   本地是 fail-open（记不进就按原样继续，与压缩同口径）。
4. **与检索的关系**：`session/query.py` 在**原始事件**上检索 ⇒ 被裁掉的中间段**仍可被搜到**
   （本地取舍：宁可搜得全，也不让裁剪把历史从检索面抹掉）；上游检索走的是裁剪后的表面。
5. **阈值/预算是字符码点不是 token**（上游同款已知限制）；**字素簇仍可能被切开**（上游同款已知限制，
   本地无 locale-aware 分段）。

**验收证据**：

| 手段 | 结果 |
|---|---|
| `py_compile`（新模块 + 4 个既有文件 + 1 个 docstring 追加） | 全过 |
| `pytest -q` | **153 passed**（原 132 + 新增 **21** 例 `tests/test_agent_pruner.py`） |
| 覆盖点 | 纯函数（恰好等于阈值不裁 / 头+标记+尾形状与长度上界 / **`tail=0` 不退化** / 预算非法值 7 例构造期拒绝 / 清单只挑超预算 `tool/result` / 幂等 + 跳过被压缩覆盖的 seq / 畸形记录 fail-safe）；回放（记录就地生效、**原事件逐字保留**、不带裁剪表即原始视图、未知 seq 忽略、**后写覆盖**）；计账（`event_chars` 覆盖表命中/未命中、`select_span` 按有效字符选区间 —— 同组事件在有效视图下由 `(0,4)` 变为 `None`）；端到端（**裁完够用 ⇒ 只发 1 次模型调用**且主回合请求含标记、无被删中段；裁完仍超 ⇒ 照常压缩且**摘要器读到裁剪视图**；预算内一次多余调用都不发；仅追加 + `seq` 连续 + 不落任何 `compaction*`） |
| 依赖面 | 纯标准库，**零新依赖** |

**已知缺口（本轮未做）**：① `shadowedTokenCount` 等 token 侧事实一律不记（本地无计量服务），故「裁剪省了多少
token」只能按字符量近似；② 裁剪**只作用于 `tool/result` 的正文**，不碰 assistant 的 `tool_calls.arguments`
（本地工具参数很短，上游同样不裁）；③ 无可配置入口（预算是模块常量；上游是插件配置项）。

**未实测**：真实模型端点下「裁剪后模型是否仍答得对」（**信息有损**，上游同样列为已知限制）；大规模会话下的
裁剪耗时未做 A/B 计时（纯字符串切片，复杂度线性，但**未实测墙钟**）。

**文档**：见 §11 对应行。

### 6.11 M2 会话标题实施记录（2026-09-19：吃 `session-title` + `session-title-llm` + `session-title-first-prompt-llm`，已落地）

**范围界定**：上游与"标题"相关的有 4 个包 + 通用投影框架，本地只吃三个：

| 上游包 / 设施 | 吃否 | 理由 |
|---|---|---|
| `session-title`（规范化 / 折叠 / 兜底 / 接受与取代） | ✅ | 标题的核心契约：来源优先级、字节限额、控制字符清洗、log-only |
| `session-title-llm`（模型标题的**共享调用策略**） | ✅ | system 提示、JSON 框定、输入/输出/超时限额、finish 判据 |
| `session-title-first-prompt-llm`（首条消息选材 + `first-prompt` 节律） | ✅ | 本地选定的自动节律（见下） |
| `session-title-all-prompts-llm` | ❌ | 每来一句就重算一次标题 —— 本地方针是"能省则省"，不值得每轮多一次调用 |
| `session-projection*`（投影框架 `title` / `titleInput` 单元） | ❌ | 本地不引投影框架：直接**折叠**（`fold_title()`），列表用原始行扫描 |
| `session/title-llm-request`（预派发记录） | ❌ | 上游用它自证"辅助调用的路由与已记录的主请求路由一致"；本地路由就是本轮的 provider/model |
| `rename()`（`source.kind == "user"`） | ❌ | 本地没有改名入口；事件形状保留 `source`，折叠时**不解释**它 |

**改动**（1 个新模块 + 4 个既有文件 + 1 个新测试文件 + 1 处前端一行）：

- **新增 `services/agent/title.py`**（约 470 行，语义移植自上游三个包）：
  - 常量与限额：`SESSION_TITLE = "session/title"`、`TITLE_FALLBACK_MAX_WORDS = 8` /
    `TITLE_FALLBACK_MAX_BYTES = 96` / `TITLE_MAX_BYTES = 120`（上游三限额**必填无默认**，本地取它 README
    示例值）、`TITLE_TARGET_WORDS = 6` / `TITLE_TARGET_CJK_CHARS = 12`（共享调用策略里的"目标长度"）、
    `TITLE_MAX_INPUT_BYTES = 32768` / `TITLE_MAX_OUTPUT_TOKENS = 96` / `TITLE_TIMEOUT_S = 20` + 一次重试；
  - **规范化**（上游 `normalize.ts` 同名模式逐条照搬）：OSC（含未终结尾巴）/ CSI / 其余两字节 ESC 序列、
    非空白 C0/C1 控制字符、**方向与隐形控制字符**全去；空白折叠成单空格；`truncate_title_utf8()` 按
    **UTF-8 字节**截断且**不切开码点**（Python 侧逐字符累加 `len(ch.encode())`）；
  - **合格消息与折叠**：`title_message()`（只认人类 `user/message` 且规范化后非空）→
    `collect_title_messages(events, through_seq=…)` → `fold_title(events)`（最后一条**非空**标题胜出）；
  - `ensure_fallback()`：无标题时按首条合格消息落一条 `fallback`（**零模型调用、零网络**）；
  - `title_system_prompt()` / `frame_messages()`（把选材消息**框成 JSON**，正文无法破坏结构分隔）/
    `generate_title()`（**fail-closed**：无终止事件 / `error` / `aborted` / `max-tokens` / 返回工具调用 /
    **非 `stop` 的终止原因**（含 `content-filter`）/ 正文规范化后为空 ⇒ `TitleError`）；
  - `auto_title()`：`first-prompt` 节律 —— 会话里**恰好一条**合格人类消息时才生成并落 `provider` 标题。
- `session/history.py`：事件表新增 `session/title` 行（**跳过**：标题 log-only，不进消息序列）+ 新增
  「标题」小节；`summarize_events()` 的 `title` 改为**优先取 `fold_title()`**；`summarize_session_file()`
  的**原始行扫描**里另找 `"session/title"` 行、只对**最后一个命中行**解码取 `data.title`（与折叠**同口径**：
  最后一条非空标题），没有标题事件时才回落到「首条提问前 40 字」（M1 行为）。
- `ask.py`：新增两个小函数并接进 `ask()` ——
  ① `_append_fallback_title()`：追加本轮 `user/message` **之后**立刻补兜底标题（对齐上游 `onUserMessage`
  的节律：每条合格消息都尝试、已有标题即跳过）；② `_maybe_generate_title()`：主回合结束后跑**首轮一次**
  的模型标题（`auto_title()`），**被取消的轮次跳过**。两步都 **fail-open**（只记 warning）。
- `ui/static/app/js/agent-panel.js`：`#agent-history` 下拉的标签由 `session.preview` 改为
  **`session.title || session.preview`** —— 原来后端返回的 `title` 字段**根本没被前端用过**，标题做完也是
  白做；这是本次唯一的前端改动（1 行取值，无新文案、无 i18n 变更）。
- `tests/test_agent_title.py`（**31 例**）；`tests/test_agent_history.py` 的
  `test_summarize_and_conversation_view_with_anchors` 补一个标题步骤并改断言（见下）。

**语义偏差与取舍（上游 → 本地）**：

1. **没有异步服务**（最重要的一条）：上游是常驻 `SessionTitleService`，自动生成**从不阻塞主回答**，
   并用 `AbortController` 处理取代/超时/生命周期。本地 `ask()` 是**同步**调用面 ⇒ 标题调用排在**主回合
   之后**（`loop/end` 已落盘）。**代价**：面板的 `done` 会晚一个**极小**辅助调用的时间，且**仅每会话首轮
   一次**；换来的是**没有**引入后台线程池与取代状态机（本地单写者 + 单飞作业，不值得）。
2. **被取消的轮次不生成标题**（**本地新增**，上游无此分支）：用户已喊停，不再多花一次调用。
3. **只吃 `first-prompt`**：不吃 `all-prompts`；因此也不做上游那层「provider 注册表 + automatic 节律」
   抽象，只有一条内联路径。
4. **不吃 `rename()`**：无改名入口；`source` 仍写进事件（`fallback` / `provider`），折叠时不解释它。
5. **不移植投影框架与预派发记录**（见上表）。
6. **折叠加固**：空标题记录**视作没有**（继续用前一条有效标题）—— 上游 `findLast` 会直接采用它；
   本地要求"最后一条**非空**"，且**与列表的原始行扫描同口径**（否则 `summarize_events` 与
   `summarize_session_file` 会给出不同标题）。
7. **本地扩展：标题调用用量记进事件**（`session/title.usage`，形状同 `loop/end.usage`）—— 上游不记。
   与 `compaction.usage` 一样**不进** benchmark（报告只扫 `loop/end`）。
8. `TITLE_TARGET_WORDS` / `TITLE_TARGET_CJK_CHARS` / `maxInputBytes` / `maxOutputTokens` / `timeoutMs`
   在上游都是**必填配置**（库内无默认），本地落为模块常量（默认值即上文）。

**验收证据**：

| 手段 | 结果 |
|---|---|
| `py_compile`（新模块 + 4 个既有文件） / `node --check` | 全过 |
| `pytest -q` | **184 passed**（原 153 + 新增 **31** 例 `tests/test_agent_title.py`） |
| 覆盖点 | 规范化（CSI/OSC/未终结 OSC/两字节 ESC、C0-C1、方向与隐形字符、空白折叠、**按字节截断不切开码点**、非法上限 5 例）；合格消息与折叠（非人类/空白/纯控制字符不合格、`through_seq` 上界、**最后一条非空标题胜出**）；兜底（首条消息前 8 词 / 96 字节、只落一次、已有标题或没有合格消息则跳过）；模型调用（**请求形状**：system = `title_system_prompt()`、单条 user、正文以固定前缀开头且其后是 `[{seq,text}]` 的合法 JSON、`max_tokens = 96`；正常返回带 usage；**fail-closed 七路**（error / aborted / max-tokens / tool-calls / content-filter / 空正文 / 无终止事件）；输入超限与空选材不发请求；`AgentLlmError` 被包成 `TitleError`；取消）；节律（恰好一条合格消息才生成，两条则一次请求都不发）；端到端（首轮落 `fallback` + `provider` 两条且后者带 `usage`、**次轮不再生成**、**被取消的轮次只留兜底**、**标题调用失败不影响问答**、老会话再聊一句补兜底但不做模型标题、**标题永不进模型输入**（主回合请求无标题字样 + `build_history` 不多出消息 + 列表扫描与折叠同口径）） |
| **浏览器实测**（harness `MEMORIA_HARNESS_KB` 指向临时库、`MEMORIA_CONFIG_DIR` 隔离、端口 8645；**不需要模型**：会话文件里的 `session/title` 直接手写） | `/rpc` `agent_sessions_list` 返回 `title = "多层感知机的要点"`（**折叠出的 provider 标题**，不是 `preview` 也不是首条提问）；浏览器里 `#agent-history` 的选项为 `{value: "session-title-demo", text: "多层感知机的要点（1 轮）"}`、`optionCount = 2`、未禁用；`#-agent-dock` / `#agent-input` 均存在（面板已初始化） |
| 依赖面 | 纯标准库 / 纯浏览器原生 API，**零新依赖** |

**顺带修掉的一处"做完也看不见"**：后端从 M1c 起就返回 `title` 字段，但前端一直用的是 `preview`
（首条提问前 80 字）。本次把下拉标签改成 `title || preview`，标题才真正可见。

**已知缺口（本轮未做）**：① **标题调用用量不进 benchmark / 面板状态栏**（只扫 `loop/end`，与 §6.8 同一缺口，
现在多了一处来源）；② 无改名（`rename()`）与"钉住"语义；③ 无 `all-prompts` 节律；④ 不做标题的
`titleInput` 投影缓存（每次折叠走一次事件列表 ⇒ O(n)，本地会话规模无压力）。

**未实测**：真实模型端点下**标题的质量**与语言选择（只做静态 + 单测 + 假 provider + 手写会话文件的浏览器实测；
用户 `config/agent.json` 是真密钥、**刻意不调用**）；真机上"首轮多等一个辅助调用"的实际手感。

**文档**：见 §11 对应行。

### 6.12 M2 收尾实施记录（2026-09-19：吃 `context/session-reference`，已落地）

**范围界定（先读上游四文件才动手）**：`context/session-reference` 上游有 7 个源文件，本地只吃三块的**语义**，
`spill.ts` 明确不吃（见下）：

| 上游文件 | 吃否 | 理由 |
|---|---|---|
| `src/uri.ts`（URI 编解码 / mention 格式化与解析） | ✅ | 语法与规范化规则的唯一事实源 |
| `src/projection.ts`（当前表层投影 + 字节预算保留） | ✅ | 只投影 user/assistant 文本、先丢较早消息再截断 |
| `src/serialization.ts`（标签安全 JSON） | ✅ | `<` → `\u003c`，源文本拼不出定界标签 |
| `src/spill.ts`（完整 transcript 落盘 + 省略通知） | ❌ | 本地无 spill 存储；截断/放弃时**只**出省略通知并写明"未保存" |
| `src/index.ts` / `config.ts` / `types.ts`（服务监听器 / 配置 schema / 类型） | ⚠️ 部分 | 只取"规范化 + 准备 + 渲染"这条纯函数链；**pre-step 监听器**不移植（本地是同步 `ask()`，没有 agent 事件总线） |

**改动**（1 个新模块 + 3 个既有文件 + 1 个新测试文件 + 前端 4 个文件）：

- **新增 `services/agent/session/reference.py`**（语义移植自 `uri.ts` + `projection.ts` + `serialization.ts`）：
  - `SESSION_REFERENCE_SCHEME = "dsh-session:"`；`encode_session_uri()` = scheme + `base64url(JSON.dumps(id))`（无填充）
    ⇒ **任何字符串 id 都能精确往返**；`decode_session_uri()` 只收规范输入（错 scheme / payload 不匹配
    `^[A-Za-z0-9_-]+$` / 解出不是 JSON 字符串 / **重编码与原串不逐字节相等** ⇒ `SessionReferenceError`）；
  - `format_session_mention()`（label 里 `\` 与 `]` 转义）、`parse_session_references()`（正则与上游 `uri.ts:71` 逐字一致：
    **显式 Markdown mention 格式错误即报错**；裸 token 只在 payload 为非空 base64url 形状时才当引用，随后仍按规范化校验）；
  - `list_candidates()`：排除调用方自己、对 id/标题做不区分大小写过滤、**最近修改在前**（本地每库一份会话 ⇒ 上游"按 cwd 亲和度排序"退化为"同库"）；
  - `build_snapshot()`：去重（保首次顺序）、**拒绝自引用**、`max_references ≤ 3`；逐来源经 `conversation_messages()` 投影后
    按字节预算保留（**先丢较早消息、再头尾截断**）、`<` 逃逸、渲染 `## 引用的会话` + 固定警告 +
    `<referenced-sessions>` + 省略通知 `<referenced-session-omissions>`。
- `services/agent/session/__init__.py`：导出新增的 10 个公开名（常量 / 异常 / 8 个函数）。
- `services/agent/ask.py`：`session.append("user/message")` **之前**解析 mention 并建快照；`loop.run()` 收
  `rendered_text + "\n\n" + snapshot`，**JSONL 只落 `rendered_text`**（见下偏差 1）。
- 前端：`js/agent-panel.js` 末尾追加块（会话 URI 编解码 / chip 渲染包装 `linkifyUser` / 历史行「引用」按钮
  + 被引用高亮 / document 级点击委托）；`css/app.css` 末尾追加样式块；`i18n/{zh-CN,en}.js` 末尾各追加 3 键。
- `tests/test_agent_session_reference.py`（**33 例**）。

**语义偏差与取舍（上游 → 本地）**：

1. **不落盘快照**（最重要的一条）：上游把快照作为**第二条 user 消息**持久化进目标会话，使"捕获后的源变更无法改变回放"；
   本地只在 `loop.run()` 的请求里追加，JSONL 里仍是**可读的 `@label` 原文**。**理由**：本地会话文件同时是
   **读取路径的事实源** —— `agent_sessions_list` 以 2 MiB 上限做原始行扫描（去读放大）、`agent_session_load`
   直接把它回放成渲染视图；把几十 KiB 的不受信背景写进去会污染渲染视图、推高扫描成本，也让"列表预览/标题"不再干净。
   **代价**：目标会话的后续轮次不会自动重放该快照（上游会）⇒ **重新 mention 即重新附带**，这就是本地的"重新挂载"方式。
2. **不移植 spill 存储**：上游把被截断引用的完整 transcript 存进 spill 后端并给出 `retrievalHint`；本地无此设施 ⇒
   省略通知里写 `spill: "unavailable"` 并**显式说明"完整 transcript 未保存，被省略内容无法取回"**（不含检索提示）。
3. **投影口径本地化**：上游逐 `assistant/message` 投影并识别 compaction checkpoint；本地用 `conversation_messages()`
   （**每轮一条最终 assistant 气泡 + user 文本**，不含工具）⇒ ① 同一轮的多条中间 assistant 不逐个进快照；
   ② 本地 `compaction` 摘要是"回放期在原位补一条 user 消息"，**`conversation_messages()` 不应用压缩覆盖**，
   故源会话的摘要不进快照、**也没有 checkpoint 概念** ⇒ 保留策略退化为"先丢最旧消息"（上游会跳过 checkpoint）。
4. **来源放不下时放弃该来源、记 `unavailable`**（上游让整次 preparation 失败）：本地是用户面向的问答入口，
   不值得因某个被引用会话过大而整轮失败；实现上"空信封都装不下"才算放弃（头尾截断几乎总能压进预算）。
5. `cwd` / `capturedThroughSeq` 恒为 `null`：本地无 per-session 工作目录、也没有"冻结到某 seq"的捕获概念
   （字段保留上游形状，值如实为 null）。
6. **无自动字节预算**：上游按 `max(65536, floor(contextWindow × 4 × referenceContextFraction))` 估算；本地固定
   `REFERENCE_MAX_BYTES = 65536`（无路由/容量元数据），`max_references` 默认 3 且越限报错。
7. **无 pre-step 监听器 / 无投影框架 / 无游标与谱系**：本地只保留纯函数链，`ask()` 直接调用。
8. **前端是本地新增**：上游把候选发现与 mention 插入交给宿主编辑器（`ctx.remote.sessionReferenceResolver`），
   本地没有这层 ⇒ 最小入口 = 左栏「历史」行内「引用」按钮（插 token、**不切会话**）+ 用户气泡里的会话 chip
   （点击切到「历史」页签并高亮该行、**不载入**该会话）。
9. **解析失败会向上抛**：显式 Markdown mention 的 URI 格式错误（或裸候选非规范）在 `parse_session_references()`
   即 `SessionReferenceError`；`ask()` **未拦截**（对齐上游"格式错误即失败"），是本地的一处已知易踩点。

**验收证据**：

| 手段 | 结果 |
|---|---|
| `py_compile`（新模块 + `session/__init__.py` + `ask.py` + 新测试） | 全过 |
| `pytest tests/ -q` | **245 passed**（本轮新增 **33** 例 `tests/test_agent_session_reference.py`） |
| `node --check`（`agent-panel.js` / `zh-CN.js` / `en.js`） | 3/3 通过 |
| `node scripts/i18n_selftest.js` | **12/12 PASS** |
| `python scripts/scan_ui_strings.py` | `files=3 rows=5`（**无新增硬编码候选**） |
| `(Get-Item docs\todo.md).Length` | 见 §11 本轮行（≤ 36864） |
| 依赖面 | 纯标准库 / 纯浏览器原生 API，**零新依赖** |

**未实测**：① **浏览器交互**（本轮会话**没有浏览器工具**，无法执行"点引用→输入框出现 token→发送→chip 渲染→点 chip 切页签"
的端到端步骤；仅有单测与静态检查）；② 真实模型端点下"引用背景"的实际引导效果与 token 影响；③ 源会话含压缩/裁剪事件时
快照的具体取舍观感。

**文档**：`conventions/docs-management.md §4.2` 本轮登记行；`docs/todo.md §13` **AG03** 改写为完成态；本节。

---

## 6.13 引用机制扩展（2026-09-19 立项；**2026-09-20 已落地，见 §6.20 / §6.21**）

> 来源：用户提议 —— "当前 memoria 有成熟的拖拽选取，你能把这个也纳入引用机制吗（引用对话内容和文件内内容）"。
> 现状：M2 已落两条 **token 级**引用 —— `@相对路径`（上游 `context/file-reference` 语义：**只给模型说明**，内容由模型自己用读取工具取）与 `@[label](dsh-session:…)`（上游 `context/session-reference`：宿主把**有界快照**注入本轮请求）。两者都只引用**整个对象**（一个文件 / 一个会话），**不引用片段**。用户要的是**片段级**引用。
>
> **2026-09-22 订正**：上面这段是 09-19 立项时的现状；**片段级引用已于 2026-09-20 落地**（文件区间 §6.20/§6.21、对话片段 §6.20/§6.21），下表三行状态已就地更新。

| 子项 | 语义 | 落点 / 前置 | 状态 |
|---|---|---|---|
| **A. 文件内选区引用** | 预览/源码里拖选一段 → 生成引用 token，后端能定位到**具体区间** | 需要区间 token（如 `@路径#L12-L30`）；**必须先定"模型看到什么"**：只给区间（模型自己 `read_document`）还是把摘录直塞（像会话快照那样）。前置：**AG07**（引用/锚点合法性 —— 区间只跳起始行、`#L12-L30` 的解析与投影） | ✅ **已落地（2026-09-20，§6.20/§6.21）**：token = `@相对路径#L12-L30` / `@路径#L12`（§6.21 再加**列号** `#L3C2-L5C4`）；采「只给区间」那一支 —— 投影**只回行号与首末行摘要**，正文仍由模型自取；倒置 ⇒ `invalid`、越界 ⇒ `not_found` |
| **B. 对话内容引用** | 选中某条回复 / 某段对话 → 作为下一轮显式上下文 | 台账 **AG01** 已是同一诉求（"引用 agent 回复内容再追问，粒度/入口/请求形状未定"）⇒ 与本项**合并规格化**。实现上最自然的形态：给 `dsh-session:` 加片段维（`#msg:<seq>`）或复用会话快照的"单消息投影" | ✅ **已落地（2026-09-20，§6.20/§6.21）**：片段维 = `dsh-session:<base64url>#seq:<起>-<止>`（§6.20），§6.21 再加**消息内字符区间** `#seq:3c12-3c48`；快照片段投影已接；台账侧 AG01 可据此复评收口 |
| **C. 入口** | 选区之后如何"变成引用" | 复用既有链路：文件树拖拽已有先例（`file-tree.js` → `insertMention`）；对话面板同理 = 选中 → 悬浮动作/右键 → 把 token 插到输入框。**不做**隐式自动引用（保住上游"用户在消息里显式圈定"口径） | **已全部落地**：① 文件侧 v1（2026-09-20，§6.19.2）—— 预览/源码非空选区 ⇒ 悬浮「加入对话」⇒ 插 `@相对路径`（当时只到文件级）；② **对话栏消息级入口**（2026-09-20，§6.20）—— 气泡选区 ⇒ 悬浮「加入对话」⇒ 带位置的片段 token；③ 打字框 chip 渲染（§6.20/§6.21） |

**共同约束**：① 片段若直塞内容，同样要过**不受信任**警告与 `<` 转义；② **不落盘**口径与 §6.12 偏差 1 一致（JSONL 只留 token）；③ 新 token 形态先写进本表与 `reference/agent-guide/01` §6 的 token 清单，再动手。

---

### 6.14 M2 时间上下文实施记录（2026-09-20：吃 `context/time-context`，已落地）

> 补上 §6.7 登记为「**未**顺带吃 `time-context`」的那一块（`docs/design/dsh-agent-port.md:245`）—— 它是 M2 引用家族里最后一个小项；§6.12 收掉 `session-reference` 后单独开工。

**范围界定（先读上游四个源文件才动手）**：上游把读数作为**追加的一条 user 角色消息**写进持久历史（`src/index.ts:211-220`），**不进 system prompt**；本地只吃它的**文本语义**，监听器与调度器按本地架构重落：

| 上游文件 | 吃否 | 理由 |
|---|---|---|
| `src/timestamp.ts` | ✅ | `Intl.DateTimeFormat` 的字段口径（年-月-日T时:分:秒 + 数字偏移，`hourCycle:'h23'`）逐位照搬 |
| `src/request-zone.ts` | ⚠️ 收敛 | 三态时区策略（resolved / mixed / missing）本地没有对应通道 ⇒ 收敛成一条固定说明（偏差 3） |
| `src/index.ts` | ⚠️ 部分 | 只取 `renderText()`（`index.ts:105-107`）的文本形态；`agent/pre-step` 监听器、`refreshIntervalMs` 到期调度、`sessionProjections` 注册不移植（本地无 agent 事件总线与投影服务；同步 `ask()` 一轮一次） |
| `src/invariant.ts` | ❌ | 本地无 invariant 配套设施 |

**上游关键事实（读码所得，不猜）**：① 每条读数三行 —— `Time sampled while preparing turn <turn>, step <step>: <ts>` / `Browser time zone for this request: …` / `Elapsed since the preceding model-visible message|step context: …`；② 时区取自**当前开放轮次**里经宿主校验的 `user-rpc.clientTimeZone`，**混杂或缺失就要求模型向用户澄清**（`request-zone.ts:66-80`），回退值不等于用户权威；③ 回退时区 = 配置 `timeZone`，省略则在**加载期**解析进程时区一次（`index.ts:129-142`）；④ 它是 **opt-in 插件**（默认组合不挂载，Schedule Web overlay 才挂），`refreshIntervalMs` 省略或 `0` ⇒ 每个合格步骤都注入；**不按工具门控**；⑤ README 明说 KV Cache 影响是"仅追加、不使既有条目失效"。

**改动**（3 个既有源文件 + 3 个既有测试文件，无新增模块；`prompt.py` **零行漂移**：4 处同行内改写 + 文件尾追加 63 行）：

- `services/agent/prompt.py`
  - 新增常量 `TIME_CONTEXT_SECTION`（`prompt.py:295-320`）：上游 `renderBrowserTimeZoneContext()` 的**中文落法**，上游英文原文按 `FILE_REFERENCE_SECTION` 同例写在常量注释上方（`request-zone.ts:66-80`）。**门控对齐上游**：上游按「插件被挂载」启停（与 `FILE_REFERENCE_SECTION` 的工具门控不同）⇒ 本地对应「agent 功能已启用」（`build_system_prompt()` 被调用即"已挂载"），故**无条件注入**。
  - `build_system_prompt()` 在**用户引用之后、回答要求之前**追加该段（`prompt.py:263`）—— 段落顺序变为「基础身份 → 运行环境 → 库内指令 → 可用工具 → 用户引用（`@路径`）→ 时间上下文 → 回答要求」。
  - 新增 `_local_now()`（`prompt.py:323-330`，本模块**唯一**的时钟读取点；单测 monkeypatch 它来冻结时间）/ `format_time_context()`（`333-344`）/ `render_time_context()`（`347-355`）。
- `services/agent/ask.py`：`prompt =（用户原文，或 原文 + 跨会话快照）+ "\n\n" + render_time_context()`（`ask.py:445` 同行内联改写，行号未变）；`ask.py:79` 的导入名同步扩为两个。
- 测试：`tests/test_agent_loop.py` 文件尾追加 **4 例**（段落不按工具门控 / system 段里没有动态读数 / 冻结时钟的格式断言 / `ask()` 只把读数加进本轮请求且 JSONL 里没有）；`tests/test_agent_history.py` 新增 `sent_texts()` 小工具并更新 **4 处**断言、`tests/test_agent_session_reference.py` 更新 **1 处**断言（它们原本断言"请求里的 user 正文 == 提问原文"，读数追加后改为剥掉读数再比）。

**模型看到的文本（逐字）** —— system 段的固定说明（每轮一致）：

```markdown
## 时间上下文

宿主会在本轮请求末尾给出一条本机时钟读数，形如 `2026-09-20T09:37:33+08:00`（含数字偏移）：

1. 用户**未限定**时区的日期与时间，按该读数所在时区解释；
2. 该读数**只**用于指导自然语言解释，**不要**替用户或工具参数假定时区；
3. 读数缺失、或与用户明说的时区相冲突时，**先向用户澄清**，不要猜一个时区。
```

本轮请求末尾追加的读数（一次提问恰好一条；下面是本机实测输出）：`当前本地时间：2026-09-20T09:51:44+08:00`

**语义偏差与取舍（上游 → 本地）**：

1. **读数不落盘、且与本轮提问同处一条 user 文本**（与 §6.12 偏差 1 同口径）：上游把读数作为**独立的一条 user 角色消息**追加进请求与持久历史（可回放、随压缩累积）；本地 `loop.run()` 只收一条提问文本，故读数追加在**同一条 user 文本的尾段**（不改消息条数、不引 loop 改造），且**不进会话文件**。**理由**：本地会话文件同时是读取路径的事实源（列表预览 / 标题 / 回放都直接读它），而读数是**派生值**且每分钟不同，写进去会污染渲染视图与预览。**代价**：后续轮次不会重放旧读数（上游会一直累积到被 compaction 遮蔽）。
2. **静态说明与动态读数拆成两半**：上游把时区策略行**写进每条读数**（每轮都变）；本地把**不变**的那半放进 system 段、**可变**的那半放在**可复用前缀之后**（请求末尾）。**理由**：整份读数若进 system 段，该段每轮都不同 ⇒ 整段 system 前缀失去复用价值；拆开后对齐上游 README 的"仅追加，不使既有 KV Cache 条目失效"。
3. **三态时区收敛成一句**：上游时区来自开放轮次的 `user-rpc.clientTimeZone`（宿主校验；混杂/缺失 ⇒ 要求澄清）；本地**没有浏览器时区通道**（宿主就是本机），故 `resolved / mixed / missing` 收敛成"按读数所在时区解释 / 与用户明说冲突即澄清"。上游「仅限提示词来源信息」（不悄然替另一个工具填时区字段）这条限制**保留**为第 2 条。
4. **时区来源 = 机器本地时区**：`datetime.now().astimezone()`（OS 本地时区；本机 Windows `Asia/Shanghai` ⇒ `+08:00`）。上游解析失败在**加载期** fail loud；本地每轮取一次，`astimezone()` 会给 naive 值补上本机偏移 ⇒ **读数恒带数字偏移**（`%z` 为空只可能出现在 naive 输入，而函数开头已补齐）。上游末尾另附 `[IANA 时区名]` 括注，本地**省略**（标准库无法从 OS 可靠取到 IANA 名，且不引新依赖）—— 数字偏移逐位一致，时区仍可解释。
5. **无 turn/step、无经过时长**：上游读数首行带 `turn`/`step`，第三行是"自前一条模型可见消息（或前一条读数）起的经过时长"；本地同步 `ask()` 一轮一次、工具轮次不进 pre-step ⇒ 没有"步骤"概念，**也没有可用于 elapsed 的历史基线**（读数不落盘，见偏差 1）⇒ 首行退化为单个时间戳。
6. **不移植 `refreshIntervalMs` / 投影框架 / invariant 配套 ⇒ 本地不新增配置项**：上游靠 `Config.timeZone` + `refreshIntervalMs` 两个字段调节；本地时区**就是**机器时区、节律**就是**每轮一次（= 上游默认值 `0`）。本地无 cordis.yml，故不新造设置面（上游「No hardcoded tunables」约束的是插件配置面）。

**验收证据**：

| 手段 | 结果 |
|---|---|
| `py_compile`（`prompt.py` / `ask.py` / 3 个测试文件） | 全过 |
| `python -m pytest tests/ -q` | **258 passed**（原 254 + 本轮新增 4 例；另 5 处既有断言随读数更新：`tests/test_agent_history.py` 4 处、`tests/test_agent_session_reference.py` 1 处） |
| 真实渲染（Python 级，非浏览器） | 段落文本见上；读数 `当前本地时间：2026-09-20T09:51:44+08:00`（`+08:00` = 本机 `Asia/Shanghai`）；`tools=()` 时 `TIME_CONTEXT_SECTION in system == True`、`FILE_REFERENCE_SECTION in system == False`（门控对照） |
| `node --check` / `node scripts/i18n_selftest.js` | **不适用**：本轮零前端、零 i18n 改动 |
| 依赖面 | 纯标准库（`datetime`），零新依赖 |

**未实测**：① 真实模型端点对该读数的实际利用（如"今天是几号/现在几点"类问题的回答质量）；② 跨 DST 时区的偏移变化（本机 `Asia/Shanghai` 无夏令时，未构造其它时区跑过）；③ 真机面板端到端（本轮**没有浏览器工具**，只做到 Python 级渲染）；④ 上游 `time-context` 在 dsh 真机上的对照行为（未运行 dsh，只读码）。

**文档**：`conventions/docs-management.md §4.2` 本轮登记行；`reference/agent-guide/10` §6「系统提示组装」行与 `reference/agent-guide/01` §6 引用行的锚点重取（`门控 262-263` → `261-262`，新增 `295-355` 时间上下文块）；§5 映射表本行与 §8 阶段状态同步；§11 变更记录本轮行。**台账**：`docs/todo.md §13` 里**没有**本项对应行（AG07 / AG13–AG17 均非时间上下文）⇒ **未新增台账行**（该台账当时零字节余量；按本轮口径：不为没有对应行的落地项发明新条目）。

---

### 6.15 M2 模型切换实施记录（2026-09-20：吃 `core/agent` 的 `model-selection`，已落地）

> 用户拍板：**先吃 ⏳ 里最省的一块**。故本轮先按「成本 / 收益 / 风险」把 §5 里**全部 ⏳ 候选**逐条读码量过，再动手；判定为「已覆盖 / 本地不适用 / 无消费方」的**不强 port**，只逐条登记证据（与 §5 里既有 ❌ 行同一处置方式）。

**候选逐条界定（读上游源码所得，不猜）**：

| 候选（§5 行） | 上游做什么（文件:行） | 本地现状（文件:行） | 判定 |
|---|---|---|---|
| **`core/agent` 的 `model-selection`** | 把 agent 级 provider/model/effort 绑到请求；**换模型时**向下一次请求追加一条 durable user-role 告知（`packages/core/agent/src/model-selection.ts:41-56` `modelSwitchNotice()`、:108-121 pre-step 挂载） | **缺**：`loop/end` 不记模型（`usage_report.py:20` 把"未记模型名"列为已知限制），换模型后 system 段「运行环境 · 模型」直接改写（`prompt.py:248`）⇒ 同一会话里的历史轮次**无声易主**，且事后不可查 | ✅ **吃**（本轮） |
| `core/agent` 的 registry / initiator | `AgentRegistry`：live agent 表 + `AsyncLocalStorage` 发起者链 + Cordis `Service`/`FiberState`/`typert` 注册（`agent/src/index.ts:245-684`） | 本地是同步 `ask()`、单会话单进程，没有 agent 注册表/生命周期/发起者链的消费方 | ❌ 不吃（Cordis 专有） |
| `core/agent-default-model` | 默认模型的 settings 段 + `currentSelection()` / `saveSelection()`（`agent-default-model/src/index.ts:64-107`） | **已覆盖**：`DEFAULT_MODEL` + `config/agent.json` 的 `model` 键 + `load_config()` 每次现读 / `save_config()` 原子写（`llm/config.py:80`、`202-241`、`284-333`）；余下差异只有 `provider` 路由与 `reasoningEffort` 两个字段，而本地只有一个端点、请求也没有 effort 旋钮（`llm/types.py` 的 `LlmRequest`） | 已覆盖 |
| `core/agent-tool-presentation` | 在 `native` / `ptc` / `both` 之间选**工具呈现**（`agent-tool-presentation/src/index.ts:50-72`；`ptc` 需 PTC runtime） | 本地恒为 `native`（`tools/registry.py` 把全部可见 schema 直接发给模型，无 PTC runtime 也无此旋钮） | 本地不适用 |
| `session-projection` 框架（含 `-cache`） | Cordis 服务：registry + `stateVersion` 校验 + 可持久化的折叠状态 + change feed（`session-projection/src/index.ts`、`session-projection-cache`） | 本地单进程单视图，没有"多订阅者 + 持久化折叠状态"的消费方 | ❌ 不吃 |
| `session-stats` 单元 | 折叠 `step/start`→`assistant/message`（`llmMs`/`ttftMs`/`decodeMs`）与 `tool/call`→`tool/result`（`toolMs`）（`session-stats/src/projection.ts:130-198`，字段见 :32-49） | ① `ttftMs`/`decodeMs` 要**逐片首 token 时间**与**逐步 usage**，本地 usage 只在轮边界、思考与分片时刻都不落盘；② `turns`/`steps` 已被 `usage_report.py`（逐轮）与 `summarize_session*()`（轮数）覆盖；③ 唯一未覆盖的 `toolMs` 本地读出来恒 ≈0 —— 本地 `tool/call` 是**工具跑完之后**才落盘（`loop.py:362-368`），上游是分发**之前**落盘（`agent-loop/src/tool-calls.ts:168` `appendToolCall()` 先于 `:174` `dispatch()`）⇒ **2026-09-22 已对齐**（`tool/call` 改为**先于分发**落盘：`loop.py:362` 那一行上移到 `self.tools.invoke()` 之前，等量换位 ⇒ `toolMs` 前提成立，见 §11 同日行） | ❌ 不吃（口径不匹配，见下「未做」） |
| `interaction/commands` | 插件级 slash 命令 registry：注册 / 发现 / 执行 + `command/run`、`command/done` 生命周期事件（`commands/src/index.ts:263-431`，语法 `parseCommand()` :125-132） | **无消费方**：`ask()` 无命令入口、前端无命令输入面；唯一够格的命令 `/compact` 在 §5 已判 ❌（`command-compact`） | ✅ **2026-09-22 已移植最小面**（§6.23）：消费方随 compaction 落地而出现；注册表 + 生命周期 + `parse_command()` 照搬，`/compact`（复用 `ask._compact_if_needed(force=True)`）与 `/permission <档位>` 按本地需求落地；**未移植**：scope 分层、附件、`/` 补全弹层、`sourceEventSeq` 生产者 |
| `interaction/permission-presets` | 把 sandbox 模式 + 审批策略两个旋钮打成一档（`permission-presets/src/index.ts:177-287`），带 `/permission` 命令与 `permissions` 投影 | ✅ **2026-09-22 已移植（裁到本地口径）**：`services/agent/permission_presets.py` 把**只剩一个**的旋钮（`approval/policy`）打成三档 —— `manual-approval`（`ask`，逐条确认）/ `auto-approval`（`auto`，**默认**：常规写自动放行、风险写问一次）/ `all-access`（`allow-all`，不问全放行；2026-09-22 前叫 `never`，因与上游同名反义而改名），外加**派生只读**的 `custom`（可展示、**不可作切换目标**、不进事件载荷）；档位以**会话事件**落盘（`permission/preset` + `approval/policy`，生效值 = 最后一个覆盖事件 ?? 组合默认），默认档**按 agent 配**（`config/agent.json: permission.<agent>`）；切换面 = 输入区选择器 `#agent-permission` + 设置页默认档 + `agent_permission_*` RPC。**不移植**：`sandbox/mode` 那一半（无 shell / 无进程隔离 / 网络不在其词汇内）、`session/end-seed`（无子代理）。**`/permission <preset>` 命令面已于 2026-09-22 补上**（见 §6.23 的 `/permission`；复用同一个 `set_preset()`）。**语义偏差**：上游 `never` = 「不询问 ⇒ 需审批者一律拒绝」（有 sandbox 兜底），本地落地为「从不询问 = 一律放行」并**改名为 `allow-all`**（同名反义会让读上游文档的人误判；旧会话事件里的 `never` 仍按 `allow-all` **只读兼容**）。**审计**：`approval/asked` + `approval/decided` 已于 2026-09-22 落盘（log-only，每次 ask 恰一条 decided） | ✅ 已落地（§11 本轮行） |
| `credentials/authorization` | OAuth 类端点授权流程（`authorization/src/index.ts`） | 本地单端点单密钥，"写名不写值"已由 `llm/config.py` 覆盖（§6.6 偏差 ⑧），无 OAuth 端点可授权 | 本地不适用 |

**为什么吃 `model-selection`**：6 个候选里**唯一**同时满足「有模型可见文本」「有真实本地缺口」「不需要新 UI / 新依赖 / 新格式」的一份；改动面也最小（3 个既有源文件：1 处文件尾追加 + 2 处同行内联改写）。

**改动**（3 个既有源文件 + 1 个测试文件，无新增模块；`prompt.py` / `ask.py` 零行漂移，`loop.py` +1 行）：

- `services/agent/loop.py`：`loop/end` 载荷新增 `"model": self.model`（`loop.py:396`）—— 每轮一条的**模型事实**（含 `aborted` / `error` 结束的轮次）；除 `usage_payload()` 的键外，旧读者对未知键一律忽略（AGENTS.md §3「payload 只增不改」）。
- `services/agent/prompt.py` 文件尾追加 `MODEL_CHANGE_NOTICE` + `render_model_change_notice()`（`prompt.py:358-382`）：上游 `modelSwitchNotice()` 的**中文落法**，上游英文原文按 `FILE_REFERENCE_SECTION` / `TIME_CONTEXT_SECTION` 同例写在常量注释上方；`__all__` 在既有行内联追加两个名字（`prompt.py:60-61`，行数不变）。
- `services/agent/ask.py`：`prompt = … + _model_notice(…) + render_time_context()`（`ask.py:445` 同行内联改写，行数不变；导入名扩为三个，`ask.py:79`）；文件尾追加 `_last_recorded_model()` / `_model_notice()`（`ask.py:458-495`）—— 取会话里**最后一条 `loop/end.model`** 与本轮模型比对，不同才追加告知。
- 测试：`tests/test_agent_loop.py` 文件尾追加 **7 例**（告知文本逐字 / `loop/end` 记模型 / 换模型续聊请求里出现且不落盘 / 同模型不告知 / a→b→a 仍告知 / 老会话无模型记录不告知 / `replay=False` 不告知）。

**模型看到的文本（逐字）** —— 换模型续聊时，本轮请求的最后一条 user 消息（实测输出）：

```text
第二问

[模型已更换：本轮之前的助手回复由 deepseek-chat 生成；本会话此后由 model-beta 继续]

当前本地时间：2026-09-20T10:21:18+08:00
```

同模型续聊则只有 `第三问\n\n当前本地时间：…`（无告知、无多余空行）。

**语义偏差与取舍（上游 → 本地）**：

1. **告知是"从日志派生的"而非新增持久消息**：上游把它作为**一条 user 角色消息**追加进请求并写进会话历史（可回放、随压缩累积）；本地按 §6.12/§6.14 同口径只加进**本轮请求文本**（不落盘、不改消息条数）。**理由**：本地 `user/message` 事件 = **一个用户轮次**（`summarize_events()` 的 `turn_count`、`conversation_messages()` 的气泡、检索语料都直接读它）⇒ 把插件告知写成 `user/message` 会污染轮数、左栏历史与对话渲染视图。**代价**：告知不会随历史被重放（下一轮由"最后一条 `loop/end.model`"重新派生 ⇒ 语义等价，且模型换回旧模型时会**再次**告知）。
2. **模型标签只有模型名**：上游 `routeLabel()` 在 provider 不同时写 `provider/model`；本地没有 provider 概念（单端点）⇒ 标签就是模型名。
3. **比对基准是"最近一轮"而不是"请求 header"**：上游比 `selection.assembled` 与 `session.requestHeader()?.config`（每次请求都落一份请求配置）；本地没有请求记录（`loop.py` 模块 docstring 早已登记"未移植请求 header 冻结"）⇒ 基准改为**会话里最后一条 `loop/end.model`**。**老会话**（本字段之前落盘）读不到模型 ⇒ 按「未知」处理、**不**告知（fail-safe），代价是"换模型后第一次续聊老会话"不提醒。
4. **`replay=False` 不告知**：此时本轮请求里没有历史，告知"上面的回复出自别的模型"没有对象；上游无此开关。
5. **插入位置**：夹在**用户文本之后、时间读数之前**（时间读数仍是请求末尾，§6.14 位置未变）；上游是 pre-step 链上 `{prepend: true}` 追加的消息，与 time-context 的先后由监听器序决定，本地取"告知在前"的固定序。
6. **不移植的事**：（a）`installModelSelection()` 的另外两条语义 —— 把选中模型写进 `system-prompt/assemble` 的 `variables`（本地 system 段本就带"模型："一行，`prompt.py:248`）与把 provider/model/effort 覆写进请求配置（本地 `LlmRequest` 只有单一 `model`，无 effort 旋钮）；（b）**effort-only 变化不告知**（本地无 effort）；（c）`agent-default-model.saveSelection()` 这条写侧（本地写侧就是 `save_config({"model": …})`）。

**验收证据**：

| 手段 | 结果 |
|---|---|
| `py_compile`（`prompt.py` / `ask.py` / `loop.py`） | 全过 |
| `python -m pytest tests/ -q` | **265 passed**（原 258 + 本轮新增 7 例；**无既有断言需要改动** —— 告知只在"续聊且模型变"时出现） |
| 真实请求文本（Python 级，临时脚本 + 假 provider，仓库外跑完即删） | 见上「模型看到的文本」；另打印：同模型续聊**无**告知、全新会话请求条数 = 1 且无告知、`loop/end.model` = `['deepseek-chat', 'model-beta', 'model-beta']`、会话 JSONL 里 `user/message` 正文仍是 `['第一问','第二问','第三问']`、JSONL 中**出现告知字样 = False** |
| `node --check` / `node scripts/i18n_selftest.js` / `scan_ui_strings.py` | **不适用**：本轮零前端、零 i18n 改动 |
| 依赖面 / 行号 | 纯标准库，零新依赖；`prompt.py`、`ask.py`、测试文件均为**文件尾追加 + 同行内联**；`loop.py` **+1 行**（`loop/end` 事件 `390-398` → `390-399`，其后行号 +1，已重取的锚点见下「文档」） |

**未实测**：① 真实模型端点对这条告知的利用（如换模型后是否还会把旧回复记成自己写的）；② 真机面板端到端（本轮**没有浏览器工具**，只做到 Python 级请求文本）；③ 上游 `model-selection` 在 dsh 真机上的对照行为（未运行 dsh，只读码）。

**文档**：`conventions/docs-management.md §4.2` 本轮登记行；`reference/agent-guide/10` 会话事实源 / `loop/end` 载荷 / 锚点表三处（`loop.py:390-398` → `390-399`、`loop.py:302-398` → `302-399`）+ 新增「模型切换告知」一条；§5 映射表本行与 §8 阶段状态同步；§11 变更记录本轮行。**台账**：`docs/todo.md §13` 里**没有**本项对应行 ⇒ **未新增台账行**（该台账零字节余量，按 §6.14 同口径处置）。

**本轮未做（如实登记，勿当成已实现）**：① ~~`toolMs` 所需的事件次序对齐（把 `loop.py` 的 `tool/call` 从"工具跑完后"提到"分发前"，对齐上游 `tool-calls.ts:168`）~~ **2026-09-22 已完成**（§11 同日行：等量换位 + 两条新用例，总行数不变 ⇒ 锚点零漂移；`toolMs` 前提已成立）；② 按轮模型做**逐轮成本归属**（`pricing.estimate()` 现在用"当前模型"给所有历史轮定价，`ui.py:1441`）—— `loop/end.model` 现已具备前提，改 `usage_report.turn_from_event()` + 定价调用即可，**仍未做**。

---

### 6.16 上游读面移植实施记录（2026-09-20：吃 `fs/tool-fs` 的 `read`/`read_image` + `fs/tool-fs-search` 的 `glob`/`grep`，已落地）

> 用户口径：**「上游的读先移植进来」**；同轮登记一项**后续优化项**（不实现）：「agent 常常调用 powershell 进行脚本化读写等（但是常常因为语法错浪费 token，这个以后是一个优化项目）」—— 见 §8 的 ⏳ 新增行。本轮的读面移植正是它的第一半（原生工具替代脚本）。

**范围界定（先读上游源文件才动手）**：

| 上游文件 | 吃否 | 理由 |
|---|---|---|
| `fs/tool-fs/src/read.ts` | ✅ | `read` 的参数校验（`offset` 默认 1、`limit` 默认**且**上限 = 配置值、`limit > maxLimit` 直接报错，`:55-61`）与「一次 stat → 窗口 → 观测」的次序；本地落在既有 `read_document` 上（不新增工具，见偏差 4） |
| `fs/tool-fs/src/read-render.ts` | ⚠️ 部分 | 行/字符/字节三重 cap 的**窗口构建次序**与**续读 footer 文案口径**（`:95-170`）；`readMaxLineLength` 的**单行截断**不吃（偏差 4） |
| `fs/tool-fs/src/read-image.ts` | ⚠️ 部分 | 扩展名表（`:25-31`）、四个文件签名（`:33-34`）、`sniffImageMediaType()`（`:54-60`）、「扩展名与签名不一致」的拒绝口径；`attachments` 持久化、路由 `inputModalities` 门控（`:119-131`）、尺寸/像素/字节上限**本地无对应**（偏差 3） |
| `fs/tool-fs/src/index.ts` | ⚠️ 部分 | 只取「`read_image` 是**组合条件**注册」这一形态（`:70-72`）；本地没有 `attachments` 服务，注册条件改为「知识库 agent 已启用」 |
| `fs/tool-fs-search/src/glob.ts` | ✅ 部分 | `globMaxResults` 默认 100（`:25`）、`GLOB_VCS_EXCLUDES`（`:37`）、argv 语义（`--files --glob=… --sort=modified --no-ignore --hidden`，`:89-107`）、超上限的「计数 + 收窄」footer（`:213-240`）；ripgrep 进程与 spill 不吃 |
| `fs/tool-fs-search/src/grep.ts` | ✅ 部分 | `grepMaxMatches` = 250（`:29`）、`grepMaxLineBytes` = 2000（`:35`）、`include` 单正向 glob 校验（`:67-78`）、按文件分组的 `Line N: <preview>` 形状（`:191-203`）、`timeoutMs` 预算（README.md:64）；`--json` 传输层与 spill 不吃 |
| `search-core.ts` · `presentation.ts` · `direct-call.ts` · `tool-fs/{write,edit,sandbox,session-cwd,diff,error}.ts` · `tests/*` | ❌ | 子进程/spill/展示/写面/规格测试，本地无对应（写面见 §5.1「写工具」组；本轮的 Python 侧测试另写，见下） |

**上游关键事实（读码所得，不猜）**：① cap 三件套 = **2000 行** / 单行 2000 字符 / **50 KiB**，另 ≥10 MiB 走流式（`read.ts:15`、`:21`、`read-render.ts:11`、`:14`、`README.zh.md:59-62`）；② `offset` 越界（超 EOF；空文件 + `offset=1` 除外）抛 `FS_NOT_FOUND`（`read-render.ts:96-98`）；③ footer 三态**逐字**为 `(Output capped. Showing lines a-b. Use offset=N to continue.)` / `(Showing lines a-b of T. Use offset=N to continue.)` / `(End of file - total T lines)`（`read-render.ts:152-170`），结果信封为 `<path>…</path>` + `<type>file</type>` + `<content>`（行形如 `N: text`，`:163`）；④ `glob` 的 pattern **不含 `/` 时匹配任意深度的文件名**（`README.zh.md:46-48`、`:305-306` 的系统提示段同款说明）；⑤ `grep` 结果按文件分组、每行 `Line N: <preview>`，上限 250 条内联（`grep.ts:29`、`:191-203`）；⑥ 两者的失败码是 `SEARCH_INVALID_PATTERN` / `SEARCH_FAILED` / `SEARCH_RAW_OUTPUT_OVERFLOW` / `SEARCH_ABORTED`，而**模型参数错误仍是普通工具参数错误**（`README.md:77`）；⑦ `read_image` 只在 `attachments` 挂载时注册，且执行时拒绝「未声明 image 输入的路由」（`index.ts:70-72`、`read-image.ts:119-131`）；⑧ 上游三工具的 README 都写明「模型可见文本逐字固定 + 仅追加的 KV 影响」。

**改动**（2 个既有源文件 + 1 个既有测试文件 + 1 个新测试文件，无新增模块）：

- `services/agent/tools/kb.py`（**文件尾追加 + 1 处等量改写 + 1 处 +15 行**）
  - `read_document` 新增 `offset`/`limit`：签名 `:283`、窗口调用 `:311-324`（该 14 行与原 14 行**等量改写**，故其上锚点零漂移）；实现 `_read_window()` `:730-776`、包装层 `_read_document_call()` `:779-790`、`DEFAULT_READ_LIMIT` `:688`；**工具声明 `:523-550` 由 13 行变 28 行（+15）** —— 本文件第 551 行起的锚点整体 +15（已重取，见「文档」）。
  - 新增三个工具：`glob`（实现 `:911-946`，声明 `:610-627`）、`grep`（实现 `:982-1072`，声明 `:628-649`）、`read_image`（实现 `:1088-1131`，声明 `:650-665`）；`KB_TOOL_NAMES` `:73-80`（**8 行等量改写**，9 个名字）与 `build_kb_tools()` 的返回元组同步（三者默认 `read_only=True`）。
  - 共用件：`_safe_rel_any()` `:793-808` / `_safe_rel_dir()` `:811-816`（`_safe_rel()` 的「不限扩展名」版）、`_walk_kb_files()` `:819-839`（VCS 排除、**两侧 realpath** 的越界判定）、**允许根列表** `_read_roots()` / `_resolve_in_read_roots()` `:1135-1162`（文件尾追加；今天单根 ⇒ 行为等价）、`_translate_glob()` + `_glob_matcher()` `:841-901`、`_check_include()` `:948-957`、`_preview_line()` `:965-970`、`_sniff_image_media_type()` `:1075-1085`。
- `services/agent/prompt.py`（**零行漂移**）：`@路径` 段门控由「只认 `read_document`」放宽为**任一读取手段在场**（`prompt.py:261` 同行内联改写）；文件尾追加 `FILE_REFERENCE_TOOLS` + `_has_read_tool()`（`:385-394`，调用期取用 ⇒ 顶层 import 段不动）；`__all__` 同行内联扩名（`:61`）；`FILE_REFERENCE_SECTION` 的注释按新口径改写（`:205-207`，行数不变）。
- 测试：`tests/test_agent_loop.py` 的门控例改用「任一读取工具」口径（本轮该文件仅此 1 处语义更新，并新增一条「只剩 `glob` 也注入」断言）；新增 `tests/test_agent_tools_read.py`（**20 例**：分页/续读提示可解析/越界与 limit 上下限/字符预算续读/正文行号口径/glob 匹配与上限与**可见性（`.memoria/**` 默认可见、`.git` 不可见）**与允许根之外拒绝/realpath 越界条目不列不读/ grep 格式与 include 与正则错误与二进制跳过与 250 上限与 2000 字节预览/read_image 四类校验 + 明确拒绝/新工具注册与 `read_only`/schema 形状/**允许根列表与越界错误码稳定**）。

**模型看到的文本（逐字，实测输出）**：

```text
# ① 分页（read_document path=long.md offset=1 limit=4）
文档 long.md：共 120 行，0 个知识点。

知识点（`文件:行号`）：
- （该文档没有 sidecar 知识点）

正文：
第 1 行：多层感知机要点 1
第 2 行：多层感知机要点 2
第 3 行：多层感知机要点 3
第 4 行：多层感知机要点 4

…（已显示第 1-4 行，共 120 行；续读请把 offset 设为 5。）

# ② glob（pattern=*.md，按修改时间新→旧）
vocab/mlp.md
long.md

# ③ grep（pattern=多层全连接）
命中 1 处（pattern='多层全连接'）

vocab/mlp.md
Line 3: 多层感知机由多层全连接组成。

# ④ read_image（合法 PNG）
Error: read_image: 本端点暂不支持图像输入 —— pic.png 已通过格式校验（image/png），但缺『多媒体眼睛』插件（属未来多媒体能力）：当前模型通道（纯文本 `Message.content`）无法把图片作为内容块发出，故不返回图片本身；请改用文字描述该图（见 dsh-agent-port.md §6.16）。 (UNSUPPORTED_IMAGE_INPUT)
```

越界（允许根之外）的四类拒绝（实测）：`read_document` `../outside.md` → `INVALID_ARGUMENTS`；`offset=999` → `NOT_FOUND`（`offset 999 超出范围 —— "long.md" 正文共 120 行`）；`glob` `path=../../etc`、`grep` `path=..\..\win.ini`、`read_image` `../img.png` → 均 `INVALID_ARGUMENTS`。

**语义偏差与取舍（上游 → 本地）**：

1. **工具面是「工作区根」而不是「知识库内容面」**（结构性，**2026-09-20 设计改正**）：所有路径经**允许根列表**（`_read_roots()`，今天只含库根）校验（上游由 `ctx.fs` 后端 + 沙箱档决定可读范围）；「只能看到某些文件」是**程序施加的可见性/权限**，不是把工具本身缩到知识库。**可见性**：只跳 VCS 内部目录（`.git` 等，理由=非内容且会污染 glob/grep），`.memoria/**` **默认可见**（agent 维护 sidecar/manifest 需要看得见）；指向允许根之外的符号链接条目**既不列也不读**。**未来的越界方向**：结构上预留「允许根列表」以支持越出根目录（Windows 拖入对话栏的外部文件，可带**只读/不可信**标记），并注明「将来把根加进列表即放行」；越界一律是**明确的拒绝错误**（`INVALID_ARGUMENTS`），不是「文件不存在」。**理由**：`glob`/`grep` 不该成为绕过 `read_document` 路径校验的后门，但可见面应由程序/权限决定而非把工具缩到知识库。
2. **`grep` 用 Python `re`，不引 ripgrep**（结构性）：正则方言不同（RE2 无回溯 vs Python 回溯；`\p{…}`、`\A`/`\z` 等简写各自不同；同一条 pattern 的**命中集合可能不同**）。上游的进程面（`--no-config` 防 `RIPGREP_CONFIG_PATH` 注入、raw stdout 上限、stderr 尾部、terminate grace）本地统统没有；改为自持 `GREP_MAX_MATCHES=250` / `GREP_MAX_LINE_BYTES=2000` / `GREP_TIMEOUT_S=30`（对齐上游默认值）+ `GREP_MAX_FILE_BYTES=4 MiB`（**本地新增**边界）。跳过**报数不静默**（`（N 个文件超过 4 MiB 未扫描；M 个二进制文件已跳过）`）。**理由**：零依赖是仓库硬约束（`packaging/build.py` 体积预算）。**风险**：模型若按 ripgrep 语法写 `\p{Han}` 会得到参数错误（错误文案已写明「本工具用 Python `re` 语法，非 ripgrep 方言」）。
3. **`read_image` 只到「参数与校验」**（结构性，**不伪造成功**；**2026-09-20 归类改正**）：读不到图**不是**「provider 不支持 content part」这么简单，而是**缺一个多媒体的「眼睛」插件** ⇒ 归入**未来的多媒体能力**，**不再算读面缺口**。当下的机制约束是：本地消息层是纯文本（`llm/types.py:87` 的 `Message.content: str`），`providers/openai_compatible.py:396` 的 `_message_to_wire()` 只写 `{"role", "content": <str>}`。故工具照上游做扩展名表 / 文件签名 / 「扩展名与签名不一致」三类校验，校验通过后仍返回 `UNSUPPORTED_IMAGE_INPUT` 并说明真实原因与替代做法（改用文字描述）。缺的还有：附件持久化、`maxImageBytes`/`maxImagePixels`/`maxImageDimension`、按路由 `inputModalities` 的能力门控（本地单端点、无 model info 通道）。**待办**：**待『多媒体眼睛』插件**（该插件落地后，本工具把最后一步换成真的返回图片）。
4. **不新增 `read` 工具，而是把分页加进既有 `read_document`**：本地上游对应的读取面是知识库文档工具（不是文件系统），且 `@路径` 门控、知识点锚点、`File:line` 引用都挂在它上面。**故签名向后兼容**：不传 `offset`/`limit` 时窗口 = 首 20,000 字符内的整行，未截断时**逐字等于旧输出**（含正文末尾换行），`MAX_BODY_CHARS` 语义不变（有单测断言）。
5. **不逐行加行号 + 不做单行 2000 字符截断**：上游结果每行 `N: text`，本地正文保持原样（行号由「知识点（`文件:行号`）」清单给出，与既有引用约定一致）；`readMaxLineLength` 的单行截断不吃，超长行由 20,000 字符预算兜底。**理由**：旧调用逐字兼容优先（偏差 4 同因）。
6. **未截断时不产 EOF footer**：上游恒有第三态 footer；本地只在**被截断**时产出续读提示（`…（已显示第 a-b 行，共 T 行；续读请把 offset 设为 N。）` / `…（正文已达 20000 字符预算：…）`），未截断则**不追加任何 footer**。**理由**：无参数调用必须逐字不变（偏差 4）；**代价**：模型要自己从表头的「共 T 行」判断是否读尽。
7. **预算用「字符」而非「字节」，且以整行为单位**：上游 `readMaxBytes` = 50 KiB 字节、溢出即停在行尾；本地沿用既有 20,000 **字符**（`MAX_BODY_CHARS`），按整行累加到预算为止 ⇒ 同一文档的截断点与上游不同（本地更早或更晚，取决于中文字符占比）。
8. **无 spill ⇒ 超限只报数不给 locator**：上游把完整结果写 spill 并在 footer 给 `Full sorted result stored at: <locator>`；本地没有 spill 存储，footer 改为「匹配 N 个文件，仅显示最近修改的 M 个；请收窄 pattern 或 path 以查看其余」/「仅显示前 250 处；请收窄 pattern / path / include」。
9. **`glob` 排序方向取「新→旧」**：上游用 ripgrep `--sort=modified`；方向**未在只读检出里可判定**，唯一线索是上游单测注释「mtime order puts one freshly-unpacked subtree first」（`tool-fs-search/tests/tools.spec.ts:790-792`）⇒ 取「最新修改在前」。**未实测**（见下）。
10. **门控放宽为「任一读取手段在场」**：上游是 `ctx.tools.get('read') === undefined ? '' : …`；本地读取手段有四个，名单 `FILE_REFERENCE_TOOLS`（旧口径只认 `read_document`）⇒ **只装了 `glob` 的知识库也会得到 `@路径` 段**（有单测断言）。
11. **`read_image` 的注册条件**：上游按 `attachments` 服务挂载注册；本地没有该服务，按「知识库 agent 已启用」（`build_kb_tools()` 被调用）注册 —— 于是模型**会看到**这个工具，但它**永不返回图片**。**取舍**：schema 里已写明「当前缺「多媒体眼睛」插件」以免误导；**代价**：每个请求多付一个 schema 的 token，且模型偶尔会误调一次（得到明确错误后可自纠）。
12. **`glob` 的 glob 方言子集**：支持 `*`（不跨 `/`）、`?`、`**`、`{a,b}` 与 `[...]`；**不支持** `!` 取反与其他 ripgrep 深度修饰；`{}` 只做单层展开。`grep` 的 `include` 照上游拒绝 `!` 与逗号列表，但**不**替代上游 `--glob` 的全部语义。

**验收证据**：

| 手段 | 结果 |
|---|---|
| `py_compile`（`kb.py` / `prompt.py` / `tests/test_agent_tools_read.py` / `tests/test_agent_loop.py`） | 全过 |
| `python -m pytest tests/ -q` | **284 passed**（原 265 + 本轮新增 19 例；既有测试仅 1 处断言语义更新 —— `tests/test_agent_loop.py` 的门控例）；**2026-09-20 设计改正轮：285 passed**（原 284 + 新增 1 例允许根列表用例；2 处既有断言随 `.memoria/**` 可见性改正） |
| 真实行为取证（Python 级；仓库外临时脚本，跑完即删） | 见上「模型看到的文本」四段 + 五类拒绝；另实测：续读提示可被 `re` 解析出 `offset=5`、按之续读首行正是「第 5 行」、读到末页**无** footer；`grep` 命中行号（`Line 3`）与 `read_document` 的正文行号**同一行空间**；**2026-09-20 设计改正后重测**：`glob` 结果**含** `.memoria/agent/**`、**不含** `.git/**`（`GLOB_EXCLUDED_DIRS` 只余 VCS 名单）；`_read_roots()` 返回值 = `(库根,)`，四类越界均 `INVALID_ARGUMENTS`；解析到根外的符号链接条目不列不读 |
| 门控取证 | 同一份工具集：全部 9 工具 ⇒ `@路径` 段在；**只剩 `glob`** ⇒ 仍在；四个读取工具全去掉 ⇒ **不在** |
| `node --check` / `scripts/i18n_selftest.js` / `scripts/scan_ui_strings.py` | **不适用**：本轮零前端、零 UI 文案、零 i18n 键（工具描述是模型可见文本，不进 UI 字典） |
| 依赖面 | **纯标准库**（`os` / `re` / `time` 局部导入），零新依赖 ⇒ 打包体积不变 |
| 行号 | `kb.py`：`read_document` 声明区 **+15 行**，其余全为文件尾追加；`prompt.py` / 两个测试文件：同行内联或文件尾追加（零漂移）。**2026-09-20 设计改正轮**：`kb.py` 全部为**等量改写**（`_safe_rel()` / `_safe_rel_any()` / `_walk_kb_files()` 等）＋文件尾追加允许根列表块 ⇒ **零锚点漂移**（本节与 §5.1 引用的 `file:line` 均未移动）。 |
| 上游检出未被改 | `git -C dsh-src status --porcelain` **空** |

**未实测**：① 上游 `--sort=modified` 的**真实方向**（只读检出，本地未运行 `rg`/`dsh`；依据是上游单测注释 `tools.spec.ts:790-792`）；② 真实模型端点下模型**是否会正确续读**（拿到 footer 后按 offset 再调一次）与**用对工具**（该用 `grep` 时不用 PowerShell）；③ 真机面板端到端（本轮**没有浏览器工具**，且零前端改动）；④ `grep` 的 30s 预算与 4 MiB 单文件上限只走了**常规路径**（未构造超时/超大文件用例，跳过计数分支由二进制文件那条覆盖）；⑤ Python `re` 与 ripgrep 的**逐条方言差异**未做穷举对照（只断言了「非法正则 ⇒ 参数错误」这一条）；⑥ `read_image` 的校验分支未用真实相机/大图验证（只用合成的 PNG 签名 + 文本伪装 + 扩展名错配三种）；⑦ 大库（数千文件）下 `glob`/`grep` 的**墙钟耗时**未做 A/B 计时（有界性有单测，墙钟未测）。

**文档**：`conventions/docs-management.md §4.2` 本轮登记行；`reference/agent-guide/10` 三处（工具面计数行 `181`、系统提示门控行 `198`、`search_sessions` 锚点行 `226`）；本文件 §5.1 读工具四行 + 会话检索行 + 三段结论中的 ①③；§8 新增 ⏳ 行（PowerShell 优化项）；§11 变更记录本轮行。**同轮设计改正（2026-09-20，用户口径）**：① 工具面 = **工作区根**（今天 = 库根），结构性偏差改述为「**允许根列表** + 可见性/权限由程序施加」，将来支持越出根目录（外部拖入，只读/不可信）⇒ `kb.py` 引入 `_read_roots()` / `_resolve_in_read_roots()`（文件尾追加）、路径校验与遍历都改走它（行为等价、零锚点漂移）；② `.memoria/**` 由「默认排除」改为**默认可见**、`.git` 等 VCS 内部仍排除（`GLOB_EXCLUDED_DIRS` `:692`）；③ `read_image` 归入**未来多媒体「眼睛」插件**（原「消息层图片支持」待办措辞作废），偏差 3 与 §5.1 两行同步；④ `reference/agent-guide/10` 工具面段落一处同步。**锚点重取（old → new）**：`tools/kb.py:566-592` → **`:581-607`**（`search_sessions` 声明，因 `read_document` 声明区 +15 行）、`prompt.py:262-263` → **`:261`（门控行）+ `:385-394`（名单与判定）**；其余引用（`kb.py:73-80`、`:160-172`、`:212-215`、`:238`、`:279`、`:341`、`:377`、`:460`、`:486`、`prompt.py:194-218`、`:207`、`:270`）**未动**。**台账**：`docs/todo.md` **未编辑**（另一写者并发重写中；建议台账行见本轮报告）。

---

### 6.17 会话查询五工具补全实施记录（2026-09-20：吃 `session-query/tool-session-query` 的其余四个工具 + `session-query/src/tracing.ts`，已落地）

> 补上 §5.1 读工具组的最后一行：上游 `tool-session-query` 明说**五个**只读工具（`README.zh.md:12`、`:47-51`），本地此前只落了 `search_sessions` 一个（§6.9 明文「不移植 `lineage` / `trace`」）。本轮把**其余四个**（`session_event_search` / `session_trace` / `session_event_trace` / `session_event_read`）按上游**名字、参数与结果形状**补齐；`search_sessions` 保留原名与既有行为（名字偏差见偏差 1）。

**范围界定（先读上游源文件才动手）**：

| 上游文件 | 吃否 | 理由 |
|---|---|---|
| `tool-session-query/src/index.ts` | ✅ 部分 | 五个工具名 / 描述 / 参数 / `isConcurrencySafe`（三个精确读取工具并行安全）；本地落**四个新工具**（`session_search` 早已以 `search_sessions` 之名落地）；`Config`（`maxSearchResults` / `searchTimeoutMs`）本地无配置面（偏差 6） |
| `tool-session-query/src/input.ts` | ✅ 部分 | ISO 8601 时间戳口径（`ISO_TIMESTAMP` `:179-180`、逐项日历校验 `:188-221`、`from <= to` `:149`/`:170`、非负安全整数 `:278-285`、数组非空 `:287-294`）；`surfaces` / `availability` / `parent_session_ids` / `include_root_sessions` 无本地对应（偏差 4/5） |
| `tool-session-query/src/operations.ts` | ✅ 部分 | 五个操作的编排次序（授权 → 规范化 → 过滤 → 收集）；`collectPages` 的**游标翻页**、调用方会话身份、`SESSION_QUERY_TOOL_*` 错误净化不移植（偏差 2/3/7） |
| `tool-session-query/src/presentation.ts` | ✅ | 五个结果文本逐条落为中文（分组 / 每命中 `seq \| type \| time` + `Snippet:` / 上限提示 / `formatNeighbor()` 的邻接摘要） |
| `session-query/src/tracing.ts` | ✅ 部分 | `traceSession()` 的祖先链（由近及远）+ 后代树 + 未解析父会话、`traceEvent()` 的替换链与直接替换；`foldSurface()` 表面折叠与 `sourceEventSeqs` **不移植**（本地无这些字段：偏差 3） |
| `session-query/src/index.ts` 的 `traceSession` / `traceEvent` / `readEvent` | ✅ | 三个方法的语义与 `_readWindow()` 的 `0..SESSION_QUERY_READ_WINDOW_MAX` 上限（`config.ts:6`） |
| `workspace-access.ts` / `service-boundary.ts` / `cursor.ts` / `session-query-sqlite` / `observation.ts` / `session-log-export` | ❌ | 调用方 `cwd` 授权、模型边界错误净化、提供方游标、SQLite FTS 索引、宿主可观测性、导出 UI —— 本地无对应（§6.9 已登记，本轮不变） |

**上游关键事实（读码所得，不猜）**：① 五个工具名与描述逐字为 `session_search` / `session_event_search` / `session_trace` / `session_event_trace` / `session_event_read`（`index.ts:65-121`，生成目录见 `dsh-src/docs/tool-catalog.zh.md:1697-1928`）；② `session_id` **可省** = 当前会话，且事件检索在当前会话上截断到「执行本次调用的步骤之前」（`operations.ts:128-139`）；③ 上限：`maxSearchResults` 默认 **100**（部署侧，模型不可调，`index.ts:22`）、`before`/`after` 默认 0 且 ≤ **50**（`config.ts:6`、`index.ts:396-405` 的 `_readWindow`）、搜索协作截止 `searchTimeoutMs` 默认 **30000**（`index.ts:25`）；④ 搜索结果文本 = `Session <id> — <title>` + 每组 `seq \| type \| surface \| time` + `Snippet:` + 达上限时的 `Result cap reached. Narrow the query or add filters to find additional matches.`（`presentation.ts:48-106`）；⑤ 精读 = 目标**完整** JSON + `Before:` / `After:` 每条 `- seq N | type | time` + 语义文本缩进（空则 `(no semantic text)`，`presentation.ts:165-194`）；⑥ 谱系 = `Ancestors (nearest first)` / `Descendants`（树形按深度缩进）+ 越界边界标记（`presentation.ts:108-147`）；⑦ 事件溯源 = `Replaced by` / `Replacement chain` / `Events replaced by target` / `Events cited directly as sources` / `Direct derived events`，数据来自 `foldSurface()` 的 `replacements` 与事件的 `sourceEventSeqs`（`tracing.ts:86-110`、`:222-224`）；⑧ 模型永远看不到游标 / 偏移 / 分页大小 / 可控上限（`README.zh.md:53`）。

**改动**（2 个既有源文件 + 1 个既有测试文件 + 1 个新测试文件，无新增模块）：

- `services/agent/session/query.py`（**文件尾追加** 298 行 + 3 处等量改写，零锚点漂移）
  - 新增库面：`require_session()`（`:462-470`，会话不存在 ⇒ `SessionQueryNotFound`；非法 id 仍由 `store.session_file()` 抛 `ValueError` ⇒ fail-closed）、`read_event()`（`:528-552`，窗口按事件下标取、两端夹紧）、`trace_event()`（`:555-573`）、`session_lineage()`（`:605-662`）；结果 dataclass `SessionEventWindowResult`（`:417-425`）/ `SessionEventTraceResult`（`:428-437`）/ `SessionLineageRecord`（`:441-448`）/ `SessionLineageResult`（`:452-459`）。
  - 新增常量（`:400-409`）：`DEFAULT_READ_WINDOW` / `MAX_READ_WINDOW = 50`（上游 `SESSION_QUERY_READ_WINDOW_MAX`）/ `DEFAULT_SEARCH_RESULT_LIMIT = 100`（上游 `maxSearchResults`）/ `REPLACEMENT_TYPES = (compaction, compaction/prune)` / `HEADER_LINE_MAX_BYTES = 64 KiB`（本地新增：读 header 的单行上限）。
  - 共用件：`_covered_seqs()` / `_replacement_maps()`（替换关系的本地口径）、`_window()`、`_header_of()`（只读首行 ⇒ 谱系不解码整份文件）、`_parent_of()`、`_lineage_record()`；`__all__ += [...]`（`:665-679`，不在文件头插行）。
  - **3 处等量改写**：`read_session` 加入 `store` 导入行（`:76`）、模块 docstring 的「不移植」项由「`lineage` / `trace`」改述为「`tracing.ts` 的 `foldSurface` 表面折叠」（`:41-44`，行数不变）。
- `services/agent/tools/kb.py`（**文件尾追加** 439 行 + 2 处等量改写，零锚点漂移）
  - `KB_TOOL_NAMES` 由 9 个名字扩为 **13** 个（`:73-80`，**8 行等量改写**）；`build_kb_tools()` 返回元组末位同行改写为 `), *_session_query_tools(root),`（`:665`，**零行漂移**）；模块 docstring 的工具表行改为「会话查询家族（5 个）」（`:18`）。
  - 新增四个工具实现 `_session_event_search()`（`:1297-1363`）、`_session_trace()`（`:1366-1413`）、`_session_event_trace()`（`:1416-1464`）、`_session_event_read()`（`:1467-1507`）与声明工厂 `_session_query_tools()`（`:1510-1605`，四把 `Tool` 全部默认 `read_only=True`）。
  - 共用件：`_epoch_ms()`（`:1208-1240`，带时区限定的 ISO 8601 → **含端点** epoch 毫秒，逐项日历校验）、`_seq_arg()`（`:1243`）、`_event_types_arg()`（`:1252`）、`_session_arg()`（`:1266`）、`_title_of()`（`:1274`）、`_iso_ms()`（上游 `toISOString()` 形态）、`_neighbour_line()`（`:1286`）、`SESSION_EVENT_HITS_CAP = 100`（`:1185`）、`_SessionArgError`（`:1193`，参数/作用域错误 ⇒ `INVALID_ARGUMENTS`）。
- 测试：新增 `tests/test_agent_session_query_trace.py`（**23 例**）；`tests/test_agent_tools_read.py:416` 一行断言由「末尾三工具」改为「读面三工具的相对次序」（新工具按追加顺序排在末尾；该断言无 `<文件>:<行号>` 锚点引用）。

**模型看到的文本（逐字，实测输出；节选自仓库外临时脚本）**：

```text
# ① session_event_search（session_id=demo-s1, query=梯度）
会话 demo-s1 — 梯度下降是什么

事件命中 4 条：
1. 第 0 条 | user/message | 2026-09-20T08:41:15Z
   片段：梯度下降是什么
2. 第 1 条 | assistant/message | 2026-09-20T08:41:15Z
   片段：梯度下降是一种优化方法 search_kb {"query":"梯度"}
3. 第 3 条 | tool/result | 2026-09-20T08:41:15Z
   片段：命中：梯度下降 很长的工具输出 …
4. 第 7 条 | compaction | 2026-09-20T08:41:15Z
   片段：## 已完成 - 讲过梯度下降

引用这些内容时写成「会话 demo-s1 第 N 条」，**不要**写成 `文件:行号`（那是知识库文档的形状）。

# ② session_trace（有派生子会话 / 无亲无故）
会话 demo-s1 — 梯度下降是什么
创建时间：2026-09-20T08:41:41Z

祖先（由近及远）：
- 无（目标即根会话）

后代：
  - demo-child — 派生会话里的一问 | 2026-09-20T08:41:41Z

会话 demo-solo — 孤零零的一轮
创建时间：2026-09-20T08:41:41Z

祖先（由近及远）：
- 无（目标即根会话）

后代：
- 无

（本地会话格式不记录 `parentSession`：没有 fork/派生会话 ⇒ 每个会话都是根、都没有后代。）

# ③ session_event_trace（seq=0，被 compaction 替换）
会话 demo-s1 — 梯度下降是什么
目标：第 0 条 | user/message | 2026-09-20T08:41:15Z
被替换为：第 7 条
替换链：第 7 条
被目标替换的事件：无
直接引用的源事件：本地事件格式不记录 `sourceEventSeqs` ⇒ 无从给出（上游按该字段计算）
由目标派生的事件：同上，本地不落盘任何派生/引用关系 ⇒ 无从给出

（本地「替换」口径：`compaction` 的 `shadowed` 与 `compaction/prune` 的 `pruned[].seq` 覆盖的事件，与回放一致。）

# ④ session_event_read（seq=3, before=1, after=1）
会话 demo-s1 — 梯度下降是什么
目标事件（第 3 条，完整未删节）：
```json
{ "v": 1, "seq": 3, "time": 1789893675747, "type": "tool/result", "data": { "id": "c1", "name": "search_kb", "content": "命中：梯度下降 …" } }
```

之前的事件：
- 第 2 条 | tool/call | 2026-09-20T08:41:15Z | （无语义文本）

之后的事件：
- 第 4 条 | user/message | 2026-09-20T08:41:15Z
  那学习率呢

# ⑤ 失败码（逐条实测）
[session_event_search] {"session_id": "nope"} -> NOT_FOUND：会话 'nope' 不存在
[session_event_search] {"session_id": "../escape"} -> INVALID_ARGUMENTS：非法会话 id：'../escape'（只允许字母数字与 . _ -）
[session_event_search] {"time_from": "2026-09-20T09:00:00"} -> INVALID_ARGUMENTS：必须是带时区限定的 ISO 8601 时间戳（`Z` 或 `±HH:MM`）
[session_event_trace] {"seq": 42} -> NOT_FOUND：会话 "demo-s1" 没有第 42 条事件
[session_event_read] {"before": 51} -> INVALID_ARGUMENTS：before 必须是 0..50 的整数（收到 51）
[session_event_read] {} -> INVALID_ARGUMENTS：seq 必填

# ⑥ 命中上限（105 条命中 ⇒ 只出 100 条 + 提示）
事件命中 100 条：
1. 第 0 条 | user/message | 2026-09-20T08:41:15Z
…
（已达结果上限 100 条：请收窄 query 或加过滤条件以看到其余。）
```

**语义偏差与取舍（上游 → 本地）**：

1. **`search_sessions` 保留原名（不新增 `session_search`）**：上游叫 `session_search`（单数）、返回**按会话分组的会话命中**；本地 §6.9 已落 `search_sessions`（复数）并带 `limit`。**取舍**：不并置两个近义工具（多付一份 schema token 且模型易混），故**只承认名字偏差**；上游 `session_search` 的 11 个过滤器（`session_ids` / `created_at_from|to` / `parent_session_ids` / `include_root_sessions` / `availability` / `event_*` 六项 / `event_surfaces`）**仍未移植**（本地只有 `query` + `limit`）。
2. **无调用方会话身份 ⇒ 四个工具的 `session_id` 全部必填**：上游 `session_id` 可省（= 当前会话，`index.ts:84-86`）。本地 `Tool.handler` 只拿得到参数、拿不到「哪个会话在调用」，`build_kb_tools()` 也未绑定 session ⇒ 省略即**参数错误**（fail-closed），不猜一个会话。**连带**：事件检索「在当前会话上截断到本次调用之前」（`operations.ts:128-139`）与 `SESSION_QUERY_TOOL_NO_CURRENT_STEP` 都没有本地落点。
3. **「替换关系」换了数据来源（本地缺 `foldSurface`）**：上游 `replacedBy` / `replacedEventSeqs` 来自表面折叠（影子事件 `surfaceOp: replace`，`tracing.ts:181-220`）；本地事件面**没有** surfaceOp/阴影语义，承载替换的是 `compaction.shadowed` 与 `compaction/prune.pruned[].seq`（口径与 `history.py` 回放一致：被覆盖的 seq 不再进模型请求）。**`sourceEventSeqs` / `derivedEventSeqs` 无从计算** ⇒ 返回 `None`，工具文本明说原因（**不伪造「无」**：与「确实没有」区分开）。
4. **无 `surfaces` 过滤**：上游事件检索/会话检索都有 `current` / `shadowed` / `log-only` 三值；本地没有「表面」概念（§6.9 已登记），故该参数不出现。
5. **无 `availability` / `parent_session_ids` / `include_root_sessions`**：上游按 live/persisted 双来源与父会话过滤；本地语料全是磁盘文件、且此前没有 `parentSession` 数据（见偏差 8）。
6. **不移植配置面与协作截止**：上游 `maxSearchResults`（默认 100，部署可调）与 `searchTimeoutMs`（默认 30000）来自插件 `Config`；本地无 cordis.yml ⇒ 上限取**上游默认值**常量（`SESSION_EVENT_HITS_CAP = 100` / `SESSION_EVENT_HITS_CAP + 1` 的探针判 `capped`），**不做 30s 截止**（扫描已被「单文件 2 MiB × 跨会话份数」四重有界化约束，与既有 `search_sessions` 同口径）。**模型不可调上限**这一点与上游一致（schema 里没有 `limit`）。
7. **无授权/净化层**：上游按调用方 `cwd` 精确相等授权（`workspace-access.ts`），越权是 `SESSION_QUERY_TOOL_UNAUTHORIZED`；本地工具面作用域天然 = 本库会话目录（`build_kb_tools(kb_path)` 已绑定），故不需要授权步与对应错误码。
8. **`session_trace` 的「本地恒为根」是事实、不是伪造**：算法与上游逐条同构（`parentSession` 父链、未解析父会话 ⇒ `complete=false`、后代按 `createdAt` 再按 id 排序、成环报错）；但**本地没有任何写入方生产 `parentSession`** ⇒ 实际每个会话都是根、都没有后代。工具文本在两者皆空时补一句如实说明；一旦将来有写入方落该键（例如 fork），`session_trace` 无需改动即可给出真谱系。**偏差**：上游结果里的 `Availability`（live/persisted）与 `[outside workspace]` 边界标记不打印（本地无 live 源、无授权边界）。
9. **ISO 8601 → 毫秒截断**：上游保留亚毫秒余数并用 `nextUp/nextDown` 夹紧端点（`input.ts:236-264`）；本地按**毫秒**截断、端点为闭区间 ⇒ 亚毫秒精度的边界可能有 1ms 级差异（事件时间本身就是整毫秒，实际不可见）。
10. **结果文本落为中文、并保留本地「引用形状」约定**：`seq N` 写成「第 N 条」、`Snippet:` 写成「片段：」、`Session <id> — <title>` 写成「会话 <id> — <标题>」；两个搜索工具都带一句「引用时写成『会话 <id> 第 N 条』，**不要**写成 `文件:行号`」（与 §6.9 同一口径：对话命中不是文档出处）。**不移植**：上游的 surface 列、`Availability`、游标/偏移字面量（本地本就没有）。
11. **精读窗口按事件下标取、两端夹紧**：上游 `startSeq = max(0, seq - before)`、`endSeq = min(len-1, seq + after)`（`index.ts:379-380`）——本地以**下标**实现同一语义（不假设 `seq == 下标`，逐条比对取出下标）；缺目标 ⇒ `SessionQueryNotFound` ⇒ 工具面 `NOT_FOUND`（上游 `SESSION_QUERY_EVENT_NOT_FOUND`）。
12. **错误码取本地既有码族**：参数/作用域非法 ⇒ `INVALID_ARGUMENTS`、目标不存在 ⇒ `NOT_FOUND`（上游是 `SESSION_QUERY_INVALID_FILTER` / `SESSION_QUERY_INVALID_WINDOW` / `SESSION_QUERY_*_NOT_FOUND`）。**语义一致点**：坏作用域（目录穿越 `../x`、非法 id）一律**明确拒绝**，绝不静默返回空结果（有单测与实测输出为证）。
13. **不移植上游的固定指引段**：上游在 system prompt 里注入一句固定指引（`PROMPT_TEXT`，`index.ts:51-54`、`:59-63`），本地 §6.9 起就**未**注入 ⇒ 本轮沿用（避免动 §6.14/§6.16 刚定的提示词段落与 KV 前缀）。**登记为剩余缺口**（见下「已知缺口」）。

**验收证据**：

| 手段 | 结果 |
|---|---|
| `py_compile`（`session/query.py` / `tools/kb.py` / 2 个测试文件） | 全过 |
| `python -m pytest tests/ -q` | **308 passed**（原 285 + 本轮新增 **23** 例 `tests/test_agent_session_query_trace.py`；既有测试仅 1 处断言语义更新 —— `tests/test_agent_tools_read.py:416` 的「末尾三工具」改为「读面三工具相对次序」） |
| 真实行为取证（Python 级；仓库外临时脚本，跑完即删） | 见上「模型看到的文本」六段；另实测：`KB_TOOL_NAMES` 与 `build_kb_tools()` 实际注册顺序**逐项一致**（13 个）、`read_only` 全为真、`before.maximum == MAX_READ_WINDOW == 50`、105 条命中只出 100 条 + 上限提示、`session_trace` 在有/无父会话两种会话上分别给出后代与「本地不记录 `parentSession`」说明、`session_event_trace` 对「被 compaction 覆盖」与「被 prune 覆盖」两种 seq 都给出正确替换链 |
| 覆盖点 | 常量与上游一致（50 / 100 / `pruner.PRUNE`）；`read_event`（窗口夹紧、默认仅目标、左端夹 0、`True`/小数/字符串/越界窗口一律报错、目标与会话缺失、目录穿越）；`trace_event`（compaction 与 prune 两类替换、替换链、后写覆盖、引用字段恒 `None`）；`session_lineage`（根会话、父链「由近及远」、后代树按深度、未解析父会话、成环报错、目标缺失）；四个工具的模型可见文本（命中/片段/上限提示/完整 JSON/邻接摘要/`（无语义文本）`/谱系/替换关系/`无从给出`）；注册与 schema（必填项、`additionalProperties: false`、`before.maximum`、追加顺序在末尾）；fail-closed（`NOT_FOUND` / `INVALID_ARGUMENTS` 逐条） |
| 依赖面 | **纯标准库**（`re` / `datetime` / `calendar` 均为函数内局部导入），零新依赖 ⇒ 打包体积不变 |
| 行号 | 两个源文件**全部为文件尾追加 + 等量改写**（`query.py` 3 处、`kb.py` 2 处）⇒ §5.1/§6.9/§6.16 引用的既有 `file:line` **零漂移**；唯二重取的是 `reference/agent-guide/10` 里指向 `session/query.py` 的行范围块（旧 `1-380` → 新 `1-679`，见「文档」） |
| 上游检出未被改 | `git -C dsh-src status --porcelain` **空**；`git -C dsh-src rev-parse HEAD` = `0d1f50007f9bca3f52b06e1c3074fa14d5fb0720` |

**已知缺口（本轮未做）**：① 上游 `PROMPT_TEXT` 固定指引段仍未注入（偏差 13）；② `session_search` 的 11 个过滤器、`surfaces` 维度未移植（偏差 1/4/5）；③ `capped` 事实仍不进 `search_session()` 的返回（§6.9 偏差 6 未变；新工具靠「多要一条」探针自判）；④ 本地无 `parentSession` 写入方 ⇒ `session_trace` 实际恒为「根 + 无后代」（偏差 8）；⑤ 不移植上游游标分页与 `searchTimeoutMs`。

**未实测**：① 真实模型端点下模型**是否会正确选工具**（该用 `session_event_search` 时不用 `search_sessions`、拿到命中后是否接着 `session_event_read` 取原文）—— 只做静态 + 单测 + Python 级真实调用；② 大库（数百份会话 / 数 MiB 会话文件）下 `session_lineage` 的**墙钟耗时**（有界性有设计约束，未做 A/B 计时）；③ 真机面板端到端（本轮零前端改动，且没有浏览器工具）；④ 上游 dsh 真机上的对照行为（未运行 `dsh`，全部依据只读检出）。

**文档**：`conventions/docs-management.md §4.2` 本轮登记行（`:162`）；`reference/agent-guide/10` 三处**等量改写**（工具面计数行 `181`「6 → 9 → **13**」、会话检索工具段 `226`、§6 证据锚行 `431` —— 三行都是单物理行改写 ⇒ **行号零漂移**）；本文件 §5.1 会话检索行 + 三段结论中的 ①③、§8「M2 已落地部分」与「已转 ✅」口径、§11 变更记录本轮行（`:1341` —— **原 `:1218`，随 §6.18 插入整体下移，已重取**）。**锚点重取（old → new）**：`reference/agent-guide/10` 的 `services/agent/session/query.py:1-380` → **`:1-679`**（同块内新增 `read_event`/`trace_event`/`session_lineage` 与常量行）、`tools/kb.py:566-592` → **`:581-607`**（该行随 §6.16 重取，本轮沿用）；**§6.17 自身两次取号的更正**：本轮新增块 `_session_event_search` `:1295-1361` → **`:1297-1363`**、`_session_trace` `:1364-1411` → **`:1366-1413`**、`_session_event_trace` `:1414-1464` → **`:1416-1464`**、`_session_query_tools` `:1508-1603` → **`:1510-1605`**、`_epoch_ms` `:1207-1238` → **`:1208-1240`**（写作时点与验收时点的行号复取）。`tools/kb.py` 的**既有**引用（`:73-80`、`:83-84`、`:446-482`、`:581-607`、`:460`、`:523-550`、`:610-665`、`:688`、`:730-776`、`:793-839`、`:911-1072`、`:1088-1162`）**全部未动**（本轮对 `kb.py` 只有文件尾追加与等量改写）。**台账**：`docs/todo.md` **未编辑**（另一写者并发重写中；建议台账行见本轮报告）。

---

### 6.18 引用板块（R 线）实施记录（2026-09-20：只读「引用解析」+「引用审计」，已落地）

> 用户口径「把引用板块做了」。它是**读侧**能力、不动上游一行：把库里五种引用（`@路径` / `dsh-session:` / `[[…]]` / `文件:行号` / `![](...)`）做成两把**只读**工具 —— `resolve_reference`（解一条）与 `audit_references`（查一批）。前置关系：§6.13 的 A 子项（文件内选区引用）与写侧（M3）都要求「先能**准确解析**目标」，本板块就是那个前置。
> **路线来源**：台账 **AG07**（`docs/todo.md:265`，K2 路线已定）与 [agent-capabilities.md §6.5](agent-capabilities.md)（`agent-capabilities.md:447-481`）已经拍板的 **P（提示词收窄语法）+ V（程序校验 + 用库内清单分级收敛）+ L（改读时投影）**，以及紧随其后的「**不要做**」清单。本节按它实现，**不另立口径**。

**范围界定（本期只覆盖库内五类引用）**：

| 引用 | 解析路径（复用件，全部实读） | 状态词 |
|---|---|---|
| `@相对路径`（含 `@"带空格"`、目录尾斜杠） | 正则逐字对齐前端 `MENTION_RE`（`ui/static/app/js/agent-panel.js:125`）；路径校验走**允许根**（`tools/kb.py:1142` `_read_roots()` / `:1147` `_resolve_in_read_roots()`，经 `:793` `_safe_rel_any()`）；库内清单来自 `:819` `_walk_kb_files()` | `ok` / `not_found` / `ambiguous` / `rejected` |
| `@[label](dsh-session:…)` / 裸 URI | 复用 `session/reference.py:101` 的 `_MENTION_RE`（单一事实源，两处语法不再各写一份）+ `:142` `decode_session_uri()`；文件走 `session/store.py:61` `session_file()`（非法 id 直接抛错 ⇒ fail-closed） | `ok` / `not_found` / `invalid` / `rejected` |
| `[[…]]`（id / 别名 / 文件名 / 多目标） | `link_resolver.py:33` `scan_wikilinks()` + `:49` `resolve_link_target()`（全局 id / file stem）；别名与挂接见偏差 3。**`[[\…]]` 是字样式命令、不是链接**（2026-09-22 修：目标段排除反斜杠，见 `_WIKILINK_RE` 行注） | `ok` / `not_found` / `ambiguous` |
| `文件:行号` / 区间 | 正则字符类对齐前端 `ANCHOR_RE`（`agent-panel.js:117`），另补 `#L12-L30` 与全角 `：`；行号对照剥 frontmatter 的正文行（`tools/kb.py:175` `_read_body_lines()`，与 `read_document` 同一行空间） | `ok` / `not_found` / `ambiguous` / `rejected` / **`unsupported`** |
| `![](...)`（`.memoria/images/**` + registry 登记态） | 复用 `document.py:1151` `_parse_image_ref_url()`（可注册性）、`:1167` `diagnose_image_refs()`（全库口径）、`:987` `_load_image_registry()`（**只读、不重建**）、`:937` `_doc_image_names_from_body()` | `ok` / `not_found` / `invalid` / `unsupported` / `rejected` |

**明确不做（写进两把工具的描述，避免模型误以为能解）**：① **块级引用**（代码块 / 表格 / 公式）—— 需要新的稳定块标识，属另一设计；② **选区 / 片段引用**（区间末端的读时投影、对话片段引用）—— 属 §6.13 的 A / B 子项。**L 路线本轮未实施** ⇒ 区间锚点一律如实回 `unsupported`（只核起始行、明说「不校验末端、不声称区间语义已被解析」），**不假装能解**。

**三条路线逐条落法**：

1. **P**（提示词收窄语法）= **已由 `prompt.FILE_REFERENCE_SECTION` 承载**（`prompt.py:208-218`，要求引用取自工具回显的 canonical 路径），本轮**不重复实现**、也不动提示词（保住 §6.14/§6.15 刚定的段落顺序与 KV 前缀）。
2. **V**（本块核心）= 三级：**V1 归一化**（`_reference_normalize()`，NFKC → 按终止字符截断 → 剥引号/CJK 括注/反引号 → `\`→`/` → 去 `./` 前缀）；**V2 分级收敛**（`_reference_converge_file()`：**精确 → 唯一 basename → 唯一后缀**，任一级命中 >1 即 `ambiguous` 并回候选，**绝不猜**）；**V3 回灌**（`not_found` 当**普通工具结果**返回：「真实情况 + 下一步」，**不自动重试**、不扩正则）。
3. **L**（改读时投影）= **未实施**（见上）。§6.5 落地顺序第 5 条只允许「读取时投影」这一种形态，本板块没有渲染层可投影 ⇒ 宁可回 `unsupported`。

**改动**（1 个源文件 + 1 个新测试文件 + 1 个既有测试文件 1 行断言；`kb.py` 为**文件尾追加 + 2 处等量改写** ⇒ 既有 `file:line` 零漂移）：

- `services/agent/tools/kb.py`
  - **文件尾追加 986 行**（`git diff --numstat` 实测：新增 991 / 删除 5 = 追加 986 + 2 处改写 5 行；追加段 `kb.py:1606-2591`，其中块注释起 `:1608`；代码本身 `:1608-2591` = 984 行）：常量 `REFERENCE_MAX_CHARS = 512`（`:1640`）/ `REFERENCE_MAX_CANDIDATES = 10`（`:1642`）/ `REFERENCE_AUDIT_MAX_ISSUES = 100`（`:1644`）/ `REFERENCE_KINDS`（`:1647`）；正则三条 `_FILE_MENTION_PATTERN`（`:1669`）/ `_ANCHOR_REF_PATTERN`（`:1674`）/ `_IMAGE_REF_PATTERN`（`:1686`）；共用件 `_reference_normalize()`（`:1725`）/ `_reference_converge_file()`（`:1749`）/ `_reference_rel_in_roots()`；五个解析体 `_resolve_file_reference()`（`:1837`）/ `_resolve_session_reference()`（`:1917`）/ `_resolve_kp_link_reference()`（`:1970`）/ `_resolve_anchor_reference()`（`:2015`）/ `_resolve_image_reference()`（`:2099`）＋ `_reference_image_registry()`（`:2090`）；分派表 `_REFERENCE_RESOLVERS`（`:2187`）与自动识别 `_detect_reference_kind()`（`:2196`）；工具体 `_resolve_reference()`（`:2214-2235`）；审计 `_audit_document()`（`:2272-2466`，五类逐条扫）与 `_audit_references()`（`:2468-2521`）；声明工厂 `_reference_tools()`（`:2526-2591`，两把 `Tool` 均 `read_only=True`、`additionalProperties: false`）。
  - **等量改写 2 处（零行漂移）**：`KB_TOOL_NAMES` 13 → **15** 个名字（`:73-80`，8 行等量改写）；`build_kb_tools()` 返回元组末行 `), *_session_query_tools(root),` → `), *_session_query_tools(root), *_reference_tools(root),`（`:665`）。
- 测试：新增 `tests/test_agent_tools_reference.py`（**12 例**，含 fixture 库 + 逐检查名计数断言 + 零写入断言）；`tests/test_agent_session_query_trace.py:487` 一行断言由「末尾四工具」改为「末尾四工具仍连续 + 其后接 R 线两工具」。

**模型看到的文本（逐字，仓库外临时脚本实测；节选）**：

```text
# ① resolve_reference（精确 / 唯一 basename 收敛 / 多义 / 行号越界）
引用解析：@notes/b.md
- 类型：file（`@路径` 文件引用）
- 归一化目标：notes/b.md
- 状态：ok（已解析）
- 指向：知识库文档 notes/b.md（共 3 行，1 个知识点）
- 建议下一步：read_document(path="notes/b.md")

引用解析：notes/c.md:3
- 类型：anchor（`文件:行号` 锚点）
- 状态：ok（已解析）
- 指向：sub/c.md 第 3 行：第一行。          ← 按唯一 basename 从 `notes/c.md` 收敛到 `sub/c.md`
- 建议下一步：read_document(path="sub/c.md", offset=3, limit=1)

引用解析：@same.md
- 状态：ambiguous（多目标歧义（未猜））
- 候选（共 2 个，最多列 10 个）：
  1. dup1/same.md
  2. dup2/same.md
- 原因：库内有 2 个同名 / 同后缀文件（basename 级命中 >1）—— 程序不猜

引用解析：notes/c.md#L2-L4
- 状态：unsupported（本地不支持）
- 指向：起始行 L2 在范围内（目标 `sub/c.md`）
- 原因：区间锚点本地无法可靠解析：没有「读时投影」能力（§6.5 L 路线未落地），故只核起始行、**不校验末端**，也不声称区间语义已被解析

# ② resolve_reference（会话 / 歧义 / 图片 / 越界 / 坏 URI）
引用解析：@[上次](dsh-session:ImRlbW8tczEi)
- 类型：session（`dsh-session:` 会话引用）   - 状态：ok（已解析）
- 指向：会话 `demo-s1`（标题：第一句提问）
引用解析：@../outside.md                    - 状态：rejected（越界拒绝）  - 原因：路径在允许根（知识库根）之外，或含上跳 `..` —— 工具面 fail-closed 拒绝
引用解析：@[坏](dsh-session:%%%)             - 状态：invalid（token 非法） - 原因：URI 非规范（`decode_session_uri()` 拒绝…）
引用解析：![pic](.memoria/images/pic.png)    - 状态：ok  - 指向：文件存在；registry.json 已登记（引用方：notes/a.md）

# ③ audit_references（fixture 库全库；逐条 = 检查名 / 位置 / 目标 / 问题 / 严重级）
引用审计：扫描 全库 5 篇 .md，发现 16 个引用问题（已列 16 条：error 6 / warning 10）。
- [error] file_reference.missing @ notes/a.md:3 目标 @notes/missing.md：库内不存在该文件（精确 / 唯一 basename / 唯一后缀三级都未命中）
- [error] file_reference.outside_root @ notes/a.md:5 目标 @../outside.md：路径在允许根之外或含上跳 `..`，fail-closed 拒绝
- [warning] file_reference.ambiguous @ notes/a.md:7 目标 @same.md：多义：`dup1/same.md`、`dup2/same.md`（程序不猜，用完整相对路径重写）
- [warning] kp_link.body_not_attached @ notes/a.md:9 目标 [[b-kp]]：正文出现但未挂接（sidecar `instances` / `excluded` 里没有本行）
- [warning] kp_link.ambiguous_target @ notes/a.md:9 目标 [[dup-kp]]：`by_id` 内多条同 id 记录：…（不猜）
- [warning] anchor.range_unsupported @ notes/a.md:11 目标 notes/c.md:2-4：区间锚点：本地没有读时投影（§6.5 L 路线未落地）⇒ 只保证起始行、不校验末端（不假装能解）
- [error] image.unregistered @ notes/a.md:15 目标 ![sp](.memoria/images/my pic.png)：裸 URL 含空白 ⇒ 图片注册规则识别不到…
- [warning] image.not_registered @ notes/a.md:16 目标 ![unreg](.memoria/images/unregistered.png)：`.memoria/images/unregistered.png` 不在 `registry.json` 的 refs 里
检查名（可用 resolve_reference 逐个复现）：file_reference.missing / … / image.not_registered

# ④ 上限（limit=3）与边界
（已达上限 3 条：还有 13 条未列出；请用 `path` 参数收窄到单篇文档）
[resolve_reference] reference="" -> INVALID_ARGUMENTS：reference 不能为空
[resolve_reference] kind="bogus" -> INVALID_ARGUMENTS：未知 kind 'bogus'（可选 file、session、kp_link、anchor、image…）
[resolve_reference] reference="x"*513 -> INVALID_ARGUMENTS：reference 过长（513 字符 > 上限 512）
[resolve_reference] reference="???": INVALID_ARGUMENTS：无法识别引用类型
[audit_references] path="../outside.md" -> INVALID_ARGUMENTS；path 缺文件 -> NOT_FOUND
```

**语义偏差与取舍（AG07 三路线 → 本地）**：

1. **V2 只取三级收敛，**不吃** §6.5 的「模糊（尾部元素加权，学 fzf）」**：§6.5「不要做」第 3 条明确「短 basename 上极易误并；误并比漏并更糟」。本地把 ①精确 ②唯一 basename ③唯一后缀 做成**硬闸门**，>1 一律 `ambiguous` + 候选 ⇒ 目标口径「**零误跳 + 可解释的候选**」（§6.5 结语）。
2. **L（读时投影）未实施 ⇒ 区间锚点 `unsupported`**：这是本轮**最主要的有意缺口**。工具仍给出「起始行在/不在范围内」这一条可用事实，但**明说**不校验末端、不声称区间语义已解析（对应 §6.5「不要假装能解」）。**取舍**：宁可让模型退回单行锚点（`x.md:12`）或自己 `read_document(offset=…)`，也不产出一个我们无法兑现的区间语义。
3. **别名（`links[].anchor_text`）与「正文出现但未挂接」按**文档上下文**判定**：`resolve_reference` 只拿得到一条 token（没有所在文档），故只做**全局**解析（kp_id / file stem）并在文本里明说「别名与挂接需要文档上下文，请对含该 token 的文档跑 `audit_references`」；逐处判定落在审计侧（复用 `document.py:2145` `_resolve_scan_link_entry()` + `link_instances.py:380` `is_line_attached()`）。
4. **V1 的「终止字符」集与前端 `ANCHOR_RE` 同源**（CJK 标点 / 成对括号 / 引号之后不属于路径）：好处是 `@a.md（说明）` 这类正文标注不再被当成文件名的一部分（实测修掉了一处误报）；**已知取舍**：文件名里若真含 `（）` 或 `，`，会被截断 ⇒ 现记为**已知限制**（真实库中未实测到此类文件名，见「未实测」）。空白**不**参与截断（`@"含 空格.md"` 的空白是路径的一部分，对齐上游 `formatFileMention`）。
5. **图片引用只覆盖 `.memoria/images/**`**：非库内 URL（外链 / 其它目录）回 `unsupported`（明确「不支持」而不是瞎解析）；registry 状态**只读 `registry.json`**（`_load_image_registry()`，**不用** `_registry_ensure()`/`rebuild_image_registry()`）⇒ 注册表缺失时如实说「登记状态无法判定」，**不伪造「已登记」**，也不为一次只读调用去写库。
6. **会话引用作用域限本库**（`session_file()` + 文件存在性）：`dsh-session:` 的 URI 解码成功但 id 形状非法（含 `..` / 空白等）⇒ `rejected`；URI 非规范 ⇒ `invalid`；文件不存在 ⇒ `not_found` 并说明「会话按库分，不跨库」（与 `agent_session_load` 同口径）。
7. **审计语料 = `collect_md_files()`**（与 `validate_kb` / `diagnose_image_refs` 同口径）：不含 `.memoria/**`（那是产品元数据，不是知识正文）⇒ 不审 `kb-spec.zh-CN.md` 一类文件，避免噪声。
8. **上限 100 条 + 「已达上限」提示，但计数保持完整**：超限时**继续计数、只截显示**（照 `grep` 的 `命中 N/M 处` 做法），文案给「还有 N 条未列出 + 用 `path` 收窄」。
9. **错误码取本地既有码族**：参数非法（空 / 未知 kind / 超长 / 未知形态 / `limit` 越界 / `path` 越界）⇒ `INVALID_ARGUMENTS`；目标文档不存在 ⇒ `NOT_FOUND`（工具体内部另有**业务**状态词表 `ok` / `not_found` / `ambiguous` / `invalid` / `rejected` / `unsupported`，与错误码分离 —— 一条「解析不到」的引用是**正常结果**，不是工具失败）。
10. **不改会话 / 事件日志、不新增事实源**：两把工具全程在 `kb_read_only()` 守卫内（`kb.py:103`），零写入（有单测以文件清单前后比对为证）。

**验收证据**：

| 手段 | 结果 |
|---|---|
| `py_compile`（`tools/kb.py` / `tests/test_agent_tools_reference.py`） | 全过 |
| `python -m pytest tests/ -q` | **320 passed**（原 308 + 本轮新增 **12** 例 `tests/test_agent_tools_reference.py`；既有测试仅 1 处断言更新 —— `tests/test_agent_session_query_trace.py:487`） |
| 真实行为取证（Python 级；仓库外临时脚本，跑完即删） | 见上「模型看到的文本」四段；另实测 `KB_TOOL_NAMES` 与 `build_kb_tools()` 实际注册顺序**逐项一致**（**15** 个）、两工具 `read_only=True`、`kind` 枚举 = 五类、`limit > 100` 与 `limit = 0`（直连工具体）都报错、`resolve_reference` 与 `audit_references` 调用前后 fixture 库文件清单**逐字不变** |
| 覆盖点 | `@路径`（精确 / 唯一 basename 收敛 / `@"带空格"` / 目录尾斜杠 / 悬空 / 多义 / 上跳）；会话（规范 / 裸 URI / 悬空 / 坏 URI / 非法 id）；`[[…]]`（id / 悬空 / 跨文件同 id 歧义 / 未挂接）；锚点（精确 / 全角冒号 + `L` 前缀 / 越界行 / 区间 `unsupported` / 文件不存在 / 上跳）；图片（已登记 / 缺文件 / 不可注册 / 注册表缺失 / 非库内）；审计（14 类检查名的**逐条计数**、形状（检查名 / `文件:行` / 目标 / 问题）、上限提示、`path` 收窄、干净文档回「未发现问题」）；边界（空 / 未知 kind / 超长 / 未知形态 / 多余参数 / 越界 `path`） |
| 依赖面 | **纯标准库**（`re` / `unicodedata` 均为函数内局部导入），零新依赖 ⇒ 打包体积不变 |
| 行号 | `kb.py` 仅**文件尾追加**（`:1608-2591`；**§6.20 再追加至 `:2710`；§6.21 再追加至 `:2821`**）+ **2 处等量改写**（`:73-80`、`:665`）⇒ §5.1/§6.16/§6.17 引用的既有 `file:line` **零漂移**；本轮新增引用的外部行号已逐处实读（`agent-panel.js:117`/`:125`、`session/reference.py:101`/`:142`、`session/store.py:61`、`link_resolver.py:25`/`:41`、`link_instances.py:380`、`document.py:937`/`:987`/`:1151`/`:1167`/`:2145`） |
| 上游检出未被改 | 本轮**未读**上游（R 线是本地独有能力的补齐，不是上游移植）；`dsh-src/` 未触碰 |

**已知缺口（本轮未做）**：① **L 路线（读时投影）未实施** ⇒ 区间锚点只能 `unsupported`（偏差 2）；② 块级引用（代码块 / 表格 / 公式）与选区 / 片段引用**不在本期范围**（工具描述里已声明）；③ §6.5 的「模糊级收敛」按「不要做」清单**有意不采纳**；④ 别名 / 挂接的逐处判定只在 `audit_references` 侧（偏差 3）；⑤ 文件名含 CJK 标点时的截断限制（偏差 4）；⑥ **写侧不做** —— 本板块是 M3（plan + 编译器）的前置，写能力仍按 [agent-capabilities.md](agent-capabilities.md) 的插件契约走。

**AG07 的状态变化（只在本节记录；`docs/todo.md` 未编辑）**：AG07 记的 K2 三路线里，**P 已在 §6.7 落地、V 由本轮落地（读侧）**，**L 与「写侧按引用改写正文」仍未做** ⇒ AG07 从「⏳ 路线已定」推进到「**V 已落地（读侧）/ L 未实施**」；台账行**未由本轮改写**（另一写者正在并发重写 `docs/todo.md`），建议文字见本轮报告。

**未实测**：① 真实模型端点下模型**是否会主动用**这两把工具（先 `resolve_reference` 自检再写 `文件:行号`）；② 大库（数千篇 md）下 `audit_references` 的墙钟耗时（有界性只体现在**输出条数**，**未做**文件数 / 字节级预算，也未做 A/B 计时 —— 已知取舍）；③ 真实用户库中「文件名含 CJK 标点 / 括号」与「`@路径` 紧跟中文标点」的实际分布（fixture 只覆盖构造样例）；④ 真机面板端到端（本轮零前端改动）；⑤ 与 `dsh` 真机的对照（**不适用**：上游没有引用解析能力，本板块是本地独有）。

**文档**：`conventions/docs-management.md §4.2` 本轮登记行；`reference/agent-guide/10` 工具面计数行 **等量改写**（13 → **15**）；`reference/agent-guide/06` 新增一节「引用解析与审计（agent 侧只读）」；本文件 §5.1 五行（`@路径` / 跨会话 / `[[id]]` / `文件:行号` / 块级·片段）+ §11 变更记录本轮行。**锚点重取（old → new）**：本轮 `kb.py` 只有文件尾追加与等量改写 ⇒ **无 old → new**；`reference/agent-guide/10` 里 `tools/kb.py:1608-2591` 是本轮新增块的**首次**取号（旧文未引用）；**本文件内部的旧锚 `:1218`（§6.17 轮次的 §11 行）→ `:1436`**（§6.18 插入 122 行、§6.19 再插入 95 行 ⇒ 其后行号整体下移，仅此一处需重取；`docs/design/dsh-agent-port.md:245`（§6.14 引用）在插入点**之前**，未动）。**台账**：`docs/todo.md` **未编辑**（另一写者并发重写中；建议台账行见本轮报告）。

---

### 6.19 用户报障修复：引用会话"解析不到任何东西" + 选区悬浮「加入对话」（2026-09-20）

> 用户原话：「首先我尝试引用会话发给 agent，agent 的回复是解析不到任何东西；第二，我在文件内（不论源码或者预览区）
> 以及对话栏拖拽选取之后，没有在选区附近悬浮显示『添加到对话 chat』」。本节记录**两条真实用户报障**的取证、根因与处置。

#### 6.19.1 #1 引用会话 → 模型"解析不到任何东西"（P0）

**全链路取证（真实数据，非推断）**——用用户的真实会话（`docs/example/AAA_Vocab/.memoria/agent/sessions/*.jsonl`）在仓库外临时脚本里跑真实管线：

| 环节 | 实测结果 |
|---|---|
| 前端 token（`agent-panel.js` `sessionUri()` → `formatSessionMentionToken()`） | 与后端 `encode_session_uri()` **逐字节相同**（node 实算 `dsh-session:InNlc3Npb24tMjAyNjA5MThUMTYzMDE0Wi04YWMwNmVkNSI` vs Python 同值；无填充 base64url ✓） |
| `parse_session_references()` | 命中并改写：`请参考 @[源会话标题](dsh-session:…) 总结一下` → `请参考 @源会话标题 总结一下`，`references=[{session_id, label}]` ✓ |
| `build_snapshot()`（**同库、非自引用**） | 正常：快照含 `源会话的答案` 等真实正文 ✓ |
| `ask()` 组装的请求 | `rendered_text + "\n\n" + snapshot + "\n\n" + 时间读数` ✓（`ask.py:445` 的既有拼装未变） |

⇒ **正常路径完全没坏**。坏的是**两条"静默变空"路径**（同一根因：mention 留在了请求里，内容与说明都丢了）：

1. **自引用**（引用"当前会话自己"）：`build_snapshot(exclude_session_id=…)` 走 `continue` 丢弃来源，`planned` 为空 ⇒ **直接返回 `None`** ⇒ `ask()` 只发 `rendered_text`。**改前实测（真实会话 id）**：
   `请参考 @本轮会话 总结\n\n当前本地时间：2026-09-20T19:14:24+08:00`（**整段快照不存在** ⇒ 模型手里只有一个光秃秃的 `@标签`）。
   **可达性**：面板会**自动恢复上次会话**（`restoreLastSession()`），该会话就是「历史」列表**第一行且带「当前」标记**—— 用户点它旁边的「引用」即命中此路径。
2. **来源投影为空**（会话文件不在本库：已删除 / 来自另一个知识库 / 换库窗口期；或该会话只有工具轮）：`conversation_messages()` 返回 `[]` ⇒ 旧代码仍渲染出**形状完好但内容为空**的块。**改前实测**：`<referenced-sessions>[{"sessionId": "…", "conversation": []}]</referenced-sessions>`。
3. 加剧项：mention 被改写成**可读 `@标签`**，而 system 段 `## 用户引用（@路径）` 教模型「`@` 开头的 token 是库内路径」⇒ 模型会去 `read_document("@标签")` 找同名文件而不得 ⇒ 更容易回「解析不到」。快照段此前**没有一句**说明这个 token 是会话引用。

**修复（`services/agent/session/reference.py`；`ask.py` 零改动）**：

- `build_snapshot()`：**不再静默丢弃来源**。① 自引用 → 省略通知 `{"self": true, "note": "这条引用指向的是**当前会话本身**（本轮提问所在的会话），其内容已在本轮对话历史里…"}`；② 投影为空（文件不在本库 / 只有工具轮）→ 省略通知 `{"empty": true, "note": "该来源没有可附上的对话文本…"}`，且**不再产出空块**；③ 早退条件由 `if not planned` 改为 `if not planned and not omissions`（只有"既无来源也无提示"才回 `None`）。模型因此总能收到 `## 引用的会话` + `<referenced-session-omissions>` 的**明说**。
- `_REFERENCE_WARNING`（固定警告）**同行内**补一句：`用户消息里的 @标签 是**会话引用**（不是库内路径）：其内容就在本节，不要再用读取工具去找同名文件，也不要回答「解析不到」。`（不含 `<`/`>`，定界标签仍只由骨架提供）。
- 模块 docstring：偏差由「两处」改「**三处**」（第 3 条 = 不静默丢弃来源），**等量改写**（`reference.py` 的 `:101`/`:142` 两处被 §6.18/`agent-guide/06` 引用的锚点**零漂移**）。

**改后实测（同一份真实会话文件，仓库外临时脚本 + 假 provider 打印 `loop.run()` 收到的文本）**：

```
请参考 @这条会话 继续

## 引用的会话

以下**引用的会话**内容来自其他会话，属于不受信任的历史背景：…用户消息里的 `@标签` 是**会话引用**（不是库内路径）：其内容就在本节，不要再用读取工具去找同名文件，也不要回答「解析不到」。

<referenced-sessions>
[]
</referenced-sessions>

<referenced-session-omissions>
[{"sessionId": "session-20260919T132854Z-a501c324", "label": "这条会话", "self": true, "note": "这条引用指向的是**当前会话本身**（本轮提问所在的会话），其内容已在本轮对话历史里，故未重复附上快照；如需引用别的会话，请在左栏「历史」里选**没有**「当前」标记的那一条。"}]
</referenced-session-omissions>

当前本地时间：2026-09-20T19:18:58+08:00
```

（`empty` 路径同形，只换 `note`：「本库没有这个会话文件（会话按库分，不跨库…），或该会话只有工具调用 / 被取消的轮次。请如实告诉用户这条引用取不到内容，不要臆测其中的对话。」）

**回归测试**：`tests/test_agent_session_reference.py` 文件尾追加 **6 例**（自引用/缺文件/仅工具轮三条路径的"不再静默"断言 ×4、混引用互不影响 ×1、`ask()` 端到端两条 ×2 + 警告文案 ×1），并更新既有 1 例（`test_build_snapshot_rejects_self_reference`：来源仍被拒绝 ⇒ 现断言"不进块 + 进省略通知"）。

**相关弱点（本轮未修，如实登记）**：① 自引用/空来源在**面板侧**没有即时反馈（用户点「引用」看不出这条会被忽略）—— 要修得靠前端 chip/提示，属 UI 项；② `conversation_messages()` 的投影**只出 user + 每轮最终 assistant**，工具轮与思考一律不进快照 ⇒ "只有工具轮的会话"内容上确实为空（本轮改为明说，不假装有内容）；③ 会话文件损坏（非撕裂尾行）仍会让 `read_session()` 抛 `ValueError` 冒泡到 RPC（fail-loud，未改成省略通知）。

#### 6.19.2 #2 选区悬浮「加入对话」：**从未存在**，本轮补最小版

**真相（grep 取证，非假设）**：全前端**不存在**该 affordance —— `加入对话` / `添加到对话` / `add-to-chat` / `selection-bubble` / `selAdd` 在 `app/**` **零命中**；`insertMention()` 的唯一调用点是**文件树拖拽**（`agent-panel.js:1401`）；`-sel-*` 仅 `app.css:4245` 的公式块选区高亮（`.-math.-sel-covered`）；`sel-source.js` 只做**选区渲染**（跨行拖拽/Shift 选择），没有任何"选区 → 对话"入口。⇒ 本条**不属于"坏了的既有功能"**，属**未实现**。

**实现（最小版；1 个前端模块 + CSS + 2 个 i18n 键）**：
`agent-panel.js` 文件尾追加块（`agent-panel.js:2964-3077`）+ `app.css` 文件尾追加块（`app.css:5615-5641`）+ `i18n/{zh-CN,en}.js` 尾部各 2 键（`agent.selAddAction` / `agent.selAddTitle`）。

**交互契约（逐条）**：

| 维度 | 行为 |
|---|---|
| 何时出现 | 选区**非空**（`getSelection()` 非折叠且 `toString().trim()` 非空）且 `range.commonAncestorContainer` 落在 `#preview`（预览区）或 `#editor`（源码区）内，且**已打开文件**（`state.currentPath` 非空）⇒ 在选区**上方居中**显示（贴视口顶时改落选区下方），`position: fixed; z-index: 62` |
| 何时消失 | 选区变空 / 点别处（`mousedown` capture，点按钮自身除外）/ **任意滚动**（`scroll` capture，内层容器也算）/ `Esc` / 换文件（选区自然消失）/ 窗口 `resize` |
| 点它做什么 | 复用**文件树拖拽那条** `insertMention(state.currentPath, "file")` ⇒ 把 **`@相对路径`** 插到输入框的**上次光标位置**（`inputCaret` 同一条语义、同一落点规则），随后收掉按钮 |
| 产生的 token（**精确**） | **只有** `@相对路径`；路径含空格时为 `@"路径"`（与 `formatMention` 同口径）。**选中的文字本身不进请求、也不生成区间 token** —— 片段级引用（`@路径#L12-L30` / 摘录直塞）属 §6.13 A 项、规格未定，本版**不发明语法**（模型拿到 `@路径` 后自行 `read_document`） |
| 不碰什么 | 文件树拖拽落点、既有选区渲染（`sel-source.js`）、消息气泡的 mention 渲染（`linkifyUser`）；本块只**读**选区 + 维护一个浮动按钮 |
| 已知限制 | 面板 dock 处于折叠态时也照样插（token 在输入框里，展开即可见；**未**做自动展开或 toast 反馈）；预览区/源码区以外的选区（如对话栏消息区）**不支持** |

**对话栏（消息级）选区**：**本轮明确不做** —— "选中某条回复 → 引用"需要新的片段 token（`dsh-session:<uri>#msg:<seq>` 一类）或"单消息投影"，即 §6.13 **B 项**（并入台账 AG01，仍 ⏳ 待规格化）。在规格拍板前**不发明**该 token。

**验收证据**：

| 手段 | 结果 |
|---|---|
| `py_compile`（`session/reference.py` / 新测试） | 全过 |
| `python -m pytest tests/ -q` | **326 passed**（原 **320** + 本轮新增 **6** 例；既有断言更新 **1** 处 = 自引用例） |
| `node --check`（`agent-panel.js` / `zh-CN.js` / `en.js`） | 3/3 通过 |
| `node scripts/i18n_selftest.js` | **12/12 PASS** |
| `python scripts/scan_ui_strings.py`（本轮以临时脚本把 `OUT` 改到临时文件，**未覆盖** `docs/reference/i18n-inventory.md`） | `files=3 rows=5`（**无新增硬编码候选**） |
| 真实数据复现（仓库外临时脚本，跑完即删） | #1 改前/改后请求文本见 §6.19.1（真实会话文件，非构造样例） |
| HTTP 静态面（harness `http://127.0.0.1:8660/`，服务活文件） | `curl … /app/js/agent-panel.js` 含 `-agent-sel-add`（`:2980`）/`selAddAction`（`:3042`）；`/app/css/app.css` 含 `.-agent-sel-add`（`:5623`）；`/app/i18n/zh-CN.js` 含 `"加入对话"`（`:1327`） |
| 依赖面 | 零新依赖（Python 侧纯标准库；前端纯原生 API） |

**未实测**：① **浏览器 DOM 交互**（本轮**没有浏览器工具**）—— "拖选 → 按钮出现 → 点击 → token 落在上次光标处 / 滚动与 Esc 收掉 / 与文件树拖拽互不干扰"这五步只有静态与 HTTP 面证据，**留给协调者真机走查**；② 真实模型端点下自引用/空来源 notice 是否足以让模型如实回答（本地只保证"请求里有明说"）；③ 对话栏消息级选区（未做）。

**文档**：本节 + `reference/agent-guide/01`「选区悬浮『加入对话』」行 + `conventions/docs-management.md §4.2` 本轮登记行 + §6.13 的 C 行状态推进 + §11 变更记录本轮行。**锚点重取（old → new）**：`reference/agent-guide/10` 的 `zh-CN.js:1322 / en.js:1410`（原为两语言包**末行**）→ `zh-CN.js:1320 / en.js:1408`（改为 `agent.generating` 键**声明行**，因两包末尾各追加了 8 行 `selAdd` 块）；`dsh-agent-port.md:1229`（§6.18 的「文档」行）内部锚 `:1341` → `:1436`（本节插入 95 行 ⇒ 其后行号整体下移）。**其余既有 `file:line` 零漂移**：`session/reference.py` 的两处被引用锚（`:101`/`:142`）在改动点**之前**、`ask.py` 本轮**未改一行**、`agent-panel.js`/`app.css`/两语言包均为**文件尾追加**。**台账**：`docs/todo.md` **未编辑**（另一写者并发重写中）。

---

### 6.20 选区引用的「位置」+ 气泡入口 + 打字框 chip（2026-09-20，三项一并落地）

> 用户原话：「内容显示区（both 源码和预览）可以拖拽选取加入对话了，但是实际写入对话的仍然只是
> `@文件名`，根本没有标出对应内容的源码位置等，而对话栏仍然不能悬浮显示加入对话；另外，引用仍是
> `@` + 纯文本而不是在打字框里面把引用渲染一下」。本节按这三条逐项记录 —— §6.19.2 的 v1
> 口径（"只有 `@相对路径`、对话栏消息区不支持"）**由本节取代**，§6.18 的「区间锚点一律回
> `unsupported`」也**由本节取代**（该两处历史行只在下方列出被取代的断言，不改写历史记录）。

#### 6.20.1 A：选区引用必须带**位置**（AG07 的 **L 路线：读时投影**）

**token 语法（最终形态，保守，只有这两种，不发明第三种）**：

| 形态 | 例子 | 说明 |
|---|---|---|
| 行区间 | `@docs/a.md#L12-L30` | `<起>` ≤ `<止>`；**相对库根的路径**，与 `@路径` 同一路径口径 |
| 单行 | `@docs/a.md#L12` | 选区落在同一行 |
| 含空格路径 | `@"docs/IELTS vocab.md"#L12-L30` | 引号只包**路径**，`#L…` 在引号**之外**（与 `formatMention` 的 `@"…"` 同族） |

前端产出点：`agent-panel.js` 末尾追加块的 `formatRangeMention()`（`agent-panel.js:3192`）。

**选区 → 源码行号（诚实分级）**：

| 宿主 | 行号来源 | 精度 |
|---|---|---|
| 源码区 `#editor` | 每个行元素 `.-line[data-line]`（`sourceLineAt()`，`agent-panel.js:3095`）；终点恰停在下一行**第一个文本节点**的 0 偏移时收一行（`endLineAt()`，`:3103`） | **精确行号**（1 起，与 `read_document` 同一行空间） |
| 预览区 `#preview` | 块的 `data--src-line` / `data--src-line-end`（`previewBlockRange()`，`:3113`；终点落在下一块块首时回上一块末行，`prevPreviewBlockEnd()`，`:3123`） | **块级近似**（边界块的首/末行取块自身的源码行区间；**非字符级**）。理由：字符级映射所需的 `. -seg[data-line]` 由 `annotateSegments()`（`markdown-preview.js:1252`）生成，但**全仓没有调用点**（`grep annotateSegments` 只命中定义与导出）⇒ 现状拿不到字符级映射，**不假装有** |
| 取不到行号 | 回 `@路径`（既有 `formatMention`），**不编造行号** | — |

**后端（L 路线落地）**：`services/agent/tools/kb.py` 文件尾追加块 +
`_resolve_anchor_reference()` 的区间分支改为**委托调用**（`kb.py:2077-2081`，§6.21 重取：原 `:2067-2071`）：

- `_at_range_parts()`（`kb.py:2673`，§6.21 重取：原 `:2621`）：识别 `@路径#L12-L30` / `@"含 空格"#L12-L30` / 单行 `#L12` ⇒ `(路径, 起, 止或 None)`；
- `_anchor_range_result()`（`kb.py:2696`，§6.21 重取：原 `:2635`）：解析到 `_read_body_lines()` 的**当前正文行**并双向校验 ⇒
  `ok`（`指向：<file> 第 12-30 行（N 行）：首行 … / 末行 …` + `read_document(path=…, offset=12, limit=19)`）/
  `invalid`（**倒置**）/ `not_found`（任一端越界，报出越界的那一端）/ `rejected` / `ambiguous` / `not_found`（文件级）；
- `_detect_reference_kind()` 在 `@`→file 之前先判区间形态 ⇒ `@路径#L12-L30` 归 **anchor**；
- `audit_references`：① `@路径` 扫描**跳过**区间 token（避免误报 `file_reference.*`），④ 锚点扫描**剥掉 `@`** 后按区间校验 ⇒
  检查名 `anchor.range_inverted`（**新**，替换已不可产的 `anchor.range_unsupported`）、越界复用既有 `anchor.line_out_of_range`；
- **投影口径 = 只回行号与首末行，不把区间正文塞进结果**（与 AG07/§6.5「只允许读取时投影形态」一致）⇒
  请求体积不因选区而膨胀，正文始终由模型自己 `read_document(offset, limit)` 取。

**提示词**：`prompt.FILE_REFERENCE_SECTION` 第 2 条**同行内**补一句（`prompt.py:215`，
**行数不变 ⇒ §6.14/§6.15 定的段落顺序与 `prompt.py:208-218` 锚点零漂移**）：
「结尾的 `#L12-L30` 是**行区间**（`#L12` 为单行）—— 应当用 `read_document` 的 `offset`/`limit` 去读那一段，而不是假设自己看过了；」。

#### 6.20.2 B：对话栏（消息气泡）选区也能悬浮「加入对话」

**触发范围**：`selAddHit()`（`agent-panel.js:3179`，整函数重绑）在 §6.19 的 `#preview` / `#editor` 之外
**追加** `#agent-messages`；浮动按钮本身（`#-agent-sel-add`）、出现/消失规则（滚动 / Esc / 点别处 / resize）**全部复用**。

**「气泡 → seq」映射（本轮新增的唯一新事实）**：`conversation_messages()`（`session/history.py:494-497` 文档、`:506`/`:514`/`:527` 实现）
给每条渲染记录**追加 `seq` 键**：

| 气泡 | `seq` 取值 |
|---|---|
| user 气泡 | 该轮 `user/message` 事件的 `seq` |
| assistant 气泡 | 该轮**最后一条非空** `assistant/message` 的 `seq`（= 界面上那条最终答案，与文本口径同源） |

前端把它落在气泡 DOM 上（`data-agent-seq`，由 `loadSession` 包装器在 `agent_session_load` 返回后按顺序标上）；
选区落在哪个气泡 ⇒ 取该气泡的 `seq`；**跨气泡** ⇒ `[起, 止]` 两个气泡的 `seq`。
**实时生成中的当轮气泡没有 `seq`**（会话尚未重新载入）⇒ `selectionLocation()` 回 `null` ⇒ 既不显示按钮也不产出 token（**不猜**）。

**token 语法（最终形态）**：`@[<label>](dsh-session:<base64url>#seq:<n>)`，跨消息 `#seq:<起>-<止>`；
`<label>` = 左栏「历史」里该会话的标题（缺省回会话 id），URI 与转义复用既有 `sessionUri()` / `formatSessionMentionToken()`
（`agent-panel.js` 的 `sessionFragmentToken()`，`:3201`）。

**后端解析（`session/reference.py`）**：

- 新增 `split_session_fragment()`（`reference.py:528`）+ `_SEGMENT_RE`（`:525`，`#seq:(\d+)(?:-(\d+))?$`
  —— **`$` 锚定**，中段的 `#seq:` 不当片段）；**先切片段、再对 base64 部分做原有的规范化往返校验**
  （`decode_session_uri()` 函数体内一行换调，`:145`，**行号未变**）；
- `_MENTION_RE` 的**裸 URI 分支**尾部放宽为可带片段（`reference.py:102`，唯一的本地扩展）；
- `parse_session_references()` 命中时**追加** `seq_from` / `seq_to` 两个键（`:198`；**无片段的项形状逐字不变**）；
- `build_snapshot()` 对带片段的引用**只投影落进该区间的消息**（复用 `conversation_messages()` 的 `seq` 键）；
  去重键升为 `(session_id, 片段)`；片段落不到任何消息时记 `{"fragment": true, "seq": "99-120", "note": …}` 省略通知
  （**越界 / 指向工具或推理事件都不静默**）。**无片段引用的行为与去重键都逐字不变**（回归测试对照证明）。

**两层错误口径**：**语法层**（倒置 `#seq:9-3`）⇒ `SessionReferenceError`（明确报错）；
**存在层**（序号在该会话里落不到任何对话消息）⇒ 快照里的 `fragment` 省略通知。

#### 6.20.3 C：打字框里**渲染**引用（chip）

方案 = **镜像层**（不破坏 textarea 语义）：在 `.-agent-composer` **末尾追加** `.-agent-composer-mirror`
（`composerMirrorEl()`，`agent-panel.js:3296`；**不插进 `#agent-statusbar` ↔ `#agent-input` 之间** ——
那一对紧邻是 01 篇已实测的 DOM 事实，`bar.nextElementSibling === input` 必须继续成立），
用**同一套**字体 / 字号（`--agent-font-size`）/ 行高 1.45 /
内距 `0.3125rem 8px` / `white-space: pre-wrap` 渲染同一段文本，把 token 包成 chip；
textarea 自身文字**透明**（`color: transparent` + `caret-color` 保留 ⇒ 光标仍闪），光标 / 选区 / 输入法仍归 textarea。

| 要求 | 落法 |
|---|---|
| token 形态 | `@路径`、`@"含空格"`、`@路径#L12-L30`、`@[label](dsh-session:…#seq:<n>)`（`COMPOSER_TOKEN_RE`，`:3248`） |
| **不错位** | chip **逐字保留 token 原文**（不缩短、不加 padding / 字号）⇒ 镜像与 textarea 同宽；`#L…` 与 `--session` 只用**颜色 / `box-shadow`** 区分 |
| 同步 | `input`/`keyup`/`change`/`paste`/`cut`/`drop`/`scroll` + `window resize` + `MutationObserver(#-agent-dock.style)`（抓 `--agent-font-size`）+ 三个**包装器**（`insertMention` / `insertSessionToken` / `ask`，覆盖程序化插入与发送清空，`:3349-3367`） |
| 零视觉差异 | 无 token（或面板收起、量 0）⇒ 摘掉 `.-on` 与 `.-agent-chips-on` ⇒ 镜像 `display:none`、textarea 恢复原样式 |
| 不动既有逻辑 | `inputCaret` / `insertMention` / `insertSessionToken` 的插入规则与 `ask()` 发送逻辑**一行未改**；CSS 全部进 `app.css` 末尾追加块 |
| 分层 | 镜像 `z-index: 0`（在 textarea 之下）、textarea `z-index: 1` ⇒ 背景由镜像提供、光标与选区仍可见 |

**已知取舍**：选区高亮（`::selection`）会盖住该范围内的 chip 文字颜色（textarea 的选区矩形在镜像之上）——
已把选区底色设为 `var(--theme-color)`，不做进一步规避。

**验收与未实测**：见 §6.20.4 / §6.20.5。

#### 6.20.4 验收证据（本机实测）

| 手段 | 结果 |
|---|---|
| `python -m pytest tests/ -q` | **335 passed**（原 **326** + 本轮新增 **9** 例：`tests/test_agent_session_reference.py` 文件尾 9 例；`tests/test_agent_tools_reference.py` **无新增函数**、改 1 例断言 + fixture 末尾 +1 行 + 期望表换 1 项） |
| `python -m py_compile`（`tools/kb.py` / `session/reference.py` / `session/history.py` / `prompt.py`） | 4/4 过 |
| `node --check`（`agent-panel.js` / `zh-CN.js` / `en.js`） | 3/3 过 |
| `node scripts/i18n_selftest.js` | **12/12 PASS** |
| 行为取证（仓库外临时脚本，跑完即删） | ① `@a.md#L3-L5` ⇒ `状态：ok（已解析）` + `指向：a.md 第 3-5 行（3 行）：首行 第三行 / 末行 第五行` + `read_document(path="a.md", offset=3, limit=3)`；`@a.md#L5-L3` ⇒ `状态：invalid（token 非法）` + `行区间倒置…`；`@a.md#L3-L99` ⇒ `状态：not_found（目标不存在）` + `第 99 行超出 …（该文档正文共 7 行）`。② `@[片段](…#seq:3)` ⇒ `refs=[{session_id, label, seq_from: 3, seq_to: 3}]`，快照 `conversation=[{"role": "assistant", "text": "第二答（就是要引用的那一段）"}]`；`#seq:2-3` ⇒ 两条消息；**无片段** ⇒ 四条消息逐字照旧。③ `ask()` 最终请求文本 = `只看这段 @片段` + `## 引用的会话` + `<referenced-sessions>[…第二答…]</referenced-sessions>` + 时间读数 |
| HTTP 静态面（harness `http://127.0.0.1:8660/`，服务活文件） | `/app/js/agent-panel.js` 含 `data-agent-seq` / `bubbleSeq` / `return end > start ? head + "#L" + start + "-L" + end : head + "#L" + start;` / `-agent-composer-chip` / `selAddActionSeq`；`/app/css/app.css` 含 `.-agent-composer-mirror.-on` / `#agent-input.-agent-chips-on` / `.-agent-composer-chip`；`/app/i18n/zh-CN.js` 含 `selAddTitleSeq` |
| 依赖面 | 零新依赖（Python 纯标准库；前端纯原生 API） |

#### 6.20.5 未实测 / 未做

① **浏览器 DOM 交互全线未实测**（本轮**没有浏览器工具**）：镜像层是否与 textarea 逐像素对齐（含滚动 / 手动 `resize` / 字号切换 / 多行换行）、气泡选区的按钮出现与 `#seq:` 落点、预览区块级行区间的**用户可感精度** —— 这四项只有静态（`node --check`）与 HTTP 面证据，**留给协调者真机走查**。
② 实时（未重载）的当轮气泡**拿不到 `seq`** ⇒ 不能引用（有意为之，`conversation_messages()` 是唯一 seq 事实源）；③ 预览区仍是**块级**近似行区间（字符级映射缺调用点，见 §6.20.1）；④ 选区文本仍**不进请求**（只给位置，正文由模型自取 —— 这是 AG07 L 路线的既定口径，不是缺口）；⑤ 块级引用（代码块 / 表格 / 公式）仍未解。

#### 6.20.6 文档与锚点重取（old → new）

**文档**：本节 + `reference/agent-guide/01`（前端：选区 token / 气泡入口 / 打字框 chip 三小节）+
`conventions/docs-management.md §4.2` 本轮登记行 + §11 变更记录本轮行 + `reference/agent-guide/06 §2.10`
三处**原位等量**校正（区间 `unsupported` → L 路线；`decode_session_uri()` 的 `:142` → `:143`；块区间
`:1608-2591` → `:1608-2710`）。

**锚点重取**：

- `services/agent/tools/kb.py:1608-2591` → **`:1608-2821`**（§6.21 重取；本轮当时为 `:1608-2710`）（本轮 **+119 行**：文件尾追加块 `:2601-2710` **110 行** + 原位改写 **+9 行**；引用处 **2 个**：
  本文件 `:1220`、`agent-guide/06-links-and-graph.md:218`，均已就地更新）；
- `agent-panel.js:2964-3077`（§6.19 的追加块）、`app.css:5615-5641`、`zh-CN.js:1320` / `en.js:1408`、
  `session/reference.py:101`、`prompt.py:208-218`/`:215`/`:261`/`:263`、`ask.py:445`、`session/history.py:261-299`、
  `tools/kb.py` 的 `:175`/`:665`/`:819`/`:1142`/`:1147`/`:1749` —— **全部零漂移**（本轮改动都落在其**之后**或为等量改写）；
- **本轮新取的锚**：`agent-panel.js:3095`/`:3103`/`:3113`/`:3123`/`:3179`/`:3192`/`:3201`/`:3248`/`:3297`/`:3349-3367`、
  `kb.py:2077-2081`/`:2673`/`:2696`（§6.21 重取：原 `2067-2071`/`2621`/`2635`）、`reference.py:102`/`:145`/`:198`/`:525`/`:528`、`history.py:494-497`/`:506`/`:514`/`:527`；
- **校正一处既有 off-by-one**：`agent-guide/06:223` 的 `session/reference.py:142` → **`:143`**
  （`def decode_session_uri` 在本轮之前**已经在 143**，非本轮移动）。

**台账**：`docs/todo.md` **未编辑**（另一写者并发重写中，本轮只报建议）—— 建议把 **AG07** 从
「P 已落地 / V 已落地（读侧）/ L 未实施」推进为「**P + V + L 全部落地（读侧）**；仅剩「写侧按引用改写正文」未做」。

**被本节取代的历史断言（只列出处，不改写历史行）**：§6.18 表格行的 `锚点 … **`unsupported`**`（本文件 `:1122`）、
§6.19.2 的「token **只有** `@相对路径`…不生成区间 token」（`:1303`）与「对话栏消息区**不支持**」（`:1305`/`:1307`）。

### 6.21 列号 + 输入框**原子块** + 对话内引用渲染（2026-09-20，三项一并落地）

> 用户原话：「显示区域引用定位得有开始行号字符号和结束行号字符号，而且在对话框渲染是把引用视作一个块整体
> 删除或者光标整体跳过，而且对话内的引用没有渲染，也没有开始结束的标记」。本节是 §6.20 的直接续写：
> §6.20 的 token 只有**行**，本节把「位置」补到**行:列**，并解决输入框与气泡两侧的**呈现**问题。

#### 6.21.1 A：选区引用带**列号**（P 线语法扩展 + V 线校验）

**token 语法（最终形态；保守扩展，旧形态逐字兼容）**：两端各写成 `L<行>` 或 `L<行>C<列>`：

| 形态 | 例子 | 说明 |
|---|---|---|
| 行+列区间 | `@docs/a.md#L3C2-L5C7` | 列 **1 起**，**字符位置**语义（行首 = 1，行末 caret = 行长 + 1） |
| 混写（只写一端） | `@docs/a.md#L3C2-L5` | **缺列 = 行首 / 行末**（起端缺 ⇒ 行首；止端缺 ⇒ 行末），不猜具体列 |
| 单点 | `@docs/a.md#L3C2` | 落在同一行的一个字符位 |
| 向后兼容（不变） | `@docs/a.md#L12-L30` / `@docs/a.md#L12` | 老 token **逐字照旧**（列缺省 ⇒ 只投影行范围） |
| 含空格路径 | `@"docs/A B.md"#L3C2-L5C7` | 引号只包**路径**，`#L…` 在引号之外（与 §6.20 同口径） |

**不发明第三种分隔符**：仍然只有 `#L…`（P 收窄语法的"保守"要求）；`文件:3C2`（冒号形态带列）**不是**本块语法，
`_resolve_anchor_reference()` 只在 `sep == "#"` 且带列时才走列分支 —— 认不出就交给别的引用类型，**绝不猜**。

**前端产出（诚实分级；`agent-panel.js` 文件尾追加块）**：

| 宿主 | 行 / 列来源 | 精度 |
|---|---|---|
| 源码区 `#editor` | 行 = `.-line[data-line]`（`sourceLineAt()`，`:3095`）；列 = **行内字符偏移 + 1**（`lineContentOffset()` `:3408` 只数 `.-line-content` 内的文本节点 —— **不数行号列** `.-lineno`，也不数 `. -sync-cursor` 之类视觉注入；`editorPoint()` `:3445`） | **行 + 列都精确**（列 = 1 起字符位置；与后端同一字符计数口径，CRLF 的 `\r` 与 `\n` 都不计、TAB 计 1） |
| 预览区 `#preview` | 仍是块级 `[data--src-line][data--src-line-end]`（`previewBlockRange()` `:3113` / `prevPreviewBlockEnd()` `:3123`），**列恒缺省** | **行是块级近似、列明确不给**（字符级映射所需的 `annotateSegments()` 仍**全仓无调用点**）⇒ 产出 `#L12-L30`，不假装有列 |
| 取不到行号 | 退回 `@路径`（既有 `formatMention` 口径，纯函数里同样兜底） | 不编造 |

- 终点恰停在**下一行行首**（源码区）⇒ 收回到上一行且**列缺省**（= 上一行行末），不多算一行。
- 拼写的**唯一事实源** = 纯函数 `rangeTokenText()`（`:3456`，不碰 DOM）；`formatRangeMention` 重绑为它的薄壳
  （`:3509`），落点仍是既有 `insertSessionToken()`（上次光标处，规则一行未改）。

**后端（`services/agent/tools/kb.py`）**：

- `_AT_RANGE_PATTERN`（`:2665`）两端各加可选 `C(\d+)`；`_at_range_parts()`（`:2673`）返回 **5 元组**
  `(路径, 起行, 起列或 None, 止行, 止列或 None)`（两个调用方只做 `is not None` 判断 ⇒ 不受影响）；
- `_anchor_range_result()`（`:2696`）加两个可选列参数并**在原有行校验之后**加列校验：
  **列越界**（`col < 1` 或 `col > 行长 + 1`）⇒ `not_found`（报出「第 X 行第 C 列超出（该行共 N 个字符，合法列 1..N+1）」）；
  **同行列倒置**（`止列 < 起列`）⇒ `invalid`；行倒置仍优先于列（先判行）；
- **输出**：带列时 `指向：<file> 起 3:2 → 止 5:4（3 行）：首行 … / 末行 …`（缺列那端写「行首 / 行末」）；
  单点带列写 `第 3 行第 2 列：…`；**无列时输出与 §6.20 逐字一致**（有回归测试对照）；
- `_detect_reference_kind()` 先判区间形态 ⇒ 带列 token 归 **anchor**（不会掉进 `@`→file 分支）；
- `audit_references`：④ 锚点扫描改用同一 `_ANCHOR_REF_PATTERN`（新增 `sep` / `startcol` / `endcol` 组）⇒
  **列越界复用 `anchor.line_out_of_range`**、**同行列倒置复用 `anchor.range_inverted`**（不新增检查名 ⇒
  `_REFERENCE_AUDIT_CHECKS` 与既有台账零漂移）；① `@路径` 扫描对区间 token 的跳过**放宽到带列形态**，
  并顺手剥掉紧贴 token 的中文标点再判（否则 `@a.md#L3C2-L5C4。` 会被误报 `file_reference.missing`）。
- **投影口径不变**：只回「起止 + 首末行摘要 + `read_document(offset, limit)` 建议」，**不塞正文**。

**提示词**：`prompt.FILE_REFERENCE_SECTION` 第 2 条**同行内**补列号说明（`prompt.py:215`，**行数不变**）。

#### 6.21.2 B：输入框里的引用是**原子块**

`agent-panel.js` 文件尾追加块（`bindComposerAtomicTokens()` `:3576`）：用**镜像层同一解析器**
`COMPOSER_TOKEN_RE` 算 token 区间（`composerTokenSpans()` `:3531`），在 `#agent-input` 的 **capture 阶段** `keydown` 上拦截：

| 键 / 状态 | 行为 |
|---|---|
| `Backspace`，caret **恰在** token 尾（`pos === span.end`） | **整体删掉这一个 token**（`replaceInputRange()`：`execCommand("insertText","")` ⇒ 浏览器撤销栈里算**一次**编辑；不可用时退回 `setRangeText`） |
| `Delete`，caret **恰在** token 首（`pos === span.start`） | 同上（整体删） |
| `←` / `→`，caret **落在 token 内部** | 整体跳到该 token 的**首 / 尾**（不在 token 中间停留） |
| 整块被选中（`start===span.start && end===span.end`）或 caret **贴边** | 镜像层给该 chip 加 `.-agent-composer-chip--active`（原子块的视觉反馈） |
| 有选区（非折叠）时按这些键 | **不拦**（交给浏览器：整体覆盖删除本就是一次编辑） |
| `e.isComposing` / `keyCode === 229`（输入法组字中）、任何修饰键（`ctrl/meta/alt/shift`，含 Shift 选区） | **一律不碰** |
| Enter 发送 / Shift+Enter 换行 | 不碰（原有 `keydown` 处理器一行未改） |
| 粘贴 / 拖放 / `inputCaret` 记账 / 镜像几何同步 | 不碰；编辑后调 `afterComposerEdit()` 记 `inputCaret` 并同步镜像（另加 `select` / `mouseup` 监听以刷新高亮） |

**`<textarea>` 下仍做不到的（如实登记）**：① 无法让**跨 chip 的选区**在视觉上只高亮 chip 部分（选区由 textarea 自绘，
镜像层只能整体换色，`::selection` 会盖住 chip 文字色 —— §6.20 已记的同一取舍）；② 无法把 chip 变成**真正的不可分割对象**：
`Home/End`、双击选词、`Ctrl+←/→` 按词跳、鼠标点击落在 chip 内部等路径**仍会在 token 中间落 caret**（本轮只覆盖
Backspace / Delete / ← / → 四条主路径）；③ 撤销**粒度由浏览器定**（`execCommand` 路径能合并为一次，`setRangeText` 退回路径不保证）。

#### 6.21.3 C：对话内引用渲染（user + assistant，含**起止**）

**扫描器 `REF_MENTION_RE`（`:3750`）只认两种**：① 会话**片段** `@[label](dsh-session:…#seq:n)`；② 文件**区间**
`@path#L…C…`（普通 `@路径` 与无片段会话仍交给既有 `linkifyUser` / `renderAssistantBody`，**不抢它们的活**）。

| 侧 | 落法 | 覆盖 |
|---|---|---|
| **user 气泡** | 在既有（会话 aware 的）`linkifyUser` 包装层**之外**再包一层（`:3758`）；命中段直接出 chip，未命中段交给内层 | 区间引用 + 会话片段引用（**旧的「片段显示成裸文本 / 被误当文件 chip」由此修掉**） |
| **assistant 气泡** | 包装 `renderAssistantBody`（`:3835`）：既有 marked→净化→锚点化**跑完**后，对**文本节点**做一次替换（`chipRangeRefsInDom()` `:3790`） | 同一批 token；**代码块 / 行内代码**（`code`/`pre`/`kbd`/`samp`）、`script`/`style`/`textarea`、**公式**（`katex`/`math` 类）与**已完成锚点化的 `-agent-anchor`** 之内的文本**一律跳过**；raw HTML 在 `sanitizeHtmlInto` 阶段已按白名单拆壳，故无需另判。流式渲染也走同一入口（§6.20 的 AG11 包装调的就是 `renderAssistantBody`） |

**起止怎么展示**：chip 正文 = `路径 起–止`（如 `mlp.md 12:5–14:20`；单点只写一个；缺列只写行 —— 与 token 语义一致），
`title` 用 `agent.rangeChipTitle`（zh：「引用：{path} 起 {from} → 止 {to}…」）把「起 / 止」写全；点击复用既有锚点委托
（`data-agent-file` / `data-agent-line`）⇒ 打开文件并高亮**起始行**。会话片段 chip 追加 `.-agent-mention-seq`
（`#seq:` 的起止序号），`title` 用 `agent.sessionChipTitleSeq`。

#### 6.21.4 验收证据（本机实测）

| 手段 | 结果 |
|---|---|
| `python -m pytest tests/ -q` | **341 passed**（原 **335** + 本轮新增 **6** 例：`tests/test_agent_tools_reference.py` 尾 **3** 例、新文件 `tests/test_agent_panel_token.py` **3** 例；既有断言**零改动**） |
| `python -m py_compile`（`tools/kb.py` / `prompt.py` / 两个测试文件） | 4/4 过 |
| `node --check`（`agent-panel.js` / `zh-CN.js` / `en.js`） | 3/3 过 |
| `node scripts/i18n_selftest.js` | **12/12 PASS** |
| `python scripts/scan_ui_strings.py` | `files=3 rows=5`（**无新增硬编码候选**；重生成的 `i18n-inventory.md` 只有「生成日期」变，**已还原**为 `2026-09-19` ⇒ diff-free） |
| 行为取证（Python 级，仓库外临时库 `kbcol2`，跑完即删） | 见下方四段原始输出 + 审计两行 |
| **前端 token 拼写单测**（`tests/test_agent_panel_token.py`，用 `node` eval **真源码**的 `rangeTokenText`） | 9 条形态逐字匹配；其中 6 条再喂给后端 `_at_range_parts()` **逐字解回**（前后端同一语法）；另有静态断言：`addSelectionToChat` 确实把 `startCol`/`endCol` 传给 `formatRangeMention`，且列来自 `.-line-content` 偏移 |
| HTTP 静态面（harness `http://127.0.0.1:8660/`，服务活文件） | `/app/js/agent-panel.js` 200（**185986 B**：`rangeTokenText`×2 / `-agent-composer-chip--active` / `bindComposerAtomicTokens` / `REF_MENTION_RE`×7 / `chipRangeRefsInDom`×2 / `agent.rangeChipTitle`）、`/app/css/app.css` 200（**161747 B**：`.-agent-composer-chip--active`×2 / `.-agent-mention--range`×2 / `.-agent-mention-seq`×2）、`/app/i18n/zh-CN.js` 200（**63190 B**：`rangeChipTitle` / `sessionChipTitleSeq` / 「起 {from} → 止 {to}」）、`/app/i18n/en.js` 200（**70264 B**） |
| 依赖面 | 零新依赖（Python 纯标准库；前端纯原生 API，`execCommand` 有 `setRangeText` 兜底） |

**原始输出（行为取证）**：

```
### @notes/a.md#L3C2-L5C4
- 状态：ok（已解析）
- 指向：notes/a.md 起 3:2 → 止 5:4（3 行）：首行 abcdefghij / 末行 第三行内容
- 建议下一步：read_document(path="notes/a.md", offset=3, limit=3)
### @notes/a.md#L3C2-L4
- 状态：ok（已解析）
- 指向：notes/a.md 起 3:2 → 止 4:行末（2 行）：首行 abcdefghij / 末行 第二行正文
### @notes/a.md#L5C4-L3C2
- 状态：invalid（token 非法）
- 原因：行区间倒置：起点 L5 在终点 L3 之后（区间须写成 `#L<起>-L<止>` 且起 ≤ 止）
### @notes/a.md#L3C99
- 状态：not_found（目标不存在）
- 原因：第 3 行第 99 列超出（该行共 10 个字符，合法列 1..11）
- 建议下一步：read_document(path="notes/a.md", offset=3, limit=1) 取回该行后按真实字符数重写列号

### audit_references(path="notes/b.md")（同一文档里「正常 / 行倒置 / 列越界」三条 token）
引用审计：扫描 指定文档 `notes/b.md`，发现 2 个引用问题（已列 2 条：error 0 / warning 2）。
- [warning] anchor.range_inverted @ notes/b.md:1 目标 notes/a.md#L5C4-L3C2：区间锚点倒置：起点 L5 在终点 L3 之后（区间须 `#L<起>-L<止>` 且起 ≤ 止）
- [warning] anchor.line_out_of_range @ notes/b.md:1 目标 notes/a.md#L3C99：第 3 行第 99 列超出（该行共 10 个字符，合法列 1..11）
```

（`normal` 那条**不报**、也不产生 `file_reference.*` 误报 ⇒ ①/④ 分工正确。）

#### 6.21.5 未实测 / 未做

① **浏览器 DOM 交互全线未实测**（本轮**没有浏览器工具**）：源码区拖选出的列号是否与用户肉眼一致、
镜像层 `--active` 高亮的观感、Backspace/Delete/←/→ 四条原子路径的真机手感、`execCommand` 撤销粒度、
气泡 chip 在窄栏里的换行 —— 这五项只有静态、单测与 HTTP 面证据，**留给协调者真机走查**；
② 预览区仍是**块级**近似且**不给列**（诚实口径，非缺口）；③ `Home/End`、双击选词、`Ctrl+←/→`、鼠标点进 chip 内部
仍会落在 token 中间（见 §6.21.2 末）；④ 跨 chip 的选区无法只高亮 chip 部分（textarea 自绘选区）；
⑤ 块级引用（代码块 / 表格 / 公式）仍未解（§6.20.5 ⑤ 同）。

#### 6.21.6 文档与锚点重取（old → new）

**文档**：本节 + `reference/agent-guide/01`（前端：§6 新增一行）+ `conventions/docs-management.md §4.2` 本轮登记行。

**锚点重取**（本文件下方编号一律为**改后**值）：

- `services/agent/tools/kb.py:1608-2710` → **`:1608-2821`**（本轮 **+111 行**；`kb.py` 总行数 2710 → **2821**）；
- `kb.py:2067-2071`（`_resolve_anchor_reference()` 区间分支）→ **`:2077-2081`**（上方 Edit 位前移 +10 行）；
- `kb.py:2621`（`_at_range_parts`）→ **`:2673`**；`kb.py:2635`（`_anchor_range_result`）→ **`:2696`**；
- §6.20.1 / §6.18 §「行号」行 / §6.20.6 的**就地更新**处：本文件 `:1357`/`:1359`/`:1360`/`:1220`/`:1457`/`:1463`；
  `reference/agent-guide/06-links-and-graph.md:218`（`:1608-2710` → `:1608-2821`）；
- **零漂移**：`agent-panel.js` 的上方所有锚点（`2964-3077`、`3095`、`3103`、`3113`、`3123`、`3179`、`3192`、`3201`、
  `3248`、`3297`、`3349-3367`）—— 本轮前端改动**全部是文件尾追加**（`agent-panel.js` 3409 → **3855** 行）；
  `app.css:5615-5641`/`5643-5691`（本轮只在其后追加，5691 → **5713** 行）；`zh-CN.js:1320`/`1331-1342`、
  `en.js:1408`/`1420-1434`（本轮只在其后追加，1343 → **1352** / 1435 → **1445** 行）；
  `prompt.py:208-218`/`:215`（同行内追加）与 `:261`/`:263`、`session/reference.py:101`/`:142`/`:143`/`:198`/`:525`/`:528`、
  `session/history.py:261-299`/`:494-497`/`:506`/`:514`/`:527`、`ask.py:445`、`kb.py` 的 `:175`/`:665`/`:819`/`:1142`/`:1147`/`:1749`
  —— **全部零漂移**；
- **本轮新取的锚**：`agent-panel.js:3408`/`:3445`/`:3456`/`:3470`/`:3509`/`:3531`/`:3546`/`:3559`/`:3576`/`:3651`/`:3686`/`:3709`/`:3750`/`:3758`/`:3790`/`:3835`、
  `app.css:5702`/`:5706`/`:5710`、`kb.py:2665`/`:2673`/`:2696`/`:2813`（`_range_col_display`）。

**台账**：`docs/todo.md` **未编辑**（另一写者并发重写中）—— 建议 AG07 补一句「读侧投影已到**列**级（源码区精确；预览区仍块级不给列）」。

**被本节取代的历史断言（只列出处，不改写历史行）**：§6.20.1 表「行区间 / 单行」两种形态（本文件 `:1340-1344`）、
§6.20.3 的 token 形态行（`:1419`）。

---

### 6.22 技能（skill）规则面落地（2026-09-22：吃 `packages/skill` 的规则，**结构按本地重落**）

> 人问「上游 skill 机制可以照搬吗」⇒ 结论：**规则可以照搬、外层结构不能**。本轮把规则落成 v1：
> `services/agent/skills.py`（新）+ `tools/kb.py` 文件末追加只读工具 `skill` + `prompt.py` 追加「可用技能」段。

**上游四块 × 本轮处置**

| 上游块 | 依赖 | 本地 | 处置 |
|---|---|---|---|
| `skill`（注册表：provider 合并 / rank 遮蔽 / 目录与正文两段式） | Cordis `Service` + `ScopedLayers` + `ctx.events` | 无插件运行时、**无 scope 分层**（只有一个 `main` agent） | **规则照搬、结构塌成单层扁平合并**（scope 与"按 (cwd, scope 链, revision) 缓存目录"整块删掉） |
| `skill-filesystem`（根表 / frontmatter / 发现） | 纯 fs + YAML | Python 都能做 | ✅ **照搬**（根表、rank、只认根下一层、宽松布尔、旧键拒绝） |
| `skill-filesystem` 的 **watcher**（~350 行 Chokidar：root/ancestor 双模、rewatch、stability/poll、maxProjects 淘汰） | 常驻 watcher + `fs/observed` 事件 | 无 fs 事件服务；且本地是**知识库根**、不是 git 工程 | ❌ **不搬**：技能目录小、frontmatter 解析便宜 ⇒ **每轮重建目录**（`build_system_prompt()` 每轮都调） |
| `tool-skill`：① `skill` 工具 ② **持久目录消息**（`source.kind='skill-catalog'`，按条目 digest 重发/原地替换） ③ `/name` 手势 | `agent/pre-step` 瀑布 + 消息 `source` + 命令面 | 无 pre-step 挂钩、无消息 source 概念、无命令注册表 | ① ✅ 照搬（名称/参数/三类错误）；② **改落成 system 提示的一段**（与 `FILE_REFERENCE_SECTION` 同构、**不落盘**，同时间上下文口径）；③ ✅ **已补**（2026-09-22，§6.24 —— 前置的命令注册表 §6.23 已落地） |

**照搬的规则清单**（逐条出处见 `services/agent/skills.py` 模块头表）：名字语法 `^[a-z0-9]+(?:-[a-z0-9]+)*$`；
根表 rank（`project-dsh` 100 / `project-agents` 200 / `runtime` 250 / `custom` 300 / `user-dsh` 400 / `user-agents` 500 / `bundled` 600）；
发现只认根的下一层（嵌套 `**/SKILL.md` 不发现）；frontmatter 必填 `name`+`description`、可选 `whenToUse`/`disable-model-invocation`/`user-invocable`；
宽松布尔（`true/yes/on/1` ↔ `false/no/off/0`）与**旧键主动拒绝**；rank → 注册序 → 目录内序 + 同名遮蔽（后者仅 warn）；
`<skill_content>`/`<skill_resources>`/`<skill_instructions>` 渲染（name 走属性转义、提示语走文本转义、**正文逐字不转义**）；
目录行形状与 description 空白折叠 + **500 截断**；目录文案（"只有摘要，**加载前不要照做**"）。

**本地偏差（有意，逐条）**

1. **只吃一个根**：`<kb>/.memoria/agent/skills/**`（source `kb`、rank 100）。上游按 cwd **向上找 `.git`** 定"工程根"再叠 `~/.dsh`、`~/.agents`
   —— Memoria 没有"工程根"概念（app 从任意 cwd 启动，**库才是边界**），而库外根会破坏"允许根"纪律（`tools/kb.py::_read_roots()` 今天只有库根）
   ⇒ **全局技能根留待拍板**；根表按上游形状保留，加根是一行的事。
2. **不做 watcher / 注册表层 / 持久目录消息**（理由见上表；~~`/name` 手势~~ **2026-09-22 已补**，见 §6.24）。
3. ~~**`user-invocable` 与 `disable-model-invocation` 照上游解析，但本地暂无用户入口**：后者会让技能在本地**完全没有入口**
   （目录与工具都不认它）；发现时记一条 warning 如实说明，等 `commands` 落地即生效。~~
   **2026-09-22 订正**：该前置（命令注册表）已落地（§6.23）⇒ `/name` 手势补齐（§6.24）：两条字段都已有出口，
   当时那条"本地暂无用户调用面"的 warning 已删（`user-invocable: false` 现在是**真口径**，不再需要提示）。
4. **本地新增两条硬边界**：单文件 > `MAX_SKILL_BYTES`（64 KiB）跳过；技能文件必须 UTF-8。**未移植** `metadata` 字段（本地无消费方）。
5. **信任口径**：正文按上游当**可信本地内容**（逐字进 `<skill_instructions>`）。它的能力边界是"给模型的指令"——
   **绕不过写路径**（仍要过 `propose_write` → 计划校验 → 审批档 → 写前备份 → 可整批撤销）⇒ 最坏是"模型做了它本来不会做的**库内**改动"，不是任意执行。

**验收**：新增 `tests/test_agent_skills.py` **50 例**（名字语法 / 两种形态与嵌套不发现 / frontmatter 四类非法 / 宽松布尔真值与非法值 / 旧键拒绝 /
`disable-model-invocation` 两面 / 同名遮蔽 / 两段式（只改正文时目录摘要不变而 load 拿到新正文）/ 目录渲染与 500 截断与转义 /
`<skill_content>` 正文逐字 / 工具三类错误 / 提示词门控（工具不在场或目录为空都不出段）/ **只读纪律**（发现+加载+调工具+建 prompt 后整库逐字节不变））；
`pytest -q` **953 passed**；`tests/test_doc_anchors.py` 通过（本轮的 `kb.py` / `prompt.py` 改动**全部为行内 1:1 替换或文件末追加** ⇒
既有 `<文件>:<行号>` 锚点**零漂移**，含 `KB_TOOL_NAMES`（`kb.py:73-80` 仍 8 行）与 `prompt.py:263` 那条）。

**如实交代**：① 没有 L4 实回合（未验"真模型看到目录段后会不会去调 `skill`"）；② 目录段进 **system 提示**（上游是追加在请求末尾的 user 消息）
⇒ 技能变动会让 KV 前缀失效，且**不进会话日志**（回放看不到当时的目录）；③ ~~未做用户手势 ⇒ `user-invocable` 目前是"解析了但没出口"~~ **2026-09-22 已补**（§6.24）。

---

### 6.23 斜杠命令（2026-09-22：吃 `interaction/commands` 的**注册表与生命周期**，两条内建命令按本地需求落地）

**来源**：人「继续移植上游」；本轮拣选依据是**消费方已经出现** —— 自动压缩（§6.16）已落地 ⇒ `/compact` 有了真实需求。

**上游形状**（`packages/interaction/commands/src/index.ts`）：一个插件可注册的**命令注册表** + 一条 `execute()`：
整行以 `/name` 开头且**名字已注册** ⇒ 交出 handler **在宿主侧执行**（**不产生模型消息**）；名字**没注册 ⇒ 回 `undefined`**
（注释原话：*Admission misses … log nothing*）⇒ 调用方把那行当**普通文本**发出去（`/usr/bin`、`5/8` 不会被误吃）。
执行全程有成对 **log-only** 生命周期 `command/run` → `command/done`（按 `commandId` 配对，与 `tool/call`↔`tool/result` 同构）。

**照搬的规则**（逐条注了上游出处，见 `services/agent/commands.py` 模块头表格）：命令名语法、行解析正则与 `rawInput`
口径（**含**分隔空白）、未知名静默放行、成对生命周期与信封字段名、`recordInput:false` 省略 `args`、结果两态
（`success{text?}` / `error{text}`，error 文本必须非空）、handler 抛异常**先**落 `kind:"error"` 的 done **再**抛、
`commandId = cmd-<实例令牌>-<自增序号>`、描述符按名排序。

**本地偏差**（逐条登记）：

| 偏差 | 理由 |
|---|---|
| **不做注册表的"层"**（上游 `ScopedLayers` + 每 agent scope 链可遮蔽同名） | 本地只有一个 agent（`main`）⇒ 塌成**单层扁平注册表**（同 §6.22 的 skill 口径） |
| **不做附件**（`input.attachments` / 图片与文件上传回执） | 本地 composer 没有附件通道 ⇒ 字段与 `admitCommandAttachments()` 整块不移植 |
| **不做 `/` 自动补全弹层与键盘选择** | 上游留给"capable clients"；本地只给 `descriptors()` + `agent_command_list` RPC，前端做的是**一行纯文本提示**（不可点、无键盘选择） |
| **挂点在 `ask()`**（上游 `execute()` 是宿主 Remote 方法、由客户端调） | 本地没有独立的 agent 运行时对象，而 `ask()` 恰好**已经**把上下文（会话 / provider / system / 工具集 / 历史）组装好了 ⇒ 在那里分流最省、也**不会与主回合的组装漂移**；返回仍走 `AskResult`（`stop_reason="command"`、`iterations=0`、`usage={}`） |
| `sourceEventSeq` 字段**保留但无生产者** | 上游用于让客户端定位更丰富的领域事件，本地暂无消费方 |
| 命令提示的**名字/描述暂为后端语言** | 事实源在后端（`agent_command_list`）；i18n 只加"没有匹配"一句（登记待办） |
| **命令轮仍要过提交侧的「出网 / 端点」两道闸** | **真机 RPC 路径实测暴露**：`agent_ask_start('/permission all-access')` 在**没配 base_url** 时回 `{"status":"error","code":"no_base_url"}` —— 闸在 `ask_stream.submit`（`ask_stream.py:308-318`），**早于** `ask()` 里的命令分发。上游语义是"命令**宿主侧**执行"（连模型都不需要），故 `/permission` 这种纯本地命令**本不该**被端点和"关网络"挡住。**未改的理由**：把闸放行给命令行会连带让 `/compact` 也在缺端点时进入 handler，而它必然失败在 `_compact_if_needed` 的 fail-open 分支 ⇒ 用户会看到**误导性**的「没有可压的区间」（真因是"没配端点"）⇒ 简单放行会制造一个更隐蔽的坑；同时改两处（放行 + `/compact` 的端点前置检查）才能自洽。**留待拍板**，改动面估计 ~15 行 + 3 条用例 |

**内建两条**（上游把命令留给各插件注册，本地先给"前置已就位"的两个）：

- **`/compact`** —— 手动压缩：复用**同一个** `ask._compact_if_needed(force=True)`（`force` 只跳过阈值判断，
  先裁后压 / `select_span()` 选区间 / fail-open 全线**逐字不变**）；选不出区间时如实回「没有可压的区间」。
- **`/permission <档位>`** —— 切**本次会话**的审批档：复用 `permission_presets.set_preset()`（落 `permission/preset`
  + `approval/policy`）；错填时报错**必须可行动**（列出可选档位）。

**落点与零漂移**：`ask.py` 的挂点是**中段插入**（上下文齐了才分流）⇒ 该文件其下锚点整体 +15 行，
已把文档里引用的 `ask.py:421` **重取为 `ask.py:445`**（4 份文档 7 处）；`_compact_if_needed` 的 `force` 形参
与阈值判断都是**行内 1:1 替换**（`cancel: … force: bool = False,` 收在同一行，不动行数）；
`ui.py` 的 `agent_command_list`、`agent-panel.js` 的命令块、`app.css`、两份 i18n **全部为文件末追加**。
> **同轮发现（登记）**：`agent-guide/10` 里其余 `ask.py:<行号>` 锚点（`:202`/`:203`/`:204`/`:210`/`:212`/`:216`/`:224`/`:226`/`:237`/`:429-433`/`:494`）
> **早在本轮之前就已陈旧**（例如写着 `ask.py:311-335` 的区间实际是 `411-425`）⇒ 需**专项重取**，本轮只更新了被自己移动的那些。

**验收**：新增 `tests/test_agent_commands.py` **33 例** —— 行解析（含 `/usr/bin`、`5/8`、大写、全角空格、前导空白一律**不是**命令）、
注册期校验与描述符（**不含 handler**）、未知名**零事件**、成对生命周期（含**领域事件落在 run/done 之间**这一形态、
`record_input=False` 省 `args`、handler 抛异常先落 error-done 再抛、非 `CommandResult` 转错误结果、`err("")` 拒绝）、
`/permission` 真切换（落好 `permission/preset`）与错填报可行动错、`/compact` 三条路径（无历史 / **无可压区间 ⇒ 零模型调用** /
**真压下去**：7 轮 ×4k 字符 ⇒ 恰一次摘要调用 + 一条 `compaction{shadowed,model,shadowed_chars}`）、
`ask()` 分流（命令轮 `stop_reason="command"`、**`user/message` 不增**、**`provider.requests` 零增量**；未注册斜杠行**照旧进模型**）、
`agent_command_list` 纯只读（整库文件集不变）。
`pytest -q` **995 passed**；`node --check`（`agent-panel.js` + 两份 i18n）、`scripts/i18n_selftest.js`、`tests/test_doc_anchors.py` 全 PASS。

**真机 RPC 路径实测（L4-lite，不联网）**：`UIAPI.agent_command_list()` 正常返回两条描述符；
`agent_ask_start('/permission all-access')` 在**没配 base_url** 时回 `no_base_url` —— 由此查出上面偏差表最后一行那个**真问题**
（提交侧闸早于命令分发）。**注意**：本轮所有其它断言都走 `ask()` 直调（那里没有那两道闸）⇒ **只测到了引擎、没测到提交路径**。

**如实交代**：① **无 L4 实渲染/实回合**（未验真机面板里 `/` 提示的观感、也未验真用户点一次）；
② **命令轮要过提交侧的"出网 / 端点"闸**（见上表最后一行，留待拍板）；③ 未做 `/clear`（属产品决定）；④ 未做命令名 i18n 与补全弹层。

---

### 6.24 `skill` 的 `/name` 用户手势（2026-09-22：吃 `tool-skill` 的 pre-step 注入）

**来源**：人「继续对齐」；拣选依据 = **前置已就位**（命令注册表 §6.23 刚落地，而 §6.22 曾登记"`user-invocable` 与
`disable-model-invocation` 已按上游解析但**暂无用户入口**"）。

**上游口径**（`packages/skill/tool-skill/src/index.ts:163-204`、`:409`、`:418-430`，逐条对照）：

| 上游行为 | 出处 | 本地落法 |
|---|---|---|
| 手势 = **空白包围**的 `/name` 记号，可出现在文本**任意位置**；第二个 `/` 或非边界字符打断匹配（`/usr/bin`、`5/8` 不误判） | `:409` | 正则**逐字照搬**（`skills.SKILL_GESTURE`，`re` 无 `g` 旗标 ⇒ `finditer`） |
| **只扫 `source.kind === 'user'` 的文本块** —— 外部文本伪造不了手势 | `:171-174`、`:418-430` | 实现上更严：只扫 **`ask()` 收到的用户原文**（`@提及` 改写**之前**）⇒ 会话标题等宿主/模型产出文本也伪造不了 |
| 候选名按 **first-seen 序**去重 | `:426` | `invoked_names()` 同序去重 |
| 逐个查注册表；**未知名 / 用户禁用的技能一律保持普通散文** | `:191-195` | `render_invocations()` 命中不到（`load_skill()` 回 `None`）或 `user_invocable is False` ⇒ 跳过，**不报错** |
| 命中者把 `renderSkillContent()` 作为**注入指令上下文**，**追加在所有其它注入之后**（背景在前、要照做的材料在末） | `:165-170` | `prompt.render_skill_invocation()` → `ask.py:445` 拼在本轮请求**最末**（时间读数之后） |
| 是 `disable-model-invocation` 技能的**唯一入口**（目录与 `skill` 工具都看不见它们） | `:175-176` | 同（`render_invocations()` 不看 `model_invocable`） |
| 与**命令注册表互不相干的闭命名空间**：命令行在宿主侧先解析，命中不了技能就仍是普通散文 | `:172-174` | 顺序天然成立：`ask()` 先走 `commands.handle_command_line()` 分流，未命中才轮到本文 |

**落点与零漂移**：`skills.py` 文件末追加 `SKILL_GESTURE` / `invoked_names()` / `render_invocations()`；
`prompt.py` 文件末追加 `render_skill_invocation()`（`__all__` 与末两段 docstring 为**行内等量扩展**）；
`ask.py` 两处**行内 1:1 替换**（`:79` 导入名扩为四个、`:445` 末项追加调用）⇒ **总行数不变**，
所有 `ask.py:445` / `prompt.py:263` / `skills.py` 既有锚点**零漂移**。

**本地偏差（有意）**：注入**只进本轮请求、不落盘**（同跨会话快照 §6.12 与时间读数 §6.14 口径）——
上游把它持久化成 `source.kind='skill-invocation'` 的 user 消息，故**跨轮仍在**；本地要跨轮须先有"消息 `source`"概念（§6.22 偏差 4）。
另：多块注入以空行相接进**同一条** user 文本（上游是**多条** user 消息）—— 对单条注入逐字等价。

**验收**：`tests/test_agent_skills.py` **50 → 56 例**（正则边界与去重 / 未知名与 `user-invocable: false` 保持散文 /
`disable-model-invocation` 技能**只能被手势带进来** / 注入块形状与位次 / `ask()` 端到端：请求末尾有 `<skill_content>` 且
**会话 JSONL 里零命中** / `/usr/bin` 不触发）；`pytest -q` **1048 passed**；`test_doc_anchors.py` 通过。

**如实交代**：① **无 L4 实回合**（未验真模型收到注入后是否真按技能行事）；② **前端没有技能名的 `/` 提示**
（命令提示只列 `agent_command_list` 的注册命令；上游的 transcript chip 属客户端装饰，本地未做）——
`/name` 目前要求用户**记得技能名**；③ 手势只在本轮生效，续聊同一话题需重新点一次名。

---

## 7. 四条红线怎么落（逐条）

| 红线（出处） | 本方案的落法 |
|---|---|
| **离线优先**（designV0） | 应用**默认可用但可一键关**出网；模型仅走用户自配端点；不内嵌权重、不后台拉取任何东西；`.memoria/cache/**` 之外不新增缓存 |
| **禁止 silent 写入**（designV0:254,911） | M1 工具面**只读**；写能力（M3）一律"提议 → 用户确认 → 应用"，且应用必须走既有服务层（原子写 A7 → 索引失效 G5.4 → manifest/sidecar 同步 A1/A2 → pending 同步 A3），**禁止旁路写文件**。**M3 设计已完善**（[agent-capabilities.md §2.3.1](agent-capabilities.md)）：该红线在**插件边界物理可证** —— 插件不含可执行体（无 `open(...,"w")` 的机会）、核心写原语是唯一写者、落盘前做 realpath 前缀校验；**且 apply 前必留写前 pre-image、备份失败即不写**（[§2.3.2](agent-capabilities.md)） |
| **单一事实源**（AGENTS.md §1） | 会话数据落在新事实源（须先登记，见 P3）；提示词/规范仍只有 `.memoria/agent/**` 与 `resources/agent-prompts/**` 两处（后者是程序读取源） |
| **免安装、可离线分发**（`build.py` 硬门禁） | 纯 Python 实现 ⇒ **不引 Node、不引新运行时**；新增依赖须过 `packaging/build.py` 的 `_REQUIRED_RELEASE_RESOURCES` 与体积预算（M1 目标：轻量包增量 < 2 MB） |

---

## 8. 分阶段

| 阶段 | 范围 | 出口（门禁） |
|---|---|---|
| **M1** | 应用内对话 + 读库问答（只读工具、单一会话、jsonl 持久化、密钥本地引用、出网开关） | §6.4 全绿 + 用户真机走查 |
| **M2** | 长会话（compaction）+ 会话检索（session-query）+ 上下文引用（file/session reference/time）+ 标题 | M1 门禁 + 压缩前后 A/B（上下文长度、回答可回溯性） |
| **M3** | 写能力：提议（**agent 只产声明式 plan**）→ 确认 → 应用（逐条确认 + **写前备份** + 可撤销）；落盘由**编译器**在 apply 入口完成。**主体已落地（2026-09-21/22）**：`propose_write`（工具内直接落盘；命中风险条件的 op 走逐条确认）、`plan.py`/`apply.py`/`backup.py`/`audit.py`/`observation.py`、`permission_presets.py`（三档）。**未落地**：能力插件**契约本体**（`capabilities.json` 零命中）与 per-KB 开关；**仍待**：M3b 的 `set_kp_range` / `rename_kp`（只登记不编译） | "无 silent 写入"专项验证：任一次拒绝都不改盘；`validate_kb` errors=0 |
| **M4** | 对外契约（若届时 D2 仍在推进）：复用旧稿 §7 的 T1 CLI 面，把 M1–M3 的能力暴露给外部 agent | 契约文档 + 版本协商 + 只读默认 |

> **M2 落盘口径（2026-09-18 拍板）**：compaction 的结果**持久化进会话 JSONL**（新增一种记录类型，由 `session/history.py::build_history()` 回放时把被覆盖区间替换为摘要），对齐上游「把摘要写进会话事件面」的做法；**不**采用「请求期变换 + `.memoria/cache/` 缓存摘要」那条路。
>
> **更正（读码后）**：该新增类型是**纯追加**且旧读者对未知 type 一律跳过 ⇒ 旧版本读新文件只是
> **降级为「没有压缩」**，不误读不崩（等价上游 `ignorable: true`）⇒ **不需要** bump
> `SESSION_FORMAT_VERSION`、也无老会话迁移问题。详见 §6.8。
>
> **M2 已落地部分**：§6.7（上下文引用 `context/file-reference`）、§6.8（compaction）、
> §6.9（session-query）、§6.10（`compaction-tool-result-pruner`）、§6.11（会话标题）、
> §6.12（跨会话引用 `context/session-reference`）、§6.14（时间上下文 `context/time-context`）、
> **§6.15（模型切换告知 `core/agent` 的 `model-selection`）**、**§6.16（上游读面：`read` 分页 / `glob` / `grep` / `read_image`，2026-09-20）**、**§6.17（会话查询五工具补全：`session_event_search` / `session_trace` / `session_event_trace` / `session_event_read`，2026-09-20）**。
> **§5 映射表里 `context/*` 三行的引用族（tmux 除外）与 `core/agent` 家族至此全部处置完毕**（吃 / 已覆盖 / 不适用 逐条有证据）；**§5.1 读工具组的四项已从 ❌/⏸ 收敛为 ✅（读图能力归未来多媒体「眼睛」插件，不计入读面缺口；工具面 = 工作区根，见 §6.16 偏差 1）；会话检索家族的第五项（`session-query` 五工具）也已 5/5（`search_sessions` 保留原名，见 §6.17）**；下一阶段为 M3 写能力。
>
> **M2 之后仍未做（按阶段）**：**M3** = 写能力（提议 → 确认 → 应用）+ 由它解锁的
> `interaction/permission-presets`（要有第 2 个旋钮才有"档"可切）与 `interaction/commands`
> （要有真实命令需求才有得注册）；**M4** = 对外契约（旧稿 §7 的 T1 CLI 面）。
> **M3 设计已完善（见 [agent-capabilities.md §2](agent-capabilities.md)），待拍板（P7–P12）/ 待实施**：
> 写能力改为「可插拔能力插件 + **计划 API + 编译器**」形态（契约 + 装载器 + 写管线 + 权限矩阵；agent 只产 plan、落盘由编译器），并给出 **M3a/M3b** 两个
> 切片与安全门四条（含**写前备份可用可清**，§2.3.2）；`permission-presets` 所需的"第 2 个旋钮"由该契约的 `approval` 档提供（§2.1/P11）。
> 另有两条**本模块级**待办（见 §6.15 末段）：~~`tool/call` 落盘位次对齐（`toolMs` 可测的前提）~~ **2026-09-22 已做**（见 §11 本轮行：`tool/call` 改为**先于分发**落盘，等量换位、总行数不变）与逐轮成本按轮模型归属（仍未做）。
>
> **仍标 ⏳ 的行（2026-09-22 重刷；上一版是 2026-09-20）**：
> `credentials/authorization`（**条件性 ⏳**：本地无 OAuth 端点、单密钥已由 `llm/config.py` 覆盖 ⇒ 现在不适用，
> 只有将来接授权类端点时才回来吃）；`storage/*` · `skill/*` · `hooks/*` · `guard/*` · `plan/*` · `goal/*` · `todo/*`（⏸ 按需；其中 `todo_write` 是唯一小件）。
> **已由 M3 落地、从 ⏳ 转 ✅（截至 2026-09-22）**：`permission-presets`（`services/agent/permission_presets.py` 三档 + 逐条确认卡）、
> 写能力本体（`propose_write` → plan → 编译器 → apply；`KNOWN_OPS` **14** / `COMPILED_OPS` **12**）、写前备份与撤销（`services/agent/backup.py`）、
> 写路径审计（`services/agent/audit.py` 的 `capability/apply`·`undo`·`redo`·`force_save`）、读后写守卫（`services/agent/observation.py`）、**技能规则面**（`services/agent/skills.py` + 只读工具 `skill` + 提示词目录段，§6.22）、**斜杠命令**（`services/agent/commands.py` + `/compact`·`/permission`，§6.23）、**`/name` 技能手势**（§6.24）。
> **仍未落地（可做，按建议顺序）**：① 能力插件**契约本体**（`capabilities.json` 零命中 ⇒ 今天是"直接工具"而非声明式插件，见 §5 第 117 行）；
> ② `interaction/tool-ask-user`（模型中途向用户提问）；③ `read_image` 的**真读图能力**（缺"多媒体眼睛"插件，参数/校验已齐）；
> ④ `skill` 的**剩余三块**（watcher / 注册表层 / 持久目录消息 —— ~~`/name` 用户手势~~ **2026-09-22 已补，§6.24**：`user-invocable` 与 `disable-model-invocation` 两条字段现已都有出口）；
> ⑤ M4 对外契约；~~另两条本模块级待办见上（`tool/call` 落盘位次、逐轮成本归属）~~ ⇒ **`tool/call` 位次 2026-09-22 已对齐上游**；逐轮成本归属仍未做。
> 已转为**已覆盖 / 不适用 / 不吃**（见 §6.15 表）：`core/agent-default-model`（已覆盖）、
> `core/agent-tool-presentation`（本地恒 `native`）、`core/agent` 的 registry/initiator（Cordis 专有）、
> `session-projection*` 框架（Cordis 专有）与 `session-stats`（无对应事件面，`turns/steps` 已覆盖）。
> ❌ 不吃者（tmux / telemetry / `api/*`·`sdk/*`·`bundle/*` / 沙箱与执行编排族 / `compaction` 的两个子包 / `file-reference-local`）不在计划内。
>
> **⏳ 用户登记（2026-09-20，工具面优化项；本轮只登记、不实现）**：*「agent 常常调用 powershell 进行脚本化读写等（但是常常因为语法错浪费 token，这个以后是一个优化项目）」* ⇒ 后续优化方向（三选一或组合）：① **优先用原生工具** —— 本轮已补 `read_document` 分页 / `glob` / `grep`（§6.16），可直接替代 `Get-Content` / `Get-ChildItem` / `Select-String` 这三类最常见的脚本化读；② **预置脚本模板**（常用 PowerShell 片段做成受控模板/别名，模型填参而不写语法）；③ **错误前置校验**（在调用前挡掉语法错，而不是让 shell 的报错文本回灌上下文烧 token）。**澄清**：产品内 agent 目前**没有**命令执行面（§5 第 118 行 ❌ 不吃 `shell/*`·`subprocess/*`），故这条现状更可能指**宿主/IDE 侧的 agent**；若将来给产品内 agent 开口执行面，②③ 才落在本仓库（本项无需现在拍板）。

---

## 9. 风险

| # | 风险 | 等级 | 处置 |
|---|---|---|---|
| P1 | 上游为 developer preview，破坏性变更频繁 | 中 | pin `0d1f5000`；**只在需要时** diff 对应包；不做全量同步 |
| P2 | **语义漂移**（重写后行为与原实现不一致） | 中高 | 每块留下"上游文件 → 本地文件 → 行为差异"记录；关键行为（审批/终止条件/错误重试）写单测 |
| P3 | 上下文与工程成本（上游 12k 文件） | 中 | 按包读双语 README 先行；**每次只吃一块**，禁止批量搬运 |
| P4 | 许可与归属疏漏 | 中 | §4 的清单进 M1 验收项；补齐 Memoria 自身 `LICENSE` 与 `THIRD_PARTY_NOTICES` |
| P5 | 出网与密钥带来的隐私面 | 中 | 默认关闭入口需显式开启；密钥走引用不落明文；日志脱敏 |
| P6 | CVE 面（旧稿 X6：沙箱逃逸 CVE-2026-82533，0.1.1-rc.2 及以下） | **低** | 本方案**不吃**沙箱/执行/编排包，暴露面仅模型调用与本地文件读 |

---

## 10. 待拍板问题（答复后开工）

| ID | 问题 | 选项 | 影响 |
|---|---|---|---|
| **P1** | Python 落点目录名 | ✅ **已定（2026-09-17）：`src/memoria/services/agent/**`** | 与既有服务层/CLI 并列，复用检索与校验 |
| **P2** | 模型调用实现 | ✅ **已定（2026-09-17）：标准库 `urllib` + 手写 SSE**（零新依赖，打包体积不变；重试/退避参照上游 `llm-retry`） | 决定依赖与打包体积 |
| **P3** | 会话数据的事实源位置 | ✅ **已定（2026-09-17）：`<kb>/.memoria/agent/sessions/*.jsonl`**（随库走）——**须登记进 `AGENTS.md` §1 单一事实源表**（该文件人维护、Agent 只读，见下） | 需人工登记 |
| **P4** | 出网开关粒度 | ① 全局开关 + 端点配置（推荐，M1 够用）② per-KB 开关 ③ 全局 + per-KB | 决定设置面板与隐私边界 |
| **P5** | 是否复刻 `interaction/commands`（slash 命令） | ① M1 不做（推荐）② 做最小 `/clear` `/compact` | 决定前端工作量 |
| **P6** | 是否同步修订 `AGENTS.md` / `kb-agent.md` 的边界措辞（产品内 Agent ≠ 仓库协作 Agent） | ① 修订（推荐，避免后续误读 RISC 条款）② 只在本文说明 | 决定契约文件改动 |
| **P7** | 自身 `LICENSE` 选哪个 | ✅ **已作废（2026-09-17）**：`LICENSE` 本就是 MIT（署名 `FreshTim`）⇒ 无需选择/新建；本条实际只剩**新增 `THIRD_PARTY_NOTICES.md`**（登记 dsh 的 MIT 原文 + pin `0d1f5000` + npm 字段 `BSD-3-Clause` 差异）—— **✅ 已于 2026-09-19 完成**（根目录，另含逐块移植落点表） | §4.3 剩余缺口**已关闭** |

> **P4–P6 默认执行口径（2026-09-17，未另问）**：**P4** = 全局出网开关 + 端点配置（M1 够用，per-KB 留到 M3）；**P5** = M1 不做 slash 命令；**P6** = 建议修订措辞（见下方待人工改动）。
>
> **需人工改动的两处（仓库契约文件，Agent 只读）**：
> 1. `AGENTS.md` §1 单一事实源表新增一行：`| 会话历史（产品内对话 Agent） | <kb>/.memoria/agent/sessions/*.jsonl | 应用代码 |`；
> 2. `AGENTS.md`／`kb-agent.md` 补一句边界说明：RISC 的「永不新增独立 Agent」约束的是**仓库协作 Agent**，不约束**产品内面向用户的对话 Agent**。

---

## 11. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-17 | 初版：主线定为 D1′ 代码级移植（旧稿 D1/D2 降级为旁支）；上游事实基线实测（含 pin `0d1f5000`）；包级映射表（吃/不吃 + 阶段）；M1 竖切与文件级清单；四条红线落法；M1–M4 分阶段；6 条风险；P1–P7 待拍板；登记 `docs-management.md §4.2` |
| 2026-09-17 | 拍板回填：**P1** = `src/memoria/services/agent/**`；**P2** = 标准库 `urllib` + 手写 SSE（零新依赖）；**P3** = `<kb>/.memoria/agent/sessions/*.jsonl`（待人工登记 AGENTS.md §1）；**P7** = MIT + `THIRD_PARTY_NOTICES.md`。P4–P6 按推荐默认（全局开关+端点配置 / M1 不做 slash / 建议修订边界措辞，两项契约改动需人工落地） |
| 2026-09-17 | **更正**：§0/§4.3/P7 曾记"仓库无 `LICENSE`"——错（源于一次失败的目录检查）。核实：`LICENSE` 早已存在（MIT，`Copyright (c) 2026 FreshTim`，`730f9a8a`），故 P7 作废；实际缺口只有缺 `THIRD_PARTY_NOTICES.md`。同步更正 `docs-management.md` §4.2 同条登记 |
| 2026-09-17 | **M1a 落地**（只吃 `llm` 包）：新增 `src/memoria/services/agent/llm/**`（10 文件）+ `scripts/agent_llm_smoke.py` + `tests/test_agent_llm.py`（21 例）+ 仓库根 `THIRD_PARTY_NOTICES.md`。验收：`py_compile` 12/12、`pytest 21 passed`、`--mock` 冒烟通过、零第三方依赖、12/12 带来源注释、无既有文件被改；偏差与未实测项见 §6.5 |
| 2026-09-17 | **M1b 落地**（吃 `core`/`session`/`context`/`interaction`）：新增 11 文件 / 2,236 行（loop、system-prompt 组装、11 个只读工具与注册表、jsonl 会话存储、fail-closed 审批、`ask()` 入口、`scripts/agent_ask.py`、12 例单测）。验收：`py_compile` 全过、`pytest 33 passed`、`--mock` 离线竖切跑通（先 `search_kb` 再作答、输出 `文件:行号` 锚点）、**零写入**（逐文件对比仅新增会话 jsonl）。偏差见 §6.6 |
| 2026-09-18 | **M2 上半落地**（吃 `context/file-reference`）：`services/agent/prompt.py` 新增常量 `FILE_REFERENCE_SECTION`（上游 `FILE_REFERENCE_PROMPT` 的中文落法）并按上游门控注入（**仅当 `read_document` 在场**），段落顺序变为「基础身份 → 运行环境 → 库内指令 → 可用工具 → 用户引用（`@路径`） → 回答要求」；删掉同日早些时候临时塞进「基础身份」的那一行。顺带修掉前端 `@` 语法两处**真缺陷**（邮箱 `a@b.com` 被误渲染成 chip / 含空格路径完全无法表示）—— `MENTION_RE` 换成上游 `activeAtToken` 语义的四分组式 + 新增 `formatMention()`（上游 `formatFileMention` 语义）。验收：`pytest 81 passed`（+1 门控单测）、harness 浏览器实测 4 chip + `a@b.com` 不被识别 + 插入侧 `@"含空格"` 形式。偏差与证据见 §6.7 |
| 2026-09-18 | **拍板 M2 落盘口径**：compaction 的结果**持久化进会话 JSONL**（新增记录类型，`build_history()` 回放时替换被覆盖区间），对齐上游「把摘要写进会话事件面」；**不**走「请求期变换 + cache 缓存摘要」。故 compaction 落地时会改会话格式 ⇒ 需同步 `SESSION_FORMAT_VERSION` 与老会话兼容策略（见 §8 表下注）。同轮还确立：**先补 M2 的最小一块（上下文引用）**，compaction / session-query / 标题留后 |
| 2026-09-18 | **M2 compaction 落地**（吃 `compaction/compaction` + `compaction-basic`）：新增 `services/agent/compaction.py`（阈值/保留比例同上游 0.8/0.16、`MAX_TOKENS=8192`、8 段骨架的中文落法 + `frameSummary` + 工具配对切割点 + KV 前缀对齐的摘要调用 + fail-closed）；`session/history.py` 新增 `COMPACTION` 事件与压缩回放（原位出摘要、链式只出最新、无效记录不吞事件）；`ask.py` 加自动触发（超预算才压、**失败不打断提问**）；`loop.py` 的 `_usage_payload` 提为公开 `usage_payload`。验收：`pytest 104 passed`（+23 例 `tests/test_agent_compaction.py`）。偏差、缺口与未实测见 §6.8 |
| 2026-09-18 | **更正**：上一条拍板笔记里「需同步 `SESSION_FORMAT_VERSION`」**不成立** —— `compaction` 是纯追加类型且三个既有读者对未知 type 一律跳过 ⇒ 旧版本读新文件只降级为「没有压缩」，不误读不崩（等价上游 `ignorable: true`）。按上游「只有结构变更才 bump」的规则，**不 bump**。已同步修 §8 表下注与 §6.8 |
| 2026-09-19 | **M2 session-query 落地**（吃 `session-query/session-query` 的 `extraction.ts`+`filters.ts` + `session-query/tool-session-query`；**不吃** `session-query-sqlite`（不引索引）/ `session-log-export`（导出 UI））：新增 `services/agent/session/query.py`（语义文本抽取含**本地扩展**的 `compaction`→`summary`、字面量匹配的逐词转义防注入 + 空白弹性、摘要窗、`_Filters` 的「子句间 AND / 子句内 OR」、四重有界化、字节级预筛）；`tools/kb.py` 增 `search_sessions` 工具（只读，命中写成「会话 `<id>` 第 N 条」**且刻意不产生 `文件:行号` 锚点**）；新增 `tests/test_agent_session_query.py` 28 例。验收：`pytest -q` **132 passed**（原 104 + 28）；修掉一个真 bug（`limit=0` 仍返回 1 条）；零新依赖。偏差（语料无 live/SQLite 索引、排序由相关性改为 `modified_at` 倒序、`snippet` 窗口未逐字对齐、不移植游标/谱系/可观测性）、缺口与未实测见 §6.9 |
| 2026-09-19 | **M2 工具结果裁剪落地**（吃 `compaction/compaction-tool-result-pruner` —— §6.8 曾登记为「留后」，本轮补上）：新增 `services/agent/pruner.py`（`PRUNE_MARKER` 逐字照抄、阈值/头/尾 = 8192/4096/1024 同上游、`PruneBudgets` 构造期校验保证**永不增长**、`prune_text`/`apply_budget`/`applied_chars`/`prune_plan`/`prune_records`/`prune_applied`）；`session/history.py` 新增事件表行 + 「工具结果裁剪回放」小节（`_tool_message`/`_replay`/`replay_events` 接裁剪表、`build_history` 自动应用、新增 `compaction_shadowed()`）；`compaction.py` 的 `event_chars`/`select_span` 新增 `effective_chars`（按**有效视图**计账，避免高估尾部）；`ask._compact_if_needed()` 改为**先裁、再压**（裁完够用即**免掉**一次摘要调用，仍是超则摘要器读裁剪视图），返回值语义放宽为「是否落了事件」。**落盘**：一条 `compaction/prune`（`{pruned:[{seq,id,chars_before,chars_after,head,tail}], chars_removed}`），回放期**就地**重建 —— 不像上游那样追加替换 `tool/result`（同一 `tool_call_id` 两条工具消息会被端点 400）。验收：`pytest -q` **153 passed**（原 132 + 21 例 `tests/test_agent_pruner.py`）；零新依赖。偏差（纯字符串内容模型、不移植影子定价/`surfaceOp`、检索仍走原文、字符非 token 预算）、缺口与未实测见 §6.10；§8「M2 剩余」同步更新 |
| 2026-09-19 | **M2 会话标题落地**（吃 `session-title` + `session-title-llm` + `session-title-first-prompt-llm`；**不吃** `all-prompts`（每轮一次调用不值）/ 投影框架 / `session/title-llm-request` 预派发记录 / `rename()`）：新增 `services/agent/title.py`（`session/title` **log-only** 事件；来源最新者胜：`fallback` 确定性兜底 = 首条人类消息前 8 词 / 96 字节、`provider` 模型标题、`user` 改名未移植；规范化照搬上游（OSC/CSI/ESC 序列、C0-C1、方向与隐形字符、空白折叠、**按 UTF-8 字节截断不切开码点**）；限额 8/96/120 + 调用策略 `maxInputBytes=32768` / `maxOutputTokens=96` / `timeout=20s`；`generate_title()` **fail-closed**（非 `stop` 的终止原因一律拒）；`auto_title()` = `first-prompt` 节律）；`history.py` 的 `summarize_events`/`summarize_session_file` 都改为**优先取折叠标题**（原始行扫描只对最后一个命中行解码，与折叠同口径）；`ask()` 两步接进（追加提问后落兜底、主回合后跑首轮一次的模型标题、**被取消的轮次跳过**、两步都 fail-open）；**顺带修掉"做完也看不见"**——前端 `#agent-history` 下拉标签由 `preview` 改为 `title || preview`（后端 `title` 字段此前从未被前端使用）。验收：`pytest -q` **184 passed**（原 153 + 31 例 `tests/test_agent_title.py`；`test_agent_history.py` 一处断言随之更新）；**浏览器实测**（harness 端口 8645、临时库 + 手写 `session/title`、不需要模型）：`agent_sessions_list.title = "多层感知机的要点"`、下拉选项文本 `多层感知机的要点（1 轮）`。偏差（**本地无异步服务 ⇒ 标题调用排在主回合之后**、仅首轮一次；被取消轮次不生成；用量记进事件但不进 benchmark）、缺口与未实测见 §6.11；§5 映射表与 §8「M2 剩余」同步更新 |
| 2026-09-20 | **M2 时间上下文落地**（吃 `context/time-context` 的 `timestamp.ts` 字段口径 + `request-zone.ts` 三态策略 + `index.ts` 的 `renderText()` 文本；**不吃** pre-step 监听器 / `refreshIntervalMs` 到期调度 / `sessionProjections` 投影 / `invariant.ts`）：`services/agent/prompt.py` 文件尾追加 `TIME_CONTEXT_SECTION`（中文落法，上游英文原文写在常量注释上方；**不按工具门控** —— 对齐上游「插件被挂载」）+ `_local_now()` / `format_time_context()` / `render_time_context()`，`build_system_prompt()` 在「用户引用」之后无条件追加该段（`prompt.py:263`）；`ask.py:445` 把读数追加在**本轮请求末尾**（不进 system 段、不落盘）。验收：`py_compile` 全过；`pytest -q` **258 passed**（原 254 + 本轮 4 例，另 3 处既有断言随读数更新）；Python 级真实渲染 `当前本地时间：2026-09-20T09:51:44+08:00`（本机 `Asia/Shanghai`）+ `tools=()` 门控对照（时间上下文段在、文件引用段不在）。有意偏差：读数不落盘（同 §6.12 偏差 1）、静态说明与动态读数两分（KV 前缀）、三态时区收敛为一句、省略 `[IANA]` 括注、无 turn/step 与 elapsed、不新增配置项。偏差、缺口与未实测见 §6.14；§5 映射表 + §8 阶段状态同步 |
| 2026-09-20 | **M2 模型切换落地 + ⏳ 候选全量界定**（吃 `core/agent` 的 `model-selection`；同一轮把 §5 全部 ⏳ 候选读码量过并逐条定性）：`loop.py` 的 `loop/end` 载荷新增 `"model"`（`loop.py:396`，**+1 行**）；`prompt.py` 文件尾追加 `MODEL_CHANGE_NOTICE` + `render_model_change_notice()`（上游 `modelSwitchNotice()` 的中文落法，英文原文写在常量注释上方）；`ask.py:445` 同行内联追加 `_model_notice(...)`（文件尾追加 `_last_recorded_model()` / `_model_notice()`）—— 续聊时「会话最后一条 `loop/end.model` ≠ 本轮模型」就在本轮请求里加一条告知（**不落盘**，同 §6.12/§6.14 口径）。验收：`py_compile` 全过；`pytest -q` **265 passed**（原 258 + 7 例，**无既有断言需要改**）；Python 级实请求逐字取证（`第二问\n\n[模型已更换：本轮之前的助手回复由 deepseek-chat 生成；本会话此后由 model-beta 继续]\n\n当前本地时间：…`；同模型续聊无告知；`loop/end.model=['deepseek-chat','model-beta','model-beta']`；JSONL 正文仍是用户原文）。**本轮把 6 个 ⏳ 候选定性为**：`core/agent` 的 registry/initiator 与 `session-projection*` 框架 = 不吃（Cordis 专有）、`agent-default-model` = 已覆盖（`llm/config.py`）、`agent-tool-presentation` = 本地恒 `native`、`session-stats` = 不吃（ttft/decode 无事件面、turns/steps 已覆盖、`toolMs` 因本地 `tool/call` 落盘位次而后测不准）、`commands`/`permission-presets` = 留 M3（无消费方 / 无第二个旋钮）、`credentials/authorization` = 条件性 ⏳。偏差（告知由日志派生而非持久消息、标签无 provider、基准是"最近一轮"、老会话不告知、`replay=False` 不告知、插入位次）与未实测见 §6.15；§5 四行 + §8 阶段状态同步 |
| 2026-09-20 | **M3 设计完善（docs only，未实施）**：写能力改为「可插拔能力插件」形态并把四条线（W/N/S/H）收进**同一份契约**，详见 [agent-capabilities.md §2](agent-capabilities.md)（该文件本轮重写 §2 七小节 + 新增 §10 P7–P11 + §9 R8）。本文件同步：§5 `interaction/commands · permission-presets` 行（`approval` 档 = 第 2 个旋钮，待拍板 P11）、`credentials/authorization` 行、`storage/* · skill/* · hooks/*…` 行（`skill` 归入同一契约）；§7 红线「禁止 silent 写入」行（补"插件边界物理可证"）；§8 的 **M3 行**与 §8 表下注（M3 设计已完善，待拍板/待实施）。**未新增/修改任何源码**；`todo.md §13 AG04` 仍为 K3 待评审 |
| 2026-09-20 | **§5.1 新增：上游读写面 vs 本地现状对照表（docs only，未改任何源码）**：只读上游检出 `dsh-src/`（pin `0d1f5000`，`git -C dsh-src status --porcelain` 空）读齐读面（`fs/tool-fs` 的 `read`/`read_image` + `fs/tool-fs-search` 的 `glob`/`grep` + `session-query/tool-session-query` 五个工具 + `context/*` 四包 + `core/tools` 注册表）、写面（`write`/`edit` 参数形态、`fs-local/fsio.ts` 原子写与版本令牌、`fs-observation-policy` 读后写守卫、`fs-sandbox`/`sandbox` 三档、`user-approval` waterfall、`permission-presets` 组合档）与 `skill` 形态（`skill-filesystem` 的 `SKILL.md`/平铺 `.md` + frontmatter + 目录/正文两段式 + 五根 rank + 两布尔调用策略）；逐条对照本地 `tools/kb.py`/`tools/registry.py`/`approvals.py`/`prompt.py`/`session/reference.py`/`document.py`。**表 30 行**（读工具 6 / 引用与上下文 7 / 写工具 4 / 把关 4 / 备份·审计·撤销 4 / 技能与命令 2 / 其它差距 3）+ 三段结论（已完全移植 / 本地替换 / 完全没设计）。**关键事实**：上游**有审计、无备份、无撤销**（`fs-local/src/win32.ts:20` backup 传 `null`），本地反之**设计了备份+撤销、无版本令牌**；本地写面已改为 plan + 编译器的模型（编译器未实施）。**已完全移植** 6 项、**本地替换** 3 项、**空白 gap** 5 类。**未实施任何代码**；`docs/todo.md` 未改动（另一写者并发重写中，本轮只报告不编辑）。 |
| 2026-09-20 | **历史行右键菜单（重命名 / 删除）+ 行悬浮提示（M2 会话标题的收口：上游 `session-title` 的 `rename()` 此前明确"未移植"，本轮以**追加 `session/title`** 的方式补齐 UI 入口）**：后端新增 RPC `agent_session_rename(session_id, title, kb_path=None)`（`ui.py:1366-1419`，**插在 `agent_session_delete` 之后** ⇒ 其下 `agent_usage_stats` 等 anchor **+54**，`agent_session_delete` 及以上零漂移）；前端实现**全部**落在 `agent-panel.js` 文件末尾追加块（`:4091-4299`：`decorateHistoryRowMenu` / `openHistRowMenu` / `histRename` / `histDeleteWithConfirm` / `promptHistInput` + 视图上的 `contextmenu` 委托），行内 `-hist-del` 按钮退役、删除改走应用内确认弹窗，菜单/弹窗复用 app.js 通用 `showTreeContextMenu` / `confirmTreeAction`。**语义口径**：改名 = **追加**一条 `session/title`（`source.kind="user"`、`message_seqs: []`），依赖 `title.fold_title()` 的"最新者胜"⇒ **回放 / 列表 / 模型输入三侧零改动**（`title.py` 政策一节原话"将来接改名 UI 无需改回放"）；标题 `clean_title_text()` + `TITLE_MAX_BYTES`(120) **拒绝而非截断**；本地新增 `busyLock`：生成中禁改当前会话（在飞作业的 `SessionStore._seq` 是构造时点数得出的，另开 store 去写会撞 seq）。验收：`pytest -q` **356 passed**（+ 后端 2 例 / 前端 2 例）、`node --check` 3/3、真机 E2E（harness 8662）右键菜单/重命名/删除确认/悬浮提示/`[data-hist-del]=0` 全通过（**首次 E2E 的 `未知方法` 是 harness 进程过期，非代码缺陷**；改名后已还原原标题、未实际删除会话）。登记见 `docs-management.md §4.2`；RPC 表与锚点重取见 `reference/agent-guide/10 §2.15`、UI 侧见 `01 §6`。`docs/todo.md` 未编辑（另一写者并发重写中） |
| 2026-09-20 | **上游读面移植落地（§6.16）**：用户口径「上游的读先移植进来」⇒ 吃 `fs/tool-fs` 的 `read` 参数语义（offset 1-based / limit 默认且上限 2000 / 越界 `FS_NOT_FOUND`）/ 三重 cap / 续读 footer 与 `read_image` 的扩展名 + 文件签名校验，吃 `fs/tool-fs-search` 的 `glob`（100）/`grep`（250 处、单行 2000 字节、30s 预算）上限与输出形状。① `services/agent/tools/kb.py`：`read_document` 新增 `offset`/`limit`（默认且最多 **2000 行**、越界 `NOT_FOUND`、截断给「续读请把 offset 设为 N」；**不传参逐字兼容旧输出**）；新增三个只读工具 `glob`（匹配口径照上游「不含 `/` 比文件名/任意深度」）、`grep`（**Python `re` 而非 ripgrep**，零依赖）、`read_image`（**只做参数与校验；端点不支持图像输入 ⇒ 明确 `UNSUPPORTED_IMAGE_INPUT`，不伪造成功**）；路径校验复用 `_safe_rel` 系并扩展为「不限扩展名 + 两侧 realpath」（`.memoria/**` 与 VCS 元数据排除，符号链接越界**不列不读**）。② `services/agent/prompt.py`：`@路径` 段门控由「只认 `read_document`」放宽为**任一读取手段在场**（`FILE_REFERENCE_TOOLS`，零行漂移）。③ 测试：新增 `tests/test_agent_tools_read.py` **19 例**；`tests/test_agent_loop.py` 门控例语义更新 1 处。**验收**：`py_compile` 全过；`pytest -q` **284 passed**（原 265）；Python 级真实取证（续读提示可解析并续读成功、`glob` 列表、`grep` 分组命中、五类越界/库外拒绝逐项输出）；零新依赖、零前端 / 零 i18n 改动；`dsh-src` 检出未改。**偏差 12 条**（工具面=知识库 / Python `re` 方言 / `read_image` 只到校验 / 不逐行加行号 / 未截断无 footer / 字符非字节预算 / 无 spill / 排序取新→旧 / 门控放宽 / 注册条件 / glob 方言子集 / 不新增 `read` 工具）与 **7 条未实测**见 §6.16；**锚点重取** `tools/kb.py:566-592` → `:581-607`、`prompt.py:262-263` → `:261` + `:385-394`。④ 同轮在 §8 登记**用户优化项**（agent 靠 PowerShell 脚本化读写、语法错浪费 token ⇒ 优先原生工具 / 预置脚本模板 / 错误前置校验；**只登记不实现**）。**`docs/todo.md` 未编辑**（另一写者并发重写中；建议台账行见本轮报告） |
| 2026-09-20 | **上游读面设计改正（工具面 = 工作区根 + 允许根列表 + 可见性/权限分离）**：用户口径「工具面应该是整个根目录的工作区，只是用户只能看见程序限制给他看的文件，甚至以后为了让 Windows 拖拽进对话栏，需要越出根目录」＋「无法识别照片是因为没装上多媒体的『眼睛』插件，留给以后」。① `services/agent/tools/kb.py`（**全部等量改写 + 文件尾追加 ⇒ 零锚点漂移**）：新增**允许根列表** `_read_roots()`（今天 = `(库根,)`）/ `_resolve_in_read_roots()`（`:1135-1162`），路径校验（`_safe_rel()` / `_safe_rel_any()`）与遍历（`_walk_kb_files()` 逐根）**都改走它**（行为等价）；`GLOB_EXCLUDED_DIRS` `:692` 收缩为**只跳 VCS 内部目录**（`.git`/`.svn`/`.hg`/`.bzr`/`.jj`/`.sl`，理由=非内容且会污染 glob/grep），**`.memoria/**` 改默认可见**（agent 维护 sidecar/manifest 需要看得见）；越界一律**明确的拒绝错误**（`INVALID_ARGUMENTS`，非「不存在」），将来把根加进列表即放行；`read_document`/`glob`/`grep`/`read_image` 的路径错误文案与工具描述改为「工作区（允许根）内」。② `read_image` **归类改正**：读不到图不是「provider 不支持 content part」，而是**缺一个多媒体的「眼睛」插件** ⇒ 归入**未来多媒体能力**、**从读面缺口移出**；待办措辞由「消息层图片支持」改为**「待『多媒体眼睛』插件」**（工具描述、错误文本、§5.1/§6.16 同步；错误码 `UNSUPPORTED_IMAGE_INPUT` 不变）。③ 测试：`tests/test_agent_tools_read.py` +1 例（允许根列表与越界错误码稳定，含「多根即放行」断言），2 例断言随 `.memoria/**` 可见性改写。**验收**：`py_compile` 全过；`pytest -q` **285 passed**（原 284）；仓库外临时脚本取证（`_read_roots()`/`_resolve_in_read_roots()` 输出、`.memoria` 可列可搜 vs `.git` 不可见、四类越界 `INVALID_ARGUMENTS`、符号链接越界不列不读）；零新依赖、零前端 / 零 i18n 改动；未碰 `agent-plugin-design.md`（人正在逐步对齐）。**`docs/todo.md` 未编辑**（另一写者并发重写中；建议台账行见本轮报告） |
| 2026-09-20 | **会话查询五工具补全（§6.17）**：上游 `session-query/tool-session-query` 明说**五个**只读工具（`README.zh.md:12`、`:47-51`），本地此前只落 `search_sessions` 一个 ⇒ 本轮补上**其余四个**（`session_event_search` / `session_trace` / `session_event_trace` / `session_event_read`），上游**名字、参数与结果形状**照搬，`search_sessions` 保留原名与既有行为（名字偏差见 §6.17 偏差 1）。① `services/agent/session/query.py`（**文件尾追加** + 3 处等量改写，零锚点漂移）：新增 `require_session()`（`:462-470`，会话不存在 ⇒ `SessionQueryNotFound`）/ `read_event()`（`:528-552`，窗口按事件下标取、两端夹紧）/ `trace_event()`（`:555-573`）/ `session_lineage()`（`:605-662`）＋四个结果 dataclass（`:417-459`）＋常量 `MAX_READ_WINDOW = 50`（上游 `SESSION_QUERY_READ_WINDOW_MAX`，`config.ts:6`）/ `DEFAULT_SEARCH_RESULT_LIMIT = 100`（上游 `maxSearchResults`，`index.ts:22`）/ `REPLACEMENT_TYPES`（本地承载替换的两类记录）。② `services/agent/tools/kb.py`（**文件尾追加** + 2 处等量改写，零锚点漂移）：`KB_TOOL_NAMES` 9 → **13**（`:73-80`）、`build_kb_tools()` 末位接 `*_session_query_tools(root)`（`:665`）、四个实现（`:1297-1363` / `:1366-1413` / `:1416-1464` / `:1467-1507`）与声明工厂（`:1510-1605`，四把 `Tool` 全 `read_only=True`、上限 `SESSION_EVENT_HITS_CAP = 100` `:1185`、`before`/`after` ≤ 50）；③ 测试：新增 `tests/test_agent_session_query_trace.py` **23 例**（`:1-522`），`tests/test_agent_tools_read.py:416` 一处断言语义更新。**验收**：`py_compile` 全过；`pytest -q` **308 passed**（原 285）；仓库外临时脚本 Python 级取证（四工具真实输出、105 条命中截到 100 + 上限提示、六类失败码 `NOT_FOUND` / `INVALID_ARGUMENTS`）；`git -C dsh-src status --porcelain` 空、HEAD 仍 `0d1f5000`。**偏差 13 条**（`session_id` 本地必填｜无调用方 `cwd` 授权与错误净化层｜替换关系改由 `compaction.shadowed`·`compaction/prune.pruned[].seq` 承载｜`sourceEventSeqs`/`derivedEventSeqs` 无从计算 ⇒ `None` 且文本明说、**不伪造「无」**｜无 `surfaces`/`availability`/`parent_session_ids`/`include_root_sessions` 过滤｜无 `Config` 与 `searchTimeoutMs`｜结果文本落为中文并保留本地「引用形状」约定｜ISO 8601 毫秒截断｜错误码取 `INVALID_ARGUMENTS`·`NOT_FOUND`｜不注入上游 `PROMPT_TEXT` 指引段）与 **4 条未实测**见 §6.17；**§5.1 会话检索行由 1/5 收敛为 5/5**。**`docs/todo.md` 未编辑**（另一写者并发重写中；建议台账行见本轮报告） |
| 2026-09-20 | **选区引用带位置 + 气泡入口 + 打字框 chip（§6.20，三项一并落地）**：用户三条报障 —— ①「实际写入对话的仍然只是 `@文件名`，根本没有标出对应内容的源码位置」；②「对话栏仍然不能悬浮显示加入对话」；③「引用仍是 `@` + 纯文本而不是在打字框里面把引用渲染一下」。**A（AG07 的 L 路线：读时投影）**：token 语法定为 `@相对路径#L12-L30` / `@路径#L12` / `@"含 空格"#L12-L30`（只有这两种，不发明第三种）；前端 `formatRangeMention()`（`agent-panel.js:3192`）—— 源码区取 `.-line[data-line]` **精确行号**，预览区取块级 `data--src-line[-end]`（**近似**：字符级所需的 `annotateSegments()` 全仓**无调用点**，如实标注不假装）；`tools/kb.py` 尾部追加 `_at_range_parts()`/`_anchor_range_result()`（`:2621`/`:2635`）+ 区间分支委托调用 ⇒ `ok`（行范围 + 首末行摘要 + `read_document(offset, limit)` 建议）/ `invalid`（倒置）/ `not_found`（越界），`_detect_reference_kind()` 先判区间形态归 **anchor**，`audit_references` ①跳过区间 token、④剥 `@` 校验，检查名 `anchor.range_inverted` 替换 `anchor.range_unsupported`；**投影只回行号与首末行**（正文仍由模型自取）；`prompt.FILE_REFERENCE_SECTION` 第 2 条同行补一句（**零行漂移**）。**B（气泡选区）**：`selAddHit()` 追加 `#agent-messages` 宿主；「气泡 → seq」= `conversation_messages()` 每条记录**追加 `seq` 键**（user 气泡 = 该轮 `user/message` 的 seq；assistant 气泡 = 该轮**最后一条非空** `assistant/message` 的 seq），前端标 `data-agent-seq`；token = `@[label](dsh-session:<base64url>#seq:<n>)`（跨气泡 `#seq:<起>-<止>`）；后端 `split_session_fragment()`（`reference.py:528`）+ `_MENTION_RE` 裸 URI 分支扩片段 + `parse_session_references()` 追加 `seq_from`/`seq_to`（**无片段形状逐字不变**）+ `build_snapshot()` 片段投影（去重键升为 `(session_id, 片段)`，落不到消息 ⇒ `fragment` 省略通知）；语法层倒置 ⇒ `SessionReferenceError`。**C（打字框 chip）**：**镜像层** `.-agent-composer-mirror`（追加在 `.-agent-composer` 末尾、靠 `z-index` 压在 textarea 之下；同字体/字号/行高/内距/换行 + 几何与滚动同步 + `MutationObserver` 抓字号 + 三个包装器抓程序化插入与发送清空）把 token 包成 chip，textarea 文字透明、光标与选区仍归 textarea，**chip 逐字保留 token 原文**（否则错位）；无 token ⇒ 摘类隐藏 ⇒ **零视觉差异**。**验收**：`pytest -q` **335 passed**（原 326 + 新 9 例）、`py_compile` 4/4、`node --check` 3/3、`i18n_selftest` 12/12、仓库外临时脚本行为取证（区间 ok/倒置/越界、片段解析与快照投影、`ask()` 端到端请求文本）、HTTP 静态面（harness 8660）复核新标记在线。**锚点重取**：`tools/kb.py:1608-2591` → `:1608-2710`（2 处引用就地更新）；校正既有 off-by-one `agent-guide/06` 的 `session/reference.py:142` → `:143`。**未实测**：浏览器 DOM 交互全线（无浏览器工具）。**`docs/todo.md` 未编辑**（建议把 AG07 推进为「P + V + L 全部落地（读侧）」）。 |
| 2026-09-20 | **气泡「可寻址」：会话片段带消息内字符区间（用户选 C）+ 短别名 token**：用户口径「C. 渲染也做可寻址结构」「这个就是我想要的，而且 memoria 本身就有成熟的 AST 映射」＋「会话引用不需要渲染会话id，太占地方，**实际要传入**」。**① 语法（前后端同一套，1 起闭区间，与文件引用 `#L3C2-L5C7` 同口径）**：`#seq:<条>` / `#seq:<起>-<止>`（既有）/ **新增** `#seq:<起>c<a>-<止>c<b>`（消息内字符位；同一条内两端重复写条号，如 `#seq:3c12-3c48`）；缺 `-` 段的字符位 ⇒ 该端按消息末尾；缺 `c` ⇒ 该端整条。**② 后端** `services/agent/session/reference.py`：`_SEGMENT_RE` 扩为 4 组（`:525`）；末尾追加 `split_session_fragment_full()`（`:620` 起，⇒ 上方锚点零漂移）⇒ `{seq_from,seq_to[,char_from,char_to]}`，**语法非法明确报错**（起>止 / 同条内字符位倒置 / 字符位<1）；`split_session_fragment()` **签名与返回形状不变**（内部改走完整解析）；`_fragment_fields()` 透传完整字典 ⇒ 引用项**只在给字符位时**多出 `char_from`/`char_to`（无片段形状逐字不变）；`build_snapshot()` 的片段视图经新增 `_slice_fragment_view()` 裁到字符区间（**同一条内一次算完**，绝不"先切头再切尾"；缺端 = 该消息首/末；越界**钳到边界**；裁完一个字不剩 ⇒ 回空列表走既有 `fragment` 省略通知，不静默）；`_reference_fragment()` 升为 4 元组（`planned`/`seen` 标注同步）；`_MENTION_RE` 裸 URI 分支接受 `c<数字>`。**③ 前端** `agent-panel.js`：**不换渲染管线**（助手气泡的 `sanitizeHtmlInto()` 是硬前置、**丢弃全部属性** ⇒ 渲染期标记活不下来；助手输出属不可信文本，换净化链是安全回退），改**渲染后反标** —— `annotateMessageOffsets(el, text)`（`:3850`，在 `renderBody()` 同行接线）利用"可见文本一定是消息原文的**有序子序列**"逐文本节点贪心定位，套 `[data-md-from][data-md-to]`（**0 基半开**、值为消息原文偏移）；定位不到标 `data-md-drop="1"` 并冻结游标（不猜）。`messageOffsetAt()`（`:3877`）把选区端点映射回原文偏移；`selectionLocation()` 两个 messages 分支追加 `offFrom`/`offTo`；`addSelectionToChat()` 把两端偏移交给 `sessionFragmentToken(from,to,offFrom,offTo)`；纯函数 `fragmentSuffix()`（`:3889`，0 基→1 基，**缺一端/倒置一律退回整条**）拼后缀，`fragmentSpanText()`（`:3900`）拼 chip 可见串（`3:12–3:48`）；气泡片段 chip 的 tail 由裸序号改该串（title 仍为原始片段）。**④ 短别名**（同轮）：`formatSessionMentionToken()`/`sessionFragmentToken()` 走 `sessionAliasUri()` ⇒ 输入框只出现 `@[标题](dsh-session:s1#seq:3c12-3c48)`，真实 id 留内存表；`ask()` 发送前 `expandSessionAliases()` 换回完整 URI ⇒ 发后端 / 落盘 JSONL / 气泡渲染**一律可解析**；镜像 chip 会话分支改判 `sessionAliasOrUriOk()`。**验收**：`pytest -q` **350 passed**（原 342；新增 `test_agent_session_reference.py` 字符区间 5 例 + `test_agent_panel_token.py` 别名/片段 2 例，后者用 **node 实跑**从真源码抽出的纯函数）；`node --check` 3/3。**未实测（如实）**：① **反标在真机气泡上的逐字对齐** —— harness 的配置未隔离，恢复会话需写 `config/ui-settings.json`（**真实用户配置**；本轮误写一次，已由运行中的 app 重写回原状，见同轮报告），故未继续；② 助手气泡（marked 产物：表格补齐空白 / MathJax / 图片 alt）的反标命中率只有设计论证 + "找不到即 drop" 兜底，**未逐篇实测**。**偏差**：字符位按 Python `str` 下标（码点）而非 UTF-8 字节（前端 `textContent` 同口径）；跨条选区只裁两端，中间各条整条投影。`docs/todo.md` 未编辑（另一写者并发重写中） |
| 2026-09-22 | **审批档位移植（吃 `interaction/permission-presets` 的会话级档）+ 逐条确认打通**：人「继续移植上游」＋四问拍板（英文机器键 + 中文显示名 / `auto` 保留闸门 / 默认档 = 自动审批且**按 agent 配**（设置面板可改）/ 手动档**做通逐条确认**）。**上游最小核心两条**：① 会话级**可回放**的旋钮状态（`permission/preset` + `approval/policy`，生效值 = 最后一个覆盖事件 ?? 组合默认）；② 统一审批闸（四值封闭词汇，**只有 `allowed-once` 放行**，`unavailable` fail-closed）。**本地裁剪**：`sandbox/mode` 那一半不移植（无 shell / 无进程隔离 / 网络不在其词汇内）⇒ 只剩一个旋钮；`custom` 按上游做成**派生只读态**（可展示、不可作切换目标、不进事件载荷）；`session/end-seed` 不移植（无子代理）。**改动**：新增 `services/agent/permission_presets.py`（档位表/fold/derive/set/pin/policy_for/catalog）与 `services/agent/approval_bridge.py`（进程内信箱：登记 ⇒ 面板轮询可见 ⇒ 回填唤醒；超时 120s ⇒ `unavailable`、取消 ⇒ `cancelled`、**未挂载 ⇒ 立即拒绝不空等**）；`approvals.py` **文件尾追加** `RISKY_OPS`/`write_is_risky()`/`GuardedPolicy`（`ApprovalOutcome`(50)/`DefaultApprovalPolicy`(102)/`AskPolicy`(128) 锚点零漂移）；`ask.py` 文件尾追加 `_bind_permission()` + 函数内**等量替换 1 行**（`approval=approval` → `approval=_bind_permission(root, session, approval)`，行数不变 ⇒ `ask.py:445` 零漂移）；`ask_stream.py`（`_run` 的 `attach()/detach()`、`cancel()` 的 `abort()`、`snapshot()` 追加键 `pending_approvals` 只增不改）；`llm/config.py`（`permission` 进白名单 + 文件尾追加 `PERMISSION_KEY`/`_coerce_permission()`/`permission_presets_map()`）；`presentation/api/ui.py` 文件尾追加四个 RPC + 运行期挂载；前端 `agent-panel.js` 末尾块 + `index.html:345` 同行追加第三个 `<label>`（行数不变）+ `app.css`/`zh-CN.js`/`en.js` 末尾追加。**验收**：`pytest -q` **853 passed**（新文件 `tests/test_agent_permission_presets.py` **37 例**）；`node --check` ×3、`i18n_selftest` 全 PASS；**L4 实渲染**（harness 8655 + 临时库 + **脚本化 provider**，不联网）：后端闭环证明「风险写真的被拦 ⇒ 回填 `allowed-once` ⇒ 盘上真的改名」/「`all-access` 不再挂起且照样写成功」/「`manual` + `rejected` ⇒ 工具结果 `DENIED`」/「三档切换在会话 JSONL 里可回放」；浏览器内证明选择器三项可切换 + `custom` disabled、设置页同族行在位、卡片按钮可用且点击后写盘成功。**L4 抓出并修掉两个真 bug**（都已复验）：㈠ 待批卡按 `call id` 单键去重，而 call id 只保证一轮内唯一（跨轮复用 ⇒ 新待批项被静默跳过 ⇒ 挂起 120s 后判拒绝、**写入静默死掉**）⇒ 改 `call id + created_at` 复合键（复验卡片计数 1 → 2）；㈡ 点按钮写下的终态被下一帧的通用「已处理」覆盖 ⇒ `markApprovalCardDone()` 加"已有终态即返回"守卫（复验跨帧稳定为 `Allowed once` / `Rejected`）。**未移植/未验（如实）**：`/permission <preset>` 命令面、`approval/asked`·`approval/decided` 审计事件、部署可配置档位表；真机真实端点下的观感未验。**偏差 5 条**（`never` 语义本地化｜`auto` 值本地新增｜档位键本地命名｜无 sandbox 维度｜默认档从上游 `settings` 命名空间改到 `config/agent.json: permission.<agent>`） |
| 2026-09-22 | **修复：`read_document` 只认 `.md` —— 读不了非 markdown 文件**（人：「我发现 agent 读不了非 markdown 文件」）。**这一条是往**上游**靠、而不是偏离**：上游 `read` 吃任意路径。**根因**：本地读面一处**不对称** —— `glob`/`grep` 走 `_walk_kb_files()` + `_safe_rel_any()`（不限扩展名）⇒ 模型看得见 `data.csv`；`read_document` 走 `_safe_rel()`（`tools/kb.py:160-163` **要求 `.md` 后缀**）⇒ 真去读回「path 必须是…相对 `.md` 路径」；且工具描述/`@路径` 段都写"Markdown 文档"⇒ 模型压根不试。**改动**：`_read_document_call()` 里**等量替换 1 行**改走新增 `_read_text_or_document()`（分流：`.md`/`.markdown` → 既有 `_read_document()`，**语义一字未改**；其它 → `_read_plain_text()`：纯文本窗口、不剥 frontmatter、无 sidecar/KP 段、NUL ⇒ `BINARY_FILE` 指路 `read_image`、`utf-8-sig`（吃 BOM）→ GB18030 → 有损兜底、前 1 MiB 上限并如实标注）；配套把 `read_document` 的工具描述、`path` 描述与 `prompt.FILE_REFERENCE_SECTION` 第 2 条改成"不限 `.md`"（**等量改写**，锚点零漂移）。路径守卫未松（越界/上跳/绝对路径仍 `INVALID_ARGUMENTS`）。**验收**：`pytest -q` **865 passed**（`tests/test_agent_tools_read.py` +9 例）；**L4 实回合**（harness 8661 + 临时库 + 脚本化 provider）真发 `read_document`：`.csv`/`.py`/GBK `.txt` 全部 `is_error=false` 且正文回显、`.bin` 回 `BINARY_FILE`。**未改（如实）**：左侧文件树仍只列 `.md`（`list_files()` 用 `collect_md_files()`）⇒ 非 md 在树上不可见/不可拖；引用**锚点**形态（`文件:行号`）仍限 md |
| 2026-09-22 | **轮次预算回归上游：`max_iterations` 默认 0 = 无上限**（人：「怎么有连续调用工具的 8 轮上限，上游都没有」）。上游口径（`core/agent-loop/README.zh.md:200`）：「**没有内置轮次预算**：工具调用或 steering 会让当前轮次继续；限制失控轮次的策略必须从既有生命周期扩展点（如 `agent/turn-stopping`）执行取消」——本地 M1 却把 `max_iterations = 8` 当安全上界（§6.6 偏差表第 ① 条，当时就登记为"本地新增"）。**改动（全部等量改写/末尾追加 ⇒ 锚点零漂移）**：`DEFAULT_MAX_ITERATIONS` **8 → 0**；`AgentLoop.__init__` 校验 `< 1` → `< 0`（负数仍拒）；循环头 `range(1, (self.max_iterations or UNBOUNDED_ITERATIONS) + 1)`；文件尾追加 `UNBOUNDED_ITERATIONS = 1_000_000`（永远到不了 ⇒ 保留 `StopReason.MAX_ITERATIONS` 防御性出口，也不引 `while True`）。**失控出口**= 前端「停止」（真取消 `CancelToken`，协作式）；配套把面板 `POLL_TIMEOUT_MS` 5 分钟 → 30 分钟（仅"面板不再等"的兜底，不改作业语义）。**验收**：`pytest -q` **868 passed**（`test_agent_loop.py` +2：默认预算下**跑满 12 步**工具调用再收尾 —— 旧默认 8 下必失败；0/正数/负数三种取值语义）；**L4 实回合**（harness 8662 + 脚本化 provider）连续 12 次 `read_document` 全部执行、`loop/end` 为 `stop_reason:"final-answer"`、`iterations:13`。**偏差表第 ① 条**已就地改为"默认 0 = 无上限（对齐上游）" |
| 2026-09-22 | **补齐「读后写守卫」+ 审批审计事件 + `never` 改名**（人从"我们改了上游设计"清单里点名三件：「补审批审计事件」「改 never 命名避歧义」「补读后写守卫 + 登记台账」）。**三件都是"向上游靠"** | **① 读后写守卫**（`services/agent/observation.py`，语义移植 `fs/fs-observation-policy`；上游 README 的口径已逐条对照进模块头）：观察态 = `{rel: (present, sha256)}` 三态（unseen / confirmed absent / present@version）；`read_document`/`read_kp` 成功即记（`NOT_FOUND` 记"确认不存在" ⇒ 授权之后的 guarded create）；**只有 `create_file` 免读**，其余 op 未读 ⇒ `FS_NOT_OBSERVED`、读到过但当时不存在 ⇒ `FS_NOT_FOUND`、sha256 变了 ⇒ `FS_STALE_VERSION`（三条都给"重读再重提"的恢复指引）；观察表**进程内、不跨会话**（= 上游"resume 后须重读"）；**写成功后 `_refresh_observations()` 刷新版本**（= 上游 `fs/observed`：成功的改动本身更新观察记录，否则模型改完自己就撞 STALE）。落点：`tools/kb.py::_observation_block()` 在写工具处理器里（上游是 `fs/*` 事件闸 + provider 的原子 CAS，本地无事件层 ⇒ 比较-写非原子，如实登记）。**② 审批审计事件**：`approval_bridge.EVENT_ASKED/EVENT_DECIDED`（载荷与上游对齐：`{id, tool, reason}` / `{id, outcome}`，`id` = tool call id），由 `ask._bind_permission()` 把本会话 `session.append` 装给审批桥 ⇒ **每次 ask 恰一条 decided**（决定/取消/超时/摘除都走同一出口，log-only 不进模型请求）；审计回调抛错也**不影响裁决**（旁路）。**③ `never` → `allow-all`**：本地这档是"不问 ⇒ 一律放行"，上游 `never` 恰好相反（"不问 ⇒ 需审批者一律拒绝"，靠 sandbox 兜底）⇒ 同名反义易误判，改名；**旧会话事件里的 `never` 仍按 `allow-all` 只读兼容**（`LEGACY_APPROVAL_POLICIES`，会话日志 append-only 不重解释）。**顺带修**（L4 暴露）：同一秒内第二次 `propose_write` 会撞批次目录（txid 原先写死 `-01`）⇒ `WRITE_FAILED (backup_failed)：批次已存在`，改 `_next_txid()` 递增序号。**验收**：`pytest -q` **891 passed**（新 `tests/test_agent_observation_gate.py` 15 例、`test_agent_permission_presets.py` +5 例、`test_agent_plan_rpc.py` 把"越界路径"用例拆成"闸更早拦 + 编译器兜底"两例）；**L4 真实回合**（harness 8663 + 脚本化 provider，不联网）：未读就写 ⇒ `FS_NOT_OBSERVED` 且盘上**零写入**（无 sidecar）、先读再写 ⇒ `demo-kp` 真的落进 `.memoria/sidecars/notes/demo.memoria.yaml`、新会话直接改名 ⇒ 又是 `FS_NOT_OBSERVED`（观察不跨会话）、人工放行的风险写 ⇒ 会话 JSONL 落 `approval/asked {id:w1,…}` + `approval/decided {id:w1, outcome:allowed-once}`。**如实交代**：① 无应答者的调用方（CLI 未挂载）不经过审批桥 ⇒ 不产审计事件（可见面是工具结果 `DENIED`），与上游"无 handler 也记 `unavailable`"有差；② 档位表仍是代码常量（上游 `Config.presets` 可配）；③ 真机面板下的观感未验 |
| 2026-09-22 | **订正本文件里的过期行（docs only，未改任何源码）**：本文件是 2026-09-20 的快照，M3 落地后多处仍写「未移植/未实施」⇒ 逐行核对代码后就地更正：**§5.1 写工具两行**（`write`/`edit`：⏸ → ✅，写清本地形态 = `propose_write` → plan → 编译器 → apply，`KNOWN_OPS` **13** / `COMPILED_OPS` **11**）、**§5.1 写前备份 / 撤销两行**（⏸ 有设计未实施 → ✅ 已落地，`services/agent/backup.py`）、**§5.1 审计行**（"插件审计仍停留在设计" → 已落 `capability/apply`·`undo`·`redo`·`force_save` + `approval/asked`·`decided`；余差 = `capability/backup` 未产事件）、**§5 `user-approval`·`tool-ask-user` 行**（拆开：审批已落 / `tool-ask-user` 仍未移植）、**§5 `commands`·`permission-presets` 行**（拆开：后者 ✅ 2026-09-22 已落三档；`commands` 仍 ⏳ **但消费方已出现**）、**§5 `credentials-local` 行**（原写落到 `services/agent/credentials.py` —— 该文件**不存在**，语义实际在 `llm/config.py`）、**§5 `credentials/authorization` 行**（改为"条件性，复核仍不适用"）、**§5 `storage/skill/hooks/…` 行**（写明"整族一个都没吃"且能力插件**契约本体仍未实现**，`capabilities.json` 零命中）、**§5.1 `skill` 形态行**（"只做了目录约定" → `src/**` grep `skills` **零命中**，连目录约定都未进代码）、**§5.1 gap 清单（③）**与 **§8 M3 行 / §8「仍标 ⏳ 的行」整段**（按 2026-09-22 实况重刷：写面/备份/撤销/守卫/审计/权限档从 ⏳ 转 ✅；仍未落地四项按建议顺序列出）、**§6.13 引用机制扩展**（标题与 A/B/C 三行：⏳ 待规格化 → ✅ 已落地 §6.20/§6.21）。**新发现（同轮）**：`src/**` 内 **`capabilities.json` 与 `skills` 零命中、无命令注册表、无 `ask_user` 工具、无 `services/agent/credentials.py`** ⇒ "能力插件契约本体 / `commands` / `tool-ask-user` / `skill` 形态"四类属**设计有、实现无**（已在对应行写明）。**未改**：`dsh-src/` 检出（仍 pin `0d1f5000`）、任何 `src/**`。登记见 `docs-management.md §4.2` |
| 2026-09-22 | **技能（skill）规则面落地（吃 `packages/skill` 的规则，结构按本地重落）+ §6.22**：人问「上游 skill 机制可以照搬吗」⇒ 逐包读码后结论 = **规则可照搬、外层四块不可**。**① 新模块** `src/memoria/services/agent/skills.py`：名字语法、根表 rank、发现（平铺 `<name>.md` / 目录包 `<name>/SKILL.md`，**只认根的下一层**）、YAML frontmatter 契约（必填 `name`+`description`；可选 `whenToUse`/`disable-model-invocation`/`user-invocable`；**宽松布尔** `true/yes/on/1` ↔ `false/no/off/0`；**旧键主动拒绝** —— `modelInvocable` 之类必须写 kebab 形式）、同名遮蔽（rank → 注册序 → 目录内序，后者仅 warn）、两种渲染（目录行 + description 空白折叠/500 截断；`<skill_content>`/`<skill_resources>`/`<skill_instructions>` 且**正文逐字不转义**）。**② `tools/kb.py`**：`KB_TOOL_NAMES` **行内**追加 `"skill"`（16 → **17** 个；**1:1 行内替换 ⇒ 该文件既有 30 余个 `<文件>:<行号>` 锚点零漂移**）、`build_kb_tools()` 末行同款追加 `*_skill_tools(root)`、文件末追加 `_skill_tools()`/`_skill_tool()`（只读；非法名 `INVALID_ARGUMENTS` / 未知名 `NOT_FOUND`（附本轮可用清单）/ 不可模型调用 `SKILL_NOT_INVOCABLE` 三类错误照搬上游）。**③ `prompt.py`**：`sections.append(TIME_CONTEXT_SECTION)` 那**一行等量替换**为 `sections.extend(_skill_and_time_sections(kb_path, tools))`（**行数不变 ⇒ `prompt.py:263`/`:270`/`:385-394` 等 15 处文档锚点零漂移**），文件末追加该函数（门控 = `skill` 工具在场**且目录非空**；`skills` 走函数内延迟导入）。**④ 有意不落四块**（逐条理由见 §6.22 偏差表）：`skill-filesystem` 的 **watcher**（~350 行 Chokidar）、注册表的 **"层"**（Cordis `ScopedLayers` + scope 链 ⇒ 本地塌成单层扁平合并）、**持久目录消息**（上游把目录作为可原地替换的 `user/message`，`source.kind='skill-catalog'` ⇒ 本地改落成 **system 提示的一段**、**不落盘**）、**`/name` 用户手势**（需命令注册表）。**⑤ 根表只吃一个根**：`<kb>/.memoria/agent/skills/**`（rank 100）—— 上游按 cwd **向上找 `.git`** 定工程根再叠 `~/.dsh`、`~/.agents`，而 Memoria 没有"工程根"概念且库外根会破坏"允许根"纪律 ⇒ **全局根留待拍板**。**⑥ 本地新增两条硬边界**：单文件 > 64 KiB 跳过、必须 UTF-8；未移植 `metadata` 字段（无消费方）。**验收**：新增 `tests/test_agent_skills.py` **50 例**；`pytest -q` **953 passed**（原 903）；`tests/test_doc_anchors.py` 通过。**如实交代**：① **无 L4 实回合**（未验真模型看到目录段后会不会去调 `skill`）；② 目录段进 system 提示 ⇒ 技能变动会让 KV 前缀失效，且**不进会话日志**（回放看不到当时的目录）；③ `user-invocable` 与 `disable-model-invocation` 已按上游解析但**暂无用户入口**（后者在本地等于"无任何入口"，发现时记 warning 如实说明）。**台账**：`docs/todo.md` 新增 **AG21**；`reference/agent-guide/10` 的工具计数 15 → **17** 同步订正 |
| 2026-09-22 | **补 `move_file` op（跨目录搬整篇 = `kb.file.move`）—— 属"本地发明"，与上游无关；同时推翻 design 里"按 §6 R2 不做"的旧判定** | 来源 = **产品内 agent 的真机报障**（它要按目录方案把 3 篇挪进 `expressions/phrases/`，却报告"写接口不能跨目录搬文件：`rename_file` 只改文件名、保持所在目录，也没有改 sidecar `file:` 字段的接口"）。**重新推演 R2**：旧判定过宽 —— `[[id]]`/`[[stem]]` 是 id/stem 寻址（移动不改 stem ⇒ 引用天然不断，按 id 索引的 `errors.json` 同样不受影响）、图片引用按规范是**库根相对** ⇒ 都不受移动影响；R2 真正管的是**"文件相对"写法** ⇒ 落法改**拦**（`move_breaks_relative_refs`，判据 = "按库根解析不到、按文件所在目录解析得到"）。**改动**：`services/document.py` **末尾追加** `move_file_document()`（**不做成类方法**：类体铺到文件末附近，插方法会让其下约 30 处 `document.py:<行号>` 锚点漂移）+ 补齐旧版同目录侧车搬迁 + `apply_path_move()` 级联；`plan.OP_MOVE_FILE`；`file_ops.move_plan()`/`apply_move_file()`；`apply.py` 原语（备份集 = 源与目标两侧）；`approvals.RISKY_OPS`；工具说明 ⑫；**顺序规矩**新增 `file_ops_must_be_last`（文件级 op 之后不得再有非文件级 op），`move_file` 可**连排多条**。**验收**：`pytest -q` **961 passed**（`test_agent_file_ops.py` +8 例）；`test_doc_anchors.py` 通过；真机路径实测（临时库 + 真工具入口）`read_document` → `propose_write[move_file]` ⇒ 已写入、旧位置没了、引用方 `[[flee-the-nest]]` 原样。**未做**：目录级移动仍无；不支持"移动+改名"同批；无 L4 实回合。台账：`docs/todo.md` **AG22**；`agent-plugin-design.md` §7 2.6 行 / §6 迁移清单第 13 行 / §8 依赖表同步订正 |
| 2026-09-22 | **斜杠命令最小面落地（吃 `interaction/commands` 的注册表 + 生命周期；内建 `/compact`·`/permission`）+ §6.23** | 拣选依据 = **消费方已经出现**（自动压缩 §6.16 落地 ⇒ `/compact` 有真实需求）。**新模块** `services/agent/commands.py`：`COMMAND_NAME_RE` / `parse_command()`（正则与 `rawInput` 含分隔空白**逐字照搬**）、**单层扁平**注册表（`register`/`find`/`descriptors`，注册期即校验名字与描述）、`execute()`（**未知名 ⇒ 不落任何事件、回 `None`**；`command/run` → handler → `command/done` 成对且 log-only；`recordInput:false` 省 `args`；handler 抛异常**先**落 error-done 再抛；`commandId = cmd-<实例令牌>-<自增序号>`）、`ok()`/`err()`（error 文本必须非空）、`default_registry()`、`handle_command_line()`（回 `AskResult`）。**两条内建**：`/compact`（复用**同一个** `ask._compact_if_needed(force=True)`；`force` 只跳过阈值判断，先裁后压/`select_span`/fail-open 全线不变）、`/permission <档位>`（复用 `permission_presets.set_preset()`）。**挂点** `ask()`：`registry` + `system` 建好后插入分流（上下文此刻刚好齐 ⇒ 与主回合同参），命中即 `return` —— **不落 `user/message`、不进 loop**；未注册的斜杠行**原样进模型**。**`ask.py`**：`_compact_if_needed` 的 `force` 形参与阈值判断均为**行内 1:1 替换**（`cancel: … force: bool = False,` 同一行）；挂点为**中段插入 +15 行** ⇒ 文档里的 `ask.py:421` **重取为 `ask.py:445`**（4 份文档 7 处），并**登记** `agent-guide/10` 其余 `ask.py:<行号>` 锚点**早在本轮前就已陈旧**（需专项重取）。**RPC/前端**：`ui.py` 文件末追加 `agent_command_list`（纯只读）；`agent-panel.js` 文件末块（IIFE 末尾、只包装既有函数）：命令轮气泡加 `-agent-msg--command` 并**摘掉用量行与复制按钮**（零 token、也没有可复制的"回答"）、输入 `/` 时给一行可用命令提示（数据来自 RPC）；`app.css` 与两份 i18n 末尾追加。**未移植**：scope 分层、附件（`input.attachments`）、`/` 补全弹层与键盘选择、`sourceEventSeq` 生产者、命令名 i18n。**验收**：新增 `tests/test_agent_commands.py` **33 例**（含"`/usr/bin`、`5/8`、大写、全角空格、前导空白**一律不是**命令"、"未知名零事件"、"命令轮 `provider.requests` **零增量**且 `user/message` 不增"、"`/compact` 真压下去（恰一次摘要 + 一条 `compaction`）"、"`/compact` 无可压区间时**零模型调用**"、"`agent_command_list` 纯只读"）；`pytest -q` **995 passed**；`node --check`×3 + `i18n_selftest` + `test_doc_anchors.py` 全 PASS。**如实交代**：无 L4 实回合（未验真机面板 `/` 提示观感）；未做 `/clear`（属产品决定）。台账：`docs/todo.md` **AG23** |
| 2026-09-22 | **`tool/call` 落盘位次对齐上游（"先记账，再干活"）** —— 人「先搁置（插件），先对齐上游」后挑的**最小、锚点最明确**的一条 | **上游口径**：`dsh-src/packages/core/agent-loop/src/tool-calls.ts:168` 的 `appendToolCall()` **先于** `:174` 的 `dispatch()`；本地 `loop.py` 原先反着来（`self.tools.invoke()` **之后**才 `_emit("tool/call", …)`）⇒ 两个后果：① **崩在工具里 = 没有任何调用记录**（日志看不出它发生过；`assistant/message.tool_calls` 是**上一轮**的模型输出，不是调用记录）；② `tool/call.time` 与 `tool/result.time` 是背靠背两次写入（`SessionStore.append()` 每条打 `time`，`session/store.py:215`）⇒ **`toolMs` 恒 ≈0**（测的是写盘间隔而非工具耗时），`session-stats` 那类按事件时间计时的消费方读不到真值（§5.1 `session-stats` 行第 ③ 条、§6.15 末段待办①）。**改法 = 纯等量换位**：把 `loop.py:368` 那一行上移到 `:362`（`self.tools.invoke()` 之前）并在行尾给一句短注（理由与出处落**文件尾**新块）⇒ **总行数不变**、`tool/result` 仍在 `loop.py:369` ⇒ 其下**所有** `loop.py:<行号>` 锚点（`:396`、`:302-399`、`:390-398`、`:380-383`、`:489-506` 等约 20 处）**零漂移**。**配对不变量不受影响**：`registry.invoke()` 把任何失败（未知工具 / 参数非法 / 审批拒绝 / 异常）都转成带错误文本的 `ToolResult`（`tools/registry.py:226`）⇒ 「`tool/call` 之后必有 `tool/result`」照旧成立；回放侧（`session/history.py` 跳过 `tool/call`）与过程行（`turn_process.tool_row()` 按到达序补状态）都不看位次。**验收**：`pytest -q` **1042 passed**（`test_agent_loop.py` **+2 例**：`test_tool_call_is_logged_before_the_tool_runs` 的判据是**在工具体内读会话文件**——那一刻 `tool/call` 必须已在盘上、`tool/result` 必须还不在（这才是可判定的"先记账"）；`test_tool_call_and_result_stay_paired_even_when_the_tool_raises` 钉住异常路径下两条事件仍一一对应）。**如实交代**：① 真机（真实端点 + 真工具）未跑，只在 loop 级用探针工具取证；② **没有任何消费方**现在就按 `toolMs` 算账 —— 本次只是把**前提**做出来（`session-stats` 本地仍判"不吃"）；③ 逐轮成本按轮模型归属仍**未做**（§6.15 末段待办②）。台账：`docs/todo.md` **AG25** |
| 2026-09-22 | **`skill` 的 `/name` 用户手势补齐（吃 `tool-skill` 的 pre-step 注入）+ §6.24** —— 人「继续对齐」；拣选依据 = **前置刚就位**（命令注册表 §6.23），而 §6.22 明写"`user-invocable` 与 `disable-model-invocation` 已解析但**暂无用户入口**" | **上游口径**（`packages/skill/tool-skill/src/index.ts:163-204`、`:409`、`:418-430`）：① 手势 = **空白包围**的 `/name`，可在文本**任意位置**，第二个 `/` 或非边界字符打断匹配（`/usr/bin`、`5/8` 不误判）；② **只扫 `source.kind==='user'`** 的文本块（外部文本伪造不了手势）；③ 候选名 **first-seen 去重**；④ 查注册表：**未知名 / 用户禁用者一律保持普通散文**；⑤ 命中者把 `renderSkillContent()` 作为**注入指令上下文**，**追加在所有其它注入之后**（背景在前、要照做的材料在末）；⑥ 是 `disable-model-invocation` 技能的**唯一入口**；⑦ 与命令注册表是**两个互不相干的闭命名空间**（命令行在宿主侧先解析）。**改动**：`services/agent/skills.py` 文件末追加 `SKILL_GESTURE`（正则逐字照搬）/`invoked_names()`/`render_invocations()`（`__all__` 行内扩三项；**删掉** §6.22 那条已过期的"本地暂无用户调用面"warning）；`prompt.py` 文件末追加 `render_skill_invocation()`（`__all__` 行内扩展 + 模块头"只读调用点"一句等量补名）；`ask.py` **两处行内 1:1 替换**（`:79` 导入名扩为四个、`:445` 末项追加 `render_skill_invocation(root, text)` 并加一句行尾注）⇒ **总行数不变**、所有既有 `ask.py:445`/`prompt.py:263` 锚点**零漂移**。**实现上比上游更严的一点**：扫的是 **`ask()` 收到的用户原文**（`@提及` 改写**之前**）⇒ 连会话标题等**宿主/模型产出**的文本都伪造不了手势。**本地偏差**：注入**只进本轮请求、不落盘**（同跨会话快照 §6.12 / 时间读数 §6.14 口径；上游持久化成 `source.kind='skill-invocation'` 的 user 消息 ⇒ 跨轮仍在，本地要跨轮须先有"消息 `source`"概念）；多块注入以空行相接进**同一条** user 文本（上游是**多条**消息，单条注入逐字等价）。**验收**：`tests/test_agent_skills.py` **50 → 56 例**（正则边界与去重 / 未知名与 `user-invocable: false` 保持散文 / `disable-model-invocation` 技能**只能被手势带进来** / 注入块形状与位次 / **`ask()` 端到端**：请求末尾确有 `<skill_content>` 且**会话 JSONL 里零命中** / `/usr/bin` 不触发）；`pytest -q` **1048 passed**、`test_doc_anchors.py` 通过。**如实交代**：① **无 L4 实回合**（未验真模型收到注入后是否真按技能行事）；② **前端无技能名 `/` 提示**（提示只列注册命令；上游的 transcript chip 属客户端装饰，本地未做）⇒ 目前要求用户**记得技能名**；③ 手势只在本轮生效。台账：`docs/todo.md` **AG26**；§6.22 的三处过期行（表 ③、偏差 2/3、如实交代 ③）已就地订正 |
