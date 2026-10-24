# Memoria agent 能力架构立场书（§0 定位 + §1 外部来源 + §2 五问 + §3–§6）

> **任务**：task-115（已解锁：`task-114` 完成，A1 被证伪）｜**协议**：`PROTOCOL.md` @ `48ca704e`（FROZEN）
> **本文范围**：**§0 + §1 + §2 + §3 + §4 + §5 + §6 全部已写**；
> §2 五问已按 N1 结论（A1 不成立，`ev:bench:n1-a1-token-hypothesis#§4`）重写，Q2 的理由链已更换（token 理由作废，见 §-1）。
> **写入时间**：2026-10-25T00:5x+08:00
> **更正记录（对抗评审后，原地改）**：
> `2026-10-25 更正：gate 主张撤回（R-R1）；三字段或补消费者或移出（R-R2）；MCP M-1 删除、X-1 改造（R-R4）；写侧补「按 heading 替换一节」缺口（R-R3）；L1 粒度标「有条件成立」+ `AS-SECTION-RANGE` 指派 arch-contract（R-R5）。`
> **本轮的读集（E1/F2' 要求可复核）**：
> `PROTOCOL.md`、`freeze-v2.json`、`PHASE1-BASELINE.json`、`PINNED-PROPOSALS.json`、task-114/task-115 描述、
> 我自己 Phase 1/3 的两份产物、`docs/design/agent-plugin-design.md` §1、`src/memoria/services/agent/**` 的头部与 grep 结果。
> **未读**：其他三方的 position 文件（本轮尚不存在）、`ruling/rulings.jsonl` 正文（我只从 PROTOCOL §11 的摘要知道裁决编号与采纳情况）。
>
> **证据身份约定**（E1 扩展，先声明再用）：
> `ev:file:<repo-相对路径>#L<n>` 仓库文件；`ev:spec:mcp/2026-07-28#<anchor>` 外部规范；`ev:doc:url:<URL>#<anchor>` 外部文档；
> `ev:paper:arXiv:2508.02694#§<n>` 外部论文；`ev:bench:*` 留待 N1；**`ev:lead-transcript`** 表示"Lead 转述的实测事实，本轮未独立复核"（显式降级，不冒充 my own evidence）。

---

# §0 定位

## §0.1 Memoria 是什么（逐条带证据，不靠形容词）

**一句话**：Memoria 是一个**本地优先、单进程、以 Markdown 文件为唯一事实源**的知识库桌面应用；它的 agent 能力**已经内置**，只是**只对内置 agent 可见**。

| 维度 | 事实 | 证据 |
|---|---|---|
| 运行载体 | Python + pywebview（Windows 上即 WebView2）桌面单进程 | `ev:file:pyproject.toml#L12`（`"pywebview>=5.0"`） |
| 事实源 | `<kb>/**/*.md` + `.memoria/{manifest.yaml, sidecars/**, pending.json}`；`.memoria/cache/**` 明确**不是**事实源 | `ev:file:AGENTS.md#L67-L69`（§1 单一事实源表） |
| 规模 | 典型 38 md / 412 KB；大库 255 md / 2530 KB；单文件约 11 KB | `ev:lead-transcript` |
| agent 代码量 | `services/agent/` **97 文件**；顶层 30 个模块 + `llm/` `session/` `tools/` 三个子包 | 实测：`(Get-ChildItem src\memoria\services\agent -Recurse -File).Count = 97` |
| 工具面 | `tools/kb.py` **304,374 B**（单文件）+ `tools/registry.py` 12,360 B | 实测：文件大小 |
| 会话事实源 | `<kb>/.memoria/agent/sessions/<session-id>.jsonl` | `ev:file:src/memoria/services/agent/ask.py#L11` |
| 写侧机制（已有，不是待建） | 声明式 plan + 校验 + dry-run 零落盘｜pre-image 备份 + 原子写 + 写后哈希 + 会话撤销栈｜审批桥 | `ev:file:src/memoria/services/agent/plan.py#L6-L14`、`ev:file:src/memoria/services/agent/backup.py#L6-L10`、`ev:file:src/memoria/services/agent/tools/kb.py#L4203-L4215` |
| 扩展点（已有，不是待建） | **声明式能力插件契约 v1（6 字段）**：插件目录**不含可执行代码**，只含声明 JSON + 只读资源；`tool_id` 必须取自**核心原语目录** | `ev:file:src/memoria/services/agent/plugins.py#L4-L14`、`ev:file:docs/design/agent-plugin-design.md#L12-L24` |
| 能力闸（已有） | `permissions.write` 非空 ⇒ `approval` **不得**为 `auto`（硬校验） | `ev:file:docs/design/agent-plugin-design.md#L24-L28` |
| 上游对照纪律（已有） | 每个契约字段必须"有真实消费者"或"照搬上游成熟设计并点名 `dsh-src/` 的 `file:line`"；两条都不满足 ⇒ 移出 v1 | `ev:file:docs/design/agent-plugin-design.md#L15` |
| 本地 DSH 上游副本 | `dsh-src/`（`packages/` 下 **52** 个包目录） | 实测：`(Get-ChildItem dsh-src\packages -Directory).Count = 52` |

**这张表直接改变本轮辩论的起点**：Memoria 不是"没有 agent 能力的应用，要从 DSH 搬一整套过来"；
它是"**已经有一套自建 + 移植混合的 agent 层、且移植纪律相当严格（pin + 逐条 file:line 对照 + 偏差登记）**"的应用。
所以"全量移植"这个提法必须被追问：**缺的到底是哪一类东西**（§0.5 给三分类判决）。

## §0.2 Memoria 不是什么（四条否定，各给证据，防止自说自话）

1. **不是 MCP 宿主，也不是 MCP 客户端/服务端。**
   实测：对 `src/**` 全量 grep `jsonrpc|json-rpc|tools/list|mcpServers|modelcontextprotocol|Mcp-Session`，
   **first-party 代码 0 命中**；唯一命中在 `src/memoria/ui/static/app/vendor/mermaid.min.js`（第三方打包件）。
   另：对 `src/**` grep 字面 `mcp` 有 1 命中，是 `ev:file:src/memoria/ui/static/app/js/code-highlight.js#L27`
   的 `memcpy` 词表 **子串误报**（`me`+`mcp`+`y`）—— 我把它单列，是因为"零引用"这种断言必须区分"语义为零"与"字面为零"。
   ⇒ 结论：**语义上 0 处 MCP 协议代码**（与 Lead 转述一致，但我给的是可复核的 grep 口径与误报说明）。
2. **不是多 agent / 插件运行时宿主。**
   `plugins.py` 自述："能力插件的**声明面**：发现、校验、启停。**本模块不含任何执行体**"，
   且"插件目录内不含可执行代码（无 `.py`/`.js`/脚本），只含声明 JSON + 只读资源"。
   ⇒ Memoria 的"插件"是**声明式能力闸**，DSH 的"plugin"是 **Cordis 服务模型**。**同名不同物**（这是 §0.5 宿主运行时判决的事实基础）。
   证据：`ev:file:src/memoria/services/agent/plugins.py#L4-L14`。
3. **不是云服务 / 多租户系统。**
   全部数据在本地磁盘（`<kb>/`），无账号体系与服务端存储；agent 的会话与备份也落在 `<kb>/.memoria/agent/**`。
   证据：`ev:file:src/memoria/services/agent/backup.py#L8-L10`（"本模块自身只写 `<kb>/.memoria/agent/backups/**`"）。
4. **不是通用编码/终端 agent。**
   虽有 `shell_exec.py`（17 KB），但其**边界写死在代码里**：`workdir` 经 `realpath` 前缀校验必须落在知识库根（含 `scratch/`）内，
   库外 ⇒ 拒绝（`EXEC_CWD_OUTSIDE`）；且**不引内核沙箱**（Z.11 Q4 搁置）、不引新依赖。
   证据：`ev:file:src/memoria/services/agent/shell_exec.py#L9-L18`。
   ⇒ 它的执行面是"库内维护工具"，不是"通用 shell"。这一条对 §3（写侧安全不可被 MCP 化绕过）是硬约束。

## §0.3 agent 在 Memoria 里扮演什么角色（三身份，按写入权限排序）

| 身份 | 能做什么 | 不能做什么 | 证据 |
|---|---|---|---|
| **读者** | 读库、检索、回答（M1 竖切：应用内对话 + 读库问答） | 改事实源 | `ev:file:src/memoria/services/agent/ask.py#L6-L14` |
| **提案者** | 产出**声明式 plan**；`validate` + **dry-run 预览**行级 diff；**一个字都不写盘** | 直接落盘 | `ev:file:src/memoria/services/agent/plan.py#L6-L14`（"零落盘"精确含义 + 测试逐文件钉住） |
| **被审批的执行者** | 人批准后：pre-image 快照 → 原子写 → 写后哈希 → 压会话撤销栈；可整批 `restore_batch()` 撤销（fail-closed） | 无审批落盘；自造备份格式 | `ev:file:src/memoria/services/agent/tools/kb.py#L4203-L4215`、`ev:file:src/memoria/services/agent/backup.py#L8-L10` |

**关键事实**：agent **不是**事实源的写者。写作链已经把"提案 → 校验 → 审批 → 备份 → 撤销"**全部外化为机制**。
⇒ 因此"agent 靠记忆维护知识库"不只是坏实践，它**与 Memoria 已经建成的架构相矛盾**：它绕开了这些机制。
这是我对人那句"用封装接口替代 agent 靠记忆维护知识库"的**技术解释**（不是复述他的话）：
他要替代的不是"agent 改库"这件事，而是"**靠不可审计的记忆去改**"这件事。

## §0.4 为什么"agent 靠记忆维护知识库"不可接受（4 条，按严重度排序）

| # | 失败模式 | 为什么不可接受 | 证据 |
|---|---|---|---|
| **M-1** | **记忆不是事实源** | 会话 `.jsonl` 是"历史"，不是"现状"；而 Memoria 已有 `compaction.py`（16 KB 压缩）与 `pruner.py`（10 KB 剪枝）——**记忆本身会被有损压缩**。用有损载体维护精确真源，漂移是必然而非偶然 | `ev:file:src/memoria/services/agent/compaction.py#L1`、`ev:file:src/memoria/services/agent/pruner.py#L1`（模块存在即证据）；`ev:file:AGENTS.md#L1`（单一事实源） |
| **M-2** | **不可审计、不可回放** | 记忆型维护只会留下"对话"，不留 `plan/txid/journal/写后哈希`；出事时无法回答"哪一批、改了哪几行、能不能只撤这一批"。而现有链**天然可回放** | `ev:file:src/memoria/services/agent/tools/kb.py#L3385-L3392`（txid 唯一性被实测踩过）、`#L4203-L4215` |
| **M-3** | **成本随库规模线性增长，且大库在结构上装不下** | 412 KB → 2530 KB（≈ 6×）。若靠"每轮重读以维持记忆"，token 随 md 数线性膨胀；2530 KB 粗估 ≈ 6.5×10⁵ 字符量级，**远超单次上下文** ⇒ 不是"贵一点"，是**不可能**。这条是硬约束，不依赖任何测量（不需要 N1） | `ev:lead-transcript`（库规模）+ 算术推理（analyst-inference，标注） |
| **M-4** | **不可验证** | 记忆型维护无法回答"上次改的那 3 处在哪、还在不在"——因为没有稳定身份。而本仓阶段 1/2 已经建出块身份/行号投影（`BlockIndex`、`data-block-id`），正是为了给"哪一块"一个可验证坐标 | `ev:lead-transcript`（P1/P2 已落地）；本仓 `docs/design/block-identity-design.md` |

**这四条里，M-3 与 §1 无关、与 N1 无关** —— 即使 MCP 化会让 token 变贵（A1 成立），M-3 依然成立（记忆维护更贵）；
即使 MCP 化更省（A1 被证伪），M-1/M-2/M-4 依然成立。这就是为什么 §0 的定位判断**不依赖 N1**。

## §0.5 方向声明：我把"全量移植"精确化成三分类（**这是 §0 的核心判决**）

### §0.5.1 先纠正一个提法上的歧义

人说的原话是「**全部移植能力模型**」。这句话的主语是**能力模型**，不是"DSH 的全部实现"。
据此我把 `freeze-v2.json::expected_categories` 的前三项拆开判决——**不与人的话冲突，而是把它变精确**：

| 类别（对应 freeze-v2 前 3 项） | 我的判决 | 理由（不是偏好） | 证据/依赖 |
|---|---|---|---|
| **① DSH 能力模型**（skill / hook / guard / plan / goal / todo / permission-presets 的**语义**） | **全移植**（语义对齐，非代码照搬） | 这是"体验不好"的**直接来源**：能力缺一条，模型就少一条约束，表现为"看着像但不好用"。已移植 7 类，但仍存在**语义缺口 + pin 过期漂移**（见 §0.5.2） | `ev:lead-transcript`（已移植 7 类、pin 2026-09-15、上游 skill-filesystem 改 3 次 / tool-skill 改 2 次 / 新增 2 包未移植） |
| **② DSH 宿主运行时**（Cordis 服务模型 / lifecycle / scoped layers） | **不全移植实现；只取契约语义** | Memoria **没有多插件宿主**：`plugins.py` 是声明面、无执行体；`shell_exec` 无沙箱；单进程单 agent。照搬 Cordis = 移植一个**不存在宿主的运行时**。但其中真正与"扩展点"相关的两条语义必须取：**scoped 可见性**（谁能看见谁的声明）与 **dispose 生命周期**（卸载时怎么收回注册） | `ev:file:src/memoria/services/agent/plugins.py#L4-L14`（无执行体）、`ev:file:docs/design/agent-plugin-design.md#L14`（字段准入规则：无消费者即移出） |
| **③ DSH 自用技能内容**（`.agents/skills` 的 `dsh-*`） | **不移植内容；移植装载协议** | 那批是 DSH 自己的使用示例，属"宿主自用内容"，不是能力模型。Memoria 需要的是**发现/rank/frontmatter 规则**（`skills.py` 已落地，带 pin 与 6 条偏差登记），内容应自己写（面向知识库维护） | `ev:file:src/memoria/services/agent/skills.py#L1-L19`（pin `0d1f50007f9bca3f52b06e1c3074fa14d5fb0720` + 逐条 `file:line` 对照表） |

**判决一句话**：
> **"全量"应当是"能力模型语义面的全量对齐"，而不是"上游实现的逐文件照搬"。**
> 前者我支持（且这是人的原话）；后者我反对，理由是 Memoria 的宿主形态与 DSH 不同，照搬运行时等于引入一个不存在的宿主。

这不是"为了迎合人而给违心结论"——恰恰相反，它在**③ 和 ② 上与"照搬一切"的最强解读相反**，
而在 ① 上比"选择性移植"更激进。判据是宿主形态（§0.2 四条否定 + §0.1 已有机制），不是我的偏好。

### §0.5.2 "此前选择性移植体验不好"的诊断（3 条，可检验）

| # | 原因 | 可检验的判据 | 当前状态 |
|---|---|---|---|
| D-1 | **选择标准是"像不像"，不是"缺不缺"** | 移植清单里每一条是否对应一个**用户可见能力缺口**；找不到缺口的就是"看起来该有" | 已移植 7 类中，至少 `permission-presets` 与 `hooks` 的消费者在 Memoria 侧需要逐条点名（待 §4 覆盖面表展开） |
| D-2 | **移植粒度是文件，不是语义** | 每条移植是否有**行为契约测试**（§0.6 的 T1–T4）；只有文件搬运 ⇒ 行为不等价 | `skills.py` 做对了一半（有 pin + 逐条规则 + 6 条偏差），其余模块待核 |
| D-3 | **pin 过期无人负责** | 上游变更后是否有"漂移台账 + 责任人 + 复检触发" | 已知：pin 2026-09-15，之后 `skill-filesystem` 改 3 次、`tool-skill` 改 2 次、新增 `skill-office` / `tool-workspace-dependencies` 未移植 —— **无台账、无责任人**（`ev:lead-transcript`） |

D-3 是本轮辩论**必须解决的组织缺陷**：它与我 Phase 3 主张的"`unknowns` 必须绑 `if_true_then`"同源 ——
**没有失效条件的移植清单，就是一份会静默腐烂的清单**。

## §0.6 判据：怎么算"移植对了"（4 条黑盒契约，供 §4 三表与 §2 论断使用）

不按"移植了几个文件"验收，按**可跑的行为等价**验收（每条都能判红）：

| ID | 断言 | 判据 | 可否定性 |
|---|---|---|---|
| **T1** | 工具 schema 结构等价 | 同一 `tool_id` 的 `name/description/parameters` 与上游 `ToolSchema` 逐字段**结构**对齐（文本可不同，结构不可不同；差异须登记） | 上游 `ev:file:dsh-src/packages/core/tools/src/schema.ts` |
| **T2** | 发现结果等价 | 同一组技能根下，`skills.py` 的发现集合与 rank 决策与上游一致；含负例（嵌套 `SKILL.md` **不**发现） | `ev:file:src/memoria/services/agent/skills.py#L18-L19` |
| **T3** | 决策等价 | `guard` / `hooks` / `permission-presets` 对同一输入的判定（allow/deny/confirm）一致 | 上游对应包 |
| **T4** | 状态机等价 | `plan` / `goal` / `todo` 的**合法状态转移集**一致（不是 UI 一致） | 上游对应包 |

**这四条就是"全量"的可操作定义**：全量 ≠ 文件数，全量 = T1–T4 在覆盖类目上全绿 + 盲区已登记。

## §0.7 §0 的证据状态分级（E1/E3 合规：不把转述当实测）

| 级别 | 内容 | 处置 |
|---|---|---|
| **我本轮实测** | 97 文件 / `kb.py` 304,374 B / `registry.py` 12,360 B / `dsh-src/packages` 52 包 / `src` 内 MCP 协议代码 0 处（含 `memcpy` 误报说明）/ 各模块头部自述 | 作为 A 级证据使用 |
| **Lead 转述、本轮未复核** | 运行载体 pywebview/WebView2；库规模 38 md/412 KB 与 255 md/2530 KB；pin 2026-09-15；上游 3 次/2 次变更与 2 个新包 | 一律标 `ev:lead-transcript`，**不进裁决**，只作上下文 |
| **分析推理** | §0.5 三分类判决、§0.4 M-3 的"装不下"算术、§0.5.2 三条诊断 | 标 analyst-inference；对应 `assumption_id` 待 §2 正式登记 |

---

# §1 外部独立来源（PROTOCOL §10 硬要求：≥3 个，每类只算一个，不得同作者同材料）

> **先声明我不做什么**：本节三个来源**都不用于判定 A1**（「MCP 化一定增 token 开销」）。
> A1 的检验归 `task-114`（N1，metrics-baseline），我在此**不越位**、也不引用任何数字去暗示 N1 的结论方向。
> 本节只服务 §0 的定位判决与 §2 的形态选择。

## §1.1 S1｜MCP 官方规范 `2026-07-28`（类别：MCP 官方规范，计数 1）

**来源身份**：`ev:spec:mcp/2026-07-28#changelog`
→ <https://modelcontextprotocol.io/specification/2026-07-28/changelog>（页面自述"Version 2026-07-28 (latest)"；
变更口径为"since the previous revision 2025-11-25"）。已 fetch 验证存在（HTTP 200）。

**我从中取用了什么**（只取条款，不取"应该这样做"）：

| 条款 | 内容（原文要点） | 我取用它的地方 |
|---|---|---|
| Major #2 | **协议无状态化**：移除 `initialize`/`notifications/initialized` 握手；每个请求在 `_meta` 里携带协议版本与客户端能力 | §2-Q2 的实现成本论证（无会话管理） |
| Major #8 | 所有 result 必须带 `resultType`（`complete` / `input_required`） | §4 每个工具往返的**固定 token 结构**（可预算） |
| Minor #2 | 为 `_meta` 的 OpenTelemetry 上下文传播定义约定（`traceparent`/`tracestate`/`baggage`） | §2-Q5 trace：**走协议标准字段**，不自造 |
| Minor #3 | `tools/list` **SHOULD** 返回确定性顺序，以利于客户端缓存与 **LLM prompt cache 命中率** | §4 token 节约：schema 顺序是协议承认的成本变量 |
| Minor #5 | `tools/list`/`resources/read` 等结果须带 `ttlMs` + `cacheScope` | §4：把"重复拉取"降为可缓存项 |
| Deprecated | Roots / Sampling / Logging 进入弃用期，建议改用工具参数、资源 URI、直连 provider | §2-Q3 扩展点：**不把新契约建在弃用面上** |

**它支持我的哪个论断**：
- 支持 **C0.5-②「宿主运行时不全搬，但要取契约语义」**：协议已经把"会话/状态"从传输层拿走（Major #1/#2），
  ⇒ "要不要在 Memoria 里造一个会话型宿主"这个问题的**方向**被协议自己否定了；反过来，`_meta` 承载版本/能力/trace 才是当代契约形态。
- 支持 **C2-Q2「可以作为 MCP server」的可实现性**（注意：只支持"可实现"，不支持"应该做"——后者要 §2 论证 + N1 的成本面）。
- 支持 **C2-Q4「token 预算要按完整往返算」**：`resultType` + `_meta` 是每个 result 的固定骨架，属于"必然发生的 token"，必须计入预算。

**它的局限（不隐去）**：
1. **规范只定义线上格式，不定义实现成本**。"无状态化 ⇒ 实现更便宜"是我对条款的**推理**，规范本身没有这句话，也没有任何测量。
2. **版本极新（2026-07-28）**：客户端生态大概率滞后（上一版是 2025-11-25）。把它当"现在所有客户端都支持"的证据会过强；
   我的用法仅限"若要暴露，契约长什么样"。
3. **它不回答问题本身**：规范不回答"Memoria 该不该做 MCP server"，也不回答"做了会不会更贵"。
4. 它是**同一生态的文档**（MCP 项目），按"不得同作者同材料"我把它算作 1 个来源、且**不**与 S4 合并计数（见 §1.5）。

## §1.2 S2｜Basic Memory（类别：其他项目的 agent-KB 接口，计数 1）

**来源身份**：`ev:doc:url:https://raw.githubusercontent.com/basicmachines-co/basic-memory/main/README.md#mcp-tools`
→ repo `basicmachines-co/basic-memory`（AGPL-3.0；Python 3.12+；FastMCP；"your knowledge lives as Markdown files that both you and your AI can read, write, and search"）。已 fetch 验证存在（HTTP 200）。

**为什么选它（而不是随便找一个 MCP 项目）**：它是**与 Memoria 同构度最高**的公开实现 ——
Markdown 文件 + frontmatter + wikilink 图 + 双向读写 + 本地优先，**且已经把整套能力暴露成 MCP**。
这正是本轮问题的"存在性证明"。

**我从中取用了什么**：

| 取用点 | 它的做法 | 我用在哪 |
|---|---|---|
| **工具面按操作分族** | 内容类 `write_note/read_note/edit_note/move_note/delete_note/read_content/view_note`；检索类 `search_notes/recent_activity/list_directory`；图谱类 `build_context`（导航 `memory://` URL）；项目类；schema 类 `schema_infer/validate/diff`；兼容层 `search`/`fetch` | §2-Q3 扩展点 + §4 工具面分类（**按"库的操作**分族，不按"上游能力模块"分族） |
| **工具注解承担"渐进式发现"** | 每个工具带 `readOnlyHint`/`destructiveHint`/`idempotentHint`/`openWorldHint`；README 明说目的是 "no wasted context trying things to see what they do" | §4：用**注解**替代"试一下才知道"，这是 token 节约的**结构性**手段（不靠截断） |
| **输出格式可选、默认省** | 所有工具默认 **text** 输出，`output_format="json"` 按需 | §4：默认紧凑文本 + 结构化按需（与 §4 截断语义一脉相承） |
| **检索返回内容而非句柄** | "Matched chunk text is included so the LLM gets context, not just hits" | §4：返回**高信号内容**而不是 ID 列表（避免二次往返） |
| **写工具有 guard** | `write_note` 防意外覆盖；`edit_note` append/prepend 缺页自动创建 | §3：写侧安全不是"加个审批"，而是**每个写动词自带前置条件** |
| **文本↔图的双向一致性** | 同一份 md 被 Obsidian 与 LLM 同时读写 | §0.1 的定位校准（存在"人是唯一写者"之外的成熟形态） |

**它支持我的哪个论断**：
- 支持 **C0.5-①「能力模型语义面全量」是对的方向**：一个同构系统把"读/写/检索/图/schema"**全部**工具化后才算可用；
  只做"读"或只做"读+整文件写"会迫使 agent 用低层工具拼高层动作（这与 S4 的"工具要按工作流合并"互证）。
- 支持 **C2-Q2「Memoria 可以（且应当被认真考虑）作为 MCP server」**：存在性证明 + 工具面形状可直接借鉴（**形状**，不是代码）。
- 支持 **C2-Q3 扩展点设计的验收口径**：扩展点必须能让"新增一类库操作"不改核心 —— 它的 schema 三件套（infer/validate/diff）就是"把结构能力做成工具"的样例。

**它的局限（不隐去）**：
1. **它是产品 README，不是测量报告**。"no wasted context"、"progressive discovery"是**设计意图**，没有数字 ⇒ 按 E4 它**不能**支撑任何"省 X%"的主张。我只用它证"形状可行"，不用它证"更省"。
2. **AGPL-3.0**：只能取**设计思路与接口形状**，**不得复制代码**。这同时符合 B5 的边界（可作背景动机/设计参照，不作裁决证据）。
3. **宿主模型不同**：它为**多客户端**（Claude Desktop/Code、Codex、Cursor、VS Code、ChatGPT）服务，工具数量大，所以需要"渐进式发现"；
   Memoria 是**单进程内嵌单 agent**，工具数远小（`kb.py` 一个文件里的工具面）⇒ **不能照搬**它的发现机制，只能判断"是否需要"（§2-Q3 回答）。
4. 它是**商业产品**（README 含付费段落），存在选择性呈现风险；我只引用其**接口清单与设计选择**这类可交叉验证的事实。

## §1.3 S3｜arXiv:2508.02694《Efficient Agents: Building Effective Agents While Reducing Cost》（类别：token/成本经济测量，计数 1）

**来源身份**：`ev:paper:arXiv:2508.02694#abstract`
→ <https://arxiv.org/abs/2508.02694>（Wang, Hu, Liu, Zhu, Hou, Huang, Zhang, Yang, Liu, Zhang, Zhang, Wang, Jiang, Zhou；Submitted 24 Jul 2025；cs.AI/cs.CL/cs.MA；代码 `github.com/OPPO-PersonalAI/OAgents`）。已 fetch 验证存在（HTTP 200）。

**我从中取用了什么**（只取方法与结论，不取数字当 Memoria 的预测）：

| 取用点 | 内容 | 我用在哪 |
|---|---|---|
| **`cost-of-pass` 指标形态** | 把成本与"任务是否通过"绑定成一个指标，而不是孤立报成本 | §4：**省 token 必须在同等完成度下比较**（与 B4.e 的 `functional_pass` / `token_delta` 分离同源） |
| **复杂度边际收益递减** | 系统研究"任务本身需要多少复杂度 / 何时增加模块收益递减 / 框架设计能省多少" | §2-Q1：**"全量"必须回答"这一层机制是否被任务需要"**，不是"能力越多越好" |
| **实证结果** | 保留 OWL **96.7%** 性能，成本 **$0.398 → $0.228**，`cost-of-pass` 改善 **28.4%** | §2-Q1 的**方向性**支持：**更少机制也能保住性能**是被实证支持过的路径（不是我的偏好） |
| **归因边界** | 收益来自"框架设计"（模块选择/测试时扩展策略），不是来自换协议/换传输 | §2-Q2：**token 问题不能只靠"换接口"解决**，也不能以此否定 MCP（两条路径可叠加） |

**它支持我的哪个论断**：
- 支持 **C0.5-②「宿主运行时不照搬」**：该文最接近的实证结论是"复杂度超过任务需要 ⇒ 收益递减"，
  这是我能找到的、与"照搬一个多插件宿主运行时到单进程"最直接相关的**外部证据**（方向支持，不是等同证明）。
- 支持 **C2-Q4「每个工具要有 token 预算上限」**：`cost-of-pass` 的存在本身就是"成本必须被度量而不是被宣称"的证明。

**它的局限（不隐去）**：
1. **它测的是美元成本（含模型价格），不是纯 token**；且 **GAIA 是网页研究任务**，与"知识库维护"任务分布不同 ⇒ **不可直接外推**到 Memoria。
2. **单一工作、未见第三方复现**；作者与代码同源（OPPO），有自评风险。
3. **它比较的是 agent 框架（OWL vs Efficient Agents），不是 MCP vs 文件工具** ⇒ **不能作为 A1 的证据**（我没有这样用）。
4. 28.4% 这个数字**不可移植**到本仓：它依赖该文的模型选择与任务集；我用它只作"方向存在"的证明。

## §1.4 S4｜补充来源（**不计入 ≥3 的独立计数**，显式降级）

**来源**：`ev:doc:url:https://www.anthropic.com/engineering/writing-tools-for-agents#token-efficiency`
（Anthropic Engineering，"Writing effective tools for agents"）。已 fetch 验证存在（HTTP 200，注意实际 URL 落在 `/research/` 下）。

**为什么单列**：它与 S1 同属**同一厂商谱系**的文档材料。按"不得同作者同材料"，**我不把它算作第 4 个独立来源**，
只作为 §4 设计时的**工程参照**（并且按 B5，它只能作背景动机，不能作裁决证据）。

**取用点（均为可核对的原文事实，不是我的引申）**：
- **截断默认值**：Claude Code 默认把工具响应限制在 **25,000 tokens**；
- **响应详略可控**：给出 `ResponseFormat` 枚举（`DETAILED` / `CONCISE`），示例中 detailed **206 tokens** vs concise **72 tokens**（≈ ⅓）；
- **按工作流合并工具**：与其 `list_users`/`list_events`/`create_event`，不如一个 `schedule_event`；与其 `read_logs`，不如 `search_logs` 只回相关行；
- **截断要带引导**：截断时告诉 agent 用"多次小范围检索"而不是一次大检索；错误响应要"具体可操作"而不是不透明错误码。

**它支持**：§4 的"每个工具给 token 预算上限 + 截断语义 + 失败语义"三件套（这正是 task-115 §2-Q4 的关闭条件之一）。
**它的局限**：厂商工程博客，非同行评审、无公开测量协议；数字（25,000 / 206 vs 72）是**其产品内部口径**，不可假设与 Memoria 的分词器/模型一致；
且它不讨论"接口协议层"的开销（MCP vs 进程内函数），因此对 A1 无证据力。

## §1.5 来源 → 论断映射表 + 独立性自检

| 论断（§0/§2 引用） | S1 MCP 规范 | S2 Basic Memory | S3 arXiv:2508.02694 | S4（不计票） |
|---|---|---|---|---|
| C0.5-① 能力模型语义面全量 | — | ✅ 形状存在性 | ✅ 复杂度/收益递减（方向） | — |
| C0.5-② 宿主运行时不全搬、取契约语义 | ✅ 协议已移除会话层 | — | ✅ 方向支持 | — |
| C0.5-③ 自用技能内容不移植、只移植协议 | — | — | — | — （本条靠本仓 `skills.py` pin 证据，不靠外部） |
| C2-Q2 可作 MCP server（可实现性） | ✅ 契约形态 | ✅ 存在性证明 | — | — |
| C2-Q3 扩展点验收口径 | ✅ 弃用面清单 | ✅ schema 三件套 | — | ✅ 工具合并/命名空间 |
| C2-Q4 token 预算/截断/失败语义 | ✅ `_meta`+`resultType` 固定开销 | ✅ 默认紧凑 + 按需结构化 | ✅ cost-of-pass | ✅ 25k/206vs72 |
| C2-Q5 trace | ✅ `_meta` 的 OTel 约定 | — | — | — |
| **A1（MCP 是否增 token）** | **不使用** | **不使用** | **不使用** | **不使用** |

**独立性自检（满足 PROTOCOL §10 的"不得同作者同材料"）**：
- 作者/组织：MCP 规范（MCP 项目）｜Basic Memory（Basic Machines 公司）｜论文（Wang 等，多机构，含 OPPO PersonalAI）⇒ **三者不同源**。
- 材料类型：**规范**（应然格式）｜**产品实现**（已然形态）｜**同行可查的实证研究**（成本测量）⇒ **三种证据类型不同**，
  且它们的失效方式不同（规范会滞后、产品会营销、论文会不可外推）——这正是我为什么要求三类各一，而不是找三篇论文。
- 引用纪律：三源均为**本轮新 fetch 验证**（HTTP 200）；未引用任何无法打开的来源；S4 主动降级不计票。

## §1.6 本节对 A1 的立场（明确不越位）

- A1「MCP 化一定增 token 开销」由 `task-114` 检验，判据须含**零新增 schema 对照组**（PROTOCOL §6 N1）。
- 我在 §1 得到的唯一与 A1 相邻的结论是：**"固定开销是结构性的、可预算的"**（S1 的 `_meta`/`resultType`；S4 的 schema 随工具数增长），
  这与"是否净增"是两回事。**净增与否必须由 N1 的分组测量回答，我不预设。**
- 若 N1 结论为"成立（确实增）"：我要在 §2-Q2 增加"何时不该做 server"的条件分支；
  若为"不成立"或"无法判定"：§2-Q2 从"缓解开销"转为"选择成本最优形态"。**两种情况都不改变 §0 的三分类判决**（§0.7 已给理由）。

---

# §-1 前置：N1 结论如何改变了我的前提（E3 合规，先置而非后补）

**`task-114` 已完成（commit `a15cc240`，Lead 独立复跑 sha MATCH）。A1 被证伪。**

| 场景 | 组 A（当前） | 组 0（零新增 schema） | 组 B（MCP 化） | 组 0 vs A | 组 B vs A |
|---|---|---|---|---|---|
| T1 查概念 | 57,882 | 9,882 | 10,979 | **−82.9%** | −81.0% |
| T2 通读一章 | 537,682 | 57,682 | 68,349 | **−89.3%** | −87.3% |
| T3 多轮问答 | 111,615 | 15,615 | 17,839 | **−86.0%** | −84.0% |

**证据**：`ev:bench:n1-a1-token-hypothesis#§4`（`artifacts/agent/verify/debate/n1-a1-token-hypothesis.md`，12,581 B）。

**我自己复算的两个要点（不转述，用原始数字）：**
1. **组 B（MCP）在三个场景都**比组 0（不含 MCP、只改返回粒度）**更贵**：
   10,979/9,882 = **+11.10%**；68,349/57,682 = **+18.53%**；17,839/15,615 = **+14.24%**。
   → Lead 消息里写的是"省 10%/16%/12%"，N1 报告原文写的是"略高 8–15%"。**以原始数字复算为 11.10/18.53/14.24%**，
   差异不影响结论方向（组 B 恒比组 0 贵），但按 J6' 应就地更正口径 —— 我先改正，再据此立论。
2. **结论等级是 `directional`（静态记账模型，未跑真 tokenizer），不是 `verified`**（N1 §6 自述；§7 敏感性分析显示口径变化不翻转方向）。
   这不削弱证伪力度：**A1 是"一定增"的全称命题，证伪全称只需一个反例，而 N1 给了三个**；
   真正是 directional 的是**幅度**，不是**方向**。

**⇒ 因此作废的论断（我不再使用）**：
- ❌ "MCP 化可以省 token / MCP 是为了省 token" —— 作废（组 0 证明不碰 MCP 也省 83–89%，且 MCP 更贵）。
- ❌ 任何以"A1 成立"为前提的缓解设计（如"为了对冲 MCP 的 schema 成本，我们要做 X"）—— 前提消失，设计作废。

**⇒ 因此**必须重写的**：Q2 的论证理由**（token 理由已死）；**Q4 的重心**（从"省 token 的 MCP 接口"改为"与 MCP 正交的返回粒度设计"）。

**受影响的假设登记（E3）**：

| assumption_id | 内容 | 状态 | 检验者 / 依据 |
|---|---|---|---|
| `AS-MCP-COST` | "MCP 化会增 token" | **已证伪**（directional） | `task-114` metrics-baseline，`ev:bench:n1-a1-token-hypothesis#§4` |
| `AS-GRANULARITY` | "省耗由返回粒度决定，与是否 MCP 无关" | 已被同一实验支持（组 0 不含 MCP 仍省 83–89%） | 同上；**我的 Q4 全部建立在这条上** |
| `AS-STYLE-COST` | "MCP 形态的额外成本 = 结构化 JSON 键名 + 一次性 discover" | **未检验**（N1 §4 归因，未分离测） | 检验者待指派；影响 Q2 的"若做则最小化 schema"建议 |

---

# §2 核心论断（五问）

## §2-Q1 全量移植到什么程度

**【论断】**
"全量"应当按**三类分别判决**，且**验收单位是语义契约（§0.6 的 T1–T4），不是包名/文件数**：
① **能力模型：补齐**（5 个包族 + 工具管线扩展点 + 技能脚手架剩余 4 层）；
② **宿主运行时：不补实现，只取 2 条契约语义**（scoped 可见性、dispose）；
③ **自用技能内容：不补内容**，只补装载协议（协议已在 `skills.py` 落地）。

**【证据】**
1. **既有判定表不是空白**：`ev:file:docs/design/dsh-agent-port.md#L94-L193`（§5 包级映射表，52 包逐条 `✅吃 / ❌不吃 / ⏸按需` + 上游 `file:line`；
   §5.1 再按读/写/把关/备份审计/技能分表对照；§5 末段 ①②③ 给出"已完全移植 / 本地替换 / gap 清单"）。这使 Q1 变成**在既有表上做二选一**，而不是重新规划。
2. **能力模型缺口的正例（有消费方点名）**：
   - `commands`：文档自述"⏳ 仍未移植…**但消费方现在出现了** —— compaction 已落地 ⇒ `/compact` 有真实需求"（`dsh-agent-port.md#L111`）；
   - `hooks/* guard/* plan/* goal/* todo/*`：`⏸ 按需`→ 实际"除 `skill` 外一个都没吃"（`#L117`），其中 `todo_write` 是"唯一看着可直接吃的小件"；
   - 工具管线扩展点：`❌ 未移植：output/render/展示、restrict 掩码、多事件瀑布、PTC mode`（`#L185`）。
3. **宿主运行时不该补的反例（有理由）**：`core/agent` 的 registry/initiator 是"Cordis 专有 ⇒ 不吃"（`#L105`）；
   `session-projection*` 框架"是 Cordis registry + 持久缓存 + change feed ⇒ 不吃"（`#L107`）；`telemetry(OTel)` 不吃（同处）。
4. **同名不同物（我本轮新增的硬证据，按 P1 必须自曝）**：至少 3 处，说明"按名字对齐"必然错：
   - `plugin`：上游 = Cordis 服务模型；本地 = **声明式能力闸，无执行体**（`ev:file:src/memoria/services/agent/plugins.py#L4-L14`）；
   - `plan`：上游 `plan/*` = plan mode（权限/只读档）；本地 `plan.py` = **写计划编译器**（`ev:file:src/memoria/services/agent/plan.py#L6-L14`）；
   - `sandbox`：上游 = 内核三档隔离；本地 = **声明式 `permissions` + realpath 前缀**（`dsh-agent-port.md#L160`，隔离强度不同档）。

**【依赖假设】**
`AS-GRANULARITY`（Q4 用）；本问不依赖 A1。另：`AS-PORT-LEDGER` = "`dsh-agent-port.md` §5 的判定仍基本有效"——
该文档**部分行已过期**（例：`#L117`/`#L193` 称"能力插件契约本体仍未实现、`capabilities.json` 零命中"，但 `plugins.py`（35 KB）已存在且实现了解析/校验/发现），
故我改用它时对**结论性行**做独立复核，见 §4 `checked[]` 的复核命令。

**【falsifier】**
① 若出现"某包被判定 ❌不吃，但存在真实消费方/用户可见需求"的证据（`ev:file:` 该消费方 + 需求描述），则②③中对应条目翻为"吃"；
② 若 T1–T4 中的任一条在本地跑不通（无法建立等价判据），则"按语义全量"退化为"按类目全量、等价性用偏差登记替代"（并降级为 `unverified`）。

**【代价】**
- 判错"该补"（补了没人用）：多维护一段语义 + 多一条 pin 漂移负担；
- 判错"不该补"（漏了有人用）：模型少一条约束，表现为"看着像但不好用"——**这正是上一轮体验差的成因**（§0.5.2 D-2），代价更高。
- 我选择**偏向"补语义"**的误差方向，理由：补错的成本可退役，漏补的成本是用户持续踩。

---

## §2-Q2 Memoria 作为 MCP server

**【论断】**
MCP server 是**已定方向**（`R-L2`，组织决定），本文不设"是否立项"的条件门。我的技术立场只保留两点：
**(a) 交付顺序**：先做"粒度化 + 进程内服务层契约"，MCP 作为该契约的**薄绑定**再投递——理由是 N1 证明 MCP 不省 token、且把"整文件读"固化进对外契约的代价不可逆；
**(b) 形态**：若做，工具面取**最小集** + 结构化按需（默认 text）+ schema 总量设上限。
我**不**反对做 MCP，也不把"省 token"当作做它的理由；我反对的是"跳过粒度化、直接把当前 35 工具整面暴露成 MCP"。

**【证据】** ① token 理由已死：`ev:bench:n1-a1-token-hypothesis#§4`（组 0 无 MCP 省 83–89%，组 B 恒比组 0 贵 11.10/18.53/14.24%，我按原始数字复算）；
② 封装已在进程内成立：`ev:file:docs/design/dsh-agent-port.md#L151`（"本地换了模型：不是工具直接写"）+ `ev:file:src/memoria/services/agent/tools/kb.py#L4203-L4215`；
③ 内部 trace 已存在：`ev:file:docs/design/dsh-agent-port.md#L132`（会话查询 4 工具）、`#L171`（`capability/*` 审计事件）；
④ 协议成本形态：`ev:spec:mcp/2026-07-28#changelog`（无状态化、`_meta`、`resultType`、`ttlMs`）。
四条合成一张 4 步理由链表（下表），**没有一条依赖"A1 成立"**。

**理由链（4 步，逐步带证据；token 理由已按 §-1 删除）**

| 步 | 命题 | 证据 |
|---|---|---|
| 1 | token 不再构成理由 | `ev:bench:n1-a1-token-hypothesis#§4`：组 0（无 MCP）省 83–89%，组 B 恒比组 0 贵 11–19% |
| 2 | "封装/受控接口"**在进程内已被满足**，MCP 只对**外部** agent 新增价值 | 内部 agent 早已不直接操作 markdown：`propose_write` 只产 plan → 编译器（16 ops）→ 唯一写者（`dsh-agent-port.md#L151`）；写链 `kb.py#L4203-L4215`。**内部已有受控接口**，MCP 不是它的前提 |
| 3 | "trace 可记录"**对内部调用已成立**，MCP 只对**跨进程**新增价值 | 内部：会话 JSONL 可回放 + `audit.py`（`capability/apply|undo|redo`）+ 4 把 session 查询工具（`dsh-agent-port.md#L132`、`#L171`）。**跨进程边界才是进程内 hook 抓不到的** |
| 4 | "可测试/可替换"不需要进程边界 | 进程内 facade（服务层契约）同样能给稳定接口；换实现只需换 facade 之后 |

**⇒ 结论**：
> MCP 的**独特价值 = 跨进程互操作 + 跨边界可观测**（这是它存在的理由，也是既定方向）；
> 但"省 token"不是它的价值（N1 已证伪），所以 MCP 的**交付质量取决于它暴露的接口是否已经粒度化**，而不是取决于"有没有 MCP"。

**交付规则（只约束"顺序"与"形态"，不约束"做不做"）**

| 规则 | 内容 |
|---|---|
| **P-1 顺序** | 组 0 粒度化（Q4）**先落地**。否则 MCP 会把"整文件读"这个 89% 的浪费**固化进外部契约**——之后再改契约的代价远高于改进程内函数 |
| **D-1 形态** | 工具面取**最小集**；**动态裁剪需新增消费者**（Q3 已按 R-R1 撤回 gate 主张，不再声称"gate 已生效"）；结构化输出**按需**（默认 text，参照 S2）；schema 总量设上限（N1 实测组 A 35 工具 ≈ 4,349 token/会话固定成本） |
| **X-1 复盘** | **交付后 6 个月复盘**（调用量/外部客户端数/维护成本）；**交付义务不受需求证据影响**——这是既定方向，复盘只决定"是否优化/加文档/调工具集"，不决定"是否做" |

**【依赖假设】** `AS-MCP-COST`（已证伪）、`AS-STYLE-COST`（未检验：MCP 额外成本的构成）。
**【falsifier】** ① 若真机实测发现进程内 facade 无法提供等价的**跨进程**能力（例如 DSH/Trae 只能用 MCP 接入、且该接入是既定需求的一部分）⇒ "先 facade 后 transport"的顺序反转为"并行交付"；
② 若 MCP 交付后实测 schema 总量未超上限、且粒度化接口已先行 ⇒ 本论断的"顺序"约束可解除。
**【代价】**
- 判错方向 A（顺序反了，MCP 其实该先做）：损失是**晚交付外部接入**；但 facade 已建 ⇒ 补 transport 工作量小（S1：2026-07-28 已无状态化，**无会话管理**）。
- 判错方向 B（跳过粒度化直接暴露 35 工具整面）：损失是**永久维护一份"整文件读"对外契约**（向后兼容负担）+ 每轮 schema 固定成本。B 不可逆，A 可逆 ⇒ 先 A。

---

## §2-Q3 扩展点设计（"加一类能力而不改核心"）

**【论断】**
扩展点**已有两层**（声明面 `plugins.py` + 6 字段契约 + 核心原语目录），真正缺的是**第三层：工具面扩展点**（第三方加工具没有收口处）。
我原主张的"把 `gate` 升级为首要裁剪手段、用来对冲 schema 成本"**撤回**（R-R1，实测 `gate` 当前不被求值，见下）。
新的立场：**动态裁剪是"要做的事"，不是"已有的抵消手段"**——它需要一个目前不存在的投影消费者。

**【证据】**
1. 已有：`plugins.py`（解析/校验/发现；同名 id 重复即装载失败；`permissions` 必须是库内相对 glob；`permissions.write` 非空 ⇒ `approval ≠ auto`）
   —— `ev:file:src/memoria/services/agent/plugins.py#L4-L14`；
   契约 6 字段与"准入规则"（无消费者即移出）—— `ev:file:docs/design/agent-plugin-design.md#L15`。
2. 缺口被文档明说：`❌ 未移植：output/render/展示、restrict 掩码、多事件瀑布…`，
   **"扩展点缺失 ⇒ 第三方加工具时没有收口处，只能改 `registry.py` 本体"** —— `ev:file:docs/design/dsh-agent-port.md#L185`。
3. **`gate` 当前是死字段（R-R1 撤回依据，我独立复核确认）**：
   - `kb_has_sidecar` 全仓仅 2 命中：`plugins.py:27`（注释）+ `:66`（`GATE_VALUES = ("always","kb_has_sidecar")` 枚举定义）；
   - `gate` 被 `ToolDeclaration` 解析与校验（`plugins.py:247-258`），但 `op_available()`（`:536-541`）只读 `OP_TOOL_IDS` + `self.tool_ids`（启用位），**不求值 `gate`**；
   - `build_kb_tools()`（`kb.py:486`，函数体 243 行）内 `gate/plugin/available/enabled` **零命中**。
   ⇒ "工具不出现 = 不花 schema token"在**当前代码里不存在**。我此前的 Q3/Q4 把它当作已生效杠杆，是错的；撤回。

**【论断落地：契约增量】**
- **本轮不再新增任何字段**（R-R2）。我原提的 `tool_schema_ref` / `budget` / `lifecycle.dispose` **全部移出 v1**，
  因为它们都没有 `file:line` 级消费者 —— 按我自己引用的 `agent-plugin-design.md#L15`「无消费者即移出 v1」的标准，同样适用于我的提议。
  逐条说明为什么没有消费者、以及复评触发条件：

| 被移出的字段 | 为何无消费者（file:line） | 复评触发条件（何时回来） |
|---|---|---|
| `provides.tools[].tool_schema_ref` | 工具 schema 由 `Tool.schema()`（`registry.py:120-122`）从 `ToolSchema` 出，**不读插件声明**；"工具面投影"目前只发生在 `build_kb_tools()`（`kb.py:486`），其中无任何读插件声明的分支 | 出现 ≥1 个第三方插件**自带 schema** 导致工具面膨胀的实例 |
| `provides.tools[].budget` | 结果有界由 `kb.py:64-71` 的**硬编码常量**承担（`MAX_BODY_CHARS=20_000` 等），无 per-plugin/per-tool 分发层消费点 | 真机 E4 测出"结果无界导致总账失控"（复用 Q4 的 falsifier） |
| `lifecycle.dispose[]` | "启停"已由 `ActivePlugins` + 启用位表达（`plugins.py:511-541`），无"按字段撤销注册"的消费者 | 出现 ≥1 个"卸载后残留可见工具"的实例 |
| `gate`（已有字段，但**当前不求值**） | 见上 R-R1：解析了、存了、**从不参与工具面投影** | `build_kb_tools()` 前补上能力投影消费者（即 Q3 的"第三层"落地）后，重新评估 |

- **动态裁剪作为"待做的第三层"**：若要实现"按库状态决定工具是否出现"，正确落点是在 `build_kb_tools()` **之前**加一个
  "`ActivePlugins` → 工具集投影"消费者（`conditional_object`；`reversal_condition` = 该消费者落地后撤回本条撤回）。
  在此之前，**不声称**它对冲了 schema 成本。

**加载边界与失败隔离（保持现状，不新增复杂度）**：
库内 glob + `realpath` 前缀校验（越界即拒）；插件目录**无执行体** ⇒ 失败隔离天然成立（声明坏 ≠ 代码坏）；同名 `id` 重复 ⇒ 装载失败（不静默取其一）。

**【依赖假设】** `AS-TOOLSCHEMA-COST`（工具 schema 每会话固定成本 ≈ 4,349 token，来自 N1 §2 实测）。
**【falsifier】** 若"工具面投影消费者"落地后，实测 `gate` 裁剪能覆盖 >50% 工具（非恒 `always`）且 schema 成本下降 ⇒ 我撤回 R-R1 的撤回，`gate` 恢复为有效杠杆；
若投影消费者落地后仍无法裁剪（工具集天然恒全量）⇒ 动态裁剪方向本身不成立，改按"静态最小集 + 场景包"。
**【代价】** 把四个字段全部移出 v1 的代价是：预算/裁剪/生命周期都要靠**代码常量和约定**而非契约字段保证 ⇒ 可漂移、不可机检。
这是"诚实 > 完备"的取舍：与其留四个无消费者的装饰字段，不如空着等真实消费者（这正是 `agent-plugin-design.md#L15` 的立意）。

---

## §2-Q4 token 节约接口（重心已按 N1 改为"返回粒度"）

**【论断】**
省钱的主因是**返回粒度**（N1 组 0：不碰 MCP 也省 83–89%），因此接口第一原则是
**"默认窄、按需宽、宽必有界"**；**MCP 与省耗正交**，只是这些粒度化接口的一种投递方式。

**【证据】** ① 粒度是主因：`ev:bench:n1-a1-token-hypothesis#§4`（组 0 = 不碰 MCP，T1/T2/T3 省 82.9/89.3/86.0%）；
② schema 固定成本是真实项：`ev:bench:n1-a1-token-hypothesis#§2`（组 A 35 工具、15,220 字符 ≈ 4,349 token/会话）；
③ 现有工具已有界（不是从零设计）：`ev:file:docs/design/dsh-agent-port.md#L187`（`DEFAULT_TOP_K=5`/`MAX_BODY_CHARS=20_000`/`MAX_FILES_IN_OVERVIEW=200`，`kb.py:64-71`）、`#L128`（read 分页 2000 行 + 20,000 字符预算）；
④ 写侧已 patch 式：`ev:file:docs/design/dsh-agent-port.md#L151-L152`（`KNOWN_OPS` 17 / `COMPILED_OPS` 16，含 `replace_lines` + `expect` 逐字校验）；
⑤ 截断/详略的工程参照：`ev:doc:url:https://www.anthropic.com/engineering/writing-tools-for-agents#token-efficiency`（25,000 token 默认上限；detailed 206 vs concise 72 tokens）、`ev:doc:url:https://raw.githubusercontent.com/basicmachines-co/basic-memory/main/README.md#mcp-tools`（默认 text、`output_format=json` 按需）。

**【三级粒度（读侧）】**

| 级 | 接口形态 | 典型问题 | 预算上限（初值，**未测**） |
|---|---|---|---|
| **L0 outline** | `outline(path)` → 标题树 + 块计数 + 行号范围 | "这篇有什么" | **≤ 800 tokens** |
| **L1 section**（**默认**） | `section(path, heading\|kp_id\|line-range)` → 单节正文 | "这一节说了什么" | **≤ 4,000 tokens** |
| **L2 snippet** | `snippet(path, query\|anchor, ctx=±N)` → 命中窗口 | "这句话在哪" | **≤ 600 tokens** |
| 兼容 | `read_document(path, offset, limit)`（**已有**：默认/最多 2000 行 + 20,000 字符预算） | 确实要通读 | 沿用现有 `MAX_BODY_CHARS=20_000` |

**写侧：不需要新造（这是本轮一个反直觉的发现）** —— 本地写面**已经是 patch 式**：
17 个 `KNOWN_OPS` / 16 个 `COMPILED_OPS`，含 `replace_lines`/`insert_lines`/`delete_lines`/`upsert_block`，且**要求 `expect` 逐字原文**（对不上即拒）。
证据：`ev:file:docs/design/dsh-agent-port.md#L151-L152`。
⇒ Q4 的写侧工作 = **补回执粒度**（成功只回 `{txid, files[], ±lines, undo_available}`，不回全文 diff）**+ 给每个 op 预算**，而不是设计新写工具。

**每工具预算表（初值，全部标注"未测，需 E4 测量"）**

| 工具面 | 预算上限 | 截断语义 | 失败语义 |
|---|---|---|---|
| `outline` | 800 tok | 超限按"目录前 N 层 + 其余折叠为计数" | 路径不存在 ⇒ `NOT_FOUND` + 候选名 |
| `section` | 4,000 tok | 超限切成 `part i/n` + `next=cursor` | 歧义（多节命中）⇒ 回候选列表，**不猜** |
| `snippet` | 600 tok | 只回命中窗口 | 无命中 ⇒ 回"0 命中 + 已搜范围" |
| `search_kb` | 5 命中 × 200 字符（已有 `DEFAULT_TOP_K=5`） | 超限回计数 + 收窄提示 | 空库/无索引 ⇒ 明确原因 |
| `glob` / `grep` | 100 / 250（**已有上限**） | 超限报数 + 收窄提示（**不静默**） | 无效 pattern ⇒ 语法错误定位 |
| session 查询 4 工具 | 100 命中 / before·after ≤50（**已有**） | 同上 | `session_id` 不存在 ⇒ 明确 |
| `propose_write` 回执 | 300 tok | 只回 txid/文件/±行数 | 校验失败 ⇒ 逐条 `expect` 差异（≤200 字符内给首条 + 计数） |
| 所有错误文本 | 200 字符 + 可操作提示 | — | 参照 S4：不透明错误码 = 反模式 |

**三条跨工具规则（把 N1 的记账口径变成设计约束）**：
1. **完整往返记账**（B4.f）：预算按 `system + tool schema + messages + completions` **总账**，不是 per-call；
2. **schema 固定成本必须被 `gate` 抵消**：N1 实测组 A 35 工具 = 15,220 字符 ≈ **4,349 token/会话**（`ev:bench:n1-a1-token-hypothesis#§2`）⇒
   每新增 N 个工具，必须同时给出"哪些工具因此不再默认出现"（Q3 的 `gate`），否则净增；
3. **截断必须带下一步指令**（S4 实证做法）：截断末尾给 `next=<cursor>` 或"收窄建议"，让模型一次就能收敛。

**【依赖假设】** `AS-GRANULARITY`（核心）；`AS-TOKENIZER`（N1 用 3.5 字符/token、1.5 中文字/token 的**假设**，未真测）。
**【falsifier】** 真机 E4 实测若：① 三级粒度下任务完成率下降 >10%（模型拿不到足够上下文）⇒ 默认粒度回退一级（section→document），
并把"完成率 vs token"双指标一起验收；② 若往返次数增加导致**总账**反而上升（例如 L0→L1→L2 三次调用超过一次 L3）⇒ 改为"一次性返回 outline+首节"的合并接口。
**【代价】** 若粒度切得过细：模型要多轮才拿到上下文 ⇒ 总 token 可能不降反升（**这正是 N1 静态模型没测的部分**，我把它登记为 unknown U3）。
若切得过粗：省不下来。故必须**完成率与总账双指标**验收，不能只报省。

---

## §2-Q5 trace 轨迹

**【论断】**
trace 的机制**已经存在**（会话 JSONL + `audit.py` + 4 把只读查询工具）；本轮增量**不是再造 trace 系统**，而是补三件：
① 调用级**成本字段**；② **跨进程入口**（MCP `_meta` 的 OTel 约定，仅当 MCP 立项）；③ **容量与淘汰口径**。
并明确：**trace 是 MCP 的次要理由，不是主要理由**（内部调用已可追溯，见 Q2 步 3）。

**【证据】** ① 既有机制：`ev:file:docs/design/dsh-agent-port.md#L171`（`audit.py` 的 `capability/apply|undo|redo|force_save` 追加进会话 JSONL；审批成对事件 `approval/asked|decided`）、`#L132`（4 把会话查询只读工具 + 命中上限 100 / `before|after ≤ 50`）；
② 跨进程才有的增量：`ev:spec:mcp/2026-07-28#changelog`（Minor #2：`_meta` 的 OpenTelemetry `traceparent`/`tracestate`/`baggage` 约定）；
③ 与备份/撤销联动的落点：`ev:file:src/memoria/services/agent/tools/kb.py#L4203-L4215`（`backup_txid` 可定位到可撤销批次）；
④ 独立参考实现（形态可复用、存储不可复用）：本队 DSH 侧 `team_trajectory`（Lead 转述其能力，标 `ev:lead-transcript`）。

**【记什么（每调用一条）】**
```
{ts, session_id, turn, tool_id, plan_txid?, args_digest, result_chars, est_tokens,
 truncated:bool, approval:{asked,decided}, error_code?, write:{files[], ±lines, backup_txid, undo_available}}
```
- `args_digest` 而非明文：**隐私边界**（用户库内容不得进 trace 索引）；
- 写路径额外字段与 `capability/apply` 事件对齐（`audit.py` 已有 4 类事件）。

**【存哪】**
- **唯一事实源**：沿用 `<kb>/.memoria/agent/sessions/<sid>.jsonl` 追加（不新建并行真源，符合 AGENTS.md §1）；
- **派生索引**：`<kb>/.memoria/agent/trace/index.jsonl`，**可重建**（视作 cache，不作为事实源）。

**【怎么查】**
- 已有 4 把只读工具（`session_event_search/trace/event_trace/event_read`）+ `search_sessions`（`dsh-agent-port.md#L132`）；
- 新增 1 把聚合（**不新增原始数据**）：`trace_cost_summary(scope)` → 按会话/工具/时间窗聚合 `est_tokens`、截断率、失败率、审批拒绝率。

**【容量上限与防爆炸】**

| 项 | 口径 |
|---|---|
| 每会话条数 | 5,000（超出 FIFO 淘汰**非写路径**条目） |
| 每条字节 | ≤ 2 KB（结果正文不重复存：存 `digest + 长度 + 首 256 字符`） |
| 永不淘汰 | **错误条目**与**写路径条目**（审计价值最高） |
| 分片 | 按 `session_id` 分文件，避免单文件膨胀 |
| 与 compaction 的关系 | trace 索引**不参与**上下文压缩（它不进模型上下文；不是 `compaction.py` 的对象） |

**【与 `team_trajectory` 的差异（必须说明）】**

| 维度 | DSH 侧 `team_trajectory` | Memoria trace（本设计） |
|---|---|---|
| 数据面 | **团队工作区**元数据（成员/工具调用/写入/门禁），**不含消息体** | **用户知识库**的 KB 工具调用 + 写路径审计 |
| 隐私边界 | 工作区可公开 | 用户资产：**只存 digest/长度**，不存正文 |
| 联动 | 与任务板/门禁 | 与 **backup/undo** 联动（`backup_txid` → 可撤回到该批之前） |
| 可复用 | 复用其**事件形态**（`tool_call`/`file_read`/`file_write`/`gate_run`） | 不能复用其存储与权限模型 |

**【依赖假设】** `AS-TOOLSCHEMA-COST`（`est_tokens` 的静态估算口径）；`AS-TRACE-EXISTING`（"内部 trace 已存在"—— 由 `audit.py`/session 工具支撑）。
**【falsifier】** ① 若 30 个真实会话里 `est_tokens` 与 provider 实际 usage 偏差 >30% ⇒ 静态估算不可用，改为只记字符数 + 从 usage 回填；
② 若 trace 索引被证明可重建成本过高（>5s/会话）⇒ 降级为"仅按需生成"，不常规落盘。
**【代价】** trace 越细，写入放大与隐私面越大；若我把"不存正文"定为硬约束，后续排障会缺上下文 ⇒ 缓解：错误条目允许存≤512 字符的**错误上下文**（非库正文）。

---

# §3 写侧安全（不可绕过；不接受"加个审批"这种空话）

**机制不是审批，而是"唯一写者 + 四道前置"**。MCP 化（或任何新入口）必须**逐条保持**，缺一条即否决：

| # | 前置 | 内容 | MCP 化后的硬约束 | 证据 |
|---|---|---|---|---|
| **W1** | **入口唯一** | 一切写入必须 `propose_write` → plan → compile（16 ops）→ `apply`；正文只经 `DocumentService.save_document()` | MCP 工具层**只暴露"产 plan"语义**；**禁止**暴露任何"直接写/直接 edit"工具 | `dsh-agent-port.md#L151`（"本地换了模型：不是工具直接写"） |
| **W2** | **读后写守卫** | 未读 ⇒ `FS_NOT_OBSERVED`；读后被外部改 ⇒ `FS_STALE_VERSION`（进程内、不跨会话） | 跨进程调用方必须**在同一进程内完成读-写配对**，否则拒绝 | `ev:file:docs/design/dsh-agent-port.md#L172`（`services/agent/observation.py`） |
| **W3** | **写前备份 + 可撤销** | apply 第一步 `backup.snapshot_pre_images()`（任何落盘之前，失败即整批不写）；`restore_batch()` fail-closed | 任何新入口**不得**绕过 backup 直达文件系统；不得自造备份格式 | `ev:file:src/memoria/services/agent/tools/kb.py#L4203-L4215` |
| **W4** | **审批在分发前** | `approvals.py` 在工具分发前询问；无应答者 = `UNAVAILABLE` = 失败关闭 | 外部调用方**不得自带 `auto`**：`permissions.write` 非空 ⇒ `approval ≠ auto`（契约硬校验） | `dsh-agent-port.md#L161`、`agent-plugin-design.md#L24-L28` |

**被明确拒绝的架构（写下来，防止下轮被重新提出）**：
> "给 MCP 一个 `write`/`edit` 工具，内部直接落盘，再加审批挡一下" —— **无论加多少审批都不接受**。
> 理由：那会让事实源出现**第二个写者**，`backup/undo/审计/读后写守卫` 全部退化为例外路径。

**可测断言（供实现阶段判红）**：W1 MCP 写链上必须出现 `txid`；W2 无 `approval/decided` 却落盘 = FAIL；
W3 每批写入必须能 `restore_batch` 到 pre-image（逐字节）；W4 外部调用 `approval=auto` 且 `permissions.write` 非空 ⇒ 装载期即拒绝。
**边界不放宽**：`shell_exec` 的"cwd 必须落在库根内"（`realpath` 前缀校验）不得因 MCP 化放宽 —— `ev:file:src/memoria/services/agent/shell_exec.py#L9-L18`。

---

# §4 覆盖面三表（对 `freeze-v2.json::expected_categories` 的 10 项构成分割）

> **机器可校验格式**（PROTOCOL P2(b)）：下面 JSON 即三表本体，`checked ∪ not_examined ∪ out_of_scope == expected_categories` 且两两不相交。
> 每条 `checked` 都带 `check_cmd`，供 **P2(d) 抽查**（裁决可随机抽 N=3 条直接跑）。

```json
{
  "freeze_ref": "artifacts/agent/verify/debate/freeze-v2.json#expected_categories",
  "checked": [
    {"cat": "DSH 能力模型（skill/hook/guard/plan/goal/todo）", "evidence": "ev:file:docs/design/dsh-agent-port.md#L94-L193、#L185", "check_cmd": "Select-String -Path docs/design/dsh-agent-port.md -Pattern 'hooks|guard|goal|todo' | Measure-Object", "verdict": "已判定：skill 吃；hooks/guard/plan-mode/goal/todo + todo_write + 工具管线扩展点 属缺口"},
    {"cat": "DSH 宿主运行时（Cordis 服务/lifecycle/scoped layers）", "evidence": "ev:file:docs/design/dsh-agent-port.md#L105、#L107", "check_cmd": "Select-String -Path docs/design/dsh-agent-port.md -Pattern 'Cordis' | Measure-Object", "verdict": "已判定：registry/initiator/投影框架/telemetry 不吃；只取 scoped 可见性 + dispose 两条语义"},
    {"cat": "DSH 自用技能内容（.agents/skills 的 dsh-* 类）", "evidence": "ev:file:src/memoria/services/agent/skills.py#L1-L19、dsh-agent-port.md#L179", "check_cmd": "Select-String -Path src/memoria/services/agent/skills.py -Pattern '0d1f5000' | Measure-Object", "verdict": "已判定：内容不移植；装载协议已落地（pin + 逐条规则 + 6 条偏差）"},
    {"cat": "MCP 协议（tools/resources/prompts/transport/版本）", "evidence": "ev:spec:mcp/2026-07-28#changelog、ev:bench:n1-a1-token-hypothesis#§4", "check_cmd": "Get-ChildItem src -Recurse -File | Select-String -Pattern 'jsonrpc|tools/list|mcpServers' | Measure-Object", "verdict": "已判定：协议 2026-07-28 无状态化；MCP 化不省 token（A1 证伪）"},
    {"cat": "Memoria 现有 agent 工具面（kb.py / registry）", "evidence": "ev:file:src/memoria/services/agent/tools/kb.py#L2867（35 工具/build_kb_tools）、registry.py#L102-L118", "check_cmd": "(Get-Item src/memoria/services/agent/tools/kb.py).Length", "verdict": "已判定：304,374 B 单文件；35 工具；registry 有 Tool/invoke 管线但无扩展点"},
    {"cat": "token 经济（schema 开销/往返/错误路径/截断语义）", "evidence": "ev:bench:n1-a1-token-hypothesis#§2-#§4", "check_cmd": "Get-Item artifacts/agent/verify/debate/n1-a1-token-hypothesis.md | Select-Object Length", "verdict": "已判定（directional）：schema 固定成本 ≈4,349 tok/会话；省耗主因=粒度"},
    {"cat": "写侧安全（propose_write→审批→备份→撤销）", "evidence": "ev:file:src/memoria/services/agent/tools/kb.py#L4203-L4215、dsh-agent-port.md#L151、#L161、#L170-L172", "check_cmd": "Select-String -Path src/memoria/services/agent/backup.py -Pattern 'snapshot_pre_images|restore_batch' | Measure-Object", "verdict": "已判定：唯一写者 + 读后写守卫 + 备份/撤销 + 分发前审批，四道齐全"},
    {"cat": "扩展点契约（字段/版本/沙箱边界/兼容）", "evidence": "ev:file:src/memoria/services/agent/plugins.py#L4-L14、docs/design/agent-plugin-design.md#L12-L28", "check_cmd": "Get-Item src/memoria/services/agent/plugins.py | Select-Object Length", "verdict": "已判定：声明面存在（6 字段 + 原语目录 + gate）；缺工具面扩展点"},
    {"cat": "trace/轨迹（记录什么/存哪/查询/容量）", "evidence": "ev:file:docs/design/dsh-agent-port.md#L132、#L171、src/memoria/services/agent/audit.py", "check_cmd": "Select-String -Path src/memoria/services/agent/audit.py -Pattern 'capability/' | Measure-Object", "verdict": "已判定：机制已存在（session JSONL + audit 4 类事件 + 4 把查询工具）+ 本文件 Q5 给增量；**盲区已声明**：未读 DSH 侧 `team_trajectory` 实现，'可复用事件形态'基于二手描述"}
  ],
  "not_examined": [
    {"cat": "Memoria 知识库数据形态（md/frontmatter/graph/sidecar）", "reason": "本轮只引用了 AGENTS.md 的事实源表，未逐字段检查 frontmatter/sidecar/graph 的数据形态", "impact": "Q4 的 section 粒度依赖 heading/KP range 的可用性；若 sidecar range 解析不可靠，L1 section 会退化为整篇", "owner_to_check": "agent-arch（下一轮，或指派 kp-owner）"}
  ],
  "out_of_scope": []
}
```

**分割性声明**：
- `checked` 9 项 + `not_examined` 1 项 = **10 项** = `expected_categories` 全量；两两无交集；`out_of_scope` 为空集（理由：10 项全部属于本立场书范围。若裁决认为某项越界，我接受移入并重算，不辩）。
- **已用脚本机械校验**：`checked ∪ not_examined ∪ out_of_scope` 的字符串与 `freeze-v2.json::expected_categories` **逐字相等**（`extra: [] / missing: []`，无重复）。
- **盲区声明位置**：trace 类目的盲区（未读 `team_trajectory` 实现）写在 `checked[8].verdict` 里，而非单列 —— 因为该类目我**确实检查了**（Q5 有结论），只是有一个具名子项没读。这是我理解的 P2(b) 正确用法：**不把"没查透"写成"没查"**，也不把"查过"写成"查透"。
- **未做**：把"我检查过"写成"我证明了无遗漏"（P2(a) 禁止）。上面每一项都是"我检查了这个类目并给出结论"，不是"这些类目全部正确"。

---

# §5 风险与代价（P1 对称举证：我先给自己的方案挑毛病）

| # | 最坏会发生什么 | 后果等级 | 缓解手段 | 我的证据弱点 |
|---|---|---|---|---|
| **R1** | 我判"Q2 推后 MCP"是**错的方向判断**：外部 agent 接入其实是产品主线，推后等于错过窗口 | 高（战略） | 条件化交付规则（M-1/P-1）：facade 先行使补 transport 成本低；X-1 给退役机制；我**执行人的决定** | 我没有外部需求的一手证据（只有"人说了要 MCP"这一组织事实） |
| **R2** | 三级粒度**降低任务完成率**：模型拿不到足够上下文，迭代更多轮，总账反而上升 | 高（产品） | 双指标验收（完成率 + 总账）；默认粒度可回退一级；合并接口（outline+首节一次返回） | N1 是静态记账模型，**未计往返轮数**（已登记 U3） |
| **R3** | 我的 `est_tokens` 静态估算系统性偏差，导致预算表全是装饰 | 中 | 预算只作**相对约束**，绝对值等真机；偏差 >30% 即改口径（Q5 falsifier） | N1 的 tokenizer 口径是假设（3.5 字符/token） |
| **R4** | **三表漏类目**（我没想到的类目），表现为"看着覆盖了其实没有" | 中高 | 已登记 2 项 `not_examined`；接受 P2(d) 抽查；请 arch-contract 专门攻"你还漏了什么类目" | 这正是 PROTOCOL §10 承认防不住的"全员都没想到" |
| **R5** | 我**继承了 `dsh-agent-port.md` 的陈旧事实**（该文档部分行已过期，如称 `capabilities.json` 零命中但 `plugins.py` 已实现） | 中 | 对结论性行做独立复核（§4 每条给 `check_cmd`）；在文中显式标注 `AS-PORT-LEDGER` 假设 | 我未通读 361 KB 全文档，只精读 §5 与相关小节 |
| **R6** | 按 MCP **2026-07-28** 设计契约，但外部客户端还停在旧版（2025-06-18 / 2025-11-25） | 中 | 契约只用 tools/resources/prompts 的**稳定子集**；不依赖新特性（discover/subscriptions） | 我无法验证生态采纳率（无网络测量） |
| **R7** | 我建议"不做 MCP 主线"被读成**消极/抗命** | 中（协作） | 明确写：若人拍板做，我按 §7 override 全力执行，并给退役条件；这不是拖延，是把不可逆决定推后 | — |
| **R8** | 把 token 预算写成契约字段（`budget`）会**提高第三方写插件门槛**，压制扩展生态 | 低中 | `budget` 给默认值；`schema_ref` 由装载器自动生成；插件只需声明 `tool_id` | 无第三方生态数据可参考 |

---

# §6 unknowns（每条必须绑 `if_true_then`；写不出者不享受 P4 豁免）

| ID | 未知 | 若为真，我的方案如何变（if_true_then） |
|---|---|---|
| **U1** | pin `0d1f5000` 之后上游 `skill-filesystem` 改 3 次、`tool-skill` 改 2 次，这些变更是否改变 T1–T4 的等价性 | 若改变语义 ⇒ Q1 的"全量"必须先做**上游 diff + 重新对齐**，且 Q4 的粒度接口要按新语义重估；若只是内部重构 ⇒ 只更新 pin，不需重做 |
| **U2** | Cordis 的 **scoped layers / dispose** 在 Memoria 单进程里是否有真消费者 | 若无 ⇒ Q1 ② 连"两条契约语义"也不必取，宿主运行时整类判为"不适用"（进一步简化）；若有（如未来多插件）⇒ 必须把它们做成 `lifecycle` 契约字段（Q3 已预留） |
| **U3** | 大库（2530 KB）下，L0→L1→L2 的**多轮往返次数**是否反而使**总账**高于一次整篇读（N1 静态模型未计轮数） | 若为真 ⇒ Q4 改为"合并接口优先"（一次返回 outline + 首节），并把默认粒度从 section 上调；Q4 的预算表整体重算 |
| **U4** | 真实 tokenizer 与 N1 的假设（3.5 字符/token、1.5 中文字/token）差异多大 | 若偏差 >30% ⇒ 所有预算表的**绝对值**作废，只保留相对排序；Q4/Q5 的成本字段改用 provider 回填 |
| **U5** | 是否存在**真实外部客户端**接入需求（决定 M-1 触发条件是否成立） | 若存在 ⇒ Q2 从"推后"翻为"立项"，且形态按 D-1（最小集 + gate + 按需结构化）；若不存在 ⇒ 保持"facade 先行、server 不做"，并把该判断写入设计文档 |
| **U6** | `propose_write` 的回执当前是否回**全文 diff**（决定写侧回执改造量） | 若是 ⇒ Q4 写侧需要改造（回执粒度化，工作量 1 处）；若否 ⇒ 写侧零改造，只需补预算 |
| **U7** | 我的三表是否还有**未登记类目**（P2(a) 允许盲区，但盲区必须登记） | 若被指出存在未登记类目 ⇒ 记 `coverage_gap`，我接受降级（该结论标 `有条件成立`），并把该类目补进 `not_examined` 后重提 |

---

## 附：本文件的自我审查（P1 对称举证：先给自己的 §0/§1 挑毛病）

| # | 我的弱点 | 如果有人这样攻我，我怎么答 |
|---|---|---|
| 1 | §0.1 大量依赖 `ev:lead-transcript`（库规模、pin 日期、上游变更次数），**本轮未独立复核** | 承认这是 B 级证据；处置：已单列 §0.7，且这些事实**不承载判决**（判决靠 §0.2 的四条否定 + §0.1 的实测行）。若 Lead 要，我可以下次独立复核 pin 与包数 |
| 2 | §0.5 的三分类判决**有解释权风险**：人只说了"能力模型"，我据此把"宿主运行时"排除在外，可能被认为在收窄任务 | 我的判决是**可反驳的**：若人能指出"能力模型"包含 Cordis 运行时，我立刻改判。我已把判据写在 §0.2 四条否定上（不是口味），并给出"若判错"的后果（§0.7 + §2-Q1 的代价栏） |
| 3 | §1 三个来源**没有一个是"Memoria 这类系统的 A/B 测量"** | 接受。这正是 PROTOCOL §10 承认的局限（防不了"全员都没想到"）；我能做的是把每源的**局限**写出来（§1.1-§1.3 末段），而不是假装它们证明了更多 |
| 4 | S2 是 AGPL 产品 README，**商业色彩** | 已标局限；只用其接口清单与设计选择，且明确"不复制代码"。若评审认为产品文档不可作来源，我可以替换为 `modelcontextprotocol/servers` 的 memory server 源码（同类第二候选），但需重新 fetch 验证 |
| 5 | S3 与"知识库维护"任务分布不同，**外推有风险** | 已标；我只用它证"方向存在"，并把"28.4% 不可移植"写明 |
| 6 | §0.6 的 T1–T4 目前是**判据设计**，还没跑过任何一条 | 承认。它们的作用是给 §4 三表与 §2 论断一个**可判红**的靶子；跑通属实现阶段。若评审要求现在就给出至少 1 条已跑的 T，我会先做 T2（`skills.py` 的发现/负例最便宜） |

> **本文件不写产品代码、不改 `src/**`、不 commit。**
> **待补（非阻塞）**：§4 的 1 项 `not_examined`（知识库数据形态完整语义）在实现阶段前补齐；
> §6 的 U1–U7 需要实测/指派检验者后才能收敛。参见 §4 的 `check_cmd` 供 P2(d) 抽查。
