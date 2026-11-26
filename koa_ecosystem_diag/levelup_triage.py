# -*- coding: utf-8 -*-
"""Passive, bounded interpretation of LevelUpDiag report evidence.

Consumes ONLY the reports produced by the existing campaign. Never imports
secret payloads, changes verdicts, manufactures proof, or triggers services.
"""
from __future__ import annotations

from pathlib import Path
import json
import re

MAX_BYTES = 2_000_000
MAX_LEVELS = 100
MAX_FINDINGS = 90
_ALLOWED_STATUSES = {'PASS', 'WARN', 'FAIL', 'SKIP', 'BLOCKED', 'PARTIAL',
                     'ERROR', 'CONFIG_ERROR', 'INFRA_ERROR'}


def _read(path: Path):
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_BYTES:
        raise ValueError('Rapport manquant, symbolique ou dépassant la limite de lecture')
    return json.loads(path.read_text(encoding='utf-8-sig'))


def _safe_text(value, size=260):
    if not isinstance(value, str):
        return ''
    value = value.replace('\n', ' ').replace('\r', ' ')
    # Avoid accidentally copying the most common forms of credential values
    # from diagnostic messages into shareable central reports.
    value = re.sub(r'(?i)\b(password|token|secret|api[_-]?key|authorization)\s*[:=]\s*\S+',
                   r'\1=[MASQUÉ]', value)
    value = re.sub(r'(?i)\b(?:https?://)[^\s]+', '[URL masquée]', value)
    return value[:size]


def _cause(code, priority, title, detail, action, related):
    return {'id': code, 'priorite': priority, 'titre': title, 'detail': detail,
            'action': action, 'niveaux': related, 'resolu': False}


def interpret_report(report_path: Path, *, trusted_reports_root: Path | None = None) -> dict:
    """Read an existing LevelUpDiag run, without changing its verdict.

    When trusted_reports_root is supplied, only accept a summary within the
    controlled reports tree (not a user-provided arbitrary filesystem path).
    """
    report_path = Path(report_path).resolve()
    if report_path.name != 'summary.json':
        raise ValueError('Seul summary.json LevelUpDiag est accepté')
    if trusted_reports_root is not None:
        expected = Path(trusted_reports_root).resolve()
        if not report_path.is_relative_to(expected):
            raise ValueError('Rapport hors du répertoire LevelUpDiag autorisé')
    folder = report_path.parent
    summary = _read(report_path)
    if summary.get('schema') != 'levelupdiag.campaign-summary.v2':
        raise ValueError('Schéma LevelUpDiag incorrect')
    levels_in = summary.get('levels', [])
    if not isinstance(levels_in, list) or len(levels_in) > MAX_LEVELS:
        raise ValueError('Liste de niveaux invalide')
    run_id = summary.get('run_id', '')
    if not isinstance(run_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,90}', run_id):
        raise ValueError('Identifiant de campagne invalide')
    levels = []
    for meta in levels_in:
        if not isinstance(meta, dict):
            continue
        lid = meta.get('id', '')
        if not isinstance(lid, str) or not re.fullmatch(r'N\d{2,3}', lid):
            continue
        status = meta.get('verdict', 'INCONNU')
        if status not in _ALLOWED_STATUSES:
            status = 'INCONNU'
        item = {'id': lid, 'nom': _safe_text(meta.get('name'), 130), 'verdict': status,
                'constats': [], 'erreur_lecture': ''}
        level_path = folder/'levels'/lid/'result.json'
        try:
            report = _read(level_path)
            if report.get('schema') != 'levelupdiag.report.v2' or report.get('level_id') != lid or report.get('run_id') != run_id:
                raise ValueError('Résultat de niveau incohérent avec la campagne')
            findings = report.get('findings', [])
            if not isinstance(findings, list):
                raise ValueError('Constats de niveau invalides')
            for finding in findings[:MAX_FINDINGS]:
                if not isinstance(finding, dict):
                    continue
                verdict = finding.get('verdict')
                if verdict not in _ALLOWED_STATUSES:
                    continue
                item['constats'].append({
                    'id': _safe_text(finding.get('id'), 130),
                    'verdict': verdict,
                    'categorie': _safe_text(finding.get('category'), 80),
                    'message': _safe_text(finding.get('message'), 320),
                    'recommandation': _safe_text(finding.get('recommendation'), 320),
                })
        except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
            item['erreur_lecture'] = type(exc).__name__
        levels.append(item)

    cover = summary.get('coverage') or {}
    if not isinstance(cover, dict):cover = {}
    inv = cover.get('inventory') or {}
    boundaries = cover.get('boundary_evidence') or {}
    traces = cover.get('traces') or {}
    journeys = cover.get('journeys') or {}
    reg = cover.get('boundary_registry') or {}
    alignment = cover.get('inventory_alignment') or {}
    effective = folder/'effective_config.json'
    source_count = {'exchange_trace_files': None, 'ik.trace_files': None}
    if effective.is_file():
        try:
            cfg = _read(effective).get('interrepo') or {}
            ex = cfg.get('exchange_trace_files', None)
            ik = (cfg.get('ik') or {}).get('trace_files', None)
            source_count = {'exchange_trace_files': len(ex) if isinstance(ex, list) else None,
                            'ik.trace_files': len(ik) if isinstance(ik, list) else None}
        except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):
            pass

    def num(mapping, key):
        x = mapping.get(key, 0) if isinstance(mapping, dict) else 0
        return x if type(x) is int and x >= 0 else 0

    causes = []
    oversized = num(inv, 'oversized_files')
    unreadable = num(inv, 'unreadable_files')
    if oversized or unreadable:
        causes.append(_cause('COLLECTE_INCOMPLETE', 'P1', 'Collecte partielle',
            f'{oversized} fichiers trop volumineux et {unreadable} illisibles. Aucune analyse complète de ces fichiers.',
            'Examiner les fichiers/dossiers listés dans N01 et adapter les limites ou sources ciblées, sans les déclarer PASS.',
            ['N01']))
    req = num(boundaries, 'required_unproven')
    if req:
        causes.append(_cause('FRONTIERES_NON_PROUVEES', 'P1', 'Frontières obligatoires non démontrées',
            f'{req} frontières obligatoires sans preuve E2E qualifiée.',
            'Collecter des événements émis, reçus et réponses corrélés, valider contrats et révisions dans les deux modes.',
            ['N01','N09','N12','N13']))
    pairs = num(traces, 'correlated_pairs')
    receipts = num(traces, 'ik_receipts')
    if summary.get('selection') == 'validation-intermediaire' and not traces:
        causes.append(_cause('COLLECTE_NON_ABOUTIE', 'P1', 'Collecte de preuves non aboutie',
            'La collecte de traces ne fournit aucun résultat exploitable dans cette campagne.',
            'Consulter le rapport de N01, puis relancer une collecte ciblée.', ['N01','N09']))
    elif pairs == 0 and receipts == 0:
        more = ('Aucune source déclarée dans les deux configurations.'
                if source_count['exchange_trace_files'] == 0 and source_count['ik.trace_files'] == 0
                else 'Vérifier le chargement effectif et le format des sources déclarées.')
        causes.append(_cause('PREUVES_TRACES_ABSENTES', 'P1', 'Traces IK non corroborées',
            '0 paire corrélée, 0 reçu IK. '+more,
            'Configurer des fichiers JSON/JSONL d’exports de preuves déjà produits dans les dépôts propriétaires ; ne pas importer de logs bruts/secrets.',
            ['N09','N11','N12']))
    unproven = num(journeys, 'not_proven')
    if unproven:
        causes.append(_cause('PARCOURS_NON_PROUVES', 'P1', 'Parcours métier incomplets',
            f'{unproven} parcours déclaré(s) ne possède(nt) pas une chaîne de preuves complète.',
            'Associer les observations aux sauts du parcours, avec corrélation, timestamps, réponse et révisions.',
            ['N12','N13']))
    if any(x['id']=='N14' and x['verdict']=='SKIP' for x in levels):
        causes.append(_cause('E2E_OFFICIEL_NON_EXECUTE', 'P2', 'Test métier officiel non exécuté',
            'Le niveau N14 n’a pas exécuté de transaction authentifiée.',
            'Exécuter le kit officiel séparément et uniquement sur une pile de test isolée, après confirmation des bases.',
            ['N14']))
    review = num(reg, 'new_or_unreviewed')
    if review:
        causes.append(_cause('QUALIFICATION_A_COMPLETER', 'P2', 'Frontières à qualifier',
            f'{review} frontières nouvelles ou non revues.',
            'Soumettre au registre des frontières pour décision humaine. Ne jamais les approuver automatiquement.',
            ['N01','N13']))
    if alignment.get('aligned') is False:
        causes.append(_cause('INVENTAIRES_DIVERGENTS', 'P2', 'Inventaires documentaires divergents',
            f'Diagnostic {num(alignment,"diag_count")}, référence Audit {num(alignment,"audit_count")}.',
            'Comparer les inventaires datés et mettre à jour la source de référence après révision.',
            ['N00']))
    counts = summary.get('validation_integrale') or {}
    return {'schema': 'koa.diag.levelup.triage.v1', 'run_id': run_id,
            'verdict_source': summary.get('verdict', 'INCONNU'),
            'niveaux': levels, 'causes': causes, 'sources_configurees': source_count,
            'requis_pass': num(counts, 'required_pass'), 'requis_total': num(counts, 'required_total'),
            'collecte': {'depots_presents': num(inv,'present'),
                        'depots_declares': num(inv,'declared'),
                        'fichiers_surdimensionnes': oversized,
                        'fichiers_illisibles': unreadable},
            'limites': 'Interprétation passive ; ces constats ne constituent ni un test E2E ni une réparation automatique.'}
