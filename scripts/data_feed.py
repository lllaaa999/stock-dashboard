# -*- coding: utf-8 -*-
"""
统一数据源引擎 (Data Feed Engine)
提供多源容灾热备 (腾讯 -> 新浪 -> 东财)、内存 TTL 缓存、分时黄白线与实时资金单笔分布。
"""
import os
import sys
import time
import json
import threading
import datetime as dt
from collections import OrderedDict
from typing import Dict, List, Any, Optional

# 导入现有底层 http 客户端
CUR_DIR = os.path.dirname(os.path.abspath(__file__))
if CUR_DIR not in sys.path:
    sys.path.insert(0, CUR_DIR)
import stock_dashboard as sd
try:
    from ths_extractor import THSRealtimeQuote
except ImportError:
    THSRealtimeQuote = None

# ==========================================
# 1. 线程安全内存 TTL 缓存 (In-Memory TTL Cache)
# ==========================================
class MemoryTTLCache:
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
            }

CACHE = MemoryTTLCache()

# ==========================================
# 2. 数据源健康度探测与追踪 (Health Monitor)
# ==========================================
SOURCE_HEALTH = {
    "tencent": {"status": "healthy", "latency_ms": 0, "failures": 0, "successes": 0},
    "ths": {"status": "healthy", "latency_ms": 0, "failures": 0, "successes": 0},
    "sina": {"status": "healthy", "latency_ms": 0, "failures": 0, "successes": 0},
    "eastmoney": {"status": "healthy", "latency_ms": 0, "failures": 0, "successes": 0}
}

def _record_status(source: str, ok: bool, latency: float):
    st = SOURCE_HEALTH.get(source)
    if not st:
        return
    if ok:
        st["successes"] += 1
        st["failures"] = 0
        st["status"] = "healthy"
        st["latency_ms"] = round(latency * 1000, 1)
    else:
        st["failures"] += 1
        # 阈值必须从高到低判断: 原来的 >=3 / elif >=5 会让 offline 永远不可达(2026-09-30 修正)
        if st["failures"] >= 5:
            st["status"] = "offline"
        elif st["failures"] >= 3:
            st["status"] = "degraded"

_TRADE_DAY_CACHE = {'t': 0.0, 'is_trading': None, 'quote_date': None}


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
    except Exception as _e:
        # 修复 (2026-10-18): 原来静默 pass，并把乐观的 is_trading=True 连同
        # 300s TTL 写进缓存 —— 一次网络抖动会让系统在 5 分钟内都认为"今天是交易日"，
        # 进而影响盘前/休市判定。现在：异常时只做短缓存(30s)让下次尽快重试，
        # 并记录原因，避免把"探测失败"固化成"确定是交易日"。
        _TRADE_DAY_CACHE.update({'t': now - ttl + 30.0, 'is_trading': True, 'quote_date': None})
        _TRADE_DAY_CACHE['last_error'] = '%s: %s' % (type(_e).__name__, _e)
        return True, None
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
    return not _is_trading_today()[0]

# ==========================================
# 3. 实时行情：多源自动降级 (Tencent -> Sina -> EastMoney)
# ==========================================
def normalize_code(c: str) -> tuple[str, str, str]:
    """返回 (pure_code, full_code, em_secid)，例如 ('600519', 'sh600519', '1.600519')"""
    code = c.replace('sh', '').replace('sz', '').replace('bj', '').strip()
    is_sh = code.startswith(('6', '5', '9'))
    is_bj = code.startswith(('4', '8'))
    prefix = 'sh' if is_sh else ('bj' if is_bj else 'sz')
    full = prefix + code
    secid = ('1.' if is_sh else '0.') + code
    return code, full, secid

def get_realtime_quotes(codes: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    批量获取实时行情，优先腾讯，故障时秒切新浪，再备选东财。
    带有 1.5 秒短缓存，防止并发请求冲垮接口。
    """
    if not codes:
        return {}

    cache_key = f"quotes:{','.join(sorted(codes))}"
    cached = CACHE.get(cache_key)
    if cached is not None:
        return cached

    norm_list = [normalize_code(c) for c in codes]
    full_codes = [n[1] for n in norm_list]
    code_map = {n[1]: n[0] for n in norm_list}
    result: Dict[str, Dict[str, Any]] = {}

    # --- 策略 A: 腾讯证券 (主源，毫秒级批处理) ---
    t0 = time.time()
    try:
        url = 'https://qt.gtimg.cn/q=' + ','.join(full_codes)
        raw = sd.http(url, gbk=True, timeout=3)
        for line in raw.split(';'):
            if '=' not in line:
                continue
            p = line.split('"')[1]
            f = p.split('~')
            if len(f) > 38:
                c = f[2]
                amt = float(f[37]) if f[37] else 0
                amts = ('-' if c.startswith('.') else
                        (f'{amt/10000:,.1f}亿' if amt >= 10000 else (f'{amt:,.0f}万' if amt > 0 else '-')))
                price = float(f[3]) if f[3] else 0.0
                prev_close = float(f[4]) if f[4] else 0.0
                high = float(f[33]) if f[33] else price
                low = float(f[34]) if f[34] else price
                open_p = float(f[5]) if f[5] else price
                pct = float(f[32]) if f[32] else 0.0
                chg = float(f[31]) if f[31] else 0.0
                vol = float(f[36]) if f[36] else 0.0

                limit_up = float(f[47]) if len(f) > 47 and f[47] else 0.0
                limit_down = float(f[48]) if len(f) > 48 and f[48] else 0.0
                is_zt = (price >= limit_up - 0.01) if limit_up > 0 else False
                is_dt = (price <= limit_down + 0.01) if limit_down > 0 else False

                # 买卖五档挂单 [[price, vol], ...] (量单位为手)
                bids = [
                    [float(f[9] or 0), float(f[10] or 0)],
                    [float(f[11] or 0), float(f[12] or 0)],
                    [float(f[13] or 0), float(f[14] or 0)],
                    [float(f[15] or 0), float(f[16] or 0)],
                    [float(f[17] or 0), float(f[18] or 0)],
                ]
                asks = [
                    [float(f[19] or 0), float(f[20] or 0)],
                    [float(f[21] or 0), float(f[22] or 0)],
                    [float(f[23] or 0), float(f[24] or 0)],
                    [float(f[25] or 0), float(f[26] or 0)],
                    [float(f[27] or 0), float(f[28] or 0)],
                ]
                tot_bid = sum(b[1] for b in bids)
                tot_ask = sum(a[1] for a in asks)
                denom = tot_bid + tot_ask
                order_ratio = round((tot_bid - tot_ask) / denom * 100, 2) if denom > 0 else 0.0

                bid1_p = bids[0][0]
                bid1_v = bids[0][1]
                ask1_p = asks[0][0]
                ask1_v = asks[0][1]

                # 挂单额计算：1手=100股，元转亿元除以 1e8，即 (p * v * 100) / 1e8 = (p * v) / 1e6
                bid1_amt_yi = round(bid1_p * bid1_v / 1e6, 2) if bid1_p > 0 else 0.0
                ask1_amt_yi = round(ask1_p * ask1_v / 1e6, 2) if ask1_p > 0 else 0.0
                seal_amount_yi = bid1_amt_yi if is_zt else 0.0
                dt_pressure_yi = ask1_amt_yi if is_dt else 0.0

                result[c] = {
                    'code': c,
                    'name': f[1],
                    'price': price,
                    'prev_close': prev_close,
                    'open': open_p,
                    'high': high,
                    'low': low,
                    'pct': pct,
                    'chg': chg,
                    'volume': vol,
                    'amount': amts,
                    'upper_limit': limit_up,
                    'lower_limit': limit_down,
                    'is_zt': is_zt,
                    'is_dt': is_dt,
                    'bid1': (bid1_p, bid1_v),
                    'ask1': (ask1_p, ask1_v),
                    'bids': bids,
                    'asks': asks,
                    'total_bid_vol': tot_bid,
                    'total_ask_vol': tot_ask,
                    'order_ratio': order_ratio,
                    'weibi': order_ratio,
                    'bid1_amount_yi': bid1_amt_yi,
                    'ask1_amount_yi': ask1_amt_yi,
                    'seal_amount_yi': seal_amount_yi,
                    'seal_wan': round(seal_amount_yi * 10000, 1),
                    'dt_pressure_yi': dt_pressure_yi,
                    'dt_wan': round(dt_pressure_yi * 10000, 1),
                    'source': 'tencent',
                    'updated_at': f[30] if len(f) > 30 else ''
                }
        if len(result) >= len(full_codes) * 0.8:
            _record_status("tencent", True, time.time() - t0)
            CACHE.set(cache_key, result, ttl=1.5)
            return result
    except Exception:
        _record_status("tencent", False, time.time() - t0)

    # --- 策略 B: 同花顺极速行情 (备源 1，官方快照与高精盘口) ---
    t0 = time.time()
    if THSRealtimeQuote:
        try:
            missing_codes = [c for c in norm_list if c[0] not in result]
            if missing_codes:
                from concurrent.futures import ThreadPoolExecutor
                def _fetch_ths(item):
                    pure, full, _ = item
                    q = THSRealtimeQuote.get_realhead(pure)
                    if q and q.get('price'):
                        amt_w = q.get('amount_wan', 0.0)
                        amts = (f"{amt_w/10000:,.1f}亿" if amt_w >= 10000 else (f"{amt_w:,.0f}万" if amt_w > 0 else '-'))
                        return pure, {
                            'code': pure,
                            'name': q.get('name', ''),
                            'price': q.get('price', 0.0),
                            'prev_close': q.get('prev_close', 0.0),
                            'open': q.get('open', 0.0),
                            'high': q.get('high', 0.0),
                            'low': q.get('low', 0.0),
                            'pct': q.get('change_pct', 0.0),
                            'chg': q.get('change_amt', 0.0),
                            'volume': q.get('volume_hand', 0.0),
                            'amount': amts,
                            'upper_limit': q.get('upper_limit', 0.0),
                            'lower_limit': q.get('lower_limit', 0.0),
                            'turnover_rate': q.get('turnover_rate', 0.0),
                            'is_zt': q.get('is_zt', False),
                            'is_dt': q.get('is_dt', False),
                            'bid1': q.get('bid1', (0.0, 0.0)),
                            'ask1': q.get('ask1', (0.0, 0.0)),
                            'bids': q.get('bids', []),
                            'asks': q.get('asks', []),
                            'order_ratio': q.get('order_ratio', 0.0),
                            'bid1_amount_yi': q.get('bid1_amount_yi', 0.0),
                            'ask1_amount_yi': q.get('ask1_amount_yi', 0.0),
                            'seal_amount_yi': q.get('seal_amount_yi', 0.0),
                            'dt_pressure_yi': q.get('dt_pressure_yi', 0.0),
                            'source': 'ths',
                            'updated_at': q.get('time', '')
                        }
                    return pure, None

                with ThreadPoolExecutor(max_workers=min(len(missing_codes), 8)) as executor:
                    for pure, item in executor.map(_fetch_ths, missing_codes):
                        if item:
                            result[pure] = item
                if len(result) >= len(full_codes) * 0.8:
                    _record_status("ths", True, time.time() - t0)
                    CACHE.set(cache_key, result, ttl=1.5)
                    return result
        except Exception:
            _record_status("ths", False, time.time() - t0)

    # --- 策略 C: 新浪财经 (备源 2) ---
    t0 = time.time()
    try:
        url = 'https://hq.sinajs.cn/list=' + ','.join(full_codes)
        raw = sd.http(url, gbk=True, referer='https://finance.sina.com.cn/', timeout=3)
        for line in raw.strip().split('\n'):
            line = line.strip()
            if not line or '=' not in line:
                continue
            k = line.split('=')[0].replace('var hq_str_', '').strip()
            c = code_map.get(k, k)
            parts = line.split('=')[1].replace('"', '').replace(';', '').split(',')
            if len(parts) > 10:
                name = parts[0]
                open_p = float(parts[1]) if parts[1] else 0.0
                prev_close = float(parts[2]) if parts[2] else 0.0
                price = float(parts[3]) if parts[3] else 0.0
                high = float(parts[4]) if parts[4] else price
                low = float(parts[5]) if parts[5] else price
                vol = float(parts[8]) if len(parts) > 8 and parts[8] else 0.0
                amt = float(parts[9]) if len(parts) > 9 and parts[9] else 0.0
                amts = (f'{amt/1e8:,.1f}亿' if amt >= 1e8 else (f'{amt/1e4:,.0f}万' if amt > 0 else '-'))
                pct = round((price - prev_close) / prev_close * 100, 2) if prev_close > 0 else 0.0
                chg = round(price - prev_close, 2)

                result[c] = {
                    'code': c,
                    'name': name,
                    'price': price,
                    'prev_close': prev_close,
                    'open': open_p,
                    'high': high,
                    'low': low,
                    'pct': pct,
                    'chg': chg,
                    'volume': vol,
                    'amount': amts,
                    'source': 'sina',
                    'updated_at': parts[31] if len(parts) > 31 else ''
                }
        if result:
            _record_status("sina", True, time.time() - t0)
            CACHE.set(cache_key, result, ttl=1.5)
            return result
    except Exception:
        _record_status("sina", False, time.time() - t0)

    # --- 策略 D: 东方财富 (备源 3) ---
    t0 = time.time()
    try:
        for pure, full, secid in norm_list:
            if pure in result:
                continue
            u = f'https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f58,f43,f44,f45,f46,f47,f48,f60,f169,f170'
            raw = sd.http(u, referer='https://quote.eastmoney.com/', timeout=2)
            d = json.loads(raw).get('data') or {}
            price = round(float(d.get('f43', 0)) / 100, 2)
            high = round(float(d.get('f44', 0)) / 100, 2)
            low = round(float(d.get('f45', 0)) / 100, 2)
            open_p = round(float(d.get('f46', 0)) / 100, 2)
            prev_close = round(float(d.get('f60', 0)) / 100, 2)
            pct = round(float(d.get('f170', 0)) / 100, 2)
            chg = round(float(d.get('f169', 0)) / 100, 2)
            amt = float(d.get('f48', 0))
            amts = (f'{amt/1e8:,.1f}亿' if amt >= 1e8 else (f'{amt/1e4:,.0f}万' if amt > 0 else '-'))

            result[pure] = {
                'code': pure,
                'name': d.get('f58', ''),
                'price': price,
                'prev_close': prev_close,
                'open': open_p,
                'high': high,
                'low': low,
                'pct': pct,
                'chg': chg,
                'volume': float(d.get('f47', 0)),
                'amount': amts,
                'source': 'eastmoney',
                'updated_at': ''
            }
        if result:
            _record_status("eastmoney", True, time.time() - t0)
            CACHE.set(cache_key, result, ttl=1.5)
            return result
    except Exception:
        _record_status("eastmoney", False, time.time() - t0)

    return result

# ==========================================
# 4. 当日分时走势图 (白线价格 + 黄线均线)
# ==========================================
def get_intraday_trends(code: str) -> Dict[str, Any]:
    """
    获取当日分时数据：
    - times: 分钟时间列表 ['09:30', '09:31', ...]
    - prices: 现价(白线)
    - avg_prices: 均价(黄线)
    - volumes: 分钟量(手)
    - pre_close: 昨日收盘基准
    缓存策略：盘中 15 秒缓存；盘后 15:05 后缓存 3600 秒。
    """
    pure, full, secid = normalize_code(code)
    # 修复 (2026-10-18): 缓存 key 不含日期，而盘前 is_market_closed() 为 True，
    # 会把「昨日分时」按 3600 秒缓存下来，一路覆盖到 09:30 开盘之后，
    # 导致开盘后看到的是昨天的分时曲线。把交易日纳入 key 彻底隔离。
    _qdate = (_is_trading_today()[1] or dt.date.today().strftime('%Y%m%d'))
    cache_key = f"trends:{pure}:{_qdate}"
    cached = CACHE.get(cache_key)
    if cached is not None:
        return cached

    ttl = 3600.0 if is_market_closed() else 15.0

    # 1. 优先腾讯分时数据接口 (极速, <50ms)
    t0 = time.time()
    for host in ['https://web.ifzq.gtimg.cn', 'https://ifzq.gtimg.cn']:
        try:
            url = f"{host}/appstock/app/minute/query?code={full}"
            raw = sd.http(url, timeout=4)
            j = json.loads(raw)
            data_node = (j.get('data') or {}).get(full) or {}
            inner_data = data_node.get('data') or {}
            raw_minutes = inner_data.get('data') or []
            
            # 获取昨日收盘价作为中轴
            pre_close = 0.0
            qt_data = data_node.get('qt') or {}
            full_qt = qt_data.get(full) or []
            if len(full_qt) > 4 and full_qt[4]:
                pre_close = float(full_qt[4])

            if raw_minutes:
                times = []
                prices = []
                avg_prices = []
                volumes = []
                pcts = []

                prev_cum_vol = 0.0

                for row_str in raw_minutes:
                    parts = row_str.split()
                    if len(parts) >= 4:
                        raw_t = parts[0]
                        time_str = f"{raw_t[:2]}:{raw_t[2:]}"
                        p = float(parts[1])
                        cum_vol = float(parts[2])  # 累计手
                        cum_amt = float(parts[3])  # 累计金额(元)

                        # 计算分钟级成交量
                        delta_vol = max(0.0, cum_vol - prev_cum_vol)
                        prev_cum_vol = cum_vol

                        # 计算均价(黄线) = 累计金额 / (累计手 * 100)
                        avg_p = round(cum_amt / (cum_vol * 100), 2) if cum_vol > 0 else p
                        pct = round((p - pre_close) / pre_close * 100, 2) if pre_close > 0 else 0.0

                        times.append(time_str)
                        prices.append(p)
                        avg_prices.append(avg_p)
                        volumes.append(delta_vol)
                        pcts.append(pct)

                if not pre_close and prices:
                    pre_close = prices[0]

                res = {
                    'code': pure,
                    'pre_close': pre_close,
                    'times': times,
                    'prices': prices,
                    'avg_prices': avg_prices,
                    'volumes': volumes,
                    'pcts': pcts,
                    'source': 'tencent',
                    'count': len(times)
                }
                _record_status("tencent", True, time.time() - t0)
                CACHE.set(cache_key, res, ttl=ttl)
                return res
        except Exception:
            continue

    # 2. 备选同花顺分时数据接口 (官方逐分钟 VWAP 均价黄线, 极速免密)
    t0 = time.time()
    if THSRealtimeQuote:
        try:
            trend = THSRealtimeQuote.get_intraday_trend(pure)
            if trend and trend.get("points"):
                pts = trend["points"]
                pre_close = float(trend.get("prev_close") or 0.0)
                times = []
                prices = []
                avg_prices = []
                volumes = []
                pcts = []
                for p in pts:
                    raw_t = p["time"]
                    t_str = f"{raw_t[:2]}:{raw_t[2:]}" if len(raw_t) == 4 else raw_t
                    curr_p = float(p["price"])
                    avg_p = float(p.get("vwap", curr_p))
                    vol = round(float(p.get("volume", 0.0)) / 100.0, 1)
                    pct = round((curr_p - pre_close) / pre_close * 100, 2) if pre_close > 0 else 0.0

                    times.append(t_str)
                    prices.append(curr_p)
                    avg_prices.append(avg_p)
                    volumes.append(vol)
                    pcts.append(pct)

                if not pre_close and prices:
                    pre_close = prices[0]

                res = {
                    'code': pure,
                    'pre_close': pre_close,
                    'times': times,
                    'prices': prices,
                    'avg_prices': avg_prices,
                    'volumes': volumes,
                    'pcts': pcts,
                    'source': 'ths',
                    'count': len(times)
                }
                _record_status("ths", True, time.time() - t0)
                CACHE.set(cache_key, res, ttl=ttl)
                return res
        except Exception:
            _record_status("ths", False, time.time() - t0)

    # 3. 备选东财 trends 接口
    try:
        url = (f"https://push2his.eastmoney.com/api/qt/stock/trends2/get"
               f"?secid={secid}&fields1=f1,f2,f3,f4,f5,f6,f7,f8&fields2=f51,f52,f53,f54,f55,f56,f57,f58"
               f"&ut=fa5fd1575c3b838480cc8264a04e39b9")
        raw = sd.http(url, referer='https://quote.eastmoney.com/', timeout=4)
        j = json.loads(raw)
        data = j.get('data') or {}
        raw_trends = data.get('trends') or []
        pre_close = float(data.get('preClose') or 0.0)

        times = []
        prices = []
        avg_prices = []
        volumes = []
        pcts = []

        for line in raw_trends:
            p = line.split(',')
            if len(p) >= 8:
                t_str = p[0][11:16]  # '2026-09-24 09:30' -> '09:30'
                curr_p = float(p[2])
                avg_p = float(p[7])
                vol = float(p[5])
                pct = round((curr_p - pre_close) / pre_close * 100, 2) if pre_close > 0 else 0.0

                times.append(t_str)
                prices.append(curr_p)
                avg_prices.append(avg_p)
                volumes.append(vol)
                pcts.append(pct)

        res = {
            'code': pure,
            'pre_close': pre_close,
            'times': times,
            'prices': prices,
            'avg_prices': avg_prices,
            'volumes': volumes,
            'pcts': pcts,
            'source': 'eastmoney',
            'count': len(times)
        }
        _record_status("eastmoney", True, time.time() - t0)
        CACHE.set(cache_key, res, ttl=ttl)
        return res
    except Exception:
        pass

    return {'code': pure, 'pre_close': 0.0, 'times': [], 'prices': [], 'avg_prices': [], 'volumes': [], 'pcts': [], 'source': 'none', 'count': 0}

# ==========================================
# 5. 实时与多日主力资金分布 (超大单/大单/中单/小单)
# ==========================================
def get_capital_breakdown(code: str) -> Dict[str, Any]:
    """
    获取个股即时与近5日资金单笔分布（主力、超大单、大单、中单、小单净流入及占比）。
    纯原生 HTTP API 解析，无 akshare 依赖，毫秒级响应。
    """
    pure, _, secid = normalize_code(code)
    cache_key = f"cap_breakdown:{pure}"
    cached = CACHE.get(cache_key)
    if cached is not None:
        return cached

    ttl = 600.0 if is_market_closed() else 30.0

    # 1. 尝试东财 fflow 接口 (设置 1.5 秒硬超时, 绝不阻塞主线程)
    try:
        u = (f"https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
             f"?lmt=5&klt=101&secid={secid}&fields1=f1,f2,f3,f7"
             f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65"
             f"&ut=7eea3edcaed734bea9cbfc24409ed989")
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Referer': 'https://data.eastmoney.com/'
        }
        raw = sd.http(u, headers=headers, timeout=1.5, retries=1)
        j = json.loads(raw)
        klines = (j.get('data') or {}).get('klines', []) or []
        history = []
        for line in klines:
            p = line.split(',')
            if len(p) >= 7:
                history.append({
                    'date': p[0][:10],
                    'main_net': round(float(p[1]) / 1e8, 2),
                    'small_net': round(float(p[2]) / 1e8, 2),
                    'med_net': round(float(p[3]) / 1e8, 2),
                    'large_net': round(float(p[4]) / 1e8, 2),
                    'super_net': round(float(p[5]) / 1e8, 2),
                    'pct': round(float(p[6]), 1)
                })

        today_flow = history[-1] if history else {
            'date': '',
            'main_net': 0.0,
            'super_net': 0.0,
            'large_net': 0.0,
            'med_net': 0.0,
            'small_net': 0.0,
            'pct': 0.0
        }

        res = {
            'code': pure,
            'today': today_flow,
            'history': history
        }
        CACHE.set(cache_key, res, ttl=ttl)
        return res
    except Exception:
        pass

    # 2. 东财不可用时，秒级降级至腾讯盘口主动买卖单计算 (内外盘成交分析)
    fallback_res = {
        'code': pure,
        'today': {'date': dt.date.today().strftime('%Y-%m-%d'), 'main_net': 0.0, 'super_net': 0.0, 'large_net': 0.0, 'med_net': 0.0, 'small_net': 0.0, 'pct': 0.0},
        'history': []
    }
    try:
        _, full_code, _ = normalize_code(code)
        raw_tx = sd.http(f'https://qt.gtimg.cn/q={full_code}', gbk=True, timeout=1.5, retries=1)
        if '~' in raw_tx:
            f = raw_tx.split('~')
            if len(f) > 38:
                price = float(f[3]) if f[3] else 0.0
                out_vol = float(f[7]) if f[7] else 0.0 # 外盘(主动买)
                in_vol = float(f[8]) if f[8] else 0.0  # 内盘(主动卖)
                buy_amt = out_vol * 100 * price / 1e8
                sell_amt = in_vol * 100 * price / 1e8
                net = round(buy_amt - sell_amt, 2)
                total_amt = buy_amt + sell_amt
                pct = round(net / total_amt * 100, 1) if total_amt > 0 else 0.0

                fallback_res['today'] = {
                    'date': dt.date.today().strftime('%Y-%m-%d'),
                    'main_net': net,
                    # 腾讯内外盘只能算出"主动买卖净额", 不是主力单笔结构;
                    # 单笔分层(超大/大/中/小单)只有东财 fflow 接口才有 —— 所以这里留空,
                    # 不再按 55/45 比例编造(2026-09-30 修正: 编造的数字会直接画进资金结构图)
                    'super_net': None,
                    'large_net': None,
                    'med_net': None,
                    'small_net': None,
                    'pct': pct,
                    'source': 'tencent_inout',
                    'estimated': True
                }
    except Exception:
        # 修复 (2026-10-18): 原来静默 pass，兜底结果照样按正常 ttl(600s) 缓存。
        # 一次瞬时故障会把当日资金数据"锁死成 0"长达 10 分钟，且日志无痕。
        # 现在：记录失败来源，并对兜底结果用短 TTL，让下一次请求有机会拿到真数据。
        fallback_res['today']['source'] = fallback_res['today'].get('source') or 'fallback_zero'
        fallback_res['today']['stale'] = True
        CACHE.set(cache_key, fallback_res, ttl=min(ttl, 30.0))
        return fallback_res

    # 拿到真实数据才用正常 TTL
    CACHE.set(cache_key, fallback_res, ttl=ttl)
    return fallback_res

# ==========================================
# 6. 个股官方高精盘口快照 (THS Realhead)
# ==========================================
def get_stock_quote_detail(code: str) -> Optional[Dict[str, Any]]:
    """
    获取同花顺官方高精盘口快照：包含买一卖一档、涨跌停价、全天 VWAP 加权均价、换手率。
    带有 1.5 秒短缓存。
    """
    pure, _, _ = normalize_code(code)
    cache_key = f"quote_detail:{pure}"
    cached = CACHE.get(cache_key)
    if cached is not None:
        return cached

    if THSRealtimeQuote:
        t0 = time.time()
        try:
            detail = THSRealtimeQuote.get_realhead(pure)
            if detail:
                _record_status("ths", True, time.time() - t0)
                CACHE.set(cache_key, detail, ttl=1.5)
                return detail
        except Exception:
            _record_status("ths", False, time.time() - t0)
    return None

# ==========================================
# 7. 带缓存的多源日 K 线 (Multi-Source K-line)
# ==========================================
def get_kline_cached(full_code: str, days: int = 160) -> List[List[Any]]:
    cache_key = f"kline:{full_code}:{days}"
    cached = CACHE.get(cache_key)
    if cached is not None:
        return cached

    ttl = 3600.0 if is_market_closed() else 60.0
    kl = sd.kline_tx(full_code, days)
    if kl:
        CACHE.set(cache_key, kl, ttl=ttl)
    return kl

# ==========================================
# 8. 数据源状态与健康度概览
# ==========================================
def get_system_data_status() -> Dict[str, Any]:
    return {
        "sources": SOURCE_HEALTH,
        "cache": CACHE.stats(),
        "market_closed": is_market_closed(),
        "trading_today": _is_trading_today()[0],
        "quote_date": _is_trading_today()[1],
        "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
