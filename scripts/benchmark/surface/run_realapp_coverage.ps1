# run_realapp_coverage.ps1 —— 真机补测：启动应用 → 驱动 4 项测量 → 整树清理
#
# 复用 run_domwrites.ps1 已验证的启停/整树清理做法（task-27）。
# 只读测量，不改 src/**。
#
# 用法：
#   powershell -File scripts\benchmark\surface\run_realapp_coverage.ps1 [-Kb <路径>] [-Rounds 3] [-Ops all]
param(
    [string]$Kb = 'docs\example\行政法',   # 含 KP（52 个 kp 相关 json）
    [int]$Rounds = 3,
    [string]$Ops = 'all',
    [int]$Port = 9500,
    [int]$BootWaitSec = 18,
    [string]$Out = '',
    [string]$SessionId = ''
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$script:AppPid = $null

function Stop-App {
    if ($script:AppPid) {
        Write-Host "[realcov] stopping app tree pid $($script:AppPid)"
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
        $mine = ($cmd -like '*memoria.app.desktop*') -or ($cmd -like '*\Temp\*EBWebView*')
        if ($mine) {
            $prevEap = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            try { & taskkill.exe /PID $c.OwningProcess /T /F *>&1 | Out-Null } catch { }
            $ErrorActionPreference = $prevEap
            Write-Host "[realcov] killed own leftover listener pid $($c.OwningProcess)"
        } else {
            Write-Warning "[realcov] 端口 $Port 被非本次进程占用（pid $($c.OwningProcess)），不终止"
        }
    }
    # 孤儿 WebView2（parent 已消失、user-data-dir 指向 Temp）
    $orphans = @(Get-CimInstance Win32_Process -Filter "Name='msedgewebview2.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -like '*EBWebView*' -and
            (-not (Get-Process -Id $_.ParentProcessId -ErrorAction SilentlyContinue))
        })
    foreach ($o in $orphans) {
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try { & taskkill.exe /PID $o.ProcessId /T /F *>&1 | Out-Null } catch { }
        $ErrorActionPreference = $prevEap
    }
    if ($orphans.Count -gt 0) { Write-Host "[realcov] swept $($orphans.Count) orphaned WebView2" }
}

try {
    # 前置：端口必须空闲
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
        Write-Host "[realcov] 端口 $Port 已被占用，先清理"
        Stop-App
    }

    # 真机环境（与 realapp-measurement-protocol.md 一致）
    $env:MEMORIA_MODE      = 'dev'
    $env:MEMORIA_FRAMELESS = '0'
    $env:MEMORIA_KB        = (Resolve-Path (Join-Path $RepoRoot $Kb)).Path
    $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = "--remote-debugging-port=$Port"
    Write-Host "[realcov] KB = $env:MEMORIA_KB  (mode=real, port=$Port)"

    $stdout = Join-Path $env:TEMP "realcov_app_$Port.out"
    $stderr = Join-Path $env:TEMP "realcov_app_$Port.err"
    $p = Start-Process -FilePath 'python' -ArgumentList '-m', 'memoria.app.desktop' `
        -WorkingDirectory $RepoRoot -PassThru `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $script:AppPid = $p.Id
    Write-Host "[realcov] app started pid=$($p.Id), waiting ${BootWaitSec}s for CDP..."
    Start-Sleep -Seconds $BootWaitSec

    $ready = $false
    for ($i = 0; $i -lt 15; $i++) {
        $r = & curl.exe -s --max-time 3 "http://127.0.0.1:$Port/json/version" 2>$null
        if ($r -match 'webSocketDebuggerUrl') { $ready = $true; break }
        Start-Sleep -Seconds 2
    }
    if (-not $ready) {
        Write-Host "[realcov] CDP 未就绪；stderr 尾部："
        Get-Content $stderr -Tail 20 -ErrorAction SilentlyContinue
        Throw "[realcov] CDP 端口 $Port 未就绪"
    }
    Write-Host "[realcov] CDP ready"

    if (-not $Out) {
        $sha = (& git -C $RepoRoot rev-parse --short HEAD).Trim()
        $Out = "scripts\benchmark\surface\results\realapp-coverage_$sha.json"
    }
    $absOut = Join-Path $RepoRoot $Out

    $nodeArgs = @(
        (Join-Path $PSScriptRoot 'realapp_coverage.mjs'),
        '--cdp', "http://127.0.0.1:$Port",
        '--ops', $Ops,
        '--rounds', $Rounds,
        '--out', $absOut
    )
    if ($SessionId) { $nodeArgs += @('--session-id', $SessionId) }
    Write-Host "[realcov] measure: node $($nodeArgs -join ' ')"
    & node @nodeArgs
    $code = $LASTEXITCODE

    Write-Host "[realcov] wrote $absOut (node exit=$code)"
}
finally {
    Stop-App
    Start-Sleep -Milliseconds 800
    $still = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($still) { Write-Warning "[realcov] 端口 $Port 仍被占用（pid $($still.OwningProcess)）" }
    else { Write-Host "[realcov] port $Port free" }
    "RESULT_FILE=$Out"
}
