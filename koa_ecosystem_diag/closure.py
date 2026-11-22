"""Report what remains after a complete validation campaign."""
from collections import Counter

from .framework import write_json

MODES = ('autonome', 'integre')
NEXT_ACTION = {
    'REPONSE_NON_TERMINALE': 'Exporter le reçu terminal émis par le récepteur après traitement.',
    'REPONSE_NON_VALIDEE': 'Exporter la réponse réellement émise par le récepteur et son statut.',
    'REVISION_NON_VERIFIEE': 'Relever les révisions des services réellement déployés et les inclure dans les exports.',
    'CONTRAT_SANS_PREUVE_RUNTIME': 'Exécuter le contrat sur les versions actives et exporter les observations des deux services.',
    'QUALIFICATION_DU_PROFIL_HISTORIQUE_REQUISE': 'Faire confirmer le profil historique par les propriétaires avant de qualifier son exécution.',
    'PARCOURS_DECLARE_NON_PROUVE': 'Exécuter ce parcours dans le mode indiqué et fournir les preuves de chaque saut.',
    'TRANSACTIONS_DISJOINTES': 'Vérifier la propagation de la même corrélation native sur tous les sauts.',
    'PREUVE_EXPIREE': 'Capturer de nouvelles observations après une exécution du parcours.',
    'COLLECTE_PARTIELLE': 'Vérifier le périmètre du dépôt et les fichiers signalés dans scan-gaps.json.',
}
TERMINAL_ERRORS = {'FAIL', 'ERROR', 'CONFIG_ERROR', 'INFRA_ERROR', 'BLOCKED'}


def _progress(cases):
    return {'pass': sum(row['verdict'] == 'PASS' for row in cases), 'total': len(cases)}


def assess(summary, validation, inventory_alignment=None):
    cases = validation.get('cases', [])
    required = [row for row in cases if row['required']]
    boundaries = [row for row in required if row['kind'] in ('frontiere', 'obligation-documentaire')]
    mode_progress = {mode: _progress([row for row in boundaries if row['mode'] == mode])
                     for mode in MODES}
    blockers = []
    for row in required:
        if row['verdict'] == 'PASS':
            continue
        item = {key: row[key] for key in ('kind', 'id', 'mode', 'source', 'target', 'status', 'verdict')
                if key in row}
        if row['kind'] == 'parcours':
            item['hops_remaining'] = [
                {key: hop[key] for key in ('source', 'target', 'contract', 'status') if key in hop}
                for hop in row.get('details', {}).get('hops', [])
                if hop.get('status') != 'FRONTIERE_CORROBOREE']
        elif row['kind'] == 'frontiere':
            item['declared_journeys'] = row.get('details', {}).get('declared_journeys', 0)
            technical = row.get('details', {}).get('technical_reconciliation', {})
            if technical:
                item['historical_contract'] = technical.get('historical_contract')
                item['technical_status'] = technical.get('status')
        elif row['kind'] == 'depot':
            item['collection_gaps'] = {key: row.get('details', {}).get(key, 0) for key in
                                       ('unselected_files', 'oversized_files', 'unreadable_files')}
        codes = [item['status'], *(hop['status'] for hop in item.get('hops_remaining', [])
                                   if 'status' in hop)]
        item['next_actions'] = list(dict.fromkeys(NEXT_ACTION[code] for code in codes
                                                  if code in NEXT_ACTION))
        if not item['next_actions'] and row['kind'] == 'parcours':
            item['next_actions'] = ['Consulter les motifs de chaque saut dans validation-integrale.json.']
        blockers.append(item)
    unresolved_reviews = {row['id'] for row in cases if row['kind'] == 'frontiere'
                          and row.get('details', {}).get('review_status') == 'UNREVIEWED'}
    optional_unproven = {row['id'] for row in cases if row['kind'] == 'frontiere'
                         and row.get('details', {}).get('review_status') == 'APPROVED'
                         and not row['required'] and row['verdict'] != 'PASS'}
    level_errors = [{'id': row['id'], 'verdict': row['verdict']} for row in summary['levels']
                    if row['verdict'] in TERMINAL_ERRORS]
    scope = validation.get('documentary_aligned') is True
    collection = validation.get('collection_available') is True
    expected = set(summary.get('expected_levels', []))
    ran_all_levels = bool(expected and expected == {row['id'] for row in summary['levels']})
    ready = (scope and collection and ran_all_levels and not blockers and not level_errors
             and all(value['total'] > 0 for value in mode_progress.values()))
    alignment = inventory_alignment or {}
    return {
        'inventory_alignment': {key: alignment[key] for key in ('source', 'aligned', 'diag_only', 'audit_only')
                                if key in alignment},
        'schema': 'koa.cloture/v1', 'run_id': summary['run_id'], 'suite_version': summary['suite_version'],
        'status': 'PRET_POUR_REVUE_FINALE' if ready else 'VALIDATIONS_RESTANTES',
        'campaign_verdict': summary['verdict'], 'all_levels_reported': ran_all_levels,
        'collection_available': collection, 'documentary_aligned': scope,
        'required_by_kind': {kind: _progress([row for row in required if row['kind'] == kind])
                             for kind in sorted({row['kind'] for row in required})},
        'mandatory_boundaries_by_mode': mode_progress,
        'remaining_counts': dict(Counter(row['kind'] for row in blockers)),
        'remaining': blockers, 'level_errors': level_errors,
        'human_review_pending': sorted(unresolved_reviews), 'optional_unproven': sorted(optional_unproven),
        'certification': 'DECISION_HUMAINE',
    }


def write_report(directory, report):
    write_json(directory / 'cloture.json', report)
    lines = ['Diagnostic kOA · Clôture', f"Campagne {report['run_id']}", report['status'], '',
             'Frontières obligatoires corroborées']
    lines.extend(f"- {mode} : {progress['pass']}/{progress['total']}"
                 for mode, progress in report['mandatory_boundaries_by_mode'].items())
    lines += ['', f"Décisions de revue ouvertes : {len(report['human_review_pending'])}",
              f"Frontières optionnelles à documenter : {len(report['optional_unproven'])}",
              f"Sources documentaires alignées : {'oui' if report['documentary_aligned'] else 'non'}",
              '', 'Contrôles obligatoires à reprendre']
    for row in report['remaining']:
        route = f" ({row['source']} → {row['target']})" if row.get('source') and row.get('target') else ''
        lines.append(f"- {row['kind']} · {row['id']}{route} {row['mode']} · {row['status']}")
        lines.extend(f"  {action}" for action in row.get('next_actions', []))
    alignment = report.get('inventory_alignment', {})
    for key, label in (('diag_only', 'Diag seulement'), ('audit_only', 'Audit seulement')):
        if alignment.get(key):
            lines.append(f"- Inventaire · {label} · {', '.join(alignment[key])}")
    lines.extend(f"- niveau {row['id']} · {row['verdict']}" for row in report['level_errors'])
    lines += ['', 'Consulter cloture.json pour les détails. La décision de certification appartient au responsable.']
    (directory / 'cloture.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
