"""Decision rules: map qualitative labels + confidence to actionable suggestions.

Actions returned: 'BUY_UP', 'BUY_DOWN', 'SELL_UP', 'SELL_DOWN', 'HOLD'

The logic:
- Strong/Moderate UP with high confidence => BUY_UP
- Strong/Moderate DOWN with high confidence => BUY_DOWN
- Weak signals => HOLD unless confidence crosses a low threshold
- If a previous BUY exists on the opposite side, recommend SELL of that side when a new opposite BUY is suggested
"""
import os
from analysis import label_and_confidence

# Thresholds configurable via environment variables for easy tuning.
# Defaults keep previous behavior: moderate/strong threshold 0.5, weak threshold 0.6, buy-more threshold 0.8
UP_MOD_THRESHOLD = float(os.getenv('DECISION_UP_MOD_THRESHOLD', '0.5'))
WEAK_THRESHOLD = float(os.getenv('DECISION_WEAK_THRESHOLD', '0.6'))
BUY_MORE_THRESHOLD = float(os.getenv('DECISION_BUY_MORE_THRESHOLD', '0.8'))


def decide_action(db, market_id, component_probs, ensemble_prob, component_confidences=None):
    """
    Returns a tuple: (decision_action, decision_confidence_float, decision_summary)
    decision_action: one of 'BUY_UP','BUY_DOWN','SELL_UP','SELL_DOWN','HOLD'
    decision_confidence: float 0..1
    decision_summary: one of 'HOLD','BUY','BUY_MORE','SELL','SELL_MORE'
    """
    label, conf = label_and_confidence(component_probs, ensemble_prob, component_confidences)
    # Basic mapping to directional action
    action = 'HOLD'
    if label in ('Strong UP', 'Moderate UP') and conf >= 0.5:
        action = 'BUY_UP'
    elif label == 'Weak UP' and conf >= 0.6:
        action = 'BUY_UP'
    elif label in ('Strong DOWN', 'Moderate DOWN') and conf >= 0.5:
        action = 'BUY_DOWN'
    elif label == 'Weak DOWN' and conf >= 0.6:
        action = 'BUY_DOWN'
    else:
        action = 'HOLD'

    # Check for recent opposite buy to suggest selling it first
    try:
        row = db.execute("SELECT decision_action FROM predictions WHERE market_id=? AND decision_action IS NOT NULL ORDER BY created_at DESC LIMIT 1", (market_id,)).fetchone()
        if row:
            prev = row[0]
            if prev == 'BUY_UP' and action == 'BUY_DOWN':
                # Suggest closing previous UP position
                action = 'SELL_UP'
            elif prev == 'BUY_DOWN' and action == 'BUY_UP':
                action = 'SELL_DOWN'
    except Exception:
        pass

    # Map to summary: BUY / BUY_MORE / SELL / SELL_MORE / HOLD
    summary = 'HOLD'
    if action == 'HOLD':
        summary = 'HOLD'
    elif action.startswith('BUY'):
        # strong confidence -> buy more
        summary = 'BUY_MORE' if conf >= BUY_MORE_THRESHOLD else 'BUY'
    elif action.startswith('SELL'):
        summary = 'SELL_MORE' if conf >= BUY_MORE_THRESHOLD else 'SELL'

    # For HOLD, also provide hold direction based on ensemble probability (up vs down) via component_probs/ensemble
    hold_dir = None
    try:
        # Determine hold direction from ensemble probability in component_probs average if available
        # As a fallback, use 0.5 comparison of aggregate of component_probs
        agg = ensemble_prob if isinstance(ensemble_prob, (int, float)) else None
        if agg is None:
            # compute crude aggregate from component_probs
            agg = sum(component_probs.values())/len(component_probs) if component_probs else 0.5
        hold_dir = 'HOLD_UP' if agg >= 0.5 else 'HOLD_DOWN'
    except Exception:
        hold_dir = None
    return action, round(conf, 3), summary, hold_dir
