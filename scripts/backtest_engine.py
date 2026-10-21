# -*- coding: utf-8 -*-
"""
backtest_engine.py - 机构级轻量量化回测引擎 (Quant Backtesting Engine)
专门针对 A 股交易规则与短线/波段交易逻辑设计：
  1. 严格遵守 A 股 T+1 交易制度（当日买入必须下一交易日方可卖出）
  2. 真实摩擦成本建模：佣金（双边万2.5）、印花税（卖出单边万5）、滑点（双边 0.1%）
  3. 100 股一手整倍数买入资金约束
  4. 预置四大实战策略：
     - Strategy 1: 'cycle_timing' - 92科比情绪周期宏观择时策略（消费 sentiment_history.jsonl）
     - Strategy 2: 'chan_breakout' - 缠论分型与中枢结构突破战法（基于 core.chan）
     - Strategy 3: 'double_ma' - 经典量化双均线放量趋势战法（MA5 x MA20）
     - Strategy 4: 'zt_momentum' - 龙头涨停打板次日冲高溢价战法
  5. 完整量化评估指标：累计收益、年化收益、基准对比、超额收益(Alpha)、夏普比率、最大回撤、交易胜率、盈亏比
"""

import sys
import os
import math
import json
import datetime as dt
from typing import List, Dict, Any, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import stock_dashboard as sd
import data_feed as df_feed
from core.chan import chan_analysis_structured, calc_ema

COMMISSION_RATE = 0.00025  # 双向佣金 万2.5 (最低5元由参数控制)
MIN_COMMISSION = 5.0
STAMP_DUTY_RATE = 0.0005   # 卖出印花税 万5
SLIPPAGE_RATE = 0.0010     # 滑点 0.1%


class BacktestResult:
    """回测结果统计对象"""

    def __init__(self, initial_capital: float = 100000.0):
        self.initial_capital = float(initial_capital)
        self.final_capital = float(initial_capital)
        self.total_return_pct = 0.0
        self.benchmark_return_pct = 0.0
        self.excess_return_pct = 0.0
        # None = 样本不足，无法年化（非 0，0 会被误读为"零收益"）
        self.annualized_return_pct = None
        self.max_drawdown_pct = 0.0
        self.sharpe_ratio = 0.0
        self.sortino_ratio = 0.0
        self.calmar_ratio = 0.0
        self.win_rate_pct = 0.0
        self.profit_loss_ratio = 0.0
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.avg_hold_days = 0.0
        self.equity_curve: List[Dict[str, Any]] = []
        self.trade_logs: List[Dict[str, Any]] = []
        self.warning_msg: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "initial_capital": round(self.initial_capital, 2),
            "final_capital": round(self.final_capital, 2),
            "total_return_pct": round(self.total_return_pct, 2),
            "benchmark_return_pct": round(self.benchmark_return_pct, 2),
            "excess_return_pct": round(self.excess_return_pct, 2),
            "annualized_return_pct": (round(self.annualized_return_pct, 2)
                                      if self.annualized_return_pct is not None else None),
            "sample_sufficient": self.annualized_return_pct is not None,
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 2) if self.sharpe_ratio is not None else None,
            "sortino_ratio": round(self.sortino_ratio, 2) if self.sortino_ratio is not None else None,
            "calmar_ratio": round(self.calmar_ratio, 2) if self.calmar_ratio is not None else None,
            "win_rate_pct": round(self.win_rate_pct, 2),
            "profit_loss_ratio": round(self.profit_loss_ratio, 2),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "avg_hold_days": round(self.avg_hold_days, 1),
            "equity_curve": self.equity_curve,
            "trade_logs": self.trade_logs,
            "warning_msg": self.warning_msg,
        }


def _calc_metrics(
    equity_curve: List[Dict[str, Any]],
    trade_logs: List[Dict[str, Any]],
    initial_capital: float,
    benchmark_start_p: float,
    benchmark_end_p: float,
    warning_msg: str = "",
) -> BacktestResult:
    """计算专业量化绩效指标"""
    res = BacktestResult(initial_capital)
    res.equity_curve = equity_curve
    res.trade_logs = trade_logs
    res.warning_msg = warning_msg

    if not equity_curve:
        return res

    final_equity = equity_curve[-1]["equity"]
    res.final_capital = final_equity
    res.total_return_pct = ((final_equity - initial_capital) / initial_capital) * 100.0

    # 基准收益
    if benchmark_start_p > 0 and benchmark_end_p > 0:
        res.benchmark_return_pct = ((benchmark_end_p - benchmark_start_p) / benchmark_start_p) * 100.0
    else:
        res.benchmark_return_pct = 0.0
    res.excess_return_pct = res.total_return_pct - res.benchmark_return_pct

    # 年化收益率 (按 242 交易日换算)
    # 修复 (2026-10-18): 旧实现无条件下算年化。当回测跨度极短（例如只有 14 笔交易、
    # 覆盖几个交易日）时，years = n_days/242 极小，1/years 巨大，年化被指数级放大，
    # 出现 "+82% 累计 → 401.6% 年化" 这种无意义数字。年化只有在样本足够长时
    # 才具统计意义；不足则置为 None，由前端显示"样本不足"。
    n_days = max(1, len(equity_curve))
    years = n_days / 242.0
    MIN_DAYS_FOR_ANNUALIZED = 60      # 少于约 3 个月不年化
    res.annualized_return_pct = None
    if years > 0 and final_equity > 0 and n_days >= MIN_DAYS_FOR_ANNUALIZED:
        res.annualized_return_pct = ((final_equity / initial_capital) ** (1.0 / years) - 1.0) * 100.0

    # 最大回撤
    peak = -1.0
    max_dd = 0.0
    daily_returns = []
    prev_eq = initial_capital
    for pt in equity_curve:
        eq = pt["equity"]
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
        pt["drawdown_pct"] = round(dd * 100.0, 2)
        # 日收益率
        d_ret = (eq - prev_eq) / prev_eq if prev_eq > 0 else 0.0
        daily_returns.append(d_ret)
        prev_eq = eq

    res.max_drawdown_pct = max_dd * 100.0

    # 夏普比率 (无风险利率 2.5% 年化)
    if len(daily_returns) > 2:
        mean_ret = sum(daily_returns) / len(daily_returns)
        var = sum((r - mean_ret) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
        std_ret = math.sqrt(var) if var > 1e-12 else 0.0
        rf_daily = 0.025 / 242.0
        if std_ret > 0:
            res.sharpe_ratio = ((mean_ret - rf_daily) / std_ret) * math.sqrt(242.0)

        # 索提诺比率 (Sortino Ratio - 业内对冲基金标准，仅惩罚负向波动)
        downside_diffs = [min(0.0, r - rf_daily) for r in daily_returns]
        downside_var = sum(d ** 2 for d in downside_diffs) / max(1, len(downside_diffs))
        downside_std = math.sqrt(downside_var) if downside_var > 1e-12 else 0.0
        if downside_std > 0:
            res.sortino_ratio = ((mean_ret - rf_daily) / downside_std) * math.sqrt(242.0)

    # 卡玛比率 (年化收益 / 最大回撤)
    # 年化可能为 None(样本不足)，此时卡玛同样不可信 -> 置 None
    if res.annualized_return_pct is not None and res.max_drawdown_pct > 0.01:
        res.calmar_ratio = res.annualized_return_pct / res.max_drawdown_pct
    else:
        res.calmar_ratio = None

    # 交易统计
    res.total_trades = len(trade_logs)
    if res.total_trades > 0:
        win_trades = [t for t in trade_logs if t.get("pnl", 0) > 0]
        loss_trades = [t for t in trade_logs if t.get("pnl", 0) <= 0]
        res.winning_trades = len(win_trades)
        res.losing_trades = len(loss_trades)
        res.win_rate_pct = (res.winning_trades / res.total_trades) * 100.0

        total_gain = sum(t["pnl"] for t in win_trades)
        total_loss = abs(sum(t["pnl"] for t in loss_trades))
        if total_loss > 0:
            res.profit_loss_ratio = total_gain / total_loss
        elif total_gain > 0:
            res.profit_loss_ratio = 99.9

        res.avg_hold_days = sum(t.get("hold_days", 1) for t in trade_logs) / res.total_trades

    return res


# ==============================================================================
# 策略一：92科比情绪周期动态仓位宏观择时策略 (Cycle Timing)
# ==============================================================================
def backtest_cycle_timing(
    initial_capital: float = 100000.0,
    benchmark_code: str = "sh000001",
) -> BacktestResult:
    """
    回测逻辑：
      根据 sentiment_history.jsonl 中记录的真实历史情绪周期与状态迁移，
      动态调整大盘多头仓位比例：
        - 主升期 (Master Rise): 85% 仓位
        - 相持/震荡期 (Stalemate): 50% 仓位
        - 退潮期 (Ebb Tide): 10% 仓位 (大部队空仓防守避险，保住胜利果实)
        - 冰点期 (Ice Point): 20% 仓位 (左侧低吸试错)
      基准：上证指数全天候 100% 满仓不动。
    """
    hist_file = os.path.join(sd.DATA_DIR, "sentiment_history.jsonl")
    if not os.path.exists(hist_file):
        hist_file = os.path.join(ROOT_DIR, "data", "stock_data", "sentiment_history.jsonl")

    records = []
    if os.path.exists(hist_file):
        with open(hist_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        pass

    # 按日期升序排序
    records.sort(key=lambda x: str(x.get("date", "")))
    if not records:
        return BacktestResult(initial_capital)

    # 获取基准指数日K线
    bm_kl = df_feed.get_kline_cached(benchmark_code, 160) or []
    bm_dict = {}
    for r in bm_kl:
        d_clean = str(r[0]).replace("-", "")
        bm_dict[d_clean] = {
            "date": r[0],
            "open": float(r[1]),
            "close": float(r[2]),
            "pct": round(((float(r[2]) - float(r[1])) / float(r[1])) * 100.0, 2),
        }

    STAGE_POS = {
        "主升": 0.85,
        "亢奋": 0.70,
        "震荡": 0.50,
        "相持": 0.50,
        "中性": 0.50,
        "冰点": 0.20,
        "退潮": 0.10,
    }

    capital = initial_capital
    equity_curve = []
    trade_logs = []
    prev_stage = None
    prev_date = None
    bm_start_p = None
    bm_end_p = None

    for i, rec in enumerate(records):
        d_str = str(rec.get("date", ""))
        stage = rec.get("stage", "中性")
        score = rec.get("score", 50.0)

        bm_info = bm_dict.get(d_str)
        if not bm_info:
            continue

        c_price = bm_info["close"]
        if bm_start_p is None:
            bm_start_p = c_price
        bm_end_p = c_price

        if prev_date and prev_date in bm_dict:
            day_return_pct = ((c_price - bm_dict[prev_date]["close"]) / bm_dict[prev_date]["close"])
        else:
            day_return_pct = (c_price - bm_info["open"]) / bm_info["open"]

        target_pos = STAGE_POS.get(stage, 0.40)
        if stage == "退潮" and score < 38:
            target_pos = 0.05

        if prev_stage != stage:
            trade_logs.append({
                "date": bm_info["date"],
                "action": f"情绪迁移动态调仓: {prev_stage or '初始化'} → {stage}",
                "target_pos_pct": int(target_pos * 100),
                "reason": f"92科比周期定位【{stage}】，情绪分 {score}，设防御仓位 {int(target_pos*100)}%",
                "pnl": 0.0,
                "pnl_pct": 0.0,
                "hold_days": 1,
            })
            prev_stage = stage

        daily_pnl = capital * target_pos * day_return_pct
        prev_pos = (equity_curve[-1]["pos_pct"] / 100.0) if equity_curve else target_pos
        friction = capital * abs(target_pos - prev_pos) * (COMMISSION_RATE + SLIPPAGE_RATE)
        capital += (daily_pnl - friction)

        equity_curve.append({
            "date": bm_info["date"],
            "equity": round(capital, 2),
            "stage": stage,
            "score": round(score, 1),
            "pos_pct": int(target_pos * 100),
            "benchmark_close": c_price,
        })
        prev_date = d_str

    return _calc_metrics(
        equity_curve,
        trade_logs,
        initial_capital,
        bm_start_p or 1.0,
        bm_end_p or 1.0,
    )


# ==============================================================================
# 策略二：缠论分型与中枢结构战法单股回测 (Chan Breakout)
# ==============================================================================
def backtest_chan_strategy(
    code: str,
    days: int = 120,
    initial_capital: float = 100000.0,
    stop_loss_pct: float = 5.0,
    take_profit_pct: float = 15.0,
) -> BacktestResult:
    """
    单股缠论量化策略：
      - 买入信号：缠论底分型确认 / 一买候选 / 二买候选 / 三买确认，且收盘价站上 EMA5。
      - 卖出信号：缠论顶分型确认 / 一卖二卖警戒，或跌破 EMA20，或硬止损 5%，或止盈 15%。
      - 遵循 T+1 交易制度与万2.5佣金/万5印花税。
    """
    code_clean = str(code).strip()
    full_code = ("sh" + code_clean) if code_clean.startswith(("6", "5", "9")) else ("sz" + code_clean)

    kl = df_feed.get_kline_cached(full_code, days)
    if not kl or len(kl) < 35:
        return BacktestResult(initial_capital)

    # 资金保护校验：若高价股单手成本超过初始资金，自适应调整初始本金模拟基准
    sample_p = float(kl[-1][2])
    warning_msg = ""
    adj_capital = initial_capital
    if sample_p * 100 > initial_capital * 0.95:
        adj_capital = math.ceil((sample_p * 100 * 1.5) / 10000.0) * 10000.0
        warning_msg = f"提示: 该标的高达 ¥{sample_p:.2f}，单手(100股)需 ¥{sample_p*100:,.0f}，初始本金已自适应适配为 ¥{adj_capital:,.0f}"

    cash = adj_capital
    holding_shares = 0
    buy_price = 0.0
    buy_date = ""
    buy_bar_idx = -1

    equity_curve = []
    trade_logs = []

    for i in range(30, len(kl)):
        cur_bar = kl[i]
        cur_date, c_open, c_close, c_high, c_low = cur_bar[0], float(cur_bar[1]), float(cur_bar[2]), float(cur_bar[3]), float(cur_bar[4])

        sub_kl = kl[: i + 1]
        chan_res = chan_analysis_structured(sub_kl, full_code)
        signals = chan_res.get("signals") or []

        closes_so_far = [float(b[2]) for b in sub_kl]
        ema5 = calc_ema(closes_so_far, 5)[-1]
        ema20 = calc_ema(closes_so_far, 20)[-1]

        has_buy_signal = False
        buy_reason = ""
        for sig in signals[-3:]:
            stype = sig.get("type", "")
            if any(k in stype for k in ["一买", "二买", "三买", "底背驰"]):
                if c_close >= ema5:
                    has_buy_signal = True
                    buy_reason = f"缠论[{stype}]确认，收盘价({c_close:.2f})站上EMA5({ema5:.2f})"
                    break

        has_sell_signal = False
        sell_reason = ""
        for sig in signals[-3:]:
            stype = sig.get("type", "")
            if any(k in stype for k in ["一卖", "二卖", "三卖", "顶背驰"]):
                has_sell_signal = True
                sell_reason = f"缠论[{stype}]离场防守"
                break

        if holding_shares > 0:
            hold_days = i - buy_bar_idx
            pnl_pct = ((c_close - buy_price) / buy_price) * 100.0

            should_exit = False
            if hold_days >= 1:
                if pnl_pct <= -abs(stop_loss_pct):
                    should_exit = True
                    sell_reason = f"硬止损触发 (跌幅 {pnl_pct:.2f}% <= -{stop_loss_pct}%)"
                elif pnl_pct >= abs(take_profit_pct):
                    should_exit = True
                    sell_reason = f"止盈达标离场 (涨幅 {pnl_pct:.2f}% >= +{take_profit_pct}%)"
                elif c_close < ema20:
                    should_exit = True
                    sell_reason = f"跌破EMA20生命线({ema20:.2f})破位止损"
                elif has_sell_signal:
                    should_exit = True

            if should_exit:
                exec_price = c_close * (1.0 - SLIPPAGE_RATE)
                gross_amt = holding_shares * exec_price
                comm = max(MIN_COMMISSION, gross_amt * COMMISSION_RATE)
                stamp = gross_amt * STAMP_DUTY_RATE
                net_amt = gross_amt - comm - stamp
                pnl = net_amt - (holding_shares * buy_price)
                cash += net_amt

                trade_logs.append({
                    "date": cur_date,
                    "buy_date": buy_date,
                    "buy_price": round(buy_price, 2),
                    "sell_price": round(exec_price, 2),
                    "shares": holding_shares,
                    "hold_days": hold_days,
                    "pnl": round(pnl, 2),
                    "pnl_pct": round(pnl_pct, 2),
                    "reason": sell_reason,
                })
                holding_shares = 0
                buy_price = 0.0

        elif holding_shares == 0 and has_buy_signal:
            exec_price = c_close * (1.0 + SLIPPAGE_RATE)
            max_shares = int((cash * 0.95) / (exec_price * 100)) * 100
            if max_shares >= 100:
                cost = max_shares * exec_price
                comm = max(MIN_COMMISSION, cost * COMMISSION_RATE)
                total_cost = cost + comm
                if cash >= total_cost:
                    cash -= total_cost
                    holding_shares = max_shares
                    buy_price = exec_price
                    buy_date = cur_date
                    buy_bar_idx = i

        cur_pos_val = holding_shares * c_close
        tot_eq = cash + cur_pos_val
        equity_curve.append({
            "date": cur_date,
            "equity": round(tot_eq, 2),
            "holding_shares": holding_shares,
            "close_price": c_close,
        })

    bm_start = float(kl[30][2])
    bm_end = float(kl[-1][2])
    return _calc_metrics(equity_curve, trade_logs, adj_capital, bm_start, bm_end, warning_msg)


# ==============================================================================
# 策略三：双均线放量趋势战法 (Double MA Breakout)
# ==============================================================================
def backtest_double_ma_strategy(
    code: str,
    days: int = 120,
    initial_capital: float = 100000.0,
    ma_fast: int = 5,
    ma_slow: int = 20,
    vol_ratio: float = 1.0,
    stop_loss_pct: float = 6.0,
) -> BacktestResult:
    """
    量化双均线放量趋势策略：
      - 买入：MA(fast) 上穿 MA(slow) 且满足放量确认
      - 卖出：MA(fast) 下穿 MA(slow) 或 触发止损 (-6%)
      - 遵循 T+1 交易制度与真实摩擦成本
    """
    code_clean = str(code).strip()
    full_code = ("sh" + code_clean) if code_clean.startswith(("6", "5", "9")) else ("sz" + code_clean)

    kl = df_feed.get_kline_cached(full_code, days)
    if not kl or len(kl) < ma_slow + 5:
        return BacktestResult(initial_capital)

    sample_p = float(kl[-1][2])
    warning_msg = ""
    adj_capital = initial_capital
    if sample_p * 100 > initial_capital * 0.95:
        adj_capital = math.ceil((sample_p * 100 * 1.5) / 10000.0) * 10000.0
        warning_msg = f"提示: 该标的高达 ¥{sample_p:.2f}，单手(100股)需 ¥{sample_p*100:,.0f}，初始本金已自适应适配为 ¥{adj_capital:,.0f}"

    cash = adj_capital
    holding_shares = 0
    buy_price = 0.0
    buy_date = ""
    buy_bar_idx = -1

    equity_curve = []
    trade_logs = []

    closes = [float(b[2]) for b in kl]
    volumes = [float(b[5]) for b in kl]

    for i in range(ma_slow, len(kl)):
        cur_bar = kl[i]
        cur_date, c_close = cur_bar[0], float(cur_bar[2])

        ma_f = sum(closes[i - ma_fast + 1 : i + 1]) / ma_fast
        ma_s = sum(closes[i - ma_slow + 1 : i + 1]) / ma_slow
        ma_f_prev = sum(closes[i - ma_fast : i]) / ma_fast
        ma_s_prev = sum(closes[i - ma_slow : i]) / ma_slow

        avg_vol5 = sum(volumes[i - 5 : i]) / 5.0 if i >= 5 else volumes[i]
        cur_vol = volumes[i]

        is_golden_cross = (ma_f_prev <= ma_s_prev) and (ma_f > ma_s)
        is_vol_ok = (cur_vol >= avg_vol5 * vol_ratio) if vol_ratio > 0 else True
        is_death_cross = (ma_f_prev >= ma_s_prev) and (ma_f < ma_s)

        if holding_shares > 0:
            hold_days = i - buy_bar_idx
            pnl_pct = ((c_close - buy_price) / buy_price) * 100.0

            should_exit = False
            sell_reason = ""
            if hold_days >= 1:
                if pnl_pct <= -abs(stop_loss_pct):
                    should_exit = True
                    sell_reason = f"硬止损触发 (亏损 {pnl_pct:.2f}% <= -{stop_loss_pct}%)"
                elif is_death_cross:
                    should_exit = True
                    sell_reason = f"MA{ma_fast}死叉MA{ma_slow}离场"

            if should_exit:
                exec_price = c_close * (1.0 - SLIPPAGE_RATE)
                gross_amt = holding_shares * exec_price
                comm = max(MIN_COMMISSION, gross_amt * COMMISSION_RATE)
                stamp = gross_amt * STAMP_DUTY_RATE
                net_amt = gross_amt - comm - stamp
                pnl = net_amt - (holding_shares * buy_price)
                cash += net_amt

                trade_logs.append({
                    "date": cur_date,
                    "buy_date": buy_date,
                    "buy_price": round(buy_price, 2),
                    "sell_price": round(exec_price, 2),
                    "shares": holding_shares,
                    "hold_days": hold_days,
                    "pnl": round(pnl, 2),
                    "pnl_pct": round(pnl_pct, 2),
                    "reason": sell_reason,
                })
                holding_shares = 0
                buy_price = 0.0

        elif holding_shares == 0 and is_golden_cross and is_vol_ok:
            exec_price = c_close * (1.0 + SLIPPAGE_RATE)
            max_shares = int((cash * 0.95) / (exec_price * 100)) * 100
            if max_shares >= 100:
                cost = max_shares * exec_price
                comm = max(MIN_COMMISSION, cost * COMMISSION_RATE)
                total_cost = cost + comm
                if cash >= total_cost:
                    cash -= total_cost
                    holding_shares = max_shares
                    buy_price = exec_price
                    buy_date = cur_date
                    buy_bar_idx = i

        cur_pos_val = holding_shares * c_close
        equity_curve.append({
            "date": cur_date,
            "equity": round(cash + cur_pos_val, 2),
            "holding_shares": holding_shares,
            "close_price": c_close,
        })

    bm_start = float(kl[ma_slow][2])
    bm_end = float(kl[-1][2])
    return _calc_metrics(equity_curve, trade_logs, adj_capital, bm_start, bm_end, warning_msg)


# ==============================================================================
# 策略四：龙头首板/连板次日竞价溢价套利策略 (ZT Momentum Overnight)
# ==============================================================================
def backtest_zt_momentum_strategy(
    code: str,
    days: int = 120,
    initial_capital: float = 100000.0,
    take_profit_pct: float = 8.0,
    stop_loss_pct: float = 4.0,
) -> BacktestResult:
    """
    超短连板/首板冲高套利战法：
      - 买入：个股出现涨停板 (涨幅 >= 9.8% 或 创业板/科创板 >= 19.8%)，尾盘/竞价买入
      - 卖出：T+1 开盘冲高止盈 (默认 +8%) 或 跌破止损 (-4%) 或 次日尾盘无条件离场 (持仓恒定 1 天)
    """
    code_clean = str(code).strip()
    full_code = ("sh" + code_clean) if code_clean.startswith(("6", "5", "9")) else ("sz" + code_clean)

    kl = df_feed.get_kline_cached(full_code, days)
    if not kl or len(kl) < 15:
        return BacktestResult(initial_capital)

    sample_p = float(kl[-1][2])
    warning_msg = ""
    adj_capital = initial_capital
    if sample_p * 100 > initial_capital * 0.95:
        adj_capital = math.ceil((sample_p * 100 * 1.5) / 10000.0) * 10000.0
        warning_msg = f"提示: 该标的高达 ¥{sample_p:.2f}，初始本金自适应适配为 ¥{adj_capital:,.0f}"

    cash = adj_capital
    holding_shares = 0
    buy_price = 0.0
    buy_date = ""
    buy_bar_idx = -1

    equity_curve = []
    trade_logs = []

    # 涨停板阈值判定
    zt_threshold = 19.5 if code_clean.startswith(("30", "688")) else 9.75

    for i in range(1, len(kl)):
        prev_close = float(kl[i - 1][2])
        cur_bar = kl[i]
        cur_date, c_open, c_close, c_high, c_low = cur_bar[0], float(cur_bar[1]), float(cur_bar[2]), float(cur_bar[3]), float(cur_bar[4])

        day_pct = ((c_close - prev_close) / prev_close) * 100.0
        is_limit_up = (day_pct >= zt_threshold)

        # 持仓退出检测 (超短套利恒定持股 1~2 天)
        if holding_shares > 0:
            hold_days = i - buy_bar_idx
            # 次日盘中冲高溢价
            high_pct = ((c_high - buy_price) / buy_price) * 100.0
            open_pct = ((c_open - buy_price) / buy_price) * 100.0
            close_pct = ((c_close - buy_price) / buy_price) * 100.0

            should_exit = False
            exec_price = c_close
            sell_reason = ""

            if hold_days >= 1:
                if high_pct >= take_profit_pct:
                    should_exit = True
                    exec_price = buy_price * (1.0 + take_profit_pct / 100.0)
                    sell_reason = f"次日冲高止盈达成 (+{take_profit_pct}%)"
                elif open_pct <= -stop_loss_pct:
                    should_exit = True
                    exec_price = c_open
                    sell_reason = f"次日开盘低开止损 (-{stop_loss_pct}%)"
                else:
                    # 尾盘离场
                    should_exit = True
                    exec_price = c_close
                    sell_reason = "超短隔夜溢价 T+1 尾盘离场"

            if should_exit:
                exec_price = exec_price * (1.0 - SLIPPAGE_RATE)
                gross_amt = holding_shares * exec_price
                comm = max(MIN_COMMISSION, gross_amt * COMMISSION_RATE)
                stamp = gross_amt * STAMP_DUTY_RATE
                net_amt = gross_amt - comm - stamp
                pnl = net_amt - (holding_shares * buy_price)
                cash += net_amt
                pnl_pct = ((exec_price - buy_price) / buy_price) * 100.0

                trade_logs.append({
                    "date": cur_date,
                    "buy_date": buy_date,
                    "buy_price": round(buy_price, 2),
                    "sell_price": round(exec_price, 2),
                    "shares": holding_shares,
                    "hold_days": hold_days,
                    "pnl": round(pnl, 2),
                    "pnl_pct": round(pnl_pct, 2),
                    "reason": sell_reason,
                })
                holding_shares = 0
                buy_price = 0.0

        elif holding_shares == 0 and is_limit_up:
            exec_price = c_close * (1.0 + SLIPPAGE_RATE)
            max_shares = int((cash * 0.95) / (exec_price * 100)) * 100
            if max_shares >= 100:
                cost = max_shares * exec_price
                comm = max(MIN_COMMISSION, cost * COMMISSION_RATE)
                total_cost = cost + comm
                if cash >= total_cost:
                    cash -= total_cost
                    holding_shares = max_shares
                    buy_price = exec_price
                    buy_date = cur_date
                    buy_bar_idx = i

        cur_pos_val = holding_shares * c_close
        equity_curve.append({
            "date": cur_date,
            "equity": round(cash + cur_pos_val, 2),
            "holding_shares": holding_shares,
            "close_price": c_close,
        })

    bm_start = float(kl[1][2])
    bm_end = float(kl[-1][2])
    return _calc_metrics(equity_curve, trade_logs, adj_capital, bm_start, bm_end, warning_msg)


def get_available_strategies() -> List[Dict[str, Any]]:
    """返回所有支持的回测策略描述清单"""
    return [
        {
            "key": "cycle",
            "name": "92科比情绪周期宏观择时策略",
            "desc": "基于全网第一手情绪周期(主升/震荡/退潮/冰点)动态分配多头仓位。退潮期严格1成轻仓规避高位补跌，主升期8.5成进攻。",
            "default_code": "sh000001",
            "type": "macro_timing",
        },
        {
            "key": "chan",
            "name": "缠论分型与中枢结构突破战法",
            "desc": "基于缠论纯算力引擎(底背驰、一买、二买、三买确认)开仓，顶分型或跌破EMA20生命线止损，自带15%止盈机制。",
            "default_code": "002696",
            "type": "stock_chan",
        },
        {
            "key": "ma",
            "name": "经典量化双均线放量趋势战法",
            "desc": "MA5上穿MA20金叉且成交量有效放大时建仓，死叉或触及-6%止损线离场，经典中线趋势量化跟踪。",
            "default_code": "002696",
            "type": "trend_following",
        },
        {
            "key": "zt",
            "name": "龙头首板/连板次日溢价超短套利",
            "desc": "捕捉个股涨停板动量进场，次日开盘利用短线冲高流动性(+8%止盈或T+1尾盘)落袋为安，超短胜率验证。",
            "default_code": "002696",
            "type": "short_term_momentum",
        },
    ]


def run_strategy(
    strategy: str,
    code: str = "sh000001",
    days: int = 120,
    initial_capital: float = 100000.0,
    **kwargs,
) -> Dict[str, Any]:
    """统一回测调用入口"""
    strat = strategy.lower().strip()
    if strat in ["cycle", "cycle_timing", "kobe", "92kobe"]:
        res = backtest_cycle_timing(initial_capital=initial_capital, benchmark_code=code)
    elif strat in ["chan", "chan_breakout", "chan_theory"]:
        res = backtest_chan_strategy(code=code, days=days, initial_capital=initial_capital)
    elif strat in ["ma", "double_ma", "ma_cross"]:
        res = backtest_double_ma_strategy(code=code, days=days, initial_capital=initial_capital)
    elif strat in ["zt", "zt_momentum", "limit_up"]:
        res = backtest_zt_momentum_strategy(code=code, days=days, initial_capital=initial_capital)
    else:
        res = backtest_cycle_timing(initial_capital=initial_capital, benchmark_code=code)

    return {
        "status": "ok",
        "strategy": strat,
        "code": code,
        "summary": res.to_dict(),
    }


def print_cli_report(res_dict: Dict[str, Any]):
    """打印命令行可视化对账报告"""
    summary = res_dict.get("summary", {})
    strat = res_dict.get("strategy", "")
    code = res_dict.get("code", "")

    print("\n" + "=" * 65)
    print(f"       📊 量化回测对账报告 · 终端实测 [策略: {strat.upper()} | 标的: {code}]")
    print("=" * 65)
    if summary.get("warning_msg"):
        print(f"  🔔 {summary['warning_msg']}")
        print("-" * 65)
    print(f"  初始本金:   ¥{summary.get('initial_capital', 0):,.2f}")
    print(f"  最终资产:   ¥{summary.get('final_capital', 0):,.2f}")
    print(f"  策略累计收益: {summary.get('total_return_pct', 0):+.2f}%   (基准收益: {summary.get('benchmark_return_pct', 0):+.2f}%)")
    print(f"  超额Alpha:   {summary.get('excess_return_pct', 0):+.2f}%")
    _ann = summary.get('annualized_return_pct')
    print(f"  年化收益率:   {_ann:+.2f}%" if _ann is not None
          else "  年化收益率:   样本不足，不年化")
    print(f"  最大回撤:    {summary.get('max_drawdown_pct', 0):.2f}%")
    print(f"  夏普比率:    {summary.get('sharpe_ratio', 0):.2f}    (索提诺比率: {summary.get('sortino_ratio', 0):.2f})")
    print(f"  卡玛比率:    {summary.get('calmar_ratio', 0):.2f}")
    print("-" * 65)
    print(f"  总交易笔数:  {summary.get('total_trades', 0)} 笔 (盈利 {summary.get('winning_trades', 0)} / 亏损 {summary.get('losing_trades', 0)})")
    print(f"  交易胜率:    {summary.get('win_rate_pct', 0):.1f}%")
    print(f"  盈亏比:      {summary.get('profit_loss_ratio', 0):.2f}")
    print(f"  平均持仓天数: {summary.get('avg_hold_days', 0):.1f} 天")
    print("=" * 65)

    logs = summary.get("trade_logs", [])
    if logs:
        print("\n  [最近交易流水明细 (前5笔)]:")
        for t in logs[-5:]:
            action = t.get("action") or f"买入 {t.get('buy_date')} @ ¥{t.get('buy_price')} -> 卖出 {t.get('date')} @ ¥{t.get('sell_price')}"
            pnl_info = f"盈亏: {t.get('pnl', 0):+,.1f}元 ({t.get('pnl_pct', 0):+.2f}%)" if "pnl" in t else ""
            print(f"   * [{t.get('date')}] {action} | {pnl_info} | 原因: {t.get('reason')}")
    print("\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="A股轻量量化回测引擎")
    parser.add_argument("--strategy", type=str, default="cycle", choices=["cycle", "chan", "ma", "zt"], help="回测策略选择")
    parser.add_argument("--code", type=str, default="sh000001", help="回测标的代码")
    parser.add_argument("--days", type=int, default=120, help="回测天数")
    parser.add_argument("--capital", type=float, default=100000.0, help="初始资金")

    args = parser.parse_args()
    report = run_strategy(args.strategy, args.code, args.days, args.capital)
    print_cli_report(report)
