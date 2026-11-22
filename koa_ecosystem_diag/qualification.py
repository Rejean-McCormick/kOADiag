# -*- coding: utf-8 -*-
"""Per-boundary evidence matrix and scope coverage."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from .journeys import hop_status

FIELDS = ['boundary_key', 'source_repo', 'target_repo', 'review_status', 'required', 'protocol',
          'observed', 'documented', 'contract_status', 'static_contract', 'passive_pairs',
          'attested_pairs', 'fresh_attested_pairs', 'declared_journeys', 'matching_journeys',
          'autonomous_journeys', 'integrated_journeys', 'verdict', 'status', 'reason']


def matrix(registry, snapshot, policy=None):
    policy = policy or {}
    clock = datetime.now(timezone.utc)
    exchanges = snapshot.get('exchanges', [])
    static = snapshot.get('expected_api_links', [])
    events = snapshot.get('events', [])
    journeys = snapshot.get('journeys', [])
    profiles = snapshot.get('ik_profile_validation', {})
    scopes = {r['boundary_key']: r for r in snapshot.get('documentary_scope', {}).get('obligations', [])}
    scanned = {r['repo']: r for r in snapshot.get('repositories', [])}
    records = []
    for entry in registry.get('relations', []):
        src, dst = entry['source_repo'], entry['target_repo']
        contract = entry.get('contract') or ''
        protocol = entry.get('protocol', '')
        scope = scopes.get(entry['boundary_key'], {})
        historical = scope.get('technical_reconciliation', {})
        historical_valid = historical.get('status') in ('REFERENCE_FIGEE_VALIDEE', 'REFERENCE_HISTORIQUE_VALIDEE')
        exact_contract = historical.get('historical_contract') if historical_valid else contract

        def belongs(row):
            return (row.get('source') == src and row.get('target') == dst
                    and str(row.get('contract') or '') == exact_contract)

        def exact(row):
            return (belongs(row)
                    and (not entry.get('method') or row.get('method') == entry['method'])
                    and (not entry.get('route') or row.get('path') == entry['route'])
                    and (not entry.get('event_channel') or row.get('channel') == entry['event_channel']))

        outgoing = [e for e in exchanges if exact(e)]
        pairs = [e for e in outgoing if e.get('status') == 'PAIRE_OBSERVEE']
        attest = [e for e in pairs if e.get('provenance_attested') and e.get('independent_sources')]
        fresh = [e for e in attest if hop_status(e, protocol != 'EVENT', policy, clock)[0] == 'FRONTIERE_CORROBOREE']
        matched_api = any(e.get('id') == 'registry-' + entry['boundary_key']
                          and e.get('status') == 'APPEL_ET_ROUTE_STATIQUES' for e in static)
        matched_event = any(e.get('source') == src and e.get('target') == dst
                            and e.get('channel') == entry.get('event_channel')
                            and e.get('status') == 'NOM_COMMUN_STATIQUE' for e in events)
        profile = profiles.get(contract)
        documented = entry.get('review_status') == 'APPROVED' or bool(entry.get('comment'))
        contract_status = 'DECLARE' if documented or contract else 'NON_SPECIFIE'
        if profile:
            if profile.get('status') != 'VALIDE':
                contract_status = profile.get('status', 'NON_VERIFIE')
            elif src.casefold() in {x.casefold() for x in profile['sources']} and dst.casefold() in {
                    x.casefold() for x in profile['targets']}:
                contract_status = 'VALIDE'
            else:
                contract_status = 'ECART'
        elif protocol == 'IK':
            contract_status = 'NON_VERIFIE'
        elif matched_api or matched_event:
            contract_status = 'CORRESPONDANCE_STATIQUE'
        declared = [j for j in journeys if any(belongs(h) for h in j.get('hops', []))]
        proven = [j for j in declared if j.get('status') == 'EVIDENCE_COMPLETE'
                  and any(exact(h) and h.get('status') == 'FRONTIERE_CORROBOREE' for h in j['hops'])]
        if historical:
            contract_status = historical['status']
        absent = bool(scanned) and any(not scanned.get(name, {}).get('exists') for name in (src, dst))
        review = entry.get('review_status')
        verdict = 'PARTIAL'
        if review != 'APPROVED':
            status = 'HORS_PERIMETRE' if review == 'REJECTED' else 'REVUE_REQUISE'
            verdict = 'SKIP' if review in ('REJECTED', 'DEFERRED') else 'PARTIAL'
        elif absent:
            status = 'DEPOT_ABSENT_DU_PERIMETRE'
        elif contract_status in ('ECART', 'ECART_REFERENCE_FIGEE'):
            status, verdict = 'CONTRAT_INCOMPATIBLE', 'FAIL'
        elif historical and not historical_valid:
            status = 'QUALIFICATION_DU_PROFIL_HISTORIQUE_REQUISE'
        elif protocol == 'IK' and contract_status != 'VALIDE' and not historical_valid:
            status = 'CONTRAT_IK_NON_VERIFIE'
        elif proven:
            status, verdict = 'PARCOURS_CORROBORE', 'PASS'
        elif fresh:
            status = 'PAIRE_ATTESTEE_NON_E2E'
        elif attest:
            status = hop_status(attest[0], protocol != 'EVENT', policy, clock)[0]
        elif pairs:
            status = 'PAIRE_NON_ATTESTEE'
        elif declared:
            status = 'PARCOURS_DECLARE_NON_PROUVE'
        elif documented:
            status = 'CONTRAT_SANS_PREUVE_RUNTIME'
        else:
            status = 'AUCUNE_PREUVE'
        reasons = [status.replace('_', ' ').lower()]
        if entry.get('required') and not declared:
            reasons.append('frontière obligatoire hors parcours déclaré')
        if entry.get('required') and not entry.get('observed'):
            reasons.append('frontière obligatoire non retrouvée dans la cartographie')
        records.append({
            'boundary_key': entry['boundary_key'], 'source_repo': src, 'target_repo': dst,
            'review_status': review, 'required': entry.get('required'), 'protocol': protocol,
            'observed': bool(entry.get('observed')), 'documented': documented,
            'contract_status': contract_status, 'static_contract': historical_valid or contract_status in ('VALIDE', 'CORRESPONDANCE_STATIQUE'),
            'passive_pairs': len(pairs), 'attested_pairs': len(attest), 'fresh_attested_pairs': len(fresh),
            'declared_journeys': len(declared), 'matching_journeys': len(proven) if verdict == 'PASS' else 0,
            'autonomous_journeys': sum(j.get('mode') == 'autonome' for j in proven) if verdict == 'PASS' else 0,
            'integrated_journeys': sum(j.get('mode') == 'integre' for j in proven) if verdict == 'PASS' else 0,
            'status': status, 'verdict': verdict, 'reason': '. '.join(reasons),
            'technical_reconciliation': historical,
            'documented_profile': scope.get('documented_profile'), 'decision_comment': entry.get('comment', ''),
            'exchange_findings': [
                {'status': hop_status(e, protocol != 'EVENT', policy, clock)[0],
                 'mode': e.get('mode'), 'transaction': e.get('hash'), 'attempt': e.get('attempt_hash'),
                 'response_status': e.get('response_status')}
                for e in outgoing[:25]],
        })
    return records


def summary(rows, scope=None):
    required = [r for r in rows if r['review_status'] == 'APPROVED' and r['required'] is True]
    return {
        'registered': len(rows), 'required': len(required),
        'required_in_journey': sum(r['declared_journeys'] > 0 for r in required),
        'required_without_journey': sum(not r['declared_journeys'] for r in required),
        'required_declared_unproven': sum(r['declared_journeys'] > 0 and not r['matching_journeys'] for r in required),
        'required_proven': sum(r['matching_journeys'] > 0 for r in required),
        'required_unproven': sum(not r['matching_journeys'] for r in required),
        'required_missing_repos': sum(r['status'] == 'DEPOT_ABSENT_DU_PERIMETRE' for r in required),
        'required_not_mapped': sum(not r['observed'] for r in required),
        'required_autonomous_proven': sum(r['autonomous_journeys'] > 0 for r in required),
        'required_integrated_proven': sum(r['integrated_journeys'] > 0 for r in required),
        'documentary_aligned': bool((scope or {}).get('aligned')),
        'required_scope_complete': bool(required and (scope or {}).get('aligned')
                                        and all(r['observed'] and r['matching_journeys'] for r in required)),
        'review_pending': sum(r['status'] == 'REVUE_REQUISE' for r in rows),
        'attested_not_e2e': sum(r['attested_pairs'] > 0 and not r['matching_journeys'] for r in rows),
        'global_certified': False,
    }


def export_csv(rows, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    def safe(value):
        t = '' if value is None else str(value)
        return "'" + t if t and t[0] in ('=', '+', '-', '@', '\n', '\r', '\t') else t
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, delimiter=';')
        writer.writeheader()
        for row in rows:
            writer.writerow({key: safe(row.get(key)) for key in FIELDS})
    return path
