# -*- coding: utf-8 -*-
"""
监管/异动历史服务（从 main.py 抽出的独立模块）

职责：
  1. 单票：拉真实日K + 基准指数，算异动历史(_hist) 并调用法规引擎（保持 /api/quant/regulatory 原契约）；
  2. 批量：一次请求为池内多只票算 _hist（基准指数只拉一次、个股并发受限 + 复用 mg 的 TTL 缓存），
     任何单只失败都降级成 source=unknown / available=false，绝不伪造 0。

为什么单独成模块：main.py 已 1400+ 行，超出项目自定 350 行硬上限；
F-13 修复（监管池内每只票真日K）需要新增批量路径，不应继续堆进 giant file。
"""
import math
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import data_feed as df_feed
import market_gateway as mg

# 单票缓存: {symbol: (ts, payload)}
_CACHE = {}
# 批量缓存: {(symbols...): (ts, payload)}
_BATCH_CACHE = {}
_CACHE_LOCK = threading.Lock()

_TTL_OPEN = 60.0        # 交易时段 60s
_TTL_CLOSED = 1800.0    # 休市 30min（日K不变）

# 批量上限：一次最多 40 只，超出部分显式 unknown（不静默丢弃）
MAX_BATCH = 40
# 并发上限：免费源对突发请求敏感，5 路足够把冷启动压到秒级且不触发封禁
MAX_WORKERS = 5


def _ttl():
    try:
        return _TTL_CLOSED if df_feed.is_market_closed() else _TTL_OPEN
    except Exception:
        return _TTL_OPEN


def _cache_get(cache, key):
    hit = cache.get(key)
    if not hit:
        return None
    ts, payload = hit
    if time.time() - ts < _ttl():
        return payload
    return None


def _cache_put(cache, key, payload):
    if isinstance(cache, dict):
        cache[key] = (time.time(), payload)


def sanitize_floats(obj):
    """NaN/Inf -> None；浮点统一保留 4 位，避免 JSON 序列化失败"""
    if isinstance(obj, float):
        if math.isinf(obj) or math.isnan(obj):
            return None
        return round(obj, 4)
    if isinstance(obj, dict):
        return {k: sanitize_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_floats(v) for v in obj]
    return obj


def resolve_index_symbol(symbol):
    """按交易所细则映射基准指数（920 必须先于「9 开头=沪」判断）"""
    clean_sym = str(symbol or '').strip().upper()
    code = clean_sym.split('.')[0]
    if code.startswith(('688', '689')):
        return clean_sym, code, "000688.SH"
    if code.startswith(('300', '301')):
        return clean_sym, code, "399102.SZ"
    if code.startswith('920') or code.startswith(('8', '4')) or clean_sym.endswith('.BJ'):
        return clean_sym, code, "899050.BJ"
    if code.startswith(('6', '9')) or clean_sym.endswith('.SH'):
        return clean_sym, code, "000001.SH"
    if code.startswith(('0', '3')) or clean_sym.endswith('.SZ'):
        return clean_sym, code, "399001.SZ"
    raise ValueError(
        f"无法识别标的市场板块: {symbol}，暂不支持该市场基准指数对齐 "
        "(支持6/9沪市, 0/3深市, 8/4/920北交所)"
    )


_INDEX_CTX_CACHE = {}   # {idx_symbol: (ts, ctx)}


def _index_context(idx_symbol):
    """
    基准指数上下文（同一批请求内复用，且带 TTL 缓存）：
      {curr_idx, raw_idx_bars, idx_by_date}
    """
    hit = _cache_get(_INDEX_CTX_CACHE, idx_symbol)
    if hit:
        return hit

    raw_idx_kline = mg.fetch_symbol_klines(idx_symbol, "1D")
    raw_idx_bars = raw_idx_kline.get("klines", []) if isinstance(raw_idx_kline, dict) else []
    if not raw_idx_bars:
        raise ValueError(f"无法获取基准指数日K线数据: {idx_symbol}")

    curr_idx = None
    try:
        indices = mg.fetch_level1_indices()
        if idx_symbol in indices and indices[idx_symbol].get("price") is not None:
            curr_idx = float(indices[idx_symbol]["price"])
    except Exception:
        curr_idx = None
    if curr_idx is None:
        curr_idx = float(raw_idx_bars[-1]["close"])

    idx_by_date = {}
    for i, b in enumerate(raw_idx_bars):
        d = str(b.get("time", "")).split()[0]
        prev_c = float(raw_idx_bars[i - 1]["close"]) if i > 0 else float(b.get("open", b["close"]))
        c = float(b["close"])
        idx_by_date[d] = (prev_c, c)

    ctx = {"curr_idx": curr_idx, "raw_idx_bars": raw_idx_bars, "idx_by_date": idx_by_date}
    _cache_put(_INDEX_CTX_CACHE, idx_symbol, ctx)
    return ctx


def _pct(a, b):
    return round((a / b - 1.0) * 100.0, 2) if b else None


def build_history(bars, idx_by_date, curr_idx):
    """
    用真实日K算 T-1/T-2/Today 的个股与基准指数涨跌幅（供前端 2/3 日异动模型）。
    口径与修复后的 B-P0-2 保持一致：bars[-1] 是今日收盘，hist 不含今日。
    """
    closes = {str(b.get("time", "")).split()[0]: float(b["close"]) for b in bars}
    idx_closes = {d: v[1] for d, v in idx_by_date.items()}
    dates = sorted(closes)
    hist = {"source": "kline", "available": True, "dates": dates[-3:]}
    if len(dates) >= 3:
        d_today, d_t1, d_t2 = dates[-1], dates[-2], dates[-3]
        hist["stock_return_t1"] = _pct(closes[d_t1], closes[d_t2])
        hist["stock_return_t2"] = (
            _pct(closes[d_t2], closes[dates[-4]]) if len(dates) >= 4 else None
        )
        hist["index_return_t1"] = (
            _pct(idx_closes[d_t1], idx_closes[d_t2])
            if d_t1 in idx_closes and d_t2 in idx_closes else None
        )
        hist["index_return_t2"] = (
            _pct(idx_closes[d_t2], idx_closes[dates[-4]])
            if len(dates) >= 4 and d_t2 in idx_closes and dates[-4] in idx_closes else None
        )
        # 今日基准指数涨幅：分母用昨日指数收盘，不能用今日收盘（否则恒为 0）
        yest_idx = None
        if d_today in idx_by_date:
            yest_idx = idx_by_date[d_today][0]
        elif d_t1 in idx_closes:
            yest_idx = idx_closes[d_t1]
        if yest_idx:
            hist["index_return_today"] = _pct(curr_idx, yest_idx)
        hist["date_t2"], hist["date_t1"], hist["date_today"] = d_t2, d_t1, d_today
    return hist


def _align_index_bars(bars, idx_by_date, curr_idx):
    """把个股交易日对齐到基准指数，返回 (idx_bars, match_count)，口径与单票端点一致"""
    idx_bars = []
    last_idx_val = None
    match_count = 0
    for b in bars:
        d = str(b.get("time", "")).split()[0]
        if d in idx_by_date:
            p_val, c_val = idx_by_date[d]
            last_idx_val = (p_val, c_val)
            match_count += 1
        else:
            p_val, c_val = ((last_idx_val[1], last_idx_val[1])
                            if last_idx_val else (curr_idx, curr_idx))
        idx_bars.append({"date": d, "close": c_val, "prev_close": p_val})
    return idx_bars, match_count


def _unknown(symbol, reason):
    """显式 unknown：数值一律 null，不伪造 0"""
    return {
        "source": "unknown",
        "available": False,
        "reason": str(reason)[:160],
        "dates": [],
        "stock_return_t1": None,
        "stock_return_t2": None,
        "index_return_t1": None,
        "index_return_t2": None,
        "index_return_today": None,
    }


def _fetch_stock_bars(clean_sym):
    kline_data = mg.fetch_symbol_klines(clean_sym, "1D")
    if not kline_data or not isinstance(kline_data, dict):
        raise ValueError(f"无法获取股票日K线数据: {clean_sym}")
    bars = kline_data.get("klines", [])
    if not bars:
        raise ValueError(f"股票日K线数据为空: {clean_sym}")
    return bars


def build_single_payload(symbol):
    """/api/quant/regulatory 单票契约（保持原有字段，仅新增 history.available/source 说明）"""
    key = str(symbol)
    cached = _cache_get(_CACHE, key)
    if cached:
        return cached

    import abnormal_volatility as av

    clean_sym, code, idx_symbol = resolve_index_symbol(symbol)

    is_st = False
    try:
        qmap = df_feed.get_realtime_quotes([clean_sym]) or {}
        for qv in qmap.values():
            if 'ST' in str((qv or {}).get('name') or '').upper():
                is_st = True
            break
    except Exception:
        is_st = False

    bars = _fetch_stock_bars(clean_sym)
    ctx = _index_context(idx_symbol)
    raw_idx_bars = ctx["raw_idx_bars"]
    idx_by_date = ctx["idx_by_date"]
    curr_idx = ctx["curr_idx"]

    idx_bars, match_count = _align_index_bars(bars, idx_by_date, curr_idx)
    if match_count == 0:
        raise ValueError(
            f"基准指数 {idx_symbol} 与标的 {clean_sym} 无任何重叠交易日，无法计算异动偏离"
        )

    curr_p = float(bars[-1]['close'])

    # evaluate_stock_volatility 要求 hist 不含今日；今日价单独走 curr_price。
    # 把今日收盘塞进 hist 会让昨收变成今收，涨停价算成明日价，且今日触线被当成已清零。
    if len(bars) >= 2:
        hist_src = bars[:-1]
        idx_src = idx_bars[:-1]
    else:
        hist_src = bars
        idx_src = idx_bars
    hist_bars = [
        {
            "date": str(b.get("time", "")).split()[0],
            "close": float(b["close"]),
            "prev_close": float(hist_src[i - 1]["close"] if i > 0 else b.get("open", b["close"])),
            "volume": float(b.get("volume", 1.0)),
        }
        for i, b in enumerate(hist_src)
    ]

    hist = build_history(bars, idx_by_date, curr_idx)

    res_dict = av.evaluate_stock_volatility(
        clean_sym,
        hist_bars=hist_bars,
        index_bars=idx_src,
        curr_price=curr_p,
        curr_index=curr_idx,
        is_st=is_st,
    )
    res_data = res_dict.to_dict() if hasattr(res_dict, 'to_dict') else res_dict

    payload = {
        "status": "ok",
        "symbol": symbol,
        "regulatory": sanitize_floats(res_data),
        "history": sanitize_floats(hist),
    }
    _cache_put(_CACHE, key, payload)
    return payload


def _parse_symbols(symbols_csv):
    seen, out = set(), []
    for raw in str(symbols_csv or '').split(','):
        s = raw.strip().upper()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def build_batch_payload(symbols_csv, max_batch=MAX_BATCH):
    """
    批量算池内个股 history。
    - 基准指数按市场分组，每种只拉一次；
    - 个股并发受限（MAX_WORKERS），复用 mg.fetch_symbol_klines 的 30min 日K缓存；
    - 单只失败 -> histories[sym] = _unknown(...)，unknown 列表里带 reason；
    - 超过 max_batch 的部分同样显式 unknown（reason=超过批量上限）。
    """
    symbols = _parse_symbols(symbols_csv)
    if not symbols:
        return {"status": "error", "message": "symbols 为空", "histories": {}, "unknown": []}

    cache_key = tuple(symbols) + (max_batch,)
    cached = _cache_get(_BATCH_CACHE, cache_key)
    if cached:
        return cached

    over_limit = symbols[max_batch:]
    symbols = symbols[:max_batch]

    histories, unknown = {}, []

    # 1) 先解析板块/指数，把不可识别的直接降级 unknown
    plans = {}
    for sym in symbols:
        try:
            clean_sym, code, idx_symbol = resolve_index_symbol(sym)
            plans[sym] = (clean_sym, idx_symbol)
        except Exception as e:
            histories[sym] = _unknown(sym, e)
            unknown.append({"symbol": sym, "reason": str(e)})
    for sym in over_limit:
        reason = f"超过单次批量上限 {max_batch}，请分组请求"
        histories[sym] = _unknown(sym, reason)
        unknown.append({"symbol": sym, "reason": reason})

    # 2) 指数上下文（同一市场只拉一次）
    idx_errors = {}
    for idx_symbol in sorted({v[1] for v in plans.values()}):
        try:
            _index_context(idx_symbol)
        except Exception as e:
            idx_errors[idx_symbol] = str(e)

    # 3) 并发拉个股日K，上限 MAX_WORKERS
    results = {}
    ok_syms = [s for s in plans if plans[s][1] not in idx_errors]
    for sym in plans:
        if sym not in ok_syms:
            reason = f"基准指数不可用: {idx_errors.get(plans[sym][1])}"
            histories[sym] = _unknown(sym, reason)
            unknown.append({"symbol": sym, "reason": reason})

    if ok_syms:
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(ok_syms))) as ex:
            fut_map = {ex.submit(_fetch_stock_bars, plans[s][0]): s for s in ok_syms}
            for fut in as_completed(fut_map):
                sym = fut_map[fut]
                try:
                    results[sym] = fut.result()
                except Exception as e:
                    histories[sym] = _unknown(sym, e)
                    unknown.append({"symbol": sym, "reason": str(e)})

    # 4) 单线程算 _hist（纯计算，无网络，避免线程里碰全局缓存）
    for sym, bars in results.items():
        idx_symbol = plans[sym][1]
        try:
            ctx = _INDEX_CTX_CACHE[idx_symbol][1]
            idx_bars, match_count = _align_index_bars(bars, ctx["idx_by_date"], ctx["curr_idx"])
            if match_count == 0:
                raise ValueError("与基准指数无重叠交易日")
            histories[sym] = sanitize_floats(build_history(bars, ctx["idx_by_date"], ctx["curr_idx"]))
        except Exception as e:
            histories[sym] = _unknown(sym, e)
            unknown.append({"symbol": sym, "reason": str(e)})

    payload = {
        "status": "ok",
        "requested": len(symbols) + len(over_limit),
        "available": sum(1 for h in histories.values() if h.get("available")),
        "unknown": unknown,
        "histories": histories,
    }
    _cache_put(_BATCH_CACHE, cache_key, payload)
    return payload


def build_payload(symbol="000530.SZ", symbols=""):
    """统一入口：给了 symbols 走批量，否则走单票（原契约）"""
    if str(symbols or '').strip():
        return build_batch_payload(symbols)
    return build_single_payload(symbol)


def clear_caches():
    """测试/调试用：清空进程内缓存"""
    with _CACHE_LOCK:
        _CACHE.clear()
        _BATCH_CACHE.clear()
        _INDEX_CTX_CACHE.clear()
