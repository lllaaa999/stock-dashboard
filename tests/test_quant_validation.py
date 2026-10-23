# tests/test_quant_validation.py
import os
import sys
import unittest
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from benchmarks.quant_validation import QuantValidationPipeline, GateVerdict


class TestQuantValidationPipeline(unittest.TestCase):
    """测试 5 道量化硬门禁流水线"""

    def setUp(self):
        self.pipeline = QuantValidationPipeline(
            mode="event_sparse",
            min_ic_ir=0.4,
            min_t_stat=1.8,
            min_monotonicity_rho=0.7,
            n_permutations=100,
        )

    def test_pipeline_on_synthetic_data(self):
        rng = np.random.default_rng(seed=42)
        dates = [f"2025-01-{i:02d}" for i in range(1, 21)]
        symbols = [f"{600000 + j:06d}.SH" for j in range(30)]

        rows = []
        for dt in dates:
            for sym in symbols:
                in_pool = bool(rng.random() < 0.4)
                signal = float(rng.uniform(0, 10)) if in_pool else 0.0
                ret_3d = (signal * 0.01) + float(rng.normal(0, 0.02)) if signal > 0 else float(rng.normal(0, 0.02))
                rows.append({
                    "date": dt,
                    "symbol": sym,
                    "signal": signal,
                    "in_candidate_pool": in_pool,
                    "ret_1d": ret_3d * 0.4,
                    "ret_3d": ret_3d,
                    "ret_5d": ret_3d * 1.2,
                    "ret_10d": ret_3d * 1.5,
                    "market_regime": "bull" if rng.random() > 0.3 else "bear",
                    "turnover_pct_rank": float(rng.uniform(0, 1)),
                    "mcap_pct_rank": float(rng.uniform(0, 1)),
                })

        df = pd.DataFrame(rows)
        verdicts = self.pipeline.run_all_gates(df)

        self.assertEqual(len(verdicts), 5)
        self.assertIn("Gate1_Pattern_Decoupling", verdicts)
        self.assertIn("Gate2_Monotonicity", verdicts)
        self.assertIn("Gate3_WalkForward_OOS", verdicts)
        self.assertIn("Gate4_PostMortem_Matrix", verdicts)
        self.assertIn("Gate5_MonteCarlo_Permutation", verdicts)

        for name, v in verdicts.items():
            self.assertIsInstance(v, GateVerdict)
            self.assertIsInstance(v.passed, bool)
            self.assertIsInstance(v.metrics, dict)
            self.assertTrue(len(v.reason) > 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
