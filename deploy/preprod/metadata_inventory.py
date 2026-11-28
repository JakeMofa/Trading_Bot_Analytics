"""Preserve PostgreSQL's ordered 1024-row metadata digest with bounded scratch."""
import hashlib
import heapq
import os
import re
import shutil
import tempfile

from controller import require
from outbox_inventory import work_time

ROW_BYTES = 32
RUN_ROWS = 8192
MAX_BYTES = 64 * 1024**2
RESERVE_BYTES = 10 * 1024**3
FETCH_ROWS = 512
ORDER_ROWS = 48
HEX = re.compile(r'[0-9a-f]{64}')


def _write_run(file, rows, expected, directory, budget):
    work_time(budget)
    size = len(rows) * ROW_BYTES
    require(file.tell() + size <= min(MAX_BYTES, expected * ROW_BYTES), 'metadata_scratch_limit')
    require(shutil.disk_usage(directory).free >= RESERVE_BYTES + size, 'metadata_scratch_reserve')
    rows.sort()
    block = b''.join(rows)
    require(file.write(block) == size, 'metadata_scratch_short_write')
    require(shutil.disk_usage(directory).free >= RESERVE_BYTES, 'metadata_scratch_reserve')
    return hashlib.sha256(block).digest()


def _read_run(fd, lo, hi, expected_hash):
    # At most 256 runs at the 64 MiB cap. Each holds one 4 KiB block.
    checksum = hashlib.sha256()
    while lo < hi:
        size = min(4096, hi - lo)
        block = os.pread(fd, size, lo)
        require(len(block) == size and size % ROW_BYTES == 0, 'metadata_scratch_short_read')
        checksum.update(block)
        for i in range(0, size, ROW_BYTES):
            yield block[i:i + ROW_BYTES]
        lo += size
    require(checksum.digest() == expected_hash, 'metadata_scratch_hash_mismatch')


def _native_order(exchange, hashes):
    if len(hashes) < 2:
        return
    # Only regex-validated hex digests enter this fixed-size literal. Ask
    # the original database's default collation about every actual adjacent
    # distinct value, including the pair across each request boundary.
    array = ','.join("'" + digest + "'" for digest in hashes)
    query = """SELECT to_json(coalesce(bool_and(prior IS NULL OR prior < hash),true))
        FROM (SELECT hash,lag(hash) OVER (ORDER BY ord) AS prior
              FROM unnest(ARRAY[%s]::text[]) WITH ORDINALITY AS a(hash,ord)) pairs;""" % array
    result = exchange(query)
    require(isinstance(result,list) and len(result)==1 and result[0] is True,
            'metadata_native_order_unproven')


def metadata_digest(exchange, table, identity, budget, directory):
    # table/identity are the fixed controller inventory map. JSON framing
    # makes truncated or malformed rows rejectable by the serialized reader.
    work_time(budget)
    require(exchange("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY; SET LOCAL statement_timeout='19s';") == [],
            'metadata_snapshot_invalid')
    manifest = exchange(f'SELECT to_json(count(*)) FROM {table};')
    require(isinstance(manifest,list) and len(manifest)==1 and type(manifest[0]) is int
            and manifest[0]>=0,'metadata_snapshot_invalid')
    expected = manifest[0]
    require(expected * ROW_BYTES <= MAX_BYTES, 'metadata_scratch_limit')
    require(shutil.disk_usage(directory).free >= RESERVE_BYTES + expected * ROW_BYTES,
            'metadata_scratch_reserve')
    require(exchange(f"""DECLARE metadata_hashes NO SCROLL CURSOR FOR
        SELECT to_json(encode(sha256(convert_to(jsonb_build_array({identity})::text,'UTF8')),'hex'))
        FROM {table};""") == [], 'metadata_snapshot_invalid')
    with tempfile.TemporaryFile(dir=directory,buffering=0) as spool:
        # TemporaryFile is unlinked (or O_TMPFILE), including on process death.
        require(os.fstat(spool.fileno()).st_nlink == 0, 'metadata_scratch_not_anonymous')
        rows = []
        run_hashes = []
        count = 0
        while True:
            work_time(budget)
            batch = exchange(f'FETCH FORWARD {FETCH_ROWS} FROM metadata_hashes;')
            require(isinstance(batch,list) and len(batch)<=FETCH_ROWS,'metadata_snapshot_invalid')
            if not batch:
                break
            count += len(batch)
            require(count <= expected, 'metadata_snapshot_invalid')
            for digest in batch:
                require(isinstance(digest,str) and HEX.fullmatch(digest), 'metadata_invalid_hash')
                rows.append(bytes.fromhex(digest))
                if len(rows) == RUN_ROWS:
                    run_hashes.append(_write_run(spool, rows, expected, directory, budget))
                    rows.clear()
        require(count == expected, 'metadata_snapshot_invalid')
        if rows:
            run_hashes.append(_write_run(spool, rows, expected, directory, budget))
            rows.clear()
        # The table count and all values are frozen now. The remaining native
        # comparisons use only these literal hashes on the same read-only
        # connection, without pinning the snapshot while merging host runs.
        require(exchange('CLOSE metadata_hashes; COMMIT;') == [], 'metadata_snapshot_invalid')
        size = os.fstat(spool.fileno()).st_size
        require(size == expected * ROW_BYTES, 'metadata_scratch_short_write')
        width = ROW_BYTES * RUN_ROWS
        require(len(run_hashes)==(size+width-1)//width, 'metadata_scratch_short_write')
        sorted_rows = heapq.merge(*(_read_run(spool.fileno(), i*width, min((i+1)*width,size), checksum)
                                    for i,checksum in enumerate(run_hashes)))
        outer = hashlib.sha256()
        page = hashlib.sha256()
        chain = []
        folded = 0
        for row in sorted_rows:
            if folded % 512 == 0:
                work_time(budget)
            digest = row.hex()
            if not chain or chain[-1] != digest:
                chain.append(digest)
                if len(chain) == ORDER_ROWS:
                    _native_order(exchange, chain)
                    chain = [digest]
            page.update(digest.encode('ascii'))
            folded += 1
            if folded % 1024 == 0:
                outer.update(page.hexdigest().encode('ascii'))
                page = hashlib.sha256()
        _native_order(exchange, chain)
        work_time(budget)
        require(folded == expected, 'metadata_scratch_short_read')
        if folded % 1024:
            outer.update(page.hexdigest().encode('ascii'))
        return {'count':folded,'digest':outer.hexdigest()}
