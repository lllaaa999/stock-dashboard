import unittest
from scripts.resonance_engine import (
    ResonanceEngine,
    ResonanceTag,
    StockTickSnapshot,
    MarketSnapshot,
)

class TestResonanceEngineRegression(unittest.TestCase):
    def setUp(self):
        self.engine = ResonanceEngine()

    def test_theme_speed_rank_pioneer_and_spike_dump_exclusion(self):
        """
        核心防线回归测试：
        1. 09:31 冲天炮冲 +5% 后跳水至 -2.5% 的骗炮股，绝对不能当选 Rank=1 先锋龙，强制降级并打上冲高回落掉队标签；
        2. 09:35 破 +5% 且当前稳守 +8.8% 的真主攻股，稳定当选 Rank=1 先锋龙。
        """
        spike_and_dump = StockTickSnapshot(
            symbol="000001.SZ", name="冲高跳水杂毛", timestamp="10:00:00",
            day_ret_pct=-2.5, ret_5m_pct=-1.2, open_ret_pct=3.0, vol_ratio=2.5,
            cross_5pct_time="09:31:00", themes=["固态电池"],
        )
        real_pioneer = StockTickSnapshot(
            symbol="000002.SZ", name="真先锋主攻", timestamp="10:00:00",
            day_ret_pct=8.8, ret_5m_pct=3.5, open_ret_pct=1.5, vol_ratio=3.2,
            cross_5pct_time="09:35:00", themes=["固态电池"],
        )
        laggard = StockTickSnapshot(
            symbol="000003.SZ", name="后排跟跌", timestamp="10:00:00",
            day_ret_pct=0.8, ret_5m_pct=0.2, open_ret_pct=0.0, vol_ratio=0.9,
            cross_5pct_time=None, themes=["固态电池"],
        )
        theme_map = {"固态电池": [spike_and_dump, real_pioneer, laggard]}
        market = MarketSnapshot(timestamp="10:00:00", day_ret_pct=0.2, ret_5m_pct=0.05)

        # 评估真先锋龙
        res_pioneer = self.engine.evaluate(real_pioneer, theme_map, market)
        self.assertEqual(res_pioneer.theme_speed_rank, 1)
        self.assertIn("🚀 先锋龙", res_pioneer.theme_role_tag)
        self.assertTrue(any("🚀 先锋龙" in label for label in res_pioneer.tag_labels))

        # 评估冲高跳水杂毛
        res_dump = self.engine.evaluate(spike_and_dump, theme_map, market)
        self.assertNotEqual(res_dump.theme_speed_rank, 1)
        self.assertIn("🥀 冲高回落掉队", res_dump.theme_role_tag)
        self.assertTrue(any("🥀 冲高回落掉队" in label for label in res_dump.tag_labels))

    def test_point_plane_resonance_healthy_surge(self):
        """测试健康点面共振协同脉冲"""
        leader = StockTickSnapshot(
            symbol="002460.SZ", name="赣锋锂业", timestamp="09:40:00",
            day_ret_pct=9.5, ret_5m_pct=3.8, open_ret_pct=2.1, vol_ratio=3.5,
            is_limit_up=False, cross_5pct_time="09:34:00", themes=["锂电池"],
        )
        peer = StockTickSnapshot(
            symbol="002466.SZ", name="天齐锂业", timestamp="09:40:00",
            day_ret_pct=6.5, ret_5m_pct=2.8, open_ret_pct=1.0, vol_ratio=2.8,
            cross_5pct_time="09:36:00", themes=["锂电池"],
        )
        theme_map = {"锂电池": [leader, peer]}
        market = MarketSnapshot(timestamp="09:40:00", day_ret_pct=0.8, ret_5m_pct=0.4)

        res = self.engine.evaluate(leader, theme_map, market)
        self.assertIn(ResonanceTag.RESONANCE, res.all_tags)
        self.assertEqual(res.theme_speed_rank, 1)

if __name__ == '__main__':
    unittest.main()
