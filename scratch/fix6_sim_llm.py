# -*- coding: utf-8 -*-
"""sim_llm.py 修正 v2:
① run() 里把 deduce_impact 的返回值当成了冲击矩阵（其实是整个响应体）→ 九方全 0、多轮空。改为先取 resp['impact']
② mock_call 支持两种形态：第一轮(冲击矩阵) / 后续轮(博弈修正)，否则 dry-run 的多轮永远是空的
③ verify 脚本补两条断言（多轮内容非空、冲击值确实落进 stances）
"""
import pathlib
import subprocess

SL = pathlib.Path(r"D:\股票看盘\scripts\sim_llm.py")
VF = pathlib.Path(r"D:\股票看盘\scratch\verify_sim_llm.py")
fails = []


def edit(path, old, new, tag, expect=1):
    t = path.read_text(encoding="utf-8")
    n = t.count(old)
    if n != expect:
        fails.append(f'{tag}: 命中 {n} 次(期望 {expect})')
        print(f'  FAIL  {tag}: 命中 {n} 次')
        return
    path.write_text(t.replace(old, new), encoding="utf-8")
    print(f'  OK    {tag}')


edit(SL, """    impact, u0, raw0 = deduce_impact(seed, cfg, dry_run=dry_run)
    usages.append(u0)
    weights = FORCE_WEIGHT
    stances = {}
    for n, _wt, _d in FORCES:
        stances[n] = max(-100.0, min(100.0, float(impact.get(n, 0))))""",
     """    resp, u0, raw0 = deduce_impact(seed, cfg, dry_run=dry_run)
    usages.append(u0)
    weights = FORCE_WEIGHT
    # 注意: deduce_impact 返回的是整个响应体, 冲击矩阵在 resp['impact']
    impact_map = {str(k): v for k, v in (resp.get('impact') or {}).items()}
    stances = {}
    for n, _wt, _d in FORCES:
        try:
            stances[n] = max(-100.0, min(100.0, float(impact_map.get(n, 0))))
        except (TypeError, ValueError):
            stances[n] = 0.0""", 'run(): 取 resp[impact]')

edit(SL, """        'impact': {k: round(float(impact.get(k, 0)), 1) for k in weights},
        'theme_priority': impact.get('theme_priority') or [],
        'risk_points': impact.get('risk_points') or [],
        'scenarios': impact.get('scenarios') or {},
        'key_variables': impact.get('key_variables') or [],
        'narrative': impact.get('narrative', ''),
        'confidence': impact.get('confidence'),""",
     """        'impact': {k: round(float(impact_map.get(k) or 0), 1) for k in weights},
        'theme_priority': resp.get('theme_priority') or [],
        'risk_points': resp.get('risk_points') or [],
        'scenarios': resp.get('scenarios') or {},
        'key_variables': resp.get('key_variables') or [],
        'narrative': resp.get('narrative', ''),
        'confidence': resp.get('confidence'),""", 'payload: 从 resp 取')

edit(SL, """def mock_call(messages, cfg, json_mode=True):
    return json.dumps(MOCK_RESPONSE, ensure_ascii=False), {'prompt_tokens': 1234, 'completion_tokens': 456,
                                                           'total_tokens': 1690, 'mock': True}""",
     """MOCK_ROUND = {
    'adjust': {'国家队': 2, '机构': -3, '游资': 5, '团伙(控盘)': 4, '散户': 6,
               '北向': 1, '量化': -2, '产业资本': 1, '大散户': 5},
    'cross': '游资与小散接力情绪票，机构借政策利好逢高派发，量能在缩量中撤退。',
    'next_day': '次日合力偏多但强度有限（存量博弈，需竞价确认）。',
    'confidence': 0.58,
}


def mock_call(messages, cfg, json_mode=True):
    \"\"\"dry-run 专用：按提示词形态返回对应样例（第一轮=冲击矩阵，后续轮=博弈修正）\"\"\"
    user = ' '.join(m.get('content', '') for m in messages if m.get('role') == 'user')
    body = MOCK_ROUND if '\"adjust\"' in user else MOCK_RESPONSE
    return json.dumps(body, ensure_ascii=False), {'prompt_tokens': 1234, 'completion_tokens': 456,
                                                  'total_tokens': 1690, 'mock': True}""", 'mock 两种形态')

edit(VF, """check("dry_run 标记为真", p.get('dry_run') is True)""",
     """check("dry_run 标记为真", p.get('dry_run') is True)
check("多轮含交叉判断与次日定性", all(r.get('cross') and r.get('next_day') for r in (p.get('rounds') or [])),
      [(r.get('cross'), r.get('next_day')) for r in (p.get('rounds') or [])][:1])
check("冲击值确实落进最终立场(非全零)", any(abs(v) > 0 for v in (p.get('stances_final') or {}).values()),
      p.get('stances_final'))""", 'verify 补断言')

if fails:
    print('断言未命中, 不落盘:', fails)
    raise SystemExit(1)

PY = r"C:\Users\28769\AppData\Local\Programs\Python\Python312\python.exe"
for f in (SL, VF):
    r = subprocess.run([PY, "-m", "py_compile", str(f)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(f'{f.name} py_compile rc={r.returncode} {(r.stderr or "").strip()[:160]}')