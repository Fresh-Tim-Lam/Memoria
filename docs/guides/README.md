[中文](README.cn.md) | English

# Guides

> **Purpose**: `guides/` holds **how-to guides** — steps and methods for completing specific workflows (collaboration practices, the knowledge-base production pipeline, development/release operations). Aimed at those carrying out the work.
> **Target readers**: Project owner (the user) and AI Agents (read the relevant guide before running a specific workflow).
> **Related docs**: [docs-management.md](../conventions/docs-management.md) (rules for organizing docs); [meta-rules.md](../conventions/meta-rules.md) (meta-rules for writing conventions).

---

## Guides index

| Guide | Content | When to use |
|------|------|---------|
| [collaboration.md](./collaboration.md) | AI coding-collaboration conventions: architecture discussion / module development / testing / debugging / code review | Any development scenario |
| [usage-agent-workflow.md](./usage-agent-workflow.md) | Knowledge-base production pipeline: content generation Agent → user pastes back → conversion Agent | Producing/converting knowledge base |
| [operations.md](./operations.md) | Development/release/build/harness-validation operations manual | Local development and packaging |
| [agent-team-org.md](./agent-team-org.md) | **Agent team organization**: three-layer structure, standing domain owners, dispatch rules, knowledge placement, cost model | Organizing/spawning agents; engineering maintenance |
- [Lead 派发规范](lead-dispatch-rules.md) — 按触发条件分节读（spawn/建任务/收口/发版/压缩后）；不变量摘要见 AGENTS.md §0.5
- [Agent 团队教训库](agent-team-lessons.md) — 踩过的坑 → 可继承的判据（27 条，派发前必读三条）
- [团队工作记录机制与 Steward 设计](team-work-record-and-steward-design.md) — 三层记录（动作/任务/决策）+ 团队管理员边界 + 体量预算 + 首批机检（设计稿，待批准）
| [dsh-agent-teams-contract.md](./dsh-agent-teams-contract.md) | **DSH Agent Teams practical contract**: pre-dispatch object cognition, Lead/teammate sandbox split, evidence grading, token discipline | Running multi-agent work in DSH |
