[中文](README.cn.md) | English

# scripts/ — Developer tools

Home of the **official, reusable** developer tools. Separated from `packaging/` by responsibility: `scripts/` = development tools, `packaging/` = build & release.

## Contents

| File/directory | Purpose |
|----------------|---------|
| `run_dev.ps1` | Dev-mode launch: source + pywebview shell + DevTools + frameless (`MEMORIA_MODE=dev`) |
| `graph_layout_benchmark.py` / `.mjs` | Graph-layout stress benchmark (2D/3D layout + grouping computation) |
| `benchmark/` | Retrieval-evaluation toolset (lexical / embedding / rerank eval batch runs) |
| `bootstrap_example_sidecars.py` | Generate sidecars for the sample knowledge base |
| `gen_example_boonie_sidecars.py` | Generate sidecars for the boonie sample knowledge base |
| `scan_ui_strings.py` | UI copy inventory scanner: refreshes `docs/reference/i18n-inventory.md` (i18n inventory) |
| `i18n_selftest.js` | i18n engine self-test: `node scripts/i18n_selftest.js` (default language / switching / missing-key fallback / parameter filling) |

## Rules

- No temporary/one-off scripts here → `artifacts/`
- Retrieval-evaluation data and results → `benchmarks/`
- Packaging-related scripts → `packaging/`
