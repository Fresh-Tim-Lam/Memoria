# run_signature_selfcheck.ps1 —— 签名归一化 + 判等机制自证（task-28）
#
# 复用 run_realapp_coverage.ps1 的启停/整树清理做法。
# 只读测量，不改 src/**。
param(
    [string]$Kb = 'docs\example\行政法',
    [string]$Files = 'corpus/04-non-editable.md',
    [int]$Port = 9500,
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
}

try {
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { Stop-App }

    $env:MEMORIA_MODE      = 'dev'
    $env:MEMORIA_FRAMELESS = '0'
    $env:MEMORIA_KB        = (Resolve-Path (Join-Path $RepoRoot $Kb)).Path
    $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = "--remote-debugging-port=$Port"
    Write-Host "[sigcheck] KB = $env:MEMORIA_KB (port=$Port)"

    $stdout = Join-Path $env:TEMP "sigcheck_app_$Port.out"
    $stderr = Join-Path $env:TEMP "sigcheck_app_$Port.err"
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
        Throw "[sigcheck] CDP 未就绪"
    }
    Write-Host "[sigcheck] CDP ready"

    if (-not $Out) {
        $sha = (& git -C $RepoRoot rev-parse --short HEAD).Trim()
        $Out = "scripts\benchmark\surface\results\signature-selfcheck_$sha.json"
    }
    $absOut = Join-Path $RepoRoot $Out
    $nodeArgs = @(
        (Join-Path $PSScriptRoot 'verify_signature_normalization.mjs'),
        '--cdp', "http://127.0.0.1:$Port",
        '--files', $Files,
        '--out', $absOut
    )
    Write-Host "[sigcheck] measure: node $($nodeArgs -join ' ')"
    & node @nodeArgs
    Write-Host "[sigcheck] node exit=$LASTEXITCODE, out=$absOut"
}
finally {
    Stop-App
    Start-Sleep -Milliseconds 800
    $still = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($still) { Write-Warning "[sigcheck] 端口 $Port 仍被占用" } else { Write-Host "[sigcheck] port $Port free" }
}
