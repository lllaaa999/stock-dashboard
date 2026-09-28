import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import stock_dashboard as sd

t0 = time.time()
code = '600664'
full = ('sh' + code) if code.startswith(('6', '5', '9')) else ('sz' + code)
q = sd.tx_realtime([full])[0]
t1 = time.time()
print(f"Quote fetched in {t1-t0:.3f}s:", q['name'], q['price'])

kl = sd.kline_tx(full, 160)
t2 = time.time()
print(f"Kline fetched in {t2-t1:.3f}s: count={len(kl)}")

chan = sd.chan_analysis_structured(kl, code)
t3 = time.time()
print(f"Chan computed in {t3-t2:.3f}s: bi={len(chan['bi_points'])}, zhongshu={chan['last_zhongshu'] is not None}")
print(f"Total time: {t3-t0:.3f}s")
