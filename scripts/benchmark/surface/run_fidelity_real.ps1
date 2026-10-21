# run_fidelity_real.ps1 —— 真机 fidelity（run_fidelity.py --cdp）的启停封装（task-32）
#
# 为什么需要外层脚本：`run_fidelity.py --cdp` 只**直连**已运行的应用，不负责启动。
# 本脚本负责：启动真机 → 等 CDP → 调 run_fidelity.py --cdp → 整树清理 → 端口释放确认。
# 只读测量，不改 src/**。
param(
    # task-54：默认密封；-AmbientConfig 仅诊断（继承开发机 ui-settings.json）
    [switch]$AmbientConfig,
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
$script:Iso = Initialize-MemoriaConfigIsolation -Script 'run_fidelity_real' -Label ''run'' -Ambient:$AmbientConfig

# ── KB 完整性守卫（task-57）：冻结语料只读 + 前后 sha 校验 ──
#    事故：R-17 已实际发生两次（task-54、task-55），测试把内容写进冻结语料。
#    冻结语料取自独立变量 P5PERF_FROZEN_KB（与 MEMORIA_KB 分离，避免"守卫盯错对象"）。
$script:KbWire = Join-Path $PSScriptRoot '_kb_guard_wire.ps1'
if (-not (Test-Path $script:KbWire)) { throw "[kb-guard] 缺少 $script:KbWire —— 拒绝在无守卫下运行测量" }
. $script:KbWire
$script:KbGuard = Start-KbGuard -Script 'run_fidelity_real' -Label $Label
$script:AppPid = $null

function Stop-App {
    if ($script:AppPid) {
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
        if ($cmd -like '*memoria.app.desktop*' -or $cmd -like '*\Temp\*EBWebView*') {
            $prevEap = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            # ★ 已移除「凭端口反查 PID 再杀」——该路径曾误杀用户 app。改为只报告：
            Get-PortOwnerSafe -Port $Port | Out-Null
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
    try { Complete-KbGuard -Guard $script:KbGuard } catch { Write-Warning "[kb-guard] $_" }

    Stop-App
    Start-Sleep -Milliseconds 800
    $still = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($still) { Write-Warning "[fid-real] 端口 $Port 仍被占用" } else { Write-Host "[fid-real] port $Port free" }
}
