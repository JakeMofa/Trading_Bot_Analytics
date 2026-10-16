"""Analysis helpers: map numeric probabilities + component agreement to qualitative labels and confidence."""

from math import prod


def label_and_confidence(component_probs, ensemble_prob, component_confidences=None):
    """
    component_probs: dict of component_name -> prob_up (0..1)
    ensemble_prob: overall prob_up (0..1)
    component_confidences: dict of component_name -> confidence (0..1)

    Returns: (label, confidence 0..1)
    """
    if component_confidences is None:
        component_confidences = {k: 1.0 for k in component_probs}
    # Agreement metric: how many components are on the same side as ensemble
    side = 1 if ensemble_prob >= 0.5 else 0
    agrees = 0
    weights = 0
    for name, prob in component_probs.items():
        conf = component_confidences.get(name, 1.0)
        weights += conf
        if (prob >= 0.5) == (ensemble_prob >= 0.5):
            agrees += conf
    agreement_ratio = (agrees / weights) if weights > 0 else 0

    # Map probability ranges to labels (configurable thresholds)
    p = ensemble_prob
    if p >= 0.85 and agreement_ratio >= 0.6:
        label = 'Strong UP'
    elif 0.70 <= p < 0.85:
        label = 'Moderate UP'
    elif 0.55 <= p < 0.70:
        label = 'Weak UP'
    elif 0.45 <= p < 0.55 or agreement_ratio < 0.4:
        label = 'Neutral'
    elif 0.30 < p <= 0.45:
        label = 'Weak DOWN'
    elif 0.15 < p <= 0.30:
        label = 'Moderate DOWN'
    else:
        label = 'Strong DOWN'

    # Confidence: geometric mean of agreement and average component confidences
    avg_conf = sum(component_confidences.values())/len(component_confidences) if component_confidences else 0
    conf = (agreement_ratio * avg_conf) ** 0.5
    return label, round(conf, 3)
