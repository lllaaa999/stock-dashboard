# -*- coding: utf-8 -*-
"""
缠论核心纯算力引擎 (Core Chan Theory Engine)
不包含任何网络请求或文件 I/O，属于纯算法根据地。
支持：K线包含合并、分型识别、笔生成、中枢识别、MACD背驰检测、三类买卖点判定。
"""
from typing import List, Dict, Any


def calc_ema(vals: List[float], n: int) -> List[float]:
    """指数移动平均 (EMA) 纯数学计算

    加固 (2026-10-18): 原实现无参数校验。n=0 时 k=2.0（平滑系数>1，EMA 变成
    放大噪声的迭代，结果毫无意义）；n=-1 时 k 除零抛 ZeroDivisionError；
    n 为 None 时抛 TypeError。这些都会被上层 try/except 吞掉变成"指标算不出来"，
    排查困难。现改为显式抛 ValueError，让错误在调用点暴露。
    """
    if not vals:
        return []
    if not isinstance(n, int) or isinstance(n, bool):
        raise ValueError('calc_ema: n 必须是整数, 收到 %r' % (n,))
    if n <= 0:
        raise ValueError('calc_ema: n 必须为正整数(周期), 收到 %d' % n)
    k = 2.0 / (n + 1)
    out = [vals[0]]
    for v in vals[1:]:
        out.append(out[-1] * (1 - k) + v * k)
    return out


# 兼容旧命名
_ema = calc_ema


def _fmt_date(v) -> str:
    """把各种格式的日期统一成 MM-DD 短串，用于缠论轨迹展示。

    加固 (2026-10-18): 原实现 str(b[3])[5:] 强依赖 'YYYY-MM-DD'，
    对 '20261016'（长度8）会得到 '016'，对 datetime 对象会得到无意义片段。
    """
    s = str(v or '')
    digits = ''.join(ch for ch in s if ch.isdigit())
    if len(digits) >= 8:
        return digits[4:6] + '-' + digits[6:8]
    if len(s) >= 5:
        return s[5:10]
    return s


def chan_analysis_structured(kl: List[Any], code: str = '', period_label: str = '日线') -> Dict[str, Any]:
    """缠论级别结构化分析: K线包含合并、分型、笔、中枢识别、背驰与买卖点判定。

    参数:
        kl: K线列表，格式为 [[日期, 开盘, 收盘, 最高, 最低, ...], ...]
        code: 股票代码(选填)
        period_label: 周期中文名，用于 summary 展示（日线/周线/月线/5分钟等）
    返回:
        结构化形态分析字典
    """
    # 加固 (2026-10-18): 原 `if not kl or len(kl) < 30` 在 kl 为不可 len() 的
    # 对象（如数字/生成器）时会抛 TypeError；且下游直接 float(r[2]) 假设每行
    # 至少 5 列且可转数字，脏数据会中途抛异常让整个分析失败。
    try:
        n_kl = len(kl) if kl is not None else 0
    except TypeError:
        return {
            'status': 'error', 'msg': 'K线数据格式非法(不可索引)',
            'bi_points': [], 'zhongshu_list': [], 'last_zhongshu': None,
            'signals': [], 'cur_dir': '未知', 'trail': '', 'hint': '',
            'summary': 'K线数据格式非法'
        }
    if n_kl < 30:
        return {
            'status': 'error',
            'msg': 'K线数量不足30根，无法构建缠论中枢',
            'bi_points': [],
            'zhongshu_list': [],
            'last_zhongshu': None,
            'signals': [],
            'cur_dir': '未知',
            'trail': '',
            'hint': '',
            'summary': 'K线不足30根，结构尚未成型'
        }

    # 只保留字段齐全、可转为数字的行，避免单行脏数据中断整段分析
    _rows = []
    for r in kl:
        try:
            if len(r) < 5:
                continue
            # 仅做可转换性校验，不保留变量
            float(r[2])
            _high, _low = float(r[3]), float(r[4])
            if not (_high >= _low > 0):
                continue
            _rows.append(r)
        except (TypeError, ValueError, IndexError):
            continue
    if len(_rows) < 30:
        return {
            'status': 'error',
            'msg': '有效K线不足30根(存在脏数据)，无法构建中枢',
            'bi_points': [], 'zhongshu_list': [], 'last_zhongshu': None,
            'signals': [], 'cur_dir': '未知', 'trail': '', 'hint': '',
            'summary': '有效K线不足，结构尚未成型'
        }
    kl = _rows

    closes = [float(r[2]) for r in kl]
    e12 = calc_ema(closes, 12)
    e26 = calc_ema(closes, 26)
    dif = [a - b for a, b in zip(e12, e26)]
    dea = calc_ema(dif, 9)
    hist = [(a - b) * 2 for a, b in zip(dif, dea)]

    # 1. K线包含合并: [日期, 高, 低, 原始索引]
    bars = []
    for i, r in enumerate(kl):
        h, l = float(r[3]), float(r[4])
        if bars and ((h >= bars[-1][1] and l <= bars[-1][2]) or (h <= bars[-1][1] and l >= bars[-1][2])):
            up = len(bars) < 2 or bars[-2][1] <= bars[-1][1]
            if up:
                # 向上合并：高点取 max，低点也取 max（抬升低点）
                new_high = max(bars[-1][1], h)
                new_low = max(bars[-1][2], l)
                # 仅当新K线贡献了高点极值时才更新日期/索引，
                # 避免笔端点系统性偏移到合并区间末根（原Bug：恒指向最后一根）
                if h >= bars[-1][1]:
                    bars[-1][0] = r[0]
                    bars[-1][3] = i
                bars[-1][1] = new_high
                bars[-1][2] = new_low
            else:
                # 向下合并：高点取 min，低点也取 min（压低高点）
                new_high = min(bars[-1][1], h)
                new_low = min(bars[-1][2], l)
                # 仅当新K线贡献了低点极值时才更新日期/索引
                if l <= bars[-1][2]:
                    bars[-1][0] = r[0]
                    bars[-1][3] = i
                bars[-1][1] = new_high
                bars[-1][2] = new_low
        else:
            bars.append([r[0], h, l, i])

    # 2. 分型 -> 笔(交替极值, 间隔>=4根合并K线)
    fx = []
    for i in range(1, len(bars) - 1):
        p0, p1, p2 = bars[i - 1], bars[i], bars[i + 1]
        if p1[1] > p0[1] and p1[1] > p2[1]:
            fx.append([i, '顶', p1[1], p1[0], p1[3]])
        elif p1[2] < p0[2] and p1[2] < p2[2]:
            fx.append([i, '底', p1[2], p1[0], p1[3]])

    bi = []
    for f in fx:
        if not bi:
            bi.append(f)
            continue
        lf = bi[-1]
        if f[1] == lf[1]:
            if (f[1] == '顶' and f[2] > lf[2]) or (f[1] == '底' and f[2] < lf[2]):
                bi[-1] = f
        elif f[0] - lf[0] >= 4:
            bi.append(f)

    if len(bi) < 4:
        return {
            'status': 'warning',
            'msg': '有效笔不足4段，结构未成型',
            'bi_points': [[b[3], round(b[2], 2), b[1], b[4]] for b in bi],
            'zhongshu_list': [],
            'last_zhongshu': None,
            'signals': [],
            'cur_dir': '未知',
            'trail': '',
            'hint': '',
            'summary': '有效笔不足4段，中枢未成型'
        }

    # 加固: 原 str(b[3])[5:] 强依赖 'YYYY-MM-DD' 格式，格式不同（如 '20261016'
    # 或带时间戳）会切出错位的日期串。改为统一的 _fmt_date 处理。
    trail = ' -> '.join('%s%.2f(%s)' % (b[1], b[2], _fmt_date(b[3])) for b in bi[-5:])
    cur_dir = '向下' if bi[-1][1] == '顶' else '向上'
    bi_points = [[b[3], round(b[2], 2), b[1], b[4]] for b in bi]

    # 3. 中枢识别: 三笔重叠区间
    legs = [(bi[j - 1], bi[j]) for j in range(1, len(bi))]
    zhongshu_list = []
    for idx in range(len(legs) - 2):
        sub = legs[idx:idx + 3]
        los = [min(a[2], b[2]) for a, b in sub]
        his = [max(a[2], b[2]) for a, b in sub]
        z_lo, z_hi = max(los), min(his)
        if z_lo < z_hi:
            zhongshu_list.append({
                'lo': round(z_lo, 2),
                'hi': round(z_hi, 2),
                'start_date': sub[0][0][3],
                'end_date': sub[-1][1][3]
            })

    # 加固 (2026-10-18): legs 是 bi 相邻两点组成的"笔段"，其长度恒为 len(bi)-1。
    # 上方已保证 len(bi)>=4，故 legs>=3 理论上成立；但若 bi 结构被异常数据破坏，
    # legs[-3:] 可能不足 3 段，max(los)/min(his) 对空列表会抛 ValueError。
    # 这里显式守卫，宁可没有中枢也不要崩掉整个分析。
    last_zs = None
    pos = None
    if len(legs) >= 3:
        l3 = legs[-3:]
        los = [min(a[2], b[2]) for a, b in l3]
        his = [max(a[2], b[2]) for a, b in l3]
        zs_lo, zs_hi = (max(los), min(his)) if (los and his) else (0.0, 0.0)
    else:
        l3 = []
        zs_lo, zs_hi = 0.0, 0.0
    hints = []
    signals = []

    if zs_lo < zs_hi:
        last_close = closes[-1]
        pos = '内部' if zs_lo <= last_close <= zs_hi else ('上方' if last_close > zs_hi else '下方')
        last_zs = {
            'lo': round(zs_lo, 2),
            'hi': round(zs_hi, 2),
            'start_date': l3[0][0][3],
            'end_date': l3[-1][1][3],
            'pos': pos
        }
        if pos == '上方' and cur_dir == '向上':
            # 三买回抽验证 (2026-10-25): 最后一笔(底分型)必须在中枢上轨之上
            # 才算有效三买，否则回抽已进入中枢区间，三买不成立
            pullback_price = bi[-1][2]
            if pullback_price > zs_hi:
                hints.append('三买候选: 向上离开中枢后次回抽不跌破中枢上轨')
                signals.append({
                    'date': bi[-1][3], 'price': round(bi[-1][2], 2),
                    'type': '三买候选', 'desc': '三买潜力', 'color': '#10b981'
                })
            else:
                hints.append('三买待确认: 回抽进入中枢区间，三买不成立')
                signals.append({
                    'date': bi[-1][3], 'price': round(bi[-1][2], 2),
                    'type': '三买待确认', 'desc': '回抽入中枢·三买未确立', 'color': '#f59e0b'
                })
        elif pos == '下方' and cur_dir == '向下':
            # 三卖回抽验证 (2026-10-25): 最后一笔(顶分型)必须在中枢下轨之下
            # 才算有效三卖，否则反弹已进入中枢区间，三卖不成立
            pullback_price = bi[-1][2]
            if pullback_price < zs_lo:
                hints.append('三卖形态: 向下击穿中枢后次反弹不进中枢下轨')
                signals.append({
                    'date': bi[-1][3], 'price': round(bi[-1][2], 2),
                    'type': '三卖警戒', 'desc': '三卖警戒', 'color': '#ef4444'
                })
            else:
                hints.append('三卖待确认: 反弹进入中枢区间，三卖不成立')
                signals.append({
                    'date': bi[-1][3], 'price': round(bi[-1][2], 2),
                    'type': '三卖待确认', 'desc': '反弹入中枢·三卖未确立', 'color': '#f59e0b'
                })

    # 4. 背驰与一类/二类买卖点判断
    def leg_area(a, b):
        """两笔之间的 MACD 同方向面积（力度），用于背驰比较

        修复 (2026-10-25): 原实现 sum(abs(x) for x in seg) 对每个 hist 值取
        绝对值后再求和，会丢失段内方向信息——当一段内同时有正负 hist 值时，
        abs 会虚增面积。缠中说禅原著中背驰比较的是同方向趋势的面积，应保留
        段内正负抵消：先带符号求和 sum(seg) 得到净面积，再取绝对值用于比较。
        这样 abs 仅作用于最终净面积，而非逐元素，不丢失段内方向信息。

        加固 (2026-10-18): a[4]/b[4] 是 K 线原始索引。合并 K 线后原始索引
        可能大于 hist 长度（hist 与 closes 等长），原来的切片虽然 Python 会
        自动截断，但 lo_i 为负时会产生"从尾部取"的错误区间。这里显式 clamp。
        """
        try:
            lo_i, hi_i = sorted((int(a[4]), int(b[4])))
        except (TypeError, ValueError, IndexError):
            return 0.0
        if not hist:
            return 0.0
        lo_i = max(0, min(lo_i, len(hist) - 1))
        hi_i = max(lo_i, min(hi_i, len(hist) - 1))
        seg = hist[lo_i:hi_i + 1]
        return abs(sum(seg))

    sig_str = ''
    # 加固: 只取结构完整、方向字段合法的笔段，避免脏数据导致 KeyError/IndexError
    dn = [lg for lg in legs
          if len(lg) == 2 and len(lg[1]) > 1 and lg[1][1] == '底']
    up = [lg for lg in legs
          if len(lg) == 2 and len(lg[1]) > 1 and lg[1][1] == '顶']
    if len(dn) >= 2:
        (a1, b1), (a2, b2) = dn[-2], dn[-1]
        if b2[2] < b1[2] and leg_area(a2, b2) < leg_area(a1, b1):
            # 下跌段净面积：后段<前段 → 力度减弱 → 底背驰
            sig_str = '底背驰候选(价创新低·动能收缩)'
            signals.append({
                'date': b2[3], 'price': round(b2[2], 2),
                'type': '底背驰', 'desc': '底背驰', 'color': '#10b981'
            })
            signals.append({
                'date': b2[3], 'price': round(b2[2], 2),
                'type': '一买候选', 'desc': '一买潜力(中枢外趋势背驰)', 'color': '#10b981'
            })
            hints.append('一买候选: 趋势底背驰，极值底确立')
        elif b2[2] >= b1[2]:
            signals.append({
                'date': b2[3], 'price': round(b2[2], 2),
                'type': '二买候选', 'desc': '二买潜力(次笔回抽不破前低)', 'color': '#10b981'
            })
            hints.append('二买候选: 次笔回抽不破前低，底部形态确认')
    if len(up) >= 2:
        (a1, b1), (a2, b2) = up[-2], up[-1]
        if b2[2] > b1[2] and leg_area(a2, b2) < leg_area(a1, b1):
            # 上涨段净面积：后段<前段 → 力度减弱 → 顶背驰
            sig_str = '顶背驰候选(价创新高·动能收缩)'
            signals.append({
                'date': b2[3], 'price': round(b2[2], 2),
                'type': '顶背驰', 'desc': '顶背驰', 'color': '#ef4444'
            })
            signals.append({
                'date': b2[3], 'price': round(b2[2], 2),
                'type': '一卖警戒', 'desc': '一卖警戒(中枢外趋势背驰)', 'color': '#ef4444'
            })
            hints.append('一卖警戒: 趋势顶背驰，极值顶防守')
        elif b2[2] <= b1[2]:
            signals.append({
                'date': b2[3], 'price': round(b2[2], 2),
                'type': '二卖警戒', 'desc': '二卖警戒(次笔反弹不破前高)', 'color': '#ef4444'
            })
            hints.append('二卖警戒: 次笔反弹不破前高，顶部滞涨防守')

    hint = '；'.join(hints)
    summary_parts = [f"当前处于{period_label}【{cur_dir}的一笔】"]
    if last_zs:
        summary_parts.append(f"中枢区间 [{last_zs['lo']} ~ {last_zs['hi']}]，现价位于中枢【{pos}】")
    if hint:
        summary_parts.append(hint)
    if sig_str:
        summary_parts.append(f"异动信号：{sig_str}")

    return {
        'status': 'ok',
        'cur_dir': cur_dir,
        'trail': trail,
        'bi_points': bi_points,
        'bi_list': bi_points,
        'zhongshu_list': zhongshu_list[-3:],
        'last_zhongshu': last_zs,
        'signals': signals,
        'divergence': sig_str or '无明显背驰',
        'hint': hint,
        'summary': '；'.join(summary_parts)
    }
