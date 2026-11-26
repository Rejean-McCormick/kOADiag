# C0 service ports, passive checks and isolated E2E

## Port readiness is not an E2E transaction

`ports` reads the explicit C0 service allocation and checks local TCP/HTTP availability; it neither starts Docker nor repairs applications. The Validation Center distinguishes mandatory services from optional components. A stopped optional service is not necessarily a collision or failure.

```cmd
py -3 Diagnostic-kOA-Digital-Ecosystem-CLI.py ports --root C:\mycode
```

A reachable service is not proof that the intended owner, exact contract or business exchange was exercised. The local registry may change; inspect the current C0 `config/local-dev-ports.v1.json` before relying on a hardcoded address.

## Passive / active boundary

Default scans are passive. `--network` enables only explicitly configured probes. Non-loopback requests need additional acknowledgement and review. Never send probes to unknown or public endpoints as a way to infer certification.

## Separate official Konnaxion–Orgo test path

The 5.7.0 Validation Center documents a **two-stage, operator-confirmed** path to the owner-maintained official Konnaxion–Orgo IK test kit. It is not automatically run by deep validation:

1. Choose a named **test World** with the required active test release.
2. Independently verify that both backing databases and volumes are isolated, synthetic and free of production/personal data. Environment variable names or a user checkbox are not technical proof of isolation.
3. Record a time-limited local authorization for this World; it may be revoked and expires.
4. Run the preflight: C0 port registry, local HTTP services, required private-variable **presence**, Docker service readiness and network routing.
5. After a second explicit confirmation, run the owner-maintained kit only if data changes to the isolated test databases are acceptable.

The documented owner script resides under `C:\mycode\Orgo\Orgo\validation\konnaxion-orgo-ik\run-e2e.ps1`. kOADiag calls that existing owner script; it does **not** reimplement Orgo/Konnaxion business semantics. Optional E2E requires PowerShell 7.5+ and Docker CLI. No new `.ps1` script is supplied by this documentation.

## Interpreting the result

The E2E summary is sanitized: return code, script digest, PASS marker and optional hashed observation identifiers, not raw terminal output or secrets. An owner kit PASS addresses its stated scenarios only; cross-repository trust-chain validation, other modes and general maturity certification remain independent work.

See preserved [`GUIDE-E2E-V570.md`](../../GUIDE-E2E-V570.md) for the exact version-specific original procedure and its safeguards.

## C0 host-port consumers (24 November 2026)

The GUI launcher `Konnaxion-Orgo-E2E.pyw` and the legacy N14
`local_runtime.py` / `test_stack.py` path now **read** the two API host
ports from C0 `config/local-dev-ports.v1.json`, using service IDs
`orgo-api` and `konnaxion-api`. The November 23 registry proposes
Orgo `127.0.0.1:21111` (container `4000`) and Konnaxion
`127.0.0.1:21131` (container `8000`). Missing or invalid entries
**block** the launch or preflight; no fallback to the old host ports,
no automatic next-free-port search and no runtime configuration rewrite.

The C0 allocations remain **proposed** until each owner has adopted and
qualified them. A Docker Compose mapping or HTTP 200 alone does not
prove service identity, database isolation or a successful IK transaction.
The 24 November Windows evidence observed Orgo API mapped
`127.0.0.1:21111:4000` and healthy, whereas Konnaxion Django had exited
with a PostgreSQL hostname-resolution error. Fix that independently,
without replacing the database target or modifying credentials in the
launcher. The owner Compose files, internal Docker ports, official test
kit, private IK settings and explicit test-data consent are unchanged.

The separate `ik_e2e.py` path already reads the C0 registry and requires
explicit authorization before executing the owner kit. The optional
disabled example in `ik_diag_core.py` is historical and not evidence
of a live service; do not enable it without checking its URL against C0.
