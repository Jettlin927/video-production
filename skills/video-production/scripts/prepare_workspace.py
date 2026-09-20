"""Prepare shared video dependencies before any production task starts."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


REMOTION = '4.0.525'


def run(command, cwd=None):
    subprocess.run([str(x) for x in command], cwd=cwd, check=True)


def package_manifest():
    return {'name': 'video-production-shared-runtime', 'private': True, 'version': '1.0.0',
            'dependencies': {'@remotion/bundler': REMOTION, '@remotion/cli': REMOTION,
                             '@remotion/fonts': REMOTION, '@remotion/renderer': REMOTION,
                             'react': '18.3.1', 'react-dom': '18.3.1',
                             'remotion': REMOTION, 'typescript': '5.4.5'}}


def commands(workspace, skill_root, python=sys.executable):
    deps = workspace / 'video-production-deps'
    venv_python = deps / 'venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    npm = 'npm.cmd' if os.name == 'nt' else 'npm'
    return [
        [python, '-m', 'venv', deps / 'venv'],
        [venv_python, '-m', 'pip', 'install', '-r', skill_root / 'scripts' / 'requirements-jianying.txt'],
        [npm, 'install', '--ignore-scripts', '--cache', deps / 'npm-cache'],
        [venv_python, skill_root / 'scripts' / 'check_env.py', '--project-dir', workspace,
         '--install', '--write-tools'],
        [venv_python, skill_root / 'scripts' / 'check_env.py', '--project-dir', workspace,
         '--deep', '--json', '--write-tools'],
    ]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace-root', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    workspace = args.workspace_root.resolve()
    skill_root = Path(__file__).resolve().parent.parent
    node = workspace / 'video-production-deps' / 'node'
    plan = commands(workspace, skill_root)
    if args.dry_run:
        print(json.dumps([[str(x) for x in command] for command in plan], ensure_ascii=False, indent=2))
        return 0
    node.mkdir(parents=True, exist_ok=True)
    (workspace / 'video-production-deps' / 'requirements.txt').write_text(
        (skill_root / 'scripts' / 'requirements-jianying.txt').read_text(encoding='utf-8'), encoding='utf-8')
    (node / 'package.json').write_text(json.dumps(package_manifest(), indent=2), encoding='utf-8')
    run(plan[0]); run(plan[1]); run(plan[2], node); run(plan[3]); run(plan[4])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
