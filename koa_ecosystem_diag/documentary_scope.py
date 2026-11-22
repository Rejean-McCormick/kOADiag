"""Reconcile current observations with the existing reviewed documentary baseline."""
import csv
import re

from .boundary_registry import key_for
from .framework import read_json
from .ik_diag_core import safe_under, sha256_file


def _historical_contracts(target, authority, documents, snapshot):
    reference = 'docs/2-Technical-Reference/40-integration/knowledge-projection-contract-set.json'
    if not any(row['path'] == reference and row['status'] == 'CONFORME' for row in documents):
        return {}
    index = {row['repo']: row for row in snapshot['repositories'] if row['exists']}
    data = read_json(safe_under(authority, reference))
    handoff = data['encyklopedia']['handoff']
    ik = data['interaction_kernel']['build_request']
    profile = snapshot.get('ik_profile_validation', {}).get(ik, {})
    result = {
        key_for('EncyKlopedia', 'Daat', ''): {
            'reference': reference, 'historical_contract': handoff, 'related_ik_profile': ik,
            'related_ik_sources': profile.get('sources', []),
            'status': 'REVUE_CONTRAT_HISTORIQUE',
            'reason': 'Vérifier le handoff EncyK v1 auprès des propriétaires. Le profil de build IK est limité à ses propres émetteurs.',
        },
    }
    handoff_check = result[key_for('EncyKlopedia', 'Daat', '')]
    for row in snapshot.get('schemas', []):
        schema_id = row.get('id') or ''
        if (row.get('repo') != 'EncyKlopedia' or row.get('status') != 'LISIBLE'
                or not (schema_id == handoff or schema_id.endswith('/' + handoff))):
            continue
        try:
            from .native_evidence import schema_validator
            owner = safe_under(target, index['EncyKlopedia']['relative_path'])
            path = safe_under(owner, row['file'])
            schema_validator(path)
            handoff_check.update(status='REFERENCE_HISTORIQUE_VALIDEE',
                                 schema_file=row['file'], schema_sha256=sha256_file(path),
                                 reason='Schéma versionné du producteur prévu par le plan historique.')
        except (OSError, ValueError, KeyError, ImportError):
            pass
        except Exception as exc:
            if type(exc).__module__.split('.')[0] not in ('jsonschema', 'referencing'):
                raise
        break

    kristal = data['kristal']
    state = 'schemas/kristal-state.schema.json'
    reader = 'schemas/reader-policy.schema.json'
    freeze = {
        'reference': reference, 'historical_contract': 'kristal_state/' + kristal['standard'],
        'status': 'REFERENCE_FIGEE_ABSENTE', 'reason': 'Verrou consommateur ou copie amont indisponible',
    }
    result[key_for('Daat', 'Kristal-Framework', '')] = freeze
    try:
        ik_root = safe_under(target, index['Interaction-Kernel']['relative_path'])
        daat = safe_under(target, index['Daat']['relative_path'])
        lock = read_json(safe_under(daat, 'contracts/owners/ik/kristal.lock.json'))
        version = kristal['standard']
        if not re.fullmatch(r'[0-9]+[.][0-9]+[.][0-9]+', version):
            raise ValueError('Version de baseline invalide')
        upstream = safe_under(ik_root, 'locks/kristal-v' + version + '-upstream')
        expected = {state: kristal['kristal_state_schema_sha256'], reader: kristal['reader_policy_schema_sha256']}
        actual = {name: 'sha256:' + sha256_file(safe_under(upstream, name)) for name in expected}
        freeze['upstream_sha256'] = actual
        compatible = (lock.get('format') == 'kristal.consumer-lock/v2'
                      and lock.get('version') == version
                      and lock.get('canonicalization_profile') == kristal['canonicalization_profile']
                      and lock.get('standard_manifest_sha256') == kristal['standard_manifest_sha256']
                      and all(lock.get('contract_digests', {}).get(name) == digest
                              for name, digest in expected.items())
                      and actual == expected)
        freeze['status'] = 'REFERENCE_FIGEE_VALIDEE' if compatible else 'ECART_REFERENCE_FIGEE'
        freeze['reason'] = 'Comparaison docs, verrou Da’at et schémas amont figés. Le checkout actif Kristal exige sa propre qualification.'
    except (OSError, KeyError, TypeError, ValueError):
        pass
    return result


def reconcile(tool, target, registry, snapshot):
    baseline = tool / 'qualification-docs'
    authority = target / 'kOA_Digital_Ecosystem' / 'kOA_Digital_Ecosystem'
    documents, obligations, errors = [], [], []
    try:
        pins = read_json(baseline / 'sources-documentaires.sha256.json')['documents']
        for relative, expected in sorted(pins.items()):
            path = safe_under(authority, relative)
            actual = sha256_file(path) if path.is_file() else None
            documents.append({
                'path': relative, 'expected_sha256': expected, 'actual_sha256': actual,
                'status': 'CONFORME' if actual == expected else ('MODIFIE' if actual else 'ABSENT'),
            })
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        errors.append('Index des sources documentaires illisible')
    decisions = {r['boundary_key']: r for r in registry['relations']}
    present = {r['repo'] for r in snapshot['repositories'] if r['exists']}
    try:
        with (baseline / 'plan-preuves-obligatoires.csv').open(encoding='utf-8-sig', newline='') as stream:
            for row in csv.DictReader(stream, delimiter=';'):
                source, target_repo, contract = row['emetteur'], row['recepteur'], row['contrat']
                key = row['boundary_key']
                if key != key_for(source, target_repo, contract):
                    raise ValueError('Identité de frontière incohérente')
                decision = decisions.get(key, {})
                reconciled = decision.get('review_status') == 'APPROVED' and decision.get('required') is True
                obligations.append({
                    'boundary_key': key, 'source': source, 'target': target_repo, 'contract': contract,
                    'documented_profile': row['profil'], 'review_status': decision.get('review_status', 'ABSENT'),
                    'decision_matches_plan': reconciled,
                    'missing_repos': sorted({source, target_repo} - present),
                    'observed': decision.get('observed', False),
                })
    except (OSError, ValueError, KeyError):
        errors.append('Plan documentaire des frontières obligatoires illisible')
    try:
        historical = _historical_contracts(target, authority, documents, snapshot)
    except (OSError, KeyError, TypeError, ValueError):
        historical = {}
        errors.append('Contrats techniques du profil historique illisibles')
    for row in obligations:
        if row['boundary_key'] in historical:
            row['technical_reconciliation'] = historical[row['boundary_key']]
    return {'schema': 'koa.documentary-scope/v1', 'documents': documents, 'obligations': obligations,
            'errors': errors, 'aligned': bool(documents and obligations and not errors
                and all(d['status'] == 'CONFORME' for d in documents)
                and all(r['decision_matches_plan'] for r in obligations))}
