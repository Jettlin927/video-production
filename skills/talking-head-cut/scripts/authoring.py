"""Deterministic authoring adapters: word ranges in, validated production files out."""
import argparse
import copy
import hashlib
import json
import math
from fractions import Fraction
from pathlib import Path
import shutil
import subprocess

from map_words import remap
from semantic_pacing import prepare
from caption_pages import compile_pages, key, word_text, write_srt


FONT = Path(__file__).resolve().parents[2] / 'video-production/assets/fonts/source-han-sans/SourceHanSansSC-Light.otf'


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def index(transcript, out):
    words = transcript['words']
    if not words or len({w['id'] for w in words}) != len(words):
        raise ValueError('Transcript must have nonempty, unique word IDs')
    out.mkdir(parents=True, exist_ok=True)
    rows = ['index\tid\tstart_s\tend_s\ttext']
    rows += [f"{i}\t{w['id']}\t{w['source_start_s']}\t{w['source_end_s']}\t{word_text(w).replace(chr(9), ' ').replace(chr(10), ' ')}"
             for i, w in enumerate(words, 1)]
    (out / 'words.tsv').write_text('\n'.join(rows) + '\n', encoding='utf-8')
    draft = out / 'selection.json'
    if not draft.exists():
        save(draft, {'source_revision': transcript['revision'], 'review': 'not_checked',
                     'ranges': [{'first': 1, 'last': len(words), 'reason': '保留全部；根据词索引选择有效内容'}]})
    return {'words': len(words), 'index': str(out / 'words.tsv'), 'selection': str(draft)}


def select(transcript, selection, source, ffprobe, out, fps=30, width=None, height=None):
    if selection.get('source_revision') != transcript['revision']:
        raise ValueError('Stale selection source_revision')
    words = transcript['words']
    result = subprocess.run([str(ffprobe), '-v', 'error', '-show_streams', '-show_format',
                             '-of', 'json', str(source)], capture_output=True, text=True,
                            encoding='utf-8', errors='replace', check=True)
    meta = json.loads(result.stdout)
    video = next(s for s in meta['streams'] if s['codec_type'] == 'video')
    if not any(s['codec_type'] == 'audio' for s in meta['streams']):
        raise ValueError('Talking-head source needs an audio stream')
    source_rate = Fraction(video['avg_frame_rate'])
    duration = float(meta['format']['duration'])
    vw, vh = video['width'], video['height']
    rotation = next((s.get('rotation', 0) for s in video.get('side_data_list', []) if 'rotation' in s), 0)
    if abs(round(rotation)) % 180 == 90:
        vw, vh = vh, vw
    if (width is None) != (height is None):
        raise ValueError('Provide both width and height, or neither')
    if width is None:
        scale = min(1, 1080 / min(vw, vh))
        width, height = round(vw * scale / 2) * 2, round(vh * scale / 2) * 2
    if fps <= 0 or width <= 0 or height <= 0 or width % 2 or height % 2:
        raise ValueError('Positive FPS and positive even dimensions required')
    errors, used, segments, cursor = [], set(), [], 0
    for i, item in enumerate(selection.get('ranges', []), 1):
        a, b = item.get('first'), item.get('last')
        if type(a) is not int or type(b) is not int or not 1 <= a <= b <= len(words) or not item.get('reason'):
            errors.append({'range': i, 'error': 'first/last must name an inclusive word-index range; reason required'})
            continue
        if used.intersection(range(a, b + 1)):
            errors.append({'range': i, 'error': 'Duplicate retained words'})
            continue
        used.update(range(a, b + 1))
        start, end = words[a - 1]['source_start_s'], words[b - 1]['source_end_s']
        # Preserve up to 40ms handles without accidentally retaining adjacent omitted words.
        start = max(0, start - .04, words[a - 2]['source_end_s'] if a > 1 else 0)
        end = min(duration, end + .04, words[b]['source_start_s'] if b < len(words) else duration)
        sa, sb = round(start * 48000), round(end * 48000)
        if sb <= sa:
            errors.append({'range': i, 'error': 'Empty or overlapping source timing; inspect original audio'})
            continue
        fa, fb = cursor / 48000, (cursor + sb - sa) / 48000
        segments.append({'id': f'k{i:04}', 'source_in_s': sa / 48000, 'source_out_s': sb / 48000,
                         'final_in_s': fa, 'final_out_s': fb, 'reason': item['reason']})
        cursor += sb - sa
    if not segments:
        errors.append({'error': 'No retained ranges'})
    if errors:
        save(out / 'selection-errors.json', errors)
        raise ValueError(json.dumps(errors, ensure_ascii=False))
    stat = source.stat()
    source_info = {'path': str(source.resolve()), 'duration_s': duration,
                   'fps': {'num': source_rate.numerator, 'den': source_rate.denominator},
                   'size': stat.st_size, 'modified_ns': stat.st_mtime_ns}
    revision = 'selection-' + digest([selection, source_info, transcript, fps, width, height])
    frames = math.ceil(cursor / 48000 * fps - 1e-7)
    plan = {'revision': revision, 'source': source_info, 'width': width, 'height': height,
            'fps': {'num': fps, 'den': 1}, 'duration_frames': frames, 'duration_s': frames / fps,
            'sample_rate': 48000, 'audio_samples': cursor, 'audio_duration_s': cursor / 48000,
            'timing_mode': 'sample_audio_cumulative_video', 'segments': segments}
    mapped = remap(transcript, plan)
    save(out / 'selection-plan.json', plan)
    save(out / 'words.selected.json', mapped)
    decisions_path = out / 'pause-decisions.json'
    old_decisions = load(decisions_path) if decisions_path.exists() else None
    if not old_decisions or old_decisions.get('revision') != revision:
        if old_decisions:
            save(out / ('pause-decisions.previous-' + digest(old_decisions) + '.json'), old_decisions)
        save(decisions_path, prepare(mapped))
    return {'revision': revision, 'segments': len(segments), 'words': len(mapped['words'])}


def caption_draft(words, plan, out, max_chars=16):
    if words['revision'] != plan['revision']:
        raise ValueError('Stale mapped words')
    pages, first, length = [], 1, 0
    for i, w in enumerate(words['words'], 1):
        text = word_text(w)
        if length and length + len(text) > max_chars:
            pages.append({'lines': [[first, i - 1]], 'emphasis': []})
            first, length = i, 0
        length += len(text)
        if text.endswith(('。', '！', '？', '；', '!', '?')):
            pages.append({'lines': [[first, i]], 'emphasis': []})
            first, length = i + 1, 0
    if first <= len(words['words']):
        pages.append({'lines': [[first, len(words['words'])]], 'emphasis': []})
    if out.exists():
        raise FileExistsError('Caption draft already exists; edit it or choose a new output')
    draft = {'revision': words['revision'], 'review': 'not_checked', 'corrections': [], 'pages': pages}
    save(out, draft)
    rows = ['index\tkey\ttext'] + [f'{i}\t{key(w)}\t{word_text(w)}' for i, w in enumerate(words['words'], 1)]
    out.with_suffix('.tsv').write_text('\n'.join(rows) + '\n', encoding='utf-8')
    return {'pages': len(pages), 'draft': str(out), 'index': str(out.with_suffix('.tsv'))}


def compile_authored(words, plan, draft):
    """Collect page errors together. Authors never reconstruct text to look up IDs."""
    errors, pages, used = [], [], []
    words = copy.deepcopy(words)
    ws = words['words']
    if words['revision'] != plan['revision'] or draft.get('revision') != plan['revision']:
        return None, [{'error': 'Stale revision; recreate caption draft for this plan'}]
    corrected = set()
    for fix in draft.get('corrections', []):
        i = fix.get('word')
        if type(i) is not int or not 1 <= i <= len(ws) or i in corrected or not isinstance(fix.get('text'), str) or not fix.get('reason'):
            errors.append({'correction': fix, 'error': 'Unique word index, text and reason required'})
        else:
            ws[i - 1]['corrected_text'] = fix['text']
            corrected.add(i)
    for n, page in enumerate(draft.get('pages', []), 1):
        try:
            lines, ids, indexes = [], [], []
            for span in page['lines']:
                a, b = span
                if type(a) is not int or type(b) is not int or not 1 <= a <= b <= len(ws):
                    raise ValueError('Line range must be [first,last], inclusive indexes from caption TSV')
                indexes.extend(range(a, b + 1))
                line = [key(w) for w in ws[a - 1:b]]
                lines.append(line)
                ids.extend(line)
            used.extend(indexes)
            emphasis = []
            for span in page.get('emphasis', []):
                a, b = span['first'], span['last']
                if type(a) is not int or type(b) is not int or not 1 <= a <= b <= len(ws):
                    raise ValueError('Invalid emphasis indexes')
                emphasis.append({'word_keys': [key(w) for w in ws[a - 1:b]],
                                 'role': span['role'], 'reason': span['reason']})
            authored = {'lines': lines, 'emphasis': emphasis,
                        'takeaway': page.get('takeaway') or ''.join(word_text(ws[i - 1]) for i in indexes)}
            base = {'revision': plan['revision'], 'fps': plan['fps'], 'duration_frames': plan['duration_frames']}
            compile_pages({**words, 'words': [ws[i - 1] for i in indexes]}, {**base, 'pages': [authored]})
            pages.append(authored)
        except (ValueError, KeyError, TypeError) as exc:
            errors.append({'page': n, 'error': str(exc)})
    if used != list(range(1, len(ws) + 1)):
        from collections import Counter
        counts = Counter(used)
        errors.append({'error': 'Word coverage/order mismatch',
                       'missing': [i for i in range(1, len(ws) + 1) if not counts[i]],
                       'duplicates': [i for i, count in counts.items() if count > 1]})
    if errors:
        return None, errors
    try:
        return compile_pages(words, {**base, 'pages': pages}), []
    except ValueError as exc:
        return None, [{'error': str(exc)}]


def write_ass(captions, plan, target, font):
    from fontTools.ttLib import TTFont
    with TTFont(font) as face:
        family = face['name'].getDebugName(1)
        cmap = face.getBestCmap()
        missing = sorted({ch for c in captions['captions'] for line in c['lines'] for ch in line
                          if not ch.isspace() and ord(ch) not in cmap})
    if missing:
        raise ValueError('Font lacks characters: ' + ''.join(missing))
    if not family or any(c in family for c in ',\n\r'):
        raise ValueError('Invalid font family')
    fonts = target.parent / 'fonts'
    fonts.mkdir(exist_ok=True)
    shutil.copy2(font, fonts / font.name)
    if (font.parent / 'LICENSE.txt').exists():
        shutil.copy2(font.parent / 'LICENSE.txt', fonts / 'LICENSE.txt')
    width, height = plan['width'], plan['height']
    size = max(16, round(min(width, height) * .052))
    fps = plan['fps']['num'] / plan['fps']['den']
    def stamp(frame):
        cs = round(frame / fps * 100)
        return f'{cs // 360000}:{cs // 6000 % 60:02}:{cs // 100 % 60:02}.{cs % 100:02}'
    def escape(s):
        return s.replace('\\', '＼').replace('{', '｛').replace('}', '｝').replace('\n', ' ')
    rows = ['[Script Info]', 'ScriptType: v4.00+', f'PlayResX: {width}', f'PlayResY: {height}',
            'WrapStyle: 2', '[V4+ Styles]',
            'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding',
            f'Style: Default,{family},{size},&H00FFFFFF,&H00FFFFFF,&H00202020,&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,{width // 20},{width // 20},{height // 9},1',
            '[Events]', 'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text']
    for c in captions['captions']:
        starts = {s['start_char']: s for s in c['emphasis']}
        ends = {s['end_char'] for s in c['emphasis']}
        text, offset = '', 0
        for ln, line in enumerate(c['lines']):
            if ln:
                text += '\\N'
            for ch in line:
                if offset in ends:
                    text += '{\\r}'
                if offset in starts:
                    color = '&H00C8D250&' if starts[offset]['role'] == 'structure' else '&H00FFFFFF&'
                    text += '{\\b1\\c' + color + '}'
                text += escape(ch)
                offset += 1
        rows.append(f"Dialogue: 0,{stamp(c['start_frame'])},{stamp(c['end_frame'])},Default,,0,0,0,,{text}")
    target.write_text('\n'.join(rows) + '\n', encoding='utf-8')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['index', 'select', 'caption-draft', 'caption-build'])
    for name in ['transcript', 'selection', 'source', 'ffprobe', 'words', 'plan', 'draft', 'out']:
        p.add_argument('--' + name, type=Path)
    p.add_argument('--font', type=Path, default=FONT)
    p.add_argument('--fps', type=int, default=30)
    p.add_argument('--width', type=int); p.add_argument('--height', type=int)
    a = p.parse_args(argv)
    if a.action == 'index':
        result = index(load(a.transcript), a.out)
    elif a.action == 'select':
        result = select(load(a.transcript), load(a.selection), a.source, a.ffprobe, a.out, a.fps, a.width, a.height)
    elif a.action == 'caption-draft':
        result = caption_draft(load(a.words), load(a.plan), a.out)
    else:
        plan = load(a.plan)
        result, errors = compile_authored(load(a.words), plan, load(a.draft))
        save(a.out / 'validation.json', {'status': 'fail' if errors else 'pass', 'errors': errors})
        if errors:
            print(json.dumps({'status': 'fail', 'errors': errors}, ensure_ascii=False)); return 1
        a.out.mkdir(parents=True, exist_ok=True)
        write_ass(result, plan, a.out / 'captions.ass', a.font)
        save(a.out / 'captions.json', result)
        write_srt(result, a.out / 'captions.srt')
        result = {'status': 'pass', 'pages': len(result['captions']), 'out': str(a.out)}
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
