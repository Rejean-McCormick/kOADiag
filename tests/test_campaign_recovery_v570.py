from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from koa_ecosystem_diag.campaign_recovery import recovery_plan

class RecoveryTests(unittest.TestCase):
    def test_grouping_documentary_and_evidence_gaps(self):
        with TemporaryDirectory() as d:
            p=Path(d)
            (p/'scan-gaps.json').write_text(json.dumps({'repos':[{'repo':'Ekole-Quebec','oversized_files':2,
                'unreadable_files':0,'top_oversized_directories':[{'directory':'personnages','files':2}]}]}))
            (p/'documentary-scope.json').write_text(json.dumps({'documents':[{'path':'docs/changed.md','status':'DIFF'}]}))
            (p/'inventory-alignment.json').write_text(json.dumps({'aligned':False,'diag_only':['repo-a']}))
            (p/'effective_config.json').write_text(json.dumps({'interrepo':{'exchange_trace_files':[],
                'ik':{'trace_files':[]}, 'password':'not-shared'}}))
            report=recovery_plan(p)
            self.assertEqual(len(report['items']),4)
            self.assertNotIn('not-shared',json.dumps(report))
            self.assertTrue(any(x['category']=='preuves_e2e' for x in report['items']))

    def test_bad_identifier_is_not_exported(self):
        with TemporaryDirectory() as d:
            p=Path(d)
            (p/'scan-gaps.json').write_text(json.dumps({'repos':[{'repo':'secret-token=hide','oversized_files':1}]}))
            report=recovery_plan(p)
            self.assertNotIn('secret-token=hide',json.dumps(report))

if __name__=='__main__': unittest.main()
