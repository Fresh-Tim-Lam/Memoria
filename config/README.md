# config/ — 程序配置目录（开发态 / 发布包通用）

| 文件 | 说明 |
|------|------|
| `ui-settings.json` | 界面设置（开发态位于仓库根目录同级 `config/`，发布态位于 `Package/config/`，便携） |

发布包布局：

```text
Package/
  Memoria.exe
  config/ui-settings.json   ← 程序设置
  lib/
  resources/
```

> `ui-settings.json` 已被 `.gitignore` 忽略（用户本机设置不入库）。
