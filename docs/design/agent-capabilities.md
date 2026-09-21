# 工具与能力包路线图（产品内 Agent）

> **用途**：把"让 agent 真正智能"的四条能力线（**W 写能力 / N 联网收集 / S skill 机制 / H 宿主接口**）与两条横向约束（**token 预算与工具元层 / 基准测试集**）收敛成**可施工的阶段表与验收口径**。
> **关系**：调用面（循环、会话、工具注册表、只读工具、压缩/裁剪/标题/会话检索）已在 [dsh-agent-port.md](dsh-agent-port.md) 的 M1–M2 落地；本文只接它的 **M3（写能力）与 M4（对外契约）** 并展开。基准方法论复用 [maintenance-benchmark.md](maintenance-benchmark.md)（分层采集 / 确定性语料 / A/B 与门禁）。
> **状态**：待评审（2026-09-19 初版；**2026-09-20 完善 M3**：把写能力提升为「可插拔能力插件」契约的第一个消费者，四条线由此共用同一装载器，见 §2）。**实施状态的唯一来源是 [../todo.md §13](../todo.md) 的条目 ID**（本文不复制状态，遵守 [ledger-maintenance.md](../conventions/ledger-maintenance.md) 规则 1.2）。

---

## 0. 三条红线（不因本路线图放宽）

| 红线 | 本路线图的落法 |
|---|---|
| **离线优先** | 只有 **N 线**引入出网，且**逐次显式**（默认只读、默认关；见 §3.1） |
| **禁止 silent 写入** | **W 线**一律"提议 → 逐条确认 → 应用"，且只走既有服务层（§2.3）；**任何一次拒绝都不改盘**。**2026-09-20 加强**：该红线改为在**插件边界物理可证**——插件不含可执行体、核心写原语是唯一写者、落盘前做 realpath 前缀校验（§2.3.1）；**写前必留 pre-image、备份失败即不写**（§2.3.2）；**2026-09-20 二次加强**：写工具的接口形态定为**计划 API + 编译器**——领域动词**只产出声明式 plan**、不落盘，plan 的校验/预览与人类 UI **同一套校验器**（§2.3.3 / §2.3.4） |
| **单一事实源** | 能力包（skill / 能力插件）、工具元数据、基准产物都要先登记进事实源表，禁止并行副本；**M3 新增的库级注册文件** `<kb>/.memoria/agent/capabilities.json` **须由人登记进 [AGENTS.md §1](../../AGENTS.md)**（见 §2.2） |

---

## 1. 现状：调用面已具备，能力面极窄

| 能力 | 现状 | 缺口 |
|---|---|---|
| 只读知识库 | ✅ 六个工具：`search_kb` / `read_document` / `read_kp` / `kb_overview` / `validate_kb` / `search_sessions`（`services/agent/tools/kb.py`，零写入守卫 `kb_read_only`） | — |
| **文件增删改** | ❌ | W 线：写工具 + 审批 + 回滚（**M3 起统一为「能力插件」形态**，见 §2） |
| **建点 / 连边 / 改边类型** | ❌（只有 UI 手工入口：KP 面板、图谱面板） | W 线：同上；边类型改写在 sidecar 的 `links`/`edges` 面，需处理"边类型迁移"与既有 `path_cascade` 的边界 |
| **联网资料拉取与收集** | ❌（只有"出网开关 + 自配模型端点"） | N 线：检索/抓取 + 落 `pending` 的收集链路 |
| **用户自定义能力包** | ⚠️ 只有 `.memoria/agent/**` 的**指令文件**（语义上"只加上下文、不加工具"） | S 线：声明式 skill（发现/注入/权限/版本） |
| **程序接口给 agent** | ❌（RPC 面只服务"人点 UI"；`AskJobManager` 单飞，无后台服务） | H 线：宿主能力（agent→程序 与 程序→agent 两个方向） |
| **工具使用与 token 的度量** | ⚠️ `scripts/benchmark/usage/report_usage.py`（只扫 `loop/end`） | 横向 A/B：记账口径不全 + 缺工具选择质量指标 + 缺任务级口径 |

> 一句话：**现在 agent 只会"读"，不会"写"、不会"上网"、不能"被扩展"、不能"主动"**——这四条线补齐，才谈得上"程序的灵魂"。

---

## 2. 能力线 W：写能力 —— 第一个**可插拔能力插件**（M3 完善设计）

> 用户口径（2026-09-20）：「M3 需要完善设计，做成可插拔的机制」。本节因此**不只是**写工具清单：先把 **W/N/S/H 四条线共用的「能力插件契约」**定下来（2.1–2.2），再把**写能力作为该契约的第一个消费者**落地（2.3–2.4），最后说明四条线如何各自成为**同一条契约下的插件族**（2.5）与分期验收（2.6）。
> **契约的模板**是 [AGENTS.md §6](../../AGENTS.md) 的 Agent 注册条目（声明式条目 + 单一注册文件 + 权限显式；**"禁项显式"/"提示词独立文件"两项已随本轮收缩移出 v1**，见 §2.1「暂缓字段」），实样见 `artifacts/agent/agents.json`；差别只在"扩展的是**产品内对话 Agent 的工具面**"而不是"仓库协作 Agent 的派发面"（边界措辞见 [dsh-agent-port.md §10](dsh-agent-port.md) 的待人工改动项）。

### 2.1 插件能力契约（capability plugin contract）（契约正文已迁出本文）

> **契约正文已迁出本文**：字段集、暂缓字段、上游对照与待讨论项统一见 **[agent-plugin-design.md](agent-plugin-design.md)**（**唯一事实源**，活文档、由人逐步对齐）—— 本节不再复制字段表（禁并行事实源）。
> **本文自 2026-09-20 起不再是事实源**：**契约与相关设计（含写场景清单、注册装载、写管线、计划 API、权限越界、备份撤销、M3 分期）一律以 [agent-plugin-design.md](agent-plugin-design.md) 为准**；本文降级为**历史 / 路线图**，其 M3 部分将由人逐步迁入该文（迁移清单见该文 §6），冲突处一律以该文为准。
> 本节只保留**模块侧**内容：注册与装载（§2.2）、写管线与计划 API（§2.3）、权限与越界（§2.4）、四线落法（§2.5）、M3 分期（§2.6）。**本文其余各节原引 `§2.1` 的字段表 / 暂缓清单 / JSON 实样，一律以该文为准**：`provides.tools[]` 的 `constrain`/`gate` 属判断项、可再收紧（该文 §4 Q2），`approval` 的**安全下限**（`permissions` 含 `write` ⇒ 不得为 `auto`）与全部字段的**校验规则**也由该文定义。

字段之外还有**一条铁律**（2.2 会反复引用，v1 不变）：**插件目录内不含可执行代码**（无 `.py` / `.js` / 脚本），只含**声明 JSON + 只读资源**。

#### 2.1.1 三层术语（原语 / 领域动词 / 技能）

> 用户口径（2026-09-20）：接口分**三层**、走**一条管线**；铁律是 **领域动词只产出 plan，不直接写盘**。

| 层 | 是什么 | 谁定义（唯一来源） | 有无执行体 | **产出** |
|---|---|---|---|---|
| **原语 primitive** | 核心内置的**写工具体**（`tool_id` 的落盘实现）；内部只调服务层公开入口（§2.3.1） | 核心：`provides.tools[].tool_id` 的**取值目录**（M3a 一次性加进原语目录） | ✅ 有（在**核心**内，不在插件目录） | **落盘**（只经 apply 入口 + 写前备份，§2.3.2） |
| **领域动词 tool** | 插件声明挑用的那个 `tool_id` 的**模型可见调用面**（同一 id，经 `constrain` 收紧 + `gate` 门控）；即 `provides.tools[]` 的条目 | 插件声明 `resources/agent-capabilities/<id>.json` | ❌ **无代码**（只声明） | **plan（声明式，不落盘）**（§2.3.3） |
| **技能 skill** | 用户自定义能力包（`SKILL.md` + `manifest.json`，§4.2；即**用户技能类**插件） | 用户：`<kb>/.memoria/agent/skills/**` | ❌ **无代码** | 提示注入 + 声明领域动词（同样只产 plan） |

**一句话**：**模型调领域动词 → 得到 plan → 编译器（§2.3.4）把 plan 编成对原语的有序调用 → 只有编译器在 apply 入口落盘**。三层里模型只见"领域动词"、用户只见"技能"，**代码只存在于核心**。

### 2.2 注册与装载

- **两个位置，职责分开**（沿用既有的"程序读取源 vs 库内事实源"分工）：
  1. **插件声明（随版本分发，只读）**：`resources/agent-capabilities/<id>.json` —— 与 `resources/agent-prompts/**` 同级的**程序读取源**，不含可执行代码；
  2. **库级启用与参数（随库走，用户可改）**：`<kb>/.memoria/agent/capabilities.json` —— **单一注册文件**（形态对齐 `artifacts/agent/agents.json`）。**该文件是新增事实源，须由人登记进 [AGENTS.md §1](../../AGENTS.md) 单一事实源表**（Agent 只读那张表；先例见 [dsh-agent-port.md §10](dsh-agent-port.md) 的 P3 会话目录）。
- **发现顺序**（顺序确定，冲突即失败）：① 内置声明按 `id` 字典序加载 → ② 用 `<kb>/.memoria/agent/capabilities.json` 的 `enabled[]` 求交集与启用位（**条目存在即启用**，§2.1）→ ③ `id` 未在声明里出现 / **v1 字段校验不过**（§2.1 字段表的"校验规则"列）⇒ **该条不装载 + 一条可见告警**，其余照常（**装载 fail-soft，执行 fail-closed**）。
- **冲突与重名**：
  - 两个声明同 `id` ⇒ 装载失败；
  - 两个插件声明**同一 `tool_id` 的同一动作类** ⇒ 装载失败（沿用 `ToolRegistry.register()` 的既有语义：重名 `raise ValueError`，`services/agent/tools/registry.py:207`、`:212-213`）；
  - `tool_id` 与原语目录不一致（未知动作）⇒ 拒绝该 `tool_id`，不静默降级。
- **不变量「新增插件不改核心」**：装载器落地（M3a）之后，新增一个插件 **不得**改动下列任一文件 —— `services/agent/tools/registry.py`、`services/agent/tools/kb.py`、`services/agent/approvals.py`、`services/agent/ask.py`、`services/agent/llm/config.py`、`presentation/api/ui.py`、`services/document.py`、`storage/{sidecar,manifest,pending}.py`。新插件只需**一处新增**：`resources/agent-capabilities/<id>.json`（**只写 v1 字段集**；提示词段落属暂缓字段，见 §2.1）；库级只改 `<kb>/.memoria/agent/capabilities.json`。
  - **为什么不需动 `llm/config.py` 的键白名单**：库级启停状态落在**另一个文件**（`.memoria/agent/capabilities.json`），因此 `_WRITABLE_KEYS`（`services/agent/llm/config.py:87`）与全局 `config/agent.json` 的键集**不变** —— 避免了"per-KB 状态挤进全局配置"（全局/库级的分工口径见 [dsh-agent-port.md §10](dsh-agent-port.md) 的 P4）。
- **工具原语（primitive）的归属**：`tool_id`（如 `kb.kp.create`）背后的**工具体**属**核心原语目录**，由 M3a 一次性加进目录（内部只调 `DocumentService` / `storage/**` 的公开入口，见 2.3.1）；插件只能**挑用 + 收紧参数 + 声明权限**，不能新增工具体。这条就是"物理上不能越界"的**根**：**插件不带代码 ⇒ 没有 `open(...,"w")` 的机会**。三层术语见 §2.1.1：插件挑用的 `tool_id` 是**模型可见的领域动词**，其产出是 **plan**（不落盘）；落盘只发生在编译器的 apply 入口。
- **UI/RPC 面**：`UIAPI` 的公开方法即 RPC（`src/memoria/app/shell/pywebview.py:477` 的 `js_api=api`）。装载器只新增**一个通用网关方法**（如 `agent_capability_call(id, action, payload)`）+ 既有的配置读写面，**不按插件新增具名方法** —— 否则每加一个插件就要改 `presentation/api/ui.py`，与"不改核心"矛盾。

### 2.3 写管线（propose → dry-run diff → 逐条确认 → apply → 审计 → 撤销）

| 步 | 做什么 | 落在哪（**已存在**的接入口） |
|---|---|---|
| 1 **propose** | 模型调用写工具 ⇒ **只产 plan**（`{v,txid,intent,ops[]}`，§2.3.3）、不落盘。提议卡片 = `intent` + 由 `preview_plan`（§2.3.4）算出的影响文件/行清单 | 写工具声明 `read_only=False`（`services/agent/tools/registry.py:114`）⇒ 必过审批 |
| 2 **dry-run diff** | 应用前算出"将改哪些文件、哪些行"：已有文件在**临时副本**上真跑一次并算 diff，新建/删除给整段或整文件 | 取原文用 `DocumentService.load_document()`（`services/document.py:1271`）；diff 只在内存/`tempfile` 临时目录算 |
| 3 **逐条确认** | 逐条 ✓/✗；**未获批 = 不执行**（无应答者也拒） | `ToolRegistry.invoke()` 在**分发前**问策略（`registry.py:265-288`）→ `ApprovalPolicy.decide`（`services/agent/approvals.py:109-115`）→ 应答者走 `AskPolicy(answerer=…)`（`approvals.py:127-152`），无应答者 ⇒ `unavailable` ⇒ 拒绝 |
| 4 **apply** | 获批后**先取写前 pre-image（§2.3.2）**，再**一次性**转调既有服务层：原子写 → 索引失效 → manifest/sidecar 同步 → pending 同步 → KP 重锚 | 见 2.3.1、2.3.2 |
| 5 **审计** | 追加事件 `capability/proposal` / `capability/apply` / `capability/reject`（含插件 id、`tool_id`、逐文件 ±行、幂等键、决定与时间；**plan 架构下另含 `plan.v` / `txid` / `intent` / 逐 `op_id`**，§2.3.3） | 会话 JSONL `<kb>/.memoria/agent/sessions/*.jsonl`；**纯追加**，旧读者对未知 `type` 一律跳过（`services/agent/session/history.py:261-299`）⇒ **不 bump** `SESSION_FORMAT_VERSION`（同 [dsh-agent-port.md §6.8](dsh-agent-port.md) 的 compaction 口径） |
| 6 **撤销** | 同一会话内"撤销上一次 apply"，数据面见 §2.3.2、选项见 §10 P10 | 按**写前快照**（§2.3.2）逐字节回滚；审计事件只作可回放证据，不作唯一回滚源 |

**统一形态的四条不变口径**（承 §2 初版，未放宽）：

- 模型**不直接写盘**：写工具只产**提议**，人在面板上**逐条确认**后才应用；
- 一次确认 = 一个**事务**：应用前取受影响文件的**写前快照**（pre-image，口径见 §2.3.2），任一步失败即**整批回滚**；
- 提议**可读**：每条带"人话一句 + 影响文件 + 前后差异"；
- **不做**"模型自动应用"（M3 不做，见 2.6）；也不做"按规则批量自动应用"（留到基准能证明安全之后）。

#### 2.3.1 「禁止 silent 写入」在插件边界的落法（唯一写者）

红线出处：[designV0.md:911](../designV0.md)（"所有结果 **提议 → 用户确认**，禁止 silent 写入"）与 [`designV0.md:254`](../designV0.md)（"**禁止静默写入**"）。落到**插件边界**＝三层同向：

1. **没有代码 ⇒ 没有写入口**：插件目录不含可执行体（2.2 铁律），所以插件在物理上没有 `open(...,"w")` 的机会；它只能"挑用核心原语 + 声明权限"。
2. **核心写原语是唯一写者**：每个写原语内部**只许**调既有服务层的公开入口 —— 正文 `DocumentService.save_document`（`services/document.py:317`，tmp + `os.replace`）与 `DocumentService._write_body`（`:2064`）；sidecar `storage/sidecar.py:120 save_sidecar_for_md`；manifest `storage/manifest.py:178 touch_manifest_entry` / `:102 flush_manifest_deferred` / `:136 save_manifest`；pending `storage/pending.py:273 sync_pending_for_file`。**原语之外不允许任何模块落盘**（本节 §2.3 初版口径不变：`open(...,"w")` 直接落盘即违规）；**且原语的调用者唯一 = apply 入口**，写前 pre-image 是该入口的第一步（§2.3.2）⇒ agent 路径上"无备份的写入"不存在。
3. **写前必过滤、写后必自证**：原语在落盘前用 `permissions.write` 的 glob + `os.path.realpath` 做前缀校验（2.4）；落盘后由门禁做**逐文件 SHA256 全等**比对（拒绝/失败 ⇒ 全等；成功 ⇒ 差异只出现在人确认过的那几条）。

> 一句话：`禁止 silent 写入` 不再只靠"施工纪律"，而是**结构上可证**——插件无代码、写原语唯一、路径校验前置。

#### 2.3.2 备份（写前 pre-image）与撤销的数据面

> 用户口径（2026-09-20）：「写入技能还需要有备份机制」。本节把 §2.3 第 4 步（apply）与第 6 步（撤销）之间的**数据面**定死：写前留 pre-image、撤销按它**逐字节**回滚、保留与清理有数字口径，且全程**不静默**。

**1. 时机与粒度**

| 维度 | 口径 |
|---|---|
| 时机 | **apply 之前**（获批后、任何落盘之前）：先 pre-image，后写；失败即**不落盘** |
| 粒度 | **单文件 pre-image + 每轮一个批次快照**（两者结合）：批次 = 一次确认 = 一个事务 = 一个 `txid`；批内含该事务**受影响文件集**的逐文件整字节副本 |
| 受影响文件集 | 该事务会碰的全部文件 —— 正文 `.md`、其 sidecar、`.memoria/manifest.yaml`、`.memoria/pending.json`（即 §2.3.1 四个写原语的**全部**落盘目标） |
| **新建文件** | 也留一条记录但**不留字节**：journal 记 `{"existed": false}` ⇒ 撤销 = **删除**该文件（避免 0 字节副本与"空文件"歧义） |
| 删除文件 | 与新建对称：记 `{"existed": true, sha256, bytes}` ⇒ 撤销 = 从副本写回 |

**2. 存哪、命名、格式**

- **目录**（随库走，与 `.memoria/agent/**` 既有布局对齐）：`<kb>/.memoria/agent/backups/<session_id>/<txid>/`
  - `<session_id>` 复用会话 id（`session-<UTC 时间戳>Z-<hex8>`，`services/agent/session/store.py:69`；字符集只含字母数字与 `. _ -`，可安全做目录名）；
  - `<txid>` = 批次 id：`<UTC 时间戳>-<两位序号>`（如 `20260920T021100Z-07`），同会话内单调递增 ⇒ **字典序即 FIFO 顺序**。
- **批次内命名**：
  - `journal.json`：批次清单 `{txid, session_id, ts, plugin, tool_id, files:[{rel_path, existed, sha256, bytes, too_large}]}`；自身走 tmp + `os.replace`，**先于 apply 落盘**；
  - `files/<原相对路径>`：逐文件**整字节**副本，**按原目录结构镜像**（如 `files/.memoria/sidecars/a.md.memoria.yaml`）⇒ 人可核对、无命名冲突。
- **格式取舍：原字节复制（不存 diff/patch）**
  - 支持理由：§2.3.1 的四个写原语**全部是整文件重写**（`save_document` `services/document.py:317` 的 `open(tmp,"w")` + `os.replace` `:342-347`；`save_sidecar_for_md` `storage/sidecar.py:120` → `atomic_write_yaml` `storage/atomic_yaml.py:46`；`touch_manifest_entry` `storage/manifest.py:178` → `save_manifest` `:136`；`sync_pending_for_file` `storage/pending.py:273` → `save_pending` `:91`）⇒ pre-image 天然就是"整份旧文件"；
  - 二进制/超大文件：字节副本对二进制安全；diff 文本化会引入编码与换行风险 ⇒ **diff 只用于给人看的 dry-run（§2.3 第 2 步），不进备份存储**；
  - **编码/换行保真**：字节副本 ⇒ 逐字节原样；撤销用 `os.replace` 覆盖，**不重新编码、不规范化换行**；
  - **上限（fail-closed）**：单文件 > **8 MiB** 或单批 > **32 MiB** ⇒ 该次 apply **预检失败、不落盘**（可见报错），**不**降级为"无备份的写入"。

**3. 保留与清理（数字口径）**

| 项 | 数值 | 说明 |
|---|---|---|
| 每会话保留批次数 | **5** | 足够"撤销上一次"及其前几批回退 |
| 每库保留会话数（备份目录） | **10**（按最新修改优先） | 超出按 FIFO 淘汰最旧会话的备份目录 |
| 每库备份总字节上限 | **64 MiB** | 超限按 FIFO 淘汰最旧批次 |
| 单文件 / 单批上限 | **8 MiB / 32 MiB** | 见上；超限即预检失败（拒绝该次 apply） |

- **淘汰顺序**：FIFO（按 `<txid>` 时间戳，最旧先淘汰）。**不变式：淘汰永不删除"当前会话的最新批次"**（= 尚未撤销的最新批次）—— 撤销可用性的底线。
- **清理时机**：① apply 成功、审计落盘后**机会式** trimming（只列备份目录，不扫库）；② 打开库时；③ 关库时。**读/查询热路径不触发**（见第 6 条）。
- **不静默**：每次淘汰追加 `capability/backup` 事件 `{action:"evicted", batches:[], bytes_freed}`；**备份失败 ⇒ 不 apply**（fail-closed）—— 追加 `{action:"failed", reason}` 后当面报错，**不**沿用既有 `write_backup` 的 fail-open（见第 6 条）。

**4. 与「唯一写者」的绑定点（调用序）**

备份是 **apply 入口的第一步**；apply 入口是 agent 写路径上**唯一**能到达 §2.3.1 四原语的通道：

```
apply 入口（核心，M3a）
  1. 路径校验（realpath 前缀；§2.4）—— 越界即拒，此时尚未建任何备份
  2. snapshot_pre_images(tx)   → tmp 建 <txid>/files/** + journal.json（os.replace）
  3. 任一步失败 ⇒ 删该 <txid> 残目录 + capability/backup{failed} + 返回（**零部分写**）
  4. DocumentService.save_document()    services/document.py:317
  5. save_sidecar_for_md()              storage/sidecar.py:120
  6. touch_manifest_entry()             storage/manifest.py:178
  7. sync_pending_for_file()            storage/pending.py:273
  8. 审计 append（capability/apply，含 backup{txid, dir, files}）
  9. 机会式 trimming（§2.3.2 第 3 条）
```

**插件为何绕不过**：① 插件目录不含可执行体（§2.2 铁律）⇒ 没有 `open(...,"w")`，也没有直呼上述四个函数的通道；② §2.3.1 已收紧"原语之外不允许任何模块落盘"，本节再加一条**原语的调用者唯一 = apply 入口**；③ 插件的 `permissions.write` 是**白名单**且**不含** `.memoria/agent/backups/**`（**白名单不含即不可触达**；`forbidden` 属 §2.1 暂缓字段，此事由白名单结构保证）⇒ 它既写不了、也删不了备份。⇒ agent 路径上"无备份的写入"不存在。

> **边界（如实说）**：**人机 UI 直存**（用户点保存、确认 KP 等既有链路）不属 M3 能力插件路径，本轮**不**纳入统一备份；它们沿用 designV0 §6.6 L2 的可选增强（见第 6 条），不在 M3a 门禁内。

**5. 撤销 / 回滚**

| 面 | 口径 |
|---|---|
| 粒度 | **以事务（批次）为单位**（一次 apply = 一个 `txid`）；"单条提议"= 该提议单独成批时即一批；**整轮** = 该轮各批次倒序；**整会话** = 会话内全部批次倒序。M3a 只做**撤销上一批**；整轮 / 整会话留 M3b（§2.6） |
| 入口 | 走 §2.2 的**唯一通用网关**：`agent_capability_call(id, action="undo", payload={txid?})`（缺省 = 该会话最新批次），形态对齐既有 `agent_session_delete`（`presentation/api/ui.py:1329`）；**不新增具名方法**（§2.2 口径） |
| UI | 紧挨面板里每条 `capability/apply` 审计卡片的「撤销」按钮（复用同一张 apply/reject 卡片，不新开面板） |
| 审批 | 撤销本身是**写**（会覆盖当前盘上内容）⇒ 仍需 `approval=confirm` 逐条确认，**不因"是撤销"免审** |
| 审计 | 追加 `capability/undo`（含 `txid`、逐文件 sha256 前后、结果）；纯追加，旧读者对未知 type 跳过 |
| **外部改动保护** | 撤销前**必须**校验目标文件当前 sha256 == apply 时记录的 sha256；任一不符 ⇒ **拒绝撤销**（**不静默覆盖用户手改**），可见报错并保留备份 |
| 一致性恢复 | 覆盖回 md + sidecar + manifest + pending 后，清 `DocumentService._cache` 并跑 `DocumentService.validate_kb()`（`services/document.py:2001`；RPC `presentation/api/ui.py:384`）⇒ errors 应为 0；词法索引按 `_write_body` 既有做法重建（`document.py:2076`） |
| **撤销失败** | **不静默、保留备份、报错**：不删 `txid` 目录、失败即停（不二次自动恢复），追加 `capability/undo{result:"failed"}`，由用户重试或人工处置 |

**6. 与既有机制的关系**

- **既有 L2 备份（必须如实说明）**：`atomic_yaml.write_backup`（`storage/atomic_yaml.py:22`，被 `save_sidecar`/`save_manifest` 与 pending 的 `_atomic_write_json` 调用）**已经在写前留同目录 `.bak`**（仅最新一版，designV0:611）。但它是**尽力而为 / fail-open**（`OSError` 只 `logger.warning` 后**降级继续写**，`:41-43`），且**不按事务聚合、不保证跨文件一致**；正文 `.md` 路径**完全没有**这层（`save_document`/`_write_body` 只有 tmp + `os.replace`）。**本节的 pre-image 与之叠加而非替代**：`.bak` 继续作单文件最后版本的兜底；**撤销只依赖批次快照**，并要求 **fail-closed**（备份失败 ⇒ 不写）——这是对既有 fail-open 的**有意收紧**，只作用于 M3 agent 路径。
- **KB 本身是 git 仓库（可选情形）**：本机制**不依赖** git、也**不调** git（插件不含代码 ⇒ 没有 `git` 调用通道；`forbidden` 属 §2.1 暂缓字段）。备份仍照做（撤销要秒级，且 git 未必可用/已提交）；两者不互斥。**建议**（文档口径，不由程序写）该库把 `.memoria/agent/backups/` 加入忽略，以免备份进版本历史。
- **不进热路径**（[designV0.md:987](../designV0.md)「不进查询热路径」）：备份是**本地文件字节复制** —— 无网络、无后台常驻、无索引构建；只出现在**写路径**（apply 前）与**打开/关库时的有界 trimming**；读 / 检索路径**零改动**。
- **是否新增事实源**：**否**。备份是**非权威、可清理副本**：权威状态仍是 md / sidecar / manifest / pending 本身；删掉备份最多让撤销在窗口内不可用（且**可见报错**），**不损坏**任何权威数据 —— 与 [AGENTS.md §1](../../AGENTS.md) 对 `.memoria/cache/**`（可再生缓存、不作为事实源）的定性同类。
- **但备份不放在 `.memoria/cache/**` 下**：cache 的既有语义是"校验失败**直接删了重建**"（designV0:657），静默清空会破坏撤销 ⇒ 给**独立目录 + 自己的保留口径 + 可见清理**。
- **仅当**评审者选择把备份升格为"可分发 / 可审计的权威档案"（即 §10 P10 选②完整历史并承诺长期保留）时，才需把下面这行交**人**登记进 [AGENTS.md §1](../../AGENTS.md)：`| 写前备份（agent 能力插件） | 各知识库 .memoria/agent/backups/**（可清理副本） | 应用代码（仅 apply 入口写） |`

#### 2.3.3 计划 API（plan schema）

> 用户口径（2026-09-20）：「写模块」的接口形态 = **计划 API + 编译器** —— agent 只产出**声明式 plan**；Memoria 用编译器把 plan 变成具体编辑，并复用**人类 UI 同一套校验器**。领域动词（§2.1.1）**只回 plan**。

**信封**（字段只增不改，兼容口径见 §10 **P12**）：

```jsonc
{
  "v": 1,                        // plan schema 版本
  "txid": "20260920T021100Z-07", // 事务 id：与 §2.3.2 的 <txid> 同格式同来源（一个 plan = 一个批次 = 一个 txid）
  "intent": "给 deep-learning.md 建 2 个知识点，并把 3 处正文挂到 attention",  // 人话一句（审计与确认卡标题）
  "ops": [ /* 有序；前 op 的结果对后 op 可见（可"先建点、后连边"） */ ]
}
```

**op 通用字段**：`op`（动词名）/ `op_id`（plan 内唯一，供逐条确认与审计定位）/ `file`（库内相对 `.md` 路径）。
**编译器对每个 op 做三件事**：① **路径归一**（复用只读侧 `_safe_rel`，`src/memoria/services/agent/tools/kb.py:160-172`）② **目标解析**（`resolve`，§2.3.4）③ **逐 op 校验**；随后把 op 序列编成对**原语**（§2.6 附表）的**有序调用序列**（落盘前由 apply 入口取 pre-image，§2.3.2）。**编译产物 = 原语调用序列；op 与原语多为一对一，`upsert_kp` 为一对二。**

| op | 字段 | 校验规则（幂等 / 可解析 / 歧义） | 编译器要解析 | 编译到（**唯一实现**） | 失败语义 |
|---|---|---|---|---|---|
| **`upsert_kp`** | `op_id`、`file`、`kp_id`、`name`、`range{start{line,snippet?},end{line,snippet?}}`、`tags[]?`、`description?`、`aliases[]?` | `start.line ≤ end.line` 且两端行**非空**（对齐 `kp_range_start_empty`/`kp_range_end_empty`）；新建时 `kp_id` 跨库唯一；**幂等键 `(file, kp_id)`** ⇒ 同 id 已存在走**更新**分支，不新建 | 行号 → snippet：`lines[ln-1].strip()[:80]`（`SNIPPET_MAX_LEN=80`，`src/memoria/range/constants.py:1`）；`range_resolved` 在预览/审计时由 `resolve_range`（`src/memoria/range/locator.py:67`）算 | `confirm_kp_range()`（`src/memoria/services/document.py:1360`；幂等更新分支 `:1406-1412`、id 唯一复核 `:1414-1419`）+（有 tags/description/aliases 时）`update_kp()`（`:1722`）；终校 `validate_sidecar`（`src/memoria/storage/sidecar_validate.py:133`） | **拒整批** |
| **`attach_links`** | `op_id`、`file`、`anchor_text`、`targets[]`、`occurrences[{line,matched_text}]?`（缺省 = 编译器扫出的全部候选）、`display_text?`、`edge_type?`、`relevance?`、`source_id?` | `targets` 逐个**必须可解析**（`ok`；`ambiguous`/`not_found` ⇒ 拒）；`edge_type ∈ {reference,extend}`（`contain` 不由 plan 写）；`occurrences[].line` 必须在扫描结果中命中且 `matched_text` **与命中文本一致**、非子串、无 `blocked`；**幂等键 `(file, anchor_text, occurrence, targets)`** ⇒ 已挂接处不二次包裹（`instances` 去重） | 复用**人 UI 同一条链路**：匹配 `scan_link_text_matches`（`src/memoria/services/link_text_search.py:825`，经 `services/link_instances.py:15` 转发）→ canonical 锚/列跨度 `resolve_canonical_anchor`、`line_matched_spans`（`document.py:2569-2570`）→ 正文包裹 `wrap_plain_on_lines`（`src/memoria/services/link_instances.py:72`，在 `document.py:2611` 调用） | `apply_link_instances()`（`src/memoria/services/document.py:2493`，写 sidecar + `_write_body` `:2699`；内部 `invalid` 判定 `:2547-2567`） | **拒整批** |
| **`detach_links`** | `op_id`、`file`、`anchor_text`、`occurrences[{line}]`、`mode:"detach"｜"remove_route"` | `anchor_text` 必须在 sidecar `links[]` 命中；`line` 必须存在且当前为 `[[…]]` 或已在 `instances`；**幂等**：已 `excluded` 的行再 detach ⇒ no-op（`add_excluded_lines` 去重，`link_instances.py:182`） | 路由定位 `_sidecar_entry_for_anchor`（`document.py:2134`）；行合法性同 `detach_link_instance` 内判定（`:2452-2458`） | `detach_link_instance()`（`document.py:2428`）；`mode=remove_route` → `delete_link_route()`（`:2709`）/ `remove_link()`（`:2773`） | **拒整批** |
| **`set_kp_range`** | `op_id`、`file`、`kp_id`、`range{start{line},end{line}}` | 行号/非空/顺序同 `upsert_kp`；`kp_id` 必须已存在于该文件；**幂等**：解析后 `range_resolved` 相同即视为无变化（`line_hint`/`snippet` 重算不算变更） | 同 `upsert_kp`（`resolve_range`） | `confirm_kp_range()`（`document.py:1360`）；单端微调 `pick_snippet_line()`（`:1665`） | **拒整批** |
| **`rename_kp`** | `op_id`、`kp_id`、`new_kp_id`、`new_name?` | 旧 id 必须可解析；新 id 必须可用（跨库唯一，`exists_in_file` 亦拒）；**幂等**：重放时旧 id 已不存在 ⇒ 按"旧 id 不可解析"**拒**（fail-closed，不静默 no-op） | 影响面**全库** ⇒ 预览必须给出受影响文件清单（`build_kp_index`，`services/link_resolver.py:47`） | `rename_kp_id()`（`document.py:1937` → `services/kp_rename.py`）+（改 name 时）`update_kp()` | **拒整批** |
| ~~`merge_kp`~~（**第二批**） | `op_id`、`keep_kp_id`、`merge_kp_ids[]`、`new_name?` | 各 id 可解析、互不相同；合并后 range/tags 冲突需人工拍板 | 近重复**建议** `suggest_kp_merge`（`src/memoria/services/search_kernel.py:135`，**只给建议**） | ⚠️ **本地无合并动作实现** ⇒ 需新增最小能力（见下） | **拒整批** |

**需新增的最小能力**（映射不到既有机制的，如实列出，不假装存在）：

1. **plan schema + 编译器 + `validate_plan`/`preview_plan` 本身**：新模块（只读面 + 编译，不含落盘）；
2. **`occurrences[].matched_text` 的前置核对**：既有 `apply_link_instances` 只收 `selected_lines`（`document.py:2498`）⇒ 编译器需先用 `scan_link_text_matches` 的 `matched_text` 比对 plan 给的行，再折算 `selected_lines`（薄胶水，只读）；
3. **`merge_kp` 的合并动作**：本地只有**建议**（`suggest_kp_merge` `search_kernel.py:135`；人 UI 也只展示建议，见 [agent-guide/05 §7](../reference/agent-guide/05-knowledge-points.md) 第 3 条）——合并 = 新 id + 重指 `links`/`edges` + 删源 KP，属**第二批新增**；
4. **plan 版本号 / 兼容承诺**：见 §10 **P12**（待拍板）。

**失败语义：拒整批（all-or-nothing）**。理由三条：① 一次确认 = 一个事务 = 一个 `txid`（§2.3 / §2.3.2 已定），若允许部分应用，"整批回滚"与"部分成功"两种语义并存，备份的 sha256 全等断言（§2.6 安全门 1/4）无法成立；② 下游 `apply_link_instances` 本身已是"要么全包裹、要么报错"（`document.py:2613-2620`），逐条放行会引入更细的中间态；③ 逐条 ✗ 仍可用（§2.3 第 3 步）——那是**编译前**的选择，不是编译后的部分执行。`validate_plan` 的 errors 按 `op_id` 定位（便于模型自查并**重写整批**），**不下发**"只应用合法子集"。

#### 2.3.4 编译器与校验器（只读面：给 agent 自检，也给人 UI 复用）

| API | 语义 | 复用（**唯一实现**，不另写一份） |
|---|---|---|
| `validate_plan(plan)` | 结构 + 语义校验，按 `op_id` 返回 errors/warnings；**不碰盘** | 路径 `_safe_rel`（`tools/kb.py:160-172`）；KP id `check_kp_id`（`document.py:1444`）；目标 `resolve_link_target`（`services/link_resolver.py:41`）；匹配 `scan_link_text_matches`（`link_text_search.py:825`）；终校 `validate_sidecar`（`sidecar_validate.py:133`） |
| `preview_plan(plan)` | **dry-run diff**：在内存 / `tempfile` 副本上真跑编译器，出"将改哪些文件、哪些行"；**零落盘** | 读原文 `load_document()`（`document.py:1271`）/ `_read_body()`（`:1259`）；范围解析 `resolve_range`（`range/locator.py:67`）；包裹试算 `wrap_plain_on_lines`（`link_instances.py:72`） |
| `resolve(target)` | KP id / 文件 stem → 候选；`ok` / `ambiguous` / `not_found` | `resolve_link_target`（`link_resolver.py:41`）、`resolve_links`（`document.py:1954`） |
| `audit_kb()` | 全库一致性审计（errors / warnings） | `DocumentService.validate_kb()`（`document.py:2001`；RPC `presentation/api/ui.py:384`） |

> **硬不变量：同一套校验器，两个消费者（人 UI 与 agent）。** 上表四个 API **不得**另写宽松校验，必须**转调人类 UI 已走的同一批函数**（右列即"唯一实现"）。反例（禁止）：在编译器里自建"边类型白名单"或"路径合法性"判断 —— 那会与 `normalize_link_edge_type`（`src/memoria/graph/edge_types.py:61-66`）/ `_safe_rel` 漂移，出现"人 UI 拒绝、agent 放行"的不一致。
>
> **自检循环**（替代"再问模型一遍"）：模型出 plan → `validate_plan`（有错按 `op_id` 重写**整批**）→ `preview_plan` 给人看 → 逐条确认 → apply。这与 §6.5 的结论一致：**校验器必须是程序**（无外部反馈的"自我纠错"已被证伪）。编译器本身**不落盘**；落盘只发生在 apply 入口（§2.3.1）。

### 2.4 权限与越界（违约即硬拒 + 审计 + 零部分写）

**权限矩阵**（行 = 路径域，列 = 插件声明的**动作类**（`read` / `write` / `network` / `host`）；风格同 [AGENTS.md §4](../../AGENTS.md)）：

| 路径域 | `read` | `write` | `network` | `host` |
|---|---|---|---|---|
| `**/*.md`（库内正文） | R | **R/W**（`approval=confirm`） | R | R |
| `.memoria/sidecars/**`、`.memoria/manifest.yaml`、`.memoria/pending.json` | R | **R/W**（**只经原语**，不直接写） | — | R |
| `.memoria/agent/sessions/**` | R | R（**只由核心追加审计事件**） | R | R |
| `.memoria/agent/backups/**`（写前备份，§2.3.2） | R | R（**只由 apply 入口写**；插件不可触达） | — | R |
| `.memoria/images/**` | R | R/W（仅 `kb.file.image_*` 原语） | R/W（先落 pending） | R |
| `.memoria/cache/**`（可再生缓存） | R/W | R/W | R/W | R/W |
| **库根之外**任意路径 | **Deny** | **Deny** | Deny | Deny |
| 出网 | Deny | Deny（默认关） | **逐次显式**（除 `llm/config.py:83` 的全局 `enabled` 外，还要求本次意图） | Deny |
| 执行外部命令 | Deny | Deny | Deny | Deny |

> **v1 声明面（2026-09-20）**：契约只开 `read` / `write` 两列（§2.1）；`network` / `host` / `exec` 三列是"引入对应动作类之后"才生效的预留列，v1 **没有对应字段可声明** ⇒ 本轮不发生效（"执行外部命令"一行同理，且 `approval` 的安全下限在引入 `exec` 时随之扩到它）。

**违约行为**（沿用 `ToolRegistry.invoke()` 的"失败也是结果"语义，`services/agent/tools/registry.py:232-302`）：

- **硬拒**：越界的 `tool_id` / 路径 / `permissions` 之外的动作 ⇒ 工具结果文本 `Error: … (DENIED)`（稳定 code `DENIED_CODE`，`registry.py:55`），**不抛异常、不结束轮次**；
- **审计**：写一条 `capability/reject`（插件 id、`tool_id`、拒绝原因、越界路径原文）；
- **零部分写**：越界判定发生在**任何落盘之前**（apply 入口一次性做完校验）⇒ 不存在"写了一半"；第 4 步中途失败 ⇒ 按快照**整批回滚**。

**路径逃逸**：一律 `os.path.realpath` 归一后判前缀，拒绝 ①含 `..` 的路径 ②归一后落在库根外的路径 ③**符号链接指向库外**（先解析链接再比库根 realpath）。`.md` 后缀与相对路径的既有判断照抄只读侧的 `_safe_rel()`（`services/agent/tools/kb.py:160-172`，已在生产只读工具里使用）。

**库之外**：本设计**不提供任何**库外写能力 —— 不改程序目录（`config/agent.json` 由既有设置面写）、不写用户主目录；dry-run 用的临时目录走 `tempfile` 且随事务销毁。

### 2.5 W/N/S/H 四条线如何落成插件族

同一条契约、同一个装载器；四条线 = 四个**插件族/目录**（**族 ≠ 枚举值**：族是按**目录与来源**的约定划分的 —— 内置 `resources/agent-capabilities/**` 按功能分目录、用户侧 `<kb>/.memoria/agent/skills/**`，**不是契约字段**；与 2026-09-20 删除 `kind` 的决定一致，见 §2.1「字段演进暂缓」）。下表右两列是**关键**：纯声明式的线可以完全不动核心，非纯声明式的线必须先有一次性挂载点。

| 族 | 首批插件 | `permissions` 要点 | 纯声明式？ | "不改核心"的前提 |
|---|---|---|---|---|
| **W 写** | `kb-write`（建点 / 改点 / 连边 / 文件增删改） | `write` 限库内正文 + `.memoria/**` 白名单；`approval=confirm` | ✅（工具体 = 核心原语） | M3a 一次性把写原语加进原语目录 |
| **N 联网** | `web-search`、`web-fetch` | 出网**逐次显式**（默认关；`network` 动作类是 N1 才引入的声明面，§2.1 暂缓清单）；抓取结果**先进 pending**（`storage/pending.py:91 save_pending`） | ✅ | N1 一次性把 `net.*` 原语加进目录 + 域名/私网策略（§3.3） |
| **S skill** | `<kb>/.memoria/agent/skills/<name>/`（`SKILL.md` + `manifest.json`，§4.2） | 默认只读；声明写权限仍 `confirm`（§4.4 不放宽） | ✅（skill 本就是声明式） | S1 一次性把 `use_skill` 按需注入器加进目录 |
| **H 宿主** | 悬浮卡片、定时唤醒（§5.2） | 宿主能力**默认关、逐 KB 开关**（`host` 动作类是 H1 才引入的声明面，§2.1 暂缓清单）；RPC 侧走通用网关 | ⚠️ **否**：RPC 侧可声明式，**浮层组件**需要一个核心提供的前端挂载点 | H1 需先加挂载点；建议单独立项（§5.4） |

> 结论要如实说：**能插的是"声明与权限"，不能插的是"新的执行体"**。这与 [AGENTS.md §6](../../AGENTS.md)（注册表条目 + 独立提示词文件、无执行体）和 §4.1「非目标：不做任意脚本执行」是同一条红线。

**写能力作为第一个消费者**：它同时验证了三件对后面三族同样重要的事 —— ① 契约能表达"多动作类 + 分级审批"；② 权限矩阵能被装载器与写原语**双向**执行；③ 审计事件能被回放。N/S/H 后续只需新增各自的原语与插件声明，**契约与装载器不再改**。

### 2.6 M3 分期与验收门（替代初版 W1/W2，对应 [dsh-agent-port.md §8](dsh-agent-port.md) 的 M3）

| 切片 | 落什么 | K 级（[ledger-maintenance.md §2](../conventions/ledger-maintenance.md)） | 验收门 |
|---|---|---|---|
| **M3a**（**计划 API 最小闭环**） | **最小可用契约 v1（§2.1）**校验器 + 装载器 + 库级注册文件 + **完整写管线**（propose = `plan` → `preview_plan` → 逐条确认 → **写前备份** → apply → 审计）+ **计划 API**（信封 + 编译器 + 只读面 `validate_plan`/`preview_plan`/`resolve`/`audit_kb`，§2.3.3 / §2.3.4）+ **首批 3 个 op**：`upsert_kp`、`attach_links`、`detach_links`（覆盖 KP 与链接两个动作类、两个方向） | 拍板前 **K3 待评审**；实施后 **K2 代码完成·验收未闭环**；三件证据齐 ⇒ **K4** | ① 单测 + ② harness DOM + ③ **安全门**（下列四条） |
| **M3b**（族化收口） | 其余 op（`set_kp_range`、`rename_kp`、`merge_kp`）+ 撤销/回滚（**整轮 / 整会话**，§2.3.2、§10 P10）+ `permission-presets` 的第二个旋钮 + **各一个"只声明不启用"的 N/S 样板插件**（验证契约通用性） | 同上 | M3a 门禁 + **越权次数 = 0** + L2 A/B（§7.4） |

**安全门（四条缺一不可，产物落 `artifacts/agent/verify/**`；每条给 plan 架构下的验证方式）**：

1. **无 silent 写** —— *测什么*：任一次拒绝/失败后，受影响文件 + `.memoria/**` **逐文件 SHA256** 与事务前全等。*怎么测*：为每个 op 的失败分支（目标不可解析 / 行号越界 / `occurrences[].matched_text` 不符 / 边类型非法）各造一个 plan → `validate_plan` 断言 errors 非空、`preview_plan` 断言 diff 为空 → 断言 SHA256 全等且**未创建** `backups/<session>/<txid>/`（拒批发生在 §2.3.2 调用序第 2 步之前）。
2. **越界被拒** —— *测什么*：`DENIED_CODE` 且零字节变化。*怎么测*：`ops[].file` 分别取 `../escape.md`、库外绝对路径、指向库外的**符号链接**各一例；**回程**：`attach_links` 的 `occurrences[].line` 也要有等价用例，证明路径/目标**两处同源**校验；断言在 `validate_plan` 阶段即拒、apply 未启动。
3. **审计可回放** —— *测什么*：**仅凭**会话 JSONL 的 `capability/apply` 事件即可重建"改了哪些文件、哪些行"（字段级断言，不依赖内存态）。*怎么测*：审计按 plan 落（含 `plan.v` / `txid` / `intent` / 逐 `op_id` / 逐文件 ±行 / `backup{txid}`），测试只读 JSONL 重放并逐字段断言。
4. **备份可用可清**（§2.3.2） —— *测什么*：① **正常写后可用备份恢复逐字节一致**（用该批 `files/**` 覆盖回受影响文件 + `.memoria/**`，与事务前 SHA256 逐文件全等）；② **写失败 / 备份失败 ⇒ 零部分写**（无任何文件被改，且失败批次目录被删除或标记为可见）；③ **越界 plan 被拒后无备份残留**（或残留可清理且计数可见）。*怎么测*：单测（`tests/test_agent_capabilities.py` 增 "restore byte-equal / zero-partial-write / deny-no-residue" 三组用例）+ 一个 `docs/example/rich-content-test/_harness.py` 演示（plan → preview → apply → 撤销 → 逐字节比对，走真实 KB）。

**附：M3 首批写原语目录**（插件只能挑用这些；`幂等键` 是 §6.3 原则 5 的落实）：

| 原语 `tool_id` | 语义 | 幂等键 | 复用（**唯一的落盘路径**） | 关键风险 |
|---|---|---|---|---|
| `kb.kp.create` | 建知识点（写 sidecar + 锚定 range） | `(file, kp_id)` | `services/document.py:1360 confirm_kp_range()` | range 锚不稳 → 走既有 KP 创建/确认链路 |
| `kb.kp.update` | 改 KP 名/描述/标签 | `(file, kp_id)` | `services/document.py:1722 update_kp()` | 图谱与 KP 面板的刷新时机 |
| `kb.link.create` | 连边（含边类型） | `(from, to, type)` | `services/document.py:2885 create_edge()` | 边类型词表须与图谱面板**同一份**事实源 |
| `kb.link.set_type` | 改边类型 | 同上 | `services/document.py:2885 create_edge()` / `:2971 delete_edge()` | 与"边类型迁移"同一实现 |
| `kb.file.create` | 新建 `.md` | `(path)` | `services/document.py:794 create_file()` | 目录自动创建须留在库内 |
| `kb.file.rename` | 重命名/移动 | `(from, to)` | `services/document.py:583 rename_file()` | 级联复用既有实现 |
| `kb.file.delete` | 删除 `.md` + sidecar | `(path)` | `services/document.py:782 delete_file()` | **默认关**（该开关属 §2.1 暂缓的 `config` 参数面，随 M3b 复评引入） |
| ~~`kb.file.move`~~ | 移动（目录重命名已实现，文件移动待补） | `(from, to)` | — | **M3 不进工具集**：正文内相对链接改写未落地（§9 R2） |

> **与原语目录的关系（2026-09-20，plan 架构）**：本表是**原语**（编译器的调用目标），不是模型可见的 op；plan 的 op（§2.3.3）编译到它们。M3a 首批 3 个 op 启用的是：`upsert_kp` → `kb.kp.create` / `kb.kp.update`；`attach_links` / `detach_links` → **新增原语** `kb.link.attach` / `kb.link.detach`（薄包装 `services/document.py:2493 apply_link_instances` / `:2428 detach_link_instance`，落盘仍只经原语）。本表 `kb.link.create`（`:2885 create_edge`，**纯边、不写正文**）与之**不是同一个动作**，其 op 形态（`upsert_edge`）留 M3b；`kb.file.*` 三个原语 M3a 不进工具集。

**明确不做（M3 内）**：

- ❌ **不做任意脚本/命令执行**：`permissions.exec` 属 §2.1 **暂缓字段**（v1 无 exec 声明面；引入它时 `approval` 的安全下限随之扩到 `exec`）；上游沙箱/执行族（`sandbox/*`、`shell/*`、`terminal/*` …）**不吃**（[dsh-agent-port.md §5](dsh-agent-port.md) ❌ 行，CVE 面见其 §9 P6）；
- ❌ **不做"模型自动应用"**：`approval.write=confirm` 是**装载期硬校验**，插件无法自行降档（用户能否覆写见 §10 P9）；
- ❌ **不做跨库写**：一次会话只绑一个库（`presentation/api/ui.py:1253 _agent_kb`），写原语的 `scope` 恒为当前库；
- ❌ **不做库外写**（含程序目录与用户主目录，见 2.4）；
- ❌ **不做 `kb.file.move`**（见上表）；
- ❌ **不做 plan 的"部分应用"**：一律**拒整批**（§2.3.3 失败语义）；逐条 ✗ 属**编译前**选择、不是编译后的部分执行；
- ❌ **M3a 不做 `set_kp_range` / `rename_kp` / `merge_kp`**：`set_kp_range` 可由 `upsert_kp` 覆盖；`rename_kp` 影响**全库**、门禁面过大；`merge_kp` 本地无动作实现 ⇒ 全部留 M3b；
- ❌ **不做 plan 版本协商**（`v` + `min_compiler` 区间等）：见 §10 P12；
- ❌ **不做 M4 对外契约**（旧稿 T1 CLI 面）：留 M4。

### 2.7 与上游 dsh（pin `0d1f5000`）的关系：借什么 / 自己发明什么

| 面 | 上游怎么做（对照物，只读码） | 本设计的处置 |
|---|---|---|
| 一次性审批、无应答即拒 | `interaction/user-approval`（已移植到 `approvals.py`） | ✅ **复用**：`AskPolicy(answerer=…)`（`services/agent/approvals.py:127`）就是"逐条确认"的接入口 |
| 写工具的 **diff 呈现契约** | `fs/tool-fs/src/write.ts:98-103`（`presentationMeta` 出 `diffs`）与 `:134-150`（`card: 'diff'`） | ✅ **借呈现契约**（dry-run diff 给人看）；❌ **不移植**该包的落盘路径与 `fs/write-intent` 单槽（`:114`，本地无版本号 CAS ⇒ 改用幂等键 + 事务快照） |
| 沙箱升级（"宽一点，再问一次"） | `fs/tool-fs/src/sandbox.ts`（`FsSandboxController`：`sandbox_permissions` + `justification` 一次性升级）+ `sandbox/sandbox`（`read-only` / `workspace-write` / `danger-full-access`） | ❌ **不吃**（`sandbox/*` 属"不吃"族）。本设计用**声明式 `permissions` + realpath 前缀校验**替代：等价于"只有一档 `workspace-write`、workspace = 库根、**没有**升级档" —— 这是**本地发明**，不是移植 |
| 权限档（presets） | `interaction/permission-presets/src/index.ts`（把 sandbox 模式 + 审批策略两个旋钮打成一档） | ⏸ **条件性**：本设计提供了第二个旋钮（`approval`：`auto`/`confirm`/`never`）⇒ M3b 之后"档"才有对象可切（呼应 [dsh-agent-port.md §6.15](dsh-agent-port.md) 的"本地只有一条固定策略、无第二个旋钮"判定） |
| 工具注册即发布 / 重名即错 | `core/tools`（已移植） | ✅ **复用**：`ToolRegistry.register()`（`services/agent/tools/registry.py:207`、`:212-213`）—— 装载器的冲突规则直接对齐它 |
| 技能（skill） | `skill/skill`（provider registry：合并 catalog、按 rank 定胜负、`SkillSource` 分级） | ⏸ 留 S1；本设计只先定"skill 族 = 声明式插件 + 只读默认"（§4.4），不引 provider rank |
| 会话投影/事件溯源审计 | `session-projection*`（❌ 不吃） | ❌ **不吃**：审计落在既有会话 JSONL 的**追加事件**上（`session/history.py:261-299` 的未知类型跳过语义），不引投影框架 |

---

## 3. 能力线 N：联网资料拉取与收集

### 3.1 边界（离线优先怎么落）

- **默认关**（沿用现有出网开关 `agent.json: enabled`）；**每一次**出网调用都要有**用户显式意图**（"去查一下 X"），不做后台轮询/自动抓取；
- 抓取结果**先进 `pending`**（草案态），不直接进正文/图谱 —— 用户确认后才成为知识。

### 3.2 工具（草案）

| 工具 | 语义 | token 策略 |
|---|---|---|
| `web_search` | 检索（返回标题 + URL + 摘要，**不回正文**） | 结果条数上限（默认 5）、每条摘要字节上限 |
| `fetch_url` | 抓正文 → **落 `pending` md + sidecar 草案**，只回"路径 + 摘要 + 长度" | **长文不进上下文**；模型需要时再用 `read_document` |
| `save_to_pending` | 把模型整理过的内容写进 pending | 与 W 线同一套确认/回滚 |

### 3.3 审计与安全

单次字节上限 + 超时 + 域名策略（黑/白名单，默认黑名单空、白名单空=只允许 http(s) 且拒绝私网地址）；**把"这次出网"记进会话事件**（可审计、可复盘），并在面板上可见。

---

## 4. 能力线 S：skill 机制（用户自定义能力包）

### 4.1 目标与非目标

- **目标**：用户不改程序即可扩展 agent 能力（提示 + 工具声明 + 资源），且**扩展是声明式的**；
- **非目标**：不做"任意脚本执行"（与仓库协作 agent 的沙箱/执行红线一致，见 [AGENTS.md §6](../../AGENTS.md)）。

### 4.2 声明式形态（= §2.1 契约的一个**用户技能类**插件，声明式、**不含代码**）

```
<kb>/.memoria/agent/skills/<name>/
  SKILL.md         # 何时用、怎么用（模型可读，按需注入）
  manifest.json    # = §2.1 的能力插件契约（**v1 字段集**：id/name/provides.tools/permissions/approval）
  assets/**        # 可选：模板、词表（只读）
```

> 与 §2.1 的对应：`manifest.json` 就是**同一份插件契约**（**v1 字段集**，§2.1），只是**用户技能类**（"类"由**来源目录** `<kb>/.memoria/agent/skills/**` 约定，不是契约字段；§2.1 已删除分类字段，见其「字段演进（一）」）；技能正文 `SKILL.md` 由 §4.3 的 `use_skill` 按需注入（**不依赖** `provides.prompt`，该字段属 §2.1 暂缓）；它的 `tool_id` 同样只能取自核心原语目录（**skill 不引入新的执行体**，见 §2.5 结论）。启用位与参数值落在同一份库级注册文件 `<kb>/.memoria/agent/capabilities.json`。

### 4.3 发现与按需注入（token 是关键约束）

**不把全部 skill 说明塞进 system 提示**（会随 skill 数量线性膨胀）。两段式：system 里只放"有哪些 skill + 一句话用途"；模型决定要用时，用 `use_skill(name)` 把该 skill 的 `SKILL.md` 正文**按需注入**（一次注入、当轮有效）。这条与横向 A（§6）直接相关。

### 4.4 权限模型

- skill 声明的工具**默认只读**；声明写权限的 skill 仍需**逐条确认**（不因"来自 skill"而降级审批）；
- 权限在**库级**登记（哪个库启用了哪些 skill），可一键停用。

### 4.5 复用与维护

版本（`manifest.version`）、依赖（`requires`）、冲突（同名工具优先级：内置 > skill，且冲突要**显式报错**而不是静默覆盖）、卸载（删目录即停用，与会话数据无关）。

---

## 5. 能力线 H：宿主接口（让 agent 用程序能力）

### 5.1 两个方向

- **agent → 程序**（调用）：把程序已有的能力暴露成 agent 可用工具（如"创建悬浮卡片""打开某个文件并高亮""触发一次检索"）；
- **程序 → agent**（唤醒）：程序侧事件把 agent 叫起来（定时到达、文件变化、卡片超时），**主动发起**一轮对话。

### 5.2 典型形态（用户举的例子）

| 形态 | 机制 | 注意 |
|---|---|---|
| 创建知识卡片并**悬浮在屏幕上** | 新增 RPC + 前端浮层组件（类似既有 flash 卡片，但可交互/可拖拽/可持久） | 与 z-index 体系、窗口最小尺寸、无窗口宿主（headless）的降级 |
| **定时 poll 后自我唤醒**并发起对话 | 最小调度器 + 会话写入（把唤醒也记成会话事件） | 见 §5.4 |
| 主动汇报（"我整理完了这 3 个文件"） | 同上 + 面板未读标记 | 打扰控制（§5.3） |

### 5.3 主动性的三问（必须先答）

1. **谁批准**：默认**关**；逐 KB 开关 + 首次开启时明确告知"它会在你不在时花 token"；
2. **频率上限**：每小时/每天上限 + 最短间隔；
3. **静默时段**：用户可设"不打扰"时段；超限的任务排队而不是丢弃。

### 5.4 现实约束：本地**没有后台服务**

本地 `ask()` 是**同步**调用面（`AskJobManager` 单飞），压缩/裁剪/标题都只能挂在 `ask()` 里同步做 —— 主动唤醒要求引入**一个最小调度器**：谁持有（随库/随进程）、进程退出后如何恢复（落盘队列 + 启动补跑或丢弃）、与既有 `MaintenanceExecutor`（2 worker）和前端 `scheduler.js` 的职责边界。**这是 H 线最难的一块**，建议单独立项评审。

### 5.5 与仓库契约的边界

[AGENTS.md](../../AGENTS.md) 的 RISC 条款（"永不新增独立 Agent"）约束的是**仓库协作 Agent**，不约束**产品内面向用户的对话 Agent**；措辞修订已在 [dsh-agent-port.md](dsh-agent-port.md) §10 登记为**待人工改动**（Agent 只读该文件）。

---

## 6. 横向 A：token 预算与工具元层

### 6.1 三级预算（超出即降级，不静默）

| 级别 | 约束 | 超限行为 |
|---|---|---|
| 单次工具结果 | 已有：`read_document ≤ 20k 字符`、检索 `top_k=5`；待补：统一 `max_result_chars` | 截断 + 明确标注"已截断" |
| 单轮工具调用 | 已有：`max_iterations=8` | 停止并如实回答"没查完" |
| 单会话累计 | 新增：按库可配的预算（token 或字符） | 提示用户并**停止**，不静默继续烧 |

### 6.2 记账口径必须补齐（当前缺口）

`scripts/benchmark/usage/report_usage.py` 只扫 `loop/end` ⇒ **标题调用、压缩（`compaction.usage`）、裁剪**三处开销**都不进报告**。基准要可信，先把这三处纳入同一形状的记账。

### 6.3 工具创建 / 复用 / 维护的六条原则

1. **一个能力一个事实源**：检索只有 `search_kb`、读文件只有 `read_document`、读 KP 只有 `read_kp`；新增工具前先证明"现有工具做不到"；
2. **工具描述本身耗 token**：schema 与描述一并计入预算，禁止在描述里写长示例；
3. **参数结构化**：能用枚举（如边类型）就不要让模型自由发挥；
4. **结果先摘要后详情**：工具默认回"摘要 + 定位信息（路径/seq）"，全文按需再取（`search_sessions` 已是这套）；
5. **幂等 + 可重放**：写类工具必须幂等（同参数重复调用不产生第二次写入）；
6. **可观测**：每次工具调用记 name/参数摘要/耗时/结果字节数 —— 这是基准的原料。

### 6.4 反模式清单（评审时逐条对照）

把大段正文塞进工具结果 · 工具描述里写长示例 · 同一轮重复调用同一工具 · 用两个工具做一件事 · 结果不带定位信息（模型只能重查） · 写类工具"顺手"多改一处。

---

### 6.5 引用完整性：让模型写的路径真的可用（P / V / L 三路线，文献支撑）

**问题**（实测，见 [agent-guide/01 §7](../reference/agent-guide/01-shell-and-layout.md)）：模型在回答里写 `文件.md:行号`，会出现①不存在的路径（少目录、近似文件名）②同一文件多种写法（`a.md`/`./a.md`/`docs/a.md`）③全角冒号/中文标点包裹/区间写法 ④点了跳不到。解析层 `services/link_resolver.py:41` 目前**只有精确匹配**（返回 `ambiguous`/`not_found`，无模糊或后缀回退）—— 这是"跳不到"的直接原因。

**三条路线与证据强度**：

| 路线 | 做法 | 证据强度 | 成本 | 与"只追加日志"红线 |
|---|---|---|---|---|
| **P** 提示词/规范约束 | 在 system prompt 里把引用语法**收窄到"只能取自工具回显的 canonical 路径"**，并给示例 | 中 | 低 | 兼容 |
| **V** 输出后程序校验与自动修补 | 归一化 → 精确 → 唯一 basename → 唯一后缀 → 模糊；多候选返回候选、不猜 | **高** | 中 | 兼容（纯读时计算） |
| **L** 事后修补落盘记录 | 就地改写会话 JSONL | **低**（档案/法规文献一致反对改写历史） | 中高 | **冲突** |

**关键文献结论**（原文与链接见本轮检索记录）：
- 引用类错误里"**混错 id**"只占约 **5%**，且属于**可被程序完全消除**的一类（[Fine-grained Rewards](https://arxiv.org/html/2402.04315v3)）⇒ V 的投入产出比最高。
- **反证**：引用**格式风格**对幻觉率**没有可测影响**（[Where Fake Citations Are Made](https://arxiv.org/html/2604.18880v1)）⇒ 继续扩正则只能提高"可解析率"，**不会**提高"引对率"。
- 厂商口径一致：要保证结构合规就用 structured outputs / strict 工具（[Anthropic](https://docs.anthropic.com/en/docs/control-output-format)、[Azure](https://learn.microsoft.com/en-au/Azure/foundry/openai/how-to/structured-outputs)、[Gemini](https://ai.google.dev/gemini-api/docs/structured-output)）；但 DeepSeek 官方 JSON mode **最弱**（自陈偶发返回空内容） ⇒ 在 DeepSeek 端点**必须** P+V 叠加（[DeepSeek JSON](https://api-docs.deepseek.com/guides/json_mode)）。
- Anthropic 的 Citations/Search-results 用**内部标识符**（如 `kb://article-1234`）承载归属、由 API 解析指针 —— 这是"从根上不可能写错路径"的形态（[Citations](https://platform.claude.com/docs/en/build-with-claude/citations)），但也最贵。
- **无外部反馈的"自我纠错"被证伪**（[ICLR 2024](https://arxiv.org/pdf/2310.01798.pdf)、[TACL 2024 综述](https://www.semanticscholar.org/paper/3fa1e1c67514b9eaf9ec8da562baef8974b4f3f9)）；有外部真值（文件清单）时才有显著收益（[PROCO](https://arxiv.org/pdf/2405.14092.pdf)）⇒ 校验器必须是**程序**，不是"再问模型一遍"。
- 事件溯源与审计口径：历史**只能追加补偿事件**，读取用**投影**（[Azure Event Sourcing](https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing)）；这与本仓库 [AGENTS.md §3](../../AGENTS.md) 的"事件只追加、永不改写"一致。

**落地顺序（建议）**：
1. **V1 归一化**：NFKC（全角→半角）、剥 CJK 标点包裹、去引号、去 `./` 前缀（零风险，消掉问题②③）。
2. **V2 分级收敛**：精确 → 唯一 basename → 唯一后缀 → 模糊（尾部元素加权，学 fzf 的 `path` 方案）；**任一级命中 >1 就判 `ambiguous` 并回候选，绝不猜**；行号越界 ⇒ 降级为文件级锚点。
3. **V3 回灌**：把 `not_found` 当**正常工具结果**返回（"不存在；库内相近的有 X/Y/Z"），**不自动重试**；同一猜测三次即停。错误文本模板 = 什么失败 + 为什么 + 真实情况 + 下一步。
4. **P**：只做一件事 —— 要求引用**取自工具回显的 canonical 路径**（`tools/kb.py:279` 已经在回显里带路径，把它变成硬约定）。**不要**加"请确保路径存在"这类话。
5. **L**：只做**读取时投影**（渲染/查询层修正，等价 upcaster）；确需留痕则**追加**一条修正事件，**不碰** `sessions/*.jsonl` 与 `events.jsonl`。

**明确"不要做"**（都有反证）：
- ❌ 别再用扩大正则覆盖面来"修好跳转"（只影响可识别性，不影响目标真实性）。
- ❌ 别依赖模型自我检查/自我修复（无外部反馈的自纠会掉分）。
- ❌ 别用全局固定编辑距离阈值自动改写（短 basename 上极易误并；实体解析共识是**误并比漏并更糟**）。
- ❌ 别改写已落盘的会话 JSONL / 事件日志（与仓库红线冲突，且与审计口径相反）。
- ❌ 别为整个知识库做路径枚举 schema（引擎覆盖度不一、大字典有成本）；只对**检索候选集**做枚举约束。

**目标口径**：V 的目标是"**零误跳 + 可解释的候选**"，不是"自动修对所有路径"（本领域没有对口研究；路径解析更接近 entity linking，其共识就是"启发式 + 候选 + 人工兜底"）。

---

## 7. 横向 B：基准测试集设计

### 7.1 三个层次

| 层 | 对象 | 采集 | 判定 |
|---|---|---|---|
| **L1 工具正确性** | 单次调用 | 固定 prompt → 期望工具 + 期望参数 | 选对/选错/多余调用/该用没用 |
| **L2 任务级** | 多轮维护任务（如"给 X 文件建 3 个 KP 并连边、然后校验通过"） | 轮数、工具调用序列、**总 token**、成功率、最终 `validate` 结果 | 完成率 + token 成本 + 是否越权写入 |
| **L3 回归基准** | 固定语料 + 固定 prompt 集，跨 commit | 同 maintenance-benchmark 的 A/B（确定性语料、warmup + 5 次采样、median/p95） | 关键指标不退化 |

### 7.2 指标

成功率 · **工具选择正确率** · **多余调用率** · 总 token（含辅助调用）· 缓存命中率 · 首答时延 · **写入越权次数（必须为 0）**。

### 7.3 语料

- 复用 `docs/example/showcase`（可复现）作 L1/L2 的"真库"；
- 新增**确定性合成任务集**：`scripts/benchmark/agent/gen_agent_tasks.py`（seed 固定，任务描述 + 期望工具序列 + 期望终态断言）；
- 语料生成到 `artifacts/_bench_agent/kb`（gitignore），结果写 `scripts/benchmark/agent/results/<label>_<sha>.{json,md}`（与 maintenance/graph/usage 并列）。

### 7.4 门禁

- 任何声称"更智能/更省 token"的改动，必须附 **L2 的 A/B**（成功率 + token 两列），并在 `results/summary.md` 留表；
- 出现"写入越权次数 > 0"或"成功率下降"⇒ 打回（与 [maintenance-benchmark.md](maintenance-benchmark.md) §5.6 同款纪律）。

### 7.5 与既有基准的关系

| 基准 | 对象 | 现状 |
|---|---|---|
| `scripts/benchmark/maintenance/` | 维护机制性能（保存/索引/调度） | 已有基线与门禁 ✅ |
| `scripts/benchmark/graph/` | 图谱渲染与布局 | 已有 |
| `scripts/benchmark/usage/` | 单轮 token 与缓存命中 | 已有（口径待补，§6.2） |
| **`scripts/benchmark/agent/`（本稿新增）** | **工具选择 + 任务级成本 + 写安全** | 待建 |

---

## 8. 阶段建议（供评审；**状态见 todo.md §13**）

| 阶段 | 范围 | 出口 |
|---|---|---|
| **T1** | 记账口径补齐（标题/压缩/裁剪进报告）+ 工具调用可观测（name/参数摘要/耗时/字节数） | 一份报告能回答"这轮花了多少、花在谁身上" |
| **B1** | L1 + L2 骨架（工具选择正确率、任务级 token、越权次数） | 有可复跑的对照表（先只用只读能力） |
| **W1**（=`M3a`） | 能力插件契约 + 装载器 + 库级注册文件 + 写管线（propose=`plan` → `preview_plan` → 逐条确认 → 应用 → 审计）+ **计划 API**（§2.3.3/§2.3.4）+ **首批 3 个 op**（`upsert_kp`、`attach_links`、`detach_links`） | "无 silent 写入"专项通过 + 越界被拒 + 审计可回放 + 备份可用可清（§2.6 安全门四条） |
| **W2**（=`M3b`） | 其余 op（`set_kp_range`、`rename_kp`、`merge_kp`）+ 撤销回滚 + `permission-presets` 第二旋钮 + N/S 各一个"只声明不启用"样板插件 | M3 出口（[dsh-agent-port §8](dsh-agent-port.md)）：越权次数 0 + L2 A/B |
| **N1** | 出网一次 + `web_search`/`fetch_url` 原语 + 落 `pending` + 联网类插件声明（族/来源目录约定，见 §2.5） | 出网可审计、长文不进上下文 |
| **S1** | 声明式 skill（只读工具 + `use_skill` 按需注入）+ 用户技能类插件声明（§4.2） | 一个用户自定义 skill 端到端可用 |
| **H1** | 最小宿主接口（悬浮卡片 + 定时唤醒，默认关）+ 核心侧前端挂载点 | 主动性三问有答案、可一键停 |

> 建议顺序 **T1 → B1 → W1(M3a) → W2(M3b) → N1 → S1 → H1**：先有度量与写能力闭环，再放联网与扩展，最后才放开"主动"。**W1/W2 已按 §2 更名为 M3a/M3b**（同一切片，`M3` 编号对齐 [dsh-agent-port.md §8](dsh-agent-port.md)）；N1/S1/H1 的"不改核心"前提见 §2.5。

---

## 9. 风险

| # | 风险 | 等级 | 处置 |
|---|---|---|---|
| R1 | **写能力毁用户库**（模型误解、range 锚错位） | 高 | 逐条确认 + 写前 pre-image / 事务回滚（§2.3.2）+ 只走既有服务层 + 每轮 `validate`；备份失败即不写（fail-closed） |
| R2 | **正文内相对链接/引用未随文件移动改写**（`path_cascade` 明确不碰正文） | 中高 | M3b 前补齐正文改写，否则 `kb.file.move` 不进工具集（§2.6 不做清单） |
| R3 | **出网泄露与"自动抓取"越界** | 中高 | 默认关 + 逐次显式 + 审计事件 + 私网地址拒绝 |
| R4 | skill / 能力插件变成任意代码执行面 | 高 | 契约**不含执行体**（插件只声明，工具体=核心原语）+ `permissions.exec` 属暂缓字段、v1 无 exec 声明面（§2.1/§2.5/§2.6）；执行类需求单独评审（沙箱，上游**不吃**） |
| R5 | 主动性变成"烧 token 的玩具" | 中 | 默认关 + 频率/静默约束 + 预算上限（§6.1） |
| R6 | 工具集膨胀导致选错率上升 | 中 | §6.3 原则 + L1 基准把"多余调用率"纳入门禁 |
| R7 | 基准不可比（模型/端点漂移） | 中 | 报告必须带 commit + 模型名 + 是否真端点；离线用假 provider 的可复现档 |
| R8 | **装载器成为新的越权写入面**（声明校验不严 ⇒ 插件拿到超出预期的写权限；`tool_id` 与原语不匹配被静默放宽） | 高 | 装载期硬校验（`write` 非空、`approval.write≠auto`、`tool_id` 必须在原语目录，即 §2.1 v1 字段表的"校验规则"列）+ 落盘前 realpath 前缀校验 + 安全门第 2 条专测越界；插件无代码 ⇒ 无写入口（§2.2/§2.3.1/§2.6） |

---

## 10. 待拍板

| ID | 问题 | 选项 | 影响 |
|---|---|---|---|
| **P1** | 写能力的确认交互 | ① 面板内逐条 ✓/✗（推荐） ② 系统弹窗逐条 ③ 批量"接受同类" | 前端工作量与可读性 |
| **P2** | 写工具是否允许"批量提议"（一次提议多条变更） | ① 允许但逐条确认（推荐） ② 只允许单条 | 事务复杂度 |
| **P3** | 出网工具的实现面 | ① 复用模型端点的联网能力（若端点支持） ② 应用自己抓（标准库 urllib + 白名单）（推荐） | 隐私面与实现量 |
| **P4** | skill 的承载位置 | ① `<kb>/.memoria/agent/skills/**`（随库走，推荐） ② 程序目录（跨库共享） | 分发与迁移 |
| **P5** | 主动性由谁调度 | ① 最小独立调度器（推荐） ② 复用 `MaintenanceExecutor` ③ 前端 `scheduler.js` | H 线复杂度（§5.4） |
| **P6** | 基准的"真端点"档是否纳入门禁 | ① 纳入（更真实但不可复现） ② 只作参考（推荐：门禁用假 provider 档） | 门禁可信度 |
| **P7** | **能力插件注册表的承载位置**（§2.2） | ① 内置声明 `resources/agent-capabilities/**`（随版本）+ 库级启用 `<kb>/.memoria/agent/capabilities.json`（随库）（**推荐**：与既有"程序读取源 vs 库内事实源"分工一致，且不动 `config/agent.json` 键白名单）② 全部随库（`.memoria/agent/capabilities/**`，可分发，但升级要迁移）③ 全部在程序目录（跨库共享，但无法 per-KB 启停） | 决定是否需人工登记 `AGENTS.md §1` |
| **P8** | **M3a 首批 op 个数**（plan 架构下按 **op** 计，不再按"原语"计；§2.3.3） | ① **三个**（`upsert_kp` + `attach_links` + `detach_links`，**推荐**：覆盖 KP 与链接两个动作类、两个方向，三条都能映射既有链路且可幂等证伪）② 五个（再加 `set_kp_range` + `rename_kp`：`rename_kp` 影响**全库**、M3a 门禁面过大）③ 一个（只有 `upsert_kp`：风险最低，但契约的"多动作类 + 分级审批"未被验证） | M3a 工期与门禁覆盖 |
| **P9** | **插件 `approval` 档是否允许用户覆写**（plan 架构下 `approval` 按 **op 动作类**分档：`resolve`/`validate_plan` 属 read ⇒ `auto`；`upsert_kp`/`attach_links`/`detach_links` 属 write ⇒ `confirm`） | ① **不可覆写**：库级文件只接受启停位与 `config` **值**（参数 schema 属 §2.1 暂缓），`approval` 由声明决定（**推荐**：审批档是安全不变量而非偏好；若可覆写则出现"声明 `confirm`、库级 `auto`"的双源，与 §2.3.4 的"单一校验器"口径冲突）② 可覆写（用户可把某插件 `write` 降到 `auto`）—— 需醒目告警 + 额外审计，且与 §2.1 的装载期硬校验冲突 | 决定 `capabilities.json` 的字段面 |
| **P10** | **撤销/回滚的实现口径**（§2.3 第 6 步；数据面见 §2.3.2） | ① **写前快照 + 会话内撤销 + 每会话保留 5 批 / 每库 64 MiB（FIFO，最新批次永不淘汰）**（**推荐**：可逐字节回滚、存储有界、撤销失败与淘汰均可见） ② **完整历史**（保留全部批次或用户设定的大额保留）：可撤销任意历史批次，代价 = 备份随写入线性增长 + 需人工清理 ③ **仅审计重放**（不存快照）：只能按 ±行 diff 语义回放，**不保证逐字节**，且文件被外部改动后不可安全回放 ⇒ 只作审计、不作撤销。**plan 架构下的口径**：批次粒度 = **一个 plan = 一个 `txid`**（不再按"一条提议"），撤销仍以 `txid` 为单位 | 存储与清理策略；② 的磁盘占用与"轻量/离线"的取舍 |
| **P11** | **`permission-presets`（权限档）是否随 M3b 落地** | ① 随 M3b 落地最小两档（**推荐**：`ask`＝写能力开、`never`＝全关；此时§2.1 的 `approval` 已是第 2 个旋钮）② 留到 M4（写能力已能用，档位只是便利） | 呼应 [dsh-agent-port §6.15](dsh-agent-port.md) 的"无第二个旋钮"判定 |
| **P12** | **编译器是否需要独立的 plan 版本号 / 向后兼容承诺**（§2.3.3 信封的 `v`） | ① **plan 自带 `v`，遵循"只增不改"**：新 op / 新字段只追加，旧编译器遇**未知 `op` 或未知字段 ⇒ 拒绝该 plan 并报错**（不静默忽略）（**推荐**：与 [AGENTS.md §3](../../AGENTS.md) 信封铁律同构 ⇒"格式演进不改提示词"**程序可验**；`v` 仅在**破坏性**变更时 +1）② plan 无版本号（靠工具 schema 隐式约束）：最省事，但"格式演进不改提示词"无从校验，且旧 plan 落盘后无法回放 ③ 完全版本协商（`v` + `min_compiler` 区间）：最严，但**单进程本地**产品无跨端消费者，属过度设计 | 决定 §2.3.3 信封字段与"格式演进"承诺能否被程序验证 |

---

## 11. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-19 | 初版（待评审）：现状盘点（调用面已具备、能力面极窄）；四条能力线（W 写 / N 联网 / S skill / H 宿主）逐线给出形态、边界、风险与验收；两条横向约束（token 三级预算 + 工具元层六原则与反模式；基准三层 L1/L2/L3 + 指标 + 语料 + 门禁，复用 maintenance-benchmark 方法论）；阶段建议 T1→B1→W1→W2→N1→S1→H1；7 条风险；P1–P6 待拍板。登记 `docs-management.md §4.2`，状态行落在 `todo.md §13`（AG04） |
| 2026-09-20 | **完善 M3：写能力 → 可插拔能力插件机制**（用户口径「M3 需要完善设计，做成可插拔的机制」）。§2 由"写工具清单"重写为七小节：**2.1 插件能力契约**（硬校验表（14 个字段；`kind` 已于同日删去 ⇒ **13**，见本表末行）+ 内置声明与库级启用两份 JSON 实样；铁律 = 插件目录**不含可执行代码**）、**2.2 注册与装载**（内置声明 `resources/agent-capabilities/**` + 库级 `<kb>/.memoria/agent/capabilities.json` 两位置分工、发现顺序、冲突即失败、不变量"新增插件不改核心"逐个点名核心文件、UIAPI 只加**一个通用网关**）、**2.3 写管线**（propose → dry-run diff → 逐条确认 → apply → 审计 → 撤销六步，逐步标注**已存在**的接入函数）+ **2.3.1 唯一写者**（`DocumentService.save_document`(`document.py:317`) / `storage/sidecar.py:120` / `storage/manifest.py:178` / `storage/pending.py:273`）、**2.4 权限矩阵与越界**（realpath 前缀校验、硬拒 `DENIED_CODE`、零部分写、库外一律 Deny）、**2.5 四线 → 插件族**（W/N/S 纯声明式、H 需一个前端挂载点；如实说明"能插的是声明与权限，不能插的是执行体"）、**2.6 M3a/M3b 分期 + 安全门三条 + 首批写原语目录 + 不做清单**、**2.7 与上游关系**（借 `user-approval` 与 `tool-fs` 的 diff 呈现契约；**沙箱升级不吃**，本设计用声明式 permissions + realpath 校验替代 —— 本地发明）。同步：§0 红线「禁止 silent 写入」加强为"插件边界物理可证"、§0 单一事实源补库级注册文件须登记；§1 缺口行；§4.2 skill 归入同一契约；§8 `W1/W2` 更名 `M3a/M3b` 并补 N1/S1/H1 的不改核心前提；§9 新增 **R8**（装载器成为越权写入面）；§10 新增 **P7–P11**（注册表承载 / M3a 原语个数 / approval 可否覆写 / 回滚口径 / 权限档是否随 M3b）；全部锚点逐条读码核对（见 §2 各处的 `file:line`）。**未实施任何代码**（本轮 docs only）；`docs/todo.md §13 AG04` 行按规则 8 同义压缩后仍为 K3 待评审 |
| 2026-09-20 | **为写能力补备份机制**（用户口径「写入技能还需要有备份机制」）。新增 **§2.3.2 备份（写前 pre-image）与撤销的数据面**（六小节）：① **时机/粒度** = apply 前、单文件 pre-image + 每轮一个批次快照（`txid`），覆盖 §2.3.1 四原语的**全部**落盘目标（md / sidecar / manifest / pending）；新建文件记 `{"existed": false}`（撤销=删除）；② **位置/命名/格式** = `<kb>/.memoria/agent/backups/<session_id>/<txid>/{journal.json,files/<原相对路径>}`，**原字节复制**（不做 diff/patch 存储，diff 只用于人看的 dry-run），逐字节/换行保真，单文件 >**8 MiB** 或单批 >**32 MiB** ⇒ 预检失败不写；③ **保留口径** = 每会话 **5** 批 / 每库 **10** 会话 / 总计 **64 MiB**，FIFO 淘汰且**永不删当前会话最新批次**，清理时机为 apply 后 / 打开 / 关库（不进读热路径），淘汰与失败**均可见**、**备份失败即不写（fail-closed）**；④ **唯一写者绑定点** = 备份是 apply 入口第一步（调用序 `路径校验 → snapshot_pre_images → 四原语 → 审计 → trimming`），插件无代码 + `permissions.write` 白名单不含 `backups/**` ⇒ 绕不过；⑤ **撤销** = 以事务为单位（M3a 只做撤上一批），入口走 §2.2 唯一通用网关 `agent_capability_call(action="undo")`（形态对齐 `ui.py:1329`），撤销**仍需审批 + 审计**，撤销前校验 sha256 防覆盖用户手改，撤销后跑 `validate_kb()`（`document.py:2001`）恢复一致性，**撤销失败不静默、保留备份、报错**；⑥ **与既有机制的关系** = 如实说明既有 `atomic_yaml.write_backup`（`storage/atomic_yaml.py:22`）的 `.bak` 是 **fail-open、单版本、非事务**，本节 pre-image 与之**叠加**并**有意收紧**为 fail-closed（仅 M3 agent 路径）；git 库情形**不调 git**；**不构成新增事实源**（非权威可清理副本，与 `.memoria/cache/**` 同类，但**不**放 cache 下以免被静默清空），并给出"若升格为权威档案才需人工登记 `AGENTS.md §1`"的那一行原文。同步：§0 红线加"写前必留 pre-image、备份失败即不写"；§2.1 实样 `forbidden` 增 `backups/**`、`emits` 增 `capability/backup`/`capability/undo`；§2.3 表第 4/6 步与"四条不变口径"引 §2.3.2；§2.3.1 补"原语调用者唯一 = apply 入口"；§2.4 矩阵增 `backups/**` 行；§2.6 M3a 落点加"写前备份"、安全门**三条 → 四条**（新增"备份可用可清"+验证方式）、M3b 撤销范围标注"整轮/整会话"；§9 R1 处置加写前 pre-image；**§10 P10 重写**为三选项（①写前快照+会话内撤销+数字保留（推荐）②完整历史 ③仅审计重放） |
| 2026-09-20 | **定死「写模块」接口形态 = 计划 API + 编译器**（用户口径：agent 只产出声明式 plan；Memoria 用编译器把 plan 变成具体编辑，并复用人类 UI 同一套校验器；格式演进不改提示词、幂等可验、审批粒度天然对齐）。**新增 §2.1.1 三层术语**（原语 / 领域动词 tool / 技能 skill，含"有无执行体""产出"两列，铁律 = **领域动词只产出 plan，不直接写盘**）；**§2.1 契约就地修正**：`provides.tools[]` 行改为"它贡献的**领域动词**……**该工具只产出 plan、不落盘**（§2.3.3/§2.1.1）"，并把实样里 `enum_from: graph.link_types` 更正为 `graph.edge_types.EDGE_TYPES`（真实常量 `src/memoria/graph/edge_types.py:14`）；§2.2 补"插件挑用的 `tool_id` 是领域动词、产出 plan"一句。**新增 §2.3.3 计划 API**：信封 `{v, txid, intent, ops[]}` + **op 表**（`upsert_kp` / `attach_links` / `detach_links` / `set_kp_range` / `rename_kp`，`merge_kp` 列第二批），每 op 给字段、校验规则（幂等键、"目标必须可解析"、越界/歧义如何拒）、编译器要解析什么（路径归一 `tools/kb.py:160-172`、KP id `check_kp_id`、`occurrences` 的"行+匹配文本"对齐 `scan_link_text_matches`/`wrap_plain_on_lines`）、编译到的**唯一实现**（`document.py:1360/1722/2493/2428/1937`），并给出**失败语义 = 拒整批（all-or-nothing）+ 三条理由**，另列 **4 条"需新增的最小能力"**（编译器本体、`occurrences.matched_text` 前置核对、`merge_kp` 合并动作、plan 版本承诺）。**新增 §2.3.4 编译器与校验器**：`validate_plan` / `preview_plan`（dry-run diff）/ `resolve` / `audit_kb` 四个只读面 + **硬不变量「同一套校验器，两个消费者（人 UI 与 agent）」**（逐 API 点名复用函数与行号，禁止另写宽松校验）+ 自检循环。**§2.3 管线第 1/5 步**改为产 `plan` 并按 plan 落审计。**§2.6** M3a 收敛为**计划 API 最小闭环**（首批 3 个 op + 只读面 + 完整管线），M3b 收其余 op；**安全门四条逐条给出 plan 架构下的"测什么/怎么测"**；附表下新增**原语目录与 op 的关系**（M3a 新增原语 `kb.link.attach`/`kb.link.detach`；`kb.link.create` 是纯边、`upsert_edge` 留 M3b）；不做清单新增 3 条（不做部分应用 / M3a 不做 `set_kp_range`·`rename_kp`·`merge_kp` / 不做版本协商）。**§8 W1/W2 行**同步为 plan 口径。**§10**：**P8 改为"首批 op 个数"**（①三个推荐 ②五个 ③一个）、**P9 补 plan 按 op 动作类分档**（推荐仍为不可覆写，理由补"双源与单一校验器冲突"）、**P10 补批粒度 = 一个 plan = 一个 `txid`**、**新增 P12**（plan 是否需独立版本号/兼容承诺：①自带 `v` 只增不改（推荐）②无版本号 ③完整协商）。**未实施任何代码**（本轮 docs only）；同步轻改 `dsh-agent-port.md` M3 行、`docs-management.md §4.2`、`todo.md §13 AG04`（字节门禁见验证） |
| 2026-09-20 | **字段演进：删除 `kind`（不再用未经验证的枚举同时承担"权限域"与"来源/划分"两种语义）**（用户口径：「那就不要写这个 kind 的字段，我们慢慢攒插件，后面才能知道有没有必要保留这个字段，以及怎么划分」）。**docs only，未改任何源码**。① `design/agent-capabilities.md` **§2.1**：删 `kind` 行（原 `read` / `write` / `network` / `skill` / `host`）⇒ **字段数 14 → 13**；内置声明实样删 `"kind": "write"`；`permissions.write` 行"`kind=write` 必填"改为"**有写动作类时**必填且非空"；**`approval` 行改写**为"**必须显式声明**（按动作类分档，不由分类字段推导）"，硬校验列落**安全下限**：「`permissions` 含 `write` 或 `exec` ⇒ `approval` **不得为 `auto`**；唯一例外须在 `forbidden`/注释里写明理由，且该例外**必须落审计**」；新增段 **「字段演进暂缓（2026-09-20）」** = 原话要点 + **`kind` 两项职责的替代**（approval 改显式声明 + 安全下限；**UI 先按插件来源目录/名单分组，是否需分类维度暂不由契约决定**）+ **复评触发条件 = 攒够 3–5 个真实插件**。② `kind` 残留清扫（同文件）：§2.1.1 技能行、§2.4 权限矩阵列名（`插件 kind` → `插件声明的动作类`）、**§2.5 改写为"四线 = 四个插件族/目录（族 ≠ 枚举值，按目录与来源约定、不是契约字段）"并删表内 `kind` 列**、§4.2 标题与注（→"**用户技能类**插件（声明式、**不含代码**）"，不引枚举）、§8 N1/S1 行。③ 轻改 `design/dsh-agent-port.md` §5（`skill` 行去掉 `kind: skill`）与 `docs-management.md §4.2`（追加本轮登记）。④ **§10 无改动**：P7–P12 逐条核对，均不依赖 `kind`（P8 按 **op 个数**、P9 按 **op 动作类**分档、P11 指 `approval` 旋钮），**未新增**"分类维度"待拍板项（用户已决定延后）。**未实施任何代码**；`docs/todo.md` 本轮未改动（AG04 行不依赖 `kind`，字节中性） |
| 2026-09-20 | **契约收缩为「最小可用契约 v1」（字段 13 → 6）**（用户口径：「能力契约我们慢慢完善，我们先以第一个写模块进行设计，只需要满足『最小可用契约字段集』，不要上来就框住，除非 dsh 上游有成熟的设计」）。**docs only，未改任何源码**。① `design/agent-capabilities.md` **§2.1 重写**：标题改「**最小可用契约 v1**」+ 写入**准入规则**（字段要么**有真实消费者点名**、要么**照搬上游成熟设计并点名 `file:line`**，两条都不满足即移出）；v1 字段表 **6 个** = `id`（有据：`dsh-src/packages/fs/tool-fs/src/index.ts:19`、`apps/cli/src/profile-boot.ts:173`）/ `name`（有据：`interaction/permission-presets/src/index.ts:62-71`）/ `provides.tools[]`（**本地自定**：上游是运行时 `ctx.tools.register()`，`core/tools/src/index.ts:1043`；仅取值语义对齐 `ToolSchema`，`core/tools/src/schema.ts:483-498`）/ `permissions.read`·`permissions.write`（**本地自定**：上游只有执行器档 `SandboxMode`，`packages/sandbox/sandbox/src/index.ts:29`）/ `approval`（**本地自定字段**，词汇对齐 `ApprovalOutcome`，`interaction/user-approval/src/types.ts:32`；上游档位是会话级 `ApprovalPolicy`，`interaction/user-approval/src/index.ts:60`），每行给"消费者是谁 / 上游对照 / 校验规则"；② **新增「暂缓字段（不在 v1）」清单**（10 条，逐条给**移出理由 + 再引入触发条件**）：`provides.prompt`、`permissions.exec`、`permissions.network`·`host`、`forbidden`、`config`（参数 schema）、`emits`、`verify`、`provenance`、`unload`、`enabled`（**契约层冗余** —— 库级注册表 `enabled[]` 的条目存在性即开关）；③ 两份 JSON 实样同步为 v1 字段集（并注 `v` 是信封版本、不占字段位）；④ **一致性清扫**：§2 引言（"禁项显式/提示词独立文件"标注已移出）、§2.2（"`config` 超界" → "v1 字段校验不过"；"两处新增" → **一处**）、§2.4（新增 **v1 声明面**注：只开 `read`/`write`，`network`/`host`/`exec` 三列不发生效）、§2.5（N/H 行的动作类改标"随 N1/H1 引入"）、§2.6（M3a 落点标 v1；`kb.file.delete` 开关与 `permissions.exec` 改按暂缓口径）、§4.2（去掉 `provides.prompt` 依赖）、§9 R4·R8（去掉 `exec` 恒空、`forbidden` 非空表述）、§10 **P9**（库级"只接受启停位与 `config` 值"）；**`approval` 安全下限**统一为「`permissions` 含 `write` ⇒ 不得 `auto`；**引入 `exec` 时该条随之生效**」；⑤ 轻改 `design/dsh-agent-port.md` §8 **M3 行**（标注 v1 字段集）与 `conventions/docs-management.md §4.2`（追加本行）。**`docs/todo.md` 未改动**（AG04 行不依赖被移出字段，状态仍 **K3 待评审**，字节中性） |
| 2026-09-20 | **契约迁出：新增活文档 [agent-plugin-design.md](agent-plugin-design.md)，本文只留指针**（用户口径：「我要一个新的文档写这些内容，所有内容都由我来慢慢对齐；先把上面确定的 6 字段最小协议记录进去，然后我们讨论写组件的细节」）。**docs only，未改任何源码**。① **新文档** `docs/design/agent-plugin-design.md`（**唯一事实源**）= 头部（用途 / 关联文档 / 状态=**活文档、由人逐步对齐** / **治理约定=Agent 只追加、不改写人已确认条目**）+ §1 最小可用契约 v1（6 字段表 + 准入规则 + **两份 JSON 实样**，均**逐字照抄**自本文收缩前的 §2.1）+ §2 暂缓字段 10 条 + §3 上游事实（三条结论 + `ApprovalOutcome` 含 `unavailable` ⇒ fail-closed，`file:line` 已逐条复验）+ §4 待讨论 Q1–Q6（`name` 去留 / `constrain`·`gate` 去留 / P8 首批 op 个数 / P9 `approval` 覆写 / P10 备份保留 / P12 plan 版本与兼容；只写问题 + 可选项）+ §5 变更记录；② **本文 §2.1** 的字段表、暂缓清单、`kind` 删除演进与两份 JSON 实样**全部迁出**，改为 **2 行指针**，只保留**模块侧**内容（铁律"插件目录内不含可执行代码"）与"其余各节原引 `§2.1` 字段表/暂缓清单/实样一律以该文为准"一句（**禁并行事实源**）；③ 登记 `conventions/docs-management.md §4.2`。**`docs/todo.md` 未改动**（AG04 行不引用 §2.1 字段表，字节中性） |
| 2026-09-20 | **本文降级为历史 / 路线图，不再是事实源**（用户口径：「这个文件不是只用于协议，所有相关设计都放在这，旧的我们不作为事实源」）。[agent-plugin-design.md](agent-plugin-design.md) 同日由「能力插件最小协议 v1」**重定位为「能力插件与写模块总设计」（协议 + 写场景 + 模块设计）**，并新增 §6 迁移清单（登记本文 §2.1.1/§2.2/§2.3/§2.3.1/§2.3.2/§2.3.3/§2.3.4/§2.4/§2.5/§2.6/§2.7 与 §8/§9/§10 中与写模块相关的行，逐行标状态）、§7 写场景清单（44 行，读码取证）、§8 场景关系与排序建议。**本文本轮只做两处最小改动**：§2.1 指针处补一句「契约与相关设计以 agent-plugin-design.md 为准；本文不再作为事实源」，以及本行。**未搬任何内容、未实施任何代码**；登记 `conventions/docs-management.md §4.2`；`docs/todo.md` 未改动 |
