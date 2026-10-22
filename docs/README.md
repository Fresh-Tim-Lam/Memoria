[中文](README.cn.md) | English

# Memoria Documentation Center

> **Purpose**: the entry-point index of `docs/` — lists the responsibility of every subdirectory and its key documents, so that humans and agents can locate things quickly.
> **Intended readers**: project owner (the user) and AI Agents (read this page first before entering docs).
> **Related docs**: [conventions/docs-management.md](conventions/docs-management.md) (docs organization rules, including the directory registry table).

---

## Subdirectory Navigation

| Directory | Responsibility | Entry / Key documents |
|------|------|--------------|
| `conventions/` | Contractual conventions (rules that both humans and agents must follow) | [README.md](conventions/README.md) (list of conventions) |
| `guides/` | How-to guides (how to do something) | [README.md](guides/README.md) |
| `reference/` | Reference material (understanding: architecture, terminology, hard constraints, feature mechanisms) | [README.md](reference/README.md) |
| `design/` | Design documents and decision records | system-design.md, dicussion.md, designV0.md, etc.; 台账归档明细：[agent-panel-batches.md](design/agent-panel-batches.md)；长期计划/自动作业优先级：[longterm-plan-2026-10.md](design/longterm-plan-2026-10.md)；Agent 技能约定：[agent-skills.md](design/agent-skills.md)；导出 HTML 草案：[export-html-draft.md](design/export-html-draft.md)（§13 叙述原文存档）、[ledger-archive-2026.md](design/ledger-archive-2026.md)（§10 归档明细）、[editor-input-defects-2026-10.md](design/editor-input-defects-2026-10.md)（§5.1 缺陷详情）、[packaging-release.md](design/packaging-release.md)（§8 P04/P06 详情）、[maintenance-jobs-archive-2026-10.md](design/maintenance-jobs-archive-2026-10.md)（§5 作业明细） |
| `sessions/` | Records of past conversations (carry context forward; formerly `agents/`) | Per-session documents |
| `example/` | Container for example knowledge bases: `showcase/` (official showcase, kept in repo) and `import-test/` (fixtures, kept in repo); other local samples and personal libraries stay local only |  |
| `refs/` | Development reference materials | [README.md](refs/README.md) |
| `prompts/` | Prompt templates | [README.md](prompts/README.md) |
| `tmp/` | A small number of diagnostic / debugging records | Debug session records |

## How to Choose Among the Three Main Directory Types

| Content type | Goes into | Typical examples |
|---------|------|---------|
| Contracts / rules (both humans and agents must follow) | `conventions/` | versioning, syntax, import format, logging, directory organization, docs management |
| How-to guides (how to do something) | `guides/` | knowledge-base production pipeline, AI coding collaboration |
| Reference material (understanding: what it is / why) | `reference/` | system architecture, glossary, hard constraints, image feature mechanism |

For the detailed decision process, see [conventions/docs-management.md](conventions/docs-management.md#2-子目录职责与决策表).

## Root Rules

Only the following files are allowed at the `docs/` root:
- `README.md` (this page, master index)
- `todo.md` (active work list / todo)

All other documents must go into one of the subdirectories in the table above; a new subdirectory must be registered in the directory registry table of [conventions/docs-management.md](conventions/docs-management.md#4-自维护机制).

## Quick Navigation (by Task)

| I want to… | Look here |
|-------|--------|
| Check the current version / bump the version | [conventions/version.md](conventions/version.md) |
| Decide where a file goes | [conventions/directory-organization.md](conventions/directory-organization.md) |
| Add a new docs subdirectory | [conventions/docs-management.md](conventions/docs-management.md#4-自维护机制) |
| Understand the system architecture | [reference/architecture.md](reference/architecture.md), [design/system-design.md](design/system-design.md) |
| Learn about the `[[]]` syntax | [conventions/markdown-form-std.md](conventions/markdown-form-std.md) |
| Have an Agent produce / convert knowledge bases | [guides/usage-agent-workflow.md](guides/usage-agent-workflow.md) |
| Onboard a new AI / hand over | all of `reference/` + [guides/README.md](guides/README.md) + [conventions/README.md](conventions/README.md) |
| Find past conversations | `sessions/` |
