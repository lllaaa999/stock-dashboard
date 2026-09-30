# -*- coding: utf-8 -*-
"""P2-A: 健壮性四件套 —— ① TTL 缓存真 LRU+硬上限 ② 午休/节假日识别 ③ 首页缓存口径 ④ ut token 失效告警
外加 .gitignore 收尾。用"精确替换 + 命中计数断言", 任一断言失败整体不落盘。
"""
import pathlib
import sys

ROOT = pathlib.Path(r"D:\股票看盘")
DF = ROOT / "scripts" / "data_feed.py"
SD = ROOT / "scripts" / "stock_dashboard.py"
MAIN = ROOT / "web" / "main.py"
HTML = ROOT / "web" / "templates" / "index.html"
GI = ROOT / ".gitignore"

EDITS = []

# ============ data_feed.py ============
EDITS.append((DF, "from typing import Dict, List, Any, Optional",
              "from collections import OrderedDict\nfrom typing import Dict, List, Any, Optional",
              "df: import OrderedDict"))

EDITS.append((DF, '''class MemoryTTLCache:
    def __init__(self):
        self._cache: Dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key in self._cache:
                exp, val = self._cache[key]
                if time.time() < exp:
                    self._hits += 1
                    return val
                else:
                    del self._cache[key]
            self._misses += 1
            return None

    def set(self, key: str, val: Any, ttl: float = 60.0):
        with self._lock:
            # 限制缓存最大条目，防止无界增长
            if len(self._cache) > 2000:
                now = time.time()
                # 剔除过期或最老条目
                expired = [k for k, (exp, _) in self._cache.items() if exp < now]
                for k in expired[:500]:
                    del self._cache[k]
            self._cache[key] = (time.time() + ttl, val)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            valid = sum(1 for exp, _ in self._cache.values() if exp >= now)
            total = self._hits + self._misses
            hit_ratio = round(self._hits / total * 100, 1) if total > 0 else 0.0
            return {
                "active_keys": valid,
                "hits": self._hits,
                "misses": self._misses,
                "hit_ratio_pct": hit_ratio
            }''', '''class MemoryTTLCache:
    """线程安全 TTL 缓存 + 真 LRU 硬上限。

    旧实现只在条目数 >2000 **且存在过期项**时才清理 —— 没有硬上限、没有 LRU,
    盘中热门 key 永不淘汰, 长跑会无界增长(2026-09-30 修正)。
    现改为 OrderedDict: 命中即 move_to_end, 超上限时先清过期、再按 LRU 淘汰到 90%。
    """

    def __init__(self, max_entries: int = 4000):
        self._cache: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._max = int(max_entries)

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            item = self._cache.get(key)
            if item is None:
                self._misses += 1
                return None
            exp, val = item
            if time.time() >= exp:
                del self._cache[key]
                self._misses += 1
                return None
            self._cache.move_to_end(key)      # LRU: 命中即刷新最近使用顺序
            self._hits += 1
            return val

    def set(self, key: str, val: Any, ttl: float = 60.0):
        with self._lock:
            self._cache[key] = (time.time() + ttl, val)
            self._cache.move_to_end(key)
            if len(self._cache) > self._max:
                self._evict_locked()

    def _evict_locked(self):
        now = time.time()
        for k in [k for k, (exp, _) in self._cache.items() if exp < now]:
            del self._cache[k]
        target = max(1, int(self._max * 0.9))
        while len(self._cache) > target:
            self._cache.popitem(last=False)   # 淘汰最久未使用
            self._evictions += 1

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            valid = sum(1 for exp, _ in self._cache.values() if exp >= now)
            total = self._hits + self._misses
            hit_ratio = round(self._hits / total * 100, 1) if total > 0 else 0.0
            return {
                "active_keys": valid,
                "max_entries": self._max,
                "evictions": self._evictions,
                "hits": self._hits,
                "misses": self._misses,
                "hit_ratio_pct": hit_ratio
            }''', "df: LRU cache"))

EDITS.append((DF, '''def is_market_closed() -> bool:
    """判断是否处于盘后时间 (周一至周五 15:05 之后或周末)"""
    now = dt.datetime.now()
    if now.weekday() >= 5:
        return True
    if now.hour > 15 or (now.hour == 15 and now.minute >= 5):
        return True
    if now.hour < 9 or (now.hour == 9 and now.minute < 15):
        return True
    return False''', '''_TRADE_DAY_CACHE = {'t': 0.0, 'is_trading': None, 'quote_date': None}


def _is_trading_today(ttl: float = 300.0):
    """今天是不是交易日 —— 用上证指数实时行情的日期戳判断(节假日它会停在最近交易日),
    不硬编码节假日日历。取不到数据时保守返回 True(退回纯时间判断)。
    返回 (is_trading, quote_date)。"""
    now = time.time()
    if _TRADE_DAY_CACHE['is_trading'] is not None and (now - _TRADE_DAY_CACHE['t']) < ttl:
        return _TRADE_DAY_CACHE['is_trading'], _TRADE_DAY_CACHE['quote_date']
    is_trading, qd = True, None
    try:
        raw = sd.http('https://qt.gtimg.cn/q=sh000001', gbk=True, timeout=3, retries=1)
        parts = raw.split('~') if '~' in raw else []
        if len(parts) > 30 and parts[30]:
            qd = str(parts[30])[:8]
            is_trading = (qd == dt.date.today().strftime('%Y%m%d'))
    except Exception:
        pass
    _TRADE_DAY_CACHE.update({'t': now, 'is_trading': is_trading, 'quote_date': qd})
    return is_trading, qd


def _closed_by_clock(now) -> bool:
    """纯时间判断(周末/盘前/午休/收盘后) —— 与交易日探测解耦, 便于单测"""
    if now.weekday() >= 5:
        return True
    minute = now.hour * 60 + now.minute
    if minute < 9 * 60 + 15 or minute > 15 * 60 + 5:
        return True
    if 11 * 60 + 30 <= minute < 13 * 60:
        return True
    return False


def is_market_closed() -> bool:
    """是否处于"非交易时段": 周末 / 节假日 / 盘前 / 午休 / 收盘后。

    2026-09-30 修正: 原实现只认"周末 + 9:15 前 + 15:05 后", 午休(11:30-13:00)和
    节假日都被当成盘中 —— 长假里页面开着会按 15s TTL 白打上游好几天。
    """
    if _closed_by_clock(dt.datetime.now()):
        return True
    return not _is_trading_today()[0]''', "df: is_market_closed"))

EDITS.append((DF, '''        "market_closed": is_market_closed(),''',
              '''        "market_closed": is_market_closed(),
        "trading_today": _is_trading_today()[0],
        "quote_date": _is_trading_today()[1],''', "df: status fields"))

# ============ stock_dashboard.py ============
EDITS.append((SD, """    j = json.loads(http(u))
    d = j.get('data') or {}
    return (d.get('pool') or [])""",
              """    j = json.loads(http(u))
    if not isinstance(j, dict) or 'data' not in j:
        # ut token 失效时东财返回的是 rc!=0 / 无 data 字段的响应体; 旧代码会把它当成
        # "该日无涨停池"静默吞掉 —— 7 日回溯白跑、情绪分凭空少一块(2026-09-30 修正)。
        print('[涨停池·警告] %s %s 响应里没有 data 字段 —— 疑似 ut token 失效(当前 UT=%s); '
              '请从东方财富行情页-涨停池的网络请求里重新抓 ut 并更新 UT 常量' % (kind, ymd, UT))
        return []
    d = j.get('data') or {}
    return (d.get('pool') or [])""", "sd: ut token warn"))

# ============ web/main.py ============
EDITS.append((MAIN, """_market_cache = {
    'data': None,
    'timestamp': 0.0,
}""", """_market_cache = {
    'data': None,
    'timestamp': 0.0,
    # 2026-09-30: 首页"缓存命中"原来读的是 data_feed 那套(行情快照)缓存, 而大盘页实际
    # 走这个 _market_cache —— 于是首页永远显示 0%, 看着像坏了。这里补上自己的计数。
    'hits': 0,
    'misses': 0,
    'last_refresh_s': None,
}""", "main: market cache counters"))

EDITS.append((MAIN, """def _get_market_ttl() -> float:
    \"\"\"动态 TTL：A 股交易时段 (9:15-15:05 周一至周五) 6秒，其余时段 60秒\"\"\"
    now = datetime.datetime.now()
    if now.weekday() < 5:
        minute_of_day = now.hour * 60 + now.minute
        if (9 * 60 + 15) <= minute_of_day <= (15 * 60 + 5):
            return 6.0
    return 60.0""", """def _get_market_ttl() -> float:
    \"\"\"动态 TTL：交易时段 6 秒, 其余时段 60 秒。

    2026-09-30: 改用 data_feed.is_market_closed() 统一判定 —— 原实现把午休和节假日
    都算作盘中, 长假里页面开着会 6 秒一次白刷上游。
    \"\"\"
    return 60.0 if df_feed.is_market_closed() else 6.0""", "main: market ttl"))

EDITS.append((MAIN, """    if not refresh and _market_cache['data'] is not None and (now_ts - _market_cache['timestamp']) < ttl:
        cached_resp = dict(_market_cache['data'])""",
              """    if not refresh and _market_cache['data'] is not None and (now_ts - _market_cache['timestamp']) < ttl:
        _market_cache['hits'] += 1
        cached_resp = dict(_market_cache['data'])""", "main: hit counter"))

EDITS.append((MAIN, """    def safe(fn, default=None):""",
              """    _market_cache['misses'] += 1


    def safe(fn, default=None):""", "main: miss counter"))

EDITS.append((MAIN, """    _market_cache['data'] = resp_data
    _market_cache['timestamp'] = now_ts

    return JSONResponse(resp_data)""",
              """    _market_cache['data'] = resp_data
    _market_cache['timestamp'] = now_ts
    _market_cache['last_refresh_s'] = elapsed

    return JSONResponse(resp_data)""", "main: last refresh"))

EDITS.append((MAIN, """@app.get("/api/data_status")
def api_data_status():
    \"\"\"获取所有上游数据源健康度与内存 TTL 缓存运行指标\"\"\"
    return JSONResponse(df_feed.get_system_data_status())""",
              """@app.get("/api/data_status")
def api_data_status():
    \"\"\"上游数据源健康度 + 内存 TTL 缓存指标 + 大盘页缓存命中(market_cache)\"\"\"
    st = df_feed.get_system_data_status()
    _mh, _mm = _market_cache['hits'], _market_cache['misses']
    st['market_cache'] = {
        'hits': _mh,
        'misses': _mm,
        'hit_ratio_pct': round(_mh / max(_mh + _mm, 1) * 100, 1),
        'ttl_s': _get_market_ttl(),
        'last_refresh_s': _market_cache['last_refresh_s'],
        'age_s': round(time.time() - _market_cache['timestamp'], 1) if _market_cache['timestamp'] else None,
    }
    return JSONResponse(st)""", "main: data_status market_cache"))

# ============ index.html ============
EDITS.append((HTML, """    if(pCa){
      pCa.textContent = `⚡ 缓存命中 ${c.hit_ratio_pct || 0}% (${c.hits || 0}次)`;
    }""", """    if(pCa){
      const mc = d.market_cache || null;
      pCa.textContent = mc
        ? `⚡ 大盘缓存 命中${mc.hits || 0}/未命中${mc.misses || 0} · TTL ${mc.ttl_s || '-'}s${d.market_closed ? ' · 休市中' : ''}`
        : `⚡ 缓存命中 ${c.hit_ratio_pct || 0}% (${c.hits || 0}次)`;
    }""", "html: cache pill"))

# ============ .gitignore ============
EDITS.append((GI, """*.bak""", """*.bak

# 优化/结算前的临时备份快照
scratch/*_backup_*/""", "gitignore"))

print("== 应用编辑 ==")
work = {}
for path in [p for p, *_ in EDITS]:
    work.setdefault(path, path.read_text(encoding="utf-8"))

ok = True
for path, old, new, label in EDITS:
    cnt = work[path].count(old)
    if cnt != 1:
        print(f"  ABORT  {label}: 命中 {cnt} 次(应为 1)")
        ok = False
        continue
    work[path] = work[path].replace(old, new, 1)
    print(f"  OK     {label}")

if not ok:
    print("有编辑未命中, 整体不落盘")
    sys.exit(1)

for path in work:
    path.write_text(work[path], encoding="utf-8")
    print(f"已写回: {path}  ({path.stat().st_size}B)")
print("== 完成 ==")