from array import array
import math
import subprocess
import unittest
from unittest.mock import patch

from audio_identity import correlation, verify_audio


class AudioIdentityTests(unittest.TestCase):
    def test_wrong_or_shifted_audio_does_not_pass(self):
        a = [((i * i + i * 131) % 9997) - 5000 for i in range(8000)]
        self.assertAlmostEqual(correlation(a, a), 1)
        self.assertLess(correlation(a, a[50:] + a[:50]), .95)
        self.assertIsNone(correlation([0] * 1000, [0] * 1000))
        self.assertEqual(correlation([0] * 1000, a[:1000]), 0)

    def test_bounded_windows_compare_same_positions(self):
        data = array('h', (round(math.sin(i / 9) * 5000) for i in range(8000))).tobytes()
        with patch('audio_identity.subprocess.run', return_value=subprocess.CompletedProcess([], 0, stdout=data)) as run:
            report = verify_audio('ffmpeg', 'delivered.mp4', 'reference.wav', 100)
        self.assertEqual(report['status'], 'pass')
        self.assertEqual(run.call_count, 10)
        for call in run.call_args_list:
            command = call.args[0]
            self.assertLess(command.index('-ss'), command.index('-i'))
            self.assertEqual(command[command.index('-t') + 1], '1')


if __name__ == '__main__':
    unittest.main()
