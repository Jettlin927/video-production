import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from managed_job import start, status, stop, read


class ManagedJobTests(unittest.TestCase):
    def wait(self, predicate, seconds=10):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.1)
        self.fail('Condition did not become true')

    def test_cancel_kills_grandchild_and_releases_lock_for_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); beat = root / 'beat'; job = root / 'job'
            child = root / 'child.py'
            child.write_text('import pathlib,time,sys\np=pathlib.Path(sys.argv[1])\nwhile True:\n p.write_text(str(time.time()))\n time.sleep(.1)\n')
            parent = root / 'parent.py'
            parent.write_text('import subprocess,sys,time\nsubprocess.Popen([sys.executable,sys.argv[1],sys.argv[2]])\ntime.sleep(120)\n')
            launched = start(job, [sys.executable, parent, child, beat])
            self.assertEqual(launched['state'], 'running')
            self.wait(beat.exists)
            with self.assertRaisesRegex(ValueError, 'already running'):
                start(job, [sys.executable, parent, child, beat])
            stopped = stop(job)
            self.assertEqual(stopped['state'], 'cancelled')
            time.sleep(.3); old = beat.read_text(); time.sleep(.4)
            self.assertEqual(old, beat.read_text(), 'Orphaned grandchild still writing after cancel')
            start(job, [sys.executable, '-c', 'pass'])
            self.wait(lambda: status(job)['state'] == 'completed')

    def test_nonzero_exit_is_not_a_completed_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start(root, [sys.executable, '-c', 'raise SystemExit(7)'])
            self.wait(lambda: status(root)['state'] == 'failed')
            self.assertEqual(status(root)['exit_code'], 7)

    @unittest.skipUnless(os.name == 'nt', 'Windows Job Object teardown')
    def test_worker_death_also_kills_child_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); beat = root / 'beat'; job = root / 'job'
            command = [sys.executable, '-c',
                       'import pathlib,time,sys\np=pathlib.Path(sys.argv[1])\nwhile True:\n p.write_text(str(time.time()))\n time.sleep(.1)', str(beat)]
            launched = start(job, command)
            self.wait(beat.exists)
            # Kill only the worker, deliberately not /T. Its Job Object must remove the child.
            subprocess.run(['taskkill', '/PID', str(launched['pid']), '/F'], check=True,
                           stdout=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
            self.wait(lambda: status(job)['state'] == 'interrupted')
            old = beat.read_text(); time.sleep(.4)
            self.assertEqual(old, beat.read_text())


if __name__ == '__main__':
    unittest.main()
