# -*- coding: utf-8 -*-
"""Evidence coverage, next steps and campaign-to-campaign delta.

All statements are intentionally qualified. 'E2E global' is never inferred from
inventory, static contracts, isolated 200 responses, or even partial journeys.
"""
from __future__ import annotations
from pathlib import Path
import csv
from .framework import read_json,write_json


def from_snapshot(snapshot):
    d=snapshot.get('summary',{}) if isinstance(snapshot,dict) else {}
    expected=int(d.get('inventory_repos') or 0)
    present=int(d.get('present_repos') or 0)
    truncated=int(d.get('repositories_scan_truncated') or 0)
    journeys=snapshot.get('journeys',[])
    valid=sum(row.get('status')=='EVIDENCE_COMPLETE' for row in journeys)
    return {'inventory':{'present':present,'declared':expected,'truncated':truncated,
                          'complete':bool(expected and present==expected and not truncated
                                          and not int(d.get('source_files_oversized',0))
                                          and not int(d.get('source_files_unreadable',0))
                                          and not int(d.get('source_repositories_empty',0))),
                          'eligible_files':int(d.get('source_files_eligible') or 0),
                          'scanned_files':int(d.get('source_files_scanned') or 0),
                          'unselected_files':int(d.get('source_files_unselected') or 0),
                          'oversized_files':int(d.get('source_files_oversized') or 0),
                          'unreadable_files':int(d.get('source_files_unreadable') or 0),
                          'empty_repo_surfaces':int(d.get('source_repositories_empty') or 0),
                          'scan_scope':'code/configuration (hors dossiers exclus)'},
            'relations':int(d.get('relations') or 0),
            'api':{'static_calls':int(d.get('api_static_calls') or 0),
                   'routes_matched':int(d.get('api_route_matches') or 0),
                   'routes_inbound':int(d.get('api_inbound_routes') or 0),
                   'declared':int(d.get('expected_api_links') or 0),
                   'declared_matched':int(d.get('expected_api_links_matched') or 0),
                   'live_checks_ok':int(d.get('api_live_ok') or 0)},
            'traces':{'correlated_pairs':int(d.get('exchanges_correlated') or 0),
                      'ik_receipts':int(d.get('ik_receipts_success') or 0)},
            'journeys':{'declared':len(journeys),'evidence_complete':valid,
                        'not_proven':len(journeys)-valid},
            'global_end_to_end':{'status':'NON_CERTIFIE',
                'explanation':'La validation A à Z exige un référentiel exhaustif de parcours et des preuves indépendantes de chaque frontière; les exports restent des observations, pas une preuve universelle.'}}


def priorities(cover):
    lines=[]
    inv=cover['inventory'];api=cover['api'];trace=cover['traces'];j=cover['journeys']
    if inv['declared']!=inv['present']:
        lines.append(f"Inventaire : {inv['declared']-inv['present']} dépôt(s) non observé(s) — confirmer les chemins C:\\mycode.")
    if inv['truncated']:
        lines.append(f"Collecte : {inv['truncated']} dépôt(s) tronqué(s) — vérifier les fichiers ciblés et ajuster la limite.")
    if inv.get('oversized_files') or inv.get('unreadable_files'):
        lines.append(f"Collecte : {inv.get('oversized_files')} fichiers volumineux et {inv.get('unreadable_files')} fichiers illisibles ignorés.")
    if inv.get('empty_repo_surfaces'):
        lines.append(f"Collecte : {inv['empty_repo_surfaces']} dépôt(s) sans fichier source/configuration dans le périmètre analysé.")
    if not j['declared']:
        lines.append('E2E : déclarer les parcours requis dans koa-ecosystem-diag.config.local.json.')
    elif j['not_proven']:
        lines.append(f"E2E : {j['not_proven']} parcours sur {j['declared']} n’ont pas assez de preuves de livraison/réponse.")
    if api['declared'] and api['declared_matched']<api['declared']:
        lines.append(f"API : {api['declared']-api['declared_matched']} frontières explicites sans paire appel/route statique.")
    if not trace['correlated_pairs']:
        lines.append('Traces : importer des exports passifs attribués aux dépôts émetteur et récepteur.')
    boundary=cover.get('boundary_evidence',{})
    if boundary.get('required_unproven'):
        lines.append(f"Preuves : {boundary['required_unproven']} frontières obligatoires sans parcours corroboré; voir matrice-preuves-frontieres.csv.")
    if api['static_calls'] and not api['routes_matched']:
        lines.append('API : rattacher les appels statiques à des dépôts/routes via les endpoints déclarés; ne pas inférer les cibles.')
    if not lines:
        lines.append('Les relations auditées sont qualifiées. Une preuve E2E globale exige toujours une couverture exhaustive des parcours.')
    return lines


def get_previous(control, uid, *, intermediate=False):
    all_summaries=sorted((Path(control)/'runs').glob('*/summary.json'),reverse=True)
    for p in all_summaries:
        if p.parent.name==uid:continue
        try:
            summary=read_json(p)
            if (summary.get('selection') == 'validation-intermediaire') != intermediate:
                continue
            snapshot=p.parent/'levels'/'N01'/'snapshot.json'
            return summary,read_json(snapshot) if snapshot.is_file() else None
        except (OSError,ValueError,KeyError,TypeError):pass
    return None,None


def delta(previous_summary,previous_snapshot,cover,current_snapshot):
    if not previous_summary:return {'comparison_available':False,'reason':'Première campagne sans référence antérieure'}
    result={'comparison_available':True,'previous_run_id':previous_summary.get('run_id'),
            'previous_verdict':previous_summary.get('verdict'),
            'metrics':{},'relations_added':[],'relations_not_observed':[],'relations_changed':[]}
    if not previous_snapshot:return result
    before=from_snapshot(previous_snapshot)
    for category,field in (('inventory','present'),('inventory','truncated'),('api','static_calls'),('api','routes_matched'),('traces','correlated_pairs'),('journeys','evidence_complete')):
        old=before[category][field];new=cover[category][field]
        result['metrics'][f'{category}.{field}']={'before':old,'after':new,'delta':new-old}
    def key(r):return (str(r.get('source','')).casefold(),str(r.get('target','')).casefold(),str(r.get('contract','')).casefold())
    prev={key(r):r for r in previous_snapshot.get('relations',[])}
    curr={key(r):r for r in current_snapshot.get('relations',[])}
    result['relations_added']=[{'source':r['source'],'target':r['target'],'contract':r.get('contract'),'qualification':r.get('qualification')} for k,r in curr.items() if k not in prev]
    result['relations_not_observed']=[{'source':r['source'],'target':r['target'],'contract':r.get('contract'),'qualification':r.get('qualification')} for k,r in prev.items() if k not in curr]
    result['relations_changed']=[{'source':curr[k]['source'],'target':curr[k]['target'],
        'contract':curr[k].get('contract'),'before':prev[k].get('qualification'),
        'after':curr[k].get('qualification')} for k in curr.keys() & prev.keys() if curr[k].get('qualification')!=prev[k].get('qualification')]
    return result


def export_relations_matrix(snapshot, target):
    fields=['id','source','target','contract','qualification','topologie','contrat','api_statique','api_sonde','echange_passif','ik_receipts','obligations']
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('w',encoding='utf-8-sig',newline='') as fh:
        writer=csv.DictWriter(fh,fieldnames=fields,delimiter=';');writer.writeheader()
        for row in snapshot.get('relations',[]):
            dims=row.get('dimensions',{})
            writer.writerow({name:row.get(name,'') if name in ('id','source','target','contract','qualification') else dims.get(name,'') for name in fields})
    return target
