# -*- coding: utf-8 -*-
"""Focused regression cases. Run from the tool folder: python -m unittest discover -s tests -v"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from koa_ecosystem_diag.journeys import evaluate_journeys
from koa_ecosystem_diag.interrepo_core import _load_exchanges,_find_local_refs
from koa_ecosystem_diag.framework import campaign_verdict
from koa_ecosystem_diag.api_links import check_links


class JourneyAndBoundaryTests(unittest.TestCase):
    def _records(self,root,code='200',separate=True,receiver=True,journey='fixture-e2e'):
        data=[]
        for src,tgt,ident in [('Konnaxion','Orgo','req-1'),('Orgo','Konnaxion','req-2')]:
            for phase in ['sent']+(['received'] if receiver else [])+['response']:
                data.append({'correlation_id':ident,'journey_id':journey,
                             'source':src,'target':tgt,'phase':phase,
                             'method':'GET','path':'/boundary','status':code if phase=='response' else ''})
        paths=[]
        if separate:
            for phase in ('sent','received','response'):
                name=f'{phase}.json';(root/name).write_text(json.dumps([r for r in data if r['phase']==phase]),encoding='utf-8');paths.append(name)
        else:
            (root/'combined.json').write_text(json.dumps(data),encoding='utf-8');paths=['combined.json']
        return paths

    def _journey(self,records,root):
        exchanges,_=_load_exchanges(root,records,None)
        return evaluate_journeys([{'id':'fixture-e2e','nodes':['Konnaxion','Orgo','Konnaxion']}],exchanges,[])[0]

    def test_two_independent_hop_transactions_do_not_prove_single_journey(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);result=self._journey(self._records(root),root)
            self.assertEqual(result['status'],'TRANSACTIONS_DISJOINTES')
            self.assertEqual(result['verified_hops'],0)

    def test_no_response_cannot_qualify(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);result=self._journey(self._records(root,code='500'),root)
            self.assertEqual(result['verified_hops'],0)
            self.assertEqual(result['hops'][0]['status'],'REPONSE_NON_VALIDEE')

    def test_missing_receiver_cannot_qualify(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);result=self._journey(self._records(root,receiver=False),root)
            self.assertEqual(result['verified_hops'],0)

    def test_same_export_is_not_independent(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);result=self._journey(self._records(root,separate=False),root)
            self.assertEqual(result['verified_hops'],0)
            self.assertEqual(result['hops'][0]['status'],'SOURCES_NON_INDEPENDANTES')

    def test_wrong_journey_not_falsely_matched(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);result=self._journey(self._records(root,journey='other'),root)
            self.assertEqual(result['verified_hops'],0)

    def test_explicit_api_contract_matches_both_sides_only(self):
        declared=[{'id':'a-to-b','source':'A','target':'B','method':'GET','path':'/status'}]
        calls=[{'source':'A','target':'','method':'GET','path':'/status','evidence':{'file':'client.py'}}]
        routes=[{'repo':'B','method':'GET','path':'/status','evidence':{'file':'server.py'}}]
        good=check_links(declared,calls,routes)
        self.assertEqual(good[0]['status'],'APPEL_ET_ROUTE_STATIQUES')
        self.assertEqual(check_links(declared,calls,[])[0]['status'],'APPEL_SANS_ROUTE_OBSERVEE')
        self.assertEqual(check_links(declared,[],routes)[0]['status'],'ROUTE_SANS_APPEL_OBSERVE')

    def test_external_urn_is_not_a_missing_local_file(self):
        self.assertEqual(_find_local_refs({'properties':{'a':{'$ref':'urn:konstellation:query-spec:0.2'}}}),[])
        self.assertEqual(_find_local_refs({'$ref':'./sibling.schema.json'}),['./sibling.schema.json'])

    def test_required_partial_campaign_verdict_is_partial_not_blocked(self):
        got=campaign_verdict([{'level_id':'N01','verdict':'PARTIAL'},{'level_id':'N02','verdict':'PASS'}],{'N01':True,'N02':True})
        self.assertEqual(got,'PARTIAL')

    def test_missing_required_level_stays_blocked(self):
        got=campaign_verdict([{'level_id':'N01','verdict':'BLOCKED'}],{'N01':True})
        self.assertEqual(got,'BLOCKED')


if __name__=='__main__':unittest.main()
