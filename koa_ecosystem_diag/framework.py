# -*- coding: utf-8 -*-
"""LevelUpDiag architectural contract adapted to kOA's inter-repository boundaries.

Manifest v2, isolated workers, explicit dependencies, bounded evidence, stable
findings, strict verdict aggregation, and run history. No app/test commands.
"""
from __future__ import annotations
from . import VERSION
import json
from datetime import datetime, timezone
from pathlib import Path

VERDICTS = ('PASS','WARN','FAIL','SKIP','BLOCKED','PARTIAL','ERROR','INFRA_ERROR','CONFIG_ERROR')
RANK = {'PASS':0,'WARN':1,'SKIP':2,'PARTIAL':3,'BLOCKED':4,'INFRA_ERROR':5,'FAIL':6,'ERROR':7,'CONFIG_ERROR':8}


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def read_json(path):
    with Path(path).open(encoding='utf-8-sig') as stream:
        return json.load(stream)


def write_json(path, obj):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.tmp')
    with temp.open('w',encoding='utf-8') as out:
        json.dump(obj,out,ensure_ascii=False,indent=2,default=str)
        out.write('\n')
    temp.replace(path)


def merge(base, patch):
    if not isinstance(base,dict) or not isinstance(patch,dict):
        return patch
    out={k:v for k,v in base.items()}
    for k,v in patch.items():
        out[k]=merge(out[k],v) if k in out else v
    return out


def verdict_for(findings):
    return max((x['verdict'] for x in findings), key=lambda x:RANK[x],default='PASS')


def campaign_verdict(results, required):
    if not results:return 'CONFIG_ERROR'
    values=[r.get('verdict','ERROR') for r in results]
    if any(x in ('CONFIG_ERROR','ERROR') for x in values):return 'ERROR'
    if 'FAIL' in values:return 'FAIL'
    if any(r.get('verdict') in ('SKIP','BLOCKED','INFRA_ERROR') and required.get(r['level_id']) for r in results):return 'BLOCKED'
    if any(r.get('verdict')=='PARTIAL' and required.get(r['level_id']) for r in results):return 'PARTIAL'
    if any(x in ('WARN','BLOCKED','PARTIAL','INFRA_ERROR') for x in values):return 'WARN'
    return 'PASS'


class Report:
    def __init__(self,meta,root,run_id):
        self.meta=meta;self.root=str(root);self.run_id=run_id;self.started=now()
        self.findings=[];self.artifacts=[];self.metrics={}

    def add(self,id,verdict,category,message,*,evidence=None,recommendation=None):
        if verdict not in VERDICTS:raise ValueError('Unknown verdict: '+str(verdict))
        obj={'id':id,'verdict':verdict,'category':category,'message':str(message)[:900]}
        if evidence is not None:obj['evidence']=evidence
        if recommendation:obj['recommendation']=recommendation
        self.findings.append(obj)

    def artifact(self,kind,path,description=''):
        self.artifacts.append({'kind':kind,'path':str(path),'description':description})

    def data(self,verdict=None):
        return {'schema':'levelupdiag.report.v2','standard':'LevelUpDiag','standard_version':'1.0.0',
          'suite':'Diagnostic du kOA Digital Ecosystem','suite_version':VERSION,
          'run_id':self.run_id,'level_id':self.meta['id'],'level_name':self.meta['name'],
          'purpose':self.meta.get('purpose',''),'target_repo_root':self.root,
          'started_at':self.started,'ended_at':now(),'verdict':verdict or verdict_for(self.findings),
          'required':self.meta.get('required',False),'findings':self.findings,
          'artifacts':self.artifacts,'metrics':self.metrics}


def load_manifest(tool):
    m=read_json(Path(tool)/'koa-ecosystem-diag.manifest.json')
    if m.get('schema')!='levelupdiag.manifest.v2':raise ValueError('Format manifeste incompatible')
    levels=m.get('levels',[]);ids=[x.get('id') for x in levels]
    if not ids or len(set(ids))!=len(ids) or any(not x for x in ids):raise ValueError('Niveaux non uniques')
    for x in levels:
        if not isinstance(x.get('module'),str) or not x['module'].startswith('koa_ecosystem_diag.levels.'):
            raise ValueError('Module de niveau refusé: '+str(x.get('module')))
        for d in x.get('depends_on',[]):
            if d not in ids:raise ValueError(f"{x['id']} dépend d'un niveau inconnu: {d}")
    # Reject any dependency cycle before the scheduler starts.
    deps={x['id']:x.get('depends_on',[]) for x in levels}
    visited=set();active=set()
    def visit(i):
        if i in active:raise ValueError('Cycle de dépendances: '+i)
        if i in visited:return
        active.add(i)
        for j in deps[i]:visit(j)
        active.remove(i);visited.add(i)
    for x in ids:visit(x)
    return m


def resolve_campaign(manifest,name):
    levels={x['id']:x for x in manifest['levels']}
    if name in levels:chosen={name}
    elif name in manifest.get('campaigns',{}):chosen=set(manifest['campaigns'][name]['levels'])
    else:raise ValueError('Campagne inconnue: '+name)
    if not chosen.issubset(levels):raise ValueError('Campagne contient des niveaux inconnus')
    while True:
        more=chosen | {d for i in chosen for d in levels[i].get('depends_on',[])}
        if more==chosen:break
        chosen=more
    return sorted((levels[x] for x in chosen),key=lambda r:(r.get('order',0),r['id']))


def load_config(tool,root_override=None,config_override=None):
    tool=Path(tool).resolve()
    cfg=read_json(tool/'koa-ecosystem-diag.config.json')
    local=tool/'koa-ecosystem-diag.config.local.json'
    if local.is_file():cfg=merge(cfg,read_json(local))
    if config_override:cfg=merge(cfg,read_json(config_override))
    if cfg.get('format')!='koa.digital-ecosystem-diagnostic.config/v1':
        raise ValueError('Format configuration invalide')
    root=Path(root_override or cfg.get('target_root') or r'C:\mycode').expanduser().resolve()
    if not root.is_dir():raise ValueError('Dossier racine introuvable: '+str(root))
    control=Path(cfg.get('control_dir','reports/Diagnostic-kOA-Digital-Ecosystem'))
    if control.is_absolute() or '..' in control.parts or not control.parts:
        raise ValueError('control_dir doit rester relatif au diagnostic')
    resolved=(tool/control).resolve()
    if not resolved.is_relative_to(tool) or resolved==tool:raise ValueError('Sortie non autorisée')
    interrepo=cfg.get('interrepo',{})
    if interrepo.get('format')!='koa.interrepo-kernel.config/1':raise ValueError('Configuration interrepo incompatible')
    cfg['_root']=str(root);cfg['_tool']=str(tool);cfg['_control']=str(resolved)
    return cfg
