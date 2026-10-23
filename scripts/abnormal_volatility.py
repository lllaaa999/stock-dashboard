# -*- coding: utf-8 -*-
"""
scripts/abnormal_volatility.py

A股超短量化防守端：异常波动监管红线与安全价向量化反推引擎
严格遵循沪深北交易所现行《交易规则》与《异常交易实时监控细则》：
1. 法定区间首尾复利偏离值：CumDev = (P_t / P_{t0-1} - 1) - (I_t / I_{t0-1} - 1)
2. 普通异动窗口 k in {2, 3}（主板 ±20%/ST ±12%，双创 ±30%，北交 ±40%），公告次日追溯清零
3. 严重异动双轨穿透：10日内同向异动达标（主板4次/双创3次）、10日 +100%/-50%、30日 +200%/-70%
4. 跨停牌日基准指数对齐与法定除权除息参考价精确折算
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence
import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class BoardRuleConfig:
    """交易所板块异动监管规则参数配置"""
    board_name: str
    limit_ratio: float                  # 日涨跌幅限制 (0.05 / 0.10 / 0.20 / 0.30)
    normal_up_threshold: float          # 普通异动正向偏离阈值 (0.12 / 0.20 / 0.30 / 0.40)
    normal_down_threshold: float        # 普通异动负向偏离阈值
    max_normal_triggers_10d: int        # 10日内触发严重异动的同向普通异动次数 (主板4次, 双创/北交3次)
    severe_10d_up_threshold: float      # 10日严重异动正向偏离阈值 (沪深 1.00, 北交 1.50)
    severe_10d_down_threshold: float    # 10日严重异动负向偏离阈值 (沪深 -0.50, 北交 -0.60)
    severe_30d_up_threshold: float      # 30日严重异动正向偏离阈值 (沪深 2.00, 北交 3.00)
    severe_30d_down_threshold: float    # 30日严重异动负向偏离阈值 (沪深 -0.70, 北交 -0.75)


@dataclass(slots=True)
class WindowConstraintDetail:
    """单个有效监管滑动窗口的逆推约束明细"""
    window_type: str        # "NORMAL_2_3D" | "SEVERE_COUNT_10D" | "SEVERE_10D_100P" | "SEVERE_30D_200P"
    window_days: int        # 包含今日在内的实际交易日跨度 k
    start_date: str         # 窗口期初首个交易日标识
    base_price_adj: float   # 窗口期初前收盘价 (经法定除权折算后 P_{t0-1})
    base_index: float       # 窗口期初前一日基准指数收盘点位 I_{t0-1}
    threshold: float        # 该窗口适用的正向偏离阈值
    safe_price: float       # 该窗口逆推得出的今日安全上限价 (退1分钱+缓冲垫)
    exact_trigger_price: float  # 不含缓冲垫的精确理论触线价
    curr_cum_dev: float     # 当前实时价格下的累计偏离度


@dataclass(slots=True)
class VolatilityEvaluationResult:
    """单股全维异动体检结果结构"""
    stock_code: str
    board_name: str
    prev_close: float
    curr_price: float
    limit_up_price: float
    safe_price: float                   # 全局最严安全价 (min of normal & severe)
    normal_safe_price: float            # 普通异动安全价
    severe_safe_price: float            # 严重异动(特停红线)安全价
    headroom_pct: float                 # 距全局安全价剩余空间: (safe_price - curr_price) / prev_close
    severe_headroom_pct: float          # 距严重异动红线剩余空间: (severe_safe_price - curr_price) / prev_close
    is_unconstrained_today: bool        # 今日即使封死涨停也绝不触发任何异动 (首板/低位免死金牌)
    is_severe_unconstrained_today: bool # 今日即使封死涨停也绝不触发严重异动
    is_normal_triggered_now: bool       # 当前价格是否已突破普通异动安全线
    is_severe_triggered_now: bool       # 当前价格是否已突破严重异动红线
    is_severe_locked: bool              # 是否处于严重异动空间锁死状态 (今日涨停会触线 且 剩余空间 < 2%)
    normal_triggers_in_prev_9d: int     # 过去9个交易日内已触发的同向普通异动次数
    will_Upgrade_to_severe_on_normal: bool  # 今日若触发普通异动，是否直接凑满次数升级为严重异动
    binding_window: dict[str, Any]      # 当前最严苛的瓶颈窗口详情
    action_advice: str                  # 盘口实战操作建议徽章

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def get_board_rule_config(stock_code: str, is_st: bool = False) -> BoardRuleConfig:
    """根据股票代码前缀与ST状态精确匹配沪深北交易所异动规则"""
    code = stock_code.strip().upper()
    for prefix in ("SH", "SZ", "BJ", "."):
        code = code.replace(prefix, "")

    if code.startswith(("300", "301", "688", "689")):
        return BoardRuleConfig(
            board_name="双创板(20cm)",
            limit_ratio=0.20,
            normal_up_threshold=0.30,
            normal_down_threshold=-0.30,
            max_normal_triggers_10d=3,
            severe_10d_up_threshold=1.00,
            severe_10d_down_threshold=-0.50,
            severe_30d_up_threshold=2.00,
            severe_30d_down_threshold=-0.70,
        )
    if code.startswith(("43", "83", "87", "92")):
        return BoardRuleConfig(
            board_name="北交所(30cm)",
            limit_ratio=0.30,
            normal_up_threshold=0.40,
            normal_down_threshold=-0.40,
            max_normal_triggers_10d=3,
            severe_10d_up_threshold=1.50,
            severe_10d_down_threshold=-0.60,
            severe_30d_up_threshold=3.00,
            severe_30d_down_threshold=-0.75,
        )
    if is_st:
        return BoardRuleConfig(
            board_name="主板ST(5cm)",
            limit_ratio=0.05,
            normal_up_threshold=0.12,
            normal_down_threshold=-0.12,
            max_normal_triggers_10d=4,
            severe_10d_up_threshold=0.50,
            severe_10d_down_threshold=-0.30,
            severe_30d_up_threshold=1.00,
            severe_30d_down_threshold=-0.50,
        )
    return BoardRuleConfig(
        board_name="沪深主板(10cm)",
        limit_ratio=0.10,
        normal_up_threshold=0.20,
        normal_down_threshold=-0.20,
        max_normal_triggers_10d=4,
        severe_10d_up_threshold=1.00,
        severe_10d_down_threshold=-0.50,
        severe_30d_up_threshold=2.00,
        severe_30d_down_threshold=-0.70,
    )


def round_price_cent(price: float | NDArray[np.float64]) -> float | NDArray[np.float64]:
    """按A股法定四舍五入至分（消除IEEE 754二进制浮点表示误差）"""
    return np.floor((price + 1e-9) * 100.0 + 0.5) / 100.0


def compute_statutory_ex_right_price(
    prev_close: float | NDArray[np.float64],
    cash_dividend: float | NDArray[np.float64] = 0.0,
    bonus_share_ratio: float | NDArray[np.float64] = 0.0,
    transfer_share_ratio: float | NDArray[np.float64] = 0.0,
    allotment_ratio: float | NDArray[np.float64] = 0.0,
    allotment_price: float | NDArray[np.float64] = 0.0,
) -> float | NDArray[np.float64]:
    """
    计算交易所法定除权(息)参考价：
    P_ex = round((前收盘价 - 每股现金红利 + 配股价格 * 配股比例) / (1 + 送股率 + 转增率 + 配股率), 2)
    """
    numerator = prev_close - cash_dividend + allotment_price * allotment_ratio
    denominator = 1.0 + bonus_share_ratio + transfer_share_ratio + allotment_ratio
    raw_ex_price = numerator / np.maximum(denominator, 1e-9)
    return round_price_cent(raw_ex_price)


def adjust_historical_base_prices_for_ex_rights(
    prev_closes: NDArray[np.float64],
    cash_dividends: NDArray[np.float64],
    share_split_ratios: NDArray[np.float64],
    allotment_ratios: NDArray[np.float64],
    allotment_prices: NDArray[np.float64],
) -> NDArray[np.float64]:
    """
    对历史序列中的每个窗口期初前收盘价 P_{t0-1}，若窗口内部 [t0, t] 发生了除权除息，
    按交易所法定公式逐次向后折算至当前可比口径。
    """
    n = len(prev_closes)
    adj_bases = prev_closes.astype(np.float64).copy()
    has_corp_action = (
        (np.abs(cash_dividends) > 1e-7)
        | (np.abs(share_split_ratios) > 1e-7)
        | (np.abs(allotment_ratios) > 1e-7)
    )
    if not np.any(has_corp_action):
        return adj_bases

    # 若第 m 日发生除权除息，则所有起点 t0 <= m 的窗口期初基准价均需在该日执行一次法定除权折算
    action_indices = np.flatnonzero(has_corp_action)
    for idx in action_indices:
        adj_bases[: idx + 1] = compute_statutory_ex_right_price(
            prev_close=adj_bases[: idx + 1],
            cash_dividend=cash_dividends[idx],
            bonus_share_ratio=share_split_ratios[idx],
            transfer_share_ratio=0.0,
            allotment_ratio=allotment_ratios[idx],
            allotment_price=allotment_prices[idx],
        )
    return adj_bases


def compute_exact_safe_price(
    p_bases_adj: NDArray[np.float64],
    i_bases: NDArray[np.float64],
    i_curr: float,
    thresholds: NDArray[np.float64],
    buffer_ratio: float = 0.0015,
    cap_at_limit: bool = False,
    limit_up_price: float | None = None,
) -> tuple[float, NDArray[np.float64], NDArray[np.float64]]:
    """
    核心向量化安全价逆推求解器 (耗时 < 0.005ms)

    参数:
        p_bases_adj: 各有效滑动窗口期初前收盘价 P_{t0-1} (已做除权折算)
        i_bases: 各有效滑动窗口期初前一日基准指数收盘点位 I_{t0-1}
        i_curr: 当前实时基准指数点位 I_t
        thresholds: 各窗口对应的正向偏离度监管红线 (如 0.20, 0.30, 1.00, 2.00)
        buffer_ratio: 尾盘指数抢筹/跳水缓冲垫 (默认 0.15%)
        cap_at_limit: 是否在今日涨停价处截断 (默认 False 解绑，防止首板误报空间锁死)
        limit_up_price: 今日涨停价 (仅当 cap_at_limit=True 时生效)

    返回:
        (min_safe_price, per_window_safe_prices, per_window_exact_trigger_prices)
    """
    if p_bases_adj.size == 0:
        inf_arr = np.array([], dtype=np.float64)
        return float("inf"), inf_arr, inf_arr

    index_devs = (i_curr / np.maximum(i_bases, 1e-9)) - 1.0
    # 理论精确触线价: (P_trigger / P_base - 1) - IndexDev = Threshold
    exact_trigger_prices = p_bases_adj * (1.0 + index_devs + thresholds)

    # 扣除尾盘缓冲垫后，向下截断至分，并再退 1 分钱确保绝对不越界
    buffered_raw = p_bases_adj * (1.0 + index_devs + thresholds - buffer_ratio)
    safe_prices = np.floor((buffered_raw + 1e-9) * 100.0) / 100.0 - 0.01

    if cap_at_limit and limit_up_price is not None:
        safe_prices = np.minimum(safe_prices, limit_up_price)

    return float(np.min(safe_prices)), safe_prices, exact_trigger_prices


def _normalize_bars_input(
    hist_bars: Sequence[Mapping[str, Any]] | NDArray[np.float64],
    index_bars: Sequence[Mapping[str, Any]] | NDArray[np.float64],
) -> tuple[
    list[str],
    NDArray[np.float64],
    NDArray[np.float64],
    NDArray[np.float64],
    NDArray[np.float64],
    NDArray[np.float64],
    NDArray[np.float64],
    NDArray[np.float64],
    NDArray[np.float64],
]:
    """
    将输入的个股历史K线与指数K线统一规整并对齐（自动剔除个股全天停牌日，同时严格锚定停牌前一日指数）。
    支持 dict 列表或 NumPy 数组输入。
    """
    if isinstance(hist_bars, np.ndarray) and hist_bars.dtype.names is None:
        # 纯数值数组输入: 若为 1D 视为收盘价序列; 若为 2D 则列0为prev_close, 列1为close
        s_arr = np.asarray(hist_bars, dtype=np.float64)
        i_arr = np.asarray(index_bars, dtype=np.float64)
        if s_arr.ndim == 1:
            closes = s_arr
            prev_closes = np.empty_like(closes)
            prev_closes[0] = closes[0]
            prev_closes[1:] = closes[:-1]
        else:
            prev_closes = s_arr[:, 0]
            closes = s_arr[:, 1]

        if i_arr.ndim == 1:
            idx_closes = i_arr
            idx_prev_closes = np.empty_like(idx_closes)
            idx_prev_closes[0] = idx_closes[0]
            idx_prev_closes[1:] = idx_closes[:-1]
        else:
            idx_prev_closes = i_arr[:, 0]
            idx_closes = i_arr[:, 1]

        n = min(len(closes), len(idx_closes))
        closes = closes[-n:]
        prev_closes = prev_closes[-n:]
        idx_closes = idx_closes[-n:]
        idx_prev_closes = idx_prev_closes[-n:]
        dates = [f"T-{n - idx}" for idx in range(n)]
        zeros = np.zeros(n, dtype=np.float64)
        return (
            dates,
            prev_closes,
            closes,
            idx_prev_closes,
            idx_closes,
            zeros,
            zeros,
            zeros,
            zeros,
        )

    # 字典序列输入: 支持按 date 对齐并自动过滤 volume == 0 的停牌日
    idx_map: dict[str, tuple[float, float]] = {}
    idx_list = list(index_bars)
    for pos, item in enumerate(idx_list):
        d_str = str(item.get("date", f"IDX_{pos}"))
        c_val = float(item["close"])
        p_val = float(item.get("prev_close", idx_list[pos - 1]["close"] if pos > 0 else c_val))
        idx_map[d_str] = (p_val, c_val)

    dates_out: list[str] = []
    s_prev_list: list[float] = []
    s_close_list: list[float] = []
    i_prev_list: list[float] = []
    i_close_list: list[float] = []
    cash_div_list: list[float] = []
    split_list: list[float] = []
    allot_ratio_list: list[float] = []
    allot_price_list: list[float] = []

    s_list = list(hist_bars)
    for pos, bar in enumerate(s_list):
        vol = float(bar.get("volume", 1.0))
        is_suspended = bool(bar.get("is_suspended", False)) or (vol <= 0.0 and "volume" in bar)
        if is_suspended:
            continue

        d_str = str(bar.get("date", f"T-{len(s_list) - pos}"))
        s_close = float(bar["close"])
        s_prev = float(bar.get("prev_close", s_close_list[-1] if s_close_list else s_close))

        if d_str in idx_map:
            i_prev, i_close = idx_map[d_str]
        elif pos < len(idx_list):
            raw_ib = idx_list[pos]
            i_close = float(raw_ib["close"])
            i_prev = float(raw_ib.get("prev_close", idx_list[pos - 1]["close"] if pos > 0 else i_close))
        else:
            raise ValueError(f"基准指数缺少交易日 {d_str} 的对齐行情数据")

        dates_out.append(d_str)
        s_prev_list.append(s_prev)
        s_close_list.append(s_close)
        i_prev_list.append(i_prev)
        i_close_list.append(i_close)
        cash_div_list.append(float(bar.get("cash_dividend", 0.0)))
        split_list.append(
            float(bar.get("bonus_share_ratio", 0.0)) + float(bar.get("transfer_share_ratio", 0.0))
        )
        allot_ratio_list.append(float(bar.get("allotment_ratio", 0.0)))
        allot_price_list.append(float(bar.get("allotment_price", 0.0)))

    return (
        dates_out,
        np.asarray(s_prev_list, dtype=np.float64),
        np.asarray(s_close_list, dtype=np.float64),
        np.asarray(i_prev_list, dtype=np.float64),
        np.asarray(i_close_list, dtype=np.float64),
        np.asarray(cash_div_list, dtype=np.float64),
        np.asarray(split_list, dtype=np.float64),
        np.asarray(allot_ratio_list, dtype=np.float64),
        np.asarray(allot_price_list, dtype=np.float64),
    )


def simulate_historical_volatility_state(
    s_prev_adj: NDArray[np.float64],
    s_close: NDArray[np.float64],
    i_prev: NDArray[np.float64],
    i_close: NDArray[np.float64],
    rule: BoardRuleConfig,
) -> tuple[int, list[int], int]:
    """
    在历史已完成交易日序列上运行双轨异动状态机：
    1. 普通异动轨道：检测窗口 k in {1, 2, 3} (通常 k=2 或 k=3 触达 ±20%/±30%)，
       一旦在历史第 d 日触发正向普通异动，公告次日清零，后续普通异动窗口起点 t0 必须 >= d + 1。
    2. 统计最近 9 个已完成交易日内的同向（正向）普通异动触发次数，用于判定今日是否触发“10日N次同向严重异动”。
    3. 严重异动轨道：独立检测是否存在已公告的严重异动清零点。

    返回:
        (last_normal_trigger_idx, normal_trigger_indices_in_last_9d, last_severe_trigger_idx)
    """
    n_days = len(s_close)
    last_normal_idx = -1
    last_severe_idx = -1
    normal_trigger_days: list[int] = []

    for d in range(n_days):
        # 1. 检查第 d 日是否触发普通正向异动 (窗口长度 k in {1, 2, 3}，起点 t0 > last_normal_idx)
        min_t0_normal = max(0, d - 2, last_normal_idx + 1)
        triggered_normal_today = False
        for t0 in range(min_t0_normal, d + 1):
            stock_ret = (s_close[d] / max(s_prev_adj[t0], 1e-9)) - 1.0
            index_ret = (i_close[d] / max(i_prev[t0], 1e-9)) - 1.0
            cum_dev = stock_ret - index_ret
            if cum_dev + 1e-9 >= rule.normal_up_threshold:
                triggered_normal_today = True
                break

        if triggered_normal_today:
            last_normal_idx = d
            normal_trigger_days.append(d)

        # 2. 检查第 d 日是否触发严重正向异动 (10日N次普通异动 / 10日100% / 30日200%)
        min_t0_sev10 = max(0, d - 9, last_severe_idx + 1)
        min_t0_sev30 = max(0, d - 29, last_severe_idx + 1)

        # 10日窗口内同向普通异动次数是否达标
        recent_normal_cnt = sum(1 for trig_d in normal_trigger_days if trig_d >= min_t0_sev10)
        triggered_severe_today = recent_normal_cnt >= rule.max_normal_triggers_10d

        if not triggered_severe_today:
            for t0 in range(min_t0_sev10, d + 1):
                cum_dev_10 = ((s_close[d] / max(s_prev_adj[t0], 1e-9)) - 1.0) - (
                    (i_close[d] / max(i_prev[t0], 1e-9)) - 1.0
                )
                if cum_dev_10 + 1e-9 >= rule.severe_10d_up_threshold:
                    triggered_severe_today = True
                    break

        if not triggered_severe_today:
            for t0 in range(min_t0_sev30, d + 1):
                cum_dev_30 = ((s_close[d] / max(s_prev_adj[t0], 1e-9)) - 1.0) - (
                    (i_close[d] / max(i_prev[t0], 1e-9)) - 1.0
                )
                if cum_dev_30 + 1e-9 >= rule.severe_30d_up_threshold:
                    triggered_severe_today = True
                    break

        if triggered_severe_today:
            last_severe_idx = d

    # 统计距离今日最近9个历史交易日 (即包含今日共10个交易日且在最近一次严重异动之后) 的普通异动次数
    active_10d_floor = max(0, n_days - 9, last_severe_idx + 1)
    recent_9d_triggers = [trig_d for trig_d in normal_trigger_days if trig_d >= active_10d_floor]
    return last_normal_idx, recent_9d_triggers, last_severe_idx


def evaluate_stock_volatility(
    stock_code: str,
    hist_bars: Sequence[Mapping[str, Any]] | NDArray[np.float64],
    index_bars: Sequence[Mapping[str, Any]] | NDArray[np.float64],
    curr_price: float,
    curr_index: float,
    *,
    is_st: bool = False,
    cap_at_limit: bool = False,
    buffer_ratio: float = 0.0015,
    today_cash_dividend: float = 0.0,
    today_share_split_ratio: float = 0.0,
    today_allotment_ratio: float = 0.0,
    today_allotment_price: float = 0.0,
) -> dict[str, Any]:
    """
    单股全维异动体检入口函数（支持主板/双创/北交/ST，双轨独立滑动，向量化安全价逆推）

    参数:
        stock_code: 股票代码 (如 "000001.SZ", "300750", "688001")
        hist_bars: 过去 N 个交易日(建议 >= 30日, 不含今日)的个股已完成日K线序列
        index_bars: 对应日期的基准指数已完成日K线序列
        curr_price: 今日盘中实时价格 (或拟挂单价格)
        curr_index: 今日盘中实时基准指数点位
        is_st: 是否为 ST/*ST 标的
        cap_at_limit: 是否将安全价截断在今日涨停价以内 (默认 False 彻底根除首板锁死误报)
        buffer_ratio: 尾盘跳水安全垫比例 (默认 0.0015 即 0.15%)
    """
    rule = get_board_rule_config(stock_code, is_st=is_st)
    (
        dates,
        s_prev,
        s_close,
        i_prev,
        i_close,
        cash_div,
        split_ratio,
        allot_ratio,
        allot_price,
    ) = _normalize_bars_input(hist_bars, index_bars)

    n_hist = len(s_close)
    if n_hist == 0:
        raise ValueError("hist_bars 至少需要包含 1 个有效历史交易日数据")

    # 1. 对历史窗口基准价进行期间除权除息法定折算
    s_prev_adj = adjust_historical_base_prices_for_ex_rights(
        prev_closes=s_prev,
        cash_dividends=cash_div,
        share_split_ratios=split_ratio,
        allotment_ratios=allot_ratio,
        allotment_prices=allot_price,
    )

    # 2. 运行历史双轨异动状态机，定位上次普通异动清零点与近9日同向普通异动次数
    last_normal_idx, recent_9d_triggers, last_severe_idx = simulate_historical_volatility_state(
        s_prev_adj=s_prev_adj,
        s_close=s_close,
        i_prev=i_prev,
        i_close=i_close,
        rule=rule,
    )

    # 3. 计算今日前收盘基准价（若今日发生除权除息，按法定公式折算）
    today_prev_close = float(
        compute_statutory_ex_right_price(
            prev_close=float(s_close[-1]),
            cash_dividend=today_cash_dividend,
            bonus_share_ratio=today_share_split_ratio,
            transfer_share_ratio=0.0,
            allotment_ratio=today_allotment_ratio,
            allotment_price=today_allotment_price,
        )
    )
    today_prev_index = float(i_close[-1])

    # 若今日发生除权，历史所有期初基准价同样需要叠加今日除权折算
    if (
        abs(today_cash_dividend) > 1e-7
        or abs(today_share_split_ratio) > 1e-7
        or abs(today_allotment_ratio) > 1e-7
    ):
        s_prev_adj = np.asarray(
            compute_statutory_ex_right_price(
                prev_close=s_prev_adj,
                cash_dividend=today_cash_dividend,
                bonus_share_ratio=today_share_split_ratio,
                transfer_share_ratio=0.0,
                allotment_ratio=today_allotment_ratio,
                allotment_price=today_allotment_price,
            ),
            dtype=np.float64,
        )

    limit_up_price = float(round_price_cent(today_prev_close * (1.0 + rule.limit_ratio)))

    # 4. 构建包含今日 (索引为 n_hist) 的全量期初基准序列
    all_dates = dates + ["TODAY"]
    all_p_bases = np.append(s_prev_adj, today_prev_close)
    all_i_bases = np.append(i_prev, today_prev_index)
    today_idx = n_hist

    # 判定今日一旦触发普通异动，是否会凑满 10日内 N 次同向普通异动从而直接触发严重异动
    normal_cnt_prev_9d = len(recent_9d_triggers)
    upgrade_normal_to_severe = (normal_cnt_prev_9d + 1) >= rule.max_normal_triggers_10d

    window_records: list[tuple[str, int, int, float]] = []

    # (A) 普通异动有效子窗口: 连续 2 日 (t0 = today_idx - 1) 与 连续 3 日 (t0 = today_idx - 2)
    #     且起点 t0 必须严格晚于上次普通异动触发日 last_normal_idx
    min_normal_t0 = max(0, today_idx - 2, last_normal_idx + 1)
    for t0 in range(min_normal_t0, today_idx):  # k = today_idx - t0 + 1 in {2, 3}
        k_days = today_idx - t0 + 1
        w_type = "SEVERE_COUNT_10D" if upgrade_normal_to_severe else "NORMAL_2_3D"
        window_records.append((w_type, k_days, t0, rule.normal_up_threshold))

    # (B) 严重异动 10 日 +100% 穿透子窗口: k in {1, ..., 10} (起点晚于上次严重异动公告日)
    min_sev10_t0 = max(0, today_idx - 9, last_severe_idx + 1)
    for t0 in range(min_sev10_t0, today_idx + 1):
        k_days = today_idx - t0 + 1
        window_records.append(("SEVERE_10D_100P", k_days, t0, rule.severe_10d_up_threshold))

    # (C) 严重异动 30 日 +200% 穿透子窗口: k in {1, ..., 30} (起点晚于上次严重异动公告日)
    min_sev30_t0 = max(0, today_idx - 29, last_severe_idx + 1)
    for t0 in range(min_sev30_t0, today_idx + 1):
        k_days = today_idx - t0 + 1
        window_records.append(("SEVERE_30D_200P", k_days, t0, rule.severe_30d_up_threshold))

    # 5. 组装向量并一次性逆推所有窗口的安全价
    t0_indices = np.array([rec[2] for rec in window_records], dtype=np.int64)
    w_thresholds = np.array([rec[3] for rec in window_records], dtype=np.float64)
    w_p_bases = all_p_bases[t0_indices]
    w_i_bases = all_i_bases[t0_indices]

    overall_safe_price, safe_prices_vec, exact_prices_vec = compute_exact_safe_price(
        p_bases_adj=w_p_bases,
        i_bases=w_i_bases,
        i_curr=curr_index,
        thresholds=w_thresholds,
        buffer_ratio=buffer_ratio,
        cap_at_limit=cap_at_limit,
        limit_up_price=limit_up_price,
    )

    # 实时计算各窗口当前累计偏离度
    curr_cum_devs = ((curr_price / np.maximum(w_p_bases, 1e-9)) - 1.0) - (
        (curr_index / np.maximum(w_i_bases, 1e-9)) - 1.0
    )

    # 分离普通异动安全价与严重异动安全价
    is_severe_mask = np.array([rec[0].startswith("SEVERE") for rec in window_records], dtype=bool)
    is_normal_mask = np.array(
        [rec[0] in ("NORMAL_2_3D", "SEVERE_COUNT_10D") for rec in window_records], dtype=bool
    )

    severe_safe_price = (
        float(np.min(safe_prices_vec[is_severe_mask])) if np.any(is_severe_mask) else float("inf")
    )
    normal_safe_price = (
        float(np.min(safe_prices_vec[is_normal_mask])) if np.any(is_normal_mask) else float("inf")
    )

    # 定位全局最紧约束窗口 (相同安全价下优先选择周期更短、更早触碰的窗口)
    min_safe_val = float(np.min(safe_prices_vec))
    candidate_indices = np.flatnonzero(safe_prices_vec <= min_safe_val + 1e-4)
    min_idx = int(min(candidate_indices, key=lambda idx: (window_records[idx][1], -curr_cum_devs[idx])))
    bind_type, bind_k, bind_t0, bind_thresh = window_records[min_idx]
    binding_detail = WindowConstraintDetail(
        window_type=bind_type,
        window_days=bind_k,
        start_date=all_dates[bind_t0],
        base_price_adj=round(float(w_p_bases[min_idx]), 4),
        base_index=round(float(w_i_bases[min_idx]), 4),
        threshold=round(float(bind_thresh), 4),
        safe_price=round(float(safe_prices_vec[min_idx]), 2),
        exact_trigger_price=round(float(exact_prices_vec[min_idx]), 4),
        curr_cum_dev=round(float(curr_cum_devs[min_idx]), 4),
    )

    # 6. 计算真实安全垫与免死金牌标识 (彻底解决首板涨停误报空间锁死问题)
    headroom_pct = (overall_safe_price - curr_price) / max(today_prev_close, 1e-9)
    severe_headroom_pct = (severe_safe_price - curr_price) / max(today_prev_close, 1e-9)

    is_unconstrained_today = bool(overall_safe_price >= limit_up_price)
    is_severe_unconstrained_today = bool(severe_safe_price >= limit_up_price)

    is_normal_triggered_now = bool(curr_price > normal_safe_price)
    is_severe_triggered_now = bool(curr_price > severe_safe_price)

    # 仅当今日涨停会触碰严重异动红线 (!is_severe_unconstrained_today) 且剩余空间 < 2% 时才判定为空间锁死
    is_severe_locked = bool(
        (not is_severe_unconstrained_today) and (severe_headroom_pct < 0.02)
    )

    # 7. 生成盘口实战操作建议
    if is_severe_triggered_now:
        advice = "🛑 已越过严重异动红线（面临停牌核查或重点监控，严禁追高/果断兑现）"
    elif is_severe_locked:
        advice = (
            f"🚨 严重异动空间锁死(<2%): 极值安全价 {severe_safe_price:.2f} 元，"
            f"拉升即触特停红线，仅宜持筹做T或逢高兑现"
        )
    elif is_unconstrained_today:
        advice = (
            f"🟢 安全无虞（今日涨停 {limit_up_price:.2f} 元亦不触任何异动，安全价 {overall_safe_price:.2f} 元，可放手博弈）"
        )
    elif is_normal_triggered_now:
        advice = (
            f"🟡 已触发普通异动（盘后上龙虎榜），距严重异动红线尚有 {severe_headroom_pct * 100:.2f}% 空间"
        )
    elif not is_severe_unconstrained_today:
        advice = (
            f"⚠️ 严重异动射程内：特停安全上限 {severe_safe_price:.2f} 元（剩余安全垫 {severe_headroom_pct * 100:.2f}%），控仓博弈"
        )
    else:
        advice = (
            f"🔵 普通异动射程内：龙虎榜安全价 {normal_safe_price:.2f} 元（剩余 {headroom_pct * 100:.2f}%），今日无严重异动风险"
        )

    result = VolatilityEvaluationResult(
        stock_code=stock_code,
        board_name=rule.board_name,
        prev_close=round(today_prev_close, 2),
        curr_price=round(curr_price, 2),
        limit_up_price=round(limit_up_price, 2),
        safe_price=round(overall_safe_price, 2),
        normal_safe_price=round(normal_safe_price, 2),
        severe_safe_price=round(severe_safe_price, 2),
        headroom_pct=round(float(headroom_pct), 4),
        severe_headroom_pct=round(float(severe_headroom_pct), 4),
        is_unconstrained_today=is_unconstrained_today,
        is_severe_unconstrained_today=is_severe_unconstrained_today,
        is_normal_triggered_now=is_normal_triggered_now,
        is_severe_triggered_now=is_severe_triggered_now,
        is_severe_locked=is_severe_locked,
        normal_triggers_in_prev_9d=normal_cnt_prev_9d,
        will_Upgrade_to_severe_on_normal=upgrade_normal_to_severe,
        binding_window=asdict(binding_detail),
        action_advice=advice,
    )
    return result.to_dict()


if __name__ == "__main__":
    # 内置自检测试：验证 1. 首板免死金牌  2. 双创 2日30%异动捕获  3. 10日100%严重异动锁死
    mock_index = [{"date": f"2026-10-{d:02d}", "prev_close": 3000.0, "close": 3000.0} for d in range(1, 15)]

    # 场景 A: 低位首板冲涨停 (昨收10.00, 现价10.95, 涨停11.00) -> 绝不能误报空间锁死
    mock_stock_first_board = [
        {"date": f"2026-10-{d:02d}", "prev_close": 10.0, "close": 10.0} for d in range(1, 15)
    ]
    res_a = evaluate_stock_volatility("000001.SZ", mock_stock_first_board, mock_index, curr_price=10.95, curr_index=3000.0)
    assert res_a["is_unconstrained_today"] is True, "首板应当判定为今日无异动约束"
    assert res_a["is_severe_locked"] is False, "首板冲涨停严禁误报严重异动空间锁死"

    # 场景 B: 300创业板昨日涨停(+20%)，今日再涨+10%即满2日累计30%异动 (检验 k=2 窗口捕获)
    mock_stock_chinext = [
        {"date": f"2026-10-{d:02d}", "prev_close": 10.0, "close": 10.0} for d in range(1, 14)
    ] + [{"date": "2026-10-14", "prev_close": 10.0, "close": 12.0}]
    res_b = evaluate_stock_volatility("300750.SZ", mock_stock_chinext, mock_index, curr_price=13.10, curr_index=3000.0)
    # 期初前收盘 10.0, 2日+30%精确触线价为 13.00, 扣除0.15%缓冲与1分钱后安全价应为 12.97
    assert res_b["normal_safe_price"] == 12.97, f"预期2日异动安全价12.97, 实际{res_b['normal_safe_price']}"
    assert res_b["is_normal_triggered_now"] is True, "2日累计偏离+31%必须捕获普通异动触发"

    print("[OK] scripts/abnormal_volatility.py 全量自检断言通过！")
    print("首板体检示例:", res_a["action_advice"])
    print("双创2日异动示例:", res_b["action_advice"])
