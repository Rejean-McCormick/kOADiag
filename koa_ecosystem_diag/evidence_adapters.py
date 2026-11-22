# -*- coding: utf-8 -*-
"""Read passive inter-repository evidence exports; NEVER execute providers.

Input files are relative to target_root. Each source may be a relative string
(legacy, untrusted provenance) or {path,owner_repo,field_map}. Only allowlisted
metadata is retained, never payloads, tokens, URLs or raw correlation ids.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re
from .native_evidence import observation

SCHEMA = 'koa.interrepo.evidence-import/v1'
PHASES = {'sent','received','response','published','consumed'}
ALIASES = {
    'correlation_id': ('correlation_id','trace_id','interaction_id','request_id'),
    'attempt_id': ('attempt_id','message_id','exchange_id'),
    'source_revision': ('source_revision',),
    'target_revision': ('target_revision',),
    'channel': ('channel','topic'),
    'journey_id': ('journey_id','scenario_id'),
    'source_repo': ('source_repo','source','producer_repo'),
    'target_repo': ('target_repo','target','consumer_repo'),
    'phase': ('phase','direction','event_phase'),
    'method': ('method','http_method'),
    'path': ('path','route','http_path'),
    'status': ('status','http_status','status_code','result'),
    'contract': ('contract','contract_id','ik_profile','profile'),
    'timestamp': ('timestamp','occurred_at','observed_at','time','ts'),
}
MAX_SIZE=12_000_000
MAX_RECORDS=20_000


def _value(record, key, fields):
    wanted = fields.get(key)
    candidates = [wanted] if isinstance(wanted,str) and wanted else ALIASES[key]
    for path in candidates:
        node=record
        for part in path.split('.'):
            if not isinstance(node,dict) or part not in node:
                node=None;break
            node=node[part]
        if node is not None and node!='':return node
    return ''


def _time(value):
    try:
        if isinstance(value, (int,float)) and not isinstance(value,bool):
            dt=datetime.fromtimestamp(float(value),tz=timezone.utc)
        elif isinstance(value,str) and len(value)<=60:
            dt=datetime.fromisoformat(value.strip().replace('Z','+00:00'))
            if dt.tzinfo is None:return None
        else:return None
        return dt.astimezone(timezone.utc).isoformat(timespec='milliseconds')
    except (OverflowError,ValueError,OSError,TypeError):return None


def _safe_path(root, relative):
    if not isinstance(relative,str) or not relative.strip() or len(relative)>500:
        raise ValueError('Chemin export vide ou excessif')
    p=Path(relative)
    if p.is_absolute() or '..' in p.parts:
        raise ValueError('Export hors racine interdit')
    root=Path(root).resolve()
    candidate=(root/p).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError('Export hors racine interdit')
    current=root
    for component in p.parts:
        current=current/component
        if current.is_symlink():raise ValueError('Export via lien symbolique interdit')
    if candidate.suffix.lower() not in ('.json','.jsonl','.ndjson'):
        raise ValueError('Export JSON/JSONL uniquement')
    if not candidate.is_file() or candidate.stat().st_size>MAX_SIZE:
        raise ValueError('Export absent ou trop volumineux (12 Mo max)')
    return candidate


def _records(path, raw):
    content = raw.decode('utf-8-sig')
    if path.suffix.lower() in ('.jsonl', '.ndjson'):
        lines = [line for line in content.splitlines() if line.strip()]
        if len(lines) > MAX_RECORDS:
            raise ValueError('Export tronqué: limite de lignes dépassée')
        return (json.loads(line) for line in lines)
    data = json.loads(content)
    if isinstance(data, dict):
        data = next((data[k] for k in ('records', 'events', 'entries')
                     if isinstance(data.get(k), list)), None)
    if not isinstance(data, list) or len(data) > MAX_RECORDS:
        raise ValueError('Tableau/records/events/entries invalide ou trop volumineux')
    return iter(data)


def _scalar(value, limit):
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        return ''
    value = str(value).strip()
    return value if len(value) <= limit else ''


def load(root, sources, *, stop=None, linux_root=None):
    """Parse and hash the same bytes, publishing records only from complete files."""
    results, findings = [], []
    if not isinstance(sources, list):
        return [], [{'status': 'ECART', 'detail': 'Liste exports invalide'}]
    if len(sources) > 500:
        findings.append({'status': 'ECART', 'detail': 'Limite de 500 sources dépassée'})
    for spec in sources[:500]:
        if stop and stop():
            raise InterruptedError('Collecte annulée')
        if isinstance(spec, str):
            spec = {'path': spec}
        relative = spec.get('path') if isinstance(spec, dict) else None
        try:
            path = _safe_path(root, relative)
            owner = _scalar(spec.get('owner_repo', ''), 120)
            if spec.get('owner_repo') and (not owner or not re.fullmatch(r'[a-zA-Z0-9_.\- /]+', owner)):
                raise ValueError('Propriétaire d’export invalide')
            kind = spec.get('format', 'exchange')
            mode = spec.get('mode', 'non_renseigne')
            if mode not in ('autonome', 'integre', 'non_renseigne'):
                raise ValueError('Mode d’observation invalide')
            with path.open('rb') as stream:
                raw = stream.read(MAX_SIZE + 1)
            if len(raw) > MAX_SIZE:
                raise ValueError('Export trop volumineux')
            digest = hashlib.sha256(raw).hexdigest()
            pin = spec.get('sha256')
            if pin is not None and pin != digest:
                raise ValueError('Empreinte SHA-256 attendue différente')
            finding = {'status': 'LU', 'source': relative, 'owner': owner,
                       'sha256': digest, 'digest_pinned': pin is not None, 'format': kind, 'mode': mode}
            if kind != 'exchange':
                finding.update(observation(kind, raw, linux_root))
                findings.append(finding)
                continue
            fields = spec.get('field_map', {})
            if not isinstance(fields, dict) or any(
                    k not in ALIASES or not isinstance(v, str)
                    or not re.fullmatch(r'[a-zA-Z0-9_.]{1,80}', v) for k, v in fields.items()):
                raise ValueError('Mapping de champs invalide')
            accepted, skipped = [], 0
            for obj in _records(path, raw):
                if stop and stop():
                    raise InterruptedError('Collecte annulée')
                if not isinstance(obj, dict):
                    skipped += 1
                    continue
                value = {k: _value(obj, k, fields) for k in ALIASES}
                ident = _scalar(value['correlation_id'], 250)
                src = _scalar(value['source_repo'], 120)
                dst = _scalar(value['target_repo'], 120)
                phase = _scalar(value['phase'], 20).casefold()
                if not ident or not src or not dst or phase not in PHASES:
                    skipped += 1
                    continue
                journey = _scalar(value['journey_id'], 120)
                attempt = _scalar(value['attempt_id'], 250)
                route = _scalar(value['path'], 160)
                if route and (not route.startswith('/') or route.startswith('//') or '?' in route or '#' in route):
                    skipped += 1
                    continue
                accepted.append({
                    'hash': hashlib.sha256(ident.encode()).hexdigest()[:16],
                    'journey_hash': hashlib.sha256(journey.encode()).hexdigest()[:16] if journey else '',
                    'attempt_hash': hashlib.sha256(attempt.encode()).hexdigest()[:16] if attempt else '',
                    'source': src, 'target': dst, 'phase': phase,
                    'method': _scalar(value['method'], 12).upper(), 'path': route,
                    'status': _scalar(value['status'], 40), 'channel': _scalar(value['channel'], 160),
                    'contract': _scalar(value['contract'], 160), 'timestamp': _time(value['timestamp']),
                    'source_revision': _scalar(value['source_revision'], 128),
                    'target_revision': _scalar(value['target_revision'], 128),
                    'file': relative, 'owner': owner, 'file_sha256': digest,
                    'digest_pinned': pin is not None, 'mode': mode,
                })
            if len(results) + len(accepted) > 100000:
                raise ValueError('Budget global de 100000 preuves dépassé')
            results.extend(accepted)
            findings.append(dict(finding, records=len(accepted), ignored=skipped))
        except InterruptedError:
            raise
        except (OSError, ValueError, TypeError, UnicodeError, KeyError, ImportError):
            findings.append({'status': 'ECART', 'source': str(relative or '')[:160],
                             'detail': 'Export absent, illisible ou incompatible. Vérifier format, limites, empreinte et dépendances.'})
        except Exception as exc:
            if type(exc).__module__.split('.')[0] not in ('jsonschema', 'referencing'):
                raise
            findings.append({'status': 'ECART', 'source': str(relative or '')[:160],
                             'detail': 'Schéma officiel invalide ou référence non disponible localement.'})
    return results, findings
