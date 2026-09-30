import json
from pathlib import Path
import tempfile
import unittest

from deliver_screencast import snapshot


class ScreencastDeliveryTests(unittest.TestCase):
    def test_snapshot_is_mp4_renderer_only_and_plan_is_frozen(self):
        plan = json.loads((Path(__file__).resolve().parents[1] / 'assets/demo-plan.json').read_text('utf-8'))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); author = root / 'input.json'; audio = root / 'audio.wav'; font = root / 'font.ttf'
            author.write_text(json.dumps(plan), encoding='utf-8'); audio.write_bytes(b'audio'); font.write_bytes(b'font')
            out, frozen, signature = snapshot(author, audio, font, root / 'output')
            author.write_text('{}', encoding='utf-8')
            self.assertEqual(json.loads((out / 'project/plan.json').read_text('utf-8')), plan)
            self.assertEqual(frozen, plan)
            self.assertTrue((out / 'project/Screencast.tsx').is_file())
            self.assertEqual(list(out.rglob('*jianying*')), [])
            self.assertFalse((out / '剪映工程').exists())
            self.assertEqual(len(signature), 20)

    def test_audio_change_invalidates_render_snapshot(self):
        plan = (Path(__file__).resolve().parents[1] / 'assets/demo-plan.json').read_text('utf-8')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / 'plan.json'; source.write_text(plan, encoding='utf-8')
            audio = root / 'audio.wav'; audio.write_bytes(b'first'); font = root / 'font.ttf'; font.write_bytes(b'font')
            a = snapshot(source, audio, font, root / 'out')[2]
            audio.write_bytes(b'new')
            self.assertNotEqual(a, snapshot(source, audio, font, root / 'out')[2])


if __name__ == '__main__':
    unittest.main()
