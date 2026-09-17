"""ASR anomaly candidates and PCM-to-encoded waveform delay checks (not listening)."""
import argparse
import json
import math
import re
import wave
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'video-production' / 'scripts'))
from bailian_media import load, save


def asr_candidates(doc):
    findings = []
    previous = -math.inf
    for word in doc['words']:
        a = word.get('source_start_s', word.get('start'))
        b = word.get('source_end_s', word.get('end'))
        text = word.get('source_text', word.get('word', word.get('text', '')))
        reasons = []
        valid = isinstance(a, (float, int)) and isinstance(b, (float, int)) and math.isfinite(a) and math.isfinite(b) and b > a >= 0
        if not valid:
            reasons.append('invalid_timestamp')
        else:
            if a < previous:
                reasons.append('overlap_or_reversed_order')
            previous = b
            units = len(re.findall(r'[\u3400-\u9fff]|[A-Za-z0-9]+', text))
            if b - a > max(1.2, units * .8):
                reasons.append('long_word_may_hide_prompt_or_retake')
            if word.get('probability', 1) < .6:
                reasons.append('low_asr_probability')
        if reasons:
            findings.append({'word_id': word['id'], 'text': text, 'source_in_s': a, 'source_out_s': b,
                             'reasons': reasons, 'action': 'Re-recognize overlapping short source windows and review; do not clamp or auto-delete'})
    return {'status': 'candidates_found' if findings else 'no_numeric_candidates', 'findings': findings,
            'listening': 'not_checked', 'note': 'High ASR probability never overrides anomalous timestamps'}


def pcm(path):
    import numpy as np
    with wave.open(str(path), 'rb') as w:
        if w.getsampwidth() != 2:
            raise ValueError('Use signed 16-bit PCM WAV for the sync check')
        sr = w.getframerate()
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2').astype(float)
        return sr, audio.reshape(-1, w.getnchannels()).mean(axis=1)


def sync(reference, encoded, times, window_s=.5, search_ms=100, max_lag_ms=20):
    import numpy as np
    sr, x = pcm(reference)
    sr2, y = pcm(encoded)
    if sr != sr2:
        raise ValueError('Decode both WAVs to the same sample rate')
    n, pad = round(window_s * sr), round(search_ms * sr / 1000)
    if n <= 1 or pad < 1 or max_lag_ms < 0:
        raise ValueError('Invalid correlation settings')
    results = []
    for t in times:
        start = round(t * sr)
        if start < pad or start + n > len(x) or start + n + pad > len(y):
            results.append({'time_s': t, 'status': 'not_checked', 'reason': 'window_outside_audio'}); continue
        a = x[start:start+n]
        b = y[start-pad:start+n+pad]
        if np.std(a) < 20:
            results.append({'time_s': t, 'status': 'not_checked', 'reason': 'unvoiced_reference'}); continue
        # Normalize each candidate window separately: a louder adjacent syllable
        # must not beat an identical but quieter window through energy alone.
        ac = a-a.mean()
        corr = np.correlate(b, ac, mode='valid')
        sums = np.r_[0., np.cumsum(b)]
        squares = np.r_[0., np.cumsum(b*b)]
        energy = np.maximum(0, squares[n:]-squares[:-n]-(sums[n:]-sums[:-n])**2/n)
        denom = np.sqrt(energy*np.sum(ac*ac))
        scores = np.divide(corr, denom, out=np.full_like(corr, -np.inf), where=denom>0)
        if not np.isfinite(scores).any():
            results.append({'time_s': t, 'status': 'not_checked', 'reason': 'unvoiced_encoded'}); continue
        candidates = np.flatnonzero(scores >= np.max(scores)-1e-9)
        peak = int(candidates[np.argmin(abs(candidates-pad))])
        lag = peak - pad
        q = b[peak:peak+n]
        co = float(np.corrcoef(a, q)[0, 1]) if np.std(q) else 0
        lag_ms = lag / sr * 1000
        confident = math.isfinite(co) and co >= .90 and abs(lag) < pad
        results.append({'time_s': t, 'lag_ms': lag_ms, 'correlation': co,
                        'status': ('pass' if abs(lag_ms) <= max_lag_ms else 'fail') if confident else 'not_checked'})
    overall = 'fail' if any(x['status'] == 'fail' for x in results) else ('pass' if results and all(x['status'] == 'pass' for x in results) else 'not_checked')
    return {'status': overall, 'windows': results, 'tolerance_ms': max_lag_ms,
            'positive_lag': 'encoded audio is late relative to timeline PCM', 'listening': 'not_checked'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='mode', required=True)
    a = sub.add_parser('asr'); a.add_argument('--transcript', required=True); a.add_argument('--out', required=True)
    a = sub.add_parser('sync'); a.add_argument('--reference', required=True); a.add_argument('--encoded', required=True)
    a.add_argument('--times', required=True, help='comma-separated final timeline seconds')
    a.add_argument('--out', required=True); a.add_argument('--max-lag-ms', type=float, default=20)
    args = p.parse_args()
    result = asr_candidates(load(args.transcript)) if args.mode == 'asr' else sync(
        args.reference, args.encoded, [float(x) for x in args.times.split(',')], max_lag_ms=args.max_lag_ms)
    save(args.out, result)
    print(json.dumps({'status': result['status'], 'out': args.out}))
