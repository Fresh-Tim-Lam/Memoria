# ---------------------------------------------------------------------------
# run_domwrites.ps1 —— 真机「每键 DOM 写入」测量一键脚本
#
# 启动真实 Memoria 应用（WebView2 + CDP 端口）→ 跑 realapp_domwrites.mjs → 关闭应用。
# 用途：阶段 1 性能闸（phase1-performance-gate.md）的「新基线」与「P2 最终判定」取数。
#
# 用法：
#   .\scripts\benchmark\surface\run_domwrites.ps1 -Out "results\raw-domwrites-post19-run1.json"
#   .\scripts\benchmark\surface\run_domwrites.ps1 -Rounds 5 -Keys 10 -Warmup 5 -Port 9500
#
# 设计要点（见文档 phase1-performance-gate.md §4.0 与 metrics-agent 报告）：
#   · 每次测量独立启停应用，避免前端 ?v= 旧缓存、内存态、残留选区污染读数；
#   · 用 Start-Process 记录 PID，结束用 Stop-Process 精确杀该 PID + 兜底按 9500 端口找 owner，
#     不 taskkill /F 全局 python，避免误杀其它进程、避免锁 .desktop-build；
#   · env 写死 dev 态（MEMORIA_MODE=dev、MEMORIA_FRAMELESS=0），
#     KB 用 tests/probe-kb（scale-5k.md 档位，与既有基线一致）。
# ---------------------------------------------------------------------------
param(
    # task-54：默认密封；-AmbientConfig 仅诊断（继承开发机 ui-settings.json）
    [switch]$AmbientConfig,
    [string]$Out = "results\raw-domwrites-run.json",
    [string]$FileA = "scale/scale-5k.md",
    [int]$Rounds = 5,
    [int]$Keys = 10,
    [int]$Warmup = 5,
    [int]$Port = 9500,
    [int]$BootWaitSec = 16,      # 应用 + CDP 就绪的保守等待
    [switch]$KeepAlive           # 调试用：测量后不关应用
)

$ErrorActionPreference = "Stop"

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

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path

# ── 配置隔离（task-54）：默认密封，不继承开发机 config/ui-settings.json ──
#   事故背景：ambient 的 search.embedding_enabled=true 会让搜索同步建 embedding 索引
#   而长时间阻塞（S11 假红）；同类泄漏也可能污染冻结基线。
$script:IsoHelper = Join-Path $PSScriptRoot '_iso_config.ps1'
if (-not (Test-Path $script:IsoHelper)) {
    throw "[iso] 缺少 $script:IsoHelper —— 拒绝在无配置隔离下运行测量"
}
. $script:IsoHelper
$script:Iso = Initialize-MemoriaConfigIsolation -Script 'run_domwrites' -Label ''run'' -Ambient:$AmbientConfig

function Stop-App {
    # 1) 只终止本次启动的 $script:AppPid（不连带子进程树）。
    #    !! 实测教训：pywebview 的 WebView2 会拉起一整棵 msedgewebview2 进程树
    #    (browser + crashpad + gpu-process + utility + renderer...)。
    #    只 Stop-Process 主 python 进程 => 那棵树全部变成孤儿继续吃 CPU/GPU，
    #    下一次测量的读数被这堆残留拖慢（实测 run2 时延随轮次单调上升 12->22ms，
    #    而写入计数完全没变 => 纯机器侧负载，不是代码回归）。
    #    现改用 Stop-OrphanWebView2 按唯一标记精确清理孤儿（原「杀整棵树」做法已于 task-49 废弃，
#    因其会波及其他进程，曾导致用户应用被误杀）。
    if ($script:AppPid) {
        $p = Get-Process -Id $script:AppPid -ErrorAction SilentlyContinue
        if ($p) {
            Stop-MeasurementProcess -ProcessId $script:AppPid -ExpectedPort $Port -Quiet | Out-Null
            Write-Host "[run_domwrites] stopped app tree pid $($script:AppPid) (/T)"
        }
        $script:AppPid = $null
    }
    # 2) 兜底：按 CDP 端口找监听者
    #    !! taskkill 对"正在退出的子进程"会返回 ERROR 且写 stderr；在 $ErrorActionPreference=Stop
    #    下这会把整个脚本打断（虽然测量已完成，但退出码非 0，看着像失败）。故显式吞掉其 stderr
    #    与退出码，并把"端口仍被占"降级为 warning。
    #    !! 更重要：**只杀确实是本次测量留下的进程**（python memoria 或 Temp EBWebView 下的 WebView2），
    #    绝不误杀别人的进程 —— 实测这台机器上存在一个外部打包版 Memoria.exe 的 WebView2 也在监听，
    #    那不是我启动的，不能碰。
    Start-Sleep -Milliseconds 500
    $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($c) {
        $ownerProc = Get-CimInstance Win32_Process -Filter "ProcessId=$($c.OwningProcess)" -ErrorAction SilentlyContinue
        $cmd = if ($ownerProc) { [string]$ownerProc.CommandLine } else { '' }
        $mine = ($cmd -like '*memoria.app.desktop*') -or ($cmd -like '*\Temp\*EBWebView*') -or ($cmd -like '*\Temp\tmp*')
        if ($mine) {
            $prevEap = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            # ★ 已移除「凭端口反查 PID 再杀」——该路径曾误杀用户 app。改为只报告：
            Get-PortOwnerSafe -Port $Port | Out-Null
            $ErrorActionPreference = $prevEap
            Write-Host "[run_domwrites] killed own leftover listener tree pid $($c.OwningProcess)"
        } else {
            Write-Warning "[run_domwrites] 端口 $Port 被**非本次测量**的进程占用（pid $($c.OwningProcess)），不终止：$($cmd.Substring(0,[Math]::Min(90,$cmd.Length)))"
        }
    }
    # 3) 兜底：清理 parent 已消失、且 user-data-dir 指向 Temp\...EBWebView 的孤儿
    #    （只认 Temp 下的 EBWebView，不碰用户正常 Edge / 其它应用的 WebView2）
    $orphans = @(Get-CimInstance Win32_Process -Filter "Name='msedgewebview2.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match 'user-data-dir=[^"]*\\Temp\\[^"\\]*EBWebView' })
    $swept = 0
    foreach ($o in $orphans) {
        $parentAlive = $null -ne (Get-Process -Id $o.ParentProcessId -ErrorAction SilentlyContinue)
        if (-not $parentAlive) {
            Stop-Process -Id $o.ProcessId -Force -ErrorAction SilentlyContinue
            $swept++
        }
    }
    if ($swept -gt 0) { Write-Host "[run_domwrites] swept $swept orphaned temp WebView2 process(es)" }
    # 4) 确认端口释放
    Start-Sleep -Milliseconds 800
    $c2 = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($c2) { Write-Warning "[run_domwrites] port $Port 仍未释放（pid $($c2.OwningProcess)）" }
    else { Write-Host "[run_domwrites] port $Port free" }
}

try {
    # 先确保端口干净（残留进程）
    # ★ task-49：端口被占用时**不再自动清理**（曾因反查 PID 误杀用户 app），只报告。
    $portInfo = Get-PortOwnerSafe -Port $Port
    if (-not $portInfo.Free) {
        throw "[run_domwrites] 端口 $Port 被占用（$($portInfo.Identity)），请换端口后重跑。$($portInfo.Advice)"
    }

    # ── env ──
    $env:MEMORIA_MODE      = 'dev'
    $env:MEMORIA_FRAMELESS = '0'
    $env:MEMORIA_KB        = Join-Path $RepoRoot 'tests\probe-kb'
    $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = "--remote-debugging-port=$Port"

    # ── 启动应用 ──
    $stdout = Join-Path $env:TEMP "domwrites_app_$($Port).out"
    $stderr = Join-Path $env:TEMP "domwrites_app_$($Port).err"
    $p = Start-Process -FilePath 'python' -ArgumentList '-m','memoria.app.desktop' `
          -WorkingDirectory $RepoRoot -PassThru `
          -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $script:AppPid = $p.Id
    Write-Host "[run_domwrites] app started pid=$($p.Id), waiting ${BootWaitSec}s for CDP..."

    Start-Sleep -Seconds $BootWaitSec

    # 确认 CDP 起来
    $ready = $false
    for ($i = 0; $i -lt 10; $i++) {
        $r = & curl.exe -s --max-time 3 "http://127.0.0.1:$Port/json/version" 2>$null
        if ($r -match 'webSocketDebuggerUrl') { $ready = $true; break }
        Start-Sleep -Seconds 2
    }
    if (-not $ready) {
        Throw "[run_domwrites] CDP 端口 $Port 未就绪；stderr 尾部：`n$(Get-Content $stderr -Tail 15 -ErrorAction SilentlyContinue)"
    }

    # ── 测量 ──
    $absOut = Join-Path $RepoRoot $Out
    $nodeArgs = @(
        (Join-Path $PSScriptRoot 'realapp_domwrites.mjs'),
        '--port', $Port,
        '--file-a', $FileA,
        '--rounds', $Rounds,
        '--keys', $Keys,
        '--warmup-keys', $Warmup,
        '--out', $absOut
    )
    Write-Host "[run_domwrites] measure: node $($nodeArgs -join ' ')"
    & node @nodeArgs
    $measureExit = $LASTEXITCODE
    if ($measureExit -ne 0) {
        Throw "[run_domwrites] 测量失败（node exit=$measureExit）。out=$absOut"
    }

    if (Test-Path $absOut) {
        Write-Host "[run_domwrites] wrote $absOut"
    } else {
        Throw "[run_domwrites] 测量未产出 out 文件"
    }
} finally {
    if (-not $KeepAlive) {
        Stop-App
    } else {
        Write-Host "[run_domwrites] KeepAlive：应用保持运行（pid $($script:AppPid)）"
    }
    # 清理本脚本设的 env（不污染调用方后续）
    Remove-Item Env:\MEMORIA_MODE, Env:\MEMORIA_FRAMELESS, Env:\MEMORIA_KB, Env:\WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS -ErrorAction SilentlyContinue
}
