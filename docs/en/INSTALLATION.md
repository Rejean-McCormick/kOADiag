# Installation and configuration

## Observed distribution

This guide is based on the **5.7.0** snapshot: a Tkinter `.pyw` desktop application, a `.cmd` launcher, a Python CLI, the `koa_ecosystem_diag/` package, a LevelUpDiag-style manifest and tests. Nothing in this package installs or starts owner application services.

The local directory reported for the tool is:

```text
C:\mycode\kOA_Digital_Ecosystem\kOADiag
```

Check your real checkout before running any command. The executable launcher and CLI paths are relative to the folder containing them.

## Requirements

- Windows and Python 3.10 or newer for the documented desktop workflow; Tkinter must be present for the graphical interface.
- Dependencies listed in [`requirements-diag-v5.4.txt`](../../requirements-diag-v5.4.txt), including `jsonschema>=4.22,<5`, when required by the chosen workflow.
- Read permission for the **explicitly chosen** repository scan roots. Do not silently grant global write permission to all kOA projects.
- Optional: PowerShell 7.5+, Docker CLI and **isolated test instances** only for the separate owner-operated Konnaxion–Orgo E2E kit. These are not required for passive documentation or structure scans.

Use a Python environment controlled by the operator to install dependencies; never execute install scripts discovered inside third-party owner repositories as part of a passive scan.

## Launch

```cmd
Lancer-Diagnostic-kOA-Digital-Ecosystem.cmd
```

The `.cmd` launcher prefers `pyw -3`, then `pythonw`, and finally `py -3`. To print manifest metadata without using the UI:

```cmd
py -3 Diagnostic-kOA-Digital-Ecosystem-CLI.py manifest
```

## Configuration hierarchy

- `koa-ecosystem-diag.config.json`: supplied defaults, including `C:\mycode` as the default target root and `reports/Diagnostic-kOA-Digital-Ecosystem` as the control/report location.
- `koa-ecosystem-diag.config.local.example.json`: a template for local overrides.
- `koa-ecosystem-diag.config.local.json`: local operator configuration that **must not be committed**; preserve it across upgrades.
- `koa-ecosystem-diag.manifest.json`: authoritative local definitions for levels and campaign dependencies; avoid ad hoc edits.

Inspect any `--config` override before use. Private endpoints, tokens and traces are never suitable for GitHub or generic documentation exports.

## Upgrade policy

Back up the installed tool and local configuration, copy only release-approved code files, and avoid overwriting report history, local settings or historic proof. A snapshot copy is not an installer or a qualification report. For version-specific original migration constraints, consult [Legacy source map](LEGACY_SOURCES.md).
