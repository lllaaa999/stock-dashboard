from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import numpy as np


@dataclass
class LHBSeatConfig:
  """龙虎榜反套皮与正交验身算子超参数配置（V2 排毒生产版）"""

  prior_weight: float = 0.08  # 席位名称静态先验最大权重 (<= 0.10)
  purity_deadzone: float = 0.25  # 量化做T轧差纯度死区阈值 (|NetRatio| < 0.25)
  purity_full_thresh: float = 0.80  # 满额主升净买入纯度阈值
  dvr_flip_center: float = 0.58  # VW-DVR 掩护出货极性翻转中心点
  dvr_flip_slope: float = 15.0  # VW-DVR Sigmoid 翻转陡峭度
  monopoly_turn_thresh: float = 0.25  # 买一占全天成交额上限 (25%)
  monopoly_float_thresh: float = 0.03  # 买一占自由流通市值上限 (3.0%)
  low_turn_exemption: float = 0.06  # 缩量板换手率豁免基准 (6%以下线性折减成交占比惩罚)
  quant_wash_gross_ratio: float = 0.15  # 量化双向对倒占总成交额警戒线 (15%)
  retail_pollution_thresh: float = 0.45  # 拉萨散户天团占买五总额警戒线 (45%)
  ledger_window: int = 20  # 席位历史对账滑动窗口长度
  bayes_shrinkage_pos_k: float = 3.0  # 正向表现小样本经验贝叶斯收缩常数 (防假繁荣)
  downside_penalty_amp: float = 1.20  # 负向核按钮恶棍惩罚放大系数 (零收缩直接打满)
  trend_vwap_weight: float = 0.55  # 非涨停趋势票：日内VWAP站上率权重
  trend_tail_weight: float = 0.45  # 非涨停趋势票：尾盘30分钟承接强度权重


class SeatReputationLedger:
  """席位信誉时序自适应衰减状态机（支持非对称贝叶斯收缩与防李鬼借壳熔断）"""

  def __init__(self, config: LHBSeatConfig = LHBSeatConfig()):
    self.cfg = config
    # 存储结构: seat_name -> shape (N, 3) 矩阵 [r_open_excess, d_nuc_5m, u_trap]
    self.history: Dict[str, np.ndarray] = {}
    self.static_priors: Dict[str, float] = {}

  def register_static_priors(self, priors: Dict[str, float]) -> None:
    """注册极弱静态先验 (-1.0 ~ +1.0)"""
    for seat, val in priors.items():
      self.static_priors[seat] = float(np.clip(val, -1.0, 1.0))

  def record_post_performance(
      self,
      seat_name: str,
      r_open_excess: float,
      d_nuc_5m: float,
      u_trap: float,
  ) -> None:
    """盘后对账：记录席位作为主买上榜后的次日真实盘口表现"""
    new_row = np.array([[r_open_excess, d_nuc_5m, u_trap]], dtype=np.float64)
    if seat_name not in self.history:
      self.history[seat_name] = new_row
    else:
      updated = np.vstack([self.history[seat_name], new_row])
      self.history[seat_name] = updated[-self.cfg.ledger_window :]

  def get_dynamic_reputation(self, seat_name: str) -> Tuple[float, bool]:
    """计算单个席位的当前后验信誉系数 tilde_gamma_i 及是否触发【核按钮黑名单】

    返回: (tilde_gamma_i in [-1, 1], is_nuclear_harvester)
    """
    eps = 1e-9
    p0 = self.static_priors.get(seat_name, 0.0)
    hist = self.history.get(seat_name, None)

    if hist is None or len(hist) == 0:
      return float(self.cfg.prior_weight * p0), False

    r_open = hist[:, 0]
    d_nuc = hist[:, 1]
    u_trap = hist[:, 2]

    # 1. 向量化计算单次上榜真实后验效用 u_k (正负项尺度平衡归一化)
    u_k = (
        0.85 * np.tanh(r_open / 0.03)
        - 0.40 * np.clip(d_nuc / 0.04, 0.0, 1.5)
        - 0.15 * np.clip(u_trap / 0.06, 0.0, 1.0)
    )

    n = len(u_k)
    # 2. 基准指数衰减权重 (越近权重越大)
    exponents = np.arange(n - 1, -1, -1, dtype=np.float64)
    weights = np.power(0.88, exponents)

    # 3. 非对称惩罚：次日恶意低开且5分钟核按钮的记录，权重放大 2.5 倍
    is_bad_dump = (r_open < -0.02) & (d_nuc > 0.03)
    weights = np.where(is_bad_dump, weights * 2.5, weights)

    # 4. 近 5 次借壳突变熔断检测 (Fast-Kill Gate)
    recent_m = min(n, 5)
    recent_dumps = int(np.sum(u_k[-recent_m:] < -0.25))
    is_nuclear_harvester = bool(recent_dumps >= 3)

    if is_nuclear_harvester and n > 5:
      # 触发借壳熔断：历史老功劳簿权重直接砍掉 90%，瞬间暴露李鬼本色
      weights[:-5] *= 0.10

    # 5. 【修复3】非对称经验贝叶斯收缩：正向防假繁荣，负向零收缩严惩恶棍
    w_sum = float(np.sum(weights))
    weighted_sum = float(np.sum(weights * u_k))
    raw_mean = weighted_sum / (w_sum + eps)

    if raw_mean >= 0.0 and not is_nuclear_harvester:
      # 正向表现执行小样本收缩 (kappa = 3.0)
      gamma_dynamic = weighted_sum / (w_sum + self.cfg.bayes_shrinkage_pos_k)
      effective_p0 = p0
    else:
      # 负向表现或已触发核按钮熔断：绝不向 0 收缩，若含恶意核按钮则放大惩罚
      amp = self.cfg.downside_penalty_amp if np.any(is_bad_dump) else 1.0
      gamma_dynamic = min(0.0, raw_mean * amp)
      # 一旦账本变负或触发熔断，禁止正向静态名气先验做护身符
      effective_p0 = min(0.0, p0)

    gamma_dynamic = float(np.clip(gamma_dynamic, -1.0, 1.0))
    tilde_gamma = (
        self.cfg.prior_weight * effective_p0
        + (1.0 - self.cfg.prior_weight) * gamma_dynamic
    )
    return float(np.clip(tilde_gamma, -1.0, 1.0)), is_nuclear_harvester


class LHBOrthogonalEvaluator:
  """龙虎榜截面结构 x 盘中微观物理轨迹 正交联合验身引擎（V2 排毒生产版）"""

  def __init__(
      self,
      ledger: SeatReputationLedger,
      config: LHBSeatConfig = LHBSeatConfig(),
  ):
    self.ledger = ledger
    self.cfg = config

  @staticmethod
  def _compute_deduplicated_net_imbalance(
      buy_seats: List[str],
      B: np.ndarray,
      S_on_buy: np.ndarray,
      sell_seats: Optional[List[str]],
      S_top5: np.ndarray,
      B_on_sell: Optional[np.ndarray],
      total_turnover: float,
  ) -> float:
    """【修复2】全榜唯一席位去重轧差计算器

    消除双向做T席位或拉萨天团同时出现在买五和卖五时，卖额被重复扣减两次的记账 Bug。
    """
    eps = 1e-9
    unique_ledger: Dict[str, Tuple[float, float]] = {}

    # 录入买方前五席位的 (买入额, 同席位卖出额)
    for i, seat in enumerate(buy_seats):
      b_val = float(B[i])
      s_val = float(S_on_buy[i]) if i < len(S_on_buy) else 0.0
      if seat in unique_ledger:
        prev_b, prev_s = unique_ledger[seat]
        unique_ledger[seat] = (max(prev_b, b_val), max(prev_s, s_val))
      else:
        unique_ledger[seat] = (b_val, s_val)

    # 录入卖方前五席位，若该席位已在买五中出现，则对齐去重，绝不二次累加卖额
    if sell_seats is not None and len(sell_seats) == len(S_top5):
      for j, seat in enumerate(sell_seats):
        s_val = float(S_top5[j])
        b_val = (
            float(B_on_sell[j])
            if (B_on_sell is not None and j < len(B_on_sell))
            else 0.0
        )
        if seat in unique_ledger:
          prev_b, prev_s = unique_ledger[seat]
          unique_ledger[seat] = (max(prev_b, b_val), max(prev_s, s_val))
        else:
          unique_ledger[seat] = (b_val, s_val)
    else:
      # 兼容未传入 sell_seats 名称的旧调用：自动剔除与 S_on_buy 数值完全一致的重叠卖单
      remaining_s_on_buy = list(np.round(S_on_buy[S_on_buy > 0], 2))
      for j, s_raw in enumerate(S_top5):
        s_val = float(s_raw)
        s_round = round(s_val, 2)
        if s_round in remaining_s_on_buy:
          remaining_s_on_buy.remove(s_round)
        else:
          b_val = (
              float(B_on_sell[j])
              if (B_on_sell is not None and j < len(B_on_sell))
              else 0.0
          )
          unique_ledger[f"__UNLABELED_SELL_{j}__"] = (b_val, s_val)

    total_unique_buy = sum(pair[0] for pair in unique_ledger.values())
    total_unique_sell = sum(pair[1] for pair in unique_ledger.values())
    return float((total_unique_buy - total_unique_sell) / (total_turnover + eps))

  def evaluate_board(
      self,
      buy_seats: List[str],
      buy_amounts: np.ndarray,  # 买方前五席位买入额
      buy_side_sells: np.ndarray,  # 买方前五席位同日卖出额 (用于计算 NetRatio)
      sell_amounts: np.ndarray,  # 卖方前五席位卖出额
      is_retail_seat: np.ndarray,  # bool数组: 标记买方席位是否属于拉萨等散户大本营
      total_turnover: float,  # 全天成交总额
      float_cap: float,  # 自由流通市值
      vw_dvr: float,  # 盘中微观算子: VW-DVR 承接/派发比 (0~1, 越小承接越强)
      limit_strength: float = 0.0,  # 涨停封单强度归一化值 (0~1)
      first_seal_norm_time: float = 1.0,  # 首次封板归一化时间 (0.0=9:30, 1.0=15:00)
      seal_withdraw_ratio: float = 0.0,  # 涨停封单撤单率 (0~1)
      is_limit_up: bool = True,  # 【修复1】是否涨停收盘 (False则走趋势容量中军分支)
      above_vwap_ratio: float = 0.75,  # 【修复1】非涨停趋势票: 全天价格站上分时均线时间占比 (0~1)
      tail_30m_support: float = 0.70,  # 【修复1】非涨停趋势票: 尾盘30分钟主动买盘承接强度 (0~1)
      sell_seats: Optional[List[str]] = None,  # 【修复2】卖方前五席位名称列表 (用于精确去重)
      sell_side_buys: Optional[np.ndarray] = None,  # 【修复2】卖方前五席位同日买入额 (可选)
  ) -> Dict[str, object]:
    eps = 1e-9
    B = np.asarray(buy_amounts, dtype=np.float64)
    S_on_buy = np.asarray(buy_side_sells, dtype=np.float64)
    S_top5 = np.asarray(sell_amounts, dtype=np.float64)
    B_on_sell = (
        np.asarray(sell_side_buys, dtype=np.float64)
        if sell_side_buys is not None
        else None
    )
    retail_mask = np.asarray(is_retail_seat, dtype=bool)

    turnover_rate = total_turnover / (float_cap + eps)

    # --- Step 1: 向量化计算席位买卖纯度比 (Net Purity Gate) ---
    gross_vol = B + S_on_buy + eps
    net_vol = B - S_on_buy
    rho = net_vol / gross_vol  # NetRatio in [-1, 1]

    is_quant_t = np.abs(rho) < self.cfg.purity_deadzone
    purity_gate = np.zeros_like(rho)

    # 量化做T死区惩罚
    purity_gate = np.where(
        is_quant_t,
        -0.35 * (1.0 - np.abs(rho) / self.cfg.purity_deadzone),
        purity_gate,
    )
    # 纯多头主升区凸性激活
    pos_mask = rho >= self.cfg.purity_deadzone
    span = self.cfg.purity_full_thresh - self.cfg.purity_deadzone
    purity_gate = np.where(
        pos_mask,
        np.power(
            np.clip((rho - self.cfg.purity_deadzone) / span, 0.0, 1.0), 1.5
        ),
        purity_gate,
    )
    # 净卖出线性惩罚
    neg_mask = rho <= -self.cfg.purity_deadzone
    purity_gate = np.where(neg_mask, rho, purity_gate)

    # --- Step 2: 盘中微观轨迹正交验身乘子 (VW-DVR & 双模态定力因子) ---
    # 2.1 VW-DVR 极性翻转器: 若全天 DVR > 0.58，买单被判定为【掩护出货/被动接盘】
    psi_dvr = float(
        1.0
        - 2.0
        / (
            1.0
            + np.exp(
                -self.cfg.dvr_flip_slope * (vw_dvr - self.cfg.dvr_flip_center)
            )
        )
    )

    # 2.2 【修复1】双模态定力因子: 区分涨停接力板与非涨停趋势容量中军
    if is_limit_up:
      psi_commit = float(
          np.clip(limit_strength, 0.1, 1.0)
          * np.exp(-1.8 * (first_seal_norm_time**2))
          * (1.0 - np.clip(seal_withdraw_ratio, 0.0, 1.0))
      )
    else:
      vwap_ratio_clipped = float(np.clip(above_vwap_ratio, 0.0, 1.0))
      tail_supp_clipped = float(np.clip(tail_30m_support, 0.0, 1.0))
      psi_commit = float(
          np.clip(
              self.cfg.trend_vwap_weight * vwap_ratio_clipped
              + self.cfg.trend_tail_weight * tail_supp_clipped,
              0.15,
              1.0,
          )
      )

    # --- Step 3: 提取席位滚动信誉并合成单席位得分 ---
    gammas = np.zeros(len(buy_seats), dtype=np.float64)
    harvester_flags = np.zeros(len(buy_seats), dtype=bool)
    for idx, name in enumerate(buy_seats):
      gammas[idx], harvester_flags[idx] = self.ledger.get_dynamic_reputation(
          name
      )

    # 资金体量权重: 单个席位净买入占成交额比重
    size_weight = np.clip(
        np.abs(net_vol) / (total_turnover * 0.05 + eps), 0.2, 2.5
    )

    positive_seat_mask = (gammas > 0) & (purity_gate > 0)
    micro_verifier = np.where(
        positive_seat_mask,
        np.where(psi_dvr >= 0.0, psi_dvr * psi_commit, psi_dvr),
        1.0,
    )

    base_direction = np.where(
        is_quant_t | (harvester_flags & (purity_gate > 0)),
        -np.abs(gammas) - 0.3,
        gammas * purity_gate,
    )
    seat_scores = 10.0 * size_weight * base_direction * micro_verifier

    # --- Step 4: 全局边界异常与一票否决门禁 ---
    veto_tags: List[str] = []
    penalty_score = 0.0

    # 4.1 买一独大流动性黑洞检测 (含缩量板换手率豁免补丁)
    b1_turn_share = float(B[0] / (total_turnover + eps)) if len(B) > 0 else 0.0
    b1_float_share = float(B[0] / (float_cap + eps)) if len(B) > 0 else 0.0
    turn_modulator = float(min(1.0, turnover_rate / self.cfg.low_turn_exemption))

    xi_mono = float(
        max(
            (b1_turn_share * turn_modulator) / self.cfg.monopoly_turn_thresh,
            b1_float_share / self.cfg.monopoly_float_thresh,
        )
    )
    if xi_mono >= 1.0:
      veto_tags.append("LIQUIDITY_BLACK_HOLE")
      penalty_score -= 15.0 * xi_mono

    # 4.2 量化高频双向对倒洗盘检测
    quant_gross_share = float(
        np.sum(gross_vol[is_quant_t]) / (total_turnover + eps)
    )
    if (
        int(np.sum(is_quant_t)) >= 2
        and quant_gross_share >= self.cfg.quant_wash_gross_ratio
    ):
      veto_tags.append("QUANT_PINGPONG_WASH")
      seat_scores = np.minimum(seat_scores, 0.0)
      penalty_score -= 8.0

    # 4.3 【修复4】李鬼掩护出货检测: 显式扣减 15 分并削平残余正分
    if np.any(gammas > 0.3) and vw_dvr > 0.60:
      veto_tags.append("FAKE_SHELL_DISTRIBUTION_COVER")
      seat_scores = np.minimum(seat_scores, 0.0)
      penalty_score -= 15.0

    # 4.4 核按钮收割机现身检测
    if np.any(harvester_flags):
      veto_tags.append("NUCLEAR_HARVESTER_PRESENT")
      penalty_score -= 10.0 * int(np.sum(harvester_flags))

    # 4.5 【修复2】真游资单挑“拉萨天团”诱多局检测 (采用去重后的真实全榜失衡度)
    retail_buy_ratio = float(np.sum(B[retail_mask]) / (np.sum(B) + eps))
    lhb_net_imbalance = self._compute_deduplicated_net_imbalance(
        buy_seats=buy_seats,
        B=B,
        S_on_buy=S_on_buy,
        sell_seats=sell_seats,
        S_top5=S_top5,
        B_on_sell=B_on_sell,
        total_turnover=total_turnover,
    )
    if (
        retail_buy_ratio >= self.cfg.retail_pollution_thresh
        and lhb_net_imbalance < -0.05
    ):
      veto_tags.append("RETAIL_BAGHOLDING_TRAP")
      seat_scores = -np.abs(seat_scores)
      penalty_score -= 12.0

    total_score = float(
        np.clip(np.sum(seat_scores) + penalty_score, -30.0, 30.0)
    )
    gate_passed = (len(veto_tags) == 0) and (total_score > 0.0)

    return {
        "total_lhb_score": round(total_score, 3),
        "gate_passed": gate_passed,
        "veto_tags": veto_tags,
        "lhb_net_imbalance": round(lhb_net_imbalance, 4),
        "seat_breakdown": {
            buy_seats[i]: {
                "net_purity_rho": round(float(rho[i]), 3),
                "reputation_gamma": round(float(gammas[i]), 3),
                "is_quant_t": bool(is_quant_t[i]),
                "is_nuclear_harvester": bool(harvester_flags[i]),
                "seat_score": round(float(seat_scores[i]), 3),
            }
            for i in range(len(buy_seats))
        },
        "micro_multipliers": {
            "psi_dvr": round(psi_dvr, 3),
            "psi_commit": round(psi_commit, 3),
            "xi_monopoly": round(xi_mono, 3),
            "is_limit_up": is_limit_up,
        },
    }
