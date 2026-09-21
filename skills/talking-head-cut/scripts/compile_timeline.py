"""Compile content-authored selections and pause decisions into one validated timeline."""
import argparse
import json
import hashlib
from pathlib import Path

from check_timeline import validate
from map_words import remap
from semantic_pacing import apply


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def compile_timeline(selection, transcript, decisions, sample_rate=48000):
    selected = transcript if transcript['revision'] == selection['revision'] else remap(transcript, selection)
    plan, pause_report = apply(selection, selected, decisions, sample_rate)
    revision_input = json.dumps([selection, transcript, decisions, sample_rate], sort_keys=True, ensure_ascii=False)
    plan['revision'] = 'cut-' + hashlib.sha256(revision_input.encode()).hexdigest()[:20]
    report = validate(plan)
    if report['status'] != 'pass':
        raise ValueError('Compiled timeline is invalid: ' + '; '.join(report['errors']))
    mapped = remap(transcript, plan)
    return plan, mapped, pause_report, report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection', type=Path, required=True,
                        help='Content-authored selection-plan.json; arbitrary duration and segment count')
    parser.add_argument('--transcript', type=Path, required=True, help='Word-level source transcript JSON')
    parser.add_argument('--decisions', type=Path, required=True, help='Explicit semantic pause decisions JSON')
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--sample-rate', type=int, default=48000)
    args = parser.parse_args(argv)
    result = compile_timeline(load(args.selection), load(args.transcript), load(args.decisions), args.sample_rate)
    for name, value in zip(('edit-plan.json', 'mapped-words.json', 'pause-report.json', 'timeline-check.json'), result):
        save(args.out_dir / name, value)
    print(json.dumps({'status': 'pass', 'revision': result[0]['revision'],
                      'segments': len(result[0]['segments']), 'words': len(result[1]['words'])}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
