# Validation checklist

`tools/validate_playbook.py` implements every check with an id below. Run:

```
python3 tools/validate_playbook.py <file-or-dir> --platform xsoar6|xsoar8|xsiam --strict
```

Calibration: 0 ERROR across 108 shipped CommonPlaybooks. The WARNs it raises on
shipped content (duplicate task names, missing `#default#`, unused inputs,
`system: true`) are things custom content should not do.

**Delivery bar: 0 ERROR, 0 WARN.** INFO = mention if relevant.

## Playbook (PB)

| Id | Sev | Check |
|---|---|---|
| PB-00 | ERROR | YAML parses; is a playbook or a script |
| PB-01 | ERROR | top level has id, version, name, starttaskid, tasks, inputs, outputs, fromversion |
| PB-02 | WARN | `version: -1` |
| PB-04/05 | ERROR | starttaskid exists, is type start, only one start |
| PB-06 | ERROR | `marketplaces` includes the target platform |
| PB-07 | WARN | no `system: true` |
| PB-10..13 | ERROR | key == id; taskid == task.id; uuid; unique |
| PB-14 | ERROR | known task type |
| PB-15 | WARN | non-start task has a name |
| PB-16 | ERROR | quietmode in 0/1/2 |
| PB-17 | WARN | view JSON with position; positions distinct |
| PB-18 | WARN | task names unique |
| PB-20 | ERROR | command task has `script` (INFO if bare without `\|\|\|`) |
| PB-21 | INFO | command pinned to one brand |
| PB-22 | ERROR/WARN | Set/SetAndHandleEmpty has key / value |
| PB-23 | INFO | `Set` writes empty values |
| PB-30 | INFO | manual condition (playbook waits for an analyst) |
| PB-31 | WARN | every condition label has a route |
| PB-32 | ERROR | every route label is a condition label (WARN if case differs) |
| PB-33 | ERROR | condition groups are lists |
| PB-34 | WARN | condition has `#default#` |
| PB-35 | ERROR | label routes only on conditions |
| PB-36 | ERROR/WARN | `#error#` route ⇔ `continueonerrortype: errorPath` |
| PB-37 | INFO | continue-on-error without error path |
| PB-40 | ERROR | sub-playbook task names its playbook |
| PB-41 | WARN | for-each loop has max > 0 |
| PB-42 | INFO | sub-playbook shares context |
| PB-45 | ERROR | collection task has form or message |
| PB-46 | ERROR | argument has both simple and complex |
| PB-50 | ERROR | every route target exists |
| PB-51 | WARN | every task reachable from start |
| PB-52 | WARN | no route cycles |
| PB-53 | ERROR | at least one terminal task |
| PB-60 | ERROR | every `inputs.X` is declared |
| PB-61 | WARN | every declared input is read |
| PB-62 | WARN | operator/transformer is known (else confirm on tenant) |
| PB-63 | WARN | no `${}` in an `iscontext: true` operand |
| PB-64 | WARN | context-looking left operand without iscontext |
| PB-65 | WARN | balanced `${...}` |
| PB-66 | ERROR | no hard-coded secrets |
| PB-67 | WARN/ERROR | `incident.*` on XSIAM (verify) / `alert.*` on XSOAR |
| PB-70 | INFO | closes the incident/alert |
| PB-71 | INFO | task count and scripts used |

## Script (SC)

| Id | Sev | Check |
|---|---|---|
| SC-01 | ERROR | commonfields, name, script, type present |
| SC-02/03 | WARN | id == name; version -1 |
| SC-10 | ERROR | python subtype python3 |
| SC-11 | ERROR | dockerimage pinned (WARN on :latest) |
| SC-12 | INFO | body is `-` (split format) |
| SC-13 | WARN | has error handling |
| SC-14 | ERROR | no hard-coded secrets |
| SC-15 | INFO | `demisto.results` instead of `return_results` |
| SC-16 | WARN | outputs_prefix declared in outputs |
| SC-17 | WARN | every `args.get('x')` declared |

## By reading (not mechanical)

- Sub-playbook argument names == the child's input keys (open the child).
- Every verdict row in the test matrix is reachable with real data.
- Every context path read exists **and is populated** in the sample.
- Response actions behind approval or an off-by-default input.
- Description says what the playbook does in one paragraph.
