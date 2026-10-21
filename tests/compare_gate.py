# -*- coding: utf-8 -*-
"""
仓位闸门效果对照实验：同一标的、同一策略，只切换 use_gate

目的：验证「大盘趋势闸门」到底有没有用，而不是想当然地加一层。
对照组 = 直接按信号交易；实验组 = 信号 + 大盘闸门。
"""
import sys, os
_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts')
sys.path.insert(0, _SCRIPTS)
os.chdir(_SCRIPTS)

import paper_trading as pt

CASES = [
    ('000001', 'chan'), ('000001', 'ma'),
    ('300750', 'chan'), ('300750', 'ma'),
    ('002594', 'chan'), ('002594', 'ma'),
    ('600036', 'chan'),
]

print('=' * 96)
print(f"{'标的':>8} {'策略':>5} | {'无闸门收益':>10} {'回撤':>7} {'回合':>4} {'胜率':>6} | "
      f"{'有闸门收益':>10} {'回撤':>7} {'回合':>4} {'胜率':>6} | {'拦截':>4} {'收益差':>8}")
print('=' * 96)

rows = []
for code, strat in CASES:
    off = pt.run_replay(code, strategy=strat, days=250, use_gate=False)
    on = pt.run_replay(code, strategy=strat, days=250, use_gate=True)
    if off.get('status') != 'ok' or on.get('status') != 'ok':
        print(f"{code:>8} {strat:>5} | 数据不足，跳过")
        continue
    r_off = off['total_return_pct']; r_on = on['total_return_pct']
    d_off = off['max_drawdown_pct']; d_on = on['max_drawdown_pct']
    diff = r_on - r_off
    blocks = on.get('gate_blocks', 0)
    rows.append((code, strat, r_off, r_on, d_off, d_on, diff, blocks,
                 off['round_trips'], on['round_trips']))
    print(f"{code:>8} {strat:>5} | {r_off:>9.2f}% {d_off:>6.2f}% {off['round_trips']:>4} "
          f"{off['win_rate_pct']:>5.1f}% | {r_on:>9.2f}% {d_on:>6.2f}% {on['round_trips']:>4} "
          f"{on['win_rate_pct']:>5.1f}% | {blocks:>4} {diff:>+7.2f}%")

print('=' * 96)
if rows:
    n = len(rows)
    avg_off = sum(r[2] for r in rows) / n
    avg_on = sum(r[3] for r in rows) / n
    avg_dd_off = sum(r[4] for r in rows) / n
    avg_dd_on = sum(r[5] for r in rows) / n
    wins = sum(1 for r in rows if r[6] > 0.01)
    losses = sum(1 for r in rows if r[6] < -0.01)
    print(f"  样本数            : {n}")
    print(f"  平均收益 无闸门   : {avg_off:+.2f}%")
    print(f"  平均收益 有闸门   : {avg_on:+.2f}%")
    print(f"  平均回撤 无闸门   : {avg_dd_off:.2f}%")
    print(f"  平均回撤 有闸门   : {avg_dd_on:.2f}%")
    print(f"  闸门让收益变好    : {wins} 例")
    print(f"  闸门让收益变差    : {losses} 例")
    print(f"  结论              : 收益{'改善' if avg_on > avg_off else '变差'} "
          f"{avg_on - avg_off:+.2f}%，回撤{'降低' if avg_dd_on < avg_dd_off else '上升'} "
          f"{avg_dd_on - avg_dd_off:+.2f}%")
    print()
    print('  注意：样本仅 %d 个、跨度约一年，不足以证明统计显著性。' % n)
    print('        闸门的价值主要在"避免在下跌趋势里满仓"这一尾部风险，')
    print('        单看平均收益可能看不出优势。')
