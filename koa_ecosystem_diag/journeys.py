# -*- coding: utf-8 -*-
"""Passive multi-repository transaction continuity: one correlation for ALL hops.

A separate successful pair for each hop is NOT a complete journey. To label a
journey EVIDENCE_COMPLETE, the same transaction must cross every hop in order,
with distinct owner-declared sender/receiver exports and fresh time evidence.
These are observations, never cryptographic attestation or total certification.
"""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timezone, timedelta
import hashlib
import re

SHELL_REPOS = frozenset(('Koali', 'Koali-Control-Panel'))


def _norm(value):return re.sub(r'[^a-z0-9]','',str(value or '').casefold())


def _dt(value):
    try:
        dt=datetime.fromisoformat(value.replace('Z','+00:00'))
        return dt.astimezone(timezone.utc) if dt.tzinfo else None
    except (AttributeError,ValueError,TypeError):return None


def hop_status(item, response_required, policy, clock, prior_end=None):
    if item.get('status') == 'TENTATIVES_AMBIGUES':
        return 'TENTATIVES_AMBIGUES', None
    if item.get('status') != 'PAIRE_OBSERVEE':
        return item.get('status', 'RECEPTION_MANQUANTE'), None
    if not item.get('independent_sources'):
        return 'SOURCES_NON_INDEPENDANTES', None
    if response_required and not item.get('response_ok'):
        return 'REPONSE_NON_VALIDEE', None
    if not item.get('provenance_attested'):
        return 'PROVENANCE_NON_ATTESTEE', None
    if response_required and not item.get('response_provenance'):
        return 'REPONSE_NON_ATTESTEE', None
    strict = policy.get('strict_evidence') is True
    if item.get('revision_status') == 'INCOMPATIBLE':
        return 'REVISION_INCOMPATIBLE', None
    if item.get('contract_status') == 'ECART':
        return 'CONTRAT_INCOMPATIBLE', None
    if strict:
        if response_required and str(item.get('response_status','')).lower() in ('202', 'accepted'):
            return 'REPONSE_NON_TERMINALE', None
        if not item.get('attempt_hash'):
            return 'TENTATIVE_NON_IDENTIFIEE', None
        if item.get('mode') not in ('autonome', 'integre'):
            return 'MODE_NON_RENSEIGNE', None
        if not item.get('digest_pinned'):
            return 'EMPREINTE_NON_VERIFIEE', None
        if item.get('revision_status') != 'ALIGNEE':
            return 'REVISION_NON_VERIFIEE', None
    timestamp = _dt(item.get('occurred_at'))
    end = _dt(item.get('responded_at') if response_required else item.get('received_at'))
    if strict or policy.get('require_timestamps', True) is not False:
        max_age = policy.get('max_age_hours', 168)
        if type(max_age) is not int or not 1 <= max_age <= 8760:
            max_age = 168
        if not item.get('timestamps_valid') or not timestamp or not end:
            return 'HORODATAGE_NON_VERIFIE', None
        if clock - timestamp > timedelta(hours=max_age) or end > clock + timedelta(minutes=5):
            return 'PREUVE_EXPIREE', None
        if prior_end and timestamp < prior_end:
            return 'ORDRE_TRANSACTION_INCOHERENT', None
    return 'FRONTIERE_CORROBOREE', end


def evaluate_journeys(declarations, exchanges, relations, policy=None):
    policy = policy if isinstance(policy, dict) else {}
    clock = datetime.now(timezone.utc)
    result = []
    if not isinstance(declarations, list):
        return result
    catalog = {(_norm(r.get('source')), _norm(r.get('target')), r.get('contract', ''))
               for r in relations}
    index = {}
    for e in exchanges:
        key = (e.get('journey_hash'), _norm(e.get('source')), _norm(e.get('target')))
        index.setdefault(key, []).append(e)
    enabled_ids = [str(d.get('id') or '').strip()[:100] for d in declarations[:120]
                   if isinstance(d, dict) and d.get('enabled', True) is not False]
    duplicate_ids = {name for name, count in Counter(enabled_ids).items() if count > 1}
    for declaration in declarations[:120]:
        if not isinstance(declaration, dict) or declaration.get('enabled', True) is False:
            continue
        name = str(declaration.get('id') or '').strip()[:100]
        nodes = declaration.get('nodes')
        required = bool(declaration.get('required', True))
        response_required = bool(declaration.get('require_response', True))
        mode = declaration.get('mode', policy.get('mode', 'non_renseigne'))
        refs = declaration.get('contract_refs')
        valid_nodes = isinstance(nodes, list) and 2 <= len(nodes) <= 30 and all(
            isinstance(n, str) and n.strip() for n in nodes)
        valid_refs = refs is None or (valid_nodes and isinstance(refs, list)
                     and len(refs) == len(nodes) - 1 and all(isinstance(x, str) for x in refs))
        valid_mode = (mode in ('autonome', 'integre', 'non_renseigne')
                      and not (mode == 'autonome' and valid_nodes and any(n in SHELL_REPOS for n in nodes)))
        if not name or name in duplicate_ids or not valid_nodes or not valid_refs or not valid_mode:
            result.append({'id': name or '(invalide)', 'status': 'CONFIG_INVALIDE', 'required': required,
                           'reason': 'Vérifier id, nodes, mode et contract_refs', 'hops': [], 'verified_hops': 0})
            continue
        journey_hash = hashlib.sha256(name.encode()).hexdigest()[:16]
        hop_pairs = list(zip(nodes, nodes[1:]))
        refs = refs if refs is not None else [''] * len(hop_pairs)
        by_hop = []
        for (source, target), contract in zip(hop_pairs, refs):
            possible = index.get((journey_hash, _norm(source), _norm(target)), [])
            groups = {}
            for item in possible:
                item_mode = item.get('mode', 'non_renseigne')
                if not item.get('hash') or item.get('contract', '') != contract:
                    continue
                if item_mode == 'autonome' and any(n in SHELL_REPOS for n in nodes):
                    continue
                if mode != 'non_renseigne' and item_mode != mode:
                    continue
                groups.setdefault((item['hash'], item_mode), []).append(item)
            by_hop.append(groups)
        transactions = set().union(*(groups.keys() for groups in by_hop))
        best, best_count = [], -1
        for transaction in sorted(transactions) or [('', mode)]:
            hops, verified, previous = [], 0, None
            used_attempts = set()
            for (source, target), contract, groups in zip(hop_pairs, refs, by_hop):
                options = groups.get(transaction, [])
                ranked = []
                for item in options:
                    status, end = hop_status(item, response_required, policy, clock, previous)
                    attempt = (source, target, item.get('attempt_hash'))
                    if attempt in used_attempts:
                        status = 'TENTATIVE_DEJA_UTILISEE'
                    ranked.append((status, end, item, attempt))
                successful = [x for x in ranked if x[0] == 'FRONTIERE_CORROBOREE']
                if successful:
                    status, end, item, attempt = min(successful, key=lambda x: (x[1] is None, x[1]))
                    previous = end or previous
                    verified += 1
                    used_attempts.add(attempt)
                elif ranked:
                    status, _, item, _ = ranked[0]
                else:
                    status, item = 'PREUVE_MANQUANTE', {}
                hops.append({
                    'source': source, 'target': target, 'contract': contract, 'status': status,
                    'method': item.get('method', ''), 'path': item.get('path', ''), 'channel': item.get('channel', ''),
                    'relation_reference_present': (_norm(source), _norm(target), contract) in catalog,
                    'correlation_hash': transaction[0], 'attempt_hash': item.get('attempt_hash', ''),
                    'mode': transaction[1], 'evidence_files': item.get('evidence', []),
                    'evidence_sha256': item.get('evidence_sha256', {}),
                    'complementary_observations': item.get('complementary_observations', []),
                    'response_observed': bool(item.get('response_observed')), 'response_ok': bool(item.get('response_ok')),
                    'occurred_at': item.get('occurred_at'), 'received_at': item.get('received_at'),
                    'responded_at': item.get('responded_at'), 'observed_revisions': item.get('observed_revisions', []),
                })
            if verified > best_count:
                best, best_count = hops, verified
            if verified == len(hop_pairs):
                break
        complete = best_count == len(hop_pairs)
        observed = [{key for key, rows in hop.items() if any(r['status'] == 'PAIRE_OBSERVEE' for r in rows)}
                    for hop in by_hop]
        disjoint = all(observed) and not set.intersection(*observed)
        status = 'EVIDENCE_COMPLETE' if complete else (
            'TRANSACTIONS_DISJOINTES' if disjoint else 'PREUVES_INSUFFISANTES')
        result.append({
            'id': name, 'journey_hash': journey_hash, 'required': required, 'nodes': nodes,
            'contract_refs': refs, 'status': status, 'mode': best[0]['mode'] if best else mode,
            'reason': ('Transaction unique corroborée sur tous les sauts' if complete else
                       'Consulter le statut détaillé de chaque saut'),
            'hops': best, 'verified_hops': best_count, 'require_response': response_required,
            'observed_transactions': len(transactions), 'evidence_scope': 'PASSIVE_ONLY',
        })
    return result
