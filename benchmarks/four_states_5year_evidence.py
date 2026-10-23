# -*- coding: utf-8 -*-
"""benchmarks/four_states_5year_evidence.py — A股5年真实行情四态（共振攻坚/逆势大妖/孤立脉冲/双子星换手）量化实证"""
import os
import sys
import json
import pandas as pd
import numpy as np
import baostock as bs

# 5年跨周期全景核心标的群与关联题材
THEMES = [
    # 2021
    {
        'year': '2021', 'name': '碳中和电力',
        'leader': ('sh.600744', '华银电力'), 'peer1': ('sz.000966', '长源电力'), 'peer2': ('sz.300234', '开尔新材'),
        'start': '2021-03-01', 'end': '2021-04-15'
    },
    {
        'year': '2021', 'name': '九安抗疫与医药',
        'leader': ('sz.002432', '九安医疗'), 'peer1': ('sz.002750', '龙津药业'), 'peer2': ('sz.300261', '雅本化学'),
        'start': '2021-11-15', 'end': '2022-01-20'
    },
    # 2022
    {
        'year': '2022', 'name': '新基建双雄',
        'leader': ('sz.002761', '浙江建投'), 'peer1': ('sz.002037', '保利联合'), 'peer2': ('sh.600512', '腾达建设'),
        'start': '2022-02-08', 'end': '2022-03-25'
    },
    {
        'year': '2022', 'name': '汽车大周期',
        'leader': ('sz.000957', '中通客车'), 'peer1': ('sz.002703', '浙江世宝'), 'peer2': ('sz.000025', '特力A'),
        'start': '2022-05-10', 'end': '2022-07-05'
    },
    # 2023
    {
        'year': '2023', 'name': 'AI算力与模型',
        'leader': ('sz.002229', '鸿博股份'), 'peer1': ('sz.002362', '汉王科技'), 'peer2': ('sh.603083', '剑桥科技'),
        'start': '2023-01-30', 'end': '2023-04-15'
    },
    {
        'year': '2023', 'name': '华为Mate60',
        'leader': ('sz.002855', '捷荣技术'), 'peer1': ('sz.000536', '华映科技'), 'peer2': ('sh.605588', '冠石科技'),
        'start': '2023-08-28', 'end': '2023-10-15'
    },
    # 2024
    {
        'year': '2024', 'name': '无人驾驶',
        'leader': ('sh.600611', '大众交通'), 'peer1': ('sh.600650', '锦江在线'), 'peer2': ('sh.600686', '金龙汽车'),
        'start': '2024-07-05', 'end': '2024-08-15'
    },
    {
        'year': '2024', 'name': '华为海思',
        'leader': ('sz.000062', '深圳华强'), 'peer1': ('sz.001298', '好上好'), 'peer2': ('sz.300050', '世纪鼎利'),
        'start': '2024-08-12', 'end': '2024-09-15'
    },
    {
        'year': '2024', 'name': '秋季科技重组',
        'leader': ('sz.002583', '海能达'), 'peer1': ('sz.000158', '常山北明'), 'peer2': ('sz.300339', '润和软件'),
        'start': '2024-09-20', 'end': '2024-11-05'
    },
    # 2026
    {
        'year': '2026', 'name': '算电协同双子星',
        'leader': ('sh.600396', '华电辽能'), 'peer1': ('sh.600726', '华电能源'), 'peer2': ('sh.601991', '大唐发电'),
        'start': '2026-03-01', 'end': '2026-05-30'
    }
]

def run_four_states_study():
    lg = bs.login()
    if lg.error_code != '0':
        print(f'Baostock login failed: {lg.error_msg}')
        return

    records = []

    for t in THEMES:
        stocks = [t['leader'], t['peer1']]
        if t.get('peer2'):
            stocks.append(t['peer2'])

        dfs = {}
        for code, name in stocks:
            rs = bs.query_history_k_data_plus(code, 'date,open,close,high,low,pctChg,volume', start_date=t['start'], end_date=t['end'], frequency='d', adjustflag='2')
            df = rs.get_data()
            if not df.empty:
                for c in ['open', 'close', 'high', 'low', 'pctChg', 'volume']:
                    df[c] = pd.to_numeric(df[c], errors='coerce')
                dfs[name] = df

        # Query Index sh.000001
        rs_idx = bs.query_history_k_data_plus('sh.000001', 'date,open,close,high,low,pctChg,volume', start_date=t['start'], end_date=t['end'], frequency='d')
        df_idx = rs_idx.get_data()
        if not df_idx.empty:
            for c in ['open', 'close', 'high', 'low', 'pctChg', 'volume']:
                df_idx[c] = pd.to_numeric(df_idx[c], errors='coerce')
            dfs['大盘'] = df_idx

        if t['leader'][1] not in dfs or '大盘' not in dfs:
            continue

        lead_name = t['leader'][1]
        peer1_name = t['peer1'][1]
        peer2_name = t.get('peer2', (None, None))[1]

        df_m = dfs[lead_name][['date', 'open', 'close', 'high', 'low', 'pctChg', 'volume']].copy()
        df_m.rename(columns={c: f'{c}_lead' for c in ['open', 'close', 'high', 'low', 'pctChg', 'volume']}, inplace=True)

        if peer1_name in dfs:
            df_p1 = dfs[peer1_name][['date', 'open', 'close', 'high', 'low', 'pctChg', 'volume']].copy()
            df_p1.rename(columns={c: f'{c}_p1' for c in ['open', 'close', 'high', 'low', 'pctChg', 'volume']}, inplace=True)
            df_m = pd.merge(df_m, df_p1, on='date', how='inner')

        if peer2_name and peer2_name in dfs:
            df_p2 = dfs[peer2_name][['date', 'open', 'close', 'high', 'low', 'pctChg', 'volume']].copy()
            df_p2.rename(columns={c: f'{c}_p2' for c in ['open', 'close', 'high', 'low', 'pctChg', 'volume']}, inplace=True)
            df_m = pd.merge(df_m, df_p2, on='date', how='inner')

        df_idx_sub = dfs['大盘'][['date', 'pctChg']].copy()
        df_idx_sub.rename(columns={'pctChg': 'pct_index'}, inplace=True)
        df_m = pd.merge(df_m, df_idx_sub, on='date', how='inner')

        # Iterate days
        for i in range(len(df_m) - 2):
            row = df_m.iloc[i]
            nxt = df_m.iloc[i + 1]
            nxt2 = df_m.iloc[i + 2]

            # Target 1: Leader is active
            ret_lead = row['pctChg_lead']
            ret_idx = row['pct_index']
            p1_ret = row.get('pctChg_p1', 0)
            p2_ret = row.get('pctChg_p2', 0)
            max_peer_ret = max(p1_ret, p2_ret)

            # Check forward return for Leader
            t1_gap = (nxt['open_lead'] / row['close_lead'] - 1) * 100
            t1_ret = nxt['pctChg_lead']
            t1_low = (nxt['low_lead'] / row['close_lead'] - 1) * 100
            t3_ret = (nxt2['close_lead'] / row['close_lead'] - 1) * 100
            is_zt_next = t1_ret >= 9.5
            is_big_mian = (t1_ret <= -5.0) or (t1_low <= -7.0)

            # 1. 🔥 共振攻坚: 龙头大涨/涨停 (>=7%) + 同题材至少1只跟涨 (>=5%) + 大盘平稳/微红 (pct_index > -0.4%)
            if ret_lead >= 7.0 and max_peer_ret >= 5.0 and ret_idx >= -0.4:
                records.append({
                    'date': row['date'], 'theme': t['name'], 'stock': lead_name,
                    'state': '🔥共振攻坚', 't1_gap': t1_gap, 't1_ret': t1_ret, 'is_zt_next': is_zt_next,
                    'is_big_mian': is_big_mian, 't3_ret': t3_ret
                })

            # 2. ⚡ 逆势大妖: 大盘急跌跳水 (pct_index <= -0.7%) + 龙头顶风大涨/涨停 (ret_lead >= 6.5%)
            elif ret_idx <= -0.7 and ret_lead >= 6.5:
                records.append({
                    'date': row['date'], 'theme': t['name'], 'stock': lead_name,
                    'state': '⚡逆势大妖', 't1_gap': t1_gap, 't1_ret': t1_ret, 'is_zt_next': is_zt_next,
                    'is_big_mian': is_big_mian, 't3_ret': t3_ret
                })

            # 3. ⚠️ 孤立脉冲: 龙头或小弟单股冲高 (>=5%)，但同题材其他关联股全在水下或极弱 (max_peer_ret < 1.0%)
            elif ret_lead >= 5.0 and max_peer_ret < 1.0 and ret_idx > -0.7:
                records.append({
                    'date': row['date'], 'theme': t['name'], 'stock': lead_name,
                    'state': '⚠️孤立脉冲', 't1_gap': t1_gap, 't1_ret': t1_ret, 'is_zt_next': is_zt_next,
                    'is_big_mian': is_big_mian, 't3_ret': t3_ret
                })

            # 4. 🔄 双子星换手: 主龙大分歧 (ret_lead <= -3.0% 或断板)，但二号星 (p1) 强势逆转封板 (p1_ret >= 9.5%)
            if ret_lead <= -3.0 and p1_ret >= 9.5:
                # Evaluate Peer1 forward return
                t1_gap_p1 = (nxt['open_p1'] / row['close_p1'] - 1) * 100
                t1_ret_p1 = nxt['pctChg_p1']
                t1_low_p1 = (nxt['low_p1'] / row['close_p1'] - 1) * 100
                t3_ret_p1 = (nxt2['close_p1'] / row['close_p1'] - 1) * 100
                records.append({
                    'date': row['date'], 'theme': t['name'], 'stock': f'{peer1_name}(接力{lead_name})',
                    'state': '🔄双子星换手', 't1_gap': t1_gap_p1, 't1_ret': t1_ret_p1,
                    'is_zt_next': t1_ret_p1 >= 9.5, 'is_big_mian': (t1_ret_p1 <= -5.0) or (t1_low_p1 <= -7.0),
                    't3_ret': t3_ret_p1
                })

    bs.logout()

    df = pd.DataFrame(records)
    print('=' * 85)
    print('📊 A股 5 年（2021-2026）龙头四态异动实证量化总账 (真实盘后对账)')
    print('=' * 85)
    print(f'总有效事件样本量 N = {len(df)} 组\n')

    summary = []
    for state in ['🔥共振攻坚', '⚡逆势大妖', '⚠️孤立脉冲', '🔄双子星换手']:
        sub = df[df['state'] == state]
        if sub.empty:
            continue
        summary.append({
            '异动态标签': state,
            '样本数N': len(sub),
            '次日高开率': f"{(sub['t1_gap'] > 0).mean() * 100:.1f}%",
            '次日平均开盘': f"+{sub['t1_gap'].mean():.2f}%" if sub['t1_gap'].mean() > 0 else f"{sub['t1_gap'].mean():.2f}%",
            '次日收盘均幅': f"+{sub['t1_ret'].mean():.2f}%" if sub['t1_ret'].mean() > 0 else f"{sub['t1_ret'].mean():.2f}%",
            '次日连板率': f"{(sub['is_zt_next']).mean() * 100:.1f}%",
            '次日大面率': f"{(sub['is_big_mian']).mean() * 100:.1f}%",
            '3日累计收益': f"+{sub['t3_ret'].mean():.2f}%" if sub['t3_ret'].mean() > 0 else f"{sub['t3_ret'].mean():.2f}%",
        })

    print(pd.DataFrame(summary).to_string(index=False))
    print('\n' + '=' * 85)

    # Print 8 classic cases
    print('【经典实战抽检对账清单（精选8例）】')
    samples = df.sample(min(8, len(df)), random_state=42)[['date', 'theme', 'stock', 'state', 't1_gap', 't1_ret', 't3_ret']]
    samples.rename(columns={'t1_gap': '次日开盘', 't1_ret': '次日收盘', 't3_ret': '3日累计'}, inplace=True)
    print(samples.to_string(index=False))

if __name__ == '__main__':
    run_four_states_study()
