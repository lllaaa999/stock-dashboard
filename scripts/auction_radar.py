# -*- coding: utf-8 -*-
"""
9:25 早盘集合竞价雷达 + 亏钱效应大面榜
- 昨日涨停今日溢价率 (接力情绪晴雨表)
- 弱转强异动 (超预期接力)
- 竞价爆量与一字封单
- 日内天地大面榜 (风险警报)
"""
import os, sys, json, datetime as dt
import stock_dashboard as sd

def get_recent_trading_days(n=2):
    """回溯获取最近 n 个有涨停池数据的交易日"""
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

def get_auction_radar():
    """计算 9:25 集合竞价雷达与亏钱效应大面榜"""
    t0 = dt.datetime.now()
    trading_days = get_recent_trading_days(2)
    if not trading_days:
        return {'status': 'error', 'msg': '无近期涨停池数据'}

    # 判断今日是否已有数据，或者回溯昨天
    # 如果 trading_days[0] 是今天，则昨日为 trading_days[1]
    # 否则 trading_days[0] 就是最近的完整交易日（用作昨日涨停池分析）
    today_str = dt.date.today().strftime('%Y%m%d')
    if len(trading_days) >= 2:
        t_date, t_zt = trading_days[0]
        y_date, y_zt = trading_days[1]
    else:
        t_date, t_zt = trading_days[0]
        y_date, y_zt = trading_days[0]

    t_zb = sd._pool('ZB', t_date) or []
    y_zb = sd._pool('ZB', y_date) or []

    # 梯队晋级与炸板率统计 (吸纳 vibe-astock / easy-stock 核心指标)
    total_touch = len(t_zt) + len(t_zb)
    broken_rate = round(len(t_zb) / total_touch * 100, 1) if total_touch > 0 else 0.0
    seal_rate = round(len(t_zt) / total_touch * 100, 1) if total_touch > 0 else 0.0

    max_lbc = 0
    leader = None
    for z in t_zt:
        lbc = int(z.get('lbc', 1))
        if lbc > max_lbc:
            max_lbc = lbc
            leader = z

    prev_1b = [z.get('c') for z in y_zt if int(z.get('lbc', 1)) == 1]
    prev_2b = [z.get('c') for z in y_zt if int(z.get('lbc', 1)) == 2]
    prev_multi = [z.get('c') for z in y_zt if int(z.get('lbc', 1)) >= 2]

    today_zt_map = {z.get('c'): int(z.get('lbc', 1)) for z in t_zt}
    succ_1to2 = [c for c in prev_1b if today_zt_map.get(c, 0) >= 2]
    succ_2to3 = [c for c in prev_2b if today_zt_map.get(c, 0) >= 3]
    succ_multi = [c for c in prev_multi if today_zt_map.get(c, 0) > 2]

    promote_1_2 = round(len(succ_1to2) / len(prev_1b) * 100, 1) if prev_1b else 0.0
    promote_2_3 = round(len(succ_2to3) / len(prev_2b) * 100, 1) if prev_2b else 0.0
    promote_high = round(len(succ_multi) / len(prev_multi) * 100, 1) if prev_multi else 0.0

    highest_leader = {
        'name': leader.get('n', '-') if leader else '-',
        'code': leader.get('c', '-') if leader else '-',
        'lbc': max_lbc,
        'industry': leader.get('hybk', '-') if leader else '-'
    } if leader else None

    promotion_metrics = {
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
            'fbt': d.get('fbt', '')
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
                'fbt': ''
            }

    codes = [('sh' if c.startswith(('6', '5', '9')) else 'sz') + c for c in all_targets if c]

    # 分批极速拉取实时行情 (Tencent 毫秒级)
    quotes = {}
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
                    drop_from_high = round(pct - high_pct, 2)
                    vol_ratio = float(parts[49]) if len(parts) > 49 and parts[49] else 1.0
                    turnover = float(parts[38]) if parts[38] else 0.0
                    amount = float(parts[37]) if parts[37] else 0.0  # 万元
                    limit_up = float(parts[47]) if len(parts) > 47 and parts[47] else 0.0
                    limit_down = float(parts[48]) if len(parts) > 48 and parts[48] else 0.0

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
                        'amount_yi': round(amount / 10000, 2),
                        'is_zt': (curr_p >= limit_up - 0.01) if limit_up > 0 else False,
                        'is_dt': (curr_p <= limit_down + 0.01) if limit_down > 0 else False,
                        'is_one_word': (open_pct >= 9.8 and curr_p == open_p and low_p == open_p),
                    }
        except Exception as e:
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

        premium_summary = {
            'y_date': y_date,
            'total_zt': len(zt_stats_items),
            'avg_open_pct': avg_open,
            'avg_curr_pct': avg_curr,
            'open_positive_rate': round(up_open_count / len(zt_stats_items) * 100, 1),
            'curr_positive_rate': round(up_curr_count / len(zt_stats_items) * 100, 1),
            'promote_zt_count': zt_again,
            'dt_count': dt_count,
            'mian_count': mian_count,
            'sentiment_tag': sentiment_tag,
            'sentiment_color': sentiment_color,
        }
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
    for item in zt_stats_items + zb_items:
        # 炸板转强: 昨炸板但今日高开>1.5% 且量比>1.5
        if item.get('src') == 'ZB' and item['open_pct'] >= 1.5 and item['vol_ratio'] >= 1.5:
            reason = f"昨炸板(今开{item['open_pct']:+.1f}%,量比{item['vol_ratio']:.1f})"
            weak_to_strong.append(dict(item, reason=reason))
        # 烂板转强: 昨曾炸板多次但回封，今高开>2.5%
        elif item.get('zbc', 0) >= 2 and item['open_pct'] >= 2.5 and item['vol_ratio'] >= 1.5:
            reason = f"昨炸{item.get('zbc')}次(今高开{item['open_pct']:+.1f}%,量比{item['vol_ratio']:.1f})"
            weak_to_strong.append(dict(item, reason=reason))
        # 弱板转高开加速: 昨首板换手，今高开>4%且量比>2
        elif item.get('lbc', 1) == 1 and item['open_pct'] >= 4.0 and item['vol_ratio'] >= 2.0:
            reason = f"昨首板(今加速高开{item['open_pct']:+.1f}%,量比{item['vol_ratio']:.1f})"
            weak_to_strong.append(dict(item, reason=reason))

    weak_to_strong.sort(key=lambda x: -x['open_pct'])

    # 3. 竞价爆量与一字板
    auction_boom = [x for x in zt_stats_items if x['vol_ratio'] >= 3.0 or x['is_one_word']]
    auction_boom.sort(key=lambda x: -x['vol_ratio'])

    # 4. 亏钱效应大面榜 (天地大面 / 冲高大回撤 / 跌停)
    big_loss_candidates = list(quotes.values())
    try:
        url = 'https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=20&po=0&np=1&fltt=2&fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f12,f14,f2,f3,f15,f16,f18'
        raw_em = sd.http(url, timeout=3)
        diff = json.loads(raw_em).get('data', {}).get('diff', [])
        for d in diff:
            c = str(d.get('f12', ''))
            if c and c not in quotes:
                prev_c = float(d.get('f18', 0))
                curr_c = float(d.get('f2', 0))
                high_c = float(d.get('f15', 0))
                pct = float(d.get('f3', 0))
                if prev_c > 0:
                    high_pct = round((high_c - prev_c) / prev_c * 100, 2)
                    drop = round(pct - high_pct, 2)
                    big_loss_candidates.append({
                        'code': c,
                        'name': str(d.get('f14', '')),
                        'price': curr_c,
                        'prev_close': prev_c,
                        'open_pct': 0,
                        'pct': pct,
                        'high_pct': high_pct,
                        'drop_from_high': drop,
                        'vol_ratio': 1.0,
                        'amount_yi': 0,
                        'is_zt': False,
                        'is_dt': (pct <= -9.5),
                        'is_one_word': False,
                    })
    except Exception:
        pass

    big_loss = sorted([x for x in big_loss_candidates if x['drop_from_high'] <= -4.0 or x['pct'] <= -7.0],
                      key=lambda x: x['drop_from_high'])[:12]

    elapsed = round((dt.datetime.now() - t0).total_seconds(), 2)
    return {
        'status': 'ok',
        'elapsed': elapsed,
        'promotion_metrics': promotion_metrics,
        'premium_summary': premium_summary,
        'weak_to_strong': weak_to_strong[:12],
        'auction_boom': auction_boom[:12],
        'big_loss': big_loss,
        'updated_at': dt.datetime.now().strftime('%H:%M:%S')
    }
