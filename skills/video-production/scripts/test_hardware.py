from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from hardware import detect


class HardwareTests(unittest.TestCase):
    def test_intel_usable_after_listed_nvidia_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            ffmpeg = Path(temp) / 'ffmpeg'; ffmpeg.write_text('fake')
            report = Path(temp) / 'hardware.json'
            with patch('hardware.inventory', return_value={'devices': ['Intel Arc']}), \
                 patch('hardware.run', return_value=SimpleNamespace(stdout='h264_nvenc h264_qsv libx264', stderr='')), \
                 patch('hardware.probe_encoder', side_effect=lambda _, e: {'usable': e != 'h264_nvenc'}) as probe:
                result = detect(ffmpeg, report)
                self.assertEqual(result['selected_encoder'], 'h264_qsv')
                count = probe.call_count
                self.assertTrue(detect(ffmpeg, report)['reused'])
                self.assertEqual(probe.call_count, count)
                ffmpeg.write_text('different binary')
                self.assertFalse(detect(ffmpeg, report)['reused'])
                self.assertGreater(probe.call_count, count)

    def test_driver_change_invalidates_cached_probe(self):
        with tempfile.TemporaryDirectory() as temp:
            ffmpeg = Path(temp) / 'ffmpeg'; ffmpeg.write_text('fake')
            report = Path(temp) / 'hardware.json'
            with patch('hardware.inventory', side_effect=[{'devices': ['driver1']}, {'devices': ['driver2']}]), \
                 patch('hardware.run', return_value=SimpleNamespace(stdout='libx264', stderr='')), \
                 patch('hardware.probe_encoder', return_value={'usable': True}):
                first, second = detect(ffmpeg, report), detect(ffmpeg, report)
                self.assertNotEqual(first['fingerprint'], second['fingerprint'])
                self.assertEqual(second['selected_encoder'], 'libx264')


if __name__ == '__main__':
    unittest.main()
