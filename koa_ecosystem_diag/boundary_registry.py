# -*- coding: utf-8 -*-
"""Persistent, reviewable inter-repository boundary registry.

Local state belongs to the diagnostic, never to any target repository. The
scanner may add observations but can never approve, reject or certify them.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 'koa.ecosystem-boundary-registry/v1'
FILENAME = 'koa-ecosystem-diag.boundaries.local.json'
STATES = frozenset(('UNREVIEWED', 'APPROVED', 'REJECTED', 'DEFERRED'))
PROTOCOLS = frozenset(('', 'HTTP', 'EVENT', 'IK', 'PACKAGE', 'CI', 'OTHER'))
METHODS = frozenset(('', 'GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'))


def key_for(source: str, target: str, contract: str) -> str:
    # Retain v5.1's CSV identity so earlier reviews can be matched.
    return hashlib.sha256((source + '\0' + target + '\0' + contract).encode('utf-8')).hexdigest()[:20]


def path_for(tool: Path) -> Path:
    return Path(tool).resolve() / FILENAME


def empty() -> dict:
    return {'schema': SCHEMA, 'updated_at': '', 'relations': []}


def read(tool: Path) -> dict:
    path = path_for(tool)
    if not path.is_file():
        return empty()
    if path.is_symlink():
        raise ValueError('Le registre local ne peut pas être un lien symbolique')
    if path.stat().st_size > 6_000_000:
        raise ValueError('Registre local trop volumineux')
    with path.open('r', encoding='utf-8-sig') as stream:
        data = json.load(stream)
    if not isinstance(data, dict) or data.get('schema') != SCHEMA or not isinstance(data.get('relations'), list):
        raise ValueError('Format du registre inter-repos invalide')
    seen = set()
    for row in data['relations']:
        if not isinstance(row, dict):
            raise ValueError('Entrée du registre invalide')
        identity = str(row.get('boundary_key') or '')
        if not identity or identity in seen or len(identity) != 20:
            raise ValueError('Identifiant de frontière invalide ou dupliqué')
        seen.add(identity)
        if row.get('review_status') not in STATES or row.get('required') not in (True, False, None):
            raise ValueError('Décision de frontière invalide')
        if row.get('review_status') != 'APPROVED' and row.get('required') is not None:
            raise ValueError('Seule une frontière APPROVED peut définir required')
    return data


def _save(tool: Path, data: dict) -> Path:
    path = path_for(tool)
    if path.exists() and path.is_symlink():
        raise ValueError('Registre local symbolique interdit')
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    data['updated_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    try:
        with temp.open('w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()
    return path


def synchronize(tool: Path, relations: list[dict], *, persist=True, initial=None) -> tuple[dict, int]:
    """Merge discovered boundaries, NEVER change a human review decision."""
    data = read(tool) if initial is None else initial
    known = {row['boundary_key']: row for row in data['relations']}
    observed = set()
    new = 0
    for rel in relations:
        if not isinstance(rel, dict):
            continue
        src, dst, contract = (str(rel.get(k) or '').strip() for k in ('source', 'target', 'contract'))
        if not src or not dst:
            continue
        identity = key_for(src, dst, contract)
        observed.add(identity)
        if identity not in known:
            known[identity] = {
                'boundary_key': identity, 'source_repo': src, 'target_repo': dst,
                'contract': contract, 'review_status': 'UNREVIEWED', 'required': None,
                'protocol': '', 'method': '', 'route': '', 'event_channel': '', 'audit_repo_identity': '',
                'comment': '', 'last_qualification': str(rel.get('qualification') or ''),
                'observed': True,
            }
            new += 1
        else:
            row = known[identity]
            row['last_qualification'] = str(rel.get('qualification') or '')
            row['observed'] = True
    for identity, row in known.items():
        if identity not in observed:
            row['observed'] = False  # Preserve previously reviewed relations.
    data['relations'] = sorted(known.values(), key=lambda r:(r['source_repo'].casefold(), r['target_repo'].casefold(),r['contract']))
    if persist and (new or path_for(tool).is_file()):
        _save(tool, data)
    return data, new


def decide(tool: Path, identity: str, *, status: str, required: bool | None,
           protocol: str = '', method: str = '', route: str = '', event_channel: str = '',
           audit_repo_identity: str = '', comment: str = '') -> dict:
    data = read(tool)
    if status not in STATES:
        raise ValueError('Statut de revue inconnu')
    if status == 'APPROVED':
        if type(required) is not bool:
            raise ValueError('Une frontière approuvée doit être obligatoire ou optionnelle')
    elif required is not None:
        raise ValueError('Seules les frontières approuvées portent une obligation')
    protocol = protocol.upper().strip();method = method.upper().strip()
    if protocol not in PROTOCOLS or method not in METHODS:
        raise ValueError('Protocole ou méthode inconnu')
    if method and protocol != 'HTTP':
        raise ValueError('Une méthode HTTP exige le protocole HTTP')
    if route and (len(route) > 240 or not route.startswith('/') or '?' in route or '#' in route):
        raise ValueError('La route doit être un chemin sans query ni fragment')
    if event_channel and (protocol!='EVENT' or len(event_channel)>180 or any(x in event_channel for x in ('\r','\n','\x00'))):
        raise ValueError('Le canal est réservé aux frontières EVENT (180 caractères maximum)')
    if any(len(str(s)) > limit for s, limit in ((audit_repo_identity,160),(comment,400))):
        raise ValueError('Champ trop long')
    selected = next((row for row in data['relations'] if row['boundary_key']==identity), None)
    if selected is None:
        raise ValueError('Frontière inconnue : synchroniser un scan avant de qualifier')
    selected.update(review_status=status, required=required, protocol=protocol,method=method,route=route,
                    event_channel=event_channel.strip(),audit_repo_identity=audit_repo_identity.strip(), comment=comment.strip())
    selected['reviewed_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    _save(tool, data)
    return selected


def metrics(data: dict, current_keys: set[str] | None = None) -> dict:
    rows = data['relations']
    observed = [r for r in rows if (r['boundary_key'] in current_keys if current_keys is not None else r.get('observed', False))]
    statuses = {k: sum(r['review_status'] == k for r in observed) for k in STATES}
    official = [r for r in observed if r['review_status'] == 'APPROVED']
    missing_mapping = sum(not r.get('audit_repo_identity') for r in official)
    return {'registered':len(rows), 'observed':len(observed),'new_or_unreviewed':statuses['UNREVIEWED'],
            'approved':statuses['APPROVED'],'required':sum(r['required'] is True for r in official),
            'optional':sum(r['required'] is False for r in official),
            'rejected':statuses['REJECTED'],'deferred':statuses['DEFERRED'],
            'not_seen':len(rows)-len(observed), 'approved_without_audit_mapping':missing_mapping,
            'review_complete':bool(observed and not statuses['UNREVIEWED'] and not statuses['DEFERRED']),
            'global_e2e_certified':False}


def _csv_cell(value) -> str:
    value = '' if value is None else str(value)[:500]
    return "'" + value if value and value[0] in ('=', '+', '-', '@', '\t', '\r', '\n') else value


def export_csv(data: dict, output: Path) -> int:
    fields = ['boundary_key','source_repo','target_repo','contract','review_status','required','protocol',
              'method','route','event_channel','audit_repo_identity','last_qualification','observed','comment']
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,delimiter=';');writer.writeheader()
        for row in data['relations']:
            writer.writerow({k: _csv_cell(row.get(k)) for k in fields})
    return len(data['relations'])
