import tempfile
from pathlib import Path
import unittest

from prepare_workspace import REMOTION, commands, package_manifest


class PrepareWorkspaceTests(unittest.TestCase):
    def test_shared_runtime_is_pinned_and_scoped_to_workspace(self):
        manifest = package_manifest()
        self.assertEqual(manifest['dependencies']['remotion'], REMOTION)
        self.assertEqual(manifest['dependencies']['@remotion/cli'], REMOTION)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            plan = commands(root, Path('skill').resolve(), 'python')
            flattened = ' '.join(str(x) for command in plan for x in command)
            self.assertIn(str(root / 'video-production-deps' / 'venv'), flattened)
            self.assertIn(str(root / 'video-production-deps' / 'npm-cache'), flattened)
            self.assertIn('--install', plan[3])
            self.assertNotIn('--install', plan[4])


if __name__ == '__main__':
    unittest.main(verbosity=2)
