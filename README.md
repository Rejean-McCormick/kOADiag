# kOADiag — kOA Digital Ecosystem Diagnostics

**Local-first cross-repository diagnostics, boundary evidence and C0 validation.**

> **Snapshot basis:** kOADiag **5.7.0**, inspected from the supplied 2026-11-20 SmartDump archive. This README describes the observed code and documented capabilities, not a fresh qualification of any currently deployed kOA application.

kOADiag helps engineers examine how independent kOA repositories relate: declared inventory, APIs and routes, events, versioned Interaction Kernel (IK) contracts, dependencies, local service ports, owner-provided traces and explicitly declared end-to-end (E2E) journeys. It generates structured, scope-limited findings and can prepare a privacy-minimized handoff for the independent GitHub Audit application.

It **does not own** product business state, Kristal semantic authority, release decisions, or security certification. A diagnostic `PASS` describes the checks actually performed; it never promotes historical evidence or automatically qualifies the whole ecosystem.

## Main capabilities

- **Passive cross-repository campaigns:** inspect structure, coverage, declared boundaries, APIs, events, dependencies, IK versions, observed exchanges and documentary continuity.
- **C0 readiness and port checks:** compare expected local service allocations with observed listeners, without starting or rewriting services.
- **Validation Center:** view campaign levels, causes and evidence, domain summaries and concrete remediation guidance. Deep validation lists owner test suites but does not run their product tests.
- **Evidence-aware E2E review:** correlate supplied sender/receiver traces and scope-limited declared journeys; a successful probe is not an E2E transaction.
- **Opt-in isolated test-stack E2E:** separately gated use of the **owner-maintained Konnaxion–Orgo** official test kit; this exceptional path may write **test** data and requires explicit user confirmation.
- **Safe audit export:** a deterministic, minimized ZIP with allowlisted verdicts and aggregate metadata, not secrets, source files, raw traces or proof of certification.

## Installation

**Windows:** Python 3.10+; Tkinter is required for the desktop interface. The evidence engine uses the third-party package pinned in [`requirements-diag-v5.4.txt`](requirements-diag-v5.4.txt), notably `jsonschema`. Use a trusted virtual environment if dependencies are not already available.

The documented local location is `C:\mycode\kOA_Digital_Ecosystem\kOADiag` (verify your actual checkout). No installer is run by opening this README. Keep local configuration and existing `reports/` outputs intact.

Launch the desktop interface:

```cmd
Lancer-Diagnostic-kOA-Digital-Ecosystem.cmd
```

Or from a terminal opened at the repository root:

```cmd
py -3 Diagnostic-kOA-Digital-Ecosystem-CLI.py manifest
py -3 Diagnostic-kOA-Digital-Ecosystem-CLI.py run structure --root C:\mycode
```

These examples are **passive by default**. See [installation and configuration](docs/en/INSTALLATION.md) before selecting other campaigns or enabling probes.

## CLI quick reference

| Example | Meaning |
|---|---|
| `py -3 Diagnostic-kOA-Digital-Ecosystem-CLI.py manifest` | Read the installed N00–N14 manifest and campaign definitions |
| `py -3 Diagnostic-kOA-Digital-Ecosystem-CLI.py run structure --root C:\mycode` | Structural, non-network campaign |
| `py -3 Diagnostic-kOA-Digital-Ecosystem-CLI.py run complet --root C:\mycode` | Full standard inter-repository campaign, with network probes still opt-in |
| `py -3 Diagnostic-kOA-Digital-Ecosystem-CLI.py ports --root C:\mycode` | Check declared C0 TCP/HTTP services; no service startup |
| `py -3 Diagnostic-kOA-Digital-Ecosystem-CLI.py history` | List local recorded campaigns |
| `py -3 Diagnostic-kOA-Digital-Ecosystem-CLI.py export-audit` | Produce a private, allowlisted audit bundle from the latest campaign |

CLI verdicts include `PASS`, `WARN`, `PARTIAL`, `FAIL`, `BLOCKED`, `ERROR`, `INFRA_ERROR` and `CONFIG_ERROR`; **`PARTIAL` is an incomplete observation, not a pass**. The CLI may return a nonzero code for a diagnostic result without indicating a Python crash.

## Reports, evidence and safety

By default, reports are written under `reports/Diagnostic-kOA-Digital-Ecosystem/`. `summary.json`, `levels/Nxx/result.json`, validation views, CSV exports and an optional audit bundle are **different artifacts with different evidence scopes**. The supplied snapshot contains older report files; their dates and suite versions must not be treated as the result of a new scan.

- Do not commit or upload `koa-ecosystem-diag.config.local.json`, private export files, raw owner traces, passwords or tokens.
- Health `200` does not demonstrate a cross-repository transaction.
- Only enable remote GET/HEAD probes with explicit approval and a reviewed destination list.
- Never run the separate transactional test-stack path without independently verified isolated databases, a named test World and a fresh confirmation.
- Historic proof and owner contracts must remain immutable; no `PASS` promotes `C0/C1/C2/C3` status on its own.

## Documentation

| Guide | Contents |
|---|---|
| [English documentation index](docs/README.md) | Navigation and scope |
| [Installation and configuration](docs/en/INSTALLATION.md) | Windows setup and local configuration |
| [Architecture and diagnostic levels](docs/en/ARCHITECTURE.md) | N00–N14 and campaign semantics |
| [CLI and campaigns](docs/en/CLI.md) | Exact CLI flags, exit behavior and safe examples |
| [Evidence and qualification](docs/en/EVIDENCE.md) | Provenance, statuses, reports and non-certification |
| [C0 ports and isolated E2E](docs/en/PORTS_E2E.md) | Probes vs real test-only execution |
| [Audit exports and integration](docs/en/INTEGRATIONS.md) | C0, Doc Server, GitHub Audit, RepoSurveyor |
| [Troubleshooting](docs/en/TROUBLESHOOTING.md) | Partial scans, missing evidence and limitations |
| [Legacy document map](docs/en/LEGACY_SOURCES.md) | Preserved historical French documents |

## Ecosystem boundaries

The **kOA Digital Ecosystem** repository maintains the C0 architecture and declared owner boundaries. **kOADiag** observes them; **kOA Doc Server** presents documentation, independent wikis and RepoSurveyor profiles; **RepoSurveyor** supplies an independent local engineering profile; **Kompiler** builds semantic Context Packs; **GitHub Audit** handles independently approved, dated publication. These are complementary responsibilities, not one automatic certification pipeline.

**Design language:** English documentation, original machine/API identifiers and native diagnostic output statuses preserved for compatibility. The original dated French reports and validation guides are not rewritten.
