param(
    [int]$Port = 9587,
    [string]$KbSource = 'artifacts\agent\verify\todo\ordered-list-fixture\kb',
    [string]$Out = 'artifacts\agent\verify\todo\ordered-list-realapp.json',
    [int]$BootWaitSec = 40
)
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..\..')).Path
Import-Module (Join-Path $RepoRoot 'scripts\benchmark\surface\safe-kill.psm1') -Force -DisableNameChecking
$launcher = Join-Path $RepoRoot 'artifacts\agent\verify\todo\preview-scroll-lost-on-edit-launch.py'
$probe = Join-Path $RepoRoot 'artifacts\agent\verify\todo\ordered-list-realapp-probe.mjs'
$srcKb = (Resolve-Path (Join-Path $RepoRoot $KbSource)).Path
$script:AppPid = $null
$userBefore = @(Get-Process -Name 'Memoria' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
Write-Host "[t157] 用户 Memoria.exe PID（前后必须不变）: $($userBefore -join ',')"
try {
    $work = Join-Path $env:TEMP ("memoria_t157_" + $PID + "_" + (Get-Random))
    New-Item -ItemType Directory -Path $work -Force | Out-Null
    $workKb = Join-Path $work 'kb'; Copy-Item $srcKb $workKb -Recurse -Force
    $cfg = Join-Path $work 'config'; New-Item -ItemType Directory -Path $cfg -Force | Out-Null
    $env:MEMORIA_CONFIG_DIR = $cfg
    Remove-Item Env:\MEMORIA_UI_SETTINGS -ErrorAction SilentlyContinue
    $env:MEMORIA_MODE = 'dev'; $env:MEMORIA_FRAMELESS = '0'; $env:MEMORIA_KB = $workKb
    $env:PYTHONIOENCODING = 'utf-8'
    $busy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($busy) { throw "[t157] 端口 $Port 被占用" }
    $p = Start-Process -FilePath 'python' -ArgumentList $launcher, "$Port" -WorkingDirectory $RepoRoot -PassThru `
        -RedirectStandardOutput (Join-Path $work 'app.out') -RedirectStandardError (Join-Path $work 'app.err')
    $script:AppPid = $p.Id
    Write-Host "[t157] app pid=$($p.Id)，等 CDP ..."
    $ok = $false; $deadline = (Get-Date).AddSeconds($BootWaitSec)
    while ((Get-Date) -lt $deadline) {
        $r = & curl.exe -s --max-time 3 "http://127.0.0.1:$Port/json/version" 2>$null
        if ($r -match 'webSocketDebuggerUrl') { $ok = $true; break }
        Start-Sleep -Milliseconds 800
    }
    if (-not $ok) { Get-Content (Join-Path $work 'app.err') -Tail 25 -ErrorAction SilentlyContinue; throw "[t157] CDP 未就绪" }
    $outAbs = Join-Path $RepoRoot $Out
    & node $probe --cdp "http://127.0.0.1:$Port" --kb $workKb --out $outAbs
    Write-Host "[t157] probe exit=$LASTEXITCODE out=$outAbs workdir=$work"
}
finally {
    if ($script:AppPid) { try { Stop-MeasurementProcess -ProcessId $script:AppPid -ExpectedPort $Port -Quiet | Out-Null } catch { Write-Warning "[t157] stop: $_" } }
    Start-Sleep -Milliseconds 700
    $still = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $still) { Write-Host "[t157] 端口已释放" }
    $userAfter = @(Get-Process -Name 'Memoria' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
    Write-Host "[t157] 用户 Memoria.exe PID（后）: $($userAfter -join ',') / 一致=$((($userBefore -join ',') -eq ($userAfter -join ',')))"
}
