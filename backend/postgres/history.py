"""Explicit bounded historical retrieval. Never a current-price fallback."""
from __future__ import annotations

import base64
from dataclasses import replace
from decimal import Decimal
import json
import uuid

from .archive_codec import (ArchiveError, ArchiveIntegrityError, ArchiveLimits,
                            CycleBudget, read_verified, row_cursor, wire)
from .lifecycle import validate_manifest_chain


class HistoryError(ArchiveError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def encode_cursor(generation_id, row):
    payload = json.dumps([generation_id, *row_cursor(row)], separators=(',', ':')).encode()
    return 'v1.' + base64.urlsafe_b64encode(payload).decode().rstrip('=')


def decode_cursor(cursor, generation_id):
    if cursor is None:
        return None
    try:
        if len(cursor) > 2048 or not cursor.startswith('v1.'):
            raise ValueError()
        text = cursor[3:]
        value = json.loads(base64.b64decode(text + '=' * (-len(text) % 4), altchars=b'-_', validate=True))
        if (not isinstance(value, list) or len(value) != 3 or value[0] != generation_id or
                not all(isinstance(item, str) for item in value)):
            raise ValueError()
        return value[1:]
    except (ValueError, UnicodeError, TypeError) as exc:
        raise HistoryError('invalid_cursor', 'history cursor is invalid for this generation') from exc


class ArchiveHistory:
    def __init__(self, repository, transport=None, limits=ArchiveLimits()):
        self.repository, self.transport, self.limits = repository, transport, limits

    def read_generation(self, generation_id, *, dataset='raw.events', limit=100,
                        after_event_id=None):
        try:
            if str(uuid.UUID(generation_id)) != generation_id:
                raise ValueError()
        except (ValueError, AttributeError, TypeError) as exc:
            raise HistoryError('invalid_generation', 'generation must be a canonical UUID') from exc
        if dataset != 'raw.events':
            raise HistoryError('unsupported_dataset', 'only raw.events has archived retrieval in CP4')
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise HistoryError('invalid_limit', 'history limit must be 1..500')
        after = decode_cursor(after_event_id, generation_id)
        try:
            generation, local, more = self.repository.local_history(
                generation_id, after, replace(self.limits, max_rows=min(limit, self.limits.max_rows)))
            if local is not None:
                return self._result(generation, wire(local), more, 'local_postgres', [])
            if self.transport is None:
                raise HistoryError('archive_disabled', 'archived history transport is not configured')
            manifests = self.repository.manifests(generation_id)
            digest = validate_manifest_chain(manifests, generation)
            if digest != generation['seal_hash']:
                raise ArchiveIntegrityError('archived generation catalog changed')
            budget = CycleBudget(self.limits)
            rows, hashes, more = [], [], False
            for index, manifest in enumerate(manifests):
                last = manifest['coverage']['last']
                if after is not None and last is not None and last <= after:
                    continue
                decoded = read_verified(self.transport, manifest, budget)
                candidates = [row for row in decoded if after is None or row_cursor(row) > after]
                space = limit - len(rows)
                rows.extend(candidates[:space])
                hashes.append(manifest['sha256'])
                if len(rows) == limit:
                    more = len(candidates) > space or index < len(manifests) - 1
                    break
            return self._result(generation, rows, more, 'authenticated_archive', hashes)
        except HistoryError:
            raise
        except ArchiveError as exc:
            raise HistoryError(exc.code, str(exc)) from exc
        except (OSError, TimeoutError) as exc:
            raise HistoryError('archive_unavailable', 'historical archive retrieval failed') from exc

    @staticmethod
    def _result(generation, rows, more, tier, hashes):
        return {'rows': rows, 'next_cursor': encode_cursor(generation['generation_id'], rows[-1]) if more and rows else None,
                'complete': not more,
                'provenance': {'tier': tier, 'origin_id': generation['origin_id'],
                               'generation_id': generation['generation_id'], 'dataset': 'raw.events',
                               'state': generation['state'], 'sha256': hashes,
                               'sealed_at': wire(generation.get('sealed_at')),
                               'historical_only': True, 'official_settlement': False}}

    def price_inputs(self, generation_id, **kwargs):
        """Offline calculation hook; keeps original source/provenance and NULLs.

        Deliberately separate from live forecast functions. Consumers explicitly
        select compatible source/symbol/time and label exchange reference inputs.
        """
        result = self.read_generation(generation_id, **kwargs)
        return {**result, 'inputs': [
            {'origin_id': row['origin_id'], 'generation_id': row['generation_id'],
             'source': row['source'], 'event_id': row['event_id'],
             'symbol': row.get('symbol'), 'source_time': row.get('source_time'),
             'source_epoch': Decimal(row['source_epoch']) if row.get('source_epoch') is not None else None,
             'price': Decimal(row['price']) if row.get('price') is not None else None,
             'size': Decimal(row['size']) if row.get('size') is not None else None,
             'available_at': row.get('available_at'), 'received_at': row.get('received_at'),
             'payload': row['payload'], 'raw_payload': row.get('raw_payload'),
             'content_hash': row['content_hash']}
            for row in result['rows']]}
