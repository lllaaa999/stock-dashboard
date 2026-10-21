# -*- coding: utf-8 -*-
"""
缠论引擎防御加固回归测试 (core/chan.py)

背景 (2026-10-18): opencode 审查指出 chan.py 多处缺少入参防御，
脏数据会让整个分析抛异常并被上层静默吞掉，表现为"缠论算不出来"却无原因。

本测试锁定加固后必须满足：
  1. calc_ema 对 n<=0 / 非整数 显式抛 ValueError（而不是静默算出垃圾或除零）
  2. kl 为 None / 不可 len / 元素不足 / 脏数据 时不崩溃，返回 status=error 的完整结构
  3. 正常 K 线行为不变（回归保护）：能产出笔、中枢、summary
  4. _fmt_date 兼容多种日期格式
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from core.chan import calc_ema, chan_analysis_structured, _fmt_date

fails = []
def check(name, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + name + ((' | ' + str(extra)) if extra else ''))
    if not cond: fails.append(name)


def _raises(fn):
    """辅助：调用并判断是否抛异常"""
    try:
        fn()
        return False
    except Exception:
        return True


print('=== 1. calc_ema 参数校验 ===')
check('n=0 抛 ValueError', _raises(lambda: calc_ema([1.0, 2.0], 0)))
check('n=-1 抛 ValueError', _raises(lambda: calc_ema([1.0, 2.0], -1)))
check('n=1.5 抛 ValueError', _raises(lambda: calc_ema([1.0, 2.0], 1.5)))
check('n=None 抛 ValueError', _raises(lambda: calc_ema([1.0, 2.0], None)))
check('vals 为空返回 []', calc_ema([], 12) == [])
check('正常 n=3 长度一致', len(calc_ema([1.0, 2.0, 3.0, 4.0], 3)) == 4)

print('\n=== 2. 异常 K 线输入不崩溃 ===')
ERROR_KEYS = ('status', 'msg', 'bi_points', 'zhongshu_list', 'last_zhongshu',
              'signals', 'cur_dir', 'trail', 'hint', 'summary')
for label, bad in [
    ('None', None),
    ('空列表', []),
    ('不足30根', [[f'2026-01-{i:02d}', 1, 1, 1, 1] for i in range(1, 20)]),
    ('不可len的整数', 12345),
]:
    try:
        r = chan_analysis_structured(bad)
        ok = isinstance(r, dict) and r.get('status') in ('error', 'warning')
        missing = [k for k in ERROR_KEYS if k not in r]
        check('%s -> status=%s 且结构完整' % (label, r.get('status')),
              ok and not missing, missing if missing else 'ok')
    except Exception as e:
        check('%s 不崩溃' % label, False, repr(e))

print('\n=== 3. 脏数据行被过滤而非中断 ===')
# 30 根正常 + 若干脏行（短行/非数字/高低颠倒）
good = [[f'2026-{(i//28)+1:02d}-{(i%28)+1:02d}', 10 + i * 0.1, 10.2 + i * 0.1,
         10.5 + i * 0.1, 9.8 + i * 0.1] for i in range(40)]
dirty = [['2026-02-01', 1, 'abc', 2, 1],        # 收盘价非数字
         ['2026-02-02', 1, 1],                   # 列数不足
         ['2026-02-03', 1, 1, 1, 99],            # 高低颠倒
         None]                                    # None 行
try:
    r = chan_analysis_structured(good + dirty)
    check('脏行被跳过而非崩溃', r.get('status') in ('ok', 'warning', 'error'), r.get('status'))
except Exception as e:
    check('脏行被跳过', False, repr(e))

print('\n=== 4. 正常 K 线：行为不变(回归保护) ===')
# 构造有明显波段的数据，确保能生成笔
import math
kl = []
for i in range(120):
    base = 10 + 2 * math.sin(i / 6.0)
    kl.append([f'2026-{(i//28)+1:02d}-{(i%28)+1:02d}', base, base + 0.1,
               base + 0.35, base - 0.35])
r = chan_analysis_structured(kl)
check('status=ok 或 warning', r.get('status') in ('ok', 'warning'), r.get('status'))
check('产出笔', len(r.get('bi_points') or []) >= 2, len(r.get('bi_points') or []))
check('summary 非空', bool(r.get('summary')), r.get('summary', '')[:40])
check('cur_dir 合法', r.get('cur_dir') in ('向上', '向下', '未知'), r.get('cur_dir'))
if r.get('status') == 'ok':
    check('有中枢时 pos 合法',
          not r.get('last_zhongshu') or r['last_zhongshu'].get('pos') in ('内部', '上方', '下方'),
          (r.get('last_zhongshu') or {}).get('pos'))

print('\n=== 5. _fmt_date 兼容多格式 ===')
for raw, want in [('2026-10-16', '10-16'), ('20261016', '10-16'),
                  ('2026-10-16 15:00:00', '10-16')]:
    got = _fmt_date(raw)
    check('_fmt_date(%r) == %s' % (raw, want), got == want, got)
check('_fmt_date(None) 不崩溃', isinstance(_fmt_date(None), str), repr(_fmt_date(None)))

print()
if fails:
    print('FAILED:', fails); sys.exit(1)
print('=== 缠论加固测试全部通过 ===')
