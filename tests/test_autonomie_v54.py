"""Proof qualification regressions for v5.4."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import unittest

from koa_ecosystem_diag import boundary_registry
from koa_ecosystem_diag.evidence_adapters import load
from koa_ecosystem_diag.ik_diag_core import profile_tree
from koa_ecosystem_diag.interrepo_core import _load_exchanges, inventory_surface
from koa_ecosystem_diag.journeys import evaluate_journeys
from koa_ecosystem_diag.native_evidence import observation
from koa_ecosystem_diag.qualification import matrix, summary
from koa_ecosystem_diag.revisions import resolve_revisions

REV = {'A': 'a'*40, 'B': 'b'*40, 'C': 'c'*40}
POLICY = {'strict_evidence': True, 'reference_revisions': REV}
JOURNEY = {'id': 'demonstration', 'nodes': ['A', 'B', 'C'], 'contract_refs': ['handoff/1', 'return/1']}


class EvidenceV54(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.stamp = datetime.now(timezone.utc) - timedelta(minutes=10)

    def export(self, name, records, owner='', **options):
        content = json.dumps(records).encode()
        (self.root / name).write_bytes(content)
        return {'path': name, 'owner_repo': owner, 'sha256': sha256(content).hexdigest(), **options}

    def sources(self, alter=None):
        result = []
        for n, (src, dst, contract) in enumerate((('A', 'B', 'handoff/1'), ('B', 'C', 'return/1'))):
            for i, (phase, owner) in enumerate((('sent', src), ('received', dst), ('response', dst))):
                row = {'correlation_id': 'transaction-1', 'journey_id': JOURNEY['id'],
                       'attempt_id': f'attempt-{n}', 'source_repo': src, 'target_repo': dst,
                       'contract': contract, 'method': 'POST', 'path': '/handoff',
                       'source_revision': REV[src], 'target_revision': REV[dst],
                       'phase': phase, 'status': 200 if phase == 'response' else '',
                       'timestamp': (self.stamp + timedelta(seconds=10*n+i)).isoformat()}
                options = {'mode': 'autonome'}
                if alter:
                    alter(n, i, row, options)
                result.append(self.export(f'{n}-{i}.json', [row], owner, **options))
        return result

    def evaluate(self, sources):
        exchanges, findings = _load_exchanges(self.root, sources, set(REV), policy=POLICY)
        result = evaluate_journeys([JOURNEY], exchanges, [], POLICY)[0]
        return result, exchanges, findings

    def test_single_revision_bound_transaction(self):
        result, pairs, _ = self.evaluate(self.sources())
        self.assertEqual(result['status'], 'EVIDENCE_COMPLETE')
        self.assertEqual(result['mode'], 'autonome')
        self.assertEqual(result['verified_hops'], 2)
        self.assertTrue(all(x['evidence_sha256'] for x in result['hops']))
        self.assertTrue(all(x['revision_status'] == 'ALIGNEE' for x in pairs))

    def test_modes_cannot_be_joined(self):
        def alter(n, i, row, options):
            if n:
                options['mode'] = 'integre'
        result, _, _ = self.evaluate(self.sources(alter))
        self.assertEqual(result['status'], 'TRANSACTIONS_DISJOINTES')

    def test_integrated_transaction_can_be_proven_separately(self):
        def alter(n, i, row, options):
            options['mode'] = 'integre'
        result, _, _ = self.evaluate(self.sources(alter))
        self.assertEqual(result['status'], 'EVIDENCE_COMPLETE')
        self.assertEqual(result['mode'], 'integre')

    def test_response_from_other_attempt_cannot_complete_hop(self):
        def alter(n, i, row, options):
            if n == 0 and i == 2:
                row['attempt_id'] = 'attempt-retry'
        result, _, _ = self.evaluate(self.sources(alter))
        self.assertEqual(result['hops'][0]['status'], 'REPONSE_NON_VALIDEE')

    def test_changed_revision_cannot_prove_hop(self):
        def alter(n, i, row, options):
            if n == 0:
                row['target_revision'] = 'e'*40
        result, _, _ = self.evaluate(self.sources(alter))
        self.assertEqual(result['hops'][0]['status'], 'REVISION_INCOMPATIBLE')

    def test_accepted_response_not_terminal(self):
        def alter(n, i, row, options):
            if n == 0 and i == 2:
                row['status'] = 202
        result, _, _ = self.evaluate(self.sources(alter))
        self.assertEqual(result['hops'][0]['status'], 'REPONSE_NON_TERMINALE')

    def test_digest_mismatch_rejects_entire_export(self):
        files = self.sources()
        (self.root / files[1]['path']).write_text('[]')
        result, _, findings = self.evaluate(files)
        self.assertNotEqual(result['status'], 'EVIDENCE_COMPLETE')
        self.assertEqual(findings[1]['status'], 'ECART')

    def test_bad_jsonl_tail_does_not_import_prefix(self):
        raw = b'{"correlation_id":"txn","source_repo":"A","target_repo":"B","phase":"sent"}\n{invalid'
        (self.root / 'bad.jsonl').write_bytes(raw)
        rows, findings = load(self.root, ['bad.jsonl'])
        self.assertEqual(rows, [])
        self.assertEqual(findings[0]['status'], 'ECART')

    def test_journal_integrity_and_private_projection(self):
        row = b'{"sequence":1,"record":{"correlation_id":"tx-secret","bounded_payload":{"private":"private"}}}\n'
        common = {'journal_version': '1.0.0', 'export_id': 'test', 'record_count': 1,
                  'records_sha256': sha256(row).hexdigest()}
        header = dict(common, record_type='header', field_allowlist=['correlation_id', 'bounded_payload'])
        trailer = dict(common, record_type='trailer')
        raw = json.dumps(header).encode() + b'\n' + row + json.dumps(trailer).encode() + b'\n'
        value = observation('koa-linux-journal', raw, None)
        self.assertEqual(value['correlated'], 1)
        self.assertNotIn('private', str(value))
        self.assertNotIn('tx-secret', str(value))
        with self.assertRaises(ValueError):
            observation('koa-linux-journal', raw.replace(b'tx-secret', b'tx-changed'), None)

    def test_koali_readiness_is_complementary(self):
        data = {'schema': 'levelupdiag.campaign-summary.v2', 'run_id': 'test', 'diagnostic_mode': 'qualification',
                'started_at': self.stamp.isoformat(), 'ended_at': self.stamp.isoformat(), 'verdict': 'PASS',
                'expected_levels': ['N12'], 'levels': [{'id': 'N12', 'verdict': 'PASS'}]}
        spec = self.export('koali.json', data, 'LevelUpDiag-kOA-Linux', format='koali-summary', mode='integre')
        result, pairs, findings = self.evaluate([spec])
        self.assertEqual(findings[0]['readiness_n12'], 'PASS')
        self.assertEqual(pairs, [])
        self.assertEqual(result['verified_hops'], 0)

    def test_registry_observation_does_not_write_human_state(self):
        view, new = boundary_registry.synchronize(self.root, [{'source': 'A', 'target': 'B'}], persist=False)
        self.assertEqual(new, 1)
        self.assertEqual(view['relations'][0]['review_status'], 'UNREVIEWED')
        self.assertFalse(boundary_registry.path_for(self.root).exists())

    def test_gap_is_exact_and_required_scope_remains_unproven(self):
        (self.root / 'contracts').mkdir()
        (self.root / 'contracts' / 'Big.json').write_text(' ' * 5000)
        surface = inventory_surface('A', self.root, {'scan': {'max_file_bytes': 2048}})
        self.assertIn({'path': 'contracts/Big.json', 'reason': 'TAILLE'}, surface['boundary_scan_gaps'])
        entry = {'boundary_key': 'x', 'source_repo': 'A', 'target_repo': 'B', 'contract': '',
                 'required': True, 'review_status': 'APPROVED', 'observed': False}
        rows = matrix({'relations': [entry]}, {'repositories': [{'repo': 'A', 'exists': True}]}, POLICY)
        self.assertEqual(rows[0]['status'], 'DEPOT_ABSENT_DU_PERIMETRE')
        self.assertFalse(summary(rows, {'aligned': True})['required_scope_complete'])

    def test_checkout_revision_precedes_configuration(self):
        git = self.root / '.git'
        git.mkdir()
        (git / 'HEAD').write_text('ref: refs/heads/main\n')
        (git / 'packed-refs').write_text(f"{REV['A']} refs/heads/main\n")
        revisions, findings = resolve_revisions({'a': {'path': self.root, 'name': 'A'}}, {'A': REV['B']})
        self.assertEqual(revisions['A'], REV['A'])
        self.assertTrue(findings[0]['configuration_mismatch'])


@unittest.skipUnless(os.environ.get('KOA_REFERENCE_IK'), 'Snapshot Interaction Kernel non indiqué')
class OfficialProfilesV54(unittest.TestCase):
    def test_active_profiles_and_adopted_locks(self):
        profiles, findings = profile_tree(Path(os.environ['KOA_REFERENCE_IK']))
        self.assertGreaterEqual(len(profiles), 3)
        self.assertTrue(all(row['status'] == 'OK' for row in findings))
        self.assertEqual(sum(row['name'].startswith('Verrou adopté:') for row in findings), 6)
        self.assertEqual(profiles['governance.decision.execute', '1.0.0']['native_validation'], 'VALIDE')


    @unittest.skipUnless(os.environ.get('KOA_TEST_NATIVE_RUNTIME'), 'Runtime Python IK non installé')
    def test_official_trace_admission(self):
        from koa_ecosystem_diag.native_evidence import ik_trace_validator
        from interaction_kernel import IKError
        root = Path(os.environ['KOA_REFERENCE_IK'])
        profiles, _ = profile_tree(root)
        validator = ik_trace_validator(root / 'contracts', profiles)
        vector = json.loads((root / 'tck/fingerprint/vectors.json').read_text())
        envelope = vector['vectors'][0]['envelope']
        validator.validate_envelope(envelope)
        envelope.pop('target')
        with self.assertRaises(IKError):
            validator.validate_envelope(envelope)


@unittest.skipUnless(os.environ.get('KOA_REFERENCE_LINUX'), 'Snapshot kOA Linux non indiqué')
class OfficialReceiptV54(unittest.TestCase):
    def test_native_receipt_schema_and_invalid_correlation(self):
        root = Path(os.environ['KOA_REFERENCE_LINUX'])
        now = datetime.now(timezone.utc).isoformat()
        receipt = {
            'schema_version': '1.0.0', 'receipt_id': 'receipt:test:001',
            'receipt_schema_version': '1.0.0', 'receipt_class': 'transition_receipt',
            'transition_type': 'test_state_change', 'producer_component_id': 'test_component',
            'subject_ref': 'subject:test:001', 'actor_ref': 'service:test-client',
            'target_refs': ['target:test:001'], 'scope': {'kind': 'component', 'id': 'test_component'},
            'requested_action': 'test_state_change',
            'correlation': {'schema_version': '1.0.0', 'correlation_id': 'test:correlation'},
            'authority_refs': ['decision:test:001'], 'decision': 'authorized',
            'execution_state': 'completed', 'commit_state': 'committed', 'outcome': 'committed',
            'requested_at': now, 'completed_at': now, 'committed_at': now, 'recorded_at': now,
            'reason_codes': [], 'component_contract_refs': ['docs/contracts/test.json'],
            'disclosure_class': 'operator_restricted', 'retention_class': 'operational',
        }
        value = observation('koa-linux-receipt', json.dumps(receipt).encode(), root)
        self.assertEqual(value['correlated'], 1)
        del receipt['correlation']['schema_version']
        with self.assertRaises(ValueError):
            observation('koa-linux-receipt', json.dumps(receipt).encode(), root)


if __name__ == '__main__':
    unittest.main()
