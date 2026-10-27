param(
    [int]$AppPort = 9600,
    [string]$OutDir = 'artifacts\agent\verify\todo\preview-panel-images-mermaid'
)
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..\..\..')).Path
Import-Module (Join-Path $RepoRoot 'scripts\benchmark\surface\safe-kill.psm1') -Force -DisableNameChecking
$launcher = Join-Path $RepoRoot 'artifacts\agent\verify\todo\preview-scroll-lost-on-edit-launch.py'
$probe = Join-Path $PSScriptRoot '198-probe.mjs'
$kb = Join-Path $PSScriptRoot 'fixture\kb'
$outAbs = Join-Path $RepoRoot $OutDir
$env:MEMORIA_MODE = 'dev'; $env:MEMORIA_FRAMELESS = '0'; $env:MEMORIA_KB = $kb
$env:PYTHONIOENCODING = 'utf-8'
$work = Join-Path $env:TEMP ('memoria_t198_' + $PID + '_' + (Get-Random))
New-Item -ItemType Directory -Path $work -Force | Out-Null
$env:MEMORIA_CONFIG_DIR = (Join-Path $work 'config')
$env:MEMORIA_DOWNLOAD_DIR = (Join-Path $work 'Downloads')
$p = Start-Process -FilePath 'python' -ArgumentList $launcher, "$AppPort" -WorkingDirectory $RepoRoot -PassThru `
    -RedirectStandardOutput (Join-Path $work 'app.out') -RedirectStandardError (Join-Path $work 'app.err')
Write-Host "[t198] app pid=$($p.Id) port=$AppPort kb=$kb"
try {
    $deadline = (Get-Date).AddSeconds(45)
    while ((Get-Date) -lt $deadline) {
        $r = & curl.exe -s --max-time 3 "http://127.0.0.1:$AppPort/json/version" 2>$null
        if ($r -match 'webSocketDebuggerUrl') { break }
        Start-Sleep -Milliseconds 700
    }
    $json = Join-Path $outAbs 't198-real.json'
    & node $probe --cdp "http://127.0.0.1:$AppPort" --out $json
    $code = $LASTEXITCODE
    Write-Host "[t198] probe exit=$code"
    if ($code -ne 0) {
        Get-Content (Join-Path $work 'app.err') -Tail 30 -ErrorAction SilentlyContinue
        throw "[t198] probe failed"
    }
}
finally {
    try { Stop-MeasurementProcess -ProcessId $p.Id -ExpectedPort $AppPort -Quiet | Out-Null } catch { }
    Start-Sleep -Milliseconds 500
    $still = Get-NetTCPConnection -LocalPort $AppPort -State Listen -ErrorAction SilentlyContinue
    Write-Host "[t198] port released=$(-not $still) work=$work"
}
