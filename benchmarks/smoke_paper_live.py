# -*- coding: utf-8 -*-
"""实时纸上交易 —— 冒烟测试（连跑3次巡检，验证状态持久化）"""
import sys, os, json
_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts')
sys.path.insert(0, _SCRIPTS)
os.chdir(_SCRIPTS)

import paper_trading as pt

# 首次运行用干净状态
if os.path.exists(pt.PAPER_STATE):
    os.remove(pt.PAPER_STATE)
for f in (pt.PAPER_TRADES, pt.PAPER_EQUITY):
    if os.path.exists(f):
        os.remove(f)

for tick in range(1, 4):
    print('=' * 72)
    print(f'第 {tick} 次巡检')
    r = pt.run_paper_tick(strategy='chan', codes=["000001","300750","002594"],
                          initial_cash=100000)
    print(f"  时间      : {r['ts']}")
    print(f"  策略      : {r['strategy']}")
    for a in r['actions']:
        filled = '成交' if a.get('filled') else ('持有' if a['action'] in ('hold',) else '未成交')
        print(f"    {a['code']} {a['action']:5} {filled:4} @{a.get('price', 0):.2f}  {a.get('reason','')[:40]}")
    s = r['snapshot']
    print(f"  现金      : ¥{s['cash']:,.2f}")
    print(f"  持仓市值  : ¥{s['market_value']:,.2f}")
    print(f"  总权益    : ¥{s['equity']:,.2f}  ({s['return_pct']:+.2f}%)")
    print(f"  持仓      : {s['positions']}")
    if r['trades_this_tick']:
        print(f"  本笔成交  : {len(r['trades_this_tick'])} 笔")
    if r['rejects_this_tick']:
        print(f"  被拒      : {r['rejects_this_tick']}")

print('=' * 72)
print('累计报告')
rep = pt.paper_report()
print(f"  巡检次数  : {rep['runs']}")
print(f"  成交笔数  : {rep['trades']}  (完整回合 {rep['round_trips']})")
print(f"  胜率      : {rep['win_rate_pct']}%")
print(f"  总佣金    : ¥{rep['total_commission']:.2f}")
print(f"  总印花税  : ¥{rep['total_stamp_duty']:.2f}")
print(f"  最新权益  : {rep['latest_equity']}")
print()
print('落盘文件:')
for f in (pt.PAPER_STATE, pt.PAPER_TRADES, pt.PAPER_EQUITY):
    print(f"  {'存在' if os.path.exists(f) else '缺失'}  {f}")
