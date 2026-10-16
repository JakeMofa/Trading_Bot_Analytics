"""OpenAI-backed advisor (stable copy).
Reads OPENAPIKEY from environment or .env and calls Chat Completions API.
"""
import json
import os
import urllib.request

API_URL = 'https://api.openai.com/v1/chat/completions'
MODEL = os.getenv('AI_MODEL', 'gpt-3.5-turbo')


def _load_key():
    key = os.getenv('OPENAPIKEY') or os.getenv('OPENAI_API_KEY') or os.getenv('OPENAI_KEY')
    if key:
        return key
    # fallback: try to read .env in project root
    try:
        # project root is two levels up from this file (backend/app -> project root)
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        env_path = os.path.join(repo_root, '.env')
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                for line in f:
                    if line.strip().startswith('OPENAPIKEY=') or line.strip().startswith('OPENAI_API_KEY='):
                        k = line.strip().split('=', 1)[1]
                        return k.strip().strip('"')
    except Exception:
        pass
    return None


def ai_suggest(summary_text, ensemble_prob=None, components=None, history_text=None):
    key = _load_key()
    if not key:
        return None
    system = (
        "You are a concise crypto market analyst. Given numeric signals and a short context, "
        "produce a single short recommendation (BUY_UP, BUY_DOWN, or HOLD), a numeric confidence 0..1, "
        "and one-sentence explanation. Return only a JSON object."
    )
    sample_json = json.dumps({"action": "BUY_UP", "confidence": 0.75, "explanation": "One short sentence"})
    # Include a short history string if provided (keeps prompts compact). History should be pre-formatted by the caller.
    history_block = f"Recent history:\n{history_text}\n\n" if history_text else ""
    user = (
        f"Context:\n{summary_text}\n\n{history_block}Ensemble probability_up: {ensemble_prob}\n"
        f"Components: {json.dumps(components or {})}\n\n"
        f"Respond with a JSON object like: {sample_json}. If you recommend HOLD, include an integer field 'hold_seconds' estimating how long to hold (seconds). Example: {json.dumps({'action':'HOLD','confidence':0.6,'explanation':'Wait for volatility to settle','hold_seconds':300})}. Return only JSON.")
    payload = {
        'model': MODEL,
        'messages': [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': user}
        ],
        'max_tokens': 150,
        'temperature': 0.0
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(API_URL, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    req.add_header('Authorization', f'Bearer {key}')
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            text = resp.read().decode('utf-8')
            res = json.loads(text)
            msg = res.get('choices', [{}])[0].get('message', {}).get('content')
            if not msg:
                return None
            try:
                parsed = json.loads(msg)
                return {'action': parsed.get('action'), 'confidence': float(parsed.get('confidence', 0)), 'explanation': parsed.get('explanation')}
            except Exception:
                import re
                m = re.search(r"\{.*\}", msg, re.S)
                if m:
                    try:
                        parsed = json.loads(m.group(0))
                        return {'action': parsed.get('action'), 'confidence': float(parsed.get('confidence', 0)), 'explanation': parsed.get('explanation')}
                    except Exception:
                        return None
    except Exception:
        return None
    return None
