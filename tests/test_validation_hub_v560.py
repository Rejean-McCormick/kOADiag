from __future__ import annotations
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch

from koa_ecosystem_diag import validation_hub as v


def fake_ports():
    services = [
        {'id': 'orgo-api', 'owner': 'orgo', 'port': 21111, 'tcp': True, 'http_code': 404,
         'status': 'HTTP_UNVERIFIED', 'detail': 'API répond'},
        {'id': 'orgo-web', 'owner': 'orgo', 'port': 21110, 'tcp': True, 'http_code': 200,
         'status': 'FAMILY_MATCH', 'detail': 'famille'},
        {'id': 'konnaxion-web', 'owner': 'konnaxion', 'port': 21130, 'tcp': False,
         'status': 'STOPPED', 'detail': 'fermé'},
        {'id': 'konnaxion-api', 'owner': 'konnaxion', 'port': 21131, 'tcp': False,
         'status': 'STOPPED', 'detail': 'fermé'},
        {'id': 'initkoa-web', 'owner': 'initkoa', 'port': 21120, 'tcp': False,
         'status': 'STOPPED', 'detail': 'fermé'},
    ]
    return {'services': services, 'registry_sha256': 'test-sha',
            'endpoint_pairs': [
                {'name':'IK Orgo -> Konnaxion','source':'orgo-api','target':'konnaxion-api',
                 'source_tcp':True,'target_tcp':False,'status':'ENDPOINTS_INDISPONIBLES', 'e2e_proven':False},
                {'name':'Audit kOA -> HomePage','source':'initkoa-web','target':'initkoa-web',
                 'source_tcp':False,'target_tcp':False,'status':'ENDPOINTS_INDISPONIBLES', 'e2e_proven':False},
            ]}


class ValidationHubTests(unittest.TestCase):
    def test_quick_is_readonly_and_never_calls_deep(self):
        with TemporaryDirectory() as folder, patch.object(v.c0, 'check_all', return_value=fake_ports()) as scan, \
             patch.object(v, '_passive_campaign', side_effect=AssertionError('should not run')):
            result=v.validate(Path(folder), mode='rapide')
            self.assertEqual(result['summary']['services_accessibles'], 2)
            self.assertEqual(result['summary']['services_essentiels_accessibles'], 2)
            self.assertEqual(result['summary']['verdict'], 'PARTIEL')
            self.assertEqual(result['summary']['transactions_e2e_executees'], 0)
            self.assertEqual(result['links'][1]['status'], 'NON_TESTABLE')
            self.assertEqual(result['links'][0]['status'], 'EXTREMITES_INDISPONIBLES')
            self.assertEqual(result['health'], [])
            scan.assert_called_once()

    def test_deep_runs_existing_campaign_in_safe_mode(self):
        seen=[]
        with TemporaryDirectory() as folder, patch.object(v.c0,'check_all',return_value=fake_ports()), \
             patch.object(v,'health_probe',side_effect=lambda s: {'id':s['id'],'status':'NON_CONFIGURE'}):
            result=v.validate(Path(folder),mode='approfondie',tool=Path(folder),
                     deep_runner=lambda r: {'verdict':'PASS'},progress=seen.append)
            self.assertEqual(result['campaign']['verdict'],'PASS')
            self.assertEqual(len(result['health']),5)
            self.assertEqual(result['summary']['verdict'],'PARTIEL')
            self.assertTrue(any('LevelUpDiag' in line for line in seen))

    def test_false_healthy_wrong_identity(self):
        original=fake_ports()
        original['services'][1]['status']='WRONG_SERVICE'
        original['services'][2]['tcp']=True
        original['services'][3]['tcp']=True
        original['services'][4]['tcp']=True
        original['endpoint_pairs'][0]['target_tcp']=True
        links=v.diagnose_links(original)
        s=v.summarize(original,links,[],'rapide')
        self.assertEqual(s['verdict'],'ECART')

    def test_health_unrecognized_not_a_success(self):
        h=v.health_probe({'id':'unknown','port':21145,'tcp':True})
        self.assertEqual(h['status'],'NON_CONFIGURE')

    def test_reports_round_trip(self):
        with TemporaryDirectory() as folder, patch.object(v.c0,'check_all',return_value=fake_ports()):
            r=v.validate(Path(folder))
            path=v.save_report(r,Path(folder)/'out')
            self.assertTrue((path/'validation.json').is_file())
            self.assertTrue((path/'applications.csv').is_file())
            self.assertTrue((path/'connexions.csv').is_file())
            self.assertTrue((path/'synthese.txt').is_file())
            parsed=json.loads((path/'validation.json').read_text(encoding='utf-8'))
            self.assertEqual(parsed['summary']['services_accessibles'],2)

    def test_campaign_invoked_with_no_destructive_flags(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'Diagnostic-kOA-Digital-Ecosystem-CLI.py').write_text('# test')
            from unittest.mock import Mock
            captured=[]
            def invoke(args, **kw):
                captured.extend(args)
                return Mock(stdout='VERDICT=WARN\n',returncode=10)
            with patch.object(v.subprocess, 'run', side_effect=invoke):
                response=v._passive_campaign(root,root)
            self.assertEqual(response['verdict'],'ERROR') # no summary cannot mean success
            self.assertIn('validation-integrale',captured)
            for disallowed in ('--runtime-local','--network','--remote','--audit','--start-test-stack'):
                self.assertNotIn(disallowed,captured)


if __name__=='__main__': unittest.main()
