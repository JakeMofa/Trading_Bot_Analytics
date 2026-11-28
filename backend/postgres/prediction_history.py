"""Point-in-time saved forecast history for one configured origin and market."""
import base64
from collections import defaultdict
from pathlib import Path
import time

from .archive_codec import ArchiveIntegrityError, ArchiveLimit, ArchiveUnavailable, encoded, sha256
from .cloud_origin_binding import cloud_binding
from .domain import json_value, timestamp
from .history import HistoryError
from .history_v2_envelope import CLOUD_COLUMNS, cloud_row_matches
from .market_history import BoundedHistoryReader, MAX_GENERATIONS, MAX_PAGE_BYTES, decode
from .pp_history_connection import PPHistoryConnectionFactory

TABLE = 'core.predictions'
FIELDS = CLOUD_COLUMNS[TABLE]
DISPLAY = ('prediction_id', 'snapshot_id', 'market_id', 'model_version', 'as_of', 'created_at',
           'seconds_remaining', 'probability_up', 'probability_down', 'abstain_reason')
MAX_SECONDS = 4
READER_DSN = Path('/run/secrets/pp_prediction_history_reader_dsn')
READER_CA = Path('/run/secrets/pp_history_ca')


def configured_archive(settings, environ):
    flag = environ.get('TRADEBOT_PP_PREDICTION_HISTORY', 'false')
    if flag == 'false':
        return None
    if flag != 'true' or settings.environment != 'preprod' or settings.data_mode != 'pp_live':
        raise ValueError('invalid structured prediction reader configuration')
    return HostedPredictions(settings.origin_id, PPHistoryConnectionFactory(
        READER_DSN, READER_CA, origin_id=settings.origin_id, reader=True))


def select_page(connection, schema, origin, window, after, limit):
    # Only variable-width values from a bounded page can cross the connection.
    # Retain the full hosted projection for comparison with its exact revision.
    from psycopg import sql
    fields = FIELDS if schema == 'history_v2' else (*DISPLAY, 'content_hash')
    cols = sql.SQL(',').join(map(sql.Identifier, fields))
    condition = sql.SQL('')
    params = [origin, window.market_id, window.start, window.end, window.as_of]
    if after:
        condition = sql.SQL(' AND (as_of,prediction_id COLLATE "C") < (%s,%s)')
        params.extend(after)
    rows = connection.execute(sql.SQL('''
        WITH picked AS MATERIALIZED (
            SELECT {cols} FROM {table} WHERE origin_id=%s AND market_id=%s
              AND as_of >= %s AND as_of < %s AND created_at <= %s {after}
            ORDER BY as_of DESC,prediction_id COLLATE "C" DESC LIMIT %s
        ), sized AS (SELECT COALESCE(sum(octet_length(row_to_json(picked)::text)),0) AS bytes FROM picked)
        SELECT {bounded}, sized.bytes FROM picked CROSS JOIN sized
        ORDER BY picked.as_of DESC,picked.prediction_id COLLATE "C" DESC
        ''').format(cols=cols, table=sql.Identifier(schema,'predictions'), after=condition,
                    bounded=sql.SQL(',').join(sql.SQL('CASE WHEN sized.bytes<={} THEN picked.{} END AS {}').format(
                        sql.Literal(MAX_PAGE_BYTES), sql.Identifier(k), sql.Identifier(k)) for k in fields)),
        (*params,limit+1)).fetchall()
    if rows and rows[0]['bytes'] > MAX_PAGE_BYTES:
        raise ArchiveLimit('saved prediction page exceeds byte budget; reduce limit')
    for r in rows:
        del r['bytes']
    return rows


def expected_page(db, origin, window, after, limit):
    # Structured outbox identities survive local raw retirement. Check only
    # the requested market's forecast ledgers when archive coverage is needed.
    return db.execute("""SELECT payload->>'prediction_id' AS id, (payload->>'as_of')::timestamptz AS at,
            generation_id,content_hash,acknowledged_at IS NOT NULL AS acked
        FROM ops.outbox WHERE origin_id=%s AND entity_type='core.predictions'
          AND payload->>'market_id'=%s AND (payload->>'as_of')::timestamptz >= %s
          AND (payload->>'as_of')::timestamptz < %s AND (payload->>'created_at')::timestamptz <= %s
          AND (%s::timestamptz IS NULL OR
            ((payload->>'as_of')::timestamptz,(payload->>'prediction_id') COLLATE "C") < (%s,%s))
        ORDER BY (payload->>'as_of')::timestamptz DESC,(payload->>'prediction_id') COLLATE "C" DESC LIMIT %s""",
        (origin,window.market_id,window.start,window.end,window.as_of,
         after[0] if after else None,*(after or (None,None)),limit+1)).fetchall()


class HostedPredictions:
    def __init__(self, origin, connection_factory):
        self.origin = origin
        self.role = cloud_binding(origin).reader_role
        self.connection_factory = connection_factory

    def page(self, window, after, limit, deadline):
        import psycopg
        from .cold_structured_source import ReadOnlyStructuredSource
        from .history_v2_transport import HistoryV2PostgresTransport
        try:
            with self.connection_factory(timeout_seconds=deadline-time.monotonic()) as db:
                db.read_only = True
                with db.transaction():
                    db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                    HistoryV2PostgresTransport._limit(db,deadline-time.monotonic(),catalog_search_path=True)
                    identity = db.execute('SELECT current_user AS role,current_database() AS db').fetchone()
                    if identity != {'role': self.role, 'db': 'postgres'}:
                        raise ArchiveIntegrityError('prediction archive login mismatch')
                    ReadOnlyStructuredSource._reader_identity(db)
                    rows = select_page(db, 'history_v2', self.origin, window, after, limit)
                    self.verify(db, rows)
        except (psycopg.OperationalError, psycopg.errors.InsufficientPrivilege):
            raise ArchiveUnavailable('scoped prediction archive unavailable') from None
        return rows

    def verify(self, db, projections):
        from .history_v2_transport import HistoryV2PostgresTransport
        if not projections:
            return
        by_entity = {encoded([self.origin,r['prediction_id']]).decode():r for r in projections}
        # The archive receipt index is keyed on origin/type/md5(entity_id).
        # Match the full entity identity too; the hash is only the index lookup.
        found = db.execute("""SELECT k.entity_id, r.generation_id, r.outbox_id
            FROM unnest(%s::text[]) k(entity_id) LEFT JOIN LATERAL (
              SELECT generation_id,outbox_id FROM history_v2.structured_receipts r
              WHERE r.origin_id=%s AND r.entity_type='core.predictions'
              AND md5(r.entity_id)=md5(k.entity_id) AND r.entity_id=k.entity_id
              ORDER BY r.outbox_id DESC LIMIT 1) r ON true""", (list(by_entity),self.origin)).fetchall()
        groups = defaultdict(dict)
        for row in found:
            if row['outbox_id'] is None:
                raise ArchiveIntegrityError('saved prediction missing archive receipt')
            groups[str(row['generation_id'])][row['outbox_id']] = row['entity_id']
        if len(groups)>MAX_GENERATIONS:
            raise ArchiveLimit('prediction revision lookup exceeds generation bound')
        remaining = MAX_PAGE_BYTES
        for gid, ids in groups.items():
            verifier = HistoryV2PostgresTransport(self.connection_factory, origin_id=self.origin,
                generation_id=gid, expected_database='postgres', expected_role=self.role)
            envelopes = verifier._read_revisions(db,sorted(ids),remaining)
            for row in envelopes:
                if row['entity_type'] != TABLE or row['entity_id'] != ids[row['id']] or not cloud_row_matches(
                        row, by_entity[row['entity_id']]):
                    raise ArchiveIntegrityError('saved prediction projection differs from its archive revision')
                remaining -= len(encoded(row))


def render(row, tier):
    item = json_value({k:row[k] for k in DISPLAY})
    item['id'] = item.pop('prediction_id')
    item['tier'] = tier
    return item


class PredictionHistory(BoundedHistoryReader):
    def __init__(self, store, archive=None):
        super().__init__()
        self.store, self.archive = store, archive
        if archive is not None and archive.origin != store.settings.origin_id:
            raise ValueError('prediction archive must match local origin')

    def _read(self, window, cursor, limit, include_archive=False):
        origin = self.store.settings.origin_id
        deadline = time.monotonic()+MAX_SECONDS
        scope = sha256(encoded(['saved_predictions_v1',origin,window.market_id,window.start,window.end,
                                window.as_of,include_archive]))
        after = decode(cursor,scope) if cursor else None
        if after:
            try:
                after = (timestamp(after[0]), after[1])
                if not window.start <= after[0] < window.end or after[0]>window.as_of or not after[1]:
                    raise ValueError()
            except (ValueError, TypeError, OverflowError):
                raise HistoryError('invalid_cursor','invalid saved prediction key') from None
        with self.store.connection(readonly=True) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            db.execute("SET LOCAL statement_timeout='2000ms'")
            db.execute("SET LOCAL lock_timeout='250ms'")
            generations = db.execute("""SELECT generation_id,started_at,sealed_at,state
                FROM archive.generations WHERE origin_id=%s AND state<>'prepared'
                AND started_at<=%s AND (sealed_at IS NULL OR sealed_at >= %s)
                ORDER BY started_at,generation_id LIMIT %s""",
                (origin,min(window.end,window.as_of),window.start,MAX_GENERATIONS+1)).fetchall()
            if len(generations)>MAX_GENERATIONS:
                raise ArchiveLimit('too many generations in prediction history interval')
            local = select_page(db,'core',origin,window,after,limit)
            retired = [r['generation_id'] for r in generations if r['state']=='retired']
            needs_archive = bool(retired or include_archive or not generations)
            expected = expected_page(db,origin,window,after,limit) if needs_archive else []
        ids = [r['generation_id'] for r in generations]
        cold, missing, reasons = [], [], []
        tiers = ['local_postgres']
        covered = window.start
        for gen in generations:
            if gen['started_at']>covered:
                break
            covered = max(covered,gen['sealed_at'] or window.as_of)
        if not ids or covered < min(window.end,window.as_of):
            reasons.append('generation_time_gap')
        if needs_archive:
            try:
                if self.archive is None:
                    raise ArchiveUnavailable('prediction archive reader not configured')
                cold = self.archive.page(window,after,limit,deadline)
                tiers.append('authenticated_archive')
            except ArchiveUnavailable:
                reasons.append('archive_unavailable')
                missing = retired
        if time.monotonic()>deadline:
            raise ArchiveLimit('prediction history deadline reached')
        unique = {}
        for source, rows in [('local_postgres', local),('authenticated_archive',cold)]:
            for row in rows:
                old = unique.get(row['prediction_id'])
                if old and (old[0]['content_hash'] != row['content_hash'] or any(
                        old[0][k] != row[k] for k in DISPLAY)):
                    raise ArchiveIntegrityError('inconsistent prediction identity across tiers')
                if not old:
                    unique[row['prediction_id']] = row,source
        ordered = sorted(unique.values(), key=lambda pair:(pair[0]['as_of'],pair[0]['prediction_id']),reverse=True)
        # A LIMIT on either tier may hide keys below this page's frontier.
        # Check only identities which must already be visible in both pages.
        has_more = len(ordered)>limit or len(expected)>limit
        frontier = ((ordered[limit-1][0]['as_of'],ordered[limit-1][0]['prediction_id'])
                    if has_more and len(ordered)>=limit else None)
        archived_ids = {r['prediction_id'] for r in cold}
        for record in expected:
            identity = record['id']
            if frontier and (record['at'],identity)<frontier:
                continue
            if identity not in unique:
                reason = 'saved_prediction_missing'
            elif unique[identity][0]['content_hash']!=record['content_hash']:
                raise ArchiveIntegrityError('prediction differs from its local ledger')
            elif 'authenticated_archive' in tiers and identity not in archived_ids:
                reason = 'archive_revision_missing' if record['acked'] else 'archive_sync_pending'
            else:
                continue
            if reason not in reasons:
                reasons.append(reason)
            if record['generation_id'] not in missing:
                missing.append(record['generation_id'])
        items = [render(r,tier) for r,tier in ordered[:limit]]
        next_cursor = None
        if has_more and items and not missing and 'archive_unavailable' not in reasons:
            last = items[-1]
            next_cursor = base64.urlsafe_b64encode(encoded([scope,[last['as_of'],last['id']]])).decode()
        return {'items':items,'next_cursor':next_cursor,'origin_id':origin,'as_of':window.as_of.isoformat(),
                'coverage':{'complete':not reasons,'reasons':reasons,'generation_ids':ids,
                            'missing_generations':missing,'tiers':tiers,
                            'meaning':'saved forecasts in the requested decision window, created by the pinned cutoff'}}
