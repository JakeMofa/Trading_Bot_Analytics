"""One checked PostgreSQL connection per live writer, with one transaction per event."""
import asyncio
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from threading import Lock

_active = ContextVar('feed_writer', default=None)


class _Session:
    def __init__(self, store):
        self.store = store
        self.connection = None
        self.lock = Lock()
        self.closed = False

    @contextmanager
    def transaction(self):
        # A canceled to_thread may still be committing. Close waits behind it.
        with self.lock:
            if self.closed:
                raise RuntimeError('feed writer closed')
            if self.connection is None or self.connection.closed:
                self.connection = self.store.connection()
            with self.connection.transaction():
                yield self.connection

    def close(self):
        with self.lock:
            self.closed = True
            if self.connection is not None:
                self.connection.close()


def event_transaction(store):
    session = _active.get()
    if session is not None and session.store is store:
        return session.transaction()
    return store.connection()


@asynccontextmanager
async def feed_writer(store):
    session = _Session(store)
    token = _active.set(session)
    try:
        yield
    finally:
        _active.reset(token)
        await asyncio.to_thread(session.close)
