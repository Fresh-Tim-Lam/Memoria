#Requires -Version 5.1
<#
  构建发布包 → 仓库根目录 Package/（可整夹分发给用户）
  依赖：pip install -e ".[desktop]" ; pip install pyinstaller
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
python (Join-Path $PSScriptRoot "build.py") @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
