# -*- coding: utf-8 -*-
"""股票看盘 · 七层雷达 可视化仪表盘 (FastAPI)"""
import sys, os, json, datetime, time, re, asyncio
import numpy as np
dt = datetime
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))
import stock_dashboard as sd
import strategies_lib as strat_lib
import auction_radar as ar
import data_feed as df_feed
import strategic_decision as strat_dec
import backtest_engine as bt_engine
import paper_trading as paper

def _normalize_stock_code(raw_code: str) -> str:
    """自动将 sh600519 / 600519.SH / sz000001 / ' 600519 ' 归一化为纯6位数字代码"""
    if not raw_code:
        return ""
    raw = str(raw_code).strip()
    m = re.search(r'\b(\d{6})\b', raw)
    if m:
        return m.group(1)
    digits = re.findall(r'\d+', raw)
    if digits:
        joined = "".join(digits)
        if len(joined) >= 6:
            return joined[:6]
    return raw


from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import market_gateway as mg
import quant_data_service as qds

app = FastAPI(title="股票看盘 · 七层雷达")

# 唯一前端：React 构建产物 (frontend/ -> vite build -> 自动同步到 web/dist)
WEB_DIR = os.path.dirname(os.path.abspath(__file__))
dist_dir = os.path.join(WEB_DIR, 'dist')
if os.path.exists(os.path.join(dist_dir, 'assets')):
    app.mount("/assets", StaticFiles(directory=os.path.join(dist_dir, 'assets')), name="assets")

HIST_LOCAL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'stock_data', 'sentiment_history.jsonl')
HIST = HIST_LOCAL if os.path.exists(HIST_LOCAL) else os.path.join(sd.DATA_DIR, 'sentiment_history.jsonl')

_market_cache = {
    'data': None,
    'timestamp': 0.0,
    # 2026-09-30: 首页"缓存命中"原来读的是 data_feed 那套(行情快照)缓存, 而大盘页实际
    # 走这个 _market_cache —— 于是首页永远显示 0%, 看着像坏了。这里补上自己的计数。
    'hits': 0,
    'misses': 0,
    'last_refresh_s': None,
}

# 交易日历缓存 (上证指数日K日期集合)，避免每个请求都打网络
_TRADING_DAYS_CACHE = {'dates': None, 'ts': 0.0}


def _get_market_ttl() -> float:
    """动态 TTL：交易时段 6 秒, 其余时段 60 秒。

    2026-09-30: 改用 data_feed.is_market_closed() 统一判定 —— 原实现把午休和节假日
    都算作盘中, 长假里页面开着会 6 秒一次白刷上游。
    """
    return 60.0 if df_feed.is_market_closed() else 6.0


def _is_real_trading_day(ymd):
    """判断 ymd 是否为真实交易日（以上证指数日K为准）

    上游多个行情接口对非交易日不返回空，而是回吐最近交易日快照，
    因此"有没有数据"不能作为交易日判据。这里统一走日K日历，
    并带进程内缓存避免每次请求都打网络。取不到日历则保守返回 False。
    """
    now_ts = time.time()
    if _TRADING_DAYS_CACHE['dates'] is not None and now_ts - _TRADING_DAYS_CACHE['ts'] < 600:
        return ymd in _TRADING_DAYS_CACHE['dates']
    try:
        kl = sd.kline_tx('sh000001', 120)
        dates = {str(r[0])[:10].replace('-', '') for r in (kl or [])}
        dates = {d for d in dates if len(d) == 8 and d.isdigit()}
        if dates:
            _TRADING_DAYS_CACHE['dates'] = dates
            _TRADING_DAYS_CACHE['ts'] = now_ts
            return ymd in dates
    except Exception:
        pass
    return False


def read_hist():
    records_by_date = {}
    candidate_paths = [
        HIST_LOCAL,
        os.path.join(sd.DATA_DIR, 'sentiment_history.jsonl'),
        os.path.expanduser('~/.hermes/stock_data/sentiment_history.jsonl'),
    ]
    for p in candidate_paths:
        if os.path.exists(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            r = json.loads(line)
                            d_key = str(r.get('date', ''))
                            if d_key:
                                records_by_date[d_key] = r
            except Exception:
                pass

    # 若今日情绪已产生且尚未落盘，动态拼入今日点使折线实时连贯
    # 修复 (2026-10-18): 原先无条件把"今天"拼进曲线。但休市日（周末/节假日）
    # 上游涨停池接口会回吐最近一个交易日的快照，于是曲线里会凭空多出一个
    # 周末点，且数值与前一交易日完全重复，同时把真实交易日挤成"缺失"。
    # 情绪曲线只允许出现真实交易日：先校验今天是否交易日，再用日K核对
    # 该点数值是否与前一个交易日完全相同（回吐特征），任一不满足则不拼入。
    now_ymd = datetime.date.today().strftime('%Y%m%d')
    if _market_cache.get('data') and _market_cache['data'].get('emotion'):
        emo = _market_cache['data']['emotion']
        if emo.get('score') is not None and now_ymd not in records_by_date:
            if _is_real_trading_day(now_ymd):
                _new = {
                    'date': now_ymd,
                    'score': emo.get('score'),
                    'band': emo.get('band'),
                    'zt': emo.get('zt_count') or emo.get('zt'),
                    'zb': emo.get('zb_count') or emo.get('zb'),
                    'dt': emo.get('dt_count') or emo.get('dt'),
                    'max_lb': emo.get('max_lb'),
                    'stage': emo.get('stage')
                }
                # 回吐检测：与最近一个既有交易日四项全同 -> 视为同一份数据，不重复画点
                _prev_keys = [k for k in records_by_date if k < now_ymd]
                _echo = False
                if _prev_keys:
                    _p = records_by_date[max(_prev_keys)]
                    try:
                        _echo = (int(_p.get('zt') or -1) == int(_new['zt'] or -2)
                                 and int(_p.get('zb') or -1) == int(_new['zb'] or -2)
                                 and int(_p.get('dt') or -1) == int(_new['dt'] or -2)
                                 and int(_p.get('max_lb') or -1) == int(_new['max_lb'] or -2))
                    except Exception:
                        _echo = False
                if not _echo:
                    records_by_date[now_ymd] = _new

    return sorted(records_by_date.values(), key=lambda r: str(r.get('date', '')))

DEFAULT_WATCHLIST_SYMBOLS = [
    '600519.SH', '300750.SZ', '002594.SZ', '000530.SZ',
    '002466.SZ', '601318.SH', '000001.SZ', '000063.SZ'
]

@app.get("/")
def index():
    dist_index = os.path.join(dist_dir, 'index.html')
    if os.path.exists(dist_index):
        return FileResponse(dist_index)
    return JSONResponse(
        {
            "status": "error",
            "message": "前端产物缺失: web/dist/index.html。请在 frontend/ 执行 bun run build（构建后会自动同步到 web/dist）。",
        },
        status_code=503,
    )


@app.get("/api/health")
def api_health():
    dist_ok = os.path.isfile(os.path.join(dist_dir, 'index.html'))
    return JSONResponse(
        {
            "status": "ok" if dist_ok else "degraded",
            "frontend": "react-dist" if dist_ok else "missing",
            "dist_dir": dist_dir,
            "server_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    )

@app.get("/vite.svg")
@app.get("/apple-touch-icon.png")
@app.get("/registerSW.js")
@app.get("/sw.js")
@app.get("/manifest.webmanifest")
@app.get("/icon.svg")
@app.get("/pwa-192x192.png")
@app.get("/pwa-512x512.png")
@app.get("/pwa-maskable-512x512.png")
def serve_pwa_static_file(request: Request):
    filename = request.url.path.lstrip('/')
    f = os.path.join(dist_dir, filename)
    if os.path.isfile(f):
        return FileResponse(f)
    return JSONResponse({"status": "not found"}, status_code=404)

@app.get("/workbox-{wb_hash:path}")
def serve_workbox(wb_hash: str):
    f = os.path.join(dist_dir, f"workbox-{wb_hash}")
    if os.path.isfile(f):
        return FileResponse(f)
    return JSONResponse({"status": "not found"}, status_code=404)

@app.get("/api/market/search")
def api_market_search(q: str = ""):
    q = q.strip()
    if not q:
        return JSONResponse({"status": "ok", "results": []})
    try:
        import urllib.request, urllib.parse
        encoded_q = urllib.parse.quote(q)
        url = f"https://searchapi.eastmoney.com/api/suggest/get?type=14&token=4f22e26c03c09e1f3e9f416a787d5f72&input={encoded_q}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        items = (data.get('QuotationCodeTable') or {}).get('Data') or []
        results = []
        syms_to_fetch = []
        for x in items[:15]:
            c = str(x.get('Code', '')).strip()
            name = str(x.get('Name', '')).strip()
            pinyin = str(x.get('PinYin', '')).strip()
            if not c or len(c) != 6:
                continue
            suffix = '.SH' if c.startswith(('6', '9')) else ('.BJ' if c.startswith(('4', '8')) else '.SZ')
            symbol = f"{c}{suffix}"
            syms_to_fetch.append(symbol)
            results.append({
                "symbol": symbol,
                "code": c,
                "name": name,
                "pinyin": pinyin,
                "market": suffix[1:],
                "securityType": x.get('SecurityTypeName', '')
            })
        if syms_to_fetch:
            quotes = mg.fetch_level1_quotes(syms_to_fetch)
            for r in results:
                q_obj = quotes.get(r['symbol'])
                if q_obj:
                    r['price'] = q_obj.get('price', 0.0)
                    r['changePercent'] = q_obj.get('changePercent', 0.0)
                    r['change'] = q_obj.get('change', 0.0)
                    r['volume'] = q_obj.get('volume', 0)
                    r['amount'] = q_obj.get('amount', 0)
                    r['turnoverRate'] = q_obj.get('turnoverRate', 0.0)
                    r['quote'] = q_obj
        return JSONResponse({"status": "ok", "results": results})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e), "results": []}, status_code=500)

def _attach_ultra_short(quotes: dict) -> dict:
    """给 L1 报价补上 ultraShort（连板身位/首封时间/封单/竞价开盘等真实字段）。

    为什么必须补：前端 ultraShortQuant 的连板梯队、身位、晋级率全部读
    quote.ultraShort.consecutiveBoards，缺这个字段时一律退化成 0（"最高 0 连板"）。
    数据全部来自东财涨停池/炸板池，取不到就**不塞**该字段（前端保留旧值），
    绝不用 0 或硬编码常量冒充。
    """
    for sym, q in list(quotes.items()):
        if not isinstance(q, dict):
            continue
        try:
            us = qds.get_ultra_short_profile(sym, q)
        except Exception:
            us = None
        if us:
            q['ultraShort'] = us
    return quotes


@app.get("/api/market/quote/{symbol}")
def api_market_quote(symbol: str):
    try:
        clean_sym = symbol.strip()
        if not ('.' in clean_sym):
            suffix = '.SH' if clean_sym.startswith(('6', '9')) else ('.BJ' if clean_sym.startswith(('4', '8')) else '.SZ')
            clean_sym = f"{clean_sym}{suffix}"
        quotes = mg.fetch_level1_quotes([clean_sym])
        quote = quotes.get(clean_sym)
        if not quote and quotes:
            quote = list(quotes.values())[0]
        if not quote:
            return JSONResponse({"status": "not_found", "message": "Quote not available"}, status_code=404)
        _attach_ultra_short({clean_sym: quote})
        return JSONResponse({"status": "ok", "symbol": clean_sym, "quote": quote})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.get("/api/market/snapshot")
def api_market_snapshot():
    quotes = mg.fetch_level1_quotes(DEFAULT_WATCHLIST_SYMBOLS)
    _attach_ultra_short(quotes)
    indices = mg.fetch_level1_indices()
    return JSONResponse({
        "quotes": quotes,
        "indices": indices,
        "batchWindowMs": 150,
        "serverTime": int(time.time() * 1000)
    })

@app.get("/api/market/klines/{symbol}")
def api_market_klines(symbol: str, period: str = "1D"):
    return JSONResponse(mg.fetch_intraday_and_klines(symbol, period))

@app.post("/api/market/scenario")
async def api_market_scenario(request: Request):
    try:
        body = await request.json()
        symbol = body.get("symbol", "000530.SZ")
        quotes = mg.fetch_level1_quotes([symbol])
        quote = quotes.get(symbol) or (list(quotes.values())[0] if quotes else {})
        return JSONResponse({"ok": True, "quote": quote})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

_auction_radar_cache = {"data": None, "ts": 0}

@app.get("/api/quant/auction_radar")
def api_quant_auction_radar():
    global _auction_radar_cache
    now = time.time()
    if _auction_radar_cache["data"] and (now - _auction_radar_cache["ts"] < 5.0):
        return JSONResponse(_auction_radar_cache["data"])

    try:
        def to_sym(c):
            c = str(c).strip().zfill(6)
            if c.startswith(('6', '9')):
                return c + '.SH'
            elif c.startswith(('4', '8')):
                return c + '.BJ'
            return c + '.SZ'

        r = ar.get_auction_radar() or {}
        radar_items = []
        seen = set()
        # 金额口径：'auction' = 真正的 9:25 竞价额；'intraday' = 开盘后累计成交额（占昨比含义不同）
        _basis = r.get('amount_basis') or 'auction'
        _amt_label = '竞价占昨比' if _basis == 'auction' else '当日成交占昨比'

        # 顺序即优先级：核按钮/大面榜先入，避免「跌停放巨量」被 boom 榜当成抢筹后
        # 因 symbol 已存在被去重跳过（2026-10-26 三峡新材 600293 实证）。
        for item in r.get('big_loss', []):
            code = str(item.get('code')).zfill(6)
            sym = to_sym(code)
            if sym in seen: continue
            seen.add(sym)
            amt_yi = float(item.get('amount_yi', 0.0) or 0.0)
            ratio_pct = float(item.get('amount_ratio_pct', 0.0) or 0.0)
            radar_items.append({
                'symbol': sym,
                'code': code,
                'name': item.get('name', code),
                'auctionPrice': float(item.get('price', 0.0) or 0.0),
                'auctionChangePercent': float(item.get('pct', 0.0) or 0.0),
                'auctionAmount': round(amt_yi * 1e8, 2),
                'yesterdayAmount': round((amt_yi * 1e8) / (ratio_pct / 100.0), 2) if ratio_pct > 0 else 0.0,
                'amountToYesterdayRatio': ratio_pct,
                'auctionVolumeRatio': float(item.get('vol_ratio', 1.0) or 1.0),
                'unmatchedHands': int((item.get('total_bid_vol', 0) or 0) - (item.get('total_ask_vol', 0) or 0)),
                'amountBasis': _basis,
                'signal': 'NUCLEAR_BUTTON',
                'signalLabel': '竞价核按钮',
                'signalReason': item.get('reason') or f"深水大面踩踏，竞价重挫 {item.get('pct')}%",
                'trapWarning': True,
            })


        for item in r.get('weak_to_strong', []):
            code = str(item.get('code')).zfill(6)
            sym = to_sym(code)
            if sym in seen: continue
            seen.add(sym)
            amt_yi = float(item.get('amount_yi', 0.0) or 0.0)
            ratio_pct = float(item.get('amount_ratio_pct', 0.0) or 0.0)
            radar_items.append({
                'symbol': sym,
                'code': code,
                'name': item.get('name', code),
                'auctionPrice': float(item.get('price', 0.0) or 0.0),
                'auctionChangePercent': float(item.get('pct', 0.0) or 0.0),
                'auctionAmount': round(amt_yi * 1e8, 2),
                'yesterdayAmount': round((amt_yi * 1e8) / (ratio_pct / 100.0), 2) if ratio_pct > 0 else 0.0,
                'amountToYesterdayRatio': ratio_pct,
                'auctionVolumeRatio': float(item.get('vol_ratio', 1.0) or 1.0),
                'unmatchedHands': int((item.get('total_bid_vol', 0) or 0) - (item.get('total_ask_vol', 0) or 0)),
                'amountBasis': _basis,
                'signal': 'WEAK_TO_STRONG',
                'signalLabel': '分歧弱转强',
                'signalReason': item.get('reason') or f"昨分歧释放，今竞价高开反包，{_amt_label} {ratio_pct}%",
                'trapWarning': bool(item.get('is_fake_high_open', False)),
            })

        for item in r.get('auction_boom', []):
            code = str(item.get('code')).zfill(6)
            sym = to_sym(code)
            if sym in seen: continue
            seen.add(sym)
            is_locked = bool(item.get('is_one_word') or float(item.get('order_ratio', 0) or 0) >= 99.0)
            amt_yi = float(item.get('amount_yi', 0.0) or 0.0)
            ratio_pct = float(item.get('amount_ratio_pct', 0.0) or 0.0)
            radar_items.append({
                'symbol': sym,
                'code': code,
                'name': item.get('name', code),
                'auctionPrice': float(item.get('price', 0.0) or 0.0),
                'auctionChangePercent': float(item.get('pct', 0.0) or 0.0),
                'auctionAmount': round(amt_yi * 1e8, 2),
                'yesterdayAmount': round((amt_yi * 1e8) / (ratio_pct / 100.0), 2) if ratio_pct > 0 else 0.0,
                'amountToYesterdayRatio': ratio_pct,
                'auctionVolumeRatio': float(item.get('vol_ratio', 1.0) or 1.0),
                'unmatchedHands': int((item.get('total_bid_vol', 0) or 0) - (item.get('total_ask_vol', 0) or 0)),
                'amountBasis': _basis,
                'signal': 'LOCKED_LIMIT_UP' if is_locked else 'SUPER_GRAB',
                'signalLabel': '一字巨封顶板' if is_locked else '超预期抢筹',
                'signalReason': item.get('reason') or f"抢筹异动，{_amt_label} {ratio_pct}%",
                'trapWarning': bool(item.get('is_fake_high_open', False)),
            })

        grabCount = sum(1 for it in radar_items if it['signal'] in ('SUPER_GRAB', 'LOCKED_LIMIT_UP'))
        nuclearCount = sum(1 for it in radar_items if it['signal'] == 'NUCLEAR_BUTTON')
        weakToStrongCount = sum(1 for it in radar_items if it['signal'] == 'WEAK_TO_STRONG')
        highlightStocks = radar_items[:6]  # signal 从未赋值 'NORMAL'，原过滤恒真

        resp = {
            "status": "ok",
            "radar_items": radar_items,
            "grabCount": grabCount,
            "nuclearCount": nuclearCount,
            "weakToStrongCount": weakToStrongCount,
            # 原来写死 0，前端"竞价砸盘"卡片永远是 0。这里改为按实际信号统计
            # （当前映射未产出 OVERHEAT_DUMP 分类，所以仍为 0，但至少是算出来的，不是常量）
            "dumpCount": sum(1 for it in radar_items if it['signal'] == 'OVERHEAT_DUMP'),
            "highlightStocks": highlightStocks,
            "amount_basis": _basis,
            "promotion_metrics": r.get('promotion_metrics', {}),
            "premium_summary": r.get('premium_summary', {}),
            "timestamp": int(time.time() * 1000)
        }
        _auction_radar_cache["data"] = resp
        _auction_radar_cache["ts"] = now
        return JSONResponse(resp)
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# ---------- 全市场竞价扫描（独立于接力雷达，两套并行） ----------
_full_scan_cache = {"data": None, "ts": 0}

@app.get("/api/quant/full_market_scan")
def api_quant_full_market_scan():
    """全市场竞价扫描：东财clist一次拉全A股，严格阈值信号判定。
    与接力雷达完全独立，5秒缓存。
    """
    global _full_scan_cache
    now = time.time()
    if _full_scan_cache["data"] and (now - _full_scan_cache["ts"] < 5.0):
        return JSONResponse(_full_scan_cache["data"])

    try:
        result = ar.get_full_market_auction_scan()
        _full_scan_cache["data"] = result
        _full_scan_cache["ts"] = now
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


_REG_CACHE: dict = {}          # {symbol: (ts, payload)}
_REG_TTL_OPEN = 60.0           # 交易时段 60s
_REG_TTL_CLOSED = 1800.0       # 休市 30min（日K不变，监管仓位无需频繁重算）


@app.get("/api/quant/regulatory")
def api_quant_regulatory(symbol: str = "000530.SZ"):
    # 该端点每次都要拉 160 根日K + 全量指数（实测冷启动 2.5s），
    # 而结果在同一天的收盘价不变，故按 symbol 做 TTL 缓存。
    _now = time.time()
    _hit = _REG_CACHE.get(symbol)
    if _hit:
        _ts, _payload = _hit
        _ttl = _REG_TTL_CLOSED if df_feed.is_market_closed() else _REG_TTL_OPEN
        if _now - _ts < _ttl:
            return JSONResponse(_payload)
    try:
        import abnormal_volatility as av
        clean_sym = symbol.strip().upper()
        code = clean_sym.split('.')[0]
        if code.startswith(('6', '9')) or clean_sym.endswith('.SH'):
            idx_symbol = "000001.SH"
        elif code.startswith(('0', '3')) or clean_sym.endswith('.SZ'):
            idx_symbol = "399001.SZ"
        elif code.startswith(('8', '4')) or clean_sym.endswith('.BJ'):
            idx_symbol = "899050.BJ"
        else:
            raise ValueError(f"无法识别标的市场板块: {symbol}，暂不支持该市场基准指数对齐 (支持6/9沪市, 0/3深市, 8/4北交所)")

        kline_data = mg.fetch_symbol_klines(clean_sym, "1D")
        if not kline_data or not isinstance(kline_data, dict):
            raise ValueError(f"无法获取股票日K线数据: {clean_sym}")
        bars = kline_data.get("klines", [])
        if not bars:
            raise ValueError(f"股票日K线数据为空: {clean_sym}")

        raw_idx_kline = mg.fetch_symbol_klines(idx_symbol, "1D")
        raw_idx_bars = raw_idx_kline.get("klines", []) if isinstance(raw_idx_kline, dict) else []
        if not raw_idx_bars:
            raise ValueError(f"无法获取基准指数日K线数据: {idx_symbol}")

        indices = mg.fetch_level1_indices()
        if idx_symbol in indices and indices[idx_symbol].get("price") is not None:
            curr_idx = float(indices[idx_symbol]["price"])
        else:
            curr_idx = float(raw_idx_bars[-1]["close"])

        curr_p = float(bars[-1]['close'])

        idx_by_date = {}
        for i, b in enumerate(raw_idx_bars):
            d = str(b.get("time", "")).split()[0]
            prev_c = float(raw_idx_bars[i - 1]["close"]) if i > 0 else float(b.get("open", b["close"]))
            c = float(b["close"])
            idx_by_date[d] = (prev_c, c)

        idx_bars = []
        last_idx_val = None
        fill_count = 0
        match_count = 0
        for b in bars:
            d = str(b.get("time", "")).split()[0]
            if d in idx_by_date:
                p_val, c_val = idx_by_date[d]
                last_idx_val = (p_val, c_val)
                match_count += 1
            else:
                fill_count += 1
                p_val, c_val = (last_idx_val[1], last_idx_val[1]) if last_idx_val else (curr_idx, curr_idx)
            idx_bars.append({"date": d, "close": c_val, "prev_close": p_val})

        if match_count == 0:
            raise ValueError(f"基准指数 {idx_symbol} 与标的 {clean_sym} 无任何重叠交易日，无法计算异动偏离")

        fill_ratio = fill_count / len(bars)
        hist_bars = [
            {
                "date": str(b.get("time", "")).split()[0],
                "close": float(b["close"]),
                "prev_close": float(bars[i - 1]["close"] if i > 0 else b.get("open", b["close"])),
                "volume": float(b.get("volume", 1.0))
            }
            for i, b in enumerate(bars)
        ]

        # T-1 / T-2 真实涨跌幅（供前端 2/3 日模型使用，替换掉那边的 ?? 5.2 / ?? 4.8 默认值）。
        # 数据就来自上面已经取到的 K 线，不额外发请求。
        def _pct(a: float, b: float):
            return round((a / b - 1.0) * 100.0, 2) if b else None

        _closes = {str(b.get("time", "")).split()[0]: float(b["close"]) for b in bars}
        _idx_closes = {d: v[1] for d, v in idx_by_date.items()}
        _dates = sorted(_closes)
        _hist = {"source": "kline", "dates": _dates[-3:]}
        if len(_dates) >= 3:
            _d_today, _d_t1, _d_t2 = _dates[-1], _dates[-2], _dates[-3]
            _hist["stock_return_t1"] = _pct(_closes[_d_t1], _closes[_d_t2])
            _hist["stock_return_t2"] = (
                _pct(_closes[_d_t2], _closes[_dates[-4]]) if len(_dates) >= 4 else None
            )
            _hist["index_return_t1"] = (
                _pct(_idx_closes[_d_t1], _idx_closes[_d_t2])
                if _d_t1 in _idx_closes and _d_t2 in _idx_closes else None
            )
            _hist["index_return_t2"] = (
                _pct(_idx_closes[_d_t2], _idx_closes[_dates[-4]])
                if len(_dates) >= 4 and _d_t2 in _idx_closes and _dates[-4] in _idx_closes else None
            )
            # 今日基准指数涨幅：优先用实时指数价对昨收
            if _d_today in _idx_closes:
                _hist["index_return_today"] = _pct(curr_idx, _idx_closes[_d_today])
            _hist["date_t2"], _hist["date_t1"], _hist["date_today"] = _d_t2, _d_t1, _d_today

        res_dict = av.evaluate_stock_volatility(
            clean_sym,
            hist_bars=hist_bars,
            index_bars=idx_bars,
            curr_price=curr_p,
            curr_index=curr_idx
        )

        res_data = res_dict.to_dict() if hasattr(res_dict, 'to_dict') else res_dict
        import math
        def sanitize_floats(obj):
            if isinstance(obj, float):
                if math.isinf(obj) or math.isnan(obj):
                    return None
                return round(obj, 4)
            elif isinstance(obj, dict):
                return {k: sanitize_floats(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [sanitize_floats(v) for v in obj]
            return obj
        clean_res = sanitize_floats(res_data)

        payload = {
            "status": "ok",
            "symbol": symbol,
            "regulatory": clean_res,
            "history": sanitize_floats(_hist)
        }
        _REG_CACHE[symbol] = (time.time(), payload)
        return JSONResponse(payload)
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
@app.get("/api/quant/dragon_tiger")
def api_quant_dragon_tiger(symbol: str = "000530.SZ"):
    try:
        res = qds.get_real_dragon_tiger(symbol)
        return JSONResponse(res)
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.get("/api/quant/ladder")
def api_quant_ladder():
    try:
        res = qds.get_real_ladder()
        return JSONResponse(res)
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

# 缠论结构缓存: symbol -> (ts, payload)，纯算力但日K要拉网络，故按 symbol 缓存 5 分钟
_CHAN_CACHE = {}
_theme_resonance_cache = {"data": None, "ts": 0}

@app.get("/api/quant/theme_resonance")
def api_quant_theme_resonance():
    global _theme_resonance_cache
    now = time.time()
    if _theme_resonance_cache["data"] and (now - _theme_resonance_cache["ts"] < 10.0):
        return JSONResponse(_theme_resonance_cache["data"])
    try:
        res = qds.get_real_theme_resonance()
        _theme_resonance_cache["data"] = res
        _theme_resonance_cache["ts"] = now
        return JSONResponse(res)
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.get("/api/quant/chan/{symbol}")
def api_quant_chan(symbol: str, days: int = 200, period: str = "1D"):
    """缠论结构（分型/笔/中枢/背驰/买卖点）。

    为什么要单独一个端点：K线接口 /api/market/klines 只给 OHLC，缠论要另外算；
    这里用与图表同源的日K喂给 core.chan，保证"图上画的笔"和"报出的买卖点"是同一批数据。
    纯 CPU 计算（200 根约几毫秒），按 symbol+period 缓存 5 分钟。
    """
    valid_periods = {"5m", "15m", "30m", "60m", "1D", "1W", "1M"}
    safe_period = period if period in valid_periods else "1D"
    _now = time.time()
    try:
        clean_sym = (symbol or '').strip().upper()
        if '.' not in clean_sym:
            suffix = '.SH' if clean_sym.startswith(('6', '9')) else ('.BJ' if clean_sym.startswith(('4', '8')) else '.SZ')
            clean_sym = f"{clean_sym}{suffix}"
        _cache_key = f"{clean_sym}:{safe_period}"
        # 缓存TTL按周期分级：分钟K新笔可能几分钟内形成，短TTL及时反映；
        # 日/周/月K结构变化慢，长TTL省CPU（原硬编码300s对5分钟K太长）。
        _CHAN_TTL = {"5m": 60, "15m": 120, "30m": 180, "60m": 180,
                     "1D": 300, "1W": 600, "1M": 1200}
        _ttl = _CHAN_TTL.get(safe_period, 300)
        _hit = _CHAN_CACHE.get(_cache_key)
        if _hit and _now - _hit[0] < _ttl:
            return JSONResponse(_hit[1])
        # 简单上限：超过 200 个 key 时清掉最早的 50 个，防止长时间运行内存膨胀
        if len(_CHAN_CACHE) > 200:
            for _k in sorted(_CHAN_CACHE, key=lambda k: _CHAN_CACHE[k][0])[:50]:
                _CHAN_CACHE.pop(_k, None)
        kd = mg.fetch_symbol_klines(clean_sym, safe_period) or {}
        bars = kd.get("klines") or []
        if len(bars) < 30:
            raise ValueError(f"{safe_period} K线不足30根({len(bars)})，无法构建缠论结构: {clean_sym}")
        # core.chan 入参格式: [时间, 开, 收, 高, 低, 量]
        # 时间字段保留完整格式：日/周/月K为 YYYY-MM-DD，分钟K为 YYYY-MM-DD HH:mm。
        # 之前 split()[0] 会把分钟K截成纯日期，导致同一天多根K的笔端点被前端错误对齐到当日首根。
        kl = []
        for b in bars[-max(30, min(int(days or 200), 500)):]:
            kl.append([
                str(b.get("time", "")),
                float(b["open"]), float(b["close"]),
                float(b["high"]), float(b["low"]),
                float(b.get("volume", 0) or 0),
            ])
        _period_label = {"5m": "5分钟", "15m": "15分钟", "30m": "30分钟",
                         "60m": "60分钟", "1D": "日线", "1W": "周线", "1M": "月线"}.get(safe_period, "日线")
        chan = sd.chan_analysis_structured(kl, clean_sym, period_label=_period_label)
        payload = {
            "status": "ok",
            "symbol": clean_sym,
            "period": safe_period,
            "bars": len(kl),
            "chan": chan,
            "updatedAt": int(time.time() * 1000),
        }
        _CHAN_CACHE[_cache_key] = (_now, payload)
        return JSONResponse(payload)
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    subscribed_symbols = list(DEFAULT_WATCHLIST_SYMBOLS)
    batch_window_ms = 150
    try:
        init_quotes = mg.fetch_level1_quotes(subscribed_symbols)
        _attach_ultra_short(init_quotes)
        init_indices = mg.fetch_level1_indices()
        init_msg = {
            "type": "INIT_SNAPSHOT",
            "quotes": list(init_quotes.values()),
            "indices": list(init_indices.values()),
            "batchWindowMs": batch_window_ms,
            "serverTime": int(time.time() * 1000)
        }
        await websocket.send_text(json.dumps(init_msg))
    except Exception as e:
        print(f"[WS] INIT_SNAPSHOT 发送失败: {e}", flush=True)
        try:
            await websocket.send_text(json.dumps({"type": "ERROR", "message": f"初始化失败: {e}"}))
        except Exception:
            pass

    async def receiver():
        nonlocal batch_window_ms, subscribed_symbols
        try:
            while True:
                data_text = await websocket.receive_text()
                try:
                    msg = json.loads(data_text)
                    mtype = msg.get("type")
                    if mtype == "PING":
                        pong = {
                            "type": "PONG",
                            "clientTimestamp": msg.get("timestamp", int(time.time() * 1000)),
                            "serverTime": int(time.time() * 1000)
                        }
                        await websocket.send_text(json.dumps(pong))
                    elif mtype == "SUBSCRIBE":
                        syms = msg.get("symbols", [])
                        if syms:
                            for s in syms:
                                if s in subscribed_symbols:
                                    subscribed_symbols.remove(s)
                                subscribed_symbols.insert(0, s)
                    elif mtype == "SET_BATCH_WINDOW":
                        win = msg.get("windowMs", 150)
                        batch_window_ms = max(100, min(200, int(win)))
                except Exception:
                    pass
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    async def broadcaster():
        try:
            while True:
                await asyncio.sleep(batch_window_ms / 1000.0)
                quotes = mg.fetch_level1_quotes(subscribed_symbols[:50])
                indices = mg.fetch_level1_indices()
                batch_msg = {
                    "type": "SNAPSHOT_BATCH",
                    "quotes": list(quotes.values()),
                    "indices": list(indices.values()),
                    "batchWindowMs": batch_window_ms,
                    "serverTime": int(time.time() * 1000)
                }
                await websocket.send_text(json.dumps(batch_msg))
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    rec_task = asyncio.create_task(receiver())
    broad_task = asyncio.create_task(broadcaster())
    done, pending = await asyncio.wait([rec_task, broad_task], return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()


@app.get("/api/market")
def api_market(refresh: bool = False):
    now_ts = time.time()
    ttl = _get_market_ttl()

    # 命中短期缓存直接返回（未强制刷新时）
    if not refresh and _market_cache['data'] is not None and (now_ts - _market_cache['timestamp']) < ttl:
        _market_cache['hits'] += 1
        cached_resp = dict(_market_cache['data'])
        cached_resp['from_cache'] = True
        cached_resp['cache_age'] = round(now_ts - _market_cache['timestamp'], 1)
        return JSONResponse(cached_resp)

    _market_cache['misses'] += 1


    def safe(fn, default=None):
        try:
            return fn()
        except Exception:
            return default

    # 盘前/盘中主力净流入(f62)多为0，自动切近5日(f164)口径；收盘后用当日口径
    _hm = datetime.datetime.now().hour * 60 + datetime.datetime.now().minute
    sector_days = 5 if _hm < 15 * 60 else 1

    tasks = {
        'indices': lambda: safe(lambda: sd.tx_realtime(sd.IDX_CODES), []),
        'emotion': lambda: safe(lambda: sd.emotion(), None),
        'globals': lambda: safe(lambda: sd.global_markets(), None),
        'sectors': lambda: safe(lambda: sd.sector_flow(sector_days), None),
        'margin': lambda: safe(lambda: sd.margin_total(), None),
        'news': lambda: safe(lambda: sd.news(12), None),
    }

    t0 = time.time()
    results = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(fn): key for key, fn in tasks.items()}
        for fut in futures:
            key = futures[fut]
            try:
                results[key] = fut.result()
            except Exception:
                results[key] = [] if key == 'indices' else None

    elapsed = round(time.time() - t0, 2)
    strat_dec_res = safe(lambda: strat_dec.analyze_strategic_decision(
        emo=results.get('emotion'),
        sec=results.get('sectors'),
        idxs=results.get('indices')
    ), None)

    resp_data = dict(
        indices=results.get('indices', []),
        emotion=results.get('emotion'),
        strategic_decision=strat_dec_res,
        globals=results.get('globals'),
        sectors=results.get('sectors') or dict(inflow=[], outflow=[]),
        margin=results.get('margin'),
        news=results.get('news'),
        updated=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        elapsed=elapsed,
        from_cache=False,
    )

    _market_cache['data'] = resp_data
    # 时间戳记"产出完成时刻": 原来记请求开始时刻(now_ts), 一旦本次请求耗时超过 TTL
    # (慢链路/冷启动/新增的交易日探测), 下一次请求立刻判过期 —— 缓存等于从未命中(2026-09-30 修正)
    _market_cache['timestamp'] = time.time()
    _market_cache['last_refresh_s'] = elapsed

    return JSONResponse(resp_data)


@app.api_route("/api/strategic_decision", methods=["GET", "POST"])
async def api_strategic_decision(request: Request):
    """战役决策参谋部：基于毛选认识论与矛盾论体系的战略大势与战术指令 (支持持仓账本对账)"""
    try:
        portfolio = None
        equity = 1000000.0
        if request.method == "POST":
            try:
                body = await request.json()
                portfolio = body.get('portfolio')
                equity = float(body.get('equity', 1000000.0))
            except Exception:
                pass
        else:
            pf_str = request.query_params.get('portfolio')
            if pf_str:
                try:
                    portfolio = json.loads(pf_str)
                except Exception:
                    pass
            eq_param = request.query_params.get('equity')
            if eq_param:
                try:
                    equity = float(eq_param)
                except Exception:
                    pass

        m_data = _market_cache.get('data') or {}
        emo = m_data.get('emotion')
        sec = m_data.get('sectors')
        idxs = m_data.get('indices')
        res = strat_dec.analyze_strategic_decision(
            emo=emo, sec=sec, idxs=idxs,
            portfolio=portfolio, account_equity=equity
        )
        return JSONResponse(res)
    except Exception as e:
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)


@app.get("/api/emotion/history")
def api_emotion_history():
    return JSONResponse(read_hist())


_auction_cache = {
    'data': None,
    'timestamp': 0.0,
}


@app.get("/api/auction")
def api_auction(refresh: bool = False):
    """9:25 早盘集合竞价雷达 + 亏钱效应大面榜"""
    now_ts = time.time()
    ttl = _get_market_ttl()
    if not refresh and _auction_cache['data'] is not None and (now_ts - _auction_cache['timestamp']) < ttl:
        cached = dict(_auction_cache['data'])
        cached['from_cache'] = True
        cached['cache_age'] = round(now_ts - _auction_cache['timestamp'], 1)
        return JSONResponse(cached)
    try:
        t0 = time.time()
        res = ar.get_auction_radar()
        res['elapsed'] = round(time.time() - t0, 2)
        res['from_cache'] = False
        _auction_cache['data'] = res
        _auction_cache['timestamp'] = now_ts
        return JSONResponse(res)
    except Exception as e:
        return JSONResponse(dict(status="error", error=str(e)), status_code=500)


@app.get("/api/auction/audit")
def api_auction_audit(date: str = None):
    """收盘竞价自动对账结果 (封板率、溢价与打脸核验)"""
    try:
        import auction_audit as aa
        target_d = date or dt.date.today().strftime('%Y%m%d')
        res = aa.audit_auction_for_day(target_d)
        return JSONResponse(res)
    except Exception as e:
        return JSONResponse(dict(status="error", error=str(e)), status_code=500)


@app.get("/api/auction/audit/ledger")
def api_auction_audit_ledger(limit: int = 30):
    """竞价对账累计总账本与胜率曲线"""
    try:
        import auction_audit as aa
        return JSONResponse(aa.get_auction_audit_ledger(limit=limit))
    except Exception as e:
        return JSONResponse(dict(status="error", error=str(e)), status_code=500)


@app.get("/api/screen")
def api_screen(patterns: str = ""):
    """形态选股：全市场快照→候选→K线→8形态判定（约1-2分钟）"""
    import screener
    only = patterns.strip() or None
    try:
        res = screener.run(only)
        summary = {p: len(lst) for p, lst in res.items()}
        return JSONResponse(dict(status="ok", summary=summary, results=res))
    except Exception as e:
        return JSONResponse(dict(status="error", error=str(e)), status_code=500)


_strat_cache = {
    'data': None,
    'timestamp': 0.0,
    'mode': '',
}


@app.get("/api/strategies")
def api_strategies(mode: str = "auto", refresh: bool = False):
    """12策略选股库：按情绪周期自适应(auto) / 全策略(all) / 单策略"""
    valid_strat_keys = {'auto', 'all', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L'}
    mode_clean = (mode or "").strip()
    if not mode_clean or (mode_clean not in valid_strat_keys and not any(k.strip().upper() in valid_strat_keys for k in mode_clean.split(','))):
        mode = "auto"
    else:
        mode = mode_clean

    now_ts = time.time()
    if not refresh and _strat_cache['data'] and _strat_cache['mode'] == mode and (now_ts - _strat_cache['timestamp']) < 120.0:
        cached = dict(_strat_cache['data'])
        cached['from_cache'] = True
        cached['cache_age'] = round(now_ts - _strat_cache['timestamp'], 1)
        return JSONResponse(cached)
    try:
        t0 = time.time()
        res = strat_lib.run_strategies_structured(mode)
        res['elapsed'] = round(time.time() - t0, 2)
        res['from_cache'] = False
        _strat_cache['data'] = res
        _strat_cache['timestamp'] = time.time()
        _strat_cache['mode'] = mode
        return JSONResponse(res)
    except Exception as e:
        return JSONResponse(dict(status="error", error=str(e)), status_code=500)


@app.get("/api/watchlist")
def api_watchlist(codes: str = ""):
    """本地自选股盯盘池：极速批量拉取实时行情"""
    if not codes.strip():
        return JSONResponse([])
    raw_codes = [_normalize_stock_code(c) for c in codes.split(',') if _normalize_stock_code(c)]
    if not raw_codes:
        return JSONResponse([])
    tx_codes = [('sh' if c.startswith(('6', '5', '9')) else 'sz') + c for c in raw_codes[:60]]
    try:
        url = 'https://qt.gtimg.cn/q=' + ','.join(tx_codes)
        raw = sd.http(url, gbk=True, timeout=4)
        items = []
        for line in raw.split(';'):
            if '=' not in line:
                continue
            parts = line.split('"')[1].split('~')
            if len(parts) > 38 and parts[4] and parts[5]:
                c = parts[2]
                prev_c = float(parts[4])
                if prev_c <= 0:
                    continue
                curr_p = float(parts[3])
                open_p = float(parts[5])
                high_p = float(parts[33])
                low_p = float(parts[34])
                pct = float(parts[32]) if parts[32] else 0.0
                chg = float(parts[31]) if parts[31] else 0.0
                open_pct = round((open_p - prev_c) / prev_c * 100, 2)
                high_pct = round((high_p - prev_c) / prev_c * 100, 2)
                # 日内回撤率：必须以"当日最高价"为基数 (curr-high)/high。
                # 旧写法 pct - high_pct 是两个不同基数的百分比相减，数值错位，
                # 在涨停股上偏差被放大以致误触 -4% 大面阈值。
                drop_from_high = round((curr_p - high_p) / high_p * 100, 2) if high_p > 0 else 0.0
                vol_ratio = float(parts[49]) if len(parts) > 49 and parts[49] else 1.0
                turnover = float(parts[38]) if parts[38] else 0.0
                amount = float(parts[37]) if parts[37] else 0.0
                limit_up = float(parts[47]) if len(parts) > 47 and parts[47] else 0.0
                limit_down = float(parts[48]) if len(parts) > 48 and parts[48] else 0.0
                amts = ('-' if c.startswith('.') else
                        (f'{amount/10000:,.1f}亿' if amount >= 10000 else (f'{amount:,.0f}万' if amount > 0 else '-')))
                items.append({
                    'code': c,
                    'name': parts[1],
                    'price': curr_p,
                    'pct': pct,
                    'chg': chg,
                    'prev_close': prev_c,
                    'open_p': open_p,
                    'open_pct': open_pct,
                    'high_p': high_p,
                    'high_pct': high_pct,
                    'low_p': low_p,
                    'drop_from_high': drop_from_high,
                    'vol_ratio': vol_ratio,
                    'turnover': turnover,
                    'amount': amts,
                    'amount_num': round(amount / 10000, 2),
                    'is_zt': (curr_p >= limit_up - 0.01) if limit_up > 0 else False,
                    'is_dt': (curr_p <= limit_down + 0.01) if limit_down > 0 else False,
                    'time': parts[30] if len(parts) > 30 else '',
                })
        return JSONResponse(items)
    except Exception:
        return JSONResponse([], status_code=500)


@app.get("/api/data_status")
def api_data_status():
    """上游数据源健康度 + 内存 TTL 缓存指标 + 大盘页缓存命中(market_cache)"""
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
    return JSONResponse(st)


@app.get("/api/backtest/presets")
def api_backtest_presets():
    """获取所有预置回测策略元数据"""
    return JSONResponse(bt_engine.get_available_strategies())


@app.get("/api/backtest/run")
def api_backtest_run(
    strategy: str = "cycle",
    code: str = "sh000001",
    days: int = 120,
    capital: float = 100000.0,
):
    """运行量化回测并返回对账报告与净值曲线"""
    raw_code = str(code).strip()
    if raw_code.lower().startswith(('sh', 'sz')):
        c_target = raw_code
    else:
        norm = _normalize_stock_code(raw_code)
        c_target = norm if norm else ("sh000001" if strategy == "cycle" else "002696")
    res = bt_engine.run_strategy(strategy=strategy, code=c_target, days=days, initial_capital=capital)
    return JSONResponse(res)


# ============================================================
# 模拟自动交易 (Paper Trading) —— 不接券商，不下真单
# ============================================================

@app.get("/api/paper/replay")
def api_paper_replay(
    code: str = "000001",
    strategy: str = "chan",
    days: int = 250,
    capital: float = 100000.0,
):
    """历史回放模拟自动交易：逐根K线推进，次日开盘成交（无未来函数）"""
    c = _normalize_stock_code(code) or code
    res = paper.run_replay(c, strategy=strategy, days=days, initial_cash=capital)
    return JSONResponse(res)


@app.get("/api/paper/tick")
def api_paper_tick(strategy: str = "chan", codes: str = "", capital: float = None):
    """执行一次实时纸上交易巡检（不真下单），结果持久化到 data/stock_data/"""
    code_list = [c.strip() for c in codes.split(',') if c.strip()] or None
    if code_list:
        code_list = [_normalize_stock_code(c) or c for c in code_list]
    res = paper.run_paper_tick(strategy=strategy, codes=code_list, initial_cash=capital)
    return JSONResponse(res)


@app.get("/api/paper/report")
def api_paper_report():
    """纸上交易累计报告（成交笔数/胜率/费用/回撤）"""
    return JSONResponse(paper.paper_report())


@app.get("/api/paper/reset")
def api_paper_reset():
    """清空纸上交易状态（重新开始模拟）"""
    import os as _os
    killed = []
    for f in (paper.PAPER_STATE, paper.PAPER_TRADES, paper.PAPER_EQUITY):
        try:
            if _os.path.exists(f):
                _os.remove(f)
                killed.append(_os.path.basename(f))
        except Exception:
            pass
    return JSONResponse({"status": "ok", "cleared": killed})


@app.get("/api/stock/{code}")
def api_stock(code: str, refresh: bool = False):
    code = _normalize_stock_code(code)
    cache_key = f"api_stock:{code}"
    if not refresh:
        cached = df_feed.CACHE.get(cache_key)
        if cached is not None:
            return JSONResponse(cached)

    full = ('sh' + code) if code.startswith(('6', '5', '9')) else ('sz' + code)

    def fetch_quote():
        try:
            quotes = df_feed.get_realtime_quotes([code])
            return quotes.get(code)
        except Exception:
            return None

    def fetch_kline():
        try:
            return df_feed.get_kline_cached(full, 160)
        except Exception:
            return None

    def fetch_trends():
        try:
            return df_feed.get_intraday_trends(code)
        except Exception:
            return None

    def fetch_capital():
        try:
            return df_feed.get_capital_breakdown(code)
        except Exception:
            return {}

    def fetch_announcements():
        ann_cache_key = f"ann:{code}"
        cached = df_feed.CACHE.get(ann_cache_key)
        if cached is not None:
            return cached
        ann_list = []
        try:
            u = (f'https://np-anotice-stock.eastmoney.com/api/security/ann'
                 f'?sr=-1&page_size=8&page_index=1&ann_type=A&stock_list={code}')
            em_hdrs = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'}
            data = json.loads(sd.http(u, headers=em_hdrs, timeout=2.5, retries=1))
            for a in (data.get('data') or {}).get('list', []):
                ann_list.append(dict(date=a.get('notice_date', '')[:10], title=a.get('title', '')))
            df_feed.CACHE.set(ann_cache_key, ann_list, ttl=300.0)
        except Exception:
            pass
        return ann_list

    tasks = {
        'quote': fetch_quote,
        'kline': fetch_kline,
        'trends': fetch_trends,
        'capital': fetch_capital,
        'announcements': fetch_announcements,
    }

    results = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fn): key for key, fn in tasks.items()}
        for fut in futures:
            key = futures[fut]
            try:
                results[key] = fut.result()
            except Exception:
                results[key] = None

    q = results.get('quote')
    kl = results.get('kline')
    trends = results.get('trends')
    cap_info = results.get('capital') or {}
    fund = cap_info.get('history') or []
    today_flow = cap_info.get('today') or {}
    ann = results.get('announcements') or []

    # 缠论中枢与一二三买卖点诊断（纯算力快速计算）
    chan = None
    if kl and len(kl) >= 30:
        try:
            chan = sd.chan_analysis_structured(kl, code)
        except Exception:
            chan = None

    # 4 大超短微观纯 NumPy 算子毫秒级全息体检
    ultrashort = None
    try:
        from scripts.ultrashort_metrics import (
            calc_intraday_dvr,
            evaluate_limit_order_strength,
            evaluate_volatility_headroom,
        )
        import numpy as np

        # 1. 纯盘中下行方差占比 (DVR)
        dvr_data = None
        if trends and trends.get('prices') and len(trends['prices']) >= 5:
            c_1m = np.asarray(trends['prices'], dtype=float)
            p_c = float(trends.get('pre_close') or (q.get('prev_close') if q else c_1m[0]))
            res_dvr = calc_intraday_dvr(c_1m, c_1m, c_1m, p_c)
            dvr_data = {
                "dvr": res_dvr.dvr,
                "intraday_amp_pct": res_dvr.intraday_amp_pct,
                "price_pos_ratio": res_dvr.price_pos_ratio,
                "is_strong_absorption": res_dvr.is_strong_absorption,
                "label": res_dvr.label,
            }

        # 2. 封单质量比与撤单预警 (Limit Strength)
        lim_data = None
        if q:
            p_curr = float(q.get('price') or 0.0)
            p_up = float(q.get('upper_limit') or (p_curr * 1.1))
            bids = q.get('bids') or []
            bid1_shares = float(bids[0][1] * 100) if bids and len(bids) > 0 and len(bids[0]) > 1 else 0.0
            float_cap_yuan = float(q.get('float_mcap') or 0.0) * 100000000.0 if q.get('float_mcap') else 2000000000.0
            turnover_yuan = float(q.get('amount_raw') or 0.0)
            res_lim = evaluate_limit_order_strength(
                limit_price=p_up,
                bid1_volume_shares=bid1_shares,
                free_float_mcap_yuan=float_cap_yuan,
                day_turnover_yuan=turnover_yuan,
            )
            lim_data = {
                "seal_amount_wan": res_lim.seal_amount_wan,
                "seal_to_float_pct": res_lim.seal_to_float_pct,
                "seal_to_turnover_pct": res_lim.seal_to_turnover_pct,
                "is_tail_withdrawing": res_lim.is_tail_withdrawing,
                "status_label": res_lim.status_label,
            }

        # 3. 异动监管真实安全垫 (Headroom)
        headroom_data = None
        if q:
            p_curr = float(q.get('price') or 0.0)
            p_up = float(q.get('upper_limit') or (p_curr * 1.1))
            res_hr = evaluate_volatility_headroom(
                current_price=p_curr,
                limit_up_price=p_up,
                raw_normal_crit_price=p_curr * 1.20,
                raw_severe_crit_price=p_curr * 1.60,
                will_limit_trigger_normal=False,
                will_limit_trigger_severe=False,
            )
            headroom_data = res_hr

        ultrashort = {
            "dvr": dvr_data,
            "limit_strength": lim_data,
            "headroom": headroom_data,
        }
    except Exception as e:
        ultrashort = {"error": str(e)}

    resp_data = dict(
        code=code,
        quote=q,
        kline=kl,
        chan=chan,
        trends=trends,
        fund_flow=fund,
        today_flow=today_flow,
        announcements=ann,
        ultrashort=ultrashort,
        data_source=q.get('source', 'tencent') if q else 'unknown'
    )
    ttl = 60.0 if df_feed.is_market_closed() else 3.0
    df_feed.CACHE.set(cache_key, resp_data, ttl=ttl)
    return JSONResponse(resp_data)


if __name__ == "__main__":
    import uvicorn
    import os
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run(app, host=host, port=port)
