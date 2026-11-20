"""PP structured sync service. Each iteration completes at most one page."""
import json
import os
import signal
import threading
import time

from .cloud_origin_binding import TRIAL_ORIGIN, TRIAL_ORIGINS, cloud_binding
from .cloud_runtime_profile import selected_cloud_origin,cloud_files,require_trial_files
from .archive_codec import ArchiveIntegrityError, ArchiveLimit, ArchiveUnavailable
from .connection import connect
from .history_v2_transport import HistoryV2PostgresTransport
from .lifecycle import LifecycleRepository
from .migrate import validate_schema
from .pp_history_connection import PPHistoryConnectionFactory
from .pp_history_session import ReusablePPHistoryConnectionFactory, session_reuse_requested
from .pp_structured_drain import DrainLimits, drain_bounded
from .pp_structured_probe import LOCAL_DSN, MAX_PENDING, ORIGIN, check_environment, private_dsn, retain_revisions


# Recurring-only page. The operator one-shot retains its independent 25-row cap.
RECURRING_LIMITS = DrainLimits(max_cycles=1, max_cycle_rows=50)


def synchronized_batches_requested(environ, *, origin, retain_revisions):
    value = environ.get('TRADEBOT_PP_SYNC_BARRIERS', 'false')
    if (value not in ('true', 'false') or
            value == 'true' and (origin not in TRIAL_ORIGINS or not retain_revisions)):
        raise ArchiveIntegrityError('exact trial revision-retaining synchronization opt-in required')
    return value == 'true'


def failure_context(error):
    phase = getattr(error, 'structured_phase', None)
    if phase not in ('local_prepare', 'cloud_import', 'cloud_readback',
                     'local_ack', 'after_local_ack'):
        return {}
    result = {'phase': phase}
    page = getattr(error, 'structured_page', None)
    if (isinstance(page, tuple) and len(page) == 3 and
            all(type(value) is int for value in page)):
        first, last, count = page
        if 0 < first <= last and 1 <= count <= RECURRING_LIMITS.max_cycle_rows:
            result.update(first_outbox_id=first, last_outbox_id=last, page_rows=count)
    return result


def supervise(page, stop, emit):
    delay = 1
    while not stop.is_set():
        start = time.monotonic()
        try:
            result = page()
        except ArchiveUnavailable as error:
            # A replay uses the same durable outbox page and verifies any
            # receipts already committed remotely before local ACK.
            emit(dict(status='retry', reason='archive_unavailable', delay_seconds=delay,
                      **failure_context(error)))
            stop.wait(delay)
            delay = min(60, delay * 2)
            continue
        except Exception as error:
            reason = {ArchiveIntegrityError: 'archive_integrity',
                      ArchiveLimit: 'archive_limit'}.get(type(error), 'structured_page_failed')
            emit(dict(status='hold', reason=reason, **failure_context(error)))
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

    remote = None
    reuse = False
    try:
        origin=selected_cloud_origin(os.environ)
        check_environment(os.environ, recurring=True,origin_id=origin)
        require_trial_files(os.environ,origin,structured=True)
        files=cloud_files(origin)
        reuse = session_reuse_requested(os.environ)
        capture = retain_revisions(os.environ)
        synchronized = synchronized_batches_requested(os.environ, origin=origin,
                                                      retain_revisions=capture)
        dsn = private_dsn(LOCAL_DSN)

        def local():
            return connect(dsn, environment='preprod')

        with local() as conn:
            if conn.execute('SELECT session_user AS login').fetchone()['login'] != 'tradebot_lifecycle':
                raise ValueError('wrong PP lifecycle role')
            validate_schema(conn, 'preprod')
        repo = LifecycleRepository(local, environment='preprod', pending_outbox_limit=MAX_PENDING)
        factory_type=ReusablePPHistoryConnectionFactory if reuse else PPHistoryConnectionFactory
        if origin==ORIGIN:
            remote=factory_type()
        else:
            remote=factory_type(files['TRADEBOT_PP_HISTORY_DSN_FILE'],files['TRADEBOT_PP_HISTORY_CA_FILE'],origin_id=origin)

        def transport(generation, *, timeout_seconds):
            return HistoryV2PostgresTransport(remote, origin_id=origin,
                generation_id=generation, expected_database='postgres',
                expected_role=cloud_binding(origin).writer_role, retain_revisions=capture,
                sync_barriers=synchronized)

        def page():
            return drain_bounded(repo, transport, execute=True,
                                 limits=RECURRING_LIMITS,origin_id=origin)

        emit(dict(status='structured_worker_ready', sync_barriers=synchronized,
                  session_reuse=reuse))
        return supervise(page, stop, emit)
    except Exception:
        emit(dict(status='hold', reason='structured_startup_failed'))
        return 1
    finally:
        if reuse and remote is not None:
            remote.close()


if __name__ == '__main__':
    raise SystemExit(main())
