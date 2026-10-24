# Agent 团队组织（工程维护基石）

> **定位**：定义 DSH 会话内 agent 团队的**常驻结构、领域所有权、派发规则与成本模型**。
> 补充 [dsh-agent-teams-contract.md](dsh-agent-teams-contract.md)（实操契约）与 [AGENTS.md](../../AGENTS.md)（角色骨架）。
> **状态**：生效中，2026-10-19。

---

## 0. 为什么要有这份组织文档（团队的真实作用）

团队的作用**不是"把活并行"**，而是**把 context 切开**：
一个 100 轮的长会话会让每句话都为整段历史付费（实测单会话可达千万级 token）。
按领域拆成窄上下文的 agent，每个只带自己那片知识，是降低 token 的唯一结构性办法。

因此三条推论：
1. **跨域知识必须落盘**（`docs/reference/agent-guide/0X-*.md` + AOCI），不能留在某个 agent 的脑子里 —— 否则它一结束知识就没了；
2. **派发必须先给对象认知**（见 contract §0.5），agent 只读增量、不重 grep 全貌；
3. **简单任务 Lead 直接做**，不进团队 —— 派发的固定开销（briefing + 往返）常常大于任务本身。

## 1. 三层结构

> **⚠️ 2026-10-23 第三轮复盘修正（重要，先读这段再读表）**
>
> 本节的「三层结构」是**设计意图**，不是实况。截至 2026-10-23 的实测事实是：
>
> ```
> L1「9 个常驻领域 Owner」中，14 天内有磁盘产出证据的 = 2 个（render-perf / sync-mapper）
> 其余 9 名常驻成员（含 todo-owner / team-curator）全部 inactive，且 0 条派发记录
> 真实工作模式 = Lead 一个人做 + 按需 spawn 一次性 teammate + Curator 按轮审计
> ```
>
> 因此下表要按**状态语义**读：`active`（14 天有证据）≠ `standby`（领域已登记、当前无活）。
> 「常驻」不等于「在运转」；把 standby 当 active 是本团队历史上最贵的一类自欺（见 §2.3）。

| 层 | 谁 | 生命周期 | 用途 |
|---|---|---|---|
| **L0 调度** | Lead | 整个会话 | 派发、裁决、扩权原子操作（git/大文件/删除）、最终验收 |
| **L1 领域能力（standby 池）** | 7 名常驻（5 领域 + 2 非领域） | 跨多个工作单元常驻（inactive 时零 token 成本，**只占名额**） | 各自领域内的分析、实现、复核；**有领域记忆** |
| **L2 一次性子代理** | `subagent` / `spawn_teammate` | 用完即弃 | 只读盘点、单点机械活、并发分片；**不占名额、不留上下文** |
| **L3 周期性审计** | Curator（按轮 spawn） | 每轮复盘 | 审计团队资产并**直接修改**；唯一持有团队定义写权限 |

**判据（2026-10-23 修订，原文「简单任务 Lead 直接做」保留）**：
- 需要跨多轮 steer、需要领域累积 → **L1**（但先确认它真的 active，否则等于派给一个不存在的人）；
- 一次性、只读、跑完即弃 → **L2**；
- 一两行改动能凭现有认知完成 → **Lead 自己做**；
- 团队自身资产（注册表/契约/组织/机检脚本）→ **L3 Curator**，不进领域 Owner。

## 1.5 实际运行形态 vs 书面形态（2026-10-24 自省，必读）

**这条是本组织文档最重要的诚实声明。**

### 真实运行形态（2026-10-24 一整天 174 个 commit 的实测）
```
Lead（1 个）              = 编排 + 独立验证 + 集成 + 发布，唯一有全局视野
按任务 spawn 的 deep 执行者 = 4 个，写域极窄、单任务生命周期、交付即退役
  · p0-selection      → task-79 五阶段 / task-83 / task-75 / task-84（7 commit）
  · boot-probe        → task-69 测量（5 个探针）
  · boot-fix-backend  → task-69 P0-a + P1 后端（2 commit，缓存 279×）
  · measurement-debt  → task-81 / task-82（4 个文件）
名册上 8 个「常驻领域 Owner」 → 本轮【全部零产出】（render-perf / sync-mapper /
  arch-contract / doc-consistency / metrics-baseline / todo-owner / curator-r3 / team-plugin-creator）
```

### 结论：不要假装常驻部门制在运转
书面结构说"5 个领域 Owner 常驻"，实际是 **Lead + 按需专家池**。
把这个差异写下来，比继续维护一个漂亮但没有执行力的名册更有用。

**因此，本组织文档的正确读法**：
| 层 | 真实作用 | 决策权 |
|---|---|---|
| **Lead** | 唯一编排者与验收者 | 全部 |
| **常驻领域 Owner（§2/§2.2）** | **按需召用的专家**（`send_message` 唤醒即用），不是"在岗" | 无（只出意见与产物） |
| **按任务 spawn 的执行者（§2.4）** | 真正的主力执行单元 | 仅其任务写域内 |

### 三条由此产生的纪律
1. **不要因为"名册上有人"就以为有人在干活** —— 判断依据是 `team_snapshot` 的
   `inactiveOwners` 与任务板的 `owner` 是否活跃，不是名册。
2. **主力任务优先派 ephemeral 执行者**（写域窄、生命周期短、好审计），
   常驻 Owner 适合"该领域需要长期口径判断"的场合。
3. **组织健康度看两件事**：① 任务板是否干净（无卡死/无无主）② 教训库是否在更新
   （`docs/guides/agent-team-lessons.md`，机检 `lessons_stale`）。

---

## 2. 常驻成员与领域所有权（当前 5 个领域 Owner；另有 2 个非领域常驻见 §2.2；4 个域已退役见 §2.3；上限 16）

| Agent | 领域所有权 | 对应对象认知 |
|---|---|---|
| `render-perf` | **渲染性能域**：首开/切页签/打字时延、内存预算、性能回归守卫 | `agent-guide/04-preview-and-rendering.md` + `design/benchmark-measurement-protocol.md` |
| `sync-mapper` | **编辑-预览同步域**：锚点映射准确度、选区与光标映射、双向同步 | `agent-guide/03-editor-and-formatting.md` + `design/edit-syntax-and-mapping.md` |
| `arch-contract` | **架构与契约域**：显示子系统契约 C1–C12、重构总纲与阶段裁决、`agent-guide/01`+`10` | `architecture.md` + `design/view-surface-contract.md` |
| `doc-consistency` | **文档一致性域**：文档↔代码审计、文档债、`agent-guide/06`+`07`+`08` | `docs/conventions/**` + 各 design 稿 |
| `metrics-baseline` | **度量与基准域**：真机/无头度量协议、基线与预算、交互金标准回归、渲染保真度指标 | `design/realapp-measurement-protocol.md` + `design/benchmark-measurement-protocol.md` + `design/render-fidelity-contract.md` |

> **名额口径**（2026-10-20 核实源码 `agent-team/src/roster.ts:63`）：`maxMembers` = **「每个 Team 的非退役 roster 条目上限」，即只数 teammate、不含 Lead**。
> 当前 roster 共 **5 名领域 Owner + 2 名非领域常驻 = 7 名 teammate**（+Lead = 8）/ 上限 16 ⇒ 还有 **8 个空位**。
> 2026-10-23 依 Curator r3 建议退役 4 名（kp-owner/settings-owner/surface-new/team-steward），
> 退役登记见下方 §2.3（**故意不用反引号首列**，避免被 `team_audit.py` 的 roster 机检当作「当前 Owner」）。
> 空缺领域（如 06 图谱本体、08 导入导出）默认走 L2 subagent；**只有出现长期、跨任务的领域责任时才升格为 Owner**。


### 2.1 动态维护能力（2026-10-20 起具备）

DSH 的 `agent-team` 插件此前**不能退役、不能改名**（roster 只有 `spawn`），导致团队一旦建立就被历史包袱锁死。我们在 DSH 侧补齐了三项能力（DSH 仓库提交 `468b01b5b2`）：

| 能力 | 工具 | 语义 |
|---|---|---|
| **退役** | `retire_teammate {target}` | 从花名册移除、释放会话、**释放名额**；journal 历史保留（只追加不删） |
| **改名/改描述** | `update_teammate {target, name?, description?}` | 新名成为 `send_message`/任务板 owner 的新 target |
| **提额** | `maxMembers: 8 → 16` | `agent-team-profile/cordis.patch.yml` |

**维护纪律**（必须遵守，否则又会退化成"历史包袱锁死"）：
1. **任务闭环即退役**：单点任务型 teammate（「修 X bug」「落地 Y」）完成后**当轮退役**，不留着占位；
2. **Owner 用领域命名**，不用「fix 型」命名（`jump-fix` 这类名字会让人误以为它只干过一次活）；
3. 退役前先确认它的产出已落到**磁盘报告/提交**（会话记忆不保留，退役即丢上下文）；
4. 改名后**同步更新本表与任务板 owner**（ownerName 由 roster 快照派生，改名会自动跟随，但本表要人改）；
5. **角色退役须留痕**：`agents.json` 标 `retired-in-dsh` + 理由 + 证据（不删除）；退役后必须过
   `python scripts/agent/team_audit.py` 的 `role_evidence` 检查（active 角色须有 14 天证据，
   否则会被判「幽灵角色」WARN）。

### 2.2 非领域常驻成员（当前 3 个，不计入 §2 领域 Owner 数）

名册里还有 3 个**有明确职责、但不按领域切分**的常驻成员（`list_agents` 可见；它们不出现在上表中，
以免污染 §2 的领域计数与 `team_audit.py` 的 roster 比对）：

| 成员 | 职责 | 与领域 Owner 的区别 |
|---|---|---|
| `todo-owner`（TODO 文档 Owner） | 维护 `docs/todo.md`、登记新缺陷/待办、审计陈旧与废弃项 | 不拥有代码领域，只维护单一台账；按 §2.1「任务闭环即退役」判断是否保留 |
| `team-plugin-creator`（DSH 插件改进者，Creator 模式） | 实现 `team-plugin-improvement-spec.md` 的 R1–R8（DSH 插件侧改动：roster 落盘 / 派发审计日志 / 强制 owner / complete 绑产物 / 快照生成 / 周期触发 / preset 暴露 / token 统计）；**唯一持有 DSH 插件源码与 preset 写权限的角色** | 不碰 Memoria 产品代码（`src/**`）与 Memoria 团队资产（`team/**`）；改动需重打包才生效 ⇒ 受 §13「打包是单向门」约束 |
| `steward`（团队管理员，2026-10-24 恢复） | **组织资产 + 成员工作记录 + 过程审计 + 协议演进**。维护 `team/agents.json` / 名册 / 工作记录三层（动作/任务/决策）；审过程不审结果；产出必须是**新机检**而非报告；**不阻断**（阻断权在机检/人）。**代次说明**：v4-pro 时代的 `curator-r3` 与 v4-pro 的 `steward` 首实例均已退役，当前为 flash 代（第二实例，同名复用）| 与领域 Owner：管全团队的过程与行为，不拥有产品领域；与 `todo-owner`：steward 管「怎么干」，todo-owner 管「干什么/先干什么」|

> > **2026-10-24 变更：Curator 已退役。** 人指令「团队统一 deepseek-flash，v4-pro 的删掉」——
> 最后一代 Curator 运行身份是 `curator-r3`（v4-pro，第三轮复盘）。其产出已沉淀为
> `docs/guides/agent-team-lessons.md`（27 条判据）+ 本文件 §1.5（运行形态诚实声明），
> 职责由 **Lead** 承担（§4 第 6 步「R1 级改动必须独立验收」）。
> 历史 spawn 名 `team-curator` / `curator-r3` 记录在 `agents.json → retired_agents[].roster_alias`，
> `team_audit.py::role_evidence` 按 `id ∪ alias` 匹配，故不会因换名假报幽灵角色。

> 口径（2026-10-23 Lead 更新）：`team_audit.py` 的 `roster` 检查**同时解析 §2 与 §2.2**：
> 合法快照成员 = §2 领域 Owner（9）+ §2.2 非领域常驻（3）= **11**；缺 1 个或多 1 个都会 FAIL。
> 另外 `role_evidence` 检查（`agents.json` active 角色的 14 天证据）独立覆盖 active 角色活性。
> 文档自述计数只约束 §2 领域 Owner（9），不含 §2.2。

### 2.3 状态语义与待执行的花名册动作（2026-10-23 第三轮新增）

**状态三分**（定义在 `agents.json` → `status_semantics`，此处只讲用法）：

| 状态 | 含义 | 机检要求 |
|---|---|---|
| **active** | 14 天内有可复跑证据，且可被指派新活 | `team_audit::role_evidence` 必须给它找到证据，否则报「幽灵角色」WARN |
| **standby** | 领域已登记、职责明确，**当前窗口无活** | **不要求**证据，也不算幽灵 ⇒ 把「占名额」与「在运转」分开 |
| **retired-in-dsh** | DSH 下无可派发身份，保留历史 | 必须在快照 `retired[]` 中，且不得再出现在 §2 当前表 |

**待执行动作队列**（Curator 只能提议；`retire_teammate`/`rename_teammate` 是 Lead 的 DSH 操作）：

待执行清单在 `team/agents.json` → `dsn_roster_actions.retire_recommended`（含每人理由 + 证据 + 吸收方）。
本轮推荐退役 4 名、保留 6 名 standby：

| 动作 | 目标 | 理由（可复跑） | 吸收方 |
|---|---|---|---|
| 退役 | `kp-owner` | 14 天 0 派发 / 0 任务板 owner / 0 专属产物；该域近 30 天无 src 变更 | Lead 直做 + L2 |
| 退役 | `settings-owner` | 同上（0/0/0） | Lead 直做 + L2 |
| 退役 | `surface-new` | 同上；近 3 天该目录改动作者均为 Lead | Lead 直做 + L2 |
| 退役 | `team-steward` | 职责已被 `scripts/agent/team_audit.py`（9 类机检）+ Curator 完全覆盖，人形 Owner 反而制造第二套口径 | 机检脚本 + Curator |
| 保留 standby | `arch-contract` / `doc-consistency` / `metrics-baseline` / `render-perf` / `sync-mapper` / `todo-owner` | 领域仍在（契约、文档、度量、渲染、同步、台账），但**按 standby 计** | — |

**执行纪律（否则队列会变成新的自欺）**：
1. Lead 执行 `retire_teammate` 后，**必须在同一轮** ① 更新本表与 §2.2、② 重导出快照、③ 从 `dsn_roster_actions` 删除该条目；
2. `contract_drift` D6 会校验「队列里的目标仍存在于 roster 快照」，残留即 WARN —— 用来防「已退休却仍挂在待办里」；
3. 未执行前，机检 `roster` 仍要求成员齐全，**不要先改文档再改名册**（顺序错了会 FAIL）。

> **为什么是「退役」而不是「删除」**：条目进 `retired_agents[]`，理由 + 证据保留，可随时复活。
> 代价只有 4 个名额；收益是新人读 org/agents 时不会再以为「有 9 个 Owner 在干活」。

### 2.4 按任务 spawn 的执行者（ephemeral，不计入常驻名册）

**背景（2026-10-24 新增）**：某些任务需要 deep 模式的长时执行者（如 P0 缺陷修复、跨文件测量工具改造），
它们只活一个任务周期，**不是常驻成员**。org.md 无法预知每次会 spawn 谁，因此不能靠本表登记。

**登记方式**：`team/agents.json → ephemeral_agents[]`，每条含
`id` / `purpose` / `task` / `spawned_at` / `dispose_when`。

**机检口径**（`team_audit.py::roster`）：
- 快照里出现**已声明**的 ephemeral 成员 ⇒ **INFO**（不计入常驻计数）
- 快照里出现**未声明**的成员 ⇒ 仍 **FAIL「名册漏登记」**（漂移检测强度不变）
- 期望总数 = §2 领域 Owner + §2.2 常驻 + 当前活跃的 ephemeral

> **2026-10-24 收口记录**：本机制上线当天 spawn 了 4 个 ephemeral，全部已退役、`ephemeral_agents` 现已清空：
> `p0-selection`（task-79 五阶段 + 83 + 75 + 84，7 commit）、`boot-probe`（task-69 测量，5 探针）、
> `boot-fix-backend`（task-69 P0-a 缓存 279× + P1 后端）、`measurement-debt`（task-81 + 82）。
> 其中后两个是 flash，前两个是 **v4-pro —— 已按 2026-10-24 人指令随之退役**（团队统一 flash）。

**收口要求**：任务 `complete` 后**必须 retire 该成员并从 `ephemeral_agents` 删除**，
否则它会以"已声明但已不存在"的状态残留（下一轮 Curator 审计会报）。

**为什么不用"放宽成 WARN"**：那会让「改名漂移」也一起被放过
（历史事故：`curator-r3` vs `team-curator` 曾导致 `role_evidence` 假报幽灵角色）。
显式名单既保留了强度，又承认了"按任务 spawn"这个真实形态。

### 2.5 已退役（2026-10-23 起；含 2026-10-24 的 v4-pro 退役）

> 依据：14 天内 0 派发 / 0 任务板 owner / 0 角色专属产物（`team/dispatch-log.jsonl` + 快照 + `git log`）。
> 保留描述供回溯；若该域重新有活，按 §2.1「按需 spawn」恢复，不预先占用名额。

| 原域 | 现状 | absorbed_by |
|---|---|---|
| kp-owner | 知识点面板/图谱联动/KP 抽取 | Lead 直做 + L2 subagent |
| settings-owner | 设置项/i18n/快捷键 | Lead 直做 + L2 subagent |
| surface-new | RenderCore 新渲染管线（P2–P4 已交付） | Lead 直做 + L2 subagent |
| team-steward | 名册/编制一致性检测 | `scripts/agent/team_audit.py`（9 类机检）+ Curator |
| **curator-r3**（v4-pro） | 团队策展/复盘（第三轮已完成） | Lead + `docs/guides/agent-team-lessons.md` + §1.5 |
| **p0-selection**（v4-pro，ephemeral） | task-79/83/75/84（已发布 0.4.6） | Lead 复核 + 已入库 commit |
| **boot-probe**（v4-pro，ephemeral） | task-69 测量阶段（根因已定位并修复） | Lead 复核 + `artifacts/agent/verify/boot-*` |

## 3. 领域覆盖与缺口（对照 agent-guide 10 篇）

| agent-guide 篇 | Owner | 状态 |
|---|---|---|
| 01 shell-and-layout | `arch-contract` | 兼任 |
| 02 file-tree-and-nav | `arch-contract` | 原 `jump-fix` 已退役（R4 已修 `c33c9353`） |
| 03 editor-and-formatting | `sync-mapper` | 原 `mapper-fix` 已退役（R3 已修 `79865b1d`） |
| 04 preview-and-rendering | `render-perf` | 原 `render-impl` 已退役（CHTML→SVG 已落地 `4a3e5a7d`） |
| 05 knowledge-points | （原 `kp-owner`，已退役） | 由 Lead 直做 |
| 06 links-and-graph | `doc-consistency` | 文档侧兼任；图谱本体重构范围外 |
| 07 search-and-images | `doc-consistency` | 文档侧兼任 |
| 08 import-export-and-check | `doc-consistency` | 文档侧兼任 |
| 09 settings-i18n-and-shortcuts | （原 `settings-owner`，已退役） | 由 Lead 直做 |
| 10 data-layout-and-host-embedding | `arch-contract` | 兼任 |

**下次扩编的判断标准**：只有当某领域出现**跨任务、反复出现**的工作（≥3 次派发）时，才从 subagent 升格为 Owner；否则一律 subagent。

## 4. 派发规则（Lead 每次派活前必须走这 6 步）

> **第 6 步（2026-10-24 新增）：R1 级改动必须独立验收。**
> 见 `docs/guides/agent-team-lessons.md §7` 风险分级。R1 = 单向门（打包/发版/改 tag/
> 强推/迁移数据）。**执行者自报不算验收** —— 必须由 Lead 亲跑门禁，或另派一个
> **未参与实现**的 verifier agent 复跑（它只看磁盘产物，不信报告）。
> 本轮实证：多个 agent 的「全 PASS」经 Lead 复跑后才发现探针口径错误（32 条假红、
> 基线 math/mermaid 的 0/4 是探针缺陷）。**「自己验自己」是本组织最大的单点风险。**


1. **查表**：这个任务属于哪个领域？§2 表里有 Owner 吗？
2. **有 Owner** → 派给它，briefing 只给「任务 + 验收 + 对象认知路径」，**不回灌历史对话**；
3. **无 Owner** → 派 `subagent`，同样只给对象认知路径；
4. **能自己做** → Lead 自己做（≤ 一两个文件的小改、纯查询、git 操作）；
5. **全程禁**：不整段回灌工具输出、不重复 grep 同一块、不为简单问题跑全量测试。

## 5. 知识存放（跨域复用的唯一载体）

| 知识类型 | 落点 | 不进哪 |
|---|---|---|
| 界面/交互现状 | `docs/reference/agent-guide/0X-*.md` | agent 上下文 |
| 设计决策与施工图 | `docs/design/*.md`（标明权威/过时） | 对话记忆 |
| 验证产物（一次性） | `artifacts/**`（不进 git） | docs |
| 代码结构认知 | AOCI 索引（正式认知层） | agent 记忆 |
| 团队自身规则 | 本文件 + contract | — |

**改完代码必须同步对应 agent-guide 章节** —— 否则下次派发又要重 grep，token 账会再涨回来。

## 6. 成本模型（为什么"简单对话"要便宜）

| 开销 | 量级 | 对策 |
|---|---|---|
| 会话历史累积 | **最大头**，每轮全量携带 | 长会话及时收口；简单对话开新会话 |
| 编辑 AGENTS.md | 每次 edit 触发全文重注入（25 KB） | 攒够一次改完 |
| 整段工具输出 | 单次可达数万 token | 一律 `Select-Object -Last N` |
| 全量 pytest | 1400+ 用例输出 | 只跑相关测试文件 |
| resumed 旧 agent | 携带其旧上下文 | 优先新建窄任务，不复用陈旧上下文 |

## 7. 演进记录

| 日期 | 变更 |
|---|---|
| 2026-10-19 | 初版：确立三层结构、8 个常驻 Owner 的领域表、10 篇 agent-guide 的覆盖缺口、5 步派发规则、知识落点与成本模型 |
| 2026-10-19 | 首轮全员激活：8 个 Owner 各确认领域并回报「最大未解决问题 + 建议下一单元」（见 §8） |
| 2026-10-20 | **团队重整（首次动态维护）**：退役 3 个任务已闭环的单点 agent（`render-impl`/`mapper-fix`/`jump-fix`）；3 个含糊命名改为领域名（`arch-agent`→`arch-contract`、`detail-agent`→`doc-consistency`、`metrics-agent`→`metrics-baseline`）；补 2 个缺口 Owner（`kp-owner` 知识点域、`settings-owner` 设置/i18n/快捷键域）；名额上限 8→16。前提是 DSH 侧补齐了 `retire_teammate`/`update_teammate`（DSH 提交 `468b01b5b2`），维护纪律见 §2.1 |
| 2026-10-23 | **团队载体收口（P1–P5）**：AGENTS.md 标注 Trae 三角色为历史；`agents.json` 重写为 DSH 角色能力目录（lead/executor/auditor/registrar/curator）；新增 append-only `team/dispatch-log.jsonl` + `scripts/agent/dispatch_log.py`；Curator 以 Creator 模式 teammate 上线（`spawn_teammate({mode:"creator"})`），首次审计产物 `team/curator/audit-2026-10-23/`；P5 经人类确认后清理 28 个未引用大文件（750.2 MB → 66.7 MB，`.md` 114 份保留） |
| 2026-10-23（第三轮，复盘） | **组织形态纠偏 + 机检扩到 9 类**：① §1 改写为「设计意图 vs 实况」（11 名常驻中仅 2 名 14 天有证据）；② 新增 §2.3 状态三分（active/standby/retired）+ 待执行退役 4 名 / 保留 standby 6 名；③ 新增 §13 Lead 代码独立审查的风险分级 R0/R1/R2 + 「新特性必须附不变量检查」三条判据；④ `team_audit.py` 新增 `silent_failure`（S1–S6）/`contract_drift`（D1–D6）/`commit_hygiene`（H1–H3），并修掉两处**假绿**（写域无输入仍报「无重叠」、12 条无主任务不告警）；⑤ `dispatch_log.py` 增加 done-无产物 fail-closed 拦截 + `corrects` 更正协议 |

## 8. 首轮全员回报（2026-10-19，各 Owner 自述 · **历史快照**）

> **阅读须知**：本表是 2026-10-19 的**原始快照，保留不删**（追溯用）。
> 其中 `render-impl` / `mapper-fix` / `jump-fix` 已于 2026-10-20 **退役**（任务闭环），
> `arch-agent` / `detail-agent` / `metrics-agent` 已改名为 `arch-contract` / `doc-consistency` / `metrics-baseline`。
> **当前名册以 §2 为准。**

| Owner | 确认领域 | 自报的最大未解决问题 | 建议下一工作单元 |
|---|---|---|---|
| `render-perf` | 渲染性能 | **预览缓存命中率 0%**：`_previewCacheStash` 早退条件（`app.js:13134` 的 `!state.doc.preview_body`、`:13133` 的 `_dirty`）让正在编辑的大文件永远进不了预览池 ⇒ 整篇解析 ~1s 纯亏 | 改早退为按 `fp` 指纹判失效，并用度量协议验命中率上升 |
| ~~`render-impl`~~（已退役） | 渲染实现 | CHTML→SVG 切换**已完成**（含 mapper/app/edit-handler 复核：`_isAtomElement` 用非结构化信号，SVG 下无需改动）。真实未收口仅剩 1 项：`app.js:11751` 导出路径 `svg.fontCache="local"` + `typesetClear` 可能致 `<defs>` 未重建、导出公式空（待真机验证）。另一条同批待验风险：SVG 用 `ex` 度量替代 `matchFontHeight`，字高/基线可能有细微差异 | 真机验证导出公式 + 公式行高抽查（该项需人在真机执行，非 agent 可闭环） |
| `sync-mapper` | 编辑-预览同步 | **R1 是单点放大器**：`app.js:1872` 末块判据全有或全无，一旦失效全文退回与 parser 平行的第二套启发式，R2/R5/R6 全在此时显形 | R1 改逐块守卫（`block.srcLineEnd <= srcLines.length`）+ 退化时打 `log("STAMP","fallback")` |
| ~~`mapper-fix`~~（已退役） | 映射实现 | `srcToAst` 的 LIST/BLOCKQUOTE 无专用分支（走单行 inline 口径、`nodePath` 可越界）；rawMarker 残余降 P2 | 补 LIST/BLOCKQUOTE 专用分支 + 纯 Node 验证（与 R3 同族） |
| `jump-fix` | 导航与跳转 | 4 条已知不准：重命名不重映射导航栈（`file-tree.js:51-73`）、导航失败不回滚 cursor（`app.js:6228-6240`）、树内点击回卷丢尾（`nav-stack.js:38-46`）、文档锚点已 +27 漂移 | 重命名后重映射 `MemoriaNavStack` 帧路径（含 `filePointer`） |
| `arch-agent` | 架构与契约 | 8 条脱节仍在（D1/D2/D3/D5/D6/D8/D9/D10）；**最大风险是三份文档互相声明自己是/不是事实源** | 产出《契约权威性裁决单》+ D1/D10 修法清单 |
| `detail-agent` | 文档一致性 | 3 条：①`agent-guide/04`+P 稿通篇 `m0/js/*` 旧路径（`m0/` 已不存在，锚点全失效）；②真源口径冲突未裁；③`docs/todo.md §13` 悬空 | 只读核查 06/07/08 三篇锚点与交叉引用，产出 drift 报告 |
| `metrics-agent` | 度量与基准 | `logCursorContext` 每键跑仍属最高优先，**但未被 raw 证明因果**（机制假设） | 探针里给 `write_map_log` 挂计数，把假设变成「每键 RPC 调用数」硬读数 |

## 9. 自维护约定与首例纠错（重要）

**自维护规则**（agent 如何维护本文档）：
1. **写者白名单**：本文档由 **Lead** 或 **Curator**（`docs/guides/curator-agent-prompt.md`）写；
   各领域 Owner **不直接编辑**（并行写同一文件必冲突）。
   > **2026-10-23 Lead 裁决**：原文写「Lead 单写」，与 Curator 职责（维护团队文档）冲突。
   > 规则的**目的是防并行写冲突**，而 Curator 是 Lead **串行派发**的单一角色，不存在并行冲突；
   > 且维护团队文档正是它的核心职责。故按「白名单」表述，保留对领域 Owner 的禁令。
   > 若未来 Curator 改为常驻并发角色，本条须重新裁决。
2. Owner 通过**回报**更新自己那一行：把「最大未解决问题 + 建议下一单元」发给 Lead，Lead 汇总落表。
3. Owner 可自行维护**自己领域的 artifacts 报告**（`artifacts/agent/verify/<owner>-*.md`），那是自由写区。

**首例纠错（2026-10-19，`render-impl`）**：
它回报「tex-svg.js 未落盘、刷新即 404、需 Lead 沙箱外复制」——**已证伪**：
`src/memoria/ui/static/vendor/mathjax/es5/tex-svg.js` 实际存在（2,108,580 字节，
SHA256 `D4295DC3…A882` 与源一致），探针残留已清，并已入 commit `4a3e5a7d`。

**根因**：它当年的复制失败留在了自己的上下文里，后续我在沙箱外完成的事实它无从得知
⇒ **陈旧上下文会把已解决的问题持续误报为待办**。

**教训（写入派发纪律）**：
- Owner 回报**未复核**的事实型结论时，Lead 必须**先验证再采信**（本次一验即破）；
- 给长期在岗的 Owner 派新活前，先下**上下文压缩指令**：让它保留「角色 + 已证实的结论 + 未解决问题」，
  **显式丢弃已被证伪/已由他人完成的旧结论**，避免用旧记忆否定新事实。

**压缩指令已实测有效（2026-10-19）**：对 `render-impl` 下达「作废旧结论 → 固化角色与已证实结论 → 重新回答未收口项」后，
它**自我纠错成功**并给出准确的剩余项（导出公式 `<defs>` 重建待验 + SVG `ex` 度量行高风险）。
⇒ **该指令应成为「Owner 长期在岗后接手新任务」的标准前置步骤。**

## 9.1 第二例纠错：**测量工具的错误会伪装成产品回归**（2026-10-20，Lead 自身事故）

**经过**：`render-perf` 完成 task-19（消除每键 148 次空操作）后，我（Lead）跑 11 条交互金标准 → **11/11 全红、520s**。
我做了 A/B：撤掉它的改动 → 11/11 绿；装回 → 全红 ⇒ **据此判定「它的改动有害」**。

**真相**：错的是**我的测量工具**。`scripts/benchmark/surface/interaction.mjs` 里 CDP 端口用
`9222 + Math.random()*3000` **猜**端口；两个 benchmark 并发时可能撞同一端口 ⇒ 后启动的 Edge 绑不上调试端口，
CDP 客户端于是**连到了另一个正在跑的页面**。症状恰好是 `window.MemoriaApp` 存在、
`window.MemoriaParser` 却 `undefined`、`#preview` 停在「预览模块未加载」静态占位。

**为什么 A/B 会骗人**：两次结果不同纯粹是**端口竞争运气**不同——A/B 只有在"唯一变量被隔离"时才成立，
而我的两次运行**环境本身不是隔离的**。

**修复**（`f6d08c20`）：`freeTcpPort()` 绑定 0 取真空闲端口 + **启动后断言 parser/lexer/mapper/renderer 四模块齐全**，
缺失即明确报「CDP 可能连到别的页面」，不再伪装成 45s 超时。修复后同一份代码 **11/11 绿、24.7s**。

**教训（写入度量纪律）**：
1. **先证明测量工具可信，再测产品**——工具故障的症状往往与产品缺陷一模一样；
2. **A/B 的前提是环境隔离**：并发跑同一套 harness 时，端口/临时目录/浏览器用户目录**都必须唯一**；
3. 出现「全红且每条都等满超时」时，**优先怀疑环境与工具**，不要先归因到被测代码；
4. **跨域结论（Lead 判定某 Owner 的改动有害）必须给出可复现的因果链**，仅凭一次 A/B 不够。

## 9.2 第三例：**"假通过"比 bug 更危险**（2026-10-20，`render-perf` 自我纠错）

它的等价性测试脚本初版报告「命中集合恒为 0 处差异」，看起来是完美通过。实际是：
`compareBoundaryPoints` 里用了裸标识符 `END_TO_START`（正确写法是 `Range.END_TO_START`），
在类方法里被解析成全局变量 → `ReferenceError` → **被既有 `try/catch` 吞掉** → `isCovered` 永远 `false`
⇒ 改造前后"永远一致"。

**它自己发现并留档**，修正后得到真实结论（14/14 场景 + 20,910 组端点穷举逐元素一致）。

**教训**：
1. **"全部一致"和"全部为 0"要先证伪**：结果过于完美时，先构造一个**必须失败**的用例；
2. 既有 `try/catch` 是**假通过的温床**：断言型代码绝不能放在会被静默吞掉的 try 里；
3. 报告里必须写**"我如何证明这个测试会红"**，而不是只写"测试通过"。



## 10. 收口体检清单（每轮收口前必跑）

> 目的：把「编制/任务/产物」维护从「Lead 碰巧注意到」变成「每轮必跑、有证据」。执行 `team-steward`（只检测+提议）；本清单 Lead 单写。

### 10.1 机检（4 条命令，2026-10-23 第三轮扩到 9 类检查）

| 命令 | 判据 |
|---|---|
| `python scripts/agent/team_audit.py` | 退出码 0（**FAIL=0**）才可收口；FAIL 必须当轮处置，或由 Lead 在收口报告显式豁免并写理由 |
| `python scripts/agent/team_audit.py --selftest` | 必须 PASS（红 fixture 报出 9 类检查共 20 项断言；绿 fixture 零 FAIL/WARN）——防「假通过」 |
| `python scripts/agent/dispatch_log.py check` | 退出码 0（派发日志存在、JSON 合法、最近一条 ≤7 天） |
| `python scripts/agent/dispatch_log.py --selftest` | 必须 PASS（红 7 类：缺文件/过期/坏JSON/缺字段/done无report被拒/corrects滥用被拒/默认路径回归） |

机检覆盖（9 类）：
1. `snapshot_health` 快照健康（存在/可解析/字段齐全/过期提示）
2. `roster` 名册一致性（§2 + §2.2 vs 快照 members/retired）
3. `stall` 卡死 **+ 无人认领**（pending 无 owner 也报，旧实现只扫 in_progress ⇒ 12 条无主任务全线静默）
4. `write_scope` 写域重叠 **+ 输入充分性**（全部缺 writeScopes 时报「输入不足/假绿」，不再输出「无重叠」）
5. `artifact_refs` 声称 ≠ 存在（报告内引用路径 + 任务交付物）
6. `role_evidence` active 角色 14 天证据（按 `id ∪ roster_alias` 匹配）
7. `silent_failure` **静默失败 S1–S6**（done 无产物 / 产物不存在 / 产物晚于结论 / spawn 未闭环 / 行序乱 / 闭环时间不可信）
8. `contract_drift` **契约漂移 D1–D6**（事件流路径 / 枚举与写入器一致 / 通道证据可指 / status 合法 / id 与名册对账 / 待办动作残留）
9. `commit_hygiene` **自修链 H1–H3**（自认修复前提交 / 同文件同日 ≥3 次 / feat 改 src 未附不变量）

报告落点 `artifacts/agent/verify/team-audit-<YYYYMMDD-HHmm>.md`。

### 10.2 五项人工确认

1. **名册 vs 文档**：§2 当前 Owner 表 = 平台 `list_agents` 的 teammate 集合（含 `team-steward`）；退役者只留 §8 历史。
2. **任务卡死**：快照 `in_progress` 任务，owner 须 `running` 或有**晚于快照导出时间**的新产物/新提交；否则当轮催办/改派。
3. **编制泄漏**：单点任务型完成即退役；领域 Owner 仅在领域已无后续活时退役；退役前确认产出已落盘（§2.1）。
4. **产物落盘**：报告「已交付/已落盘/已产出」必须指向磁盘真实文件；一次性产物标注可清理；机检 WARN 需人工判读并记录。
5. **写域**：并行 Owner `writeScopes` 不得重叠；`org.md` 等单写文档只由 Lead 写。

### 10.3 快照纪律

Lead 每轮收口前重导出 `team/team-board-snapshot.json`，导出时间必须**晚于最后一次任务状态变更与相关 commit**；`writeScopes` 取任务板最新 revision；`limit.currentMembers` 口径与 `members` 数组一致（**含/不含 Lead 必须写明**）。

### 10.3.1 派发日志纪律（2026-10-23）

- 每次 `spawn_teammate` / `send_message` / 收口后，Lead 用
  `python scripts/agent/dispatch_log.py append --actor ... --target ... --phase ...` 追加一条；
- 收口前 `python scripts/agent/dispatch_log.py check` 必须为 0；
- 日志只追加，不改历史行；回填历史用 `--phase backfill --ts <ISO8601> --source backfill:<证据路径>`。
- 详见 [dsh-agent-teams-contract.md §7](dsh-agent-teams-contract.md)。

### 10.4 边界

`team-steward` 只输出检测结论与提议；`spawn`/`retire`/`rename`/改本文件/改任务板均由 **Lead 执行**；结论必须带证据，未核实标「未核实」，不得推测。

## 11.3 读码陷阱：IIFE 内同名函数重绑（2026-10-21 立，由 5 次误判换来）

**现象**：`agent-panel.js` 里 `addSelectionToChat` 有 **3 处**定义（L3240 / L3426 / L3726），
`selectionLocation` 2 处，`formatRangeMention` 2 处。**后赋值覆盖前者**，生效的是**最后一处**。

**后果**：`grep` 取第一条匹配去读 ⇒ 读到的是**被覆盖的旧定义** ⇒ 得出"功能缺失"的错误结论，
进而派出"重造功能"的任务（本次差点造出第二套引用语法，违反 §6.21.1 明令）。

**规则（派单/评审前必须执行）**：
1. `grep` 命中 >1 处定义时，**必须以最后一处为准**（IIFE 内 `X = function(){}` 是重绑，不是新常量）；
2. 更可靠的做法：**用运行时探针确认生效实现**（`String(fn)` 取函数体 / 在页面里 eval 实跑）；
3. 判定"某功能不存在"之前，**必须排除"它已存在但被重绑"**。

**为什么这条特别贵**：前几次错误是"实现细节判断错"，改一处即可；
这一次是"认为功能不存在"，会**重复造功能并主动破坏已落地契约**。

---

## 11.4 风险规则的位置

**风险相关规则的单一事实源**：`docs/guides/risk-management.md`

包含：风险分级（可能性 × 影响）、**单向门 vs 双向门**判定、**pre-flight 清单**、pre-mortem、回滚计划要求、风险登记册（R-01…）、风险上报与关闭协议。

**派单时必须**：
1. 判定该任务是单向门还是双向门（§2）
2. 单向门 ⇒ 在 task 描述里写明 **回滚路径 + 起始 commit + pre-mortem**
3. R0（`I4` 数据损坏）⇒ **必须停下上报人类**，不得由 Agent 自行处置

---

## 12. 并发协议：写域与测量密封性（2026-10-21 立，2026-10-21 对齐业界术语）

### 12.0 术语来源

本节借用 Bazel 的 hermeticity 概念，而非自造规范：

- [Hermeticity](https://bazel.build/basics/hermeticity)：*"给定相同的输入源码和产品配置，密封的构建系统总是返回相同的输出，因为它把构建与宿主机变化隔离"*。两个关键方面：**Isolation（隔离）** 与 **Source identity（源码身份，用唯一哈希标识）**。
- [What Makes a Cache Hit](https://bazel.virtuslab.com/book/2~4~3/)：**Action Key = Inputs + Instructions + Execution Context**。三者任一变化，结果即可合法不同。

**官方列出的"非密封来源"中，第 4 条正是我们踩过的坑**：*"Writing to the source tree during the build — 第一次构建写入源码树，固定了目标 A 的源码树；然后尝试构建目标 B 可能失败。"* 我们的表现不是构建失败，而是**测量结果不可信**。

---

### 12.1 `write_scopes` 的正确用法

`write_scopes` 表达的是**互斥意图**（"这两个任务不应同时写同一处"），不是"我会碰哪些目录"。

- ❌ **错误**：所有任务都写 `artifacts/agent/verify/`（共用报告目录当写域）⇒ 全员互相告警，告警失去意义
- ✅ **正确**：写到**产物级**前缀，例如 `artifacts/agent/verify/p4e-*`、`artifacts/agent/verify/p4e_probe.mjs`

**判据**：如果两个任务**不会**同时写同一个文件，它们就不该有相同的 `write_scopes`。

### 12.2 测量密封性三要素

**真实冲突不是"两个 agent 写同一个文件"，而是"有人写 `src/**` 的同时，有人在用 `src/**` 做测量"。** 这种冲突 `write_scopes` 抓不到（一个是写，一个是读+运行），只能靠协议。

任何**对比型测量**（新旧双跑 / 性能前后 / 保真度 / 任何拿两次运行结果做比较的任务）必须固定并记录三项：

| 要素 | 要求 | 落地方式 |
|---|---|---|
| **Inputs** | ① `git status --porcelain -- src/` 必须为空<br>② HEAD sha 写进**产物文件名**<br>③ 若依赖 KB/语料，其 sha256 必须校验 | `-<sha>.json`；`run_p5_finalize.ps1` 的 `-ExpectSha` + KB sha256 guard |
| **Instructions** | ① 测量脚本自身 sha256 记进产物<br>② 命令行参数完整记录 | 产物 JSON 加 `protocol: {scriptSha256, argv}` |
| **Execution Context** | ① 并发浏览器/进程数<br>② 端口<br>③ 机器负载快照 | 产物 JSON 加 `env: {browserProcs, port, load}` |

**Inputs 不干净 ⇒ 拒跑**（不得静默继续，不得事后"标注一下"）。
**Instructions / Execution Context 变化 ⇒ 结果可合法不同**，必须在报告里显式声明，不得跨口径比较。

### 12.3 自检：null sequential build（官方方法）

Bazel 官方验证密封性的做法是 **"null sequential builds"**：

> *"如果你运行 make 并得到成功构建，再次运行构建不应重建任何目标……比较文件内容的哈希却得到不同结果，那么这个构建不可复现。"*

**移植到本仓库**：

> **同一 commit + 同一脚本 + 同一参数，连跑 2 次，两次产物除时间戳/路径外必须逐字节相同。**
> **若不同 ⇒ 测量本身不密封 ⇒ 该测量得出的任何"改进/退化"结论都不可用。**

**这是唯一能自动发现"测量本身有问题"的手段。** 今天所有误判（假绿/假红/假 diff）都源于测量不密封或判定口径错，而非被测对象真的退化。

**落地**：对比型脚本应支持 `--twice`（连跑两次并自比），或由执行者手工跑两次后 `diff` 产物。

### 12.4 今天的实际代价（记录在案）

| 事件 | 后果 |
|---|---|
| 测量期间 `src/**` 被改 | 矩阵跑了 3 轮不同代码版本的结果，**归因错了 3 次**（尾块 → 跨文档残留 → 代码版本不一致），耗费数小时 |
| 判定逻辑读不存在的 JSON 键 | `totals` 无 `schema_error` ⇒ `null -eq 0` 恒 False ⇒ **假红**，误以为从未通过 |
| 无 guard 的旧脚本 | 无法区分"真回归"与"跨版本噪声" |

**每次跨版本混跑的代价 ≈ 数小时排查**，远高于加 guard 的成本。

### 12.5 已实现 / 待接入

| 脚本 | Inputs guard | 产物带 sha | 自检（twice） |
|---|---|---|---|
| `run_p5_finalize.ps1` | ✅ src 干净 + KB sha256 | ✅ | ⏳ 待加 `--twice` |
| `fidelity_cli.mjs --cdp` | ⚠️ 部分 | ⚠️ | ❌ |
| `perf_ops_cli.mjs` | ❌ | ⚠️ | ❌ |
| `run_interaction.py` | ❌ | ⚠️ | ❌ |

---

## 13. Lead 代码的独立审查：风险分级与强制触发（2026-10-23 第三轮立项）

### 13.0 事实前提（可复跑，不是推测）

```powershell
git log --since="2026-10-23 00:00" --oneline | Measure-Object -Line      # → 73
git log --since="2026-10-23 00:00" --format="%an" | Sort-Object -Unique   # → 只有 Lead/人 一个作者
```

**73 个提交、0 次由第二方看过代码。** Lead 既是作者又是唯一审查者 ⇒ 自己的错误只能靠
「某个 agent 偶然读到那段代码」发现（清单 A1/A2 全靠 task-80 的偶遇）。这是**运气，不是机制**。

### 13.1 风险分级：什么改动**必须**派独立审查

判据必须能被一条命令判定，不能写「重要改动要审查」。分级只看两件事：
**不可逆程度**（能不能回退） × **验证盲区**（现有门禁能不能证明它对）。

| 级别 | 触发条件（任一命中） | 审查要求 |
|---|---|---|
| **R2 强制独立审查** | ① 触碰 `src/**` **且** 同一 commit 未附测试/探针（`commit_hygiene H3` 命中）<br>② 数据/迁移类：`artifacts/baseline-kb/**`、`<kb>/.memoria/**`、`team/agents.json` 结构、`Package/**`<br>③ 删除 ≥20 行或删文件<br>④ 今日同一文件已被改 ≥3 次（`commit_hygiene H2` 热点）<br>⑤ 自认「修复前提交引入的缺陷」（`H1` 命中）即**下一次**同类改动 | **提交前**必须由独立 teammate（`subagent` 或领域 Owner）做只读复核，产出 `artifacts/agent/verify/review-<sha>.md`；报告必须含「我构造了什么用例能证明它是红的」 |
| **R1 提交后同轮复核** | 触碰 `src/**` 且附带测试/探针；或改 `docs/guides/**` 契约类 | 可先提交，但**同一轮收口前**必须有一次独立复核（可以是 L2 subagent 的只读 diff 审查） |
| **R0 双向门** | 只改 `docs/**` 正文、`team/curator/**`、报告类；纯查询 | 不派审查；靠机检 + Curator 下一轮审计 |

### 13.2 「新增特性必须同时提交不变量检查」——可执行判据

**规则**：任何 `feat(` 提交若改 `src/**`，必须**在同一 commit** 内至少新增/修改一处
「该特性的不变量检查」（测试、探针、或基准断言），否则不得提交。

**怎么判断这条检查真的覆盖了新特性？**（这是问题里最难的一句，给三条硬判据）

1. **红过的证据**：报告里必须写明「我把哪一行改坏 → 该检查变红」（A2 的反例：`-src-block`
   数量 == AST 块数，这条不变量在 2eef3e34 提交时**不存在**，所以门禁全绿而 bug 已在）。
2. **断言对象是新特性本身**，不是它的邻居：检查必须能在**特性被删掉时变红**。可执行验证：
   在临时分支删掉特性实现，检查必须 FAIL（一次即可，留报告）。
3. **能指名失败模式**：检查名/注释必须写出它防的是哪个已知坏法（例：
   「嵌套 `<ul>` 不得带 `-src-block`」），而不是笼统的「冒烟通过」。

> 三条里缺任一条 ⇒ 视为「无覆盖」，`commit_hygiene H3` 仍会报，且该改动落入 R2。

### 13.3 机制而非纪律：三条落地

| 机制 | 位置 | 作用 |
|---|---|---|
| `commit_hygiene` 机检（H1/H2/H3） | `team_audit.py`，收口必跑 | 把「自修链 / 热点 / 无测试 feat」变成**每轮必列清单**，不再靠偶然发现 |
| 风险分级表（本节） | 本文件 | 派单/提交前 20 秒判定；R2 未复核 ⇒ 收口报告必须显式写「未复核 + 理由」 |
| 独立复核报告落盘 | `artifacts/agent/verify/review-<sha>.md` | 让「有没有第二个人看过」成为可查事实，而不是回忆 |

**成本控制**（为什么不是每个改动都派）：R0/R1 占日常改动 ~80%，零额外派发；
R2 按今日数据估算约 3–6 次/天（热点文件 10 次改 + feat 无测试 16 个里的一部分），
每次只读复核 ≈ 一次窄任务的固定开销 —— 远低于「一个静默 bug 花 1 轮真机验证白发」的代价。
