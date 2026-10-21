# -*- coding: utf-8 -*-
import sys, os
os.chdir(r'D:\股票看盘\scripts')
sys.path.insert(0, r'D:\股票看盘\scripts')
import trading_calendar as tc

# 用假的交易日历注入，验证纯逻辑
tc._KLINE_CACHE = {'dates': {'20261013','20261014','20261015','20261016'}, 'ts': 1e18}
FAKE_POOL = {'20261016': [{'c':'600001','lbc':1}], '20261015': [{'c':'600002','lbc':1}],
             '20261014': [{'c':'600003','lbc':1}]}
fetcher = lambda ymd: FAKE_POOL.get(ymd, [])

fails = []
def check(name, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + name + ((' | ' + str(extra)) if extra else ''))
    if not cond: fails.append(name)

print('=== 1. is_trading_day 必须拒绝周末 ===')
check('20261017(周六) 非交易日', tc.is_trading_day('20261017') is False)
check('20261018(周日) 非交易日', tc.is_trading_day('20261018') is False)
check('20261016(周五) 是交易日', tc.is_trading_day('20261016') is True)

print('\n=== 2. latest_trading_day 周日应回溯到周五 ===')
check('周日回溯=20261016', tc.latest_trading_day('20261018') == '20261016',
      tc.latest_trading_day('20261018'))
check('周六回溯=20261016', tc.latest_trading_day('20261017') == '20261016',
      tc.latest_trading_day('20261017'))

print('\n=== 3. get_recent_trading_days 绝不能返回周末/同源 ===')
days = tc.get_recent_trading_days(2, end_ymd='20261018', pool_fetcher=fetcher)
print('     返回:', [(d, len(p)) for d, p in days])
check('取到2个交易日', len(days) == 2, len(days))
check('第1个是周五20261016', days[0][0] == '20261016', days[0][0] if days else None)
check('第2个是周四20261015', len(days) > 1 and days[1][0] == '20261015',
      days[1][0] if len(days) > 1 else None)
check('绝不包含周末20261017', all(d != '20261017' for d, _ in days))
check('绝不包含周末20261018', all(d != '20261018' for d, _ in days))
check('两天不同源', len(days) >= 2 and days[0][0] != days[1][0])

print('\n=== 4. 回归: 旧逻辑会把周末当交易日 -> 今日今昨同源 ===')
import datetime as dt
ORANGE = set(FAKE_POOL) | {'20261017','20261018'}
old_found = []
for i in range(0, 12):
    ds = (dt.date(2026,10,18) - dt.timedelta(days=i)).strftime('%Y%m%d')
    # 模拟东财对任何日期都回吐周五快照
    if ds in ORANGE:
        old_found.append(ds)
    if len(old_found) >= 2: break
print('     旧逻辑取到:', old_found)
check('旧逻辑确实踩坑(今昨都是周末)', old_found[0] != days[0][0], old_found)

print()
if fails:
    print('FAILED:', fails); sys.exit(1)
print('=== 交易日历校验全部通过 ===')

print('\n=== 5. end_ymd 脏值必须安全返回 [] ===')
for bad in ['', 'abc', '2026-10-18', '202610', '99999999x', None]:
    try:
        r = tc.get_recent_trading_days(2, end_ymd=bad, pool_fetcher=fetcher)
        ok = isinstance(r, list)
        check('end_ymd=%r 不崩溃返回list' % (bad,), ok, r if not ok else 'ok')
    except Exception as e:
        check('end_ymd=%r 不崩溃' % (bad,), False, repr(e))

print('\n=== 6. 日历不可用时，回退模式必须去重同源数据 ===')
# 真正模拟"日历拉取失败": 打桩 _load_trading_dates 返回空集合
_orig_load = tc._load_trading_dates
tc._load_trading_dates = lambda force=False: set()
_same = [{'c': '600001', 'lbc': 1}, {'c': '600002', 'lbc': 2}]
same_fetcher = lambda ymd: list(_same)
r = tc.get_recent_trading_days(2, end_ymd='20261019', pool_fetcher=same_fetcher)
print('     fallback 返回:', [d for d, _ in r])
check('同源数据只保留1天(不去重复活旧bug)', len(r) <= 1, len(r))

# 不同数据时应正常取满
import copy
def varied(ymd):
    return [{'c': '6000' + ymd[-2:], 'lbc': 1}]
r2 = tc.get_recent_trading_days(2, end_ymd='20261019', pool_fetcher=varied)
check('数据不同时可取满2天', len(r2) == 2, [d for d, _ in r2])

tc._load_trading_dates = _orig_load
# 还原
tc._KLINE_CACHE = {'dates': {'20261013','20261014','20261015','20261016'}, 'ts': 1e18}
