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
        orgo = root/ik.ORGO_DIR/'.env'
        orgo.write_text('POSTGRES_PASSWORD=never-share\nKONNAXION_IK_URL=http://host.docker.internal:21131/api/integrations/ik/konnaxion/interactions/\n',encoding='utf-8')
        kx=root/ik.KONNAXION_DIR/'backend/.envs/.local/.django'
        kx.parent.mkdir(parents=True,exist_ok=True)
        kx.write_text('IK_ORGO_TOKEN=super-secret\nIK_ORGO_TARGET_ORGANIZATION=orgo\nIK_ORGO_INTERACTIONS_URL=http://host.docker.internal:21111/api/v3/ik/interactions\n',encoding='utf-8')
        (root/ik.ORGO_DIR/ik.ORGO_COMPOSE).write_text('services: {}')
        (root/ik.KONNAXION_DIR/'backend'/ik.KX_COMPOSE).write_text('services: {}')
        if auth:
            (tool/ik.TEST_AUTH_NAME).write_text(json.dumps({
                'schema':'koa.diag.ik.test-authorization.v1',
                'environment':'isolated-test','orgo_isolated_test_db':True,
                'konnaxion_isolated_test_db':True,
                'allowed_world_keys':['koadiag-test'],
                'expires_utc':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
            }), encoding='utf-8')

    def _check(self, root, tool):
        def runner(cmd, **kw):
            return Mock(returncode=0,stdout=('postgres\napi\nworker\n' if 'Orgo' in str(kw['cwd'])
                else 'redis\ndjango\nceleryworker\n'),stderr='')
        with patch.object(ik,'_ports',return_value={'orgo-api':21111,'konnaxion-api':21131}):
            return ik.preflight(root,tool,world_key='koadiag-test',docker_path='docker',ps_path='pwsh',
                                http_check=lambda port,path:{'status':'PASS','http_code':200},docker_call=runner)

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
            self.assertNotIn('super-secret',json.dumps(data))
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
            f=root/ik.ORGO_DIR/'.env'
            f.write_text('POSTGRES_PASSWORD=abc\nKONNAXION_IK_URL=http://host.docker.internal:8000/api/v3/foo\n')
            data=self._check(root,tool)
            self.assertIn('route_orgo_vers_konnaxion',data['blocking_checks'])
            self.assertNotIn(':8000',json.dumps(data))

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
