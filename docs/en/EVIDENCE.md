# Evidence, provenance and qualification boundaries

**A report records a scoped observation; it is not an architecture certification.** kOADiag compares locally collected code/configuration surfaces, registry declarations and optional owner-supplied evidence. The source, its date, scope and independent corroboration determine what can be concluded.

## Observations versus owner proof

- **Static:** repository presence, links, imports, routes, schemas and proposed contracts can show a *potential or declared interface*, not a successful transaction.
- **Network probe:** an authorized GET/HEAD health response shows one endpoint's responsiveness at one time, not inter-repository business completion.
- **Passive trace pairing:** producer and consumer records must be independently sourced and match appropriate journey/correlation identifiers before a hop can be called corroborated.
- **Business E2E:** owner-operated tests on a verified isolated stack may provide stronger *specific* evidence. They still do not qualify all kOA products or automatically promote an entire maturity category.

## Interpretation of incomplete coverage

`PARTIAL` is an essential finding. It may reflect oversized/truncated files, missing IK exports, incomplete inventory alignment, a missing owner contract or an unverified journey. A downstream checker can continue where evidence exists but must carry the upstream partial warning. `BLOCKED`, `FAIL`, `ERROR` and `CONFIG_ERROR` remain distinct.

## Native report files

The configured report folder is `reports/Diagnostic-kOA-Digital-Ecosystem/`. A campaign may write:

- `latest/summary.json` and `latest/levels/Nxx/result.json` for the last observed run;
- separate timestamped run directories under the control root;
- detailed validation center reports, `causes.csv`, `niveaux.csv`, `remediations.csv` and `tests_applicatifs.csv`, as supported by the selected 5.7.0 center action;
- passive evidence maps and plan-of-action views, with effective configuration and scan-gap summaries;
- privacy-minimized audit ZIP packages under the separately documented handoff path.

The supplied snapshot includes dated older **5.6.0** reports even though the installed code in that snapshot identifies as **5.7.0**. Never present those reports as a new 5.7.0 run.

## Protect private and historical materials

Do not copy raw `.env`, auth tokens, owner database content, full HTTP messages or private trace payloads into documentation. Leave `reports/`, signed proof and owner-specific governance decisions unchanged when translating README or guides. kOADiag does not independently authorize release, publication, `C0/C1/C2/C3` promotion or a declaration of global maturity.
