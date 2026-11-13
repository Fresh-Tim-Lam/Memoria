param(
    [Parameter(Mandatory = $true)][string]$JobFile
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Write-Log([string]$Message) {
    try {
        $dir = Split-Path -Parent $script:Job.result_path
        if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
        Add-Content -LiteralPath $script:LogPath -Encoding UTF8 -Value ("{0} {1}" -f (Get-Date -Format "o"), $Message)
    } catch { }
}

function Write-Result([string]$Status, [string]$Reason, [bool]$RolledBack) {
    $payload = [ordered]@{
        status      = $Status
        reason      = $Reason
        rolled_back = $RolledBack
        from_version = $script:Job.from_version
        to_version   = $script:Job.to_version
        backup_dir   = $script:Job.backup_dir
        log_path     = $script:LogPath
        finished_at  = (Get-Date -Format "o")
    }
    try {
        $tmp = $script:Job.result_path + ".tmp"
        $json = ($payload | ConvertTo-Json -Depth 4)
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($tmp, $json, $utf8NoBom)
        Move-Item -LiteralPath $tmp -Destination $script:Job.result_path -Force
    } catch { }
}

$script:Job = Get-Content -LiteralPath $JobFile -Raw -Encoding UTF8 | ConvertFrom-Json
$script:LogPath = [string]$script:Job.log_path
$staging = $null
$swapped = $false
$started = $false

try {
    Write-Log ("start job={0} parent={1} target={2} variant={3}" -f $script:Job.job_id, $script:Job.parent_pid, $script:Job.target_dir, $script:Job.variant)

    # 1) wait for Memoria to release its own files
    $deadline = (Get-Date).AddSeconds(90)
    while ($true) {
        $parent = Get-Process -Id ([int]$script:Job.parent_pid) -ErrorAction SilentlyContinue
        if (-not $parent) { break }
        if ((Get-Date) -gt $deadline) { throw "parent-timeout: Memoria still running after 90s" }
        Start-Sleep -Milliseconds 250
    }
    Write-Log "parent exited"

    # 2) re-verify final zip (the downloader already verified the .part)
    $actual = (Get-FileHash -LiteralPath ([string]$script:Job.zip_path) -Algorithm SHA256).Hash.ToLowerInvariant()
    $expected = ([string]$script:Job.sha256).ToLowerInvariant()
    if (-not $expected -or $actual -ne $expected) {
        throw "sha256-mismatch: expected=$expected actual=$actual"
    }
    Write-Log "sha256 ok"

    # 3) extract into a sibling staging directory (same volume => atomic directory move)
    $targetParent = Split-Path -Parent ([string]$script:Job.target_dir)
    $targetLeaf = Split-Path -Leaf ([string]$script:Job.target_dir)
    $staging = Join-Path $targetParent (".{0}.staging-{1}" -f $targetLeaf, [guid]::NewGuid().ToString("N"))
    if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $staging | Out-Null
    Expand-Archive -LiteralPath ([string]$script:Job.zip_path) -DestinationPath $staging -Force
    Write-Log "extracted to $staging"

    $stagedExe = Join-Path $staging ([string]$script:Job.exe_name)
    $stagedVersionFile = Join-Path $staging "VERSION"
    if (-not (Test-Path -LiteralPath $stagedExe)) { throw "staging-missing-exe" }
    if (-not (Test-Path -LiteralPath $stagedVersionFile)) { throw "staging-missing-version" }
    $stagedVersion = (Get-Content -LiteralPath $stagedVersionFile -Raw -Encoding UTF8).Trim()
    if ($stagedVersion -ne [string]$script:Job.to_version) {
        throw "version-mismatch: staged=$stagedVersion expected=$($script:Job.to_version)"
    }
    Write-Log "staged version=$stagedVersion"

    # 4) preserve local app config (release zip deliberately strips private config)
    $oldConfig = Join-Path ([string]$script:Job.target_dir) "config"
    if (Test-Path -LiteralPath $oldConfig) {
        $newConfig = Join-Path $staging "config"
        if (-not (Test-Path -LiteralPath $newConfig)) { New-Item -ItemType Directory -Force -Path $newConfig | Out-Null }
        Get-ChildItem -LiteralPath $oldConfig -Force | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $newConfig -Recurse -Force
        }
        Write-Log "preserved config"
    }

    # 5) rename old app dir -> backup, staging -> app dir
    $backup = [string]$script:Job.backup_dir
    if (Test-Path -LiteralPath $backup) { throw "backup-exists: $backup" }
    [System.IO.Directory]::Move([string]$script:Job.target_dir, $backup)
    $swapped = $true
    Write-Log "old app moved to backup"

    [System.IO.Directory]::Move($staging, [string]$script:Job.target_dir)
    $staging = $null
    Write-Log "new app activated"

    # 6) lite package has no hf/: keep the installed models
    if ([string]$script:Job.variant -eq "lite") {
        $oldHf = Join-Path $backup "hf"
        if (Test-Path -LiteralPath $oldHf) {
            $newHf = Join-Path ([string]$script:Job.target_dir) "hf"
            if (Test-Path -LiteralPath $newHf) { Remove-Item -LiteralPath $newHf -Recurse -Force }
            [System.IO.Directory]::Move($oldHf, $newHf)
            Write-Log "preserved hf/"
        }
    }

    # 7) start new build and record success
    $newExe = Join-Path ([string]$script:Job.target_dir) ([string]$script:Job.exe_name)
    Start-Process -FilePath $newExe -WorkingDirectory ([string]$script:Job.target_dir)
    $started = $true
    Write-Log "new app started"
    Write-Result "success" "" $false
    exit 0
}
catch {
    $reason = $_.Exception.Message
    Write-Log ("FAILED: {0}" -f $reason)
    $rolledBack = $false
    try {
        if ($swapped) {
            $target = [string]$script:Job.target_dir
            $backup = [string]$script:Job.backup_dir
            if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
            if (Test-Path -LiteralPath $backup) {
                [System.IO.Directory]::Move($backup, $target)
                $rolledBack = $true
                Write-Log "rolled back from backup"
            }
        }
    } catch {
        Write-Log ("ROLLBACK FAILED: {0}" -f $_.Exception.Message)
    }
    if ($staging -and (Test-Path -LiteralPath $staging)) {
        try { Remove-Item -LiteralPath $staging -Recurse -Force } catch { }
    }
    Write-Result "failed" $reason $rolledBack
    exit 1
}
