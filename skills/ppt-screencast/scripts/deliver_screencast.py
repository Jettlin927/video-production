"""MP4-only screencast delivery from one frozen plan; no Jianying dependency or conversion."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

from check_screencast_plan import validate
from screencast_review import preview_valid, review_packet, require_review

SKILL = Path(__file__).resolve().parents[1]
PUBLIC = SKILL.parent / 'video-production' / 'scripts'
sys.path.insert(0, str(PUBLIC))
from managed_job import read, write, lock

FONT = SKILL.parent / 'video-production/assets/fonts/notosanssc/NotoSansSC[wght].ttf'


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def snapshot(plan_path, audio, font, out_dir, runtime=None):
    plan_bytes = Path(plan_path).read_bytes()
    plan = json.loads(plan_bytes.decode('utf-8-sig'))
    check = validate(plan)
    assets = SKILL / 'assets/remotion'
    names = ('Screencast.tsx', 'CameraStage.tsx', 'motion.mjs', 'render-screencast.mjs')
    inputs = {'plan': hashlib.sha256(plan_bytes).hexdigest(), 'audio': file_hash(audio), 'audio_extension': audio.suffix,
              'font': file_hash(font), 'runtime': runtime,
              'code': {n: file_hash(assets / n) for n in names}, 'worker': file_hash(__file__),
              'plan_checker': file_hash(SKILL / 'scripts/check_screencast_plan.py'),
              'review_checker': file_hash(SKILL / 'scripts/screencast_review.py'),
              'qc_checker': file_hash(SKILL.parent / 'talking-head-cut/scripts/qc_delivery.py')}
    inputs['audio_checker'] = file_hash(PUBLIC / 'audio_identity.py')
    signature = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()[:20]
    out = out_dir.resolve() / signature
    project = out / 'project'; public = project / 'public'
    public.mkdir(parents=True, exist_ok=True)
    write(project / 'plan.json', plan)
    write(project / 'inputs.json', inputs)
    write(out / 'plan-check.json', check)
    for name in names:
        shutil.copy2(assets / name, project / name)
    shutil.copy2(font, public / 'font.ttf')
    if (font.parent / 'OFL.txt').is_file():
        shutil.copy2(font.parent / 'OFL.txt', public / 'OFL.txt')
    shutil.copy2(audio, public / ('narration' + audio.suffix))
    if file_hash(public / ('narration' + audio.suffix)) != inputs['audio'] or file_hash(public / 'font.ttf') != inputs['font']:
        raise ValueError('Audio/font changed during snapshot; retry from stable inputs')
    return out, plan, signature


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('workspace-root', 'plan', 'audio', 'out-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--font', type=Path, default=FONT)
    parser.add_argument('--preview-only', action='store_true')
    parser.add_argument('--frames', help='Optional comma-separated frames for partial preview; cannot approve full delivery')
    parser.add_argument('--review', type=Path)
    args = parser.parse_args(argv)
    tools = read(args.workspace_root / 'video-production-deps/tools.json')
    meta = json.loads(subprocess.check_output([tools['ffprobe'], '-v', 'error', '-show_streams', '-show_format',
        '-of', 'json', str(args.audio)], text=True, encoding='utf-8'))
    if not any(s['codec_type'] == 'audio' for s in meta['streams']):
        raise ValueError('Narration input has no audio stream')
    audio_duration = float(meta['format']['duration'])
    runtime = {'tools': {k: tools[k] for k in ('node', 'browser', 'ffmpeg', 'ffprobe', 'node_modules')},
               'remotion': file_hash(Path(tools['node_modules']) / 'remotion/package.json')}
    with lock(args.out_dir / '.screencast-lock'):
        out, plan, signature = snapshot(args.plan, args.audio, args.font, args.out_dir, runtime)
        if plan.get('narration_audio_sha256') and file_hash(args.audio) != plan['narration_audio_sha256']:
            raise ValueError('Narration audio changed after timing binding; rebuild the plan')
        duration = plan['duration_frames'] / plan['fps']
        if abs(audio_duration - duration) > 1 / plan['fps'] + .001:
            raise ValueError('Narration duration differs from plan; rebuild timing instead of trimming speech')
        state_file = out / 'delivery.json'
        state = read(state_file) if state_file.is_file() else {'signature': signature, 'revision': plan['revision'], 'stages': {}}
        project = out / 'project'
        def stage(name, command, products):
            entry = state['stages'].get(name)
            if entry and all(p.is_file() and file_hash(p) == entry['hashes'].get(p.name) for p in products):
                return
            state.update(state='running', stage=name)
            write(state_file, state)
            started = time.time()
            with (out / (name + '.log')).open('wb') as log:
                result = subprocess.run([str(c) for c in command], stdout=log, stderr=log)
            if result.returncode:
                state.update(state='failed', stage=name, exit_code=result.returncode)
                write(state_file, state)
                raise RuntimeError(f'{name} failed; see {out / (name + ".log")}')
            state['stages'][name] = {'seconds': time.time() - started, 'hashes': {p.name: file_hash(p) for p in products}}
            write(state_file, state)
        renderer = [tools['node'], project / 'render-screencast.mjs', args.workspace_root / 'video-production-deps/tools.json',
                    project / 'Screencast.tsx', out / 'video.mp4']
        preview_index = out / 'preflight.json'
        if args.preview_only:
            if not (preview_index.is_file() and preview_valid(plan, read(preview_index), out)):
                state['stages'].pop('preview', None)
                command = [*renderer, '--preview-only']
                if args.frames:
                    command.append('--frames=' + args.frames)
                stage('preview', command, [preview_index])
            draft = out / 'review-draft.json'
            if not draft.is_file():
                write(draft, review_packet(plan, signature))
            complete = preview_valid(plan, read(preview_index), out)
            ready = 'preview_ready' if complete else 'partial_preview_ready'
            state.update(state=ready, stage='review', review=str(draft))
            write(state_file, state)
            print(json.dumps({'state': ready, 'signature': signature, 'revision': plan['revision'],
                              'review_draft': str(draft), 'preview_index': str(preview_index)}, ensure_ascii=False))
            return 0
        if args.frames:
            raise ValueError('--frames is for preview only')
        if not args.review or not preview_index.is_file():
            raise ValueError('Run screencast-preview and review this snapshot before full render')
        require_review(plan, signature, read(args.review), read(preview_index), out)
        stage('render', [*renderer, '--skip-preview'], [out / 'video.mp4'])
        stage('mux', [tools['ffmpeg'], '-v', 'error', '-nostdin', '-i', out / 'video.mp4', '-i', project / ('public/narration' + args.audio.suffix),
            '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-af', 'apad',
            '-t', str(duration), '-movflags', '+faststart', '-y', out / 'final.mp4'], [out / 'final.mp4'])
        qc_plan = {'revision': plan['revision'], 'fps': {'num': plan['fps'], 'den': 1}, 'width': plan['width'],
                   'height': plan['height'], 'duration_frames': plan['duration_frames'], 'duration_s': duration}
        write(project / 'qc-plan.json', qc_plan)
        stage('qc', [sys.executable, SKILL.parent / 'talking-head-cut/scripts/qc_delivery.py', '--media', out / 'final.mp4',
            '--plan', project / 'qc-plan.json', '--out', out / 'qc.json', '--ffmpeg', tools['ffmpeg'], '--ffprobe', tools['ffprobe'],
            '--reference-audio', project / ('public/narration' + args.audio.suffix)], [out / 'qc.json'])
        state.update(state='completed', stage='done', export_format='mp4', overall='technical_ready',
                     pre_render_review='pass',
                     visual_review='not_checked', listening='not_checked', outputs={'mp4': str(out / 'final.mp4'), 'qc': str(out / 'qc.json')})
        write(state_file, state)
        handoff = {'revision': plan['revision'], 'signature': signature, 'state': 'completed', 'overall': 'technical_ready',
                   'pre_render_review': 'pass', 'export_format': 'mp4', 'outputs': state['outputs'],
                   'remaining': ['成片连续动作抽查', '完整听审']}
        write(args.out_dir / 'handoff.json', handoff)
        production = args.out_dir.parent / 'production.json'
        if production.is_file():
            record = read(production)
            record.update(export_format='mp4', timeline_revision=plan['revision'], outputs={**state['outputs'], 'revision': plan['revision']})
            write(production, record)
        print(json.dumps(handoff, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
