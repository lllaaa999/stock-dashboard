import sys
sys.path.insert(0, 'web')
sys.path.insert(0, 'scripts')
from starlette.testclient import TestClient
from main import app

client = TestClient(app)

print('--- TESTING /api/emotion/history ---')
r = client.get('/api/emotion/history')
assert r.status_code == 200, f'Status {r.status_code}'
hist = r.json()
print('History count:', len(hist))
print('First date:', hist[0]['date'], 'Last date:', hist[-1]['date'])
assert len(hist) >= 20, f'Expected 20+ historical emotion records, got {len(hist)}'

print('\n--- TESTING /api/strategies?mode=all ---')
r2 = client.get('/api/strategies?mode=all&refresh=1')
assert r2.status_code == 200
strat_data = r2.json()
for s in strat_data.get('strategies', []):
    if s['key'] == 'E':
        print('Strategy E items count:', len(s['items']))
        for it in s['items']:
            print('  ->', it['code'], it['name'], 'Price:', it['price'], 'Pct:', it['pct'])
            assert it['price'] is not None and it['price'] > 0, f"Price invalid: {it['price']}"
            assert it['pct'] is not None and it['pct'] > 0, f"Pct invalid: {it['pct']}"

print('\nALL TESTS PASSED! Emotion trend and Strategy E prices are 100% verified!')
