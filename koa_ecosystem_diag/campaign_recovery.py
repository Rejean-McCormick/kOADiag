# -*- coding: utf-8 -*-
"""Non-destructive reconciliation plan from a *completed* LevelUpDiag run.

No automatic changes to repository indexes, SHA pins, boundary decisions,
collection limits or IK evidence: these require an accountable source review.
"""
from __future__ import annotations

from pathlib import Path
import json
import re

MAX_DOCUMENT = 3_000_000
MAX_ROWS = 250


def read_bounded(folder: Path, filename: str):
    path = Path(folder)/filename
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_DOCUMENT:
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (ValueError, UnicodeError, OSError):
        return None


def clean(value, limit=180):
    if not isinstance(value, str):
        return ''
    # Render only relative identifiers with no URLs, shell syntax or secrets.
    value = value.replace('\\', '/').replace('\n', ' ').replace('\r', ' ')
    if not re.fullmatch(r'[a-zA-Z0-9À-ÿ ._@/()\-]+', value):
        return '[identifiant masqué]'
    return value[:limit]


def recovery_plan(run_dir: Path):
    """Give concrete grouped next actions; do not silently change any verdict."""
    run_dir = Path(run_dir)
    gap = read_bounded(run_dir, 'scan-gaps.json') or {}
    docs = read_bounded(run_dir, 'documentary-scope.json') or {}
    inventories = read_bounded(run_dir, 'inventory-alignment.json') or {}
    effective = read_bounded(run_dir, 'effective_config.json') or {}
    config = effective.get('interrepo') or {}
    plan = []
    for row in (gap.get('repos') or [])[:MAX_ROWS]:
        if not isinstance(row, dict):
            continue
        over = row.get('oversized_files', 0)
        unreadable = row.get('unreadable_files', 0)
        if not ((type(over) is int and over > 0) or (type(unreadable) is int and unreadable > 0)):
            continue
        dirs = [clean(d.get('directory')) for d in row.get('top_oversized_directories', [])[:8]
                if isinstance(d, dict)]
        plan.append({'id': 'SCAN_'+str(len(plan)), 'category': 'collecte', 'priority': 'P2',
                     'owner': clean(row.get('repo')), 'count': (over or 0)+(unreadable or 0),
                     'locations': dirs,
                     'action': 'Examiner ces dossiers et exclure les données non pertinentes, ou cibler une collecte segmentée autorisée. Ne pas augmenter globalement les limites.'})
    for doc in (docs.get('documents') or [])[:MAX_ROWS]:
        if not isinstance(doc, dict) or doc.get('status') == 'CONFORME':
            continue
        plan.append({'id': 'DOC_'+str(len(plan)), 'category': 'documentation', 'priority': 'P2',
                     'owner': 'Docs', 'file': clean(doc.get('path')),
                     'action': 'Revoir le contenu avec le dépôt auteur; actualiser son empreinte uniquement après approbation explicite.'})
    if inventories.get('aligned') is False:
        diag_only = inventories.get('diag_only') or []
        audit_only = inventories.get('audit_only') or []
        plan.append({'id': 'INVENTORY_DIFF', 'category': 'inventaire', 'priority': 'P2',
                     'owner': 'C0 / Audit',
                     'diag_only': [clean(x) for x in diag_only[:30]],
                     'audit_only': [clean(x) for x in audit_only[:30]],
                     'action': 'Rapprocher les instantanés datés; ne pas déclarer à jour un inventaire historique.'})
    exchange = config.get('exchange_trace_files')
    ik = (config.get('ik') or {}).get('trace_files')
    if isinstance(exchange, list) and isinstance(ik, list) and not exchange and not ik:
        plan.append({'id': 'TRACE_SOURCES_MISSING', 'category': 'preuves_e2e', 'priority': 'P1',
                     'owner': 'Orgo / Konnaxion',
                     'action': 'Produire des exports de preuve assainis depuis les dépôts propriétaires, puis déclarer les fichiers et empreintes dans la configuration locale de kOADiag. Aucun log brut ni jeton.'})
    return {'schema': 'koa.diag.campaign-recovery.v1',
            'items': plan,
            'counts': {cat:sum(r['category']==cat for r in plan)
                       for cat in ('collecte','documentation','inventaire','preuves_e2e')},
            'warning': 'Plan de remédiation dérivé des preuves : aucun fichier source, verdict ou empreinte modifié.'}
