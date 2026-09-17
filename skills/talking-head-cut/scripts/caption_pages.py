"""Compile editorial phrase pages from mapped words; no global keyword highlighting.

Each page provides ordered word keys instance_id:id, 1-2 lines, takeaway,
and explicit emphasis spans with role/reason. Emits JSON + SRT, rejects lost words.
"""
import argparse
import json
import math
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'video-production' / 'scripts'))
from bailian_media import load, save


def key(w):
    return w.get('instance_id', 'source') + ':' + w['id']


def word_text(w):
    return w.get('corrected_text', w.get('text', w.get('word', '')))


def frame(t, fps):
    return math.floor(t * fps + .5)


def compile_pages(words_doc, editorial):
    if words_doc['revision'] != editorial['revision']:
        raise ValueError('Stale subtitle revision')
    fps = editorial['fps']['num'] / editorial['fps']['den']
    words = words_doc['words']
    keys = [key(w) for w in words]
    if len(keys) != len(set(keys)):
        raise ValueError('Duplicate word instance keys')
    lookup = dict(zip(keys, words))
    used, caps, warnings = [], [], []
    for i, page in enumerate(editorial['pages']):
        lines = page['lines']
        if not 1 <= len(lines) <= 2 or any(not line for line in lines) or not page.get('takeaway'):
            raise ValueError('Each page requires 1-2 nonempty lines and an editorial takeaway')
        ids = [k for line in lines for k in line]
        if any(k not in lookup for k in ids):
            raise ValueError('Unknown word key')
        used.extend(ids)
        ws = [lookup[k] for k in ids]
        start = frame(ws[0]['final_start_s'], fps)
        end = frame(ws[-1]['final_end_s'], fps)
        end = page.get('end_frame', end)
        if type(end) is not int or not 0 <= start < end <= editorial['duration_frames']:
            raise ValueError('Invalid page interval')
        if end < frame(ws[-1]['final_end_s'], fps):
            raise ValueError('Subtitle would disappear before its final word')
        spans = []
        emphasized = set()
        for span in page.get('emphasis', []):
            selected = span['word_keys']
            if not selected or not span.get('reason') or span.get('role') not in ['focus', 'structure']:
                raise ValueError('Emphasis requires selected words, reason and focus/structure role')
            try:
                first = ids.index(selected[0])
            except ValueError:
                raise ValueError('Emphasis is outside page') from None
            if ids[first:first + len(selected)] != selected:
                raise ValueError('Emphasis must be a complete contiguous phrase inside the page')
            if emphasized.intersection(selected):
                raise ValueError('Conflicting overlapping emphasis spans')
            emphasized.update(selected)
            char_start = sum(len(word_text(lookup[k])) for k in ids[:first])
            char_end = char_start + sum(len(word_text(lookup[k])) for k in selected)
            spans.append({**span, 'start_frame': frame(lookup[selected[0]]['final_start_s'], fps),
                          'start_char': char_start, 'end_char': char_end,
                          'text': ''.join(word_text(lookup[k]) for k in selected),
                          'color_role': 'white' if span['role'] == 'focus' else 'accent'})
        if end - start < .4 * fps:
            warnings.append({'page': i + 1, 'issue': 'short_card', 'action': 'Review phrase grouping; do not change speech to lengthen a card'})
        caps.append({'id': f'c{i+1:03}', 'word_keys': ids, 'start_frame': start, 'end_frame': end,
                     'lines': [''.join(word_text(lookup[k]) for k in line) for line in lines],
                     'takeaway': page['takeaway'], 'layout': page.get('layout', 'body'), 'emphasis': spans})
    if used != keys:
        raise ValueError('Pages must cover every retained word exactly once in final order')
    if any(a['end_frame'] > b['start_frame'] for a, b in zip(caps, caps[1:])):
        raise ValueError('Overlapping pages; revise holds or phrase boundaries')
    for protected in editorial.get('protected_phrases', []):
        normalized = [''.join(c['lines']) for c in caps]
        if protected in ''.join(normalized) and not any(protected in line for c in caps for line in c['lines']):
            raise ValueError('Protected phrase split across pages: ' + protected)
    return {'revision': editorial['revision'], 'fps': editorial['fps'], 'captions': caps, 'warnings': warnings}


def write_srt(result, target):
    fps = result['fps']['num'] / result['fps']['den']
    def stamp(f):
        ms = frame(f / fps, 1000)
        return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
    text = '\n\n'.join(f"{i+1}\n{stamp(c['start_frame'])} --> {stamp(c['end_frame'])}\n" + '\n'.join(c['lines'])
                       for i, c in enumerate(result['captions']))
    Path(target).write_text(text + '\n', encoding='utf-8')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--words', required=True, type=Path)
    p.add_argument('--editorial', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    a = p.parse_args()
    result = compile_pages(load(a.words), load(a.editorial))
    save(a.out, result)
    write_srt(result, a.out.with_suffix('.srt'))
    print(json.dumps({'pages': len(result['captions']), 'warnings': result['warnings']}, ensure_ascii=False))
