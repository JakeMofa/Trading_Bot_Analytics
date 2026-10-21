"""Research decision rules for the experimental ensemble.

These are directional research labels only. They do not represent actual
positions or execution state. In particular, a prior model suggestion must
never be treated as proof that a position exists.
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
    decision_action: one of 'BUY_UP','BUY_DOWN','HOLD'
    decision_confidence: float 0..1
    decision_summary: one of 'HOLD','BUY','BUY_MORE'
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

    # Map to a research summary. No SELL is inferred without real position state.
    summary = 'HOLD'
    if action == 'HOLD':
        summary = 'HOLD'
    elif action.startswith('BUY'):
        # strong confidence -> buy more
        summary = 'BUY_MORE' if conf >= BUY_MORE_THRESHOLD else 'BUY'
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
