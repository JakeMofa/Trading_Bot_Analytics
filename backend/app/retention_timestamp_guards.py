"""Explicit additive timestamp guards using SQLite built-ins only.

SQLite maintains invalid-row membership in the same transaction as every raw
INSERT/UPDATE/DELETE, including writers running older application code. Retention
checks current definitions and current guard contents under its deletion lock.
Installation is explicit supervised maintenance, never application startup.
"""
TABLES=('observations','stream_events')
D='[0-9]'
PREFIX=f'{D*4}-{D*2}-{D*2}T{D*2}:{D*2}:{D*2}'
COLUMN='received_at'
YEAR=f'CAST(substr({COLUMN},1,4) AS INTEGER)'
MONTH=f'CAST(substr({COLUMN},6,2) AS INTEGER)'
DAY=f'CAST(substr({COLUMN},9,2) AS INTEGER)'
MAX_DAY=(f'(CASE {MONTH} WHEN 2 THEN 28+({YEAR}%4=0 AND ({YEAR}%100<>0 OR {YEAR}%400=0)) '
         'WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END)')
# Pair each GLOB with the UTF-8 BYTE length: SQL length(TEXT) stops at NUL.
INVALID_SQL=(f"NOT COALESCE((typeof({COLUMN})='text' AND "
    f"((length(CAST({COLUMN} AS BLOB))=25 AND {COLUMN} GLOB '{PREFIX}+00:00') OR "
    f"(length(CAST({COLUMN} AS BLOB))=32 AND {COLUMN} GLOB '{PREFIX}.{D*6}+00:00')) "
    f'AND {YEAR} BETWEEN 1 AND 9999 AND {MONTH} BETWEEN 1 AND 12 '
    f'AND {DAY} BETWEEN 1 AND {MAX_DAY} '
    f'AND CAST(substr({COLUMN},12,2) AS INTEGER) BETWEEN 0 AND 23 '
    f'AND CAST(substr({COLUMN},15,2) AS INTEGER) BETWEEN 0 AND 59 '
    f'AND CAST(substr({COLUMN},18,2) AS INTEGER) BETWEEN 0 AND 59),0)')


def index_name(table):
    if table not in TABLES:raise ValueError('unsupported timestamp guard table')
    return 'retention_'+table+'_invalid_time_v1'


def index_sql(table):
    return f'CREATE INDEX {index_name(table)} ON {table}(received_at COLLATE BINARY) WHERE {INVALID_SQL}'


def available(db,table):
    name=index_name(table)
    row=db.execute("SELECT sql FROM main.sqlite_schema WHERE type='index' AND name=?",(name,)).fetchone()
    if row is None:return False
    # Exact reviewed SQL, not a name-only or whitespace/substring approximation.
    if row[0]!=index_sql(table):raise ValueError('timestamp guard definition differs')
    return True


def invalid_exists(db,table):
    if not available(db,table):raise ValueError('timestamp guard missing')
    return db.execute(f'SELECT 1 FROM main.{table} INDEXED BY {index_name(table)} WHERE {INVALID_SQL} LIMIT 1').fetchone() is not None


def create_indexes(db):
    """Caller owns maintenance deadline/transaction; never commits or deletes."""
    if not db.in_transaction:raise ValueError('explicit transaction required for timestamp guards')
    if db.execute('PRAGMA encoding').fetchone()[0]!='UTF-8':
        raise ValueError('timestamp guards require current UTF-8 storage contract')
    for table in TABLES:
        if not available(db,table):db.execute(index_sql(table))
