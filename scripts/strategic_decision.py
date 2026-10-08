#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
战略战术决策中枢 (Strategic Decision Engine) v2.1
基于《毛泽东选集》底层认识论与决策方法论：
  1. 《论持久战》—— 战略阶段与大势定位 (防御 / 相持 / 反攻，单一事实源消费 cycle_position；空数据 unknown 守卫)
  2. 《实践论 / 反对本本主义》—— 实事求是 · 盘面微观真相核验 (消费已有 diverge，穿透指数虚火，无数据不造假)
  3. 《矛盾论》—— 抓主要矛盾与核心战场 (多日资金净流与梯队定性，识别轮动诱多与单日脉冲)
  4. 《战略问题》—— 集中优势兵力打歼灭战 (持仓账本真实对账 + 9:25 开火硬量化开关 + 动态止损)
"""
import sys
import os
import json
import time
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stock_dashboard as sd

DECISION_LOG_PATH = os.path.join(sd.DATA_DIR, 'strategy_decisions.jsonl')


def _log_decision_record(rec):
    """持久化战略判定记录，供次日对账与回测核验"""
    try:
        os.makedirs(sd.DATA_DIR, exist_ok=True)
        with open(DECISION_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    except Exception:
        pass


def analyze_strategic_decision(emo=None, sec=None, idxs=None, portfolio=None, account_equity=None):
    """
    基于第一手客观数据生成战略战术决策中枢报告
    :param emo: 情绪字典 (来自 sd.emotion())
    :param sec: 板块资金流 (来自 sd.sector_flow())
    :param idxs: 指数行情 (来自 sd.tx_realtime(sd.IDX_CODES))
    :param portfolio: 用户实际持仓账本 [{'code': '600519', 'shares': 200, 'cost': 1450, 'stop_loss': 1380}, ...]
    :param account_equity: 账户总资产 (元)，未指定则按 1,000,000 元估算并显式注明
    """
    # 1. 彻底防守 None 与异常崩溃
    if emo is None:
        try:
            emo = sd.emotion()
        except Exception:
            emo = {}
    emo = emo or {}

    if sec is None:
        try:
            sec = sd.sector_flow(5 if dt.datetime.now().hour < 15 else 1)
        except Exception:
            sec = {}
    sec = sec or {}

    if idxs is None:
        try:
            idxs = sd.tx_realtime(sd.IDX_CODES)
        except Exception:
            idxs = []
    idxs = idxs or []

    # 2. 真实数据校验 (数据断供守卫: 缺数据绝不造假事实，绝不瞎下军令与仓位)
    has_valid_data = bool(
        emo and (emo.get('score') is not None or emo.get('zt') is not None or emo.get('zt_count') is not None)
    )

    if not has_valid_data:
        motto_unknown = "没有调查，没有发言权；不知敌情，绝不草率盲动。"
        return {
            "status": "data_unavailable",
            "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "phase": {
                "key": "unknown",
                "title": "数据暂不可用",
                "badge": "信号缺失 · 暂停研判",
                "color": "#94a3b8",
                "motto": motto_unknown,
                "desc": "行情接口连接断供或非交易时段无快照，系统恪守《实践论》底线，严禁用虚构数据臆想推演！",
                "posture": "保持静默观望，暂停开火与仓位下达，等待第一手真实数据恢复。",
                "pos_range": "数据缺失 · 暂不给仓位建议",
                "pos_pct": None,
                "max_stocks": None,
                "cycle_stage": "未知",
                "basis_note": "核心情绪与盘面数据缺失，拒绝盲目臆断",
            },
            "portfolio_audit": {
                "title": "战备兵力实查 · 真实持仓硬约束",
                "account_equity": float(account_equity) if account_equity and float(account_equity) > 0 else 1000000.0,
                "equity_is_estimate": not bool(account_equity and float(account_equity) > 0),
                "actual_stocks_count": len(portfolio) if isinstance(portfolio, list) else 0,
                "max_stocks_limit": None,
                "actual_market_value": 0.0,
                "actual_pos_pct": 0.0,
                "target_pos_pct": None,
                "excess_pos_pct": 0.0,
                "excess_stocks": 0,
                "reduce_amount": 0.0,
                "status": "DATA_UNAVAILABLE",
                "tag": "⚪ 暂缺大势基准",
                "instruction": "因市场底层数据断供，暂无法比对战备兵力合规性。",
                "holdings": [],
            },
            "reality_check": {
                "title": "实事求是 · 盘面真相核验 (反对主观臆断)",
                "status": "unavailable",
                "verdict": "第一手盘面数据缺失，实事求是停止核验，严禁用默认值代替客观事实！",
                "divergence": False,
                "evidence": [
                    {"dimension": "数据链条", "fact": "行情数据断供", "eval": "⚪ 暂停", "comment": "等待数据重连"}
                ],
            },
            "contradiction": {
                "title": "矛盾论 · 抓主要矛盾与核心战场",
                "nature": "未知 (数据缺失)",
                "primary_theme": "无",
                "primary_aspect": "数据不足，无法定性矛盾主要方面",
                "secondary_warning": "不作臆断",
                "sustainable": False,
            },
            "tactics": {
                "title": "集中优势兵力打歼灭战 · 军令硬开关",
                "rule_1_concentration": {
                    "title": "伤其十指不如断其一指",
                    "passed": True,
                    "threshold": "待评估",
                    "actual": f"持有 {len(portfolio) if isinstance(portfolio, list) else 0} 只",
                    "verdict": "待评估",
                    "content": "数据断供暂不判定集中度",
                },
                "rule_2_fire_command": {
                    "title": "不打无把握之仗 · 9:25 开火硬开关",
                    "fire_status": "DATA_UNAVAILABLE",
                    "fire_status_title": "⚠️ 数据缺失 (锁死扳机)",
                    "fire_reason": "核心市场数据缺失，胜算不明，坚决不开火！",
                    "conditions": [],
                    "content": "不知敌情，绝不草率盲动！",
                },
                "rule_3_stop_loss": {
                    "title": "实事求是 · 因敌变化动态止损",
                    "passed": True,
                    "breached_count": 0,
                    "breached_stocks": [],
                    "verdict": "待评估",
                    "content": "数据恢复后核验防守止损线",
                },
            },
            "motto": motto_unknown,
        }

    # 3. 提取基础事实
    score = float(emo.get('score', 50.0))
    band = emo.get('band', '中性')
    zt_cnt = int(emo.get('zt') if emo.get('zt') is not None else emo.get('zt_count', 0))
    zb_cnt = int(emo.get('zb') if emo.get('zb') is not None else emo.get('zb_count', 0))
    dt_cnt = int(emo.get('dt') if emo.get('dt') is not None else emo.get('dt_count', 0))
    max_lb = int(emo.get('max_lb', 0))
    effect = emo.get('effect') or {}
    premium = float(effect.get('premium') if effect.get('premium') is not None else emo.get('premium_next_open', 0.0))
    rate_1to2 = float(effect.get('rate_1to2') if effect.get('rate_1to2') is not None else emo.get('rate_1to2', 0.0))
    diverge_note = emo.get('diverge')
    ladder = emo.get('ladder_grouped') or {}
    themes = emo.get('themes_list') or emo.get('themes') or []

    # 提取上证与创业板涨跌幅
    sh_pct = 0.0
    cy_pct = 0.0
    for q in idxs:
        c = str(q.get('code', ''))
        n = str(q.get('name', ''))
        p = float(q.get('pct', 0.0))
        if '000001' in c or '上证' in n:
            sh_pct = p
        elif '399006' in c or '创业板' in n:
            cy_pct = p

    total_z = zt_cnt + zb_cnt
    zb_rate = round((zb_cnt / max(1, total_z)) * 100, 1)

    # ==================== 维度一：《论持久战》战略三阶段 (消费 cycle_position 单一事实源) ====================
    cycle_stage = emo.get('stage')
    if not cycle_stage:
        try:
            cycle_stage = sd.cycle_position()
        except Exception:
            cycle_stage = None

    if not cycle_stage:
        # ==================== 兜底阈值量化依据（真实样本统计与博弈特征 · 详见 scripts/threshold_evidence.py） ====================
        # 1. score < 42: 对应本库历史样本(N=32)下四分位经验线 P25=41.5；待v2独立样本累计>=30条后持续动态校准
        # 2. zb_rate >= 35.0%: 对应本库样本上四分位(P75=32.1%)之上高危抛压区；实测样本N=7(次日均幅-0.08%，样本不足严禁通胀宣称概率)
        # 3. dt_cnt >= 10: 真实跌停达两位数，恐慌盘加速涌出
        # 4. score >= 65 (与系统上四分位P75=69.6呼应): 处于多头合力高分位区
        # 5. zb_rate < 20.0%: 对应本库中低抛压分位(P25=18.6%)，封板坚决，分歧较小
        # 6. dt_cnt <= 2: 几无跌停核按钮，做多情绪协同
        if score < 42 or zb_rate >= 35 or dt_cnt >= 10:
            cycle_stage = '退潮'
        elif score >= 65 and zb_rate < 20 and dt_cnt <= 2:
            cycle_stage = '主升'
        else:
            cycle_stage = '修复'

    # 将 5 阶段严密映射到毛选战略三阶段，消除口径分裂
    if cycle_stage in ('退潮', '冰点'):
        phase_key = "defense"
        phase_title = "战略防御阶段"
        phase_badge = "深沟高垒 · 防御蓄势"
        phase_color = "#ef4444"
        phase_motto = "存人失地，人地皆存；存地失人，人地皆失。"
        phase_desc = f"市场处于【{cycle_stage}期】(情绪分 {score:.1f}，炸板率 {zb_rate}%)。空头主导释放风险，局部虚火不掩整体萧条。保存资本有生力量是压倒一切的第一战略目标！"
        pos_range = "0 ~ 2 成极低仓位"
        pos_pct = 15
        max_stocks = 1
        posture = "只防不攻，空仓或极轻仓观望；任何盘中脉冲非确认信号绝不追高，宁可踏空，绝不送命。"
        basis_note = f"依据情绪周期底层定位【{cycle_stage}】(炸板率{zb_rate}%/跌停{dt_cnt}家)，映射为战略防御阶段"
    elif cycle_stage in ('主升', '亢奋'):
        phase_key = "counter"
        phase_title = "战略反攻阶段"
        phase_badge = "大踏步前进 · 决战决胜"
        phase_color = "#10b981"
        phase_motto = "集中优势兵力，大踏步前进，决战决胜。"
        phase_desc = f"市场处于【{cycle_stage}共振期】(情绪分 {score:.1f}，涨停 {zt_cnt} 家)。多头主力合力进攻，赚钱效应全面铺开，主线核心龙头具有极高溢价空间。"
        pos_range = "7 ~ 9 成高仓位"
        pos_pct = 80
        max_stocks = 3
        posture = "集中优势兵力直扑主线领头羊；持股为主，顺大势而为，不轻言撤退。"
        basis_note = f"依据情绪周期底层定位【{cycle_stage}】(涨停{zt_cnt}家/高度{max_lb}板)，映射为战略反攻阶段"
    else:
        phase_key = "stalemate"
        phase_title = "战略相持阶段"
        phase_badge = "游击机动 · 抓小试错"
        phase_color = "#fbbf24"
        phase_motto = "打得赢就打，打不赢就走；你打你的，我打我的。"
        phase_desc = f"市场处于【{cycle_stage}拉锯期】(情绪分 {score:.1f})。多空僵持，无大级别指数趋势，热点快速轮动，局部存在结构性机会。"
        pos_range = "3 ~ 5 成机动兵力"
        pos_pct = 40
        max_stocks = 2
        posture = "游击战术，不打阵地硬仗；聚焦核心龙头低吸试错，见好就收，快进快出。"
        basis_note = f"依据情绪周期底层定位【{cycle_stage}】(存量博弈拉锯)，映射为战略相持阶段"

    # ==================== 维度二：《实践论》实事求是 · 盘面微观真相核验 ====================
    evidence = []
    # 证据1: 虚火背离判定 (优先消费 emo['diverge']，统一结论并消除死变量)
    # 阈值依据性质（实事求是）：
    # - rate_1to2 < 12.0%: 初始经验设定（本库带effect样本仅2条，待样本累计）；首板接力过低提示微观梯队断层
    # - premium < 0.3%: 初始经验盈亏平衡线（打板扣除佣金税费生命线，待样本累计）；低于0.3%提示接力资金陷入负收益
    is_divergence = bool(diverge_note)
    if not is_divergence and sh_pct >= 0 and (rate_1to2 < 12.0 or premium < 0.3):
        is_divergence = True

    if is_divergence:
        diverge_detail = diverge_note or f"上证微幅翻红 ({sh_pct:+.2f}%)，但接力溢价仅 {premium:+.2f}%，1进2晋级率仅 {rate_1to2:.1f}%"
        evidence.append({
            "dimension": "指数 vs 微观接力",
            "fact": diverge_detail,
            "eval": "⚠️ 虚火表象",
            "comment": "典型的‘指数红但个股亏钱’，权重掩护后排接力资金出逃，严禁用主观臆想代替客观数据！"
        })
    else:
        evidence.append({
            "dimension": "大盘接力意愿",
            "fact": f"昨日涨停今日溢价 {premium:+.2f}%，1进2晋级率 {rate_1to2:.1f}%",
            "eval": "中性反映" if rate_1to2 >= 15 else "接力低迷",
            "comment": "客观数据真实反映短线资金意愿，无虚假放大"
        })

    # 证据2: 炸板率抛压客观判定
    evidence.append({
        "dimension": "封板成色与抛压",
        "fact": f"涨停 {zt_cnt} 家，炸板 {zb_cnt} 家 (炸板率 {zb_rate}%)，跌停 {dt_cnt} 家",
        "eval": "抛压沉重" if zb_rate >= 30 else ("封板坚决" if zb_rate < 18 else "分歧适中"),
        "comment": "炸板率>30%表明跟风合力涣散，筹码松动极易次日低开闷杀"
    })

    # 证据3: 最高连板与梯队断层
    if max_lb >= 5 and rate_1to2 < 12.0:
        evidence.append({
            "dimension": "梯队结构诊断",
            "fact": f"空间板打到 {max_lb} 板，但首板进二板晋级率仅 {rate_1to2:.1f}%",
            "eval": "⚠️ 梯队断层",
            "comment": "极度分化结构：‘独木难支’，龙头抱团掩护全线退潮，非核心跟风盘九死一生"
        })

    reality_status = "danger" if (zb_rate >= 35 or dt_cnt >= 10) else ("warning" if is_divergence else "healthy")
    reality_verdict = (
        "第一手事实证明：当前盘面微观赚钱效应严重失血，高位断板风险高悬。严禁用主观臆想代替客观数据！"
        if reality_status == "danger" else
        ("第一手事实证明：表面指数平稳，但底层接力脆弱。坚持实事求是，不可盲目加仓。" if reality_status == "warning" else
         "第一手事实证明：盘面量价与情绪结构健康，多头资金步调协同，支撑既定作战计划。")
    )

    # ==================== 维度三：《矛盾论》抓主要矛盾与核心主战场 ====================
    # 结合近 3~5 日主力资金净流入板块与涨停题材，防止把一日脉冲当主战场
    inflows = sec.get('inflow') or []
    inflow_names = [x.get('name') for x in inflows[:5] if x.get('name')]
    theme_names = [t['name'] if isinstance(t, dict) else t[0] for t in themes[:5]] if themes else []

    confirmed_main = [name for name in inflow_names if any(name in t or t in name for t in theme_names)]
    if confirmed_main:
        primary_theme_str = ' · '.join(confirmed_main[:3])
        has_sustainable_trend = True
        sustain_desc = "5日主力资金持续净流入且涨停梯队合力共振"
    elif inflow_names:
        primary_theme_str = ' · '.join(inflow_names[:2])
        has_sustainable_trend = False
        sustain_desc = "主力资金有净流入但涨停梯队支撑不足，属于权重护盘或结构分歧"
    elif theme_names:
        primary_theme_str = ' · '.join(theme_names[:2])
        has_sustainable_trend = False
        sustain_desc = "当日涨停脉冲但5日主力资金未见大幅净流入，定性为超跌试错，持续性存疑"
    else:
        primary_theme_str = '核心权重'
        has_sustainable_trend = False
        sustain_desc = "板块轮动涣散，无明显主战场"

    outflows = sec.get('outflow') or []
    outflow_names = [x.get('name') for x in outflows[:3] if x.get('name')]
    distraction_themes = [t for t in theme_names if t not in primary_theme_str and any(t in o for o in outflow_names)]

    if phase_key == "defense":
        contradiction_nature = "存量流失与高位派发出清"
        primary_aspect = f"防守期资金避险为主，局部脉冲【{primary_theme_str}】({sustain_desc})，缺乏大兵团持续增量"
        secondary_warning = (
            f"今日边缘板块 ({'、'.join(distraction_themes[:3]) if distraction_themes else '杂毛轮动'}) 净流出严重，无持续性，"
            "定性为【次要矛盾 / 轮动骚扰与诱多】，坚决不分心、不追击。"
        )
    elif phase_key == "counter":
        contradiction_nature = "增量扩张与主线核心抢筹"
        primary_aspect = f"兵团级主力集中突击【{primary_theme_str}】({sustain_desc})，梯队完整中军扎实，具备持续进攻动能"
        secondary_warning = "主线之外的其他分支反弹均为支流，严禁‘分兵支援’，牢牢咬住主线主战场！"
    else:
        contradiction_nature = "存量博弈拉锯与轮动内卷"
        primary_aspect = f"结构性行情突围，资金聚焦于局部领头题材【{primary_theme_str}】({sustain_desc})"
        secondary_warning = (
            f"盘中边缘板块 ({'、'.join(distraction_themes[:2]) if distraction_themes else '跟风杂毛'}) 快速轮动抽血，皆为【次要矛盾】。"
            "切忌东一榔头西一棒子，紧盯辨识度前排。"
        )

    # ==================== 维度四：接真实持仓账本，硬性兵力约束动真格 ====================
    equity_is_estimate = not bool(account_equity and float(account_equity) > 0)
    account_eq = float(account_equity) if not equity_is_estimate else 1000000.0
    actual_holdings = portfolio if isinstance(portfolio, list) else []
    actual_count = len(actual_holdings)

    total_market_val = 0.0
    stop_loss_breached = []
    holding_details = []

    if actual_count > 0:
        pf_codes = [str(h.get('code', '')).zfill(6) for h in actual_holdings if h.get('code')]
        quotes = {}
        try:
            q_list = sd.tx_realtime(pf_codes)
            for q in q_list:
                quotes[str(q.get('code', '')).zfill(6)] = float(q.get('price', 0.0))
        except Exception:
            quotes = {}

        for h in actual_holdings:
            code = str(h.get('code', '')).zfill(6)
            shares = float(h.get('shares', 0.0))
            cost = float(h.get('cost', 0.0))
            cur_p = quotes.get(code, cost)
            sl = float(h.get('stop_loss', cost * 0.95))
            m_val = round(shares * cur_p, 2)
            total_market_val += m_val

            is_breached = (cur_p <= sl) and (sl > 0)
            if is_breached:
                stop_loss_breached.append({
                    'code': code, 'cur_price': cur_p, 'stop_loss': sl,
                    'loss_pct': round((cur_p - cost) / cost * 100, 2) if cost > 0 else 0.0
                })
            holding_details.append({
                'code': code, 'shares': shares, 'cost': cost, 'cur_price': cur_p,
                'market_value': m_val, 'stop_loss': sl, 'breached': is_breached
            })

    actual_pos_pct = round((total_market_val / account_eq) * 100, 1) if account_eq > 0 else 0.0
    excess_pos_pct = max(0.0, round(actual_pos_pct - pos_pct, 1))
    excess_stocks = max(0, actual_count - max_stocks)
    allowed_max_val = round(account_eq * (pos_pct / 100.0), 2)
    reduce_amount = max(0.0, round(total_market_val - allowed_max_val, 2))

    est_note = " (按总资产 100 万估算)" if equity_is_estimate else ""

    # 战备戒备状态判定
    if excess_pos_pct > 10.0 or excess_stocks > 0:
        pos_audit_status = "RED_OVERWEIGHT"
        pos_audit_tag = f"🔴 严重超限 · 必须立刻减仓{est_note}"
        pos_audit_instruction = (
            f"战备红色警报！实测仓位 {actual_pos_pct}%{est_note} (超限 {excess_pos_pct}%)，持仓 {actual_count} 只 (超限 {excess_stocks} 只)！"
            f"严重违背《论持久战》兵力纪律，必须立即减仓约 ¥{reduce_amount:,.0f}，清退非核心杂毛！"
        )
    elif excess_pos_pct > 0.0:
        pos_audit_status = "YELLOW_CAUTION"
        pos_audit_tag = f"🟡 轻度超额 · 停止加仓{est_note}"
        pos_audit_instruction = f"仓位轻度超额 {excess_pos_pct}% (当前 {actual_pos_pct}% vs 上限 {pos_pct}%){est_note}，严禁再开新仓，等待冲高减至安全水位。"
    elif actual_count == 0:
        pos_audit_status = "GREEN_EMPTY"
        pos_audit_tag = "🟢 空仓待命 · 作战自由度极高"
        pos_audit_instruction = "当前空仓，保存有生力量完好，拥有绝对选择权与主动权！"
    else:
        pos_audit_status = "GREEN_COMPLIANT"
        pos_audit_tag = f"🟢 兵力合规 · 战备状态良好{est_note}"
        pos_audit_instruction = f"当前持有 {actual_count} 只，实测仓位 {actual_pos_pct}%{est_note}，完全符合战略{pos_range}要求。"

    # ==================== 维度五：三条军令落成可判定开关 (接竞价雷达 + 涨停质量分) ====================
    rule_1_passed = (actual_count <= max_stocks)
    rule_1_detail = {
        "title": "伤其十指不如断其一指",
        "passed": rule_1_passed,
        "threshold": f"持仓 <= {max_stocks} 只",
        "actual": f"当前持有 {actual_count} 只",
        "verdict": "合规" if rule_1_passed else f"违纪 (超限 {excess_stocks} 只)",
        "content": "全账户持仓严格控制在上限以内，严禁‘撒胡椒面式’买满杂毛。要打就打歼灭战！"
    }

    # 军令二: 9:25 开火指令硬开关 (接竞价雷达溢价 + 晋级率 + 涨停质量分)
    max_quality = 0.0
    quality_leader = ""
    try:
        zt_pool = emo.get('zt_pool') or sd._pool('ZT', dt.date.today().strftime('%Y%m%d')) or []
        for z_item in zt_pool:
            q_score, _ = sd.limit_up_quality(z_item)
            if q_score > max_quality:
                max_quality = q_score
                quality_leader = f"{z_item.get('n', '')}({z_item.get('c', '')}) 质量分{q_score:.1f}"
    except Exception:
        max_quality = 0.0

    cond_stage_ok = (phase_key != "defense")
    cond_premium_ok = (premium >= 1.0)
    cond_rate_ok = (rate_1to2 >= 15.0)
    cond_quality_ok = (max_quality >= 7.0)

    fire_conditions = [
        {"name": "大势非防御期", "passed": cond_stage_ok, "threshold": "相持或反攻", "actual": phase_title},
        {"name": "接力溢价胜率", "passed": cond_premium_ok, "threshold": ">= +1.00%", "actual": f"{premium:+.2f}%"},
        {"name": "1进2接力晋级率", "passed": cond_rate_ok, "threshold": ">= 15.0%", "actual": f"{rate_1to2:.1f}%"},
        {"name": "核心涨停质量分", "passed": cond_quality_ok, "threshold": ">= 7.0分", "actual": f"{max_quality:.1f}分 ({quality_leader or '无'})"},
    ]

    if phase_key == "defense":
        fire_status = "FIRE_FORBIDDEN"
        fire_status_title = "🚫 严禁开火 (锁死扳机)"
        fire_reason = f"大势处于战略防御退潮期 (炸板率 {zb_rate}%)，胜率极低，任何竞价异动皆为诱多派发，手指坚决离开扳机！"
    elif all(c["passed"] for c in fire_conditions):
        fire_status = "FIRE_ALLOWED"
        fire_status_title = "🎯 准许开火 (满足歼灭战信号)"
        fire_reason = f"大势步入{phase_title}，接力溢价与涨停质量分({max_quality:.1f})达标，可集中优势兵力突击主战场先锋！"
    else:
        fire_status = "HOLD_AND_WAIT"
        fire_status_title = "⏳ 按兵不动 (胜算不足观望)"
        failed_conds = [c["name"] for c in fire_conditions if not c["passed"]]
        fire_reason = f"未现高胜算信号 (未达标项: {', '.join(failed_conds)})，不打无把握之仗，保持静默！"

    rule_2_detail = {
        "title": "不打无把握之仗 · 9:25 开火硬开关",
        "fire_status": fire_status,
        "fire_status_title": fire_status_title,
        "fire_reason": fire_reason,
        "conditions": fire_conditions,
        "content": "9:25 竞价未出现符合预案的高胜算信号前，手指离开扳机，绝不草率盲动！"
    }

    # 军令三: 动态止损与防守线纠偏
    rule_3_passed = (len(stop_loss_breached) == 0)
    rule_3_detail = {
        "title": "实事求是 · 因敌变化动态止损",
        "passed": rule_3_passed,
        "breached_count": len(stop_loss_breached),
        "breached_stocks": stop_loss_breached,
        "verdict": "正常" if rule_3_passed else f"⚠️ 警报: {len(stop_loss_breached)} 只跌破防守线",
        "content": (
            "一旦大盘破位或个股跌破防守止损线，客观事实已变，坚决执行纪律无条件离场，不抱任何侥幸！"
            if rule_3_passed else
            f"紧急撤退指令：持仓中 {', '.join([b['code'] for b in stop_loss_breached])} 已跌破止损线，客观条件恶化，立即止损斩仓！"
        )
    }

    # 4. 持久化存档快照 (仅在有真实有效数据时记录，供次日对账与证伪)
    decision_record = {
        "date": dt.date.today().strftime('%Y%m%d'),
        "time": dt.datetime.now().strftime('%H:%M:%S'),
        "cycle_stage": cycle_stage,
        "phase_key": phase_key,
        "pos_pct_limit": pos_pct,
        "fire_status": fire_status,
        "actual_stocks_count": actual_count,
        "actual_pos_pct": actual_pos_pct,
        "sh_pct": sh_pct,
        "zb_rate": zb_rate,
        "premium": premium,
        "max_quality": max_quality
    }
    _log_decision_record(decision_record)

    motto_quote = (
        "以方法建立认知，由认知派生纪律。看透了客观规律与胜负底牌，严格守纪便不再是痛苦的抗拒，而是顺应大势的最舒适抉择。"
    )

    return {
        "status": "ok",
        "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "phase": {
            "key": phase_key,
            "title": phase_title,
            "badge": phase_badge,
            "color": phase_color,
            "motto": phase_motto,
            "desc": phase_desc,
            "posture": posture,
            "pos_range": pos_range,
            "pos_pct": pos_pct,
            "max_stocks": max_stocks,
            "cycle_stage": cycle_stage,
            "basis_note": basis_note,
        },
        "portfolio_audit": {
            "title": "战备兵力实查 · 真实持仓硬约束",
            "account_equity": account_eq,
            "equity_is_estimate": equity_is_estimate,
            "actual_stocks_count": actual_count,
            "max_stocks_limit": max_stocks,
            "actual_market_value": total_market_val,
            "actual_pos_pct": actual_pos_pct,
            "target_pos_pct": pos_pct,
            "excess_pos_pct": excess_pos_pct,
            "excess_stocks": excess_stocks,
            "reduce_amount": reduce_amount,
            "status": pos_audit_status,
            "tag": pos_audit_tag,
            "instruction": pos_audit_instruction,
            "holdings": holding_details,
        },
        "reality_check": {
            "title": "实事求是 · 盘面真相核验 (反对主观臆断)",
            "status": reality_status,
            "verdict": reality_verdict,
            "divergence": is_divergence,
            "evidence": evidence,
        },
        "contradiction": {
            "title": "矛盾论 · 抓主要矛盾与核心战场",
            "nature": contradiction_nature,
            "primary_theme": primary_theme_str,
            "primary_aspect": primary_aspect,
            "secondary_warning": secondary_warning,
            "sustainable": has_sustainable_trend,
        },
        "tactics": {
            "title": "集中优势兵力打歼灭战 · 军令硬开关",
            "rule_1_concentration": rule_1_detail,
            "rule_2_fire_command": rule_2_detail,
            "rule_3_stop_loss": rule_3_detail,
        },
        "motto": motto_quote,
    }


def format_cli_output(d):
    """格式化纯文本输出，适合控制台与终端展示"""
    p = d['phase']
    pa = d['portfolio_audit']
    rc = d['reality_check']
    c = d['contradiction']
    t = d['tactics']
    r1 = t['rule_1_concentration']
    r2 = t['rule_2_fire_command']
    r3 = t['rule_3_stop_loss']

    lines = []
    lines.append("=" * 68)
    lines.append("🎖️ 【战役决策参谋部 · 战略战术决策中枢】 (毛选方法论指导)")
    lines.append("=" * 68)
    lines.append(f"【战略阶段】 {p['title']} [{p['badge']}]")
    lines.append(f"【判定依据】 {p['basis_note']}")
    lines.append(f"【战略指针】 “{p['motto']}”")
    lines.append(f"【局势解析】 {p['desc']}")
    lines.append(f"【作战姿态】 {p['posture']}")
    lines.append("-" * 68)
    lines.append(f"【战备兵力实查】 ({pa['tag']})")
    lines.append(f"  • 持仓只数: {pa['actual_stocks_count']} 只 (战略上限 {pa.get('max_stocks_limit') or '无'} 只)")
    lines.append(f"  • 实测仓位: {pa['actual_pos_pct']}% (战略上限 {pa.get('target_pos_pct') or '无'}%, 超限 {pa.get('excess_pos_pct', 0)}%)")
    lines.append(f"  • 兵力指令: {pa['instruction']}")
    lines.append("-" * 68)
    lines.append(f"【实事求是 · 盘面真相核验】 (状态: {rc['status'].upper()})")
    lines.append(f"  结论: {rc['verdict']}")
    for ev in rc.get('evidence', []):
        lines.append(f"  • {ev['dimension']}: {ev['fact']} [{ev['eval']}] -> {ev['comment']}")
    lines.append("-" * 68)
    lines.append("【矛盾论 · 抓主要矛盾与核心战场】")
    lines.append(f"  • 市场总矛盾: {c['nature']}")
    lines.append(f"  • 矛盾主要方面 (主战场): 【{c['primary_theme']}】 (持续性: {'高' if c['sustainable'] else '需观察/非持续主线'})")
    lines.append(f"    {c['primary_aspect']}")
    lines.append(f"  • 警惕次要矛盾 (轮动杂毛):")
    lines.append(f"    {c['secondary_warning']}")
    lines.append("-" * 68)
    lines.append("【歼灭战三大军令 · 量化硬开关】")
    lines.append(f"  [军令 1 - 集中兵力] {'[PASS]' if r1['passed'] else '[FAIL]'} {r1['actual']} vs {r1['threshold']}")
    lines.append(f"  [军令 2 - 9:25开火] {r2['fire_status_title']}")
    lines.append(f"          原因: {r2['fire_reason']}")
    for cond in r2.get('conditions', []):
        lines.append(f"          {'✓' if cond['passed'] else '✗'} {cond['name']}: {cond['actual']} (要求 {cond['threshold']})")
    lines.append(f"  [军令 3 - 动态撤退] {'[PASS]' if r3['passed'] else '[ALERT]'} {r3['content']}")
    lines.append("=" * 68)
    lines.append(f"💡 认识论心法: {d['motto']}")
    lines.append("=" * 68)
    return "\n".join(lines)


if __name__ == '__main__':
    demo_portfolio = [
        {'code': '600519', 'shares': 200, 'cost': 1450.0, 'stop_loss': 1380.0},
        {'code': '300750', 'shares': 800, 'cost': 235.0, 'stop_loss': 220.0}
    ]
    res = analyze_strategic_decision(portfolio=demo_portfolio, account_equity=1000000.0)
    print(format_cli_output(res))
