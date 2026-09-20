import json
from pathlib import Path
import tempfile
import unittest

from init_project import SUBDIRS, create_project


class InitProjectTests(unittest.TestCase):
    def test_classifies_project_and_references_source_without_copying(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'raw video.mp4'
            source.write_bytes(b'raw')
            task = create_project(root, 'talking-head', 'Client Demo', '20260920', [source])
            self.assertEqual(task, root / 'projects' / 'talking-head' / '20260920-client-demo')
            self.assertTrue(all((task / name).is_dir() for name in SUBDIRS))
            self.assertTrue((root / 'video-production-deps').is_dir())
            self.assertTrue((root / 'scratch').is_dir())
            manifest = json.loads((task / 'input' / 'source-manifest.json').read_text('utf-8'))
            self.assertEqual(manifest['sources'][0]['path'], str(source.resolve()))
            self.assertEqual(source.read_bytes(), b'raw')
            self.assertEqual(list((task / 'input').glob('*.mp4')), [])

    def test_rejects_parallel_same_name_project(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            create_project(root, 'hook-video', 'launch', '20260920')
            with self.assertRaises(FileExistsError):
                create_project(root, 'hook-video', 'launch', '20260920')

    def test_rejects_name_without_stable_ascii_slug(self):
        with tempfile.TemporaryDirectory() as temp, self.assertRaises(ValueError):
            create_project(Path(temp), 'validation', '项目测试', '20260920')

    def test_rejects_unknown_route(self):
        with tempfile.TemporaryDirectory() as temp, self.assertRaises(ValueError):
            create_project(Path(temp), 'other', 'demo', '20260920')


if __name__ == '__main__':
    unittest.main(verbosity=2)
