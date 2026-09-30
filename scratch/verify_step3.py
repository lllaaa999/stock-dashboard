# -*- coding: utf-8 -*-
"""Step3 验证: 情绪分 v2(去饱和 + 赚钱效应 + 背离标记) + 竞价雷达缓存 + 尺度隔离

用法: python scratch/verify_step3.py   （纯离线, 不联网）
"""
import json
import pathlib
import sys
import types

ROOT = pathlib.Path(r"D:\股票看盘")
sys.path.insert(0, str(ROOT / "scripts"))
import stock_dashboard as sd  # noqa: E402

fails = []


def check(name, cond, extra=''):
    print(('PASS  ' if cond else 'FAIL  ') + name + (('   ' + str(extra)) if extra else ''))
    if not cond:
        fails.append(name)


EFF_TODAY = {'available': True, 'premium': 1.54, 'rate_1to2': 12.8,
             'score': 0.6 * ((1.54 + 5) / 10) + 0.4 * (12.8 / 50),
             'y_date': '20260929', 'tag': '接力偏弱'}
EFF_STRONG = {'available': True, 'premium': 4.5, 'rate_1to2': 62.0,
              'score': 0.6 * 0.95 + 0.4 * 1.0}

print("== 1. v1 对照公式（应与今日存档的 61.11 一致）==")
v1 = sd._emotion_score_v1(45, 10, 4, 7)
check("v1(45,10,4,7) ≈ 61.11", abs(v1 - 61.11) < 0.05, round(v1, 2))

print()
print("== 2. v2 公式：今日真实参数（涨停45/炸板10/跌停4/7板，竞价雷达实测 溢价+1.54% 晋级12.8%）==")
s2, div2 = sd._emotion_score_v2(45, 10, 4, 7, EFF_TODAY)
print("   v1 =", round(v1, 2), "-> v2 =", round(s2, 2), "| band =", sd._emotion_band(s2), "| diverge =", div2)
check("v2 今日 ≈ 55.1（比 v1 的 61.1 更贴近“接力偏弱”的事实）", abs(s2 - 55.11) < 0.15, round(s2, 2))
check("band 仍为 中性（阈值未动）", sd._emotion_band(s2) == '中性')
check("背离标记 = score_high_effect_weak", div2 == 'score_high_effect_weak')

print()
print("== 3. 去饱和：v1 在 80 家以上饱和（80 与 150 同分），v2 不再饱和 ==")
v1_80, v1_150 = sd._emotion_score_v1(80, 10, 4, 7), sd._emotion_score_v1(150, 10, 4, 7)
v2_80, _ = sd._emotion_score_v2(80, 10, 4, 7, EFF_TODAY)
v2_150, _ = sd._emotion_score_v2(150, 10, 4, 7, EFF_TODAY)
print(f"   v1: 80家={v1_80:.2f} 150家={v1_150:.2f} 差={v1_150-v1_80:.2f}")
print(f"   v2: 80家={v2_80:.2f} 150家={v2_150:.2f} 差={v2_150-v2_80:.2f}")
check("v1 在 80 家后基本饱和（80→150 仅差 %.2f 分，只剩炸板率分母的残余变化）" % (v1_150 - v1_80),
      (v1_150 - v1_80) < 1.2)
check("v2 分辨率更高（80→150 差 %.2f 分，是 v1 的 %.1f 倍）" % (v2_150 - v2_80, (v2_150 - v2_80) / max(v1_150 - v1_80, 1e-9)),
      (v2_150 - v2_80) > (v1_150 - v1_80) * 3)
check("v2 的饱和点上移到 120 家", abs(sd._emotion_score_v2(120, 10, 4, 7, EFF_TODAY)[0]
                                - sd._emotion_score_v2(150, 10, 4, 7, EFF_TODAY)[0]) < 2.2)

print()
print("== 4. 低情绪 + 强赚钱效应 -> 冰点试错窗口标记 ==")
s4, div4 = sd._emotion_score_v2(8, 6, 10, 2, EFF_STRONG)
print("   score =", round(s4, 2), "| band =", sd._emotion_band(s4), "| diverge =", div4)
check("低分(<50) + 溢价>3% + 晋级>50% -> score_low_effect_strong", div4 == 'score_low_effect_strong', div4)

print()
print("== 5. 赚钱效应取不到 -> 中性计入 + 不标背离 ==")
s5, div5 = sd._emotion_score_v2(45, 10, 4, 7, {'available': False, 'reason': 'x'})
check("按中性 12.5 分计入（≈55.24）", abs(s5 - 55.24) < 0.15, round(s5, 2))
check("不标背离", div5 is None)

print()
print("== 6. 竞价雷达缓存（否则 web 每次刷新都要付 ~6s）==")
calls = {'n': 0}
fake = types.ModuleType('auction_radar')


def _fake_radar():
    calls['n'] += 1
    return {'status': 'ok',
            'premium_summary': {'avg_curr_pct': 1.54, 'y_date': '20260929', 'sentiment_tag': '接力偏弱'},
            'promotion_metrics': {'rate_1to2': 12.8}}


fake.get_auction_radar = _fake_radar
sys.modules['auction_radar'] = fake
sd._EFFECT_CACHE.update({'t': 0.0, 'data': None})
e1 = sd._effect_metrics()
e2 = sd._effect_metrics()
check("首次命中并给出 score≈0.4948", bool(e1.get('available')) and abs(e1['score'] - 0.4948) < 0.001, e1.get('score'))
check("第二次走缓存（雷达只被调 1 次）", calls['n'] == 1, calls)


def _boom():
    raise RuntimeError('should not be called (cache)')


fake.get_auction_radar = _boom
e3 = sd._effect_metrics()
check("缓存期内雷达即使炸了也返回缓存值", e3.get('available') is True)
sd._EFFECT_CACHE.update({'t': 0.0, 'data': None})
e4 = sd._effect_metrics()
check("缓存过期 + 雷达异常 -> available=False 且带 reason",
      (not e4.get('available')) and 'should not be called' in e4.get('reason', ''))

print()
print("== 7. 历史存档未被改写（v2 记录将从今日收盘起追加）==")
h = ROOT / "data" / "stock_data" / "sentiment_history.jsonl"
recs = [json.loads(l) for l in h.read_text(encoding='utf-8').splitlines() if l.strip()]
last = recs[-1]
print("   末条:", {k: last.get(k) for k in ('date', 'score', 'algo', 'score_v1', 'effect', 'diverge')})
check("末条仍是 v1 结构（无 algo 字段）", last.get('algo') is None and last.get('date') == '20260929')

print()
print("FAILED:", fails if fails else "无 —— 全部通过")
sys.exit(1 if fails else 0)