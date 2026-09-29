# -*- coding: utf-8 -*-
"""Round 2 Automated Fault-Finding & Stress Test Suite (第二轮找茬测试脚本)"""
import sys
import os
import json
import urllib.request
import urllib.error
import urllib.parse
import time
from concurrent.futures import ThreadPoolExecutor

BASE_URL = "http://127.0.0.1:8001"

def fetch_json(endpoint, timeout=20):
    url = BASE_URL + endpoint
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode('utf-8'))

def test_round2():
    results = []
    
    def log_test(name, passed, detail=""):
        status = "✅ PASS" if passed else "❌ FAIL"
        results.append((name, passed, detail))
        print(f"[{status}] {name} - {detail}")

    print("=" * 60)
    print("开始执行第二轮深度找茬与边界并发测试 (Round 2)...")
    print("=" * 60)

    # Test 1: Code normalization on /api/stock with 'sh' prefix
    try:
        status, data = fetch_json("/api/stock/sh600519")
        passed = status == 200 and data.get("code") == "600519" and data.get("quote") is not None
        log_test("Test 1: /api/stock/sh600519 前缀代码归一化", passed, f"返回代码: {data.get('code')}")
    except Exception as e:
        log_test("Test 1: /api/stock/sh600519 前缀代码归一化", False, str(e))

    # Test 2: Code normalization on /api/stock with '.SZ' suffix
    try:
        status, data = fetch_json("/api/stock/000001.SZ")
        passed = status == 200 and data.get("code") == "000001" and data.get("quote") is not None
        log_test("Test 2: /api/stock/000001.SZ 后缀代码归一化", passed, f"返回代码: {data.get('code')}")
    except Exception as e:
        log_test("Test 2: /api/stock/000001.SZ 后缀代码归一化", False, str(e))

    # Test 3: Code normalization with extra whitespace
    try:
        status, data = fetch_json("/api/stock/%20600519%20")
        passed = status == 200 and data.get("code") == "600519"
        log_test("Test 3: /api/stock/ 空格代码归一化", passed, f"返回代码: {data.get('code')}")
    except Exception as e:
        log_test("Test 3: /api/stock/ 空格代码归一化", False, str(e))

    # Test 4: /api/sim with 'sh' prefix code
    try:
        status, data = fetch_json("/api/sim?code=sh600519")
        passed = (status == 200 and data.get("status") == "ok" and 
                  data.get("mode") == "agents" and data.get("code") == "600519" and
                  len(data.get("forces", [])) >= 5 and bool(data.get("stage")))
        log_test("Test 4: /api/sim?code=sh600519 个股博弈看板矩阵生成", passed, 
                 f"mode: {data.get('mode')}, forces: {len(data.get('forces', []))}, stage: {data.get('stage')}")
    except Exception as e:
        log_test("Test 4: /api/sim?code=sh600519 个股博弈看板矩阵生成", False, str(e))

    # Test 5: /api/watchlist with mixed prefixed codes
    try:
        status, data = fetch_json("/api/watchlist?codes=sh600519,000001.SZ,sz300750")
        codes_ret = [x.get("code") for x in data] if isinstance(data, list) else []
        passed = status == 200 and "600519" in codes_ret and "000001" in codes_ret and "300750" in codes_ret
        log_test("Test 5: /api/watchlist 批量混合前后缀自选股清洗", passed, f"成功解析: {codes_ret}")
    except Exception as e:
        log_test("Test 5: /api/watchlist 批量混合前后缀自选股清洗", False, str(e))

    # Test 6: Custom scenario with quotes and special punctuation in /api/sim
    try:
        title = "巴菲特声明: 'A股具备性价比' & 央行降准50BP!"
        encoded_title = urllib.parse.quote(title)
        status, data = fetch_json(f"/api/sim?scenario={encoded_title}")
        passed = (status == 200 and data.get("status") == "ok" and 
                  data.get("mode") == "sim" and len(data.get("forces", [])) >= 5)
        log_test("Test 6: /api/sim 特殊字符与单引号事件注入推演", passed, 
                 f"domain: {data.get('domain')}, forces: {len(data.get('forces', []))}")
    except Exception as e:
        log_test("Test 6: /api/sim 特殊字符与单引号事件注入推演", False, str(e))

    # Test 7: /api/data_status health check
    try:
        status, data = fetch_json("/api/data_status")
        sources = data.get("sources", {})
        tx = sources.get("tencent", {}).get("status")
        sn = sources.get("sina", {}).get("status")
        passed = status == 200 and (tx == "healthy" or sn == "healthy")
        log_test("Test 7: /api/data_status 多通道健康度上报", passed, f"tx: {tx}, sn: {sn}")
    except Exception as e:
        log_test("Test 7: /api/data_status 多通道健康度上报", False, str(e))

    # Test 8: /api/auction radar endpoint
    try:
        status, data = fetch_json("/api/auction")
        passed = status == 200 and ("promotion_metrics" in data or "weak_to_strong" in data)
        log_test("Test 8: /api/auction 集合竞价雷达接口", passed, f"状态: {data.get('status', 'ok')}, 指标项: {list(data.keys())[:4]}")
    except Exception as e:
        log_test("Test 8: /api/auction 集合竞价雷达接口", False, str(e))

    # Test 9: /api/screen with pattern parameter edge cases
    try:
        status, data = fetch_json("/api/screen?patterns=none_exist_pattern")
        passed = status == 200 and data.get("status") == "ok"
        log_test("Test 9: /api/screen 不存在形态参数容错", passed, f"status: {data.get('status')}")
    except Exception as e:
        log_test("Test 9: /api/screen 不存在形态参数容错", False, str(e))

    # Test 10: Concurrency stress testing (5 parallel requests to /api/sim)
    try:
        t0 = time.time()
        sim_endpoints = [
            "/api/sim?code=600519",
            "/api/sim?scenario=%E9%99%8D%E6%BA%96",
            "/api/sim?code=000001",
            "/api/sim?scenario=%E5%A4%96%E7%9B%98%E5%A4%A7%E6%B6%A8",
            "/api/sim?code=300750"
        ]
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(fetch_json, ep) for ep in sim_endpoints]
            resps = [f.result() for f in futures]
        elapsed = time.time() - t0
        all_ok = all(s == 200 and d.get("status") == "ok" for s, d in resps)
        log_test("Test 10: /api/sim 5路并发推演与重定向隔离", all_ok, f"耗时: {elapsed:.2f}s, 全部成功: {all_ok}")
    except Exception as e:
        log_test("Test 10: /api/sim 5路并发推演与重定向隔离", False, str(e))

    # Test 11: High-concurrency market refresh & cache hits
    try:
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(fetch_json, "/api/market") for _ in range(6)]
            resps = [f.result() for f in futures]
        elapsed = time.time() - t0
        all_ok = all(s == 200 and "indices" in d for s, d in resps)
        from_caches = sum(1 for s, d in resps if d.get("from_cache"))
        log_test("Test 11: /api/market 高并发热点抗压与缓存命中", all_ok, f"耗时: {elapsed:.2f}s, 缓存命中数: {from_caches}/6")
    except Exception as e:
        log_test("Test 11: /api/market 高并发热点抗压与缓存命中", False, str(e))

    # Test 12: Strategies fast fallback test
    try:
        status, data = fetch_json("/api/strategies?mode=auto")
        strats = data.get("strategies", [])
        passed = status == 200 and isinstance(strats, list) and len(strats) > 0
        log_test("Test 12: /api/strategies 策略库自适应选股", passed, f"策略数: {len(strats)}, 耗时: {data.get('elapsed', 0)}s, 周期: {data.get('stage')}")
    except Exception as e:
        log_test("Test 12: /api/strategies 策略库自适应选股", False, str(e))

    print("=" * 60)
    passed_count = sum(1 for _, p, _ in results if p)
    total_count = len(results)
    print(f"第二轮找茬与并发优化测试结果: {passed_count}/{total_count} PASSED")
    print("=" * 60)
    return passed_count == total_count

if __name__ == "__main__":
    success = test_round2()
    sys.exit(0 if success else 1)
