#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
战略战术决策中枢 (Strategic Decision Engine)
基于《毛泽东选集》底层认识论与决策方法论：
  1. 《论持久战》—— 战略阶段与大势定位 (防御 / 相持 / 反攻)
  2. 《实践论 / 反对本本主义》—— 实事求是 · 盘面微观真相核验 (反对主观脑补)
  3. 《矛盾论》—— 抓主要矛盾与核心战场 (主攻主流 / 摒弃杂毛)
  4. 《战略问题》—— 集中优势兵力打歼灭战 (仓位军令与开火纪律)
"""
import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stock_dashboard as sd

def analyze_strategic_decision(emo=None, sec=None, idxs=None):
    """
    基于第一手客观数据生成战略战术决策中枢报告
    """
    if emo is None:
        try:
            emo = sd.emotion()
        except Exception:
            emo = {}
    if sec is None:
        try:
            sec = sd.sector_flow(1)
        except Exception:
            sec = {}
    if idxs is None:
        try:
            idxs = sd.tx_realtime(sd.IDX_CODES)
        except Exception:
            idxs = []

    # 1. 提取基础事实 (兼顾 zt/zt_count, zb/zb_count, dt/dt_count 等各种字典结构)
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

    # 计算炸板率
    total_z = zt_cnt + zb_cnt
    zb_rate = round((zb_cnt / max(1, total_z)) * 100, 1)

    # 提取上证与创业板涨跌幅
    sh_pct = 0.0
    cy_pct = 0.0
    for q in idxs:
        c = q.get('code', '')
        if '000001' in c:
            sh_pct = float(q.get('pct', 0.0))
        elif '399006' in c:
            cy_pct = float(q.get('pct', 0.0))

    # ==================== 维度一：《论持久战》战略阶段定位 ====================
    # 结合情绪得分、炸板率、跌停数以及周期位置
    if score < 42 or dt_cnt >= 10 or zb_rate >= 35:
        phase_key = "defense"
        phase_title = "战略防御阶段"
        phase_badge = "深沟高垒 · 防御蓄势"
        phase_color = "#ef4444"
        phase_motto = "存人失地，人地皆存；存地失人，人地皆失。"
        phase_desc = "市场处于退潮派发或冰点筑底期。空头主导释放风险，局部虚火不掩整体萧条。此时保存资本有生力量是压倒一切的第一战略目标！"
        pos_range = "0 ~ 2 成极低仓位"
        pos_pct = 15
        posture = "只防不攻，空仓观望；任何盘中脉冲非确认信号绝不追高，宁可踏空，绝不送命。"
    elif score >= 68 and dt_cnt <= 3 and zb_rate < 20:
        phase_key = "counter"
        phase_title = "战略反攻阶段"
        phase_badge = "大踏步前进 · 决战决胜"
        phase_color = "#10b981"
        phase_motto = "集中优势兵力，大踏步前进，决战决胜。"
        phase_desc = "市场处于主升共振期或良性扩张期。多头主力形成合力共振，赚钱效应全面铺开，主线核心龙头具有极高溢价空间。"
        pos_range = "7 ~ 9 成高仓位"
        pos_pct = 80
        posture = "集中优势兵力直扑主线领头羊；持股为主，梯队轮动，顺大势而为，不轻言撤退。"
    else:
        phase_key = "stalemate"
        phase_title = "战略相持阶段"
        phase_badge = "游击机动 · 抓小试错"
        phase_color = "#fbbf24"
        phase_motto = "打得赢就打，打不赢就走；你打你的，我打我的。"
        phase_desc = "市场处于修复震荡或存量博弈拉锯期。多空僵持，无大级别趋势，热点轮动极快，互掏口袋。"
        pos_range = "3 ~ 5 成机动兵力"
        pos_pct = 40
        posture = "游击战术，不打阵地硬仗；聚焦核心做T，低吸潜伏，见好就收，快进快出。"

    # ==================== 维度二：《实践论》实事求是 · 盘面真相核验 ====================
    evidence = []
    # 证据1: 指数与微观赚钱效应背离
    is_divergence = False
    if sh_pct >= 0 and (rate_1to2 < 15 or premium < 0.5):
        is_divergence = True
        evidence.append({
            "dimension": "指数 vs 微观接力",
            "fact": f"上证微幅翻红 ({sh_pct:+.2f}%)，但接力溢价仅 {premium:+.2f}%，1进2晋级率仅 {rate_1to2:.1f}%",
            "eval": "⚠️ 虚火表象",
            "comment": "典型的‘只赚指数不赚钱’，权重掩护后排接力资金出逃，严防主观脑补追高"
        })
    elif sh_pct < 0 and rate_1to2 > 25 and premium > 2.0:
        evidence.append({
            "dimension": "指数 vs 局部战火",
            "fact": f"上证虽绿 ({sh_pct:+.2f}%)，但接力溢价达 {premium:+.2f}%，晋级率达 {rate_1to2:.1f}%",
            "eval": "🔥 暗流涌动",
            "comment": "指数压盘洗盘，局部题材独立走强，资金正在开辟新根据地"
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
    if max_lb >= 5 and rate_1to2 < 12:
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

    # ==================== 维度三：《矛盾论》抓主要矛盾与主战场 ====================
    # 提取主力流入板块与题材梯队
    inflows = sec.get('inflow') or []
    outflows = sec.get('outflow') or []

    top_themes = [t['name'] if isinstance(t, dict) else t[0] for t in themes[:3]] if themes else []
    top_inflow_name = inflows[0]['name'] if inflows else '核心资产'
    top_inflow_val = inflows[0]['flow'] if inflows else 0.0

    primary_theme_str = ' · '.join(top_themes) if top_themes else top_inflow_name
    
    # 定性主要矛盾性质
    if phase_key == "defense":
        contradiction_nature = "存量流失与高位派发出清"
        primary_aspect = "多头主力被动收缩，各路资金抢跑兑现避险"
        secondary_warning = "今日边缘板块脉冲仅为超跌抽风或主力护盘遮羞布，无增量持续性，定性为【次要矛盾 / 轮动骚扰】，坚决不分心、不追击。"
    elif phase_key == "counter":
        contradiction_nature = "增量扩张与主线核心抢筹"
        primary_aspect = f"兵团级主力集中突击【{primary_theme_str}】，梯队完整中军扎实"
        secondary_warning = "主线之外的其他分支反弹均为支流，严禁‘分兵支援’，牢牢咬住主线主战场！"
    else:
        contradiction_nature = "存量博弈拉锯与轮动内卷"
        primary_aspect = f"结构性行情突围，资金聚焦于局部领头题材【{primary_theme_str}】"
        secondary_warning = f"盘中多板块快速轮动抽血，皆为【次要矛盾】。切忌东一榔头西一棒子，紧盯核心中军与辨识度前排。"

    # ==================== 维度四：《战略问题》集中优势兵力与作战军令 ====================
    tactics = {
        "title": "集中优势兵力打歼灭战",
        "position_guide": pos_range,
        "position_pct": pos_pct,
        "rule_1_concentration": "伤其十指不如断其一指：全账户持仓严格控制在 2~3 只以内，严禁‘撒胡椒面式’买满杂毛。没有胜算绝不出手，要打就打歼灭战！",
        "rule_2_preparation": "不打无把握之仗，不打无准备之仗：9:25 集合竞价未出现符合预案的高胜算信号前，手指离开扳机，绝不草率盲动！",
        "rule_3_adaptability": "实事求是，因敌变化而取胜：一旦大盘跌破防守线或核心龙头断板爆头，客观条件已变，立即执行纪律，不抱任何侥幸！"
    }

    motto_quote = (
        "以方法建立认知，由认知派生纪律。看透了客观规律与胜负底牌，严格守纪便不再是痛苦的抗拒，而是顺应大势的最舒适抉择。"
    )

    return {
        "status": "ok",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
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
        },
        "reality_check": {
            "title": "实事求是 · 盘面真相核验 (反对主观臆断)",
            "status": reality_status,
            "verdict": reality_verdict,
            "evidence": evidence,
        },
        "contradiction": {
            "title": "矛盾论 · 抓主要矛盾与核心战场",
            "nature": contradiction_nature,
            "primary_theme": primary_theme_str,
            "primary_aspect": primary_aspect,
            "secondary_warning": secondary_warning,
        },
        "tactics": tactics,
        "motto": motto_quote,
    }


def format_cli_output(d):
    """格式化纯文本输出，适合控制台与终端展示"""
    p = d['phase']
    rc = d['reality_check']
    c = d['contradiction']
    t = d['tactics']
    lines = []
    lines.append("=" * 66)
    lines.append("🎖️ 【战役决策参谋部 · 战略战术决策中枢】 (毛选方法论指导)")
    lines.append("=" * 66)
    lines.append(f"【战略阶段】 {p['title']} [{p['badge']}]")
    lines.append(f"【战略指针】 “{p['motto']}”")
    lines.append(f"【局势解析】 {p['desc']}")
    lines.append(f"【作战姿态】 {p['posture']}")
    lines.append("-" * 66)
    lines.append(f"【实事求是 · 盘面真相核验】 (状态: {rc['status'].upper()})")
    lines.append(f"  结论: {rc['verdict']}")
    for ev in rc['evidence']:
        lines.append(f"  • {ev['dimension']}: {ev['fact']} [{ev['eval']}] -> {ev['comment']}")
    lines.append("-" * 66)
    lines.append("【矛盾论 · 抓主要矛盾与核心战场】")
    lines.append(f"  • 市场总矛盾: {c['nature']}")
    lines.append(f"  • 矛盾主要方面 (主战场): 【{c['primary_theme']}】")
    lines.append(f"    {c['primary_aspect']}")
    lines.append(f"  • 警惕次要矛盾 (轮动杂毛):")
    lines.append(f"    {c['secondary_warning']}")
    lines.append("-" * 66)
    lines.append("【集中优势兵力 · 战术兵力指引】")
    lines.append(f"  • 建议兵力仓位: {t['position_guide']} ({t['position_pct']}%)")
    lines.append(f"  • 兵力集中度法则: {t['rule_1_concentration']}")
    lines.append(f"  • 战役准备法则: {t['rule_2_preparation']}")
    lines.append(f"  • 动态纠偏法则: {t['rule_3_adaptability']}")
    lines.append("=" * 66)
    lines.append(f"💡 认识论心法: {d['motto']}")
    lines.append("=" * 66)
    return "\n".join(lines)


if __name__ == '__main__':
    res = analyze_strategic_decision()
    print(format_cli_output(res))
