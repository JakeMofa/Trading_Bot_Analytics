"""Strict normalized input and JSON boundaries; source spelling is evidence."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json


def utcnow():
    return datetime.now(timezone.utc)


def timestamp(value):
    result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('timestamp requires an explicit timezone')
    return result.astimezone(timezone.utc)


def decimal_text(value, *, positive=False):
    if isinstance(value, (float, bool)):
        raise ValueError('financial decimals require a string, Decimal or integer')
    try:
        number = Decimal(value)
    except (InvalidOperation, TypeError):
        raise ValueError('invalid decimal') from None
    if not number.is_finite() or (positive and number <= 0):
        raise ValueError('invalid decimal range')
    return str(value)


def json_value(value):
    if isinstance(value, datetime):
        return timestamp(value).isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_value(item) for item in value]
    return value


def canonical(value):
    return json.dumps(json_value(value), sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def bound(value, maximum=500):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ValueError(f'limit must be between 1 and {maximum}')
    return value
