# scripts/resonance_engine.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple
import unittest
import numpy as np
try:
    from scripts.ultrashort_metrics import compute_theme_speed_ranks
except ModuleNotFoundError:
    import os, sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from scripts.ultrashort_metrics import compute_theme_speed_ranks


class ResonanceTag(Enum):
    RESONANCE = "🔥 共振"
    ISOLATED = "⚠️ 孤立"
    COUNTER_TREND = "⚡ 逆势"
    TWIN_CORE_RELAY = "🔄 双子星掩护"
    K_POSITION_USURPING = "👑 卡位夺权"
    NEUTRAL = "➖ 常态跟随"


# 默认剔除的宽泛噪音属性标签（避免因“融资融券”里有其他票涨停而误判共振）
DEFAULT_NOISE_THEMES: Set[str] = {
    "融资融券", "转融券标的", "沪股通", "深股通", "富时罗素", "MSCI中国",
    "标普道琼斯", "证金持股", "央企国企改革", "地方国企改革", "微盘股",
    "高股息", "专精特新", "昨日涨停", "昨日连板", "百元股", "转债标的", "基金重仓"
}


@dataclass
class StockTickSnapshot:
    """单只股票盘中分时截面快照"""
    symbol: str
    name: str
    timestamp: str                     # 格式 "HH:MM:SS" 或 "HH:MM"，如 "09:33:00"
    day_ret_pct: float                 # 当日当前涨跌幅 (%)，如 8.5 代表 +8.5%
    ret_5m_pct: float                  # 最近 5 分钟涨速 (%)，如 3.2 代表 5分钟拉升 3.2%
    open_ret_pct: float                # 09:25 竞价高开幅度 (%)
    vol_ratio: float                   # 当前分时量比 (相对于过去5日同刻均量)，如 2.5
    auction_vol_ratio: float = 1.0     # 09:25 集合竞价量比
    is_limit_up: bool = False          # 当前是否封死涨停
    first_seal_time: Optional[str] = None  # 首次封板时间 "HH:MM:SS"，未封板为 None
    cross_5pct_time: Optional[str] = None  # 突破+5%时间 "HH:MM:SS"，未突破为 None
    prev_boards: int = 0               # 截至昨日的连板数 (首板前为0，昨日首板为1，昨日3连板为3)
    prev_day_ret_pct: float = 0.0      # 昨日收盘涨跌幅 (%)，用于辅助判定反包
    themes: List[str] = field(default_factory=list)  # 所属题材概念列表
    hist_5m_mean_pct: Optional[float] = None         # 过去20日同一时刻 5m 涨速均值 (%)
    hist_5m_std_pct: Optional[float] = None          # 过去20日同一时刻 5m 涨速标准差 (%)


@dataclass
class MarketSnapshot:
    """大盘基准指数盘中分时快照"""
    timestamp: str
    day_ret_pct: float                 # 大盘当日涨跌幅 (%)，如 -1.2 代表跌 1.2%
    ret_5m_pct: float                  # 大盘最近 5 分钟涨速 (%)，如 -0.32 代表 5分钟跳水 0.32%
    hist_5m_std_pct: Optional[float] = None


@dataclass
class ResonanceResult:
    """点面共振引擎输出结果"""
    symbol: str
    name: str
    anchor_theme: str                  # 锚定的当日核心活跃题材
    primary_tag: ResonanceTag          # 最高优先级主角标
    all_tags: List[ResonanceTag]       # 触发的所有角标列表（按优先级排序）
    tag_labels: List[str]              # 字符串角标列表，直接供前端渲染
    evidence: Dict[str, object]        # 触发判定的量化证据链
    theme_speed_rank: Optional[int] = None  # 题材内启动前锋排名 (Rank=1 为先锋龙)
    theme_role_tag: Optional[str] = None    # 题材角色标签 (如 "🚀 先锋龙 (Rank=1)", "🥀 冲高回落掉队")


class ResonanceEngine:
    """
    A股超短盘中【点面共振五态标签引擎】
    """

    def __init__(
        self,
        twin_pairs: Optional[Dict[str, List[str]]] = None,
        noise_themes: Optional[Set[str]] = None,
        base_theme_5m_threshold_pct: float = 0.30,
        base_stock_5m_threshold_pct: float = 2.00,
        market_dive_5m_pct: float = -0.25,
        market_dive_day_pct: float = -1.00,
    ):
        self.twin_pairs: Dict[str, List[str]] = twin_pairs or {}
        self.noise_themes: Set[str] = noise_themes if noise_themes is not None else DEFAULT_NOISE_THEMES
        self.base_theme_5m_thresh = base_theme_5m_threshold_pct
        self.base_stock_5m_thresh = base_stock_5m_threshold_pct
        self.market_dive_5m_pct = market_dive_5m_pct
        self.market_dive_day_pct = market_dive_day_pct

    # =========================================================================
    # 1. 分时段动态波动率因子与 Z-Score 判定
    # =========================================================================
    @staticmethod
    def get_intraday_volatility_multiplier(timestamp: str) -> float:
        clean_ts = timestamp.strip()[:5]  # 取 "HH:MM"
        if clean_ts <= "09:25":
            return 2.50
        elif clean_ts <= "09:40":
            return 2.00
        elif clean_ts <= "10:00":
            return 1.40
        elif clean_ts <= "10:30":
            return 1.15
        elif clean_ts <= "14:15":
            return 0.85
        else:
            return 1.20

    def _is_5m_surge_significant(
        self,
        ret_5m_pct: float,
        base_thresh_pct: float,
        timestamp: str,
        hist_mean: Optional[float] = None,
        hist_std: Optional[float] = None,
        z_threshold: float = 2.0,
    ) -> Tuple[bool, float]:
        mult = self.get_intraday_volatility_multiplier(timestamp)
        dynamic_thresh = base_thresh_pct * mult

        if hist_std is not None and hist_std > 1e-4:
            mean_val = hist_mean if hist_mean is not None else 0.0
            z_score = (ret_5m_pct - mean_val) / hist_std
            is_sig = (z_score >= z_threshold) and (ret_5m_pct >= base_thresh_pct * 0.7)
            return is_sig, round(z_score, 2)

        return (ret_5m_pct >= dynamic_thresh), round(dynamic_thresh, 2)

    # =========================================================================
    # 2. 脏概念过滤与当日最强主线板块锚定
    # =========================================================================
    def select_anchor_theme(
        self, target: StockTickSnapshot, theme_constituents_map: Dict[str, List[StockTickSnapshot]]
    ) -> Tuple[str, List[StockTickSnapshot], Dict[str, float]]:
        valid_themes = [t for t in target.themes if t not in self.noise_themes]
        if not valid_themes:
            valid_themes = target.themes if target.themes else ["未分类题材"]

        best_theme = valid_themes[0]
        best_score = -1e9
        best_peers: List[StockTickSnapshot] = []
        best_stats: Dict[str, float] = {}

        for theme in valid_themes:
            all_stocks = theme_constituents_map.get(theme, [])
            peers = [s for s in all_stocks if s.symbol != target.symbol]
            if not peers:
                score = 0.0
                stats_dict = {
                    "peer_count": 0,
                    "limit_up_peers": 0,
                    "strong_peers": 0,
                    "theme_5m_ret_pct": 0.0,
                    "theme_day_ret_pct": 0.0,
                }
            else:
                limit_ups = sum(1 for p in peers if p.is_limit_up)
                strong_peers = sum(1 for p in peers if p.day_ret_pct >= 5.0 or p.ret_5m_pct >= 2.0)
                max_boards = max((p.prev_boards for p in peers), default=0)
                mean_5m = float(np.mean([p.ret_5m_pct for p in peers]))
                mean_day = float(np.mean([p.day_ret_pct for p in peers]))

                score = limit_ups * 15.0 + max_boards * 8.0 + strong_peers * 4.0 + mean_5m * 10.0 + mean_day
                stats_dict = {
                    "peer_count": len(peers),
                    "limit_up_peers": limit_ups,
                    "strong_peers": strong_peers,
                    "theme_5m_ret_pct": round(mean_5m, 3),
                    "theme_day_ret_pct": round(mean_day, 3),
                }

            if score > best_score:
                best_score = score
                best_theme = theme
                best_peers = peers
                best_stats = stats_dict

        return best_theme, best_peers, best_stats

    # =========================================================================
    # 3. 核心五态判定主流程
    # =========================================================================
    @staticmethod
    def _time_to_seconds(ts: Optional[str]) -> int:
        if not ts:
            return 999999
        parts = [int(x) for x in ts.strip().split(":")]
        if len(parts) == 2:
            return parts[0] * 3600 + parts[1] * 60
        return parts[0] * 3600 + parts[1] * 60 + parts[2]

    def _find_twin_partners(
        self, target: StockTickSnapshot, universe_map: Dict[str, StockTickSnapshot]
    ) -> List[StockTickSnapshot]:
        partner_symbols = set(self.twin_pairs.get(target.symbol, []))
        clean_name = target.name.replace("*ST", "").replace("ST", "").strip()
        prefix = clean_name[:2] if len(clean_name) >= 3 else ""

        partners = []
        for sym, snap in universe_map.items():
            if sym == target.symbol:
                continue
            if sym in partner_symbols:
                partners.append(snap)
            elif prefix and snap.name.startswith(prefix) and (set(target.themes) & set(snap.themes)):
                partners.append(snap)
        return partners

    def evaluate(
        self,
        target: StockTickSnapshot,
        theme_constituents_map: Dict[str, List[StockTickSnapshot]],
        market: MarketSnapshot,
        extra_universe_map: Optional[Dict[str, StockTickSnapshot]] = None,
    ) -> ResonanceResult:
        universe_map: Dict[str, StockTickSnapshot] = dict(extra_universe_map or {})
        for stocks in theme_constituents_map.values():
            for s in stocks:
                universe_map[s.symbol] = s
        universe_map[target.symbol] = target

        # 1. 锚定当日核心主线题材
        anchor_theme, peers, theme_stats = self.select_anchor_theme(target, theme_constituents_map)

        # 1.1 计算同题材成分股启动前锋度排名与微观角色标签 (剔除早盘冲天炮跳水骗炮杂毛)
        all_theme_stocks = [target] + peers
        theme_items_for_rank = [
            {
                "symbol": s.symbol,
                "is_limit_up": s.is_limit_up,
                "first_seal_time": s.first_seal_time,
                "cross_5pct_time": getattr(s, "cross_5pct_time", None),
                "day_ret_pct": s.day_ret_pct,
            }
            for s in all_theme_stocks
        ]
        speed_ranks = compute_theme_speed_ranks(theme_items_for_rank)
        target_rank, target_role_tag = speed_ranks.get(target.symbol, (999, "➖ 板块未动/跟跌"))

        # 2. 计算个股与板块分时涨速是否显著
        stock_5m_sig, stock_thresh_info = self._is_5m_surge_significant(
            target.ret_5m_pct,
            self.base_stock_5m_thresh,
            target.timestamp,
            target.hist_5m_mean_pct,
            target.hist_5m_std_pct,
        )
        # 板块指数 5m 涨速应当由同板块其他成分股(peers)决定，避免个股单骑暴拉时被自身分时拉高误判为“板块合力”
        sector_5m_ret = theme_stats.get("theme_5m_ret_pct", 0.0)
        theme_5m_sig, theme_thresh_info = self._is_5m_surge_significant(
            sector_5m_ret, self.base_theme_5m_thresh, target.timestamp
        )

        is_stock_attacking = (
            target.is_limit_up
            or (stock_5m_sig and target.vol_ratio >= 1.2)
            or (target.day_ret_pct >= 6.0 and target.vol_ratio >= 1.5)
        )

        is_market_diving = (
            market.ret_5m_pct <= self.market_dive_5m_pct
            or market.day_ret_pct <= self.market_dive_day_pct
        )

        triggered_tags: List[ResonanceTag] = []
        evidence: Dict[str, object] = {
            "anchor_theme": anchor_theme,
            "sector_5m_ret_pct": round(sector_5m_ret, 3),
            "dynamic_theme_5m_thresh": theme_thresh_info,
            "dynamic_stock_5m_thresh": stock_thresh_info,
            "market_5m_ret_pct": market.ret_5m_pct,
            "market_day_ret_pct": market.day_ret_pct,
            "theme_speed_rank": target_rank,
            "theme_role_tag": target_role_tag,
        }

        # ---------------------------------------------------------------------
        # 状态 A：👑 卡位夺权 (K-Position Usurping)
        # ---------------------------------------------------------------------
        higher_or_equal_dragons = [
            p for p in peers if p.prev_boards >= max(1, target.prev_boards)
        ]
        usurped_dragons = []
        for dragon in higher_or_equal_dragons:
            auction_usurp = (
                (target.open_ret_pct - dragon.open_ret_pct >= 3.0)
                and (target.auction_vol_ratio >= 2.5)
                and (target.day_ret_pct >= dragon.day_ret_pct + 2.0)
            )
            seal_usurp = False
            if target.is_limit_up:
                if (not dragon.is_limit_up) and (target.day_ret_pct - dragon.day_ret_pct >= 3.0):
                    seal_usurp = True
                elif (
                    dragon.is_limit_up
                    and dragon.prev_boards > target.prev_boards
                    and (self._time_to_seconds(dragon.first_seal_time) - self._time_to_seconds(target.first_seal_time) >= 180)
                ):
                    seal_usurp = True

            if auction_usurp or seal_usurp:
                usurped_dragons.append(f"{dragon.name}({dragon.prev_boards}板,现{dragon.day_ret_pct:+.1f}%)")

        if usurped_dragons:
            triggered_tags.append(ResonanceTag.K_POSITION_USURPING)
            evidence["usurped_targets"] = usurped_dragons

        # ---------------------------------------------------------------------
        # 状态 B：🔄 双子星掩护 (Twin-Core Relay)
        # ---------------------------------------------------------------------
        twin_partners = self._find_twin_partners(target, universe_map)
        twin_events = []
        for partner in twin_partners:
            is_relay_cover = (
                (-9.5 < partner.day_ret_pct <= -2.0)
                and (target.is_limit_up or target.day_ret_pct >= 7.0)
            )
            is_self_cover = (
                (-9.5 < target.day_ret_pct <= -2.0)
                and (partner.is_limit_up or partner.day_ret_pct >= 7.0)
            )
            if is_relay_cover or is_self_cover:
                role = "主攻接棒" if is_relay_cover else "水下掩护"
                twin_events.append(f"{role}:搭档[{partner.name}]({partner.day_ret_pct:+.1f}%)")

        if twin_events:
            triggered_tags.append(ResonanceTag.TWIN_CORE_RELAY)
            evidence["twin_core_detail"] = twin_events

        # ---------------------------------------------------------------------
        # 状态 C：⚡ 逆势 (Counter-Trend)
        # ---------------------------------------------------------------------
        is_fanbao = (target.prev_day_ret_pct <= -3.0) and (target.day_ret_pct >= 5.0)
        alpha_5m = target.ret_5m_pct - market.ret_5m_pct
        if is_market_diving and (
            target.is_limit_up or is_fanbao or (is_stock_attacking and alpha_5m >= 1.8)
        ):
            triggered_tags.append(ResonanceTag.COUNTER_TREND)
            evidence["counter_trend_alpha_5m_pct"] = round(alpha_5m, 2)
            evidence["is_fanbao"] = is_fanbao

        # ---------------------------------------------------------------------
        # 状态 D：🔥 共振 (Resonance)
        # ---------------------------------------------------------------------
        has_peer_support = (
            theme_stats.get("limit_up_peers", 0) >= 1
            or theme_stats.get("strong_peers", 0) >= 1
            or theme_5m_sig
        )
        if is_stock_attacking and has_peer_support and (not is_market_diving):
            triggered_tags.append(ResonanceTag.RESONANCE)
            evidence["resonance_support"] = {
                "limit_up_peers": theme_stats.get("limit_up_peers", 0),
                "strong_peers": theme_stats.get("strong_peers", 0),
                "theme_5m_sig": theme_5m_sig,
            }

        # ---------------------------------------------------------------------
        # 状态 E：⚠️ 孤立 (Isolated)
        # ---------------------------------------------------------------------
        is_solo_pulse = stock_5m_sig or (target.day_ret_pct >= 4.0)
        if is_solo_pulse and len(peers) > 0:
            all_peers_flat = all(abs(p.day_ret_pct) <= 0.5 for p in peers)
            all_peers_low_vol = all(p.vol_ratio < 1.2 for p in peers)
            if all_peers_flat and all_peers_low_vol:
                triggered_tags.append(ResonanceTag.ISOLATED)
                evidence["isolated_peers_max_abs_ret"] = round(
                    max(abs(p.day_ret_pct) for p in peers), 2
                )

        if not triggered_tags:
            triggered_tags.append(ResonanceTag.NEUTRAL)

        tag_labels = [t.value for t in triggered_tags]
        if target_role_tag and not target_role_tag.startswith("➖"):
            tag_labels.append(target_role_tag)

        return ResonanceResult(
            symbol=target.symbol,
            name=target.name,
            anchor_theme=anchor_theme,
            primary_tag=triggered_tags[0],
            all_tags=triggered_tags,
            tag_labels=tag_labels,
            evidence=evidence,
            theme_speed_rank=target_rank,
            theme_role_tag=target_role_tag,
        )


# =============================================================================
# 内置单元测试：验证模块 3 五态触发、脏概念过滤与动态阈值
# =============================================================================
class TestResonanceEngine(unittest.TestCase):

    def setUp(self):
        self.engine = ResonanceEngine(
            twin_pairs={
                "600726.SH": ["600396.SH"],
                "600396.SH": ["600726.SH"],
            }
        )

    def test_state1_resonance_and_noise_theme_filtering(self):
        target = StockTickSnapshot(
            symbol="000099.SZ", name="中信海直", timestamp="10:35:00",
            day_ret_pct=7.5, ret_5m_pct=2.8, open_ret_pct=2.0, vol_ratio=2.4,
            themes=["融资融券", "深股通", "央企国企改革", "低空经济"],
        )
        theme_map = {
            "融资融券": [
                StockTickSnapshot("601398.SH", "工商银行", "10:35:00", 0.1, 0.0, 0.0, 0.8, themes=["融资融券"])
            ],
            "低空经济": [
                target,
                StockTickSnapshot("300411.SZ", "金盾股份", "10:35:00", 20.0, 1.5, 5.0, 3.1, is_limit_up=True, themes=["低空经济"]),
                StockTickSnapshot("002085.SZ", "万丰奥威", "10:35:00", 6.2, 1.8, 1.5, 2.0, themes=["低空经济"]),
            ],
        }
        market = MarketSnapshot(timestamp="10:35:00", day_ret_pct=0.45, ret_5m_pct=0.12)

        res = self.engine.evaluate(target, theme_map, market)
        self.assertEqual(res.anchor_theme, "低空经济")
        self.assertIn(ResonanceTag.RESONANCE, res.all_tags)
        self.assertEqual(res.primary_tag, ResonanceTag.RESONANCE)

    def test_state2_isolated_pulse(self):
        target = StockTickSnapshot(
            symbol="600100.SH", name="同方股份", timestamp="13:45:00",
            day_ret_pct=4.8, ret_5m_pct=3.5, open_ret_pct=0.2, vol_ratio=1.9,
            themes=["量子科技"],
        )
        theme_map = {
            "量子科技": [
                target,
                StockTickSnapshot("002222.SZ", "福晶科技", "13:45:00", 0.15, 0.05, 0.0, 0.7, themes=["量子科技"]),
                StockTickSnapshot("300555.SZ", "路通视信", "13:45:00", -0.30, -0.10, -0.2, 0.8, themes=["量子科技"]),
            ]
        }
        market = MarketSnapshot(timestamp="13:45:00", day_ret_pct=0.10, ret_5m_pct=0.02)

        res = self.engine.evaluate(target, theme_map, market)
        self.assertIn(ResonanceTag.ISOLATED, res.all_tags)
        self.assertEqual(res.primary_tag, ResonanceTag.ISOLATED)

    def test_state3_counter_trend(self):
        target = StockTickSnapshot(
            symbol="002400.SZ", name="省广集团", timestamp="14:10:00",
            day_ret_pct=10.0, ret_5m_pct=4.2, open_ret_pct=-1.5, vol_ratio=3.2,
            is_limit_up=True, prev_day_ret_pct=-5.5, themes=["AI营销"],
        )
        theme_map = {"AI营销": [target]}
        market = MarketSnapshot(timestamp="14:10:00", day_ret_pct=-1.25, ret_5m_pct=-0.35)

        res = self.engine.evaluate(target, theme_map, market)
        self.assertIn(ResonanceTag.COUNTER_TREND, res.all_tags)
        self.assertTrue(res.evidence["is_fanbao"])

    def test_state4_twin_core_relay(self):
        huadian_nengyuan = StockTickSnapshot(
            symbol="600726.SH", name="华电能源", timestamp="10:15:00",
            day_ret_pct=10.0, ret_5m_pct=2.5, open_ret_pct=4.5, vol_ratio=2.8,
            is_limit_up=True, prev_boards=2, themes=["电力"],
        )
        huadian_liaoneng = StockTickSnapshot(
            symbol="600396.SH", name="华电辽能", timestamp="10:15:00",
            day_ret_pct=-4.2, ret_5m_pct=-0.5, open_ret_pct=-2.0, vol_ratio=2.1,
            is_limit_up=False, prev_boards=3, themes=["电力"],
        )
        theme_map = {"电力": [huadian_nengyuan, huadian_liaoneng]}
        market = MarketSnapshot(timestamp="10:15:00", day_ret_pct=0.2, ret_5m_pct=0.05)

        res = self.engine.evaluate(huadian_nengyuan, theme_map, market)
        self.assertIn(ResonanceTag.TWIN_CORE_RELAY, res.all_tags)

    def test_state5_k_position_usurping(self):
        new_leader = StockTickSnapshot(
            symbol="002500.SZ", name="山西证券", timestamp="09:32:00",
            day_ret_pct=10.0, ret_5m_pct=2.5, open_ret_pct=7.5, vol_ratio=4.5,
            auction_vol_ratio=4.2, is_limit_up=True, first_seal_time="09:31:05",
            prev_boards=2, themes=["多元金融"],
        )
        old_dragon = StockTickSnapshot(
            symbol="600800.SH", name="渤海租赁", timestamp="09:32:00",
            day_ret_pct=-1.5, ret_5m_pct=-2.7, open_ret_pct=1.2, vol_ratio=3.0,
            auction_vol_ratio=1.5, is_limit_up=False, first_seal_time=None,
            prev_boards=3, themes=["多元金融"],
        )
        theme_map = {"多元金融": [new_leader, old_dragon]}
        market = MarketSnapshot(timestamp="09:32:00", day_ret_pct=0.3, ret_5m_pct=0.1)

        res = self.engine.evaluate(new_leader, theme_map, market)
        self.assertIn(ResonanceTag.K_POSITION_USURPING, res.all_tags)
        self.assertEqual(res.primary_tag, ResonanceTag.K_POSITION_USURPING)

    def test_state6_theme_speed_rank_pioneer_and_spike_dump_exclusion(self):
        """
        回归测试：早盘 09:31 冲天炮冲 +5% 后跳水至 -2.5% 的骗炮股绝不能当选 Rank=1 先锋龙；
        09:35 破 +5% 且当前稳守 +8.8% 的真主攻股荣获 Rank=1 先锋龙。
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

        # 评估真实先锋龙
        res_pioneer = self.engine.evaluate(real_pioneer, theme_map, market)
        self.assertEqual(res_pioneer.theme_speed_rank, 1)
        self.assertIn("🚀 先锋龙", res_pioneer.theme_role_tag)
        self.assertTrue(any("🚀 先锋龙" in label for label in res_pioneer.tag_labels))

        # 评估冲高跳水杂毛
        res_dump = self.engine.evaluate(spike_and_dump, theme_map, market)
        self.assertNotEqual(res_dump.theme_speed_rank, 1)
        self.assertIn("🥀 冲高回落掉队", res_dump.theme_role_tag)
        self.assertTrue(any("🥀 冲高回落掉队" in label for label in res_dump.tag_labels))


if __name__ == "__main__":
    unittest.main(verbosity=2)
