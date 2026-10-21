# run_p5_isolated_matrix.ps1 —— P5 矩阵「每篇文档独立会话」驱动（task-33 方案②）
#
# 为什么需要它（Lead 裁决）：
#   批跑时中招的文档**会换**（12 文档批是 scale-5k 多 1，2 文档批是 scale-1k 少 1），
#   且方向都不一致（一次 new 多、一次 legacy 少）⇒ 结论是**跨文档状态残留**，
#   渲染管线无辜。为拿到**可信基线**，改为每篇文档独立起一次 app 会话跑 dual。
#
# ⚠️ 口径：本脚本产出的是「每文档独立会话」基线，与批跑结果**不可混比**。
#
# 用法：
#   powershell -File scripts/benchmark/surface/run_p5_isolated_matrix.ps1
#   （默认跑 13 篇；可用 -Files 指定子集）
param(
    [string]$Kb = 'artifacts\_p5_matrix_kb',
    [string]$Label = 'p5iso',
    [string]$Files = '',
    [int]$ReadyTimeout = 300000,
    [int]$BootWaitSec = 18
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$ResultsDir = Join-Path $RepoRoot 'scripts\benchmark\surface\results'
$VerbDir = Join-Path $RepoRoot 'artifacts\agent\verify'
$Sha = (& git -C $RepoRoot rev-parse --short HEAD).Trim()
$script:AppPid = $null
$script:Port = 0

$AllFiles = @(
    'scale/scale-1k.md',
    'scale/scale-5k.md',
    'scale/scale-10k.md',
    'corpus/01-ime-zh.md',
    'corpus/02-inline-edges.md',
    'corpus/03-block-boundaries.md',
    'corpus/04-non-editable.md',
    'corpus/05-images.md',
    'corpus/06-links-and-kp.md',
    'corpus/07-extremes.md',
    'README.md',
    'docs/error_log_format.md',
    'docs/ref/ppt/ocr.md'
)
if ($Files) { $AllFiles = @($Files -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ }) }

function Stop-App {
    if ($script:AppPid) {
        $prevEap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
        try { & taskkill.exe /PID $script:AppPid /T /F *>&1 | Out-Null } catch { }
        $ErrorActionPreference = $prevEap; $script:AppPid = $null
    }
    Start-Sleep -Milliseconds 800
    if ($script:Port -gt 0) {
        $c = Get-NetTCPConnection -LocalPort $script:Port -State Listen -ErrorAction SilentlyContinue
        if ($c) {
            $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($c.OwningProcess)" -ErrorAction SilentlyContinue
            $cmd = if ($owner) { [string]$owner.CommandLine } else { '' }
            if ($cmd -like '*memoria.app.desktop*' -or $cmd -like '*\Temp\*EBWebView*') {
                $prevEap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
                try { & taskkill.exe /PID $c.OwningProcess /T /F *>&1 | Out-Null } catch { }
                $ErrorActionPreference = $prevEap
            }
        }
    }
    # 只扫 user-data-dir 在 Temp 的孤儿（=本次启动的）
    $orphans = @(Get-CimInstance Win32_Process -Filter "Name='msedgewebview2.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -like '*EBWebView*' -and $_.CommandLine -like '*\Temp\*' -and
            (-not (Get-Process -Id $_.ParentProcessId -ErrorAction SilentlyContinue))
        })
    $prevEap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    foreach ($o in $orphans) { try { & taskkill.exe /PID $o.ProcessId /T /F *>&1 | Out-Null } catch { } }
    $ErrorActionPreference = $prevEap
    foreach ($o in $orphans) {
        for ($w = 0; $w -lt 10; $w++) {
            if (-not (Get-Process -Id $o.ProcessId -ErrorAction SilentlyContinue)) { break }
            Start-Sleep -Milliseconds 500
        }
    }
    if ($orphans.Count -gt 0) { Write-Host "[p5iso] swept $($orphans.Count) orphaned WebView2" }
}

function Start-App {
    $l = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    $l.Start(); $script:Port = $l.LocalEndpoint.Port; $l.Stop()

    $env:MEMORIA_MODE = 'dev'
    $env:MEMORIA_FRAMELESS = '0'
    $env:MEMORIA_KB = (Resolve-Path (Join-Path $RepoRoot $Kb)).Path
    $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = "--remote-debugging-port=$($script:Port)"

    $out = Join-Path $env:TEMP "p5iso_app_$($script:Port).out"
    $err = Join-Path $env:TEMP "p5iso_app_$($script:Port).err"
    $p = Start-Process -FilePath 'python' -ArgumentList '-m', 'memoria.app.desktop' `
        -WorkingDirectory $RepoRoot -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
    $script:AppPid = $p.Id
    Start-Sleep -Seconds $BootWaitSec
    for ($i = 0; $i -lt 15; $i++) {
        $r = & curl.exe -s --max-time 3 "http://127.0.0.1:$($script:Port)/json/version" 2>$null
        if ($r -match 'webSocketDebuggerUrl') { return $true }
        Start-Sleep -Seconds 2
    }
    return $false
}

$index = @()
$failCount = 0
try {
    $i = 0
    foreach ($f in $AllFiles) {
        $i++
        $safe = ($f -replace '[/\\]', '_')
        Write-Host "[p5iso] ($i/$($AllFiles.Count)) $f  —— 独立会话"
        if (-not (Start-App)) { Write-Host "[p5iso]   APP 启动失败，跳过"; $failCount++; Stop-App; continue }

        $dir = Join-Path $VerbDir "p5iso_$safe"
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        $outNew = Join-Path $dir "new_$Sha.json"
        $outLegacy = Join-Path $dir "legacy_$Sha.json"
        $outDiag = Join-Path $dir "diag_$Sha.json"

        $nodeArgs = @(
            'artifacts\agent\verify\p2c_realapp_new.mjs',
            '--cdp', "http://127.0.0.1:$($script:Port)",
            '--files', $f,
            '--ready-timeout', "$ReadyTimeout",
            '--out-new', $outNew,
            '--out-legacy', $outLegacy,
            '--out-diag', $outDiag
        )
        & node @nodeArgs 2>&1 | Out-Null
        $nodeExit = $LASTEXITCODE

        Stop-App
        Start-Sleep -Milliseconds 500

        $index += [pscustomobject]@{
            file = $f
            port = $script:Port
            nodeExit = $nodeExit
            new = $outNew
            legacy = $outLegacy
            diag = $outDiag
            ok = ($nodeExit -eq 0 -and (Test-Path $outNew) -and (Test-Path $outLegacy))
        }
        if ($nodeExit -ne 0) { $failCount++ }
        Write-Host "[p5iso]   exit=$nodeExit"
    }
}
finally {
    Stop-App
    Start-Sleep -Milliseconds 800
}

$ManifestPath = Join-Path $VerbDir "p5iso-manifest-$Sha.json"
$manifest = @{
    schema = 'memoria-p5-isolated-matrix/v1'
    mode = 'per-doc-isolated-session'
    note = '每篇文档独立起一次 app 会话；与批跑结果不可混比'
    headSha = $Sha
    kb = $Kb
    docCount = $AllFiles.Count
    failed = $failCount
    entries = $index
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content $ManifestPath -Encoding UTF8
Write-Host "[p5iso] manifest: $ManifestPath"
Write-Host "[p5iso] 完成 $($AllFiles.Count) 篇，失败 $failCount"
