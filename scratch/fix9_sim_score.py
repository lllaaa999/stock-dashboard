# -*- coding: utf-8 -*-
"""sim_score.py 修正：风险核对优先采用"可自动验证"的规则。

实测问题："高位连板特停风险" 同时含 "特停"(不可验证) 与 "高位"(可验证)，按顺序先撞上"特停"
→ 判成"未发生"，把本该摇摆的风险说成已排除（比"未验证"更危险）。
改法：把匹配到的规则全部收集，优先取可验证的那条；都不可验证才标"未验证"。
"""
import pathlib
import subprocess

P = pathlib.Path(r"D:\股票看盘\scripts\sim_score.py")
t = P.read_text(encoding="utf-8")
fails = []

OLD = """RISK_RULES = [
    ('炸板', lambda f: (float(f.get('zb') or 0) / max(float(f.get('zt') or 0) + float(f.get('zb') or 0), 1) * 100) > 30,
     '次日炸板率 >30%'),
    ('跌停', lambda f: (float(f.get('dt') or 0) > float((f.get('prev') or {}).get('dt') or 0)), '次日跌停数增加'),
    ('缩量', lambda f: False, '需成交额序列（暂不可自动验证）'),
    ('特停', lambda f: False, '监管特停无法自动验证'),
    ('监管', lambda f: False, '监管动作无法自动验证'),
    ('高位', lambda f: (float(f.get('max_lb') or 0) <= float((f.get('prev') or {}).get('max_lb') or 0)),
     '次日最高板未抬高（高度走弱）'),
]


def score_risks(risks, facts):
    out = []
    for r in (risks or []):
        item = str(r.get('item', ''))
        verdict = '未验证'
        note = ''
        for kw, fn, desc in RISK_RULES:
            if kw in item:
                note = desc
                try:
                    verdict = '命中' if fn(facts) else '未发生'
                except Exception:
                    verdict = '未验证'
                break
        out.append({'item': item, 'reason': r.get('reason', ''), 'verdict': verdict, 'check': note})
    return out"""

NEW = """# (关键词, 判定函数, 说明, 是否可自动验证) —— 可验证的优先，避免"特停"这类不可验证词盖住"高位"
RISK_RULES = [
    ('炸板', lambda f: (float(f.get('zb') or 0) / max(float(f.get('zt') or 0) + float(f.get('zb') or 0), 1) * 100) > 30,
     '次日炸板率 >30%', True),
    ('跌停', lambda f: (float(f.get('dt') or 0) > float((f.get('prev') or {}).get('dt') or 0)), '次日跌停数增加', True),
    ('高位', lambda f: (float(f.get('max_lb') or 0) <= float((f.get('prev') or {}).get('max_lb') or 0)),
     '次日最高板未抬高（高度走弱）', True),
    ('缩量', lambda f: False, '需成交额序列（暂不可自动验证）', False),
    ('特停', lambda f: False, '监管特停无法自动验证', False),
    ('监管', lambda f: False, '监管动作无法自动验证', False),
]


def score_risks(risks, facts):
    \"\"\"风险点核对：命中多条规则时**优先采用可自动验证的那条**，都不可验证才标"未验证"。\"\"\"
    out = []
    for r in (risks or []):
        item = str(r.get('item', ''))
        matches = [(kw, fn, desc, ver) for kw, fn, desc, ver in RISK_RULES if kw in item]
        usable = [m for m in matches if m[3]]
        pick = usable[0] if usable else (matches[0] if matches else None)
        verdict, note = '未验证', ''
        if pick:
            note = pick[2]
            if pick[3]:
                try:
                    verdict = '命中' if pick[1](facts) else '未发生'
                except Exception:
                    verdict = '未验证'
        out.append({'item': item, 'reason': r.get('reason', ''), 'verdict': verdict, 'check': note})
    return out"""

if t.count(OLD) != 1:
    fails.append(f'风险规则块命中 {t.count(OLD)} 次')
    print('  FAIL  风险规则块未唯一命中')
else:
    t = t.replace(OLD, NEW)
    P.write_text(t, encoding="utf-8")
    print('  OK    风险规则改为"可验证优先"')

if fails:
    raise SystemExit(1)
PY = r"C:\Users\28769\AppData\Local\Programs\Python\Python312\python.exe"
r = subprocess.run([PY, "-m", "py_compile", str(P)], capture_output=True, text=True, encoding="utf-8", errors="replace")
print(f'sim_score.py py_compile rc={r.returncode} {(r.stderr or "").strip()[:160]}')