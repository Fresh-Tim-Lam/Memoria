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
| `THIRD_PARTY_NOTICES.md` | **缺失**（`NOTICE` / `NOTICE.md` / `COPYING` 亦均无） | ⚠️ 需新增：登记 `dsh`（**MIT 原文逐字保留** + pin commit + 与 npm 包字段 `BSD-3-Clause` 的差异说明），之后每移植一块追加条目 |
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
| `session/session-projection*` · `stats` · `title*` · `telemetry*` | 同上 | 投影/统计/标题/遥测 | ⏳ 投影与标题 M2；**telemetry（OTel）❌ 不吃** | — | M2 |
| `context/agent-instructions` | 39 ts | 工作区指令文件 → 上下文（**只加上下文、不加工具**） | ✅ 吃 | 对接既有 `.memoria/agent/kb-spec*.md` | **M1** |
| `context/*-reference` · `time-context` · `tmux-context` | 同上 | 文件/会话引用、时间、tmux | ⏳ 引用类 M2；tmux ❌ | — | M2 |
| `interaction/user-approval` · `tool-ask-user` | 24 ts | 一次性审批、向用户提问（fail-closed） | ✅ 吃最小面 | `services/agent/approvals.py` | **M1** |
| `interaction/commands` · `permission-presets` | 同上 | slash 命令、权限预设 | ⏳ M2/M3 | 前端指令 | M2 |
| `credentials/credentials-local` | 19 ts | 本地密钥**引用**（配置写名不写值） | ✅ 吃 | `services/agent/credentials.py` | **M1** |
| `credentials/authorization` | 同上 | 授权流程 | ⏳ 需要 OAuth 类端点时 | — | M3 |
| `compaction/*` | 33 ts | 长会话压缩、工具输出裁剪、`/compact` | ⏸ M2（长会话出现后） | `services/agent/compaction.py` | M2 |
| `session-query/*` | 48 ts | 会话检索 | ⏸ M2 | — | M2 |
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

> **M2 落盘口径（2026-09-18 拍板）**：compaction 的结果**持久化进会话 JSONL**（新增一种记录类型，由 `session/history.py::build_history()` 回放时把被覆盖区间替换为摘要），对齐上游「把摘要写进会话事件面」的做法；**不**采用「请求期变换 + `.memoria/cache/` 缓存摘要」那条路。因此 M2 落地时会**改会话格式** ⇒ 需同步 `SESSION_FORMAT_VERSION`、老会话兼容策略、以及 `reference/agent-guide/10` 的会话格式表。
>
> **M2 已落地部分**：§6.7（上下文引用 `context/file-reference`）。**剩余**：compaction（`compaction/*` 四个包）、session-query（`session-query/*` 四个包）、会话标题（`session/title*` + 投影）。

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
| **P7** | 自身 `LICENSE` 选哪个 | ✅ **已作废（2026-09-17）**：`LICENSE` 本就是 MIT（署名 `FreshTim`）⇒ 无需选择/新建；本条实际只剩**新增 `THIRD_PARTY_NOTICES.md`**（登记 dsh 的 MIT 原文 + pin `0d1f5000` + npm 字段 `BSD-3-Clause` 差异） | 关闭 §4.3 剩余缺口 |

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
