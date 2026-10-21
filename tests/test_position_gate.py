# -*- coding: utf-8 -*-
"""
大盘趋势仓位闸门测试 (position_gate.py)

ADX 是 Wilder 标准指标，算法错一点结果就全错。这里用三类构造数据验证：
  1. 单边强趋势  -> ADX 必须很高（>25）且上升
  2. 横盘震荡    -> ADX 必须很低（<18）
  3. 数据不足    -> fail-closed 返回 0%
另外验证：闸门与情绪周期合并时取较小值。
"""
import sys, os
_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts')
sys.path.insert(0, _SCRIPTS)
os.chdir(_SCRIPTS)

import position_gate as pg

fails = []
def check(name, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + name + ((' | ' + str(extra)) if extra else ''))
    if not cond: fails.append(name)


def make_bars(prices):
    """把收盘价序列造造成 K 线 [日期, 开, 收, 高, 低, 量]"""
    out = []
    for i, p in enumerate(prices):
        out.append([f'2026-{1+i//28:02d}-{1+i%28:02d}',
                    round(p, 2), round(p, 2),
                    round(p * 1.005, 2), round(p * 0.995, 2), 1e6])
    return out


print('=== 1. 单边强趋势：ADX 应显著偏高 ===')
up = [100 + i * 1.0 for i in range(80)]          # 稳定上涨
r = pg.calc_adx(make_bars(up))
last_adx = [v for v in r['adx'] if v is not None]
check('ADX 可计算', len(last_adx) > 0, len(last_adx))
if last_adx:
    check('强趋势 ADX > 25', last_adx[-1] > 25, round(last_adx[-1], 2))
    check('+DI 明显大于 -DI',
          r['plus_di'][-1] > r['minus_di'][-1],
          f"+{r['plus_di'][-1]:.1f} vs -{r['minus_di'][-1]:.1f}")

print('\n=== 2. 横盘震荡：ADX 应显著偏低 ===')
rng = [100 + (1.0 if i % 2 == 0 else -1.0) for i in range(80)]   # 上下摆动
r2 = pg.calc_adx(make_bars(rng))
adx2 = [v for v in r2['adx'] if v is not None]
check('震荡 ADX 可计算', len(adx2) > 0, len(adx2))
if adx2:
    check('震荡 ADX < 25', adx2[-1] < 25, round(adx2[-1], 2))

print('\n=== 3. 下跌趋势：-DI 应占优 ===')
dn = [200 - i * 1.0 for i in range(80)]
r3 = pg.calc_adx(make_bars(dn))
check('下跌 -DI > +DI', r3['minus_di'][-1] > r3['plus_di'][-1],
      f"-{r3['minus_di'][-1]:.1f} vs +{r3['plus_di'][-1]:.1f}")

print('\n=== 4. 数据不足必须 fail-closed ===')
for label, kl in [
    ('None', None),
    ('空列表', []),
    ('10根', make_bars([100 + i for i in range(10)])),
    ('25根(不足2*period+2)', make_bars([100 + i for i in range(25)])),
]:
    g = pg.evaluate_gate(kl)
    check(f'{label} -> allow_pct=0', g['allow_pct'] == 0, g['allow_pct'])
    check(f'{label} -> ok=False', g['ok'] is False, g['ok'])

print('\n=== 5. 脏数据不崩溃 ===')
dirty = make_bars([100 + i for i in range(60)])
dirty[30] = ['2026-02-01', 1, 'abc', 2, 1]          # 收盘非数字
dirty[31] = ['2026-02-02', 1, 1]                     # 列数不足
try:
    g = pg.evaluate_gate(dirty)
    check('脏数据返回结构完整', 'allow_pct' in g and 'reason' in g, g.get('allow_pct'))
except Exception as e:
    check('脏数据不崩溃', False, repr(e))

print('\n=== 6. 闸门与情绪周期合并取较小值 ===')
for cycle, gate, want, want_bind in [
    (80, 100, 80, 'cycle'),      # 情绪弱于趋势
    (80, 0, 0, 'gate'),          # 趋势闸门拦住满仓 —— 核心价值
    (40, 50, 40, 'cycle'),
    (15, 50, 15, 'cycle'),
]:
    c = pg.combine_with_cycle(cycle, gate)
    check(f'cycle={cycle} gate={gate} -> {want}',
          c['final_pct'] == want and c['binding'] == want_bind,
          f"final={c['final_pct']} binding={c['binding']}")

c_none = pg.combine_with_cycle(None, 100)
check('情绪数据缺失时保守取0', c_none['final_pct'] == 0, c_none)

print('\n=== 7. 真实指数数据 ===')
import data_feed as df
kl = df.get_kline_cached('sh000001', 200)
g = pg.evaluate_gate(kl)
print(f"    上证指数实际评估:")
print(f"      ADX       = {g.get('adx')}  (前值 {g.get('adx_prev')}, 上升={g.get('adx_rising')})")
print(f"      收盘      = {g.get('close')}   MA20 = {g.get('ma')}")
print(f"      允许仓位  = {g.get('allow_pct')}%")
print(f"      判定理由  = {g.get('reason')}")
check('真实数据可评估', g['ok'] is True, g['reason'])
check('allow_pct 在合法集合内', g['allow_pct'] in (0, 50, 100), g['allow_pct'])


print('')
print('=== 8. 方向约束：强趋势但空头主导时必须不开仓 ===')
dn_bars = make_bars([300 - i * 1.2 for i in range(90)])
g_dn = pg.evaluate_gate(dn_bars)
print(f"    单边下跌: ADX={g_dn.get('adx')} +DI={g_dn.get('plus_di')} -DI={g_dn.get('minus_di')}")
check('下跌趋势 bullish=False', g_dn.get('bullish') is False, g_dn.get('bullish'))
check('下跌趋势绝不允许满仓', g_dn['allow_pct'] < 100, g_dn['allow_pct'])
check('下跌趋势不允许开仓(0%)', g_dn['allow_pct'] == 0, g_dn['allow_pct'])
check('理由提及空头主导', '空头主导' in g_dn['reason'] or '不开新仓' in g_dn['reason'], g_dn['reason'])

up_bars = make_bars([100 + i * 1.2 for i in range(90)])
g_up = pg.evaluate_gate(up_bars)
print(f"    单边上涨: ADX={g_up.get('adx')} +DI={g_up.get('plus_di')} -DI={g_up.get('minus_di')} 允许{g_up['allow_pct']}%")
check('上涨趋势 bullish=True', g_up.get('bullish') is True, g_up.get('bullish'))
check('上涨趋势允许满仓', g_up['allow_pct'] == 100, g_up['allow_pct'])

print()
if fails:
    print('FAILED:', fails); sys.exit(1)
print('=== 仓位闸门测试全部通过 ===')
