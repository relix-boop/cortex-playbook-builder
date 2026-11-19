# Building blind - and what changes when you have access

## Ask in the first reply (all together)

> To build this so it works on your tenant I need a few things - I'll start
> with stated assumptions meanwhile:
> 1. Platform: XSOAR 6, XSOAR 8, or XSIAM? Multi-tenant?
> 2. One real alert/incident: run `!Print value=${alert}` (XSIAM) or
>    `!Print value=${incident}` (XSOAR) on a typical one and paste the output
>    (mask what you need to).
> 3. How should it start - trigger/incident type, called by another playbook,
>    or a job?
> 4. Which integrations are enabled for enrichment / response (brand names)?
> 5. Does anything else close or update these alerts (another playbook,
>    automation rule, mirroring)?

If the user cannot supply an item: proceed, state the assumption, list it under
*unverified* with the exact check.

## Self-check by reading (after the validator)

**Wiring**
- [ ] Every condition label and `#default#` routed; every branch reaches Done
- [ ] Parallel branches converge on one title, not on several leaves
- [ ] Error-path on tasks that may legitimately fail (XQL, rate-limited APIs)

**Data**
- [ ] Each path read appears in the sample, populated, with the right type (list?)
- [ ] Operands: bare path + `iscontext: true`; strings: `${path}`
- [ ] Sub-playbook argument keys copied from the child's inputs
- [ ] Every input has a description and a safe default

**Usefulness**
- [ ] Per-entity verdict with its reason, visible without opening context
- [ ] A middle bucket for disagreement / missing data
- [ ] The "nothing to check" path produces a status too

**Safety**
- [ ] Response actions behind approval or `AutoRespond=false`
- [ ] Auto-close behind `AutoClose=false`, reason from an input
- [ ] No secrets, tenant URLs or keys in the YAML

## Test plan to hand over (no access)

| # | Input | Expected |
|---|---|---|
| 1 | known-bad IP / EICAR hash | MALICIOUS, not closed |
| 2 | known-good (8.8.8.8 / signed MS binary) | CLEAN, closed only if AutoClose=true |
| 3 | private IP only | NO_PUBLIC_IP |
| 4 | empty field | the no-data status, no error |
| 5 | reputation integration disabled | skipped, verdict UNKNOWN/CLEAN, no red task |

How to run: create a test incident/alert named `ZZ <playbook> test`, attach the
playbook (`!setPlaybook name="..."`), read the War Room, then
`!Print value=${Triage}`.

## If you have access

- **API key** (XSOAR 8 / XSIAM: key + key id; XSOAR 6: key): upload, run on a
  test alert, read `/investigation/<id>` entries, re-download and diff.
- **No key, logged-in browser** (XSIAM webapp): same-origin
  `fetch('/xsoar/<path>')` with header `X-CSRF-Token: <csrf_token cookie>`;
  `playbook/save/yaml` to upload, `entry` with `{investigationId, data: "!cmd"}`
  to run commands. [field]
- Back up the live object before touching it. Never put keys in files you deliver.
- Quotas: XQL compute units and parallel query caps are per tenant - batch,
  do not poll in tight loops. [field]
