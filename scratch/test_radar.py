import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import stock_dashboard as sd
import datetime as dt

def test_auction_and_risk():
    today = dt.date.today().strftime('%Y%m%d')
    # 查找最近的两个交易日
    prev_days = []
    base = dt.date.today()
    for i in range(1, 10):
        d_str = (base - dt.timedelta(days=i)).strftime('%Y%m%d')
        p = sd._pool('ZT', d_str)
        if p:
            prev_days.append((d_str, p))
            if len(prev_days) >= 2:
                break
    
    if not prev_days:
        print("未找到近期涨停池数据")
        return

    y_date, y_zt = prev_days[0]
    print(f"昨日交易日: {y_date}, 涨停家数: {len(y_zt)}")

    # 1. 批量拉取昨日涨停股在当天的实时行情 (极速 Tencent 批量)
    codes = [('sh' if d['c'].startswith(('6','5','9')) else 'sz') + d['c'] for d in y_zt]
    raw = sd.http('https://qt.gtimg.cn/q=' + ','.join(codes[:80]), gbk=True)

    items = []
    for line in raw.split(';'):
        if '=' not in line:
            continue
        parts = line.split('"')[1].split('~')
        if len(parts) > 38 and parts[4] and parts[5]:
            code = parts[2]
            name = parts[1]
            price = float(parts[3])
            prev_close = float(parts[4])
            open_p = float(parts[5])
            high_p = float(parts[33])
            low_p = float(parts[34])
            pct = float(parts[32]) if parts[32] else 0.0
            turnover = float(parts[38]) if parts[38] else 0.0
            volume_ratio = float(parts[49]) if len(parts) > 49 and parts[49] else 1.0
            amount = float(parts[37]) if parts[37] else 0.0 # 万元
            limit_up = float(parts[47]) if len(parts) > 47 and parts[47] else 0.0
            limit_down = float(parts[48]) if len(parts) > 48 and parts[48] else 0.0

            open_pct = round((open_p - prev_close) / prev_close * 100, 2) if prev_close > 0 else 0.0
            high_pct = round((high_p - prev_close) / prev_close * 100, 2) if prev_close > 0 else 0.0
            drop_from_high = round(pct - high_pct, 2) # 日内回撤

            items.append({
                'code': code,
                'name': name,
                'price': price,
                'prev_close': prev_close,
                'open_price': open_p,
                'open_pct': open_pct,
                'pct': pct,
                'high_pct': high_pct,
                'drop_from_high': drop_from_high,
                'volume_ratio': volume_ratio,
                'amount': round(amount / 10000, 2), # 亿元
                'is_zt': (price >= limit_up - 0.01) if limit_up > 0 else False,
                'is_dt': (price <= limit_down + 0.01) if limit_down > 0 else False,
                'opened_zt': (high_p >= limit_up - 0.01 and price < limit_up - 0.01) if limit_up > 0 else False,
            })

    if items:
        avg_open = sum(x['open_pct'] for x in items) / len(items)
        avg_curr = sum(x['pct'] for x in items) / len(items)
        up_open_count = sum(1 for x in items if x['open_pct'] > 0)
        up_curr_count = sum(1 for x in items if x['pct'] > 0)
        zt_again = sum(1 for x in items if x['is_zt'])
        mian_count = sum(1 for x in items if x['drop_from_high'] <= -6.0)

        print(f"昨日涨停样本数: {len(items)}")
        print(f"今日开盘平均溢价率: {avg_open:+.2f}% (高开率: {up_open_count/len(items)*100:.1f}%)")
        print(f"今日最新平均涨幅: {avg_curr:+.2f}% (红盘率: {up_curr_count/len(items)*100:.1f}%)")
        print(f"连板晋级数: {zt_again}只 | 日内吃大面(高点回撤>=6%): {mian_count}只")

        # 弱转强候选
        weak_to_strong = [x for x in items if x['open_pct'] >= 1.5 and x['volume_ratio'] >= 1.5]
        weak_to_strong.sort(key=lambda x: -x['open_pct'])
        print(f"\n弱转强候选 ({len(weak_to_strong)}只):", [(x['name'], f"开盘{x['open_pct']:+.1f}%", f"现{x['pct']:+.1f}%", f"量比{x['volume_ratio']}") for x in weak_to_strong[:5]])

        # 大面榜 (日内回撤最大)
        big_loss = sorted(items, key=lambda x: x['drop_from_high'])[:10]
        print("\n大面预警榜 TOP5:")
        for x in big_loss[:5]:
            print(f"  {x['name']}({x['code']}): 现价{x['pct']:+.1f}%, 曾冲高{x['high_pct']:+.1f}%, 日内大面回撤: {x['drop_from_high']:+.1f}%")

if __name__ == '__main__':
    test_auction_and_risk()
