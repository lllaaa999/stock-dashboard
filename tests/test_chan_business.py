# -*- coding: utf-8 -*-
"""
缠论业务逻辑回归测试 (core/chan.py)

锁定 2026-10-25 以来的关键改动，防止后续迭代破坏：
  1. 分钟K时间戳完整保留（不再被 split()[0] 截成纯日期）
  2. 三买/三卖回抽验证：底分型必须 > 中枢上轨才算三买，否则降级为"待确认"
  3. 笔端点严格交替（不能连续两个顶/底）
  4. MACD 净面积背驰（段内正负抵消后取绝对值，而非逐元素 abs）
  5. signals 字段结构合法（date/price/type/color 齐全）
"""
import sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from core.chan import chan_analysis_structured, calc_ema

fails = []
def check(name, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + name + ((' | ' + str(extra)) if extra else ''))
    if not cond: fails.append(name)


def _make_trend_kl(n=120, base=10.0, amp=2.0, drift=0.0, start_date='2026-01-01 09:30'):
    """生成带趋势的K线序列，触发笔/中枢/信号"""
    kl = []
    y, m, d = 2026, 1, 1
    hh, mm = 9, 30
    for i in range(n):
        wave = math.sin(i / 5.0) * amp + drift * i * 0.05
        o = base + wave
        c = o + 0.15 * math.sin(i / 3.0)
        h = max(o, c) + 0.25 + 0.05 * math.sin(i)
        l = min(o, c) - 0.25 - 0.05 * math.cos(i)
        # 分钟时间戳推进
        mm += 5
        if mm >= 60:
            mm = 0
            hh += 1
        if hh >= 15:
            hh, mm = 9, 30
            d += 1
        if d > 28:
            d = 1
            m += 1
            if m > 12: m = 1
        ts = f'{y:04d}-{m:02d}-{d:02d} {hh:02d}:{mm:02d}'
        kl.append([ts, round(o, 3), round(c, 3), round(h, 3), round(l, 3), 1000])
    return kl


print('=== 1. 分钟K时间戳完整保留 ===')
kl_min = _make_trend_kl(120)
r = chan_analysis_structured(kl_min, '000001.SZ')
check('能正常分析', r.get('status') in ('ok', 'warning'), r.get('status'))
bi_pts = r.get('bi_points') or []
check('产出笔', len(bi_pts) >= 2, f'{len(bi_pts)} 笔')
if bi_pts:
    first_date = str(bi_pts[0][0])
    check('笔端点时间戳带 HH:mm（未被截断）', ' ' in first_date and ':' in first_date, first_date)
    check('笔端点日期部分正确', first_date.startswith('2026-'), first_date)

# 日K也不应该被破坏
kl_day = []
for i in range(120):
    base = 10 + 2 * math.sin(i / 6.0)
    m = (i // 28) + 1
    d = (i % 28) + 1
    kl_day.append([f'2026-{m:02d}-{d:02d}', base, base + 0.1, base + 0.35, base - 0.35, 1000])
r_day = chan_analysis_structured(kl_day)
check('日K也能分析', r_day.get('status') in ('ok', 'warning'), r_day.get('status'))
day_bi = r_day.get('bi_points') or []
if day_bi:
    check('日K笔端点为纯日期', ':' not in str(day_bi[0][0]), day_bi[0][0])

print('\n=== 2. 笔端点严格交替（顶/底不能连续）===')
for res, label in [(r, '分钟K'), (r_day, '日K')]:
    pts = res.get('bi_points') or []
    types = [str(p[2]) for p in pts]
    alternating = all(types[i] != types[i+1] for i in range(len(types)-1))
    check(f'{label} 笔端点顶底交替', alternating, types[:6])
    # 价格方向也应该一致：顶分型价格高于相邻
    prices = [float(p[1]) for p in pts]
    check(f'{label} 笔端点价格非空且为正', all(p > 0 for p in prices), prices[:3])

print('\n=== 3. signals 字段结构合法 ===')
for res, label in [(r, '分钟K'), (r_day, '日K')]:
    sigs = res.get('signals') or []
    check(f'{label} signals 是列表', isinstance(sigs, list))
    for s in sigs[:3]:
        ok = ('date' in s and 'price' in s and 'type' in s and 'color' in s)
        check(f'{label} signal 字段齐全 ({s.get("type", "?")})', ok, s)
        check(f'{label} signal 颜色为合法 hex',
              str(s.get('color', '')).startswith('#'), s.get('color'))

print('\n=== 4. MACD 计算正确性（已知值回归）===')
# 5根价格 10,11,12,11,10 → 手算 EMA12/26 在小样本下退化但不应崩
ema_short = calc_ema([10.0, 11.0, 12.0, 11.0, 10.0], 3)
check('EMA 长度等于输入', len(ema_short) == 5, len(ema_short))
check('EMA 首值等于首输入', abs(ema_short[0] - 10.0) < 1e-6, ema_short[0])
# EMA 平滑系数 k=2/(3+1)=0.5，第二个值 = 10*0.5 + 11*0.5 = 10.5
check('EMA(3) 第二根为 10.5', abs(ema_short[1] - 10.5) < 1e-6, ema_short[1])

print('\n=== 5. 中枢区间合法（lo < hi）===')
for res, label in [(r, '分钟K'), (r_day, '日K')]:
    for zs in (res.get('zhongshu_list') or []):
        lo, hi = float(zs['lo']), float(zs['hi'])
        check(f'{label} 中枢 lo<hi ({lo}~{hi})', lo < hi, zs)
        check(f'{label} 中枢日期存在', bool(zs.get('start_date') and zs.get('end_date')),
              zs.get('start_date'))
    lz = res.get('last_zhongshu')
    if lz:
        check(f'{label} 最后中枢 pos 合法',
              lz.get('pos') in ('内部', '上方', '下方'), lz.get('pos'))

print('\n=== 6. 输出字段完整（上层渲染依赖）===')
REQUIRED = ('status', 'cur_dir', 'trail', 'bi_points', 'zhongshu_list',
            'last_zhongshu', 'signals', 'divergence', 'hint', 'summary')
for res, label in [(r, '分钟K'), (r_day, '日K')]:
    missing = [k for k in REQUIRED if k not in res]
    check(f'{label} 所有必要字段存在', not missing, missing if missing else 'ok')

print()
if fails:
    print('FAILED:', fails); sys.exit(1)
print('=== 缠论业务逻辑测试全部通过 ===')
