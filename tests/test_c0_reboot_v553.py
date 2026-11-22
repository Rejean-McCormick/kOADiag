# -*- coding: utf-8 -*-
"""Tests de sécurité du contrôle C0. Aucun démarrage réel n'est effectué."""
from __future__ import annotations
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from koa_ecosystem_diag import c0_reboot as reboot
from koa_ecosystem_diag.port_diagnostics import REGISTRY_ID

PORTS = {
    'orgo-web': 21110, 'orgo-api': 21111, 'orgo-worlds-web': 21112,
    'orgo-worlds-api': 21113, 'orgo-koali-web': 21114, 'orgo-koali-api': 21115,
    'orgo-koali-pglite': 21116, 'initkoa-web': 21120,
    'konnaxion-web': 21130, 'konnaxion-api': 21131,
    'konnaxion-capsule-agent-local': 21132,
    'konnaxion-capsule-manager-local': 21133,
    'konnaxion-koali-web': 21134, 'konnaxion-koali-api': 21135,
    'skope-web': 21140,
    'ekole-quebec-learner': 21150, 'ekole-quebec-teacher': 21151,
    'ekole-opsconsole': 21152, 'ekole-pastorale-learner': 21153,
    'ekole-pastorale-teacher': 21154, 'koali-spaces-web': 21170,
}


def owner(service_id):
    if service_id.startswith('orgo'): return 'orgo'
    if service_id.startswith('konnaxion'): return 'konnaxion'
    if service_id.startswith('initkoa'): return 'initkoa'
    if service_id.startswith('skope'): return 'skope'
    if service_id.startswith('ekole'): return 'ekole'
    return 'koali'


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.registry = self.base / 'kOA_Digital_Ecosystem' / 'kOA_Digital_Ecosystem' / 'config' / 'local-dev-ports.v1.json'
        self.registry.parent.mkdir(parents=True)
        self.original_base, self.original_registry = reboot.BASE, reboot.REGISTRY
        self.addCleanup(self.restore)
        reboot.BASE, reboot.REGISTRY = self.base, self.registry
        self.doc = {
            'schema_version': 1, 'registry_id': REGISTRY_ID,
            'host': '127.0.0.1', 'transport': 'tcp',
            'pool': {'start': 21100, 'end': 21199},
            'blocks': [{'owner': own, 'start': lo, 'end': lo + 9} for own, lo in
                       [('orgo',21110),('initkoa',21120),('konnaxion',21130),
                        ('skope',21140),('ekole',21150),('koali',21170)]],
            'services': [dict(id=sid, owner=owner(sid), port=port)
                         for sid, port in PORTS.items()]
        }
        self.save()

    def restore(self):
        reboot.BASE, reboot.REGISTRY = self.original_base, self.original_registry

    def save(self):
        self.registry.write_text(json.dumps(self.doc, ensure_ascii=False), encoding='utf-8')

    def test_all_21_covered_and_groups_partition(self):
        services = reboot.load_registry()
        listed = [sid for group in reboot.GROUPS.values() for sid in group['ids']]
        self.assertEqual(set(listed), set(services))
        self.assertEqual(len(listed), 21)
        self.assertEqual(sum(len(g['ids']) for g in reboot.GROUPS.values() if g['mode'] == 'manual'), 9)

    def test_plan_reports_manual_and_does_not_start_anything(self):
        buffer = io.StringIO()
        with patch.object(reboot, 'build_commands', side_effect=AssertionError('no start')), \
             patch.object(reboot, 'run_docker', side_effect=AssertionError('no Docker')), \
             patch.object(reboot, 'launch_process', side_effect=AssertionError('no process')), \
             contextlib.redirect_stdout(buffer):
            self.assertEqual(reboot.main(['plan', '--all', '--root', str(self.base)]), 0)
        output = buffer.getvalue()
        self.assertEqual(output.count(' MANUEL'), 3)
        self.assertIn('Aucun processus n’a été modifié', output)
        self.assertIn('21120', output)

    def test_duplicate_port_refused(self):
        self.doc['services'][1]['port'] = 21110
        self.save()
        with self.assertRaises(ValueError):
            reboot.load_registry()

    def test_new_service_refused_until_group_plan_updated(self):
        self.doc['services'].append({'id':'orgo-new', 'owner':'orgo', 'port':21117})
        self.save()
        with self.assertRaisesRegex(RuntimeError, 'ne correspond pas'):
            reboot.load_registry()

    def test_stale_pid_never_stopped(self):
        state={'processes':[{'group':'initkoa','label':'old','pid':99999999,'created':'0'}]}
        with patch.object(reboot, 'owned', return_value=False), \
             patch.object(reboot, 'state_save') as save, \
             patch.object(reboot.os, 'kill', side_effect=AssertionError('killed')):
            self.assertTrue(reboot.stop_group('initkoa', state))
        self.assertEqual(state['processes'], [])
        save.assert_called_once()

    @unittest.skipIf(__import__('os').name == 'nt', 'Test réservé au Linux de CI')
    def test_non_windows_refuses_reboot(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(reboot.main(['restart','--all','--root',str(self.base)]), 2)

    def test_ui_exposes_explicit_confirmation_without_force(self):
        gui = (Path(__file__).resolve().parents[1] / 'Diagnostic-kOA-Digital-Ecosystem.pyw').read_text(encoding='utf-8')
        self.assertIn('VOIR LE PLAN', gui)
        self.assertIn('Essentiels', gui)
        self.assertIn('Tous les groupes', gui)
        self.assertIn('Arrêter supervisés', gui)
        self.assertIn('if not ack.get()', gui)
        self.assertIn("self.q.put(('reboot_done'", gui)
        self.assertNotIn("cmd.append('--force-owned')", gui)

if __name__ == '__main__':
    unittest.main()
