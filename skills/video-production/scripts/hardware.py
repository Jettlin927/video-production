"""Inventory the local GPU and test FFmpeg encoders; never infer usability from a name."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import time

from managed_job import write


ENCODERS = ('h264_nvenc', 'h264_qsv', 'h264_amf', 'h264_videotoolbox')


def run(args, timeout=20):
    return subprocess.run([str(x) for x in args], capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=timeout,
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)


def inventory():
    if os.name == 'nt':
        result = run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                      'Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion,PNPDeviceID,Status | ConvertTo-Json -Compress'], 15)
        if result.returncode:
            return {'devices': [], 'error': result.stderr[-1000:]}
        devices = json.loads(result.stdout.strip() or '[]')
        return {'devices': devices if isinstance(devices, list) else [devices]}
    if platform.system() == 'Darwin':
        result = run(['system_profiler', 'SPDisplaysDataType', '-json'])
        return {'devices': json.loads(result.stdout).get('SPDisplaysDataType', [])}
    try:
        result = run(['lspci', '-nn'])
        return {'devices': [line for line in result.stdout.splitlines() if re.search('VGA|3D|Display', line)]}
    except FileNotFoundError:
        return {'devices': [], 'error': 'lspci unavailable; encoder tests still determine usability'}


def probe_encoder(ffmpeg, encoder):
    started = time.monotonic()
    try:
        result = run([ffmpeg, '-hide_banner', '-v', 'error', '-f', 'lavfi',
                      '-i', 'color=c=black:s=640x360:r=30:d=0.2', '-vf', 'format=nv12',
                      '-c:v', encoder, '-frames:v', '6', '-f', 'null', '-'])
        return {'usable': result.returncode == 0, 'seconds': round(time.monotonic() - started, 3),
                'detail': result.stderr[-1600:]}
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {'usable': False, 'detail': str(exc)}


def detect(ffmpeg, report_path, refresh=False):
    ffmpeg = Path(ffmpeg).resolve()
    try:
        devices = inventory()
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        devices = {'devices': [], 'error': str(exc)}
    stat = ffmpeg.stat()
    signature = {'system': platform.platform(), 'machine': platform.node(), 'gpu': devices,
                 'ffmpeg': str(ffmpeg), 'size': stat.st_size, 'modified_ns': stat.st_mtime_ns, 'probe_version': 1}
    fingerprint = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
    if report_path and report_path.exists() and not refresh:
        try:
            cached = json.loads(report_path.read_text(encoding='utf-8'))
            if cached['fingerprint'] == fingerprint and time.time() - cached['checked_epoch'] < 86400:
                return {**cached, 'reused': True}
        except (KeyError, ValueError):
            pass
    listing = run([ffmpeg, '-hide_banner', '-encoders'])
    text = listing.stdout + listing.stderr
    tests = {encoder: (probe_encoder(ffmpeg, encoder) if re.search(r'\b' + encoder + r'\b', text)
                       else {'usable': False, 'detail': 'Encoder absent from this FFmpeg build'}) for encoder in ENCODERS}
    tests['libx264'] = probe_encoder(ffmpeg, 'libx264')
    selected = next((e for e in ENCODERS if tests[e]['usable']), 'libx264')
    report = {'schema_version': 1, 'checked_epoch': time.time(), 'fingerprint': fingerprint,
              'hardware': signature, 'encoders': tests, 'selected_encoder': selected,
              'ready': tests[selected]['usable'], 'reused': False,
              'scope': 'Encoding acceleration only; filters and decoding may still use CPU'}
    if report_path:
        write(report_path, report)
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace-root', type=Path, required=True)
    p.add_argument('--report', type=Path)
    p.add_argument('--refresh', action='store_true')
    a = p.parse_args(argv)
    tools_path = a.workspace_root / 'video-production-deps/tools.json'
    tools = json.loads(tools_path.read_text(encoding='utf-8'))
    path = a.report or Path(tools.get('hardware_report') or a.workspace_root / 'video-production-deps/hardware.json')
    report = detect(Path(tools['ffmpeg']), path, a.refresh)
    tools['hardware_report'] = str(path.resolve())
    write(tools_path, tools)
    print(json.dumps({'ready': report['ready'], 'selected_encoder': report['selected_encoder'],
                      'report': str(path), 'hardware': report['hardware']['gpu'], 'encoders': report['encoders']}, ensure_ascii=False))
    return 0 if report['ready'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
