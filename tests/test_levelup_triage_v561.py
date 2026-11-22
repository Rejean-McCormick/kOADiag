from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch, Mock

from koa_ecosystem_diag import levelup_triage, validation_hub


class LevelUpTriageTests(unittest.TestCase):
    def _campaign(self, root):
        folder = root/'reports'/'Diagnostic-kOA-Digital-Ecosystem'/'runs'/'20261120T154115Z-demo'
        (folder/'levels'/'N01').mkdir(parents=True)
        (folder/'levels'/'N14').mkdir(parents=True)
        meta = {'schema':'levelupdiag.campaign-summary.v2','run_id':folder.name,
                'verdict':'PARTIAL', 'levels':[{'id':'N01','name':'Collecte','verdict':'PARTIAL'},
                {'id':'N14','name':'E2E','verdict':'SKIP'}],
                'coverage':{'inventory':{'oversized_files':10,'unreadable_files':0,'present':55,'declared':55},
                            'traces':{'correlated_pairs':0,'ik_receipts':0},
                            'boundary_evidence':{'required_unproven':4},
                            'journeys':{'not_proven':1},
                            'boundary_registry':{'new_or_unreviewed':25},
                            'inventory_alignment':{'aligned':False,'diag_count':53,'audit_count':49}},
                'validation_integrale':{'required_pass':51,'required_total':65}}
        (folder/'summary.json').write_text(json.dumps(meta),encoding='utf-8')
        (folder/'effective_config.json').write_text(json.dumps({'interrepo':{
            'exchange_trace_files':[], 'ik':{'trace_files':[]}, 'SECRET':'must-not-leak'}}),encoding='utf-8')
        for level, verdict in [('N01','PARTIAL'),('N14','SKIP')]:
            (folder/'levels'/level/'result.json').write_text(json.dumps({
                'schema':'levelupdiag.report.v2', 'level_id':level,'run_id':folder.name,
                'findings':[{'id':'sample','verdict':verdict,'category':'scope',
                             'message':'password=super-secret http://example.test'},
                            {'id':'pass','verdict':'PASS','message':'OK'}]}), encoding='utf-8')
        return folder/'summary.json'

    def test_root_causes_grounded_no_fake_e2e(self):
        with TemporaryDirectory() as directory:
            base=Path(directory);path=self._campaign(base)
            data=levelup_triage.interpret_report(path,trusted_reports_root=base/'reports')
            ids={x['id'] for x in data['causes']}
            self.assertTrue({'COLLECTE_INCOMPLETE','FRONTIERES_NON_PROUVEES',
                 'PREUVES_TRACES_ABSENTES','E2E_OFFICIEL_NON_EXECUTE','INVENTAIRES_DIVERGENTS'} <= ids)
            self.assertEqual(data['requis_pass'],51)
            self.assertEqual(data['requis_total'],65)
            self.assertEqual(data['verdict_source'],'PARTIAL')
            self.assertEqual(data['sources_configurees']['exchange_trace_files'],0)
            self.assertNotIn('super-secret', json.dumps(data))
            self.assertNotIn('must-not-leak', json.dumps(data))

    def test_wrong_root_or_mismatched_level_not_read(self):
        with TemporaryDirectory() as directory:
            base=Path(directory);path=self._campaign(base)
            with self.assertRaises(ValueError):
                levelup_triage.interpret_report(path,trusted_reports_root=base/'invalid')
            r=path.parent/'levels'/'N01'/'result.json'
            data=json.loads(r.read_text(encoding='utf-8'));data['run_id']='wrong'
            r.write_text(json.dumps(data),encoding='utf-8')
            got=levelup_triage.interpret_report(path,trusted_reports_root=base/'reports')
            self.assertEqual(got['niveaux'][0]['erreur_lecture'],'ValueError')

    def test_campaign_reports_round_trip(self):
        with TemporaryDirectory() as directory:
            base=Path(directory);path=self._campaign(base)
            triage=levelup_triage.interpret_report(path)
            result={'schema':'koa.diag.validation.hub.v1',
                    'summary':{'mode':'approfondie','verdict':'PARTIEL','services_essentiels_accessibles':5,
                               'services_essentiels_total':5,'services_accessibles':5,'port_count':21,
                               'liaisons_extremites_accessibles':2,'liaisons_declarees':6,
                               'precision':'aucun E2E'},
                    'services':[], 'links':[], 'campaign':{'verdict':'PARTIAL','triage':triage}}
            out=validation_hub.save_report(result,base/'exports')
            self.assertTrue((out/'causes.csv').exists())
            self.assertTrue((out/'niveaux.csv').exists())
            self.assertIn('51/65', (out/'synthese.txt').read_text(encoding='utf-8'))

    def test_passive_campaign_does_not_launch_e2e(self):
        with TemporaryDirectory() as directory:
            base=Path(directory);path=self._campaign(base)
            (base/'Diagnostic-kOA-Digital-Ecosystem-CLI.py').write_text('# test',encoding='utf-8')
            with patch.object(validation_hub.subprocess,'run',return_value=Mock(
                    stdout='RUN_ROOT='+str(path.parent)+'\nVERDICT=PARTIAL\n', returncode=21)) as runner:
                result=validation_hub._passive_campaign(base,base)
            self.assertEqual(result['verdict'],'PARTIAL')
            self.assertEqual(len(result['triage']['causes']),7)
            args=runner.call_args.args[0]
            for flag in ('--runtime-local','--network','--remote','--start-test-stack'):
                self.assertNotIn(flag,args)

if __name__=='__main__':unittest.main()
