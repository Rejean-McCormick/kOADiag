# -*- coding: utf-8 -*-
"""LevelUpDiag-style dependency scheduler with isolated processes and run history."""
from __future__ import annotations
from . import VERSION
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import importlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback
import uuid
from .framework import (Report,read_json,write_json,now,load_config,load_manifest,
                       resolve_campaign,campaign_verdict,VERDICTS)
from .coverage import from_snapshot,priorities,get_previous,delta,export_relations_matrix
from .audit_export import publish_private_bundle
from .boundary_review import write_review_register
from .boundary_registry import metrics as registry_metrics, export_csv as registry_csv
from .inventory_alignment import compare as compare_inventories
from . import audit_bridge

# A PARTIAL upstream snapshot is usable evidence. Only a missing/fatal dependency blocks children.
HARD={'FAIL','SKIP','BLOCKED','ERROR','INFRA_ERROR','CONFIG_ERROR'}


def run_id():return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]


def _blocked(meta,root,uid,deps):
    r=Report(meta,root,uid)
    r.add('dependencies.unavailable','BLOCKED','orchestration',
          'Dépendance de niveau non disponible',evidence={'dependencies':deps})
    return r.data()


def _failure(meta,root,uid,verdict,message):
    r=Report(meta,root,uid)
    r.add('worker.infra.failure',verdict,'infrastructure',message)
    return r.data()


def _console_python():
    exe=Path(sys.executable)
    if os.name=='nt' and exe.name.lower()=='pythonw.exe':
        other=exe.with_name('python.exe')
        if other.exists():return str(other)
    return str(exe)


def worker(tool,meta,cfg,run_root,uid,allow_network=False,allow_remote=False,ack_remote=False,
           *, integral=False, runtime_local=False, runtime_world=None, runtime_audit=None, start_test_stack=False):
    # Worker can write only within the run directory that was created by parent.
    tool=Path(tool).resolve();run_root=Path(run_root).resolve()
    conf=Path(cfg['_control']).resolve()
    if not run_root.is_relative_to(conf/'runs'):
        raise ValueError('run_root hors contrôle')
    level_dir=run_root/'levels'/meta['id'];level_dir.mkdir(parents=True,exist_ok=True)
    report=Report(meta,cfg['_root'],uid)
    ctx={'run_root':str(run_root),'allow_network':allow_network,
         'allow_remote':allow_remote,'ack_remote':ack_remote,
         'integral':integral,'runtime_local':runtime_local,
         'runtime_world':runtime_world,'runtime_audit':runtime_audit,'start_test_stack':start_test_stack}
    try:
        module=importlib.import_module(meta['module'])
        module.RUNNERS[meta['id']](cfg,report,ctx)
        # Quality propagates independently of the DAG scheduling gate. A partial
        # snapshot MUST NEVER silently yield a PASS child level.
        upstream={}
        for dep in meta.get('depends_on',[]):
            source=run_root/'levels'/dep/'result.json'
            if source.is_file():
                upstream[dep]=read_json(source).get('verdict','ERROR')
        partial={k:v for k,v in upstream.items() if v=='PARTIAL'}
        if partial:
            report.add('evidence.upstream.partial','PARTIAL','coverage',
              'Résultat fondé sur une collecte partielle; les constats restent utilisables, pas exhaustifs.',
              evidence={'upstream':partial})
        report.metrics['upstream_quality']=upstream
        value=report.data()
    except Exception as exc:
        report.add('worker.exception','ERROR','diagnostic',
                   f'Erreur interne {meta["id"]}: {type(exc).__name__}: {str(exc)[:300]}',
                   recommendation='Consulter le traceback; aucun verdict PASS inféré.')
        (level_dir/'traceback.txt').write_text(traceback.format_exc()[-16000:],encoding='utf-8')
        report.artifact('traceback',level_dir/'traceback.txt','Erreur isolée du niveau')
        value=report.data('ERROR')
    write_json(level_dir/'result.json',value)
    return value


def campaign(tool,selection='complet',root_override=None,config_override=None,*,jobs=None,
             allow_network=False,allow_remote=False,ack_remote=False,notify=None,runtime_local=False,
             audit=False,audit_root=None,runtime_world=None,start_test_stack=False):
    notify=notify or (lambda text:None)
    tool=Path(tool).resolve()
    manifest=load_manifest(tool)
    cfg=load_config(tool,root_override,config_override)
    if allow_remote and (not allow_network or not ack_remote):
        raise ValueError('Accès distant interdit sans --network ET --ack-remote')
    if runtime_local and selection != 'validation-integrale':
        raise ValueError('--runtime-local requiert validation-integrale')
    levels=resolve_campaign(manifest,selection)
    uid=run_id();run_root=Path(cfg['_control'])/'runs'/uid
    run_root.mkdir(parents=True,exist_ok=False)
    # Only public/non-secret config is persisted. Refuse key/value secrets in config.
    save_cfg={k:v for k,v in cfg.items() if not k.startswith('_')}
    write_json(run_root/'effective_config.json',save_cfg)
    started=now();notify(f'RUN_ROOT={run_root}')
    audit_dir = None
    audit_status = None
    if audit or audit_root:
        try:
            audit_dir = audit_bridge.find_audit(Path(cfg['_root']), audit_root)
            sources, errors = audit_bridge.archive_descriptors(Path(cfg['_root']), audit_dir)
            write_json(run_root/'archived-evidence.json', sources)
            notify(f'AUDIT_EVIDENCE={len(sources)} export(s) archivé(s)')
            for error in errors:
                notify('AUDIT_EVIDENCE_WARNING='+error)
        except (OSError, ValueError, TypeError) as exc:
            audit_status = {'status': 'UNAVAILABLE', 'detail': str(exc)}
            notify('AUDIT_WARNING='+str(exc))
    workers=int(jobs or cfg.get('execution',{}).get('max_parallel',4));workers=max(1,min(8,workers))
    meta_by={x['id']:x for x in levels}
    pending=set(meta_by);running={};results={}
    full = selection == 'validation-integrale'
    fail_fast = not full and bool(cfg.get('execution', {}).get('fail_fast', False))
    def launch(meta):
        dest=run_root/'levels'/meta['id'];dest.mkdir(parents=True,exist_ok=True)
        cmd=[_console_python(),str(tool/'Diagnostic-kOA-Digital-Ecosystem-CLI.py'),
            '_worker','--root',cfg['_root'],'--run-root',str(run_root),
            '--id',meta['id'],'--run-id',uid]
        if config_override:cmd+=['--config',str(Path(config_override).resolve())]
        if allow_network:cmd.append('--network')
        if allow_remote:cmd.append('--remote')
        if ack_remote:cmd.append('--ack-remote')
        if full:cmd.append('--integral-worker')
        if runtime_local:cmd.append('--runtime-local')
        if meta['id'] == 'N14' and start_test_stack:cmd.append('--start-test-stack')
        if meta['id'] == 'N14' and runtime_world:cmd+=['--world', runtime_world]
        if audit_dir and meta['id'] in ('N00', 'N14'):cmd+=['--audit-root', str(audit_dir)]
        timeout=int(meta.get('timeout_seconds',cfg.get('execution',{}).get('default_timeout_seconds',120)))
        if meta['id'] == 'N14' and start_test_stack:
            timeout = max(timeout, 600)
        if full and meta['id'] == 'N01':
            timeout = max(timeout, 1800)
        start=time.monotonic()
        try:
            result=subprocess.run(cmd,cwd=str(tool),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,encoding='utf-8',errors='replace',text=True,shell=False,timeout=timeout,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name=='nt' else 0)
            path=dest/'result.json'
            if path.is_file():
                data=read_json(path)
                if data.get('schema')!='levelupdiag.report.v2' or data.get('level_id')!=meta['id'] or data.get('run_id')!=uid:
                    data=_failure(meta,cfg['_root'],uid,'INFRA_ERROR','Résultat worker malformé')
            else:
                data=_failure(meta,cfg['_root'],uid,'INFRA_ERROR',
                              f'Worker sans résultat (code {result.returncode}); stderr: {result.stderr[-700:]}')
        except subprocess.TimeoutExpired:
            data=_failure(meta,cfg['_root'],uid,'INFRA_ERROR',f'Niveau expiré après {timeout}s')
        except Exception as exc:
            data=_failure(meta,cfg['_root'],uid,'INFRA_ERROR',f'Impossible de lancer le niveau: {exc}')
        data.setdefault('metrics',{})['worker_duration_seconds']=round(time.monotonic()-start,2)
        write_json(dest/'result.json',data)
        return data

    # Import freshly produced evidence before the passive collector starts.
    # N14 failure is recorded as a level result; it never gates N01.
    if runtime_local and 'N14' in pending:
        notify('N14 · Exécution du kit local sur la pile d’essai')
        results['N14'] = launch(meta_by['N14'])
        pending.remove('N14')
        notify(f'LEVEL=N14|{results["N14"]["verdict"]}|{meta_by["N14"]["name"]}')
    pool=ThreadPoolExecutor(max_workers=workers)
    try:
        while pending or running:
            for lid,f in list(running.items()):
                if f.done():
                    results[lid]=f.result();del running[lid]
                    notify(f'LEVEL={lid}|{results[lid]["verdict"]}|{meta_by[lid]["name"]}')
            if fail_fast and pending and any(r['verdict'] in ('FAIL','ERROR','CONFIG_ERROR') for r in results.values()):
                for lid in list(pending):
                    results[lid]=_blocked(meta_by[lid],cfg['_root'],uid,{'fail_fast':'arrêt'})
                    pending.remove(lid)
                    notify(f'LEVEL={lid}|BLOCKED|arrêt anticipé configuré')
                continue
            ready=[];blocked_this_round=False
            for lid in list(pending):
                meta=meta_by[lid];deps=meta.get('depends_on',[])
                if all(d in results for d in deps):
                    tolerated = set(meta.get('continue_after', [])) if full else set()
                    snapshot_available = (run_root/'levels'/'N01'/'snapshot.json').is_file()
                    bad = {d: results[d]['verdict'] for d in deps if d not in tolerated
                           and results[d]['verdict'] in HARD
                           and not (full and d == 'N01' and snapshot_available)}
                    if bad:
                        results[lid]=_blocked(meta,cfg['_root'],uid,bad);pending.remove(lid);blocked_this_round=True
                        notify(f'LEVEL={lid}|BLOCKED|dépendance indisponible')
                    else:ready.append(meta)
            ready.sort(key=lambda x:(x.get('order',0),x['id']))
            exclusive=next((x for x in ready if not x.get('parallel_safe',True)),None)
            launched=False
            if exclusive and not running:
                running[exclusive['id']]=pool.submit(launch,exclusive);pending.remove(exclusive['id']);launched=True
            elif not exclusive and not any(not meta_by[k].get('parallel_safe',True) for k in running):
                for meta in ready[:max(0,workers-len(running))]:
                    running[meta['id']]=pool.submit(launch,meta);pending.remove(meta['id']);launched=True
            if not launched and running:time.sleep(.1)
            if not launched and not running and pending and not blocked_this_round:
                raise RuntimeError('Orchestrateur bloqué; inspecter les dépendances du manifeste')
    finally:pool.shutdown(wait=True)
    ordered=[results[m['id']] for m in levels]
    for row in ordered:
        write_json(run_root/'levels'/row['level_id']/'result.json',row)
    required={x['id']:bool(x.get('required')) for x in levels}
    verdict=campaign_verdict(ordered,required)
    counts={x:sum(r['verdict']==x for r in ordered) for x in VERDICTS}
    snapshot_file=run_root/'levels'/'N01'/'snapshot.json'
    snapshot=read_json(snapshot_file) if snapshot_file.is_file() else None
    cover=from_snapshot(snapshot) if snapshot else None
    registry_file=run_root/'registry-snapshot.json'
    registry_data=read_json(registry_file) if registry_file.is_file() else None
    if cover is not None:
        cover['boundary_registry']=registry_metrics(registry_data) if registry_data else {'status':'UNAVAILABLE','review_complete':False}
        boundary_file=run_root/'boundary-qualification.json'
        if boundary_file.is_file():
            cover['boundary_evidence']=read_json(boundary_file).get('summary',{})
    previous_summary,previous_snapshot=get_previous(cfg['_control'],uid)
    changes=delta(previous_summary,previous_snapshot,cover,snapshot) if cover else {'comparison_available':False,'reason':'Collecte N01 absente'}
    write_json(run_root/'delta.json',changes)
    try:
        alignment=compare_inventories(tool, audit_dir)
        write_json(run_root/'inventory-alignment.json',alignment)
    except (ValueError,OSError,TypeError,KeyError) as exc:
        alignment={'source':'unavailable','aligned':False,'error':str(exc)[:160]}
    if cover is not None:
        cover['inventory_alignment']={k: (len(alignment[k]) if k in ('diag_only','audit_only') else alignment[k]) for k in ('source','aligned','diag_count','audit_count','common','diag_only','audit_only') if k in alignment}
    if snapshot:
        export_relations_matrix(snapshot,run_root/'exports'/'matrice-relations.csv')
        # Explicitly list the actual repository collection gaps, not only totals.
        with (run_root/'exports'/'couverture-depots.csv').open('w',encoding='utf-8-sig',newline='') as stream:
            import csv
            writer=csv.DictWriter(stream,fieldnames=['repo','exists','truncated','eligible_files','scanned_files','oversized_files','unreadable_files','unselected_files','index_overflow_files'],delimiter=';')
            writer.writeheader()
            for repo in snapshot.get('repositories',[]):
                writer.writerow({k:repo.get(k,'') for k in writer.fieldnames})
        # Paths are directory names relative to each repo, not code snippets.
        gaps=[{'repo':repo.get('repo'), 'truncated':repo.get('truncated',False),
               'boundary_scan_gaps':repo.get('boundary_scan_gaps',[]),
               'boundary_scan_gap_count':repo.get('boundary_scan_gap_count',0),
               'unreadable_files':repo.get('unreadable_files',0),
               'unselected_files':repo.get('unselected_files',0),
               'oversized_files':repo.get('oversized_files',0),
               'top_unselected_directories':repo.get('unselected_by_root',[]),
               'top_oversized_directories':repo.get('oversized_by_root',[])}
              for repo in snapshot.get('repositories',[])
              if any(repo.get(key,0) for key in ('unselected_files','oversized_files',
                                                  'unreadable_files','boundary_scan_gap_count'))]
        write_json(run_root/'scan-gaps.json',{'schema':'koa.scan-gaps/v1','repos':gaps})
        if registry_data:registry_csv(registry_data,run_root/'exports'/'registre-frontieres.csv')
        write_review_register(snapshot,run_root/'exports'/'frontieres-a-qualifier.csv')
        (run_root/'priorites.txt').write_text('\n'.join(priorities(cover))+'\n',encoding='utf-8')
    summary={'schema':'levelupdiag.campaign-summary.v2','standard':'LevelUpDiag','standard_version':'1.0.0',
             'suite':'Diagnostic du kOA Digital Ecosystem','suite_version':VERSION,
             'run_id':uid,'selection':selection,'target_repo_root':cfg['_root'],
             'started_at':started,'ended_at':now(),'verdict':verdict,'counts':counts,
             'coverage':cover,'comparison':{'available':changes['comparison_available'],
                 'previous_run_id':changes.get('previous_run_id'),'report':'delta.json'},
             'expected_levels':[m['id'] for m in levels],
             'required_levels':[m['id'] for m in levels if m.get('required')],
             'levels':[{'id':r['level_id'],'name':r['level_name'],'verdict':r['verdict'],
                       'result':f"levels/{r['level_id']}/result.json"} for r in ordered],
             'security':{'repo_mutations':False,'internal_app_tests':False,'local_test_data_mutations_possible':bool(runtime_local),
                         'allow_network':bool(allow_network),'allow_remote':bool(allow_remote),
                         'local_runtime_kit_requested':bool(runtime_local)},
             'provenance':'Evidence statique ou traces exportées; aucune certification E2E implicite.'}
    comprehensive = run_root/'validation-integrale.json'
    if comprehensive.is_file():
        result = read_json(comprehensive)
        summary['validation_integrale'] = {key: result[key] for key in
            ('counts', 'required_total', 'required_pass', 'global_certified')}
        summary['validation_integrale']['report'] = comprehensive.name
    closure_report = None
    if full:
        from .closure import assess, write_report
        validation = read_json(comprehensive) if comprehensive.is_file() else {}
        closure_report = assess(summary, validation, alignment)
        write_report(run_root, closure_report)
        summary['cloture'] = {'status': closure_report['status'], 'report': 'cloture.json',
                              'mandatory_boundaries_by_mode': closure_report['mandatory_boundaries_by_mode']}
        notify('CLOTURE='+str(run_root/'cloture.json'))
    write_json(run_root/'summary.json',summary)
    txt=['Diagnostic du kOA Digital Ecosystem - '+selection,'Run: '+uid,'Verdict: '+verdict,
         'Racine: '+cfg['_root'],'','NIVEAUX']
    txt += [f"{r['level_id']}  {r['verdict']:<12} {r['level_name']}" for r in ordered]
    if cover:
        txt += ['','COUVERTURE : '+str(cover['inventory']['present'])+'/'+str(cover['inventory']['declared'])+' dépôts; '+str(cover['inventory']['truncated'])+' tronqués',
                'PARCOURS : '+str(cover['journeys']['evidence_complete'])+'/'+str(cover['journeys']['declared'])+' suffisamment corroborés',
                'E2E GLOBAL : NON CERTIFIÉ',
                'FRONTIÈRES À QUALIFIER : '+str(cover['boundary_registry'].get('new_or_unreviewed','?')), '', 'PRIORITÉS']+priorities(cover)
    if 'validation_integrale' in summary:
        details = summary['validation_integrale']
        txt += ['', f"VALIDATION INTÉGRALE : {details['required_pass']}/{details['required_total']} contrôles obligatoires PASS",
                'Détail : validation-integrale.json et exports/validation-integrale.csv']
    txt += ['','Une route, un import ou une réponse GET ne valide pas un échange métier E2E.']
    (run_root/'summary.txt').write_text('\n'.join(txt)+'\n',encoding='utf-8')
    latest=Path(cfg['_control'])/'latest'
    latest.mkdir(parents=True,exist_ok=True)
    if closure_report:
        write_report(latest, closure_report)
    else:
        for name in ('cloture.json', 'cloture.txt'):
            (latest/name).unlink(missing_ok=True)
    (latest/'audit-import.json').unlink(missing_ok=True)
    write_json(latest/'summary.json',summary)
    (latest/'summary.txt').write_text('\n'.join(txt)+'\n',encoding='utf-8')
    for r in ordered:
        dest=latest/'levels'/r['level_id']/'result.json';dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(run_root/'levels'/r['level_id']/'result.json',dest)
    # Only metadata derived from the completed campaign is made importable by
    # GitHub Audit. Failure to export does not alter the diagnostic verdict.
    try:
        archived, current = publish_private_bundle(run_root, Path(cfg['_control']))
        notify('AUDIT_EXPORT='+str(current))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        notify('AUDIT_EXPORT_ERROR='+type(exc).__name__+': '+str(exc)[:180])
    if audit_dir:
        try:
            audit_status = audit_bridge.import_run(run_root, audit_dir, _console_python())
        except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
            audit_status = {'status': 'ERROR', 'detail': str(exc)[:900]}
    if audit_status:
        write_json(run_root/'audit-import.json', audit_status)
        if read_json(latest/'summary.json')['run_id'] == uid:
            write_json(latest/'audit-import.json', {'run_id': uid, **audit_status})
        notify('AUDIT_IMPORT='+audit_status['status']+' · '+audit_status['detail'])
    notify('VERDICT='+verdict)
    return summary,run_root
