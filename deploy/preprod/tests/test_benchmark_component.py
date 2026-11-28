import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from controller import BENCHMARK_INSTANCE
from linux_actions import DISPLAY_ORIGIN, PROJECT, compatible_api_image


class BoundAPIImage(unittest.TestCase):
    def test_only_compatible_latest_api_receipt_matches_current_watch(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        request = SimpleNamespace(source_sha='a'*40, artifact_sha256='b'*64)
        image = 'sha256:'+'c'*64
        context = SimpleNamespace(staging=root, request=request, image=image)
        active = dict(instance=BENCHMARK_INSTANCE,trial_origin=DISPLAY_ORIGIN,state='ready_off',
            nonce='n',initial_a='generation-A',source_sha=request.source_sha,artifact_sha256=request.artifact_sha256,
            image_id=image)
        labels = {'com.docker.compose.service':'api','com.docker.compose.project':PROJECT,
                  'tradebot.source_sha':'d'*40,'tradebot.api_artifact_sha256':'e'*64,
                  'tradebot.api_schema_sha256':'f'*64}
        row = {'Image':'sha256:'+'1'*64,'Config':{'Labels':labels,'User':'10001:10001'}}
        self.enterContext(patch('linux_actions.HostBinding.from_marker',return_value=SimpleNamespace(hostname=BENCHMARK_INSTANCE)))
        self.enterContext(patch('transition_control._read_active',return_value=active))
        self.enterContext(patch('controller._secure_file',side_effect=lambda p:(p.read_bytes(),None)))
        self.assertFalse(compatible_api_image(context,row))
        record = {'version':1,'scope':'benchmark-api-component-v1','nonce':active['nonce'],
                  'instance':BENCHMARK_INSTANCE,'origin':DISPLAY_ORIGIN,'initial_a':active['initial_a'],
                  'collector_source_sha':request.source_sha,'collector_artifact_sha256':request.artifact_sha256,
                  'collector_image':image,'api_source_sha':labels['tradebot.source_sha'],'api_image':row['Image'],
                  'api_artifact_sha256':labels['tradebot.api_artifact_sha256'],
                  'api_schema_sha256':labels['tradebot.api_schema_sha256']}
        target=root/'benchmark-api-component.json'
        target.write_text(json.dumps(record))
        self.assertTrue(compatible_api_image(context,row))
        for k in record:
            with self.subTest(k=k):
                target.write_text(json.dumps(record | {k:'wrong'}))
                self.assertFalse(compatible_api_image(context,row))
        target.write_text(json.dumps(record))
        labels['com.docker.compose.service']='operator'
        self.assertFalse(compatible_api_image(context,row))
