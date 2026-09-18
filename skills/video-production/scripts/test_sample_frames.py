import unittest

from sample_frames import build_command, parse_ranges, parse_rate


class SampleFrameTests(unittest.TestCase):
    def test_parse_ranges_is_inclusive(self):
        self.assertEqual(parse_ranges('100:109,200:209'), [(100, 109), (200, 209)])

    def test_parse_rejects_reversed_range(self):
        with self.assertRaises(ValueError):
            parse_ranges('10:9')

    def test_command_uses_per_range_seek_and_concat(self):
        command = build_command('ffmpeg.exe', 'input.mp4', 'out.mp4',
                                [(100, 109), (200, 209)], parse_rate('50/1'))
        joined = ' '.join(command)
        self.assertEqual(command.count('-ss'), 2)
        self.assertIn('trim=end_frame=10', joined)
        self.assertIn('concat=n=2:v=1:a=0', joined)
        self.assertNotIn("select='", joined)


if __name__ == '__main__':
    unittest.main(verbosity=2)
