# benchmarks/quant_validation.py
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import numpy as np
import pandas as pd
from scipy import stats


@dataclass
class GateVerdict:
    gate_name: str
    passed: bool
    metrics: Dict[str, float]
    reason: str


class QuantValidationPipeline:
    """
    A股超短与选股因子 5 道硬门禁准入流水线
    支持 mode='cross_sectional' (全市场连续因子) 与 mode='event_sparse' (超短稀疏打板/异动信号)
    """

    def __init__(
        self,
        mode: str = "event_sparse",
        min_ic_ir: float = 0.5,
        min_t_stat: float = 2.0,
        min_monotonicity_rho: float = 0.8,
        n_permutations: int = 500,
    ):
        self.mode = mode
        self.min_ic_ir = min_ic_ir
        self.min_t_stat = min_t_stat
        self.min_monotonicity_rho = min_monotonicity_rho
        self.n_permutations = n_permutations

    def run_all_gates(self, df: pd.DataFrame) -> Dict[str, GateVerdict]:
        """
        统一入口
        :param df: 面板数据，必须包含列:
                   ['date', 'symbol', 'signal', 'in_candidate_pool',
                    'ret_1d', 'ret_3d', 'ret_5d', 'ret_10d',
                    'market_regime', 'turnover_pct_rank', 'mcap_pct_rank']
                   其中 'signal' > 0 代表触发或打分值，'in_candidate_pool' 为当日涨停池/异动基准池布尔值
        """
        results = {
            "Gate1_Pattern_Decoupling": self.gate1_ic_and_time_series(df),
            "Gate2_Monotonicity": self.gate2_quantile_monotonicity(df),
            "Gate3_WalkForward_OOS": self.gate3_walk_forward_oos(df),
            "Gate4_PostMortem_Matrix": self.gate4_failure_attribution(df),
            "Gate5_MonteCarlo_Permutation": self.gate5_permutation_test(df),
        }
        return results

    # ================= 门禁 1：横截面 IC 与时序左尾分布解耦 =================
    def gate1_ic_and_time_series(self, df: pd.DataFrame) -> GateVerdict:
        # 1. 横截面 Rank IC（超短模式下仅在候选活跃池内计算打分区分度）
        pool_df = df[df["in_candidate_pool"] == True] if self.mode == "event_sparse" else df

        def _daily_rank_ic(g: pd.DataFrame) -> float:
            if len(g) < 5 or g["signal"].nunique() < 2:
                return np.nan
            return g["signal"].corr(g["ret_3d"], method="spearman")

        ic_series = pool_df.groupby("date", group_keys=False).apply(_daily_rank_ic).dropna()
        ic_mean = float(ic_series.mean()) if len(ic_series) > 0 else 0.0
        ic_std = float(ic_series.std(ddof=1)) if len(ic_series) > 1 else 1e-6
        ic_ir = ic_mean / ic_std if ic_std > 0 else 0.0
        t_stat = ic_ir * np.sqrt(len(ic_series))

        # 2. 时序分布：统计信号触发后 (signal > 0) 未来 1/3/5/10 日左尾 5% VaR 与偏度
        triggered = df[df["signal"] > 0]
        ts_metrics = {}
        for h in [1, 3, 5, 10]:
            col = f"ret_{h}d"
            if col in triggered.columns and len(triggered) > 0:
                s = triggered[col].dropna()
                ts_metrics[f"{col}_mean"] = round(float(s.mean()), 4)
                ts_metrics[f"{col}_VaR_5pct"] = round(float(np.percentile(s, 5)), 4)
                ts_metrics[f"{col}_skew"] = round(float(stats.skew(s)), 3)

        passed = (ic_ir >= self.min_ic_ir) and (abs(t_stat) >= self.min_t_stat)
        return GateVerdict(
            gate_name="规律分型(截面IC与时序左尾风险)",
            passed=bool(passed),
            metrics={"IC_Mean": round(ic_mean, 4), "IC_IR": round(ic_ir, 3), "t_stat": round(t_stat, 2), **ts_metrics},
            reason="通过" if passed else f"IC_IR({ic_ir:.2f})或t统计量({t_stat:.2f})未达标",
        )

    # ================= 门禁 2：5 分组单调性 & 剔除 Q5 单点污染 =================
    def gate2_quantile_monotonicity(self, df: pd.DataFrame) -> GateVerdict:
        active = df[df["signal"] > 0].copy() if self.mode == "event_sparse" else df.copy()
        if len(active) < 50:
            return GateVerdict("分组单调性", False, {}, "有效信号样本量不足50，无法进行5分组检验")

        # 按信号打分切分 Q1 ~ Q5
        active["quantile"] = pd.qcut(active["signal"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5])
        q_rets = active.groupby("quantile", observed=False)["ret_3d"].mean()

        # 检验 1: Spearman 秩相关系数检验梯队单调递增
        rho, _ = stats.spearmanr([1, 2, 3, 4, 5], q_rets.values)

        # 检验 2: 识别“仅 Q5 奇高、Q1~Q4 乱序或无差异”的极端样本污染
        q1_to_q4_rho, _ = stats.spearmanr([1, 2, 3, 4], q_rets.values[:4])
        q5_jump_ratio = (q_rets.loc[5] - q_rets.loc[4]) / (abs(q_rets.loc[4] - q_rets.loc[1]) + 1e-6)
        is_q5_outlier_polluted = (q1_to_q4_rho < 0.2) and (q5_jump_ratio > 3.0)

        passed = (rho >= self.min_monotonicity_rho) and (not is_q5_outlier_polluted)
        return GateVerdict(
            gate_name="5分组单调性检验",
            passed=bool(passed),
            metrics={
                "spearman_rho": round(float(rho), 3),
                "q1_to_q4_rho": round(float(q1_to_q4_rho), 3),
                **{f"Q{i}_ret3d": round(float(q_rets.loc[i]), 4) for i in range(1, 6)},
            },
            reason="单调性良好" if passed else ("检测到仅Q5奇高、Q1-Q4乱序的过拟合污染" if is_q5_outlier_polluted else f"单调性系数({rho:.2f})不足"),
        )

    # ================= 门禁 3：Walk-Forward 分年度/市场状态滚动检验 =================
    def gate3_walk_forward_oos(self, df: pd.DataFrame) -> GateVerdict:
        triggered = df[df["signal"] > 0].copy()
        triggered["year"] = pd.to_datetime(triggered["date"]).dt.year

        yearly_stats = {}
        profitable_years = 0
        total_years = 0

        for yr, g in triggered.groupby("year"):
            total_years += 1
            mean_ret = float(g["ret_3d"].mean())
            win_rate = float((g["ret_3d"] > 0).mean())
            yearly_stats[f"{yr}_mean_ret"] = round(mean_ret, 4)
            yearly_stats[f"{yr}_win_rate"] = round(win_rate, 3)
            if mean_ret > 0:
                profitable_years += 1

        # 要求至少 75% 以上的独立年份保持正期望，拒绝单一年份牛市暴利掩盖其余年份亏损
        consistency_ratio = profitable_years / max(1, total_years)
        passed = consistency_ratio >= 0.75
        return GateVerdict(
            gate_name="Walk-Forward跨周期稳健性",
            passed=bool(passed),
            metrics={"profitable_year_ratio": round(consistency_ratio, 2), **yearly_stats},
            reason="跨周期稳健" if passed else "策略过度依赖单一年度/单一牛市行情，样本外衰减严重",
        )

    # ================= 门禁 4：失败样本归因矩阵 (反向生成熔断条件) =================
    def gate4_failure_attribution(self, df: pd.DataFrame) -> GateVerdict:
        triggered = df[df["signal"] > 0].copy()
        losers = triggered[triggered["ret_3d"] < -0.05]  # 聚焦大面样本 (3日亏损超5%)

        if len(losers) == 0 or len(triggered) == 0:
            return GateVerdict("失败样本归因矩阵", True, {}, "无显著大面样本")

        # 计算各市场环境切片下的“大面率 (Crash Rate)”
        regime_crash_rate = (
            triggered.groupby("market_regime")
            .apply(lambda g: (g["ret_3d"] < -0.05).mean())
            .to_dict()
        )
        # 找出大面率最高的致命死穴环境，用于写入实盘熔断配置
        worst_regime = max(regime_crash_rate, key=regime_crash_rate.get)
        worst_rate = regime_crash_rate[worst_regime]

        return GateVerdict(
            gate_name="失败样本归因与熔断提炼",
            passed=True,  # 归因模块作为诊断与熔断器生成器输出
            metrics={f"crash_rate_{k}": round(float(v), 3) for k, v in regime_crash_rate.items()},
            reason=f"已定位策略死穴：在【{worst_regime}】环境下大面率高达 {worst_rate*100:.1f}%，建议实盘设为硬熔断闸门",
        )

    # ================= 门禁 5：同日截面蒙特卡洛置换检验 (500次) =================
    def gate5_permutation_test(self, df: pd.DataFrame) -> GateVerdict:
        """
        核心逻辑：保持每日开仓数量不变，在每个开仓日的当日活跃候选池(in_candidate_pool)中
        随机盲抽同等数量的股票，重复 500 次，检验真实策略是否处于随机分布的 Top 5% (p < 0.05)
        """
        triggered = df[df["signal"] > 0]
        if len(triggered) == 0:
            return GateVerdict("蒙特卡洛置换检验", False, {}, "无触发样本")

        real_mean_ret = float(triggered["ret_3d"].mean())
        daily_counts = triggered.groupby("date").size().to_dict()

        # 预构建每日候选池收益数组，加速 500 次置换
        pool_df = df[df["in_candidate_pool"] == True]
        daily_pool_rets = {
            dt: grp["ret_3d"].dropna().values
            for dt, grp in pool_df.groupby("date")
            if dt in daily_counts
        }

        rng = np.random.default_rng(seed=42)
        random_strategy_means = np.zeros(self.n_permutations)

        for i in range(self.n_permutations):
            sampled_rets = []
            for dt, k_count in daily_counts.items():
                pool_arr = daily_pool_rets.get(dt, np.array([]))
                if len(pool_arr) >= k_count:
                    sampled_rets.append(rng.choice(pool_arr, size=k_count, replace=False))
                elif len(pool_arr) > 0:
                    sampled_rets.append(rng.choice(pool_arr, size=k_count, replace=True))
            if sampled_rets:
                random_strategy_means[i] = np.concatenate(sampled_rets).mean()

        # 计算单侧 p-value (真实收益被打败的比例)
        p_value = float(np.mean(random_strategy_means >= real_mean_ret))
        percentile_95 = float(np.percentile(random_strategy_means, 95))
        passed = p_value < 0.05

        return GateVerdict(
            gate_name="蒙特卡洛置换检验(500次同日盲抽)",
            passed=bool(passed),
            metrics={
                "real_mean_ret": round(real_mean_ret, 4),
                "random_95th_ret": round(percentile_95, 4),
                "p_value": round(p_value, 4),
            },
            reason="显著跑赢随机基准" if passed else f"p={p_value:.3f} >= 0.05，无法排除纯情绪Beta与运气噪音",
        )
