"""Bounded decoded-audio identity checks; no provider calls or temporary media files."""
from array import array
import math
import subprocess
import sys


def correlation(a, b):
    n = min(len(a), len(b))
    if n < 100:
        return None
    a, b = a[:n], b[:n]
    ma, mb = sum(a) / n, sum(b) / n
    aa = sum((x - ma) ** 2 for x in a)
    bb = sum((x - mb) ** 2 for x in b)
    if aa < n and bb < n:
        return None
    if aa < n or bb < n:
        return 0.0
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(aa * bb)


def verify_audio(ffmpeg, media, reference, duration):
    def decode(path, start):
        result = subprocess.run([str(ffmpeg), '-v', 'error', '-nostdin', '-ss', str(start), '-i', str(path),
                                 '-t', '1', '-map', '0:a:0', '-ac', '1', '-ar', '8000', '-f', 's16le', '-'],
                                capture_output=True)
        if result.returncode:
            raise ValueError('Reference/delivered audio decode failed')
        samples = array('h'); samples.frombytes(result.stdout)
        if sys.byteorder != 'little':
            samples.byteswap()
        return samples
    windows = []
    starts = sorted({max(0, min(duration - 1, duration * p)) for p in (.1, .3, .5, .7, .9)})
    for start in starts:
        score = correlation(decode(media, start), decode(reference, start))
        windows.append({'start_s': round(start, 3), 'correlation': score,
                        'status': 'not_checked' if score is None else ('pass' if score >= .95 else 'fail')})
    checked = [row for row in windows if row['status'] != 'not_checked']
    status = 'pass' if len(checked) >= min(2, len(starts)) and all(row['status'] == 'pass' for row in checked) else 'fail'
    return {'check': 'narration_identity', 'status': status, 'windows': windows,
            'scope': 'up to five distinct one-second decoded windows; not full listening or semantic review'}
