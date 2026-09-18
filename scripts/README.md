[中文](README.cn.md) | English

# scripts/ — Developer tools

Home of the **official, reusable** developer tools. Separated from `packaging/` by responsibility: `scripts/` = development tools, `packaging/` = build & release.

## Contents

| File/directory | Purpose |
|----------------|---------|
| `run_dev.ps1` | Dev-mode launch: source + pywebview shell + DevTools + frameless (`MEMORIA_MODE=dev`) |
| `graph_layout_benchmark.py` / `.mjs` | Graph-layout stress benchmark (2D/3D layout + grouping computation) |
| `benchmark/` | Retrieval-evaluation toolset (lexical / embedding / rerank eval batch runs) |
| `benchmark/usage/` | Agent token-usage report: aggregates session `loop/end.usage` into JSON + Markdown, read-only (`report_usage.py`, cn-only README) |
| `screenshots/` | Screenshot capture for README / docs: hotkey-triggered client-area grab with duplicate-frame detection |
| `bootstrap_example_sidecars.py` | Generate sidecars for the sample knowledge base |
| `gen_example_boonie_sidecars.py` | Generate sidecars for the boonie sample knowledge base |
| `scan_ui_strings.py` | UI copy inventory scanner: refreshes `docs/reference/i18n-inventory.md` (i18n inventory) |
| `i18n_selftest.js` | i18n engine self-test: `node scripts/i18n_selftest.js` (default language / switching / missing-key fallback / parameter filling) |
| `agent_llm_smoke.py` | Agent LLM smoke tool (dsh port, M1): streams one answer from the configured remote endpoint and prints usage. `--mock` runs a built-in fake SSE endpoint so it works offline. Config via `MEMORIA_AGENT_BASE_URL` / `MEMORIA_AGENT_API_KEY` / `MEMORIA_AGENT_MODEL` (key never printed) |
| `agent_ask.py` | Agent end-to-end ask tool (dsh port, M1): `--kb <path> "<question>"` runs the read-only agent loop (search / read / overview / validate tools) and prints the answer with `file:line` anchors, usage and the session file. `--mock` uses a scripted offline provider (no network). Never writes the knowledge base except `<kb>/.memoria/agent/sessions/*.jsonl` |

## Rules

- No temporary/one-off scripts here → `artifacts/`
- Retrieval-evaluation data and results → `benchmarks/`
- Packaging-related scripts → `packaging/`
