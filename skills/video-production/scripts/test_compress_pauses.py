import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave
from array import array

import compress_pauses as pauses


class PausePcmTests(unittest.TestCase):
    def test_pcm_wave_does_not_build_a_large_ffmpeg_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / 'source.wav', Path(tmp) / 'out.wav'
            samples = array('h', (round(math.sin(i / 20) * 5000) for i in range(24000)))
            with wave.open(str(source), 'wb') as audio:
                audio.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
                audio.writeframes(samples.tobytes())
            parts = [{'src_start': 0, 'src_end': .4}, {'src_start': .6, 'src_end': 1}]
            with patch.object(pauses, 'run', side_effect=AssertionError('PCM fast path must not invoke FFmpeg')):
                backend = pauses.cut_and_join('ffmpeg', str(source), parts, str(target))
            self.assertEqual(backend, 'pcm-wave')
            with wave.open(str(target), 'rb') as audio:
                self.assertEqual(audio.getnframes(), 19200 - round(pauses.CROSSFADE_S * 24000))
                output = array('h'); output.frombytes(audio.readframes(audio.getnframes()))
            self.assertEqual(output[:100], samples[:100])
            self.assertEqual(output[-100:], samples[-100:])
            self.assertFalse(Path(str(target) + '.filter.txt').exists())

    def test_empty_and_short_pcm_slices_are_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / 'in.wav', Path(tmp) / 'out.wav'
            with wave.open(str(source), 'wb') as audio:
                audio.setparams((1, 2, 1000, 0, 'NONE', 'not compressed'))
                audio.writeframes(array('h', [100] * 1000).tobytes())
            parts = [{'src_start': 0, 'src_end': .4}, {'src_start': .5, 'src_end': .5},
                     {'src_start': .6, 'src_end': .601}, {'src_start': .7, 'src_end': 1}]
            pauses.cut_and_join('unused', str(source), parts, str(target))
            with wave.open(str(target), 'rb') as audio:
                self.assertGreater(audio.getnframes(), 650)


if __name__ == '__main__':
    unittest.main()
