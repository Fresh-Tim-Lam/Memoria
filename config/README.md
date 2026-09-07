[中文](README.cn.md) | English

# config/ — Program configuration directory (shared by dev mode / release package)

| File | Description |
|------|-------------|
| `ui-settings.json` | UI settings (in dev mode located in `config/` next to the repo root; in release mode in `Package/config/`, portable) |

Release package layout:

```text
Package/
  Memoria.exe
  config/ui-settings.json   ← program settings
  lib/
  resources/
```

> `ui-settings.json` is ignored by `.gitignore` (per-user local settings are not committed).
