#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
股票综合看盘数据采集器 · 七层雷达
用法:
  python stock_dashboard.py market            # 大盘全景: 指数+外盘+情绪指数+板块资金+两融+快讯
  python stock_dashboard.py market --no-news  # 同上但不抓快讯(更快)
  python stock_dashboard.py stock 600664      # 个股体检: 行情+均线+区间+主力资金+融资+公告
  python stock_dashboard.py stock 600664 --chart [--days 120]
  python stock_dashboard.py emotion [--date YYYY-MM-DD]
  python stock_dashboard.py screener [leader|fund|volume|lhb|all]  # 四策略选股
  python stock_dashboard.py cycle           # 情绪周期定位(92科比五阶段)
  python stock_dashboard.py chan 600664     # 缠论简化引擎(日线笔/中枢/背驰)
"""
import sys, os, json, re, ssl, time, threading, urllib.request, datetime as dt  # urllib.request 被 http() 使用

try:
    from curl_cffi import requests as _creq
    # 默认禁用 curl_cffi，防止 Windows 系统下 HTTP/2 与 IPv6 ALPN 协商导致的 20 秒恶性超时卡顿
    _HAS_CURL = os.environ.get('STOCK_USE_CURL') == '1'
except Exception:
    _HAS_CURL = False

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# 注: limit_up_quality 虽在本文件内未直接调用，但被 strategic_decision / strategies_lib
# 通过 sd.limit_up_quality 引用，必须保留导出；_lu_* 系列内部函数已无外部引用。
from core.chan import chan_analysis_structured
from core.quality import limit_up_quality
from core.emotion import _emotion_band, _emotion_score_v1, _emotion_score_v2, _effect_flat

CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
_cand = os.path.join(ROOT_DIR, 'data')
if os.path.isdir(_cand):
    _H = _cand
else:
    _H = os.environ.get('STOCK_DATA_HOME') or os.environ.get('HERMES_HOME') or os.path.expanduser('~/.hermes')
HERMES_HOME = _H
DATA_DIR = os.path.join(HERMES_HOME, 'stock_data')
CHART_DIR = os.path.join(DATA_DIR, 'charts')
SNAPSHOT_DIR = os.path.join(DATA_DIR, 'snapshots')
os.makedirs(CHART_DIR, exist_ok=True)
os.makedirs(SNAPSHOT_DIR, exist_ok=True)
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'}

def http(url, gbk=False, timeout=8, retries=2, referer=None, headers=None, circuit=True):
    """HTTP 取数（curl_cffi 优先，urllib 兜底），带 host 级熔断。

    修复 (2026-10-18):
    1) 原实现完全不看 host 熔断状态 —— 熔断只存在于 _get_first_ok，而
       tx_realtime / kline_tx / news / margin 等全部直连 http()，于是一个
       已判死的 host 仍会被反复请求。现在所有出网请求都经过这里，冷却期内的
       host 直接快速失败（fail-fast），不再消耗 timeout × retries。
    2) 默认超时从 20s 收敛到 8s、重试 3 次收敛到 2 次。原默认值下，
       快讯三级回退链最坏要等约 2 分钟，指数行情最坏 60s+，用户侧表现为
       "页面转圈"。绝大多数 JSON 接口在 2s 内返回，8s 已足够宽容。

    :param circuit: 是否参与熔断（False 时强制请求，用于人工探活）
    """
    import urllib.parse
    import time

    host = urllib.parse.urlsplit(url).netloc
    # fail-fast: 熔断期内直接抛错，避免 timeout × retries 的无谓等待
    if circuit and host and _cb_is_open(host):
        raise RuntimeError('host %s 处于熔断冷却期，跳过请求' % host)

    last = None
    hh = dict(headers) if headers else dict(UA)
    if referer and not headers:
        hh['Referer'] = referer
    for i in range(max(1, retries)):
        try:
            if _HAS_CURL:
                try:
                    r = _creq.get(url, headers=hh, impersonate='chrome', timeout=timeout)
                    raw = r.content
                    if circuit and host:
                        _cb_record(host, True)
                    return raw.decode('gbk', 'replace') if gbk else raw.decode('utf-8', 'replace')
                except Exception:
                    pass  # curl 失败回退 urllib
            req = urllib.request.Request(url, headers=hh)
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                raw = r.read()
            if circuit and host:
                _cb_record(host, True)
            return raw.decode('gbk', 'replace') if gbk else raw.decode('utf-8', 'replace')
        except Exception as e:
            last = e
            if circuit and host:
                _cb_record(host, False)
            # 熔断刚打开时不再做无意义的重试退避
            if circuit and host and _cb_is_open(host):
                break
            time.sleep(0.8 * (i + 1))
    raise last

# ---- host 级熔断: 进程内连续失败计数, 自动半开启恢复机制 ----
_HOST_FAIL = {}          # {host: 连续失败次数}
_HOST_BLACKOUT = {}      # {host: 冷却截止时间戳}
_CB_LOCK = threading.Lock()   # 修复: Web 多线程下熔断状态需加锁，避免计数竞争
_CIRCUIT_N = int(os.environ.get('STOCK_HTTP_BREAK_N', '3'))
_CIRCUIT_COOLDOWN = 60.0 # 熔断后冷却 60 秒自动半开启重试


def _cb_record(host, ok):
    """记录一次 host 级请求结果，维护熔断状态（线程安全）"""
    import time
    if not host:
        return
    now_ts = time.time()
    with _CB_LOCK:
        if ok:
            _HOST_FAIL[host] = 0
            _HOST_BLACKOUT.pop(host, None)
        else:
            n = _HOST_FAIL.get(host, 0) + 1
            _HOST_FAIL[host] = n
            if n >= _CIRCUIT_N:
                _HOST_BLACKOUT[host] = now_ts + _CIRCUIT_COOLDOWN
                w('[熔断] %s 连续%d次失败, 冷却%.0f秒' % (host, n, _CIRCUIT_COOLDOWN))

def _get_first_ok(urls, gbk=False, timeout=8, retries=2, referer=None, headers=None):
    """按序尝试 urls, 跳过处于冷却期内的 host; 某 host 连续失败 _CIRCUIT_N 次后冷却 60s。
    任一 host 成功即清零计数并解除熔断。"""
    import urllib.parse
    last = None
    for u in urls:
        host = urllib.parse.urlsplit(u).netloc
        # 冷却期内的 host 直接跳过，避免把时间浪费在已知失效的通道上
        if _cb_is_open(host):
            continue
        try:
            # http() 内部已负责记录成功/失败并维护熔断状态，此处不再重复计数，
            # 否则同一个失败会被计两次（一次在 http 内，一次在这里），
            # 导致熔断阈值实际只相当于 half。
            return http(u, gbk=gbk, timeout=timeout, retries=retries,
                        referer=referer, headers=headers)
        except Exception as e:
            last = e
    raise RuntimeError('全部通道失败: %s' % last)

def _cb_is_open(host):
    """判断指定 host 当前是否处于熔断冷却期"""
    import time
    if not host:
        return False
    clean_host = host.replace('https://', '').replace('http://', '').split('/')[0]
    return _HOST_BLACKOUT.get(clean_host, 0) > time.time()

def w(*a):
    print(*a)

# ---------- 1. 腾讯实时行情 ----------
IDX_CODES = ['sh000001','sz399001','sz399006','sh000300','sh000688','hkHSI','hkHSTECH','usDJI','usIXIC','usINX']

def tx_realtime(codes):
    out = []
    t = http('https://qt.gtimg.cn/q=' + ','.join(codes), gbk=True)
    for line in t.split(';'):
        if '=' not in line: continue
        p = line.split('"')[1]
        f = p.split('~')
        if len(f) > 38:
            amt = float(f[37]) if f[37] else 0
            amts = ('-' if f[2].startswith('.') else
                    (f'{amt/10000:,.0f}亿' if amt >= 10000 else (f'{amt:,.0f}万' if amt > 0 else '-')))
            out.append(dict(code=f[2], name=f[1], price=float(f[3]), chg=float(f[31]),
                            pct=float(f[32]), high=float(f[33]), low=float(f[34]), amount=amts,
                            raw_amount=amt, trade_time=f[30] if len(f) > 30 else ''))
    return out

def market_quotes():
    w('\n===== [1] A股/港美指数 =====')
    for q in tx_realtime(IDX_CODES):
        w(f"{q['code']} | {q['name']} | {q['price']} | {q['pct']:+.2f}% | 高低{q['high']}/{q['low']} | 额{q['amount']}")

# ---------- 2. 新浪隔夜外盘包 ----------
def global_markets():
    w('\n===== [2] 隔夜外盘(盘前定调) =====')
    try:
        t = http('https://hq.sinajs.cn/list=hf_CHA50CFD,hf_NQ,hf_CL,hf_GC,fx_susdcnh', gbk=True,
                 referer='https://finance.sina.com.cn/')
        rows = {}
        for m in re.finditer(r'hq_str_(\w+)="([^"]*)"', t):
            rows[m.group(1)] = m.group(2).split(',')
        def g(k, i, dflt='-'):
            v = rows.get(k, [])
            return v[i] if len(v) > i and v[i] else dflt
        out = dict(a50=g('hf_CHA50CFD', 0), a50_hi=g('hf_CHA50CFD', 4), a50_lo=g('hf_CHA50CFD', 5), a50_time=g('hf_CHA50CFD', 6),
                   nq=g('hf_NQ', 0), nq_time=g('hf_NQ', 6), gold=g('hf_GC', 0), gold_hi=g('hf_GC', 4), gold_lo=g('hf_GC', 5),
                   oil=g('hf_CL', 0), usdcnh=g('fx_susdcnh', 1), usdcnh_chg=g('fx_susdcnh', 11))
        w(f"A50期货: {out['a50']}  区间{out['a50_hi']}~{out['a50_lo']} @{out['a50_time']}  <-开盘定调核心")
        w(f"纳指期货: {out['nq']} @{out['nq_time']}")
        w(f"COMEX金: {out['gold']} 区间{out['gold_hi']}~{out['gold_lo']} | WTI油: {out['oil']}")
        w(f"USDCNH: {out['usdcnh']} ({out['usdcnh_chg']})")
        return out
    except Exception as e:
        w(f'[外盘失败] {e}')
        return None

# ---------- 3. 板块主力资金 ----------
# 修复 (2026-10-18): 原实现 days=1(当日 f62) 与 days=5(近5日 f164) 共用同一个
# sector_flow.json，两种口径互相覆盖，页面会拿 5 日累计当"今日"显示。
# 现在按口径分文件，并带日期戳，跨日自动失效。
def _sector_cache_file(days):
    _d = dt.date.today().strftime('%Y%m%d')
    return os.path.join(DATA_DIR, 'sector_flow_d%d_%s.json' % (days, _d))

# 兼容旧引用（仅读，不再写入）
_SECTOR_CACHE_FILE = os.path.join(DATA_DIR, 'sector_flow.json')

def sector_flow(days=1):
    """days=1: 当日主力净流入(fid=f62) —— 仅收盘后有效, 盘前必全0;
    days=5: 近5日主力净流入(fid=f164) —— 盘前情报应使用此口径。
    内置东财 -> 新浪 -> 本地缓存三重保障，绝不返回 None。"""
    w('\n===== [3] 板块主力资金(亿元%s) =====' % ('·近5日' if days == 5 else ''))
    out = dict(inflow=[], outflow=[])
    fid = 'f164' if days == 5 else 'f62'
    
    # 通道 1: 东财 push2
    try:
        hosts = ['https://push2.eastmoney.com',
                 'https://push2delay.eastmoney.com',
                 'https://48.push2.eastmoney.com']
        for tag, po, pz in [('流入TOP8', 1, 8), ('流出TOP5', 0, 5)]:
            urls = [_h + '/api/qt/clist/get?pn=1&pz=%d&po=%d&np=1&fltt=2&fid=%s&fs=m:90+t:2&fields=f12,f14,f62,f164,f184' % (pz, po, fid) for _h in hosts]
            j = json.loads(_get_first_ok(urls, retries=1, timeout=3))
            if not (j.get('data') or {}).get('diff'):
                raise RuntimeError('push2无数据')
            w(f'-- {tag} --')
            dst = out['inflow'] if po == 1 else out['outflow']
            for d in j['data']['diff']:
                fv, pv = _num(d.get(fid)), _num(d.get('f184'))
                row = dict(name=d['f14'], flow=round(fv / 1e8, 1), pct=round(pv, 2))
                w(f"{d['f14']}: {fv/1e8:+.1f}亿 ({pv:+.2f}%)")
                dst.append(row)
        if out['inflow'] or out['outflow']:
            out['source'] = 'eastmoney'
            out['days'] = days
            out['estimated'] = False
            try:
                _fp = _sector_cache_file(days)
                os.makedirs(os.path.dirname(_fp), exist_ok=True)
                json.dump(out, open(_fp, 'w', encoding='utf-8'), ensure_ascii=False)
            except Exception:
                pass
            return out
    except Exception as e:
        w(f'[东财板块资金降级] {e}')

    # 通道 2: 新浪行业板块实时行情 (极速高可用降级)
    try:
        raw_sina = http('http://vip.stock.finance.sina.com.cn/q/view/newSinaHy.php', gbk=True, timeout=3)
        if '=' in raw_sina:
            raw_json = raw_sina.split('=', 1)[1].strip()
            s_dict = json.loads(raw_json)
            s_items = []
            for k, v in s_dict.items():
                parts = v.split(',')
                if len(parts) >= 8:
                    s_name = parts[1]
                    s_pct = float(parts[5])
                    s_amt = float(parts[7])
                    s_flow = round(s_amt * (s_pct / 100.0) * 0.15 / 1e8, 1)
                    s_items.append({'name': s_name, 'pct': round(s_pct, 2), 'flow': s_flow})
            if s_items:
                s_items.sort(key=lambda x: x['pct'], reverse=True)
                out['inflow'] = s_items[:8]
                s_outflow = sorted(s_items[-5:], key=lambda x: x['pct'])
                for o in s_outflow:
                    if o['flow'] > 0:
                        o['flow'] = -abs(o['flow'])
                out['outflow'] = s_outflow
                # 修复 (2026-10-18): 新浪没有真正的"主力净流入"字段，这里的 flow
                # 是用「成交额 × 涨跌幅 × 0.15」估算出来的（0.15 为经验系数），
                # 与东财的主力资金口径完全不同。旧代码把它当真实数据落盘缓存，
                # 导致下次直接读缓存时无法区分真假。现在显式打标且不落盘，
                # 每次重新计算，避免污染 day=1/day=5 的口径。
                out['source'] = 'sina_estimated'
                out['estimated'] = True
                out['days'] = days
                w(f'[新浪板块资金降级成功] 获取流入{len(out["inflow"])}只, 流出{len(out["outflow"])}只 (估算值, 不落盘)')
                return out
    except Exception as e2:
        w(f'[新浪板块资金降级失败] {e2}')

    # 通道 3: 本地快照缓存（按口径 + 日期分文件，只接受当天的东财真实数据）
    _cf = _sector_cache_file(days)
    if os.path.exists(_cf):
        try:
            cached = json.load(open(_cf, encoding='utf-8'))
            if (cached.get('inflow') or cached.get('outflow')) and not cached.get('estimated'):
                w('[板块资金使用本地缓存]')
                return cached
        except Exception:
            pass

    return out

# ---------- 4. 涨停池/情绪指数 ----------
UT = '7eea3edcaed734bea9cbfc24409ed989'
# ==================== 涨停质量分 (迁移至 core.quality，保持外观兼容) ====================
# 已在文件头部从 core.quality 统一导入:
# limit_up_quality, _lu_num, _lu_time_score, _lu_seal_score, _lu_board_score
_POOL_CACHE = {}

def _pool_akshare(kind, ymd):
    """涨停/炸板/跌停池的 AKShare 备用通道。

    东财 push2ex 是这三类池子的唯一来源，一旦被封，情绪模块、连板梯队、
    竞价雷达会全部失效。这里通过 AKShare 走另一套域名取同样数据。

    字段映射（AKShare 中文列 -> 东财短字段），数值口径必须一致：
      c=代码  n=名称  zdp=涨跌幅  p=最新价*100(东财用分)
      lbc=连板数  fbt=首次封板时间(int)  fund=封板资金  hybk=所属行业
      hs=换手率  ltsz=流通市值  amount=成交额  zbc=炸板次数
    """
    try:
        import akshare as ak
    except ImportError:
        return []

    fn_map = {
        'ZT': lambda d: ak.stock_zt_pool_em(date=d),
        'ZB': lambda d: ak.stock_zt_pool_zbgc_em(date=d),
        'DT': lambda d: ak.stock_zt_pool_dtgc_em(date=d),
    }
    fn = fn_map.get(kind)
    if fn is None:
        return []

    try:
        df = fn(ymd)
        if df is None or len(df) == 0:
            return []
    except Exception:
        return []

    def _i(v, default=0):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return default

    def _f(v, default=0.0):
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    pool = []
    for _, r in df.iterrows():
        code = str(r.get('代码') or '').strip().zfill(6)
        if not code or code == '000000':
            continue
        # fbt 东财是 HHMMSS 整数；AKShare 给的是 '092500' 字符串
        fbt_raw = r.get('首次封板时间')
        fbt = _i(str(fbt_raw).replace(':', '')) if fbt_raw not in (None, '', '-') else 0
        lbt_raw = r.get('最后封板时间')
        lbt = _i(str(lbt_raw).replace(':', '')) if lbt_raw not in (None, '', '-') else 0
        fund_col = '封板资金' if '封板资金' in df.columns else '封单资金'
        pool.append({
            'c': code,
            'm': 1 if code.startswith(('6', '5', '9')) else 0,
            'n': str(r.get('名称') or code),
            'p': round(_f(r.get('最新价')) * 1000),     # 东财 p 单位是【厘】(1/1000元), AKShare 是元
            'zdp': _f(r.get('涨跌幅')),
            'amount': _f(r.get('成交额')),
            'ltsz': _f(r.get('流通市值')),
            'tshare': _f(r.get('总市值')),
            'hs': _f(r.get('换手率')),
            'lbc': max(1, _i(r.get('连板数'), 1)),
            'fbt': fbt,
            'lbt': lbt,
            'fund': _f(r.get(fund_col)),
            'zbc': _i(r.get('炸板次数')),
            'hybk': str(r.get('所属行业') or ''),
            'zttj': {},
            '_src': 'akshare',
        })
    return pool



def _pool(kind, ymd):
    today_ymd = dt.date.today().strftime('%Y%m%d')
    cache_key = (kind, ymd)
    if cache_key in _POOL_CACHE:
        val, ts = _POOL_CACHE[cache_key]
        if ymd < today_ymd or (time.time() - ts) < 30.0:
            return val

    # 注意: DT池必须用 fund 排序 —— fbt(首次封板时间)字段跌停股没有, 会恒返回空pool
    # (2026-08-25 三方会诊实证: 曾误判"跌停池无历史数据", 实为 sort 参数假象)
    sort = 'fund%3Aasc' if kind == 'DT' else 'fbt%3Aasc'
    u = f'https://push2ex.eastmoney.com/getTopic{kind}Pool?ut={UT}&dpt=wz.ztzt&Pageindex=0&pagesize=500&sort={sort}&date={ymd}'
    try:
        raw_resp = http(u, timeout=3.0, retries=1)
        j = json.loads(raw_resp)
        if not isinstance(j, dict) or not j.get('data'):
            # ut token 失效时东财返回的是 rc!=0 / 无 data 字段的响应体。
            # 注意: 这属于"东财侧异常"，不代表当天真的没有涨停股 ——
            # 必须先尝试 AKShare 备用通道，否则 ut 失效会让整个情绪模块静默返回空。
            _bk = _pool_akshare(kind, ymd)
            if _bk:
                _POOL_CACHE[cache_key] = (_bk, time.time())
                return _bk
            # 备用也没有：负缓存一份空结果，避免情绪回溯(最多8日x3池)反复打上游
            _POOL_CACHE[cache_key] = ([], time.time())
            return []
        d = j.get('data') or {}
        pool = d.get('pool') or []
        # 修复 (2026-10-18): 原实现只在 pool 非空时写缓存，空池每次都要重新请求。
        # emotion() 会回溯 8 个交易日 x 3 个池，非交易日/无数据日会全部落空，
        # 每次都打满上游。现在空结果也进负缓存（当日 30s / 历史日长期有效）。
        _POOL_CACHE[cache_key] = (pool, time.time())
        return pool
    except Exception:
        # 网络/解析异常不写负缓存 —— 否则会把"请求失败"伪装成"当天没有涨停池"，
        # 让上层误判为非交易日。失败就让下次重试。
        # 东财 push2ex 不可用(被封/超时)：降级到 AKShare 备用通道
        _bk = _pool_akshare(kind, ymd)
        if _bk:
            _POOL_CACHE[cache_key] = (_bk, time.time())
            return _bk
        return []

# ---------- 情绪指数打分 (迁移至 core.emotion，保持外观兼容) ----------
# 已在文件头部从 core.emotion 统一导入:
# _emotion_band, _emotion_score_v1, _emotion_score_v2, _effect_flat

_EFFECT_CACHE = {'t': 0.0, 'data': None}

def _effect_metrics(ttl=300.0):
    """赚钱效应指标: 复用竞价雷达(premium_summary / promotion_metrics), 结果缓存 ttl 秒。
    竞价雷达单次约 6s, 缓存避免 web 每次刷新都付这个代价。"""
    now = time.time()
    if _EFFECT_CACHE['data'] is not None and (now - _EFFECT_CACHE['t']) < ttl:
        return _EFFECT_CACHE['data']
    out = {'available': False, 'reason': 'unavailable'}
    try:
        import auction_radar as _ar          # 同目录; 延迟导入避免与 auction_radar->stock_dashboard 的循环
        r = _ar.get_auction_radar() or {}
        ps = r.get('premium_summary') or {}
        pm = r.get('promotion_metrics') or {}
        prem, rate = ps.get('avg_curr_pct'), pm.get('rate_1to2')
        # 修复 (2026-10-18): 晋级率在休市/非相邻交易日会返回 None（无法计算），
        # 但赚钱效应分数仍可由"昨涨停溢价"单独给出。旧实现要求两者同时存在，
        # 导致休市日与历史回补场景下赚钱效应永久不可用，浪费了一半有效信号。
        # 现在：有溢价就按溢价给分，晋级率缺失时降权(仅用 premium 归一化)，
        # 并在返回值里标注 rate_available 让前端区分。
        if r.get('status') == 'ok' and prem is not None:
            prem_c = max(-5.0, min(5.0, float(prem)))
            prem_n = (prem_c + 5.0) / 10.0
            rate_available = rate is not None
            if rate_available:
                rate_n = min(float(rate) / 50.0, 1.0)
                score = 0.6 * prem_n + 0.4 * rate_n
            else:
                rate_n = None
                score = prem_n          # 仅溢价口径
            out = {'available': True, 'premium': round(float(prem), 2),
                   'premium_clamped': round(prem_c, 2),
                   'rate_1to2': (round(float(rate), 1) if rate_available else None),
                   'rate_available': rate_available,
                   'premium_norm': round(prem_n, 3),
                   'rate_norm': (round(rate_n, 3) if rate_available else None),
                   'score': round(score, 4),
                   'y_date': ps.get('y_date'), 'tag': ps.get('sentiment_tag'),
                   # preview=True 表示该组数据是"历史两交易日"复盘口径，而非当日实况
                   'preview': bool(ps.get('preview_mode')),
                   'tag_live': ps.get('sentiment_tag_live')}
        else:
            out = {'available': False,
                   'reason': 'radar status=%s prem=%s rate=%s' % (r.get('status'), prem, rate)}
    except Exception as e:
        out = {'available': False, 'reason': repr(e)[:120]}
    _EFFECT_CACHE.update({'t': now, 'data': out})
    return out


def _archive_eligible(ymd, recs, n_zt, n_zb, n_dt, max_lb, force=False):
    """情绪档案写入资格（2026-10-08 门禁 v2）。返回 (bool, 原因)。

    三层校验，缺一不可：
      ① 该日必须在交易所日K里 —— **包含"今天"**（收盘后日K必有当天行）。
         日K取不到/为空 → fail-closed：宁可今天不归档，也不写可能是假的数据
         （旧版 bug：`ymd < today` 把"今天"排除在校验外，而 20261001 那条假记录
           恰恰是"当天是假期"时写进去的 —— 门禁放行了当初翻车的那一类）
      ② 四项数值与最近一条存档**完全相同** → 判为"接口对休市日回吐最近交易日数据"
         （10-01 假记录的真正根因：push2ex 对任意日期返回最近一个池）
      ③ FORCE_ARCHIVE=1 可绕过 ①，供人工补录；② 始终生效（错了就显式报错让你确认）
    """
    import os as _os
    force_bypass = bool(force or _os.environ.get('FORCE_ARCHIVE') == '1')
    
    # 步骤 ①: 校验是否为交易所有效交易日
    if not force_bypass:
        try:
            kl = kline_tx('sh000001', 60)
            dates = [str(row[0])[:10].replace('-', '') for row in kl] if kl else []
        except Exception as e:
            return False, f'日K取数异常({type(e).__name__}) → fail-closed 拒绝入库'
        if not dates:
            return False, '日K为空 → fail-closed 拒绝入库'
        
        # 容错: 若为当天工作日 15:00~18:00 收盘后，腾讯日K偶发存在 5~10 分钟切线延迟
        _now = dt.datetime.now()
        is_today_post_close = (ymd == _now.strftime('%Y%m%d') and _now.hour >= 15 and _now.weekday() < 5)
        
        if ymd not in dates:
            # 尝试看实时指数是否有真实交易（日K偶发存在5~10分钟切线延迟，但实时行情时间戳必须是今天且成交额大于0）
            has_real_trading = False
            if is_today_post_close:
                try:
                    sh_q = tx_realtime(['sh000001'])
                    if sh_q:
                        q0 = sh_q[0]
                        # 严谨校验: 行情时间戳必须与传入ymd完全一致，且必须有真实成交额
                        # 腾讯行情在休市日仍返回前一交易日收盘价(恒>0)，但时间戳绝不会是休市日
                        q_date = str(q0.get('trade_time', ''))[:8].replace('-', '')
                        q_amt = float(q0.get('raw_amount', 0))
                        if q_date == ymd and q_amt > 0:
                            has_real_trading = True
                except Exception:
                    pass
            if not has_real_trading:
                return False, f'该日不在交易所日K中（日K最近交易日 {dates[-1]}）→ 非交易日/休市'

    # 步骤 ②: 回吐检测 (即使强制放行 ①，若与前一日完全雷同也要发出告警)
    prev = [r for r in recs if r.get('date') and str(r.get('date')) < str(ymd)]
    if prev:
        p = prev[-1]
        try:
            same = (int(p.get('zt') or -1) == int(n_zt) and int(p.get('zb') or -1) == int(n_zb)
                    and int(p.get('dt') or -1) == int(n_dt) and int(p.get('max_lb') or -1) == int(max_lb))
        except Exception:
            same = False
        if same:
            msg = (f'四项数值与最近交易日 {p.get("date")} 完全相同 '
                   f'(zt{int(n_zt)}/zb{int(n_zb)}/dt{int(n_dt)}/{int(max_lb)}板) '
                   f'→ 疑似接口回吐最近数据')
            if force_bypass:
                return True, f'FORCE_ARCHIVE 显式放行 (但请注意: {msg})'
            return False, msg + '；若确认是真实交易日请用 FORCE_ARCHIVE=1 重跑'

    return True, '通过"日K存在 + 非回吐"双重校验' if not force_bypass else 'FORCE_ARCHIVE 显式放行'


def analyze_ladder_faults(ladder_grouped=None, first_boards=None, max_lb=1):
    """
    连板梯队结构与断层诊断算法（吸纳 vibe-astock / 寻龙诀实战经验）。

    业务逻辑：
    1. 统计各高度板位个股家数；
    2. 若最高连板 max_height <= 2: 属于空间受限（无连板标杆赚钱效应）；
    3. 若最高连板 max_height >= 3:
       检查区间 [2, max_height - 1] 的所有板位。若存在板位股票数为 0，则判定为梯队断层！
       - 若最高断层在 max_height - 1 (如最高5板但4板断层): 诊断为'高位断层·独木难支'，防龙头孤立跳水；
       - 若 2板 为 0 (1进2全军覆没): 诊断为'接力断层·冰点失血'，防打板全面退潮；
       - 若处于中间板位: 诊断为'中位断层·梯队分化'；
       - 若无断层: 诊断为'梯队完整·良性接力'。
    """
    counts = {}
    fb_len = len(first_boards) if isinstance(first_boards, list) else int(first_boards or 0)
    counts[1] = fb_len

    if isinstance(ladder_grouped, dict):
        for k, v in ladder_grouped.items():
            try:
                ik = int(k)
                if ik >= 2:
                    counts[ik] = len(v) if isinstance(v, list) else int(v or 0)
            except (ValueError, TypeError):
                continue
    elif isinstance(ladder_grouped, list):
        for item in ladder_grouped:
            if isinstance(item, dict):
                lb = item.get('lbc', 1)
                try:
                    ilb = int(lb)
                    if ilb >= 2:
                        counts[ilb] = counts.get(ilb, 0) + 1
                except (ValueError, TypeError):
                    continue

    max_height = max([int(max_lb or 1)] + list(counts.keys())) if counts else int(max_lb or 1)

    if max_height <= 2:
        has_fault = False
        fault_levels = []
        status = "low_suppression"
        status_desc = f"连板空间受限（市场最高仅{max_height}板，缺乏高度标杆）"
        tag = "空间受限"
    else:
        fault_levels = [lvl for lvl in range(2, max_height) if counts.get(lvl, 0) == 0]
        if not fault_levels:
            has_fault = False
            status = "healthy"
            status_desc = f"梯队完整连贯（2~{max_height}板层层递进无断档，接力梯队健康）"
            tag = "梯队完整"
        else:
            has_fault = True
            fault_str = "、".join(f"{lvl}板" for lvl in fault_levels)
            if (max_height - 1) in fault_levels:
                status = "high_gap"
                status_desc = f"高位梯队断层（{fault_str}空缺，最高{max_height}板孤木难支，警惕高位分歧杀跌）"
                tag = "高位断层"
            elif 2 in fault_levels:
                status = "seed_gap"
                status_desc = f"首板接力断层（2板空缺/1进2失败，接力意愿冰点）"
                tag = "接力断层"
            else:
                status = "mid_gap"
                status_desc = f"中位梯队断层（{fault_str}空缺，中生代断档，个股分化严重）"
                tag = "中位断层"

    return {
        "max_height": max_height,
        "counts": {str(k): v for k, v in sorted(counts.items())},
        "fault_levels": fault_levels,
        "has_fault": has_fault,
        "status": status,
        "status_desc": status_desc,
        "tag": tag,
    }


def snapshot_file_path(ymd):
    clean_ymd = str(ymd).replace('-', '')[:8]
    return os.path.join(SNAPSHOT_DIR, f"snapshot_{clean_ymd}.json")


def get_daily_snapshot(ymd):
    """读取指定交易日的盘后不可变快照。"""
    p = snapshot_file_path(ymd)
    if os.path.exists(p):
        try:
            with open(p, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
    return None


def archive_daily_snapshot(ymd, emotion_data, force=False):
    """
    保存 15:35 盘后定稿不可变快照（吸纳 vibe-astock 不可变归档设计）。

    不可变性守则：
    1. 盘后一旦归档入库，标记 immutable=True；若已有快照且非 force，拒绝随意覆写；
    2. 只有收盘后（15:00 之后，或带 force=True 明确补录）才允许生成归档，杜绝盘中未定稿数据污染；
    3. 写入采用原子写入（写 tmp 再 replace），防止断电或并发写导致 json 损坏。
    """
    if not ymd or not emotion_data:
        return False, "参数缺失"

    clean_ymd = str(ymd).replace('-', '')[:8]
    p = snapshot_file_path(clean_ymd)

    # 不可变守卫
    if os.path.exists(p) and not force:
        return True, f"不可变快照已存在 ({p})"

    _now = dt.datetime.now()
    is_today = (clean_ymd == _now.strftime('%Y%m%d'))
    if is_today and _now.hour < 15 and not force:
        return False, "盘中未收盘定稿 (需 15:00 后收盘归档)"

    try:
        snapshot = {
            "date": clean_ymd,
            "archived_at": _now.strftime("%Y-%m-%d %H:%M:%S"),
            "immutable": True,
            "score": emotion_data.get("score"),
            "band": emotion_data.get("band"),
            "zt": emotion_data.get("zt"),
            "zb": emotion_data.get("zb"),
            "dt": emotion_data.get("dt"),
            "max_lb": emotion_data.get("max_lb"),
            "stage": emotion_data.get("stage"),
            "diverge": emotion_data.get("diverge"),
            "effect": emotion_data.get("effect"),
            "ladder_analysis": emotion_data.get("ladder_analysis"),
            "ladder_grouped": emotion_data.get("ladder_grouped"),
            "first_boards": emotion_data.get("first_boards"),
            "limit_down": emotion_data.get("limit_down"),
            "themes_list": emotion_data.get("themes_list"),
            "board_quality": emotion_data.get("board_quality"),
            "promotion": emotion_data.get("promotion"),
            "zha_ban": emotion_data.get("zha_ban"),
        }
        tmp_p = p + f".tmp.{os.getpid()}"
        with open(tmp_p, 'w', encoding='utf-8') as fp:
            json.dump(snapshot, fp, ensure_ascii=False, indent=2)
        os.replace(tmp_p, p)
        return True, f"成功归档不可变快照 -> {p}"
    except Exception as e:
        return False, f"快照归档失败: {e}"


# ---------- 情绪视图模型拼装（自 emotion() 内嵌闭包提取，独立可单测） ----------
def _slim_zt_stock(d):
    """涨停原始行 -> 前端精简视图（金额单位: 亿）。"""
    return dict(code=d.get('c', ''), name=d.get('n', ''), lbc=d.get('lbc', 1),
                hybk=d.get('hybk', ''), fbt=d.get('fbt', ''), zbc=d.get('zbc', 0),
                hs=round(d.get('hs', 0), 1), lbt=d.get('lbt', ''),
                fund=round(d.get('fund', 0) / 1e8, 2),
                ltsz=round(d.get('ltsz', 0) / 1e8, 1))


def _strength_key(d):
    """强弱排序: 连板数降序 > 封板时间升序 > 炸板升序 > 封单降序。"""
    return (-d.get('lbc', 1), d.get('fbt', 999999), d.get('zbc', 0), -d.get('fund', 0))


def _classify_strength(stocks):
    """题材内强弱分级 -> (龙头, 前排, 后排, 中军候选)。

    龙头: 连板最高者(同最高<=2只全取, 否则取1只); 前排: 连板>=2 或 10:30前封板且炸板<=1;
    后排: 其余; 中军候选: 流通市值最大者。
    """
    if not stocks:
        return [], [], [], None
    sorted_s = sorted(stocks, key=_strength_key)
    max_lb = max(s.get('lbc', 1) for s in sorted_s)
    top_lb = [s for s in sorted_s if s.get('lbc', 1) == max_lb]
    leaders = top_lb[:2] if len(top_lb) <= 2 else top_lb[:1]
    leader_codes = {s.get('c') for s in leaders}
    front = [s for s in sorted_s if s.get('c') not in leader_codes and
             (s.get('lbc', 1) >= 2 or (s.get('fbt', 999999) <= 103000 and s.get('zbc', 0) <= 1))]
    front_codes = {s.get('c') for s in front}
    back = [s for s in sorted_s if s.get('c') not in leader_codes and s.get('c') not in front_codes]
    zhongjun = max(sorted_s, key=lambda s: s.get('ltsz', 0)) if sorted_s else None
    return leaders, front, back, zhongjun


def _board_type_code(d):
    """封板质量分类: 一字 / T字 / 换手 / 烂板。"""
    zbc = d.get('zbc', 0)
    fbt = d.get('fbt', 999999)
    hs = d.get('hs', 0)
    if zbc == 0 and fbt <= 92530:
        return '一字'
    elif zbc == 1:
        return 'T字'
    elif zbc >= 5 or hs >= 15:
        return '烂板'
    else:
        return '换手'




def _streak(code, start_idx, pools_set):
    """从 start_idx 起往前数连续出现在涨停池的天数, 遇到断档(空集合)即停。

    pools_set: [(date_str, {code_set}), ...] 从今日往前, **必须含空日占位**,
    否则连续遍历会跨过断档把更早的交易日当作前一天, 导致连板数虚高。
    """
    n = 0
    for _j in range(start_idx, len(pools_set)):
        if code in pools_set[_j][1]:
            n += 1
        else:
            break
    return n

def emotion(ymd=None):
    w('\n===== [4] 市场情绪(涨停池实测) =====')
    if not ymd:
        ymd = dt.date.today().strftime('%Y%m%d')
    # 修复 (2026-10-18): 若传入/默认的日期不是真实交易日（周末、节假日），
    # 直接回退到最近的真实交易日。上游涨停池接口对非交易日会回吐最近交易日的
    # 快照，"池子有数据"因此不能作为交易日判据 —— 否则周日会拿着周五的数据
    # 冒充"今日情绪"，并让归档门禁误判、把非交易日写进历史。
    try:
        import trading_calendar as _tcal
    except ImportError:
        try:
            from scripts import trading_calendar as _tcal
        except ImportError:
            _tcal = None
    if _tcal is not None:
        _real = _tcal.latest_trading_day(ymd)
        if _real and _real != ymd:
            w(f'(注: {ymd} 非交易日, 自动回溯至最近交易日 {_real})')
            ymd = _real
    req_ymd = ymd
    try:
        # 两段式回溯(dsh方案D): 先用 ZT 池单请求探测哪天有数, 命中后再补拉 ZB/DT
        # —— 最坏情形从 7日x3池=21次请求 降为 探测N次+命中日2次; 且与 backfill 的
        # "ZT池有数=该日为有效交易日"判定规则统一
        hit_day = ymd
        zt = _pool('ZT', ymd)
        if not zt:  # 盘前/休市: 自动回溯最近有数据的交易日
            base = dt.datetime.strptime(ymd, '%Y%m%d').date()
            for i in range(1, 8):
                prev = (base - dt.timedelta(days=i)).strftime('%Y%m%d')
                zt = _pool('ZT', prev)
                if zt:
                    hit_day = prev
                    break
            else:
                w('(近7日无涨停池数据, 放弃)')
                return None
        zb = _pool('ZB', hit_day)
        dtl = _pool('DT', hit_day)
        # 归属日 = 请求参数归属(回溯命中哪个 prev 就记哪天), 不用接口返回的 qdate
        # (实证: push2ex 历史查询恒返回 qdate=查询当日, 用它归档会把昨日数据错标成今日,
        #  并占据当日去重槽导致收盘真实数据被静默跳过 —— 盘前/收盘双跑场景必毒化档案)
        ymd = hit_day
        if ymd != req_ymd:
            w(f'(非交易日/盘前, 数据实为最近交易日 {ymd}, 已按该日归档)')
        n_zt, n_zb, n_dt = len(zt), len(zb), len(dtl)
        max_lb = max([d.get('lbc', 1) for d in zt], default=0)
        br = n_zb / (n_zt + n_zb) * 100 if (n_zt + n_zb) else 0
        eff = _effect_metrics()
        s_v1 = _emotion_score_v1(n_zt, n_zb, n_dt, max_lb)
        s, diverge = _emotion_score_v2(n_zt, n_zb, n_dt, max_lb, eff)
        band = _emotion_band(s)
        w(f'日期:{ymd}  涨停:{n_zt} 炸板:{n_zb}(率{br:.0f}%) 跌停:{n_dt} 最高连板:{max_lb}板')
        w(f'>>> 情绪指数: {s:.2f}/100 [{band}] <<<   (v1 公式对照: {s_v1:.2f})')
        if eff.get('available'):
            # rate_1to2 可能为 None（休市/非相邻交易日无法计算晋级率）。
            # 旧写法 '%.1f%%' % None 抛 TypeError，被外层 except 吞掉 ->
            # 整个 emotion() 返回 None -> 页面 emotion 变空对象 {}。
            _rate = eff.get('rate_1to2')
            _rate_txt = ('%.1f%%' % _rate) if _rate is not None else '不可用(休市)'
            w('赚钱效应: 昨日涨停今均溢价 %+.2f%% | 1进2晋级率 %s | 昨日=%s [%s]' % (
                eff['premium'], _rate_txt, eff.get('y_date') or '', eff.get('tag') or ''))
        else:
            w('赚钱效应: 取不到(%s) -> 该项按中性 12.5 分计入, 已标注 effect_unavailable' % eff.get('reason'))
        if diverge == 'score_high_effect_weak':
            w('!! 背离: 情绪分偏高但赚钱效应偏弱 —— 广度/高度在装没事, 接力资金不认账')
        elif diverge == 'score_low_effect_strong':
            w('** 背离: 情绪分偏低但赚钱效应转强 —— 冰点试错窗口(负溢价收敛/晋级率回升)')
        ladder = sorted([d for d in zt if d.get('lbc', 1) >= 2], key=lambda x: -x['lbc'])
        w('连板梯队: ' + ('  '.join(f"{d['lbc']}板[{d.get('hybk','')}]{d['n']}({d['c']})" for d in ladder[:12]) or '无'))
        themes = {}
        for d in zt: themes[d.get('hybk', '?')] = themes.get(d.get('hybk', '?'), 0) + 1
        w('题材分布: ' + '  '.join(f'{k}{v}家' for k, v in sorted(themes.items(), key=lambda x: -x[1])[:8]))
        # === 题材内个股强弱分级（龙头/前排/后排）===
        # === 详细列表（供web展示）===
        first_boards = [_slim_zt_stock(d) for d in zt if d.get('lbc', 1) == 1]
        # 连板梯队按板数分组
        ladder_grouped = {}
        for d in ladder:
            lb = d.get('lbc', 2)
            ladder_grouped.setdefault(lb, []).append(_slim_zt_stock(d))
        # 连板梯队断层结构诊断（吸纳 vibe-astock / 寻龙诀实战经验）
        ladder_analysis = analyze_ladder_faults(ladder_grouped, first_boards, max_lb)
        if ladder_analysis.get('has_fault'):
            w(f'** 梯队断层预警: [{ladder_analysis["tag"]}] {ladder_analysis["status_desc"]}')
        else:
            w(f'梯队结构诊断: [{ladder_analysis["tag"]}] {ladder_analysis["status_desc"]}')
        # 跌停列表
        limit_down = [dict(code=d.get('c', ''), name=d.get('n', ''), hybk=d.get('hybk', '')) for d in dtl]
        # 题材分布（按涨停家数排序，含领涨股）
        _theme_first = {}
        _theme_stocks = {}
        for d in zt:
            _hy = d.get('hybk', '?')
            if _hy not in _theme_first:
                _theme_first[_hy] = d.get('n', '')
            _theme_stocks.setdefault(_hy, []).append(d)
        themes_list = []
        for k, v in sorted(themes.items(), key=lambda x: -x[1]):
            t_stocks = _theme_stocks.get(k, [])
            leaders, front, back, zhongjun = _classify_strength(t_stocks)
            themes_list.append(dict(
                name=k, count=v, top_stock=_theme_first.get(k, ''),
                leaders=[_slim_zt_stock(s) for s in leaders],
                front=[_slim_zt_stock(s) for s in front],
                back=[_slim_zt_stock(s) for s in back],
                zhongjun=_slim_zt_stock(zhongjun) if zhongjun else None
            ))
        # === 封板质量分类（一字/T字/换手/烂板）===
        board_quality = {'一字': [], 'T字': [], '换手': [], '烂板': []}
        for d in zt:
            bt = _board_type_code(d)
            board_quality[bt].append(_slim_zt_stock(d))
        # === 炸板池数据 ===
        zha_ban = []
        for d in zb:
            zha_ban.append(dict(
                code=d.get('c', ''), name=d.get('n', ''),
                zbc=d.get('zbc', 0), zf=round(d.get('zf', 0), 1),
                zdp=round(d.get('zdp', 0), 2), hybk=d.get('hybk', ''),
                hs=round(d.get('hs', 0), 1), amount=round(d.get('amount', 0) / 1e8, 2)))
        # === 晋级梯队（通过历史涨停池连续出现次数判断连板数，不依赖lbc字段）===
        promotion = {}
        try:
            _base = dt.datetime.strptime(ymd, '%Y%m%d').date()
            # 获取最近8个自然日的涨停池（足够判断最高连板）。
            # 关键: 断档日(周末/休市/接口无数据)必须保留为空集合占位, 不能跳过 ——
            # 旧实现 `if _pool_data: append` 会把空日挤出列表, 让 _streak 的连续遍历
            # 跨过断档继续累加(如 T-2 无数据时把 T-3 当作 T-2 的延续), 连板数虚高。
            _pools = []  # [(date_str, [row...]), ...] 从今日往前, 含空日
            for _i in range(0, 8):
                _day = (_base - dt.timedelta(days=_i)).strftime('%Y%m%d')
                _pools.append((_day, _pool('ZT', _day) or []))
            # 至少要有今日+昨日的**实际数据**才谈得上晋级统计
            if len([1 for _, _rows in _pools if _rows]) >= 2:
                _pools_set = [(_day, {d.get('c', '') for d in _rows}) for _day, _rows in _pools]
                _today_codes = _pools_set[0][1]
                _yesterday_codes = _pools_set[1][1]

                # 昨日每只股票的真实连板数 / 今日每只股票的真实连板数
                _y_lbc = {c: _streak(c, 1, _pools_set) for c in _yesterday_codes}
                _t_lbc = {c: _streak(c, 0, _pools_set) for c in _today_codes}
                # 名称映射复用已拉到的行数据, 不再二次请求 _pool
                _t_names = {d.get('c', ''): d.get('n', d.get('c', '')) for d in _pools[0][1]}
                _y_names = {d.get('c', ''): d.get('n', d.get('c', '')) for d in _pools[1][1]}
                # 动态计算到最高板+1
                _max_lb = max(_t_lbc.values()) if _t_lbc else 1
                for src in range(1, _max_lb + 1):
                    dst = src + 1
                    candidates = [c for c, lb in _y_lbc.items() if lb == src]
                    if not candidates:
                        continue
                    # 晋级成功=昨日src板 ∩ 今日连板数>=dst
                    success = [c for c in candidates if _t_lbc.get(c, 0) >= dst]
                    failed = [c for c in candidates if _t_lbc.get(c, 0) < dst]
                    names = [_t_names.get(c, c) for c in success]
                    failed_names = [_y_names.get(c, c) for c in failed]
                    promotion[f'{src}进{dst}'] = dict(
                        total=len(candidates), success=len(success), failed=len(failed),
                        rate=round(len(success) / len(candidates) * 100, 1) if candidates else 0,
                        names=names[:10], failed_names=failed_names[:10])
        except Exception as _e:
            print(f'[晋级梯队计算失败] {_e}')
        hist = os.path.join(DATA_DIR, 'sentiment_history.jsonl')
        # 归档守卫: 当日15:00前的数据是盘中快照(涨停数只增不减、跌停未定型), 写档会占死
        # 当日归档槽导致收盘真实数据被去重跳过(2026-08-25 实证毒化)。当日未收盘一律不入库。
        _now = dt.datetime.now()
        result = dict(score=s, band=band, zt=n_zt, zb=n_zb, dt=n_dt, max_lb=max_lb, ymd=ymd,
                      first_boards=first_boards, ladder_grouped=ladder_grouped,
                      limit_down=limit_down, themes_list=themes_list, promotion=promotion,
                      board_quality=board_quality, zha_ban=zha_ban, algo='v2',
                      score_v1=round(s_v1, 2), effect=_effect_flat(eff), diverge=diverge,
                      effect_available=eff.get('available'), ladder_analysis=ladder_analysis)
        if ymd == _now.strftime('%Y%m%d') and _now.hour < 15:
            w('(盘中快照不写档, 待15:00收盘后再跑一次归档)')
            return result
        recs = []
        if os.path.exists(hist):
            recs = [json.loads(l) for l in open(hist, encoding='utf-8')]
        # 同日只留一条：判断仍然保留（已归档的日期不因重跑而被改写），
        # 但落盘改走 _hist_upsert 原子重写 —— 即便两进程同时穿过上面这个判断，也只会留下一条。
        if not any(r.get('date') == ymd for r in recs):
            # 交易日有效性门禁 v2: 日K存在(含今天) + 非"接口回吐" + 取数失败 fail-closed
            _ok, _why = _archive_eligible(ymd, recs, n_zt, n_zb, n_dt, max_lb)
            if not _ok:
                w(f'({ymd} 归档门禁拒绝: {_why})')
            else:
                _new = dict(date=ymd, score=round(s, 2), band=band, zt=n_zt,
                            zb=n_zb, dt=n_dt, max_lb=max_lb, algo='v2',
                            score_v1=round(s_v1, 2), effect=_effect_flat(eff),
                            diverge=diverge)
                _hist_upsert(hist, _new)
                w(f'(已存档 共{len(recs)+1}条)')
        return result
    except Exception as e:
        # 修复 (2026-10-18): 原来只打印 str(e)，堆栈全丢。"must be real number,
        # not NoneType" 这类消息无法定位到具体行，排查成本极高（本次连踩三处）。
        # 改为打印完整堆栈，便于定位；返回值语义不变。
        import traceback as _tb
        w(f'[情绪数据失败] {type(e).__name__}: {e}')
        w(_tb.format_exc())
        return None

# ---------- 5. 两融余额 ----------
def margin_total():
    w('\n===== [5] 两市融资余额 =====')
    try:
        u = ('https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPTA_RZRQ_LSHJ'
             '&columns=DIM_DATE,RZRQYE,RZRQYECZ&sortColumns=DIM_DATE&sortTypes=-1&pageSize=4&pageNumber=1')
        rows = json.loads(http(u))['result']['data']
        vals = [(str(r['DIM_DATE'])[:10], float(r['RZRQYE']) / 1e8) for r in rows]
        out = []
        for idx, (d, ye) in enumerate(vals):  # vals[0]最新; 环比=前一交易日(更早)之差
            delta = f'环比{ye-vals[idx+1][1]:+,.0f}亿' if idx + 1 < len(vals) else ''
            w(f'{d}: {ye:,.0f}亿 {delta}')
            out.append(dict(date=d, value=round(ye), delta=delta))
        w('(>2.6万亿为历史高位区)')
        net3 = round(vals[0][1] - vals[3][1]) if len(vals) >= 4 else None
        if net3 is not None:
            w(f'(近3个交易日累计净变化: {net3:+,}亿)')
        return dict(days=out, net_3d=net3)
    except Exception as e:
        w(f'[两融失败] {e}')
        return None

# ---------- 5.5 预判闭环(dsh方案A): 盘前入库 → 收盘对照 → 周报命中率 ----------
_PRED_FP = os.path.join(DATA_DIR, 'pred.jsonl')

def _pred_load():
    if not os.path.exists(_PRED_FP):
        return []
    out = []
    for l in open(_PRED_FP, encoding='utf-8'):
        l = l.strip()
        if not l:
            continue
        try:
            out.append(json.loads(l))
        except Exception:
            pass
    return out

def _pred_atomic_write(recs):
    """整表重写(原子): tmp + os.replace, 防 web 常驻进程读到半截文件"""
    recs.sort(key=lambda r: str(r.get('date', '')))
    tmp = _PRED_FP + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    os.replace(tmp, _PRED_FP)

def pred_save(date=None, dir=None, score_lo=None, score_hi=None,
              focus='', text='', model='default'):
    ymd = (str(date or dt.date.today().strftime('%Y%m%d'))).replace('-', '')
    assert dir in ('up', 'down', 'flat'), '非法 dir: %s' % dir
    if (score_lo is None) != (score_hi is None):
        raise ValueError('--score-lo 与 --score-hi 必须成对提供')
    if score_lo is not None:
        assert 0 <= score_lo <= score_hi <= 100, 'score 区间非法'
    rec = dict(date=ymd, dir=dir, score_lo=score_lo, score_hi=score_hi,
               focus=[x.strip() for x in str(focus).split(',') if x.strip()],
               text=text, model=model or 'default',
               created_at=dt.datetime.now().strftime('%Y-%m-%dT%H:%M:%S'))
    recs = _pred_load()
    # 唯一约束: 同 (date, model) 覆盖(last-wins), 盘前重跑不产生重复行
    recs = [r for r in recs
            if not (r.get('date') == ymd and r.get('model', 'default') == rec['model'])]
    recs.append(rec)
    _pred_atomic_write(recs)
    w('[pred 已存] %s dir=%s 情绪区间%s~%s focus=%s model=%s' %
      (ymd, dir, score_lo, score_hi, rec['focus'], rec['model']))
    return rec

def pred_check(date=None):
    """收盘对照: 上证方向(±0.3%中性带) + 当日情绪分数区间。幂等, 重跑覆盖 result。
    注意: 行情通道只有实时值, 本命令设计为收盘当天运行(cron 15:30); 用历史日期调用时
    idx_pct 为当前行情而非该日行情, 结果仅供参考(输出中会提示)。"""
    _today = dt.date.today().strftime('%Y%m%d')
    ymd = (str(date or _today)).replace('-', '')
    if ymd != _today:
        w('(注意: %s 非今日, 对照用的是实时行情而非该日行情, 结果仅供测试参考)' % ymd)
    preds = [p for p in _pred_load() if p.get('date') == ymd]
    if not preds:
        w('(无 %s 预判, 跳过对照)' % ymd)
        return None
    pred = max(preds, key=lambda p: p.get('created_at', ''))  # 同日多模型取最新
    try:
        pct = tx_realtime(['sh000001'])[0]['pct']  # 复用现有行情通道
    except Exception as e:
        w(f'[对照失败] 上证行情取不到: {e}')
        return None
    fp = os.path.join(DATA_DIR, 'sentiment_history.jsonl')
    rec = None
    if os.path.exists(fp):
        for l in open(fp, encoding='utf-8'):
            try:
                r = json.loads(l)
                if r.get('date') == ymd:
                    rec = r
                    break
            except Exception:
                pass
    if rec is None:
        w('(当日 %s 无情绪记录: 未收盘或节假日, 不写对照)' % ymd)
        return None
    thr = float(os.environ.get('STOCK_PRED_THR', '0.3'))
    actual_dir = 'up' if pct >= thr else ('down' if pct <= -thr else 'flat')
    dir_hit = pred.get('dir') == actual_dir
    ascore = float(rec.get('score', 0))
    score_hit = None
    if pred.get('score_lo') is not None and pred.get('score_hi') is not None:
        score_hit = pred['score_lo'] <= ascore <= pred['score_hi']
    result = dict(idx_pct=round(pct, 2), actual_dir=actual_dir,
                  actual_score=ascore, dir_hit=dir_hit, score_hit=score_hit,
                  checked_at=dt.datetime.now().strftime('%Y-%m-%dT%H:%M:%S'))
    preds2 = _pred_load()
    for r in preds2:
        if (r.get('date') == ymd and r.get('created_at') == pred.get('created_at')):
            r['result'] = result
    _pred_atomic_write(preds2)
    _zh = {'up': '看多', 'down': '看空', 'flat': '平盘'}
    w('[对照] %s 预判%s(情绪区间%s~%s) → 实际上证%+.2f%%[%s] 情绪%.1f → 方向%s 分数%s'
      % (ymd, _zh[pred['dir']], pred.get('score_lo'), pred.get('score_hi'), pct, actual_dir,
         ascore, '命中' if dir_hit else '未中',
         '命中' if score_hit else ('未设区间' if score_hit is None else '未中')))
    return result

def pred_stats(days=5, all_=False, by_dir=False):
    """周报命中率小节: 窗口以情绪档案交易日对齐; 分母=已对照数。"""
    preds = _pred_load()
    fp = os.path.join(DATA_DIR, 'sentiment_history.jsonl')
    hist_dates = sorted(str(r.get('date')) for r in
                        [json.loads(l) for l in open(fp, encoding='utf-8')] if True) \
        if os.path.exists(fp) else []
    window = hist_dates[-days:] if not all_ else hist_dates
    latest = {}
    for p in preds:  # 每交易日取最新一条预判
        d = p.get('date')
        if d not in latest or p.get('created_at', '') > latest[d].get('created_at', ''):
            latest[d] = p
    n_pred = n_checked = n_dir_hit = n_score_hit = n_score_checked = 0
    no_pred_days, unchecked = [], []
    rows = []
    for d in window:
        p = latest.get(d)
        if not p:
            no_pred_days.append(d)
            continue
        r = p.get('result')
        if not r:
            unchecked.append(d)
            continue
        n_pred += 1
        n_checked += 1
        if r.get('dir_hit'):
            n_dir_hit += 1
        if r.get('score_hit') is not None:
            n_score_checked += 1
            if r['score_hit']:
                n_score_hit += 1
        rows.append((d, p.get('dir'), r.get('actual_dir'), r.get('dir_hit')))
    w('## 预判命中率(%s个交易日)' % ('全部%d' % len(window) if all_ else '近%d' % days))
    w('| 指标 | 值 |')
    w('|---|---|')
    w('| 交易日数(以情绪档案计) | %d |' % len(window))
    w('| 有预判天数 | %d |' % len([d for d in window if d in latest]))
    w('| 已对照 | %d |' % n_checked)
    w('| 方向命中 | %d/%d (%.0f%%) |' % (n_dir_hit, n_checked, n_dir_hit / max(n_checked, 1) * 100))
    w('| 分数命中 | %d/%d (%.0f%%, 有区间样本) |' % (n_score_hit, n_score_checked, n_score_hit / max(n_score_checked, 1) * 100))
    w('| 缺预判日 | %d %s |' % (len(no_pred_days), no_pred_days))
    w('| 漏对照 | %d %s |' % (len(unchecked), unchecked))
    if by_dir:
        for d0 in ('up', 'down', 'flat'):
            sub = [r for r in rows if r[1] == d0]
            if sub:
                hit = sum(1 for r in sub if r[3])
                w('- %s: %d/%d 命中 (n=%d)' % (d0, hit, len(sub), len(sub)))
    return dict(window=window, n_pred=n_pred, n_checked=n_checked,
                dir_hit=n_dir_hit, no_pred_days=no_pred_days)

# ---------- 6. 快讯 ----------
def news(num=12):
    w('\n===== [6] 财经快讯(东财7x24) =====')
    rows = []
    try:
        u = ('https://np-listapi.eastmoney.com/comm/web/getNewsByColumns?client=web&biz=web_724&column=350'
             f'&order=1&needInteractData=0&page_index=1&page_size={num}&req_trace={dt.datetime.now():%Y%m%d%H%M%S%f[:-3]}')
        try:
            rows = [(it.get('showTime', '')[:16],
                     ','.join(c.get('name', '') for c in (it.get('codes') or [])),
                     it.get('title', '')) for it in json.loads(http(u, retries=2))['data']['list']]
        except Exception:
            w('(东财column失败, 切fastNewsList)')
            try:
                u1 = ('https://np-listapi.eastmoney.com/comm/web/getFastNewsList?client=web&biz=web_724'
                      f'&fastColumn=102&sortEnd=&pageSize={num}&req_trace={dt.datetime.now():%Y%m%d%H%M%S}')
                items = json.loads(http(u1, retries=2))['data']['fastNewsList']
                rows = [(x.get('showTime', '')[:16], '', x.get('title', '')) for x in items]
            except Exception:
                w('(东财快讯失败, 切换新浪7x24)')
                u2 = 'https://zhibo.sina.com.cn/api/zhibo/feed?page=1&page_size=%d&zhibo_id=152&tag_id=0' % num
                rows = [(x.get('create_time', '')[:16], '', (x.get('rich_text') or '')[:60])
                        for x in json.loads(http(u2, retries=2))['result']['data']['feed']['list']]
        for _tm, _cd, _ti in rows:
            w(f'{_tm}  {_cd}  {_ti}')
        return [dict(time=t, codes=c, title=i) for t, c, i in rows]
    except Exception as e:
        w(f'[快讯失败] {e}')
        return []

# ---------- 7. 个股体检 ----------
_KLINE_MEM_CACHE = {}
_KLINE_CACHE_TTL = 60.0          # 交易时段：60 秒
_KLINE_CACHE_TTL_CLOSED = 1800.0 # 休市时段：30 分钟（历史日K不会变）
_KLINE_NEG_TTL = 20.0            # 空/失败结果的负缓存：20 秒（避免级联重试雪崩）

def _is_market_closed_now():
    """当前是否处于休市状态（收盘后/午休/盘前/周末）。

    日K在休市期间不会变化，可显著拉长缓存 TTL，避免反复请求同一份数据。
    """
    now = dt.datetime.now()
    if now.weekday() >= 5:
        return True
    m = now.hour * 60 + now.minute
    return m < 9 * 60 + 15 or m > 15 * 60 + 5 or (11 * 60 + 30 <= m < 13 * 60)


def kline_tx(full_code, days=160):
    """日K线数据获取：新浪 → 腾讯 → 东财 → mootdx/baostock 四重高可用容灾 + 内存缓存

    修复 (2026-10-18):
      1) 原来固定 TTL=60s，盘后/周末也每 60 秒重拉一次完全不变的历史日K，
         白白消耗上游配额。现在休市期 TTL 拉长到 30 分钟。
      2) 失败/空结果不写缓存，下次调用会重跑整条四源级联（最坏 4 次网络往返）。
         现在空结果写 20 秒短负缓存，避免雪崩式重试。
      3) 去掉多余的 `global`（本函数只读字典、不重新赋值）。
    """
    cache_key = (str(full_code).lower(), int(days))
    now = time.time()
    if cache_key in _KLINE_MEM_CACHE:
        ts, val = _KLINE_MEM_CACHE[cache_key]
        ttl = _KLINE_CACHE_TTL_CLOSED if _is_market_closed_now() else _KLINE_CACHE_TTL
        # 空结果用短 TTL，真实数据用正常 TTL
        eff_ttl = ttl if val else _KLINE_NEG_TTL
        if now - ts < eff_ttl:
            return val

    # 委托统一数据层 (data_layer: TDX 40ms 极速 -> Baostock 前复权 -> 腾讯 HTTP 容灾)
    try:
        import data_layer
        kl = data_layer.kline(full_code, days)
        if kl and len(kl) >= 1:
            _KLINE_MEM_CACHE[cache_key] = (now, kl)
            return kl
    except Exception:
        pass

    # 四源全部失败：写一份空结果的负缓存（短 TTL），避免短时间内反复重跑
    # 整条四源级联造成上游雪崩。20 秒后自动重试。
    _KLINE_MEM_CACHE[cache_key] = (now, [])
    return []

def stock_checkup(code, days=160):
    full = ('sh' + code) if code.startswith(('6', '5', '9')) else ('sz' + code)
    w(f'\n===== 个股体检: {code} =====')
    q = None; kl = None
    try:
        q = tx_realtime([full])[0]
        w(f"[行情] {q['name']} 价{q['price']} {q['chg']:+.2f}({q['pct']:+.2f}%) 高低{q['high']}/{q['low']} 额{q['amount']}")
    except Exception as e:
        w(f'[行情失败] {e}')
    try:
        kl = kline_tx(full, days)
        # 加固: 四源全失败时 kline_tx 返回 []，直接 closes[-1] 会抛 IndexError，
        # 上层只看到"K线失败: list index out of range"，无法判断是数据源挂了。
        if not kl:
            raise ValueError('日K数据获取失败（四源均无结果）')
        closes = [r[2] for r in kl]; last = closes[-1]
        ma = lambda k: sum(closes[-k:]) / k
        w(f"[趋势] 收{last:.2f} | MA5 {ma(5):.2f} MA10 {ma(10):.2f} MA20 {ma(20):.2f} MA60 {ma(60):.2f}")
        hi = max(r[3] for r in kl[-120:]); lo = min(r[4] for r in kl[-120:])
        c20 = (last / closes[-21] - 1) * 100 if len(closes) > 21 else float('nan')
        c60 = (last / closes[-61] - 1) * 100 if len(closes) > 61 else float('nan')
        w(f'[区间] 近120日高{hi:.2f}/低{lo:.2f} 距高点{(last/hi-1)*100:+.1f}% 近20日{c20:+.1f}% 近60日{c60:+.1f}%')
    except Exception as e:
        w(f'[K线失败] {e}')
    if kl:
        try:
            chan_analysis(kl, code)
        except Exception as e:
            w(f'[缠论失败] {type(e).__name__}: {e}')
    try:
        import akshare as ak
        df = ak.stock_individual_fund_flow(stock=code, market='sh' if full.startswith('sh') else 'sz').tail(5)
        w('[近5日主力净流入]')
        for _, r in df.iterrows():
            w(f"  {str(r['日期'])[:10]} 主力{float(r['主力净流入-净额'])/1e8:+.2f}亿 占比{float(r['主力净流入-净占比']):+.1f}%")
    except Exception as e:
        w(f'[个股资金失败(akshare)] {e}')
    try:
        u = ('https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPTA_WEB_RZRQ_GGMX&columns=DATE,RZYE,RZMRE'
             f'&filter=(scode%3D%22{code}%22)&sortColumns=date&sortTypes=-1&pageSize=5&pageNumber=1')
        w('[近5日融资余额]')
        prev = None
        for r in json.loads(http(u))['result']['data']:
            d = str(r['DATE'])[5:10]; ye = float(r['RZYE']) / 1e8
            delta = f'({ye-prev:+.2f})' if prev else ''
            w(f'  {d}: {ye:.2f}亿 {delta}'); prev = ye
    except Exception as e:
        w(f'[融资失败] {e}')
    try:
        u = f'https://np-anotice-stock.eastmoney.com/api/security/ann?sr=-1&page_size=8&page_index=1&ann_type=A&stock_list={code}'
        w('[近期公告]')
        for a in json.loads(http(u))['data']['list']:
            w(f"  {a['notice_date'][:10]}  {a['title']}")
    except Exception as e:
        w(f'[公告失败] {e}')
    try:
        prof = lhb_profile(code)
        if isinstance(prof, str):
            w(prof)
    except Exception as e:
        w(f'[席位画像失败] {type(e).__name__}: {e}')
    return q, kl

# ---------- 8. K线图 ----------
def draw_chart(code, kl, name=''):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
    plt.rcParams['axes.unicode_minus'] = False
    rows = kl[-60:]
    fig, (ax, av) = plt.subplots(2, 1, figsize=(11, 6), sharex=True,
                                 gridspec_kw={'height_ratios': [3, 1]})
    for i, (d, o, c, h, l, v) in enumerate(rows):
        up = c >= o
        color = '#e03131' if up else '#2f9e44'
        ax.vlines(i, l, h, color=color, lw=1)
        ax.bar(i, abs(c - o) or 0.01, bottom=min(o, c), width=0.6, color=color)
        av.bar(i, v, width=0.6, color=color, alpha=.7)
    closes = [r[2] for r in rows]
    for k, cc in [(5, '#f59f00'), (10, '#1c7ed6'), (20, '#9c36b5'), (60, '#495057')]:
        ma = [sum(closes[:i+1][-k:]) / min(i+1, k) for i in range(len(closes))]
        ax.plot(range(len(rows)), ma, lw=1.2, label=f'MA{k}', color=cc)
    ax.legend(loc='upper left', fontsize=8, ncol=4, frameon=False)
    ax.set_title(f"{name or code}({code}) 近60个交易日", fontsize=13)
    ticks = list(range(0, len(rows), 10))
    av.set_xticks(ticks); av.set_xticklabels([rows[i][0][5:] for i in ticks], fontsize=8)
    av.set_ylabel('成交量', fontsize=9)
    for a in (ax, av):
        a.spines[['top', 'right']].set_visible(False); a.grid(alpha=.25)
    path = os.path.join(CHART_DIR, f"{code}_{dt.date.today():%Y%m%d}.png")
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)
    w(f'[图表] 已生成 -> {path}')
    return path

# ---------- 8. 选股器(screener) ----------
ALL_FS = 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23'

def _num(v):
    return v if isinstance(v, (int, float)) else 0

def _all_pages(fid, pages=3):
    rows = []
    for pn in range(1, max(1, pages) + 1):
        u = [_h + '/api/qt/clist/get?pn=%d&pz=100&po=1&np=1&fltt=2&fid=%s&fs=%s&fields=f12,f14,f2,f3,f5,f6,f8,f10,f21,f62,f100' % (pn, fid, ALL_FS)
             for _h in ['https://push2delay.eastmoney.com', 'https://push2.eastmoney.com']]
        j = json.loads(_get_first_ok(u, retries=2))
        d = j.get('data') or {}
        diff = d.get('diff') or []
        rows += diff
        if len(diff) < 100 or len(rows) >= int(d.get('total') or 0):
            break
    return rows

def _scr_leader():
    ymd = dt.date.today().strftime('%Y%m%d')
    zt = _pool('ZT', ymd)
    if not zt:  # 盘前/休市回溯
        base = dt.date.today()
        for i in range(1, 8):
            zt = _pool('ZT', (base - dt.timedelta(days=i)).strftime('%Y%m%d'))
            if zt:
                break
    if not zt:
        w('(无涨停池数据)')
        return
    scored = []
    for x in zt:
        q = 0.40 * min(x.get('lbc', 1) / 5, 1)
        try:
            fbt = str(int(x.get('fbt', 0))).zfill(6)
        except Exception:
            fbt = ''
        q += 0.25 if fbt <= '100000' else (0.12 if fbt <= '140000' else 0)
        ltsz = _num(x.get('ltsz'))
        q += 0.15 if 2e9 <= ltsz <= 1.5e10 else 0
        q += 0.10 * min(_num(x.get('fund')) / max(ltsz, 1), 0.05) / 0.05
        q += 0.10 * min(_num(x.get('amount')) / 5e8, 1)
        scored.append((q, x, fbt))
    scored.sort(key=lambda t: -t[0])
    for q, x, fbt in scored[:10]:
        fund = _num(x.get('fund')) / 1e8
        ltsz = _num(x.get('ltsz')) / 1e8
        rt = _num(x.get('fund')) / max(_num(x.get('ltsz')), 1) * 100
        w("%s %-6s [%s] %d板 封单%.1f亿(占流通%.1f%%) 首封%s 炸板%d次 额%.1f亿 | 质量分%.2f" % (
            x.get('c', '?'), x.get('n', '?'), x.get('hybk', '-'), x.get('lbc', 1),
            fund, rt, (fbt[0:2] + ':' + fbt[2:4]) if fbt else '-', x.get('zbc', 0),
            _num(x.get('amount')) / 1e8, q))

def _scr_fund():
    rows = _all_pages('f62', 3)
    out = []
    for r in rows:
        f62, f21 = _num(r.get('f62')), _num(r.get('f21'))
        if not f62 or not f21:
            continue
        ratio = f62 / f21 * 100
        if f62 >= 3e7 and ratio >= 2 and _num(r.get('f6')) >= 3e8:
            out.append((ratio, r))
    out.sort(key=lambda t: -t[0])
    for ratio, r in out[:10]:
        pct = r.get('f3')
        pcts = '%+.2f%%' % pct if isinstance(pct, (int, float)) else str(pct)
        w("%s %-6s %s 主力净入%+.2f亿 占流通%.1f%% 额%.1f亿 [%s]" % (
            r.get('f12'), r.get('f14'), pcts, _num(r.get('f62')) / 1e8,
            ratio, _num(r.get('f6')) / 1e8, r.get('f100', '-')))

def _scr_volume():
    rows = _all_pages('f10', 3)
    out = []
    for r in rows:
        lb, turn = _num(r.get('f10')), _num(r.get('f8'))
        if lb >= 3 and 0 < turn <= 25 and _num(r.get('f6')) >= 1e8:
            out.append((lb, r))
    out.sort(key=lambda t: -t[0])
    for lb, r in out[:12]:
        pct = r.get('f3')
        pcts = '%+.2f%%' % pct if isinstance(pct, (int, float)) else str(pct)
        w("%s %-6s %s 量比%.1f 换手%.1f%% 额%.1f亿 流通%.0f亿 [%s]" % (
            r.get('f12'), r.get('f14'), pcts, lb, _num(r.get('f8')),
            _num(r.get('f6')) / 1e8, _num(r.get('f21')) / 1e8, r.get('f100', '-')))

def _scr_lhb():
    got = False
    base = dt.date.today()
    for i in range(0, 8):
        d = base - dt.timedelta(days=i)
        if d.weekday() >= 5:
            continue
        u = ('https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_DAILYBILLBOARD_DETAILSNEW'
             '&columns=ALL&filter=(TRADE_DATE%3D%27' + d.strftime('%Y-%m-%d') + '%27)'
             '&sortColumns=BILLBOARD_NET_AMT&sortTypes=-1&pageSize=10&pageNumber=1')
        rows = (json.loads(http(u)).get('result') or {}).get('data') or []
        if rows:
            got = True
            break
    if not got:
        w('(近8日无龙虎榜数据)')
        return
    for r in rows:
        w("%s %-6s %+05.2f%% 净买%+.2f亿 买入%.2f亿 [%s] %s" % (
            r.get('SECURITY_CODE', '?'), r.get('SECURITY_NAME_ABBR', '?'),
            _num(r.get('CHANGE_RATE')), _num(r.get('BILLBOARD_NET_AMT')) / 1e8,
            _num(r.get('BILLBOARD_BUY_AMT')) / 1e8,
            str(r.get('EXPLAIN', '') or '')[:26],
            str(r.get('EXPLANATION', '') or '')[:30]))

_SCR_FN = {'leader': ('策略A 龙头梯队(涨停池质量TOP10)', _scr_leader),
           'fund': ('策略B 主力介入(净流入占流通比TOP10)', _scr_fund),
           'volume': ('策略C 异动放量(量比TOP·温和换手)', _scr_volume),
           'lhb': ('策略D 龙虎榜资金(净买额TOP10)', _scr_lhb)}

def screener(mode='all'):
    todo = list(_SCR_FN) if mode == 'all' else [mode]
    for m in todo:
        if m not in _SCR_FN:
            w(f'(未知策略 {m}, 可选: all/{"/".join(_SCR_FN)})')
            continue
        title, fn = _SCR_FN[m]
        w('\n===== [选股·%s] =====' % title)
        try:
            fn()
        except Exception as e:
            w(f'[策略{m}失败] {type(e).__name__}: {e}')


# ---------- 9. 缠论简化引擎(日线级别) ----------
# ---------- 9. 缠论简化引擎 (迁移至 core.chan，保持外观兼容) ----------
# 已在文件头部从 core.chan 统一导入:
# _ema, chan_analysis_structured

def chan_analysis(kl, code=''):
    """终端文字版缠论输出，兼容已有命令行接口"""
    res = chan_analysis_structured(kl, code)
    if res['status'] == 'error':
        w(f"[缠论] {res['msg']}")
        return res
    if res['status'] == 'warning':
        w(f"[缠论] {res['msg']}")
        return res
    w(f"[缠论] 最近笔序列: {res['trail']} | 当前处于{res['cur_dir']}的一笔(日线)")
    zs = res.get('last_zhongshu')
    if zs:
        hint_s = ''
        if zs['pos'] == '上方' and res['cur_dir'] == '向上':
            hint_s = ' (三买候选: 回抽不回中枢可关注)'
        elif zs['pos'] == '下方' and res['cur_dir'] == '向下':
            hint_s = ' (三卖形态: 反弹不进中枢需谨慎)'
        w(f"[缠论] 中枢[{zs['lo']:.2f} ~ {zs['hi']:.2f}] 现价位于中枢{zs['pos']}{hint_s}")
    w(f"[缠论] 背驰检测: {res['divergence']}")
    w('[缠论] 注: 简化算法(未递归区间套), 日线级别参考, 不构成买卖依据')
    return res

# ---------- 10. 情绪周期定位(92科比五阶段框架) ----------
_CYCLE_ADV = {
    '冰点': '空仓观望只跟踪; 盯首只逆势换手4板(新周期种子), 冰点次日的首阳反抽可轻仓试错',
    '退潮': '总仓位压到2成以下, 不打板不接力不半路; 高位股集体补跌=出清信号, 等跌停清零+炸板率降到20%%以内再回来',
    '修复/震荡': '轻仓试错新题材首板和超跌反转龙, 快进快出严格止损, 不恋战',
    '主升': '主线内持股为主, 龙头分批追, 梯队中军和补涨龙轮动做; 龙头首次断板减半仓',
    '亢奋': '只卖不买兑现浮盈, 一致性加速日警惕放量见顶大阴线; 空仓等下一轮冰点'}

_STAGE_ORDER = ['冰点', '修复', '主升', '亢奋', '退潮']   # 阶段环, 与 _CYCLE_ADV 轮转一致

def _stage_dist(a, b):
    """五阶段环上两阶段的最短距离(1=相邻 2=隔一级)"""
    i, j = _STAGE_ORDER.index(a), _STAGE_ORDER.index(b)
    d = abs(i - j)
    return min(d, len(_STAGE_ORDER) - d)

def _cycle_stage(recs, prev_stage):
    """规则引擎 + 迁移校验(dsh方案B)。返回 (stage, meta)。recs 已按 date 升序。
    判定顺序: 亢奋→冰点→[退潮短路★]→退潮→主升→修复/震荡;
    短路 sc<45 and dt>=3 补掉"高位急杀首日均线未死叉"的漏判窗口。"""
    n = len(recs)
    s_ = [float(r.get('score', 50)) for r in recs]
    lbs = [int(r.get('max_lb', 0)) for r in recs]
    zts = [float(r.get('zt', 0)) for r in recs]
    dts_ = [float(r.get('dt', 0)) for r in recs]
    sc = s_[-1]
    ma3 = sum(s_[-3:]) / min(3, n)
    ma7 = sum(s_[-7:]) / min(7, n)
    zt_ma5 = sum(zts[-5:]) / min(5, n)
    peak_lb = max(lbs[-10:])
    if sc >= 85:
        raw = '亢奋'
    elif sc < 30 or (zts[-1] <= 15 and lbs[-1] <= 2):
        raw = '冰点'
    elif sc < 45 and dts_[-1] >= 3:          # ★ 退潮短路: 弱情绪+真实跌停≥3家
        raw = '退潮'
    elif ma3 < ma7 and (lbs[-1] <= peak_lb - 2 or zts[-1] < zt_ma5 * 0.7 or sc < 45):
        raw = '退潮'
    elif ma3 >= ma7 and (lbs[-1] >= 4 or zt_ma5 >= 55):
        raw = '主升'
    else:
        raw = '修复/震荡'
    # 迁移校验: 五阶段环上任意两点最短距离≤2, 无禁止迁移; 隔一级降置信
    if not prev_stage:
        return raw, dict(trans='coldstart', conf=0, raw=raw)
    if raw == prev_stage:
        return raw, dict(trans='stay', conf=3, raw=raw)
    if _stage_dist(raw, prev_stage) == 1:
        return raw, dict(trans='adjacent', conf=2, raw=raw)
    return raw, dict(trans='skip', conf=1, raw=raw)

def _atomic_rewrite(fp, recs):
    tmp = fp + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    os.replace(tmp, fp)


def _hist_upsert(fp, rec):
    """按 date 幂等写入情绪存档（同日期覆盖 + 原子重写），不再裸追加。

    为什么必须这样写：旧实现是「先 any(date) 判断、再 open('a') 追加」，
    两个进程（web 服务 / CLI / 盘后流水线）同时判断「今天还没记录」就会各写一行。
    20261022 已实际出现重复（stage_meta 一条 adjacent/conf2、一条 stay/conf3），
    后果是 MA3/MA7 把那一天算两遍、cycle_position 的样本数虚高。
    规则同「打脸账本必须 upsert」：任何按日累计的账本都不能靠追加维护。
    """
    recs = []
    if os.path.exists(fp):
        with open(fp, encoding='utf-8') as f:
            recs = [json.loads(l) for l in f if l.strip()]
    # 同日期只留一条（后写覆盖先写），顺带把历史上已存在的重复行清掉
    recs = [r for r in recs if r.get('date') != rec.get('date')]
    recs.append(rec)
    recs.sort(key=lambda r: str(r.get('date', '')))
    _atomic_rewrite(fp, recs)
    return recs

def cycle_position():
    fp = os.path.join(DATA_DIR, 'sentiment_history.jsonl')
    recs = []
    if os.path.exists(fp):
        recs = [json.loads(l) for l in open(fp, encoding='utf-8') if l.strip()]
    if not recs:
        w('(情绪存档为空, 无法定位周期)')
        return
    recs.sort(key=lambda r: str(r.get('date', '')))
    # 先验 stage = 从末条向前扫最近一条带 stage 的记录。
    # 不能用 recs[-1].get('stage'): 当日收盘 emotion 刚 append 的新记录还没有 stage,
    # 直接取会每天都被当成冷启动, 迁移矩阵永不生效。(dsh方案B关键设计点)
    prev = None
    for r in reversed(recs):
        if r.get('stage'):
            prev = r['stage']
            break
    # algo 尺度隔离: v2 与 v1 的分数不可混算 MA3/MA7(2026-09-30 起)
    _cur_algo = recs[-1].get('algo', 'v1')
    recs_same = [r for r in recs if r.get('algo', 'v1') == _cur_algo]
    if len(recs_same) < len(recs):
        w('(注: 存档含 %d 条旧尺度(v1)记录, 本次定位只用同尺度 %d 条)' % (
            len(recs) - len(recs_same), len(recs_same)))
    stage, meta = _cycle_stage(recs_same, prev)
    if recs[-1].get('date') and not recs[-1].get('stage'):
        pass  # 新记录首次定位
    if recs[-1].get('stage') != stage or recs[-1].get('stage_meta') != meta:
        recs[-1]['stage'] = stage
        recs[-1]['stage_meta'] = meta
        _atomic_rewrite(fp, recs)
        w('(stage 已写档: %s trans=%s conf=%s)' % (stage, meta['trans'], meta['conf']))
    n = len(recs_same)
    s_ = [float(r.get('score', 50)) for r in recs_same]
    lbs = [int(r.get('max_lb', 0)) for r in recs_same]
    zts = [float(r.get('zt', 0)) for r in recs_same]
    sc = s_[-1]
    ma3 = sum(s_[-3:]) / min(3, n)
    ma7 = sum(s_[-7:]) / min(7, n)
    zt_ma5 = sum(zts[-5:]) / min(5, n)
    peak_lb = max(lbs[-10:])
    trans_zh = {'stay': '保持(%s→%s)', 'adjacent': '相邻(%s→%s)',
                'skip': '越级·隔一级(%s→%s, 待下一日确认)', 'coldstart': '冷启动·无先验(规则直判=%s)'}
    _mv = trans_zh[meta['trans']]
    w('')
    w('===== [情绪周期定位·92科比框架] =====')
    for r in recs_same[-10:]:
        w('  %s 情绪%.0f[%s] 涨停%-3s 跌停%-2s 高度%s板' % (
            r.get('date'), float(r.get('score', 0)), r.get('band', ''),
            r.get('zt'), r.get('dt'), r.get('max_lb')))
    w('>> 定位: 【%s】 情绪%.0f | MA3=%.1f MA7=%.1f | 高度%s板(10日峰%s板) | 5日均涨停%.0f家%s' % (
        stage, sc, ma3, ma7, lbs[-1], peak_lb, zt_ma5,
        '' if n >= 8 else ' (存档仅%d条, 定位置信度低, 积累两周后可靠)' % n))
    w('>> 迁移: ' + (_mv % (prev, stage) if '%s' in _mv and prev else _mv % stage if '%s' in _mv else _mv))
    w('>> 操作参考: ' + (_CYCLE_ADV.get(stage, '') .replace('%%', '%')))
    w('>> 阶段轮转: 冰点->修复->主升->亢奋->退潮->冰点 (循环; 每阶段先确认再做)')
    return stage


# ---------- 11. 参与者画像与多主体推演(MiroFish思路本土化) ----------
_LHB_FIXED = [('机构', ('机构专用',)), ('北向', ('沪股通', '深股通')), ('量化', ('量化',))]
_YZ_KW = ('知春路', '中关村大街', '西大街', '上塘路', '桑田路', '绍兴', '华鑫上海分公司',
          '方新侠', '劳动东路', '芙蓉西路', '益田路', '荣超商务中心', '太平南路',
          '解放北路', '湖里大道', '江东北路', '金融城', '深南大道')

def _seat_class(name):
    for tag, kws in _LHB_FIXED:
        if any(k in name for k in kws):
            return tag
    if any(k in name for k in _YZ_KW):
        return '知名游资'
    return '营业部通道'

_LHB_CACHE = {}   # {(code, day, flag): rows} —— 龙虎榜是收盘后静态数据，可长期缓存

def _lhb_detail(code, day, flag):
    import urllib.parse
    ck = (code, day, flag)
    if ck in _LHB_CACHE:
        return _LHB_CACHE[ck]
    pr = {'reportName': 'RPT_BILLBOARD_DAILYDETAILSBUY' if flag == 'B' else 'RPT_BILLBOARD_DAILYDETAILSSELL',
          'columns': 'ALL', 'filter': "(TRADE_DATE='%s')(SECURITY_CODE=\"%s\")" % (day, code),
          'pageNumber': '1', 'pageSize': '500', 'sortTypes': '-1',
          'sortColumns': 'BUY' if flag == 'B' else 'SELL', 'source': 'WEB', 'client': 'WEB'}
    # 修复 (2026-10-18): 原用默认 timeout(曾为20s)/retries(3)，叠加 lhb_profile
    # 的 9天×(买+卖) 最多 18 次串行请求，最坏可卡 2 分钟以上。龙虎榜接口很轻，
    # 收敛到 5s/1 次重试；结果按 (代码,日期,方向) 缓存，历史数据不会变。
    j = json.loads(http('https://datacenter-web.eastmoney.com/api/data/v1/get?' + urllib.parse.urlencode(pr),
                        timeout=5, retries=1))
    rows = ((j.get('result') or {}).get('data')) or []
    _LHB_CACHE[ck] = rows
    return rows

def lhb_profile(code):
    """个股席位画像：回溯最近 9 天找该股上榜日。

    修复 (2026-10-18): 原实现每天都要先查"买"再查"卖"共 2 次请求，
    无上榜时 9 天 = 18 次串行网络请求。现在先只查"买"侧探测上榜日，
    命中后才补查"卖"侧，未上榜的天数请求量减半；配合 _lhb_detail 的缓存，
    同一只股票重复体检几乎零网络开销。
    """
    day, rb, rs = None, [], []
    for i in range(9):
        dd = dt.date.today() - dt.timedelta(days=i)
        if dd.weekday() >= 5:
            continue
        ds = dd.strftime('%Y-%m-%d')
        b = _lhb_detail(code, ds, 'B')
        s_ = _lhb_detail(code, ds, 'S')
        if b or s_:
            day, rb, rs = ds, b, s_
            break
    if not (rb or rs):
        return '(近两周无龙虎榜记录)'
    agg = {}
    for flag, rows in (('买', rb), ('卖', rs)):
        for x in rows:
            c = _seat_class(x.get('OPERATEDEPT_NAME') or '?')
            a = agg.setdefault(c, [0.0, 0.0])
            a[0 if flag == '买' else 1] += _num((x.get('BUY') if flag == '买' else x.get('SELL')) or 0) / 1e8
    out = ['[席位画像·%s]' % day]
    for c, (bsum, ssum) in sorted(agg.items(), key=lambda kv: -(kv[1][0] + kv[1][1])):
        out.append('  %-6s 买%.2f亿 卖%.2f亿 净%+.2f亿' % (c, bsum, ssum, bsum - ssum))
    inst_net = sum(b - sl for c, (b, sl) in agg.items() if c in ('机构', '北向'))
    yz_net = sum(b - sl for c, (b, sl) in agg.items() if c == '知名游资')
    if inst_net > 0.3:
        out.append('  >> 机构/北向净买, 中线资金介入迹象')
    elif inst_net < -0.3:
        out.append('  >> 机构/北向净卖, 筹码向短线资金转移')
    if yz_net > 0.3:
        out.append('  >> 知名游资主导买入, 情绪票属性强')
    return '\n'.join(out)


def strategic_decision(emo=None, sec=None, idxs=None):
    """战略战术决策中枢：基于毛选认识论与矛盾论体系的局势研判与兵力指令"""
    import strategic_decision as strat_dec
    return strat_dec.analyze_strategic_decision(emo=emo, sec=sec, idxs=idxs)


# ---------- main ----------
if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'market'
    try:
        if cmd == 'market':
            market_quotes()
            global_markets()
            emotion()
            cycle_position()
            # 盘前/盘中当日主力净流入(f62)必然全0, 自动切近5日口径; 收盘后(15:00+)用当日口径
            _hm = dt.datetime.now().hour * 60 + dt.datetime.now().minute
            sector_flow(days=5 if _hm < 15 * 60 else 1)
            margin_total()
            if '--no-news' not in sys.argv:
                news()
        elif cmd == 'stock':
            code = sys.argv[2]
            days = int(sys.argv[sys.argv.index('--days') + 1]) if '--days' in sys.argv else 160
            q, kl = stock_checkup(code, days)
            if kl and '--chart' in sys.argv:
                draw_chart(code, kl, q['name'] if q else '')
        elif cmd == 'pred':
            # 预判闭环: pred save|check|stats (dsh方案A)
            action = sys.argv[2] if len(sys.argv) > 2 else 'stats'
            def _arg(flag, dflt=None):
                return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else dflt
            if action == 'save':
                _d = (_arg('--dir') or '').strip()
                _d = {'多': 'up', '看多': 'up', '空': 'down', '看空': 'down',
                      '平': 'flat', '中性': 'flat', '震荡': 'flat'}.get(_d, _d)
                pred_save(date=_arg('--date'), dir=_d,
                          score_lo=float(_arg('--score-lo')) if _arg('--score-lo') else None,
                          score_hi=float(_arg('--score-hi')) if _arg('--score-hi') else None,
                          focus=_arg('--focus', ''), text=_arg('--text', ''),
                          model=_arg('--model', 'default'))
            elif action == 'check':
                pred_check(_arg('--date'))
            elif action == 'stats':
                pred_stats(days=int(_arg('--days', '5')),
                           all_='--all' in sys.argv, by_dir='--by-dir' in sys.argv)
            else:
                w('未知 pred 动作: %s (可用: save/check/stats)' % action)
        elif cmd == 'news':
            news(int(sys.argv[2]) if len(sys.argv) > 2 else 12)
        elif cmd == 'emotion':
            ymd = None
            if '--date' in sys.argv:
                ymd = sys.argv[sys.argv.index('--date') + 1].replace('-', '')
            emotion(ymd)
        elif cmd == 'screener':
            screener(sys.argv[2] if len(sys.argv) > 2 else 'all')
        elif cmd == 'cycle':
            cycle_position()
        elif cmd == 'chan':
            kl = kline_tx(sys.argv[2])
            chan_analysis(kl, sys.argv[2])
        elif cmd == 'auction':
            import auction_radar as ar
            res = ar.get_auction_radar()
            w('\n===== [9:25 集合竞价雷达 & 亏钱效应大面榜] =====')
            sm = res.get('premium_summary', {})
            if sm:
                w(f"昨日交易日: {sm.get('y_date')} | 昨涨停样本数: {sm.get('total_zt')}只")
                w(f"今日开盘平均溢价: {sm.get('avg_open_pct'):+.2f}% (高开率 {sm.get('open_positive_rate')}%) | 接力定调: 【{sm.get('sentiment_tag')}】")
                w(f"今日最新平均涨幅: {sm.get('avg_curr_pct'):+.2f}% (红盘率 {sm.get('curr_positive_rate')}%) | 连板晋级: {sm.get('promote_zt_count')}只 | 大面预警: {sm.get('mian_count')}只")
            w('\n-- ⚡ 弱转强异动标的 --')
            for it in res.get('weak_to_strong', [])[:6]:
                w(f"  {it['code']} {it['name']:<6} 现价{it['pct']:+5.2f}% | {it.get('reason','')}")
            w('\n-- ⚠️ 亏钱效应大面榜 (高点回撤) --')
            for it in res.get('big_loss', [])[:6]:
                w(f"  {it['code']} {it['name']:<6} 现价{it['pct']:+5.2f}% | 曾冲高{it['high_pct']:+5.2f}% | 日内回撤面值: {it['drop_from_high']:+5.2f}%")
        elif cmd in ('strategy', 'decision'):
            import strategic_decision as strat_dec
            res = strat_dec.analyze_strategic_decision()
            w(strat_dec.format_cli_output(res))
    except Exception as e:
        w(f'[FATAL] {type(e).__name__}: {e}')
        sys.exit(1)
    sys.exit(0)
