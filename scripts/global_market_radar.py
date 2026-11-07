# -*- coding: utf-8 -*-
"""
全球全资产监控与跨市场传导链 + 7×24 快讯 (global_market_radar.py)

功能：
1. 新浪 hq.sinajs.cn + 腾讯 qt.gtimg.cn 双源互备，覆盖 6 大类共 28+ 核心全球资产。
2. 计算八大跨市场关联传导链（A股外资开盘链、AI算力半导体链、特斯拉机器人链、苹果端侧消费电子链、中概互联内需链、避险贵金属工业有色链、地缘能源化工链、国际粮价种业链）。
3. 新浪 7×24 全球财经快讯抓取与结构化打标（宏观/科技/大宗/A股，多空极性与重要性）。
4. 汇总全球风险偏好定调与顶级传导共振，提供 API 缓存接口与 Focus 引擎算子接入。
"""

import json
import logging
import re
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------- 标的配置表
ASSET_CONFIGS: List[Dict[str, Any]] = [
    # ASIA_CORE (A股先行与亚太锚)
    {
        "symbol": "CHA50CFD",
        "name": "富时中国A50期指",
        "category": "ASIA_CORE",
        "sina_id": "hf_CHA50CFD",
        "gtimg_id": None,
    },
    {
        "symbol": "HSI",
        "name": "恒生指数",
        "category": "ASIA_CORE",
        "sina_id": "int_hangseng",
        "gtimg_id": "hkHSI",
    },
    {
        "symbol": "HSTECH",
        "name": "恒生科技指数",
        "category": "ASIA_CORE",
        "sina_id": "rt_hkHSTECH",
        "gtimg_id": "hkHSTECH",
    },
    {
        "symbol": "N225",
        "name": "日经225",
        "category": "ASIA_CORE",
        "sina_id": "int_nikkei",
        "gtimg_id": None,
    },
    # US_EU_INDICES (欧美股指与期指)
    {
        "symbol": "IXIC",
        "name": "纳斯达克综指",
        "category": "US_EU_INDICES",
        "sina_id": "int_nasdaq",
        "gtimg_id": "usIXIC",
    },
    {
        "symbol": "INX",
        "name": "标普500",
        "category": "US_EU_INDICES",
        "sina_id": "int_sp500",
        "gtimg_id": "usINX",
    },
    {
        "symbol": "DJI",
        "name": "道琼斯工业",
        "category": "US_EU_INDICES",
        "sina_id": "int_dji",
        "gtimg_id": "usDJI",
    },
    {
        "symbol": "NQ_FUT",
        "name": "纳指100期货",
        "category": "US_EU_INDICES",
        "sina_id": "hf_NQ",
        "gtimg_id": None,
    },
    {
        "symbol": "ES_FUT",
        "name": "标普500期货",
        "category": "US_EU_INDICES",
        "sina_id": "hf_ES",
        "gtimg_id": None,
    },
    {
        "symbol": "DAX",
        "name": "德国DAX30",
        "category": "US_EU_INDICES",
        "sina_id": "int_dax",
        "gtimg_id": None,
    },
    {
        "symbol": "FTSE",
        "name": "英国富时100",
        "category": "US_EU_INDICES",
        "sina_id": "int_ftse",
        "gtimg_id": None,
    },
    # TECH_GIANTS (全球科技巨头与中概锚)
    {
        "symbol": "NVDA",
        "name": "英伟达",
        "category": "TECH_GIANTS",
        "sina_id": "gb_nvda",
        "gtimg_id": "usNVDA",
    },
    {
        "symbol": "TSM",
        "name": "台积电",
        "category": "TECH_GIANTS",
        "sina_id": "gb_tsm",
        "gtimg_id": "usTSM",
    },
    {
        "symbol": "TSLA",
        "name": "特斯拉",
        "category": "TECH_GIANTS",
        "sina_id": "gb_tsla",
        "gtimg_id": "usTSLA",
    },
    {
        "symbol": "AAPL",
        "name": "苹果",
        "category": "TECH_GIANTS",
        "sina_id": "gb_aapl",
        "gtimg_id": "usAAPL",
    },
    {
        "symbol": "MSFT",
        "name": "微软",
        "category": "TECH_GIANTS",
        "sina_id": "gb_msft",
        "gtimg_id": "usMSFT",
    },
    {
        "symbol": "AMD",
        "name": "超威半导体",
        "category": "TECH_GIANTS",
        "sina_id": "gb_amd",
        "gtimg_id": "usAMD",
    },
    {
        "symbol": "AVGO",
        "name": "博通",
        "category": "TECH_GIANTS",
        "sina_id": "gb_avgo",
        "gtimg_id": "usAVGO",
    },
    {
        "symbol": "ASML",
        "name": "阿斯麦",
        "category": "TECH_GIANTS",
        "sina_id": "gb_asml",
        "gtimg_id": "usASML",
    },
    {
        "symbol": "BABA",
        "name": "阿里巴巴",
        "category": "TECH_GIANTS",
        "sina_id": "gb_baba",
        "gtimg_id": "usBABA",
    },
    {
        "symbol": "PDD",
        "name": "拼多多",
        "category": "TECH_GIANTS",
        "sina_id": "gb_pdd",
        "gtimg_id": "usPDD",
    },
    {
        "symbol": "HK00700",
        "name": "腾讯控股",
        "category": "TECH_GIANTS",
        "sina_id": "rt_hk00700",
        "gtimg_id": "hk00700",
    },
    # COMMODITIES (全球大宗商品：贵金属/工业金属/能源/农产品)
    {
        "symbol": "GC",
        "name": "COMEX黄金",
        "category": "COMMODITIES",
        "sina_id": "hf_GC",
        "gtimg_id": None,
    },
    {
        "symbol": "SI",
        "name": "COMEX白银",
        "category": "COMMODITIES",
        "sina_id": "hf_SI",
        "gtimg_id": None,
    },
    {
        "symbol": "HG",
        "name": "COMEX美铜",
        "category": "COMMODITIES",
        "sina_id": "hf_HG",
        "gtimg_id": None,
    },
    {
        "symbol": "CL",
        "name": "WTI纽约原油",
        "category": "COMMODITIES",
        "sina_id": "hf_CL",
        "gtimg_id": None,
    },
    {
        "symbol": "OIL",
        "name": "布伦特原油",
        "category": "COMMODITIES",
        "sina_id": "hf_OIL",
        "gtimg_id": None,
    },
    {
        "symbol": "NG",
        "name": "美国天然气",
        "category": "COMMODITIES",
        "sina_id": "hf_NG",
        "gtimg_id": None,
    },
    {
        "symbol": "SOYBEAN",
        "name": "CBOT美豆",
        "category": "COMMODITIES",
        "sina_id": "hf_S",
        "gtimg_id": None,
    },
    {
        "symbol": "CORN",
        "name": "CBOT美玉米",
        "category": "COMMODITIES",
        "sina_id": "hf_C",
        "gtimg_id": None,
    },
    # FOREX (全球汇率与流动性锚)
    {
        "symbol": "USDCNH",
        "name": "离岸人民币",
        "category": "FOREX",
        "sina_id": "fx_susdcnh",
        "gtimg_id": "fxUSDCNH",
    },
    {
        "symbol": "EURUSD",
        "name": "欧元兑美元",
        "category": "FOREX",
        "sina_id": "fx_seurusd",
        "gtimg_id": "fxEURUSD",
    },
    {
        "symbol": "USDJPY",
        "name": "美元兑日元",
        "category": "FOREX",
        "sina_id": "fx_susdjpy",
        "gtimg_id": "fxUSDJPY",
    },
]

ASSET_MAP = {a["symbol"]: a for a in ASSET_CONFIGS}

# ----------------------------------------------------------------- 八大跨市场传导链定义
TRANSMISSION_CHAINS_CONFIG: List[Dict[str, Any]] = [
    {
        "id": "chain_a_open",
        "name": "A股开盘与外资流动性链",
        "drivers": [
            {"symbol": "CHA50CFD", "multiplier": 1.0},
            {"symbol": "HSI", "multiplier": 1.0},
            {"symbol": "HSTECH", "multiplier": 1.0},
            {"symbol": "USDCNH", "multiplier": -1.0},  # 离岸人民币升值(USDCNH跌)为A股正向利好
        ],
        "mappedSectors": ["核心宽基/沪深300", "券商金融", "港股互联网映射"],
        "mappedSymbols": [
            {"symbol": "600519.SH", "name": "贵州茅台"},
            {"symbol": "300059.SZ", "name": "东方财富"},
        ],
        "transmissionLogic": "富时A50期指与恒生科技直接引导早盘外资与核心宽基风险偏好，离岸人民币汇率升值吸引外资主动加仓流动性资产。",
    },
    {
        "id": "chain_ai_semi",
        "name": "AI算力与硬科技半导体链",
        "drivers": [
            {"symbol": "NVDA", "multiplier": 1.0},
            {"symbol": "TSM", "multiplier": 1.0},
            {"symbol": "AMD", "multiplier": 1.0},
            {"symbol": "AVGO", "multiplier": 1.0},
            {"symbol": "ASML", "multiplier": 1.0},
            {"symbol": "IXIC", "multiplier": 1.0},
        ],
        "mappedSectors": ["CPO光模块", "AI算力芯片", "半导体设备"],
        "mappedSymbols": [
            {"symbol": "300308.SZ", "name": "中际旭创"},
            {"symbol": "688256.SH", "name": "寒武纪"},
            {"symbol": "002371.SZ", "name": "北方华创"},
        ],
        "transmissionLogic": "全球算力总龙头与先进制程供应链走势直接决定A股光模块、算力芯片及半导体设备的估值锚与做多情绪。",
    },
    {
        "id": "chain_ev_robot",
        "name": "特斯拉与智能车/人形机器人链",
        "drivers": [
            {"symbol": "TSLA", "multiplier": 1.0},
            {"symbol": "NQ_FUT", "multiplier": 1.0},
        ],
        "mappedSectors": ["人形机器人", "智能驾驶FSD", "固态/锂电池"],
        "mappedSymbols": [
            {"symbol": "002050.SZ", "name": "三花智控"},
            {"symbol": "601689.SH", "name": "拓普集团"},
            {"symbol": "300750.SZ", "name": "宁德时代"},
        ],
        "transmissionLogic": "特斯拉股价波动与产品量产催化直接映射A股智能驾驶软硬件及人形机器人执行器核心供应链标的。",
    },
    {
        "id": "chain_apple_edge",
        "name": "苹果与AI端侧消费电子链",
        "drivers": [
            {"symbol": "AAPL", "multiplier": 1.0},
            {"symbol": "MSFT", "multiplier": 1.0},
            {"symbol": "INX", "multiplier": 1.0},
        ],
        "mappedSectors": ["果链消费电子", "AI智能眼镜", "AI应用端"],
        "mappedSymbols": [
            {"symbol": "002475.SZ", "name": "立讯精密"},
            {"symbol": "002241.SZ", "name": "歌尔股份"},
        ],
        "transmissionLogic": "苹果硬件出货预期与微软AI终端落地节奏主导A股端侧电子零组件与整机制造商品牌代工溢价。",
    },
    {
        "id": "chain_china_tech",
        "name": "中概互联与内需情绪链",
        "drivers": [
            {"symbol": "HSTECH", "multiplier": 1.0},
            {"symbol": "HK00700", "multiplier": 1.0},
            {"symbol": "BABA", "multiplier": 1.0},
            {"symbol": "PDD", "multiplier": 1.0},
        ],
        "mappedSectors": ["互联网电商", "AI大模型应用", "大消费"],
        "mappedSymbols": [
            {"symbol": "300418.SZ", "name": "昆仑万维"},
            {"symbol": "002555.SZ", "name": "三七互娱"},
        ],
        "transmissionLogic": "美股中概与港股巨头映射内需消费信心与平台经济景气度，联动驱动A股传媒应用与泛消费板块估值修复。",
    },
    {
        "id": "chain_gold_metal",
        "name": "全球避险与贵金属/工业有色链",
        "drivers": [
            {"symbol": "GC", "multiplier": 1.0},
            {"symbol": "SI", "multiplier": 1.0},
            {"symbol": "HG", "multiplier": 1.0},
        ],
        "mappedSectors": ["黄金贵金属", "铜铝工业金属", "小金属资源"],
        "mappedSymbols": [
            {"symbol": "601899.SH", "name": "紫金矿业"},
            {"symbol": "600547.SH", "name": "山东黄金"},
            {"symbol": "603993.SH", "name": "洛阳钼业"},
        ],
        "transmissionLogic": "纽约黄金反映全球地缘避险与通胀预期，伦铜美铜指示全球制造业复苏强度，直接主导A股有色资源品现货与期货溢价。",
    },
    {
        "id": "chain_energy_chem",
        "name": "地缘能源与油气化工航运链",
        "drivers": [
            {"symbol": "CL", "multiplier": 1.0},
            {"symbol": "OIL", "multiplier": 1.0},
            {"symbol": "NG", "multiplier": 1.0},
        ],
        "mappedSectors": ["油气开采", "油运航运", "煤化工/燃气"],
        "mappedSymbols": [
            {"symbol": "600938.SH", "name": "中国海油"},
            {"symbol": "600026.SH", "name": "中远海能"},
        ],
        "transmissionLogic": "国际油气价格受地缘冲突与产油国供给扰动，直接传导至A股三桶油、VLCC远洋油运及中下游基础化工成本端。",
    },
    {
        "id": "chain_agri_food",
        "name": "国际粮价与农业种业链",
        "drivers": [
            {"symbol": "SOYBEAN", "multiplier": 1.0},
            {"symbol": "CORN", "multiplier": 1.0},
        ],
        "mappedSectors": ["种植业与种业", "农林牧渔", "化肥磷化工"],
        "mappedSymbols": [
            {"symbol": "600598.SH", "name": "北大荒"},
            {"symbol": "000998.SZ", "name": "隆平高科"},
        ],
        "transmissionLogic": "CBOT美豆美玉米期货价格反映国际农产品供需平衡表，对国内粮食保供安全预期、种业创新及农化肥周期形成直接映射。",
    },
]


# ----------------------------------------------------------------- 辅助工具函数
def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or isinstance(v, bool):
            return default
        s = str(v).replace("%", "").replace(",", "").strip()
        if not s:
            return default
        f = float(s)
        if f != f or f in (float("inf"), float("-inf")):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _clean_round(x: float, ndigits: int = 2) -> float:
    return round(float(x), ndigits)


# ----------------------------------------------------------------- 解析器：腾讯行情 qt.gtimg.cn
def parse_gtimg_quote(text: str) -> Dict[str, Dict[str, Any]]:
    """
    解析腾讯 qt.gtimg.cn 返回格式：
    v_hkHSI="100~恒生指数~HSI~24481.860~24796.980~...~-315.120~-1.27~...";
    parts[3]: 现价, parts[4]: 昨收, parts[31]: 涨跌额, parts[32]: 涨跌幅(%)
    """
    results: Dict[str, Dict[str, Any]] = {}
    if not text:
        return results

    for item in text.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        try:
            var_part, val_part = item.split("=", 1)
            gtimg_id = var_part.replace("v_", "").strip()
            val_part = val_part.strip().strip('"').strip("'")
            parts = val_part.split("~")
            if len(parts) < 5:
                continue

            price = _to_float(parts[3])
            prev_close = _to_float(parts[4])
            change = _to_float(parts[31]) if len(parts) > 31 else 0.0
            change_pct = _to_float(parts[32]) if len(parts) > 32 else 0.0

            if change_pct == 0.0 and prev_close > 0 and price > 0:
                change = price - prev_close
                change_pct = (change / prev_close) * 100.0

            high = _to_float(parts[33]) if len(parts) > 33 else 0.0
            low = _to_float(parts[34]) if len(parts) > 34 else 0.0

            results[gtimg_id] = {
                "gtimg_id": gtimg_id,
                "name": parts[1] if len(parts) > 1 else "",
                "price": _clean_round(price, 4),
                "prevClose": _clean_round(prev_close, 4),
                "change": _clean_round(change, 4),
                "changePercent": _clean_round(change_pct, 2),
                "high": _clean_round(high, 4) if high else None,
                "low": _clean_round(low, 4) if low else None,
                "source": "gtimg",
            }
        except Exception as e:
            logger.debug("Failed to parse gtimg line: %s, error: %s", item, e)
            continue

    return results


# ----------------------------------------------------------------- 解析器：新浪行情 hq.sinajs.cn
def parse_sina_quote(text: str) -> Dict[str, Dict[str, Any]]:
    """
    解析新浪 hq.sinajs.cn 行情：
    - hf_: 外盘期货, v[0] 现价, v[7] 昨结算(若空或0用 v[2]), 涨跌幅 (price - prev) / prev * 100
    - int_: 全球指数, v[1] 现价, v[2] 涨跌额, v[3] 涨跌幅(去%)
    - gb_: 美股, v[1] 现价, v[2] 涨跌幅(%), v[26] 昨收
    - rt_hk: 港股, v[6] 现价, v[3] 昨收, v[8] 涨跌幅(%)
    - fx_s: 外汇, v[1] 现价, v[3]/v[5] 昨收, 计算或提取准确涨跌幅(%)
    """
    results: Dict[str, Dict[str, Any]] = {}
    if not text:
        return results

    for line in text.split("\n"):
        line = line.strip()
        if not line or "=" not in line:
            continue
        try:
            var_part, val_part = line.split("=", 1)
            sina_id = var_part.replace("var hq_str_", "").strip()
            val_part = val_part.strip().rstrip(";").strip('"').strip("'")
            if not val_part:
                continue
            v = val_part.split(",")
            if len(v) < 2:
                continue

            price = 0.0
            prev_close = 0.0
            change = 0.0
            change_pct = 0.0
            name = ""

            if sina_id.startswith("hf_"):
                # 外盘期货: v[0]=现价, v[2]=买价/开盘, v[4]=最高, v[5]=最低, v[7]=昨结算
                price = _to_float(v[0])
                prev_close = _to_float(v[7])
                if prev_close <= 0.0 and len(v) > 2:
                    prev_close = _to_float(v[2])
                if prev_close > 0:
                    change = price - prev_close
                    change_pct = (change / prev_close) * 100.0
                name = v[13] if len(v) > 13 and v[13] else (v[12] if len(v) > 12 else "")

            elif sina_id.startswith("int_"):
                # 全球指数: v[0]=名称, v[1]=现价, v[2]=涨跌额, v[3]=涨跌幅(%)
                name = v[0]
                price = _to_float(v[1])
                change = _to_float(v[2])
                change_pct = _to_float(v[3].replace("%", ""))
                prev_close = price - change if price else 0.0

            elif sina_id.startswith("gb_"):
                # 美股: v[0]=名称, v[1]=现价, v[2]=涨跌幅(%), v[4]=涨跌额, v[26]=昨收
                name = v[0]
                price = _to_float(v[1])
                change_pct = _to_float(v[2])
                change = _to_float(v[4]) if len(v) > 4 else 0.0
                prev_close = _to_float(v[26]) if len(v) > 26 else (price - change)

            elif sina_id.startswith("rt_hk"):
                # 港股: v[1]=名称, v[3]=昨收, v[6]=现价, v[7]=涨跌额, v[8]=涨跌幅(%)
                name = v[1] if len(v) > 1 else ""
                prev_close = _to_float(v[3]) if len(v) > 3 else 0.0
                price = _to_float(v[6]) if len(v) > 6 else 0.0
                change = _to_float(v[7]) if len(v) > 7 else (price - prev_close)
                change_pct = _to_float(v[8]) if len(v) > 8 else 0.0
                if change_pct == 0.0 and prev_close > 0:
                    change_pct = ((price - prev_close) / prev_close) * 100.0

            elif sina_id.startswith("fx_s") or sina_id.startswith("fx_"):
                # 外汇: v[1]=现价, v[3]=昨收/前结算, v[5]=开盘, v[9]=名称, v[10]=涨跌幅(%), v[11]=涨跌额
                price = _to_float(v[1])
                prev_close = _to_float(v[3])
                if len(v) > 9:
                    name = v[9]
                if len(v) > 10 and v[10]:
                    change_pct = _to_float(v[10])
                if len(v) > 11 and v[11]:
                    change = _to_float(v[11])

                if change_pct == 0.0 and prev_close > 0 and price > 0:
                    change = price - prev_close
                    change_pct = (change / prev_close) * 100.0
                elif prev_close <= 0 and price > 0 and change != 0.0:
                    prev_close = price - change

            else:
                price = _to_float(v[1]) if len(v) > 1 else 0.0

            results[sina_id] = {
                "sina_id": sina_id,
                "name": name,
                "price": _clean_round(price, 4),
                "prevClose": _clean_round(prev_close, 4),
                "change": _clean_round(change, 4),
                "changePercent": _clean_round(change_pct, 2),
                "source": "sina",
            }
        except Exception as e:
            logger.debug("Failed to parse sina line: %s, error: %s", line, e)
            continue

    return results


# ----------------------------------------------------------------- 双源网络抓取与熔断互备
def _http_get(url: str, headers: Optional[Dict[str, str]] = None, timeout: float = 5.0) -> str:
    default_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://finance.sina.com.cn/",
    }
    if headers:
        default_headers.update(headers)
    req = urllib.request.Request(url, headers=default_headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        content = resp.read()
        try:
            return content.decode("gbk")
        except UnicodeDecodeError:
            return content.decode("utf-8", errors="ignore")


def fetch_all_quotes(timeout: float = 5.0) -> Dict[str, Dict[str, Any]]:
    """
    新浪 + 腾讯双源互备抓取全部 28+ 资产实时行情。
    对于有腾讯接口的标的进行并发/合并补全，未覆盖或失败的走新浪主源与备选源互相兜底。
    """
    sina_ids = [a["sina_id"] for a in ASSET_CONFIGS if a.get("sina_id")]
    gtimg_ids = [a["gtimg_id"] for a in ASSET_CONFIGS if a.get("gtimg_id")]

    sina_quotes: Dict[str, Dict[str, Any]] = {}
    gtimg_quotes: Dict[str, Dict[str, Any]] = {}

    # 1. 抓取新浪
    if sina_ids:
        try:
            sina_url = "https://hq.sinajs.cn/list=" + ",".join(sina_ids)
            sina_text = _http_get(sina_url, timeout=timeout)
            sina_quotes = parse_sina_quote(sina_text)
        except Exception as e:
            logger.warning("Failed to fetch sina quotes: %s", e)

    # 2. 抓取腾讯
    if gtimg_ids:
        try:
            gtimg_url = "http://qt.gtimg.cn/q=" + ",".join(gtimg_ids)
            gtimg_text = _http_get(gtimg_url, timeout=timeout)
            gtimg_quotes = parse_gtimg_quote(gtimg_text)
        except Exception as e:
            logger.warning("Failed to fetch gtimg quotes: %s", e)

    # 3. 资产组装与双源互备匹配
    assets: Dict[str, Dict[str, Any]] = {}
    for cfg in ASSET_CONFIGS:
        symbol = cfg["symbol"]
        sina_id = cfg.get("sina_id")
        gtimg_id = cfg.get("gtimg_id")

        q_gt = gtimg_quotes.get(gtimg_id) if gtimg_id else None
        q_sn = sina_quotes.get(sina_id) if sina_id else None

        # 优先使用有效价格的来源
        selected = None
        source_name = "fallback"

        if q_gt and q_gt.get("price", 0) > 0:
            selected = q_gt
            source_name = "gtimg"
        elif q_sn and q_sn.get("price", 0) > 0:
            selected = q_sn
            source_name = "sina"
        elif q_gt:
            selected = q_gt
            source_name = "gtimg"
        elif q_sn:
            selected = q_sn
            source_name = "sina"

        price = selected.get("price", 0.0) if selected else 0.0
        change = selected.get("change", 0.0) if selected else 0.0
        change_pct = selected.get("changePercent", 0.0) if selected else 0.0
        prev_close = selected.get("prevClose", 0.0) if selected else 0.0

        assets[symbol] = {
            "symbol": symbol,
            "name": cfg["name"],
            "category": cfg["category"],
            "price": price,
            "change": change,
            "changePercent": change_pct,
            "prevClose": prev_close,
            "source": source_name,
        }

    return assets


# ----------------------------------------------------------------- 八大跨市场关联传导链计算
def calculate_transmission_chains(assets: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    根据资产行情计算八大传导链的共振强度 resonanceScore ([-100, +100])、
    方向 (BULLISH / BEARISH / NEUTRAL) 和 强度等级 (STRONG / MODERATE / MILD)。
    """
    chains: List[Dict[str, Any]] = []

    for chain_cfg in TRANSMISSION_CHAINS_CONFIG:
        cid = chain_cfg["id"]
        cname = chain_cfg["name"]
        drivers = chain_cfg["drivers"]

        driver_assets = []
        effective_pcts = []

        for d in drivers:
            sym = d["symbol"]
            mult = d.get("multiplier", 1.0)
            ast = assets.get(sym)
            if not ast:
                continue

            pct = ast.get("changePercent", 0.0)
            eff_pct = pct * mult
            effective_pcts.append(eff_pct)

            driver_assets.append({
                "symbol": sym,
                "name": ast["name"],
                "price": ast["price"],
                "changePercent": pct,
                "effectiveChangePercent": _clean_round(eff_pct, 2),
                "multiplier": mult,
            })

        if not effective_pcts:
            avg_pct = 0.0
            resonance_score = 0.0
            direction = "NEUTRAL"
            intensity = "MILD"
        else:
            avg_pct = sum(effective_pcts) / len(effective_pcts)

            # 一致性共振加权：若同向驱动资产占比高，增强共振分
            if abs(avg_pct) > 1e-4:
                same_sign = sum(1 for p in effective_pcts if (p > 0 and avg_pct > 0) or (p < 0 and avg_pct < 0))
                agreement_ratio = same_sign / len(effective_pcts)
            else:
                agreement_ratio = 0.5

            # 缩放因子：通常外盘平均涨跌 1.5%~2.5% 即代表强烈共振 (对应 35~60+ 分)
            raw_score = avg_pct * 20.0 * (0.8 + 0.4 * agreement_ratio)
            resonance_score = _clean_round(max(-100.0, min(100.0, raw_score)), 1)

            if resonance_score >= 15.0:
                direction = "BULLISH"
            elif resonance_score <= -15.0:
                direction = "BEARISH"
            else:
                direction = "NEUTRAL"

            abs_score = abs(resonance_score)
            if abs_score >= 50.0:
                intensity = "STRONG"
            elif abs_score >= 25.0:
                intensity = "MODERATE"
            else:
                intensity = "MILD"

        chains.append({
            "id": cid,
            "name": cname,
            "resonanceScore": resonance_score,
            "direction": direction,
            "intensity": intensity,
            "avgChangePercent": _clean_round(avg_pct, 2),
            "driverSymbols": [d["symbol"] for d in drivers],
            "driverAssets": driver_assets,
            "mappedSectors": chain_cfg["mappedSectors"],
            "mappedSymbols": chain_cfg["mappedSymbols"],
            "transmissionLogic": chain_cfg["transmissionLogic"],
        })

    # 按 abs(resonanceScore) 降序排列
    chains.sort(key=lambda x: abs(x["resonanceScore"]), reverse=True)
    return chains


# ----------------------------------------------------------------- 新浪 7×24 全球财经快讯抓取与打标
_MACRO_KWS = ["美联储", "降息", "降准", "利率", "CPI", "通胀", "非农", "GDP", "财政", "国债", "央行", "汇率", "货币政策", "鲍威尔", "欧洲央行", "宏观"]
_TECH_KWS = ["人工智能", "AI", "芯片", "半导体", "英伟达", "算力", "机器人", "自动驾驶", "特斯拉", "苹果", "大模型", "CPO", "光模块", "华为", "消费电子"]
_COMMODITY_KWS = ["原油", "黄金", "白银", "美铜", "铜", "天然气", "大豆", "玉米", "农产品", "贵金属", "有色", "欧佩克", "OPEC", "桶", "汇率", "离岸人民币"]
_A_SHARE_KWS = ["A股", "证监会", "交易所", "沪深", "上证", "深证", "创业板", "科创板", "涨停", "跌停", "增持", "回购", "国常会", "发改委", "工信部", "北向资金"]

_BULL_KWS = ["上涨", "涨超", "走强", "大涨", "突破", "增长", "超预期", "降息", "提振", "利好", "增加", "创历史新高", "扩产", "签约", "增持", "扭亏"]
_BEAR_KWS = ["下跌", "跌超", "走弱", "暴跌", "承压", "减少", "不及预期", "利空", "预亏", "减持", "处罚", "监管", "降级", "衰退", "下滑", "风险"]
_HIGH_IMPORTANCE_KWS = ["重磅", "突发", "历史新高", "降息", "紧急", "史诗", "暴跌", "暴涨", "重大", "正式公布", "决议", "关税", "制裁"]


def _tag_news(title: str, summary: str) -> Tuple[str, str, str]:
    """返回 (category, polarity, importance)"""
    text = f"{title} {summary}"

    # Category
    score_macro = sum(1 for k in _MACRO_KWS if k in text)
    score_tech = sum(1 for k in _TECH_KWS if k in text)
    score_comm = sum(1 for k in _COMMODITY_KWS if k in text)
    score_ashare = sum(1 for k in _A_SHARE_KWS if k in text)

    scores = [
        ("TECH_INDUSTRY", score_tech),
        ("A_SHARE_POLICY", score_ashare),
        ("COMMODITY_FX", score_comm),
        ("GLOBAL_MACRO", score_macro),
    ]
    scores.sort(key=lambda x: x[1], reverse=True)
    category = scores[0][0] if scores[0][1] > 0 else "GLOBAL_MACRO"

    # Polarity
    bull_count = sum(1 for k in _BULL_KWS if k in text)
    bear_count = sum(1 for k in _BEAR_KWS if k in text)
    if bull_count > bear_count:
        polarity = "BULLISH"
    elif bear_count > bull_count:
        polarity = "BEARISH"
    else:
        polarity = "NEUTRAL"

    # Importance
    if any(k in text for k in _HIGH_IMPORTANCE_KWS) or (title.startswith("【") and any(k in title for k in _HIGH_IMPORTANCE_KWS + ["宣布", "发布", "通过"])):
        importance = "HIGH"
    else:
        importance = "NORMAL"

    return category, polarity, importance


def fetch_global_live_news(limit: int = 15) -> List[Dict[str, Any]]:
    """
    抓取新浪 7×24 全球财经快讯，自动清洗与智能打标。
    若网络超时，平滑回退，绝不抛出未捕获异常。
    """
    url = "https://zhibo.sina.com.cn/api/zhibo/feed?page=1&page_size=20&zhibo_id=152&tag_id=0&dire=f&dpc=1"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://finance.sina.com.cn/",
    }

    raw_items = []
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            raw_items = data.get("result", {}).get("data", {}).get("feed", {}).get("list", [])
    except Exception as e:
        logger.warning("Failed to fetch sina live news: %s, attempting fallback...", e)
        # 回退至 news_events 快讯
        try:
            import news_events as ne
            fallback_items = ne.fetch_ths_fast() if hasattr(ne, "fetch_ths_fast") else []
            for it in fallback_items[:limit]:
                cat, pol, imp = _tag_news(it.get("title", ""), it.get("summary", ""))
                raw_items.append({
                    "id": str(hash(it.get("title", ""))),
                    "create_time": it.get("time", ""),
                    "rich_text": it.get("summary") or it.get("title") or "",
                    "docurl": it.get("url", ""),
                })
        except Exception:
            raw_items = []

    out: List[Dict[str, Any]] = []
    for item in raw_items[:limit]:
        try:
            body = re.sub(r"<[^>]+>", "", item.get("rich_text") or "")
            body = re.sub(r"\s+", " ", body).strip()
            if not body:
                continue

            # 提取标题
            m = re.match(r"^【(.*?)】\s*(.*)$", body)
            if m:
                title = m.group(1).strip()
                summary = m.group(2).strip() or body
            else:
                first = re.split(r"[。！？!?；;]", body)[0] or body
                title = first[:45].strip()
                summary = body

            category, polarity, importance = _tag_news(title, summary)

            out.append({
                "id": str(item.get("id") or abs(hash(title))),
                "time": str(item.get("create_time") or "")[:19],
                "title": title,
                "summary": summary,
                "category": category,
                "polarity": polarity,
                "importance": importance,
                "url": item.get("docurl") or "",
            })
        except Exception as e:
            logger.debug("Error processing live news item: %s", e)
            continue

    return out


# ----------------------------------------------------------------- 主入口：全球全资产雷达
def get_global_market_radar() -> Dict[str, Any]:
    """
    全球全资产监控主入口函数：
    双源行情 + 八大跨市场传导链 + 7×24 快讯 + 宏观偏好定调。
    """
    now_ms = int(time.time() * 1000)

    # 1. 抓取行情与计算传导链
    assets_map = fetch_all_quotes()
    assets_list = list(assets_map.values())
    chains = calculate_transmission_chains(assets_map)

    # 2. 抓取 7×24 全球快讯
    live_news = fetch_global_live_news(limit=15)

    # 3. 统计风险偏好与核心锚定资产
    a50 = assets_map.get("CHA50CFD", {})
    usdcnh = assets_map.get("USDCNH", {})
    a50_pct = a50.get("changePercent", 0.0)
    usdcnh_price = usdcnh.get("price", 0.0)
    usdcnh_pct = usdcnh.get("changePercent", 0.0)

    # 纳指期货 / 标普 / 恒指
    nq = assets_map.get("NQ_FUT", {})
    inx = assets_map.get("INX", {})
    hsi = assets_map.get("HSI", {})
    gold = assets_map.get("GC", {})

    eq_pcts = [x.get("changePercent", 0.0) for x in (a50, nq, inx, hsi) if x.get("changePercent") is not None]
    avg_eq = sum(eq_pcts) / len(eq_pcts) if eq_pcts else 0.0

    gold_pct = gold.get("changePercent", 0.0)

    if avg_eq >= 0.35 and a50_pct >= 0.0:
        global_risk_appetite = "RISK_ON"
        risk_appetite_label = "全球风险偏好升温"
    elif avg_eq <= -0.35 or (gold_pct > 1.0 and avg_eq < 0.0):
        global_risk_appetite = "RISK_OFF"
        risk_appetite_label = "全球避险情绪升温"
    else:
        global_risk_appetite = "MIXED"
        risk_appetite_label = "全球资产分化震荡"

    bullish_chains = [c for c in chains if c["resonanceScore"] > 0]
    bearish_chains = [c for c in chains if c["resonanceScore"] < 0]

    top_bullish_chain = bullish_chains[0] if bullish_chains else None
    top_bearish_chain = bearish_chains[0] if bearish_chains else None

    # 分组资产
    groups: Dict[str, List[Dict[str, Any]]] = {
        "ASIA_CORE": [],
        "US_EU_INDICES": [],
        "TECH_GIANTS": [],
        "COMMODITIES": [],
        "FOREX": [],
    }
    for ast in assets_list:
        cat = ast.get("category", "")
        if cat in groups:
            groups[cat].append(ast)

    return {
        "status": "ok",
        "updatedAt": now_ms,
        "summary": {
            "globalRiskAppetite": global_risk_appetite,
            "riskAppetiteLabel": risk_appetite_label,
            "a50ChangePercent": _clean_round(a50_pct, 2),
            "usdcnhPrice": _clean_round(usdcnh_price, 4),
            "usdcnhChangePercent": _clean_round(usdcnh_pct, 2),
            "topBullishChain": top_bullish_chain,
            "topBearishChain": top_bearish_chain,
        },
        "assets": assets_list,
        "groups": groups,
        "transmissionChains": chains,
        "liveNews": live_news,
    }
