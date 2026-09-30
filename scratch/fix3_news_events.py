# -*- coding: utf-8 -*-
"""news_events.py 可读性修正 v3:
① 新浪无【标题】的消息不再拿 60 字正文当标题 → 取首句截断 36 字
② 板块榜"代表消息"优先取【标题】里命中的；只在摘要里命中的板块, 显示摘要上下文片段（不再张冠李戴）
③ 板块词表剔掉东财 hybk 的截断名("房地产服" 是 "房地产服务" 的前缀) → 用更长名替换
"""
import pathlib
import re
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


# ① 新浪标题提取
rep("""            m = re.match(r'^【(.+?)】(.*)$', body)
            title = m.group(1).strip() if m else body[:60]""",
    """            m = re.match(r'^【(.+?)】\\s*(.*)$', body)
            if m:
                title = m.group(1).strip()
            else:
                first = re.split(r'[。！？!?；;]', body)[0] or body
                title = first[:36]""",
    '新浪标题提取')

# ② 板块榜代表消息: 标题命中优先, 否则显示摘要上下文
rep("""            if len(a['samples']) < 3:
                a['samples'].append(e['title'][:48])""",
    """            if len(a['samples']) < 3:
                if s in (e.get('title') or ''):
                    a['samples'].append(e['title'][:48])
                else:
                    _i = (e.get('summary') or '').find(s)
                    if _i >= 0:
                        a['samples'].append('…' + e['summary'][max(0, _i - 8): _i + 30].strip() + '…')
                    else:
                        a['samples'].append(e['title'][:48])""",
    '板块榜代表消息取上下文')

# ③ 板块词表: 剔除被更长名包含的截断名
rep("""    ymd = (date_str or dt.date.today().strftime('%Y-%m-%d')).replace('-', '')
    for kind in ('ZT', 'DT'):
        try:
            for x in (sd._pool(kind, ymd) or []):
                if x.get('hybk'):
                    vocab.add(str(x['hybk']))
        except Exception as e:
            w(f'  [板块词表] {kind} 池行业读取失败: {e}')
    return {v for v in vocab if v and len(v) >= 2}""",
    """    ymd = (date_str or dt.date.today().strftime('%Y-%m-%d')).replace('-', '')
    pool_names = set()
    for kind in ('ZT', 'DT'):
        try:
            for x in (sd._pool(kind, ymd) or []):
                if x.get('hybk'):
                    pool_names.add(str(x['hybk']))
        except Exception as e:
            w(f'  [板块词表] {kind} 池行业读取失败: {e}')
    # 东财 hybk 会截断成 4 字(如 '房地产服'), 若已有更长名包含它就让位给长名, 避免榜上出现半截词
    vocab |= {n for n in pool_names
              if not any(o != n and len(o) > len(n) and o.startswith(n) for o in (vocab | pool_names))}
    return {v for v in vocab if v and len(v) >= 2}""",
    '板块词表剔除截断名')

if fails:
    print()
    print('断言未命中, 不落盘:', fails)
    raise SystemExit(1)

P.write_text(t, encoding="utf-8")
PY = r"C:\Users\28769\AppData\Local\Programs\Python\Python312\python.exe"
r = subprocess.run([PY, "-m", "py_compile", str(P)], capture_output=True, text=True, encoding="utf-8", errors="replace")
print(f'\n已写回 {P} ({P.stat().st_size}B) | py_compile rc={r.returncode} {(r.stderr or "").strip()}')