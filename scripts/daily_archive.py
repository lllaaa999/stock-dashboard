# -*- coding: utf-8 -*-
"""
每日盘面事实归档（B1）

产出 data/stock_data/daily/YYYYMMDD.json：
  情绪五件套 + 涨停梯队分层 + 竞价候选 + 板块资金 + 当日决策摘要 + 各块可用性标记。

设计原则（与项目既有「不可变快照」守则一致）：
  1. 只写事实，不写预测：情绪只从已归档的 sentiment_history / snapshot 读取，
     不回算、不新抓（补档 30 天不应触发 30 次情绪链路上游）。
  2. 缺失即 unknown：某一块拿不到就 available=false + reason，绝不填 0 冒充真值。
  3. 幂等 + 可重复执行：已存在的归档默认跳过（--force 才重写），写入走 tmp+replace。
  4. 当日归档只在 15:00 后允许生成（盘中数据未定稿），历史日期可补档。

配套：
  - 连续性校验 archive_status()：列出区间内缺失的交易日（接口 /api/daily/archive_status）
  - 补档 CLI：python scripts/daily_archive.py --from 20261001 --to 20261102
"""
import os
import io
import json
import datetime as dt
import argparse

import stock_dashboard as sd
import trading_calendar as tc

ARCHIVE_DIR = os.path.join(sd.DATA_DIR, 'daily')
AUCTION_DIR = os.path.join(sd.DATA_DIR, 'auction_records')
SCHEMA = 'daily_archive.v1'

# 竞价候选归档时只保留复盘需要的字段（bids/asks 明细太大，且原始文件仍在）
_AUCTION_FIELDS = (
    'code', 'name', 'open_pct', 'pct', 'vol_ratio', 'drop_from_high',
    'is_fake_high_open', 'is_zt', 'lbc', 'seal_amount_yi', 'order_ratio', 'reason',
)


def _clean_ymd(ymd):
    s = str(ymd or '').replace('-', '').strip()
    return s[:8] if (len(s) >= 8 and s[:8].isdigit()) else ''


def _read_json(path):
    if not os.path.exists(path):
        return None
    try:
        with io.open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _atomic_write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with io.open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def archive_path(ymd):
    return os.path.join(ARCHIVE_DIR, _clean_ymd(ymd) + '.json')


def _sentiment_records():
    """读 sentiment_history.jsonl 全量（坏行跳过）"""
    fp = os.path.join(sd.DATA_DIR, 'sentiment_history.jsonl')
    rows = []
    if not os.path.exists(fp):
        return rows
    with io.open(fp, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict) and obj.get('date'):
                rows.append(obj)
    return rows


def _emotion_block(ymd):
    """情绪五件套：sentiment_history 优先（离线、口径统一），snapshot 补缺字段"""
    rec = None
    for r in _sentiment_records():
        if str(r.get('date')) == ymd:
            rec = r
    snap = sd.get_daily_snapshot(ymd) if rec is None or rec.get('effect') is None else None

    if rec is None and snap is None:
        return {'available': False, 'reason': 'no_emotion_archive'}

    src = 'sentiment_history' if rec is not None else 'snapshot'
    out = {'available': True, 'source': src}
    fields = ('score', 'band', 'zt', 'zb', 'dt', 'max_lb', 'effect', 'diverge', 'stage', 'cycle_stage')
    for k in fields:
        if rec is not None and rec.get(k) is not None:
            out[k] = rec[k]
        elif snap is not None and snap.get(k) is not None:
            out[k] = snap[k]
    if snap is not None and rec is not None:
        for k in ('score', 'band', 'zt', 'zb', 'dt', 'max_lb'):
            if out.get(k) is None and snap.get(k) is not None:
                out[k] = snap[k]
    return out


def _ladder_block(ymd):
    """涨停梯队分层：按连板高度聚合（复用 push2ex 涨停池，历史日期可查）"""
    try:
        pool = sd._pool('ZT', ymd) or []
    except Exception as e:
        return {'available': False, 'reason': f'pool_fetch_error: {e}'}
    if not pool:
        return {'available': False, 'reason': 'zt_pool_empty_or_unavailable'}

    by_board = {}
    stocks = []
    for item in pool:
        code = str(item.get('c') or item.get('code') or '')
        name = item.get('n') or item.get('name') or ''
        try:
            lbc = int(item.get('lbc') or item.get('board_count') or 1)
        except (TypeError, ValueError):
            lbc = 1
        row = {'code': code, 'name': name, 'boards': lbc}
        stocks.append(row)
        by_board.setdefault(lbc, []).append(row)

    groups = [
        {'boards': b, 'count': len(rows), 'stocks': rows}
        for b, rows in sorted(by_board.items(), reverse=True)
    ]
    return {
        'available': True,
        'source': 'eastmoney_zt_pool',
        'total': len(pool),
        'max_height': max(by_board.keys()),
        'by_board': groups,
    }


def _auction_block(ymd):
    p = os.path.join(AUCTION_DIR, 'auction_candidates_%s.json' % ymd)
    data = _read_json(p)
    if not data:
        return {'available': False, 'reason': 'no_auction_candidates_file',
                'expected_file': os.path.basename(p)}
    cands = []
    for c in (data.get('weak_to_strong') or []):
        cands.append({k: c.get(k) for k in _AUCTION_FIELDS if c.get(k) is not None})
    return {
        'available': True,
        'source_file': os.path.basename(p),
        'recorded_at': data.get('recorded_at'),
        'phase': data.get('phase'),
        # synthetic=True 表示快照不是 9:25 实盘窗口抓的，复盘时必须显式区分
        'synthetic': bool(data.get('synthetic')),
        'auction_boom': data.get('auction_boom'),
        'fake_high_opens': data.get('fake_high_opens'),
        'candidates': cands,
        'candidate_count': len(cands),
    }


def _sector_block(ymd):
    for days in (1, 5):
        p = os.path.join(sd.DATA_DIR, 'sector_flow_d%d_%s.json' % (days, ymd))
        data = _read_json(p)
        if data and (data.get('inflow') or data.get('outflow')):
            return {
                'available': True,
                'source': data.get('source'),
                'estimated': bool(data.get('estimated')),
                'days': data.get('days', days),
                'inflow': data.get('inflow') or [],
                'outflow': data.get('outflow') or [],
            }
    return {'available': False, 'reason': 'no_sector_flow_file'}


def _decision_block(ymd):
    fp = os.path.join(sd.DATA_DIR, 'strategy_decisions.jsonl')
    rows = []
    if os.path.exists(fp):
        with io.open(fp, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if isinstance(obj, dict) and str(obj.get('date')) == ymd:
                    rows.append(obj)
    if not rows:
        return {'available': False, 'reason': 'no_decision_record'}
    latest = rows[-1]
    return {
        'available': True,
        'source': 'strategy_decisions.jsonl',
        'records': len(rows),
        'latest': latest,
        'phase_keys': sorted({str(r.get('phase_key')) for r in rows if r.get('phase_key')}),
    }


def build_daily_archive(ymd, force=False):
    """
    生成单日归档。幂等：已存在且非 force -> skipped。
    返回 {'status': 'ok'|'skipped', 'date':..., 'path':..., 'gaps': [...]}
    """
    ymd = _clean_ymd(ymd)
    if not ymd:
        return {'status': 'error', 'message': '日期非法'}
    p = archive_path(ymd)
    if os.path.exists(p) and not force:
        return {'status': 'skipped', 'reason': 'archive_exists', 'date': ymd, 'path': p}

    now = dt.datetime.now()
    is_today = (ymd == now.strftime('%Y%m%d'))
    if is_today and now.hour < 15 and not force:
        return {'status': 'skipped', 'reason': 'intraday_not_final',
                'date': ymd, 'path': p}

    emotion = _emotion_block(ymd)
    ladder = _ladder_block(ymd)
    auction = _auction_block(ymd)
    sector = _sector_block(ymd)
    decision = _decision_block(ymd)

    gaps = [name for name, blk in (
        ('emotion', emotion), ('ladder', ladder), ('auction', auction),
        ('sector', sector), ('decision', decision),
    ) if not blk.get('available')]

    record = {
        'schema': SCHEMA,
        'date': ymd,
        'archived_at': now.strftime('%Y-%m-%d %H:%M:%S'),
        'immutable': True,
        'emotion': emotion,
        'ladder': ladder,
        'auction': auction,
        'sector': sector,
        'decision': decision,
        'gaps': gaps,
    }
    _atomic_write(p, record)
    return {'status': 'ok', 'date': ymd, 'path': p, 'gaps': gaps}


def archive_status(days=60, end_ymd=None):
    """
    连续性校验：列出最近 days 个交易日内尚未归档的日期。
    日历不可用时降级为 sentiment_history 的日期集合（并显式标注来源），
    绝不按自然日星期几冒充交易日。
    """
    end = _clean_ymd(end_ymd) or dt.date.today().strftime('%Y%m%d')
    start = (dt.datetime.strptime(end, '%Y%m%d') - dt.timedelta(days=int(days) * 2)).strftime('%Y%m%d')
    expected = tc.trading_days_between(start, end)
    cal_src = 'exchange_calendar'
    if not expected:
        cal_src = 'sentiment_history_offline'
        expected = sorted({str(r.get('date')) for r in _sentiment_records()
                           if start <= str(r.get('date')) <= end})
        expected = expected[-int(days):]

    existing = set()
    if os.path.isdir(ARCHIVE_DIR):
        for fn in os.listdir(ARCHIVE_DIR):
            if fn.endswith('.json') and len(fn) == 13:
                existing.add(fn[:8])

    missing = [d for d in expected if d not in existing]
    return {
        'calendar_source': cal_src,
        'calendar_available': cal_src == 'exchange_calendar',
        'days': int(days),
        'expected_count': len(expected),
        'archived_count': len([d for d in expected if d in existing]),
        'missing_count': len(missing),
        'missing_dates': missing,
        'latest_archived': max(existing) if existing else None,
        'archive_dir': ARCHIVE_DIR,
    }


def archive_range(from_ymd, to_ymd=None, force=False):
    """补档：在 [from, to] 内按真实交易日生成；日历不可用时逐自然日尝试并显式跳过无数据日"""
    start = _clean_ymd(from_ymd)
    end = _clean_ymd(to_ymd) or dt.date.today().strftime('%Y%m%d')
    if not start or not end or start > end:
        return {'status': 'error', 'message': '日期区间非法'}

    dates = tc.trading_days_between(start, end)
    cal_src = 'exchange_calendar'
    if not dates:
        cal_src = 'natural_day_fallback'
        cur = dt.datetime.strptime(start, '%Y%m%d')
        stop = dt.datetime.strptime(end, '%Y%m%d')
        dates = []
        while cur <= stop:
            if cur.weekday() < 5:
                dates.append(cur.strftime('%Y%m%d'))
            cur += dt.timedelta(days=1)

    results = {'status': 'ok', 'calendar_source': cal_src,
               'range': [start, end], 'dates': len(dates),
               'written': [], 'skipped': [], 'no_data': []}
    for ymd in dates:
        r = build_daily_archive(ymd, force=force)
        if r.get('status') == 'ok':
            results['written'].append(ymd)
        elif r.get('status') == 'skipped':
            results['skipped'].append({'date': ymd, 'reason': r.get('reason')})
            if r.get('reason') == 'intraday_not_final':
                continue
        if r.get('status') == 'skipped' and r.get('reason') == 'archive_exists':
            continue
        # 写成功但五块全缺 = 该日没有任何事实可归档
        if r.get('status') == 'ok' and len(r.get('gaps') or []) == 5:
            results['no_data'].append(ymd)
    return results


def main():
    ap = argparse.ArgumentParser(description='每日盘面事实归档 / 补档 / 连续性校验')
    ap.add_argument('--date', help='归档单日 YYYYMMDD')
    ap.add_argument('--from', dest='from_ymd', help='补档起始日 YYYYMMDD')
    ap.add_argument('--to', dest='to_ymd', help='补档结束日 YYYYMMDD（默认今天）')
    ap.add_argument('--force', action='store_true', help='已存在也重写（仅补档/回滚时用）')
    ap.add_argument('--status', action='store_true', help='只输出连续性状态')
    ap.add_argument('--days', type=int, default=60, help='status 的交易日窗口（默认 60）')
    args = ap.parse_args()

    if args.status:
        print(json.dumps(archive_status(days=args.days), ensure_ascii=False, indent=2))
    elif args.from_ymd:
        print(json.dumps(archive_range(args.from_ymd, args.to_ymd, force=args.force),
                         ensure_ascii=False, indent=2))
    else:
        ymd = _clean_ymd(args.date) or dt.date.today().strftime('%Y%m%d')
        print(json.dumps(build_daily_archive(ymd, force=args.force),
                         ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
