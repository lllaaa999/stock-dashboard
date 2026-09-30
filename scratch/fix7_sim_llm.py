# -*- coding: utf-8 -*-
"""sim_llm.py 修正 v3 —— 抗"模型返回坏 JSON"（实测 web 路径就栽在这）：
① _extract_json 多级修复：去 ``` 包裹 → 去尾逗号 → strict=False → ast.literal_eval 兜底
② 新增 _call_json(...)：解析失败时把原文回喂给模型要求"只输出合法 JSON"并重试一次
③ run() 单轮失败不再弃全局：记下错误、保留已有立场、标记 partial=True
④ verify 脚本补两条：坏 JSON 能修复 / 首次坏→重试成功
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


# ⓿ 补 import re（新解析器要用）
edit(SL, 'import pathlib\nimport sys', 'import pathlib\nimport re\nimport sys', 'sim_llm: 补 import re')

# ① 容错解析
edit(SL, """def _extract_json(text):
    \"\"\"容错解析：模型偶尔会带 ```json 包裹或前后缀\"\"\"
    s = (text or '').strip()
    if s.startswith('```'):
        s = s.split('```')[1] if len(s.split('```')) > 1 else s
        s = s[4:] if s.lower().startswith('json') else s
    i, j = s.find('{'), s.rfind('}')
    if i < 0 or j <= i:
        raise ValueError('响应里没有 JSON 对象')
    return json.loads(s[i:j + 1])""",
     """def _extract_json(text):
    \"\"\"容错解析：```json 包裹 / 前后缀 / 尾逗号 / 单引号 / 控制字符 都要能救回来。

    实测（2026-09-30）：deepseek-v4.1-flash 偶发尾逗号 → json.loads 抛
    "Expecting ',' delimiter" 直接把整轮推演打回 rule 回落，所以这里必须多级修复。
    \"\"\"
    s = (text or '').strip()
    if '```' in s:
        parts = s.split('```')
        if len(parts) >= 2:
            s = parts[1]
        s = s[4:] if s.lstrip().lower().startswith('json') else s
    i, j = s.find('{'), s.rfind('}')
    if i < 0 or j <= i:
        raise ValueError('响应里没有 JSON 对象')
    body = s[i:j + 1]
    cands = [body, re.sub(r',\\s*([}\\]])', r'\\1', body)]
    cands.append(re.sub(r'[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f]', '', cands[-1]))
    last = None
    for c in cands:
        for kwargs in ({}, {'strict': False}):
            try:
                return json.loads(c, **kwargs)
            except Exception as e:
                last = e
    try:                      # 单引号/True/None 之类的 python 字面量兜底
        import ast
        return ast.literal_eval(cands[0])
    except Exception as e:
        last = e
    raise ValueError(f'JSON 解析失败(多级修复后): {last}')


def _call_json(messages, cfg, dry_run=False, retries=1):
    \"\"\"调用并解析 JSON：失败时把原文回喂要求"只输出合法 JSON"再试一次。

    返回 (data, usage, raw_content)。
    \"\"\"
    fn = mock_call if dry_run else call_llm
    msgs, last_err, content = list(messages), None, ''
    for attempt in range(retries + 1):
        content, usage = fn(msgs, cfg)
        try:
            return _extract_json(content), usage, content
        except Exception as e:
            last_err = e
            if attempt < retries:
                w(f'[LLM] 第 {attempt + 1} 次返回不是合法 JSON（{e}），回喂修复提示重试…')
                msgs = msgs + [
                    {'role': 'assistant', 'content': (content or '')[:1200]},
                    {'role': 'user', 'content': '上面这段不是合法 JSON。请只输出合法 JSON：不要 markdown 包裹、'
                                                '不要注释、不要尾逗号，字段与要求完全一致。'},
                ]
    raise ValueError(f'JSON 解析失败(已重试 {retries} 次): {last_err}')""", '_extract_json 多级修复 + _call_json')

# ② deduce_impact 走 _call_json
edit(SL, """    fn = mock_call if dry_run else call_llm
    content, usage = fn([{'role': 'system', 'content': SYSTEM_PROMPT}, {'role': 'user', 'content': user}], cfg)
    data = _extract_json(content)
    return data, usage, content""",
     """    return _call_json([{'role': 'system', 'content': SYSTEM_PROMPT},
                       {'role': 'user', 'content': user}], cfg, dry_run=dry_run)""", 'deduce_impact 走 _call_json')

# ③ play_round 走 _call_json
edit(SL, """    fn = mock_call if dry_run else call_llm
    content, usage = fn([{'role': 'system', 'content': SYSTEM_PROMPT}, {'role': 'user', 'content': user}], cfg)
    data = _extract_json(content)
    return data, usage, content""",
     """    return _call_json([{'role': 'system', 'content': SYSTEM_PROMPT},
                       {'role': 'user', 'content': user}], cfg, dry_run=dry_run)""", 'play_round 走 _call_json')

# ④ run(): 单轮失败不弃全局
edit(SL, """    for rnd in range(2, max(rounds, 1) + 1):
        data, u, _raw = play_round(rnd, seed, stances, cfg, dry_run=dry_run, prev_note=prev_note)
        adj = data.get('adjust') or {}""",
     """    partial = False
    for rnd in range(2, max(rounds, 1) + 1):
        try:
            data, u, _raw = play_round(rnd, seed, stances, cfg, dry_run=dry_run, prev_note=prev_note)
        except Exception as e:
            # 单轮失败不再把整场推演打回回落：记下错误、保留上一轮立场继续
            partial = True
            round_rows.append({'round': rnd, 'error': f'{type(e).__name__}: {e}',
                               'stances': {k: round(v, 1) for k, v in stances.items()}})
            w(f'[LLM] 第 {rnd} 轮失败，保留上一轮立场继续：{type(e).__name__}: {e}')
            continue
        adj = data.get('adjust') or {}""", 'run(): 单轮失败容错')

edit(SL, """        'ok': True, 'engine': 'llm', 'dry_run': bool(dry_run),""",
     """        'ok': True, 'engine': 'llm', 'dry_run': bool(dry_run), 'partial': partial,""", 'payload: partial 标记')

# ⑤ verify 补断言
edit(VF, """try:
    sl._extract_json('完全没有 JSON')
    check("  无 JSON → 抛错", False)
except Exception:
    check("  无 JSON → 抛错", True)""",
     """for name, bad in [('尾逗号', '{"a":1,}'), ('数组尾逗号', '{"a":[1,2,]}'),
                  ('单引号', "{'a': 1}"), ('含控制字符', '{"a":1}\\x07')]:
    try:
        check(f"  坏 JSON 修复: {name}", sl._extract_json(bad) == {'a': 1} or sl._extract_json(bad).get('a') == [1, 2],
              sl._extract_json(bad))
    except Exception as e:
        check(f"  坏 JSON 修复: {name}", False, f'{type(e).__name__}: {e}')
try:
    sl._extract_json('完全没有 JSON')
    check("  无 JSON → 抛错", False)
except Exception:
    check("  无 JSON → 抛错", True)

print()
print("== 3b. 首次坏 JSON → 回喂修复提示后重试成功 ==")
_calls = {'n': 0}


def _flaky(messages, cfg, json_mode=True):
    _calls['n'] += 1
    if _calls['n'] == 1:
        return '{"impact": {"游资": 5,}}', {'total_tokens': 10}      # 尾逗号 → 坏
    return '{"impact": {"游资": 9}}', {'total_tokens': 10}


_real_call = sl.call_llm
sl.call_llm = _flaky
try:
    data, usage, content = sl._call_json([{'role': 'user', 'content': 'x'}], dict(cfg, api_key='dummy'), retries=1)
    check("重试后拿到合法 JSON", data.get('impact', {}).get('游资') == 9, (data, _calls['n']))
    check("确实发生了两次调用", _calls['n'] == 2, _calls['n'])
finally:
    sl.call_llm = _real_call""", 'verify 补坏 JSON 断言')

if fails:
    print('断言未命中, 不落盘:', fails)
    raise SystemExit(1)

PY = r"C:\Users\28769\AppData\Local\Programs\Python\Python312\python.exe"
for f in (SL, VF):
    r = subprocess.run([PY, "-m", "py_compile", str(f)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(f'{f.name} py_compile rc={r.returncode} {(r.stderr or "").strip()[:200]}')