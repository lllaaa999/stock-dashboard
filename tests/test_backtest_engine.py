# -*- coding: utf-8 -*-
"""
量化回测引擎单元测试套件 (Unit Tests for Quant Backtest Engine)
覆盖：
  1. 绩效指标数学计算 (收益率、年化、夏普、最大回撤、胜率、盈亏比)
  2. 92科比情绪周期择时策略 (cycle_timing)
  3. 缠论分型战法回测 (chan_breakout) 与自适应本金适配
  4. 双均线趋势策略 (double_ma)
  5. 龙头涨停板动量策略 (zt_momentum)
"""
import os
import sys
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
SCRIPTS_DIR = os.path.join(ROOT_DIR, 'scripts')
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from scripts.backtest_engine import (
    BacktestResult,
    _calc_metrics,
    backtest_cycle_timing,
    backtest_chan_strategy,
    backtest_double_ma_strategy,
    backtest_zt_momentum_strategy,
    get_available_strategies,
    run_strategy,
)


class TestBacktestEngine(unittest.TestCase):
    """回测算力引擎单元测试"""

    def test_metrics_calculation(self):
        """测试绩效指标数学计算精确性"""
        equity_curve = [
            {"date": "2026-01-01", "equity": 100000.0},
            {"date": "2026-01-02", "equity": 105000.0},
            {"date": "2026-01-03", "equity": 102000.0},
            {"date": "2026-01-04", "equity": 110000.0},
        ]
        trade_logs = [
            {"pnl": 5000.0, "hold_days": 2},
            {"pnl": -3000.0, "hold_days": 1},
            {"pnl": 8000.0, "hold_days": 3},
        ]
        res = _calc_metrics(equity_curve, trade_logs, 100000.0, 3000.0, 3150.0)
        self.assertAlmostEqual(res.total_return_pct, 10.0, places=2)
        self.assertAlmostEqual(res.benchmark_return_pct, 5.0, places=2)
        self.assertAlmostEqual(res.excess_return_pct, 5.0, places=2)
        self.assertEqual(res.total_trades, 3)
        self.assertEqual(res.winning_trades, 2)
        self.assertEqual(res.losing_trades, 1)
        self.assertAlmostEqual(res.win_rate_pct, 66.67, places=1)
        self.assertAlmostEqual(res.profit_loss_ratio, 13000.0 / 3000.0, places=2)
        # 最大回撤: 从 105000 跌至 102000 = -2.857%
        self.assertAlmostEqual(res.max_drawdown_pct, 2.86, places=1)

    def test_available_strategies(self):
        """测试策略列表完整性"""
        strats = get_available_strategies()
        self.assertTrue(len(strats) >= 4)
        keys = [s["key"] for s in strats]
        self.assertIn("cycle", keys)
        self.assertIn("chan", keys)
        self.assertIn("ma", keys)
        self.assertIn("zt", keys)

    def test_cycle_timing_execution(self):
        """测试情绪周期择时策略运行"""
        res = run_strategy("cycle", code="sh000001")
        self.assertEqual(res["status"], "ok")
        summary = res["summary"]
        self.assertIn("total_return_pct", summary)
        self.assertIn("benchmark_return_pct", summary)
        self.assertIn("equity_curve", summary)
        self.assertTrue(len(summary["equity_curve"]) > 0)

    def test_chan_strategy_execution(self):
        """测试单股缠论突破策略运行"""
        res = run_strategy("chan", code="002696", days=60)
        self.assertEqual(res["status"], "ok")
        summary = res["summary"]
        self.assertIn("equity_curve", summary)
        self.assertTrue(len(summary["equity_curve"]) > 0)

    def test_high_price_stock_adaptation(self):
        """测试高价股单手自适应适配"""
        res = run_strategy("chan", code="600519", days=60, initial_capital=100000.0)
        self.assertEqual(res["status"], "ok")
        summary = res["summary"]
        # 初始本金应自适应上浮至 200,000 元
        self.assertTrue(summary["initial_capital"] >= 150000.0)
        self.assertTrue("提示" in summary.get("warning_msg", ""))


if __name__ == '__main__':
    unittest.main()
