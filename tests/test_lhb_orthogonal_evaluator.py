import unittest
import numpy as np
from pathlib import Path
import sys

# 让 `python tests/test_xxx.py` 与 `python -m unittest` 两种跑法都能找到 scripts/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(_PROJECT_ROOT), str(_PROJECT_ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lhb_orthogonal_evaluator import LHBOrthogonalEvaluator, LHBSeatConfig, SeatReputationLedger


class TestLHBOrthogonalEvaluatorV2(unittest.TestCase):
  """龙虎榜反套皮与正交验身引擎 V2 单元测试套件"""

  def setUp(self) -> None:
    self.cfg = LHBSeatConfig()
    self.ledger = SeatReputationLedger(self.cfg)
    # 注册知名游资与普通席位先验
    self.ledger.register_static_priors({
        "六一中路": 1.0,
        "呼家楼": 0.9,
        "机构专用A": 0.8,
        "深股通专用": 0.7,
        "中信上海分公司": 0.6,
        "陈小群常驻席位": 0.85,
        "某被借壳老牌席位": 0.8,
        "量化总部席位A": 0.0,
        "量化总部席位B": 0.0,
        "东财拉萨团结路第一": -0.5,
        "东财拉萨东环路第二": -0.5,
    })
    # 给真游资与核心机构席位注入良好的历史对账表现 (高开溢价、无核按钮、低回落)
    for seat in ["六一中路", "呼家楼", "机构专用A", "深股通专用", "中信上海分公司"]:
      for _ in range(10):
        self.ledger.record_post_performance(seat, 0.045, 0.005, 0.01)

    self.evaluator = LHBOrthogonalEvaluator(self.ledger, self.cfg)

  def test_1_non_limit_up_trend_capacity_leader_passes(self) -> None:
    """【验证修复1】非涨停趋势容量中军（如大换手涨8%上榜）不被封单衰减器误杀"""
    buy_seats = ["呼家楼", "六一中路", "机构专用A", "深股通专用", "中信上海分公司"]
    buy_amounts = np.array([1.2e8, 0.9e8, 0.8e8, 0.7e8, 0.5e8])
    buy_side_sells = np.array([0.0, 0.0, 0.05e8, 0.1e8, 0.0])
    sell_amounts = np.array([0.6e8, 0.5e8, 0.4e8, 0.3e8, 0.3e8])
    is_retail = np.array([False, False, False, False, False])

    res = self.evaluator.evaluate_board(
        buy_seats=buy_seats,
        buy_amounts=buy_amounts,
        buy_side_sells=buy_side_sells,
        sell_amounts=sell_amounts,
        is_retail_seat=is_retail,
        total_turnover=35.0e8,  # 35亿大成交趋势中军
        float_cap=150.0e8,  # 150亿流通盘 (换手率23.3%上榜)
        vw_dvr=0.32,  # 盘口主动承接极强
        limit_strength=0.0,  # 未涨停，无封单
        first_seal_norm_time=1.0,  # 未封板
        seal_withdraw_ratio=0.0,
        is_limit_up=False,  # 走趋势容量中军模态
        above_vwap_ratio=0.88,  # 全天88%时间站稳分时均线之上
        tail_30m_support=0.82,  # 尾盘抢筹承接强劲
    )

    self.assertTrue(res["gate_passed"], "趋势中军应当顺利通过门禁")
    self.assertEqual(len(res["veto_tags"]), 0)
    self.assertGreater(
        res["micro_multipliers"]["psi_commit"],
        0.80,
        "非涨停趋势票的定力乘子不应被零封单误杀",
    )
    self.assertGreater(
        res["total_lhb_score"], 8.0, "真游资主买趋势大票应获得显著正分"
    )

  def test_2_deduplicated_net_imbalance_prevents_double_counting(self) -> None:
    """【验证修复2】买五与卖五重叠席位的卖额不发生二次重复扣减"""
    buy_seats = [
        "呼家楼",
        "东财拉萨团结路第一",
        "东财拉萨东环路第二",
        "量化总部席位A",
        "中信北京",
    ]
    # 拉萨与量化同时在买五和卖五双向出现
    buy_amounts = np.array([6000.0, 2000.0, 1800.0, 1500.0, 1200.0])  # 买五总买 12500
    buy_side_sells = np.array(
        [0.0, 2100.0, 1900.0, 1600.0, 0.0]
    )  # 买五同席位卖 5600

    # 卖五席位中，前三个正是买五里的拉萨与量化席位！只有后两个是纯卖出新席位
    sell_seats = [
        "东财拉萨团结路第一",
        "东财拉萨东环路第二",
        "量化总部席位A",
        "某机构席位",
        "某减持席位",
    ]
    sell_amounts = np.array([2100.0, 1900.0, 1600.0, 1500.0, 1000.0])
    sell_side_buys = np.array([2000.0, 1800.0, 1500.0, 0.0, 0.0])
    is_retail = np.array([False, True, True, False, False])

    total_turnover = 80000.0
    res = self.evaluator.evaluate_board(
        buy_seats=buy_seats,
        buy_amounts=buy_amounts,
        buy_side_sells=buy_side_sells,
        sell_amounts=sell_amounts,
        is_retail_seat=is_retail,
        total_turnover=total_turnover,
        float_cap=500000.0,
        vw_dvr=0.35,
        limit_strength=0.75,
        first_seal_norm_time=0.2,
        seal_withdraw_ratio=0.1,
        is_limit_up=True,
        sell_seats=sell_seats,
        sell_side_buys=sell_side_buys,
    )

    # 真实唯一席位总买 = 12500, 真实唯一席位总卖 = 2100+1900+1600+1500+1000 = 8100
    # 真实净流入 = +4400 (+5.50%)，绝不是重复扣减后的 12500 - 5600 - 8100 = -1200 (-1.5%)
    expected_imbalance = (12500.0 - 8100.0) / total_turnover
    self.assertAlmostEqual(
        res["lhb_net_imbalance"], expected_imbalance, places=4
    )
    self.assertGreater(res["lhb_net_imbalance"], 0.0)
    self.assertNotIn("RETAIL_BAGHOLDING_TRAP", res["veto_tags"])

  def test_3_asymmetric_bayes_shrinkage_and_fast_kill_breaker(self) -> None:
    """【验证修复3】非对称贝叶斯收缩不保护恶棍，且近5次3次核按钮触发借壳熔断"""
    # 场景A: 某新席位首次上榜就恶意低开-4%且开盘5分钟核按钮暴跌6%
    self.ledger.record_post_performance(
        "新晋砸盘帮席位", r_open_excess=-0.04, d_nuc_5m=0.06, u_trap=0.05
    )
    gamma_bad_new, _ = self.ledger.get_dynamic_reputation("新晋砸盘帮席位")

    # 若按旧版除以 (w + 3.0)，负分会被稀释一半以上；新版零收缩+1.2倍放大，负分必须深于 -0.80
    self.assertLess(
        gamma_bad_new, -0.80, "单次恶性核按钮记录严禁被小样本常数向0稀释"
    )

    # 场景B: 老牌高信誉席位（先验0.8 + 10次优质记录）近期被李鬼借壳，近5次有3次恶意核按钮
    for _ in range(10):
      self.ledger.record_post_performance(
          "某被借壳老牌席位", 0.04, 0.005, 0.01
      )
    gamma_before, flag_before = self.ledger.get_dynamic_reputation(
        "某被借壳老牌席位"
    )
    self.assertGreater(gamma_before, 0.45)
    self.assertFalse(flag_before)

    # 注入近 5 次记录中的 3 次恶意核按钮
    self.ledger.record_post_performance("某被借壳老牌席位", -0.035, 0.055, 0.04)
    self.ledger.record_post_performance("某被借壳老牌席位", -0.040, 0.060, 0.05)
    self.ledger.record_post_performance("某被借壳老牌席位", 0.010, 0.010, 0.01)
    self.ledger.record_post_performance("某被借壳老牌席位", -0.030, 0.050, 0.04)

    gamma_after, flag_after = self.ledger.get_dynamic_reputation(
        "某被借壳老牌席位"
    )
    self.assertTrue(
        flag_after, "近5次出现3次核按钮必须触发 NUCLEAR_HARVESTER 熔断"
    )
    self.assertLess(
        gamma_after, 0.0, "借壳熔断后老功劳簿权重砍90%，信誉必须立刻转负"
    )

  def test_4_quant_pingpong_and_fake_shell_explicit_penalty(self) -> None:
    """【验证修复4】量化做T识别与李鬼掩护出货（显式扣减 -15.0 分）"""
    buy_seats = [
        "六一中路",
        "量化总部席位A",
        "量化总部席位B",
        "游资跟风甲",
        "游资跟风乙",
    ]
    # 六一中路买4000万；两个量化席位大额双向吞吐做T（买5000万卖4800万）
    buy_amounts = np.array([4000.0, 5000.0, 4500.0, 1500.0, 1000.0])
    buy_side_sells = np.array([0.0, 4800.0, 4400.0, 0.0, 0.0])
    sell_amounts = np.array([6000.0, 4800.0, 4400.0, 3000.0, 2000.0])
    is_retail = np.array([False, False, False, False, False])

    # 全天 VW-DVR 高达 0.68（严重放量下杀出货），触发李鬼掩护出货 + 量化对倒洗盘
    res = self.evaluator.evaluate_board(
        buy_seats=buy_seats,
        buy_amounts=buy_amounts,
        buy_side_sells=buy_side_sells,
        sell_amounts=sell_amounts,
        is_retail_seat=is_retail,
        total_turnover=80000.0,
        float_cap=400000.0,
        vw_dvr=0.68,  # 高 DVR 派发态
        limit_strength=0.20,
        first_seal_norm_time=0.85,
        seal_withdraw_ratio=0.50,
        is_limit_up=True,
    )

    self.assertFalse(res["gate_passed"])
    self.assertIn("FAKE_SHELL_DISTRIBUTION_COVER", res["veto_tags"])
    self.assertIn("QUANT_PINGPONG_WASH", res["veto_tags"])
    self.assertTrue(res["seat_breakdown"]["量化总部席位A"]["is_quant_t"])
    self.assertTrue(res["seat_breakdown"]["量化总部席位B"]["is_quant_t"])
    # 显式扣分 -15.0 (李鬼掩护出货) + -8.0 (量化对倒) + 负向席位分，必须触及深红告警下限区间
    self.assertLessEqual(res["total_lhb_score"], -20.0)


if __name__ == "__main__":
  unittest.main(verbosity=2)
