# -*- coding: utf-8 -*-
"""
tests/test_abnormal_volatility.py

针对 scripts/abnormal_volatility.py 的全量单元测试：
覆盖：
1. 注册制法定区间首尾复利偏离度公式 vs 旧规累加差异校验与精确安全价逆推
2. 主板 (±20%) 与 双创 (±30%) 的 2日 (k=2) 与 3日 (k=3) 异动捕获，严防 2 日异动漏判
3. 普通异动“公告次日清零”与“10日内同向 N 次普通异动升级为严重异动”及“10日100%/30日200%穿透滑动”双轨状态机
4. 跨停牌日指数基准锚定与法定除权除息参考价四舍五入折算
5. 首板冲涨停解绑截断 (cap_at_limit=False)，杜绝误报“空间锁死(<2%)”
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = _PROJECT_ROOT / "scripts"
for _p in (str(_PROJECT_ROOT), str(_SCRIPTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from abnormal_volatility import (
    compute_exact_safe_price,
    compute_statutory_ex_right_price,
    evaluate_stock_volatility,
)


class TestAbnormalVolatilityEngine(unittest.TestCase):
    """异常波动监管红线与安全价反推引擎单元测试"""

    def setUp(self) -> None:
        # 构造平稳基准指数 (点位恒为 3000.0)
        self.flat_index_15d = [
            {"date": f"2026-10-{d:02d}", "prev_close": 3000.0, "close": 3000.0}
            for d in range(1, 16)
        ]

    def test_statutory_compound_formula_and_safe_price_solver(self) -> None:
        """测试1：验证法定首尾复利偏离公式与 0.15% 缓冲垫 + 退 1 分钱安全价逆推精度"""
        p_bases = np.array([10.00], dtype=np.float64)
        i_bases = np.array([3000.0], dtype=np.float64)
        i_curr = 3030.0  # 指数区间上涨 +1.0%
        thresholds = np.array([0.20], dtype=np.float64)  # 主板 +20% 阈值

        min_safe, safe_vec, exact_vec = compute_exact_safe_price(
            p_bases_adj=p_bases,
            i_bases=i_bases,
            i_curr=i_curr,
            thresholds=thresholds,
            buffer_ratio=0.0015,
            cap_at_limit=False,
        )
        # 理论精确触线价: 10.00 * (1 + 0.01 + 0.20) = 12.10 元
        self.assertAlmostEqual(float(exact_vec[0]), 12.10, places=6)
        # 扣除 0.15% 缓冲垫后: 10.00 * (1.21 - 0.0015) = 12.085 -> floor 至 12.08 -> 退 1 分钱 = 12.07 元
        self.assertEqual(min_safe, 12.07)
        self.assertEqual(float(safe_vec[0]), 12.07)

    def test_2day_and_3day_normal_volatility_capture(self) -> None:
        """测试2：严密捕获主板 2日20% 与 创业板/科创板 2日30% 及 3日异动，杜绝 k=2 漏判"""
        # (A) 主板连续 2 个 10% 涨停 (10.00 -> 11.00 -> 今日 12.10, 2日复利涨幅 21% > 20%)
        hist_main = self.flat_index_15d[:-1].copy()
        stock_main = [
            {"date": item["date"], "prev_close": 10.0, "close": 10.0}
            for item in hist_main[:-1]
        ] + [{"date": hist_main[-1]["date"], "prev_close": 10.0, "close": 11.0}]

        res_main_2d = evaluate_stock_volatility(
            "600001.SH", stock_main, hist_main, curr_price=12.10, curr_index=3000.0
        )
        # 期初基准 10.00, 主板 +20% 安全价应为 floor(10*(1.20-0.0015)*100)/100 - 0.01 = 11.97
        self.assertEqual(res_main_2d["normal_safe_price"], 11.97)
        self.assertTrue(res_main_2d["is_normal_triggered_now"])
        self.assertEqual(res_main_2d["binding_window"]["window_days"], 2)

        # (B) 300 创业板昨日 +20% (10.00 -> 12.00)，今日冲至 13.05 (2日累计 +30.5% > 30%)
        stock_chinext = [
            {"date": item["date"], "prev_close": 10.0, "close": 10.0}
            for item in hist_main[:-1]
        ] + [{"date": hist_main[-1]["date"], "prev_close": 10.0, "close": 12.0}]

        res_chinext_2d = evaluate_stock_volatility(
            "300750.SZ", stock_chinext, hist_main, curr_price=13.05, curr_index=3000.0
        )
        self.assertEqual(res_chinext_2d["normal_safe_price"], 12.97)
        self.assertTrue(res_chinext_2d["is_normal_triggered_now"])
        self.assertEqual(res_chinext_2d["binding_window"]["window_days"], 2)

    def test_normal_announcement_reset_and_severe_upgrade_state_machine(self) -> None:
        """测试3：验证普通异动公告次日清零，以及 10 日内累计同向异动升级为严重异动"""
        # 构造双创股票在过去 8 个交易日内已触发 2 次 30% 普通异动 (双创 10 日内 3 次即触发严重异动):
        # 第1次触发: Day 2 (10.0 -> 11.5 -> 13.1, +31%) -> 公告清零，下次起点从 Day 3 (基准13.1) 开始
        # 第2次触发: Day 5 (13.1 -> 15.0 -> 17.1, +30.53%) -> 公告清零，下次起点从 Day 6 (基准17.1) 开始
        # Day 6 收盘 17.5，今日 (Day 7) 若再触发第 3 次普通异动，将直接升级为 SEVERE_COUNT_10D 严重异动！
        closes = [10.0, 11.5, 13.1, 13.1, 15.0, 17.1, 17.5]
        prevs = [10.0, 10.0, 11.5, 13.1, 13.1, 15.0, 17.1]
        stock_bars = [
            {"date": f"2026-10-0{i+1}", "prev_close": prevs[i], "close": closes[i]}
            for i in range(len(closes))
        ]
        idx_bars = [
            {"date": f"2026-10-0{i+1}", "prev_close": 3000.0, "close": 3000.0}
            for i in range(len(closes))
        ]

        res = evaluate_stock_volatility(
            "688001.SH", stock_bars, idx_bars, curr_price=19.80, curr_index=3000.0
        )
        self.assertEqual(res["normal_triggers_in_prev_9d"], 2)
        self.assertTrue(res["will_Upgrade_to_severe_on_normal"])
        # 因为前 2 次已在 Day 2 与 Day 5 公告清零，当前普通异动有效窗口起点必须是 Day 6 (期初基准 17.1)
        # 同時受 10日+100% 穿透窗口约束 (起点 Day 0 基准 10.0, 触线价 20.0, 安全价 19.97)
        # Day 6 起点 +30% 触线价为 17.1 * 1.3 = 22.23，故全局最紧瓶颈为 10日100% 穿透窗口 (19.97 元)
        self.assertEqual(res["severe_safe_price"], 19.97)
        self.assertTrue(res["is_severe_locked"])

    def test_cross_suspension_alignment_and_statutory_ex_right(self) -> None:
        """测试4：验证跨停牌日指数锚定与期间除权除息法定参考价折算"""
        # 验证法定除权参考价：前收盘 20.00 元，每股派息 0.50 元，10送转10股 (split=1.0) -> (20 - 0.5)/2 = 9.75 元
        ex_p = compute_statutory_ex_right_price(
            prev_close=20.00, cash_dividend=0.50, bonus_share_ratio=1.0
        )
        self.assertEqual(float(ex_p), 9.75)

        # 构造含停牌日与除权日的个股序列
        stock_bars = [
            {"date": "2026-10-01", "prev_close": 20.0, "close": 22.0, "volume": 1000},
            {"date": "2026-10-02", "prev_close": 22.0, "close": 22.0, "volume": 0, "is_suspended": True},
            {
                "date": "2026-10-03",
                "prev_close": 22.0,
                "close": 11.50,
                "volume": 1500,
                "cash_dividend": 0.50,
                "bonus_share_ratio": 1.0,
            },
        ]
        idx_bars = [
            {"date": "2026-10-01", "prev_close": 3000.0, "close": 3000.0},
            {"date": "2026-10-02", "prev_close": 3000.0, "close": 3060.0},  # 停牌期间大盘涨 2%
            {"date": "2026-10-03", "prev_close": 3060.0, "close": 3060.0},
        ]
        res = evaluate_stock_volatility(
            "000001.SZ", stock_bars, idx_bars, curr_price=11.60, curr_index=3060.0
        )
        # 2026-10-01 的期初前收盘价 20.00 经 10-03 除权折算后应为 9.75 元
        self.assertEqual(res["prev_close"], 11.50)
        self.assertFalse(res["is_severe_triggered_now"])

    def test_first_board_unconstrained_no_false_alarm(self) -> None:
        """测试5：验证低位首板冲涨停时解绑涨停截断，绝不误报空间锁死"""
        stock_bars = [
            {"date": item["date"], "prev_close": 10.0, "close": 10.0}
            for item in self.flat_index_15d
        ]
        res = evaluate_stock_volatility(
            "000002.SZ",
            stock_bars,
            self.flat_index_15d,
            curr_price=10.98,
            curr_index=3000.0,
            cap_at_limit=False,
        )
        self.assertTrue(res["is_unconstrained_today"])
        self.assertTrue(res["is_severe_unconstrained_today"])
        self.assertFalse(res["is_severe_locked"])
        self.assertGreater(res["safe_price"], res["limit_up_price"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
