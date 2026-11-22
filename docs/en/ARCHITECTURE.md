# Diagnostic architecture and levels

kOADiag 5.7.0 is an **observational** tool for independent kOA owner repositories. Its LevelUpDiag-style manifest defines fifteen levels (N00 through N14). The CLI's `run`, `manifest`, `ports`, `history` and `export-audit` actions provide separate entry points. The scheduler uses explicit dependencies, bounded worker processes and recorded verdicts.

## Levels in the installed manifest

| Level | Observed purpose |
|---|---|
| N00 | Reference integrity and security checks |
| N01 | Passive collection of inter-repository evidence |
| N02 | Topology and link ownership |
| N03 | Interaction Kernel contracts and schema drift |
| N04 | Outbound APIs and inbound routes |
| N05 | Events, topics and subscribers |
| N06 | Dependencies and version constraints |
| N07 | Cross-repository imports, CI and service variables |
| N08 | Boundary obligations |
| N09 | Traces, envelopes and IK receipts |
| N10 | Explicitly opt-in GET/HEAD API probes |
| N11 | Journey continuity and qualification evidence |
| N12 | E2E journey evidence and correlation |
| N13 | Per-repository, per-boundary and per-mode comprehensive validation |
| N14 | Separate Konnaxion–Orgo official business kit on an **isolated test stack** |

`N14` is **not** triggered by ordinary deep passive validation in the Validation Center. The owner-operated business kit is a separate, authorization-gated path. A manifest dependency or a test list is not permission to run it.

## Campaign selection

- `structure`: N00, N01, N02, N03, N06, N07, N08, N11, plus declared dependencies.
- `echanges`: N00, N01, N04, N05, N09, N10, N11, N12, plus dependencies.
- `e2e`: N00, N01, N09, N11, N12, plus dependencies; review supplied evidence only unless separately authorized.
- `complet`: N00–N12; includes an opt-in probe level but does **not** inherently authorize a network request.
- `validation-integrale`: manifest lists N00–N14; **do not select it blindly**, because a separate runtime-local operation exists for the official business test kit. Review the manifest and runtime flags.

The manifest, not this prose, controls the exact required/optional status and execution dependencies. Future versions must be rechecked rather than assumed equivalent to 5.7.0.

## Verdict discipline

`PASS`, `WARN`, `PARTIAL`, `FAIL`, `BLOCKED`, `SKIP`, `ERROR`, `INFRA_ERROR`, `CONFIG_ERROR` have different meanings. `PARTIAL` does not automatically block every downstream diagnostic; affected consumers retain an explicit partial-evidence finding. It also does not turn a missing or failed check green.

A system-level conclusion is constrained by source coverage, independent trace corroboration, declared boundaries and missing owner tests. Do not confuse a diagnostic observation with architectural C0 qualification.
