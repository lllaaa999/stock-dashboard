# -*- coding: utf-8 -*-
"""
竞价雷达辅助函数回归测试

背景 (2026-10-18): 经 opencode 代码审查发现两类问题并修复，此处锁定：

1. 大面榜还有一处 `round(pct - high_pct, 2)` 漏改
   —— 与文件开头已修的 intraday_drawdown_pct 属同类错误
   （两个不同基数的涨幅百分比相减，不是回撤率）。

2. is_one_word 写死 open_pct >= 9.8
   —— 只对 10cm 主板成立。创业板/科创板 20cm、北交所 30cm 一字板
   open_pct 到 19.9/29.9 尚能通过，但 ST 股 5cm 涨停仅 4.9% 会被漏判；
   反过来 20cm 股只涨 10% 远未涨停却被误判成一字板。

3. 东财接口停牌时返回 '-' 或空串，float() 直接抛 ValueError
   会中断整个 for 循环，使大面榜整页空白。
"""
import sys, os
_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts')
sys.path.insert(0, _SCRIPTS)
os.chdir(_SCRIPTS)

import auction_radar as ar

fails = []
def check(name, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + name + ((' | ' + str(extra)) if extra else ''))
    if not cond: fails.append(name)


print('=== 1. _safe_float 兜脏值 ===')
cases = [
    (None, 0.0), ('-', 0.0), ('', 0.0), ('--', 0.0), ('  ', 0.0),
    ('None', 0.0), ('12.5', 12.5), (12.5, 12.5), (0, 0.0), ('abc', 0.0),
]
for raw, want in cases:
    got = ar._safe_float(raw)
    check('_safe_float(%r) == %s' % (raw, want), abs(got - want) < 1e-9, got)
check('自定义默认值生效', ar._safe_float('-', 9.9) == 9.9, ar._safe_float('-', 9.9))

print('\n=== 2. 大面榜回撤必须用最高价为基数 ===')
# 昨收10 最高11.5 现价11.1 -> 真实回撤 (11.1-11.5)/11.5 = -3.48%
real = ar.intraday_drawdown_pct(11.1, 11.5)
check('回撤 = -3.48%', abs(real - (-3.48)) < 0.01, real)
# 旧算法 pct(11%) - high_pct(15%) = -4.00% —— 刚好越过大面 -4% 阈值造成误报
old_style = round((11.1 - 10) / 10 * 100 - (11.5 - 10) / 10 * 100, 2)
check('旧算法确实会误报(-4.00%)', old_style == -4.0, old_style)
check('新算法不越阈值', real > -4.0, real)

print('\n=== 3. _is_one_word_bar 按个股涨停价判定 ===')
# 10cm 一字板: 昨收10 涨停11 开=高=低=现=11
check('10cm 一字板识别', ar._is_one_word_bar(11.0, 11.0, 11.0, 11.0, 10.0) is True)
# 20cm 一字板: 昨收10 涨停12
check('20cm 一字板识别', ar._is_one_word_bar(12.0, 12.0, 12.0, 12.0, 10.0) is True)
# 30cm 一字板: 昨收10 涨停13
check('30cm 一字板识别', ar._is_one_word_bar(13.0, 13.0, 13.0, 13.0, 10.0) is True)
# ST 5cm 一字板: 昨收10 涨停10.5 —— 旧阈值 9.8 会漏判
check('ST 5cm 一字板识别(旧阈值会漏)', ar._is_one_word_bar(10.5, 10.5, 10.5, 10.5, 10.0) is True)
# 20cm 股只涨 10%（远未涨停）不应误判为一字板
check('20cm 涨10%不误判', ar._is_one_word_bar(11.0, 11.0, 11.0, 12.0, 10.0) is False)
# 盘中回落不算一字板
check('盘中回落不算一字板', ar._is_one_word_bar(11.0, 11.0, 10.8, 11.0, 10.0) is False)
# 收盘未封住不算
check('收盘未封不算一字板', ar._is_one_word_bar(11.0, 10.9, 10.9, 11.0, 10.0) is False)
# limit_up 缺失时退回启发式
check('limit_up缺失退回启发式(10cm)', ar._is_one_word_bar(11.0, 11.0, 11.0, 0, 10.0) is True)
check('limit_up缺失退回启发式(4.9%不够)', ar._is_one_word_bar(10.49, 10.49, 10.49, 0, 10.0) is False)

print('\n=== 4. 全零/None 输入不崩溃 ===')
for args in [(0, 0, 0, 0, 0), (None, None, None, None, None)]:
    try:
        r = ar._is_one_word_bar(*args)
        check('_is_one_word_bar(%s) 不崩溃' % (args,), r is False, r)
    except Exception as e:
        check('_is_one_word_bar(%s) 不崩溃' % (args,), False, repr(e))

# ============================================================
# 竞价爆量「抢筹」判定必须带方向门禁
# 背景 (2026-10-26): 三峡新材 600293 一字跌停(-9.98%)、买盘全空、卖一压 30 万手，
# 却因为「量比 5.3 + 成交占昨 513%」被判成「超预期抢筹」。
# 原 auction_boom 是一条纯量能表达式，完全不看方向。
# ============================================================
print()
print('=== 竞价爆量抢筹的方向门禁 ===')

# 真实踩坑样本：跌停 + 巨量 + 极端卖压
sanxia = dict(pct=-9.98, is_dt=True, order_ratio=-86.9, vol_ratio=5.3,
              amount_ratio_pct=513.26, is_one_word=False, seal_amount_yi=0.0)
check('三峡新材(一字跌停+巨量) 不得判为抢筹', ar.is_auction_boom(sanxia) is False)

# 正常抢筹：高开 + 买盘主导 + 放量
check('高开5%放量买盘主导 → 抢筹',
      ar.is_auction_boom(dict(pct=5.0, is_dt=False, order_ratio=62.0, vol_ratio=4.2,
                              amount_ratio_pct=9.0, is_one_word=False, seal_amount_yi=0.0)) is True)
# 一字涨停：封单巨大、委比极高
check('一字涨停封单0.8亿 → 抢筹',
      ar.is_auction_boom(dict(pct=10.0, is_dt=False, order_ratio=99.0, vol_ratio=1.1,
                              amount_ratio_pct=1.0, is_one_word=True, seal_amount_yi=0.8)) is True)
# 高开但卖压压倒性（委比 -60）：不算抢筹
check('高开但卖压压倒性(委比-60) → 不算抢筹',
      ar.is_auction_boom(dict(pct=1.2, is_dt=False, order_ratio=-60.0, vol_ratio=4.0,
                              amount_ratio_pct=8.0, is_one_word=False, seal_amount_yi=0.0)) is False)
# 低开放量（-2%）：不算抢筹
check('低开-2%放量 → 不算抢筹',
      ar.is_auction_boom(dict(pct=-2.0, is_dt=False, order_ratio=10.0, vol_ratio=5.0,
                              amount_ratio_pct=12.0, is_one_word=False, seal_amount_yi=0.0)) is False)
# 平开但完全没量：不算抢筹
check('平开无量(量比1.0/占昨2%) → 不算抢筹',
      ar.is_auction_boom(dict(pct=0.0, is_dt=False, order_ratio=5.0, vol_ratio=1.0,
                              amount_ratio_pct=2.0, is_one_word=False, seal_amount_yi=0.0)) is False)
# 脏数据不炸
check('字段缺失/脏值安全返回 False', ar.is_auction_boom({}) is False and ar.is_auction_boom(None) is False)

print()
if fails:
    print('FAILED:', fails); sys.exit(1)
print('=== 竞价雷达辅助函数测试全部通过 ===')

print('\n=== 5. _safe_int 兜 lbc 脏值（防止整页崩溃）===')
import importlib
importlib.reload(ar)
int_cases = [
    (None, 1), ('', 1), ('-', 1), ('--', 1), ('None', 1),
    (3, 3), ('3', 3), (' 5 ', 5), (2.0, 2), ('abc', 1), (True, 1),
]
for raw, want in int_cases:
    got = ar._safe_int(raw, 1)
    check('_safe_int(%r) == %s' % (raw, want), got == want, got)
check('自定义默认值', ar._safe_int('-', 7) == 7, ar._safe_int('-', 7))

print('\n=== 6. 竞价金额占昨比与缩量假高开识别 ===')
# 成交额占昨比计算
check('1000万/1亿 = 10%', abs(ar.calc_amount_ratio_pct(1e7, 1e8) - 10.0) < 1e-4)
check('昨日成交为0时不除零', ar.calc_amount_ratio_pct(1e7, 0) == 0.0)
check('今日成交为0时返回0', ar.calc_amount_ratio_pct(0, 1e8) == 0.0)
check('非法值安全返回0', ar.calc_amount_ratio_pct(None, '-') == 0.0)

# 缩量假高开判定
# 案例 A: 高开 3.5%, 但量比仅 0.6, 竞价成交占昨仅 0.8% (典型假高开/挂撤诱多)
check('缩量假高开A (量比弱+占比低)', ar.is_fake_high_open(3.5, 0.6, 0.08, 0.8) is True)
# 案例 B: 高开 4.0%, 绝对金额仅 200万 (0.02亿), 占昨 0.5% (微小玩具拉高)
check('缩量假高开B (金额极小+占昨低)', ar.is_fake_high_open(4.0, 1.2, 0.02, 0.5) is True)
# 案例 C: 高开 3.0%, 量比 2.5, 竞价金额 3000万, 占昨 6.5% (真金白银真转强)
check('真实强高开C (量价齐升不误判)', ar.is_fake_high_open(3.0, 2.5, 0.30, 6.5) is False)
# 案例 D: 平开或低开 (-0.5%), 不触发假高开
check('平开/低开D 不触发', ar.is_fake_high_open(-0.5, 0.4, 0.01, 0.2) is False)

print()
if fails:
    print('FAILED:', fails)
    sys.exit(1)
print('=== 竞价雷达所有测试全部通过 ===')
