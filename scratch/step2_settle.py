# -*- coding: utf-8 -*-
"""Step2 收口: 存档合并 + 启动器固化 STOCK_DATA_HOME + 哨兵改为单点校验

背景: stock_dashboard.py 的落点链是 STOCK_DATA_HOME > HERMES_HOME > ~/.hermes,
      两个启动器都没设 STOCK_DATA_HOME -> 用桌面 bat 启动时收盘归档会写进 Hermes 目录,
      与项目侧存档分叉(实测: 项目侧 30 条含 20260929 / Hermes 侧 29 条缺 20260929)。
本脚本: 备份 -> 按日期并集合并(同日期取字段更全者) -> 冻结 Hermes 旧档 -> 两个 bat 固化变量 -> 重写哨兵。
"""
import json
import os
import pathlib
import shutil

ROOT = pathlib.Path(r"D:\股票看盘")
PROJ = ROOT / "data" / "stock_data" / "sentiment_history.jsonl"
HERM = pathlib.Path(r"C:\Users\28769\AppData\Local\hermes\stock_data\sentiment_history.jsonl")
DESK_BAT = pathlib.Path(r"C:\Users\28769\Desktop\启动股票看盘.bat")
PROJ_BAT = ROOT / "一键启动股票看盘.bat"
SYNC = ROOT / "scripts" / "sync_check.ps1"
BK = ROOT / "scratch" / "step2_backup_20260930"
BK.mkdir(parents=True, exist_ok=True)


def load(p):
    recs = []
    if p.exists():
        for ln in p.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                try:
                    recs.append(json.loads(ln))
                except Exception as e:
                    print("   跳过坏行:", e)
    return recs


print("== 1. 备份（合并前快照）==")
for src in [PROJ, HERM, PROJ_BAT, DESK_BAT, SYNC]:
    if src.exists():
        dst = BK / src.name
        shutil.copy2(src, dst)
        print(f"   {src}  ->  {dst.name}  ({src.stat().st_size}B)")

print()
print("== 2. 合并存档（按日期并集；同日期取字段更全者）==")
a, b = load(PROJ), load(HERM)
by = {}
conflicts = []


def richness(r):
    return sum(1 for k in ("stage", "stage_meta", "band", "zt", "zb", "dt", "max_lb")
               if r.get(k) is not None)


for tag, recs in (("项目侧", a), ("Hermes侧", b)):
    for r in recs:
        d = str(r.get("date"))
        if d not in by:
            by[d] = r
            continue
        old = by[d]
        if json.dumps(old, sort_keys=True, ensure_ascii=False) == json.dumps(r, sort_keys=True, ensure_ascii=False):
            continue
        win, lose = (r, old) if richness(r) > richness(old) else (old, r)
        conflicts.append((d, win, lose))
        by[d] = win
print(f"   项目侧 {len(a)} 条 / Hermes侧 {len(b)} 条  ->  合并后 {len(by)} 条")
print(f"   同日期不同值: {len(conflicts)} 条")
for d, w, l in conflicts:
    print(f"     {d}: 保留 score={w.get('score')} stage={w.get('stage')} | 丢弃 score={l.get('score')} stage={l.get('stage')}")
dates = sorted(by)
print("   合并后日期序列:", dates)
tmp = str(PROJ) + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    for d in dates:
        f.write(json.dumps(by[d], ensure_ascii=False) + "\n")
os.replace(tmp, PROJ)
print(f"   已原子写回项目侧: {PROJ}  ({PROJ.stat().st_size}B)")

print()
print("== 3. 冻结 Hermes 侧旧档（改名 .legacy，防止再被追加）==")
if HERM.exists():
    leg = pathlib.Path(str(HERM) + ".legacy-20260930")
    if leg.exists():
        leg.unlink()
    HERM.rename(leg)
    print(f"   {HERM.name}  ->  {leg.name}")
else:
    print("   (Hermes 侧已无该文件)")

print()
print("== 4. 启动器固化 STOCK_DATA_HOME（保持 GBK + CRLF，不写 chcp）==")
SETLINE = r"set STOCK_DATA_HOME=D:\股票看盘\data"


def patch_bat(p):
    p = pathlib.Path(p)
    if not p.exists():
        print(f"   缺失: {p}")
        return
    raw = p.read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    txt = raw.decode("gbk")
    crlf = "\r\n" in txt
    print(f"   {p.name}: {len(raw)}B  BOM={has_bom}  CRLF={crlf}")
    if "STOCK_DATA_HOME" in txt:
        print("     已包含该变量，跳过")
        return
    normalized = txt.replace("\r\n", "\n")
    lines = normalized.split("\n")
    out, inserted = [], False
    for i, ln in enumerate(lines):
        out.append(ln)
        if not inserted and (ln.strip().startswith("title") or i == 0):
            out.append(SETLINE)
            inserted = True
    new = "\r\n".join(out)  # 统一 CRLF（bat 必须 CRLF，见 04-tech-env 踩坑记录）
    p.write_bytes(new.encode("gbk"))
    print(f"     已插入固化行（CRLF/GBK 保持）: {SETLINE}")


for p in [PROJ_BAT, DESK_BAT]:
    patch_bat(p)

print()
print("== 5. 哨兵重写为“单点校验”（旧的硬链副本治理目标 D:\\hermes 已删除）==")
SYNC_TEXT = r'''# sync_check.ps1 - 单点校验哨兵 (2026-09-30 重写)
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
'''
SYNC.write_bytes(b"\xef\xbb\xbf" + SYNC_TEXT.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))
print(f"   已重写: {SYNC} ({SYNC.stat().st_size}B, UTF-8 with BOM + CRLF)")

print()
print("== 完成 ==")