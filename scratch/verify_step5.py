# -*- coding: utf-8 -*-
"""P2-⑤ 验证: 涨停质量分单测 / 封板时间分级边界 / 缺数据归一 / E 策略排序接入 / 源码接入点自检"""
import contextlib
import io
import pathlib
import sys

ROOT = pathlib.Path(r"D:\股票看盘")
sys.path.insert(0, str(ROOT / "scripts"))
import stock_dashboard as sd  # noqa: E402
import strategies_lib as sl  # noqa: E402

fails = []


def check(name, cond, extra=''):
    print(('PASS  ' if cond else 'FAIL  ') + name + (('   ' + str(extra)) if extra else ''))
    if not cond:
        fails.append(name)


print("== 1. limit_up_quality 单测 ==")
s1, d1 = sd.limit_up_quality({'fbt': 92530, 'fund': 6e8, 'ltsz': 100e8, 'lbc': 2, 'zbc': 0})
check("竞价封板 + 封单占流通6% + 2板 -> 满分 10.0", s1 == 10.0, s1)
check("  detail 三项齐全 + seal_ratio 正确", d1['used_factors'] == 3 and not d1['missing'] and d1['seal_ratio_pct'] == 6.0, d1)
s2, _ = sd.limit_up_quality({'fbt': 143000, 'fund': 0.3e8, 'ltsz': 100e8, 'lbc': 1, 'zbc': 0})
check("尾盘封板 + 封单0.3% + 首板 -> 1.9", s2 == 1.9, s2)
s3, _ = sd.limit_up_quality({'fbt': 95500, 'fund': 2e8, 'ltsz': 100e8, 'lbc': 1, 'zbc': 0})
check("9:45封板 + 封单2% + 首板 -> 6.45", s3 == 6.45, s3)
s4, _ = sd.limit_up_quality({'fbt': 92530, 'fund': 6e8, 'ltsz': 100e8, 'lbc': 2, 'zbc': 3})
check("烂板(炸3次) 扣 1.5 -> 8.5", s4 == 8.5, s4)
s5, _ = sd.limit_up_quality({'fbt': 92530, 'fund': 6e8, 'ltsz': 100e8, 'lbc': 2, 'zbc': 2})
check("炸2次 扣 0.7 -> 9.3", s5 == 9.3, s5)
s6, d6 = sd.limit_up_quality({'fbt': 92530, 'fund': 6e8, 'ltsz': 0, 'lbc': 2, 'zbc': 0})
check("缺流通市值 -> 按剩余权重归一(仍10.0) 且标记 missing", s6 == 10.0 and d6['missing'] and d6['used_factors'] == 2, (s6, d6))
s7, d7 = sd.limit_up_quality({'fbt': 92530, 'ltsz': 0, 'lbc': 0})
check("只剩封板时间一个因子 -> 该因子满分 10.0", s7 == 10.0 and d7['used_factors'] == 1, (s7, d7))
s8, d8 = sd.limit_up_quality({})
check("空字典 -> 0 分且标记 missing", s8 == 0.0 and d8.get('missing'), (s8, d8))
s9, _ = sd.limit_up_quality({'fbt': 92530, 'fund': 1e8, 'ltsz': 100e8, 'lbc': 7, 'zbc': 0})
check("高位 7 板 -> 连板分 0 (不奖励高位)", s9 == round((10 * .35 + 7 * .35 + 0 * .30), 2), s9)

print()
print("== 2. 封板时间分级边界 ==")
for fbt, want in [(93000, 10.0), (93001, 8.0), (100000, 8.0), (100001, 5.0),
                  (113000, 5.0), (113001, 2.0), (140000, 2.0), (140001, 0.0), (150000, 0.0)]:
    v, _ = sd.limit_up_quality({'fbt': fbt, 'ltsz': 0, 'lbc': 0})
    check(f"  封板 {fbt} -> 时间分 {want}", v == want, v)

print()
print("== 3. E 策略排序接入（打桩行情快照, 离线可复现）==")
fake_zt = [
    # 晚封但封单占比高 -> 旧逻辑(按封单占比)排第一
    {'c': '600001', 'n': '晚封高封单', 'hybk': '测试', 'lbc': 1, 'fbt': 95900, 'fund': 1.74e8, 'ltsz': 60e8, 'zbc': 0},
    # 竞价封板但封单占比低 -> 新逻辑(质量分)排第一
    {'c': '600002', 'n': '竞价低封单', 'hybk': '测试', 'lbc': 1, 'fbt': 92520, 'fund': 0.96e8, 'ltsz': 60e8, 'zbc': 0},
]
sl.by_code = lambda: {x['c']: {'f6': 5e8, 'f62': 1e8, 'f2': 11.0, 'f3': 10.0, 'f10': 3.0} for x in fake_zt}
q_a, _ = sd.limit_up_quality(fake_zt[0])
q_b, _ = sd.limit_up_quality(fake_zt[1])
print(f"   质量分: 晚封高封单={q_a}  竞价低封单={q_b}   (旧口径按封单占比: 晚封2.9% > 竞价1.6%)")
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    raw = sl.scr_first_board(fake_zt)
order = [x.get('n') for _q, _r, x, _f, _a in raw]
check("E 按质量分排序: 竞价低封单 在前（与旧口径相反）", order == ['竞价低封单', '晚封高封单'], order)
check("E 把 qlty 写回池子对象供下游复用", all('qlty' in x for _q, _r, x, _f, _a in raw))
check("E CLI 输出带质量列", '质量' in buf.getvalue(), buf.getvalue().strip()[:60])

print()
print("== 4. 源码接入点自检 ==")
src = (ROOT / "scripts" / "strategies_lib.py").read_text(encoding="utf-8")
check("E/F/H 三处排序键均改为 (质量, 原分)", src.count("out.sort(key=lambda t: (-t[0], -t[1]))") == 3,
      src.count("out.sort(key=lambda t: (-t[0], -t[1]))"))
check("Web 适配器 E 解包 5 元组", src.count("for _q, ratio, x, fbt, amt in (raw or [])[:10]:") == 1)
check("Web 适配器 F/H 解包 6 元组", src.count("for _q, sc, c, x, pct_t1, fbt in (raw or [])[:8]:") == 2)
check("Web 条目带 quality 字段", src.count("'quality': _q,") == 3, src.count("'quality': _q,"))
chunks = {}
for _part in src.split("\ndef ")[1:]:
    chunks[_part.split("(")[0].strip()] = _part
_targets = ('scr_first_board', 'scr_break_rebound', 'scr_n_shape')
_bad = [n for n in _targets if "out.sort(key=lambda t: (-t[0], -t[1]))" not in chunks.get(n, "")]
check("E/F/H 各自函数体内都用了新排序键(其余策略保留原样)", not _bad, _bad)

print()
print("FAILED:", fails if fails else "无 —— 全部通过")
sys.exit(1 if fails else 0)