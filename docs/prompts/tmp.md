# DSH Agent Teams 插件：详细使用指示与文件地址

## 一、先看全景：4 个包各管什么

| 包 | 职责 | 你什么时候会碰它 |
|---|---|---|
| `@deepseek-ai/dsh-experimental-agent-team` | 团队领域服务：Lead/成员投影、任务板、派发/退役/改名、消息、持久化 | 改团队语义 / 排查任务板 |
| `@deepseek-ai/dsh-experimental-tool-agent-team` | 11 个模型工具 + Team policy 提示词 + spawn 模式（mechanical/standard/deep/**creator**） | 改工具参数、加 mode、改提示词 |
| `@deepseek-ai/dsh-experimental-client-ui-agent-team` | Web 会话头部的 Agent Teams 入口：roster、任务板、跳转 teammate 会话 | 改 UI / 加面板 |
| `@deepseek-ai/dsh-experimental-agent-team-profile` | 组合层：启用上面三个、禁用旧 `tool-subagent-*`、设上限 16 | 改部署配置（名额/模型路由） |

依赖链：`agent-team-profile`（Cordis patch）→ 挂载 `agent-team` + `tool-agent-team` + `client-ui-agent-team`；`tool-agent-team` 通过 subagent 服务启动 teammate，teammate 的组合可显式指定 Agent preset（Creator 模式就是 preset `cordis`）。

---

## 二、文件详细地址

### 1) DSH 宿主侧（D:\deepseek-harness）

**组合与部署配置**

| 文件 | 用途 |
|---|---|
| `D:\deepseek-harness\packages\experimental\agent-team-profile\cordis.patch.yml` | **团队部署层**：`maxMembers: 16`、任务/消息上限、`mechanicalModel`/`deepModel`、禁用旧 subagent 工具、挂载 UI |
| `D:\deepseek-harness\.dsh\profiles\desktop\package.json` | 当前桌面 profile 的 **bundle 列表**（已含 `@deepseek-ai/dsh-experimental-agent-team-profile`） |
| `D:\deepseek-harness\.dsh\profiles\desktop\cordis.patch.yml` | 你本机 profile 的**用户覆盖层**（改配置优先改这里） |
| `D:\deepseek-harness\packages\bundle\web-app\presets\standard.patch.yml` | 标准 agent preset（普通 teammate 继承这个） |
| `D:\deepseek-harness\packages\bundle\web-app\presets\cordis.patch.yml` | **Creator 模式 preset**（`plugin_manager`、`tool-cordis`、创造技能、plan mode） |
| `D:\deepseek-harness\packages\preset\agent-preset-registry\src\index.ts` | preset 注册表：`mount` / `composeFrom` / `resolve` / `composedPreset` |
| `D:\deepseek-harness\packages\boot\plugin-manager\src\tools.ts` | `plugin_manager` 工具实现（Creator 模式里真正改插件/配置的工具） |
| `D:\deepseek-harness\packages\extensions\tool-cordis\src\index.ts` | `tool-cordis`（运行时插件/服务检查） |

**插件源码**

| 文件 | 用途 |
|---|---|
| `D:\deepseek-harness\packages\experimental\agent-team\src\index.ts` | 服务入口、`ctx.agentTeams` |
| `...\agent-team\src\types.ts` | `SpawnTeammateRequest`（含 `preset`/`model`/`reasoningEffort`/`toolFilter`/`persona`）、`TeamMemberView`、任务类型 |
| `...\agent-team\src\roster.ts` | 成员生命周期、spawn 透传、改名/退役、名额 |
| `...\agent-team\src\task-board.ts` | 任务板 CRUD、revision/owner 校验 |
| `...\agent-team\src\projection.ts` | `agentTeam` 投影（Web/客户端读它） |
| `...\agent-team\src\journal.ts` | append-only `team/member`、`team/task` 事件 |
| `...\agent-team\src\session-message.ts` | 跨成员消息（`send_message` 的落盘形态） |
| `...\agent-team\src\persisted.ts` / `lifecycle.ts` / `activity.ts` | 冷启动恢复 / 生命周期 / 活跃状态 |
| `...\agent-team\src\task-view.ts` / `task-graph.ts` / `validation.ts` | 任务视图、依赖图、参数校验 |
| `D:\deepseek-harness\packages\experimental\tool-agent-team\src\index.ts` | **11 个工具、POLICY、`resolveSpawnMode`、`creatorPreset`** |
| `...\client-ui-agent-team\src\client\TeamAction.tsx` | 会话头部 Agent Teams 按钮/面板 |
| `...\client-ui-agent-team\src\client\mount.ts` | UI 挂载 |
| `...\client-ui-agent-team\locale\{en,zh}.json` | UI 文案 |

**子 Agent preset 支持（Creator 模式的底座，上一轮新增）**

| 文件 | 用途 |
|---|---|
| `D:\deepseek-harness\packages\subagent\subagent\src\types.ts` | `SubagentStartRequest.agentPreset?`、`SubagentCapabilities.agentPreset?` |
| `...\subagent\src\child-agent.ts` | `applyChildComposition()`：显式 preset 用 `agentPresets.mount()`；`childSessionMeta()` 写入 header |
| `...\subagent\src\manager.ts` | `resolveChildPreset()`、fresh/cold-resume 两条路径的 preset 透传 |
| `D:\deepseek-harness\packages\subagent\subagent-spawn-in-process\src\index.ts` | spawn provider，声明 `agentPreset: true` |
| `D:\deepseek-harness\packages\subagent\subagent-fork-in-process\src\index.ts` | fork provider，同样声明 |

**文档 / 目录 / 测试**

| 文件 | 用途 |
|---|---|
| `D:\deepseek-harness\docs\subsystems\agent-team.md` + `.zh.md` | 团队子系统契约（类型等价块） |
| `D:\deepseek-harness\docs\subsystems\subagent.md` + `.zh.md` | subagent 契约（含 `agentPreset`） |
| `D:\deepseek-harness\packages\experimental\agent-team\README.md` + `.zh.md` | agent-team 包参考 |
| `D:\deepseek-harness\packages\experimental\tool-agent-team\README.md` + `.zh.md` | **工具用法 / 配置 / 模型体验**（最实用的入口） |
| `D:\deepseek-harness\packages\experimental\client-ui-agent-team\README.md` + `.zh.md` | UI 行为说明 |
| `D:\deepseek-harness\docs\tool-catalog.md` / `.zh.md` | 工具 schema 全量目录（spawn_teammate 参数以此为准） |
| `D:\deepseek-harness\docs\config-catalog.md` / `.zh.md` | 配置字段全量目录 |
| `D:\deepseek-harness\packages\experimental\agent-team\tests\team.spec.ts` | 团队生命周期/任务板测试 |
| `...\agent-team\tests\projection-events.spec.ts` / `persistence.spec.ts` | 投影 / 持久化测试 |
| `...\tool-agent-team\tests\tool-team.spec.ts` | **Creator 模式、模式路由、工具行为测试** |
| `...\client-ui-agent-team\tests\team-action.client.spec.tsx` | UI 测试 |
| `D:\deepseek-harness\packages\subagent\subagent\tests\activation-presets.spec.ts` | 子 Agent 显式 preset / 冷恢复测试 |

### 2) Memoria 团队资产侧（D:\AAA_Jupyter\Memoria）

| 文件 | 用途 |
|---|---|
| `D:\AAA_Jupyter\Memoria\AGENTS.md` | 顶部「历史载体警告」，§2 三角色已标注 DSH 下退役 |
| `D:\AAA_Jupyter\Memoria\artifacts\agent\agents.json` | schema v2 角色能力目录：lead/executor/auditor/registrar/curator + 3 个 retired |
| `D:\AAA_Jupyter\Memoria\artifacts\agent\dispatch-log.jsonl` | append-only 派发日志（spawn/message/done/retire/backfill） |
| `D:\AAA_Jupyter\Memoria\artifacts\agent\team-board-snapshot.json` | 每轮收口导出的团队快照 |
| `D:\AAA_Jupyter\Memoria\artifacts\agent\curator\audit-2026-10-23\raw.json` | Curator 首次审计（机器可读） |
| `...\audit-2026-10-23\SUMMARY.md` | Curator 首次审计（人可读，含清理候选与「最该改的一件事」） |
| `...\audit-2026-10-23\cleanup-deleted.json` | P5 删除清单（28 文件 / 683.48 MB） |
| `D:\AAA_Jupyter\Memoria\scripts\agent\dispatch_log.py` | 派发日志 `append` / `check` / `--selftest` |
| `D:\AAA_Jupyter\Memoria\scripts\agent\curator_audit.py` | Curator 只读采集器（生成 raw+SUMMARY） |
| `D:\AAA_Jupyter\Memoria\scripts\agent\team_audit.py` | 每轮收口机检（roster/stall/write_scope/artifact_refs） |
| `D:\AAA_Jupyter\Memoria\docs\guides\team-plugin-overhaul-spec.md` | 规格 + 第七部分实施状态（V1–V7 验收） |
| `D:\AAA_Jupyter\Memoria\docs\guides\agent-team-status.md` | 当前真实状态 |
| `D:\AAA_Jupyter\Memoria\docs\guides\dsh-agent-teams-contract.md` | DSH 实操契约（§7 派发日志、§8 Creator/Curator、§9 任务板历史、§10 权限边界） |
| `D:\AAA_Jupyter\Memoria\docs\guides\curator-agent-prompt.md` | Curator 系统提示词（spawn 时用） |
| `D:\AAA_Jupyter\Memoria\docs\guides\agent-team-org.md` | 运行时领域 Owner 组织表 + 收口纪律 |

---

## 三、启用与生效

### 1) 当前 profile 已启用

`D:\deepseek-harness\.dsh\profiles\desktop\package.json` 的 `dsh.profile.bundles` 已包含 `@deepseek-ai/dsh-experimental-agent-team-profile`，无需额外安装。

### 2) 换到别的 profile

在该 profile 的 `cordis.patch.yml` 追加（或直接在 bundle 列表加入 `...agent-team-profile`）：

```yaml
- insert:
    - id: agent-team
      name: '@deepseek-ai/dsh-experimental-agent-team'
      config:
        maxMembers: 16
        maxTasks: 256
        maxMessageBytes: 65536
        disposalTimeoutMs: 5000
    - id: tool-agent-team
      name: '@deepseek-ai/dsh-experimental-tool-agent-team'
      config:
        freshProvider: spawn
        forkProvider: fork
        mechanicalModel: deepseek-flash
        deepModel: deepseek-v4-pro
        creatorPreset: cordis      # 可选；默认就是 cordis
    - id: ui-agent-team
      name: '@deepseek-ai/dsh-experimental-client-ui-agent-team'
```

### 3) 让代码改动生效

- 桌面打包应用：`cd D:\deepseek-harness; pnpm run build:desktop` 后重启桌面应用；或 `pnpm run dev:desktop` 以开发模式跑。
- 从仓库跑 `dsh web`：`pnpm build`（host+client lib）后重启；只改 client 插件时用 `pnpm run dev:web`（watcher 会重建 client 插件 bundle，HMR 生效）。
- 只改 Python/文档（Memoria）：无需构建。

> 当前已打包产物路径（用于核对加载的是哪份代码）：`D:\deepseek-harness\apps\desktop\.desktop-build\targets\win-x64\unsigned-artifacts\win-unpacked\resources\app.asar`

---

## 四、详细使用

### A. 普通 Team 工作流（Lead 视角）

对 Lead 说（模型自己会调工具）：

```
用 Agent Teams 做：1) 创建 executor-a 负责改 X；2) 建任务 task-1 给它；
3) 收口前用 list_agents 检查，读它的磁盘报告，然后 retire 掉。
```

等价工具调用链：

```text
spawn_teammate { name:"executor-a", description:"改 X", prompt:"...", context:"fresh", mode:"standard" }
team_task_create { subject:"...", description:"...", write_scopes:["src/x/**"] }
send_message { target:"executor-a", message:"task-1 已建，认领后开工；完成后把报告路径发我" }
team_task_list {}                       # 看 owner/status/revision
wait_agent { timeout_ms: 60000 }
team_task_get { task_id:"task-1" }
retire_teammate { target:"executor-a" } # Lead only
```

### B. `spawn_teammate` 参数与四种 mode

| 参数 | 必填 | 说明 |
|---|---|---|
| `name` | ✅ | lower-kebab-case，唯一；退役后名字可复用 |
| `description` | ✅ | 一句话职责（也作为 subagent label） |
| `prompt` | ✅ | 完整初始任务书（不含历史对话；对象认知路径直接写进去） |
| `context` | | `fresh`（默认，无 Lead 历史）/ `fork`（继承 Lead 已完成轮） |
| `mode` | | `mechanical`（reasoning off + 可配廉价模型）/ `standard`（默认）/ `deep`（高推理）/ **`creator`（Creator 模式）** |
| `model` | | 显式模型覆盖；省略用 mode 默认/部署默认 |

返回：`{"member": { target, role, status, description, provider, context, model?, diagnostics }}`。后续 `send_message`/任务 owner 都用 `target`。

### C. Creator 模式（重点）

**前提**
1. 当前 profile 有 Agent preset registry（Web/桌面自带）；
2. Creator preset 可用——默认 `cordis`（`packages/bundle/web-app/presets/cordis.patch.yml`）；
3. Lead 会话权限足够：`plugin_manager` 改 profile 需要 `danger-full-access` 或单次审批，否则失败关闭。

**调用**

```text
spawn_teammate {
  name: "plugin-curator",
  description: "维护 DSH 插件与 profile",
  prompt: "先只读盘点：用 plugin_manager list_plugins 列出当前 profile 的插件，找出未启用但被显式配置的插件，输出表格；不要修改任何配置。",
  context: "fresh",
  mode: "creator"
}
```

**Creator teammate 能做什么**
- `plugin_manager`：`list_plugins` / `list_bundles` / `set_plugin` / `set_bundle` / `install_bundle` / `remove_bundle` / `set_version_exemption` 等；live profile 立即生效，startup profile 需重启。
- `tool-cordis`：检查已挂载服务、插件 inventory、schema。
- 创造技能：`agent-experience`、`cordis-plugin-development`、`editing-cordis-compositions`、`cordis-composition-reference`（路径 `D:\deepseek-harness\packages\preset\agent-preset\skills\...`）。
- 仍保留 Team 工具（`send_message`/`list_agents`/任务板），可回报进度。

**验证它真的进了 Creator 模式**
```text
list_agents {}  → 该成员 status=inactive/running
send_message { target:"plugin-curator", message:"汇报你当前可用的插件管理工具与 preset 名称" }
```
它回复里应出现 `plugin_manager` / `cordis`；在 UI 的 Agent Teams 面板点进它的会话可看完整工具调用。

**边界**
- DSH 沙箱没有子路径白名单：Creator teammate 的写域靠 preset 工具集 + 提示词 + 审批约束，不是硬隔离。
- 没有 cron：不能定时跑，只能 Lead 显式派发或用户关键词触发。
- `persona` / `tool_filter` / 裸 `preset` 目前是**服务级 API**（`SpawnTeammateRequest`），`spawn_teammate` 工具只暴露 `mode`/`model`。

### D. 11 个工具速查

| 工具 | 作用 | 关键参数 |
|---|---|---|
| `spawn_teammate` | 创建持久 teammate | `name, description, prompt, context?, mode?, model?`（Lead only） |
| `send_message` | 消息/steer/唤醒 | `target, message` |
| `list_agents` | 花名册与可用性 | 无 |
| `wait_agent` | 等下一次状态/消息/任务变化 | `timeout_ms`（10s–1h） |
| `interrupt_agent` | 中断当前 turn | `target`（Lead only） |
| `update_teammate` | 改名/改描述 | `target, name?, description?`（Lead only；任务 ownerName 自动跟随） |
| `retire_teammate` | 退役、释放名额/会话 | `target`（Lead only；provisioning 时拒绝） |
| `team_task_create` | 建任务 | `subject, description, blocked_by?, write_scopes?` |
| `team_task_list` | 任务板（含 completed，不只 pending） | `status?, owner?, ready?, limit?, cursor?` |
| `team_task_get` | 单任务最新 revision | `task_id` |
| `team_task_update` | claim/release/edit/complete 等 CAS | `task_id, expected_revision, action, ...` |

### E. Memoria 的 Curator 用法

```text
spawn_teammate {
  name: "team-curator",
  description: "审计并维护团队资产",
  prompt: "读取 docs/guides/curator-agent-prompt.md 作为你的系统角色。先跑 python scripts/agent/curator_audit.py --date <今天> 与 python scripts/agent/dispatch_log.py check；然后按提示词审计，实际修改 artifacts/agent/agents.json / 契约 / status；删除动作必须先列清单给人类确认。",
  mode: "creator"
}
```

派发/收口日志（Lead 必做）：

```powershell
cd D:\AAA_Jupyter\Memoria
$env:PYTHONIOENCODING="utf-8"
python scripts/agent/dispatch_log.py append --actor lead --target team-curator --phase spawn --task team-audit --desc "首次团队审计"
python scripts/agent/dispatch_log.py check
```

收口机检：

```powershell
python scripts/agent/team_audit.py          # 要求 FAIL=0
python scripts/agent/team_audit.py --selftest
```

### F. 进阶：服务级 API（写自定义插件时）

```ts
// 在某个插件里拿到团队服务
const team = ctx.agentTeams
const { member } = await team.spawnTeammate(caller, {
  name: 'plugin-curator',
  description: '维护插件',
  prompt: [{ type: 'text', text: '...' }],
  context: 'fresh',
  provider: 'spawn',
  preset: 'cordis',            // ← Creator 模式
  toolFilter: { deny: ['pwsh'] }, // ← 服务级
  persona: '...',                 // ← 服务级
  signal,
})
```

子 Agent preset 的底层契约见 `SubagentStartRequest.agentPreset`（`packages/subagent/subagent/src/types.ts`）：显式 preset 会记录在子 Session header，冷恢复时自动重新挂载同一 preset。

---

## 五、配置参考

| 插件 | 字段 | 默认 | 说明 |
|---|---|---|---|
| `agent-team` | `maxMembers` | 16 | 非退役 teammate 上限（不含 Lead） |
| | `maxTasks` | 256 | 未删除任务上限 |
| | `maxMessageBytes` | 65536 | 单条 sender-framed 消息上限 |
| | `disposalTimeoutMs` | 5000 | 收口/排空超时 |
| `tool-agent-team` | `freshProvider` | `spawn` | 新 teammate 用的 subagent provider |
| | `forkProvider` | `fork` | fork 模式的 provider |
| | `mechanicalModel` | 继承部署默认 | `mechanical` 模式的模型 |
| | `deepModel` | 继承部署默认 | `deep` 模式的模型 |
| | `creatorPreset` | `cordis` | `creator` 模式用的 Agent preset |

---

## 六、故障排查

| 现象/报错 | 原因 | 修复 |
|---|---|---|
| `agent preset registry` 报错 | 运行组合里没有 Agent preset registry（headless 自定义组合常见） | 挂载 `@deepseek-ai/dsh-agent-preset-registry`；或去掉 `mode:"creator"` |
| `agent preset "cordis" is unavailable` | 该 profile 没有 `cordis` preset | 在 profile bundle 里启用 web-app presets，或把 `creatorPreset` 改成实际存在的 preset |
| `tool "send_message" is already registered in this scope` | Creator preset 与 Team 工具同名（旧 subagent 控制未禁用） | 确认 profile 用了 `agent-team-profile`（它禁用 `tool-subagent-control`/`tool-subagent-list-agents`） |
| `Team member limit 16 reached` | 名额满 | `list_agents` 找出闲置成员 → `retire_teammate` |
| `only the Team Lead` | 非 Lead 调维护工具 | 由 Lead 执行 |
| `plugin_manager` 失败/被拒 | 权限不足（非 danger-full-access 且无审批） | 在权限足够的 Lead 会话里 spawn；或为单次操作开审批 |
| `wait_agent` 立即 `noProgress` | 没有 running/provisioning 的 peer | 先 `send_message` 唤醒目标再等 |
| 改了代码但行为没变 | 运行的是已打包 `app.asar` | `pnpm run build:desktop`/`pnpm build` 后重启（或 `dev:desktop`） |

---

## 七、验证命令与测试地址

```powershell
cd D:\deepseek-harness

# 类型 & 测试（团队 + 子 Agent preset）
node .\node_modules\typescript\bin\tsc -p tsconfig.host.json --noEmit
pnpm exec vitest run packages/subagent packages/experimental/agent-team/tests packages/experimental/tool-agent-team/tests

# 只跑 Creator 模式相关
pnpm exec vitest run packages/experimental/tool-agent-team/tests -t "Creator"

# 目录同步门禁
pnpm run verify-tool-catalog
pnpm run verify-config-catalog
pnpm run verify-type-equiv
```

Memoria 侧：

```powershell
cd D:\AAA_Jupyter\Memoria
$env:PYTHONIOENCODING="utf-8"
python scripts/agent/dispatch_log.py check
python scripts/agent/dispatch_log.py --selftest
python scripts/agent/team_audit.py
python scripts/agent/curator_audit.py --date 2026-10-23
```

**测试文件绝对地址**
- `D:\deepseek-harness\packages\experimental\tool-agent-team\tests\tool-team.spec.ts`
- `D:\deepseek-harness\packages\experimental\agent-team\tests\team.spec.ts`
- `D:\deepseek-harness\packages\experimental\agent-team\tests\projection-events.spec.ts`
- `D:\deepseek-harness\packages\experimental\agent-team\tests\persistence.spec.ts`
- `D:\deepseek-harness\packages\experimental\client-ui-agent-team\tests\team-action.client.spec.tsx`
- `D:\deepseek-harness\packages\subagent\subagent\tests\activation-presets.spec.ts`