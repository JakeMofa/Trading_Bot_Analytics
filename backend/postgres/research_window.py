"""Offline bounded research composition; no API, credentials, writes or activation.

The supplied raw reader verifies local/archive history. The injected revision
source must be the existing receipt-verifying source; explicit envelope hashes
also bind the reviewed immutable records. This is not whole-market discovery.
"""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
import time
import re
import uuid

from .archive_codec import ArchiveIntegrityError, ArchiveLimit, ArchiveUnavailable, encoded, sha256
from .history_v2_envelope import HASH, validate_outbox_stream
from .history import ArchiveHistory

TABLES = frozenset({'core.protected_evidence', 'core.snapshot_evidence',
                   'core.feature_snapshots', 'core.predictions', 'core.outcomes'})


def instant(value):
    try:
        fraction = re.search(r'T\d{2}:\d{2}:\d{2}[.,](\d+)', value)
        if fraction and len(fraction[1]) > 6:
            raise ValueError()
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if result.tzinfo is None:
            raise ValueError()
        return result.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError):
        raise ArchiveIntegrityError('research timestamp needs an explicit offset') from None


def epoch(value):
    delta = value - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return Decimal(delta.days * 86400 + delta.seconds) + Decimal(delta.microseconds) / 1000000


def same_final(left, right):
    if left is None or right is None:
        return left is None and right is None
    try:
        a, b = Decimal(str(left)), Decimal(str(right))
        return a.is_finite() and b.is_finite() and a == b
    except (InvalidOperation, ValueError):
        return False


class ResearchWindow:
    """One exact generation/market, 900 seconds, <=50 reviewed revisions.

    Raw scan is limited to four verified 500-row pages; larger generations are
    explicitly unsupported. Twenty seconds covers composition; remote requests remain capped at four seconds.
    Labels use their own explicit cutoff and never enter predictor inputs.
    """
    def __init__(self, raw_history, revisions, *, origin_id, generation_id,
                 clock=time.monotonic):
        if (origin_id != 'pp-live-pp' and not origin_id.startswith('generated-')):
            raise ValueError('PP or generated research origin required')
        if (str(uuid.UUID(generation_id)) != generation_id or
                revisions.origin_id != origin_id or revisions.generation_id != generation_id):
            raise ValueError('exact revision source binding required')
        self.raw, self.revisions = raw_history, revisions
        self.origin, self.generation, self.clock = origin_id, generation_id, clock

    def read(self, manifest, *, market_id, start, end, as_of, labels_as_of):
        begun = self.clock()
        def remaining():
            left = 20 - (self.clock() - begun)
            if left <= 0:
                raise ArchiveLimit('research window deadline')
            return left
        starts, ends, cutoff, label_cutoff = map(instant, (start, end, as_of, labels_as_of))
        if (not isinstance(market_id, str) or not market_id or len(market_id) > 256
                or epoch(starts) % 900 != 0 or (ends - starts).total_seconds() != 900
                or not starts <= cutoff <= ends
                or label_cutoff < cutoff or not isinstance(manifest, list)
                or not 1 <= len(manifest) <= 50):
            raise ArchiveLimit('explicit bounded 15-minute research scope required')
        ids, hashes, previous = [], {}, 0
        for item in manifest:
            if (not isinstance(item, dict) or set(item) != {'id', 'envelope_sha256'}
                    or type(item['id']) is not int or not previous < item['id'] < 2**63
                    or not isinstance(item['envelope_sha256'], str)
                    or not HASH.fullmatch(item['envelope_sha256'])):
                raise ArchiveIntegrityError('invalid reviewed research manifest')
            previous = item['id']; ids.append(previous); hashes[previous] = item['envelope_sha256']
        try:
            records = self.revisions.read_revisions(ids, max_bytes=256*1024,
                                                   timeout_seconds=min(4, remaining()))
        except (ArchiveIntegrityError, ArchiveLimit, ArchiveUnavailable):
            raise
        except Exception:
            raise ArchiveUnavailable('research revision source unavailable') from None
        remaining()
        if (not isinstance(records, list) or len(records) != len(ids)
                or [r.get('id') for r in records if isinstance(r, dict)] != ids):
            raise ArchiveIntegrityError('missing or reordered research revisions')
        if len(encoded(records)) > 256*1024:
            raise ArchiveLimit('research revision byte bound')
        validate_outbox_stream(records, origin_id=self.origin, generation_id=self.generation)
        by_table = {table: [] for table in TABLES}
        entities = set()
        for row in records:
            key = (row['entity_type'], row['entity_id'])
            if (row['entity_type'] not in TABLES or key in entities
                    or sha256(encoded(row)) != hashes[row['id']]):
                raise ArchiveIntegrityError('unreviewed or duplicate research entity')
            entities.add(key)
            payload = row['payload']
            if row['entity_type'] != 'core.snapshot_evidence' and payload.get('market_id') != market_id:
                raise ArchiveIntegrityError('research market mismatch')
            if row['entity_type'] == 'core.protected_evidence' and payload.get('generation_id') != self.generation:
                raise ArchiveIntegrityError('research evidence generation mismatch')
            by_table[row['entity_type']].append(deepcopy(payload))
        raw, seen, cursor = [], set(), None
        tiers = []
        lower, upper = epoch(starts), epoch(ends)
        for _ in range(4):
            remaining()
            left = remaining()
            raw_page = ArchiveHistory(self.raw.repository, self.raw.transport,
                replace(self.raw.limits, max_seconds=left,
                        request_timeout_seconds=min(left, self.raw.limits.request_timeout_seconds)))
            page = raw_page.read_generation(self.generation, limit=500, after_event_id=cursor)
            remaining()
            provenance = page['provenance']
            if (provenance['origin_id'], provenance['generation_id']) != (self.origin, self.generation):
                raise ArchiveIntegrityError('raw research scope mismatch')
            tiers.append(provenance)
            for row in page['rows']:
                key = tuple(row[k] for k in ('origin_id', 'generation_id', 'source', 'event_id'))
                if key[:2] != (self.origin, self.generation) or key in seen:
                    raise ArchiveIntegrityError('duplicate or foreign research input')
                seen.add(key)
                source_at = row.get('source_epoch')
                if (row.get('market_id') == market_id and row['source'] == 'polymarket_us'
                        and row['kind'] in ('market', 'quote') and source_at is not None
                        and lower <= Decimal(source_at) < upper
                        and instant(row['received_at']) <= cutoff
                        and instant(row['available_at']) <= cutoff
                        and Decimal(source_at) <= epoch(cutoff)):
                    raw.append(deepcopy(row))
            cursor = page['next_cursor']
            if cursor is None:
                break
        if cursor is not None:
            raise ArchiveLimit('research generation exceeds four raw pages')
        evidence = {r['evidence_id']: r for r in by_table['core.protected_evidence']}
        snapshots = {r['snapshot_id']: r for r in by_table['core.feature_snapshots']}
        edges = by_table['core.snapshot_evidence']
        linked = {}
        for edge in edges:
            sid, eid = edge['snapshot_id'], edge['evidence_id']
            if sid not in snapshots or eid not in evidence:
                raise ArchiveIntegrityError('research evidence link is incomplete')
            linked.setdefault(sid, []).append(evidence[eid])
        features = []
        for sid, snapshot in snapshots.items():
            stamp = instant(snapshot['as_of'])
            publications = [e for e in linked.get(sid, []) if e['source'] == 'calculation_inputs'
                            and e['kind'] == 'feature_inputs' and e['event_id'] == sid]
            if len(publications) != 1:
                raise ArchiveIntegrityError('snapshot publication availability unproved')
            publication = publications[0]
            if publication['payload'] != snapshot['evidence_json']:
                raise ArchiveIntegrityError('saved calculation inputs differ')
            calculation = snapshot['evidence_json']
            market = calculation.get('market', {})
            if instant(market.get('first_seen')) > stamp:
                raise ArchiveIntegrityError('market metadata arrived after saved feature time')
            price = calculation.get('price') or {}
            for name in ('source_time', 'received_at'):
                if price.get(name) is not None and instant(price[name]) > stamp:
                    raise ArchiveIntegrityError('saved reference input is from the future')
            for candle in calculation.get('candle_inputs', []):
                if (instant(candle.get('received_at')) > stamp
                        or instant(candle.get('start')) + timedelta(seconds=60) > stamp):
                    raise ArchiveIntegrityError('saved candle input was unavailable')
            for proof in linked[sid]:
                if proof is not publication and instant(proof['available_at']) > stamp:
                    raise ArchiveIntegrityError('saved evidence arrived after feature time')
            if (starts <= stamp < ends and stamp <= cutoff
                    and all(instant(e['available_at']) <= cutoff and instant(e['received_at']) <= cutoff
                            for e in linked[sid])):
                features.append(snapshot)
        selected = {r['snapshot_id']: r for r in features}
        forecasts = []
        for prediction in by_table['core.predictions']:
            sid = prediction['snapshot_id']
            if sid not in snapshots or instant(prediction['as_of']) != instant(snapshots[sid]['as_of']):
                raise ArchiveIntegrityError('saved forecast snapshot link differs')
            if sid in selected and instant(prediction['created_at']) <= cutoff:
                forecasts.append(prediction)
        labels = []
        for outcome in by_table['core.outcomes']:
            proof = evidence.get(outcome['evidence_id'])
            # Store.ingest wraps captured data/provenance; _protect adds only
            # normalized price/size/symbol beside that wrapper. Never accept a
            # flattened synthetic result as proof of an ingested outcome.
            captured = proof.get('payload') if proof else None
            outcome_payload = outcome.get('payload')
            if (not proof or proof['source'] != 'polymarket_us' or proof['kind'] != 'outcome'
                    or proof['event_id'] != outcome['outcome_id']
                    or not isinstance(captured, dict)
                    or not isinstance(captured.get('data'), dict)
                    or not isinstance(captured.get('provenance'), dict)
                    or not isinstance(outcome_payload, dict)
                    or outcome_payload.get('data') != captured['data']
                    or outcome_payload.get('provenance') != captured['provenance']
                    or captured['data'].get('result') != outcome['result']
                    or not same_final(captured['data'].get('final'), outcome['final'])):
                raise ArchiveIntegrityError('official outcome evidence unproved')
            if all(instant(r[k]) <= label_cutoff for r, k in
                   ((outcome, 'available_at'), (outcome, 'confirmed_at'),
                    (proof, 'received_at'), (proof, 'available_at'))) and all(
                        r.get('source_time') is None or instant(r['source_time']) <= label_cutoff
                        for r in (outcome, proof)):
                labels.append(outcome)
        result = {'scope': dict(origin_id=self.origin, generation_id=self.generation, market_id=market_id,
                               start=start, end=end, as_of=as_of, labels_as_of=labels_as_of),
                  'inputs': raw, 'saved_features': features, 'saved_forecasts': forecasts,
                  'official_outcome_labels': labels,
                  'links': [e for e in edges if e['snapshot_id'] in selected],
                  'coverage': {'status': 'reviewed_manifest_only', 'whole_market': 'not_established',
                               'raw_generation_scan_complete': True, 'recomputed_features': False},
                  'provenance': {'raw_pages': tiers, 'reviewed_envelope_hashes': hashes,
                                 'prototype_only': True, 'retirement_authority': False}}
        remaining()
        if len(encoded(result)) > 2*1024**2:
            raise ArchiveLimit('research response byte bound')
        remaining()
        return result
