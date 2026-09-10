# .memoria/agent — 知识库智能体目录
agent名称：Memoria KB Agent
> 用途：本目录存放**供 Trae 智能体使用**的知识库工具包，由 Memoria 生成与升级。
> 与知识内容无关：`.memoria/` 已被知识库扫描与「构建」跳过，**不会**污染文档树或图谱。

## 文件

| 文件 | 用途 | 谁维护 |
|---|---|---|
| `prompt.zh-CN.md` | 粘贴到 Trae「自定义智能体 → 指令」 | Memoria（升级时覆盖） |
| `kb-spec.zh-CN.md` | 知识库编撰 / 维护规范（智能体每次会话**先读**） | Memoria（升级时覆盖） |
| `preview-formats.md` | 支持格式说明：某种写法**渲染成什么**（渲染写法权威，**按需读**） | Memoria（升级时覆盖） |
| `fsrs.py` | 确定性 FSRS 调度（`due` / `init` / `grade`） | Memoria（升级时覆盖） |
| `review/cards.json` | 复习卡片定义 | 智能体 |
| `review/progress.json` | 复习进度与日志 | `fsrs.py` |
| `.kit.json` | 工具包版本（用于升级比对） | Memoria |

## 红线

- **不手写** `.memoria/manifest.yaml`（由 Memoria「构建」生成）。
- 复习状态只写 `review/**`，**不得**写进 sidecar（避免污染知识语义）。
- 到期日/间隔一律由 `fsrs.py` 计算，不要自己推算日期。

## 升级

Memoria 升级后再次执行「为知识库创建 Trae 智能体」即可刷新本目录文件；
**`review/**` 永不被覆盖**。Trae 智能体无需重建——规则更新只在 `kb-spec.zh-CN.md`。
