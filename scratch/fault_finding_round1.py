import urllib.request, urllib.parse, json, time, sys

BASE = 'http://127.0.0.1:8001'
failures = []

def test(name, url, expect_status=200, check_fn=None):
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=25) as resp:
            elapsed = round((time.time() - t0) * 1000, 1)
            code = resp.status
            body = resp.read().decode('utf-8')
            if code != expect_status:
                failures.append(f'[{name}] Expect status {expect_status}, got {code} ({elapsed}ms)')
                print(f'❌ {name} -> status {code}')
                return
            if check_fn:
                ok, msg = check_fn(body)
                if not ok:
                    failures.append(f'[{name}] Check failed: {msg} ({elapsed}ms)')
                    print(f'❌ {name} -> {msg}')
                    return
            print(f'✅ {name} ({elapsed}ms)')
    except urllib.error.HTTPError as e:
        elapsed = round((time.time() - t0) * 1000, 1)
        if e.code == expect_status:
            print(f'✅ {name} (expected HTTP {e.code}) ({elapsed}ms)')
        else:
            failures.append(f'[{name}] HTTP Error {e.code} ({elapsed}ms)')
            print(f'❌ {name} -> HTTP {e.code}')
    except Exception as e:
        elapsed = round((time.time() - t0) * 1000, 1)
        failures.append(f'[{name}] Exception {type(e).__name__}: {e} ({elapsed}ms)')
        print(f'❌ {name} -> {type(e).__name__}: {e}')

print('===== [第一轮找茬: 边界输入与异常参数测试] =====')
test('1.1 sim空输入', f'{BASE}/api/sim')
test('1.2 sim超长文本输入(1000字)', f'{BASE}/api/sim?scenario=' + urllib.parse.quote('央行重磅政策利好发布' * 100))
test('1.3 sim特殊符号与SQL注入探测', f'{BASE}/api/sim?scenario=' + urllib.parse.quote("'; DROP TABLE users; -- <script>alert(1)</script>"))
test('1.4 sim纯emoji与乱码输入', f'{BASE}/api/sim?scenario=' + urllib.parse.quote('🚀🔥💎📉📈!@#$%^&*()_+~`'))
test('1.5 sim非法股票代码', f'{BASE}/api/sim?code=XYZ999')

test('2.1 stock非法不存在代码', f'{BASE}/api/stock/999999')
test('2.2 stock非法非数字代码', f'{BASE}/api/stock/ABCDEF')
test('2.3 stock代码包含空格', f'{BASE}/api/stock/600519%20')
test('2.4 stock极短交易历史代码(新股)', f'{BASE}/api/stock/301633')

test('3.1 watchlist全非法代码', f'{BASE}/api/watchlist?codes=INVALID,000000,ABC')
test('3.2 watchlist超长代码列表(120只)', f'{BASE}/api/watchlist?codes=' + ','.join([f'600{i:03d}' for i in range(120)]))
test('3.3 watchlist含空逗号', f'{BASE}/api/watchlist?codes=,,,600519,,,,000001,,')

test('4.1 strategies未知模式', f'{BASE}/api/strategies?mode=unknown_random_mode')

test('5.1 screen非法形态', f'{BASE}/api/screen?patterns=NonExistentPattern')

print('\n-- 第一轮找茬结果汇报 --')
if failures:
    print(f'发现 {len(failures)} 处边界隐患/瑕疵:')
    for f in failures:
        print('  •', f)
else:
    print('全部 12 项边界测试顺利抵御！')
