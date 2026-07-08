#Requires -Version 5.1
<#
  一键构建发布包 → 仓库根目录 Package/

  用法：
    .\scripts\build_release.cmd         # 推荐（不受 ExecutionPolicy 限制）
    .\scripts\build_release.ps1         # 若被策略拦截，用 .cmd 或：
      powershell -ExecutionPolicy Bypass -File .\scripts\build_release.ps1
    .\scripts\build_release.ps1 --no-clean

  首次或换环境请先：
    pip install -e ".[desktop]"
    pip install pyinstaller

  构建完成后运行：
    .\scripts\run_release.cmd
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$BuildPy = Join-Path $Root "packaging\build.py"
if (-not (Test-Path $BuildPy)) {
    Write-Error "未找到构建脚本: $BuildPy"
}

Write-Host "==> Memoria 发布包构建（输出: Package\）" -ForegroundColor Cyan
python $BuildPy @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$Exe = Join-Path $Root "Package\Memoria.exe"
if (-not (Test-Path $Exe)) {
    Write-Error "构建结束但未找到: $Exe"
}

Write-Host ""
Write-Host "==> 完成: $Exe" -ForegroundColor Green
Write-Host "    分发整个 Package\ 文件夹即可。"
Write-Host "    本地试运行: .\scripts\run_release.cmd"
