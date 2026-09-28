# -*- coding: utf-8 -*-
"""
Test script for Promotion Rate, Broken Ratio, and Emotion Gauges
"""
import urllib.request
import json
import datetime as dt

def get_trading_dates():
    # 获取今天和上一个交易日日期 (排除周末)
    today = dt.date.today()
    days = []
    cur = today
    while len(days) < 2:
        if cur.weekday() < 5: # 周一到周五
            days.append(cur.strftime('%Y%m%d'))
        cur -= dt.timedelta(days=1)
    return days[0], days[1] # today_ymd, prev_ymd

def fetch_zt_pool(ymd):
    u = f'https://push2ex.eastmoney.com/getTopicZTPool?ut=7eea3edcaed734bea9cbfc24409ed989&dpt=wz.ztzt&Pageindex=0&pagesize=300&sort=fbt:asc&date={ymd}'
    req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=4) as r:
            j = json.loads(r.read().decode('utf-8'))
            return (j.get('data') or {}).get('pool') or []
    except Exception as e:
        print(f"Error fetching ZT for {ymd}: {e}")
        return []

def fetch_zb_pool(ymd):
    u = f'https://push2ex.eastmoney.com/getTopicZBPool?ut=7eea3edcaed734bea9cbfc24409ed989&dpt=wz.ztzt&Pageindex=0&pagesize=300&sort=fbt:asc&date={ymd}'
    req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=4) as r:
            j = json.loads(r.read().decode('utf-8'))
            return (j.get('data') or {}).get('pool') or []
    except Exception as e:
        print(f"Error fetching ZB for {ymd}: {e}")
        return []

def test_promotion_metrics():
    today_ymd, prev_ymd = get_trading_dates()
    print(f"Today: {today_ymd}, Prev: {prev_ymd}")

    today_zt = fetch_zt_pool(today_ymd)
    today_zb = fetch_zb_pool(today_ymd)
    prev_zt = fetch_zt_pool(prev_ymd)

    print(f"Today ZT: {len(today_zt)}, Today ZB: {len(today_zb)}, Prev ZT: {len(prev_zt)}")

    # 1. 炸板率与封板成功率
    total_touch = len(today_zt) + len(today_zb)
    broken_rate = round(len(today_zb) / total_touch * 100, 1) if total_touch > 0 else 0.0
    seal_rate = round(len(today_zt) / total_touch * 100, 1) if total_touch > 0 else 0.0
    print(f"\n1. 封板率: {seal_rate}% | 炸板率: {broken_rate}% (触板总数: {total_touch})")

    # 2. 最高板龙头
    max_lbc = 0
    leader_stock = None
    for z in today_zt:
        lbc = int(z.get('lbc', 1))
        if lbc > max_lbc:
            max_lbc = lbc
            leader_stock = z
    if leader_stock:
        print(f"2. 当前最高板: {max_lbc} 连板 [{leader_stock.get('c')} {leader_stock.get('n')}] 题材: {leader_stock.get('hy')}")

    # 3. 连板梯队晋级分析
    # 分组昨天首板和连板标的
    prev_1b = [z.get('c') for z in prev_zt if int(z.get('lbc', 1)) == 1]
    prev_2b = [z.get('c') for z in prev_zt if int(z.get('lbc', 1)) == 2]
    prev_multi = [z.get('c') for z in prev_zt if int(z.get('lbc', 1)) >= 2]

    # 今天成功涨停的
    today_zt_codes = {z.get('c'): int(z.get('lbc', 1)) for z in today_zt}

    # 晋级二板的
    succ_1to2 = [c for c in prev_1b if today_zt_codes.get(c, 0) >= 2]
    rate_1to2 = round(len(succ_1to2) / len(prev_1b) * 100, 1) if prev_1b else 0.0

    # 晋级三板的
    succ_2to3 = [c for c in prev_2b if today_zt_codes.get(c, 0) >= 3]
    rate_2to3 = round(len(succ_2to3) / len(prev_2b) * 100, 1) if prev_2b else 0.0

    # 连板继续晋级的
    succ_multi = [c for c in prev_multi if today_zt_codes.get(c, 0) > 2]
    rate_multi = round(len(succ_multi) / len(prev_multi) * 100, 1) if prev_multi else 0.0

    print(f"\n3. 梯队晋级率:")
    print(f"   首板 -> 二板晋级率: {rate_1to2}% ({len(succ_1to2)} / {len(prev_1b)})")
    print(f"   二板 -> 三板晋级率: {rate_2to3}% ({len(succ_2to3)} / {len(prev_2b)})")
    print(f"   高标连板晋级率:     {rate_multi}% ({len(succ_multi)} / {len(prev_multi)})")

if __name__ == '__main__':
    test_promotion_metrics()
