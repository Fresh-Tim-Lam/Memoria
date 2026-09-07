[中文](README.cn.md) | English

# Conventions

> **Purpose**: `conventions/` holds **binding conventions** — rules that both humans and machines must follow (syntax, formatting, directory layout, versioning, logging, documentation management, meta-rules). File names are lowercase kebab-case.
> **Target readers**: Project owner (the user) and AI Agents (consult the relevant convention before creating or modifying code or documentation).
> **Related docs**: [meta-rules.md](./meta-rules.md) (meta-rules for writing conventions); [docs-management.md](./docs-management.md) (rules for organizing docs).

---

## Conventions index

| Convention | Content | Who must follow |
|------|------|---------|
| [meta-rules.md](./meta-rules.md) | Meta-rules for how to discuss and author conventions | All convention authors |
| [docs-management.md](./docs-management.md) | Rules for organizing docs/ (subdirectory responsibilities, registration, lifecycle) | Everyone (including AI Agents) |
| [directory-organization.md](./directory-organization.md) | Top-level directory responsibilities and placement of temporary files | Everyone (including AI Agents) |
| [version.md](./version.md) | Version number format, single source of truth, upgrade process | Anyone involved in version changes/packaging |
| [markdown-form-std.md](./markdown-form-std.md) | Unified `[[]]` syntax system (incl. image node attributes) | Knowledge-base content producers |
| [import-format.md](./import-format.md) | Flat-file import format for the knowledge base | Content generation Agent (Role A) |
| [context-key.md](./context-key.md) | CTX-KEY context firewall mechanism | Project owner and AI Agents |
| [logging.md](./logging.md) | Log storage/naming/format/lifecycle | Anyone adding or debugging logs |
| [refs-system.md](./refs-system.md) | Usage rules for the reference library (refs/) | Anyone citing technical references |
| [i18n.md](./i18n.md) | Language-system maintenance rules (copy key extraction / language-pack structure and fallback / onboarding new UI / inventory maintenance) | Anyone adding or modifying UI copy |
| [readme-i18n.md](./readme-i18n.md) | Bilingual (Chinese/English) maintenance rules for READMEs and project screenshots (README.md ↔ README.cn.md sync, screenshot curation/storage, self-checks) | Anyone maintaining a README or adding/replacing demo screenshots |

> **Decision flow**: content that is a "rule everyone, human or machine, must follow" → put it in this directory; an operational how-to guide → `guides/`; a reference explanation → `reference/`. See [docs-management.md](./docs-management.md) for details.
