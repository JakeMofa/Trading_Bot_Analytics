"""Renew only a currently owned Benchmark writer after checking disk and backlog."""

from . import pp_space
from .cloud_origin_binding import DISPLAY_ORIGIN
from .lifecycle import LifecycleHold
from .rehearsal_profile import WATCH_LEASE_SECONDS


class WatchLease:
    def __init__(self, repository, anchor):
        if repository.environment != 'preprod' or not anchor:
            raise LifecycleHold('Benchmark watch requires a prepared initial generation')
        self.repository = repository
        self.anchor = anchor
        self.session_id = None

    def set_explicit_off(self, stopped):
        with self.repository.transaction() as db:
            self.repository._checkpoint(
                db,
                {'origin_id': DISPLAY_ORIGIN, 'generation_id': self.anchor},
                'watch:operator-off',
                {'stopped': stopped},
            )

    def explicit_off(self):
        with self.repository.transaction() as db:
            return self._stopped(db)

    def _stopped(self, db):
        row = db.execute(
            """SELECT cursor FROM archive.checkpoints
            WHERE origin_id=%s AND generation_id=%s AND consumer='watch:operator-off'
            FOR SHARE""",
            (DISPLAY_ORIGIN, self.anchor),
        ).fetchone()
        return row is not None and row['cursor'] != {'stopped': False}

    def _capacity(self, db):
        if pp_space.sample()['space_hold']:
            raise LifecycleHold('Benchmark PostgreSQL filesystem reserve unavailable')
        cap = self.repository.pending_outbox_limit
        if cap != 10000:
            raise LifecycleHold('Benchmark pending outbox guard changed')
        pending = db.execute(
            """SELECT count(*) AS n FROM (
            SELECT 1 FROM ops.outbox WHERE origin_id=%s AND acknowledged_at IS NULL LIMIT %s
            ) AS remaining""",
            (DISPLAY_ORIGIN, cap),
        ).fetchone()['n']
        if pending >= cap:
            raise LifecycleHold('Benchmark pending outbox reached its configured cap')

    def admit(self, seconds):
        if seconds != WATCH_LEASE_SECONDS:
            raise LifecycleHold('unexpected Benchmark lease interval')
        with self.repository.transaction() as db:
            self._capacity(db)
            if self._stopped(db):
                raise LifecycleHold('Benchmark operator requested OFF')
            row = db.execute(
                """SELECT w.generation_id FROM ops.writer_state w
                JOIN archive.generations g USING (origin_id,generation_id)
                WHERE w.origin_id=%s AND NOT w.collector_enabled AND w.collector_session_id IS NULL
                  AND w.collector_lease_expires_at IS NULL AND g.state='collecting' AND g.hold_reason IS NULL
                  AND EXISTS (SELECT FROM archive.generations a WHERE a.origin_id=w.origin_id
                              AND a.generation_id=%s AND a.slot='A')""",
                (DISPLAY_ORIGIN, self.anchor),
            ).fetchone()
            if not row:
                raise LifecycleHold('Benchmark writer generation unavailable')
            return str(row['generation_id'])

    def renew(self):
        session = self.session_id
        if not session:
            raise LifecycleHold('Benchmark process has no live writer')
        with self.repository.transaction() as db:
            self._capacity(db)
            if self._stopped(db):
                raise LifecycleHold('Benchmark operator requested OFF')
            row = db.execute(
                """UPDATE ops.writer_state w SET
                    collector_lease_expires_at=clock_timestamp()+(%s * interval '1 second')
                FROM archive.generations g WHERE w.origin_id=%s AND w.collector_session_id=%s
                  AND w.collector_enabled AND w.collector_lease_expires_at>clock_timestamp()
                  AND g.origin_id=w.origin_id AND g.generation_id=w.generation_id
                  AND g.state='collecting' AND g.hold_reason IS NULL
                RETURNING w.epoch,w.generation_id,w.collector_lease_expires_at""",
                (WATCH_LEASE_SECONDS, DISPLAY_ORIGIN, session),
            ).fetchone()
            if not row:
                raise LifecycleHold('Benchmark lease expired, held, or transferred')
            return dict(
                origin_id=DISPLAY_ORIGIN,
                generation_id=str(row['generation_id']),
                epoch=row['epoch'],
                lease_expires_at=row['collector_lease_expires_at'].isoformat(),
            )

    def release(self, session):
        # An old process's finally block must never switch off its successor.
        if session:
            with self.repository.transaction() as db:
                db.execute(
                    """UPDATE ops.writer_state SET collector_enabled=false,collector_session_id=NULL,
                    collector_lease_expires_at=NULL,epoch=epoch+1,updated_at=clock_timestamp()
                    WHERE origin_id=%s AND collector_session_id=%s""",
                    (DISPLAY_ORIGIN, session),
                )
            if self.session_id == session:
                self.session_id = None
        return {'collector_enabled': False}
