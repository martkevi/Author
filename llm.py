"""OpenRouter client with retries, usage tracking and robust JSON parsing."""
import json
import logging
import re
import threading
import time

import requests

import config

log = logging.getLogger(__name__)
URL = "https://openrouter.ai/api/v1/chat/completions"

_usage = {"tokens": 0}
_lock = threading.Lock()


class LLMError(Exception):
    pass


class FatalLLMError(LLMError):
    """Bad key, no credits, or wrong model name. Retrying will not help."""


def take_usage() -> int:
    """Return tokens used since last call and reset the counter."""
    with _lock:
        t = _usage["tokens"]
        _usage["tokens"] = 0
    return t


def chat(system: str, user: str, model: str, temperature: float = 0.8,
         max_tokens: int = 4000, timeout: int = 600) -> str:
    payload = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
    }
    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "X-Title": "Author Agent",
    }
    last = None
    for attempt in range(6):
        try:
            r = requests.post(URL, headers=headers, json=payload, timeout=timeout)
            if r.status_code in (401, 402, 403, 404):
                raise FatalLLMError(f"OpenRouter HTTP {r.status_code}: {r.text[:300]}")
            if r.status_code in (408, 409, 425, 429, 500, 502, 503, 504):
                raise LLMError(f"HTTP {r.status_code}")
            r.raise_for_status()
            data = r.json()
            if "error" in data:
                raise LLMError(str(data["error"])[:300])
            content = (data["choices"][0]["message"].get("content") or "").strip()
            if not content:
                raise LLMError("empty response")
            with _lock:
                _usage["tokens"] += int((data.get("usage") or {}).get("total_tokens", 0))
            return content
        except FatalLLMError:
            raise
        except Exception as e:  # network, timeout, transient API errors
            last = e
            wait = min(60, 4 * (attempt + 1) ** 2)
            log.warning("LLM attempt %d failed (%s). Retrying in %ss", attempt + 1, e, wait)
            time.sleep(wait)
    raise LLMError(f"OpenRouter failed repeatedly: {last}")


def extract_json(text: str):
    """Pull the first valid JSON object/array out of a model reply."""
    text = re.sub(r"```(?:json)?", "", text)
    dec = json.JSONDecoder()
    for m in re.finditer(r"[\{\[]", text):
        try:
            obj, _ = dec.raw_decode(text[m.start():])
            return obj
        except json.JSONDecodeError:
            continue
    raise ValueError("no JSON found")


def chat_json(system: str, user: str, model: str, temperature: float = 0.4,
              max_tokens: int = 4000):
    system = system + "\n\nReply with valid JSON only. No commentary, no markdown fences."
    raw = chat(system, user, model, temperature, max_tokens)
    try:
        return extract_json(raw)
    except ValueError:
        pass
    fixed = chat("You repair broken JSON. Output only the corrected valid JSON.",
                 raw[:30000], config.MODEL_FAST, 0.0, max_tokens)
    return extract_json(fixed)
