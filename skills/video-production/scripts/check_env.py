"""Environment doctor for the video-production skill family.

Inventories every external dependency the skills rely on, resolves the tools that are
allowed to live outside PATH, validates the shared .env and the bundled fonts, and reports
which routes are actually usable on this machine. Standard library only, so it can run
before anything else has been installed. Sibling skills found next to this one
(talking-head-cut, hook-video) are covered by the script/link checks too.

    python scripts/check_env.py                       # human-readable report
    python scripts/check_env.py --json                # machine-readable
    python scripts/check_env.py --deep                # also hash every bundled font
    python scripts/check_env.py --network             # also test TLS reachability of the API host
    python scripts/check_env.py --search D:\\tools     # extra roots to look for ffmpeg/ffprobe in
    python scripts/check_env.py --write-tools         # record resolved paths in tools.json

Exit code is 0 when every required dependency is present, 1 otherwise. Warnings never fail
the run; they mark evidence the skill asks for that this machine cannot produce yet.
"""
import argparse
import json
import os
import platform
import shutil
import socket
import ssl
import stat
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIBLING = ROOT.parent / 'talking-head-cut'
HOOK_SIBLING = ROOT.parent / 'hook-video'
# Optional sibling skills: checked for scripts/links when present, never required.
EXTRA_SIBLINGS = [p for p in (HOOK_SIBLING,) if p.exists()]
MIN_PYTHON = (3, 8)
RECOMMENDED_PYTHON = (3, 10)

# Where --install places portable binaries: shared by every skill, outside any one package,
# so a downloaded 80 MB ffmpeg is not duplicated into each skill copy that gets shared.
INSTALL_DIR = Path.home() / '.agents' / 'skills' / '.tools' / 'bin'

# Directories that commonly hold ffmpeg/Chrome without ever editing PATH.
TOOL_DIRS = [
    INSTALL_DIR,
    ROOT / '.tools' / 'bin',
    ROOT.parent / '.tools' / 'bin',
    Path('C:/ffmpeg/bin'),
    Path('C:/Program Files/ffmpeg/bin'),
    Path('C:/ProgramData/chocolatey/bin'),
    Path.home() / 'scoop' / 'shims',
    Path(os.environ.get('LOCALAPPDATA', '')) / 'Microsoft' / 'WinGet' / 'Links',
    Path('/usr/local/bin'),
    Path('/opt/homebrew/bin'),
]
BROWSER_PATHS = [
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
]
BROWSER_ENV = ['REMOTION_BROWSER_EXECUTABLE', 'PUPPETEER_EXECUTABLE_PATH', 'CHROME_PATH']
EXE = '.exe' if os.name == 'nt' else ''
SEARCH_DEPTH = 6
TOOLS_JSON = ROOT / 'scripts' / 'tools.json'


def recorded_tools():
    """Paths remembered by a previous --write-tools run, so a second run needs no --search."""
    try:
        return json.loads(TOOLS_JSON.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def find_tool(name, extra_roots=(), env_vars=(), names=None, recorded=None):
    """Explicit env var -> PATH -> canonical tool dirs -> remembered path -> bounded search.

    Canonical directories (including the shared install dir) deliberately outrank a
    remembered path, so a proper install supersedes an earlier stopgap location. `names`
    lists the executable spellings to try in order; Windows npm/npx are `.cmd` shims rather
    than real executables, so they must be preferred over the `.ps1` wrapper.
    """
    candidates = names or (['%s.cmd' % name, '%s.exe' % name, name] if os.name == 'nt' else [name])
    for var in list(env_vars) + [name.upper()]:
        value = os.environ.get(var, '').strip()
        if value and Path(value).is_file():
            return str(Path(value)), f'环境变量 {var}'
    for candidate in candidates:
        which = shutil.which(candidate)
        if which:
            return which, 'PATH'
    for directory in TOOL_DIRS:
        for candidate in candidates:
            path = Path(directory) / candidate
            if path.is_file():
                return str(path), f'常见安装目录 {directory}'
    value = str((recorded or {}).get(name) or '').strip()
    if value and Path(value).is_file():
        return value, f'上次记录 {TOOLS_JSON.name}'
    for root in extra_roots:
        root = Path(root)
        if not root.is_dir():
            continue
        base_depth = len(root.parts)
        for current, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__'}]
            if len(Path(current).parts) - base_depth >= SEARCH_DEPTH:
                dirs[:] = []
                continue
            for candidate in candidates:
                if candidate in files:
                    return str(Path(current) / candidate), f'搜索目录 {root}'
    return None, None


def run_version(path, args, timeout=20):
    """A short version string from the tool's own banner, or a marker when it cannot run."""
    import re
    import subprocess
    if Path(path).suffix.lower() == '.ps1':
        return '<PowerShell 包装脚本，未探测版本>'
    try:
        result = subprocess.run([path] + args, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=timeout)
        text = ((result.stdout or '') + (result.stderr or '')).strip()
    except Exception as exc:                     # noqa: BLE001 - any failure is just "no version"
        return f'<{type(exc).__name__}>'
    if not text:
        return '<无输出>'
    first = text.splitlines()[0]
    # "ffmpeg version 7.1-full_build" -> 7.1 ; nightly builds report a git id instead,
    # e.g. "ffmpeg version N-126574-g912208af28-20260916", which is the version.
    if 'version ' in first:
        token = first.split('version ', 1)[1].split(' ', 1)[0].strip()
        numeric = re.match(r'\d+(?:\.\d+)*', token)
        return (numeric.group(0) if numeric else token)[:40] or first[:40]
    found = re.search(r'\d+\.\d+(?:\.\d+)?', first)
    return found.group(0) if found else first[:40]


def install_commands():
    """System package-manager one-liners, for users who prefer a machine-wide install."""
    if sys.platform == 'win32':
        return ['winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements',
                'choco install ffmpeg -y',
                'scoop install ffmpeg']
    if sys.platform == 'darwin':
        return ['brew install ffmpeg']
    return ['sudo apt install -y ffmpeg', 'sudo dnf install -y ffmpeg', 'sudo pacman -S ffmpeg']


def archives():
    """Static builds for a machine that has nothing but Python, best source first.

    Each entry provides ffmpeg and/or ffprobe; every source is tried in order until all
    requested binaries are on disk. Only fixed, well-known URLs are used.
    """
    machine = platform.machine().lower()
    arm = machine in ('arm64', 'aarch64')
    table = {
        'win32': [
            {'url': 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-'
                    + ('winarm64' if arm else 'win64') + '-gpl.zip',
             'kind': 'zip', 'provides': ['ffmpeg', 'ffprobe'], 'label': 'BtbN FFmpeg-Builds (GPL)'},
            {'url': 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip',
             'kind': 'zip', 'provides': ['ffmpeg', 'ffprobe'], 'label': 'gyan.dev release-essentials'},
        ],
        'linux': [
            {'url': 'https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-'
                    + ('arm64' if arm else 'amd64') + '-static.tar.xz',
             'kind': 'tarxz', 'provides': ['ffmpeg', 'ffprobe'], 'label': 'johnvansickle static'},
        ],
        'darwin': [
            {'url': 'https://evermeet.cx/ffmpeg/getrelease/zip',
             'kind': 'zip', 'provides': ['ffmpeg'], 'label': 'evermeet.cx ffmpeg'},
            {'url': 'https://evermeet.cx/ffprobe/getrelease/zip',
             'kind': 'zip', 'provides': ['ffprobe'], 'label': 'evermeet.cx ffprobe'},
        ],
    }
    return table.get(sys.platform, [])


def download_file(url, dest, budget=900, quiet=False):
    """Stream a URL to disk with a coarse progress report. Standard library only."""
    from urllib.request import Request, urlopen
    started = time.time()
    request = Request(url, headers={'User-Agent': 'video-production-check_env'})
    with urlopen(request, timeout=90) as response, open(dest, 'wb') as handle:
        total = int(response.headers.get('Content-Length') or 0)
        seen, mark = 0, 0
        while True:
            chunk = response.read(262144)
            if not chunk:
                break
            handle.write(chunk)
            seen += len(chunk)
            if not quiet and (seen - mark >= 25 * 1024 * 1024 or (total and seen >= total)):
                mark = seen
                percent = f' {seen * 100 // total}%' if total else ''
                print(f'    {seen / 1048576:.0f} MB{percent}', flush=True)
            if time.time() - started > budget:
                raise TimeoutError('下载超出时间预算')
    return dest.stat().st_size


def extract_archive(archive, dest, kind):
    import tarfile
    import zipfile
    dest.mkdir(parents=True, exist_ok=True)
    if kind == 'zip':
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(dest)
    else:
        with tarfile.open(archive) as bundle:
            bundle.extractall(dest)          # fixed URLs above; not an untrusted user archive
    return dest


def find_binary(root, name):
    """Locate a binary anywhere in an extracted tree, preferring a real `bin/` layout."""
    hits = []
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for candidate in {name + EXE, name}:
            if candidate in files:
                hits.append(Path(current) / candidate)
    hits.sort(key=lambda path: (path.parent.name != 'bin', len(path.parts)))
    return hits[0] if hits else None


def install_tools(names, dest_dir, quiet=False):
    """Download the archives that provide `names`, place the binaries, verify each one runs."""
    results, pending = {}, list(names)
    for source in archives():
        if not pending:
            break
        offered = [name for name in pending if name in source['provides']]
        if not offered:
            continue
        if not quiet:
            print(f'  来源 {source["label"]}', flush=True)
            print(f'    {source["url"]}', flush=True)
        with tempfile.TemporaryDirectory() as workspace:
            workspace = Path(workspace)
            archive = workspace / ('bundle.zip' if source['kind'] == 'zip' else 'bundle.tar.xz')
            try:
                size = download_file(source['url'], archive, quiet=quiet)
                if not quiet:
                    print(f'    下载完成 {size / 1048576:.0f} MB，解包…', flush=True)
                extract_archive(archive, workspace / 'x', source['kind'])
            except Exception as exc:                 # noqa: BLE001 - report and try the next source
                for name in offered:
                    results[name] = {'ok': False, 'detail': f'{source["label"]} 失败：{type(exc).__name__}: {exc}'}
                continue
            for name in list(offered):
                found = find_binary(workspace / 'x', name)
                if not found:
                    results[name] = {'ok': False, 'detail': f'{source["label"]} 内没有 {name}'}
                    continue
                dest_dir.mkdir(parents=True, exist_ok=True)
                target = dest_dir / (name + EXE)
                shutil.copy2(found, target)
                if os.name != 'nt':
                    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                version = run_version(str(target), ['-version'])
                results[name] = {'ok': True, 'path': str(target), 'source': source['label'], 'version': version}
                pending.remove(name)
                if not quiet:
                    print(f'    已放置 {target}（{version}）', flush=True)
    for name in pending:
        results[name] = {'ok': False, 'detail': '所有来源都失败或未提供该工具'}
    return results


def skill_links(skill_md):
    """Relative markdown links inside a SKILL.md, as (target, exists)."""
    import re
    text = skill_md.read_text(encoding='utf-8')
    out = []
    for target in re.findall(r'\]\(([^)#\s]+)\)', text):
        if target.startswith(('http://', 'https://', 'mailto:')):
            continue
        out.append((target, (skill_md.parent / target).exists()))
    return out


def parse_scripts(directory):
    """Every skill script must at least compile on this interpreter."""
    bad = []
    for path in sorted(Path(directory).glob('*.py')):
        try:
            compile(path.read_text(encoding='utf-8'), str(path), 'exec')
        except SyntaxError as exc:
            bad.append(f'{path.name}:{exc.lineno}: {exc.msg}')
    return bad


def check_fonts(deep=False):
    import hashlib
    manifest = ROOT / 'assets' / 'fonts' / 'manifest.json'
    if not manifest.exists():
        return {'present': False, 'reason': 'assets/fonts/manifest.json 缺失', 'files': [], 'missing': ['manifest.json']}
    doc = json.loads(manifest.read_text(encoding='utf-8'))
    missing, bad_size, bad_hash, ok = [], [], [], 0
    for entry in doc['files']:
        path = ROOT / 'assets' / 'fonts' / entry['path']
        if not path.is_file():
            missing.append(entry['path'])
            continue
        if path.stat().st_size != entry['bytes']:
            bad_size.append(entry['path'])
            continue
        if deep:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != entry['sha256']:
                bad_hash.append(entry['path'])
                continue
        ok += 1
    return {'present': True, 'checked': len(doc['files']), 'ok': ok,
            'missing': missing, 'size_mismatch': bad_size, 'hash_mismatch': bad_hash,
            'families': sorted({e['family'] for e in doc['files']})}


def check_env(env_path):
    """Load .env through the same code path the skill scripts use, then validate its shape."""
    sys.path.insert(0, str(ROOT / 'scripts'))
    import bailian_media
    result = {'path': str(env_path), 'present': env_path.exists(), 'keys': [], 'problems': []}
    if not result['present']:
        result['problems'].append('缺少 .env；复制 .env.example 后填入业务空间 Key')
        return result
    cfg = bailian_media.config(env_path)
    result['keys'] = sorted(k for k in cfg if k.startswith(('DASHSCOPE', 'BAILIAN')))
    if not cfg.get('DASHSCOPE_API_KEY', '').strip():
        result['problems'].append('DASHSCOPE_API_KEY 为空：转写与生成素材路线不可用')
    if not cfg.get('DASHSCOPE_BASE_URL', '').strip():
        result['problems'].append('DASHSCOPE_BASE_URL 为空：无法定位业务空间')
    else:
        try:
            bailian_media.api_base(cfg)
        except ValueError as exc:
            result['problems'].append(f'DASHSCOPE_BASE_URL 不合法（{exc}）')
        result['base_url'] = cfg['DASHSCOPE_BASE_URL']
    result['asr_model'] = cfg.get('BAILIAN_ASR_MODEL', '')
    return result


def check_network(host, timeout=8):
    started = time.time()
    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=timeout) as raw:
            with context.wrap_socket(raw, server_hostname=host) as tls:
                return {'host': host, 'reachable': True, 'tls': tls.version(),
                        'ms': round((time.time() - started) * 1000)}
    except Exception as exc:                     # noqa: BLE001
        return {'host': host, 'reachable': False, 'error': f'{type(exc).__name__}: {exc}',
                'ms': round((time.time() - started) * 1000)}


def disk_report(path):
    try:
        usage = shutil.disk_usage(path)
        return {'path': str(path), 'free_gb': round(usage.free / 1024 ** 3, 1),
                'total_gb': round(usage.total / 1024 ** 3, 1),
                'ok': usage.free > 20 * 1024 ** 3}
    except OSError as exc:
        return {'path': str(path), 'error': str(exc), 'ok': False}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--json', action='store_true', help='Machine-readable output')
    parser.add_argument('--deep', action='store_true', help='Also verify every bundled font by SHA256')
    parser.add_argument('--network', action='store_true', help='Also test TLS reachability of the API host')
    parser.add_argument('--search', action='append', default=[], metavar='DIR',
                        help='Extra root to search for ffmpeg/ffprobe (repeatable)')
    parser.add_argument('--output-dir', default=os.getcwd(), help='Where media will be written')
    parser.add_argument('--env', type=Path, default=ROOT / '.env')
    parser.add_argument('--write-tools', action='store_true',
                        help='Record resolved tool paths in scripts/tools.json for later runs')
    parser.add_argument('--quiet', action='store_true', help='Only print problems')
    parser.add_argument('--install', nargs='*', metavar='TOOL', default=None,
                        help='Download and place missing CLI tools (bare --install = every missing one). '
                             'Never runs implicitly: installing needs the current task\'s authorization.')
    parser.add_argument('--install-dir', type=Path, default=INSTALL_DIR,
                        help=f'Where --install places binaries (default: {INSTALL_DIR})')
    parser.add_argument('--print-install-commands', action='store_true',
                        help='Only print system package-manager commands; install nothing')
    return parser.parse_args(argv)


def build_report(args):
    """Collect the whole picture without printing, so bootstrap and probes can reuse it.

    Side effect: --write-tools (and any --install) writes scripts/tools.json.
    """
    report = {'skill_root': str(ROOT), 'sibling_root': str(SIBLING), 'os': platform.platform(),
              'required': {}, 'recommended': {}, 'optional': {}, 'routes': {},
              'problems': [], 'warnings': [], 'install': {'requested': False}}

    def record(bucket, name, ok, detail, hint=''):
        report[bucket][name] = {'ok': bool(ok), 'detail': detail, 'hint': hint}
        if not ok:
            (report['problems'] if bucket == 'required' else report['warnings']).append(
                {'item': name, 'detail': detail, 'hint': hint})

    # ---- python ----
    py = platform.python_version()
    py_ok = sys.version_info[:2] >= MIN_PYTHON
    record('required', 'python', py_ok, f'{py} ({sys.executable})',
           f'需要 >= {".".join(map(str, MIN_PYTHON))}；推荐 >= {".".join(map(str, RECOMMENDED_PYTHON))}')
    if py_ok and sys.version_info[:2] < RECOMMENDED_PYTHON:
        report['warnings'].append({'item': 'python', 'detail': f'{py} 低于推荐版本',
                                   'hint': f'推荐 {".".join(map(str, RECOMMENDED_PYTHON))}+'})

    # ---- skill layout ----
    bad = parse_scripts(ROOT / 'scripts') + (parse_scripts(SIBLING / 'scripts') if SIBLING.exists() else [])
    for extra in EXTRA_SIBLINGS:
        bad += parse_scripts(extra / 'scripts')
    count = 2 + len(EXTRA_SIBLINGS)
    record('required', 'skill_layout', SIBLING.exists() and not bad,
           (f'{count} 个 Skill 相邻，脚本全部可编译' if not bad else f'脚本语法错误 {bad}'),
           'video-production 与 talking-head-cut 必须放在同一级技能目录；hook-video 在场时一并检查')
    links = skill_links(ROOT / 'SKILL.md') + (skill_links(SIBLING / 'SKILL.md') if SIBLING.exists() else [])
    for extra in EXTRA_SIBLINGS:
        links += skill_links(extra / 'SKILL.md')
    broken = [t for t, exists in links if not exists]
    record('required', 'skill_files', not broken,
           f'SKILL.md 相对链接 {len(links)} 条，缺失 {len(broken)}',
           '缺失: ' + ', '.join(broken) if broken else '')

    # ---- fonts ----
    fonts = check_fonts(deep=args.deep)
    fonts_ok = fonts['present'] and not fonts['missing'] and not fonts['size_mismatch'] and not fonts['hash_mismatch']
    record('required', 'fonts', fonts_ok,
           f'{fonts.get("ok", 0)}/{fonts.get("checked", 0)} 个文件通过'
           + ('（含 SHA256）' if args.deep else '（仅大小；--deep 可校验 SHA256）'),
           f'缺失 {fonts["missing"]} 大小异常 {fonts["size_mismatch"]} 哈希异常 {fonts["hash_mismatch"]}')
    report['font_families'] = fonts.get('families', [])

    # ---- external binaries ----
    remembered = recorded_tools()
    ffmpeg, ffmpeg_src = find_tool('ffmpeg', args.search, recorded=remembered)
    ffprobe, ffprobe_src = find_tool('ffprobe', args.search, recorded=remembered)
    node, node_src = find_tool('node', args.search, recorded=remembered)
    npm, npm_src = find_tool('npm', args.search, recorded=remembered)
    resolved = {}
    for name, path, source, version_args in [
            ('ffmpeg', ffmpeg, ffmpeg_src, ['-version']),
            ('ffprobe', ffprobe, ffprobe_src, ['-version']),
            ('node', node, node_src, ['--version']),
            ('npm', npm, npm_src, ['--version'])]:
        if path:
            resolved[name] = {'path': path, 'source': source,
                              'version': run_version(path, version_args)}
        else:
            resolved[name] = {'path': None, 'source': None, 'version': None}
    report['tools'] = resolved

    # ---- optional install: explicit opt-in, never triggered by a plain check ----
    if args.install is not None:
        wanted = list(args.install) or [n for n in ('ffmpeg', 'ffprobe') if not resolved[n]['path']]
        if wanted:
            if not args.quiet:
                print(f'安装 {", ".join(wanted)} -> {args.install_dir}', flush=True)
            outcome = install_tools(wanted, args.install_dir, quiet=args.quiet)
            report['install'] = {'requested': True, 'dir': str(args.install_dir), 'outcome': outcome}
            for name, result in outcome.items():
                if result.get('ok'):
                    resolved[name] = {'path': result['path'], 'source': '本次安装',
                                      'version': result['version']}
            ffmpeg, ffprobe = resolved['ffmpeg']['path'], resolved['ffprobe']['path']
            ffmpeg_src = resolved['ffmpeg']['source']
            ffprobe_src = resolved['ffprobe']['source']
            args.write_tools = True                    # remember what was just placed
        else:
            report['install'] = {'requested': True, 'dir': str(args.install_dir), 'outcome': {},
                                 'note': '所需命令行工具均已存在，无需安装'}
            if not args.quiet:
                print('所需命令行工具均已存在，无需安装。', flush=True)

    ffmpeg_hint = ('把 ffmpeg 放进 PATH，或用 --ffmpeg "<解析到的路径>" 调用脚本'
                   if not ffmpeg else f'脚本调用时带上 --ffmpeg "{ffmpeg}"（若不在 PATH）')
    record('required', 'ffmpeg', bool(ffmpeg),
           f'{resolved["ffmpeg"]["version"]} @ {ffmpeg}（{ffmpeg_src}）' if ffmpeg else '未找到',
           ffmpeg_hint)
    record('recommended', 'ffprobe', bool(ffprobe),
           f'{resolved["ffprobe"]["version"]} @ {ffprobe}（{ffprobe_src}）' if ffprobe else '未找到',
           'prepare_broll.py 需要 ffprobe 探测生成素材；ffmpeg 通常自带')
    record('required', 'node', bool(node),
           f'{resolved["node"]["version"]} @ {node}（{node_src}）' if node else '未找到',
           'Remotion 路线需要 Node.js；建议 LTS >= 18')
    record('required', 'npm', bool(npm),
           f'{resolved["npm"]["version"]} @ {npm}（{npm_src}）' if npm else '未找到',
           '安装 Remotion 工程依赖需要 npm/npx')

    # ---- browser ----
    browser, browser_src = None, None
    for var in BROWSER_ENV:
        value = os.environ.get(var, '').strip()
        if value and Path(value).is_file():
            browser, browser_src = value, f'环境变量 {var}'
            break
    if not browser:
        for candidate in BROWSER_PATHS:
            if Path(candidate).is_file():
                browser, browser_src = candidate, '常见安装位置'
                break
    if not browser:
        for name in ['google-chrome', 'chromium', 'chrome', 'msedge']:
            found = shutil.which(name)
            if found:
                browser, browser_src = found, 'PATH'
                break
    record('required', 'browser', bool(browser),
           f'{browser}（{browser_src}）' if browser else '未找到 Chrome/Chromium',
           'Remotion 渲染需要一个浏览器可执行文件；可用 REMOTION_BROWSER_EXECUTABLE 指定')

    # ---- .env ----
    env_info = check_env(args.env)
    key_ok = env_info['present'] and not env_info['problems']
    record('required', 'dashscope_key', key_ok,
           (f'已配置 {len(env_info["keys"])} 项：{", ".join(env_info["keys"])}' if key_ok
            else (env_info['problems'][0] if env_info['problems'] else '未配置')),
           '从 .env.example 创建 .env 并填写业务空间 Key；'
           '缺少 Key 时本地剪辑仍可完成，但转写与生成素材路线不可用')
    report['env'] = env_info

    # ---- numpy ----
    try:
        import numpy
        numpy_info = f'numpy {numpy.__version__}'
        numpy_ok = True
    except ImportError:
        numpy_info, numpy_ok = '未安装', False
    record('recommended', 'numpy', numpy_ok, numpy_info,
           'speech_checks.py 的波形同步质检需要 numpy：python -m pip install numpy')

    # ---- disk ----
    disk = disk_report(args.output_dir)
    record('recommended', 'disk_space', disk.get('ok'),
           f'{disk.get("free_gb")} GB 可用 / {disk.get("total_gb")} GB（{disk["path"]}）',
           '视频工作区需要数十 GB：源片 + 切片 + 渲染中间文件；注意渲染器还会占用系统临时目录')
    report['disk'] = disk

    # ---- network (opt-in) ----
    if args.network:
        host = ''
        base = env_info.get('base_url', '')
        if base:
            from urllib.parse import urlparse
            host = urlparse(base).hostname or ''
        report['network'] = check_network(host) if host else {'reachable': None, 'error': '没有可用的 BASE_URL'}
        if host and not report['network']['reachable']:
            report['warnings'].append({'item': 'network', 'detail': f'{host} 不可达',
                                       'hint': '转写与生成素材需要访问业务空间；本地剪辑不需要'})
    else:
        report['network'] = {'checked': False, 'hint': '加 --network 可测试业务空间连通性'}

    # ---- route readiness ----
    def ok(name):
        """An item counts as satisfied only if it was recorded and passed, in any bucket."""
        for bucket in ('required', 'recommended', 'optional'):
            if name in report[bucket]:
                return report[bucket][name]['ok']
        return True

    def ready(*items):
        return all(ok(k) for k in items)
    report['routes'] = {
        '字幕/转写（百炼 ASR）': ready('python', 'ffmpeg', 'dashscope_key', 'skill_files'),
        '口播本地脚本（选内容/气口/字幕）': ready('python', 'skill_files', 'skill_layout'),
        '波形同步质检': ready('python', 'numpy'),
        '剪片与渲染（Remotion）': ready('ffmpeg', 'node', 'npm', 'browser'),
        '钩子视频（纯排版动画）': HOOK_SIBLING.exists() and ready('node', 'npm', 'browser', 'skill_files'),
        '生成素材（B-roll）': ready('ffprobe', 'ffmpeg', 'dashscope_key'),
    }

    # What bootstrap could still fix by itself. Human-only items (.env key, disk, Python
    # version) are deliberately excluded: re-running an installer would never resolve them.
    report['auto_fixable'] = [
        name for name in ('ffmpeg', 'ffprobe')
        if not (report['required'].get(name) or report['recommended'].get(name) or {'ok': True})['ok']
        and any(name in source['provides'] for source in archives())
    ]

    if args.write_tools or (args.install and any(
            r.get('ok') for r in report['install'].get('outcome', {}).values())):
        target = TOOLS_JSON
        target.write_text(json.dumps({
            'checked_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'platform': platform.platform(),
            'python': sys.executable,
            'ffmpeg': ffmpeg, 'ffprobe': ffprobe, 'node': node, 'npm': npm, 'browser': browser,
        }, ensure_ascii=False, indent=2), encoding='utf-8')
        report['tools_json'] = str(target)

    return report


def render_report(report, args):
    """Print a report built by build_report(); returns the process exit code."""
    problems, warnings = report['problems'], report['warnings']
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.quiet:
        if problems:
            print('\n'.join(f'{p["item"]}: {p["detail"]}  ({p["hint"]})' for p in problems))
        else:
            print('所有必需依赖就绪。')
    else:
        mark = {True: 'OK  ', False: 'MISS'}
        lines = [f'video-production 环境检查  |  {platform.platform()}',
                 f'skill: {ROOT}',
                 f'sibling: {SIBLING}  ({"" if SIBLING.exists() else "缺失"})',
                 f'hook-video: {HOOK_SIBLING}  ({"" if HOOK_SIBLING.exists() else "缺失（可选）"})', '']
        for bucket, label in [('required', '必需'), ('recommended', '建议'), ('optional', '可选')]:
            entries = report[bucket]
            if not entries:
                continue
            lines.append(f'[{label}]')
            for name, item in entries.items():
                lines.append(f'  {mark[item["ok"]]} {name:<14} {item["detail"]}')
                if not item['ok'] and item['hint']:
                    lines.append(f'       -> {item["hint"]}')
            lines.append('')
        lines.append('[路线可用性]')
        for name, ok in report['routes'].items():
            lines.append(f'  {mark[ok]} {name}')
        lines.append('')
        disk = report['disk']
        lines.append(f'[磁盘] {disk.get("free_gb")} GB 可用（{disk["path"]}）')
        if report['network'].get('reachable') is not None:
            net = report['network']
            lines.append(f'[网络] {net.get("host")} ' +
                         (f'可达 {net.get("ms")}ms {net.get("tls")}' if net.get('reachable')
                          else f'不可达 {net.get("error")}'))
        if problems:
            lines += ['', f'阻塞项 {len(problems)} 个：'] + \
                     [f'  - {p["item"]}: {p["detail"]}  ({p["hint"]})' for p in problems]
        else:
            lines += ['', '所有必需依赖就绪。']
        if report['auto_fixable']:
            lines += [f'可由脚本自动安装：{", ".join(report["auto_fixable"])}',
                      f'  python {Path(__file__).name} --install']
        if warnings:
            lines += [f'提醒 {len(warnings)} 项：'] + \
                     [f'  - {w["item"]}: {w["detail"]}  ({w["hint"]})' for w in warnings]
        path = (report['tools'].get('ffmpeg') or {}).get('path')
        if path and not shutil.which('ffmpeg'):
            lines += ['', f'ffmpeg 不在 PATH；调用脚本时显式传入：--ffmpeg "{path}"']
        print('\n'.join(lines))

    return 0 if not problems else 1


def main(argv=None):
    args = parse_args(argv)
    if args.print_install_commands:
        print('\n'.join(install_commands()))
        return 0
    return render_report(build_report(args), args)


if __name__ == '__main__':
    raise SystemExit(main())