# -*- coding: utf-8 -*-
"""
交易日历并发安全回归测试

背景 (2026-10-18): trading_calendar 的日K缓存最初把"检查缓存"与"回填缓存"
拆成两把独立锁，缓存未命中时多个并发线程会同时打上游 —— 实测 10 个并发请求
触发 10 次网络调用。Web 首屏会同时唤起多个接口，正好会踩到这个点。
修复方案: single-flight（首次未命中只放一个线程去拉，其余排队后复用结果）。

本测试锁定：
  1. 并发首次访问只允许 1 次上游调用
  2. TTL 内重复调用不打网络
  3. 拉取失败时若存在旧缓存，降级返回旧值而不是返回空
  4. 完全无缓存且上游失败时返回 None 不崩溃
  5. force=True 能绕过缓存强制刷新
"""
import sys, os, threading, time

_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts')
sys.path.insert(0, _SCRIPTS)
os.chdir(_SCRIPTS)

import trading_calendar as tc
import stock_dashboard as sd

fails = []
def check(name, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + name + ((' | ' + str(extra)) if extra else ''))
    if not cond: fails.append(name)


_ORIG = sd.kline_tx

def run_concurrent(n_threads, fetch_delay):
    """n 个线程同时首次访问，返回 (上游调用次数, 结果列表, 耗时)"""
    calls = {'n': 0}
    lk = threading.Lock()

    def fake(code, cnt):
        with lk:
            calls['n'] += 1
        time.sleep(fetch_delay)
        return [['2026-10-16'], ['2026-10-15'], ['2026-10-14']]

    sd.kline_tx = fake
    tc._KLINE_CACHE = {'dates': None, 'ts': 0.0}
    results, rlk = [], threading.Lock()

    def worker():
        r = tc.latest_trading_day('20261018')
        with rlk:
            results.append(r)

    ths = [threading.Thread(target=worker) for _ in range(n_threads)]
    t0 = time.time()
    for t in ths: t.start()
    for t in ths: t.join()
    el = time.time() - t0
    sd.kline_tx = _ORIG
    return calls['n'], results, el


print('=== 1. 10 并发首次访问：只允许 1 次上游调用 ===')
n_calls, results, elapsed = run_concurrent(10, 0.3)
check('上游仅被调用 1 次', n_calls == 1, f'实际 {n_calls} 次')
check('所有线程都拿到正确日期', all(r == '20261016' for r in results), set(results))
check('总耗时接近单次网络耗时(<1s)', elapsed < 1.0, '%.2fs' % elapsed)

print('\n=== 2. 缓存命中后不再打网络 ===')
hit_calls = {'n': 0}
def counting(code, cnt):
    hit_calls['n'] += 1
    return [['2026-10-16']]
sd.kline_tx = counting
tc._KLINE_CACHE = {'dates': {'20261016'}, 'ts': time.time()}
for _ in range(5):
    tc.latest_trading_day('20261016')
check('TTL 内 5 次调用 0 次打网络', hit_calls['n'] == 0, f'实际 {hit_calls["n"]} 次')

print('\n=== 3. 上游失败时降级返回旧缓存 ===')
def boom(code, cnt):
    raise RuntimeError('upstream down')
sd.kline_tx = boom
tc._KLINE_CACHE = {'dates': {'20261016', '20261015'}, 'ts': 0.0}   # 有过期旧缓存
try:
    d = tc.latest_trading_day('20261018')
    check('旧缓存降级返回 20261016', d == '20261016', d)
except Exception as e:
    check('旧缓存降级返回', False, repr(e))

print('\n=== 4. 完全无缓存且上游失败：返回 None 而非崩溃 ===')
tc._KLINE_CACHE = {'dates': None, 'ts': 0.0}
try:
    d = tc.latest_trading_day('20261018')
    ok, val = (d is None), d
except Exception as e:
    ok, val = False, repr(e)
check('返回 None 不崩溃', ok, val)

print('\n=== 5. force=True 必须绕过缓存强制刷新 ===')
force_calls = {'n': 0}
def fc(code, cnt):
    force_calls['n'] += 1
    return [['2026-10-16']]
sd.kline_tx = fc
tc._KLINE_CACHE = {'dates': {'20260101'}, 'ts': time.time()}
tc._load_trading_dates(force=True)
check('force=True 确实打了上游', force_calls['n'] == 1, f'实际 {force_calls["n"]} 次')

# 还原，避免影响其它测试
sd.kline_tx = _ORIG
tc._KLINE_CACHE = {'dates': None, 'ts': 0.0}

print()
if fails:
    print('FAILED:', fails); sys.exit(1)
print('=== 并发安全测试全部通过 ===')
