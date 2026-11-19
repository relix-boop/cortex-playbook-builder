# Playbook YAML schema

The same YAML imports into XSOAR 6, XSOAR 8 and XSIAM. Shapes below are taken
from shipped content (`demisto/content`, CommonPlaybooks, 108 files) [OOB].

## Top level

```yaml
id: CY - IP Reputation Triage        # custom content: same as name
version: -1                          # always -1 for upload; server bumps it
name: CY - IP Reputation Triage
description: One paragraph. Shown in the designer and the playbook picker.
starttaskid: "0"                     # string, the start task's key
tasks: { "0": {...}, "1": {...} }    # map: string key -> task
view: |-                             # JSON *string* (designer canvas)
  {"linkLabelsPosition": {}, "paper": {"dimensions": {"height": 1200, "width": 900, "x": 0, "y": 50}}}
inputs:  [...]
outputs: [...]
tests:
- No tests
fromversion: 6.10.0                  # lowest server version that may load it
marketplaces:                        # which products may load it
- xsoar
- marketplacev2
```

Optional: `quiet: true` (quiet mode for the whole playbook - no War Room
entries from tasks), `inputSections` / `outputSections` (grouping in the UI),
`supportedModules` (XSIAM/platform module gating - leave out for custom content),
`toversion`, `deprecated`, `hidden`.

**Never ship `system: true`** for custom content - it is the flag that makes a
playbook read-only in the UI. Shipped content has it; yours must not.

`marketplaces` values: `xsoar` (XSOAR 6/8), `xsoar_saas`, `xsoar_on_prem`,
`marketplacev2` (XSIAM), `platform` (Cortex unified platform tenants),
`xpanse`. Omitted = SDK default (XSOAR only) - always set it explicitly.

## Task

```yaml
"3":
  id: "3"                            # == the map key (string)
  taskid: 8c2c...-uuid4              # == task.id below
  type: regular                      # start | title | regular | condition | playbook | collection
  task:
    id: 8c2c...-uuid4
    version: -1
    name: Get IP reputation
    description: What this task does and why (designer tooltip).
    script: '|||ip'                  # command: 'Brand|||command'; '' brand = all instances
    type: regular                    # repeats the outer type (start omits it)
    iscommand: true                  # true for integration/Builtin commands, false for scripts
    brand: ""
  nexttasks:
    '#none#': ["4"]                  # regular/title/playbook/collection
  scriptarguments:
    ip:
      complex: {root: Triage.IPs}
  separatecontext: false             # true on sub-playbook tasks
  continueonerror: false
  continueonerrortype: ""            # "" | errorPath
  view: |-
    {"position": {"x": 450, "y": 620}}
  note: false
  timertriggers: []
  ignoreworker: false
  skipunavailable: false             # true = skip when no instance/playbook exists
  quietmode: 0                       # 0 inherit playbook setting; 1 / 2 explicit (verify in UI)
  isoversize: false
  isautoswitchedtoquietmode: false
```

Other per-task keys in the wild: `conditions` (condition tasks), `loop`
(sub-playbook tasks), `message` + `form` (data collection), `results`
(script-condition outputs), `reputationcalc` (1 / 2 - indicator extraction
mode), `fieldMapping` (map command output to incident fields), `evidencedata`.

### Identity rules (ERROR if broken)
- Map key == `id` == a string; `taskid` == `task.id` == a uuid4, unique in the playbook.
- `starttaskid` names the single `type: start` task. Convention: `"0"`.
- Every id in `nexttasks` exists.
- Script tasks use `task.scriptName`; command tasks use `task.script` with `|||`.

### Routes (`nexttasks`)
| Key | On | Meaning |
|---|---|---|
| `'#none#'` | any non-condition | normal next |
| `<label>` | condition | branch whose condition matched (label string exactly, incl. case) |
| `'#default#'` | condition | else |
| `'#error#'` | any task with `continueonerrortype: errorPath` | task errored |

A list under a key = parallel branches. Convergence: several tasks route to the
same id; the target waits for all incoming branches that were taken.

## view (positions)

JSON string, `{"position": {"x": .., "y": ..}}`. Shipped content uses ~170-200
px vertical and ~400-450 px horizontal spacing. Distinct positions per task;
otherwise the designer stacks them. The builder lays out by longest-path depth.

## inputs

```yaml
inputs:
- key: IP
  value:                     # default; {} = none
    complex:
      root: alert
      accessor: hostip
  required: false
  description: ...
  playbookInputQuery: null   # or an indicator/incident query object (inputs from TIM)
```
Read as `inputs.IP` (complex root) or `${inputs.IP}` (inside a simple string).
Key names may contain spaces (`inputs.Indicator Expiration`) - avoid them in new work.

## outputs

```yaml
outputs:
- contextPath: Triage.Verdict
  description: MALICIOUS | SUSPICIOUS | CLEAN
  type: string        # string | number | boolean | date | unknown
```
Declared outputs are what the parent's designer offers. With
`separatecontext: true` the child's context is **not** visible to the parent
except through declared outputs.
