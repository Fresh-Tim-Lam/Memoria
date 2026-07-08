#Requires -Version 5.1
<#
  开发态：本地试 PyQt6 发布壳（不打包）
  用法：.\scripts\run_dev_pyqt6.ps1
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$env:MEMORIA_MODE = "dev"
$env:MEMORIA_SHELL = "pyqt6"
if (-not $env:MEMORIA_FRAMELESS) { $env:MEMORIA_FRAMELESS = "1" }
python (Join-Path $Root "app_m0.py") @args
