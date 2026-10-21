<#
.SYNOPSIS
    配置隔离助手（PowerShell 版）—— 测试密封性（task-54）。

.DESCRIPTION
    与 `_iso_config.py` 同一契约：**默认隔离**，每次 run 创建唯一的**空**配置目录并设
    `MEMORIA_CONFIG_DIR` 指向它，使应用不读开发机 `config/ui-settings.json`。

    ★ 事故背景（task-53）★
    开发机 `config/ui-settings.json` 里 `search.embedding_enabled=true`。真机/无头
    测量脚本隐式继承该文件 ⇒ 搜索会在单线程 harness 内同步构建 embedding 索引
    （BERT 编码数百段），阻塞 >45s，导致 S11 稳定假红。同类泄漏也可能污染冻结基线。

.PARAMETER Script
    脚本标识，用于配置目录命名（如 'run_domwrites'）。
.PARAMETER Label
    本次 run 的 label。
.PARAMETER Ambient
    诊断开关：不隔离，继承开发机配置（仅用于自证判别力）。
.PARAMETER Keep
    是否保留空配置目录（默认 $true，供诊断）。

.OUTPUTS
    [hashtable] @{ Isolated; Ambient; ConfigDir; Keep; Describe() }
#>

function Initialize-MemoriaConfigIsolation {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Script,
        [string]$Label = 'run',
        [switch]$Ambient,
        [bool]$Keep = $true
    )

    # 仓库根：本文件位于 scripts/benchmark/surface/
    $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
    $configEnvVars = @('MEMORIA_CONFIG_DIR', 'MEMORIA_UI_SETTINGS')

    # 记录原值，便于恢复
    $previous = @{}
    foreach ($k in $configEnvVars) { $previous[$k] = [Environment]::GetEnvironmentVariable($k, 'Process') }

    if ($Ambient) {
        # 诊断模式：清掉外层可能设的隔离变量，确保"真的 ambient"
        foreach ($k in $configEnvVars) { [Environment]::SetEnvironmentVariable($k, $null, 'Process') }
        Write-Host "[iso] DIAG: ambient 配置（不隔离）—— 会继承开发机 ui-settings.json"
        return @{
            Isolated  = $false
            Ambient   = $true
            ConfigDir = $null
            Keep      = $Keep
            Previous  = $previous
            Describe  = 'DIAG ambient（不隔离）'
        }
    }

    # 唯一空目录：artifacts/_<script>_config_<label>_<pid>_<random>
    $artifacts = Join-Path $repoRoot 'artifacts'
    if (-not (Test-Path $artifacts)) { New-Item -ItemType Directory -Path $artifacts -Force | Out-Null }
    $safeLabel = ($Label -replace '[^A-Za-z0-9\-_.]', '_')
    if ($safeLabel.Length -gt 40) { $safeLabel = $safeLabel.Substring(0, 40) }
    $rand = [System.IO.Path]::GetRandomFileName().Split('.')[0]
    $cfgDir = Join-Path $artifacts ("_{0}_config_{1}_{2}_{3}" -f $Script, $safeLabel, $PID, $rand)
    New-Item -ItemType Directory -Path $cfgDir -Force | Out-Null

    $env:MEMORIA_CONFIG_DIR = $cfgDir
    Remove-Item Env:\MEMORIA_UI_SETTINGS -ErrorAction SilentlyContinue

    Write-Host "[iso] 密封配置目录: $cfgDir"

    return @{
        Isolated  = $true
        Ambient   = $false
        ConfigDir = $cfgDir
        Keep      = $Keep
        Previous  = $previous
        Describe  = "密封配置目录: $cfgDir"
    }
}

<#
.SYNOPSIS
    写入产物的密封性元数据。
#>
function Get-MemoriaConfigIsolationManifest {
    param([Parameter(Mandatory)][hashtable]$Isolation)

    $dirEmpty = $null
    if ($Isolation.ConfigDir) {
        $items = @(Get-ChildItem -LiteralPath $Isolation.ConfigDir -ErrorAction SilentlyContinue)
        $dirEmpty = ($items.Count -eq 0)
    }
    return @{
        isolated         = [bool]$Isolation.Isolated
        ambient          = [bool]$Isolation.Ambient
        config_dir       = $Isolation.ConfigDir
        config_env       = @{
            MEMORIA_CONFIG_DIR   = $env:MEMORIA_CONFIG_DIR
            MEMORIA_UI_SETTINGS  = $env:MEMORIA_UI_SETTINGS
        }
        keep             = [bool]$Isolation.Keep
        config_dir_empty = $dirEmpty
    }
}

<#
.SYNOPSIS
    清理（按 Keep 策略）并恢复原环境变量。
#>
function Clear-MemoriaConfigIsolation {
    param([Parameter(Mandatory)][hashtable]$Isolation)

    # 恢复环境变量
    foreach ($k in $Isolation.Previous.Keys) {
        [Environment]::SetEnvironmentVariable($k, $Isolation.Previous[$k], 'Process')
    }
    if ($Isolation.Keep -or -not $Isolation.ConfigDir) { return }
    Remove-Item -LiteralPath $Isolation.ConfigDir -Recurse -Force -ErrorAction SilentlyContinue
}

<#
.SYNOPSIS
    给脚本加 `-AmbientConfig` 开关的帮助文本（各脚本自行声明 param）。
#>
function Get-MemoriaAmbientConfigHelp {
    return 'DIAG：不设 MEMORIA_CONFIG_DIR，继承开发机 config/ui-settings.json（仅诊断；默认隔离）'
}

Export-ModuleMember -Function @(
    'Initialize-MemoriaConfigIsolation',
    'Get-MemoriaConfigIsolationManifest',
    'Clear-MemoriaConfigIsolation',
    'Get-MemoriaAmbientConfigHelp'
)
