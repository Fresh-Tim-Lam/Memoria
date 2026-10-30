# 团队协议注册表（`team/protocols.json`）

> **状态**：生效中（2026-10-30，v9 / schema `team-protocols/v1`，registryVersion 1）
> **数据**：本文件是 **语义权威**；[`team/protocols.json`](../../team/protocols.json) 是它的**机器投影**（`team_protocol_list` 可读）。
> **漂移**：注册表条目的 `source.{path,anchor}` 指向本文件对应小节；若本文件小节标题/内容被改而注册表未同步，
> `team_protocol_list` 会返回 `protocolNotice{status:"drift"}`（插件侧文本子串启发式，已登记已知盲区）。
> **目的**：把 Memoria 团队**真实在执行的约束**从"人记得"变成"插件可读、可审计、能拒绝的协议"。
> **原则**：宁少勿滥；每条必须有真实条款/事故锚点；没有现行条款支撑的只能进[附录 A](#附录-a未注册候选及原因)（不进 json）。

---

## 0. 先说清三个术语（与原件 schema 对齐，避免误读）

| 本文用词 | 注册表字段 | 取值 | 含义 |
|---|---|---|---|
| 强制方式 | `enforcement` | `refuse` / `audit` / `warn` | `refuse`=插件**会拒绝**该操作；`audit`/`warn`=只记录/提示，**不拒绝**。`refuse` 只允许 `origin=plugin`，且必须含插件白名单谓词。 |
| 约束类型 | `constraints[].type` | `format` / `semantics` / `topic` | `format`/`semantics` 可机检（白名单：`integer-range`、`complete-requires-evidence`）；**`topic` 只审计不拒绝**。 |
| 来源 | `origin` | `plugin` / `convention` | `plugin`=插件侧承载强制；`convention`=团队条款承载（插件只能审计），必须有 `source`。 |

> ⚠️ 与任务书字段名的对应：任务书里的 `why` **不是** schema 字段（`additionalProperties:false`），
> 故本文件把"为什么"写进 `history[].note` + 本表的**依据**列；任务书里的 `check` 对应 schema 的 `checks[]`（`{id,kind,command?}`）；
> 任务书里的 `format|semantics|topic` 对应上面的**约束类型**，而强制度用 `enforcement` 表达。

---

## 1. 八条已注册协议（总表）

| id | 版本 | 强制方式 | 拒绝/审计条件 | 依据（真实条款或事故） |
|---|---|---|---|---|
| `P-01 tool.peerMessage.hops` | 1.0 | **refuse**（format） | peer 直发消息 `hops` 超出部署配置 `peerMessageMaxHops`（默认 4）⇒ `TEAM_PEER_HOPS_EXCEEDED` | 插件 v9 R-06；DSH 测试实例 `5>4` 被拒；`dispatch-log.jsonl` 608 条 message 真实流量 |
| `P-02 evidence-on-complete` | 1.0 | **refuse**（semantics+format） | `task.complete` 既无 `evidence[]` 也无 `no_artifact_reason` ⇒ `TEAM_TASK_EVIDENCE_REQUIRED` | AGENTS §0.5 L3；插件既有拒绝（v8 起） |
| `P-03 workflow-version-plan-ref` | 1.0 | audit（topic） | 版本级任务（subject/description 含 X.Y.Z）无/错 `plan_ref` ⇒ 原生 `TEAM_PLAN_REF_REQUIRED` / `TEAM_PLAN_REF_MISMATCH`（**注册表只登记不新增强制**） | AGENTS §0.5 L8；插件 `plan-ref-required` |
| `P-04 org-group-single-domain` | 1.0 | audit（topic） | 组成员与组声明域不一致 ⇒ 原生 `TEAM_GROUP_DOMAIN_MISMATCH` | 插件 v9 `member-group-membership`；`roster.ts:752` |
| `P-05 tool.peerMessage.groupIsolation` | 1.0 | audit（topic） | 跨工作组成员直接点对点消息 ⇒ 原生 `TEAM_PEER_GROUP_ONLY` | 插件 v9 `peer-message-governance`；`index.ts:929` |
| `P-06 dispatch-task-before-spawn` | 1.0 | audit（topic） | spawn 行缺 task / task 不存在 / spawn 早于 task 创建 ⇒ `team_audit.py::l1_task_before_spawn` 报 FAIL | AGENTS §0.5 L1；SF-052（真实抓到 task-113 先 spawn 后建任务） |
| `P-07 safety-shared-workspace-destructive-revert` | 1.0 | audit（topic） | 对共享主工作区执行 `checkout --`/`reset --hard`/`restore` 等 ⇒ 违 B-danger-1（当前**无人可拒绝**，见条款"强制力诚实标注"） | lead-dispatch-rules §B-danger-1；2026-10-26 render-perf 事件 |
| `P-08 workflow-frontend-verification` | 1.0 | audit（topic） | 前端/面板改动未按 V-frontend-1 真机验证，或同组件连续 3 次不通过仍打补丁 ⇒ 违 V-frontend-1/2 | lead-dispatch-rules §V-frontend-1/2；2026-10-29 五轮验收失败事故 |

> 强制力口径（诚实）：本注册表**只有 P-01/P-02 会真正拒绝**（因插件有对应白名单谓词）；
> P-03…P-08 的 `audit` 表示**注册表只登记/审计、不改变工具行为**——其中 P-03/P-04/P-05 的原生拒绝由插件代码单独实现
> （错误码见"依据"列），P-06 由 `team_audit.py` 事后机检，P-07/P-08 目前**只能人工评审**（见各自小节）。

---

## 2. 逐条说明

### P-01 tool.peerMessage.hops — peer 直发跳数上限

- **条款/依据**：插件 v9 协议示例 `examples[0]`（R-06）；真实流量：`team/dispatch-log.jsonl` 有 608 条 `phase=message`。
- **约束**：`format.assert=integer-range`，`field=hops`，`min=0`，`maxFromConfig=peerMessageMaxHops`（部署默认 4）。
- **拒绝条件**：peer 直发链路的 `hops` 超过配置上限。
- **必拒绝样例**：两名同组成员互相直发，hop 计数到 **5**（> 默认 4）⇒ `TEAM_PEER_HOPS_EXCEEDED`（并带 `protocol_id=tool.peerMessage.hops@1.0`）。
- **必通过样例**：hop 计数 **4** 或以下 ⇒ 正常投递。
- **已知细节**：Lead 作为收件人不参与 peer hop 计数；Lead 插话会重置 peer 链路（真实行为，见 `TEAM-USAGE.md §12`）。

### P-02 evidence-on-complete — 收口必须有可验证产物

- **条款/依据**：AGENTS §0.5 **L3**（关闭任务必须有 evidence；工具已强制）；插件 v8 起 `TEAM_TASK_EVIDENCE_REQUIRED`。
- **约束**：`semantics.assert=complete-requires-evidence`（`artifactRequired:true`）+ `format`（`evidence[]` 每项 `path` 必填、`sha256` 64 位小写 hex）。
- **拒绝条件**：`task.complete` 既无 `evidence[]`，也无 `no_artifact_reason`。
- **必拒绝样例**：`team_task_update(action="complete", evidence=[])` 且不填 `no_artifact_reason` ⇒ `TEAM_TASK_EVIDENCE_REQUIRED`。
- **必通过样例**：`evidence=[{"path":"team/steward/audit-2026-10-26-r9/SUMMARY.md"}]`（可附 `sha256`）⇒ 通过。

### P-03 workflow-version-plan-ref — 版本级任务必须先有计划

- **条款/依据**：AGENTS §0.5 **L8**（版本级规划必须由 todo-owner 产出并写进 `docs/todo.md`，Lead 不得凭记忆排期）；插件 v9 `plan-ref-required`。
- **注册表行为**：`audit`（topic）——**注册表本身不新增拒绝**；真实拒绝来自插件：版本级任务缺 `plan_ref` ⇒ `TEAM_PLAN_REF_REQUIRED`；
  `plan_ref` 不是 `docs/` 下文件或未提到该版本 ⇒ `TEAM_PLAN_REF_MISMATCH`。
- **审计对象**：`task.create` 动作上 `planRef` 是否随任务落盘（`checks` 引用两个原生错误码）。

### P-04 org-group-single-domain — 组与声明域唯一

- **条款/依据**：插件 v9 `member-group-membership`（组配额 + 组↔域唯一）；`TEAM_GROUP_DOMAIN_MISMATCH`（`roster.ts:752`）。
- **注册表行为**：`audit`（topic）；真实拒绝由插件在 `team_set_member_group` 等动作执行。
- **语义**：一个工作组的成员必须覆盖该组的声明域；把无该域的成员塞进组 ⇒ 拒绝。
- 例：`memoria-governance`（治理组）成员须有治理/组织类域；把纯 UI 成员直接加入 ⇒ `TEAM_GROUP_DOMAIN_MISMATCH`。

### P-05 tool.peerMessage.groupIsolation — 跨组只经 Lead

- **条款/依据**：插件 v9 `peer-message-governance`（`TEAM_PEER_GROUP_ONLY`；`index.ts:929`）。
- **注册表行为**：`audit`（topic）；真实拒绝由插件执行：跨工作组成员不能直接 `send_message`，必须经 Lead 派发。
- 例：`steward`（memoria-governance）直接消息 `render-perf`（release-ops）⇒ `TEAM_PEER_GROUP_ONLY`；经 Lead 转发 ⇒ 允许。

### P-06 dispatch-task-before-spawn — 先建任务再 spawn

- **条款/依据**：AGENTS §0.5 **L1**（spawn 前必须先建任务并声明 writeScope）；SF-052 新增 `team_audit.py::l1_task_before_spawn`。
- **注册表行为**：`audit`（topic）；机检由 `team_audit.py` 事后执行（不是工具拒绝）。
- **真实证据**：`task-113` spawn 时间 2026-10-24T16:42:52Z **早于** task 创建 16:52:53Z（约 10 分钟）；另有 Lead 自报 2 次 L1（1 次导致成员干完发现板上无任务）。
- **通过条件**：spawn 行带 `task`，task 在台账（快照/轨迹/日志非 spawn 行）存在，且创建事件不晚于 spawn。
- **已知存量（2026-10-30，不回填）**：`team_audit.py::l1_task_before_spawn` 上线后报 **11 条**插件 spawn 缺配对 `task`（检查上线前的历史，样本 `retrieval-researcher`）。**保持 FAIL 不回填/不造假**；是否清洗另开票（见附录 D）。

### P-07 safety-shared-workspace-destructive-revert — 禁止对共享工作区破坏性回滚

- **条款/依据**：`docs/guides/lead-dispatch-rules.md` **§B-danger-1**（2026-10-26 v2.1）；真实事故：render-perf 为 pre/post 对照
  在共享工作区 `git checkout -- app.js` 约 90 秒，当时 sync-mapper 正在同一文件做 task-168（核对后未丢，属运气非方法）。
- **注册表行为**：`audit`（topic）——**目前没有任何机制能拒绝**（`checkout -- <file>` 不写 reflog，事后不可取证）；
  条款明确"工具拦截落地前不得宣称已机检保护"。
- **禁止清单**：`checkout -- <path>` / `checkout .` / `checkout <ref> -- <path>` / `restore` / `reset --hard|--merge` /
  `clean -f*` / `stash drop|clear` / `apply -R` / `update-index --assume-unchanged|--skip-worktree` / `worktree remove --force`。
- **例外**：仅 Lead 可发起 R1 例外，成员需 Lead 授权并在 `dispatch-log` 留痕（`phase=risk` + 完整命令 + 理由 + 执行前 sha256 快照 + 事后差集核对）。

### P-08 workflow-frontend-verification — 前端必须真机验证、三次回归停手

- **条款/依据**：`docs/guides/lead-dispatch-rules.md` **§V-frontend-1**（验收只认"dev 实例注入样例后真机看见效果"）+
  **§V-frontend-2**（同组件连续 3 次验收不通过 ⇒ 停止打补丁，先改架构规范）（实际小节标题：`V-frontend-1 前端效果验证（2026-10-29，强制）` / `V-frontend-2 三次回归即停止打补丁（2026-10-29，强制）`）；事故：2026-10-29 面板改造"单测全绿/构建通过/口头已修"但真机仍坏，
  同组件连续 5 轮验收失败。
- **注册表行为**：`audit`（topic）；仅人工评审（无自动机检），`checks` 标 `kind=review`（V-frontend-1 / V-frontend-2）。
- **通过条件**：附 dev 注入截图 + DOM 指标 + "示例数据（dev 注入）"横幅；连续 3 次回归的组件必须先有架构规范更新记录。

---

## 3. 未注册候选及原因（附录 A：不臆造、不硬塞）

| 候选 | 真实依据 | 为什么本轮不注册 |
|---|---|---|
| 发版三查（标题格式/双语/造价段/远端 tag） | lead-dispatch-rules §4、L5；真实事故：v0.4.6 本地 tag 从未推送到远端 | 属**低频人工评审**（Lead 亲跑）；注册表只能 `audit`，无法增强强制力；且 `release-manager` 已有常驻职责。留待 registryVersion 2 与 release 检查合并登记。**2026-10-30 Lead 裁定：等 `release-manager` 有活跃任务时再评估能否机检；现在不升格。** |
| L9 spawn 必须显式 `mode` / 禁用默认 pro | AGENTS §0.5 L9；插件 `TEAM_PRO_MODEL_FORBIDDEN` | 插件原生拒绝已存在；但 L9 条款只约束"显式 mode"，未直接规定 pro 禁用（pro 禁用是插件默认），证据锚不齐；不下沉成协议。 |
| L10 决策留索引（Decision/Why） | AGENTS §0.5 L10；`team/decisions.jsonl` 已有记录 | `enforcement` 只能是人工评审，且"提交内 Decision/Why"无 machine check；放附录。 |
| 跨域借用（P-A）/ 工作类型 seminar（P-B）/ 组配额（P-G） | 插件 v9 错误码（`TEAM_TASK_DOMAIN_FIT_REQUIRED` 等） | 与 P-04/P-05 同属"组织/派发"组，避免条目膨胀；下一版按组内聚合登记。 |
| B3 steward 收据 / prompt_drift 门禁 | org.md §2.6 B3 / team_audit 检查 | 已被 `team_audit.py` 机检覆盖，且属团队**自身审计**而非协作协议；不作为 team protocol 注册。 |
| 前端 V-frontend-1 的"一键脚本"路径 | rules §V-frontend-1 V3 | 只是操作提示，不是约束。 |

**共通判据**：没有"真实条款 + 可指认依据"、或没有"机检/人工评审载体"的，都不进 json。

---

## 4. 校验与复跑

```powershell
# 1) 注册表可读且无漂移（应 configured=true，且无 protocolNotice）
python - <<'PY'   # 或用工具 team_protocol_list
PY

# 2) 注册表结构/漂移的直接入口（Agent 环境）
#    team_protocol_list            → configured/条目/protocolNotice
#    team_protocol_list include_inactive=true

# 3) 团队审计（注册表不应引入 team_audit FAIL）
python scripts/agent/team_audit.py --json
```

**漂移修复**：改本文件小节标题/内容后，同步更新 `team/protocols.json` 中对应条目的 `source.anchor`；
或恢复被改掉的标题文本（插件是"规范化锚点子串"启发式，不解析 markdown 标题层级）。

---

## 附录 B：与任务书字段的差异（防误读）

- 任务书写 `origin` = "derive-from: file:line 或 dispatch-log 证据"；**插件 schema 中 `origin` 是 `plugin|convention` 枚举**，
  证据锚改由 `source.{path,anchor}` + 本表格"依据"列 + `history[].note` 承载（否则 registry 直接 `TEAM_PROTOCOL_INVALID`）。
- 任务书写 `enforcement: format|semantics|topic`；实际是 `enforcement: refuse|audit|warn` + `constraints[].type: format|semantics|topic` 两层。
- 任务书写 `check`；schema 是 `checks[]`（`id/kind/command?`），本注册表用它引用真实错误码或机检 id。

## 附录 C：变更记录

| 日期 | 变更 |
|---|---|
| 2026-10-30 | 首版 `registryVersion=1`：登记 8 条（P-01..P-08）；其中只有 P-01/P-02 会真正拒绝（插件白名单谓词），其余为 audit/登记 + 审计。 |

## 附录 D：已知存量（FAIL 保持，不回填；清洗另开票）

> 登记时间 2026-10-30。原则：**检查上线前发生的历史问题不回填、不造假**；保持 FAIL 可见，清洗走独立票。

| 来源检查 | 存量 | 处置 |
|---|---|---|
| `team_audit::l1_task_before_spawn`（P-06） | **11 条**插件 spawn 缺配对 task（上线前历史；样本 `retrieval-researcher`） | 保持 FAIL；本表留痕；是否清洗另开票（不回填 dispatch-log） |
| `team_audit::silent_failure S2` | **8 条** done 引用产物不存在（实际为跨仓路径迁移：产物在 DSH 仓） | **已由 task-246（2026-10-30）按更正协议处理**：追加 8 条 `phase=backfill` + `corrects`（append-only，未改旧行），指向 `team/steward/task-246-s2-cleanup.md`（逐条结论 + DSH 实际路径 + sha256）；S2 FAIL → 0 |
| `team_audit::deliberation_quality dq6` | 1 个 pycache 产物未跟踪 | **已由 task-246 清理**：删除 debate 下 2 个 `__pycache__`（生成缓存，可再生）；dq6 FAIL → 0（注：dq6 是 `rglob` 磁盘扫描 vs `git ls-files`，`.gitignore` 对它无效，故只能删缓存） |
| `deliberation_quality dq5` / `steward_self_audit` | 已由 2026-10-30 refreeze（`standards_updated[5]`）+ steward r10 解决 | 已闭环 |

> 注：dq5/tooling（`team_audit.py` sha 与 freeze 不一致）属 R-R6 裁决的预期 WARN，不阻断裁决。

