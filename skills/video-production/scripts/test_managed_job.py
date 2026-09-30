import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from managed_job import start, status, stop, read, write, watch


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

    def test_watch_waits_for_same_job_and_reports_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            launched = start(root, [sys.executable, '-c', 'raise SystemExit(7)'])
            result = watch(root, timeout=5)
            self.assertEqual(result['job_id'], launched['job_id'])
            self.assertEqual(result['state'], 'failed')
            self.assertEqual(result['exit_code'], 7)

    def test_watch_timeout_does_not_stop_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start(root, [sys.executable, '-c', 'import time; time.sleep(30)'])
            try:
                result = watch(root, timeout=0)
                self.assertEqual(result['state'], 'running')
                self.assertTrue(result['watch_timed_out'])
                self.assertEqual(status(root)['state'], 'running')
            finally:
                stop(root)

    def test_status_rereads_after_worker_completes_before_lock_acquisition(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); run = root / 'run'
            write(root / 'active.json', {'run_dir': str(run)})
            write(run / 'state.json', {'job_id': 'r', 'state': 'running'})
            @contextmanager
            def finished_before_lock(_):
                write(run / 'state.json', {'job_id': 'r', 'state': 'completed', 'exit_code': 0})
                yield
            with patch('managed_job.lock', finished_before_lock):
                self.assertEqual(status(root)['state'], 'completed')

    def test_watch_rejects_wrong_job_and_invalid_timeout(self):
        with patch('managed_job.status', return_value={'job_id': 'actual', 'state': 'completed'}):
            with self.assertRaisesRegex(ValueError, 'job_id'):
                watch(Path('.'), job_id='other')
            for timeout in (float('nan'), float('inf'), -1):
                with self.assertRaises(ValueError):
                    watch(Path('.'), timeout=timeout)

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
