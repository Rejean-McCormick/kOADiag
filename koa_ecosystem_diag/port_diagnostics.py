# -*- coding: utf-8 -*-
"""Read-only C0 local TCP/HTTP port diagnostics.

The C0 registry is authoritative. This module deliberately does not allocate,
start, stop or reconfigure services and never follows HTTP redirects.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import csv
import hashlib
import http.client
import json
from pathlib import Path
import re
import socket
import uuid

REGISTRY_REL = Path('kOA_Digital_Ecosystem/kOA_Digital_Ecosystem/config/local-dev-ports.v1.json')
REGISTRY_ID = 'koa-c0-local-development-ports'
MAX_SERVICE_COUNT = 100

# Only a product-family clue, not proof of the exact running instance. The
# diagnostic never claims identity based on an HTTP 200 or a reachable socket.
FAMILY_WORDS = {
    'orgo': ('orgo',),
    'initkoa': ('knowledge in common', 'initkoa', 'kòa', 'kōa'),
    'konnaxion': ('konnaxion',),
    'skope': ('skope',),
    'ekole': ('ekole', 'ékole', 'école québec', 'pastorale'),
    'koali': ('koali',),
}

# Non-HTTP services should not receive an HTTP request. These are declared C0
# TCP allocations, not evidence that PGlite is available as a network server.
NON_HTTP_IDS = {'orgo-koali-pglite'}

# Host-level endpoint presence is not a proof of network reachability from
# inside Docker, authentication, or an Interaction Kernel business transaction.
RELATED_ENDPOINTS = (
    ('Interaction Kernel : Orgo -> Konnaxion', 'orgo-api', 'konnaxion-api'),
    ('Interaction Kernel : Konnaxion -> Orgo', 'konnaxion-api', 'orgo-api'),
    ('Koali : Konnaxion Web -> API', 'konnaxion-koali-web', 'konnaxion-koali-api'),
    ('Koali : Orgo Web -> API', 'orgo-koali-web', 'orgo-koali-api'),
    ('Orgo Worlds : Web -> API', 'orgo-worlds-web', 'orgo-worlds-api'),
    ('Audit kOA -> HomePage', 'initkoa-web', 'initkoa-web'),
)


def registry_file(root: Path, explicit: Path | str | None = None) -> Path:
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    return (Path(root).expanduser() / REGISTRY_REL).resolve()


def read_registry(root: Path, explicit: Path | str | None = None) -> tuple[Path, dict]:
    path = registry_file(root, explicit)
    if not path.is_file():
        raise FileNotFoundError(f'Registre C0 absent : {path} (aucun port de remplacement inventé)')
    doc = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(doc, dict) or doc.get('registry_id') != REGISTRY_ID or doc.get('schema_version') != 1:
        raise ValueError('Le fichier indiqué n’est pas le registre C0 v1 attendu')
    if doc.get('host') != '127.0.0.1' or doc.get('transport') != 'tcp':
        raise ValueError('Ce diagnostic accepte uniquement le registre C0 TCP sur 127.0.0.1')
    pool = doc.get('pool')
    if not isinstance(pool, dict) or (pool.get('start'), pool.get('end')) != (21100, 21199):
        raise ValueError('Plage C0 inattendue : attendu 21100–21199')
    services = doc.get('services')
    if not isinstance(services, list) or not 1 <= len(services) <= MAX_SERVICE_COUNT:
        raise ValueError('Liste de services C0 absente ou anormalement longue')
    ids, ports = set(), set()
    blocks = doc.get('blocks', [])
    if not isinstance(blocks, list):
        raise ValueError('Blocs C0 invalides')
    for service in services:
        if not isinstance(service, dict):
            raise ValueError('Une entrée de service C0 est invalide')
        sid, port, owner = service.get('id'), service.get('port'), service.get('owner')
        if not isinstance(sid, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{1,90}', sid):
            raise ValueError(f'ID de service invalide : {sid!r}')
        if not isinstance(owner, str) or not owner:
            raise ValueError(f'Propriétaire C0 invalide pour {sid}')
        if isinstance(port, bool) or not isinstance(port, int) or not 21100 <= port <= 21199:
            raise ValueError(f'Port C0 invalide pour {sid} : {port!r}')
        if sid in ids or port in ports:
            raise ValueError(f'Attribution C0 dupliquée pour {sid} ou {port}')
        ids.add(sid); ports.add(port)
        if not any(isinstance(b, dict) and b.get('owner') == owner
                   and isinstance(b.get('start'), int) and isinstance(b.get('end'), int)
                   and b['start'] <= port <= b['end'] for b in blocks):
            raise ValueError(f'Port {port} ({sid}) hors du bloc de {owner}')
    return path, doc


def _tcp_open(port: int, timeout: float) -> tuple[bool, str]:
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=timeout):
            return True, ''
    except (OSError, TimeoutError) as exc:
        return False, type(exc).__name__


def _http_probe(port: int, timeout: float) -> dict:
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=timeout)
    try:
        connection.request('GET', '/', headers={
            'Host': f'localhost:{port}',
            'User-Agent': 'kOADiag-C0/1.0 (local-read-only-check)',
            'Accept': 'text/html,application/json,*/*',
            'Connection': 'close',
        })
        response = connection.getresponse()
        data = response.read(16384)
        title = ''
        content_type = response.getheader('Content-Type', '')[:128]
        if 'html' in content_type.lower() or data[:200].lower().find(b'<html') != -1:
            match = re.search(rb'<title\b[^>]*>(.*?)</title\s*>', data, re.I | re.S)
            if match:
                title = re.sub(r'\s+', ' ', match.group(1).decode('utf-8', 'replace')).strip()[:160]
        # Retain only safe metadata, never response bodies, cookies or auth headers.
        identity = (response.getheader('X-KOA-Service-Id') or '').strip()[:120]
        return {'http_code': response.status, 'content_type': content_type,
                'title': title, 'declared_service_id': identity}
    except (OSError, http.client.HTTPException, TimeoutError) as exc:
        return {'http_code': None, 'http_error': type(exc).__name__}
    finally:
        connection.close()


def _family_from_title(title: str) -> str | None:
    lower = title.casefold()
    hits = [family for family, words in FAMILY_WORDS.items() if any(x in lower for x in words)]
    # A mixed brand page (e.g., kOA architecture mentioning Orgo) cannot
    # establish ownership of the listening process.
    return hits[0] if len(hits) == 1 else None


def probe_service(service: dict, *, timeout: float = 1.0) -> dict:
    sid = service['id']
    port = service['port']
    row = {'id': sid, 'owner': service['owner'], 'purpose': service.get('purpose', ''),
           'port': port, 'adoption': service.get('adoption', 'non_renseigne'),
           'tcp': False, 'http_code': None, 'http_title': '',
           'status': 'STOPPED', 'detail': 'Aucun service TCP local sur le port attribué'}
    connected, reason = _tcp_open(port, timeout)
    if not connected:
        row['tcp_error'] = reason
        return row
    row['tcp'] = True
    if sid in NON_HTTP_IDS:
        row.update(status='TCP_OPEN_UNVERIFIED', detail='TCP ouvert ; protocole/identité non validés')
        return row
    found = _http_probe(port, timeout)
    row['http_code'] = found.get('http_code')
    row['http_title'] = found.get('title', '')
    if found.get('http_code') is None:
        row.update(status='TCP_OPEN_UNVERIFIED',
                   detail='TCP ouvert, mais aucune réponse HTTP claire ('+found.get('http_error', 'inconnu')+')')
        return row
    declared = found.get('declared_service_id', '')
    row['content_type'] = found.get('content_type', '')
    if declared:
        if declared == sid:
            row.update(status='IDENTITY_CONFIRMED', detail='Identifiant X-KOA-Service-Id exact')
        else:
            row.update(status='WRONG_SERVICE', detail='Autre service déclaré : '+declared)
        return row
    family = _family_from_title(row['http_title'])
    expected = 'initkoa' if service['owner'] == 'initkoa' else service['owner']
    if family and family != expected:
        row.update(status='WRONG_SERVICE', detail=f'Titre HTTP identifié comme {family}, attendu {expected}')
    elif family == expected:
        row.update(status='FAMILY_MATCH', detail='Famille reconnue dans le titre, instance exacte non prouvée')
    else:
        row.update(status='HTTP_UNVERIFIED', detail='Serveur HTTP présent, identité non vérifiée')
    return row


def check_all(root: Path, *, registry: Path | str | None = None,
              timeout: float = 1.0, workers: int = 8) -> dict:
    if not 0.1 <= timeout <= 10:
        raise ValueError('Timeout autorisé : 0.1 à 10 secondes')
    path, doc = read_registry(root, registry)
    rows = []
    with ThreadPoolExecutor(max_workers=max(1, min(int(workers), 12))) as pool:
        futures = {pool.submit(probe_service, service, timeout=timeout): service
                   for service in doc['services']}
        for future in as_completed(futures):
            service = futures[future]
            try:
                rows.append(future.result())
            except Exception as exc:
                rows.append({'id': service['id'], 'owner': service['owner'],
                             'port': service['port'], 'tcp': False, 'http_code': None,
                             'http_title': '', 'status': 'SCAN_ERROR',
                             'detail': f'Erreur de sonde ({type(exc).__name__})'})
    rows.sort(key=lambda x: x['port'])
    stats = Counter(item['status'] for item in rows)
    by_id = {x['id']: x for x in rows}
    links = []
    for name, source, target in RELATED_ENDPOINTS:
        if source not in by_id or target not in by_id:
            continue
        a, b = by_id[source], by_id[target]
        both = bool(a['tcp'] and b['tcp'])
        links.append({'name': name, 'source': source, 'target': target,
                      'source_tcp': a['tcp'], 'target_tcp': b['tcp'],
                      'status': 'DEUX_ENDPOINTS_OUVERTS_NON_E2E' if both else 'ENDPOINTS_INDISPONIBLES',
                      'e2e_proven': False})
    return {'schema': 'koa.c0.local-port-check.v1',
            'checked_at_utc': datetime.now(timezone.utc).isoformat(),
            'registry_path': str(path),
            'registry_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'registry_status': doc.get('decision_status'),
            'expected': len(rows), 'summary': dict(stats), 'services': rows,
            'endpoint_pairs': links,
            'limitations': [
                'Un port ouvert ne prouve pas le bon processus.',
                'Le titre HTTP prouve au mieux la famille du produit, pas l’instance exacte.',
                'Les paires de services sont sondées depuis le PC, jamais depuis les conteneurs Docker.',
                'Aucune authentification, transaction métier ni Interaction Kernel E2E n’est exécutée.',
                'Les services non démarrés sont signalés STOPPED, pas comme une collision.',
            ]}


def write_reports(result: dict, directory: Path) -> Path:
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    folder = target / (stamp + '-' + uuid.uuid4().hex[:6])
    folder.mkdir(parents=True, exist_ok=False)
    (folder/'ports-c0.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    columns = ['port', 'id', 'owner', 'purpose', 'tcp', 'http_code', 'http_title', 'status', 'detail', 'adoption']
    with (folder/'ports-c0.csv').open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=columns, extrasaction='ignore', delimiter=';')
        writer.writeheader(); writer.writerows(result['services'])
    lines = [f"DIAGNOSTIC C0 — {result['checked_at_utc']}",
             f"Registre : {result['registry_path']}",
             f"Attributions : {result['expected']}",
             'Les ports arrêtés peuvent correspondre à des services volontairement inactifs.',
             'Un port ouvert n’atteste pas une communication IK E2E.', '']
    for row in result['services']:
        lines.append(f"{row['port']:>5} | {row['id']:<34} | {row['status']:<21} | {row['detail']}")
    lines += ['', 'Paires locales (présence seulement, jamais preuve IK E2E) :']
    for link in result['endpoint_pairs']:
        lines.append(f"{link['name']} : {link['status']}")
    (folder/'ports-c0.txt').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return folder
