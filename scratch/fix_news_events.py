# -*- coding: utf-8 -*-
"""修复 news_events.py: ① dedupe 兼容归档态输入(有 sources 列表, 无 source 字段) ② 类型优先级: 海外 提到 政策 前"""
import pathlib
import subprocess

P = pathlib.Path(r"D:\股票看盘\scripts\news_events.py")
t = P.read_text(encoding="utf-8")
fails = []


def rep(old, new, tag, expect=1):
    global t
    n = t.count(old)
    if n != expect:
        fails.append(f'{tag}: 命中 {n} 次(期望 {expect})')
        print(f'  FAIL  {tag}: 命中 {n} 次(期望 {expect})')
        return
    t = t.replace(old, new)
    print(f'  OK    {tag}')


OLD_DEDUPE = '''def dedupe(items, thresh=0.72):
    """标题归一化 + shingle Jaccard 去重（同一快讯会被多源重复推送）"""
    groups, exact = [], {}
    for it in items:
        n = _norm_title(it.get('title'))
        if len(n) < 4:
            continue
        g = exact.get(n)
        if g is not None:
            g['sources'].add(it['source'])
            if not g.get('codes') and it.get('codes'):
                g['codes'] = it['codes']
            continue
        bucket, sh = n[:4], _shingles(n)
        hit = None
        for cand in groups:
            if cand['_bucket'] != bucket:
                continue
            if _jaccard(sh, cand['_sh']) >= thresh:
                hit = cand
                break
        if hit is not None:
            hit['sources'].add(it['source'])
            if not hit.get('codes') and it.get('codes'):
                hit['codes'] = it['codes']
            continue
        g = {'time': it['time'], 'title': it['title'], 'summary': it.get('summary', ''),
             'url': it.get('url', ''), 'codes': it.get('codes', ''), 'sources': {it['source']},
             '_bucket': bucket, '_sh': sh, 'raw_title': it['title']}
        groups.append(g)
        exact[n] = g
    out = []
    for g in groups:
        d = {k: v for k, v in g.items() if not k.startswith('_')}
        d['sources'] = sorted(d.get('sources') or [])
        out.append(d)
    return out'''

NEW_DEDUPE = '''def _srcs_of(it):
    """兼容两种输入形态：采集态(有 source 字段) 与归档态(有 sources 列表)"""
    s = it.get('source')
    if s:
        return {s}
    v = it.get('sources')
    if isinstance(v, list):
        return set(v)
    if isinstance(v, str) and v:
        return set(x for x in v.split(',') if x)
    return {'归档'}


def dedupe(items, thresh=0.72):
    """标题归一化 + shingle Jaccard 去重（同一快讯会被多源重复推送）"""
    groups, exact = [], {}
    for it in items:
        n = _norm_title(it.get('title'))
        if len(n) < 4:
            continue
        srcs = _srcs_of(it)
        g = exact.get(n)
        if g is not None:
            g['sources'] |= srcs
            if not g.get('codes') and it.get('codes'):
                g['codes'] = it['codes']
            continue
        bucket, sh = n[:4], _shingles(n)
        hit = None
        for cand in groups:
            if cand['_bucket'] != bucket:
                continue
            if _jaccard(sh, cand['_sh']) >= thresh:
                hit = cand
                break
        if hit is not None:
            hit['sources'] |= srcs
            if not hit.get('codes') and it.get('codes'):
                hit['codes'] = it['codes']
            continue
        g = {'time': it['time'], 'title': it['title'], 'summary': it.get('summary', ''),
             'url': it.get('url', ''), 'codes': it.get('codes', ''), 'sources': set(srcs),
             '_bucket': bucket, '_sh': sh}
        groups.append(g)
        exact[n] = g
    out = []
    for g in groups:
        d = {k: v for k, v in g.items() if not k.startswith('_')}
        d['sources'] = sorted(d.get('sources') or [])
        out.append(d)
    return out'''

rep(OLD_DEDUPE, NEW_DEDUPE, 'dedupe 重写(兼容归档态)', 1)

# 类型优先级: 海外 先于 政策（"美联储降息/关税"不应被归成政策）
rep('''TYPE_RULES = [
    ('政策', [''', '''TYPE_RULES = [
    ('海外', ['美联储', '鲍威尔', '美股', '纳斯达克', '道琼斯', '标普', '关税', '制裁', '反倾销', '欧盟',
             '日本央行', '原油', '黄金', '美元指数', '以色列', '俄乌', '地缘', '海外', '出口管制']),
    ('政策', [''', '类型规则: 海外 提到 政策 前')
rep('''    ('海外', ['美联储', '鲍威尔', '美股', '纳斯达克', '道琼斯', '标普', '关税', '制裁', '反倾销', '欧盟',
             '日本央行', '原油', '黄金', '美元指数', '以色列', '俄乌', '地缘', '海外', '出口管制']),
    ('公司', [''', '''    ('公司', [''', '删掉原位置的 海外 规则')

if fails:
    print()
    print('有断言未命中, 不落盘:', fails)
    raise SystemExit(1)

P.write_text(t, encoding="utf-8")
PY = r"C:\Users\28769\AppData\Local\Programs\Python\Python312\python.exe"
r = subprocess.run([PY, "-m", "py_compile", str(P)], capture_output=True, text=True, encoding="utf-8", errors="replace")
print(f'\n已写回 {P} ({P.stat().st_size}B) | py_compile rc={r.returncode} {(r.stderr or "").strip()}')
print('规则顺序:', [l.split("'")[1] for l in P.read_text(encoding="utf-8").splitlines() if l.startswith("    ('") and '[' in l][:6])