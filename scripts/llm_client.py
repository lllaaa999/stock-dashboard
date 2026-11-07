# -*- coding: utf-8 -*-
"""统一 LLM 客户端：读取 config/llm.local.json，OpenAI 兼容 /chat/completions。日志绝不输出 api_key。"""
import json
import os
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG_PATH = os.path.join(BASE_DIR, "config", "llm.local.json")

_PLACEHOLDER_HINTS = ("在此填入", "your", "xxxx", "<", "placeholder", "api_key", "changeme", "请填入")


class LLMError(Exception):
    """LLM 调用失败（错误信息已脱敏，不含 key）。"""


def load_config(path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    p = path or DEFAULT_CONFIG_PATH
    try:
        with open(p, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg if isinstance(cfg, dict) else None
    except (OSError, ValueError):
        return None


def has_valid_key(cfg: Optional[Dict[str, Any]]) -> bool:
    if not cfg:
        return False
    key = str(cfg.get("api_key") or "").strip()
    if len(key) < 8:
        return False
    low = key.lower()
    return not any(h in low for h in _PLACEHOLDER_HINTS)


def is_available(cfg: Optional[Dict[str, Any]] = None, path: Optional[str] = None) -> bool:
    cfg = cfg if cfg is not None else load_config(path)
    return has_valid_key(cfg) and bool(str((cfg or {}).get("base_url") or "").strip()) \
        and bool(str((cfg or {}).get("model") or "").strip())


def _redact(text: str, key: str) -> str:
    return text.replace(key, "***") if key else text


def chat(messages: List[Dict[str, str]], cfg: Optional[Dict[str, Any]] = None, timeout: Optional[float] = None,
         temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> str:
    """返回助手文本；不可用或失败抛 LLMError。"""
    cfg = cfg if cfg is not None else load_config()
    if not is_available(cfg):
        raise LLMError("LLM 未配置或 key 无效")
    key = str(cfg["api_key"]).strip()
    url = str(cfg["base_url"]).rstrip("/") + "/chat/completions"
    body = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": cfg.get("temperature", 0.3) if temperature is None else temperature,
        "max_tokens": cfg.get("max_tokens", 2000) if max_tokens is None else max_tokens,
    }
    req = urllib.request.Request(
        url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AlphaPulse/1.1",
        })
    t = float(timeout if timeout is not None else cfg.get("timeout", 60))
    try:
        with urllib.request.urlopen(req, timeout=t) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return str(payload["choices"][0]["message"]["content"] or "")
    except urllib.error.HTTPError as e:
        raise LLMError(f"HTTP {e.code}") from None
    except Exception as e:  # 超时、网络、解析
        raise LLMError(_redact(f"{type(e).__name__}: {e}", key)) from None
