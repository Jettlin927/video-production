"""Unified CLI and machine-readable contract for the video-production skill family."""
import argparse
import json
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
TALKING = SKILL.parent / 'talking-head-cut' / 'scripts'
ROUTES = ('talking-head', 'hook-video', 'transcription', 'storyboard',
          'asset', 'existing-edit', 'validation')


def add_path(parser, flag, help_text, required=True, action=None):
    kwargs = {'help': help_text, 'required': required}
    if action:
        kwargs.update(action=action, default=[])
    else:
        kwargs['type'] = Path
    parser.add_argument(flag, **kwargs)


def command(subparsers, name, help_text, script, outputs):
    parser = subparsers.add_parser(name, help=help_text, description=help_text)
    parser.set_defaults(_script=script, _outputs=outputs, _command=name)
    return parser


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version', version='video-production-cli 1')
    sub = parser.add_subparsers(dest='command', required=True)

    p = command(sub, 'prepare', 'Install shared dependencies before production work.',
                HERE / 'prepare_workspace.py', ['video-production-deps/**', 'video-production-deps/tools.json'])
    add_path(p, '--workspace-root', 'Workspace containing raw media, projects and shared dependencies.')
    p.add_argument('--dry-run', action='store_true', help='Print actions without writing or installing.')

    p = command(sub, 'check', 'Check an already prepared workspace; never installs.',
                HERE / 'check_env.py', ['video-production-deps/tools.json'])
    add_path(p, '--workspace-root', 'Prepared video workspace.')
    p.add_argument('--deep', action='store_true', help='Verify bundled font hashes.')
    p.add_argument('--network', action='store_true', help='Check configured API TLS reachability.')
    add_path(p, '--env', 'Optional Skill .env path.', required=False)

    p = command(sub, 'init', 'Create a classified project directory and source manifest.',
                HERE / 'init_project.py', ['projects/<route>/<date>-<name>/**', 'production.json'])
    add_path(p, '--workspace-root', 'Video workspace root.')
    p.add_argument('--route', required=True, choices=ROUTES, help='Production route and project category.')
    p.add_argument('--name', required=True, help='Stable ASCII project slug or title.')
    p.add_argument('--date', help='YYYYMMDD; defaults to today.')
    add_path(p, '--source', 'Source media path; repeatable and recorded without copying.',
             required=False, action='append')

    p = command(sub, 'transcribe', 'Create or resume a cached word-level Bailian transcript.',
                HERE / 'bailian_asr.py', ['<out>/transcript.source.json', '<out>/*.srt', '<out>/*-manifest.json'])
    add_path(p, '--workspace-root', 'Workspace used to resolve shared FFmpeg.')
    add_path(p, '--media', 'Source media file.')
    add_path(p, '--out', 'Transcription output directory.')
    add_path(p, '--env', 'Optional Skill .env path.', required=False)
    p.add_argument('--execute', action='store_true', help='Authorize actual provider submission/resume.')
    p.add_argument('--audio-format', choices=('wav', 'mp3'), default='wav')
    p.add_argument('--no-diarization', action='store_true')
    p.add_argument('--speaker-count', type=int)

    p = command(sub, 'compile', 'Compile arbitrary editorial selections into one validated timeline.',
                TALKING / 'compile_timeline.py', ['edit-plan.json', 'mapped-words.json', 'pause-report.json', 'timeline-check.json'])
    add_path(p, '--selection', 'Content-authored selection-plan.json.')
    add_path(p, '--transcript', 'Word-level transcript JSON.')
    add_path(p, '--decisions', 'Explicit semantic pause decisions JSON.')
    add_path(p, '--out-dir', 'Timeline output directory.')
    p.add_argument('--sample-rate', type=int, default=48000)

    p = command(sub, 'captions', 'Compile semantic caption authorship with exact word coverage.',
                TALKING / 'caption_pages.py', ['<out>.json', '<out>.srt'])
    add_path(p, '--words', 'mapped-words.json from compile.')
    add_path(p, '--editorial', 'Agent-authored caption-editorial.json.')
    add_path(p, '--out', 'Output captions JSON; SRT is written beside it.')

    p = command(sub, 'render', 'Render a validated timeline with shared FFmpeg.',
                TALKING / 'render_timeline.py', ['<out>', '<out-dir>/render.log'])
    add_path(p, '--workspace-root', 'Prepared workspace used to resolve FFmpeg.')
    add_path(p, '--source', 'Original source media.')
    add_path(p, '--plan', 'Validated edit-plan.json.')
    add_path(p, '--out', 'Final MP4 path.')
    add_path(p, '--captions-ass', 'Optional ASS subtitle file.', required=False)
    p.add_argument('--width', type=int, default=1920); p.add_argument('--height', type=int, default=1080)
    p.add_argument('--encoder', choices=('auto', 'libx264', 'h264_nvenc'), default='auto')
    p.add_argument('--preset', default='medium'); p.add_argument('--crf', type=int, default=18)

    p = command(sub, 'qc', 'Run Windows-safe deterministic technical delivery QC.',
                TALKING / 'qc_delivery.py', ['<out>/qc.json'])
    add_path(p, '--workspace-root', 'Prepared workspace used to resolve FFmpeg and ffprobe.')
    add_path(p, '--media', 'Rendered delivery file.')
    add_path(p, '--plan', 'The exact edit-plan.json used for rendering.')
    add_path(p, '--out', 'QC JSON output path.')

    p = sub.add_parser('contract', help='Print the machine-readable CLI contract derived from argparse.')
    p.add_argument('--pretty', action='store_true', help='Indent JSON output.')
    p.set_defaults(_command='contract')
    return parser


def type_name(action):
    if isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
        return 'boolean'
    return {Path: 'path', int: 'integer', float: 'number', str: 'string'}.get(action.type, 'string')


def action_contract(action):
    item = {'flags': list(action.option_strings), 'dest': action.dest, 'type': type_name(action),
            'required': bool(action.required), 'help': action.help or ''}
    if action.default not in (None, argparse.SUPPRESS, [], False):
        item['default'] = action.default
    if action.choices is not None:
        item['choices'] = list(action.choices)
    if isinstance(action, argparse._AppendAction):
        item['repeatable'] = True
    return item


def parser_contract(parser):
    result = {'schema_version': 1, 'program': 'video-production', 'commands': {}}
    sub_action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    for name, child in sub_action.choices.items():
        if name == 'contract':
            continue
        defaults = child._defaults
        result['commands'][name] = {
            'description': child.description or '',
            'arguments': [action_contract(a) for a in child._actions if a.option_strings and a.dest != 'help'],
            'outputs': list(defaults.get('_outputs', [])),
            'runner': str(defaults.get('_script', '')),
        }
    return result


def tools(workspace):
    path = workspace.resolve() / 'video-production-deps' / 'tools.json'
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f'workspace is not prepared; run prepare first ({path}: {exc})') from exc


def forwarded(args):
    command = args._command
    values = vars(args)
    out = []
    skip = {'command', '_command', '_script', '_outputs'}
    for dest, value in values.items():
        if dest in skip or value is None or value is False or value == []:
            continue
        if dest == 'workspace_root':
            if command == 'check':
                flag = '--project-dir'
            elif command in ('prepare', 'init'):
                flag = '--workspace-root'
            else:
                continue
        else:
            flag = '--' + dest.replace('_', '-')
        if value is True:
            out.append(flag)
        elif isinstance(value, list):
            for item in value:
                out += [flag, str(item)]
        else:
            out += [flag, str(value)]
    if command == 'check':
        out += ['--json', '--write-tools']
    if command == 'transcribe':
        out += ['--ffmpeg', tools(args.workspace_root)['ffmpeg']]
    if command == 'render':
        out += ['--ffmpeg', tools(args.workspace_root)['ffmpeg']]
    if command == 'qc':
        resolved = tools(args.workspace_root)
        out += ['--ffmpeg', resolved['ffmpeg'], '--ffprobe', resolved['ffprobe']]
    return out


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args._command == 'contract':
        print(json.dumps(parser_contract(parser), ensure_ascii=False, indent=2 if args.pretty else None))
        return 0
    command_line = [sys.executable, args._script, *forwarded(args)]
    return subprocess.run([str(x) for x in command_line]).returncode


if __name__ == '__main__':
    raise SystemExit(main())
