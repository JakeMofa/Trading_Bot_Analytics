"""Pack pending history_v2 envelopes under the exact canonical JSON array bound."""
import json
from .archive_codec import ArchiveIntegrityError, ArchiveLimit, encoded, wire
from .retirement_accounting import phase

# PostgreSQL NUMERIC accepts 131072 digits before and 16383 after the point.
MAX_NUMBER_BYTES = 131072 + 16383 + 2  # sign and decimal point
FIELDS = ('id', 'origin_id', 'generation_id', 'entity_type', 'entity_id', 'content_hash', 'payload')


def envelope(row):
    return wire({key: row[key] for key in FIELDS})


def _compact_postgres_json(chunks, capacity):
    """Read a large PostgreSQL JSON projection without allocating an oversized row.

    PostgreSQL escapes JSON strings minimally in UTF-8, but includes structural
    spaces and can expand a float exponent into many decimal places. Discard
    only whitespace outside strings and normalize number tokens with the same
    stdlib JSON decoder/encoder used for ordinary jsonb results.
    """
    output, number = bytearray(), bytearray()
    quoted = escaped = False
    for chunk in chunks:
        for char in chunk:
            if quoted:
                output.append(char)
                if escaped:
                    escaped = False
                elif char == 92:  # backslash
                    escaped = True
                elif char == 34:
                    quoted = False
            elif number and char in b'0123456789+-.Ee':
                if len(number) >= MAX_NUMBER_BYTES:
                    raise ArchiveIntegrityError('numeric token exceeds PostgreSQL representation')
                number.append(char)
            else:
                if number:
                    output.extend(encoded(json.loads(number)))
                    number.clear()
                if char == 45 or 48 <= char <= 57:
                    number.append(char)
                elif char not in b' \t\r\n':
                    output.append(char)
                    quoted = char == 34
            if len(output) > capacity:
                return None
    # The database always emits a complete object ending with '}'.
    if quoted or number:
        raise ArchiveIntegrityError('incomplete structured projection')
    return json.loads(output)


def _large_row(db, generation, identity, capacity):
    # Most large source rows fit once the two SQL-only timestamps are left out.
    # For genuinely expanded jsonb (e.g. many 1e-300 values), materialize the
    # seven-field projection once on the server. Fetch a fixed chunk at a time
    # and stop as soon as the canonical envelope no longer fits.
    db.execute("""DECLARE packing_one_row NO SCROLL CURSOR FOR
        WITH source AS MATERIALIZED (
            SELECT convert_to(row_to_json(record)::text,'UTF8') AS document,
                   created_at,acknowledged_at
            FROM ops.outbox o CROSS JOIN LATERAL
              (SELECT o.id,o.origin_id,o.generation_id,o.entity_type,o.entity_id,o.content_hash,o.payload) record
            WHERE o.generation_id=%s AND o.id=%s AND o.acknowledged_at IS NULL)
        SELECT substring(document FROM n FOR 8192) AS part,octet_length(document) AS total,created_at,acknowledged_at
        FROM source CROSS JOIN LATERAL generate_series(1,octet_length(document),8192) AS n""",
        (generation,identity))
    fetch = 'FETCH FORWARD 1 FROM packing_one_row'
    first = db.execute(fetch).fetchone()
    if first is None:
        raise ArchiveIntegrityError('pending outbox row changed during selection')
    def chunks():
        row = first
        while row is not None:
            yield bytes(row['part'])
            row = db.execute(fetch).fetchone()

    if first['total'] <= capacity:
        record = json.loads(b''.join(chunks()))
    else:
        record = _compact_postgres_json(chunks(), capacity)
    db.execute('CLOSE packing_one_row')
    if record is None:
        return None
    return {**record, 'created_at':first['created_at'], 'acknowledged_at':first['acknowledged_at']}


def pending_page(db, generation, limit, max_bytes):
    if type(max_bytes) is not int or max_bytes < 2:
        raise ArchiveLimit('structured page requires space for JSON array brackets')
    with phase('structured_page_size_query'):
        # Bind the trusted catalog origin so the partial pending index can seek
        # straight to the unacknowledged tail, even after days of collection.
        sizes = db.execute("""SELECT o.id,octet_length(row_to_json(o)::text) AS bytes
            FROM ops.outbox o WHERE o.origin_id=(SELECT g.origin_id FROM archive.generations g
                WHERE g.generation_id=%s) AND o.generation_id=%s AND o.acknowledged_at IS NULL
            ORDER BY o.id LIMIT %s""",(generation,generation,limit)).fetchall()
    selected = []
    remaining = max_bytes-2  # the canonical JSON array brackets
    pos = 0
    with phase('structured_page_payload_query'):
        while pos < len(sizes):
            begin, local_bytes = pos, 0
            while pos < len(sizes) and local_bytes + sizes[pos]['bytes'] <= max_bytes:
                local_bytes += sizes[pos]['bytes']
                pos += 1
            if pos == begin:
                row = _large_row(db,generation,sizes[pos]['id'],remaining-bool(selected))
                rows = [row] if row is not None else []
                pos += 1
                if not rows:
                    if not selected:
                        raise ArchiveLimit('single structured envelope exceeds byte bound')
                    return selected
            else:
                ids = [item['id'] for item in sizes[begin:pos]]
                rows = db.execute("""SELECT * FROM ops.outbox WHERE generation_id=%s
                    AND acknowledged_at IS NULL AND id=ANY(%s::bigint[]) ORDER BY id""",(generation,ids)).fetchall()
                if [r['id'] for r in rows] != ids:
                    raise ArchiveIntegrityError('pending outbox rows changed during selection')
            for row in rows:
                cost = len(encoded(envelope(row))) + bool(selected)  # comma after preceding row
                if cost > remaining:
                    if not selected:
                        raise ArchiveLimit('single structured envelope exceeds byte bound')
                    return selected
                remaining -= cost
                selected.append(row)
    return selected
