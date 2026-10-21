"""Optional OpenAI-backed research advisor.

Paid AI calls are disabled by default. Set ENABLE_OPENAI_ANALYST=true locally
before any request is allowed. Numerical collection/forecasting must continue
to work when this module is disabled or unavailable.
"""
import json
import os
import re
import urllib.request
from pathlib import Path

API_URL = 'https://api.openai.com/v1/chat/completions'
MODEL = os.getenv('AI_MODEL', 'gpt-3.5-turbo')


def _env_file_values():
    values = {}
    try:
        env_path = Path(__file__).resolve().parents[2] / '.env'
        if env_path.is_file():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                name, value = line.split('=', 1)
                values[name.strip()] = value.strip().strip('"').strip("'")
    except Exception:
        pass
    return values


def _setting(name, default=None):
    value = os.getenv(name)
    if value is not None:
        return value
    return _env_file_values().get(name, default)


def is_enabled():
    return str(_setting('ENABLE_OPENAI_ANALYST', 'false')).strip().lower() in (
        '1', 'true', 'yes', 'on')


def _load_key():
    # Standard name first; keep legacy aliases for backward compatibility.
    for name in ('OPENAI_API_KEY', 'OPENAPIKEY', 'OPENAI_KEY'):
        value = _setting(name)
        if value:
            return value
    return None


def _parsed_result(parsed):
    if not isinstance(parsed, dict):
        return None
    try:
        confidence = float(parsed.get('confidence', 0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    hold_seconds = parsed.get('hold_seconds')
    try:
        hold_seconds = int(hold_seconds) if hold_seconds is not None else None
    except (TypeError, ValueError):
        hold_seconds = None
    if hold_seconds is not None:
        hold_seconds = max(0, hold_seconds)
    return {
        'action': parsed.get('action'),
        'confidence': confidence,
        'explanation': parsed.get('explanation'),
        'hold_seconds': hold_seconds,
    }


def ai_suggest(summary_text, ensemble_prob=None, components=None, history_text=None):
    if not is_enabled():
        return None
    key = _load_key()
    if not key:
        return None

    system = (
        "You are a concise crypto market research analyst. Given numeric signals "
        "and context, return BUY_UP, BUY_DOWN, or HOLD, confidence 0..1, and one "
        "short explanation. This is research output, not an execution instruction. "
        "Return only a JSON object."
    )
    sample_json = json.dumps({
        "action": "BUY_UP",
        "confidence": 0.75,
        "explanation": "One short sentence",
    })
    history_block = f"Recent context:\n{history_text}\n\n" if history_text else ""
    user = (
        f"Context:\n{summary_text}\n\n"
        f"{history_block}"
        f"Ensemble probability_up: {ensemble_prob}\n"
        f"Components: {json.dumps(components or {})}\n\n"
        f"Respond with a JSON object like: {sample_json}. "
        "If action is HOLD, you may include integer hold_seconds. Return only JSON."
    )
    payload = {
        'model': os.getenv('AI_MODEL') or _setting('AI_MODEL', MODEL),
        'messages': [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': user},
        ],
        'max_tokens': 150,
        'temperature': 0.0,
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(API_URL, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    req.add_header('Authorization', f'Bearer {key}')
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            response_text = resp.read().decode('utf-8')
        response = json.loads(response_text)
        message = response.get('choices', [{}])[0].get('message', {}).get('content')
        if not message:
            return None
        try:
            return _parsed_result(json.loads(message))
        except Exception:
            match = re.search(r"\{.*\}", message, re.S)
            if match:
                try:
                    return _parsed_result(json.loads(match.group(0)))
                except Exception:
                    return None
    except Exception:
        return None
    return None
