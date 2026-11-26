"""Isolated validation session with streamed output and owned-process cancellation."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time


class ValidationCancelled(Exception):
    """The operator stopped the validation."""


class _WindowsJob:
    def __init__(self, process):
        import ctypes as ct
        from ctypes import wintypes as wt

        class Limits(ct.Structure):
            _fields_ = [
                ('process_time', ct.c_int64), ('job_time', ct.c_int64),
                ('flags', wt.DWORD), ('min_ws', ct.c_size_t), ('max_ws', ct.c_size_t),
                ('processes', wt.DWORD), ('affinity', ct.c_size_t),
                ('priority', wt.DWORD), ('schedule', wt.DWORD),
            ]

        class ExtendedLimits(ct.Structure):
            _fields_ = [
                ('basic', Limits), ('io_counters', ct.c_uint64 * 6),
                ('process_memory', ct.c_size_t), ('job_memory', ct.c_size_t),
                ('peak_process', ct.c_size_t), ('peak_job', ct.c_size_t),
            ]

        kernel = ct.WinDLL('kernel32', use_last_error=True)
        signatures = {
            'CreateJobObjectW': (wt.HANDLE, [ct.c_void_p, wt.LPCWSTR]),
            'SetInformationJobObject': (wt.BOOL, [wt.HANDLE, ct.c_int, ct.c_void_p, wt.DWORD]),
            'AssignProcessToJobObject': (wt.BOOL, [wt.HANDLE, wt.HANDLE]),
            'CloseHandle': (wt.BOOL, [wt.HANDLE]),
        }
        for name, (result, args) in signatures.items():
            fn = getattr(kernel, name)
            fn.restype, fn.argtypes = result, args
        self.kernel = kernel
        self.handle = kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ct.WinError(ct.get_last_error())
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        try:
            if not kernel.SetInformationJobObject(self.handle, 9, ct.byref(limits), ct.sizeof(limits)):
                raise ct.WinError(ct.get_last_error())
            # Popen retains the live process handle, so the ID cannot resolve to another process.
            if not kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
                raise ct.WinError(ct.get_last_error())
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def stream_process(command, cwd, on_line, *, timeout, cancel=None, owned=False):
    """Run a command and deliver complete output lines without waiting for EOF.

    For an owned worker, stdin gates all work until containment is installed.
    A file with separate read/write handles keeps descendant stdout from
    blocking the timeout or cancellation if it outlives the original child.
    """
    if cancel is not None and cancel.is_set():
        raise ValidationCancelled()
    with tempfile.TemporaryDirectory(prefix='koadiag-') as temp:
        output = Path(temp) / 'progress.log'
        with output.open('wb') as writer, output.open('rb') as reader:
            proc = subprocess.Popen(
                command, cwd=cwd, stdin=subprocess.PIPE if owned else subprocess.DEVNULL,
                stdout=writer, stderr=subprocess.DEVNULL, shell=False,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                start_new_session=owned and os.name != 'nt',
            )
            job = None
            deadline = time.monotonic() + timeout
            try:
                if owned:
                    if os.name == 'nt':
                        job = _WindowsJob(proc)
                    with proc.stdin:
                        proc.stdin.write(b'START\n')
                while True:
                    if cancel is not None and cancel.is_set():
                        raise ValidationCancelled()
                    code = proc.poll()
                    for _ in range(64):
                        position = reader.tell()
                        line = reader.readline()
                        if not line:
                            if code is not None:
                                return code
                            break
                        if not line.endswith(b'\n') and code is None:
                            reader.seek(position)
                            break
                        on_line(line.decode('utf-8', errors='replace').strip())
                    if code is None:
                        if time.monotonic() >= deadline:
                            raise subprocess.TimeoutExpired(command, timeout)
                        time.sleep(0.1)
            finally:
                if job is not None:
                    job.close()
                elif owned and os.name != 'nt':
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=5)


def launch_validation(python, tool, root, mode, cancel, notify):
    outcome = None

    def receive(line):
        nonlocal outcome
        if not line.startswith('HUB='):
            return
        kind, value = json.loads(line[4:])
        if kind == 'progress':
            notify(value)
        elif kind in ('done', 'error'):
            outcome = (kind, value)

    code = stream_process(
        [str(python), '-u', '-m', 'koa_ecosystem_diag.hub_session', mode, str(root)],
        tool, receive, timeout=150 if mode == 'intermediaire' else 2100, cancel=cancel, owned=True,
    )
    if outcome and outcome[0] == 'error':
        raise RuntimeError(outcome[1])
    if code != 0 or outcome is None:
        raise RuntimeError(f'Validation interrompue sans rapport (code {code}).')
    folder = Path(outcome[1])
    return json.loads((folder / 'validation.json').read_text(encoding='utf-8')), str(folder)


def _main():
    from . import validation_hub

    # Use binary stdin: Windows local codecs and newline translation are irrelevant.
    if sys.stdin.buffer.readline().strip() != b'START':
        return 2

    def send(kind, value):
        print('HUB=' + json.dumps([kind, value]), flush=True)

    tool = Path(__file__).resolve().parents[1]
    mode, root = sys.argv[1:]
    try:
        result = validation_hub.validate(
            Path(root), mode=mode, tool=tool, progress=lambda line: send('progress', line),
        )
        send('progress', 'Enregistrement du rapport…')
        folder = validation_hub.save_report(
            result, tool / 'reports' / 'Diagnostic-kOA-Digital-Ecosystem' / 'validations',
        )
        send('done', str(folder))
        return 0
    except Exception as exc:
        send('error', f'{type(exc).__name__}: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(_main())
