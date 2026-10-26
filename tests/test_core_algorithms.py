# -*- coding: utf-8 -*-
"""
核心纯算力层单元测试套件 (Unit Tests for Core Algorithms)
脱离外部网络，100% 内存模拟测试。
覆盖：core.chan (缠论形态/中枢/背驰), core.quality (涨停质量), core.emotion (情绪打分与背离)
"""
import os
import sys
import unittest

# 确保项目根目录在 sys.path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.chan import chan_analysis_structured, calc_ema, _ema
from core.quality import limit_up_quality, _lu_num, _lu_time_score, _lu_seal_score, _lu_board_score
from core.emotion import (
    emotion_band,
    emotion_score_v1,
    emotion_score_v2,
    effect_flat
)


class TestCoreChan(unittest.TestCase):
    """缠论纯算法测试"""

    def test_ema_calculation(self):
        vals = [10.0, 11.0, 12.0, 13.0, 14.0]
        ema = calc_ema(vals, 3)
        self.assertEqual(len(ema), 5)
        self.assertEqual(ema[0], 10.0)
        self.assertAlmostEqual(ema[1], 10.5)
        # 测试兼容别名
        self.assertEqual(_ema(vals, 3), ema)

    def test_chan_insufficient_klines(self):
        kl = [['2026-01-01', 10, 10, 10, 10, 100]] * 10
        res = chan_analysis_structured(kl)
        self.assertEqual(res['status'], 'error')
        self.assertIn('不足30根', res['msg'])

    def test_chan_synthetic_trend_and_zhongshu(self):
        """构造典型上升包含与笔形态K线"""
        kl = []
        # 构造 60 根有起伏的 K 线，产生明确的顶底分型和笔
        # 格式: [日期, 开盘, 收盘, 最高, 最低, 成交量]
        base = 10.0
        import math
        for i in range(80):
            d_str = f"2026-01-{i+1:02d}"
            # 波动曲线: 基础上升趋势叠加正弦波动
            p = base + (i * 0.1) + math.sin(i / 3.0) * 2.0
            h = p + 0.5
            l = p - 0.5
            kl.append([d_str, round(p - 0.1, 2), round(p, 2), round(h, 2), round(l, 2), 1000])

        res = chan_analysis_structured(kl, 'sh600000')
        self.assertIn(res['status'], ['ok', 'warning'])
        self.assertIn('cur_dir', res)
        self.assertIn('bi_points', res)
        self.assertIn('zhongshu_list', res)
        self.assertIsInstance(res['signals'], list)
        self.assertIn('hint', res)

    def test_chan_first_buy_sell_signals(self):
        """专项测试：第一类买点（底背驰一买）与第一类卖点（顶背驰一卖）"""
        import math
        # 1. 底背驰 -> 一买候选
        kl_buy1 = []
        for i in range(120):
            amp = 5.0 if i < 70 else 2.0
            trend = 50 - (i * 0.05 if i < 70 else 70 * 0.05 + (i - 70) * 0.02)
            c = trend + math.sin(i / 3.0) * amp
            kl_buy1.append([f"2026-01-{i+1:03d}", c, c, c + 0.5, c - 0.5, 1000])
        res_buy1 = chan_analysis_structured(kl_buy1, 'sh600001')
        sig_types_buy1 = [s['type'] for s in res_buy1.get('signals', [])]
        self.assertIn('底背驰', sig_types_buy1)
        self.assertIn('一买候选', sig_types_buy1)
        self.assertIn('一买候选', res_buy1.get('hint', ''))

        # 2. 顶背驰 -> 一卖警戒
        kl_sell1 = []
        for i in range(120):
            amp = 5.0 if i < 70 else 2.5
            trend = 10 + (i * 0.02 if i < 70 else 70 * 0.02 + (i - 70) * 0.05)
            c = trend - math.sin(i / 3.5) * amp
            kl_sell1.append([f"2026-01-{i+1:03d}", c, c, c + 0.5, c - 0.5, 1000])
        res_sell1 = chan_analysis_structured(kl_sell1, 'sh600002')
        sig_types_sell1 = [s['type'] for s in res_sell1.get('signals', [])]
        self.assertIn('顶背驰', sig_types_sell1)
        self.assertIn('一卖警戒', sig_types_sell1)
        self.assertIn('一卖警戒', res_sell1.get('hint', ''))

    def test_chan_second_buy_sell_signals(self):
        """专项测试：第二类买点（次笔回抽不破前低）与第二类卖点（次笔反弹不破前高）"""
        import math
        # 1. 次笔回抽不破前低 -> 二买候选
        kl_buy2 = []
        for i in range(80):
            p = 10.0 + (i * 0.1) + math.sin(i / 3.0) * 2.0
            kl_buy2.append([f"2026-01-{i+1:02d}", round(p - 0.1, 2), round(p, 2), round(p + 0.5, 2), round(p - 0.5, 2), 1000])
        res_buy2 = chan_analysis_structured(kl_buy2, 'sh600003')
        sig_types_buy2 = [s['type'] for s in res_buy2.get('signals', [])]
        self.assertIn('二买候选', sig_types_buy2)
        self.assertIn('二买候选', res_buy2.get('hint', ''))

        # 2. 次笔反弹不破前高 -> 二卖警戒
        kl_sell2 = []
        for i in range(80):
            p = 50.0 - (i * 0.1) + math.sin(i / 3.0) * 2.0
            kl_sell2.append([f"2026-01-{i+1:02d}", round(p - 0.1, 2), round(p, 2), round(p + 0.5, 2), round(p - 0.5, 2), 1000])
        res_sell2 = chan_analysis_structured(kl_sell2, 'sh600004')
        sig_types_sell2 = [s['type'] for s in res_sell2.get('signals', [])]
        self.assertIn('二卖警戒', sig_types_sell2)
        self.assertIn('二卖警戒', res_sell2.get('hint', ''))

    def test_chan_three_buy_sell_pullback_verification(self):
        """专项测试：三买三卖回抽验证——回抽在中枢外则确认，回抽入中枢则降级"""
        import math

        # 1. 先震荡形成中枢后突破上行，回抽在中枢上轨之上 → 三买候选
        kl_buy3 = []
        for i in range(100):
            if i < 55:
                c = 11 + math.sin(i / 2.0) * 1.0
            elif i < 70:
                c = 11 + (i - 55) * 0.35
            else:
                c = 16.25 - (i - 70) * 0.12
            kl_buy3.append([f"2026-01-{i+1:03d}", round(c, 2), round(c, 2), round(c + 0.5, 2), round(c - 0.5, 2), 1000])
        res_buy3 = chan_analysis_structured(kl_buy3, 'sh600010')
        buy3_sigs = [s for s in res_buy3.get('signals', []) if '三买' in s.get('type', '')]
        for s in buy3_sigs:
            self.assertIn(s['type'], ['三买候选', '三买待确认'],
                          f"三买信号必须是候选或待确认，收到: {s['type']}")

        # 2. 先震荡形成中枢后突破下行，回抽在中枢下轨之下 → 三卖警戒
        kl_sell3 = []
        for i in range(100):
            if i < 55:
                c = 11 + math.sin(i / 2.0) * 1.0
            elif i < 70:
                c = 11 - (i - 55) * 0.35
            else:
                c = 5.75 + (i - 70) * 0.10
            kl_sell3.append([f"2026-01-{i+1:03d}", round(c, 2), round(c, 2), round(c + 0.5, 2), round(c - 0.5, 2), 1000])
        res_sell3 = chan_analysis_structured(kl_sell3, 'sh600011')
        sell3_sigs = [s for s in res_sell3.get('signals', []) if '三卖' in s.get('type', '')]
        for s in sell3_sigs:
            self.assertIn(s['type'], ['三卖警戒', '三卖待确认'],
                          f"三卖信号必须是警戒或待确认，收到: {s['type']}")

        # 3. 回抽入中枢场景：突破后大幅回撤进入中枢区间 → 应降级为待确认
        kl_buy3_fail = []
        for i in range(100):
            if i < 55:
                c = 11 + math.sin(i / 2.0) * 1.0
            elif i < 65:
                c = 11 + (i - 55) * 0.4
            else:
                c = 15 - (i - 65) * 0.25
            kl_buy3_fail.append([f"2026-01-{i+1:03d}", round(c, 2), round(c, 2), round(c + 0.5, 2), round(c - 0.5, 2), 1000])
        res_buy3_fail = chan_analysis_structured(kl_buy3_fail, 'sh600012')
        fail_sigs = [s for s in res_buy3_fail.get('signals', []) if '三买' in s.get('type', '')]
        for s in fail_sigs:
            self.assertIn(s['type'], ['三买候选', '三买待确认'],
                          f"回抽失败场景信号类型必须合法，收到: {s['type']}")



class TestCoreQuality(unittest.TestCase):
    """涨停质量多因子评分测试"""

    def test_auxiliary_scores(self):
        self.assertEqual(_lu_time_score(92500), 10.0)
        self.assertEqual(_lu_time_score(94000), 8.0)
        self.assertEqual(_lu_time_score(110000), 5.0)
        self.assertEqual(_lu_time_score(133000), 2.0)
        self.assertEqual(_lu_time_score(143000), 0.0)
        self.assertIsNone(_lu_time_score(None))

        self.assertEqual(_lu_seal_score(6.0), 10.0)
        self.assertEqual(_lu_seal_score(2.0), 7.0)
        self.assertEqual(_lu_seal_score(0.6), 4.0)
        self.assertEqual(_lu_seal_score(0.2), 2.0)
        self.assertEqual(_lu_seal_score(0.05), 0.0)
        self.assertIsNone(_lu_seal_score(None))

        self.assertEqual(_lu_board_score(2), 10.0)
        self.assertEqual(_lu_board_score(3), 6.0)
        self.assertEqual(_lu_board_score(1), 4.0)
        self.assertEqual(_lu_board_score(4), 2.0)

    def test_limit_up_quality_golden_case(self):
        """黄金最强2板: 9:25竞价封板 + 封单占流通>5% + 2板 + 0炸板"""
        stock = {
            'fbt': 92500,
            'lbc': 2,
            'zbc': 0,
            'ltsz': 100000000,
            'fund': 10000000   # 10% 封单
        }
        score, detail = limit_up_quality(stock)
        self.assertEqual(score, 10.0)
        self.assertEqual(detail['used_factors'], 3)
        self.assertFalse(detail['missing'])

    def test_limit_up_quality_blown_board_penalty(self):
        """烂板多次扣分测试"""
        stock = {
            'fbt': 93000,
            'lbc': 2,
            'zbc': 3,          # 3次炸板扣 1.5分
            'ltsz': 100000000,
            'fund': 10000000
        }
        score, detail = limit_up_quality(stock)
        self.assertEqual(score, 8.5)


class TestCoreEmotion(unittest.TestCase):
    """情绪指标测试"""

    def test_emotion_band(self):
        # 阈值标定 (2026-10-25): 33/45/60/72，基于38条历史存档实证分布
        self.assertEqual(emotion_band(20), '冰点')
        self.assertEqual(emotion_band(40), '退潮/偏冷')
        self.assertEqual(emotion_band(50), '中性')
        self.assertEqual(emotion_band(65), '活跃')
        self.assertEqual(emotion_band(80), '亢奋')
        # 边界验证：阈值点归属上一区间（< 语义）
        self.assertEqual(emotion_band(33), '退潮/偏冷')
        self.assertEqual(emotion_band(45), '中性')
        self.assertEqual(emotion_band(60), '活跃')
        self.assertEqual(emotion_band(72), '亢奋')

    def test_emotion_score_v1(self):
        s = emotion_score_v1(n_zt=80, n_zb=0, n_dt=0, max_lb=8)
        self.assertEqual(s, 85.0)

    def test_emotion_score_v2_and_divergence(self):
        # 模拟表面情绪高，但赚钱效应差（炸板率高、接力亏钱）
        eff_weak = {
            'available': True,
            'premium': -1.5,
            'rate_1to2': 10.0,
            'score': 0.2
        }
        s, diverge = emotion_score_v2(n_zt=50, n_zb=20, n_dt=2, max_lb=5, eff=eff_weak)
        self.assertGreater(s, 0)
        if s >= 50:
            self.assertEqual(diverge, 'score_high_effect_weak')

        # 扁平化数据
        flat = effect_flat(eff_weak)
        self.assertIsNotNone(flat)
        self.assertEqual(flat['premium'], -1.5)

    def test_emotion_score_v2_extreme_bull_and_clamp(self):
        # 极端亢奋行情：涨停150只、0炸板、0跌停、最高板10、赚钱效应满分（传 1.5 验证 clamp）
        # v2 权重合计 = 10+18+17+12+25 = 82，即「理论上限 82 分」。
        # 修复 (2026-10-25): 亢奋线已从 80 降至 72，82 分可稳定触发"亢奋"相位。
        eff_extreme = {
            'available': True,
            'premium': 6.0,
            'rate_1to2': 60.0,
            'score': 1.5  # 传入 > 1.0 验证 clamp 至 1.0
        }
        score, diverge = emotion_score_v2(n_zt=150, n_zb=0, n_dt=0, max_lb=10, eff=eff_extreme)
        self.assertAlmostEqual(score, 82.0, places=2, msg="极端牛市样本应顶到 v2 理论上限 82")
        self.assertLessEqual(score, 100.0, "情绪分上限必须严格截断至 100")
        # 修复验证：82 分在新阈值下应映射为"亢奋"（旧阈值 80 时仅 80~82 可达，几乎不可能）
        self.assertEqual(emotion_band(score), '亢奋', "v2 理论上限 82 必须落入亢奋相位")

        # clamp 生效证明：eff.score 传 1.5 与传 1.0 必须得到同一分数
        eff_full = dict(eff_extreme, score=1.0)
        score_full, _ = emotion_score_v2(n_zt=150, n_zb=0, n_dt=0, max_lb=10, eff=eff_full)
        self.assertAlmostEqual(score, score_full, places=6, msg="eff.score>1 必须被 clamp 到 1.0")

        # 验证 eff.score 极度恶化为负值时的下限截断
        eff_negative = {
            'available': True,
            'score': -0.5
        }
        score_neg, _ = emotion_score_v2(n_zt=0, n_zb=20, n_dt=30, max_lb=0, eff=eff_negative)
        self.assertGreaterEqual(score_neg, 0.0, "情绪分下限必须截断至 0")
        self.assertAlmostEqual(score_neg, 0.0, places=2, msg="负向越界应被 clamp 到 0")


if __name__ == '__main__':
    unittest.main()
