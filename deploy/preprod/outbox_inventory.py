"""Bounded, read-only preservation of the original ordered outbox page digest."""
import contextlib
import hashlib
import json
import os
import re
import selectors
import signal
import subprocess

from controller import DeploymentHold, require

# The outer flock, when used, belongs to this relay in the PostgreSQL
# container. It outlives the psql frontend. Never signal a server process.
RELAY = r"""
set -eu
umask 077
export PGCONNECT_TIMEOUT=5
export PGOPTIONS='-c statement_timeout=19000 -c default_transaction_read_only=on -c client_connection_check_interval=250'
dir=$(mktemp -d)
child=''
fifo_fd=''
backend=''
birth=''
# Fixed Linux PostgreSQL container shares the backend's PID namespace.
process_birth() {
    local backend=$1
    if [ ! -d "/proc/$backend" ]; then
        if [ -r /proc/self/stat ]; then echo gone; else echo unknown; fi
        return
    fi
    # Strip through the closing comm parenthesis (comm may contain spaces).
    local stat tail ticks
    if ! IFS= read -r stat <"/proc/$backend/stat"; then echo unknown; return; fi
    tail=${stat##*) }
    set -- $tail
    ticks=${20:-}
    case "$ticks" in ''|*[!0-9]*) echo unknown;; *)
        if [ "$1" = Z ]; then echo gone; else echo "$ticks"; fi;;
    esac
}
wait_for_exit() {
    local pid=$1 started=$2
    while :; do
        case "$(process_birth "$pid")" in gone) return;; unknown|"$started") sleep .05;; *) return;; esac
    done
}
postmaster=$(head -n1 "$PGDATA/postmaster.pid")
case "$postmaster" in ''|*[!0-9]*) exit 75;; esac
master_birth=$(process_birth "$postmaster")
case "$master_birth" in ''|*[!0-9]*) exit 75;; esac
children() { cat "/proc/$postmaster/task/$postmaster/children"; }
# If startup is interrupted before pg_backend_pid() returns, an authenticated
# client can still exist. Keep possible new postmaster children excluded; no
# query other than the PID handshake has been supplied at that point.
baseline=' '
initial=$(children)
for pid in $initial; do
    identity=$(process_birth "$pid")
    case "$identity" in gone|unknown) ;; *) baseline="$baseline$pid:$identity ";; esac
done
cleanup() {
    trap '' HUP INT TERM
    if [ -n "$child" ]; then
        kill -INT "$child" 2>/dev/null || :
        if [[ ${fifo_fd:-} =~ ^[0-9]+$ ]]; then exec {fifo_fd}>&-; fifo_fd=''; fi
        wait "$child" 2>/dev/null || :
        if [ -n "$birth" ]; then
            wait_for_exit "$backend" "$birth"
        else
            # The frontend is gone. A connection it authenticated must already
            # have a server child. Include unrelated newcomers conservatively.
            while ! possible=$(children); do
                [ "$(process_birth "$postmaster")" = gone ] && break
                sleep .05
            done
            for pid in ${possible:-}; do
                identity=$(process_birth "$pid")
                while [ "$identity" = unknown ]; do sleep .05; identity=$(process_birth "$pid"); done
                case "$identity" in gone) continue;; esac
                case "$baseline" in *" $pid:$identity "*) continue;; esac
                wait_for_exit "$pid" "$identity"
            done
        fi
    elif [ -n "$birth" ]; then
        wait_for_exit "$backend" "$birth"
    fi
    rm -f "$dir/in" "$dir/backend"
    rmdir "$dir"
}
trap cleanup EXIT
# An interrupt during the short private handshake must not discard the identity
# before the serialized cleanup can see it.
stopping=0
trap 'stopping=1' HUP INT TERM
mkfifo "$dir/in"
"$@" <"$dir/in" &
child=$!
exec {fifo_fd}>"$dir/in"
rm "$dir/in"
# psql writes precisely its own backend PID privately, before the controller
# can supply an expensive statement. Only this shell owns this directory.
printf '%s %s\n' 'SELECT pg_backend_pid() \g' "$dir/backend" >&"$fifo_fd"
for tick in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do
    [ -s "$dir/backend" ] && break
    kill -0 "$child" 2>/dev/null || exit 75
    sleep .2
done
read -r backend <"$dir/backend" || exit 75
case "$backend" in ''|*[!0-9]*) exit 75;; esac
birth=$(process_birth "$backend")
case "$birth" in ''|*[!0-9]*) birth=''; exit 75;; esac
[ "$stopping" = 0 ] || exit 74
trap 'exit 74' HUP INT TERM
while IFS= read -r -t 20 line; do
    printf '%s\n' "$line" >&"$fifo_fd"
    if [ "$line" = '\q' ]; then
        if [[ ${fifo_fd:-} =~ ^[0-9]+$ ]]; then exec {fifo_fd}>&-; fifo_fd=''; fi
        wait "$child"
        child=''
        exit 0
    fi
done
exit 74
"""
END = b'__tradebot_inventory_response__\n'
# Allow a server statement's 19s timeout and an orderly physical disconnect
# even if the caller's global work deadline is approaching.
CLEANUP_SECONDS = 23


def work_time(budget, maximum=20):
    remaining = budget.timeout() - CLEANUP_SECONDS
    require(remaining > 0, 'deadline_exceeded')
    return min(maximum, remaining)


@contextlib.contextmanager
def psql_channel(args, budget, env, verify_cleanup):
    """One physical session. Each response has 20s and 64 KiB, the caller owns the total budget."""
    work_time(budget)
    child = subprocess.Popen(args, env=env, bufsize=0, start_new_session=True,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    done = False
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            selector.register(child.stderr, selectors.EVENT_READ)

            def exchange(sql):
                # One bounded message fits in an empty pipe. No next query is
                # queued until this response and its complete marker are verified.
                message = (sql + '\n\\echo ' + END.decode()).encode()
                require(len(message) <= 4096, 'child_io_bound')
                deadline = budget.clock() + work_time(budget)
                require(child.stdin.write(message) == len(message), 'child_failed')
                reply = bytearray()
                while not reply.endswith(END):
                    remaining = min(work_time(budget), deadline - budget.clock())
                    require(remaining > 0, 'child_deadline_exceeded')
                    for ready, _ in selector.select(min(remaining, .25)):
                        part = os.read(ready.fd,8192)
                        require(part and ready.fileobj is child.stdout, 'outbox_psql_failed')
                        reply.extend(part)
                        require(len(reply) <= 65536, 'child_output_bound')
                require(budget.clock() < deadline, 'child_deadline_exceeded')
                return [json.loads(line) for line in reply[:-len(END)].splitlines()]

            yield exchange
            child.stdin.write(b'\\q\n')
            child.stdin.close()
            # No commands remain in flight after the last response.
            require(child.wait(timeout=budget.timeout(2)) == 0, 'outbox_psql_failed')
            done = True
    except (BrokenPipeError, ValueError, subprocess.TimeoutExpired) as exc:
        raise DeploymentHold('outbox_psql_failed') from exc
    finally:
        if not child.stdin.closed:
            child.stdin.close()
        try:
            if not done:
                try:
                    # When the Docker attach frontend has been killed, its exit
                    # code says nothing about the physical connection. The same
                    # independent flock must reopen before cleanup is accepted.
                    child.wait(timeout=budget.timeout(.5))
                except (subprocess.TimeoutExpired, DeploymentHold):
                    pass
                try:
                    verify_cleanup()
                except (DeploymentHold, subprocess.TimeoutExpired) as exc:
                    raise DeploymentHold('outbox_reader_cleanup_unproven') from exc
                finally:
                    if child.poll() is None:
                        try:
                            os.killpg(child.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        child.wait(timeout=2)
        finally:
            child.stdout.close()
            child.stderr.close()


def _page(number):
    # PostgreSQL bigint division truncates toward zero, including at -2**63.
    return number // 1024 if number >= 0 else -((-number) // 1024)


def origin_digest(exchange, origin):
    require(re.fullmatch('[a-z][a-z0-9-]{0,100}',origin), 'unexpected_outbox_origin')
    require(exchange("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY; SET LOCAL statement_timeout='19s';") == [],
            'outbox_snapshot_invalid')
    # The same MVCC snapshot covers descriptor discovery, every full-row hash,
    # and cursor exhaustion. No archive records or unbounded lists leave SQL.
    declare = f"""DECLARE outbox_pages NO SCROLL CURSOR FOR
        SELECT json_build_array(page,lo,hi,n,count(*) OVER (),sum(n) OVER ())
        FROM (SELECT id/1024 AS page,min(id) AS lo,max(id) AS hi,count(*) AS n
              FROM ops.outbox WHERE origin_id='{origin}' GROUP BY id/1024) ranges
        ORDER BY page;"""
    require(exchange(declare) == [], 'outbox_snapshot_invalid')
    count = pending = pages = 0
    manifest = None
    previous = None
    digest = hashlib.sha256()
    while True:
        descriptors = exchange('FETCH FORWARD 16 FROM outbox_pages;')
        require(isinstance(descriptors,list) and len(descriptors)<=16, 'outbox_inventory_invalid')
        if not descriptors:
            break
        for desc in descriptors:
            require(isinstance(desc,list) and len(desc)==6 and all(type(x) is int for x in desc),
                    'outbox_inventory_invalid')
            page, lo, hi, expected, page_total, row_total = desc
            if manifest is None:
                manifest = (page_total,row_total)
            require(manifest == (page_total,row_total) and pages < page_total <= row_total,
                    'outbox_inventory_invalid')
            require((previous is None or previous<page) and -(2**63)<=lo<=hi<2**63
                    and _page(lo)==_page(hi)==page and 0<expected<=hi-lo+1, 'outbox_inventory_invalid')
            result = exchange(f"""WITH hashes AS MATERIALIZED (
                SELECT o.id, o.acknowledged_at IS NULL AS pending,
                    encode(sha256(convert_to(to_jsonb(o)::text,'UTF8')),'hex') AS hash
                FROM ops.outbox o WHERE o.origin_id='{origin}' AND o.id BETWEEN {lo} AND {hi})
                SELECT json_build_array(count(*),count(*) FILTER (WHERE pending),
                    encode(sha256(convert_to(string_agg(hash,'' ORDER BY id),'UTF8')),'hex'))
                FROM hashes;""")
            require(isinstance(result,list) and len(result)==1 and isinstance(result[0],list)
                    and len(result[0])==3, 'outbox_inventory_invalid')
            n, waiting, page_hash = result[0]
            require(type(n) is int and n==expected and type(waiting) is int and 0<=waiting<=n
                    and isinstance(page_hash,str) and re.fullmatch('[0-9a-f]{64}',page_hash), 'outbox_inventory_invalid')
            digest.update(page_hash.encode('ascii'))
            count += n
            pending += waiting
            previous = page
            pages += 1
    require(count>0 and manifest==(pages,count) and pending<=10000 and exchange('CLOSE outbox_pages; COMMIT;')==[], 'outbox_inventory_invalid')
    return {'count':count, 'pending':pending, 'digest':digest.hexdigest()}
