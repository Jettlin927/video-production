"""Static guards; real media behavior is tested in test_render_media.py."""
import unittest
from render_timeline import graph


def fixture():
    return {'fps': {'num': 30, 'den': 1}, 'duration_frames': 61, 'sample_rate': 48000, 'segments': [
        {'id': 'a', 'source_in_s': .1, 'source_out_s': 1.115, 'final_in_s': 0, 'final_out_s': 1.015},
        {'id': 'b', 'source_in_s': 2.1, 'source_out_s': 3.106, 'final_in_s': 1.015, 'final_out_s': 2.021}]}


class RenderGraphTests(unittest.TestCase):
    def test_audio_keeps_sample_lengths_and_pads_only_final_tail(self):
        text = graph(fixture(), 1080, 1920)
        self.assertIn('atrim=start_sample=4800:end_sample=53520', text)
        self.assertIn('atrim=start_sample=100800:end_sample=149088', text)
        self.assertEqual(text.count('apad'), 1)
        self.assertIn('trim=end_frame=30', text)
        self.assertIn('trim=end_frame=31', text)

    def test_tail_reaches_declared_ceil_frame_without_moving_cuts(self):
        plan = fixture(); plan['duration_frames'] = 62
        text = graph(plan, 1080, 1920)
        self.assertIn('trim=end_frame=62', text)
        self.assertIn('atrim=end_sample=99200', text)

    def test_subframe_video_segment_rejected(self):
        plan = fixture(); plan['segments'][0]['final_out_s'] = .001
        with self.assertRaisesRegex(ValueError, 'below one frame'):
            graph(plan, 1080, 1920)


if __name__ == '__main__':
    unittest.main()
