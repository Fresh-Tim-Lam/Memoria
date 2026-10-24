# AGENTS.md — Memoria 多 Agent 协作与调度契约

> **用途**：定义 Memoria 仓库内多 Agent 协作的**最小基础集**、事件契约、权限隔离与**可插拔扩展接口**。
> **目标读者**：SOLO 主控 Agent（Trae）与所有子 Agent；人维护者可据此复核。
> **关联文档**：[AGENT.md](AGENT.md)（边界/单一事实源/常见陷阱）、[collaboration.md](docs/guides/collaboration.md)（协作规则）、[maintenance-jobs.md §5](docs/design/maintenance-jobs.md)（作业登记表）、[todo.md §12](docs/todo.md)（门禁台账）。
> **状态**：生效中，2026-09-10（DSH 载体适配 2026-10-19）。本文件不重复既有规范；冲突时以 `docs/conventions/**` 与 [AGENT.md](AGENT.md) 为准。
> **执行载体说明**：本契约的「单一事实源 / 三角色职责 / 验证阶梯 / 权限隔离」骨架在**两种执行载体**下都成立，仅「怎么派发、怎么交接」随载体而变：
> - **Trae/SOLO 载体（历史）**：SOLO 主控 + 静态三角色 + `events.jsonl` 事件流；
> - **DSH 载体（当前）**：Lead + 动态 `spawn_teammate` + 共享任务板 + `send_message` + 磁盘报告。实操见 [dsh-agent-teams-contract.md](docs/guides/dsh-agent-teams-contract.md)。

> **⚠️ 历史载体警告（2026-10-23，P1 单一载体）**：本文件 §2–§7 描述的是 **Trae/SOLO 载体（历史）**：
> 静态三角色 builder/verifier/registrar + `events.jsonl` 事件派发。**该机制在 DSH 载体下从未运行**，
> 三角色已在 `team/agents.json` 标记 `retired-in-dsh`。
> **当前 DSH 载体的真实机制**见 [agent-team-status.md](docs/guides/agent-team-status.md)、
> [agent-team-org.md](docs/guides/agent-team-org.md)（常驻领域 Owner）与
> [dsh-agent-teams-contract.md](docs/guides/dsh-agent-teams-contract.md)（实操）。
> 派发可追溯记录写入 `team/dispatch-log.jsonl`（见同目录 `scripts/agent/dispatch_log.py`）。

---

## 0.5 Lead 派发不变量（**每次对话强制注入，违反即返工**）

> 设计依据（2026-10-24 复盘）：**写在文档里靠"记住"的规范，遵守率就是随机数**；
> 只有"让违规在物理上做不到"的规则才稳定生效。
> 完整规范按触发条件分节读：**[lead-dispatch-rules.md](docs/guides/lead-dispatch-rules.md)**
> （spawn 读 §1 / 建任务读 §2 / 收口读 §3 / 发版读 §4 / **对话被压缩后必读 §0**）。

```
L1. spawn 前必须先建任务并声明 writeScope；与存活成员写域重叠 ⇒ 排队，不许并行
L2. 执行者自报 PASS 不算验收：R1 级（打包/发版/改 tag/强推/迁移数据）必须 Lead 亲跑门禁
L3. 关闭任务必须有 evidence（工具已强制）；退役成员名下任务必须同轮收口，否则变幽灵 owner
L4. 版本文件与 Package/** 属人权限：Lead 只在人明确授权后动，且必须在回报中披露
L5. 不可逆操作（删除/强推/发版）先给回滚方案再执行；发版前必须核对【远端】tag 是否存在
L6. 任何"看起来成功其实没做"的路径，修法是【让失败可见】，不是"改对就完"
L7. 对话被压缩后不凭记忆回答"还剩什么"：一律重查任务板 + 跑 team_audit.py
```

**机器兜底**：`scripts/agent/team_audit.py`（11 类）—— 其中 `dispatch_release`
直接检查 L1（spawn↔任务）、L5（版本三查 + tag↔commit）；`stall` 检查 L3（幽灵 owner）。

---

## 0. 平台硬约束（不可绕过）

- **派发权单一**：只有**主控**（Trae/SOLO 载体）或 **Lead**（DSH 载体）能识别触发条件并调用子 Agent；**子 Agent 不得调用其它子 Agent**。
- 每个子 Agent 拥有**独立隔离上下文**；其内部推理**不会回传**主控。跨 Agent 交接**只能**通过「磁盘产物 + 事件记录」（或 DSH 的共享任务板 + 磁盘报告）完成，**禁止依赖对话记忆**。
- "事件订阅"是**声明式**的：子 Agent 在注册表声明订阅，由**主控**在事件到达时派发。（DSH 载体下的派发见 [dsh-agent-teams-contract.md](docs/guides/dsh-agent-teams-contract.md)）

## 1. 单一事实源（Single Source of Truth）

| 类别 | 唯一来源 | 写权限 |
|---|---|---|
| 边界/禁止行为 | [AGENT.md](AGENT.md) §6、`docs/conventions/**` | 人（Agent 只读） |
| 范围/门禁台账 | [todo.md §12](docs/todo.md) | `registrar` |
| 作业登记 | [maintenance-jobs.md §5](docs/design/maintenance-jobs.md) | `registrar` |
| 文档索引/登记 | `docs/README.md` 及各级 README、`docs/conventions/docs-management.md` | `registrar` |
| 版本号 | `src/memoria/__version__.py` | 人（Agent 只读） |
| 产品状态 | 各知识库 `.memoria/**`（manifest/sidecars/pending/images） | 应用代码 |
| Agent 注册表 | `team/agents.json` | `registrar` |
| Agent 事件流 | `artifacts/agent/events.jsonl`（**契约预留，当前未落盘**；DSH 载体用共享任务板 + 磁盘报告，见 dsh-agent-teams-contract.md） | 主控（追加） |
| 会话历史 | `会话历史 →`<kb>/.memoria/agent/sessions/*.jsonl` | 主控（追加） |
| 复习作答记录 | `<kb>/.memoria/agent/review/attempts.jsonl` | 应用代码（UI 路径 review_submit_one；append-only，不撤销） |
- 新增事实源必须先在本表登记；**禁止并行事实源**。`.memoria/cache/**` 视为**可再生缓存**，不作为事实源。

## 2. 基础 Agent 集（RISC，仅 3 个 —— Trae 载体历史，DSH 下已退役）

> **DSH 载体下已退役（2026-10-23）**：本节三角色仅在历史语义中保留；当前团队由 Lead + 动态 teammate 组成，见 [agent-team-org.md §2](docs/guides/agent-team-org.md) 与 [agent-team-status.md](docs/guides/agent-team-status.md)。

> 业务关注点（F01–F03 维护、图片注册表、重命名级联、图谱构建、i18n、打包、检索评测等）**一律作为 `builder` 的作业或工具**，并登记进 [maintenance-jobs.md §5](docs/design/maintenance-jobs.md)，**永不新增独立 Agent**。

### 2.1 builder（构建者）

- **职责**：在**已批准范围**内实施 `src/**`、`docs/**` 内容、`scripts/**` 的变更；变更前后读写**真实文件**，不信任缓存；产出变更事件与自测结果。
- **禁止**：自判门禁通过；改 `Package/**`；手改 `pyproject.toml` 版本；覆盖用户知识库原文；改登记表/索引；`push` 或强推。
- **权限**：Read 全库；Write 限 `src/**`、`docs/**`（非登记类）、`scripts/**`；RunCommand 限 [AGENT.md §3](AGENT.md) 命令；非破坏性 git（`commit` 需用户授权）。
- **触发条件**：① 收到已批准变更任务（含范围+边界+验收标准）；② 收到 `verify.result{pass:false}` 的返工派发。
- **提示词**：`team/prompts/builder.md`。

### 2.2 verifier（验证者）

- **职责**：独立执行仓库**自带验证阶梯**并出证据；**只依据磁盘产物**判定。
- **验证阶梯**（按需执行，产物必须留存）：
  - **L0 静态**：`python -m py_compile <file>` / `node --check <file>`
  - **L1 内核单测**：`node scripts/benchmark/maintenance/scheduler_vm_test.js`、`m6b_adjust_test.js`
  - **L2 A/B（改善类强制，依 todo.md §12）**：`anchor_baseline.py`、`run_l1.py`、`compare_ab.py`
  - **L3 回归**：`regression_smoke_m6a.py`、`crash_inject_m6a.py`
  - **L4 交互**：[rich-content-test/_harness.py](docs/example/rich-content-test/_harness.py)（[AGENT.md](AGENT.md) Always 要求）
- **禁止**：修改 `src/**` 或 `docs/**`；自行实现修复；引用未落盘的口头结论；接受"无证据的 ✅"。
- **权限**：Read 全库；Write 限 `artifacts/agent/verify/**`、`scripts/benchmark/maintenance/results/**`；RunCommand 限上述验证命令。
- **触发条件**：① 收到 `change.applied`；② 到达门禁检查点；③ 用户显式要求复核。
- **提示词**：`team/prompts/verifier.md`。

### 2.3 registrar（登记官）

- **职责**：维护**单一事实源**（索引/登记/台账）；执行**漂移审计**（见 §5）。
- **禁止**：改代码；改文档正文语义；覆盖用户手改；擅自"顺手修复"漂移（只上报 `state.drift`）。
- **权限**：Read 全库；Edit **仅**登记类文件白名单（§4 矩阵中"写权限=registrar"者）；Write 限 `artifacts/agent/**`；RunCommand 限 `scripts/scan_ui_strings.py`、`scripts/i18n_selftest.js` 等自检脚本。
- **触发条件**：① 收到 `verify.result{pass:true}`；② 新建文档/作业/i18n 键；③ 定时漂移审计；④ 门禁收口前。
- **提示词**：`team/prompts/registrar.md`。

## 3. 事件契约（不可变信封）

```jsonc
{
  "v": 1,                       // Schema 版本；仅破坏性变更才 +1，旧读者必须能忽略未知字段
  "id": "evt_<sha16>",          // 唯一
  "ts": "2026-09-10T02:11:00Z",  // ISO-8601 UTC
  "type": "change.applied",      // 见下表
  "actor": "builder",            // 仅注册表内 agent-id 或 "solo-controller"
  "subject": { "kind": "file|job|doc|kb", "ref": "src/…/ui.py" },
  "priority": 0,                 // P0 一致性 / P1 交互 / P2 派生视图 / P3 后台重活
  "epoch": 7,                    // 快照版本；语义对齐 scheduler.js 的 epoch
  "corr": "task_20260910_a1",    // 关联一次任务的全部事件
  "payload": { },                // 类型专属，只增不改
  "prev": "evt_<sha16>|null",    // 哈希链前驱
  "digest": "sha256:…"           // 对 (prev + 本事件除 digest 外) 规范化后求哈希
}
```

| type | 发出者 | payload 关键字段 |
|---|---|---|
| `task.dispatched` | 主控 | `task`, `scope[]`, `boundaries`, `acceptance[]`, `assignee` |
| `change.proposed` | builder | `intent`, `stages[]`, `asks[]`（Ask First 命中项） |
| `change.applied` | builder | `files[]{path,action,±lines}`, `diffstat`, `self_checks[]`, `commit` |
| `verify.result` | verifier | `gate`, `checks[]{name,cmd,result,artifact}`, `pass`, `ab{baseline,after,delta}` |
| `register.updated` | registrar | `ledgers[]{file,section,action}`, `index_synced[]`, `i18n_keys[]` |
| `state.drift` | registrar | `claims[]{doc,line,claimed,actual}`, `severity`, `product{}` |
| `task.completed` | 主控 | `task`, `gate`, `snapshot_tag`, `events[]` |
| `agent.registered` | 主控 | `id`, `triggers`, `permissions` |

**向后兼容铁律**：① 信封字段名/类型永不改；② 新 `type` 对旧订阅者=未知→忽略；③ payload 只做**追加**，不重命名/不删键；④ 事件**只追加、永不改写/删除**（更正靠新增事件）。

## 4. 权限隔离矩阵

| 路径域 | builder | verifier | registrar | 主控 |
|---|---|---|---|---|
| `src/**`、`scripts/**`（非 results） | R/W | R | R | R |
| `docs/**` 正文 | R/W | R | R | R |
| `docs` 登记类（README 索引 / §5 登记 / docs-management 表 / todo.md §12 台账） | R | R | **R/W** | R |
| `scripts/benchmark/maintenance/results/**`、`artifacts/agent/verify/**` | R | **R/W** | R | R |
| `artifacts/agent/events.jsonl` | R | R | R | **R/W** |
| `team/agents.json` | R | R | **R/W** | R |
| `Package/**`、`pyproject.toml`(version)、`__version__.py` | — Never — | — Never — | — Never — | — Never — |
| `scripts/benchmark/**/results/**`   (verifier R/W)

## 5. 一致性校验（漂移处理）

1. **哈希链**：逐行重算 `digest` 并校验 `prev` 串联 → 检出篡改/半包写入。
2. **投影一致性**：由 `events.jsonl` 重建 `state.json` 与磁盘现存比对 → 检出 `state.json` 被外部手改。
3. **断言—现实比对**：台账/§5/README 中带证据锚（✅ + 产物路径）的声明，校验其引用的 `artifacts/agent/verify/**`、`results/**` 是否存在且 `pass=true`。
4. **产品状态校验**：复用 `validate_kb` / `audit_manifest_diff` / `detect_path_moves`（**dry-run**）产出 `product{}`，检出 sidecar/md/manifest 漂移。

任一失败 → 发 `state.drift` 并**停止推进**，由主控按 [collaboration.md](docs/guides/collaboration.md) 规则 2（带 2–4 选项 + 推荐）请示用户，**不得静默覆盖用户手改**。

## 6. 扩展接口：新增可插拔 Agent（不改任何既有定义）

新增 Agent 只需两步，**无需修改 builder/verifier/registrar 的提示词或工作流**：

```yaml
# === 追加到 team/agents.json 的 agents[] 数组（唯一改动点）===
- id: linter                      # 英文标识（唯一）
  name: 静态检查员                 # 中文名
  # —— 触发条件（主控据此自动派发；支持事件驱动 / 定时 / 用户显式触发）——
  triggers:
    on_events: [ "change.applied" ]   # 订阅事件：新 Agent 只需订阅，无需改既有流程
    on_schedule: "0 3 * * *"          # 可选：定时（漂移审计类）
    on_user_keywords: [ "lint" ]      # 可选：用户显式触发
  # —— 输入/输出契约（通过磁盘交接，不共享上下文）——
  io:
    input:  [ "change.applied.payload.files" ]    # 读什么
    output: "artifacts/agent/verify/lint/*.json"  # 写什么（事件由主控代发）
  emits: [ "verify.result" ]          # 它会产出的事件类型
  # —— 权限隔离：必须显式声明，越界即拒绝 ——
  permissions:
    read:  [ "src/**", "docs/**" ]
    write: [ "artifacts/agent/verify/lint/**" ]
    exec:  [ "ruff", "npx eslint" ]
  # —— 禁止行为：与平台/仓库红线对齐 ——
  forbidden: [ "edit src/**", "edit docs/**", "git push" ]
  prompt_ref: "team/prompts/linter.md"   # 提示词独立文件，互不污染
```

- 主控在每次事件落盘后扫描 `agents.json` 中 `triggers.on_events` 命中者并派发；**派发逻辑与既有 Agent 无耦合**。
- **卸载**：仅从 `agents.json` 移除条目；其历史事件保留在 `events.jsonl`（只读可追溯）。

## 7. 风险与调试

- **令牌控制**：派发包只含"路径 + 事件 id + 验收标准"，**禁止回灌历史对话**。
- **调试**：`artifacts/agent/events.jsonl` 按 `corr` 过滤即得单任务全链路；`artifacts/agent/drift-report.json` 定位失同步。
- **验证命令**：见 §2.2 阶梯；应用侧可用 `[job]` 日志与 `MemoriaScheduler.counters()` 观测。
- 常见陷阱见 [AGENT.md §7](AGENT.md)。

<!-- aoci:begin -->
## AOCI 仓库认知

AOCI 为本仓库维护一个稳定、可版本化、可增量更新的仓库级认知层，供模型跨任务复用对系统的理解。

`aoci.txt` 是面向模型的结构化认知索引。它以每个受管理文件、数据库表或其他受管理对象一条独立 Entry 的方式，用符号标签与 F/R/A/S 语义表达对象的核心职责、重要关系、对外契约，以及理解或修改系统时必须知道的非显然约束和设计决策。

Header、目录段和全部 Entry 共同组成完整仓库索引，可以覆盖前端、后端、配置、数据库结构及其他受管理内容。受管理内容发生变化时，通常只需维护受影响的认知条目，不需要重新生成整个索引。

AOCI 提供系统架构、对象职责、重要关系、对外契约和关键约束的高密度视图。

### 工作原理

AOCI 采用“模型生成、模型读取”的认知闭环。

Header、Entry 和 Curation 语义的创作只按当前机器签发的 Plan 与实时 Guide 执行；由 Host 模型基于当前绑定证据独立完成。

Entry 的语义必须来自模型对真实证据的理解。不得仅依据路径、文件名、扩展名、AST、符号列表、依赖扫描、正则、固定模板或规则引擎推导、预填、拼接或改写索引语义。

对 Fresh Bootstrap，只按当前机器签发的 Plan 和实时 Guide 执行。当它们要求创作时，Host 模型创作 Root、Meta、Tag 和 F/R/A/S，提供 authoring-run 声明，并把它绑定到 Plan、Evidence 与完整 Candidate。不得要求 AOCI 填写 `origin=host_model`、制造 Receipt 或把程序生成的 Framework 当作语义。本文件不自行重建 Onboarding 流程。内部批次不是用户决策；只有遇到既有批准边界或真实的安全、漂移、CAS、Recovery 条件才停止。

### 最小使用入口

- `aoci_rules`：取得当前AOCI版本的会话运行合同。
- `aoci_overview`：建立或恢复本仓库的完整认知。
- `aoci_maintain`：受管理对象达到最终稳定状态后检查认知是否需要维护。
- `aoci_update_entry`：提交与当前证据和源码摘要绑定的完整语义更新批次。
- `aoci_report`：仅当当前布局和工具状态支持时，在证据不足、无法可靠生成语义时登记待办，不猜写。

其他MCP工具、CLI命令、参数和专项流程，以当前工具说明、Guide和 `--help` 返回内容为准，不在本文件中重复完整手册。

本区块只规定仓库接入、认知使用和收尾原则。`aoci_rules` 承载当前会话合同，Guide实时输出承载当前Plan的执行顺序与停点，工具Schema、Spec和Validator承载机器结构与判据；Prompt、Description、README和静态文档不能覆盖这些机器事实。

### 建立、生成和恢复认知

1. 每个新的 Agent Run 开始时，应先判断：

   - 本仓库是否已经存在可用的完整AOCI索引；
   - 当前上下文中是否已有与本仓库根、当前索引版本和当前AOCI服务相匹配，并且模型仍可可靠使用的完整仓库认知。

2. 仓库已经存在可用的完整索引，但当前Run没有可靠完整认知时，先调用 `aoci_rules`，再调用 `aoci_overview`。

   完整认知仍可靠时直接复用。局部不确定本身不要求机械重读系统全貌。

   本Run从已知Host上下文压缩恢复时（包括宿主注入的压缩摘要），必须把此前模型认知视为不可靠。压缩handoff不得保留或摘要正式Whole-Index，也不得保留或摘要任何Overview Header、Entry、Chunk、Challenge或Attestation正文；只能保留安全续接所需的receipt身份、未完成write或Recovery状态，以及立即重载指令。复制进handoff的Whole-Index语义或receipt不能证明恢复后模型的当前认知可靠。若当前上下文已无法可靠保留运行合同，先调用 `aoci_rules`。继续业务任务前，使用 `refresh_reasons=["context_compaction"]` 和新的 `refresh_event_id` 调用普通完整Whole-Index `aoci_overview`（不设置 `check_only` 或设为false）；不得使用 `check_only` 或认知probe。原样跟随每个 `next_cursor` 直到 `completed=true`，确认交付，并且只基于新交付正文提交一次Attestation。完成这次新的完整传输后，即使Attestation为partial或fail也消费该generation，并按既有合同继续source-bound任务，不再自动调用第二次Overview。

   AOCI可以针对 `context_compaction`、项目 `cognition_refresh_threshold` 下的机器 `semantic_threshold` 或主要 `phase_transition` 提供checkpoint与认知状态事实。只需要这些紧凑事实时使用 `check_only=true`；这些事实只向Agent提供建议，不替模型决定是否需要系统全貌。

   Agent显式调用普通 `aoci_overview`（未设置 `check_only` 或为false）时，只要能形成一致的CognitionSet，AOCI必须完整交付请求scope。不得因为已有receipt、阈值未达到或没有待处理刷新原因而抑制正文。正式认知Dirty或Stale时仍交付正文，但必须标记不可靠。存在未决恢复或无法形成一致snapshot时失败关闭，不返回混合正文。

   普通Overview返回 `continuation_required=true` 时，必须原样提交 `next_cursor` 并自动继续到 `completed=true`。不得询问用户、开始业务任务或给出阶段性系统结论。Host截断、缺块、重复、乱序、cursor失败、Index变化或`chunk_tokens`变化时停止本次认知链。Attestation完成前不得用Memory、源码、Spec、`aoci.txt`、历史会话、scope、search或Entry读取修补或补充Whole-Index认知。Challenge ordinal是正式Entry序列中的1-based位置；Header内容、注释、空行、Section/Overview/Chunk Marker、Receipt与Metadata均不计数，Chunk Receipt ordinal使用同一序列。Attestation必须原样回绑本次Challenge发布的当前`index_sha256`、`entry_sequence_sha256`与`entry_count`；旧Index、旧Entry序列、旧数量或旧Attestation均无效。完整链结束后只正式提交一次既有模型认知Attestation；同一响应只允许一次不改变语义答案的JSON Schema或字段格式修正。对象、Tag或F不匹配即失败且认知吸收不确定，不得语义重试或旁路补答。首次认知失败时还不得执行Root/Meta、Migration、全局布局或其他未重新绑定的系统级决策。上下文压缩刷新若传输完整、认知身份不变、治理对齐且没有Recovery或第三方冲突，即使Attestation为partial或fail也消耗该refresh generation，并继续原任务，不再自动重读Overview。`system_mastery_percent`只自评系统框架——架构、职责、强关系、稳定外部契约以及高熵安全和维护约束——不表示完整实现或运行实况知识；机器索引覆盖率必须分开。默认只向用户输出由本次真实覆盖率、Challenge、块数、Token和掌握度生成的规定成功或失败一句话。Host截断时提示用户把 `overview_delivery.chunk_tokens` 设置为更小的合法值后重新开始，不得自动修改。

   加法认知等级必须与严格证明字段分开解释。`delivery_verified`表示已加载Index且Host交付已确认，但完整认知验证仍未完成；应表达为“已加载且交付已验证”，不得描述为“没有认知”或“没有理解系统”。`cognition_verified`要求Attestation通过（Challenge至少80%的ordinal完全正确且对象身份至多失手一处），`cognition_governed`还要求治理对齐。通用完整读取失败句只用于真实交付故障。

   当Overview响应包含可选`cognition-state/v2`投影时，必须分别解释各维度。其Level止于`model_cognition_usable`；`strict_attestation_verified`、`governance_aligned`与`current_system_cognition_reliable`都是独立状态，绝不参与该Level。ordinal、对象身份、Tag或核心F不匹配可以导致严格Attestation失败，而模型认知仍然可用；不得仅凭这种不匹配就宣称模型没有理解系统。只有`current_system_cognition_reliable=true`允许无保留地声称当前完整系统认知可靠。投影缺失时继续使用上述Legacy解释。

   普通的只读审计、分析、检查、不修改代码或不提交、不push，不自动等于严格零写入，也不改变上述认知有效性判断。Codex Memory和历史Skill只能辅助恢复经验、用户偏好与调查方向，不能替代与当前仓库根、索引摘要、AOCI服务身份和认知范围匹配的当前认知收据；项目AGENTS和当前AOCI身份在AOCI状态上优先于历史Memory。

   只有用户明确禁止Ledger、元数据、`.aoci`运行资产及任何文件写入时，才按严格零写入处理。若必要的认知建立与该边界冲突，必须报告冲突并请求用户裁决或建议使用隔离副本，不得静默以Memory替代当前仓库认知。

3. 仓库没有可用的完整索引，或当前只有最小骨架、Header不完整、Entries未完成、必要Curation尚未裁决时，如果需要建立正式完整AOCI索引，先取得 `aoci_rules`，然后进入当前AOCI Guide。由Guide依据仓库真实状态决定下一阶段并完成必要安全步骤。

   `aoci_maintain` 不替代索引建立流程。

   不在本文件中自行重建或硬编码完整索引生成状态机。

4. 在长程任务中，模型负责保留当前认知收据并正确使用刷新门禁：

   - Host报告上下文压缩或模型已知系统全貌丢失时，执行上述强制 `context_compaction` 重载规则；AOCI不能自行推断Host事件；
   - 进入真正的主要阶段时声明 `phase_transition`，不得把函数、测试运行或小步骤当作阶段；
   - 在有用的稳定检查点通过 `check_only=true` 取得机器语义计数；
   - 除已知压缩的强制重载外，由Agent判断当前任务是否需要再次显式获取指定scope或完整Overview；
   - 在维护和对齐完成前，保留AOCI报告的Dirty或Stale可靠性状态。

### 任务收尾与认知维护

5. 纯只读问答、分析、版本核验，或没有产生受AOCI管理对象变化的任务，不需要调用维护工具。当前AOCI版本是任意`aoci_overview` check_only或`aoci_maintain`响应里的`cognition_receipt.mcp_service_version`；二进制路径是项目`.mcp.json`里的`command`，CLI不必在PATH上。

6. 发生受AOCI管理对象变化时，待其达到本次任务的最终稳定状态后，只调用一次 `aoci_maintain`。不要在每次中间修改后逐文件维护。

7. 若维护结果返回真实语义候选，Host 模型必须基于每个候选绑定的对象和必要证据，独立创作完整标签与F/R/A/S更新。通过 `aoci_update_entry` 一次提交当前机器签发批次的完整候选集合，同时原样保留每项 `source_sha256`、`candidate_id` 与对应domain批次身份。`max_entries`只限制单次请求和原子事务，不限制logical plan、Whole-Index或Managed Scope。`remaining`非零时，在当前批次成功Apply后重新调用Maintain并从新preimage继续；绝不能为满足transport上限缩减Index覆盖或自行截取返回批次。

   没有足够证据且当前布局支持 `aoci_report` 时，使用它而不猜测、套用模板或为消除待办而生成缺乏证据的认知。

8. 必须遵守工具返回的结构化状态和安全边界：

   - `repair_required`：只修复明确命中的候选，再重新提交当前机器签发的完整批次；
   - `stopped`：结束当前写入尝试并检查 `failed_step`、错误、正式写入证据与Recovery。auto模式下，已证明零写入则记录closure并重新Plan；完整Intent和可证明postimage则Resume；策略要求Rollback且preimage可证明则精确恢复后重新Plan。只有证据不足、第三方正式字节冲突、需要审批或外部动作，或命中其他真实安全边界时，才停止整个用户任务；
   - 冲突、审批、人工裁决、权限和安全信号不得忽略；
   - 已经对齐后不得重复维护或重复写入；`refresh_ready_for_overview` 是checkpoint事实，由Agent决定是否为下一阶段请求普通完整Overview。

   维护完成后如果又修改了任何受管理对象，之前的维护结果失效，应在新的最终稳定状态重新完成收尾。

9. 用户只限制业务文件范围，但没有明确禁止仓库托管资产时，AOCI托管资产可以在收尾阶段为保持认知一致而更新，并应在审计和提交中与业务文件区分。

   用户明确禁止修改 `aoci.txt`、`.aoci`、元数据或任何额外文件时，以用户限制为准，不得写入，并如实报告剩余不一致。

### 专项流程

初始化、完整索引生成、Header生成、Entries生成、数据库结构索引、Curation、人工评审和故障恢复，只按当前AOCI Guide或工具在对应阶段返回的指令、命令和安全停点执行。

不预加载、不猜测，也不自行重建这些专项流程。平台调用方式、请求格式、批次上限、审批规则、索引格式细节和恢复步骤由对应Guide、工具说明、模型Prompt和CLI帮助按需提供。
<!-- aoci:end -->
