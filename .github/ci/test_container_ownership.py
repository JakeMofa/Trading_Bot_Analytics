import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import container_ownership as owned

ID = 'a'*64
OWNER = 'b'*32


def response(code=0, stdout='', stderr=''):
    return SimpleNamespace(returncode=code, stdout=stdout, stderr=stderr)


class OwnershipTests(unittest.TestCase):
    def test_name_collision_or_creation_failure_never_creates_receipt_or_deletes(self):
        with tempfile.TemporaryDirectory() as temp:
            receipt = Path(temp)/'receipt.json'
            with patch.object(owned, 'run', return_value=response(1, stderr='name already in use')) as docker:
                with self.assertRaises(RuntimeError):
                    owned.create('fixture', 'tradebot-schema-collision', receipt)
                self.assertFalse(receipt.exists())
                self.assertFalse(owned.cleanup(receipt))
                self.assertEqual(docker.call_count, 1)
                self.assertEqual(docker.call_args.args[0][0], 'create')

    def test_success_records_id_and_owner_then_cleanup_uses_exact_id(self):
        with tempfile.TemporaryDirectory() as temp:
            receipt = Path(temp)/'receipt.json'
            with patch.object(owned, 'run', return_value=response(stdout=ID)) as docker:
                self.assertEqual(owned.create('fixture', 'tradebot-schema-owned', receipt), ID)
                record = json.loads(receipt.read_text())
                self.assertIn(owned.LABEL+'='+record['owner'], docker.call_args.args[0])
            inspected = json.dumps([{'Id': ID, 'Config': {'Labels': {owned.LABEL: record['owner']}}}])
            with patch.object(owned, 'run', side_effect=[response(stdout=inspected), response()]) as docker:
                self.assertTrue(owned.cleanup(receipt))
                self.assertEqual(docker.call_args_list[0].args[0], ['container', 'inspect', ID])
                self.assertEqual(docker.call_args_list[1].args[0], ['rm', '--force', '--volumes', ID])

    def test_wrong_label_or_identity_is_preserved(self):
        for identity, label in [(ID, 'c'*32), ('c'*64, OWNER)]:
            inspected = json.dumps([{'Id': identity, 'Config': {'Labels': {owned.LABEL: label}}}])
            with patch.object(owned, 'run', return_value=response(stdout=inspected)) as docker:
                with self.assertRaises(RuntimeError):
                    owned.cleanup_record({'id': ID, 'owner': OWNER})
                self.assertEqual(docker.call_count, 1)

    def test_missing_receipt_already_removed_and_invalid_receipt_do_not_delete(self):
        with patch.object(owned, 'run', return_value=response(1, stderr='No such container')) as docker:
            self.assertFalse(owned.cleanup_record({'id': ID, 'owner': OWNER}))
            self.assertEqual(docker.call_count, 1)
        with patch.object(owned, 'run') as docker:
            with self.assertRaises(ValueError):
                owned.cleanup_record({'id': 'name', 'owner': OWNER})
            docker.assert_not_called()

    def test_existing_receipt_prevents_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            receipt = Path(temp)/'receipt.json'
            receipt.write_text('{}')
            with patch.object(owned, 'run') as docker:
                with self.assertRaises(ValueError):
                    owned.create('fixture', 'tradebot-schema-owned', receipt)
                docker.assert_not_called()
