# -*- coding: utf-8 -*-
"""Strict passive E2E evidence, provenance, boundaries and safety regressions."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from koa_ecosystem_diag.evidence_adapters import load
from koa_ecosystem_diag.interrepo_core import _load_exchanges
from koa_ecosystem_diag.journeys import evaluate_journeys
from koa_ecosystem_diag.qualification import matrix,summary
from koa_ecosystem_diag.boundary_registry import key_for


class EvidenceV53(unittest.TestCase):
    def _files(self,root,*,ident='one-transaction',different=False,stale=False,omit_timestamp=False,owners=True):
        t=datetime.now(timezone.utc)-(timedelta(days=20) if stale else timedelta(seconds=150))
        descriptors=[]
        for n,(src,tgt) in enumerate((('A','B'),('B','C'))):
            txn='two' if different and n else ident
            for j,(phase,owner) in enumerate((('sent',src),('received',tgt),('response',tgt))):
                stamp=(t+timedelta(seconds=n*20+j*5)).isoformat()
                obj={'correlation_id':txn,'journey_id':'journey-abc','source_repo':src,
                     'target_repo':tgt,'phase':phase,'status':'200' if phase=='response' else '',
                     'method':'POST','path':'/sync'}
                if not omit_timestamp:obj['timestamp']=stamp
                path=f'{n}_{phase}.json'
                (root/path).write_text(json.dumps([obj]),encoding='utf8')
                descriptor={'path':path}
                if owners:descriptor['owner_repo']=owner
                descriptors.append(descriptor)
        return descriptors

    def _run(self,root,**kw):
        files=self._files(root,**kw)
        exchanges,errors=_load_exchanges(root,files,None)
        self.assertFalse(any(x['status']=='ECART' for x in errors))
        return evaluate_journeys([{'id':'journey-abc','nodes':['A','B','C']}],exchanges,[])[0],exchanges

    def test_single_fresh_transaction_proves_declared_two_hop_journey(self):
        with tempfile.TemporaryDirectory() as folder:
            value,exchanges=self._run(Path(folder))
            self.assertEqual(value['status'],'EVIDENCE_COMPLETE')
            self.assertEqual(value['verified_hops'],2)
            self.assertEqual(len([e for e in exchanges if e.get('provenance_attested')]),2)

    def test_separate_transactions_cannot_be_joined(self):
        with tempfile.TemporaryDirectory() as folder:
            value,_=self._run(Path(folder),different=True)
            self.assertEqual(value['status'],'TRANSACTIONS_DISJOINTES')

    def test_missing_owner_cannot_be_implicitly_attested(self):
        with tempfile.TemporaryDirectory() as folder:
            value,_=self._run(Path(folder),owners=False)
            self.assertNotEqual(value['status'],'EVIDENCE_COMPLETE')
            self.assertEqual(value['hops'][0]['status'],'PROVENANCE_NON_ATTESTEE')

    def test_undated_events_not_certified(self):
        with tempfile.TemporaryDirectory() as folder:
            value,_=self._run(Path(folder),omit_timestamp=True)
            self.assertEqual(value['hops'][0]['status'],'HORODATAGE_NON_VERIFIE')

    def test_response_from_wrong_owner_is_not_validated(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);files=self._files(root)
            for row in files:
                if 'response' in row['path']:row['owner_repo']='A'
            exchanges,_=_load_exchanges(root,files,None)
            journey=evaluate_journeys([{'id':'journey-abc','nodes':['A','B','C']}],exchanges,[])[0]
            self.assertNotEqual(journey['status'],'EVIDENCE_COMPLETE')
            self.assertEqual(journey['hops'][0]['status'],'REPONSE_NON_ATTESTEE')

    def test_stale_evidence_not_certified(self):
        with tempfile.TemporaryDirectory() as folder:
            value,_=self._run(Path(folder),stale=True)
            self.assertEqual(value['hops'][0]['status'],'PREUVE_EXPIREE')

    def test_untrusted_export_cannot_escape_target_root(self):
        with tempfile.TemporaryDirectory() as folder:
            records,errors=load(Path(folder),[{'path':'../outside.json','owner_repo':'A'}])
            self.assertEqual(records,[])
            self.assertEqual(errors[0]['status'],'ECART')

    def test_event_path_can_be_correlated_without_http_response(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            now=datetime.now(timezone.utc)
            sources=[]
            for phase,owner in [('published','A'),('consumed','B')]:
                rel=f'{phase}.json'
                (root/rel).write_text(json.dumps([{'correlation_id':'event-1',
                    'journey_id':'event-ab','source_repo':'A','target_repo':'B',
                    'phase':phase,'timestamp':now.isoformat()}]),encoding='utf8')
                sources.append({'path':rel,'owner_repo':owner})
            exchanges,_=_load_exchanges(root,sources,None)
            result=evaluate_journeys([{'id':'event-ab','nodes':['A','B'],
                'require_response':False}],exchanges,[])[0]
            self.assertEqual(result['status'],'EVIDENCE_COMPLETE')

    def test_custom_mapping_and_payload_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'custom.json').write_text(json.dumps({'events':[{'context':{'trace':'secret-trace'},
                 'actor':'A','consumer':'B','kind':'sent','payload':{'api_key':'NOT_FOR_REPORT'}}]}),encoding='utf8')
            records,errors=load(root,[{'path':'custom.json','owner_repo':'A','field_map':{
                'correlation_id':'context.trace','source_repo':'actor','target_repo':'consumer','phase':'kind'}}])
            self.assertEqual(errors[0]['status'],'LU')
            self.assertEqual(len(records),1)
            self.assertNotIn('secret-trace',str(records))
            self.assertNotIn('NOT_FOR_REPORT',str(records))

    def test_required_unreviewed_never_gains_pass(self):
        rows=[{'boundary_key':key_for('A','B',''), 'source_repo':'A','target_repo':'B','contract':'',
               'review_status':'UNREVIEWED','required':None,'protocol':'HTTP','route':'/sync'}]
        data=matrix({'relations':rows},{'exchanges':[{'source':'A','target':'B','status':'PAIRE_OBSERVEE',
                 'provenance_attested':True,'response_ok':True}], 'events':[], 'expected_api_links':[],'journeys':[]})
        self.assertEqual(data[0]['status'],'REVUE_REQUISE')
        self.assertFalse(summary(data)['global_certified'])

if __name__=='__main__':unittest.main()
