# -*- coding: utf-8 -*-
"""验证门禁 v2 与账本 upsert（用合成数据离线验证 + 真实重跑验证自愈）"""
import json
import pathlib
import sys

ROOT = pathlib.Path(r"D:\股票看盘")
sys.path.insert(0, str(ROOT / "scripts"))
import stock_dashboard as sd   # noqa: E402
import sim_score as ss         # noqa: E402

fails = []


def check(name, cond, extra=''):
    print(('PASS  ' if cond else 'FAIL  ') + name + (('   ' + str(extra)) if extra else ''))
    if not cond:
        fails.append(name)


print("== 1. 归档门禁 v2：当初那条假记录现在挡得住吗 ==")
recs = [{'date': '20260929', 'zt': 57, 'zb': 8, 'dt': 10, 'max_lb': 6},
        {'date': '20260930', 'zt': 52, 'zb': 12, 'dt': 9, 'max_lb': 7}]
# 复刻 10-01 的现场：当天是假期，但接口回吐了 09-30 的池子 → 四项数值完全相同
ok, why = sd._archive_eligible('20261001', recs, 52, 12, 9, 7)
check("假期日(不在日K) 被拒", ok is False, why)
check("  拒绝理由指向'不在交易所日K'", '不在交易所日K' in why, why)

print()
print("== 2. fail-closed：日K取不到时不许放行 ==")
_real = sd.kline_tx
sd.kline_tx = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('网络挂了'))
ok, why = sd._archive_eligible('20261008', recs, 43, 32, 13, 8)
check("日K异常 → 拒绝入库(fail-closed)", ok is False, why)
sd.kline_tx = lambda *a, **k: []
ok, why = sd._archive_eligible('20261008', recs, 43, 32, 13, 8)
check("日K为空 → 拒绝入库(fail-closed)", ok is False, why)
sd.kline_tx = _real

print()
print("== 3. 正常交易日仍要放行（不能误杀）==")
ok, why = sd._archive_eligible('20261008', recs, 43, 32, 13, 8)
check("10-08(真实交易日, 数值与前一日不同) → 放行", ok is True, why)

print()
print("== 4. 回吐检测：数值与最近交易日完全相同 → 拒绝 + 给人话指引 ==")
ok, why = sd._archive_eligible('20261008', recs, 52, 12, 9, 7)
check("四项与 09-30 完全相同 → 拒绝", ok is False, why)
check("  给出 FORCE_ARCHIVE 补录指引", 'FORCE_ARCHIVE' in why, why)
ok, why = sd._archive_eligible('20261008', recs, 43, 32, 13, 8)
check("数值不同 → 放行（不误杀真实交易日）", ok is True, why)

print()
print("== 5. 账本 upsert：重跑不再累计虚高，陈旧样本自愈 ==")
led = ss.LEDGER
n_before = len([l for l in led.read_text(encoding='utf-8').splitlines() if l.strip()]) if led.exists() else 0
rows = [json.loads(l) for l in led.read_text(encoding='utf-8').splitlines() if l.strip()] if led.exists() else []
print(f"  修前账本: {n_before} 条 | 其中 (pred,next) = {sorted((r.get('pred_date'), r.get('next_date')) for r in rows)}")
res = ss.run(all_=True, quiet=True)
rows = [json.loads(l) for l in led.read_text(encoding='utf-8').splitlines() if l.strip()]
keys = sorted((r.get('pred_date'), r.get('next_date')) for r in rows)
print(f"  重算(全量)后: {len(rows)} 条 | (pred,next) = {keys}")
check("同一笔预测只留一条（upsert 生效）", len(rows) == len(set(r.get('pred_date') for r in rows)), len(rows))
check("陈旧样本(次日=20261001)已被覆盖掉", all(k[1] != '20261001' for k in keys), keys)
check("次日起点已是真实的 20261008", any(k[1] == '20261008' for k in keys), keys)
ss.run(all_=True, quiet=True)
rows2 = [json.loads(l) for l in led.read_text(encoding='utf-8').splitlines() if l.strip()]
check("再跑一次条数不变（不再重复追加）", len(rows2) == len(rows), (len(rows), len(rows2)))
st = ss.ledger_stats()
print(f"  累计统计: {st}")
check("统计口径 = 去重后样本数", st.get('samples') == len(rows), st)

print()
print("== 6. 默认路径（不加 --all）也不会被陈旧样本挡住 ==")
todo = []
for p in ss.predictions():
    d = p.stem.replace('sim-', '')
    nxt = ss.next_trade_date(d)
    if nxt and not ss.already_scored(d, nxt):
        todo.append(d)
check("已记且次日正确 → 默认跳过（不重复计分）", todo == [], todo)
check("若次日变了 → 会重算（陈旧样本挡不住）",
      ss.already_scored('2026-09-30', '20261001') is False and ss.already_scored('2026-09-30', '20261008') is True)

print()
print("FAILED:", fails if fails else "无 —— 全部通过")
sys.exit(1 if fails else 0)