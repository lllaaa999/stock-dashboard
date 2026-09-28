# -*- coding: utf-8 -*-
"""A股情绪周期选股器 v3 · 92科比体系
数据链路：
  1) 股票代码表：东财 clist（编号子域轮换 + 每日本地缓存）
  2) 实时快照：腾讯 qt.gtimg.cn（分批 600/次，不受东财限流影响）
  3) 候选 K 线：腾讯 fqkline（并发）
三种模式（参考92科比情绪周期）：
  低吸  —— 退潮/冰点/混沌期：龙头首阴、强势回踩均线、缩量企稳反包
  打板  —— 启动/发酵期：首板涨停、连板接力、换手板
  趋势  —— 高潮/主升期：均线多头排列、沿均线稳步上行、放量突破
"""
import sys, os, json, time, random, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'scripts'))
import stock_dashboard as sd

EM_HDRS = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.eastmoney.com/', 'Origin': 'https://www.eastmoney.com'}
UT = '7eea3edcaed734bea9cbfc24409ed989'
MAX_KLINE = 150
WORKERS = 16
CACHE = os.path.join(HERE, '..', 'data', 'stock_list.json')

PATTERNS = ['低吸', '打板', '趋势', '龙回头', '首阴反包', 'N字反包', '均线粘合', '地量反转', '缺口突破']


def _f(v):
    try:
        return float(str(v).replace('-', '0'))
    except Exception:
        return 0.0


def limit_pct(code):
    return 19.8 if code.startswith(('300', '301', '688')) else 9.8


def fetch_code_list(force=False):
    """东财 clist 全代码表，带编号子域轮换 + 重试；本地文件缓存优先"""
    if not force and os.path.exists(CACHE):
        try:
            cached = json.load(open(CACHE, encoding='utf-8'))
            if cached and len(cached) > 100:
                return cached
        except Exception:
            pass
    codes = []
    for pn in range(1, 60):
        host = f'{random.randint(1, 92)}.push2.eastmoney.com'
        u = (f'https://{host}/api/qt/clist/get?pn={pn}&pz=100&po=1&np=1&fltt=2&invt=2'
             '&fid=f12&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f12,f14,f26'
             f'&ut={UT}')
        got = None
        for attempt in range(3):
            try:
                j = json.loads(sd.http(u, headers=EM_HDRS))
                diff = (j.get('data') or {}).get('diff', []) or []
                got = diff
                break
            except Exception:
                time.sleep(0.5)
        if got is None:
            continue
        if not got:
            break
        for d in got:
            codes.append(dict(code=str(d.get('f12', '')), name=d.get('f14', ''),
                              listed=str(d.get('f26') or '')))
        time.sleep(0.15)
    if codes:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        json.dump(codes, open(CACHE, 'w', encoding='utf-8'), ensure_ascii=False)
    return codes


def tx_quotes(full_codes):
    """腾讯批量实时行情（含量比 f49）"""
    out = {}
    for i in range(0, len(full_codes), 600):
        batch = full_codes[i:i + 600]
        try:
            t = sd.http('https://qt.gtimg.cn/q=' + ','.join(batch), gbk=True)
            for line in t.split(';'):
                if '=' not in line:
                    continue
                f = line.split('"')[1].split('~')
                if len(f) > 49:
                    out[f[2]] = dict(code=f[2], name=f[1], price=_f(f[3]), pct=_f(f[32]),
                                     vol_ratio=_f(f[49]), amount=f[37] if len(f) > 37 else '')
        except Exception:
            pass
        time.sleep(0.1)
    return out


def prefilter(codes, quotes):
    """预筛：保留有涨停基因、异动、或趋势特征的候选"""
    out = []
    for c in codes:
        if 'ST' in c['name'].upper() or '退' in c['name']:
            continue
        if not c['listed'] or c['listed'] > '20260601':
            continue
        q = quotes.get(c['code'])
        if not q:
            continue
        lim = limit_pct(c['code'])
        # 打板候选：涨停/接近涨停/高量比
        # 低吸候选：下跌但未破位（-5%~0%）
        # 趋势候选：温和上涨（1%~7%）或高量比
        if (q['pct'] >= lim - 0.5 or q['pct'] >= 3 or q['vol_ratio'] >= 1.5
                or -5 <= q['pct'] < 0 or q['vol_ratio'] >= 1.2):
            out.append(dict(code=c['code'], name=c['name'], price=q['price'],
                            pct=q['pct'], vol_ratio=q['vol_ratio']))
    out.sort(key=lambda x: -max(abs(x['pct']), x['vol_ratio']))
    return out[:MAX_KLINE]


def fetch_kline(meta):
    full = ('sh' + meta['code']) if meta['code'].startswith(('6', '5', '9')) else ('sz' + meta['code'])
    try:
        kl = sd.kline_tx(full, 160)
        if kl and len(kl) >= 60:
            return meta, kl
    except Exception:
        pass
    return meta, None


def analyze(meta, kl):
    """92科比情绪周期三模式判定"""
    rows = kl
    closes = [r[2] for r in rows]
    highs = [r[3] for r in rows]
    lows = [r[4] for r in rows]
    vols = [r[5] for r in rows]
    c = closes[-1]
    lim = limit_pct(meta['code'])
    ma = lambda k: sum(closes[-k:]) / k if len(closes) >= k else 0
    ma5, ma10, ma20, ma60 = ma(5), ma(10), ma(20), ma(60)
    today_pct = meta['pct'] if meta['pct'] else (closes[-1] / closes[-2] - 1) * 100
    vol5 = sum(vols[-6:-1]) / 5 if len(vols) >= 6 else vols[-1]
    vol_ratio_today = vols[-1] / vol5 if vol5 else 1

    # 连板数统计
    lim_days = 0
    for i in range(len(closes) - 1, 0, -1):
        if (closes[i] / closes[i - 1] - 1) * 100 >= lim - 0.3:
            lim_days += 1
        else:
            break
    # 近10日涨停次数（涨停基因）
    lim_count_10 = sum(1 for i in range(max(1, len(closes)-10), len(closes))
                       if (closes[i] / closes[i-1] - 1) * 100 >= lim - 0.3)
    # 近20日涨停次数
    lim_count_20 = sum(1 for i in range(max(1, len(closes)-20), len(closes))
                       if (closes[i] / closes[i-1] - 1) * 100 >= lim - 0.3)

    res = {}

    # ========== 打板模式（启动/发酵期）==========
    # 首板：今日涨停，昨日未涨停
    if today_pct >= lim - 0.3 and lim_days == 1:
        prev_pct = (closes[-2] / closes[-3] - 1) * 100 if len(closes) > 2 else 0
        if prev_pct < lim - 0.3:
            tag = '首板涨停'
            if vol_ratio_today >= 1.5:
                tag += f'·放量{vol_ratio_today:.1f}倍'
            if lim_count_20 >= 2:
                tag += '·有涨停基因'
            res['打板'] = tag
    # 连板：2板及以上
    elif lim_days >= 2:
        tag = f'{lim_days}连板'
        # 判断是否换手板（非一字）
        if lows[-1] < highs[-1] * 0.98:
            tag += '·换手板'
        else:
            tag += '·一字板'
        if vol_ratio_today >= 1.2:
            tag += f'·量比{vol_ratio_today:.1f}'
        res['打板'] = tag
    # 准涨停（涨幅7%~涨停-0.3%），有冲板潜力
    elif lim - 3 <= today_pct < lim - 0.3 and vol_ratio_today >= 1.5:
        if lim_count_20 >= 1:
            res['打板'] = f'冲板候选·涨{today_pct:.1f}%·量比{vol_ratio_today:.1f}'

    # ========== 低吸模式（退潮/冰点/混沌期）==========
    # 1. 龙头首阴：前期连板后第一次收阴，回调到MA5附近
    if lim_days == 0 and today_pct < 0:
        # 检查前3天内是否有涨停
        had_limit_recent = any(
            (closes[i] / closes[i-1] - 1) * 100 >= lim - 0.3
            for i in range(len(closes)-2, max(0, len(closes)-5), -1)
        )
        if had_limit_recent and ma5 > 0:
            dist_ma5 = (c - ma5) / ma5 * 100
            if -3 <= dist_ma5 <= 2 and today_pct >= -6:
                res['低吸'] = f'龙头首阴·距MA5{dist_ma5:+.1f}%·前3日有涨停'

    # 2. 强势回踩：均线多头，回调到MA10/MA20不破，缩量
    if ma5 > ma10 > ma20 and ma20 > 0 and today_pct <= 1:
        dist_ma10 = (c - ma10) / ma10 * 100
        dist_ma20 = (c - ma20) / ma20 * 100
        if -2 <= dist_ma10 <= 2 and vol_ratio_today < 1.0:
            res['低吸'] = f'回踩MA10·缩量{vol_ratio_today:.1f}倍·均线多头'
        elif -2 <= dist_ma20 <= 3 and vol_ratio_today < 1.0 and ma10 > ma20:
            res['低吸'] = f'回踩MA20·缩量{vol_ratio_today:.1f}倍·均线多头'

    # 3. 缩量企稳：连续下跌后缩量止跌，前期有涨停基因
    if (today_pct >= -2 and today_pct <= 2 and vol_ratio_today < 0.8
            and lim_count_20 >= 1 and c > ma20 * 0.9):
        # 近5日有下跌
        recent_down = sum(1 for i in range(len(closes)-5, len(closes)-1)
                          if closes[i] < closes[i-1])
        if recent_down >= 2:
            res['低吸'] = f'缩量企稳·量比{vol_ratio_today:.1f}·近20日{lim_count_20}次涨停'

    # ========== 趋势模式（高潮/主升期）==========
    # 1. 均线多头排列 + 沿MA5上升
    if ma5 > ma10 > ma20 > ma60 and c > ma5 and ma60 > 0:
        # 沿均线上升：近10日收盘价大部分在MA5上方
        above_ma5 = sum(1 for i in range(len(closes)-10, len(closes))
                        if closes[i] > sum(closes[max(0,i-4):i+1]) / min(5, i+1))
        if above_ma5 >= 7:
            slope = (ma5 - sum(closes[-10:-5]) / 5) / ma5 * 100 if ma5 else 0
            res['趋势'] = f'均线多头·沿MA5上行·MA5斜率{slope:+.2f}%'

    # 2. 放量突破平台/前高
    if vol5 and vol_ratio_today >= 1.8 and c > max(highs[-21:-1]) and 2 <= today_pct <= 8:
        res['趋势'] = f'放量突破·量{vol_ratio_today:.1f}倍·破20日新高'

    # 3. 平台突破后回踩确认（趋势中继）
    hi20 = max(highs[-21:-1]) if len(highs) >= 21 else max(highs)
    if (c > hi20 * 0.97 and ma5 > ma10 > ma20
            and 0 <= today_pct <= 5 and vol_ratio_today < 1.5):
        if '趋势' not in res:
            res['趋势'] = f'突破后回踩确认·站稳20日高·均线多头'

    # ========== 龙回头（龙头回调后二次启动）==========
    # 近30日内有过连板或大涨，回调8-20日后今日放量上涨站回MA10
    if len(closes) >= 25 and today_pct >= 3 and vol_ratio_today >= 1.3 and c > ma10:
        # 找近30日内的最大涨幅（龙头启动信号）
        max_gain = 0
        peak_idx = 0
        for i in range(len(closes)-25, len(closes)-3):
            gain = (closes[i] / closes[i-1] - 1) * 100
            if gain > max_gain:
                max_gain = gain
                peak_idx = i
        # 有过涨停或接近涨停，且距今5-20日
        days_since_peak = len(closes) - 1 - peak_idx
        if max_gain >= lim - 1 and 5 <= days_since_peak <= 20:
            # 回调幅度：从峰值回撤10%-30%
            peak_price = closes[peak_idx]
            drawdown = (peak_price - min(lows[peak_idx:])) / peak_price * 100
            if 8 <= drawdown <= 35:
                res['龙回头'] = f'回调{drawdown:.0f}%后启动·距峰值{days_since_peak}日·量比{vol_ratio_today:.1f}'

    # ========== 首阴反包（涨停后首阴，次日反包）==========
    if len(closes) >= 4:
        day1_pct = (closes[-3] / closes[-4] - 1) * 100 if len(closes) > 3 else 0
        day2_pct = (closes[-2] / closes[-3] - 1) * 100
        # 前天涨停，昨天首阴（下跌），今天反包大阳
        if day1_pct >= lim - 0.3 and day2_pct < 0 and today_pct >= 5:
            if c >= closes[-3]:  # 反包吃掉阴线
                res['首阴反包'] = f'前日涨停·昨日首阴·今日反包{today_pct:.1f}%'
            elif today_pct >= 3:
                res['首阴反包'] = f'前日涨停·昨日首阴·今日反弹{today_pct:.1f}%'

    # ========== N字反包（涨停-调整-涨停，N字形）==========
    if len(closes) >= 8 and today_pct >= lim - 0.3:
        # 今日涨停，往前找前一个涨停，中间调整2-5天
        for gap in range(3, 7):
            if len(closes) <= gap + 1:
                continue
            prev_limit_pct = (closes[-gap-1] / closes[-gap-2] - 1) * 100 if len(closes) > gap + 1 else 0
            if prev_limit_pct >= lim - 0.3:
                # 中间调整期最大回撤
                adjust_high = max(highs[-gap:-1])
                adjust_low = min(lows[-gap:-1])
                pullback = (adjust_high - adjust_low) / adjust_high * 100
                if pullback >= 3:
                    res['N字反包'] = f'间隔{gap}日·调整{pullback:.0f}%·今日再涨停'
                break

    # ========== 均线粘合（MA5/MA10/MA20粘合后向上发散）==========
    if ma5 > 0 and ma10 > 0 and ma20 > 0:
        ma_max = max(ma5, ma10, ma20)
        ma_min = min(ma5, ma10, ma20)
        spread = (ma_max - ma_min) / ma_min * 100
        # 粘合度<3%，今日向上发散（涨幅>2%，MA5>MA10>MA20，放量）
        if spread < 3 and today_pct >= 2 and vol_ratio_today >= 1.2 and ma5 >= ma10 >= ma20:
            res['均线粘合'] = f'粘合度{spread:.1f}%·向上发散·量比{vol_ratio_today:.1f}'

    # ========== 地量反转（极度缩量后放量上涨）==========
    if len(vols) >= 20:
        min_vol_20 = min(vols[-20:-1])
        # 近3日内有地量（创20日新低），今日放量上涨
        if min(vols[-4:-1]) <= min_vol_20 * 1.1 and today_pct >= 3 and vol_ratio_today >= 1.5:
            res['地量反转'] = f'地量后放量·量比{vol_ratio_today:.1f}·涨{today_pct:.1f}%'

    # ========== 缺口突破（跳空缺口突破前高）==========
    if len(closes) >= 3:
        gap_pct = (lows[-1] - highs[-2]) / highs[-2] * 100
        # 跳空缺口>1%，放量，突破20日高点
        if gap_pct >= 1 and vol_ratio_today >= 1.5 and c > max(highs[-21:-1]):
            res['缺口突破'] = f'跳空{gap_pct:.1f}%·破20日高·量比{vol_ratio_today:.1f}'

    return res


def run(only=None):
    print('获取股票代码表...')
    codes = fetch_code_list()
    if not codes:
        return {p: [] for p in PATTERNS}
    print(f'代码表 {len(codes)} 只, 拉实时快照(腾讯)...')
    full = [('sh' + c['code']) if c['code'].startswith(('6', '5', '9')) else ('sz' + c['code']) for c in codes]
    quotes = tx_quotes(full)
    print(f'实时行情 {len(quotes)} 只, 预筛候选...')
    cands = prefilter(codes, quotes)
    print(f'候选 {len(cands)} 只, 并发拉K线({WORKERS}线程)...')
    klines = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(fetch_kline, m): m for m in cands}
        for fu in as_completed(futs):
            m, kl = fu.result()
            if kl:
                klines[m['code']] = (m, kl)
    print(f'K线就绪 {len(klines)} 只, 情绪周期选股判定...')
    result = {p: [] for p in PATTERNS}
    for code, (m, kl) in klines.items():
        for p, note in analyze(m, kl).items():
            if p in result:
                result[p].append(dict(code=m['code'], name=m['name'], price=m['price'],
                                      pct=m['pct'], vol_ratio=m['vol_ratio'], note=note))
    # 排序：打板/趋势/龙回头/首阴反包/N字反包/地量反转/缺口突破按涨幅降序，低吸按涨幅升序，均线粘合按涨幅降序
    for p in ['打板', '趋势', '龙回头', '首阴反包', 'N字反包', '均线粘合', '地量反转', '缺口突破']:
        result[p].sort(key=lambda x: -x['pct'])
    result['低吸'].sort(key=lambda x: x['pct'])
    if only:
        return {only: result.get(only, [])}
    return result


if __name__ == '__main__':
    sys.stdout = __import__('io').TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    only = sys.argv[1] if len(sys.argv) > 1 else None
    t0 = datetime.datetime.now()
    r = run(only)
    for p, lst in r.items():
        print(f'\n===== {p}: {len(lst)} 只 =====')
        for x in lst[:20]:
            print(f"  {x['code']} {x['name']} {x['price']} ({x['pct']:+.2f}%) {x['note']}")
    print(f'\n耗时 {datetime.datetime.now() - t0}')
