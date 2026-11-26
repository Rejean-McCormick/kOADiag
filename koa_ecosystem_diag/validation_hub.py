# -*- coding: utf-8 -*-
"""Central read-only validation journeys for kOADiag.

Run modes never start services, invoke internal app suites, create test data,
contact remote hosts, or authenticate. The deep LevelUpDiag invocation disables
network, remote, audit publication, and runtime-local options explicitly.
"""
from __future__ import annotations

from collections import Counter, deque
from datetime import datetime, timezone
import csv
from hashlib import sha256
import http.client
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid

from . import port_diagnostics as c0
from .levelup_triage import MAX_BYTES, MAX_FINDINGS, _safe_text, interpret_report
from .framework import load_config, load_manifest, resolve_campaign, VERDICTS
from .campaign_recovery import recovery_plan
from .hub_session import stream_process
from .app_suite_catalog import discover as discover_app_suites

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
_SAFE_PROGRESS = re.compile(r'^(RUN_ROOT=|LEVEL_START=|LEVEL=|VERDICT=|SUMMARY=)')
HUB_CAMPAIGNS = {'intermediaire': 'validation-intermediaire', 'approfondie': 'validation-integrale'}
INTERMEDIATE_LIMITS = {'campaign_seconds': 105, 'files_per_repo': 120, 'bytes_per_file': 80000,
                       'entries_per_repo': 2500, 'seconds_per_repo': 2,
                       'surface_seconds': 22, 'ik_reference_seconds': 6}



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
    domains = {
        'services_essentiels': ('TCP_CONFIRME' if reachable_essential == len(essential) and all(
            row.get('status') == 'IDENTITY_CONFIRMED' for row in essential) else
            'TCP_ACCESSIBLE_IDENTITE_PARTIELLE' if reachable_essential == len(essential) and not incorrect else 'PARTIAL'),
        'sante_http': ('NON_EXECUTEE' if mode == 'rapide' else
                       ('ECART' if health_errors else 'PASS' if all(
                           h['status'] == 'HTTP_OK' for h in health if h['id'] in ESSENTIALS
                       ) and len([h for h in health if h['id'] in ESSENTIALS]) == len(essential) else 'PARTIAL')),
        'connexions': ('PARTIAL' if not all(x['status'] == 'EXTREMITES_ACCESSIBLES'
                         for x in links if x['source'] != x['target']) else 'TCP_SEULEMENT'),
        'preuves_levelup': 'NON_EXECUTEES' if campaign is None else campaign.get('verdict','INCONNU'),
        'interaction_kernel_e2e': 'NON_EXECUTE',
    }
    return {
        'domaines': domains,
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


def _developer_evidence(run_root, runs_dir, expected_levels, campaign):
    levels = [{'id': meta['id'], 'nom': meta['name'], 'verdict': 'NON_OBSERVE',
               'source': None, 'sha256': None, 'artefacts': [], 'constats': [],
               'constats_omis': 0} for meta in expected_levels]
    evidence = {'schema': 'koa.diag.developer-evidence.v1', 'run_id': None,
                'verdict': campaign['verdict'], 'limites': INTERMEDIATE_LIMITS, 'niveaux': levels,
                'exports_locaux': ['validation.json', 'applications.csv', 'connexions.csv'],
                'portee': 'Constats passifs et traces existantes, aucune transaction E2E exécutée.'}
    if run_root is None:
        return evidence
    raw_root = Path(run_root)
    root = raw_root.resolve()
    if raw_root.is_symlink() or root.parent != runs_dir.resolve() or not re.fullmatch(
            r'[A-Za-z0-9_-]{1,90}', root.name):
        return evidence
    evidence['run_id'] = root.name
    evidence['dossier_source'] = f'runs/{root.name}'
    for item in levels:
        rel = f"levels/{item['id']}/result.json"
        source = root/rel
        try:
            if not source.is_file() or source.is_symlink() or not source.resolve().is_relative_to(root):
                continue
            with source.open('rb') as stream:
                raw = stream.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                item['erreur_lecture'] = 'Rapport de niveau trop volumineux'
                continue
            data = json.loads(raw.decode('utf-8-sig'))
            if (data['schema'] != 'levelupdiag.report.v2' or data['level_id'] != item['id']
                    or data['run_id'] != root.name or data['verdict'] not in VERDICTS):
                item['erreur_lecture'] = 'Identité, schéma ou verdict invalide'
                continue
            item.update(source=rel, sha256=sha256(raw).hexdigest(), verdict=data['verdict'])
            findings = data.get('findings', [])
            if isinstance(findings, list):
                item['constats_omis'] = max(0, len(findings) - MAX_FINDINGS)
                item['constats'] = [{
                    key: _safe_text(finding.get(key), 320)
                    for key in ('id', 'verdict', 'category', 'message', 'recommendation')
                } for finding in findings[:MAX_FINDINGS] if isinstance(finding, dict)]
            artifacts = data.get('artifacts', [])
            if isinstance(artifacts, list):
                for ref in artifacts[:40]:
                    if not isinstance(ref, dict) or not isinstance(ref.get('path'), str):
                        continue
                    original = Path(ref['path'])
                    path = (original if original.is_absolute() else root/original).resolve()
                    if path.is_relative_to(root) and path.is_file() and not original.is_symlink():
                        item['artefacts'].append(path.relative_to(root).as_posix())
        except (OSError, ValueError, RuntimeError, KeyError, TypeError, AttributeError) as exc:
            item['erreur_lecture'] = type(exc).__name__
    return evidence


def _passive_campaign(root: Path, tool: Path, *, progress=None, python=None, timeout=1800, selection='validation-integrale',
                      evidence_context=None) -> dict:
    # No runtime-local, network, remote, start-test-stack or --audit flags.
    executable = python or sys.executable
    command = [str(executable), '-X', 'utf8', '-u', str(tool/'Diagnostic-kOA-Digital-Ecosystem-CLI.py'),
               'run', selection, '--root', str(root)]
    last_run_root = None

    def outcome(data):
        if evidence_context is not None:
            data['developer_evidence'] = _developer_evidence(last_run_root, *evidence_context, data)
            data.setdefault('run_id', data['developer_evidence']['run_id'])
        return data

    if not (tool/'Diagnostic-kOA-Digital-Ecosystem-CLI.py').is_file():
        return outcome({'verdict': 'ERROR', 'detail': 'CLI LevelUpDiag absent'})
    try:
        def receive(line):
            nonlocal last_run_root
            if not _SAFE_PROGRESS.match(line):
                return
            if line.startswith('RUN_ROOT='):
                last_run_root = line.split('=', 1)[1]
            if progress:
                progress('LevelUpDiag : '+line[:240])

        exit_code = stream_process(command, tool, receive, timeout=timeout)
        if last_run_root:
            report_path = Path(last_run_root)/'summary.json'
            trusted = evidence_context[0] if evidence_context is not None else tool
            if (report_path.resolve().is_relative_to(trusted.resolve()) and
                    report_path.is_file() and not report_path.is_symlink() and
                    report_path.stat().st_size <= MAX_BYTES):
                data = json.loads(report_path.read_text(encoding='utf-8'))
                triage = None
                try:
                    triage = interpret_report(report_path, trusted_reports_root=(trusted if evidence_context else tool/'reports'))
                except (OSError, ValueError, TypeError, UnicodeError):
                    # A valid campaign is never erased because the optional triage fails.
                    pass
                recovery = None
                try:
                    recovery = recovery_plan(report_path.parent)
                except (OSError, ValueError, TypeError, UnicodeError):
                    pass
                return outcome({'verdict': data.get('verdict', 'INCONNU'),
                        'run_id': data.get('run_id'), 'report_path': str(report_path),
                        'exit_code': exit_code, 'triage': triage, 'recovery': recovery})
        return outcome({'verdict': 'ERROR', 'exit_code': exit_code,
                'detail': 'La campagne n’a pas retourné de rapport utilisable'})
    except subprocess.TimeoutExpired:
        return outcome({'verdict': 'PARTIAL' if evidence_context else 'ERROR',
                        'timed_out': True, 'detail': 'Délai maximal LevelUpDiag dépassé'})
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return outcome({'verdict': 'ERROR', 'detail': 'Échec LevelUpDiag : '+type(exc).__name__})


def validate(root: Path, *, mode='rapide', tool: Path | None = None,
             progress=None, deep_runner=None) -> dict:
    if mode != 'rapide' and mode not in HUB_CAMPAIGNS:
        raise ValueError('Mode de validation inconnu')
    root = Path(root).expanduser().resolve()
    intermediate = mode == 'intermediaire'
    journal = deque(maxlen=256)

    def notify(line):
        if intermediate:
            # Keep the event, without copying absolute output paths or raw worker logs.
            marker = line.split(' : ', 1)[-1]
            event = marker.split('=', 1)[0] if marker.startswith(('RUN_ROOT=', 'SUMMARY=')) else line
            journal.append({'at_utc': datetime.now(timezone.utc).isoformat(),
                            'event': _safe_text(event, 320)})
        if progress:
            progress(line)

    notify('Vérification des ports C0 et des identités locales…')
    ports = c0.check_all(root, timeout=0.75 if intermediate else 1.5)
    links = diagnose_links(ports)
    existing = {}
    for owner in sorted({s['owner'] for s in ports['services']}):
        rel = REPOS.get(owner)
        existing[owner] = {'path': rel, 'present': (root/rel).is_dir()} if rel else {
            'path': None, 'present': None}
    health = []
    campaign = None
    if mode in HUB_CAMPAIGNS:
        notify('Sondes de santé locales en lecture seule…')
        health = [health_probe(row, timeout=0.75) if intermediate else health_probe(row)
                  for row in ports['services']]
        notify('Campagne LevelUpDiag intermédiaire · preuves développeur…' if intermediate else
               'Campagne LevelUpDiag intégrale (passive, sans E2E transactionnel)…')
        if intermediate:
            if tool is None:
                raise ValueError('Dossier kOADiag requis pour la validation intermédiaire')
            tool = Path(tool)
            levels = resolve_campaign(load_manifest(tool), HUB_CAMPAIGNS[mode])
            runs_dir = Path(load_config(tool, root)['_control'])/'runs'
            campaign = _passive_campaign(root, tool, progress=notify,
                timeout=INTERMEDIATE_LIMITS['campaign_seconds'], selection=HUB_CAMPAIGNS[mode],
                evidence_context=(runs_dir, levels))
            notify('Index des preuves développeur terminé.')
        elif deep_runner is not None:
            campaign = deep_runner(root)
        else:
            if tool is None:
                raise ValueError('Dossier kOADiag requis pour la campagne approfondie')
            campaign = _passive_campaign(root, Path(tool), progress=notify)
        notify('Inventaire des suites applicatives déclarées…')
    suite_catalog = discover_app_suites(root) if mode in HUB_CAMPAIGNS else []
    summary = summarize(ports, links, health, mode, campaign=campaign)
    output = {'schema': 'koa.diag.validation.hub.v1',
              'checked_at_utc': datetime.now(timezone.utc).isoformat(),
              'summary': summary, 'services': ports['services'], 'links': links,
              'repositories': existing, 'health': health, 'campaign': campaign,
              'application_test_suites': suite_catalog,
              'ik_e2e': {'status':'NON_EXECUTE', 'detail':'Exécution séparée, sécurisée et confirmée par utilisateur.'},
              'port_registry_sha256': ports['registry_sha256']}
    if intermediate:
        output['developer_evidence'] = campaign.pop('developer_evidence')
        output['developer_evidence']['journal'] = list(journal)
    return output


def save_report(result: dict, base: Path) -> Path:
    folder = Path(base)/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6])
    folder.mkdir(parents=True, exist_ok=False)
    with (folder/'applications.csv').open('w', encoding='utf-8-sig', newline='') as out:
        columns = ['id','owner','port','tcp','http_code','status','detail']
        writer = csv.DictWriter(out, columns, extrasaction='ignore', delimiter=';')
        writer.writeheader();writer.writerows(result['services'])
    with (folder/'connexions.csv').open('w', encoding='utf-8-sig', newline='') as out:
        columns = ['name','source','target','status','detail','e2e_proven']
        writer = csv.DictWriter(out, columns, extrasaction='ignore', delimiter=';')
        writer.writeheader();writer.writerows(result['links'])
    triage = (result.get('campaign') or {}).get('triage')
    if isinstance(triage, dict):
        with (folder/'causes.csv').open('w', encoding='utf-8-sig', newline='') as out:
            columns = ['id', 'priorite', 'titre', 'detail', 'action', 'niveaux']
            writer = csv.DictWriter(out, columns, extrasaction='ignore', delimiter=';')
            writer.writeheader()
            for row in triage.get('causes', []):
                writer.writerow(dict(row, niveaux=','.join(row.get('niveaux', []))))
        with (folder/'niveaux.csv').open('w', encoding='utf-8-sig', newline='') as out:
            columns = ['id', 'nom', 'verdict', 'constats_non_pass', 'erreur_lecture']
            writer = csv.DictWriter(out, columns, delimiter=';')
            writer.writeheader()
            for row in triage.get('niveaux', []):
                writer.writerow({'id':row['id'], 'nom':row['nom'], 'verdict':row['verdict'],
                    'constats_non_pass':sum(f['verdict'] not in ('PASS','SKIP') for f in row['constats']),
                    'erreur_lecture': row.get('erreur_lecture','')})
    suites = result.get('application_test_suites', [])
    if suites:
        with (folder/'tests_applicatifs.csv').open('w', encoding='utf-8-sig', newline='') as out:
            columns=['owner','location','kind','entry','status']
            writer=csv.DictWriter(out,columns,extrasaction='ignore',delimiter=';')
            writer.writeheader();writer.writerows(suites)
    recovery = (result.get('campaign') or {}).get('recovery')
    if isinstance(recovery, dict):
        with (folder/'remediations.csv').open('w', encoding='utf-8-sig', newline='') as out:
            columns=['id','category','priority','owner','count','file','locations','action']
            writer=csv.DictWriter(out,columns,extrasaction='ignore',delimiter=';')
            writer.writeheader()
            for row in recovery.get('items', []):
                writer.writerow(dict(row, locations=', '.join(row.get('locations',[]))))
    developer = result.get('developer_evidence')
    if isinstance(developer, dict):
        journal = developer['journal']
        index = {key: value for key, value in developer.items() if key != 'journal'}
        (folder/'preuves-index.json').write_text(
            json.dumps(index, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        (folder/'preuves-journal.jsonl').write_text(
            ''.join(json.dumps(event, ensure_ascii=False)+'\n' for event in journal),
            encoding='utf-8')
        with (folder/'preuves-constats.csv').open('w', encoding='utf-8-sig', newline='') as out:
            columns = ['niveau','id','verdict','category','message','recommendation','source']
            writer = csv.DictWriter(out, columns, delimiter=';')
            writer.writeheader()
            for level in developer['niveaux']:
                for finding in level['constats']:
                    row = dict(finding, niveau=level['id'], source=level['source'])
                    writer.writerow({
                        key: "'" + value if isinstance(value, str) and
                        value.lstrip().startswith(('=', '+', '-', '@')) else value
                        for key, value in row.items()
                    })
    s = result['summary']
    lines = [f"kOADiag — Validation {s['mode']}", f"Verdict : {s['verdict']}",
             f"Essentiels : {s['services_essentiels_accessibles']}/{s['services_essentiels_total']}",
             f"Services C0 : {s['services_accessibles']}/{s['port_count']}",
             f"Connexions : {s['liaisons_extremites_accessibles']}/{s['liaisons_declarees']} (extrémités seulement)",
             'Tests métier E2E : 0 (nécessitent confirmation distincte)',
             s['precision']]
    if isinstance(developer, dict):
        lines.append('Dossier développeur : preuves-index.json · preuves-constats.csv · preuves-journal.jsonl')
    if suites:
        lines.append('Suites propriétaires référencées : '+str(len(suites))+' (non exécutées).')
    if s.get('domaines'):
        lines.extend(['', 'DOMAINES DISTINCTS :'] + [f' - {k}: {v}' for k,v in s['domaines'].items()])
    if isinstance(recovery, dict):
        lines.append('Plan de remédiation : '+str(len(recovery.get('items',[])))+' pistes (sans changement automatique).')
    if isinstance(triage, dict):
        lines.append('')
        lines.append(f"LEVELUP : {triage['requis_pass']}/{triage['requis_total']} contrôles obligatoires PASS")
        lines.append(f"Causes à traiter : {len(triage.get('causes', []))} (preuves et périmètre, non pannes automatiques)")
        lines.extend(f" - {row['priorite']} {row['titre']}: {row['action']}" for row in triage.get('causes', []))
    (folder/'synthese.txt').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    # Publish the JSON marker only after all report files are complete.
    pending = folder/'validation.json.tmp'
    pending.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    pending.replace(folder/'validation.json')
    return folder
