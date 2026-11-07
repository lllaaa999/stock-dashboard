# -*- coding: utf-8 -*-
"""
单元测试：全球全资产监控与跨市场传导链 + 7×24 快讯
涵盖：
1. 新浪与腾讯双源行情解析器（hf_, int_, gb_, rt_hk, fx_s, gtimg 格式与精度）
2. 标的分组与双源互备回退机制
3. 八大跨市场关联传导链（USDCNH 反向汇率逻辑、科技/大宗商品共振、A股映射标的）
4. 7×24 快讯清洗打标与网络超时容错降级
5. Focus 引擎与 Narrator 接入（THEME 走强、RISK 拖累、NEWS 填充与数字一致性校验）
6. FastAPI 端点 GET /api/market/global_radar 契约与 10 秒内存缓存
"""

import json
import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for d in (os.path.join(BASE_DIR, "scripts"), os.path.join(BASE_DIR, "web")):
    if d not in sys.path:
        sys.path.insert(0, d)

import global_market_radar as gmr
import focus_engine as fe
import focus_narrator as fn
from main import app, _global_radar_cache


# =====================================================================
# 1. 新浪与腾讯双源解析器单元测试
# =====================================================================

def test_parse_sina_futures_hf():
    """测试新浪外盘期货 hf_ 解析（现价、昨结算、昨结算为0时的兜底、涨跌幅）"""
    mock_text = (
        'var hq_str_hf_CHA50CFD="12800.000,,12700.000,12850.000,12890.000,12680.000,05:14:59,12500.000,12500.000,1000,1,1,2026-11-07,富时中国A50期货,0";\n'
        'var hq_str_hf_GC="4100.000,,4000.000,4120.000,4150.000,3980.000,05:59:59,0.000,0.000,0,1,1,2026-11-07,纽约黄金,0";\n'
    )
    res = gmr.parse_sina_quote(mock_text)
    assert "hf_CHA50CFD" in res
    a50 = res["hf_CHA50CFD"]
    assert a50["price"] == 12800.0
    assert a50["prevClose"] == 12500.0
    assert a50["change"] == 300.0
    assert a50["changePercent"] == 2.4  # (12800 - 12500) / 12500 * 100 = 2.4%

    # 昨结算为 0 时，兜底用 v[2] (4000.0)
    assert "hf_GC" in res
    gc = res["hf_GC"]
    assert gc["price"] == 4100.0
    assert gc["prevClose"] == 4000.0
    assert gc["change"] == 100.0
    assert gc["changePercent"] == 2.5


def test_parse_sina_global_index_int():
    """测试新浪全球指数 int_ 解析（现价、涨跌额、带%与不带%的涨跌幅）"""
    mock_text = (
        'var hq_str_int_hangseng="恒生指数,24500.00,-250.00,-1.01%";\n'
        'var hq_str_int_nasdaq="纳斯达克,22500.00,150.00,0.67";\n'
    )
    res = gmr.parse_sina_quote(mock_text)
    hsi = res["int_hangseng"]
    assert hsi["name"] == "恒生指数"
    assert hsi["price"] == 24500.0
    assert hsi["change"] == -250.0
    assert hsi["changePercent"] == -1.01

    nasdaq = res["int_nasdaq"]
    assert nasdaq["price"] == 22500.0
    assert nasdaq["change"] == 150.0
    assert nasdaq["changePercent"] == 0.67


def test_parse_sina_us_and_hk_stocks():
    """测试新浪美股 gb_ 与港股 rt_hk 解析"""
    mock_text = (
        'var hq_str_gb_nvda="英伟达,190.0000,3.50,2026-11-07 09:42:04,6.42,185.0000,192.0000,184.0000,240.00,160.00,1000,1000,450000,0,0,0,0,0,0,0,0,0,0,0,0,0,183.5800";\n'
        'var hq_str_rt_hk00700="00700,腾讯控股,TENCENT,420.000,430.000,422.000,425.000,5.000,1.19,428.000,418.000";\n'
    )
    res = gmr.parse_sina_quote(mock_text)
    nvda = res["gb_nvda"]
    assert nvda["name"] == "英伟达"
    assert nvda["price"] == 190.0
    assert nvda["changePercent"] == 3.5
    assert nvda["prevClose"] == 183.58

    tx = res["rt_hk00700"]
    assert tx["name"] == "腾讯控股"
    assert tx["price"] == 425.0
    assert tx["prevClose"] == 420.0
    assert tx["changePercent"] == 1.19


def test_parse_sina_forex_fx_s():
    """测试新浪外汇 fx_s 解析（汇率现价、涨跌幅提取）"""
    mock_text = (
        'var hq_str_fx_susdcnh="05:58:52,7.1250,7.1260,7.1250,138,7.1500,7.1600,7.1100,7.1250,离岸人民币,-0.35,-0.0250,0.002,,7.25,7.05,,2026-11-07";\n'
    )
    res = gmr.parse_sina_quote(mock_text)
    cnh = res["fx_susdcnh"]
    assert cnh["price"] == 7.125
    assert cnh["changePercent"] == -0.35
    assert cnh["change"] == -0.025


def test_parse_gtimg_quotes():
    """测试腾讯行情 qt.gtimg.cn 按 ~ 分割解析"""
    mock_text = (
        'v_hkHSI="100~恒生指数~HSI~24481.860~24796.980~24404.620~24742770~0~0~24481.860~0~0~0~0~0~0~0~0~0~24481.860~0~0~0~0~0~0~0~0~0~0.0~2026/11/06 18:30:50~-315.120~-1.27~24740.180~24349.300~";\n'
        'v_usNVDA="200~英伟达~NVDA.OQ~186.64~181.60~191.10~180212285~0~0~188.69~0~0~0~0~0~0~0~0~0~188.75~0~0~0~0~0~0~0~0~0~~2026-11-06 16:00:01~5.04~2.78~194.90~185.22~";\n'
    )
    res = gmr.parse_gtimg_quote(mock_text)
    assert "hkHSI" in res
    hsi = res["hkHSI"]
    assert hsi["name"] == "恒生指数"
    assert hsi["price"] == 24481.86
    assert hsi["prevClose"] == 24796.98
    assert hsi["change"] == -315.12
    assert hsi["changePercent"] == -1.27

    assert "usNVDA" in res
    nvda = res["usNVDA"]
    assert nvda["price"] == 186.64
    assert nvda["prevClose"] == 181.6
    assert nvda["change"] == 5.04
    assert nvda["changePercent"] == 2.78


# =====================================================================
# 2. 标的分组与双源互备回退测试
# =====================================================================

def test_dual_source_fallback_logic():
    """测试主源失效时，自动从备选源读取并正确按 5 大组分类"""
    mock_gtimg = {
        "usNVDA": {"gtimg_id": "usNVDA", "name": "英伟达", "price": 185.0, "changePercent": 2.5, "prevClose": 180.0, "change": 5.0},
    }
    mock_sina = {
        "gb_tsm": {"sina_id": "gb_tsm", "name": "台积电", "price": 200.0, "changePercent": 3.0, "prevClose": 194.17, "change": 5.83},
        "hf_CHA50CFD": {"sina_id": "hf_CHA50CFD", "name": "A50", "price": 13000.0, "changePercent": 1.2, "prevClose": 12845.8, "change": 154.2},
    }

    with patch.object(gmr, "parse_gtimg_quote", return_value=mock_gtimg), \
         patch.object(gmr, "parse_sina_quote", return_value=mock_sina), \
         patch.object(gmr, "_http_get", return_value="dummy"):
        assets = gmr.fetch_all_quotes()

    assert assets["NVDA"]["source"] == "gtimg"
    assert assets["NVDA"]["price"] == 185.0
    assert assets["TSM"]["source"] == "sina"
    assert assets["TSM"]["price"] == 200.0
    assert assets["CHA50CFD"]["source"] == "sina"
    assert assets["CHA50CFD"]["price"] == 13000.0

    # 验证资产数量覆盖与分组
    all_categories = {a["category"] for a in gmr.ASSET_CONFIGS}
    assert all_categories == {"ASIA_CORE", "US_EU_INDICES", "TECH_GIANTS", "COMMODITIES", "FOREX"}
    assert len(gmr.ASSET_CONFIGS) >= 28


# =====================================================================
# 3. 八大跨市场关联传导链计算测试
# =====================================================================

def test_transmission_chains_usdcnh_inversion():
    """测试 A 股开盘链中离岸人民币 USDCNH 的反向汇率逻辑（升值即跌幅 -> A股正向贡献）"""
    mock_assets = {
        "CHA50CFD": {"symbol": "CHA50CFD", "name": "A50", "price": 13000.0, "changePercent": 1.5},
        "HSI": {"symbol": "HSI", "name": "恒指", "price": 24000.0, "changePercent": 1.2},
        "HSTECH": {"symbol": "HSTECH", "name": "恒科", "price": 4200.0, "changePercent": 2.0},
        # 人民币升值，USDCNH 下跌 0.8% -> multiplier=-1.0, 有效贡献 +0.8%
        "USDCNH": {"symbol": "USDCNH", "name": "离岸人民币", "price": 7.1000, "changePercent": -0.8},
    }
    chains = gmr.calculate_transmission_chains(mock_assets)
    a_chain = [c for c in chains if c["id"] == "chain_a_open"][0]

    # 所有 4 个驱动因子全部为正向利好贡献 (1.5, 1.2, 2.0, +0.8)
    assert a_chain["direction"] == "BULLISH"
    assert a_chain["resonanceScore"] > 30.0
    assert len(a_chain["mappedSymbols"]) >= 2
    assert any(s["symbol"] == "600519.SH" for s in a_chain["mappedSymbols"])
    assert any(s["symbol"] == "300059.SZ" for s in a_chain["mappedSymbols"])


def test_transmission_chains_tech_and_commodities():
    """测试 AI 算力科技链与避险贵金属大宗商品链共振及代表标的映射"""
    mock_assets = {
        "NVDA": {"symbol": "NVDA", "name": "英伟达", "price": 190.0, "changePercent": 4.5},
        "TSM": {"symbol": "TSM", "name": "台积电", "price": 200.0, "changePercent": 3.8},
        "AMD": {"symbol": "AMD", "name": "超威半导体", "price": 150.0, "changePercent": 3.2},
        "AVGO": {"symbol": "AVGO", "name": "博通", "price": 180.0, "changePercent": 2.9},
        "ASML": {"symbol": "ASML", "name": "阿斯麦", "price": 950.0, "changePercent": 3.0},
        "IXIC": {"symbol": "IXIC", "name": "纳斯达克", "price": 22500.0, "changePercent": 2.2},
        # 贵金属暴跌
        "GC": {"symbol": "GC", "name": "COMEX黄金", "price": 3900.0, "changePercent": -3.5},
        "SI": {"symbol": "SI", "name": "COMEX白银", "price": 42.0, "changePercent": -4.2},
        "HG": {"symbol": "HG", "name": "COMEX美铜", "price": 4.5, "changePercent": -2.8},
    }
    chains = gmr.calculate_transmission_chains(mock_assets)
    # 按 abs(resonanceScore) 降序
    scores = [abs(c["resonanceScore"]) for c in chains]
    assert scores == sorted(scores, reverse=True)

    tech_chain = [c for c in chains if c["id"] == "chain_ai_semi"][0]
    assert tech_chain["direction"] == "BULLISH"
    assert tech_chain["intensity"] == "STRONG"
    assert tech_chain["resonanceScore"] >= 50.0
    assert any(s["symbol"] == "300308.SZ" for s in tech_chain["mappedSymbols"])

    gold_chain = [c for c in chains if c["id"] == "chain_gold_metal"][0]
    assert gold_chain["direction"] == "BEARISH"
    assert gold_chain["resonanceScore"] <= -50.0
    assert any(s["symbol"] == "601899.SH" for s in gold_chain["mappedSymbols"])


# =====================================================================
# 4. 7×24 快讯清洗打标与网络容错测试
# =====================================================================

def test_live_news_tagging_and_cleaning():
    """测试快讯标题清洗、分类与多空强弱打标"""
    raw_feed = {
        "result": {
            "data": {
                "feed": {
                    "list": [
                        {
                            "id": "1001",
                            "create_time": "2026-11-07 14:30:00",
                            "rich_text": "<p>【突发重磅！美联储宣布降息50个基点，全球风险偏好大涨】<br/>鲍威尔表示通胀回到控制范围。</p>",
                            "docurl": "http://finance.sina.com.cn/1001",
                        },
                        {
                            "id": "1002",
                            "create_time": "2026-11-07 14:25:00",
                            "rich_text": "【英伟达与台积电宣布新一代先进封装芯片量产突破】算力出货量预计超预期增长。",
                            "docurl": "",
                        },
                        {
                            "id": "1003",
                            "create_time": "2026-11-07 14:20:00",
                            "rich_text": "中东产油国地缘冲突加剧导致国际原油期货价格暴跌承压走弱。",
                            "docurl": "",
                        },
                    ]
                }
            }
        }
    }

    with patch.object(gmr, "urllib") as mock_url:
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(raw_feed).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_url.request.urlopen.return_value = mock_resp

        news = gmr.fetch_global_live_news(limit=10)

    assert len(news) == 3
    n1 = news[0]
    assert n1["title"] == "突发重磅！美联储宣布降息50个基点，全球风险偏好大涨"
    assert n1["category"] == "GLOBAL_MACRO"
    assert n1["polarity"] == "BULLISH"
    assert n1["importance"] == "HIGH"

    n2 = news[1]
    assert n2["category"] == "TECH_INDUSTRY"
    assert n2["polarity"] == "BULLISH"

    n3 = news[2]
    assert n3["category"] == "COMMODITY_FX"
    assert n3["polarity"] == "BEARISH"


def test_live_news_timeout_graceful_fallback():
    """测试网络超时时不抛异常，平滑返回已有快讯或空列表"""
    with patch.object(gmr.urllib.request, "urlopen", side_effect=TimeoutError("Request timed out")):
        news = gmr.fetch_global_live_news(limit=5)
        assert isinstance(news, list)


# =====================================================================
# 5. Focus 引擎与 Narrator 接入测试
# =====================================================================

def test_focus_engine_global_radar_integration():
    """测试 build_focus 接入 global_radar 后：
    1. resonanceScore >= 35 生成 THEME 走强条目并关联 A 股标的
    2. resonanceScore <= -35 生成 RISK 拖累条目
    3. liveNews 填充 news 分区
    4. 所有生成的 narrative 满足 focus_narrator 数字一致性校验
    """
    mock_radar_data = {
        "status": "ok",
        "transmissionChains": [
            {
                "id": "chain_ai_semi",
                "name": "AI算力与硬科技半导体链",
                "resonanceScore": 48.5,
                "direction": "BULLISH",
                "intensity": "STRONG",
                "driverAssets": [
                    {"name": "英伟达", "changePercent": 4.5},
                    {"name": "台积电", "changePercent": 3.8},
                ],
                "mappedSectors": ["CPO光模块", "AI算力芯片"],
                "mappedSymbols": [
                    {"symbol": "300308.SZ", "name": "中际旭创"},
                    {"symbol": "688256.SH", "name": "寒武纪"},
                ],
                "transmissionLogic": "算力芯片龙头大涨。",
            },
            {
                "id": "chain_gold_metal",
                "name": "全球避险与贵金属/工业有色链",
                "resonanceScore": -42.0,
                "direction": "BEARISH",
                "intensity": "MODERATE",
                "driverAssets": [
                    {"name": "COMEX黄金", "changePercent": -3.2},
                ],
                "mappedSectors": ["黄金贵金属"],
                "mappedSymbols": [
                    {"symbol": "601899.SH", "name": "紫金矿业"},
                ],
                "transmissionLogic": "黄金外盘大跌。",
            },
        ],
        "liveNews": [
            {
                "id": "9901",
                "time": "2026-11-07 15:30:00",
                "title": "全球半导体联盟Q3出货量超预期增长18%",
                "importance": "HIGH",
                "polarity": "BULLISH",
            },
            {
                "id": "9902",
                "time": "2026-11-07 15:20:00",
                "title": "中东停火协议取得重大进展",
                "importance": "NORMAL",
                "polarity": "NEUTRAL",
            },
        ],
    }

    ops = {
        "ladder": lambda: None,
        "theme_resonance": lambda: None,
        "intraday_radar": lambda: None,
        "regulatory": lambda l: None,
        "global_radar": lambda: mock_radar_data,
    }

    res = fe.build_focus(operators=ops, now_ms=1700000000000)

    # 1. 验证 THEME 包含 AI 算力跨市场走强条目
    theme_items = [i for i in res["themes"] if i["id"].startswith("theme-global-chain_ai_semi")]
    assert len(theme_items) == 1
    t_item = theme_items[0]
    assert t_item["level"] == "GREEN"
    assert "300308.SZ" in t_item["symbols"]
    assert "688256.SH" in t_item["symbols"]

    # 2. 验证 RISK 包含避险贵金属拖累条目
    risk_items = [i for i in res["risks"] if i["id"].startswith("risk-global-chain_gold_metal")]
    assert len(risk_items) == 1
    r_item = risk_items[0]
    assert r_item["level"] in ("RED", "YELLOW")
    assert "601899.SH" in r_item["symbols"]

    # 3. 验证 news 分区非空
    assert len(res["news"]) >= 2
    news_titles = [n["title"] for n in res["news"]]
    assert any("出货量" in t for t in news_titles)

    # 4. 关键安全检验：所有生成条目的 narrative 必须 100% 通过 focus_narrator 数字一致性校验！
    for item in res["items"]:
        is_consistent = fn.numbers_consistent(item["narrative"], item)
        assert is_consistent, f"Item {item['id']} narrative numbers inconsistent: {item['narrative']}"


# =====================================================================
# 6. FastAPI 端点 GET /api/market/global_radar 契约测试
# =====================================================================

def test_fastapi_global_radar_endpoint():
    """测试 GET /api/market/global_radar 路由契约与 10 秒内存缓存机制"""
    client = TestClient(app)

    # 重置缓存确保首次真实调用
    _global_radar_cache["data"] = None
    _global_radar_cache["ts"] = 0.0

    mock_res = {
        "status": "ok",
        "updatedAt": 1700000000000,
        "summary": {
            "globalRiskAppetite": "RISK_ON",
            "riskAppetiteLabel": "全球风险偏好升温",
            "a50ChangePercent": 1.25,
            "usdcnhPrice": 7.1234,
            "usdcnhChangePercent": -0.25,
            "topBullishChain": {"id": "chain_ai_semi", "resonanceScore": 60.0},
            "topBearishChain": None,
        },
        "assets": [
            {"symbol": "NVDA", "name": "英伟达", "category": "TECH_GIANTS", "price": 190.0, "changePercent": 3.0}
        ],
        "groups": {
            "ASIA_CORE": [],
            "US_EU_INDICES": [],
            "TECH_GIANTS": [
                {"symbol": "NVDA", "name": "英伟达", "category": "TECH_GIANTS", "price": 190.0, "changePercent": 3.0}
            ],
            "COMMODITIES": [],
            "FOREX": [],
        },
        "transmissionChains": [],
        "liveNews": [],
    }

    with patch("global_market_radar.get_global_market_radar", return_value=mock_res) as mock_get:
        # 第一次请求
        resp1 = client.get("/api/market/global_radar")
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["status"] == "ok"
        assert data1["summary"]["globalRiskAppetite"] == "RISK_ON"
        assert len(data1["assets"]) == 1
        assert mock_get.call_count == 1

        # 第二次请求（10 秒内命中内存缓存，底层函数不被重复调用）
        resp2 = client.get("/api/market/global_radar")
        assert resp2.status_code == 200
        assert mock_get.call_count == 1
