# source-cut-run.ps1 —— task-150 真机取证运行器（**只写临时 KB 副本**；不改用户 KB、不 commit）
param(
    [int]$Port = 9585,
    [string]$KbSource = 'artifacts\agent\verify\todo\source-cut-fixture\kb',
    [string]$Out = 'artifacts\agent\verify\todo\source-cut-realapp.json',
    [int]$BootWaitSec = 40,
    [switch]$FixMode = $false
)
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..\..')).Path
Import-Module (Join-Path $RepoRoot 'scripts\benchmark\surface\safe-kill.psm1') -Force -DisableNameChecking
$launcher = Join-Path $RepoRoot 'artifacts\agent\verify\todo\preview-scroll-lost-on-edit-launch.py'
$probe = Join-Path $RepoRoot 'artifacts\agent\verify\todo\source-cut-probe.mjs'
$cliphelper = Join-Path $RepoRoot 'artifacts\agent\verify\todo\source-cut-clipboard.ps1'
$srcKb = (Resolve-Path (Join-Path $RepoRoot $KbSource)).Path
$script:AppPid = $null
$userBefore = @(Get-Process -Name 'Memoria' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
Write-Host "[t150] 用户 Memoria.exe PID（前后必须不变）: $($userBefore -join ',')"
try {
    if (-not (Test-Path $srcKb)) { throw "[t150] 夹具 KB 不存在，请先跑 source-cut-fixture-gen.py: $srcKb" }
    $work = Join-Path $env:TEMP ("memoria_t150_" + $PID + "_" + (Get-Random))
    New-Item -ItemType Directory -Path $work -Force | Out-Null
    $workKb = Join-Path $work 'kb'; Copy-Item $srcKb $workKb -Recurse -Force
    $cfg = Join-Path $work 'config'; New-Item -ItemType Directory -Path $cfg -Force | Out-Null
    $env:MEMORIA_CONFIG_DIR = $cfg
    Remove-Item Env:\MEMORIA_UI_SETTINGS -ErrorAction SilentlyContinue
    $env:MEMORIA_MODE = 'dev'; $env:MEMORIA_FRAMELESS = '0'; $env:MEMORIA_KB = $workKb
    $env:PYTHONIOENCODING = 'utf-8'
    $busy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($busy) { throw "[t150] 端口 $Port 被占用（pid $($busy.OwningProcess)），换端口" }
    $p = Start-Process -FilePath 'python' -ArgumentList $launcher, "$Port" -WorkingDirectory $RepoRoot -PassThru `
        -RedirectStandardOutput (Join-Path $work 'app.out') -RedirectStandardError (Join-Path $work 'app.err')
    $script:AppPid = $p.Id
    Write-Host "[t150] app pid=$($p.Id)，等 CDP（最多 ${BootWaitSec}s）..."
    $ok = $false
    $deadline = (Get-Date).AddSeconds($BootWaitSec)
    while ((Get-Date) -lt $deadline) {
        $r = & curl.exe -s --max-time 3 "http://127.0.0.1:$Port/json/version" 2>$null
        if ($r -match 'webSocketDebuggerUrl') { $ok = $true; break }
        Start-Sleep -Milliseconds 800
    }
    if (-not $ok) { Get-Content (Join-Path $work 'app.err') -Tail 25 -ErrorAction SilentlyContinue; throw "[t150] CDP 未就绪" }
    Write-Host "[t150] CDP ready；KB(副本)=$workKb"
    $outAbs = Join-Path $RepoRoot $Out
    $probeArgs = @($probe, '--cdp', "http://127.0.0.1:$Port", '--kb', $workKb, '--cliphelper', $cliphelper, '--out', $outAbs)
    if ($FixMode) { $probeArgs += '--fix-mode' }
    & node @probeArgs
    $code = $LASTEXITCODE
    Write-Host "[t150] probe exit=$code out=$outAbs"
    Write-Host "[t150] workdir(保留供诊断)=$work"
    # 探针"失败"是取证结果（改前红矩阵），不当作运行器错误；退出码原样透传
    exit $code
}
finally {
    if ($script:AppPid) { try { Stop-MeasurementProcess -ProcessId $script:AppPid -ExpectedPort $Port -Quiet | Out-Null } catch { Write-Warning "[t150] stop: $_" } }
    Start-Sleep -Milliseconds 700
    $still = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($still) { Write-Warning "[t150] 端口 $Port 仍被占用（pid $($still.OwningProcess)）——不杀" } else { Write-Host "[t150] 端口已释放" }
    $userAfter = @(Get-Process -Name 'Memoria' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
    Write-Host "[t150] 用户 Memoria.exe PID（后）: $($userAfter -join ',') / 一致=$((($userBefore -join ',') -eq ($userAfter -join ',')))"
}
