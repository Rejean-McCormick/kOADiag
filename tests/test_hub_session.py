import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from koa_ecosystem_diag.hub_session import ValidationCancelled, stream_process


class HubSessionTests(unittest.TestCase):
    def test_reports_progress_before_exit_and_cancels_owned_tree(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            marker = root / 'descendant-survived'
            descendant = (
                'import pathlib, sys, time; time.sleep(1.4); '
                'pathlib.Path(sys.argv[1]).touch()'
            )
            worker = (
                'import subprocess, sys, time; '
                'assert sys.stdin.buffer.readline().strip() == b"START"; '
                'subprocess.Popen([sys.executable, "-c", sys.argv[1], sys.argv[2]]); '
                'print("LEVEL_START=N01|Collecte", flush=True); time.sleep(10)'
            )
            event = threading.Event()
            seen = []

            def receive(line):
                seen.append(line)
                event.set()

            with self.assertRaises(ValidationCancelled):
                stream_process(
                    [sys.executable, '-c', worker, descendant, str(marker)],
                    root, receive, timeout=5, cancel=event, owned=True,
                )
            self.assertEqual(seen, ['LEVEL_START=N01|Collecte'])
            self.assertFalse(threading.Event().wait(1.6))
            self.assertFalse(marker.exists(), 'Validation child outlived its owned session')

    def test_silent_worker_has_a_timeout(self):
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(subprocess.TimeoutExpired):
            stream_process(
                [sys.executable, '-c', 'import time; time.sleep(10)'],
                folder, lambda _: None, timeout=0.25,
            )


class HubStartTests(unittest.TestCase):
    def test_start_reaches_worker_without_a_previous_report(self):
        from importlib.machinery import SourceFileLoader
        from importlib.util import module_from_spec, spec_from_loader
        from queue import Queue
        from types import SimpleNamespace
        from unittest.mock import Mock, patch

        try:
            import tkinter  # noqa: F401
        except ImportError:
            self.skipTest('Tkinter indisponible')
        source = Path(__file__).resolve().parents[1] / 'Diagnostic-kOA-Digital-Ecosystem.pyw'
        spec = spec_from_loader('koatest_gui', SourceFileLoader('koatest_gui', str(source)))
        gui = module_from_spec(spec)
        spec.loader.exec_module(gui)
        app = SimpleNamespace(
            hub_running=False, running=False, ports_running=False,
            reboot_running=False, ik_busy=False, rootvar=Mock(get=lambda: str(source.parent)),
            hub_status=Mock(), hub_fast_btn=Mock(), hub_deep_btn=Mock(), hub_mid_btn=Mock(), hub_stop_btn=Mock(),
            hub_progress_bar=Mock(), hub_set_text=Mock(), hub_steps_text=Mock(), q=Queue(),
            manifest=gui.load_manifest(source.parent),
        )

        class ImmediateThread:
            def __init__(self, *, target, **_kwargs):
                self.target = target

            def start(self):
                self.target()

        with patch.object(gui.threading, 'Thread', ImmediateThread), \
             patch.object(gui, 'launch_validation', return_value=({'summary': {}}, 'fixture')) as run:
            gui.App.hub_begin(app, 'approfondie')
        run.assert_called_once()
        self.assertEqual(app.q.get_nowait(), ('hub_done', ({'summary': {}}, 'fixture')))
        self.assertEqual(app.hub_total, 15)
        app.hub_running = False
        with patch.object(gui.threading, 'Thread', ImmediateThread), \
             patch.object(gui, 'launch_validation', return_value=({'summary': {}}, 'fixture')) as run:
            gui.App.hub_begin(app, 'intermediaire')
        self.assertEqual(run.call_args.args[3], 'intermediaire')
        self.assertEqual(app.hub_total, 5)
