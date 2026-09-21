import unittest
from unittest.mock import patch

from render_timeline import choose_encoder, graph


class OperationalEntrypointTests(unittest.TestCase):
    def test_renderer_consumes_arbitrary_segment_count(self):
        plan = {'fps': {'num': 30, 'den': 1}, 'duration_frames': 180, 'segments': [
            {'source_in_s': 1.25, 'source_out_s': 2.5, 'final_in_s': 0, 'final_out_s': 1.25},
            {'source_in_s': 9.0, 'source_out_s': 12.75, 'final_in_s': 1.25, 'final_out_s': 5},
            {'source_in_s': 20.0, 'source_out_s': 21.0, 'final_in_s': 5, 'final_out_s': 6},
        ]}
        value = graph(plan, 1920, 1080, True)
        self.assertIn('concat=n=3:v=1:a=0', value)
        self.assertIn('concat=n=3:v=0:a=1', value)
        self.assertIn('trim=start=9.000000000:end=12.750000000', value)
        self.assertIn('[vcat]ass=captions.ass:fontsdir=fonts[vout]', value)

    def test_gpu_selection_consumes_verified_hardware_result(self):
        with patch('render_timeline.detect', return_value={'ready': True, 'selected_encoder': 'h264_qsv'}):
            self.assertEqual(choose_encoder('ffmpeg', 'auto'), 'h264_qsv')
        with patch('render_timeline.detect', return_value={'ready': False}):
            with self.assertRaises(ValueError):
                choose_encoder('ffmpeg', 'auto')


if __name__ == '__main__':
    unittest.main(verbosity=2)
