"""Probe and stage reviewed generated images/videos into a Remotion public folder."""
import argparse
import json
import math
from pathlib import Path
import subprocess
from bailian_media import load, save, file_hash, validate_plan, tool_path
from visual_plan import generated, require_visual_review


def stage(manifest, timeline, public, ffmpeg=None, ffprobe=None, width=1080, height=1920):
    ffmpeg = ffmpeg or tool_path('ffmpeg')
    ffprobe = ffprobe or tool_path('ffprobe')
    validate_plan(manifest)
    for key in ['revision', 'fps', 'duration_frames']:
        if manifest[key] != timeline[key]:
            raise ValueError('Media plan and applied timeline disagree: ' + key)
    ordered = sorted(manifest['jobs'], key=lambda j: j['start_frame'])
    if any(a['end_frame'] > b['start_frame'] for a, b in zip(ordered, ordered[1:])):
        raise ValueError('Overlapping B-roll needs an explicit composition; this adapter accepts one visual at a time')
    public = Path(public).resolve()
    target_dir = public / 'generated'
    fps = manifest['fps']['num'] / manifest['fps']['den']
    rate = f"{manifest['fps']['num']}/{manifest['fps']['den']}"
    assets = []
    for job in ordered:
        require_visual_review(manifest, job)
        if manifest.get('schema_version') == 2 and generated(job):
            reference = manifest['style_reference']
            if file_hash(reference['path']) != reference['sha256']:
                raise ValueError('Style reference image changed; review against the current reference')
        if job.get('asset_review') != 'pass' or not job.get('review_notes'):
            raise ValueError('Inspect actual asset and record asset_review=pass plus review_notes: ' + job['id'])
        source = Path(job['path']).resolve()
        if file_hash(source) != job['sha256']:
            raise ValueError('Source media hash changed')
        data = json.loads(subprocess.run([str(ffprobe), '-v', 'error', '-show_streams', '-show_format',
                                         '-of', 'json', str(source)], check=True, capture_output=True, text=True).stdout)
        stream = next(s for s in data['streams'] if s['codec_type'] == 'video')
        frames = job['end_frame'] - job['start_frame']
        duration = frames / fps
        source_in = job.get('source_in_s', 0)
        if not isinstance(source_in, (float, int)) or not math.isfinite(source_in) or source_in < 0:
            raise ValueError('Invalid B-roll source offset')
        if job['kind'] == 'video':
            available = float(stream.get('duration', data['format'].get('duration', 0)))
            if source_in + duration > available + 1e-4:
                raise ValueError('Generated video too short for placement; shorten placement, never silently loop or freeze')
        rect = job['rect'] if job['placement'] == 'inset' else {'x': 0, 'y': 0, 'width': 1, 'height': 1}
        w = max(2, round(width * rect['width'] / 2) * 2)
        h = max(2, round(height * rect['height'] / 2) * 2)
        ext = '.png' if job['kind'] == 'image' else '.mp4'
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / (job['id'] + ext)
        if source == target:
            raise ValueError('Staging would overwrite downloaded source')
        vf = f'scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1'
        cmd = [str(ffmpeg), '-y', '-v', 'error']
        if job['kind'] == 'video':
            cmd += ['-ss', str(source_in)]
        cmd += ['-i', str(source), '-an']
        if job['kind'] == 'image':
            cmd += ['-vf', vf, '-frames:v', '1', '-update', '1', str(target)]
        else:
            cmd += ['-vf', vf + ',fps=' + rate, '-frames:v', str(frames), '-c:v', 'libx264',
                    '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(target)]
        subprocess.run(cmd, check=True, capture_output=True)
        subprocess.run([str(ffmpeg), '-v', 'error', '-xerror', '-i', str(target), '-f', 'null', '-'],
                       check=True, capture_output=True)
        if job['kind'] == 'video':
            staged = json.loads(subprocess.run([str(ffprobe), '-v', 'error', '-count_frames', '-show_streams',
                                               '-of', 'json', str(target)], check=True, capture_output=True, text=True).stdout)
            vs = next(s for s in staged['streams'] if s['codec_type'] == 'video')
            if int(vs['nb_read_frames']) != frames or any(s['codec_type'] == 'audio' for s in staged['streams']):
                raise ValueError('Staged clip frame count or muted-audio check failed')
        label = 'AI 生成示意' if generated(job) else ('示意图' if job.get('source_type') == 'template' else '')
        assets.append({'id': job['id'], 'kind': job['kind'], 'src': 'generated/' + target.name,
                       'start_frame': job['start_frame'], 'end_frame': job['end_frame'],
                       'rect': rect, 'muted': True, 'label': label,
                       'source_sha256': job['sha256'], 'staged_sha256': file_hash(target),
                       'reason': job['reason'], 'review_notes': job['review_notes'],
                       'source_type': job.get('source_type', 'generated'),
                       'purpose': job.get('purpose'), 'source_word_ids': job.get('source_word_ids'),
                       'source_text': job.get('source_text'), 'visual_goal': job.get('visual_goal'),
                       'claim_scope': job.get('claim_scope'), 'evidence_basis': job.get('evidence_basis'),
                       'style_id': job.get('style_id')})
    result = {k: manifest[k] for k in ['revision', 'fps', 'duration_frames']}
    result['assets'] = assets
    save(public / 'broll.timeline.json', result)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--timeline', type=Path, required=True)
    p.add_argument('--public', type=Path, required=True)
    p.add_argument('--ffmpeg', default=None, help='Defaults to the resolved ffmpeg (see bootstrap.py)')
    p.add_argument('--ffprobe', default=None, help='Defaults to the resolved ffprobe (see bootstrap.py)')
    p.add_argument('--width', type=int, default=1080)
    p.add_argument('--height', type=int, default=1920)
    a = p.parse_args()
    r = stage(load(a.manifest), load(a.timeline), a.public, a.ffmpeg, a.ffprobe, a.width, a.height)
    print(json.dumps({'staged_assets': len(r['assets']), 'timeline': str(a.public / 'broll.timeline.json')}))
