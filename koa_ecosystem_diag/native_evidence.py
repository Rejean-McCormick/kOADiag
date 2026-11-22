"""Validate native contracts and import complementary observations offline."""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re

from .ik_diag_core import load_json, safe_under


def schema_validator(path, directory=None):
    from jsonschema import Draft202012Validator, FormatChecker
    from referencing import Registry, Resource

    schema = load_json(path)
    Draft202012Validator.check_schema(schema)
    registry = Registry()
    if directory is not None:
        for item in sorted(directory.glob('*.schema.json')):
            resource = Resource.from_contents(load_json(safe_under(directory, item.name)))
            registry = registry.with_resource(item.resolve().as_uri(), resource)
            if resource.id():
                registry = registry.with_resource(resource.id(), resource)
    if '$id' not in schema:
        schema = dict(schema, **{'$id': path.resolve().as_uri()})
    return Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())


def validate_profiles(contracts, profiles):
    """Use the indexed descriptors, official meta-schema and offline $refs."""
    results = {}
    try:
        schema = safe_under(contracts, 'schemas/profile.schema.json')
        validator = schema_validator(schema, schema.parent)
    except ImportError:
        return {key: 'VALIDATEUR_INDISPONIBLE' for key in profiles}
    except Exception:
        return {key: 'ECART' for key in profiles}
    for key, item in profiles.items():
        try:
            validator.validate(load_json(Path(item['descriptor'])))
            schema_validator(Path(item['payload']))
            results[key] = 'VALIDE'
        except Exception:
            results[key] = 'ECART'
    return results


def journal_records(raw):
    """Verify the native Audit Broker journal envelope and its exact record bytes."""
    lines = raw.splitlines(keepends=True)
    if len(lines) < 2 or len(lines) > 20002:
        raise ValueError('Taille du journal invalide')
    header, trailer = json.loads(lines[0]), json.loads(lines[-1])
    digest = sha256(b''.join(lines[1:-1])).hexdigest()
    if not all(isinstance(item, dict) and item.get('record_type') == kind
               and item.get('journal_version') == '1.0.0'
               and type(item.get('record_count')) is int
               and item['record_count'] == len(lines) - 2
               and item.get('records_sha256') == digest
               for item, kind in ((header, 'header'), (trailer, 'trailer'))):
        raise ValueError('Intégrité ou format du journal invalide')
    if not header.get('export_id') or header['export_id'] != trailer.get('export_id'):
        raise ValueError('Identité du journal incohérente')
    allowlist = header.get('field_allowlist')
    if not isinstance(allowlist, list) or not all(isinstance(x, str) for x in allowlist):
        raise ValueError('Champs déclarés du journal invalides')
    for index, line in enumerate(lines[1:-1], 1):
        entry = json.loads(line)
        if (not isinstance(entry, dict) or type(entry.get('sequence')) is not int
                or entry['sequence'] != index or not isinstance(entry.get('record'), dict)
                or not set(entry['record']) <= set(allowlist)):
            raise ValueError('Séquence ou format de journal invalide')
        yield entry['record']


def _date(value):
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('Fuseau absent')
    return stamp


def _correlation_observation(count, correlations):
    return {'records': count, 'correlated': len(correlations),
            'correlation_hashes': sorted(sha256(x.encode()).hexdigest()[:16] for x in correlations)}


def observation(kind, raw, linux_root):
    """Return bounded counters. Native observations cannot manufacture a hop."""
    if kind == 'koa-linux-journal':
        records, correlations = 0, set()
        for row in journal_records(raw):
            records += 1
            ident = row.get('correlation_id')
            if isinstance(ident, str) and ident and len(ident) <= 250:
                correlations.add(ident)
        return _correlation_observation(records, correlations)
    data = json.loads(raw)
    if kind == 'koa-linux-receipt':
        if linux_root is None:
            raise ValueError('Dépôt kOA Linux absent')
        schema = safe_under(linux_root, 'interfaces/receipts/receipt-envelope.schema.json')
        validator = schema_validator(schema, schema.parent)
        receipts = data if isinstance(data, list) else [data]
        if not receipts or len(receipts) > 20000:
            raise ValueError('Nombre de reçus invalide')
        correlations = set()
        for row in receipts:
            if not validator.is_valid(row):
                raise ValueError('Reçu incompatible avec le schéma kOA Linux')
            stamps = [_date(row[field]) for field in
                      ('requested_at', 'started_at', 'completed_at', 'committed_at')
                      if field in row]
            # Authoritative commit may precede completion. Both must follow start.
            if len(stamps) > 1 and any(stamp < stamps[0] for stamp in stamps[1:]):
                raise ValueError('Horodatage du reçu incohérent')
            correlations.add(row['correlation']['correlation_id'])
        return _correlation_observation(len(receipts), correlations)
    schemas = {
        'koali-summary': 'levelupdiag.campaign-summary.v2',
        'orgo-summary': 'levelupdiag.campaign-summary.v2',
        'konnaxion-summary': 'konnaxiondiag.campaign-summary.v4',
    }
    if kind not in schemas or not isinstance(data, dict) or data.get('schema') != schemas[kind]:
        raise ValueError('Format de rapport spécialisé incompatible')
    expected = data.get('expected_levels')
    levels = data.get('levels')
    if not isinstance(expected, list) or not expected or not isinstance(levels, list):
        raise ValueError('Périmètre du rapport spécialisé invalide')
    verdicts = {'PASS', 'WARN', 'PARTIAL', 'FAIL', 'SKIP', 'BLOCKED', 'ERROR', 'CONFIG_ERROR', 'INFRA_ERROR'}
    actual = {}
    for row in levels:
        level = row.get('id', row.get('level_id')) if isinstance(row, dict) else None
        if not isinstance(level, str) or not re.fullmatch(r'N[0-9]{2,3}', level) or level in actual:
            raise ValueError('Niveau du rapport spécialisé invalide')
        verdict = row.get('verdict')
        if verdict not in verdicts:
            raise ValueError('Verdict du niveau invalide')
        actual[level] = verdict
    if len(expected) != len(actual) or set(expected) != actual.keys() or data.get('verdict') not in verdicts:
        raise ValueError('Résumé spécialisé incomplet')
    if not isinstance(data.get('run_id'), str) or not data['run_id']:
        raise ValueError('Identité de campagne absente')
    if kind == 'koali-summary' and not isinstance(data.get('diagnostic_mode'), str):
        raise ValueError('Mode natif Koali absent')
    if _date(data['ended_at']) < _date(data['started_at']):
        raise ValueError('Horodatage du résumé incohérent')
    return {'records': len(actual), 'verdict': data['verdict'],
            'ended_at': data['ended_at'], 'levels': actual,
            'readiness_n12': actual.get('N12') if kind == 'koali-summary' else None}


def ik_trace_validator(contracts, profiles):
    """Use the installed official validator with a local-only schema registry."""
    from interaction_kernel import ContractValidator, ProfileRegistry

    registry = ProfileRegistry()
    for item in profiles.values():
        if item.get('native_validation') == 'VALIDE':
            registry.register_directory(Path(item['descriptor']).parent)

    class OfflineValidator(ContractValidator):
        def __init__(self):
            self.profile_registry = registry
            self.validators = {}

        def _validator(self, name):
            if name not in self.validators:
                path = safe_under(contracts, 'schemas/' + name)
                self.validators[name] = schema_validator(path, path.parent)
            return self.validators[name]

    return OfflineValidator()
