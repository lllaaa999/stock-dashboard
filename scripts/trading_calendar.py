# -*- coding: utf-8 -*-
"""
交易日历校验模块 (Trading Calendar Guard)

背景 / 为什么需要这个模块
--------------------------------------------------------------------------
东方财富 push2ex 涨停池接口对 **非交易日不返回空**，而是直接回吐最近一个
交易日的快照。实证 (2026-10-18)：

    20261018 周日 -> 61 只
    20261017 周六 -> 61 只
    20261016 周五 -> 61 只      # 三份数据完全一致
    20261019~20261025 未来日期 -> 也都返回 61 只

也就是说接口根本不校验 date 参数。任何"用池子有没有数据来判断是不是
交易日"的逻辑都会把周末/节假日当成交易日，导致：

  1. 昨涨停池 与 今涨停池 取到同一份数据 -> "昨->今"晋级比对变成自己跟自己比
  2. 首板股在"今天"仍是首板 -> 1进2 晋级率恒为 0%
  3. 溢价统计用同一份收盘价对同一份收盘价 -> 红盘率 100%、"超强接力"假信号
  4. 非交易日数据被写入情绪历史存档 -> 污染周期状态机

本模块用**上证指数真实日K**作为权威交易日历 (交易所实际有收盘K线的日期)，
不依赖任何"池子有没有数据"的弱信号。
"""

import datetime as dt
import threading

# 上证指数日K缓存 (进程内, 避免每次调用都打网络)
#   2026-10-18 修复: 原实现"检查缓存"和"回填缓存"分成两把独立的锁，
#   缓存未命中时多个并发线程会同时打上游（实测 10 线程 = 10 次请求，
#   Web 首屏会同时唤起多个接口，正好触发）。改为 single-flight：
#   第一次未命中时只有一个线程去取，其余线程等它取完直接复用结果。
_KLINE_CACHE = {'dates': None, 'ts': 0.0}
_KLINE_TTL = 600.0          # 10 分钟
_LOCK = threading.Lock()
_FETCH_LOCK = threading.Lock()   # 单飞锁：保证同一时刻只有一个线程在拉取


def _load_trading_dates(force=False):
    """拉取最近约 250 个交易日的上证指数日K日期集合 (带 TTL 缓存 + 单飞)"""
    import time as _time

    def _fresh():
        return (_KLINE_CACHE['dates'] is not None
                and _time.time() - _KLINE_CACHE['ts'] < _KLINE_TTL)

    if not force:
        with _LOCK:
            if _fresh():
                return _KLINE_CACHE['dates']

    # single-flight: 拿到 _FETCH_LOCK 的线程负责真正拉取，其余在此排队；
    # 排队线程进入后先再检查一次缓存，通常已有结果，直接返回，不再打网络。
    with _FETCH_LOCK:
        if not force:
            with _LOCK:
                if _fresh():
                    return _KLINE_CACHE['dates']

        now = _time.time()
        dates = set()
        try:
            import stock_dashboard as sd
            kl = sd.kline_tx('sh000001', 250)
            for r in kl or []:
                d = str(r[0])[:10].replace('-', '')
                if len(d) == 8 and d.isdigit():
                    dates.add(d)
        except Exception:
            dates = set()

        if dates:
            with _LOCK:
                _KLINE_CACHE['dates'] = dates
                _KLINE_CACHE['ts'] = now
            return dates

        # 拉取失败: 若手上有旧缓存则降级返回旧值（宁可陈旧也不返回空，
        # 否则所有交易日判定会瞬间失效）
        with _LOCK:
            if _KLINE_CACHE['dates']:
                return _KLINE_CACHE['dates']
        return dates


def latest_trading_day(before_or_on=None):
    """返回 <= 指定日期的最近一个真实交易日 (ymd 字符串)。取不到返回 None"""
    target = before_or_on or dt.date.today().strftime('%Y%m%d')
    dates = _load_trading_dates()
    if not dates:
        return None
    cand = [d for d in dates if d <= target]
    return max(cand) if cand else None


def is_trading_day(ymd):
    """判断 ymd(YYYYMMDD) 是否为本所真实交易日。日历拉取失败时保守返回 False"""
    if not ymd:
        return False
    dates = _load_trading_dates()
    if not dates:
        return False
    return ymd in dates


def get_recent_trading_days(n=2, end_ymd=None, pool_fetcher=None):
    """
    回溯获取最近 n 个**真实交易日**及其涨停池数据。

    :param n:           需要的交易日数量
    :param end_ymd:     从哪天往前回溯 (默认今天)
    :param pool_fetcher: callable(ymd) -> list，默认用东方财富涨停池
    :return: [(ymd, pool), ...] 按日期**从新到旧**排列；数据缺失的日期会被跳过

    与旧实现的关键差异：先用权威交易日历过滤掉非交易日，**再**取池子。
    这样周末/节假日不会再被当成交易日，也不会出现"今昨同源"。
    """
    if pool_fetcher is None:
        import stock_dashboard as sd
        pool_fetcher = lambda ymd: sd._pool('ZT', ymd)

    base = end_ymd or dt.date.today().strftime('%Y%m%d')
    # 入口校验: end_ymd 可能是外部传入的脏值，strptime 会抛未捕获 ValueError
    base = str(base).strip()
    if not (len(base) == 8 and base.isdigit()):
        return []
    try:
        dt.datetime.strptime(base, '%Y%m%d')
    except ValueError:
        return []

    dates = _load_trading_dates()
    fallback_mode = False
    if not dates:
        # 日历不可用 -> 退化为"按工作日回溯 + 池子有无数据"的旧逻辑。
        # 注意：接口对非交易日会回吐最近交易日快照，因此这条路径存在
        # "相邻两天取到同一份数据"的风险。下面用内容指纹去重兜底，
        # 保证不会把同一份数据当成两个交易日（旧 bug 的复发路径）。
        fallback_mode = True
        dates = set()
        d0 = dt.datetime.strptime(base, '%Y%m%d').date()
        for i in range(0, 40):
            d = d0 - dt.timedelta(days=i)
            if d.weekday() < 5:
                dates.add(d.strftime('%Y%m%d'))

    candidates = sorted([d for d in dates if d <= base], reverse=True)

    found = []
    seen_fingerprints = set()
    for ymd in candidates[:40]:          # 最多回看 40 个交易日
        p = pool_fetcher(ymd)
        if not p:
            continue

        if fallback_mode:
            # 内容指纹: 代码集合 + 各股连板数。若与已收集的某天完全一致，
            # 说明接口回吐了同一份快照，跳过，避免"今昨同源"。
            fp = (len(p), tuple(sorted(
                (str(z.get('c', '')), z.get('lbc', 1)) for z in p if isinstance(z, dict)
            )))
            if fp in seen_fingerprints:
                continue
            seen_fingerprints.add(fp)

        found.append((ymd, p))
        if len(found) >= n:
            break
    return found


def purge_non_trading_records(jsonl_path, key='date'):
    """
    清理情绪历史存档里落在非交易日上的错误记录。
    返回 (保留条数, 删除条数, 被删除的日期列表)
    """
    import json
    import os

    if not os.path.exists(jsonl_path):
        return 0, 0, []

    dates = _load_trading_dates()
    kept, dropped, dropped_dates = [], 0, []
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                kept.append(line)
                continue
            d = str(obj.get(key, '') or '')
            if d and dates and d not in dates:
                dropped += 1
                dropped_dates.append(d)
                continue
            kept.append(line)

    if dropped:
        tmp = jsonl_path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            for line in kept:
                f.write(line + '\n')
        os.replace(tmp, jsonl_path)

    return len(kept), dropped, dropped_dates
