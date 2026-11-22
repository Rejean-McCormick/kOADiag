"""Regression: declared scope and E2E proof must never be conflated."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from koa_ecosystem_diag.interrepo_core import inventory_surface
from koa_ecosystem_diag.journeys import evaluate_journeys
from koa_ecosystem_diag.qualification import matrix, summary
from koa_ecosystem_diag.boundary_registry import key_for


class ScopeMappingV531(unittest.TestCase):
    def _record(self, source, target, contract='', required=True):
        return {'boundary_key': key_for(source, target, contract),
                'source_repo': source, 'target_repo': target,
                'contract': contract, 'review_status': 'APPROVED',
                'required': required, 'protocol': 'IK'}

    def test_two_of_four_required_boundaries_are_declared_not_proven(self):
        records = [
            self._record('Konnaxion', 'Orgo', 'governance.decision.execute/1.0.0'),
            self._record('Orgo', 'Konnaxion', 'accountability.impact.publish/1.0.0'),
            self._record('EncyKlopedia', 'Daat'),
            self._record('Daat', 'Kristal-Framework'),
        ]
        declaration = {
            'id': 'konnaxion-orgo-decision-impact',
            'nodes': ['Konnaxion', 'Orgo', 'Konnaxion'],
            'contract_refs': [
                'governance.decision.execute/1.0.0',
                'accountability.impact.publish/1.0.0',
            ],
            'enabled': True, 'required': True, 'require_response': True,
        }
        journeys = evaluate_journeys([declaration], [], [], {})
        self.assertEqual(journeys[0]['status'], 'PREUVES_INSUFFISANTES')
        self.assertEqual([h['contract'] for h in journeys[0]['hops']], declaration['contract_refs'])
        rows = matrix({'relations': records}, {'journeys': journeys, 'exchanges': []})
        result = summary(rows)
        self.assertEqual(result['required'], 4)
        self.assertEqual(result['required_in_journey'], 2)
        self.assertEqual(result['required_without_journey'], 2)
        self.assertEqual(result['required_unproven'], 4)
        self.assertEqual(result['required_declared_unproven'], 2)
        self.assertEqual(result['required_proven'], 0)
        self.assertEqual([r['declared_journeys'] for r in rows], [1, 1, 0, 0])
        self.assertFalse(result['global_certified'])

    def test_different_contract_same_pair_does_not_inherit_scope(self):
        records = [
            self._record('Konnaxion', 'Orgo', 'governance.decision.execute/1.0.0'),
            self._record('Konnaxion', 'Orgo', 'other.profile/1.0.0'),
        ]
        journey = evaluate_journeys([{
            'id': 'j', 'nodes': ['Konnaxion', 'Orgo'],
            'contract_refs': ['governance.decision.execute/1.0.0'],
        }], [], [], {})
        rows = matrix({'relations': records}, {'journeys': journey, 'exchanges': []})
        self.assertEqual([r['declared_journeys'] for r in rows], [1, 0])
        self.assertEqual([r['matching_journeys'] for r in rows], [0, 0])

    def test_no_contract_refs_does_not_assign_ik_profile_by_guessing(self):
        registry = {'relations': [self._record('Konnaxion','Orgo','profile.a')]}
        journeys = evaluate_journeys([{
            'id': 'j', 'nodes': ['Konnaxion', 'Orgo']
        }], [], [], {})
        rows = matrix(registry, {'journeys': journeys, 'exchanges': []})
        self.assertEqual(rows[0]['declared_journeys'], 0)

    def test_scan_gap_metadata_only_no_code_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'boundary').mkdir();(root/'other').mkdir()
            for i in range(25):
                (root/'other'/f'piece_{i:03d}.py').write_text('value = 1\n', encoding='utf-8')
            (root/'boundary'/'service_api.py').write_text('a = "x" * 800\n',encoding='utf-8')
            data=inventory_surface('Dummy',root,{'scan':{'max_files_per_repo':20,'max_file_bytes':2048}})
            self.assertTrue(data['scan_limit_reached'])
            self.assertEqual(data['files_unselected'],6)
            self.assertEqual(data['unselected_by_root'][0]['directory'],'other')
            self.assertEqual(data['unselected_by_root'][0]['files'],6)
            self.assertNotIn('value =',str(data['unselected_by_root']))


if __name__ == '__main__':
    unittest.main()

class ContractEvidenceV531(unittest.TestCase):
    def _prepare(self, root, contract):
        import json
        from datetime import datetime, timezone, timedelta
        t = datetime.now(timezone.utc) - timedelta(seconds=120)
        exports=[]
        for i,(phase,owner) in enumerate((('sent','A'),('received','B'),('response','B'))):
            rel=f'{phase}.json'
            obj={'correlation_id':'private-opaque-correlation',
                 'journey_id':'journey-contract',
                 'source_repo':'A','target_repo':'B',
                 'phase':phase,'method':'POST','path':'/execute',
                 'timestamp':(t+timedelta(seconds=i*5)).isoformat(),
                 'status':'200' if phase=='response' else ''}
            if contract is not None:obj['contract']=contract
            (root/rel).write_text(json.dumps([obj]),encoding='utf-8')
            exports.append({'path':rel,'owner_repo':owner})
        return exports

    def test_contract_specific_journey_requires_contract_in_evidence(self):
        from koa_ecosystem_diag.interrepo_core import _load_exchanges
        from koa_ecosystem_diag.journeys import evaluate_journeys
        journey={'id':'journey-contract','nodes':['A','B'],
                 'contract_refs':['profile.alpha/1.0.0']}
        for contract,expected in [(None,'PREUVES_INSUFFISANTES'),
                                  ('profile.beta/1.0.0','PREUVES_INSUFFISANTES'),
                                  ('profile.alpha/1.0.0','EVIDENCE_COMPLETE')]:
            with self.subTest(contract=contract),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                pairs,_=_load_exchanges(root,self._prepare(root,contract),None)
                result=evaluate_journeys([journey],pairs,[])[0]
                self.assertEqual(result['status'],expected)

    def test_different_contracts_cannot_be_correlated_on_same_transaction(self):
        import json
        from datetime import datetime, timezone
        from koa_ecosystem_diag.interrepo_core import _load_exchanges
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);spec=[]
            for phase,owner,contract in [('sent','A','profile.alpha/1'),('received','B','profile.beta/1')]:
                name=phase+'.json'
                (root/name).write_text(json.dumps([{
                    'correlation_id':'id','journey_id':'test','source_repo':'A','target_repo':'B',
                    'phase':phase,'contract':contract,'timestamp':datetime.now(timezone.utc).isoformat(),
                }]),encoding='utf-8')
                spec.append({'path':name,'owner_repo':owner})
            pairs,_=_load_exchanges(root,spec,None)
            self.assertFalse(any(x.get('status')=='PAIRE_OBSERVEE' for x in pairs))
