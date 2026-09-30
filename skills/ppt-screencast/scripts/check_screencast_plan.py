"""Validate a screencast plan; geometry checks are not semantic or audiovisual QC."""
import argparse
import json
import math
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value, name, positive=False, integer=False):
    require(isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value), f'{name}: expected a finite number')
    require(not positive or value > 0, f'{name}: must be positive')
    require(not integer or isinstance(value, int), f'{name}: expected an integer')
    return value


def interval(item, start, end, name):
    a = number(item['start_frame'], name + '.start_frame', integer=True)
    b = number(item['end_frame'], name + '.end_frame', integer=True)
    require(start <= a < b <= end, f'{name}: interval out of range')
    return a, b


def box(item, name):
    for key in ('x', 'y', 'w', 'h'):
        number(item[key], name + '.' + key, positive=key in ('w', 'h'))


def camera_at(keys, frame):
    if frame <= keys[0]['frame']:
        return keys[0]
    for a, b in zip(keys, keys[1:]):
        if frame <= b['frame']:
            t = (frame - a['frame']) / (b['frame'] - a['frame'])
            t = t * t * (3 - 2 * t)
            return {key: a[key] + (b[key] - a[key]) * t for key in ('cx', 'cy', 'scale')}
    return keys[-1]


def visible(target, camera, viewport, padding=0):
    x = viewport['w'] / 2 + (target['x'] - padding - camera['cx']) * camera['scale']
    y = viewport['h'] / 2 + (target['y'] - padding - camera['cy']) * camera['scale']
    w = (target['w'] + padding * 2) * camera['scale']
    h = (target['h'] + padding * 2) * camera['scale']
    return x >= -0.001 and y >= -0.001 and x + w <= viewport['w'] + 0.001 and y + h <= viewport['h'] + 0.001


def cursor_at(target, cue, frame):
    local = frame - cue['start_frame']
    progress = max(0, min(1, (local - cue['approach_frames']) / cue['draw_frames']))
    pad = cue['padding']
    if cue['kind'] == 'circle':
        angle = -math.pi / 2 + progress * math.pi * 2
        x = target['x'] + target['w'] / 2 + (target['w'] / 2 + pad) * math.cos(angle)
        y = target['y'] + target['h'] / 2 + (target['h'] / 2 + pad) * math.sin(angle)
    else:
        x = (target['x'] - pad + (target['w'] + 2 * pad) * progress
             if cue['kind'] == 'underline' else target['x'] + target['w'] + pad)
        y = target['y'] + target['h'] + pad
    if local < cue['approach_frames']:
        t = local / cue['approach_frames']
        t = t * t * (3 - 2 * t)
        x += (1 - t) * 32
        y -= (1 - t) * 24
    return x, y


def validate(plan):
    require(bool(plan['revision']), 'revision is required')
    for key in ('width', 'height', 'fps', 'duration_frames'):
        number(plan[key], key, positive=True, integer=True)
    view = plan['viewport']
    box(view, 'viewport')
    require(view['x'] >= 0 and view['y'] >= 0 and view['x'] + view['w'] <= plan['width']
            and view['y'] + view['h'] <= plan['height'], 'viewport outside output canvas')
    pages = {}
    for page in plan['pages']:
        require(bool(page['id']) and page['id'] not in pages, 'duplicate or empty page ID')
        for key in ('width', 'height'):
            number(page[key], 'page.' + key, positive=True)
        elements = {}
        for item in page['elements']:
            require(bool(item['id']) and item['id'] not in elements, 'duplicate or empty element ID')
            box(item, item['id'])
            require(item.get('kind', 'text') in ('text', 'chips', 'stat', 'panel', 'flow', 'bullets', 'quote', 'bars', 'rule'),
                    f"{item['id']}: unsupported element kind")
            require(item['x'] >= 0 and item['y'] >= 0 and item['x'] + item['w'] <= page['width']
                    and item['y'] + item['h'] <= page['height'], f"{item['id']}: outside page")
            if 'font_size' in item:
                number(item['font_size'], item['id'] + '.font_size', positive=True)
            elements[item['id']] = item
        pages[page['id']] = elements
    require(pages and plan['scenes'], 'pages and scenes must not be empty')
    next_start = 0
    cue_count = 0
    warnings = []
    for index, scene in enumerate(plan['scenes']):
        name = f'scene[{index}]'
        start, end = interval(scene, 0, plan['duration_frames'], name)
        require(start == next_start, f'{name}: scenes must cover timeline without gaps or overlaps')
        next_start = end
        require(scene['page_id'] in pages, f'{name}: unknown page_id')
        keys = scene['camera']
        require(len(keys) >= 2, f'{name}: need first and last camera keys')
        require(keys[0]['frame'] == start and keys[-1]['frame'] == end - 1,
                f'{name}: camera keys must include scene first and last frames')
        previous = start - 1
        for key in keys:
            frame = number(key['frame'], 'camera.frame', integer=True)
            require(previous < frame < end, f'{name}: camera frames must increase')
            previous = frame
            for field in ('cx', 'cy', 'scale'):
                number(key[field], 'camera.' + field, positive=field == 'scale')
        previous_end = start
        for cue in scene['cues']:
            a, b = interval(cue, start, end, 'cue')
            require(a >= previous_end, f'{name}: cues must be ordered and not overlap')
            previous_end = b
            require(cue['kind'] in ('circle', 'underline', 'point'), 'unknown cue kind')
            require(isinstance(cue.get('reason'), str) and cue['reason'].strip(), 'cue needs a semantic reason')
            require(cue['target_id'] in pages[scene['page_id']], 'unknown target_id')
            approach = number(cue['approach_frames'], 'approach_frames', positive=True, integer=True)
            draw = number(cue['draw_frames'], 'draw_frames', positive=True, integer=True)
            require(approach + draw < b - a, 'cue needs time to approach, draw and hold')
            padding = number(cue['padding'], 'padding')
            require(padding >= 0, 'padding must not be negative')
            target = pages[scene['page_id']][cue['target_id']]
            pose = camera_at(keys, a)
            for frame in range(a, b):
                camera = camera_at(keys, frame)
                require(visible(target, camera, view, padding),
                        f"{name}: {cue['target_id']} or annotation outside viewport at frame {frame}")
                px, py = cursor_at(target, cue, frame)
                sx = view['w'] / 2 + (px - camera['cx']) * camera['scale']
                sy = view['h'] / 2 + (py - camera['cy']) * camera['scale']
                require(0 <= sx and 0 <= sy and sx + 25 <= view['w'] and sy + 32 <= view['h'],
                        f'{name}: cursor outside viewport at frame {frame}')
                require(all(abs(camera[k] - pose[k]) < 0.001 for k in ('cx', 'cy', 'scale')),
                        f'{name}: camera must settle before cue at frame {frame}')
            if target.get('font_size', 999) * pose['scale'] < plan['width'] * 0.025:
                warnings.append(f"{cue['target_id']}: check text readability in rendered frame")
            cue_count += 1
    require(next_start == plan['duration_frames'], 'scenes do not cover final frames')
    require(cue_count > 0, 'screencast needs at least one target-bound emphasis cue')
    previous_end = 0
    for caption in plan.get('captions', []):
        a, b = interval(caption, 0, plan['duration_frames'], 'caption')
        require(a >= previous_end, 'caption intervals overlap or are unordered')
        previous_end = b
        box(caption, 'caption')
        require(caption['x'] >= 0 and caption['y'] >= 0
                and caption['x'] + caption['w'] <= plan['width']
                and caption['y'] + caption['h'] <= plan['height'], 'caption outside output')
        overlap = (caption['x'] < view['x'] + view['w'] and caption['x'] + caption['w'] > view['x']
                   and caption['y'] < view['y'] + view['h'] and caption['y'] + caption['h'] > view['y'])
        require(not overlap, 'caption overlaps content viewport')
    return {'status': 'pass', 'revision': plan['revision'], 'scenes': len(plan['scenes']),
            'cues': cue_count, 'warnings': warnings,
            'semantic_review': 'not_checked', 'audiovisual_review': 'not_checked'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args(argv)
    try:
        result = validate(json.loads(args.plan.read_text(encoding='utf-8-sig')))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {'status': 'fail', 'error': str(exc)}
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding='utf-8')
    print(text)
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
