"""Shared Bailian voice enrollment: local reference, durable identity, no automatic retries."""
import argparse
import base64
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile
import wave

from bailian_media import ApiRejected, Client, ROOT, api_base, config, file_hash, fingerprint, load, save
from managed_job import lock

ENDPOINT = '/services/audio/tts/customization'
ENROLL_MODEL = 'qwen-voice-enrollment'
CLONE_MODEL = 'qwen3-tts-vc-2026-01-22'
MAX_BYTES = 10 * 1024 * 1024


def provider_scope(cfg):
    return fingerprint({'base': api_base(cfg)})


def load_voice_record(path, cfg):
    record = load(path)
    if record.get('schema_version') != 1 or record.get('status') != 'ready':
        raise ValueError('Voice record is not ready; inspect enrollment state before synthesis')
    if record.get('model') != CLONE_MODEL:
        raise ValueError('Unsupported voice target model; use the maintained non-realtime VC adapter')
    if not re.fullmatch(r'qwen-tts-vc-[a-zA-Z0-9_-]+', record.get('voice', '')):
        raise ValueError('Invalid cloned voice identity')
    if record.get('provider_scope') != provider_scope(cfg):
        raise ValueError('Voice belongs to a different API endpoint; use its original region/workspace')
    return record


def prepare_reference(audio, target, ffmpeg, start_s, sample_seconds):
    result = subprocess.run([ffmpeg, '-hide_banner', '-v', 'error', '-nostdin', '-y',
                             '-ss', str(start_s), '-i', str(audio), '-t', str(sample_seconds),
                             '-vn', '-ar', '24000', '-ac', '1', '-c:a', 'pcm_s16le', str(target)],
                            capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode:
        raise RuntimeError('Cannot prepare reference audio; source remains unchanged')
    from bailian_tts import wav_frames
    duration = wav_frames(target) / 24000
    if not 3 <= duration <= 60 or target.stat().st_size > MAX_BYTES:
        raise ValueError('Reference must contain 3-60 seconds of audio, at most 10 MiB')
    return {'duration_s': duration, 'sample_sha256': file_hash(target)}


def create_voice(audio, out, cfg, execute=False, consent=False, ffmpeg=None,
                 preferred_name='video', start_s=0, sample_seconds=15, client=None):
    if not audio.is_file():
        raise ValueError('Provide an existing local reference audio/video file')
    if audio.resolve() in (out.resolve(), out.with_suffix('.state.json').resolve()):
        raise ValueError('Voice outputs must not overwrite the reference')
    if not re.fullmatch(r'[a-zA-Z0-9_]{1,16}', preferred_name):
        raise ValueError('preferred_name must be 1-16 ASCII letters, numbers or underscores')
    if not math.isfinite(start_s) or start_s < 0 or not math.isfinite(sample_seconds) or not 3 <= sample_seconds <= 60:
        raise ValueError('start_s must be nonnegative; sample_seconds must be 3-60')
    # Direct Python calls and argparse floats must identify the same paid enrollment.
    start_s = int(start_s) if start_s == int(start_s) else start_s
    sample_seconds = int(sample_seconds) if sample_seconds == int(sample_seconds) else sample_seconds
    if out.suffix.lower() != '.json' or out.name.endswith('.state.json'):
        raise ValueError('Use a separate .json voice record, not a .state.json path')
    scope = provider_scope(cfg) if cfg.get('DASHSCOPE_BASE_URL') else None
    intent = {'source_sha256': file_hash(audio), 'start_s': start_s, 'sample_seconds': sample_seconds,
              'model': CLONE_MODEL, 'preferred_name': preferred_name, 'provider_scope': scope}
    signature = fingerprint(intent)
    plan = {'signature': signature, **intent, 'record': str(out),
            'key_configured': bool(cfg.get('DASHSCOPE_API_KEY', '').strip())}
    if not execute:
        return {'mode': 'dry_run', **plan}
    if not consent:
        raise ValueError('Confirm own/authorized/synthetic reference audio with --consent')
    if not ffmpeg:
        raise ValueError('Prepared workspace FFmpeg is required')
    client = client or Client(cfg)
    scope = provider_scope(cfg)
    with lock(out.parent / ('.' + out.stem + '-lock')):
        state_path = out.with_suffix('.state.json')
        if out.is_file():
            record = load_voice_record(out, cfg)
            if record.get('signature') != signature:
                raise ValueError('Existing voice record has different inputs; do not overwrite it')
            return {**record, 'record': str(out), 'reused': True}
        state = load(state_path) if state_path.is_file() else {}
        if state:
            if state.get('signature') != signature:
                raise ValueError('Saved enrollment has different inputs; preserve its outcome')
            if state.get('status') == 'ready':
                save(out, state['record'])
                return {**load_voice_record(out, cfg), 'record': str(out), 'reused': True}
            raise RuntimeError('Prior enrollment unresolved or rejected; inspect saved state and voice-list, do not recreate blindly')
        with tempfile.TemporaryDirectory(prefix='voice-reference-', dir=out.parent) as temp:
            sample = Path(temp) / 'reference.wav'
            metadata = prepare_reference(audio, sample, ffmpeg, start_s, sample_seconds)
            body = {'model': ENROLL_MODEL, 'input': {'action': 'create', 'target_model': CLONE_MODEL,
                    'preferred_name': preferred_name,
                    'audio': {'data': 'data:audio/wav;base64,' + base64.b64encode(sample.read_bytes()).decode('ascii')}}}
            state = {'signature': signature, 'status': 'submitting', **intent, **metadata, 'consent_confirmed': True}
            save(state_path, state)
            try:
                response = client.call('POST', ENDPOINT, body)
            except ApiRejected as exc:
                save(state_path, {**state, 'status': 'rejected', 'error': str(exc)})
                raise RuntimeError(f'Voice creation rejected: {exc}; retain state and fix configuration') from None
            except Exception:
                save(state_path, {**state, 'status': 'uncertain'})
                raise RuntimeError('Voice creation outcome uncertain; query voice-list before any authorized retry') from None
            output = response.get('output', {})
            voice = output.get('voice')
            valid = isinstance(voice, str) and bool(re.fullmatch(r'qwen-tts-vc-[a-zA-Z0-9_-]+', voice))
            ready = valid and not output.get('fallback_mode', False) and output.get('target_model', CLONE_MODEL) == CLONE_MODEL
            record = {'schema_version': 1, **intent, **metadata, 'signature': signature,
                      'status': 'ready' if ready else 'review_required', 'voice': voice,
                      'consent_confirmed': True, 'request_id': response.get('request_id'),
                      'usage': response.get('usage', {}), 'fallback_mode': output.get('fallback_mode', False)}
            # Persist the server-created identity before local delivery. Never save base64 or signed URLs.
            save(state_path, {**state, 'status': record['status'], 'record': record})
            save(out, record)
            if not ready:
                raise RuntimeError('Enrollment returned a degraded/invalid identity; keep record for review, do not auto-create another')
            return {**record, 'record': str(out), 'reused': False}


def list_voices(cfg, execute=False, page_index=0, page_size=20, client=None):
    if page_index < 0 or not 1 <= page_size <= 100:
        raise ValueError('page_index must be nonnegative; page_size must be 1-100')
    body = {'model': ENROLL_MODEL, 'input': {'action': 'list', 'page_index': page_index, 'page_size': page_size}}
    if not execute:
        return {'mode': 'dry_run', 'request': body}
    response = (client or Client(cfg)).call('POST', ENDPOINT, body)
    return {'request_id': response.get('request_id'), 'page_index': page_index,
            'page_size': page_size, 'output': response.get('output', {})}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    create = sub.add_parser('create')
    create.add_argument('--audio', type=Path, required=True)
    create.add_argument('--out', type=Path, required=True)
    create.add_argument('--preferred-name', default='video')
    create.add_argument('--start-s', type=float, default=0)
    create.add_argument('--sample-seconds', type=float, default=15)
    create.add_argument('--consent', action='store_true')
    create.add_argument('--ffmpeg')
    listing = sub.add_parser('list')
    listing.add_argument('--page-index', type=int, default=0)
    listing.add_argument('--page-size', type=int, default=20)
    for command in (create, listing):
        command.add_argument('--env', type=Path, default=ROOT / '.env')
        command.add_argument('--execute', action='store_true')
    args = parser.parse_args(argv)
    try:
        cfg = config(args.env)
        result = (create_voice(args.audio, args.out, cfg, args.execute, args.consent, args.ffmpeg,
                               args.preferred_name, args.start_s, args.sample_seconds)
                  if args.action == 'create' else list_voices(cfg, args.execute, args.page_index, args.page_size))
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, wave.Error) as exc:
        print(json.dumps({'status': 'fail', 'error': str(exc) if isinstance(exc, (ValueError, RuntimeError))
                          else 'Local voice record/audio I/O failed'}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
