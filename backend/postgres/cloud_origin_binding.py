"""Reviewed exact PP cloud scopes; no prefix, environment or credential discovery."""
from dataclasses import dataclass
from hashlib import sha256

LEGACY_ORIGIN = 'pp-live-pp'
TRIAL_ORIGIN = 'pp-live-pp-trial-20261119-01'
TRIAL_WRITER = 'tradebot_pp_trial_20261119_01_writer'
TRIAL_READER = 'tradebot_pp_trial_20261119_01_reader'
NEXT_TRIAL_ORIGIN = 'pp-live-pp-trial-20261119-02'
NEXT_TRIAL_WRITER = 'tradebot_pp_trial_20261119_02_writer'
NEXT_TRIAL_READER = 'tradebot_pp_trial_20261119_02_reader'
TRIAL_ORIGINS = frozenset({TRIAL_ORIGIN, NEXT_TRIAL_ORIGIN})


@dataclass(frozen=True)
class CloudBinding:
    origin_id: str
    writer_role: str
    reader_role: str

    def role(self, *, reader=False):
        if type(reader) is not bool: raise ValueError('explicit boolean reader selection required')
        return self.reader_role if reader else self.writer_role

    @property
    def raw_prefix(self):
        return 'raw-v1/' + sha256(self.origin_id.encode()).hexdigest() + '/'


def cloud_binding(origin_id):
    if origin_id == LEGACY_ORIGIN:
        return CloudBinding(origin_id, 'tradebot_pp_history', 'tradebot_pp_history')
    if origin_id == TRIAL_ORIGIN:
        return CloudBinding(origin_id, TRIAL_WRITER, TRIAL_READER)
    if origin_id == NEXT_TRIAL_ORIGIN:
        return CloudBinding(origin_id, NEXT_TRIAL_WRITER, NEXT_TRIAL_READER)
    raise ValueError('unreviewed exact PP cloud origin')
