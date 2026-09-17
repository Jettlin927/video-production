"""One-shot first-run bootstrap for the video-production / talking-head-cut skills.

Run this once, the first time the skills land on a machine:

    python scripts/bootstrap.py             # check only; installs nothing, deletes nothing
    python scripts/bootstrap.py --install   # check, then download whatever is missing
    python scripts/bootstrap.py --keep      # check, and keep this file even when ready

Sequence:

1. Run the full dependency check (`check_env.build_report`) and print the summary.
2. If a CLI dependency is missing and `--install` was given, fetch a portable build into
   `~/.agents/skills/.tools/bin`, place the binaries and verify each one actually runs.
3. Record resolved paths in `scripts/tools.json` so later runs need no extra searching.
4. Delete this file once nothing remains that it could fix.

A bare run installs nothing, so it is safe to execute automatically. Items only a human can
supply — the `.env` key, Python version, free disk space — never keep the bootstrap alive,
because re-running it would not resolve them; they are recorded in `tools.json` instead.

Exit code 0 means nothing is left for the bootstrap to fix; 1 means dependencies it could
still install are missing (run again with `--install`, which needs the user's authorization).
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
CHECKER = HERE / 'check_env.py'
TOOLS_JSON = HERE / 'tools.json'

# Which unmet items the bootstrap refuses to keep itself alive for: an installer run would
# never resolve them. Grouped only so the report can say who is expected to fix each one.
HUMAN_ONLY = {'dashscope_key'}                    # needs the user's API key in .env
MANUAL_INSTALL = {'node', 'npm', 'browser'}       # system software; this script does not install it
SELF_CHECKED = {'python', 'fonts', 'skill_files', 'skill_layout', 'disk_space'}  # environment/skill integrity


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--install', action='store_true',
                        help='Download missing CLI tools (needs the current task\'s authorization)')
    parser.add_argument('--install-dir', default=None, help='Where to place downloaded binaries')
    parser.add_argument('--search', action='append', default=[], metavar='DIR',
                        help='Extra root to look for existing tools in (repeatable)')
    parser.add_argument('--keep', action='store_true', help='Do not delete this bootstrap when ready')
    parser.add_argument('--quiet', action='store_true', help='Suppress download progress')
    return parser.parse_args(argv)


def remove_self():
    """Delete this file; fall back to renaming it so it can never run a second time."""
    path = Path(__file__).resolve()
    try:
        path.unlink()
        return True, f'已删除 {path}'
    except OSError as exc:
        try:
            renamed = path.with_suffix('.py.done')
            path.rename(renamed)
            return True, f'无法删除（{exc}），已改名为 {renamed.name} 使其不再运行'
        except OSError as inner:
            return False, f'无法删除或改名（{exc} / {inner}）：请手动删除 {path}'


def record(summary):
    """Merge the bootstrap outcome into tools.json next to the resolved tool paths."""
    data = {}
    if TOOLS_JSON.exists():
        try:
            data = json.loads(TOOLS_JSON.read_text(encoding='utf-8'))
        except ValueError:
            data = {}
    data['bootstrap'] = summary
    TOOLS_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return TOOLS_JSON


def main(argv=None):
    args = parse_args(argv)
    if not CHECKER.exists():
        print(json.dumps({'status': 'error', 'message': f'缺少 {CHECKER}，Skill 目录不完整'},
                         ensure_ascii=False))
        return 1
    sys.path.insert(0, str(HERE))
    import check_env as checker

    print('[bootstrap] video-production 首次初始化')
    print(f'  检查脚本 {CHECKER}')
    forwarded = ['--write-tools']
    for root in args.search:
        forwarded += ['--search', root]
    if args.install:
        forwarded += ['--install']
        if args.install_dir:
            forwarded += ['--install-dir', args.install_dir]
    if args.quiet:
        forwarded += ['--quiet']
    report = checker.build_report(checker.parse_args(forwarded))

    # ---- what was installed just now ----
    installed = {name: result for name, result in report['install'].get('outcome', {}).items()
                 if result.get('ok')}
    failed = {name: result for name, result in report['install'].get('outcome', {}).items()
              if not result.get('ok')}

    print('  已就绪：' + ', '.join(
        f'{name} {entry["version"]}' for name, entry in report['tools'].items() if entry['path']))
    for name, result in installed.items():
        print(f'  本次安装：{name} {result["version"]} -> {result["path"]}')
    for name, result in failed.items():
        print(f'  安装失败：{name} — {result["detail"]}')

    # ---- what only a human or the system package manager can supply ----
    def report_group(label, names):
        for problem in report['problems']:
            if problem['item'] in names:
                print(f'  {label}：{problem["item"]} — {problem["detail"]}')
                if problem['hint']:
                    print(f'{" " * (len(label) + 4)}{problem["hint"]}')

    report_group('需人工处理', HUMAN_ONLY)
    report_group('需自行安装', MANUAL_INSTALL)
    report_group('环境或目录问题', SELF_CHECKED)

    fixable = report['auto_fixable']
    ready = not fixable

    summary = {'ran_at': checker.time.strftime('%Y-%m-%dT%H:%M:%S'),
               'installed': {n: r['path'] for n, r in installed.items()},
               'install_failed': {n: r['detail'] for n, r in failed.items()},
               'needs_human': [p['item'] for p in report['problems'] if p['item'] in HUMAN_ONLY],
               'needs_manual_install': [p['item'] for p in report['problems'] if p['item'] in MANUAL_INSTALL],
               'environment_issues': [p['item'] for p in report['problems'] if p['item'] in SELF_CHECKED],
               'left_fixable': fixable,
               'ready': ready,
               'deleted': None}
    if not ready:
        summary['next'] = 'python scripts/bootstrap.py --install'

    if args.keep:
        summary['deleted'] = 'skipped (--keep)'
    elif ready:
        summary['deleted'] = remove_self()[1]
    else:
        summary['deleted'] = 'kept (dependencies still fixable)'

    tools_path = record(summary)

    # ---- verdict ----
    if ready:
        print(f'  结果：可自动安装的依赖已就绪（记录于 {tools_path.name}）')
        counts = [('需人工处理', HUMAN_ONLY), ('需自行安装', MANUAL_INSTALL), ('环境或目录问题', SELF_CHECKED)]
        outstanding = [f'{label} {sum(1 for p in report["problems"] if p["item"] in names)} 项'
                       for label, names in counts
                       if any(p['item'] in names for p in report['problems'])]
        if outstanding:
            print(f'  仍需注意：{"、".join(outstanding)}（见上；这些不是 bootstrap 能修的）')
        print(f'  {summary["deleted"]}')
        print('  后续复查用 scripts/check_env.py，不要再创建 bootstrap。')
    else:
        print(f'  结果：仍有可由脚本安装的依赖：{", ".join(fixable)}')
        print('  需要用户授权后执行：python scripts/bootstrap.py --install')
        print('  bootstrap 保留，安装成功后会自行删除。')
    return 0 if ready else 1


if __name__ == '__main__':
    raise SystemExit(main())