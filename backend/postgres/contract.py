"""Lossless values shared by local persistence and the private history contract."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
import math
import re
from uuid import UUID

SCHEMA_VERSION = 1
DATABASES = {'preprod': 'tradebot_pp', 'production': 'tradebot_prod'}
_TIMESTAMP = re.compile(r'^(\d{4}-\d{2}-\d{2})[Tt](\d{2}:\d{2}:\d{2})(?:\.(\d+))?([Zz]|[+-]\d{2}:\d{2})$')


def source_timestamp(value):
    """Return original RFC3339 text and exact epoch seconds, without float loss.

    PostgreSQL TIMESTAMPTZ has microsecond resolution. Epoch NUMERIC is the
    authoritative sortable source instant; original spelling stays evidence.
    Leap seconds are rejected, not silently changed to a different instant.
    """
    if not isinstance(value, str) or not (match := _TIMESTAMP.fullmatch(value)):
        raise ValueError('source time must be an explicit RFC3339 instant')
    day, clock, fraction, offset = match.groups()
    if offset.upper() == 'Z':
        offset = '+00:00'
    elif offset == '-00:00':
        raise ValueError('unknown RFC3339 offset is not an exact instant')
    if int(offset[1:3]) > 23 or int(offset[4:6]) > 59:
        raise ValueError('invalid timestamp offset')
    instant = datetime.fromisoformat(f'{day}T{clock}{offset}').astimezone(timezone.utc)
    delta = instant - datetime(1970, 1, 1, tzinfo=timezone.utc)
    whole = delta.days * 86400 + delta.seconds
    with localcontext() as context:
        context.prec = max(40, len(fraction or '') + 20)
        epoch = Decimal(whole) + (Decimal('0.' + fraction) if fraction else Decimal(0))
    return value, epoch


def exact_decimal(value, *, nullable=False):
    if value is None and nullable:
        return None
    if isinstance(value, (float, bool)) or not isinstance(value, (str, int, Decimal)):
        raise ValueError('exact decimal requires decimal text, integer, or Decimal')
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError('invalid decimal') from exc
    if not result.is_finite():
        raise ValueError('decimal must be finite')
    return result


def _json_value(value):
    if isinstance(value, Decimal):
        return str(exact_decimal(value))
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError('nonfinite JSON number')
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError('JSON object keys must be text')
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def canonical_json(value):
    return json.dumps(_json_value(value), sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False)


def content_hash(value):
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


def generation_id(value):
    if not isinstance(value, str):
        raise ValueError('generation identity must be UUID text')
    try:
        canonical = str(UUID(value))
    except (ValueError, AttributeError) as exc:
        raise ValueError('generation identity must be UUID text') from exc
    if canonical != value:
        raise ValueError('generation identity must be canonical lowercase UUID text')
    return canonical


def partition_name(value):
    return 'events_g_' + generation_id(value).replace('-', '')
