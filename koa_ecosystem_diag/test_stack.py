"""Start the existing local test services and wait for application readiness."""
import json
from pathlib import Path
import shutil
import subprocess
import time
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, ProxyHandler

from .port_diagnostics import read_registry

KX_FILES = ('docker-compose.local.yml', 'docker-compose.worlds.local.yml',
            'docker-compose.e2e-db.local.yml')
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


OPENER = build_opener(ProxyHandler({}), NoRedirect())


def docker_call(command, directory, timeout, log):
    result = subprocess.run(command, cwd=directory, capture_output=True,
                            stdin=subprocess.DEVNULL, encoding='utf-8',
                            errors='replace', timeout=timeout)
    log.write(f"{' '.join(command[1:])} · code {result.returncode}\n")
    log.write(result.stdout + result.stderr + '\n')
    log.flush()
    if result.returncode:
        raise ValueError(f'Docker a retourné {result.returncode}')
    return result.stdout


def wait_ready(urls, deadline, log):
    pending = dict(urls)
    while pending and time.monotonic() < deadline:
        for name, url in tuple(pending.items()):
            try:
                with OPENER.open(url, timeout=2) as response:
                    if response.status == 200 and response.geturl() == url:
                        log.write(f'{name} · HTTP 200\n')
                        del pending[name]
            except OSError:
                continue
        if pending:
            time.sleep(2)
    if pending:
        raise ValueError('Services indisponibles : ' + ', '.join(pending))


def start(orgo, backend, log, *, root):
    # Check C0 before any Docker operation; this is target allocation, not
    # evidence that the owner has deployed the binding or test DB isolation.
    _, registry = read_registry(root)
    allocations = {row['id']: row['port'] for row in registry['services']}
    if 'orgo-api' not in allocations or 'konnaxion-api' not in allocations:
        raise ValueError('Registre C0 incomplet : API Konnaxion ou Orgo manquante')
    docker = shutil.which('docker')
    if not docker:
        raise ValueError('Docker introuvable')
    for path in (orgo / 'docker-compose.yml', *(backend / name for name in KX_FILES)):
        if not path.is_file():
            raise ValueError(f'Configuration Compose absente : {path.name}')

    base = [docker, 'compose']
    kx = base + [item for name in KX_FILES for item in ('-f', name)]
    # Verify the resolved Konnaxion database target without logging credentials.
    result = subprocess.run([*kx, 'config', '--format', 'json'], cwd=backend,
                            capture_output=True, stdin=subprocess.DEVNULL, timeout=20)
    if result.returncode:
        raise ValueError('La configuration Compose Konnaxion est inexploitable')
    services = json.loads(result.stdout)['services']
    for name in ('django', 'celeryworker'):
        service = services.get(name, {})
        database = urlsplit(service.get('environment', {}).get('DATABASE_URL', ''))
        if (database.hostname, database.path) != ('kx-e2e-postgres', '/konnaxion_e2e'):
            raise ValueError(f'{name} ne cible pas la base Docker E2E Konnaxion')

    docker_call([*base, '-f', 'docker-compose.yml', 'up', '-d', '--no-build',
                 'api', 'worker'], orgo, 80, log)
    docker_call([*kx, 'up', '-d', '--no-build', 'django', 'celeryworker'], backend, 80, log)
    for command, directory, names in (
        ([*base, '-f', 'docker-compose.yml'], orgo, {'api', 'worker'}),
        (kx, backend, {'django', 'celeryworker'}),
    ):
        raw = docker_call([*command, 'ps', '--status', 'running', '--services'], directory, 15, log)
        missing = names - set(raw.splitlines())
        if missing:
            raise ValueError('Conteneurs attendus arrêtés : ' + ', '.join(sorted(missing)))
    wait_ready({'Orgo': f"http://127.0.0.1:{allocations['orgo-api']}/health/ready",
                'Konnaxion': f"http://127.0.0.1:{allocations['konnaxion-api']}/health/ready/"},
               time.monotonic() + 90, log)
