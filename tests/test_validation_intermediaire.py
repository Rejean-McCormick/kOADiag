from hashlib import sha256
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from koa_ecosystem_diag import validation_hub as v
from koa_ecosystem_diag.coverage import get_previous


class IntermediateEvidenceTests(unittest.TestCase):
    def test_timed_out_campaign_keeps_its_existing_evidence(self):
        with TemporaryDirectory() as folder:
            tool = Path(folder)
            (tool/'Diagnostic-kOA-Digital-Ecosystem-CLI.py').touch()
            runs = tool/'reports'/'runs'
            root = runs/'sample-run'
            level = root/'levels'/'N00'
            level.mkdir(parents=True)
            artifact = level/'evidence.csv'
            artifact.touch()
            outside = tool/'private.json'
            outside.touch()
            source = level/'result.json'
            source.write_text(json.dumps({
                'schema':'levelupdiag.report.v2', 'level_id':'N00', 'run_id':root.name,
                'verdict':'WARN', 'findings':[{'id':'sample.issue','verdict':'WARN',
                    'category':'scope','message':'token=private-value','evidence':{'payload':'raw'}}],
                'artifacts':[{'path':str(artifact)},{'path':str(outside)}],
            }), encoding='utf-8')
            expected = [{'id':'N00','name':'Intégrité'},{'id':'N01','name':'Collecte'}]

            def stream(args, cwd, receive, **options):
                self.assertIn('validation-intermediaire', args)
                self.assertNotIn('--runtime-local', args)
                self.assertEqual(options['timeout'], 105)
                receive('RUN_ROOT='+str(root))
                raise subprocess.TimeoutExpired(args, 105)

            with patch.object(v, 'stream_process', side_effect=stream):
                result = v._passive_campaign(tool, tool, selection='validation-intermediaire',
                    timeout=105, evidence_context=(runs,expected))
            self.assertTrue(result['timed_out'])
            first, second = result['developer_evidence']['niveaux']
            self.assertEqual(first['sha256'], sha256(source.read_bytes()).hexdigest())
            self.assertEqual(first['artefacts'], ['levels/N00/evidence.csv'])
            self.assertEqual(first['verdict'], 'WARN')
            self.assertEqual(second['verdict'], 'NON_OBSERVE')
            evidence = json.dumps(first)
            self.assertNotIn('private-value', evidence)
            self.assertNotIn('payload', evidence)

    def test_history_keeps_bounded_and_full_campaigns_separate(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            for uid, selection in [('a-full','validation-integrale'),('b-mid','validation-intermediaire')]:
                path = root/'runs'/uid/'summary.json'
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps({'selection':selection,'run_id':uid}))
            self.assertEqual(get_previous(root,'current')[0]['run_id'],'a-full')
            self.assertEqual(get_previous(root,'current',intermediate=True)[0]['run_id'],'b-mid')


class IntermediateSamplingTests(unittest.TestCase):
    def test_bounded_enumeration_marks_coverage_incomplete(self):
        from koa_ecosystem_diag.interrepo_core import inventory_surface
        with TemporaryDirectory() as folder:
            root = Path(folder)
            for number in range(45):
                (root/f'api_{number:02d}.py').write_text('import sys\n', encoding='utf-8')
            result = inventory_surface('fixture',root,{'scan':{
                'max_files_per_repo':120,'max_surface_entries_per_repo':12,
            }})
            self.assertGreater(result['files_scanned'], 0)
            self.assertLessEqual(result['files_scanned'], 11)
            self.assertTrue(result['traversal_limited'])
            self.assertTrue(result['scan_limit_reached'])

    def test_exhausted_read_budget_keeps_inventory_but_no_code_claim(self):
        from koa_ecosystem_diag.interrepo_core import inventory_surface
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'api.py').write_text('import sys\n', encoding='utf-8')
            result = inventory_surface('fixture',root,{'scan':{}},deadline=0)
            self.assertEqual(result['files_scanned'], 0)
            self.assertTrue(result['traversal_limited'])
            self.assertTrue(result['scan_limit_reached'])
