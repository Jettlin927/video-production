import copy
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import deliver_screencast as delivery
from screencast_review import preview_frames, preview_valid, require_review, review_packet


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads((Path(__file__).resolve().parents[1] / 'assets/demo-plan.json').read_text('utf-8'))
        self.temp = tempfile.TemporaryDirectory(prefix='screencast-review-test-')
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name)
        (self.out / 'preflight').mkdir()
        self.index = {'frames': []}
        for frame in preview_frames(self.plan):
            data = f'offline frame {frame}'.encode()
            file = f'f{frame}.jpg'
            (self.out / 'preflight' / file).write_bytes(data)
            self.index['frames'].append({'frame': frame, 'file': file, 'sha256': hashlib.sha256(data).hexdigest()})
        self.review = review_packet(self.plan, 'snapshot')
        self.review.update(semantic='pass', visual='pass')
        for page in self.review['pages']:
            page.update(status='pass', notes='Offline fixture source and preview compared')

    def test_current_complete_review_and_preview_pass(self):
        self.assertTrue(preview_valid(self.plan, self.index, self.out))
        require_review(self.plan, 'snapshot', self.review, self.index, self.out)

    def test_draft_cannot_authorize_render(self):
        draft = review_packet(self.plan, 'snapshot')
        with self.assertRaisesRegex(ValueError, 'review must pass'):
            require_review(self.plan, 'snapshot', draft, self.index, self.out)

    def test_stale_review_partial_preview_or_changed_picture_block_render(self):
        with self.assertRaisesRegex(ValueError, 'stale'):
            require_review(self.plan, 'new-snapshot', self.review, self.index, self.out)
        partial = copy.deepcopy(self.index); partial['frames'].pop()
        with self.assertRaisesRegex(ValueError, 'preview is missing'):
            require_review(self.plan, 'snapshot', self.review, partial, self.out)
        (self.out / 'preflight' / self.index['frames'][0]['file']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'preview is missing'):
            require_review(self.plan, 'snapshot', self.review, self.index, self.out)

    def test_missing_page_or_unresolved_issue_block_render(self):
        self.review['pages'] = []
        with self.assertRaisesRegex(ValueError, 'every page'):
            require_review(self.plan, 'snapshot', self.review, self.index, self.out)
        self.review = review_packet(self.plan, 'snapshot')
        self.review.update(semantic='pass', visual='pass')
        for page in self.review['pages']:
            page.update(status='pass', notes='Checked')
        self.review['issues'] = [{'level': 'high', 'status': 'open'}]
        with self.assertRaisesRegex(ValueError, 'Unresolved'):
            require_review(self.plan, 'snapshot', self.review, self.index, self.out)

    def test_delivery_without_review_never_launches_renderer(self):
        source, audio, font = [self.out / name for name in ('plan.json', 'audio.wav', 'font.ttf')]
        source.write_text(json.dumps(self.plan), encoding='utf-8')
        audio.write_bytes(b'offline audio'); font.write_bytes(b'offline font')
        modules = self.out / 'modules/remotion'; modules.mkdir(parents=True)
        (modules / 'package.json').write_text('{}', encoding='utf-8')
        deps = self.out / 'video-production-deps'; deps.mkdir()
        tools = {key: key for key in ('ffprobe', 'ffmpeg', 'node', 'browser')}
        tools['node_modules'] = str(modules.parent)
        (deps / 'tools.json').write_text(json.dumps(tools), encoding='utf-8')
        with patch.object(delivery.subprocess, 'check_output', return_value=json.dumps({'streams': [{'codec_type': 'audio'}], 'format': {'duration': '12'}})), \
                patch.object(delivery.subprocess, 'run', side_effect=AssertionError('No render before review')):
            with self.assertRaisesRegex(ValueError, 'before full render'):
                delivery.main(['--workspace-root', str(self.out), '--plan', str(source), '--audio', str(audio),
                               '--font', str(font), '--out-dir', str(self.out / 'output')])

    def test_reviewed_delivery_reuses_preview_and_includes_audio_identity(self):
        source, audio, font = [self.out / name for name in ('plan.json', 'audio.wav', 'font.ttf')]
        source.write_text(json.dumps(self.plan), encoding='utf-8'); audio.write_bytes(b'fixture audio'); font.write_bytes(b'fixture font')
        modules = self.out / 'modules/remotion'; modules.mkdir(parents=True)
        (modules / 'package.json').write_text('{}', encoding='utf-8')
        tools = {key: key for key in ('ffprobe', 'ffmpeg', 'node', 'browser')}
        tools['node_modules'] = str(modules.parent)
        deps = self.out / 'video-production-deps'; deps.mkdir()
        (deps / 'tools.json').write_text(json.dumps(tools), encoding='utf-8')
        runtime = {'tools': tools, 'remotion': delivery.file_hash(modules / 'package.json')}
        output, plan, signature = delivery.snapshot(source, audio, font, self.out / 'output', runtime)
        shutil.copytree(self.out / 'preflight', output / 'preflight')
        (output / 'preflight.json').write_text(json.dumps(self.index), encoding='utf-8')
        self.review['signature'] = signature
        reviewed = self.out / 'review.json'; reviewed.write_text(json.dumps(self.review), encoding='utf-8')
        commands = []
        def execute(command, **kwargs):
            commands.append(command)
            if '--out' in command:
                Path(command[command.index('--out') + 1]).write_text('{"status":"pass"}', encoding='utf-8')
            else:
                Path(command[-2] if command[-1] == '--skip-preview' else command[-1]).write_bytes(b'offline video fixture')
            return subprocess.CompletedProcess(command, 0)
        with patch.object(delivery.subprocess, 'check_output', return_value=json.dumps({'streams': [{'codec_type': 'audio'}], 'format': {'duration': '12'}})), \
                patch.object(delivery.subprocess, 'run', side_effect=execute):
            self.assertEqual(delivery.main(['--workspace-root', str(self.out), '--plan', str(source), '--audio', str(audio),
                '--font', str(font), '--out-dir', str(self.out / 'output'), '--review', str(reviewed)]), 0)
        self.assertEqual(len(commands), 3)
        self.assertIn('--skip-preview', commands[0])
        self.assertIn('--reference-audio', commands[2])


if __name__ == '__main__':
    unittest.main()
