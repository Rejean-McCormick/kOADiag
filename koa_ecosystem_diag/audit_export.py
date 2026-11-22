# -*- coding: utf-8 -*-
"""Privacy-minimized LevelUpDiag campaign export for kOA GitHub Audit v0.22.

Only a small allowlist of aggregate campaign data and level verdict metadata is
serialized.  No source files, paths, findings, URLS, secrets or traces are copied.
The exported ZIP is *not* an E2E certification or a signed attestation.
"""
from __future__ import annotations

import hashlib
import io
from datetime import datetime, timezone
import json
import re
from pathlib import Path
import zipfile

from .framework import read_json

SUMMARY_SCHEMA = 'levelupdiag.campaign-summary.v2'
LEVEL_SCHEMA = 'levelupdiag.report.v2'
SUITE = 'Diagnostic du kOA Digital Ecosystem'
ALLOWED_VERDICTS = {'PASS', 'WARN', 'FAIL', 'SKIP', 'BLOCKED', 'PARTIAL',
                    'ERROR', 'INFRA_ERROR', 'CONFIG_ERROR'}
RUN_RE = re.compile(r'[A-Za-z0-9._-]{1,120}\Z')
LEVEL_RE = re.compile(r'N[0-9]{2,3}\Z')
MAX_RESULTS = 100
MAX_FILE_BYTES = 5_000_000


def _read_checked(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError('Résultat absent, lien symbolique ou taille excessive')
    data = read_json(path)
    if not isinstance(data, dict):
        raise ValueError('Résultat JSON non objet')
    return data


def _counter(value: object) -> int | None:
    if type(value) is int and 0 <= value <= 1_000_000:
        return value
    return None


def _numbers(value: object, fields: tuple[str, ...]) -> dict:
    value = value if isinstance(value, dict) else {}
    return {name: _counter(value.get(name)) for name in fields}


def _safe_coverage(raw: object) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    inv = raw.get('inventory', {})
    inv = inv if isinstance(inv, dict) else {}
    api = raw.get('api', {})
    traces = raw.get('traces', {})
    journeys = raw.get('journeys', {})
    end_to_end = raw.get('global_end_to_end', {})
    end_to_end = end_to_end if isinstance(end_to_end, dict) else {}
    # Conservative, closed vocabulary; never include arbitrary explanation text.
    status = end_to_end.get('status')
    if status not in ('NON_CERTIFIE', 'NON_DETERMINE'):
        status = 'NON_DETERMINE'
    return {
        'inventory': {**_numbers(inv, ('present', 'declared', 'truncated')),
                      'complete': inv.get('complete') if type(inv.get('complete')) is bool else None},
        'relations': _counter(raw.get('relations')),
        'api': _numbers(api, ('static_calls', 'routes_matched', 'routes_inbound', 'declared',
                              'declared_matched', 'live_checks_ok')),
        'traces': _numbers(traces, ('correlated_pairs', 'ik_receipts')),
        'journeys': _numbers(journeys, ('declared', 'evidence_complete', 'not_proven')),
        'global_end_to_end': {'status': status},
    }


def _safe_iso(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 60:
        return None
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            return None
        return stamp.astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    except ValueError:
        return None


def _safe_token(value: object, maxlen: int = 80) -> str:
    if isinstance(value, str) and len(value) <= maxlen and re.fullmatch(r'[a-zA-Z0-9._-]+', value):
        return value
    return 'unknown'


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8')


def _member(name: str, content: bytes, archive: zipfile.ZipFile) -> None:
    # Stable timestamps and permissions make re-export idempotent.
    info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    archive.writestr(info, content, compresslevel=7)


def build_bundle(run_directory: Path) -> bytes:
    """Validate a campaign then return a deterministic, metadata-only ZIP.

    Accepted by koa_audit.ecosystem_diag.normalize (v0.22).
    """
    run_directory = Path(run_directory)
    if not run_directory.is_dir() or run_directory.is_symlink():
        raise ValueError('Dossier de campagne invalide')
    summary = _read_checked(run_directory / 'summary.json')
    if summary.get('schema') != SUMMARY_SCHEMA or summary.get('suite') != SUITE:
        raise ValueError('Résumé LevelUpDiag kOA incompatible')
    run_id = summary.get('run_id')
    if not isinstance(run_id, str) or not RUN_RE.fullmatch(run_id):
        raise ValueError('run_id invalide')
    verdict = summary.get('verdict')
    if verdict not in ALLOWED_VERDICTS:
        raise ValueError('Verdict global invalide')
    levels = summary.get('levels')
    if not isinstance(levels, list) or not 1 <= len(levels) <= MAX_RESULTS:
        raise ValueError('Liste de niveaux invalide')

    metadata_levels, level_payloads, ids = [], [], set()
    for row in levels:
        if not isinstance(row, dict):
            raise ValueError('Niveau invalide')
        lid = row.get('id')
        if not isinstance(lid, str) or not LEVEL_RE.fullmatch(lid) or lid in ids:
            raise ValueError('Identifiant de niveau absent, invalide ou dupliqué')
        ids.add(lid)
        lverdict = row.get('verdict')
        if lverdict not in ALLOWED_VERDICTS:
            raise ValueError(f'Verdict invalide : {lid}')
        # Never follow paths embedded in the (possibly untrusted) report.
        raw_result = _read_checked(run_directory / 'levels' / lid / 'result.json')
        if any(raw_result.get(field) != expected for field, expected in (
            ('schema', LEVEL_SCHEMA), ('suite', SUITE), ('run_id', run_id),
            ('level_id', lid), ('verdict', lverdict)
        )):
            raise ValueError(f'Résultat de niveau incohérent : {lid}')
        metadata_levels.append({'id': lid, 'verdict': lverdict,
                                'result': f'levels/{lid}/result.json'})
        level_payloads.append((lid, {
            'schema': LEVEL_SCHEMA,
            'suite': SUITE,
            'suite_version': _safe_token(summary.get('suite_version'), 32),
            'run_id': run_id,
            'level_id': lid,
            'verdict': lverdict,
        }))

    counts = {s: sum(r['verdict'] == s for r in metadata_levels)
              for s in sorted(ALLOWED_VERDICTS)}
    # Fail rather than silently publishing inconsistent aggregate counts.
    reported_counts = summary.get('counts')
    if isinstance(reported_counts, dict):
        for name, value in reported_counts.items():
            if name in counts and value != counts[name]:
                raise ValueError(f'Compteurs incohérents ({name})')
    sanitized_summary = {
        'schema': SUMMARY_SCHEMA,
        'suite': SUITE,
        'suite_version': _safe_token(summary.get('suite_version'), 32),
        'run_id': run_id,
        'selection': _safe_token(summary.get('selection'), 80),
        'started_at': _safe_iso(summary.get('started_at')),
        'ended_at': _safe_iso(summary.get('ended_at')),
        'verdict': verdict,
        'counts': counts,
        'coverage': _safe_coverage(summary.get('coverage')),
        'levels': metadata_levels,
    }
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, 'w') as archive:
        _member('latest/summary.json', _json_bytes(sanitized_summary), archive)
        for lid, item in level_payloads:
            _member(f'latest/levels/{lid}/result.json', _json_bytes(item), archive)
    return memory.getvalue()


def export_campaign(run_directory: Path, output: Path) -> tuple[Path, str]:
    """Write an archive without replacing different bytes at an existing path."""
    output = Path(output)
    contents = build_bundle(run_directory)
    digest = hashlib.sha256(contents).hexdigest()
    if 'docs' in {part.casefold() for part in output.resolve().parts}:
        raise ValueError('Écriture dans docs/ interdite (GitHub Pages)')
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.is_symlink():
        raise ValueError('Sortie symbolique refusée')
    if output.exists():
        if hashlib.sha256(output.read_bytes()).hexdigest() != digest:
            raise FileExistsError('Archive de campagne existante avec un contenu différent')
        return output, digest
    with output.open('xb') as destination:
        destination.write(contents)
    return output, digest


def publish_private_bundle(run_directory: Path, control: Path) -> tuple[Path, Path]:
    """Produce run-id archive and latest archive, private to the diagnostic."""
    run_directory, control = Path(run_directory), Path(control)
    summary = _read_checked(run_directory / 'summary.json')
    run_id = summary.get('run_id')
    if not isinstance(run_id, str) or not RUN_RE.fullmatch(run_id):
        raise ValueError('run_id invalide')
    folder = control / 'bridge-audit'
    folder.mkdir(parents=True, exist_ok=True)
    # This folder must never be published through a GitHub Pages docs/ directory.
    if 'docs' in {p.casefold() for p in folder.resolve().parts}:
        raise ValueError('Dossier de publication docs/ interdit')
    (folder / '.gitignore').write_text('*\n!.gitignore\n', encoding='utf-8')
    archived, _ = export_campaign(run_directory, folder / f'{run_id}.zip')
    current = folder / 'latest-audit.zip'
    if current.is_symlink():
        raise ValueError('Lien symbolique latest-audit.zip refusé')
    tmp = folder / ('latest-audit.zip.tmp-' + run_id)
    if tmp.exists():
        raise FileExistsError('Archive temporaire déjà présente')
    try:
        tmp.write_bytes(archived.read_bytes())
        tmp.replace(current)
    finally:
        tmp.unlink(missing_ok=True)
    return archived, current
