"""Inventory and boundary-by-mode validation results for a single campaign."""
import csv
from collections import Counter

from .framework import write_json
from .journeys import evaluate_journeys
from .qualification import matrix

MODES = ('autonome', 'integre')


def assess(snapshot, decisions, declarations, policy, *, collected, runtime_cases=()):
    cases = list(runtime_cases)
    for repo in snapshot.get('repositories', []):
        present = repo.get('exists')
        incomplete = (repo.get('truncated') or repo.get('oversized_files') or
                      repo.get('unreadable_files') or not repo.get('scanned_files'))
        cases.append({'kind': 'depot', 'id': repo['repo'], 'mode': '',
                      'verdict': 'BLOCKED' if not present else ('PARTIAL' if incomplete else 'PASS'),
                      'status': 'ABSENT' if not present else ('COLLECTE_PARTIELLE' if incomplete else 'COLLECTE_OK'),
                      'required': True, 'details': repo})
    if not isinstance(declarations, list):
        cases.append({'kind': 'configuration', 'id': 'journeys', 'mode': '', 'verdict': 'CONFIG_ERROR',
                      'status': 'LISTE_PARCOURS_INVALIDE', 'required': True})
        declarations = []
    for i, row in enumerate(declarations):
        if not isinstance(row, dict) or (row.get('enabled', True) is not False and
                row.get('mode', 'non_renseigne') not in ('non_renseigne', *MODES)):
            cases.append({'kind': 'configuration', 'id': f'journeys[{i}]', 'mode': '', 'verdict': 'CONFIG_ERROR',
                          'status': 'CONFIGURATION_PARCOURS_INVALIDE', 'required': True})
    for mode in MODES:
        applicable = [dict(row, mode=mode) for row in declarations
                      if isinstance(row, dict) and row.get('enabled', True) is not False
                      and row.get('mode', 'non_renseigne') in ('non_renseigne', mode)]
        view = dict(snapshot)
        view['exchanges'] = [row for row in snapshot.get('exchanges', []) if row.get('mode') == mode]
        journeys = evaluate_journeys(applicable, view['exchanges'], snapshot.get('relations', []),
                                    dict(policy, mode=mode, strict_evidence=True))
        view['journeys'] = journeys
        for journey in journeys:
            status = journey['status']
            cases.append({'kind': 'parcours', 'id': journey['id'], 'mode': mode,
                          'verdict': ('PASS' if status == 'EVIDENCE_COMPLETE' else
                                      'CONFIG_ERROR' if status == 'CONFIG_INVALIDE' else
                                      'PARTIAL' if collected else 'BLOCKED'),
                          'status': status if collected or status == 'CONFIG_INVALIDE' else 'COLLECTE_INDISPONIBLE',
                          'required': journey['required'], 'details': journey})
        rows = matrix(decisions, view, dict(policy, strict_evidence=True))
        for row in rows:
            verdict, status = row['verdict'], row['status']
            if not collected and row['review_status'] == 'APPROVED':
                verdict, status = 'BLOCKED', 'COLLECTE_INDISPONIBLE'
            elif status == 'DEPOT_ABSENT_DU_PERIMETRE':
                verdict = 'BLOCKED'
            cases.append({'kind': 'frontiere', 'id': row['boundary_key'], 'mode': mode,
                          'source': row['source_repo'], 'target': row['target_repo'],
                          'verdict': verdict, 'status': status, 'required': row['required'] is True,
                          'details': row})
        represented = {row['boundary_key'] for row in rows if row['required'] is True}
        for row in snapshot.get('documentary_scope', {}).get('obligations', []):
            if row['boundary_key'] not in represented:
                cases.append({'kind': 'obligation-documentaire', 'id': row['boundary_key'], 'mode': mode,
                              'source': row['source'], 'target': row['target'],
                              'verdict': 'BLOCKED', 'status': 'DECISION_OBLIGATOIRE_MANQUANTE',
                              'required': True, 'details': row})
    counts = dict(Counter(row['verdict'] for row in cases))
    required = [row for row in cases if row['required']]
    return {'schema': 'koa.validation-integrale/v1', 'cases': cases, 'counts': counts,
            'required_total': len(required), 'required_pass': sum(r['verdict'] == 'PASS' for r in required),
            'collection_available': collected,
            'documentary_aligned': snapshot.get('documentary_scope', {}).get('aligned', False),
            'global_certified': False}


def write_assessment(report, run_root):
    target = run_root / 'validation-integrale.json'
    write_json(target, report)
    csv_path = run_root / 'exports' / 'validation-integrale.csv'
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ('kind', 'id', 'mode', 'source', 'target', 'required', 'verdict', 'status')
    with csv_path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter=';')
        writer.writeheader()
        for row in report['cases']:
            cells = {key: str(row.get(key, '')) for key in fields}
            writer.writerow({key: "'" + value if value.startswith(('=', '-', '+', '@', '\t', '\r', '\n'))
                             else value for key, value in cells.items()})
    return target, csv_path
