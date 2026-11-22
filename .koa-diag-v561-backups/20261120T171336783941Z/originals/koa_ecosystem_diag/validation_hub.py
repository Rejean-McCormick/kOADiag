# -*- coding: utf-8 -*-
"""Central read-only validation journeys for kOADiag.

Run modes never start services, invoke internal app suites, create test data,
contact remote hosts, or authenticate. The deep LevelUpDiag invocation disables
network, remote, audit publication, and runtime-local options explicitly.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import csv
import http.client
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid

from . import port_diagnostics as c0

# No request is made to any path that is not explicitly declared here.
# Unknown applications remain "not validated", never guessed healthy.
HEALTH_PATHS = {
    'orgo-api': '/health/ready',
    'konnaxion-api': '/health/ready/',
    'orgo-web': '/',
    'konnaxion-web': '/',
    'initkoa-web': '/',
}
REPOS = {
    'orgo': 'Orgo/Orgo',
    'initkoa': 'HomePage/HomePage',
    'konnaxion': 'Konnaxion/Konnaxion',
    'skope': 'Skope/Skope',
    'ekole': 'Ekole/ekole',
    'koali': 'kOA-Linux/koali-spaces',
}
ESSENTIALS = {'orgo-web', 'orgo-api', 'initkoa-web', 'konnaxion-web', 'konnaxion-api'}
_SAFE_PROGRESS = re.compile(r'^(RUN_ROOT=|LEVEL=|VERDICT=|SUMMARY=)')


def health_probe(service: dict, timeout: float = 2.0) -> dict:
    """Read-only, no redirects, loopback-only, bounded response."""
    sid = service['id']
    path = HEALTH_PATHS.get(sid)
    if not path:
        return {'id': sid, 'status': 'NON_CONFIGURE', 'detail': 'Aucun endpoint santé validé pour ce service'}
    if not service.get('tcp'):
        return {'id': sid, 'status': 'INDISPONIBLE', 'detail': 'Port local fermé', 'path': path}
    port = service['port']
    if not isinstance(port, int) or not 21100 <= port <= 21199:
        raise ValueError('Port hors registre C0')
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=timeout)
    try:
        conn.request('GET', path, headers={'User-Agent': 'kOADiag-C0-Health/1.0', 'Connection': 'close'})
        response = conn.getresponse()
        response.read(256)
        status = 'HTTP_OK' if response.status == 200 else 'HTTP_NON_OK'
        return {'id': sid, 'status': status, 'http_code': response.status, 'path': path,
                'detail': 'Réponse HTTP 200' if status == 'HTTP_OK' else f'Réponse HTTP {response.status}'}
    except (OSError, TimeoutError, http.client.HTTPException) as exc:
        return {'id': sid, 'status': 'ERREUR_HTTP', 'path': path, 'detail': type(exc).__name__}
    finally:
        conn.close()


def diagnose_links(ports_result: dict) -> list[dict]:
    """Describe observed local reachability, not an authenticated E2E."""
    links = []
    by_id = {x['id']: x for x in ports_result['services']}
    for row in ports_result['endpoint_pairs']:
        rec = dict(row)
        if rec['source'] == rec['target']:
            rec['status'] = 'NON_TESTABLE'
            rec['detail'] = 'Source indépendante non enregistrée dans C0 ; audit kOA non démontré'
        elif rec['source_tcp'] and rec['target_tcp']:
            source, target = by_id[rec['source']], by_id[rec['target']]
            if 'WRONG_SERVICE' in (source['status'], target['status']):
                rec['status'] = 'IDENTITE_INCORRECTE'
                rec['detail'] = 'Au moins un endpoint répond avec une mauvaise identité'
            else:
                rec['status'] = 'EXTREMITES_ACCESSIBLES'
                rec['detail'] = 'Présence TCP des deux côtés uniquement ; transaction E2E non testée'
        else:
            rec['status'] = 'EXTREMITES_INDISPONIBLES'
            rec['detail'] = 'Un ou deux endpoints locaux sont indisponibles'
        rec['e2e_proven'] = False
        links.append(rec)
    return links


def summarize(ports_result: dict, links: list, health: list, mode: str, *, campaign=None) -> dict:
    services = ports_result['services']
    essential = [row for row in services if row['id'] in ESSENTIALS]
    reachable = sum(bool(row.get('tcp')) for row in services)
    reachable_essential = sum(bool(row.get('tcp')) for row in essential)
    incorrect = [r for r in services if r['status'] in ('WRONG_SERVICE', 'SCAN_ERROR')]
    health_errors = [h for h in health if h['status'] in ('HTTP_NON_OK', 'ERREUR_HTTP')]
    link_err = sum(x['status'] == 'IDENTITE_INCORRECTE' for x in links)
    issues = len(incorrect) + len(health_errors) + link_err
    if issues:
        verdict = 'ECART'
    elif reachable_essential < len(essential):
        verdict = 'PARTIEL'
    else:
        verdict = 'CONDITIONNEL'
    if campaign is not None:
        if campaign.get('verdict') in ('FAIL', 'ERROR', 'BLOCKED', 'INFRA_ERROR', 'CONFIG_ERROR'):
            verdict = 'ECART'
        elif campaign.get('verdict') in ('WARN', 'PARTIAL') and verdict == 'CONDITIONNEL':
            verdict = 'PARTIEL'
    return {
        'mode': mode, 'verdict': verdict, 'port_count': len(services),
        'services_accessibles': reachable, 'services_essentiels_accessibles': reachable_essential,
        'services_essentiels_total': len(essential),
        'services_non_demarras': sum(not r.get('tcp') for r in services),
        'anomalies_identite': len(incorrect), 'erreurs_sante': len(health_errors),
        'liaisons_declarees': len(links),
        'liaisons_extremites_accessibles': sum(x['status'] == 'EXTREMITES_ACCESSIBLES' for x in links),
        'transactions_e2e_executees': 0,
        'precision': 'Absence de service ≠ panne si le composant est volontairement arrêté. '
                     'Aucun échange métier, agent distant ni authentification n’a été testé.'
    }


def _passive_campaign(root: Path, tool: Path, *, progress=None, python=None, timeout=1800) -> dict:
    # No runtime-local, network, remote, start-test-stack or --audit flags.
    executable = python or sys.executable
    command = [str(executable), str(tool/'Diagnostic-kOA-Digital-Ecosystem-CLI.py'),
               'run', 'validation-integrale', '--root', str(root)]
    if not (tool/'Diagnostic-kOA-Digital-Ecosystem-CLI.py').is_file():
        return {'verdict': 'ERROR', 'detail': 'CLI LevelUpDiag absent'}
    try:
        proc = subprocess.run(command, cwd=str(tool), stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, encoding='utf-8', errors='replace',
                              timeout=timeout, shell=False,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        markers = [line.strip() for line in proc.stdout.splitlines() if _SAFE_PROGRESS.match(line.strip())]
        if progress:
            for line in markers[-50:]: progress('LevelUpDiag : '+line[:240])
        run_roots = [line.split('=', 1)[1] for line in markers if line.startswith('RUN_ROOT=')]
        if run_roots:
            report_path = Path(run_roots[-1])/'summary.json'
            if report_path.is_file():
                data = json.loads(report_path.read_text(encoding='utf-8'))
                return {'verdict': data.get('verdict', 'INCONNU'),
                        'run_id': data.get('run_id'), 'report_path': str(report_path),
                        'exit_code': proc.returncode}
        return {'verdict': 'ERROR', 'exit_code': proc.returncode,
                'detail': 'La campagne n’a pas retourné de rapport utilisable'}
    except subprocess.TimeoutExpired:
        return {'verdict': 'ERROR', 'detail': 'Délai maximal LevelUpDiag dépassé'}
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {'verdict': 'ERROR', 'detail': 'Échec LevelUpDiag : '+type(exc).__name__}


def validate(root: Path, *, mode='rapide', tool: Path | None = None,
             progress=None, deep_runner=None) -> dict:
    if mode not in ('rapide', 'approfondie'):
        raise ValueError('Mode de validation inconnu')
    root = Path(root).expanduser().resolve()
    if progress: progress('Vérification des ports C0 et des identités locales…')
    ports = c0.check_all(root, timeout=1.5)
    links = diagnose_links(ports)
    existing = {}
    for owner in sorted({s['owner'] for s in ports['services']}):
        rel = REPOS.get(owner)
        existing[owner] = {'path': rel, 'present': (root/rel).is_dir()} if rel else {
            'path': None, 'present': None}
    health = []
    campaign = None
    if mode == 'approfondie':
        if progress: progress('Sondes de santé locales en lecture seule…')
        health = [health_probe(row) for row in ports['services']]
        if progress: progress('Campagne LevelUpDiag intégrale (passive, sans E2E transactionnel)…')
        if deep_runner is not None:
            campaign = deep_runner(root)
        else:
            if tool is None: raise ValueError('Dossier kOADiag requis pour la campagne approfondie')
            campaign = _passive_campaign(root, Path(tool), progress=progress)
    summary = summarize(ports, links, health, mode, campaign=campaign)
    output = {'schema': 'koa.diag.validation.hub.v1',
              'checked_at_utc': datetime.now(timezone.utc).isoformat(),
              'summary': summary, 'services': ports['services'], 'links': links,
              'repositories': existing, 'health': health, 'campaign': campaign,
              'port_registry_sha256': ports['registry_sha256']}
    return output


def save_report(result: dict, base: Path) -> Path:
    folder = Path(base)/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6])
    folder.mkdir(parents=True, exist_ok=False)
    (folder/'validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    with (folder/'applications.csv').open('w', encoding='utf-8-sig', newline='') as out:
        columns = ['id','owner','port','tcp','http_code','status','detail']
        writer = csv.DictWriter(out, columns, extrasaction='ignore', delimiter=';')
        writer.writeheader();writer.writerows(result['services'])
    with (folder/'connexions.csv').open('w', encoding='utf-8-sig', newline='') as out:
        columns = ['name','source','target','status','detail','e2e_proven']
        writer = csv.DictWriter(out, columns, extrasaction='ignore', delimiter=';')
        writer.writeheader();writer.writerows(result['links'])
    s = result['summary']
    lines = [f"kOADiag — Validation {s['mode']}", f"Verdict : {s['verdict']}",
             f"Essentiels : {s['services_essentiels_accessibles']}/{s['services_essentiels_total']}",
             f"Services C0 : {s['services_accessibles']}/{s['port_count']}",
             f"Connexions : {s['liaisons_extremites_accessibles']}/{s['liaisons_declarees']} (extrémités seulement)",
             'Tests métier E2E : 0 (nécessitent confirmation distincte)',
             s['precision']]
    (folder/'synthese.txt').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return folder
