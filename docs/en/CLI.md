# CLI and campaign reference

Run commands from the kOADiag root. The literal file name is part of the current distribution; it is not being renamed by this documentation.

```cmd
py -3 Diagnostic-kOA-Digital-Ecosystem-CLI.py manifest
py -3 Diagnostic-kOA-Digital-Ecosystem-CLI.py run structure --root C:\mycode
py -3 Diagnostic-kOA-Digital-Ecosystem-CLI.py run complet --root C:\mycode
py -3 Diagnostic-kOA-Digital-Ecosystem-CLI.py ports --root C:\mycode
py -3 Diagnostic-kOA-Digital-Ecosystem-CLI.py history
py -3 Diagnostic-kOA-Digital-Ecosystem-CLI.py export-audit
```

`manifest` prints the installed manifest. `history` lists recorded campaign summaries. `ports` checks the declared local registry. `export-audit` produces an allowlisted privacy-minimized ZIP from the latest available campaign; inspect the source and destination before sharing.

## Supported CLI actions

`run`, `history`, `manifest`, `export-audit`, `ports`, and the internal `_worker` action. Do not use `_worker` as a public interface.

| Option | Meaning and safety |
|---|---|
| `--root` | Explicit repository tree to examine; default is configured under `C:\mycode` |
| `--config` | Reviewed local configuration file |
| `--jobs` | Concurrency bound |
| `--registry` | Optional exact C0 port registry for `ports` |
| `--port-timeout` / `--port-out-dir` | Local port probe timeout/report directory |
| `--network` | Enable **configured** network probes; not safe to turn on by default |
| `--remote` and `--ack-remote` | Additional controls for non-loopback endpoints; review destinations and expected traffic first |
| `--run-root`, `--out` | Input campaign and ZIP destination for `export-audit` |
| `--runtime-local`, `--world`, `--start-test-stack` | **Exceptional test-only execution**, not part of passive audits |
| `--audit`, `--audit-root` | Optional private audit integration, not a public publication action |

The last two groups are intentionally excluded from the quick-start examples. The owner test kit requires independent test-database isolation checks and explicit authorization; see [C0 ports and isolated E2E](PORTS_E2E.md).

## Exit codes

For ordinary campaign execution the code maps a `PASS` or `WARN` to `0`, `FAIL` to `10`, `BLOCKED` to `20`, `PARTIAL` to `21`, and `ERROR` to `30`. `ports` distinguishes ready (`0`), missing/unready (`10`) and wrong service or scan error (`20`). Interpret nonzero verdicts as diagnostic outcomes first; inspect `summary.json` for the reason.

## Output

The CLI prints `SUMMARY=<path>/summary.json` after a campaign, `REPORT_PORTS_C0=<directory>` after port checks and `AUDIT_EXPORT=<zip>` for an exported campaign. Treat these paths as local data and keep raw diagnostics out of public CI artifacts unless explicitly reviewed.
