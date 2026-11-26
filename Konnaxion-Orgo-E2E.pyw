"""Windows launcher for the repository-maintained Konnaxion–Orgo test."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
from queue import Empty, Queue
import re
import shutil
import subprocess
from tempfile import NamedTemporaryFile
from threading import Thread
import tkinter as tk
from tkinter import filedialog, ttk
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

from koa_ecosystem_diag.port_diagnostics import read_registry

BRAND = '#1E6864'
PASS_MARKER = 'KONNAXION <-> ORGO IK E2E PASS'


@dataclass(frozen=True)
class Stack:
    name: str
    folder: Path
    compose_file: str
    services: tuple[str, ...]
    ready_url: str
    host_port: int

    def command(self, docker, *args):
        return [docker, 'compose', '-f', self.compose_file, *args]


def host_ports_at(root):
    """Read the *target* loopback allocations from C0; never guess free ports."""
    _, registry = read_registry(root)
    services = {row['id']: row['port'] for row in registry['services']}
    expected = ('orgo-api', 'konnaxion-api')
    missing = [name for name in expected if name not in services]
    if missing:
        raise ValueError('C0 is missing assigned service IDs: ' + ', '.join(missing))
    return services


def stacks_at(root):
    ports = host_ports_at(root)
    kx = ports['konnaxion-api']
    orgo = ports['orgo-api']
    return (
        Stack('Konnaxion', root/'Konnaxion'/'Konnaxion'/'backend', 'docker-compose.local.yml',
              ('redis', 'mailpit', 'django', 'celeryworker'),
              f'http://127.0.0.1:{kx}/health/ready/', kx),
        Stack('Orgo', root/'Orgo'/'Orgo', 'docker-compose.yml',
              ('postgres', 'api', 'worker'), f'http://127.0.0.1:{orgo}/health/ready', orgo),
    )


def invoke(args, folder, timeout):
    return subprocess.run(args, cwd=folder, shell=False, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, encoding='utf-8', errors='replace',
                          timeout=timeout, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def json_rows(output):
    if not output.strip():
        return []
    if output.lstrip().startswith('['):
        return json.loads(output)
    return [json.loads(line) for line in output.splitlines() if line.strip()]


def service_states(output):
    states = {}
    for row in json_rows(output):
        service = row['Service']
        health = str(row.get('Health') or '').lower()
        state = str(row['State']).lower()
        if state == 'running' and health in ('unhealthy', 'starting'):
            state = health
        states.setdefault(service, []).append(state)
    return states


def port_owners(docker, folder, port):
    try:
        result = invoke([docker, 'ps', '--format', '{{json .}}'], folder, 15)
        if result.returncode:
            return []
        return [row['Names'] for row in json_rows(result.stdout)
                if re.search(rf':{port}->', row.get('Ports', ''))
                and re.fullmatch(r'[A-Za-z0-9_.-]+', row.get('Names', ''))]
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError, KeyError):
        return []


def startup_diagnostic(stack, docker, service, output, emit):
    detail = output.lower()
    if any(marker in detail for marker in
           ('port is already allocated', 'address already in use', 'ports are not available',
            'only one usage of each socket address')):
        ports = re.findall(r'(?<![\w.])(?:127[.]0[.]0[.]1|0[.]0[.]0[.]0|localhost):(\d{1,5})', detail)
        port = int(ports[0]) if ports else (stack.host_port if service in ('django', 'api') else None)
        if port:
            emit(f'{stack.name} · {service}: Docker could not bind host port {port}.')
            owners = port_owners(docker, stack.folder, port)
            if owners:
                emit('Docker container(s) publishing this port: ' + ', '.join(owners) + '.')
            else:
                emit(f'To identify a Windows listener, run: Get-NetTCPConnection -State Listen -LocalPort {port}')
        else:
            emit(f'{stack.name} · {service}: Docker reported a port binding conflict.')
    elif 'permission denied' in detail or 'access is denied' in detail:
        emit(f'{stack.name} · {service}: Docker reported a permission error.')
    elif 'mount' in detail:
        emit(f'{stack.name} · {service}: Docker reported a mount error. Check the local volume paths.')
    else:
        emit(f'{stack.name} · {service}: Docker reported a start error.')
        emit(f'Inspect it in Docker Desktop or run: docker compose -f {stack.compose_file} start {service}')
        emit(f'Run that command from {stack.folder} to see Docker’s full error locally.')


def django_exit_details(stack, docker, emit):
    try:
        result = invoke(stack.command(docker, 'ps', '--all', '--quiet', 'django'), stack.folder, 15)
        container_ids = result.stdout.split() if not result.returncode else []
        for ident in container_ids:
            if not re.fullmatch(r'[a-f0-9]{12,64}', ident):
                continue
            result = invoke([docker, 'inspect', '--format', '{{json .State}}', ident], stack.folder, 15)
            if result.returncode:
                continue
            state = json.loads(result.stdout)
            code = state.get('ExitCode')
            if type(code) is int:
                emit(f'Konnaxion · django: last exit code {code}.')
            if state.get('OOMKilled') is True:
                emit('Konnaxion · django: Docker reports an out-of-memory kill.')
            if state.get('Error'):
                startup_diagnostic(stack, docker, 'django', state['Error'], emit)
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError, KeyError):
        emit('Konnaxion · django: Docker container details unavailable.')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def readiness(url):
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(url, timeout=4) as response:
            return response.status == 200
    except (HTTPError, URLError, TimeoutError, OSError):
        return False


def setup_present(backend):
    required = {'IK_ORGO_TOKEN', 'IK_ORGO_TARGET_ORGANIZATION'}
    path = backend/'.envs'/'.local'/'.django'
    if not path.is_file():
        return False
    configured = set()
    with path.open(encoding='utf-8-sig', errors='replace') as stream:
        for line in stream:
            name, sep, value = line.partition('=')
            if sep and name.strip() in required and value.strip().strip('"\'').strip():
                configured.add(name.strip())
    return required <= configured


def kit_lines(output):
    return [re.sub(r'\x1b\[[0-9;]*m', '', line).strip() for line in output.splitlines()]


def kit_failure(output, emit):
    """Keep full diagnostics locally and show bounded, recognized details in the UI."""
    lines = kit_lines(output)
    try:
        folder = Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'Konnaxion-Orgo-E2E' / 'logs'
        folder.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(mode='w', encoding='utf-8', prefix='kit-', suffix='.log',
                                dir=folder, delete=False) as log:
            log.write(output)
        emit(f'Full kit output (local, may contain sensitive data): {log.name}')
    except OSError:
        emit('Could not save the full kit output locally.')
    for line in lines:
        if re.fullmatch(r'Orgo Signal: [A-Z_]+|Orgo impact operation: [A-Z_]+', line):
            emit(line)
    patterns = (
        (r'password authentication failed', 'PostgreSQL rejected the configured credentials.'),
        (r'relation "[A-Za-z0-9_]+" does not exist', 'A database table is missing. Check Django migrations.'),
        (r"""No module named ['"][A-Za-z0-9_.]+['"]""", None),
        (r'(?:Signal read failed|Case read failed|Replay failed) HTTP [1-5][0-9]{2}', None),
        (r'Expected IK_IDEMPOTENCY_CONFLICT/409, got HTTP [1-5][0-9]{2}', None),
        (r'Expected exactly 1 task, found [0-9]+', None),
        (r'Konnaxion emission DEAD:\s+([A-Z][A-Z0-9_]{1,60})', None),
        (r'No Konnaxion IntegrationOperation was created', None),
        (r'Impact IntegrationOperation did not succeed; status=[A-Z_]+', None),
        (r'Django command did not emit IK_E2E_JSON', 'The Django shell did not return the expected test record. See the local output.'),
    )
    normalized = '\n'.join(lines)
    for pattern, description in patterns:
        match = re.search(pattern, normalized)
        if match:
            emit('Kit diagnostic: ' + (description or match.group(0)))
            break


def run_action(root, action, emit):
    if not root.is_dir():
        return 'Repository root not found.'
    try:
        stacks = stacks_at(root)
    except (OSError, ValueError, TypeError, KeyError):
        return 'BLOCKED — C0 port registry missing, invalid or incomplete. No legacy port fallback.'
    docker = shutil.which('docker')
    pwsh = shutil.which('pwsh')
    if not docker:
        return 'Docker CLI not found. Start Docker Desktop and check again.'
    emit('C0 assigned host ports (not evidence of service readiness): ' +
         ', '.join(f'{stack.name}={stack.host_port}' for stack in stacks))
    ready = True
    start_failed = False
    for stack in stacks:
        if not (stack.folder/stack.compose_file).is_file():
            emit(f'{stack.name}: Compose file missing.')
            ready = False
            continue
        try:
            result = invoke(stack.command(docker, 'ps', '--all', '--format', 'json'), stack.folder, 20)
            if result.returncode:
                emit(f'{stack.name}: Compose status unavailable. Check Docker Desktop and local configuration.')
                ready = False
                continue
            states = service_states(result.stdout)
            if action == 'start':
                stopped = [name for name in stack.services
                           if states.get(name) and all(state in ('created', 'exited') for state in states[name])]
                for name in stopped:
                    emit(f'{stack.name}: starting {name}.')
                    try:
                        result = invoke(stack.command(docker, 'start', name), stack.folder, 60)
                    except subprocess.TimeoutExpired:
                        emit(f'{stack.name} · {name}: Docker start timed out.')
                        start_failed = True
                        continue
                    if result.returncode:
                        startup_diagnostic(stack, docker, name, result.stdout + '\n' + result.stderr, emit)
                        start_failed = True
                if stopped:
                    result = invoke(stack.command(docker, 'ps', '--all', '--format', 'json'), stack.folder, 20)
                    states = service_states(result.stdout) if not result.returncode else {}
            stack_running = True
            for name in stack.services:
                values = states.get(name, [])
                label = ', '.join(values) if values else 'container missing'
                emit(f'{stack.name} · {name}: {label}')
                stack_running = stack_running and bool(values) and all(state == 'running' for state in values)
            responds = readiness(stack.ready_url)
            if responds and not stack_running:
                emit(f'{stack.name}: readiness endpoint responds, but the expected Compose services are incomplete.')
            else:
                emit(f'{stack.name} readiness: {"ready" if responds else "unavailable"}.')
            if stack.name == 'Konnaxion' and 'exited' in states.get('django', []):
                django_exit_details(stack, docker, emit)
            ready = ready and stack_running and responds
        except (OSError, subprocess.TimeoutExpired, ValueError, TypeError, KeyError):
            emit(f'{stack.name}: service check could not finish.')
            ready = False
    configured = setup_present(stacks[0].folder)
    emit('Konnaxion IK settings: ' + ('present.' if configured else 'missing. See the official local preparation guide.'))
    kit = stacks[1].folder/'validation'/'konnaxion-orgo-ik'/'run-e2e.ps1'
    if not pwsh or not kit.is_file():
        emit('PowerShell 7 or the official Orgo kit is missing.')
    if not (ready and configured and pwsh and kit.is_file()):
        if start_failed:
            return 'One or more containers failed to start. See the specific Docker errors above.'
        if action == 'start':
            return 'Check again when the containers have finished starting. Missing containers require the official setup.'
        return 'Preflight incomplete. Review the service statuses above.'
    if action != 'test':
        return 'Ready to run the official test on the configured test databases.'

    emit('Running the official test. It can take several minutes.')
    try:
        result = invoke([pwsh, '-NoProfile', '-NonInteractive', '-File', str(kit),
                         '-OrgoRoot', str(stacks[1].folder), '-KonnaxionRoot', str(stacks[0].folder.parent),
                         '-OrgoHostUrl', f'http://127.0.0.1:{stacks[1].host_port}', '-TimeoutSeconds', '120'], root, 240)
    except subprocess.TimeoutExpired as exc:
        parts = (exc.stdout or b'', exc.stderr or b'')
        output = '\n'.join(part.decode('utf-8', errors='replace') if isinstance(part, bytes) else part
                           for part in parts)
        kit_failure(output, emit)
        return 'FAIL — The kit exceeded 240 seconds. Check the test data before retrying.'
    lines = kit_lines(result.stdout)
    for line in lines:
        if re.fullmatch(r'Konnaxion emission: [a-z_]+ \(attempts=\d+\)', line):
            emit(line)
        elif line.startswith('Replay idempotency confirmed:'):
            emit('Replay idempotency confirmed.')
        elif line == 'Divergent replay conflict confirmed.':
            emit(line)
    if result.returncode == 0 and PASS_MARKER in lines:
        emit(PASS_MARKER)
        return 'PASS — The official test completed.'
    output = result.stdout + '\n' + result.stderr
    kit_failure(output, emit)
    if 'is not running' in output:
        return 'FAIL — A required container stopped during the test. Check services.'
    if any(word in output.lower() for word in ('not digitally signed', 'signé numériquement', 'pssecurityexception')):
        return 'BLOCKED — PowerShell refused to execute the script. Check its execution policy.'
    if 'prepare-local.ps1 first' in output:
        return 'BLOCKED — The IK test settings are missing. See the official setup guide.'
    if 'Timed out waiting for Konnaxion emission delivery' in output:
        return 'FAIL — Orgo did not receive the Konnaxion emission in time. Check Celery and IK routing.'
    if 'Timed out waiting for Orgo Signal processing' in output:
        return 'FAIL — Orgo did not process the signal in time. Check the Orgo worker.'
    return f'FAIL — The official kit exited with code {result.returncode}. See the kit diagnostics above.'


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Konnaxion–Orgo E2E')
        self.geometry('850x570')
        self.minsize(700, 470)
        self.events = Queue()
        self.busy = False
        self.root_path = tk.StringVar(value=r'C:\mycode')
        self.test_database = tk.BooleanVar()
        self.status = tk.StringVar(value='Check the local test stack to begin.')
        tk.Label(self, text='Konnaxion–Orgo E2E', bg=BRAND, fg='white',
                 font=('Segoe UI', 21, 'bold'), anchor='w', padx=20, pady=14).pack(fill='x')
        body = ttk.Frame(self, padding=16)
        body.pack(fill='both', expand=True)
        paths = ttk.Frame(body)
        paths.pack(fill='x')
        ttk.Label(paths, text='Repository root').pack(side='left', padx=(0, 12))
        self.path_entry = ttk.Entry(paths, textvariable=self.root_path)
        self.path_entry.pack(side='left', fill='x', expand=True)
        self.browse = ttk.Button(paths, text='Browse…', command=self.choose_root)
        self.browse.pack(side='left', padx=(8, 0))
        actions = ttk.Frame(body)
        actions.pack(fill='x', pady=(12, 6))
        self.buttons = []
        for action, label in (('check', 'Check services'), ('start', 'Start existing services'), ('test', 'Run E2E test')):
            button = ttk.Button(actions, text=label, command=lambda value=action: self.begin(value))
            button.pack(side='left', padx=(0, 8))
            self.buttons.append(button)
        self.check = ttk.Checkbutton(body, text='Konnaxion and Orgo point to test databases. This run creates test data.',
                                     variable=self.test_database, command=self.update_buttons)
        self.check.pack(anchor='w', pady=(4, 10))
        output = ttk.Frame(body)
        output.pack(fill='both', expand=True)
        self.log = tk.Text(output, wrap='word', state='disabled', font=('Consolas', 10))
        scroll = ttk.Scrollbar(output, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        ttk.Label(body, textvariable=self.status, wraplength=720).pack(fill='x', pady=(10, 0))
        self.root_path.trace_add('write', self.reset_test_confirmation)
        self.update_buttons()
        self.after(100, self.read_events)
        self.protocol('WM_DELETE_WINDOW', self.close)

    def choose_root(self):
        chosen = filedialog.askdirectory(initialdir=self.root_path.get())
        if chosen:
            self.root_path.set(chosen)

    def reset_test_confirmation(self, *_):
        self.test_database.set(False)
        self.update_buttons()

    def update_buttons(self):
        enabled = 'disabled' if self.busy else 'normal'
        for widget in (*self.buttons, self.path_entry, self.browse, self.check):
            widget.configure(state=enabled)
        if not self.test_database.get():
            self.buttons[-1].configure(state='disabled')

    def begin(self, action):
        if self.busy or (action == 'test' and not self.test_database.get()):
            return
        value = self.root_path.get().strip()
        if not value:
            self.status.set('Choose a repository root.')
            return
        root = Path(value)
        self.busy = True
        self.update_buttons()
        self.status.set('Working…')
        self.log.configure(state='normal')
        self.log.delete('1.0', 'end')
        self.log.configure(state='disabled')

        def work():
            try:
                result = run_action(root, action, lambda line: self.events.put(('log', line)))
            except (OSError, ValueError):
                result = 'The launcher could not access the configured local files or commands.'
            self.events.put(('done', result))

        Thread(target=work, daemon=True).start()

    def read_events(self):
        try:
            while True:
                kind, message = self.events.get_nowait()
                self.log.configure(state='normal')
                self.log.insert('end', message + '\n')
                self.log.see('end')
                self.log.configure(state='disabled')
                if kind == 'done':
                    self.busy = False
                    self.status.set(message)
                    self.update_buttons()
        except Empty:
            pass
        self.after(100, self.read_events)

    def close(self):
        if self.busy:
            self.status.set('Wait for the current operation to finish.')
        else:
            self.destroy()


if __name__ == '__main__':
    App().mainloop()
