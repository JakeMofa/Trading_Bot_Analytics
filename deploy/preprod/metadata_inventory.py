"""Preserve the original metadata digest using one native text-ordered cursor."""
import hashlib
import re

from controller import require
from outbox_inventory import work_time

# Preserve the previous qualification's cardinality bound. PostgreSQL's
# unchanged19s statement/64MiB temporary-file guards can refuse earlier.
MAX_ROWS = 64 * 1024**2 // 32
FETCH_ROWS = 512
HEX = re.compile(r'[0-9a-f]{64}')


def metadata_digest(exchange, table, identity, budget, directory):
    # table/identity are the fixed controller inventory map. directory remains
    # an interface argument; this path creates no host scratch or extra files.
    work_time(budget)
    require(exchange("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY; SET LOCAL statement_timeout='19s';") == [],
            'metadata_snapshot_invalid')
    manifest = exchange(f'SELECT to_json(count(*)) FROM {table};')
    require(isinstance(manifest,list) and len(manifest)==1 and type(manifest[0]) is int
            and manifest[0]>=0,'metadata_snapshot_invalid')
    expected = manifest[0]
    require(expected <= MAX_ROWS, 'metadata_inventory_limit')
    # ORDER BY retains PostgreSQL's actual text collation, including ICU
    # numeric order. OFFSET0 keeps JSON wire projection above the single sort
    # so it stores one text fingerprint instead of both JSON and text copies.
    require(exchange(f"""DECLARE metadata_hashes NO SCROLL CURSOR FOR
        SELECT to_json(fingerprint) FROM (
            SELECT encode(sha256(convert_to(jsonb_build_array({identity})::text,'UTF8')),'hex') AS fingerprint
            FROM {table} ORDER BY fingerprint OFFSET 0
        ) ordered_hashes;""") == [], 'metadata_snapshot_invalid')
    outer = hashlib.sha256()
    page = hashlib.sha256()
    count = 0
    while True:
        work_time(budget)
        batch = exchange(f'FETCH FORWARD {FETCH_ROWS} FROM metadata_hashes;')
        require(isinstance(batch,list) and len(batch)<=FETCH_ROWS,'metadata_snapshot_invalid')
        if not batch:
            break
        require(count + len(batch) <= expected, 'metadata_snapshot_invalid')
        for digest in batch:
            require(isinstance(digest,str) and HEX.fullmatch(digest), 'metadata_invalid_hash')
            page.update(digest.encode('ascii'))
            count += 1
            if count % 1024 == 0:
                outer.update(page.hexdigest().encode('ascii'))
                page = hashlib.sha256()
    require(count == expected, 'metadata_snapshot_invalid')
    if count % 1024:
        outer.update(page.hexdigest().encode('ascii'))
    work_time(budget)
    require(exchange('CLOSE metadata_hashes; COMMIT;') == [], 'metadata_snapshot_invalid')
    return {'count':count,'digest':outer.hexdigest()}
