# 能力插件与写模块总设计（协议 · 写场景 · 模块设计）

> **用途**：承载产品内 Agent **能力插件与写模块的全部相关设计** —— ① **插件契约**（字段集 §1、暂缓字段 §2、上游对照 §3、待讨论 §4）；② **写场景清单**（今天 Memoria 到底支持哪些「写入形态」、哪些不支持、各落到哪个 op/原语，见 §7；场景间关系与排序见 §8）；③ **模块设计**（注册与装载 / 写管线 / 唯一写者 / 备份与撤销 / 计划 API / 编译器与校验器 / 权限与越界 / 四线落法 / M3 分期与安全门：**逐节自 [agent-capabilities.md](./agent-capabilities.md) §2 迁入**，迁移状态见 §6）。本文件是相关设计的**唯一事实源**；其他文档只留**指针**，**不得复制字段表**。
> **关联文档**：[agent-capabilities.md](./agent-capabilities.md)（**历史 / 路线图 —— 自 2026-09-20 起不再是事实源**；其 M3 模块设计将逐步迁入本文，见 §6）、[dsh-agent-port.md](./dsh-agent-port.md)（**移植总纲**：M1–M2 已落地，M3 写能力待拍板/待实施）、[preview-formats.md](../reference/preview-formats.md)（**正文书写格式与渲染语法权威**，§7 的「今天支持什么」逐处据它核对）、[agent-guide/README.md](../reference/agent-guide/README.md)（人 UI 现有写入路径的取证文档）。
> **状态**：**活文档 —— 由人逐步对齐**（2026-09-20 建立；同日由「最小协议」**重定位为「协议 + 场景 + 模块设计」总设计文档**）。
> **治理约定**：**人主导、逐步对齐；Agent 只追加、不改人已确认的条目**。Agent **只在被明确要求时追加**，**不得改写人已确认的条目**（字段、选项、结论一并适用）；每次改动经人确认后**由人自行定稿**。讨论未完的地方留在 §4 与 §7 / §8，只写"问题 + 可选项"，不代替人下结论。
> **事实源口径（2026-09-20）**：本文是能力插件与写模块相关设计的**唯一事实源**；[agent-capabilities.md](./agent-capabilities.md) **不再是事实源**（降级为**历史 / 路线图**，其 M3 部分将**逐步迁入**本文，见 §6）。**迁移完成前**，凡两份文档冲突处，**一律以本文为准**。
> 本文表内出现的 `§x` / `P9` 等编号，指 [agent-capabilities.md](./agent-capabilities.md) 的对应小节与待拍板编号（§6 迁移完成后改指本文）。

---

## 1. 最小可用契约 v1（6 字段）

> 用户口径（2026-09-20）：「能力契约我们慢慢完善，我们先以第一个写模块进行设计，只需要满足『最小可用契约字段集』，不要上来就框住，除非 dsh 上游有成熟的设计」。故本节只定**第一个消费者（写模块）今天真的会用到**的字段；上一轮 13 个字段的旧表**收缩为 6 个**（2026-09-20）。
> **准入规则（v1 唯一的字段裁判）**：一个字段要进 v1，必须满足**其一** —— ① **有真实消费者点名**（本节每行写清"谁读它、在哪一步用"）；② **照搬 dsh 上游的成熟设计**（必须点名只读检出 `dsh-src/` 的 `file:line`，且**语义与命名照它的**）。**两条都不满足 ⇒ 一律移出 v1**（进下方「暂缓字段」清单，并逐条给复评触发条件）。**不接受**"将来可能有插件需要"这类理由。

| 字段 | 必填 | 为什么需要（消费者是谁） | 上游对照 | 校验规则 |
|---|---|---|---|---|
| `id` | ✅ | 装载器：按 `id` 与库级 `enabled[]` 求交集与启用位（§2.2）；审计：每条 `capability/*` 带插件 id；冲突判定：两个声明同 `id` | **有据**：插件模块的稳定标识 `export const name`（`dsh-src/packages/fs/tool-fs/src/index.ts:19`）＋组合树条目 `id`（patch 以 `id` 定位，`dsh-src/apps/cli/src/profile-boot.ts:173`） | 英文 kebab-case、唯一；重复 ⇒ **装载失败**（不静默取其一） |
| `name` | ⬜ | 库级启停 / 插件列表面板的**人读标签**（`id` 是机器标识，不可替代）；§2.2 第 ③ 步"一条可见告警"指名插件 | **有据**：上游确有"发现 UI 用的展示标签"形态 —— `PresetSpec.name`（注释原文 "display label a client shows"，`dsh-src/packages/interaction/permission-presets/src/index.ts:62-71`）、`CommandDefinition.description`（"used in discovery UI"，`dsh-src/packages/interaction/commands/src/index.ts:66-67`） | 非空字符串；缺省回落 `id` |
| `provides.tools[]`（`tool_id` 必填；`constrain` / `gate` 可选） | ✅ | 装载器：`tool_id`（**必须**取自核心原语目录）+ 按 `gate` 决定该**领域动词**是否出现在模型可见工具面；**编译器 / `validate_plan`**：`constrain` 是参数收紧的唯一来源（§2.1.1 / §2.3.4，如边类型枚举取自 `graph.edge_types.EDGE_TYPES`）。**该工具只产出 plan、不落盘**（§2.3.3） | **本地自定**：上游**没有**"包声明工具清单"这种声明面 —— 工具是 `apply()` 里**运行时**注册的 `ctx.tools.register(definition)`（`dsh-src/packages/core/tools/src/index.ts:1043`）。仅**取值语义**对齐上游 `ToolSchema`（`name`/`description`/`parameters`，`dsh-src/packages/core/tools/src/schema.ts:483-498`；构造走 `defineTool` `:545`） | `tool_id` 不在原语目录 → **拒绝装载**；同一 `tool_id` 的同一动作类被两个插件声明 ⇒ 装载失败（§2.2） |
| `permissions.read` | ✅ | 装载器：声明的 `tool_id` 动作类必须落在声明面内（`read` 之外的 `tool_id` 一律拒）；§2.4 矩阵与 UI 展示"该插件可读范围" | **本地自定**：上游没有 per-plugin 读写 glob，只有**执行器级**档位 `SandboxMode = 'read-only'｜'workspace-write'｜'danger-full-access'`（`dsh-src/packages/sandbox/sandbox/src/index.ts:29`） | 相对库根的 glob；归一后落在库根外一律 Deny |
| `permissions.write` | ✅（有写动作类时非空） | **§2.4 apply 入口的路径校验读它**（glob + `os.path.realpath` 前缀校验 ⇒ 越界即拒，§2.3.1 第 3 条）；装载器：空 ⇒ 该插件不可写 | **本地自定**；语义对应上游 `workspace-write` 档且 workspace = 库根（§2.7 的"本地发明"口径不变） | 非空才可写；逐条 glob 做前缀校验；`.memoria/agent/sessions/**` 与 `.memoria/agent/backups/**` 不在白名单 |
| `approval` | ✅ | 审批策略在工具**分发前**读它（`services/agent/approvals.py:109-115`；即 §2.3 第 3 步"逐条确认"）；§10 P9 决定它能否被库级覆写 | 字段**本地自定**：上游审批是**运行时**询问 waterfall `approval/request`（`dsh-src/packages/interaction/user-approval/src/types.ts:85-89`），档位是**会话级** `ApprovalPolicy = 'ask'｜'never'`（`dsh-src/packages/interaction/user-approval/src/index.ts:60`）—— **没有**"插件按动作类声明档"的形态。**仅词汇对齐**：`ApprovalOutcome`（`allowed-once`/`rejected`/`cancelled`/`unavailable`，不可用即 fail-closed，`types.ts:32`） | **必须显式声明**，按动作类分档：`auto` / `confirm` / `never`。**安全下限：`permissions` 含 `write` ⇒ `approval` 不得为 `auto`**（硬校验，见 §10 P9）；v1 **不含 `exec` 字段** ⇒ **引入 `exec` 时该下限随之扩到 `exec`** |

> `provides.tools[]` 的两个子字段 `constrain` / `gate` 属**判断项、可再收紧**（是否留在 v1 见 §4）。
> 字段之外还有**一条铁律**（模块侧反复引用，见 [agent-capabilities.md §2.1/§2.2](./agent-capabilities.md)）：**插件目录内不含可执行代码**（无 `.py` / `.js` / 脚本），只含**声明 JSON + 只读资源**。

**字段演进（一）：删除 `kind`（2026-09-20）**：本契约**已删除 `kind` 字段**（原取值 `read` / `write` / `network` / `skill` / `host`）。用户口径原话：「那就不要写这个 kind 的字段，我们慢慢攒插件，后面才能知道有没有必要保留这个字段，以及怎么划分」——即**暂不引入分类维度**，等**复评触发条件：攒够 3–5 个真实插件**时再决定"有没有必要、按什么划分"。`kind` 原本承担的两件事就地改为：① **默认 `approval` 档**：**不由分类推导**，改为 `approval` **必须显式声明**（按动作类）+ 上表的安全下限（`permissions` 含 `write`/`exec` ⇒ 不得 `auto`）；② **UI 分组**：**暂不由契约决定** —— **UI 先按插件来源目录/名单分组**（内置 `resources/agent-capabilities/**` vs 用户 `<kb>/.memoria/agent/skills/**`），是否需要分类维度等上述复评后再定。

**内置声明实样**（`resources/agent-capabilities/kb-write.json`，随版本分发、只读）—— **只写 v1 字段集**：

```jsonc
{
  "v": 1,
  "id": "kb-write",
  "name": "写能力（建点 / 改点 / 连边 / 文件增删改）",
  "provides": {
    "tools": [
      { "tool_id": "kb.kp.create",   "gate": "always" },
      { "tool_id": "kb.kp.update",   "gate": "kb_has_sidecar" },
      { "tool_id": "kb.link.create", "gate": "always", "constrain": { "type": { "enum_from": "graph.edge_types.EDGE_TYPES" } } }
    ]
  },
  "permissions": {
    "read":  [ "**/*.md", ".memoria/**" ],
    "write": [ "**/*.md", ".memoria/sidecars/**", ".memoria/manifest.yaml", ".memoria/pending.json" ]
  },
  "approval": { "read": "auto", "write": "confirm" }
}
```

> `v` 是**声明文件的信封版本**（"只增不改"，语义对齐 [AGENTS.md §3](../../AGENTS.md) 的事件信封与 §10 P12 的 plan 版本口径），**不占**上表字段位。上方「暂缓字段」里的键**不写进声明文件**。

**库级启用实样**（`<kb>/.memoria/agent/capabilities.json`，随库走、用户可改）：

```jsonc
{
  "v": 1,
  "enabled": [
    { "id": "kb-write",       "on": true,  "config": {} },
    { "id": "web-fetch",      "on": false, "config": {} },
    { "id": "kb-skill-local", "on": true,  "config": {} }
  ]
}
```

> `enabled[]` 就是**库级注册表**（§2.2 位置 2）：**条目存在即启用**，故契约层**不再需要 `enabled` 字段**（见下方「暂缓字段」）；`config` 的**值位保留**，但 v1 没有参数 schema ⇒ 值暂不校验（一律空对象）。
> 注意 `kb-write` 的 `permissions.write` **不含** `.memoria/agent/sessions/**`：审计事件是**核心**写的，不是插件写的 —— 这正是 §2.3.1「插件物理上不能越界」的一个可核实例；也**不含** `.memoria/agent/backups/**`（§2.3.2 第 4 条：插件既写不了、也删不了备份）。

---

## 2. 暂缓字段（不在 v1）

**暂缓字段（不在 v1）**：按下表逐条移出，**每条都给复评触发条件**（不写"将来再说"）；复评时按 §1 准入规则重新过一遍，过了才回到字段表。

| 暂缓字段 | 移出理由（v1 下它没有消费者） | 再引入的触发条件 |
|---|---|---|
| `provides.prompt` | 写模块的模型可见文本由**核心** system 段落 + 工具 schema（`description`/`parameters`）承担；v1 没有需要 per-plugin 注入的提示词段落 | 出现第二个**必须自带提示词段落**的插件（N 线域名/私网策略、S 线 `SKILL.md` 正文）且核心段落装不下时；**且**须先定两条校验：与它的工具**同门控**、不得写进 `resources/agent-prompts/**`（既有事实源） |
| `permissions.exec` | §2.6 明确 M3 不做命令执行 ⇒ 没有 exec 动作类，字段既无校验对象也无消费者 | 出现第一个真要跑外部命令的插件，**且**沙箱/白名单方案单独评审通过时；同时把 `approval` 的安全下限扩到 `exec` |
| `permissions.network` / `permissions.host`（动作类列） | v1 只开 `read`/`write` 两类动作；N/S/H 三条线未开工（§2.5） | N1 / H1 各自引入与 `net.*` / 宿主原语配套的动作类时；此前 §2.4 矩阵对应列不发生效 |
| `forbidden` | 纯文本、无程序消费者；它列的禁项今天已由**结构**保证（插件目录无代码 §2.2 + `permissions.write` 白名单 + realpath 前缀校验 §2.3.1 + apply 入口唯一写者 §2.3.2） | 出现"必须由声明驱动、装载器能**机检**"的禁项（如某插件须禁 `git` 而权限面表达不了），**且**同时有装载期或调用期检查器 |
| `config`（**参数 schema**；库级 `config` **值位**保留，见 §2.2） | v1 的 3 个 op 没有需要用户调的参数（批量上限、删文件开关都属 M3b） | 出现第一个必须由用户调参的插件行为（`max_files_per_apply`、`allow_file_delete` 之类）；须同时定"声明侧给参数名/类型/边界、库级只存值"的分工与超界校验 |
| `emits` | 审计事件名今天由**核心**写（`capability/proposal`｜`apply`｜`reject`｜`backup`｜`undo`，§2.3 / §2.3.2），插件不产生自有事件 ⇒ 没有"按声明过滤"的消费者 | 出现**插件自有**事件名（第三方插件的领域事件）且核心的追加通道需要按声明白名单过滤时 |
| `verify` | v1 的自证是**模块级**：§2.6 四道安全门 + 证据锚落 `artifacts/agent/verify/**`；只有一个内置插件时 per-plugin 单测/harness 路径是空转 | 出现第 2–3 个插件（各自需自证）或要做**第三方插件准入**评审时；须同时定"缺失是否拒载" |
| `provenance` | 唯一内置插件 `kb-write` 的移植面已写在 §2.7 与根 `THIRD_PARTY_NOTICES.md`，per-plugin 字段冗余 | 出现真正 `ported-from-dsh@<pin>` 的第二方插件时；须与根 `THIRD_PARTY_NOTICES.md` 联动校验 |
| `unload` | v1 只有 `restart` 一种可能（没有热卸载消费者） | 出现热卸载需求（H 线常驻插件 / 前端挂载点）**且**给出卸载用例时 |
| `enabled`（库级开关） | **契约层冗余**：库级启停已由 `<kb>/.memoria/agent/capabilities.json` 的 `enabled[]` **条目存在性**承担（§2.2）；上游同样落在**条目级**（`dsh-src/apps/cli/src/profile-boot.ts:173` 的 `{ id, disabled: true }` patch） | 同一 `id` 需要按作用域（目录/会话）多份启用记录，或需要"随版本分发但默认关"的第三态时 |

---

## 3. 上游事实（供对齐用）

> 只读 `dsh-src/`（pin `0d1f5000`）核对，**结论不改**：上游**没有**本契约的三个"声明面"，故这三处只能是本地发明（或本地转译）。

| # | 结论 | 证据锚（`file:line`） |
|---|---|---|
| 1 | 上游**没有**"包声明工具清单"这种声明面 —— 工具是 `apply()` 里**运行时**注册的 | `ctx.tools.register(definition)`：`dsh-src/packages/core/tools/src/index.ts:1043`；取值语义对齐 `ToolSchema`（`name`/`description`/`parameters`）：`dsh-src/packages/core/tools/src/schema.ts:483-498`，构造走 `defineTool` `:545` |
| 2 | 上游**没有** per-plugin 的权限/审批声明 —— 权限只有**执行器级**档位、审批只有**会话级**档位 | `SandboxMode = 'read-only'｜'workspace-write'｜'danger-full-access'`：`dsh-src/packages/sandbox/sandbox/src/index.ts:29`；`ApprovalPolicy = 'ask'｜'never'`：`dsh-src/packages/interaction/user-approval/src/index.ts:60`；运行时询问 waterfall `approval/request`：`dsh-src/packages/interaction/user-approval/src/types.ts:85-89` |
| 3 | **启用与配置在组合层**（不是包自声明）—— 组合树按条目 `id` 打 patch | `dsh-src/apps/cli/src/profile-boot.ts:173`（`{ id, disabled: true }`） |
| 4 | **`ApprovalOutcome` 含 `unavailable` ⇒ 不可用即 fail-closed**（本契约 `approval` 的词汇对齐它） | `dsh-src/packages/interaction/user-approval/src/types.ts:32`（`'allowed-once'｜'rejected'｜'cancelled'｜'unavailable'`；`types.ts:30` 注释 "Callers fail closed on `unavailable`"） |

---

## 4. 待讨论（写组件细节）

> 只列**问题 + 可选项**，**不预设结论**；由人逐步对齐。口径细节见 [agent-capabilities.md](./agent-capabilities.md) 对应节与 §10 待拍板。

| # | 问题 | 可选项 |
|---|---|---|
| Q1 | `name` 是否保留（去掉即**5 字段**） | ① 保留（人读标签；缺省回落 `id`）② 去掉（`id` 足够，UI 标签用 `id` / 来源目录） |
| Q2 | `constrain` / `gate` 是否留在 v1 | ① 都留（写模块今天就用：`enum_from` 收紧参数、`gate` 门控可见性）② 都移出（进 §2 暂缓清单，等第二个消费者）③ 只留其一 |
| Q3 | 首批 op 个数（[§10 P8](./agent-capabilities.md)） | ① 三个（`upsert_kp` + `attach_links` + `detach_links`）② 五个（再加 `set_kp_range` + `rename_kp`）③ 一个（只有 `upsert_kp`） |
| Q4 | `approval` 覆写口径（[§10 P9](./agent-capabilities.md)） | ① 不可覆写（库级只接受启停位与 `config` 值；审批档是安全不变量）② 可覆写（需醒目告警 + 额外审计；与装载期硬校验的冲突待解） |
| Q5 | 备份保留口径（[§10 P10](./agent-capabilities.md)） | ① 写前快照 + 会话内撤销 + 每会话 5 批 / 每库 64 MiB（FIFO，最新批次永不淘汰）② 完整历史（可撤任意批次，存储线性增长）③ 仅审计重放（不保证逐字节） |
| Q6 | plan 版本号 / 兼容承诺（[§10 P12](./agent-capabilities.md)） | ① plan 自带 `v`、"只增不改"，未知 `op`/字段 ⇒ 拒整批 ② 无版本号（靠工具 schema 隐式约束）③ 完整版本协商（`v` + `min_compiler` 区间） |

> **已拍板（2026-09-20，人）：Q3 = ①三个**（`upsert_kp` + `attach_links` + `detach_links`）、**Q5 = ①写前快照 + 会话内撤销**（每会话 5 批 / 每库 64 MiB，FIFO；**最新批次永不淘汰**）、**Q6 = ①自带 `v` + "只增不改"**（未知 op / 字段 ⇒ 拒整批）。三者逐条对应本表选项①；**Q1**（`name` 去留）/ **Q2**（`constrain`/`gate` 去留）/ **Q4**（`approval` 可否覆写）**仍待定** —— 它们只影响插件契约字段面，**不阻塞第二个写闭环起步**（该闭环按 op 与备份口径动工，不依赖这三项）。

---

## 5. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-20 | 本轮建立。契约正文自 [agent-capabilities.md](./agent-capabilities.md) §2.1 **迁出**：6 字段最小可用契约 v1 + 准入规则（§1）、10 条暂缓字段（§2）、上游事实三条 + `ApprovalOutcome`（§3）、待讨论 Q1–Q6（§4）；两份 JSON 实样与 `kind` 删除演进随迁。`agent-capabilities.md` §2.1 只留指针，§11 追加说明；登记 `conventions/docs-management.md §4.2` |
| 2026-09-20 | **重定位为「协议 + 写场景 + 模块设计」总设计文档**（用户口径：「这个文件不是只用于协议，所有相关设计都放在这，旧的我们不作为事实源；先讨论插件几种写场景……」）。① 标题由「能力插件最小协议 v1」改为「能力插件与写模块总设计」；头部「用途 / 关联文档 / 状态 / 治理约定」相应改写，并新增**事实源口径**一句：本文为**唯一事实源**，[agent-capabilities.md](./agent-capabilities.md) **不再是事实源**（降级为**历史 / 路线图**，M3 逐步迁入本文；**迁移完成前冲突处一律以本文为准**）。② 新增 **§6 迁移清单**（15 行：§2.1.1 / §2.2 / §2.3 / §2.3.1 / §2.3.2 / §2.3.3 / §2.3.4 / §2.4 / §2.5 / §2.6 / §2.7 与 §8 / §9 / §10 中与写模块相关的行，逐行标 `未迁`；**本轮不搬**）。③ 新增 **§7 写场景清单（讨论中，2026-09-20）**：一张表 **44 行**（1.x 九行 / 2.x 八行 / 3.x 五行 / 4.x 八行 / 5.x 五行 / 6.x 九行），覆盖纯知识库维护 / 文件内容增删改 / 字体样式 / 图片引用 / 代码块书写 / 读码新发现的写入形态（侧车重建、pending、锚点重锚、路径级联、会话与配置面），每行给「现状（`file:line` 或"无"）+ 落到哪个 op / 原语 + 是否需新原语（暂定名）+ 审批档建议（标"待定"）+ 归属」。④ 新增 **§8 场景间的关系与排序建议（讨论用）**：共用原语分组、依赖关系（连边依赖 KP 存在等）、候选第一批（标"待你拍板"）、以及**判断今天不该给 agent 做**的场景及理由。⑤ **§1–§5 编号与内容不变**（新增节追加在 §5 之后，编号连续）。**docs only，未改任何源码**；`agent-capabilities.md` 仅 §2.1 指针补一句 + §11 追加一行；登记 `conventions/docs-management.md §4.2`；`docs/todo.md` **未改动**（AG04 行引用的 §2/§10 内容仍在原文，字节中性） |
| 2026-09-20 | **M3a 只读骨架第一片落地（首次有源码）**：新增 `src/memoria/services/agent/plan.py`（plan schema + `validate_plan` / `preview_plan` / `resolve_target`，**零 apply 函数**）+ `tests/test_agent_plan.py`（10 例）。**两条实证结论请人复核并据此校正 §2.3.3 / §2.3.4（本轮只登记，未改那两节正文）**：① **`scan_link_text_matches()` 不产出纯文本出现** —— 对纯文本正文它只回 `'。注意力机'` / `'在别处。'` 这类**模糊建议命中**（实测三种 `search_options` 组合结果一致），它匹配的是**既有 wikilink 路由 + 建议**；纯文本出现（即 `attach_links` 要落的那种）由 `wrap_plain_on_lines()` 内部调用的 `find_plain_text_in_line()` 定位 ⇒ §2.3.3「编译器要解析」列里写的 `scan_link_text_matches` **对纯文本不成立**，本片改用后者（候选行与包裹位置因此由**构造**保证一致，仍满足"同一套校验器"硬不变量）。② **`normalize_link_edge_type()` 对未知值一律回落 `reference`** ⇒ 单看归一化结果会把 `contain` / `prerequisite` 放行；卡白名单必须卡**原值**（本片先卡原值再归一化）。另记一条范围口径：`preview_plan()` 的"零落盘"= **不写事实源**（md / sidecar / manifest / pending 逐字节不变），但复用的 `resolve_link_target()` → `build_kp_index()` 会补写**可再生缓存** `.memoria/cache/search_aux/kp/*.json`（[AGENTS.md §1](../../AGENTS.md)：`cache/**` 不作为事实源）—— 测试已逐文件钉住"只碰 cache"。**未做**：四个只读面的 RPC 暴露、前端确认卡、`set_kp_range` / `rename_kp` 的编译、`detach_links` 的正文 diff 试算、`upsert_kp` 的 sidecar 终校。登记 `conventions/docs-management.md §4.2`；`docs/todo.md` 未编辑（另一写者并发重写中） |
| 2026-09-20 | **拍板回填 Q3 / Q5 / Q6（人已确认，全部取选项①）**：Q3 = 首批**三个 op**（`upsert_kp` + `attach_links` + `detach_links`）、Q5 = **写前快照 + 会话内撤销**（每会话 5 批 / 每库 64 MiB，FIFO，最新批次永不淘汰）、Q6 = plan **自带 `v` + "只增不改"**（未知 op / 字段 ⇒ 拒整批）。记录位置：本节末 §4 表下新增「已拍板」块（**只追加，未改 Q1–Q6 原行**）。Q1 / Q2 / Q4 仍待定且**不阻塞**第二个写闭环。**顺带定下第二片（写入闭环）的施工顺序**（不新增契约、不改人已确认条目）：① **备份子系统先行**（Q5 已定，它是所有写场景的前置，且**零事实源写入**可独立验收）→ ② 三个 op 的 apply（编译器产物 = 原语调用序列，写前取 pre-image）→ ③ 审批 + 审计（`approval` 档位待 Q4）→ ④ 四个只读面 + apply 的 RPC 暴露与前端确认卡。**本轮 docs only，未改任何源码** |
| 2026-09-20 | **备份子系统落地（第二片 ①：写前 pre-image + 保留 + 撤销的数据面，Q5 = ① 已拍板）**：新增 `src/memoria/services/agent/backup.py` + `tests/test_agent_backup.py`（**9 例**）。**① 逐条照 §2.3.2 落地**：目录 `<kb>/.memoria/agent/backups/<session_id>/<txid>/{journal.json, files/<原相对路径>}`；粒度 = 一个 `txid` 一个批次；新建文件记 `{"existed": false}` 且**不留字节**（撤销 = 删除）；**原字节复制**（不存 diff，不重新编码/不规范化换行）；上限 **8 MiB / 32 MiB** 超限即**预检失败且不留半个批次**（不降级为"无备份的写入"）；保留 **5 批/会话**、**10 个会话目录/库**、**64 MiB/库**，FIFO 且**永不淘汰当前会话最新批次**；撤销前比对 sha256，不符即**拒绝**（不静默覆盖用户手改）；撤销失败**保留备份 + 如实报错**。**② 两处本地补充（请人复核后并入 §2.3.2 正文）**：㈠ **批次目录整体原子落位**（先在 `<txid>.tmp-<pid>` 建齐 `files/**` 与 journal，再 `os.replace()` 整目录改名 ⇒ 任何失败都只需删临时目录，**不会留半个批次**）；㈡ **新增 `post.json`** —— §2.3.2 第 2 条列的 journal 字段只有 **pre-image** 哈希，而第 5 条要求"撤销前校验当前 sha256 == **apply 时**记录的 sha256"，apply 又发生在 journal 落盘**之后** ⇒ pre-image 哈希当不了这个凭据；故增 `record_post_images()`（apply 四原语后由 apply 入口调用一次，落**写后**逐文件哈希），撤销自动读它校验，**缺 `post.json` 默认拒绝撤销**（fail-closed；`allow_unverified=True` 仅供人工处置且如实标 `verified:false`）。**③ 测试自己抓到两个真问题（已修）**：㈠ **整批全是新建文件时临时目录没建** ⇒ journal 写不进去（补 `os.makedirs(tmp_dir, exist_ok=True)`）；㈡ 绝对路径被 `lstrip("/")` 后**悄悄当相对路径用**（`/etc/passwd` → `<kb>/etc/passwd`，静默改语义）⇒ 改为**绝对路径一律拒**，且调用方不再做"宽容归一化"。**④ 验收**：`pytest tests/test_agent_backup.py -q` **9 passed**、`pytest -q` **375 passed**（原 366）；测试逐条钉住"除 `.memoria/agent/backups/**` 外逐文件不变""字节级撤销往返""apply 后被手改 ⇒ 拒绝且不覆盖""缺 post.json 默认拒""FIFO 淘汰且最新永不淘汰"。**⑤ 未做（如实）**：`capability/backup` / `capability/undo` 事件与审计、撤销的 `approval=confirm`、打开/关库时的 trimming 挂点（属第二片 ③④）；撤销后的一致性恢复（清 `DocumentService._cache` + `validate_kb()`）留给 apply 网关。登记 `conventions/docs-management.md §4.2`；`docs/todo.md` 未编辑（另一写者并发重写中） |
| 2026-09-20 | **② apply 入口落地 + 修掉一个阻塞它的产品缺陷**：新增 `src/memoria/services/agent/apply.py`（编译器 + apply 入口 + 整批回滚）+ `tests/test_agent_apply.py`（8 例）。**调用序**照 §2.3.2 第 4 条：`validate_plan` → `snapshot_pre_images` → **原语白名单**（`confirm_kp_range` / `update_kp` / `apply_link_instances` / `detach_link_instance` / `delete_link_route` 五个落点，别的一律不可达）→ `record_post_images` → 机会式 `trim_backups`；任一步失败 ⇒ 用该批次 pre-image **整批回滚**并如实回报。**三条实证发现（请人复核后并入设计正文）**：① **产品缺陷（非 M3 引入，人机 UI 同链路）** —— `link_text_search` 纯文本分支把 **body 绝对偏移**当**行内**偏移去查 `view_to_orig`，返回的 span 整体右移且 `matched_text` 不等于锚文本（最小复现：`前缀文字注意力机制后缀文字。` ⇒ `col=9, '后缀文字。'`，应为 `col=4, '注意力机制'`）⇒ `apply_link_instances()` 会把正文改坏（实测曾产出 `注意力机制是核心[[。注意力机]]制也出现在别处。`）。**已修**（等量替换、行号零漂移）：`row_pos = pos - (body.rfind("\n", 0, pos) + 1)` 后再查映射；新增 `tests/test_link_text_search.py`（13 例：三例最小复现 + 通用不变量 `row[replace_start:replace_end] == matched_text`）。② **§2.3.3 缺一条前置**：同一 plan 内「先建点、后连边」要求**前序 op 的结果对后序 op 的 `attach_links` 目标解析可见**（信封注释已写"前 op 的结果对后 op 可见"，但校验列未落实）—— 否则最常见的 plan 恒被 `target_not_found` 拒；已在 `validate_plan` 里补 `pending_ids` 集合 + 回归用例。③ **`attach_links` 在 M3a 内只能到行粒度**：`apply_link_instances()` 只收 `selected_lines`（**没有列**），同一行多处出现时只能包裹其中一处（实测包最后一处）⇒ 设计稿 op 字段 `occurrences[].matched_text` **落不到列级**（要列级得改原语签名，属后续批次）。**测试自己抓到的**：`upsert_kp`+`attach_links` 同 plan 的 5 个用例先失败（即发现 ②）；`instances` 按出现处记（同行两处 ⇒ 两条 `{line:3}`）。**验收**：`pytest -q` **393 passed**（原 375；无 xfail 残留）。**未做**：③ 审批 + 审计（`capability/apply`/`capability/backup`/`capability/undo`）、④ RPC 与前端确认卡；撤销的网关侧一致性恢复（清 `_cache` + `validate_kb`）。**另记一条工具链教训**：测试若构造 `DocumentService` 而不隔离 `MEMORIA_CONFIG_DIR`，会经「记录最近打开」写**真实** `config/ui-settings.json`（本轮实测把 8 条临时库写进 `recent_kbs`，已清理并给两个 fixture 补隔离）—— 建议加 `tests/conftest.py` autouse 隔离，待人拍板。登记 `conventions/docs-management.md §4.2`；`docs/todo.md` 未编辑 |
| 2026-09-20 | **更正上一条的「行粒度」结论 + 给原语补列级 span（人已拍板）**：用户追问「原本 memoria 就是可以选中一行内任意文字建跳转，怎么现在颗粒度就变成行？」—— **追问成立，我上一条的说法不准确**。**① 查清人机 UI 真实路径**（读码）：选中文字 ⇒ `wrap_text_as_link()`（`document.py:2821`，**只建 sidecar 路由、不碰正文**，`update_markdown=False`；锚文本 = 选中的那段文字）⇒ 随后**匹配面板**确认包裹位置 ⇒ `apply_link_instances(…, [...m.selected], …)`（`app.js:6025`，`m.selected` 是**行号集合**，`app.js:5963`）。⇒ 所以"字符级"的真正来源是**锚文本本身**（选中哪段文字，锚就是哪段）；只有"**同一行里该文字重复出现**"时，锚文本与行号两条信息都相同、才是定位极限 —— 而**人机 UI 在那种情形下同样只包一处**（同函数同参数）。**② 拍板：补列级参数**。`DocumentService.apply_link_instances()` 新增关键字参数 `selected_spans: dict | None = None`（**默认 None ⇒ 旧行为逐字不变**，人机 UI 与既有调用者零影响）；给了 span 就**必须先与锚文本逐字相符**，不符即 `{status:"error"}`（`document.py:2611-2626`）—— 与 `plan.py` 校验形成**双保险**。RPC `apply_link_instances`（`ui.py:564`）追加同名可选参数并透传。**③ plan 侧扩字段**：`occurrences[].col`（**1 起列号**，与 `#L3C2` 同口径）⇒ 校验核对该列起确为锚文本（新错误码 `col_mismatch`），并产出 `pinned_spans: {line: (start0, end0)}`；编译期把它作为 `selected_spans` 传给原语；`preview_plan()` 用**同一份 pinned span** 试算 ⇒ 预览与落地不可能漂移。同行多处**且没给 col** ⇒ 新警告 `ambiguous_occurrence`（不拒，如实说明"哪一处由后端按行取值决定"）。**④ 设计稿 §2.3.3「需新增的最小能力」第 2 条**（`occurrences[].matched_text` 前置核对）**据此升级为"行 + 列"双核对**，请人复核后并入该节正文。**⑤ 顺带（未做，可选后续）**：人机 UI 的匹配面板其实已列出**每一处**，只是确认时把列丢了 —— 前端接上 `selected_spans` 后即可区分同行两处；本轮**未改前端**。**⑥ 验收**：`pytest -q` **397 passed**（原 393；+4 例：C1/C10 两个方向各包对一处、列号不符即拒、不给 col 的旧口径回归、`ambiguous_occurrence` 警告）；三个原语锚点行号未动（`confirm_kp_range` 1360 / `detach_link_instance` 2428 / `apply_link_instances` 2493）。登记 `conventions/docs-management.md §4.2` |
| 2026-09-20 | **新增 §9「写冲突优先级与并发保护」（人已拍板）+ 落后端一半实现**：用户问「用户修改和 agent 修改哪个定位更高优先？」⇒ 结论**不是"某一方优先"**，而是三条规则：① **盘上版本 = 唯一权威**（任何写者写前必须确认"我读到的版本 == 盘上版本"，不一致即拒写并回报 `stale_write`）② **人的当下操作最高**（agent 不得趁人正在编辑同一文件时抢写）③ **冲突由人明示决定**（前端弹「重载 / 以我为准 / 看差异」，**agent 不自动合并、不静默赢，人的过期 buffer 也不自动赢**）。**明确否掉**多线程（写路径本是无锁同步短事务，开线程只会引入进程内竞态）与增量修改（对 lost update 不免疫，属优化后置）。**实现（本轮只做后端一半）**：新模块 `storage/file_version.py`（`file_version`=内容 sha256 / `rel_version` / `with_version` / `guard_save`）；`ui.py` 的 `load_document` **追加** `version`（只增不改）、`save_document` 追加可选 `base_version`（**空串 = 不校验 ⇒ 旧行为逐字不变**）—— 两处都是**等量替换**委托进新模块，`services/document.py` **一行未动**（零行漂移）；`preview_plan()` 返回 `base_versions`（= 用户看过的那一版），`apply_plan()` **先比版本再谈 plan**（文件变了还报"plan 非法"是误导），不一致 ⇒ `stale_write` 且**尚未建备份**。**验收**：新增 `tests/test_write_conflicts.py`（8 例：版本=字节 sha256、`load_document` 带版本、版本匹配才写且回写新版本、**过期保存被拒且不覆盖**、不传版本=旧行为、`preview_plan` 交基准、**预览后被改 ⇒ 整批拒且不建备份不写盘**、版本一致正常落地）；`pytest -q` **405 passed**（原 397）。**未做（下一步）**：前端保存带 `version` + `stale_write` 三选一弹窗（含 i18n 中英）、apply 期间前端忙位与"当前文件正被编辑 ⇒ 拒 apply"。**另记**：`_write_body` 的 `os.replace` 偶发 `WinError 5`（外部瞬时持锁，非句柄泄漏）—— 是否加短退避重试仍待人拍板。登记 `conventions/docs-management.md §4.2` |
| 2026-09-20 | **写冲突保护：前端一半落地（版本令牌"通电"）+「以我为准」先备份再覆盖**：`app.js` **IIFE 内仅四处同行内替换**（守卫行 `deferIfBusy(markDirty)` / 保存调用带 `state.doc?.version` / **失败行**改走 `onSaveFailed`（返回 true 即不再 `console.warn`）/ 成功后滚回新版本；`git diff` 只有 `@@ -124 / -133 / -135 / -137 @@` 四个单行 hunk）⇒ **零行漂移**；文件末尾追加 `memoriaWriteGuard` 块（80 行）（`setBusy` / `deferIfBusy` / `onSaveFailed` + **三选一弹窗**「重载 / 以我为准 / 稍后」，复用既有 `.-modal` 样式与 `confirmTreeAction` 同构；跨闭包只经 `window.MemoriaApp` 门面，`state` 是同一对象引用 ⇒ 版本可直接读写）。**「以我为准」= `force=True`**：后端 `guard_save` 先走 `services/agent/backup` 落 `manual-force/<txid>` 批次（含 `post.json`）**再覆盖**，备份失败即拒（不降级为无备份覆盖）⇒ 被覆盖掉的那一版**可直接 `restore_batch` 撤销**（测试已跑通往返）。i18n 以**文件末尾 `Object.assign`** 追加 `writeConflict.*`（中英各 8 键，`i18n_selftest.js` 全 PASS）。**验收**：`pytest -q` **409 passed**（原 405；`test_write_conflicts.py` 12 例，含两个前端接线不变量——保存带版本/成功后滚基线/`stale_write` 只走弹窗/忙位让路/三选一按钮与 force 调用，以及中英键成对）；`node --check` 3/3。**仍未做**：apply 期间的前端忙位与 agent 写入口接线（等 ④ 一起：`setBusy` 包住 apply + apply 前查"当前文件脏 ⇒ 拒"，即规则 ② 的另一半）。登记 `conventions/docs-management.md §4.2` |
| 2026-09-20 | **第二片 ③「审计事件 + 撤销后一致性恢复 + `detach_links` 预览 diff」落地（log-only，不动请求体）**：① **新模块** `src/memoria/services/agent/audit.py`：`append(kb_path, session_id, type, payload)` —— 把写动作**追加进既有会话 `session/*.jsonl`**（`SessionStore.append` + `flush`），`capability/apply` / `capability/undo` / `capability/force_save` 三种事件；**fail-open 但如实**：返回 `{status:"ok"\|"skipped"\|"error"}`，**不抛不回滚**（写已完成，审计失败只是没留痕，绝不因此撤销用户的写入）。之所以选会话流而不是新事实源：回放对未知 `type` 直接跳过、`compaction.event_chars()` 计 0 ⇒ **不改请求体、不动 KV 前缀、不影响回放**（与既有 `session/title` 同构），避免新增并行事实源（AGENTS.md §1）。② **接入三条写路径**：`apply.py` **四处返回**（`stale_write` / 备份失败 / 原语失败 / 成功）都带 `audit` 字段；`backup.restore_batch()` 新增 `audit: bool = True` 形参并在成功后记 `capability/undo`；apply 的**事务内回滚显式传 `audit=False`**（它不是"用户撤销"，apply 失败事件已记全貌，不冒充）；`file_version.py` 的「以我为准」强制覆盖记 `capability/force_save`。③ **撤销后一致性恢复**（补上第二片 ① 留的尾巴）：新增 `apply.recover_after_write(kb_path, rel_paths, service=None)` —— 清 `DocumentService._cache` 中受影响条目 + 跑 `validate_kb()` 并回报 `{cache_cleared, errors, warnings}`。**为什么必须显式清**：`backup.restore_batch()` 是**直接写盘**、不走 `save_document()`，应用侧那份进程内解析缓存会残留撤销前的正文。④ **`detach_links` 预览不再是空 diff**：`plan.py` 的 `preview_plan()` 原先如实标 `diff_available: false`，现改用 `detach_link_instance()` 内部**同一个原子函数** `unwrap_lines()` 给出逐行 before/after ⇒ **预览与落地不可能漂移**（docstring 同步更正）。⑤ **验收**：新增 `tests/test_agent_audit.py`（**7 例**：成功/被拒都留痕、撤销留痕、**内部回滚不冒充 undo**、force_save 留痕、审计 fail-open 且如实、`recover_after_write` 清缓存并校验、detach 预览出行级 diff）；`pytest -q` **427 passed + 3 flaky**（见下）；`py_compile` 7 文件全过。⑥ **如实交代两件未决**：㈠ `test_agent_apply.py` 的 **`WinError 5` 非确定性 flake**（`os.replace` 被瞬时持锁；本次全量跑 3 挂，单跑必过）—— 是否加**有界退避重试**（仅 `WinError 5/32`）**仍待人拍板**；㈡ `recover_after_write` 触碰 `_cache` 私有属性，更干净的做法是给 `DocumentService` 加**公开失效 API**（已登记，未做）。⑦ **仍未做**：审批应答者与确认 UI、RPC 暴露 + 前端确认卡 + apply 忙位接线（M3a 剩余 ③④）。登记 `conventions/docs-management.md §4.2`；`docs/todo.md` 未编辑（另一写者并发重写中） |
| 2026-09-20 | **写路径 `os.replace` 加有界退避重试（人已拍板）**：`test_agent_apply.py` 的非确定性 `PermissionError: WinError 5`（连续写同一 md 时偶发，重跑从不复现、单跑必过；句柄泄漏已排除）判定为**外部瞬时持锁**（AV / 索引器 / 后台词法索引线程）。**① 新模块** `src/memoria/storage/atomic_write.py`：`replace_with_retry(src, dst)` —— **只**对 `WinError 5`（拒绝访问）/ `WinError 32`（共享冲突）重试，`5 × 50 ms`（上限 250 ms），每次重试 `logger.warning`（带 winerror / 第几次 / 源→目标，**可见**），**耗尽仍抛**（绝不把真权限错误吞成静默成功）；非 Windows 上 `OSError` 无 `winerror` ⇒ 等价于裸 `os.replace`。**② 两处写点等量换用**（`document.py` **零行漂移**，import 追加在文件末尾）：`save_document` 的 `os.replace(tmp_full, full)`（`:347`）与 `_write_body` 的 `os.replace(tmp, full)`（`:2074`）—— 即"人机保存"与"agent 写"两条正文写路径。**③ 验收**：`tests/test_write_conflicts.py` 追加 3 例（瞬时锁救回且睡满次数 / 非瞬时**立刻抛不重试** / 有界耗尽仍抛）⇒ 15 passed；`test_agent_apply.py` 连跑 **9 次全绿**。**④ 如实交代**：这 9 次**没有一次真触发到那个瞬时锁**（无重试日志）⇒ "重试把人救回来"目前**只由单测覆盖**，尚未在线复现（能证明的只是没引入回归）。**⑤ 有意不扩面**：sidecar / manifest / `kp_rename` / `backup.restore_batch` 等其余 `os.replace` 点**保持裸 replace**（本轮只治"用户与 agent 的正文写点"）。`docs/todo.md` 未编辑 |
| 2026-09-20 | **M3a ④ 落地：计划 API 的 RPC 暴露 + 前端确认卡 + apply 忙位（第二片收尾）**。**① RPC 面（`ui.py`，追加在类末尾 ⇒ 既有 `ui.py:<行>` 锚点零漂移）**：四个只读面 `agent_plan_validate` / `agent_plan_preview` / `agent_plan_resolve` / `agent_plan_audit` + `agent_plan_apply(plan, kb_path, session_id, base_versions)` + `agent_plan_undo(kb_path, session_id, txid)`；只读面**零落盘**且一律复用 `plan.py` 的同一套校验器（不另写宽松判断）；当前库复用应用侧 `DocumentService`（同一份缓存与 KP 唯一性判定），**别的库传 `None`** 由 plan 层自建（`agent_plan_audit` 只支持当前库，否则 `kb_mismatch`）；未开库一律结构化 `no_kb`。`agent_plan_apply` 省略 `session_id` ⇒ 归入 `ui-plan` 伪会话（**返回值带回** `session_id`/`txid`，供撤销原样传回）；成功后跑 `recover_after_write()`（清解析缓存 + `validate_kb()`）。`agent_plan_undo` 走 `restore_batch()` + 同一套恢复，**外部改动保护 fail-closed**（apply 之后被改过 ⇒ `external_change` 整批拒）。**② 两条口径本轮钉死**（此前含糊）：㈠ **校验期拒绝 = 零字节变化**（连审计都不写，对齐 §2.6 安全门第 1 条"无 silent 写"）；**只有过了校验的落地尝试**（stale / 备份失败 / 原语失败 / 成功）才一律留痕 `capability/apply`。㈡ **勾选 = 编译前的选择**：未勾的 op 由**前端**从 `plan.ops` 去掉再提交，后端**不引入**任何"部分执行"（仍 all-or-nothing）。**③ 前端（不改 `app.js`，零行漂移）**：新模块 `js/plan-confirm.js`（`window.MemoriaPlan = {open, openFromText, close, undo}`）—— dry-run 预览 → 卡片摊开"哪个文件、哪一行、before → after" + 逐条勾选（默认全勾，按钮联动计数）→ apply；§9 规则 ① 靠 `preview.base_versions` **原样回传**；§9 规则 ② 的另一半 = `MemoriaWriteGuard.setBusy(true)` 包住 apply（人机保存经 `deferIfBusy` 重新入队）+ 当前编辑未落盘时**先有界等待（≤3 s）仍脏即拒**；成功后给 txid + 「撤销这一批」，并 `openFile(cur, {skipNav:true})` 重开当前文件；失败（含 `stale_write`）给「重新预览」。`index.html` 末尾挂载该文件、`app.css` 末尾追加计划卡样式块、i18n **中英各 23 键**（`plan.*`，末尾 `Object.assign`）。**④ 验收**：新增 `tests/test_agent_plan_rpc.py`（**14 例**：四个只读面逐文件 sha256 不变、未开库一律 `no_kb`、preview→apply→undo **逐字节还原**（正文+sidecar+manifest+pending）、看完预览后被改 ⇒ `stale_write` 且**未建备份**、非法 plan ⇒ `invalid_plan` 且**含审计在内零字节变化**、撤销缺 `session_id` 明确报错、RPC 路径的 `capability/apply` 落会话文件、确认卡接线不变量（勾选在编译前 / 忙位包住 apply / 脏编辑拒写 / 写完重开当前文件 / 中英键成对））⇒ `pytest -q` **447 passed**；`node --check` 3/3；`scripts/i18n_selftest.js` 全 PASS。**⑤ L4 交互实证**（静态服务器 + 浏览器实渲染 + 截图）：契约齐全的 preview 下卡片渲染为标题（含 intent）/摘要（共 3 项、2 文件）/3 个默认全勾的勾选项/两个文件分组/行级 `- before` `+ after`/取消+应用按钮，盒子 760×333 **无重叠、无裁切、无溢出**，`plan-confirm.js` **零报错**；缺 `status` 的非法 preview 按设计落入"预览异常"分支（证明 fail-safe 分支可用）。**⑥ 未做（如实）**：**工具面未接** ⇒ 模型还不能自己产出 plan，故卡片当前入口是 JS API（`MemoriaPlan.open(plan)` / `openFromText(json)`，控制台可测），聊天里出现 plan 即自动给确认按钮属下一步；`approval` 的**应答者**（`ApprovalRequest` / `AskPolicy` / `agent_ask_start`+`agent_ask_poll` 这条现成通道）仍未挂；`recover_after_write` 仍触碰 `_cache` 私有字段（待加公开失效 API）。登记 `conventions/docs-management.md §4.2`；`docs/todo.md` 未编辑（另一写者并发重写中） |

---

## 6. 迁移清单（自 [agent-capabilities.md](./agent-capabilities.md) 迁入本文）

> **兜底规则（迁移完成前一律适用）**：凡两份文档**冲突**处，**以本文为准**；本节标 `未迁` 的内容**仍以 `agent-capabilities.md` 原文为工作依据**（本文只登记"要迁什么"，不复制正文 —— 禁并行事实源）。
> **本轮（2026-09-20）不搬任何正文**：先讨论 §7 的写场景；迁移动作由人逐步发起，每迁一节把该行改为 `已迁` 并在本节末尾登记日期。
> **编号纪律**：本文 §1–§5 **不复用、不重排**；迁入内容一律**追加**为 §9 起的**新节**（或并入现有新节），**不插进 §1–§5**。若某节迁入时确需重排 `agent-capabilities.md` 的编号，**旧 → 新编号映射必须写在本节该行里**。

| # | 来源（`agent-capabilities.md`） | 要迁入的内容（一句话） | 状态 |
|---|---|---|---|
| 1 | §2.1.1 | 三层术语（**原语 / 领域动词 tool / 技能 skill**）与"领域动词只产出 plan、不落盘"铁律 | 未迁 |
| 2 | §2.2 | **注册与装载**：两个位置（内置声明 `resources/agent-capabilities/<id>.json` / 库级 `<kb>/.memoria/agent/capabilities.json`）、发现顺序、冲突与重名、**不变量「新增插件不改核心」**、UIAPI 只加一个通用网关 | 未迁 |
| 3 | §2.3 | **写管线**六步（propose → dry-run diff → 逐条确认 → apply → 审计 → 撤销）+ 四条不变口径 | 未迁 |
| 4 | §2.3.1 | **唯一写者**：四原语（`save_document` / `save_sidecar_for_md` / `touch_manifest_entry` / `sync_pending_for_file`）+ realpath 前缀校验 | 未迁 |
| 5 | §2.3.2 | **备份与撤销**：pre-image 时机与粒度、`<txid>` 目录与格式、保留口径（5 批 / 10 会话 / 64 MiB）、撤销与外部改动保护 | 未迁 |
| 6 | §2.3.3 | **计划 API**：`{v,txid,intent,ops[]}` 信封、op 表与校验规则、**拒整批**失败语义、需新增的最小能力清单 | 未迁 |
| 7 | §2.3.4 | **编译器与校验器**：`validate_plan` / `preview_plan` / `resolve` / `audit_kb` 四个只读面 + "同一套校验器、两个消费者"硬不变量 | 未迁 |
| 8 | §2.4 | **权限与越界**：权限矩阵（含 `backups/**`、`images/**` 行）、违约硬拒 + 审计 + 零部分写、路径逃逸判定 | 未迁 |
| 9 | §2.5 | **W/N/S/H 四线如何落成插件族**（族 ≠ 枚举值；"能插的是声明与权限，不能插的是执行体"） | 未迁 |
| 10 | §2.6 | **M3 分期与验收门**：M3a/M3b 切片表 + **四条安全门** + 首批写原语目录 + "明确不做"清单 | 未迁 |
| 11 | §2.7 | **与上游 dsh 的关系**：借什么 / 本地发明什么（含"沙箱升级不吃、用声明式 `permissions` + realpath 替代"） | 未迁 |
| 12 | §8 阶段建议 | 与写模块相关的两行：**W1 = M3a**（计划 API 最小闭环）、**W2 = M3b**（其余 op + 撤销 + 权限档） | 未迁 |
| 13 | §9 风险 | 与写模块相关的四条：**R1**（写能力毁用户库）、**R2**（正文内相对链接未随文件移动改写 ⇒ 影响 §7 的 2.6 / 4.5）、**R4**（skill/插件变成任意代码执行面）、**R8**（装载器成为新的越权写入面） | 未迁 |
| 14 | §10 待拍板 | 与写模块相关的项：**P1**（确认交互）、**P2**（批量提议）、**P7**（注册表承载位置）、**P8**（首批 op 个数，本文 §4 Q3 已引）、**P9**（`approval` 可否覆写，本文 §4 Q4 已引）、**P10**（撤销口径，本文 §4 Q5 已引）、**P11**（权限档是否随 M3b）、**P12**（plan 版本，本文 §4 Q6 已引）；**P3–P6 属 N/S/H 与基准线，不迁** | 未迁 |
| 15 | §0 / §1 中与写模块相关行 | §0 红线的"写前必留 pre-image、备份失败即不写"与"插件边界物理可证"两处；§1 现状盘点的"能力面极窄"结论（作为 §7 现状表的背景） | 未迁 |

---

## 7. 写场景清单（讨论中，2026-09-20）

> **这一节是本轮的主交付：只做讨论材料，不预设结论。**每行的「审批档」一律是**建议**且**待定**；「归属」是**建议切片**，不是承诺。
> **取证口径**：现状列全部**读码得到**（`file:line` 以仓库根为基准；`ui.py` = `src/memoria/presentation/api/ui.py`；前端 = `src/memoria/ui/static/app/**`）。渲染/书写格式的**语法权威**是 [preview-formats.md](../reference/preview-formats.md)，人 UI 的写入路径取证见 [agent-guide](../reference/agent-guide/README.md)。
> **两个反复出现的"底座"（本节多处引用）**：
> - **通用行级原语**（暂定 `kb.file.edit`）：按行区间替换/插入/删除正文行 —— 今天只存在**整篇**入口 `DocumentService.save_document`（`document.py:317`；RPC `ui.py:200`），**没有**行级/区间级入口。
> - **整块原语**（暂定 `kb.block.upsert`）：按块类型（code / table / math / mermaid）重建某个块 —— 今天**没有后端入口**，块编辑面板在前端用 `blockEl.textContent` + 下拉选择重建源码行（`edit-handler.js:1710-1744`）。

| # | 场景（用户 / AI 想做什么） | 今天 Memoria 的支持现状（`file:line` 或"无"） | 落到哪个 op / 需要哪个原语 | 是否需要**新原语**（暂定名） | 审批档（建议，**待定**） | 归属（建议） |
|---|---|---|---|---|---|---|
| 1.1 | 连边：把正文某处 `[[…]]` 挂到某个 KP | ✅ 有：`apply_link_instances`（`document.py:2493`，RPC `ui.py:564`）；目标不可解析即拒（`document.py:2536` 扫描 + 逐目标校验）；单点解挂 `detach_link_instance`（`document.py:2428`，RPC `ui.py:537`） | `attach_links` / `detach_links` → 薄包装原语 `kb.link.attach` / `kb.link.detach` | 否（原著 M3a 已定为新增薄包装） | `confirm` | **M3a** |
| 1.2 | 连边：建 KP↔KP 的**纯边**（不写正文） | ✅ 有：`create_edge`（`document.py:2885`，RPC `ui.py:780`），只写 sidecar `edges[]`；`reference` / `extend` 两型（`contain` 只由范围嵌套推导，`edge_types.py:61-66`） | `upsert_edge` → 原语 `kb.link.create` / `kb.link.set_type` | 否（原著 §2.6 附表已列，M3b 启用） | `confirm` | M3b |
| 1.3 | 创建知识点（建 KP + 锚定 range） | ✅ 有：`confirm_kp_range`（`document.py:1360`，RPC `ui.py:220`）；起止行**非空**硬校验（`:1386-1399`）、跨库 id 唯一复核（`:1414-1419`）、终校 `validate_sidecar`（`sidecar_validate.py:133`） | `upsert_kp` → 原语 `kb.kp.create` | 否 | `confirm` | **M3a** |
| 1.4 | 改知识点：名称 / 区间 / 描述 | ✅ 有：`update_kp`（`document.py:1722`，RPC `ui.py:296`）改 name/description；`confirm_kp_range` 改区间；`set_kp_range` 属 M3b | `upsert_kp` / `set_kp_range` → 原语 `kb.kp.update` | 否 | `confirm` | M3a（名称）· M3b（单独调区间） |
| 1.5 | 完善 tag（选 tag / 加候选 / 调别名） | ✅ 有：`update_kp`（`document.py:1722`）整体覆写 `tags` / `tag_candidates` / `aliases` / `alias_candidates` / `description_candidates`（`:1769-1820`）；建议侧 `suggest_tags_api`（`document.py:1515`）、`suggest_description_api`（`:1544`）**只给建议** | `upsert_kp`（`tags`/`aliases` 字段） | ⚠️ **建议新增** `kb.kp.tag.set`（**增删单个 tag** vs 整体覆写，待定） | `confirm` | M3a（整体覆写）· M3b（增量） |
| 1.6 | 合并近重复 KP | ⚠️ **只有建议、无动作**：`suggest_kp_merge`（`document.py:1497` → `search_kernel.py:136`）；人 UI 也只展示建议（[05 §5 第 3 条](../reference/agent-guide/05-knowledge-points.md)） | `merge_kp`（第二批） | ✅ **需要**：`kb.kp.merge`（新 id + 重指 `links`/`edges` + 删源 KP） | `confirm` | M3b |
| 1.7 | 删除知识点（只删配置、不改正文） | ✅ 有：`delete_kp`（`document.py:1875`，RPC `ui.py:336`）；同时解除 `links[].source_id` 引用（`:1892-1896`） | `delete_kp` | ✅ **需要**：`kb.kp.delete` | `confirm`（删除类建议不设 `auto`） | M3b |
| 1.8 | 改知识点名称 / id（**全库级联**） | ✅ 有：`rename_kp_id`（`document.py:1937` → `services/kp_rename.py`；RPC `ui.py:342`），影响面全库 | `rename_kp` | ✅ **需要**：`kb.kp.rename`（预览须给受影响文件清单，`services/kp_index.py:37` 的 `build_kp_index`） | `confirm` | M3b |
| 1.9 | 处理待确认提议（确认 / 忽略 / 刷新） | ✅ 有：`sync_pending_for_file`（`storage/pending.py:273`）、`sync_kb_pending`（`:172`）、`dismiss_pending_item`（`:317`）；确认仍走 `confirm_kp_range` | `confirm_pending` / `dismiss_pending` | ⚠️ **建议新增**：`kb.pending.confirm` / `kb.pending.dismiss`（或复用 `upsert_kp` + 一个 dismiss 原语） | `confirm`（dismiss 建议 `confirm`） | M3b |
| 2.1 | 改正文段落（替换若干行） | ✅ 有**整篇**入口 `save_document`（`document.py:317`；RPC `ui.py:200`；tmp + `os.replace` `:341-347`，保留 frontmatter `:337`）；**无行级入口** | `replace_lines` → **通用行级原语** `kb.file.edit` | ✅ **需要** | `confirm` | M3b |
| 2.2 | 插入新段落（不覆盖他人内容） | ⚠️ 只能整篇重写（`save_document` `document.py:317`）；无插入原语 | `insert_block` / `insert_lines` → 复用 `kb.file.edit` | ✅ **需要**（若 `kb.file.edit` 已按行区间设计则可复用） | `confirm` | M3b |
| 2.3 | 删除段落 | ⚠️ 同 2.2：只能整篇重写 | `delete_lines` → 复用 `kb.file.edit` | ✅ **需要**（同上） | `confirm` | M3b |
| 2.4 | 新建 `.md` 文件 | ✅ 有：`create_file`（`document.py:794`；RPC `file_create` `ui.py:149`；父目录自动创建、自动补 `.md`、`touch_manifest_entry`） | `create_file` → 原语 `kb.file.create` | 否（原著附表已列，M3a 不进工具集） | `confirm` | M3b |
| 2.5 | 删除整文件（`.md` + sidecar） | ✅ 有：`delete_file`（`document.py:782`；RPC `file_delete` `ui.py:143`） | `delete_file` → 原语 `kb.file.delete` | 否（原著附表已列，**默认关**，开关属 `config` 暂缓字段） | `confirm`（**建议不设 `auto`**） | M3b |
| 2.6 | 重命名 / 移动文件 | ✅ 有：`rename_file`（`document.py:583`；RPC `file_rename` `ui.py:137`）——**含全库 `[[stem]]` 改写级联**（`:629-648`）与 sidecar/manifest/pending 迁移；目录重命名 `rename_dir`（`:697`，RPC `ui.py:161`） | `rename_file` → 原语 `kb.file.rename` | 否（原著附表已列）；`kb.file.move` 仍**不做**（见 §6 第 13 行 R2） | `confirm` | M3b |
| 2.7 | 改 frontmatter | ❌ **无**：`save_document` 只**原样保留** frontmatter（`document.py:337` `strip_frontmatter` → `compose_markdown`），没有写 frontmatter 的入口；且 KP 元数据权威是 sidecar、frontmatter **不参与解析**（[05 §5 第 10 条](../reference/agent-guide/05-knowledge-points.md)） | `set_frontmatter` → 原语 `kb.file.frontmatter.set` | ✅ **需要**（且需先定"frontmatter 与 sidecar 谁是权威"，[05 篇] 已判 sidecar） | 建议 `confirm`（**待定**） | 后线 |
| 2.8 | 新建 / 重命名目录 | ✅ 有：`create_dir`（`document.py:812`；RPC `dir_create` `ui.py:155`）、`rename_dir`（`document.py:697`；RPC `dir_rename` `ui.py:161`） | `create_dir` / `rename_dir` | ✅ **需要**：`kb.dir.create` / `kb.dir.rename` | `confirm` | M3b |
| 3.1 | 字体样式：粗体 / 斜体（md 原生） | ✅ 有：`format_text`（`document.py:2078`，RPC `ui.py:548`）支持 `bold`（`**…**` `:2098`）与 `italic`（`*…*` `:2100`）；**无**删除线、**无**行内代码 | `apply_style` → 原语 `kb.style.apply` | ✅ **需要**（今天只有人 UI 单行/单列区间调用，无 agent 面） | `confirm` | M3b |
| 3.2 | 字体样式：高亮 / 字色（**本地扩展语法**） | ✅ **是本地扩展、且可渲染**：`[[\h\|…]]` / `[[\h:bg\|…]]` / `[[\h:bg:fg\|…]]` / `[[\c:color\|…]]`（[preview-formats.md §4.2](../reference/preview-formats.md)）；写入侧 `format_text` 覆盖 `highlight`（`:2102-2107`）与 `fontcolor`（`:2108-2110`） | `apply_style` → `kb.style.apply` | ✅ **需要**（同上；注意 `[[\…]]` **不嵌套**，`]]` 按行内第一个收尾） | `confirm` | M3b |
| 3.3 | 字体样式：字号 / 下划线 / 上标 / 下标 | ⚠️ **能渲染、不能写**：`[[\s:size\|…]]` / `[[\u\|…]]` / `[[\sup\|…]]` / `[[\sub\|…]]` 只存在于**渲染侧**（`renderer.js:352-384`；语法见 [preview-formats.md §4.2](../reference/preview-formats.md)）；**`format_text` 的 `format_type` 枚举里没有它们**（`document.py:2098-2112`）⇒ 今天连人 UI 也无法应用这几种 | `apply_style` → `kb.style.apply`（扩枚举） | ✅ **需要**（且**先要补** `format_text` 的 `format_type`，否则连人 UI 也不支持） | `confirm` | 后线（先补人 UI） |
| 3.4 | 字体样式：**sidecar 记录样式**（带名高亮等） | ❌ **无**：全库 `src/**` 无 `highlights` 写入/校验路径（`sidecar_validate.py` 只校验 `knowledge_points` / `edges` / `links`，`sidecar_validate.py:180/283/327`）；`markdown-form-std.md:78` 与 `preview-formats.md §4.2` 提到的 sidecar `highlights[]` 在当前代码中**没有实现**（⚠️ 既有文档与代码的又一处不一致，如实记录） | 无 op（先定契约） | ✅ **需要**：**新存储**（sidecar `styles[]` / `highlights[]` 的字段契约）；按 [AGENTS.md §1](../../AGENTS.md) 若成为事实源须**先由人登记** | 建议 `confirm`（**待定**） | 后线 |
| 3.5 | 字体样式：整文级字号 / 字色 | ❌ **不是内容**：字号是**视图偏好** `--preview-font-size`，由「设置 → 显示 → 文字」滑块写 `ui-settings.json`（[preview-formats.md §5](../reference/preview-formats.md)；`display-settings.js:79-85`） | —（无 op） | ❌ 不建议 | — | **不建议给 agent 做** |
| 4.1 | 插入图片引用（正文新增 `![](…)` 行） | ⚠️ **仅前端**：`image-tools.js:108-161` 按锚点插入源码行（`![alt](<relPath>)`，尖括号包裹 `:83-90`）；**无后端入口** | `insert_image_ref` → 复用**通用行级原语** `kb.file.edit` | ✅ **需要**（行级原语）；另需 `kb.image.import` 入库 | `confirm` | M3b |
| 4.2 | 图片登记进 `.memoria/images/**`（与 manifest） | ⚠️ **部分**：`import_image`（`document.py:833`；RPC `ui.py:851`）做扩展名白名单 + **MD5 内容去重** + 重名编号，**只复制文件**；manifest **不索引图片**（`manifest.py:47 entry_for_md` 只对 `.md` 取值）；图片另有**独立注册表** `registry.json`，由 `rebuild_image_registry`（`document.py:1014`）重建、`_update_registry_for_doc`（`:1027`）增量维护 | `import_image` → 原语 `kb.image.import` | ✅ **需要**：`kb.image.attach`（入库 + 登记注册表）。⚠️ 澄清：**manifest 里没有图片条目**，别把"登记进 manifest"当成既有能力 | `confirm` | M3b |
| 4.3 | 改图片说明 / 替代文本（alt） | ⚠️ **仅前端**：`image-tools.js:515-519` 只改 `![…]` 内的 alt（保留 url 与 title），直接整行替换源码；**无后端入口** | `set_image_alt` → 复用 `kb.file.edit` 或 `kb.image.set_alt` | ✅ **需要**（可复用行级原语） | `confirm` | M3b |
| 4.4 | 改图片属性（`width` / `align` / `name-size` / `name`） | ⚠️ **仅前端**：`image-tools.js:486-512` 解析行尾 `"k=v,…"` 做**键级合并**（保序、保留未知键）后整行替换；语法权威见 [preview-formats.md §4.3](../reference/preview-formats.md) | `set_image_attrs` → 复用 `kb.file.edit` 或 `kb.image.set_attrs` | ✅ **需要**（可复用行级原语） | `confirm` | M3b |
| 4.5 | 移动 / 重命名图片资产（改路径） | ❌ **无**：图片侧只有 `import_image`（增）、`cleanup_unused_images`（`document.py:1104`，删）、`fix_unregistered_image_refs`（`:1236`，改引用格式）；**没有**改图片文件名的动作 | `move_image` → `kb.image.move` | ✅ **需要**（且需同步全部引用正文，属 [§6 第 13 行 R2] 未落地项） | `confirm`（**待定**） | 后线 |
| 4.6 | 删除图片引用（仅删引用行 / 删未引用文件） | ⚠️ **部分**：前端"删除引用"只删当前文档的引用行（`image-tools.js:410-436`，别处仍引用则**拒绝**）；真删磁盘文件走 `cleanup_unused_images`（`document.py:1104`，RPC `ui.py:872`）**不可恢复** | `detach_image_ref` / `delete_image` → `kb.image.detach` / `kb.image.delete` | ✅ **需要** | "仅删引用"建议 `confirm`；"真删文件"建议 `confirm` 且**默认关**（同 `kb.file.delete` 口径） | M3b |
| 4.7 | 修复"已引用但未注册"的图片引用（补尖括号） | ✅ 有：`diagnose_image_refs`（`document.py:1168`，RPC `ui.py:886`）+ `fix_unregistered_image_refs`（`document.py:1236`，RPC `ui.py:893`），把裸 URL 改写为 `<…>` 形式 | `fix_image_refs` | ⚠️ **建议新增**（可复用行级原语做等价改写） | 建议 `confirm`（**待定**，可用 dry-run diff 先行） | M3b |
| 4.8 | 清理未引用图片（真删文件） | ✅ 有：`unused_images`（`document.py:1082`）/ `cleanup_unused_images`（`:1104`）；另有**后台自动**路径 `image_registry_auto_check`（`:1047`，6 小时宽限 `:1071`） | — | ❌ 不建议 | — | **不建议给 agent 做**（见 §8 理由） |
| 5.1 | 插入 / 更新代码块（含语言标注） | ⚠️ **仅前端**：块编辑面板 `_BLOCK_TOOLS`（`edit-handler.js:1169` 起；语言下拉读取 `:1599-1604`）在退出块编辑时重建围栏行（`:1734-1740`）；**无后端入口**。渲染为 `<pre class="-code-block">` + `language-<lang>`，**无语法高亮**（[preview-formats.md §2](../reference/preview-formats.md)） | `upsert_block(kind=code, lang)` → **整块原语** `kb.block.upsert` | ✅ **需要** | `confirm` | M3b |
| 5.2 | 表格（新建 / 改单元格 / 加行列） | ❌ **人 UI 也不支持写**：块编辑的「+行 / +列」按钮（`edit-handler.js:1217-1218`）**无任何事件绑定**，退出块编辑时表格分支**显式不处理内容更新**（`edit-handler.js:1712-1714`）、且不标脏（`:1784`）；渲染侧支持 `<table>`（`renderer.js:207-235`） | `upsert_block(kind=table)` → `kb.block.upsert` | ✅ **需要**（且**先要补人 UI 的表格写回**） | `confirm`（**待定**） | 后线（先补人 UI） |
| 5.3 | 公式块 `$$…$$` | ⚠️ **能写但已知有缺陷**：块编辑退出时用 `blockEl.textContent` 取内容（`edit-handler.js:1710-1717`）重建 `$$…$$`（`:1741-1744`），而该 DOM 在 MathJax 排版后已被 `mjx-container` 替换 ⇒ 写回内容可能不是原始 TeX（[04 §10 第 1 条](../reference/agent-guide/04-preview-and-rendering.md)，**待运行时确认**） | `upsert_block(kind=math)` → `kb.block.upsert` | ✅ **需要**（且**先修人 UI 的写回缺陷**） | `confirm`（**待定**） | 后线（先修缺陷） |
| 5.4 | `<details>` 折叠块（及任意原始 HTML） | ❌ **不支持**：正文里的原始 HTML 标签**按字面文本显示、不生成 DOM**（[preview-formats.md §2](../reference/preview-formats.md)）；仅**渲染侧**对用户自己写的 `<details>/<summary>` 加了三角样式（`agent-panel.js` 末尾块，[04 §7](../reference/agent-guide/04-preview-and-rendering.md)） | — | ❌ 不建议（要先改渲染器放行 HTML） | — | **不建议给 agent 做** |
| 5.5 | Mermaid 图块 | ⚠️ **仅前端**：类型下拉（`edit-handler.js:1184` 起）；源码走 `code_block + lang=mermaid` 归一（`edit-handler.js:1332-1333`），重建与代码块同一分支（`:1734-1740`）；后端无入口。失败给红框（`preview.mermaidFail`） | `upsert_block(kind=mermaid)` → `kb.block.upsert` | ✅ **需要** | `confirm` | 后线 |
| 6.1 | KP 范围重锚（正文编辑后自动校正） | ✅ 有：`_resync_kp_ranges_after_edit`（`document.py:420`），在 `save_document` 内**自动**触发（`:376`）；编辑期另有 `resolve_kp_ranges` RPC（`ui.py:206`） | 派生动作 | ❌ 不新增（应**隐式发生**，不作为独立场景暴露） | — | 不作为独立场景 |
| 6.2 | pending 同步（KP 变更后刷新待确认） | ✅ 有：`sync_pending_for_file`（`storage/pending.py:273`），在 `confirm_kp_range` / `delete_kp` 内**自动**调用（`document.py:1440`、`:1913`）；全库 `sync_kb_pending`（`pending.py:172`） | 派生动作 | ❌ 不新增（同上，隐式发生） | — | 不作为独立场景 |
| 6.3 | 重建 / 同步 manifest（文件清单） | ✅ 有：`rebuild_manifest`（`manifest.py:183`）经 `sync_manifest`（`document.py:2120`，RPC `ui.py:414`）；⚠️ 被**路径移动**阻断（`document.py:2123-2131`，先要求"修复路径"）；读侧有 pending overlay（`manifest.py:86-99`） | `rebuild_manifest` | ✅ **需要**：`kb.manifest.rebuild` | 建议 `confirm`（且**先要求无 path_moves**） | M3b |
| 6.4 | 路径级联修复（批量改正文 + sidecar 路径） | ✅ 有：`repair_path_cascade`（`document.py:2054`，RPC `ui.py:426`），**默认 dry-run**（`apply=False`）；`reconcile_path_cascade` 实现 | `repair_paths` | ✅ **需要**：`kb.paths.repair` | `confirm`（**必须逐条预览**） | M3b |
| 6.5 | 批量重命名级联（改文件名 → 全库 `[[stem]]` 改写） | ✅ 有：见 2.6（`document.py:583`，含 `replace_link_id_in_markdown` 级联 `:637`） | 见 2.6 | ❌（复用 2.6） | `confirm` | M3b |
| 6.6 | KP id 全库级联改（正文 `[[id]]` + 各 sidecar 引用） | ✅ 有：见 1.8（`document.py:1937`） | 见 1.8 | ❌（复用 1.8） | `confirm` | M3b |
| 6.7 | 安装 / 刷新 KB Agent 文件（写 `<kb>/.memoria/agent/**`） | ⚠️ 有但**不同性质**：`install_kb_agent`（RPC `ui.py:1100`）向库内写提示词/规范文件，属**程序安装面**；且打开知识库时会**自动补写/刷新**，是**有意例外于"禁止 silent 写入"**（`docs-management.md §4.2` 2026-09-10 行） | — | ❌ 不建议 | — | **不建议给 agent 做** |
| 6.8 | 会话 / 偏好 / 模型配置类写入 | ⚠️ 存在但**不在内容面**：`agent_session_delete`（`ui.py:1329`，删会话 JSONL）、`save_ui_settings`（`ui.py:769`）、`agent_save_config`（`ui.py:1184`，写 `config/agent.json`）；会话目录与备份目录都**不在** §2.4 的插件 `permissions.write` 白名单内 | — | ❌ 不建议 | — | **不建议给 agent 做** |
| 6.9 | 备份与撤销（写前 pre-image / 撤销上一批） | ❌ **尚无**（M3a 待实现）：既有只有 `atomic_yaml.write_backup`（`storage/atomic_yaml.py:22`）留下的**单版本 `.bak`**，且 **fail-open**（`:41-43`），不按事务聚合；正文 `.md` 路径**完全没有**这层 | 由 apply 入口隐式做（§6 第 5 行） | ✅ **需要**（`snapshot_pre_images` + `agent_capability_call(action="undo")`） | 撤销本身仍 `confirm` | M3a |

---

## 8. 场景间的关系与排序建议（讨论用）

> 全部为**建议 / 待定**，**不替人定案**；本节只给讨论用的分组、依赖与候选顺序。

**A. 共用同一原语的场景（先定底座，多数场景不必各造原语）**

| 原语（暂定） | 被哪些场景共用 | 说明 |
|---|---|---|
| **通用行级原语** `kb.file.edit` | 2.1 / 2.2 / 2.3 / 3.1 / 3.2 / 3.3 / 4.1 / 4.3 / 4.4 / 4.7 | 这些场景在实现上**都只是"改写某几行"**（今天的写入口 `save_document` 是整篇，`document.py:317`）。若先有行级原语，字体样式与图片属性**无需各自的后端原语** |
| **整块原语** `kb.block.upsert` | 5.1 / 5.2 / 5.3 / 5.5 | 按块类型重建（code / table / math / mermaid）；5.2 / 5.3 先要修人 UI 的写回缺陷 |
| `kb.kp.*`（create/update/delete/rename/merge） | 1.3 / 1.4 / 1.5 / 1.7 / 1.8 / 1.6 | 1.5 建议先做"整体覆写"，"增删单个 tag"待定 |
| `kb.link.*`（attach/detach/create） | 1.1 / 1.2 | attach/detach 写正文，create 是纯边 |
| `kb.image.*` | 4.1 / 4.2 / 4.5 / 4.6 | 4.1–4.4 多数可落到行级原语 |

**B. 依赖关系（做后者之前前者必须成立）**

- **1.1 连边 → 依赖 1.3 / 1.4（KP 存在）**：`attach_links` 的每个 target 必须**可解析**（`document.py:2536`），否则整批拒。
- **2.6 / 6.5 文件改名 → 依赖正文改写能力**：`rename_file` 已含全库 `[[stem]]` 改写（`document.py:629-648`），但**正文内相对链接/图片路径**不在其中（§6 第 13 行 R2）⇒ `kb.file.move` 因此**不进工具集**。
- **4.x 全部 → 依赖 2.1–2.3 的行级原语**（插入/改写图片引用行）。
- **1.6 合并 KP → 依赖 1.8 改名 + 1.7 删除**（合并 = 新 id + 重指 `links`/`edges` + 删源 KP）。
- **3.4 sidecar 记录样式 → 依赖"新存储契约"**：且按 [AGENTS.md §1](../../AGENTS.md)，若成为**事实源**须**先由人登记**；否则不得落盘。
- **6.3 manifest 重建 → 依赖 6.4 路径修复**：有 `path_moves` 时 `sync_manifest` **拒绝执行**（`document.py:2123-2131`）。
- **6.9 备份/撤销 → 是所有写场景的前置**（§6 第 5 行；apply 入口第一步取 pre-image）。

**C. 候选第一批（待你拍板）**

1. **1.3 建点 + 1.4 改点 + 1.1 连边（含解挂）** —— 即原著已定的 M3a 三个 op（`upsert_kp` / `attach_links` / `detach_links`，§4 Q3）。理由：三条都**映射既有服务层入口**（`document.py:1360/1722/2493/2428`）、可**幂等**证伪、可写前备份，且已覆盖"KP + 链接两个动作类、两个方向"。
2. **（可加）1.5 完善 tag 的"整体覆写"分支** —— 复用 `update_kp`（`document.py:1722`），增量原语留后。
3. **建议在建第二批之前先拍板"通用行级原语"** —— 它是字体样式、图片属性、段落增删三类场景的**共同底座**，先定它可一次性解掉 §7 的十余行。

**D. 建议今天不该给 agent 做的场景（各一句理由）**

| 场景 | 理由 |
|---|---|
| **4.8 未引用图片清理** | 真删磁盘文件**不可恢复**，且已有"6 小时宽限 + 后台自动"的路径（`document.py:1047-1078`）；让模型参与只会放大 data-loss 面 |
| **5.4 `<details>` / 任意原始 HTML** | 渲染器**按字面文本显示原始 HTML**（[preview-formats.md §2](../reference/preview-formats.md:36)）⇒ 写了也不生效；属"要先改渲染器"的前置问题 |
| **6.7 安装 / 刷新 KB Agent 文件** | 属**程序安装面**（写 `.memoria/agent/**`），且现路径是**有意例外于"禁止 silent 写入"**的自动补写；交给 agent 会与"边界可证"的口径冲突 |
| **6.8 会话 / 偏好 / 配置写** | 这些文件**不在** §2.4 的 `permissions.write` 白名单内（会话、备份目录都被显式排除），且属库外/程序面 |
| **3.5 整文级字号 / 字色** | 它是**视图偏好**（`ui-settings.json` 的 `--preview-font-size`），不是知识库内容；agent 改它=改用户界面设置，不是"写知识" |
| **2.7 frontmatter（可暂缓）** | KP 元数据权威是 **sidecar**、frontmatter **不参与解析** ⇒ 写入价值低、且要先定"谁权威"；建议留到 §7 其他场景之后 |
| **6.1 / 6.2（派生动作）** | 范围重锚与 pending 同步应**隐式发生**在写入事务内，不该作为独立 agent 场景暴露（否则出现"绕开事务的第二个写者"） |
| **5.2 表格 / 5.3 公式块（暂缓）** | 人 UI 自身尚未写好（表格无事件绑定 `edit-handler.js:1451-1452`；公式块写回可能损坏 TeX）⇒ **先修人 UI**，再考虑 agent 面 |

---

## 9. 写冲突优先级与并发保护（口径，2026-09-20 人已拍板）

> **触发**：用户问「你把用户修改和 agent 修改哪个定位更高优先？」。本节是**结论口径**。
> **实现落点**：`memoria/storage/file_version.py`（版本令牌）+ `services/agent/apply.py`（整批拒）；
> 口径条目属**人已确认**，Agent 只追加、不改写。

**三条规则（不设"谁的内容优先"，只设"不许基于过期版本写"）**

1. **盘上版本 = 唯一权威**：任何写者（人机保存 / agent apply / 级联修复）写之前必须确认
   "我读到的版本 == 盘上版本"；不一致 ⇒ **拒写**并回报结构化 `stale_write`（带期望/当前版本）。
2. **人的当下操作最高**：agent 的整批写不得趁人正在编辑同一文件时抢写 —— 该文件有未落盘编辑时，
   apply 应**等或拒**（不抢、不覆盖）。
3. **冲突由人明示决定**：`stale_write` 交前端弹三选一 —— ① 重载（丢弃我的编辑，跟盘上走）
   ② 以我为准（**覆盖前先把盘上那一版存进备份目录**，保证仍可回滚）③ 看差异（可后置）。
   **agent 不自动合并、不静默赢；人的过期 buffer 也不自动赢**。

**为什么不是"某一方优先"**：优先的是**人**，不是**人的过期 buffer**。让人的过期保存自动赢 =
静默抹掉 agent 那个**已审计、可撤销的事务**（审计链与盘上现实脱节）；让 agent 自动赢 = 吞掉人的
编辑意图。两者都禁止 ⇒ 只剩"**拒绝 + 明示选择**"。

| 场景 | 谁赢 | 依据 |
|---|---|---|
| 用户正在编辑 F，agent apply 改 F | **用户**（agent 等 / 拒） | 规则 2 |
| 用户 buffer 落后（F 已被 agent 改过），用户点保存 | **都不自动赢**：拒保存 + 弹冲突 | 规则 1 + 3 |
| 两个窗口（`open_new_window` = **独立进程**）同时保存 | 后写者被拒 + 提示 | 规则 1 |
| 两个 agent 会话同时 apply | 先到先得，后到拒 | 规则 1（版本令牌天然覆盖） |
| 用户手改后点「撤销」 | **拒绝撤销**（保留备份） | 与规则 1 同向；`post.json` 写后哈希校验（已实现） |

**实现形状（本轮已落后端一半）**

- **版本令牌**：`storage/file_version.py` 提供 `file_version` / `rel_version` / `with_version` /
  `guard_save`；`ui.py` 的 `load_document` 追加 `version` 字段（**只增不改**，旧读者忽略），
  `save_document` 追加可选 `base_version`（**空串 = 不校验 ⇒ 旧行为逐字不变**）。
  `services/document.py` **一行未动** —— 两个 RPC 用**等量替换**委托进新模块（零行漂移）。
- **agent 侧**：`preview_plan()` 返回 `base_versions`（= 用户看过的那一版）⇒ apply 时原样传回；
  `apply_plan()` **先比版本再谈 plan**（文件都变了还报"plan 非法"是误导），不一致 ⇒ `stale_write`
  且**尚未建备份、未写盘**；调用方没给基准时退化为"本次编译时那份"的最低限度自检。
- **未做（下一步）**：前端保存路径带上 `version` 并处理 `stale_write`（三选一弹窗 + i18n 中英）；
  apply 期间的前端忙位与"当前文件正被编辑 ⇒ 拒 apply"。
- **前端一半（同日落地，追加记录）**：`app.js` **IIFE 内四处同行内替换**（零行漂移，`git diff` 可证
  只有 `@@ -124 / -133 / -135 / -137 @@` 四个单行 hunk + 文件尾追加块）——
  `syncToDisk` ① 守卫行加 `MemoriaWriteGuard.deferIfBusy(markDirty)`（忙 ⇒ 重新入队让路）
  ② 保存调用带 `state.doc?.version` ③ 成功后把响应的新版本滚回 `state.doc.version`；
  并在**文件末尾追加** `(function memoriaWriteGuard(){…})()`：`setBusy`（供 agent apply 前后置位）、
  `deferIfBusy`、`onSaveFailed`（只接管 `stale_write`），以及**三选一弹窗**（复用既有
  `.-modal` 样式，与 `confirmTreeAction` 同构）：「重载（丢弃我的编辑）」→ `openFile(path)`；
  「以我为准（先备份再覆盖）」→ `save_document(..., force=true)`；「稍后」→ 关掉。
  **覆盖前先备份**由后端 `guard_save(force=True)` 保证（走 `services/agent/backup` 落
  `manual-force/<txid>` 批次 + `post.json` ⇒ 可直接 `restore_batch` 撤销；备份失败即拒写）。
  i18n 用**文件末尾 `Object.assign`** 追加 `writeConflict.*`（中英各 8 键，selftest 通过）。
  验收：`pytest -q` **409 passed**；`node --check` 3/3；`scripts/i18n_selftest.js` 全 PASS。
  前端接线已用测试钉住（`test_frontend_wires_version_token_and_conflict_dialog` +
  `test_conflict_dialog_keys_exist_in_every_locale`）。
- **仍未做**：apply 期间**前端忙位与 agent 写入口的接线**（等 ④ 的 RPC + 确认卡一起挂：
  届时 `MemoriaWriteGuard.setBusy(true/false)` 包住 apply，并在 apply 前查"当前文件是否正被编辑
  ⇒ 脏则拒 apply"，即规则 2 的另一半）；`_write_body` 的 `WinError 5` 短退避重试仍待拍板。

**明确否掉的两条路（防复发）**

- **多线程**：写路径本身就是**同步短事务**，现状**没有写锁**（现有锁只覆盖词法索引 / executor /
  kp_index / embedding / agent 作业）。开多线程只会把"文件级并发"升级成"进程内竞态 + 部分写"
  ⇒ **不做**；正确方向是**串行 + 版本校验**。
- **增量修改**：行级 patch 同样基于某个基准版本、对 lost update **不免疫**；它的价值在写入量 /
  备份体积 / diff 可读性 ⇒ 属优化，**后置**。

**已知环境噪声（与本口径无关，如实记录）**：`_write_body` 的 `os.replace` 偶发 `WinError 5`
（外部 AV / 索引器瞬时持锁；`_write_body` 自身无句柄泄漏：`with` + flush + fsync → close → replace）。
是否加"瞬时锁短退避重试"**待人拍板**（本轮未改）。
