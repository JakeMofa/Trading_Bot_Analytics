"""PP structured sync service. Each iteration completes at most one page."""
import json
import os
import signal
import threading
import time

from .archive_codec import ArchiveIntegrityError, ArchiveLimit, ArchiveUnavailable
from .connection import connect
from .history_v2_transport import HistoryV2PostgresTransport
from .lifecycle import LifecycleRepository
from .migrate import validate_schema
from .pp_history_connection import PPHistoryConnectionFactory
from .pp_structured_drain import DrainLimits, drain_bounded
from .pp_structured_probe import LOCAL_DSN, MAX_PENDING, ORIGIN, check_environment, private_dsn, retain_revisions


# Recurring-only page. The operator one-shot retains its independent 25-row cap.
RECURRING_LIMITS = DrainLimits(max_cycles=1, max_cycle_rows=50)


def supervise(page, stop, emit):
    delay = 1
    while not stop.is_set():
        start = time.monotonic()
        try:
            result = page()
        except ArchiveUnavailable:
            # A replay uses the same durable outbox page and verifies any
            # receipts already committed remotely before local ACK.
            emit(dict(status='retry', reason='archive_unavailable', delay_seconds=delay))
            stop.wait(delay)
            delay = min(60, delay * 2)
            continue
        except Exception as error:
            reason = {ArchiveIntegrityError: 'archive_integrity',
                      ArchiveLimit: 'archive_limit'}.get(type(error), 'structured_page_failed')
            emit(dict(status='hold', reason=reason))
            return 1
        delay = 1
        count = result['acknowledged']
        emit(dict(status=result['status'], acknowledged=count,
                  page_seconds=round(time.monotonic() - start, 4)))
        stop.wait(0.1 if count else 5)
    return 0


def main():
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())

    def emit(event):
        print(json.dumps(event, sort_keys=True), flush=True)

    try:
        check_environment(os.environ, recurring=True)
        dsn = private_dsn(LOCAL_DSN)

        def local():
            return connect(dsn, environment='preprod')

        with local() as conn:
            if conn.execute('SELECT session_user AS login').fetchone()['login'] != 'tradebot_lifecycle':
                raise ValueError('wrong PP lifecycle role')
            validate_schema(conn, 'preprod')
        repo = LifecycleRepository(local, environment='preprod', pending_outbox_limit=MAX_PENDING)
        capture = retain_revisions(os.environ)
        remote = PPHistoryConnectionFactory()

        def transport(generation, *, timeout_seconds):
            return HistoryV2PostgresTransport(remote, origin_id=ORIGIN,
                generation_id=generation, expected_database='postgres',
                expected_role='tradebot_pp_history', retain_revisions=capture)

        def page():
            return drain_bounded(repo, transport, execute=True,
                                 limits=RECURRING_LIMITS)

        emit(dict(status='structured_worker_ready'))
        return supervise(page, stop, emit)
    except Exception:
        emit(dict(status='hold', reason='structured_startup_failed'))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
