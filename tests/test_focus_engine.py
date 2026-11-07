# -*- coding: utf-8 -*-
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for d in (os.path.join(BASE_DIR, "scripts"), os.path.join(BASE_DIR, "web")):
    if d not in sys.path:
        sys.path.insert(0, d)

import focus_engine as fe


def _ladder(**kw):
    d = {"status": "ok", "tradeDate": "20261106", "maxBoardHeight": 6, "secondMaxBoardHeight": 3,
         "brokenBoardCount": 4, "limitDownCount": 2, "sealSuccessRate": 66.7, "hasLadderFault": True,
         "missingBoards": [4, 5], "ebbTideRiskScore": 70, "ebbTideRiskLevel": "HIGH_EBB_RISK",
         "spaceDragonSymbol": "000530.SZ", "sentimentPhase": "退潮核按钮期", "topDragonIsolation": True,
         "distributionComparison": []}
    d.update(kw)
    return d


def _theme(name, score=80, link=90, role="MAIN_ATTACK", flow=2e9, pct=3.5):
    return {"sectorName": name, "resonanceScore": score, "dragonLinkageScore": link, "attackRole": role,
            "totalNetInflowCNY": flow, "sectorChangePercent": pct, "limitUpCount": 4,
            "pioneerDragon": {"symbol": "600000.SH"}}


def _ops(ladder=None, themes=None, radar=None, reg=None):
    return {
        "ladder": lambda: ladder,
        "theme_resonance": lambda: themes,
        "intraday_radar": lambda: radar,
        "regulatory": lambda l: reg,
    }


def test_risk_first_and_levels():
    themes = {"status": "ok", "themes": [_theme("AI算力")]}
    res = fe.build_focus(_ops(_ladder(), themes), now_ms=1)
    levels = [i["level"] for i in res["items"]]
    assert levels == sorted(levels, key=lambda x: fe.LEVEL_ORDER[x])
    assert res["items"][0]["level"] == "RED"
    assert res["risks"] and res["themes"][0]["level"] == "GREEN"
    assert res["marketTone"]["level"] == "RED" and res["marketTone"]["phase"] == "退潮核按钮期"


def test_facts_come_from_operator_data():
    res = fe.build_focus(_ops(_ladder(maxBoardHeight=7)), now_ms=1)
    fault = [i for i in res["risks"] if i["id"].startswith("risk-ladder-fault")][0]
    f = {x["label"]: x for x in fault["facts"]}
    assert f["最高板"]["value"] == 7 and f["最高板"]["unit"] == "板"
    assert all(set(x) == {"label", "value", "unit"} for x in fault["facts"])
    assert fault["narrativeSource"] == "template"


def test_truncation_per_category_and_total():
    themes = {"status": "ok", "themes": [_theme(f"题材{i}", score=80 + i * 0.1) for i in range(12)]}
    res = fe.build_focus(_ops(_ladder(), themes), now_ms=1)
    assert len(res["themes"]) == fe.PER_CATEGORY_LIMIT
    assert len(res["items"]) <= fe.TOTAL_LIMIT
    # 同级按 score 降序
    sc = [i["score"] for i in res["themes"]]
    assert sc == sorted(sc, reverse=True)


def test_total_limit_15():
    items = []
    for cat in ("RISK", "THEME", "ANOMALY", "NEWS"):
        for k in range(5):
            items.append(fe._make_item(id=f"{cat}-{k}", category=cat, level="YELLOW", title="t",
                                       facts=[], score=k))
    assert len(fe.sort_and_truncate(items)) == 15


def test_dedupe_keeps_highest_score():
    a = fe._make_item(id="x", category="RISK", level="RED", title="a", facts=[], score=10)
    b = fe._make_item(id="x", category="RISK", level="RED", title="b", facts=[], score=90)
    out = fe.sort_and_truncate([a, b])
    assert len(out) == 1 and out[0]["score"] == 90


def test_operator_failure_swallowed():
    def boom():
        raise RuntimeError("net down")
    ops = _ops(_ladder(), None)
    ops["theme_resonance"] = boom
    ops["intraday_radar"] = boom
    res = fe.build_focus(ops, now_ms=1)
    assert res["operatorsOk"]["theme_resonance"] is False
    assert res["operatorsOk"]["ladder"] is True
    assert res["risks"]


def test_all_operators_fail_still_valid():
    res = fe.build_focus({"ladder": lambda: 1 / 0}, now_ms=1)
    assert res["items"] == [] and res["marketTone"]["level"] == "INFO"


def test_radar_and_regulatory_items():
    radar = {"status": "ok", "summary": {"marketTemperament": "BEARISH_DEFENSE", "bullishCount": 1, "bearishCount": 6},
             "anomalies": [{"symbol": "000001.SZ", "name": "平安", "polarity": "BEARISH", "anomalyStrength": 90,
                            "typeCode": 32, "typeName": "封跌停", "changePercent": -9.9}],
             "symbolCapitalFlow": {"symbol": "000530.SZ", "name": "大冷", "synergyLevel": "BEARISH_DUMP",
                                   "synergyScore": -60, "mainNetInflow": -3e8, "changePercent": -2.1}}
    reg = [{"symbol": "000530.SZ", "name": "大冷", "regulatory": {"headroom_pct": 0.01, "normal_triggers_in_prev_9d": 2}}]
    res = fe.build_focus(_ops(None, None, radar, reg), now_ms=1)
    ids = {i["id"].rsplit("-", 1)[0] for i in res["items"]}
    assert any(i.startswith("risk-regulatory") for i in ids)
    syn = [i for i in res["anomalies"] if i["id"].startswith("anomaly-synergy")][0]
    assert syn["level"] == "RED"
    reg_item = res["risks"][0]
    assert reg_item["facts"][0]["value"] == 1
