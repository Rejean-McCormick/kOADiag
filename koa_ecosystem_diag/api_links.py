# -*- coding: utf-8 -*-
"""Explicit API boundary matching; strictly static evidence, never runtime proof."""
from __future__ import annotations


def _norm(value):return str(value or '').strip().casefold()


def check_links(declarations,calls,routes):
    if not isinstance(declarations,list):return []
    results=[]
    for row in declarations[:500]:
        if not isinstance(row,dict) or row.get('enabled',True) is False:continue
        ident=str(row.get('id') or 'sans-id')[:100]
        src=str(row.get('source','')).strip();tgt=str(row.get('target','')).strip()
        method=str(row.get('method','GET')).upper();path=str(row.get('path','')).strip()
        if not src or not tgt or not path.startswith('/') or method not in ('GET','HEAD','POST','PUT','PATCH','DELETE'):
            results.append({'id':ident,'status':'CONFIG_INVALIDE','required':bool(row.get('required',False)),'source':src,'target':tgt,'method':method,'path':path,
                'source_evidence':[],'target_evidence':[]})
            continue
        outgoing=[c.get('evidence',{}) for c in calls if _norm(c.get('source'))==_norm(src)
                  and c.get('method')==method and c.get('path')==path and
                  (not c.get('target') or _norm(c.get('target'))==_norm(tgt))]
        inbound=[r.get('evidence',{}) for r in routes if _norm(r.get('repo'))==_norm(tgt) and r.get('path')==path and r.get('method')==method]
        state='APPEL_ET_ROUTE_STATIQUES' if outgoing and inbound else ('APPEL_SANS_ROUTE_OBSERVEE' if outgoing else ('ROUTE_SANS_APPEL_OBSERVE' if inbound else 'NON_OBSERVE'))
        results.append({'id':ident,'source':src,'target':tgt,'method':method,'path':path,'status':state,
             'required':bool(row.get('required',False)),'source_evidence':outgoing[:8],
             'target_evidence':inbound[:8]})
    return results
