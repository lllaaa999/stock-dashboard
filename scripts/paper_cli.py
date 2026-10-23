# -*- coding: utf-8 -*-
"""
模拟自动交易 —— 命令行入口

用法
----
  # 历史回放（逐根K线推进，次日开盘成交）
  python scripts/paper_cli.py replay 000001 --strategy chan --days 250
  python scripts/paper_cli.py replay 300750 --strategy ma --capital 200000

  # 实时纸上交易巡检（不真下单，可反复执行）
  python scripts/paper_cli.py tick --strategy chan
  python scripts/paper_cli.py tick --codes 000001,300750,002594

  # 累计报告 / 重置
  python scripts/paper_cli.py report
  python scripts/paper_cli.py reset
"""
import sys
import os
import argparse
import json

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
_SCRIPTS = os.path.join(_HERE, 'scripts')
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import paper_trading as pt


def _pct(v):
    return ('%+.2f%%' % v) if isinstance(v, (int, float)) else '—'


def cmd_replay(args):
    r = pt.run_replay(args.code, strategy=args.strategy, days=args.days,
                      initial_cash=args.capital, use_gate=args.gate)
    if r.get('status') != 'ok':
        print('回放失败:', r.get('msg'))
        return 1

    print('=' * 66)
    print('历史回放模拟自动交易')
    print('=' * 66)
    print(f"  标的        : {r['code']}    策略: {r['strategy']}")
    print(f"  回放K线     : {r['bars']} 根")
    if r.get('warning'):
        print(f"  ⚠ {r['warning']}")
    print('-' * 66)
    print(f"  初始本金    : ¥{r['initial_cash']:>12,.2f}")
    print(f"  期末权益    : ¥{r['final_equity']:>12,.2f}")
    print(f"  总收益率    : {_pct(r['total_return_pct']):>12}")
    print(f"  最大回撤    : {r['max_drawdown_pct']:.2f}%")
    print(f"  成交笔数    : {r['trades']}  (完整回合 {r['round_trips']})")
    print(f"  胜率        : {r['win_rate_pct']:.1f}%  ({r['win']}胜/{r['loss']}负)")
    plr = r['profit_loss_ratio']
    print(f"  盈亏比      : {plr if plr is not None else '—'}")
    print(f"  总佣金      : ¥{r['total_commission']:,.2f}")
    print(f"  总印花税    : ¥{r['total_stamp_duty']:,.2f}")
    print(f"  被拒委托    : {r['rejected']}")
    if r.get('gate_enabled'):
        gs = r.get('gate_stats') or {}
        print(f"  趋势闸门    : 触发{gs.get('evaluated_days',0)}次 / 拦截{gs.get('blocked_buy_signals',0)}次")
        if gs.get('last_reason'):
            print(f"      最近判定  : {gs['last_reason']}")
    if r.get('reject_samples'):
        for x in r['reject_samples']:
            print(f"      {x['date']} {x['side']} -> {x['reason']}")

    if args.verbose and r.get('trade_log'):
        print('-' * 66)
        print('成交明细:')
        for t in r['trade_log']:
            pnl = f"  盈亏 {t['pnl']:+.2f}" if 'pnl' in t else ''
            print(f"   {t['date']} {t['side']:4} {t['price']:>9.2f} ×{t['shares']:>6}  "
                  f"{t.get('reason', '')[:34]}{pnl}")
    return 0


def cmd_tick(args):
    codes = [c.strip() for c in args.codes.split(',')] if args.codes else None
    r = pt.run_paper_tick(strategy=args.strategy, codes=codes,
                          initial_cash=args.capital)
    print('=' * 66)
    print(f"实时纸上交易巡检  @ {r['ts']}")
    print('=' * 66)
    for a in r['actions']:
        if a['action'] == 'hold':
            status = '持有' if a.get('price') else '跳过'
        elif a.get('filled'):
            status = '✔成交'
        else:
            status = f"✘{a.get('reject_reason') or '未成交'}"
        print(f"  {a['code']} {a['action']:5} {status:<16} @{a.get('price', 0):>9.2f}  "
              f"{a.get('reason', '')[:32]}")
    s = r['snapshot']
    print('-' * 66)
    print(f"  现金     : ¥{s['cash']:>12,.2f}")
    print(f"  持仓市值 : ¥{s['market_value']:>12,.2f}")
    print(f"  总权益   : ¥{s['equity']:>12,.2f}  ({_pct(s['return_pct'])})")
    print(f"  持仓     : {s['positions'] or '空仓'}")
    print(f"  状态文件 : {r['state_file']}")
    return 0


def cmd_report(args):
    r = pt.paper_report()
    print('=' * 66)
    print('纸上交易累计报告')
    print('=' * 66)
    print(f"  初始本金   : ¥{(r['initial_cash'] or 0):,.2f}")
    print(f"  巡检次数   : {r['runs']}")
    print(f"  最近巡检   : {r['last_run'] or '—'}")
    print(f"  成交笔数   : {r['trades']}  (完整回合 {r['round_trips']})")
    print(f"  胜率       : {r['win_rate_pct']}%  ({r['win']}胜/{r['loss']}负)")
    print(f"  总佣金     : ¥{r['total_commission']:,.2f}")
    print(f"  总印花税   : ¥{r['total_stamp_duty']:,.2f}")
    print(f"  最大回撤   : {r['max_drawdown_pct'] if r['max_drawdown_pct'] is not None else '—'}%")
    print(f"  最新权益   : {json.dumps(r['latest_equity'], ensure_ascii=False) if r['latest_equity'] else '—'}")
    return 0


def cmd_reset(args):
    killed = []
    for f in (pt.PAPER_STATE, pt.PAPER_TRADES, pt.PAPER_EQUITY):
        try:
            if os.path.exists(f):
                os.remove(f)
                killed.append(os.path.basename(f))
        except Exception:
            pass
    print('已清空:', killed or '（无文件）')
    return 0


def main():
    ap = argparse.ArgumentParser(description='模拟自动交易（不接券商，不下真单）')
    sub = ap.add_subparsers(dest='cmd')

    p1 = sub.add_parser('replay', help='历史回放模拟')
    p1.add_argument('code')
    p1.add_argument('--strategy', default='chan', choices=list(pt.STRATEGIES))
    p1.add_argument('--days', type=int, default=250)
    p1.add_argument('--capital', type=float, default=100000.0)
    p1.add_argument('-v', '--verbose', action='store_true')
    p1.add_argument('--gate', action='store_true',
                    help='启用大盘趋势闸门(ADX+方向)。注意: 实测会拦截96%%的买点，'
                         '导致几乎不交易，谨慎开启')
    p1.set_defaults(func=cmd_replay)

    p2 = sub.add_parser('tick', help='实时纸上交易巡检')
    p2.add_argument('--strategy', default='chan', choices=list(pt.STRATEGIES))
    p2.add_argument('--codes', default='')
    p2.add_argument('--capital', type=float, default=None)
    p2.set_defaults(func=cmd_tick)

    p3 = sub.add_parser('report', help='累计报告')
    p3.set_defaults(func=cmd_report)

    p4 = sub.add_parser('reset', help='清空模拟账户')
    p4.set_defaults(func=cmd_reset)

    args = ap.parse_args()
    if not getattr(args, 'func', None):
        ap.print_help()
        return 1
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
