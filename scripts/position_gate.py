# -*- coding: utf-8 -*-
"""
position_gate.py —— 大盘趋势仓位闸门 (Market Regime Position Gate)

设计来源 / 借鉴
--------------------------------------------------------------------------
借鉴 KHunter 的「当日仓位上限（大盘 ADX 判定）」思路，并做了适配：

  ADX > 25 且上升                                  -> 允许 100%（趋势明确，可满仓）
  ADX < 18 且上升 且 收盘 > MA20                   -> 允许 50%（趋势酝酿，半仓试探）
  其他                                             -> 允许 0%（震荡/下跌，不开新仓）

核心思想是「**默认不开仓**」：只有当大盘趋势被证明确认时才放行，
而不是「信号来了就买」。这与本项目原有的情绪周期仓位建议**取较小值**，
形成双重保险：

    最终仓位 = min(情绪周期建议, 大盘趋势闸门)

为什么需要这一层
--------------------------------------------------------------------------
原项目 strategic_decision.py 的仓位建议只来自「情绪周期」（主升 80% / 相持 40%
/ 退潮 15%）。但情绪周期是**短线赚钱效应**的度量，与大盘趋势可能背离：
情绪分很高但指数在下跌趋势中，此时满仓的风险远大于收益。
ADX 衡量的是趋势强度，两者是正交维度，取小能显著降低回撤。

ADX 计算（Wilder 标准算法）
--------------------------------------------------------------------------
  TR  = max(H-L, |H-Cprev|, |L-Cprev|)
  +DM = H-Hprev if (H-Hprev) > (Lprev-L) and > 0 else 0
  -DM = Lprev-L if (Lprev-L) > (H-Hprev) and > 0 else 0
  Wilder 平滑（period=14）:
      ATR_t  = (ATR_{t-1} * (n-1) + TR_t) / n
      +DI    = 100 * smoothed(+DM) / ATR
      -DI    = 100 * smoothed(-DM) / ATR
      DX     = 100 * |+DI - -DI| / (+DI + -DI)
      ADX    = Wilder 平滑后的 DX
"""

import math
from typing import List, Any, Dict, Optional

ADX_PERIOD = 14
ADX_STRONG = 25.0      # 强趋势阈值
ADX_WEAK = 18.0        # 趋势酝酿阈值
MA_TREND = 20          # 趋势确认用均线


def _wilders_smooth(values: List[float], n: int) -> List[Optional[float]]:
    """Wilder 平滑（RMA）：首值用前 n 个的简单平均，其后递推"""
    out: List[Optional[float]] = [None] * len(values)
    if len(values) < n:
        return out
    first = sum(values[:n]) / n
    out[n - 1] = first
    prev = first
    for i in range(n, len(values)):
        prev = (prev * (n - 1) + values[i]) / n
        out[i] = prev
    return out


def calc_adx(kl: List[Any], period: int = ADX_PERIOD) -> Dict[str, Any]:
    """从 K 线列表计算 ADX 序列

    :param kl: [[日期, 开, 收, 高, 低, 量], ...]
    :return: {'adx': [...], 'plus_di': [...], 'minus_di': [...], 'ok': bool}
             序列与输入等长，前置不足部分为 None
    """
    n = len(kl)
    empty = {'adx': [None] * n, 'plus_di': [None] * n,
             'minus_di': [None] * n, 'ok': False}
    if n < period * 2 + 2:
        return empty

    highs, lows, closes = [], [], []
    for r in kl:
        try:
            # 三个字段必须一次性全部取到，否则视为脏行。
            # 逐个 append 会出现「收盘追加成功、最高价越界崩溃」的不一致状态。
            c = float(r[2]); h = float(r[3]); l = float(r[4])
        except (TypeError, ValueError, IndexError):
            if closes:
                # 脏行：用前一行填充，保持序列等长
                closes.append(closes[-1])
                highs.append(highs[-1])
                lows.append(lows[-1])
            else:
                return empty
            continue
        closes.append(c)
        highs.append(h)
        lows.append(l)
    if len(closes) < period * 2 + 2:
        return empty

    tr_list, plus_dm, minus_dm = [], [], []
    for i in range(1, len(closes)):
        h, l, c = highs[i], lows[i], closes[i]
        ph, pl, pc = highs[i - 1], lows[i - 1], closes[i - 1]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        up_move = h - ph
        down_move = pl - l
        pdm = up_move if (up_move > down_move and up_move > 0) else 0.0
        mdm = down_move if (down_move > up_move and down_move > 0) else 0.0
        tr_list.append(tr)
        plus_dm.append(pdm)
        minus_dm.append(mdm)

    atr = _wilders_smooth(tr_list, period)
    s_pdm = _wilders_smooth(plus_dm, period)
    s_mdm = _wilders_smooth(minus_dm, period)

    dx_list: List[float] = []
    dx_idx: List[int] = []
    plus_di_out: List[Optional[float]] = [None] * n
    minus_di_out: List[Optional[float]] = [None] * n

    for k in range(len(tr_list)):
        a, p, m = atr[k], s_pdm[k], s_mdm[k]
        if a is None or a <= 0:
            continue
        pdi = 100.0 * p / a
        mdi = 100.0 * m / a
        idx = k + 1                      # tr_list 从下标1开始对应 kl
        plus_di_out[idx] = pdi
        minus_di_out[idx] = mdi
        denom = pdi + mdi
        dx = 100.0 * abs(pdi - mdi) / denom if denom > 0 else 0.0
        dx_list.append(dx)
        dx_idx.append(idx)

    adx_out: List[Optional[float]] = [None] * n
    if len(dx_list) >= period:
        smoothed = _wilders_smooth(dx_list, period)
        for j, val in enumerate(smoothed):
            if val is not None and j < len(dx_idx):
                adx_out[dx_idx[j]] = val

    return {'adx': adx_out, 'plus_di': plus_di_out,
            'minus_di': minus_di_out, 'ok': True}


def evaluate_gate(kl: List[Any], period: int = ADX_PERIOD) -> Dict[str, Any]:
    """评估大盘趋势闸门，返回允许仓位比例

    :return: {
        'allow_pct': 0/50/100,      # 允许的最大仓位百分比
        'reason': str,              # 人话解释
        'adx': float|None,          # 当前 ADX
        'adx_rising': bool,         # ADX 是否在上升
        'close': float|None,
        'ma': float|None,
        'ok': bool                  # 数据是否足够
    }
    数据不足时**保守返回 0%**（fail-closed）：宁可不开仓，不可在盲区满仓。
    """
    if not kl or len(kl) < max(MA_TREND + 2, period * 2 + 2):
        return {'allow_pct': 0, 'reason': 'K线不足，趋势闸门 fail-closed',
                'adx': None, 'adx_rising': False, 'close': None, 'ma': None, 'ok': False}

    res = calc_adx(kl, period)
    if not res['ok']:
        return {'allow_pct': 0, 'reason': 'ADX计算失败，fail-closed',
                'adx': None, 'adx_rising': False, 'close': None, 'ma': None, 'ok': False}

    adx_seq = res['adx']
    cur_adx = adx_seq[-1]
    # 找最近一个有效 ADX 做对比（判断是否上升）
    prev_adx = None
    for v in reversed(adx_seq[:-1]):
        if v is not None:
            prev_adx = v
            break

    closes = []
    for r in kl:
        try:
            c = float(r[2])
        except (TypeError, ValueError, IndexError):
            # 脏行：用前值填充保持等长，首个元素异常则跳过
            if closes:
                closes.append(closes[-1])
            continue
        closes.append(c)
    cur_close = closes[-1] if closes else None
    ma = (sum(closes[-MA_TREND:]) / MA_TREND) if len(closes) >= MA_TREND else None

    if cur_adx is None or cur_close is None or ma is None:
        return {'allow_pct': 0, 'reason': 'ADX/MA 无有效值，fail-closed',
                'adx': cur_adx, 'adx_rising': False,
                'close': cur_close, 'ma': round(ma, 2) if ma else None, 'ok': False}

    # 上升判定允许小幅回落：ADX 在平台期会有 ±0.5 的抖动，
    # 严格 > 会把"强势趋势中的正常波动"误判成"趋势转弱"。
    adx_rising = bool(prev_adx is not None and cur_adx >= prev_adx - 0.5)
    above_ma = cur_close > ma
    # 方向判定：+DI > -DI 为多头主导。
    # 修复 (2026-10-19): ADX 只衡量"趋势强度"，不辨方向 —— 单边下跌同样能让
    # ADX 冲到 40+。原实现只看 ADX>25 且上升就放行满仓，会在下跌趋势中满仓，
    # 与设计意图完全相反。现在必须同时满足"多头主导"，方向与强度双确认才放行。
    pdi = res['plus_di'][-1]
    mdi = res['minus_di'][-1]
    bullish = bool(pdi is not None and mdi is not None and pdi > mdi)

    if cur_adx > ADX_STRONG and adx_rising and bullish and above_ma:
        allow, reason = 100, (f'ADX={cur_adx:.1f}>{ADX_STRONG:.0f} 且上升、多头主导'
                              f'(+DI{pdi:.0f}>-DI{mdi:.0f})、站上MA{MA_TREND} → 允许满仓')
    elif cur_adx < ADX_WEAK and adx_rising and above_ma and bullish:
        allow, reason = 50, (f'ADX={cur_adx:.1f}<{ADX_WEAK:.0f} 且上升、'
                             f'收盘{cur_close:.2f}>MA{MA_TREND}({ma:.2f}) → 半仓试探')
    else:
        if cur_adx > ADX_STRONG and not bullish:
            why = f'ADX={cur_adx:.1f} 强趋势但空头主导(-DI{mdi:.0f}>+DI{pdi:.0f})'
        elif cur_adx > ADX_STRONG and not above_ma:
            why = f'ADX={cur_adx:.1f} 强趋势但收盘{cur_close:.2f}跌破MA{MA_TREND}({ma:.2f})'
        elif cur_adx > ADX_STRONG and not adx_rising:
            why = f'ADX={cur_adx:.1f} 高位但转弱'
        elif ADX_WEAK <= cur_adx <= ADX_STRONG:
            why = f'ADX={cur_adx:.1f} 处于震荡区({ADX_WEAK:.0f}-{ADX_STRONG:.0f})'
        else:
            why = f'ADX={cur_adx:.1f} 趋势不足'
        allow, reason = 0, f'{why} → 不开新仓'

    return {'allow_pct': allow, 'reason': reason,
            'adx': round(cur_adx, 2),
            'adx_prev': round(prev_adx, 2) if prev_adx is not None else None,
            'adx_rising': adx_rising,
            'bullish': bullish,
            'plus_di': round(pdi, 2) if pdi is not None else None,
            'minus_di': round(mdi, 2) if mdi is not None else None,
            'above_ma': above_ma,
            'close': round(cur_close, 2),
            'ma': round(ma, 2), 'ok': True}


def combine_with_cycle(cycle_pct: Optional[float], gate_pct: int) -> Dict[str, Any]:
    """把情绪周期仓位与大盘趋势闸门合并：取较小值

    :param cycle_pct: 情绪周期给出的仓位百分比（可能为 None 表示数据缺失）
    :param gate_pct:  趋势闸门允许的百分比
    :return: {'final_pct': float, 'cycle_pct':..., 'gate_pct':..., 'binding': 'cycle'|'gate'}
    """
    if cycle_pct is None:
        # 情绪数据缺失时，不拿趋势闸门单独放行，保守取 0
        return {'final_pct': 0, 'cycle_pct': None, 'gate_pct': gate_pct,
                'binding': 'cycle(数据缺失)'}
    final = min(float(cycle_pct), float(gate_pct))
    binding = 'gate' if gate_pct < cycle_pct else 'cycle'
    return {'final_pct': final, 'cycle_pct': float(cycle_pct),
            'gate_pct': gate_pct, 'binding': binding}
