# -*- coding: utf-8 -*-
import json
import os
import sys
import time

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for d in (os.path.join(BASE_DIR, "scripts"), os.path.join(BASE_DIR, "web")):
    if d not in sys.path:
        sys.path.insert(0, d)

import focus_engine as fe
import focus_narrator as fn
import llm_client

CFG = {"base_url": "http://x/v1", "api_key": "sk-test-key-123456789", "model": "m", "timeout": 5}


def _item():
    return fe._make_item(id="risk-a", category="RISK", level="RED", title="连板梯队出现断层",
                         facts=[fe._fact("最高板", 5, "板"), fe._fact("炸板数", 4, "家"),
                                fe._fact("封板成功率", 66.7, "%")], score=80)


@pytest.fixture(autouse=True)
def _clean():
    fn.reset_state()
    yield
    fn.reset_state()


def _chat_returning(text):
    return lambda messages: text


def _run(chat, tmp_path, items=None, **kw):
    items = items or [_item()]
    info = fn.refresh(items, chat_fn=chat, cfg=CFG, log_dir=str(tmp_path), **kw)
    return info, fn.apply_cached(items)


def test_valid_llm_narrative_accepted(tmp_path):
    txt = json.dumps([{"id": "risk-a", "narrative": "最高板5板、炸板4家，封板成功率66.7%，断层说明承接不足，后续存在不确定性。"}],
                     ensure_ascii=False)
    info, (items, mode) = _run(_chat_returning(txt), tmp_path)
    assert info["accepted"] == 1 and mode == "llm"
    assert items[0]["narrativeSource"] == "llm"
    logs = os.listdir(tmp_path)
    assert len(logs) == 1 and logs[0].startswith("focus-") and logs[0].endswith(".jsonl")
    rec = json.loads(open(tmp_path / logs[0], encoding="utf-8").read().splitlines()[0])
    assert rec["accepted"] == ["risk-a"] and "sk-test" not in json.dumps(rec)


def test_tampered_number_rejected(tmp_path):
    txt = json.dumps([{"id": "risk-a", "narrative": "最高板8板，风险较高。"}], ensure_ascii=False)
    info, (items, mode) = _run(_chat_returning(txt), tmp_path)
    assert info["rejected"]["risk-a"] == "number_mismatch"
    assert mode == "template" and items[0]["narrativeSource"] == "template"
    assert items[0]["narrative"].startswith("连板梯队出现断层")


def test_banned_words_rejected(tmp_path):
    for w in ("建议买入", "必涨", "稳赚", "翻倍", "满仓"):
        fn.reset_state()
        txt = json.dumps([{"id": "risk-a", "narrative": f"最高板5板，{w}。"}], ensure_ascii=False)
        info, (items, mode) = _run(_chat_returning(txt), tmp_path)
        assert info["rejected"]["risk-a"] == "banned_word", w
        assert items[0]["narrativeSource"] == "template"


def test_mixed_mode(tmp_path):
    a, b = _item(), fe._make_item(id="risk-b", category="RISK", level="YELLOW", title="空间龙孤立",
                                  facts=[fe._fact("最高板", 6, "板")])
    txt = json.dumps({"risk-a": "最高板5板，需谨慎。", "risk-b": "最高板9板"}, ensure_ascii=False)
    info, (items, mode) = _run(_chat_returning(txt), tmp_path, items=[a, b])
    assert mode == "mixed"
    assert [i["narrativeSource"] for i in items] == ["llm", "template"]


def test_invalid_json_degrades(tmp_path):
    info, (items, mode) = _run(_chat_returning("这不是JSON"), tmp_path)
    assert info["reason"] == "llm_error" and mode == "template"


def test_timeout_degrades(tmp_path):
    def boom(messages):
        raise TimeoutError("timed out")
    info, (items, mode) = _run(boom, tmp_path)
    assert info["reason"] == "llm_error" and mode == "template"
    assert items[0]["narrativeSource"] == "template"


def test_no_key_unavailable(tmp_path):
    info = fn.refresh([_item()], cfg={"base_url": "http://x", "api_key": "在此填入你的 DeepSeek API Key", "model": "m"},
                      log_dir=str(tmp_path))
    assert info["reason"] == "unavailable" and not info["called"]
    assert not llm_client.is_available({"base_url": "http://x", "api_key": "", "model": "m"})
    assert not llm_client.has_valid_key(None)
    assert llm_client.is_available(CFG)
    with pytest.raises(llm_client.LLMError):
        llm_client.chat([{"role": "user", "content": "hi"}], cfg={"api_key": ""})


def test_missing_config_file(tmp_path):
    assert llm_client.load_config(str(tmp_path / "nope.json")) is None


def test_rate_limit_and_daily_cap(tmp_path):
    calls = []
    def chat(m):
        calls.append(1)
        return json.dumps([{"id": "risk-a", "narrative": "最高板5板。"}], ensure_ascii=False)
    t0 = 1_800_000_000.0
    fn.refresh([_item()], chat_fn=chat, cfg=CFG, now=t0, log_dir=str(tmp_path))
    r2 = fn.refresh([_item()], chat_fn=chat, cfg=CFG, now=t0 + 10, log_dir=str(tmp_path))
    assert r2["reason"] == "rate_limited" and len(calls) == 1
    fn.refresh([_item()], chat_fn=chat, cfg=CFG, now=t0 + 10, force=True, log_dir=str(tmp_path))
    assert len(calls) == 2
    fn.reset_state()
    cfg = dict(CFG, focus_daily_limit=1)
    fn.refresh([_item()], chat_fn=chat, cfg=cfg, now=t0, log_dir=str(tmp_path))
    r = fn.refresh([_item()], chat_fn=chat, cfg=cfg, now=t0 + 5000, log_dir=str(tmp_path))
    assert r["reason"] == "daily_limit"


def test_ttl_intraday_vs_after_close():
    # 2027-01-04 周一 10:00 北京时间 = 02:00 UTC
    import datetime as dt
    mon_10 = dt.datetime(2027, 1, 4, 2, 0, tzinfo=dt.timezone.utc).timestamp()
    mon_20 = dt.datetime(2027, 1, 4, 12, 0, tzinfo=dt.timezone.utc).timestamp()
    assert fn.current_ttl(mon_10) == 300 and fn.current_ttl(mon_20) == 1800


def test_number_checks():
    it = _item()
    assert fn.numbers_consistent("最高板5板，成功率66.7%", it)
    assert not fn.numbers_consistent("成功率66.8%", it)
    assert fn.parse_llm_json("```json\n[{\"id\":\"a\",\"narrative\":\"x\"}]\n```") == {"a": "x"}
