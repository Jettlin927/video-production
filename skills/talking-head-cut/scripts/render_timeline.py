"""Render any validated original-speed edit plan in one FFmpeg graph."""
import argparse
import json
import subprocess
from pathlib import Path

from check_timeline import validate


def run(command):
    return subprocess.run([str(x) for x in command], capture_output=True, text=True,
                          encoding='utf-8', errors='replace')


def encoders(ffmpeg):
    result = run([ffmpeg, '-hide_banner', '-encoders'])
    return result.stdout + result.stderr


def choose_encoder(ffmpeg, requested):
    if requested != 'auto':
        return requested
    return 'h264_nvenc' if 'h264_nvenc' in encoders(ffmpeg) else 'libx264'


def graph(plan, width, height, captions=False):
    count = len(plan['segments'])
    rows = [f'[0:v]split={count}' + ''.join(f'[vs{i}]' for i in range(count)),
            f'[0:a]asplit={count}' + ''.join(f'[as{i}]' for i in range(count))]
    for i, segment in enumerate(plan['segments']):
        a, b = segment['source_in_s'], segment['source_out_s']
        rows += [f'[vs{i}]trim=start={a:.9f}:end={b:.9f},setpts=PTS-STARTPTS,scale={width}:{height}:flags=lanczos[v{i}]',
                 f'[as{i}]atrim=start={a:.9f}:end={b:.9f},asetpts=PTS-STARTPTS[a{i}]']
    inputs = ''.join(f'[v{i}][a{i}]' for i in range(len(plan['segments'])))
    rows.append(f'{inputs}concat=n={len(plan["segments"])}:v=1:a=1[vcat][aout]')
    rows.append('[vcat]ass=captions.ass[vout]' if captions else '[vcat]null[vout]')
    return ';'.join(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--ffmpeg', type=Path, required=True)
    parser.add_argument('--captions-ass', type=Path)
    parser.add_argument('--width', type=int, default=1920); parser.add_argument('--height', type=int, default=1080)
    parser.add_argument('--encoder', choices=('auto', 'libx264', 'h264_nvenc'), default='auto')
    parser.add_argument('--preset', default='medium'); parser.add_argument('--crf', type=int, default=18)
    args = parser.parse_args(argv)
    args.source = args.source.resolve()
    args.plan = args.plan.resolve()
    args.out = args.out.resolve()
    args.ffmpeg = args.ffmpeg.resolve()
    if args.captions_ass:
        args.captions_ass = args.captions_ass.resolve()
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    report = validate(plan)
    if report['status'] != 'pass':
        raise SystemExit('invalid timeline: ' + '; '.join(report['errors']))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    work = args.out.parent / '.render-timeline'
    work.mkdir(exist_ok=True)
    if args.captions_ass:
        (work / 'captions.ass').write_bytes(args.captions_ass.read_bytes())
    encoder = choose_encoder(args.ffmpeg, args.encoder)
    command = [args.ffmpeg, '-v', 'warning', '-nostdin', '-i', args.source,
               '-filter_complex', graph(plan, args.width, args.height, bool(args.captions_ass)),
               '-map', '[vout]', '-map', '[aout]', '-c:v', encoder]
    command += (['-preset', args.preset, '-crf', args.crf] if encoder == 'libx264'
                else ['-preset', 'p5', '-cq', args.crf])
    command += ['-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', '-y', args.out]
    result = subprocess.run([str(x) for x in command], cwd=work, capture_output=True, text=True,
                            encoding='utf-8', errors='replace')
    (args.out.parent / 'render.log').write_text(result.stdout + result.stderr, encoding='utf-8')
    if result.returncode:
        raise SystemExit(f'ffmpeg failed ({result.returncode}); see {args.out.parent / "render.log"}')
    print(json.dumps({'status': 'pass', 'encoder': encoder, 'output': str(args.out)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
