param([string]$Out = "$env:TEMP\memoria_clipboard.txt")
# 剪贴板读回助手：WriteAllText(UTF8, 无 BOM) 避免 PowerShell 控制台编码把中文弄坏。
$c = Get-Clipboard -Raw
if ($null -eq $c) { $c = "" }
[System.IO.File]::WriteAllText($Out, [string]$c, (New-Object System.Text.UTF8Encoding($false)))
Write-Output ("WROTE len=" + ([string]$c).Length)
