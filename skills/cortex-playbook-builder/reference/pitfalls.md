# Pitfalls - silent failures

Each item: symptom → cause → rule. Tag says where it was learned.

## Wiring and structure

1. **Branch goes nowhere.** Condition matched a label with no route, or no
   `#default#` → playbook stops "completed" halfway. Rule: route every label and
   `#default#`. (PB-31, PB-34) [OOB]
2. **Label case.** Condition label `yes`, route `Yes` → shipped content has it;
   do not rely on it. Identical strings. (PB-32) [OOB]
3. **Hand-typed ids.** Duplicate `taskid`, `taskid != task.id`, key `!= id`.
   Generate with the builder. (PB-10..13)
4. **Route cycles for retries.** Use a sub-playbook loop (`exitCondition` +
   `wait` + `max`) or a polling command. (PB-52)
5. **`demisto-sdk validate` is not a wiring check.** In testing it passed a file
   with a route to a missing task and a corrupted taskid. Run
   `validate_playbook.py` too.

## Context

6. **Path compared as a literal.** Operand without `iscontext: true`. (PB-64)
7. **`${}` inside `iscontext`.** Double resolution. (PB-63)
8. **Field exists, never populated.** Condition always `#default#`, looks
   clean. Verify on a real sample; `!Print value=${alert.x}`. [field]
9. **XSIAM list fields** (`alert.username` etc.) compared with
   `isEqualString` against a single value → false. `FirstArrayElement`. [field]
10. **`Set` with empty value** writes `""` and later `isNotEmpty`/`isExists`
    disagree. Use `SetAndHandleEmpty`. [OOB]
11. **Sub-playbook input name typo**: the child receives nothing and still
    succeeds. Copy keys from the child's `inputs`. (Not checkable across files.)
12. **Child context invisible to parent** with `separatecontext: true` unless
    declared in the child's `outputs`.
13. **Data collection answers keyed by task name** - renaming the ask task
    breaks every condition reading `<Name>.Answers.0`.

## Platform

14. **XSIAM: one playbook per alert.** First matching trigger by priority wins.
    To add behaviour, add a sub-playbook task at the end of the winning
    playbook rather than a competing trigger. [field]
15. **XSIAM: OOB sub-playbook not adopted** → "Playbook X is not adopted in
    Task N - stopping". Playbook Catalog → Adopt (GUI only). [field]
16. **Upload inside a content pack flips the playbook to System** and locks UI
    editing. Use REST insert / playbook import to keep it custom. [field]
17. **System content cannot be overwritten (98) or name-shadowed (33)**; system
    scripts cannot be updated (100001). New id / `_copy`. [field]
18. **Close reasons differ**: XSOAR `Resolved`, `False Positive`, `Duplicate`,
    `Other` (+ custom); XSIAM alert resolution reasons are
    `Resolved - False Positive`-style. Make CloseReason an input. [docs - verify]
19. **Jobs / scheduled runs have no alert.** `incident.*`/`alert.*` are empty.
20. **XQL quotas and parallel caps.** Every alert running an XQL task can hit
    "maximum allowed number of parallel running queries". Error-path the XQL
    task, keep one query per alert, backoff in scripts. [field]
21. **XQL `comp` drops `_vendor`/`_product`** unless re-selected. Column names
    in results are the XQL names, not mapped alert field names. [field]
22. **Two writers on one alert**: another playbook/automation rule/mirroring
    also closes or updates → last write wins. Ask before auto-close.

## Scripts

23. **No `dockerimage`** → runs on an old default image, f-strings are a
    SyntaxError. Pin the tenant's most common `demisto/python3:<tag>`. (SC-11) [field]
24. **Outputs not declared** → designer cannot offer them; the parent can't see
    them through a separate context. (SC-16)
25. **Quiet tasks leave no War Room entry.** Absence of entries is not absence
    of execution - check context and TIM. [field]
26. **Script reads args not declared** → always None from the UI. (SC-17)

## Verdicts

27. **One vendor false-positives on everything** (seen with lookups that score
    any hit). Test the matrix with a known-good value too (8.8.8.8, a Microsoft
    signed binary hash) and expect CLEAN.
28. **Threshold above reach**: score combination that can never cross it.
    Every verdict row in the test matrix must be reachable with real data.
