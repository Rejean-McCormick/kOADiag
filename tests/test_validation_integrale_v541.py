import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from koa_ecosystem_diag import boundary_registry, runner
from koa_ecosystem_diag.framework import Report, load_manifest
from koa_ecosystem_diag.full_validation import assess
from koa_ecosystem_diag.levels.checks import n10


class IntegralTests(unittest.TestCase):
    def test_every_boundary_has_two_mode_results(self):
        decisions = {'relations': [
            {'boundary_key': 'one', 'source_repo': 'A', 'target_repo': 'B',
             'required': True, 'review_status': 'APPROVED', 'observed': True},
            {'boundary_key': 'two', 'source_repo': 'B', 'target_repo': 'A',
             'required': None, 'review_status': 'REJECTED', 'observed': True},
        ]}
        snapshot = {'repositories': [{'repo': 'A', 'exists': True, 'scanned_files': 10},
                                     {'repo': 'B', 'exists': False}],
                    'documentary_scope': {'aligned': False, 'obligations': [
                        {'boundary_key': 'three', 'source': 'C', 'target': 'A'}]}}
        value = assess(snapshot, decisions, [], {}, collected=True)
        self.assertEqual(len(value['cases']), 8)
        by_key = {(row['id'], row['mode']): row['verdict'] for row in value['cases']}
        self.assertEqual(by_key['one', 'autonome'], 'BLOCKED')
        self.assertEqual(by_key['two', 'integre'], 'SKIP')
        self.assertEqual(by_key['three', 'integre'], 'BLOCKED')
        self.assertEqual(by_key['A', ''], 'PASS')

    def test_failed_and_malformed_probes_do_not_prevent_next_probe(self):
        def probe(spec, *args):
            if spec['id'] == 'malformed':
                raise TypeError()
            return {'source': 'A', 'target': 'B', 'detail': '',
                    'http_status': 200, 'latency_ms': 1,
                    'status': 'API_REPOND' if spec['id'] == 'success' else 'INACCESSIBLE'}

        with tempfile.TemporaryDirectory() as tmp, patch('koa_ecosystem_diag.ik_diag_core.probe_api', side_effect=probe):
            root = Path(tmp)
            report = Report({'id': 'N10', 'name': 'API'}, root, 'test')
            cfg = {'interrepo': {'ik': {'probes': [
                {'enabled': True, 'id': item} for item in ('failure', 'malformed', 'success')]}}}
            n10(cfg, report, {'run_root': root, 'allow_network': True})
            rows = json.loads((root/'levels/N10/probes.json').read_text())
            self.assertEqual([row['status'] for row in rows],
                             ['INACCESSIBLE', 'CONFIG_INVALIDE', 'API_REPOND'])
            self.assertEqual(report.data()['verdict'], 'FAIL')

    def test_full_campaign_runs_after_invalid_registry_even_with_fail_fast(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tool = root/'tool'
            tool.mkdir()
            for name in ('koa_ecosystem_diag',):
                shutil.copytree(source/name, tool/name, ignore=shutil.ignore_patterns('__pycache__'))
            for name in ('Diagnostic-kOA-Digital-Ecosystem-CLI.py',
                         'koa-ecosystem-diag.config.json', 'koa-ecosystem-diag.manifest.json'):
                shutil.copyfile(source/name, tool/name)
            invalid = boundary_registry.path_for(tool)
            invalid.write_text('{invalid', encoding='utf-8')
            local = tool/'koa-ecosystem-diag.config.local.json'
            local.write_text(json.dumps({'execution': {'fail_fast': True}}), encoding='utf-8')
            target = root/'target'
            target.mkdir()
            summary, directory = runner.campaign(tool, 'validation-integrale', target, jobs=4)
            levels = {row['id']: row['verdict'] for row in summary['levels']}
            self.assertEqual(len(levels), len(load_manifest(tool)['levels']))
            self.assertEqual(levels['N00'], 'CONFIG_ERROR')
            self.assertIn(levels['N01'], ('PARTIAL', 'BLOCKED'))
            self.assertEqual(levels['N10'], 'SKIP')
            self.assertEqual(levels['N14'], 'SKIP')
            self.assertTrue((directory/'validation-integrale.json').is_file())
            self.assertEqual(invalid.read_text(), '{invalid')


if __name__ == '__main__':
    unittest.main()
