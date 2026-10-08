# -*- coding: utf-8 -*-
"""① 归档门禁堵口（fail-closed + 今天也校验 + 回吐检测）
② sim_score 账本 upsert（按 pred_date 覆盖，不再重复追加；陈旧样本自动自愈）
"""
import pathlib
import subprocess

SD = pathlib.Path(r"D:\股票看盘\scripts\stock_dashboard.py")
SS = pathlib.Path(r"D:\股票看盘\scripts\sim_score.py")
fails = []

GATE_FN = '''def _archive_eligible(ymd, recs, n_zt, n_zb, n_dt, max_lb, force=False):
    """情绪档案写入资格（2026-10-08 门禁 v2）。返回 (bool, 原因)。

    三层校验，缺一不可：
      ① 该日必须在交易所日K里 —— **包含"今天"**（收盘后日K必有当天行）。
         日K取不到/为空 → fail-closed：宁可今天不归档，也不写可能是假的数据
         （旧版 bug：`ymd < today` 把"今天"排除在校验外，而 20261001 那条假记录
           恰恰是"当天是假期"时写进去的 —— 门禁放行了当初翻车的那一类）
      ② 四项数值与最近一条存档**完全相同** → 判为"接口对休市日回吐最近交易日数据"
         （10-01 假记录的真正根因：push2ex 对任意日期返回最近一个池）
      ③ FORCE_ARCHIVE=1 可绕过 ①，供人工补录；② 始终生效（错了就显式报错让你确认）
    """
    import os as _os
    if force or _os.environ.get('FORCE_ARCHIVE') == '1':
        return True, 'FORCE_ARCHIVE 显式放行'
    try:
        kl = kline_tx('sh000001', 60)
        dates = [str(row[0])[:10].replace('-', '') for row in kl] if kl else []
    except Exception as e:
        return False, f'日K取数异常({type(e).__name__}) → fail-closed 拒绝入库'
    if not dates:
        return False, '日K为空 → fail-closed 拒绝入库'
    if ymd not in dates:
        return False, f'该日不在交易所日K中（日K最近交易日 {dates[-1]}）→ 非交易日/休市'
    prev = [r for r in recs if r.get('date') and str(r.get('date')) < str(ymd)]
    if prev:
        p = prev[-1]
        try:
            same = (int(p.get('zt') or -1) == int(n_zt) and int(p.get('zb') or -1) == int(n_zb)
                    and int(p.get('dt') or -1) == int(n_dt) and int(p.get('max_lb') or -1) == int(max_lb))
        except Exception:
            same = False
        if same:
            return False, (f'四项数值与最近交易日 {p.get("date")} 完全相同 '
                           f'(zt{int(n_zt)}/zb{int(n_zb)}/dt{int(n_dt)}/{int(max_lb)}板) '
                           f'→ 疑似接口回吐最近数据；若确认是真实交易日请用 FORCE_ARCHIVE=1 重跑')
    return True, '通过"日K存在 + 非回吐"双重校验'


'''


def edit(path, old, new, tag, expect=1):
    t = path.read_text(encoding="utf-8")
    n = t.count(old)
    if n != expect:
        fails.append(f'{tag}: 命中 {n} 次(期望 {expect})')
        print(f'  FAIL  {tag}: 命中 {n} 次')
        return
    path.write_text(t.replace(old, new), encoding="utf-8")
    print(f'  OK    {tag}')


# ---------- ① 门禁 ----------
edit(SD, "def emotion(ymd=None):", GATE_FN + "def emotion(ymd=None):", 'sd: 插入 _archive_eligible')

edit(SD, """        if not any(r.get('date') == ymd for r in recs):
            # 交易日有效性门禁: 必须是交易所真实交易日 (节假日与非交易日严禁入库，防止毒化 MA 与周期判定)
            is_valid_day = True
            try:
                kl_check = kline_tx('sh000001', 30)
                if kl_check:
                    k_dates = [str(row[0])[:10].replace('-', '') for row in kl_check]
                    # 历史日期必须在日K中；当天日期在15点后也应有日K生成
                    if ymd not in k_dates and ymd < _now.strftime('%Y%m%d'):
                        is_valid_day = False
            except Exception:
                pass
            if not is_valid_day:
                w(f'({ymd} 非有效交易日/节假日休市, 跳过情绪归档)')
            else:""",
     """        if not any(r.get('date') == ymd for r in recs):
            # 交易日有效性门禁 v2: 日K存在(含今天) + 非"接口回吐" + 取数失败 fail-closed
            _ok, _why = _archive_eligible(ymd, recs, n_zt, n_zb, n_dt, max_lb)
            if not _ok:
                w(f'({ymd} 归档门禁拒绝: {_why})')
            else:""", 'sd: 门禁改为 v2（fail-closed + 今天也校验 + 回吐检测）')

# ---------- ② 账本 upsert ----------
edit(SS, """def already_scored(date_str):
    if not LEDGER.exists():
        return False
    for line in LEDGER.read_text(encoding='utf-8').splitlines():
        try:
            if json.loads(line).get('pred_date') == date_str:
                return True
        except Exception:
            continue
    return False""",
     """def already_scored(date_str, next_ymd=None):
    \"\"\"是否已记分。传入 next_ymd 时还要求"记的次日就是当前算出的次日"——
    这样陈旧样本（例如当初误用假期日 20261001 当次日算出来的那条）不会挡住重算，自动自愈。\"\"\"
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
    \"\"\"按 pred_date 覆盖写入（同一笔预测重算即替换, 不再重复追加/累计虚高）\"\"\"
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
    LEDGER.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\\n' for r in rows), encoding='utf-8')
    return len(rows)""", 'sim_score: already_scored 加次日校验 + ledger_upsert')

edit(SS, """    todo = []
    for p in predictions():
        d = p.stem.replace('sim-', '')
        if date and d != date:
            continue
        if not all_ and already_scored(d):
            continue
        todo.append((d, p))""",
     """    todo = []
    for p in predictions():
        d = p.stem.replace('sim-', '')
        if date and d != date:
            continue
        nxt_pre = next_trade_date(d)          # 先算出"当前应记的次日", 用来识别陈旧样本
        if not all_ and already_scored(d, nxt_pre):
            continue
        todo.append((d, p))""", 'sim_score: run() 用次日校验挑待记分项')

edit(SS, """        if res.get('ok'):
            with open(LEDGER, 'a', encoding='utf-8') as f:
                f.write(json.dumps({'pred_date': d, 'next_date': res['next_date'],
                                    'direction': res['direction'], 'strength': res['strength'],
                                    'sectors': res['sectors'], 'scenario': res['scenario'],
                                    'risks': res['risks']}, ensure_ascii=False) + '\\n')""",
     """        if res.get('ok'):
            ledger_upsert({'pred_date': d, 'next_date': res['next_date'],
                           'direction': res['direction'], 'strength': res['strength'],
                           'sectors': res['sectors'], 'scenario': res['scenario'],
                           'risks': res['risks']})""", 'sim_score: 写账本改为 upsert')

if fails:
    print('有失败项:', fails)
    raise SystemExit(1)

PY = r"C:\Users\28769\AppData\Local\Programs\Python\Python312\python.exe"
for f in (SD, SS):
    r = subprocess.run([PY, "-m", "py_compile", str(f)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(f'{f.name} py_compile rc={r.returncode} {(r.stderr or "").strip()[:200]}')