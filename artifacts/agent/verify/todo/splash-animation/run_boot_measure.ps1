# task-186 T-splash-2 冷启动耗时对照测量（改前/改后同一口径）
#
# 每次 trial：
#   · 全新隔离 config 目录（MEMORIA_CONFIG_DIR）⇒ 冷启动语义一致（无上次文件可恢复，走启发式打开）
#   · 固定 KB = 本目录 kb/（tests/probe-kb 副本）
#   · t0 = 启动子进程的墙钟毫秒 → 页面里 html.-booting 移除的墙钟毫秒（measure_boot.mjs）
#   · 结束后只杀自己启动的进程树
#
# 用法：powershell -NoProfile -ExecutionPolicy Bypass -File run_boot_measure.ps1 `
#         -Label before -Trials 5 -NodeExe <node.exe>
param(
    [string]$Label = 'before',
    [int]$Trials = 5,
    [string]$NodeExe = 'node',
    [int]$BasePort = 9630
)
$ErrorActionPreference = 'Stop'
$Here = $PSScriptRoot
$RepoRoot = $Here
1..5 | ForEach-Object { $RepoRoot = Split-Path $RepoRoot -Parent }
$KbDir = Join-Path $Here 'kb'
$ConfigRoot = Join-Path $Here "config-$Label"
$OutDir = Join-Path $Here "measures-$Label"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = 'python' }

$rows = @()
for ($i = 1; $i -le $Trials; $i++) {
    $port = $BasePort + $i
    $cfg = Join-Path $ConfigRoot ("trial-{0}" -f $i)
    if (Test-Path $cfg) { Remove-Item $cfg -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $cfg | Out-Null
    $out = Join-Path $OutDir ("trial-{0}.json" -f $i)
    if (Test-Path $out) { Remove-Item $out -Force }

    $busy = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($busy) { throw "端口 $port 被占用（pid $($busy.OwningProcess)），换 BasePort 重跑" }

    $env:MEMORIA_MODE = 'dev'
    $env:MEMORIA_FRAMELESS = '0'
    $env:MEMORIA_KB = (Resolve-Path $KbDir).Path
    $env:MEMORIA_CONFIG_DIR = (Resolve-Path $cfg).Path
    $env:MEMORIA_PROBE_CDP_PORT = "$port"
    $stdout = Join-Path $env:TEMP "splash_boot_${Label}_$i.out"
    $stderr = Join-Path $env:TEMP "splash_boot_${Label}_$i.err"
    $t0 = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    $p = Start-Process -FilePath $python -ArgumentList (Join-Path $Here 'launch_with_cdp.py') `
        -WorkingDirectory $RepoRoot -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $valid = $false
    try {
        $ready = $false
        for ($j = 0; $j -lt 40; $j++) {
            Start-Sleep -Milliseconds 150
            try {
                $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 1 "http://127.0.0.1:$port/json/version" -ErrorAction Stop
                if ($r.Content -match 'webSocketDebuggerUrl') { $ready = $true; break }
            } catch { }
        }
        if (-not $ready) { throw "trial ${i}: CDP 未就绪；stderr: $(Get-Content $stderr -Tail 8 -ErrorAction SilentlyContinue | Out-String)" }
        & $NodeExe (Join-Path $Here 'measure_boot.mjs') --port $port --t0 $t0 --out $out
        if ($LASTEXITCODE -eq 0) { $valid = $true }
    } finally {
        & taskkill.exe /T /F /PID $p.Id 2>$null | Out-Null
        Start-Sleep -Milliseconds 700
        Remove-Item Env:\MEMORIA_MODE, Env:\MEMORIA_FRAMELESS, Env:\MEMORIA_KB, Env:\MEMORIA_CONFIG_DIR, Env:\MEMORIA_PROBE_CDP_PORT -ErrorAction SilentlyContinue
    }
    $rec = if (Test-Path $out) { Get-Content $out -Raw | ConvertFrom-Json } else { $null }
    $ms = if ($rec -and $rec.boot_ms) { [double]$rec.boot_ms } else { $null }
    Write-Host ("[measure:{0}] trial {1}/{2}: valid={3} boot_ms={4}" -f $Label, $i, $Trials, $valid, $ms)
    $rows += [pscustomobject]@{ trial = $i; valid = $valid; boot_ms = $ms; json = $out }
}

$validMs = @($rows | Where-Object { $_.valid -and $null -ne $_.boot_ms } | ForEach-Object { $_.boot_ms } | Sort-Object)
$summary = [pscustomobject]@{
    label = $Label
    trials = $rows
    valid_count = $validMs.Count
    median_ms = if ($validMs.Count -ge 1) { $validMs[[math]::Floor(($validMs.Count - 1) / 2)] } else { $null }
    min_ms = if ($validMs.Count) { $validMs[0] } else { $null }
    max_ms = if ($validMs.Count) { $validMs[-1] } else { $null }
    all_ms = $validMs
}
$summaryPath = Join-Path $OutDir 'summary.json'
[IO.File]::WriteAllText($summaryPath, ($summary | ConvertTo-Json -Depth 6), (New-Object System.Text.UTF8Encoding($false)))
Write-Host ("[measure:{0}] valid={1}/{2} median={3}ms all={4}" -f $Label, $validMs.Count, $Trials, $summary.median_ms, ($validMs -join ','))
Write-Host "[measure:$Label] summary: $summaryPath"
