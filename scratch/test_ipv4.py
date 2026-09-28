# -*- coding: utf-8 -*-
import socket
import urllib.request
import json
import time

# Force IPv4 in socket
orig_getaddrinfo = socket.getaddrinfo
def getaddrinfo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
    return orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

socket.getaddrinfo = getaddrinfo_ipv4

secid = '1.600519'

# 1. FFLOW
t0 = time.time()
u1 = f'https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get?lmt=5&klt=101&secid={secid}&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65&ut=7eea3edcaed734bea9cbfc24409ed989'
try:
    req = urllib.request.Request(u1, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'})
    with urllib.request.urlopen(req, timeout=3) as r:
        j = json.loads(r.read().decode('utf-8'))
        count = len((j.get("data") or {}).get("klines") or [])
        print(f"1. FFLOW SUCCESS! {(time.time()-t0)*1000:.1f}ms, count={count}")
except Exception as e:
    print('1. FFLOW FAIL:', e)

# 2. CLIST
t0 = time.time()
u2 = 'https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=5&po=1&np=1&fltt=2&fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f12,f14,f2,f3'
try:
    req = urllib.request.Request(u2, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://quote.eastmoney.com/'})
    with urllib.request.urlopen(req, timeout=3) as r:
        j = json.loads(r.read().decode('utf-8'))
        count = len((j.get("data") or {}).get("diff") or [])
        print(f"2. CLIST SUCCESS! {(time.time()-t0)*1000:.1f}ms, count={count}")
except Exception as e:
    print('2. CLIST FAIL:', e)
