import unittest

from render_timeline import choose_encoder, graph


class OperationalEntrypointTests(unittest.TestCase):
    def test_renderer_consumes_arbitrary_segment_count(self):
        plan = {'segments': [
            {'source_in_s': 1.25, 'source_out_s': 2.5},
            {'source_in_s': 9.0, 'source_out_s': 12.75},
            {'source_in_s': 20.0, 'source_out_s': 21.0},
        ]}
        value = graph(plan, 1920, 1080, True)
        self.assertIn('concat=n=3:v=1:a=1', value)
        self.assertIn('trim=start=9.000000000:end=12.750000000', value)
        self.assertIn('[vcat]ass=captions.ass[vout]', value)

    def test_gpu_is_selected_only_when_encoder_is_reported(self):
        import render_timeline
        original = render_timeline.encoders
        try:
            render_timeline.encoders = lambda _: ' V....D h264_nvenc NVIDIA NVENC H.264 encoder'
            self.assertEqual(choose_encoder('ffmpeg', 'auto'), 'h264_nvenc')
            render_timeline.encoders = lambda _: ' V....D libx264 H.264'
            self.assertEqual(choose_encoder('ffmpeg', 'auto'), 'libx264')
        finally:
            render_timeline.encoders = original


if __name__ == '__main__':
    unittest.main(verbosity=2)
