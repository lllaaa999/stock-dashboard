# -*- coding: utf-8 -*-
"""sim_score.py — 次日打脸账本（2026-09-30 新增 · 消息面→推演 第 ④ 步）

把当天 LLM 推演（data/llm/sim-YYYY-MM-DD.json）与**次一交易日**的真实结果对账，逐条打分并累计：

  ① 方向命中：预测加权合力符号（|net_pct|<5 记中性）vs 次日上证涨跌 + 情绪分变化
  ② 强度命中：预测的多轮定性（强/中/弱）vs 次日情绪分变动 + 涨停数变动
  ③ 板块命中：预测板块优先级 Top3（看多）有多少进入次日涨停池行业 Top10（按家数）
  ④ 情景归位：按规则判定次日实际落入 乐观/中性/悲观 哪一档（三档都写出来了，但模型没给概率，
     所以只做"归位"不做"押中率"打分 —— 要能押注需让模型输出三档概率，见 --hint）
  ⑤ 风险点命中：可自动验证的关键词（炸板/跌停/缩量/特停）逐条核对；不可验证的标"未验证"

输出：data/llm/score-YYYY-MM-DD.json + 追加 data/llm/ledger.jsonl（含累计命中率）

用法：
  python scripts/sim_score.py                 # 给所有"还没打过分"的推演补记分
  python scripts/sim_score.py --date 2026-09-30
  python scripts/sim_score.py --all           # 全部重算
设计：**记分核心 score_one(pred, facts) 是纯函数**（事实由 gather 出来传进去），便于离线单测。
"""
import argparse
import collections
import datetime as dt
import json
import os
import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import stock_dashboard as sd  # noqa: E402

ROOT = _HERE.parent
DATA_DIR = ROOT / 'data'
LLM_DIR = DATA_DIR / 'llm'
SENT_PATH = pathlib.Path(sd.DATA_DIR) / 'sentiment_history.jsonl'
LEDGER = LLM_DIR / 'ledger.jsonl'

w = sd.w


# ==================== 取数 ====================
def _sent_records():
    if not SENT_PATH.exists():
        return []
    out = []
    for line in SENT_PATH.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return sorted(out, key=lambda r: str(r.get('date', '')))


def next_trade_date(date_str):
    """获取次一有效交易日。优先以交易所真实日K为唯一事实源，防止假期休市记录被误判。"""
    ymd = date_str.replace('-', '')
    try:
        kl = sd.kline_tx('sh000001', 90)
        k_dates = [str(r[0])[:10].replace('-', '') for r in kl]
        for kd in k_dates:
            if kd > ymd:
                return kd
    except Exception:
        pass
    # 兜底：若日K未返回，遍历情绪存档，但必须有真实指数涨跌幅校验
    for r in _sent_records():
        d = str(r.get('date', ''))
        if d > ymd and _index_pct(d) is not None:
            return d
    return None


def _index_pct(ymd):
    """上证指数该日涨跌幅（用日K算，历史可查）"""
    try:
        kl = sd.kline_tx('sh000001', 60)
        want = f'{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}'
        for i, row in enumerate(kl):
            if str(row[0])[:10] == want and i > 0:
                prev = float(kl[i - 1][2])
                return round((float(row[2]) - prev) / prev * 100, 2) if prev else None
    except Exception as e:
        w(f'[对账] 指数取数失败: {e}')
    return None


def gather_facts(next_ymd):
    """次一交易日的真实事实（指数涨跌 / 情绪分 / 涨停·炸板·跌停·最高板 / 涨停池行业分布）"""
    facts = {'date': next_ymd, 'index_pct': _index_pct(next_ymd)}
    rec = None
    for r in _sent_records():
        if str(r.get('date')) == next_ymd:
            rec = r
    prev = None
    recs = [r for r in _sent_records() if str(r.get('date')) <= next_ymd]
    if len(recs) >= 2:
        prev = recs[-2]
    if rec:
        for k in ('score', 'score_v1', 'zt', 'zb', 'dt', 'max_lb'):
            if k in rec:
                facts[k] = rec[k]
        if prev and prev.get('date') != rec.get('date'):
            facts['prev'] = {k: prev.get(k) for k in ('date', 'score', 'zt', 'zb', 'dt', 'max_lb')}
    try:
        pool = sd._pool('ZT', next_ymd) or []
        facts['zt_industries'] = dict(collections.Counter(str(x.get('hybk') or '') for x in pool if x.get('hybk')))
        facts['zt_count_pool'] = len(pool)
    except Exception as e:
        w(f'[对账] 涨停池取数失败: {e}')
        facts['zt_industries'] = {}
    return facts


# ==================== 记分核心（纯函数） ====================
def score_direction(pred_net_pct, facts):
    """方向：预测偏多/偏空/中性 vs 次日上证涨跌 + 情绪分变化"""
    idx = facts.get('index_pct')
    dscore = None
    prev = facts.get('prev') or {}
    if facts.get('score') is not None and prev.get('score') is not None:
        try:
            dscore = round(float(facts['score']) - float(prev['score']), 2)
        except Exception:
            dscore = None
    if idx is None and dscore is None:
        return {'hit': None, 'reason': '次日指数与情绪分都缺，无法判定'}
    pred = '偏多' if pred_net_pct > 5 else ('偏空' if pred_net_pct < -5 else '中性')
    votes = []
    if idx is not None:
        votes.append('偏多' if idx > 0.5 else ('偏空' if idx < -0.5 else '中性'))
    if dscore is not None:
        votes.append('偏多' if dscore > 2 else ('偏空' if dscore < -2 else '中性'))
    realized = collections.Counter(votes).most_common(1)[0][0]
    return {'hit': pred == realized, 'pred': pred, 'realized': realized,
            'index_pct': idx, 'score_delta': dscore,
            'reason': f"预测{pred} vs 实际{realized}（指数{idx}% / 情绪分{dscore:+}）" if dscore is not None
                      else f"预测{pred} vs 实际{realized}（指数{idx}%）"}


def score_strength(pred_net_pct, facts):
    """强度：|net_pct| 分档 vs 次日实际波动（情绪分变动 + 涨停数变动）"""
    prev = facts.get('prev') or {}
    dscore = dzt = None
    try:
        dscore = abs(float(facts['score']) - float(prev['score']))
    except Exception:
        pass
    try:
        dzt = abs(float(facts['zt']) - float(prev['zt']))
    except Exception:
        pass
    if dscore is None and dzt is None:
        return {'hit': None, 'reason': '次日情绪/涨停数据缺失'}
    pred = '强' if abs(pred_net_pct) >= 20 else ('中' if abs(pred_net_pct) >= 8 else '弱')
    if dscore is not None:
        realized = '强' if dscore >= 6 else ('中' if dscore >= 2.5 else '弱')
    else:
        realized = '强' if dzt >= 15 else ('中' if dzt >= 6 else '弱')
    return {'hit': pred == realized, 'pred': pred, 'realized': realized,
            'score_delta_abs': dscore, 'zt_delta_abs': dzt,
            'reason': f'预测强度{pred} vs 实际{realized}（情绪分变动{dscore} / 涨停数变动{dzt}）'}


def score_sectors(pred_top, facts, topn=3):
    """板块：预测看多 Top-N 有多少进入次日涨停池行业 Top10（按家数）"""
    inds = facts.get('zt_industries') or {}
    if not inds:
        return {'hit': None, 'reason': '次日涨停池行业分布缺失'}
    ranked = [k for k, _v in sorted(inds.items(), key=lambda kv: -kv[1])[:10]]
    want = [t.get('sector', '') for t in pred_top if (t.get('polarity') or 0) > 0][:topn]
    if not want:
        return {'hit': None, 'reason': '预测里没有看多板块'}
    hit = [s for s in want if any(s and (s in r or r in s) for r in ranked)]
    rate = round(len(hit) / len(want) * 100, 1)
    return {'hit': rate >= 50, 'pred': want, 'realized_top10': ranked, 'matched': hit,
            'hit_rate_pct': rate, 'reason': f"预测 {want} → 次日涨停池Top10 {ranked}，命中 {hit}（{rate}%）"}


def score_scenario(pred_scenarios, facts):
    """情景归位：按规则判定次日实际落入哪一档（乐观/中性/悲观）"""
    idx = facts.get('index_pct')
    prev = facts.get('prev') or {}
    dscore = None
    try:
        dscore = float(facts['score']) - float(prev['score'])
    except Exception:
        pass
    zb_rate = None
    try:
        zb, zt = float(facts.get('zb') or 0), float(facts.get('zt') or 0)
        zb_rate = zb / max(zt + zb, 1) * 100
    except Exception:
        pass
    if idx is None and dscore is None and zb_rate is None:
        return {'hit': None, 'reason': '次日数据不足，无法归位'}
    if (idx is not None and idx >= 0.5) and (dscore is None or dscore >= -2) and (zb_rate is None or zb_rate <= 30):
        realized = '乐观'
    elif (idx is not None and idx <= -0.5) or (dscore is not None and dscore <= -5) or (zb_rate is not None and zb_rate > 35):
        realized = '悲观'
    else:
        realized = '中性'
    return {'hit': True, 'realized': realized, 'zb_rate_pct': round(zb_rate, 1) if zb_rate is not None else None,
            'index_pct': idx, 'score_delta': dscore,
            'reason': f"实际落入【{realized}】（指数{idx}% / 情绪分变动{dscore} / 炸板率{round(zb_rate, 1) if zb_rate is not None else None}%）"}


# (关键词, 判定函数, 说明, 是否可自动验证) —— 可验证的优先，避免"特停"这类不可验证词盖住"高位"
RISK_RULES = [
    ('炸板', lambda f: (float(f.get('zb') or 0) / max(float(f.get('zt') or 0) + float(f.get('zb') or 0), 1) * 100) > 30,
     '次日炸板率 >30%', True),
    ('跌停', lambda f: (float(f.get('dt') or 0) > float((f.get('prev') or {}).get('dt') or 0)), '次日跌停数增加', True),
    ('高位', lambda f: (float(f.get('max_lb') or 0) <= float((f.get('prev') or {}).get('max_lb') or 0)),
     '次日最高板未抬高（高度走弱）', True),
    ('缩量', lambda f: False, '需成交额序列（暂不可自动验证）', False),
    ('特停', lambda f: False, '监管特停无法自动验证', False),
    ('监管', lambda f: False, '监管动作无法自动验证', False),
]


def score_risks(risks, facts):
    """风险点核对：命中多条规则时**优先采用可自动验证的那条**，都不可验证才标"未验证"。"""
    out = []
    for r in (risks or []):
        item = str(r.get('item', ''))
        matches = [(kw, fn, desc, ver) for kw, fn, desc, ver in RISK_RULES if kw in item]
        usable = [m for m in matches if m[3]]
        pick = usable[0] if usable else (matches[0] if matches else None)
        verdict, note = '未验证', ''
        if pick:
            note = pick[2]
            if pick[3]:
                try:
                    verdict = '命中' if pick[1](facts) else '未发生'
                except Exception:
                    verdict = '未验证'
        out.append({'item': item, 'reason': r.get('reason', ''), 'verdict': verdict, 'check': note})
    return out


def score_one(pred, facts):
    # 跨期衰减适配: 优先采用经时间衰减折现后的合力刻度，使长假/跨周末对账客观公允
    net_pct = pred.get('decayed_net_pct') if pred.get('decayed_net_pct') is not None else pred.get('net_pct')
    if net_pct is None:
        return {'ok': False, 'reason': '预测里没有 net_pct / decayed_net_pct'}
    res = {
        'ok': True, 'pred_date': pred.get('date'), 'next_date': facts.get('date'),
        'model': pred.get('model'), 'seed_sha': pred.get('seed_sha'),
        'pred_net': pred.get('decayed_net', pred.get('net')),
        'pred_net_pct': net_pct,
        'raw_net_pct': pred.get('net_pct'),
        'time_decay': pred.get('time_decay', 1.0),
        'direction': score_direction(net_pct, facts),
        'strength': score_strength(net_pct, facts),
        'sectors': score_sectors(pred.get('theme_priority') or [], facts),
        'scenario': score_scenario(pred.get('scenarios') or {}, facts),
        'risks': score_risks(pred.get('risk_points') or [], facts),
        'facts': {k: v for k, v in facts.items() if k != 'zt_industries'},
    }
    return res


# ==================== 主流程 ====================
def predictions():
    if not LLM_DIR.exists():
        return []
    return sorted(p for p in LLM_DIR.glob('sim-*.json'))


def already_scored(date_str, next_ymd=None):
    """是否已记分。传入 next_ymd 时还要求"记的次日就是当前算出的次日"——
    这样陈旧样本（例如当初误用假期日 20261001 当次日算出来的那条）不会挡住重算，自动自愈。"""
    if not LEDGER.exists():
        return False
    for line in LEDGER.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get('pred_date') == date_str:
            return True if next_ymd is None else (r.get('next_date') == next_ymd)
    return False


def ledger_upsert(rec):
    """按 pred_date 覆盖写入（同一笔预测重算即替换, 不再重复追加/累计虚高）"""
    rows = []
    if LEDGER.exists():
        for line in LEDGER.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get('pred_date') != rec.get('pred_date'):
                rows.append(r)
    rows.append(rec)
    rows.sort(key=lambda r: (str(r.get('pred_date', '')), str(r.get('next_date', ''))))
    LLM_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = LEDGER.with_suffix('.tmp')
    tmp_path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')
    os.replace(tmp_path, LEDGER)
    return len(rows)


def ledger_stats():
    if not LEDGER.exists():
        return {}
    rows = []
    for line in LEDGER.read_text(encoding='utf-8').splitlines():
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    n = len(rows)
    if not n:
        return {}
    dir_hits = [r['direction']['hit'] for r in rows if r.get('direction', {}).get('hit') is not None]
    sec_rates = [r['sectors']['hit_rate_pct'] for r in rows if r.get('sectors', {}).get('hit_rate_pct') is not None]
    str_hits = [r['strength']['hit'] for r in rows if r.get('strength', {}).get('hit') is not None]
    return {
        'samples': n,
        'direction_hit_pct': round(sum(1 for x in dir_hits if x) / len(dir_hits) * 100, 1) if dir_hits else None,
        'strength_hit_pct': round(sum(1 for x in str_hits if x) / len(str_hits) * 100, 1) if str_hits else None,
        'sector_avg_hit_pct': round(sum(sec_rates) / len(sec_rates), 1) if sec_rates else None,
        'scenario_dist': dict(collections.Counter(r['scenario'].get('realized') for r in rows
                                                  if r.get('scenario', {}).get('realized'))),
    }


def run(date=None, all_=False, quiet=False):
    LLM_DIR.mkdir(parents=True, exist_ok=True)
    todo = []
    for p in predictions():
        d = p.stem.replace('sim-', '')
        if date and d != date:
            continue
        nxt_pre = next_trade_date(d)          # 先算出"当前应记的次日", 用来识别陈旧样本
        if not all_ and already_scored(d, nxt_pre):
            continue
        todo.append((d, p))
    if not todo:
        w('[对账] 没有待记分的推演（用 --all 重算，或先跑 sim_llm.py）')
        return []
    results = []
    for d, path in todo:
        pred = json.loads(path.read_text(encoding='utf-8'))
        nxt = next_trade_date(d)
        if not nxt:
            w(f"[对账] {d} 的次日数据还没归档（未收盘或休市）→ 跳过")
            results.append({'ok': False, 'pred_date': d, 'reason': 'next_day_missing'})
            continue
        facts = gather_facts(nxt)
        res = score_one(pred, facts)
        res['pred_date'] = d
        res['next_date'] = facts.get('date')
        (LLM_DIR / f'score-{d}.json').write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding='utf-8')
        if res.get('ok'):
            ledger_upsert({'pred_date': d, 'next_date': res['next_date'],
                           'direction': res['direction'], 'strength': res['strength'],
                           'sectors': res['sectors'], 'scenario': res['scenario'],
                           'risks': res['risks']})
        results.append(res)
    if not quiet:
        print_report(results)
    return results


def print_report(results):
    w('')
    w('=' * 78)
    w('次日打脸账本（预测 vs 实际）')
    w('=' * 78)
    for r in results:
        if not r.get('ok'):
            w(f"  {r.get('pred_date')}: 未记分（{r.get('reason')}）")
            continue
        w(f"  {r['pred_date']} → {r['next_date']}  预测合力 {r['pred_net']}（刻度 {r['pred_net_pct']}）")
        w(f"    方向: {'✅' if r['direction'].get('hit') else '❌'} {r['direction'].get('reason')}")
        w(f"    强度: {'✅' if r['strength'].get('hit') else '❌'} {r['strength'].get('reason')}")
        w(f"    板块: {'✅' if r['sectors'].get('hit') else '❌'} {r['sectors'].get('reason')}")
        w(f"    情景: {r['scenario'].get('reason')}")
        for rk in r.get('risks', []):
            w(f"    风险[{rk['verdict']}] {rk['item'][:24]} —— {rk.get('check') or '无自动核对规则'}")
    st = ledger_stats()
    if st:
        w('')
        w(f"累计样本 {st['samples']} 条 | 方向命中 {st['direction_hit_pct']}% | "
          f"强度命中 {st['strength_hit_pct']}% | 板块平均命中 {st['sector_avg_hit_pct']}% | "
          f"情景分布 {st['scenario_dist']}")
        w('（样本 <10 时这些百分比意义有限；模型目前没输出三档概率，所以情景只做"归位"不做"押中率"）')


def main():
    ap = argparse.ArgumentParser(description='次日打脸账本：把 LLM 推演与次日真实结果对账')
    ap.add_argument('--date', default=None, help='只记某个预测日 YYYY-MM-DD')
    ap.add_argument('--all', action='store_true', help='全部重算（含已记分的）')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    res = run(date=a.date, all_=a.all)
    if a.json:
        print(json.dumps(res, ensure_ascii=False))
    if not res:
        raise SystemExit(0)


if __name__ == '__main__':
    main()