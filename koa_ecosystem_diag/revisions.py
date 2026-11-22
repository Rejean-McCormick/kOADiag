"""Read checkout revisions without invoking commands in the target repositories."""
from pathlib import Path
import re

COMMIT = re.compile(r'(?:[0-9a-f]{40}|[0-9a-f]{64})\Z')
REF = re.compile(r'refs/[A-Za-z0-9._/-]+\Z')


def _commit(value):
    return value if isinstance(value, str) and COMMIT.fullmatch(value) else None


def checkout_revision(root):
    git = root / '.git'
    if not git.is_dir() or git.is_symlink():
        return None
    try:
        head = (git / 'HEAD').read_text(encoding='ascii').strip()
        if _commit(head):
            return head
        if not head.startswith('ref: '):
            return None
        ref = head[5:]
        if not REF.fullmatch(ref) or '..' in Path(ref).parts:
            return None
        path = (git / ref).resolve()
        if not path.is_relative_to(git.resolve()):
            return None
        if path.is_file():
            return _commit(path.read_text(encoding='ascii').strip())
        packed = git / 'packed-refs'
        if packed.is_file():
            with packed.open(encoding='ascii') as stream:
                for line in stream:
                    fields = line.split()
                    if len(fields) == 2 and fields[1] == ref:
                        return _commit(fields[0])
    except (OSError, UnicodeError, ValueError):
        return None
    return None


def resolve_revisions(repo_map, configured):
    configured = configured if isinstance(configured, dict) else {}
    revisions, findings = {}, []
    for repo in repo_map.values():
        root, name = repo['path'], repo['name']
        if not root.is_dir():
            continue
        head = checkout_revision(root)
        asserted = _commit(configured.get(name))
        revision = head or asserted
        if revision:
            revisions[name] = revision
        if head or name in configured:
            findings.append({'repo': name, 'revision': revision,
                'origin': 'GIT_HEAD' if head else ('CONFIGURATION' if asserted else 'INCONNUE'),
                'configuration_mismatch': name in configured and (not asserted or asserted != revision)})
    return revisions, findings
