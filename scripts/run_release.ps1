#Requires -Version 5.1
<#
  发布态：运行已构建的 exe
  先执行：.\scripts\build_release.ps1
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Exe = Join-Path $Root "Package\Memoria.exe"
if (-not (Test-Path $Exe)) {
    Write-Error "未找到发布包，请先运行: .\scripts\build_release.cmd"
}
$ReleaseDir = Split-Path -Parent $Exe
Set-Location $ReleaseDir
$env:MEMORIA_MODE = "release"
$env:MEMORIA_SHELL = "pyqt6"
& $Exe @args
