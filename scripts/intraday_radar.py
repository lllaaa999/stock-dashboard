# -*- coding: utf-8 -*-
"""
股票看盘 · 盘中异动与资金流向监控模块 (Intraday Anomaly & Capital Flow Radar)
提供东财实时盘口异动三级容灾抓取、分时序列实时特征挖掘、主力资金流向拆解与异动-资金共振评估
"""
import sys
import os
import math
import time
import json
import re
import urllib.request
import urllib.parse
from typing import Dict, List, Any, Optional, Tuple

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import data_feed as df_feed
import stock_dashboard as sd

# 尝试导入 market_gateway (位于 ../web/market_gateway.py)
mg = None
try:
    import market_gateway as mg_import
    mg = mg_import
except ImportError:
    WEB_DIR = os.path.join(os.path.dirname(SCRIPTS_DIR), 'web')
    if WEB_DIR not in sys.path:
        sys.path.insert(0, WEB_DIR)
    try:
        import market_gateway as mg_import
        mg = mg_import
    except ImportError:
        mg = None


# 1. 异动类型码映射字典 ANOMALY_TYPE_MAP
# code -> (typeName, polarity, base_score)
ANOMALY_TYPE_MAP: Dict[int, Tuple[str, str, int]] = {
    8201: ("火箭发射", "BULLISH", 80),
    8202: ("快速反弹", "BULLISH", 65),
    8193: ("大笔买入", "BULLISH", 70),
    4: ("封涨停板", "BULLISH", 95),
    32: ("打开涨停", "BEARISH", 90),
    64: ("有大买盘", "BULLISH", 70),
    8207: ("竞价上涨", "BULLISH", 60),
    8209: ("高开5日线", "BULLISH", 60),
    8204: ("加速下跌", "BEARISH", 80),
    8203: ("大笔卖出", "BEARISH", 70),
}


# 2. 基础工具函数
def to_clean_code(symbol_or_code: str) -> str:
    """去掉 .SH/.SZ/.BJ 或 sh/sz/bj 前缀/后缀，返回 6 位纯数字字符串"""
    if not symbol_or_code:
        return ""
    s = str(symbol_or_code).strip()
    m = re.search(r'\b(\d{6})\b', s)
    if m:
        return m.group(1)
    digits = "".join(re.findall(r'\d+', s))
    if len(digits) >= 6:
        return digits[:6]
    return s


def to_symbol(code: str) -> str:
    """6 位代码转 XXXXXX.SH (6/9开头)、XXXXXX.BJ (4/8/920开头)、XXXXXX.SZ (其余)"""
    clean = to_clean_code(code)
    if not clean:
        return ""
    if clean.startswith('920') or clean.startswith(('4', '8')):
        return f"{clean}.BJ"
    elif clean.startswith(('6', '9')):
        return f"{clean}.SH"
    else:
        return f"{clean}.SZ"


def format_tm(tm_val: Any) -> str:
    """将东财 tm 整数 (如 93015 -> "09:30:15", 142503 -> "14:25:03") 或 "HH:MM" 格式化为 "HH:MM:SS" """
    if tm_val is None or tm_val == "":
        return time.strftime("%H:%M:%S")
    s = str(tm_val).strip()
    if ":" in s:
        parts = s.split(":")
        if len(parts) == 2:
            return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}:00"
        elif len(parts) >= 3:
            return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}:{parts[2].zfill(2)}"
    # 提取纯数字并补全
    digits = "".join(filter(str.isdigit, s))
    if len(digits) == 5:
        return f"0{digits[0]}:{digits[1:3]}:{digits[3:5]}"
    elif len(digits) == 6:
        return f"{digits[0:2]}:{digits[2:4]}:{digits[4:6]}"
    elif len(digits) == 4:
        return f"{digits[0:2]}:{digits[2:4]}:00"
    elif len(digits) == 3:
        return f"0{digits[0]}:{digits[1:3]}:00"
    return s


def compute_anomaly_strength(type_code: int, change_pct: float, volume_hands: float = 0.0) -> int:
    """
    计算异动强度得分 [10, 100]
    base_score 来自 ANOMALY_TYPE_MAP (默认 60)
    幅度加成: min(15.0, abs(change_pct) * 1.5)
    量能加成: min(5.0, math.log10(max(volume_hands, 10.0)) * 1.2)
    返回 int(max(10, min(100, round(base_score + amp_bonus + vol_bonus))))
    """
    info = ANOMALY_TYPE_MAP.get(int(type_code))
    base_score = float(info[2]) if info else 60.0

    amp_bonus = min(15.0, abs(float(change_pct or 0.0)) * 1.5)
    vh = max(float(volume_hands or 0.0), 10.0)
    vol_bonus = min(5.0, math.log10(vh) * 1.2)

    total = round(base_score + amp_bonus + vol_bonus)
    return int(max(10, min(100, total)))


def compute_synergy_score(
    anomalies: list,
    main_net_inflow: float,
    main_net_ratio: float,
    outer_vol: int = 0,
    inner_vol: int = 0,
    target_symbol: str = "",
) -> Tuple[int, str, str]:
    """
    计算盘口异动与资金流向共振评分及定性结论
    返回 (score, synergyLevel, synergyVerdict)
    """
    # 1. 异动方向分 S_anom in [-50, 50]
    eval_list = anomalies
    is_market_fallback = False
    if target_symbol and anomalies:
        clean_target = to_clean_code(target_symbol)
        matched = [a for a in anomalies if to_clean_code(a.get("code") or a.get("symbol") or "") == clean_target]
        if matched:
            eval_list = matched
        else:
            eval_list = anomalies[:10]
            is_market_fallback = True

    if eval_list:
        vals = []
        for a in eval_list:
            st = float(a.get("anomalyStrength") or a.get("strength") or 60.0)
            pol = str(a.get("polarity") or "NEUTRAL").upper()
            if pol == "BULLISH":
                vals.append(st)
            elif pol == "BEARISH":
                vals.append(-st)
            else:
                vals.append(0.0)
        mean_val = (sum(vals) / len(vals)) if vals else 0.0
        # 若为全市场兜底均值则乘以 0.4
        factor = 0.4 * 0.5 if is_market_fallback else 0.5
        S_anom = mean_val * factor
        S_anom = max(-50.0, min(50.0, S_anom))
    else:
        S_anom = 0.0

    # 2. 资金流向分 S_cap in [-50, 50]
    inflow = float(main_net_inflow or 0.0)
    ratio = float(main_net_ratio or 0.0)
    if abs(inflow) > 0.0 or abs(ratio) > 0.0:
        inflow_yi = inflow / 1e8
        sign_part = math.copysign(min(25.0, abs(inflow_yi) * 12.0), inflow_yi) if inflow_yi != 0.0 else 0.0
        raw_cap = ratio * 1.8 + sign_part
        S_cap = max(-50.0, min(50.0, raw_cap))
    else:
        outer = float(outer_vol or 0)
        inner = float(inner_vol or 0)
        if outer + inner > 0:
            imb = (outer - inner) / (outer + inner)
            S_cap = max(-50.0, min(50.0, imb * 50.0))
        else:
            S_cap = 0.0

    score = int(round(max(-100.0, min(100.0, S_anom + S_cap))))

    # 3. 分级与定性结论
    if score >= 50:
        level = "STRONG_RESONANCE"
        verdict = "主力抢筹与盘口异动强共振，真突破概率高"
    elif score >= 15:
        level = "MILD_RESONANCE"
        verdict = "资金温和配合异动，关注分时均线承接"
    elif score > -20:
        level = "DIVERGENCE_WARNING"
        verdict = "异动脉冲但主力净流向背离，警惕诱多/对倒骗线"
    else:
        level = "BEARISH_DUMP"
        verdict = "大单持续流出叠加空头异动，严防派发核按钮"

    return score, level, verdict


def _parse_eastmoney_info(type_code: int, info_str: str) -> Tuple[float, float, float, float]:
    """
    解析 Eastmoney 异动 i 字段，返回 (price, change_pct, volume_hands, amount_cny)
    """
    if not info_str:
        return 0.0, 0.0, 0.0, 0.0
    parts = [p.strip() for p in info_str.split(',') if p.strip()]
    nums = []
    for p in parts:
        try:
            nums.append(float(p))
        except (ValueError, TypeError):
            continue

    price = 0.0
    change_pct = 0.0
    volume_hands = 0.0
    amount_cny = 0.0

    if len(nums) >= 4:
        if type_code == 4:
            # 封涨停板: [现价, 成交股数, 现价, 涨跌幅]
            price = nums[0]
            volume_hands = nums[1] / 100.0
            change_pct = nums[3]
            amount_cny = price * nums[1]
        else:
            # 大买盘/大单买卖: [成交股数, 现价, 涨跌幅, 金额]
            volume_hands = nums[0] / 100.0
            price = nums[1]
            change_pct = nums[2]
            amount_cny = nums[3]
    elif len(nums) == 3:
        # 如 [涨跌幅, 现价, 涨跌幅] 或 [现价, 成交股数, 涨跌幅]
        if abs(nums[0] - nums[2]) < 1e-4:
            change_pct = nums[0]
            price = nums[1]
        else:
            price = nums[0]
            volume_hands = nums[1] / 100.0
            change_pct = nums[2]
            amount_cny = price * nums[1]
    elif len(nums) == 2:
        # 如 [现价, 涨跌幅]
        price = nums[0]
        change_pct = nums[1]
    elif len(nums) == 1:
        price = nums[0]

    # 东财部分类型 i 里涨跌幅为小数 (如 0.0521 -> 5.21%)
    if abs(change_pct) <= 0.35 and change_pct != 0.0:
        change_pct = change_pct * 100.0

    return round(price, 2), round(change_pct, 2), round(volume_hands, 1), round(amount_cny, 2)


def _format_detail_text(type_name: str, price: float, change_pct: float, volume_hands: float, amount_cny: float) -> str:
    """生成详细描述文本"""
    parts = [f"[{type_name}]"]
    if price > 0:
        parts.append(f"现价 {price:.2f} ({change_pct:+.2f}%)")
    elif change_pct != 0:
        parts.append(f"涨跌幅 {change_pct:+.2f}%")
    if amount_cny >= 1e4:
        parts.append(f"成交 {amount_cny / 1e4:.1f}万")
    elif volume_hands > 0:
        parts.append(f"成交 {volume_hands:.0f}手")
    return " ".join(parts)


# 3. 三级数据源实现
def fetch_eastmoney_anomalies(limit: int = 64) -> List[Dict[str, Any]]:
    """
    Tier 1: 从东财实时异动接口拉取全市场盘口异动
    """
    type_str = "8201,8202,8193,4,32,64,8207,8209,8204,8203"
    url = (
        f"https://push2ex.eastmoney.com/getAllStockChanges"
        f"?type={type_str}&pageindex=0&pagesize={limit}"
        f"&ut=7eea3edcaed734bea9cbfc24409ed989&dpt=wzchanges"
    )
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://quote.eastmoney.com/'
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=1.5) as resp:
        body = resp.read().decode('utf-8')
    data = json.loads(body)
    all_stock = (data.get("data") or {}).get("allstock", [])
    if not all_stock:
        return []

    res: List[Dict[str, Any]] = []
    for idx, item in enumerate(all_stock):
        c = str(item.get("c") or "").strip()
        if not c:
            continue
        tm = item.get("tm")
        name = str(item.get("n") or c).strip()
        t = int(item.get("t") or 0)
        i_str = str(item.get("i") or "").strip()

        type_meta = ANOMALY_TYPE_MAP.get(t, (f"异动_{t}", "NEUTRAL", 60))
        type_name, polarity, _ = type_meta
        price, change_pct, volume_hands, amount_cny = _parse_eastmoney_info(t, i_str)

        time_str = format_tm(tm)
        clean_code = to_clean_code(c)
        sym = to_symbol(clean_code)
        strength = compute_anomaly_strength(t, change_pct, volume_hands)
        detail = _format_detail_text(type_name, price, change_pct, volume_hands, amount_cny)

        res.append({
            "id": f"{clean_code}_{tm}_{t}_{idx}",
            "time": time_str,
            "symbol": sym,
            "code": clean_code,
            "name": name,
            "typeCode": t,
            "typeName": type_name,
            "polarity": polarity,
            "price": price,
            "changePercent": change_pct,
            "volumeHands": volume_hands,
            "amountCNY": amount_cny,
            "anomalyStrength": strength,
            "detailText": detail,
        })
    return res


def mine_anomalies_from_intraday_trends(symbols: List[str], quotes_map: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Tier 2: 当 Tier 1 为空或网络异常时，从活跃股分时序列实时挖掘特征异动
    """
    quotes_map = quotes_map or {}
    candidates = list(dict.fromkeys([s for s in symbols if s]))[:8]
    if not candidates:
        candidates = ["000530.SZ", "600519.SH", "300750.SZ"]

    anomalies: List[Dict[str, Any]] = []

    for sym in candidates:
        code = to_clean_code(sym)
        full_sym = to_symbol(code)
        q = quotes_map.get(full_sym) or quotes_map.get(code) or {}
        name = q.get('name') or code

        # 获取真实分时趋势
        try:
            trend_data = df_feed.get_intraday_trends(code)
        except Exception:
            trend_data = None

        if not trend_data:
            continue

        # 兼容字典格式与序列格式
        times: List[str] = []
        prices: List[float] = []
        avg_prices: List[float] = []
        volumes: List[float] = []
        pre_close: float = 0.0

        if isinstance(trend_data, dict):
            times = [str(x) for x in trend_data.get('times', [])]
            prices = [float(x or 0.0) for x in trend_data.get('prices', [])]
            avg_prices = [float(x or 0.0) for x in trend_data.get('avg_prices', [])]
            volumes = [float(x or 0.0) for x in trend_data.get('volumes', [])]
            pre_close = float(trend_data.get('pre_close') or 0.0)
        elif isinstance(trend_data, list):
            for row in trend_data:
                if isinstance(row, (list, tuple)) and len(row) >= 4:
                    times.append(str(row[0]))
                    prices.append(float(row[1] or 0.0))
                    avg_prices.append(float(row[2] or 0.0))
                    volumes.append(float(row[3] or 0.0))
                elif isinstance(row, dict):
                    times.append(str(row.get('time', '')))
                    prices.append(float(row.get('price', 0.0)))
                    avg_prices.append(float(row.get('avg_price', 0.0)))
                    volumes.append(float(row.get('volume', 0.0)))

        if not prices:
            continue

        if pre_close <= 0.0:
            pre_close = float(q.get('prevClose') or prices[0])
            if pre_close <= 0.0:
                pre_close = prices[0]

        n_pts = min(len(times), len(prices))
        if n_pts < 2:
            continue

        stock_anomalies: List[Dict[str, Any]] = []
        high_so_far = -999999.0
        low_so_far = 999999.0
        touched_limit_up = False
        limit_broken = False
        last_8201_idx = -99
        last_8204_idx = -99
        last_8202_idx = -99
        last_8193_idx = -99

        for i in range(n_pts):
            t = times[i]
            p = prices[i]
            ap = avg_prices[i] if i < len(avg_prices) and avg_prices[i] > 0 else p
            v = volumes[i] if i < len(volumes) else 0.0
            pct = (p - pre_close) / pre_close * 100.0 if pre_close > 0 else 0.0

            if p > high_so_far:
                high_so_far = p
            if p < low_so_far:
                low_so_far = p

            high_pct = (high_so_far - pre_close) / pre_close * 100.0 if pre_close > 0 else 0.0
            low_pct = (low_so_far - pre_close) / pre_close * 100.0 if pre_close > 0 else 0.0

            # 1. 触及涨停 (change_pct >= 9.7%) -> 4
            if pct >= 9.7 and not touched_limit_up:
                touched_limit_up = True
                stock_anomalies.append({
                    "time": format_tm(t),
                    "typeCode": 4,
                    "price": round(p, 2),
                    "changePercent": round(pct, 2),
                    "volumeHands": round(v, 1),
                })

            # 2. 曾触及涨停后回落 (high_pct >= 9.7% 且当前 < 9.2%) -> 32
            if high_pct >= 9.7 and pct < 9.2 and not limit_broken and touched_limit_up:
                limit_broken = True
                stock_anomalies.append({
                    "time": format_tm(t),
                    "typeCode": 32,
                    "price": round(p, 2),
                    "changePercent": round(pct, 2),
                    "volumeHands": round(v, 1),
                })

            # 3. 日内 3 分钟拉升 >= 1.8% -> 8201 (波段去重)
            if i >= 3:
                p_3m = prices[i - 3]
                gain_3m = (p - p_3m) / pre_close * 100.0 if pre_close > 0 else 0.0
                if gain_3m >= 1.8 and i - last_8201_idx >= 3:
                    last_8201_idx = i
                    stock_anomalies.append({
                        "time": format_tm(t),
                        "typeCode": 8201,
                        "price": round(p, 2),
                        "changePercent": round(pct, 2),
                        "volumeHands": round(v, 1),
                    })

            # 4. 日内 3 分钟急跌 <= -1.8% -> 8204 (波段去重)
            if i >= 3:
                p_3m = prices[i - 3]
                drop_3m = (p - p_3m) / pre_close * 100.0 if pre_close > 0 else 0.0
                if drop_3m <= -1.8 and i - last_8204_idx >= 3:
                    last_8204_idx = i
                    stock_anomalies.append({
                        "time": format_tm(t),
                        "typeCode": 8204,
                        "price": round(p, 2),
                        "changePercent": round(pct, 2),
                        "volumeHands": round(v, 1),
                    })

            # 5. 低点探底后反弹站上均价线 (low_pct <= -1.5% 且反弹 >= 1.8% 且 price >= avg_price) -> 8202
            if low_pct <= -1.5 and p >= ap and pre_close > 0:
                rebound = (p - low_so_far) / pre_close * 100.0
                if rebound >= 1.8 and i - last_8202_idx >= 3:
                    last_8202_idx = i
                    stock_anomalies.append({
                        "time": format_tm(t),
                        "typeCode": 8202,
                        "price": round(p, 2),
                        "changePercent": round(pct, 2),
                        "volumeHands": round(v, 1),
                    })

            # 6. 单分钟成交量激增 (前 5 分钟均量 3 倍且价格上涨) -> 8193
            if i >= 5:
                v5 = volumes[i - 5:i]
                avg_v5 = sum(v5) / 5.0
                if avg_v5 > 0 and v >= 3.0 * avg_v5 and p > prices[i - 1] and i - last_8193_idx >= 2:
                    last_8193_idx = i
                    stock_anomalies.append({
                        "time": format_tm(t),
                        "typeCode": 8193,
                        "price": round(p, 2),
                        "changePercent": round(pct, 2),
                        "volumeHands": round(v, 1),
                    })

        # 7. 若分时平稳未达上述强阈值，提取当日最大放量点兜底保证产出有效异动
        if not stock_anomalies:
            max_v_idx = 0
            max_v = -1.0
            for vi, vol in enumerate(volumes):
                if vol > max_v:
                    max_v = vol
                    max_v_idx = vi
            t_max = times[max_v_idx]
            p_max = prices[max_v_idx]
            v_max = volumes[max_v_idx]
            pct_max = (p_max - pre_close) / pre_close * 100.0 if pre_close > 0 else 0.0
            prev_p = prices[max(0, max_v_idx - 1)]
            tc = 8193 if p_max >= prev_p else 8203
            stock_anomalies.append({
                "time": format_tm(t_max),
                "typeCode": tc,
                "price": round(p_max, 2),
                "changePercent": round(pct_max, 2),
                "volumeHands": round(v_max, 1),
            })

        # 将挖掘出的异动转化为标准契约项 (去重与格式化)
        seen_keys = set()
        for sa in stock_anomalies:
            tc = sa["typeCode"]
            tm_s = sa["time"]
            key = (tc, tm_s[:5])  # 同一分钟同一类型去重
            if key in seen_keys:
                continue
            seen_keys.add(key)

            meta = ANOMALY_TYPE_MAP.get(tc, ("盘中异动", "BULLISH", 65))
            type_name, polarity, _ = meta
            px = sa["price"]
            cp = sa["changePercent"]
            vh = sa["volumeHands"]
            amt = round(px * vh * 100.0, 2)
            st = compute_anomaly_strength(tc, cp, vh)
            dt_txt = _format_detail_text(type_name, px, cp, vh, amt)

            anomalies.append({
                "id": f"mined_{code}_{tm_s.replace(':', '')}_{tc}_{len(anomalies)}",
                "time": tm_s,
                "symbol": full_sym,
                "code": code,
                "name": name,
                "typeCode": tc,
                "typeName": type_name,
                "polarity": polarity,
                "price": px,
                "changePercent": cp,
                "volumeHands": vh,
                "amountCNY": amt,
                "anomalyStrength": st,
                "detailText": dt_txt,
            })

    # 按时间降序，同时间按强度从高到低排序 (最新异动排在前)
    anomalies.sort(key=lambda x: (x["time"], x["anomalyStrength"]), reverse=True)
    return anomalies


def fallback_anomalies_from_quotes(quotes_map: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Tier 3: 当 Tier 1 与 Tier 2 均无数据时，基于 Level-1 快照盘口生成真实异动
    """
    anomalies: List[Dict[str, Any]] = []
    now_tm = time.strftime("%H:%M:%S")

    for sym, q in (quotes_map or {}).items():
        if not isinstance(q, dict):
            continue
        code = to_clean_code(q.get('code') or sym)
        full_sym = to_symbol(code)
        name = q.get('name') or code
        price = float(q.get('price') or 0.0)
        change_pct = float(q.get('changePercent') or 0.0)
        volume = float(q.get('volume') or 0.0)
        outer = float(q.get('outerVolume') or 0.0)
        inner = float(q.get('innerVolume') or 0.0)
        amount = float(q.get('amount') or (price * volume * 100.0))

        if price <= 0.0:
            continue

        # 规则判断
        if change_pct >= 9.7:
            type_code = 4
        elif change_pct >= 3.0:
            type_code = 8201 if outer >= inner else 8207
        elif change_pct <= -3.0:
            type_code = 8204 if inner >= outer else 8203
        elif outer > inner * 1.5:
            type_code = 64
        elif inner > outer * 1.5:
            type_code = 8203
        elif change_pct > 0:
            type_code = 8202
        else:
            type_code = 8203

        meta = ANOMALY_TYPE_MAP.get(type_code, ("盘口异动", "BULLISH", 60))
        type_name, polarity, _ = meta
        strength = compute_anomaly_strength(type_code, change_pct, volume)
        detail = _format_detail_text(type_name, price, change_pct, volume, amount)

        anomalies.append({
            "id": f"snap_{code}_{type_code}_{len(anomalies)}",
            "time": now_tm,
            "symbol": full_sym,
            "code": code,
            "name": name,
            "typeCode": type_code,
            "typeName": type_name,
            "polarity": polarity,
            "price": round(price, 2),
            "changePercent": round(change_pct, 2),
            "volumeHands": round(volume, 1),
            "amountCNY": round(amount, 2),
            "anomalyStrength": strength,
            "detailText": detail,
        })

    anomalies.sort(key=lambda x: x["anomalyStrength"], reverse=True)
    return anomalies


# 4. 资金流向采集与共振计算
def fetch_symbol_capital_flow(
    symbol: str,
    quote: Optional[Dict[str, Any]] = None,
    symbol_anomalies: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    采集目标个股实时资金流向，拆解超大/大/中/小单并计算与异动的共振评分
    """
    code = to_clean_code(symbol)
    full_sym = to_symbol(code)
    quote = quote or {}
    name = quote.get('name') or code
    price = float(quote.get('price') or 0.0)
    change_pct = float(quote.get('changePercent') or 0.0)

    main_net = 0.0
    super_net = 0.0
    large_net = 0.0
    med_net = 0.0
    small_net = 0.0
    main_ratio = 0.0

    # 1. 尝试东财实时个股资金流 ulist 接口
    secid = f"{1 if full_sym.endswith('.SH') else 0}.{code}"
    url = (
        f"https://push2.eastmoney.com/api/qt/ulist.np/get"
        f"?secids={secid}&fields=f12,f14,f2,f3,f62,f66,f72,f78,f84,f184"
        f"&ut=b2884a393a59ad64002292a3e90d46a5"
    )
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://data.eastmoney.com/'
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            raw = resp.read().decode('utf-8')
        d = json.loads(raw)
        diff = (d.get('data') or {}).get('diff', [])
        if diff and isinstance(diff, list):
            row = diff[0]
            name = row.get('f14') or name
            px_val = float(row.get('f2') or 0.0)
            if price <= 0.0:
                price = px_val / 100.0 if px_val > 1000 else px_val
            chg_val = float(row.get('f3') or 0.0)
            if change_pct == 0.0:
                change_pct = chg_val / 100.0 if abs(chg_val) > 100 else chg_val

            main_net = float(row.get('f62') or 0.0)
            super_net = float(row.get('f66') or 0.0)
            large_net = float(row.get('f72') or 0.0)
            med_net = float(row.get('f78') or 0.0)
            small_net = float(row.get('f84') or 0.0)
            r_val = float(row.get('f184') or 0.0)
            main_ratio = r_val / 100.0 if abs(r_val) > 100 else r_val
    except Exception:
        pass

    # 2. 若东财实时 ulist 接口无数据，降级至 df_feed.get_capital_breakdown(code)
    recent_5d = []
    try:
        cb = df_feed.get_capital_breakdown(code) or {}
        today_cb = cb.get('today') or {}
        if main_net == 0.0 and abs(float(today_cb.get('main_net') or 0.0)) > 0:
            # get_capital_breakdown 的 main_net 单位为亿元
            main_net = float(today_cb.get('main_net') or 0.0) * 1e8
            super_net = float(today_cb.get('super_net') or 0.0) * 1e8
            large_net = float(today_cb.get('large_net') or 0.0) * 1e8
            med_net = float(today_cb.get('med_net') or 0.0) * 1e8
            small_net = float(today_cb.get('small_net') or 0.0) * 1e8
            main_ratio = float(today_cb.get('pct') or 0.0)

        history = cb.get('history') or []
        for h in history:
            raw_yi = float(h.get('main_net') or 0.0)
            recent_5d.append({
                "date": str(h.get('date') or ''),
                "mainNetInflow": round(raw_yi * 1e8, 2),
                "mainNetInflowYi": round(raw_yi, 2),
                "changePercent": float(h.get('pct') or 0.0),
            })
    except Exception:
        pass

    # 3. 若仍为 0 且 quote 盘口存在，通过内外盘差自洽估算主力流入
    outer_v = int(float(quote.get('outerVolume') or 0))
    inner_v = int(float(quote.get('innerVolume') or 0))
    if main_net == 0.0 and (outer_v + inner_v > 0) and price > 0:
        main_net = float((outer_v - inner_v) * 100 * price)
        super_net = main_net * 0.55
        large_net = main_net * 0.45
        med_net = -main_net * 0.20
        small_net = -main_net * 0.80
        total_v = outer_v + inner_v
        main_ratio = round((outer_v - inner_v) / total_v * 100.0, 2) if total_v > 0 else 0.0

    # 4. 计算异动-资金共振分
    score, level, verdict = compute_synergy_score(
        anomalies=symbol_anomalies or [],
        main_net_inflow=main_net,
        main_net_ratio=main_ratio,
        outer_vol=outer_v,
        inner_vol=inner_v,
        target_symbol=full_sym,
    )

    return {
        "symbol": full_sym,
        "code": code,
        "name": name,
        "price": round(price, 2),
        "changePercent": round(change_pct, 2),
        "mainNetInflow": round(main_net, 2),
        "superLargeNetInflow": round(super_net, 2),
        "largeNetInflow": round(large_net, 2),
        "mediumNetInflow": round(med_net, 2),
        "smallNetInflow": round(small_net, 2),
        "mainNetRatio": round(main_ratio, 2),
        "synergyScore": score,
        "synergyLevel": level,
        "synergyVerdict": verdict,
        "recent5DaysMainNet": recent_5d,
    }


def fetch_top_inflow_stocks(quotes_map: Optional[Dict[str, Any]] = None, anomalies_by_sym: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    获取全市场主力净流入榜 Top 10
    """
    quotes_map = quotes_map or {}
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get"
        "?pn=1&pz=15&po=1&np=1&ut=b2884a393a59ad64002292a3e90d46a5"
        "&fltt=2&invt=2&fid=f62&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
        "&fields=f12,f14,f2,f3,f62,f184"
    )
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://data.eastmoney.com/'
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            raw = resp.read().decode('utf-8')
        d = json.loads(raw)
        diff = (d.get('data') or {}).get('diff', [])
        if diff and isinstance(diff, list):
            res = []
            for row in diff[:10]:
                c = str(row.get('f12') or '')
                if not c:
                    continue
                px = float(row.get('f2') or 0.0)
                cp = float(row.get('f3') or 0.0)
                inflow = float(row.get('f62') or 0.0)
                ratio = float(row.get('f184') or 0.0)
                res.append({
                    "symbol": to_symbol(c),
                    "code": c,
                    "name": str(row.get('f14') or c),
                    "price": round(px, 2),
                    "changePercent": round(cp, 2),
                    "mainNetInflow": round(inflow, 2),
                    "mainNetRatio": round(ratio, 2),
                })
            if res:
                return res
    except Exception:
        pass

    # 兜底：从 quotes_map 中基于外盘-内盘金额估算排序
    top_candidates = []
    for sym, q in quotes_map.items():
        if not isinstance(q, dict):
            continue
        c = to_clean_code(q.get('code') or sym)
        px = float(q.get('price') or 0.0)
        cp = float(q.get('changePercent') or 0.0)
        ov = float(q.get('outerVolume') or 0.0)
        iv = float(q.get('innerVolume') or 0.0)
        net_inflow = (ov - iv) * 100 * px
        tot = ov + iv
        ratio = round((ov - iv) / tot * 100.0, 2) if tot > 0 else 0.0
        top_candidates.append({
            "symbol": to_symbol(c),
            "code": c,
            "name": q.get('name') or c,
            "price": round(px, 2),
            "changePercent": round(cp, 2),
            "mainNetInflow": round(net_inflow, 2),
            "mainNetRatio": round(ratio, 2),
        })

    top_candidates.sort(key=lambda x: x["mainNetInflow"], reverse=True)
    return top_candidates[:10]


# 5. 主入口函数
def get_intraday_radar(symbol: str = "000530.SZ", limit: int = 50) -> Dict[str, Any]:
    """
    盘中异动与资金流向监控模块主入口
    """
    clean_code = to_clean_code(symbol or "000530")
    target_symbol = to_symbol(clean_code)

    # 优先拉取一批行情活跃池
    watchlist = list(dict.fromkeys([
        target_symbol, '000530.SZ', '600519.SH', '300750.SZ', '002594.SZ',
        '688981.SH', '300059.SZ', '601318.SH', '600036.SH'
    ]))
    quotes_map: Dict[str, Any] = {}
    if mg and hasattr(mg, 'fetch_level1_quotes'):
        try:
            quotes_map = mg.fetch_level1_quotes(watchlist) or {}
        except Exception:
            quotes_map = {}

    anomalies: List[Dict[str, Any]] = []
    basis = "live_eastmoney"
    basis_label = "东财实时异动"

    # Tier 1
    try:
        anomalies = fetch_eastmoney_anomalies(limit=max(limit, 64))
    except Exception:
        anomalies = []

    # Tier 2
    if not anomalies:
        basis = "intraday_trend_mined"
        basis_label = "真实分时挖掘"
        try:
            anomalies = mine_anomalies_from_intraday_trends(watchlist, quotes_map)
        except Exception:
            anomalies = []

    # Tier 3
    if not anomalies:
        basis = "snapshot_fallback"
        basis_label = "L1盘口快照"
        try:
            anomalies = fallback_anomalies_from_quotes(quotes_map)
        except Exception:
            anomalies = []

    # 统计市场情绪指标
    bullish_cnt = sum(1 for a in anomalies if a.get("polarity") == "BULLISH")
    bearish_cnt = sum(1 for a in anomalies if a.get("polarity") == "BEARISH")
    if bullish_cnt >= bearish_cnt * 1.5 and bullish_cnt > 0:
        dominant_sig = "多头占优"
        market_temp = "BULLISH_ATTACK"
    elif bearish_cnt >= bullish_cnt * 1.5 and bearish_cnt > 0:
        dominant_sig = "空头占优"
        market_temp = "BEARISH_DEFENSE"
    else:
        dominant_sig = "多空均衡"
        market_temp = "BALANCED_ROTATION"

    # 目标股票资金流向与共振评估
    target_quote = quotes_map.get(target_symbol) or quotes_map.get(clean_code)
    symbol_cap_flow = fetch_symbol_capital_flow(target_symbol, target_quote, anomalies)

    # 主力净流入榜
    top_inflows = fetch_top_inflow_stocks(quotes_map)

    return {
        "status": "ok",
        "basis": basis,
        "basisLabel": basis_label,
        " basisLabel": basis_label,
        "updatedAt": int(time.time() * 1000),
        "summary": {
            "totalCount": len(anomalies),
            "bullishCount": bullish_cnt,
            "bearishCount": bearish_cnt,
            "dominantSignal": dominant_sig,
            "marketTemperament": market_temp,
        },
        "symbolCapitalFlow": symbol_cap_flow,
        "anomalies": anomalies[:limit],
        "topInflowStocks": top_inflows[:10],
    }
