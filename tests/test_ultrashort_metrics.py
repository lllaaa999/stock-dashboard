# -*- coding: utf-8 -*-
"""
tests/test_ultrashort_metrics.py

针对 scripts/ultrashort_metrics.py 的全量单元测试：
覆盖：
1. 窄幅横盘期贝叶斯方差底噪收缩 (VW-DVR 稳定在 0.50 附近，消除分母趋零浮点震荡)
2. 振幅 4.2% 中心点双 Sigmoid 连续软门控 (保留震荡市 4.5%~5.5% 蓄势承接信号)
3. 千亿中军与缩量一字板的 500万/0.3% 换手门槛保护及尾盘 >40% 大单撤退报警
4. 因果序贯 Gram-Schmidt 正交化 (正交残差零共线性)、开盘 25 分钟指数半衰期与一票否决风险乘子
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

from ultrashort_metrics import (
    compute_adaptive_vw_dvr,
    compute_desensitized_headroom,
    evaluate_limit_order_strength,
    robust_orthogonal_scoring,
    sequential_gram_schmidt_orthogonalize,
)


class TestUltrashortMetricsEngine(unittest.TestCase):
    """超短微观底牌与异构因子正交融合单元测试"""

    def test_bayesian_shrinkage_under_low_volatility_noise(self) -> None:
        """测试1：横盘 1 分钱买卖跳动底噪下，VW-DVR 被先验稳健收缩至 ~0.50 且承接分趋于 0"""
        n_bars = 60
        # 20 元股票盘中仅发生极轻微 1 分钱跳动 (收益率 ±0.0002)，振幅 0.8%
        r_noise = np.where(np.arange(n_bars) % 2 == 0, 0.0002, -0.00025)
        v_flat = np.full(n_bars, 500.0, dtype=np.float64)

        res = compute_adaptive_vw_dvr(
            r_1m=r_noise,
            v_1m=v_flat,
            p_prev=20.0,
            amp_intraday=0.008,
            pos_intraday=0.50,
            shrink_lambda=4.0,
        )
        self.assertAlmostEqual(float(res["vw_dvr"]), 0.50, delta=0.04)
        self.assertAlmostEqual(float(res["absorption_score"]), 0.0, delta=0.02)
        self.assertEqual(res["dvr_regime_label"], "⚪ 窄幅横盘钝化")

    def test_dual_sigmoid_soft_gate_transition(self) -> None:
        """测试2：验证振幅 4.8% (低于原 6% 硬截断) 的放量拉升缩量洗盘股可通过双 Sigmoid 软门控获得正向承接分"""
        n_bars = 60
        r_accum = np.zeros(n_bars, dtype=np.float64)
        v_accum = np.full(n_bars, 800.0, dtype=np.float64)
        # 放量拉升、缩量微跌
        r_accum[:30] = 0.0016
        v_accum[:30] = 4500.0
        r_accum[30:] = -0.0004
        v_accum[30:] = 500.0

        res_48 = compute_adaptive_vw_dvr(
            r_1m=r_accum,
            v_1m=v_accum,
            p_prev=10.0,
            amp_intraday=0.048,
            pos_intraday=0.78,
        )
        self.assertLess(float(res_48["vw_dvr"]), 0.25)
        self.assertGreater(float(res_48["absorption_score"]), 0.30)
        self.assertEqual(res_48["dvr_regime_label"], "🟢 良性分歧承接")

    def test_limit_order_strength_turnover_gate_and_withdrawal(self) -> None:
        """测试3：验证 500万/0.3% 换手门槛防一字板封成比失真，以及 >40% 封单撤退警报"""
        # 标的 A: 极度缩量一字板 (成交仅 200 万 < 500万 且 换手 0.04% < 0.3%) -> 封成比强制归 0 防虚高，靠封流比得分
        # 标的 B: 正常换手铁板 (封单 3亿 / 流通盘 50亿 = 6% >= 5%，无撤单)
        # 标的 C: 尾盘大单撤退股 (峰值封单 2亿，当前仅剩 8000万，撤单率 60% > 40%)
        seal_amt = np.array([2.5e8, 3.0e8, 0.8e8])
        peak_amt = np.array([2.5e8, 3.1e8, 2.0e8])
        turn_amt = np.array([2.0e6, 2.5e8, 1.8e8])
        float_cap = np.array([50.0e8, 50.0e8, 50.0e8])
        is_sealed = np.array([True, True, True])

        res = evaluate_limit_order_strength(
            seal_amount=seal_amt,
            peak_seal_amount=peak_amt,
            turnover_amount=turn_amt,
            free_float_mkt_cap=float_cap,
            is_sealed=is_sealed,
            minutes_from_open=200.0,
        )
        # 标的 A 因未过 500万/0.3% 换手门禁，seal_to_turnover_ratio 必须置 0
        self.assertEqual(float(res["seal_to_turnover_ratio"][0]), 0.0)
        self.assertTrue(bool(res["is_iron_sealed"][0]))
        self.assertTrue(bool(res["is_iron_sealed"][1]))
        # 标的 C 撤单 60% 必须报警且质量分被大幅折价
        self.assertTrue(bool(res["is_large_withdrawal"][2]))
        self.assertAlmostEqual(float(res["seal_drop_ratio"][2]), 0.60, places=4)
        self.assertLess(float(res["seal_quality_score"][2]), float(res["seal_quality_score"][1]) * 0.5)

    def test_gram_schmidt_orthogonality_and_veto_scoring(self) -> None:
        """测试4：验证因果序贯正交化消除共线性，以及大单撤退/冲高回落/异动锁死的一票否决惩罚"""
        rng = np.random.default_rng(1024)
        m = 30
        # 构造高度共线性的前两个因子 (相关系数 > 0.95)
        f1 = np.linspace(0.0, 1.0, m)
        f2 = f1 + rng.normal(0.0, 0.02, size=m)
        f3 = rng.uniform(0.0, 1.0, size=m)
        f4 = rng.uniform(0.0, 1.0, size=m)
        raw_mat = np.column_stack([f1, f2, f3, f4])

        ortho_ranks = sequential_gram_schmidt_orthogonalize(raw_mat)
        self.assertEqual(ortho_ranks.shape, (m, 4))
        self.assertTrue(np.all((ortho_ranks >= 0.0) & (ortho_ranks <= 1.0)))

        # 验证一票否决乘子在综合打分中的压制作用
        auc = np.array([9.0, 9.0, 9.0, 9.0])
        spd = np.array([1.0, 1.0, 1.0, 1.0])
        dvr_s = np.array([0.8, 0.8, 0.8, 0.8])
        seal_s = np.array([0.9, 0.9, 0.9, 0.9])
        sealed = np.array([True, True, False, True])

        withdraw_mask = np.array([False, True, False, False])
        fade_mask = np.array([False, False, True, False])
        locked_mask = np.array([False, False, False, True])

        scores, penalties, _ = robust_orthogonal_scoring(
            auction_metric=auc,
            speed_rank=spd,
            absorption_score=dvr_s,
            seal_quality_score=seal_s,
            is_sealed=sealed,
            minutes_from_open=120.0,
            is_large_withdrawal=withdraw_mask,
            is_spike_fade=fade_mask,
            is_severe_locked=locked_mask,
        )
        self.assertEqual(float(penalties[0]), 1.0)
        self.assertEqual(float(penalties[1]), 0.40)
        self.assertEqual(float(penalties[2]), 0.25)
        self.assertEqual(float(penalties[3]), 0.35)
        self.assertGreater(float(scores[0]), float(scores[1]) * 2.0)
        self.assertGreater(float(scores[0]), float(scores[3]) * 2.5)

    def test_desensitized_headroom_unconstrained_floor(self) -> None:
        """测试5：验证无异动约束标的真实安全垫脱敏保底为 30% (0.30)"""
        curr_p = np.array([10.80, 19.85])
        prev_c = np.array([10.00, 18.00])
        limit_p = np.array([11.00, 20.00])
        sev_safe_p = np.array([14.50, 19.95])  # 第1只涨停11.00 < 安全价14.50(无约束); 第2只安全价19.95接近涨停且空间<2%

        eff_hr, locked = compute_desensitized_headroom(curr_p, prev_c, limit_p, sev_safe_p)
        self.assertGreaterEqual(float(eff_hr[0]), 0.30)
        self.assertFalse(bool(locked[0]))
        self.assertTrue(bool(locked[1]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
