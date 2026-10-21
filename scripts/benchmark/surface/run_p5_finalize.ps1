# run_p5_finalize.ps1 —— P5 矩阵一次定案（task-33）
#
# 前提（脚本会先自检，不满足就拒跑）：
#   1. `git status --porcelain -- src/` 必须干净  —— 否则又是跨代码版本混跑（本轮最大教训）
#   2. HEAD 必须与 -ExpectSha 一致（若给了）
#
# 做法：在固定 commit 上跑 13 文档 dual（同会话 legacy→new），再用官方 comparator 判定。
# 产出：定案用的 legacy/new JSON + comparator 输出 + 块数哨兵表。
param(
    [string]$Kb = 'artifacts\_p5_matrix_kb',
    [string]$Label = 'p5final',
    [int]$ReadyTimeout = 300000,
    [string]$ExpectSha = ''
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
Set-Location $RepoRoot

$Sha = (& git rev-parse --short HEAD).Trim()
Write-Host "[finalize] HEAD = $Sha"

# ── 硬前提 1：src/** 必须干净 ──
$dirty = @(& git status --porcelain -- src/ | Where-Object { $_ -notmatch 'ask_stream|index\.html' })
if ($dirty.Count -gt 0) {
    Write-Host "[finalize] 🔴 拒跑：src/** 有未提交改动（这会导致跨代码版本混跑，见报告 §9）"
    $dirty | ForEach-Object { Write-Host "    $_" }
    Write-Host "[finalize] 请先让 surface-new 提交，再重跑本脚本。"
    exit 3
}
Write-Host "[finalize] ✓ src/** 干净"

# ── 硬前提 2：HEAD 符合预期 ──
if ($ExpectSha -and $Sha -ne $ExpectSha) {
    Write-Host "[finalize] 🔴 拒跑：HEAD=$Sha，期望 $ExpectSha"
    exit 3
}

# ── 硬前提 3：冻结 KB 必须是 _p5_matrix_kb 那一份（Lead 裁决 ③）──
#   !! 教训：`tests/probe-kb/scale/scale-5k.md` 工作区被别的 agent 变异污染
#      （98573 字节、**末尾无 \n**），而 git HEAD / 冻结 KB 是 92760 字节、**末尾有 \n**。
#      文件尾那个 \n 会让 parser 多产 1 个 blank 块 ⇒ 喂错 KB 就会得到 3110 vs 3111 的假 diff。
#      故这里把 KB 身份钉死：sha256 + 末尾字节双重校验，不符即拒跑。
$ExpectedKbSha = 'a626b6961576bf6d'
$KbProbe = Join-Path $RepoRoot (Join-Path $Kb 'scale\scale-5k.md')
if (-not (Test-Path $KbProbe)) {
    Write-Host "[finalize] 🔴 拒跑：冻结 KB 缺 scale-5k.md（$KbProbe）"
    exit 3
}
$kbHash = (Get-FileHash $KbProbe -Algorithm SHA256).Hash.ToLower()
$kbBytes = [System.IO.File]::ReadAllBytes($KbProbe)
$kbLen = $kbBytes.Length
$kbLastByte = if ($kbLen -gt 0) { $kbBytes[$kbLen - 1] } else { -1 }
Write-Host "[finalize] KB scale-5k.md: sha256=$($kbHash.Substring(0,16)) bytes=$kbLen lastByte=$kbLastByte"

if (-not $kbHash.StartsWith($ExpectedKbSha)) {
    Write-Host "[finalize] 🔴 拒跑：冻结 KB sha256 不是 $ExpectedKbSha...（实际 $($kbHash.Substring(0,16))）"
    Write-Host "[finalize]   请重建冻结 KB：python scripts/benchmark/surface/make_p5_matrix_kb.py"
    exit 3
}
if ($kbLastByte -ne 10) {
    Write-Host "[finalize] 🔴 拒跑：冻结 KB 末尾字节=$kbLastByte，期望 10（\n）"
    Write-Host "[finalize]   文件尾缺 \n 会让 parser 少产 1 个 blank 块 ⇒ 假 diff"
    exit 3
}
Write-Host "[finalize] ✓ 冻结 KB 身份校验通过（sha256 + 末尾 \n）"

$Files = 'scale/scale-5k.md,scale/scale-1k.md,scale/scale-10k.md,corpus/01-ime-zh.md,corpus/02-inline-edges.md,corpus/03-block-boundaries.md,corpus/04-non-editable.md,corpus/05-images.md,corpus/06-links-and-kp.md,corpus/07-extremes.md,README.md,docs/error_log_format.md,docs/ref/ppt/ocr.md'

Write-Host "[finalize] 跑 13 文档 dual（同会话）..."
& powershell -File (Join-Path $PSScriptRoot '..\..\..\artifacts\agent\verify\p2c_session.ps1') `
    -Kb $Kb -Label $Label -Files $Files -ReadyTimeout $ReadyTimeout 2>&1 |
    Select-String 'p2c|DONE|port' | ForEach-Object { Write-Host "  $($_.Line)" }

if ($LASTEXITCODE -ne 0) {
    Write-Host "[finalize] 🔴 dual 跑失败（exit=$LASTEXITCODE）"
    exit 4
}

$Legacy = Join-Path $RepoRoot "scripts\benchmark\surface\results\fidelity-p2c-$Label-legacy-$Sha.json"
$NewLegacy = Join-Path $RepoRoot "scripts\benchmark\surface\results\fidelity-p2c-$Label-newlegacy-$Sha.json"
$New = Join-Path $RepoRoot "scripts\benchmark\surface\results\fidelity-p2c-$Label-new-$Sha.json"
$CmpOut = Join-Path $RepoRoot 'scripts\benchmark\surface\results\compare-p5-final.json'

Write-Host "[finalize] comparator（默认 12 kind 全集；对比对象 = newlegacy vs new，同会话同状态）..."
Write-Host "[finalize]   注意：不用 -legacy（那是 fidelity_cli 独立批，会触发 S13 编辑器回读剥尾 \\n，不可靠）"
if (-not (Test-Path $NewLegacy)) {
    Write-Host "[finalize] 🔴 缺 -newlegacy（同会话 legacy），可能是 p2c_session 未生成；中止"
    exit 4
}
& node (Join-Path $PSScriptRoot 'compare_signatures.mjs') --baseline $NewLegacy --current $New --out $CmpOut
$cmpExit = $LASTEXITCODE
Write-Host "[finalize] comparator exit=$cmpExit（0=PASS）"

# ── 判定：必须 13/13 全绿 + unsupported=0 ──
$json = Get-Content $CmpOut -Raw -Encoding UTF8 | ConvertFrom-Json
$t = $json.totals
Write-Host ""
Write-Host "[finalize] totals: match=$($t.match) diff=$($t.diff) unsupported=$($t.unsupported) missing=$($t.missing) schema_error=$($t.schema_error)"

# ⚠️ 坑（2026-10-21 实测）：`compare_signatures.mjs` 的 totals **不含 `schema_error` 键**
#   ⇒ `$t.schema_error` 取到 `$null`，而 PowerShell 的 `$null -eq 0` 是 **False**
#   ⇒ 即使 diff/unsupported/missing 全 0，`$allPass` 恒为 False，脚本永远报"未达标"。
#   这是**假红**（与"假绿"同族的判定错误），已按"缺失即视为 0 但必须显式打印"修正：
#   显式取键并给默认值 0，同时把最终判据打印出来，避免再次误读。
function _Num($v) { if ($null -eq $v) { return 0 } return [int]$v }
$nDiff = _Num $t.diff
$nUnsupported = _Num $t.unsupported
$nMissing = _Num $t.missing
$nSchemaError = _Num $t.schema_error
$allPass = ($nDiff -eq 0 -and $nUnsupported -eq 0 -and $nMissing -eq 0 -and $nSchemaError -eq 0)
Write-Host "[finalize] 判据: diff=$nDiff unsupported=$nUnsupported missing=$nMissing schema_error=$nSchemaError => allPass=$allPass"
Write-Host ""
if ($allPass) {
    Write-Host "[finalize] ✅ 13/13 全绿 + unsupported=0 —— 可以正式冻结 S_render_frozen"
    exit 0
} else {
    Write-Host "[finalize] 🔴 未达标，不可冻结"
    exit 1
}
