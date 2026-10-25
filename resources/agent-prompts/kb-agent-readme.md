<!-- spec-version: 1.1.0 -->
<!-- spec-deps: src/memoria/services/kb_agent.py@0d816956b4d0, src/memoria/services/agent/skills.py@55330f5f7273, src/memoria/services/agent/plugins.py@ffe87c142190, src/memoria/services/agent/session/store.py@004ecb69fbdb, src/memoria/services/agent/backup.py@277a859ddeec, src/memoria/services/agent/scratch.py@d3d631b6e66d, src/memoria/services/agent/attachments.py@d53bf89398bc, src/memoria/services/agent/apply.py@d8b6445f4d5b -->
<!-- reviewed-on: 2026-10-25 -->
# .memoria/agent — 知识库智能体目录
agent名称：Memoria KB Agent
> 用途：本目录存放**供 Trae 智能体使用**的知识库工具包，由 Memoria 生成与升级。
> 与知识内容无关：`.memoria/` 已被知识库扫描与「构建」跳过，**不会**污染文档树或图谱。

## 文件与目录

| 路径 | 用途 | 谁维护 |
|---|---|---|
| `prompt.zh-CN.md` | 粘贴到 Trae「自定义智能体 → 指令」 | Memoria（升级时覆盖） |
| `kb-spec.zh-CN.md` | 知识库编撰 / 维护规范（智能体每次会话**先读**） | Memoria（升级时覆盖） |
| `preview-formats.md` | 支持格式说明：某种写法**渲染成什么**（渲染写法权威，**按需读**） | Memoria（升级时覆盖） |
| `fsrs.py` | 确定性 FSRS 调度（`due` / `init` / `grade`） | Memoria（升级时覆盖） |
| `review/cards.json` | 复习卡片定义 | 智能体 |
| `review/progress.json` | 复习进度与日志 | `fsrs.py`（勿手改） |
| `.kit.json` | 工具包版本（用于升级比对） | Memoria |
| `capabilities.json` | 本库能力插件启停（`{"v":1,"enabled":[{"id":…}]}`；由应用「设置 → 能力」面板维护） | 应用 / 用户可改 |
| `skills/**` | 本库技能（`<name>.md` 或 `<name>/SKILL.md`；frontmatter 必填 `name` + `description`） | 智能体 / 用户 |
| `sessions/**` | 会话记录（应用内 Agent 的 JSONL） | 应用（**勿手改**） |
| `backups/**` | 写入前备份与撤销点 | 应用（**勿手改**） |
| `scratch/**` | 脚本工作区（应用管理；脚本仅在人在场时执行） | 应用（**勿手改**） |
| `attachments/**` | 聊天图片 / 文档附件 | 应用（**勿手改**） |

## 红线

- **不手写** `.memoria/manifest.yaml`（由 Memoria「构建」生成）。
- 复习状态只写 `review/**`，**不得**写进 sidecar（避免污染知识语义）。
- 到期日/间隔一律由 `fsrs.py` 计算，不要自己推算日期。
- **不手改** `sessions/`、`backups/`、`attachments/`、`scratch/`、`capabilities.json`（应用管理目录/文件；改坏会丢会话、撤销点或能力开关）。
- **直接编辑文件不经过应用的写安全闸**（入口唯一 / 读后写 / 写前备份 / 审批）：批量或高风险改动前，先自行备份受影响文件。

## 升级

打开知识库时应用会自动补写/刷新本目录（幂等：内容一致即跳过）；也可手动执行「为知识库创建 Trae 智能体」。
升级只覆盖上表「Memoria」维护的文件（`prompt.zh-CN.md` / `kb-spec.zh-CN.md` / `preview-formats.md` / `fsrs.py` / `.kit.json`）；
**`review/**` 与应用管理目录（`skills/`、`sessions/`、`backups/`、`scratch/`、`attachments/`、`capabilities.json`）永不被覆盖**。
Trae 智能体无需重建——规则更新只在 `kb-spec.zh-CN.md`（每次会话先读）。
