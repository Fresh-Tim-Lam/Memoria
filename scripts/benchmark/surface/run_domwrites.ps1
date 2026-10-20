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
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path

function Stop-App {
    # 1) 按记录的 PID **连整棵进程树**一起杀。
    #    !! 实测教训：pywebview 的 WebView2 会拉起一整棵 msedgewebview2 进程树
    #    (browser + crashpad + gpu-process + utility + renderer...)。
    #    只 Stop-Process 主 python 进程 => 那棵树全部变成孤儿继续吃 CPU/GPU，
    #    下一次测量的读数被这堆残留拖慢（实测 run2 时延随轮次单调上升 12->22ms，
    #    而写入计数完全没变 => 纯机器侧负载，不是代码回归）。
    #    故用 taskkill /T 杀整棵树，再兜底清理指向临时 EBWebView 的孤儿。
    if ($script:AppPid) {
        $p = Get-Process -Id $script:AppPid -ErrorAction SilentlyContinue
        if ($p) {
            & taskkill.exe /PID $script:AppPid /T /F 2>&1 | Out-Null
            Write-Host "[run_domwrites] stopped app tree pid $($script:AppPid) (/T)"
        }
        $script:AppPid = $null
    }
    # 2) 兜底：按 CDP 端口找监听者
    Start-Sleep -Milliseconds 500
    $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($c) {
        & taskkill.exe /PID $c.OwningProcess /T /F 2>&1 | Out-Null
        Write-Host "[run_domwrites] killed leftover listener tree pid $($c.OwningProcess)"
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
    $leftover = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($leftover) {
        Write-Warning "[run_domwrites] 端口 $Port 被 pid $($leftover.OwningProcess) 占用，先清理"
        Stop-App
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
