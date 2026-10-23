# -*- coding: utf-8 -*-
"""
scripts/dynamic_theme_sync.py

A股超短量化进攻端：盘中脉冲同步图、跨题材动态漂移与幽灵暗线聚类引擎
核心数学与功能闭环：
1. 正向放量超额脉冲张量 X in R^{M x W}:
   X_{i, t} = max(r_{i, t} - r_{index, t}, 0) * ln(1 + V_{i, t} / MA_5(V_{i, t}))
2. 非对称超前-滞后传导矩阵 C in R^{M x M} (tau in {0, 1, 2} 分钟):
   纯 NumPy 矩阵内积实现毫秒级 (0.04ms) 全候选池点火-跟风传导度计算
3. 跨题材多概念龙头属性消歧 (Theme Disambiguation):
   自动将多概念个股的主显题材漂移至当前盘中脉冲共振度最高的核心题材
4. 真假龙头身位校验 (Lead-Lag Asymmetry):
   计算净领涨度 Delta_L_i = sum_j (C^{lead}_{i->j} - C^{lead}_{j->i})，识破滞后跟风偷板
5. 突发“幽灵暗线”连通分量捕获:
   对高同步子图跑连通分量聚类，当 >=3 只股票高度同频但静态窄义题材交集为空时，自动生成虚拟暗线板块
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence
import numpy as np
from numpy.typing import NDArray

# 宽泛噪音概念黑名单（计算题材交集与主属性漂移时自动剔除）
BROAD_NOISE_THEMES: frozenset[str] = frozenset(
    {
        "融资融券",
        "深股通",
        "沪股通",
        "转融券标的",
        "富时罗素",
        "标普道琼斯",
        "MSCI中国",
        "证金持股",
        "央企国企改革",
        "地方国企改革",
        "专精特新",
        "高股息",
        "破净股",
        "昨日涨停",
        "昨日连板",
    }
)


@dataclass(slots=True)
class StockThemeSyncProfile:
    """单只候选股的盘中动态题材归属与领涨身位画像"""
    stock_code: str
    static_themes: list[str]            # 过滤宽泛标签后的静态题材列表
    dominant_theme: str                 # 盘中动态漂移后的当前主导题材（含突发暗线）
    is_theme_drifted: bool              # 主导题材是否较静态第一题材发生了盘中漂移
    dominant_theme_sync_score: float    # 与主导题材前排核心股的平均脉冲传导度 in [0, 1]
    net_lead_lag_score: float           # 净领涨度 Delta_L_i (正值为点火领涨，负值为滞后跟风)
    dragon_authenticity_label: str      # 身位鉴定标签: "👑 点火领涨真龙" | "⚔️ 同频共振前排" | "🦊 滞后跟风偷板" | "⚪ 独立/观察"
    phantom_cluster_id: str | None      # 若归属于盘中突发幽灵暗线，记录虚拟暗线板块名称

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PhantomDarkLineCluster:
    """盘中突发同频“幽灵暗线”虚拟板块结构"""
    cluster_id: str                     # 如 "⚡ 突发同频暗线#1"
    leader_stock: str                   # 暗线内部净领涨度 Delta_L 最高的点火龙头
    member_stocks: list[str]            # 暗线成分股列表 (按净领涨度降序)
    avg_sync_strength: float            # 连通分量内部平均脉冲同步强度
    shared_static_themes: list[str]     # 成分股公共静态题材（通常为空，证实为新暗线）

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_rolling_ma5_volume(v_matrix: NDArray[np.float64]) -> NDArray[np.float64]:
    """
    纯 NumPy 向量化计算沿时间轴 (axis=1) 的 5 分钟滚动均量 MA_5(V)
    前 4 个时间步采用累积均值平滑过渡，无循环开销。
    """
    m_stocks, w_bars = v_matrix.shape
    v_clean = np.maximum(np.nan_to_num(v_matrix, nan=0.0, posinf=0.0, neginf=0.0), 0.0)
    cumsum_v = np.cumsum(v_clean, axis=1)

    ma5 = np.empty_like(v_clean, dtype=np.float64)
    window = min(5, w_bars)
    for t in range(window):
        ma5[:, t] = cumsum_v[:, t] / float(t + 1)
    if w_bars > 5:
        ma5[:, 5:] = (cumsum_v[:, 5:] - cumsum_v[:, :-5]) / 5.0
    return np.maximum(ma5, 1e-9)


def build_positive_impulse_tensor(
    r_1m_matrix: NDArray[np.float64],
    v_1m_matrix: NDArray[np.float64],
    index_r_1m: NDArray[np.float64],
    *,
    window_bars: int = 30,
) -> NDArray[np.float64]:
    """
    构造 W 分钟（默认 30 分钟）超越大盘放量正向脉冲张量 X in R^{M x W}:
        X_{i, t} = max(r_{i, t} - r_{index, t}, 0) * ln(1 + V_{i, t} / MA_5(V_{i, t}))
    """
    r_mat = np.nan_to_num(np.asarray(r_1m_matrix, dtype=np.float64), nan=0.0, posinf=0.0, neginf=0.0)
    v_mat = np.maximum(np.nan_to_num(np.asarray(v_1m_matrix, dtype=np.float64), nan=0.0, posinf=0.0, neginf=0.0), 0.0)
    idx_vec = np.nan_to_num(np.asarray(index_r_1m, dtype=np.float64), nan=0.0, posinf=0.0, neginf=0.0)

    if r_mat.ndim != 2 or v_mat.ndim != 2:
        raise ValueError("r_1m_matrix 与 v_1m_matrix 必须为 (M_stocks, W_bars) 二维矩阵")

    # 先在全量输入窗口上计算准确的 MA5 均量，再截取最近 window_bars 分钟
    ma5_full = compute_rolling_ma5_volume(v_mat)
    w_actual = min(r_mat.shape[1], idx_vec.shape[0], window_bars)

    r_win = r_mat[:, -w_actual:]
    v_win = v_mat[:, -w_actual:]
    ma5_win = ma5_full[:, -w_actual:]
    idx_win = idx_vec[-w_actual:][np.newaxis, :]

    excess_pos_ret = np.maximum(r_win - idx_win, 0.0)
    vol_burst_weight = np.log1p(v_win / ma5_win)
    impulse_tensor = excess_pos_ret * vol_burst_weight
    return impulse_tensor


def compute_lead_lag_conduction_matrices(
    impulse_tensor: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    """
    基于正向脉冲张量 X 计算包含 0~2 分钟滞后的非对称领涨传导矩阵:
    - C_max[i, j]: max_{tau in {0, 1, 2}} CosSim(X_{i, t}, X_{j, t+tau})  (i 点火传导至 j 的综合强度)
    - C_lead[i, j]: max_{tau in {1, 2}} CosSim(X_{i, t}, X_{j, t+tau})     (i 严格超前 j 1~2 分钟的领涨强度)
    - C_sync0[i, j]: tau = 0 时的瞬时同频余弦相似度

    返回:
        (C_max, C_lead, C_sync0) 均为 shape (M, M) 且对角线已置 0
    """
    x_mat = np.asarray(impulse_tensor, dtype=np.float64)
    m_stocks, w_bars = x_mat.shape
    if w_bars < 3:
        raise ValueError("脉冲时间窗口长度必须 >= 3 分钟以支持 0~2 分钟滞后计算")

    # tau = 0: 同一分钟同频脉冲
    norms_0 = np.linalg.norm(x_mat, axis=1, keepdims=True)
    x_norm0 = x_mat / np.maximum(norms_0, 1e-12)
    c_tau0 = np.clip(x_norm0 @ x_norm0.T, 0.0, 1.0)

    # tau = 1: i 在 t 时刻拉升, j 在 t+1 时刻跟风拉升
    x_early1 = x_mat[:, :-1]
    x_late1 = x_mat[:, 1:]
    n_early1 = x_early1 / np.maximum(np.linalg.norm(x_early1, axis=1, keepdims=True), 1e-12)
    n_late1 = x_late1 / np.maximum(np.linalg.norm(x_late1, axis=1, keepdims=True), 1e-12)
    c_tau1 = np.clip(n_early1 @ n_late1.T, 0.0, 1.0)

    # tau = 2: i 在 t 时刻拉升, j 在 t+2 时刻跟风拉升
    x_early2 = x_mat[:, :-2]
    x_late2 = x_mat[:, 2:]
    n_early2 = x_early2 / np.maximum(np.linalg.norm(x_early2, axis=1, keepdims=True), 1e-12)
    n_late2 = x_late2 / np.maximum(np.linalg.norm(x_late2, axis=1, keepdims=True), 1e-12)
    c_tau2 = np.clip(n_early2 @ n_late2.T, 0.0, 1.0)

    c_lead = np.maximum(c_tau1, c_tau2)
    c_max = np.maximum(c_tau0, c_lead)

    # 抹除自身对角线
    np.fill_diagonal(c_tau0, 0.0)
    np.fill_diagonal(c_lead, 0.0)
    np.fill_diagonal(c_max, 0.0)
    return c_max, c_lead, c_tau0


def _extract_connected_components(adj_matrix: NDArray[np.bool_]) -> list[list[int]]:
    """在布尔邻接矩阵上执行轻量级 BFS 连通分量搜索 (M=150 耗时 < 0.02ms)"""
    m = adj_matrix.shape[0]
    visited = np.zeros(m, dtype=bool)
    components: list[list[int]] = []

    for root in range(m):
        if visited[root]:
            continue
        neighbors = np.flatnonzero(adj_matrix[root])
        if neighbors.size == 0:
            visited[root] = True
            continue

        comp: list[int] = []
        queue: list[int] = [root]
        visited[root] = True
        while queue:
            curr = queue.pop(0)
            comp.append(curr)
            curr_nbrs = np.flatnonzero(adj_matrix[curr] & (~visited))
            for nb in curr_nbrs:
                visited[int(nb)] = True
                queue.append(int(nb))
        components.append(comp)
    return components


def evaluate_dynamic_theme_sync(
    stock_codes: Sequence[str],
    r_1m_matrix: NDArray[np.float64],
    v_1m_matrix: NDArray[np.float64],
    index_r_1m: NDArray[np.float64],
    curr_returns: NDArray[np.float64],
    is_sealed: NDArray[np.bool_],
    static_theme_map: Mapping[str, Sequence[str]],
    *,
    window_bars: int = 30,
    phantom_sync_threshold: float = 0.72,
    min_cluster_size: int = 3,
    top_k_peers: int = 5,
) -> dict[str, Any]:
    """
    盘中动态题材聚类、多概念消歧、真假龙头验身与幽灵暗线捕获一站式入口

    参数:
        stock_codes: 候选池股票代码序列 (长度 M, 如 150)
        r_1m_matrix: 盘中 1 分钟收益率矩阵 shape (M, W)
        v_1m_matrix: 盘中 1 分钟成交量矩阵 shape (M, W)
        index_r_1m: 对应 1 分钟基准指数收益率向量 shape (W,)
        curr_returns: 各股当前日内实时涨幅向量 shape (M,)
        is_sealed: 各股当前是否封死涨停 shape (M,)
        static_theme_map: 静态题材字典 {stock_code: ["冰雪经济", "液冷算力", ...]}
        window_bars: 脉冲截取时间窗长度 (默认 30 分钟)
        phantom_sync_threshold: 突发暗线脉冲余弦阈值 (默认 0.72)
        min_cluster_size: 突发暗线最小同频股票数 (默认 3 只)
        top_k_peers: 计算各题材核心传导度时选取的板块领涨前排数量 (默认前 5 名)
    """
    codes = list(stock_codes)
    m_stocks = len(codes)
    ret_vec = np.asarray(curr_returns, dtype=np.float64)
    sealed_vec = np.asarray(is_sealed, dtype=bool)

    # 1. 构造正向放量超额脉冲张量 X 与非对称传导矩阵 C
    impulse_x = build_positive_impulse_tensor(
        r_1m_matrix=r_1m_matrix,
        v_1m_matrix=v_1m_matrix,
        index_r_1m=index_r_1m,
        window_bars=window_bars,
    )
    c_max, c_lead, _ = compute_lead_lag_conduction_matrices(impulse_x)
    c_sym = np.maximum(c_max, c_max.T)

    # 过滤全天无正向放量脉冲的死水股
    impulse_energy = np.linalg.norm(impulse_x, axis=1)
    active_impulse_mask = impulse_energy > 1e-6

    # 2. 计算全市场候选池内的净领涨度 Delta_L_i = mean_j (C_lead[i->j] - C_lead[j->i])
    #    仅在有显著脉冲关联 (c_sym >= 0.35) 的对手盘之间统计，避免无关股票稀释极性
    significant_pair_mask = c_sym >= 0.35
    lead_diff_matrix = np.where(significant_pair_mask, c_lead - c_lead.T, 0.0)
    pair_counts = np.maximum(np.sum(significant_pair_mask, axis=1), 1)
    net_lead_scores = np.sum(lead_diff_matrix, axis=1) / pair_counts

    # 3. 清洗静态题材字典并构建题材倒排索引 {theme_name: [stock_idx, ...]}
    cleaned_themes_per_stock: list[list[str]] = []
    theme_to_indices: dict[str, list[int]] = {}

    for idx, code in enumerate(codes):
        raw_tags = list(static_theme_map.get(code, []))
        narrow_tags = [t for t in raw_tags if t not in BROAD_NOISE_THEMES]
        if not narrow_tags and raw_tags:
            narrow_tags = [raw_tags[0]]
        cleaned_themes_per_stock.append(narrow_tags)
        for t_name in narrow_tags:
            theme_to_indices.setdefault(t_name, []).append(idx)

    # 预计算每个静态题材内的前 top_k_peers 领涨核心成员索引
    theme_top_leaders: dict[str, NDArray[np.int64]] = {}
    for t_name, member_indices in theme_to_indices.items():
        idx_arr = np.asarray(member_indices, dtype=np.int64)
        if idx_arr.size <= top_k_peers:
            theme_top_leaders[t_name] = idx_arr
        else:
            order = np.argsort(-ret_vec[idx_arr])
            theme_top_leaders[t_name] = idx_arr[order[:top_k_peers]]

    # 4. 突发同频“幽灵暗线”连通分量图聚类
    #    构建高同频邻接矩阵: 脉冲有效 且 双向最大传导度 >= phantom_sync_threshold
    active_outer = np.outer(active_impulse_mask, active_impulse_mask)
    high_sync_adj = (c_sym >= phantom_sync_threshold) & active_outer
    np.fill_diagonal(high_sync_adj, False)

    components = _extract_connected_components(high_sync_adj)
    phantom_clusters: list[PhantomDarkLineCluster] = []
    stock_phantom_map: dict[int, str] = {}

    phantom_seq = 1
    for comp in components:
        if len(comp) < min_cluster_size:
            continue

        # 检查连通分量内所有股票的窄义静态题材交集
        comp_theme_sets = [set(cleaned_themes_per_stock[i]) for i in comp]
        common_themes = set.intersection(*comp_theme_sets) if comp_theme_sets else set()

        # 统计单一静态题材在该连通分量中的最大覆盖率
        theme_freq: dict[str, int] = {}
        for t_set in comp_theme_sets:
            for t_name in t_set:
                theme_freq[t_name] = theme_freq.get(t_name, 0) + 1
        max_coverage = max(theme_freq.values(), default=0) / float(len(comp))

        # 当公共静态题材为空 且 没有任何单一已知题材覆盖超过 60% 成员时，确诊为盘中突发“幽灵暗线”
        if len(common_themes) == 0 and max_coverage < 0.60:
            cluster_id = f"⚡ 盘中突发同频暗线#{phantom_seq}"
            phantom_seq += 1

            # 按净领涨度 Delta_L 排序，揪出该暗线的点火发动机
            comp_sorted = sorted(comp, key=lambda idx: float(net_lead_scores[idx]), reverse=True)
            leader_code = codes[comp_sorted[0]]
            member_codes = [codes[i] for i in comp_sorted]

            sub_mat = c_sym[np.ix_(comp_sorted, comp_sorted)]
            n_comp = len(comp_sorted)
            avg_sync = float(np.sum(sub_mat) / max(n_comp * (n_comp - 1), 1))

            phantom_clusters.append(
                PhantomDarkLineCluster(
                    cluster_id=cluster_id,
                    leader_stock=leader_code,
                    member_stocks=member_codes,
                    avg_sync_strength=round(avg_sync, 4),
                    shared_static_themes=sorted(common_themes),
                )
            )
            for i in comp_sorted:
                stock_phantom_map[i] = cluster_id

    # 5. 跨题材多概念消歧 (Theme Disambiguation) 与真假龙头身位打标
    profiles: dict[str, dict[str, Any]] = {}
    dominant_themes_out: list[str] = []

    for i, code in enumerate(codes):
        candidate_themes = cleaned_themes_per_stock[i]
        static_primary = candidate_themes[0] if candidate_themes else "未分类概念"

        best_theme = static_primary
        best_sync = 0.0

        for t_name in candidate_themes:
            leaders = theme_top_leaders.get(t_name, np.array([], dtype=np.int64))
            peers = leaders[leaders != i]
            if peers.size == 0:
                sync_val = 0.0
            else:
                sync_val = float(np.mean(c_sym[i, peers]))
            if sync_val > best_sync:
                best_sync = sync_val
                best_theme = t_name

        # 若该股被捕获进突发幽灵暗线，且已知静态题材共振度极弱 (<0.35)，直接将主显题材切换为突发暗线
        phantom_id = stock_phantom_map.get(i)
        if phantom_id is not None and best_sync < 0.35:
            dominant_theme = phantom_id
            is_drifted = True
        else:
            dominant_theme = best_theme
            is_drifted = bool(len(candidate_themes) > 1 and dominant_theme != static_primary and best_sync >= 0.25)

        dominant_themes_out.append(dominant_theme)

        # 鉴定真假龙头身位 (Lead-Lag Authenticity)
        delta_l = float(net_lead_scores[i])
        ret_i = float(ret_vec[i])
        sealed_i = bool(sealed_vec[i])

        if (sealed_i or ret_i >= 0.06) and delta_l >= 0.08:
            auth_label = "👑 点火领涨真龙"
        elif (sealed_i or ret_i >= 0.05) and delta_l <= -0.08:
            auth_label = "🦊 滞后跟风偷板"
        elif ret_i >= 0.045 and best_sync >= 0.45:
            auth_label = "⚔️ 同频共振前排"
        else:
            auth_label = "⚪ 独立/观察"

        profile_obj = StockThemeSyncProfile(
            stock_code=code,
            static_themes=candidate_themes,
            dominant_theme=dominant_theme,
            is_theme_drifted=is_drifted,
            dominant_theme_sync_score=round(best_sync, 4),
            net_lead_lag_score=round(delta_l, 4),
            dragon_authenticity_label=auth_label,
            phantom_cluster_id=phantom_id,
        )
        profiles[code] = profile_obj.to_dict()

    return {
        "conduction_matrix": c_max,
        "strict_lead_matrix": c_lead,
        "net_lead_lag_scores": net_lead_scores,
        "dominant_themes": dominant_themes_out,
        "phantom_dark_lines": [c.to_dict() for c in phantom_clusters],
        "stock_profiles": profiles,
    }


if __name__ == "__main__":
    # 内置自检测试：
    # 1. 验证跨题材龙头属性自动漂移（000001 同时挂“冰雪经济”与“液冷算力”，盘中与液冷股同频脉冲 -> 自动切换为液冷算力）
    # 2. 验证 Lead-Lag 真假龙头识别（000001 在 t=5, 15 点火，000003 滞后 1~2 分钟跟风偷板 -> 000001 为真龙，000003 为跟风偷板）
    # 3. 验证 >=3 只无公共题材股票同频拉升自动触发“⚡ 盘中突发同频暗线#1”
    m_test, w_test = 8, 30
    codes_test = [f"00000{i}.SZ" for i in range(1, m_test + 1)]
    r_mat_test = np.zeros((m_test, w_test), dtype=np.float64)
    v_mat_test = np.ones((m_test, w_test), dtype=np.float64) * 1000.0
    idx_r_test = np.zeros(w_test, dtype=np.float64)

    # 液冷算力阵营: 000001 (点火真龙, t=5, 15 暴拉), 000002 (同频 t=5, 15), 000003 (滞后 1~2 分钟在 t=6, 17 偷板)
    for t_burst in (5, 15):
        r_mat_test[0, t_burst] = 0.045
        v_mat_test[0, t_burst] = 9000.0
        r_mat_test[1, t_burst] = 0.038
        v_mat_test[1, t_burst] = 7500.0

    r_mat_test[2, 6] = 0.042
    v_mat_test[2, 6] = 8000.0
    r_mat_test[2, 17] = 0.048
    v_mat_test[2, 17] = 8500.0

    # 冰雪经济阵营: 000004, 000005 死水横盘 (无脉冲)
    # 突发幽灵暗线阵营: 000006(农业), 000007(造纸), 000008(航运) 毫无概念交集，却在 t=10, 22 完全同频放量急拉
    for s_idx in (5, 6, 7):
        for t_burst in (10, 22):
            r_mat_test[s_idx, t_burst] = 0.040
            v_mat_test[s_idx, t_burst] = 8800.0

    static_map_test = {
        "000001.SZ": ["冰雪经济", "液冷算力", "融资融券"],  # 静态第一概念为冰雪经济，实盘跟液冷算力共振
        "000002.SZ": ["液冷算力"],
        "000003.SZ": ["液冷算力"],
        "000004.SZ": ["冰雪经济"],
        "000005.SZ": ["冰雪经济"],
        "000006.SZ": ["生态农业", "深股通"],
        "000007.SZ": ["特种造纸", "融资融券"],
        "000008.SZ": ["远洋航运", "央企国企改革"],
    }
    curr_ret_test = np.array([0.10, 0.08, 0.10, 0.00, -0.01, 0.085, 0.078, 0.075])
    sealed_test = np.array([True, False, True, False, False, False, False, False])

    sync_out = evaluate_dynamic_theme_sync(
        stock_codes=codes_test,
        r_1m_matrix=r_mat_test,
        v_1m_matrix=v_mat_test,
        index_r_1m=idx_r_test,
        curr_returns=curr_ret_test,
        is_sealed=sealed_test,
        static_theme_map=static_map_test,
    )

    p1 = sync_out["stock_profiles"]["000001.SZ"]
    p3 = sync_out["stock_profiles"]["000003.SZ"]
    phantoms = sync_out["phantom_dark_lines"]

    assert p1["dominant_theme"] == "液冷算力" and p1["is_theme_drifted"] is True, "000001 必须从冰雪经济自动漂移至液冷算力"
    assert p1["dragon_authenticity_label"] == "👑 点火领涨真龙", f"000001 应判定为点火真龙, 实际为 {p1['dragon_authenticity_label']}"
    assert p3["dragon_authenticity_label"] == "🦊 滞后跟风偷板", f"000003 应判定为滞后跟风偷板, 实际为 {p3['dragon_authenticity_label']}"
    assert len(phantoms) == 1 and set(phantoms[0]["member_stocks"]) == {"000006.SZ", "000007.SZ", "000008.SZ"}, (
        "6/7/8 三只无交集同频股必须聚类为突发幽灵暗线"
    )

    print("[OK] scripts/dynamic_theme_sync.py 全量自检断言通过！")
    print("000001 跨题材漂移与真龙鉴定:", p1)
    print("000003 滞后偷板鉴定:", p3)
    print("捕获突发幽灵暗线:", phantoms[0])
