# Agent 技能（skill）：编写约定与随包技能

> **状态**：2026-10-12 初稿；随包技能 `skill-creator` / `kb-maintenance` 已落地，编写约定对后续所有技能创作生效。
> **用途**：把 GitHub 高 star skill 生态的**精华**（编写最佳实践）收敛成 Memoria 自己的技能编写约定，并登记随包技能目录与已知漂移。
> **关联文档**：[agent-capabilities.md §4](agent-capabilities.md)（skill 机制设计）、[agent-plugin-design.md](agent-plugin-design.md)（能力插件与写模块总设计）。
> **单一事实源**：技能的**机制**事实源是 `src/memoria/services/agent/skills.py`（frontmatter 契约 / 两段式发现 / `skill` 工具 / `/name` 手势 / 内置只读根）；本文只承载**编写约定**与**随包技能目录**，不重复机制细节，冲突以机制实现为准。

---

## 1. 调研结论（GitHub 高 star skill 的精华）

2026-10 对高 star skill 仓库做的一次横向调研（stars 为当时量级，仅取方向，不承诺精确）：

| 仓库 | 亮点 | 可取之处 |
|---|---|---|
| [anthropics/skills](https://github.com/anthropics/skills)（官方） | SKILL.md 格式 + 渐进披露 + `skill-creator` 元技能 | **格式与触发键**：`description` 写明"何时用"，目录只给摘要 |
| [obra/superpowers](https://github.com/obra/superpowers) | 20+ 实战技能（TDD/debug/协作） | **单一职责 + 可操作步骤**：一个技能一件事，给步骤/示例/清单 |
| [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) | 分类清单 | 题材来源（开发/数据/商业） |
| [K-Dense-AI/claude-scientific-skills](https://github.com/K-Dense-AI/claude-scientific-skills) | 垂直领域覆盖 | 垂直领域技能示范 |
| [travisvn/awesome-claude-skills](https://github.com/travisvn/awesome-claude-skills) | 工作流定制 | 工作流类技能示范 |

**共性精华（可迁移）**：

1. **格式统一**：`SKILL.md` + YAML frontmatter；`description` 是**触发键**（第三人称、写明何时用），不是一句话简介。
2. **渐进披露**：目录只放摘要、正文按需加载、重参考放独立资源文件——不把全部技能说明塞进 system 提示。
3. **单一职责**：一个技能只做一件事，正文精炼（≤几百行）。
4. **可操作 + 边界清晰**：给步骤/示例/检查清单，并写明"何时停下问人、哪些错误码如实转述"。
5. **`skill-creator` 元技能是生态标配**：教模型怎么写好技能，把约定固化进产品本身。

Memoria 的机制（`skills.py`）已实现 1–2 的大部分（源自 dsh 上游 `packages/skill/**`），缺的是**把 3–5 落成产品内容**：`skill-creator` 元技能 + 领域技能 + 集中的编写约定。

## 2. 编写约定（融合后的本地口径）

以下约定固化在随包技能 `skill-creator` 正文里，此处是**要点**：

1. **命名与目录**：技能名 kebab-case；库内根 `<kb>/.memoria/agent/skills/`，目录包 `<name>/SKILL.md` 或平铺 `<name>.md`；同名**库内盖过内置**。
2. **frontmatter 触发键**：`name` + `description` 必填；`whenToUse`（camelCase）补触发场景；`disable-model-invocation` / `user-invocable`（kebab）可选；旧 camelCase 键一律拒。
3. **单一职责**：一技能一事。
4. **自足**：内置技能正文必须自足（资源目录在库外读不到），并明说"别去读我的目录"；库内技能可带 `assets/`，引相对路径要说清解析基准。
5. **停问清单**：把错误码/症状如实转述、不绕不编。

## 3. 随包技能目录

`resources/agent-skills/**`（`bundled` 根，rank 600，库内同名可遮蔽），随版本分发：

| 技能 | 职责 |
|---|---|
| `web-research` | N 线联网工作法（先判断该不该查 → 两把工具取舍 → 落待确认清单 → 何时停下问用户） |
| `skill-creator` | 写技能的元技能（本文 §2 的正文版） |
| `kb-maintenance` | 知识库维护工作法（`propose_write` 的正确用法：先读后写、op 一览、顺序规矩、失败处理） |

随包清单登记于 `packaging/build.py _REQUIRED_RELEASE_RESOURCES`；技能发现/加载的只读性与测试见 `tests/test_agent_skills.py` §⑬。

## 4. 已知漂移与待办

- **`web-research` 的「没有运行工具」已过时**：2026-10-06 起新增 `pwsh` / `cmd` 两把执行工具（`read_only=False` ⇒ 审批门、cwd 限库内，见 `services/agent/shell_exec.py`）。`web-research` 正文里"`scratch_*` 没有运行工具、写好后请用户点面板「运行」"仍按旧口径写，待下一轮顺带订正（订正时须同步更新 `tests/test_agent_skills.py` 里对其正文的断言）。
- **内置技能的资源读取口径未解决**：内置技能的基目录在库外、读取工具到不了，故今天的内置技能**一律不配 `assets/`**、正文自足（见 [agent-capabilities.md §4.6](agent-capabilities.md) 的"已知限制"）。要给内置技能配资源，须先把该目录纳入允许根或改渲染口径。

## 变更记录

| 日期 | 变更 |
|---|---|
| 2026-10-12 | 初稿：调研高 star skill 精华（§1）；收敛编写约定（§2）；新增随包技能 `skill-creator` / `kb-maintenance` 并登记目录（§3）；记录 `web-research` 执行工具口径漂移（§4）。同步更新 `packaging/build.py _REQUIRED_RELEASE_RESOURCES` 与 `tests/test_agent_skills.py` §⑬。 |
