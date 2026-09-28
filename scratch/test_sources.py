# -*- coding: utf-8 -*-
"""
Test script for data_feed enhancements
"""
import time
import json
import urllib.request

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import stock_dashboard as sd

def test_sources():
    code = '600519'
    secid = '1.600519'
    
    # 1. Test Trends
    print("--- 1. Testing Trends ---")
    u_trends = (
        f"https://push2his.eastmoney.com/api/qt/stock/trends2/get"
        f"?secid={secid}&fields1=f1,f2,f3,f4,f5,f6,f7,f8&fields2=f51,f52,f53,f54,f55,f56,f57,f58"
        f"&ut=fa5fd1575c3b838480cc8264a04e39b9"
    )
    t0 = time.time()
    try:
        raw = sd.http(u_trends, referer='https://quote.eastmoney.com/', timeout=5)
        j = json.loads(raw)
        d = j.get('data') or {}
        trends = d.get('trends') or []
        pre_close = d.get('preClose')
        print(f"Trends latency: {(time.time()-t0)*1000:.1f}ms, count: {len(trends)}, preClose: {pre_close}")
        if trends:
            p = trends[-1].split(',')
            print(f"Latest trend minute: time={p[0]}, price={p[2]}, avg={p[7]}, vol={p[5]}")
    except Exception as e:
        print(f"Trends failed: {e}")

    # 2. Test Realtime Order Breakdown (Super large, large, medium, small)
    print("\n--- 2. Testing Order Breakdown ---")
    u_flow = (
        f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}"
        f"&fields=f58,f135,f136,f137,f138,f139,f140,f141,f142,f143,f144,f145,f146,f147,f148,f149"
    )
    t0 = time.time()
    try:
        raw = sd.http(u_flow, referer='https://quote.eastmoney.com/', timeout=5)
        j = json.loads(raw)
        d = j.get('data') or {}
        print(f"Flow latency: {(time.time()-t0)*1000:.1f}ms")
        print(f"Name: {d.get('f58')}")
        print(f"主力净流入: {d.get('f137',0)/1e8:.2f}亿 (超大单: {d.get('f140',0)/1e8:.2f}亿, 大单: {d.get('f143',0)/1e8:.2f}亿)")
        print(f"中单净流入: {d.get('f146',0)/1e8:.2f}亿, 小单散户净流入: {d.get('f149',0)/1e8:.2f}亿")
    except Exception as e:
        print(f"Flow failed: {e}")

    # 3. Test Sina Quote Fallback
    print("\n--- 3. Testing Sina Fallback ---")
    full = 'sh600519'
    u_sina = f"https://hq.sinajs.cn/list={full}"
    t0 = time.time()
    try:
        raw = sd.http(u_sina, gbk=True, referer='https://finance.sina.com.cn/', timeout=5)
        print(f"Sina latency: {(time.time()-t0)*1000:.1f}ms")
        line = raw.split('=')[1].replace('"', '').strip()
        parts = line.split(',')
        print(f"Sina Quote: name={parts[0]}, price={parts[3]}, open={parts[1]}, prev_close={parts[2]}")
    except Exception as e:
        print(f"Sina failed: {e}")

if __name__ == '__main__':
    test_sources()
