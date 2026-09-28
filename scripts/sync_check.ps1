# sync_check.ps1 - 多拷贝哈希哨兵 (硬链治理, 2026-08-25 dsh方案E落地)
# 用法: powershell -File sync_check.ps1 [-Fix]
# 默认只读比对+告警; -Fix 时对分叉/缺失的副本自动重建硬链
param([switch]$Fix)
$ErrorActionPreference = 'Continue'
$base = 'D:\股票看盘\scripts\stock_dashboard.py'
$links = @(
  'D:\hermes\Hermes Agent CN Desktop\data\hermes-home\scripts\stock_dashboard.py',
  'D:\hermes\Hermes Agent CN Desktop\data\hermes-home\skills\finance-stock-dashboard\scripts\stock_dashboard.py'
)
if (-not (Test-Path $base)) { Write-Warning "BASE MISSING: $base"; exit 1 }
$hb = (Get-FileHash $base -Algorithm SHA256).Hash
$bad = 0
foreach ($p in $links) {
  if (-not (Test-Path $p)) {
    Write-Warning "MISSING: $p"
    $bad++
    if ($Fix) { New-Item -ItemType HardLink -Path $p -Target $base | Out-Null; Write-Output "FIXED(hardlink): $p" }
    continue
  }
  # 硬链健康检查: 同 inode 则 hash 必同; hash 不同说明已断链或被改
  $hp = (Get-FileHash $p -Algorithm SHA256).Hash
  if ($hb -ne $hp) {
    Write-Warning "DIVERGED: $p"
    $bad++
    if ($Fix) { Remove-Item $p -Force; New-Item -ItemType HardLink -Path $p -Target $base | Out-Null; Write-Output "FIXED(relinked): $p" }
  } else {
    Write-Output "OK: $p"
  }
}
# ---- strategies_lib.py 同样治理 (2026-08-25 策略库会诊新增) ----
$base = 'D:\股票看盘\scripts\strategies_lib.py'
$links = @(
  'D:\hermes\Hermes Agent CN Desktop\data\hermes-home\scripts\strategies_lib.py',
  'D:\hermes\Hermes Agent CN Desktop\data\hermes-home\skills\finance-stock-dashboard\scripts\strategies_lib.py'
)
if (-not (Test-Path $base)) { Write-Warning "BASE MISSING: $base"; $bad++ }
else {
  $hb = (Get-FileHash $base -Algorithm SHA256).Hash
  foreach ($p in $links) {
    if (-not (Test-Path $p)) { Write-Warning "MISSING: $p"; $bad++; if ($Fix) { New-Item -ItemType HardLink -Path $p -Target $base | Out-Null; Write-Output "FIXED(hardlink): $p" }; continue }
    $hp = (Get-FileHash $p -Algorithm SHA256).Hash
    if ($hb -ne $hp) { Write-Warning "DIVERGED: $p"; $bad++; if ($Fix) { Remove-Item $p -Force; New-Item -ItemType HardLink -Path $p -Target $base | Out-Null; Write-Output "FIXED(relinked): $p" } }
    else { Write-Output "OK: $p" }
  }
}
# 存档一致性(只读比对不修复): 情绪档 + 预判档(可能尚不存在)
$pairs = @(
  @('D:\hermes\Hermes Agent CN Desktop\data\hermes-home\stock_data\sentiment_history.jsonl', 'D:\股票看盘\data\stock_data\sentiment_history.jsonl'),
  @('D:\hermes\Hermes Agent CN Desktop\data\hermes-home\stock_data\pred.jsonl', 'D:\股票看盘\data\stock_data\pred.jsonl')
)
foreach ($pair in $pairs) {
  if ((Test-Path $pair[0]) -and (Test-Path $pair[1])) {
    if ((Get-FileHash $pair[0]).Hash -ne (Get-FileHash $pair[1]).Hash) {
      Write-Warning "ARCHIVE DIVERGED: $($pair[0]) vs $($pair[1])"; $bad++
    } else {
      Write-Output "ARCHIVE OK: $(Split-Path $pair[0] -Leaf)"
    }
  }
}
if ($bad -gt 0 -and -not $Fix) { exit 2 } else { exit 0 }

