# -*- coding: utf-8 -*-
"""
9:25 早盘集合竞价雷达 + 亏钱效应大面榜
- 昨日涨停今日溢价率 (接力情绪晴雨表)
- 弱转强异动 (超预期接力)
- 竞价爆量与一字封单
- 日内天地大面榜 (风险警报)
"""
import json, datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed
import stock_dashboard as sd

try:
    from ths_extractor import THSRealtimeQuote
except ImportError:
    try:
        from scripts.ths_extractor import THSRealtimeQuote
    except ImportError:
        THSRealtimeQuote = None

try:
    import trading_calendar as tcal
except ImportError:
    try:
        from scripts import trading_calendar as tcal
    except ImportError:
        tcal = None

def calc_amount_ratio_pct(curr_amount_yuan, prev_amount_yuan):
    """计算当前/竞价成交额占昨日全天成交额的百分比(%)

    用途 (2026-10-20 升级): 抓真金白银表态，过滤缩量假高开诱多。
    """
    try:
        curr = float(curr_amount_yuan or 0.0)
        prev = float(prev_amount_yuan or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if prev <= 0 or curr <= 0:
        return 0.0
    return round((curr / prev) * 100, 2)


def is_auction_boom(x):
    """竞价爆量「抢筹」判定：必须同时满足「有量」+「没在往下砸」。

    历史 bug（2026-10-26 三峡新材 600293）：原实现是一条纯量能表达式
    `vol_ratio>=3 or is_one_word or seal>=0.3亿 or amount_ratio_pct>=5`，
    **完全不看方向**，于是这只 -9.98% 一字跌停、买盘全空、卖一压 30 万手的票
    被判成「超预期抢筹」，理由写着"竞价占昨比 513%"。

    抢筹的前提是买盘主动、价格不跌，所以这里加三道方向门禁：
      ① 不是跌停（is_dt）
      ② 竞价涨跌幅 >= 0（不低开）
      ③ 五档委比不极端偏卖（order_ratio > -40，即卖压不超过买压的 2.3 倍）
    任一条不满足 → 不是抢筹，交给 big_loss（核按钮）去处理。
    """
    try:
        if not isinstance(x, dict):
            return False
        if x.get('is_dt'):
            return False
        if float(x.get('pct') or 0.0) < 0.0:
            return False
        if float(x.get('order_ratio') or 0.0) <= -40.0:
            return False
        return bool(
            float(x.get('vol_ratio') or 0.0) >= 3.0
            or x.get('is_one_word')
            or float(x.get('seal_amount_yi') or 0.0) >= 0.3
            or float(x.get('amount_ratio_pct') or 0.0) >= 5.0
        )
    except (TypeError, ValueError):
        return False


def is_fake_high_open(open_pct, vol_ratio, amount_yi, amount_ratio_pct):
    """识别缩量假高开（主力挂撤诱多，极易出现开盘跳水吃大面）

    规则 (结合游资打板心法与寻龙诀量化门禁):
    1. 必须是显著高开: open_pct >= 1.5%
    2. 资金极度匮乏 (满足其一即判定为假高开):
       - 量比极弱 (vol_ratio < 1.0) 且成交额占昨比 < 2.0%
       - 绝对金额过小: 竞价金额 < 500 万 (amount_yi < 0.05) 且占昨比 < 1.0%
    """
    try:
        op = float(open_pct or 0.0)
        vr = float(vol_ratio or 1.0)
        amt = float(amount_yi or 0.0)
        ratio = float(amount_ratio_pct or 0.0)
    except (TypeError, ValueError):
        return False

    if op < 1.5:
        return False

    # 量比弱且资金占比过低
    if vr < 1.0 and ratio < 2.0:
        return True
    # 绝对金额极低（不足500万，且占昨日比不足1%）
    if amt < 0.05 and ratio < 1.0:
        return True

    return False


def intraday_drawdown_pct(curr_p, high_p):
    """日内回撤率(%) —— 以当日最高价为基数

    修复 (2026-10-18): 旧写法 drop = pct - high_pct 是把两个"相对昨收的涨幅
    百分比"相减，两者基数不同，结果既不是回撤率也会系统性偏移。举例：
        昨收 6.20 / 最高 6.77 / 现价 6.32
        旧算法 (pct - high_pct) = 1.94 - 9.19 = -7.26%   ❌
        正确   (6.32-6.77)/6.77 = -6.65%                 ✅
    偏差在涨停股上被放大：昨收10、冲高11.5、收11.1 真实只回落 3.48%，
    旧算法给出 -4.00%，刚好越过 -4% 的"大面"阈值造成误报。
    """
    try:
        curr_p = float(curr_p)
        high_p = float(high_p)
    except (TypeError, ValueError):
        return 0.0
    if high_p <= 0:
        return 0.0
    return round((curr_p - high_p) / high_p * 100, 2)


def get_recent_trading_days(n=2):
    """回溯获取最近 n 个**真实交易日**的涨停池数据

    修复 (2026-10-18): 原实现用"池子有没有数据"判断是不是交易日，但东方财富
    涨停池接口对非交易日会直接回吐最近一个交易日的快照（周末、甚至未来日期
    都返回同样数据）。结果 t_date/y_date 被取成周日/周六，两者数据同源，
    "昨->今"晋级比对变成自己跟自己比，1进2 晋级率恒为 0%，同时溢价统计
    因收盘价对收盘价而全红 -> 出现 "0% 晋级率" 与 "超强接力 100%" 并存。
    现在改为先用上证指数真实日K过滤交易日，再取池子。
    """
    if tcal is not None:
        return tcal.get_recent_trading_days(n, pool_fetcher=lambda ymd: sd._pool('ZT', ymd))

    base = dt.date.today()
    found = []
    for i in range(0, 12):
        d_str = (base - dt.timedelta(days=i)).strftime('%Y%m%d')
        p = sd._pool('ZT', d_str)
        if p:
            found.append((d_str, p))
            if len(found) >= n:
                break
    return found

def _safe_float(v, default=0.0):
    """把东财/腾讯返回的脏值('-', '', None, '--')安全转成 float

    修复 (2026-10-18): 东财接口在停牌/无成交时会返回 '-' 或空串，
    直接 float() 抛 ValueError 会中断整个 for 循环，导致大面榜整页空白。
    """
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s or s in ('-', '--', 'None', 'null'):
        return default
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


def _safe_int(v, default=1):
    """东财 lbc(连板数) 字段可能返回 None / '' / '-' 等脏值。

    修复 (2026-10-18): 原来直接 int(z.get('lbc', 1))，一旦遇到脏值抛
    ValueError，整个竞价雷达页会崩掉（晋级梯队/天梯全部丢失）。
    """
    if v is None:
        return default
    if isinstance(v, bool):
        return default
    if isinstance(v, int):
        return v
    try:
        s = str(v).strip()
        if not s or s in ('-', '--', 'None', 'null'):
            return default
        return int(float(s))
    except (TypeError, ValueError):
        return default


def _is_one_word_bar(open_p, curr_p, low_p, limit_up, prev_close):
    """判断是否"一字板"（开盘即封死涨停，全天无回落）

    修复 (2026-10-18): 原实现写死 open_pct >= 9.8，只对 10cm 主板成立。
    创业板/科创板 20cm、北交所 30cm 的一字板 open_pct 会到 19.9 / 29.9，
    但 ST 股 5cm 的涨停只有 4.9，会被 9.8 门槛漏掉。
    改为以个股自身的涨停价(limit_up)为基准判定：
      开盘价 == 最低价 == 现价 == 涨停价  →  一字板
    limit_up 缺失时退回"相对昨收 >= 9.8%"的启发式。
    """
    eps = 0.011   # 一个最小价格变动单位，容纳四舍五入
    if not (curr_p == open_p and low_p == open_p):
        return False
    if limit_up and limit_up > 0:
        return abs(open_p - limit_up) <= eps
    if prev_close and prev_close > 0:
        return (open_p - prev_close) / prev_close * 100 >= 9.8
    return False


def get_auction_radar():
    """计算 9:25 集合竞价雷达与亏钱效应大面榜

    重要 (2026-10-18 修复)：必须区分「今天」与「上一交易日」。

    旧实现在休市日会把 trading_days[0] 同时当成"今天"和"昨天"，于是
    （a）晋级统计拿同一天的数据自己跟自己比 → 1进2 恒为 0%；
    （b）溢价统计拿同一天的收盘价对同一天收盘价 → 红盘率 100%、"超强接力"。
    两个结论互相矛盾却同时展示在页面上。

    新语义：
      today_ymd  = 今天，仅当今天**确实是交易日**时才是真实盘面，否则视为"无今日盘面"
      prev_ymd   = 今天之前最近的一个真实交易日（真正的"昨日涨停池"）
      base_ymd   = 今日有盘面用 today_ymd，否则退化用 prev_ymd（休市日看最近交易日复盘）
    晋级率仅在"今日确有真实盘面"时计算，否则返回 None 并由前端标注"休市，不适用"。
    """
    t0 = dt.datetime.now()
    trading_days = get_recent_trading_days(3)
    if not trading_days:
        return {'status': 'error', 'msg': '无近期涨停池数据'}

    today_str = dt.date.today().strftime('%Y%m%d')
    avail = [d for d, _ in trading_days]
    pool_map = dict(trading_days)

    # 今天是否为本所真实交易日（日历为准，不用"池子有没有数据"）
    today_is_trading = False
    if tcal is not None:
        today_is_trading = tcal.is_trading_day(today_str)
    else:
        today_is_trading = today_str in pool_map

    if today_is_trading and today_str in pool_map:
        t_date, t_zt = today_str, pool_map[today_str]
        prev_candidates = [d for d in avail if d < today_str]
        y_date = max(prev_candidates) if prev_candidates else None
        y_zt = pool_map.get(y_date, []) if y_date else []
    else:
        # 休市日：最近交易日只作为"基准盘面"，不存在真正的"今日晋级"
        t_date = max(avail)
        t_zt = pool_map[t_date]
        prev_candidates = [d for d in avail if d < t_date]
        y_date = max(prev_candidates) if prev_candidates else None
        y_zt = pool_map.get(y_date, []) if y_date else []

    if not t_zt:
        return {'status': 'error', 'msg': '涨停池为空'}

    # 晋级比对只有在"今天确实是交易日、且昨日数据独立可得"时才有意义
    promotion_valid = bool(today_is_trading and y_date and y_date != t_date and y_zt)

    t_zb = sd._pool('ZB', t_date) or []
    y_zb = (sd._pool('ZB', y_date) or []) if y_date else []

    # 梯队晋级与炸板率统计 (吸纳 vibe-astock / easy-stock 核心指标)
    total_touch = len(t_zt) + len(t_zb)
    broken_rate = round(len(t_zb) / total_touch * 100, 1) if total_touch > 0 else 0.0
    seal_rate = round(len(t_zt) / total_touch * 100, 1) if total_touch > 0 else 0.0

    max_lbc = 0
    leader = None
    for z in t_zt:
        lbc = _safe_int(z.get('lbc'), 1)
        if lbc > max_lbc:
            max_lbc = lbc
            leader = z

    prev_1b = [z.get('c') for z in y_zt if _safe_int(z.get('lbc'), 1) == 1]
    prev_2b = [z.get('c') for z in y_zt if _safe_int(z.get('lbc'), 1) == 2]
    prev_multi = [z.get('c') for z in y_zt if _safe_int(z.get('lbc'), 1) >= 2]

    today_zt_map = {z.get('c'): _safe_int(z.get('lbc'), 1) for z in t_zt}
    succ_1to2 = [c for c in prev_1b if today_zt_map.get(c, 0) >= 2]
    succ_2to3 = [c for c in prev_2b if today_zt_map.get(c, 0) >= 3]
    succ_multi = [c for c in prev_multi if today_zt_map.get(c, 0) > 2]

    # 晋级率：仅在 promotion_valid 时给出数值；否则为 None，前端显示"休市·不适用"
    # （修复前恒为 0.0，会被误读成"一个都没晋级"，这正是页面自相矛盾的来源之一）
    if promotion_valid and prev_1b:
        promote_1_2 = round(len(succ_1to2) / len(prev_1b) * 100, 1)
    else:
        promote_1_2 = None
    if promotion_valid and prev_2b:
        promote_2_3 = round(len(succ_2to3) / len(prev_2b) * 100, 1)
    else:
        promote_2_3 = None
    if promotion_valid and prev_multi:
        promote_high = round(len(succ_multi) / len(prev_multi) * 100, 1)
    else:
        promote_high = None

    highest_leader = {
        'name': leader.get('n', '-') if leader else '-',
        'code': leader.get('c', '-') if leader else '-',
        'lbc': max_lbc,
        'industry': leader.get('hybk', '-') if leader else '-'
    } if leader else None

    promotion_metrics = {
        # 数据可信度标记：前端据此决定展示"数值"还是"休市·不适用"
        'promotion_valid': promotion_valid,
        'today_is_trading': today_is_trading,
        't_date': t_date,
        'y_date': y_date,
        'broken_rate': broken_rate,
        'seal_rate': seal_rate,
        'total_zt': len(t_zt),
        'total_zb': len(t_zb),
        'total_touch': total_touch,
        'max_lbc': max_lbc,
        'highest_leader': highest_leader,
        'leader_name': leader.get('n') if leader else '-',
        'leader_code': leader.get('c') if leader else '-',
        'leader_industry': leader.get('hybk') if leader else '-',
        'promote_1_to_2_rate': promote_1_2,
        'today_2_board_count': len(succ_1to2),
        'y_1_board_count': len(prev_1b),
        'promote_2_to_3_rate': promote_2_3,
        'today_3_board_count': len(succ_2to3),
        'y_2_board_count': len(prev_2b),
        'high_tier_promote_rate': promote_high,
        'today_high_tier_count': len(succ_multi),
        'y_high_tier_count': len(prev_multi),
        # 兼容简写
        'rate_1to2': promote_1_2,
        'rate_2to3': promote_2_3,
        'rate_multi': promote_high,
    }

    # 汇总待监控标的
    all_targets = {}
    for d in y_zt:
        all_targets[d.get('c', '')] = {
            'name': d.get('n', ''),
            'src': 'ZT',
            'lbc': d.get('lbc', 1),
            'hybk': d.get('hybk', ''),
            'zbc': d.get('zbc', 0),
            'fbt': d.get('fbt', ''),
            'prev_amount': _safe_float(d.get('amount'), 0.0),  # 昨日全天成交额(元)
        }
    for d in y_zb:
        c = d.get('c', '')
        if c and c not in all_targets:
            all_targets[c] = {
                'name': d.get('n', ''),
                'src': 'ZB',
                'lbc': 0,
                'hybk': d.get('hybk', ''),
                'zbc': d.get('zbc', 1),
                'fbt': '',
                'prev_amount': _safe_float(d.get('amount'), 0.0),  # 昨日全天成交额(元)
            }

    codes = [('sh' if c.startswith(('6', '5', '9')) else 'sz') + c for c in all_targets if c]

    # 分批极速拉取实时行情 (Tencent 毫秒级)
    quotes = {}
    _batch_fail = []   # [(首个代码, 异常类型)] —— 腾讯批量接口失败批次，用于可观测性
    for i in range(0, len(codes), 80):
        chunk = codes[i:i + 80]
        try:
            raw = sd.http('https://qt.gtimg.cn/q=' + ','.join(chunk), gbk=True, timeout=5)
            for line in raw.split(';'):
                if '=' not in line:
                    continue
                parts = line.split('"')[1].split('~')
                if len(parts) > 38 and parts[4] and parts[5]:
                    c = parts[2]
                    prev_close = float(parts[4])
                    if prev_close <= 0:
                        continue
                    curr_p = float(parts[3])
                    open_p = float(parts[5])
                    high_p = float(parts[33])
                    low_p = float(parts[34])
                    pct = float(parts[32]) if parts[32] else 0.0
                    open_pct = round((open_p - prev_close) / prev_close * 100, 2)
                    high_pct = round((high_p - prev_close) / prev_close * 100, 2)
                    drop_from_high = intraday_drawdown_pct(curr_p, high_p)
                    vol_ratio = float(parts[49]) if len(parts) > 49 and parts[49] else 1.0
                    turnover = float(parts[38]) if parts[38] else 0.0
                    amount = float(parts[37]) if parts[37] else 0.0  # 万元
                    limit_up = float(parts[47]) if len(parts) > 47 and parts[47] else 0.0
                    limit_down = float(parts[48]) if len(parts) > 48 and parts[48] else 0.0

                    # 买卖五档挂单 (量单位为手) [[price, vol], ...]
                    bids = [
                        [float(parts[9] or 0), float(parts[10] or 0)],
                        [float(parts[11] or 0), float(parts[12] or 0)],
                        [float(parts[13] or 0), float(parts[14] or 0)],
                        [float(parts[15] or 0), float(parts[16] or 0)],
                        [float(parts[17] or 0), float(parts[18] or 0)],
                    ]
                    asks = [
                        [float(parts[19] or 0), float(parts[20] or 0)],
                        [float(parts[21] or 0), float(parts[22] or 0)],
                        [float(parts[23] or 0), float(parts[24] or 0)],
                        [float(parts[25] or 0), float(parts[26] or 0)],
                        [float(parts[27] or 0), float(parts[28] or 0)],
                    ]
                    tot_bid = sum(b[1] for b in bids)
                    tot_ask = sum(a[1] for a in asks)
                    denom = tot_bid + tot_ask
                    order_ratio = round((tot_bid - tot_ask) / denom * 100, 2) if denom > 0 else 0.0

                    bid1_p = bids[0][0]
                    bid1_v = bids[0][1]
                    ask1_p = asks[0][0]
                    ask1_v = asks[0][1]

                    is_zt = (curr_p >= limit_up - 0.01) if limit_up > 0 else False
                    is_dt = (curr_p <= limit_down + 0.01) if limit_down > 0 else False

                    # 挂单额计算：1手=100股，(p * v * 100) / 1e8 = (p * v) / 1e6 亿元
                    bid1_amt_yi = round(bid1_p * bid1_v / 1e6, 2) if bid1_p > 0 else 0.0
                    ask1_amt_yi = round(ask1_p * ask1_v / 1e6, 2) if ask1_p > 0 else 0.0
                    seal_amount_yi = bid1_amt_yi if is_zt else 0.0
                    dt_pressure_yi = ask1_amt_yi if is_dt else 0.0

                    prev_amt = all_targets.get(c, {}).get('prev_amount', 0.0)
                    prev_amt_yi = round(prev_amt / 1e8, 2) if prev_amt > 0 else 0.0
                    amt_yi = round(amount / 10000, 2)
                    amt_ratio_pct = calc_amount_ratio_pct(amount * 10000.0, prev_amt)
                    fake_high = is_fake_high_open(open_pct, vol_ratio, amt_yi, amt_ratio_pct)

                    quotes[c] = {
                        'code': c,
                        'name': parts[1],
                        'price': curr_p,
                        'prev_close': prev_close,
                        'open_price': open_p,
                        'open_pct': open_pct,
                        'pct': pct,
                        'high_pct': high_pct,
                        'low_p': low_p,
                        'drop_from_high': drop_from_high,
                        'vol_ratio': vol_ratio,
                        'turnover': turnover,
                        'amount_yi': amt_yi,
                        'prev_amount_yi': prev_amt_yi,
                        'amount_ratio_pct': amt_ratio_pct,
                        'is_fake_high_open': fake_high,
                        'limit_up': limit_up,
                        'limit_down': limit_down,
                        'is_zt': is_zt,
                        'is_dt': is_dt,
                        'is_one_word': _is_one_word_bar(open_p, curr_p, low_p, limit_up, prev_close),
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
                    }
        except Exception as e:
            # 修复 (2026-10-18): 原来是裸 pass，当腾讯与同花顺同时失败时，
            # 页面只表现为"部分股票缺失"，没有任何线索。
            _batch_fail.append((chunk[0], type(e).__name__))
            pass

    # 极速热备：若腾讯批量接口漏票或超时，通过线程池并发调用同花顺极速盘口补齐
    missing_codes = [c for c in all_targets if c and c not in quotes]
    if missing_codes and THSRealtimeQuote:
        def _fetch_ths_quote(cd):
            try:
                res = THSRealtimeQuote.get_realhead(cd)
                return cd, res
            except Exception:
                return cd, None

        with ThreadPoolExecutor(max_workers=min(10, len(missing_codes))) as executor:
            futures = [executor.submit(_fetch_ths_quote, cd) for cd in missing_codes]
            for fut in as_completed(futures):
                try:
                    c, q = fut.result()
                    if q and q.get('prev_close', 0) > 0 and q.get('price', 0) > 0:
                        prev_close = q['prev_close']
                        curr_p = q['price']
                        open_p = q.get('open') or curr_p
                        high_p = q.get('high') or curr_p
                        low_p = q.get('low') or curr_p
                        pct = q.get('change_pct', 0.0)
                        open_pct = round((open_p - prev_close) / prev_close * 100, 2)
                        high_pct = round((high_p - prev_close) / prev_close * 100, 2)
                        drop_from_high = intraday_drawdown_pct(curr_p, high_p)
                        limit_up = q.get('upper_limit', 0.0)
                        limit_down = q.get('lower_limit', 0.0)
                        turnover = q.get('turnover_rate', 0.0)
                        amount_yi = round(q.get('amount_wan', 0.0) / 10000, 2)
                        is_zt = q.get('is_zt', (curr_p >= limit_up - 0.01) if limit_up > 0 else False)
                        is_dt = q.get('is_dt', (curr_p <= limit_down + 0.01) if limit_down > 0 else False)

                        prev_amt = all_targets.get(c, {}).get('prev_amount', 0.0)
                        prev_amt_yi = round(prev_amt / 1e8, 2) if prev_amt > 0 else 0.0
                        amt_ratio_pct = calc_amount_ratio_pct(amount_yi * 1e8, prev_amt)
                        fake_high = is_fake_high_open(open_pct, 1.0, amount_yi, amt_ratio_pct)

                        quotes[c] = {
                            'code': c,
                            'name': q.get('name', ''),
                            'price': curr_p,
                            'prev_close': prev_close,
                            'open_price': open_p,
                            'open_pct': open_pct,
                            'pct': pct,
                            'high_pct': high_pct,
                            'low_p': low_p,
                            'drop_from_high': drop_from_high,
                            'vol_ratio': 1.0,
                            'turnover': turnover,
                            'amount_yi': amount_yi,
                            'prev_amount_yi': prev_amt_yi,
                            'amount_ratio_pct': amt_ratio_pct,
                            'is_fake_high_open': fake_high,
                            'limit_up': limit_up,
                            'limit_down': limit_down,
                            'is_zt': is_zt,
                            'is_dt': is_dt,
                            'is_one_word': _is_one_word_bar(open_p, curr_p, low_p, limit_up, prev_close),
                            'bid1': q.get('bid1', (0.0, 0.0)),
                            'ask1': q.get('ask1', (0.0, 0.0)),
                            'bids': q.get('bids', []),
                            'asks': q.get('asks', []),
                            'order_ratio': q.get('order_ratio', 0.0),
                            'weibi': q.get('weibi', q.get('order_ratio', 0.0)),
                            'bid1_amount_yi': q.get('bid1_amount_yi', 0.0),
                            'ask1_amount_yi': q.get('ask1_amount_yi', 0.0),
                            'seal_amount_yi': q.get('seal_amount_yi', 0.0),
                            'seal_wan': q.get('seal_wan', round(q.get('seal_amount_yi', 0.0) * 10000, 1)),
                            'dt_pressure_yi': q.get('dt_pressure_yi', 0.0),
                            'dt_wan': q.get('dt_wan', round(q.get('dt_pressure_yi', 0.0) * 10000, 1)),
                        }
                except Exception:
                    pass

    # 1. 统计昨日涨停股在今日的综合溢价
    zt_stats_items = []
    for d in y_zt:
        c = d.get('c', '')
        if c in quotes:
            merged = dict(quotes[c])
            merged.update(all_targets[c])
            zt_stats_items.append(merged)

    if zt_stats_items:
        avg_open = round(sum(x['open_pct'] for x in zt_stats_items) / len(zt_stats_items), 2)
        avg_curr = round(sum(x['pct'] for x in zt_stats_items) / len(zt_stats_items), 2)
        up_open_count = sum(1 for x in zt_stats_items if x['open_pct'] > 0)
        up_curr_count = sum(1 for x in zt_stats_items if x['pct'] > 0)
        zt_again = sum(1 for x in zt_stats_items if x['is_zt'])
        dt_count = sum(1 for x in zt_stats_items if x['is_dt'])
        mian_count = sum(1 for x in zt_stats_items if x['drop_from_high'] <= -6.0)

        # 情绪标签判定
        # 修复 (2026-10-18): 休市日时 y_zt 是"上一交易日"、quotes 是"最近交易日收盘"，
        # 这组溢价是**历史复盘**而非当日接力实况。旧代码照样打上"超强接力"，
        # 与同期 0% 的晋级率并列显示，读者无法分辨。此处加语境标记，
        # 并在休市日改写标签前缀，前端据此可做灰化/标注。
        if avg_open >= 2.5:
            sentiment_tag = '超强接力'
            sentiment_color = 'emerald'
        elif avg_open > 0.5:
            sentiment_tag = '温和溢价'
            sentiment_color = 'cyan'
        elif avg_open >= -1.0:
            sentiment_tag = '接力偏弱'
            sentiment_color = 'amber'
        else:
            sentiment_tag = '接力极度恶化'
            sentiment_color = 'rose'

        # 若今日非交易日，或"昨日池"与"今日盘面"不是相邻的真实两个交易日，
        # 则该结论只代表历史复盘
        preview_mode = (not today_is_trading) or (not promotion_valid)
        sentiment_tag_live = sentiment_tag
        if preview_mode:
            sentiment_tag = f'{sentiment_tag}（{y_date}→{t_date} 历史复盘）'

        total_seal = round(sum(x.get('seal_amount_yi', 0) for x in zt_stats_items if x.get('is_zt')), 2)
        total_dt_pressure = round(sum(x.get('dt_pressure_yi', 0) for x in zt_stats_items if x.get('is_dt')), 2)

        premium_summary = {
            'y_date': y_date,
            't_date': t_date,
            'preview_mode': preview_mode,
            'sentiment_tag_live': sentiment_tag_live,
            'total_zt': len(zt_stats_items),
            'avg_open_pct': avg_open,
            'avg_curr_pct': avg_curr,
            'open_positive_rate': round(up_open_count / len(zt_stats_items) * 100, 1),
            'curr_positive_rate': round(up_curr_count / len(zt_stats_items) * 100, 1),
            'promote_zt_count': zt_again,
            'dt_count': dt_count,
            'mian_count': mian_count,
            'total_seal_amount_yi': total_seal,
            'total_dt_pressure_yi': total_dt_pressure,
            'sentiment_tag': sentiment_tag,
            'sentiment_color': sentiment_color,
        }
        promotion_metrics['total_seal_amount_yi'] = total_seal
        promotion_metrics['total_dt_pressure_yi'] = total_dt_pressure
    else:
        premium_summary = {}

    # 2. 弱转强标的 (超预期高开 + 带量)
    zb_items = []
    zt_codes = {x['code'] for x in zt_stats_items}
    for d in y_zb:
        c = d.get('c', '')
        if c in quotes and c not in zt_codes:
            merged = dict(quotes[c])
            merged.update(all_targets.get(c, {}))
            zb_items.append(merged)

    weak_to_strong = []
    fake_high_opens = []
    for item in zt_stats_items + zb_items:
        # 记录缩量假高开诱多标的 (供风险警示)
        if item.get('is_fake_high_open'):
            amt_info = f"金额{item.get('amount_yi', 0)}亿(占昨{item.get('amount_ratio_pct', 0)}%)" if item.get('prev_amount_yi', 0) > 0 else f"成交{item.get('amount_yi', 0)}亿"
            reason = f"缩量诱多预警: 高开{item['open_pct']:+.1f}%但量比仅{item['vol_ratio']:.1f}, {amt_info}"
            fake_high_opens.append(dict(item, reason=reason, risk_tag='缩量诱多'))

        # 弱转强异动标的判定 —— 核心：坚决剔除缩量假高开！
        if item.get('is_fake_high_open'):
            continue

        amt_str = f"量{item['amount_yi']}亿/占昨{item['amount_ratio_pct']}%" if item.get('prev_amount_yi', 0) > 0 else f"成交{item['amount_yi']}亿"

        # 炸板转强: 昨炸板但今日高开>1.5% 且量比>1.5
        if item.get('src') == 'ZB' and item['open_pct'] >= 1.5 and item['vol_ratio'] >= 1.5:
            reason = f"昨炸板(今开{item['open_pct']:+.1f}%,量比{item['vol_ratio']:.1f},{amt_str})"
            weak_to_strong.append(dict(item, reason=reason))
        # 烂板转强: 昨曾炸板多次但回封，今高开>2.5%
        elif item.get('zbc', 0) >= 2 and item['open_pct'] >= 2.5 and item['vol_ratio'] >= 1.5:
            reason = f"昨炸{item.get('zbc')}次(今高开{item['open_pct']:+.1f}%,量比{item['vol_ratio']:.1f},{amt_str})"
            weak_to_strong.append(dict(item, reason=reason))
        # 弱板转高开加速: 昨首板换手，今高开>4%且量比>2
        elif item.get('lbc', 1) == 1 and item['open_pct'] >= 4.0 and item['vol_ratio'] >= 2.0:
            reason = f"昨首板(今加速高开{item['open_pct']:+.1f}%,量比{item['vol_ratio']:.1f},{amt_str})"
            weak_to_strong.append(dict(item, reason=reason))

    weak_to_strong.sort(key=lambda x: -x['open_pct'])
    fake_high_opens.sort(key=lambda x: -x['open_pct'])

    # 3. 竞价爆量与一字板封单 (量比>=3.0 或 一字板 或 实时竞价封单>0.3亿 或 金额占昨比>=5%)
    #    ⚠️ 必须过 is_auction_boom 的方向门禁：跌停/低开/极端卖压一律不进抢筹池
    auction_boom = [x for x in zt_stats_items if is_auction_boom(x)]
    auction_boom.sort(key=lambda x: (x.get('seal_amount_yi', 0) if x.get('is_zt') else 0, x.get('amount_ratio_pct', 0), x['vol_ratio']), reverse=True)

    # 4. 亏钱效应大面榜 (天地大面 / 冲高大回撤 / 跌停)
    big_loss_candidates = list(quotes.values())
    try:
        url = 'https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=20&po=0&np=1&fltt=2&fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f12,f14,f2,f3,f15,f16,f18'
        raw_em = sd.http(url, timeout=3)
        diff = json.loads(raw_em).get('data', {}).get('diff', [])
        for d in diff:
            c = str(d.get('f12', ''))
            if c and c not in quotes:
                # 用 _safe_float 兜脏值，避免单条异常中断整个大面榜
                prev_c = _safe_float(d.get('f18'), 0.0)
                curr_c = _safe_float(d.get('f2'), 0.0)
                high_c = _safe_float(d.get('f15'), 0.0)
                pct = _safe_float(d.get('f3'), 0.0)
                if prev_c > 0 and high_c > 0:
                    # 修复: 此处原为 round(pct - high_pct, 2)，与文件开头
                    # intraday_drawdown_pct() 注释里已修的是同一类错误
                    # （两个不同基数的涨幅百分比相减，不是回撤率）。
                    drop = intraday_drawdown_pct(curr_c, high_c)
                    big_loss_candidates.append({
                        'code': c,
                        'name': str(d.get('f14', '')),
                        'price': curr_c,
                        'prev_close': prev_c,
                        'open_pct': 0,
                        'pct': pct,
                        'high_pct': round((high_c - prev_c) / prev_c * 100, 2),
                        'drop_from_high': drop,
                        'vol_ratio': 1.0,
                        'amount_yi': 0,
                        'is_zt': False,
                        'is_dt': (pct <= -9.5),
                        'is_one_word': False,
                    })
    except Exception:
        pass

    # 亏钱效应榜排序：一字跌停的 high==low==跌停价，`drop_from_high` 恒为 0，
    # 若只按回撤升序取前 12，最惨的跌停票反而会被挤掉（2026-10-26 三峡新材即如此，
    # 结果它在 boom 榜里被当成"抢筹"、在核按钮榜里又看不见）。
    # 改为：跌停/深水优先 → 跌幅更深优先 → 回撤更大优先。
    def _big_loss_severity(x):
        pct = _safe_float(x.get('pct'), 0.0)
        drop = _safe_float(x.get('drop_from_high'), 0.0)
        return (0 if pct <= -9.5 else 1, pct, drop)

    big_loss = sorted([x for x in big_loss_candidates if x['drop_from_high'] <= -4.0 or x['pct'] <= -7.0],
                      key=_big_loss_severity)[:12]

    elapsed = round((dt.datetime.now() - t0).total_seconds(), 2)

    # 金额口径：9:25~9:30 的成交额才是真正的「竞价成交额」；开盘后 amount 会一直累加，
    # 此时「占昨比」是"当日累计成交/昨日全天"，不是"竞价占昨"。必须如实标注，
    # 否则会出现"竞价额 3.56 亿 / 占昨 513%"这种看着吓人、其实是盘中累计的数字。
    _now = dt.datetime.now()
    if _now.hour < 9 or (_now.hour == 9 and _now.minute < 25):
        amount_basis = 'pre'
    # 9:30:00 起已是连续竞价，只有 9:25~9:29:59 的成交额才是真正的竞价额
    elif _now.hour == 9 and _now.minute < 30:
        amount_basis = 'auction'
    else:
        amount_basis = 'intraday'

    # ================= weak_to_strong × auction_boom 交叉去重 =================
    # 同一股票可能同时满足弱转强和抢筹条件，保留信号强度更高的，去重另一个。
    # 信号强度评分：max(open_pct, 0) + vol_ratio（开盘强度 + 量能强度）
    # 去重后在保留项上附加 cross_dedup 字段，记录被去重的来源信号。
    wts_codes = {x['code'] for x in weak_to_strong}
    boom_codes = {x['code'] for x in auction_boom}
    overlap_codes = wts_codes & boom_codes

    cross_dedup_log = []
    if overlap_codes:
        def _signal_strength(item):
            return max(item.get('open_pct', 0) or 0, 0) + (item.get('vol_ratio', 0) or 0)

        for code in overlap_codes:
            wts_item = next(x for x in weak_to_strong if x['code'] == code)
            boom_item = next(x for x in auction_boom if x['code'] == code)
            wts_score = _signal_strength(wts_item)
            boom_score = _signal_strength(boom_item)
            if wts_score >= boom_score:
                # 保留 weak_to_strong，从 auction_boom 移除
                wts_item['cross_dedup'] = 'auction_boom'
                auction_boom = [x for x in auction_boom if x['code'] != code]
                cross_dedup_log.append({'code': code, 'kept': 'weak_to_strong', 'removed': 'auction_boom',
                                        'scores': {'wts': round(wts_score, 2), 'boom': round(boom_score, 2)}})
            else:
                # 保留 auction_boom，从 weak_to_strong 移除
                boom_item['cross_dedup'] = 'weak_to_strong'
                weak_to_strong = [x for x in weak_to_strong if x['code'] != code]
                cross_dedup_log.append({'code': code, 'kept': 'auction_boom', 'removed': 'weak_to_strong',
                                        'scores': {'wts': round(wts_score, 2), 'boom': round(boom_score, 2)}})

    radar_out = {
        'status': 'ok',
        'elapsed': elapsed,
        'amount_basis': amount_basis,
        'promotion_metrics': promotion_metrics,
        'premium_summary': premium_summary,
        'weak_to_strong': weak_to_strong[:12],
        'fake_high_opens': fake_high_opens[:12],
        'auction_boom': auction_boom[:12],
        'big_loss': big_loss,
        'cross_dedup': cross_dedup_log if cross_dedup_log else None,
        # 数据缺失可观测性：腾讯批量接口失败批次。非空说明部分个股的实时行情
        # 未能取到（依赖同花顺兜底），页面若出现"缺票"可据此定位。
        'data_warn': ({'tencent_batch_fail': len(_batch_fail),
                       'sample': [c for c, _ in _batch_fail[:5]]}
                      if _batch_fail else None),
        'updated_at': dt.datetime.now().strftime('%H:%M:%S')
    }

    # 自动保存早盘竞价推荐池快照（供 15:00 收盘对账闭环核验）
    #
    # 归档日必须用"盘面实际对应的交易日" t_date，不能用 dt.date.today()。
    # 休市日（周末/节假日）跑雷达时，today 并不是交易日，却会把最近交易日的盘面
    # 存成"今天"的快照 → 生成一条不存在的交易日的对账记录。
    # 实测事故：20261025（周六）跑了一次，打脸账本里就多出一条
    # "20261025 弱转强3只 / 封板率33.3% / 胜率33.3%" 的假样本。
    # 与情绪存档 20261001 假记录是同一类事故，教训一致：默认怀疑"今天"。
    try:
        import auction_audit as _aa
        _cur_ymd = t_date or dt.date.today().strftime('%Y%m%d')
        # 时点闸门：只有 9:15~9:35 之间抓的快照才是"9:25 决策快照"；
        # 其余时点（盘后/休市日复盘）抓到的是收盘后行情，含后见之明，标 synthetic，
        # 打脸账本会把它排除在命中率统计之外。
        _now_min = dt.datetime.now().hour * 60 + dt.datetime.now().minute
        _phase = 'auction' if (9 * 60 + 15) <= _now_min <= (9 * 60 + 35) else 'post_close'
        _aa.save_auction_candidates_snapshot(_cur_ymd, radar_out, phase=_phase)
    except Exception:
        pass

    return radar_out


# ====================== 全市场竞价扫描（独立于接力雷达） ======================

def get_full_market_auction_scan():
    """全市场竞价扫描：一次拉全A股竞价快照，严格阈值信号判定。

    与 get_auction_radar()（接力雷达）完全独立，不依赖昨日涨停/炸板身份。
    用东财clist接口 pz=5500 一个请求拿全市场，不分批。

    信号类型：
      SUPER_GRAB      — 超预期抢筹：open_pct>=2.0 AND vol_ratio>=2.0 AND 非跌停
      NUCLEAR_BUTTON  — 竞价核按钮：open_pct<=-5.0 OR (open_pct<=-3.0 AND vol_ratio>=2.0)
      LOCKED_LIMIT_UP — 一字封单：open_pct>=9.8（启发式，不拉涨停价）
      FAKE_HIGH       — 缩量假高开：open_pct>=3.0 AND vol_ratio<1.0（高开无量=诱多）

    排除：ST股（名称含ST/ST*）、停牌（现价=0或昨收=0）
    每类信号取 top 30，按强度排序。
    """
    url = (
        'https://push2.eastmoney.com/api/qt/clist/get'
        '?pn=1&pz=5500&po=1&np=1&fltt=2&fid=f3'
        '&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23'
        '&fields=f12,f14,f2,f3,f4,f5,f6,f8,f10,f15,f16,f18,f62'
    )
    try:
        raw = sd.http(url, timeout=8, retries=2)
        j = json.loads(raw)
    except Exception as e:
        return {'status': 'error', 'msg': f'东财接口异常: {e}'}

    d = j.get('data') or {}
    diff = d.get('diff') or []
    if not diff:
        return {'status': 'error', 'msg': '东财返回空数据'}

    super_grab = []
    nuclear_button = []
    locked_limit = []
    fake_high = []
    total_scanned = 0

    for r in diff:
        code = r.get('f12')
        name = r.get('f14')
        price = r.get('f2')
        pct = r.get('f3')
        vol_ratio = r.get('f10')
        amount = r.get('f6')
        prev_close = r.get('f18')
        high = r.get('f15')
        low = r.get('f16')
        seal_amount = r.get('f62')

        # 排除停牌
        if not price or not prev_close or float(prev_close) == 0:
            continue
        # 排除ST
        if name and ('ST' in str(name).upper()):
            continue

        total_scanned += 1

        price = float(price)
        prev_close = float(prev_close)
        pct = float(pct or 0.0)
        vol_ratio = float(vol_ratio or 0.0)
        amount = float(amount or 0.0)
        high = float(high or 0.0)
        low = float(low or 0.0)
        seal_amount = float(seal_amount or 0.0)

        # 竞价阶段最新价≈竞价价
        open_pct = round((price - prev_close) / prev_close * 100, 2)

        item = {
            'code': code,
            'name': name,
            'price': price,
            'open_pct': open_pct,
            'pct': pct,
            'vol_ratio': vol_ratio,
            'amount': amount,
            'high': high,
            'low': low,
            'prev_close': prev_close,
            'seal_amount': seal_amount,
        }

        # NUCLEAR_BUTTON（核按钮优先判定，避免跌停票被抢筹误判）
        if open_pct <= -5.0 or (open_pct <= -3.0 and vol_ratio >= 2.0):
            item['signal'] = 'NUCLEAR_BUTTON'
            item['signalLabel'] = '竞价核按钮'
            item['_intensity'] = abs(open_pct)  # 跌得越多越靠前
            nuclear_button.append(item)

        # LOCKED_LIMIT_UP（一字封单）
        elif open_pct >= 9.8:
            item['signal'] = 'LOCKED_LIMIT_UP'
            item['signalLabel'] = '一字封单'
            item['_intensity'] = open_pct + (seal_amount / 1e8)  # 封单额加成
            locked_limit.append(item)

        # SUPER_GRAB（超预期抢筹）
        elif open_pct >= 2.0 and vol_ratio >= 2.0:
            item['signal'] = 'SUPER_GRAB'
            item['signalLabel'] = '超预期抢筹'
            item['_intensity'] = open_pct * vol_ratio  # 开涨幅×量比
            super_grab.append(item)

        # FAKE_HIGH（缩量假高开）
        elif open_pct >= 3.0 and vol_ratio < 1.0:
            item['signal'] = 'FAKE_HIGH'
            item['signalLabel'] = '缩量假高开'
            item['_intensity'] = open_pct  # 高开越多越危险
            fake_high.append(item)

    # 每类信号取 top 30，按强度降序
    super_grab.sort(key=lambda x: -x['_intensity'])
    nuclear_button.sort(key=lambda x: -x['_intensity'])
    locked_limit.sort(key=lambda x: -x['_intensity'])
    fake_high.sort(key=lambda x: -x['_intensity'])

    super_grab = super_grab[:30]
    nuclear_button = nuclear_button[:30]
    locked_limit = locked_limit[:30]
    fake_high = fake_high[:30]

    # 合并去重（同一只票可能被多类信号选中，保留强度最高的）
    seen = set()
    scan_items = []
    for pool in [nuclear_button, locked_limit, super_grab, fake_high]:
        for item in pool:
            if item['code'] in seen:
                continue
            seen.add(item['code'])
            item.pop('_intensity', None)
            scan_items.append(item)

    return {
        'status': 'ok',
        'scan_items': scan_items,
        'grabCount': len(super_grab),
        'nuclearCount': len(nuclear_button),
        'fakeHighCount': len(fake_high),
        'lockedCount': len(locked_limit),
        'total_scanned': total_scanned,
        'updated_at': dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
