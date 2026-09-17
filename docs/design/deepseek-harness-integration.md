# DeepSeek Harness（dsh）与 Memoria 的双向融入：可行性分析与分阶段规划

> ⚠️ **口径变更（2026-09-17）**：本文的 **D1/D2 二分框架已不再是主线** —— 用户拍板把「**代码级移植 `dsh` 到 Memoria（记为 D1′）**」立为主线，见 [dsh-agent-port.md](./dsh-agent-port.md)。本文 **D1 的 ❌ 结论（不起子进程、不内嵌运行时）与 D2 的旁支结论仍然有效**，保留作可行性分析记录；涉及"产品内对话 Agent"的判断请以新文档为准。

> **用途**：评估 `dsh`（DeepSeek Harness）与 Memoria 的**两个方向**的融入——**D1（正）把 `dsh` 融入 Memoria**、**D2（反）把 Memoria 作为插件融入 `dsh`**（D2 正在由另一项目推进）。说明各方向与 Memoria 既有硬约束（离线优先、禁止 silent 写入、单一事实源、免安装打包）的关系、可选路线、推荐路线、以及每个决策点由谁拍板。**本文只做分析与规划，不含任何实施；实施前须先答复 §13 的阻塞问题。**
> **目标读者**：项目负责人（评审范围与取舍）；推进 D2 的外部项目作者（对齐接口契约）；后续实施 Agent（决策冻结后据此拆任务）。
> **关联文档**：[kb-agent.md](./kb-agent.md)（知识库 Agent 载体决策）、[dicussion.md](./dicussion.md)（P2 LLM 智能层规划）、[designV0.md](./designV0.md)（离线 / 不进热路径 / 禁止 silent 写入三条红线）、[../../AGENTS.md](../../AGENTS.md)（多 Agent 协作契约与权限矩阵）、[../reference/architecture.md](../reference/architecture.md)（四层架构）、[../todo.md](../todo.md)（§9 V 系列 = 需求挂点、§12 = 门禁台账）。
> **状态**：草稿（待评审），2026-09-14（v2：补 D2 反向方向）。

---

## 0. 结论速览

| # | 结论 | 标记 |
|---|---|---|
| 1 | **两个方向的难度与既有决策冲突面完全不对称**：D2 与 Memoria 既有决策**几乎零冲突**（Memoria 仍是纯本地应用、不内嵌 LLM、不联网）；D1 会同时踩中离线、事实源、silent 写入、打包四条红线。 | ✅（D2）/ ❌（D1 直接内嵌） |
| 2 | **D2 的地基已经存在**：Memoria 已有 CLI（`validate` / `repair-paths` / `diagnose-images`），**每个子命令都自带 `--json`**，且写命令**默认只预览、必须显式 `--apply`**——这正好是"提议 → 确认"范式。 | ✅ |
| 3 | D2 的主要缺口不是"能不能调"，而是**对外契约的稳定性**：能力面（工具清单）、传输面选择、版本协商与弃用策略、以及**写权限边界**（当前 93 个 RPC 方法全部面向 GUI，无一个声明过对外稳定性）。 | ⏳ |
| 4 | **`dsh` 与本项目的定位错位**：它是"自主多步执行 + 工具调用 + 沙箱"的通用运行时；Memoria 需要的是"在自有知识库上受控维护与检索问答"。二者只在会话/事件/权限这套**基础设施**上同构（§6）。 | ⏳ |
| 5 | `dsh` 官方处于 **developer preview + 会有破坏性变更 + 未经安全审计**，历史上有沙箱逃逸 CVE（CVE-2026-82533，`≤0.1.1-rc.2` 受影响，`0.1.2-alpha.2` 起修复）→ 不应作为 Memoria 的核心依赖。 | ❌（就"核心依赖"而言） |
| 6 | 推荐：**D2 优先做稳**（先"只读能力面 + 对外契约"，写能力默认关闭并走提议）；**D1 降级为方案 C（仅 LLM 能力层）/ A（研发助手）**；D 方向（借鉴架构）作为文档层面对齐并行。 | 💡（推荐，待拍板） |

**一句话**：把 Memoria 变成 `dsh` 的**能力提供方**（D2）能融入，而且地基已有；把 `dsh` 变成 Memoria 的 **Agent 内核**（D1）会同时踩中四条红线。

---

## 1. 两个方向（坐标与术语）

| 方向 | 关系 | 谁调谁 | 状态 | 本文位置 |
|---|---|---|---|---|
| **D1（正）** | `dsh` 融入 Memoria | Memoria 应用启动/调用 `dsh` 子进程，把"自主执行"引入产品（或研发流程） | 设想 | §3–§6、§8–§10 |
| **D2（反）** | Memoria 融入 `dsh` | 外部 `dsh` 插件调用 Memoria 的能力（检索 / 校验 / 维护 / 提议） | **另一项目正在推进，尚未发布** | §7（重点） |

**D2 的关键含义**：Memoria 从"要引入一个运行时"变成"**要对外提供一个稳定契约**"。这恰好与 [kb-agent.md:17](./kb-agent.md) 的非目标（**不把 LLM 内嵌进 Memoria 应用运行时**）**完全一致**——能力在 Memoria，智能体在外面。

---

## 2. Memoria 到底要什么（目标对齐）

仓库里已经**白纸黑字写下**了这个需求，不需要推测：

| 需求出处 | 原文要点 |
|---|---|
| [todo.md:152](../todo.md) | 未编号条目：「接入大语言模型 api 接口，直接进行对话，增强检索框引擎联网场景能力，同时让用户直接在程序维护发展知识库」 |
| [dicussion.md:331-336](./dicussion.md) | 四层架构中的「**LLM 智能层（Python）**」；**所有输出是"建议"，用户确认后生效，不自动修改 .md** |
| [dicussion.md:474-486](./dicussion.md) | 选型结论：「核心智能需求用 Embedding 即可满足。**LLM API 作为 P2 扩展，用于文档精炼和知识问答**」 |
| [dicussion.md:589-603](./dicussion.md) | 渐进式三阶段：本地 Embedding → **P2 LLM API（用户可选配置 Key）** → P3 可选本地大模型 |
| [kb-agent.md:12-15](./kb-agent.md)、[todo.md:151](../todo.md) V06 | 知识库 Agent（答疑 / 撰写整理 / FSRS 复习），**当前载体 = Trae 智能体** |

**归纳出的四条真实能力需求**：① 对话式检索问答（可回溯到 KP / 行号）；② 受控维护（提议 → 用户确认 → 应用）；③ 确定性调度（FSRS 等，离线可复现）；④ **外部智能体能读同一套知识库契约**（第 ④ 条正是 D2）。

---

## 3. `dsh` 事实基线

> 证据纪律：**【官方】**＝DeepSeek 官方域名 / 官方仓库文件 / registry 元数据；**【第三方】**＝社区文章；**【未证实】**＝无法核实。

| 维度 | 事实 | 来源 |
|---|---|---|
| 许可 | **MIT**（`0.0.1-rc.*` 曾为 BSD-3-Clause，`0.1.0-rc.2` 起才是 MIT） | 【官方】registry |
| 状态 | **developer preview**；「**THERE WILL BE COMPATIBILITY-BREAKING CHANGES**」；`SAFETY.md` 明示**未经安全审计、不得视为安全或生产可用**、沙箱与审批**不保证隔离** | 【官方】README / SAFETY.md |
| 运行时 | **强依赖 Node**（CLI / web / headless / ACP 四个入口）。官方开发指南：Node「supports 22.19+ and 24+」；精确区间与"Node 23 不支持"为第三方口径 | 【官方】+【未证实】 |
| Python SDK | 官方 `deepseek-harness-sdk`：**stdio newline-delimited JSON-RPC**；随包安装**按平台预编译 runtime wheel**（官方称「needs **no system Node.js**」）；**支持 Windows x64**、Python ≥3.10；**必须显式给 `DSH_HOME`**；**不能传完整 Cordis 配置树**（只能选 profile + 有序 patch） | 【官方】python/sdk README、PyPI |
| 四入口 | `dsh web`（`127.0.0.1:3080`，**拒绝 `--host 0.0.0.0`**）；`dsh --profile headless "task"`（stdout 只出最终答案、exit code 表结果、**无交互追问**）；`dsh --profile acp`（**stdout 专供 ACP JSON-RPC 帧**）；Python SDK | 【官方】CLI reference、headless/acp bundle README |
| 首次联网 | 本体仅约 **48 KB 启动器**；真实依赖在**首次使用某 profile 时装进 `$DSH_HOME/profiles/`** | 【官方/半官方】registry + CLI reference |
| 模型接入 | seam `dsh-llm-deepseek`（路由名 `deepseek-official`）与 `dsh-llm-pi-ai`（Anthropic/OpenAI/Bedrock/Vertex/自建网关）；默认公告 `deepseek-v4-pro` / `deepseek-v4-flash` 等，**100 万 token 上下文**；**OpenAI 兼容端点支持**；本地模型（Ollama/vLLM）机制可行但**官方未点名** | 【官方】providers / llm-deepseek README；本地栈为【第三方】 |
| 沙箱 | Linux bwrap/Landlock、macOS Seatbelt、**Windows ACL 受限令牌**（`WRITE_RESTRICTED` + 按工作区派生写 SID，**fail-closed**）；**Docker 非必需**；但官方自陈 Windows runner 为 **`partial`（部分强制）**，且**网络与进程可见性不在沙箱语义范围内** | 【官方】sandbox 文档、`dsh-sandbox-windows-acl` |
| 审批 | 沙箱模式与审批策略是**两个独立旋钮**；内置两档预设：`workspace-write`（+**ask**）与 `danger-full-access`（+never）。`ApprovalOutcome` **封闭且 fail-closed**：只有 `allowed-once` 放行；**无应答默认 `unavailable` = 拒绝** | 【官方】approval / permission-presets |
| 会话 | **只追加 typed `SessionEvent` 日志**（唯一事实源，消息由日志派生，原则「**Model-visible means logged**」）；JSONL / SQLite；fork / resume / **replay**；**compaction 是独立 seam**（三种 log-only 事件） | 【官方】session / compaction |
| 插件 | Cordis：`inject` 声明依赖、`ctx.xxx` 服务键位、四类事件（`emit`/`bail`/`serial`/`waterfall`）、**可逆副作用**（卸载自动回卷）；工具用 `ctx.tools.register(defineTool({...}))`，管线 `tools/pre-execute → execute → post-execute` 可拦截 | 【官方】develop/framework、develop/basic/tool |
| 能力接缝 | 一个 seam = **Definition（`ctx.xxx` + 类型）/ Provider（实现）/ Consumer（面向模型的工具）**；单角色不构成 seam；换 Provider 即改产品行为 | 【官方】capability-seams、develop/practice |
| 换 fs/子进程先例 | `dsh-e2b` POC；但官方明列未完成："host-workspace synchronization / network policy / sandbox discovery 不在 POC 内"、**"not a whole-harness runtime"**、**无任何 shipped composition 默认启用 E2B** | 【官方】packages/e2b/e2b/README.md |
| 已知漏洞 | **CVE-2026-82533**（CVSS 9.4）：沙箱内 agent 经本机未鉴权控制面 API（只校验 `Host` 头）可把会话切到 `danger-full-access` 逃逸；**≤ `0.1.1-rc.2` 受影响，`0.1.2-alpha.2`（2026-08-30）起修复** | 【第三方】多源 + 官方仓库互证 |
| 官方"托壳"先例 | `apps/desktop`（Electron）：pin 精确版本 + 离线 seed，**不开放任何 Web 服务或 loopback 端口**；另有 Python SDK、ACP（可被 Zed 等驱动） | 【官方】架构文档 |
| 未找到先例 | 把 `dsh` 嵌进 **Python + pywebview** 桌面壳的公开案例；**本机也没有那个"把 Memoria 做成 dsh 插件"的工程**（已在 `d:\AAA_Jupyter` 全盘复核，无 `package.json` 命中 `memoria`/`dsh-plugin`） | 【未证实 / 本机实测】 |

**未证实清单**（不得当作决策依据）：完整依赖闭包体积；首启下载量；缓存命中率 97%–99.93% 等宣传数字；Star 数；"暂不接收外部 PR"；ACP 官方方法逐条矩阵；本地 Ollama 具体配置步骤。

---

## 4. Memoria 事实基线：红线 + 对外可调用面

### 4.1 四条红线（逐条带出处）

| 红线 | 原文/证据 | 对 D1（dsh 进产品） | 对 D2（Memoria 当插件） |
|---|---|---|---|
| **离线优先、无云依赖** | 「无云端依赖，全离线」[architecture.md:11](../reference/architecture.md)；「离线 `[✅]` 全部本地；无联网」[designV0.md:1020](./designV0.md)；「LLM 生成 **V1 Won't**…**不进查询热路径**」[designV0.md:987](./designV0.md)；代码级 `HF_HUB_OFFLINE=1` / `local_files_only=True`（`embedding_provider.py:16-17,128,131`、`rerank_provider.py:16-17`） | ❌ 冲突（默认远端 + 首启联网） | ✅ **不冲突**（Memoria 侧不新增任何联网；联网发生在外部 agent 侧） |
| **禁止 silent 写入** | [designV0.md:254,911](./designV0.md)；唯一明文例外 = KB Agent 补写 [kb-agent.md:286](./kb-agent.md) | ❌ 冲突（dsh 默认自主写文件，审批只有 `allow_once` 粒度） | ⚠️ **取决于边界设计**：外部 agent **不得直写** `*.md`/`.memoria/*`，只能调 Memoria 的"预览→应用"面（§7.3） |
| **单一事实源** | [AGENTS.md:16-29](../../AGENTS.md)（仓库级）＋ [kb-agent.md:70](./kb-agent.md)（知识库侧三事实源＝`*.md` + `sidecars/**` + `agent/review/**`）；`manifest.yaml` / `pending.json` / `kp_targets.json` 属**派生产物与状态**，不是事实源；「禁止并行事实源」 | ❌ 冲突（`SessionEvent` 是另一套日志） | ⚠️ 需声明：外部 agent 的会话日志是**过程日志（可删）**，不是知识事实源 |
| **免安装、可离线分发** | `Memoria.exe + lib/ + resources/ + hf/`（`build.py:241-256`）；`_REQUIRED_RELEASE_RESOURCES` 硬门禁（`build.py:193-217`）；完整包 1182.8 MB / 轻量包 35.1 MB（[operations.md:115](../guides/operations.md)） | ❌ 冲突（Node + dsh 闭包） | ✅ **不冲突**（Memoria 包不变） |

### 4.2 **对外可调用面（D2 的现成地基）**

| 面 | 现状 | 证据 |
|---|---|---|
| **CLI（已存在，且已具备机器可读输出）** | `memoria validate <kb> [--json]`、`memoria repair-paths <kb> [--apply] [--json]`、`memoria diagnose-images <kb> [--json]`；**默认 dry-run，写操作必须显式 `--apply`**；stdout 强制 UTF-8（Windows 管道安全）；退出码 0/1 表结果 | `src/memoria/cli/main.py:111-125`、`:120`、`:104-109`、`:74-76,96-100` |
| 样例库文档已在用 CLI | showcase 的 README 直接给出 `python -m memoria.cli.main validate docs/example/showcase` | `docs/example/showcase/README.md` |
| **壳层 API 面（面向 GUI，未声明对外稳定性）** | `UIAPI` 共 93 个方法；Agent 相关 4 个：`get_agent_prompt:1055`、`get_kb_agent_prompt:1075`、`install_kb_agent:1095`、`get_reference_doc:1112`。**注意：产品不存在 HTTP `/rpc`**（**2026-09-15 更正**：此前误把测试 harness 自建的端点当成产品能力）—— 只有两条壳层通道：pywebview `js_api`（`app/shell/pywebview.py:471-484`）与 pyqt6 QWebChannel 单槽 `UIAPIRpc.invoke(method, args_json)`（`presentation/api/api_rpc.py:44-67`）；`static_server.py` 仅 `GET /`(:114) 与 `GET /<path:path>`(:130) | `presentation/api/ui.py` |
| 作业执行器 | `MaintenanceExecutor`：线程池（`max_workers=2`）、同 kind+key 顶替合并、状态 `queued/running/done/error/superseded`；RPC `validate_kb_async / job_status / jobs_snapshot` | `services/executor.py:31-163`；`ui.py:392-412` |
| 检索栈 | lexical 倒排（jieba + 拼音）、embedding（离线 HF MiniLM-l12）、cross-encoder rerank、RRF 融合 | `services/{lexical_index,embedding_provider,rerank_provider,retrieval_fusion}.py` |
| LLM 空槽 | `model_router` 的 `llm_tag: None` / `llm_summary: None` —— **槽位已留、实现为空** | `services/model_router.py:11-20` |
| KB 侧契约 | `.memoria/agent/` 工具包（幂等、原子写、不覆盖 `review/**`） | `services/kb_agent.py:26-37,84-145`；[kb-agent.md:34-52](./kb-agent.md) |
| 事件流 | `artifacts/agent/events.jsonl` **尚不存在**（契约预留） | 全仓未找到 |
| 网络出口 | 全仓**无任何 LLM/外部 API 客户端** | grep `requests|httpx|openai|urllib.request|api.deepseek` 仅 3 处无关命中 |

> **结论**：D2 需要的"能被机器调 + JSON 输出 + 预览/应用分离"三件事，**CLI 已经做到**。缺的是**对外契约的稳定性声明**与**能力面补全**（检索 / 图 / 读 KP / 提议）。

---

## 5. 冲突面分析（按方向）

| # | 冲突 | 方向 | 严重度 | 可解性 |
|---|---|---|---|---|
| X1 | 离线优先 vs 远端 LLM | D1 | 高 | ✅ 只做可选扩展层、默认关闭、指向本地 OpenAI 兼容端点 |
| X2 | 禁止 silent 写入 vs 外部自主写文件 | D1 **与 D2** | 高 | ✅ 硬边界：**外部 agent 只写 `proposals/**` 或只调"预览→应用"面**；应用由 Memoria 服务层完成 |
| X3 | 单一事实源 vs 外部会话日志 | D1 **与 D2** | 中 | ✅ 明确外部日志 = 过程日志（可删），非知识事实源；如需登记进 [AGENTS.md §1](../../AGENTS.md) |
| X4 | 免安装打包 vs Node 依赖 | D1 | 中 | ⚠️ 只能做成**独立可选组件**，不进 `_REQUIRED_RELEASE_RESOURCES`（体积【未证实】） |
| X5 | 版本稳定性 vs preview | D1 **与 D2** | 中 | ✅ pin 版本 + 只依赖稳定子集 + 适配层隔离 |
| X6 | 安全面（未审计 + 历史 CVE） | D1 **与 D2** | 中高 | ✅ pin ≥ `0.1.2-alpha.2`；禁用 `sdk-minimal`（pin `danger-full-access` + 无审批）；不启用 `dsh web`；只允许 `read-only`/受控 preset |
| X7 | 数据外发与隐私 | D1 **与 D2** | 中 | ✅ 按库显式开关 + 外发前可见 + 优先本地端点（[dicussion.md:1035](./dicussion.md)「不默认上传」） |
| X8 | i18n / 门禁 | D1 | 低 | ✅ 常规流程（`scan_ui_strings.py` rows=0 + `i18n_selftest.js`） |
| X9 | **跨进程并发写** | **D2 新增** | 中高 | ⚠️ GUI 会话与外部 agent 可能同时写同一文件；现有 `executor` 只有同 `kind+key` 合并、**不跨进程** → 需要文件级互斥或"单写者"约定（§7.3、R11） |
| X10 | **沙箱约束与知识库位置** | **D2 新增** | 中 | ⚠️ 若插件经子进程调 `python -m memoria`，子进程继承受限令牌 → **写入被限制在 dsh 的 workspace**，知识库必须位于 workspace 内（或只给只读能力）；需与对方确认（§7.5、R13） |

**关键判断**：X2/X3 靠"**不给写权限，只让它产提议**"即可化解；X9/X10 是 D2 特有的**工程细节**，必须与对方项目一起定；X4–X6 是 D1 的代价。

---

## 6. 契合面：哪些东西值得（或不该）照搬

| `dsh` 机制 | Memoria 的对应物 | 判断 |
|---|---|---|
| **能力接缝三角色**（Definition / Provider / Consumer） | [AGENTS.md §6](../../AGENTS.md) 四角色隔离矩阵 + 单一改动点扩展 | 💡 **值得借鉴为描述语言**：把"检索通道/渲染器/图谱布局/模型适配器 + **对外工具面**"表达成 seam，扩展规则更清晰（**文档层面对齐**） |
| **只追加 typed 事件日志**（"Model-visible means logged"） | `artifacts/agent/events.jsonl` + 哈希链（`prev`/`digest`，[AGENTS.md:65-95](../../AGENTS.md)）——**当前未落盘** | 💡 **同构度极高**：可借用"日志即唯一事实源 + 从事件派生视图"，且 **D2 的跨进程审计正需要它** |
| **fail-closed 审批**（无应答 = `unavailable` = 拒绝） | "所有结果提议 → 用户确认" | ✅ **方向一致**：可把"无应答即拒绝、绝不静默放行"写进确认流程规范（D2 的提议接口直接沿用） |
| **`waterfall` 工具管线** | 无对应物 | ⏸ 暂不需要：Memoria 的维护动作是**枚举式作业**（[maintenance-jobs.md](./maintenance-jobs.md) 登记表），不是开放式工具调用 |
| **沙箱 / 隔离执行** | 无对应物 | ⏸ 只在"外部 agent 写提议"场景需要；**D2 下沙箱是对方的责任**（本节 X9/X10） |
| **Agent loop / 子 Agent 编排** | 无对应物 | ❌ **不建议自建**：Memoria 的能力面是确定性流水线；[AGENTS.md:33](../../AGENTS.md) RISC 已明确"业务关注点一律作为 builder 的作业，**永不新增独立 Agent**" |
| **`SessionEvent` 持久化** | 无 | ⏸ 若 D1 采用则顺带获得；不单独引入 |

---

## 7. D2 详解：Memoria 作为 `dsh` 的能力提供方（正在发生）

> 前提：**契约定义权在双方**，但 Memoria 必须定义"**哪些能力可被外部调用、以什么稳定性承诺、写权限边界在哪**"。

### 7.1 传输面选择（三选一或组合）

| 方案 | 形态 | 优点 | 风险/限制 |
|---|---|---|---|
| **T1 CLI 子进程（推荐先行）** | `memoria <cmd> <kb> --json` | **已存在**；无端口；无 GUI 依赖；沙箱友好（在 workspace 内起子进程）；退出码可判定 | 每次冷启动 Python 解释器成本；能力面目前仅 3 条命令（validate / repair-paths / diagnose-images），需补检索/图/读 KP/提议 |
| **T2 loopback HTTP `/rpc`（⚠️ 现状不存在，需新增）** | 需先在 `static_server` 新增 POST `/rpc` 路由转发到 `UIAPI`，并让 `bridge.js` 在无 pywebview/Qt 时回退到 HTTP 桥 | 宿主零配合；能力面最全 | **产品当前没有这个端点**（旧文档误记为已有）；需要 GUI 应用正在运行；**端口 + 鉴权**须自建；与 UI 会话共享状态 |
| **T3 常驻 headless 服务** | 新增无 GUI 的 RPC 服务进程 | 最干净：可鉴权、可版本化、可并发控制 | **需要新代码**（当前无此入口）；本次不实施 |

**建议**：**T1 作为基础契约**（先只读 + 预览/应用语义，补齐能力面），T2 作为"应用在跑时"的可选快捷通道且**必须加本机令牌**，T3 留待契约稳定后再正式化。

### 7.2 建议的对外能力面（按风险从低到高）

| 层 | 能力 | 对应既有实现 | 风险 |
|---|---|---|---|
| **L0 只读** | 完整性校验 `validate`；图片引用诊断；路径漂移检测（预览） | CLI 3 条命令；`validate_kb` / `get_graph_audit` / `diagnose_image_refs` | 极低 |
| **L0 只读（待补）** | 检索（query → KP + 文件 + 行号）；读 KP / 读文档；图谱节点与边；`pending` 列表 | `search` / `lexical_index` + `embedding_provider` + `retrieval_fusion`；`load_document`；`get_graph_data`；`get_kb_pending` | 低（需新增 CLI/JSON 入口） |
| **L1 提议** | 生成"待确认变更"（KP 新增/修改、链接、别名、标签）；**不落盘** | `confirm_kp_range` / `update_kp` / `suggest_*` 系列（皆为 GUI 面，需下沉为可编程面） | 中（要有提议格式与存储） |
| **L2 应用** | 应用提议（原子写 + 索引失效 + manifest/sidecar 同步） | 服务层 A7 原子写、G5.4 写后失效、A1/A2 同步、A3 pending 路径同步 | 高（**须用户确认**，默认关闭） |

### 7.3 Memoria 侧必须守住的边界（红线具体化）

1. **不直写**：外部 agent **不得**写 `*.md`、`.memoria/sidecars/**`、`manifest.yaml`、`pending.json`；只能走 `--json` 调用或写 `<kb>/.memoria/agent/proposals/**`（若采用目录提议）。
2. **写必须经服务层**：所有落盘经既有链路 —— 原子写（A7）→ 索引写后失效（G5.4）→ manifest/sidecar 同步（A1/A2）→ pending 路径同步（A3）。**禁止**任何"直接 replace 文件"的旁路。
3. **默认只读**：对外能力默认 L0；L1/L2 需 **per-KB 显式开关**（并记录于该库 `.memoria/` 或 UI 设置）。
4. **无 UI 依赖**：外部调用链不得弹窗、不得依赖 DOM/会话状态（CLI 路径天然满足）。
5. **可回溯**：所有输出带**文件 + 行号**锚点；提议变更须可 diff、可拒绝。
6. **单写者/互斥**：同一知识库的并发写要有互斥（文件锁或"唯一写者"约定）；否则 X9 会产出 sidecar/md 漂移（用 `validate_kb` errors=0 作为验收）。
7. **版本协商**：对外命令/JSON schema 需要版本标识与弃用策略；建议新建契约文档（§7.4）。

### 7.4 需要新建的"对外契约"文档（建议，待批准）

- 归属：按 [docs-management.md](../conventions/docs-management.md) 的决策表，"**双方都要遵守的约定**" → `docs/conventions/`；建议 `docs/conventions/external-agent-api.md`（若先作为提案，可暂并入本文 §7，方案冻结后再另立）。
- 必须写清的六件事：① 传输面（T1/T2/T3 取舍）；② 命令与 JSON schema（含字段稳定性等级）；③ 退出码与错误码；④ 写权限边界与提议格式；⑤ 版本协商与弃用策略；⑥ 并发与锁约定。

### 7.5 dsh 沙箱语义对 D2 的含义（必须与对方确认）

- Windows ACL runner 是 **`partial`**；**网络与进程可见性不在沙箱保证范围**（官方明说"reads and network access are not confined"）。
- 若插件经**子进程**调 `python -m memoria …`：子进程继承受限令牌 → **写入被限制在 dsh 的 workspace + 会话私有临时目录** ⇒ **知识库必须位于 dsh 的 workspace 内**，否则"应用提议"会因写失败而 fail-closed（这反而是安全的好事，但需在契约里说清）。
- 若插件经 **loopback HTTP** 调在跑的 GUI：网络不在沙箱限制内 ⇒ **必须自带令牌**，否则形成新的"未鉴权本机控制面"（正是 CVE-2026-82533 的形态）。
- 结论：**优先子进程（T1）**，且把"知识库 = workspace"作为约定写进契约。

### 7.6 需要对方项目提供的信息（否则契约只能靠猜）

| 项 | 为什么需要 |
|---|---|
| 项目坐标（仓库 / 包名 / 联系人） | 本机未找到该工程，无法读取其真实契约 |
| 插件形态：tool / service seam / fs provider？ | 决定我们暴露的是"工具"还是"服务"；若是 **fs provider**，则意味着对方要**直接读写文件** → **触发红线 X2，必须否决或改为只读** |
| 是否接受"提议 → 用户确认 → 应用"三段式 | 决定 L1/L2 是否存在 |
| 目标 dsh 版本与 preset | 决定沙箱/审批与我们的权限边界 |
| 知识库是否位于其 workspace | 决定 X10 是否成立 |
| 发布节奏与兼容承诺 | 决定我们的契约版本策略 |

---

## 8. 方案空间与取舍（D1 方向 + 借鉴方向）

| 方案 | 内容 | 侵入 | 离线红线 | 体积 | 满足 `todo.md:152` | 主要风险 |
|---|---|---|---|---|---|---|
| **A. 研发流程助手** | 用 `dsh web` / headless 作为**开发期**助手（读仓库、跑验证、写草稿）；不进产品、不进仓库契约 | 无 | 不涉及 | 0 | ❌ | preview 破坏性变更；需明确不让它碰 `src/**`（与 [AGENTS.md](../../AGENTS.md) SOLO 契约重叠） |
| **B. 产品内可选"运行时"** | 经 **Python SDK** 接入，作业化挂 `executor`；只写 `proposals/**` | 高 | ⚠️ 需专门设计 | ⚠️ 待实测 | ✅ 部分 | X1/X4/X6；**D2 已能达成同类目标，故 B 的优先级下降** |
| **C. 仅 LLM 能力层** | 在 `model_router` 的 `llm_tag`/`llm_summary` 空槽实现 OpenAI 兼容客户端；问答 = 既有检索召回 → LLM 归纳；**只读** | 中 | ✅ 可完全离线 | 0 | ✅ 核心诉求 | 成本/隐私（可用本地端点规避）；依赖召回质量 |
| **D. 只借鉴架构范式** | seam 三角色、只追加事件流、fail-closed 审批写进既有契约（纯文档） | 无 | 不涉及 | 0 | ❌ | 抽象过度（RISC 反对） |

> 与 D2 的关系：**D2 让方案 B 变得不必要**（同样的"外部智能体"，由外部项目承载），D2 反而**放大方案 D 的价值**（契约与事件流是 D2 的基础设施）。

---

## 9. 推荐路线与分阶段规划

> 推荐：**D2 优先做稳 → D1 降级为 C/A → D 并行**。
> 理由：D2 已有真实需求方与现成地基（CLI + `--json` + 预览/应用语义），且**不触碰任何红线**；D1 的 B 方案要付出 Node 依赖与安全维护成本，收益与 D2 重叠。

### 阶段 0：判定与冻结（本次交付）

- 产物：本文件；登记见 §12。
- 出口条件：§13 的 Q1–Q9 答复完毕；与 D2 对方项目完成 §7.6 的信息对齐。

### 阶段 1：**对外契约骨架 + 只读能力面**（D2，最低风险）

| 项 | 内容 |
|---|---|
| 契约 | 起草 `docs/conventions/external-agent-api.md`（§7.4 六件事）；先定 T1（CLI + JSON）版本号与稳定性等级 |
| 能力 | 把 L0 补全：`search`（→ KP/文件/行号）、`graph`、`read`（KP/文档）、`pending`；统一 `--json` 输出与退出码 |
| 边界 | 全部只读；不引入写能力 |
| 验收（参考 [AGENTS.md §2.2](../../AGENTS.md) 阶梯） | L0 `py_compile`；每个子命令 `--json` 可解析；**断网可用**；输出含文件+行号锚点；对同一库无任何写入（写前后 `validate_kb` errors=0 且 mtime 不变） |

### 阶段 2：**提议 → 确认 → 应用**（D2，写能力）

| 项 | 内容 |
|---|---|
| 提议面 | L1：生成待确认变更（文件 + diff + 依据），存 `<kb>/.memoria/agent/proposals/**` |
| 应用面 | L2：由 **Memoria 服务层**应用（原子写 → 索引失效 → manifest/sidecar 同步 → pending 同步），**逐条或批量用户确认**；无应答 = 不应用 |
| 开关 | per-KB 显式开关；默认关闭 |
| 并发 | 文件级互斥 / 单写者约定（X9） |
| 验收 | 越权写测试（构造"直写 md"用例必须被拒）；提议→应用全链路可追溯；`.memoria` 与 md 无漂移；外部 agent 侧不残留写入痕迹 |

### 阶段 3：能力面标准化与可选常驻服务

- T3（headless 服务，带鉴权 + 版本协商）；把 `.memoria/agent/` 契约 + ACP 组合，使任意 ACP 客户端（Zed 等）可驱动同一知识库智能体。
- 与 V06 的关系：与"Trae 智能体"**并存为多载体**（同一份 `.memoria/agent/` 契约），不做替换。

### 并行工作项（不阻塞主线）

| 项 | 内容 | 类别 |
|---|---|---|
| P1 | 对齐描述语言：引入 seam 三角色描述"检索通道/渲染器/图谱布局/模型适配器 + 对外工具面" | D（文档） |
| P2 | 落盘 `artifacts/agent/events.jsonl`（"只追加 + 派生视图"）——**D2 的跨进程审计正需要它** | D（文档先行，实施另立项） |
| P3 | 把"无应答即拒绝、绝不静默放行"写进提议/确认流程规范 | D（文档） |
| P4 | D1 的 C 方案（LLM 能力层）按需推进；A 方案仅做一次性价值实验（产物不入库） | D1 |

---

## 10. 风险登记表

| ID | 风险 | 方向 | 影响 | 缓解 | 停手线 |
|---|---|---|---|---|---|
| R1 | 离线承诺被破坏（首启联网装 profile） | D1 | 高 | 完整包不内置；未安装时功能静默隐藏而非报错 | 无法做到"未安装时应用全功能不受影响"→ 不做方案 B |
| R2 | 越权写入 | D1/D2 | 高 | 只给 `proposals/**` 或只给只读；服务层应用；不给 `danger-full-access`；禁用 `sdk-minimal` | 出现任何"外部直写 md/sidecar"路径 → 立即回滚 |
| R3 | 数据外发 | D1/D2 | 中高 | per-KB 显式开关 + 外发前可见 + 优先本地端点 | Q4 未答复前不实施联网能力 |
| R4 | API 成本 | D1/D2 | 中 | 默认关闭；显式触发；提示 token/费用 | — |
| R5 | preview 破坏性变更 | D1/D2 | 中 | pin 版本；只依赖稳定子集；适配层隔离 | 跨版本回归失败 → 暂缓升级 |
| R6 | 安全漏洞（含 CVE 类） | D1/D2 | 中高 | pin ≥ `0.1.2-alpha.2`；不开放 3080；最小权限 preset；只读为默认 | 新 CVE 未修复 → 禁用该组件 |
| R7 | 体积膨胀 | D1 | 中 | 不进必需资源；独立组件；实测后再定形态 | 单组件 >100 MB 且无法按需下载 → 退化为仅外部客户端 |
| R8 | 并行事实源 | D1/D2 | 中 | 外部日志 = 过程日志（可删）；如需登记进 [AGENTS.md §1](../../AGENTS.md) | 出现双向同步需求 → 重新评审 |
| R9 | 多载体漂移（Trae / ACP / dsh 插件） | D2 | 低 | 同一份 `.memoria/agent/` 契约与 `kb-spec`，只换驱动方 | — |
| R10 | 抽象过度（照搬插件体系） | D | 低 | 只借鉴描述语言，不自建插件内核 | — |
| **R11** | **跨进程并发写**（GUI 与外部 agent 同时写库） | **D2** | 中高 | 文件级互斥 / 单写者约定；`validate_kb` errors=0 作为验收 | 出现 md/sidecar 漂移 → 停止写能力 |
| **R12** | **对外契约漂移**（对方项目按未发布版本对接） | **D2** | 中 | 契约文档 + 版本标识 + 弃用策略；契约变更走 [docs-management.md](../conventions/docs-management.md) 登记 | 对方要求"无版本直接对接" → 拒绝 |
| **R13** | **沙箱导致写入被拒**（知识库不在 dsh workspace 内） | **D2** | 中 | 契约写明"知识库 = workspace"；或只提供只读能力 | 无法约定 → 仅 L0 |

---

## 11. 对既有已拍板决策的影响

| 既有决策 | 出处 | D2 下 | D1 下 | 待裁决 |
|---|---|---|---|---|
| **载体 = Trae 智能体** | [kb-agent.md:25](./kb-agent.md) | 变为**多载体**（Trae / dsh 插件 / ACP 客户端并存，同一契约） | 同左 | ① 仅 Trae ② **并存（推荐）** ③ 替换 |
| **非目标：不把 LLM 内嵌进 Memoria 应用运行时** | [kb-agent.md:17](./kb-agent.md) | ✅ **完全一致**（能力在 Memoria、智能体在外面） | ⚠️ 冲突（阶段 1/2 都触碰） | D1 若不放弃 → 需修订为"不内嵌**模型权重**，允许可选外部进程/端点" |
| **LLM 生成 = V1 Won't，不进查询热路径** | [designV0.md:987](./designV0.md) | ✅ 不冲突 | ⚠️ 需认定"用户显式触发不属热路径" | ① 认定不冲突（推荐）② 视作冲突延后 |
| **禁止 silent 写入（唯一例外 = KB Agent 补写）** | [designV0.md:254,911](./designV0.md) / [kb-agent.md:286](./kb-agent.md) | ⚠️ 需明确"提议 ≠ 写入"；若采用 `proposals/**` 目录则需登记为第 2 个例外（但**它不是事实源**，只是待确认队列） | 同左 | ① 提议不算写入（推荐）② 登记为例外 |

> ⚠️ 这些都是**用户已拍板**的决策。按 [collaboration.md §0](../guides/collaboration.md) 规则 6，未获答复前**不得默认继续**。

---

## 12. 登记与文档维护

### 12.1 本次已做的登记（文档层）

| 动作 | 目标 |
|---|---|
| 新建本文件 | `docs/design/deepseek-harness-integration.md` |
| 追加修订记录 | [docs-management.md §4.2](../conventions/docs-management.md) 一行 |

### 12.2 不做的事（本次边界）

- **不改任何代码**（`src/**` / `scripts/**` / `packaging/**`）。
- **不改** [AGENTS.md](../../AGENTS.md)、[kb-agent.md](./kb-agent.md)、[designV0.md](./designV0.md)、[todo.md](../todo.md) —— 属"裁决后"的登记动作。

### 12.3 建议的门禁登记（待批准后才写入 [todo.md §12](../todo.md)）

| 建议 ID | 内容 | 方向 | 状态 |
|---|---|---|---|
| H1 | 对外契约文档（`external-agent-api.md`：传输面 / schema / 边界 / 版本策略） | D2 | 💡 待批准 |
| H2 | 只读能力面补全（search / graph / read / pending + 统一 `--json`） | D2 | 💡 待批准 |
| H3 | 提议 → 确认 → 应用（`proposals/**` + 服务层应用 + per-KB 开关 + 互斥） | D2 | 💡 待批准（依赖 Q8） |
| H4 | 事件流落盘（`events.jsonl`，契约已存在） | D | 💡 待批准 |
| H5 | LLM 能力层（OpenAI 兼容端点 + 只读问答，`model_router` 空槽） | D1-C | 💡 待批准 |
| H6 | dsh 作为研发期助手（一次性价值实验，产物不入库） | D1-A | 💡 待批准 |

### 12.4 附带发现（既有漂移，请另行处置）

- **文档引用悬空**：[AGENTS.md](../../AGENTS.md) 的单一事实源表与 [docs/README.md:39](../README.md) 均引用 `docs/to-dolist.md`，磁盘上实际是 `docs/todo.md`（`docs/to-dolist.md` 不存在）。建议统一命名——**本次未擅自修改**（涉及人维护的契约文件）。

---

## 13. 待评审问题（阻塞项，须答复后才继续）

| ID | 问题 | 选项 | 影响 |
|---|---|---|---|
| **Q1** | 两个方向的优先级？ | ① **D2 优先、D1 降级（推荐）** ② D1 优先 ③ 只做 D2 ④ 只做 D1 | 决定后续全部工作 |
| **Q2** | §11 的四条已拍板决策怎么裁决（尤其"载体=Trae 智能体"与"非目标：不内嵌 LLM"） | ① 维持原判 ② **多载体并存 + "不内嵌模型权重，允许可选外部进程/端点"（推荐）** ③ 全面放开 | 决定 D1 是否合法 |
| **Q3** | D1 的 B 方案是否还做（D2 已能达成同类目标）？ | ① **暂缓（推荐）** ② 继续 | 决定是否背 Node 依赖 |
| **Q4** | 模型来源优先级：本地 OpenAI 兼容端点 vs DeepSeek 官方 API | ① **本地优先、远端可选（推荐）** ② 远端优先 ③ 双轨 | 决定隐私与成本 |
| **Q5** | 是否允许外部 agent 拥有"提议"权限（不直写）？ | ① **允许，限定 `proposals/**` 或提议 API（推荐）** ② 只读 | 决定写能力是否存在 |
| **Q6** | 是否现在登记 §12.3 的 H1–H6 到 [todo.md §12](../todo.md)？ | ① 登记 ② 等 Q1 后 | 决定台账 |
| **Q7** | D2 传输面选哪个？ | ① **T1 CLI（推荐先行）** ② T2 loopback HTTP（**需先新增端点 + 鉴权**） ③ T3 常驻服务 ④ T1+T2 | 决定实现形态 |
| **Q8** | D2 写能力的开关粒度与确认方式？ | ① **per-KB 开关 + 逐条确认（推荐）** ② 全库开关 + 批量 ③ 不给写 | 决定边界与验收 |
| **Q9** | 是否现在起草 `docs/conventions/external-agent-api.md`？ | ① **是（推荐，契约先行）** ② 等对方项目信息齐 | 决定 D2 能否并行开工 |

### 需要向 D2 对方项目索要的信息（§7.6 摘要）

项目坐标 / 插件形态（tool 还是 **fs provider**）/ 是否接受"提议→确认→应用" / 目标 dsh 版本与 preset / 知识库是否在其 workspace / 发布节奏与兼容承诺。

> ⚠️ 若对方采取 **fs provider** 形态（直接读写文件），**直接触发红线 X2**，需立即否决或改为只读——这是本方案最高优先级的对齐项。

---

## 14. 参考来源

**Memoria 侧**（仓库内文件，正文已给行号）：`docs/design/{kb-agent,dicussion,designV0}.md`、`docs/reference/architecture.md`、`docs/todo.md`、`docs/guides/operations.md`、`docs/example/showcase/README.md`、`AGENTS.md`、`src/memoria/cli/main.py`、`src/memoria/services/**`、`src/memoria/presentation/api/ui.py`、`packaging/build.py`、`pyproject.toml`。

**`dsh` 侧**（官方优先）：

- 官方文档站：<https://deepseek-harness.github.io/deepseek-harness/en/guide/quickstart>；架构 <https://deepseek-harness.github.io/deepseek-harness/en/reference/>；能力接缝 <https://deepseek-harness.github.io/deepseek-harness/en/reference/capability-seams>；沙箱 <https://deepseek-harness.github.io/deepseek-harness/en/reference/subsystems/sandbox>；审批 <https://deepseek-harness.github.io/deepseek-harness/en/reference/subsystems/approval>；会话 <https://deepseek-harness.github.io/deepseek-harness/en/reference/subsystems/session>；压缩 <https://deepseek-harness.github.io/deepseek-harness/en/reference/subsystems/compaction>；事件 <https://deepseek-harness.github.io/deepseek-harness/en/develop/framework/events>；provider <https://deepseek-harness.github.io/deepseek-harness/en/guide/providers>；Python SDK <https://deepseek-harness.github.io/deepseek-harness/en/guide/python-sdk>
- 官方仓库文件（raw）：`README.md`、`SAFETY.md`、`docs/development.md`、`apps/cli/reference/README.md`、`python/sdk/README.md`、`packages/bundle/{base,headless,acp-app}/README.md`、`packages/e2b/e2b/README.md`、`packages/llm/llm-deepseek/README.md`
- registry：<https://www.npmjs.com/package/@deepseek-ai/dsh>、<https://registry.npmjs.org/@deepseek-ai/dsh>、<https://pypi.org/project/deepseek-harness-sdk/>、<https://www.npmjs.com/package/@deepseek-ai/dsh-sandbox-windows-acl>
- 安全事件：【第三方】<https://thehackernews.com/2026/09/deepseek-harness-flaw-let-ai-agents.html>、<https://www.ox.security/blog/cve-2026-82533-deepseek-harness-ai-agent-sandbox-escape/>
- 其它【第三方，仅参考】：<https://deepseekagent.io/zh/guides/deepseek-harness>、<https://deepseekharness.dev/zh/github>、<https://gist.github.com/robbin/b0b3cc024d88235b1ebeecce5499b5e8>、<https://npm.io/package/dsh-acp-server>

---

## 15. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-14 | 初版（草稿待评审）：dsh 事实基线（含未证实清单）、Memoria 红线与挂载点、8 条冲突面、方案 A–D、阶段 0–3 规划与验收、10 条风险、§9 裁决项、Q1–Q6、附带发现（`to-dolist.md` 引用悬空） |
| 2026-09-14 | **v2**：确认 **D2（Memoria → dsh 插件）正在由另一项目推进**后重构为双向版本。新增 §1 方向坐标、§7 D2 详解（传输面 T1/T2/T3、分级能力面 L0–L2、边界七条、契约文档落点、沙箱语义、需对方提供的信息）；冲突面补 X9（跨进程并发写）/X10（沙箱与知识库位置）；风险补 R11–R13；§11 拆成"D2 下 / D1 下"；问题扩到 Q7–Q9；门禁建议扩到 H1–H6。**新证据**：Memoria CLI 已自带 `--json` 与 `--apply` 预览语义（`src/memoria/cli/main.py:111-125,120`），对外契约地基已存在 |
