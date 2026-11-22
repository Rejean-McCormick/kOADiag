# -*- coding: utf-8 -*-
"""Non-authoritative diagnostic/audit inventory reconciliation.

The shipped Audit inventory is a dated snapshot, never silently an official
live registry. A fresh local file can be supplied by the operator later.
"""
from __future__ import annotations
import json
from pathlib import Path

LOCAL_NAME = 'koa-ecosystem-diag.audit-inventory.local.json'
SNAPSHOT_NAME = 'audit-inventory.20261110.json'


def _repo_ids(payload):
    values = payload if isinstance(payload, list) else payload.get('github_repos', payload.get('repositories', []))
    if not isinstance(values, list):raise ValueError('Liste inventaire Audit invalide')
    out = set()
    for item in values:
        value = item.get('github_repo') if isinstance(item, dict) else item
        if not isinstance(value,str) or '/' not in value or len(value) > 180:
            raise ValueError('Identifiant de dépôt invalide')
        out.add(value)
    return out


def compare(tool: Path, audit_root: Path | None = None) -> dict:
    tool=Path(tool).resolve()
    diag=tool/'koa_ecosystem_diag'/'references'/'repositories.json'
    local=tool/LOCAL_NAME
    source='local_override' if local.is_file() else 'dated_snapshot_2026-11-10'
    audit=local if source=='local_override' else tool/'koa_ecosystem_diag'/'references'/SNAPSHOT_NAME
    if audit_root:
        current = audit_root / 'data' / 'initial_inventory.json'
        if current.is_file() and not local.is_file():
            source, audit = 'local_audit_initial_inventory', current
    for p in (diag,audit):
        if p.is_symlink() or p.stat().st_size > 800_000:
            raise ValueError('Fichier inventaire trop grand ou lien symbolique')
    with diag.open(encoding='utf-8-sig') as f:d=json.load(f)
    with audit.open(encoding='utf-8-sig') as f:a=json.load(f)
    ours=_repo_ids(d);other=_repo_ids(a)
    return {'source':source, 'diag_count':len(ours),'audit_count':len(other),
            'common':len(ours & other), 'diag_only':sorted(ours-other),
            'audit_only':sorted(other-ours),
            'aligned':ours==other,
            'qualification':'MAPPING_A_REVOIR' if ours != other else 'SNAPSHOT_ALIGNE_NON_CERTIFIANT'}
