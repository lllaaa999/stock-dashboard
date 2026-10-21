#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
scripts/auction_audit.py — 早盘集合竞价推荐池收盘自动对账与打脸账本引擎

实战原则（吸纳寻龙诀/vibe-astock 实战闭环）：
1. 真实留痕：09:25 集合竞价雷达产出的推荐标的（弱转强、竞价抢筹、假高开预警）于盘前自动记录快照；
2. 严杜未来函数：以真实开盘价为买入基准，收盘价为结算基准，计算日内真实盈亏、封板率与大面率；
3. 双向对照验证：同时对账【弱转强推荐池】与【假高开诱多池】，用真实盘面事实检验第一步过滤规则的 Alpha 纯度；
4. 闭环落盘：生成单日对账不可变报告，并追加至全局 ledger.jsonl，供后续模型与策略持续反思迭代。
"""
import os
import sys
import json
import time
import datetime as dt
import pathlib

_HERE = pathlib.Path(__file__).resolve().parent
ROOT = _HERE.parent
sys.path.insert(0, str(_HERE))

import stock_dashboard as sd

AUCTION_RECORD_DIR = os.path.join(sd.DATA_DIR, 'auction_records')
os.makedirs(AUCTION_RECORD_DIR, exist_ok=True)
LEDGER_FILE = os.path.join(AUCTION_RECORD_DIR, 'auction_audit_ledger.jsonl')


def _candidates_file_path(ymd):
    clean_ymd = str(ymd).replace('-', '')[:8]
    return os.path.join(AUCTION_RECORD_DIR, f"auction_candidates_{clean_ymd}.json")


def _audit_file_path(ymd):
    clean_ymd = str(ymd).replace('-', '')[:8]
    return os.path.join(AUCTION_RECORD_DIR, f"auction_audit_{clean_ymd}.json")


def save_auction_candidates_snapshot(ymd, radar_result, force=False):
    """
    保存 09:25 竞价推荐池与监控快照。
    """
    if not ymd or not isinstance(radar_result, dict):
        return False, "数据无效"
    p = _candidates_file_path(ymd)
    if os.path.exists(p) and not force:
        return True, f"今日候选快照已存在: {p}"

    wts = radar_result.get('weak_to_strong') or []
    boom = radar_result.get('auction_boom') or []
    fakes = radar_result.get('fake_high_opens') or []

    payload = {
        'date': str(ymd).replace('-', '')[:8],
        'recorded_at': dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'weak_to_strong': wts,
        'auction_boom': boom,
        'fake_high_opens': fakes,
    }
    tmp_p = p + f".tmp.{os.getpid()}"
    try:
        with open(tmp_p, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_p, p)
        return True, f"成功保存竞价候选快照: {p}"
    except Exception as e:
        return False, f"保存竞价候选快照失败: {e}"


def get_auction_candidates(ymd):
    p = _candidates_file_path(ymd)
    if os.path.exists(p):
        try:
            with open(p, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
    return None


def _audit_single_group(items, zt_codes, zb_codes, ymd):
    """
    对一个股票池进行收盘对账核算。
    """
    if not items:
        return {
            'count': 0, 'zt_count': 0, 'zt_rate': 0.0,
            'zb_count': 0, 'zb_rate': 0.0, 'win_count': 0, 'win_rate': 0.0,
            'avg_open_to_close_pct': 0.0, 'avg_max_gain_pct': 0.0,
            'big_loss_count': 0, 'big_loss_rate': 0.0,
            'details': []
        }

    clean_items = []
    for it in items:
        code = str(it.get('code') or it.get('c') or '').strip().zfill(6)
        if code:
            clean_items.append({
                'code': code,
                'name': it.get('name') or it.get('n') or code,
                'open_pct': float(it.get('open_pct') or 0.0),
                'vol_ratio': float(it.get('vol_ratio') or 0.0),
                'amt_ratio_pct': float(it.get('amount_ratio_pct') or 0.0),
                'reason': it.get('reason') or '',
            })

    codes = [x['code'] for x in clean_items]
    # 批量获取真实行情
    full_codes = [('sh' if c.startswith(('6', '5', '9')) else 'sz') + c for c in codes]
    quotes = sd.tx_realtime(full_codes) if full_codes else []
    q_map = {q['code']: q for q in quotes if 'code' in q}

    details = []
    zt_c = 0
    zb_c = 0
    win_c = 0
    big_loss_c = 0
    pnl_sum = 0.0
    max_gain_sum = 0.0

    for it in clean_items:
        c = it['code']
        q = q_map.get(c, {})
        # 行情数据解析
        open_p = float(q.get('price', 0)) # 兜底
        # 尝试通过新浪日K获取今日准确开盘收盘(若 tx_realtime 字段平移)
        close_p = float(q.get('price') or 0)
        high_p = float(q.get('high') or close_p)
        low_p = float(q.get('low') or close_p)
        pct_today = float(q.get('pct') or 0)

        # 若有开盘价涨幅，倒推开盘价
        open_pct = it['open_pct']
        if close_p > 0 and (1.0 + pct_today / 100.0) != 0:
            yesterday_close = close_p / (1.0 + pct_today / 100.0)
            est_open_p = yesterday_close * (1.0 + open_pct / 100.0)
        else:
            est_open_p = close_p

        # 开盘买入到收盘的收益率
        if est_open_p > 0:
            open_to_close = round(((close_p - est_open_p) / est_open_p) * 100.0, 2)
            max_gain = round(((high_p - est_open_p) / est_open_p) * 100.0, 2)
        else:
            open_to_close = 0.0
            max_gain = 0.0

        is_zt = c in zt_codes
        is_zb = c in zb_codes
        is_win = (open_to_close > 0)
        is_big_loss = (open_to_close <= -5.0)

        if is_zt: zt_c += 1
        if is_zb: zb_c += 1
        if is_win: win_c += 1
        if is_big_loss: big_loss_c += 1
        pnl_sum += open_to_close
        max_gain_sum += max_gain

        details.append({
            'code': c,
            'name': it['name'],
            'open_pct': open_pct,
            'close_pct': pct_today,
            'open_to_close_pct': open_to_close,
            'max_gain_pct': max_gain,
            'is_zt': is_zt,
            'is_zb': is_zb,
            'is_win': is_win,
            'is_big_loss': is_big_loss,
            'vol_ratio': it['vol_ratio'],
            'amt_ratio_pct': it['amt_ratio_pct'],
            'reason': it['reason'],
        })

    n = len(clean_items)
    return {
        'count': n,
        'zt_count': zt_c,
        'zt_rate': round((zt_c / n) * 100.0, 1) if n > 0 else 0.0,
        'zb_count': zb_c,
        'zb_rate': round((zb_c / n) * 100.0, 1) if n > 0 else 0.0,
        'win_count': win_c,
        'win_rate': round((win_c / n) * 100.0, 1) if n > 0 else 0.0,
        'avg_open_to_close_pct': round(pnl_sum / n, 2) if n > 0 else 0.0,
        'avg_max_gain_pct': round(max_gain_sum / n, 2) if n > 0 else 0.0,
        'big_loss_count': big_loss_c,
        'big_loss_rate': round((big_loss_c / n) * 100.0, 1) if n > 0 else 0.0,
        'details': details
    }


def audit_auction_for_day(ymd, force=False):
    """
    收盘对账核心函数：消费今日盘面事实，核验今日竞价雷达推荐效果。
    """
    clean_ymd = str(ymd).replace('-', '')[:8]
    audit_file = _audit_file_path(clean_ymd)

    # 若已有且非强制，直接返回已对账结果
    if os.path.exists(audit_file) and not force:
        try:
            with open(audit_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass

    cand = get_auction_candidates(clean_ymd)
    if not cand:
        # 尝试从今日运行的竞价雷达中现场生成快照（用于盘后补录）
        try:
            import auction_radar as ar
            radar_res = ar.get_auction_radar()
            if radar_res and radar_res.get('status') == 'ok':
                save_auction_candidates_snapshot(clean_ymd, radar_res, force=True)
                cand = get_auction_candidates(clean_ymd)
        except Exception as e:
            print(f"[竞价对账] 尝试提取候选失败: {e}")

    if not cand:
        return {
            'status': 'no_candidates',
            'date': clean_ymd,
            'message': f"未找到交易日 {clean_ymd} 的竞价候选池快照"
        }

    # 提取收盘涨停池与炸板池真实事实
    zt_pool = sd._pool('ZT', clean_ymd) or []
    zb_pool = sd._pool('ZB', clean_ymd) or []
    zt_codes = {str(d.get('c', '')).strip().zfill(6) for d in zt_pool}
    zb_codes = {str(d.get('c', '')).strip().zfill(6) for d in zb_pool}

    wts_audit = _audit_single_group(cand.get('weak_to_strong', []), zt_codes, zb_codes, clean_ymd)
    boom_audit = _audit_single_group(cand.get('auction_boom', []), zt_codes, zb_codes, clean_ymd)
    fake_audit = _audit_single_group(cand.get('fake_high_opens', []), zt_codes, zb_codes, clean_ymd)

    audit_result = {
        'status': 'ok',
        'date': clean_ymd,
        'audited_at': dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'summary': {
            'weak_to_strong': {
                'count': wts_audit['count'],
                'zt_rate': wts_audit['zt_rate'],
                'win_rate': wts_audit['win_rate'],
                'avg_pnl': wts_audit['avg_open_to_close_pct'],
                'big_loss_rate': wts_audit['big_loss_rate'],
            },
            'auction_boom': {
                'count': boom_audit['count'],
                'zt_rate': boom_audit['zt_rate'],
                'win_rate': boom_audit['win_rate'],
                'avg_pnl': boom_audit['avg_open_to_close_pct'],
            },
            'fake_high_opens_control': {
                'count': fake_audit['count'],
                'zt_rate': fake_audit['zt_rate'],
                'win_rate': fake_audit['win_rate'],
                'avg_pnl': fake_audit['avg_open_to_close_pct'],
                'big_loss_rate': fake_audit['big_loss_rate'],
            }
        },
        'weak_to_strong': wts_audit,
        'auction_boom': boom_audit,
        'fake_high_opens': fake_audit,
    }

    # 持久化当日对账文件
    tmp_f = audit_file + f".tmp.{os.getpid()}"
    try:
        with open(tmp_f, 'w', encoding='utf-8') as f:
            json.dump(audit_result, f, ensure_ascii=False, indent=2)
        os.replace(tmp_f, audit_file)
    except Exception as e:
        print(f"[竞价对账] 保存单日对账文件失败: {e}")

    # 追加/更新至全局 ledger
    try:
        _upsert_ledger(clean_ymd, audit_result)
    except Exception as e:
        print(f"[竞价对账] 写入打脸账本失败: {e}")

    return audit_result


def _upsert_ledger(ymd, audit_result):
    lines = []
    if os.path.exists(LEDGER_FILE):
        with open(LEDGER_FILE, 'r', encoding='utf-8') as f:
            for l in f:
                l = l.strip()
                if l:
                    try:
                        row = json.loads(l)
                        if row.get('date') != ymd:
                            lines.append(row)
                    except Exception:
                        pass

    entry = {
        'date': ymd,
        'audited_at': audit_result.get('audited_at'),
        'wts_count': audit_result['summary']['weak_to_strong']['count'],
        'wts_zt_rate': audit_result['summary']['weak_to_strong']['zt_rate'],
        'wts_win_rate': audit_result['summary']['weak_to_strong']['win_rate'],
        'wts_avg_pnl': audit_result['summary']['weak_to_strong']['avg_pnl'],
        'wts_big_loss_rate': audit_result['summary']['weak_to_strong']['big_loss_rate'],
        'fake_count': audit_result['summary']['fake_high_opens_control']['count'],
        'fake_avg_pnl': audit_result['summary']['fake_high_opens_control']['avg_pnl'],
        'fake_big_loss_rate': audit_result['summary']['fake_high_opens_control']['big_loss_rate'],
    }
    lines.append(entry)
    lines.sort(key=lambda x: str(x.get('date', '')))

    tmp_ledger = LEDGER_FILE + f".tmp.{os.getpid()}"
    with open(tmp_ledger, 'w', encoding='utf-8') as f:
        for r in lines:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    os.replace(tmp_ledger, LEDGER_FILE)


def get_auction_audit_ledger(limit=30):
    """读取对账总账本与统计指标。"""
    records = []
    if os.path.exists(LEDGER_FILE):
        with open(LEDGER_FILE, 'r', encoding='utf-8') as f:
            for l in f:
                l = l.strip()
                if l:
                    try:
                        records.append(json.loads(l))
                    except Exception:
                        pass
    records.sort(key=lambda x: str(x.get('date', '')))
    sliced = records[-limit:] if limit else records

    # 计算累计整体表现
    total_wts = sum(r.get('wts_count', 0) for r in records)
    if total_wts > 0:
        cum_win_rate = round(sum(r.get('wts_win_rate', 0) * r.get('wts_count', 0) for r in records) / total_wts, 1)
        cum_zt_rate = round(sum(r.get('wts_zt_rate', 0) * r.get('wts_count', 0) for r in records) / total_wts, 1)
        cum_avg_pnl = round(sum(r.get('wts_avg_pnl', 0) * r.get('wts_count', 0) for r in records) / total_wts, 2)
    else:
        cum_win_rate, cum_zt_rate, cum_avg_pnl = 0.0, 0.0, 0.0

    return {
        'records': sliced,
        'total_days': len(records),
        'total_wts_stocks': total_wts,
        'cum_win_rate': cum_win_rate,
        'cum_zt_rate': cum_zt_rate,
        'cum_avg_pnl': cum_avg_pnl,
    }


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='早盘竞价雷达收盘自动对账工具')
    parser.add_argument('--date', type=str, default=dt.date.today().strftime('%Y%m%d'), help='对账日期 (YYYYMMDD)')
    parser.add_argument('--force', action='store_true', help='强制重新对账')
    args = parser.parse_args()

    print(f"[竞价对账] 开始处理日期: {args.date}...")
    res = audit_auction_for_day(args.date, force=args.force)
    print(json.dumps(res.get('summary', res), ensure_ascii=False, indent=2))
