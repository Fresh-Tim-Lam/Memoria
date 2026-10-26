param(
    [int]$Port = 9597,
    [string]$Out = 'artifacts\agent\verify\todo\contentmin-def-A.json',
    [string]$Label = 'A',
    [int]$BootWaitSec = 40
)
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..\..')).Path
Import-Module (Join-Path $RepoRoot 'scripts\benchmark\surface\safe-kill.psm1') -Force -DisableNameChecking
$launcher = Join-Path $RepoRoot 'artifacts\agent\verify\todo\preview-scroll-lost-on-edit-launch.py'
$probe = Join-Path $RepoRoot 'artifacts\agent\verify\todo\contentmin-def-probe.mjs'
$srcKb = (Resolve-Path (Join-Path $RepoRoot 'artifacts\agent\verify\todo\link-popover-fixture\kb')).Path
$script:AppPid = $null
$userBefore = @(Get-Process -Name 'Memoria' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
Write-Host "[t170] user Memoria PID: $($userBefore -join ',') repo=$RepoRoot"
try {
    $work = Join-Path $env:TEMP ("memoria_t170_" + $PID + "_" + (Get-Random))
    New-Item -ItemType Directory -Path $work -Force | Out-Null
    $workKb = Join-Path $work 'kb'; Copy-Item $srcKb $workKb -Recurse -Force
    $cfg = Join-Path $work 'config'; New-Item -ItemType Directory -Path $cfg -Force | Out-Null
    $env:MEMORIA_CONFIG_DIR = $cfg
    Remove-Item Env:\MEMORIA_UI_SETTINGS -ErrorAction SilentlyContinue
    $env:MEMORIA_MODE = 'dev'; $env:MEMORIA_FRAMELESS = '0'; $env:MEMORIA_KB = $workKb
    $env:PYTHONIOENCODING = 'utf-8'
    $env:PYTHONPATH = (Join-Path $RepoRoot 'src')
    $busy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($busy) { throw "[t170] port $Port busy" }
    $p = Start-Process -FilePath 'python' -ArgumentList $launcher, "$Port" -WorkingDirectory $RepoRoot -PassThru `
        -RedirectStandardOutput (Join-Path $work 'app.out') -RedirectStandardError (Join-Path $work 'app.err')
    $script:AppPid = $p.Id
    Write-Host "[t170] app pid=$($p.Id), wait CDP ..."
    $ok = $false; $deadline = (Get-Date).AddSeconds($BootWaitSec)
    while ((Get-Date) -lt $deadline) {
        $r = & curl.exe -s --max-time 3 "http://127.0.0.1:$Port/json/version" 2>$null
        if ($r -match 'webSocketDebuggerUrl') { $ok = $true; break }
        Start-Sleep -Milliseconds 800
    }
    if (-not $ok) { Get-Content (Join-Path $work 'app.err') -Tail 25 -ErrorAction SilentlyContinue; throw "[t170] CDP not ready" }
    $outAbs = Join-Path $RepoRoot $Out
    & node $probe --cdp "http://127.0.0.1:$Port" --out $outAbs --label $Label
    Write-Host "[t170] probe exit=$LASTEXITCODE out=$outAbs work=$work"
}
finally {
    if ($script:AppPid) { try { Stop-MeasurementProcess -ProcessId $script:AppPid -ExpectedPort $Port -Quiet | Out-Null } catch { Write-Warning "[t170] stop: $_" } }
    Start-Sleep -Milliseconds 700
    $still = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $still) { Write-Host "[t170] port released" }
    $userAfter = @(Get-Process -Name 'Memoria' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
    Write-Host "[t170] user Memoria PID after: $($userAfter -join ',') same=$((($userBefore -join ',') -eq ($userAfter -join ',')))"
}
