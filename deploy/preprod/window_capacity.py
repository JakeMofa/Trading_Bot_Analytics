"""Offline sizing for one isolated two-market PP test; no activation authority."""

from fractions import Fraction
from math import ceil


def estimate(*, elapsed, initial_a, final_a, rows_added, db_growth, retained_a, retained_rows):
    """Project the measured interval across the longest possible alignment and lease."""
    values = (elapsed, initial_a, final_a, rows_added, db_growth, retained_a, retained_rows)
    if any(type(value) is not int or value < 0 for value in values):
        raise ValueError('measurements must be nonnegative integer seconds, bytes or counts')
    if not elapsed or final_a <= initial_a or not rows_added or not db_growth:
        raise ValueError('an advancing interval is required')
    raw_rate = Fraction(final_a - initial_a, elapsed)
    # Within the 4,560-second lease, allow a 30-second switcher tick after
    # alignment plus two markets, and up to two ticks around the B OFF.
    a_seconds, b_seconds = 2730, 1860
    candidate = 96 * 1024**2
    a = retained_a + ceil(raw_rate * a_seconds)
    b = ceil(raw_rate * b_seconds)
    projected_rows = retained_rows + ceil(Fraction(rows_added * a_seconds, elapsed))
    return {
        'a_relation_bytes': a, 'b_growth_bytes': b,
        'db_growth_bytes_over_max_lease': ceil(Fraction(db_growth * 4560, elapsed)),
        'a_projected_rows': projected_rows, 'minimum_archive_chunks': ceil(projected_rows / 500),
        'existing_32_mib_exceeded': max(a, b) >= 32 * 1024**2,
        'proposal_96_mib_exceeded': max(a, b) >= candidate,
        'suggested_a_margin_bytes': candidate - a,
        'status': 'PROJECTION_ONLY',
    }
