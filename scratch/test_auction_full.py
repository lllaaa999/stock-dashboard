import sys, os, json, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import stock_dashboard as sd

def build_auction_radar():
    t0 = dt.datetime.now()
    # 1. 获取最近有效交易日的 ZT 与 ZB 池
    y_zt = []
    y_zb = []
    y_date = ''
    base = dt.date.today()
    for i in range(1, 10):
        d_str = (base - dt.timedelta(days=i)).strftime('%Y%m%d')
        p = sd._pool('ZT', d_str)
        if p:
            y_zt = p
            y_date = d_str
            y_zb = sd._pool('ZB', d_str)
            break

    if not y_zt:
        return {'status': 'error', 'msg': '无近期涨停数据'}

    # 2. 批量拉取昨日涨停股与炸板股的今日实时行情 (Tencent 毫秒级)
    all_targets = {}
    for d in y_zt:
        all_targets[d['c']] = {'name': d.get('n', ''), 'src': 'ZT', 'lbc': d.get('lbc', 1), 'hybk': d.get('hybk', ''), 'zbc': d.get('zbc', 0)}
    for d in y_zb:
        if d['c'] not in all_targets:
            all_targets[d['c']] = {'name': d.get('n', ''), 'src': 'ZB', 'lbc': 0, 'hybk': d.get('hybk', ''), 'zbc': d.get('zbc', 1)}

    codes = [('sh' if c.startswith(('6', '5', '9')) else 'sz') + c for c in all_targets]
    
    # 分批批量拉取 (每次最多80只)
    quotes = {}
    for i in range(0, len(codes), 80):
        chunk = codes[i:i+80]
        try:
            raw = sd.http('https://qt.gtimg.cn/q=' + ','.join(chunk), gbk=True, timeout=5)
            for line in raw.split(';'):
                if '=' not in line: continue
                parts = line.split('"')[1].split('~')
                if len(parts) > 38 and parts[4] and parts[5]:
                    c = parts[2]
                    prev_close = float(parts[4])
                    if prev_close <= 0: continue
                    open_p = float(parts[5])
                    curr_p = float(parts[3])
                    high_p = float(parts[33])
                    low_p = float(parts[34])
                    pct = float(parts[32]) if parts[32] else 0.0
                    open_pct = round((open_p - prev_close) / prev_close * 100, 2)
                    high_pct = round((high_p - prev_close) / prev_close * 100, 2)
                    drop_from_high = round(pct - high_pct, 2)
                    vol_ratio = float(parts[49]) if len(parts) > 49 and parts[49] else 1.0
                    turnover = float(parts[38]) if parts[38] else 0.0
                    amount = float(parts[37]) if parts[37] else 0.0 # 万元
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
            print("Tencent chunk error:", e)

    # 3. 统计昨日涨停股在今日的综合溢价
    zt_stats_items = []
    for d in y_zt:
        c = d['c']
        q = quotes.get(c)
        if q:
            merged = dict(q)
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
            'sentiment_tag': '超强接力' if avg_open > 2.5 else ('温和溢价' if avg_open > 0 else ('接力偏弱' if avg_open > -1.5 else '接力极度恶化'))
        }
    else:
        premium_summary = {}

    # 4. 弱转强标的 (超预期高开 + 带量)
    # 条件: 1) 昨日炸板但今日高开>1.5% 且量比>1.5; 2) 或昨日换手板今日超预期高开>3%
    weak_to_strong = []
    zb_items = []
    zt_codes = {x['code'] for x in zt_stats_items}
    for d in y_zb:
        c = d.get('c')
        if c in quotes and c not in zt_codes:
            merged = dict(quotes[c])
            merged.update(all_targets.get(c, {}))
            zb_items.append(merged)

    for item in zt_stats_items + zb_items:
        # 炸板转强
        if item.get('src') == 'ZB' and item['open_pct'] >= 1.5 and item['vol_ratio'] >= 1.5:
            reason = f"昨炸板(今开{item['open_pct']:+.1f}%,量比{item['vol_ratio']})"
            weak_to_strong.append(dict(item, reason=reason))
        # 烂板转强 (昨曾炸板多次但回封，今高开>2.5%)
        elif item.get('zbc', 0) >= 2 and item['open_pct'] >= 2.5 and item['vol_ratio'] >= 1.5:
            reason = f"昨炸{item.get('zbc')}次(今高开{item['open_pct']:+.1f}%,量比{item['vol_ratio']})"
            weak_to_strong.append(dict(item, reason=reason))
        # 弱板转高开加速 (昨首板换手率高，今高开>4%且量比>2)
        elif item.get('lbc', 1) == 1 and item['open_pct'] >= 4.0 and item['vol_ratio'] >= 2.0:
            reason = f"昨首板(今加速高开{item['open_pct']:+.1f}%,量比{item['vol_ratio']})"
            weak_to_strong.append(dict(item, reason=reason))

    weak_to_strong.sort(key=lambda x: -x['open_pct'])

    # 5. 竞价爆量与一字板
    auction_boom = [x for x in zt_stats_items if x['vol_ratio'] >= 3.0 or x['is_one_word']]
    auction_boom.sort(key=lambda x: -x['vol_ratio'])

    # 6. 大面亏钱榜 (日内天地大面 / 炸板杀跌)
    # 取全部有行情记录的股票中 drop_from_high 最惨的 + 跌停股
    big_loss_candidates = list(quotes.values())
    
    # 额外补充全市场跌幅榜（EastMoney）以捕捉全市场天地板
    try:
        url = 'https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=20&po=0&np=1&fltt=2&fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f12,f14,f2,f3,f15,f16,f18'
        raw_em = sd.http(url, timeout=3)
        diff = json.loads(raw_em).get('data', {}).get('diff', [])
        for d in diff:
            c = str(d.get('f12'))
            if c not in quotes:
                prev_c = float(d.get('f18', 0))
                curr_c = float(d.get('f2', 0))
                high_c = float(d.get('f15', 0))
                pct = float(d.get('f3', 0))
                if prev_c > 0:
                    high_pct = round((high_c - prev_c) / prev_c * 100, 2)
                    drop = round(pct - high_pct, 2)
                    big_loss_candidates.append({
                        'code': c,
                        'name': str(d.get('f14')),
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
    except Exception as e:
        print("EastMoney losers fallback err:", e)

    big_loss = sorted([x for x in big_loss_candidates if x['drop_from_high'] <= -4.0 or x['pct'] <= -7.0], key=lambda x: x['drop_from_high'])[:12]

    elapsed = round((dt.datetime.now() - t0).total_seconds(), 2)
    return {
        'status': 'ok',
        'elapsed': elapsed,
        'premium_summary': premium_summary,
        'weak_to_strong': weak_to_strong[:10],
        'auction_boom': auction_boom[:10],
        'big_loss': big_loss,
        'updated_at': dt.datetime.now().strftime('%H:%M:%S')
    }

if __name__ == '__main__':
    res = build_auction_radar()
    print("Elapsed:", res['elapsed'])
    print("Premium Summary:", res['premium_summary'])
    print(f"Weak to Strong count: {len(res['weak_to_strong'])}")
    print(f"Auction Boom count: {len(res['auction_boom'])}")
    print(f"Big Loss count: {len(res['big_loss'])}")
