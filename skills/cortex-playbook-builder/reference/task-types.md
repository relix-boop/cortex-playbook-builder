# Task types - exact shapes

Every shape below is copied from shipped content [OOB] unless marked. Builder
calls in `tools/pb_builder.py` are given for each.

## start - `pb.start()`
Exactly one. Inner `task` has `name: ""`, no `type`. Routes `'#none#'`.

## title (section header) - `pb.title("Enrich")`
No logic. Use one per phase (Collect / Enrich / Verdict / Respond / Done) as
convergence points: many branches → one title keeps the canvas readable. A title
with no `nexttasks` is a terminal ("Done").

## regular - integration command - `pb.command(name, "ip", args)`
```yaml
task: {script: '|||ip', iscommand: true, brand: ""}
```
- `'|||cmd'` = run on **every** enabled instance that implements it (generic).
  Prefer it for enrichment.
- `'Brand|||cmd'` with `brand: Brand` = only that integration. Needed when two
  integrations share a command name, and for response actions.
- Special args every command accepts: `using` (instance name),
  `extend-context` (`Key=jmespath` to save raw fields), `ignore-outputs: true`,
  `execution-timeout`. [docs]
- `skipunavailable: true`: skip instead of error when no instance exists.

## regular - server builtin - `pb.builtin(name, "closeInvestigation", args)`
```yaml
task: {script: Builtin|||closeInvestigation, iscommand: true, brand: Builtin}
```
Common builtins: `closeInvestigation` (closeReason, closeNotes, id),
`setIncident` (XSOAR field updates), `setAlert` (XSIAM, verify),
`extractIndicators` (text), `enrichIndicators` (indicatorsValues),
`createNewIndicator`, `appendIndicatorField`, `linkIncidents`,
`setParentIncidentContext`, `taskComplete`, `investigate`.

## regular - automation - `pb.script(name, "Print", args)` / `pb.set(...)`
```yaml
task: {scriptName: SetAndHandleEmpty, iscommand: false, brand: ""}
```
Most used [OOB]: `Set` (79), `IsIntegrationAvailable` (70),
`SetAndHandleEmpty` (53), `SearchIncidentsV2`, `Exists`, `GetIndicatorDBotScore`,
`CountArraySize`, `DeleteContext`, `IsIPInRanges`, `MatchRegexV2`,
`PrintErrorEntry`, `FindSimilarIncidentsByText`.
`SetAndHandleEmpty` args: key, value, append, stringify, force. It does not
write when value is empty; `Set` writes `""`. Use SetAndHandleEmpty by default.

## regular - manual - `pb.manual(name, description)`
No script. Playbook waits until an analyst completes it. Use for response
steps you will not automate yet; the description says exactly what to do.

## condition - built-in - `pb.condition(name, {label: groups})`
```yaml
type: condition
conditions:
- label: "yes"
  condition:                 # list = AND of groups
  - - operator: isNotEmpty    # inner list = OR
      left: {value: {simple: Triage.IPs}, iscontext: true}
  - - operator: isEqualString
      left:  {value: {simple: inputs.AutoClose}, iscontext: true}
      right: {value: {simple: "true"}}
      ignorecase: true
nexttasks:
  "yes": ["7"]
  '#default#': ["9"]
```
- Labels are evaluated in order; first match wins. Several labels = a switch.
- Always route `'#default#'` - otherwise "no match" stops the playbook.
- Label in `conditions` and key in `nexttasks` must match exactly; shipped
  content has a `yes`/`Yes` mismatch - do not copy it.
- `yes`/`no` must be quoted in YAML (the builder does it).

## condition - by script - `pb.script_condition(name, "IsIntegrationAvailable", args)`
`task.scriptName` set, no `conditions`; the script's return value is the label
(`yes` / `no` for IsIntegrationAvailable). Routes are those labels + `#default#`.

## condition - manual
No `conditions`, no `scriptName`: the analyst picks the branch in the UI. The
playbook waits. Validator reports INFO.

## playbook (sub-playbook) - `pb.subplaybook(name, id, args, for_each=...)`
```yaml
type: playbook
task: {playbookName: X, playbookId: X, type: playbook}
scriptarguments: {IP: {complex: {root: Triage.IPs}}}   # keys = child's input keys, exact
separatecontext: true
loop: {iscommand: false, exitCondition: "", wait: 1, max: 0}
```
- `separatecontext: true`: child gets its own context; only its declared
  outputs come back. Default to true.
- **for-each**: `loop.forEach: true`, `max: N` - runs once per element of
  the inputs that are lists. Use instead of route cycles.
- **loop until**: `exitCondition` (condition list) + `wait` seconds + `max`.
- On XSIAM the child, if OOB, must be adopted first. [field]

## collection (data collection / ask) - `pb.ask(...)`
`message` (to, subject, body, methods: [] for in-app only, or `email`,
timings) + `form.questions[]` (type: shortText, longText, singleSelect,
multiSelect, number, date, boolean; `optionsarg` for options). Answers land in
`<Task Name>.Answers.<question id>` - reference with root
`Analyst decision.Answers.0`. Renaming the task breaks the reference.
Values per marketplace: `simple:marketplacev2: Investigator` overrides the
recipient on XSIAM [OOB].

For Slack/Teams approvals use the integration's ask command
(`SlackAskV2` / `MicrosoftTeamsAsk`) followed by a manual wait task carrying
the entitlement tag. The tag sits in `task.tags` inside the inner task dict,
not at the outer level - at the outer level it is dropped silently. [field]

## Error path - `pb.on_error(task, handler)`
```yaml
continueonerror: true
continueonerrortype: errorPath
nexttasks: {'#none#': [ok], '#error#': [handler]}
```
Use on calls that may legitimately fail (XQL quota, rate limits, 404 on
lookups) so the alert gets a status instead of a red playbook.

## Timers [docs]
`timertriggers: [{fieldname: timetoassignment, action: start|stop|pause}]` -
drives SLA fields. Leave empty unless the user asks for SLA tracking.
