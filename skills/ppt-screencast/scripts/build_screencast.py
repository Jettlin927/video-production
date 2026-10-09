"""Compile authored page/target/timing data into deterministic screencast camera keys."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess

from check_screencast_plan import validate, validate_content_sources, require, number


def compile_plan(author):
    plan = copy.deepcopy(author)
    validate_content_sources(plan)
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
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--author', type=Path)
    inputs.add_argument('--content', type=Path)
    for flag in ('script', 'timing', 'audio', 'author-out'):
        parser.add_argument('--' + flag, type=Path)
    parser.add_argument('--ffprobe')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        source = args.author or args.content
        require(source.resolve() != args.out.resolve(), 'Output must not overwrite authorship')
        if args.content:
            from author_screencast import bind_content
            require(all((args.script, args.timing, args.audio, args.ffprobe)), '--content needs --script, --timing, --audio and prepared ffprobe')
            duration = float(subprocess.check_output([args.ffprobe, '-v', 'error', '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1', str(args.audio)], text=True, encoding='utf-8'))
            author = bind_content(json.loads(args.content.read_text('utf-8-sig')), json.loads(args.script.read_text('utf-8-sig')),
                                  json.loads(args.timing.read_text('utf-8-sig')), duration)
            author['narration_audio_sha256'] = hashlib.sha256(args.audio.read_bytes()).hexdigest()
            if args.author_out:
                require(args.author_out.resolve() not in {source.resolve(), args.script.resolve(), args.timing.resolve(), args.out.resolve()}, 'author-out must not overwrite inputs or plan')
                args.author_out.parent.mkdir(parents=True, exist_ok=True)
                args.author_out.write_text(json.dumps(author, ensure_ascii=False, indent=2), encoding='utf-8')
        else:
            author = json.loads(args.author.read_text('utf-8-sig'))
        plan = compile_plan(author)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'status': 'pass', 'revision': plan['revision'], 'scenes': len(plan['scenes']), 'out': str(args.out)}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'fail', 'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
