[中文](README.cn.md) | English

# resources/ — Application Assets

> **Purpose**: stores the **non-code static assets** distributed with the app repository (app icons, demo screenshots, etc.), referenced by the app at runtime, by packaging scripts, and by the GitHub showcase; the screenshots also serve as the images for the repository READMEs (English / Chinese).
> **Intended readers**: developers who maintain the icons; people who maintain / add project demo screenshots (README images); packaging-script maintainers.
> **Related docs**: [docs/conventions/readme-i18n.md](../docs/conventions/readme-i18n.md) (conventions for maintaining the bilingual EN/CN README and screenshot descriptions); [docs/conventions/docs-management.md](../docs/conventions/docs-management.md) (docs organization rules); [docs/conventions/directory-organization.md](../docs/conventions/directory-organization.md) (top-level directory responsibilities).

## Contents

| Path | Purpose |
|------|------|
| `icons/` | App icons (`Memoria.ico` / `Memoria-big.ico` / `Memoria.png`), used for the window, the taskbar, and packaged artifacts |
| `screenshots/` | Project demo screenshots (`demo-*.png`) used as images in the READMEs (EN / CN); **not included** in the release package by the packaging script |

## Directory-Change Conventions

- **No** image assets may live under `docs/` (docs holds documents only — binary assets such as screenshots always go under `resources/screenshots/`); if a screenshot-type binary appears under `docs/`, move it into this directory and update the references accordingly.
- After adding / deleting / renaming a screenshot, update in sync: the `README.md` and `README.cn.md` references, this table's description, and the repository document registry (the revision log in docs-management.md).
