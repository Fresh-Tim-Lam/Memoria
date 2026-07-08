# Memoria 打包工具（开发者用）

此目录仅用于**从源码构建** Windows 发布包，**不要**随 `Package/` 一起分发给最终用户。

## 构建

```powershell
.\scripts\build_release.cmd
```

PowerShell 若提示 ExecutionPolicy 拦截，请用 `.cmd`（上式），勿改系统策略。

或：`.\scripts\build_release.ps1` / `.\packaging\build.ps1` / `memoria-build`

首次或换环境：

```powershell
pip install -e ".[desktop]"
pip install pyinstaller
```

## 产物位置

构建完成后，可分发目录为仓库根目录的 **`Package/`**：

```
Package/
  Memoria.exe
  lib/
  resources/
  config/               # ui-settings.json（与 exe 同目录，便携）
  VERSION
  manifest.json
  README.txt
```

将整个 `Package/` 文件夹打包（zip/拷贝）给用户即可。

## 本目录说明

```
packaging/
  build.ps1
  build.py
  app_release.py          # PyInstaller 入口
  memoria.spec            # PyInstaller 配置
  pyi_rth_memoria_qtwebengine.py
  templates/
  config/                 # 环境变量示例
  build/                  # 中间产物（gitignore）
  dist/                   # 中间产物（gitignore）
```
