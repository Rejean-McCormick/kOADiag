from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from koa_ecosystem_diag.app_suite_catalog import discover

class SuiteDiscoveryTests(unittest.TestCase):
    def test_only_script_names_not_commands_and_never_runs(self):
        with TemporaryDirectory() as d:
            r=Path(d)
            proj=r/'Orgo'/'Orgo';proj.mkdir(parents=True)
            (proj/'package.json').write_text(json.dumps({'scripts':{
                'test':'echo password=secret', 'dev':'next dev', 'lint':'secret-command'}
            }),encoding='utf-8')
            rows=discover(r)
            owner=[x for x in rows if x['owner']=='orgo']
            self.assertEqual({r['entry'] for r in owner},{'test','lint'})
            self.assertNotIn('secret-command',json.dumps(rows))
            self.assertTrue(any(x['status']=='ABSENT' for x in rows))

if __name__=='__main__':unittest.main()
