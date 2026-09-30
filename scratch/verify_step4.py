# -*- coding: utf-8 -*-
"""P2-A 验证: LRU 硬上限 / 午休+节假日识别 / ut token 告警 / 首页缓存口径 / gitignore

用法: python scratch/verify_step4.py     （离线为主, 不依赖 web 服务）
"""
import contextlib
import datetime as dt
import io
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(r"D:\股票看盘")
sys.path.insert(0, str(ROOT / "scripts"))
import data_feed as df  # noqa: E402
import stock_dashboard as sd  # noqa: E402

fails = []


def check(name, cond, extra=''):
    print(('PASS  ' if cond else 'FAIL  ') + name + (('   ' + str(extra)) if extra else ''))
    if not cond:
        fails.append(name)


print("== 1. TTL 缓存: 真 LRU + 硬上限 ==")
c = df.MemoryTTLCache(max_entries=5)
for k in 'abcde':
    c.set(k, k, ttl=60)
check("未超限时保留全部 5 条", len(c._cache) == 5 and c._evictions == 0, len(c._cache))
c.get('a')                      # 刷新 a 的最近使用
c.set('f', 'f', ttl=60)         # 触发淘汰(6 > 5 -> 降到 90% = 4)
keys = list(c._cache.keys())
print("   淘汰后 keys =", keys, "| evictions =", c._evictions)
check("触发淘汰且回到上限内", len(c._cache) <= 5 and c._evictions > 0, (len(c._cache), c._evictions))
check("LRU 生效: 刚访问过的 a 被留下", 'a' in keys)
check("LRU 生效: 最久未用的 b 被淘汰", 'b' not in keys)
check("新写入的 f 在", 'f' in keys)

print()
print("== 2. TTL 过期仍然有效 + stats 新字段 ==")
c2 = df.MemoryTTLCache(max_entries=10)
c2.set('t', 1, ttl=0.01)
time.sleep(0.05)
check("过期后 get 返回 None", c2.get('t') is None)
check("过期计入 miss", c2.stats()['misses'] >= 1, c2.stats())
st = c2.stats()
check("stats 暴露 max_entries / evictions", 'max_entries' in st and 'evictions' in st, list(st))

print()
print("== 3. _closed_by_clock: 午休/周末/盘前盘后（纯时间, 可单测）==")
cases = [
    ("周六 10:00", dt.datetime(2026, 10, 3, 10, 0), True),
    ("周一 08:00 盘前", dt.datetime(2026, 9, 28, 8, 0), True),
    ("周一 09:30 开盘", dt.datetime(2026, 9, 28, 9, 30), False),
    ("周一 11:29 上午盘尾", dt.datetime(2026, 9, 28, 11, 29), False),
    ("周一 11:30 午休开始", dt.datetime(2026, 9, 28, 11, 30), True),
    ("周一 12:30 午休中", dt.datetime(2026, 9, 28, 12, 30), True),
    ("周一 12:59 午休末", dt.datetime(2026, 9, 28, 12, 59), True),
    ("周一 13:00 下午开盘", dt.datetime(2026, 9, 28, 13, 0), False),
    ("周一 15:05 收盘", dt.datetime(2026, 9, 28, 15, 5), False),
    ("周一 15:06 收盘后", dt.datetime(2026, 9, 28, 15, 6), True),
]
for label, t, want in cases:
    got = df._closed_by_clock(t)
    check(f"{label} -> {'休市' if want else '交易'}", got == want, got)

print()
print("== 4. 节假日识别（不硬编码日历, 用实时行情日期戳）==")
_real = df._is_trading_today
df._is_trading_today = lambda ttl=300.0: (False, '20260929')
check("行情日期戳停在上一交易日 -> is_market_closed() 为 True（现在处于交易时段）",
      df.is_market_closed() is True)
df._is_trading_today = lambda ttl=300.0: (True, dt.date.today().strftime('%Y%m%d'))
now = dt.datetime.now()
expect = df._closed_by_clock(now)
check(f"交易日 -> 结果与纯时间判断一致（现在应为 {'休市' if expect else '交易'}）",
      df.is_market_closed() is expect, expect)
df._is_trading_today = _real

print()
print("== 5. ut token 失效告警（不再静默）==")
sd.http = lambda url, **kw: json.dumps({'rc': 1, 'msg': 'token expired'})
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    out = sd._pool('ZT', '20260930')
check("无 data 字段 -> 返回空 + 打印 ut token 警告",
      out == [] and 'ut token 失效' in buf.getvalue(), buf.getvalue().strip()[:80])
sd.http = lambda url, **kw: json.dumps({'data': None})
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    out = sd._pool('ZT', '20260930')
check("data:null 形态 -> 同样告警", out == [] and 'ut token 失效' in buf.getvalue())
sd.http = lambda url, **kw: json.dumps({'data': {'pool': [{'c': '600825', 'n': '新华传媒', 'lbc': 7}]}})
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    out = sd._pool('ZT', '20260930')
check("正常响应 -> 不告警且返回池子", len(out) == 1 and '警告' not in buf.getvalue(), out)

print()
print("== 6. .gitignore 已忽略备份目录 ==")
gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
check("含 scratch/*_backup_*/", "scratch/*_backup_*/" in gi)
r = subprocess.run(["git", "status", "--short"], cwd=str(ROOT), capture_output=True, text=True, timeout=60)
lines = r.stdout or ""
check("git status 不再列出备份目录", "_backup_" not in lines, [l for l in lines.splitlines() if 'backup' in l])

print()
print("FAILED:", fails if fails else "无 —— 全部通过")
sys.exit(1 if fails else 0)