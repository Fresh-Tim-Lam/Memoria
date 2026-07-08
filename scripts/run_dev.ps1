#Requires -Version 5.1
<#
  开发态：pywebview 壳（默认）
  用法：.\scripts\run_dev.ps1
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$env:MEMORIA_MODE = "dev"
$env:MEMORIA_SHELL = "pywebview"
if (-not $env:MEMORIA_FRAMELESS) { $env:MEMORIA_FRAMELESS = "1" }
if (-not $env:MEMORIA_DEBUG) { $env:MEMORIA_DEBUG = "1" }
python (Join-Path $Root "app_m0.py") @args
