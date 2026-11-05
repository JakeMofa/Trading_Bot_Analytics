"""Explicit generated-import scope; never a production authorization or guard."""
from dataclasses import dataclass
import math
import time


@dataclass(frozen=True)
class MigrationBudget:
    row_limit: int = 10000
    byte_limit: int = 128*1024**2
    deadline: float = 0

    def __post_init__(self):
        # Additional rows are allowed only through an explicit generated test
        # argument. Byte/process/workspace limits are not enlarged.
        if type(self.row_limit) is not int or not 0 < self.row_limit <= 100000:
            raise ValueError('generated migration row scope exceeds 100000')
        if type(self.byte_limit) is not int or not 0 < self.byte_limit <= 128*1024**2:
            raise ValueError('generated migration byte scope exceeds 128MiB')
        now=time.monotonic()
        if not math.isfinite(self.deadline) or not now < self.deadline <= now+170:
            raise ValueError('original generated migration deadline required (maximum 170s remaining)')

    def expired(self):
        return time.monotonic() >= self.deadline

    def check(self):
        if self.expired():
            raise TimeoutError('original migration operation deadline')
