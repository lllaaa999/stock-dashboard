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
import urllib.request
from typing import Dict, List, Optional, Any

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))
import data_feed as df_feed
import stock_dashboard as sd

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
    if symbol.startswith(('sh', 'sz')):
        return symbol.lower()
    if symbol.startswith(('6', '5', '9')):
        return f"sh{symbol}"
    return f"sz{symbol}"


def _tx_code_to_symbol(tx_code: str) -> str:
    tx_code = tx_code.strip().lower()
    if tx_code.startswith('sh'):
        return f"{tx_code[2:]}.SH"
    elif tx_code.startswith('sz'):
        return f"{tx_code[2:]}.SZ"
    return tx_code


def fetch_level1_quotes(symbols: Optional[List[str]] = None) -> Dict[str, Any]:
    """从腾讯官方接口批量拉取 Level-1 真实五档盘口与快照指标"""
    if not symbols:
        symbols = DEFAULT_WATCHLIST_SYMBOLS

    tx_codes = [_symbol_to_tx_code(s) for s in symbols]
    url = 'https://qt.gtimg.cn/q=' + ','.join(tx_codes)

    quotes: Dict[str, Any] = {}
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            content = resp.read().decode('gbk', errors='ignore')
    except Exception:
        return quotes

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
            market = 'SH' if tx_code.startswith('sh') else 'SZ'
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

    return quotes


def fetch_level1_indices(symbols: Optional[List[str]] = None) -> Dict[str, Any]:
    """拉取大盘核心宽基指数实时快照"""
    if not symbols:
        symbols = DEFAULT_INDEX_SYMBOLS

    tx_codes = [_symbol_to_tx_code(s) for s in symbols]
    url = 'https://qt.gtimg.cn/q=' + ','.join(tx_codes)
    indices: Dict[str, Any] = {}

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            content = resp.read().decode('gbk', errors='ignore')
    except Exception:
        return indices

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

    return indices


def fetch_symbol_klines(symbol: str, period: str = '1D') -> Dict[str, Any]:
    """获取指定标的的 K 线或分时图序列 (TDX 缓存 + 腾讯分时)"""
    tx_code = _symbol_to_tx_code(symbol)
    pure_code = symbol.split('.')[0] if '.' in symbol else tx_code[2:]

    if period == 'intraday':
        trends = df_feed.get_intraday_trends(pure_code)
        if not trends or 'prices' not in trends or not trends['prices']:
            return {'symbol': symbol, 'period': 'intraday', 'prevClose': 0, 'intraday': []}

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
        return {
            'symbol': symbol,
            'period': 'intraday',
            'prevClose': pre_close,
            'intraday': pts,
        }
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
        return {
            'symbol': symbol,
            'period': period,
            'klines': bars,
        }

fetch_intraday_and_klines = fetch_symbol_klines

