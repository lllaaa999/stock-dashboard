# -*- coding: utf-8 -*-
"""股票看盘 · 七层雷达 可视化仪表盘 (FastAPI)"""
import sys, os, json, datetime, time, re
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))
import stock_dashboard as sd
import strategies_lib as strat_lib
import auction_radar as ar
import data_feed as df_feed

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


from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse

app = FastAPI(title="股票看盘 · 七层雷达")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates'))

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


def _get_market_ttl() -> float:
    """动态 TTL：交易时段 6 秒, 其余时段 60 秒。

    2026-09-30: 改用 data_feed.is_market_closed() 统一判定 —— 原实现把午休和节假日
    都算作盘中, 长假里页面开着会 6 秒一次白刷上游。
    """
    return 60.0 if df_feed.is_market_closed() else 6.0


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
    now_ymd = datetime.date.today().strftime('%Y%m%d')
    if _market_cache.get('data') and _market_cache['data'].get('emotion'):
        emo = _market_cache['data']['emotion']
        if emo.get('score') is not None and now_ymd not in records_by_date:
            records_by_date[now_ymd] = {
                'date': now_ymd,
                'score': emo.get('score'),
                'band': emo.get('band'),
                'zt': emo.get('zt_count') or emo.get('zt'),
                'zb': emo.get('zb_count') or emo.get('zb'),
                'dt': emo.get('dt_count') or emo.get('dt'),
                'max_lb': emo.get('max_lb'),
                'stage': emo.get('stage')
            }

    return sorted(records_by_date.values(), key=lambda r: str(r.get('date', '')))


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


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
    resp_data = dict(
        indices=results.get('indices', []),
        emotion=results.get('emotion'),
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


@app.get("/api/sim")
def api_sim(scenario: str = "", code: str = "", engine: str = "rule"):
    """多主体模拟：世界模拟v2 + 可选 LLM 消息面推演

    engine=rule（默认，纯规则引擎）| engine=llm（LLM 读当日事件表出九方冲击矩阵,
    再交给同一个规则引擎做传染与加权 —— LLM 只给判断, 不碰算术）。
    无密钥/调用失败时自动回落 rule，并在返回里标 engine=rule(fallback)。
    """
    import io
    from contextlib import redirect_stdout
    code = _normalize_stock_code(code)
    buf = io.StringIO()
    llm_payload = None
    llm_impact = None
    if engine == "llm" and not code:
        try:
            import sim_llm as _simllm
            llm_payload = _simllm.run(dry_run=False, quiet=True)
        except Exception as e:
            llm_payload = {"ok": False, "reason": "exception", "hint": f"{type(e).__name__}: {e}"}
        if llm_payload.get("ok"):
            llm_impact = dict(llm_payload.get("impact") or {})
            llm_impact["theme_priority"] = llm_payload.get("theme_priority") or []
        else:
            llm_payload = dict(llm_payload, fallback=True)
    try:
        with redirect_stdout(buf):
            if code:
                sd.agent_sim(code)
                mode = "agents"
            else:
                sd.sim_world(scenario.strip() or None, llm_impact=llm_impact,
                             llm_note="LLM 消息面推演")
                mode = "sim"
        text = buf.getvalue()
        m_stage = re.search(r"定位: 【(.+?)】", text)
        m_net = re.search(r"加权合力:\s*([+-]?\d+)", text)
        m_meta_domain = re.search(r"【事件智能研判】属性:\s*(.+?)\s*\|", text)
        m_meta_desc = re.search(r"【事件智能研判】.*?逻辑:\s*(.+)", text)
        m_path = re.search(r">> 推演.*?: (.+)", text)
        m_pos = re.search(r"• 仓位指引:\s*(.+)", text)
        m_atk = re.search(r"• 进攻方向:\s*(.+)", text)
        
        forces = []
        for line in text.split('\n'):
            m_f = re.search(r"^\s+([\u4e00-\u9fa5\(\)]+)\s+([+-]?\d+)分\s+\[(.+?)\]\s+动作:\s*(.+)", line)
            if m_f:
                forces.append({
                    'name': m_f.group(1).strip(),
                    'score': int(m_f.group(2)),
                    'attitude': m_f.group(3).strip(),
                    'action': m_f.group(4).strip(),
                })
        rounds = re.findall(r"【传染R\d】.+", text)

        net_val = int(m_net.group(1)) if m_net else 0
        if mode == "agents":
            domain_str = f"个股资金博弈 ({code})"
            desc_str = f"针对个股 {code} 展开的九方多主体博弈合力推演"
        else:
            domain_str = m_meta_domain.group(1).strip() if m_meta_domain else ''
            desc_str = m_meta_desc.group(1).strip() if m_meta_desc else None
        
        beneficiary = None
        branching = None
        if mode == "sim":
            try:
                beneficiary = sd.get_event_beneficiary_stocks(scenario.strip(), domain_str, net_val)
            except Exception:
                pass
            try:
                branching = sd.get_branching_scenarios(scenario.strip(), domain_str, net_val)
            except Exception:
                pass
            
        history_review = None
        try:
            history_review = sd.get_historical_review(scenario.strip())
        except Exception:
            pass

        stage_val = m_stage.group(1) if m_stage else (m_path.group(1).strip() if m_path else None)

        return JSONResponse(dict(
            status="ok", mode=mode, code=code, text=text,
            engine=("llm" if (llm_payload and llm_payload.get("ok")) else
                    ("rule(fallback)" if llm_payload else "rule")),
            llm=llm_payload,
            stage=stage_val,
            net=("加权合力: " + m_net.group(1)) if m_net else None,
            net_value=net_val,
            domain=domain_str or None,
            desc=desc_str,
            path=m_path.group(1).strip() if m_path else None,
            playbook={'position': m_pos.group(1).strip() if m_pos else None, 'attack': m_atk.group(1).strip() if m_atk else None},
            forces=forces,
            rounds=rounds,
            beneficiary=beneficiary,
            branching=branching,
            history_review=history_review,
            historical_benchmarks=getattr(sd, '_HISTORICAL_BENCHMARKS', []),
        ))
    except Exception as e:
        return JSONResponse(dict(status="error", error=str(e), text=buf.getvalue()), status_code=500)


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
                drop_from_high = round(pct - high_pct, 2)
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
    except Exception as e:
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


@app.get("/api/stock/{code}")
def api_stock(code: str):
    code = _normalize_stock_code(code)
    full = ('sh' + code) if code.startswith(('6', '5', '9')) else ('sz' + code)
    
    # 1. 实时行情 (腾讯 -> 新浪 -> 东财 自动降级与 1.5s 内存缓存)
    q = None
    try:
        quotes = df_feed.get_realtime_quotes([code])
        q = quotes.get(code)
    except Exception:
        pass

    # 2. 日 K 线 (带 60s 盘中缓存 / 盘后永久缓存)
    kl = None
    try:
        kl = df_feed.get_kline_cached(full, 160)
    except Exception:
        pass

    # 3. 缠论中枢与一二三买卖点诊断
    chan = None
    if kl and len(kl) >= 30:
        try:
            chan = sd.chan_analysis_structured(kl, code)
        except Exception:
            chan = None

    # 4. 当日分时走势 (黄白线、分时成交量、分钟涨跌幅)
    trends = None
    try:
        trends = df_feed.get_intraday_trends(code)
    except Exception:
        trends = None

    # 5. 资金分布 (主力/超大单/大单/中单/小单单笔分布及近5日流向, 零 akshare 阻塞)
    cap_info = df_feed.get_capital_breakdown(code)
    fund = cap_info.get('history') or []
    today_flow = cap_info.get('today') or {}

    # 6. 个股公告 (300秒内存缓存, 2秒短超时防阻塞)
    ann_cache_key = f"ann:{code}"
    ann = df_feed.CACHE.get(ann_cache_key)
    if ann is None:
        ann = []
        try:
            u = (f'https://np-anotice-stock.eastmoney.com/api/security/ann'
                 f'?sr=-1&page_size=8&page_index=1&ann_type=A&stock_list={code}')
            em_hdrs = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'}
            data = json.loads(sd.http(u, headers=em_hdrs, timeout=2.5, retries=1))
            for a in (data.get('data') or {}).get('list', []):
                ann.append(dict(date=a.get('notice_date', '')[:10], title=a.get('title', '')))
            df_feed.CACHE.set(ann_cache_key, ann, ttl=300.0)
        except Exception:
            pass

    return JSONResponse(dict(
        code=code,
        quote=q,
        kline=kl,
        chan=chan,
        trends=trends,
        fund_flow=fund,
        today_flow=today_flow,
        announcements=ann,
        data_source=q.get('source', 'tencent') if q else 'unknown'
    ))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8001, reload=False)
