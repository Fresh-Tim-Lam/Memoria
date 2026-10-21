# run_realapp_coverage.ps1 —— 真机补测：启动应用 → 驱动 4 项测量 → 整树清理
#
# 复用 run_domwrites.ps1 已验证的启停/整树清理做法（task-27）。
# 只读测量，不改 src/**。
#
# 用法：
#   powershell -File scripts\benchmark\surface\run_realapp_coverage.ps1 [-Kb <路径>] [-Rounds 3] [-Ops all]
param(
    # task-54：默认密封；-AmbientConfig 仅诊断（继承开发机 ui-settings.json）
    [switch]$AmbientConfig,
    [string]$Kb = 'docs\example\行政法',   # 含 KP（52 个 kp 相关 json）
    [int]$Rounds = 3,
    [string]$Ops = 'all',
    [int]$Port = 9500,
    [int]$BootWaitSec = 18,
    [string]$Out = '',
    [string]$SessionId = ''
)

$ErrorActionPreference = 'Stop'

# ═══════════════════════════════════════════════════════════════════════════
#  安全终止（task-49）—— 统一入口：禁止杀进程树、禁止凭端口反查 PID 再杀。
#  ★ 事故背景：2026-10-21 本仓库测量脚本用「端口反查 PID + 杀进程树」的方式清理实例，
#    端口恰好被用户手动打开的 Package\Memoria.exe 占用 ⇒ **用户 app 被误杀并重启**
#    （pid 21860 → 39868 → 49444）。故：
#      · 只杀本次脚本 Start-Process 得到的 $script:AppPid；
#      · 杀前校验该 PID 命令行必含本次调试端口，不含则拒绝；
#      · 端口被占用时**只报告、不终止**；
#      · 绝不杀进程树（不连带子进程），绝不杀 Package\Memoria.exe。
# ═══════════════════════════════════════════════════════════════════════════
$script:SafeKillModule = Join-Path $PSScriptRoot 'safe-kill.psm1'
if (Test-Path $script:SafeKillModule) {
    Import-Module $script:SafeKillModule -Force -DisableNameChecking
} else {
    throw "[safe-kill] 缺少 $script:SafeKillModule —— 禁止在无安全模块时运行（防误杀用户应用）"
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path

# ── 配置隔离（task-54）：默认密封，不继承开发机 config/ui-settings.json ──
#   事故背景：ambient 的 search.embedding_enabled=true 会让搜索同步建 embedding 索引
#   而长时间阻塞（S11 假红）；同类泄漏也可能污染冻结基线。
$script:IsoHelper = Join-Path $PSScriptRoot '_iso_config.ps1'
if (-not (Test-Path $script:IsoHelper)) {
    throw "[iso] 缺少 $script:IsoHelper —— 拒绝在无配置隔离下运行测量"
}
. $script:IsoHelper
$script:Iso = Initialize-MemoriaConfigIsolation -Script 'run_realapp_coverage' -Label ''run'' -Ambient:$AmbientConfig
$script:AppPid = $null

function Stop-App {
    if ($script:AppPid) {
        Write-Host "[realcov] stopping app tree pid $($script:AppPid)"
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try { Stop-MeasurementProcess -ProcessId $script:AppPid -ExpectedPort $Port -Quiet | Out-Null } catch { }
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
            # ★ 已移除「凭端口反查 PID 再杀」——该路径曾误杀用户 app。改为只报告：
            Get-PortOwnerSafe -Port $Port | Out-Null
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
        try { & taskkill.exe /PID $o.ProcessId /F *>&1 | Out-Null } catch { }   # 单进程终止（task-49：不连带子树）
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
