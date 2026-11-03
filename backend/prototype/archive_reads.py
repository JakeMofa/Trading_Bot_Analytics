"""Generated integration adapter: bounded authenticated GETs; never retries writes.

The caller supplies the ORIGINAL phase deadline. Each HTTP request gets the
remaining budget as an inactivity timeout; late responses are rejected.
This is NOT a hard wall-clock HTTP deadline: trickled responses require a
reviewed enclosing phase supervisor before production integration. Verification stays outside this
transport helper, so corrupt evidence never becomes a retryable response.
"""
import math
import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote
import httpx

class ArchiveHold(RuntimeError):
    pass

class BoundedArchiveReads:
    def __init__(self, cloud, deadline, clock=time.monotonic, sleep=time.sleep,
                 jitter=lambda: random.uniform(0, .250), wall=lambda: datetime.now(timezone.utc)):
        self.cloud, self.deadline = cloud, deadline
        self.clock, self.sleep, self.jitter, self.wall = clock, sleep, jitter, wall

    def download_bytes(self, bucket, path):
        for attempt in range(3):
            remaining = self.deadline - self.clock()
            if remaining <= 0:
                raise ArchiveHold('archive GET deadline exhausted')
            response = None
            try:
                response = self.cloud.client.get(
                    f'{self.cloud.config.url}/storage/v1/object/authenticated/'
                    f'{quote(bucket, safe="")}/{quote(path, safe="/")}',
                    headers=self.cloud._headers(**{'Cache-Control': 'no-store'}),
                    timeout=remaining)
                if self.clock() >= self.deadline:
                    raise ArchiveHold('archive GET returned after deadline')
                response.raise_for_status()
                return response.content
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 429 and not 500 <= exc.response.status_code < 600:
                    raise ArchiveHold(f'archive GET permanent HTTP {exc.response.status_code}') from None
            except (httpx.TimeoutException, httpx.NetworkError):
                pass
            if attempt == 2:
                raise ArchiveHold('archive GET transient attempts exhausted')
            delay = (1, 2)[attempt] + min(.250, max(0, self.jitter()))
            if response is not None and 'Retry-After' in response.headers:
                value = response.headers['Retry-After']
                try:
                    retry = float(value)
                    if retry < 0 or not math.isfinite(retry):
                        raise ValueError()
                except ValueError:
                    try:
                        date = parsedate_to_datetime(value)
                        if date.tzinfo is None: raise ValueError()
                        retry = max(0, (date - self.wall()).total_seconds())
                    except (ValueError, TypeError, OverflowError):
                        raise ArchiveHold('invalid archive Retry-After') from None
                delay = max(delay, retry)
            if delay >= self.deadline - self.clock():
                raise ArchiveHold('archive retry deferred: insufficient original deadline')
            self.sleep(delay)
