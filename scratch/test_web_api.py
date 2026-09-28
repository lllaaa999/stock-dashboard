import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'web'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_endpoints():
    print("Testing /api/auction...")
    res = client.get("/api/auction")
    assert res.status_code == 200, f"/api/auction returned {res.status_code}: {res.text}"
    j = res.json()
    print("  /api/auction OK, summary:", j.get('premium_summary'))
    print("  weak_to_strong count:", len(j.get('weak_to_strong', [])))
    print("  big_loss count:", len(j.get('big_loss', [])))

    print("\nTesting /api/watchlist...")
    res = client.get("/api/watchlist?codes=600519,000001,300750")
    assert res.status_code == 200, f"/api/watchlist returned {res.status_code}: {res.text}"
    wl = res.json()
    print(f"  /api/watchlist OK, count={len(wl)}")
    for s in wl:
        print(f"    {s['code']} {s['name']}: {s['price']} ({s['pct']:+.2f}%)")

    print("\nTesting /api/stock/600664 (including chan)...")
    res = client.get("/api/stock/600664")
    assert res.status_code == 200, f"/api/stock returned {res.status_code}: {res.text}"
    st = res.json()
    chan = st.get('chan')
    print("  /api/stock OK, has chan:", chan is not None)
    if chan:
        print("  chan status:", chan.get('status'))
        print("  chan bi_points count:", len(chan.get('bi_points', [])))
        print("  chan last_zhongshu:", chan.get('last_zhongshu'))
        print("  chan signals count:", len(chan.get('signals', [])))
        print("  chan summary:", chan.get('summary'))

if __name__ == '__main__':
    test_endpoints()
