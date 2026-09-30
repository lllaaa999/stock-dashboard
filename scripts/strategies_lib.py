# -*- coding: utf-8 -*-
"""
strategies_lib.py - 选股策略库 v2 (2026-08-25 与 DeepSeek 会诊定稿, 详见 收集策略会诊/)
12策略中的8个已量化落地(E-L), A-D在 stock_dashboard.screener, M=情绪总开关内置。
每策略标注适用阶段, screener2 按 cycle_position 自动启停。
"""
import sys, os, json, datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stock_dashboard as sd

w = sd.w

def _num(v):
    return v if isinstance(v, (int, float)) else 0

# ---------- 全市场快照(pz上限100实测, 56页翻完, 进程内缓存) ----------
_SNAP = None
_BYCODE = None
_FIELDS = 'f12,f14,f26,f2,f3,f6,f8,f10,f15,f16,f17,f18,f21,f31,f62,f66,f100,f164,f24'

_SNAP_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'snapshot_cache.json')

def _snapshot_from_tencent():
    """根据当前网络环境：腾讯接口极速稳定（0.3s），作为全市场行情兜底"""
    codes_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'stock_list.json')
    if not os.path.exists(codes_path):
        return []
    try:
        with open(codes_path, encoding='utf-8') as f:
            raw_codes = json.load(f)
            codes = [s['code'] for s in raw_codes if str(s.get('code','')).startswith(('60', '688', '00', '30'))]
    except Exception:
        return []

    rows = []
    for i in range(0, len(codes), 600):
        batch = [('sh' + c if c.startswith(('6', '5', '9')) else 'sz' + c) for c in codes[i:i+600]]
        u = 'https://qt.gtimg.cn/q=' + ','.join(batch)
        try:
            raw = sd.http(u, gbk=True, timeout=5)
            for line in raw.split(';'):
                if '=' not in line:
                    continue
                parts = line.split('"')[1].split('~')
                if len(parts) > 40:
                    c = parts[2]
                    p = float(parts[3]) if parts[3] else 0.0
                    pct = float(parts[32]) if parts[32] else 0.0
                    amt = float(parts[37]) * 10000 if parts[37] else 0.0
                    hs = float(parts[38]) if parts[38] else 0.0
                    ltsz = float(parts[45]) * 1e8 if len(parts) > 45 and parts[45] else 0.0
                    rows.append({
                        'f12': c, 'f14': parts[1], 'f2': p, 'f3': pct, 'f6': amt,
                        'f8': hs, 'f10': float(parts[49]) if len(parts) > 49 and parts[49] else 1.0,
                        'f15': float(parts[33]) if parts[33] else 0.0,
                        'f16': float(parts[34]) if parts[34] else 0.0,
                        'f18': float(parts[4]) if parts[4] else 0.0,
                        'f21': ltsz, 'f62': 0.0, 'f100': 'A股',
                    })
        except Exception:
            pass
    return rows

def snapshot(force=False):
    global _SNAP, _BYCODE
    if _SNAP is not None and not force:
        return _SNAP

    # 1. 优先读取近4小时内的本地磁盘快照缓存，避免频繁全市场60页扫描
    if not force and os.path.exists(_SNAP_CACHE_PATH):
        try:
            if _time.time() - os.path.getmtime(_SNAP_CACHE_PATH) < 4 * 3600:
                with open(_SNAP_CACHE_PATH, 'r', encoding='utf-8') as f:
                    _SNAP = json.load(f)
                    if _SNAP:
                        _BYCODE = {r.get('f12'): r for r in _SNAP}
                        return _SNAP
        except Exception:
            pass

    rows, seen = [], set()
    hosts = ['https://push2.eastmoney.com', 'https://push2delay.eastmoney.com', 'https://48.push2.eastmoney.com']

    def _is_cb_open(h):
        if hasattr(sd, '_cb_is_open'):
            try:
                return sd._cb_is_open(h)
            except Exception:
                pass
        blackout = getattr(sd, '_HOST_BLACKOUT', {})
        clean_h = h.replace('https://', '').replace('http://', '').split('/')[0]
        return blackout.get(clean_h, 0) > time.time()

    # 智能熔断快速失败：若东财主机处于熔断冷却中，立即跳过网络轮询，零等待回退
    if any(_is_cb_open(h) for h in hosts):
        hosts = []
    try:
        for pn in range(1, 60):
            urls = [h + ('/api/qt/clist/get?pn=%d&pz=100&po=1&np=1&fltt=2&fid=f6'
                         '&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=%s' % (pn, _FIELDS)) for h in hosts]
            j = json.loads(sd._get_first_ok(urls, retries=2))
            d = j.get('data') or {}
            diff = d.get('diff') or []
            if not diff:
                break
            for r in diff:
                c = r.get('f12')
                if c and c not in seen:
                    seen.add(c)
                    rows.append(r)
            if len(rows) >= int(d.get('total') or 0):
                break
    except Exception as e:
        w(f'[快照网络提示] 东财接口响应异常: {e}')

    # 2. 如果东财网络受限，自动启用腾讯行情源秒级兜底
    if not rows and os.path.exists(_SNAP_CACHE_PATH):
        try:
            with open(_SNAP_CACHE_PATH, 'r', encoding='utf-8') as f:
                rows = json.load(f)
        except Exception:
            pass

    if not rows:
        w('[网络自适应] 启用腾讯高频实时行情秒级兜底...')
        rows = _snapshot_from_tencent()

    if rows:
        _SNAP = rows
        _BYCODE = {r.get('f12'): r for r in rows}
        try:
            with open(_SNAP_CACHE_PATH, 'w', encoding='utf-8') as f:
                json.dump(rows, f, ensure_ascii=False)
        except Exception:
            pass

    if _SNAP is None:
        _SNAP = []
        _BYCODE = {}
    return _SNAP

def by_code():
    snapshot()
    return _BYCODE or {}

# ---------- 通用硬过滤(dsh会诊全局约定) ----------
def hard_ok(r):
    """ST/退市/北交所/次新<60日/股价<2元/成交额<5000万 一票否决"""
    name = str(r.get('f14') or '')
    if 'ST' in name.upper() or '退' in name:
        return False
    code = str(r.get('f12') or '')
    # 剔除北交所股票(8/4/920开头)及非标准代码
    if code.startswith(('8', '4', '920')):
        return False
    f26 = r.get('f26')
    if isinstance(f26, int) and f26 > 19000000:
        try:
            if (dt.date.today() - dt.date(f26 // 10000, f26 // 100 % 100, f26 % 100)).days < 60:
                return False
        except ValueError:
            pass
    if _num(r.get('f2')) < 2.0 or _num(r.get('f6')) < 5e7:
        return False
    return True

def universe():
    return [r for r in snapshot() if hard_ok(r)]

def zt_pct_limit(code):
    """涨停判定阈值(%), ST已被硬剔除"""
    return 19.5 if str(code).startswith(('300', '301', '688')) else 9.8

# ---------- K线缓存 [date,open,close,high,low,vol] ----------
_KL = {}
_KL_FAIL = set()
import time as _time
_last_kl_ts = [0.0]

def _kline_em(code, days=90):
    """东财K线备用源(腾讯WAF限流时兜底): 返回与kline_tx同构 [date,o,c,h,l,vol]"""
    mkt = '1' if str(code).startswith(('6', '5', '9')) else '0'
    u = ('https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=%s.%s'
         '&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56&klt=101&fqt=1&end=20500101&lmt=%d'
         % (mkt, code, days))
    try:
        j = json.loads(sd._get_first_ok([u], retries=2))
        rows = ((j.get('data') or {}).get('klines')) or []
        out = []
        for s in rows:
            p = s.split(',')
            out.append([p[0], float(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[5])])
        return out
    except Exception:
        return []

def _kline_tx_alt(full_code, days):
    """腾讯备用域名(web.ifzq被WAF间歇拦截, ifzq实测可用 —— dsh二轮实证)"""
    u = 'https://ifzq.gtimg.cn/appstock/app/fqkline/get?param=%s,day,,,%d,qfq' % (full_code, days)
    try:
        j = json.loads(sd.http(u))
        node = j.get('data', {}).get(full_code, {})
        rows = node.get('qfqday') or node.get('day') or []
        return [[r[0]] + [float(x) for x in r[1:5]] + [float(r[5])] for r in rows]
    except Exception:
        return []

def get_kl(code, days=170):
    """三源链(tx主域→tx备域→东财)+轻量节流; 单股失败平滑降级，不触发全局阻断。
    默认170天保G策略160日回撤口径"""
    code_str = str(code).strip()
    if code_str in _KL:
        return _KL[code_str]
    if code_str.startswith(('8', '4', '920')):
        return []
    if _time.time() - _last_kl_ts[0] < 0.08:
        _time.sleep(max(0.0, 0.08 - (_time.time() - _last_kl_ts[0])))
    kl = []
    full = ('sh' + code_str) if code_str.startswith(('6', '5', '9')) else ('sz' + code_str)
    # 1. 优先腾讯主接口
    try:
        kl = sd.kline_tx(full, days)
    except Exception:
        kl = []
    # 2. 腾讯备用源
    if not kl:
        try:
            kl = _kline_tx_alt(full, days)
        except Exception:
            kl = []
    # 3. 东财源兜底
    if not kl:
        try:
            kl = _kline_em(code_str, days)
        except Exception:
            kl = []

    _last_kl_ts[0] = _time.time()
    if kl:
        _KL[code_str] = kl
        _KL_FAIL.discard(code_str)
    elif code_str not in _KL_FAIL:
        _KL_FAIL.add(code_str)
    return kl

def _pct(row, prev):
    pc = prev[2]
    return (row[2] - pc) / pc * 100 if pc else 0.0

def _amt(row):
    """成交额(元) = 量(手)*100*收盘价 —— dsh二轮评审实证: 腾讯K线vol单位是手"""
    return row[5] * row[2] * 100

# ---------- 三池同日回溯 ----------
def pools_recent(maxback=8):
    base = dt.date.today()
    for i in range(maxback):
        ymd = (base - dt.timedelta(days=i)).strftime('%Y%m%d')
        zt = sd._pool('ZT', ymd)
        if zt:
            return ymd, zt, sd._pool('ZB', ymd), sd._pool('DT', ymd)
    return None, [], [], []

def _sector_f164():
    """板块5日主力净流入{名称:金额}, 单页TOP100降序, 不在表内视为<=0"""
    try:
        hosts = ['https://push2.eastmoney.com',
                 'https://push2delay.eastmoney.com',
                 'https://48.push2.eastmoney.com']
        urls = [h + '/api/qt/clist/get?pn=1&pz=100&po=1&np=1&fltt=2&fid=f164&fs=m:90+t:2&fields=f14,f164' for h in hosts]
        j = json.loads(sd._get_first_ok(urls, retries=2))
        return {r.get('f14'): _num(r.get('f164')) for r in (j.get('data') or {}).get('diff') or []}
    except Exception:
        return {}

# ================= E. 低位首板挖掘 (适用: 冰点末/修复) =================
def scr_first_board(zt):
    """首板+早封+零炸+封单比>=1.5%+小盘<=80亿; 按涨停质量分排序(同分看封单占比)"""
    out = []
    for x in zt:
        try:
            if int(x.get('lbc', 1)) != 1:
                continue
        except Exception:
            continue
        fbt = str(int(x.get('fbt', 0)) ).zfill(6)
        if fbt > '100000' or int(x.get('zbc', 0)) != 0:
            continue
        ltsz = _num(x.get('ltsz'))
        if ltsz <= 0 or ltsz > 80e8:
            continue
        ratio = _num(x.get('fund')) / ltsz * 100
        if ratio < 1.5:
            continue
        r = by_code().get(x.get('c')) or {}
        amt = _num(r.get('f6')) or _num(x.get('amount'))
        if amt < 1e8:
            continue
        q, _qd = sd.limit_up_quality(x)
        x['qlty'] = q                       # 带出去给 CLI/Web/Agent 复用(2026-09-30 P2-⑤)
        out.append((q, ratio, x, fbt, amt))
    out.sort(key=lambda t: (-t[0], -t[1]))
    for q, ratio, x, fbt, amt in out[:10]:
        w('%s %-6s [%s] 质量%.1f 首封%s 封单%.1f亿(占流通%.1f%%) 流通%.0f亿 额%.1f亿' % (
            x.get('c'), x.get('n'), x.get('hybk', '-'), q,
            fbt[:2] + ':' + fbt[2:4], _num(x.get('fund')) / 1e8, ratio,
            _num(x.get('ltsz')) / 1e8, amt / 1e8))
    return out

# ================= F. 断板反包 (适用: 修复/主升; 退潮禁用) =================
def scr_break_rebound(zt):
    """涨停-断板-涨停 结构, K线复核断板日承接, 反包日早封"""
    out = []
    for x in zt:
        code = x.get('c')
        try:
            if int(x.get('lbc', 1)) != 1:
                continue
        except Exception:
            continue
        kl = get_kl(code)
        if len(kl) < 4:
            continue
        t, t1, t2 = kl[-1], kl[-2], kl[-3]
        lim = zt_pct_limit(code)
        p2 = _pct(t2, kl[-4])
        if p2 < lim - 0.5 or _pct(t1, t2) >= lim - 0.5 or _pct(t, t1) < lim - 0.5:
            continue
        pct_t1 = _pct(t1, t2)
        if pct_t1 < -6.0:
            continue
        a1, a2 = _amt(t1), _amt(t2)
        if a2 <= 0 or a1 < 0.8 * a2:
            continue
        if t1[4] < t2[2] * 0.92:
            continue
        fbt = str(int(x.get('fbt', 0))).zfill(6)
        if fbt > '103000' or int(x.get('zbc', 0)) > 1:
            continue
        r = by_code().get(code) or {}
        if _num(r.get('f62')) <= 0:
            continue
        q, _qd = sd.limit_up_quality(x)
        x['qlty'] = q
        score = -pct_t1 + (10 if fbt <= '100000' else 0) + min(_num(r.get('f62')) / 1e8, 5)
        out.append((q, score, code, x, pct_t1, fbt))
    out.sort(key=lambda t: (-t[0], -t[1]))
    for q, sc, code, x, pct_t1, fbt in out[:8]:
        w('%s %-6s [%s] 质量%.1f T-1断板%+.1f%%后今反包 首封%s 炸%d 主力净入%+.1f亿' % (
            code, x.get('n'), x.get('hybk', '-'), q, pct_t1,
            fbt[:2] + ':' + fbt[2:4], x.get('zbc', 0),
            _num((by_code().get(code) or {}).get('f62')) / 1e8))
    return out

# ================= G. 超跌反弹 (适用: 冰点/退潮末段) =================
def scr_oversold(univ):
    """距160日高回撤>=40%, 近3日放量止跌, 当日2~6%启动, 主力转正"""
    out = []
    for r in univ:
        # 廉价预筛(快照字段): 60日跌幅<=-25%粗滤深跌 + 当日启动带 + 资金换手
        if _num(r.get('f24')) > -25.0:
            continue
        f3 = _num(r.get('f3'))
        if not (2.0 <= f3 <= 6.0 and _num(r.get('f62')) > 0 and 5.0 <= _num(r.get('f8')) <= 25.0):
            continue
        code = r.get('f12')
        kl = get_kl(code)
        if len(kl) < 30:
            continue
        hi160 = max(row[3] for row in kl[-160:])
        close = kl[-1][2]
        if hi160 <= 0 or (hi160 - close) / hi160 < 0.40:
            continue
        stop = False
        for row, prev in zip(kl[-3:], kl[-4:]):
            pv = prev[5]
            if _pct(row, prev) >= 3.0 and pv > 0 and row[5] >= 1.5 * sum(x[5] for x in kl[-8:-4]) / 4:
                stop = True
                break
        if not stop:
            continue
        out.append(((hi160 - close) / hi160 * 100, r))
    out.sort(key=lambda t: -t[0])
    for dd, r in out[:12]:
        w('%s %-6s [%s] 价%.2f %+.2f%% 距160日高-%.0f%% 换手%.1f%% 主力净入%+.1f亿' % (
            r.get('f12'), r.get('f14'), r.get('f100', '-'), _num(r.get('f2')),
            _num(r.get('f3')), dd, _num(r.get('f8')), _num(r.get('f62')) / 1e8))
    return out

# ================= H. N字反包 (适用: 修复/主升) =================
def scr_n_shape(zt):
    """涨停-缩量浅回踩-再放量涨停, 低位1~2板位置"""
    out = []
    for x in zt:
        code = x.get('c')
        try:
            lbc = int(x.get('lbc', 1))
        except Exception:
            continue
        if lbc > 2:
            continue
        kl = get_kl(code)
        if len(kl) < 4:
            continue
        t, t1, t2 = kl[-1], kl[-2], kl[-3]
        lim = zt_pct_limit(code)
        if _pct(t2, kl[-4]) < lim - 0.5 or _pct(t1, t2) >= lim - 0.5 or _pct(t, t1) < lim - 0.5:
            continue
        pct_t1 = _pct(t1, t2)
        if not (-8.0 <= pct_t1 <= 0.0):
            continue
        if t1[4] < t2[2] * 0.90:
            continue
        if t2[5] <= 0 or t1[5] > 0.7 * t2[5]:
            continue
        if t[5] < 1.5 * max(t1[5], 1):
            continue
        fbt = str(int(x.get('fbt', 0))).zfill(6)
        if fbt > '103000' or int(x.get('zbc', 0)) > 1:
            continue
        r = by_code().get(code) or {}
        if _num(r.get('f10')) < 2.0:
            continue
        q, _qd = sd.limit_up_quality(x)
        x['qlty'] = q
        score = -pct_t1 + (t2[5] / max(t1[5], 1)) + min(_num(r.get('f10')), 10) * 0.5
        out.append((q, score, code, x, pct_t1, fbt))
    out.sort(key=lambda t: (-t[0], -t[1]))
    for q, sc, code, x, pct_t1, fbt in out[:8]:
        w('%s %-6s [%s] 质量%.1f %d板N字 T-1回调%+.1f%%今反包 首封%s' % (
            code, x.get('n'), x.get('hybk', '-'), q, int(x.get('lbc', 1)),
            pct_t1, fbt[:2] + ':' + fbt[2:4]))
    return out

# ================= I. 均线趋势加速 (适用: 主升/亢奋) =================
def scr_trend_accel(univ):
    """多头排列+MA5三连升+放量加速未涨停, 近20日有涨停基因"""
    out = []
    for r in univ:
        code = r.get('f12')
        f3 = _num(r.get('f3'))
        if not (5.0 <= f3 < zt_pct_limit(code) - 0.5):
            continue
        if _num(r.get('f62')) <= 0 or _num(r.get('f6')) < 5e8:
            continue
        if _num(r.get('f24')) <= 5.0 or not (2.0 <= _num(r.get('f8')) <= 30.0):
            continue
        kl = get_kl(code)
        if len(kl) < 25:
            continue
        closes = [row[2] for row in kl]
        vols = [row[5] for row in kl]
        ma5 = sum(closes[-5:]) / 5.0
        ma10 = sum(closes[-10:]) / 10.0
        ma20 = sum(closes[-20:]) / 20.0
        if not (ma5 > ma10 > ma20 and closes[-1] > ma5):
            continue
        ma5s = [sum(closes[-(5 + i):len(closes) - i]) / 5.0 for i in range(4)]
        if not all(ma5s[i] > ma5s[i + 1] for i in range(3)):
            continue
        vma5 = sum(vols[-6:-1]) / 5.0
        if vma5 <= 0 or vols[-1] < 1.2 * vma5:
            continue
        lim = zt_pct_limit(code)
        if not any(_pct(kl[i], kl[i - 1]) >= lim - 0.5 for i in range(len(kl) - 20, len(kl))):
            continue
        score = f3 * 2 + min(vols[-1] / vma5, 3)
        out.append((score, r))
    out.sort(key=lambda t: -t[0])
    for sc, r in out[:12]:
        w('%s %-6s [%s] %+.2f%% 额%.1f亿 换手%.1f%% 主力净入%+.1f亿' % (
            r.get('f12'), r.get('f14'), r.get('f100', '-'), _num(r.get('f3')),
            _num(r.get('f6')) / 1e8, _num(r.get('f8')), _num(r.get('f62')) / 1e8))
    return out

# ================= J. 板块梯队完整性+中军低吸 (适用: 修复末/主升) =================
def scr_sector_ladder(zt, zb):
    """按hybk聚合: 涨停>=3+高标+龙头封单比>=1%+炸板<=2+板块5日净流入>0; 另选中军"""
    sectors = {}
    for x in zt:
        sectors.setdefault(x.get('hybk') or '-', []).append(x)
    zb_cnt = {}
    for b in zb:
        k = b.get('hybk') or '-'
        zb_cnt[k] = zb_cnt.get(k, 0) + 1
    f164map = _sector_f164()
    good = {}
    for sec, xs in sectors.items():
        lbcs = []
        for x in xs:
            try:
                lbcs.append(int(x.get('lbc', 1)))
            except Exception:
                continue
        if len(xs) < 3 or not lbcs:
            continue
        if max(lbcs) < 2 or 1 not in lbcs:
            continue
        lead = max(xs, key=lambda y: _num(y.get('lbc', 1)))
        if _num(lead.get('fund')) / max(_num(lead.get('ltsz')), 1) * 100 < 1.0:
            continue
        if zb_cnt.get(sec, 0) > 2 or f164map.get(sec, -1) <= 0:
            continue
        big = False
        bc = by_code()
        for x in xs:
            rr = bc.get(x.get('c')) or {}
            if _num(rr.get('f21')) >= 100e8 and _num(rr.get('f6')) >= 8e8 and _num(rr.get('f3')) > 0:
                big = True
                break
        if big:
            good[sec] = (xs, lead)
    w('-- 梯队成立板块 --')
    for sec, (xs, lead) in sorted(good.items(), key=lambda kv: -len(kv[1][0])):
        w('[%s] 涨停%d家 高标%s%d板 炸板%d 板块5日净入%.1f亿' % (
            sec, len(xs), lead.get('n'), int(lead.get('lbc', 1)),
            zb_cnt.get(sec, 0), f164map.get(sec, 0) / 1e8))
    w('-- 中军候选(梯队板块内 30~300亿/额>10亿/+3~7%/主力净入) --')
    bc = by_code()
    mids = []
    seen_sec = set(good)
    for r in snapshot():
        sec = r.get('f100', '-')
        if sec not in seen_sec or not hard_ok(r):
            continue
        ltsz = _num(r.get('f21'))
        if not (30e8 <= ltsz <= 300e8 and _num(r.get('f6')) >= 10e8):
            continue
        f3 = _num(r.get('f3'))
        if not (3.0 <= f3 <= 7.0 and _num(r.get('f62')) > 0):
            continue
        mids.append((_num(r.get('f62')) / max(ltsz, 1) * 100, r))
    mids.sort(key=lambda t: -t[0])
    for ratio, r in mids[:8]:
        w('%s %-6s [%s] %+.2f%% 额%.1f亿 流通%.0f亿 占流通%.1f%%' % (
            r.get('f12'), r.get('f14'), r.get('f100', '-'), _num(r.get('f3')),
            _num(r.get('f6')) / 1e8, _num(r.get('f21')) / 1e8, ratio))
    return good, mids

# ================= K. 跌停撬板/准地天板 (适用: 退潮末/冰点) =================
def scr_lift_board(dt_pool_today, univ):
    """当日曾进跌停池+收盘拉红>=3%+振幅>=16%+放量+主力净入"""
    out = []
    bc = by_code()
    for x in dt_pool_today:
        code = x.get('c')
        r = bc.get(code)
        if not r:
            continue
        f3 = _num(r.get('f3'))
        if f3 < 3.0:
            continue
        hi, lo = _num(r.get('f15')), _num(r.get('f16'))
        prev = _num(r.get('f18'))
        if prev <= 0 or lo <= 0 or (hi - lo) / prev < 0.16:
            continue
        if _num(r.get('f6')) < 1.5e8 or _num(r.get('f8')) < 5.0 or _num(r.get('f62')) <= 0:
            continue
        kl = get_kl(code)
        if len(kl) >= 2 and _pct(kl[-1], kl[-2]) >= zt_pct_limit(code) - 0.5:
            continue
        oc = x.get('oc', 0)
        score = f3 + (hi - lo) / prev * 100 + int(oc or 0) * 2
        out.append((score, code, r, oc))
    out.sort(key=lambda t: -t[0])
    for sc, code, r, oc in out[:10]:
        w('%s %-6s [%s] %+.2f%% 开板%d次 振幅达标 换手%.1f%% 额%.1f亿 主力净入%+.1f亿' % (
            code, r.get('f14'), r.get('f100', '-'), _num(r.get('f3')),
            int(oc or 0), _num(r.get('f8')), _num(r.get('f6')) / 1e8,
            _num(r.get('f62')) / 1e8))
    return out

# ================= L. 龙虎榜游资接力 (适用: 主升/亢奋; T+1注意) =================
def scr_yz_relay(zt):
    """连板>=2上榜+游资净买+机构不接盘+量化占比<30%+买一>=3000万"""
    import urllib.parse
    ymd = None
    base = dt.date.today()
    if dt.datetime.now().hour < 17:
        base = base - dt.timedelta(days=1)  # 榜单盘后才披露, 17点前查当日必空(dsh二轮)
    for i in range(8):
        d = base - dt.timedelta(days=i)
        if d.weekday() < 5:
            ymd = d.strftime('%Y-%m-%d')
            break
    if not ymd:
        return []
    out = []
    lbc_map = {x.get('c'): int(x.get('lbc', 1)) for x in zt}
    for code, lbc in sorted(lbc_map.items(), key=lambda kv: -kv[1]):
        if lbc < 2:
            continue
        try:
            rb = sd._lhb_detail(code, ymd, 'B')
            rs = sd._lhb_detail(code, ymd, 'S')
        except Exception:
            continue
        if not rb:
            continue
        buy_total = sum(sd._num(x.get('BUY')) for x in rb)
        sell_total = sum(sd._num(x.get('SELL')) for x in rs)
        if buy_total - sell_total <= 0:
            continue
        agg = {}
        for flag, rows in (('B', rb), ('S', rs)):
            for xx in rows:
                c = sd._seat_class(xx.get('OPERATEDEPT_NAME') or '?')
                a = agg.setdefault(c, [0.0, 0.0])
                a[0 if flag == 'B' else 1] += sd._num(xx.get('BUY') if flag == 'B' else xx.get('SELL'))
        b_inst = sum(v[0] for k, v in agg.items() if k in ('机构', '北向'))
        s_inst = sum(v[1] for k, v in agg.items() if k in ('机构', '北向'))
        yz_buy = sum(v[0] for k, v in agg.items() if k == '知名游资')
        q_buy = sum(v[0] for k, v in agg.items() if k == '量化')
        top1 = max((sd._num(x.get('BUY')) for x in rb), default=0)
        if not (yz_buy > 0 and s_inst > b_inst and q_buy / max(buy_total, 1) < 0.30 and top1 >= 3000e4):
            continue
        nm = ((by_code().get(code) or {}).get('f14')) or code
        out.append((buy_total - sell_total, code, nm, lbc))
        w('%s %-6s %d板 榜单净买%+.2f亿 游资买%.2f亿 机构净%+.2f亿 量化占%.0f%% 买一%.0f万' % (
            code, nm, lbc, (buy_total - sell_total) / 1e8, yz_buy / 1e8,
            (b_inst - s_inst) / 1e8, q_buy / max(buy_total, 1) * 100, top1 / 1e4))
        if len(out) >= 6:
            break
    if not out:
        w('(无符合条件的游资接力票)')
    return out

# ================= M. 情绪周期总开关 (前置风控, 定义所有阶段) =================
def regime_gate():
    """返回(stage, advice, allow_set)。allow_set=当前可启用策略集合"""
    stage = sd.cycle_position()
    recs = []
    try:
        fp = os.path.join(sd.DATA_DIR, 'sentiment_history.jsonl')
        with open(fp, encoding='utf-8') as f:
            recs = [json.loads(ln) for ln in f if ln.strip()]
    except Exception:
        pass
    last = recs[-1] if recs else {}
    up, down = int(last.get('zt') or 0), int(last.get('dt') or 0)
    zb, mx = int(last.get('zb') or 0), int(last.get('max_lb') or last.get('maxlb') or 0)
    br = zb / max(up + zb, 1)
    # 以92科比周期引擎(stage)为主判定 —— 2026-08-25实跑教训: 原始阈值在退潮修复日
    # 会误判成主升(涨停65/炸板25%/高度5板全达标), 放行进攻策略是方向性错误
    _MAP = {
        '冰点': ('冰点档: 仅超跌反弹/撬板试探, 半仓内', {'G', 'K'}),
        '修复': ('修复档: 首板/反包类优先', {'E', 'F', 'H'}),
        '修复/震荡': ('修复档(引擎原话): 首板/反包类优先', {'E', 'F', 'H'}),
        '主升': ('主升档: 全策略开启', {'E', 'F', 'H', 'I', 'J', 'L'}),
        '亢奋': ('亢奋档: 仅龙头/趋势加速, 减仓兑现为主', {'I', 'L'}),
        '退潮': ('退潮档: 空仓观望, 仅超跌/撬板跟踪', {'G', 'K'}),
    }
    advice, allow = _MAP.get(stage, (None, None))
    if not advice:  # 引擎无结论时才用原始阈值兜底
        if up < 25 or mx <= 1 or br >= 0.45 or down >= 20:
            advice, allow = '冰点档(阈值兜底): 仅超跌/撬板', {'G', 'K'}
        elif up >= 70 and br <= 0.20 and mx >= 5 and down <= 5:
            advice, allow = '亢奋档(阈值兜底): 仅龙头/加速', {'I', 'L'}
        elif up >= 40 and br <= 0.30 and mx >= 3 and down <= 10:
            advice, allow = '主升档(阈值兜底): 全策略开启', {'E', 'F', 'H', 'I', 'J', 'L'}
        elif 25 <= up < 40 and br <= 0.35 and mx >= 2:
            advice, allow = '修复档(阈值兜底): 首板/反包优先', {'E', 'F', 'H'}
        else:
            advice, allow = '退潮档(阈值兜底): 观望', {'G', 'K'}
    w('>> 周期[%s] 涨停%d 炸板%d 跌停%d 高度%d板 炸板率%.0f%%' % (stage, up, zb, down, mx, br * 100))
    w('>> 总开关: %s | 本次执行: %s' % (advice, ','.join(sorted(allow & _ACTIVE)) or '无'))
    return stage, advice, allow

_ACTIVE = {'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L'}
def set_active(keys):
    global _ACTIVE
    _ACTIVE = set(keys)

# ================= 编排器: screener2 =================
_STRATS = [
    ('E', '低位首板挖掘', '冰点末/修复', scr_first_board),
    ('F', '断板反包', '修复/主升', scr_break_rebound),
    ('G', '超跌反弹', '冰点/退潮末', scr_oversold),
    ('H', 'N字反包', '修复/主升', scr_n_shape),
    ('I', '均线趋势加速', '主升/亢奋', scr_trend_accel),
    ('J', '板块梯队+中军', '修复末/主升', scr_sector_ladder),
    ('K', '跌停撬板/准地天板', '退潮末/冰点', scr_lift_board),
    ('L', '龙虎榜游资接力', '主升/亢奋(T+1)', scr_yz_relay),
]
_STAGE_HINT = {
    'E': '冰点末/修复', 'F': '修复/主升(退潮禁用)', 'G': '冰点/退潮末',
    'H': '修复/主升', 'I': '主升/亢奋(尾段最后一棒)', 'J': '修复末/主升',
    'K': '退潮末/冰点(情绪见底先行)', 'L': '主升/亢奋(退潮=最后一棒)',
}

def screener2(mode='auto'):
    """mode: auto=按周期开关执行 | all=全策略跑一遍 | E/F/G/H/I/J/K/L 单策略"""
    w('\n########## 选股器 v2 (策略库会诊版) ##########')
    stage, advice, allow = regime_gate()
    ymd, zt, zb, dtp = pools_recent()
    if not zt:
        w('(近8日无涨停池数据, 池类策略跳过)')
    run_all = (mode == 'all')
    todo = [(k, t, fn) for k, t, _s, fn in _STRATS if run_all or k in allow]
    if not todo:
        w('(当前周期无适配策略, 仅输出总开关)')
        return
    univ = None
    for k, title, fn in todo:
        if k in ('E', 'F', 'H', 'L') and not zt:
            continue
        if k in ('G', 'I') or k == 'J' or k == 'K':
            if univ is None:
                univ = universe()
                w('[快照] 全市场%d只, 硬过滤后%d只' % (len(snapshot()), len(univ)))
        w('\n===== [%s %s] 适用:%s%s =====' % (
            k, title, _STAGE_HINT[k], '' if (run_all or k in allow) else ' (当前周期非适用,仅观察)'))
        try:
            if k == 'E':
                fn(zt)
            elif k == 'F':
                fn(zt)
            elif k == 'G':
                fn(univ)
            elif k == 'H':
                fn(zt)
            elif k == 'I':
                fn(univ)
            elif k == 'J':
                fn(zt, zb)
            elif k == 'K':
                fn(dtp, univ)
            elif k == 'L':
                fn(zt)
        except Exception as e:
            w('[%s失败] %s: %s' % (k, type(e).__name__, e))
    w('\n(选股器v2完; 阈值依据2026-08-25 dsh会诊定稿, 不构成投资建议)')

def run_strategies_structured(mode='auto'):
    """结构化运行策略库，返回规范 Dict，供 Web API 或 Agent 直接消费"""
    stage, advice, allow = regime_gate()
    ymd, zt, zb, dtp = pools_recent()
    run_all = (mode == 'all')
    valid_strat_keys = set(s[0] for s in _STRATS)
    target_keys = set(k.strip().upper() for k in mode.split(',')) if mode not in ('auto', 'all') else set()
    if mode not in ('auto', 'all') and not (target_keys & valid_strat_keys):
        # 针对非法或未知模式，自动安全降级为 auto 自适应模式
        mode = 'auto'
        target_keys = set()
    univ = None
    strat_results = []
    bc = by_code()

    for k, title, s_hint, fn in _STRATS:
        is_active = (run_all or k in allow or k in target_keys)
        # 如果是 auto 模式，只收集当前活跃的策略；若是 all 或指定模式，均收集
        if mode == 'auto' and not is_active:
            continue

        items = []
        if not (k in ('E', 'F', 'H', 'L') and not zt):
            if k in ('G', 'I', 'J', 'K') and univ is None:
                univ = universe()
            try:
                if k == 'E':
                    raw = fn(zt)
                    for _q, ratio, x, fbt, amt in (raw or [])[:10]:
                        c = x.get('c')
                        r = bc.get(c) or {}
                        p_val = _num(r.get('f2'))
                        if p_val <= 0 and _num(x.get('p')) > 0:
                            p_val = _num(x.get('p')) / 1000
                        pct_val = _num(r.get('f3'))
                        if pct_val == 0.0 and _num(x.get('zdp')) != 0.0:
                            pct_val = _num(x.get('zdp'))
                        items.append({
                            'code': c,
                            'name': x.get('n'),
                            'industry': x.get('hybk', '-'),
                            'price': round(p_val, 2),
                            'pct': round(pct_val, 2),
                            'quality': _q,
                            'desc': f"质量{_q:.1f} 首封{fbt[:2]}:{fbt[2:4]} 封单{_num(x.get('fund'))/1e8:.1f}亿(占流通{ratio:.1f}%) 流通{_num(x.get('ltsz'))/1e8:.0f}亿 额{amt/1e8:.1f}亿",
                        })
                elif k == 'F':
                    raw = fn(zt)
                    for _q, sc, c, x, pct_t1, fbt in (raw or [])[:8]:
                        r = bc.get(c) or {}
                        p_val = _num(r.get('f2'))
                        if p_val <= 0 and _num(x.get('p')) > 0:
                            p_val = _num(x.get('p')) / 1000
                        pct_val = _num(r.get('f3'))
                        if pct_val == 0.0 and _num(x.get('zdp')) != 0.0:
                            pct_val = _num(x.get('zdp'))
                        items.append({
                            'code': c,
                            'name': x.get('n'),
                            'industry': x.get('hybk', '-'),
                            'price': round(p_val, 2),
                            'pct': round(pct_val, 2),
                            'quality': _q,
                            'desc': f"质量{_q:.1f} T-1断板{pct_t1:+.1f}%后今反包 首封{fbt[:2]}:{fbt[2:4]} 炸{x.get('zbc', 0)}次 主力净入{_num(r.get('f62'))/1e8:+.1f}亿",
                        })
                elif k == 'G':
                    raw = fn(univ)
                    for dd, r in (raw or [])[:12]:
                        items.append({
                            'code': r.get('f12'),
                            'name': r.get('f14'),
                            'industry': r.get('f100', '-'),
                            'price': round(_num(r.get('f2')), 2),
                            'pct': round(_num(r.get('f3')), 2),
                            'desc': f"距160日高-{dd:.0f}% 换手{_num(r.get('f8')):.1f}% 额{_num(r.get('f6'))/1e8:.1f}亿 主力净入{_num(r.get('f62'))/1e8:+.1f}亿",
                        })
                elif k == 'H':
                    raw = fn(zt)
                    for _q, sc, c, x, pct_t1, fbt in (raw or [])[:8]:
                        r = bc.get(c) or {}
                        p_val = _num(r.get('f2'))
                        if p_val <= 0 and _num(x.get('p')) > 0:
                            p_val = _num(x.get('p')) / 1000
                        pct_val = _num(r.get('f3'))
                        if pct_val == 0.0 and _num(x.get('zdp')) != 0.0:
                            pct_val = _num(x.get('zdp'))
                        items.append({
                            'code': c,
                            'name': x.get('n'),
                            'industry': x.get('hybk', '-'),
                            'price': round(p_val, 2),
                            'pct': round(pct_val, 2),
                            'quality': _q,
                            'desc': f"质量{_q:.1f} {int(x.get('lbc', 1))}板N字 T-1回调{pct_t1:+.1f}%今反包 首封{fbt[:2]}:{fbt[2:4]}",
                        })
                elif k == 'I':
                    raw = fn(univ)
                    for sc, r in (raw or [])[:12]:
                        items.append({
                            'code': r.get('f12'),
                            'name': r.get('f14'),
                            'industry': r.get('f100', '-'),
                            'price': round(_num(r.get('f2')), 2),
                            'pct': round(_num(r.get('f3')), 2),
                            'desc': f"多头加速 额{_num(r.get('f6'))/1e8:.1f}亿 换手{_num(r.get('f8')):.1f}% 主力净入{_num(r.get('f62'))/1e8:+.1f}亿",
                        })
                elif k == 'J':
                    good, mids = fn(zt, zb)
                    for ratio, r in (mids or [])[:8]:
                        items.append({
                            'code': r.get('f12'),
                            'name': r.get('f14'),
                            'industry': r.get('f100', '-'),
                            'price': round(_num(r.get('f2')), 2),
                            'pct': round(_num(r.get('f3')), 2),
                            'desc': f"中军标的 额{_num(r.get('f6'))/1e8:.1f}亿 流通{_num(r.get('f21'))/1e8:.0f}亿 占流通{ratio:.1f}%",
                        })
                elif k == 'K':
                    raw = fn(dtp, univ)
                    for sc, c, r, oc in (raw or [])[:10]:
                        items.append({
                            'code': c,
                            'name': r.get('f14'),
                            'industry': r.get('f100', '-'),
                            'price': round(_num(r.get('f2')), 2),
                            'pct': round(_num(r.get('f3')), 2),
                            'desc': f"准地天板/撬板 开板{int(oc or 0)}次 换手{_num(r.get('f8')):.1f}% 额{_num(r.get('f6'))/1e8:.1f}亿",
                        })
                elif k == 'L':
                    raw = fn(zt)
                    for net_buy, c, nm, lbc in (raw or [])[:6]:
                        r = bc.get(c) or {}
                        p_val = _num(r.get('f2'))
                        pct_val = _num(r.get('f3'))
                        items.append({
                            'code': c,
                            'name': nm,
                            'industry': r.get('f100', '-'),
                            'price': round(p_val, 2),
                            'pct': round(pct_val, 2),
                            'desc': f"龙虎榜游资接力 {lbc}板 榜单净买{net_buy/1e8:+.2f}亿",
                        })

                # 补全缺失的价格和涨跌幅 (走毫秒级实时行情通道补充)
                missing_codes = [it['code'] for it in items if not it.get('price') or it.get('price') <= 0]
                if missing_codes:
                    try:
                        import data_feed as _df
                        live_quotes = _df.get_realtime_quotes(missing_codes)
                        for it in items:
                            if it['code'] in live_quotes:
                                lq = live_quotes[it['code']]
                                if lq.get('price') and lq['price'] > 0:
                                    it['price'] = round(float(lq['price']), 2)
                                if lq.get('pct') is not None:
                                    it['pct'] = round(float(lq['pct']), 2)
                    except Exception:
                        pass
            except Exception as e:
                w(f'[{k}结构化收集异常] {e}')

        strat_results.append({
            'key': k,
            'name': title,
            'stage_hint': s_hint,
            'active': is_active,
            'count': len(items),
            'items': items,
        })

    return {
        'status': 'ok',
        'date': ymd or dt.date.today().strftime('%Y%m%d'),
        'stage': stage,
        'advice': advice,
        'allow': sorted(list(allow)),
        'mode': mode,
        'strategies': strat_results,
        'updated': dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'auto'
    screener2(mode)








