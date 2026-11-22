# -*- coding: utf-8 -*-
"""Inter-repo diagnostic levels. Never launches target applications or test suites."""
from __future__ import annotations
import hashlib
import csv
from pathlib import Path
from ..framework import read_json, write_json
from .. import interrepo_core
from .. import ik_diag_core as ik
from .. import boundary_registry as registry
from ..qualification import matrix as boundary_matrix, summary as boundary_summary, export_csv as boundary_csv
from ..inventory_alignment import compare as compare_inventories
from ..documentary_scope import reconcile

MAX_FINDINGS=90


def _emit(report,identifier,severity,category,message,evidence=None,recommendation=None):
    if len(report.findings)<MAX_FINDINGS:
        report.add(identifier,severity,category,message,evidence=evidence,recommendation=recommendation)
    elif len(report.findings)==MAX_FINDINGS:
        report.add(category+'.results.truncated','WARN',category,
          'Le rapport de niveau a atteint sa limite de constats; consulter le snapshot intégral.')


def _snapshot(cfg,ctx):
    p=Path(ctx['run_root'])/'levels'/'N01'/'snapshot.json'
    if not p.is_file():raise FileNotFoundError('Snapshot N01 absent : '+str(p))
    return read_json(p)


def _reference(cfg,relative):
    root=Path(cfg['_tool'])/'koa_ecosystem_diag'/'references'
    path=(root/relative).resolve()
    if not path.is_relative_to(root.resolve()):raise ValueError('Référence hors racine')
    return path


def n00(cfg,report,ctx):
    """Inspect manifests/reference integrity and boundary safety, not individual apps."""
    for name in ('repositories.json','graph-registry.v1.json','graph-focus.v1.json'):
        path=_reference(cfg,name)
        if not path.is_file():
            _emit(report,'references.'+name+'.missing','FAIL','references','Référence absente: '+name)
            continue
        body=read_json(path)
        sha=hashlib.sha256(path.read_bytes()).hexdigest()
        report.metrics[name+'_sha256']=sha
        _emit(report,'references.'+name+'.readable','PASS','references',name+' lisible',{'sha256':sha,'type':type(body).__name__})
    inv=read_json(_reference(cfg,'repositories.json'))
    repos=inv if isinstance(inv,list) else inv.get('repositories',[])
    if not isinstance(repos,list) or not repos:
        _emit(report,'inventory.empty','FAIL','references','Inventaire des dépôts vide/invalide')
    else:
        report.metrics['inventory_declared']=len(repos)
        _emit(report,'inventory.count','PASS','references',f'{len(repos)} dépôts dans le registre')
    root=Path(cfg['_root'])
    if not root.is_dir():_emit(report,'target.root.missing','BLOCKED','configuration','Racine introuvable')
    if cfg['interrepo'].get('relations') and not isinstance(cfg['interrepo']['relations'],list):
        _emit(report,'configuration.relations.invalid','CONFIG_ERROR','configuration','relations doit être une liste')
    try:
        local = registry.read(Path(cfg['_tool']))
        report.metrics['registry_rows']=len(local['relations'])
    except (ValueError, OSError, TypeError) as exc:
        _emit(report,'registry.invalid','CONFIG_ERROR','configuration',f'Registre inter-repos invalide : {exc}')
    try:
        audit = ctx.get('runtime_audit')
        alignment=compare_inventories(Path(cfg['_tool']), Path(audit) if audit else None)
        report.metrics['audit_inventory_diag_count']=alignment['diag_count']
        report.metrics['audit_inventory_reference_count']=alignment['audit_count']
        report.metrics['audit_inventory_unmatched']=len(alignment['diag_only'])+len(alignment['audit_only'])
        if not alignment['aligned']:
            _emit(report,'inventory.audit.reference.difference','WARN','references',
                'Écart entre l’inventaire de référence Audit et la liste Diagnostic : revue nécessaire',
                {'diag_only':alignment['diag_only'],'audit_only':alignment['audit_only'],
                 'source':alignment['source']})
    except (ValueError,OSError,TypeError,KeyError) as exc:
        _emit(report,'inventory.audit.reference.unavailable','WARN','references',f'Rapprochement Audit indisponible : {exc}')
    _emit(report,'security.no-target-commands','PASS','security',
      'Les niveaux de collecte et d’analyse lisent les dépôts. Le kit métier N14 est explicite et réservé à une pile d’essai.')


def n01(cfg,report,ctx):
    """Shared evidence harvest, with network strictly OFF (other levels read the snapshot)."""
    root=Path(cfg['_root'])
    # Only explicit human-approved HTTP boundaries become declared expectations.
    # Rejected/deferred/unreviewed edges never become runtime requirements.
    try:
        reviewed = registry.read(Path(cfg['_tool']))
    except (OSError, ValueError, TypeError):
        if not ctx.get('integral'):
            raise
        reviewed = registry.empty()
        _emit(report,'collection.registry.invalid','PARTIAL','scope',
              'Registre local inexploitable. Collecte poursuivie sans décisions locales.')
    interrepo=dict(cfg['interrepo'])
    from ..audit_bridge import merge_descriptors
    run_root = Path(ctx['run_root'])
    trace_inputs = interrepo.get('exchange_trace_files', [])
    for source in (run_root/'archived-evidence.json',
                   run_root/'levels'/'N14'/'evidence-descriptors.json'):
        if source.is_file():
            trace_inputs = merge_descriptors(trace_inputs, read_json(source))
    interrepo['exchange_trace_files'] = trace_inputs
    if ctx.get('integral'):
        scan = dict(interrepo.get('scan', {}))
        scan['max_files_per_repo'] = 60000
        scan['max_file_bytes'] = 1000000
        interrepo['scan'] = scan
        interrepo['integral_scan'] = True
    api_declarations=list(interrepo.get('expected_api_links',[]))
    for row in reviewed['relations']:
        if row['review_status']=='APPROVED' and row.get('protocol')=='HTTP' and row.get('method') and row.get('route'):
            api_declarations.append({'id':'registry-'+row['boundary_key'],
                'source':row['source_repo'],'target':row['target_repo'],
                'method':row['method'],'path':row['route'],'required':row['required'] is True})
    interrepo['expected_api_links']=api_declarations
    raw=interrepo_core.run(root,Path(cfg['_tool'])/'koa_ecosystem_diag'/'references',
       interrepo,allow_network=False,allow_remote=False)
    p=Path(ctx['run_root'])/'levels'/'N01'/'snapshot.json'
    # Reconcile only discovered boundaries. Never auto-approve user decisions.
    review, newly_discovered = registry.synchronize(Path(cfg['_tool']),raw.get('relations',[]),persist=False,initial=reviewed)
    review_status=registry.metrics(review)
    registry_copy=Path(ctx['run_root'])/'registry-snapshot.json'
    write_json(registry_copy,review)
    scope = reconcile(Path(cfg['_tool']), root, review, raw)
    raw['documentary_scope'] = scope
    write_json(p,raw)
    scope_file = Path(ctx['run_root']) / 'documentary-scope.json'
    write_json(scope_file, scope)
    report.artifact('documentary-scope', scope_file, 'Sources /docs et périmètre obligatoire')
    if not scope['aligned']:
        _emit(report,'scope.documentary.review','WARN','scope','Sources ou décisions du plan documentaire à rapprocher')
    boundary_rows=boundary_matrix(review,raw,interrepo.get('evidence_policy'))
    matrix_summary=boundary_summary(boundary_rows,scope)
    if matrix_summary['required_without_journey'] or matrix_summary['required_missing_repos'] or matrix_summary['required_not_mapped']:
        _emit(report,'scope.required.gaps','PARTIAL','scope',
              'Frontières obligatoires hors parcours ou dépôts manquants',matrix_summary)
    boundary_report=Path(ctx['run_root'])/'boundary-qualification.json'
    write_json(boundary_report,{'schema':'koa.boundary-evidence.v1',
        'rows':boundary_rows,'summary':matrix_summary})
    boundary_csv(boundary_rows,Path(ctx['run_root'])/'exports'/'matrice-preuves-frontieres.csv')
    report.artifact('boundary-evidence',boundary_report,'Qualification observée séparée de la décision humaine')
    registry.export_csv(review,Path(ctx['run_root'])/'exports'/'registre-frontieres.csv')
    report.metrics['registry_new']=newly_discovered
    report.metrics['registry_unreviewed']=review_status['new_or_unreviewed']
    report.artifact('registry',registry_copy,'Décisions humaines conservées indépendamment des observations')
    report.artifact('snapshot',p,'Preuves et relations extraites en lecture seule')
    # Bounded CSV exports per boundary domain; all paths remain within this run.
    export_specs={
      'relations':('relations',['id','source','target','contract','maturity','qualification']),
      'appels-api':('api_calls',['source','target','method','path','status','mapping']),
      'routes-api':('api_routes',['repo','method','path']),
      'frontieres-api':('expected_api_links',['id','source','target','method','path','status','required']),
      'evenements':('events',['channel','source','target','status']),
      'dependances':('dependencies',['repo','package','target_repo','constraint','kind','status']),
      'ci-workflows':('workflows',['source','target','reference','revision','status']),
      'echanges':('exchanges',['hash','source','target','kind','status']),
      'profils-ik':('ik_contracts',['name','status','detail']),
      'schemas':('schemas',['repo','file','id','version','status']),
      'parcours-e2e':('journeys',['id','status','verified_hops','required','reason'])}
    export_dir=Path(ctx['run_root'])/'exports';export_dir.mkdir(parents=True,exist_ok=True)
    for label,(key,columns) in export_specs.items():
        target=export_dir/(label+'.csv')
        with target.open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=columns,delimiter=';',extrasaction='ignore')
            writer.writeheader();writer.writerows(raw.get(key,[]))
        report.artifact('csv',target,'Vue '+label+' des frontières inter-repos')
    summary=raw['summary']
    report.metrics.update({k:v for k,v in summary.items() if isinstance(v,(int,float,bool))})
    present=summary['present_repos'];total=summary['inventory_repos']
    if not present:
        _emit(report,'collection.no-repositories','BLOCKED','inventory','Aucun dépôt accessible dans le registre', {'present':present,'total':total})
    elif present<total:
        _emit(report,'collection.partial','PARTIAL','inventory',f'Collecte sur {present}/{total} dépôts (couverture partielle)',
           {'present':present,'total':total},'Confirmer les dépôts réellement installés avant de conclure.')
    else:
        _emit(report,'collection.inventory.complete','PASS','inventory',f'Collecte sur {present}/{total} dépôts')
    if summary['repositories_scan_truncated']:
        _emit(report,'collection.scan.truncated','PARTIAL','inventory',
          f"Scan limité dans {summary['repositories_scan_truncated']} dépôt(s) : {summary.get('source_files_unselected',0)} fichiers éligibles non sélectionnés",
          recommendation='Consulter scan-gaps.json, puis ajuster précisément la portée avant d’augmenter le plafond.')
    if summary.get('source_files_oversized') or summary.get('source_files_unreadable'):
        _emit(report,'collection.files.unreadable','PARTIAL','inventory',
              f"Collecte incomplète : {summary.get('source_files_oversized',0)} fichiers trop volumineux, {summary.get('source_files_unreadable',0)} illisibles")
    if summary.get('source_repositories_empty'):
        _emit(report,'collection.empty_surfaces','WARN','inventory',
              f"{summary['source_repositories_empty']} dépôt(s) sans fichiers de code/configuration dans les surfaces analysées")
    if raw.get('scan_issues'):
        _emit(report,'collection.scan.issues','WARN','inventory',
          f"{len(raw['scan_issues'])} fichier(s) source n’ont pu être examinés", {'sample':raw['scan_issues'][:4]})


def n02(cfg,report,ctx):
    x=_snapshot(cfg,ctx)
    absent=[r for r in x['repositories'] if not r['exists']]
    report.metrics.update(declared=len(x['repositories']),present=len(x['repositories'])-len(absent),relations=len(x['relations']))
    if absent:_emit(report,'topology.repositories.absent','WARN','topology',
        f'{len(absent)} dépôt(s) absent(s) selon inventaire',{'sample':[r['repo'] for r in absent[:15]]})
    for row in x['relations']:
        if row['qualification']=='ECART':
            _emit(report,'topology.relation.'+row['id']+'.drift','WARN','topology',
              f"{row['source']} → {row['target']}: relation en écart", {'dimensions':row.get('dimensions',{})})
        elif row['qualification']=='REPO_ABSENT':
            _emit(report,'topology.relation.'+row['id']+'.missing','WARN','topology',
              f"{row['source']} → {row['target']}: dépôt manquant")
    if not x['relations']:_emit(report,'topology.relations.empty','PARTIAL','topology','Aucune liaison cartographiée')
    else:_emit(report,'topology.map.readable','PASS','topology',f"{len(x['relations'])} liaisons inventoriées")
    registry_path=Path(ctx['run_root'])/'registry-snapshot.json'
    if registry_path.is_file():
        review=registry.metrics(read_json(registry_path))
        report.metrics.update({('registry_'+k): v for k,v in review.items() if isinstance(v,(bool,int))})
        if review['new_or_unreviewed'] or review['deferred']:
            _emit(report,'topology.registry.pending','PARTIAL','governance',
                f"Registre : {review['new_or_unreviewed']} frontières non revues et {review['deferred']} reportées",
                {'required_confirmed':review['required'],'approved_optional':review['optional']},
                'Qualifier les frontières dans l’onglet Registre des frontières avant de certifier un périmètre.')
        if review['not_seen']:
            _emit(report,'topology.registry.not_observed','WARN','governance',
                f"{review['not_seen']} frontières historiques non observées cette campagne; décisions conservées.")
    else:
        _emit(report,'topology.registry.unavailable','PARTIAL','governance','Registre de revue non disponible')


def n03(cfg,report,ctx):
    x=_snapshot(cfg,ctx)
    contracts=x['ik_contracts'];schemas=x['schemas'];present={r['repo'] for r in x['repositories'] if r['exists']}
    ik_present=any('interaction' in r.casefold() and 'kernel' in r.casefold() for r in present)
    bad=0
    for row in contracts:
        status=row.get('status')
        if status in ('ECART','ABSENT'):
            bad+=1
            sev='FAIL' if status=='ECART' and ik_present else 'WARN'
            _emit(report,'contracts.ik.'+str(bad),sev,'contract',
                str(row.get('name','Contrat'))+': '+str(row.get('detail',''))[:220],row.get('evidence'))
    schema_review=0
    for row in schemas:
        if row['status']=='REF_ABSENTE':
            bad+=1
            _emit(report,'contracts.schema.'+str(bad),'WARN','schema',
              f"{row['repo']} — {row['file']}: référence locale introuvable",
              {'id':row.get('id'),'missing_refs':row.get('missing_refs',[])},
              'Confirmer la résolution du $ref depuis le dépôt ou le paquet du contrat.')
        elif row['status'] in ('SCHEMA_ID_MULTIPLE_DIGESTS_REVIEW','DERIVE_SCHEMA_CANONIQUE'):
            schema_review+=1
            _emit(report,'contracts.schema.review.'+str(schema_review),'WARN','schema',
              f"{row['repo']} — {row['file']}: plusieurs empreintes partagent le même identifiant",
              {'id':row.get('id'),'digest':row.get('digest')},
              'Qualifier le propriétaire, la version et le lock attendu avant de parler d’incompatibilité.')
    report.metrics.update(ik_contracts=len(contracts),schemas=len(schemas),issues=bad,schema_review=schema_review)
    if not bad and not schema_review:_emit(report,'contracts.no-drift','PASS','contract','Aucune anomalie dans les contrats analysés')
    if not ik_present:_emit(report,'contracts.ik.repository.absent','WARN','contract','Propriétaire Interaction Kernel non localisé : preuves IK incomplètes')


def n04(cfg,report,ctx):
    x=_snapshot(cfg,ctx);calls=x['api_calls'];report.metrics.update(calls=len(calls),matches=sum(a['status']=='ROUTE_CORRESPONDANTE' for a in calls))
    unknown=[a for a in calls if a['status']!='ROUTE_CORRESPONDANTE']
    if not calls:_emit(report,'api.static.none','PARTIAL','api','Aucun appel HTTP statique inter-repos reconnu; appels dynamiques possibles')
    else:
        _emit(report,'api.static.observed','PASS','api',f"{len(calls)} appels sortants observés, {report.metrics['matches']} correspondances directes")
        for i,a in enumerate(unknown[:40],1):
            _emit(report,'api.static.unresolved.'+str(i),'WARN','api',
              f"{a['source']} → {a['target'] or '?'} : {a['method']} {a['path']} ({a['status']})",
               {'evidence':a['evidence'],'mapping':a.get('mapping')})
    declared=x.get('expected_api_links',[])
    report.metrics['declared_boundaries']=len(declared)
    report.metrics['declared_boundaries_matched']=sum(e['status']=='APPEL_ET_ROUTE_STATIQUES' for e in declared)
    for i,b in enumerate(declared,1):
        status=b['status'];sev='PASS' if status=='APPEL_ET_ROUTE_STATIQUES' else ('CONFIG_ERROR' if status=='CONFIG_INVALIDE' else 'WARN')
        _emit(report,'api.boundary.'+str(i),sev,'api',
            f"{b['source']} → {b['target']}: {b['method']} {b['path']} — {status}",
            {'source_evidence':b.get('source_evidence',[]),'target_evidence':b.get('target_evidence',[])},
            'Une absence d’indice statique ne prouve pas un échec runtime; vérifier l’appel dynamique ou déclarer les ports.')
    _emit(report,'api.runtime.not-proven','WARN','api','Concordance des routes ≠ appel réussi entre deux applications.')


def n05(cfg,report,ctx):
    x=_snapshot(cfg,ctx);events=x['events'];report.metrics.update(channels=len({e['channel'] for e in events}),edges=len(events))
    pairs=[e for e in events if e['status']=='NOM_COMMUN_STATIQUE']
    singles=[e for e in events if e['status']!='NOM_COMMUN_STATIQUE']
    if pairs:_emit(report,'events.channels.matched','PASS','event',f'{len(pairs)} correspondance(s) statique(s) publication / abonnement')
    regfile=Path(ctx['run_root'])/'registry-snapshot.json'
    if regfile.is_file():
        reviewed=read_json(regfile)
        approved=[r for r in reviewed.get('relations',[]) if r.get('review_status')=='APPROVED'
            and r.get('protocol')=='EVENT' and r.get('observed',False)]
        report.metrics['approved_event_boundaries']=len(approved)
        for i,r in enumerate(approved,1):
            channel=r.get('event_channel') or (r.get('contract','')[6:] if r.get('contract','').startswith('event:') else '')
            matched=any(e.get('source')==r['source_repo'] and e.get('target')==r['target_repo']
                and e.get('status')=='NOM_COMMUN_STATIQUE' and (not channel or e.get('channel')==channel) for e in events)
            _emit(report,'events.approved.'+str(i),'PASS' if matched else 'WARN','event',
                f"{r['source_repo']} → {r['target_repo']} : "+
                ('canal producteur/consommateur présent, livraison non prouvée' if matched
                else 'canal déclaré non apparié statiquement'),
                {'channel':channel,'required':r.get('required')})
    for i,e in enumerate(singles[:35],1):
        _emit(report,'events.unilateral.'+str(i),'WARN','event',
          f"Canal {e['channel']}: producteur / consommateur non appariés ({e['status']})")
    if not events:_emit(report,'events.none','PARTIAL','event','Aucun canal inter-repos détecté par analyse statique')
    _emit(report,'events.delivery.not-proven','WARN','event','Un nom de canal commun ne prouve pas la livraison d’un message.')


def n06(cfg,report,ctx):
    x=_snapshot(cfg,ctx);deps=[d for d in x['dependencies'] if d.get('target_repo')]
    report.metrics.update(dependencies=len(deps),version_drift=sum(d.get('status')=='VERSION_A_EXAMINER' for d in deps))
    if deps:_emit(report,'dependencies.declared','PASS','dependencies',f'{len(deps)} dépendances inter-repos déclarées')
    else:_emit(report,'dependencies.none','PARTIAL','dependencies','Aucune dépendance inter-repos reconnue dans les manifestes')
    for i,d in enumerate(deps,1):
        if d.get('status')=='VERSION_A_EXAMINER':
            _emit(report,'dependencies.version.'+str(i),'WARN','dependencies',
              f"{d['repo']} → {d['target_repo']} : {d.get('detail','Pin divergent')}")


def n07(cfg,report,ctx):
    x=_snapshot(cfg,ctx)
    for key in ('imports','workflows','env_edges'):
        report.metrics[key]=len(x[key])
    if any(x[k] for k in ('imports','workflows','env_edges')):
        _emit(report,'coupling.static.detected','PASS','coupling',
          f"{len(x['imports'])} imports, {len(x['workflows'])} workflows, {len(x['env_edges'])} références de configuration")
    else:_emit(report,'coupling.static.none','PARTIAL','coupling','Aucun couplage statique détecté sur ces surfaces')
    for i,w in enumerate(x['workflows'],1):
        if w['status']=='REF_MOBILE_A_EXAMINER':
            _emit(report,'coupling.workflow.mobile.'+str(i),'WARN','ci',
              f"{w['source']} → {w['target']} : référence CI mobile {w['revision']}",w['evidence'])


def n08(cfg,report,ctx):
    x=_snapshot(cfg,ctx)
    checks=x['boundary_expectations'];report.metrics['obligations']=len(checks)
    if not checks:_emit(report,'obligations.none','SKIP','obligation','Aucune obligation de frontière configurée : contrôle non applicable')
    for i,item in enumerate(checks,1):
        if item['status']=='EXIGENCE_MANQUANTE':
            _emit(report,'obligations.'+str(i)+'.missing','FAIL','obligation',
              f"{item['source']} → {item['target']}: {item['detail']}")
        else:_emit(report,'obligations.'+str(i)+'.present','PASS','obligation',
              f"{item['source']} → {item['target']}: obligation déclarée présente (sans preuve E2E)")


def n09(cfg,report,ctx):
    x=_snapshot(cfg,ctx)
    pairs=[e for e in x['exchanges'] if e['status']=='PAIRE_OBSERVEE']
    attested=[e for e in pairs if e.get('provenance_attested')]
    receipts=[e for e in x['ik_receipts'] if e['status']=='RECU_SUCCES']
    report.metrics.update(exported_exchanges=len(x['exchanges']),correlated=len(pairs),
                          attested=len(attested),ik_receipts=len(receipts),
                          source_errors=sum(e.get('status')=='ECART' for e in x.get('exchange_sources',[])))
    if attested:
        _emit(report,'traces.correlated','PASS','evidence',
          f'{len(pairs)} paires observées dont {len(attested)} avec provenance déclarée; {len(receipts)} reçu(s) IK')
    elif pairs:
        _emit(report,'traces.untrusted','PARTIAL','evidence',
          f'{len(pairs)} paire(s) observées mais sans provenance émetteur/récepteur attestée')
    else:_emit(report,'traces.no-correlation','PARTIAL','evidence',
       'Aucune paire émission / réception corrélée dans les exports configurés',
       recommendation='Configurer les exports des outils dédiés, sans lancer leurs tests depuis ce diagnostic.')
    complementary = [r for r in x.get('exchange_sources',[]) if r.get('status') == 'LU' and r.get('format') != 'exchange']
    report.metrics['complementary_sources'] = len(complementary)
    for i,issue in enumerate(x.get('exchange_sources',[]),1):
        if issue.get('status')=='ECART':
            _emit(report,'traces.export.invalid.'+str(i),'WARN','evidence',
                'Export de traces non exploitable: '+str(issue.get('detail',''))[:120],
                {'source':issue.get('source')})
    for i,e in enumerate(x['exchanges'],1):
        if e['status']!='PAIRE_OBSERVEE':
            _emit(report,'traces.unpaired.'+str(i),'WARN','evidence',
              f"{e['source']} → {e['target']}: {e['status']}")
    for i,revision in enumerate(x.get('reference_revisions', []),1):
        if revision['configuration_mismatch']:
            _emit(report,'traces.revision.'+str(i),'PARTIAL','evidence',
                  'Révision configurée incohérente: '+revision['repo'])
    for i,issue in enumerate(x.get('ik_trace_sources', []),1):
        if issue.get('status') == 'ECART':
            _emit(report,'traces.ik.import.'+str(i),'PARTIAL','evidence',issue['detail'])
    for i,e in enumerate(x['ik_receipts'],1):
        if e['status'] in ('ECART','ECHEC','REFUSE'):
            _emit(report,'traces.receipt.'+str(i),'FAIL','evidence',
               f"Réponse IK en écart ({e['status']})",{'source':e.get('source'),'target':e.get('target')})


def n10(cfg,report,ctx):
    """Opt-in only; no requests unless explicitly enabled by user and config."""
    probes=cfg['interrepo'].get('ik',{}).get('probes',[])
    if not isinstance(probes, list):
        _emit(report,'probes.configuration','CONFIG_ERROR','api','La liste des sondes est invalide')
        return
    enabled = []
    for i, probe in enumerate(probes):
        if not isinstance(probe, dict):
            _emit(report, f'probes.configuration.{i}', 'CONFIG_ERROR', 'api', 'Descripteur de sonde invalide')
        elif probe.get('enabled'):
            enabled.append(probe)
    report.metrics['enabled_probes']=len(enabled)
    if not enabled:
        _emit(report,'probes.none','SKIP','api','Aucune sonde activée (mode sûr par défaut).')
        return
    allow_network=bool(ctx.get('allow_network'))
    allow_remote=bool(ctx.get('allow_remote') and ctx.get('ack_remote'))
    if not allow_network:
        _emit(report,'probes.network.disabled','BLOCKED','api','Sondes configurées mais réseau non autorisé pour cette campagne')
        return
    opts={'timeout_seconds':3,'max_response_bytes':65536}
    path=Path(ctx['run_root'])/'levels'/'N10'/'probes.json'
    rows=[]
    for p in enabled:
        try:
            row=ik.probe_api(p,opts,allow_network,allow_remote)
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            row = {'source': str(p.get('source', '')), 'target': str(p.get('target', '')),
                   'status': 'CONFIG_INVALIDE', 'detail': 'Descripteur de sonde invalide',
                   'http_status': None, 'latency_ms': None}
        rows.append(row)
        status=row['status']
        verdict='PASS' if status=='API_REPOND' else ('BLOCKED' if status in ('REFUSE','NON_CONFIGURE') else 'FAIL')
        _emit(report,'probes.'+str(p.get('id','unnamed'))[:80],verdict,'api',
            f"{row['source']} → {row['target']} : {status} — {row['detail'][:180]}",
            {'status':status,'http_status':row['http_status'],'latency_ms':row['latency_ms']})
    write_json(path,rows);report.artifact('api-probes',path,'Réponses GET/HEAD configurées sans corps sensibles')
    report.metrics.update(responses_ok=sum(x['status']=='API_REPOND' for x in rows),responses_total=len(rows))
    _emit(report,'probes.not-e2e','WARN','api','Sonde de lecture réussie ≠ échange métier inter-repos certifié.')


def n11(cfg,report,ctx):
    x=_snapshot(cfg,ctx);relations=x['relations']
    quals={}
    for r in relations:quals[r['qualification']]=quals.get(r['qualification'],0)+1
    report.metrics['qualifications']=quals
    proven=sum(r['qualification']=='ECHANGE_CORRELE' for r in relations)
    _emit(report,'continuity.graph.available','PASS','continuity',f'{len(relations)} liaisons cartographiées, {proven} avec preuves corrélées')
    for row in relations:
        if row['qualification'] in ('ECART','REPO_ABSENT'):
            _emit(report,'continuity.'+row['id']+'.attention','WARN','continuity',
               f"{row['source']} → {row['target']} : {row['qualification']}")
    if proven==0:
        _emit(report,'continuity.runtime.unproven','PARTIAL','continuity',
             'Aucune continuité E2E attestée par paires de traces : la topologie reste en partie déclarative')
    else:
        _emit(report,'continuity.passive.evidence','PASS','continuity',
            'Les paires de traces exportées étayent certains échanges, pas la totalité de l’écosystème')
    _emit(report,'continuity.certification.limit','WARN','continuity',
       'Ce diagnostic ne certifie pas les parcours métier de bout en bout; voir les preuves de chaque liaison.')


def n12(cfg,report,ctx):
    x=_snapshot(cfg,ctx)
    journeys=x.get('journeys',[])
    modes = x.get('koali',{})
    report.metrics.update(koali_summary_exports=modes.get('koali_summaries',0),
                          koali_dependency_indicators=len(modes.get('dependency_indicators',[])),
                          autonomous_complete=sum(j['status']=='EVIDENCE_COMPLETE' and j.get('mode')=='autonome' for j in journeys),
                          integrated_complete=sum(j['status']=='EVIDENCE_COMPLETE' and j.get('mode')=='integre' for j in journeys))
    report.metrics.update(configured=len(journeys),
                          evidence_complete=sum(j['status']=='EVIDENCE_COMPLETE' for j in journeys),
                          incomplete=sum(j['status']!='EVIDENCE_COMPLETE' for j in journeys))
    if not journeys:
        _emit(report,'journeys.none','PARTIAL','e2e',
            'Aucun parcours E2E explicite configuré. Aucune certification A à Z possible.',
            recommendation='Déclarer interrepo.journeys et fournir des traces passives identifiées.')
        return
    for j in journeys:
        status=j['status'];id=str(j['id'])
        if status=='EVIDENCE_COMPLETE':
            _emit(report,'journey.'+id+'.evidence','PASS','e2e',
                  f"{id} ({j.get('mode','non_renseigne')}): transaction corroborée sur tous les sauts.",
                  evidence={'hops':j['hops'],'journey_hash':j.get('journey_hash')},
                  recommendation='Validation basée sur exports fournis, pas une attestation cryptographique du comportement métier.')
        else:
            _emit(report,'journey.'+id+'.incomplete','PARTIAL','e2e',
                f"{id}: {status}. {j.get('verified_hops',0)}/{len(j.get('hops',[]))} frontières corroborées.",
                evidence={'hops':j.get('hops',[])},
                recommendation='Exporter les émissions, réceptions ET réponses depuis les applications concernées.')
    _emit(report,'journeys.scope','WARN','e2e',
        'La preuve d’un parcours déclaré ne valide pas les autres parcours non configurés.')


def n13(cfg, report, ctx):
    from ..full_validation import assess, write_assessment

    root = Path(ctx['run_root'])
    tool = Path(cfg['_tool'])
    target = Path(cfg['_root'])
    snapshot_path = root / 'levels' / 'N01' / 'snapshot.json'
    registry_path = root / 'registry-snapshot.json'
    collected = snapshot_path.is_file() and registry_path.is_file()
    if collected:
        try:
            snapshot = read_json(snapshot_path)
            decisions = read_json(registry_path)
        except (OSError, ValueError, TypeError):
            collected = False
    if not collected:
        decisions = registry.empty()
        try:
            decisions = registry.read(tool)
        except (OSError, ValueError, TypeError):
            _emit(report,'full.registry','PARTIAL','scope','Registre local indisponible')
        try:
            references, _ = ik.read_reference_data(target, tool/'koa_ecosystem_diag'/'references')
            repositories = ik.inventory(references['repositories.json'], target)
        except (OSError, ValueError, TypeError, KeyError):
            repositories = {}
        snapshot = {'repositories': [{'repo': row['name'], 'exists': row['path'].is_dir()}
                                      for row in repositories.values()]}
        snapshot['documentary_scope'] = reconcile(tool, target, decisions, snapshot)
    interrepo = cfg['interrepo']
    policy = interrepo.get('evidence_policy', {})
    declarations = interrepo.get('journeys', [])
    runtime_cases = []
    for level, kind in (('N10', 'sonde-api'), ('N14', 'kit-metier')):
        path = root / 'levels' / level / 'result.json'
        if not path.is_file():
            continue
        data = read_json(path)
        for finding in data.get('findings', []):
            if finding['id'] != 'probes.not-e2e':
                runtime_cases.append({'kind': kind, 'id': finding['id'], 'mode': '',
                                      'verdict': finding['verdict'], 'status': finding['message'],
                                      'required': False, 'details': finding})
    result = assess(snapshot, decisions, declarations, policy if isinstance(policy, dict) else {},
                    collected=collected, runtime_cases=runtime_cases)
    for path in write_assessment(result, root):
        report.artifact('validation-integrale', path, 'Résultats détaillés par dépôt, frontière et mode')
    report.metrics.update(cases=len(result['cases']), counts=result['counts'],
                          required_total=result['required_total'], required_pass=result['required_pass'])
    for verdict in ('FAIL', 'CONFIG_ERROR', 'BLOCKED', 'PARTIAL'):
        count = sum(row['verdict'] == verdict for row in result['cases']
                    if row['required'] or row['kind'] == 'frontiere')
        if count:
            _emit(report,'full.cases.'+verdict.lower(),verdict,'scope',
                  f'{count} contrôle(s) {verdict}. Consulter la matrice intégrale.')
    if not result['cases'] or not result['documentary_aligned']:
        _emit(report,'full.scope.incomplete','PARTIAL','scope','Périmètre documentaire incomplet')


def n14(cfg, report, ctx):
    if not ctx.get('runtime_local'):
        _emit(report, 'runtime.local.disabled', 'SKIP', 'runtime',
              'Kit d’essai local disponible avec --runtime-local')
        return
    from ..local_runtime import run
    audit = ctx.get('runtime_audit')
    verdict, message, evidence = run(
        Path(cfg['_root']), world=ctx.get('runtime_world'),
        audit=Path(audit) if audit else None, run_root=Path(ctx['run_root']),
        start_stack=ctx.get('start_test_stack', False),
    )
    _emit(report, 'runtime.konnaxion-orgo.official', verdict, 'runtime', message, evidence)


RUNNERS={f'N{i:02d}':fn for i,fn in enumerate((n00,n01,n02,n03,n04,n05,n06,n07,n08,n09,n10,n11,n12,n13,n14))}
