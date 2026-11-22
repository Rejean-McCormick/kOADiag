"""Local campaign import and passive evidence discovery for GitHub Audit."""
from pathlib import Path
import re
import subprocess

from .framework import read_json
from .audit_export import export_campaign

AUDIT_NAMES = ('kOA-D-E-GitHub-Audit', 'kOA-Digital-Ecosystem-GitHub-Audit')
DIGEST = re.compile(r'[0-9a-f]{64}\Z')


def find_audit(root, requested=None):
    if requested:
        candidates = [Path(requested)]
    else:
        candidates = [parent / name for parent in
                      (root, root / AUDIT_NAMES[1], root / 'kOA_Digital_Ecosystem')
                      for name in AUDIT_NAMES]
    matches = {candidate.resolve() for candidate in candidates
               if (candidate / 'koa_audit' / 'ecosystem_diag.py').is_file()}
    if len(matches) == 1:
        return matches.pop()
    if len(matches) > 1:
        raise ValueError('Plusieurs dépôts Audit trouvés. Indiquer le dossier Audit.')
    raise ValueError('Dépôt GitHub Audit introuvable. Indiquer le dossier Audit.')


def archive_descriptors(root, audit):
    private = (audit / 'private_evidence').resolve()
    if not private.is_relative_to(audit) or not private.is_relative_to(root):
        raise ValueError('private_evidence doit se trouver dans le dépôt Audit sous la racine kOA.')
    if not private.is_dir():
        return [], []
    descriptors, errors = [], []
    for directory in sorted(private.iterdir()):
        if directory.is_symlink() or not directory.is_dir():
            continue
        if directory.name.startswith('konnaxion-orgo-'):
            manifest = directory / 'config-observations.json'
        elif directory.name.startswith('koa-observations-'):
            manifest = directory / 'descripteurs-import.json'
        else:
            continue
        if not manifest.exists():
            continue
        try:
            if manifest.is_symlink() or manifest.stat().st_size > 512_000:
                raise ValueError('manifeste hors limite')
            data = read_json(manifest)
            rows = data if isinstance(data, list) else data['interrepo']['exchange_trace_files']
            if not isinstance(rows, list):
                raise ValueError('liste de descripteurs attendue')
            archived = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                relative = row.get('path')
                if not isinstance(relative, str):
                    continue
                path = root / relative
                if path.parent.resolve() != directory:
                    continue
                if path.is_symlink() or not path.is_file():
                    raise ValueError('export référencé absent ou symbolique')
                if not isinstance(row.get('sha256'), str) or not DIGEST.fullmatch(row['sha256']):
                    raise ValueError('empreinte d’export absente ou invalide')
                if not row.get('owner_repo'):
                    raise ValueError('propriétaire d’export absent')
                archived.append(row)
            descriptors.extend(archived)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f'{directory.name}/{manifest.name} · {type(exc).__name__}')
    return descriptors, errors


def merge_descriptors(existing, additions):
    if not isinstance(existing, list):
        raise ValueError('interrepo.exchange_trace_files doit être une liste.')
    rows = list(existing)
    paths = {str(row.get('path') if isinstance(row, dict) else row).replace('\\', '/').casefold()
             for row in existing}
    for row in additions:
        key = row['path'].replace('\\', '/').casefold()
        if key not in paths:
            rows.append(row)
            paths.add(key)
    return rows


def import_run(run_root, audit, python):
    bundle, _ = export_campaign(run_root, run_root / 'audit-import.zip')
    result = subprocess.run(
        [python, '-m', 'koa_audit', 'ecosystem-diag-import', '--input', str(bundle)],
        cwd=audit, capture_output=True, stdin=subprocess.DEVNULL,
        encoding='utf-8', errors='replace', timeout=120,
    )
    if result.returncode:
        return {'status': 'ERROR', 'exit_code': result.returncode,
                'detail': (result.stderr or result.stdout)[-1600:]}
    return {'status': 'IMPORTED', 'detail': result.stdout.strip()[:1600]}
