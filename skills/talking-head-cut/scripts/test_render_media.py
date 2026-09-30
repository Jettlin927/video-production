"""Real FFmpeg regression: fractional source FPS, many cuts and sample-accurate audio."""
import array
import json
import math
import os
from pathlib import Path
import random
import subprocess
import tempfile
import unittest
import wave
from unittest.mock import patch

from render_timeline import main as render, graph


@unittest.skipUnless(os.environ.get('VIDEO_TEST_FFMPEG'), 'Set VIDEO_TEST_FFMPEG/FFPROBE for real media tests')
class RenderMediaTests(unittest.TestCase):
    def test_late_seek_matches_unseeked_frame_and_audio_reference(self):
        import numpy as np
        ffmpeg, ffprobe = os.environ['VIDEO_TEST_FFMPEG'], os.environ['VIDEO_TEST_FFPROBE']
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); sr = 48000
            samples = np.random.default_rng(22).integers(-6000, 6000, sr * 6, dtype=np.int16)
            with wave.open(str(root / 'raw.wav'), 'wb') as stream:
                stream.setparams((1, 2, sr, len(samples), 'NONE', '')); stream.writeframes(samples.tobytes())
            source = root / 'raw.mkv'
            subprocess.run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=s=160x96:r=60000/1001:d=6',
                            '-i', str(root / 'raw.wav'), '-c:v', 'libx264', '-preset', 'ultrafast',
                            '-c:a', 'pcm_s16le', str(source)], check=True)
            segments = []; cursor = 0
            for i, (a, b) in enumerate([(4.213, 4.714), (2.133, 2.834), (5.133, 5.734)]):
                count = round(b * sr) - round(a * sr)
                fa, fb = cursor / sr, (cursor + count) / sr
                segments.append({'id': str(i), 'source_in_s': a, 'source_out_s': b,
                    'source_in_frame': round(a * 60000 / 1001), 'source_out_frame': round(b * 60000 / 1001),
                    'final_in_s': fa, 'final_out_s': fb, 'final_in_frame': round(fa * 30),
                    'final_out_frame': round(fb * 30), 'duration_frames': round(fb * 30) - round(fa * 30)})
                cursor += count
            frames = math.ceil(cursor / sr * 30)
            plan = {'revision': 'late-seek', 'source': {'duration_s': 6, 'fps': {'num': 60000, 'den': 1001}},
                    'fps': {'num': 30, 'den': 1}, 'duration_frames': frames, 'duration_s': frames / 30,
                    'sample_rate': sr, 'audio_samples': cursor, 'segments': segments}
            (root / 'plan.json').write_text(json.dumps(plan))
            commands = []
            real_run = subprocess.run
            def capture(command, **kwargs):
                commands.append(command)
                return real_run(command, **kwargs)
            with patch('render_timeline.subprocess.run', side_effect=capture):
                render(['--source', str(source), '--plan', str(root / 'plan.json'), '--ffmpeg', ffmpeg,
                        '--out', str(root / 'seek.mp4'), '--width', '160', '--height', '96',
                        '--encoder', 'libx264', '--preset', 'ultrafast'])
            command = commands[-1]
            self.assertLess(command.index('-ss'), command.index('-i'))
            self.assertEqual(command[command.index('-ss') + 1], '2')
            # Old graph, no input seek: same source, plan, codec and settings.
            (root / 'reference-graph.txt').write_text(graph(plan, 160, 96))
            real_run([ffmpeg, '-v', 'error', '-i', str(source), '-/filter_complex', str(root / 'reference-graph.txt'),
                      '-map', '[vout]', '-map', '[aout]', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18',
                      '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', str(root / 'reference.mp4')], check=True)
            def decode(path, args):
                return subprocess.check_output([ffmpeg, '-v', 'error', '-i', str(path), *args, '-'])
            a = decode(root / 'seek.mp4', ['-an', '-f', 'rawvideo', '-pix_fmt', 'rgb24'])
            b = decode(root / 'reference.mp4', ['-an', '-f', 'rawvideo', '-pix_fmt', 'rgb24'])
            self.assertEqual(a, b, 'Input seek changed retained video frames')
            audio_args = ['-vn', '-f', 's16le', '-ac', '1', '-ar', str(sr)]
            a = np.frombuffer(decode(root / 'seek.mp4', audio_args), dtype='<i2').astype(float)
            b = np.frombuffer(decode(root / 'reference.mp4', audio_args), dtype='<i2').astype(float)
            self.assertEqual(len(a), len(b))
            self.assertGreater(np.corrcoef(a, b)[0, 1], .999)

    def test_frames_and_audio_stay_on_canonical_grids(self):
        import numpy as np
        ffmpeg, ffprobe = os.environ['VIDEO_TEST_FFMPEG'], os.environ['VIDEO_TEST_FFPROBE']
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); sr = 48000; rng = random.Random(31)
            samples = array.array('h', [int(8000 * math.sin(i * .071 + i * i * .0000001) + rng.uniform(-1500, 1500)) for i in range(sr * 6)])
            with wave.open(str(root / 'raw.wav'), 'wb') as stream:
                stream.setparams((1, 2, sr, len(samples), 'NONE', '')); stream.writeframes(samples.tobytes())
            subprocess.run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=s=160x96:r=60000/1001:d=6',
                            '-i', str(root / 'raw.wav'), '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'pcm_s16le',
                            str(root / 'raw.mkv')], check=True)
            segments, cursor = [], 0
            for i, (a, b) in enumerate([(0.133, .564), (.72, 1.347), (1.5, 1.831), (2.1, 2.529), (2.8, 3.257), (3.5, 4.031), (4.3, 4.711), (5, 5.589)]):
                sa, sb = round(a * sr), round(b * sr); fa, fb = cursor / sr, (cursor + sb - sa) / sr
                segments.append({'id': str(i), 'source_in_s': a, 'source_out_s': b, 'final_in_s': fa, 'final_out_s': fb,
                                 'source_in_frame': round(a * 60000 / 1001), 'source_out_frame': round(b * 60000 / 1001),
                                 'final_in_frame': round(fa * 30), 'final_out_frame': round(fb * 30),
                                 'duration_frames': round(fb * 30) - round(fa * 30)})
                cursor += sb - sa
            frames = math.ceil(cursor / sr * 30)
            plan = {'revision': 'media-regression', 'source': {'duration_s': 6, 'fps': {'num': 60000, 'den': 1001}},
                    'fps': {'num': 30, 'den': 1}, 'duration_frames': frames, 'duration_s': frames / 30,
                    'sample_rate': sr, 'audio_samples': cursor, 'segments': segments}
            (root / 'plan.json').write_text(json.dumps(plan))
            render(['--source', str(root / 'raw.mkv'), '--plan', str(root / 'plan.json'), '--ffmpeg', ffmpeg,
                    '--out', str(root / 'out.mp4'), '--width', '160', '--height', '96', '--encoder', 'libx264', '--preset', 'ultrafast'])
            probe = json.loads(subprocess.check_output([ffprobe, '-v', 'error', '-select_streams', 'v:0', '-show_frames',
                    '-show_streams', '-of', 'json', str(root / 'out.mp4')]))
            self.assertEqual(len(probe['frames']), frames)
            self.assertEqual(probe['streams'][0]['r_frame_rate'], '30/1')
            pts = [float(f['best_effort_timestamp_time']) for f in probe['frames']]
            self.assertLess(max(abs(t - i / 30) for i, t in enumerate(pts)), .000002)
            pcm = subprocess.check_output([ffmpeg, '-v', 'error', '-i', str(root / 'out.mp4'), '-vn', '-f', 's16le', '-ac', '1', '-ar', str(sr), '-'])
            decoded = np.frombuffer(pcm, dtype='<i2').astype(float)
            original = np.asarray(samples, dtype=float)
            offsets = []
            for seg in segments:
                a = round(seg['source_in_s'] * sr) + 1500
                b = round(seg['final_in_s'] * sr) + 1500
                expected = original[a:a + 4000]
                correlations = [np.corrcoef(expected, decoded[b + lag:b + lag + 4000])[0, 1] for lag in range(-100, 101)]
                lag = int(np.argmax(correlations)) - 100; offsets.append(lag)
                self.assertLessEqual(abs(lag), 1)
                self.assertGreater(max(correlations), .9)
            print('REAL_MEDIA: frames=%d continuous_pts=true per_cut_audio_lag_samples=%s' % (frames, offsets))
            # A graph far beyond CreateProcess's command-line budget must still render.
            long_plan = dict(plan)
            long_plan.update(duration_frames=450, duration_s=15, audio_samples=15 * sr)
            long_plan['segments'] = [dict(id=str(i), source_in_s=.1, source_out_s=.2,
                source_in_frame=6, source_out_frame=12, final_in_s=i / 10, final_out_s=(i + 1) / 10,
                final_in_frame=i * 3, final_out_frame=(i + 1) * 3) for i in range(150)]
            (root / 'long-plan.json').write_text(json.dumps(long_plan))
            render(['--source', str(root / 'raw.mkv'), '--plan', str(root / 'long-plan.json'), '--ffmpeg', ffmpeg,
                    '--out', str(root / 'long.mp4'), '--width', '160', '--height', '96', '--encoder', 'libx264', '--preset', 'ultrafast'])
            self.assertGreater((root / 'long.mp4').stat().st_size, 1000)
            print('REAL_MEDIA: 150-segment file-based filter graph rendered')


if __name__ == '__main__':
    unittest.main()
