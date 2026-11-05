# -*- coding: utf-8 -*-
"""
股票看盘 · AlphaPulse Level-1 权威数据网关与 WebSocket 推流适配器
支持真实腾讯 Level-1 五档盘口逐笔快照、通达信二进制 K 线与分时数据
"""
import sys
import os
import time
import math
import datetime
import json
import urllib.request
from typing import Dict, List, Optional, Any

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))
import data_feed as df_feed
import stock_dashboard as sd

# ---------------------------------------------------------------
# K线结果缓存：腾讯 ifzq 接口已被 WAF 封禁(HTTP 501)，每次冷启动都要
# 走完整三级降级（实测 22s）。这里缓存最终结果，避免重复踩坑。
# 交易时段 TTL 60s，休市 TTL 30min（休市期间日K不会变）。
_KLINE_RESULT_CACHE: Dict[str, Any] = {}   # key -> (ts, payload)
_KLINE_TTL_OPEN = 60.0
_KLINE_TTL_CLOSED = 1800.0


def _kline_cache_get(key: str):
    item = _KLINE_RESULT_CACHE.get(key)
    if not item:
        return None
    ts, payload = item
    ttl = _KLINE_TTL_CLOSED if df_feed.is_market_closed() else _KLINE_TTL_OPEN
    if time.time() - ts < ttl:
        return payload
    _KLINE_RESULT_CACHE.pop(key, None)
    return None


def _kline_cache_put(key: str, payload: Any):
    # 只缓存有真实数据的响应，空结果不缓存（避免把失败固化）
    if payload and payload.get('klines'):
        _KLINE_RESULT_CACHE[key] = (time.time(), payload)
    return payload


DEFAULT_WATCHLIST_SYMBOLS = [
    '600519.SH', '300750.SZ', '002594.SZ', '688981.SH',
    '300059.SZ', '601318.SH', '600036.SH', '601360.SH',
    '002230.SZ', '000858.SZ', '601899.SH', '000651.SZ',
    '000530.SZ'
]

DEFAULT_INDEX_SYMBOLS = [
    '000001.SH', '399001.SZ', '399006.SZ', '000688.SH', '000300.SH'
]


def _symbol_to_tx_code(symbol: str) -> str:
    symbol = symbol.strip()
    if '.' in symbol:
        code, market = symbol.split('.')
        return f"{market.lower()}{code}"
    if symbol.lower().startswith(('sh', 'sz', 'bj')):
        return symbol.lower()
    if symbol.startswith('920') or symbol.startswith(('4', '8')):
        return f"bj{symbol}"
    if symbol.startswith(('6', '5', '9')):
        return f"sh{symbol}"
    return f"sz{symbol}"


def _tx_code_to_symbol(tx_code: str) -> str:
    tx_code = tx_code.strip().lower()
    if tx_code.startswith('sh'):
        return f"{tx_code[2:]}.SH"
    if tx_code.startswith('bj'):
        return f"{tx_code[2:]}.BJ"
    if tx_code.startswith('sz'):
        return f"{tx_code[2:]}.SZ"
    return tx_code


def _fetch_quotes_via_fallback(symbols: List[str]) -> Dict[str, Any]:
    """当腾讯主源 qt.gtimg.cn 超时/被封时，降级到 df_feed 多级容灾（TDX / 同花顺 / 新浪）"""
    try:
        raw_map = df_feed.get_realtime_quotes(symbols) or {}
    except Exception:
        return {}
    if not raw_map:
        return {}

    now_ms = int(time.time() * 1000)
    quotes: Dict[str, Any] = {}
    for s in symbols:
        tx_code = _symbol_to_tx_code(s)
        pure = tx_code[2:]
        q = raw_map.get(pure) or raw_map.get(s)
        if not q:
            continue
        try:
            if tx_code.startswith('sh'):
                market = 'SH'
            elif tx_code.startswith('bj'):
                market = 'BJ'
            else:
                market = 'SZ'
            symbol = f"{pure}.{market}"
            price = float(q.get('price') or 0.0)
            prev_close = float(q.get('prev_close') or q.get('pre_close') or price)
            open_p = float(q.get('open') or price)
            high_p = float(q.get('high') or price)
            low_p = float(q.get('low') or price)
            chg = float(q.get('chg') or round(price - prev_close, 2))
            chg_pct = float(q.get('pct') or (round(chg / prev_close * 100, 2) if prev_close > 0 else 0.0))
            vol_hands = int(float(q.get('volume') or 0))
            amt_yuan = float(q.get('amount_raw') or 0.0)
            float_cap_yi = float(q.get('float_mcap') or 0.0)
            limit_up = float(q.get('upper_limit') or round(prev_close * 1.10, 2))
            limit_down = float(q.get('lower_limit') or round(prev_close * 0.90, 2))

            raw_bids = q.get('bids') or []
            bids = []
            for i in range(5):
                if i < len(raw_bids) and len(raw_bids[i]) >= 2:
                    bp = float(raw_bids[i][0] or 0)
                    bv = int(float(raw_bids[i][1] or 0))
                    bids.append({"level": i + 1, "price": bp if bp > 0 else None, "volume": bv})
                else:
                    bids.append({"level": i + 1, "price": None, "volume": None})

            raw_asks = q.get('asks') or []
            asks = []
            for i in range(5):
                if i < len(raw_asks) and len(raw_asks[i]) >= 2:
                    ap = float(raw_asks[i][0] or 0)
                    av = int(float(raw_asks[i][1] or 0))
                    asks.append({"level": i + 1, "price": ap if ap > 0 else None, "volume": av})
                else:
                    asks.append({"level": i + 1, "price": None, "volume": None})

            phase = 'TRADING'
            if bool(q.get('is_zt')) or (limit_up > 0 and price >= limit_up - 0.01):
                phase = 'LIMIT_UP'
            elif bool(q.get('is_dt')) or (limit_down > 0 and price <= limit_down + 0.01):
                phase = 'LIMIT_DOWN'

            quotes[symbol] = {
                'symbol': symbol,
                'code': pure,
                'market': market,
                'name': q.get('name') or pure,
                'pinyin': '',
                'sector': 'A股精选',
                'price': price,
                'prevClose': prev_close,
                'open': open_p,
                'high': high_p,
                'low': low_p,
                'change': chg,
                'changePercent': chg_pct,
                'volume': vol_hands,
                'amount': amt_yuan,
                'turnoverRate': float(q.get('turnover_rate') or 0.0),
                'volumeRatio': 1.0,
                'amplitude': round((high_p - low_p) / prev_close * 100, 2) if prev_close > 0 else 0.0,
                'peTtm': 20.0,
                'pb': 2.5,
                'marketCap': float_cap_yi,
                'floatMarketCap': float_cap_yi,
                'outerVolume': vol_hands // 2,
                'innerVolume': vol_hands - (vol_hands // 2),
                'limitUpPrice': limit_up,
                'limitDownPrice': limit_down,
                'phase': phase,
                'orderBook': {'bids': bids, 'asks': asks},
                'recentTrades': [],
                'updatedAt': now_ms,
            }
        except Exception:
            continue
    return quotes


_L1_QUOTES_CACHE: Dict[str, Any] = {'ts': 0.0, 'key': (), 'data': {}}
_L1_INDICES_CACHE: Dict[str, Any] = {'ts': 0.0, 'key': (), 'data': {}}
_L1_SHORT_TTL = 0.25  # 250ms 进程级短缓存，避免多 WS 客户端并发打爆上游


def fetch_level1_quotes(symbols: Optional[List[str]] = None) -> Dict[str, Any]:
    """从腾讯官方接口批量拉取 Level-1 真实五档盘口与快照指标"""
    if not symbols:
        symbols = DEFAULT_WATCHLIST_SYMBOLS

    tx_codes = [_symbol_to_tx_code(s) for s in symbols]
    cache_key = tuple(tx_codes)
    now_t = time.time()
    if _L1_QUOTES_CACHE['key'] == cache_key and (now_t - _L1_QUOTES_CACHE['ts'] < _L1_SHORT_TTL) and _L1_QUOTES_CACHE['data']:
        return dict(_L1_QUOTES_CACHE['data'])

    url = 'https://qt.gtimg.cn/q=' + ','.join(tx_codes)

    quotes: Dict[str, Any] = {}
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            content = resp.read().decode('gbk', errors='ignore')
    except Exception:
        # 腾讯 qt 不可用（被封/超时/网络异常）：降级到 df_feed 多级备源
        fb = _fetch_quotes_via_fallback(symbols)
        if fb:
            _L1_QUOTES_CACHE.update({'ts': time.time(), 'key': cache_key, 'data': fb})
        return fb

    now_ms = int(time.time() * 1000)
    for line in content.split(';'):
        line = line.strip()
        if not line or '=' not in line:
            continue
        try:
            tx_var, raw_data = line.split('=', 1)
            tx_code = tx_var.replace('v_', '').strip()
            parts = raw_data.strip('"').split('~')
            if len(parts) <= 45 or not parts[4] or not parts[5]:
                continue

            code = parts[2]
            name = parts[1]
            if tx_code.startswith('sh'):
                market = 'SH'
            elif tx_code.startswith('bj'):
                market = 'BJ'
            else:
                market = 'SZ'
            symbol = f"{code}.{market}"

            price = float(parts[3]) if parts[3] else 0.0
            prev_close = float(parts[4]) if parts[4] else 0.0
            open_p = float(parts[5]) if parts[5] else price
            high_p = float(parts[33]) if len(parts) > 33 and parts[33] else price
            low_p = float(parts[34]) if len(parts) > 34 and parts[34] else price
            volume_hands = int(float(parts[6])) if len(parts) > 6 and parts[6] else 0
            outer_vol = int(float(parts[7])) if len(parts) > 7 and parts[7] else 0
            inner_vol = int(float(parts[8])) if len(parts) > 8 and parts[8] else 0

            # 五档委买
            bids = []
            for i in range(5):
                p_idx = 9 + i * 2
                v_idx = 10 + i * 2
                bp = float(parts[p_idx]) if len(parts) > p_idx and parts[p_idx] else None
                bv = int(float(parts[v_idx])) if len(parts) > v_idx and parts[v_idx] else None
                bids.append({"level": i + 1, "price": bp if (bp and bp > 0) else None, "volume": bv})

            # 五档委卖
            asks = []
            for i in range(5):
                p_idx = 19 + i * 2
                v_idx = 20 + i * 2
                ap = float(parts[p_idx]) if len(parts) > p_idx and parts[p_idx] else None
                av = int(float(parts[v_idx])) if len(parts) > v_idx and parts[v_idx] else None
                asks.append({"level": i + 1, "price": ap if (ap and ap > 0) else None, "volume": av})

            chg = float(parts[31]) if len(parts) > 31 and parts[31] else 0.0
            chg_pct = float(parts[32]) if len(parts) > 32 and parts[32] else 0.0
            turnover_wan = float(parts[37]) if len(parts) > 37 and parts[37] else 0.0
            amount_yuan = turnover_wan * 10000.0
            turnover_rate = float(parts[38]) if len(parts) > 38 and parts[38] else 0.0
            amplitude = float(parts[43]) if len(parts) > 43 and parts[43] else 0.0
            market_cap_yi = float(parts[44]) if len(parts) > 44 and parts[44] else 0.0
            float_cap_yi = float(parts[45]) if len(parts) > 45 and parts[45] else market_cap_yi
            limit_up = float(parts[47]) if len(parts) > 47 and parts[47] else round(prev_close * 1.10, 2)
            limit_down = float(parts[48]) if len(parts) > 48 and parts[48] else round(prev_close * 0.90, 2)
            vol_ratio = float(parts[49]) if len(parts) > 49 and parts[49] else 1.0
            pe_ttm = float(parts[39]) if len(parts) > 39 and parts[39] else 20.0
            pb = float(parts[46]) if len(parts) > 46 and parts[46] else 2.5

            phase = 'TRADING'
            if limit_up > 0 and price >= limit_up - 0.01:
                phase = 'LIMIT_UP'
            elif limit_down > 0 and price <= limit_down + 0.01:
                phase = 'LIMIT_DOWN'

            quotes[symbol] = {
                'symbol': symbol,
                'code': code,
                'market': market,
                'name': name,
                'pinyin': '',
                'sector': 'A股精选',
                'price': price,
                'prevClose': prev_close,
                'open': open_p,
                'high': high_p,
                'low': low_p,
                'change': chg,
                'changePercent': chg_pct,
                'volume': volume_hands,
                'amount': amount_yuan,
                'turnoverRate': turnover_rate,
                'volumeRatio': vol_ratio,
                'amplitude': amplitude,
                'peTtm': pe_ttm,
                'pb': pb,
                'marketCap': market_cap_yi,
                'floatMarketCap': float_cap_yi,
                'outerVolume': outer_vol,
                'innerVolume': inner_vol,
                'limitUpPrice': limit_up,
                'limitDownPrice': limit_down,
                'phase': phase,
                'orderBook': {'bids': bids, 'asks': asks},
                'recentTrades': [],
                'updatedAt': now_ms,
            }
        except Exception:
            continue

    if not quotes:
        quotes = _fetch_quotes_via_fallback(symbols)
    if quotes:
        _L1_QUOTES_CACHE.update({'ts': time.time(), 'key': cache_key, 'data': quotes})
    return quotes


def fetch_level1_indices(symbols: Optional[List[str]] = None) -> Dict[str, Any]:
    """拉取大盘核心宽基指数实时快照"""
    if not symbols:
        symbols = DEFAULT_INDEX_SYMBOLS

    tx_codes = [_symbol_to_tx_code(s) for s in symbols]
    cache_key = tuple(tx_codes)
    now_t = time.time()
    if _L1_INDICES_CACHE['key'] == cache_key and (now_t - _L1_INDICES_CACHE['ts'] < _L1_SHORT_TTL) and _L1_INDICES_CACHE['data']:
        return dict(_L1_INDICES_CACHE['data'])

    url = 'https://qt.gtimg.cn/q=' + ','.join(tx_codes)
    indices: Dict[str, Any] = {}

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            content = resp.read().decode('gbk', errors='ignore')
    except Exception:
        return dict(_L1_INDICES_CACHE['data']) if _L1_INDICES_CACHE['data'] else indices

    for line in content.split(';'):
        line = line.strip()
        if not line or '=' not in line:
            continue
        try:
            tx_var, raw_data = line.split('=', 1)
            tx_code = tx_var.replace('v_', '').strip()
            parts = raw_data.strip('"').split('~')
            if len(parts) <= 35:
                continue
            symbol = _tx_code_to_symbol(tx_code)
            name = parts[1]
            price = float(parts[3])
            prev_close = float(parts[4])
            chg = float(parts[31]) if len(parts) > 31 and parts[31] else 0.0
            chg_pct = float(parts[32]) if len(parts) > 32 and parts[32] else 0.0
            volume_shou = float(parts[6]) if len(parts) > 6 and parts[6] else 0.0
            amount_wan = float(parts[37]) if len(parts) > 37 and parts[37] else 0.0

            indices[symbol] = {
                'symbol': symbol,
                'name': name,
                'price': price,
                'prevClose': prev_close,
                'change': chg,
                'changePercent': chg_pct,
                'volume': round(volume_shou / 1000000.0, 2),  # 亿手
                'amount': round(amount_wan / 10000.0, 1),    # 亿元
                'upCount': 0,
                'downCount': 0,
                'flatCount': 0,
            }
        except Exception:
            continue

    if indices:
        _L1_INDICES_CACHE.update({'ts': time.time(), 'key': cache_key, 'data': indices})
    return indices


def fetch_symbol_klines(symbol: str, period: str = '1D') -> Dict[str, Any]:
    """获取指定标的的 K 线或分时图序列 (TDX 缓存 + 腾讯分时)"""
    _ck = f"{symbol}:{period}"
    _hit = _kline_cache_get(_ck)
    if _hit is not None:
        return _hit
    tx_code = _symbol_to_tx_code(symbol)
    pure_code = symbol.split('.')[0] if '.' in symbol else tx_code[2:]

    if period == 'intraday':
        trends = df_feed.get_intraday_trends(pure_code)
        if not trends or 'prices' not in trends or not trends['prices']:
            return _kline_cache_put(_ck, {'symbol': symbol, 'period': 'intraday', 'prevClose': 0, 'intraday': []})

        pre_close = float(trends.get('pre_close') or trends['prices'][0])
        times = trends.get('times', [])
        prices = trends.get('prices', [])
        avg_prices = trends.get('avg_prices', [])
        volumes = trends.get('volumes', [])

        pts = []
        today_str = datetime.date.today().strftime('%Y-%m-%d')
        for i, p in enumerate(prices):
            t_str = times[i] if i < len(times) else f"09:{30+i}"
            avg_p = avg_prices[i] if i < len(avg_prices) else p
            vol = volumes[i] if i < len(volumes) else 0
            pts.append({
                'time': t_str,
                'timestamp': int(time.time()),
                'price': p,
                'avgPrice': avg_p,
                'volume': vol,
                'amount': round(vol * p * 100, 2),
                'change': round(p - pre_close, 2),
                'changePercent': round((p - pre_close) / pre_close * 100, 2) if pre_close > 0 else 0.0,
            })
        return _kline_cache_put(_ck, {
            'symbol': symbol,
            'period': 'intraday',
            'prevClose': pre_close,
            'intraday': pts,
        })
    elif period in ('5m', '15m', '30m', '60m'):
        m_map = {'5m': 'm5', '15m': 'm15', '30m': 'm30', '60m': 'm60'}
        p = m_map.get(period, 'm5')
        url = f'https://ifzq.gtimg.cn/appstock/app/kline/mkline?param={tx_code},{p},,160'
        try:
            raw = sd.http(url)
        except Exception:
            # 腾讯 K线接口被 WAF 拦截(HTTP 501)时不能冒泡成 500,
            # 置空后交给下方降级链路(df_feed / data_layer 多级容灾)兜底
            raw = None
        bars = []
        if raw:
            try:
                data = json.loads(raw).get('data', {}).get(tx_code, {})
                rows = data.get(p) or []
                for r in rows:
                    t_str = str(r[0])
                    dt_str = f'{t_str[:4]}-{t_str[4:6]}-{t_str[6:8]} {t_str[8:10]}:{t_str[10:12]}' if len(t_str) == 12 else t_str
                    ts = int(datetime.datetime.strptime(t_str, '%Y%m%d%H%M').timestamp()) if len(t_str) == 12 else 0
                    o, c, h, l = float(r[1]), float(r[2]), float(r[3]), float(r[4])
                    v = float(r[5]) if len(r) > 5 else 0.0
                    bars.append({
                        'time': dt_str,
                        'timestamp': ts,
                        'open': o,
                        'high': h,
                        'low': l,
                        'close': c,
                        'volume': v,
                        'amount': round(v * c * 100, 2),
                    })
            except Exception:
                pass
        if not bars:
            try:
                import data_layer as _dl
                for row in (_dl.min_kline(symbol, n=160, freq=period) or []):
                    dt_str = str(row[0])
                    bars.append({
                        'time': dt_str,
                        'timestamp': 0,
                        'open': float(row[1]),
                        'high': float(row[3]),
                        'low': float(row[4]),
                        'close': float(row[2]),
                        'volume': float(row[5]) if len(row) > 5 else 0.0,
                        'amount': float(row[6]) if len(row) > 6 else 0.0,
                    })
            except Exception:
                pass
        return _kline_cache_put(_ck, {
            'symbol': symbol,
            'period': period,
            'klines': bars,
        })
    elif period in ('1D', 'day', '1W', 'week', '1M', 'month'):
        p_map = {'1D': 'day', 'day': 'day', '1W': 'week', 'week': 'week', '1M': 'month', 'month': 'month'}
        p = p_map.get(period, 'day')
        url = f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={tx_code},{p},,,160,qfq'
        # 该域名已实测被腾讯 WAF 封禁（返回 501 + waf.tencent.com 拦截页）。
        # 过去每次都先请求它再超时降级（冷启动白等 ~23s），这里用熔断器短路：
        # 只要命中冷却就直接跳过，直接走 baostock 主通道。
        _host = 'web.ifzq.gtimg.cn'
        if sd._cb_is_open(_host):
            raw = None
        else:
            try:
                raw = sd.http(url)
            except Exception:
                raw = None
        bars = []
        if raw:
            try:
                data = json.loads(raw).get('data', {}).get(tx_code, {})
                rows = data.get(f'qfq{p}') or data.get(p) or []
                for r in rows:
                    try:
                        d_str = str(r[0])[:10]
                        ts = int(datetime.datetime.strptime(d_str, '%Y-%m-%d').timestamp())
                        o, c, h, l = float(r[1]), float(r[2]), float(r[3]), float(r[4])
                        v = float(r[5]) if len(r) > 5 else 0.0
                        amt = round(v * c * 100, 2)
                        if len(r) > 6 and isinstance(r[6], (int, float, str)) and not isinstance(r[6], dict):
                            try:
                                amt = float(r[6])
                            except Exception:
                                pass
                        bars.append({
                            'time': d_str,
                            'timestamp': ts,
                            'open': o,
                            'high': h,
                            'low': l,
                            'close': c,
                            'volume': v,
                            'amount': amt,
                        })
                    except Exception:
                        continue
            except Exception:
                pass
        if not bars and p in ('week', 'month'):
            # 周/月不能退回日 K。走东财/腾讯对应周期。
            try:
                import data_layer as _dl
                _rows = _dl.kline_period(symbol, days=160, period=p) or []
                for _r in _rows:
                    _d = str(_r[0])[:10]
                    bars.append({
                        'time': _d,
                        'timestamp': int(datetime.datetime.strptime(_d, '%Y-%m-%d').timestamp()),
                        'open': float(_r[1]),
                        'high': float(_r[3]),
                        'low': float(_r[4]),
                        'close': float(_r[2]),
                        'volume': float(_r[5]) if len(_r) > 5 else 0.0,
                        'amount': 0.0,
                    })
            except Exception:
                pass
        if not bars and p == 'day':
            # 日 K：腾讯被 WAF 拦时降级到 data_feed(TDX/baostock 多级容灾)。周/月禁止退回日 K。
            try:
                _rows = df_feed.get_kline_cached(tx_code, 160)
                for _r in (_rows or []):
                    try:
                        _d = str(_r[0])[:10]
                        _o, _c, _h, _l = float(_r[1]), float(_r[2]), float(_r[3]), float(_r[4])
                        _v = float(_r[5]) if len(_r) > 5 else 0.0
                        bars.append({
                            'time': _d,
                            'timestamp': int(datetime.datetime.strptime(_d, '%Y-%m-%d').timestamp()),
                            'open': _o, 'high': _h, 'low': _l, 'close': _c,
                            'volume': _v,
                            'amount': float(_r[6]) if len(_r) > 6 else _v * _c * 100,
                        })
                    except Exception:
                        continue
            except Exception:
                pass
        if bars:
            return _kline_cache_put(_ck, {
                'symbol': symbol,
                'period': period,
                'klines': bars,
            })
    else:
        # 日 K 线
        klines_raw = df_feed.get_kline_cached(tx_code, 160)
        bars = []
        if klines_raw:
            for row in klines_raw:
                try:
                    date_str = str(row[0])[:10]
                    o_p = float(row[1])
                    c_p = float(row[2])
                    h_p = float(row[3])
                    l_p = float(row[4])
                    vol = float(row[5]) if len(row) > 5 else 0.0
                    amt = float(row[6]) if len(row) > 6 else vol * c_p * 100
                    bars.append({
                        'time': date_str,
                        'timestamp': int(datetime.datetime.strptime(date_str, '%Y-%m-%d').timestamp()),
                        'open': o_p,
                        'high': h_p,
                        'low': l_p,
                        'close': c_p,
                        'volume': vol,
                        'amount': amt,
                    })
                except Exception:
                    continue
        return _kline_cache_put(_ck, {
            'symbol': symbol,
            'period': period,
            'klines': bars,
        })

fetch_intraday_and_klines = fetch_symbol_klines

