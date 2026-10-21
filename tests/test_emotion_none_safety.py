# -*- coding: utf-8 -*-
"""
情绪算法 None 安全回归测试

背景 (2026-10-18): 把竞价雷达的 rate_1to2 在"休市/非相邻交易日"改为返回 None 后，
core.emotion.emotion_score_v2 里原本写的是 float(eff.get('rate_1to2', 0.0))。
dict.get 的默认值只在**键缺失**时生效，值是 None 时返回 None，float(None) 抛
TypeError，导致整条情绪链路失败、/api/market 的 emotion 变成空对象 {}。

本测试锁定：eff 里各字段为 None 时不得抛异常，且不得把 None 当成 0 去误判背离。
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from core.emotion import emotion_score_v2

fails = []
def check(name, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + name + ((' | ' + str(extra)) if extra else ''))
    if not cond: fails.append(name)

print('=== 1. rate_1to2 为 None 时不得崩溃 ===')
try:
    s, d = emotion_score_v2(n_zt=61, n_zb=49, n_dt=10, max_lb=11,
                            eff={'available': True, 'premium': -1.64, 'rate_1to2': None,
                                 'score': 0.4})
    check('不抛异常', True, f'score={s:.2f} diverge={d}')
    check('分数在 0-100', 0 <= s <= 100)
except Exception as e:
    check('不抛异常', False, repr(e))

print('\n=== 2. 所有可选字段为 None 时也不得崩溃 ===')
try:
    s, d = emotion_score_v2(n_zt=61, n_zb=49, n_dt=10, max_lb=11,
                            eff={'available': True, 'premium': None,
                                 'rate_1to2': None, 'score': None})
    check('不抛异常', True, f'score={s:.2f}')
except Exception as e:
    check('不抛异常', False, repr(e))

print('\n=== 3. rate 缺失不得被当成 0 误判"梯队失血" ===')
# premium 为正、eff_sc 正常，仅因 rate=None 不应判成 score_high_effect_weak
s, d = emotion_score_v2(n_zt=61, n_zb=49, n_dt=10, max_lb=11,
                        eff={'available': True, 'premium': 2.0, 'rate_1to2': None,
                             'score': 0.6})
check('rate=None 且溢价为正时不判弱背离', d != 'score_high_effect_weak', f'diverge={d}')

print('\n=== 4. rate 正常时行为不变(回归保护) ===')
s1, d1 = emotion_score_v2(n_zt=61, n_zb=49, n_dt=10, max_lb=11,
                          eff={'available': True, 'premium': 2.6, 'rate_1to2': 24.2,
                               'score': 0.65})
check('强溢价+晋级率24.2% 不误杀', d1 != 'score_high_effect_weak', f'diverge={d1}')
s2, d2 = emotion_score_v2(n_zt=61, n_zb=49, n_dt=10, max_lb=11,
                          eff={'available': True, 'premium': -2.0, 'rate_1to2': 5.0,
                               'score': 0.2})
check('负溢价触发弱背离', d2 == 'score_high_effect_weak' if s2 >= 50 else True,
      f'score={s2:.1f} diverge={d2}')

print('\n=== 5. eff 不可用时按中性计分 ===')
s3, d3 = emotion_score_v2(n_zt=61, n_zb=49, n_dt=10, max_lb=11, eff={'available': False})
check('不崩溃且 diverge=None', d3 is None, f'score={s3:.2f}')

print()
if fails:
    print('FAILED:', fails); sys.exit(1)
print('=== None 安全回归测试全部通过 ===')
