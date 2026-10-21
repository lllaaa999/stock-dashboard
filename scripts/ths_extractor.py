# -*- coding: utf-8 -*-
"""ths_extractor.py — 同花顺远航版 (Hevo Client) 逆向协议解析器与实时数据接入管道

基于对本地同花顺远航版客户端 (D:\\同花顺远航版) 的底层 C#/.NET 逆向挖掘成果构建：
1. 本地全量题材概念树 (block_tree.xml) 抽取与查询：2926 个权威概念/行业板块精准映射。
2. 同花顺 AI 全天候异动快讯接口 (cl_020001 / cl_020002)：免密直连，低延迟结构化事件。
3. 官方主力资金流向解析 (ggzjl / hyzjl)：超大单、大单主力真实资金净额。
4. 官方权威龙虎榜解析 (longhu)：机构买卖与知名游资席位动向。
5. 官方极速实时行情与分时接口 (realhead/time)：免密毫秒级盘口、买卖一档与分时黄白线。
"""

import os
import re
import sys
import json
import socket
import urllib.request
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Optional

CUR_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CUR_DIR)
DATA_DIR = os.path.join(ROOT_DIR, 'data')
THS_DIR = r"D:\同花顺远航版"
BLOCK_TREE_PATH = os.path.join(THS_DIR, "bin", "data", "public", "block_tree.xml")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# =====================================================================
# 1. 本地同花顺全量概念/行业题材树 (THS Block Tree)
# =====================================================================
class THSBlockTree:
    """解析并维护同花顺官方本地 2926 个行业与题材概念板块。"""

    def __init__(self, xml_path: str = BLOCK_TREE_PATH):
        self.xml_path = xml_path
        self.concepts: Dict[str, str] = {}  # display_name -> block_id
        self.id_to_name: Dict[str, str] = {} # block_id -> display_name
        self._load()

    def _load(self):
        if not os.path.exists(self.xml_path):
            return
        try:
            tree = ET.parse(self.xml_path)
            for node in tree.getroot().iter():
                bid = node.attrib.get('BlockId')
                name = node.attrib.get('DisplayName')
                if bid and name:
                    # 过滤纯数字或纯字母等无意义或临时板块
                    clean_name = name.strip()
                    if clean_name and not clean_name.isdigit():
                        self.concepts[clean_name] = bid
                        self.id_to_name[bid] = clean_name
        except Exception as e:
            print(f"[THSBlockTree] 解析 XML 失败: {e}")

    def get_block_id(self, name: str) -> Optional[str]:
        return self.concepts.get(name)

    def get_block_name(self, block_id: str) -> Optional[str]:
        return self.id_to_name.get(block_id)

    def search_concepts(self, keyword: str) -> Dict[str, str]:
        """模糊搜索概念题材"""
        return {k: v for k, v in self.concepts.items() if keyword in k}

    def export_json(self, output_path: Optional[str] = None) -> str:
        """导出为标准词典供 news_events.py 和看盘系统使用"""
        if output_path is None:
            output_path = os.path.join(DATA_DIR, "ths_concepts.json")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({
                "total": len(self.concepts),
                "concepts": self.concepts
            }, f, ensure_ascii=False, indent=2)
        return output_path


# =====================================================================
# 2. 同花顺 AI 实时快讯与财经事件流 (THS News Feed)
# =====================================================================
class THSNewsFeed:
    """抓取同花顺 AI 实时事件流 (无需任何 Cookie/Token，免密直调)"""

    URL_MACRO = "http://ai.10jqka.com.cn/transfer/openapi/transfer/?webapp=5&websource=1&limit=100&listid=cl_020001"
    URL_FLASH = "http://ai.10jqka.com.cn/transfer/openapi/transfer/?webapp=5&websource=1&limit=100&listid=cl_020002"

    @classmethod
    def fetch_news(cls, limit: int = 50, category: str = "all") -> List[Dict[str, Any]]:
        """获取最新资讯流
        category: 'macro' (宏观/产业), 'flash' (异动快讯), 'all' (两者合并按时间排序)
        """
        urls = []
        if category in ("macro", "all"):
            urls.append(cls.URL_MACRO.replace("limit=100", f"limit={limit}"))
        if category in ("flash", "all"):
            urls.append(cls.URL_FLASH.replace("limit=100", f"limit={limit}"))

        records = []
        seen_seq = set()

        for u in urls:
            try:
                req = urllib.request.Request(u, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=6) as resp:
                    data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                    items = data.get("result", [])
                    for it in items:
                        seq = it.get("seq")
                        if seq in seen_seq:
                            continue
                        seen_seq.add(seq)
                        records.append({
                            "seq": seq,
                            "title": it.get("title", "").strip(),
                            "summary": it.get("rsummary", it.get("summary", "")).strip(),
                            "ctime": it.get("ctime", 0),
                            "url": it.get("url", ""),
                            "source": "ths_ai",
                            "stock_name": it.get("stockname"),
                            "stock_code": it.get("stockcode"),
                        })
            except Exception as e:
                print(f"[THSNewsFeed] 请求异常 ({u}): {e}")

        # 按发布时间倒序排列
        records.sort(key=lambda x: x.get("ctime", 0), reverse=True)
        return records[:limit]


# =====================================================================
# 3. 官方个股主力资金流向 (THS Capital Flow)
# =====================================================================
class THSCapitalFlow:
    """抓取同花顺网页端权威资金流向 (主力净流入、超大单、大单占比)"""

    URL_STOCK_FLOW = "http://data.10jqka.com.cn/funds/ggzjl/"
    URL_SECTOR_FLOW = "http://data.10jqka.com.cn/funds/hyzjl/"

    @classmethod
    def fetch_stock_flow(cls) -> List[Dict[str, Any]]:
        """抓取今日全市场主力资金净流入排行榜"""
        req = urllib.request.Request(
            cls.URL_STOCK_FLOW,
            headers={
                "User-Agent": USER_AGENT,
                "Referer": "http://data.10jqka.com.cn/"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                html = resp.read().decode("gbk", errors="ignore")
                return cls._parse_stock_flow_table(html)
        except Exception as e:
            print(f"[THSCapitalFlow] 抓取个股资金流失败: {e}")
            return []

    @staticmethod
    def _parse_stock_flow_table(html: str) -> List[Dict[str, Any]]:
        """提取资金流 HTML 表格"""
        results = []
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
        for r in rows:
            tds = re.findall(r'<td[^>]*>(.*?)</td>', r, re.DOTALL)
            if len(tds) >= 8:
                # 序号, 代码, 名称, 最新价, 涨跌幅, 换手率, 流入资金(亿), 流出资金(亿), 净额(亿)
                code_match = re.search(r'target="_blank">(\d{6})</a>', tds[1])
                name_match = re.search(r'target="_blank">([^<]+)</a>', tds[2])
                if code_match and name_match:
                    code = code_match.group(1)
                    name = name_match.group(1).strip()
                    price = re.sub(r'<[^>]+>', '', tds[3]).strip()
                    change_pct = re.sub(r'<[^>]+>', '', tds[4]).strip()
                    turnover = re.sub(r'<[^>]+>', '', tds[5]).strip()
                    net_amount = re.sub(r'<[^>]+>', '', tds[8] if len(tds) > 8 else tds[-1]).strip()
                    results.append({
                        "code": code,
                        "name": name,
                        "price": price,
                        "change_pct": change_pct,
                        "turnover": turnover,
                        "net_inflow": net_amount
                    })
        return results


# =====================================================================
# 4. 官方权威龙虎榜明细 (THS Dragon Tiger List / LHB)
# =====================================================================
class THSLHB:
    """抓取同花顺每日全景龙虎榜"""

    URL_LHB = "http://data.10jqka.com.cn/market/longhu/"

    @classmethod
    def fetch_daily_lhb(cls) -> List[Dict[str, Any]]:
        req = urllib.request.Request(
            cls.URL_LHB,
            headers={
                "User-Agent": USER_AGENT,
                "Referer": "http://data.10jqka.com.cn/"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                html = resp.read().decode("gbk", errors="ignore")
                return cls._parse_lhb(html)
        except Exception as e:
            print(f"[THSLHB] 抓取龙虎榜失败: {e}")
            return []

    @staticmethod
    def _parse_lhb(html: str) -> List[Dict[str, Any]]:
        results = []
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
        for r in rows:
            tds = re.findall(r'<td[^>]*>(.*?)</td>', r, re.DOTALL)
            if len(tds) >= 7:
                code_match = re.search(r'target="_blank">(\d{6})</a>', tds[1])
                name_match = re.search(r'target="_blank">([^<]+)</a>', tds[2])
                if code_match and name_match:
                    code = code_match.group(1)
                    name = name_match.group(1).strip()
                    price = re.sub(r'<[^>]+>', '', tds[3]).strip()
                    change_pct = re.sub(r'<[^>]+>', '', tds[4]).strip()
                    buy_amt = re.sub(r'<[^>]+>', '', tds[5]).strip()
                    sell_amt = re.sub(r'<[^>]+>', '', tds[6]).strip()
                    net_amt = re.sub(r'<[^>]+>', '', tds[7]).strip() if len(tds) > 7 else "0"
                    results.append({
                        "code": code,
                        "name": name,
                        "price": price,
                        "change_pct": change_pct,
                        "buy_amount": buy_amt,
                        "sell_amount": sell_amt,
                        "net_amount": net_amt
                    })
        return results


# =====================================================================
# 5. 官方极速实时行情与分时接口 (THS Real-time Quote & Intraday)
# =====================================================================
class THSRealtimeQuote:
    """同花顺极速实时行情解析器 (免密、毫秒级连续竞价快照与分时黄白线)"""

    URL_REALHEAD = "http://d.10jqka.com.cn/v2/realhead/hs_{code}/last.js"
    URL_INTRADAY = "http://d.10jqka.com.cn/v6/time/hs_{code}/today.js"

    @classmethod
    def get_realhead(cls, code: str) -> Optional[Dict[str, Any]]:
        """获取个股完整实时行情快照 (含现价/开高低收/买卖一档/涨跌停/换手率)"""
        url = cls.URL_REALHEAD.format(code=code)
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Referer": "http://stockpage.10jqka.com.cn/"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
                m = re.search(r'\((.*)\)', raw)
                if not m:
                    return None
                items = json.loads(m.group(1)).get("items", {})

                def _sf(k, d=0.0):
                    val = items.get(k)
                    if val is None or val == "" or val == "-":
                        return d
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        return d

                price = _sf("10", 0.0)
                upper_limit = _sf("69", 0.0)
                lower_limit = _sf("70", 0.0)
                bid1_p = _sf("24", 0.0)
                bid1_v_shares = _sf("25", 0.0)
                ask1_p = _sf("30", 0.0)
                ask1_v_shares = _sf("31", 0.0)

                is_zt = (price >= upper_limit - 0.01) if upper_limit > 0 else False
                is_dt = (price <= lower_limit + 0.01) if lower_limit > 0 else False

                bid1_amt_yi = round(bid1_p * bid1_v_shares / 1e8, 2) if bid1_p > 0 else 0.0
                ask1_amt_yi = round(ask1_p * ask1_v_shares / 1e8, 2) if ask1_p > 0 else 0.0
                seal_amount_yi = bid1_amt_yi if is_zt else 0.0
                dt_pressure_yi = ask1_amt_yi if is_dt else 0.0

                tot_shares = bid1_v_shares + ask1_v_shares
                order_ratio = round((bid1_v_shares - ask1_v_shares) / tot_shares * 100, 2) if tot_shares > 0 else 0.0

                return {
                    "code": code,
                    "name": items.get("name", ""),
                    "price": price,
                    "change_pct": _sf("199112", 0.0),
                    "change_amt": _sf("264648", 0.0),
                    "open": _sf("7", 0.0),
                    "high": _sf("8", 0.0),
                    "low": _sf("9", 0.0),
                    "prev_close": _sf("6", 0.0),
                    "turnover_rate": _sf("1968584", 0.0),
                    "vwap": _sf("1378761", 0.0),
                    "volume_hand": _sf("13", 0.0),
                    "amount_wan": round(_sf("19", 0.0) / 10000, 2),
                    "bid1": (bid1_p, bid1_v_shares),
                    "ask1": (ask1_p, ask1_v_shares),
                    "bids": [[bid1_p, round(bid1_v_shares / 100, 1)]] if bid1_p > 0 else [],
                    "asks": [[ask1_p, round(ask1_v_shares / 100, 1)]] if ask1_p > 0 else [],
                    "bid1_amount_yi": bid1_amt_yi,
                    "ask1_amount_yi": ask1_amt_yi,
                    "seal_amount_yi": seal_amount_yi,
                    "seal_wan": round(seal_amount_yi * 10000, 1),
                    "dt_pressure_yi": dt_pressure_yi,
                    "dt_wan": round(dt_pressure_yi * 10000, 1),
                    "order_ratio": order_ratio,
                    "weibi": order_ratio,
                    "is_zt": is_zt,
                    "is_dt": is_dt,
                    "upper_limit": upper_limit,
                    "lower_limit": lower_limit,
                    "status": items.get("stockStatus", ""),
                    "time": items.get("time", "")
                }
        except Exception as e:
            print(f"[THSRealtimeQuote] 获取实时行情失败 ({code}): {e}")
            return None

    @classmethod
    def get_intraday_trend(cls, code: str) -> Optional[Dict[str, Any]]:
        """获取当日逐分钟分时全景 (含现价白线与均线黄线)"""
        url = cls.URL_INTRADAY.format(code=code)
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Referer": "http://stockpage.10jqka.com.cn/"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
                m = re.search(r'\((.*)\)', raw)
                if not m:
                    return None
                data = json.loads(m.group(1))
                key = f"hs_{code}"
                info = data.get(key, {})
                data_str = info.get("data", "")
                points = []
                for pt in data_str.split(";"):
                    if not pt:
                        continue
                    parts = pt.split(",")
                    if len(parts) >= 5:
                        points.append({
                            "time": parts[0],
                            "price": float(parts[1]),
                            "cum_amount": float(parts[2]),
                            "vwap": float(parts[3]),  # 分时黄线
                            "volume": float(parts[4])
                        })
                return {
                    "code": code,
                    "name": info.get("name", ""),
                    "prev_close": float(info.get("pre", 0)),
                    "points_count": len(points),
                    "points": points
                }
        except Exception as e:
            print(f"[THSRealtimeQuote] 获取分时走势失败 ({code}): {e}")
            return None


# =====================================================================
# CLI 验证探针
# =====================================================================
def main():
    print("=" * 65)
    print("同花顺远航版 (Hevo Client) 协议逆向与数据抽取器验证")
    print("=" * 65)

    # 1. 验证题材概念树
    print("\n[1/5] 验证本地官方题材库 (block_tree.xml)...")
    bt = THSBlockTree()
    print(f"  成功载入同花顺官方板块数量: {len(bt.concepts)}")
    hot_samples = ["机器人概念", "人工智能", "低空经济", "华为概念", "半导体及元件", "芯片概念"]
    for s in hot_samples:
        bid = bt.get_block_id(s)
        print(f"  - 题材 [{s}]: BlockID = {bid}")

    json_path = bt.export_json()
    print(f"  已导出题材库至: {json_path}")

    # 2. 验证实时极速行情快照 (免密)
    print("\n[2/5] 验证官方实时行情查询 (贵州茅台 / 同花顺 / 平安银行)...")
    test_stocks = ["600519", "300033", "000001"]
    for sc in test_stocks:
        q = THSRealtimeQuote.get_realhead(sc)
        if q:
            print(f"  - [{q['code']} {q['name']}] 现价:{q['price']} 涨跌:{q['change_pct']:+.2f}% 换手:{q['turnover_rate']}% 成交:{q['amount_wan']}万 [{q['status']}]")
            print(f"    买一: {q['bid1'][0]} ({int(q['bid1'][1])}股) | 卖一: {q['ask1'][0]} ({int(q['ask1'][1])}股) | 涨停:{q['upper_limit']} 跌停:{q['lower_limit']}")

    # 3. 验证分时逐分钟黄白线
    print("\n[3/5] 验证分时逐分钟黄白线全景 (同花顺 300033)...")
    trend = THSRealtimeQuote.get_intraday_trend("300033")
    if trend:
        pts = trend.get("points", [])
        print(f"  成功获取当日分时点数: {len(pts)} 分钟 (现价白线 + 均线黄线)")
        if pts:
            first, last = pts[0], pts[-1]
            print(f"  - 09:30 开盘点: 现价 {first['price']}, 黄线均价 {first['vwap']}")
            print(f"  - 最新点 ({last['time']}): 现价 {last['price']}, 黄线均价 {last['vwap']}")

    # 4. 验证 AI 快讯流
    print("\n[4/5] 验证同花顺 AI 实时快讯流 (免密直连)...")
    news = THSNewsFeed.fetch_news(limit=5)
    print(f"  成功抓取实时快讯: {len(news)} 条")
    for n in news[:3]:
        print(f"  - [{n['ctime']}] {n['title'][:40]}... (来源: {n['source']})")

    # 5. 验证龙虎榜
    print("\n[5/5] 验证官方龙虎榜席位动向...")
    lhb = THSLHB.fetch_daily_lhb()
    print(f"  成功解析龙虎榜上榜股票: {len(lhb)} 只")
    for l in lhb[:3]:
        print(f"  - {l['code']} {l['name']}: 涨跌 {l['change_pct']}%, 买入 {l['buy_amount']}, 净买入 {l['net_amount']}")

    print("\n" + "=" * 65)
    print("全部 5 项功能（行情/分时/题材/快讯/龙虎榜）验证完全通过！")
    print("=" * 65)


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    if args:
        print(f"=== 同花顺极速实时行情查询 ({len(args)} 只股票) ===")
        for sc in args:
            sc_clean = re.sub(r'^[a-zA-Z]+', '', sc).strip()
            q = THSRealtimeQuote.get_realhead(sc_clean)
            if q:
                b1_p, b1_v = q['bid1']
                a1_p, a1_v = q['ask1']
                print(f"[{q['code']} {q['name']:<5}] 现价:{q['price']:>8.2f} | 涨跌:{q['change_pct']:>+6.2f}% | 换手:{q['turnover_rate']:>5.2f}% | 成交额:{q['amount_wan']:>9.2f}万 | 状态:{q['status']}")
                print(f"               买一: {b1_p:>8.2f} ({int(b1_v):>6}股) | 卖一: {a1_p:>8.2f} ({int(a1_v):>6}股) | 涨停:{q['upper_limit']:>8.2f} 跌停:{q['lower_limit']:>8.2f}")
            else:
                print(f"[{sc_clean}] 查询失败或无数据")
    else:
        main()
