# check_code_highlight_run.ps1 -- real-machine assertion runner for code-block highlight fidelity.
# Guard: only kill the PID started by THIS script (safe-kill verifies debug port in cmdline);
# never resolve by port, never taskkill /T. Snapshots user release app (`Memoria.exe`) before/after.
param(
    # task-54：默认密封；-AmbientConfig 仅诊断（继承开发机 ui-settings.json）
    [switch]$AmbientConfig,
    [string]$Kb = 'artifacts\_p5_matrix_kb',
    [string]$Files = 'scale/scale-5k.md,scale/scale-10k.md,scale/scale-1k.md,corpus/01-ime-zh.md,corpus/02-inline-edges.md,corpus/03-block-boundaries.md,corpus/04-non-editable.md,corpus/05-images.md,corpus/06-links-and-kp.md,corpus/07-extremes.md,README.md,docs/error_log_format.md,docs/ref/ppt/ocr.md',
    [int]$Port = 0,
    [int]$BootWaitSec = 20
)
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path

# ── 配置隔离（task-54）：默认密封，不继承开发机 config/ui-settings.json ──
#   事故背景：ambient 的 search.embedding_enabled=true 会让搜索同步建 embedding 索引
#   而长时间阻塞（S11 假红）；同类泄漏也可能污染冻结基线。
$script:IsoHelper = Join-Path $PSScriptRoot '_iso_config.ps1'
if (-not (Test-Path $script:IsoHelper)) {
    throw "[iso] 缺少 $script:IsoHelper —— 拒绝在无配置隔离下运行测量"
}
. $script:IsoHelper
$script:Iso = Initialize-MemoriaConfigIsolation -Script 'check_code_highlight_run' -Label ''run'' -Ambient:$AmbientConfig
$KbAbs = (Resolve-Path (Join-Path $RepoRoot $Kb)).Path
Import-Module (Join-Path $RepoRoot 'scripts\benchmark\surface\safe-kill.psm1') -Force
if ($Port -le 0) { $l = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0); $l.Start(); $Port = $l.LocalEndpoint.Port; $l.Stop() }
$Out = Join-Path $RepoRoot 'artifacts\agent\verify\p6a-highlight-check.json'
$SnapOut = Join-Path $RepoRoot 'artifacts\agent\verify\p6a-highlight-userapp-snapshots.json'
$script:AppPid = $null
$script:PreserveScene = $false

function Get-UserAppSnapshot {
    @(Get-CimInstance Win32_Process -Filter "Name='Memoria.exe'" -ErrorAction SilentlyContinue |
        Select-Object ProcessId, ExecutablePath, @{n = 'CreationDate'; e = { if ($_.CreationDate) { $_.CreationDate.ToString('o') } else { $null } } })
}
function SnapshotKey($snap) {
    ($snap | Sort-Object ProcessId | ForEach-Object { "$($_.ProcessId)|$($_.ExecutablePath)|$($_.CreationDate)" }) -join ';'
}
function Stop-App {
    if ($script:AppPid) { Stop-MeasurementProcess -ProcessId $script:AppPid -ExpectedPort $Port -Quiet | Out-Null; $script:AppPid = $null }
    Start-Sleep -Milliseconds 600
    Stop-OrphanWebView2 -Marker "--remote-debugging-port=$Port" | Out-Null
}

$before = Get-UserAppSnapshot
Write-Host "[p6h] user-app BEFORE: $(@($before | ForEach-Object { $_.ProcessId }) -join ',')"
try {
    $owner = Get-PortOwnerSafe -Port $Port
    if (-not $owner.Free) { throw "port $Port already in use ($($owner.Identity)); refusing to start/kill anything" }
    $env:MEMORIA_MODE = 'dev'; $env:MEMORIA_FRAMELESS = '0'
    $env:MEMORIA_KB = $KbAbs
    $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = "--remote-debugging-port=$Port"
    $p = Start-Process -FilePath 'python' -ArgumentList '-m', 'memoria.app.desktop', "--remote-debugging-port=$Port" -WorkingDirectory $RepoRoot -PassThru `
        -RedirectStandardOutput (Join-Path $env:TEMP "p6h_$Port.out") -RedirectStandardError (Join-Path $env:TEMP "p6h_$Port.err")
    $script:AppPid = $p.Id
    Start-Sleep -Seconds $BootWaitSec
    # Keep measurement window un-minimized: render-ready polls requestAnimationFrame (paused when iconic).
    $fgJob = Start-Job -ScriptBlock {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class Win32Restore {
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
}
'@ -ErrorAction SilentlyContinue
        while ($true) {
            Start-Sleep -Seconds 2
            Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | ForEach-Object {
                try { if ([Win32Restore]::IsIconic($_.MainWindowHandle)) { [Win32Restore]::ShowWindow($_.MainWindowHandle, 9) | Out-Null } } catch { }
            }
        }
    }
    for ($i = 0; $i -lt 20; $i++) { $r = & curl.exe -s --max-time 3 "http://127.0.0.1:$Port/json/version" 2>$null; if ($r -match 'webSocketDebuggerUrl') { break }; Start-Sleep -Seconds 2 }
    Write-Host "[p6h] CDP port=$Port kb=$KbAbs"
    & node (Join-Path $PSScriptRoot 'check_code_highlight.mjs') --cdp "http://127.0.0.1:$Port" --kb $KbAbs --files $Files --out $Out
    Write-Host "[p6h] node exit=$LASTEXITCODE"
}
finally {
    if ($fgJob) { Stop-Job -Job $fgJob -ErrorAction SilentlyContinue; Remove-Job -Job $fgJob -Force -ErrorAction SilentlyContinue }
    $after = Get-UserAppSnapshot
    Write-Host "[p6h] user-app AFTER : $(@($after | ForEach-Object { $_.ProcessId }) -join ',')"
    $changed = ((SnapshotKey $before) -ne (SnapshotKey $after))
    $snap = [ordered]@{ schema = 'memoria-p6a-highlight-userapp-snapshots/v1'; port = $Port; before = $before; after = $after; changed = $changed; capturedAt = (Get-Date).ToUniversalTime().ToString('o'); checkOut = $Out }
    [IO.File]::WriteAllText($SnapOut, ($snap | ConvertTo-Json -Depth 6), (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "[p6h] snapshot=$SnapOut changed=$changed"
    if ($changed) { $script:PreserveScene = $true; Write-Host "__P6A_USERAPP_CHANGED__ before=[$(SnapshotKey $before)] after=[$(SnapshotKey $after)]" }
    if ($script:PreserveScene) { Write-Host '[p6h] USER APP CHANGED -> preserving scene, exit 3' } else { Stop-App }
}
if ($script:PreserveScene) { exit 3 }
