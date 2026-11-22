import unittest

from koa_ecosystem_diag.closure import assess
from koa_ecosystem_diag.qualification import matrix


class ClosureTests(unittest.TestCase):
    def test_one_mode_never_fills_the_other(self):
        levels = [{'id': 'N13', 'verdict': 'PASS'}]
        summary = {'run_id': 'r1', 'suite_version': '5.4.2', 'levels': levels,
                   'expected_levels': ['N13'], 'verdict': 'PASS'}
        boundary = {'kind': 'frontiere', 'id': 'ab', 'required': True, 'mode': 'autonome',
                    'verdict': 'PASS', 'status': 'PARCOURS_CORROBORE'}
        validation = {'documentary_aligned': True, 'collection_available': True, 'cases': [boundary]}
        result = assess(summary, validation)
        self.assertEqual(result['status'], 'VALIDATIONS_RESTANTES')
        validation['cases'].append(dict(boundary, mode='integre', verdict='PARTIAL', status='PREUVE_MANQUANTE'))
        result = assess(summary, validation)
        self.assertEqual(result['remaining_counts'], {'frontiere': 1})
        self.assertEqual(result['remaining'][0]['mode'], 'integre')
        validation['cases'][1]['verdict'] = 'PASS'
        result = assess(summary, validation)
        self.assertEqual(result['status'], 'PRET_POUR_REVUE_FINALE')
        self.assertEqual(result['certification'], 'DECISION_HUMAINE')

    def test_historical_boundary_uses_exact_validated_contract(self):
        row = {'boundary_key': 'ab', 'source_repo': 'A', 'target_repo': 'B',
               'review_status': 'APPROVED', 'required': True, 'protocol': 'OTHER', 'contract': ''}
        historical = {'historical_contract': 'kristal_state/6.0.0', 'status': 'REFERENCE_FIGEE_VALIDEE'}
        scope = {'obligations': [{'boundary_key': 'ab', 'technical_reconciliation': historical}]}
        hop = {'source': 'A', 'target': 'B', 'contract': '', 'status': 'FRONTIERE_CORROBOREE'}
        snapshot = {'documentary_scope': scope, 'journeys': [
            {'status': 'EVIDENCE_COMPLETE', 'mode': 'autonome', 'hops': [hop]}]}
        self.assertEqual(matrix({'relations': [row]}, snapshot)[0]['verdict'], 'PARTIAL')
        hop['contract'] = historical['historical_contract']
        self.assertEqual(matrix({'relations': [row]}, snapshot)[0]['verdict'], 'PASS')
        historical['status'] = 'REFERENCE_FIGEE_ABSENTE'
        self.assertEqual(matrix({'relations': [row]}, snapshot)[0]['verdict'], 'PARTIAL')
