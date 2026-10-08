# -*- coding: utf-8 -*-
"""scripts/threshold_evidence.py — 阈值实证检验与分位数核查工具

本脚本以项目权威存档（sentiment_history.jsonl + 真实日K）为唯一事实源，
输出客观分位数、真实次日表现对照，坚决杜绝“修辞通胀”与“假实证”。
"""
import os
import sys
import json
import pathlib
import datetime as dt

_HERE = pathlib.Path(__file__).resolve().parent
ROOT = _HERE.parent
sys.path.insert(0, str(_HERE))

import stock_dashboard as sd

SENT_PATH = pathlib.Path(sd.DATA_DIR) / 'sentiment_history.jsonl'


def percentile(data, p):
    """纯 Python 计算分位数（p 为 0~100）"""
    if not data:
        return 0.0
    sorted_d = sorted(data)
    k = (len(sorted_d) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_d) - 1)
    d = k - f
    return sorted_d[f] + d * (sorted_d[c] - sorted_d[f])


def run_evidence_audit():
    if not SENT_PATH.exists():
        print(f"存档文件不存在: {SENT_PATH}")
        return

    raw_lines = [json.loads(l) for l in SENT_PATH.read_text(encoding='utf-8').splitlines() if l.strip()]
    # 按日期去重与去假期回吐
    recs_by_date = {}
    for r in raw_lines:
        d = str(r.get('date', ''))
        if d:
            recs_by_date[d] = r
    
    unique_dates = sorted(recs_by_date.keys())
    recs = [recs_by_date[d] for d in unique_dates]
    n_total = len(recs)

    # 1. 情绪分统计 (全样本 vs v2尺度)
    all_scores = [float(r['score']) for r in recs if r.get('score') is not None]
    v2_scores = [float(r['score']) for r in recs if r.get('algo') == 'v2' and r.get('score') is not None]
    v1_scores = [float(r['score']) for r in recs if r.get('algo') != 'v2' and r.get('score') is not None]

    # 2. 炸板率统计
    zb_rates = []
    for r in recs:
        zt = float(r.get('zt') or 0)
        zb = float(r.get('zb') or 0)
        if zt + zb > 0:
            zb_rates.append(round(zb / (zt + zb) * 100, 1))

    # 3. 日K对照
    kl = sd.kline_tx('sh000001', 90) or []
    k_map = {str(row[0])[:10].replace('-', ''): float(row[2]) for row in kl}
    k_dates = sorted(k_map.keys())

    # 验证 >35% 炸板率次日表现
    high_zb_next = []
    for r in recs:
        d = str(r.get('date', ''))
        zt = float(r.get('zt') or 0)
        zb = float(r.get('zb') or 0)
        rate = (zb / max(1, zt + zb)) * 100
        if rate >= 35.0:
            nxt = [kd for kd in k_dates if kd > d]
            if nxt:
                nd = nxt[0]
                idx = k_dates.index(nd)
                if idx > 0:
                    p_prev = k_map[k_dates[idx - 1]]
                    p_cur = k_map[nd]
                    chg = round((p_cur - p_prev) / p_prev * 100, 2)
                    high_zb_next.append((d, round(rate, 1), nd, chg))

    print("=" * 72)
    print("📊 股票综合看盘 · 核心判定阈值真实统计核验证明 (真数对账)")
    print("=" * 72)
    print(f"数据事实源: {SENT_PATH.name} (去重有效日期 N={n_total})")
    print(f"算法尺度分布: v1 样本 {len(v1_scores)} 条 | v2 样本 {len(v2_scores)} 条")
    print("-" * 72)

    print("【1. 情绪分历史分位数核验】")
    p25_all, p50_all, p75_all = percentile(all_scores, 25), percentile(all_scores, 50), percentile(all_scores, 75)
    print(f"  · 全量样本 (N={len(all_scores)}): P25={p25_all:.1f} | P50={p50_all:.1f} | P75={p75_all:.1f}")
    if v2_scores:
        print(f"  · v2尺度样本 (N={len(v2_scores)}): 当前仅有 {v2_scores}，样本量严重不足！")
    print(f"  ⚖️ 判定依据性质: 42分/68分 对应全量样本的经验分位（P25={p25_all:.1f}，P75={p75_all:.1f}）。")
    print(f"     必须诚实注明：因v2刚上线仅{len(v2_scores)}条，当前阈值是承袭v1经验分位，待v2积累>=30条后正式校准！\n")

    print("【2. 炸板率历史分位数核验】")
    p25_zb, p50_zb, p75_zb = percentile(zb_rates, 25), percentile(zb_rates, 50), percentile(zb_rates, 75)
    print(f"  · 全量样本 (N={len(zb_rates)}): P25={p25_zb:.1f}% | P50={p50_zb:.1f}% | P75={p75_zb:.1f}% | 最大={max(zb_rates):.1f}%")
    print(f"  ⚖️ 判定依据性质: 18%~25% 对应本库历史中低区分位 (P25~P50)，非全域常态；35% 对应 P75 甚至更高抛压区。\n")

    print(f"【3. 炸板率 >35% 的次日真实表现实测 (实际对账样本 N={len(high_zb_next)})】")
    if high_zb_next:
        for d, r, nd, chg in high_zb_next:
            print(f"  {d} 炸板率 {r}% → 次日({nd}) 上证涨跌: {chg:+5.2f}%")
        down_count = sum(1 for _, _, _, chg in high_zb_next if chg < 0)
        up_count = sum(1 for _, _, _, chg in high_zb_next if chg > 0)
        avg_chg = sum(chg for _, _, _, chg in high_zb_next) / len(high_zb_next)
        print(f"  实测结果: 下跌 {down_count} 次 ({down_count/len(high_zb_next)*100:.1f}%) | 上涨 {up_count} 次 | 次日均幅 {avg_chg:+.2f}%")
        print(f"  ⚖️ 严禁通胀结论: 样本量仅 {len(high_zb_next)} 天，跌多跌少受指数护盘扰动，严禁宣传‘超70%反噬’！")
    else:
        print("  暂无可对账样本。")

    print("-" * 72)
    print("【4. 1进2晋级率与溢价率依据性质】")
    print("  · 1进2 晋级率 (12%) / 溢价率 (0.3% / 1.5%):")
    print("    本库带 effect 历史仅 2 天，本库数据暂无法做大样本推断！")
    print("    诚实口径：此数值严格属于短线交易经验先验规则，杜绝包装成‘本库实证’。\n")
    print("=" * 72)


if __name__ == '__main__':
    run_evidence_audit()
