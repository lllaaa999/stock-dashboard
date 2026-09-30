# -*- coding: utf-8 -*-
"""news_events.py 修正 v5:
① 去重加"重叠系数"判据(交集/较短标题 >=0.8) —— 修掉"央行宣布降准50个基点" vs "央行降准50个基点" 漏合并
② 归档口径统一: merge_raw 拆成 _union_prev + save_raw, 归档写的 = 模糊去重后的当日消息
   (让 "jsonl 行数 == 事件表条数" 成为可断言的不变量)
"""
import pathlib
import subprocess

NE = pathlib.Path(r"D:\股票看盘\scripts\news_events.py")
t = NE.read_text(encoding="utf-8")
fails = []


def edit(old, new, tag, expect=1):
    global t
    n = t.count(old)
    if n != expect:
        fails.append(f'{tag}: 命中 {n} 次(期望 {expect})')
        print(f'  FAIL  {tag}: 命中 {n} 次')
        return
    t = t.replace(old, new)
    print(f'  OK    {tag}')


# ① 重叠系数函数
edit("def _containment(a, b):",
     "def _overlap_coef(a, b):\n"
     "    \"\"\"重叠系数 = 交集 / 较短集合 —— 处理'一条标题比另一条多几个修饰词'的情形\"\"\"\n"
     "    if not a or not b:\n"
     "        return 0.0\n"
     "    return len(a & b) / float(min(len(a), len(b)))\n\n\n"
     "def _containment(a, b):",
     '重叠系数函数')

# ② 去重判据
edit("if _jaccard(sh, g['_sh']) >= thresh or _containment(n, g['_norm']):",
     "if (_jaccard(sh, g['_sh']) >= thresh or _overlap_coef(sh, g['_sh']) >= 0.8\n"
     "                    or _containment(n, g['_norm'])):",
     '去重判据加重叠系数')

# ③ 归档函数拆分
OLD_MERGE = """def merge_raw(date_str, new_items):
    \"\"\"与已归档的当日消息做并集（按归一化标题去重），避免重跑丢数据\"\"\"
    path, _ = _day_paths(date_str)
    merged, seen = [], set()
    existing = []
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                existing.append(json.loads(line))
            except Exception:
                continue
    for it in existing + new_items:
        n = _norm_title(it.get('title'))
        if not n or n in seen:
            continue
        seen.add(n)
        merged.append(it)
    merged.sort(key=lambda x: x.get('time', ''))
    path.write_text('\\n'.join(json.dumps(x, ensure_ascii=False) for x in merged) + '\\n', encoding='utf-8')
    return merged, len(existing)"""

NEW_MERGE = """def _union_prev(prev, new_items):
    \"\"\"与已归档的当日消息做并集（按归一化标题精确去重），避免重跑丢数据\"\"\"
    out, seen = [], set()
    for it in list(prev) + list(new_items):
        n = _norm_title(it.get('title'))
        if not n or n in seen:
            continue
        seen.add(n)
        out.append(it)
    return out


def save_raw(date_str, items):
    \"\"\"归档写的 = 模糊去重后的当日消息（保证 jsonl 行数 == 事件表条数）\"\"\"
    path, _ = _day_paths(date_str)
    rows = sorted(items, key=lambda x: x.get('time', ''))
    path.write_text('\\n'.join(json.dumps(x, ensure_ascii=False) for x in rows) + '\\n', encoding='utf-8')
    return len(rows)"""

edit(OLD_MERGE, NEW_MERGE, '归档函数拆分')

# ④ run() 归档流程
edit("""    if not no_fetch:
        deduped, _prev = merge_raw(date_str, deduped)
        deduped = dedupe(deduped)   # 并集后再去一次（跨源的近似重复）""",
     """    if not no_fetch:
        prev = load_raw(date_str)
        if prev:
            deduped = _union_prev(prev, deduped)   # 与已归档消息并集（按归一化标题精确合并）
        deduped = dedupe(deduped)                  # 再模糊去重（跨源近似重复）
        save_raw(date_str, deduped)                # 归档 = 去重后的当日消息""",
     'run() 归档流程')

if fails:
    print('断言未命中, 不落盘:', fails)
    raise SystemExit(1)

NE.write_text(t, encoding="utf-8")
PY = r"C:\Users\28769\AppData\Local\Programs\Python\Python312\python.exe"
r = subprocess.run([PY, "-m", "py_compile", str(NE)], capture_output=True, text=True, encoding="utf-8", errors="replace")
print(f'已写回 {NE} ({NE.stat().st_size}B) | py_compile rc={r.returncode} {(r.stderr or "").strip()}')