# Context（AI 上下文）

> 用途：**喂给 AI 的项目说明文档**（AI skill 注入 / 工作交接 / 新 agent 上手）。内容为说明性知识：架构总览、术语表、关键约束解读、常见操作指引。

## 使用方式

- 交接 / 新会话：先读本目录下所有文档（按 README 顺序），再读 `docs/standards/` 中与本任务相关的规范
- 本目录与 `standards/` 的关系：standards 是"必须遵守的规则"，本目录是"理解项目的知识"，两者配套使用

## 文档索引

| 文件 | 内容 |
|------|------|
| [usage-agent-workflow.md](usage-agent-workflow.md) | 知识库生产流水线：内容生成 Agent → 平面文件 → 转换 Agent → 知识库文件夹（双角色规则、质量标准、自维护机制） |
| （待补）architecture.md | 系统架构总览：双壳（pywebview/PyQt6）、静态服务器、前端模块、数据流 |
| （待补）glossary.md | 术语表：KP、sidecar、manifest、contain 边、虚链等 |
| （待补）hard-constraints.md | 关键硬性约束（从项目记忆沉淀，如色板不换行、取色器禁原生 input、Package/lib 同步等） |
| （待补）operations.md | 常见操作指引：开发态/发布态启动、构建、harness 复现、日志位置 |

## 沉淀规范

项目运行中产生的关键结论（修复过的坑、已确认的决策）应定期沉淀到本目录对应文档，避免重复排查。
