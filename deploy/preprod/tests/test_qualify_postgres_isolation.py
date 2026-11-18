"""The real controller gets a fresh disposable CI volume, never fixture origins."""

import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


HERE=Path(__file__).parents[1]
sys.path.insert(0,str(HERE))
spec=importlib.util.spec_from_file_location('qualify_postgres_isolation',HERE/'qualify_postgres.py')
qualification=importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualification)


class ControllerFixtureIsolation(unittest.TestCase):
    def test_only_claimed_root_ci_can_reset_generated_volume(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            foundation=root/'foundation';foundation.mkdir()
            runtime_secrets=root/'runtime';runtime_secrets.mkdir()
            marker=root/'no-host-marker'
            events=[]
            with patch.dict(os.environ,{'GITHUB_ACTIONS':'true'}), \
                 patch.object(qualification.os,'geteuid',return_value=0), \
                 patch.object(qualification.f,'MARKER',marker), \
                 patch.object(qualification,'CI_FOUNDATION_SECRETS',foundation), \
                 patch.object(qualification,'CI_RUNTIME_SECRETS',runtime_secrets), \
                 patch.object(qualification,'controller_fixture_owned',return_value=True), \
                 patch.object(qualification,'runtime',side_effect=lambda args,env:events.append(('runtime',args))), \
                 patch.object(qualification.f,'run',side_effect=lambda args:events.append(('volume_absent',args)) or ''), \
                 patch.object(qualification.f,'start',side_effect=lambda path:events.append(('foundation',path))), \
                 patch.object(qualification.f,'sql',side_effect=lambda query,path:events.append(('sql',query)) or
                              ('t' if 'to_regclass' in query else '')):
                qualification.isolate_controller_fixture({'mode':'generated'},[(foundation,1,2),(runtime_secrets,3,4)])
                self.assertEqual([event[0] for event in events],
                                 ['runtime','volume_absent','foundation','runtime','sql','sql'])
                self.assertEqual(events[0][1],['down','--volumes','--remove-orphans'])
                self.assertEqual(events[3][1][0:3],['up','-d','--force-recreate'])

    def test_marker_or_missing_ownership_blocks_before_docker(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            foundation=root/'foundation';foundation.mkdir()
            runtime_secrets=root/'runtime';runtime_secrets.mkdir()
            marker=root/'host-marker'
            with patch.dict(os.environ,{'GITHUB_ACTIONS':'true'}), \
                 patch.object(qualification.os,'geteuid',return_value=0), \
                 patch.object(qualification.f,'MARKER',marker), \
                 patch.object(qualification,'CI_FOUNDATION_SECRETS',foundation), \
                 patch.object(qualification,'CI_RUNTIME_SECRETS',runtime_secrets), \
                 patch.object(qualification,'runtime') as runtime:
                with self.assertRaises(RuntimeError):
                    qualification.isolate_controller_fixture({},[])
                marker.write_text('{}')
                with self.assertRaises(RuntimeError):
                    qualification.isolate_controller_fixture({},[(foundation,1,2),(runtime_secrets,3,4)])
                runtime.assert_not_called()


if __name__=='__main__':
    unittest.main()
