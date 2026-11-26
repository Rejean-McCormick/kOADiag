# -*- coding: utf-8 -*-
"""kOA Interaction Kernel / Inter-repository boundary auditor v3.

Reads source/architecture/explicit passive traces only. Does not run any repo's
app, migrations, internal diagnostics or mutating API calls. Never conflates a
static declaration, a receiver healthcheck and a successful cross-repo exchange.
"""
from __future__ import annotations
from . import VERSION
import collections
import ast
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

from . import ik_diag_core as ik

SCHEMA = 'koa.interrepo-kernel.config/1'
SKIP = ik.EXCLUDES | {'tests', 'test', '__tests__', 'examples', 'example', 'fixtures',
                      'docs', 'wiki', 'site', '.github', '.idea', '.vscode', 'screenshots'}
CODE = {'.py', '.pyw', '.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs', '.go', '.rs', '.php', '.sh', '.ps1'}
CONFIG = {'.json', '.yaml', '.yml', '.toml'}

# Reference lanes explicitly described by the ecosystem contract map; all remain
# documentary, and can be overridden by newer local docs / verified evidence.
DOC_LANES = [
    ('EncyKlopedia', 'Mediatheque', 'encyk.source-evidence-handoff/2.0.0', 'receiver_pending'),
    ('Kristal-Authoring-Kit', 'Kristal-Manager', 'kristal.github-read-surface/1.0', 'integrated_pending'),
    ('Kristal-Manager', 'Konstellation-Light', 'kristal.github-collection-index/1.0', 'blocked'),
    ('Kristal-Manager', 'Kompiler', 'kristal.github-collection-index/1.0', 'blocked'),
    ('Skope', 'EncyKlopedia', 'skope.reviewed-working-export', 'candidate'),
    ('Kristal-Framework', 'Ekole', 'kristal.learning-surface', 'candidate'),
    ('diK', 'Kristalizer', 'dik-kristalizer-owner-boundary', 'proposed'),
]
DOC_REF = 'docs/2-Technical-Reference/40-integration/contract-map.md'

PY_ROUTE = re.compile(r'@(?:[\w]+\.)?(get|post|put|patch|delete|head|options|route|api_route)\s*\(\s*[\"\']([^\"\'\n]{1,180})', re.I)
JS_ROUTE = re.compile(r'\b(?:app|router|server|fastify)\s*\.\s*(get|post|put|patch|delete|head|options)\s*\(\s*[\"\']([^\"\'\n]{1,180})', re.I)
PY_CALL = re.compile(r'\b(?:requests|httpx|session|client|axios|urllib3)\s*\.\s*(get|post|put|patch|delete|head|request)\s*\(\s*[\"\'](https?://[^\"\'\s]{3,250})', re.I)
FETCH_CALL = re.compile(r'\bfetch\s*\(\s*[\"\'`](https?://[^\"\'`\s]{3,250})', re.I)
URL_RE = re.compile(r'https?://(?:localhost|127\.0\.0\.1|\[::1\]|[a-zA-Z][\w.\-]{0,70})(?::\d{1,5})?(?:/[\w\-./{}]*)?', re.I)
EMIT_RE = re.compile(r'\b(?:publish|emit|produce|send_event|publish_event)\s*\(\s*[\"\']([\w.\-:/]{3,100})[\"\']', re.I)
SUB_RE = re.compile(r'\b(?:subscribe|consume|on_event|subscribe_event)\s*\(\s*[\"\']([\w.\-:/]{3,100})[\"\']', re.I)
ENV_RE = re.compile(r'\b(?:os\.getenv|os\.environ\.get)\s*\(\s*[\"\']([A-Z][A-Z0-9_]{3,90})|\bprocess\.env\.([A-Z][A-Z0-9_]{3,90})')
SECRET = re.compile(r'(?:token|secret|password|passwd|api.key|private.key|credential)', re.I)
VALID_ROUTE = re.compile(r'^/[\w/{}.:\-~]*$')
PORT_ALIAS = re.compile(r'[^a-z0-9]+')


def norm(s):
    return PORT_ALIAS.sub('', str(s or '').casefold())


def ensure_safe(root, relative):
    if not isinstance(relative, str) or not relative or '\0' in relative:
        raise ValueError('Chemin relatif invalide')
    p = Path(relative)
    if p.is_absolute() or p.drive or '..' in p.parts:
        raise ValueError('Chemin hors racine non autorisé: ' + str(relative))
    return ik.safe_under(root, p)


def source_line(text, offset):
    return text.count('\n', 0, offset) + 1


def ev(path, line, repo_root):
    return {'file': str(path.relative_to(repo_root)).replace('\\', '/'), 'line': line}


def _capture_match(regex, text, file, base, kind, target):
    for m in regex.finditer(text):
        target.append({'kind': kind, 'value': m.group(1), 'evidence': ev(file, source_line(text, m.start()), base)})


def canonical_url(raw):
    """Remove query, fragments and credentials; only safe URL parts are returned."""
    try:
        p = urlsplit(raw)
        if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
            return None
        port = p.port
        if port and not (0 < port < 65536):
            return None
        host = p.hostname.lower()
        return {'url': f'{p.scheme}://{p.netloc}{p.path or "/"}',
                'scheme': p.scheme, 'host': host, 'port': port, 'path': p.path or '/'}
    except (ValueError, AttributeError):
        return None


def _manifest_deps(repo_dir, name):
    """Direct dependency declarations only: never resolves or installs packages."""
    deps, packages, issues = [], [], []
    def add(dep, version, location, kind):
        if isinstance(dep, str) and dep and len(dep) < 140:
            deps.append({'repo': name, 'package': dep, 'constraint': str(version or ''),
                         'source_file': location, 'kind': kind, 'target_repo': '', 'status': 'EXTERNE'})
    p = repo_dir / 'package.json'
    if p.is_file() and p.stat().st_size < 600000:
        try:
            obj = ik.load_json(p)
            packages.append({'name': str(obj.get('name', '')), 'version': str(obj.get('version',''))})
            for fld in ('dependencies', 'peerDependencies', 'optionalDependencies'):
                if isinstance(obj.get(fld), dict):
                    for dep, version in obj[fld].items():
                        add(dep, version, 'package.json', fld)
        except (ValueError, OSError, TypeError) as exc:
            issues.append({'status': 'ERREUR', 'repo': name, 'element': 'package.json', 'detail': str(exc)[:150]})
    p = repo_dir / 'pyproject.toml'
    if p.is_file() and p.stat().st_size < 400000:
        try:
            raw=p.read_text(encoding='utf-8-sig')
            try:
                import tomllib
                obj=tomllib.loads(raw)
                proj=obj.get('project',{})
                packages.append({'name': str(proj.get('name','')), 'version': str(proj.get('version',''))})
                for item in proj.get('dependencies',[]):
                    mat=re.match(r'\s*([A-Za-z0-9][\w.\-]*)(?:\[[^]]*\])?\s*(.*)',str(item))
                    if mat:add(mat.group(1),mat.group(2),'pyproject.toml','PEP621')
                for group in proj.get('optional-dependencies',{}).values():
                    if isinstance(group,list):
                        for item in group:
                            mat=re.match(r'\s*([A-Za-z0-9][\w.\-]*)\s*(.*)',str(item))
                            if mat:add(mat.group(1),mat.group(2),'pyproject.toml','optional')
                poetry=obj.get('tool',{}).get('poetry',{})
                if isinstance(poetry,dict):
                    packages.append({'name':str(poetry.get('name','')),'version':str(poetry.get('version',''))})
                    for dep, value in poetry.get('dependencies',{}).items():
                        if dep.casefold()!='python':add(dep,value,'pyproject.toml','poetry')
            except ImportError:
                # Python 3.9/3.10: conservative lexer of package/version and quoted dependencies.
                project=re.search(r'(?ms)^\[project\]\s*(.*?)(?=^\[|\Z)',raw)
                if project:
                    section=project.group(1)
                    packages.append({'name':next(iter(re.findall(r'^name\s*=\s*["\']([^"\']+)',section,re.M)),''),
                                     'version':next(iter(re.findall(r'^version\s*=\s*["\']([^"\']+)',section,re.M)),'')})
                    match=re.search(r'(?ms)^dependencies\s*=\s*\[(.*?)\]',section)
                    if match:
                        for spec in re.findall(r'["\']([^"\']+)["\']',match.group(1)):
                            m=re.match(r'\s*([\w.\-]+)\s*(.*)',spec)
                            if m:add(m.group(1),m.group(2),'pyproject.toml','PEP621')
        except (OSError, ValueError, TypeError) as exc:
            issues.append({'status': 'ERREUR', 'repo': name, 'element':'pyproject.toml', 'detail': str(exc)[:150]})
    for fname in ('requirements.txt','requirements-prod.txt','requirements.in'):
        p=repo_dir/fname
        if not p.is_file() or p.stat().st_size > 150000:continue
        try:
            for line in p.read_text(encoding='utf-8',errors='replace').splitlines():
                line=line.split('#',1)[0].strip()
                if not line or line.startswith(('-r','--')):continue
                if line.startswith(('-e ', 'file:', 'git+')):
                    add(line,'',fname,'local-or-vcs');continue
                m=re.match(r'^([A-Za-z][\w.\-]*)\s*(.*)$',line)
                if m:add(m.group(1),m.group(2),fname,'pip')
        except OSError as exc:
            issues.append({'status':'ERREUR','repo':name,'element':fname,'detail':str(exc)[:150]})
    return deps, packages, issues


def inventory_surface(repo_name, repo_dir, cfg, stop=None, *, deadline=None):
    """Index only declared boundary surfaces; no internal unit/app execution."""
    limits=cfg.get('scan',{})
    file_ceiling = 60000 if cfg.get('integral_scan') else 20000
    max_files=max(20,min(file_ceiling,int(limits.get('max_files_per_repo',8500))))
    import_limit = 100000 if cfg.get('integral_scan') else 2500
    excluded_roots = {
        'Konnaxion': {'_konnaxion_i18n_backups'},
        'Kristalizer': {'sortie'},
    }.get(repo_name, set())
    generated_reports = {
        'Ekole-Quebec': {'plans/moodle_projection_dry_run.json'},
        'Konnaxion': {
            'frontend/artifacts/i18n-extraction/ui-translation-occurrences.json',
            'frontend/artifacts/i18n-extraction/ui-translation-unique.json',
        },
        'Kristal-Manager': {
            'rapports/analyse-20261105-181520-c7ac78/rapport_global.json',
            'rapports/analyse-20261107-071044-c33cda/rapport_global.json',
        },
    }.get(repo_name, set())
    large_data_files = {
        'Konnaxion-Worlds': {'universes/fakeplant/fixture/employes.json'},
        'Orgo-Worlds': {'fakeplant/fixture/employes.json'},
        'Konstellation': {
            'data/biblical.pack.local.json',
            'data/theophile-biblical.enriched.pack.json',
            'data/theophile.semantic.enriched.json',
        },
    }.get(repo_name, set())
    max_bytes=max(2048,min(1000000,int(limits.get('max_file_bytes',220000))))
    surface={'repo':repo_name,'files_scanned':0,'files_eligible':0,'files_oversized':0,
             'files_unreadable':0,'scan_limit_reached':False,'scan_scope':'boundary-relevant code/config',
             'boundary_scan_gaps':[], 'boundary_scan_gap_count':0,
             'files_unselected':0,'files_index_overflow':0,'unselected_by_root':[],
             'oversized_by_root':[],
             'routes':[],'calls':[],'urls':[],'events_pub':[],'events_sub':[],
             'env_names':[],'imports':[],'schemas':[],'deps':[],'packages':[],'issues':[]}
    surface['deps'],surface['packages'],surface['issues']=_manifest_deps(repo_dir,repo_name)
    # Two-pass deterministic scan: prioritize boundary entrypoints instead of
    # exhausting the budget on alphabetically earlier unrelated source files.
    candidates = []
    terms = ('api', 'route', 'client', 'server', 'service', 'integration', 'interop',
             'kernel', 'bridge', 'contract', 'schema', 'event', 'message', 'webhook',
             'adapter', 'transport', 'openapi', 'graphql', 'rpc', 'endpoint', 'sdk')
    configured_paths = set()
    for rule in cfg.get('boundary_expectations', []):
        if not isinstance(rule, dict):
            continue
        for side in ('source', 'target'):
            if rule.get(side) == repo_name and isinstance(rule.get(side + '_files'), list):
                configured_paths.update(str(p).replace('\\', '/').casefold() for p in rule[side + '_files'])

    def gap(relative, reason, priority):
        if priority > 0:
            return
        surface['boundary_scan_gap_count'] += 1
        if len(surface['boundary_scan_gaps']) < 1000:
            surface['boundary_scan_gaps'].append({'path': relative, 'reason': reason})

    max_index = max(60000, max_files * 6)
    index_overflow = 0
    visited = 0
    visit_limit = limits.get('max_surface_entries_per_repo')
    indexing_limited = False

    def index_limited():
        return ((visit_limit is not None and visited >= visit_limit) or
                (deadline is not None and time.monotonic() >= deadline))

    for current, dirs, files in os.walk(repo_dir, followlinks=False):
        if index_limited():
            indexing_limited = True
            break
        visited += 1
        if stop and stop():raise ik.Stopped()
        dirs[:] = sorted(d for d in dirs if d not in SKIP and not d.startswith('.')
                         and not (Path(current) == repo_dir and d.casefold() in excluded_roots))
        for filename in sorted(files):
            if index_limited():
                indexing_limited = True
                break
            visited += 1
            path=Path(current)/filename
            if path.is_symlink() or path.suffix.lower() not in CODE | CONFIG:
                continue
            relative = path.relative_to(repo_dir).as_posix()
            folded = relative.casefold()
            if folded in generated_reports and folded not in configured_paths:
                continue
            surface['files_eligible'] += 1
            pieces = re.split(r'[/_.\-]', folded)
            priority = 0 if any(any(x in part for x in terms) for part in pieces) else (1 if path.suffix.lower() in CODE else 2)
            if folded in configured_paths:
                priority = -1
            if len(candidates) >= max_index and priority >= 0:
                index_overflow += 1
                gap(relative, 'LIMITE_INDEX', priority)
                continue
            candidates.append((priority, relative, path))
        if indexing_limited:
            break
    ordered=sorted(candidates,key=lambda row:(row[0],row[1].casefold(),row[1]))
    omitted=ordered[max_files:]
    surface['files_index_overflow']=index_overflow
    surface['files_unselected']=len(omitted)+index_overflow
    surface['scan_limit_reached'] = bool(index_overflow or omitted or indexing_limited)
    surface['traversal_limited'] = indexing_limited
    for priority, relative, _ in omitted:
        gap(relative, 'LIMITE_SCAN', priority)
    omission_counts=collections.Counter((rel.split('/')[0] if '/' in rel else '[root]')
                                        for _,rel,_ in omitted)
    if index_overflow:
        omission_counts['[index-budget-other]']+=index_overflow
    surface['unselected_by_root']=[{'directory':name,'files':count}
                                   for name,count in omission_counts.most_common(12)]
    oversize_counts=collections.Counter()
    selected = ordered[:max_files]
    for ix, (priority, relative, path) in enumerate(selected):
        if stop and stop():raise ik.Stopped()
        if deadline is not None and time.monotonic() >= deadline:
            surface['scan_limit_reached'] = surface['traversal_limited'] = True
            surface['files_unselected'] += len(selected) - ix
            for unscanned_priority, unscanned_path, _ in selected[ix:]:
                gap(unscanned_path, 'BUDGET_TEMPS', unscanned_priority)
            break
        try:
            large_data = (
                relative.casefold() in large_data_files or
                (repo_name == 'kristal-public' and relative.startswith('kristals/')
                 and path.suffix.lower() == '.json')
            )
            file_limit = 24_000_000 if cfg.get('integral_scan') and large_data else max_bytes
            if path.stat().st_size > file_limit:
                surface['files_oversized']+=1
                gap(relative, 'TAILLE', priority)
                rel=path.relative_to(repo_dir).as_posix()
                oversize_counts[rel.split('/')[0] if '/' in rel else '[root]']+=1
                continue
            raw=path.read_text(encoding='utf-8-sig',errors='replace')
        except (OSError, ValueError):
            surface['files_unreadable']+=1
            gap(relative, 'LECTURE', priority)
            continue
        surface['files_scanned']+=1
        rel=ev(path,0,repo_dir)['file']
        iscode=path.suffix.lower() in CODE
        if iscode:
            if path.suffix.lower() in ('.py', '.pyw'):
                try:
                    tree=ast.parse(raw,filename=rel)
                    for node in ast.walk(tree):
                        if isinstance(node,ast.Import):
                            for name in node.names:
                                surface['imports'].append({'name':name.name.split('.')[0],
                                  'evidence':{'file':rel,'line':node.lineno}})
                        elif isinstance(node,ast.ImportFrom) and node.level==0 and node.module:
                            surface['imports'].append({'name':node.module.split('.')[0],
                                  'evidence':{'file':rel,'line':node.lineno}})
                except SyntaxError:
                    pass  # An application-internal syntax error is not the boundary audit's scope.
            elif path.suffix.lower() in ('.js','.jsx','.ts','.tsx','.mjs','.cjs'):
                for match in re.finditer(r'''\b(?:from\s+|require\s*\(\s*|import\s*\(\s*)[\"']([^\"']{2,100})''',raw):
                    pkg=match.group(1)
                    if pkg.startswith(('.', '/', '#')):continue
                    surface['imports'].append({'name':pkg.split('/')[0] if not pkg.startswith('@') else '/'.join(pkg.split('/')[:2]),
                        'evidence':ev(path,source_line(raw,match.start()),repo_dir)})
            for pattern in (PY_ROUTE,JS_ROUTE):
                for match in pattern.finditer(raw):
                    method,url=match.group(1).upper(),match.group(2)
                    if url.startswith('/') and VALID_ROUTE.match(url):
                        surface['routes'].append({'method':method,'path':url,'repo':repo_name,
                            'evidence':ev(path,source_line(raw,match.start()),repo_dir)})
            for pattern,method_name in ((PY_CALL,None),(FETCH_CALL,'GET')):
                for match in pattern.finditer(raw):
                    method=(match.group(1).upper() if method_name is None else method_name)
                    value=match.group(2) if method_name is None else match.group(1)
                    parsed=canonical_url(value)
                    if parsed:
                        surface['calls'].append(dict(parsed,method=method,repo=repo_name,
                            evidence=ev(path,source_line(raw,match.start()),repo_dir)))
            _capture_match(EMIT_RE,raw,path,repo_dir,'publish',surface['events_pub'])
            _capture_match(SUB_RE,raw,path,repo_dir,'subscribe',surface['events_sub'])
            for match in ENV_RE.finditer(raw):
                key=match.group(1) or match.group(2)
                if re.search(r'(?:URL|ENDPOINT|HOST|PORT|BROKER|TOPIC|SERVICE|QUEUE|API|OIDC|SCOPE|AUDIENCE|TENANT)',key):
                    surface['env_names'].append({'name':key,'evidence':ev(path,source_line(raw,match.start()),repo_dir)})
            for match in URL_RE.finditer(raw):
                val=canonical_url(match.group(0))
                if val and (val['host'] in ('localhost','127.0.0.1','::1') or '.' not in val['host']):
                    surface['urls'].append(dict(val,evidence=ev(path,source_line(raw,match.start()),repo_dir)))
        if path.suffix.lower() == '.json' and (path.name.lower().endswith('.schema.json') or 'openapi' in path.name.lower() or 'schemas' in (part.lower() for part in path.parts)):
            try:
                j=json.loads(raw)
                if isinstance(j,dict):
                    schema_id=str(j.get('$id') or '')
                    schema_ver=str(j.get('version') or j.get('schema_version') or '')
                    # Do not confuse unrelated schemas that share a filename.
                    surface['schemas'].append({'repo':repo_name,'file':rel,'id':schema_id,
                        'version':schema_ver,'digest':hashlib.sha256(json.dumps(j,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest(),
                        'refs':_find_local_refs(j),'status':'LISIBLE'})
                    if isinstance(j.get('paths'),dict):
                        for route,methods in j['paths'].items():
                            if not isinstance(methods,dict):continue
                            for method in methods:
                                if method.upper() in ('GET','HEAD','POST','PUT','PATCH','DELETE'):
                                    surface['routes'].append({'repo':repo_name,'method':method.upper(),
                                        'path':route,'evidence':{'file':rel,'line':0}})
            except (ValueError,TypeError):
                surface['issues'].append({'status':'ERREUR','repo':repo_name,'element':rel,'detail':'JSON de schéma illisible'})
    surface['oversized_by_root']=[{'directory':name,'files':count}
                                  for name,count in oversize_counts.most_common(12)]
    # Remove duplicates without storing code or values of env vars.
    for name in ('routes','calls','urls','events_pub','events_sub','env_names','imports'):
        seen=set(); out=[]
        for x in surface[name]:
            key=(x.get('method'),x.get('path'),x.get('url'),x.get('value'),x.get('name'),
                 x['evidence']['file'],x['evidence']['line'])
            if key not in seen:
                seen.add(key);out.append(x)
        limit = import_limit if name == 'imports' else 2500
        if len(out) > limit:
            surface['scan_limit_reached'] = True
            for item in out[limit:]:
                gap(item['evidence']['file'], 'LIMITE_' + name.upper(), 0)
        surface[name]=out[:limit]
    return surface


def _find_local_refs(obj):
    found=[]; pending=[obj];nodes=0
    while pending and nodes<20000:
        node=pending.pop();nodes+=1
        if isinstance(node,dict):
            ref=node.get('$ref')
            if isinstance(ref,str) and not ref.startswith('#') and not re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:',ref):
                found.append(ref.split('#',1)[0])
            pending.extend(node.values())
        elif isinstance(node,list):pending.extend(node)
    return sorted(set(found))[:100]


def _repo_aliases(repos, surfaces):
    aliases={}; conflict=set()
    for name,s in surfaces.items():
        candidates=[name]+[p.get('name') for p in s['packages'] if p.get('name')]
        for alias in candidates:
            key=norm(alias)
            if not key:continue
            if key in aliases and aliases[key]!=name:conflict.add(key)
            else:aliases[key]=name
    return {a:r for a,r in aliases.items() if a not in conflict}


def _target_for_url(parsed, service_endpoints, aliases):
    """Host/port mapping is explicit; ambiguous loopback port is not resolved."""
    matched=[]
    for repo, urls in service_endpoints.items():
        if not isinstance(urls,list):continue
        for configured in urls:
            target=canonical_url(configured)
            if not target:continue
            if target['host'] == parsed['host'] and target['port'] == parsed['port'] and target['scheme'] == parsed['scheme']:
                matched.append(repo)
    matched=list(dict.fromkeys(matched))
    if len(matched)==1:return matched[0], 'port_configure'
    if len(matched)>1:return '', 'port_ambigu'
    host=norm(parsed['host'].split('.')[0])
    if host in aliases and parsed['host'] not in ('localhost','127.0.0.1','::1'):
        return aliases[host], 'hote_nominal'
    return '', 'non_resolu'


def _add_relation(rows, src, tgt, contract='', provenance='', maturity='documented', basis=None):
    src=str(src or '').strip();tgt=str(tgt or '').strip()
    if not src or not tgt or norm(src)==norm(tgt):return None
    key=(norm(src),norm(tgt),str(contract or '').strip())
    if key not in rows:
        rows[key]={'source':src,'target':tgt,'contract':contract,'origins':[],
                   'maturity':maturity,'evidence':[], 'source_repo':'','target_repo':'',
                   'dimensions':{},'qualification':'NON_VERIFIE','detail':''}
    r=rows[key]
    if provenance and provenance not in r['origins']:r['origins'].append(provenance)
    if basis and basis not in r['evidence']:r['evidence'].append(basis)
    if r['maturity'] in ('candidate','proposed') and maturity not in ('candidate','proposed'):
        r['maturity']=maturity
    return r


def _find_relation(rows,src,tgt):
    matches=[v for (a,b,c),v in rows.items() if a==norm(src) and b==norm(tgt)]
    return matches


def _known_repo_name(raw, alias):
    return alias.get(norm(raw),'')


def _code_bridge_summary(surfaces, deps, endpoints, events):
    result=[]
    for repo,s in sorted(surfaces.items()):
        result.append({'repo':repo,'files_scanned':s['files_scanned'],
            'truncated':s['scan_limit_reached'],'api_routes':len(s['routes']),
            'api_outbound':len(s['calls']),'event_publish':len(s['events_pub']),
            'event_subscribe':len(s['events_sub']),'schema_count':len(s['schemas']),
            'declared_deps':sum(d['repo']==repo for d in deps),'imports_scanned':len(s['imports']),
            'env_keys':len(s['env_names'])})
    return result


def _load_exchanges(root, paths, allowed, stop=None, *, linux_root=None, policy=None):
    """Correlate exact boundary identities within one transaction and attempt."""
    from .evidence_adapters import load
    records, findings = load(root, paths, stop=stop, linux_root=linux_root)
    revisions = (policy or {}).get('reference_revisions', {})
    if not isinstance(revisions, dict):
        revisions = {}
    grouped = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in records:
        if allowed is not None and (r['source'] not in allowed or r['target'] not in allowed):
            continue
        protocol = 'EVENT' if r['phase'] in ('published', 'consumed') or r['channel'] else 'API'
        identity = (r['hash'], r['journey_hash'], r['attempt_hash'], r['source'], r['target'],
                    r['contract'], r['method'], r['path'], r['channel'], r['mode'], protocol)
        items = grouped[identity][r['phase']]
        if len(items) < 2 and r not in items:
            items.append(r)
    out = []
    for identity, phases in grouped.items():
        hid, journey, attempt, source, target, contract, method, path, channel, mode, protocol = identity
        sent = phases.get('published' if protocol == 'EVENT' else 'sent', [])
        received = phases.get('consumed' if protocol == 'EVENT' else 'received', [])
        responses = phases.get('response', [])
        ambiguous = any(len(items) > 1 for items in (sent, received, responses))
        s = sent[0] if sent else None
        r = received[0] if received else None
        reply = responses[0] if responses else None
        used = [x for x in (s, r, reply) if x]
        independent = bool(s and r and s['file'] != r['file'] and s['file_sha256'] != r['file_sha256'])
        trusted = independent and s['owner'] == source and r['owner'] == target
        times = [x['timestamp'] for x in used]
        response_status = reply['status'] if reply else ''
        expected = (revisions.get(source), revisions.get(target))
        observed = {(x['source_revision'], x['target_revision']) for x in used}
        revision_status = 'NON_VERIFIEE'
        if len(observed) > 1 and len({pair for pair in observed if all(pair)}) > 1:
            revision_status = 'INCOMPATIBLE'
        if all(expected):
            if any(value and value != expected[i] for pair in observed for i, value in enumerate(pair)):
                revision_status = 'INCOMPATIBLE'
            elif observed == {expected}:
                revision_status = 'ALIGNEE'
        out.append({
            'hash': hid, 'journey_hash': journey, 'attempt_hash': attempt,
            'source': source, 'target': target, 'kind': protocol,
            'contract': contract, 'mode': mode, 'method': method, 'path': path, 'channel': channel,
            'status': 'TENTATIVES_AMBIGUES' if ambiguous else ('PAIRE_OBSERVEE' if s and r else
                        ('RECEPTION_NON_PROUVEE' if s else 'EMISSION_NON_PROUVEE')),
            'response_observed': bool(reply),
            'response_ok': bool(reply) and ((response_status.isascii() and response_status.isdigit()
                            and 200 <= int(response_status) < 300)
                            or response_status.casefold() in ('ok', 'success', 'succeeded', 'accepted')),
            'response_status': response_status,
            'response_provenance': bool(s and reply and reply['owner'] == target
                                        and s['file_sha256'] != reply['file_sha256']),
            'provenance_attested': trusted, 'independent_sources': independent,
            'digest_pinned': all(x['digest_pinned'] for x in used),
            'revision_status': revision_status,
            'observed_revisions': sorted(observed),
            'timestamps_valid': bool(s and r) and all(times) and times == sorted(times),
            'occurred_at': s['timestamp'] if s else None,
            'received_at': r['timestamp'] if r else None,
            'responded_at': reply['timestamp'] if reply else None,
            'detail': 'Tentatives concurrentes ou dupliquées' if ambiguous else 'Rapprochement des métadonnées exportées',
            'evidence': sorted({x['file'] for x in used}),
            'evidence_sha256': {x['file']: x['file_sha256'] for x in used},
        })
    return out, findings


def detect_workflows(root, surfaces, alias, stop=None):
    """Cross-repo GitHub workflow references, read-only. No workflow is executed."""
    workflows=[]
    use_re=re.compile(r"(?m)^\s*(?:-\s*)?uses\s*:\s*[\"']?([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@([A-Za-z0-9_.\-]+)")
    for repo,surface in surfaces.items():
        base=root/surface['relative'] if 'relative' in surface else surface['repo_path']
        folder=base/'.github'/'workflows'
        if not folder.is_dir() or not folder.resolve().is_relative_to(base.resolve()):continue
        for path in sorted(folder.iterdir()):
            if stop and stop():raise ik.Stopped()
            if path.suffix.lower() not in ('.yaml','.yml') or path.is_symlink() or path.stat().st_size>250000:continue
            try:raw=path.read_text(encoding='utf-8-sig',errors='replace')
            except OSError:continue
            for m in use_re.finditer(raw):
                target=alias.get(norm(m.group(1).rsplit('/',1)[-1]))
                if target and target!=repo:
                    ref=m.group(2)
                    workflows.append({'source':repo,'target':target,'reference':m.group(1),
                        'revision':ref,'status':'REF_MOBILE_A_EXAMINER' if ref in ('main','master','develop','dev','latest') else 'REFERENCE_DECLARÉE',
                        'evidence':{'file':str(path.relative_to(base)).replace('\\','/'),'line':source_line(raw,m.start())}})
    return workflows


def detect_env_edges(surfaces, alias):
    """Configuration boundary hints; variable *names* only, not their values."""
    edges=[]
    for repo,surf in surfaces.items():
        for obj in surf['env_names']:
            key=obj['name']
            for name,target in alias.items():
                if len(name)<4 or target==repo:continue
                # Compare uppercase underscore-separated tokens, no fuzzy substring matches.
                parts=set(re.split(r'_+',key.upper()))
                if name.upper() in parts and re.search(r'(?:API|URL|HOST|SERVICE|QUEUE|TOPIC|ENDPOINT)',key):
                    edges.append({'source':repo,'target':target,'variable':key,
                         'status':'REFERENCE_CONFIG_STATIQUE','evidence':obj['evidence']})
                    break
    return edges


def evaluate_boundary_expectations(root, requests, repo_map, surfaces):
    """Checks only user-declared files and source-level env references. No auth claims."""
    out=[];by_name={v['name']:v for v in repo_map.values()}
    for row in requests:
        if not isinstance(row,dict):continue
        src=str(row.get('source',''));tgt=str(row.get('target',''))
        name=str(row.get('id',''))[:100]
        missing=[]
        requirements=sum(len(row.get(k,[])) for k in ('source_files','target_files','source_env_names','target_env_names') if isinstance(row.get(k,[]),list))
        if requirements==0:missing.append('Aucune obligation vérifiable configurée')
        for side,repo in (('source',src),('target',tgt)):
            item=by_name.get(repo)
            if not item or not item['path'].is_dir():
                missing.append(f'{side}: repo absent');continue
            base=item['path'].resolve()
            for relative in (row.get(f'{side}_files',[]) if isinstance(row.get(f'{side}_files',[]),list) else []):
                p=Path(str(relative))
                if p.is_absolute() or '..' in p.parts or not (base/p).resolve().is_relative_to(base) or not (base/p).is_file():
                    missing.append(f'{side}: fichier absent / non autorisé: {str(relative)[:80]}')
            names={x['name'] for x in surfaces.get(repo,{}).get('env_names',[])}
            for env_name in (row.get(f'{side}_env_names',[]) if isinstance(row.get(f'{side}_env_names',[]),list) else []):
                if env_name not in names:missing.append(f'{side}: référence statique absente: {str(env_name)[:80]}')
        out.append({'id':name,'source':src,'target':tgt,
            'status':'EXIGENCE_MANQUANTE' if missing else 'EXIGENCE_DECLAREE_PRESENTE',
            'detail':'; '.join(missing) if missing else 'Fichiers et références déclarés présents — comportement non validé',
            'note':str(row.get('note',''))[:240]})
    return out


def run(root, references, cfg, *, allow_network=False, allow_remote=False, notify=None, stop=None):
    """Full cross-repo audit. API probes opt-in. No subprocess / internal app tests."""
    started=time.monotonic();root=Path(root).expanduser().resolve()
    if not root.is_dir():raise ValueError('Racine inaccessible: '+str(root))
    if cfg.get('format') != SCHEMA:raise ValueError('Configuration v3 incompatible')
    notify=notify or (lambda *_:None)
    check=lambda: (_ for _ in ()).throw(ik.Stopped()) if stop and stop() else None
    check()
    ik_cfg=json.loads(json.dumps(ik.DEFAULT_CONFIG))
    custom=cfg.get('ik',{})
    for k in ('probes','trace_files','system_repo_overrides'):
        if k in custom:ik_cfg[k]=custom[k]
    ik_cfg['scan']=dict(cfg.get('scan',{}))
    notify('log','Analyse du registre, des parcours et des contrats IK…')
    base=ik.run(root,references,ik_cfg,allow_network=allow_network,allow_remote=allow_remote,notify=notify,stop=stop)
    check()
    data,_=ik.read_reference_data(root,references)
    repo_map=ik.inventory(data['repositories.json'],root)
    sources={}
    deferred=set()
    seconds=ik_cfg['scan'].get('surface_seconds')
    deadline=time.monotonic()+seconds if seconds is not None else None
    focus = {'interaction-kernel', 'koa-linux-koali', 'orgo', 'konnaxion', 'konnaxion-worlds', 'konfid'}
    ordered_repos = sorted(repo_map.items(), key=lambda pair: (
        deadline is not None and pair[0].casefold() not in focus, pair[0]))
    for key,entry in ordered_repos:
        check()
        if not entry['path'].is_dir():continue
        name=entry['name']
        if deadline is not None and time.monotonic() >= deadline:
            deferred.add(name)
            continue
        notify('progress',('Repos',len(sources)+1,len(repo_map)))
        repo_deadline = min(deadline, time.monotonic()+2) if deadline is not None else None
        sources[name]=inventory_surface(name,entry['path'],cfg,stop,deadline=repo_deadline)
    notify('log',f"Surface passive: {len(sources)}/{len(repo_map)} dépôts présents.")
    check()
    alias=_repo_aliases(repo_map,sources)
    for entry in repo_map.values():alias.setdefault(norm(entry['name']),entry['name'])
    extra_alias=cfg.get('repo_aliases',{})
    if isinstance(extra_alias,dict):
        for k,v in extra_alias.items():
            if v in sources or any(x['name']==v for x in repo_map.values()):alias[norm(k)]=v
    # A source import is a static coupling, even without a pinned manifest dependency.
    import_edges=[]
    for owner,s in sources.items():
        for item in s['imports']:
            target=alias.get(norm(item['name']))
            if target and target!=owner:
                import_edges.append({'source':owner,'target':target,'module':item['name'],
                    'status':'IMPORT_STATIQUE','evidence':item['evidence']})
    # Additional inter-repo coupling surfaces (never execute workflows or read env values).
    for name,surf in sources.items():
        surf['repo_path']=next(x['path'] for x in repo_map.values() if x['name']==name)
        surf['relative']=next(x['relative'] for x in repo_map.values() if x['name']==name)
    workflows=detect_workflows(root,sources,alias,stop)
    env_edges=detect_env_edges(sources,alias)
    boundary_expectations=evaluate_boundary_expectations(root,cfg.get('boundary_expectations',[]),repo_map,sources)
    # Graph + active IK explicit relations
    rows={}
    for old in base['links']:
        src=_known_repo_name(old.get('source_repo') or old['source'],alias) or old.get('source_repo') or old['source']
        tgt=_known_repo_name(old.get('target_repo') or old['target'],alias) or old.get('target_repo') or old['target']
        r=_add_relation(rows,src,tgt,old.get('contract',''),'IK + graphe',old.get('baseline','documented'))
        if r:
            r['ik_status']=old['status'];r['ik_detail']=old['detail']
            r['ik_refs_src']=old.get('source_code',[]);r['ik_refs_dst']=old.get('target_code',[])
    for src,tgt,contract,maturity in DOC_LANES:
        _add_relation(rows,src,tgt,contract,'Carte de contrats kOA',maturity,DOC_REF)
    for custom in cfg.get('relations',[]):
        if not isinstance(custom,dict):continue
        _add_relation(rows,custom.get('source'),custom.get('target'),custom.get('contract',''),
                      'Déclaration utilisateur',custom.get('status','declared'),custom.get('reference',''))
    # Exact declared dependencies in manifests only; version drift is not a proof of failed calls.
    dependencies=[];packages={}
    for owner,s in sources.items():
        for p in s['packages']:
            if p.get('name') and p.get('version'):packages[norm(p['name'])]=(owner,p['version'])
        for d in s['deps']:
            depkey=norm(d['package'])
            target=alias.get(depkey)
            if not target and d['kind']=='local-or-vcs':
                for alias_name,target_name in alias.items():
                    if len(alias_name)>4 and alias_name in norm(d['package']):target=target_name;break
            if target and target != owner:
                d['target_repo']=target
                d['status']='DECLAREE'
                _add_relation(rows,owner,target,'','Dépendance manifeste','declared',d['source_file'])
                pinned=re.match(r'^\s*==\s*([\w.+\-]+)',d['constraint'])
                if pinned and depkey in packages and packages[depkey][1]!=pinned.group(1):
                    d['status']='VERSION_A_EXAMINER'
                    d['detail']=f"Pin {pinned.group(1)}; version source {packages[depkey][1]} (sans résolution du paquet installé)"
            dependencies.append(d)
    # Note: package versions may be indexed after a consumer; resolve in a 2nd pass.
    for d in dependencies:
        target=d.get('target_repo');pinned=re.match(r'^\s*==\s*([\w.+\-]+)',d.get('constraint',''))
        if target and pinned and norm(d['package']) in packages and pinned.group(1)!=packages[norm(d['package'])][1]:
            d['status']='VERSION_A_EXAMINER'
            d['detail']=f"Pin {pinned.group(1)}; source {packages[norm(d['package'])][1]} (versions de dépôts, non du paquet installé)"
    for x in import_edges:
        _add_relation(rows,x['source'],x['target'],'','Import inter-repo', 'observed_static',x['evidence']['file'])
    for w in workflows:
        _add_relation(rows,w['source'],w['target'],'','Workflow GitHub', 'observed_static',w['evidence']['file'])
    for env in env_edges:
        _add_relation(rows,env['source'],env['target'],'','Référence de configuration', 'observed_static',env['evidence']['file'])
    for requirement in boundary_expectations:
        _add_relation(rows,requirement['source'],requirement['target'],'',
            'Obligation configurée','declared',requirement['id'])
    known_repo_names = {entry['name'] for entry in repo_map.values()}
    # HTTP requests: link to target ONLY with unambiguous explicit port or service alias.
    api_calls=[]
    ports=cfg.get('service_endpoints',{})
    ports={repo: urls for repo, urls in ports.items() if repo in known_repo_names} if isinstance(ports, dict) else {}
    routes_by_repo={name:{(r['method'],r['path']) for r in s['routes']} for name,s in sources.items()}
    for owner,s in sources.items():
        for call in s['calls']:
            check()
            target,how=_target_for_url(call,ports,alias)
            if how == 'hote_nominal':
                how, target = 'indice_hote_nominal', ''
            if target == owner:
                how, target = 'appel_local', ''
            hit=(call['method'],call['path']) in routes_by_repo.get(target,set())
            status='ROUTE_CORRESPONDANTE' if hit else ('CIBLE_IDENTIFIEE' if target else 'CIBLE_INCONNUE')
            d={'source':owner,'target':target,'method':call['method'],'endpoint':call['url'],
               'path':call['path'],'status':status,'mapping':how,'evidence':call['evidence']}
            api_calls.append(d)
            if target and target!=owner:
                _add_relation(rows,owner,target,'','Appel HTTP détecté','observed_static',call['evidence']['file'])
    # Event pub/sub matching EXACT channel strings, no semantic inference.
    channels=collections.defaultdict(lambda:{'publish':[],'subscribe':[]})
    for owner,s in sources.items():
        for direction,key in (('publish','events_pub'),('subscribe','events_sub')):
            for item in s[key]:
                channel= item['value']
                channels[channel][direction].append({'repo':owner,'evidence':item['evidence']})
    events=[]
    for channel,parts in sorted(channels.items()):
        seen_pairs=set()
        for publisher in parts['publish']:
            for subscriber in parts['subscribe']:
                if publisher['repo']==subscriber['repo']:continue
                pair=(publisher['repo'],subscriber['repo'])
                if pair in seen_pairs:continue
                seen_pairs.add(pair)
                events.append({'channel':channel,'source':pair[0],'target':pair[1],
                    'status':'NOM_COMMUN_STATIQUE','publisher_evidence':publisher['evidence'],
                    'subscriber_evidence':subscriber['evidence']})
                _add_relation(rows,pair[0],pair[1],f'event:{channel}','Événement statique','observed_static',publisher['evidence']['file'])
        if not seen_pairs and (parts['publish'] or parts['subscribe']):
            events.append({'channel':channel,'source':', '.join(sorted(set(x['repo'] for x in parts['publish']))),
                 'target':', '.join(sorted(set(x['repo'] for x in parts['subscribe']))),
                 'status':'UNILATERAL_OU_LOCAL','publisher_evidence':parts['publish'][0]['evidence'] if parts['publish'] else {},
                 'subscriber_evidence':parts['subscribe'][0]['evidence'] if parts['subscribe'] else {}})
    # Local schema references and same canonical $id consistency.
    schemas=[];canonical=collections.defaultdict(list)
    for owner,s in sources.items():
        basepath=next((x['path'] for x in repo_map.values() if x['name']==owner),None)
        for row in s['schemas']:
            x=dict(row)
            missing=[]
            for ref in row['refs']:
                source_schema=basepath/row['file']
                candidate=(source_schema.parent/ref).resolve()
                if not candidate.is_relative_to(basepath.resolve()) or not candidate.is_file():
                    missing.append(ref)
            x['missing_refs']=missing
            x['status']='REF_ABSENTE' if missing else 'LISIBLE'
            if x['id']:canonical[(x['id'],x['version'])].append(x)
            schemas.append(x)
    for group in canonical.values():
        # Identical $id with distinct digests can arise from historical locks,
        # copies and vendored references. It is an *ambiguity* until an explicit
        # producer/consumer version lock asserts that two copies must match.
        if len({x['repo'] for x in group})>1 and len({x['digest'] for x in group})>1:
            digest_count=len({x['digest'] for x in group})
            for x in group:
                if x['status']=='LISIBLE':
                    x['status']='SCHEMA_ID_MULTIPLE_DIGESTS_REVIEW'
                    x['variants']=digest_count
    # Generic exchanged proofs only with matching sender + receiver evidence.
    known_names = {entry['name'] for entry in repo_map.values()}
    linux_root = next((entry['path'] for entry in repo_map.values()
                       if norm(entry['name']) == 'koalinuxkoali' and entry['path'].is_dir()), None)
    from .revisions import resolve_revisions
    policy = cfg.get('evidence_policy', {})
    policy = dict(policy) if isinstance(policy, dict) else {}
    revisions, revision_findings = resolve_revisions(repo_map, policy.get('reference_revisions'))
    policy['reference_revisions'] = revisions
    exchanges, exchange_sources = _load_exchanges(
        root, cfg.get('exchange_trace_files', []), known_names, stop,
        linux_root=linux_root, policy=policy)
    complementary = collections.defaultdict(list)
    for finding in exchange_sources:
        for ident in finding.pop('correlation_hashes', []):
            complementary[ident].append({
                'source': finding['source'], 'format': finding['format'], 'sha256': finding['sha256']})
    for exchange in exchanges:
        exchange['complementary_observations'] = complementary.get(exchange['hash'], [])[:25]
    native_profiles = base.get('profile_validation', {})
    for exchange in exchanges:
        profile = native_profiles.get(exchange['contract'])
        if profile is not None:
            exchange['contract_status'] = (
                'VALIDE' if profile['status'] == 'VALIDE'
                and norm(exchange['source']) in {norm(x) for x in profile['sources']}
                and norm(exchange['target']) in {norm(x) for x in profile['targets']}
                else 'ECART')
    # Quality dimensions per relation. Missing optional evidence is NOT a failure.
    present={entry['name']:entry['path'].is_dir() for entry in repo_map.values()}
    for r in rows.values():
        check()
        src=r['source'];tgt=r['target'];src_ok=present.get(src);tgt_ok=present.get(tgt)
        r['source_repo']=src if src in present else ''
        r['target_repo']=tgt if tgt in present else ''
        rel_deps=[x for x in dependencies if x['repo']==src and x.get('target_repo')==tgt]
        rel_imports=[x for x in import_edges if x['source']==src and x['target']==tgt]
        rel_workflows=[x for x in workflows if x['source']==src and x['target']==tgt]
        rel_env=[x for x in env_edges if x['source']==src and x['target']==tgt]
        rel_expect=[x for x in boundary_expectations if x['source']==src and x['target']==tgt]
        rel_calls=[x for x in api_calls if x['source']==src and x['target']==tgt]
        rel_events=[x for x in events if x['source']==src and x['target']==tgt]
        rel_probes=[x for x in base['api'] if norm(x.get('source')) in (norm(src),) and norm(x.get('target'))==norm(tgt)]
        rel_ik=[x for x in base['traces'] if norm(x.get('source')) in (norm(src),norm(r.get('source','')))
                and norm(x.get('target')) in (norm(tgt),norm(r.get('target','')))
                and (not r['contract'] or x.get('contract')==r['contract'])]
        rel_exchange=[x for x in exchanges if norm(x['source'])==norm(src) and norm(x['target'])==norm(tgt) and x['contract']==r['contract']]
        d={
          'topologie':'PRESENTS' if src_ok and tgt_ok else ('ABSENTS' if src_ok is False or tgt_ok is False else 'NON_LOCALISE'),
          'contrat': 'IK_ALIGNE' if r.get('ik_status')=='CONTRAT_ALIGNE' else ('ECART' if r.get('ik_status')=='ECART' else ('DECLARATION' if r['contract'] else 'NON_SPECIFIE')),
          'integration_code': 'REFERENCES_IK_BILATERALES' if r.get('ik_refs_src') and r.get('ik_refs_dst') else ('APPELS_ROUTES' if any(x['status']=='ROUTE_CORRESPONDANTE' for x in rel_calls) else ('UNILATERAL_OU_INCONNU')),
          'dependances': 'DECLAREES' if rel_deps else 'NON_DECLAREES',
          'imports': 'IMPORT_DECLARÉ' if rel_imports else 'NON_OBSERVE',
          'workflows': 'REF_EXTERNES_DECLARÉES' if rel_workflows else 'NON_OBSERVE',
          'config_variables': 'INDICES_ENV' if rel_env else 'NON_OBSERVE',
          'obligations': 'ECART' if any(x['status']=='EXIGENCE_MANQUANTE' for x in rel_expect)
              else ('DECLARATIONS_PRESENTES' if rel_expect else 'NON_CONFIGURE'),
          'api_statique': 'ROUTE_CORRESPONDANTE' if any(x['status']=='ROUTE_CORRESPONDANTE' for x in rel_calls) else ('CIBLE_IDENTIFIEE' if rel_calls else 'NON_OBSERVE'),
          'evenements': 'NOM_COMMUN_STATIQUE' if rel_events else 'NON_OBSERVE',
          'api_sonde': 'API_REPOND' if any(x['status']=='API_REPOND' for x in rel_probes) else ('ECART' if any(x['status'] in ('ECART','INACCESSIBLE') for x in rel_probes) else 'NON_TESTE'),
          'ik_receipts': 'RECU_SUCCES' if any(x['status']=='RECU_SUCCES' for x in rel_ik) else 'NON_OBSERVE',
          'echange_passif': 'PAIRE_OBSERVEE' if any(x['status']=='PAIRE_OBSERVEE' for x in rel_exchange) else 'NON_OBSERVE',
        }
        r['dimensions']=d
        r['preuves']={'declared_dependencies':len(rel_deps),'static_http_calls':len(rel_calls),
            'event_channels':len(rel_events),'static_imports':len(rel_imports),
            'workflow_refs':len(rel_workflows),
            'env_link_hints':len(rel_env),'declared_expectations':len(rel_expect),
            'configured_api_probes':len(rel_probes),
            'passive_pairs':sum(x['status']=='PAIRE_OBSERVEE' for x in rel_exchange),
            'ik_receipts':sum(x['status']=='RECU_SUCCES' for x in rel_ik)}
        if d['topologie']=='ABSENTS':r['qualification']='REPO_ABSENT'
        elif d['contrat']=='ECART' or d['api_sonde']=='ECART' or d['obligations']=='ECART':r['qualification']='ECART'
        elif d['echange_passif']=='PAIRE_OBSERVEE' :r['qualification']='ECHANGE_CORRELE'
        elif d['contrat']=='IK_ALIGNE' or d['integration_code']=='APPELS_ROUTES':r['qualification']='CONTRAT_OU_ROUTE'
        elif rel_calls or rel_deps or rel_imports or rel_events or rel_workflows or rel_env:r['qualification']='INDICES_STATIQUES'
        elif r['maturity'] in ('blocked','candidate','proposed','receiver_pending','integrated_pending'):r['qualification']='CANDIDAT_OU_BLOQUE'
        else:r['qualification']='DOCUMENTE'
        r['detail']='Une concordance statique, une sonde GET/HEAD ou une trace exportée ne certifie pas la transaction métier E2E.'
    relations=sorted(rows.values(),key=lambda x:(x['source'].casefold(),x['target'].casefold(),x['contract']))
    for ix,r in enumerate(relations,1):r['id']=f'R{ix:03d}'
    repo_coverage=[]
    for repo in sorted(repo_map.values(),key=lambda x:x['name'].lower()):
        name=repo['name']
        related=[r for r in relations if r['source']==name or r['target']==name]
        src=sources.get(name,{})
        repo_coverage.append({'repo':name,'exists':repo['path'].is_dir(),
          'relative_path':repo['relative'],'incoming':sum(r['target']==name for r in related),
          'outgoing':sum(r['source']==name for r in related),
          'linked':len(related),'scanned_files':src.get('files_scanned',0),
          'truncated':name in deferred or src.get('scan_limit_reached',False),
          'traversal_limited':name in deferred or src.get('traversal_limited',False),
          'eligible_files':src.get('files_eligible',0),
          'oversized_files':src.get('files_oversized',0),
          'unreadable_files':src.get('files_unreadable',0),
          'unselected_files':src.get('files_unselected',0),
          'index_overflow_files':src.get('files_index_overflow',0),
          'boundary_scan_gaps':src.get('boundary_scan_gaps',[]),
          'boundary_scan_gap_count':src.get('boundary_scan_gap_count',0),
          'unselected_by_root':src.get('unselected_by_root',[]),
          'oversized_by_root':src.get('oversized_by_root',[]),
          'qualification': 'ABSENT' if not repo['path'].is_dir() else ('NON_CARTOGRAPHIE' if not related else 'CARTOGRAPHIE')})
    schema_issues=sum(x['status'] not in ('LISIBLE',) for x in schemas)
    dep_issues=sum(x['status']=='VERSION_A_EXAMINER' for x in dependencies)
    scan_warnings=sum(x['truncated'] for x in repo_coverage)
    statuses=dict(collections.Counter(x['qualification'] for x in relations))
    from .api_links import check_links
    # Expose observed inbound API routes only, without scanning application
    # internals or calling them. This makes consumer/producer boundary contracts
    # inspectable even when the call's base URL comes from a dynamic config.
    api_routes=[r for s in sources.values() for r in s['routes']]
    expected_api_links=check_links(cfg.get('expected_api_links',[]),api_calls,api_routes)
    from .journeys import evaluate_journeys
    journeys=evaluate_journeys(cfg.get('journeys',[]),exchanges,relations,policy)
    from .journeys import SHELL_REPOS
    shell_dependencies = [
        {'source': r['source'], 'target': r['target'], 'indicators': [
            name for name, count in r['preuves'].items() if count and name in
            ('declared_dependencies', 'static_http_calls', 'event_channels', 'static_imports',
             'workflow_refs', 'env_link_hints')]}
        for r in relations if r['target'] in SHELL_REPOS]
    return {'format':'koa.interrepo-kernel.report/1','version':VERSION,
      'timestamp':datetime.now(timezone.utc).isoformat(), 'root':str(root),
      'elapsed_seconds':round(time.monotonic()-started,2),
      'reference_sources':base['reference_sources'],
      'security':{'read_only_repos':True,'internal_app_tests_run':False,'subprocesses_run':False,
                  'api_probes_opt_in':bool(allow_network),'remote_opt_in':bool(allow_remote),
                  'payloads_in_report':False},
      'summary':{'inventory_repos':len(repo_map),'present_repos':len(sources)+len(deferred),
       'source_repos_sampled':len(sources),'source_repos_deferred':len(deferred),
       'source_repo_traversals_limited':sum(x['traversal_limited'] for x in repo_coverage),
       'relations':len(relations),'qualifications':statuses,
       'api_static_calls':len(api_calls),'api_route_matches':sum(x['status']=='ROUTE_CORRESPONDANTE' for x in api_calls),
       'api_inbound_routes':len(api_routes),'expected_api_links':len(expected_api_links),
       'expected_api_links_matched':sum(x['status']=='APPEL_ET_ROUTE_STATIQUES' for x in expected_api_links),
       'api_live_ok':sum(x['status']=='API_REPOND' for x in base['api']),
       'api_live_probes':len(base['api']),
       'events':len(events),'cross_repo_events':sum(x['status']=='NOM_COMMUN_STATIQUE' for x in events),
       'declared_dependencies':sum(bool(x.get('target_repo')) for x in dependencies),
       'workflow_cross_repo':len(workflows), 'imports_cross_repo':len(import_edges),
       'env_boundary_hints':len(env_edges),
       'boundary_expectations':len(boundary_expectations),
       'boundary_expectations_missing':sum(x['status']=='EXIGENCE_MANQUANTE' for x in boundary_expectations),
       'dependency_versions_to_review':dep_issues,'schemas':len(schemas), 'schema_issues':schema_issues,
       'active_ik_profiles':base['summary']['active_ik_profiles'],'ik_contract_issues':base['summary']['contract_issues'],
       'exchanges_correlated':sum(x['status']=='PAIRE_OBSERVEE' for x in exchanges),
       'ik_receipts_success':sum(x['status']=='RECU_SUCCES' for x in base['traces']),
       'repositories_scan_truncated':scan_warnings,
       'source_files_eligible':sum(x.get('files_eligible',0) for x in sources.values()),
       'source_files_scanned':sum(x.get('files_scanned',0) for x in sources.values()),
       'source_files_unselected':sum(x.get('files_unselected',0) for x in sources.values()),
       'source_files_oversized':sum(x.get('files_oversized',0) for x in sources.values()),
       'source_files_unreadable':sum(x.get('files_unreadable',0) for x in sources.values()),
       'source_repositories_empty':sum(x.get('files_eligible',0)==0 for x in sources.values()),
       'journeys_configured':len(journeys),
       'journeys_evidence_complete':sum(j['status']=='EVIDENCE_COMPLETE' for j in journeys),
       'fully_certified_e2e':0},
      'journeys':journeys,'reference_revisions':revision_findings,
      'koali':{'declared_mode':policy.get('mode', 'non_renseigne'),
               'shell_repos':sorted(SHELL_REPOS),
               'dependency_indicators':[r for r in shell_dependencies if r['indicators']],
               'koali_summaries':sum(r.get('status') == 'LU' and r.get('format') == 'koali-summary'
                                     for r in exchange_sources)},
      'relations':relations,'repositories':repo_coverage,'api_calls':api_calls,
      'api_routes':api_routes,'expected_api_links':expected_api_links,
      'api_probes':base['api'],'events':events,'dependencies':dependencies,
      'schemas':schemas,'imports':import_edges,'workflows':workflows,'env_edges':env_edges,
      'boundary_expectations':boundary_expectations,
      'exchanges':exchanges,'exchange_sources':exchange_sources,
      'ik_profile_validation':native_profiles,'ik_contracts':base['contracts'],'ik_paths':base['paths'],'ik_receipts':base['traces'],'ik_trace_sources':base['trace_sources'],
      'scan_issues':[x for s in sources.values() for x in s['issues']],
      'surface_counts':_code_bridge_summary(sources,dependencies,api_calls,events)}


def export(report, destination):
    dest=Path(destination);dest.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
    prefix='InterRepo-Kernel_'+stamp
    files={}
    json_path=dest/(prefix+'.json');ik.save_json(json_path,report);files['json']=str(json_path)
    specs={
     'relations':('relations',['id','source','target','contract','maturity','qualification','detail']),
     'repos':('repositories',['repo','exists','incoming','outgoing','linked','qualification','truncated']),
     'api':('api_calls',['source','target','method','path','endpoint','status','mapping']),
     'sondes':('api_probes',['id','source','target','endpoint','status','http_status','detail']),
     'events':('events',['channel','source','target','status']),
     'dependencies':('dependencies',['repo','package','target_repo','constraint','kind','status','detail']),
     'imports':('imports',['source','target','module','status']),
     'workflows':('workflows',['source','target','reference','revision','status']),
     'env_edges':('env_edges',['source','target','variable','status']),
     'expectations':('boundary_expectations',['id','source','target','status','detail']),
     'schemas':('schemas',['repo','file','id','version','status']),
     'exchanges':('exchanges',['hash','source','target','kind','status','detail']),
     'contracts':('ik_contracts',['name','status','detail']),
     'paths':('ik_paths',['id','title','status','sequence'])}
    for label,(section,columns) in specs.items():
        output=dest/(prefix+'_'+label+'.csv')
        with output.open('w',encoding='utf-8-sig',newline='') as fh:
            writer=csv.DictWriter(fh,fieldnames=columns,delimiter=';',extrasaction='ignore')
            writer.writeheader();writer.writerows(report[section])
        files[label]=str(output)
    output=dest/(prefix+'.txt')
    with output.open('w',encoding='utf-8') as fh:
        fh.write('kOA / Interaction Kernel — couverture des relations inter-repos\n')
        fh.write(f"Date UTC: {report['timestamp']}\nRacine: {report['root']}\n\n")
        for key,value in report['summary'].items():fh.write(f'{key}: {value}\n')
        fh.write('\nRAPPEL: contrat, lecture API, et traces corrélées sont des niveaux de preuve distincts.\n')
        fh.write('Aucune certification fonctionnelle ou E2E globale.\n')
    files['txt']=str(output)
    return files
