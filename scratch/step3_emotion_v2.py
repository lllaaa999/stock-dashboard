# -*- coding: utf-8 -*-
"""Step3: 情绪分升级(v2) —— 去饱和 + 新增"赚钱效应"项 + 背离标记 + 尺度隔离

依据(见 SKILL.md 收口更新): 国泰海通《从涨停板、打板策略到赚钱效应引发的情绪择时指标》(2025-05)
把"打板收益(涨停股次日平均收益, 缩尾)"列为因子; 复盘体系口径: 正向环境 = 连板晋级率>50% 且
昨日涨停平均溢价>3%。原公式 min(zt/80,1)*30 在 80 家以上饱和(80 家与 150 家同分)且完全没有
赚钱效应项 —— 2026-09-30 实测 61.1 分与"接力偏弱(1进2 仅 12.8%)"背离。

本脚本用"精确字符串替换 + 命中计数断言"改 7 处, 任一断言失败即整体不落盘。
"""
import pathlib
import sys

ROOT = pathlib.Path(r"D:\股票看盘")
SD = ROOT / "scripts" / "stock_dashboard.py"
HTML = ROOT / "web" / "templates" / "index.html"

HELPERS = '''# ---------- 情绪指数打分: v1(对照留档) / v2(去饱和+赚钱效应) ----------
def _emotion_band(s):
    return ('冰点' if s < 30 else '退潮/偏冷' if s < 50 else '中性' if s < 70 else '活跃' if s < 85 else '亢奋')

def _emotion_score_v1(n_zt, n_zb, n_dt, max_lb):
    """旧公式(0-100): 基准10 + 广度30 + 高度25 + 封板质量20 - 跌停惩罚15。仅作对照留档。"""
    s = 10
    s += min(n_zt / 80, 1) * 30
    s += min(max_lb / 8, 1) * 25
    s += (1 - n_zb / (n_zt + n_zb)) * 20 if (n_zt + n_zb) else 10
    s -= min(n_dt / 15, 1) * 15
    return max(0, min(100, s))

def _emotion_score_v2(n_zt, n_zb, n_dt, max_lb, eff):
    """新公式(0-100): 基准10 + 广度18(平方根去饱和) + 高度17(平方根) + 封板质量12
    + 赚钱效应25 + 跌停惩罚15。
    赚钱效应 = 0.6*溢价分 + 0.4*晋级分; 溢价分 = clamp(昨日涨停今均涨跌, -5%, +5%) 归一化;
    晋级分 = min(1进2晋级率/50, 1)。取不到该指标时按中性 12.5 分计入(并标注).
    返回 (score, diverge)。diverge: score_high_effect_weak / score_low_effect_strong / None
    """
    s = 10
    s += math.sqrt(min(n_zt / 120, 1)) * 18
    s += math.sqrt(min(max_lb / 8, 1)) * 17
    s += ((1 - n_zb / (n_zt + n_zb)) * 12 if (n_zt + n_zb) else 6)
    s += (eff['score'] * 25) if eff.get('available') else 12.5
    s -= min(n_dt / 15, 1) * 15
    s = max(0, min(100, s))
    diverge = None
    if eff.get('available'):
        prem = float(eff.get('premium', 0.0))
        rate = float(eff.get('rate_1to2', 0.0))
        if s >= 50 and (prem < 0 or rate < 25):
            diverge = 'score_high_effect_weak'
        elif s < 50 and prem > 3 and rate > 50:
            diverge = 'score_low_effect_strong'
    return s, diverge

def _effect_flat(eff):
    """存档用扁平化(不写嵌套, 便于日后回测)"""
    if not eff.get('available'):
        return None
    return dict(premium=eff.get('premium'), rate_1to2=eff.get('rate_1to2'),
                effect_score=round(eff.get('score', 0) * 25, 2),
                y_date=eff.get('y_date'), tag=eff.get('tag'))

_EFFECT_CACHE = {'t': 0.0, 'data': None}

def _effect_metrics(ttl=300.0):
    """赚钱效应指标: 复用竞价雷达(premium_summary / promotion_metrics), 结果缓存 ttl 秒。
    竞价雷达单次约 6s, 缓存避免 web 每次刷新都付这个代价。"""
    now = time.time()
    if _EFFECT_CACHE['data'] is not None and (now - _EFFECT_CACHE['t']) < ttl:
        return _EFFECT_CACHE['data']
    out = {'available': False, 'reason': 'unavailable'}
    try:
        import auction_radar as _ar          # 同目录; 延迟导入避免与 auction_radar->stock_dashboard 的循环
        r = _ar.get_auction_radar() or {}
        ps = r.get('premium_summary') or {}
        pm = r.get('promotion_metrics') or {}
        prem, rate = ps.get('avg_curr_pct'), pm.get('rate_1to2')
        if r.get('status') == 'ok' and prem is not None and rate is not None:
            prem_c = max(-5.0, min(5.0, float(prem)))
            prem_n = (prem_c + 5.0) / 10.0
            rate_n = min(float(rate) / 50.0, 1.0)
            out = {'available': True, 'premium': round(float(prem), 2),
                   'premium_clamped': round(prem_c, 2), 'rate_1to2': round(float(rate), 1),
                   'premium_norm': round(prem_n, 3), 'rate_norm': round(rate_n, 3),
                   'score': round(0.6 * prem_n + 0.4 * rate_n, 4),
                   'y_date': ps.get('y_date'), 'tag': ps.get('sentiment_tag')}
        else:
            out = {'available': False,
                   'reason': 'radar status=%s prem=%s rate=%s' % (r.get('status'), prem, rate)}
    except Exception as e:
        out = {'available': False, 'reason': repr(e)[:120]}
    _EFFECT_CACHE.update({'t': now, 'data': out})
    return out


'''

EDITS = []  # (file, old, new, label)

# --- 1. imports ---
EDITS.append((SD, "import sys, os, json, re, ssl, urllib.request, datetime as dt",
              "import sys, os, json, re, ssl, time, math, urllib.request, datetime as dt",
              "imports(+time,+math)"))

# --- 2. 插入打分函数(在 emotion 之前) ---
EDITS.append((SD, "def emotion(ymd=None):", HELPERS + "def emotion(ymd=None):", "insert score helpers"))

# --- 3. 打分块替换 ---
OLD_SCORE = """        n_zt, n_zb, n_dt = len(zt), len(zb), len(dtl)
        max_lb = max([d.get('lbc', 1) for d in zt], default=0)
        br = n_zb / (n_zt + n_zb) * 100 if (n_zt + n_zb) else 0
        s = 10
        s += min(n_zt / 80, 1) * 30
        s += min(max_lb / 8, 1) * 25
        s += (1 - n_zb / (n_zt + n_zb)) * 20 if (n_zt + n_zb) else 10
        s -= min(n_dt / 15, 1) * 15
        s = max(0, min(100, s))
        band = ('冰点' if s < 30 else '退潮/偏冷' if s < 50 else '中性' if s < 70 else '活跃' if s < 85 else '亢奋')
        w(f'日期:{ymd}  涨停:{n_zt} 炸板:{n_zb}(率{br:.0f}%) 跌停:{n_dt} 最高连板:{max_lb}板')
        w(f'>>> 情绪指数: {s:.2f}/100 [{band}] <<<')"""
NEW_SCORE = """        n_zt, n_zb, n_dt = len(zt), len(zb), len(dtl)
        max_lb = max([d.get('lbc', 1) for d in zt], default=0)
        br = n_zb / (n_zt + n_zb) * 100 if (n_zt + n_zb) else 0
        eff = _effect_metrics()
        s_v1 = _emotion_score_v1(n_zt, n_zb, n_dt, max_lb)
        s, diverge = _emotion_score_v2(n_zt, n_zb, n_dt, max_lb, eff)
        band = _emotion_band(s)
        w(f'日期:{ymd}  涨停:{n_zt} 炸板:{n_zb}(率{br:.0f}%) 跌停:{n_dt} 最高连板:{max_lb}板')
        w(f'>>> 情绪指数: {s:.2f}/100 [{band}] <<<   (v1 公式对照: {s_v1:.2f})')
        if eff.get('available'):
            w('赚钱效应: 昨日涨停今均溢价 %+.2f%% | 1进2晋级率 %.1f%% | 昨日=%s [%s]' % (
                eff['premium'], eff['rate_1to2'], eff.get('y_date') or '', eff.get('tag') or ''))
        else:
            w('赚钱效应: 取不到(%s) -> 该项按中性 12.5 分计入, 已标注 effect_unavailable' % eff.get('reason'))
        if diverge == 'score_high_effect_weak':
            w('!! 背离: 情绪分偏高但赚钱效应偏弱 —— 广度/高度在装没事, 接力资金不认账')
        elif diverge == 'score_low_effect_strong':
            w('** 背离: 情绪分偏低但赚钱效应转强 —— 冰点试错窗口(负溢价收敛/晋级率回升)')"""
EDITS.append((SD, OLD_SCORE, NEW_SCORE, "scoring block"))

# --- 4. 盘中提前返回 ---
EDITS.append((SD, """            return dict(score=s, band=band, zt=n_zt, zb=n_zb, dt=n_dt, max_lb=max_lb, ymd=ymd,
                         first_boards=first_boards, ladder_grouped=ladder_grouped,
                         limit_down=limit_down, themes_list=themes_list, promotion=promotion,
                         board_quality=board_quality, zha_ban=zha_ban)""",
              """            return dict(score=s, band=band, zt=n_zt, zb=n_zb, dt=n_dt, max_lb=max_lb, ymd=ymd,
                         first_boards=first_boards, ladder_grouped=ladder_grouped,
                         limit_down=limit_down, themes_list=themes_list, promotion=promotion,
                         board_quality=board_quality, zha_ban=zha_ban, algo='v2',
                         score_v1=round(s_v1, 2), effect=_effect_flat(eff), diverge=diverge,
                         effect_available=eff.get('available'))""",
              "intraday return"))

# --- 5. 归档写入 ---
EDITS.append((SD, """                fp.write(json.dumps(dict(date=ymd, score=round(s, 2), band=band, zt=n_zt,
                                         zb=n_zb, dt=n_dt, max_lb=max_lb), ensure_ascii=False) + '\\n')""",
              """                fp.write(json.dumps(dict(date=ymd, score=round(s, 2), band=band, zt=n_zt,
                                         zb=n_zb, dt=n_dt, max_lb=max_lb, algo='v2',
                                         score_v1=round(s_v1, 2), effect=_effect_flat(eff),
                                         diverge=diverge), ensure_ascii=False) + '\\n')""",
              "archive write"))

# --- 6. 收盘返回 ---
EDITS.append((SD, """        return dict(score=s, band=band, zt=n_zt, zb=n_zb, dt=n_dt, max_lb=max_lb, ymd=ymd,
                     first_boards=first_boards, ladder_grouped=ladder_grouped,
                     limit_down=limit_down, themes_list=themes_list, promotion=promotion,
                     board_quality=board_quality, zha_ban=zha_ban)""",
              """        return dict(score=s, band=band, zt=n_zt, zb=n_zb, dt=n_dt, max_lb=max_lb, ymd=ymd,
                     first_boards=first_boards, ladder_grouped=ladder_grouped,
                     limit_down=limit_down, themes_list=themes_list, promotion=promotion,
                     board_quality=board_quality, zha_ban=zha_ban, algo='v2',
                     score_v1=round(s_v1, 2), effect=_effect_flat(eff), diverge=diverge,
                     effect_available=eff.get('available'))""",
              "final return"))

# --- 7. 周期定位: 尺度隔离 ---
EDITS.append((SD, "    stage, meta = _cycle_stage(recs, prev)",
              """    # algo 尺度隔离: v2 与 v1 的分数不可混算 MA3/MA7(2026-09-30 起)
    _cur_algo = recs[-1].get('algo', 'v1')
    recs_same = [r for r in recs if r.get('algo', 'v1') == _cur_algo]
    if len(recs_same) < len(recs):
        w('(注: 存档含 %d 条旧尺度(v1)记录, 本次定位只用同尺度 %d 条)' % (
            len(recs) - len(recs_same), len(recs_same)))
    stage, meta = _cycle_stage(recs_same, prev)""",
              "cycle algo isolation"))

EDITS.append((SD, """    n = len(recs)
    s_ = [float(r.get('score', 50)) for r in recs]
    lbs = [int(r.get('max_lb', 0)) for r in recs]
    zts = [float(r.get('zt', 0)) for r in recs]
    sc = s_[-1]""",
              """    n = len(recs_same)
    s_ = [float(r.get('score', 50)) for r in recs_same]
    lbs = [int(r.get('max_lb', 0)) for r in recs_same]
    zts = [float(r.get('zt', 0)) for r in recs_same]
    sc = s_[-1]""",
              "cycle MA same-algo"))

EDITS.append((SD, "    for r in recs[-10:]:", "    for r in recs_same[-10:]:", "cycle display same-algo"))

# --- 8. 前端: 赚钱效应 + 背离 ---
EDITS.append((HTML, """  document.getElementById('emoMetrics').innerHTML = `
    <div class="metric"><div class="l">周期定位</div><div class="v" style="color:var(--accent);">${e.band}</div></div>
    <div class="metric"><div class="l">涨停数</div><div class="v up">${e.zt}</div></div>
    <div class="metric"><div class="l">炸板率</div><div class="v flat">${(e.zb/(Math.max(e.zt+e.zb,1))*100).toFixed(0)}%</div></div>
    <div class="metric"><div class="l">跌停数</div><div class="v down">${e.dt}</div></div>
    <div class="metric"><div class="l">最高板</div><div class="v" style="color:var(--gold);">${e.max_lb}板</div></div>`;""",
              """  const _eff = e.effect || null;
  const _effTxt = _eff ? `溢价 ${_eff.premium>0?'+':''}${_eff.premium}% · 1进2 ${_eff.rate_1to2}%`
                       : (e.effect_available === false ? '取不到(源降级)' : '—');
  const _effCol = !_eff ? 'var(--text-muted)'
        : ((_eff.premium < 0 || _eff.rate_1to2 < 25) ? 'var(--down)'
        : ((_eff.premium > 3 && _eff.rate_1to2 > 50) ? 'var(--up)' : 'var(--text-secondary)'));
  const _div = e.diverge === 'score_high_effect_weak'
        ? '<span style="color:var(--down);font-weight:700;">⚠ 分数偏高但接力偏弱（广度在装没事）</span>'
        : (e.diverge === 'score_low_effect_strong'
        ? '<span style="color:var(--up);font-weight:700;">⚡ 分数偏低但赚钱效应转强（冰点试错窗口）</span>' : '');

  document.getElementById('emoMetrics').innerHTML = `
    <div class="metric"><div class="l">周期定位</div><div class="v" style="color:var(--accent);" title="v1 公式对照: ${e.score_v1 ?? '-'}">${e.band}</div></div>
    <div class="metric"><div class="l">涨停数</div><div class="v up">${e.zt}</div></div>
    <div class="metric"><div class="l">炸板率</div><div class="v flat">${(e.zb/(Math.max(e.zt+e.zb,1))*100).toFixed(0)}%</div></div>
    <div class="metric"><div class="l">跌停数</div><div class="v down">${e.dt}</div></div>
    <div class="metric"><div class="l">最高板</div><div class="v" style="color:var(--gold);">${e.max_lb}板</div></div>
    <div class="metric"><div class="l">赚钱效应</div><div class="v" style="color:${_effCol};font-size:15px;">${_effTxt}</div></div>
    ${_div ? `<div class="metric" style="grid-column:1/-1;">${_div}</div>` : ''}`;""",
              "frontend emotion card"))

print("== 应用编辑 ==")
work = {}
for path in {e[0] for e in EDITS}:
    work[path] = path.read_text(encoding="utf-8")

ok = True
for path, old, new, label in EDITS:
    cnt = work[path].count(old)
    if cnt != 1:
        print(f"  ABORT  {label}: 命中 {cnt} 次(应为 1) -> 未落盘")
        ok = False
        continue
    work[path] = work[path].replace(old, new, 1)
    print(f"  OK     {label}")

if not ok:
    print("有编辑未命中, 整体不落盘")
    sys.exit(1)

for path in work:
    path.write_text(work[path], encoding="utf-8")
    print(f"已写回: {path}  ({path.stat().st_size}B)")
print("== 完成 ==")