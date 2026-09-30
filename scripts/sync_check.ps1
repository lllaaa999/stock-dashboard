# sync_check.ps1 - 单点校验哨兵 (2026-09-30 重写)
# 旧版职责: 比对 D:\hermes\... 两处硬链副本的 SHA256 —— 但 D:\hermes 已于 2026-08-17 被删除,
#           副本不存在, 旧哨兵只会输出 MISSING, 等于防分叉机制已死。
# 新版职责(单点权威):
#   1) 权威存档存在, 且 Hermes 侧不再长出第二份 sentiment_history.jsonl (已冻结为 .legacy)
#   2) 两个启动器都固化了 STOCK_DATA_HOME (否则收盘归档会写进 Hermes 目录 -> 分叉)
#   3) 打印权威存档条数, 便于和上游核对
# 用法: powershell -File scripts\sync_check.ps1 ; 退出码 = 问题数
param([switch]$Fix)   # -Fix 参数保留兼容, 新版无需修复动作
$ErrorActionPreference = 'Continue'
$root = 'D:\股票看盘'
$bad = 0

$proj = Join-Path $root 'data\stock_data\sentiment_history.jsonl'
$herm = Join-Path $env:LOCALAPPDATA 'hermes\stock_data\sentiment_history.jsonl'

if (-not (Test-Path $proj)) {
    Write-Warning "MISSING 权威存档: $proj"; $bad++
} else {
    $n = (Get-Content -LiteralPath $proj -Encoding UTF8 | Where-Object { $_.Trim() -ne '' }).Count
    Write-Output "OK  权威存档 $n 条: $proj"
}

if (Test-Path $herm) {
    Write-Warning "DIVERGED 又出现第二份存档(应已冻结为 .legacy-20260930): $herm"; $bad++
} else {
    Write-Output "OK  Hermes 侧无重复存档"
}

foreach ($b in @((Join-Path $root '一键启动股票看盘.bat'), (Join-Path $env:USERPROFILE 'Desktop\启动股票看盘.bat'))) {
    if (-not (Test-Path $b)) { Write-Warning "MISSING 启动器: $b"; $bad++; continue }
    $txt = [System.IO.File]::ReadAllText($b, [System.Text.Encoding]::GetEncoding(936))
    if ($txt -match 'STOCK_DATA_HOME') { Write-Output ("OK  启动器已固化: " + (Split-Path $b -Leaf)) }
    else { Write-Warning ("未固化 STOCK_DATA_HOME: " + $b); $bad++ }
}

Write-Output ("—— 单点校验完成, 问题数: " + $bad)
exit $bad
