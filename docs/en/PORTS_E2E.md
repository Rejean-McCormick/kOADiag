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
