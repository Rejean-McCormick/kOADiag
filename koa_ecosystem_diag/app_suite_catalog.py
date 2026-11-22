# -*- coding: utf-8 -*-
"""Passive inventory of app-owned test entrypoints. No arbitrary script execution."""
from __future__ import annotations
from pathlib import Path
import json

OWNER_CANDIDATES = {
    'orgo': ('Orgo/Orgo',),
    'initkoa': ('HomePage/HomePage',),
    'konnaxion': ('Konnaxion/Konnaxion', 'Konnaxion/Konnaxion/frontend',
                  'Konnaxion/Konnaxion/backend'),
    'skope': ('Skope/Skope',),
    'ekole': ('Ekole/ekole', 'Ekole/ekole-quebec'),
    'koali': ('kOA-Linux/koali-spaces',),
}
SCRIPT_PREFIXES = ('test', 'check', 'lint', 'typecheck', 'verify', 'validate', 'quality')
MAX_SCRIPTS = 80


def discover(root: Path) -> list[dict]:
    """Only manifest existence and script names; commands can contain secrets."""
    root = Path(root).resolve()
    rows = []
    for owner, places in OWNER_CANDIDATES.items():
        found = False
        for relative in places:
            folder = (root/relative).resolve()
            if not folder.is_relative_to(root) or not folder.is_dir() or folder.is_symlink():
                continue
            found = True
            pkg = folder/'package.json'
            if pkg.is_file() and not pkg.is_symlink() and pkg.stat().st_size < 150_000:
                try:
                    scripts = json.loads(pkg.read_text(encoding='utf-8-sig')).get('scripts', {})
                    if isinstance(scripts, dict):
                        for script in list(sorted(scripts))[:MAX_SCRIPTS]:
                            if isinstance(script,str) and script.lower().startswith(SCRIPT_PREFIXES):
                                rows.append({'owner':owner,'location':relative,'kind':'npm-script',
                                             'entry':script[:80],'status':'DECOUVERT_NON_EXECUTE'})
                except (OSError,UnicodeError,ValueError,TypeError):
                    pass
            for entry in ('pytest.ini','pyproject.toml','tox.ini','Makefile'):
                f=folder/entry
                if f.is_file() and not f.is_symlink():
                    rows.append({'owner':owner,'location':relative,'kind':'manifest',
                                 'entry':entry,'status':'PRESENT_NON_EXECUTE'})
        if not found:
            rows.append({'owner':owner,'location':places[0],'kind':'repository',
                         'entry':'', 'status':'ABSENT'})
        elif not any(row['owner']==owner for row in rows):
            rows.append({'owner':owner,'location':places[0],'kind':'none',
                         'entry':'','status':'AUCUN_TEST_REFERENCE'})
    return rows
