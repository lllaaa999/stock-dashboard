# -*- coding: utf-8 -*-
"""交付③ 验证：次日打脸账本（记分核心纯函数 + 真实数据可得性）
不依赖次日行情：用合成事实验证规则，再检查真实推演的"次日未归档"路径是否如实报告。
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(r"D:\股票看盘")
sys.path.insert(0, str(ROOT / "scripts"))
import sim_score as ss  # noqa: E402

fails = []


def check(name, cond, extra=''):
    print(('PASS  ' if cond else 'FAIL  ') + name + (('   ' + str(extra)) if extra else ''))
    if not cond:
        fails.append(name)


print("== 1. 方向判定 ==")
h = ss.score_direction(12, {'index_pct': 1.2, 'score': 60.0, 'zt': 55, 'prev': {'score': 55.0, 'zt': 50}})
check("预测偏多 + 实际偏多 → 命中", h['hit'] is True, h['reason'])
h = ss.score_direction(-12, {'index_pct': 0.8, 'score': 58.0, 'prev': {'score': 56.0}})
check("预测偏空 + 实际上涨 → 不中", h['hit'] is False, h['reason'])
h = ss.score_direction(2, {'index_pct': -0.2, 'score': 55.0, 'prev': {'score': 56.0}})
check("预测中性 + 实际窄幅 → 命中", h['hit'] is True, h['reason'])
h = ss.score_direction(10, {})
check("缺数据 → hit=None 且说明原因", h['hit'] is None and '无法判定' in h['reason'], h['reason'])

print()
print("== 2. 强度判定 ==")
h = ss.score_strength(25, {'score': 62.0, 'zt': 60, 'prev': {'score': 55.0, 'zt': 40}})
check("预测强(25) + 情绪分变动7 → 命中强", h['hit'] is True, h['reason'])
h = ss.score_strength(3, {'score': 56.0, 'zt': 41, 'prev': {'score': 55.5, 'zt': 40}})
check("预测弱(3) + 变动很小 → 命中弱", h['hit'] is True, h['reason'])
h = ss.score_strength(25, {'score': 55.2, 'zt': 41, 'prev': {'score': 55.0, 'zt': 40}})
check("预测强但实际很平静 → 不中（虚张声势要被打脸）", h['hit'] is False, h['reason'])

print()
print("== 3. 板块命中 ==")
pred_top = [{'sector': '银行', 'polarity': 1}, {'sector': '汽车', 'polarity': 1},
            {'sector': '创新药', 'polarity': 1}, {'sector': '房地产', 'polarity': -1}]
facts = {'zt_industries': {'半导体': 6, '银行': 5, '汽车': 4, '化学制药': 3, '光伏设备': 2}}
h = ss.score_sectors(pred_top, facts)
check("看多3个中命中2个 → 命中率67%", h['hit'] is True and h['hit_rate_pct'] == 66.7, h['reason'])
check("看空板块不参与命中（房地产不拉低分子）", '房地产' not in h['pred'], h['pred'])
h = ss.score_sectors([{'sector': '白酒', 'polarity': 1}], {'zt_industries': {'半导体': 6}})
check("全不中 → hit=False", h['hit'] is False, h['reason'])
h = ss.score_sectors(pred_top, {})
check("缺次日涨停池 → hit=None", h['hit'] is None, h['reason'])

print()
print("== 4. 情景归位 ==")
h = ss.score_scenario({}, {'index_pct': 0.9, 'score': 60.0, 'zb': 6, 'zt': 60, 'prev': {'score': 57.0}})
check("指数涨+情绪升+炸板低 → 乐观", h['realized'] == '乐观', h['reason'])
h = ss.score_scenario({}, {'index_pct': -1.4, 'score': 50.0, 'zb': 18, 'zt': 30, 'prev': {'score': 57.0}})
check("指数跌+情绪退+炸板高 → 悲观", h['realized'] == '悲观', h['reason'])
h = ss.score_scenario({}, {'index_pct': 0.1, 'score': 57.0, 'zb': 7, 'zt': 40, 'prev': {'score': 57.0}})
check("窄幅+情绪平 → 中性", h['realized'] == '中性', h['reason'])

print()
print("== 5. 风险点核对（只核对可自动验证的，其余如实标未验证）==")
facts = {'zb': 8, 'zt': 45, 'dt': 10, 'max_lb': 5, 'prev': {'dt': 10, 'max_lb': 6}}
h = ss.score_risks([{'item': '炸板与跌停并存', 'reason': 'x'}, {'item': '高位连板特停风险', 'reason': 'y'},
                    {'item': '节后资金回流不确定', 'reason': 'z'}], facts)
check("炸板率15% → 该风险判未发生", h[0]['verdict'] == '未发生', h[0])
check("最高板 6→5 走弱 → 高位风险命中", h[1]['verdict'] == '命中', h[1])
check("无法自动验证的项如实标未验证", h[2]['verdict'] == '未验证', h[2])

print()
print("== 6. 端到端记分 score_one（合成一对预测/事实）==")
pred = {'date': '2026-09-30', 'model': 'x', 'seed_sha': 'abc', 'net': 100.2, 'net_pct': 13.7,
        'theme_priority': [{'sector': '银行', 'polarity': 1}, {'sector': '汽车', 'polarity': 1}],
        'scenarios': {}, 'risk_points': [{'item': '炸板与跌停并存'}]}
res = ss.score_one(pred, {'date': '20261008', 'index_pct': 1.1, 'score': 61.0, 'zt': 60, 'zb': 5, 'dt': 3,
                          'max_lb': 7, 'prev': {'score': 57.66, 'zt': 57, 'dt': 10, 'max_lb': 6},
                          'zt_industries': {'银行': 6, '汽车': 5, '半导体': 9}})
check("score_one 产出五段记分", res.get('ok') and all(k in res for k in ('direction', 'strength', 'sectors', 'scenario', 'risks')))
check("方向命中被记下", res['direction']['hit'] is True, res['direction']['reason'])
check("板块命中率被记下", res['sectors'].get('hit_rate_pct') == 100.0, res['sectors']['reason'])

print()
print("== 7. 真实数据路径：次日未归档时必须如实报告，不能编 ===")
res = ss.run(all_=False, quiet=True)
if not res:
    check("无待记分推演（或已记过）", True, 'ok')
else:
    for r in res:
        check(f"{r.get('pred_date')}: 结果如实（未收盘/休市 → next_day_missing）",
              r.get('ok') is True or r.get('reason') in ('next_day_missing',), r.get('reason'))
scored = list((ROOT / 'data' / 'llm').glob('score-*.json'))
print(f"  已生成的记分文件: {[p.name for p in scored] or '（暂无，需次日数据）'}")
check("未凭空生成记分文件（无次日数据时不该有 score-*.json）",
      (not scored) or all(json.loads(p.read_text(encoding='utf-8')).get('ok') for p in scored), [p.name for p in scored])

print()
print("FAILED:", fails if fails else "无 —— 全部通过")
sys.exit(1 if fails else 0)