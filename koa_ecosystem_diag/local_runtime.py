"""Run the owner-maintained kit and ingest its explicitly exported metadata."""
from datetime import datetime
from pathlib import Path
import json
import shutil
import subprocess

from .framework import write_json
from .ik_diag_core import safe_under, sha256_file
from .port_diagnostics import read_registry

MARKER = 'KOA_OBSERVATIONS='
JOURNEY = 'konnaxion-orgo-decision-impact'


def archive_observations(root, audit, uid, record):
    correlation = record['correlation_id']
    if not isinstance(correlation, str) or not correlation.strip():
        raise ValueError('Corrélation native absente')
    groups = {'Konnaxion': [], 'Orgo': []}
    for prefix, source, target, contract, statuses in (
        ('decision', 'Konnaxion', 'Orgo', 'governance.decision.execute/1.0.0', ('accepted', 'succeeded')),
        ('impact', 'Orgo', 'Konnaxion', 'accountability.impact.publish/1.0.0', ('succeeded',)),
    ):
        attempt, status = record[f'{prefix}_id'], record[f'{prefix}_status']
        if not isinstance(attempt, str) or not attempt or status not in statuses:
            raise ValueError(f'Tentative ou reçu {prefix} invalide')
        common = {'journey_id': JOURNEY, 'source_repo': source, 'target_repo': target,
                  'correlation_id': correlation, 'attempt_id': attempt, 'contract': contract}
        for phase, owner in (('sent', source), ('received', target), ('response', target)):
            value = record[f'{prefix}_{phase}']
            if not isinstance(value, str) or not datetime.fromisoformat(value.replace('Z', '+00:00')).tzinfo:
                raise ValueError(f'Horodatage {prefix}/{phase} invalide')
            row = dict(common, phase=phase, timestamp=value)
            if phase == 'response':
                row['status'] = status
            groups[owner].append(row)
    directory = (audit / 'private_evidence' / f'konnaxion-orgo-{uid}').resolve()
    if not directory.is_relative_to(audit) or not directory.is_relative_to(root):
        raise ValueError('Destination privée hors racine kOA')
    directory.mkdir(parents=True, exist_ok=False)
    files = []
    for owner, rows in groups.items():
        path = directory / f'{owner.lower()}-observations.json'
        write_json(path, rows)
        files.append({'path': path.relative_to(root).as_posix(), 'owner_repo': owner,
                      'mode': 'autonome', 'sha256': sha256_file(path)})
    write_json(directory / 'config-observations.json', {'interrepo': {'exchange_trace_files': files}})
    return files


def run(root, *, world=None, audit=None, run_root=None, start_stack=False):
    try:
        orgo = safe_under(root, 'Orgo/Orgo')
        konnaxion = safe_under(root, 'Konnaxion/Konnaxion')
        script = safe_under(orgo, 'validation/konnaxion-orgo-ik/run-e2e.ps1')
    except ValueError:
        return 'BLOCKED', 'Chemin du kit officiel hors périmètre', {}
    pwsh = shutil.which('pwsh')
    if not pwsh or not script.is_file() or not konnaxion.is_dir():
        return 'BLOCKED', 'Le kit Orgo, Konnaxion ou PowerShell 7 est absent', {}
    try:
        _, registry = read_registry(root)
        allocations = {row['id']: row['port'] for row in registry['services']}
        orgo_port = allocations['orgo-api']
        konnaxion_port = allocations['konnaxion-api']
    except (OSError, ValueError, TypeError, KeyError):
        return 'BLOCKED', 'Registre C0 absent, invalide ou sans les API requises', {}
    if start_stack:
        from .test_stack import start
        logfile = run_root / 'levels' / 'N14' / 'test-stack.log'
        try:
            with logfile.open('w', encoding='utf-8') as log:
                start(orgo, konnaxion / 'backend', log, root=root)
        except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
            return 'BLOCKED', f'Pile d’essai indisponible : {exc}. Consulter test-stack.log.', {
                'local_log': 'levels/N14/test-stack.log'
            }
    command = [pwsh, '-NoProfile', '-NonInteractive', '-File', str(script),
               '-OrgoRoot', str(orgo), '-KonnaxionRoot', str(konnaxion),
               '-OrgoHostUrl', f'http://127.0.0.1:{orgo_port}', '-TimeoutSeconds', '120']
    if world:
        command.extend(('-WorldKey', world))
    capture = bool(audit and run_root and 'switch]$ExportObservations' in
                   script.read_text(encoding='utf-8-sig'))
    if capture:
        command.append('-ExportObservations')
    try:
        result = subprocess.run(command, cwd=root, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=240)
    except subprocess.TimeoutExpired:
        return 'FAIL', 'Le kit officiel a dépassé 240 secondes', {}
    except OSError:
        return 'INFRA_ERROR', 'Impossible de lancer le kit officiel', {}
    evidence = {'script_sha256': sha256_file(script), 'exit_code': result.returncode}
    lines = result.stdout.decode('utf-8', errors='replace').splitlines()
    if result.returncode or not any('KONNAXION <-> ORGO IK E2E PASS' in line for line in lines):
        if run_root:
            log = run_root / 'levels' / 'N14' / 'kit-local.log'
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text('\n'.join(line for line in lines if not line.startswith(MARKER)),
                           encoding='utf-8')
            evidence['local_log'] = 'levels/N14/kit-local.log'
        return 'FAIL', 'Le kit officiel n’a pas terminé. Consulter le journal local N14.', evidence
    if capture:
        try:
            payload, = [line[len(MARKER):] for line in lines if line.startswith(MARKER)]
            files = archive_observations(root, audit, run_root.name, json.loads(payload))
            write_json(run_root / 'levels' / 'N14' / 'evidence-descriptors.json', files)
            evidence['observations_archived'] = len(files)
        except (KeyError, TypeError, ValueError, OSError) as exc:
            return 'PARTIAL', f'Kit métier réussi, archivage incomplet ({type(exc).__name__}).', evidence
    elif audit:
        return 'PARTIAL', 'Kit métier réussi. Cette version du kit ne fournit pas les métadonnées exportables.', evidence
    return 'PASS', 'Assertions du kit officiel Konnaxion–Orgo réussies sur la pile locale', evidence
