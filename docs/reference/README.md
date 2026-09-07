[中文](README.cn.md) | English

# Reference

> **Purpose**: `reference/` holds **reference explanations** — descriptions of the system architecture, terminology, hard constraints, and feature internals, for consultation while understanding and debugging. File names are lowercase kebab-case.
> **Target readers**: Maintainers / AI Agents (consult the relevant reference before understanding the system or troubleshooting).
> **Related docs**: [docs-management.md](../conventions/docs-management.md) (rules for organizing docs); [logging.md](../conventions/logging.md) (logging conventions).

---

## Reference index

| Document | Content |
|------|------|
| [architecture.md](./architecture.md) | System architecture overview (dual shell / static server / frontend modules / data flow) |
| [glossary.md](./glossary.md) | Glossary (KP / sidecar / manifest / contain edges / virtual links, etc.) |
| [hard-constraints.md](./hard-constraints.md) | Hard constraints (established facts that must not be violated) |
| [image-features.md](./image-features.md) | Image feature description and internals (rendering pipeline / path resolution / interaction / static serving) |
| [preview-formats.md](./preview-formats.md) | Preview rendering notes: supported formats and styling (block / inline / extended syntax / styles / interaction / boundaries) |
| [i18n-inventory.md](./i18n-inventory.md) | Registry of UI copy strings (incl. locating Chinese copy; the factual basis for i18n migration and language-pack maintenance; refresh with `python scripts/scan_ui_strings.py`) |
