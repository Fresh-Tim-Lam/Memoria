param(
    [int]$AppPort = 9600,
    [int]$OfflineAppPort = 9601,
    [string]$OutDir = 'artifacts\agent\verify\update-mechanism'
)
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..\..')).Path
Import-Module (Join-Path $RepoRoot 'scripts\benchmark\surface\safe-kill.psm1') -Force -DisableNameChecking
$launcher = Join-Path $RepoRoot 'artifacts\agent\verify\todo\preview-scroll-lost-on-edit-launch.py'
$probe = Join-Path $RepoRoot 'artifacts\agent\verify\update-mechanism\update-e2e-probe.mjs'
$mock = Join-Path $RepoRoot 'artifacts\agent\verify\update-mechanism\mock_update_server.py'
$payload = Join-Path $RepoRoot 'artifacts\agent\verify\update-mechanism\payload'
$srcKb = (Resolve-Path (Join-Path $RepoRoot 'artifacts\agent\verify\todo\link-popover-fixture\kb')).Path
$outAbs = Join-Path $RepoRoot $OutDir
New-Item -ItemType Directory -Path $outAbs -Force | Out-Null
$script:MockPid = $null; $script:AppPid = $null
$userBefore = @(Get-Process -Name 'Memoria' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
Write-Host "[t180] user Memoria PID before: $($userBefore -join ',') repo=$RepoRoot"

function Wait-CDP([int]$Port, [int]$Sec) {
    $deadline = (Get-Date).AddSeconds($Sec)
    while ((Get-Date) -lt $deadline) {
        $r = & curl.exe -s --max-time 3 "http://127.0.0.1:$Port/json/version" 2>$null
        if ($r -match 'webSocketDebuggerUrl') { return $true }
        Start-Sleep -Milliseconds 700
    }
    return $false
}

function Run-App([string]$Tag, [int]$Port, [bool]$Offline, [string]$RequestLog) {
    $work = Join-Path $env:TEMP ("memoria_t180_" + $Tag + "_" + $PID + "_" + (Get-Random))
    New-Item -ItemType Directory -Path $work -Force | Out-Null
    $kb = Join-Path $work 'kb'; Copy-Item $srcKb $kb -Recurse -Force
    $cfg = Join-Path $work 'config'; New-Item -ItemType Directory -Path $cfg -Force | Out-Null
    $env:MEMORIA_CONFIG_DIR = $cfg
    $env:MEMORIA_DOWNLOAD_DIR = (Join-Path $work 'Downloads')
    Remove-Item Env:\MEMORIA_UI_SETTINGS -ErrorAction SilentlyContinue
    $env:MEMORIA_MODE = 'dev'; $env:MEMORIA_FRAMELESS = '0'; $env:MEMORIA_KB = $kb
    $env:PYTHONIOENCODING = 'utf-8'
    if ($Offline) {
        # 「出网」开关：agent.json enabled=false；更新页应显示关闭且零请求
        $agentCfg = Join-Path $cfg 'agent.json'
        Set-Content -Path $agentCfg -Value '{"enabled": false}' -Encoding utf8
    }
    $env:MEMORIA_UPDATE_API_URL = "http://127.0.0.1:$($script:MockPort)/latest"
    $env:MEMORIA_UPDATE_ALLOWED_HOSTS = '127.0.0.1'
    $busy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($busy) { throw "[t180] port $Port busy" }
    $p = Start-Process -FilePath 'python' -ArgumentList $launcher, "$Port" -WorkingDirectory $RepoRoot -PassThru `
        -RedirectStandardOutput (Join-Path $work 'app.out') -RedirectStandardError (Join-Path $work 'app.err')
    $script:AppPid = $p.Id
    Write-Host "[t180] $Tag app pid=$($p.Id) port=$Port config=$cfg"
    if (-not (Wait-CDP $Port 45)) {
        Get-Content (Join-Path $work 'app.err') -Tail 30 -ErrorAction SilentlyContinue
        throw "[t180] CDP not ready ($Tag)"
    }
    $json = Join-Path $outAbs ("update-e2e-" + $Tag + ".json")
    $offArg = @()
    if ($Offline) { $offArg = @('--offline') }
    $downArg = @('--downloads', (Join-Path $work 'Downloads'))
    & node $probe --cdp "http://127.0.0.1:$Port" --out $json --requests $RequestLog --downloads (Join-Path $work 'Downloads') @offArg
    $code = $LASTEXITCODE
    Write-Host "[t180] $Tag probe exit=$code out=$json work=$work"
    try { Stop-MeasurementProcess -ProcessId $script:AppPid -ExpectedPort $Port -Quiet | Out-Null } catch { Write-Warning "[t180] stop app: $_" }
    Start-Sleep -Milliseconds 700
    if ($code -ne 0) { throw "[t180] probe failed ($Tag) exit=$code" }
}

try {
    $mockLog = Join-Path $env:TEMP ("memoria_t180_requests_" + $PID + ".jsonl")
    $portFile = Join-Path $env:TEMP ("memoria_t180_port_" + $PID + ".txt")
    Remove-Item $portFile -ErrorAction SilentlyContinue
    $mockProc = Start-Process -FilePath 'python' -ArgumentList $mock, '--port-file', $portFile, '--log', $mockLog, '--payload-dir', $payload, '--chunk-delay', '0.02' -PassThru `
        -RedirectStandardOutput (Join-Path $env:TEMP ("memoria_t180_mock_" + $PID + '.out')) `
        -RedirectStandardError (Join-Path $env:TEMP ("memoria_t180_mock_" + $PID + '.err'))
    $script:MockPid = $mockProc.Id
    $deadline = (Get-Date).AddSeconds(15)
    while ((Get-Date) -lt $deadline -and -not (Test-Path $portFile)) { Start-Sleep -Milliseconds 200 }
    if (-not (Test-Path $portFile)) { throw "[t180] mock server did not start" }
    $script:MockPort = (Get-Content $portFile -Raw).Trim()
    Write-Host "[t180] mock server port=$($script:MockPort) log=$mockLog"

    # ① 正常联网：检查 + full 取消 + lite 下载 + 说明 + 隐私日志 + 延迟自动检查
    Run-App 'normal' $AppPort $false $mockLog
    # ② 出网关闭：零请求
    $offlineLog = Join-Path $env:TEMP ("memoria_t180_offline_requests_" + $PID + ".jsonl")
    # mock 日志重置为新的独立文件：为独立证据，另起一个服务实例
    $mockLog2 = Join-Path $env:TEMP ("memoria_t180_requests_offline_" + $PID + ".jsonl")
    $portFile2 = Join-Path $env:TEMP ("memoria_t180_port_offline_" + $PID + ".txt")
    Remove-Item $portFile2 -ErrorAction SilentlyContinue
    $mockProc2 = Start-Process -FilePath 'python' -ArgumentList $mock, '--port-file', $portFile2, '--log', $mockLog2, '--payload-dir', $payload -PassThru `
        -RedirectStandardOutput (Join-Path $env:TEMP ("memoria_t180_mock2_" + $PID + '.out')) `
        -RedirectStandardError (Join-Path $env:TEMP ("memoria_t180_mock2_" + $PID + '.err'))
    $deadline = (Get-Date).AddSeconds(15)
    while ((Get-Date) -lt $deadline -and -not (Test-Path $portFile2)) { Start-Sleep -Milliseconds 200 }
    $script:MockPort = (Get-Content $portFile2 -Raw).Trim()
    Write-Host "[t180] offline mock port=$($script:MockPort) log=$mockLog2"
    $script:MockPid2 = $mockProc2.Id
    try {
        Run-App 'offline' $OfflineAppPort $true $mockLog2
    } finally {
        try { Stop-Process -Id $mockProc2.Id -Force -ErrorAction SilentlyContinue } catch { }
    }
    Write-Host "[t180] done"
}
finally {
    if ($script:AppPid) { try { Stop-MeasurementProcess -ProcessId $script:AppPid -ExpectedPort $AppPort -Quiet | Out-Null } catch { } }
    if ($script:MockPid) { try { Stop-Process -Id $script:MockPid -Force -ErrorAction SilentlyContinue } catch { } }
    if ($script:MockPid2) { try { Stop-Process -Id $script:MockPid2 -Force -ErrorAction SilentlyContinue } catch { } }
    Start-Sleep -Milliseconds 700
    $ports = @($AppPort, $OfflineAppPort)
    foreach ($p in $ports) {
        $still = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
        if (-not $still) { Write-Host "[t180] port $p released" }
    }
    $userAfter = @(Get-Process -Name 'Memoria' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
    Write-Host "[t180] user Memoria PID after: $($userAfter -join ',') same=$((($userBefore -join ',') -eq ($userAfter -join ',')))"
}
