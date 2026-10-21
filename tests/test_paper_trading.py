# -*- coding: utf-8 -*-
"""
模拟交易引擎核心规则校验 (paper_trading.py)

这些是「模拟自动交易」能否代表实盘的关键约束，必须逐条锁死：
  1. T+1  —— 当日买入当日不可卖
  2. 整手 —— 买入数量必须是 100 的整数倍
  3. 费用 —— 佣金双边(最低5元)、印花税仅卖出、滑点双边
  4. 资金 —— 不允许出现负现金
  5. 无未来函数 —— 回放中信号在 T 日收盘产生，成交必须在 T+1 开盘
"""
import sys, os
_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts')
sys.path.insert(0, _SCRIPTS)
os.chdir(_SCRIPTS)

import paper_trading as pt

fails = []
def check(name, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + name + ((' | ' + str(extra)) if extra else ''))
    if not cond: fails.append(name)


print('=== 1. T+1：当日买入当日不可卖 ===')
b = pt.SimBroker(100000)
r = b.buy('600519', 100.0, '2026-10-16', 'test')
check('买入成功', r is not None, r and r['shares'])
check('持仓正确', b.shares_of('600519') == r['shares'], b.shares_of('600519'))
s_same = b.sell('600519', 101.0, '2026-10-16', '当日卖')
check('当日卖出被拒', s_same is None)
check('被拒原因含T+1', any('T+1' in x['reason'] for x in b.rejects),
      [x['reason'] for x in b.rejects])
s_next = b.sell('600519', 101.0, '2026-10-17', '次日卖')
check('次日卖出成功', s_next is not None, s_next and s_next['shares'])

print('\n=== 2. 整手：买入必须是 100 的整数倍 ===')
b2 = pt.SimBroker(100000)
r2 = b2.buy('000001', 11.53, '2026-10-16', 'test')
check('股数 % 100 == 0', r2['shares'] % 100 == 0, r2['shares'])

print('\n=== 3. 费用计算 ===')
b3 = pt.SimBroker(100000)
buy = b3.buy('000001', 10.0, '2026-10-16', 'test')
gross_buy = buy['shares'] * buy['price']
exp_comm = max(5.0, gross_buy * 0.00025)
check('买入佣金正确', abs(buy['commission'] - round(exp_comm, 2)) < 0.02,
      f"实际{buy['commission']} 期望{round(exp_comm,2)}")
check('买入无印花税', buy['stamp_duty'] == 0.0, buy['stamp_duty'])
check('买入成交价含滑点(高于市价)', buy['price'] > 10.0, buy['price'])

sell = b3.sell('000001', 11.0, '2026-10-17', 'test')
gross_sell = sell['shares'] * sell['price']
exp_stamp = gross_sell * 0.0005
check('卖出印花税正确', abs(sell['stamp_duty'] - round(exp_stamp, 2)) < 0.02,
      f"实际{sell['stamp_duty']} 期望{round(exp_stamp,2)}")
check('卖出成交价含滑点(低于市价)', sell['price'] < 11.0, sell['price'])

print('\n=== 4. 资金安全：不允许负现金 ===')
b4 = pt.SimBroker(10000)
for i in range(5):
    b4.buy('600519', 100.0, f'2026-10-1{i}', 'test')
check('现金 >= 0', b4.cash >= -1e-6, b4.cash)
check('超买被拒', len(b4.rejects) >= 1, len(b4.rejects))

print('\n=== 5. 无未来函数：成交价必须是次日开盘价 ===')
import data_feed as df_feed
code = '000001'
full = 'sz000001'
kl = df_feed.get_kline_cached(full, 120)
res = pt.run_replay(code, strategy='chan', days=120, initial_cash=100000, warmup=35)
if res.get('status') == 'ok' and res['trade_log']:
    # 找到每笔成交的日期，核对成交价是否等于当日开盘*(1±滑点)
    date_to_bar = {str(b[0]): b for b in kl}
    all_ok = True
    detail = []
    for t in res['trade_log'][:8]:
        bar = date_to_bar.get(t['date'])
        if not bar:
            continue
        o = float(bar[1])
        exp = pt._round_tick(o * (1 + pt.SLIPPAGE_RATE) if t['side'] == 'buy'
                             else o * (1 - pt.SLIPPAGE_RATE))
        # 止损/止盈单是按触发价成交的，允许不等
        if '止损' in (t.get('reason') or '') or '止盈' in (t.get('reason') or ''):
            continue
        ok = abs(t['price'] - exp) < 0.02
        if not ok:
            all_ok = False
            detail.append(f"{t['date']} {t['side']} 实际{t['price']} 期望{exp}")
    check('普通成交均按当日开盘价±滑点', all_ok, detail[:3] if detail else '全部匹配')
else:
    check('回放可运行', False, res.get('msg'))


print('\n=== 6. 被拒委托必须留痕（可审计） ===')
b6 = pt.SimBroker(1000)
b6.buy('600519', 1300.0, '2026-10-16', '资金不足')
check('拒单有记录', len(b6.rejects) == 1, b6.rejects)
check('拒单含原因', b6.rejects[0]['reason'] != '', b6.rejects[0]['reason'])

print()
if fails:
    print('FAILED:', fails); sys.exit(1)
print('=== 模拟交易核心规则全部通过 ===')
