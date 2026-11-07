# -*- coding: utf-8 -*-
"""
「今日关注」AI 解读层：
  * 一批一次调用 LLM，要求返回 JSON（id -> narrative）；
  * 数字一致性校验：narrative 中出现的数字必须都在该条 facts 值 / 标题 / 标签内，否则该条回退模板；
  * 禁用词过滤（买入/卖出/必涨/翻倍/稳赚/满仓…）命中则回退模板；
  * 任何失败（无 Key、超时、非法 JSON、超限）整体降级为模板；
  * 留痕写入 data/llm/focus-YYYY-MM-DD.jsonl（不含 api_key）；
  * 限频：盘中 5 分钟 / 收盘后 30 分钟，每日调用上限默认 200。
"""
import copy
import datetime as _dt
import json
import os
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import llm_client

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LLM_LOG_DIR = os.path.join(BASE_DIR, "data", "llm")

BANNED_WORDS = ("买入", "卖出", "必涨", "必跌", "翻倍", "稳赚", "满仓", "梭哈", "抄底", "加仓", "清仓",
                "建议买", "建议卖", "保证收益", "一定涨", "无风险")
INTRADAY_TTL = 300
OFFHOURS_TTL = 1800
FAIL_RETRY_TTL = 60
DEFAULT_DAILY_LIMIT = 200
MAX_NARRATIVE_LEN = 220
_NUM_RE = re.compile(r"\d+(?:\.\d+)?")

_lock = threading.Lock()
_narr_cache: Dict[str, Tuple[str, float]] = {}      # signature -> (narrative, ts)
_state: Dict[str, Any] = {"last_attempt": 0.0, "last_ok": False, "day": "", "calls": 0, "running": False}


# ----------------------------------------------------------------- 校验

def _bj_now(now: Optional[float] = None) -> _dt.datetime:
    ts = time.time() if now is None else now
    return _dt.datetime.fromtimestamp(ts, _dt.timezone(_dt.timedelta(hours=8)))


def is_intraday(now: Optional[float] = None) -> bool:
    t = _bj_now(now)
    if t.weekday() >= 5:
        return False
    return _dt.time(9, 15) <= t.time() <= _dt.time(15, 0)


def current_ttl(now: Optional[float] = None) -> int:
    return INTRADAY_TTL if is_intraday(now) else OFFHOURS_TTL


def extract_numbers(text: str) -> List[float]:
    return [float(x) for x in _NUM_RE.findall(text or "")]


def allowed_numbers(item: Dict[str, Any]) -> List[float]:
    nums: List[float] = extract_numbers(item.get("title", ""))
    for f in item.get("facts") or []:
        nums.extend(extract_numbers(str(f.get("label", ""))))
        nums.extend(extract_numbers(str(f.get("value", ""))))
    return nums


def numbers_consistent(narrative: str, item: Dict[str, Any]) -> bool:
    allowed = allowed_numbers(item)
    for n in extract_numbers(narrative):
        if not any(abs(n - a) < 1e-9 for a in allowed):
            return False
    return True


def has_banned_word(narrative: str) -> bool:
    return any(w in (narrative or "") for w in BANNED_WORDS)


def validate_narrative(narrative: Any, item: Dict[str, Any]) -> Tuple[bool, str]:
    if not isinstance(narrative, str) or not narrative.strip():
        return False, "empty"
    if len(narrative) > MAX_NARRATIVE_LEN:
        return False, "too_long"
    if has_banned_word(narrative):
        return False, "banned_word"
    if not numbers_consistent(narrative, item):
        return False, "number_mismatch"
    return True, "ok"


def parse_llm_json(text: str) -> Dict[str, str]:
    """解析 LLM 输出为 {id: narrative}；接受数组[{id,narrative}] 或对象 {id: narrative}；非法则抛 ValueError。"""
    s = (text or "").strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.I)
    data: Any = None
    try:
        data = json.loads(s)
    except ValueError:
        m = re.search(r"\[.*\]", s, re.S) or re.search(r"\{.*\}", s, re.S)
        if m:
            data = json.loads(m.group(0))  # 仍非法则抛 ValueError
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        data = data["items"]
    out: Dict[str, str] = {}
    if isinstance(data, list):
        for r in data:
            if isinstance(r, dict) and r.get("id") is not None:
                out[str(r["id"])] = r.get("narrative")
    elif isinstance(data, dict):
        out = {str(k): v for k, v in data.items()}
    else:
        raise ValueError("not json array/object")
    return out


def signature(item: Dict[str, Any]) -> str:
    return json.dumps([item.get("id"), item.get("level"), item.get("title"), item.get("facts")],
                      ensure_ascii=False, sort_keys=True)


# ----------------------------------------------------------------- 留痕与计数

def _write_trace(record: Dict[str, Any], log_dir: Optional[str] = None, now: Optional[float] = None) -> None:
    try:
        d = log_dir or LLM_LOG_DIR
        os.makedirs(d, exist_ok=True)
        day = _bj_now(now).strftime("%Y-%m-%d")
        with open(os.path.join(d, f"focus-{day}.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _daily_limit(cfg: Optional[Dict[str, Any]]) -> int:
    try:
        return int((cfg or {}).get("focus_daily_limit", DEFAULT_DAILY_LIMIT))
    except (TypeError, ValueError):
        return DEFAULT_DAILY_LIMIT


def reset_state() -> None:
    """测试用：清空缓存与计数。"""
    with _lock:
        _narr_cache.clear()
        _state.update({"last_attempt": 0.0, "last_ok": False, "day": "", "calls": 0, "running": False})


# ----------------------------------------------------------------- 提示词

SYSTEM_PROMPT = (
    "你是 A 股行情研究助手，为每条『关注事项』写一句 40~90 字的中文解读。严格规则："
    "1) 只允许引用该条 facts 与 title 中已有的数字，不得新增、换算或推测任何数字；"
    "2) 禁止出现 买入、卖出、必涨、翻倍、稳赚、满仓 等荐股或收益承诺用语，不给操作指令；"
    "3) 写明依据，并说明不确定性；风险级别为 RED/YELLOW 的条目不得弱化风险措辞；"
    "4) 只输出 JSON 数组，每个元素形如 {\"id\": \"...\", \"narrative\": \"...\"}，不要输出其他文字。")


def _build_messages(items: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    payload = [{"id": i["id"], "level": i["level"], "category": i["category"], "title": i["title"],
                "facts": i["facts"]} for i in items]
    return [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]


# ----------------------------------------------------------------- 核心

def refresh(items: List[Dict[str, Any]], *, chat_fn: Optional[Callable] = None, cfg: Optional[Dict[str, Any]] = None,
            now: Optional[float] = None, force: bool = False, log_dir: Optional[str] = None) -> Dict[str, Any]:
    """同步调用一次 LLM 并写缓存（会阻塞，请在后台线程调用）。返回 {'called','accepted','rejected','reason'}。"""
    ts = time.time() if now is None else now
    info = {"called": False, "accepted": 0, "rejected": {}, "reason": ""}
    if not items:
        info["reason"] = "no_items"
        return info
    cfg = cfg if cfg is not None else llm_client.load_config()
    if chat_fn is None and not llm_client.is_available(cfg):
        info["reason"] = "unavailable"
        return info
    day = _bj_now(ts).strftime("%Y-%m-%d")
    with _lock:
        if _state["day"] != day:
            _state.update({"day": day, "calls": 0})
        ttl = current_ttl(ts) if _state["last_ok"] else FAIL_RETRY_TTL
        if not force and ts - _state["last_attempt"] < ttl:
            info["reason"] = "rate_limited"
            return info
        if _state["calls"] >= _daily_limit(cfg):
            info["reason"] = "daily_limit"
            return info
        _state["calls"] += 1
        _state["last_attempt"] = ts
        _state["last_ok"] = False

    messages = _build_messages(items)
    fn = chat_fn or (lambda m: llm_client.chat(m, cfg=cfg, timeout=min(float((cfg or {}).get("timeout", 60)), 60.0)))
    record: Dict[str, Any] = {"ts": int(ts * 1000), "input": messages[1]["content"], "output": None,
                              "accepted": [], "rejected": {}, "error": None}
    info["called"] = True
    try:
        raw = fn(messages)
        record["output"] = raw
        result = parse_llm_json(raw)
    except Exception as e:  # 超时 / 非法 JSON / 网络
        record["error"] = f"{type(e).__name__}: {e}"[:300]
        info["reason"] = "llm_error"
        _write_trace(record, log_dir, ts)
        return info

    for it in items:
        ok, why = validate_narrative(result.get(it["id"]), it)
        if ok:
            with _lock:
                _narr_cache[signature(it)] = (result[it["id"]].strip(), ts)
            record["accepted"].append(it["id"])
            info["accepted"] += 1
        else:
            record["rejected"][it["id"]] = why
            info["rejected"][it["id"]] = why
    with _lock:
        _state["last_ok"] = info["accepted"] > 0
    info["reason"] = "ok"
    _write_trace(record, log_dir, ts)
    return info


def apply_cached(items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], str]:
    """不触网：把缓存中通过校验的 LLM 文案套到条目上（深拷贝）。返回 (items, narrativeMode)。"""
    out = copy.deepcopy(items)
    n_llm = 0
    for it in out:
        with _lock:
            hit = _narr_cache.get(signature(it))
        if hit and validate_narrative(hit[0], it)[0]:
            it["narrative"] = hit[0]
            it["narrativeSource"] = "llm"
            n_llm += 1
    if not out or n_llm == 0:
        return out, "template"
    return out, "llm" if n_llm == len(out) else "mixed"


def needs_refresh(items: List[Dict[str, Any]], now: Optional[float] = None, cfg: Optional[Dict[str, Any]] = None) -> bool:
    if not items:
        return False
    cfg = cfg if cfg is not None else llm_client.load_config()
    if not llm_client.is_available(cfg):
        return False
    ts = time.time() if now is None else now
    with _lock:
        if _state["running"]:
            return False
        all_cached = all(signature(i) in _narr_cache for i in items)
        ttl = current_ttl(ts) if _state["last_ok"] else FAIL_RETRY_TTL
        if all_cached and ts - _state["last_attempt"] < ttl:
            return False
        return ts - _state["last_attempt"] >= ttl


def refresh_async(items: List[Dict[str, Any]], **kw) -> bool:
    """后台线程刷新，立即返回；已有刷新在跑或无需刷新时返回 False。"""
    if not needs_refresh(items, now=kw.get("now"), cfg=kw.get("cfg")):
        return False
    with _lock:
        if _state["running"]:
            return False
        _state["running"] = True
    snapshot = copy.deepcopy(items)

    def _run():
        try:
            refresh(snapshot, **kw)
        except Exception:
            pass
        finally:
            with _lock:
                _state["running"] = False

    threading.Thread(target=_run, name="focus-narrator", daemon=True).start()
    return True
