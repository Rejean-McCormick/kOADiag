"""V5.2 regression: decisions are manual, durable and not E2E attestation."""
from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest

from koa_ecosystem_diag import boundary_registry as reg
from koa_ecosystem_diag.interrepo_core import inventory_surface

class RegistryV52(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tool=Path(self.tmp.name)
        self.rows=[{'source':'Konnaxion','target':'Orgo','contract':'ik.events/1','qualification':'DOCUMENTE'}]

    def test_unreviewed_first_and_decisions_survive_scan(self):
        rows,n=reg.synchronize(self.tool,self.rows)
        self.assertEqual(n,1)
        first=rows['relations'][0]
        self.assertEqual(first['review_status'],'UNREVIEWED')
        self.assertIsNone(first['required'])
        self.assertFalse(reg.metrics(rows)['review_complete'])
        reg.decide(self.tool,first['boundary_key'],status='APPROVED',required=True,
                   protocol='IK',audit_repo_identity='Rejean-McCormick/Orgo')
        again,n=reg.synchronize(self.tool,[dict(self.rows[0],qualification='CONTRAT_OU_ROUTE')])
        self.assertEqual(n,0)
        one=again['relations'][0]
        self.assertEqual(one['review_status'],'APPROVED')
        self.assertIs(one['required'],True)
        self.assertEqual(one['last_qualification'],'CONTRAT_OU_ROUTE')
        self.assertFalse(reg.metrics(again)['global_e2e_certified'])
        self.assertEqual(reg.metrics(again)['required'],1)

    def test_missing_snapshot_preserves_prior_decision(self):
        rows,_=reg.synchronize(self.tool,self.rows)
        key=rows['relations'][0]['boundary_key']
        reg.decide(self.tool,key,status='APPROVED',required=False)
        after,_=reg.synchronize(self.tool,[])
        self.assertFalse(after['relations'][0]['observed'])
        self.assertEqual(reg.metrics(after)['not_seen'],1)
        self.assertIs(after['relations'][0]['required'],False)

    def test_reject_bad_approval_and_untrusted_registry(self):
        rows,_=reg.synchronize(self.tool,self.rows)
        key=rows['relations'][0]['boundary_key']
        with self.assertRaises(ValueError):
            reg.decide(self.tool,key,status='APPROVED',required=None)
        with self.assertRaises(ValueError):
            reg.decide(self.tool,key,status='REJECTED',required=True)
        with self.assertRaises(ValueError):
            reg.decide(self.tool,key,status='APPROVED',required=True,protocol='HTTP',route='?token=x')
        with self.assertRaises(ValueError):
            reg.decide(self.tool,key,status='APPROVED',required=True,protocol='IK',method='GET')
        doc=reg.read(self.tool);doc['relations'][0]['review_status']='CERTIFIED'
        reg.path_for(self.tool).write_text(json.dumps(doc),encoding='utf-8')
        with self.assertRaises(ValueError):reg.read(self.tool)

    def test_prioritized_scan_and_limited_scope(self):
        repo=self.tool/'sample-repo';repo.mkdir()
        for i in range(31):
            (repo/f'a{i:03d}.py').write_text('def helper():\n    return 1\n',encoding='utf-8')
        (repo/'z_api_client.py').write_text('@app.get("/ready")\ndef handler():\n    return 1\n',encoding='utf-8')
        result=inventory_surface('Sample',repo,{'scan':{'max_files_per_repo':20,'max_file_bytes':220000}})
        self.assertTrue(result['scan_limit_reached'])
        self.assertEqual(result['files_scanned'],20)
        self.assertEqual(result['files_eligible'],32)
        self.assertEqual(result['routes'][0]['path'],'/ready')
        self.assertEqual(result['scan_scope'],'boundary-relevant code/config')

if __name__ == '__main__':
    unittest.main()

class InventoryAlignmentV52(unittest.TestCase):
    def test_reference_difference_is_explicit_and_dated(self):
        from koa_ecosystem_diag.inventory_alignment import compare
        base=Path(__file__).resolve().parents[1]
        rows=compare(base)
        self.assertEqual(rows['source'],'dated_snapshot_2026-11-10')
        self.assertEqual(rows['diag_count'],53)
        self.assertEqual(rows['audit_count'],49)
        self.assertEqual(len(rows['diag_only']),4)
        self.assertFalse(rows['aligned'])

    def test_local_audit_inventory_override_is_respected(self):
        from koa_ecosystem_diag.inventory_alignment import compare, LOCAL_NAME
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp); refs=base/'koa_ecosystem_diag'/'references';refs.mkdir(parents=True)
            (refs/'repositories.json').write_text(json.dumps([{'github_repo':'demo/A'},{'github_repo':'demo/B'}]))
            (base/LOCAL_NAME).write_text(json.dumps({'github_repos':['demo/A','demo/B']}))
            rows=compare(base)
            self.assertTrue(rows['aligned']);self.assertEqual(rows['source'],'local_override')
