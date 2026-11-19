import os
from pathlib import Path
import stat
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from postgres import pp_space


class PPFilesystemTests(unittest.TestCase):
    def reading(self, *, free=pp_space.FLOOR, options='ro', mount=True, elapsed=0, device='8:1'):
        dev = os.makedev(8,1)
        entry = f'2 1 {device} /bound {pp_space.BIND} {options} - ext4 /dev/device rw'
        with patch.object(pp_space.os,'lstat',return_value=SimpleNamespace(st_mode=stat.S_IFREG,st_dev=dev)), \
             patch.object(pp_space.Path,'read_text',return_value=entry if mount else ''), \
             patch.object(pp_space.os,'statvfs',return_value=SimpleNamespace(f_frsize=1,f_bavail=free)), \
             patch.object(pp_space.time,'monotonic',side_effect=[0,elapsed]):
            return pp_space.sample()

    def test_floor_and_untrusted_samples(self):
        self.assertIsNone(self.reading()['space_hold'])
        self.assertEqual(self.reading(free=pp_space.FLOOR-1)['space_hold'],'pp_filesystem_reserve')
        for params in ({'mount':False},{'options':'rw'},{'elapsed':3},{'device':'8:2'}):
            with self.subTest(params=params):
                self.assertEqual(self.reading(**params)['space_hold'],'pp_filesystem_sample_unavailable')
        with patch.object(pp_space.os,'lstat',side_effect=OSError):
            self.assertIsNone(pp_space.sample()['filesystem_free_bytes'])
