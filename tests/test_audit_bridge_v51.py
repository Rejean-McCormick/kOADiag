# -*- coding: utf-8 -*-
"""Diagnostic->Audit bridge contract; no GitHub Audit dependency required."""
import csv
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from koa_ecosystem_diag.audit_export import build_bundle, export_campaign, publish_private_bundle
from koa_ecosystem_diag.boundary_review import write_review_register


class AuditBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.run = self.base / 'runs' / '20261110T192300Z-83d16444'
        self.run.mkdir(parents=True)
        self.summary = {
            'schema': 'levelupdiag.campaign-summary.v2',
            'suite': 'Diagnostic du kOA Digital Ecosystem', 'suite_version': '5.1.0',
            'run_id': self.run.name, 'selection': 'complet',
            'target_repo_root': r'C:\mycode\sensitive',
            'started_at': '2026-11-10T19:23:00+00:00',
            'ended_at': '2026-11-10T19:24:18+00:00',
            'verdict': 'PARTIAL', 'counts': {'PARTIAL': 1},
            'levels': [{'id': 'N01', 'verdict': 'PARTIAL', 'result': '../../secret.txt'}],
            'coverage': {
                'inventory': {'present': 53, 'declared': 53, 'truncated': 2, 'complete': False},
                'relations': 58,
                'api': {'static_calls': 5},
                'traces': {'correlated_pairs': 0},
                'journeys': {'declared': 0, 'evidence_complete': 0},
                'global_end_to_end': {'status': 'NON_CERTIFIE', 'explanation': 'SECRET-COVERAGE'},
            },
        }
        self.detail = {
            'schema': 'levelupdiag.report.v2', 'suite': self.summary['suite'],
            'run_id': self.run.name, 'level_id': 'N01', 'verdict': 'PARTIAL',
            'target_repo_root': r'C:\mycode\secret',
            'findings': [{'message': 'SECRET-TRACE-AND-TOKEN', 'url': 'http://localhost/private'}],
        }
        self.write()

    def write(self):
        (self.run / 'summary.json').write_text(json.dumps(self.summary), encoding='utf-8')
        result = self.run / 'levels' / 'N01' / 'result.json'
        result.parent.mkdir(parents=True, exist_ok=True)
        result.write_text(json.dumps(self.detail), encoding='utf-8')

    def test_deterministic_and_private(self):
        a = build_bundle(self.run)
        self.assertEqual(a, build_bundle(self.run))
        with zipfile.ZipFile(self.base / 'test.zip', 'w') as out:
            out.writestr('bad.txt', 'test')
        with zipfile.ZipFile(__import__('io').BytesIO(a)) as archive:
            self.assertEqual(sorted(archive.namelist()), [
                'latest/levels/N01/result.json', 'latest/summary.json'])
            summary = json.loads(archive.read('latest/summary.json'))
            self.assertEqual(summary['coverage']['relations'], 58)
        for private in (b'C:\\mycode', b'SECRET-COVERAGE', b'SECRET-TRACE', b'localhost', b'../../secret.txt'):
            self.assertNotIn(private, a)

    def test_mismatch_rejected(self):
        self.detail['run_id'] = 'different'
        self.write()
        with self.assertRaisesRegex(ValueError, 'incohérent'):
            build_bundle(self.run)

    def test_no_partial_level_export(self):
        (self.run/'levels/N01/result.json').unlink()
        with self.assertRaises(ValueError):
            build_bundle(self.run)

    def test_published_private_and_idempotent(self):
        control = self.base / 'private-reports'
        first, latest = publish_private_bundle(self.run, control)
        self.assertEqual(first.read_bytes(), latest.read_bytes())
        second, again = publish_private_bundle(self.run, control)
        self.assertEqual(first, second)
        self.assertEqual(latest, again)
        self.assertTrue((control/'bridge-audit/.gitignore').is_file())

    def test_refuse_github_pages(self):
        with self.assertRaisesRegex(ValueError, 'docs'):
            export_campaign(self.run, self.base / 'docs' / 'private.zip')

    def test_export_identical_but_not_overwrite_different(self):
        target = self.base/'audit.zip'
        export_campaign(self.run, target)
        export_campaign(self.run, target)
        self.summary['coverage']['relations'] = 59
        self.write()
        with self.assertRaises(FileExistsError):
            export_campaign(self.run, target)

    def test_review_register_not_automatically_qualified_and_excel_safe(self):
        snapshot={'relations':[{'source':'=SECRET', 'target':'Orgo', 'contract':'/health',
                               'qualification':'DOCUMENTÉ'}]}
        out=self.base/'review.csv'
        self.assertEqual(write_review_register(snapshot,out),1)
        with out.open(encoding='utf-8-sig',newline='') as stream:
            row=next(csv.DictReader(stream,delimiter=';'))
        self.assertEqual(row['review_status'],'UNREVIEWED')
        self.assertEqual(row['required'],'')
        self.assertTrue(row['source_repo'].startswith("'="))

if __name__ == '__main__':
    unittest.main()
