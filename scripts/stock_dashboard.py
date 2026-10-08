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
  python stock_dashboard.py agents [代码]   # 多主体推演(大盘或个股)
  python stock_dashboard.py sim [情景]      # 世界模拟v2(记忆+传染+情景注入)
"""
import sys, os, json, re, ssl, time, math, urllib.request, datetime as dt

try:
    from curl_cffi import requests as _creq
    # 默认禁用 curl_cffi，防止 Windows 系统下 HTTP/2 与 IPv6 ALPN 协商导致的 20 秒恶性超时卡顿
    _HAS_CURL = os.environ.get('STOCK_USE_CURL') == '1'
except Exception:
    _HAS_CURL = False

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
_cand = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
if os.path.isdir(_cand):
    _H = _cand
else:
    _H = os.environ.get('STOCK_DATA_HOME') or os.environ.get('HERMES_HOME') or os.path.expanduser('~/.hermes')
HERMES_HOME = _H
DATA_DIR = os.path.join(HERMES_HOME, 'stock_data')
CHART_DIR = os.path.join(DATA_DIR, 'charts')
os.makedirs(CHART_DIR, exist_ok=True)
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'}

def http(url, gbk=False, timeout=20, retries=3, referer=None, headers=None):
    import time
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
                    return raw.decode('gbk', 'replace') if gbk else raw.decode('utf-8', 'replace')
                except Exception:
                    pass  # curl 失败回退 urllib
            req = urllib.request.Request(url, headers=hh)
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                raw = r.read()
            return raw.decode('gbk', 'replace') if gbk else raw.decode('utf-8', 'replace')
        except Exception as e:
            last = e
            time.sleep(0.8 * (i + 1))
    raise last

# ---- host 级熔断: 进程内连续失败计数, 自动半开启恢复机制 ----
_HOST_FAIL = {}          # {host: 连续失败次数}
_HOST_BLACKOUT = {}      # {host: 冷却截止时间戳}
_CIRCUIT_N = int(os.environ.get('STOCK_HTTP_BREAK_N', '3'))
_CIRCUIT_COOLDOWN = 60.0 # 熔断后冷却 60 秒自动半开启重试

def _get_first_ok(urls, gbk=False, timeout=20, retries=2, referer=None, headers=None):
    """按序尝试 urls, 跳过处于冷却期内的 host; 某 host 连续失败 _CIRCUIT_N 次后冷却 60s。
    任一 host 成功即清零计数并解除熔断。"""
    import urllib.parse, time
    last = None
    now_ts = time.time()
    for u in urls:
        host = urllib.parse.urlsplit(u).netloc
        if host in _HOST_BLACKOUT and now_ts < _HOST_BLACKOUT[host]:
            continue
        try:
            txt = http(u, gbk=gbk, timeout=timeout, retries=retries, referer=referer, headers=headers)
            _HOST_FAIL[host] = 0
            _HOST_BLACKOUT.pop(host, None)
            return txt
        except Exception as e:
            last = e
            _HOST_FAIL[host] = _HOST_FAIL.get(host, 0) + 1
            if _HOST_FAIL[host] >= _CIRCUIT_N:
                _HOST_BLACKOUT[host] = now_ts + _CIRCUIT_COOLDOWN
                w('[熔断] %s 连续%d次失败, 暂时冷却60秒' % (host, _CIRCUIT_N))
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
            try:
                os.makedirs(os.path.dirname(_SECTOR_CACHE_FILE), exist_ok=True)
                json.dump(out, open(_SECTOR_CACHE_FILE, 'w', encoding='utf-8'), ensure_ascii=False)
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
                w(f'[新浪板块资金降级成功] 获取流入{len(out["inflow"])}只, 流出{len(out["outflow"])}只')
                try:
                    os.makedirs(os.path.dirname(_SECTOR_CACHE_FILE), exist_ok=True)
                    json.dump(out, open(_SECTOR_CACHE_FILE, 'w', encoding='utf-8'), ensure_ascii=False)
                except Exception:
                    pass
                return out
    except Exception as e2:
        w(f'[新浪板块资金降级失败] {e2}')

    # 通道 3: 本地快照缓存
    if os.path.exists(_SECTOR_CACHE_FILE):
        try:
            cached = json.load(open(_SECTOR_CACHE_FILE, encoding='utf-8'))
            if cached.get('inflow') or cached.get('outflow'):
                w('[板块资金使用本地缓存]')
                return cached
        except Exception:
            pass

    return out

# ---------- 4. 涨停池/情绪指数 ----------
UT = '7eea3edcaed734bea9cbfc24409ed989'
# ==================== 涨停质量分 (2026-09-30 P2) ====================
def _lu_num(v):
    return float(v) if isinstance(v, (int, float)) else 0.0


def _lu_time_score(fbt):
    """封板时间分 0~10(越早越强)。依据: 9:25 竞价封板 3 日超额 +5.7%, 10:00 后递减, 14:00 后 -2.4%"""
    if not fbt:
        return None
    if fbt <= 93000:
        return 10.0
    if fbt <= 100000:
        return 8.0
    if fbt <= 113000:
        return 5.0
    if fbt <= 140000:
        return 2.0
    return 0.0


def _lu_seal_score(ratio_pct):
    """封单强度分 0~10 = 封单额/流通市值。>5% -> 3日超额 +8.4%, 1~5% -> +3.1%, <1% -> -0.7%"""
    if ratio_pct is None:
        return None
    if ratio_pct >= 5:
        return 10.0
    if ratio_pct >= 1:
        return 7.0
    if ratio_pct >= 0.5:
        return 4.0
    if ratio_pct >= 0.1:
        return 2.0
    return 0.0


def _lu_board_score(lbc):
    """连板结构分 0~10。依据: 第 2 板 alpha 最强, 4 板后衰减, 6 板以上转负"""
    if not lbc:
        return None
    return {1: 4.0, 2: 10.0, 3: 6.0, 4: 2.0}.get(int(lbc), 0.0)


def limit_up_quality(d):
    """涨停质量分 0~10 = 0.35x封板时间 + 0.35x封单强度 + 0.30x连板结构, 缺项按权重归一, 烂板扣分。

    只用池子里现成的字段(fbt/fund/ltsz/lbc/zbc), 不额外发请求。
    依据: 涨停板因子实证(竞价封板 +5.7% / 封单占流通>5% +8.4% / 第 2 板 alpha 最强)。
    E/F/H 策略用它当首要排序键, 并通过 x['qlty'] 把分数带给 CLI 与 Web。
    返回 (score, detail)。
    """
    try:
        fbt = int(d.get('fbt') or 0)
    except Exception:
        fbt = 0
    try:
        lbc = int(d.get('lbc') or 0)
    except Exception:
        lbc = 0
    try:
        zbc = int(d.get('zbc') or 0)
    except Exception:
        zbc = 0
    ltsz = _lu_num(d.get('ltsz'))
    ratio = (_lu_num(d.get('fund')) / ltsz * 100) if ltsz > 0 else None

    parts = []
    tv, sv, bv = _lu_time_score(fbt), _lu_seal_score(ratio), _lu_board_score(lbc)
    if tv is not None:
        parts.append((tv, 0.35, 'time'))
    if sv is not None:
        parts.append((sv, 0.35, 'seal'))
    if bv is not None:
        parts.append((bv, 0.30, 'board'))
    if not parts:
        return 0.0, {'score': 0.0, 'missing': True, 'used_factors': 0}
    wsum = sum(p[1] for p in parts)
    score = sum(p[0] * p[1] for p in parts) / wsum
    if zbc >= 3:
        score -= 1.5
    elif zbc == 2:
        score -= 0.7
    score = max(0.0, min(10.0, round(score, 2)))
    return score, {
        'score': score, 'fbt': fbt, 'lbc': lbc, 'zbc': zbc,
        'seal_ratio_pct': round(ratio, 2) if ratio is not None else None,
        'parts': {p[2]: p[0] for p in parts},
        'used_factors': len(parts), 'missing': len(parts) < 3,
    }


def _pool(kind, ymd):
    # 注意: DT池必须用 fund 排序 —— fbt(首次封板时间)字段跌停股没有, 会恒返回空pool
    # (2026-08-25 三方会诊实证: 曾误判"跌停池无历史数据", 实为 sort 参数假象)
    sort = 'fund%3Aasc' if kind == 'DT' else 'fbt%3Aasc'
    u = f'https://push2ex.eastmoney.com/getTopic{kind}Pool?ut={UT}&dpt=wz.ztzt&Pageindex=0&pagesize=500&sort={sort}&date={ymd}'
    j = json.loads(http(u))
    if not isinstance(j, dict) or not j.get('data'):
        # ut token 失效时东财返回的是 rc!=0 / 无 data 字段的响应体; 旧代码会把它当成
        # "该日无涨停池"静默吞掉 —— 7 日回溯白跑、情绪分凭空少一块(2026-09-30 修正)。
        print('[涨停池·警告] %s %s 响应里没有 data 字段 —— 疑似 ut token 失效(当前 UT=%s); '
              '请从东方财富行情页-涨停池的网络请求里重新抓 ut 并更新 UT 常量' % (kind, ymd, UT))
        return []
    d = j.get('data') or {}
    return (d.get('pool') or [])

# ---------- 情绪指数打分: v1(对照留档) / v2(去饱和+赚钱效应) ----------
def _emotion_band(s):
    return ('冰点' if s < 30 else '退潮/偏冷' if s < 50 else '中性' if s < 70 else '活跃' if s < 85 else '亢奋')

def _emotion_score_v1(n_zt, n_zb, n_dt, max_lb):
    """旧公式(0-100): 基准10 + 广度30 + 高度25 + 封板质量20 - 跌停惩罚15。仅作对照留档。"""
    s = 10
    s += min(n_zt / 80, 1) * 30
    s += min(max_lb / 8, 1) * 25
    s += (1 - n_zb / (n_zt + n_zb)) * 20 if (n_zt + n_zb) else 10
    s -= min(n_dt / 15, 1) * 15
    return max(0, min(100, s))

def _emotion_score_v2(n_zt, n_zb, n_dt, max_lb, eff):
    """新公式(0-100): 基准10 + 广度18(平方根去饱和) + 高度17(平方根) + 封板质量12
    + 赚钱效应25 + 跌停惩罚15。
    赚钱效应 = 0.6*溢价分 + 0.4*晋级分; 溢价分 = clamp(昨日涨停今均涨跌, -5%, +5%) 归一化;
    晋级分 = min(1进2晋级率/50, 1)。取不到该指标时按中性 12.5 分计入(并标注).
    返回 (score, diverge)。diverge: score_high_effect_weak / score_low_effect_strong / None
    """
    s = 10
    s += math.sqrt(min(n_zt / 120, 1)) * 18
    s += math.sqrt(min(max_lb / 8, 1)) * 17
    s += ((1 - n_zb / (n_zt + n_zb)) * 12 if (n_zt + n_zb) else 6)
    s += (eff['score'] * 25) if eff.get('available') else 12.5
    s -= min(n_dt / 15, 1) * 15
    s = max(0, min(100, s))
    diverge = None
    if eff.get('available'):
        prem = float(eff.get('premium', 0.0))
        rate = float(eff.get('rate_1to2', 0.0))
        if s >= 50 and (prem < 0 or rate < 25):
            diverge = 'score_high_effect_weak'
        elif s < 50 and prem > 3 and rate > 50:
            diverge = 'score_low_effect_strong'
    return s, diverge

def _effect_flat(eff):
    """存档用扁平化(不写嵌套, 便于日后回测)"""
    if not eff.get('available'):
        return None
    return dict(premium=eff.get('premium'), rate_1to2=eff.get('rate_1to2'),
                effect_score=round(eff.get('score', 0) * 25, 2),
                y_date=eff.get('y_date'), tag=eff.get('tag'))

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
        if r.get('status') == 'ok' and prem is not None and rate is not None:
            prem_c = max(-5.0, min(5.0, float(prem)))
            prem_n = (prem_c + 5.0) / 10.0
            rate_n = min(float(rate) / 50.0, 1.0)
            out = {'available': True, 'premium': round(float(prem), 2),
                   'premium_clamped': round(prem_c, 2), 'rate_1to2': round(float(rate), 1),
                   'premium_norm': round(prem_n, 3), 'rate_norm': round(rate_n, 3),
                   'score': round(0.6 * prem_n + 0.4 * rate_n, 4),
                   'y_date': ps.get('y_date'), 'tag': ps.get('sentiment_tag')}
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


def emotion(ymd=None):
    w('\n===== [4] 市场情绪(涨停池实测) =====')
    if not ymd:
        ymd = dt.date.today().strftime('%Y%m%d')
    req_ymd = ymd
    try:
        # 两段式回溯(dsh方案D): 先用 ZT 池单请求探测哪天有数, 命中后再补拉 ZB/DT
        # —— 最坏情形从 7日x3池=21次请求 降为 探测N次+命中日2次; 且与 backfill 的
        # "ZT池有数=该日为有效交易日"判定规则统一
        def _probe(day):
            return _pool('ZT', day)
        hit_day = ymd
        zt = _probe(ymd)
        if not zt:  # 盘前/休市: 自动回溯最近有数据的交易日
            base = dt.datetime.strptime(ymd, '%Y%m%d').date()
            for i in range(1, 8):
                prev = (base - dt.timedelta(days=i)).strftime('%Y%m%d')
                zt = _probe(prev)
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
            w('赚钱效应: 昨日涨停今均溢价 %+.2f%% | 1进2晋级率 %.1f%% | 昨日=%s [%s]' % (
                eff['premium'], eff['rate_1to2'], eff.get('y_date') or '', eff.get('tag') or ''))
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
        def _strength_key(d):
            # 强弱排序: 连板数降序 > 封板时间升序 > 炸板升序 > 封单降序
            return (-d.get('lbc', 1), d.get('fbt', 999999), d.get('zbc', 0), -d.get('fund', 0))
        def _classify(stocks):
            if not stocks:
                return [], [], [], None
            sorted_s = sorted(stocks, key=_strength_key)
            max_lb = max(s.get('lbc', 1) for s in sorted_s)
            # 龙头: 连板最高的1-2只（如果最高连板只有1只，取它；如果有多只同最高，取封板最早的2只）
            top_lb = [s for s in sorted_s if s.get('lbc', 1) == max_lb]
            leaders = top_lb[:2] if len(top_lb) <= 2 else top_lb[:1]
            leader_codes = {s.get('c') for s in leaders}
            # 前排: 连板>=2 或 上午10:30前封板且炸板<=1次
            front = [s for s in sorted_s if s.get('c') not in leader_codes and
                     (s.get('lbc', 1) >= 2 or (s.get('fbt', 999999) <= 103000 and s.get('zbc', 0) <= 1))]
            front_codes = {s.get('c') for s in front}
            # 后排: 其余
            back = [s for s in sorted_s if s.get('c') not in leader_codes and s.get('c') not in front_codes]
            # 中军候选: 涨停股中流通市值最大的
            zhongjun = max(sorted_s, key=lambda s: s.get('ltsz', 0)) if sorted_s else None
            return leaders, front, back, zhongjun
        # === 详细列表（供web展示）===
        def _slim(d):
            return dict(code=d.get('c', ''), name=d.get('n', ''), lbc=d.get('lbc', 1),
                        hybk=d.get('hybk', ''), fbt=d.get('fbt', ''), zbc=d.get('zbc', 0),
                        hs=round(d.get('hs', 0), 1), lbt=d.get('lbt', ''),
                        fund=round(d.get('fund', 0) / 1e8, 2),
                        ltsz=round(d.get('ltsz', 0) / 1e8, 1))
        first_boards = [_slim(d) for d in zt if d.get('lbc', 1) == 1]
        # 连板梯队按板数分组
        ladder_grouped = {}
        for d in ladder:
            lb = d.get('lbc', 2)
            ladder_grouped.setdefault(lb, []).append(_slim(d))
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
            leaders, front, back, zhongjun = _classify(t_stocks)
            themes_list.append(dict(
                name=k, count=v, top_stock=_theme_first.get(k, ''),
                leaders=[_slim(s) for s in leaders],
                front=[_slim(s) for s in front],
                back=[_slim(s) for s in back],
                zhongjun=_slim(zhongjun) if zhongjun else None
            ))
        # === 封板质量分类（一字/T字/换手/烂板）===
        def _board_type(d):
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
        board_quality = {'一字': [], 'T字': [], '换手': [], '烂板': []}
        for d in zt:
            bt = _board_type(d)
            board_quality[bt].append(_slim(d))
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
            # 获取最近8天涨停池（足够判断最高连板）
            _pools = []  # [(date_str, {code_set}), ...] 从今日往前
            for _i in range(0, 8):
                _day = (_base - dt.timedelta(days=_i)).strftime('%Y%m%d')
                _pool_data = _pool('ZT', _day)
                if _pool_data:
                    _pools.append((_day, {d.get('c', '') for d in _pool_data}))
            if len(_pools) >= 2:
                _today_codes = _pools[0][1]
                _yesterday_codes = _pools[1][1]
                # 计算连续涨停天数：从某日往前数，直到不在涨停池
                def _streak(code, start_idx):
                    s = 0
                    for _j in range(start_idx, len(_pools)):
                        if code in _pools[_j][1]:
                            s += 1
                        else:
                            break
                    return s
                # 昨日每只股票的真实连板数
                _y_lbc = {c: _streak(c, 1) for c in _yesterday_codes}
                # 今日每只股票的真实连板数
                _t_lbc = {c: _streak(c, 0) for c in _today_codes}
                # 今日涨停股名称映射
                _t_names = {d.get('c', ''): d.get('n', d.get('c', '')) for d in zt}
                _y_names = {d.get('c', ''): d.get('n', d.get('c', '')) for d in _pool('ZT', _pools[1][0]) or []}
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
        if ymd == _now.strftime('%Y%m%d') and _now.hour < 15:
            w('(盘中快照不写档, 待15:00收盘后再跑一次归档)')
            return dict(score=s, band=band, zt=n_zt, zb=n_zb, dt=n_dt, max_lb=max_lb, ymd=ymd,
                         first_boards=first_boards, ladder_grouped=ladder_grouped,
                         limit_down=limit_down, themes_list=themes_list, promotion=promotion,
                         board_quality=board_quality, zha_ban=zha_ban, algo='v2',
                         score_v1=round(s_v1, 2), effect=_effect_flat(eff), diverge=diverge,
                         effect_available=eff.get('available'))
        recs = []
        if os.path.exists(hist):
            recs = [json.loads(l) for l in open(hist, encoding='utf-8')]
        if not any(r.get('date') == ymd for r in recs):
            # 交易日有效性门禁 v2: 日K存在(含今天) + 非"接口回吐" + 取数失败 fail-closed
            _ok, _why = _archive_eligible(ymd, recs, n_zt, n_zb, n_dt, max_lb)
            if not _ok:
                w(f'({ymd} 归档门禁拒绝: {_why})')
            else:
                with open(hist, 'a', encoding='utf-8') as fp:
                    fp.write(json.dumps(dict(date=ymd, score=round(s, 2), band=band, zt=n_zt,
                                             zb=n_zb, dt=n_dt, max_lb=max_lb, algo='v2',
                                             score_v1=round(s_v1, 2), effect=_effect_flat(eff),
                                             diverge=diverge), ensure_ascii=False) + '\n')
                w(f'(已存档 共{len(recs)+1}条)')
        return dict(score=s, band=band, zt=n_zt, zb=n_zb, dt=n_dt, max_lb=max_lb, ymd=ymd,
                     first_boards=first_boards, ladder_grouped=ladder_grouped,
                     limit_down=limit_down, themes_list=themes_list, promotion=promotion,
                     board_quality=board_quality, zha_ban=zha_ban, algo='v2',
                     score_v1=round(s_v1, 2), effect=_effect_flat(eff), diverge=diverge,
                     effect_available=eff.get('available'))
    except Exception as e:
        w(f'[情绪数据失败] {e}')
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
def kline_tx(full_code, days=160):
    # 1. 优先新浪日 K 线接口（毫秒级、免 WAF 限流、极度稳定）
    try:
        raw_code = full_code.lower()
        if not raw_code.startswith(('sh', 'sz')):
            raw_code = ('sh' if raw_code.startswith(('6', '5', '9')) else 'sz') + raw_code
        u = f'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={raw_code}&scale=240&ma=no&datalen={days}'
        raw = http(u, timeout=2.5, retries=1)
        data = json.loads(raw)
        if data and isinstance(data, list):
            out = []
            for r in data:
                out.append([r['day'], float(r['open']), float(r['close']), float(r['high']), float(r['low']), float(r['volume'])])
            if len(out) >= 5:
                return out
    except Exception:
        pass

    # 2. 东财历史 K 线接口（备用）
    try:
        code = full_code[2:]
        market = '1' if full_code.startswith(('sh', 'SH', '6', '5', '9')) else '0'
        secid = f'{market}.{code}'
        em_hdr = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Referer': 'https://www.eastmoney.com/'}
        url = (f'https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={secid}'
               f'&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61'
               f'&klt=101&fqt=1&end=20500101&lmt={days}')
        j = json.loads(http(url, headers=em_hdr, timeout=2.5, retries=1))
        klines = (j.get('data') or {}).get('klines') or []
        if klines:
            out = []
            for line in klines:
                p = line.split(',')
                out.append([p[0], float(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[5])])
            return out
    except Exception:
        pass

    # 3. 统一数据层（mootdx 兜底）
    try:
        import data_layer
        kl = data_layer.kline(full_code, days)
        if kl and len(kl) >= 5:
            return kl
    except Exception:
        pass

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
        kl = kline_tx(full, days); closes = [r[2] for r in kl]; last = closes[-1]
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
def _ema(vals, n):
    k = 2.0 / (n + 1)
    out = [vals[0]]
    for v in vals[1:]:
        out.append(out[-1] * (1 - k) + v * k)
    return out

def chan_analysis_structured(kl, code=''):
    """缠论日线级别结构化分析: K线包含合并、分型、笔、中枢识别、背驰与买卖点判定"""
    if not kl or len(kl) < 30:
        return {
            'status': 'error',
            'msg': 'K线数量不足30根，无法构建缠论中枢',
            'bi_points': [],
            'zhongshu_list': [],
            'last_zhongshu': None,
            'signals': [],
            'cur_dir': '未知',
            'trail': '',
            'summary': 'K线不足30根，结构尚未成型'
        }
    closes = [r[2] for r in kl]
    e12, e26 = _ema(closes, 12), _ema(closes, 26)
    dif = [a - b for a, b in zip(e12, e26)]
    dea = _ema(dif, 9)
    hist = [(a - b) * 2 for a, b in zip(dif, dea)]

    # 1. K线包含合并: [日期, 高, 低, 原始索引]
    bars = []
    for i, r in enumerate(kl):
        h, l = float(r[3]), float(r[4])
        if bars and ((h >= bars[-1][1] and l <= bars[-1][2]) or (h <= bars[-1][1] and l >= bars[-1][2])):
            up = len(bars) < 2 or bars[-2][1] <= bars[-1][1]
            if up:
                bars[-1][1] = max(bars[-1][1], h); bars[-1][2] = max(bars[-1][2], l)
            else:
                bars[-1][1] = min(bars[-1][1], h); bars[-1][2] = min(bars[-1][2], l)
            bars[-1][0] = r[0]; bars[-1][3] = i
        else:
            bars.append([r[0], h, l, i])

    # 2. 分型 -> 笔(交替极值, 间隔>=4根合并K线)
    fx = []
    for i in range(1, len(bars) - 1):
        p0, p1, p2 = bars[i - 1], bars[i], bars[i + 1]
        if p1[1] > p0[1] and p1[1] > p2[1]:
            fx.append([i, '顶', p1[1], p1[0], p1[3]])
        elif p1[2] < p0[2] and p1[2] < p2[2]:
            fx.append([i, '底', p1[2], p1[0], p1[3]])
    bi = []
    for f in fx:
        if not bi:
            bi.append(f); continue
        lf = bi[-1]
        if f[1] == lf[1]:
            if (f[1] == '顶' and f[2] > lf[2]) or (f[1] == '底' and f[2] < lf[2]):
                bi[-1] = f
        elif f[0] - lf[0] >= 4:
            bi.append(f)

    if len(bi) < 4:
        return {
            'status': 'warning',
            'msg': '有效笔不足4段，结构未成型',
            'bi_points': [[b[3], round(b[2], 2), b[1], b[4]] for b in bi],
            'zhongshu_list': [],
            'last_zhongshu': None,
            'signals': [],
            'cur_dir': '未知',
            'trail': '',
            'summary': '有效笔不足4段，中枢未成型'
        }

    trail = ' -> '.join('%s%.2f(%s)' % (b[1], b[2], str(b[3])[5:]) for b in bi[-5:])
    cur_dir = '向下' if bi[-1][1] == '顶' else '向上'
    bi_points = [[b[3], round(b[2], 2), b[1], b[4]] for b in bi]

    # 3. 中枢识别: 三笔重叠区间
    legs = [(bi[j - 1], bi[j]) for j in range(1, len(bi))]
    zhongshu_list = []
    for idx in range(len(legs) - 2):
        sub = legs[idx:idx + 3]
        los = [min(a[2], b[2]) for a, b in sub]
        his = [max(a[2], b[2]) for a, b in sub]
        z_lo, z_hi = max(los), min(his)
        if z_lo < z_hi:
            zhongshu_list.append({
                'lo': round(z_lo, 2),
                'hi': round(z_hi, 2),
                'start_date': sub[0][0][3],
                'end_date': sub[-1][1][3]
            })

    l3 = legs[-3:]
    los = [min(a[2], b[2]) for a, b in l3]
    his = [max(a[2], b[2]) for a, b in l3]
    zs_lo, zs_hi = max(los), min(his)
    last_zs = None
    pos = '未知'
    hint = ''
    signals = []

    if zs_lo < zs_hi:
        last_close = closes[-1]
        pos = '内部' if zs_lo <= last_close <= zs_hi else ('上方' if last_close > zs_hi else '下方')
        last_zs = {
            'lo': round(zs_lo, 2),
            'hi': round(zs_hi, 2),
            'start_date': l3[0][0][3],
            'end_date': l3[-1][1][3],
            'pos': pos
        }
        if pos == '上方' and cur_dir == '向上':
            hint = '三买候选: 向上离开中枢后次回抽不跌破中枢上轨'
            signals.append({
                'date': bi[-1][3], 'price': round(bi[-1][2], 2),
                'type': '三买候选', 'desc': '三买潜力', 'color': '#10b981'
            })
        elif pos == '下方' and cur_dir == '向下':
            hint = '三卖形态: 向下击穿中枢后次反弹不进中枢下轨'
            signals.append({
                'date': bi[-1][3], 'price': round(bi[-1][2], 2),
                'type': '三卖警戒', 'desc': '三卖警戒', 'color': '#ef4444'
            })

    # 4. 背驰判断
    def leg_area(a, b):
        lo_i, hi_i = sorted((a[4], b[4]))
        seg = hist[max(0, lo_i - 3):hi_i + 1]
        return sum(abs(x) for x in seg)

    sig_str = ''
    dn = [lg for lg in legs if lg[1][1] == '底']
    up = [lg for lg in legs if lg[1][1] == '顶']
    if len(dn) >= 2:
        (a1, b1), (a2, b2) = dn[-2], dn[-1]
        if b2[2] < b1[2] and leg_area(a2, b2) < leg_area(a1, b1):
            sig_str = '底背驰候选(价创新低·动能收缩)'
            signals.append({
                'date': b2[3], 'price': round(b2[2], 2),
                'type': '底背驰', 'desc': '底背驰', 'color': '#10b981'
            })
    if len(up) >= 2:
        (a1, b1), (a2, b2) = up[-2], up[-1]
        if b2[2] > b1[2] and leg_area(a2, b2) < leg_area(a1, b1):
            sig_str = '顶背驰候选(价创新高·动能收缩)'
            signals.append({
                'date': b2[3], 'price': round(b2[2], 2),
                'type': '顶背驰', 'desc': '顶背驰', 'color': '#ef4444'
            })

    summary_parts = [f"当前处于日线【{cur_dir}的一笔】"]
    if last_zs:
        summary_parts.append(f"中枢区间 [{last_zs['lo']} ~ {last_zs['hi']}]，现价位于中枢【{pos}】")
    if hint:
        summary_parts.append(hint)
    if sig_str:
        summary_parts.append(f"异动信号：{sig_str}")

    return {
        'status': 'ok',
        'cur_dir': cur_dir,
        'trail': trail,
        'bi_points': bi_points,
        'bi_list': bi_points,
        'zhongshu_list': zhongshu_list[-3:],
        'last_zhongshu': last_zs,
        'signals': signals,
        'divergence': sig_str or '无明显背驰',
        'summary': '；'.join(summary_parts)
    }

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

def _lhb_detail(code, day, flag):
    import urllib.parse
    pr = {'reportName': 'RPT_BILLBOARD_DAILYDETAILSBUY' if flag == 'B' else 'RPT_BILLBOARD_DAILYDETAILSSELL',
          'columns': 'ALL', 'filter': "(TRADE_DATE='%s')(SECURITY_CODE=\"%s\")" % (day, code),
          'pageNumber': '1', 'pageSize': '500', 'sortTypes': '-1',
          'sortColumns': 'BUY' if flag == 'B' else 'SELL', 'source': 'WEB', 'client': 'WEB'}
    j = json.loads(http('https://datacenter-web.eastmoney.com/api/data/v1/get?' + urllib.parse.urlencode(pr)))
    return ((j.get('result') or {}).get('data')) or []

def lhb_profile(code):
    day, rb, rs = None, [], []
    for i in range(9):
        dd = dt.date.today() - dt.timedelta(days=i)
        if dd.weekday() >= 5:
            continue
        b = _lhb_detail(code, dd.strftime('%Y-%m-%d'), 'B')
        s_ = _lhb_detail(code, dd.strftime('%Y-%m-%d'), 'S')
        if b or s_:
            day, rb, rs = dd.strftime('%Y-%m-%d'), b, s_
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

_AGENT_W = [('国家队', 1.2), ('机构', 0.9), ('游资', 1.0), ('团伙(控盘)', 0.6), ('散户', 0.7), ('北向', 0.8), ('量化', 0.7), ('产业资本', 0.5), ('大散户', 0.9)]

def agent_sim(code=None):
    w('')
    if not code:
        w('===== [多主体推演·五类参与者博弈(大盘)] =====')
        try:
            stage = cycle_position()
        except Exception:
            stage = None
        recs = []
        fp = os.path.join(DATA_DIR, 'sentiment_history.jsonl')
        if os.path.exists(fp):
            recs = [json.loads(l) for l in open(fp, encoding='utf-8') if l.strip()]
        if not recs:
            w('(无情绪存档, 无法推演)')
            return
        last = recs[-1]
        sc = float(last.get('score', 50)); zt = float(last.get('zt', 0))
        n_dt = float(last.get('dt', 0)); lb = float(last.get('max_lb', 0))
        zbrate = float(last.get('zb', 0)) / max(zt + float(last.get('zb', 1)), 1) * 100
        mgd = 0.0
        try:
            u = ('https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPTA_RZRQ_LSHJ'
                 '&columns=DIM_DATE,RZRQYE&sortColumns=DIM_DATE&sortTypes=-1&pageSize=2&pageNumber=1')
            rows = json.loads(http(u))['result']['data']
            mgd = (float(rows[0]['RZRQYE']) - float(rows[1]['RZRQYE'])) / 1e8
        except Exception:
            pass
        def cl(v, lo, hi):
            return max(lo, min(hi, v))
        ag = {}
        ag['散户'] = cl((sc - 45) * 3, -70, 85) * (0.5 if stage == '退潮' else 1) + (-20 if stage == '冰点' else 0)
        ag['游资'] = lb * 14 - zbrate * 1.2 + {'主升': 35, '亢奋': 10, '修复/震荡': 5, '退潮': -35, '冰点': -50}.get(stage or '', 0)
        ag['机构'] = cl((20 if mgd > 0 else -15 if mgd < 0 else 0) + (sc - 50) * 0.6, -40, 40)
        ag['团伙(控盘)'] = lb * 16 - zbrate * 0.8 + (10 if 40 <= zt <= 95 else 0) + (-25 if stage in ('退潮', '冰点') else 0)
        ag['国家队'] = 40 if (n_dt >= 10 or sc < 35) else (-20 if sc > 68 else 0) + (20 if mgd < -100 else 0)
        w('  参与者    倾向(-100空~+100多)  依据')
        basis = {
            '散户': '情绪%d分%s' % (sc, '/退潮跟风减半' if stage == '退潮' else ''),
            '游资': '高度%.0f板 炸板率%.0f%% 阶段[%s]' % (lb, zbrate, stage),
            '机构': '两融环比%+.0f亿 情绪中性偏离%+.0f' % (mgd, sc - 50),
            '团伙(控盘)': '题材活跃度(涨停%.0f家)与锁仓环境' % zt,
            '国家队': '跌停%.0f家/系统性信号/杠杆流失%s' % (n_dt, '%.0f亿' % mgd if mgd < -100 else '不明显')}
        net = 0.0
        for name, ww in [x for x in _AGENT_W if x[0] in ag]:
            v = ag[name]
            net += v * ww
            arrow = '看多' if v > 15 else ('看空' if v < -15 else '观望')
            w('  %-8s %+7.0f [%s]  %s' % (name, v, arrow, basis[name]))
        w('  ---- 加权合力: %+.0f ----' % net)
        path = ('修复反弹概率偏高: 关注率先走出4板的题材种子' if net > 30 else
                '恐慌加速风险偏高: 严控仓位等出清信号' if net < -40 else
                '惯性退潮·缩量磨底: 多看少动, 等待右侧确认')
        w('  >> 推演路径: ' + path)
        w('  >> 注: 规则引擎基于当日实数据的启发式打分, 是推演不是预测')
    else:
        full = ('sh' + code) if code.startswith(('6', '5', '9')) else ('sz' + code)
        quotes = tx_realtime([full])
        if not quotes:
            w('[行情] 未能获取到股票代码 %s 的行情数据，请核对代码' % code)
            return
        q = quotes[0]
        pct = q.get('pct', 0.0)
        w('[行情] %s %+.2f%% 额%s' % (q.get('name', code), pct, q.get('amount', '-')))
        prof = lhb_profile(code)
        w(prof if isinstance(prof, str) else '')
        ymd = dt.date.today().strftime('%Y%m%d')
        zt = _pool('ZT', ymd)
        me = next((x for x in zt if x.get('c') == code), None)
        seal = ''
        if me:
            rt = _num(me.get('fund')) / max(_num(me.get('ltsz')), 1) * 100
            seal = '涨停在榜: 封单%.1f亿(占流通%.1f%%) %d板 炸板%d次' % (
                _num(me.get('fund')) / 1e8, rt, me.get('lbc', 1), me.get('zbc', 0))
            w('[涨停] ' + seal)
        ag = {}
        ag['散户'] = 60 if pct > 7 else (30 if pct > 2 else -30 if pct < -4 else 0)
        ag['游资'] = (35 if me else 0) + (15 if '知名游资主导买入' in str(prof) else -15 if isinstance(prof, str) and '营业部通道' in prof else 0) + (-20 if pct < -5 else 0)
        ag['机构'] = 30 if '中线资金介入' in str(prof) else (-30 if '筹码向短线转移' in str(prof) else 0)
        ag['团伙(控盘)'] = 40 if (me and rt >= 1.5) else (-20 if me and me.get('zbc', 0) >= 3 else 0)
        ag['国家队'] = 0
        ag, _ = _sim_pipeline(ag, use_memory=False)   # 个股: 无记忆无情景, 仅传染; 势力子集自动适配
        net, net_pct = _weighted_net(ag)              # 统一加权口径(原裸 sum 已废)
        for name, ww in [x for x in _AGENT_W if x[0] in ag]:
            v = ag[name]
            arrow = '买入/拉抬' if v > 25 else ('做多' if v > 10 else ('观望' if v > -10 else '卖出/出货'))
            act = _get_agent_action(name, v)
            w('  %-8s %+4.0f分 [%s] 动作: %s' % (name, v, arrow, act))
        w('  ---- 加权合力: %+.0f ----' % net)
        w('  ---- 加权合力: %+.0f (均值%+.1f/±100) ----' % (net, net_pct))
        # 阈值换算自旧裸sum口径(>40,<-20)/权重和3.2 → +12.5/-6.25, 保持判定语义不变
        verdict = ('多头合力: 情绪票接力格局, 注意龙头断板信号' if net_pct >= 12.5 else
                   '空头压力: 谨防高位派发' if net_pct <= -6.25 else
                   '多空均衡: 区间对待')
        w('  >> 推演: ' + verdict)


# ---------- 12. 世界模拟v2(MiroFish三机制: 势力记忆/交互传染/情景注入) ----------
_AG_ST = os.path.join(DATA_DIR, 'agents_state.json')
_SCN = {
    '外盘暴跌': {'散户': -50, '游资': -35, '机构': -25, '团伙(控盘)': -10, '国家队': 45, '量化': -30, '北向': -45, '产业资本': -5, '大散户': -35},
    '外盘大涨': {'散户': 40, '游资': 30, '机构': 25, '团伙(控盘)': 10, '国家队': -10, '量化': 25, '北向': 35, '产业资本': 5, '大散户': 45},
    '重磅利好': {'散户': 45, '游资': 35, '机构': 20, '团伙(控盘)': 15, '国家队': 0, '量化': 20, '北向': 25, '产业资本': 10, '大散户': 55},
    '利空突袭': {'散户': -45, '游资': -30, '机构': -20, '团伙(控盘)': -15, '国家队': 30, '量化': -25, '北向': -30, '产业资本': -10, '大散户': -40},
    '流动性收紧': {'散户': -25, '游资': -30, '机构': -35, '团伙(控盘)': -20, '国家队': 0, '量化': -40, '北向': -35, '产业资本': -15, '大散户': -45},
}

def parse_event_scenario(text):
    """MiroFish 级事件语义解析引擎：将任意自然语言突发事件映射为九方势力冲击矩阵"""
    if not text:
        return {'domain': '日常基准', 'polarity': 0, 'desc': '无外生事件冲击，以真实市场博弈为基准'}, {}
    text = text.strip()
    if text in _SCN:
        desc_map = {
            '外盘暴跌': ('外盘冲击', -1, '海外重挫波及A股开盘情绪，北向撤退'),
            '外盘大涨': ('外盘提振', 1, '全球风险偏好回暖，北向与权重共振'),
            '重磅利好': ('全面利好', 1, '重磅支持政策出台，激活全场资金风险偏好'),
            '利空突袭': ('黑天鹅突袭', -1, '突发负面冲击，各路资金避险防御'),
            '流动性收紧': ('流动性收缩', -1, '宏观或场内流动性承压，压缩估值空间'),
        }
        meta = desc_map.get(text, ('预设情景', 0, '预设宏观冲击'))
        return {'domain': meta[0], 'polarity': meta[1], 'desc': meta[2]}, _SCN[text]

    impact = {'散户': 0, '游资': 0, '机构': 0, '团伙(控盘)': 0, '国家队': 0, '量化': 0, '北向': 0, '产业资本': 0, '大散户': 0}
    
    # 1. 货币与宏观流动性
    if any(k in text for k in ['降准', '降息', '放水', '流动性宽松', '下调准备金', '印花税', '减税', '逆回购加量']):
        impact.update({'机构': 35, '游资': 30, '散户': 45, '大散户': 50, '量化': 25, '北向': 30, '国家队': -10, '产业资本': 15})
        meta = {'domain': '宏观货币宽松', 'polarity': 1, 'desc': '无风险利率下行与资金面宽松，全面抬升市场估值中枢与交易意愿'}
    elif any(k in text for k in ['加息', '收紧', '去杠杆', '通胀高企', '紧缩', '提高准备金']):
        impact.update({'机构': -35, '游资': -30, '散户': -30, '大散户': -40, '量化': -35, '北向': -40, '国家队': 15, '产业资本': -15})
        meta = {'domain': '宏观流动性收紧', 'polarity': -1, 'desc': '流动性预期边际转紧，压制高估值品种与杠杆投机盘'}
        
    # 2. 外盘与地缘冲击
    elif any(k in text for k in ['美股暴跌', '美股大跌', '外盘暴跌', '外盘重挫', '关税', '制裁', '地缘冲突', '战争', '封锁', '出口限制']):
        impact.update({'北向': -45, '散户': -40, '游资': -35, '机构': -25, '量化': -30, '国家队': 50, '大散户': -35, '产业资本': -10})
        meta = {'domain': '外生与地缘风险', 'polarity': -1, 'desc': '全球避险情绪爆发引发外资流出，国家队承担逆周期托底职责'}
    elif any(k in text for k in ['美股大涨', '外盘大涨', '纳指新高', '中概大涨', '外盘反弹']):
        impact.update({'北向': 40, '机构': 25, '游资': 30, '散户': 35, '量化': 25, '国家队': -15, '大散户': 45, '产业资本': 10})
        meta = {'domain': '外盘向好传导', 'polarity': 1, 'desc': '海外市场强势提振风险偏好，高贝塔品种与核心资产受益'}

    # 3. 科技创新与新质产业题材利好
    elif any(k in text for k in ['AI', '人工智能', '芯片', '半导体', '算力', '创新药', '低空经济', '商业航天', '固态电池', '重磅突破', '新质生产力', '科技支持', '重大合同', '中标']):
        impact.update({'游资': 50, '大散户': 45, '量化': 35, '团伙(控盘)': 30, '散户': 35, '机构': 20, '北向': 15, '国家队': 0, '产业资本': 15})
        meta = {'domain': '产业科技利好', 'polarity': 1, 'desc': '主线科技题材催化，游资与量化共振主攻首板与前排，散户接力跟进'}

    # 4. 监管降温与核查特停
    elif any(k in text for k in ['特停', '核查', '问询', '立案', '严打', '操纵', '降温', '限制高频', '异常交易', '违规减持']):
        impact.update({'游资': -55, '团伙(控盘)': -50, '量化': -35, '大散户': -40, '散户': -25, '机构': -10, '国家队': 20, '北向': -15})
        meta = {'domain': '监管降温与合规风控', 'polarity': -1, 'desc': '接力情绪骤降，高位妖股断板退潮，资金被迫防御或切换至低位中军'}

    # 5. 业绩雷与黑天鹅
    elif any(k in text for k in ['暴雷', '亏损', '造假', '暴跌', '退市', '违规被查', '扣押', '留置', '债务危机']):
        impact.update({'散户': -50, '大散户': -45, '机构': -35, '游资': -25, '量化': -25, '团伙(控盘)': -20, '国家队': 30, '北向': -30})
        meta = {'domain': '黑天鹅突袭', 'polarity': -1, 'desc': '信任崩塌引发非理性出清与踩踏，资金转向防御类避险品种'}

    # 6. 通用情感自然语言识别
    else:
        pos_words = ['利好', '上涨', '大涨', '增长', '突破', '爆发', '超预期', '买入', '增持', '繁荣', '合作', '复苏', '首发', '提升', '新高']
        neg_words = ['利空', '下跌', '大跌', '下滑', '爆雷', '恶化', '打压', '封杀', '警惕', '风险', '亏损', '受阻', '制约', '衰退']
        pos_cnt = sum(1 for w in pos_words if w in text)
        neg_cnt = sum(1 for w in neg_words if w in text)
        
        if pos_cnt > neg_cnt:
            scale = min(1.6, 0.8 + pos_cnt * 0.25)
            impact.update({'游资': int(35 * scale), '散户': int(30 * scale), '大散户': int(40 * scale), '机构': int(20 * scale), '量化': int(25 * scale), '北向': int(20 * scale), '产业资本': int(10 * scale)})
            meta = {'domain': '正面催化事件', 'polarity': 1, 'desc': f'识别出{pos_cnt}项积极要素，多头势力顺势做多并带动市场风险偏好'}
        elif neg_cnt > pos_cnt:
            scale = min(1.6, 0.8 + neg_cnt * 0.25)
            impact.update({'散户': int(-35 * scale), '游资': int(-30 * scale), '大散户': int(-35 * scale), '机构': int(-20 * scale), '量化': int(-25 * scale), '北向': int(-25 * scale), '国家队': int(30 * scale)})
            meta = {'domain': '负面风险事件', 'polarity': -1, 'desc': f'识别出{neg_cnt}项负面扰动，空头预期主导，需防范冲高回落或惯性下探'}
        else:
            impact.update({'散户': -10, '游资': 15, '大散户': 10, '机构': -10, '量化': 20, '国家队': 0})
            meta = {'domain': '结构分歧事件', 'polarity': 0, 'desc': '多空信号交织，市场缺乏强共识，各势力转入日内分歧轮动'}

    return meta, impact

def _get_agent_action(name, val):
    if val >= 30:
        actions = {
            '国家队': '降温平抑：对过热标的适度减持或引导中枢平衡',
            '机构': '积极进攻：增配大盘价值、高股息红利与行业成长龙头',
            '游资': '极限进攻：开盘猛顶核心题材一字板，全力打造连板标杆',
            '团伙(控盘)': '合力锁仓：强力控盘封板，借市场势头大幅拉升溢价',
            '散户': '羊群跟风：亢奋追涨，高频挂涨停价抢入最热标的',
            '北向': '大举买入：大幅净买入核心资产，带动权重与指数冲关',
            '量化': '高频动量：触发追涨打板模型，日内满仓加杠杆做T助推',
            '产业资本': '溢价接盘：大宗交易溢价成交，发布增持或回购计划',
            '大散户': '猛推龙头：大额融资加仓辨识度龙头，锁死流动性',
        }
    elif val >= 10:
        actions = {
            '国家队': '常规观察：无极端异动，维持常规流动性支持',
            '机构': '温和调仓：低吸低估值防守品种，试探性建仓结构机会',
            '游资': '首板挖掘：围绕主线板块寻找首板与1进2低吸套利',
            '团伙(控盘)': '盘中做T：维护分时均线平稳，小幅收集低位浮筹',
            '散户': '试探买入：逐步增加仓位，偏好低价股与热门概念',
            '北向': '顺势流入：小幅净流入，偏向消费与科技蓝筹',
            '量化': '正常做T：维持网格交易与动量Alpha策略',
            '产业资本': '平稳持股：大宗交易平价成交，维持经营性定力',
            '大散户': '跟随做多：逢低建仓趋势中军，不盲目打板',
        }
    elif val <= -30:
        actions = {
            '国家队': '逆周期强力护盘：大手笔买入宽基ETF、四大行与中字头托底',
            '机构': '无差别防御：大幅减持高贝塔与周期股，回笼现金避险',
            '游资': '无情核按钮：开盘一字跌停砸盘抢跑，毫不犹豫断臂止损',
            '团伙(控盘)': '砸盘出逃：放弃护盘，利用反弹高抛甩卖出清库存',
            '散户': '恐慌踩踏：竞价割肉挂跌停，绝望离场并相互踩踏',
            '北向': '加速撤退：大幅单边净流出，抛售白马核心资产',
            '量化': '抽离流动性：触发强制风控止损线，多头策略集体平仓',
            '产业资本': '折价甩卖：急需流动性，大宗交易大比例折价出逃',
            '大散户': '杠杆爆仓止损：被动平仓与平仓甩卖，引发流动性危机',
        }
    elif val <= -10:
        actions = {
            '国家队': '被动防御：在重要均线与整数关口挂单拦截急跌',
            '机构': '减仓观望：适度降低权益仓位，增加现金头寸防守',
            '游资': '防守反包：放弃连板高标接力，退守超跌反弹做套利',
            '团伙(控盘)': '边拉边撤：制造虚假拉升诱多，伺机分批派发筹码',
            '散户': '套牢死扛：不愿止损，被迫“短线变长线”持股待涨',
            '北向': '谨慎观望：外资呈小幅净流出态势，规避风险板块',
            '量化': '收紧敞口：降低多头暴露，加大日内对冲与融券做空',
            '产业资本': '偶有折价：大宗交易小幅折价，减持意愿略有抬头',
            '大散户': '分批减仓：主动平掉融资杠杆，保留现金实力',
        }
    else:
        actions = {
            '国家队': '按兵不动：多空平衡，无需额外行政与资金干预',
            '机构': '持仓观望：按兵不动等待明确的宏观数据或财报指引',
            '游资': '混沌试盘：轻仓打野，试探盘面阻力，不盲目发动总攻',
            '团伙(控盘)': '窄幅震荡：维持当前市值区间，等待市场合力契机',
            '散户': '分歧犹豫：买卖意愿不强，成交清淡，多持币观望',
            '北向': '双向对冲：日内波动较小，净流入流出基本相抵',
            '量化': '高频套利：依赖盘中微小波动获取超额收益，不押单边',
            '产业资本': '正常运营：无明显异动与资本运作，静观其变',
            '大散户': '观望为主：不轻易出手，等待右侧放量确定性信号',
        }
    return actions.get(name, '按兵不动观望')

_CONT = {'散户': [('游资', 0.28)],
         '游资': [('团伙(控盘)', 0.18), ('国家队', -0.12), ('量化', 0.10)],
         '机构': [('国家队', 0.15), ('北向', 0.10)],
         '团伙(控盘)': [('游资', 0.15), ('机构', 0.10), ('量化', 0.08)],
         '国家队': [],
         '量化': [('游资', 0.12), ('机构', 0.06)],
         '北向': [('国家队', 0.15)],
         '产业资本': [],
         '大散户': [('游资', 0.22), ('散户', 0.10)]}

def _mem_load():
    try:
        rec = json.load(open(_AG_ST, encoding='utf-8'))
        rec.setdefault('schema_version', 1)   # v1 兼容: 无版本号视为1
        return rec
    except Exception:
        return {}

def _mem_save(rec):
    json.dump(rec, open(_AG_ST, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

def _sim_pipeline(ag, scenario=None, use_memory=False, cur_date='', verbose=False,
                  impact_override=None, impact_note=''):
    """统一推演管道(dsh方案C): ①势力记忆锚定(use_memory, 惯性0.3) ②情景注入 ③3轮传染(阻尼0.6)。
    势力子集自动适配(_CONT 只作用于存在的势力)。返回 (ag, 轮次快照行列表)。"""
    cl = lambda v, lo, hi: max(lo, min(hi, v))
    if use_memory:
        mem = _mem_load()
        prev = {} if mem.get('date') == cur_date else (mem.get('stances') or {})
        if prev:
            if verbose:
                w('【记忆】昨日立场 -> 今日初始(惯性0.3):')
            for k in ag:
                pv = float(prev.get(k, 0))
                ag[k] = ag[k] * 0.7 + pv * 0.3
                if verbose:
                    w('  %-8s %+5.0f -> %+5.0f' % (k, pv, ag[k]))
    if scenario or impact_override:
        if impact_override:
            # LLM(或外部)给出的九方冲击矩阵: 只覆盖"判断"这一层, 后面的传染/加权仍走本引擎
            meta = {'domain': impact_note or 'LLM 消息面推演',
                    'desc': '外部冲击矩阵（LLM 依据当日消息面事件表给出），数值聚合仍由本引擎计算'}
            impact = {}
            for _k, _v in (impact_override or {}).items():
                try:
                    impact[str(_k)] = float(_v)
                except (TypeError, ValueError):
                    continue      # 非数值项(如 theme_priority 列表)不进冲击矩阵
        else:
            meta, impact = parse_event_scenario(scenario)
        if verbose:
            if scenario:
                w('【上帝视角·事件注入】: %s' % scenario)
            if impact_override:
                w('【事件注入·LLM 冲击矩阵】%s' % ' '.join('%s%+.0f' % (k, v) for k, v in impact.items()))
                _it = impact_override.get('theme_priority') if isinstance(impact_override, dict) else None
                if _it:
                    w('【LLM 板块优先级】%s' % ' '.join('%s%s' % (
                        '+' if x.get('polarity', 0) > 0 else ('-' if x.get('polarity', 0) < 0 else '·'),
                        x.get('sector', '')) for x in _it[:6]))
            w('【事件研判】领域: %s | 影响逻辑: %s' % (meta['domain'], meta['desc']))
        ag = {k: cl(v + impact.get(k, 0), -100, 100) for k, v in ag.items()}
    names = list(ag)
    lines = []
    for rnd in range(1, 4):
        nxt = dict(ag)
        for k in names:
            d = sum(wt * ag[kj] for kj, wt in _CONT.get(k, []) if kj in ag)
            nxt[k] = cl(ag[k] + 0.6 * d, -100, 100)
        ag = nxt
        line = '【传染R%d】%s' % (rnd, ' '.join('%s%+.0f' % (k[:2], ag[k]) for k in names))
        lines.append(line)
        if verbose:
            w(line)
    return ag, lines

def _weighted_net(ag):
    """统一口径(dsh方案C核心): 任意势力子集一律按 _AGENT_W 同名权重加权。
    返回 (加权净额, 加权均值): 均值 = 净额/权重和, 天然落在 ±100 刻度(与立场同单位),
    可跨 scope 比较——修掉个股裸 sum 未加权的口径分裂。注意均值不再乘100。"""
    net = sum(ag[n] * ww for n, ww in _AGENT_W if n in ag)
    wsum = sum(ww for n, ww in _AGENT_W if n in ag)
    return net, (net / wsum if wsum else 0.0)

# ---------- 事件映射标的、竞价分叉对策与历史时光机对账 ----------
_HISTORICAL_BENCHMARKS = [
    {
        'key': '2024-09-24',
        'title': '2024-09-24 国新办金融三部委王炸组合拳',
        'scenario': '国新办重磅发布会：降准50BP释放1万亿、降息20BP、创设首期5000亿互换便利与3000亿股票回购增持再贷款',
        'real_market': '三大指数历史级爆发，上证单日大涨+4.15%，创业板狂飙+5.54%，全市场超5100股普涨，成交量放大至9700亿，随后引爆史诗级牛市行情！',
        'force_review': '国家队与机构联手大金融中军破阵，游资与量化开盘全线顶格抢筹券商金融科技，散户极速空翻多狂欢，北向单日暴买百亿。'
    },
    {
        'key': '2024-10-08',
        'title': '2024-10-08 节后天量开盘3.45万亿巨震',
        'scenario': '国庆假期开户暴增，节后首日全市场高开近千股竞价涨停，成交额破纪录达3.45万亿元',
        'real_market': '上证跳空高开+10%后巨震收涨+4.59%，单日巨震3.45万亿创历史纪录，走出巨量长假阴线，次日深度大洗盘，多空分化达到顶峰。',
        'force_review': '散户蜂拥冲锋满仓入场，机构与大散户趁高位天量逢高减持派发，量化日内多空激烈对冲，资金承接面临严峻换手考验。'
    },
    {
        'key': '2024-11-08',
        'title': '2024-11-08 10万亿化债与地方隐性债务置换',
        'scenario': '全国人大常委会批准增加6万亿元地方政府债务限额置换存量隐性债务，合计化债规模达10万亿元',
        'real_market': '此前预期充分发酵，政策靴子落地后指数呈现高位蓄势与良性震荡，资金有序自大盘权重向低位AMC化债与破净红利扩散。',
        'force_review': '机构重估地方资产负债表与银行资产质量，游资活跃于地方AMC概念首板套利，大盘进入健康结构性轮动。'
    },
    {
        'key': '2024-01-22',
        'title': '2024-01-22 雪球敲入冰点与国家队救市',
        'scenario': '中证500/1000雪球衍生品大面积敲入，小盘微盘流动性枯竭遭遇踩踏，国家队动用大额资金扫货宽基ETF托底',
        'real_market': '市场极度恐慌冰点，千股跌停，但国家队随后以数百亿资金买入沪深300及中证500ETF，彻底扭转流动性枯竭，构筑大双底。',
        'force_review': '散户与大散户恐慌割肉踩踏，量化DMA被动减仓，国家队逆周期强力托底扫货，成功阻断系统性金融风险。'
    },
    {
        'key': '2023-08-27',
        'title': '2023-08-27 证券印花税减半征收史诗级利好',
        'scenario': '财政部、税务总局宣布证券交易印花税减半征收，证监会统筹一二级市场平衡，阶段性收紧IPO并规范减持',
        'real_market': '8月28日三大指数大幅高开逾+5%，券商近50股竞价涨停，随后因存量博弈抛压沉重，一路震荡走低收长假阴线。',
        'force_review': '游资与散户竞价疯抢一字板，但机构与大散户借超预期高开大举砸盘兑现，体现了弱市存量博弈中“利好出尽先卖为敬”的真实博弈。'
    }
]

_EVENT_THEMES = [
    {
        'keywords': ['降准', '降息', '流动性', '货币', '放水', '准备金', '印花税', '减税', '逆回购', '互换便利', '再贷款', '金融三部委', '大金融'],
        'theme': '大金融与高贝塔弹性核心',
        'sectors': ['证券', '金融科技', '多元金融', '房地产'],
        'stocks': [
            {'code': '600030', 'name': '中信证券', 'role': '中军总舵手', 'tag': '券商一哥·流动性最直接受益'},
            {'code': '300059', 'name': '东方财富', 'role': '弹性急先锋', 'tag': '创业板零售券商龙头·交投放大弹性王'},
            {'code': '300033', 'name': '同花顺', 'role': '金融科技先锋', 'tag': 'AI炒股软件·交投活跃催化业绩'},
            {'code': '601377', 'name': '中原证券', 'role': '低位首板标杆', 'tag': '中小券商高贝塔连板先锋'}
        ]
    },
    {
        'keywords': ['AI', '人工智能', '芯片', '半导体', '算力', 'CPO', '光模块', '服务器', '昇腾', '模型', 'PCB'],
        'theme': '新一代人工智能与自主算力底座',
        'sectors': ['CPO光模块', '算力芯片', 'AI服务器', 'PCB覆铜板'],
        'stocks': [
            {'code': '300308', 'name': '中际旭创', 'role': '全球总龙头', 'tag': '800G/1.6T高速光模块领航者'},
            {'code': '300502', 'name': '新易盛', 'role': '弹性先锋', 'tag': '光通信模块高弹性标的'},
            {'code': '601138', 'name': '工业富联', 'role': '千亿中军', 'tag': 'AI高算力服务器与高速交换机中军'},
            {'code': '688256', 'name': '寒武纪', 'role': '自主算力', 'tag': '国产AI训练推理芯片核心标杆'}
        ]
    },
    {
        'keywords': ['低空', '飞行汽车', 'eVTOL', '无人机', '航天', '卫星', '商业航天'],
        'theme': '低空经济与商业航天新质生产力',
        'sectors': ['低空经济', '商业航天', '卫星互联网', '通航运营'],
        'stocks': [
            {'code': '000099', 'name': '中信海直', 'role': '运营核心', 'tag': '国内通航飞行运营绝对龙头'},
            {'code': '002085', 'name': '万丰奥威', 'role': '整机先锋', 'tag': 'eVTOL飞行器研发与整机制造领头羊'},
            {'code': '600118', 'name': '中国卫星', 'role': '航天中军', 'tag': '卫星制造国家队·商业航天核心中军'}
        ]
    },
    {
        'keywords': ['固态电池', '锂电', '电池', '新能源', '储能', '光伏'],
        'theme': '下一代固态电池与清洁能源革新',
        'sectors': ['固态电池', '锂电池材料', '光伏设备', '大储能'],
        'stocks': [
            {'code': '300750', 'name': '宁德时代', 'role': '全球霸主', 'tag': '动力电池绝对王者·技术创新中军'},
            {'code': '002460', 'name': '赣锋锂业', 'role': '资源与固态', 'tag': '固态电池金属锂负极先发优势'},
            {'code': '300037', 'name': '新宙邦', 'role': '电解质先锋', 'tag': '新型电解质与固态材料领航者'}
        ]
    },
    {
        'keywords': ['创新药', '医药', '医疗', '疫苗', '生物科技', 'CXO'],
        'theme': '生物医药创新与出海先锋',
        'sectors': ['创新药', 'CXO一体化', '医疗器械', '中药创新'],
        'stocks': [
            {'code': '600276', 'name': '恒瑞医药', 'role': '创新药中军', 'tag': '国内创新药研发一哥·多品类管线出海'},
            {'code': '603259', 'name': '药明康德', 'role': '全球CXO一体化', 'tag': '全球新药外包服务领跑者'},
            {'code': '300347', 'name': '泰格医药', 'role': '临床CRO龙头', 'tag': '国内临床研究外包先锋'}
        ]
    },
    {
        'keywords': ['消费', '内需', '以旧换新', '补贴', '家电', '汽车', '白酒'],
        'theme': '内需大消费与产业以旧换新',
        'sectors': ['白酒消费', '白电龙头', '整车制造', '商贸零售'],
        'stocks': [
            {'code': '600519', 'name': '贵州茅台', 'role': '消费定海神针', 'tag': '大消费价值核心·北向与机构底仓'},
            {'code': '000651', 'name': '格力电器', 'role': '高股息白电', 'tag': '消费品以旧换新与高分红防御'},
            {'code': '002594', 'name': '比亚迪', 'role': '整车制造旗舰', 'tag': '新能源汽车销量与市占率第一'}
        ]
    },
    {
        'keywords': ['化债', '债务', 'AMC', '基建', '水利', '地方债'],
        'theme': '大规模化债与地方AMC资产重估',
        'sectors': ['地方AMC', '金融化债', '破净基建央企', '环保水务'],
        'stocks': [
            {'code': '600000', 'name': '浦发银行', 'role': '金融化债先锋', 'tag': '资产质量改善·地方债务置换受益'},
            {'code': '601668', 'name': '中国建筑', 'role': '基建破净央企', 'tag': '应收账款回流·央企估值重塑'},
            {'code': '000063', 'name': '中兴通讯', 'role': '数字基建中军', 'tag': '新质生产力通信基础设施底座'}
        ]
    },
    {
        'keywords': ['暴跌', '外盘暴跌', '地缘', '战争', '特停', '核查', '立案', '黑天鹅', '风险', '利空', '去杠杆', '紧缩', '雪球'],
        'theme': '避险对冲与低估值高股息防守堡垒',
        'sectors': ['高股息红利', '黄金贵金属', '煤炭能源', '大行中字头'],
        'stocks': [
            {'code': '601088', 'name': '中国神华', 'role': '终极红利护城河', 'tag': '高股息现金流·牛熊避风港'},
            {'code': '600900', 'name': '长江电力', 'role': '防守基石', 'tag': '无视经济周期的水电价值锚点'},
            {'code': '601899', 'name': '紫金矿业', 'role': '地缘避险先锋', 'tag': '金铜资源战略储备·抗通胀与避险'},
            {'code': '600489', 'name': '中金黄金', 'role': '黄金纯正标的', 'tag': '国际金价共振避险弹性标的'}
        ]
    }
]

def get_event_beneficiary_stocks(scenario_text='', domain='', net_val=0):
    """根据事件语义或推演合力，智能穿透并获取核心受益/避险标的实时行情"""
    matched = None
    txt = (scenario_text or '') + ' ' + (domain or '')
    
    for t in _EVENT_THEMES:
        if any(k.lower() in txt.lower() for k in t['keywords']):
            matched = t
            break
            
    if not matched:
        if net_val < -20:
            matched = _EVENT_THEMES[-1]
        elif net_val > 25:
            matched = _EVENT_THEMES[0]
        else:
            matched = _EVENT_THEMES[1]
            
    codes = [s['code'] for s in matched['stocks']]
    tx_codes = [('sh' if c.startswith(('6', '5', '9')) else 'sz') + c for c in codes]
    quote_map = {}
    try:
        url = 'https://qt.gtimg.cn/q=' + ','.join(tx_codes)
        raw = http(url, gbk=True, timeout=3)
        for line in raw.strip().split(';'):
            if '=' not in line:
                continue
            parts = line.split('"')[1].split('~')
            if len(parts) > 38 and parts[4] and parts[5]:
                c = parts[2]
                curr_p = float(parts[3])
                pct = float(parts[32]) if parts[32] else 0.0
                amt = float(parts[37]) if parts[37] else 0.0
                quote_map[c] = {
                    'price': curr_p,
                    'pct': pct,
                    'amount_str': f"{amt/1e4:.1f}亿" if amt >= 1e4 else f"{amt:.0f}万",
                }
    except Exception:
        pass
        
    stocks = []
    for s in matched['stocks']:
        item = dict(s)
        q = quote_map.get(s['code'], {})
        item['price'] = q.get('price', 0.0)
        item['pct'] = q.get('pct', 0.0)
        item['amount_str'] = q.get('amount_str', '-')
        stocks.append(item)
        
    return {
        'theme': matched['theme'],
        'sectors': matched['sectors'],
        'stocks': stocks,
    }

def get_branching_scenarios(scenario_text='', domain='', net_val=0):
    """次日集合竞价 9:25 高低开三套分叉树战术剧本 (超预期大幅高开 / 符合预期平开 / 不及预期低开)"""
    is_bull = net_val > 15
    is_bear = net_val < -15
    
    if is_bear:
        up_action = "【92科比逆势战术】若利空之下超预期大幅高开，通常为主力诱多或特大反抽。前排若无巨量一字锁死，切忌追高接盘！持仓者逢冲高分批减仓兑现，仅少量资金关注最强弱转强先锋。"
        flat_action = "【92科比防守战术】小幅平开说明多空博弈犹豫。开盘9:30-9:40严格观察承接力度，若开盘分时跌破分时均线且量能萎缩，果断逢高离场，不参与弱势轮动。"
        down_action = "【92科比冰点战术】大幅低开属预期内风险释放。开盘前10分钟不盲目无脑杀跌割肉，等待日内探底后的急速脉冲反抽；若反抽无法站上开盘价，顺势清仓/减仓至2成以下防守。"
    elif is_bull:
        up_action = "【92科比追强战术】超预期大幅高开说明情绪亢奋，多头抢筹！严禁追涨后排跟风（谨防大烂板），全神贯注盯紧同题材'竞价封单金额最大'的一字排单与'竞价量比>2.5'的首板龙头，果断排板或半路打板！"
        flat_action = "【92科比低吸战术】平开/小高开为极佳的上车分歧窗口。重点观察9:35第一波分时下探企稳节点，回踩分时均线不破且主力资金净买入时，从容低吸核心主线中军与高辨识度龙头。"
        down_action = "【92科比纠偏战术】若在利好预期下意外大幅低开，说明主力借利好大举砸盘或外盘拖累。观察9:30-9:35是否有国家队或机构托底大单逆势上攻，若无强力承接则警惕'利好出尽'，果断管住手观望。"
    else:
        up_action = "【92科比试盘战术】大幅高开先观察板块联动性，若仅为个股脉冲而板块无跟风，容易冲高回落被套；若带出板块效应，可在开盘回踩不破均线时轻仓参与前排。"
        flat_action = "【92科比常态战术】震荡平衡市，遵循'买在分歧、卖在一致'原则。日内不追高任何大阳线，精选均线多头回踩或形态突破个股做日内差价T+0。"
        down_action = "【92科比低吸防守】大幅低开杀跌释放短期分歧，急跌不割肉，观察前低支撑位。若缩量企稳可针对底仓做日内超跌低吸，午后拉高即T出。"

    return [
        {
            'type': 'up',
            'title': '剧本 A: 【超预期大幅高开】(竞价开盘 > +1.5%)',
            'trigger': '集合竞价多头爆量抢筹，高开幅度 > +1.5%，核心龙头大额一字封单',
            'market_logic': '多头资金达成强共识，风险偏好迅速升温，短线溢价拉满',
            'action': up_action,
            'badge': '积极进攻 / 龙头抢筹',
            'color': '#ff4d4f'
        },
        {
            'type': 'flat',
            'title': '剧本 B: 【符合预期平开/小高开】(竞价开盘 -0.5% ~ +1.5%)',
            'trigger': '竞价平稳波动在 -0.5% ~ +1.5% 区间，多空开盘基本平衡',
            'market_logic': '多空情绪自然延续，分歧在盘中逐步展开，以结构性轮动为主',
            'action': flat_action,
            'badge': '从容低吸 / 观察分歧',
            'color': '#fbbf24'
        },
        {
            'type': 'down',
            'title': '剧本 C: 【不及预期大幅低开】(竞价开盘 < -1.0%)',
            'trigger': '竞价大幅低开 < -1.0%，或者利好高开低走砸绿，竞价出现大额抛盘',
            'market_logic': '资金恐慌抢跑或预期落空，短线流动性承压，承接偏弱',
            'action': down_action,
            'badge': '防守控仓 / 谨慎反抽',
            'color': '#22c55e'
        }
    ]

def get_historical_review(scenario_text=''):
    """时光机复盘对账：匹配经典历史大事件并返回真实市场走势与九方表现对账"""
    if not scenario_text:
        return None
    txt = scenario_text.lower()
    for b in _HISTORICAL_BENCHMARKS:
        if b['key'] in txt or any(k in txt for k in b['title'].split()) or any(w in txt for w in ['924', '降准50bp', '3.45万亿', '10万亿', '雪球', '印花税减半']):
            if b['key'] in txt or ('924' in txt or '降准50' in txt and '2024-09-24' == b['key']) or ('3.45' in txt and '2024-10-08' == b['key']) or ('10万亿' in txt and '2024-11-08' == b['key']) or ('雪球' in txt and '2024-01-22' == b['key']) or ('印花税' in txt and '2023-08-27' == b['key']):
                return b
    return None

def sim_world(scenario=None, llm_impact=None, llm_note=''):
    w('')
    w('===== [世界模拟v2] 势力记忆+交互传染+情景注入 =====')
    if scenario:
        meta, _ = parse_event_scenario(scenario)
        w('【事件注入沙盘】: %s' % scenario)
        w('【事件智能研判】属性: %s | 逻辑: %s' % (meta['domain'], meta['desc']))
    try:
        stage = cycle_position()
    except Exception:
        stage = ''
    recs = []
    fp = os.path.join(DATA_DIR, 'sentiment_history.jsonl')
    if os.path.exists(fp):
        recs = [json.loads(l) for l in open(fp, encoding='utf-8') if l.strip()]
    if not recs:
        w('(无情绪存档)')
        return
    la = recs[-1]
    sc = float(la.get('score', 50)); zt = float(la.get('zt', 0))
    n_dt = float(la.get('dt', 0)); lb = float(la.get('max_lb', 0))
    zbrate = float(la.get('zb', 0)) / max(zt + float(la.get('zb', 1)), 1) * 100
    mgd = 0.0
    try:
        u = ('https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPTA_RZRQ_LSHJ'
             '&columns=DIM_DATE,RZRQYE&sortColumns=DIM_DATE&sortTypes=-1&pageSize=2&pageNumber=1')
        rows = json.loads(http(u))['result']['data']
        mgd = (float(rows[0]['RZRQYE']) - float(rows[1]['RZRQYE'])) / 1e8
    except Exception:
        pass
    cl = lambda v, lo, hi: max(lo, min(hi, v))
    ag = {}
    ag['散户'] = cl((sc - 45) * 3, -70, 85) * (0.5 if stage == '退潮' else 1) + (-20 if stage == '冰点' else 0)
    ag['游资'] = lb * 14 - zbrate * 1.2 + {'主升': 35, '亢奋': 10, '修复/震荡': 5, '退潮': -35, '冰点': -50}.get(stage, 0)
    ag['机构'] = cl((20 if mgd > 0 else -15 if mgd < 0 else 0) + (sc - 50) * 0.6, -40, 40)
    ag['团伙(控盘)'] = lb * 16 - zbrate * 0.8 + (10 if 40 <= zt <= 95 else 0) + (-25 if stage in ('退潮', '冰点') else 0)
    ag['国家队'] = (40 if (n_dt >= 10 or sc < 35) else (-20 if sc > 68 else 0)) + (20 if mgd < -100 else 0)
    # -- 大散户: 跟随情绪但更极端; 亢奋重仓/冰点割肉/退潮死扛(反应系数<1); 杠杆盘敏感 --
    ag['大散户'] = cl((sc - 45) * 2.5, -65, 90) * {'亢奋': 1.2, '主升': 1.1, '修复/震荡': 1.0, '退潮': 0.55, '冰点': 0.4}.get(stage, 1.0) + (-25 if stage == '冰点' else 0) + (15 if mgd > 50 else -20 if mgd < -80 else 0)
    # -- 北向: A50期指日内强弱代理(贴日高=风险偏好高) --
    pos = 0.0
    try:
        t = http('https://hq.sinajs.cn/list=hf_CHA50CFD', gbk=True,
                 referer='https://finance.sina.com.cn/')
        rw = {}
        for _m in re.finditer(r'hq_str_(\w+)="([^"]*)"', t):
            rw[_m.group(1)] = _m.group(2).split(',')
        def g2(k, i):
            v = rw.get(k, [])
            return v[i] if len(v) > i and v[i] else None
        px, hi_, lo_ = g2('hf_CHA50CFD', 0), g2('hf_CHA50CFD', 4), g2('hf_CHA50CFD', 5)
        if px and hi_ and lo_ and float(hi_) > float(lo_):
            pos = (float(px) - float(lo_)) / (float(hi_) - float(lo_)) * 2 - 1
    except Exception:
        pos = 0.0
    ag['北向'] = cl(pos * 25, -30, 30)
    # -- 量化: 炸板率高=打板策略亏损撤流动性; 高度打开=动量策略进场 --
    ag['量化'] = cl((zbrate - 20) * -1.5 + (lb - 3) * 5, -40, 40) + (10 if stage == '主升' else -10 if stage == '冰点' else 0)
    # -- 产业资本: 当日大宗交易加权折溢价(溢价=产业接盘意愿) --
    dz_net = 0.0
    dday = la.get('date', '')
    if len(dday) == 8:
        diso = '%s-%s-%s' % (dday[:4], dday[4:6], dday[6:])
        try:
            import urllib.parse as _up
            dp = {'reportName': 'RPT_BLOCKTRADE_STA',
                  'columns': 'PREMIUM_RATIO,DEAL_AMT,DISCOUNT_TIMES,PREMIUM_TIMES',
                  'filter': "(TRADE_DATE>='" + diso + "')(TRADE_DATE<='" + diso + "')",
                  'pageNumber': '1', 'pageSize': '500', 'sortTypes': '-1',
                  'sortColumns': 'TURNOVERRATE', 'source': 'WEB', 'client': 'WEB'}
            drows = json.loads(http('https://datacenter-web.eastmoney.com/api/data/v1/get?' + _up.urlencode(dp)))['result']['data'] or []
            amt = sum(float(x.get('DEAL_AMT') or 0) for x in drows)
            wsum = sum(float(x.get('DEAL_AMT') or 0) * float(x.get('PREMIUM_RATIO') or 0) for x in drows)
            wpr = wsum / amt * 100 if amt else 0.0
            premium = sum(int(x.get('PREMIUM_TIMES') or 0) for x in drows)
            disc = sum(int(x.get('DISCOUNT_TIMES') or 0) for x in drows)
            dz_net = cl(wpr * 8 + (1 if premium > disc else -1) * min(abs(premium - disc), 5) * 1.5, -25, 25)
            w('[大宗交易·%s] %d笔 %.1f亿 加权折溢%.2f%% (溢价%d笔/折价%d笔)' % (diso, len(drows), amt / 1e4, wpr, premium, disc))
        except Exception as e:
            w('[大宗交易失败] %s' % e)
    ag['产业资本'] = dz_net  # 基线中性, 大宗信号即立场
    # ①②③ 统一管道: 势力记忆锚定 + 情景注入 + 3轮传染
    ag, _ = _sim_pipeline(ag, scenario=scenario, use_memory=True,
                          cur_date=la.get('date', ''), verbose=True,
                          impact_override=llm_impact, impact_note=llm_note)
    net, net_pct = _weighted_net(ag)
    w('\n【九方势力博弈动作解析】')
    for n, ww in _AGENT_W:
        v = ag[n]
        arrow = '强力看多' if v > 30 else ('温和看多' if v > 10 else ('强力看空' if v < -30 else ('谨慎看空' if v < -10 else '中立观望')))
        act = _get_agent_action(n, v)
        w('  %-8s %+4.0f分 [%s] 动作: %s' % (n, v, arrow, act))
    w('  ---- 加权合力: %+.0f ----' % net)
    w('  ---- 加权合力: %+.0f (均值%+.1f/±100) ----' % (net, net_pct))
    path = ('修复反弹/主升强化: 多头合力占优，顺势做多' if net > 30 else
            '恐慌加速/风险释放: 严控仓位防守，规避高位承接风险' if net < -40 else
            '分歧震荡/结构轮动: 多空势均力敌，控制仓位做低吸做T')
    w('  >> 推演路径%s: %s' % (('('+scenario+')') if scenario else '', path))
    pos_advice = '7~9成高仓位（主线核心）' if net > 40 else ('5~7成中等仓位（分歧低吸）' if net > 10 else ('3~5成谨慎仓位（只做超跌）' if net > -25 else '0~2成极低仓位（空仓防守）'))
    attack_advice = '领涨题材核心龙头一字板/放量首板' if net > 25 else ('趋势中军回踩均线/超跌大市值反弹' if net > -15 else '避险高股息红利或离场观望')
    w('【次日92科比操盘战术】')
    w('  • 仓位指引: %s' % pos_advice)
    w('  • 进攻方向: %s' % attack_advice)

    # 核心受益与防守标的
    bene = get_event_beneficiary_stocks(scenario or '', meta.get('domain', '') if scenario else '', net)
    if bene and bene.get('stocks'):
        w('\n【核心受益/防守板块与标的池】: %s' % bene.get('theme', ''))
        w('  板块: %s' % ' / '.join(bene.get('sectors', [])))
        for st in bene['stocks']:
            w('  • %s %s [%s] 现价:%s (%+.2f%%) | %s' % (st['code'], st['name'], st['role'], st['price'] or '-', st['pct'], st['tag']))

    # 次日集合竞价分叉树三套战术
    branches = get_branching_scenarios(scenario or '', meta.get('domain', '') if scenario else '', net)
    w('\n【次日 9:25 集合竞价分叉树战术剧本】')
    for br in branches:
        w('  [%s] 触发条件: %s' % (br['title'], br['trigger']))
        w('    >> %s' % br['action'])

    # 历史时光机复盘对账
    hist_rev = get_historical_review(scenario or '')
    if hist_rev:
        w('\n【🕰️ 历史著名大事件·时光机复盘对账】')
        w('  基准事件: %s' % hist_rev['title'])
        w('  真实走势: %s' % hist_rev['real_market'])
        w('  势力对账: %s' % hist_rev['force_review'])

    if not scenario:  # 情景推演是假设, 不污染真实记忆
        _mem_save({'schema_version': 2, 'date': la.get('date', ''), 'stage': stage,
                   'stances': {k: round(v, 1) for k, v in ag.items()},
                   'net': round(net, 1), 'net_mean': round(net_pct, 1)})


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
        elif cmd == 'agents':
            agent_sim(sys.argv[2] if len(sys.argv) > 2 else None)
        elif cmd == 'sim':
            sim_world(sys.argv[2] if len(sys.argv) > 2 else None)
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
