# -*- coding: utf-8 -*-
"""fix7 收尾：
① deduce_impact / play_round 函数体完全相同 → 用 count=2 一次替换两处（上次用唯一命中断言, 反而卡住）
② verify 两处断言过时：现在配置文件真实存在(base_url=中转站/model=deepseek-v4.1-flash), 不能再断言内置默认值
③ verify 的"重试"用例改用不可修复输入（截断 JSON）—— 尾逗号已能被新解析器救回, 不再触发重试
"""
import pathlib
import subprocess

SL = pathlib.Path(r"D:\股票看盘\scripts\sim_llm.py")
VF = pathlib.Path(r"D:\股票看盘\scratch\verify_sim_llm.py")
fails = []

OLD_CALL = """    fn = mock_call if dry_run else call_llm
    content, usage = fn([{'role': 'system', 'content': SYSTEM_PROMPT}, {'role': 'user', 'content': user}], cfg)
    data = _extract_json(content)
    return data, usage, content"""
NEW_CALL = """    return _call_json([{'role': 'system', 'content': SYSTEM_PROMPT},
                       {'role': 'user', 'content': user}], cfg, dry_run=dry_run)"""

# ① 两处同体替换
t = SL.read_text(encoding="utf-8")
n = t.count(OLD_CALL)
if n != 2:
    fails.append(f' deduce_impact/play_round 替换: 命中 {n} 次(期望 2)')
    print(f'  FAIL  同体替换: 命中 {n} 次')
else:
    SL.write_text(t.replace(OLD_CALL, NEW_CALL), encoding="utf-8")
    print('  OK    deduce_impact + play_round 均改走 _call_json（count=2）')

# ② verify 断言改配置感知
vt = VF.read_text(encoding="utf-8")
pairs = [
    ('check("默认 base_url 指向 DeepSeek", cfg[\'base_url\'].startswith(\'https://api.deepseek.com\'), cfg[\'base_url\'])',
     'check("base_url 有效（配置文件优先于内置默认）", cfg[\'base_url\'].startswith(\'http\'), f"{cfg[\'base_url\']} ← {cfg[\'source\']}")'),
    ('check("默认模型 deepseek-chat", cfg[\'model\'] == \'deepseek-chat\', cfg[\'model\'])',
     'check("model 非空且来源可追溯", bool(cfg[\'model\']), f"{cfg[\'model\']} ← {cfg[\'source\']}")'),
    ("return '{\"impact\": {\"游资\": 5,}}', {'total_tokens': 10}      # 尾逗号 → 坏",
     "return '{\"impact\": {\"游资\": 5', {'total_tokens': 10}        # 截断 JSON → 不可修复（尾逗号已被解析器救回）"),
]
for old, new in pairs:
    if vt.count(old) != 1:
        fails.append(f'verify: 命中 {vt.count(old)} 次: {old[:40]}')
        print(f'  FAIL  verify 断言未唯一命中: {old[:50]}')
    else:
        vt = vt.replace(old, new)
        print(f'  OK    verify 断言修正: {new[:52]}')
VF.write_text(vt, encoding="utf-8")

if fails:
    print('有失败项:', fails)

PY = r"C:\Users\28769\AppData\Local\Programs\Python\Python312\python.exe"
for f in (SL, VF):
    r = subprocess.run([PY, "-m", "py_compile", str(f)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(f'{f.name} py_compile rc={r.returncode} {(r.stderr or "").strip()[:160]}')