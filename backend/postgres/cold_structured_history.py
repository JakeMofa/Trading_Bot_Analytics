"""Offline/injected-source prototype for explicit, exact structured history pages.

No API registration, credentials, network client, cloud writes or retirement
hooks. A caller must supply a scoped receipt-verifying source and an independently
reviewed manifest of exact immutable envelope hashes. Current qualification is
PP only; a production origin requires a separate role/transport qualification.
"""
from __future__ import annotations

from copy import deepcopy
import time
import uuid

from .archive_codec import ArchiveIntegrityError, ArchiveLimit, ArchiveUnavailable, encoded, sha256
from .history_v2_envelope import HASH, validate_outbox_stream

ORIGIN = 'pp-live-pp'
ENTITIES = frozenset({'core.feature_snapshots', 'core.predictions', 'core.outcomes'})
MAX_ROWS = 50
MAX_BYTES = 256 * 1024
MAX_SECONDS = 4


class ColdStructuredHistory:
    def __init__(self, source, *, origin_id, generation_id, clock=time.monotonic):
        if (origin_id != ORIGIN or getattr(source, 'origin_id', None) != origin_id
                or getattr(source, 'generation_id', None) != generation_id):
            raise ValueError('exact qualified PP source binding required')
        try:
            if str(uuid.UUID(generation_id)) != generation_id:
                raise ValueError()
        except (ValueError, AttributeError, TypeError):
            raise ValueError('canonical generation required') from None
        self.source, self.origin_id, self.generation_id = source, origin_id, generation_id
        self.clock = clock

    def read_page(self, manifest, *, entity_type, market_id, cursor=None):
        """Return one reviewed scope's page; never discover/claim whole-market coverage."""
        if (entity_type not in ENTITIES or not isinstance(market_id, str)
                or not market_id or len(market_id) > 256 or not isinstance(manifest, list)
                or not 1 <= len(manifest) <= 500):
            raise ArchiveLimit('bounded explicit structured history scope required')
        expected, previous = {}, 0
        for entry in manifest:
            if (not isinstance(entry, dict) or set(entry) != {'id', 'envelope_sha256'}
                    or type(entry['id']) is not int or not previous < entry['id'] < 2**63
                    or not isinstance(entry['envelope_sha256'], str)
                    or not HASH.fullmatch(entry['envelope_sha256'])):
                raise ArchiveIntegrityError('invalid or unordered history manifest')
            previous = entry['id']
            expected[previous] = entry['envelope_sha256']
        scope = sha256(encoded(dict(origin_id=self.origin_id, generation_id=self.generation_id,
                                    entity_type=entity_type, market_id=market_id, manifest=manifest)))
        after = 0
        if cursor is not None:
            if (not isinstance(cursor, dict) or set(cursor) != {'scope_sha256', 'after_id'}
                    or cursor['scope_sha256'] != scope or type(cursor['after_id']) is not int
                    or cursor['after_id'] not in expected):
                raise ArchiveIntegrityError('cursor does not match reviewed history scope')
            after = cursor['after_id']
        ids = [key for key in expected if key > after][:MAX_ROWS]
        # Explicit continuation past the final reviewed ID is complete for this
        # manifest only; it never proves the generation or market has no more data.
        records = []
        if ids:
            started = self.clock()
            try:
                records = self.source.read_revisions(ids, max_bytes=MAX_BYTES, timeout_seconds=MAX_SECONDS)
            except (ArchiveIntegrityError, ArchiveLimit, ArchiveUnavailable):
                raise
            except Exception:
                raise ArchiveUnavailable('cold structured source unavailable') from None
            if self.clock() - started >= MAX_SECONDS:
                raise ArchiveLimit('cold structured read deadline reached')
            if not isinstance(records, list) or [r.get('id') for r in records if isinstance(r, dict)] != ids or len(records) != len(ids):
                raise ArchiveIntegrityError('reviewed historical revisions missing or reordered')
            if len(encoded(records)) > MAX_BYTES:
                raise ArchiveLimit('cold structured page byte limit')
            validate_outbox_stream(records, origin_id=self.origin_id, generation_id=self.generation_id)
            for row in records:
                if (row['entity_type'] != entity_type or row['payload'].get('market_id') != market_id
                        or sha256(encoded(row)) != expected[row['id']]):
                    raise ArchiveIntegrityError('historical query scope or exact envelope hash mismatch')
        more = bool(ids and ids[-1] != next(reversed(expected)))
        return {'rows': deepcopy(records),
                'next_cursor': dict(scope_sha256=scope, after_id=ids[-1]) if more else None,
                'coverage': {'status': 'bounded_reviewed_id_page', 'reviewed_ids': len(expected),
                             'returned_ids': ids, 'end_of_reviewed_manifest': not more,
                             'whole_market_coverage': 'not_established'},
                'provenance': {'tier': 'private_structured_history_prototype', 'origin_id': self.origin_id,
                               'generation_id': self.generation_id, 'entity_type': entity_type,
                               'market_id': market_id, 'scope_sha256': scope,
                               'envelope_sha256': [expected[key] for key in ids],
                               'historical_only': True, 'prototype_only': True,
                               'retirement_authority': False, 'official_settlement_inferred': False}}
