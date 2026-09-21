import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import video_production as cli


class UnifiedCliTests(unittest.TestCase):
    def test_contract_is_derived_from_every_public_parser(self):
        parser = cli.build_parser()
        contract = cli.parser_contract(parser)
        self.assertEqual(set(contract['commands']),
                         {'prepare', 'check', 'init', 'transcribe', 'compile', 'captions', 'render', 'qc',
                          'hardware', 'index', 'select', 'pause-prepare', 'caption-draft', 'caption-build',
                          'export', 'deliver', 'job-status', 'job-stop', 'job-resume'})
        render = contract['commands']['render']
        encoder = next(a for a in render['arguments'] if a['dest'] == 'encoder')
        self.assertEqual(encoder['choices'], ['auto', 'libx264', 'h264_nvenc', 'h264_qsv', 'h264_amf', 'h264_videotoolbox'])
        self.assertEqual(encoder['default'], 'auto')
        self.assertTrue(next(a for a in render['arguments'] if a['dest'] == 'source')['required'])
        self.assertIn('<out-dir>/render.log', render['outputs'])

    def test_contract_json_is_serializable(self):
        text = json.dumps(cli.parser_contract(cli.build_parser()), ensure_ascii=False)
        self.assertEqual(json.loads(text)['schema_version'], 1)

    def test_check_never_forwards_install(self):
        args = cli.build_parser().parse_args(['check', '--workspace-root', '.'])
        forwarded = cli.forwarded(args)
        self.assertEqual(forwarded[:2], ['--project-dir', '.'])
        self.assertIn('--json', forwarded)
        self.assertIn('--write-tools', forwarded)
        self.assertNotIn('--install', forwarded)

    def test_render_resolves_shared_ffmpeg_without_exposing_flag(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            deps = root / 'video-production-deps'; deps.mkdir()
            (deps / 'tools.json').write_text(json.dumps({'ffmpeg': 'shared-ffmpeg'}), encoding='utf-8')
            args = cli.build_parser().parse_args([
                'render', '--workspace-root', str(root), '--source', 'raw.mp4',
                '--plan', 'edit-plan.json', '--out', 'final.mp4'])
            forwarded = cli.forwarded(args)
            self.assertEqual(forwarded[-2:], ['--ffmpeg', 'shared-ffmpeg'])
            self.assertNotIn('--workspace-root', forwarded)

    def test_dispatch_uses_argv_list_not_shell(self):
        with patch('video_production.subprocess.run') as run:
            run.return_value.returncode = 0
            result = cli.main(['init', '--workspace-root', '.', '--route', 'validation',
                               '--name', 'contract-smoke'])
        self.assertEqual(result, 0)
        self.assertIsInstance(run.call_args.args[0], list)


if __name__ == '__main__':
    unittest.main(verbosity=2)
