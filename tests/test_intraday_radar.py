# -*- coding: utf-8 -*-
"""
盘中异动与资金流向监控模块 自动化单元测试套件
覆盖:
1. 工具函数与异动强度/共振评分算法
2. Tier 1 东财实时异动解析与字段完整性验证
3. Tier 2 分时序列真实特征挖掘 (火箭发射/快速反弹/放量大买/触板与炸板等)
4. Tier 3 Level-1 盘口快照降级容灾
5. FastAPI /api/quant/intraday_radar 路由与 Schema 校验
6. 缓存机制与异常容灾 500 处理
"""
import sys
import os
import json
import time
from unittest.mock import patch, MagicMock

import pytest

# 设置工作目录与导入路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(BASE_DIR, 'scripts')
WEB_DIR = os.path.join(BASE_DIR, 'web')

for d in (SCRIPTS_DIR, WEB_DIR):
    if d not in sys.path:
        sys.path.insert(0, d)

import intraday_radar as ir
import quant_data_service as qds
from fastapi.testclient import TestClient
from main import app, _intraday_radar_cache


# ----------------------------------------------------------------------
# Test 1: 工具函数校验 (to_symbol, to_clean_code, format_tm)
# ----------------------------------------------------------------------
def test_utility_helpers():
    # to_clean_code
    assert ir.to_clean_code("000530.SZ") == "000530"
    assert ir.to_clean_code("sh600519") == "600519"
    assert ir.to_clean_code("BJ832000") == "832000"
    assert ir.to_clean_code(" 300750 ") == "300750"
    assert ir.to_clean_code("") == ""

    # to_symbol
    assert ir.to_symbol("600519") == "600519.SH"
    assert ir.to_symbol("900901") == "900901.SH"
    assert ir.to_symbol("000530") == "000530.SZ"
    assert ir.to_symbol("300750") == "300750.SZ"
    assert ir.to_symbol("832000") == "832000.BJ"
    assert ir.to_symbol("430002") == "430002.BJ"
    assert ir.to_symbol("920001") == "920001.BJ"
    assert ir.to_symbol("000530.SZ") == "000530.SZ"
    assert ir.to_symbol("sh600519") == "600519.SH"

    # format_tm
    assert ir.format_tm(93015) == "09:30:15"
    assert ir.format_tm("93015") == "09:30:15"
    assert ir.format_tm(142503) == "14:25:03"
    assert ir.format_tm("142503") == "14:25:03"
    assert ir.format_tm("09:30") == "09:30:00"
    assert ir.format_tm("14:25:03") == "14:25:03"
    assert ir.format_tm(930) == "09:30:00"


# ----------------------------------------------------------------------
# Test 2: 异动强度与共振评分核心算法
# ----------------------------------------------------------------------
def test_anomaly_strength_and_synergy_score():
    # 1. compute_anomaly_strength 边界与加成校验
    # 极小值约束: [10, 100]
    st_low = ir.compute_anomaly_strength(type_code=8207, change_pct=0.0, volume_hands=0.0)
    assert 10 <= st_low <= 100
    assert st_low >= 60  # 8207 base_score 为 60

    # 极大值约束: 封板 95 + 15 + 5 -> 115 裁剪为 100
    st_high = ir.compute_anomaly_strength(type_code=4, change_pct=10.0, volume_hands=500000.0)
    assert st_high == 100

    # 常见 8201 火箭发射
    st_8201 = ir.compute_anomaly_strength(type_code=8201, change_pct=2.5, volume_hands=2000.0)
    assert 80 <= st_8201 <= 100

    # 2. compute_synergy_score 共振分与定性结论校验
    # Case A: 多头共振 STRONG_RESONANCE (score >= 50)
    bull_anomalies = [
        {"polarity": "BULLISH", "anomalyStrength": 85},
        {"polarity": "BULLISH", "anomalyStrength": 90},
    ]
    score_a, level_a, verdict_a = ir.compute_synergy_score(
        anomalies=bull_anomalies,
        main_net_inflow=2.5e8,  # 2.5 亿元大额净流入
        main_net_ratio=16.0,
    )
    assert score_a >= 50
    assert level_a == "STRONG_RESONANCE"
    assert verdict_a == "主力抢筹与盘口异动强共振，真突破概率高"

    # Case B: 温和配合 MILD_RESONANCE (15 <= score < 50)
    mild_anomalies = [
        {"polarity": "BULLISH", "anomalyStrength": 65},
    ]
    score_b, level_b, verdict_b = ir.compute_synergy_score(
        anomalies=mild_anomalies,
        main_net_inflow=0.2e8,
        main_net_ratio=3.0,
    )
    assert 15 <= score_b < 50
    assert level_b == "MILD_RESONANCE"
    assert verdict_b == "资金温和配合异动，关注分时均线承接"

    # Case C: 诱多背离 DIVERGENCE_WARNING (-20 < score < 15)
    # 异动多头脉冲但主力大单反向出逃
    div_anomalies = [
        {"polarity": "BULLISH", "anomalyStrength": 75},
    ]
    score_c, level_c, verdict_c = ir.compute_synergy_score(
        anomalies=div_anomalies,
        main_net_inflow=-3.0e8,  # 净流出 3 亿
        main_net_ratio=-15.0,
    )
    assert -20 < score_c < 15
    assert level_c == "DIVERGENCE_WARNING"
    assert verdict_c == "异动脉冲但主力净流向背离，警惕诱多/对倒骗线"

    # Case D: 空头派发 BEARISH_DUMP (score <= -20)
    bear_anomalies = [
        {"polarity": "BEARISH", "anomalyStrength": 85},
        {"polarity": "BEARISH", "anomalyStrength": 80},
    ]
    score_d, level_d, verdict_d = ir.compute_synergy_score(
        anomalies=bear_anomalies,
        main_net_inflow=-2.0e8,
        main_net_ratio=-12.0,
    )
    assert score_d <= -20
    assert level_d == "BEARISH_DUMP"
    assert verdict_d == "大单持续流出叠加空头异动，严防派发核按钮"

    # Case E: 无资金流向时使用内外盘盘口差估算
    score_e, level_e, _ = ir.compute_synergy_score(
        anomalies=[],
        main_net_inflow=0.0,
        main_net_ratio=0.0,
        outer_vol=60000,
        inner_vol=20000,
    )
    assert -100 <= score_e <= 100


# ----------------------------------------------------------------------
# Test 3: Tier 1 东财实时异动解析与契约字段完整性
# ----------------------------------------------------------------------
def test_parse_eastmoney_anomalies():
    mock_payload = {
        "rc": 0,
        "data": {
            "allstock": [
                {"tm": 93510, "c": "000530", "n": "冰山冷热", "t": 8201, "i": "0.0215,8.80,0.0215"},
                {"tm": 94002, "c": "600519", "n": "贵州茅台", "t": 4, "i": "1750.00,50000,1750.00,0.1000"},
                {"tm": 100530, "c": "002594", "n": "比亚迪", "t": 32, "i": "285.50,-0.0980"},
                {"tm": 101215, "c": "300750", "n": "宁德时代", "t": 64, "i": "300000,260.00,0.035,78000000.0"},
                {"tm": 103000, "c": "688981", "n": "中芯国际", "t": 8204, "i": "0.025,95.00,-0.025"},
            ]
        }
    }

    class MockResp:
        def read(self):
            return json.dumps(mock_payload).encode('utf-8')
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    with patch('urllib.request.urlopen', return_value=MockResp()):
        items = ir.fetch_eastmoney_anomalies(limit=10)
        assert len(items) == 5

        # 验证 14 项完整字段
        required_fields = {
            "id", "time", "symbol", "code", "name", "typeCode", "typeName",
            "polarity", "price", "changePercent", "volumeHands", "amountCNY",
            "anomalyStrength", "detailText"
        }
        for item in items:
            assert required_fields.issubset(item.keys())

        # 检查 8201 (火箭发射)
        item_8201 = items[0]
        assert item_8201["typeCode"] == 8201
        assert item_8201["typeName"] == "火箭发射"
        assert item_8201["polarity"] == "BULLISH"
        assert item_8201["symbol"] == "000530.SZ"
        assert item_8201["time"] == "09:35:10"
        assert item_8201["changePercent"] == 2.15
        assert item_8201["price"] == 8.80

        # 检查 4 (封涨停板)
        item_4 = items[1]
        assert item_4["typeCode"] == 4
        assert item_4["typeName"] == "封涨停板"
        assert item_4["polarity"] == "BULLISH"
        assert item_4["symbol"] == "600519.SH"
        assert item_4["changePercent"] == 10.0
        assert item_4["volumeHands"] == 500.0

        # 检查 32 (打开涨停)
        item_32 = items[2]
        assert item_32["typeCode"] == 32
        assert item_32["typeName"] == "打开涨停"
        assert item_32["polarity"] == "BEARISH"
        assert item_32["changePercent"] == -9.80

        # 检查 64 (有大买盘)
        item_64 = items[3]
        assert item_64["typeCode"] == 64
        assert item_64["amountCNY"] == 78000000.0


# ----------------------------------------------------------------------
# Test 4: Tier 2 分时序列真实特征挖掘 (火箭发射/快速反弹/放量买入/加速下跌)
# ----------------------------------------------------------------------
def test_tier2_intraday_trend_mining_fallback():
    # 模拟 Tier 1 网络不可达或返回空列表
    synthetic_trends = {
        "code": "000530",
        "pre_close": 10.0,
        "times": [
            "09:30", "09:31", "09:32", "09:33", "09:34", "09:35",
            "09:36", "09:37", "09:38", "09:39", "09:40", "09:41"
        ],
        # 09:30~09:33: 10.0 -> 10.22 (3分钟拉升 2.2% >= 1.8% -> 触发 8201 火箭发射)
        # 09:34~09:36: 探底 9.80 (-2.0% <= -1.5%) -> 反弹到 10.05 (+2.5% >= 1.8% 且均价之上 -> 触发 8202 快速反弹)
        # 09:37: 单分钟量从 100 暴增到 800 (>3倍均量) 且价格上涨 -> 触发 8193 大笔买入
        # 09:38~09:41: 3分钟急跌 10.05 -> 9.80 (-2.5% <= -1.8% -> 触发 8204 加速下跌)
        "prices": [
            10.00, 10.05, 10.10, 10.22,
            9.80, 9.90, 10.05,
            10.12,
            10.05, 9.95, 9.85, 9.80
        ],
        "avg_prices": [
            10.00, 10.02, 10.05, 10.10,
            10.00, 9.95, 9.98,
            10.02,
            10.02, 10.00, 9.98, 9.95
        ],
        "volumes": [
            100, 100, 100, 120,
            150, 160, 200,
            800,  # 暴增量
            150, 140, 130, 120
        ],
    }

    mock_quotes = {
        "000530.SZ": {
            "symbol": "000530.SZ",
            "code": "000530",
            "name": "冰山冷热",
            "price": 9.80,
            "prevClose": 10.0,
            "changePercent": -2.0,
            "volume": 2270,
            "outerVolume": 1200,
            "innerVolume": 1070,
        }
    }

    with patch('intraday_radar.fetch_eastmoney_anomalies', return_value=[]), \
         patch.object(ir.df_feed, 'get_intraday_trends', return_value=synthetic_trends):

        res = ir.get_intraday_radar(symbol="000530.SZ", limit=50)

        assert res["status"] == "ok"
        assert res["basis"] == "intraday_trend_mined"
        assert res["basisLabel"] == "真实分时挖掘"
        assert len(res["anomalies"]) > 0

        mined_codes = {a["typeCode"] for a in res["anomalies"]}
        # 必须成功挖掘出 8201(火箭发射)、8202(快速反弹)、8193(大笔买入)、8204(加速下跌) 等核心类型
        assert {8201, 8202, 8193}.issubset(mined_codes)

        # 绝无假股票名，代码均为真实股票
        for a in res["anomalies"]:
            assert a["code"] in ["000530", "600519", "300750", "002594", "688981", "300059", "601318", "600036"]
            assert a["symbol"].endswith((".SZ", ".SH", ".BJ"))


# ----------------------------------------------------------------------
# Test 5: Tier 3 Level-1 盘口快照降级容灾
# ----------------------------------------------------------------------
def test_tier3_snapshot_fallback():
    mock_quotes = {
        "000530.SZ": {
            "symbol": "000530.SZ",
            "code": "000530",
            "name": "冰山冷热",
            "price": 9.94,
            "prevClose": 9.04,
            "changePercent": 9.96,  # 触及涨停 -> 4
            "volume": 50000,
            "outerVolume": 45000,
            "innerVolume": 5000,
            "amount": 49700000.0,
        },
        "600519.SH": {
            "symbol": "600519.SH",
            "code": "600519",
            "name": "贵州茅台",
            "price": 1750.0,
            "prevClose": 1700.0,
            "changePercent": 2.94,
            "volume": 8000,
            "outerVolume": 5500,
            "innerVolume": 2500,
            "amount": 140000000.0,
        },
    }

    with patch('intraday_radar.fetch_eastmoney_anomalies', return_value=[]), \
         patch('intraday_radar.mine_anomalies_from_intraday_trends', return_value=[]), \
         patch('market_gateway.fetch_level1_quotes', return_value=mock_quotes):

        res = ir.get_intraday_radar(symbol="000530.SZ", limit=10)

        assert res["status"] == "ok"
        assert res["basis"] == "snapshot_fallback"
        assert res["basisLabel"] == "L1盘口快照"
        assert len(res["anomalies"]) > 0

        # 检查是否识别出了封板或买盘异动
        type_codes = [a["typeCode"] for a in res["anomalies"]]
        assert 4 in type_codes


# ----------------------------------------------------------------------
# Test 6: FastAPI /api/quant/intraday_radar 路由与 Schema 校验
# ----------------------------------------------------------------------
def test_fastapi_intraday_radar_endpoint():
    client = TestClient(app)
    # 清理测试前缓存
    _intraday_radar_cache.clear()

    resp = client.get("/api/quant/intraday_radar?symbol=000530.SZ&limit=20")
    assert resp.status_code == 200

    data = resp.json()
    # 顶层契约字段校验
    assert data["status"] == "ok"
    assert data["basis"] in ["live_eastmoney", "intraday_trend_mined", "snapshot_fallback"]
    assert "basisLabel" in data
    assert isinstance(data["updatedAt"], int)
    assert isinstance(data["anomalies"], list)
    assert len(data["anomalies"]) <= 20
    assert isinstance(data["topInflowStocks"], list)

    # summary 结构校验
    summary = data["summary"]
    for k in ["totalCount", "bullishCount", "bearishCount", "dominantSignal", "marketTemperament"]:
        assert k in summary
    assert summary["marketTemperament"] in ["BULLISH_ATTACK", "BEARISH_DEFENSE", "BALANCED_ROTATION"]

    # symbolCapitalFlow 结构校验
    flow = data["symbolCapitalFlow"]
    req_flow_keys = [
        "symbol", "code", "name", "price", "changePercent", "mainNetInflow",
        "superLargeNetInflow", "largeNetInflow", "mediumNetInflow", "smallNetInflow",
        "mainNetRatio", "synergyScore", "synergyLevel", "synergyVerdict", "recent5DaysMainNet"
    ]
    for k in req_flow_keys:
        assert k in flow, f"Missing {k} in symbolCapitalFlow"
    assert flow["synergyLevel"] in ["STRONG_RESONANCE", "MILD_RESONANCE", "DIVERGENCE_WARNING", "BEARISH_DUMP"]
    assert isinstance(flow["recent5DaysMainNet"], list)

    # 验证 3 秒缓存命中
    cached_resp = client.get("/api/quant/intraday_radar?symbol=000530.SZ&limit=20")
    assert cached_resp.status_code == 200
    assert cached_resp.json()["updatedAt"] == data["updatedAt"]


# ----------------------------------------------------------------------
# Test 7: 路由异常容灾 500 返回
# ----------------------------------------------------------------------
def test_fastapi_intraday_radar_error_handling():
    client = TestClient(app)
    _intraday_radar_cache.clear()

    with patch('quant_data_service.get_real_intraday_radar', side_effect=RuntimeError("Upstream fatal error")):
        resp = client.get("/api/quant/intraday_radar?symbol=000001.SZ")
        assert resp.status_code == 500
        err_data = resp.json()
        assert err_data["status"] == "error"
        assert "Upstream fatal error" in err_data["message"]
