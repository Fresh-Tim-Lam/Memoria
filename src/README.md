[中文](README.cn.md) | English

# src/ — Memoria source code

> src layout: Python package + frontend static assets, imported as the `memoria` package after installation.

## Structure

| Path | Responsibility |
|------|----------------|
| `memoria/app/` | Desktop startup entry: `desktop.py` (DPI/UTF-8 fallbacks), `shell/` (pywebview / pyqt6 shells), `build.py`, `runtime.py` |
| `memoria/cli/` | Command-line entry (`memoria`) |
| `memoria/domain/` | Domain types (Range, KP, etc.) |
| `memoria/range/` | snippet + line_hint location algorithms |
| `memoria/graph/` | Graph building, edge derivation, link audit, layout benchmarks |
| `memoria/presentation/` | pywebview API bridge (`api/`), path resolution, bottle static server |
| `memoria/services/` | Application services: document loading, retrieval kernel (lexical/embedding/rerank fusion), import engine, KP index |
| `memoria/storage/` | Sidecar YAML, manifest, Markdown parsing, directory scanning, atomic writes |
| `memoria/ui/static/` | Frontend assets: `app/` (UI HTML/CSS/JS), `theme/` (memoria.css), `vendor/` (third-party like MathJax) |
| `memoria/__version__.py` | Single source of truth for the version |

## Rules

- No temporary/debug files in `src/` → put them in `artifacts/`
- The version number may only be changed in `__version__.py`; **do not** hand-edit the hardcoded version in pyproject.toml (see [docs/conventions/version.md](../docs/conventions/version.md))
- Frontend keeps the vanilla-JS, no-framework style
