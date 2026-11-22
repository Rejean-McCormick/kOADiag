# -*- coding: utf-8 -*-
import argparse
import sys
from pathlib import Path
from . import runner
from .framework import load_manifest,load_config,read_json


def main(argv=None):
    p=argparse.ArgumentParser(description='Diagnostic du kOA Digital Ecosystem - architecture LevelUpDiag')
    p.add_argument('action',nargs='?',default='run',choices=['run','history','manifest','export-audit','ports','_worker'])
    p.add_argument('selection',nargs='?',default='complet')
    p.add_argument('--root',default=None)
    p.add_argument('--config',default=None)
    p.add_argument('--jobs',type=int,default=None)
    p.add_argument('--registry',default=None,help='Chemin du registre officiel C0 (optionnel)')
    p.add_argument('--port-timeout',type=float,default=1.0,help='Timeout TCP/HTTP local par sonde (0.1–10 s)')
    p.add_argument('--port-out-dir',default=None,help='Dossier de rapports des sondes C0')
    p.add_argument('--network',action='store_true',help='Activer les sondes explicitement configurées')
    p.add_argument('--remote',action='store_true',help='Autoriser les endpoints non-loopback')
    p.add_argument('--ack-remote',action='store_true',help='Reconnaître les risques des requêtes distantes GET/HEAD')
    p.add_argument('--run-root',default=None)
    p.add_argument('--out',default=None,help='Destination de export-audit (*.zip)')
    p.add_argument('--run-id',default=None)
    p.add_argument('--id',default=None)
    p.add_argument('--integral-worker',action='store_true',help=argparse.SUPPRESS)
    p.add_argument('--runtime-local',action='store_true',
                   help='Exécuter le kit officiel Konnaxion–Orgo sur une pile locale d’essai (crée des données)')
    p.add_argument('--audit',action='store_true',help='Lire les exports privés et importer la campagne dans GitHub Audit')
    p.add_argument('--audit-root',help='Dossier du dépôt GitHub Audit')
    p.add_argument('--world',help='World actif de la pile d’essai Fakeplant')
    p.add_argument('--start-test-stack', action='store_true', help='Démarrer les services Docker de la pile Fakeplant existante')
    args=p.parse_args(argv)
    if args.start_test_stack and not args.runtime_local:p.error('--start-test-stack requiert --runtime-local')
    tool=Path(__file__).resolve().parents[1]
    if args.action=='ports':
        from .port_diagnostics import check_all, write_reports
        root = Path(args.root or r'C:\mycode')
        report = check_all(root, registry=args.registry, timeout=args.port_timeout)
        output = Path(args.port_out_dir) if args.port_out_dir else tool/'reports'/'Diagnostic-kOA-Digital-Ecosystem'/'ports-c0'
        folder = write_reports(report, output)
        print(f"PORTS_C0={report['expected']}", flush=True)
        for row in report['services']:
            print(f"{row['port']} | {row['id']} | {row['status']} | {row['detail']}", flush=True)
        print('REPORT_PORTS_C0='+str(folder), flush=True)
        statuses = {row['status'] for row in report['services']}
        if 'WRONG_SERVICE' in statuses or 'SCAN_ERROR' in statuses:
            return 20
        if any(s not in ('FAMILY_MATCH', 'IDENTITY_CONFIRMED') for s in statuses):
            return 10
        return 0
    if args.action=='manifest':
        import json
        print(json.dumps(load_manifest(tool),ensure_ascii=False,indent=2));return 0
    if args.action=='history':
        c=load_config(tool,args.root,args.config)
        folder=Path(c['_control'])/'runs'
        for path in sorted(folder.glob('*/summary.json'),reverse=True)[:40] if folder.exists() else []:
            s=read_json(path)
            print(s['run_id'],s['selection'],s['verdict'])
        return 0
    if args.action=='export-audit':
        from .audit_export import export_campaign, publish_private_bundle
        if args.run_root:
            source=Path(args.run_root).expanduser().resolve()
        else:
            c=load_config(tool,args.root,args.config)
            source=Path(c['_control'])/'latest'
        if args.out:
            target=Path(args.out).expanduser().resolve()
            destination,digest=export_campaign(source,target)
            print('AUDIT_EXPORT='+str(destination),flush=True)
            print('SHA256='+digest,flush=True)
        else:
            c=load_config(tool,args.root,args.config)
            _,current=publish_private_bundle(source,Path(c['_control']))
            print('AUDIT_EXPORT='+str(current),flush=True)
        return 0
    if args.action=='_worker':
        if not args.id or not args.run_id or not args.run_root:p.error('worker requires --id/--run-id/--run-root')
        meta=next((m for m in load_manifest(tool)['levels'] if m['id']==args.id),None)
        if meta is None:p.error('unknown level')
        c=load_config(tool,args.root,args.config)
        result=runner.worker(tool,meta,c,args.run_root,args.run_id,
                             args.network,args.remote,args.ack_remote,
                             integral=args.integral_worker,runtime_local=args.runtime_local,
                             runtime_world=args.world,runtime_audit=args.audit_root,
                             start_test_stack=args.start_test_stack)
        return 0 if result['verdict'] not in ('ERROR','INFRA_ERROR','CONFIG_ERROR') else 30
    summary,path=runner.campaign(tool,args.selection,args.root,args.config,jobs=args.jobs,
                                  allow_network=args.network,allow_remote=args.remote,ack_remote=args.ack_remote,
                                  notify=lambda s:print(s,flush=True),runtime_local=args.runtime_local,
                                  audit=args.audit,audit_root=args.audit_root,runtime_world=args.world,
                                  start_test_stack=args.start_test_stack)
    print('SUMMARY='+str(path/'summary.json'),flush=True)
    verdict = {'PASS':0,'WARN':0,'FAIL':10,'BLOCKED':20,'PARTIAL':21,'ERROR':30}.get(summary['verdict'],30)
    audit_result = path/'audit-import.json'
    if audit_result.is_file() and read_json(audit_result)['status'] != 'IMPORTED':
        return verdict or 31
    return verdict
