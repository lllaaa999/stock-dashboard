# -*- coding: utf-8 -*-
"""
paper_trading.py —— 模拟自动交易引擎 (Paper Trading Engine)

设计目标
--------------------------------------------------------------------------
用**同一套**撮合/记账逻辑，同时支持两种驱动方式：

  1. 历史回放模式 (replay / backtest)
     把真实历史 K 线逐根喂给引擎，每根 K 线：
       - 用「本根收盘前可见的信息」产生信号
       - 按「下一根开盘价」成交（避免未来函数 / look-ahead bias）
       - 逐笔记录成交、持仓、权益曲线

  2. 实时纸上交易模式 (live / paper)
     对接现有行情接口，每次轮询产生信号并记账。同样不真下单，
     但会持久化到 data/stock_data/paper_*.jsonl，可跨进程重启继续。

关键约束（与 A 股实盘一致）
--------------------------------------------------------------------------
  · T+1：当日买入的股份，次一交易日才能卖出
  · 100 股一手，买入数量必须是 100 的整数倍
  · 佣金双边万 2.5（最低 5 元）、印花税卖出万 5、滑点双边 0.1%
  · 涨跌停无法成交（涨停买不进 / 跌停卖不出）
  · 停牌（成交量为 0）跳过

为什么单独成文件而不改 backtest_engine.py
--------------------------------------------------------------------------
backtest_engine 里 4 个策略各写了一套循环和记账，逻辑重复且各自维护。
本模块抽出统一的 SimBroker（撮合 + 账户），策略只需给出 target_action，
便于未来接入实盘通道时只替换 broker 实现。
"""

import os
import json
import math
import datetime as dt
from typing import List, Dict, Any, Optional, Callable

import data_feed as df_feed
from core.chan import chan_analysis_structured, calc_ema
try:
    import position_gate as pg
except ImportError:
    from scripts import position_gate as pg

# ---------- 交易成本与规则常量 ----------
COMMISSION_RATE = 0.00025     # 佣金 万 2.5
MIN_COMMISSION = 5.0          # 单笔最低佣金
STAMP_DUTY_RATE = 0.0005      # 印花税（仅卖出）
SLIPPAGE_RATE = 0.0010        # 滑点 0.1%
LOT_SIZE = 100                # 一手 = 100 股
PRICE_TICK = 0.01             # 最小价格变动


def _round_tick(p: float) -> float:
    """价格对齐到最小变动单位（分）"""
    return round(round(p / PRICE_TICK) * PRICE_TICK, 2)


def _limit_prices(prev_close: float, code: str) -> tuple:
    """按板块规则计算涨跌停价（主板 10%、创业板/科创板 20%、ST 5%、北交所 30%）

    这里只做粗略判断：以代码前缀区分板块，ST 无法从代码判断，交由调用方
    传入的 pct 覆盖（或忽略）。返回 (涨停价, 跌停价)。
    """
    c = str(code).replace('sh', '').replace('sz', '').replace('bj', '')
    if c.startswith(('300', '301', '688', '689')):
        pct = 0.20
    elif c.startswith(('8', '4', '920')):
        pct = 0.30
    else:
        pct = 0.10
    return _round_tick(prev_close * (1 + pct)), _round_tick(prev_close * (1 - pct))


class SimBroker:
    """模拟券商：负责撮合、费用计算、账户记账

    与实盘券商接口保持相似形状（buy/sell/持仓/权益），
    未来接真实通道时只需替换本类的成交实现。
    """

    def __init__(self, cash: float = 100000.0):
        self.initial_cash = float(cash)
        self.cash = float(cash)
        self.position: Dict[str, Dict[str, Any]] = {}   # {code: {shares, cost, last_buy_date, ...}}
        self.trades: List[Dict[str, Any]] = []          # 成交明细
        self.rejects: List[Dict[str, Any]] = []         # 被拒绝的委托及原因
        self.equity_curve: List[Dict[str, Any]] = []

    # ---------- 账户视图 ----------
    def shares_of(self, code: str) -> int:
        return int(self.position.get(code, {}).get('shares', 0))

    def market_value(self, prices: Dict[str, float]) -> float:
        mv = 0.0
        for code, pos in self.position.items():
            p = prices.get(code)
            if p:
                mv += pos['shares'] * p
        return mv

    def total_equity(self, prices: Dict[str, float]) -> float:
        return self.cash + self.market_value(prices)

    def can_sell(self, code: str, date: str) -> bool:
        """T+1 校验：当日买入的股份当日不可卖"""
        pos = self.position.get(code)
        if not pos or pos['shares'] <= 0:
            return False
        return str(pos.get('last_buy_date', '')) < str(date)

    # ---------- 撮合 ----------
    def buy(self, code: str, price: float, date: str, reason: str = '',
            budget_ratio: float = 1.0) -> Optional[Dict[str, Any]]:
        """按「可用资金 × budget_ratio」买入，自动取整到 100 股整数倍

        :return: 成交记录 dict；若资金不足/不合规返回 None（同时记入 rejects）
        """
        if price <= 0:
            self._reject(code, date, 'buy', '价格非法', price)
            return None
        exec_price = _round_tick(price * (1 + SLIPPAGE_RATE))
        budget = self.cash * max(0.0, min(1.0, budget_ratio))
        lots = int(budget // (exec_price * LOT_SIZE))
        if lots <= 0:
            self._reject(code, date, 'buy', '资金不足一手', exec_price)
            return None
        shares = lots * LOT_SIZE
        gross = shares * exec_price
        comm = max(MIN_COMMISSION, gross * COMMISSION_RATE)
        total_cost = gross + comm
        if total_cost > self.cash + 1e-9:
            shares -= LOT_SIZE
            if shares <= 0:
                self._reject(code, date, 'buy', '资金不足(含佣金)', exec_price)
                return None
            gross = shares * exec_price
            comm = max(MIN_COMMISSION, gross * COMMISSION_RATE)
            total_cost = gross + comm

        self.cash -= total_cost
        pos = self.position.setdefault(code, {'shares': 0, 'cost': 0.0, 'last_buy_date': ''})
        # 移动加权成本（含买入佣金）
        new_shares = pos['shares'] + shares
        pos['cost'] = (pos['cost'] * pos['shares'] + total_cost) / new_shares if new_shares else 0.0
        pos['shares'] = new_shares
        pos['last_buy_date'] = str(date)

        rec = {'date': date, 'code': code, 'side': 'buy', 'price': exec_price,
               'shares': shares, 'amount': round(gross, 2), 'commission': round(comm, 2),
               'stamp_duty': 0.0, 'cash_after': round(self.cash, 2), 'reason': reason}
        self.trades.append(rec)
        return rec

    def sell(self, code: str, price: float, date: str, reason: str = '',
             ratio: float = 1.0) -> Optional[Dict[str, Any]]:
        """卖出（默认全平；ratio<1 时分批卖）"""
        pos = self.position.get(code)
        if not pos or pos['shares'] <= 0:
            self._reject(code, date, 'sell', '无持仓', price)
            return None
        if not self.can_sell(code, date):
            self._reject(code, date, 'sell', 'T+1限制：当日买入不可卖', price)
            return None
        if price <= 0:
            self._reject(code, date, 'sell', '价格非法', price)
            return None

        exec_price = _round_tick(price * (1 - SLIPPAGE_RATE))
        shares = pos['shares'] if ratio >= 1.0 else int(pos['shares'] * ratio // LOT_SIZE) * LOT_SIZE
        if shares <= 0:
            self._reject(code, date, 'sell', '卖出数量不足一手', exec_price)
            return None

        gross = shares * exec_price
        comm = max(MIN_COMMISSION, gross * COMMISSION_RATE)
        stamp = gross * STAMP_DUTY_RATE
        net = gross - comm - stamp
        self.cash += net

        avg_cost = pos['cost']
        cost_basis = avg_cost * shares
        pnl = net - cost_basis

        pos['shares'] -= shares
        # 剩余持仓的成本单价不变（移动加权成本不因卖出而改变）
        if pos['shares'] <= 0:
            self.position.pop(code, None)

        rec = {'date': date, 'code': code, 'side': 'sell', 'price': exec_price,
               'shares': shares, 'amount': round(gross, 2), 'commission': round(comm, 2),
               'stamp_duty': round(stamp, 2), 'cash_after': round(self.cash, 2),
               'pnl': round(pnl, 2), 'reason': reason}
        self.trades.append(rec)
        return rec

    def _reject(self, code, date, side, why, price):
        self.rejects.append({'date': date, 'code': code, 'side': side,
                             'reason': why, 'price': round(float(price or 0), 2)})

    # ---------- 快照 ----------
    def snapshot(self, date: str, prices: Dict[str, float]) -> Dict[str, Any]:
        mv = self.market_value(prices)
        eq = self.cash + mv
        snap = {'date': date, 'cash': round(self.cash, 2), 'market_value': round(mv, 2),
                'equity': round(eq, 2),
                'return_pct': round((eq / self.initial_cash - 1) * 100, 2) if self.initial_cash else 0.0,
                'positions': {c: p['shares'] for c, p in self.position.items()}}
        self.equity_curve.append(snap)
        return snap


# ============================================================
# 策略信号函数：输入「截至当前可见的 K 线」，输出动作
# ============================================================

def signal_chan(kl_so_far: List[Any], holding: bool) -> Dict[str, Any]:
    """缠论策略信号

    买入：出现一买/二买/三买/底背驰，且收盘站上 EMA5
    卖出：出现一卖/二卖/三卖/顶背驰，或跌破 EMA20，或止损止盈
    返回 {'action': 'buy'|'sell'|'hold', 'reason': str}
    """
    if len(kl_so_far) < 35:
        return {'action': 'hold', 'reason': '数据不足'}

    res = chan_analysis_structured(kl_so_far)
    signals = res.get('signals') or []
    closes = [float(b[2]) for b in kl_so_far]
    c_close = closes[-1]
    ema5 = calc_ema(closes, 5)[-1]
    ema20 = calc_ema(closes, 20)[-1]

    if holding:
        for sig in signals[-3:]:
            t = sig.get('type', '')
            if any(k in t for k in ('一卖', '二卖', '三卖', '顶背驰')):
                return {'action': 'sell', 'reason': f'缠论[{t}]离场'}
        if c_close < ema20:
            return {'action': 'sell', 'reason': f'跌破EMA20({ema20:.2f})'}
        return {'action': 'hold', 'reason': ''}

    for sig in signals[-3:]:
        t = sig.get('type', '')
        if any(k in t for k in ('一买', '二买', '三买', '底背驰')):
            if c_close >= ema5:
                return {'action': 'buy', 'reason': f'缠论[{t}]确认+站上EMA5'}
    return {'action': 'hold', 'reason': ''}


def signal_ma(kl_so_far: List[Any], holding: bool) -> Dict[str, Any]:
    """双均线策略：MA5 上穿 MA20 且放量买入；死叉卖出"""
    if len(kl_so_far) < 25:
        return {'action': 'hold', 'reason': '数据不足'}
    closes = [float(b[2]) for b in kl_so_far]
    vols = [float(b[5]) if len(b) > 5 else 0.0 for b in kl_so_far]
    ma5 = sum(closes[-5:]) / 5
    ma20 = sum(closes[-20:]) / 20
    ma5_prev = sum(closes[-6:-1]) / 5
    ma20_prev = sum(closes[-21:-1]) / 20

    vol_ma5 = (sum(vols[-5:]) / 5) if len(vols) >= 5 else 0.0
    vol_ok = (vols[-1] > vol_ma5 * 1.2) if vol_ma5 > 0 else True

    golden = ma5_prev <= ma20_prev and ma5 > ma20
    dead = ma5_prev >= ma20_prev and ma5 < ma20

    if holding and dead:
        return {'action': 'sell', 'reason': f'MA5死叉MA20 (MA5={ma5:.2f}, MA20={ma20:.2f})'}
    if not holding and golden and vol_ok:
        return {'action': 'buy', 'reason': f'MA5金叉MA20+放量 (MA5={ma5:.2f}, MA20={ma20:.2f})'}
    return {'action': 'hold', 'reason': ''}


STRATEGIES = {
    'chan': {'name': '缠论结构突破', 'fn': signal_chan},
    'ma': {'name': '双均线趋势', 'fn': signal_ma},
}


# ============================================================
# 模式一：历史回放模拟自动交易
# ============================================================

def run_replay(code: str, strategy: str = 'chan', days: int = 250,
               initial_cash: float = 100000.0, budget_ratio: float = 0.95,
               stop_loss_pct: float = 5.0, take_profit_pct: float = 15.0,
               warmup: int = 35, use_gate: bool = False,
               gate_code: str = 'sh000001') -> Dict[str, Any]:
    """历史回放：逐根 K 线推进，下一根开盘成交（无未来函数）

    关键点
    ------
    · 信号在第 i 根**收盘后**计算，成交在第 i+1 根**开盘**，杜绝 look-ahead
    · 止损止盈用当根最低/最高价判断是否触发，按触发价成交
    · T+1 由 SimBroker.can_sell 强制
    · use_gate=True 时叠加「大盘趋势闸门」：闸门不允许时即使个股有买点也不开仓
      （闸门只用截至当日的大盘K线，同样无未来函数）

    ⚠ 关于 use_gate 的实测结论（2026-10-19，请勿凭直觉开启）
      · 闸门单独看有选时能力：开仓日未来5日指数均值 +0.47%，关仓日 +0.10%
      · 但与缠论买点叠加后，拦截率高达 96%（买点多落在下跌途中），
        交易几乎停摆，收益"改善"主要来自不交易而非选对时机
      · 因此默认关闭。若要启用，建议先放宽 ADX 阈值或改用更贴合的信号，
        并用 tests/validate_gate_honest.py 复核，而不是直接打开
    """
    code_clean = str(code).strip()
    full_code = ('sh' + code_clean) if code_clean.startswith(('6', '5', '9')) else ('sz' + code_clean)

    kl = df_feed.get_kline_cached(full_code, days)
    if not kl or len(kl) < warmup + 5:
        return {'status': 'error', 'msg': 'K线数据不足',
                'code': code, 'strategy': strategy}

    # 资金适配：高价股单手可能超过本金（如茅台 1300元 × 100股 = 13万 > 10万），
    # 会导致全程无法成交、"收益 0%" 的假结果。此时按样本价自适应抬高基准本金。
    sample_p = float(kl[-1][2])
    warning = ''
    if sample_p * LOT_SIZE > initial_cash * 0.95:
        initial_cash = math.ceil((sample_p * LOT_SIZE * 1.2) / 10000.0) * 10000.0
        warning = (f'该股股价 ¥{sample_p:.2f}，一手需 ¥{sample_p*LOT_SIZE:,.0f}，'
                   f'原始本金不足，已自适应调整为 ¥{initial_cash:,.0f}')

    strat = STRATEGIES.get(strategy) or STRATEGIES['chan']
    fn = strat['fn']
    broker = SimBroker(initial_cash)

    # 大盘趋势闸门所需数据：指数日K，按日期索引以便与个股K线对齐。
    # 关键：只取「日期 <= 当前bar」的部分做评估，绝不使用未来数据。
    gate_kl_sorted: List[Any] = []
    gate_by_date: Dict[str, int] = {}
    if use_gate:
        try:
            gkl = df_feed.get_kline_cached(gate_code, days + 60) or []
            gate_kl_sorted = sorted(gkl, key=lambda r: str(r[0]))
            gate_by_date = {str(r[0]): idx for idx, r in enumerate(gate_kl_sorted)}
        except Exception:
            gate_kl_sorted, gate_by_date = [], []

    gate_blocks = 0        # 闸门拦截次数
    gate_allow_hist = []   # 每日闸门判定（用于报告）

    pending: Optional[Dict[str, Any]] = None   # 待执行信号（下一根开盘成交）
    entry_price = 0.0
    entry_date = ''

    for i in range(warmup, len(kl)):
        bar = kl[i]
        date = str(bar[0])
        o, c = float(bar[1]), float(bar[2])
        h, l = float(bar[3]), float(bar[4])
        vol = float(bar[5]) if len(bar) > 5 else 1.0

        prev_close = float(kl[i - 1][2])
        up_lim, dn_lim = _limit_prices(prev_close, code_clean)

        # ---- 1) 执行上一根遗留的委托（以本根开盘价成交） ----
        if pending:
            act = pending['action']
            # 涨停开盘买不进 / 跌停开盘卖不出
            if act == 'buy' and o >= up_lim - 1e-9:
                broker._reject(code_clean, date, 'buy', '开盘涨停无法买入', o)
            elif act == 'sell' and o <= dn_lim + 1e-9:
                broker._reject(code_clean, date, 'sell', '开盘跌停无法卖出', o)
            elif act == 'buy':
                rec = broker.buy(code_clean, o, date, pending.get('reason', ''), budget_ratio)
                if rec:
                    entry_price = rec['price']
                    entry_date = date
            elif act == 'sell':
                broker.sell(code_clean, o, date, pending.get('reason', ''))
                entry_price, entry_date = 0.0, ''
            pending = None

        # ---- 2) 持仓中：用当根高低价判断止损/止盈（盘中触发） ----
        holding = broker.shares_of(code_clean) > 0
        if holding and entry_price > 0 and broker.can_sell(code_clean, date):
            sl_price = _round_tick(entry_price * (1 - stop_loss_pct / 100))
            tp_price = _round_tick(entry_price * (1 + take_profit_pct / 100))
            if l <= sl_price:
                broker.sell(code_clean, sl_price, date, f'硬止损 {stop_loss_pct}%')
                entry_price, entry_date = 0.0, ''
                holding = False
            elif h >= tp_price:
                broker.sell(code_clean, tp_price, date, f'止盈 {take_profit_pct}%')
                entry_price, entry_date = 0.0, ''
                holding = False

        # ---- 3) 收盘后生成信号（下一根开盘执行） ----
        sub = kl[:i + 1]
        if vol > 0:      # 停牌日不产生信号
            _has_pos = broker.shares_of(code_clean) > 0
            sig = fn(sub, _has_pos)
            act = sig['action']

            # 大盘趋势闸门：只拦「开新仓」，不拦卖出。
            # 闸门评估只用截至当日(含)的指数K线 —— 与个股信号同一天，无未来函数。
            _gate_allow = 100
            if use_gate and act == 'buy' and not _has_pos and gate_by_date:
                _gi = gate_by_date.get(date)
                if _gi is not None:
                    _g = pg.evaluate_gate(gate_kl_sorted[:_gi + 1])
                    _gate_allow = _g.get('allow_pct', 0)
                    gate_allow_hist.append({'date': date, 'allow': _gate_allow,
                                            'adx': _g.get('adx'),
                                            'reason': _g.get('reason')})
                else:
                    # 个股有K线但指数无对应日期：无法判定趋势 -> fail-closed
                    _gate_allow = 0

            # 硬约束：有持仓不再加仓（本引擎为单标的全进全出），无持仓不产生卖单。
            if act == 'buy' and not _has_pos:
                if _gate_allow <= 0:
                    gate_blocks += 1        # 被闸门拦下，不开仓
                else:
                    pending = {'action': 'buy', 'reason': sig.get('reason', '')}
            elif act == 'sell' and _has_pos:
                pending = {'action': 'sell', 'reason': sig.get('reason', '')}

        broker.snapshot(date, {code_clean: c})

    # 收尾：最后一天按收盘价强制平仓，便于结算
    if broker.shares_of(code_clean) > 0:
        last = kl[-1]
        broker.sell(code_clean, float(last[2]), str(last[0]), '回放结束强制平仓')
        broker.snapshot(str(last[0]), {code_clean: float(last[2])})

    out = _summarize(code_clean, strat['name'], broker, kl, initial_cash)
    # 闸门统计：用于对比「开闸门 vs 不开闸门」的实际效果
    out['gate_enabled'] = bool(use_gate)
    out['gate_blocks'] = gate_blocks
    if gate_allow_hist:
        _allows = [g['allow'] for g in gate_allow_hist]
        out['gate_stats'] = {
            'evaluated_days': len(gate_allow_hist),
            'allow_100_days': sum(1 for a in _allows if a >= 100),
            'allow_50_days': sum(1 for a in _allows if a == 50),
            'allow_0_days': sum(1 for a in _allows if a <= 0),
            'blocked_buy_signals': gate_blocks,
            'last_reason': gate_allow_hist[-1]['reason'],
        }
    if warning:
        out['warning'] = warning
    return out


# ============================================================
# 统计汇总
# ============================================================

def _summarize(code, strategy_name, broker: SimBroker, kl, initial_cash) -> Dict[str, Any]:
    sells = [t for t in broker.trades if t['side'] == 'sell']
    wins = [t for t in sells if t.get('pnl', 0) > 0]
    losses = [t for t in sells if t.get('pnl', 0) <= 0]

    final_eq = broker.equity_curve[-1]['equity'] if broker.equity_curve else initial_cash
    total_ret = (final_eq / initial_cash - 1) * 100

    # 最大回撤
    peak, max_dd = -1e18, 0.0
    for pt in broker.equity_curve:
        eq = pt['equity']
        peak = max(peak, eq)
        if peak > 0:
            max_dd = max(max_dd, (peak - eq) / peak * 100)

    gross_win = sum(t['pnl'] for t in wins)
    gross_loss = abs(sum(t['pnl'] for t in losses))

    return {
        'status': 'ok',
        'mode': 'replay',
        'code': code,
        'strategy': strategy_name,
        'bars': len(kl),
        'initial_cash': round(initial_cash, 2),
        'final_equity': round(final_eq, 2),
        'total_return_pct': round(total_ret, 2),
        'max_drawdown_pct': round(max_dd, 2),
        'trades': len(broker.trades),
        'round_trips': len(sells),
        'win': len(wins),
        'loss': len(losses),
        'win_rate_pct': round(len(wins) / len(sells) * 100, 2) if sells else 0.0,
        'profit_loss_ratio': round(gross_win / gross_loss, 2) if gross_loss > 0 else None,
        'total_commission': round(sum(t['commission'] for t in broker.trades), 2),
        'total_stamp_duty': round(sum(t['stamp_duty'] for t in broker.trades), 2),
        'rejected': len(broker.rejects),
        'reject_samples': broker.rejects[:5],
        'trade_log': broker.trades,
        'equity_curve': broker.equity_curve,
    }


# ============================================================
# 模式二：实时纸上交易 (Paper / Live-paper Trading)
# ============================================================

PAPER_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         'data', 'stock_data')
PAPER_STATE = os.path.join(PAPER_DIR, 'paper_state.json')
PAPER_TRADES = os.path.join(PAPER_DIR, 'paper_trades.jsonl')
PAPER_EQUITY = os.path.join(PAPER_DIR, 'paper_equity.jsonl')


def _ensure_dir():
    try:
        os.makedirs(PAPER_DIR, exist_ok=True)
    except Exception:
        pass


def _load_json(path, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def _append_jsonl(path, obj):
    _ensure_dir()
    try:
        with open(path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(obj, ensure_ascii=False) + '\n')
    except Exception:
        pass


def load_paper_state():
    """读取纸上交易状态（跨进程持久化，重启可续）"""
    return _load_json(PAPER_STATE, {
        'created_at': dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'initial_cash': 100000.0,
        'cash': 100000.0,
        'position': {},
        'last_run': None,
        'runs': 0,
    })


def save_paper_state(state):
    _ensure_dir()
    tmp = PAPER_STATE + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, PAPER_STATE)     # 原子写，避免中断留半截文件
    except Exception:
        pass


def get_live_price(code):
    """取当前最新价（复用 data_feed 的多源容灾）"""
    try:
        pure = str(code).strip()
        full = ('sh' + pure) if pure.startswith(('6', '5', '9')) else ('sz' + pure)
        q = df_feed.get_realtime_quotes([pure])
        if q and pure in q:
            p = q[pure].get('price')
            if p:
                return float(p)
        kl = df_feed.get_kline_cached(full, 10)
        if kl:
            return float(kl[-1][2])
    except Exception:
        pass
    return None


def run_paper_tick(strategy='chan', codes=None, initial_cash=None,
                   budget_ratio=0.95, stop_loss_pct=5.0,
                   take_profit_pct=15.0, persist=True):
    """执行一次纸上交易巡检（定时任务 / 手动调用均可）

    流程：
      1. 读持久化状态（首次运行则用 initial_cash 初始化）
      2. 对每个标的：取实时价 + 近期日K -> 计算信号
      3. 按信号撮合（T+1、整手、费用全部复用 SimBroker 规则）
      4. 落盘状态 + 追加成交/权益流水
    """
    # 默认标的选择价格适中的：茅台一手需13万+，10万本金会被全程拒单，
    # 无法验证交易逻辑。需要观察高价股时显式传 codes。
    codes = codes or ['000001', '300750', '002594']
    strat = STRATEGIES.get(strategy) or STRATEGIES['chan']
    fn = strat['fn']

    state = load_paper_state()
    if initial_cash is not None and state.get('runs', 0) == 0:
        state['initial_cash'] = float(initial_cash)
        state['cash'] = float(initial_cash)

    broker = SimBroker(state['initial_cash'])
    broker.cash = float(state.get('cash', state['initial_cash']))
    broker.position = {c: dict(v) for c, v in (state.get('position') or {}).items()}

    today = dt.date.today().strftime('%Y-%m-%d')
    actions = []
    prices = {}

    for code in codes:
        pure = str(code).strip()
        price = get_live_price(pure)
        if not price:
            actions.append({'code': pure, 'action': 'skip', 'reason': '取价失败'})
            continue
        prices[pure] = price

        full = ('sh' + pure) if pure.startswith(('6', '5', '9')) else ('sz' + pure)
        kl = df_feed.get_kline_cached(full, 120) or []
        if len(kl) < 35:
            actions.append({'code': pure, 'action': 'skip', 'reason': 'K线不足'})
            continue

        has_pos = broker.shares_of(pure) > 0
        pos = broker.position.get(pure)
        entry_price = (pos or {}).get('cost', 0.0)

        # --- 止损止盈优先（盘中随时可触发） ---
        if has_pos and entry_price > 0 and broker.can_sell(pure, today):
            pnl_pct = (price - entry_price) / entry_price * 100
            if pnl_pct <= -abs(stop_loss_pct):
                rec = broker.sell(pure, price, today, '硬止损 %.2f%%' % pnl_pct)
                actions.append({'code': pure, 'action': 'sell',
                                'reason': '止损 %.2f%%' % pnl_pct,
                                'price': price, 'filled': bool(rec)})
                continue
            if pnl_pct >= abs(take_profit_pct):
                rec = broker.sell(pure, price, today, '止盈 %.2f%%' % pnl_pct)
                actions.append({'code': pure, 'action': 'sell',
                                'reason': '止盈 %.2f%%' % pnl_pct,
                                'price': price, 'filled': bool(rec)})
                continue

        # --- 策略信号（把当日实时价拼成一根未收盘K线） ---
        kl_rt = list(kl)
        kl_rt[-1] = [today] + list(kl[-1][1:])
        sig = fn(kl_rt, has_pos)
        act = sig.get('action', 'hold')

        if act == 'buy' and not has_pos:
            _rej_before = len(broker.rejects)
            rec = broker.buy(pure, price, today, sig.get('reason', ''), budget_ratio)
            _rej = broker.rejects[_rej_before:] if len(broker.rejects) > _rej_before else []
            actions.append({'code': pure, 'action': 'buy', 'reason': sig.get('reason', ''),
                            'price': price, 'filled': bool(rec),
                            'shares': (rec or {}).get('shares'),
                            'reject_reason': (_rej[0]['reason'] if _rej else None)})
        elif act == 'sell' and has_pos:
            rec = broker.sell(pure, price, today, sig.get('reason', ''))
            actions.append({'code': pure, 'action': 'sell', 'reason': sig.get('reason', ''),
                            'price': price, 'filled': bool(rec)})
        else:
            actions.append({'code': pure, 'action': 'hold', 'reason': sig.get('reason', ''),
                            'price': price})

    mv = broker.market_value(prices)
    equity = broker.cash + mv
    snap = {
        'ts': dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'cash': round(broker.cash, 2),
        'market_value': round(mv, 2),
        'equity': round(equity, 2),
        'return_pct': round((equity / state['initial_cash'] - 1) * 100, 2) if state['initial_cash'] else 0.0,
        'positions': {c: p['shares'] for c, p in broker.position.items()},
        'prices': prices,
    }

    state.update({
        'cash': round(broker.cash, 2),
        'position': broker.position,
        'last_run': snap['ts'],
        'runs': int(state.get('runs', 0)) + 1,
        'strategy': strategy,
    })
    if persist:
        save_paper_state(state)
        for t in broker.trades:
            _append_jsonl(PAPER_TRADES, t)
        _append_jsonl(PAPER_EQUITY, snap)

    return {
        'status': 'ok',
        'mode': 'paper',
        'strategy': strat['name'],
        'ts': snap['ts'],
        'actions': actions,
        'snapshot': snap,
        'trades_this_tick': broker.trades,
        'rejects_this_tick': broker.rejects,
        'state_file': PAPER_STATE,
    }


def paper_report():
    """读取纸上交易历史流水，输出累计报告"""
    state = load_paper_state()
    trades, equity = [], []
    try:
        if os.path.exists(PAPER_TRADES):
            with open(PAPER_TRADES, 'r', encoding='utf-8') as f:
                trades = [json.loads(l) for l in f if l.strip()]
    except Exception:
        pass
    try:
        if os.path.exists(PAPER_EQUITY):
            with open(PAPER_EQUITY, 'r', encoding='utf-8') as f:
                equity = [json.loads(l) for l in f if l.strip()]
    except Exception:
        pass

    sells = [t for t in trades if t.get('side') == 'sell']
    wins = [t for t in sells if t.get('pnl', 0) > 0]
    losses = [t for t in sells if t.get('pnl', 0) <= 0]
    last_eq = equity[-1] if equity else None

    peak, max_dd = -1e18, 0.0
    for pt in equity:
        eq = pt.get('equity', 0)
        peak = max(peak, eq)
        if peak > 0:
            max_dd = max(max_dd, (peak - eq) / peak * 100)

    return {
        'status': 'ok',
        'initial_cash': state.get('initial_cash'),
        'runs': state.get('runs', 0),
        'last_run': state.get('last_run'),
        'trades': len(trades),
        'round_trips': len(sells),
        'win': len(wins),
        'loss': len(losses),
        'win_rate_pct': round(len(wins) / len(sells) * 100, 2) if sells else 0.0,
        'total_commission': round(sum(t.get('commission', 0) for t in trades), 2),
        'total_stamp_duty': round(sum(t.get('stamp_duty', 0) for t in trades), 2),
        'max_drawdown_pct': round(max_dd, 2) if equity else None,
        'latest_equity': last_eq,
        'state': state,
    }
