# -*- coding: utf-8 -*-
"""交付② 接入口：把 LLM 冲击矩阵接进现有确定性引擎（stock_dashboard）与 /api/sim。

原则：LLM 只提供"判断"（impact / 叙事 / 情景），**数值聚合仍由规则引擎算** —— 可回溯、可对账。
每处替换都断言命中次数，失败整体不落盘。
"""
import pathlib
import subprocess

SD = pathlib.Path(r"D:\股票看盘\scripts\stock_dashboard.py")
MAIN = pathlib.Path(r"D:\股票看盘\web\main.py")
fails = []


def edit(path, old, new, tag, expect=1):
    t = path.read_text(encoding="utf-8")
    n = t.count(old)
    if n != expect:
        fails.append(f'{tag}: 命中 {n} 次(期望 {expect})')
        print(f'  FAIL  {tag}: 命中 {n} 次(期望 {expect})')
        return
    path.write_text(t.replace(old, new), encoding="utf-8")
    print(f'  OK    {tag}')


# ---------- stock_dashboard: 管道支持外部冲击覆盖 ----------
edit(SD,
     "def _sim_pipeline(ag, scenario=None, use_memory=False, cur_date='', verbose=False):",
     "def _sim_pipeline(ag, scenario=None, use_memory=False, cur_date='', verbose=False,\n"
     "                  impact_override=None, impact_note=''):",
     'sd: _sim_pipeline 签名')

edit(SD,
     """    if scenario:
        meta, impact = parse_event_scenario(scenario)
        if verbose:
            w('【上帝视角·事件注入】: %s' % scenario)
            w('【事件研判】领域: %s | 影响逻辑: %s' % (meta['domain'], meta['desc']))
        ag = {k: cl(v + impact.get(k, 0), -100, 100) for k, v in ag.items()}""",
     """    if scenario or impact_override:
        if impact_override:
            # LLM(或外部)给出的九方冲击矩阵: 只覆盖"判断"这一层, 后面的传染/加权仍走本引擎
            meta = {'domain': impact_note or 'LLM 消息面推演',
                    'desc': '外部冲击矩阵（LLM 依据当日消息面事件表给出），数值聚合仍由本引擎计算'}
            impact = {}
            for _k, _v in (impact_override or {}).items():
                try:
                    impact[str(_k)] = float(_v)
                except (TypeError, ValueError):
                    continue      # 非数值项(如 theme_priority 列表)不进冲击矩阵
        else:
            meta, impact = parse_event_scenario(scenario)
        if verbose:
            if scenario:
                w('【上帝视角·事件注入】: %s' % scenario)
            if impact_override:
                w('【事件注入·LLM 冲击矩阵】%s' % ' '.join('%s%+.0f' % (k, v) for k, v in impact.items()))
                _it = impact_override.get('theme_priority') if isinstance(impact_override, dict) else None
                if _it:
                    w('【LLM 板块优先级】%s' % ' '.join('%s%s' % (
                        '+' if x.get('polarity', 0) > 0 else ('-' if x.get('polarity', 0) < 0 else '·'),
                        x.get('sector', '')) for x in _it[:6]))
            w('【事件研判】领域: %s | 影响逻辑: %s' % (meta['domain'], meta['desc']))
        ag = {k: cl(v + impact.get(k, 0), -100, 100) for k, v in ag.items()}""",
     'sd: 管道冲击注入')

# ---------- stock_dashboard: sim_world 透传 ----------
edit(SD,
     "def sim_world(scenario=None):",
     "def sim_world(scenario=None, llm_impact=None, llm_note=''):",
     'sd: sim_world 签名(正则前)')

edit(SD,
     """    ag, _ = _sim_pipeline(ag, scenario=scenario, use_memory=True,
                          cur_date=la.get('date', ''), verbose=True)""",
     """    ag, _ = _sim_pipeline(ag, scenario=scenario, use_memory=True,
                          cur_date=la.get('date', ''), verbose=True,
                          impact_override=llm_impact, impact_note=llm_note)""",
     'sd: sim_world 透传 llm_impact')

# ---------- web/main.py: /api/sim?engine=llm ----------
edit(MAIN,
     '@app.get("/api/sim")\ndef api_sim(scenario: str = "", code: str = ""):\n'
     '    """多主体模拟：世界模拟v2 (MiroFish级事件沙盘注入与九方势力博弈推演)"""',
     '@app.get("/api/sim")\ndef api_sim(scenario: str = "", code: str = "", engine: str = "rule"):\n'
     '    """多主体模拟：世界模拟v2 + 可选 LLM 消息面推演\n\n'
     '    engine=rule（默认，纯规则引擎）| engine=llm（LLM 读当日事件表出九方冲击矩阵,\n'
     '    再交给同一个规则引擎做传染与加权 —— LLM 只给判断, 不碰算术）。\n'
     '    无密钥/调用失败时自动回落 rule，并在返回里标 engine=rule(fallback)。\n'
     '    """',
     'web: api_sim 签名')

edit(MAIN,
     """    code = _normalize_stock_code(code)
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            if code:
                sd.agent_sim(code)
                mode = "agents"
            else:
                sd.sim_world(scenario.strip() or None)
                mode = "sim\"""",
     """    code = _normalize_stock_code(code)
    buf = io.StringIO()
    llm_payload = None
    llm_impact = None
    if engine == "llm" and not code:
        try:
            import sim_llm as _simllm
            llm_payload = _simllm.run(dry_run=False, quiet=True)
        except Exception as e:
            llm_payload = {"ok": False, "reason": "exception", "hint": f"{type(e).__name__}: {e}"}
        if llm_payload.get("ok"):
            llm_impact = dict(llm_payload.get("impact") or {})
            llm_impact["theme_priority"] = llm_payload.get("theme_priority") or []
        else:
            llm_payload = dict(llm_payload, fallback=True)
    try:
        with redirect_stdout(buf):
            if code:
                sd.agent_sim(code)
                mode = "agents"
            else:
                sd.sim_world(scenario.strip() or None, llm_impact=llm_impact,
                             llm_note="LLM 消息面推演")
                mode = "sim\"""",
     'web: LLM 推演分支')

edit(MAIN,
     '        return JSONResponse(dict(\n            status="ok", mode=mode, code=code, text=text,',
     '        return JSONResponse(dict(\n            status="ok", mode=mode, code=code, text=text,\n'
     '            engine=("llm" if (llm_payload and llm_payload.get("ok")) else\n'
     '                    ("rule(fallback)" if llm_payload else "rule")),\n'
     '            llm=llm_payload,',
     'web: 返回体带 engine/llm')

if fails:
    print()
    print('断言未命中, 不落盘:', fails)
    raise SystemExit(1)

PY = r"C:\Users\28769\AppData\Local\Programs\Python\Python312\python.exe"
for f in (SD, MAIN):
    r = subprocess.run([PY, "-m", "py_compile", str(f)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(f'{f.name} py_compile rc={r.returncode} {(r.stderr or "").strip()[:200]}')