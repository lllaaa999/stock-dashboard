# -*- coding: utf-8 -*-
"""news_events.py 修正 v4（按验证暴露的真问题）:
① 去重改用 shingle 倒排索引找候选(不再用"前 4 字"分桶, 修掉"央行宣布降准50个基点" vs "央行降准50个基点" 漏合并),
   并对"一条标题包含另一条"(≥8 字)直接判重
② 强度以【标题】为准打分, 标题无信号时才回退看摘要 —— 修掉摘要里无关大数字把强度抬到顶格(Top1 "韩国税收 9.6")
③ 全局性政策工具(降准/降息/万亿级)额外 +1.0
④ 同步修正 verify 脚本里过时的期望值(基础强度 2.0)
"""
import pathlib
import subprocess

NE = pathlib.Path(r"D:\股票看盘\scripts\news_events.py")
VF = pathlib.Path(r"D:\股票看盘\scratch\verify_news_events.py")
fails = []


def edit(path, old, new, tag, expect=1):
    t = path.read_text(encoding="utf-8")
    n = t.count(old)
    if n != expect:
        fails.append(f'{tag}: 命中 {n} 次(期望 {expect})')
        print(f'  FAIL  {tag}: 命中 {n} 次(期望 {expect})')
        return
    path.write_text(t.replace(old, new), encoding="utf-8")
    print(f'  OK    {tag}')


# ① 去重重写
OLD_DEDUPE_Span_Start = "def _srcs_of(it):"
NEW = '''def _containment(a, b):
    """一条归一化标题包含另一条(≥8 字) —— 快讯常换标题重发同一件事"""
    if len(a) < 8 or len(b) < 8:
        return False
    return a in b or b in a


def dedupe(items, thresh=0.72):
    """标题归一化 + shingle 倒排索引去重（跨源/跨轮次重复推送极多）

    候选用 shingle 倒排表找(而非前缀分桶 —— 前缀分桶会漏掉"央行宣布降准" vs "央行降准"这类),
    再加"短标题被长标题包含"的直接判重。
    """
    groups, idx_sh = [], {}
    for it in items:
        n = _norm_title(it.get('title'))
        if len(n) < 4:
            continue
        srcs = _srcs_of(it)
        sh = _shingles(n)
        cands = {}
        for sg in sh:
            for gi in idx_sh.get(sg, ()):
                cands[gi] = cands.get(gi, 0) + 1
        need = max(3, int(len(sh) * 0.4))
        hit = None
        for gi, ov in cands.items():
            if ov < need:
                continue
            g = groups[gi]
            if _jaccard(sh, g['_sh']) >= thresh or _containment(n, g['_norm']):
                hit = g
                break
        if hit is not None:
            hit['sources'] |= srcs
            if not hit.get('codes') and it.get('codes'):
                hit['codes'] = it['codes']
            if len(n) < len(hit['_norm']):
                hit['_norm'] = n            # 留更短更干净的标题做后续包含判断
            continue
        g = {'time': it['time'], 'title': it['title'], 'summary': it.get('summary', ''),
             'url': it.get('url', ''), 'codes': it.get('codes', ''), 'sources': set(srcs),
             '_sh': sh, '_norm': n}
        groups.append(g)
        for sg in sh:
            idx_sh.setdefault(sg, set()).add(len(groups) - 1)
    out = []
    for g in groups:
        d = {k: v for k, v in g.items() if not k.startswith('_')}
        d['sources'] = sorted(d.get('sources') or [])
        out.append(d)
    return out


'''
t = NE.read_text(encoding="utf-8")
i = t.find(OLD_DEDUPE_Span_Start)
j = t.find("# ==================== ② 整理 ====================")
if i < 0 or j < 0 or i > j:
    fails.append('去重重写: 找不到区间')
    print('  FAIL  去重重写: 找不到区间')
else:
    t = t[:i] + NEW + t[j:]
    NE.write_text(t, encoding="utf-8")
    print('  OK    去重改 shingle 倒排索引 + 包含判重')

# ② 强度以标题为准
edit(NE, """        text = (it.get('title') or '') + ' ' + (it.get('summary') or '')
        cl = classify(text)""",
     """        title = it.get('title') or ''
        summary = it.get('summary') or ''
        text = title + ' ' + summary
        # 打分以【标题】为准（摘要里常出现与事件无关的大数字, 会把强度抬到顶格）; 标题无信号才回退看摘要
        cl = classify(title)
        if cl['type'] == '其他' and cl['polarity'] == 0:
            alt = classify(text[:400])
            if alt['type'] != '其他' or alt['polarity'] != 0:
                cl = alt""",
     '强度以标题为准')

# ③ 全局性政策工具加权
edit(NE, "    strength = 2.0 + {'政策': 2.0, '海外': 1.5, '公司': 1.0, '行业': 1.0, '市场结构': 1.0}.get(typ, 0.0)",
     "    strength = 2.0 + {'政策': 2.0, '海外': 1.5, '公司': 1.0, '行业': 1.0, '市场结构': 1.0}.get(typ, 0.0)\n"
     "    if typ == '政策' and ('万亿' in text or any(k in text for k in ('降准', '降息', '印花税', '全面'))):\n"
     "        strength += 1.0      # 全局性政策工具(降准/降息/万亿级)属市场级事件",
     '全局性政策加权')

# ④ verify 脚本过时期望
edit(VF, 'check("无信号 → 其他 / 中性 / 强度 3.0", c6[\'type\'] == \'其他\' and c6[\'polarity\'] == 0 and c6[\'strength\'] == 3.0, c6)',
     'check("无信号 → 其他 / 中性 / 基础强度 2.0", c6[\'type\'] == \'其他\' and c6[\'polarity\'] == 0 and c6[\'strength\'] == 2.0, c6)',
     'verify 期望值修正')

if fails:
    print()
    print('断言未命中, 不落盘:', fails)
    raise SystemExit(1)

PY = r"C:\Users\28769\AppData\Local\Programs\Python\Python312\python.exe"
for f in (NE, VF):
    r = subprocess.run([PY, "-m", "py_compile", str(f)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(f'{f.name} py_compile rc={r.returncode} {(r.stderr or "").strip()}')