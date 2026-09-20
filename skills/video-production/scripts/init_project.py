"""Create one classified video-production task without copying source media."""
import argparse
import json
import re
from datetime import date
from pathlib import Path


ROUTES = ('talking-head', 'hook-video', 'transcription', 'storyboard',
          'asset', 'existing-edit', 'validation')
SUBDIRS = ('input', 'brief', 'work', 'project', 'output', 'qc')


def slugify(value):
    slug = re.sub(r'[^a-z0-9]+', '-', value.strip().lower()).strip('-')
    if not slug:
        raise ValueError('name must contain an ASCII letter or digit')
    return slug


def source_record(path):
    source = path.resolve()
    if not source.is_file():
        raise FileNotFoundError(f'source file not found: {path}')
    stat = source.stat()
    return {'path': str(source), 'size': stat.st_size,
            'modified_ns': stat.st_mtime_ns}


def create_project(workspace_root, route, name, day=None, sources=()):
    if route not in ROUTES:
        raise ValueError(f'unknown route: {route}')
    workspace = workspace_root.resolve()
    (workspace / 'video-production-deps').mkdir(parents=True, exist_ok=True)
    (workspace / 'scratch').mkdir(parents=True, exist_ok=True)
    project_id = f'{day or date.today().strftime("%Y%m%d")}-{slugify(name)}'
    task = workspace / 'projects' / route / project_id
    if task.exists():
        raise FileExistsError(f'project already exists: {task}')
    for subdir in SUBDIRS:
        (task / subdir).mkdir(parents=True, exist_ok=True)

    manifest = {'sources': [source_record(Path(item)) for item in sources]}
    (task / 'input' / 'source-manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    production = {
        'route': route,
        'project_id': project_id,
        'revision': 1,
        'inputs': str(task / 'input' / 'source-manifest.json'),
        'project_dir': str(task / 'project'),
        'output_dir': str(task / 'output'),
        'qc_dir': str(task / 'qc'),
        'environment': {'tools_json': str(workspace / 'video-production-deps' / 'tools.json')},
    }
    (task / 'production.json').write_text(
        json.dumps(production, ensure_ascii=False, indent=2), encoding='utf-8')
    return task


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace-root', type=Path, required=True)
    parser.add_argument('--route', choices=ROUTES, required=True)
    parser.add_argument('--name', required=True, help='Short ASCII project slug or title')
    parser.add_argument('--date', help='YYYYMMDD; defaults to today')
    parser.add_argument('--source', action='append', default=[], help='Source media path; repeatable')
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.date and not re.fullmatch(r'\d{8}', args.date):
        raise SystemExit('--date must use YYYYMMDD')
    try:
        task = create_project(args.workspace_root, args.route, args.name, args.date, args.source)
    except (ValueError, FileNotFoundError, FileExistsError) as exc:
        raise SystemExit(str(exc)) from exc
    print(task)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
