<#
.SYNOPSIS
    KB 守卫接线助手（PowerShell 版）—— 供 5 个 .ps1 真机脚本统一调用（task-57 · L6）。

.DESCRIPTION
    ⚠️ 设计要点（避免 task-55 踩过的两个坑）：
      ① **冻结语料 ≠ 测量 KB**：冻结语料一律取自独立变量 `P5PERF_FROZEN_KB`
         （默认 `artifacts/_p5_matrix_kb`），与脚本实际用的 `MEMORIA_KB` 彻底分离。
         坑：曾把 FROZEN_KB_DIR 设为 MEMORIA_KB，而运行时 MEMORIA_KB 指向副本
             ⇒ 守卫盯着副本 ⇒ 副本被写 ⇒ **假红**（"内红外绿"）。
      ② **前快照必须唯一**：写到随机临时目录，避免被上一轮 run 覆盖 ⇒ 假红。

    用法（只读脚本）：
        . "$PSScriptRoot\_kb_guard_wire.ps1"
        $G = Start-KbGuard -Script 'run_ready_selfcheck' -Label $Label
        ...  # 跑测量
        Complete-KbGuard -Guard $G          # 不一致 ⇒ throw（脚本非 0）

    用法（可能写 KB 的脚本）：
        $G = Start-KbGuard -Script 'run_domwrites' -Label $Label -Writable
        $WorkKb = New-KbMeasureCopy -Guard $G      # 副本；打印路径
        $env:MEMORIA_KB = $WorkKb                  # 测量跑在副本上
        ...
        Complete-KbGuard -Guard $G                 # 校验冻结语料（应始终绿）

.NOTES
    本文件**必须**以 UTF-8 with BOM 保存：Windows PowerShell 5.1 会把无 BOM 的
    UTF-8 当 ANSI 读 ⇒ 中文注释变乱码 ⇒ 语法错误（task-49 踩过）。
#>

function Get-MemoriaFrozenKbDir {
    <#
    .SYNOPSIS
        解析冻结语料目录（只用 $env:P5PERF_FROZEN_KB，**绝不**回退到 $env:MEMORIA_KB）。
    #>
    $p = Join-Path $PSScriptRoot '..\..\..'
    $repoRoot = (Resolve-Path $p).Path
    $raw = $env:P5PERF_FROZEN_KB
    if ([string]::IsNullOrWhiteSpace($raw)) { $raw = 'artifacts/_p5_matrix_kb' }
    if ([System.IO.Path]::IsPathRooted($raw)) { return (Resolve-Path $raw).Path }
    return (Resolve-Path (Join-Path $repoRoot $raw)).Path
}

function Get-MemoriaGuardPy {
    return (Join-Path $PSScriptRoot '_kb_guard.py')
}

function Start-KbGuard {
    <#
    .SYNOPSIS
        建立前快照。冻结语料缺失 ⇒ throw（拒绝在无守卫下运行）。
    .PARAMETER Script
        脚本标识（用于快照目录命名）。
    .PARAMETER Label
        本次 run 的 label。
    .PARAMETER Writable
        该脚本**可能写 KB**（save/编辑类）⇒ 需配合 New-KbMeasureCopy 用副本。
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Script,
        [string]$Label = 'run',
        [switch]$Writable
    )

    $frozen = Get-MemoriaFrozenKbDir
    if (-not (Test-Path $frozen)) {
        throw "[kb-guard] ❌ 冻结语料目录不存在: $frozen（env P5PERF_FROZEN_KB）—— 拒绝在无守卫下运行测量"
    }

    $snapDir = Join-Path ([System.IO.Path]::GetTempPath()) ("_kbguard_{0}_{1}_{2}" -f $Script, $PID, [System.IO.Path]::GetRandomFileName().Split('.')[0])
    New-Item -ItemType Directory -Path $snapDir -Force | Out-Null
    $beforePath = Join-Path $snapDir 'before.json'

    $py = Get-MemoriaGuardPy
    & python -X utf8 $py --kb $frozen --claim --manifest $beforePath *>&1 | Out-Null
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $beforePath)) {
        throw "[kb-guard] ❌ 前快照失败（冻结语料: $frozen）"
    }

    $mode = if ($Writable) { '写类（测量跑副本）' } else { '只读' }
    Write-Host "[kb-guard] 冻结语料: $frozen"
    Write-Host "[kb-guard] 模式: $mode  快照目录: $snapDir"

    return @{
        Script     = $Script
        Label      = $Label
        Writable   = [bool]$Writable
        FrozenKb   = $frozen
        SnapDir    = $snapDir
        BeforePath = $beforePath
        WorkKb     = $null
    }
}

function New-KbMeasureCopy {
    <#
    .SYNOPSIS
        为**写类**脚本创建副本 KB，并把它设进 $env:MEMORIA_KB。
    .DESCRIPTION
        冻结语料只读；写类测试（save/编辑/粘贴/结构编辑）一律在副本上跑。
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][hashtable]$Guard)

    if (-not $Guard.Writable) {
        throw '[kb-guard] 只读脚本不应调用 New-KbMeasureCopy'
    }
    if (-not $Guard.WorkKb) {
        $py = Get-MemoriaGuardPy
        $code = @'
import sys
sys.path.insert(0, sys.argv[1])
from _kb_guard import make_work_copy
print(make_work_copy(sys.argv[2], label=sys.argv[3]))
'@
        $out = & python -X utf8 -c $code $PSScriptRoot $Guard.FrozenKb ("{0}_{1}" -f $Guard.Script, $Guard.Label)
        if ($LASTEXITCODE -ne 0) { throw '[kb-guard] ❌ 建副本失败' }
        $Guard.WorkKb = ($out | Select-Object -Last 1).ToString().Trim()
        $env:MEMORIA_KB = $Guard.WorkKb
        Write-Host "[kb-guard] 测量副本 KB: $($Guard.WorkKb)（冻结语料只读，写操作全在副本上）"
    }
    return $Guard.WorkKb
}

function Complete-KbGuard {
    <#
    .SYNOPSIS
        后校验**冻结语料**。不一致 ⇒ 判红点名；默认 throw 使脚本非 0。
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][hashtable]$Guard,
        [switch]$NoThrow
    )

    $py = Get-MemoriaGuardPy
    $resultPath = Join-Path $Guard.SnapDir 'result.json'
    $output = & python -X utf8 $py --kb $Guard.FrozenKb --verify $Guard.BeforePath 2>&1
    $code = $LASTEXITCODE

    if ($code -eq 0) {
        Write-Host "[kb-guard] ✅ 冻结语料未变（$($Guard.FrozenKb)）"
        $Guard | Add-Member -NotePropertyName Result -NotePropertyValue ([pscustomobject]@{ ok = $true; code = 0; detail = ($output -join "`n") }) -Force
        return $true
    }

    Write-Warning '[kb-guard] ❌ **红** —— 冻结语料被测试写入/删除：'
    foreach ($line in $output) { Write-Warning "  $line" }
    Write-Warning '[kb-guard] 这是**测试缺陷**：写类测试必须在副本上跑（New-KbMeasureCopy）。'
    $Guard | Add-Member -NotePropertyName Result -NotePropertyValue ([pscustomobject]@{ ok = $false; code = 1; detail = ($output -join "`n") }) -Force

    if (-not $NoThrow) { throw '[kb-guard] 判定红：冻结语料被写入（进程以非 0 退出）' }
    return $false
}

function Get-KbGuardManifest {
    <#
    .SYNOPSIS
        可落盘的守卫元数据（供报告/产物记录）。
    #>
    param([Parameter(Mandatory)][hashtable]$Guard)
    return @{
        enabled        = $true
        script         = $Guard.Script
        label          = $Guard.Label
        writable       = [bool]$Guard.Writable
        frozenKb       = $Guard.FrozenKb
        frozenKbEnv    = 'P5PERF_FROZEN_KB'
        beforeSnapshot = $Guard.BeforePath
        workKb         = $Guard.WorkKb
        snapshotDir    = $Guard.SnapDir
    }
}

# 本文件既被 `. <path>` dot-source（脚本用法），也可能被 Import-Module 加载。
# Export-ModuleMember 只在**模块内**合法，dot-source 时调用会报错 ⇒ 先判断。
if ($MyInvocation.MyCommand.ScriptBlock.Module) {
    Export-ModuleMember -Function @(
        'Get-MemoriaFrozenKbDir',
        'Start-KbGuard',
        'New-KbMeasureCopy',
        'Complete-KbGuard',
        'Get-KbGuardManifest'
    )
}
