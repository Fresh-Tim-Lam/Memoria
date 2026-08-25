# 日志规范

> **用途**：定义日志文件的存放位置、命名、格式约定与生命周期，使调试反馈可预期、可检索、不污染仓库。
> **目标读者**：项目负责人（用户）与 AI Agent（添加日志、排查问题或创建日志文件时必读）。
> **关联文档**：[AAA 讨论元规范](./AAA_讨论元规范.md)（规范书写元规则）；[directory-organization.md](./directory-organization.md)（目录组织）；[docs-management.md](./docs-management.md)（docs 组织）。

---

## 1. 日志存放位置

| 场景 | 位置 | 说明 |
|------|------|------|
| 开发期调试日志（前端/后端） | `logs/`（仓库根） | 统一日志区，已被 `.gitignore` 忽略 |
| 一次性调试产物（脚本输出、截图、CDP 诊断） | `artifacts/` | 临时垃圾区 |
| 发布态运行时诊断 | 应用数据目录 / KB 根 `.memoria/` | 由代码写入，不进仓库 |
| harness 测试环境日志 | `docs/example/rich-content-test/` | 测试附属产物，随测试环境保留 |

**禁止**：日志文件放入 `src/`、`docs/`（rich-content-test 测试环境除外）、`scripts/`。

## 2. 文件命名

格式：`<主题>-<类型>.log`

- 主题：kebab-case 小写，描述日志关注点（如 `block-skip`、`window`、`mapping`）
- 类型：`debug`（调试）/ `diag`（诊断）/ `repro`（复现）
- 示例：`logs/block-skip-debug.log`、`window-diag.txt`

## 3. 日志格式约定（项目惯例固化）

统一格式：`[HH:MM:SS.mmm] #N [TAG] message`

| 段 | 约定 |
|----|------|
| 时间戳 | `[HH:MM:SS.mmm]`，毫秒级 |
| 序号 | `#N`（可选），跟踪同事件触发次数，如 `#1 #2` |
| 标签 | `[TAG]` 大写标识模块/事件，如 `[SYNC]` `[BRUSH]` `[MAP]` `[IMG]` `[NED]` `[DBL]` `[UNDO]` |
| 级别 | 消息内用 `[DBG]`/`[INFO]`/`[WARN]`/`[ERR]` 标注（或由 TAG 语义区分） |
| 可检索性 | 诊断类日志在标签内嵌入固定关键词（如 `[img-debug]`、`[img-rewrite]`、`[SYNC]`），便于全局 grep 定位 |

示例（取自现有日志）：

```
[21:16:48.905] #1 [NED] isNonEditableBlock(89) type=paragraph → false
[21:16:49.073] #3 [DBL] ─── dblclick fired ───
[SYNC] setViewMode: source → split | dirty=false
```

## 4. 生命周期

1. **临时调试日志**：问题解决后**删除日志文件**，并从代码移除注入点（或改为开关控制，如 `_SYNC_LOG=false`、`MEMORIA_DEBUG`）。
2. **持久诊断日志**（如 `window-diag.txt`、`frameless-ok.txt`）：保留最近一次，**覆盖写而非追加**，避免无限膨胀。
3. **日志不提交**：`logs/` 已被 gitignore；不要 `git add` 日志文件。
4. **调试完成后清理**：排查结束时顺手删除不再需要的日志文件（放 `artifacts/` 或 `logs/` 均可，仓库不跟踪）。

## 5. 排查流程指引

1. 确定问题模块 → 按对应 `[TAG]` 全局 grep（`[BRUSH]`、`[MAP]`、`[IMG]` 等）
2. 开发态：查 `logs/` + F12 console
3. 发布态：查 `Package/`（window-diag.txt、frameless-ok.txt）或应用数据目录
4. harness 复现：查 `docs/example/rich-content-test/*.log`
5. 日志关闭开关：`MEMORIA_DEBUG=0`（发布态默认关）；代码内 `_SYNC_LOG=false` 可关同步日志
