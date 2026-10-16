"""Simple OpenAI-backed advisor.
Provides ai_suggest(...) which returns an action/confidence/explanation for the next 15 minutes.
Uses OPENAPIKEY from environment or falls back to reading .env file in project root.
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
        here = os.path.dirname(os.path.dirname(__file__))
        env_path = os.path.join(here, '..', '.env')
        env_path = os.path.abspath(env_path)
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                for line in f:
                    if line.strip().startswith('OPENAPIKEY=') or line.strip().startswith('OPENAI_API_KEY='):
                        k = line.strip().split('=', 1)[1]
                        return k.strip().strip('"')
    except Exception:
        pass
    return None


def ai_suggest(summary_text, ensemble_prob=None, components=None):
    """Call OpenAI Chat Completion to get a short directional suggestion for next 15 minutes.
    Returns dict: {action, confidence, explanation}
    action in ['BUY_UP','BUY_DOWN','HOLD']
    confidence float [0..1]
    explanation string
    """
    key = _load_key()
    if not key:
        return None
    system = "You are a concise crypto market analyst. Given numeric signals and a short context, produce a single short recommendation (BUY_UP, BUY_DOWN, or HOLD), a numeric confidence 0..1, and one-sentence explanation. Keep JSON only in the response."
    sample_json = json.dumps({"action": "BUY_UP", "confidence": 0.75, "explanation": "One short sentence"})
    user = (f"Context:\n{summary_text}\n\nEnsemble probability_up: {ensemble_prob}\n"
            f"Components: {json.dumps(components or {})}\n\n"
            f"Respond with a JSON object like: {sample_json}.")
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
        with urllib.request.urlopen(req, timeout=15) as resp:
            text = resp.read().decode('utf-8')
            res = json.loads(text)
            # extract assistant reply
            msg = res.get('choices', [{}])[0].get('message', {}).get('content')
            if not msg:
                return None
            # try to parse JSON inside message
            try:
                parsed = json.loads(msg)
                action = parsed.get('action')
                confidence = float(parsed.get('confidence', 0))
                explanation = parsed.get('explanation')
                return {'action': action, 'confidence': confidence, 'explanation': explanation}
            except Exception:
                # attempt to find a JSON object substring
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
