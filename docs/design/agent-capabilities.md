# 工具与能力包路线图（产品内 Agent）

> **用途**：把"让 agent 真正智能"的四条能力线（**W 写能力 / N 联网收集 / S skill 机制 / H 宿主接口**）与两条横向约束（**token 预算与工具元层 / 基准测试集**）收敛成**可施工的阶段表与验收口径**。
> **关系**：调用面（循环、会话、工具注册表、只读工具、压缩/裁剪/标题/会话检索）已在 [dsh-agent-port.md](dsh-agent-port.md) 的 M1–M2 落地；本文只接它的 **M3（写能力）与 M4（对外契约）** 并展开。基准方法论复用 [maintenance-benchmark.md](maintenance-benchmark.md)（分层采集 / 确定性语料 / A/B 与门禁）。
> **状态**：待评审（2026-09-19 初版；**2026-09-20 完善 M3**：把写能力提升为「可插拔能力插件」契约的第一个消费者，四条线由此共用同一装载器，见 §2）。**实施状态的唯一来源是 [../todo.md §13](../todo.md) 的条目 ID**（本文不复制状态，遵守 [ledger-maintenance.md](../conventions/ledger-maintenance.md) 规则 1.2）。

---

## 0. 三条红线（不因本路线图放宽）

| 红线 | 本路线图的落法 |
|---|---|
| **离线优先** | 只有 **N 线**引入出网，且**逐次显式**（默认只读、默认关；见 §3.1） |
| **禁止 silent 写入** | **W 线**一律"提议 → 逐条确认 → 应用"，且只走既有服务层（§2.3）；**任何一次拒绝都不改盘**。**2026-09-20 加强**：该红线改为在**插件边界物理可证**——插件不含可执行体、核心写原语是唯一写者、落盘前做 realpath 前缀校验（§2.3.1）；**写前必留 pre-image、备份失败即不写**（§2.3.2） |
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
> **契约的模板**是 [AGENTS.md §6](../../AGENTS.md) 的 Agent 注册条目（声明式条目 + 单一注册文件 + 权限显式 + 禁项显式 + 提示词独立文件），实样见 `artifacts/agent/agents.json`；差别只在"扩展的是**产品内对话 Agent 的工具面**"而不是"仓库协作 Agent 的派发面"（边界措辞见 [dsh-agent-port.md §10](dsh-agent-port.md) 的待人工改动项）。

### 2.1 插件能力契约（capability plugin contract）

| 字段 | 必填 | 语义 | 装载期硬校验 |
|---|---|---|---|
| `id` | ✅ | 英文标识（kebab-case，唯一） | 重复即**装载失败**（不静默取其一） |
| `kind` | ✅ | `read` / `write` / `network` / `skill` / `host` | 必须是这五值之一；决定默认 `approval` 档与 UI 分组 |
| `provides.tools[]` | ✅ | 它贡献的工具：`tool_id`（**必须**取自核心原语目录）+ 参数收紧 `constrain` + 门控 `gate` | `tool_id` 不在原语目录 → 拒绝装载 |
| `provides.prompt` | ⬜ | 提示词段落文件（相对插件目录） | 与它的工具**同门控**；不得写进 `resources/agent-prompts/**`（那是既有事实源，见 [dsh-agent-port.md §6.3](dsh-agent-port.md)） |
| `permissions.read` | ✅ | 可读路径 glob（相对库根） | `read` 之外的 `tool_id` 一律拒 |
| `permissions.write` | ✅ | **可写**路径 glob；`kind=write` 必填且非空 | 空 ⇒ 该插件不可写（默认档） |
| `permissions.exec` | ⬜ | 外部命令白名单 | **M3 恒为空**（见 2.6 不做清单） |
| `forbidden` | ✅ | 与仓库/产品红线对齐的禁项文本 | 非空，且与 `permissions` 无自相矛盾 |
| `approval` | ✅ | 按动作类分档：`auto` / `confirm` / `never` | `write` 类**不得**为 `auto`（硬校验，见 §10 P9） |
| `config` | ⬜ | 参数 schema（`type`/`default`/边界）+ 库级启停默认值 | 参数名与类型必须过校验；持久化位置见 2.2 |
| `emits` | ✅ | 它产生的审计/事件类型 | 只允许**追加**型事件名 |
| `verify` | ✅ | 自证手段：`unit`（单测路径）+ `harness`（交互钩子） | 缺失不予装载（同 §6.3 原则 6「可观测」） |
| `provenance` | ✅ | `none` 或 `ported-from-dsh@<pin>` | 非 `none` 必须同时出现在根目录 `THIRD_PARTY_NOTICES.md` |
| `unload` | ✅ | 卸载语义：`restart`（默认）/ `hot` | 声明 `hot` 必须附卸载用例 |

字段之外还有**一条铁律**（2.2 会反复引用）：**插件目录内不含可执行代码**（无 `.py` / `.js` / 脚本），只含**声明 JSON + 提示词 + 只读资源**。

**内置声明实样**（`resources/agent-capabilities/kb-write.json`，随版本分发、只读）：

```jsonc
{
  "v": 1,
  "id": "kb-write",
  "name": "写能力（建点 / 改点 / 连边 / 文件增删改）",
  "kind": "write",
  "provides": {
    "tools": [
      { "tool_id": "kb.kp.create",   "gate": "always" },
      { "tool_id": "kb.kp.update",   "gate": "kb_has_sidecar" },
      { "tool_id": "kb.link.create", "gate": "always", "constrain": { "type": { "enum_from": "graph.link_types" } } }
    ],
    "prompt": "prompt.zh-CN.md"
  },
  "permissions": {
    "read":  [ "**/*.md", ".memoria/**" ],
    "write": [ "**/*.md", ".memoria/sidecars/**", ".memoria/manifest.yaml", ".memoria/pending.json" ],
    "exec":  []
  },
  "forbidden": [
    "写入库外路径（含符号链接指向库外）",
    "写入 .memoria/agent/sessions/**（会话事实源只由核心追加审计事件）",
    "写入 .memoria/agent/backups/**（写前备份属唯一写者内部步骤，插件不可触达，见 §2.3.2）",
    "git commit / git push"
  ],
  "approval": { "read": "auto", "write": "confirm", "network": "never" },
  "config": {
    "max_files_per_apply": { "type": "integer", "default": 3, "minimum": 1, "maximum": 10 },
    "allow_file_delete":   { "type": "boolean", "default": false }
  },
  "emits": [ "capability/proposal", "capability/apply", "capability/reject", "capability/backup", "capability/undo" ],
  "verify": { "unit": "tests/test_agent_capabilities.py", "harness": "docs/example/rich-content-test/_harness.py#write-diff-card" },
  "provenance": "ported-from-dsh@0d1f5000（只借 `fs/tool-fs` 的 diff 呈现契约；不移植其落盘路径）",
  "unload": "restart"
}
```

**库级启用实样**（`<kb>/.memoria/agent/capabilities.json`，随库走、用户可改）：

```jsonc
{
  "v": 1,
  "enabled": [
    { "id": "kb-write",       "on": true,  "config": { "max_files_per_apply": 3 } },
    { "id": "web-fetch",      "on": false, "config": {} },
    { "id": "kb-skill-local", "on": true,  "config": {} }
  ]
}
```

> 注意 `kb-write` 的 `permissions.write` **不含** `.memoria/agent/sessions/**`：审计事件是**核心**写的，不是插件写的 —— 这正是 2.3.1「插件物理上不能越界」的一个可核实例。

### 2.2 注册与装载

- **两个位置，职责分开**（沿用既有的"程序读取源 vs 库内事实源"分工）：
  1. **插件声明（随版本分发，只读）**：`resources/agent-capabilities/<id>.json` —— 与 `resources/agent-prompts/**` 同级的**程序读取源**，不含可执行代码；
  2. **库级启用与参数（随库走，用户可改）**：`<kb>/.memoria/agent/capabilities.json` —— **单一注册文件**（形态对齐 `artifacts/agent/agents.json`）。**该文件是新增事实源，须由人登记进 [AGENTS.md §1](../../AGENTS.md) 单一事实源表**（Agent 只读那张表；先例见 [dsh-agent-port.md §10](dsh-agent-port.md) 的 P3 会话目录）。
- **发现顺序**（顺序确定，冲突即失败）：① 内置声明按 `id` 字典序加载 → ② 用 `<kb>/.memoria/agent/capabilities.json` 的 `enabled[]` 求交集与启用位 → ③ `id` 未在声明里出现 / 校验失败 / `config` 超界 ⇒ **该条不装载 + 一条可见告警**，其余照常（**装载 fail-soft，执行 fail-closed**）。
- **冲突与重名**：
  - 两个声明同 `id` ⇒ 装载失败；
  - 两个插件声明**同一 `tool_id` 的同一动作类** ⇒ 装载失败（沿用 `ToolRegistry.register()` 的既有语义：重名 `raise ValueError`，`services/agent/tools/registry.py:207`、`:212-213`）；
  - `tool_id` 与原语目录不一致（未知动作）⇒ 拒绝该 `tool_id`，不静默降级。
- **不变量「新增插件不改核心」**：装载器落地（M3a）之后，新增一个插件 **不得**改动下列任一文件 —— `services/agent/tools/registry.py`、`services/agent/tools/kb.py`、`services/agent/approvals.py`、`services/agent/ask.py`、`services/agent/llm/config.py`、`presentation/api/ui.py`、`services/document.py`、`storage/{sidecar,manifest,pending}.py`。新插件只需**两处新增**：`resources/agent-capabilities/<id>.json` +（若贡献提示词）同目录的 `prompt.*.md`；库级只改 `<kb>/.memoria/agent/capabilities.json`。
  - **为什么不需动 `llm/config.py` 的键白名单**：库级启停状态落在**另一个文件**（`.memoria/agent/capabilities.json`），因此 `_WRITABLE_KEYS`（`services/agent/llm/config.py:87`）与全局 `config/agent.json` 的键集**不变** —— 避免了"per-KB 状态挤进全局配置"（全局/库级的分工口径见 [dsh-agent-port.md §10](dsh-agent-port.md) 的 P4）。
- **工具原语（primitive）的归属**：`tool_id`（如 `kb.kp.create`）背后的**工具体**属**核心原语目录**，由 M3a 一次性加进目录（内部只调 `DocumentService` / `storage/**` 的公开入口，见 2.3.1）；插件只能**挑用 + 收紧参数 + 声明权限**，不能新增工具体。这条就是"物理上不能越界"的**根**：**插件不带代码 ⇒ 没有 `open(...,"w")` 的机会**。
- **UI/RPC 面**：`UIAPI` 的公开方法即 RPC（`src/memoria/app/shell/pywebview.py:477` 的 `js_api=api`）。装载器只新增**一个通用网关方法**（如 `agent_capability_call(id, action, payload)`）+ 既有的配置读写面，**不按插件新增具名方法** —— 否则每加一个插件就要改 `presentation/api/ui.py`，与"不改核心"矛盾。

### 2.3 写管线（propose → dry-run diff → 逐条确认 → apply → 审计 → 撤销）

| 步 | 做什么 | 落在哪（**已存在**的接入口） |
|---|---|---|
| 1 **propose** | 模型调用写工具 ⇒ **只产提议**、不落盘。提议 = 人话一句 + 影响文件清单 + 结构化变更（不含原始 JSON） | 写工具声明 `read_only=False`（`services/agent/tools/registry.py:114`）⇒ 必过审批 |
| 2 **dry-run diff** | 应用前算出"将改哪些文件、哪些行"：已有文件在**临时副本**上真跑一次并算 diff，新建/删除给整段或整文件 | 取原文用 `DocumentService.load_document()`（`services/document.py:1271`）；diff 只在内存/`tempfile` 临时目录算 |
| 3 **逐条确认** | 逐条 ✓/✗；**未获批 = 不执行**（无应答者也拒） | `ToolRegistry.invoke()` 在**分发前**问策略（`registry.py:265-288`）→ `ApprovalPolicy.decide`（`services/agent/approvals.py:109-115`）→ 应答者走 `AskPolicy(answerer=…)`（`approvals.py:127-152`），无应答者 ⇒ `unavailable` ⇒ 拒绝 |
| 4 **apply** | 获批后**先取写前 pre-image（§2.3.2）**，再**一次性**转调既有服务层：原子写 → 索引失效 → manifest/sidecar 同步 → pending 同步 → KP 重锚 | 见 2.3.1、2.3.2 |
| 5 **审计** | 追加事件 `capability/proposal` / `capability/apply` / `capability/reject`（含插件 id、`tool_id`、逐文件 ±行、幂等键、决定与时间） | 会话 JSONL `<kb>/.memoria/agent/sessions/*.jsonl`；**纯追加**，旧读者对未知 `type` 一律跳过（`services/agent/session/history.py:261-299`）⇒ **不 bump** `SESSION_FORMAT_VERSION`（同 [dsh-agent-port.md §6.8](dsh-agent-port.md) 的 compaction 口径） |
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

**插件为何绕不过**：① 插件目录不含可执行体（§2.2 铁律）⇒ 没有 `open(...,"w")`，也没有直呼上述四个函数的通道；② §2.3.1 已收紧"原语之外不允许任何模块落盘"，本节再加一条**原语的调用者唯一 = apply 入口**；③ 插件的 `permissions.write` 是**白名单**且**不含** `.memoria/agent/backups/**`（§2.1 `forbidden` 已显式列入）⇒ 它既写不了、也删不了备份。⇒ agent 路径上"无备份的写入"不存在。

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
- **KB 本身是 git 仓库（可选情形）**：本机制**不依赖** git、也**不调** git（§2.1 `forbidden` 含 `git commit/push`）。备份仍照做（撤销要秒级，且 git 未必可用/已提交）；两者不互斥。**建议**（文档口径，不由程序写）该库把 `.memoria/agent/backups/` 加入忽略，以免备份进版本历史。
- **不进热路径**（[designV0.md:987](../designV0.md)「不进查询热路径」）：备份是**本地文件字节复制** —— 无网络、无后台常驻、无索引构建；只出现在**写路径**（apply 前）与**打开/关库时的有界 trimming**；读 / 检索路径**零改动**。
- **是否新增事实源**：**否**。备份是**非权威、可清理副本**：权威状态仍是 md / sidecar / manifest / pending 本身；删掉备份最多让撤销在窗口内不可用（且**可见报错**），**不损坏**任何权威数据 —— 与 [AGENTS.md §1](../../AGENTS.md) 对 `.memoria/cache/**`（可再生缓存、不作为事实源）的定性同类。
- **但备份不放在 `.memoria/cache/**` 下**：cache 的既有语义是"校验失败**直接删了重建**"（designV0:657），静默清空会破坏撤销 ⇒ 给**独立目录 + 自己的保留口径 + 可见清理**。
- **仅当**评审者选择把备份升格为"可分发 / 可审计的权威档案"（即 §10 P10 选②完整历史并承诺长期保留）时，才需把下面这行交**人**登记进 [AGENTS.md §1](../../AGENTS.md)：`| 写前备份（agent 能力插件） | 各知识库 .memoria/agent/backups/**（可清理副本） | 应用代码（仅 apply 入口写） |`

### 2.4 权限与越界（违约即硬拒 + 审计 + 零部分写）

**权限矩阵**（行 = 路径域，列 = 插件 `kind`；风格同 [AGENTS.md §4](../../AGENTS.md)）：

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

**违约行为**（沿用 `ToolRegistry.invoke()` 的"失败也是结果"语义，`services/agent/tools/registry.py:232-302`）：

- **硬拒**：越界的 `tool_id` / 路径 / `permissions` 之外的动作 ⇒ 工具结果文本 `Error: … (DENIED)`（稳定 code `DENIED_CODE`，`registry.py:55`），**不抛异常、不结束轮次**；
- **审计**：写一条 `capability/reject`（插件 id、`tool_id`、拒绝原因、越界路径原文）；
- **零部分写**：越界判定发生在**任何落盘之前**（apply 入口一次性做完校验）⇒ 不存在"写了一半"；第 4 步中途失败 ⇒ 按快照**整批回滚**。

**路径逃逸**：一律 `os.path.realpath` 归一后判前缀，拒绝 ①含 `..` 的路径 ②归一后落在库根外的路径 ③**符号链接指向库外**（先解析链接再比库根 realpath）。`.md` 后缀与相对路径的既有判断照抄只读侧的 `_safe_rel()`（`services/agent/tools/kb.py:160-172`，已在生产只读工具里使用）。

**库之外**：本设计**不提供任何**库外写能力 —— 不改程序目录（`config/agent.json` 由既有设置面写）、不写用户主目录；dry-run 用的临时目录走 `tempfile` 且随事务销毁。

### 2.5 W/N/S/H 四条线如何落成插件族

同一条契约、同一个装载器；四条线只是**四个 `kind` 不同的插件族**（各自一组 `permissions`）。下表右两列是**关键**：纯声明式的线可以完全不动核心，非纯声明式的线必须先有一次性挂载点。

| 族 | `kind` | 首批插件 | `permissions` 要点 | 纯声明式？ | "不改核心"的前提 |
|---|---|---|---|---|---|
| **W 写** | `write` | `kb-write`（建点 / 改点 / 连边 / 文件增删改） | `write` 限库内正文 + `.memoria/**` 白名单；`approval=confirm` | ✅（工具体 = 核心原语） | M3a 一次性把写原语加进原语目录 |
| **N 联网** | `network` | `web-search`、`web-fetch` | `network` 逐次显式；抓取结果**先进 pending**（`storage/pending.py:91 save_pending`） | ✅ | N1 一次性把 `net.*` 原语加进目录 + 域名/私网策略（§3.3） |
| **S skill** | `skill` | `<kb>/.memoria/agent/skills/<name>/`（`SKILL.md` + `manifest.json`，§4.2） | 默认只读；声明写权限仍 `confirm`（§4.4 不放宽） | ✅（skill 本就是声明式） | S1 一次性把 `use_skill` 按需注入器加进目录 |
| **H 宿主** | `host` | 悬浮卡片、定时唤醒（§5.2） | `host` 默认关、逐 KB 开关；RPC 侧走通用网关 | ⚠️ **否**：RPC 侧可声明式，**浮层组件**需要一个核心提供的前端挂载点 | H1 需先加挂载点；建议单独立项（§5.4） |

> 结论要如实说：**能插的是"声明与权限"，不能插的是"新的执行体"**。这与 [AGENTS.md §6](../../AGENTS.md)（注册表条目 + 独立提示词文件、无执行体）和 §4.1「非目标：不做任意脚本执行」是同一条红线。

**写能力作为第一个消费者**：它同时验证了三件对后面三族同样重要的事 —— ① 契约能表达"多动作类 + 分级审批"；② 权限矩阵能被装载器与写原语**双向**执行；③ 审计事件能被回放。N/S/H 后续只需新增各自的原语与插件声明，**契约与装载器不再改**。

### 2.6 M3 分期与验收门（替代初版 W1/W2，对应 [dsh-agent-port.md §8](dsh-agent-port.md) 的 M3）

| 切片 | 落什么 | K 级（[ledger-maintenance.md §2](../conventions/ledger-maintenance.md)） | 验收门 |
|---|---|---|---|
| **M3a**（骨架 + 首个写原语） | 契约校验器 + 装载器 + 库级注册文件 + 完整写管线（propose/dry-run/逐条确认/**写前备份**/apply/审计）+ **原语目录头两个**：`kb.kp.create`、`kb.file.create` | 拍板前 **K3 待评审**；实施后 **K2 代码完成·验收未闭环**；三件证据齐 ⇒ **K4** | ① 单测 + ② harness DOM + ③ **安全门**（下列四条） |
| **M3b**（族化收口） | 其余写原语（`kb.kp.update`、`kb.link.create`、`kb.link.set_type`、`kb.file.rename`、`kb.file.delete`）+ 撤销/回滚（**整轮 / 整会话**，§2.3.2、§10 P10）+ `permission-presets` 的第二个旋钮 + **各一个"只声明不启用"的 N/S 样板插件**（验证契约通用性） | 同上 | M3a 门禁 + **越权次数 = 0** + L2 A/B（§7.4） |

**安全门（四条缺一不可，产物落 `artifacts/agent/verify/**`）**：

1. **无 silent 写**：任一次拒绝/失败后，受影响文件 + `.memoria/**` **逐文件 SHA256** 与事务前全等；
2. **越界被拒**：`../escape.md`、库外绝对路径、指向库外的**符号链接**各一例 ⇒ `DENIED_CODE` 且零字节变化；
3. **审计可回放**：**仅凭**会话 JSONL 的 `capability/apply` 事件即可重建"改了哪些文件、哪些行"（字段级断言，不依赖内存态）；
4. **备份可用可清**（2026-09-20 新增，§2.3.2）：① **正常写后可用备份恢复逐字节一致** —— 用该批 `files/**` 覆盖回受影响文件 + `.memoria/**`，与事务前 SHA256 逐文件全等；② **写失败 / 备份失败 ⇒ 零部分写** —— 无任何文件被改，且失败批次目录被删除或标记为可见；③ **越界写被拒后无备份残留**（或残留可清理且计数可见）。
   - **验证方式**：单测（`tests/test_agent_capabilities.py` 增 "restore byte-equal / zero-partial-write / deny-no-residue" 三组用例）+ 一个 `docs/example/rich-content-test/_harness.py` 演示（写 → 撤销 → 逐字节比对，走真实 KB）。

**附：M3 首批写原语目录**（插件只能挑用这些；`幂等键` 是 §6.3 原则 5 的落实）：

| 原语 `tool_id` | 语义 | 幂等键 | 复用（**唯一的落盘路径**） | 关键风险 |
|---|---|---|---|---|
| `kb.kp.create` | 建知识点（写 sidecar + 锚定 range） | `(file, kp_id)` | `services/document.py:1360 confirm_kp_range()` | range 锚不稳 → 走既有 KP 创建/确认链路 |
| `kb.kp.update` | 改 KP 名/描述/标签 | `(file, kp_id)` | `services/document.py:1722 update_kp()` | 图谱与 KP 面板的刷新时机 |
| `kb.link.create` | 连边（含边类型） | `(from, to, type)` | `services/document.py:2885 create_edge()` | 边类型词表须与图谱面板**同一份**事实源 |
| `kb.link.set_type` | 改边类型 | 同上 | `services/document.py:2885 create_edge()` / `:2971 delete_edge()` | 与"边类型迁移"同一实现 |
| `kb.file.create` | 新建 `.md` | `(path)` | `services/document.py:794 create_file()` | 目录自动创建须留在库内 |
| `kb.file.rename` | 重命名/移动 | `(from, to)` | `services/document.py:583 rename_file()` | 级联复用既有实现 |
| `kb.file.delete` | 删除 `.md` + sidecar | `(path)` | `services/document.py:782 delete_file()` | **默认关**（`config.allow_file_delete`） |
| ~~`kb.file.move`~~ | 移动（目录重命名已实现，文件移动待补） | `(from, to)` | — | **M3 不进工具集**：正文内相对链接改写未落地（§9 R2） |

**明确不做（M3 内）**：

- ❌ **不做任意脚本/命令执行**：`permissions.exec` 恒为空；上游沙箱/执行族（`sandbox/*`、`shell/*`、`terminal/*` …）**不吃**（[dsh-agent-port.md §5](dsh-agent-port.md) ❌ 行，CVE 面见其 §9 P6）；
- ❌ **不做"模型自动应用"**：`approval.write=confirm` 是**装载期硬校验**，插件无法自行降档（用户能否覆写见 §10 P9）；
- ❌ **不做跨库写**：一次会话只绑一个库（`presentation/api/ui.py:1253 _agent_kb`），写原语的 `scope` 恒为当前库；
- ❌ **不做库外写**（含程序目录与用户主目录，见 2.4）；
- ❌ **不做 `kb.file.move`**（见上表）；
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

### 4.2 声明式形态（= §2.1 契约的一个 `kind: skill` 插件）

```
<kb>/.memoria/agent/skills/<name>/
  SKILL.md         # 何时用、怎么用（模型可读，按需注入）
  manifest.json    # = §2.1 的能力插件契约（id/kind=skill/provides.tools/permissions/approval/…）
  assets/**        # 可选：模板、词表（只读）
```

> 与 §2.1 的对应：`manifest.json` 就是**同一份插件契约**，只是 `kind: skill` 且 `provides.prompt` 指向 `SKILL.md`；它的 `tool_id` 同样只能取自核心原语目录（**skill 不引入新的执行体**，见 §2.5 结论）。启用位与参数落在同一份库级注册文件 `<kb>/.memoria/agent/capabilities.json`。

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
| **W1**（=`M3a`） | 能力插件契约 + 装载器 + 库级注册文件 + 写管线（提议 → dry-run diff → 逐条确认 → 应用 → 审计）+ **两个**写原语（`kb.kp.create`、`kb.file.create`） | "无 silent 写入"专项通过 + 越界被拒 + 审计可回放 + 备份可用可清（§2.6 安全门四条） |
| **W2**（=`M3b`） | 其余写原语（`kb.kp.update` / `kb.link.*` / `kb.file.rename` / `kb.file.delete`）+ 撤销回滚 + `permission-presets` 第二旋钮 + N/S 各一个"只声明不启用"样板插件 | M3 出口（[dsh-agent-port §8](dsh-agent-port.md)）：越权次数 0 + L2 A/B |
| **N1** | 出网一次 + `web_search`/`fetch_url` 原语 + 落 `pending` + `kind: network` 插件声明 | 出网可审计、长文不进上下文 |
| **S1** | 声明式 skill（只读工具 + `use_skill` 按需注入）+ `kind: skill` 插件声明（§4.2） | 一个用户自定义 skill 端到端可用 |
| **H1** | 最小宿主接口（悬浮卡片 + 定时唤醒，默认关）+ 核心侧前端挂载点 | 主动性三问有答案、可一键停 |

> 建议顺序 **T1 → B1 → W1(M3a) → W2(M3b) → N1 → S1 → H1**：先有度量与写能力闭环，再放联网与扩展，最后才放开"主动"。**W1/W2 已按 §2 更名为 M3a/M3b**（同一切片，`M3` 编号对齐 [dsh-agent-port.md §8](dsh-agent-port.md)）；N1/S1/H1 的"不改核心"前提见 §2.5。

---

## 9. 风险

| # | 风险 | 等级 | 处置 |
|---|---|---|---|
| R1 | **写能力毁用户库**（模型误解、range 锚错位） | 高 | 逐条确认 + 写前 pre-image / 事务回滚（§2.3.2）+ 只走既有服务层 + 每轮 `validate`；备份失败即不写（fail-closed） |
| R2 | **正文内相对链接/引用未随文件移动改写**（`path_cascade` 明确不碰正文） | 中高 | M3b 前补齐正文改写，否则 `kb.file.move` 不进工具集（§2.6 不做清单） |
| R3 | **出网泄露与"自动抓取"越界** | 中高 | 默认关 + 逐次显式 + 审计事件 + 私网地址拒绝 |
| R4 | skill / 能力插件变成任意代码执行面 | 高 | 契约**不含执行体**（插件只声明，工具体=核心原语）+ `permissions.exec` M3 恒空（§2.1/§2.5/§2.6）；执行类需求单独评审（沙箱，上游**不吃**） |
| R5 | 主动性变成"烧 token 的玩具" | 中 | 默认关 + 频率/静默约束 + 预算上限（§6.1） |
| R6 | 工具集膨胀导致选错率上升 | 中 | §6.3 原则 + L1 基准把"多余调用率"纳入门禁 |
| R7 | 基准不可比（模型/端点漂移） | 中 | 报告必须带 commit + 模型名 + 是否真端点；离线用假 provider 的可复现档 |
| R8 | **装载器成为新的越权写入面**（声明校验不严 ⇒ 插件拿到超出预期的写权限；`tool_id` 与原语不匹配被静默放宽） | 高 | 装载期硬校验（`write` 非空、`approval.write≠auto`、`forbidden` 非空、`tool_id` 必须在原语目录）+ 落盘前 realpath 前缀校验 + 安全门第 2 条专测越界；插件无代码 ⇒ 无写入口（§2.2/§2.3.1/§2.6） |

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
| **P8** | **M3a 首批写原语个数** | ① 两个（`kb.kp.create` + `kb.file.create`，**推荐**：最小可证伪，先证"管线 + 安全门"）② 四个（再含 `kb.kp.update` + `kb.link.create`）③ 一个（只有 `kb.kp.create`，风险最低但契约的"多动作类 + 分级审批"未被验证） | M3a 工期与门禁覆盖 |
| **P9** | **插件 `approval` 档是否允许用户覆写** | ① **不可覆写**：库级文件只接受启停与 `config` 参数，`approval` 由声明决定（**推荐**：审批档是安全不变量而非偏好）② 可覆写（用户可把某插件 `write` 降到 `auto`）—— 需醒目告警 + 额外审计，且与 §2.1 的装载期硬校验冲突 | 决定 `capabilities.json` 的字段面 |
| **P10** | **撤销/回滚的实现口径**（§2.3 第 6 步；数据面见 §2.3.2） | ① **写前快照 + 会话内撤销 + 每会话保留 5 批 / 每库 64 MiB（FIFO，最新批次永不淘汰）**（**推荐**：可逐字节回滚、存储有界、撤销失败与淘汰均可见） ② **完整历史**（保留全部批次或用户设定的大额保留）：可撤销任意历史批次，代价 = 备份随写入线性增长 + 需人工清理 ③ **仅审计重放**（不存快照）：只能按 ±行 diff 语义回放，**不保证逐字节**，且文件被外部改动后不可安全回放 ⇒ 只作审计、不作撤销 | 存储与清理策略；② 的磁盘占用与"轻量/离线"的取舍 |
| **P11** | **`permission-presets`（权限档）是否随 M3b 落地** | ① 随 M3b 落地最小两档（**推荐**：`ask`＝写能力开、`never`＝全关；此时§2.1 的 `approval` 已是第 2 个旋钮）② 留到 M4（写能力已能用，档位只是便利） | 呼应 [dsh-agent-port §6.15](dsh-agent-port.md) 的"无第二个旋钮"判定 |

---

## 11. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-19 | 初版（待评审）：现状盘点（调用面已具备、能力面极窄）；四条能力线（W 写 / N 联网 / S skill / H 宿主）逐线给出形态、边界、风险与验收；两条横向约束（token 三级预算 + 工具元层六原则与反模式；基准三层 L1/L2/L3 + 指标 + 语料 + 门禁，复用 maintenance-benchmark 方法论）；阶段建议 T1→B1→W1→W2→N1→S1→H1；7 条风险；P1–P6 待拍板。登记 `docs-management.md §4.2`，状态行落在 `todo.md §13`（AG04） |
| 2026-09-20 | **完善 M3：写能力 → 可插拔能力插件机制**（用户口径「M3 需要完善设计，做成可插拔的机制」）。§2 由"写工具清单"重写为七小节：**2.1 插件能力契约**（14 个字段的硬校验表 + 内置声明与库级启用两份 JSON 实样；铁律 = 插件目录**不含可执行代码**）、**2.2 注册与装载**（内置声明 `resources/agent-capabilities/**` + 库级 `<kb>/.memoria/agent/capabilities.json` 两位置分工、发现顺序、冲突即失败、不变量"新增插件不改核心"逐个点名核心文件、UIAPI 只加**一个通用网关**）、**2.3 写管线**（propose → dry-run diff → 逐条确认 → apply → 审计 → 撤销六步，逐步标注**已存在**的接入函数）+ **2.3.1 唯一写者**（`DocumentService.save_document`(`document.py:317`) / `storage/sidecar.py:120` / `storage/manifest.py:178` / `storage/pending.py:273`）、**2.4 权限矩阵与越界**（realpath 前缀校验、硬拒 `DENIED_CODE`、零部分写、库外一律 Deny）、**2.5 四线 → 插件族**（W/N/S 纯声明式、H 需一个前端挂载点；如实说明"能插的是声明与权限，不能插的是执行体"）、**2.6 M3a/M3b 分期 + 安全门三条 + 首批写原语目录 + 不做清单**、**2.7 与上游关系**（借 `user-approval` 与 `tool-fs` 的 diff 呈现契约；**沙箱升级不吃**，本设计用声明式 permissions + realpath 校验替代 —— 本地发明）。同步：§0 红线「禁止 silent 写入」加强为"插件边界物理可证"、§0 单一事实源补库级注册文件须登记；§1 缺口行；§4.2 skill 归入同一契约；§8 `W1/W2` 更名 `M3a/M3b` 并补 N1/S1/H1 的不改核心前提；§9 新增 **R8**（装载器成为越权写入面）；§10 新增 **P7–P11**（注册表承载 / M3a 原语个数 / approval 可否覆写 / 回滚口径 / 权限档是否随 M3b）；全部锚点逐条读码核对（见 §2 各处的 `file:line`）。**未实施任何代码**（本轮 docs only）；`docs/todo.md §13 AG04` 行按规则 8 同义压缩后仍为 K3 待评审 |
| 2026-09-20 | **为写能力补备份机制**（用户口径「写入技能还需要有备份机制」）。新增 **§2.3.2 备份（写前 pre-image）与撤销的数据面**（六小节）：① **时机/粒度** = apply 前、单文件 pre-image + 每轮一个批次快照（`txid`），覆盖 §2.3.1 四原语的**全部**落盘目标（md / sidecar / manifest / pending）；新建文件记 `{"existed": false}`（撤销=删除）；② **位置/命名/格式** = `<kb>/.memoria/agent/backups/<session_id>/<txid>/{journal.json,files/<原相对路径>}`，**原字节复制**（不做 diff/patch 存储，diff 只用于人看的 dry-run），逐字节/换行保真，单文件 >**8 MiB** 或单批 >**32 MiB** ⇒ 预检失败不写；③ **保留口径** = 每会话 **5** 批 / 每库 **10** 会话 / 总计 **64 MiB**，FIFO 淘汰且**永不删当前会话最新批次**，清理时机为 apply 后 / 打开 / 关库（不进读热路径），淘汰与失败**均可见**、**备份失败即不写（fail-closed）**；④ **唯一写者绑定点** = 备份是 apply 入口第一步（调用序 `路径校验 → snapshot_pre_images → 四原语 → 审计 → trimming`），插件无代码 + `permissions.write` 白名单不含 `backups/**` ⇒ 绕不过；⑤ **撤销** = 以事务为单位（M3a 只做撤上一批），入口走 §2.2 唯一通用网关 `agent_capability_call(action="undo")`（形态对齐 `ui.py:1329`），撤销**仍需审批 + 审计**，撤销前校验 sha256 防覆盖用户手改，撤销后跑 `validate_kb()`（`document.py:2001`）恢复一致性，**撤销失败不静默、保留备份、报错**；⑥ **与既有机制的关系** = 如实说明既有 `atomic_yaml.write_backup`（`storage/atomic_yaml.py:22`）的 `.bak` 是 **fail-open、单版本、非事务**，本节 pre-image 与之**叠加**并**有意收紧**为 fail-closed（仅 M3 agent 路径）；git 库情形**不调 git**；**不构成新增事实源**（非权威可清理副本，与 `.memoria/cache/**` 同类，但**不**放 cache 下以免被静默清空），并给出"若升格为权威档案才需人工登记 `AGENTS.md §1`"的那一行原文。同步：§0 红线加"写前必留 pre-image、备份失败即不写"；§2.1 实样 `forbidden` 增 `backups/**`、`emits` 增 `capability/backup`/`capability/undo`；§2.3 表第 4/6 步与"四条不变口径"引 §2.3.2；§2.3.1 补"原语调用者唯一 = apply 入口"；§2.4 矩阵增 `backups/**` 行；§2.6 M3a 落点加"写前备份"、安全门**三条 → 四条**（新增"备份可用可清"+验证方式）、M3b 撤销范围标注"整轮/整会话"；§9 R1 处置加写前 pre-image；**§10 P10 重写**为三选项（①写前快照+会话内撤销+数字保留（推荐）②完整历史 ③仅审计重放） |
