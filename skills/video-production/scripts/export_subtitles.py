"""Export draft SRT from source/final word timestamps. Speaker filtering keeps timeline gaps."""
import argparse
import json
import math
from pathlib import Path
from bailian_media import load, save


def stamp(seconds):
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f'{h:02}:{m:02}:{s:02},{ms:03}'


def export(doc, out, speaker=None, max_chars=24):
    if type(max_chars) is not int or max_chars < 1:
        raise ValueError('max_chars must be a positive integer')
    words = doc['words']
    if not words:
        raise ValueError('No timed words')
    final = any('final_start_s' in w or 'final_end_s' in w for w in words)
    start, end = ('final_start_s', 'final_end_s') if final else ('source_start_s', 'source_end_s')
    speakers, chosen, warnings = {}, [], []
    sentence_speakers = {s.get('id', s.get('utterance_id')): s.get('speaker_id') for s in doc.get('utterances', [])}
    for i, w in enumerate(words):
        a, b = w.get(start), w.get(end)
        if not all(type(v) in (int, float) and math.isfinite(v) for v in [a, b]) or not 0 <= a < b:
            raise ValueError('Missing or invalid word timestamps; do not interpolate')
        sid = w.get('effective_speaker_id', w.get('speaker_id', sentence_speakers.get(w.get('utterance_id'))))
        channel = w.get('channel_id', 0)
        label = str(sid) if sid is not None else 'unknown'
        group = speakers.setdefault((channel, label), {'channel_id': channel, 'speaker_id': sid, 'word_count': 0, 'timed_word_duration_s': 0, 'samples': []})
        group['word_count'] += 1; group['timed_word_duration_s'] += b-a
        utterance = (w.get('instance_id'), w.get('utterance_id'), channel, label)
        text = w.get('corrected_text', w.get('text', '')) + w.get('punctuation', '')
        if not group['samples'] or group['samples'][-1]['utterance_id'] != str(utterance):
            if len(group['samples']) < 3:
                group['samples'].append({'utterance_id': str(utterance), 'start_s': a, 'text': text})
        elif len(group['samples'][-1]['text']) < 100:
            group['samples'][-1]['text'] += text
        if speaker is None or sid is not None and label == str(speaker):
            chosen.append({'position': i, 'key': utterance, 'id': w['id'], 'start': a, 'end': b, 'text': text})
    if not chosen:
        raise ValueError('Selected speaker has no labelled words; inspect speakers/role mapping first')
    cues, current = [], []
    for w in chosen:
        if current and (w['key'] != current[-1]['key'] or w['position'] != current[-1]['position']+1 or
                        w['start']-current[-1]['end'] > 1 or
                        len(''.join(x['text'] for x in current))+len(w['text']) > max_chars):
            cues.append(current); current = []
        current.append(w)
    if current:
        cues.append(current)
    cues.sort(key=lambda c: c[0]['start'])
    entries, rows = [], []
    for i, cue in enumerate(cues, 1):
        a, b, text = cue[0]['start'], max(w['end'] for w in cue), ''.join(w['text'] for w in cue)
        if rows and a < rows[-1]['end_s']-1e-7:
            warnings.append({'cue': i, 'reason': 'overlapping_cues_review_required'})
        if len(text) > max_chars or b-a < .4:
            warnings.append({'cue': i, 'reason': 'long_word_or_short_cue_review_required'})
        entries.append(f'{i}\n{stamp(a)} --> {stamp(b)}\n{text}\n')
        rows.append({'start_s': a, 'end_s': b, 'text': text, 'word_ids': [w['id'] for w in cue]})
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    # Numeric provider IDs are labels, never file paths or assumed actor identities.
    suffix = '.speaker-' + str(speaker) if speaker is not None else ''
    if speaker is not None and not str(speaker).isdigit():
        raise ValueError('speaker must be a numeric provider ID')
    timeline = 'final' if final else 'source'
    name = f'subtitles.{timeline}{suffix}'
    (out / (name + '.srt')).write_text('\n'.join(entries), encoding='utf-8')
    (out / (name + '.md')).write_text('\n\n'.join(r['text'] for r in rows)+'\n', encoding='utf-8')
    save(out / 'speakers.json', {'revision': doc.get('revision'), 'timeline': timeline, 'speakers': list(speakers.values()),
                                'identity_status': 'unassigned; determine on-camera/off-camera roles from source evidence'})
    result = {'revision': doc.get('revision'), 'timeline': timeline, 'speaker_filter': speaker, 'cue_count': len(rows),
              'retained_word_count': len(chosen), 'cues': rows, 'warnings': warnings, 'status': 'review_required',
              'note': 'Draft word-boundary pagination. Filtering preserves timestamps; it does not cut audio/video.'}
    save(out / (name + '.json'), result)
    return {'status': result['status'], 'srt': str(out / (name + '.srt')), 'cues': len(rows), 'words': len(chosen)}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--transcript', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--speaker', type=int, help='Filter captions only; preserve source/final gaps')
    p.add_argument('--max-chars', type=int, default=24, help='Draft cue character limit, never splits a timed word')
    a = p.parse_args()
    try:
        print(json.dumps(export(load(a.transcript), a.out, a.speaker, a.max_chars), ensure_ascii=False))
    except (ValueError, KeyError, OSError) as e:
        p.exit(1, str(e) + '\n')
