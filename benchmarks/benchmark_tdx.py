#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
tests/benchmark_tdx.py — 通达信 (TDX/pytdx/mootdx) 连接性能、稳定性与分时K线全面测评
"""
import sys
import os
import time
import json
import urllib.request
import pandas as pd

from pytdx.hq import TdxHq_API
from pytdx.params import TDXParams

# 常用优质 TDX 行情服务器列表
BEST_SERVERS = [
    {'name': '招商证券深圳', 'ip': '119.147.212.81', 'port': 7709},
    {'name': '武汉电信', 'ip': '119.97.185.73', 'port': 7709},
    {'name': '华泰证券南京', 'ip': '221.231.141.60', 'port': 7709},
    {'name': '通达信总站上海', 'ip': '101.227.73.20', 'port': 7709},
    {'name': '广发证券', 'ip': '14.215.10.45', 'port': 7709},
    {'name': '通达信深圳电信', 'ip': '112.74.214.43', 'port': 7709},
]

def test_servers():
    print("=== [1/5] TDX 服务器连通率与拡手延迟测试 ===")
    results = []
    api = TdxHq_API()
    for s in BEST_SERVERS:
        t0 = time.time()
        try:
            ok = api.connect(s['ip'], s['port'], time_out=2.0)
            latency = round((time.time() - t0) * 1000, 1)
            if ok:
                results.append((s, latency))
                print(f"  [OK] {s['name']} ({s['ip']}:{s['port']}) 连接成功 | 延迟: {latency}ms")
                api.disconnect()
            else:
                print(f"  [FAIL] {s['name']} ({s['ip']}:{s['port']}) 握手失败")
        except Exception as e:
            print(f"  [FAIL] {s['name']} ({s['ip']}:{s['port']}) 超时/异常: {e}")
    results.sort(key=lambda x: x[1])
    best = results[0] if results else None
    return api, best

def benchmark_kline(api, best_server):
    print("\n=== [2/5] TDX 分时/分钟/日K 线拉取能力测试 ===")
    if not best_server:
        print("无可用服务器")
        return
    s, lat = best_server
    api.connect(s['ip'], s['port'], time_out=3.0)
    code = '600519'  # 贵州茅台
    market = 1       # 1=sh, 0=sz

    # 1分钟 K 线
    t0 = time.time()
    k1 = api.get_security_bars(TDXParams.KLINE_TYPE_1MIN, market, code, 0, 800)
    t_k1 = round((time.time() - t0) * 1000, 1)
    print(f"  -> 1分钟 K 线 (800根): 获取 {len(k1 or [])} 根 | 耗时: {t_k1}ms | 最新时间: {k1[-1]['datetime'] if k1 else '-'}")

    # 5分钟 K 线
    t0 = time.time()
    k5 = api.get_security_bars(TDXParams.KLINE_TYPE_5MIN, market, code, 0, 800)
    t_k5 = round((time.time() - t0) * 1000, 1)
    print(f"  -> 5分钟 K 线 (800根): 获取 {len(k5 or [])} 根 | 耗时: {t_k5}ms | 最新时间: {k5[-1]['datetime'] if k5 else '-'}")

    # 日 K 线
    t0 = time.time()
    kday = api.get_security_bars(TDXParams.KLINE_TYPE_DAILY, market, code, 0, 800)
    t_kday = round((time.time() - t0) * 1000, 1)
    print(f"  -> 日 K 线 (800根): 获取 {len(kday or [])} 根 | 耗时: {t_kday}ms | 最新日期: {kday[-1]['datetime'] if kday else '-'}")

    # 分笔明细 (Tick / Transaction)
    t0 = time.time()
    ticks = api.get_transaction_data(market, code, 0, 100)
    t_ticks = round((time.time() - t0) * 1000, 1)
    print(f"  -> 分笔成交 (最新 100 笔 Tick): 获取 {len(ticks or [])} 笔 | 耗时: {t_ticks}ms")
    if ticks:
        print(f"     样例 Tick: {ticks[-1]}")

def benchmark_realtime(api, best_server):
    print("\n=== [3/5] TDX vs 腾讯 HTTP 实时行情批量性能对比 (20只标的) ===")
    codes_tdx = [(1, '600519'), (0, '000001'), (0, '000002'), (1, '601398'), (1, '601857'),
                 (0, '300750'), (0, '002594'), (1, '600036'), (1, '601318'), (0, '000858'),
                 (1, '600900'), (1, '601088'), (0, '002475'), (0, '300059'), (1, '601899'),
                 (0, '000333'), (1, '600030'), (1, '603288'), (1, '600276'), (0, '000651')]
    
    # TDX 批量行情
    t0 = time.time()
    tdx_quotes = api.get_security_quotes(codes_tdx)
    t_tdx = round((time.time() - t0) * 1000, 1)
    print(f"  [TDX TCP] 20只个股五档实时盘口: 耗时 {t_tdx}ms | 数据条数={len(tdx_quotes or [])}")
    if tdx_quotes:
        q0 = tdx_quotes[0]
        print(f"     TDX 盘口细节: {q0['code']} 价格={q0['price']} 买一={q0['bid1']}({q0['bid_vol1']}手) 卖一={q0['ask1']}({q0['ask_vol1']}手)")

    # 腾讯 HTTP 批量行情
    tx_codes = [('sh' if m==1 else 'sz') + c for m, c in codes_tdx]
    url = 'https://qt.gtimg.cn/q=' + ','.join(tx_codes)
    t0 = time.time()
    req = urllib.request.urlopen(url, timeout=5)
    raw_tx = req.read().decode('gbk')
    t_tx = round((time.time() - t0) * 1000, 1)
    tx_count = len([x for x in raw_tx.split(';') if '=' in x])
    print(f"  [腾讯 HTTP] 20只个股实时行情: 耗时 {t_tx}ms | 数据条数={tx_count}")

def benchmark_security_list(api, best_server):
    print("\n=== [4/5] TDX 全市场证券代码表获取 ===")
    t0 = time.time()
    stocks_sh = api.get_security_list(1, 0)
    stocks_sz = api.get_security_list(0, 0)
    t_sec = round((time.time() - t0) * 1000, 1)
    total = len(stocks_sh or []) + len(stocks_sz or [])
    print(f"  -> 单批次证券列表: {total} 只 | 耗时: {t_sec}ms")

def benchmark_mootdx_highlevel():
    print("\n=== [5/5] mootdx 高级封装层测试 (自动前复权 + DataFrame) ===")
    try:
        from mootdx.quotes import Quotes
        t0 = time.time()
        client = Quotes.factory(market='std')
        t_init = round((time.time() - t0) * 1000, 1)
        print(f"  -> Quotes.factory 自动选优连接耗时: {t_init}ms")
        
        # 测试 k 线
        t0 = time.time()
        df = client.k(symbol='600519', begin='2026-01-01', end='2026-10-20')
        t_df = round((time.time() - t0) * 1000, 1)
        print(f"  -> client.k() 600519 DataFrame 耗时: {t_df}ms | 行数={len(df) if df is not None else 0}")
        if df is not None and not df.empty:
            print(f"     返回列: {list(df.columns)}")
            print(f"     最新一行: {df.iloc[-1].to_dict()}")
    except Exception as e:
        print(f"  -> mootdx 高级层测试异常: {e}")

if __name__ == '__main__':
    api, best = test_servers()
    if best:
        benchmark_kline(api, best)
        benchmark_realtime(api, best)
        benchmark_security_list(api, best)
    benchmark_mootdx_highlevel()
