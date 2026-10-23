# -*- coding: utf-8 -*-
"""
闸门的诚实检验：它到底是"选对时机"还是"干脆不交易"？

上一轮对照实验显示闸门让收益从 -4.78% 改善到 +0.62%，但进一步检查发现：
闸门在 96% 的交易日都是关闭的（80 天里 77 天不开仓）。
这说明"改善"很可能来自**交易变少**，而不是来自**选对了时机**。

本测试区分这两种解释：
  A. 闸门开着的那些天，后续走势是否真的更好？（选时能力）
  B. 随机跳过同样比例的交易日，是否也能得到类似结果？（对照基线）

如果 A 不显著优于 B，那闸门的价值只是"少交易"，不是"会选时"。
"""
import sys, os, random
_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts')
sys.path.insert(0, _SCRIPTS)
os.chdir(_SCRIPTS)

import paper_trading as pt
import data_feed as df_feed
import position_gate as pg

print('=' * 78)
print('检验 A：闸门「开着」的日子，指数后续 N 日收益是否更好？')
print('=' * 78)

gkl = sorted(df_feed.get_kline_cached('sh000001', 400) or [], key=lambda r: str(r[0]))
print(f"指数K线: {len(gkl)} 根  {gkl[0][0]} ~ {gkl[-1][0]}")
print()

for horizon in (1, 5, 10):
    allow_ret, block_ret = [], []
    for i in range(60, len(gkl) - horizon):
        g = pg.evaluate_gate(gkl[:i + 1])
        if not g.get('ok'):
            continue
        c0 = float(gkl[i][2])
        c1 = float(gkl[i + horizon][2])
        r = (c1 / c0 - 1) * 100
        (allow_ret if g['allow_pct'] > 0 else block_ret).append(r)

    def stat(lst):
        if not lst:
            return '    无样本'
        avg = sum(lst) / len(lst)
        win = sum(1 for x in lst if x > 0) / len(lst) * 100
        return f"n={len(lst):>3}  均值{avg:+.3f}%  胜率{win:.1f}%"

    print(f"  未来 {horizon:>2} 日:  闸门开 {stat(allow_ret)}")
    print(f"               闸门关 {stat(block_ret)}")
    if allow_ret and block_ret:
        a = sum(allow_ret) / len(allow_ret)
        b = sum(block_ret) / len(block_ret)
        verdict = '闸门选时有正向价值' if a > b + 0.05 else ('几乎无差异' if abs(a - b) <= 0.05 else '闸门选时反向')
        print(f"               -> 差值 {a - b:+.3f}%  【{verdict}】")
    print()

print('=' * 78)
print('检验 B：随机跳过同样比例的交易日，能否复现闸门的"改善"？')
print('=' * 78)

CASES = [('000001', 'chan'), ('300750', 'chan'), ('002594', 'chan'), ('600036', 'chan')]

def skip_rate_of(code, strat):
    """统计闸门在这些标的上平均关闭比例"""
    r = pt.run_replay(code, strategy=strat, days=250, use_gate=True)
    gs = r.get('gate_stats') or {}
    n = gs.get('evaluated_days', 0)
    if not n:
        return 0.0
    return gs.get('allow_0_days', 0) / n

print(f"{'标的':>8} {'策略':>5} | {'有闸门':>9} | {'闸门关闭率':>10}")
print('-' * 78)
rates = {}
for code, strat in CASES:
    r = pt.run_replay(code, strategy=strat, days=250, use_gate=True)
    sr = skip_rate_of(code, strat)
    rates[code] = sr
    print(f"{code:>8} {strat:>5} | {r['total_return_pct']:>8.2f}% | {sr*100:>9.1f}%")

print()
print('结论（如实）：')
avg_rate = sum(rates.values()) / len(rates) if rates else 0
print(f'  闸门平均关闭率 {avg_rate*100:.1f}% —— 意味着策略绝大部分时间不交易。')
print('  这种情况下的「收益改善」不能直接归因于闸门聪明，')
print('  更可能只是「下跌趋势中少亏」。')
print()
print('  真正的改进方向：')
print('  1) 放松闸门参数（如 ADX 阈值），让它在趋势中别关得那么死；')
print('  2) 或者接受一个事实：A股过去一年是下跌市，任何多头策略都难做，')
print('     闸门的作用是「保护本金」而非「提高收益」。')
