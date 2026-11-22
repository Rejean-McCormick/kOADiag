# -*- coding: utf-8 -*-
"""Diagnostic du kOA Digital Ecosystem — GUI LevelUpDiag-style; Python 3.10+, Tkinter."""
from __future__ import annotations
import csv
import json
import os
from pathlib import Path
from datetime import datetime, timezone
import base64
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from koa_ecosystem_diag import VERSION
from koa_ecosystem_diag.framework import load_manifest,load_config,read_json
from koa_ecosystem_diag.audit_export import export_campaign
from koa_ecosystem_diag import boundary_registry as registry
from koa_ecosystem_diag import port_diagnostics
from koa_ecosystem_diag.evidence_adapters import load as load_evidence

HERE=Path(__file__).resolve().parent
BRAND='#1E6864';BRAND_DARK='#154f4c';BRAND_DEEP='#0f3c3a';BRAND_SOFT='#dfeeee';BRAND_ACCENT='#7dc9c5';BG='#f3f7f6';INK='#173338';MUTED='#5e7476'
GREEN='#178755';RED='#c12f39';AMBER='#b06b0c';GREY='#6f8295';WHITE='#ffffff'


def code_color(status):
    return {'PASS':GREEN,'WARN':AMBER,'FAIL':RED,'SKIP':GREY,'BLOCKED':AMBER,
            'PARTIAL':AMBER,'ERROR':RED,'INFRA_ERROR':RED,'CONFIG_ERROR':RED}.get(status,INK)


def python_console():
    exe=Path(sys.executable)
    if exe.name.lower()=='pythonw.exe':
        c=exe.with_name('python.exe')
        if c.exists():return str(c)
    return str(exe)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f'Diagnostic du kOA Digital Ecosystem  |  v{VERSION}')
        self.geometry('1440x900');self.minsize(1040,650)
        self.configure(bg=BG)
        self.logo_image=None;self.icon_image=None
        self.theme()
        self.load_brand_assets()
        self.q=queue.Queue();self.process=None;self.running=False;self.run_root=None
        self.summary=None;self.snapshot=None;self.results={};self.relation_rows=[]
        self.manifest=load_manifest(HERE)
        self.campaigns=self.manifest['campaigns']
        self.rootvar=tk.StringVar(value=r'C:\mycode')
        self.campaignvar=tk.StringVar(value='validation-integrale')
        self.network=tk.BooleanVar(value=False);self.remote=tk.BooleanVar(value=False)
        self.ack_remote=tk.BooleanVar(value=False)
        self.runtime_local=tk.BooleanVar(value=False)
        self.audit_enabled=tk.BooleanVar(value=True)
        self.audit_dir=tk.StringVar()
        self.runtime_world=tk.StringVar(value='fp-electromecanique-informatique')
        self.filter=tk.StringVar();self.filter.trace_add('write',lambda *_:self.render_relations())
        self.historyvar=tk.StringVar();self.level_filter=tk.StringVar(value='Tous')
        self.registry_filter=tk.StringVar()
        self.registry_filter.trace_add('write',lambda *_: self.render_registry())
        self.boundary_proof_rows={}
        self.ports_running=False;self.ports_last_folder=None
        self.reboot_running=False;self.reboot_scope=tk.StringVar(value='Essentiels')
        self.reboot_action=tk.StringVar(value='Redémarrer')
        self.make_ui();self.refresh_history();self.render_registry();self.render_evidence_imports()
        self.after(130,self.drain)
        self.protocol('WM_DELETE_WINDOW',self.close_checked)
        self.after(160,self.refresh_ports_catalog)

    def load_brand_assets(self):
        assets=HERE/'assets'
        # White mark is legible on dark brand header; brand-colored variant is
        # reserved for the native window icon. Keep refs alive for Tkinter.
        for path,attribute in ((assets/'uckk-logo-header.png','logo_image'),
                               (assets/'uckk-logo-64.png','icon_image')):
            try:
                if path.is_file():setattr(self,attribute,tk.PhotoImage(file=str(path)))
            except (tk.TclError,OSError):pass
        if self.icon_image is not None:
            try:self.iconphoto(True,self.icon_image)
            except tk.TclError:pass

    def theme(self):
        s=ttk.Style(self)
        if 'clam' in s.theme_names():s.theme_use('clam')
        s.configure('TNotebook',background=BG,borderwidth=0)
        s.configure('TNotebook.Tab',font=('Segoe UI',9,'bold'),padding=(9,9),background='#dce8f2',foreground=INK)
        s.map('TNotebook.Tab',background=[('selected','#fff')],foreground=[('selected',BRAND)])
        s.configure('Treeview',font=('Segoe UI',9),rowheight=27,background='#fff',fieldbackground='#fff',foreground=INK,borderwidth=0)
        s.configure('Treeview.Heading',font=('Segoe UI',9,'bold'),background='#e6eef6',foreground=INK,padding=7)
        s.map('Treeview',background=[('selected','#d5efed')],foreground=[('selected',INK)])
        s.configure('TCombobox',font=('Segoe UI',10),padding=5)
        s.configure('Horizontal.TProgressbar',troughcolor='#dce8f2',background=BRAND,thickness=8)

    def label(self,parent,text,**kw):
        return tk.Label(parent,text=text,font=kw.pop('font',('Segoe UI',10)),bg=kw.pop('bg','#fff'),fg=kw.pop('fg',INK),**kw)

    def button(self,parent,text,cmd,bg=BRAND,fg='#fff'):
        active = BRAND_ACCENT if bg not in ('#dce9f4','#dce8f2',BRAND_SOFT) else '#cfe3e2'
        return tk.Button(parent,text=text,command=cmd,bg=bg,fg=fg,activebackground=active,
            activeforeground=BRAND_DEEP,relief='flat',bd=0,cursor='hand2',font=('Segoe UI',10,'bold'),padx=17,pady=9)

    def make_ui(self):
        head=tk.Frame(self,bg=BRAND_DEEP,height=118);head.pack(fill='x');head.pack_propagate(False)
        brand=tk.Frame(head,bg=BRAND_DEEP);brand.pack(side='left',fill='y',padx=(24,18),pady=14)
        if self.logo_image is not None:
            tk.Label(brand,image=self.logo_image,bg=BRAND_DEEP).pack(side='left',padx=(0,18))
        else:
            tk.Label(brand,text='kOA',bg=BRAND_DEEP,fg=BRAND_ACCENT,font=('Segoe UI',24,'bold')).pack(side='left',padx=(0,18))
        b=tk.Frame(brand,bg=BRAND_DEEP);b.pack(side='left',fill='y')
        tk.Label(b,text='DIAGNOSTIC DU kOA DIGITAL ECOSYSTEM',bg=BRAND_DEEP,fg='white',font=('Segoe UI',19,'bold')).pack(anchor='w')
        tk.Label(b,text='Relations inter-repos • Architecture LevelUpDiag • 13 niveaux isolés • Aucune suite interne exécutée',
                 bg=BRAND_DEEP,fg='#c4dddc',font=('Segoe UI',10)).pack(anchor='w',pady=(5,0))
        self.verdict=tk.Label(head,text='NON EXÉCUTÉ',bg=BRAND_DARK,fg='#f2d5a1',font=('Segoe UI',11,'bold'),padx=20,pady=12)
        self.verdict.pack(side='right',padx=26)

        ctrl=tk.Frame(self,bg='#fff',highlightbackground='#d2e0ee',highlightthickness=1)
        ctrl.pack(fill='x',padx=23,pady=(16,8))
        strip=tk.Frame(ctrl,bg='#fff');strip.pack(fill='x',padx=16,pady=(13,6))
        self.label(strip,'RACINE DES DÉPÔTS',fg=MUTED).grid(row=0,column=0,sticky='w')
        self.label(strip,'CAMPAGNE',fg=MUTED).grid(row=0,column=2,sticky='w',padx=(15,0))
        e=tk.Entry(strip,textvariable=self.rootvar,relief='solid',bd=1,font=('Consolas',10),fg=INK)
        e.grid(row=1,column=0,sticky='ew',ipady=8,pady=6)
        self.button(strip,'…',self.choose_root,bg=BRAND_SOFT,fg=INK).grid(row=1,column=1,padx=(7,0))
        cb=ttk.Combobox(strip,textvariable=self.campaignvar,values=list(self.campaigns),state='readonly',width=24)
        cb.grid(row=1,column=2,sticky='ew',padx=(15,0))
        strip.columnconfigure(0,weight=4);strip.columnconfigure(2,weight=1)
        actions=tk.Frame(ctrl,bg='#fff');actions.pack(fill='x',padx=16,pady=(0,13))
        self.runbtn=self.button(actions,'LANCER LA CAMPAGNE',self.start,bg=BRAND)
        self.runbtn.pack(side='left')
        self.button(actions,'OUVRIR LES RAPPORTS',self.open_reports,bg=BRAND_SOFT,fg=INK).pack(side='left',padx=(9,0))
        self.button(actions,'RECHARGER L’HISTORIQUE',self.refresh_history,bg=BRAND_SOFT,fg=INK).pack(side='left',padx=(9,0))
        self.button(actions,'CONFIG E2E',self.open_local_config,bg=BRAND_SOFT,fg=INK).pack(side='left',padx=(9,0))
        self.button(actions,'EXPORT AUDIT',self.export_audit_gui,bg=BRAND_SOFT,fg=INK).pack(side='left',padx=(9,0))
        tk.Checkbutton(actions,text='Sondes API locales',variable=self.network,command=self.update_remote,
            bg='#fff',fg=INK,selectcolor='#fff',font=('Segoe UI',10)).pack(side='left',padx=(22,0))
        tk.Checkbutton(actions,text='Sondes distantes',variable=self.remote,command=self.update_remote,
            bg='#fff',fg=INK,selectcolor='#fff',font=('Segoe UI',10)).pack(side='left',padx=(10,0))
        self.remote_box=tk.Checkbutton(actions,text='J’autorise explicitement les GET/HEAD distants',variable=self.ack_remote,
            bg='#fff',fg=INK,selectcolor='#fff',font=('Segoe UI',9))
        self.remote_box.pack(side='left',padx=(10,0))
        local=tk.Frame(ctrl,bg='#fff');local.pack(fill='x',padx=16,pady=(0,8))
        tk.Checkbutton(local,text='Read private evidence and import results into GitHub Audit',
            variable=self.audit_enabled,bg='#fff',fg=INK).grid(row=0,column=0,sticky='w')
        ttk.Entry(local,textvariable=self.audit_dir,width=45).grid(row=0,column=1,sticky='ew',padx=8)
        self.button(local,'Audit folder…',self.choose_audit,bg=BRAND_SOFT,fg=INK).grid(row=0,column=2)
        tk.Checkbutton(local,text='Start local Docker test stack and run Konnaxion–Orgo (creates test data)',
            variable=self.runtime_local,bg='#fff',fg=INK).grid(row=1,column=0,sticky='w')
        ttk.Entry(local,textvariable=self.runtime_world,width=45).grid(row=1,column=1,sticky='ew',padx=8)
        ttk.Label(local,text='Test World').grid(row=1,column=2,sticky='w')
        local.columnconfigure(1,weight=1)
        tk.Frame(self,bg=BG,height=5).pack(fill='x')

        stats=tk.Frame(self,bg=BG);stats.pack(fill='x',padx=23,pady=(0,12))
        self.stats={}
        for i,(key,title) in enumerate([('repos','DÉPÔTS ACCESSIBLES'),('relations','RELATIONS CARTOGRAPHIÉES'),
                                         ('proven','ÉCHANGES CORRÉLÉS'),('journeys','PARCOURS CORROBORÉS'),('levels','NIVEAUX TERMINÉS')]):
            box=tk.Frame(stats,bg='#fff',highlightbackground='#d2e0ee',highlightthickness=1)
            box.grid(row=0,column=i,sticky='nsew',padx=(0,8) if i<4 else 0)
            stats.columnconfigure(i,weight=1)
            self.label(box,title,bg='#fff',fg=MUTED,font=('Segoe UI',9,'bold')).pack(anchor='w',padx=17,pady=(10,0))
            num=self.label(box,'—',bg='#fff',fg=BRAND,font=('Segoe UI',22,'bold'))
            num.pack(anchor='w',padx=17,pady=(0,10))
            self.stats[key]=num
        bar=tk.Frame(self,bg=BG);bar.pack(fill='x',padx=23,pady=(0,7))
        self.progress=ttk.Progressbar(bar,mode='determinate',maximum=len(self.manifest['levels']))
        self.progress.pack(fill='x',side='left',expand=True)
        self.progress_text=self.label(bar,'Prêt à analyser',bg=BG,fg=MUTED,font=('Segoe UI',9))
        self.progress_text.pack(side='right',padx=(15,0))

        self.tabs=ttk.Notebook(self)
        self.tabs.pack(fill='both',expand=True,padx=23,pady=(0,16))
        self.tab_overview=tk.Frame(self.tabs,bg='#fff');self.tab_levels=tk.Frame(self.tabs,bg='#fff')
        self.tab_rel=tk.Frame(self.tabs,bg='#fff');self.tab_registry=tk.Frame(self.tabs,bg='#fff');self.tab_journeys=tk.Frame(self.tabs,bg='#fff')
        self.tab_boundary_evidence=tk.Frame(self.tabs,bg='#fff');self.tab_imports=tk.Frame(self.tabs,bg='#fff')
        self.tab_evidence=tk.Frame(self.tabs,bg='#fff');self.tab_history=tk.Frame(self.tabs,bg='#fff')
        self.tab_console=tk.Frame(self.tabs,bg='#fff')
        self.tab_ports=tk.Frame(self.tabs,bg='#fff')
        for frame,name in ((self.tab_overview,'Synthèse'),(self.tab_ports,'Ports C0'),(self.tab_levels,'Niveaux LevelUpDiag'),
                           (self.tab_rel,'Relations inter-repos'),(self.tab_registry,'Registre des frontières'),(self.tab_journeys,'Parcours E2E'),
                           (self.tab_boundary_evidence,'Matrice de preuves'),(self.tab_imports,'Exports de traces'),
                           (self.tab_evidence,'Constats et preuves'),(self.tab_history,'Historique'),
                           (self.tab_console,'Journal d’exécution')):
            self.tabs.add(frame,text=name)
        self.make_overview();self.make_ports();self.make_levels();self.make_relations();self.make_registry();self.make_journeys()
        self.make_boundary_evidence();self.make_imports();self.make_evidence();self.make_history();self.make_console()
        for row in self.manifest['levels']:
            self.level_tree.insert('', 'end',iid=row['id'],values=(row['id'],row['name'],'À exécuter','OUI' if row['required'] else 'NON'))
        self.footer=self.label(self,'Campagnes : lecture seule sauf opt-in • Ports C0 : redémarrage local sur confirmation • v5.5.4',
                               bg=BG,fg=MUTED,font=('Segoe UI',9))
        self.footer.pack(anchor='w',padx=24,pady=(0,9))

    def tree(self,parent,columns,widths,stretch=None):
        container=tk.Frame(parent,bg='#fff');container.pack(fill='both',expand=True,padx=13,pady=12)
        tree=ttk.Treeview(container,columns=columns,show='headings',selectmode='browse')
        for col,w in zip(columns,widths):
            tree.heading(col,text=col)
            tree.column(col,width=w,minwidth=70,stretch=(col in (stretch or [])))
        y=ttk.Scrollbar(container,orient='vertical',command=tree.yview)
        x=ttk.Scrollbar(container,orient='horizontal',command=tree.xview)
        tree.configure(yscrollcommand=y.set,xscrollcommand=x.set)
        tree.grid(row=0,column=0,sticky='nsew');y.grid(row=0,column=1,sticky='ns');x.grid(row=1,column=0,sticky='ew')
        container.rowconfigure(0,weight=1);container.columnconfigure(0,weight=1)
        for status in ('PASS','WARN','FAIL','SKIP','BLOCKED','PARTIAL','ERROR','INFRA_ERROR'):
            tree.tag_configure(status,foreground=code_color(status))
        return tree

    def make_overview(self):
        panel=tk.Frame(self.tab_overview,bg='#fff');panel.pack(fill='both',expand=True,padx=25,pady=19)
        tk.Label(panel,text='ÉTAT DE LA CONTINUITÉ INTER-REPOS',font=('Segoe UI',16,'bold'),
                 bg='#fff',fg=BRAND).pack(anchor='w')
        self.overview_status=self.label(panel,'Aucune campagne chargée',bg='#fff',fg=MUTED,font=('Segoe UI',12,'bold'))
        self.overview_status.pack(anchor='w',pady=(12,4))
        self.overview_e2e=self.label(panel,'E2E GLOBAL : NON CERTIFIÉ',bg='#fff',fg=AMBER,font=('Segoe UI',12,'bold'))
        self.overview_e2e.pack(anchor='w',pady=(1,12))
        self.overview_text=tk.Text(panel,wrap='word',font=('Segoe UI',11),bg='#f3f9f8',fg=INK,
                                   padx=20,pady=18,borderwidth=0,highlightthickness=0)
        self.overview_text.pack(fill='both',expand=True)
        self.overview_text.insert('1.0','Lance une campagne pour obtenir le bilan de couverture, les priorités et la progression des preuves.\n\nUne réponse HTTP 200 ne prouve pas une transaction E2E. Les diagnostics internes restent hors périmètre.')
        self.overview_text.config(state='disabled')

    def make_journeys(self):
        row=tk.Frame(self.tab_journeys,bg='#fff');row.pack(fill='x',padx=16,pady=(12,0))
        self.label(row,'PARCOURS DÉCLARÉS — PREUVE DE CHAQUE FRONTIÈRE',fg=MUTED).pack(side='left')
        self.button(row,'DÉCLARER UN PARCOURS',self.create_journey,bg=BRAND_SOFT,fg=INK).pack(side='right')
        self.journey_tree=self.tree(self.tab_journeys,('Parcours','Chaîne','Sauts corroborés','État'),
                                     (160,560,155,220),['Chaîne'])
        self.journey_tree.bind('<<TreeviewSelect>>',self.on_journey)
        self.journey_rows=[]

    def create_journey(self):
        if self.running:messagebox.showwarning('Campagne','Attends la fin du diagnostic.');return
        name=simpledialog.askstring('Nouveau parcours','Identifiant unique (ex. konnaxion-orgo-retour) :',parent=self)
        if name is None:return
        import re
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{1,79}',name):
            messagebox.showerror('Identifiant','Utilise 2 à 80 caractères alphanumériques, points, tirets ou underscores.');return
        nodes=simpledialog.askstring('Chaîne E2E','Noms EXACTS des dépôts, séparés par des virgules.\nExemple : Konnaxion, Orgo, Konnaxion',parent=self)
        if nodes is None:return
        names=[x.strip() for x in nodes.split(',')]
        if not 2<=len(names)<=30 or any(not x for x in names):
            messagebox.showerror('Chaîne','Indique au moins 2 dépôts (maximum 30).');return
        try:
            path,local,_=self._local_evidence()
            journeys=local['interrepo'].setdefault('journeys',[])
            if not isinstance(journeys,list):raise ValueError('interrepo.journeys doit être une liste')
            if any(isinstance(x,dict) and x.get('id')==name for x in journeys):
                raise ValueError('Cet identifiant de parcours existe déjà')
            request_response=messagebox.askyesno('Type de parcours',
                'Exiger une réponse positive à chaque frontière ?\n\nOUI pour API request/response, NON pour événements pub/sub.',parent=self)
            mode=simpledialog.askstring('Mode E2E','autonome ou integre',initialvalue='autonome',parent=self)
            if mode is None:return
            if mode not in ('autonome','integre'):raise ValueError('Choisir autonome ou integre')
            refs=simpledialog.askstring('Contrats E2E',
                'Contrat exact de chaque saut, séparé par des virgules. Vide si aucun contrat nommé.',parent=self)
            if refs is None:return
            contracts=[part.strip() for part in refs.split(',')] if refs.strip() else ['']*(len(names)-1)
            if len(contracts)!=len(names)-1:raise ValueError('Un emplacement de contrat par saut est requis')
            journeys.append({'id':name,'enabled':True,'required':True,'nodes':names,'require_response':request_response,
                             'mode':mode,'contract_refs':contracts})
            self._save_local_evidence(path,local)
            self.log('Parcours déclaré (NON PROUVÉ) : '+name+' · '+' → '.join(names))
            messagebox.showinfo('Parcours enregistré','La chaîne est déclarée. Elle sera évaluée à la prochaine campagne E2E.\nAucune validation automatique.')
        except (ValueError,OSError,TypeError) as exc:messagebox.showerror('Parcours',str(exc))

    def on_journey(self,_=None):
        selected=self.journey_tree.selection()
        if not selected:return
        row=self.journey_rows[int(selected[0])]
        self.show_detail('Parcours '+row.get('id',''),json.dumps(row,ensure_ascii=False,indent=2))

    def render_journeys(self):
        self.journey_tree.delete(*self.journey_tree.get_children());self.journey_rows=[]
        if not self.snapshot:return
        for item in self.snapshot.get('journeys',[]):
            n=len(self.journey_rows);self.journey_rows.append(item)
            self.journey_tree.insert('','end',iid=str(n),values=(item['id'],
                ' → '.join(item.get('nodes',[])),str(item.get('verified_hops',0))+'/'+str(len(item.get('hops',[]))),(item.get('status','') + ' · ' + item.get('mode','non_renseigne'))))

    def render_overview(self):
        if not self.summary:return
        cover=self.summary.get('coverage') or {}
        inv=cover.get('inventory',{});api=cover.get('api',{});traces=cover.get('traces',{});journeys=cover.get('journeys',{})
        self.overview_status.config(text=f"Campagne {self.summary.get('run_id','?')} · Verdict {self.summary.get('verdict','?')}",fg=code_color(self.summary.get('verdict','WARN')))
        self.overview_e2e.config(text='E2E GLOBAL : NON CERTIFIÉ (preuves passives uniquement)',fg=AMBER)
        review=cover.get('boundary_registry',{})
        align=cover.get('inventory_alignment',{})
        matrix={}
        if self.run_root and (self.run_root/'boundary-qualification.json').is_file():
            try:matrix=read_json(self.run_root/'boundary-qualification.json').get('summary',{})
            except (ValueError,OSError,TypeError):pass
        closure = self.summary.get('cloture')
        full = self.summary.get('validation_integrale')
        lines = []
        if closure:
            modes = closure['mandatory_boundaries_by_mode']
            lines.append('Clôture · ' + closure['status'] + ' · ' + ' · '.join(
                f"{mode} {value['pass']}/{value['total']}" for mode, value in modes.items()))
        if full:
            lines.extend([f"Validation intégrale · {full['required_pass']}/{full['required_total']} contrôles obligatoires PASS",
                          'Détail des deux modes dans exports/validation-integrale.csv', ''])
        lines += [
            'COUVERTURE DE LA COLLECTE',
            f"  Dépôts : {inv.get('present','—')} / {inv.get('declared','—')} · scanners tronqués : {inv.get('truncated','—')}",
            f"  Relations documentées ou observées : {cover.get('relations','—')}",
            f"  Fichiers éligibles : {inv.get('eligible_files','—')} · analysés : {inv.get('scanned_files','—')} · non sélectionnés : {inv.get('unselected_files','—')} · trop volumineux : {inv.get('oversized_files','—')}",
            '', 'REGISTRE DES FRONTIÈRES',
            f"  Présentes au scan : {review.get('observed','—')} · non revues : {review.get('new_or_unreviewed','—')} · reportées : {review.get('deferred','—')}",
            f"  Approuvées : {review.get('approved','—')} · obligatoires : {review.get('required','—')} · optionnelles : {review.get('optional','—')}",
            f"  Non retrouvées cette campagne : {review.get('not_seen','—')} (décisions préservées)",
            '', 'ALIGNEMENT AVEC LA RÉFÉRENCE AUDIT',
            f"  Référence : {align.get('source','—')} · Diag : {align.get('diag_count','—')} · Audit : {align.get('audit_count','—')}",
            f"  Écarts : {align.get('diag_only','—')} côté Diag seulement, {align.get('audit_only','—')} côté Audit seulement",
            '', 'PREUVES DE COMMUNICATION',
            f"  Appels API statiques : {api.get('static_calls','—')} · routes relevées : {api.get('routes_inbound','—')} · frontières déclarées appariées : {api.get('declared_matched','—')} / {api.get('declared','—')}",
            f"  Paires d'exports corrélées : {traces.get('correlated_pairs','—')} · reçus IK : {traces.get('ik_receipts','—')}",
            f"  Obligatoires incluses dans un parcours : {matrix.get('required_in_journey','—')} / {matrix.get('required','—')} · corroborées : {matrix.get('required_proven','—')}",
            f"  Obligatoires non prouvées : {matrix.get('required_unproven','—')} · revues en attente : {matrix.get('review_pending','—')}",
            f"  Parcours explicitement déclarés : {journeys.get('declared','—')} · corroborés : {journeys.get('evidence_complete','—')}",
            f"  Obligatoires corroborées en autonome : {matrix.get('required_autonomous_proven','—')} · en intégré : {matrix.get('required_integrated_proven','—')}",
            f"  Exports Koali lus : {(self.snapshot or {}).get('koali',{}).get('koali_summaries','—')} · indices de dépendance au shell : {len((self.snapshot or {}).get('koali',{}).get('dependency_indicators',[]))}",
            '', 'PROCHAINES ACTIONS',
        ]
        priority=self.run_root/'priorites.txt' if self.run_root else None
        if priority and priority.is_file():
            lines.extend('  • '+s for s in priority.read_text(encoding='utf-8').splitlines() if s.strip())
        else:lines.append('  • Exécuter une campagne complète et charger les preuves disponibles.')
        comparison=self.summary.get('comparison',{})
        if comparison.get('available'):lines+=['',f"COMPARAISON : campagne précédente {comparison.get('previous_run_id','?')} · voir delta.json"]
        lines+=['','IMPORTANT : aucune relation documentaire, statique ou simple réponse de sonde ne certifie un échange métier de bout en bout.']
        self.overview_text.config(state='normal');self.overview_text.delete('1.0','end');self.overview_text.insert('1.0','\n'.join(lines));self.overview_text.config(state='disabled')

    def make_levels(self):
        self.level_tree=self.tree(self.tab_levels,('Niveau','Domaine','Verdict','Obligatoire'),(85,600,130,120),['Domaine'])
        self.level_tree.bind('<<TreeviewSelect>>',self.on_level)

    def make_relations(self):
        area=tk.Frame(self.tab_rel,bg='#fff');area.pack(fill='x',padx=16,pady=(12,0))
        self.label(area,'FILTRER PAR REPO, CONTRAT OU STATUT',fg=MUTED).pack(side='left')
        tk.Entry(area,textvariable=self.filter,font=('Segoe UI',10),width=45).pack(side='left',padx=12)
        self.rel_tree=self.tree(self.tab_rel,('ID','Producteur','Consommateur','Contrat','Qualification'),
                                (60,230,230,360,220),['Contrat'])
        self.rel_tree.bind('<<TreeviewSelect>>',self.on_relation)

    def make_registry(self):
        top=tk.Frame(self.tab_registry,bg='#fff');top.pack(fill='x',padx=13,pady=(11,1))
        self.label(top,'FRONTIÈRES À QUALIFIER  ·  AUCUNE APPROBATION AUTOMATIQUE',
                   fg=BRAND,font=('Segoe UI',10,'bold')).pack(side='left')
        self.registry_label=self.label(self.tab_registry,'Aucun registre local · lance une campagne complète pour découvrir les frontières.',fg=MUTED)
        self.registry_label.pack(anchor='w',padx=15,pady=(3,8))
        actions=tk.Frame(self.tab_registry,bg='#fff');actions.pack(fill='x',padx=13,pady=(0,2))
        self.label(actions,'Recherche',fg=MUTED).pack(side='left')
        tk.Entry(actions,textvariable=self.registry_filter,width=25,font=('Segoe UI',10)).pack(side='left',padx=(9,12))
        self.button(actions,'QUALIFIER LA SÉLECTION',self.edit_registry,bg=BRAND).pack(side='left',padx=(0,8))
        self.button(actions,'RECHARGER',self.render_registry,bg=BRAND_SOFT,fg=INK).pack(side='left',padx=(0,8))
        self.button(actions,'RAPPROCHER LE DERNIER SCAN',self.sync_registry_gui,bg=BRAND_SOFT,fg=INK).pack(side='left')
        self.registry_tree=self.tree(self.tab_registry,
            ('ID','Émetteur','Récepteur','Contrat','Décision','Obligation','Observé'),
            (150,175,175,300,125,115,95),['Contrat'])
        self.registry_tree.bind('<Double-1>',lambda *_:self.edit_registry())
        self.registry_rows={}

    def render_registry(self):
        if not hasattr(self,'registry_tree'):return
        self.registry_tree.delete(*self.registry_tree.get_children());self.registry_rows={}
        try:
            data=registry.read(HERE)
        except (ValueError,OSError,TypeError) as exc:
            self.registry_label.config(text='Registre invalide : '+str(exc),fg=RED)
            return
        summary=registry.metrics(data)
        self.registry_label.config(text=(
            f"{summary['registered']} lignes · {summary['new_or_unreviewed']} non revues · "
            f"{summary['approved']} approuvées ({summary['required']} obligatoires) · "
            f"{summary['deferred']} reportées · {summary['not_seen']} non observées"),fg=MUTED)
        needle=self.registry_filter.get().strip().casefold()
        for row in data['relations']:
            full=' '.join(str(row.get(k,'')) for k in ('source_repo','target_repo','contract','review_status','boundary_key'))
            if needle and needle not in full.casefold():continue
            key=row['boundary_key'];self.registry_rows[key]=row
            obligation=('Obligatoire' if row['required'] is True else
                        'Optionnelle' if row['required'] is False else '—')
            self.registry_tree.insert('','end',iid=key,values=(key,row['source_repo'],row['target_repo'],
                row['contract'],row['review_status'],obligation,'Oui' if row.get('observed') else 'Non'))

    def sync_registry_gui(self):
        if self.running:
            messagebox.showwarning('Registre','Attends la fin de la campagne.');return
        if not self.snapshot:
            messagebox.showwarning('Registre','Charge un rapport de campagne avant de rapprocher les relations.');return
        try:
            data,added=registry.synchronize(HERE,self.snapshot.get('relations',[]))
            self.render_registry()
            self.log(f'Registre rapproché du dernier scan : {len(data["relations"])} relations, {added} nouvelles.')
            messagebox.showinfo('Registre',f'{added} nouvelles frontières ajoutées à qualifier. Aucune décision existante modifiée.')
        except (ValueError,OSError,TypeError) as exc:
            messagebox.showerror('Registre',str(exc))

    def edit_registry(self):
        if self.running:
            messagebox.showwarning('Registre','Les décisions sont verrouillées durant la campagne.');return
        chosen=self.registry_tree.selection()
        if not chosen:return
        item=self.registry_rows.get(chosen[0])
        if not item:return
        win=tk.Toplevel(self);win.title('Qualifier une frontière inter-repos');win.geometry('800x640')
        win.configure(bg='#fff');win.transient(self);win.grab_set()
        body=tk.Frame(win,bg='#fff');body.pack(fill='both',expand=True,padx=22,pady=16)
        self.label(body,'FRONTIÈRE : '+item['source_repo']+' → '+item['target_repo'],font=('Segoe UI',13,'bold'),fg=BRAND).grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,4))
        self.label(body,'Contrat : '+item.get('contract',''),fg=MUTED).grid(row=1,column=0,columnspan=2,sticky='w',pady=(0,16))
        status=tk.StringVar(value=item['review_status']);needed=tk.StringVar(value=('Obligatoire' if item['required'] is True else 'Optionnelle' if item['required'] is False else 'À définir'))
        protocol=tk.StringVar(value=item.get('protocol',''));method=tk.StringVar(value=item.get('method',''))
        route=tk.StringVar(value=item.get('route',''));channel=tk.StringVar(value=item.get('event_channel',''))
        audit=tk.StringVar(value=item.get('audit_repo_identity',''))
        comment=tk.StringVar(value=item.get('comment',''))
        row=2
        for label,var,values in (
            ('Décision humaine',status,sorted(registry.STATES)),
            ('Obligation (si approuvée)',needed,['À définir','Obligatoire','Optionnelle']),
            ('Protocole',protocol,sorted(registry.PROTOCOLS)),
            ('Méthode HTTP',method,sorted(registry.METHODS))):
            self.label(body,label,fg=MUTED).grid(row=row,column=0,sticky='w',pady=7)
            ttk.Combobox(body,textvariable=var,values=values,state='readonly',width=32).grid(row=row,column=1,sticky='ew',pady=7)
            row+=1
        for label,var in (('Route HTTP sans query',route),('Canal EVENT (si applicable)',channel),('Identité canonique Audit',audit),('Note de revue',comment)):
            self.label(body,label,fg=MUTED).grid(row=row,column=0,sticky='w',pady=7)
            tk.Entry(body,textvariable=var,font=('Segoe UI',10),width=40).grid(row=row,column=1,sticky='ew',pady=7)
            row+=1
        body.columnconfigure(1,weight=1)
        self.label(body,'Une approbation confirme le périmètre, PAS la communication runtime ni E2E.',fg=AMBER).grid(row=row,column=0,columnspan=2,sticky='w',pady=(12,5))
        row+=1
        buttons=tk.Frame(body,bg='#fff');buttons.grid(row=row,column=0,columnspan=2,sticky='e',pady=(16,0))
        def save():
            try:
                obligation={'Obligatoire':True,'Optionnelle':False,'À définir':None}[needed.get()]
                registry.decide(HERE,item['boundary_key'],status=status.get(),required=obligation,
                    protocol=protocol.get(),method=method.get(),route=route.get(),
                    event_channel=channel.get(),audit_repo_identity=audit.get(),comment=comment.get())
                self.render_registry();self.log('Frontière qualifiée : '+item['boundary_key']+' · '+status.get())
                win.destroy()
            except (ValueError,OSError,TypeError) as exc:
                messagebox.showerror('Revue invalide',str(exc),parent=win)
        self.button(buttons,'ENREGISTRER LA DÉCISION',save).pack(side='right')
        self.button(buttons,'ANNULER',win.destroy,bg=BRAND_SOFT,fg=INK).pack(side='right',padx=8)

    def make_boundary_evidence(self):
        row=tk.Frame(self.tab_boundary_evidence,bg='#fff');row.pack(fill='x',padx=16,pady=(12,0))
        self.matrix_status=self.label(row,'Lancer une campagne pour qualifier les preuves par frontière.',fg=MUTED)
        self.matrix_status.pack(anchor='w')
        self.boundary_tree=self.tree(self.tab_boundary_evidence,
            ('Émetteur','Récepteur','Décision','Obligation','Contrat','Paires','E2E','Verdict','État'),
            (130,130,95,80,145,55,55,70,240),['État'])
        self.boundary_tree.bind('<<TreeviewSelect>>',self.on_boundary_evidence)

    def render_boundary_evidence(self):
        self.boundary_tree.delete(*self.boundary_tree.get_children());self.boundary_proof_rows={}
        if not self.run_root:return
        source=self.run_root/'boundary-qualification.json'
        if not source.is_file():
            self.matrix_status.config(text='Aucune matrice de preuves dans cette campagne.');return
        try:
            data=read_json(source)
            summary=data['summary'];rows=data['rows']
        except (OSError,KeyError,TypeError,ValueError) as exc:
            self.matrix_status.config(text='Matrice invalide : '+str(exc)[:130]);return
        self.matrix_status.config(text=(f"{summary['registered']} frontières · {summary['required']} obligatoires · "
            f"{summary.get('required_in_journey',0)} dans un parcours déclaré · "
            f"{summary['required_unproven']} obligatoires sans preuve · "
            f"{summary['review_pending']} à revoir"))
        for item in rows:
            ident=item['boundary_key'];self.boundary_proof_rows[ident]=item
            self.boundary_tree.insert('', 'end',iid=ident,values=(
                item['source_repo'],item['target_repo'],item['review_status'],
                'Oui' if item['required'] is True else ('Non' if item['required'] is False else '—'),
                item.get('contract_status','—'),item['passive_pairs'],item['matching_journeys'],
                item.get('verdict','—'),item['status']))

    def on_boundary_evidence(self,_=None):
        selected=self.boundary_tree.selection()
        if selected and selected[0] in self.boundary_proof_rows:
            row=self.boundary_proof_rows[selected[0]]
            self.show_detail('Preuves : '+row['source_repo']+' → '+row['target_repo'],
                json.dumps(row,ensure_ascii=False,indent=2))

    def make_imports(self):
        top=tk.Frame(self.tab_imports,bg='#fff');top.pack(fill='x',padx=15,pady=(11,3))
        self.import_status=self.label(top,'Exports passifs : métadonnées uniquement, aucun test applicatif lancé.',fg=MUTED)
        self.import_status.pack(anchor='w')
        row=tk.Frame(self.tab_imports,bg='#fff');row.pack(fill='x',padx=15,pady=(0,3))
        self.button(row,'AJOUTER EXPORT JSON / JSONL',self.add_evidence_file).pack(side='left',padx=(0,8))
        self.button(row,'RETIRER LA SÉLECTION',self.remove_evidence_file,bg=BRAND_SOFT,fg=INK).pack(side='left',padx=(0,8))
        self.button(row,'VÉRIFIER LES EXPORTS',self.verify_evidence_files,bg=BRAND_SOFT,fg=INK).pack(side='left',padx=(0,8))
        self.button(row,'RECHARGER',self.render_evidence_imports,bg=BRAND_SOFT,fg=INK).pack(side='left')
        self.import_tree=self.tree(self.tab_imports,('Chemin relatif C:\\mycode','Propriétaire déclaré','Format','Mode'),
            (490,200,160,150),['Chemin relatif C:\\mycode'])

    def _local_evidence(self):
        path=HERE/'koa-ecosystem-diag.config.local.json'
        if path.exists():
            local=read_json(path)
            if not isinstance(local,dict):raise ValueError('Configuration locale doit être un objet JSON')
        else:local={}
        interrepo=local.setdefault('interrepo',{})
        if not isinstance(interrepo,dict):raise ValueError('interrepo doit être un objet JSON')
        sources=interrepo.setdefault('exchange_trace_files',[])
        if not isinstance(sources,list):raise ValueError('exchange_trace_files doit être une liste')
        return path,local,sources

    def _save_local_evidence(self,path,local):
        # Update only the selected local setting; do not replace any other options.
        temp=path.with_name(path.name+'.tmp')
        temp.write_text(json.dumps(local,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        temp.replace(path)

    def render_evidence_imports(self):
        if not hasattr(self,'import_tree'):return
        self.import_tree.delete(*self.import_tree.get_children())
        try:
            _,_,sources=self._local_evidence()
        except (ValueError,OSError,TypeError) as exc:
            self.import_status.config(text='Configuration locale invalide : '+str(exc)[:110]);return
        for i,source in enumerate(sources):
            descriptor=source if isinstance(source,dict) else {'path':source}
            self.import_tree.insert('','end',iid=str(i),values=(
                descriptor.get('path',''),descriptor.get('owner_repo','Non attribué'),
                descriptor.get('format','exchange'),descriptor.get('mode','non_renseigne')))
        self.import_status.config(text=f'{len(sources)} export(s) configuré(s) · les fichiers originaux ne sont jamais modifiés')

    def add_evidence_file(self):
        if self.running:messagebox.showwarning('Diagnostic','Attends la fin de la campagne.');return
        root=Path(self.rootvar.get()).expanduser()
        if not root.is_dir():messagebox.showerror('Dossier','Sélectionne une racine de dépôts accessible.');return
        selected=filedialog.askopenfilename(title='Export passif depuis un diagnostic dédié',
            initialdir=str(root),filetypes=[('Preuves JSON','*.json *.jsonl *.ndjson'),('Tous fichiers','*.*')])
        if not selected:return
        try:
            rel=Path(selected).resolve().relative_to(root.resolve()).as_posix()
            if not rel.endswith(('.json','.jsonl','.ndjson')):raise ValueError('Fichier JSON/JSONL attendu')
        except ValueError:
            messagebox.showerror('Chemin','L’export doit être situé sous la racine des dépôts, sans lien hors racine.');return
        owner=simpledialog.askstring('Provenance des preuves',
            'Nom exact du dépôt qui a produit CE fichier (ex. Konnaxion).\n'
            'Si vide : les preuves seront non attestées.',parent=self)
        if owner is None:return
        mode=simpledialog.askstring('Mode de collecte','autonome, integre ou non_renseigne',
                                    initialvalue='non_renseigne',parent=self)
        if mode is None:return
        spec={'path':rel,'owner_repo':owner.strip(),'mode':mode}
        observed,diagnostics=load_evidence(root,[spec])
        if diagnostics and diagnostics[0].get('status')=='ECART':
            messagebox.showerror('Export invalide',diagnostics[0].get('detail','Erreur inconnue'));return
        if observed and messagebox.askyesno('Empreinte de référence',
                'As-tu vérifié l’origine et l’intégrité du fichier auprès du producteur ?\n'
                'Oui : conserver le SHA-256 de ces octets pour les campagnes suivantes.',parent=self):
            spec['sha256']=diagnostics[0]['sha256']
        if not observed:
            if not messagebox.askyesno('Aucun enregistrement reconnu',
                'Aucun enregistrement canonique identifié. Ajouter pour configurer plus tard un field_map ?'):return
        try:
            path,local,sources=self._local_evidence()
            if any((row.get('path') if isinstance(row,dict) else row)==rel for row in sources):
                messagebox.showinfo('Déjà configuré',rel);return
            sources.append(spec);self._save_local_evidence(path,local)
            self.render_evidence_imports()
            self.log(f'Export configuré (non exécuté) : {rel} · {len(observed)} enregistrements reconnus')
        except (ValueError,OSError,TypeError) as exc:messagebox.showerror('Export',str(exc))

    def remove_evidence_file(self):
        if self.running:return
        chosen=self.import_tree.selection()
        if not chosen:return
        idx=int(chosen[0])
        try:
            path,local,sources=self._local_evidence()
            if idx>=len(sources):return
            removed=sources.pop(idx)
            self._save_local_evidence(path,local);self.render_evidence_imports()
            self.log('Source désinscrite, fichier original conservé : '+str(removed)[:110])
        except (ValueError,OSError,TypeError) as exc:messagebox.showerror('Export',str(exc))

    def verify_evidence_files(self):
        if self.running:return
        try:
            root=Path(self.rootvar.get()).resolve()
            _,_,sources=self._local_evidence()
            records,findings=load_evidence(root,sources)
            failures=[r for r in findings if r.get('status')=='ECART']
            self.import_status.config(text=f'{len(records)} enregistrements reconnus · {len(failures)} erreur(s) · aucune opération métier')
            for i,row in enumerate(findings):
                if self.import_tree.exists(str(i)):
                    vals=list(self.import_tree.item(str(i),'values'))
                    vals[2]='ERREUR : '+str(row.get('detail',''))[:70] if row.get('status')=='ECART' else str(row.get('records',0))+' enregistrements lus'
                    self.import_tree.item(str(i),values=vals)
        except (ValueError,OSError,TypeError) as exc:messagebox.showerror('Preuves',str(exc))

    def make_evidence(self):
        top=tk.Frame(self.tab_evidence,bg='#fff');top.pack(fill='x',padx=15,pady=(11,0))
        self.label(top,'NIVEAU',fg=MUTED).pack(side='left')
        self.evidence_level=tk.StringVar(value='Tous')
        chooser=ttk.Combobox(top,textvariable=self.evidence_level,state='readonly',width=22,
             values=['Tous']+[x['id'] for x in self.manifest['levels']])
        chooser.pack(side='left',padx=(8,0));chooser.bind('<<ComboboxSelected>>',lambda *_:self.render_findings())
        self.findings_tree=self.tree(self.tab_evidence,('Niveau','Verdict','Identifiant','Description'),
                                     (85,105,330,710),['Description'])
        self.findings_tree.bind('<<TreeviewSelect>>',self.on_finding)

    def make_history(self):
        top=tk.Frame(self.tab_history,bg='#fff');top.pack(fill='x',padx=17,pady=15)
        self.label(top,'CAMPAGNES CONSERVÉES',fg=MUTED).pack(side='left')
        self.history_combo=ttk.Combobox(top,textvariable=self.historyvar,state='readonly',width=53,values=[])
        self.history_combo.pack(side='left',padx=12)
        self.button(top,'CHARGER',self.load_selected,bg=BRAND).pack(side='left')
        self.history_tree=self.tree(self.tab_history,('Date UTC','Run ID','Campagne','Verdict'),
                                    (170,250,210,150),['Run ID'])
        self.history_tree.bind('<Double-1>',lambda *_:self.load_history_row())

    def make_ports(self):
        bar=tk.Frame(self.tab_ports,bg='#fff')
        bar.pack(fill='x',padx=16,pady=(14,3))
        self.ports_button=self.button(bar,'TESTER TOUS LES PORTS C0',self.start_ports,bg=BRAND)
        self.ports_button.pack(side='left')
        self.button(bar,'RECHARGER LE REGISTRE',self.refresh_ports_catalog,bg=BRAND_SOFT,fg=INK).pack(side='left',padx=(9,0))
        self.button(bar,'OUVRIR LE DERNIER RAPPORT',self.open_ports_report,bg=BRAND_SOFT,fg=INK).pack(side='left',padx=(9,0))
        reboot_bar=tk.Frame(self.tab_ports,bg='#fff')
        reboot_bar.pack(fill='x',padx=16,pady=(5,5))
        self.label(reboot_bar,'Redémarrage C0 :',bg='#fff',fg=MUTED).pack(side='left',padx=(0,6))
        self.reboot_scope_combo=ttk.Combobox(reboot_bar,textvariable=self.reboot_scope,
            values=('Essentiels','Tous les groupes'),state='readonly',width=19)
        self.reboot_scope_combo.pack(side='left')
        self.reboot_action_combo=ttk.Combobox(reboot_bar,textvariable=self.reboot_action,
            values=('Démarrer','Redémarrer','Arrêter supervisés'),state='readonly',width=18)
        self.reboot_action_combo.pack(side='left',padx=(9,0))
        self.reboot_plan_button=self.button(reboot_bar,'VOIR LE PLAN',self.show_reboot_plan,bg=BRAND_SOFT,fg=INK)
        self.reboot_plan_button.pack(side='left',padx=(10,0))
        self.reboot_button=self.button(reboot_bar,'EXÉCUTER (CONFIRMATION)',self.show_reboot_plan,bg='#9a6a23')
        self.reboot_button.pack(side='left',padx=(9,0))
        self.ports_status=self.label(self.tab_ports,'Le registre C0 sera lu depuis C:\\mycode.',bg='#fff',fg=MUTED)
        self.ports_status.pack(anchor='w',padx=18,pady=5)
        self.ports_tree=self.tree(self.tab_ports,
            ('Port','Service','Propriétaire','TCP','HTTP','Verdict','Précision'),
            (90,260,130,75,80,205,475),['Précision'])
        self.ports_tree.tag_configure('C0_GOOD',foreground=GREEN)
        self.ports_tree.tag_configure('C0_BAD',foreground=RED)
        self.ports_tree.tag_configure('C0_WARN',foreground=AMBER)
        self.ports_tree.tag_configure('C0_IDLE',foreground=MUTED)
        self.ports_tree.bind('<Double-1>',self.show_port_detail)
        note=self.label(self.tab_ports,
            'TESTER : lecture seule. REDÉMARRER : action locale explicite avec aperçu et confirmation.\n'
            'Aucun port de secours; aucun PID inconnu arrêté; les lanceurs propriétaires restent obligatoires pour certains groupes.',
            bg='#fff',fg=MUTED,justify='left')
        note.pack(anchor='w',padx=18,pady=(0,10))
        self.ports_rows={}

    def refresh_ports_catalog(self):
        try:
            path, registry_doc=port_diagnostics.read_registry(Path(self.rootvar.get()))
        except (OSError,ValueError,TypeError,json.JSONDecodeError) as exc:
            if hasattr(self,'ports_status'):
                self.ports_status.config(text='Registre C0 indisponible : '+str(exc),fg=RED)
                self.ports_tree.delete(*self.ports_tree.get_children())
            return
        self.ports_tree.delete(*self.ports_tree.get_children())
        self.ports_rows={}
        for entry in sorted(registry_doc['services'],key=lambda r:r['port']):
            self.ports_tree.insert('','end',iid=entry['id'],
                values=(entry['port'],entry['id'],entry['owner'],'—','—','NON TESTÉ',entry.get('purpose','')),
                tags=('C0_IDLE',))
        self.ports_status.config(text=f"{len(registry_doc['services'])} ports attribués · Source : {path} · Tests non exécutés",
                                 fg=INK)

    def start_ports(self):
        if self.ports_running:return
        if self.reboot_running:
            messagebox.showwarning('Ports C0','Le redémarrage C0 est en cours.');return
        if self.running:
            messagebox.showwarning('Ports C0','La campagne principale est en cours.');return
        self.ports_running=True
        self.ports_button.config(state='disabled',text='SONDES EN COURS…')
        self.ports_status.config(text='Sondes locales en cours (aucun service n’est démarré ni arrêté)…',fg=BRAND)
        root=Path(self.rootvar.get())
        def worker():
            try:
                result=port_diagnostics.check_all(root)
                output=HERE/'reports'/'Diagnostic-kOA-Digital-Ecosystem'/'ports-c0'
                folder=port_diagnostics.write_reports(result,output)
                self.q.put(('ports_done',(result,str(folder))))
            except Exception as exc:
                self.q.put(('ports_error',type(exc).__name__+': '+str(exc)))
        threading.Thread(target=worker,daemon=True,name='koa-diag-ports-c0').start()

    def reboot_args(self,action):
        root=Path(self.rootvar.get()).expanduser()
        # The registry is required even for a preview. Never infer or scan a free port.
        port_diagnostics.read_registry(root)
        cmd=[python_console(),'-m','koa_ecosystem_diag.c0_reboot',action,
             '--root',str(root)]
        if self.reboot_scope.get()=='Tous les groupes':cmd.append('--all')
        return cmd

    def show_reboot_plan(self):
        if self.running or self.ports_running or self.reboot_running:
            messagebox.showwarning('Redémarrage C0','Une autre opération est en cours.');return
        try:
            cmd=self.reboot_args('plan')
            completed=subprocess.run(cmd,cwd=str(HERE),capture_output=True,
                text=True,encoding='utf-8',errors='replace',timeout=15,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if completed.returncode:
                raise RuntimeError((completed.stderr or completed.stdout).strip() or 'Plan indisponible')
        except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as exc:
            messagebox.showerror('Plan C0 impossible',str(exc));return
        dialog=tk.Toplevel(self)
        dialog.title('Plan de redémarrage C0 — vérification avant action')
        dialog.geometry('940x620');dialog.minsize(700,420);dialog.transient(self)
        body=tk.Frame(dialog,bg='#fff');body.pack(fill='both',expand=True,padx=18,pady=14)
        self.label(body,'Opération locale avec effets réels',bg='#fff',fg=AMBER,
            font=('Segoe UI',13,'bold')).pack(anchor='w')
        action=self.reboot_action.get()
        self.label(body,'Action choisie : '+action+' · Périmètre : '+self.reboot_scope.get()+'. '
            'Seuls les services admissibles sont concernés. Les PID inconnus ne sont jamais arrêtés. '
            'Pour Orgo, Docker Compose peut démarrer ou redémarrer des conteneurs, mais ne supprime aucun volume.',
            bg='#fff',fg=INK,wraplength=860,justify='left').pack(anchor='w',pady=(7,10))
        text=tk.Text(body,wrap='word',font=('Consolas',10),bg='#eef5f4',fg=INK,
                     height=17,relief='flat')
        text.pack(fill='both',expand=True)
        text.insert('1.0',completed.stdout)
        text.configure(state='disabled')
        ack=tk.BooleanVar(value=False)
        box=tk.Checkbutton(body,text='Je confirme le redémarrage de ces services locaux et leurs effets possibles.',
            variable=ack,bg='#fff',fg=INK,selectcolor='#fff')
        box.pack(anchor='w',pady=(12,4))
        buttons=tk.Frame(body,bg='#fff');buttons.pack(fill='x',pady=(6,0))
        self.button(buttons,'ANNULER',dialog.destroy,bg=BRAND_SOFT,fg=INK).pack(side='right')
        def confirm():
            if not ack.get():
                messagebox.showwarning('Confirmation requise','Cocher la confirmation explicite avant exécution.',parent=dialog)
                return
            dialog.destroy()
            self.start_reboot()
        self.button(buttons,'CONFIRMER : '+action.upper(),confirm,bg='#9a6a23').pack(side='right',padx=(0,9))
        dialog.grab_set();dialog.focus_set()

    def start_reboot(self):
        if self.running or self.ports_running or self.reboot_running:return
        if os.name!='nt':
            messagebox.showerror('Redémarrage C0','Le redémarrage est réservé à Windows.');return
        actions={'Démarrer':'start','Redémarrer':'restart','Arrêter supervisés':'stop'}
        try:cmd=self.reboot_args(actions[self.reboot_action.get()])
        except (OSError,ValueError,RuntimeError) as exc:
            messagebox.showerror('Redémarrage C0',str(exc));return
        self.reboot_running=True
        for b in (self.reboot_plan_button,self.reboot_button,self.ports_button):b.config(state='disabled')
        self.reboot_scope_combo.config(state='disabled')
        self.reboot_action_combo.config(state='disabled')
        self.ports_status.config(text='Redémarrage et attente de disponibilité TCP en cours : voir Journal…',fg=AMBER)
        self.log('C0 : opération '+self.reboot_action.get()+' déclenchée après confirmation explicite.')
        self.tabs.select(self.tab_ports)
        def worker():
            output=HERE/'reports'/'Diagnostic-kOA-Digital-Ecosystem'/'reboot-c0'
            folder=output/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
            folder.mkdir(parents=True,exist_ok=True)
            logfile=folder/'reboot-c0.txt'
            code=99
            try:
                with logfile.open('w',encoding='utf-8') as report:
                    proc=subprocess.Popen(cmd,cwd=str(HERE),stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',
                        bufsize=1,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    with proc.stdout as stream:
                        for line in stream:
                            report.write(line);report.flush()
                            self.q.put(('reboot_line',line.rstrip()))
                    code=proc.wait()
            except Exception as exc:
                self.q.put(('reboot_line','ERREUR : '+type(exc).__name__+': '+str(exc)))
            self.q.put(('reboot_done',(code,str(folder))))
        threading.Thread(target=worker,daemon=True,name='koa-diag-reboot-c0').start()

    def finish_reboot(self,code,folder):
        self.reboot_running=False
        for b in (self.reboot_plan_button,self.reboot_button,self.ports_button):b.config(state='normal')
        self.reboot_scope_combo.config(state='readonly')
        self.reboot_action_combo.config(state='readonly')
        self.log('C0 : opération terminée code='+str(code)+' ; journal='+folder)
        self.ports_status.config(text=('Opération terminée' if code==0 else
            'Opération partielle/en erreur')+' · audit des ports après attente de disponibilité…',
            fg=INK if code==0 else AMBER)
        self.start_ports()

    def close_checked(self):
        if self.reboot_running:
            messagebox.showwarning('Redémarrage en cours',
                'L’opération est toujours en cours. Ne ferme pas kOADiag avant le bilan.');return
        self.destroy()

    def finish_ports(self,result,folder):
        self.ports_running=False
        self.ports_button.config(state='normal',text='TESTER TOUS LES PORTS C0')
        self.ports_last_folder=Path(folder)
        self.ports_tree.delete(*self.ports_tree.get_children())
        self.ports_rows={r['id']:r for r in result['services']}
        for row in result['services']:
            status=row['status']
            tag=('C0_BAD' if status in ('WRONG_SERVICE','SCAN_ERROR')
                 else 'C0_GOOD' if status == 'IDENTITY_CONFIRMED' else 'C0_WARN')
            self.ports_tree.insert('','end',iid=row['id'],
                values=(row['port'],row['id'],row['owner'],
                        'OUI' if row['tcp'] else 'NON',
                        row['http_code'] if row['http_code'] is not None else '—',
                        status,row['detail']),tags=(tag,))
        stats=result['summary']
        self.ports_status.config(text=(f"{result['expected']} ports vérifiés · "
            f"{stats.get('STOPPED',0)} arrêtés · {stats.get('WRONG_SERVICE',0)} mauvais services · "
            f"{stats.get('FAMILY_MATCH',0)} familles reconnues · "
            f"{stats.get('IDENTITY_CONFIRMED',0)} identités confirmées · "
            f"{sum(stats.get(k,0) for k in ('HTTP_UNVERIFIED','TCP_OPEN_UNVERIFIED'))} non identifiés"),
            fg=RED if stats.get('WRONG_SERVICE',0) else INK)
        self.log('Ports C0 : '+str(self.ports_last_folder))
        self.tabs.select(self.tab_ports)

    def show_port_detail(self,event=None):
        picked=self.ports_tree.selection()
        if picked and picked[0] in self.ports_rows:
            self.show_detail('Port C0 '+picked[0],
                json.dumps(self.ports_rows[picked[0]],ensure_ascii=False,indent=2))

    def open_ports_report(self):
        if not self.ports_last_folder or not self.ports_last_folder.is_dir():
            messagebox.showinfo('Ports C0','Exécuter d’abord TESTER TOUS LES PORTS C0.');return
        folder=str(self.ports_last_folder)
        try:
            if os.name=='nt':os.startfile(folder)
            elif sys.platform=='darwin':subprocess.Popen(['open',folder])
            else:subprocess.Popen(['xdg-open',folder])
        except OSError as exc:messagebox.showerror('Rapport ports C0',str(exc))

    def make_console(self):
        container=tk.Frame(self.tab_console,bg='#fff');container.pack(fill='both',expand=True,padx=13,pady=13)
        self.console=tk.Text(container,wrap='word',font=('Consolas',10),fg=INK,bg='#f7fbff',relief='flat')
        s=ttk.Scrollbar(container,command=self.console.yview)
        self.console.config(yscrollcommand=s.set)
        self.console.pack(side='left',fill='both',expand=True);s.pack(side='right',fill='y')
        self.log('Diagnostic du kOA Digital Ecosystem v5.5.4 — prêt. Redémarrage C0 sur confirmation uniquement.\n')

    def log(self,text):
        self.console.insert('end',text if text.endswith('\n') else text+'\n')
        self.console.see('end')

    def choose_root(self):
        value=filedialog.askdirectory(title='Choisir la racine des dépôts kOA',initialdir=self.rootvar.get() if Path(self.rootvar.get()).exists() else str(Path.home()))
        if value:self.rootvar.set(value)

    def update_remote(self):
        if self.remote.get() and not self.network.get():self.network.set(True)
        if not self.remote.get():self.ack_remote.set(False)

    def choose_audit(self):
        folder=filedialog.askdirectory(title='GitHub Audit repository')
        if folder:self.audit_dir.set(folder)

    def start(self):
        if self.running:return
        if self.reboot_running:
            messagebox.showwarning('Campagne','Le redémarrage C0 est en cours.');return
        root=Path(self.rootvar.get()).expanduser()
        if not root.is_dir():messagebox.showerror('Racine introuvable','Sélectionne un dossier C:\\mycode existant.');return
        if self.runtime_local.get() and self.campaignvar.get() != 'validation-integrale':
            self.campaignvar.set('validation-integrale')
        if self.remote.get() and not self.ack_remote.get():
            messagebox.showwarning('Confirmation requise',
                'Les GET/HEAD distants nécessitent une autorisation explicite.');return
        try:
            cfg=load_config(HERE,str(root))
        except Exception as exc:messagebox.showerror('Configuration invalide',str(exc));return
        self.running=True;self.summary=None;self.snapshot=None;self.results={};self.run_root=None
        self.runbtn.config(state='disabled',text='DIAGNOSTIC EN COURS…')
        self.progress['maximum']=len({*self.selected_ids()});self.progress['value']=0
        self.progress_text.config(text='Démarrage…')
        self.verdict.config(text='ANALYSE EN COURS',fg=BRAND_ACCENT)
        for iid in self.level_tree.get_children():
            v=list(self.level_tree.item(iid,'values'));v[2]='À exécuter';self.level_tree.item(iid,values=v,tags=())
        self.log('\n--- Nouvelle campagne : '+self.campaignvar.get()+' ---')
        cmd=[python_console(),str(HERE/'Diagnostic-kOA-Digital-Ecosystem-CLI.py'),'run',
             self.campaignvar.get(),'--root',str(root)]
        if self.runtime_local.get():
            cmd.extend(('--runtime-local','--start-test-stack'))
            if self.runtime_world.get().strip():cmd+=['--world',self.runtime_world.get().strip()]
        if self.audit_enabled.get():
            cmd.append('--audit')
            if self.audit_dir.get().strip():cmd+=['--audit-root',self.audit_dir.get().strip()]
        if self.network.get():cmd.append('--network')
        if self.remote.get():cmd+=['--remote','--ack-remote']
        def task():
            try:
                self.process=subprocess.Popen(cmd,cwd=str(HERE),shell=False,
                    stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                    text=True,encoding='utf-8',errors='replace',bufsize=1,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name=='nt' else 0)
                with self.process.stdout as stream:
                    for line in stream:self.q.put(('line',line.rstrip()))
                self.q.put(('done',self.process.wait()))
            except Exception as exc:self.q.put(('error',str(exc)))
            finally:self.process=None
        threading.Thread(target=task,daemon=True,name='koa-ecosystem-diagnostic-ui').start()

    def selected_ids(self):
        choices=self.campaigns[self.campaignvar.get()]['levels']
        metas={x['id']:x for x in self.manifest['levels']};chosen=set(choices)
        while True:
            nxt=chosen | {d for x in chosen for d in metas[x]['depends_on']}
            if nxt==chosen:return chosen
            chosen=nxt

    def drain(self):
        try:
            while True:
                kind,value=self.q.get_nowait()
                if kind=='line':
                    if value.startswith('RUN_ROOT='):self.run_root=Path(value[9:]);self.log('Sortie : '+str(self.run_root))
                    elif value.startswith('LEVEL='):
                        parts=value[6:].split('|',2)
                        if len(parts)==3:
                            lid,status,name=parts
                            if self.level_tree.exists(lid):
                                v=list(self.level_tree.item(lid,'values'));v[2]=status
                                self.level_tree.item(lid,values=v,tags=(status,))
                            self.progress['value']=min(float(self.progress['maximum']),self.progress['value']+1)
                            self.progress_text.config(text=f'{int(self.progress["value"])} / {int(self.progress["maximum"])} niveaux')
                            self.stats['levels'].config(text=f'{int(self.progress["value"])} / {int(self.progress["maximum"])}')
                            self.log(f'{lid} {status:<12} {name}')
                    elif value.startswith('VERDICT='):
                        status=value[8:];self.verdict.config(text=status,fg=code_color(status))
                    elif value.startswith('SUMMARY='):pass
                    else:self.log(value)
                elif kind=='reboot_line':
                    self.log('C0 REBOOT : '+value)
                elif kind=='reboot_done':
                    code,folder=value
                    self.finish_reboot(code,folder)
                elif kind=='ports_done':
                    result,folder=value
                    self.finish_ports(result,folder)
                elif kind=='ports_error':
                    self.ports_running=False
                    self.ports_button.config(state='normal',text='TESTER TOUS LES PORTS C0')
                    self.ports_status.config(text='Sondes indisponibles : '+value,fg=RED)
                    self.log('ERREUR PORTS C0 : '+value)
                elif kind=='done':
                    self.running=False;self.runbtn.config(state='normal',text='LANCER LA CAMPAGNE')
                    if self.run_root and (self.run_root/'summary.json').is_file():
                        self.load_run(self.run_root)
                    else:
                        self.verdict.config(text='ERREUR EXÉCUTION',fg=RED)
                        messagebox.showerror('Diagnostic non terminé','Aucun rapport de campagne généré. Voir le journal.')
                    self.refresh_history()
                elif kind=='error':
                    self.running=False;self.runbtn.config(state='normal',text='LANCER LA CAMPAGNE')
                    self.verdict.config(text='ERREUR',fg=RED);self.log('ERREUR : '+value)
                    messagebox.showerror('Diagnostic',value)
        except queue.Empty:pass
        self.after(130,self.drain)

    def load_run(self,path):
        path=Path(path);self.run_root=path
        try:self.summary=read_json(path/'summary.json')
        except Exception as exc:messagebox.showerror('Rapport invalide',str(exc));return
        self.results={}
        for level in self.summary.get('levels',[]):
            p=path/level['result']
            if p.is_file():self.results[level['id']]=read_json(p)
        scan=path/'levels'/'N01'/'snapshot.json'
        self.snapshot=read_json(scan) if scan.is_file() else None
        s=self.summary;self.verdict.config(text=s['verdict'],fg=code_color(s['verdict']))
        self.stats['levels'].config(text=str(len(s['levels']))+' / '+str(len(s['levels'])))
        if self.snapshot:
            data=self.snapshot['summary'];self.stats['repos'].config(text=f"{data['present_repos']} / {data['inventory_repos']}")
            self.stats['relations'].config(text=str(data['relations']))
            self.stats['proven'].config(text=str(data['exchanges_correlated']+data['ik_receipts_success']))
            self.stats['journeys'].config(text=f"{data.get('journeys_evidence_complete',0)} / {data.get('journeys_configured',0)}")
        else:
            for key in ('repos','relations','proven','journeys'):self.stats[key].config(text='—')
        for iid in self.level_tree.get_children():
            v=list(self.level_tree.item(iid,'values'))
            item=self.results.get(iid);status=item['verdict'] if item else 'Non exécuté'
            v[2]=status;self.level_tree.item(iid,values=v,tags=(status,))
        self.progress['maximum']=len(s['levels']);self.progress['value']=len(s['levels'])
        self.progress_text.config(text='Rapport '+s['run_id'])
        self.render_relations();self.render_registry();self.render_findings();self.render_journeys();self.render_overview();self.render_boundary_evidence();self.render_evidence_imports()
        self.log('Campagne '+s['run_id']+' : '+s['verdict'])

    def render_relations(self):
        if not hasattr(self,'rel_tree'):return
        self.rel_tree.delete(*self.rel_tree.get_children())
        self.relation_rows=[]
        if not self.snapshot:return
        needle=self.filter.get().casefold().strip()
        for r in self.snapshot['relations']:
            text=' '.join(str(r.get(k,'')) for k in ('source','target','contract','qualification','maturity'))
            if needle and needle not in text.casefold():continue
            idx=len(self.relation_rows);self.relation_rows.append(r)
            self.rel_tree.insert('','end',iid=str(idx),values=(r['id'],r['source'],r['target'],r['contract'],r['qualification']))

    def render_findings(self):
        if not hasattr(self,'findings_tree'):return
        self.findings_tree.delete(*self.findings_tree.get_children())
        self.finding_rows=[];selected=self.evidence_level.get()
        for lid,result in sorted(self.results.items()):
            if selected!='Tous' and selected!=lid:continue
            for f in result.get('findings',[]):
                i=len(self.finding_rows);self.finding_rows.append((lid,f))
                self.findings_tree.insert('','end',iid=str(i),values=(lid,f['verdict'],f['id'],f['message']),tags=(f['verdict'],))

    def on_level(self,_=None):
        selected=self.level_tree.selection()
        if not selected:return
        lid=selected[0];self.evidence_level.set(lid);self.render_findings()
        self.tabs.select(self.tab_evidence)

    def on_relation(self,_=None):
        selected=self.rel_tree.selection()
        if not selected:return
        r=self.relation_rows[int(selected[0])]
        detail=json.dumps({'id':r['id'],'source':r['source'],'target':r['target'],
             'qualification':r['qualification'],'contract':r['contract'],
             'maturity':r['maturity'],'dimensions':r.get('dimensions'),
             'preuves':r.get('preuves'),'documentation':r.get('provenance')},ensure_ascii=False,indent=2)
        self.show_detail('Relation '+r['id']+' — '+r['source']+' → '+r['target'],detail)

    def on_finding(self,_=None):
        selected=self.findings_tree.selection()
        if not selected:return
        lid,f=self.finding_rows[int(selected[0])]
        self.show_detail(lid+' · '+f['id'],json.dumps(f,ensure_ascii=False,indent=2))

    def show_detail(self,title,value):
        popup=tk.Toplevel(self);popup.title(title);popup.geometry('850x530');popup.configure(bg='#fff')
        text=tk.Text(popup,wrap='word',font=('Consolas',10),bg='#f6faff',fg=INK,padx=18,pady=14)
        scroll=ttk.Scrollbar(popup,command=text.yview);text.configure(yscrollcommand=scroll.set)
        text.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
        text.insert('1.0',value);text.configure(state='disabled')

    def export_audit_gui(self):
        if self.running:
            messagebox.showwarning('Campagne en cours', 'Termine la campagne avant l’export Audit.')
            return
        if self.run_root and (self.run_root/'summary.json').is_file():
            source=self.run_root
        else:
            try:
                control=Path(load_config(HERE,self.rootvar.get())['_control'])
                source=control/'latest'
            except (OSError, ValueError, KeyError) as exc:
                messagebox.showerror('Export Audit',str(exc))
                return
        if not (source/'summary.json').is_file():
            messagebox.showwarning('Export Audit','Aucune campagne chargée. Lance d’abord une campagne.')
            return
        out=filedialog.asksaveasfilename(title='Exporter les métadonnées vers GitHub Audit',
            defaultextension='.zip',filetypes=[('Archives ZIP','*.zip')],
            initialfile='kOA-Diagnostic-pour-Audit.zip')
        if not out:return
        try:
            path,digest=export_campaign(source,Path(out))
            self.log('Export privé compatible GitHub Audit : '+str(path))
            messagebox.showinfo('Export Audit',
                'Archive compatible Audit créée.\n\n'+str(path)+
                '\n\nSHA-256 : '+digest+'\n\nMétadonnées uniquement, aucune trace brute.\n' +
                'À importer depuis GitHub Audit → Diagnostic écosystème.')
        except (OSError, ValueError, TypeError) as exc:
            messagebox.showerror('Export Audit',str(exc))

    def open_reports(self):
        try:control=Path(load_config(HERE,self.rootvar.get())['_control'])
        except Exception:control=HERE/'reports'/'Diagnostic-kOA-Digital-Ecosystem'
        control.mkdir(parents=True,exist_ok=True)
        if os.name=='nt':os.startfile(str(control))
        elif sys.platform=='darwin':subprocess.Popen(['open',str(control)])
        else:subprocess.Popen(['xdg-open',str(control)])

    def open_local_config(self):
        local=HERE/'koa-ecosystem-diag.config.local.json'
        if not local.exists():
            sample=HERE/'koa-ecosystem-diag.config.local.example.json'
            if not sample.is_file():
                messagebox.showerror('Configuration locale','Exemple de configuration introuvable.');return
            try:local.write_text(sample.read_text(encoding='utf-8'),encoding='utf-8')
            except OSError as exc:messagebox.showerror('Configuration locale',str(exc));return
        try:
            if os.name=='nt':os.startfile(str(local))
            elif sys.platform=='darwin':subprocess.Popen(['open',str(local)])
            else:subprocess.Popen(['xdg-open',str(local)])
        except (OSError,ValueError) as exc:
            messagebox.showerror('Configuration locale',str(exc))

    def refresh_history(self):
        if not hasattr(self,'history_tree'):return
        try:control=Path(load_config(HERE,self.rootvar.get())['_control'])
        except Exception:control=HERE/'reports'/'Diagnostic-kOA-Digital-Ecosystem'
        histories=[]
        if (control/'runs').exists():
            for p in sorted((control/'runs').glob('*/summary.json'),reverse=True)[:50]:
                try:
                    s=read_json(p);histories.append((p.parent,s))
                except (OSError,ValueError,KeyError,TypeError):pass
        self.histories=histories
        self.history_tree.delete(*self.history_tree.get_children())
        values=[]
        for i,(p,s) in enumerate(histories):
            self.history_tree.insert('','end',iid=str(i),values=(s.get('started_at','')[:19],s['run_id'],s['selection'],s['verdict']),tags=(s['verdict'],))
            values.append(s['run_id']+' · '+s['verdict'])
        self.history_combo['values']=values
        if values:self.history_combo.current(0)

    def load_selected(self):
        index=self.history_combo.current()
        if index>=0 and hasattr(self,'histories') and index<len(self.histories):
            self.load_run(self.histories[index][0]);self.tabs.select(self.tab_levels)

    def load_history_row(self):
        selection=self.history_tree.selection()
        if selection and hasattr(self,'histories'):
            self.load_run(self.histories[int(selection[0])][0]);self.tabs.select(self.tab_levels)


if __name__=='__main__':
    try:App().mainloop()
    except Exception as exc:
        import traceback
        try:messagebox.showerror('Erreur Diagnostic kOA',str(exc)+'\n'+traceback.format_exc()[-1300:])
        except Exception:pass
        raise
