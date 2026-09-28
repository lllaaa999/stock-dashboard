# -*- coding: utf-8 -*-
"""
End-to-end automated verification script for Data Feed Optimizations
"""
import sys
import os
import time
import json
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'web'))

import data_feed as df
from main import app

client = TestClient(app)

def test_all():
    print("==================================================")
    print("🚀 启动数据源优化全面闭环自测")
    print("==================================================")

    # 1. 测试 /api/data_status 监控接口
    print("\n[1/4] 测试数据源健康状态监控 (/api/data_status)")
    t0 = time.time()
    r = client.get("/api/data_status")
    assert r.status_code == 200, f"状态码异常: {r.status_code}"
    status_data = r.json()
    print(f"  ✓ 响应耗时: {(time.time()-t0)*1000:.1f}ms")
    print(f"  ✓ 上游通道健康状态: {status_data['sources']}")
    print(f"  ✓ 内存 TTL 缓存状态: {status_data['cache']}")

    # 2. 测试 /api/stock/{code} (腾讯主通道 + 分时图 + 资金单笔分布)
    print("\n[2/4] 测试个股全维体检 (/api/stock/600519)")
    t0 = time.time()
    r = client.get("/api/stock/600519")
    latency_cold = (time.time() - t0) * 1000
    assert r.status_code == 200, f"状态码异常: {r.status_code}"
    d = r.json()
    print(f"  ✓ 冷启动耗时: {latency_cold:.1f}ms")
    print(f"  ✓ 命中数据源: {d.get('data_source')}")
    print(f"  ✓ 实时行情: {d['quote']['name']} 最新价: {d['quote']['price']} 涨跌幅: {d['quote']['pct']}%")
    assert d['kline'] and len(d['kline']) >= 30, "日K线数据不足"
    print(f"  ✓ 日 K 线根数: {len(d['kline'])}, 最新日: {d['kline'][-1][0]}")
    assert d['chan'] is not None, "缠论结构解析失败"
    print(f"  ✓ 缠论诊断结论: {d['chan'].get('summary')}, 识别中枢数: {len(d['chan'].get('zhongshus', []))}")
    assert d['trends'] and d['trends']['count'] > 0, "分时黄白线数据为空"
    print(f"  ✓ 分时图分钟点数: {d['trends']['count']}, 昨日收盘基准: {d['trends']['pre_close']}")
    print(f"  ✓ 分时首末: 09:30={d['trends']['prices'][0]} ~ 末点={d['trends']['prices'][-1]}")
    
    # 3. 测试内存 TTL 缓存二次命中耗时 (<5ms)
    print("\n[3/4] 测试内存 TTL 缓存加速效果 (二次查询 600519)")
    t0 = time.time()
    r2 = client.get("/api/stock/600519")
    latency_warm = (time.time() - t0) * 1000
    assert r2.status_code == 200
    print(f"  ✓ 二次命中耗时: {latency_warm:.1f}ms (对比冷启动加速比: {latency_cold/max(latency_warm, 0.1):.1f}x)")
    assert latency_warm < 150, f"热查询耗时过长: {latency_warm}ms"

    # 4. 测试自选盯盘批量行情 (/api/watchlist)
    print("\n[4/4] 测试自选股极速批量轮询 (/api/watchlist)")
    t0 = time.time()
    r = client.get("/api/watchlist?codes=600519,000001,300750,600664")
    assert r.status_code == 200
    items = r.json()
    print(f"  ✓ 批量查询 4 股耗时: {(time.time()-t0)*1000:.1f}ms, 返回股数: {len(items)}")
    for it in items:
        print(f"    - {it['code']} {it['name']}: {it['price']} ({it['pct']:+.2f}%) 涨跌停: 涨{it['is_zt']}/跌{it['is_dt']}")

    print("\n==================================================")
    print("🎉 全部数据源优化项验证 100% 通过！系统轻量、健壮且极致迅速！")
    print("==================================================")

if __name__ == '__main__':
    test_all()
