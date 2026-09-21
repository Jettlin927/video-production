"""Local, resumable jobs with an OS lock, compact status and process-tree cancellation."""
import argparse
import contextlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid
import threading


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, path)


@contextlib.contextmanager
def lock(directory):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'job.lock').open('a+b') as handle:
        handle.seek(0); handle.write(b'0'); handle.flush(); handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def contain_worker():
    """Windows closes this Job on worker death, killing every descendant, including FFmpeg."""
    if os.name != 'nt':
        return None
    import ctypes as c
    from ctypes import wintypes as w
    class Basic(c.Structure):
        _fields_ = [('process_time', c.c_int64), ('job_time', c.c_int64), ('flags', w.DWORD),
                    ('min_working', c.c_size_t), ('max_working', c.c_size_t), ('active', w.DWORD),
                    ('affinity', c.c_size_t), ('priority', w.DWORD), ('scheduling', w.DWORD)]
    class IO(c.Structure):
        _fields_ = [(name, c.c_uint64) for name in ['read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes']]
    class Extended(c.Structure):
        _fields_ = [('basic', Basic), ('io', IO), ('process_memory', c.c_size_t),
                    ('job_memory', c.c_size_t), ('peak_process', c.c_size_t), ('peak_job', c.c_size_t)]
    kernel = c.WinDLL('kernel32', use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]
    kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    job = kernel.CreateJobObjectW(None, None)
    limits = Extended(); limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not job or not kernel.SetInformationJobObject(job, 9, c.byref(limits), c.sizeof(limits)):
        raise c.WinError(c.get_last_error())
    if not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess()):
        raise c.WinError(c.get_last_error())
    # Keep the handle until process exit. Closing it explicitly would also kill this worker.
    return job


def kill_tree(process):
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=10)


def worker(root, run_dir):
    request = read(run_dir / 'request.json')
    state = {'job_id': run_dir.name, 'state': 'starting', 'pid': os.getpid(),
             'started_at': time.time(), 'log': str(run_dir / 'job.log')}
    process = None
    try:
        with lock(root):
            job_handle = contain_worker()
            state['state'] = 'running'
            write(root / 'active.json', {'run_dir': str(run_dir)})
            write(run_dir / 'state.json', state)
            with (run_dir / 'job.log').open('wb') as log:
                process = subprocess.Popen(request['command'], stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                           start_new_session=os.name != 'nt',
                                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                while process.poll() is None:
                    if (run_dir / 'cancel').exists():
                        kill_tree(process)
                        state['state'] = 'cancelled'
                        break
                    time.sleep(.2)
            if state['state'] != 'cancelled':
                state['state'] = 'completed' if process.returncode == 0 else 'failed'
            state.update(exit_code=process.returncode, finished_at=time.time())
            write(run_dir / 'state.json', state)
    except Exception as exc:
        if process and process.poll() is None:
            kill_tree(process)
        state.update(state='failed', error=str(exc), finished_at=time.time())
        write(run_dir / 'state.json', state)
    return 0 if state['state'] == 'completed' else 1


def start(root, command):
    root = root.resolve()
    # Fast rejection; the worker holds this same lock throughout execution (also closes the race).
    try:
        with lock(root):
            pass
    except OSError:
        raise ValueError('A job is already running here; use job-status or job-stop') from None
    run_dir = root / 'runs' / uuid.uuid4().hex
    write(run_dir / 'request.json', {'command': [str(x) for x in command]})
    with (run_dir / 'worker.log').open('wb') as log:
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), 'worker',
                                    '--job-dir', str(root), '--run-dir', str(run_dir)],
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=log, close_fds=True,
                                   start_new_session=os.name != 'nt',
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    threading.Thread(target=process.wait, daemon=True).start()
    for _ in range(50):
        if (run_dir / 'state.json').exists():
            return {**read(run_dir / 'state.json'), 'job_dir': str(root)}
        if process.poll() is not None:
            raise RuntimeError('Job worker exited before readiness; see ' + str(run_dir / 'worker.log'))
        time.sleep(.1)
    return {'state': 'starting', 'job_id': run_dir.name, 'job_dir': str(root)}


def status(root):
    run_dir = Path(read(root / 'active.json')['run_dir'])
    state = read(run_dir / 'state.json')
    if state['state'] == 'running':
        try:
            with lock(root):
                state.update(state='interrupted', error='Worker is no longer holding the job lock')
                write(run_dir / 'state.json', state)
        except OSError:
            pass
    return state


def stop(root):
    state = status(root)
    if state['state'] != 'running':
        return state
    run_dir = Path(read(root / 'active.json')['run_dir'])
    (run_dir / 'cancel').touch()
    for _ in range(50):
        state = status(root)
        if state['state'] != 'running':
            return state
        time.sleep(.1)
    return {**state, 'state': 'stopping'}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['worker', 'status', 'stop', 'resume'])
    p.add_argument('--job-dir', type=Path, required=True)
    p.add_argument('--run-dir', type=Path)
    a = p.parse_args(argv)
    if a.action == 'worker':
        return worker(a.job_dir, a.run_dir)
    if a.action == 'resume':
        run_dir = Path(read(a.job_dir / 'active.json')['run_dir'])
        result = start(a.job_dir, read(run_dir / 'request.json')['command'])
    else:
        result = stop(a.job_dir) if a.action == 'stop' else status(a.job_dir)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
