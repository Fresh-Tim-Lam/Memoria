# run_ready_selfcheck.ps1 —— 渲染就绪判定自证的真机启停（task-31）
#
# 复用 run_signature_selfcheck.ps1 的启停/整树清理纪律。
# 只读测量，不改 src/**。
param(
    [string]$Kb = 'tests\probe-kb',
    [string]$File = 'scale/scale-5k.md',
    [int]$Port = 9501,
    [int]$BootWaitSec = 18,
    [string]$Out = ''
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
    # !! 只杀 user-data-dir 在 Temp 的孤儿（=本次启动的），且**等它真正退出**。
    #    踩过：taskkill 返回后进程仍监听端口（WebView2 子进程延迟退出）=> 下次启动抢不到端口。
    $orphans = @(Get-CimInstance Win32_Process -Filter "Name='msedgewebview2.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -like '*EBWebView*' -and $_.CommandLine -like '*\Temp\*' -and
            (-not (Get-Process -Id $_.ParentProcessId -ErrorAction SilentlyContinue))
        })
    foreach ($o in $orphans) {
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try { & taskkill.exe /PID $o.ProcessId /T /F *>&1 | Out-Null } catch { }
        $ErrorActionPreference = $prevEap
    }
    # 等待孤儿真正退出（最多 ~5s），避免端口残留
    foreach ($o in $orphans) {
        for ($w = 0; $w -lt 10; $w++) {
            if (-not (Get-Process -Id $o.ProcessId -ErrorAction SilentlyContinue)) { break }
            Start-Sleep -Milliseconds 500
        }
    }
    if ($orphans.Count -gt 0) { Write-Host "[cleanup] swept $($orphans.Count) orphaned WebView2" }
}

try {
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { Stop-App }

    $env:MEMORIA_MODE      = 'dev'
    $env:MEMORIA_FRAMELESS = '0'
    $env:MEMORIA_KB        = (Resolve-Path (Join-Path $RepoRoot $Kb)).Path
    $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = "--remote-debugging-port=$Port"
    Write-Host "[readycheck] KB = $env:MEMORIA_KB (port=$Port, file=$File)"

    $stdout = Join-Path $env:TEMP "readycheck_app_$Port.out"
    $stderr = Join-Path $env:TEMP "readycheck_app_$Port.err"
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
        Throw "[readycheck] CDP 未就绪"
    }
    Write-Host "[readycheck] CDP ready"

    if (-not $Out) {
        $sha = (& git -C $RepoRoot rev-parse --short HEAD).Trim()
        $Out = "scripts\benchmark\surface\results\ready-selfcheck_$sha.json"
    }
    $absOut = Join-Path $RepoRoot $Out
    $nodeArgs = @(
        (Join-Path $PSScriptRoot 'verify_ready_detector.mjs'),
        '--cdp', "http://127.0.0.1:$Port",
        '--file', $File,
        '--out', $absOut
    )
    Write-Host "[readycheck] measure: node $($nodeArgs -join ' ')"
    & node @nodeArgs
    Write-Host "[readycheck] node exit=$LASTEXITCODE -> $absOut"
}
finally {
    Stop-App
    Start-Sleep -Milliseconds 800
    $still = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($still) { Write-Warning "[readycheck] 端口 $Port 仍被占用" } else { Write-Host "[readycheck] port $Port free" }
}
