#!/usr/bin/env python3
"""Safe local C0 restart planner / best-effort supervisor (Python standard library).

Only touches explicitly registered C0 endpoints. Does not kill by port, install
packages, change .env, or touch remote/docker volumes. Manual-only sub-stacks
are reported as such, not silently started.
"""
from __future__ import annotations
import argparse
import ctypes
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time

from koa_ecosystem_diag.port_diagnostics import read_registry, REGISTRY_REL

BASE = Path(os.environ.get('KOA_REPOS_ROOT', r'C:\mycode'))
REGISTRY = BASE / REGISTRY_REL
STATE_DIR = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'kOA' / 'C0-reboot'
STATE_FILE = STATE_DIR/'managed-processes.json'
LOGS = STATE_DIR/'logs'

GROUPS = {
 'orgo': {'ids':['orgo-web','orgo-api'], 'path':'Orgo/Orgo', 'mode':'docker'},
 'orgo-worlds': {'ids':['orgo-worlds-web','orgo-worlds-api'], 'path':'Orgo/Orgo_Worlds', 'mode':'worlds'},
 'initkoa': {'ids':['initkoa-web'], 'path':'HomePage/HomePage', 'mode':'homepage'},
 'konnaxion': {'ids':['konnaxion-web','konnaxion-api'], 'path':'Konnaxion/Konnaxion', 'mode':'konnaxion'},
 'konnaxion-capsule': {'ids':['konnaxion-capsule-agent-local','konnaxion-capsule-manager-local'], 'path':'Konnaxion/Konnaxion_Capsule_Manager', 'mode':'manual', 'why':'Agent et Manager : lancement interactif via StartCapsuleManager.bat (peut interagir avec des instances externes).'},
 'koali-integre': {'ids':['orgo-koali-web','orgo-koali-api','orgo-koali-pglite','konnaxion-koali-web','konnaxion-koali-api','koali-spaces-web'], 'path':'kOA-Linux/koali-spaces', 'mode':'manual', 'why':'Koali lance plusieurs processus enfants via RUN_KOALI_ECOSYSTEM.cmd ; arrêter/recréer les processus individuellement serait dangereux. Utiliser son orchestrateur propre.'},
 'skope': {'ids':['skope-web'], 'path':'Skope/Skope', 'mode':'skope'},
 'ekole-quebec': {'ids':['ekole-quebec-learner','ekole-quebec-teacher'], 'path':'Ekole/ekole', 'mode':'ekole-quebec'},
 'ekole-opsconsole': {'ids':['ekole-opsconsole'], 'path':'Ekole/ekole', 'mode':'manual', 'why':'OpsConsole héritée : le lanceur et les dépendances n’ont pas été validés dans la vague 1. Ne pas démarrer sur une commande supposée.'},
 'ekole-pastorale': {'ids':['ekole-pastorale-learner','ekole-pastorale-teacher'], 'path':'Ekole/ecole-pastorale', 'mode':'ekole-pastorale'},
}

def now():
 return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')

def state_load():
 try: return json.loads(STATE_FILE.read_text(encoding='utf-8'))
 except (FileNotFoundError, ValueError): return {'schema':1,'processes':[]}

def state_save(state):
 STATE_DIR.mkdir(parents=True, exist_ok=True)
 tmp=STATE_FILE.with_suffix('.tmp')
 tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 os.replace(tmp,STATE_FILE)

def load_registry():
 """Load the C0 source of truth (never a copied or fallback list)."""
 path, document = read_registry(BASE, explicit=REGISTRY)
 services = {entry['id']: entry for entry in document['services']}
 listed = [sid for group in GROUPS.values() for sid in group['ids']]
 if len(listed) != len(set(listed)) or set(listed) != set(services):
  raise RuntimeError('Le plan de redemarrage ne correspond pas au registre C0: services manquants ou en trop.')
 return services

def check_port(port,timeout=0.25):
 try:
  with socket.create_connection(('127.0.0.1',port),timeout=timeout): return True
 except (OSError,TimeoutError): return False

# Attendre les services réellement accessibles avant de déclarer le démarrage
# réussi. Le précédent superviseur renvoyait code 0 juste après Popen et l'UI
# lançait l'audit ~3 s après, avant le Ready de Next.js (4 à 6 s).
READINESS_TIMEOUT_SECONDS = 75.0
READINESS_POLL_SECONDS = 0.5


def wait_for_ports(ports, *, timeout=READINESS_TIMEOUT_SECONDS,
                   interval=READINESS_POLL_SECONDS, check=None, clock=None, sleep=None):
 """Wait for all assigned TCP listeners, with a bounded deadline.

 This is *readiness at the TCP level*, not proof of service identity,
 HTTP health or authenticated Interaction Kernel functionality.
 """
 check = check or check_port
 clock = clock or time.monotonic
 sleep = sleep or time.sleep
 if not ports:
  raise ValueError('Aucun port attribué à vérifier')
 if timeout <= 0 or interval <= 0:
  raise ValueError('Délai de disponibilité invalide')
 start = clock()
 deadline = start + timeout
 pending = dict(ports)
 ever_open = set()
 # Two consecutive samples reduce transient false positive connections.
 consecutive = {sid: 0 for sid in ports}
 print('  Attente de disponibilité C0 : ' +
       ', '.join(f'{sid}={port}' for sid, port in ports.items()) +
       f' (max {timeout:.0f}s)', flush=True)
 while True:
  for sid, port in ports.items():
   is_open = bool(check(port))
   consecutive[sid] = consecutive[sid] + 1 if is_open else 0
   if consecutive[sid] >= 2:
    if sid not in ever_open:
     print(f'  TCP READY : {sid} sur 127.0.0.1:{port}', flush=True)
     ever_open.add(sid)
    pending.pop(sid, None)
   elif sid in ever_open:
    # A previously healthy endpoint must not be silently ignored if lost.
    ever_open.remove(sid)
    pending[sid] = port
  if not pending:
   elapsed = clock() - start
   print(f'  DISPONIBILITÉ TCP CONFIRMÉE : {len(ports)} port(s) '
         f'en {elapsed:.1f}s (identité/IK non vérifiés)', flush=True)
   return True
  remaining = deadline - clock()
  if remaining <= 0:
   print('  ECHEC DISPONIBILITÉ : '+', '.join(f'{sid}={port}'
         for sid, port in pending.items()), flush=True)
   return False
  sleep(min(interval, remaining))


def creation_time(pid):
 if os.name!='nt':
  try: return float(Path(f'/proc/{pid}').stat().st_ctime)
  except OSError: return None
 import ctypes.wintypes as w
 kernel=ctypes.WinDLL('kernel32',use_last_error=True)
 kernel.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];kernel.OpenProcess.restype=w.HANDLE
 kernel.GetProcessTimes.argtypes=[w.HANDLE,ctypes.POINTER(w.FILETIME),ctypes.POINTER(w.FILETIME),ctypes.POINTER(w.FILETIME),ctypes.POINTER(w.FILETIME)]
 kernel.GetProcessTimes.restype=w.BOOL
 h=kernel.OpenProcess(0x1000,False,pid)
 if not h: return None
 try:
  create=w.FILETIME();exit=w.FILETIME();kernel_t=w.FILETIME();user=w.FILETIME()
  if not kernel.GetProcessTimes(h,ctypes.byref(create),ctypes.byref(exit),ctypes.byref(kernel_t),ctypes.byref(user)): return None
  return str((create.dwHighDateTime<<32)|create.dwLowDateTime)
 finally: kernel.CloseHandle(h)

def owned(rec):
 if not rec.get('pid') or not rec.get('created'):return False
 actual=creation_time(int(rec['pid']))
 return actual is not None and str(actual)==str(rec['created'])

def require_cmd(name):
 cmd=shutil.which(name)
 if not cmd: raise RuntimeError(f'Commande manquante : {name}')
 return cmd

def ensure_file(path):
 if not path.is_file(): raise RuntimeError(f'Fichier requis absent : {path}')
 return path

def ensure_dir(path):
 if not path.is_dir(): raise RuntimeError(f'Dossier requis absent : {path}')
 return path

def build_commands(group,ports):
 """Return runnable command specifications; no installers, mutations or remote actions."""
 g=GROUPS[group];repo=ensure_dir(BASE/Path(g['path'])); mode=g['mode']
 if mode=='manual': raise RuntimeError('Démarrage manuel requis: '+g['why'])
 if mode=='docker':
  ensure_file(repo/'docker-compose.yml');ensure_file(repo/'.env')
  require_cmd('docker.exe' if os.name=='nt' else 'docker')
  # docker Compose controls only containers belonging to this compose file.
  return [{'kind':'docker','cwd':str(repo),'ports':ports}]
 if mode=='homepage':
  ensure_file(repo/'package.json');ensure_dir(repo/'node_modules')
  npm=require_cmd('npm.cmd' if os.name=='nt' else 'npm')
  return [{'kind':'process','cmd':[npm,'run','dev'],'cwd':str(repo),'env':{},'ports':ports,'label':'initkoa'}]
 if mode=='konnaxion':
  front=repo/'frontend';back=repo/'backend'
  ensure_dir(front/'node_modules');python=ensure_file(back/'.venv'/'Scripts'/'python.exe') if os.name=='nt' else ensure_file(back/'.venv'/'bin'/'python')
  ensure_file(back/'manage.py')
  pnpm=require_cmd('pnpm.cmd' if os.name=='nt' else 'pnpm')
  commands=[
   {'kind':'process','cmd':[str(python),'-m','uvicorn','config.asgi:application','--host','127.0.0.1','--port',str(ports['konnaxion-api'])], 'cwd':str(back), 'env':{'DJANGO_SETTINGS_MODULE':'config.settings.local'},'ports':{'konnaxion-api':ports['konnaxion-api']},'label':'konnaxion-api'},
   {'kind':'process','cmd':[pnpm,'exec','next','dev','--turbo','--hostname','127.0.0.1','-p',str(ports['konnaxion-web'])], 'cwd':str(front), 'env':{'NEXT_PUBLIC_KONNAXION_UNIVERSE_BASE_DOMAIN':'localhost','NEXT_PUBLIC_API_BASE':'/api','API_PROXY_BASE':f"http://127.0.0.1:{ports['konnaxion-api']}/api"},'ports':{'konnaxion-web':ports['konnaxion-web']},'label':'konnaxion-web'}]
  return commands
 if mode=='worlds':
  ensure_dir(repo/'node_modules');npm=require_cmd('npm.cmd' if os.name=='nt' else 'npm');npx=require_cmd('npx.cmd' if os.name=='nt' else 'npx')
  return [
   {'kind':'process','cmd':[npm,'run','dev:api'],'cwd':str(repo),'env':{},'ports':{'orgo-worlds-api':ports['orgo-worlds-api']},'label':'orgo-worlds-api'},
   {'kind':'process','cmd':[npx,'next','dev','apps/web','--hostname','127.0.0.1','-p',str(ports['orgo-worlds-web'])],'cwd':str(repo),'env':{},'ports':{'orgo-worlds-web':ports['orgo-worlds-web']},'label':'orgo-worlds-web'}]
 if mode=='skope':
  py=Path(os.environ.get('LOCALAPPDATA',''))/'Programs'/'Python'/'Python312'/'python.exe'
  if not py.is_file(): raise RuntimeError(f'Python Skope 3.12 absent : {py}')
  db=Path(r'D:\EncyKlopedia\30_working\wikidata\wikidata.compact.sqlite')
  ensure_file(db)
  return [{'kind':'process','cmd':[str(py),'-u','-m','skope','serve','--port',str(ports['skope-web']),'--db',str(db)],'cwd':str(repo),'env':{},'ports':ports,'label':'skope'}]
 if mode=='ekole-quebec':
  core=repo;content=ensure_dir(BASE/'Ekole'/'ekole-quebec');ensure_file(content/'pack.json');launch=ensure_file(core/'launcher.py')
  return [{'kind':'process','cmd':[sys.executable,str(launch),'--contenu',str(content),'--port',str(ports['ekole-quebec-learner']),'--port-editeur',str(ports['ekole-quebec-teacher'])], 'cwd':str(core),'env':{},'ports':ports,'label':'ekole-quebec'}]
 if mode=='ekole-pastorale':
  core=ensure_dir(BASE/'Ekole'/'ekole');launch=ensure_file(repo/'demarrer_pastorale.py');ensure_file(repo/'pack.json')
  return [{'kind':'process','cmd':[sys.executable,str(launch),'--sans-navigateur','--port',str(ports['ekole-pastorale-learner']),'--port-editeur',str(ports['ekole-pastorale-teacher'])], 'cwd':str(repo),'env':{},'ports':ports,'label':'ekole-pastorale'}]
 raise RuntimeError('Mode non pris en charge: '+mode)

def managed_for(state,group):
 return [r for r in state['processes'] if r.get('group')==group and owned(r)]

def run_docker(spec,restart=False):
 repo=spec['cwd']
 cmd=['docker','compose','-f','docker-compose.yml']
 if restart:
  # Only the Orgo compose project. Never docker compose down -v.
  r=subprocess.run([*cmd,'restart'],cwd=repo,check=False)
  if r.returncode!=0: print('[ORGO] restart renvoie un code non nul, tentative up -d')
 r=subprocess.run([*cmd,'up','-d'],cwd=repo,check=False)
 if r.returncode:raise RuntimeError(f'Docker compose up -d a echoue ({r.returncode})')

def launch_process(spec,group,state):
 LOGS.mkdir(parents=True,exist_ok=True)
 logname=group+'--'+spec['label']+'--'+dt.datetime.now().strftime('%Y%m%d-%H%M%S')+'.log'
 log=LOGS/logname
 env=os.environ.copy();env.update(spec['env'])
 flags=getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0) if os.name=='nt' else 0
 with log.open('ab') as out:
  proc=subprocess.Popen(spec['cmd'],cwd=spec['cwd'],env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT,creationflags=flags)
 created=creation_time(proc.pid)
 if created is None: raise RuntimeError(f'Processus disparu au démarrage: {spec["label"]}; consulter {log}')
 state['processes'].append({'group':group,'label':spec['label'],'pid':proc.pid,'created':str(created),'log':str(log),'ports':list(spec['ports'].values()),'launched_at':now()})
 state_save(state)
 print(f'  {spec["label"]} : PID {proc.pid} ; journal {log}')

def stop_group(group,state,force_owned=False):
 records=[r for r in state['processes'] if r.get('group')==group]
 remaining=[]
 for rec in records:
  if not owned(rec):
   print(f'  {rec["label"]}: suivi expiré, aucun arrêt (PID non vérifié)')
   continue
  pid=int(rec['pid'])
  print(f'  Arrêt contrôlé {rec["label"]} PID {pid}')
  if os.name=='nt':
   try: os.kill(pid,signal.CTRL_BREAK_EVENT)
   except OSError: pass
  else:
   try: os.kill(pid,signal.SIGTERM)
   except OSError: pass
  for _ in range(12):
   if not owned(rec):break
   time.sleep(0.25)
  if owned(rec):
   if force_owned:
    if not owned(rec): continue
    subprocess.run(['taskkill','/PID',str(pid),'/T','/F'] if os.name=='nt' else ['kill','-9',str(pid)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
    if owned(rec): remaining.append(rec)
   else:
    print('  Arrêt non confirmé ; relancer avec --force-owned UNIQUEMENT si ce PID est bien à vous.')
    remaining.append(rec)
 state['processes']=[r for r in state['processes'] if r.get('group')!=group]+remaining
 state_save(state)
 return not remaining

def run_action(args,services):
 state=state_load()
 if args.command=='status':
  result=[]
  for group,g in GROUPS.items():
   tracked=len(managed_for(state,group))
   for sid in g['ids']:
    p=services[sid]['port'];is_open=check_port(p)
    st='OUVERT_NON_IDENTIFIE' if is_open else 'SANS_REPONSE'
    print(f'{p:5d} {sid:38s} {st}'+(f'  suivi={tracked}' if tracked else ''))
    result.append({'id':sid,'port':p,'tcp':is_open,'status':st,'managed_processes_in_group':tracked})
  STATE_DIR.mkdir(parents=True,exist_ok=True)
  report=STATE_DIR/'dernier-statut.json'
  report.write_text(json.dumps({'date':now(),'registry':str(REGISTRY),'services':result},indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
  print('Rapport:',report)
  return 0
 selected=list(GROUPS) if args.all else ['orgo','konnaxion','initkoa']
 if args.groups: selected=[s.strip() for s in args.groups.split(',') if s.strip()]
 unknown=set(selected)-set(GROUPS)
 if unknown: raise RuntimeError('Groupe(s) inconnus : '+', '.join(sorted(unknown)))
 if args.command=='plan':
  print('Registre :',REGISTRY)
  for group in selected:
   g=GROUPS[group]
   ports=', '.join(str(services[s]['port']) for s in g['ids'])
   label='MANUEL' if g['mode']=='manual' else 'AUTOMATISABLE (prerequis requis)'
   print(f' - {group:20s} {ports:24s} {label}')
   if g['mode']=='manual':print('   ',g['why'])
  print('\nAucun processus n’a été modifié.')
  return 0
 if os.name!='nt':raise RuntimeError('Démarrage/arrêt réservés à Windows. Utiliser plan/status sur d’autres OS.')
 if args.command in ('start','restart'):
  failures=[]
  for group in selected:
   g=GROUPS[group]
   ports={s:services[s]['port'] for s in g['ids']}
   print(f'\n== {group} ==')
   if g['mode']=='manual':
    print('MANUEL :',g['why']);continue
   try:
    specs=build_commands(group,ports)
    if g['mode']=='docker':
     run_docker(specs[0],restart=args.command=='restart')
     print('  Docker Compose démarré/redémarré sans suppression de volumes.', flush=True)
     if not wait_for_ports(ports):
      print('  ECHEC : les ports Docker attendus ne sont pas disponibles.', flush=True)
      failures.append(group)
     continue
    if args.command=='restart':
     if not stop_group(group,state,force_owned=args.force_owned):
      print('  REFUS : ancien processus suivi encore actif');failures.append(group);continue
    if managed_for(state,group):
     print('  Déjà supervisé, pas de doublon.', flush=True)
     if not wait_for_ports(ports, timeout=15.0):
      print('  ECHEC : processus suivi mais port inaccessible ; essayer Redémarrer.', flush=True)
      failures.append(group)
     continue
    busy={sid:p for sid,p in ports.items() if check_port(p)}
    if busy:
     print('  REFUS : ports occupés mais identité non prouvée :',busy)
     failures.append(group);continue
    for spec in specs:launch_process(spec,group,state)
    # Aucune réussite sans preuve que les ports du groupe écoutent.
    # L'audit automatique de l'interface ne commencera qu'à la fin de cette attente.
    if not wait_for_ports(ports):
     print('  ECHEC : lancement demandé, mais service non joignable dans le délai. '
           'Consulter les journaux C0-reboot/logs.', flush=True)
     failures.append(group)
   except (RuntimeError,OSError,subprocess.SubprocessError) as exc:
    print('  ECHEC :',exc);failures.append(group)
  manual=[group for group in selected if GROUPS[group]['mode']=='manual']
  print('\nBilan: groupes manuels =', len(manual),'; groupes en erreur =',len(failures))
  if manual: print('A relancer via leurs lanceurs propriétaires :',', '.join(manual))
  print('Terminé. Disponibilité TCP des groupes lancés vérifiée; identité/IK à contrôler séparément.', flush=True)
  return 2 if failures else 0
 if args.command=='stop':
  for group in selected:
   g=GROUPS[group]
   if g['mode']=='docker':
    print(f'{group}: aucun arrêt automatique Docker Compose (risque de perturber les dépendances).')
    continue
   stop_group(group,state,force_owned=args.force_owned)
  return 0
 raise RuntimeError('Commande non supportée')

def main(argv=None):
 p=argparse.ArgumentParser(description='C0 ports: plan, status, start, restart (managed only), stop')
 p.add_argument('command',choices=['plan','status','start','restart','stop'])
 p.add_argument('--all',action='store_true',help='Inclure tous les groupes C0 (groupes manuels seulement signalés)')
 p.add_argument('--groups',help='Liste de groupes séparés par une virgule')
 p.add_argument('--force-owned',action='store_true',help='Réservé au CLI; interdit dans l’interface kOADiag')
 p.add_argument('--root', help='Racine C0 contenant tous les dépôts, ex. C:\\mycode')
 args=p.parse_args(argv)
 global BASE, REGISTRY
 if args.root:
  BASE=Path(args.root).expanduser().resolve()
  REGISTRY=BASE / REGISTRY_REL
 try:return run_action(args,load_registry())
 except (RuntimeError,ValueError,KeyError,json.JSONDecodeError) as ex:
  print('ERREUR DE SECURITE:',ex,file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
