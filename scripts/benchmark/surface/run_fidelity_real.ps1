# run_fidelity_real.ps1 —— 真机 fidelity（run_fidelity.py --cdp）的启停封装（task-32）
#
# 为什么需要外层脚本：`run_fidelity.py --cdp` 只**直连**已运行的应用，不负责启动。
# 本脚本负责：启动真机 → 等 CDP → 调 run_fidelity.py --cdp → 整树清理 → 端口释放确认。
# 只读测量，不改 src/**。
param(
    [string]$Kb = 'tests\probe-kb',
    [string]$Files = 'scale/scale-5k.md',
    [string]$Label = 'real',
    [int]$Port = 9500,
    [int]$BootWaitSec = 18,
    [int]$ReadyTimeout = 60000,
    [switch]$Mutate,
    [string]$MutateKind = 'char'
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$script:AppPid = $null

function Stop-App {
    if ($script:AppPid) {
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try { & taskkill.exe /PID $script:AppPid /T /F *>&1 | Out-Null } catch { }
        $ErrorActionPreference = $prevEap
        $script:AppPid = $null
    }
    Start-Sleep -Milliseconds 600
    $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($c) {
        $ownerProc = Get-CimInstance Win32_Process -Filter "ProcessId=$($c.OwningProcess)" -ErrorAction SilentlyContinue
        $cmd = if ($ownerProc) { [string]$ownerProc.CommandLine } else { '' }
        if ($cmd -like '*memoria.app.desktop*' -or $cmd -like '*\Temp\*EBWebView*') {
            $prevEap = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            try { & taskkill.exe /PID $c.OwningProcess /T /F *>&1 | Out-Null } catch { }
            $ErrorActionPreference = $prevEap
        }
    }
    $orphans = @(Get-CimInstance Win32_Process -Filter "Name='msedgewebview2.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like '*EBWebView*' -and (-not (Get-Process -Id $_.ParentProcessId -ErrorAction SilentlyContinue)) })
    foreach ($o in $orphans) {
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try { & taskkill.exe /PID $o.ProcessId /T /F *>&1 | Out-Null } catch { }
        $ErrorActionPreference = $prevEap
    }
    if ($orphans.Count -gt 0) { Write-Host "[fid-real] swept $($orphans.Count) orphaned WebView2" }
}

try {
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { Stop-App }

    $env:MEMORIA_MODE      = 'dev'
    $env:MEMORIA_FRAMELESS = '0'
    $env:MEMORIA_KB        = (Resolve-Path (Join-Path $RepoRoot $Kb)).Path
    $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = "--remote-debugging-port=$Port"
    Write-Host "[fid-real] KB = $env:MEMORIA_KB (port=$Port, files=$Files)"

    $stdout = Join-Path $env:TEMP "fidreal_app_$Port.out"
    $stderr = Join-Path $env:TEMP "fidreal_app_$Port.err"
    $p = Start-Process -FilePath 'python' -ArgumentList '-m', 'memoria.app.desktop' `
        -WorkingDirectory $RepoRoot -PassThru `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $script:AppPid = $p.Id
    Start-Sleep -Seconds $BootWaitSec

    $ready = $false
    for ($i = 0; $i -lt 15; $i++) {
        $r = & curl.exe -s --max-time 3 "http://127.0.0.1:$Port/json/version" 2>$null
        if ($r -match 'webSocketDebuggerUrl') { $ready = $true; break }
        Start-Sleep -Seconds 2
    }
    if (-not $ready) {
        Get-Content $stderr -Tail 20 -ErrorAction SilentlyContinue
        Throw "[fid-real] CDP 未就绪"
    }
    Write-Host "[fid-real] CDP ready, 调 run_fidelity.py --cdp"

    # run_fidelity.py 自己打印报告；node 超时给足（真机大文档慢）
    $pyArgs = @(
        'scripts\benchmark\surface\run_fidelity.py',
        '--cdp', "http://127.0.0.1:$Port",
        '--kb', $Kb,
        '--files', $Files,
        '--label', $Label,
        '--ready-timeout', "$ReadyTimeout",
        '--timeout', '600'
    )
    if ($Mutate) { $pyArgs += @('--mutate', $MutateKind) }
    Write-Host "[fid-real] python $($pyArgs -join ' ')"
    & python @pyArgs
    Write-Host "[fid-real] python exit=$LASTEXITCODE"
}
finally {
    Stop-App
    Start-Sleep -Milliseconds 800
    $still = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($still) { Write-Warning "[fid-real] 端口 $Port 仍被占用" } else { Write-Host "[fid-real] port $Port free" }
}
