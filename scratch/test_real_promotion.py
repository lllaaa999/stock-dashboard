# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import stock_dashboard as sd
import auction_radar as ar

def test():
    days = ar.get_recent_trading_days(2)
    today_ymd, today_zt = days[0]
    prev_ymd, prev_zt = days[1]
    today_zb = sd._pool('ZB', today_ymd) or []

    print(f"Today: {today_ymd} ({len(today_zt)} ZT, {len(today_zb)} ZB) | Prev: {prev_ymd} ({len(prev_zt)} ZT)")

    # 1. 封板率与炸板率
    total = len(today_zt) + len(today_zb)
    broken_rate = round(len(today_zb) / total * 100, 1) if total > 0 else 0.0
    seal_rate = round(len(today_zt) / total * 100, 1) if total > 0 else 0.0
    print(f"封板成功率: {seal_rate}% | 炸板率: {broken_rate}%")

    # 2. 最高板
    max_lbc = 0
    leader = None
    for z in today_zt:
        lbc = int(z.get('lbc', 1))
        if lbc > max_lbc:
            max_lbc = lbc
            leader = z
    if leader:
        print(f"最高板: {max_lbc} 连板 [{leader.get('c')} {leader.get('n')}] 行业: {leader.get('hybk')}")

    # 3. 梯队晋级率
    prev_1b = [z.get('c') for z in prev_zt if int(z.get('lbc', 1)) == 1]
    prev_2b = [z.get('c') for z in prev_zt if int(z.get('lbc', 1)) == 2]
    prev_multi = [z.get('c') for z in prev_zt if int(z.get('lbc', 1)) >= 2]

    today_zt_map = {z.get('c'): int(z.get('lbc', 1)) for z in today_zt}

    succ_1to2 = [c for c in prev_1b if today_zt_map.get(c, 0) >= 2]
    succ_2to3 = [c for c in prev_2b if today_zt_map.get(c, 0) >= 3]
    succ_multi = [c for c in prev_multi if today_zt_map.get(c, 0) > 2]

    rate_1to2 = round(len(succ_1to2) / len(prev_1b) * 100, 1) if prev_1b else 0.0
    rate_2to3 = round(len(succ_2to3) / len(prev_2b) * 100, 1) if prev_2b else 0.0
    rate_multi = round(len(succ_multi) / len(prev_multi) * 100, 1) if prev_multi else 0.0

    print(f"首板->二板晋级率: {rate_1to2}% ({len(succ_1to2)} / {len(prev_1b)})")
    print(f"二板->三板晋级率: {rate_2to3}% ({len(succ_2to3)} / {len(prev_2b)})")
    print(f"高标连板晋级率:   {rate_multi}% ({len(succ_multi)} / {len(prev_multi)})")

if __name__ == '__main__':
    test()
