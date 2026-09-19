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
| `core/agent` · `agent-default-model` · `agent-tool-presentation` | 同上 | agent 定义、默认模型、工具呈现 | ⏳ 按需 | 同上 | M1/M2 |
| `session/session-persistence` + `-jsonl` + `session-format` | 158 ts（整组） | 会话持久化（jsonl）+ 格式定义 | ✅ 吃**当前格式**（迁移链 `v0→v3` ❌ 不吃） | `services/agent/session/store.py` | **M1** |
| `session/session-projection*` · `stats` · `title*` · `telemetry*` | 同上 | 投影/统计/标题/遥测 | ✅ 吃**标题**（`session-title` + `-llm` + `-first-prompt-llm`，§6.11；`-all-prompts` ❌）；投影框架 / 统计 ⏳；**telemetry（OTel）❌ 不吃** | `services/agent/title.py` | **M2** |
| `context/agent-instructions` | 39 ts | 工作区指令文件 → 上下文（**只加上下文、不加工具**） | ✅ 吃 | 对接既有 `.memoria/agent/kb-spec*.md` | **M1** |
| `context/*-reference` · `time-context` · `tmux-context` | 同上 | 文件/会话引用、时间、tmux | ✅ 吃文件引用（§6.7）与会话引用（§6.12）；`time-context` ⏳、tmux ❌ | `services/agent/prompt.py`、`services/agent/session/reference.py` | **M2** |
| `interaction/user-approval` · `tool-ask-user` | 24 ts | 一次性审批、向用户提问（fail-closed） | ✅ 吃最小面 | `services/agent/approvals.py` | **M1** |
| `interaction/commands` · `permission-presets` | 同上 | slash 命令、权限预设 | ⏳ M2/M3 | 前端指令 | M2 |
| `credentials/credentials-local` | 19 ts | 本地密钥**引用**（配置写名不写值） | ✅ 吃 | `services/agent/credentials.py` | **M1** |
| `credentials/authorization` | 同上 | 授权流程 | ⏳ 需要 OAuth 类端点时 | — | M3 |
| `compaction/*` | 33 ts | 长会话压缩、工具输出裁剪、`/compact` | ✅ 吃 `compaction` + `compaction-basic` + `compaction-tool-result-pruner`；`image-offload` / `command-compact` ❌ | `services/agent/compaction.py`、`services/agent/pruner.py` | **M2** |
| `session-query/*` | 48 ts | 会话检索 | ✅ 吃 `session-query` 的 `extraction`+`filters` 与 `tool-session-query`；`session-query-sqlite` / `session-log-export` ❌ | `services/agent/session/query.py` | **M2** |
| `api/*` · `sdk/*` · `bundle/*` | 162+21 ts | Client↔Host 远程层、JSON-RPC、profile 组合 | ❌ 不吃（若将来要对 Trae/ACP 对接，复用旧稿 D2 的 CLI 面即可） | — | — |
| `storage/*` · `skill/*` · `hooks/*` · `guard/*` · `plan/*` · `goal/*` · `todo/*` | — | 非会话持久、技能、钩子、计划 | ⏸ 按需（`skill` 与既有 `.memoria/agent/` 提示词体系可能重合，M3 再评） | — | — |
| `sandbox/*` · `shell/*` · `terminal/*` · `subprocess/*` · `ssh/*` · `lsp/*` · `mcp/*` · `browser-use/*` · `computer-use/*` · `subagent/*` · `workflow/*` · `jobs/*` · `schedule/*` · `native/*` | 大 | 执行与编排 | ❌ **不吃**（Memoria 不让它跑任意命令；也避免 CVE 面） | — | — |

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

**语义偏差与取舍（上游 → 本地）**：① **`max_iterations=8` 为本地新增**（上游无轮次预算，靠协作式取消）；未移植并行工具、取消信号、runtime context、请求 header 冻结；② 工具错误统一 `Error: <msg> (<CODE>)`（`UNKNOWN_TOOL`/`INVALID_ARGUMENTS`/`DENIED`/`TOOL_FAILED`），只支持 JSON Schema 子集；③ 会话格式自持 `SESSION_FORMAT_VERSION=1`，**与上游 v3 不互通**（未移植 zstd / v0→v3 迁移链 / 跨进程锁 / 崩溃 closer）；④ 指令文件注入进 **system 段**（而非会话消息序列 ⇒ 不回放、不可压缩）；⑤ 审批比上游更严：**只读免审批、写类一律拒绝**（fail-closed），`ask_user_question` 未注册（M1 无问答 UI）；⑥ **只走 lexical 检索**（embedding 需 torch + 权重，与离线优先冲突）；⑦ 零写入靠"**重定向 + 抑制**"4 个库内写点（jieba 缓存 / lexical 缓存 / search_aux / manifest 保存）——属本地新增机制，**将来新增写点必须同步维护该清单**（已写进 docstring）；⑧ `credentials` 不单独实现（`llm/config.py` 已覆盖，M3 需多凭据时再评估）。

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

## 6.13 引用机制扩展（待规格化，2026-09-19 立项）

> 来源：用户提议 —— "当前 memoria 有成熟的拖拽选取，你能把这个也纳入引用机制吗（引用对话内容和文件内内容）"。
> 现状：M2 已落两条 **token 级**引用 —— `@相对路径`（上游 `context/file-reference` 语义：**只给模型说明**，内容由模型自己用读取工具取）与 `@[label](dsh-session:…)`（上游 `context/session-reference`：宿主把**有界快照**注入本轮请求）。两者都只引用**整个对象**（一个文件 / 一个会话），**不引用片段**。用户要的是**片段级**引用。

| 子项 | 语义 | 落点 / 前置 | 状态 |
|---|---|---|---|
| **A. 文件内选区引用** | 预览/源码里拖选一段 → 生成引用 token，后端能定位到**具体区间** | 需要区间 token（如 `@路径#L12-L30`）；**必须先定"模型看到什么"**：只给区间（模型自己 `read_document`）还是把摘录直塞（像会话快照那样）。前置：**AG07**（引用/锚点合法性 —— 区间只跳起始行、`#L12-L30` 的解析与投影） | ⏳ 待规格化 |
| **B. 对话内容引用** | 选中某条回复 / 某段对话 → 作为下一轮显式上下文 | 台账 **AG01** 已是同一诉求（"引用 agent 回复内容再追问，粒度/入口/请求形状未定"）⇒ 与本项**合并规格化**。实现上最自然的形态：给 `dsh-session:` 加片段维（`#msg:<seq>`）或复用会话快照的"单消息投影" | ⏳ 待规格化（并入 AG01） |
| **C. 入口** | 选区之后如何"变成引用" | 复用既有链路：文件树拖拽已有先例（`file-tree.js` → `insertMention`）；对话面板同理 = 选中 → 悬浮动作/右键 → 把 token 插到输入框。**不做**隐式自动引用（保住上游"用户在消息里显式圈定"口径） | ⏳ 随 A/B 定 |

**共同约束**：① 片段若直塞内容，同样要过**不受信任**警告与 `<` 转义；② **不落盘**口径与 §6.12 偏差 1 一致（JSONL 只留 token）；③ 新 token 形态先写进本表与 `reference/agent-guide/01` §6 的 token 清单，再动手。

---

## 7. 四条红线怎么落（逐条）

| 红线（出处） | 本方案的落法 |
|---|---|
| **离线优先**（designV0） | 应用**默认可用但可一键关**出网；模型仅走用户自配端点；不内嵌权重、不后台拉取任何东西；`.memoria/cache/**` 之外不新增缓存 |
| **禁止 silent 写入**（designV0:254,911） | M1 工具面**只读**；写能力（M3）一律"提议 → 用户确认 → 应用"，且应用必须走既有服务层（原子写 A7 → 索引失效 G5.4 → manifest/sidecar 同步 A1/A2 → pending 同步 A3），**禁止旁路写文件** |
| **单一事实源**（AGENTS.md §1） | 会话数据落在新事实源（须先登记，见 P3）；提示词/规范仍只有 `.memoria/agent/**` 与 `resources/agent-prompts/**` 两处（后者是程序读取源） |
| **免安装、可离线分发**（`build.py` 硬门禁） | 纯 Python 实现 ⇒ **不引 Node、不引新运行时**；新增依赖须过 `packaging/build.py` 的 `_REQUIRED_RELEASE_RESOURCES` 与体积预算（M1 目标：轻量包增量 < 2 MB） |

---

## 8. 分阶段

| 阶段 | 范围 | 出口（门禁） |
|---|---|---|
| **M1** | 应用内对话 + 读库问答（只读工具、单一会话、jsonl 持久化、密钥本地引用、出网开关） | §6.4 全绿 + 用户真机走查 |
| **M2** | 长会话（compaction）+ 会话检索（session-query）+ 上下文引用（file/session reference）+ 标题 | M1 门禁 + 压缩前后 A/B（上下文长度、回答可回溯性） |
| **M3** | 写能力：提议 → 确认 → 应用（per-KB 开关 + 逐条确认）；对接既有写链路 | "无 silent 写入"专项验证：任一次拒绝都不改盘；`validate_kb` errors=0 |
| **M4** | 对外契约（若届时 D2 仍在推进）：复用旧稿 §7 的 T1 CLI 面，把 M1–M3 的能力暴露给外部 agent | 契约文档 + 版本协商 + 只读默认 |

> **M2 落盘口径（2026-09-18 拍板）**：compaction 的结果**持久化进会话 JSONL**（新增一种记录类型，由 `session/history.py::build_history()` 回放时把被覆盖区间替换为摘要），对齐上游「把摘要写进会话事件面」的做法；**不**采用「请求期变换 + `.memoria/cache/` 缓存摘要」那条路。
>
> **更正（读码后）**：该新增类型是**纯追加**且旧读者对未知 type 一律跳过 ⇒ 旧版本读新文件只是
> **降级为「没有压缩」**，不误读不崩（等价上游 `ignorable: true`）⇒ **不需要** bump
> `SESSION_FORMAT_VERSION`、也无老会话迁移问题。详见 §6.8。
>
> **M2 已落地部分**：§6.7（上下文引用 `context/file-reference`）、§6.8（compaction）、
> §6.9（session-query）、§6.10（`compaction-tool-result-pruner`）、§6.11（会话标题）、
> **§6.12（跨会话引用 `context/session-reference`）**。**M2 已全部落地**；下一阶段为 M3 写能力。

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
| 2026-09-19 | **M2 跨会话引用落地**（吃 `context/session-reference` 的 `uri.ts` + `projection.ts` + `serialization.ts`；**不吃** `spill.ts`（无存储 ⇒ 省略通知写明"未保存"）/ pre-step 监听器 / 投影框架）：新增 `services/agent/session/reference.py`（`dsh-session:` URI 规范化编解码、mention 格式化与解析、`list_candidates`、字节预算快照 + `<`→`\u003c` 逃逸 + 省略通知）；`ask()` 把快照**只**加进本轮 `loop.run()`（**JSONL 仍落干净 `@label`**，见 §6.12 偏差 1）；前端历史行「引用」按钮 + 用户气泡会话 chip（点击切「历史」页签并高亮）。验收：`pytest -q` **245 passed**（原 212 + 33 例 `tests/test_agent_session_reference.py`）；`node --check` 3 文件、`i18n_selftest` 12/12、`scan_ui_strings` rows=5 无新增；**浏览器交互未实测**（本轮无浏览器工具）。偏差、缺口与未实测见 §6.12；§5 映射表与 §8「M2 剩余」同步更新，**M2 至此全部落地** |
