---
name: cortex-playbook-builder
description: Build, modify and review Cortex XSOAR 6, XSOAR 8 and XSIAM playbooks as complete, importable YAML (plus the automation scripts they need). Use whenever the user wants a Cortex/XSOAR/XSIAM playbook, sub-playbook or automation - alert triage, IOC enrichment, phishing, XQL pivots, analyst approval forms, block/isolate response, auto-close - even when the logic is described in plain language, in Hebrew ("פלייבוק"), or as "fix/review this playbook YAML".
metadata:
  version: "0.1.0"
  author: Reli (CYBERcom)
---

# Cortex Playbook Builder (XSOAR 6 / XSOAR 8 / XSIAM)

Turns a use case, an alert sample or an existing export into a Cortex playbook
YAML that **uploads cleanly and does useful work once it runs**. A playbook that
imports, runs green and tells the analyst nothing is not finished.

Rule sources are tagged so you know how much to trust them:
**[OOB]** checked against the 108 shipped playbooks in `demisto/content`
CommonPlaybooks, **[field]** learned on live MDR tenants, **[docs]** general
platform knowledge - verify on the tenant before relying on it.

| Step | What you do | Read |
|---|---|---|
| 1. Gather | Ask for what only the user can see; start building anyway | `reference/no-access-checklist.md` |
| 2. Plan | Platform, trigger, data shape, result contract | `reference/platforms.md`, `reference/planning.md` |
| 3. Verify fields | Every context path exists *and* is populated | the alert/incident sample, `reference/context-and-filters.md` |
| 4. Design | Tasks, branches, convergence on paper | `reference/task-types.md` |
| 5. Generate | YAML built by `tools/pb_builder.py` - never hand-typed ids | `reference/playbook-schema.md` |
| 6. Validate | `tools/validate_playbook.py` to 0 errors / 0 warnings, then a test matrix | `reference/validation-checklist.md`, `reference/pitfalls.md` |
| 7. Deliver | The file, what to fill in, what was not verified, how to upload | `reference/delivery-and-upload.md` |

Read `playbook-schema.md`, `task-types.md`, `context-and-filters.md` and
`pitfalls.md` on **every** build. Do not rely on general XSOAR memory - most
broken generated playbooks repeat an item in `pitfalls.md`.

---

## Six principles

### 1. Assume you cannot test it - unless you can

Default: no tenant access. You produce YAML; someone else uploads and runs it.
Get right **by construction** what you cannot test, **ask** for what only the
user can see (an alert/incident JSON, the integration instances enabled, field
names), and **say so** on delivery about anything unverified, with the test plan.
If you *do* have access (API key, or the user's logged-in browser), run
everything: upload, run on a test alert, read the War Room, `!Print` the
context. "Upload success" is not verification - re-download and diff. [field]

### 2. Finished means useful, not merely valid

| It does this | Not this |
|---|---|
| Normalises and filters inputs (private IPs, empties, dupes) before enrichment | Sends everything to every vendor |
| Enrichment fans out (one generic command, or parallel branches) and converges once | Chains one lookup after another |
| A verdict **per indicator / entity**, with the reasons | One overall score |
| A middle bucket (SUSPICIOUS / UNKNOWN) when sources disagree or data is missing | Forces pass/fail |
| A readable War Room summary or layout field the analyst acts on | A context dump |
| Every path - including "nothing to check" - reaches a verdict and Done | Only the happy path finishes |

Before delivering, answer: could an analyst act **without opening context
data**? Can they see **why** each verdict? Does disagreement **show**? If any
is no, keep going. Depth is proportionate - a housekeeping playbook needs no
verdict engine.

### 3. Delivery bar: 0 errors, 0 warnings

`tools/validate_playbook.py --platform <p> --strict` must pass, or every
remaining WARN is named with its reason in the delivery message. INFO items are
expected; mention the relevant ones (auto-close, continue-on-error). The
validator was calibrated on 108 shipped playbooks (0 errors). Note:
`demisto-sdk validate` passed a file with a dangling route and a broken taskid
in testing - it is **not** a wiring check. Run both when you can. [OOB]

### 4. Native tasks first; a script only when nothing else can do it

Prefer, in this order: a **condition task** with filters, **Set /
SetAndHandleEmpty** with filters + transformers, a **generic command**
(`|||ip`, `|||file`, `|||url`, `|||domain`, `enrichIndicators`), an **OOB
sub-playbook**, a **for-each sub-playbook** loop. Write an automation only for
what transformers do badly: parsing free text or raw logs, scoring across
sources, joining fan-out results, time arithmetic, building an HTML/markdown
report. Keep it one script per job, `return_results(CommandResults(...))` with
declared outputs, pinned `dockerimage`. A playbook must stay readable and
editable in the designer - not one giant script with a Start and a Done. [field]

### 5. Deliver a complete, uploadable file

- One YAML per playbook (`playbook-<Name>.yml`, spaces → `_`), plus one unified
  YAML per new automation. Sub-playbooks first in the upload order.
- A real file, not a code block. No explanation inside the YAML beyond task
  descriptions; explanation goes in the message.
- Custom content: `version: -1`, `id` == `name`, no `system: true`,
  `marketplaces` set for the target platform(s).

### 6. Never act on a client's estate by default

Response actions (block, isolate, disable account, delete email) never get a
default brand/instance and never run without either an analyst approval task or
an explicit `AutoRespond` input defaulting to `false`. Automatically triggered
playbooks are delivered **verdict-only** first (no auto-close) and switched on
after a calibration week. [field]

---

## The workflow

### Step 1 - Gather, and start building anyway

Ask in the **first reply**, together (wording in `no-access-checklist.md`):

1. **Platform and version**: XSOAR 6.x, XSOAR 8 (SaaS / on-prem), XSIAM - and
   multi-tenant or not. It changes incident vs alert, close reasons, triggers.
2. **One real incident/alert JSON** (`!Print value=${incident}` / `${alert}`, or
   the API `incident/load/<id>`). Without it every field path is a guess.
3. **How it starts**: incident type / pre-process (XSOAR), playbook trigger or
   automation rule (XSIAM), sub-playbook of what parent, or job/scheduled.
4. **Enabled integrations** for every command used (brand + instance names) -
   needed only for brand-pinned or response commands.
5. **Does anything else close or update these alerts** (another playbook,
   automation rule, mirroring)? Before adding auto-close or write-back.

Do not stall: build with stated assumptions (generic commands, `alert.*` /
`incident.*` per platform), list each under *unverified*, and give the one-line
check that confirms it.

### Step 2 - Plan

Work through `reference/planning.md`. Two hard gates:

- **Platform decides the data model** (`platforms.md`): XSOAR → `incident.*`,
  incident types, `setIncident`; XSIAM → `alert.*` (issues), playbook triggers,
  `setAlert`, XQL, one playbook per alert (first matching trigger wins).
- **Shape**: *triage* (one alert → verdict), *investigation* (pivot with XQL /
  SIEM, enrich entities, report), *sweep / job* (no incident context - every
  `incident.*` / `alert.*` reference is empty), or *sub-playbook* (inputs in,
  outputs out, `separatecontext: true`).

### Step 3 - Verify every context path

A path that exists but is never populated makes a condition that is always
"else" and looks clean. Check each against the real sample. XSIAM list-valued
fields (`alert.username`, `alert.hostip`) need `FirstArrayElement` or a
for-each; custom fields are lowercase machine names with no spaces. Without a
sample, say which shape you assumed and give `!Print value=${alert.<field>}`. [field]

### Step 4 - Design on paper

List tasks in order with type, every condition label and where it routes, and
where branches converge (usually one title task per phase, one Done). Put every
tunable (thresholds, AutoClose, CloseReason, ranges, recipients) in playbook
**inputs** - that is the Configuration step of XSOAR. Optional enrichment uses
`skipunavailable: true` so a missing integration is skipped, not failed.

### Step 5 - Generate with `tools/pb_builder.py`

Never hand-type task ids, uuids, routes or positions. The builder makes the
task map, uuids, `#none#`/label/`#default#`/`#error#` routes, layout and
`marketplaces`. See `examples/build_examples.py` for the idioms. If no code
execution, follow `playbook-schema.md` field by field and generate uuids however
you can - but say they were hand-made.

### Step 6 - Validate, then a test matrix

```
python3 tools/validate_playbook.py playbook-X.yml --platform xsiam --strict
```
Fix to 0/0. Then by reading: every condition label routed, every branch reaches
Done, no `${}` inside `iscontext: true`, every `inputs.X` declared, sub-playbook
input names match the child exactly (a typo delivers nothing and the child
still succeeds). Test scripts locally with a fake `demisto` object against the
real sample before spending tenant runs.

**Test matrix**: one row per verdict path, plus empty input and a missing
integration. Use real known-bad values (EICAR SHA256
`275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f`, a
documented Tor exit IP) so reputation really fires. With access: create a
`ZZ <name> test` alert/incident, run, read the War Room, `!Print` the outputs.

### Step 7 - Deliver

Follow `reference/delivery-and-upload.md`: the files; what it does and its
branches; what to fill in (inputs, trigger, automation rule, approvals); what
was **not** verified and the exact check for each; upload order and method
(API/SDK keeps it custom; content-pack upload can lock it as system); the test
matrix. Say the first run is a calibration run.

---

## Platform cheat sheet

| | XSOAR 6 | XSOAR 8 | XSIAM |
|---|---|---|---|
| Object | incident | incident | alert (issue); case groups alerts |
| Context root | `incident.*` | `incident.*` | `alert.*` |
| Update fields | `Builtin\|\|\|setIncident` | `setIncident` | `setAlert` (verify) |
| Close | `Builtin\|\|\|closeInvestigation` | same | same; XSIAM close reasons differ |
| Start | incident type → default playbook | same | playbook trigger / automation rule |
| marketplaces | `xsoar` | `xsoar`, `xsoar_saas` | `marketplacev2` (`platform` on unified tenants) |
| Query data | integrations | integrations | XQL: `xdr-xql-generic-query` (polling) |
| Upload | UI import / `demisto-sdk upload` / REST | same, API key + key id | `/public_api/v1/playbooks/insert` keeps it custom |

Details, triggers and gotchas: `reference/platforms.md`.

---

## Task-specific guidance

### Modifying an existing playbook
Round-trip: download the live YAML, back it up as `<name>_backup.yml`, change
only what was asked, keep existing task ids and uuids, add new tasks with new
ids above the current max, re-validate the **whole** file, upload, re-download
and diff. Never rebuild from scratch what exists on the tenant. [field]

### OOB (system) playbooks
Cannot be overwritten (err 98) or name-shadowed (err 33). Duplicate → edit the
`_copy`, or ship a new id. On XSIAM an OOB sub-playbook must be **adopted**
(Playbook Catalog → Adopt) before a custom parent can call it. [field]

### Adapting for another tenant / client
Change only names, ids and tenant-specific inputs; keep the logic in a shared
sub-playbook, per-client differences in inputs. Brand-pinned and response
commands get the client's instance, never a default. Ship inactive / verdict-only.

### Automations (scripts)
`reference/scripts.md`: unified YAML, `subtype: python3`, pinned
`dockerimage` (take the tenant's most common `demisto/python3:<tag>`), declared
args and outputs, `return_results(CommandResults(...))`, `return_error` in
`except`. XQL from a script: start + poll with backoff, the tenant caps
parallel queries. [field]

---

## Files

| File | Read it when |
|---|---|
| `reference/playbook-schema.md` | every build - top level, task object, view, inputs/outputs, field by field |
| `reference/task-types.md` | every build - start, title, command, builtin, script, condition (built-in / script / manual), sub-playbook + loops, data collection, error path |
| `reference/context-and-filters.md` | every build - `${}` vs `iscontext`, complex roots, filters (AND/OR), transformers, DT, DBotScore |
| `reference/pitfalls.md` | every build - silent-failure modes |
| `reference/platforms.md` | step 2 - XSOAR 6 vs 8 vs XSIAM, triggers, close reasons, XQL |
| `reference/planning.md` | step 2 - planning questions and shapes |
| `reference/validation-checklist.md` | step 6 - every check with id and severity |
| `reference/no-access-checklist.md` | steps 1, 6, 7 - what to ask, self-check by reading, test plan |
| `reference/scripts.md` | any automation |
| `reference/delivery-and-upload.md` | step 7 - message template, upload by UI / SDK / API |
| `tools/pb_builder.py` | step 5 - generate the YAML |
| `tools/validate_playbook.py` | step 6 - mechanical checks (playbooks and scripts) |
| `examples/` | `playbook-CY_-_IP_Reputation_Triage.yml` (cross-platform triage, the depth to match), `playbook-CY_-_XSIAM_Sign-in_Review.yml` (XQL pivot, error path, for-each sub-playbook, analyst form) and `build_examples.py` that generates both |
