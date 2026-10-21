# -*- coding: utf-8 -*-
"""
涨停质量核心算力引擎 (Core Limit-up Quality Engine)
不包含任何网络请求或文件 I/O，属于纯算法根据地。
基于涨停板多因子实证研究：
- 封板时间 (早盘/竞价强，午后弱)
- 封单强度 (封单金额/流通市值)
- 连板结构 (2板最强alpha，高位递减)
- 烂板扣分
"""
from typing import Dict, Any, Tuple, Optional


def _lu_num(v: Any) -> float:
    """安全数值转换"""
    return float(v) if isinstance(v, (int, float)) else 0.0


def _lu_time_score(fbt: Optional[int]) -> Optional[float]:
    """封板时间分 0~10(越早越强)。
    依据: 9:25 竞价封板 3 日超额 +5.7%, 10:00 后递减, 14:00 后 -2.4%
    """
    if not fbt:
        return None
    if fbt <= 93000:
        return 10.0
    if fbt <= 100000:
        return 8.0
    if fbt <= 113000:
        return 5.0
    if fbt <= 140000:
        return 2.0
    return 0.0


def _lu_seal_score(ratio_pct: Optional[float]) -> Optional[float]:
    """封单强度分 0~10 = 封单额/流通市值。
    依据: >5% -> 3日超额 +8.4%, 1~5% -> +3.1%, <1% -> -0.7%
    """
    if ratio_pct is None:
        return None
    if ratio_pct >= 5:
        return 10.0
    if ratio_pct >= 1:
        return 7.0
    if ratio_pct >= 0.5:
        return 4.0
    if ratio_pct >= 0.1:
        return 2.0
    return 0.0


def _lu_board_score(lbc: Optional[int]) -> Optional[float]:
    """连板结构分 0~10。
    依据: 第 2 板 alpha 最强, 4 板后衰减, 6 板以上转负
    """
    if not lbc:
        return None
    return {1: 4.0, 2: 10.0, 3: 6.0, 4: 2.0}.get(int(lbc), 0.0)


def limit_up_quality(d: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """涨停质量分 0~10 = 0.35x封板时间 + 0.35x封单强度 + 0.30x连板结构, 缺项按权重归一, 烂板扣分。

    只用池子里现成的字段(fbt/fund/ltsz/lbc/zbc), 不额外发请求。
    依据: 涨停板因子实证(竞价封板 +5.7% / 封单占流通>5% +8.4% / 第 2 板 alpha 最强)。
    E/F/H 策略用它当首要排序键, 并通过 x['qlty'] 把分数带给 CLI 与 Web。
    返回 (score, detail)。
    """
    try:
        fbt = int(d.get('fbt') or 0)
    except Exception:
        fbt = 0
    try:
        lbc = int(d.get('lbc') or 0)
    except Exception:
        lbc = 0
    try:
        zbc = int(d.get('zbc') or 0)
    except Exception:
        zbc = 0
    ltsz = _lu_num(d.get('ltsz'))
    ratio = (_lu_num(d.get('fund')) / ltsz * 100) if ltsz > 0 else None

    parts = []
    tv, sv, bv = _lu_time_score(fbt), _lu_seal_score(ratio), _lu_board_score(lbc)
    if tv is not None:
        parts.append((tv, 0.35, 'time'))
    if sv is not None:
        parts.append((sv, 0.35, 'seal'))
    if bv is not None:
        parts.append((bv, 0.30, 'board'))
    if not parts:
        return 0.0, {'score': 0.0, 'missing': True, 'used_factors': 0}
    wsum = sum(p[1] for p in parts)
    score = sum(p[0] * p[1] for p in parts) / wsum
    if zbc >= 3:
        score -= 1.5
    elif zbc == 2:
        score -= 0.7
    score = max(0.0, min(10.0, round(score, 2)))
    return score, {
        'score': score, 'fbt': fbt, 'lbc': lbc, 'zbc': zbc,
        'seal_ratio_pct': round(ratio, 2) if ratio is not None else None,
        'parts': {p[2]: p[0] for p in parts},
        'used_factors': len(parts), 'missing': len(parts) < 3,
    }
