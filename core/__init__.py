# -*- coding: utf-8 -*-
"""
Core Domain Layer (纯算力领域核心层)
提供脱离外部网络与文件 I/O 依赖的纯算法能力：
- 缠论形态学与动力学分析 (core.chan)
- 涨停多因子质量评分模型 (core.quality)
- 市场情绪打分与周期区间判定 (core.emotion)
"""

from core.chan import chan_analysis_structured, calc_ema
from core.quality import limit_up_quality
from core.emotion import (
    emotion_band,
    emotion_score_v1,
    emotion_score_v2,
    effect_flat
)

__all__ = [
    'chan_analysis_structured',
    'calc_ema',
    'limit_up_quality',
    'emotion_band',
    'emotion_score_v1',
    'emotion_score_v2',
    'effect_flat'
]
