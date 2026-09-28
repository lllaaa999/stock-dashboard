# -*- coding: utf-8 -*-
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import data_feed as df

def run_tests():
    print("=== 1. Testing Multi-Source Quotes ===")
    q = df.get_realtime_quotes(['600519', '000001', '300750'])
    for c, item in q.items():
        print(f"[{item['source']}] {c} {item['name']}: {item['price']} ({item['pct']:+.2f}%)")

    print("\n=== 2. Testing In-Memory TTL Cache ===")
    # Immediate repeat query should hit cache
    q2 = df.get_realtime_quotes(['600519', '000001', '300750'])
    st = df.CACHE.stats()
    print(f"Cache stats: hits={st['hits']}, misses={st['misses']}, hit_ratio={st['hit_ratio_pct']}%")

    print("\n=== 3. Testing Intraday Trends (分时黄白线) ===")
    trends = df.get_intraday_trends('600519')
    print(f"Trends source: {trends['source']}, points count: {trends['count']}, preClose: {trends['pre_close']}")
    if trends['times']:
        print(f"  First minute: {trends['times'][0]} price={trends['prices'][0]} avg={trends['avg_prices'][0]}")
        print(f"  Last minute:  {trends['times'][-1]} price={trends['prices'][-1]} avg={trends['avg_prices'][-1]}")

    print("\n=== 4. Testing Realtime Order Breakdown (主力/超大单/大单/中单/小单) ===")
    cap = df.get_capital_breakdown('600519')
    today = cap['today']
    print(f"  日期:         {today['date']}")
    print(f"  主力净流入:   {today['main_net']} 亿 (占比: {today['pct']}%)")
    print(f"  超大单净流入: {today['super_net']} 亿")
    print(f"  大单净流入:   {today['large_net']} 亿")
    print(f"  中单净流入:   {today['med_net']} 亿")
    print(f"  小单散户净流入: {today['small_net']} 亿")
    print(f"  近5日历史数据条数: {len(cap['history'])}")

    print("\n=== 5. Testing K-Line Cache ===")
    kl = df.get_kline_cached('sh600519', 60)
    print(f"K-line bars count: {len(kl)}, latest bar: {kl[-1] if kl else 'None'}")
    # Second call should hit cache instantly (<1ms)
    kl2 = df.get_kline_cached('sh600519', 60)
    print(f"Second call K-line bars: {len(kl2)}")

    print("\n=== 6. System Data Status ===")
    status = df.get_system_data_status()
    print("Health Status:", status['sources'])
    print("Final Cache Status:", status['cache'])

if __name__ == '__main__':
    run_tests()
