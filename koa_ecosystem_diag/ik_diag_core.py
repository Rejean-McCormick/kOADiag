# -*- coding: utf-8 -*-
"""kOA / Interaction Kernel - cross-repository contract and API boundary diagnostics.

No app tests, subprocesses, mutations or writes in repository trees. API probes are
opt-in and limited to explicitly configured GET/HEAD requests.
"""
from __future__ import annotations
import csv
import hashlib
import ipaddress
import json
import os
from pathlib import Path, PureWindowsPath
import re
import socket
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPHandler, HTTPSHandler, ProxyHandler, Request, HTTPRedirectHandler

APP_VERSION = '2.0.0'
EXCLUDES = {'.git', '.hg', '.svn', '.venv', 'venv', 'node_modules', 'dist', 'build', '__pycache__',
            'coverage', '.next', '.pytest_cache', '.tox', 'vendor', 'generated', '.turbo', 'target'}
SOURCE_EXTENSIONS = {'.py', '.ts', '.tsx', '.js', '.mjs', '.cjs', '.json', '.yaml', '.yml', '.toml'}
DEFAULT_CONFIG = {
    'format': 'koa.interaction-diagnostic.config/1',
    'scan': {'max_files_per_repo': 1000, 'max_file_bytes': 250000},
    'api': {'enabled': False, 'allow_remote': False, 'timeout_seconds': 3,
            'max_response_bytes': 65536},
    'system_repo_overrides': {
        'kristal': 'Kristal-Framework', 'koa-linux': 'kOA-Linux-Koali',
        'uckk': None
    },
    'trace_files': [],
    'probes': [
        {'id': 'orgo-health-ready', 'label': 'Orgo - readiness (exemple, désactivé)',
         'enabled': False, 'source': 'Konnaxion', 'target': 'Orgo', 'kind': 'readiness',
         'method': 'GET', 'url': 'http://127.0.0.1:4000/health/ready',
         'expect_status': [200], 'expect_content_type': 'application/json',
         'expect_json': {'status': 'ready'},
         'note': 'Prouve seulement la réponse Orgo, PAS le handoff Konnaxion → Orgo.'}
    ]
}

class Stopped(Exception):
    pass


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for data in iter(lambda: f.read(1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def load_json(path):
    with open(path, encoding='utf-8-sig') as f:
        return json.load(f)


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')


def relative_repo_path(winroot):
    """Strip precisely C:\\mycode from inventory paths; reject arbitrary host paths."""
    if not isinstance(winroot, str):
        raise ValueError('local_root absent')
    path = PureWindowsPath(winroot)
    parts = path.parts
    if len(parts) < 3 or parts[0].lower() != 'c:\\' or parts[1].lower() != 'mycode':
        raise ValueError('Racine inventaire inattendue: ' + winroot)
    if any(x in ('', '.', '..') for x in parts[2:]):
        raise ValueError('Chemin inventaire dangereux: ' + winroot)
    return Path(*parts[2:])


def safe_under(root, relative):
    root = Path(root).resolve()
    p = root / relative
    resolved = p.resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise ValueError('Chemin sort de la racine: ' + str(relative))
    return resolved


def normalize_system_name(s):
    return str(s).casefold().replace('’', "'").replace(' ', '').replace('-', '')


def _source_text(path):
    try:
        return path.read_text(encoding='utf-8', errors='replace').lower()
    except OSError:
        return ''


def code_references(repo_dir, contracts, max_files=1000, max_bytes=250000, stop=None, *, deadline=None):
    """Only find static source references, never infer that a call executes."""
    result = {c: [] for c in contracts}
    if not repo_dir.is_dir() or not contracts:
        return result
    found = 0
    for current, directories, files in os.walk(repo_dir):
        if deadline is not None and time.monotonic() >= deadline:
            break
        directories[:] = sorted(d for d in directories if d not in EXCLUDES and not d.startswith('.'))
        for name in sorted(files):
            if stop and stop():
                raise Stopped()
            if found >= max_files or (deadline is not None and time.monotonic() >= deadline):
                return result
            p = Path(current) / name
            if p.suffix.lower() not in SOURCE_EXTENSIONS or p.is_symlink() or not p.is_file():
                continue
            try:
                if p.stat().st_size > max_bytes:
                    continue
            except OSError:
                continue
            found += 1
            body = _source_text(p)
            for contract in contracts:
                # Require the actual profile ID as a literal; a reference is NOT a contract test.
                if contract.lower() in body and len(result[contract]) < 3:
                    result[contract].append(str(p.relative_to(repo_dir)).replace('\\', '/'))
    return result


def read_reference_data(root, refdir):
    root = Path(root).resolve()
    local = root / 'kOA_Digital_Ecosystem' / 'kOA_Digital_Ecosystem' / 'docs' / 'inventory'
    sources = []
    obj = {}
    for fname in ('repositories.json', 'graph-registry.v1.json', 'graph-focus.v1.json'):
        loc = local / fname
        if not loc.is_file():
            loc = Path(refdir) / fname
            sources.append(f'{fname}: snapshot embarqué (à vérifier)')
        else:
            sources.append(f'{fname}: docs locaux')
        obj[fname] = load_json(loc)
    if not isinstance(obj['repositories.json'], list) or not isinstance(obj['graph-registry.v1.json'], dict):
        raise ValueError('Inventaire/registre de graphe malformé')
    return obj, sources


def inventory(repo_entries, root):
    out = {}
    for entry in repo_entries:
        if not isinstance(entry, dict) or not entry.get('github_repo'):
            continue
        slug = entry['github_repo'].split('/')[-1]
        rel = relative_repo_path(entry.get('local_root', ''))
        out[slug.casefold()] = {'name': slug, 'github_repo': entry['github_repo'],
                                'path': safe_under(root, rel), 'relative': str(rel)}
    return out


def systems_map(registry, config, repo_map):
    out = {}
    for sys in registry.get('systems', []):
        repo = str(sys.get('github_repo', '')).rsplit('/', 1)[-1].casefold()
        slug = repo_map.get(repo, {}).get('name')
        out[normalize_system_name(sys.get('id', ''))] = slug
    aliases = {'daat': 'Daat', 'konnaxion': 'Konnaxion', 'orgo': 'Orgo',
               'kristal': 'Kristal-Framework', 'koalinux': 'kOA-Linux-Koali', 'uckk': None}
    for key, value in aliases.items():
        out.setdefault(key, value)
    for key, value in config.get('system_repo_overrides', {}).items():
        out[normalize_system_name(key)] = value
    return out


def profile_tree(ik_dir):
    """Return registry, explicit active metadata and lock checks; no imports of app code."""
    checks, profiles = [], {}
    index_file = ik_dir / 'contracts/profiles/index.json'
    def add(status, name, detail, evidence=''):
        checks.append({'status': status, 'group': 'Contrat IK', 'name': name,
                       'detail': detail, 'evidence': evidence})
    if not index_file.is_file():
        add('ABSENT', 'Index IK', 'contrats/profiles/index.json manquant', str(index_file))
        return profiles, checks
    try:
        index = load_json(index_file)
        if index.get('format') != 'ik.profile-index/1' or not isinstance(index.get('profiles'), list):
            raise ValueError('format inconnu')
        indexed = index['profiles']
        entries = set()
        for item in indexed:
            name, version, kind = item['id'], item['version'], item['class']
            if not all(isinstance(v, str) and re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.+-]*', v) for v in (name, version)):
                raise ValueError('Identité de profil invalide')
            key = (name, version)
            if key in entries:
                add('ECART', f'{name}/{version}', 'Profil dupliqué dans index')
                continue
            entries.add(key)
            matches = list((ik_dir / 'contracts/profiles').glob(f'*/{name}/{version}/profile.json'))
            if len(matches) != 1:
                add('ECART', f'{name}/{version}', f'Descripteur actif introuvable ou ambigu: {len(matches)} fichier(s)')
                continue
            p = safe_under(ik_dir, matches[0].relative_to(ik_dir))
            desc = load_json(p)
            payload_path = (p.parent / str(desc.get('payload_schema', ''))).resolve()
            if (desc.get('id'), desc.get('version'), desc.get('class')) != (name, version, kind):
                add('ECART', f'{name}/{version}', 'ID/version/classe ne concordent pas avec index', str(p))
                continue
            if not payload_path.is_relative_to(p.parent.resolve()) or not payload_path.is_file():
                add('ECART', f'{name}/{version}', 'Schéma payload absent ou hors profil', str(payload_path))
                continue
            schema = load_json(payload_path)
            if not isinstance(schema, dict) or schema.get('type') not in (None, 'object'):
                add('ECART', f'{name}/{version}', 'Schéma payload inattendu', str(payload_path))
                continue
            if kind not in ('command','query','event'):
                add('ECART', f'{name}/{version}', 'Classe non prise en charge', str(p))
                continue
            profiles[key] = {'id': name, 'version': version, 'class': kind,
                             'sources': desc.get('source_systems', []),
                             'targets': desc.get('target_systems', []),
                             'delivery': desc.get('delivery', {}),
                             'response': desc.get('response', {}),
                             'descriptor': str(p), 'payload': str(payload_path)}
            add('OK', f'{name}/{version}', 'Index ↔ descripteur ↔ payload cohérents', str(p))
        add('OK', 'Index actif', f'{len(profiles)}/{len(indexed)} profils chargés') if len(profiles)==len(indexed) else add('ECART', 'Index actif', f'{len(profiles)}/{len(indexed)} profils chargés')
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
        add('ECART', 'Index IK', 'Lecture/validation impossible: ' + str(exc))
    lock_file = ik_dir / 'contracts/locks/konnaxion-orgo-adopted-v1.lock.json'
    if lock_file.is_file():
        try:
            lock = load_json(lock_file)
            entries = lock.get('files', [])
            if lock.get('format') != 'ik.adopted-profile-lock/1' or lock.get('specversion') != 'ik/1.1' or not isinstance(entries,list) or len(entries)!=6:
                raise ValueError('lock non conforme ou incomplet')
            expected_names={f'contracts/profiles/konnaxion-orgo/{name}/1.0.0/{filename}'
                            for name in ('governance.decision.execute', 'accountability.impact.publish',
                                         'operational.reconsideration.recommended')
                            for filename in ('profile.json', 'payload.schema.json')}
            if {str(x.get('path','')).replace('\\','/') for x in entries} != expected_names:
                raise ValueError('liste de 6 chemins adoptés différente de la baseline')
            names = set()
            for entry in entries:
                rel = Path(str(entry['path']).replace('\\','/'))
                if rel.is_absolute() or '..' in rel.parts or rel.as_posix() in names:
                    raise ValueError('chemin lock non sûr/dupliqué')
                names.add(rel.as_posix())
                path = safe_under(ik_dir, rel)
                expected = entry.get('sha256', '')
                if not path.is_file() or expected != 'sha256:' + sha256_file(path):
                    add('ECART', 'Verrou adopté: '+rel.name, 'SHA-256 absent ou différent', rel.as_posix())
                else:
                    add('OK', 'Verrou adopté: '+rel.name, 'SHA-256 conforme', rel.as_posix())
        except (ValueError, TypeError, OSError, KeyError) as exc:
            add('ECART', 'Verrou adopté', str(exc))
    else:
        add('ABSENT', 'Verrou adopté', 'Konnaxion/Orgo lock introuvable')
    from .native_evidence import validate_profiles
    validation = validate_profiles(ik_dir / 'contracts', profiles) if profiles else {}
    adopted_lock_ok = sum(row['status'] == 'OK' and row['name'].startswith('Verrou adopté:') for row in checks) == 6
    for key, status in validation.items():
        if profiles[key]['sources'] and 'konnaxion-orgo' in Path(profiles[key]['descriptor']).parts and not adopted_lock_ok:
            status = 'ECART'
        profiles[key]['native_validation'] = status
        name = '/'.join(key)
        add('OK' if status == 'VALIDE' else ('ABSENT' if status == 'VALIDATEUR_INDISPONIBLE' else 'ECART'),
            'Validation native ' + name, status)
    return profiles, checks


def _slug(repo):
    return str(repo or '').rsplit('/', 1)[-1]


def construct_links(registry, focus, profiles, system_lookup):
    """Union of explicit IK descriptors and the ecosystem relationship registry.
    A graph path labelled 'documented' remains unqualified, even if local files exist.
    """
    rows = {}
    def insert(source, target, contract='', provenance='', baseline='documented', meaning='', evidence=''):
        source = str(source or '').strip(); target = str(target or '').strip()
        if not source or not target or source.casefold() == target.casefold():
            return
        key = (normalize_system_name(source), normalize_system_name(target), contract)
        if key in rows:
            r = rows[key]
            if provenance not in r['origins']: r['origins'].append(provenance)
            if evidence and evidence not in r['references']:r['references'].append(evidence)
            if baseline == 'qualified_local':r['baseline'] = baseline
        else:
            rows[key] = {'id': 'L%03d' % (len(rows)+1), 'source': source,'target': target,
                         'contract': contract, 'origins': [provenance], 'baseline': baseline,
                         'meaning': meaning, 'references': [evidence] if evidence else [],
                         'status': 'NON_VERIFIE', 'detail': '', 'source_code': [], 'target_code': []}
    for (_, version), p in profiles.items():
        contract = p['id'] + '/' + version
        for s in p['sources']:
            for t in p['targets']:
                if s != t:
                    insert(s, t, contract, 'IK index actif', 'declared_ik', p['class'], p['descriptor'])
    for r in registry.get('relations', []):
        insert(r.get('from'), r.get('to'), '', 'Registre écosystème', r.get('evidence_state','documented'),
               r.get('label', ''), r.get('source', ''))
    for path in focus.get('paths', []):
        steps = path.get('spine', []); ids = {s.get('id'): i for i,s in enumerate(steps)}
        def nearest(non_ik_from, direction):
            idx=ids.get(non_ik_from)
            if idx is None:return None
            while 0 <= idx < len(steps):
                obj = steps[idx]
                if obj.get('kind') != 'protocol' and 'interaction' not in _slug(obj.get('repo','')).lower():
                    return _slug(obj.get('repo')) or obj.get('label',{}).get('fr','')
                idx += direction
            return None
        for link in path.get('spine_links',[]):
            f,t = link.get('from'),link.get('to')
            s,tgt = nearest(f, -1), nearest(t, 1)
            contract = link.get('contract','')
            ev = link.get('evidence',{})
            ref = str(ev.get('path',''))
            insert(s, tgt, contract, f"Parcours {path.get('id','')}", link.get('status','documented'),
                   link.get('label',{}).get('fr',''), ref)
    return list(rows.values())



def assess_paths(focus, repo_map, all_links, active_profiles):
    """Compute conservative, documentary path-level status; never claim E2E."""
    result=[]
    for p in focus.get('paths',[]):
        nodes=p.get('spine',[])
        names=[str(node.get('label',{}).get('fr', node.get('id',''))) for node in nodes]
        missing=[]
        for node in nodes:
            slug=_slug(node.get('repo',''))
            local=repo_map.get(slug.casefold())
            if local and not local['path'].is_dir():missing.append(slug)
        declared=[str(l.get('contract','')).strip() for l in p.get('spine_links',[]) if l.get('contract')]
        qualified_ik=[c for c in declared if _match_profile(active_profiles,c)]
        candidates=sum(l.get('status') in ('candidate','proposed') for l in p.get('spine_links',[]))
        if missing:status='REPO_ABSENT'
        elif candidates:status='CANDIDAT'
        elif not declared:status='DOCUMENTE'
        elif len(qualified_ik)==len(declared):status='PROFILS_PRESENTS'
        else:status='A_QUALIFIER'
        result.append({'id':p.get('id',''),'title':p.get('title',{}).get('fr',p.get('id','')),
                       'summary':p.get('summary',{}).get('fr',''),
                       'sequence':' → '.join(names),
                       'steps':len(nodes),'links_declared':len(p.get('spine_links',[])),
                       'contracts_ik':len(qualified_ik),'contracts_declared':len(declared),
                       'candidates':candidates,'missing_repos':sorted(set(missing)),
                       'status':status, 'detail':'Parcours documentaire; ni émission réelle ni réception n’ont été déclenchées.'})
    return result


def _match_profile(contracts, raw):
    if '/' not in raw:
        return None
    name, version = raw.rsplit('/', 1)
    return contracts.get((name,version))


def _repo_for_system(sysname, systems, repo_map):
    key = normalize_system_name(sysname)
    slug = systems.get(key)
    if slug is None:
        slug = _slug(sysname)
    return repo_map.get(str(slug).casefold())


def verify_links(links, root, repo_map, systems, profiles, config, notify=None, stop=None):
    cache = {}; scan_conf = config.get('scan', {})
    contracts = sorted({p['id'] for p in profiles.values()})
    maxfiles = max(10,min(10000,int(scan_conf.get('max_files_per_repo',1000))))
    maxbytes = max(1024,min(1000000,int(scan_conf.get('max_file_bytes',250000))))
    seconds = scan_conf.get('ik_reference_seconds')
    deadline = time.monotonic() + seconds if seconds is not None else None
    for i, link in enumerate(links):
        if stop and stop():raise Stopped()
        src = _repo_for_system(link['source'], systems, repo_map)
        tgt = _repo_for_system(link['target'], systems, repo_map)
        link['source_repo'] = src['name'] if src else ''
        link['target_repo'] = tgt['name'] if tgt else ''
        link['source_exists'] = bool(src and src['path'].is_dir())
        link['target_exists'] = bool(tgt and tgt['path'].is_dir())
        profile = _match_profile(profiles, link['contract'])
        if link['contract'] and profile:
            source_ident = normalize_system_name(link['source'])
            target_ident = normalize_system_name(link['target'])
            if source_ident not in [normalize_system_name(x) for x in profile['sources']] or target_ident not in [normalize_system_name(x) for x in profile['targets']]:
                link['status'] = 'ECART'; link['detail'] = 'Sens producteur/consommateur incohérent avec profil IK actif.'
            elif profile.get('native_validation') != 'VALIDE':
                link['status'] = 'ECART' if profile.get('native_validation') == 'ECART' else 'A_QUALIFIER'
                link['detail'] = 'Validation native ou verrou du profil non confirmé.'
            else:
                link['status'] = 'CONTRAT_ALIGNE'
                link['detail'] = 'Profil IK actif et sens d’échange cohérent. Exécution non prouvée.'
        elif link['contract']:
            link['status'] = 'A_QUALIFIER'
            link['detail'] = 'Contrat cité dans le graphe, non vérifié dans l’index IK actif (peut relever d’un autre propriétaire).'
        else:
            link['status'] = 'CANDIDAT' if link['baseline'] in ('proposed','candidate') else 'DOCUMENTE'
            link['detail'] = 'Liaison de graphe sans contrat IK actif explicite; aucune exécution inférée.'
        if src and not link['source_exists']:
            link['status'] = 'REPO_ABSENT';link['detail'] += ' Dépôt émetteur absent.'
        if tgt and not link['target_exists']:
            link['status'] = 'REPO_ABSENT';link['detail'] += ' Dépôt récepteur absent.'
        # No forced failure for UCKK (not mapped to a concrete local server repo).
        for who, repo in [('source_code',src),('target_code',tgt)]:
            if not repo or not repo['path'].is_dir() or not link['contract']:
                continue
            cache_key = str(repo['path']).lower()
            if cache_key not in cache:
                cache[cache_key] = code_references(repo['path'], contracts, maxfiles, maxbytes, stop, deadline=deadline)
            prof_name = link['contract'].rsplit('/', 1)[0]
            link[who] = cache[cache_key].get(prof_name, [])
        if profile and link['status'] == 'CONTRAT_ALIGNE':
            if link['source_code'] and link['target_code']:
                link['detail'] += ' Références statiques trouvées des deux côtés (pas de preuve runtime).'
            else:
                link['detail'] += ' Références de code bilatérales non démontrées dans le périmètre scanné.'
        if notify:
            notify('progress', ('Liaisons',i+1,len(links)))
    return links


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _is_loopback(host):
    if not host:return False
    if host.lower() == 'localhost':return True
    try:return ipaddress.ip_address(host).is_loopback
    except ValueError:return False


def _json_lookup(value, dotted):
    """Dotted key path or JSON Pointer. Missing values return sentinel."""
    if dotted.startswith('/'):
        parts = [part.replace('~1','/').replace('~0','~') for part in dotted[1:].split('/')]
    else:
        parts = dotted.split('.')
    for part in parts:
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value,list) and part.isdigit() and int(part)<len(value):
            value = value[int(part)]
        else:return False, None
    return True,value


def probe_api(spec, conf, allow_network, allow_remote, stop=None):
    """Only GET / HEAD to explicitly listed endpoints. No credentials, cookies, or redirects."""
    row = {'id':str(spec.get('id','')),'source':str(spec.get('source','')),
           'target':str(spec.get('target','')), 'kind':spec.get('kind','readiness'),
           'method':str(spec.get('method','GET')).upper(),
           'endpoint':'', 'status':'NON_CONFIGURE', 'detail':'', 'http_status':None,
           'latency_ms':None, 'contract':str(spec.get('contract',''))}
    if not spec.get('enabled',False):
        row['status']='DESACTIVE';row['detail']='Sonde désactivée dans configuration.';return row
    if not allow_network:
        row['detail']='Activer explicitement les sondes réseau dans l’interface.';return row
    if stop and stop():raise Stopped()
    method=row['method']
    if method not in ('GET','HEAD'):
        row['status']='REFUSE';row['detail']='Seuls GET et HEAD sont admis (aucun POST de diagnostic).';return row
    url=str(spec.get('url',''))
    try:
        parsed=urlsplit(url)
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise ValueError('URL HTTP(S) invalide ou contient des identifiants/fragments')
        # Deny confusing paths with embedded credentials in the query.
        if parsed.query:
            raise ValueError('Paramètres de requête interdits pour éviter les secrets dans les rapports')
        if not allow_remote and not _is_loopback(parsed.hostname):
            row['status']='REFUSE';row['detail']='Seules les adresses loopback sont autorisées par défaut.';return row
        port = parsed.port
        if port is not None and not (1 <= port <= 65535):raise ValueError('Port invalide')
        row['endpoint'] = f'{parsed.scheme}://{parsed.netloc}{parsed.path or "/"}'
    except (ValueError, TypeError) as exc:
        row['status']='REFUSE';row['detail']=str(exc);return row
    timeout = max(.5,min(15,float(conf.get('timeout_seconds',3))))
    cap = max(1024,min(1048576,int(conf.get('max_response_bytes',65536))))
    opener = build_opener(ProxyHandler({}), NoRedirect(), HTTPHandler(), HTTPSHandler())
    req = Request(url,method=method,headers={'Accept':'application/json, */*',
                                              'User-Agent':'kOA-IK-Continuity-Diagnostic/'+APP_VERSION})
    start=time.perf_counter()
    try:
        try:
            response = opener.open(req, timeout=timeout)
        except HTTPError as e:
            response = e
        with response as r:
            status = int(r.status)
            content_type = str(r.headers.get('Content-Type','')).split(';')[0].strip().lower()
            raw = r.read(cap+1) if method=='GET' else b''
        row['latency_ms']=round((time.perf_counter()-start)*1000,1)
        row['http_status']=status
        expected=spec.get('expect_status',[200]);expected = expected if isinstance(expected,list) else [expected]
        if len(raw)>cap:
            row['status']='ECART';row['detail']='Réponse plus volumineuse que limite.';return row
        if status not in expected:
            row['status']='ECART';row['detail']=f'HTTP {status} au lieu de {expected}.';return row
        desired=spec.get('expect_content_type')
        if desired and str(desired).lower() not in content_type:
            row['status']='ECART';row['detail']=f'Content-Type {content_type} inattendu.';return row
        if spec.get('expect_json'):
            try:data=json.loads(raw.decode('utf-8'))
            except (UnicodeError, json.JSONDecodeError):
                row['status']='ECART';row['detail']='Réponse JSON attendue, illisible.';return row
            for pointer, expected_value in spec['expect_json'].items():
                present, actual=_json_lookup(data,pointer)
                if not present or (expected_value is not None and actual != expected_value):
                    row['status']='ECART';row['detail']='Valeur JSON non conforme: '+str(pointer);return row
        row['status']='API_REPOND';row['detail']=f'HTTP {status}, attentes de lecture respectées. ' + ('Readiness uniquement; handoff non validé.' if row['kind']=='readiness' else 'Réponse API vérifiée, E2E producteur→consommateur non validé.')
    except (URLError, OSError, TimeoutError, ValueError) as exc:
        row['latency_ms']=round((time.perf_counter()-start)*1000,1)
        row['status']='INACCESSIBLE';row['detail']=str(getattr(exc, 'reason', exc))[:250]
    return row



def inspect_traces(root, files, active_profiles, links, stop=None, validator=None):
    """Passively correlate genuine IK Envelope + Receipt records from explicit exports.

    Support JSON arrays, {records: [...]} or {envelopes:[...],receipts:[...]}, and
    JSONL. No payloads/PII copied to report; interaction IDs become short hashes.
    """
    observations=[]; envelopes={}; receipts={}; issues=[]
    if not files:
        return observations, [{'status':'NON_CONFIGURE','detail':'Aucune exportation de traces IK indiquée dans trace_files.'}]
    if validator is None:
        return observations, [{'status':'ECART','detail':'Validateur Python officiel IK indisponible.'}]
    for fn in files[:20]:
        if stop and stop():raise Stopped()
        try:
            if not isinstance(fn,str) or not fn or '\x00' in fn:
                raise ValueError('Chemin de trace vide/invalide')
            rel=Path(fn.replace('\\','/'))
            if rel.is_absolute() or '..' in rel.parts or ':' in fn:
                raise ValueError('Chemin de trace non relatif à C:\\mycode')
            path=safe_under(root,rel)
            if not path.is_file():raise ValueError('Fichier de traces absent')
            if path.stat().st_size>5*1024*1024:raise ValueError('Trace trop grande (5 Mo max)')
            contents=path.read_text(encoding='utf-8-sig')
            if path.suffix.lower()=='.jsonl':
                docs=[json.loads(line) for line in contents.splitlines() if line.strip()]
            else:
                item=json.loads(contents)
                if isinstance(item,list):docs=item
                elif isinstance(item,dict):
                    if 'records' in item:docs=item['records']
                    elif 'envelopes' in item or 'receipts' in item:
                        docs=item.get('envelopes',[])+item.get('receipts',[])
                    else:docs=[item]
                else:raise ValueError('Format export non reconnu')
            if not isinstance(docs,list) or len(docs)>5000:raise ValueError('Liste de traces invalide ou trop volumineuse')
            count=0
            valid_docs=[]
            for doc in docs:
                if not isinstance(doc, dict) or doc.get('specversion') != 'ik/1.1':
                    continue
                if doc.get('record_type') == 'receipt':
                    validator.validate_receipt(doc)
                elif isinstance(doc.get('profile'), dict):
                    validator.validate_envelope(doc)
                else:
                    continue
                valid_docs.append(doc)
            for doc in valid_docs:
                if stop and stop():raise Stopped()
                if not isinstance(doc,dict):continue
                if doc.get('specversion')!='ik/1.1':continue
                if doc.get('record_type')=='receipt':
                    ik=str(doc.get('interaction_id',''))
                    if not ik or doc.get('status') not in ('accepted','rejected','blocked','succeeded','failed'):
                        continue
                    receipts.setdefault(ik,[]).append(doc);count+=1
                elif isinstance(doc.get('profile'),dict):
                    ident=str(doc.get('id',''))
                    if not ident:continue
                    if ident in envelopes:
                        # Do not silently overwrite conflicting envelopes from different exporters.
                        old=envelopes[ident]
                        if old != doc:
                            issues.append({'status':'ECART','detail':'Identifiant d’enveloppe dupliqué avec contenus différents.'})
                            envelopes[ident] = {}
                    else:envelopes[ident]=doc
                    count+=1
            issues.append({'status':'LU','detail':f'{fn}: {count} enregistrements IK reconnus.'})
        except (ValueError,TypeError,OSError,json.JSONDecodeError) as exc:
            issues.append({'status':'ECART','detail':f'{fn}: export IK illisible ou incompatible.'})
        except Exception as exc:
            if type(exc).__module__.split('.')[0] not in ('interaction_kernel', 'jsonschema', 'referencing'):
                raise
            issues.append({'status':'ECART','detail':f'{fn}: validation officielle IK en écart.'})
    for eid, env in envelopes.items():
        if stop and stop():raise Stopped()
        profile=env.get('profile',{})
        system_src=str(env.get('source',{}).get('system','')) if isinstance(env.get('source'),dict) else ''
        system_dst=str(env.get('target',{}).get('system','')) if isinstance(env.get('target'),dict) else ''
        pkey=(str(profile.get('id','')),str(profile.get('version','')))
        contract=pkey[0]+'/'+pkey[1]
        related=receipts.pop(eid,[])
        sanitized_id=hashlib.sha256(eid.encode('utf-8')).hexdigest()[:12]
        problem=[]
        active=active_profiles.get(pkey)
        if not active:
            problem.append('Profil non actif dans l’index IK local')
        else:
            if system_src and normalize_system_name(system_src) not in {normalize_system_name(s) for s in active['sources']}:
                problem.append('Source incompatible avec le profil')
            if system_dst and normalize_system_name(system_dst) not in {normalize_system_name(t) for t in active['targets']}:
                problem.append('Cible incompatible avec le profil')
        for receipt in related:
            receipt_system=receipt.get('source',{}).get('system','') if isinstance(receipt.get('source'),dict) else ''
            if system_dst and normalize_system_name(system_dst)!=normalize_system_name(receipt_system):
                problem.append('La source du Receipt ne correspond pas à la cible de l’enveloppe')
            if receipt.get('specversion')!='ik/1.1':
                problem.append('Version IK du Receipt incohérente')
        statuses=[r['status'] for r in related]
        if len(set(statuses)&{'succeeded','failed','rejected','blocked'})>1:
            problem.append('Receipts terminaux contradictoires')
        if problem:status='ECART'
        elif 'failed' in statuses:status='ECHEC'
        elif 'rejected' in statuses or 'blocked' in statuses:status='REFUSE'
        elif 'succeeded' in statuses:status='RECU_SUCCES'
        elif 'accepted' in statuses:status='ACCEPTE_EN_ATTENTE'
        else:status='SANS_RECEIPT'
        observations.append({'interaction_hash':sanitized_id,'source':system_src,'target':system_dst,
                             'contract':contract,'status':status,'receipt_statuses':statuses,
                             'detail':'; '.join(problem) if problem else ('Receipt corrélé par interaction_id' if related else 'Aucun Receipt corrélé'),
                             'receipt_count':len(related)})
    for ident, left in receipts.items():
        observations.append({'interaction_hash':hashlib.sha256(ident.encode('utf-8')).hexdigest()[:12],
                             'source':'','target':'','contract':'','status':'RECU_ORPHELIN',
                             'receipt_statuses':[x['status'] for x in left],
                             'receipt_count':len(left), 'detail':'Receipt sans enveloppe IK correspondante.'})
    # A correlated export is evidence, not a live production certification.
    for link in links:
        matching=[item for item in observations if item['contract']==link['contract']
                  and normalize_system_name(item['source'])==normalize_system_name(link['source'])
                  and normalize_system_name(item['target'])==normalize_system_name(link['target'])]
        link['trace_evidence']={
            'successful_receipts':sum(x['status']=='RECU_SUCCES' for x in matching),
            'pending_receipts':sum(x['status']=='ACCEPTE_EN_ATTENTE' for x in matching),
            'errors':sum(x['status'] in ('ECART','ECHEC','REFUSE') for x in matching)
        }
        if matching:
            link['detail']+=' Exports IK corrélés: '+str(link['trace_evidence'])+'.'
    return observations, issues


def run(root, reference_dir, config, allow_network=False, allow_remote=False, notify=None, stop=None):
    root=Path(root).expanduser().resolve()
    if not root.is_dir():raise ValueError('Racine introuvable: '+str(root))
    if config.get('format') != 'koa.interaction-diagnostic.config/1':
        raise ValueError('Format de configuration incompatible')
    notify = notify or (lambda *args:None)
    if stop and stop():raise Stopped()
    notify('log','Chargement du graphe kOA et de l’inventaire de 53 dépôts…')
    refs,sources=read_reference_data(root, reference_dir)
    repos=inventory(refs['repositories.json'],root)
    reg,focus=refs['graph-registry.v1.json'],refs['graph-focus.v1.json']
    systems=systems_map(reg,config,repos)
    ik_repo=repos.get('interaction-kernel',{}).get('path',root/'Interaction-Kernel'/'interaction_kernel')
    notify('log','IK: '+str(ik_repo))
    profiles, checks=profile_tree(ik_repo)
    if stop and stop():raise Stopped()
    links=construct_links(reg,focus,profiles,systems)
    notify('log',f'{len(links)} liaisons issues des profils IK et du graphe écosystème.')
    verify_links(links,root,repos,systems,profiles,config,notify,stop)
    paths=assess_paths(focus,repos,links,profiles)
    notify('log','Lecture passive des exports Envelope/Receipt (si configurés)…')
    trace_files = config.get('trace_files', [])
    validator = None
    if trace_files:
        from .native_evidence import ik_trace_validator
        try:
            validator = ik_trace_validator(ik_repo / 'contracts', profiles)
        except (ImportError, OSError, ValueError):
            pass
    trace_rows, trace_issues = inspect_traces(root, trace_files, profiles, links, stop, validator)
    api_rows=[]
    options=config.get('api',{})
    for ix,probe in enumerate(config.get('probes',[])):
        if stop and stop():raise Stopped()
        api_rows.append(probe_api(probe,options,allow_network,allow_remote,stop))
        notify('progress',('API',ix+1,len(config['probes'])))
    present=sum(v['path'].is_dir() for v in repos.values())
    counts={s:sum(1 for v in links if v['status']==s) for s in sorted(set(x['status'] for x in links))}
    api_counts={s:sum(1 for v in api_rows if v['status']==s) for s in sorted(set(x['status'] for x in api_rows))}
    trace_counts={s:sum(1 for v in trace_rows if v['status']==s) for s in sorted(set(x['status'] for x in trace_rows))}
    drift=sum(1 for v in checks if v['status'] in ('ECART','ABSENT'))
    report={
        'format':'koa.ik-continuity-report/1', 'version':APP_VERSION,
        'timestamp':datetime.now(timezone.utc).isoformat(), 'root':str(root),
        'reference_sources':sources,'documents':{'registry_date':reg.get('source_date'),'focus_date':focus.get('source_date')},
        'security':{'network_probes_requested':bool(allow_network), 'remote_opt_in':bool(allow_remote),
                    'mutations':False,'app_test_suites_run':False},
        'summary':{'inventory_repos':len(repos),'repos_present':present,'links':len(links),
                   'link_status':counts,'active_ik_profiles':len(profiles), 'contract_issues':drift,
                   'api_status':api_counts,'api_exercised':sum(x['status'] not in ('DESACTIVE','NON_CONFIGURE','REFUSE') for x in api_rows),
                   'trace_status':trace_counts,'trace_records':len(trace_rows),
                   'live_e2e_certified':0},
        'contracts':checks,
        'profile_validation':{'/'.join(k): {'status': v.get('native_validation'),
            'sources': v['sources'], 'targets': v['targets']} for k,v in profiles.items()},
        'links':links,'paths':paths,'api':api_rows, 'traces':trace_rows,'trace_sources':trace_issues}
    notify('log','Important : aucun résultat ne certifie une E2E de messages producteurs/consommateurs.')
    return report


def write_reports(report, dest):
    directory=Path(dest);directory.mkdir(parents=True,exist_ok=True)
    suffix=datetime.now().strftime('%Y%m%d_%H%M%S')
    base='IK-Continuite_'+suffix
    paths={}
    out=directory/(base+'.json');save_json(out,report);paths['json']=str(out)
    sections={
        'liaisons':(['id','source','target','contract','baseline','status','detail','source_repo','target_repo'],report['links']),
        'parcours':(['id','title','sequence','status','contracts_ik','contracts_declared','missing_repos'],report['paths']),
        'contrats':(['group','name','status','detail','evidence'],report['contracts']),
        'api':(['id','source','target','kind','method','endpoint','status','http_status','latency_ms','detail'],report['api']),
        'traces':(['interaction_hash','source','target','contract','status','receipt_count','detail'],report['traces'])}
    for label,(fields,rows) in sections.items():
        out=directory/(base+'_'+label+'.csv')
        with out.open('w',encoding='utf-8-sig',newline='') as f:
            wr=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore',delimiter=';')
            wr.writeheader();wr.writerows(rows)
        paths[label]=str(out)
    s=report['summary']; out=directory/(base+'.txt')
    with out.open('w',encoding='utf-8') as f:
        f.write('kOA / IK - Diagnostic de continuité inter-dépôts\n')
        f.write('Date: '+report['timestamp']+'\nRacine: '+report['root']+'\n')
        f.write(f'Dépôts présents: {s["repos_present"]}/{s["inventory_repos"]}\n')
        f.write(f'Profils IK actifs: {s["active_ik_profiles"]}\n')
        f.write(f'Liaisons: {s["links"]} - {s["link_status"]}\n')
        f.write(f'Écarts contrats: {s["contract_issues"]}\nAPI: {s["api_status"]}\nTraces IK: {s["trace_status"]}\n')
        f.write('E2E réelle certifiée: NON (nécessite des preuves de bout en bout)\n')
        f.write('Aucune app testée, aucune écriture réseau, aucune modification de dépôt.\n\n')
        f.write('Liaisons à examiner:\n')
        for v in report['links']:
            if v['status'] != 'CONTRAT_ALIGNE':
                f.write(f'[{v["status"]}] {v["source"]} → {v["target"]} {v["contract"]}: {v["detail"]}\n')
    paths['txt']=str(out)
    return paths
