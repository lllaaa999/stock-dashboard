# -*- coding: utf-8 -*-
"""GET /api/quant/focus 接口契约（mock 算子与 LLM，不访问网络）"""
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for d in (os.path.join(BASE_DIR, "scripts"), os.path.join(BASE_DIR, "web")):
    if d not in sys.path:
        sys.path.insert(0, d)

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import focus_engine as fe
import focus_narrator as fn
import main as web_main
from main import app

LADDER = {"status": "ok", "tradeDate": "20261106", "maxBoardHeight": 5, "secondMaxBoardHeight": 2,
          "brokenBoardCount": 3, "limitDownCount": 1, "sealSuccessRate": 70.0, "hasLadderFault": True,
          "missingBoards": [3, 4], "ebbTideRiskScore": 60, "ebbTideRiskLevel": "HIGH_EBB_RISK",
          "spaceDragonSymbol": "000530.SZ", "sentimentPhase": "高潮分化期", "topDragonIsolation": False}


@pytest.fixture(autouse=True)
def _reset():
    web_main._focus_cache.update({"data": None, "ts": 0.0})
    fn.reset_state()
    yield
    web_main._focus_cache.update({"data": None, "ts": 0.0})
    fn.reset_state()


def _ops():
    return {"ladder": lambda: LADDER, "theme_resonance": lambda: None,
            "intraday_radar": lambda: None, "regulatory": lambda l: None}


def test_contract_and_cache():
    calls = []
    def ops():
        calls.append(1)
        return _ops()
    with patch.object(fe, "_default_operators", ops), \
            patch("llm_client.load_config", return_value=None):
        c = TestClient(app)
        r = c.get("/api/quant/focus")
        j = r.json()
        assert r.status_code == 200 and j["status"] == "ok"
        for k in ("marketTone", "risks", "themes", "anomalies", "news", "narrativeMode", "disclaimer", "updatedAt"):
            assert k in j
        assert j["disclaimer"] == "仅供研究，不构成投资建议"
        assert j["narrativeMode"] == "template"
        assert set(j["marketTone"]) >= {"phase", "text", "level"}
        item = j["risks"][0]
        for k in ("id", "category", "level", "title", "facts", "symbols", "narrative", "narrativeSource",
                  "evidence", "score", "updatedAt"):
            assert k in item
        assert item["narrativeSource"] == "template"
        c.get("/api/quant/focus")
        assert len(calls) == 1  # 缓存命中


def test_llm_does_not_block_and_applies_after_refresh(tmp_path):
    import threading
    gate = threading.Event()
    def slow_chat(messages, **kw):
        gate.wait(5)
        raise TimeoutError("slow")
    cfg = {"base_url": "http://x", "api_key": "sk-test-key-123456789", "model": "m"}
    with patch.object(fe, "_default_operators", _ops), \
            patch("llm_client.load_config", return_value=cfg), \
            patch.object(fn, "LLM_LOG_DIR", str(tmp_path)), \
            patch("llm_client.chat", slow_chat):
        t0 = time.time()
        r = TestClient(app).get("/api/quant/focus")
        assert time.time() - t0 < 2.0 and r.status_code == 200
        assert r.json()["narrativeMode"] == "template"
        gate.set()


def test_error_returns_500_json():
    with patch.object(fe, "build_focus", side_effect=RuntimeError("boom")):
        r = TestClient(app).get("/api/quant/focus")
    assert r.status_code == 500 and r.json()["status"] == "error"
