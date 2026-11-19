# Platforms: XSOAR 6, XSOAR 8, XSIAM

One YAML format, three data models. Decide the platform before writing a path.

## XSOAR 6 (on-prem server)
- Object: **incident**. Context root `incident.*`; custom fields by machine name.
- Start: incident **type** → default playbook; pre-process rules; jobs
  (scheduled, no incident fields); manual `!setPlaybook`.
- Update: `Builtin|||setIncident` (`severity`, custom fields as args).
- Close: `Builtin|||closeInvestigation closeReason=... closeNotes=...`.
- Engines (`using` arg / instance engine) for on-prem reach.
- Upload: Settings → Playbooks → Import; `demisto-sdk upload -i file`
  (`DEMISTO_BASE_URL`, `DEMISTO_API_KEY`); REST `POST /playbook/save/yaml`
  (multipart `file`).
- `marketplaces: [xsoar]`, `fromversion` ≤ server version (6.10.0 is safe for 6.10+).

## XSOAR 8 (SaaS / on-prem 8.x)
- Same incident model and playbook YAML as 6.
- API at `https://api-<tenant>/xsoar/...` with headers `Authorization: <key>`
  and `x-xdr-auth-id: <key id>`; `demisto-sdk` reads `DEMISTO_BASE_URL`,
  `DEMISTO_API_KEY` and `XSIAM_AUTH_ID`. [docs]
- Docker images are managed; pin `dockerimage` on scripts anyway.
- `marketplaces: [xsoar, xsoar_saas]` (or `xsoar_on_prem`).

## XSIAM
- Object: **alert** (newer UI: *issue*), grouped into **cases** (formerly
  incidents). Playbooks run on alerts. Context root `alert.*`.
- Start: **Playbook triggers** (alert filter → playbook, ordered by priority)
  or **Automation Rules**. An alert runs **one** playbook - the first matching
  trigger. Ordering and Automation Rules are GUI-only. [field]
- Update: `setAlert` (verify on the tenant; `setIncident` may also map).
- Close: `closeInvestigation` closes the alert; reasons use the XSIAM
  resolution list - keep CloseReason an input. [docs - verify]
- Data: XQL through the *Cortex Core - XQL Query Engine* integration:
  `xdr-xql-generic-query` (args `query`, `time_frame`, `query_name`) - a
  polling command in a playbook task; from a script start + poll
  `xdr-xql-get-query-results`. Results under
  `PaloAltoNetworksXQL.GenericQuery.results`. [field]
- Endpoint actions: `core-*` commands (`core-get-endpoints`,
  `core-isolate-endpoint`, `core-run-script`...) [OOB names].
- OOB playbooks must be **adopted** before use. [field]
- Upload: `POST /public_api/v1/playbooks/insert` (multipart ZIP) keeps it
  CUSTOM; via webapp `/xsoar/playbook/save/yaml`. Uploading inside a content
  pack makes it System (locked). [field]
- `marketplaces: [marketplacev2]` (+ `platform` on unified tenants).
- XSIAM issue URL: `https://<tenant>/issue-view/<id>`.

## Writing one playbook for both

- Make the entity inputs (`IP`, `Username`, `Hostname`) playbook **inputs**
  with no default; the parent / trigger maps `incident.*` or `alert.*`.
- No `setIncident` / `setAlert` inside the shared playbook; return outputs
  and let a thin platform-specific parent write fields.
- Values can differ per marketplace inside one file:
  `simple: Analyst` + `simple:marketplacev2: Investigator` [OOB].
- `marketplaces: [xsoar, marketplacev2]`.

## Multi-tenant (MSSP / MDR)
- Per-tenant differences (instances, recipients, ranges, thresholds) go in
  inputs, never in logic.
- Response commands name the tenant's instance via `using`.
- One shared sub-playbook, thin per-tenant parents.
