"""Explicit index preparation, never called by collector/application startup.

Production application requires a separately qualified operator procedure.
CREATE INDEX takes the SQLite writer; do not invoke against live production.
"""

INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS feature_stream_price_time_v2 ON stream_events "
    "(source, julianday(source_time) DESC, event_id ASC) "
    "WHERE source='coinbase'",
    "CREATE INDEX IF NOT EXISTS feature_rest_price_time_v2 ON reference_prices "
    "(source, julianday(source_time) DESC, id ASC) "
    "WHERE source='coinbase'",
)


def create_price_indexes(db):
    """Caller owns transaction/deadline; roll back the whole build on failure."""
    if not db.in_transaction:
        raise ValueError('explicit transaction required for index preparation')
    def canonical(sql):
        return ' '.join(sql.lower().replace('if not exists ', '').split())
    for statement in INDEX_STATEMENTS:
        name = statement.split()[5]
        existing = db.execute("SELECT sql FROM sqlite_schema WHERE type='index' AND name=?", (name,)).fetchone()
        if existing and canonical(existing[0]) != canonical(statement):
            raise ValueError('existing price index definition differs')
    for statement in INDEX_STATEMENTS:
        db.execute(statement)
