# -*- coding: utf-8 -*-
"""历史回放模拟自动交易 —— 冒烟测试"""
import sys, os, json
_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts')
sys.path.insert(0, _SCRIPTS)
os.chdir(_SCRIPTS)

import paper_trading as pt

for strategy in ('chan', 'ma'):
    for code in ('600519', '300750', '000001'):
        print('=' * 72)
        print(f'策略={strategy}  代码={code}')
        r = pt.run_replay(code, strategy=strategy, days=250, initial_cash=100000)
        if r.get('status') != 'ok':
            print('  ', r.get('msg')); continue
        print(f"  回放K线      : {r['bars']} 根")
        print(f"  期末权益     : ¥{r['final_equity']:,.2f}  (初始 ¥{r['initial_cash']:,.0f})")
        print(f"  总收益率     : {r['total_return_pct']:+.2f}%")
        print(f"  最大回撤     : {r['max_drawdown_pct']:.2f}%")
        print(f"  成交笔数     : {r['trades']}  (完整回合 {r['round_trips']})")
        print(f"  胜率         : {r['win_rate_pct']:.1f}%  ({r['win']}胜/{r['loss']}负)")
        print(f"  盈亏比       : {r['profit_loss_ratio']}")
        print(f"  总佣金/印花  : ¥{r['total_commission']:.2f} / ¥{r['total_stamp_duty']:.2f}")
        print(f"  被拒委托     : {r['rejected']}")
        if r['reject_samples']:
            for x in r['reject_samples'][:3]:
                print(f"      {x['date']} {x['side']} -> {x['reason']}")
        print("  前3笔成交:")
        for t in r['trade_log'][:3]:
            print(f"      {t['date']} {t['side']:4} {t['price']:>8.2f} x{t['shares']:>5}  {t.get('reason','')[:36]}")
