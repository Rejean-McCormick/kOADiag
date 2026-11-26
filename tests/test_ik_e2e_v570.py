from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, Mock
from datetime import datetime, timezone, timedelta
import json
import unittest

from koa_ecosystem_diag import ik_e2e as ik


class IkE2ETests(unittest.TestCase):
    def _setup(self, root, tool, *, auth=True):
        kit = root/ik.OFFICIAL_SCRIPT
        kit.parent.mkdir(parents=True, exist_ok=True)
        kit.write_text('# official test fixture',encoding='utf-8')
        kx = root/ik.KX_ENV
        kx.parent.mkdir(parents=True, exist_ok=True)
        kx.write_text(
            f'IK_ORGO_TOKEN={self.token}\n'
            f'IK_ORGO_TARGET_ORGANIZATION={self.org_id}\n'
            f'IK_ORGO_INTERACTIONS_URL={ik.ORGO_ROUTE}\n'
            f'IK_ORGO_ALLOWED_ORGANIZATION={self.org_id}\n', encoding='utf-8')
        if auth:
            (tool/ik.TEST_AUTH_NAME).write_text(json.dumps({
                'schema':'koa.diag.ik.test-authorization.v1',
                'environment':'isolated-test','orgo_isolated_test_db':True,
                'konnaxion_isolated_test_db':True,
                'allowed_world_keys':['koadiag-test'],
                'expires_utc':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
            }), encoding='utf-8')

    org_id = '38888af4-3202-4d25-b0b3-ecc1803ec00d'
    token = 'secret-not-for-the-report-' + 'a' * 32

    def _check(self, root, tool, *, orgo_route=None, probe_status=0,
               kx_db='konnaxion_e2e', allowed_org=None, token_valid=True):
        def row(name, env, binding=None):
            return {'Name': '/' + name, 'State': {'Running': True},
                    'Config': {'Env': [f'{key}={value}' for key, value in env.items()]},
                    'NetworkSettings': {'Ports': binding or {}}}

        def bound(internal, published):
            return {f'{internal}/tcp': [{'HostIp': '127.0.0.1', 'HostPort': str(published)}]}

        orgo_db = 'postgresql://user:never-share@host.docker.internal:5432/orgo_test'
        kx_env = {'DATABASE_URL': f'postgresql://user:never-share@kx-e2e-postgres:5432/{kx_db}',
                  'IK_ORGO_TOKEN': self.token, 'IK_ORGO_TARGET_ORGANIZATION': self.org_id,
                  'IK_ORGO_INTERACTIONS_URL': ik.ORGO_ROUTE, 'KX_IK_DOCKER_E2E': '1',
                  'IK_ORGO_INBOUND_TOKEN': 'never-share-inbound',
                  'IK_ORGO_ALLOWED_ORGANIZATION': self.org_id if allowed_org is None else allowed_org}
        rows = [
            row(ik.ORGO_CONTAINERS[0], {'DATABASE_URL': orgo_db, 'KONNAXION_DECISION_LABEL': '1.11',
                                       'KONNAXION_DECISION_WORKFLOW_CODE': 'konnaxion_decision_v1'},
                bound(4000, 21111)),
            row(ik.ORGO_CONTAINERS[1], {'DATABASE_URL': orgo_db, 'KONNAXION_IK_TOKEN': 'never-share-inbound',
                                       'KONNAXION_IK_URL': orgo_route or ik.KX_ROUTE}),
            row(ik.ORGO_CONTAINERS[2], {'POSTGRES_DB': 'orgo_test'}, bound(5432, 5432)),
            row(ik.KX_CONTAINERS[0], kx_env, bound(8000, 21131)),
            row(ik.KX_CONTAINERS[1], kx_env),
            row(ik.KX_CONTAINERS[2], {'POSTGRES_DB': 'konnaxion_e2e'}),
        ]

        def runner(cmd, **kwargs):
            if cmd[1] == 'inspect':
                return Mock(returncode=0, stdout=json.dumps(rows))
            self.assertEqual(cmd[1:4], ['exec', ik.KX_CONTAINERS[1], 'python'])
            return Mock(returncode=probe_status, stdout='never-share-celery')

        with patch.object(ik, '_ports', return_value={'orgo-api': 21111, 'konnaxion-api': 21131}), \
             patch.object(ik, '_authenticated_orgo_token', return_value=token_valid):
            return ik.preflight(root, tool, world_key='koadiag-test', docker_path='docker', ps_path='pwsh',
                                http_check=lambda port, path: {'status': 'PASS', 'http_code': 200},
                                docker_call=runner)

    def test_attestation_requires_own_confirmation_and_expires(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            with self.assertRaises(PermissionError):
                ik.attest_isolated_test_environment(root,'koadiag-test','')
            path=ik.attest_isolated_test_environment(root,'koadiag-test',ik.ISOLATION_PHRASE)
            self.assertEqual(ik.test_authorization(root,'koadiag-test')['status'],'ATTESTED')
            self.assertEqual(ik.test_authorization(root,'another-world')['status'],'BLOCKED')
            self.assertNotIn('token',path.read_text(encoding='utf-8').lower())

    def test_fully_configured_readiness_never_contains_credentials(self):
        with TemporaryDirectory() as d:
            root=Path(d);tool=root/'tool';tool.mkdir();self._setup(root,tool)
            data=self._check(root,tool)
            self.assertEqual(data['result'],'READY_FOR_EXPLICIT_CONFIRMATION')
            self.assertNotIn(self.token,json.dumps(data))
            self.assertNotIn('never-share',json.dumps(data))

    def test_attestation_missing_blocks(self):
        with TemporaryDirectory() as d:
            root=Path(d);tool=root/'tool';tool.mkdir();self._setup(root,tool,auth=False)
            data=self._check(root,tool)
            self.assertEqual(data['result'],'BLOCKED')
            self.assertIn('autorisation_donnees',data['blocking_checks'])

    def test_wrong_ik_route_blocks(self):
        with TemporaryDirectory() as d:
            root=Path(d);tool=root/'tool';tool.mkdir();self._setup(root,tool)
            data=self._check(root,tool,orgo_route='http://host.docker.internal:8000/api/v3/foo')
            self.assertIn('route_orgo_vers_konnaxion',data['blocking_checks'])
            self.assertNotIn(':8000',json.dumps(data))

    def test_machine_token_probe_requires_tenant_and_scopes(self):
        required = ['signals:read', 'signals:write', 'workflows:execute', 'work:read',
                    'work:write', 'integrations:read', 'integrations:write']
        context = {'source': 'api', 'actorType': 'system', 'organizationId': self.org_id,
                   'permissions': required}
        response = Mock(status=200)
        conn = Mock()
        conn.getresponse.return_value = response
        with patch.object(ik.http.client, 'HTTPConnection', return_value=conn) as http:
            response.read.return_value = json.dumps({'data': context}).encode()
            self.assertTrue(ik._authenticated_orgo_token(21111, self.token, self.org_id))
            http.assert_called_with('127.0.0.1', 21111, timeout=5)
            request = conn.request.call_args
            self.assertEqual(request.args, ('GET', '/api/v3/auth/me'))
            self.assertEqual(request.kwargs['headers']['X-Organization-ID'], self.org_id)
            for change in ({'permissions': []}, {'source': 'session'}, {'organizationId': None}):
                response.read.return_value = json.dumps({'data': dict(context, **change)}).encode()
                self.assertFalse(ik._authenticated_orgo_token(21111, self.token, self.org_id))

    def test_celery_rejected_route_blocks_despite_good_dotenv(self):
        with TemporaryDirectory() as d:
            root=Path(d);tool=root/'tool';tool.mkdir();self._setup(root,tool)
            data = self._check(root, tool, probe_status=1)
            self.assertIn('route_konnaxion_vers_orgo', data['blocking_checks'])
            self.assertNotIn('never-share-celery', json.dumps(data))

    def test_blocks_wrong_database_wrong_return_org_and_expired_token(self):
        with TemporaryDirectory() as d:
            root=Path(d);tool=root/'tool';tool.mkdir();self._setup(root,tool)
            data = self._check(root, tool, kx_db='not_test', allowed_org='', token_valid=False)
            self.assertIn('bases_docker', data['blocking_checks'])
            self.assertIn('organisation_retour', data['blocking_checks'])
            self.assertIn('jeton_orgo', data['blocking_checks'])

    def test_import_preserves_timestamps_and_labels_terminal_provenance(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            source = root / 'terminal.txt'
            record = {'correlation_id': 'decision:1', 'decision_status': 'accepted',
                      'impact_status': 'succeeded'}
            for hop in ('decision', 'impact'):
                record[hop + '_id'] = self.org_id
                for phase in ('sent', 'received', 'response'):
                    record[f'{hop}_{phase}'] = '2026-11-25T21:00:00Z'
            source.write_text('Konnaxion test World: koadiag-test, release ID: 1.\n' +
                              ik.OBS_PREFIX + json.dumps(dict(record, secret='never-share')) + '\n' +
                              ik.PASS + '\n', encoding='utf-8')
            result = ik.import_terminal_result(source, root)
            self.assertEqual(result['source'], 'terminal_import')
            self.assertEqual(result['release_id'], 1)
            self.assertEqual(len(result['observations']['timestamps_utc']), 6)
            self.assertNotIn('never-share', Path(result['report_path']).read_text(encoding='utf-8'))
            source.write_text(ik.PASS, encoding='utf-8')
            with self.assertRaises(ValueError):
                ik.import_terminal_result(source, root)

    def test_confirmation_required_before_any_process_call(self):
        with TemporaryDirectory() as d:
            root=Path(d);tool=root/'tool';tool.mkdir();self._setup(root,tool)
            with patch.object(ik.subprocess,'run',side_effect=AssertionError('MUST NOT EXECUTE')):
                with self.assertRaises(PermissionError):
                    ik.run_e2e(root,tool,world_key='koadiag-test',confirmation='')

    def test_blocked_preflight_prevents_execution(self):
        with TemporaryDirectory() as d:
            root=Path(d);tool=root/'tool';tool.mkdir();self._setup(root,tool)
            with patch.object(ik.subprocess,'run',side_effect=AssertionError('MUST NOT EXECUTE')):
                with self.assertRaises(PermissionError):
                    ik.run_e2e(root,tool,world_key='koadiag-test',confirmation='TEST E2E',
                               preflight_func=lambda *a,**k: {'result':'BLOCKED','blocking_checks':['docker']})

    def test_official_kit_pass_marker_and_credential_redaction(self):
        with TemporaryDirectory() as d:
            root=Path(d);tool=root/'tool';tool.mkdir();self._setup(root,tool)
            pf={'result':'READY_FOR_EXPLICIT_CONFIRMATION','ports':{'orgo-api':21111},'blocking_checks':[]}
            run=Mock(return_value=Mock(returncode=0,stdout='token=real-secret\n'+ik.PASS+'\n',stderr=''))
            with patch.object(ik.shutil,'which',return_value='pwsh'):
                result=ik.run_e2e(root,tool,world_key='koadiag-test',confirmation='TEST E2E',
                                  preflight_func=lambda *a,**k:pf,run=run)
            self.assertEqual(result['verdict'],'PASS')
            self.assertNotIn('real-secret',json.dumps(result))
            txt=Path(result['report_path']).read_text(encoding='utf-8')
            self.assertNotIn('real-secret',txt)
            cmd=run.call_args.args[0]
            self.assertIn('http://127.0.0.1:21111',cmd)
            self.assertIn('-WorldKey',cmd)

    def test_no_pass_marker_even_zero_exit_is_not_success(self):
        with TemporaryDirectory() as d:
            root=Path(d);tool=root/'tool';tool.mkdir();self._setup(root,tool)
            with patch.object(ik.shutil,'which',return_value='pwsh'):
                result=ik.run_e2e(root,tool,world_key='koadiag-test',confirmation='TEST E2E',
                    preflight_func=lambda *a,**k:{'result':'READY_FOR_EXPLICIT_CONFIRMATION',
                                            'ports':{'orgo-api':21111},'blocking_checks':[]},
                    run=lambda *a,**k:Mock(returncode=0,stdout='not finished',stderr=''))
            self.assertEqual(result['verdict'],'FAIL')

if __name__=='__main__': unittest.main()
