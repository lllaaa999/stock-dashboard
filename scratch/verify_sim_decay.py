# -*- coding: utf-8 -*-
"""scratch/verify_sim_decay.py — 验证跨节衰减、已消化过滤与阈值依据"""
import sys
import os
import json
import datetime as dt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import sim_llm
import sim_score
import strategic_decision
import stock_dashboard as sd

passed = 0
failed = 0

def check(name, cond, detail=""):
    global passed, failed
    if cond:
        print(f"PASS  {name}   {detail}")
        passed += 1
    else:
        print(f"FAIL  {name}   {detail}")
        failed += 1

print("== 1. 验证 build_seed 跨期衰减计算与时效消化甄别 ==")
seed, err = sim_llm.build_seed('2026-09-30', top_events=10)
check("seed 构建成功且无错误", err is None and seed is not None, str(err))
check("识别目标次一交易日为 20261008", seed.get('next_trade_date') == '20261008', f"target={seed.get('next_trade_date')}")
check("国庆跨期间隔天数为 8 天", seed.get('gap_days') == 8, f"gap_days={seed.get('gap_days')}")
check("跨期衰减系数生效 (0.36左右)", 0.25 <= seed.get('time_decay', 1.0) <= 0.45, f"decay={seed.get('time_decay')}")
check("种子提示词包含两项工程纪律准则", "两项工程纪律准则" in seed.get('text', ''), "包含纪律说明")
check("种子提示词包含跨期衰减警告", "跨期衰减" in seed.get('text', ''), "包含跨期衰减")
check("种子提示词包含日内已反映/警惕兑现", "日内已反映" in seed.get('text', ''), "包含消化过滤")

print("\n== 2. 验证 dry-run 完整链路生成带衰减的 payload ==")
res = sim_llm.run(date_str='2026-09-30', rounds=1, top_events=5, dry_run=True, quiet=True)
check("dry-run 运行成功", res.get('ok') is True, f"ok={res.get('ok')}")
check("payload 包含 target_date", res.get('target_date') == '20261008', f"target_date={res.get('target_date')}")
check("payload 包含 time_decay", res.get('time_decay') == seed.get('time_decay'), f"decay={res.get('time_decay')}")
check("payload 包含 decayed_net", res.get('decayed_net') is not None, f"decayed_net={res.get('decayed_net')}")
check("payload 包含 decayed_net_pct", res.get('decayed_net_pct') is not None, f"decayed_net_pct={res.get('decayed_net_pct')}")
expected_decayed = round(res['net_pct'] * res['time_decay'], 1)
check("decayed_net_pct 计算公式准确", abs(res['decayed_net_pct'] - expected_decayed) <= 0.2, f"act={res['decayed_net_pct']} exp={expected_decayed}")

print("\n== 3. 验证打脸账本 score_one 正确消费 decayed_net_pct ==")
mock_pred = {
    'date': '2026-09-30',
    'model': 'test-model',
    'seed_sha': 'test-sha',
    'net': 57.8,
    'net_pct': 7.9,
    'decayed_net': 20.8,
    'decayed_net_pct': 2.8,  # 跨节衰减后落入中性区间（|net_pct| <= 5）
    'time_decay': 0.36,
    'theme_priority': [{'sector': '银行', 'polarity': 1}],
    'risk_points': [{'item': '高位连板炸板风险'}],
}
mock_facts = {
    'date': '20261008',
    'index_pct': -0.79,
    'score': 40.79,
    'prev': {'date': '20260930', 'score': 50.53, 'zt': 52, 'zb': 12, 'dt': 9, 'max_lb': 7},
    'zt': 43, 'zb': 32, 'dt': 13, 'max_lb': 8,
    'zt_industries': {'电池': 5, '银行': 1}
}
score_res = sim_score.score_one(mock_pred, mock_facts)
check("score_one 优先读取 decayed_net_pct", score_res.get('pred_net_pct') == 2.8, f"pred_net_pct={score_res.get('pred_net_pct')}")
check("保留原始 raw_net_pct 供回溯", score_res.get('raw_net_pct') == 7.9, f"raw_net_pct={score_res.get('raw_net_pct')}")
check("跨期衰减后方向预测转为中性理性研判", score_res['direction']['pred'] == '中性', f"pred_direction={score_res['direction']['pred']}")

print(f"\n全部验证完成: PASS={passed}, FAIL={failed}")
if failed > 0:
    sys.exit(1)
