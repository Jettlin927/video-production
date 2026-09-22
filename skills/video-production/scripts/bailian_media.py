"""Shared configuration, HTTP transport and file helpers for transcription."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
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
