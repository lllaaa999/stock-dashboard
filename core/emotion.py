# -*- coding: utf-8 -*-
"""
情绪指数核心算力引擎 (Core Market Sentiment Engine)
不包含任何网络请求或文件 I/O，属于纯算法根据地。
包含：情绪打分公式（v1基础版/v2去饱和与赚钱效应加权版）、情绪区间映射与背离判别。
"""
import math
from typing import Dict, Any, Tuple, Optional


def emotion_band(s: float) -> str:
    """情绪区间文字映射: 冰点 / 退潮/偏冷 / 中性 / 活跃 / 亢奋"""
    return ('冰点' if s < 30 else '退潮/偏冷' if s < 50 else '中性' if s < 70 else '活跃' if s < 85 else '亢奋')


# 兼容旧命名
_emotion_band = emotion_band


def emotion_score_v1(n_zt: int, n_zb: int, n_dt: int, max_lb: int) -> float:
    """旧公式(0-100): 基准10 + 广度30 + 高度25 + 封板质量20 - 跌停惩罚15。仅作对照留档。"""
    s = 10.0
    s += min(n_zt / 80.0, 1.0) * 30.0
    s += min(max_lb / 8.0, 1.0) * 25.0
    s += (1.0 - n_zb / (n_zt + n_zb)) * 20.0 if (n_zt + n_zb) else 10.0
    s -= min(n_dt / 15.0, 1.0) * 15.0
    return max(0.0, min(100.0, s))


_emotion_score_v1 = emotion_score_v1


def emotion_score_v2(n_zt: int, n_zb: int, n_dt: int, max_lb: int, eff: Dict[str, Any]) -> Tuple[float, Optional[str]]:
    """新公式(0-100): 基准10 + 广度18(平方根去饱和) + 高度17(平方根) + 封板质量12
    + 赚钱效应25 + 跌停惩罚15。
    赚钱效应 = 0.6*溢价分 + 0.4*晋级分; 溢价分 = clamp(昨日涨停今均涨跌, -5%, +5%) 归一化;
    晋级分 = min(1进2晋级率/50, 1)。取不到该指标时按中性 12.5 分计入(并标注).
    返回 (score, diverge)。diverge: score_high_effect_weak / score_low_effect_strong / None
    """
    s = 10.0
    s += math.sqrt(min(n_zt / 120.0, 1.0)) * 18.0
    s += math.sqrt(min(max_lb / 8.0, 1.0)) * 17.0
    s += ((1.0 - n_zb / (n_zt + n_zb)) * 12.0 if (n_zt + n_zb) else 6.0)
    s += ((eff.get('score') or 0.0) * 25.0) if eff.get('available') else 12.5
    s -= min(n_dt / 15.0, 1.0) * 15.0
    s = max(0.0, min(100.0, s))
    
    diverge = None
    if eff.get('available'):
        prem = float(eff.get('premium') if eff.get('premium') is not None else 0.0)
        # rate_1to2 在休市/非相邻交易日为 None（晋级率不可计算）。
        # 旧写法 float(eff.get('rate_1to2', 0.0)) 只处理"键缺失"，不处理"值为 None"，
        # 直接 float(None) 抛 TypeError，导致整条情绪计算失败、页面 emotion 变空对象。
        _r = eff.get('rate_1to2')
        rate_known = _r is not None
        rate = float(_r) if rate_known else 0.0
        eff_sc = float(eff.get('score') if eff.get('score') is not None else 0.5)
        # 情绪分偏高但赚钱效应偏弱: 表面高(s>=50)，但接力资金亏损(prem<0)或综合赚钱效应不及中性且梯队失血(eff_sc<0.5 且 rate<20)
        # 避免溢价高达+2.6%且超强接力时因晋级率24.2%被硬编码rate<25误杀
        # 注：rate 未知时不参与"梯队失血"判定，避免用 0.0 冒充真实值造成误判背离
        if s >= 50 and (prem < 0
                        or (rate_known and eff_sc < 0.5 and rate < 20)
                        or (rate_known and prem < 0.8 and rate < 25)):
            diverge = 'score_high_effect_weak'
        elif s < 50 and ((rate_known and prem > 3.0 and rate > 50.0)
                         or (eff_sc >= 0.65 and prem >= 2.0)):
            diverge = 'score_low_effect_strong'
    return s, diverge


_emotion_score_v2 = emotion_score_v2


def effect_flat(eff: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """存档用扁平化(不写嵌套, 便于日后回测)

    注意: eff 中 premium / rate_1to2 / score 均可能为 None（休市日、
    晋级率不可计算等场景）。get(k, default) 的 default 只在键缺失时生效，
    值为 None 时仍返回 None，直接参与算术会抛 TypeError。
    故此处统一用 `(x if x is not None else 默认值)` 兜底。
    """
    if not eff.get('available'):
        return None
    _sc = eff.get('score')
    return dict(
        premium=eff.get('premium'),
        rate_1to2=eff.get('rate_1to2'),
        effect_score=round((_sc if _sc is not None else 0.0) * 25, 2),
        y_date=eff.get('y_date'),
        tag=eff.get('tag'),
        # 前端需要区分"晋级率=0(真的没人晋级)"与"晋级率不可用(休市/非相邻交易日)"，
        # 否则 None 会被拼成 "null%" 或误判成 0%。
        rate_available=(eff.get('rate_1to2') is not None),
        preview=bool(eff.get('preview')),
    )


_effect_flat = effect_flat
