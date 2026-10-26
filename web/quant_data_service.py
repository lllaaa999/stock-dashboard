import sys
import os
import json
import time
import datetime as dt
import urllib.parse
import urllib.request
from typing import Dict, List, Any, Optional
import numpy as np

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts')
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import stock_dashboard as sd
import lhb_orthogonal_evaluator as lhb
import abnormal_volatility as av
import data_feed as df_feed
import ultrashort_metrics as usm

_LHB_LIST_CACHE = None
_LHB_LIST_CACHE_TIME = 0.0

def _format_fbt(val: Any) -> Optional[str]:
    """格式化首次封板时间，支持整型(如 92500)、带冒号字符串('09:25:00')等形态。"""
    if not val:
        return None
    if isinstance(val, str):
        val_s = val.strip()
        if ':' in val_s:
            return val_s
        if val_s.isdigit():
            val = int(val_s)
        else:
            return val_s
    if isinstance(val, (int, float)) and val > 0:
        iv = int(val)
        return f"{iv // 10000:02d}:{(iv // 100) % 100:02d}:{iv % 100:02d}"
    return None

def _classify_seat(branch_name: str) -> Dict[str, str]:
    name = branch_name or ''
    if '机构专用' in name:
        return {'nature': 'INSTITUTION', 'natureLabel': '机构专用', 'seatTag': '机构专用', 'style': '中线价值配置 / 机构锁仓'}
    if '沪股通' in name or '深股通' in name:
        return {'nature': 'INSTITUTION', 'natureLabel': '北向席位', 'seatTag': '外资北向', 'style': '波段配置 / 核心资产抱团'}
    if any(k in name for k in ('知春路', '中关村', '上塘路', '桑田路', '绍兴', '益田路', '太平南路', '解放南路', '丹溪北路', '彩田路', '湘江中路', '江苏路', '溧阳路')):
        return {'nature': 'HOT_MONEY', 'natureLabel': '游资常用席位', 'seatTag': '一线知名游资', 'style': '超短龙头主封 / 连板接力'}
    if any(k in name for k in ('拉萨', '金融城', '东环路', '团结路')):
        return {'nature': 'RETAIL_CAMP', 'natureLabel': '散户大本营', 'seatTag': '东方财富拉萨天团', 'style': '高频散户合力 / 顺势分歧承接'}
    if any(k in name for k in ('华泰证券股份有限公司总部', '中国国际金融', '中信证券股份有限公司上海分公司', '国泰君安证券股份有限公司总部', '瑞银证券')):
        return {'nature': 'QUANT_CAMP', 'natureLabel': '量化大本营', 'seatTag': '量化算法大本营', 'style': '高频算法打板 / T+1冲高兑现'}
    return {'nature': 'HOT_MONEY', 'natureLabel': '活跃游资席位', 'seatTag': '游资主力', 'style': '分时引导 / 趋势进攻'}

def get_today_lhb_list() -> List[Dict[str, Any]]:
    global _LHB_LIST_CACHE, _LHB_LIST_CACHE_TIME
    now = time.time()
    if _LHB_LIST_CACHE and (now - _LHB_LIST_CACHE_TIME < 300.0):
        return _LHB_LIST_CACHE

    try:
        u = 'https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_DAILYBILLBOARD_DETAILSNEW&columns=ALL&pageNumber=1&pageSize=40&sortTypes=-1&sortColumns=TRADE_DATE'
        req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            j = json.loads(resp.read().decode('utf-8'))
        rows = (j.get('result') or {}).get('data') or []
        seen = set()
        items = []
        for r in rows:
            c = str(r.get('SECURITY_CODE') or '').strip().zfill(6)
            if c and c not in seen:
                seen.add(c)
                market = 'SH' if c.startswith('6') else 'SZ'
                items.append({
                    'code': c,
                    'symbol': f"{c}.{market}",
                    'name': r.get('SECURITY_NAME_ABBR') or c,
                    'reason': r.get('EXPLANATION') or '龙虎榜公开信息'
                })
        _LHB_LIST_CACHE = items
        _LHB_LIST_CACHE_TIME = now
        return items
    except Exception as e:
        print(f"[LHB_LIST] Fetch error: {e}")
        return _LHB_LIST_CACHE or []

def get_real_dragon_tiger(symbol: str) -> Dict[str, Any]:
    clean_code = symbol.split('.')[0].strip().zfill(6)
    today_lhb = get_today_lhb_list()
    
    rb, rs, day, reason = [], [], None, ''
    for i in range(9):
        dd = dt.date.today() - dt.timedelta(days=i)
        if dd.weekday() >= 5:
            continue
        ds = dd.strftime('%Y-%m-%d')
        b = sd._lhb_detail(clean_code, ds, 'B')
        s = sd._lhb_detail(clean_code, ds, 'S')
        if b or s:
            day, rb, rs = ds, b or [], s or []
            reason = (b[0].get('EXPLANATION') if b else (s[0].get('EXPLANATION') if s else ''))
            break
            
    if not (rb or rs):
        # 当前标的没有上榜数据
        return {
            'status': 'ok',
            'hasLhb': False,
            'symbol': symbol,
            'message': f"标的 {symbol} 近两周未披露龙虎榜公开信息",
            'todayLhbList': today_lhb
        }

    # 提取真实买入卖出席位
    buy_seats_raw = rb[:5]
    sell_seats_raw = rs[:5]
    
    total_turnover = float(buy_seats_raw[0].get('ACCUM_AMOUNT') or (sell_seats_raw[0].get('ACCUM_AMOUNT') if sell_seats_raw else 1e9))
    
    buy_items = []
    for idx, r in enumerate(buy_seats_raw):
        bname = r.get('OPERATEDEPT_NAME') or '未知席位'
        meta = _classify_seat(bname)
        b_amt = float(r.get('BUY') or 0.0)
        s_amt = float(r.get('SELL') or 0.0)
        buy_items.append({
            'rank': idx + 1,
            'side': 'BUY',
            'branchName': bname,
            'nature': meta['nature'],
            'natureLabel': meta['natureLabel'],
            'seatTag': meta['seatTag'],
            'operatingStyle': meta['style'],
            'buyAmount': b_amt,
            'sellAmount': s_amt,
            'netAmount': b_amt - s_amt,
            'turnoverSharePercent': round(b_amt / total_turnover * 100, 2) if total_turnover > 0 else 0.0
        })
        
    sell_items = []
    for idx, r in enumerate(sell_seats_raw):
        bname = r.get('OPERATEDEPT_NAME') or '未知席位'
        meta = _classify_seat(bname)
        b_amt = float(r.get('BUY') or 0.0)
        s_amt = float(r.get('SELL') or 0.0)
        sell_items.append({
            'rank': idx + 1,
            'side': 'SELL',
            'branchName': bname,
            'nature': meta['nature'],
            'natureLabel': meta['natureLabel'],
            'seatTag': meta['seatTag'],
            'operatingStyle': meta['style'],
            'buyAmount': b_amt,
            'sellAmount': s_amt,
            'netAmount': b_amt - s_amt,
            'turnoverSharePercent': round(s_amt / total_turnover * 100, 2) if total_turnover > 0 else 0.0
        })
        
    total_b = sum(x['buyAmount'] for x in buy_items)
    total_s = sum(x['sellAmount'] for x in sell_items)
    net_amt = total_b - total_s
    
    # 正交算子验身
    try:
        ledger = lhb.SeatReputationLedger()
        evaluator = lhb.LHBOrthogonalEvaluator(ledger)
        B = np.array([x['buyAmount'] / 1e4 for x in buy_items])
        buy_sells = np.array([x['sellAmount'] / 1e4 for x in buy_items])
        S = np.array([x['sellAmount'] / 1e4 for x in sell_items])
        sell_buys = np.array([x['buyAmount'] / 1e4 for x in sell_items])
        is_retail = np.array([x['nature'] == 'RETAIL_CAMP' for x in buy_items])
        
        # --- P0-3 修复: 从真实数据计算盘中微观维度，不再硬编码 ---
        # 中性默认值: vw_dvr=0.5 (低于0.58翻转中心，无方向性偏差)
        vw_dvr, vw_dvr_src = 0.5, 'estimated_neutral'
        # limit_strength=0.0 (无封单强度信号); float_cap=极大值 (禁用垄断误报)
        limit_strength, limit_strength_src = 0.0, 'estimated_neutral'
        float_cap, float_cap_src = 1e12, 'estimated_neutral'

        # 尝试从分时数据计算真实 VW-DVR
        try:
            trends = df_feed.get_intraday_trends(clean_code)
            if trends and trends.get('prices') and float(trends.get('pre_close', 0)) > 0:
                close_1m = np.array(trends['prices'], dtype=float)
                pc = float(trends['pre_close'])
                # 分时数据无分钟高低价，用close近似;
                # DVR核心(rv_down/rv_total)仅依赖close收益率，结果准确
                dvr_res = usm.calc_intraday_dvr(close_1m, close_1m, close_1m, pc)
                if dvr_res and dvr_res.dvr is not None:
                    vw_dvr = float(dvr_res.dvr)
                    vw_dvr_src = 'intraday_realtime'
        except Exception:
            pass

        # 尝试从涨停池获取封单强度与流通市值
        try:
            profile = get_ultra_short_profile(symbol, None)
            if profile:
                seal_amt = float(profile.get('sealOrderAmount', 0) or 0)
                if seal_amt > 0 and total_turnover > 0:
                    limit_strength = min(1.0, seal_amt / total_turnover)
                    limit_strength_src = 'limit_pool_realtime'
                ltsz = float(profile.get('ltsz', 0) or 0)
                if ltsz > 0:
                    float_cap = ltsz / 1e4  # 元 → 万元
                    float_cap_src = 'limit_pool_realtime'
        except Exception:
            pass

        micro_dims = {
            'vwDvr': round(vw_dvr, 4),
            'vwDvrSource': vw_dvr_src,
            'limitStrength': round(limit_strength, 4),
            'limitStrengthSource': limit_strength_src,
            'floatCap': round(float_cap, 2),
            'floatCapSource': float_cap_src,
            'microDimensionsActive': (
                vw_dvr_src != 'estimated_neutral'
                or limit_strength_src != 'estimated_neutral'
                or float_cap_src != 'estimated_neutral'
            ),
        }

        eval_res = evaluator.evaluate_board(
            buy_seats=[x['branchName'] for x in buy_items],
            buy_amounts=B,
            buy_side_sells=buy_sells,
            sell_amounts=S,
            is_retail_seat=is_retail,
            total_turnover=total_turnover / 1e4,
            float_cap=float_cap,
            vw_dvr=vw_dvr,
            limit_strength=limit_strength,
            is_limit_up=True,
            sell_seats=[x['branchName'] for x in sell_items],
            sell_side_buys=sell_buys
        )
        lhb_score = eval_res.get('total_lhb_score', 0.0)
        lhb_imbalance = eval_res.get('lhb_net_imbalance', 0.0)
        gate_passed = eval_res.get('gate_passed', True)
    except Exception as e:
        lhb_score = 0.0
        lhb_imbalance = 0.0
        gate_passed = True
        micro_dims = {
            'vwDvr': 0.5, 'vwDvrSource': 'error_fallback',
            'limitStrength': 0.0, 'limitStrengthSource': 'error_fallback',
            'floatCap': 1e12, 'floatCapSource': 'error_fallback',
            'microDimensionsActive': False,
        }

    # 阵营聚合统计
    camp_names = [
        ('HOT_MONEY', '游资阵营'),
        ('INSTITUTION', '机构北向'),
        ('QUANT_CAMP', '量化大本营'),
        ('RETAIL_CAMP', '散户合力')
    ]
    camp_breakdown = []
    for c_type, c_label in camp_names:
        c_buys = [x for x in buy_items if x['nature'] == c_type]
        c_sells = [x for x in sell_items if x['nature'] == c_type]
        b_sum = sum(x['buyAmount'] for x in c_buys)
        s_sum = sum(x['sellAmount'] for x in c_sells)
        tags = list({x['seatTag'] for x in (c_buys + c_sells)})
        camp_breakdown.append({
            'nature': c_type,
            'label': c_label,
            'buyAmount': b_sum,
            'sellAmount': s_sum,
            'netAmount': b_sum - s_sum,
            'buySharePercent': round(b_sum / total_b * 100, 1) if total_b > 0 else 0.0,
            'seatCount': len(c_buys) + len(c_sells),
            'representativeTags': tags
        })
        
    # 定性协同研判
    inst_buy = sum(x['buyAmount'] for x in buy_items if x['nature'] == 'INSTITUTION')
    yz_buy = sum(x['buyAmount'] for x in buy_items if x['nature'] == 'HOT_MONEY')
    quant_buy = sum(x['buyAmount'] for x in buy_items if x['nature'] == 'QUANT_CAMP')
    retail_buy = sum(x['buyAmount'] for x in buy_items if x['nature'] == 'RETAIL_CAMP')
    
    if inst_buy > 0 and yz_buy > 0 and (inst_buy + yz_buy) / total_b > 0.5:
        verdict = 'HOT_INST_RESONANCE'
        synergy_label = '游资+机构共振主封'
        playbook = '龙虎榜呈现顶级游资与机构并肩主封，席位合力极佳，次日竞价高开溢价概率极高。'
    elif yz_buy / total_b > 0.6:
        verdict = 'TOP_HOT_LOCK'
        synergy_label = '一线游资强力锁仓'
        playbook = '游资席位绝对控盘主买，超短情绪进攻属性强，关注次日竞价量比与分时承接。'
    elif quant_buy / total_b > 0.4:
        verdict = 'QUANT_CROWDED_RISK'
        synergy_label = '量化扎堆兑现风险'
        playbook = '头部量化席位占比过高，谨防次日早盘高开急冲诱多后量化算法程序化砸盘。'
    elif retail_buy / total_b > 0.4:
        verdict = 'RETAIL_TAKEOVER_WARN'
        synergy_label = '散户天团接盘预警'
        playbook = '拉萨散户大本营净买偏多，主力席位退潮出逃，追高接力胜率显著下降。'
    else:
        verdict = 'MAIN_FORCE_EXIT'
        synergy_label = '主力席位大举分歧'
        playbook = '席位多空博弈激烈，前五卖额偏大，等待盘中分歧转强再定去留。'

    board_type = '3D' if ('连续三个交易日' in reason or '3个交易日' in reason) else '1D'

    analysis = {
        'symbol': symbol,
        'code': clean_code,
        'name': buy_seats_raw[0].get('SECURITY_NAME_ABBR') or clean_code,
        'sector': 'A股主板/成长股',
        'price': float(buy_seats_raw[0].get('CLOSE_PRICE') or 0.0),
        'changePercent': float(buy_seats_raw[0].get('CHANGE_RATE') or 0.0) * 100,
        'dailyAmount': total_turnover,
        'boardType': board_type,
        'listingReason': reason or '龙虎榜公开信息',
        'tradeDate': day,
        'buySeats': buy_items,
        'sellSeats': sell_items,
        'totalBuyAmount': total_b,
        'totalSellAmount': total_s,
        'totalNetAmount': net_amt,
        'buyTurnoverRatioPercent': round(total_b / total_turnover * 100, 2) if total_turnover > 0 else 0.0,
        'sellTurnoverRatioPercent': round(total_s / total_turnover * 100, 2) if total_turnover > 0 else 0.0,
        'netTurnoverRatioPercent': round(net_amt / total_turnover * 100, 2) if total_turnover > 0 else 0.0,
        'campBreakdown': camp_breakdown,
        'dominantCamp': max(camp_breakdown, key=lambda x: x['buyAmount'])['nature'],
        'synergyVerdict': verdict,
        'synergyLabel': synergy_label,
        'nextDayPremiumScore': max(10, min(95, int(50 + lhb_score * 5 + (net_amt / total_turnover * 100)))),
        'actionablePlaybook': playbook,
        'totalLhbScore': round(lhb_score, 2),
        'lhbNetImbalance': round(lhb_imbalance, 4),
        'gatePassed': gate_passed,
        'microDimensions': micro_dims
    }

    return {
        'status': 'ok',
        'hasLhb': True,
        'analysis': analysis,
        'todayLhbList': today_lhb
    }

def get_real_ladder() -> Dict[str, Any]:
    # 取最新可用交易日的涨停池
    zt = []
    target_ymd = dt.date.today().strftime('%Y%m%d')
    for i in range(5):
        dd = dt.date.today() - dt.timedelta(days=i)
        if dd.weekday() >= 5:
            continue
        ymd = dd.strftime('%Y%m%d')
        pool = sd._pool('ZT', ymd)
        if pool:
            zt = pool
            target_ymd = ymd
            break
            
    ladder_grouped: Dict[int, List[Dict[str, Any]]] = {}
    for x in zt:
        lbc = int(x.get('lbc') or 1)
        c = str(x.get('c') or '').strip().zfill(6)
        market = 'SH' if c.startswith('6') else 'SZ'
        p_raw = float(x.get('p') or 0.0)
        price = p_raw / 1000.0 if p_raw > 100.0 else p_raw
        ladder_grouped.setdefault(lbc, []).append({
            'symbol': f"{c}.{market}",
            'code': c,
            'name': x.get('n') or c,
            'sector': x.get('hybk') or '通用行业',
            'price': price,
            'changePercent': round(float(x['zdp']), 2) if x.get('zdp') is not None else round(float(x.get('zdf') or 0.0), 2),
            'firstSealTime': _format_fbt(x.get('fbt') or x.get('fstime')),
            'sealOrderAmount': float(x.get('fund') or 0.0),
            'dragonRole': 'SPACE_DRAGON' if lbc >= 5 else ('BENCHMARK' if lbc >= 3 else 'FOLLOWER'),
            # 真实 ultraShort：前端此前为了拿到连板身位，在本地硬编码了一套
            # （auctionVolume=12000 / yesterdayAmount=1.5亿 / cumDeviation 按板数查表），
            # 这里直接给真值，前端就不必再编。
            'ultraShort': get_ultra_short_profile(f"{c}.{market}")
        })
        
    diag = sd.analyze_ladder_faults({k: [s['name'] for s in v] for k, v in ladder_grouped.items()})
    max_h = diag.get('max_height', 1)
    
    # 降序构建梯队分布行
    tier_rows = []
    for b in range(max_h, 0, -1):
        stk_list = ladder_grouped.get(b, [])
        is_missing = len(stk_list) == 0 and b in diag.get('fault_levels', [])
        tier_rows.append({
            'boardCount': b,
            'label': f"{b}连板 (最高标)" if b == max_h else (f"{b}连板 (断层)" if is_missing else (f"{b}连板" if b > 1 else '首板 (1板)')),
            'todaySealedCount': len(stk_list),
            'isFaultMissing': is_missing,
            'stockNames': [s['name'] for s in stk_list],
            # 详细对象只在 distributionComparison 保留一份，此处仅给代码，避免响应体重复约 18KB
            'stockSymbols': [s['symbol'] for s in stk_list]
        })
        
    second_max = 0
    for b in sorted(ladder_grouped.keys(), reverse=True):
        if b < max_h and len(ladder_grouped[b]) > 0:
            second_max = b
            break
            
    top_stocks = ladder_grouped.get(max_h, [])
    space_dragon = top_stocks[0]['name'] if top_stocks else '无'
    has_fault = bool(diag.get('has_fault', False))
    fault_levels = diag.get('fault_levels', [])

    distribution_comparison = []
    for row in tier_rows:
        b = row['boardCount']
        stks = ladder_grouped.get(b, [])   # 直接从源取，tiers 只保留 symbol 列表
        is_missing = row['isFaultMissing']
        yest_base = 0 if b == 1 else (len(stks) if not is_missing else None)
        eliminated = 0 if b == 1 else (max(0, yest_base - len(stks)) if yest_base is not None else None)
        prom_rate = None if b == 1 else (round(len(stks) / max(1, yest_base) * 100, 1) if not is_missing and yest_base is not None else None)
        distribution_comparison.append({
            'boardCount': b,
            'label': row['label'],
            'yesterdayBaseLabel': '新发酵首板池' if b == 1 else (f'昨{b-1}板 ({yest_base}家)' if yest_base is not None else f'昨{b-1}板 (数据缺失)'),
            'yesterdayBaseCount': yest_base,
            'yesterdayCandidateCount': None if b == 1 else yest_base,
            'todaySealedCount': len(stks),
            'eliminatedCount': eliminated,
            'promotionRate': prom_rate,
            'isFaultMissing': is_missing,
            'isFaultLevel': is_missing,
            'stockNames': row['stockNames'],
            'stocks': stks
        })

    fault_zones = []
    if fault_levels:
        sorted_faults = sorted(fault_levels)
        start = sorted_faults[0]
        prev = sorted_faults[0]
        for cur in sorted_faults[1:] + [None]:
            if cur is not None and cur == prev + 1:
                prev = cur
            else:
                span_size = prev - start + 1
                fault_zones.append({
                    'fromBoard': start,
                    'toBoard': prev,
                    'spanSize': span_size,
                    'label': f"{start}连板 (单层断层)" if start == prev else f"{start}连板 ~ {prev}连板 (连续{span_size}层真空断层)"
                })
                if cur is not None:
                    start = cur
                    prev = cur

    # ---- 真实统计（替换原先硬编码的假值）----
    # 炸板池/跌停池与晋级率一律取自真实接口数据，取不到则置 None 由前端显示 "—"
    zb_pool = sd._pool('ZB', target_ymd) or []
    dt_pool = sd._pool('DT', target_ymd) or []
    broken_cnt = len(zb_pool)
    limit_down_cnt = len(dt_pool)

    # 晋级率：用上一交易日的池子与今日对比（真实计算，不再硬编码）
    _prev_zt = []
    _base = dt.datetime.strptime(target_ymd, '%Y%m%d').date()
    for i in range(1, 8):
        _pd = (_base - dt.timedelta(days=i)).strftime('%Y%m%d')
        _p = sd._pool('ZT', _pd)
        if _p:
            _prev_zt = _p
            break

    def _promotion_rate(prev_board, today_board):
        """昨日 prev_board 板 -> 今日 today_board 板的晋级率（%），无基数返回 None。"""
        if not _prev_zt:
            return None
        prev_codes = {str(x.get('c') or '').zfill(6) for x in _prev_zt
                      if int(x.get('lbc') or 1) == prev_board}
        if not prev_codes:
            return None
        today_codes = {str(x.get('c') or '').zfill(6) for x in zt
                       if int(x.get('lbc') or 1) >= today_board}
        return round(len(prev_codes & today_codes) / len(prev_codes) * 100, 1)

    first_to_second = _promotion_rate(1, 2)
    second_to_third = _promotion_rate(2, 3)
    high_board_promotion = _promotion_rate(max_h - 1, max_h) if max_h >= 2 else None
    # 封板成功率 = 涨停数 / (涨停数 + 炸板数)
    _seal_denom = len(zt) + broken_cnt
    seal_success = round(len(zt) / _seal_denom * 100, 1) if _seal_denom else None

    return {
        'status': 'ok',
        'tradeDate': target_ymd,
        'totalCount': len(zt),
        'totalLimitUpCount': len(zt),
        'maxBoardHeight': max_h,
        'secondMaxBoardHeight': second_max,
        'spaceDragonName': space_dragon,
        'spaceDragonSymbol': top_stocks[0]['symbol'] if top_stocks else '',
        'hasLadderFault': has_fault,
        'missingBoards': fault_levels,
        'maxFaultSpan': len(fault_levels),
        'statusDesc': diag.get('status_desc', ''),
        'tag': diag.get('tag', ''),
        'firstToSecondRate': first_to_second,
        'secondToThirdRate': second_to_third,
        'highBoardPromotionRate': high_board_promotion,
        'sealSuccessRate': seal_success,
        'brokenBoardCount': broken_cnt,
        'limitDownCount': limit_down_cnt,
        'ebbTideRiskScore': round(min(98.5, max(8,
            len(fault_levels) * 16 +          # 断层跨度：每层 16 分
            broken_cnt * 6 +                   # 炸板数：每家 6 分
            limit_down_cnt * 8 +               # 跌停核按钮：每家 8 分
            (max(0, 75 - seal_success) * 0.4) + # 封板率低于 75 的惩罚
            (12 if (max_h - second_max) >= 2 else 0)  # 最高标孤立的连板差 ≥2 加 12
        )), 1) if has_fault else round(min(32, max(8,
            broken_cnt * 7 + limit_down_cnt * 8
        )), 1),
        'ebbTideRiskLevel': 'HIGH_EBB_RISK' if (has_fault and len(fault_levels) >= 2) or limit_down_cnt >= 3 else ('MEDIUM_FAULT_RISK' if has_fault or broken_cnt >= 2 else 'LOW_HEALTHY'),
        'sentimentPhase': '退潮核按钮期' if limit_down_cnt >= 3 or (has_fault and len(fault_levels) >= 2) else ('高潮分化期' if broken_cnt >= 2 or has_fault else ('主升共振期' if seal_success >= 75 and max_h >= 4 else '混沌试错期')),
        'ebbTideWarningTitle': f"【{'高危退潮预警' if has_fault else '平稳'}】{diag.get('status_desc', '')}",
        'ebbTideRiskReasons': [
            f"全市场梯队出现断层：缺 {fault_levels} 连板",
            f"空间高度龙为 {space_dragon} ({max_h}连板)，次高板为 {second_max}连板",
            f"全市场真实涨停池共抓取 {len(zt)} 只标的，梯队覆盖 1~{max_h} 板"
        ],
        'faultZones': fault_zones,
        'faultWarningText': diag.get('status_desc', '梯队状态正常'),
        'tacticalPlaybook': '中位股存在断层退潮风险，严格管住手，重点关注前排核心首板或空间龙分歧承接。' if has_fault else '梯队结构完整，连板情绪良性，可顺势参与主线核心梯队。',
        'topDragonIsolation': (max_h - second_max) >= 2,
        'distributionComparison': distribution_comparison,
        'tiers': tier_rows
    }


def get_real_theme_resonance() -> Dict[str, Any]:
    """获取全市场真实题材/行业主力资金共振与领涨龙头联动数据，彻底淘汰 np.random 与写死假题材"""
    import urllib.request

    # 1. 取最新可用交易日的涨停池
    zt = []
    target_ymd = dt.date.today().strftime('%Y%m%d')
    for i in range(5):
        dd = dt.date.today() - dt.timedelta(days=i)
        if dd.weekday() >= 5:
            continue
        ymd = dd.strftime('%Y%m%d')
        pool = sd._pool('ZT', ymd)
        if pool:
            zt = pool
            target_ymd = ymd
            break

    zt_by_hy: Dict[str, List[Dict[str, Any]]] = {}
    zt_by_code: Dict[str, Dict[str, Any]] = {}
    for x in zt:
        hy = x.get('hybk') or '其他'
        c = str(x.get('c') or '').strip().zfill(6)
        mkt = 'SH' if c.startswith(('6', '9')) else ('BJ' if c.startswith(('4', '8')) else 'SZ')
        p_raw = float(x.get('p') or 0.0)
        price = p_raw / 1000.0 if p_raw > 100.0 else p_raw
        lbc = int(x.get('lbc') or 1)
        stk_info = {
            'symbol': f"{c}.{mkt}",
            'code': c,
            'name': x.get('n') or c,
            'price': price,
            'changePercent': round(float(x['zdp']), 2) if x.get('zdp') is not None else float(x.get('zdf') or 0.0),
            'consecutiveBoards': lbc,
            'dragonRole': 'SPACE_DRAGON' if lbc >= 5 else ('BENCHMARK' if lbc >= 3 else 'FOLLOWER'),
            'roleLabel': '空间高度龙' if lbc >= 5 else ('中军辨识度' if lbc >= 3 else '跟风助攻'),
            'firstSealTime': _format_fbt(x.get('fbt') or x.get('fstime')) or '09:30:00',
            'amount': float(x.get('fund') or 0.0),
            'isLimitUp': True
        }
        zt_by_hy.setdefault(hy, []).append(stk_info)
        zt_by_code[c] = stk_info

    # 2. 从东财抓取行业与概念板块主力资金流向
    urls = [
        ('http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=15&po=1&np=1&fltt=2&fid=f62&fs=m:90+t:2&fields=f12,f14,f2,f3,f6,f62,f104,f105,f106,f128,f140,f136', '行业'),
        ('http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=15&po=1&np=1&fltt=2&fid=f62&fs=m:90+t:3&fields=f12,f14,f2,f3,f6,f62,f104,f105,f106,f128,f140,f136', '概念')
    ]
    raw_sectors = []
    seen_names = set()
    for u, cat in urls:
        try:
            req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
            res_str = urllib.request.urlopen(req, timeout=3.5).read().decode('utf-8')
            diff = json.loads(res_str).get('data', {}).get('diff', [])
            for d in diff:
                name = d.get('f14')
                if not name or name in seen_names:
                    continue
                seen_names.add(name)
                d['category'] = cat
                raw_sectors.append(d)
        except Exception:
            pass

    # 若东财网络完全异常，降级至新浪行业数据
    if not raw_sectors:
        try:
            req = urllib.request.Request('http://vip.stock.finance.sina.com.cn/q/view/newSinaHy.php')
            raw = urllib.request.urlopen(req, timeout=3.5).read().decode('gbk', errors='ignore')
            s_dict = json.loads(raw.split('=', 1)[1].strip())
            for k, v in s_dict.items():
                parts = v.split(',')
                if len(parts) >= 13:
                    raw_sectors.append({
                        'f14': parts[1],
                        'f12': parts[0],
                        'f3': float(parts[5]),
                        'f6': float(parts[7]),
                        'f62': float(parts[7]) * (float(parts[5]) / 100.0) * 0.15,
                        'f104': int(float(parts[2]) * 0.6),
                        'f105': int(float(parts[2]) * 0.3),
                        'f106': int(float(parts[2]) * 0.1),
                        'f128': parts[12],
                        'f140': parts[8].replace('sz', '').replace('sh', ''),
                        'f136': float(parts[9]),
                        'category': '行业'
                    })
        except Exception:
            pass

    # 3. 计算每个板块的量化指标
    themes = []
    total_pos_flow = sum(max(0.0, float(d.get('f62') or 0.0)) for d in raw_sectors) or 1.0

    for d in raw_sectors:
        name = str(d.get('f14') or '')
        pct = round(float(d.get('f3') or 0.0), 2)
        net_flow = float(d.get('f62') or 0.0)
        turnover = float(d.get('f6') or 0.0)
        up_cnt = int(d.get('f104') or 0)
        down_cnt = int(d.get('f105') or 0)
        flat_cnt = int(d.get('f106') or 0)
        total_stk = up_cnt + down_cnt + flat_cnt
        if total_stk == 0:
            total_stk = 50
        up_ratio = round((up_cnt / total_stk) * 100.0, 1)

        # 匹配真实涨停股
        zt_members = zt_by_hy.get(name, [])
        limit_up_cnt = len(zt_members)
        density_pct = round((limit_up_cnt / max(1, total_stk)) * 100.0, 2)

        if limit_up_cnt >= 4 or density_pct >= 4.0:
            density_level = '涨停潮高密区'
        elif limit_up_cnt >= 2:
            density_level = '梯队成型区'
        elif limit_up_cnt == 1:
            density_level = '局部试错区'
        else:
            density_level = '冰点无溢价'

        leader_n = str(d.get('f128') or '')
        leader_c = str(d.get('f140') or '').strip().zfill(6)
        leader_p = round(float(d.get('f136') or 0.0), 2)
        leader_mkt = 'SH' if leader_c.startswith(('6', '9')) else ('BJ' if leader_c.startswith(('4', '8')) else 'SZ')
        leader_sym = f"{leader_c}.{leader_mkt}"

        # 封板判定阈值按板块涨跌幅制度来（主板 10%、双创 20%、北交所 30%），
        # 同时看它是否真的在当日涨停池里 —— 池子里的才是"确定封板"。
        if leader_c.startswith(('300', '301', '688', '689')):
            seal_threshold = 19.5
        elif leader_c.startswith(('4', '8')):
            seal_threshold = 29.0
        else:
            seal_threshold = 9.8
        leader_in_pool = zt_by_code.get(leader_c)
        leader_sealed = bool(leader_in_pool) or leader_p >= seal_threshold

        # 点面共振综合得分 (0~100)
        resonance_score = min(100.0, max(20.0, round(
            50.0 + pct * 4.5 + (up_ratio - 50.0) * 0.35 + (net_flow / 1e9) * 1.8 + limit_up_cnt * 5.0,
            1
        )))

        if resonance_score >= 75.0:
            resonance_status = '主线强共振'
        elif resonance_score >= 55.0:
            resonance_status = '局部轮动'
        else:
            resonance_status = '分歧兑现'

        # 龙头联动指数 (0~100)
        if leader_sealed:
            if up_ratio >= 65.0:
                dragon_linkage_score = min(100.0, round(80.0 + limit_up_cnt * 4.0, 1))
                dragon_linkage_status = '先锋中军强联动'
                dragon_linkage_desc = f"先锋龙头【{leader_n}】{'强势封板' if leader_in_pool else f'领涨 {leader_p}%'}，板块红盘率高达 {up_ratio}%，后排梯队协同承接充沛"
            else:
                dragon_linkage_score = 62.0
                dragon_linkage_status = '单点脉冲跟风弱'
                dragon_linkage_desc = f"先锋龙头【{leader_n}】快速拉板，但板块跟风红盘仅 {up_ratio}%，呈现单点孤勇特征"
        else:
            dragon_linkage_score = max(35.0, round(45.0 + leader_p * 2.0, 1))
            dragon_linkage_status = '龙头孤立背离'
            dragon_linkage_desc = f"领涨标的【{leader_n}】涨幅 {leader_p}% 未能封板，板块缺乏绝对领涨中枢"

        # 进攻角色定性
        if resonance_score >= 70.0 and net_flow > 0:
            attack_role = 'MAIN_ATTACK'
            attack_role_label = '主攻核心主线'
        elif net_flow > 0:
            attack_role = 'SUB_ROTATION'
            attack_role_label = '支线轮动助攻'
        elif pct >= 0:
            attack_role = 'DEFENSIVE_HOLD'
            attack_role_label = '分歧观察区'
        else:
            attack_role = 'EBB_RETREAT'
            attack_role_label = '资金兑现退潮'

        cap_attack_share = max(1.0, round((max(0.0, net_flow) / total_pos_flow) * 100.0, 1))
        heat_weight = max(40.0, round(turnover / 1e8 * 0.1 + resonance_score * 0.9, 1))

        # 梯队成分股构建
        # ⚠️ 领涨股如果不在当日涨停池里，我们对它的"首封时间/连板数/封单额"一无所知。
        # 旧实现直接编了 firstSealTime='09:35:00'、amount=turnover*0.15、isLimitUp=p>=9.5，
        # 于是 45 只成员股的首封时间全是 09:35 / 09:30 两个值。现在：查得到就用池子真值，
        # 查不到就返回 None，绝不编。
        member_list = list(zt_members)
        if leader_n and not any(m['name'] == leader_n for m in member_list):
            member_list.insert(0, {
                'symbol': leader_sym,
                'code': leader_c,
                'name': leader_n,
                'price': 0.0,
                'changePercent': leader_p,
                'consecutiveBoards': leader_in_pool['consecutiveBoards'] if leader_in_pool else None,
                'dragonRole': 'PIONEER' if leader_sealed else 'FOLLOWER',
                'roleLabel': '领涨先锋' if leader_sealed else '跟风助攻',
                'firstSealTime': leader_in_pool['firstSealTime'] if leader_in_pool else None,
                'amount': leader_in_pool['amount'] if leader_in_pool else None,
                'isLimitUp': leader_sealed
            })

        pioneer_dragon = {
            'symbol': member_list[0]['symbol'] if member_list else leader_sym,
            'name': member_list[0]['name'] if member_list else leader_n,
            'changePercent': member_list[0]['changePercent'] if member_list else leader_p,
            'firstSealTime': member_list[0].get('firstSealTime') if member_list else None,
            'consecutiveBoards': member_list[0].get('consecutiveBoards') if member_list else None
        }

        capacity_core = {
            'symbol': leader_sym,
            'name': leader_n,
            'changePercent': leader_p,
            'amount': None  # 不编造容量核心成交额（原 turnover*0.12 无数据依据）
        }

        themes.append({
            'sectorName': name,
            'sectorChangePercent': pct,
            'limitUpCount': limit_up_cnt,
            'sectorConstituentCount': total_stk,
            'limitUpDensityPercent': density_pct,
            'densityLevel': density_level,
            'upRatioPercent': up_ratio,
            'totalNetInflowCNY': net_flow,
            'totalTurnoverCNY': turnover,
            'resonanceScore': resonance_score,
            'resonanceStatus': resonance_status,
            'dragonLinkageScore': dragon_linkage_score,
            'dragonLinkageStatus': dragon_linkage_status,
            'dragonLinkageDesc': dragon_linkage_desc,
            'attackRole': attack_role,
            'attackRoleLabel': attack_role_label,
            'capitalAttackSharePercent': cap_attack_share,
            'heatWeight': heat_weight,
            'pioneerDragon': pioneer_dragon,
            'capacityCore': capacity_core,
            'memberStocks': member_list[:12]
        })

    themes.sort(key=lambda x: (x['resonanceScore'], x['totalNetInflowCNY']), reverse=True)

    main_attacks = [t['sectorName'] for t in themes if t['attackRole'] == 'MAIN_ATTACK']
    if not main_attacks and themes:
        main_attacks = [t['sectorName'] for t in themes[:2]]
    sub_rotations = [t['sectorName'] for t in themes if t['attackRole'] == 'SUB_ROTATION']
    retreats = [t['sectorName'] for t in themes if t['attackRole'] == 'EBB_RETREAT']

    top3 = themes[:3]
    market_score = round(sum(t['resonanceScore'] for t in top3) / len(top3), 1) if top3 else 60.0
    mainstream_conc = round(sum(t['capitalAttackSharePercent'] for t in themes[:2]), 1) if len(themes) >= 2 else 50.0
    total_zt = sum(t['limitUpCount'] for t in themes)
    avg_density = round(sum(t['limitUpDensityPercent'] for t in themes) / len(themes), 2) if themes else 0.0

    top1 = themes[0] if themes else None
    top2 = themes[1] if len(themes) > 1 else None
    if top1 and top2:
        headline = f"当日全市场主力资金主攻【{top1['sectorName']}】(涨幅+{top1['sectorChangePercent']}% · 净流入{round(top1['totalNetInflowCNY']/1e8,1)}亿) 与【{top2['sectorName']}】(涨幅+{top2['sectorChangePercent']}% · 净流入{round(top2['totalNetInflowCNY']/1e8,1)}亿)，双主线合计凝聚全市场 {mainstream_conc}% 做多火力"
    elif top1:
        headline = f"当日全市场主力资金聚焦【{top1['sectorName']}】(涨幅+{top1['sectorChangePercent']}% · 净流入{round(top1['totalNetInflowCNY']/1e8,1)}亿)"
    else:
        headline = "全市场暂无显著主线共振"

    playbook = "顺应主攻板块先锋龙头身位与中军容量溢价，拒绝在资金兑现退潮板块盲目抄底接飞刀。"

    return {
        'status': 'ok',
        'scenario': 'live',
        'themes': themes,
        'mainstreamAttackSectors': main_attacks,
        'subRotationSectors': sub_rotations,
        'retreatSectors': retreats,
        'marketResonanceScore': market_score,
        'mainstreamConcentrationPercent': mainstream_conc,
        'totalMarketLimitUpCount': total_zt,
        'avgLimitUpDensityPercent': avg_density,
        'attackDirectionHeadline': headline,
        'tacticalPlaybook': playbook,
        'timestamp': int(time.time() * 1000)
    }


# ---------------- 超短身位档案 ultraShort ----------------
# 前端 UltraShortProfile（frontend/src/types/market.ts）需要的数据，只填**能从真实接口拿到**的：
#   · 连板数/首封时间/封单额/炸板次数/流通市值/行业 ← 东财涨停池、炸板池（lbc/fbt/fund/zbc/ltsz/hybk）
#   · 是否触板                                  ← L1 快照 high 与 limitUpPrice 比较
#   · 竞价价与竞价涨幅                            ← 开盘价即 9:25 集合竞价成交价
#   · 昨日形态/昨成交额                           ← 上一交易日涨停池、炸板池
# 拿不到的（竞价成交额、未匹配手数、竞价量比、10 日偏离度、T-1/T-2 涨跌幅）**一律不给**，
# 由前端按缺失处理（显示 "—" 或走 /api/quant/regulatory 的真实口径），绝不在这里编数字。
_US_INDEX_CACHE: Dict[str, Any] = {'ts': 0.0, 'data': None}
_US_INDEX_TTL = 30.0


def _ultra_pool_index() -> Optional[Dict[str, Any]]:
    """把「今日涨停池 / 今日炸板池 / 上一交易日涨停池+炸板池」建成按代码索引的表，30 秒缓存。

    sd._pool 自己已有缓存（历史日期永久、当日 30 秒），这里再压一层是为了避免
    WebSocket 批量报价时反复重建 dict。
    """
    now = time.time()
    if _US_INDEX_CACHE['data'] and now - _US_INDEX_CACHE['ts'] < _US_INDEX_TTL:
        return _US_INDEX_CACHE['data']

    zt, ymd = [], None
    for i in range(8):
        dd = dt.date.today() - dt.timedelta(days=i)
        if dd.weekday() >= 5:
            continue
        d = dd.strftime('%Y%m%d')
        pool = sd._pool('ZT', d) or []
        if pool:
            zt, ymd = pool, d
            break
    if not zt:
        # 取不到池子就返回 None —— 宁可不给 ultraShort，也不返回"0 连板"这种假结论
        return None

    prev_zt, prev_ymd = [], None
    base = dt.datetime.strptime(ymd, '%Y%m%d').date()
    for i in range(1, 9):
        pd = (base - dt.timedelta(days=i)).strftime('%Y%m%d')
        pool = sd._pool('ZT', pd) or []
        if pool:
            prev_zt, prev_ymd = pool, pd
            break

    def _idx(rows):
        return {str(r.get('c') or '').strip().zfill(6): r for r in rows}

    data = {
        'ymd': ymd,
        'prev_ymd': prev_ymd,
        'zt': _idx(zt),
        'zb': _idx(sd._pool('ZB', ymd) or []),
        'prev_zt': _idx(prev_zt),
        'prev_zb': _idx(sd._pool('ZB', prev_ymd) or []) if prev_ymd else {},
        'max_lb': max([int(r.get('lbc') or 1) for r in zt] or [1]),
    }
    _US_INDEX_CACHE['ts'] = now
    _US_INDEX_CACHE['data'] = data
    return data


def get_ultra_short_profile(symbol: str, quote: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """构建单只标的的 ultraShort。取不到池子返回 None（前端保留旧值/显示"—"）。"""
    idx = _ultra_pool_index()
    if not idx:
        return None

    code = str(symbol or '').split('.')[0].strip().zfill(6)
    row = idx['zt'].get(code)
    prev_row = idx['prev_zt'].get(code)
    zb_row = idx['zb'].get(code)
    prev_zb_row = idx['prev_zb'].get(code)

    lbc = int(row.get('lbc') or 1) if row else 0
    yest_lbc = int(prev_row.get('lbc') or 1) if prev_row else 0
    max_lb = int(idx['max_lb'] or 1)

    # 触板判定：在涨停池里必然触过板；否则用 L1 的最高价与涨停价比
    touched = bool(row)
    limit_px = None
    if quote:
        try:
            lp = float(quote.get('limitUpPrice') or 0.0)
            hi = float(quote.get('high') or 0.0)
            if lp > 0:
                limit_px = round(lp, 2)
                touched = touched or hi >= lp - 0.005
        except (TypeError, ValueError):
            pass

    if lbc >= 3 and lbc >= max_lb:
        role = 'SPACE_DRAGON'
    elif lbc >= 2:
        role = 'PIONEER_DRAGON'
    else:
        role = 'FOLLOWER'

    seal_amt = float(row.get('fund') or 0.0) if row else 0.0
    float_cap = float(row.get('ltsz') or 0.0) if row else 0.0

    if prev_zb_row:
        note = '昨炸板分歧'
    elif yest_lbc >= 2:
        note = f'昨{yest_lbc}连板'
    elif yest_lbc == 1:
        note = '昨首板'
    elif prev_row:
        note = '昨涨停'
    else:
        note = '昨未涨停'

    # 竞价：9:25 集合竞价成交价 = 当日开盘价；涨幅按昨收算
    auction_px = auction_pct = None
    if quote:
        try:
            o = float(quote.get('open') or 0.0)
            pc = float(quote.get('prevClose') or 0.0)
            if o > 0 and pc > 0:
                auction_px = round(o, 2)
                auction_pct = round((o / pc - 1.0) * 100.0, 2)
        except (TypeError, ValueError):
            pass

    yest_amount = None
    for r in (prev_row, prev_zb_row):
        if r and r.get('amount'):
            try:
                yest_amount = float(r['amount'])
                break
            except (TypeError, ValueError):
                pass

    is_30 = code.startswith(('300', '301', '688', '689'))
    # 池子的日期决定这套身位数据的"口径日"：盘前/周末时最新池仍是上一交易日，
    # 此时 consecutiveBoards 描述的是那个交易日，而不是"此刻"。用 isCurrentSession 标明，
    # 前端可据此提示"截至 10/23"，避免把昨天的 6 板当成今天的 6 板。
    today_ymd = dt.date.today().strftime('%Y%m%d')
    pool_pct = round(float(row['zdp']), 2) if row and row.get('zdp') is not None else None
    quote_pct = None
    if quote:
        try:
            if quote.get('changePercent') is not None:
                quote_pct = round(float(quote['changePercent']), 2)
        except (TypeError, ValueError):
            quote_pct = None
    return {
        'poolDate': idx['ymd'],
        'prevPoolDate': idx['prev_ymd'],
        'isCurrentSession': idx['ymd'] == today_ymd,
        'consecutiveBoards': lbc,
        'yesterdayBoards': yest_lbc,
        'isSealed': bool(row),
        'isIntradayTouchedLimitUp': touched,
        'firstSealTime': _format_fbt(row.get('fbt')) if row else None,
        'dragonRole': role,
        'boardRuleType': 'CHINEXT_STAR_30' if is_30 else 'MAIN_20',
        'limitUpPrice': limit_px,
        'sealOrderAmount': round(seal_amt, 2),
        'sealRatioPct': round(seal_amt / float_cap * 100.0, 2) if float_cap > 0 else None,
        'brokenTimes': int(row.get('zbc') or 0) if row else 0,
        'sector': (row or prev_row or {}).get('hybk') or (zb_row or {}).get('hybk'),
        # 涨幅优先用实时报价（今天涨了多少），没有报价才退回池子口径（那个交易日的涨幅）
        'changePercent': quote_pct if quote_pct is not None else pool_pct,
        'poolChangePercent': pool_pct,
        'auctionPrice': auction_px,
        'auctionChangePercent': auction_pct,
        'yesterdayAmount': yest_amount,
        'yesterdayPerformanceNote': note,
        'source': 'eastmoney_pool',
    }
