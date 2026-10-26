# task-183 真机 DOM 验收：启动应用（独立临时 KB + 独立用户态目录）→ 跑 probe.mjs → 关闭
#
# 隔离纪律（照 scripts/benchmark/surface/run_domwrites.ps1 的既有做法）：
#   · MEMORIA_KB       = 本目录 kb/（tests/probe-kb 的副本 + 固定 fixture 会话）⇒ 不碰用户知识库
#   · MEMORIA_CONFIG_DIR = 本目录 config/ ⇒ 不读写用户 %LOCALAPPDATA%\Memoria\config
#   · 端口被占用时 **不杀** 已有进程（可能是用户正在用的 app），直接报错退出
#   · 只结束自己启动的那棵进程树
#
# 用法：pwsh -File run_probe.ps1 [-Port 9623] [-NodeExe <node.exe>]
param(
    [int]$Port = 9623,
    [string]$NodeExe = 'node'
)
$ErrorActionPreference = 'Stop'
$Here = $PSScriptRoot
$RepoRoot = $Here
1..5 | ForEach-Object { $RepoRoot = Split-Path $RepoRoot -Parent }   # artifacts/agent/verify/todo/<dir> -> repo
$KbDir = Join-Path $Here 'kb'
$ConfigDir = Join-Path $Here 'config'
$OutJson = Join-Path $Here 'verify.json'

if (-not (Test-Path (Join-Path $KbDir '.memoria\manifest.yaml'))) { throw "缺 fixture KB：$KbDir（先运行 make_fixture.py）" }

# 每次跑之前清空隔离用户态（否则上次会话被 restore ⇒ 初始状态不确定，"无会话时应显示未知"这条会随历史漂移）
if (-not (Test-Path $ConfigDir)) { New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null }
Get-ChildItem $ConfigDir -Force | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue


$busy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($busy) { throw "端口 $Port 已被占用（pid $($busy.OwningProcess)）——不自动清理，请换端口重跑（可能是用户正在用的 app）" }

$env:MEMORIA_MODE = 'dev'
$env:MEMORIA_FRAMELESS = '0'
$env:MEMORIA_KB = (Resolve-Path $KbDir).Path
$env:MEMORIA_CONFIG_DIR = (Resolve-Path $ConfigDir).Path
$env:MEMORIA_PROBE_CDP_PORT = "$Port"   # launch_with_cdp.py 用它设置 pywebview 的 REMOTE_DEBUGGING_PORT

$stdout = Join-Path $env:TEMP "task183_probe_$Port.out"
$stderr = Join-Path $env:TEMP "task183_probe_$Port.err"
$python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = 'python' }

$appPid = $null
$exit = 1
try {
    Write-Host "[run_probe] 启动应用：$python launch_with_cdp.py（KB=$env:MEMORIA_KB, CDP=$Port）"
    $p = Start-Process -FilePath $python -ArgumentList (Join-Path $Here 'launch_with_cdp.py') -WorkingDirectory $RepoRoot -PassThru `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $appPid = $p.Id

    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 700
        try {
            $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "http://127.0.0.1:$Port/json/version" -ErrorAction Stop
            if ($r.Content -match 'webSocketDebuggerUrl') { $ready = $true; break }
        } catch { }
    }
    if (-not $ready) {
        throw "[run_probe] CDP 端口 $Port 未就绪；stderr 尾部：`n$(Get-Content $stderr -Tail 20 -ErrorAction SilentlyContinue | Out-String)"
    }
    Write-Host "[run_probe] CDP 就绪，跑 probe.mjs ..."
    & $NodeExe (Join-Path $Here 'probe.mjs') --port $Port --out $OutJson
    $exit = $LASTEXITCODE
    Write-Host "[run_probe] probe exit=$exit；产物：$OutJson"
} finally {
    if ($appPid) {
        Write-Host "[run_probe] 关闭本次启动的进程树 pid=$appPid"
        & taskkill.exe /T /F /PID $appPid 2>$null | Out-Null
        Start-Sleep -Milliseconds 800
    }
    Remove-Item Env:\MEMORIA_MODE, Env:\MEMORIA_FRAMELESS, Env:\MEMORIA_KB, Env:\MEMORIA_CONFIG_DIR, Env:\MEMORIA_PROBE_CDP_PORT -ErrorAction SilentlyContinue
}
exit $exit
