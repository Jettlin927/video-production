"""Bailian image (sync) / video (async) jobs. Standard library only.

Dry run by default. Repeating --execute resumes saved video tasks/downloads;
it never automatically resubmits a failed or uncertain paid request.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, quote
from urllib.request import Request, build_opener, HTTPRedirectHandler
from visual_plan import (generated, styled_prompt, validate_visual_plan, review_context,
                         check_budget, REVIEW_FIELDS)

ROOT = Path(__file__).resolve().parents[1]

# Populated by `check_env.py --install` in compatibility mode. Project runs can point
# this resolver at VIDEO_PRODUCTION_PROJECT_DIR and keep media tools with the project.
INSTALL_DIR = Path.home() / '.agents' / 'skills' / '.tools' / 'bin'


def tool_path(name):
    """Absolute path to a CLI tool this skill shells out to.

    Project-local media tools -> explicit env var -> PATH -> shared install dir -> remembered
    path. When nothing resolves, the bare name is returned so callers keep their previous
    behaviour and fail with the usual OS error.
    """
    exe = '.exe' if os.name == 'nt' else ''
    project_dir = os.environ.get('VIDEO_PRODUCTION_PROJECT_DIR', '').strip()
    if project_dir and name in {'ffmpeg', 'ffprobe'}:
        project_bin = Path(project_dir).resolve() / 'video-production-deps' / 'ffmpeg' / 'bin'
        candidate = project_bin / (name + exe)
        if candidate.is_file():
            return str(candidate)
    value = os.environ.get(name.upper(), '').strip()
    if value and Path(value).is_file():
        return value
    found = shutil.which(name)
    if found:
        return found
    for directory in (INSTALL_DIR, ROOT / '.tools' / 'bin'):
        candidate = Path(directory) / (name + exe)
        if candidate.is_file():
            return str(candidate)
    manifests = []
    if project_dir:
        manifests.append(Path(project_dir).resolve() / 'video-production-deps' / 'tools.json')
    manifests.append(ROOT / 'scripts' / 'tools.json')
    for manifest in manifests:
        try:
            recorded = json.loads(manifest.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        value = str(recorded.get(name) or '').strip()
        if value and Path(value).is_file():
            return value
    return name


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def config(path=ROOT / '.env'):
    values = {}
    if Path(path).exists():
        for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            key, sep, value = line.partition('=')
            if not sep or not re.fullmatch(r'[A-Z][A-Z0-9_]*', key):
                raise ValueError('Invalid .env assignment')
            values[key] = value.strip().strip('\"\'')
    for key in list(values) + ['DASHSCOPE_API_KEY']:
        if key in os.environ:
            values[key] = os.environ[key]
    return values


def api_base(cfg):
    base = cfg.get('DASHSCOPE_BASE_URL', '').rstrip('/')
    u = urlparse(base)
    host = u.hostname or ''
    allowed = host.endswith('.maas.aliyuncs.com') or host in {
        'dashscope.aliyuncs.com', 'dashscope-intl.aliyuncs.com', 'dashscope-us.aliyuncs.com'}
    if not (u.scheme == 'https' and allowed and u.path == '/api/v1') or u.username or u.password or u.query or u.fragment or u.port:
        raise ValueError('Set the official Bailian HTTPS base URL ending in /api/v1')
    return base


def fingerprint(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def request_for(job, cfg, style=None):
    kind = job['kind']
    prompt = styled_prompt(job, style)
    if not prompt:
        raise ValueError('Empty generation prompt')
    custom = job.get('generation', {})
    if kind == 'image':
        if set(custom) - {'prompt_extend'}:
            raise ValueError('Image adapter supports prompt_extend; describe framing in prompt')
        body = {'model': cfg.get('BAILIAN_IMAGE_MODEL', 'qwen-image-3.0'),
                'input': {'messages': [{'role': 'user', 'content': [{'text': prompt}]}]},
                'parameters': {'prompt_extend': custom.get('prompt_extend', True)}}
        return '/services/aigc/multimodal-generation/generation', body, False
    if kind == 'video':
        if set(custom) - {'resolution', 'ratio', 'duration'}:
            raise ValueError('Video adapter supports resolution, ratio, duration')
        params = {'resolution': cfg.get('BAILIAN_VIDEO_RESOLUTION', '480P'),
                  'ratio': cfg.get('BAILIAN_VIDEO_RATIO', 'adaptive'),
                  'duration': int(cfg.get('BAILIAN_VIDEO_DURATION', '5'))}
        params.update(custom)
        if type(params['duration']) is not int or params['duration'] <= 0:
            raise ValueError('Video duration must be a positive integer')
        body = {'model': cfg.get('BAILIAN_VIDEO_MODEL', 'wan3.0-video'),
                'input': {'prompt': prompt}, 'parameters': params}
        return '/services/aigc/video-generation/video-synthesis', body, True
    raise ValueError('kind must be image or video')


def validate_plan(plan):
    validate_visual_plan(plan)
    if not isinstance(plan.get('revision'), str) or not plan['revision']:
        raise ValueError('Plan requires final timeline revision')
    fps = plan['fps']
    if not all(type(fps[k]) is int and fps[k] > 0 for k in ['num', 'den']):
        raise ValueError('Invalid fps')
    total = plan['duration_frames']
    if type(total) is not int or total <= 0:
        raise ValueError('Invalid timeline duration')
    ids = set()
    for j in plan['jobs']:
        if j.get('kind') not in ('image', 'video'):
            raise ValueError('kind must be image or video')
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', j['id']) or j['id'] in ids:
            raise ValueError('Invalid or duplicate asset ID')
        ids.add(j['id'])
        a, b = j['start_frame'], j['end_frame']
        if type(a) is not int or type(b) is not int or not 0 <= a < b <= total:
            raise ValueError('B-roll must stay inside the locked final timeline')
        if j.get('placement') not in ['full', 'inset'] or not j.get('reason'):
            raise ValueError('Each shot needs placement and editorial reason')
        if j['placement'] == 'inset':
            rect = j.get('rect', {})
            if set(rect) != {'x', 'y', 'width', 'height'} or not all(isinstance(v, (int, float)) for v in rect.values()):
                raise ValueError('Inset requires a normalized x/y/width/height rectangle')
            if not (rect['x'] >= 0 and rect['y'] >= 0 and rect['width'] > 0 and rect['height'] > 0 and rect['x'] + rect['width'] <= 1 and rect['y'] + rect['height'] <= 1):
                raise ValueError('Inset rectangle outside canvas')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ApiRejected(RuntimeError):
    pass


class Client:
    def __init__(self, cfg):
        self.base = api_base(cfg)
        self.key = cfg.get('DASHSCOPE_API_KEY', '').strip()
        if not self.key:
            raise ValueError('DASHSCOPE_API_KEY is empty; fill the Skill .env locally')
        self.opener = build_opener(NoRedirect())

    def call(self, method, path, body=None, asynchronous=False, resource_resolve=False):
        headers = {'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json'}
        if asynchronous:
            headers['X-DashScope-Async'] = 'enable'
        if resource_resolve:
            headers['X-DashScope-OssResourceResolve'] = 'enable'
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
        req = Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=120) as res:
                result = json.load(res)
        except HTTPError as e:
            # Deliberately omit server body/URLs/headers, which may contain secrets.
            if 400 <= e.code < 500:
                raise ApiRejected(f'API rejected request (HTTP {e.code})') from None
            raise RuntimeError(f'API outcome uncertain (HTTP {e.code}); do not resubmit') from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise RuntimeError('Network/response error; retain saved task state') from None
        if result.get('code'):
            code = re.sub(r'[^a-zA-Z0-9_.-]', '', str(result['code']))[:80]
            raise ApiRejected('API error code: ' + code)
        return result


def media_urls(result, kind):
    output = result.get('output', {})
    if kind == 'video':
        return [output['video_url']] if output.get('video_url') else []
    return [part['image'] for choice in output.get('choices', [])
            for part in choice.get('message', {}).get('content', []) if part.get('image')]


def download(url, target, kind):
    u = urlparse(url)
    # The provider returns signed OSS URLs. Never send API Authorization to OSS.
    if u.scheme != 'https' or not (u.hostname or '').endswith('.aliyuncs.com') or u.username or u.password:
        raise ValueError('Unexpected media host; inspect provider result without forwarding API credentials')
    target = Path(target)
    part = target.with_suffix(target.suffix + '.part')
    try:
        with build_opener(NoRedirect()).open(Request(url), timeout=120) as res, part.open('wb') as f:
            size = 0
            while chunk := res.read(1024 * 1024):
                size += len(chunk)
                if size > 1024 * 1024 * 1024:
                    raise ValueError('Generated asset exceeds 1 GiB download limit')
                f.write(chunk)
        with part.open('rb') as f:
            head = f.read(16)
        valid = (head.startswith(b'\x89PNG\r\n\x1a\n') or head.startswith(b'\xff\xd8\xff') or (head[:4] == b'RIFF' and head[8:12] == b'WEBP')) if kind == 'image' else head[4:8] == b'ftyp'
        if not valid:
            raise ValueError('Downloaded content is not the expected media format')
        part.replace(target)
    except Exception:
        part.unlink(missing_ok=True)
        raise RuntimeError('Media download failed; saved generation result can be resumed without resubmission') from None


def run(plan, cfg, out, execute=False, client=None, fetch=download, poll_seconds=15, max_polls=40, sleep=time.sleep):
    validate_plan(plan)
    generation_jobs = [j for j in plan['jobs'] if generated(j)]
    base = api_base(cfg) if generation_jobs else None
    requests = {j['id']: request_for(j, cfg, plan.get('visual_style')) for j in generation_jobs}
    # Validate all local inputs before any paid request.
    local_hashes = {j['id']: file_hash(j['path']) for j in plan['jobs'] if not generated(j)}
    if not execute:
        return {'mode': 'dry_run', 'revision': plan['revision'], 'jobs': [
            {'id': j['id'], 'kind': j['kind'], 'endpoint': base + requests[j['id']][0],
             'body': requests[j['id']][1], 'async': requests[j['id']][2]} for j in generation_jobs],
             'local_assets': list(local_hashes)}
    if max_polls < 1 or poll_seconds < 0:
        raise ValueError('Invalid polling bounds')
    client = client or (Client(cfg) if generation_jobs else None)
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    lock = out / '.generation.lock'
    try:
        handle = lock.open('x')
    except FileExistsError:
        raise RuntimeError('Output directory is locked; check whether another generator is running') from None
    try:
        handle.write(str(os.getpid())); handle.close()
        jobs = []
        new_count = 0
        cap = int(cfg.get('BAILIAN_MAX_NEW_JOBS', '6'))
        states = [load(p) for p in out.glob('*.state.json')]
        new_jobs = [j for j in generation_jobs if not (out / (j['id'] + '.state.json')).exists()]
        check_budget(plan, states, new_jobs)
        if len(new_jobs) > cap:
            raise ValueError('New-job limit reached; reduce this batch before submitting')
        # Reject changed requests before submitting earlier jobs in the same batch.
        for job in generation_jobs:
            state_path = out / (job['id'] + '.state.json')
            path, body, _ = requests[job['id']]
            if state_path.exists() and load(state_path)['request_hash'] != fingerprint({'base': base, 'path': path, 'body': body}):
                raise ValueError('Changed generation request under existing asset ID; use a new ID for an intentional new job')
        if generation_jobs and plan.get('schema_version') == 2:
            style_path = out / '.visual-style.json'
            previous_style = load(style_path) if style_path.exists() else None
            current_style = plan['visual_style']
            if previous_style and previous_style != current_style:
                reason = plan.get('style_change_reason')
                if (previous_style['id'] == current_style['id']
                        or not isinstance(reason, str) or not reason.strip()):
                    raise ValueError('Whole-film style is locked across batches; intentional restyle needs a new style ID and style_change_reason')
            save(style_path, current_style)
        for job in plan['jobs']:
            if not generated(job):
                jobs.append({**job, 'path': str(Path(job['path']).resolve()),
                             'sha256': local_hashes[job['id']],
                             'asset_review': 'not_checked', 'muted': True})
                continue
            path, body, asynchronous = requests[job['id']]
            sig = fingerprint({'base': base, 'path': path, 'body': body})
            state_path = out / (job['id'] + '.state.json')
            state = load(state_path) if state_path.exists() else None
            if state and state['request_hash'] != sig:
                raise ValueError('Changed generation request under existing asset ID; use a new ID for an intentional new job')
            if state is None:
                if new_count >= cap:
                    raise ValueError('New-job limit reached; saved tasks are reusable')
                new_count += 1
                state = {'id': job['id'], 'kind': job['kind'], 'request_hash': sig,
                         'status': 'submission_unknown', 'model': body['model']}
                if plan.get('schema_version') == 2:
                    state['cost_reservation'] = {'shot_id': job['shot_id'],
                                                 'amount': job['estimated_cost'],
                                                 'currency': plan['budget']['currency']}
                # Write before POST: a crash after charging must not cause a blind retry.
                save(state_path, state)
                try:
                    response = client.call('POST', path, body, asynchronous)
                except ApiRejected:
                    state['status'] = 'rejected'; save(state_path, state); raise
                state['response'] = response
                task = response.get('output', {}).get('task_id')
                if asynchronous and task:
                    state.update(status='pending', task_id=task)
                elif media_urls(response, job['kind']):
                    state['status'] = 'generated'
                save(state_path, state)
            if state['status'] in ['submission_unknown', 'rejected', 'failed']:
                raise RuntimeError('Saved request failed or outcome uncertain; investigate rather than automatically paying again')
            if state['status'] == 'pending':
                for poll in range(max_polls):
                    result = client.call('GET', '/tasks/' + quote(state['task_id'], safe=''))
                    status = result.get('output', {}).get('task_status')
                    state['response'] = result
                    if status == 'SUCCEEDED':
                        state['status'] = 'generated'
                    elif status in ['FAILED', 'CANCELED', 'UNKNOWN']:
                        state['status'] = 'failed'
                    save(state_path, state)
                    if state['status'] != 'pending':
                        break
                    if poll + 1 < max_polls:
                        sleep(poll_seconds)
                if state['status'] != 'generated':
                    raise RuntimeError('Video incomplete or failed; re-run to poll a pending saved task, never recreate it')
            target = out / (job['id'] + ('.png' if job['kind'] == 'image' else '.mp4'))
            if state['status'] == 'downloaded' and (not target.exists() or file_hash(target) != state['sha256']):
                state['status'] = 'generated'
            if state['status'] == 'generated':
                urls = media_urls(state['response'], job['kind'])
                if len(urls) != 1:
                    raise RuntimeError('Expected one generated asset; inspect saved provider result')
                fetch(urls[0], target, job['kind'])
                state.update(status='downloaded', sha256=file_hash(target))
                save(state_path, state)
            jobs.append({**job, 'path': str(target), 'sha256': state['sha256'],
                         'model': state['model'], 'task_id': state.get('task_id'),
                         'request_hash': sig, 'asset_review': 'not_checked', 'muted': True})
        manifest = {k: plan[k] for k in ['revision', 'fps', 'duration_frames']}
        for key in ('schema_version', 'visual_style', 'style_reference', 'budget'):
            if key in plan:
                manifest[key] = plan[key]
        for job in jobs:
            job['review_context_hash'] = review_context(manifest, job)
            if generated(job) and plan.get('schema_version') == 2:
                job['style_review'] = 'not_checked'
        manifest.update(jobs=jobs, evidence='assets_collected; visual review and media probe pending')
        manifest_path = out / 'media-manifest.json'
        if manifest_path.exists():
            old = {j['id']: j for j in load(manifest_path)['jobs']}
            for j in jobs:
                prev = old.get(j['id'], {})
                if prev.get('review_context_hash') == j['review_context_hash']:
                    for key in REVIEW_FIELDS:
                        if key in prev:
                            j[key] = prev[key]
        save(manifest_path, manifest)
        return {'mode': 'executed', 'manifest': str(manifest_path), 'assets': len(jobs), 'new_jobs': new_count}
    finally:
        handle.close()
        lock.unlink(missing_ok=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--env', type=Path, default=ROOT / '.env')
    p.add_argument('--execute', action='store_true', help='Submit/resume the planned paid jobs')
    p.add_argument('--max-polls', type=int, default=40)
    p.add_argument('--poll-seconds', type=float, default=15)
    a = p.parse_args()
    try:
        result = run(load(a.plan), config(a.env), a.out, a.execute,
                     max_polls=a.max_polls, poll_seconds=a.poll_seconds)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, KeyError, RuntimeError, OSError) as e:
        # Known errors deliberately exclude response bodies and Authorization.
        print(json.dumps({'status': 'error', 'message': str(e)}, ensure_ascii=False))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
