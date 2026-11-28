"""Independent scratch, deadline and role-routing checks; no host/DB access."""
from contextlib import contextmanager
import errno
import hashlib
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller import Budget, DeploymentHold
import linux_actions
import metadata_inventory as inventory


class Exchange:
    def __init__(self, hashes, *, after_fetch=None):
        self.hashes = hashes
        self.position = 0
        self.after_fetch = after_fetch
        self.commands = []

    def __call__(self, query):
        self.commands.append(query)
        if query.startswith('SELECT to_json(count(*)'):
            return [len(self.hashes)]
        if query.startswith('FETCH '):
            rows = self.hashes[self.position:self.position + inventory.FETCH_ROWS]
            self.position += len(rows)
            if self.after_fetch:
                self.after_fetch()
            return rows
        if query.startswith('SELECT to_json(coalesce(bool_and'):
            return [True]
        if query.startswith(('BEGIN ', 'DECLARE ', 'CLOSE ')):
            return []
        raise AssertionError('unexpected query')


class CaptureFile:
    def __init__(self, stream, *, write_error=None):
        self.stream = stream
        self.write_error = write_error
        self.written = 0
        self.calls = []
        self.anonymous = os.fstat(stream.fileno()).st_nlink == 0
        self.inheritable = os.get_inheritable(stream.fileno())

    def __getattr__(self, name):
        return getattr(self.stream, name)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.stream.close()

    def write(self, data):
        if self.write_error:
            raise self.write_error
        self.calls.append(len(data))
        n = self.stream.write(data)
        self.written += n
        return n


class MetadataInventoryResources(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(tempfile.TemporaryDirectory())
        self.files = []
        self.native_temporary_file = tempfile.TemporaryFile
        self.enterContext(patch.object(inventory.shutil, 'disk_usage', return_value=
            SimpleNamespace(free=inventory.RESERVE_BYTES + inventory.MAX_BYTES + 4096)))

    def capture(self, **kwargs):
        def factory(*args, **options):
            stream = CaptureFile(self.native_temporary_file(*args, **options), **kwargs)
            self.files.append(stream)
            return stream
        return patch.object(inventory.tempfile, 'TemporaryFile', side_effect=factory)

    def digest(self, exchange, budget=None):
        return inventory.metadata_digest(exchange, 'core.markets',
            'origin_id,market_id,content_hash', budget or Budget(180), self.directory)

    def test_one_unlinked_noninherited_file_and_exact_binary_scratch_cap(self):
        rows = [hashlib.sha256(str(n).encode()).hexdigest() for n in range(10)]
        with (self.capture(), patch.object(inventory, 'MAX_BYTES', 320),
              patch.object(inventory, 'RUN_ROWS', 2)):
            result = self.digest(Exchange(rows))
        self.assertEqual(result['count'], 10)
        self.assertEqual(len(self.files), 1)
        file = self.files[0]
        self.assertTrue(file.anonymous)
        self.assertFalse(file.inheritable)
        self.assertTrue(file.closed)
        self.assertEqual(file.written, 320)
        self.assertEqual(file.calls, [64] * 5)
        self.assertEqual(list(Path(self.directory).iterdir()), [])

    def test_over_cap_refuses_before_creating_scratch_or_opening_cursor(self):
        with (self.capture(), patch.object(inventory, 'MAX_BYTES', 64)):
            exchange = Exchange(['a' * 64] * 3)
            with self.assertRaisesRegex(DeploymentHold, 'metadata_scratch_limit'):
                self.digest(exchange)
        self.assertEqual(self.files, [])
        self.assertFalse(any(q.startswith('DECLARE ') for q in exchange.commands))

    def test_existing_reserve_is_not_spent_on_scratch(self):
        with (self.capture(), patch.object(inventory.shutil, 'disk_usage', return_value=
                SimpleNamespace(free=inventory.RESERVE_BYTES + 31))):
            with self.assertRaisesRegex(DeploymentHold, 'metadata_scratch_reserve'):
                self.digest(Exchange(['a' * 64]))
        self.assertEqual(self.files, [])

    def test_falling_headroom_refuses_write_and_closes_anonymous_file(self):
        free = (inventory.RESERVE_BYTES + 64, inventory.RESERVE_BYTES + 31)
        with (self.capture(), patch.object(inventory.shutil, 'disk_usage',
                side_effect=[SimpleNamespace(free=n) for n in free])):
            with self.assertRaisesRegex(DeploymentHold, 'metadata_scratch_reserve'):
                self.digest(Exchange(['a' * 64]))
        self.assertEqual(len(self.files), 1)
        self.assertEqual(self.files[0].written, 0)
        self.assertTrue(self.files[0].closed)

    def test_deadline_after_fetch_closes_file_without_continuing_sql_or_folding(self):
        class Deadline:
            expired = False
            def timeout(self):
                return 0 if self.expired else 180
        budget = Deadline()
        def expire():
            budget.expired = True
        exchange = Exchange(['a' * 64] * inventory.FETCH_ROWS, after_fetch=expire)
        with self.capture():
            with self.assertRaisesRegex(DeploymentHold, 'deadline_exceeded'):
                self.digest(exchange, budget)
        self.assertEqual(len(self.files), 1)
        self.assertTrue(self.files[0].closed)
        self.assertFalse(any(q.startswith('CLOSE ') for q in exchange.commands))
        self.assertFalse(any('bool_and' in q for q in exchange.commands))

    def test_os_disk_error_keeps_scratch_anonymous_and_closes_it(self):
        with self.capture(write_error=OSError(errno.ENOSPC, 'generated fixture full')):
            with self.assertRaises(OSError) as caught:
                self.digest(Exchange(['a' * 64]))
        self.assertEqual(caught.exception.errno, errno.ENOSPC)
        self.assertTrue(self.files[0].closed)
        self.assertEqual(list(Path(self.directory).iterdir()), [])

    def test_run_and_read_buffer_bounds_are_unchanged(self):
        self.assertEqual((inventory.MAX_BYTES, inventory.RESERVE_BYTES),
                         (64 * 1024**2, 10 * 1024**3))
        self.assertEqual(inventory.MAX_BYTES // (inventory.RUN_ROWS * inventory.ROW_BYTES), 256)
        self.assertEqual(inventory.FETCH_ROWS, 512)
        reads = []
        native_pread = os.pread
        def pread(fd, size, offset):
            reads.append(size)
            return native_pread(fd, size, offset)
        with self.native_temporary_file(dir=self.directory, buffering=0) as file:
            content = b'a' * (4096 + inventory.ROW_BYTES)
            file.write(content)
            with patch.object(inventory.os, 'pread', side_effect=pread):
                rows = list(inventory._read_run(file.fileno(), 0, file.tell(),
                    hashlib.sha256(content).digest()))
        self.assertEqual(reads, [4096, inventory.ROW_BYTES])
        self.assertEqual(len(rows), 129)

    def test_same_length_scratch_corruption_is_rejected_and_file_closed(self):
        native_pread = os.pread
        flipped = []
        def pread(fd, size, offset):
            block = native_pread(fd, size, offset)
            if not flipped:
                flipped.append(True)
                block = bytes([block[0] ^ 1]) + block[1:]
            return block
        with (self.capture(), patch.object(inventory.os, 'pread', side_effect=pread),
              patch.object(inventory, 'RUN_ROWS', 2)):
            # Mock native-order answers deliberately stay True; integrity must
            # not depend on a bit flip coincidentally breaking sort order.
            with self.assertRaisesRegex(DeploymentHold, 'metadata_scratch_hash_mismatch'):
                self.digest(Exchange(['a' * 64] * 5))
        self.assertTrue(flipped)
        self.assertTrue(self.files[0].closed)
        self.assertEqual(list(Path(self.directory).iterdir()), [])

    def test_short_scratch_read_is_rejected_and_file_closed(self):
        native_pread = os.pread
        def pread(fd, size, offset):
            return native_pread(fd, size, offset)[:-1]
        with (self.capture(), patch.object(inventory.os, 'pread', side_effect=pread)):
            with self.assertRaisesRegex(DeploymentHold, 'metadata_scratch_short_read'):
                self.digest(Exchange(['a' * 64] * 5))
        self.assertTrue(self.files[0].closed)

    def test_partial_scratch_write_is_rejected_and_file_closed(self):
        def short_write(file, data):
            return file.stream.write(data[:-1])
        with (self.capture(), patch.object(CaptureFile, 'write', short_write)):
            with self.assertRaisesRegex(DeploymentHold, 'metadata_scratch_short_write'):
                self.digest(Exchange(['a' * 64] * 5))
        self.assertTrue(self.files[0].closed)

    def test_headroom_loss_after_write_closes_file_and_refuses_proof(self):
        free = (inventory.RESERVE_BYTES + 64, inventory.RESERVE_BYTES + 32,
                inventory.RESERVE_BYTES - 1)
        with (self.capture(), patch.object(inventory.shutil, 'disk_usage',
                side_effect=[SimpleNamespace(free=n) for n in free])):
            with self.assertRaisesRegex(DeploymentHold, 'metadata_scratch_reserve'):
                self.digest(Exchange(['a' * 64]))
        self.assertEqual(self.files[0].written, 32)
        self.assertTrue(self.files[0].closed)

    def test_archive_metadata_uses_reader_even_outside_watch_mode(self):
        actions = linux_actions.LinuxActions()
        actions.pg_id = 'generated-fixture-postgres'
        actions.watch_diagnostics = False
        captured = []
        @contextmanager
        def channel(args, _budget, _env, _cleanup):
            captured.append(args)
            yield lambda _: []
        with patch.object(linux_actions, 'psql_channel', channel):
            with actions._outbox_channel(Budget(180), require_reader=True):
                pass
            with actions._outbox_channel(Budget(180)):
                pass
        self.assertEqual(captured[0][captured[0].index('-U') + 1], 'tradebot_reader')
        self.assertEqual(captured[1][captured[1].index('-U') + 1], 'tradebot_app')
