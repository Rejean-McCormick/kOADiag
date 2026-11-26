# -*- coding: utf-8 -*-
"""Separate, guarded Konnaxion–Orgo IK E2E orchestration.

Read-only preflight is safe to run. The transactional path is NEVER invoked by
quick/deep validation: it needs a fresh user attestation, named test World,
explicit phrase, healthy local APIs and the official owner-maintained kit.
This module does not create, modify, or print private .env files.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit
import hashlib
import os
import tempfile
import http.client
import json
import re
import shutil
import subprocess
import uuid

from . import port_diagnostics as c0

OFFICIAL_SCRIPT = Path('Orgo/Orgo/validation/konnaxion-orgo-ik/run-e2e.ps1')
ORGO_DIR = Path('Orgo/Orgo')
KONNAXION_DIR = Path('Konnaxion/Konnaxion')
KX_ENV = KONNAXION_DIR / 'backend/.envs/.local/.django'
ORGO_ROUTE = 'http://host.docker.internal:21111/api/v3/ik/interactions'
KX_ROUTE = 'http://host.docker.internal:21131/api/integrations/ik/konnaxion/interactions/'
ORGO_CONTAINERS = ('orgo-ik-test-api-1', 'orgo-ik-test-worker-1', 'orgo-test-postgres')
KX_CONTAINERS = ('konnaxion_local_django', 'konnaxion_local_celeryworker', 'backend-kx-e2e-postgres-1')
PASS = 'KONNAXION <-> ORGO IK E2E PASS'
WORLD_RE = re.compile(r'[a-z0-9][a-z0-9_-]{0,127}\Z')
CONFIRM_PHRASE = 'TEST E2E'
ISOLATION_PHRASE = 'BASES DE TEST ISOLEES'
OBS_PREFIX = 'KOA_OBSERVATIONS='
TEST_AUTH_NAME = 'ik-e2e-test-authorization.local.json'
SCHEMA = 'koa.diag.ik.e2e.v1'


def _http_ok(port: int, route: str, timeout=4) -> dict:
    if type(port) is not int or not 21100 <= port <= 21199:
        return {'status': 'BLOCKED', 'reason': 'Port hors du registre'}
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=timeout)
    try:
        conn.request('GET', route, headers={'Connection': 'close', 'User-Agent': 'kOADiag-IK/5.7'})
        r = conn.getresponse()
        r.read(128)
        return {'status': 'PASS' if r.status == 200 else 'WARN', 'http_code': r.status}
    except (OSError, TimeoutError, http.client.HTTPException) as exc:
        return {'status': 'BLOCKED', 'reason': type(exc).__name__}
    finally:
        conn.close()


def _read_kx_env(path: Path) -> dict:
    """Match the owner's PowerShell dotenv reader. Never include values in reports."""
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 200_000:
        return {}
    values = {}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        key, sep, value = line.partition('=')
        if sep and key in ('IK_ORGO_TOKEN', 'IK_ORGO_TARGET_ORGANIZATION',
                           'IK_ORGO_INTERACTIONS_URL', 'IK_ORGO_ALLOWED_ORGANIZATION'):
            values[key] = value.strip().strip('"').strip("'")
    return values


def _docker(docker, args, root, call):
    fn = call or subprocess.run
    return fn([docker, *args], cwd=str(root), stdin=subprocess.DEVNULL,
              capture_output=True, text=True, encoding='utf-8', errors='replace',
              timeout=15, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def _running_containers(docker, names, root, call=None):
    try:
        result = _docker(docker, ['inspect', '--type', 'container', *names], root, call)
        # Docker can return the objects it found even if another name is missing.
        rows = json.loads(result.stdout)
        return {row['Name'].lstrip('/'): row for row in rows
                if row['State'].get('Running') is True}
    except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.TimeoutExpired):
        return {}


def _container_env(row):
    return dict(value.split('=', 1) for value in row.get('Config', {}).get('Env', [])
                if '=' in value)


def _bound(row, port, published):
    bindings = row.get('NetworkSettings', {}).get('Ports', {}).get(f'{port}/tcp') or []
    return any(item.get('HostIp') == '127.0.0.1' and item.get('HostPort') == str(published)
               for item in bindings)


def _db_matches(env, host, name):
    try:
        url = urlsplit(env.get('DATABASE_URL', ''))
        return (url.scheme in ('postgres', 'postgresql') and url.hostname == host
                and url.port in (None, 5432) and url.path == '/' + name)
    except ValueError:
        return False


def _uuid(value):
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _authenticated_orgo_token(port, token, organization):
    if port != 21111 or not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', token):
        return False
    required = {'signals:read', 'signals:write', 'workflows:execute', 'work:read',
                'work:write', 'integrations:read', 'integrations:write'}
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
    try:
        conn.request('GET', '/api/v3/auth/me', headers={
            'Authorization': 'Bearer ' + token, 'X-Organization-ID': organization,
            'Connection': 'close',
        })
        response = conn.getresponse()
        if response.status != 200:
            return False
        context = json.loads(response.read(8192))['data']
        return (context.get('source') == 'api' and context.get('actorType') == 'system'
                and _uuid(context.get('organizationId')) == organization
                and required.issubset(context.get('permissions', [])))
    except (OSError, ValueError, TypeError, KeyError, AttributeError, http.client.HTTPException):
        return False
    finally:
        conn.close()


def runtime_checks(root: Path, docker, ports, *, call=None) -> list[dict]:
    """Inspect the prepared isolated stacks, without starting or changing Docker."""
    checks = []

    def check(key, ok, good, bad):
        checks.append({'id': key, 'status': 'PASS' if ok else 'BLOCKED',
                       'detail': good if ok else bad})

    if not docker:
        check('docker', False, '', 'Docker CLI absent')
        return checks

    rows = _running_containers(docker, (*ORGO_CONTAINERS, *KX_CONTAINERS), root, call)
    orgo_api, orgo_worker, orgo_db, django, celery, kx_db = (
        rows.get(name, {}) for name in (*ORGO_CONTAINERS, *KX_CONTAINERS)
    )
    api, worker, django_env, celery_env, pg_orgo, pg_kx = map(
        _container_env, (orgo_api, orgo_worker, django, celery, orgo_db, kx_db)
    )
    orgo_ready = bool(orgo_api and orgo_worker and orgo_db and ports.get('orgo-api') and
                      _bound(orgo_api, 4000, ports['orgo-api']))
    kx_ready = bool(django and celery and kx_db and ports.get('konnaxion-api') and
                    _bound(django, 8000, ports['konnaxion-api']))
    check('docker_orgo', orgo_ready, 'Projet isolé orgo-ik-test et PostgreSQL de test détectés',
          'API ou worker orgo-ik-test, PostgreSQL de test ou publication C0 indisponible')
    check('docker_konnaxion', kx_ready, 'Django, Celery et PostgreSQL E2E détectés',
          'Django, Celery, PostgreSQL E2E ou publication C0 indisponible')
    check('bases_docker', all(_db_matches(env, 'host.docker.internal', 'orgo_test') for env in (api, worker))
          and all(_db_matches(env, 'kx-e2e-postgres', 'konnaxion_e2e') for env in (django_env, celery_env))
          and _bound(orgo_db, 5432, 5432)
          and pg_orgo.get('POSTGRES_DB') == 'orgo_test' and pg_kx.get('POSTGRES_DB') == 'konnaxion_e2e',
          'Cibles Docker conformes : orgo_test et konnaxion_e2e',
          'Cibles PostgreSQL isolées non confirmées')

    try:
        local = _read_kx_env(root / KX_ENV)
    except (OSError, UnicodeError):
        local = {}
    token = local.get('IK_ORGO_TOKEN')
    org_id = _uuid(local.get('IK_ORGO_TARGET_ORGANIZATION'))
    kx_services = (django_env, celery_env)
    env_matches = bool(token and org_id) and all(
        env.get('IK_ORGO_TOKEN') == token and _uuid(env.get('IK_ORGO_TARGET_ORGANIZATION')) == org_id
        for env in kx_services)
    check('env_konnaxion', env_matches,
          'Jeton local et organisation chargés dans Django et Celery',
          'Jeton ou organisation de .django absent ou différent dans Django ou Celery')
    check('jeton_orgo', orgo_ready and env_matches and
          _db_matches(api, 'host.docker.internal', 'orgo_test') and
          _authenticated_orgo_token(ports['orgo-api'], token, org_id),
          'Jeton machine accepté par Orgo avec le périmètre IK requis',
          'Jeton machine, organisation ou droits IK non confirmés par Orgo')
    check('workflow_orgo', api.get('KONNAXION_DECISION_WORKFLOW_CODE') == 'konnaxion_decision_v1'
          and bool(api.get('KONNAXION_DECISION_LABEL')), 'Workflow et label IK configurés',
          'Workflow ou label IK Orgo absent ou inattendu')
    check('route_orgo_vers_konnaxion', worker.get('KONNAXION_IK_URL') == KX_ROUTE,
          'Route de retour effective conforme à C0', 'Route de retour effective absente ou hors C0')
    check('jeton_retour', bool(worker.get('KONNAXION_IK_TOKEN')) and
          worker['KONNAXION_IK_TOKEN'] == django_env.get('IK_ORGO_INBOUND_TOKEN'),
          'Jeton de retour identique côté worker et Django',
          'Jeton de retour absent ou différent')
    check('organisation_retour', bool(org_id) and _uuid(local.get('IK_ORGO_ALLOWED_ORGANIZATION')) == org_id
          and _uuid(django_env.get('IK_ORGO_ALLOWED_ORGANIZATION')) == org_id,
          'Retour restreint à l’organisation de test',
          'Organisation autorisée absente ou différente dans .django ou Django')

    route_ok = local.get('IK_ORGO_INTERACTIONS_URL') == ORGO_ROUTE and all(
        env.get('IK_ORGO_INTERACTIONS_URL') == ORGO_ROUTE and env.get('KX_IK_DOCKER_E2E') == '1'
        for env in kx_services)
    if route_ok and kx_ready:
        probe = ('from django.conf import settings; '
                 'from konnaxion.integrations.interaction_kernel.transport import _validated_target_url as valid; '
                 'url = settings.IK_ORGO_INTERACTIONS_URL; '
                 'raise SystemExit(0 if url and valid(url) == url else 1)')
        try:
            route_ok = _docker(docker, ['exec', KX_CONTAINERS[1], 'python', 'manage.py', 'shell', '-c', probe], root, call).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            route_ok = False
    check('route_konnaxion_vers_orgo', route_ok and kx_ready,
          'Route C0 acceptée par le filtre chargé dans le conteneur Celery',
          'Route C0 absente, différente ou refusée par le filtre Konnaxion')
    return checks


def _ports(root: Path) -> dict:
    _, registry = c0.read_registry(root)
    values = {row['id']: row['port'] for row in registry['services']}
    return {'orgo-api': values['orgo-api'], 'konnaxion-api': values['konnaxion-api']}


def attest_isolated_test_environment(tool: Path, world_key: str, phrase: str) -> Path:
    """Write a one-hour user attestation. This is not a database audit."""
    if phrase != ISOLATION_PHRASE or not WORLD_RE.fullmatch(world_key):
        raise PermissionError('Attestation volontaire des bases de test nécessaire')
    tool = Path(tool).resolve()
    if not tool.is_dir():
        raise ValueError('Dossier kOADiag manquant')
    destination = tool/TEST_AUTH_NAME
    if destination.is_symlink():
        raise PermissionError('Fichier de déclaration symbolique refusé')
    # If an existing authorization file is not recognizable, do not destroy it.
    if destination.exists():
        current = destination.read_bytes()
        if len(current) > 20_000:
            raise ValueError('Attestation préexistante non reconnue')
        try:
            parsed = json.loads(current)
            if parsed.get('schema') != 'koa.diag.ik.test-authorization.v1':
                raise ValueError('Attestation préexistante non reconnue')
        except (ValueError,TypeError):
            raise ValueError('Attestation préexistante non reconnue')
    data = {'schema':'koa.diag.ik.test-authorization.v1', 'environment':'isolated-test',
            'orgo_isolated_test_db':True, 'konnaxion_isolated_test_db':True,
            'allowed_world_keys':[world_key],
            'expires_utc':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
            'notice':'Déclaration utilisateur uniquement ; aucune preuve indépendante d’isolement.'}
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=tool,
                                     prefix='.ik-e2e-', suffix='.tmp',delete=False) as out:
        candidate=Path(out.name)
        json.dump(data,out,ensure_ascii=False,indent=2)
        out.write('\n')
    try:
        os.replace(candidate, destination)
    finally:
        candidate.unlink(missing_ok=True)
    return destination


def test_authorization(tool: Path, world_key: str) -> dict:
    """A user-controlled marker is a declaration, NOT independent DB isolation proof."""
    path = Path(tool) / TEST_AUTH_NAME
    default = {'status': 'BLOCKED', 'reason': 'Attestation locale de bases isolées absente ou expirée'}
    if not path.is_file() or path.is_symlink():
        return default
    try:
        if path.stat().st_size > 20_000:
            return default
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        if data.get('schema') != 'koa.diag.ik.test-authorization.v1' or data.get('environment') != 'isolated-test':
            return default
        if data.get('orgo_isolated_test_db') is not True or data.get('konnaxion_isolated_test_db') is not True:
            return default
        worlds = data.get('allowed_world_keys')
        if not isinstance(worlds, list) or world_key not in worlds or not WORLD_RE.fullmatch(world_key):
            return {'status': 'BLOCKED', 'reason': 'World de test non autorisé dans la déclaration'}
        expiry = datetime.fromisoformat(data['expires_utc'].replace('Z', '+00:00'))
        if expiry.utcoffset() is None:
            return default
        remaining = (expiry - datetime.now(timezone.utc)).total_seconds()
        if not 0 < remaining <= 86400:
            return default
        return {'status': 'ATTESTED', 'reason': 'Isolement attesté par utilisateur, non certifié automatiquement',
                'expires_utc': expiry.isoformat(), 'world_key': world_key}
    except (KeyError, ValueError, TypeError, OSError, UnicodeError, json.JSONDecodeError):
        return default


def preflight(root: Path, tool: Path, *, world_key: str = '', docker_call=None,
              http_check=None, docker_path=None, ps_path=None) -> dict:
    root = Path(root).resolve()
    tool = Path(tool).resolve()
    checks = []
    def item(name, status, detail):
        checks.append({'id': name, 'status': status, 'detail': detail})
    try:
        ports = _ports(root)
    except (OSError, ValueError, KeyError, TypeError):
        ports = {}
    if ports.get('orgo-api') == 21111 and ports.get('konnaxion-api') == 21131:
        item('registre_c0', 'PASS', 'API Orgo et Konnaxion affectées aux ports C0 dédiés')
    else:
        item('registre_c0', 'BLOCKED', 'Registre C0 absent ou attributions inattendues')
    kit = root / OFFICIAL_SCRIPT
    if kit.is_file() and not kit.is_symlink():
        item('kit_officiel', 'PASS', 'Script du dépôt Orgo présent (aucune copie de logique métier)')
    else:
        item('kit_officiel', 'BLOCKED', 'Kit E2E officiel Orgo introuvable')
    probe = http_check or _http_ok
    for sid, path in (('orgo-api', '/health/ready'), ('konnaxion-api', '/health/ready/')):
        r = probe(ports[sid], path) if sid in ports else {'status': 'BLOCKED'}
        item('http_' + sid, r['status'], f"Santé HTTP : {r.get('http_code', 'indisponible')}")
    docker = docker_path if docker_path is not None else shutil.which('docker')
    pwsh = ps_path if ps_path is not None else shutil.which('pwsh')
    if not pwsh:
        item('pwsh', 'BLOCKED', 'PowerShell 7 requis')
    checks.extend(runtime_checks(root, docker, ports, call=docker_call))
    auth = test_authorization(tool, world_key)
    item('autorisation_donnees', 'PASS' if auth['status'] == 'ATTESTED' else 'BLOCKED', auth['reason'])
    blockers = [c['id'] for c in checks if c['status'] != 'PASS']
    return {'schema': SCHEMA, 'type': 'preflight', 'checked_at_utc': datetime.now(timezone.utc).isoformat(),
            'world_key': world_key, 'ports': ports, 'checks': checks,
            'result': 'READY_FOR_EXPLICIT_CONFIRMATION' if not blockers else 'BLOCKED',
            'blocking_checks': blockers, 'test_only_assertion': auth['status'] == 'ATTESTED',
            'explanation': 'Une attestation ne prouve pas indépendamment l’isolement des bases ; vérifier la pile réelle.'}


def run_e2e(root: Path, tool: Path, *, world_key: str, confirmation: str,
            progress=None, preflight_func=None, run=None) -> dict:
    """Explicitly requested action only. Never invoked by validate() or import."""
    if confirmation != CONFIRM_PHRASE or not WORLD_RE.fullmatch(world_key):
        raise PermissionError('Confirmation E2E explicite ou World de test manquant')
    root = Path(root).resolve()
    tool = Path(tool).resolve()
    status = (preflight_func or preflight)(root, tool, world_key=world_key)
    if status['result'] != 'READY_FOR_EXPLICIT_CONFIRMATION':
        raise PermissionError('Prévalidation bloquante : ' + ', '.join(status['blocking_checks']))
    kit = root/OFFICIAL_SCRIPT
    if not kit.is_file() or kit.is_symlink():
        raise PermissionError('Kit officiel absent')
    pwsh = shutil.which('pwsh')
    if not pwsh:
        raise PermissionError('PowerShell 7 introuvable')
    # Do not capture full raw output into shareable reports: an official kit may
    # print secrets, request/response bodies or bearer tokens on errors.
    cmd = [pwsh, '-NoProfile', '-NonInteractive', '-File', str(kit),
           '-OrgoRoot', str(root/ORGO_DIR), '-KonnaxionRoot', str(root/KONNAXION_DIR),
           '-OrgoHostUrl', f"http://127.0.0.1:{status['ports']['orgo-api']}",
           '-WorldKey', world_key, '-TimeoutSeconds', '120', '-ExportObservations']
    if progress:
        progress('Exécution distincte du kit propriétaire dans le World de test autorisé…')
    started = datetime.now(timezone.utc).isoformat()
    try:
        fn = run or subprocess.run
        p = fn(cmd, cwd=str(tool), stdin=subprocess.DEVNULL, capture_output=True,
               text=True, encoding='utf-8', errors='replace', timeout=300,
               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        lines = [x.strip() for x in p.stdout.splitlines()]
        success = p.returncode == 0 and PASS in lines
        observations = {'status': 'ABSENTES'}
        try:
            observations = _observations(lines)
        except (ValueError, OverflowError):
            pass
        result = {'schema': SCHEMA, 'type': 'transaction', 'world_key': world_key,
                  'started_at_utc': started, 'completed_at_utc': datetime.now(timezone.utc).isoformat(),
                  'verdict': 'PASS' if success else 'FAIL', 'exit_code': p.returncode,
                  'pass_marker_observed': PASS in lines, 'observations': observations,
                  'official_script_sha256': hashlib.sha256(kit.read_bytes()).hexdigest(),
                  'details': 'Test officiel terminé, marqueur PASS vérifié' if success else
                             'Le test officiel a échoué ou n’a pas renvoyé le marqueur PASS. Consulter les journaux propriétaires sécurisés.'}
    except (OSError, subprocess.TimeoutExpired):
        result = {'schema': SCHEMA, 'type': 'transaction', 'world_key': world_key,
                  'started_at_utc': started, 'completed_at_utc': datetime.now(timezone.utc).isoformat(),
                  'verdict': 'ERROR', 'exit_code': None, 'pass_marker_observed': False,
                  'observations': {'status':'ABSENTES'},
                  'details': 'Le test officiel a dépassé le délai ou le processus est inaccessible'}
    result['source'] = 'koadiag'
    return _save_report(tool, result)


def _observations(lines: list[str]) -> dict:
    records = [line[len(OBS_PREFIX):] for line in lines if line.startswith(OBS_PREFIX)]
    if len(records) != 1 or len(records[0]) >= 4096:
        raise ValueError('Une observation IK unique est requise.')
    raw = records[0]
    record = json.loads(raw)
    if not isinstance(record, dict):
        raise ValueError('Observation IK invalide.')
    correlation = record.get('correlation_id')
    if not isinstance(correlation, str) or not re.fullmatch(r'[a-zA-Z0-9:_-]{1,128}', correlation):
        raise ValueError('Corrélation IK invalide.')
    times = {}
    for hop, allowed in (('decision', ('accepted', 'succeeded')), ('impact', ('succeeded',))):
        if not _uuid(record.get(hop + '_id')) or record.get(hop + '_status') not in allowed:
            raise ValueError('Identifiant ou statut IK invalide.')
        ordered = []
        for phase in ('sent', 'received', 'response'):
            key = f'{hop}_{phase}'
            value = record.get(key)
            if not isinstance(value, str) or not 20 <= len(value) <= 40:
                raise ValueError('Horodatage IK invalide.')
            timestamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if timestamp.utcoffset() is None:
                raise ValueError('Fuseau horaire IK absent.')
            ordered.append(timestamp)
            times[key] = timestamp.astimezone(timezone.utc).isoformat()
        if ordered != sorted(ordered):
            raise ValueError('Séquence des horodatages IK incohérente.')
    return {'status': 'METADONNEES_PRESENTES',
            'raw_sha256': hashlib.sha256(raw.encode()).hexdigest(),
            'correlation_sha256_prefix': hashlib.sha256(correlation.encode()).hexdigest()[:16],
            'decision_status': record['decision_status'], 'impact_status': record['impact_status'],
            'timestamps_utc': times}


def import_terminal_result(path: Path, tool: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 256_000:
        raise ValueError('Fichier de sortie PowerShell invalide ou trop volumineux.')
    lines = [line.strip() for line in path.read_text(encoding='utf-8-sig').splitlines()]
    worlds = [m for line in lines if (m := re.fullmatch(
        r'Konnaxion test World: ([a-z0-9][a-z0-9_-]{0,127}), release ID: ([1-9][0-9]*)\.', line))]
    if lines.count(PASS) != 1 or len(worlds) != 1:
        raise ValueError('Choisis la sortie d’un seul test officiel terminé avec PASS.')
    try:
        observations = _observations(lines)
    except OverflowError as exc:
        raise ValueError('Horodatage IK hors plage.') from exc
    return _save_report(tool, {
        'schema': SCHEMA, 'type': 'transaction', 'source': 'terminal_import',
        'world_key': worlds[0][1], 'release_id': int(worlds[0][2]),
        'imported_at_utc': datetime.now(timezone.utc).isoformat(),
        'verdict': 'PASS', 'pass_marker_observed': True, 'observations': observations,
        'details': 'PASS déclaré dans une sortie du kit officiel importée. Aucune exécution kOADiag.',
    })


def _save_report(tool: Path, result: dict) -> dict:
    destination = tool/'reports'/'Diagnostic-kOA-Digital-Ecosystem'/'ik-e2e'
    destination.mkdir(parents=True, exist_ok=True)
    out = destination / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6] + '.json')
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    result['report_path'] = str(out)
    return result
