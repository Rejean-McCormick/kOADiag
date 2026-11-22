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
import hashlib
import os
import tempfile
import http.client
import json
import re
import shutil
import subprocess
import sys
import uuid

from . import port_diagnostics as c0

OFFICIAL_SCRIPT = Path('Orgo/Orgo/validation/konnaxion-orgo-ik/run-e2e.ps1')
ORGO_DIR = Path('Orgo/Orgo')
KONNAXION_DIR = Path('Konnaxion/Konnaxion')
ORGO_COMPOSE = 'docker-compose.yml'
KX_COMPOSE = 'docker-compose.local.yml'
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


def _env_keys(path: Path, keys: tuple[str, ...]) -> dict:
    """Read only required key values, never return secrets or private paths."""
    if not path.is_file() or path.is_symlink():
        return {'present': False, 'keys_present': [], 'missing_keys': list(keys), 'routes': {}}
    required = set(keys)
    found = set()
    routes = {}
    try:
        if path.stat().st_size > 200_000:
            raise ValueError('Taille .env inattendue')
        for raw in path.read_text(encoding='utf-8-sig', errors='replace').splitlines():
            if raw.startswith('#') or '=' not in raw:
                continue
            k, v = raw.split('=', 1)
            if k in required and v.strip().strip('"\''):
                found.add(k)
            if k in ('KONNAXION_IK_URL', 'IK_ORGO_INTERACTIONS_URL'):
                # Only compare to a documented literal host:port. Never report original URL.
                value = v.strip().strip('"\'')
                expected_port = 21131 if k == 'KONNAXION_IK_URL' else 21111
                routes[k] = ('OK' if re.match(
                    rf'\Ahttp://host\.docker\.internal:{expected_port}/[A-Za-z0-9_./-]+\Z', value
                ) else ('MISSING' if not value else 'NOT_C0_DOCKER'))
    except (OSError, ValueError):
        return {'present': False, 'keys_present': [], 'missing_keys': list(keys), 'routes': {}}
    return {'present': True, 'keys_present': sorted(found),
            'missing_keys': sorted(required - found), 'routes': routes}


def _compose_services(docker: str, folder: Path, compose: str, required: tuple[str, ...], *, call=None) -> dict:
    cmd = [docker, 'compose', '-f', compose, 'ps', '--services', '--status', 'running']
    try:
        fn = call or subprocess.run
        p = fn(cmd, cwd=str(folder), stdin=subprocess.DEVNULL, capture_output=True,
               text=True, encoding='utf-8', errors='replace', timeout=20,
               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if p.returncode:
            return {'status': 'BLOCKED', 'required': list(required), 'missing': list(required),
                    'detail': 'Docker Compose indisponible (aucune sortie brute affichée)'}
        running = set(p.stdout.split())
        missing = sorted(set(required) - running)
        return {'status': 'PASS' if not missing else 'BLOCKED', 'required': list(required),
                'missing': missing}
    except (OSError, subprocess.TimeoutExpired):
        return {'status': 'BLOCKED', 'required': list(required), 'missing': list(required),
                'detail': 'Impossible de vérifier les conteneurs'}


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
    orgo = _env_keys(root / ORGO_DIR / '.env', ('POSTGRES_PASSWORD', 'KONNAXION_IK_URL'))
    konnaxion = _env_keys(root / KONNAXION_DIR / 'backend/.envs/.local/.django',
                          ('IK_ORGO_TOKEN', 'IK_ORGO_TARGET_ORGANIZATION', 'IK_ORGO_INTERACTIONS_URL'))
    for name, vals in (('env_orgo', orgo), ('env_konnaxion', konnaxion)):
        missing = vals['missing_keys']
        item(name, 'BLOCKED' if missing else 'PASS',
             'Variables manquantes : ' + ', '.join(missing) if missing else 'Clés requises présentes, valeurs masquées')
    for key, vals in (('route_orgo_vers_konnaxion', orgo), ('route_konnaxion_vers_orgo', konnaxion)):
        var = 'KONNAXION_IK_URL' if key.startswith('route_orgo') else 'IK_ORGO_INTERACTIONS_URL'
        state = vals['routes'].get(var, 'MISSING')
        item(key, 'PASS' if state == 'OK' else 'BLOCKED',
             'URL Docker locale conforme à C0' if state == 'OK' else 'URL IK Docker manquante ou hors C0')
    probe = http_check or _http_ok
    for sid, path in (('orgo-api', '/health/ready'), ('konnaxion-api', '/health/ready/')):
        r = probe(ports[sid], path) if sid in ports else {'status': 'BLOCKED'}
        item('http_' + sid, r['status'], f"Santé HTTP : {r.get('http_code', 'indisponible')}")
    docker = docker_path if docker_path is not None else shutil.which('docker')
    pwsh = ps_path if ps_path is not None else shutil.which('pwsh')
    if not docker:
        item('docker', 'BLOCKED', 'Docker CLI absent')
    if not pwsh:
        item('pwsh', 'BLOCKED', 'PowerShell 7 requis')
    # The official kit executes Python inside the Konnaxion Django *container*;
    # a native Uvicorn process is insufficient even when its health probe passes.
    if docker:
        for sid, folder, compose, services in (
            ('docker_orgo', root/ORGO_DIR, ORGO_COMPOSE, ('postgres', 'api', 'worker')),
            ('docker_konnaxion', root/KONNAXION_DIR/'backend', KX_COMPOSE,
             ('redis', 'django', 'celeryworker')),
        ):
            result = _compose_services(docker, folder, compose, services, call=docker_call) if (
                folder/compose).is_file() else {'status': 'BLOCKED', 'missing': list(services)}
            item(sid, result['status'], 'Services attendus manquants : ' + ', '.join(result['missing'])
                 if result['missing'] else 'Conteneurs nécessaires démarrés')
    else:
        item('docker_orgo', 'BLOCKED', 'Compose non vérifié')
        item('docker_konnaxion', 'BLOCKED', 'Compose non vérifié')
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
        observations = {'status':'ABSENTES'}
        raw_record = next((x[len(OBS_PREFIX):] for x in lines if x.startswith(OBS_PREFIX)), None)
        if raw_record and len(raw_record) < 4096:
            try:
                item = json.loads(raw_record)
                required = ('correlation_id','decision_id','impact_id','decision_status','impact_status')
                if isinstance(item,dict) and all(isinstance(item.get(k),str) and item[k] for k in required):
                    observations = {'status':'METADONNEES_PRESENTES',
                                    'raw_sha256':hashlib.sha256(raw_record.encode()).hexdigest(),
                                    'correlation_sha256_prefix':hashlib.sha256(item['correlation_id'].encode()).hexdigest()[:16],
                                    'decision_status':str(item['decision_status'])[:32],
                                    'impact_status':str(item['impact_status'])[:32]}
            except (ValueError,TypeError):
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
    # Export only vetted structured metadata, never stdout/stderr or credentials.
    destination = tool/'reports'/'Diagnostic-kOA-Digital-Ecosystem'/'ik-e2e'
    destination.mkdir(parents=True, exist_ok=True)
    out = destination/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]+'.json')
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    result['report_path'] = str(out)
    return result
