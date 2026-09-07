[中文](README.cn.md) | English

# Prompts

> **Purpose**: Reusable prompt templates (knowledge organization, import, etc.), ready for users to copy and use directly.
> **Target readers**: Users (copy and use); AI Agents (follow this directory's conventions when adding templates).
> **Related docs**: [docs-management.md](../conventions/docs-management.md) (rules for organizing docs).

## Template index

| File | Purpose |
|------|------|
| [role-a-content-agent.md](role-a-content-agent.md) | Complete manual for Role A (content generation Agent): task prompt + flat-file format conventions + organization/batching rules + output format + self-check checklist and conflict handling. Replaces the former knowledge-organizer-prompt.md |

## Conventions

- Adding a template: name it in kebab-case, include the three header elements "Purpose / Target readers / Related docs", and register one row in the index above
- If a template contains normative constraints (e.g., import format), update the corresponding `conventions/` document first, then sync the template, to avoid drift between the two sources
