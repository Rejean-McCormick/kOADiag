# Integration with the kOA documentation and audit ecosystem

kOADiag is an **observational consumer**, never the owner of the products it inspects. It belongs in the ecosystem's map of **key documentation and diagnostics repositories**, not the primary list of 55 authoritative target-design roles.

| Repository or tool | Boundary with kOADiag |
|---|---|
| **kOA Digital Ecosystem** | Coordinates C0 architectural owners, inventories, trust boundaries and target design. kOADiag reads declared references and produces observations; it does not revise owner contracts. |
| **kOA Doc Server** | Presents readable documentation, wikis, RepoSurveyor profiles and provenance-aware ZIP exports. kOADiag findings remain separate, scope-limited evidence and cannot be promoted by an export. |
| **RepoSurveyor** | Generates independent engineering profiles and AI navigation briefs. These are not kOADiag's cross-repo qualification reports. |
| **Kompiler** | Generates semantic Context Packs using its own pipeline; a kOADiag report or Doc Server archive is not a Context Pack. |
| **Kristal Framework / Manager** | Own semantic contracts, inventory or validation under their respective roles. Diagnostics cannot substitute for native proof. |
| **Konnaxion / Orgo** | Own the official isolated IK test kit and business semantics. Optional operator-authorized execution may write to test stacks. |
| **kOA-Digital-Ecosystem-GitHub-Audit** | Separate app for privacy-minimized, operator-reviewed, date/revision-scoped audit publication. kOADiag can prepare an allowlisted ZIP, never publish historic proof by itself. |
| **initkoa-docs** | Independent public documentation portal; derived wiki/portal pages are not a new authority for diagnostic results. |

## Audit handoff

The `export-audit` CLI action uses the allowlist implemented in `koa_ecosystem_diag/audit_export.py`. It checks report schemas and exports selected aggregate metadata and level verdicts to a deterministic ZIP. Arbitrary source paths, raw findings, credentials, URLs and trace bodies are not copied into that bundle. The export is **not a signed attestation** and is not E2E certification.

```cmd
py -3 Diagnostic-kOA-Digital-Ecosystem-CLI.py export-audit
```

Verify the latest campaign's provenance and contents before any external share. A successful export **does not** authorize a Git push, a C0 registry change or a public Audit release.

## Git identity

The supplied local 5.7.0 source snapshot establishes the code's working names, not a verified GitHub remote. Do not construct a `github.com/.../kOADiag` link unless the owner and exact remote have been independently checked.
