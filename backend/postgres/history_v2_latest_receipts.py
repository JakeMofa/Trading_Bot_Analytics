"""PP-only opt-in latest identity lookup; hashes never authorize identity.

The normal rank query remains default. Missing/wrong/unready supporting index
HOLDs before the opt-in lateral query; there is no unindexed fallback. Every
lookup retains all max-outbox ties across generations, matching rank()=1.
"""
from .archive_codec import ArchiveIntegrityError

INDEX_NAME='structured_receipts_latest_identity_v1_idx'
RANK_SQL='''SELECT entity_type,entity_id,generation_id,outbox_id FROM (
    SELECT r.entity_type,r.entity_id,r.generation_id,r.outbox_id,
           rank() OVER (PARTITION BY r.entity_type,r.entity_id ORDER BY r.outbox_id DESC) AS position
    FROM history_v2.structured_receipts r
    JOIN unnest(%s::text[],%s::text[]) k(entity_type,entity_id)
    USING (entity_type,entity_id) WHERE r.origin_id=%s
) revisions WHERE position=1'''
INDEXED_SQL='''SELECT r.entity_type,r.entity_id,r.generation_id,r.outbox_id
    FROM unnest(%s::text[],%s::text[]) k(entity_type,entity_id)
    CROSS JOIN LATERAL (
        SELECT r.entity_type,r.entity_id,r.generation_id,r.outbox_id
        FROM history_v2.structured_receipts r
        WHERE r.origin_id=%s AND r.entity_type=k.entity_type
          AND pg_catalog.md5(r.entity_id)=pg_catalog.md5(k.entity_id)
          AND r.entity_id=k.entity_id
        ORDER BY r.outbox_id DESC FETCH FIRST 1 ROW WITH TIES
    ) r'''
ABI_SQL='''SELECT i.indisvalid AND i.indisready AND i.indislive AND NOT i.indisunique
    AND i.indpred IS NULL AND i.indnkeyatts=4 AND i.indnatts=4
    AND am.amname='btree' AND tn.nspname='history_v2' AND t.relname='structured_receipts'
    AND pg_catalog.pg_get_indexdef(i.indexrelid)=
        'CREATE INDEX structured_receipts_latest_identity_v1_idx ON history_v2.structured_receipts USING btree (origin_id, entity_type, md5(entity_id), outbox_id DESC)'
    AND col.collisdeterministic AS valid
    FROM pg_catalog.pg_index i
    JOIN pg_catalog.pg_class ix ON ix.oid=i.indexrelid
    JOIN pg_catalog.pg_namespace n ON n.oid=ix.relnamespace
    JOIN pg_catalog.pg_class t ON t.oid=i.indrelid
    JOIN pg_catalog.pg_namespace tn ON tn.oid=t.relnamespace
    JOIN pg_catalog.pg_am am ON am.oid=ix.relam
    JOIN pg_catalog.pg_attribute a ON a.attrelid=t.oid AND a.attname='entity_id'
    JOIN pg_catalog.pg_collation col ON col.oid=a.attcollation
    WHERE n.nspname='history_v2' AND ix.relname=%s'''


def indexed_latest_requested(environ):
    value=environ.get('TRADEBOT_PP_INDEXED_LATEST_RECEIPTS','false')
    if value not in ('true','false'):
        raise ArchiveIntegrityError('exact PP indexed latest receipt opt-in required')
    return value=='true'


class _CheckedIndex:
    def __init__(self,connection):self.connection=connection


def checked_index(connection,valid):
    if valid is not True:
        raise ArchiveIntegrityError('PP latest receipt index ABI unavailable')
    return _CheckedIndex(connection)


def latest_receipts(connection,origin,keys,*,indexed=False,_checked=None):
    if indexed:
        if _checked is None:
            # Standalone use probes first. The transport fuses this ABI into its
            # existing authenticated checkpoint SELECT, using a fresh per-page
            # token bound to this connection, so there is no additional wait.
            with connection.pipeline():
                connection.execute("SELECT pg_catalog.set_config('search_path','pg_catalog',true)")
                checked=connection.execute(ABI_SQL,(INDEX_NAME,))
            row=checked.fetchone()
            _checked=checked_index(connection,row['valid'] if row else None)
        if not isinstance(_checked,_CheckedIndex) or _checked.connection is not connection:
            raise ArchiveIntegrityError('PP latest receipt index ABI connection mismatch')
    values=([key[0] for key in keys],[key[1] for key in keys],origin)
    return connection.execute(INDEXED_SQL if indexed else RANK_SQL,values).fetchall()
