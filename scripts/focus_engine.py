# -*- coding: utf-8 -*-
"""
「AI 今日关注」规则引擎：聚合现有真实算子结果 -> 统一 FocusItem -> 风险优先排序/去重/截断。

原则：
  * facts（数字）全部取自真实算子返回值，禁止硬编码假数据；
  * 任一算子失败只被吞掉并记录到 operatorsOk，汇总其余可用部分；
  * narrative 先由模板（仅引用 facts / title 中的数字）生成，narrativeSource='template'，
    后续可由 focus_narrator 用 LLM 改写（带数字一致性校验）。
"""
import time
import datetime as _dt
from typing import Any, Callable, Dict, List, Optional

LEVEL_ORDER = {"RED": 0, "YELLOW": 1, "GREEN": 2, "INFO": 3}
PER_CATEGORY_LIMIT = 5
TOTAL_LIMIT = 15
CATEGORY_TO_KEY = {"RISK": "risks", "THEME": "themes", "ANOMALY": "anomalies", "NEWS": "news"}


def _fact(label: str, value: Any, unit: str = "") -> Dict[str, Any]:
    return {"label": label, "value": value, "unit": unit}


def _num(v: Any) -> Optional[float]:
    try:
        if v is None or isinstance(v, bool):
            return None
        f = float(v)
        if f != f or f in (float("inf"), float("-inf")):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _clean(x: float) -> Any:
    """整数值输出 int，其余保留 2 位。"""
    x = float(x)
    return int(x) if x == int(x) else round(x, 2)


def _fmt_fact(f: Dict[str, Any]) -> str:
    return f"{f['label']}{f['value']}{f.get('unit') or ''}"


def _make_item(*, id: str, category: str, level: str, title: str, facts: List[Dict[str, Any]],
               symbols: Optional[List[str]] = None, evidence: Optional[List[str]] = None,
               score: float = 50, tail: str = "", now_ms: int = 0) -> Dict[str, Any]:
    facts = [f for f in facts if f.get("value") is not None]
    narrative = f"{title}。" + ("，".join(_fmt_fact(f) for f in facts) + "。" if facts else "")
    narrative += tail
    return {
        "id": id,
        "category": category,
        "level": level,
        "title": title,
        "facts": facts,
        "symbols": [s for s in (symbols or []) if s],
        "narrative": narrative,
        "narrativeSource": "template",
        "evidence": evidence or [],
        "score": int(round(max(0.0, min(100.0, float(score))))),
        "updatedAt": now_ms,
    }


# ----------------------------------------------------------------- 各算子 -> FocusItem

def _items_from_ladder(d: Dict[str, Any], now_ms: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(d, dict) or d.get("status") not in (None, "ok"):
        return out
    ymd = str(d.get("tradeDate") or "")
    max_h, second = _num(d.get("maxBoardHeight")), _num(d.get("secondMaxBoardHeight"))
    broken, down = _num(d.get("brokenBoardCount")), _num(d.get("limitDownCount"))
    seal = _num(d.get("sealSuccessRate"))
    risk_score = _num(d.get("ebbTideRiskScore")) or 0.0
    risk_level = d.get("ebbTideRiskLevel")
    dragon_sym = d.get("spaceDragonSymbol") or ""
    missing = d.get("missingBoards") or []

    base_facts = []
    if max_h is not None:
        base_facts.append(_fact("最高板", _clean(max_h), "板"))

    if d.get("hasLadderFault"):
        facts = list(base_facts)
        facts.append(_fact("断层层数", len(missing), "层"))
        if second is not None:
            facts.append(_fact("次高板", _clean(second), "板"))
        if broken is not None:
            facts.append(_fact("炸板数", _clean(broken), "家"))
        if down is not None:
            facts.append(_fact("跌停数", _clean(down), "家"))
        out.append(_make_item(
            id=f"risk-ladder-fault-{ymd}", category="RISK",
            level="RED" if risk_level == "HIGH_EBB_RISK" else "YELLOW",
            title="连板梯队出现断层", facts=facts, symbols=[dragon_sym], evidence=["ladder", "emotion"],
            score=60 + risk_score * 0.4, tail="梯队断层意味着高位接力缺乏中位承接，需留意退潮风险。", now_ms=now_ms))
    elif risk_level == "HIGH_EBB_RISK":
        facts = [x for x in (
            _fact("跌停数", _clean(down), "家") if down is not None else None,
            _fact("炸板数", _clean(broken), "家") if broken is not None else None,
            _fact("封板成功率", _clean(seal), "%") if seal is not None else None) if x]
        out.append(_make_item(
            id=f"risk-ladder-ebb-{ymd}", category="RISK", level="RED", title="短线退潮风险偏高",
            facts=facts, symbols=[dragon_sym], evidence=["ladder", "emotion"],
            score=60 + risk_score * 0.4, tail="亏钱效应扩散，需控制风险暴露。", now_ms=now_ms))
    elif risk_level == "MEDIUM_FAULT_RISK":
        facts = [x for x in (
            _fact("炸板数", _clean(broken), "家") if broken is not None else None,
            _fact("封板成功率", _clean(seal), "%") if seal is not None else None) if x]
        out.append(_make_item(
            id=f"risk-ladder-medium-{ymd}", category="RISK", level="YELLOW", title="连板情绪出现分歧",
            facts=facts, symbols=[dragon_sym], evidence=["ladder"], score=45 + risk_score * 0.3,
            tail="分歧阶段波动加大，注意节奏。", now_ms=now_ms))

    if d.get("topDragonIsolation") and max_h is not None and second is not None:
        out.append(_make_item(
            id=f"risk-dragon-isolation-{ymd}", category="RISK", level="YELLOW", title="空间龙孤立",
            facts=[_fact("最高板", _clean(max_h), "板"), _fact("次高板", _clean(second), "板")],
            symbols=[dragon_sym], evidence=["ladder"], score=55,
            tail="最高标缺少梯队呼应，空间高度的持续性存疑。", now_ms=now_ms))
    return out


def _items_from_themes(d: Dict[str, Any], now_ms: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(d, dict) or d.get("status") not in (None, "ok"):
        return out
    themes = d.get("themes") or []
    ymd = _dt.date.today().strftime("%Y%m%d")
    for t in themes:
        name = str(t.get("sectorName") or "")
        score = _num(t.get("resonanceScore"))
        link = _num(t.get("dragonLinkageScore"))
        if not name or score is None:
            continue
        if t.get("attackRole") == "MAIN_ATTACK" and score >= 75 and link is not None and link >= 80:
            facts = [_fact("共振得分", _clean(score), "分"), _fact("龙头联动", _clean(link), "分")]
            for lab, key, unit in (("板块涨幅", "sectorChangePercent", "%"), ("涨停数", "limitUpCount", "家")):
                v = _num(t.get(key))
                if v is not None:
                    facts.append(_fact(lab, _clean(v), unit))
            pio = (t.get("pioneerDragon") or {}).get("symbol")
            out.append(_make_item(
                id=f"theme-resonance-{name}-{ymd}", category="THEME", level="GREEN",
                title=f"{name}点面共振", facts=facts, symbols=[pio], evidence=["theme_resonance"],
                score=score, tail="资金与涨停梯队同向，属于当日强势方向，但持续性需继续观察。", now_ms=now_ms))
    retreats = [t for t in themes if t.get("attackRole") == "EBB_RETREAT" and _num(t.get("totalNetInflowCNY")) is not None]
    retreats.sort(key=lambda t: _num(t.get("totalNetInflowCNY")))
    for t in retreats[:3]:
        name = str(t.get("sectorName") or "")
        pct, flow = _num(t.get("sectorChangePercent")), _num(t.get("totalNetInflowCNY"))
        facts = []
        if pct is not None:
            facts.append(_fact("板块涨幅", _clean(pct), "%"))
        facts.append(_fact("主力净流入", _clean(round(flow / 1e8, 2)), "亿"))
        out.append(_make_item(
            id=f"risk-theme-ebb-{name}-{ymd}", category="RISK", level="YELLOW", title=f"{name}资金退潮",
            facts=facts, symbols=[(t.get("pioneerDragon") or {}).get("symbol")], evidence=["theme_resonance"],
            score=40 + min(30.0, abs(flow) / 1e8), tail="主力资金流出，题材存在兑现压力。", now_ms=now_ms))
    return out


def _anom_strength(a: Dict[str, Any]) -> float:
    return _num(a.get("anomalyStrength")) or _num(a.get("strength")) or 0.0


def _items_from_radar(d: Dict[str, Any], now_ms: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(d, dict) or d.get("status") not in (None, "ok"):
        return out
    ymd = _dt.date.today().strftime("%Y%m%d")
    summ = d.get("summary") or {}
    bull, bear = _num(summ.get("bullishCount")), _num(summ.get("bearishCount"))
    if summ.get("marketTemperament") == "BEARISH_DEFENSE" and bear:
        out.append(_make_item(
            id=f"anomaly-bearish-dominant-{ymd}", category="ANOMALY", level="YELLOW", title="盘中空头异动占优",
            facts=[_fact("空头异动", _clean(bear), "条"), _fact("多头异动", _clean(bull or 0), "条")],
            evidence=["intraday_radar"], score=50 + min(30.0, bear), tail="盘中下杀类异动多于拉升类异动。", now_ms=now_ms))

    anomalies = d.get("anomalies") or []
    bears = sorted([a for a in anomalies if a.get("polarity") == "BEARISH" and _anom_strength(a) >= 80],
                   key=_anom_strength, reverse=True)[:2]
    bulls = sorted([a for a in anomalies if a.get("polarity") == "BULLISH" and _anom_strength(a) >= 80],
                   key=_anom_strength, reverse=True)[:2]
    for lst, level, tag in ((bears, "YELLOW", "bear"), (bulls, "GREEN", "bull")):
        for a in lst:
            sym = a.get("symbol") or ""
            name = a.get("name") or sym
            tname = a.get("typeName") or "盘中异动"
            facts = [_fact("异动强度", _clean(_anom_strength(a)), "分")]
            chg = _num(a.get("changePercent"))
            if chg is not None:
                facts.append(_fact("涨跌幅", _clean(chg), "%"))
            out.append(_make_item(
                id=f"anomaly-{tag}-{sym}-{a.get('typeCode')}-{ymd}", category="ANOMALY", level=level,
                title=f"{name}{tname}", facts=facts, symbols=[sym], evidence=["intraday_radar"],
                score=_anom_strength(a) * 0.9, tail="属于盘中瞬时异动，需结合量能与后续走势确认。", now_ms=now_ms))

    flow = d.get("symbolCapitalFlow") or {}
    lvl = flow.get("synergyLevel")
    sc = _num(flow.get("synergyScore"))
    if lvl in ("STRONG_RESONANCE", "DIVERGENCE_WARNING", "BEARISH_DUMP") and sc is not None and flow.get("symbol"):
        level = {"STRONG_RESONANCE": "GREEN", "DIVERGENCE_WARNING": "YELLOW", "BEARISH_DUMP": "RED"}[lvl]
        label = {"STRONG_RESONANCE": "异动与资金强共振", "DIVERGENCE_WARNING": "异动与资金背离",
                 "BEARISH_DUMP": "异动叠加资金流出"}[lvl]
        facts = [_fact("协同得分", _clean(sc), "分")]
        net = _num(flow.get("mainNetInflow"))
        if net is not None:
            facts.append(_fact("主力净流入", _clean(round(net / 1e8, 2)), "亿"))
        chg = _num(flow.get("changePercent"))
        if chg is not None:
            facts.append(_fact("涨跌幅", _clean(chg), "%"))
        out.append(_make_item(
            id=f"anomaly-synergy-{flow['symbol']}-{ymd}", category="ANOMALY", level=level,
            title=f"{flow.get('name') or flow['symbol']}{label}", facts=facts, symbols=[flow["symbol"]],
            evidence=["intraday_radar", "capital_flow"], score=50 + abs(sc) * 0.4,
            tail=str(flow.get("synergyVerdict") or ""), now_ms=now_ms))
    return out


def _items_from_regulatory(rows: List[Dict[str, Any]], now_ms: int) -> List[Dict[str, Any]]:
    """rows: [{'symbol','name','regulatory':VolatilityEvaluationResult.dict}]"""
    out: List[Dict[str, Any]] = []
    ymd = _dt.date.today().strftime("%Y%m%d")
    for r in rows or []:
        reg = r.get("regulatory") or {}
        sym, name = r.get("symbol") or "", r.get("name") or r.get("symbol") or ""
        head = _num(reg.get("headroom_pct"))
        n9 = _num(reg.get("normal_triggers_in_prev_9d"))
        triggered = reg.get("is_severe_locked") or reg.get("is_severe_triggered_now") or reg.get("is_normal_triggered_now")
        near = head is not None and head < 0.05
        if not (triggered or near) or not sym:
            continue
        level = "RED" if (triggered or (head is not None and head < 0.02)) else "YELLOW"
        facts = []
        if head is not None:
            facts.append(_fact("距异动线空间", _clean(round(head * 100, 2)), "%"))
        if n9 is not None:
            facts.append(_fact("近9日普通异动次数", _clean(n9), "次"))
        out.append(_make_item(
            id=f"risk-regulatory-{sym}-{ymd}", category="RISK", level=level,
            title=f"{name}逼近或触发监管异动", facts=facts, symbols=[sym], evidence=["regulatory"],
            score=75 if level == "RED" else 50, tail="监管异常波动可能导致停牌核查，需留意规则窗口。", now_ms=now_ms))
    return out


def _items_from_global_radar(d: Dict[str, Any], now_ms: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(d, dict) or d.get("status") not in (None, "ok"):
        return out
    ymd = _dt.date.today().strftime("%Y%m%d")

    # 1. 跨市场传导链显著信号
    chains = d.get("transmissionChains") or []
    for chain in chains:
        score = _num(chain.get("resonanceScore"))
        cid = str(chain.get("id") or "chain")
        cname = str(chain.get("name") or "跨市场传导")
        mapped_symbols = [s.get("symbol") for s in (chain.get("mappedSymbols") or []) if isinstance(s, dict) and s.get("symbol")]
        mapped_sectors = chain.get("mappedSectors") or []
        sectors_str = "/".join(str(s) for s in mapped_sectors)

        if score is None:
            continue

        if score >= 35.0:
            facts = [_fact("共振分", _clean(score), "分")]
            for drv in (chain.get("driverAssets") or [])[:3]:
                dname = drv.get("name") or drv.get("symbol")
                dpct = _num(drv.get("changePercent"))
                if dpct is not None:
                    facts.append(_fact(f"{dname}涨幅", _clean(dpct), "%"))
            sectors_desc = f"映射A股{sectors_str}等板块" if sectors_str else "映射A股关联产业链"
            out.append(_make_item(
                id=f"theme-global-{cid}-{ymd}",
                category="THEME",
                level="GREEN",
                title=f"全球传导：{cname}共振走强",
                facts=facts,
                symbols=mapped_symbols,
                evidence=["global_radar", cid],
                score=min(100.0, 50.0 + abs(score) * 0.45),
                tail=f"外盘驱动共振走强，{sectors_desc}有望获得估值提振与情绪共振。",
                now_ms=now_ms,
            ))
        elif score <= -35.0:
            level = "RED" if score <= -55.0 else "YELLOW"
            facts = [_fact("共振分", _clean(score), "分")]
            for drv in (chain.get("driverAssets") or [])[:3]:
                dname = drv.get("name") or drv.get("symbol")
                dpct = _num(drv.get("changePercent"))
                if dpct is not None:
                    facts.append(_fact(f"{dname}涨幅", _clean(dpct), "%"))
            sectors_desc = f"映射A股{sectors_str}等板块" if sectors_str else "映射A股关联产业链"
            out.append(_make_item(
                id=f"risk-global-{cid}-{ymd}",
                category="RISK",
                level=level,
                title=f"全球传导：{cname}共振走弱",
                facts=facts,
                symbols=mapped_symbols,
                evidence=["global_radar", cid],
                score=min(100.0, 55.0 + abs(score) * 0.4),
                tail=f"外盘资产下行共振，需警惕对{sectors_desc}的情绪与估值压制风险。",
                now_ms=now_ms,
            ))

    # 2. 7x24 全球财经快讯 -> NEWS
    live_news = d.get("liveNews") or []
    sorted_news = sorted(live_news, key=lambda x: (0 if x.get("importance") == "HIGH" else 1))[:5]
    for idx, news in enumerate(sorted_news):
        nid = str(news.get("id") or idx)
        title = str(news.get("title") or "").strip()
        if not title:
            continue
        importance = news.get("importance")
        polarity = news.get("polarity")
        imp_score = 85 if importance == "HIGH" else 60
        facts = [_fact("重要度", imp_score, "分")]
        t_str = str(news.get("time") or "")
        if ":" in t_str:
            t_parts = t_str.split(" ")[-1].split(":")
            if len(t_parts) >= 2 and t_parts[0].isdigit() and t_parts[1].isdigit():
                facts.append(_fact("发布时间", int(t_parts[0]) * 100 + int(t_parts[1]), "分"))

        level = "INFO"
        if importance == "HIGH":
            level = "YELLOW" if polarity == "BEARISH" else ("GREEN" if polarity == "BULLISH" else "INFO")

        out.append(_make_item(
            id=f"news-live-{nid}-{ymd}",
            category="NEWS",
            level=level,
            title=title,
            facts=facts,
            symbols=[],
            evidence=["global_radar", "live_news"],
            score=imp_score,
            tail="全球财经快讯，关注消息面对关联板块的短线情绪催化。",
            now_ms=now_ms,
        ))

    return out


# ----------------------------------------------------------------- 默认算子（延迟导入，避免测试时拉网）

def _default_operators() -> Dict[str, Callable]:
    import quant_data_service as qds
    import global_market_radar as gmr

    def _regulatory(ladder: Optional[Dict[str, Any]]):
        import regulatory_service as reg
        syms: List[Dict[str, Any]] = []
        for row in (ladder or {}).get("distributionComparison") or []:
            for s in row.get("stocks") or []:
                syms.append(s)
            if len(syms) >= 3:
                break
        rows = []
        for s in syms[:3]:
            try:
                p = reg.build_single_payload(s["symbol"])
                rows.append({"symbol": s["symbol"], "name": s.get("name"), "regulatory": p.get("regulatory")})
            except Exception:
                continue
        return rows

    return {
        "ladder": qds.get_real_ladder,
        "theme_resonance": qds.get_real_theme_resonance,
        "intraday_radar": qds.get_real_intraday_radar,
        "regulatory": _regulatory,
        "global_radar": gmr.get_global_market_radar,
    }


def _market_tone(ladder: Optional[Dict[str, Any]], theme: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(ladder, dict) or ladder.get("status") not in (None, "ok"):
        return {"phase": "数据暂缺", "text": "连板梯队数据暂不可用，无法给出情绪定调。", "level": "INFO"}
    rl = ladder.get("ebbTideRiskLevel")
    level = {"HIGH_EBB_RISK": "RED", "MEDIUM_FAULT_RISK": "YELLOW"}.get(rl, "GREEN")
    parts = []
    for lab, key, unit in (("最高", "maxBoardHeight", "板"), ("炸板", "brokenBoardCount", "家"),
                           ("跌停", "limitDownCount", "家"), ("封板成功率", "sealSuccessRate", "%")):
        v = _num(ladder.get(key))
        if v is not None:
            parts.append(f"{lab}{_clean(v)}{unit}")
    return {"phase": ladder.get("sentimentPhase") or "未知", "text": "，".join(parts) + "。" if parts else "", "level": level}


def sort_and_truncate(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """去重(按 id 保留高分) -> 风险优先排序 -> 每类最多5条 -> 总计15条。"""
    best: Dict[str, Dict[str, Any]] = {}
    for it in items:
        cur = best.get(it["id"])
        if cur is None or it["score"] > cur["score"]:
            best[it["id"]] = it
    ordered = sorted(
        best.values(),
        key=lambda x: (LEVEL_ORDER.get(x["level"], 9), 0 if x["category"] == "RISK" else 1, -x["score"]))
    counts: Dict[str, int] = {}
    out: List[Dict[str, Any]] = []
    for it in ordered:
        c = it["category"]
        if counts.get(c, 0) >= PER_CATEGORY_LIMIT:
            continue
        counts[c] = counts.get(c, 0) + 1
        out.append(it)
        if len(out) >= TOTAL_LIMIT:
            break
    return out


def build_focus(operators: Optional[Dict[str, Callable]] = None, now_ms: Optional[int] = None) -> Dict[str, Any]:
    """聚合并返回 {marketTone, items, risks, themes, anomalies, news, operatorsOk, updatedAt}。"""
    now_ms = now_ms or int(time.time() * 1000)
    ops = operators if operators is not None else _default_operators()
    ok: Dict[str, bool] = {}
    data: Dict[str, Any] = {}

    def run(name, *args):
        fn = ops.get(name)
        if fn is None:
            ok[name] = False
            return None
        try:
            r = fn(*args)
            ok[name] = r is not None
            return r
        except Exception:
            ok[name] = False
            return None

    ladder = run("ladder")
    data["theme"] = run("theme_resonance")
    data["radar"] = run("intraday_radar")
    reg_rows = run("regulatory", ladder)
    data["global_radar"] = run("global_radar")

    items: List[Dict[str, Any]] = []
    for name, fn, arg in (("ladder", _items_from_ladder, ladder),
                          ("theme_resonance", _items_from_themes, data["theme"]),
                          ("intraday_radar", _items_from_radar, data["radar"]),
                          ("regulatory", _items_from_regulatory, reg_rows),
                          ("global_radar", _items_from_global_radar, data["global_radar"])):
        if arg is None:
            continue
        try:
            items.extend(fn(arg, now_ms))
        except Exception:
            ok[name] = False

    final = sort_and_truncate(items)
    result: Dict[str, Any] = {"marketTone": _market_tone(ladder, data["theme"]), "items": final,
                              "operatorsOk": ok, "updatedAt": now_ms}
    for key in CATEGORY_TO_KEY.values():
        result[key] = []
    for it in final:
        result[CATEGORY_TO_KEY.get(it["category"], "news")].append(it)
    return result
