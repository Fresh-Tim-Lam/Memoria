# 能力插件最小协议 v1（capability plugin protocol）

> **用途**：承载产品内 Agent 的**能力插件契约**本身 —— 字段集、暂缓字段、上游对照事实与待讨论项。本文件是该契约的**唯一事实源**；其他文档（含 [agent-capabilities.md](./agent-capabilities.md) §2.1）只留**指针**，**不得复制字段表**。
> **关联文档**：[agent-capabilities.md](./agent-capabilities.md)（**模块设计**：注册与装载 / 写管线与计划 API / 唯一写者 / 备份与撤销 / 权限矩阵 / 四线落法 / M3a 分期）、[dsh-agent-port.md](./dsh-agent-port.md)（**移植总纲**：M1–M2 已落地，M3 写能力待拍板/待实施）。
> **状态**：**活文档 —— 由人逐步对齐**（2026-09-20 建立）。
> **治理约定**：**人主导、逐步对齐**。Agent **只在被明确要求时追加**，**不得改写人已确认的条目**（字段、选项、结论一并适用）；每次改动经人确认后**由人自行定稿**。讨论未完的地方留在 §4，只写"问题 + 可选项"，不代替人下结论。
> 本文表内出现的 `§x` / `P9` 等编号，指 [agent-capabilities.md](./agent-capabilities.md) 的对应小节与待拍板编号。

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

---

## 5. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-20 | 本轮建立。契约正文自 [agent-capabilities.md](./agent-capabilities.md) §2.1 **迁出**：6 字段最小可用契约 v1 + 准入规则（§1）、10 条暂缓字段（§2）、上游事实三条 + `ApprovalOutcome`（§3）、待讨论 Q1–Q6（§4）；两份 JSON 实样与 `kind` 删除演进随迁。`agent-capabilities.md` §2.1 只留指针，§11 追加说明；登记 `conventions/docs-management.md §4.2` |
