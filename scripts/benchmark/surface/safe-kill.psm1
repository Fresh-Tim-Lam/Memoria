<#
.SYNOPSIS
    安全终止模块 —— 消除"误杀用户 app"类事故的统一入口。

.DESCRIPTION
    ★ 背景（2026-10-21 真实事故）★
    测量脚本用 `taskkill /PID <x> /T /F` 清理自己的测量实例。`/T` 杀整棵进程树。
    更危险的是有脚本用 **端口反查 PID**（`$c.OwningProcess`）再杀 —— 若端口恰好被
    用户手动打开的 `Package\Memoria.exe` 占用，就会**必然误杀用户的应用**。
    事故现象：用户 app pid 21860 消失，后于 19:38:01 重启为 39868，再次于 19:49:01 重启为 49444。

    ★ 本模块的三条铁律 ★
    ① 只杀**本次脚本自己启动**的 PID（调用方传入的 $AppPid），不凭端口反查。
    ② 杀前**校验身份**：该 PID 的命令行必须含本次使用的调试端口号；不含 ⇒ 拒绝杀 + 警告。
    ③ 绝不用 `/T`（杀整棵树）；也绝不杀 `Package\Memoria.exe`（用户的应用）。

    需要清理 WebView2 子进程时，用 `Stop-OrphanWebView2 -Marker` 按**唯一标记**精确匹配，
    而不是按端口反查父进程。

.NOTES
    作者：metrics-baseline（task-49）
    对应教训：task-47/48 期间两次误杀用户 app。
#>

# 用户生产应用的进程名/路径特征 —— 任何情况下都不许杀
$script:ProtectedProcessNames = @('Memoria')
$script:ProtectedPathPattern   = '*\Package\Memoria.exe'

<#
.SYNOPSIS
    判断一个 PID 是否指向受保护的用户应用。
.OUTPUTS
    [bool] $true = 受保护，禁止杀。
#>
function Test-ProtectedProcess {
    param([Parameter(Mandatory)][int]$ProcessId)

    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
    if (-not $proc) { return $false }   # 进程不存在 ⇒ 无所谓

    if ($script:ProtectedProcessNames -contains $proc.Name) { return $true }
    if ($proc.ExecutablePath -and ($proc.ExecutablePath -like $script:ProtectedPathPattern)) { return $true }
    return $false
}

<#
.SYNOPSIS
    安全终止一个由本脚本启动的进程。
.DESCRIPTION
    校验顺序：存在性 → 受保护身份 → 命令行含调试端口 → 才杀（不带 /T）。
.PARAMETER ProcessId
    要终止的 PID。调用方应传入自己 `Start-Process` 得到的 `$p.Id`。
.PARAMETER ExpectedPort
    本次测量使用的 CDP 调试端口。该 PID 的命令行必须含此端口号才允许杀。
.PARAMETER WhatIf
    只打印"将杀哪些 PID + 身份校验结果"，不实际终止。
.PARAMETER Quiet
    不输出例行日志（告警仍会输出）。
.OUTPUTS
    [hashtable] @{ Killed=[bool]; Reason=[string]; Pid=[int] }
#>
function Stop-MeasurementProcess {
    # SupportsShouldProcess 已内置 -WhatIf，勿重复声明
    [CmdletBinding(SupportsShouldProcess = $true)]
    param(
        [Parameter(Mandatory)][int]$ProcessId,
        [int]$ExpectedPort = 0,
        [switch]$Quiet
    )

    $result = @{ Killed = $false; Reason = ''; Pid = $ProcessId }

    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
    if (-not $proc) {
        $result.Reason = 'not-running'
        if (-not $Quiet) { Write-Host "[safe-kill] pid $ProcessId 已不存在，无需清理" }
        return $result
    }

    # ① 受保护身份校验（最高优先级）
    if (Test-ProtectedProcess -ProcessId $ProcessId) {
        $result.Reason = 'PROTECTED'
        Write-Warning "[safe-kill] ⛔ 拒绝终止 pid $ProcessId —— 这是用户的应用（$($proc.Name) / $($proc.ExecutablePath)）"
        return $result
    }

    # ② 命令行必须含本次调试端口（证明是"我启动的那个"）
    $cmdline = [string]$proc.CommandLine
    if ($ExpectedPort -gt 0) {
        if ($cmdline -notmatch "(^|\s|--remote-debugging-port=)(?<![\d])$ExpectedPort(?![\d])") {
            $result.Reason = 'port-mismatch'
            Write-Warning ("[safe-kill] ⛔ 拒绝终止 pid $ProcessId —— 命令行不含调试端口 $ExpectedPort，" +
                           "不是本次测量实例。cmd=$($cmdline.Substring(0,[Math]::Min(120,$cmdline.Length)))")
            return $result
        }
    }

    # ③ 执行（绝不带 /T）
    if ($WhatIfPreference) {
        Write-Host "[safe-kill] DRY-RUN: 将终止 pid $ProcessId（身份校验通过：port=$ExpectedPort, name=$($proc.Name)）"
        $result.Reason = 'whatif'
        return $result
    }

    if ($PSCmdlet.ShouldProcess("pid $ProcessId ($($proc.Name))", 'Stop-Process')) {
        try {
            # ★ 不带 /T：只杀这一个进程，不波及子孙/兄弟（child/WebView2 由调用方按标记单独清理）
            & taskkill.exe /PID $ProcessId /F *>&1 | Out-Null
            $result.Killed = $true
            $result.Reason = 'killed'
            if (-not $Quiet) { Write-Host "[safe-kill] killed pid $ProcessId（不含 /T）" }
        } catch {
            $result.Reason = "kill-error: $($_.Exception.Message)"
            Write-Warning "[safe-kill] 终止 pid $ProcessId 失败：$($_.Exception.Message)"
        }
    }
    return $result
}

<#
.SYNOPSIS
    按唯一标记清理孤儿 WebView2 进程（替代"端口反查父进程"）。
.DESCRIPTION
    只杀命令行里含 $Marker 的 `msedgewebview2` 进程。$Marker 应是本次运行独有的
    临时 user-data-dir 片段（如 `EBWebView` 下的随机目录名），不是端口号。
.PARAMETER Marker
    必须出现的命令行片段。为空 ⇒ 直接拒绝（防止误杀全部 WebView2）。
.PARAMETER WhatIf
    只打印将杀哪些 PID。
#>
function Stop-OrphanWebView2 {
    [CmdletBinding(SupportsShouldProcess = $true)]
    param(
        [Parameter(Mandatory)][string]$Marker
    )

    if ([string]::IsNullOrWhiteSpace($Marker)) {
        Write-Warning '[safe-kill] ⛔ Stop-OrphanWebView2 需要非空 Marker，拒绝执行（防止误杀全部 WebView2）'
        return @()
    }

    $targets = @(Get-CimInstance Win32_Process -Filter "Name='msedgewebview2.exe'" -ErrorAction SilentlyContinue |
                 Where-Object { $_.CommandLine -like "*$Marker*" })

    if (-not $targets.Count) { return @() }

    $killed = @()
    foreach ($t in $targets) {
        if ($WhatIfPreference) {
            Write-Host "[safe-kill] DRY-RUN: 将终止孤儿 WebView2 pid $($t.ProcessId)（marker=$Marker）"
            continue
        }
        if ($PSCmdlet.ShouldProcess("pid $($t.ProcessId)", 'Stop-Process')) {
            try {
                & taskkill.exe /PID $t.ProcessId /F *>&1 | Out-Null   # 不带 /T
                $killed += $t.ProcessId
            } catch { }
        }
    }
    if ($killed.Count) { Write-Host "[safe-kill] 清理孤儿 WebView2: $($killed -join ',')" }
    return $killed
}

<#
.SYNOPSIS
    端口被占用时**只报告、不杀**（替代原 `$c.OwningProcess` + taskkill 路径）。
.DESCRIPTION
    原来的危险做法是"端口被占 ⇒ 反查 PID ⇒ 杀掉"。这会误杀用户应用。
    新做法：报告占用者身份 + 建议（换端口 / 手动确认），**永不自动终止**。
.PARAMETER Port
    要检查的端口。
.OUTPUTS
    [hashtable] @{ Free=[bool]; OwningProcess=[int]; Identity=[string]; Advice=[string] }
#>
function Get-PortOwnerSafe {
    param([Parameter(Mandatory)][int]$Port)

    $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $c) {
        return @{ Free = $true; OwningProcess = 0; Identity = ''; Advice = '' }
    }

    $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($c.OwningProcess)" -ErrorAction SilentlyContinue
    $name = if ($owner) { $owner.Name } else { '<unknown>' }
    $cmd  = if ($owner) { [string]$owner.CommandLine } else { '' }
    $isProtected = Test-ProtectedProcess -ProcessId $c.OwningProcess

    $identity = "$name pid=$($c.OwningProcess)"
    if ($isProtected) { $identity += ' [★ 用户应用，绝对不可杀]' }

    # ★ 关键：不论占用者是谁，都**不自动终止**。只给建议。
    $advice = if ($isProtected) {
        "该端口被用户的应用占用（$identity）。请改用其它端口（例如 -ExportPort/-Port 换一个空闲端口），不要终止用户应用。"
    } else {
        "端口被 $identity 占用。本脚本不会自动终止它（防误杀）。如需清理请人工确认后手动执行：taskkill /PID $($c.OwningProcess) /F"
    }

    Write-Warning "[safe-kill] 端口 $Port 被占用：$identity"
    Write-Warning "[safe-kill] $advice"

    return @{ Free = $false; OwningProcess = $c.OwningProcess; Identity = $identity; Advice = $advice }
}

<#
.SYNOPSIS
    模块自检：证明不会选中用户进程。
.DESCRIPTION
    扫描当前所有监听中的常见调试端口 + 用户 app 进程，打印"如果调用安全终止会怎样"。
    用于 task-49 的自证要求。
#>
function Invoke-SafeKillSelfCheck {
    param([int[]]$Ports = @())

    Write-Host ''
    Write-Host '════ 安全终止模块自检 ════'

    # ① 用户应用进程
    $userApps = @(Get-CimInstance Win32_Process -Filter "Name='Memoria.exe'" -ErrorAction SilentlyContinue)
    Write-Host "[自检] 检测到用户应用进程 $($userApps.Count) 个："
    foreach ($u in $userApps) {
        $protected = Test-ProtectedProcess -ProcessId $u.ProcessId
        Write-Host ("  pid={0,-6} name={1} protected={2} path={3}" -f $u.ProcessId, $u.Name, $protected, $u.ExecutablePath)
        if (-not $protected) { Write-Warning "  ⚠️ pid $($u.ProcessId) 未被识别为受保护，请检查规则！" }
    }

    # ② 对每个用户应用 PID 模拟"误传"场景
    Write-Host "[自检] 模拟：若脚本误把用户 app 的 PID 传给 Stop-MeasurementProcess 会怎样？"
    foreach ($u in $userApps) {
        $r = Stop-MeasurementProcess -ProcessId $u.ProcessId -ExpectedPort 9999 -WhatIf -Quiet -ErrorAction SilentlyContinue
        $ok = ($r.Reason -eq 'PROTECTED')
        Write-Host ("  pid={0,-6} => verdict={1} {2}" -f $u.ProcessId, $r.Reason, $(if ($ok) { '✅ 已被拒绝' } else { '❌ 未拦截！' }))
    }

    # ③ 端口占用者
    if ($Ports.Count) {
        Write-Host '[自检] 端口占用者身份（仅报告，不杀）：'
        foreach ($p in $Ports) {
            $r = Get-PortOwnerSafe -Port $p
            if ($r.Free) { Write-Host "  port $p : 空闲" }
        }
    }

    Write-Host '════ 自检结束 ════'
    Write-Host ''
}

Export-ModuleMember -Function @(
    'Test-ProtectedProcess',
    'Stop-MeasurementProcess',
    'Stop-OrphanWebView2',
    'Get-PortOwnerSafe',
    'Invoke-SafeKillSelfCheck'
)
