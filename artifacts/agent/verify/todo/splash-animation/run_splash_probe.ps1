# task-186 真机验收：启动应用（独立临时 KB + 独立用户态）→ 跑 probe_splash.mjs → 关闭
#   写域内证据目录：artifacts/agent/verify/todo/splash-animation
#   纪律：不碰用户 KB/用户 ui-settings；端口被占不自动清理；只杀自己启动的进程树。
param(
    [string]$NodeExe = 'node',
    [int]$Port = 9640
)
$ErrorActionPreference = 'Stop'
$Here = $PSScriptRoot
$RepoRoot = $Here
1..5 | ForEach-Object { $RepoRoot = Split-Path $RepoRoot -Parent }
$KbDir = Join-Path $Here 'kb'
$ConfigDir = Join-Path $Here 'config-probe'
$OutJson = Join-Path $Here 'verify.json'

if (-not (Test-Path $KbDir)) { throw "缺 fixture KB：$KbDir" }
if (Test-Path $ConfigDir) { Remove-Item $ConfigDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null

$busy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($busy) { throw "端口 $Port 被占用（pid $($busy.OwningProcess)）—— 不自动清理，请换端口重跑" }

$env:MEMORIA_MODE = 'dev'
$env:MEMORIA_FRAMELESS = '0'
$env:MEMORIA_KB = (Resolve-Path $KbDir).Path
$env:MEMORIA_CONFIG_DIR = (Resolve-Path $ConfigDir).Path
$env:MEMORIA_PROBE_CDP_PORT = "$Port"
$stdout = Join-Path $env:TEMP "splash_probe_$Port.out"
$stderr = Join-Path $env:TEMP "splash_probe_$Port.err"
$python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = 'python' }
$appPid = $null
$exit = 1
try {
    Write-Host "[splash-probe] 启动应用（KB=$env:MEMORIA_KB；config=$env:MEMORIA_CONFIG_DIR；CDP=$Port）"
    $p = Start-Process -FilePath $python -ArgumentList (Join-Path $Here 'launch_with_cdp.py') `
        -WorkingDirectory $RepoRoot -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $appPid = $p.Id
    $ready = $false
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Milliseconds 150
        try {
            $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 1 "http://127.0.0.1:$Port/json/version" -ErrorAction Stop
            if ($r.Content -match 'webSocketDebuggerUrl') { $ready = $true; break }
        } catch { }
    }
    if (-not $ready) { throw "[splash-probe] CDP 未就绪；stderr: $(Get-Content $stderr -Tail 20 -ErrorAction SilentlyContinue | Out-String)" }
    & $NodeExe (Join-Path $Here 'probe_splash.mjs') --port $Port --out $OutJson
    $exit = $LASTEXITCODE
} finally {
    if ($appPid) { & taskkill.exe /T /F /PID $appPid 2>$null | Out-Null; Start-Sleep -Milliseconds 700 }
    Remove-Item Env:\MEMORIA_MODE, Env:\MEMORIA_FRAMELESS, Env:\MEMORIA_KB, Env:\MEMORIA_CONFIG_DIR, Env:\MEMORIA_PROBE_CDP_PORT -ErrorAction SilentlyContinue
}
exit $exit
