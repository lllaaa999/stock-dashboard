# -*- coding: utf-8 -*-
"""benchmarks/kawai_5year_evidence.py — 5年龙头身位竞争与卡位实证统计 (2021-2026)"""
import os
import sys
import json
import datetime as dt
import pandas as pd
import numpy as np
import baostock as bs

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

# 5年核心战役标的池（代表性龙头与核心对手盘/同题材小弟）
BATTLES = [
    # 2021
    {
        'year': '2021',
        'theme': '碳中和电力',
        'winner': ('sh.600744', '华银电力'),
        'challenger': ('sz.000966', '长源电力'),
        'peer': ('sz.300234', '开尔新材'),
        'start': '2021-03-01', 'end': '2021-04-15'
    },
    {
        'year': '2021',
        'theme': '次新总龙 vs 跨境纺织',
        'winner': ('sz.003039', '顺控发展'),
        'challenger': ('sz.002269', '美邦服饰'),
        'peer': None,
        'start': '2021-03-15', 'end': '2021-04-15'
    },
    {
        'year': '2021',
        'theme': '抗疫医药',
        'winner': ('sz.002432', '九安医疗'),
        'challenger': ('sz.002750', '龙津药业'),
        'peer': ('sz.300261', '雅本化学'),
        'start': '2021-11-15', 'end': '2022-01-20'
    },
    # 2022
    {
        'year': '2022',
        'theme': '新基建双雄',
        'winner': ('sz.002761', '浙江建投'),
        'challenger': ('sz.002037', '保利联合'),
        'peer': None,
        'start': '2022-02-08', 'end': '2022-03-15'
    },
    {
        'year': '2022',
        'theme': '汽车妖王接力',
        'winner': ('sz.000957', '中通客车'),
        'challenger': ('sz.002703', '浙江世宝'),
        'peer': ('sz.000025', '特力A'),
        'start': '2022-05-10', 'end': '2022-07-05'
    },
    {
        'year': '2022',
        'theme': '信创跨年卡位',
        'winner': ('sz.003005', '竞业达'),
        'challenger': ('sz.002474', '榕基软件'),
        'peer': ('sz.000721', '西安饮食'),
        'start': '2022-10-10', 'end': '2022-12-15'
    },
    # 2023
    {
        'year': '2023',
        'theme': 'ChatGPT与算力',
        'winner': ('sz.002229', '鸿博股份'),
        'challenger': ('sz.002362', '汉王科技'),
        'peer': ('sh.603083', '剑桥科技'),
        'start': '2023-01-30', 'end': '2023-03-31'
    },
    {
        'year': '2023',
        'theme': '华为Mate60三核',
        'winner': ('sz.002855', '捷荣技术'),
        'challenger': ('sz.000536', '华映科技'),
        'peer': ('sh.605588', '冠石科技'),
        'start': '2023-08-28', 'end': '2023-10-15'
    },
    {
        'year': '2023',
        'theme': '汽车连板梯队天梯',
        'winner': ('sh.603178', '圣龙股份'),
        'challenger': ('sh.603266', '天龙股份'),
        'peer': ('sh.600178', '东安动力'),
        'start': '2023-09-25', 'end': '2023-12-05'
    },
    # 2024
    {
        'year': '2024',
        'theme': '无人驾驶/萝卜快跑',
        'winner': ('sh.600611', '大众交通'),
        'challenger': ('sh.600650', '锦江在线'),
        'peer': ('sh.600686', '金龙汽车'),
        'start': '2024-07-05', 'end': '2024-08-15'
    },
    {
        'year': '2024',
        'theme': '海思芯片与双星',
        'winner': ('sz.000062', '深圳华强'),
        'challenger': ('sz.001298', '好上好'),
        'peer': ('sz.300050', '世纪鼎利'),
        'start': '2024-08-12', 'end': '2024-09-15'
    },
    {
        'year': '2024',
        'theme': '秋季重组与双龙群',
        'winner': ('sz.002583', '海能达'),
        'challenger': ('sz.000158', '常山北明'),
        'peer': ('sz.002693', '双成药业'),
        'start': '2024-09-20', 'end': '2024-11-05'
    },
    # 2025/2026
    {
        'year': '2026',
        'theme': '算电协同双子星',
        'winner': ('sh.600396', '华电辽能'),
        'challenger': ('sh.600726', '华电能源'),
        'peer': ('sh.601991', '大唐发电'),
        'start': '2026-03-01', 'end': '2026-05-30'
    }
]

def run_5year_evidence():
    lg = bs.login()
    if lg.error_code != '0':
        print(f'Baostock login failed: {lg.error_msg}')
        return

    all_events = []
    winner_next_days = []
    loser_next_days = []
    counter_dragon_next_days = []

    print('=' * 80)
    print('🚀 A股过去5年（2021-2026）龙头身位争夺与卡位实证量化总账')
    print('=' * 80)

    for b in BATTLES:
        c_w, n_w = b['winner']
        c_l, n_l = b['challenger']
        # Query daily data
        rs_w = bs.query_history_k_data_plus(c_w, 'date,open,close,high,low,pctChg,volume', start_date=b['start'], end_date=b['end'], frequency='d', adjustflag='2')
        df_w = rs_w.get_data()
        rs_l = bs.query_history_k_data_plus(c_l, 'date,open,close,high,low,pctChg,volume', start_date=b['start'], end_date=b['end'], frequency='d', adjustflag='2')
        df_l = rs_l.get_data()

        if df_w.empty or df_l.empty:
            continue

        for df in [df_w, df_l]:
            for col in ['open', 'close', 'high', 'low', 'pctChg', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # Merge on date
        m = pd.merge(df_w, df_l, on='date', suffixes=('_w', '_l'))

        # Calculate consecutive limit ups (streak)
        # A limit up in A share main board is approx pctChg >= 9.5 (or >= 19.0 for ChiNext)
        # Detect PK days where both had high attention or streaks were competing
        for i in range(len(m) - 2):
            row = m.iloc[i]
            nxt = m.iloc[i + 1]
            nxt2 = m.iloc[i + 2]

            # Detect Limit Up status today
            is_zt_w = row['pctChg_w'] >= 9.5
            is_zt_l = row['pctChg_l'] >= 9.5

            # Case 1: Direct Kawai PK (One gets Limit Up, the other fails or breaks)
            # Either: 1) Both were in play, W is ZT, L breaks (pctChg_l < 5.0 or high > 5.0 but close < 5.0)
            if is_zt_w and not is_zt_l and (row['high_l'] / m.iloc[max(0, i-1)]['close_l'] - 1 >= 0.04 or m.iloc[max(0, i-1)]['pctChg_l'] >= 9.0):
                # W won the kawai battle today, L lost/was stepped on
                # Calculate T+1 return for both
                t1_gap_w = (nxt['open_w'] / row['close_w'] - 1) * 100
                t1_close_w = nxt['pctChg_w']
                t1_high_w = (nxt['high_w'] / row['close_w'] - 1) * 100
                t3_close_w = (nxt2['close_w'] / row['close_w'] - 1) * 100

                t1_gap_l = (nxt['open_l'] / row['close_l'] - 1) * 100
                t1_close_l = nxt['pctChg_l']
                t1_low_l = (nxt['low_l'] / row['close_l'] - 1) * 100
                t3_close_l = (nxt2['close_l'] / row['close_l'] - 1) * 100

                winner_next_days.append({
                    'date': row['date'], 'battle': f"{n_w} vs {n_l}",
                    'gap': t1_gap_w, 'ret': t1_close_w, 'max_high': t1_high_w, 't3_ret': t3_close_w,
                    'is_zt_next': t1_close_w >= 9.5
                })
                loser_next_days.append({
                    'date': row['date'], 'battle': f"{n_w} vs {n_l}",
                    'gap': t1_gap_l, 'ret': t1_close_l, 'max_drawdown': t1_low_l, 't3_ret': t3_close_l,
                    'is_big_mian': t1_close_l <= -5.0 or t1_low_l <= -7.0
                })

    bs.logout()

    # Generate DataFrames
    df_win = pd.DataFrame(winner_next_days)
    df_lose = pd.DataFrame(loser_next_days)

    print(f'\n[统计样本规模]: 5年跨周期有效卡位PK样本事件数 N = {len(df_win)} 组')
    print('-' * 80)

    # 1. 胜出方数据
    print('【一、卡位胜出方（晋级真龙/抢先封板方）次日实证表现】')
    win_rate_gap = (df_win['gap'] > 0).mean() * 100
    avg_gap = df_win['gap'].mean()
    avg_ret = df_win['ret'].mean()
    zt_prob = df_win['is_zt_next'].mean() * 100
    avg_t3 = df_win['t3_ret'].mean()
    print(f'  · 次日开盘高开率（竞价溢价概率）: {win_rate_gap:.1f}%')
    print(f'  · 次日开盘平均溢价 (Gap Open):      +{avg_gap:.2f}%')
    print(f'  · 次日收盘平均涨跌幅 (T+1 Return):  +{avg_ret:.2f}%')
    print(f'  · 次日继续封板涨停率 (连板晋级率):    {zt_prob:.1f}%')
    print(f'  · 3日累计超额收益 (T+3 Cumulative):   +{avg_t3:.2f}%')

    print('\n【二、被卡失败方（冲高回落/被按水下方）次日实证表现】')
    lose_gap_down = (df_lose['gap'] < 0).mean() * 100
    avg_lose_gap = df_lose['gap'].mean()
    avg_lose_ret = df_lose['ret'].mean()
    big_mian_rate = df_lose['is_big_mian'].mean() * 100
    avg_lose_t3 = df_lose['t3_ret'].mean()
    print(f'  · 次日开盘低开率:                  {lose_gap_down:.1f}%')
    print(f'  · 次日开盘平均低开 (Gap Open):      {avg_lose_gap:.2f}%')
    print(f'  · 次日收盘平均涨幅 (T+1 Return):    {avg_lose_ret:.2f}%')
    print(f'  · 次日大面率 (收盘<=-5%或最大回撤>7%): {big_mian_rate:.1f}%')
    print(f'  · 3日累计收益 (T+3 Cumulative):     {avg_lose_t3:.2f}%')

    print('\n【三、5年典型身位争夺经典战役抽样抽检表】')
    sample_tbl = []
    for i in range(min(10, len(df_win))):
        w_row = df_win.iloc[i]
        l_row = df_lose.iloc[i]
        sample_tbl.append({
            'PK日期': w_row['date'],
            '对决战役': w_row['battle'],
            '胜利方次日高开': f"+{w_row['gap']:.1f}%",
            '胜利方次日收盘': f"+{w_row['ret']:.1f}%",
            '被卡方次日低开': f"{l_row['gap']:.1f}%",
            '被卡方次日收盘': f"{l_row['ret']:.1f}%",
            '次日盈亏剪刀差': f"{(w_row['ret'] - l_row['ret']):.1f}%"
        })
    print(pd.DataFrame(sample_tbl).to_string(index=False))

if __name__ == '__main__':
    run_5year_evidence()
