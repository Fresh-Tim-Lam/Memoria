[中文](README.cn.md) | English

# Memoria Packaging Tools (for Developers)

This directory exists **only** to build the Windows release package **from source** — do **not** distribute it to end users together with `Package/`.

## Building (the Only Entry Point)

```powershell
.\packaging\build_release.cmd            # full build (PyInstaller --clean)
.\packaging\build_release.cmd --no-clean # incremental build (skips --clean, builds faster)
```

`.cmd` files are not subject to the PowerShell ExecutionPolicy and are the only supported build entry point.

First time or after switching environments:

```powershell
pip install -e .
pip install pyinstaller
```

## Artifact Location

After a build, the distributable directory is **`Package/`** at the repository root:

```
Package/
  Memoria.exe
  lib/
  resources/
  config/               # ui-settings.json (same directory as the exe; portable)
  VERSION
  manifest.json
  README.txt
```

Just package the entire `Package/` folder (zip / copy) and hand it to the user.

## Bundled-Resource Registry (to Prevent Missing Files)

The release package's `resources/` content is collected centrally by the **`_stage_runtime_resources()` registry** in `packaging/build.py` — it is not an automatic whole-directory copy:

| Registry item (source → in-package) | Nature | Runtime reader |
|---|---|---|
| `resources/icons` → `resources/icons` | Required | Icons |
| `resources/agent-prompts` → `resources/agent-prompts` | **Required** | `get_agent_prompt` (in-app agent-organization prompts; single source of truth) |
| `docs/reference` (whitelist) → `resources/docs` | **Required** | `get_reference_doc` (the "view format guide" popup; single source of truth) |
| `docs/example/showcase` → `resources/examples` | **Required** | Official showcase sample library (Introduction to Machine Learning — open a knowledge base to try it; only bodies / sidecars / images ship with the package; cache and the like are excluded) |

- **Required list**: `_REQUIRED_RELEASE_RESOURCES`; before a build ends, `_verify_release_resources()` self-checks and aborts the build if anything is missing.
- **Iron rule for adding bundled resources (directories / required files)**: ① register them in the `build.py` registry (or the required list) → ② update this table accordingly → ③ update `templates/README.release.txt` if needed → ④ self-check under `Package/resources/` after the build.
- Post-build self-check (no need to fully re-package):

```powershell
python -c "from pathlib import Path; p=Path('Package/resources'); print('agent-prompts:', (p/'agent-prompts'/'organize.zh-CN.md').is_file(), '| docs:', (p/'docs'/'preview-formats.md').is_file(), '| examples:', (p/'examples'/'README.md').is_file(), (p/'examples'/'overview.md').is_file(), '| icons:', (p/'icons'/'Memoria.ico').is_file())"
```

## Running Locally

```powershell
.\packaging\run_release.cmd   # run Package\Memoria.exe (release mode, pywebview shell)
.\scripts\run_dev.ps1         # dev mode (source + pywebview shell + DevTools)
```

## What's in This Directory

```
packaging/
  build_release.cmd         # build entry point (the only one)
  run_release.cmd           # release-mode run entry point
  build.py                  # main build logic (PyInstaller + Package/ layout + manifest)
  app_release.py            # PyInstaller entry point (default pywebview release shell)
  memoria.spec              # PyInstaller config (contents_directory=lib)
  pyi_rth_memoria.py        # runtime hook (taskbar grouping / icon)
  config/                   # environment-variable examples (dev / release)
  templates/                # README template shipped inside the release package
  build/                    # intermediate artifacts (gitignored)
  dist/                     # intermediate artifacts (gitignored)
```

> **Division of responsibilities**: `packaging/` = everything for packaging and releasing (entry scripts + build implementation + config + docs); it does not overlap with `scripts/` (developer tools and research scripts: the dev-mode entry point `run_dev.ps1`, `benchmark/`, etc.).
