"""Regression checks for C0-backed host ports; no live Docker/network/test DB."""
from __future__ import annotations

import importlib.util
from importlib.machinery import SourceFileLoader
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from koa_ecosystem_diag import local_runtime, test_stack


REPO = Path(__file__).resolve().parents[1]


def load_gui_source():
    name = 'koa_lot_ports_e2e_launcher'
    source = SourceFileLoader(name, str(REPO / 'Konnaxion-Orgo-E2E.pyw'))
    spec = importlib.util.spec_from_loader(name, source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    source.exec_module(module)
    return module


class RegistryPortRegression(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        path = self.root / 'kOA_Digital_Ecosystem/kOA_Digital_Ecosystem/config/local-dev-ports.v1.json'
        path.parent.mkdir(parents=True)
        self.regpath = path
        self.registry = {
            'schema_version': 1, 'registry_id': 'koa-c0-local-development-ports',
            'host': '127.0.0.1', 'transport': 'tcp',
            'pool': {'start': 21100, 'end': 21199},
            'blocks': [
                {'owner': 'orgo', 'start': 21110, 'end': 21119},
                {'owner': 'konnaxion', 'start': 21130, 'end': 21139},
            ],
            'services': [
                {'id': 'orgo-api', 'owner': 'orgo', 'port': 21111},
                {'id': 'konnaxion-api', 'owner': 'konnaxion', 'port': 21131},
            ],
            'decision_status': 'proposed',
        }
        self.save()

    def save(self):
        self.regpath.write_text(json.dumps(self.registry), encoding='utf-8')

    def prepare_owner_dirs(self):
        orgo = self.root / 'Orgo/Orgo'
        konnaxion = self.root / 'Konnaxion/Konnaxion'
        (orgo / 'validation/konnaxion-orgo-ik').mkdir(parents=True)
        (orgo / 'validation/konnaxion-orgo-ik/run-e2e.ps1').write_text('# mock owner script\n', encoding='utf-8')
        konnaxion.mkdir(parents=True)
        return orgo, konnaxion

    def test_gui_reads_both_c0_service_ids(self):
        gui = load_gui_source()
        stacks = gui.stacks_at(self.root)
        self.assertEqual(stacks[0].ready_url, 'http://127.0.0.1:21131/health/ready/')
        self.assertEqual(stacks[1].ready_url, 'http://127.0.0.1:21111/health/ready')
        self.assertEqual((stacks[0].host_port, stacks[1].host_port), (21131, 21111))

    def test_gui_follows_valid_new_ports_without_magic_numbers(self):
        gui = load_gui_source()
        self.registry['services'][0]['port'] = 21117
        self.registry['services'][1]['port'] = 21136
        self.save()
        stacks = gui.stacks_at(self.root)
        self.assertIn(':21117/', stacks[1].ready_url)
        self.assertIn(':21136/', stacks[0].ready_url)
        self.assertEqual(stacks[0].host_port, 21136)

    def test_gui_refuses_missing_registry_without_legacy_fallback(self):
        gui = load_gui_source()
        self.regpath.unlink()
        with self.assertRaises(FileNotFoundError):
            gui.stacks_at(self.root)
        with patch.object(gui, 'invoke', side_effect=AssertionError('No Docker calls')):
            self.assertIn('BLOCKED', gui.run_action(self.root, 'test', lambda *_: None))

    def test_gui_refuses_invalid_or_incomplete_registry(self):
        gui = load_gui_source()
        self.registry['services'][1]['port'] = 21111
        self.save()
        with self.assertRaises(ValueError):
            gui.stacks_at(self.root)
        self.registry['services'].pop()
        self.save()
        with self.assertRaises(ValueError):
            gui.stacks_at(self.root)

    def test_gui_handles_null_health_in_compose_json(self):
        gui = load_gui_source()
        payload = json.dumps({'Service': 'django', 'State': 'running', 'Health': None})
        self.assertEqual(gui.service_states(payload)['django'], ['running'])

    def test_gui_owner_kit_receives_port_from_registry(self):
        gui = load_gui_source()
        orgo, konnaxion = self.prepare_owner_dirs()
        backend = konnaxion / 'backend'
        backend.mkdir()
        (backend / 'docker-compose.local.yml').write_text('services: {}', encoding='utf-8')
        (orgo / 'docker-compose.yml').write_text('services: {}', encoding='utf-8')
        env = backend / '.envs/.local/.django'
        env.parent.mkdir(parents=True)
        env.write_text('IK_ORGO_TOKEN=do-not-print\nIK_ORGO_TARGET_ORGANIZATION=orgo\n', encoding='utf-8')
        self.registry['services'][0]['port'] = 21117
        self.save()
        commands = []
        def call(command, folder, timeout):
            commands.append(command)
            if command[0] == 'pwsh':
                return Mock(returncode=0, stdout=gui.PASS_MARKER + '\n', stderr='')
            services = ('redis', 'mailpit', 'django', 'celeryworker') if 'Konnaxion' in str(folder) \
                else ('postgres', 'api', 'worker')
            return Mock(returncode=0, stdout=json.dumps([
                {'Service': name, 'State': 'running', 'Health': None} for name in services
            ]), stderr='')
        with patch.object(gui, 'invoke', side_effect=call), \
             patch.object(gui.shutil, 'which', side_effect=lambda name: name), \
             patch.object(gui, 'readiness', return_value=True):
            result = gui.run_action(self.root, 'test', lambda *_: None)
        self.assertIn('PASS', result)
        command = next(command for command in commands if command[0] == 'pwsh')
        self.assertEqual(command[command.index('-OrgoHostUrl') + 1], 'http://127.0.0.1:21117')

    def test_gui_never_runs_owner_kit_when_readiness_fails(self):
        gui = load_gui_source()
        orgo, konnaxion = self.prepare_owner_dirs()
        backend = konnaxion / 'backend'
        backend.mkdir()
        (backend / 'docker-compose.local.yml').write_text('services: {}', encoding='utf-8')
        (orgo / 'docker-compose.yml').write_text('services: {}', encoding='utf-8')
        env = backend / '.envs/.local/.django'
        env.parent.mkdir(parents=True)
        env.write_text('IK_ORGO_TOKEN=do-not-print\nIK_ORGO_TARGET_ORGANIZATION=orgo\n', encoding='utf-8')
        commands = []
        def call(command, folder, timeout):
            commands.append(command)
            services = ('redis', 'mailpit', 'django', 'celeryworker') if 'Konnaxion' in str(folder) \
                else ('postgres', 'api', 'worker')
            return Mock(returncode=0, stdout=json.dumps([
                {'Service': name, 'State': 'running', 'Health': None} for name in services
            ]), stderr='')
        with patch.object(gui, 'invoke', side_effect=call), \
             patch.object(gui.shutil, 'which', side_effect=lambda name: name), \
             patch.object(gui, 'readiness', side_effect=[False, True]):
            result = gui.run_action(self.root, 'test', lambda *_: None)
        self.assertIn('Preflight incomplete', result)
        self.assertTrue(all(command[0] != 'pwsh' for command in commands))

    def test_legacy_runner_uses_registry_for_official_kit_url(self):
        self.prepare_owner_dirs()
        completed = Mock(returncode=0, stdout=b'KONNAXION <-> ORGO IK E2E PASS\n')
        with patch.object(local_runtime.shutil, 'which', return_value='pwsh'), \
             patch.object(local_runtime.subprocess, 'run', return_value=completed) as invoke:
            verdict, _, _ = local_runtime.run(self.root)
        self.assertEqual(verdict, 'PASS')
        command = invoke.call_args.args[0]
        self.assertEqual(command[command.index('-OrgoHostUrl') + 1], 'http://127.0.0.1:21111')

        self.registry['services'][0]['port'] = 21117
        self.save()
        with patch.object(local_runtime.shutil, 'which', return_value='pwsh'), \
             patch.object(local_runtime.subprocess, 'run', return_value=completed) as invoke:
            verdict, _, _ = local_runtime.run(self.root)
        self.assertEqual(verdict, 'PASS')
        command = invoke.call_args.args[0]
        self.assertEqual(command[command.index('-OrgoHostUrl') + 1], 'http://127.0.0.1:21117')

    def test_legacy_runner_blocks_invalid_registry_before_subprocess(self):
        self.prepare_owner_dirs()
        self.regpath.unlink()
        with patch.object(local_runtime.shutil, 'which', return_value='pwsh'), \
             patch.object(local_runtime.subprocess, 'run', side_effect=AssertionError('No owner kit')):
            verdict, _, _ = local_runtime.run(self.root)
        self.assertEqual(verdict, 'BLOCKED')

    def test_test_stack_fails_closed_before_docker(self):
        self.regpath.unlink()
        with patch.object(test_stack.subprocess, 'run', side_effect=AssertionError('No Docker')):
            with self.assertRaises(FileNotFoundError):
                test_stack.start(self.root/'Orgo/Orgo', self.root/'Konnaxion/Konnaxion/backend',
                                 io.StringIO(), root=self.root)

    def test_test_stack_respects_modified_registry(self):
        orgo, konnaxion = self.prepare_owner_dirs()
        backend = konnaxion/'backend'
        backend.mkdir()
        (orgo/'docker-compose.yml').write_text('services: {}', encoding='utf-8')
        for name in test_stack.KX_FILES:
            (backend/name).write_text('services: {}', encoding='utf-8')
        self.registry['services'][0]['port'] = 21117
        self.registry['services'][1]['port'] = 21136
        self.save()
        def fake_run(command, **kwargs):
            if 'config' in command:
                return Mock(returncode=0, stdout=json.dumps({'services': {
                    'django': {'environment': {'DATABASE_URL': 'postgres://user:secret@kx-e2e-postgres/konnaxion_e2e'}},
                    'celeryworker': {'environment': {'DATABASE_URL': 'postgres://user:secret@kx-e2e-postgres/konnaxion_e2e'}},
                }}).encode())
            return Mock(returncode=0, stdout='django\nceleryworker\napi\nworker\n', stderr='')
        with patch.object(test_stack.shutil, 'which', return_value='docker'), \
             patch.object(test_stack.subprocess, 'run', side_effect=fake_run), \
             patch.object(test_stack, 'wait_ready') as waited:
            test_stack.start(orgo, backend, io.StringIO(), root=self.root)
        urls = waited.call_args.args[0]
        self.assertEqual(urls['Orgo'], 'http://127.0.0.1:21117/health/ready')
        self.assertEqual(urls['Konnaxion'], 'http://127.0.0.1:21136/health/ready/')


if __name__ == '__main__':
    unittest.main()
