# Troubleshooting and interpretation

## A campaign returns `PARTIAL`

First read the current run's `summary.json`, level results, `scan-gaps.json` and remediation views. Common reasons in the observed 5.7.0 documentation are truncated/oversized files, incomplete declared inventory, missing independent IK traces, absent owner evidence or non-correlated E2E hops. Do not raise scan limits blindly or convert `PARTIAL` to `PASS`.

## Owner tests are listed but not run

Deep Validation Center mode inventories owner test entry points; it does **not** execute every application's suite. Separate test ownership, environment and permissions are deliberate safety boundaries.

## C0 ports are not ready

Compare the actual listener and expected service identity with the C0 registry. A stopped **optional** component does not necessarily indicate a port conflict. Port checks never start services. Test Docker intra-container routes separately when authorized.

## A `PASS` is present but the global E2E status remains unqualified

`PASS` may cover one level, one local service, one declared hop or the official kit's specific test scenarios. Missing independent traces, unreconciled contracts or uncovered boundaries can still block a global conclusion. This is expected.

## An older report appears in the snapshot

The supplied code identifies as **5.7.0**, but its stored `latest/summary.json` in the snapshot is from a **5.6.0** campaign. Never relabel it. Run a new campaign locally if a current result is required, and keep the old proof intact.

## Configuration or permissions error

Check the selected `--root`, `--config`, declared paths and actual filesystem permissions. Avoid storing machine-specific secrets in public docs. If a campaign is incomplete, inspect `CONFIG_ERROR` or `INFRA_ERROR` separately from a real observed `FAIL`.

## Need to compare the results to other tools?

Use C0 for architectural obligations, kOADiag for scoped diagnostic findings, RepoSurveyor for engineering profiles and Doc Server for navigation/extraction. Disagreements call for owner evidence review, not a synthetic global pass status.
