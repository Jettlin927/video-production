"""Validate source/output timebases before rendering a talking-head edit plan."""
import argparse
import json
import math
from pathlib import Path


def rate(value, name):
    if not isinstance(value, dict) or set(value) != {'num', 'den'}:
        raise ValueError(f'{name} must declare num and den')
    num, den = value['num'], value['den']
    if type(num) is not int or type(den) is not int or num <= 0 or den <= 0:
        raise ValueError(f'{name} must be a positive rational frame rate')
    return num / den


def validate(plan, require_source_frames=True):
    errors = []
    output_fps = rate(plan.get('fps'), 'plan.fps')
    source = plan.get('source') or {}
    source_fps = rate(source.get('fps'), 'plan.source.fps')
    source_duration = source.get('duration_s')
    if type(source_duration) not in (int, float) or not math.isfinite(source_duration) or source_duration <= 0:
        errors.append('source.duration_s must be a positive number')

    segments = plan.get('segments') or []
    if not segments:
        errors.append('plan.segments is empty')

    previous_final_frame = 0
    previous_final_s = 0.0
    for index, segment in enumerate(segments):
        label = segment.get('id', f'#{index}')
        si, so = segment.get('source_in_s'), segment.get('source_out_s')
        fi, fo = segment.get('final_in_s'), segment.get('final_out_s')
        if not all(type(x) in (int, float) and math.isfinite(x) for x in (si, so, fi, fo)):
            errors.append(f'{label}: source/final seconds are not finite numbers')
            continue
        if not si < so or not fi < fo:
            errors.append(f'{label}: interval is empty or reversed')
        if source_duration and (si < 0 or so > source_duration):
            errors.append(f'{label}: source interval is outside source.duration_s')
        if index and abs(fi - previous_final_s) > 1e-6:
            errors.append(f'{label}: final seconds are not continuous')

        expected_fi = round(fi * output_fps)
        expected_fo = round(fo * output_fps)
        if 'final_in_frame' in segment and segment['final_in_frame'] != expected_fi:
            errors.append(f'{label}: final_in_frame does not match final_in_s and plan.fps')
        if 'final_out_frame' in segment and segment['final_out_frame'] != expected_fo:
            errors.append(f'{label}: final_out_frame does not match final_out_s and plan.fps')
        if index and 'final_in_frame' in segment and segment['final_in_frame'] != previous_final_frame:
            errors.append(f'{label}: final frame intervals are not continuous')

        expected_si = round(si * source_fps)
        expected_so = round(so * source_fps)
        if require_source_frames and ('source_in_frame' not in segment or 'source_out_frame' not in segment):
            errors.append(f'{label}: source frame bounds are required before rendering')
        if 'source_in_frame' in segment and segment['source_in_frame'] != expected_si:
            errors.append(f'{label}: source_in_frame does not match source_in_s and source.fps')
        if 'source_out_frame' in segment and segment['source_out_frame'] != expected_so:
            errors.append(f'{label}: source_out_frame does not match source_out_s and source.fps')
        if 'source_frame_count' in segment and segment['source_frame_count'] != expected_so - expected_si:
            errors.append(f'{label}: source_frame_count is inconsistent with source frame bounds')

        previous_final_frame = expected_fo
        previous_final_s = fo

    duration_s = plan.get('duration_s')
    if type(duration_s) not in (int, float) or not math.isfinite(duration_s) or duration_s <= 0:
        errors.append('plan.duration_s must be a positive number')
    elif type(plan.get('duration_frames')) is int:
        expected_duration = round(duration_s * output_fps)
        if plan['duration_frames'] != expected_duration:
            errors.append('plan.duration_frames does not match plan.duration_s and plan.fps')
    return {
        'status': 'pass' if not errors else 'fail',
        'source_fps': source_fps,
        'output_fps': output_fps,
        'segments': len(segments),
        'errors': errors,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--allow-missing-source-frames', action='store_true',
                        help='Allow candidate plans before source frame bounds are materialized')
    args = parser.parse_args(argv)
    report = validate(json.loads(args.plan.read_text(encoding='utf-8')),
                      require_source_frames=not args.allow_missing_source_frames)
    if args.out:
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
