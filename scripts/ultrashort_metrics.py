# -*- coding: utf-8 -*-
"""
scripts/ultrashort_metrics.py

A股超短量化微观算子库与异构因子正交打分引擎：
1. compute_adaptive_vw_dvr: 成交量加权贝叶斯收缩盘中下行方差占比 + 双Sigmoid连续软门控承接得分
2. evaluate_limit_order_strength: 封流比/封成比双维监控 + 千亿中军500万/0.3%换手门槛 + 尾盘>40%大单撤退报警
3. compute_desensitized_headroom: 真实安全垫脱敏算子（规避首板与无异动标的误杀）
4. robust_orthogonal_scoring: 截面RankPct + 因果序贯Gram-Schmidt正交化 + 时序半衰期门控 + 一票否决风险乘子
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
import numpy as np
from numpy.typing import NDArray


@dataclass(slots=True)
class CandidateMicroMetrics:
    """单只候选股的微观底牌与综合正交打分输出结构"""
    stock_code: str
    vw_dvr: float                       # 成交量加权贝叶斯收缩 DVR in [0, 1]
    absorption_score: float             # 连续软门控承接极性得分 in [-1.0, +1.0]
    dvr_regime_label: str               # 盘口承接状态语义标签
    seal_to_float_ratio: float          # 买一封单金额 / 自由流通市值
    seal_to_turnover_ratio: float       # 买一封单金额 / 日内成交额 (封成比)
    seal_drop_ratio: float              # 买一封单较日内峰值回落比例
    seal_quality_score: float           # 封单综合质量得分 in [0.0, 1.0]
    is_iron_sealed: bool                # 是否满足 >=5% 自由流通市值铁板标准
    is_large_withdrawal: bool           # 是否触发买一封单骤降 >40% 大单撤退警报
    effective_headroom_pct: float       # 脱敏后的真实安全垫比例
    total_orthogonal_score: float       # 最终正交合成总分 in [0.0, 100.0]
    risk_penalty_multiplier: float      # 一票否决综合风险折扣乘子 in (0.0, 1.0]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sigmoid(x: NDArray[np.float64] | float) -> NDArray[np.float64]:
    """数值防溢出的标准 Sigmoid 函数"""
    x_clipped = np.clip(np.asarray(x, dtype=np.float64), -60.0, 60.0)
    return 1.0 / (1.0 + np.exp(-x_clipped))


def compute_adaptive_vw_dvr(
    r_1m: NDArray[np.float64],
    v_1m: NDArray[np.float64],
    p_prev: NDArray[np.float64] | float,
    amp_intraday: NDArray[np.float64] | float,
    pos_intraday: NDArray[np.float64] | float,
    *,
    shrink_lambda: float = 4.0,
) -> dict[str, NDArray[np.float64] | list[str]]:
    """
    成交量加权贝叶斯收缩 DVR 算子 + 双 Sigmoid 连续软门控承接度计算
    同时支持单股 1D 数组 (N_bars,) 与批量候选池 2D 矩阵 (M_stocks, N_bars) 输入。

    数学模型:
        VW-DVR = (sum(v_i * min(r_i, 0)^2) + 0.5 * lambda * eps_tick^2) /
                 (sum(v_i * r_i^2) + lambda * eps_tick^2)
    双 Sigmoid 连续软门控:
        1. 振幅激活门控 G_amp = Sigmoid(120 * (Amp - 0.042))  (中心点 4.2%, 消除 6% 悬崖截断)
        2. 极性软门控 Polarity = tanh(4.5 * (0.48 - VW_DVR) + 2.2 * (Pos - 0.50))
        3. 承接极性得分 absorption_score = clip(G_amp * Polarity, -1.0, 1.0)
    """
    r_mat = np.asarray(r_1m, dtype=np.float64)
    v_mat = np.asarray(v_1m, dtype=np.float64)
    is_1d = r_mat.ndim == 1
    if is_1d:
        r_mat = r_mat[np.newaxis, :]
        v_mat = v_mat[np.newaxis, :]

    m_stocks, n_bars = r_mat.shape
    p_prev_vec = np.broadcast_to(np.asarray(p_prev, dtype=np.float64), (m_stocks,))
    amp_vec = np.broadcast_to(np.asarray(amp_intraday, dtype=np.float64), (m_stocks,))
    pos_vec = np.broadcast_to(np.asarray(pos_intraday, dtype=np.float64), (m_stocks,))

    # 清洗非有限值并限制极端成交量权重
    r_clean = np.nan_to_num(r_mat, nan=0.0, posinf=0.0, neginf=0.0)
    v_clean = np.maximum(np.nan_to_num(v_mat, nan=0.0, posinf=0.0, neginf=0.0), 0.0)

    # 1. 分钟成交量相对均值权重 v_i = V_i / mean(V)
    v_mean = np.mean(v_clean, axis=1, keepdims=True)
    v_weight = np.where(v_mean > 1e-9, v_clean / np.maximum(v_mean, 1e-9), 1.0)

    # 2. 基于最小报价单位 (0.01元) 的自适应 Tick 级底噪先验
    tick_ret = 0.01 / np.maximum(p_prev_vec, 1.0)
    prior_var = shrink_lambda * np.sqrt(max(n_bars, 1)) * (tick_ret ** 2)

    # 3. 贝叶斯收缩成交量加权下行方差占比
    down_ret_sq = np.minimum(r_clean, 0.0) ** 2
    total_ret_sq = r_clean ** 2

    numerator = np.sum(v_weight * down_ret_sq, axis=1) + 0.50 * prior_var
    denominator = np.sum(v_weight * total_ret_sq, axis=1) + prior_var
    vw_dvr = np.clip(numerator / np.maximum(denominator, 1e-12), 0.0, 1.0)

    # 4. 双 Sigmoid 软门控合成连续承接得分 [-1.0, +1.0]
    # 第一重 Sigmoid: 振幅软激活门控 (在 3.0% ~ 6.0% 之间平滑爬升，保留震荡市蓄势前瞻信号)
    g_amp = _sigmoid(120.0 * (amp_vec - 0.042))

    # 第二重双 Sigmoid 极性耦合: 将低 DVR 优势与高日内分位优势映射为 [-1, 1] 极性
    dvr_advantage = 2.0 * _sigmoid(9.0 * (0.48 - vw_dvr)) - 1.0
    pos_advantage = 2.0 * _sigmoid(6.0 * (pos_vec - 0.50)) - 1.0
    combined_polarity = np.clip(0.70 * dvr_advantage + 0.30 * pos_advantage, -1.0, 1.0)

    absorption_score = np.clip(g_amp * combined_polarity, -1.0, 1.0)

    # 5. 生成盘口微观语义标签（兼容原系统硬条件并扩展软门控状态）
    labels: list[str] = []
    for idx in range(m_stocks):
        amp_val = float(amp_vec[idx])
        dvr_val = float(vw_dvr[idx])
        pos_val = float(pos_vec[idx])
        score_val = float(absorption_score[idx])

        if amp_val >= 0.06 and dvr_val < 0.35 and pos_val >= 0.55:
            labels.append("🔥 强承接洗盘")
        elif dvr_val >= 0.60 and amp_val >= 0.035:
            labels.append("🚨 放量派发")
        elif score_val >= 0.28:
            labels.append("🟢 良性分歧承接")
        elif score_val <= -0.28:
            labels.append("🟠 抛压主导偏弱")
        else:
            labels.append("⚪ 窄幅横盘钝化")

    if is_1d:
        return {
            "vw_dvr": vw_dvr[0],
            "absorption_score": absorption_score[0],
            "amplitude_gate": g_amp[0],
            "dvr_regime_label": labels[0],
        }
    return {
        "vw_dvr": vw_dvr,
        "absorption_score": absorption_score,
        "amplitude_gate": g_amp,
        "dvr_regime_label": labels,
    }


def _vector_evaluate_limit_order_strength(
    seal_amount: NDArray[np.float64] | float,
    peak_seal_amount: NDArray[np.float64] | float,
    turnover_amount: NDArray[np.float64] | float,
    free_float_mkt_cap: NDArray[np.float64] | float,
    is_sealed: NDArray[np.bool_] | bool,
    *,
    minutes_from_open: float = 120.0,
    min_turnover_amount: float = 5_000_000.0,
    min_turnover_rate: float = 0.003,
    withdrawal_threshold: float = 0.40,
) -> dict[str, NDArray[np.float64] | NDArray[np.bool_]]:
    """
    买一封单质量比与尾盘大单撤退向量化评估算子

    加固特性:
    1. 监控 Seal / FreeFloat (>= 5% 判定为铁板) 与 Seal / Turnover (封成比)
    2. 千亿中军与无量一字板防失真门禁: 仅当 成交额 >= 500万 或 实际换手率 >= 0.3% 时激活封成比常规权重；
       对于缩量一字板 (<500万 且 <0.3%换手)，防止分母趋零导致封成比虚高，自动将权重切换至封流比。
    3. 买一封单较日内峰值回落 > 40% 立即触发大单撤退报警，并在尾盘阶段加重风险惩罚。
    """
    seal_vec = np.maximum(np.asarray(seal_amount, dtype=np.float64), 0.0)
    peak_vec = np.maximum(np.asarray(peak_seal_amount, dtype=np.float64), seal_vec)
    turn_vec = np.maximum(np.asarray(turnover_amount, dtype=np.float64), 0.0)
    float_vec = np.maximum(np.asarray(free_float_mkt_cap, dtype=np.float64), 1.0)
    sealed_vec = np.asarray(is_sealed, dtype=bool)

    is_scalar = seal_vec.ndim == 0
    if is_scalar:
        seal_vec = seal_vec[np.newaxis]
        peak_vec = peak_vec[np.newaxis]
        turn_vec = turn_vec[np.newaxis]
        float_vec = float_vec[np.newaxis]
        sealed_vec = sealed_vec[np.newaxis]

    turnover_rate = turn_vec / float_vec
    seal_to_float = np.where(sealed_vec, seal_vec / float_vec, 0.0)

    # 千亿中军与有效换手门槛校验: 成交额 >= 500万 或 换手率 >= 0.3%
    valid_turnover_gate = (turn_vec >= min_turnover_amount) | (turnover_rate >= min_turnover_rate)

    raw_seal_to_turn = np.where(
        sealed_vec & (turn_vec > 1.0),
        seal_vec / np.maximum(turn_vec, 1.0),
        0.0,
    )
    # 截断极端一字板封成比至合理上限 10.0，避免污染截面数值
    seal_to_turnover = np.where(valid_turnover_gate, np.minimum(raw_seal_to_turn, 10.0), 0.0)

    # 铁板判定: 封死涨停 且 买一封单占自由流通市值 >= 5%
    is_iron_sealed = sealed_vec & (seal_to_float >= 0.05)

    # 大单撤退识别: 历史上曾有过有效封单(峰值 >= 300万) 且 当前封单较峰值骤降 > 40%
    seal_drop_ratio = np.where(
        peak_vec >= 3_000_000.0,
        np.clip((peak_vec - seal_vec) / np.maximum(peak_vec, 1.0), 0.0, 1.0),
        0.0,
    )
    is_large_withdrawal = (peak_vec >= 3_000_000.0) & (seal_drop_ratio > withdrawal_threshold)

    # 合成连续封单质量分 [0.0, 1.0]:
    # 封流比 5% 映射至 ~0.88 分; 封成比 1.0 (100%) 映射至 ~0.85 分
    score_float = 1.0 - np.exp(-35.0 * seal_to_float)
    score_turn = 1.0 - np.exp(-1.8 * seal_to_turnover)

    raw_quality = np.where(
        ~sealed_vec,
        0.0,
        np.where(
            valid_turnover_gate,
            0.55 * score_float + 0.45 * score_turn,
            score_float,  # 极度缩量一字板完全依赖封流比评估
        ),
    )

    # 若发生大单撤退，按撤单幅度与日内所处时段扣减质量分（14:00后尾盘撤单惩罚加倍）
    late_session_boost = 1.25 if minutes_from_open >= 180.0 else 1.0
    withdrawal_discount = np.where(
        is_large_withdrawal,
        np.clip(1.0 - late_session_boost * seal_drop_ratio, 0.15, 0.70),
        1.0,
    )
    seal_quality_score = np.clip(raw_quality * withdrawal_discount, 0.0, 1.0)

    if is_scalar:
        return {
            "seal_to_float_ratio": seal_to_float[0],
            "seal_to_turnover_ratio": seal_to_turnover[0],
            "seal_drop_ratio": seal_drop_ratio[0],
            "seal_quality_score": seal_quality_score[0],
            "is_iron_sealed": is_iron_sealed[0],
            "is_large_withdrawal": is_large_withdrawal[0],
            "withdrawal_penalty": withdrawal_discount[0],
        }
    return {
        "seal_to_float_ratio": seal_to_float,
        "seal_to_turnover_ratio": seal_to_turnover,
        "seal_drop_ratio": seal_drop_ratio,
        "seal_quality_score": seal_quality_score,
        "is_iron_sealed": is_iron_sealed,
        "is_large_withdrawal": is_large_withdrawal,
        "withdrawal_penalty": withdrawal_discount,
    }


def compute_desensitized_headroom(
    curr_price: NDArray[np.float64],
    prev_close: NDArray[np.float64],
    limit_up_price: NDArray[np.float64],
    severe_safe_price: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.bool_]]:
    """
    真实安全垫 (Headroom) 脱敏算子：
    若个股今日涨停价仍低于严重异动安全价 (severe_safe_price >= limit_up_price)，
    说明今日处于无异动约束自由博弈状态，安全垫统一脱敏赋予充裕值 0.30 (30%)，绝不触发首板误杀。
    """
    unconstrained = severe_safe_price >= limit_up_price
    raw_headroom = (severe_safe_price - curr_price) / np.maximum(prev_close, 1e-9)
    effective_headroom = np.where(unconstrained, np.maximum(raw_headroom, 0.30), raw_headroom)
    is_severe_locked = (~unconstrained) & (raw_headroom < 0.02)
    return effective_headroom, is_severe_locked


def cross_sectional_rank_pct(x: NDArray[np.float64]) -> NDArray[np.float64]:
    """
    极值鲁棒的截面百分位秩归一化 RankPct in [0.0, 1.0]。
    对相等数值采用中位秩(Average Tie-Breaking)，当样本数 M < 4 时平滑回退至 Sigmoid 映射。
    """
    arr = np.nan_to_num(np.asarray(x, dtype=np.float64), nan=0.0, posinf=0.0, neginf=0.0)
    m = arr.shape[0]
    if m == 0:
        return arr
    if m < 4:
        return _sigmoid(arr)

    order = np.argsort(arr, kind="mergesort")
    ranks = np.empty(m, dtype=np.float64)
    ranks[order] = np.arange(m, dtype=np.float64)

    # 处理并列值 (Tie-Breaking: 赋予相同数值平均秩，确保全0向量不会因索引顺序产生伪高低分)
    sorted_vals = arr[order]
    diff_mask = np.concatenate(([True], sorted_vals[1:] != sorted_vals[:-1], [True]))
    group_bounds = np.flatnonzero(diff_mask)
    for g_idx in range(len(group_bounds) - 1):
        start, end = group_bounds[g_idx], group_bounds[g_idx + 1]
        if end - start > 1:
            avg_rank = 0.5 * (start + end - 1)
            ranks[order[start:end]] = avg_rank

    return ranks / float(m - 1)


def sequential_gram_schmidt_orthogonalize(f_matrix: NDArray[np.float64]) -> NDArray[np.float64]:
    """
    因果序贯 Gram-Schmidt 正交化 (耗时 < 0.02ms)
    严格按照超短交易因果时间链：
        Col 0 (09:25 集合竞价量能) -> Col 1 (启动前锋度) -> Col 2 (盘中 DVR 承接度) -> Col 3 (买一封单质量)
    剥离后续因子与前序因子的共线性投影，杜绝高竞价天然早封板的重复计分 (Double Counting)。
    """
    m_stocks, k_factors = f_matrix.shape
    if m_stocks <= 1:
        return f_matrix.copy()

    centered = f_matrix - np.mean(f_matrix, axis=0, keepdims=True)
    ortho = np.zeros_like(centered, dtype=np.float64)

    for k in range(k_factors):
        vec = centered[:, k].copy()
        for j in range(k):
            basis = ortho[:, j]
            norm_sq = float(np.dot(basis, basis))
            if norm_sq > 1e-10:
                proj_coeff = float(np.dot(vec, basis)) / norm_sq
                vec = vec - proj_coeff * basis
        ortho[:, k] = vec

    # 将正交残差重新映射回截面百分位秩 [0, 1]，确保量纲完全一致
    ortho_ranked = np.empty_like(ortho, dtype=np.float64)
    for k in range(k_factors):
        if np.std(ortho[:, k]) < 1e-9:
            ortho_ranked[:, k] = 0.50
        else:
            ortho_ranked[:, k] = cross_sectional_rank_pct(ortho[:, k])
    return ortho_ranked


def robust_orthogonal_scoring(
    auction_metric: NDArray[np.float64],
    speed_rank: NDArray[np.float64],
    absorption_score: NDArray[np.float64],
    seal_quality_score: NDArray[np.float64],
    is_sealed: NDArray[np.bool_],
    *,
    minutes_from_open: float,
    is_large_withdrawal: NDArray[np.bool_] | None = None,
    is_spike_fade: NDArray[np.bool_] | None = None,
    is_severe_locked: NDArray[np.bool_] | None = None,
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    """
    异构超短因子防过拟合正交融合打分器 (`Scoring Function`)

    参数:
        auction_metric: 09:25 集合竞价综合量比/占昨比指标 (越大越强)
        speed_rank: 题材内启动前锋度排名 (Rank=1 最强，内部自动取逆序转换为正向得分)
        absorption_score: 盘中自适应 VW-DVR 承接极性得分 in [-1.0, 1.0]
        seal_quality_score: 封单质量得分 in [0.0, 1.0]
        is_sealed: 当前是否封死涨停
        minutes_from_open: 距离 09:30 开盘已交易分钟数 (0 ~ 240)
        is_large_withdrawal: 买一封单是否撤退 > 40%
        is_spike_fade: 是否属于“冲高回落掉队杂毛” (如 09:31 摸+5%后跳水翻绿)
        is_severe_locked: 是否触碰严重异动红线空间锁死 (<2%)

    返回:
        (total_scores [0~100], risk_penalty_multipliers (0~1], orthogonal_factor_ranks (M, 4))
    """
    auc_vec = np.asarray(auction_metric, dtype=np.float64)
    spd_vec = -np.asarray(speed_rank, dtype=np.float64)  # Rank=1 最小，取负号使越大越强
    dvr_vec = np.asarray(absorption_score, dtype=np.float64)
    seal_vec = np.asarray(seal_quality_score, dtype=np.float64)
    sealed_mask = np.asarray(is_sealed, dtype=bool)
    m = len(auc_vec)

    # Step 1: 极值鲁棒截面 RankPct 归一化
    f_raw = np.column_stack(
        [
            cross_sectional_rank_pct(auc_vec),
            cross_sectional_rank_pct(spd_vec),
            cross_sectional_rank_pct(dvr_vec),
            cross_sectional_rank_pct(seal_vec),
        ]
    )

    # Step 2: 因果序贯 Gram-Schmidt 正交化 (竞价 -> 前锋度 -> DVR -> 封单)
    ortho_ranks = sequential_gram_schmidt_orthogonalize(f_raw)

    # Step 3: 开盘 25 分钟指数半衰期与封板状态动态门控权重
    t_min = max(float(minutes_from_open), 0.0)
    w_auc = 0.35 * np.exp(-t_min / 25.0)

    # 封板标的重点考核封单质量(0.45)与前锋度；未封板标的重点考核盘中DVR承接与前锋度
    w_seal = np.where(sealed_mask, 0.45, 0.05)
    w_dvr = np.where(sealed_mask, 0.12, 0.52 - 0.50 * w_auc)
    w_speed = 1.0 - (w_auc + w_seal + w_dvr)

    base_score = (
        w_auc * ortho_ranks[:, 0]
        + w_speed * ortho_ranks[:, 1]
        + w_dvr * ortho_ranks[:, 2]
        + w_seal * ortho_ranks[:, 3]
    )

    # Step 4: 一票否决乘法风险门控 (杜绝单项满分掩盖致命撤单/骗炮/特停锁死)
    penalty = np.ones(m, dtype=np.float64)
    if is_large_withdrawal is not None:
        penalty *= np.where(np.asarray(is_large_withdrawal, dtype=bool), 0.40, 1.0)
    if is_spike_fade is not None:
        penalty *= np.where(np.asarray(is_spike_fade, dtype=bool), 0.25, 1.0)
    if is_severe_locked is not None:
        penalty *= np.where(np.asarray(is_severe_locked, dtype=bool), 0.35, 1.0)

    total_scores = np.round(np.clip(100.0 * base_score * penalty, 0.0, 100.0), 2)
    return total_scores, np.round(penalty, 4), ortho_ranks


def evaluate_candidate_pool_metrics(
    stock_codes: Sequence[str],
    r_1m_matrix: NDArray[np.float64],
    v_1m_matrix: NDArray[np.float64],
    prev_closes: NDArray[np.float64],
    curr_prices: NDArray[np.float64],
    high_prices: NDArray[np.float64],
    low_prices: NDArray[np.float64],
    limit_up_prices: NDArray[np.float64],
    severe_safe_prices: NDArray[np.float64],
    seal_amounts: NDArray[np.float64],
    peak_seal_amounts: NDArray[np.float64],
    turnover_amounts: NDArray[np.float64],
    free_float_mkt_caps: NDArray[np.float64],
    auction_metrics: NDArray[np.float64],
    speed_ranks: NDArray[np.float64],
    *,
    minutes_from_open: float,
    is_spike_fade: NDArray[np.bool_] | None = None,
) -> dict[str, Any]:
    """
    150只候选池全量微观底牌与综合正交打分一键式批量向量化入口 (单次耗时 < 0.2ms)
    """
    prev_c = np.maximum(np.asarray(prev_closes, dtype=np.float64), 1e-9)
    curr_p = np.asarray(curr_prices, dtype=np.float64)
    high_p = np.maximum(np.asarray(high_prices, dtype=np.float64), curr_p)
    low_p = np.minimum(np.asarray(low_prices, dtype=np.float64), curr_p)
    limit_p = np.asarray(limit_up_prices, dtype=np.float64)
    sev_safe_p = np.asarray(severe_safe_prices, dtype=np.float64)

    # 1. 日内实时振幅与日内价格分位
    amp_intraday = (high_p - low_p) / prev_c
    price_span = high_p - low_p
    pos_intraday = np.where(price_span > 1e-5, (curr_p - low_p) / np.maximum(price_span, 1e-5), 0.50)
    is_sealed = curr_p >= (limit_p - 1e-4)

    # 2. 盘中自适应 VW-DVR 承接度
    dvr_res = compute_adaptive_vw_dvr(
        r_1m=r_1m_matrix,
        v_1m=v_1m_matrix,
        p_prev=prev_c,
        amp_intraday=amp_intraday,
        pos_intraday=pos_intraday,
    )
    vw_dvr_vec = np.asarray(dvr_res["vw_dvr"], dtype=np.float64)
    absorb_vec = np.asarray(dvr_res["absorption_score"], dtype=np.float64)
    regime_labels = list(dvr_res["dvr_regime_label"])

    # 3. 买一封单质量与尾盘撤单监控
    seal_res = evaluate_limit_order_strength(
        seal_amount=seal_amounts,
        peak_seal_amount=peak_seal_amounts,
        turnover_amount=turnover_amounts,
        free_float_mkt_cap=free_float_mkt_caps,
        is_sealed=is_sealed,
        minutes_from_open=minutes_from_open,
    )
    seal_to_float_vec = np.asarray(seal_res["seal_to_float_ratio"], dtype=np.float64)
    seal_to_turn_vec = np.asarray(seal_res["seal_to_turnover_ratio"], dtype=np.float64)
    seal_drop_vec = np.asarray(seal_res["seal_drop_ratio"], dtype=np.float64)
    seal_qual_vec = np.asarray(seal_res["seal_quality_score"], dtype=np.float64)
    iron_sealed_vec = np.asarray(seal_res["is_iron_sealed"], dtype=bool)
    large_withdraw_vec = np.asarray(seal_res["is_large_withdrawal"], dtype=bool)

    # 4. 真实安全垫脱敏计算
    eff_headroom_vec, severe_locked_vec = compute_desensitized_headroom(
        curr_price=curr_p,
        prev_close=prev_c,
        limit_up_price=limit_p,
        severe_safe_price=sev_safe_p,
    )

    # 5. 因果序贯正交综合打分
    total_scores, risk_penalties, ortho_ranks = robust_orthogonal_scoring(
        auction_metric=auction_metrics,
        speed_rank=speed_ranks,
        absorption_score=absorb_vec,
        seal_quality_score=seal_qual_vec,
        is_sealed=is_sealed,
        minutes_from_open=minutes_from_open,
        is_large_withdrawal=large_withdraw_vec,
        is_spike_fade=is_spike_fade,
        is_severe_locked=severe_locked_vec,
    )

    items: dict[str, dict[str, Any]] = {}
    for i, code in enumerate(stock_codes):
        metric_obj = CandidateMicroMetrics(
            stock_code=code,
            vw_dvr=round(float(vw_dvr_vec[i]), 4),
            absorption_score=round(float(absorb_vec[i]), 4),
            dvr_regime_label=regime_labels[i],
            seal_to_float_ratio=round(float(seal_to_float_vec[i]), 4),
            seal_to_turnover_ratio=round(float(seal_to_turn_vec[i]), 4),
            seal_drop_ratio=round(float(seal_drop_vec[i]), 4),
            seal_quality_score=round(float(seal_qual_vec[i]), 4),
            is_iron_sealed=bool(iron_sealed_vec[i]),
            is_large_withdrawal=bool(large_withdraw_vec[i]),
            effective_headroom_pct=round(float(eff_headroom_vec[i]), 4),
            total_orthogonal_score=float(total_scores[i]),
            risk_penalty_multiplier=float(risk_penalties[i]),
        )
        items[code] = metric_obj.to_dict()

    return {
        "total_scores": total_scores,
        "vw_dvr": vw_dvr_vec,
        "absorption_score": absorb_vec,
        "seal_quality_score": seal_qual_vec,
        "effective_headroom_pct": eff_headroom_vec,
        "orthogonal_factor_ranks": ortho_ranks,
        "inspector_drawers": items,
    }


if __name__ == "__main__":
    # 内置自检测试：验证 1. 横盘底噪收缩防震荡  2. 放量承接识别  3. 大单撤退一票否决
    rng = np.random.default_rng(42)
    m_test, n_bars_test = 5, 60

    # 构造 5 只典型盘口特征股票:
    # Stock 0: 强承接真龙头 (早盘第1名封板, 缩量回踩放量拉升, 铁板封单无撤单)
    # Stock 1: 窄幅横盘股 (1分钱跳动底噪, 验证 VW-DVR 收缩至 ~0.50 且承接分趋近 0)
    # Stock 2: 尾盘大单撤退股 (曾有2亿封单但撤掉60%, 验证一票否决降分)
    # Stock 3: 冲高回落骗炮股 (早盘摸高回落放量砸盘, DVR 高企)
    # Stock 4: 震荡市蓄势股 (振幅 4.8% 处于 3%~6% 过渡带, 验证软门控保留正向承接分)
    r_mat = np.zeros((m_test, n_bars_test), dtype=np.float64)
    v_mat = np.ones((m_test, n_bars_test), dtype=np.float64) * 1000.0

    # Stock 0: 上涨放量、小幅回踩缩量
    r_mat[0, :30] = 0.003
    v_mat[0, :30] = 5000.0
    r_mat[0, 30:] = -0.0005
    v_mat[0, 30:] = 500.0

    # Stock 1: 极窄幅 1分钱跳动 (昨收10元, 跳动 ±0.0005)
    r_mat[1, ::2] = 0.0005
    r_mat[1, 1::2] = -0.0005

    # Stock 2: 封板但尾盘撤单60%
    r_mat[2, :20] = 0.0045
    v_mat[2, :20] = 4000.0

    # Stock 3: 放量暴跌派发
    r_mat[3, :10] = 0.004
    r_mat[3, 10:] = -0.0025
    v_mat[3, 10:] = 6000.0

    # Stock 4: 振幅 4.8% 的震荡蓄势承接 (打破原 6% 硬截断盲区)
    r_mat[4, :40] = 0.0012
    v_mat[4, :40] = 3500.0
    r_mat[4, 40:] = -0.0004
    v_mat[4, 40:] = 600.0

    codes = ["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ", "000005.SZ"]
    prev_c = np.array([10.0, 10.0, 10.0, 10.0, 10.0])
    curr_p = np.array([11.0, 10.01, 11.0, 9.60, 10.42])
    high_p = np.array([11.0, 10.05, 11.0, 10.55, 10.48])
    low_p = np.array([10.20, 9.98, 10.30, 9.55, 10.00])
    limit_p = np.array([11.0, 11.0, 11.0, 11.0, 11.0])
    sev_safe_p = np.array([15.0, 15.0, 15.0, 15.0, 15.0])

    seal_amt = np.array([3.5e8, 0.0, 0.8e8, 0.0, 0.0])
    peak_seal = np.array([3.6e8, 0.0, 2.0e8, 0.0, 0.0])  # Stock 2 撤单 60%
    turn_amt = np.array([2.5e8, 1.2e7, 2.0e8, 4.0e8, 1.5e8])
    float_cap = np.array([50.0e8, 50.0e8, 50.0e8, 50.0e8, 50.0e8])
    auc_metric = np.array([8.5, 1.1, 7.8, 4.2, 3.0])
    spd_rank = np.array([1, 4, 2, 5, 3])
    spike_fade = np.array([False, False, False, True, False])

    batch_out = evaluate_candidate_pool_metrics(
        stock_codes=codes,
        r_1m_matrix=r_mat,
        v_1m_matrix=v_mat,
        prev_closes=prev_c,
        curr_prices=curr_p,
        high_prices=high_p,
        low_prices=low_p,
        limit_up_prices=limit_p,
        severe_safe_prices=sev_safe_p,
        seal_amounts=seal_amt,
        peak_seal_amounts=peak_seal,
        turnover_amounts=turn_amt,
        free_float_mkt_caps=float_cap,
        auction_metrics=auc_metric,
        speed_ranks=spd_rank,
        minutes_from_open=195.0,
        is_spike_fade=spike_fade,
    )

    drawers = batch_out["inspector_drawers"]
    assert drawers["000001.SZ"]["dvr_regime_label"] == "🔥 强承接洗盘"
    assert 0.45 <= drawers["000002.SZ"]["vw_dvr"] <= 0.55, "窄幅横盘股 DVR 必须被贝叶斯先验收缩至 0.50 附近"
    assert drawers["000003.SZ"]["is_large_withdrawal"] is True, "撤单 60% 必须触发大单撤退报警"
    assert drawers["000005.SZ"]["absorption_score"] > 0.25, "4.8%振幅蓄势股应通过软门控获得正向承接得分"
    assert drawers["000001.SZ"]["total_orthogonal_score"] > drawers["000003.SZ"]["total_orthogonal_score"], (
        "真龙头正交总分必须远高于尾盘撤单股"
    )

    print("[OK] scripts/ultrashort_metrics.py 全量自检断言通过！")
    for c in codes:
        d = drawers[c]
        print(
            f"{c} | {d['dvr_regime_label']} | VW-DVR={d['vw_dvr']:.3f} | "
            f"承接分={d['absorption_score']:+.3f} | 封单分={d['seal_quality_score']:.2f} | "
            f"正交总分={d['total_orthogonal_score']:.2f}"
        )

# =========================================================================
# 向后兼容适配层 (Backward Compatibility Adapter for web/main & resonance)
# =========================================================================
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

@dataclass(frozen=True)
class DVRResult:
    dvr: float                    # 纯盘中连续交易下行波动占比 [0.0 ~ 1.0]
    intraday_amp_pct: float       # 纯日内振幅 (基于盘中最高-最低) (%)
    price_pos_ratio: float        # 当前价在日内高低点区间的分位 [0.0 ~ 1.0]
    is_strong_absorption: bool    # 是否满足分歧强承接
    label: str                    # 透视抽屉角标


def calc_intraday_dvr(
    close_1m: np.ndarray,
    high_1m: np.ndarray,
    low_1m: np.ndarray,
    pre_close: float,
    open_1m: Optional[np.ndarray] = None,
    min_amplitude_pct: float = 6.0,
    dvr_threshold: float = 0.35,
    min_price_pos_ratio: float = 0.55,
) -> DVRResult:
    close_1m = np.asarray(close_1m, dtype=float)
    high_1m = np.asarray(high_1m, dtype=float)
    low_1m = np.asarray(low_1m, dtype=float)

    if len(close_1m) < 5 or pre_close <= 0:
        return DVRResult(0.5, 0.0, 0.5, False, "➖ 样本不足")

    intraday_rets = np.diff(close_1m) / close_1m[:-1]
    if open_1m is not None and len(open_1m) > 0 and open_1m[0] > 0:
        first_bar_ret = (close_1m[0] - open_1m[0]) / open_1m[0]
        rets = np.concatenate(([first_bar_ret], intraday_rets))
    else:
        rets = intraday_rets

    rv_total = float(np.sum(np.square(rets)))
    if rv_total <= 1e-12:
        return DVRResult(0.0, 0.0, 0.5, False, "➖ 极窄幅横盘")

    rv_down = float(np.sum(np.square(rets[rets < 0])))
    dvr = rv_down / rv_total

    day_high = float(np.max(high_1m))
    day_low = float(np.min(low_1m))
    curr_price = float(close_1m[-1])

    intraday_amp_pct = (day_high - day_low) / pre_close * 100.0
    price_pos_ratio = (
        float(np.clip((curr_price - day_low) / (day_high - day_low), 0.0, 1.0))
        if (day_high > day_low)
        else 0.5
    )

    is_strong = (
        (intraday_amp_pct >= min_amplitude_pct)
        and (dvr < dvr_threshold)
        and (price_pos_ratio >= min_price_pos_ratio)
    )

    if is_strong:
        label = f"🛡️ 强承接洗盘 (DVR={dvr:.2f})"
    elif (intraday_amp_pct >= min_amplitude_pct and dvr >= 0.60) or (
        intraday_amp_pct >= min_amplitude_pct and price_pos_ratio <= 0.30 and dvr >= 0.45
    ):
        label = f"🩸 放量派发风险 (DVR={dvr:.2f})"
    else:
        label = f"➖ 常态波动 (DVR={dvr:.2f})"

    return DVRResult(
        dvr=round(dvr, 4),
        intraday_amp_pct=round(intraday_amp_pct, 2),
        price_pos_ratio=round(price_pos_ratio, 2),
        is_strong_absorption=is_strong,
        label=label,
    )


@dataclass(frozen=True)
class LimitOrderHealth:
    seal_amount_wan: float               # 当前买一封单金额 (万元)
    seal_to_float_pct: float             # 封单占自由流通市值比 (%)
    seal_to_turnover_pct: Optional[float] # 封单占今日已成交额比 (%，未达换手门槛时为 None)
    is_tail_withdrawing: bool            # 是否触发封单枯竭/撤单预警
    status_label: str


def _legacy_evaluate_limit_order_strength(
    limit_price: float,
    bid1_volume_shares: float,
    free_float_mcap_yuan: float,
    day_turnover_yuan: float,
    peak_seal_yuan: Optional[float] = None,
    min_turnover_for_ratio_yuan: float = 5_000_000.0,
) -> LimitOrderHealth:
    seal_yuan = limit_price * max(0.0, bid1_volume_shares)
    seal_wan = seal_yuan / 10000.0

    float_ratio = (seal_yuan / free_float_mcap_yuan * 100.0) if free_float_mcap_yuan > 0 else 0.0
    decay_from_peak = (
        (1.0 - seal_yuan / peak_seal_yuan) if (peak_seal_yuan and peak_seal_yuan > 0) else 0.0
    )

    has_meaningful_turnover = (day_turnover_yuan >= min_turnover_for_ratio_yuan) or (
        free_float_mcap_yuan > 0 and (day_turnover_yuan / free_float_mcap_yuan >= 0.003)
    )

    if has_meaningful_turnover:
        turnover_ratio: Optional[float] = round(seal_yuan / day_turnover_yuan * 100.0, 2)
        is_withdrawing = (
            (turnover_ratio < 10.0)
            or (decay_from_peak >= 0.75 and turnover_ratio < 20.0)
            or (seal_wan < 300.0)
        )
    else:
        turnover_ratio = None
        is_withdrawing = (
            (float_ratio < 0.3 and seal_wan < 500.0)
            or (decay_from_peak >= 0.80 and float_ratio < 1.0)
        )

    if is_withdrawing:
        if turnover_ratio is not None:
            if seal_wan < 300.0 and turnover_ratio >= 10.0:
                label = f"🚨 封单金额偏小 (仅{seal_wan:.0f}万)"
            else:
                label = f"🚨 封单衰竭预警 (仅占成交{turnover_ratio:.1f}%)"
        else:
            label = f"🚨 一字封单单薄/大幅撤单 (仅{seal_wan:.0f}万)"
    elif float_ratio >= 5.0 or (turnover_ratio is None and float_ratio >= 2.0):
        label = f"🔒 铁板封单 (占流通{float_ratio:.1f}%)"
    else:
        ratio_str = f"占成交{turnover_ratio:.1f}%" if turnover_ratio is not None else f"占流通{float_ratio:.1f}%"
        label = f"🟢 封单稳健 ({ratio_str})"

    return LimitOrderHealth(
        seal_amount_wan=round(seal_wan, 2),
        seal_to_float_pct=round(float_ratio, 2),
        seal_to_turnover_pct=turnover_ratio,
        is_tail_withdrawing=is_withdrawing,
        status_label=label,
    )


def evaluate_limit_order_strength(*args, **kwargs):
    if "limit_price" in kwargs or "bid1_volume_shares" in kwargs or "free_float_mcap_yuan" in kwargs or (len(args) >= 4 and isinstance(args[0], (int, float)) and "minutes_from_open" not in kwargs and "peak_seal_amount" not in kwargs):
        return _legacy_evaluate_limit_order_strength(*args, **kwargs)
    return _vector_evaluate_limit_order_strength(*args, **kwargs)


def compute_theme_speed_ranks(
    theme_stocks: List[Dict],
    min_active_ret_pct: float = 4.5,
) -> Dict[str, Tuple[int, str]]:
    def _ts_to_sec(ts: Optional[str]) -> int:
        if not ts:
            return 999999
        parts = [int(x) for x in ts.strip().split(":")]
        return parts[0] * 3600 + parts[1] * 60 + (parts[2] if len(parts) > 2 else 0)

    def _sort_key(item: Dict):
        is_lu = bool(item.get("is_limit_up", False))
        day_ret = float(item.get("day_ret_pct", 0.0))
        is_holding_gains = is_lu or (day_ret >= min_active_ret_pct)

        if is_lu:
            tier = 0
            seal_sec = _ts_to_sec(item.get("first_seal_time"))
            cross5_sec = _ts_to_sec(item.get("cross_5pct_time"))
        elif is_holding_gains:
            tier = 1
            seal_sec = 999999
            cross5_ts = item.get("cross_5pct_time") or (item.get("timestamp") if day_ret >= 5.0 else None)
            cross5_sec = _ts_to_sec(cross5_ts)
        else:
            tier = 2
            seal_sec = 999999
            cross5_sec = 999999
        return (tier, seal_sec, cross5_sec, -day_ret)

    sorted_items = sorted(theme_stocks, key=_sort_key)
    result: Dict[str, Tuple[int, str]] = {}
    for idx, item in enumerate(sorted_items):
        rank = idx + 1
        sym = item["symbol"]
        is_lu = bool(item.get("is_limit_up", False))
        day_ret = float(item.get("day_ret_pct", 0.0))
        had_crossed_5 = item.get("cross_5pct_time") is not None
        if not is_lu and day_ret < min_active_ret_pct:
            if had_crossed_5:
                role_tag = f"🥀 冲高回落掉队 (现{day_ret:+.1f}%)"
            else:
                role_tag = "➖ 板块未动/跟跌"
        elif rank == 1:
            role_tag = "🚀 先锋龙 (Rank=1)"
        elif rank in (2, 3):
            role_tag = f"⚡ 中军/前排助攻 (Rank={rank})"
        else:
            role_tag = f"⚠️ 后排跟风警示 (Rank={rank})"
        result[sym] = (rank, role_tag)
    return result


def evaluate_volatility_headroom(
    current_price: float,
    limit_up_price: float,
    raw_normal_crit_price: float,
    raw_severe_crit_price: float,
    will_limit_trigger_normal: bool,
    will_limit_trigger_severe: bool,
) -> Dict[str, object]:
    if current_price <= 0:
        return {
            "normal_constrained_today": False,
            "severe_constrained_today": False,
            "raw_normal_crit_price": raw_normal_crit_price,
            "raw_severe_crit_price": raw_severe_crit_price,
            "raw_normal_headroom_pct": 0.0,
            "raw_severe_headroom_pct": 0.0,
            "intraday_severe_room_pct": None,
            "action_advice": "➖ 价格异常",
        }

    raw_norm_headroom_pct = round((raw_normal_crit_price / current_price - 1.0) * 100.0, 2)
    raw_sev_headroom_pct = round((raw_severe_crit_price / current_price - 1.0) * 100.0, 2)

    effective_norm_safe = min(raw_normal_crit_price, limit_up_price)
    effective_sev_safe = min(raw_severe_crit_price, limit_up_price)

    intraday_sev_room_pct = round((effective_sev_safe / current_price - 1.0) * 100.0, 2)

    if not will_limit_trigger_severe:
        sev_space_desc = f"+{raw_sev_headroom_pct:.1f}%" if raw_sev_headroom_pct < 200.0 else "充裕"
        if not will_limit_trigger_normal:
            advice = f"🟢 安全垫充裕 (距真实严重红线尚有 {sev_space_desc})：今日涨停无任何异动约束"
        else:
            advice = (
                f"🟡 今日涨停仅触普通异动，无严重异动特停风险 "
                f"(若想规避普通异动需控价于 <= {effective_norm_safe:.2f}元)"
            )
    else:
        if intraday_sev_room_pct <= 0.0:
            advice = f"🛑 已越过严重异动红线 (安全上限 {effective_sev_safe:.2f}元)，收盘必触严重异动！"
        elif intraday_sev_room_pct < 2.0:
            advice = (
                f"🚨 严重异动压线锁死 (距红线 {effective_sev_safe:.2f}元 仅剩 +{intraday_sev_room_pct:.2f}%)："
                f"封板必触严重异动，警惕主力卡位横盘或兑现"
            )
        else:
            advice = (
                f"🟠 今日涨停将触严重异动：最高卡异动安全收盘价为 {effective_sev_safe:.2f}元 "
                f"(尚余 +{intraday_sev_room_pct:.2f}% 空间)"
            )

    return {
        "normal_constrained_today": will_limit_trigger_normal,
        "severe_constrained_today": will_limit_trigger_severe,
        "raw_normal_crit_price": raw_normal_crit_price,
        "raw_severe_crit_price": raw_severe_crit_price,
        "raw_normal_headroom_pct": raw_norm_headroom_pct,
        "raw_severe_headroom_pct": raw_sev_headroom_pct,
        "intraday_severe_room_pct": intraday_sev_room_pct if will_limit_trigger_severe else None,
        "action_advice": advice,
    }
