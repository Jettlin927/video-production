"""Create a small diagnostic video from source frame ranges without full-file decoding."""
import argparse
import json
import subprocess
from pathlib import Path

from bailian_media import tool_path


def parse_ranges(value):
    ranges = []
    for item in value.split(','):
        start, sep, end = item.strip().partition(':')
        if not sep:
            raise ValueError(f'Invalid range {item!r}; use START:END with inclusive frame numbers')
        try:
            start, end = int(start), int(end)
        except ValueError as exc:
            raise ValueError(f'Invalid range {item!r}; frame numbers must be integers') from exc
        if start < 0 or end < start:
            raise ValueError(f'Invalid range {item!r}; require 0 <= START <= END')
        ranges.append((start, end))
    if not ranges:
        raise ValueError('At least one frame range is required')
    return ranges


def parse_rate(value):
    num, sep, den = value.partition('/')
    if not sep or int(den) <= 0:
        raise ValueError(f'Invalid frame rate: {value}')
    return int(num), int(den)


def probe_rate(ffprobe, source):
    result = subprocess.run(
        [str(ffprobe), '-v', 'error', '-select_streams', 'v:0',
         '-show_entries', 'stream=r_frame_rate', '-of', 'default=nw=1:nk=1', str(source)],
        check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
    return parse_rate(result.stdout.strip().splitlines()[0])


def build_command(ffmpeg, source, output, ranges, fps, scale=None, preset='ultrafast', crf=28):
    num, den = fps
    rate = num / den
    command = [str(ffmpeg), '-hide_banner', '-loglevel', 'error', '-y']
    for start, end in ranges:
        # Input seeking limits decoding to a short window around each requested range.
        command += ['-ss', f'{start / rate:.6f}', '-i', str(source)]
    filters = []
    labels = []
    for index, (start, end) in enumerate(ranges):
        label = f'v{index}'
        filters.append(f'[{index}:v]trim=end_frame={end - start + 1},setpts=PTS-STARTPTS{"," + "scale=" + scale if scale else ""}[{label}]')
        labels.append(f'[{label}]')
    filters.append(''.join(labels) + f'concat=n={len(ranges)}:v=1:a=0,setpts=N/({num}/{den}*TB)[vout]')
    command += ['-filter_complex', ';'.join(filters), '-map', '[vout]', '-an',
                '-fps_mode', 'passthrough', '-c:v', 'libx264', '-preset', preset,
                '-crf', str(crf), '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(output)]
    return command


def run(source, output, ranges, ffmpeg=None, ffprobe=None, fps=None, scale=None,
        preset='ultrafast', crf=28):
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_file():
        raise ValueError(f'Input media missing: {source}')
    output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = ffmpeg or tool_path('ffmpeg')
    ffprobe = ffprobe or tool_path('ffprobe')
    fps = parse_rate(fps) if isinstance(fps, str) else (fps or probe_rate(ffprobe, source))
    command = build_command(ffmpeg, source, output, ranges, fps, scale, preset, crf)
    subprocess.run(command, check=True)
    return {
        'source': str(source), 'output': str(output),
        'fps': {'num': fps[0], 'den': fps[1]},
        'ranges': [{'start': start, 'end': end, 'count': end - start + 1}
                   for start, end in ranges],
        'decoded_frames_requested': sum(end - start + 1 for start, end in ranges),
        'seek_mode': 'per-range input seek; no full-file select decode',
        'scale': scale, 'preset': preset, 'crf': crf,
        'command': command,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ranges', required=True, help='Inclusive ranges, e.g. 100:109,200:209')
    parser.add_argument('--fps', help='Source rate as NUM/DEN; omitted uses ffprobe')
    parser.add_argument('--ffmpeg')
    parser.add_argument('--ffprobe')
    parser.add_argument('--scale', help='Optional output scale, e.g. 540:960')
    parser.add_argument('--preset', default='ultrafast')
    parser.add_argument('--crf', type=int, default=28)
    args = parser.parse_args(argv)
    report = run(args.input, args.output, parse_ranges(args.ranges), args.ffmpeg,
                 args.ffprobe, args.fps, args.scale, args.preset, args.crf)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
