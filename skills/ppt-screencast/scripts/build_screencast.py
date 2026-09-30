"""Compile authored page/target/timing data into deterministic screencast camera keys."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from check_screencast_plan import validate, require, number


def compile_plan(author):
    plan = copy.deepcopy(author)
    view = plan['viewport']
    fps = number(plan['fps'], 'fps', positive=True, integer=True)
    transition = max(3, round(fps / 3))
    hold = max(3, round(fps / 4))
    pages = {page['id']: page for page in plan['pages']}
    require(len(pages) == len(plan['pages']), 'duplicate page ID')
    for scene in plan['scenes']:
        require(scene['page_id'] in pages, 'unknown page_id')
        page = pages[scene['page_id']]
        targets = {e['id']: e for e in page['elements']}
        overview = {'cx': page['width'] / 2, 'cy': page['height'] / 2,
                    'scale': min(view['w'] / page['width'], view['h'] / page['height']) * .94}
        if not scene['cues']:
            scene['camera'] = [{'frame': scene['start_frame'], **overview}, {'frame': scene['end_frame'] - 1, **overview}]
            continue
        keys = [{'frame': scene['start_frame'], **overview}]
        previous_end = scene['start_frame'] + hold
        previous_pose = overview
        for cue in scene['cues']:
            require(cue['target_id'] in targets, 'unknown target_id')
            require(cue['start_frame'] - previous_end >= transition, 'cue lacks camera transition time; revise content timing')
            target = targets[cue['target_id']]
            cue.setdefault('padding', 14)
            margin = cue['padding'] + 66
            pose = {'cx': target['x'] + target['w'] / 2, 'cy': target['y'] + target['h'] / 2,
                    'scale': min(view['w'] / (target['w'] + 2 * margin),
                                 view['h'] / (target['h'] + 2 * margin), 1.45)}
            span = cue['end_frame'] - cue['start_frame']
            cue.setdefault('approach_frames', min(10, max(2, span // 5)))
            cue.setdefault('draw_frames', max(2, min(round(fps * .8), span - cue['approach_frames'] - hold)))
            keys.extend([{'frame': cue['start_frame'] - transition, **previous_pose},
                         {'frame': cue['start_frame'], **pose}, {'frame': cue['end_frame'] - 1, **pose}])
            previous_end, previous_pose = cue['end_frame'] - 1, pose
        return_frame = scene['end_frame'] - 1 - hold
        require(return_frame - previous_end >= transition, 'scene lacks return-to-overview transition time')
        keys.extend([{'frame': return_frame, **overview}, {'frame': scene['end_frame'] - 1, **overview}])
        # Repeated identical key frames can occur where a transition begins at a hold boundary.
        scene['camera'] = list({key['frame']: key for key in keys}.values())
    plan.pop('revision', None)
    plan['revision'] = 'screencast-' + hashlib.sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
    validate(plan)
    return plan


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--author', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        require(args.author.resolve() != args.out.resolve(), 'Output must not overwrite authorship')
        plan = compile_plan(json.loads(args.author.read_text('utf-8-sig')))
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'status': 'pass', 'revision': plan['revision'], 'scenes': len(plan['scenes']), 'out': str(args.out)}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'fail', 'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
