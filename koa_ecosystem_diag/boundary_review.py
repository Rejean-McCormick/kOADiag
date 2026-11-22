# -*- coding: utf-8 -*-
"""Conservative relation review register from a private scan snapshot.

Never auto-classifies a candidate as required, approved, or E2E-proven.
This document is for manual reconciliation with the kOA inventory authority.
"""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path


def _cell(value: object) -> str:
    """Prevent formula execution when opening exported CSV in Excel."""
    if not isinstance(value, (str, int, float)):
        return ''
    value = str(value)[:300]
    if value.startswith(('=', '+', '-', '@')) or value[:1] in ('\t', '\r', '\n'):
        return "'" + value
    return value


def write_review_register(snapshot: dict, output: Path) -> int:
    rows = snapshot.get('relations', []) if isinstance(snapshot, dict) else []
    if not isinstance(rows, list):
        raise ValueError('Relations du snapshot invalides')
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = ('boundary_key', 'source_repo', 'target_repo', 'contract',
              'qualification_observed', 'review_status', 'required',
              'protocol', 'method', 'route', 'audit_repo_identity', 'comment')
    with output.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter=';')
        writer.writeheader()
        for row in rows[:10000]:
            if not isinstance(row, dict):
                continue
            source = str(row.get('source') or '')
            target = str(row.get('target') or '')
            contract = str(row.get('contract') or '')
            key = hashlib.sha256((source + '\0' + target + '\0' + contract).encode()).hexdigest()[:20]
            writer.writerow({
                'boundary_key': key,
                'source_repo': _cell(source),
                'target_repo': _cell(target),
                'contract': _cell(contract),
                'qualification_observed': _cell(row.get('qualification', '')),
                'review_status': 'UNREVIEWED',
                'required': '',
                'protocol': '',
                'method': '',
                'route': '',
                'audit_repo_identity': '',
                'comment': '',
            })
    return min(len(rows), 10000)
